"""Inventory and package rotated OTEL JSONL source files."""

import io
import json
import os
import re
import stat
import tarfile
from pathlib import Path
from typing import BinaryIO, NoReturn

from src.constants import MAX_PAYLOAD_SIZE


class OtelSourceError(ValueError):
    """A rotated OTEL source is invalid or exceeds an export size limit."""


def collect_rotated_files(data_dir: Path, active_file: str) -> list[Path]:
    """Return complete, direct-child inventory of regular rotated JSONL files."""
    active_path = Path(active_file)
    if (
        not active_file
        or active_path.name != active_file
        or "\\" in active_file
        or "\x00" in active_file
        or active_path.suffix != ".jsonl"
        or active_path.stem in {"", ".", ".."}
    ):
        raise OtelSourceError(
            f"active OTEL file must be a plain .jsonl basename: {active_file!r}"
        )

    backup_name = re.compile(
        rf"\A{re.escape(active_path.stem)}-\d{{4}}-\d{{2}}-\d{{2}}T"
        rf"\d{{2}}-\d{{2}}-\d{{2}}\.\d{{3}}(?:-size)?"
        rf"{re.escape(active_path.suffix)}\Z",
        re.ASCII,
    )

    rotated_files: list[Path] = []
    with os.scandir(data_dir) as entries:
        for entry in entries:
            name = entry.name
            if name == active_file or backup_name.fullmatch(name) is None:
                continue

            metadata = entry.stat(follow_symlinks=False)
            if stat.S_ISREG(metadata.st_mode):
                rotated_files.append(data_dir / name)

    return sorted(rotated_files, key=lambda path: path.name)


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"nonstandard JSON constant {value}")


def _validate_object(record: bytes, member_name: str, line_number: int) -> None:
    try:
        text = record.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OtelSourceError(
            f"{member_name}: line {line_number} is not valid UTF-8"
        ) from exc

    try:
        value = json.loads(text, parse_constant=_reject_json_constant)
    except (ValueError, RecursionError) as exc:
        raise OtelSourceError(
            f"{member_name}: line {line_number} is not a valid JSON object"
        ) from exc

    if not isinstance(value, dict):
        raise OtelSourceError(
            f"{member_name}: line {line_number} contains JSON that is not an object"
        )


def package_jsonl_file(
    source: BinaryIO,
    member_name: str,
    max_payload_size: int = MAX_PAYLOAD_SIZE,
) -> io.BytesIO:
    """Convert JSONL records to one object array and return its gzip TAR archive."""
    array_buffer = io.BytesIO()
    tar_buffer = io.BytesIO()

    try:
        if max_payload_size < 0:
            raise OtelSourceError(
                f"{member_name}: payload size limit must not be negative"
            )

        array_buffer.write(b"[")
        first_record = True
        for line_number, line in enumerate(source, start=1):
            record = line.strip(b" \t\r\n")
            if not record:
                continue

            separator_size = 0 if first_record else 1
            member_size = array_buffer.tell() + separator_size + len(record) + 1
            if member_size > max_payload_size:
                raise OtelSourceError(
                    f"{member_name}: converted JSON array exceeds "
                    f"{max_payload_size} bytes"
                )

            _validate_object(record, member_name, line_number)

            if not first_record:
                array_buffer.write(b",")
            array_buffer.write(record)
            first_record = False

        if array_buffer.tell() + 1 > max_payload_size:
            raise OtelSourceError(
                f"{member_name}: converted JSON array exceeds "
                f"{max_payload_size} bytes"
            )
        array_buffer.write(b"]")
        member_size = array_buffer.tell()
        array_buffer.seek(0)

        with tarfile.open(fileobj=tar_buffer, mode="w:gz") as archive:
            tar_info = tarfile.TarInfo(member_name)
            tar_info.size = member_size
            archive.addfile(tar_info, array_buffer)

        tar_size = tar_buffer.seek(0, io.SEEK_END)
        if tar_size > max_payload_size:
            raise OtelSourceError(
                f"{member_name}: gzip TAR exceeds {max_payload_size} bytes"
            )

        tar_buffer.seek(0)
        array_buffer.close()
        return tar_buffer
    except BaseException:
        array_buffer.close()
        tar_buffer.close()
        raise
