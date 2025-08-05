from pathlib import Path
import yaml
from pydantic import (
    BaseModel,
    NonNegativeInt,
    PositiveInt,
    DirectoryPath,
    ConfigDict,
    Field,
)
from typing import Optional

from src import constants


class DataCollectorSettings(BaseModel):
    """Data collector settings loaded from YAML configuration files.

    Settings are immutable per runtime and loaded from explicit configuration.
    No environment variable overrides to ensure predictable configuration.
    """

    model_config = ConfigDict(frozen=True)

    # Required settings
    data_dir: DirectoryPath
    service_id: str
    ingress_server_url: str

    # Optional in OpenShift mode (retrieved from environment)
    ingress_server_auth_token: Optional[str] = None

    # Optional settings with defaults
    identity_id: str = "unknown"
    collection_interval: NonNegativeInt = constants.DATA_COLLECTOR_COLLECTION_INTERVAL
    cleanup_after_send: bool = True
    ingress_connection_timeout: PositiveInt = (
        constants.DATA_COLLECTOR_CONNECTION_TIMEOUT
    )
    allowed_subdirs: list[str] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, config_file: Path) -> "DataCollectorSettings":
        """Load settings from a YAML configuration file.

        Configuration is loaded exactly as specified in the YAML file
        with no environment variable overrides.
        """
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")

        with open(config_file, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)

        if config_data is None:
            raise ValueError(f"Configuration file is empty or invalid: {config_file}")

        return cls(**config_data)
