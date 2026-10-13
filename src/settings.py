from pathlib import Path, PureWindowsPath
from typing import Literal

from pydantic import (
    BaseModel,
    NonNegativeInt,
    PositiveInt,
    DirectoryPath,
    ConfigDict,
    ValidationInfo,
    field_validator,
    model_validator,
)


def _normalize_archive_path_prefix(prefix: str) -> str:
    if not prefix:
        raise ValueError("archive_path_prefix must be nonempty in OTEL mode")
    if (
        prefix.startswith("/")
        or "\\" in prefix
        or "\x00" in prefix
        or PureWindowsPath(prefix).drive
    ):
        raise ValueError("archive_path_prefix must be a relative forward-slash path")

    components = prefix.rstrip("/").split("/")
    if any(component in ("", ".", "..") for component in components):
        raise ValueError(
            "archive_path_prefix must not contain empty, dot, or parent components"
        )

    return "/".join(components) + "/"


class DataCollectorSettings(BaseModel):
    """Data collector settings loaded from YAML configuration files.

    Settings are immutable per runtime and loaded from explicit configuration.
    """

    model_config = ConfigDict(frozen=True)

    # Required settings
    data_dir: DirectoryPath
    service_id: str
    ingress_server_url: str
    ingress_server_auth_token: str

    # Optional settings with defaults
    identity_id: str
    collection_interval: NonNegativeInt
    cleanup_after_send: bool
    ingress_connection_timeout: PositiveInt
    retry_interval: PositiveInt
    allowed_subdirs: list[str]

    # Optional OTEL ingestion settings
    data_mode: Literal["json", "otel"] = "json"
    ledger_file: Path | None = None
    otel_active_file: str = "traces.jsonl"
    archive_path_prefix: str = ""

    @field_validator("archive_path_prefix")
    @classmethod
    def normalize_otel_archive_path_prefix(
        cls, prefix: str, info: ValidationInfo
    ) -> str:
        if info.data.get("data_mode") != "otel" or not prefix:
            return prefix
        return _normalize_archive_path_prefix(prefix)

    @model_validator(mode="after")
    def validate_otel_configuration(self) -> "DataCollectorSettings":
        if self.data_mode != "otel":
            return self

        if self.ledger_file is None:
            raise ValueError("ledger_file is required when data_mode is 'otel'")

        active_file = self.otel_active_file
        active_stem = active_file.removesuffix(".jsonl")
        if (
            not active_stem
            or active_stem in {".", ".."}
            or "/" in active_file
            or "\\" in active_file
            or "\x00" in active_file
            or Path(active_file).name != active_file
            or PureWindowsPath(active_file).name != active_file
            or not active_file.endswith(".jsonl")
        ):
            raise ValueError(
                "otel_active_file must be a plain .jsonl basename without traversal"
            )

        ledger_path = self.ledger_file
        if ledger_path.is_symlink():
            raise ValueError("ledger_file must not be a symlink")
        if ledger_path.exists() and not ledger_path.is_file():
            raise ValueError("ledger_file must be a regular file")
        if not ledger_path.parent.is_dir():
            raise ValueError("ledger_file parent must be an existing directory")

        try:
            source_root = self.data_dir.resolve(strict=True)
            ledger_parent = ledger_path.parent.resolve(strict=True)
            resolved_ledger = ledger_path.resolve()
        except (OSError, RuntimeError) as exc:
            raise ValueError(
                "data_dir and ledger_file parent must be resolvable directories"
            ) from exc

        if not ledger_parent.is_dir():
            raise ValueError("ledger_file parent must be an existing directory")
        if ledger_parent.is_relative_to(source_root) or resolved_ledger.is_relative_to(
            source_root
        ):
            raise ValueError("ledger_file must be outside the data_dir source tree")

        if not self.archive_path_prefix:
            raise ValueError("archive_path_prefix must be nonempty in OTEL mode")
        return self
