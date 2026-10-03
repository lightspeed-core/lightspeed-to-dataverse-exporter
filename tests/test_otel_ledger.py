"""Behavioral tests for the OTEL acknowledgment ledger."""

import json
import os
import stat
from pathlib import Path

import pytest

import src.otel_ledger as ledger_module
from src.otel_ledger import LedgerError, OtelLedger

_CURRENT_NAME = "traces-2026-10-03T03-04-05.006-size.jsonl"
_LEGACY_NAME = "agentic-2026-10-03T03-04-05.006.jsonl"


def _entry(request_id: str = "request-1") -> dict[str, str]:
    return {"request_id": request_id}


def _document(files: object, version: object = 1) -> str:
    return json.dumps({"version": version, "files": files})


def _read_ledger(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_missing_ledger_is_atomically_initialized_as_empty_v1(tmp_path):
    path = tmp_path / "ledger.json"

    ledger = OtelLedger(path)

    assert _read_ledger(path) == {"version": 1, "files": {}}
    assert not ledger.is_uploaded(_CURRENT_NAME)
    assert {entry.name for entry in tmp_path.iterdir()} == {path.name}


def test_ledger_accepts_current_and_legacy_rotations_with_any_stem(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(
        _document(
            {
                _CURRENT_NAME: _entry(),
                _LEGACY_NAME: _entry("legacy-request"),
            }
        ),
        encoding="utf-8",
    )

    ledger = OtelLedger(path)

    assert ledger.is_uploaded(_CURRENT_NAME)
    assert ledger.is_uploaded(_LEGACY_NAME)


def test_filename_identity_survives_restart_and_records_request_id(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = OtelLedger(path)

    ledger.mark_uploaded(_CURRENT_NAME, "accepted-1")
    assert ledger.is_uploaded(_CURRENT_NAME)
    assert not ledger.is_uploaded(_LEGACY_NAME)
    assert _read_ledger(path)["files"] == {_CURRENT_NAME: {"request_id": "accepted-1"}}

    restarted = OtelLedger(path)
    assert restarted.is_uploaded(_CURRENT_NAME)
    assert not restarted.is_uploaded(_LEGACY_NAME)


def test_prune_persists_only_actual_removals(tmp_path):
    path = tmp_path / "ledger.json"
    ledger = OtelLedger(path)
    ledger.mark_uploaded(_CURRENT_NAME, "accepted-1")
    ledger.mark_uploaded(_LEGACY_NAME, "accepted-2")

    ledger.prune({_CURRENT_NAME, _LEGACY_NAME})
    unchanged_inode = path.stat().st_ino
    ledger.prune({_CURRENT_NAME, _LEGACY_NAME})

    assert path.stat().st_ino == unchanged_inode
    assert ledger.is_uploaded(_CURRENT_NAME)
    assert ledger.is_uploaded(_LEGACY_NAME)

    ledger.prune({_CURRENT_NAME})
    assert ledger.is_uploaded(_CURRENT_NAME)
    assert not ledger.is_uploaded(_LEGACY_NAME)
    assert set(_read_ledger(path)["files"]) == {_CURRENT_NAME}

    ledger.prune(set())
    assert not ledger.is_uploaded(_CURRENT_NAME)
    assert _read_ledger(path) == {"version": 1, "files": {}}


@pytest.mark.parametrize(
    "document",
    [
        "{",
        '{"version":1,"version":1,"files":{}}',
        '{"version":NaN,"files":{}}',
        _document({}, version=True),
        _document({}, version=2),
        json.dumps({"version": 1, "files": {}, "extra": 1}),
        _document([]),
    ],
)
def test_invalid_document_fails_without_resetting_existing_bytes(tmp_path, document):
    path = tmp_path / "ledger.json"
    original = document.encode("utf-8")
    path.write_bytes(original)

    with pytest.raises(LedgerError):
        OtelLedger(path)

    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "files",
    [
        [],
        {"traces.jsonl": _entry()},
        {"-2026-10-03T03-04-05.006-size.jsonl": _entry()},
        {"../" + _CURRENT_NAME: _entry()},
        {"/" + _CURRENT_NAME: _entry()},
        {"nested\\" + _CURRENT_NAME: _entry()},
        {"traces-2026-10-03T03-04-05.jsonl": _entry()},
        {"traces-2026-10-03T03-04-05.006-other.jsonl": _entry()},
        {_CURRENT_NAME: {"sha256": "a" * 64, "request_id": "request-1"}},
        {_CURRENT_NAME: {"request_id": ""}},
        {_CURRENT_NAME: {"request_id": 7}},
        {_CURRENT_NAME: {}},
        {_CURRENT_NAME: {"request_id": "request-1", "extra": "not-version-1"}},
    ],
)
def test_invalid_entries_and_rotation_keys_are_fatal(tmp_path, files):
    path = tmp_path / "ledger.json"
    original = _document(files).encode("utf-8")
    path.write_bytes(original)

    with pytest.raises(LedgerError):
        OtelLedger(path)

    assert path.read_bytes() == original


def test_unreadable_existing_ledger_raises_ledger_error_without_reset(
    tmp_path, monkeypatch
):
    path = tmp_path / "ledger.json"
    original = _document({_CURRENT_NAME: _entry()}).encode("utf-8")
    path.write_bytes(original)
    original_open = Path.open

    def unreadable_open(candidate, *args, **kwargs):
        if candidate == path:
            raise PermissionError("ledger read denied")
        return original_open(candidate, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "open", unreadable_open)
        with pytest.raises(LedgerError) as raised:
            OtelLedger(path)

    assert not isinstance(raised.value, OSError)
    assert path.read_bytes() == original


def test_failed_replace_keeps_disk_and_memory_state_and_cleans_temp(
    tmp_path, monkeypatch
):
    path = tmp_path / "ledger.json"
    ledger = OtelLedger(path)
    ledger.mark_uploaded(_CURRENT_NAME, "accepted-1")
    original = path.read_bytes()

    def fail_replace(source, destination):
        raise OSError("atomic replace failed")

    with monkeypatch.context() as scoped:
        scoped.setattr(ledger_module.os, "replace", fail_replace)
        with pytest.raises(LedgerError) as raised:
            ledger.mark_uploaded(_CURRENT_NAME, "accepted-2")

    assert not isinstance(raised.value, OSError)
    assert path.read_bytes() == original
    assert ledger._files == {_CURRENT_NAME: {"request_id": "accepted-1"}}
    assert {entry.name for entry in tmp_path.iterdir()} == {path.name}
    assert OtelLedger(path)._files == {_CURRENT_NAME: {"request_id": "accepted-1"}}


def test_file_fsync_failure_keeps_state_and_cleans_temp(tmp_path, monkeypatch):
    path = tmp_path / "ledger.json"
    ledger = OtelLedger(path)
    ledger.mark_uploaded(_CURRENT_NAME, "accepted-1")
    original = path.read_bytes()
    original_fsync = os.fsync

    def fail_file_fsync(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("temporary file fsync failed")
        return original_fsync(fd)

    with monkeypatch.context() as scoped:
        scoped.setattr(ledger_module.os, "fsync", fail_file_fsync)
        with pytest.raises(LedgerError) as raised:
            ledger.mark_uploaded(_CURRENT_NAME, "accepted-2")

    assert not isinstance(raised.value, OSError)
    assert path.read_bytes() == original
    assert ledger._files == {_CURRENT_NAME: {"request_id": "accepted-1"}}
    assert {entry.name for entry in tmp_path.iterdir()} == {path.name}
    assert OtelLedger(path)._files == {_CURRENT_NAME: {"request_id": "accepted-1"}}


def test_directory_fsync_failure_does_not_update_in_memory_state(tmp_path, monkeypatch):
    path = tmp_path / "ledger.json"
    ledger = OtelLedger(path)
    ledger.mark_uploaded(_CURRENT_NAME, "accepted-1")
    original_fsync = os.fsync

    def fail_directory_fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("directory fsync failed")
        return original_fsync(fd)

    with monkeypatch.context() as scoped:
        scoped.setattr(ledger_module.os, "fsync", fail_directory_fsync)
        with pytest.raises(LedgerError) as raised:
            ledger.mark_uploaded(_CURRENT_NAME, "accepted-2")

    assert not isinstance(raised.value, OSError)
    assert ledger._files == {_CURRENT_NAME: {"request_id": "accepted-1"}}
    assert OtelLedger(path)._files == {_CURRENT_NAME: {"request_id": "accepted-2"}}


def test_load_and_startup_save_io_errors_are_ledger_errors(tmp_path, monkeypatch):
    path = tmp_path / "ledger.json"
    path.write_text("{}", encoding="utf-8")
    original_open = Path.open

    def unreadable_open(candidate, *args, **kwargs):
        if candidate == path:
            raise OSError("read failed")
        return original_open(candidate, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "open", unreadable_open)
        with pytest.raises(LedgerError) as raised:
            OtelLedger(path)
    assert not isinstance(raised.value, OSError)
    assert path.read_text(encoding="utf-8") == "{}"

    missing_path = tmp_path / "new-ledger.json"

    def fail_tempfile(*args, **kwargs):
        raise PermissionError("state directory is read-only")

    with monkeypatch.context() as scoped:
        scoped.setattr(ledger_module.tempfile, "mkstemp", fail_tempfile)
        with pytest.raises(LedgerError) as raised:
            OtelLedger(missing_path)
    assert not isinstance(raised.value, OSError)
    assert not missing_path.exists()
