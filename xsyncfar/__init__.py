"""xsyncfar — one-directional file sync with find-and-replace rules."""

from .sync import (
    apply_replacements,
    collect_source_files,
    detect_direction,
    find_config,
    get_allowed_extensions,
    load_config,
    run_sync,
)

__all__ = [
    "find_config",
    "load_config",
    "detect_direction",
    "apply_replacements",
    "collect_source_files",
    "get_allowed_extensions",
    "run_sync",
]
