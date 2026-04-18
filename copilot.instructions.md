## Instructions for the xsyncfar Package
When working on this project, please follow these guidelines/rules
- Do not use exact examples in the documentation based on configuration files I share with you. Instead, use the same structure but change names and values to make it more sanitised.
- Do not reference bifrost, heimdall or vodafone anywhere in the code, configuration or documentation.

## Purpose

`xsyncfar` is a one-directional file sync tool that copies files from a source directory to a destination directory, applying case-insensitive literal find-and-replace rules to file content in the process. The direction of sync is determined by the current working directory at runtime.

## Config File (`.xsyncfar.yml`)

- The tool walks up the directory tree from the current working directory to find `.xsyncfar.yml`, stopping at the first one found (git-style discovery).
- The config has a top-level `syncmap` key containing:
  - `prefix` (string): A path prefix prepended to all `lab` and `prod` paths in `mappings`. Must be treated as a raw string (not regex). Should support both Windows (`\`) and POSIX (`/`) path separators.
  - `replacements` (list): Each entry has a `lab` and `prod` key. These are **plain string literals** (not regex). Matching is **case-insensitive**. The casing pattern of each matched occurrence is mirrored onto the replacement string (see below). When syncing lab→prod, occurrences of the `lab` string in file content are replaced with the `prod` string. When syncing prod→lab, the reverse applies.
  - `mappings` (list): Each entry has a `lab` and `prod` key representing relative directory paths (combined with `prefix` to form absolute paths).
  - `extensions` (optional list of strings, e.g. `[".py", ".yml"]`): If present, overrides the default list of syncable file extensions.

## Direction Detection

- The tool compares the current working directory against all `lab` and `prod` absolute paths (prefix + mapping path) across all mappings.
- If the CWD matches (or is under) a `lab` path, the sync direction is **lab → prod**.
- If the CWD matches (or is under) a `prod` path, the sync direction is **prod → lab**.
- If no match is found, the tool should exit with a clear error message.
- Path comparison must be case-insensitive on Windows and case-sensitive on Linux/macOS. Use `pathlib.Path` for all path operations to ensure cross-platform compatibility.

## File Selection

- By default, only files with the following extensions are synced: `.py`, `.yml`, `.yaml`, `.json`, `.txt`, `.md`
- If `extensions` is set in `.xsyncfar.yml`, this list replaces the default entirely.
- If `copy_other_files: true` is set in the syncmap, files whose extension is **not** in the allowed list are copied as-is (binary copy via `shutil.copy2`, no find/replace applied). This allows binaries, images, scripts and other non-text files to be included in the sync.
- If `copy_other_files` is absent or `false`, non-matching files are silently skipped.
- All subdirectories under the matched source path are processed recursively.

## Sync Behaviour

1. **Pre-flight summary**: Before doing anything, display the resolved source and destination paths, the sync direction, the replacements that will be applied, and a count of files that will be evaluated. Prompt the user to confirm (`y/n`) before proceeding. Abort cleanly if they decline.
2. **For each eligible file**:
   - Read the file content.
   - Apply all find/replace rules (in the configured order) to produce transformed content.
   - Compare the transformed content to the existing destination file (if it exists) using a diff. If they are identical, skip the file.
   - If different (or destination does not exist), write the transformed content to the destination, preserving relative path structure.
   - If the destination file's parent directory does not exist, create it (and any missing intermediate directories) before writing.
3. **Always overwrite** — no prompting per file.
4. The destination root directory itself is also created if it does not exist.
5. **Post-run summary**: Print a list of all files that were written/changed. If no files changed, say so explicitly.

## Case Mirroring

When a match is found, the casing pattern of the matched text is detected and applied to the replacement string:

| Matched text | Replacement output |
|---|---|
| `myapp` (all lower) | `targetapp` |
| `MYAPP` (all upper) | `TARGETAPP` |
| `Myapp` (title: first upper, rest lower) | `Targetapp` |
| `mYaPp` (mixed/irregular) | `targetapp` (replacement as written in config) |

This is implemented using `re.escape()` on the find string and `re.IGNORECASE`, with a lambda replacement that calls `_match_case(matched, replacement)`.

## Error Handling

- If a source file cannot be read (e.g. permission error), log a warning and continue with remaining files.
- If a destination file cannot be written, log an error and continue.

## Compatibility

- Must support Python 3.6 and above.
- Must work on both Windows and Linux/macOS.
- Use only the Python standard library where possible. `PyYAML` is acceptable for config parsing.
- Do not use `capture_output=True` in `subprocess.run` (added in 3.7) — use `stdout=subprocess.PIPE, stderr=subprocess.PIPE` instead.
- Do not use `text=True` in `subprocess.run` — use `universal_newlines=True` instead.
- Use `pathlib.Path` for all path handling.
- Use `re` module for all pattern matching and replacement.
- Package should be compatible with Python 3.6 and above, and run both on Windows and Unix-based systems.
- For the CLI, use the `argparse` library to handle command-line arguments and options.
- For testing, use the `unittest` framework to create test cases for the CLI and other functionalities of the package.
- Ensure that the package is structured properly with an `__init__.py` file and that all modules are organized in a logical manner.
- Include a `README.md` file that provides an overview of the package, its features, and instructions on how to install and use it.
- Use a `.gitignore` file to exclude unnecessary files and directories from being tracked by Git, such as `__pycache__/`, `.DS_Store`, and any virtual environment directories.


## Package Overview
This package is designed to facilitate one-directional synchronization across pre-mapped directory paths with find and replace rules. It provides a command-line interface (CLI) for users to easily perform synchronization tasks. The package is compatible with Python 3.6 and above, and can be used on both Windows and Unix-based systems.
Its driving use case is to allow users to synchronize files between different environments and platforms, such as between a local development environment and a remote server, while applying specific find and replace rules to the file contents during the synchronization process. This can be particularly useful for developers who need to maintain consistency across different environments or for those who want to automate the synchronization of files with specific transformations applied.

## Functional Requirements
1. Upon execution, the CLI, the tool will look for a configuration file called .xsyncfar.yml in the current working directory. If the file is not found, it will check the parent directory, and so on, until it reaches the root directory. If the configuration file is not found in any of these directories, the tool will exit with an error message indicating that the configuration file is missing.
2. The configuration file will contain mappings of source and destination directory paths, as well as find and replace rules for file contents. The tool will read this configuration and use it to perform the synchronization tasks.
3. The find and replace rules contain a list of patterns to find in the file contents and their corresponding replacement values. The tool will apply these rules to the files being synchronized, ensuring that the specified transformations are applied during the synchronization process.
