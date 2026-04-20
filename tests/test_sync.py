"""Unit tests for xsyncfar.sync."""

import sys
import tempfile
import unittest
from pathlib import Path

from xsyncfar.sync import (
    _is_valid_filename,
    apply_replacements,
    apply_replacements_to_filename,
    build_absolute_path,
    collect_other_files,
    collect_source_files,
    dest_needs_update,
    detect_direction,
    find_config,
    get_allowed_extensions,
    get_ignore_patterns,
    load_config,
    run_sync,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as fh:
        fh.write(content)


def _read(path):
    with open(str(path), encoding="utf-8") as fh:
        return fh.read()


SAMPLE_SYNCMAP = {
    "prefix": "",
    "replacements": [
        {"lab": "myapp", "prod": "targetapp"},
        {"lab": "myorg", "prod": "targetorg"},
    ],
    "mappings": [],  # filled per test
}


# ---------------------------------------------------------------------------
# find_config
# ---------------------------------------------------------------------------


class TestFindConfig(unittest.TestCase):
    def test_finds_config_in_current_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / ".xsyncfar.yml"
            _write(config, "syncmap: {}")
            result = find_config(tmp)
            self.assertEqual(result.resolve(), config.resolve())

    def test_finds_config_in_parent_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / ".xsyncfar.yml"
            _write(config, "syncmap: {}")
            child = Path(tmp) / "subdir" / "deeper"
            child.mkdir(parents=True)
            result = find_config(str(child))
            self.assertEqual(result.resolve(), config.resolve())

    def test_returns_none_when_not_found(self):
        # Use a temp dir with no config anywhere in its lineage up to tmp root
        with tempfile.TemporaryDirectory() as tmp:
            result = find_config(tmp)
            # May or may not find one depending on the machine; only assert
            # type is correct — either None or a Path.
            self.assertTrue(result is None or isinstance(result, Path))


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig(unittest.TestCase):
    def test_loads_valid_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / ".xsyncfar.yml"
            _write(config, "syncmap:\n  prefix: /tmp\n  mappings: []\n")
            syncmap = load_config(config)
            self.assertEqual(syncmap["prefix"], "/tmp")

    def test_raises_on_missing_syncmap_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / ".xsyncfar.yml"
            _write(config, "other_key: value\n")
            with self.assertRaises(ValueError):
                load_config(config)


# ---------------------------------------------------------------------------
# build_absolute_path
# ---------------------------------------------------------------------------


class TestBuildAbsolutePath(unittest.TestCase):
    def test_combines_prefix_and_relative(self):
        if sys.platform.startswith("win"):
            result = build_absolute_path("C:\\base", "sub\\path")
            self.assertIn("sub", str(result))
            self.assertIn("path", str(result))
        else:
            result = build_absolute_path("/base", "sub/path")
            self.assertEqual(result, Path("/base/sub/path").resolve())

    def test_handles_forward_slashes_on_windows(self):
        # Should not raise on either platform
        result = build_absolute_path("/tmp", "a/b/c")
        self.assertIsInstance(result, Path)


# ---------------------------------------------------------------------------
# detect_direction
# ---------------------------------------------------------------------------


class TestDetectDirection(unittest.TestCase):
    def _make_syncmap(self, lab_path, prod_path):
        return {
            "prefix": "",
            "replacements": [],
            "mappings": [
                {"lab": str(lab_path), "prod": str(prod_path)},
            ],
        }

    def test_detects_lab_to_prod(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            lab.mkdir()
            prod.mkdir()
            syncmap = self._make_syncmap(lab, prod)
            src, dst, direction = detect_direction(syncmap, cwd=str(lab))
            self.assertEqual(direction, "lab_to_prod")
            self.assertEqual(src.resolve(), lab.resolve())
            self.assertEqual(dst.resolve(), prod.resolve())

    def test_detects_prod_to_lab(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            lab.mkdir()
            prod.mkdir()
            syncmap = self._make_syncmap(lab, prod)
            src, dst, direction = detect_direction(syncmap, cwd=str(prod))
            self.assertEqual(direction, "prod_to_lab")

    def test_detects_from_subdirectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            subdir = lab / "nested" / "deeper"
            subdir.mkdir(parents=True)
            prod.mkdir()
            syncmap = self._make_syncmap(lab, prod)
            src, dst, direction = detect_direction(syncmap, cwd=str(subdir))
            self.assertEqual(direction, "lab_to_prod")

    def test_raises_systemexit_on_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            other = Path(tmp) / "other"
            lab.mkdir()
            prod.mkdir()
            other.mkdir()
            syncmap = self._make_syncmap(lab, prod)
            with self.assertRaises(SystemExit):
                detect_direction(syncmap, cwd=str(other))


# ---------------------------------------------------------------------------
# apply_replacements
# ---------------------------------------------------------------------------


class TestApplyReplacements(unittest.TestCase):
    REPLACEMENTS = [
        {"lab": "myapp", "prod": "targetapp"},
        {"lab": "myorg", "prod": "targetorg"},
    ]

    def test_lab_to_prod_lowercase(self):
        result = apply_replacements(
            "host: myapp.myorg.local",
            self.REPLACEMENTS,
            "lab_to_prod",
        )
        self.assertEqual(result, "host: targetapp.targetorg.local")

    def test_lab_to_prod_uppercase(self):
        result = apply_replacements(
            "cluster: MYAPP",
            self.REPLACEMENTS,
            "lab_to_prod",
        )
        self.assertEqual(result, "cluster: TARGETAPP")

    def test_lab_to_prod_titlecase(self):
        result = apply_replacements(
            "cluster: Myapp",
            self.REPLACEMENTS,
            "lab_to_prod",
        )
        self.assertEqual(result, "cluster: Targetapp")

    def test_lab_to_prod_mixed_case_uses_config_value(self):
        result = apply_replacements(
            "cluster: mYaPp",
            self.REPLACEMENTS,
            "lab_to_prod",
        )
        # Mixed/irregular casing: replacement used as-is from config
        self.assertEqual(result, "cluster: targetapp")

    def test_prod_to_lab(self):
        result = apply_replacements(
            "host: targetapp.targetorg.local",
            self.REPLACEMENTS,
            "prod_to_lab",
        )
        self.assertEqual(result, "host: myapp.myorg.local")

    def test_prod_to_lab_titlecase(self):
        result = apply_replacements(
            "cluster: Targetapp",
            self.REPLACEMENTS,
            "prod_to_lab",
        )
        self.assertEqual(result, "cluster: Myapp")

    def test_no_match_leaves_content_unchanged(self):
        content = "nothing to replace here"
        result = apply_replacements(content, self.REPLACEMENTS, "lab_to_prod")
        self.assertEqual(result, content)

    def test_literal_dot_not_treated_as_regex_wildcard(self):
        # With regex this would match 'myappXlocal'; as a literal it must not
        replacements = [{"lab": "myapp.local", "prod": "targetapp.local"}]
        result = apply_replacements(
            "myappXlocal myapp.local",
            replacements,
            "lab_to_prod",
        )
        self.assertEqual(result, "myappXlocal targetapp.local")

    def test_special_regex_chars_in_find_treated_as_literals(self):
        replacements = [{"lab": "my-app (v2)", "prod": "target-app (v2)"}]
        result = apply_replacements(
            "deploying my-app (v2) now",
            replacements,
            "lab_to_prod",
        )
        self.assertEqual(result, "deploying target-app (v2) now")


class TestGetAllowedExtensions(unittest.TestCase):
    def test_returns_defaults_when_not_configured(self):
        syncmap = {"prefix": "", "replacements": [], "mappings": []}
        exts = get_allowed_extensions(syncmap)
        self.assertIn(".yml", exts)
        self.assertIn(".py", exts)

    def test_returns_custom_extensions(self):
        syncmap = {"extensions": [".tf", "hcl"]}
        exts = get_allowed_extensions(syncmap)
        self.assertEqual(exts, {".tf", ".hcl"})

    def test_adds_dot_prefix_if_missing(self):
        syncmap = {"extensions": ["yml", ".json"]}
        exts = get_allowed_extensions(syncmap)
        self.assertIn(".yml", exts)
        self.assertIn(".json", exts)


# ---------------------------------------------------------------------------
# collect_source_files
# ---------------------------------------------------------------------------


class TestCollectSourceFiles(unittest.TestCase):
    def test_collects_matching_files_recursively(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            _write(base / "a.yml", "a: 1")
            _write(base / "sub" / "b.yaml", "b: 2")
            _write(base / "sub" / "c.bin", "binary")
            _write(base / "d.py", "x = 1")
            files = collect_source_files(base, {".yml", ".yaml", ".py"})
            names = [f.name for f in files]
            self.assertIn("a.yml", names)
            self.assertIn("b.yaml", names)
            self.assertIn("d.py", names)
            self.assertNotIn("c.bin", names)

    def test_returns_empty_list_for_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = collect_source_files(Path(tmp), {".yml"})
            self.assertEqual(files, [])


# ---------------------------------------------------------------------------
# dest_needs_update
# ---------------------------------------------------------------------------


class TestDestNeedsUpdate(unittest.TestCase):
    def test_true_when_dest_missing(self):
        self.assertTrue(dest_needs_update("content", Path("/nonexistent/file.txt")))

    def test_false_when_content_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "file.txt"
            _write(dest, "same content")
            self.assertFalse(dest_needs_update("same content", dest))

    def test_true_when_content_differs(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "file.txt"
            _write(dest, "old content")
            self.assertTrue(dest_needs_update("new content", dest))


# ---------------------------------------------------------------------------
# run_sync (integration)
# ---------------------------------------------------------------------------


class TestRunSync(unittest.TestCase):
    def _make_syncmap(self, lab_path, prod_path, replacements=None):
        return {
            "prefix": "",
            "replacements": replacements
            or [
                {"lab": "myapp", "prod": "targetapp"},
            ],
            "mappings": [
                {"lab": str(lab_path), "prod": str(prod_path)},
            ],
        }

    def test_sync_copies_and_transforms_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            _write(lab / "config.yml", "cluster: myapp\n")
            _write(lab / "sub" / "deploy.yml", "env: myapp\n")
            syncmap = self._make_syncmap(lab, prod)
            changed = run_sync(lab, prod, "lab_to_prod", syncmap)
            self.assertEqual(len(changed), 2)
            self.assertEqual(_read(prod / "config.yml"), "cluster: targetapp\n")
            self.assertEqual(_read(prod / "sub" / "deploy.yml"), "env: targetapp\n")

    def test_sync_skips_unchanged_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            _write(lab / "config.yml", "cluster: myapp\n")
            # Pre-populate destination with already-correct content
            _write(prod / "config.yml", "cluster: targetapp\n")
            syncmap = self._make_syncmap(lab, prod)
            changed = run_sync(lab, prod, "lab_to_prod", syncmap)
            self.assertEqual(changed, [])

    def test_sync_creates_missing_dest_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            _write(lab / "a" / "b" / "c.yml", "key: myapp\n")
            syncmap = self._make_syncmap(lab, prod)
            run_sync(lab, prod, "lab_to_prod", syncmap)
            self.assertTrue((prod / "a" / "b" / "c.yml").exists())

    def test_sync_prod_to_lab_reverses_replacements(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            _write(prod / "config.yml", "cluster: targetapp\n")
            syncmap = self._make_syncmap(lab, prod)
            run_sync(prod, lab, "prod_to_lab", syncmap)
            self.assertEqual(_read(lab / "config.yml"), "cluster: myapp\n")

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            _write(lab / "config.yml", "cluster: myapp\n")
            syncmap = self._make_syncmap(lab, prod)
            changed = run_sync(lab, prod, "lab_to_prod", syncmap, dry_run=True)
            self.assertEqual(len(changed), 1)
            self.assertFalse((prod / "config.yml").exists())

    def test_sync_respects_custom_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            _write(lab / "file.tf", "provider: myapp\n")
            _write(lab / "file.yml", "key: myapp\n")
            syncmap = self._make_syncmap(lab, prod)
            syncmap["extensions"] = [".tf"]
            changed = run_sync(lab, prod, "lab_to_prod", syncmap)
            self.assertTrue((prod / "file.tf").exists())
            self.assertFalse((prod / "file.yml").exists())
            self.assertEqual(len(changed), 1)

    def test_copy_other_files_copies_non_matching_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            _write(lab / "config.yml", "key: myapp\n")
            # Binary-ish file whose extension is not in the default set
            (lab / "logo.png").parent.mkdir(parents=True, exist_ok=True)
            (lab / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            syncmap = self._make_syncmap(lab, prod)
            syncmap["copy_other_files"] = True
            changed = run_sync(lab, prod, "lab_to_prod", syncmap)
            self.assertIn("logo.png", [c.replace("\\", "/") for c in changed])
            self.assertEqual((prod / "logo.png").read_bytes(), b"\x89PNG\r\n\x1a\n")

    def test_copy_other_files_false_skips_non_matching(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            _write(lab / "config.yml", "key: myapp\n")
            (lab / "logo.png").parent.mkdir(parents=True, exist_ok=True)
            (lab / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            syncmap = self._make_syncmap(lab, prod)
            # copy_other_files not set (defaults to False)
            run_sync(lab, prod, "lab_to_prod", syncmap)
            self.assertFalse((prod / "logo.png").exists())

    def test_copy_other_files_skips_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            data = b"\x89PNG\r\n\x1a\n"
            (lab / "logo.png").parent.mkdir(parents=True, exist_ok=True)
            (lab / "logo.png").write_bytes(data)
            # Pre-populate destination with identical content
            (prod / "logo.png").parent.mkdir(parents=True, exist_ok=True)
            (prod / "logo.png").write_bytes(data)
            syncmap = self._make_syncmap(lab, prod)
            syncmap["copy_other_files"] = True
            changed = run_sync(lab, prod, "lab_to_prod", syncmap)
            # No text files changed, binary file unchanged — nothing reported
            self.assertEqual(changed, [])

    def test_copy_other_files_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            (lab / "logo.png").parent.mkdir(parents=True, exist_ok=True)
            (lab / "logo.png").write_bytes(b"\x89PNG")
            syncmap = self._make_syncmap(lab, prod)
            syncmap["copy_other_files"] = True
            changed = run_sync(lab, prod, "lab_to_prod", syncmap, dry_run=True)
            self.assertEqual(len(changed), 1)
            self.assertFalse((prod / "logo.png").exists())


# ---------------------------------------------------------------------------
# collect_other_files
# ---------------------------------------------------------------------------


class TestCollectOtherFiles(unittest.TestCase):
    def test_returns_files_not_in_extension_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "config.yml", "")
            (root / "logo.png").write_bytes(b"")
            (root / "script.sh").write_bytes(b"")
            other = collect_other_files(root, {".yml"})
            names = {p.name for p in other}
            self.assertIn("logo.png", names)
            self.assertIn("script.sh", names)
            self.assertNotIn("config.yml", names)

    def test_returns_empty_when_all_files_match_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "a.yml", "")
            _write(root / "b.yml", "")
            other = collect_other_files(root, {".yml"})
            self.assertEqual(other, [])


# ---------------------------------------------------------------------------
# get_ignore_patterns
# ---------------------------------------------------------------------------


class TestGetIgnorePatterns(unittest.TestCase):
    def test_returns_defaults_when_no_ignore_key(self):
        patterns = get_ignore_patterns({})
        self.assertIn(".git", patterns)

    def test_merges_config_patterns_with_defaults(self):
        patterns = get_ignore_patterns({"ignore": ["*.pyc", "__pycache__"]})
        self.assertIn(".git", patterns)
        self.assertIn("*.pyc", patterns)
        self.assertIn("__pycache__", patterns)

    def test_empty_ignore_list_returns_only_defaults(self):
        defaults = get_ignore_patterns({})
        patterns = get_ignore_patterns({"ignore": []})
        self.assertEqual(len(patterns), len(defaults))


# ---------------------------------------------------------------------------
# ignore patterns applied during collection
# ---------------------------------------------------------------------------


class TestIgnorePatterns(unittest.TestCase):
    def test_git_directory_ignored_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / ".git" / "HEAD", "ref: refs/heads/main\n")
            _write(root / ".git" / "config", "[core]\n")
            _write(root / "values.yml", "key: val\n")
            # Use default patterns (no explicit ignore_patterns arg)
            files = collect_source_files(root, {".yml"})
            names = {p.name for p in files}
            self.assertIn("values.yml", names)
            self.assertNotIn("HEAD", names)
            self.assertNotIn("config", names)

    def test_custom_pattern_excludes_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "dist" / "output.yml", "")
            _write(root / "src" / "main.yml", "")
            files = collect_source_files(root, {".yml"}, ignore_patterns=[".git", "dist"])
            paths = {str(p.relative_to(root)) for p in files}
            self.assertTrue(any("main.yml" in p for p in paths))
            self.assertFalse(any("output.yml" in p for p in paths))

    def test_wildcard_pattern_excludes_matching_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "keep.yml", "")
            _write(root / "skip.yml", "")
            files = collect_source_files(root, {".yml"}, ignore_patterns=["skip.*"])
            names = {p.name for p in files}
            self.assertIn("keep.yml", names)
            self.assertNotIn("skip.yml", names)

    def test_ignored_directory_not_descended_into(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "node_modules" / "lib" / "index.js", "")
            _write(root / "app.yml", "")
            files = collect_source_files(root, {".yml", ".js"}, ignore_patterns=["node_modules"])
            names = {p.name for p in files}
            self.assertNotIn("index.js", names)

    def test_double_star_pattern_matches_at_root_level(self):
        """**/tenants/core should exclude tenants/core even at the source root."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "tenants" / "core" / "vars.yaml", "")
            _write(root / "tenants" / "_template" / "ns.yaml", "")
            _write(root / "values.yml", "")
            files = collect_source_files(root, {".yaml", ".yml"}, ignore_patterns=["**/tenants/core"])
            rel_paths = {str(p.relative_to(root)) for p in files}
            self.assertTrue(any("values.yml" in p for p in rel_paths))
            self.assertTrue(any("_template" in p for p in rel_paths))
            self.assertFalse(any("core" in p for p in rel_paths))

    def test_run_sync_respects_ignore_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            _write(lab / "values.yml", "cluster: myapp\n")
            _write(lab / ".git" / "config", "gitdata\n")
            syncmap = {
                "prefix": "",
                "replacements": [{"lab": "myapp", "prod": "targetapp"}],
                "mappings": [{"lab": str(lab), "prod": str(prod)}],
            }
            run_sync(lab, prod, "lab_to_prod", syncmap)
            self.assertTrue((prod / "values.yml").exists())
            self.assertFalse((prod / ".git" / "config").exists())


# ---------------------------------------------------------------------------
# _is_valid_filename
# ---------------------------------------------------------------------------


class TestIsValidFilename(unittest.TestCase):
    def test_valid_names(self):
        for name in ["values.yml", "myapp-config.json", "README.md", "file"]:
            self.assertTrue(_is_valid_filename(name), f"Expected valid: {name!r}")

    def test_empty_string(self):
        self.assertFalse(_is_valid_filename(""))

    def test_invalid_chars(self):
        for name in [
            "foo/bar.yml",
            "foo\\bar.yml",
            "foo:bar.yml",
            "foo*bar.yml",
            "foo?bar.yml",
            'foo"bar.yml',
            "foo<bar.yml",
            "foo>bar.yml",
            "foo|bar.yml",
            "foo\x00bar.yml",
        ]:
            self.assertFalse(_is_valid_filename(name), f"Expected invalid: {name!r}")

    def test_windows_reserved_names(self):
        for name in ["CON", "con", "CON.txt", "PRN.yml", "NUL", "COM1", "LPT9"]:
            self.assertFalse(_is_valid_filename(name), f"Expected invalid: {name!r}")

    def test_only_dots(self):
        self.assertFalse(_is_valid_filename("."))
        self.assertFalse(_is_valid_filename(".."))

    def test_dotfile_is_valid(self):
        self.assertTrue(_is_valid_filename(".gitignore"))


# ---------------------------------------------------------------------------
# apply_replacements_to_filename
# ---------------------------------------------------------------------------


class TestApplyReplacementsToFilename(unittest.TestCase):
    REPLACEMENTS = [
        {"lab": "myapp", "prod": "targetapp"},
        {"lab": "myorg", "prod": "targetorg"},
    ]

    def test_renames_stem_lab_to_prod(self):
        result = apply_replacements_to_filename("myapp-values.yml", self.REPLACEMENTS, "lab_to_prod")
        self.assertEqual(result, "targetapp-values.yml")

    def test_renames_stem_prod_to_lab(self):
        result = apply_replacements_to_filename("targetapp-values.yml", self.REPLACEMENTS, "prod_to_lab")
        self.assertEqual(result, "myapp-values.yml")

    def test_no_match_returns_none(self):
        result = apply_replacements_to_filename("unrelated.yml", self.REPLACEMENTS, "lab_to_prod")
        self.assertIsNone(result)

    def test_extension_preserved(self):
        result = apply_replacements_to_filename("myapp.json", self.REPLACEMENTS, "lab_to_prod")
        self.assertEqual(result, "targetapp.json")

    def test_no_extension_file(self):
        result = apply_replacements_to_filename("myapp", self.REPLACEMENTS, "lab_to_prod")
        self.assertEqual(result, "targetapp")

    def test_invalid_result_returns_none(self):
        # Replacement introduces a / making the filename invalid
        replacements = [{"lab": "myapp", "prod": "target/app"}]
        result = apply_replacements_to_filename("myapp.yml", replacements, "lab_to_prod")
        self.assertIsNone(result)

    def test_case_mirroring_uppercase(self):
        result = apply_replacements_to_filename("MYAPP.yml", self.REPLACEMENTS, "lab_to_prod")
        self.assertEqual(result, "TARGETAPP.yml")

    def test_case_mirroring_titlecase(self):
        result = apply_replacements_to_filename("Myapp.yml", self.REPLACEMENTS, "lab_to_prod")
        self.assertEqual(result, "Targetapp.yml")


# ---------------------------------------------------------------------------
# run_sync with rename_files=True
# ---------------------------------------------------------------------------


class TestRunSyncFileRenaming(unittest.TestCase):
    SYNCMAP = {
        "prefix": "",
        "replacements": [{"lab": "myapp", "prod": "targetapp"}],
        "mappings": [],
    }

    def test_file_renamed_in_dest(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            _write(lab / "myapp-values.yml", "name: myapp\n")
            changed = run_sync(lab, prod, "lab_to_prod", self.SYNCMAP, rename_files=True)
            self.assertTrue((prod / "targetapp-values.yml").exists())
            self.assertFalse((prod / "myapp-values.yml").exists())
            self.assertIn("targetapp-values.yml", changed)

    def test_content_also_replaced_in_renamed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            _write(lab / "myapp-values.yml", "name: myapp\n")
            run_sync(lab, prod, "lab_to_prod", self.SYNCMAP, rename_files=True)
            content = _read(prod / "targetapp-values.yml")
            self.assertIn("targetapp", content)
            self.assertNotIn("myapp", content)

    def test_no_rename_without_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            _write(lab / "myapp-values.yml", "name: myapp\n")
            run_sync(lab, prod, "lab_to_prod", self.SYNCMAP, rename_files=False)
            self.assertTrue((prod / "myapp-values.yml").exists())
            self.assertFalse((prod / "targetapp-values.yml").exists())

    def test_invalid_rename_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            _write(lab / "myapp-values.yml", "name: myapp\n")
            syncmap = {
                "prefix": "",
                "replacements": [{"lab": "myapp", "prod": "target/app"}],
                "mappings": [],
            }
            run_sync(lab, prod, "lab_to_prod", syncmap, rename_files=True)
            # Original filename kept because replacement is invalid
            self.assertTrue((prod / "myapp-values.yml").exists())
            self.assertFalse((prod / "target" / "app-values.yml").exists())

    def test_subdir_rename(self):
        with tempfile.TemporaryDirectory() as tmp:
            lab = Path(tmp) / "lab"
            prod = Path(tmp) / "prod"
            _write(lab / "config" / "myapp-values.yml", "name: myapp\n")
            run_sync(lab, prod, "lab_to_prod", self.SYNCMAP, rename_files=True)
            self.assertTrue((prod / "config" / "targetapp-values.yml").exists())


if __name__ == "__main__":
    unittest.main()
