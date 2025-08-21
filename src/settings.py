from pydantic import (
    BaseModel,
    NonNegativeInt,
    PositiveInt,
    DirectoryPath,
    ConfigDict,
)


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
