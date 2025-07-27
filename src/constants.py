ACCESS_TOKEN_GENERATION_TIMEOUT = 10

# Data collection constants
TARBALL_FILENAME = "lightspeed-assistant.tgz"  # have no effect

# 100 MiB - Maximum size of a single payload/chunk
MAX_PAYLOAD_SIZE = 100 * 1024 * 1024
# 200 MiB - Maximum total size of data directory
MAX_DATA_DIR_SIZE = 2 * MAX_PAYLOAD_SIZE

# This user-agent work with any identity_id and correctly passes
# this id further down the road, but it is a hack and depends on
# uhc-auth-proxy inner logic. OLS-1959 is about defining a new agent
# for lightspeed assistants.
USER_AGENT = "openshift-lightspeed-operator/user-data-collection cluster/{identity_id}"
CONTENT_TYPE = "application/vnd.redhat.{service_id}.periodic+tar"

# Timing constants (in seconds)
DATA_COLLECTOR_COLLECTION_INTERVAL = 7200  # 2 hours
DATA_COLLECTOR_CONNECTION_TIMEOUT = 30
DATA_COLLECTOR_RETRY_INTERVAL = 300  # 5 minutes
