"""TOML reading and serialization for Trailytics profiles and credentials."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict

from trailytics.exceptions import ProfileStorageError

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "The 'tomli' package is required for Python < 3.11. "
            "Install it with 'pip install tomli'."
        ) from e

_BARE_KEY_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def escape_toml_string(val: str) -> str:
    """Escape and quote a string for TOML serialization."""
    escaped = (
        val.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def format_toml_key(key: str) -> str:
    """Format a TOML key, quoting if it contains special characters."""
    if _BARE_KEY_RE.match(key):
        return key
    return escape_toml_string(key)


def format_toml_value(val: Any) -> str:
    """Format a Python scalar value into a TOML literal."""
    if isinstance(val, bool):
        return "true" if val else "false"
    elif isinstance(val, (int, float)):
        return str(val)
    elif isinstance(val, str):
        return escape_toml_string(val)
    elif val is None:
        return '""'
    else:
        raise ValueError(f"Unsupported TOML value type: {type(val)}")


def dumps_toml(data: Dict[str, Any]) -> str:
    """Serialize a profile/credentials dictionary to valid TOML.

    Supports top-level scalar values and two-level nested dictionary tables
    (e.g., [profiles.production]).
    """
    lines: list[str] = []

    # First write top-level scalar values
    top_scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
    for k, v in sorted(top_scalars.items()):
        formatted_key = format_toml_key(k)
        formatted_val = format_toml_value(v)
        lines.append(f"{formatted_key} = {formatted_val}")

    if top_scalars:
        lines.append("")

    # Then write nested tables
    nested_tables = {k: v for k, v in data.items() if isinstance(v, dict)}
    for section_name, table in sorted(nested_tables.items()):
        # Handle two-level tables like profiles.name
        for sub_name, sub_table in sorted(table.items()):
            if isinstance(sub_table, dict):
                header = f"[{format_toml_key(section_name)}.{format_toml_key(sub_name)}]"
                lines.append(header)
                for k, v in sorted(sub_table.items()):
                    if not isinstance(v, dict):
                        lines.append(f"{format_toml_key(k)} = {format_toml_value(v)}")
                lines.append("")
            else:
                # 1-level table
                header = f"[{format_toml_key(section_name)}]"
                lines.append(header)
                lines.append(f"{format_toml_key(sub_name)} = {format_toml_value(sub_table)}")
                lines.append("")

    return "\n".join(lines).strip() + "\n"


def loads_toml(content: str) -> Dict[str, Any]:
    """Parse a TOML string into a dictionary."""
    try:
        return tomllib.loads(content)
    except Exception as e:
        raise ProfileStorageError(f"Malformed TOML content: {e}") from e


def load_toml_file(path: Path) -> Dict[str, Any]:
    """Load a TOML file from disk if it exists, otherwise return an empty dict."""
    if not path.is_file():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception as e:
        raise ProfileStorageError(f"Failed to read TOML file at {path}: {e}") from e
