"""Behavior tests for rotated OTEL source inventory and packaging."""

import io
import json
import stat
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.otel_file_handler import (
    OtelSourceError,
    collect_rotated_files,
    package_jsonl_file,
)


def _read_single_member(archive_buffer: io.BytesIO) -> tuple[str, int, bytes]:
    archive_buffer.seek(0)
    with tarfile.open(fileobj=archive_buffer, mode="r:gz") as archive:
        members = archive.getmembers()
        assert len(members) == 1
        member = members[0]
        extracted = archive.extractfile(member)
        assert extracted is not None
        with extracted:
            return member.name, member.size, extracted.read()


def test_collect_rotated_files_selects_only_direct_regular_backups(
    tmp_path: Path,
) -> None:
    active_file = tmp_path / "traces.jsonl"
    active_file.write_bytes(b'{"live":true}')

    current_name = "traces-2026-10-03T03-04-05.006-size.jsonl"
    legacy_name = "traces-2026-10-03T03-04-04.005.jsonl"
    (tmp_path / current_name).write_bytes(b'{"current":true}')
    (tmp_path / legacy_name).write_bytes(b'{"legacy":true}')

    noise_names = (
        "traces-2026-10-03T03-04-06.007-123.jsonl",
        "traces-2026-10-03T03-04-07.008-other.jsonl",
        "traces-2026-10-03T03-04-08.009-size.jsonl.tmp",
        "traces-2026-10-03T03-04-09.010-size.jsonl.gz",
        "other-2026-10-03T03-04-10.011-size.jsonl",
        "traces-2026-10-3T03-04-11.012-size.jsonl",
        "traces-2026-10-03T03-04-12.013-size.jsonl\n",
        "traces-２０２６-10-03T03-04-14.015-size.jsonl",
    )
    for name in noise_names:
        (tmp_path / name).write_bytes(b'{"noise":true}')

    symlink_name = "traces-2026-10-03T03-04-13.014-size.jsonl"
    (tmp_path / symlink_name).symlink_to(tmp_path / current_name)

    directory_name = "traces-2026-10-03T03-04-15.016-size.jsonl"
    (tmp_path / directory_name).mkdir()
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    (nested_dir / "traces-2026-10-03T03-04-16.017-size.jsonl").write_bytes(
        b'{"nested":true}'
    )

    assert collect_rotated_files(tmp_path, "traces.jsonl") == [
        tmp_path / legacy_name,
        tmp_path / current_name,
    ]


def test_collect_rotated_files_propagates_a_missing_root(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        collect_rotated_files(tmp_path / "missing", "traces.jsonl")


def test_collect_rotated_files_rejects_nul_in_active_basename(
    tmp_path: Path,
) -> None:
    with pytest.raises(OtelSourceError):
        collect_rotated_files(tmp_path, "traces\x00.jsonl")


def test_collect_rotated_files_returns_a_successful_empty_inventory(
    tmp_path: Path,
) -> None:
    assert collect_rotated_files(tmp_path, "traces.jsonl") == []


def test_collect_rotated_files_does_not_stat_the_active_file(monkeypatch) -> None:
    class Entry:
        def __init__(self, name: str, mode: int | None = None) -> None:
            self.name = name
            self.mode = mode

        def stat(self, *, follow_symlinks: bool = True):
            assert follow_symlinks is False
            if self.mode is None:
                raise AssertionError("the active file must not be statted")
            return SimpleNamespace(st_mode=self.mode)

    class Scan:
        def __init__(self, entries) -> None:
            self.entries = entries

        def __enter__(self):
            return iter(self.entries)

        def __exit__(self, *_args) -> None:
            return None

    backup_name = "traces-2026-10-03T03-04-05.006-size.jsonl"
    scan = Scan(
        [
            Entry("traces.jsonl"),
            Entry(backup_name, stat.S_IFREG),
        ]
    )
    monkeypatch.setattr("src.otel_file_handler.os.scandir", lambda _path: scan)

    assert collect_rotated_files(Path("/unused"), "traces.jsonl") == [
        Path("/unused") / backup_name
    ]


def test_collect_rotated_files_propagates_stat_failure_after_a_candidate(
    monkeypatch,
) -> None:
    class Entry:
        def __init__(self, name: str, mode: int | None = None) -> None:
            self.name = name
            self.mode = mode

        def stat(self, *, follow_symlinks: bool = True):
            assert follow_symlinks is False
            if self.mode is None:
                raise PermissionError("candidate disappeared during inventory")
            return SimpleNamespace(st_mode=self.mode)

    class Scan:
        def __enter__(self):
            return iter(
                [
                    Entry("traces-2026-10-03T03-04-05.006-size.jsonl", stat.S_IFREG),
                    Entry("traces-2026-10-03T03-04-06.007-size.jsonl"),
                ]
            )

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("src.otel_file_handler.os.scandir", lambda _path: Scan())

    with pytest.raises(PermissionError, match="disappeared during inventory"):
        collect_rotated_files(Path("/unused"), "traces.jsonl")


def test_collect_rotated_files_propagates_iteration_failure_after_a_candidate(
    monkeypatch,
) -> None:
    class Entry:
        name = "traces-2026-10-03T03-04-05.006-size.jsonl"

        def stat(self, *, follow_symlinks: bool = True):
            assert follow_symlinks is False
            return SimpleNamespace(st_mode=stat.S_IFREG)

    class Scan:
        def __enter__(self):
            def entries():
                yield Entry()
                raise OSError("directory iteration failed")

            return entries()

        def __exit__(self, *_args) -> None:
            return None

    monkeypatch.setattr("src.otel_file_handler.os.scandir", lambda _path: Scan())

    with pytest.raises(OSError, match="directory iteration failed"):
        collect_rotated_files(Path("/unused"), "traces.jsonl")


def test_package_jsonl_file_preserves_deep_otel_objects_and_record_bytes() -> None:
    first = (
        rb'{ "resourceSpans" : ['
        rb'{"resource":{"attributes":['
        rb'{"key":"service.name","value":{"stringValue":"agent"}},'
        rb'{"key":"large.id","value":{"intValue":"9007199254740993"}}]},'
        rb'"scopeSpans":['
        rb'{"scope":{"name":"scope.one","version":"1.0"},"spans":['
        rb'{"traceId":"0001","spanId":"0002","name":"root","events":['
        rb'{"timeUnixNano":"123","name":"exception","attributes":['
        rb'{"key":"message","value":{"stringValue":"quote: \"; '
        rb'path: C:\\tmp\\trace; newline: \\n"}}]}]}]},'
        rb'{"scope":{"name":"scope.two"},"spans":['
        rb'{"traceId":"0003","spanId":"0004","name":"child","events":[]}]}]},'
        rb'{"resource":{"attributes":['
        rb'{"key":"pod.uid","value":{"stringValue":"pod-1"}}]},'
        rb'"scopeSpans":[{"scope":{"name":"secondary"},"spans":['
        rb'{"name":"other-resource-span","events":[]}]}]}] }'
    )
    second = (
        rb'{"resourceSpans":[{"resource":{"attributes":['
        rb'{"key":"host.name","value":{"stringValue":"node"}}]},'
        rb'"scopeSpans":[{"scope":{"name":"third"},"spans":['
        rb'{"name":"final","events":[{"name":"annotation","attributes":[]}]}]}]}],'
        rb'"status":{"code":0}}'
    )
    source = io.BytesIO(b" \t" + first + b" \r\n\n\t" + second + b"\t")
    expected_array = b"[" + first + b"," + second + b"]"

    with package_jsonl_file(
        source, "v1/traces-2026-10-03T03-04-05.006-size.json"
    ) as archive:
        member_name, member_size, array_bytes = _read_single_member(archive)

    assert member_name == "v1/traces-2026-10-03T03-04-05.006-size.json"
    assert member_size == len(expected_array)
    assert array_bytes == expected_array
    assert json.loads(array_bytes) == [json.loads(first), json.loads(second)]
    assert not source.closed


def test_package_jsonl_file_emits_an_empty_array_for_blank_sources() -> None:
    with package_jsonl_file(io.BytesIO(b" \t\r\n\n\t"), "v1/empty.json") as archive:
        _, member_size, array_bytes = _read_single_member(archive)

    assert array_bytes == b"[]"
    assert member_size == 2


@pytest.mark.parametrize(
    "record",
    [
        b"{",
        b"[]",
        b"null",
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b'{"value":-Infinity}',
        b"\xff",
    ],
)
def test_package_jsonl_file_rejects_invalid_or_non_object_records(
    record: bytes,
) -> None:
    with pytest.raises(OtelSourceError, match="payload.json: line 1"):
        package_jsonl_file(io.BytesIO(record), "payload.json")


def test_package_jsonl_file_enforces_member_and_tar_size_limits() -> None:
    record = b'{"repeat":"' + (b"x" * 4096) + b'"}'
    expected_array = b"[" + record + b"]"
    member_limit = len(expected_array)

    with package_jsonl_file(
        io.BytesIO(record), "repeat.json", max_payload_size=member_limit
    ) as archive:
        _, member_size, array_bytes = _read_single_member(archive)

    assert member_size == member_limit
    assert array_bytes == expected_array

    with pytest.raises(OtelSourceError, match="converted JSON array exceeds"):
        package_jsonl_file(
            io.BytesIO(record), "repeat.json", max_payload_size=member_limit - 1
        )

    with pytest.raises(OtelSourceError, match="gzip TAR exceeds"):
        package_jsonl_file(io.BytesIO(b""), "empty.json", max_payload_size=2)
