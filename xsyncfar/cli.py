import argparse
import sys

from .sync import (
    apply_replacements_to_filename,
    collect_source_files,
    detect_direction,
    find_config,
    get_allowed_extensions,
    get_match_globs,
    load_config,
    run_sync,
)


def _format_direction(direction):
    """Return a human-readable direction label."""
    return "lab → prod" if direction == "lab_to_prod" else "prod → lab"


def _print_preflight(source_path, dest_path, direction, replacements, file_count, rename_files=False):
    """Print the pre-flight summary to stdout."""
    print("\n" + "=" * 60)
    print("  xsyncfar — pre-flight summary")
    print("=" * 60)
    print(f"  Direction     : {_format_direction(direction)}")
    print(f"  Source        : {source_path}")
    print(f"  Dest          : {dest_path}")
    print(f"  Files         : {file_count} eligible file(s) found")
    print(f"  File renaming : {'enabled' if rename_files else 'disabled'}")
    print()
    if replacements:
        print("  Replacements to apply:")
        for entry in replacements:
            if direction == "lab_to_prod":
                print(f"    '{entry['lab']}'  →  '{entry['prod']}'")
            else:
                print(f"    '{entry['prod']}'  →  '{entry['lab']}'")
        if rename_files:
            print()
            print("  Note: above rules will also be applied to filenames (stem only).")
            print("        Any result that would be an invalid filename is skipped silently.")
    else:
        print("  Replacements : none")
    print("=" * 60 + "\n")


def main():
    """Entry point for the xsyncfar CLI."""
    parser = argparse.ArgumentParser(
        prog="xsyncfar",
        description="One-directional file sync with find-and-replace rules.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )
    parser.add_argument(
        "--include-file-renaming",
        action="store_true",
        default=False,
        help=(
            "Also apply replacement rules to filenames (stem only, extension preserved). "
            "Any replacement that would produce an invalid filename is skipped silently."
        ),
    )
    args = parser.parse_args()

    config_path = find_config()
    if config_path is None:
        sys.exit(f"Error: No .xsyncfar.yml found in the current directory or any parent directory.")

    try:
        syncmap = load_config(config_path)
    except (ValueError, RuntimeError) as exc:
        sys.exit(f"Error loading config: {exc}")

    try:
        source_path, dest_path, direction = detect_direction(syncmap)
    except SystemExit:
        raise

    replacements = syncmap.get("replacements", [])
    rename_files = args.include_file_renaming

    allowed_extensions = get_allowed_extensions(syncmap)
    match_globs = get_match_globs(syncmap)
    source_files = collect_source_files(source_path, allowed_extensions, match_globs=match_globs)

    _print_preflight(source_path, dest_path, direction, replacements, len(source_files), rename_files=rename_files)

    if not source_files:
        print("Nothing to sync — no eligible files found in source directory.")
        return

    try:
        answer = input("Proceed with sync? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)

    if answer != "y":
        print("Aborted.")
        sys.exit(0)

    print()
    changed = run_sync(source_path, dest_path, direction, syncmap, rename_files=rename_files)

    print()
    if changed:
        print(f"Sync complete — {len(changed)} file(s) written:")
        for f in changed:
            print(f"  {f}")
    else:
        print("Sync complete — no files changed.")
