"""Durable acknowledgments for successfully uploaded OTEL rotation files."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path, PureWindowsPath
from typing import Any


class LedgerError(RuntimeError):
    """The OTEL acknowledgment ledger could not be safely read or updated."""


_ROTATED_BASENAME_RE = re.compile(
    r"(?P<stem>[^/\\\x00]+)-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.\d{3}"
    r"(?:-size)?\.jsonl"
)
_ROOT_KEYS = {"version", "files"}
_ENTRY_KEYS = {"request_id"}

_LedgerEntry = dict[str, str]
_LedgerFiles = dict[str, _LedgerEntry]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _validate_rotation_basename(filename: object) -> str:
    if not isinstance(filename, str) or not filename:
        raise LedgerError("ledger filename must be a nonempty string")
    if (
        filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
        or Path(filename).is_absolute()
        or PureWindowsPath(filename).is_absolute()
        or Path(filename).name != filename
    ):
        raise LedgerError(f"ledger key is not a plain basename: {filename!r}")

    match = _ROTATED_BASENAME_RE.fullmatch(filename)
    if match is None or match.group("stem") in {".", ".."}:
        raise LedgerError(f"ledger key is not a rotated JSONL basename: {filename!r}")
    return filename


def _validate_request_id(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise LedgerError("ledger request_id must be a nonempty string")
    return value


def _validate_files(value: object) -> _LedgerFiles:
    if type(value) is not dict:
        raise LedgerError("ledger files must be an object")

    files: _LedgerFiles = {}
    for filename, entry in value.items():
        filename = _validate_rotation_basename(filename)
        if type(entry) is not dict or set(entry) != _ENTRY_KEYS:
            raise LedgerError(
                f"ledger entry for {filename!r} must contain only request_id"
            )
        files[filename] = {"request_id": _validate_request_id(entry["request_id"])}
    return files


def _decode_document(document: object) -> _LedgerFiles:
    if type(document) is not dict or set(document) != _ROOT_KEYS:
        raise LedgerError("ledger must contain only version and files")

    version = document["version"]
    if type(version) is not int or version != 1:
        raise LedgerError(f"unsupported OTEL ledger version: {version!r}")

    return _validate_files(document["files"])


class OtelLedger:
    """Persist acknowledged rotated filenames as versioned JSON."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        files = self._load()
        if files is None:
            files = {}
            self._persist(files)
        self._files = files

    def is_uploaded(self, relative_path: str) -> bool:
        """Return whether this rotated basename has been acknowledged."""
        return relative_path in self._files

    def prune(self, present_paths: set[str]) -> None:
        """Remove acknowledged names absent from a complete source inventory."""
        retained = {
            filename: entry
            for filename, entry in self._files.items()
            if filename in present_paths
        }
        if len(retained) == len(self._files):
            return

        self._persist(retained)
        self._files = retained

    def mark_uploaded(self, relative_path: str, request_id: str) -> None:
        """Record a successful upload for this rotated basename."""
        filename = _validate_rotation_basename(relative_path)
        request = _validate_request_id(request_id)

        updated = self._files.copy()
        updated[filename] = {"request_id": request}
        self._persist(updated)
        self._files = updated

    def _load(self) -> _LedgerFiles | None:
        try:
            stream = self.path.open("r", encoding="utf-8")
        except FileNotFoundError as error:
            try:
                self.path.lstat()
            except FileNotFoundError:
                return None
            except OSError as stat_error:
                raise LedgerError(
                    f"Unable to inspect OTEL ledger {self.path}: {stat_error}"
                ) from stat_error
            raise LedgerError(
                f"OTEL ledger path exists but could not be opened: {self.path}"
            ) from error
        except Exception as error:
            raise LedgerError(
                f"Unable to open OTEL ledger {self.path}: {error}"
            ) from error

        try:
            with stream:
                document = json.load(
                    stream,
                    object_pairs_hook=_reject_duplicate_keys,
                    parse_constant=_reject_json_constant,
                )
        except Exception as error:
            raise LedgerError(
                f"Unable to read OTEL ledger {self.path}: {error}"
            ) from error

        try:
            return _decode_document(document)
        except LedgerError as error:
            raise LedgerError(f"Invalid OTEL ledger {self.path}: {error}") from error
        except Exception as error:
            raise LedgerError(f"Invalid OTEL ledger {self.path}: {error}") from error

    def _persist(self, files: _LedgerFiles) -> None:
        validated_files = _validate_files(files)
        document = {"version": 1, "files": validated_files}
        temporary_path: Path | None = None
        temporary_fd: int | None = None

        try:
            temporary_fd, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.name or 'otel-ledger'}.",
                suffix=".tmp",
                dir=self.path.parent,
            )
            temporary_path = Path(temporary_name)

            stream = os.fdopen(temporary_fd, "w", encoding="utf-8")
            temporary_fd = None
            with stream:
                json.dump(document, stream, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())

            os.replace(temporary_path, self.path)
            temporary_path = None

            directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            directory_fd = os.open(self.path.parent, directory_flags)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception as error:
            cleanup_error = self._cleanup_temporary(temporary_fd, temporary_path)
            message = f"Unable to persist OTEL ledger {self.path}: {error}"
            if cleanup_error is not None:
                message += f"; temporary cleanup failed: {cleanup_error}"
            raise LedgerError(message) from error

    @staticmethod
    def _cleanup_temporary(fd: int | None, path: Path | None) -> Exception | None:
        cleanup_error: Exception | None = None
        if fd is not None:
            try:
                os.close(fd)
            except Exception as error:
                cleanup_error = error

        if path is not None:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            except Exception as error:
                if cleanup_error is None:
                    cleanup_error = error
        return cleanup_error
