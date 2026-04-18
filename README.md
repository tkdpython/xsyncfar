# xsyncfar

Tool for one-directional sync across pre-mapped directory paths with find-and-replace rules applied to file content.

The sync direction is determined automatically by the directory you run the tool from — no flags needed.

---

## Features

- Bidirectional mapping: run from either side of a mapping to sync in that direction
- Case-insensitive literal find-and-replace applied to file content during sync
- Only writes files whose content has actually changed (diff before write)
- Recursively processes all subdirectories
- Pre-flight summary with confirmation prompt before any changes are made
- Automatically creates missing destination directories and files
- Configurable file extension filter (with sensible defaults)
- Git-style config discovery (walks up the directory tree)
- Works on Windows and Linux/macOS
- Python 3.6+, no dependencies beyond PyYAML

---

## Installation

```bash
pip install xsyncfar
```

Or install from source:

```bash
git clone <repo-url>
cd xsyncfar
pip install -e .
```

---

## Configuration

Create a `.xsyncfar.yml` file in your project root (or any parent directory). The tool will walk up the directory tree to find it.

```yaml
syncmap:
  # Path prefix prepended to all lab/prod paths in mappings
  prefix: "/home/user/projects/"

  # Optional: override the default file extensions to sync
  # Defaults: .py .yml .yaml .json .txt .md
  # extensions:
  #   - .yml
  #   - .tf
  #   - .py

  # Optional: copy files with non-matching extensions as-is (binary copy, no replacements)
  # Useful for images, binaries, shell scripts, etc.
  # copy_other_files: true

  # Literal find-and-replace rules applied to file content (case-insensitive)
  replacements:
    - lab: "mylab"       # string to find in source
      prod: "mycompany"  # string to replace with in destination
    - lab: "dev-cluster"
      prod: "prod-cluster"

  # Directory path pairs (relative to prefix)
  mappings:
    - lab: "my-lab-project/helm-charts/my-chart"
      prod: "my-prod-project/helm-charts/my-chart"
    - lab: "my-lab-project/configs"
      prod: "my-prod-project/configs"
```

### How direction is determined

The tool compares your current working directory against all `lab` and `prod` paths in the config:

- If your CWD is **inside a `lab` path** → syncs **lab → prod** (applying `lab` patterns, replacing with `prod` values)
- If your CWD is **inside a `prod` path** → syncs **prod → lab** (reversing all replacements)

---

## Usage

Navigate into any directory that matches a mapping (or a subdirectory of one), then run:

```bash
xsyncfar
# or
python -m xsyncfar
```

The tool will:

1. Find the nearest `.xsyncfar.yml` walking up from your CWD
2. Detect the sync direction from your CWD
3. Show a pre-flight summary of what it will do
4. Ask you to confirm before making any changes
5. Sync all eligible files, applying find/replace rules
6. Report all files that were written

### Example session

```
============================================================
  xsyncfar — pre-flight summary
============================================================
  Direction : lab → prod
  Source    : /home/user/projects/my-lab-project/helm-charts/my-chart
  Dest      : /home/user/projects/my-prod-project/helm-charts/my-chart
  Files     : 8 eligible file(s) found

  Replacements to apply:
    'mylab'       →  'mycompany'
    'dev-cluster' →  'prod-cluster'
============================================================

Proceed with sync? [y/N]: y

Sync complete — 3 file(s) written:
  values.yaml
  templates/deployment.yaml
  templates/configmap.yaml
```

---

## Supported file extensions (default)

`.py`, `.yml`, `.yaml`, `.json`, `.txt`, `.md`

Override by adding an `extensions` list to your `.xsyncfar.yml`.

To also copy files with **other** extensions unchanged (binary copy, no replacements — useful for images, scripts, binaries), set `copy_other_files: true` in your syncmap.

---

## Running tests

```bash
python -m unittest discover -s tests -v
```
