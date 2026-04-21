"""Core sync logic for xsyncfar."""

import fnmatch
import os
import re
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

CONFIG_FILENAME = ".xsyncfar.yml"
DEFAULT_EXTENSIONS = {".py", ".yml", ".yaml", ".json", ".txt", ".md"}


# ---------------------------------------------------------------------------
# Config discovery
# ---------------------------------------------------------------------------


def find_config(start_dir=None):
    """Walk up the directory tree from start_dir to find .xsyncfar.yml.

    Returns the Path to the config file, or None if not found.
    """
    current = Path(start_dir or os.getcwd()).resolve()
    while True:
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            return None
        current = parent


def load_config(config_path):
    """Parse the YAML config file and return the syncmap dict."""
    if yaml is None:
        raise RuntimeError("PyYAML is required to parse the config file. Install it with: pip install pyyaml")
    with open(str(config_path), encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not raw or "syncmap" not in raw:
        raise ValueError(f"Config file '{config_path}' must contain a top-level 'syncmap' key.")
    return raw["syncmap"]


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _is_relative_to(child, parent):
    """Python 3.6-compatible equivalent of Path.is_relative_to()."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _path_is_relative_to(child, parent):
    """Cross-platform, case-aware is_relative_to."""
    if sys.platform.startswith("win"):
        try:
            Path(str(child).lower()).relative_to(Path(str(parent).lower()))
            return True
        except ValueError:
            return False
    return _is_relative_to(child, parent)


def _paths_equal(a, b):
    """Case-insensitive on Windows, case-sensitive elsewhere."""
    if sys.platform.startswith("win"):
        return str(a).lower() == str(b).lower()
    return a == b


def build_absolute_path(prefix, relative):
    """Combine prefix and a mapping-relative path into an absolute Path.

    Handles both Windows backslash and POSIX forward-slash separators.
    """
    prefix_path = Path(prefix)
    rel_path = Path(relative.replace("\\", os.sep).replace("/", os.sep))
    return (prefix_path / rel_path).resolve()


# ---------------------------------------------------------------------------
# Direction detection
# ---------------------------------------------------------------------------


def detect_direction(syncmap, cwd=None):
    """Determine sync direction based on CWD.

    Returns a tuple (source_path, dest_path, direction) where direction is
    either 'lab_to_prod' or 'prod_to_lab'.
    Raises SystemExit if no mapping matches.
    """
    prefix = syncmap.get("prefix", "")
    mappings = syncmap.get("mappings", [])
    cwd_path = Path(cwd or os.getcwd()).resolve()

    for mapping in mappings:
        lab_abs = build_absolute_path(prefix, mapping["lab"])
        prod_abs = build_absolute_path(prefix, mapping["prod"])

        if _path_is_relative_to(cwd_path, lab_abs) or _paths_equal(cwd_path, lab_abs):
            return lab_abs, prod_abs, "lab_to_prod"
        if _path_is_relative_to(cwd_path, prod_abs) or _paths_equal(cwd_path, prod_abs):
            return prod_abs, lab_abs, "prod_to_lab"

    raise SystemExit(
        f"Error: The current directory '{cwd_path}' does not match any mapping in the config.\n"
        f"Run xsyncfar from within a directory listed in the 'mappings' section of {CONFIG_FILENAME}."
    )


# ---------------------------------------------------------------------------
# Replacement application
# ---------------------------------------------------------------------------


def _match_case(matched, replacement):
    """Mirror the casing pattern of matched onto replacement.

    Three patterns are recognised:
      - ALL UPPER  : MYAPP  -> TARGETAPP
      - all lower  : myapp  -> targetapp
      - Title case : Myapp  -> Targetapp  (first char upper, rest lower)
    Anything else (mixed/irregular) returns the replacement as defined in config.
    """
    if matched.isupper():
        return replacement.upper()
    if matched.islower():
        return replacement.lower()
    if matched[0].isupper() and matched[1:].islower():
        return replacement[0].upper() + replacement[1:].lower()
    return replacement


def apply_replacements(content, replacements, direction):
    """Apply all find/replace rules to content and return the result.

    Matching is case-insensitive. The casing pattern of each matched
    occurrence is mirrored onto the replacement string.
    'lab_to_prod': find lab strings, replace with prod strings.
    'prod_to_lab': find prod strings, replace with lab strings.
    """
    for entry in replacements:
        if direction == "lab_to_prod":
            find = entry["lab"]
            replacement = entry["prod"]
        else:
            find = entry["prod"]
            replacement = entry["lab"]
        content = re.sub(
            re.escape(find),
            lambda m, r=replacement: _match_case(m.group(), r),
            content,
            flags=re.IGNORECASE,
        )
    return content


# ---------------------------------------------------------------------------
# Filename renaming
# ---------------------------------------------------------------------------

# Characters that are never legal in a filename on any supported platform.
_INVALID_FILENAME_CHARS = set('/\\:*?"<>|\x00')


def _is_valid_filename(name):
    """Return True if name is a legal filename on the current platform.

    Checks for:
    - Empty string
    - Characters illegal on Windows or POSIX (/, \\, :, *, ?, ", <, >, |, NUL)
    - Windows-reserved names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    - Names that are only dots (. or ..)
    """
    if not name:
        return False
    if any(ch in _INVALID_FILENAME_CHARS for ch in name):
        return False
    stem = name.rsplit(".", 1)[0].upper()
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
    if stem in reserved:
        return False
    if all(ch == "." for ch in name):
        return False
    return True


def apply_replacements_to_filename(filename, replacements, direction):
    """Apply find/replace rules to the stem of a filename, preserving the extension.

    Returns the new filename if the result is valid and different from the
    original, or None if no replacement matched or if any replacement would
    produce an invalid filename (in which case the file should not be renamed).
    """
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    new_stem = apply_replacements(stem, replacements, direction)
    if new_stem == stem:
        return None
    new_filename = new_stem + suffix
    if not _is_valid_filename(new_filename):
        return None
    return new_filename


# ---------------------------------------------------------------------------
# File selection
# ---------------------------------------------------------------------------

DEFAULT_IGNORE_PATTERNS = [".git", ".git/**", "**/.git", "**/.git/**"]


def get_ignore_patterns(syncmap):
    """Return the combined list of ignore patterns (defaults + config)."""
    config_patterns = syncmap.get("ignore", [])
    return DEFAULT_IGNORE_PATTERNS + list(config_patterns)


def _is_ignored(path, source_path, patterns):
    """Return True if path matches any ignore pattern.

    Patterns are matched against:
    - the filename/directory name alone  (e.g. ``*.pyc``)
    - the path relative to source_path   (e.g. ``build/**``)
    Both comparisons use forward slashes for cross-platform consistency.
    """
    rel = path.relative_to(source_path)
    rel_str = rel.as_posix()  # always forward slashes
    name = path.name
    for pattern in patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
        if fnmatch.fnmatch(rel_str, pattern):
            return True
        # Strip leading **/ repetitions and retry — fnmatch cannot match
        # "tenants/core" against "**/tenants/core" because ** requires a
        # preceding "/" that isn't there at the root of the relative path.
        stripped = pattern
        while stripped.startswith("**/"):
            stripped = stripped[3:]
        if stripped != pattern and fnmatch.fnmatch(rel_str, stripped):
            return True
    return False


def get_allowed_extensions(syncmap):
    """Return the set of allowed extensions from config, or the defaults."""
    extensions = syncmap.get("extensions")
    if extensions is not None:
        return {ext if ext.startswith(".") else f".{ext}" for ext in extensions}
    return DEFAULT_EXTENSIONS


def get_match_globs(syncmap):
    """Return the list of filename glob patterns from 'match_file_globs' in config.

    These patterns are matched against the filename (not the full path) and
    allow files without conventional extensions (e.g. ``Dockerfile``,
    ``Makefile``, ``.env``) to be included in the sync as text files.
    Returns an empty list if not configured.
    """
    return list(syncmap.get("match_file_globs", []))


def _matches_globs(filename, globs):
    """Return True if filename matches any of the provided glob patterns."""
    for pattern in globs:
        if fnmatch.fnmatch(filename, pattern):
            return True
    return False


def collect_source_files(source_path, allowed_extensions, ignore_patterns=None, match_globs=None):
    """Recursively collect all eligible files under source_path.

    A file is eligible if:
    - its extension (lowercased) is in *allowed_extensions*, OR
    - its filename matches any pattern in *match_globs*.

    Returns a sorted list of absolute Path objects.
    """
    if ignore_patterns is None:
        ignore_patterns = []
    if match_globs is None:
        match_globs = []
    files = []
    for root, dirs, filenames in os.walk(str(source_path)):
        root_path = Path(root)
        # Prune ignored directories in-place so os.walk won't descend into them
        dirs[:] = [d for d in dirs if not _is_ignored(root_path / d, source_path, ignore_patterns)]
        for filename in filenames:
            fp = root_path / filename
            if _is_ignored(fp, source_path, ignore_patterns):
                continue
            if fp.suffix.lower() in allowed_extensions or _matches_globs(filename, match_globs):
                files.append(fp)
    return sorted(files)


def collect_other_files(source_path, allowed_extensions, ignore_patterns=None, match_globs=None):
    """Recursively collect all files whose extension is NOT in allowed_extensions
    and whose filename does not match any pattern in match_globs.

    Returns a sorted list of absolute Path objects.
    """
    if ignore_patterns is None:
        ignore_patterns = []
    if match_globs is None:
        match_globs = []
    files = []
    for root, dirs, filenames in os.walk(str(source_path)):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if not _is_ignored(root_path / d, source_path, ignore_patterns)]
        for filename in filenames:
            fp = root_path / filename
            if _is_ignored(fp, source_path, ignore_patterns):
                continue
            if fp.suffix.lower() not in allowed_extensions and not _matches_globs(filename, match_globs):
                files.append(fp)
    return sorted(files)


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------


def read_file_text(path):
    """Read a text file and return its contents, or None if it doesn't exist."""
    try:
        with open(str(path), encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def dest_needs_update(transformed, dest_path):
    """Return True if transformed content differs from the destination file."""
    existing = read_file_text(dest_path)
    if existing is None:
        return True
    return transformed != existing


def dest_needs_update_bytes(src_path, dest_path):
    """Return True if the destination file is missing or differs from the source (binary compare)."""
    if not dest_path.exists():
        return True
    try:
        with open(str(src_path), "rb") as s, open(str(dest_path), "rb") as d:
            return s.read() != d.read()
    except OSError:
        return True


# ---------------------------------------------------------------------------
# High-level sync runner
# ---------------------------------------------------------------------------


def run_sync(source_path, dest_path, direction, syncmap, dry_run=False, rename_files=False):
    """Perform the sync from source_path to dest_path.

    Applies find/replace rules to eligible text files and only writes files
    whose content has changed.  If 'copy_other_files' is True in the syncmap,
    files whose extension is not in the allowed list are copied as-is (binary
    copy, no replacements applied).
    If rename_files is True, the replacement rules are also applied to each
    filename stem.  Any replacement that would produce an invalid filename is
    silently skipped and the original filename is kept.
    Returns a list of relative path strings that were written/changed.
    Set dry_run=True to skip writing (used in tests).
    """
    replacements = syncmap.get("replacements", [])
    allowed_extensions = get_allowed_extensions(syncmap)
    ignore_patterns = get_ignore_patterns(syncmap)
    match_globs = get_match_globs(syncmap)
    copy_other = syncmap.get("copy_other_files", False)
    source_files = collect_source_files(source_path, allowed_extensions, ignore_patterns, match_globs)
    changed_files = []

    for src_file in source_files:
        rel = src_file.relative_to(source_path)

        if rename_files:
            new_filename = apply_replacements_to_filename(src_file.name, replacements, direction)
        else:
            new_filename = None

        if new_filename is not None:
            dest_file = dest_path / rel.parent / new_filename
        else:
            dest_file = dest_path / rel

        try:
            content = read_file_text(src_file)
        except OSError as exc:
            sys.stderr.write(f"WARNING: Could not read '{src_file}': {exc}\n")
            continue

        if content is None:
            sys.stderr.write(f"WARNING: Could not read '{src_file}': file disappeared\n")
            continue

        transformed = apply_replacements(content, replacements, direction)

        if not dest_needs_update(transformed, dest_file):
            continue

        if not dry_run:
            try:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                with open(str(dest_file), "w", encoding="utf-8") as fh:
                    fh.write(transformed)
            except OSError as exc:
                sys.stderr.write(f"ERROR: Could not write '{dest_file}': {exc}\n")
                continue

        dest_rel = rel.parent / new_filename if new_filename is not None else rel
        changed_files.append(str(dest_rel))

    if copy_other:
        other_files = collect_other_files(source_path, allowed_extensions, ignore_patterns, match_globs)
        for src_file in other_files:
            rel = src_file.relative_to(source_path)
            dest_file = dest_path / rel

            if not dest_needs_update_bytes(src_file, dest_file):
                continue

            if not dry_run:
                try:
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src_file), str(dest_file))
                except OSError as exc:
                    sys.stderr.write(f"ERROR: Could not copy '{dest_file}': {exc}\n")
                    continue

            changed_files.append(str(rel))

    return changed_files
