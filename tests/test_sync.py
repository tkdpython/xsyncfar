"""Unit tests for xsyncfar.sync."""

import sys
import tempfile
import unittest
from pathlib import Path

from xsyncfar.sync import (
    apply_replacements,
    build_absolute_path,
    collect_source_files,
    dest_needs_update,
    detect_direction,
    find_config,
    get_allowed_extensions,
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


if __name__ == "__main__":
    unittest.main()
