"""Unit tests for Trailytics TOML parser and serializer."""

from __future__ import annotations

import pytest

from trailytics.exceptions import ProfileStorageError
from trailytics.profiles.toml import (
    dumps_toml,
    escape_toml_string,
    format_toml_key,
    format_toml_value,
    load_toml_file,
    loads_toml,
)


def test_escape_toml_string():
    """Verify string escaping handles backslashes, quotes, and whitespace."""
    assert escape_toml_string('hello "world"') == r'"hello \"world\""'
    assert escape_toml_string("line1\nline2") == r'"line1\nline2"'
    assert escape_toml_string(r"C:\path\to\file") == r'"C:\\path\\to\\file"'
    assert escape_toml_string("\t tab") == r'"\t tab"'


def test_format_toml_key():
    """Verify bare keys vs quoted keys."""
    assert format_toml_key("profile_name") == "profile_name"
    assert format_toml_key("my-profile-1") == "my-profile-1"
    assert format_toml_key("key with spaces") == '"key with spaces"'


def test_format_toml_value():
    """Verify scalar formatting."""
    assert format_toml_value(True) == "true"
    assert format_toml_value(False) == "false"
    assert format_toml_value(123) == "123"
    assert format_toml_value(12.34) == "12.34"
    assert format_toml_value("hello") == '"hello"'
    assert format_toml_value(None) == '""'
    with pytest.raises(ValueError, match="Unsupported TOML value type"):
        format_toml_value([1, 2, 3])


def test_dumps_toml_and_loads_toml_roundtrip():
    """Verify complete round-trip serialization and deserialization."""
    original = {
        "default_profile": "local",
        "profiles": {
            "local": {
                "type": "local",
                "url": "http://localhost:5173/api",
                "workspace": "default",
                "default_project": "Default Project",
                "description": "Local Trailytics deployment",
            },
            "production": {
                "type": "remote",
                "url": "https://trailytics.company.com/api",
                "workspace": "production-ai",
                "default_project": "Customer Support",
                "description": 'Cluster with "special" chars\nand newlines',
            },
        },
    }

    serialized = dumps_toml(original)
    assert 'default_profile = "local"' in serialized
    assert "[profiles.local]" in serialized
    assert "[profiles.production]" in serialized

    loaded = loads_toml(serialized)
    assert loaded["default_profile"] == original["default_profile"]
    assert loaded["profiles"]["local"] == original["profiles"]["local"]
    assert loaded["profiles"]["production"] == original["profiles"]["production"]


def test_loads_toml_malformed():
    """Verify malformed TOML raises ProfileStorageError with informative error."""
    malformed = "default_profile = [unclosed bracket"
    with pytest.raises(ProfileStorageError, match="Malformed TOML content"):
        loads_toml(malformed)


def test_load_toml_file_missing(tmp_path):
    """Verify reading a missing file returns an empty dictionary."""
    non_existent = tmp_path / "does_not_exist.toml"
    assert load_toml_file(non_existent) == {}


def test_load_toml_file_existing(tmp_path):
    """Verify loading from an existing valid file."""
    f = tmp_path / "test.toml"
    f.write_text('default_profile = "prod"\n')
    data = load_toml_file(f)
    assert data == {"default_profile": "prod"}


def test_load_toml_file_malformed(tmp_path):
    """Verify loading from an invalid file raises ProfileStorageError."""
    f = tmp_path / "broken.toml"
    f.write_text("broken = invalid toml === \n")
    with pytest.raises(ProfileStorageError, match="Failed to read TOML file"):
        load_toml_file(f)
