ACCESS_TOKEN_GENERATION_TIMEOUT = 10

# Data collection constants
TARBALL_FILENAME = "lightspeed-assistant.tgz"  # have no effect

# This is a list of subdirectories that are allowed to be collected from
# the provided data_dir - it is here to prevent collecting unexpected data
# but it can be removed eventually as it is not purpose of this service
# do sanity check on provided data to export.
ALLOWED_SUBDIRS = ["feedback", "transcripts"]

DATA_MAX_SIZE = 100 * 1024 * 1024  # 100 MiB

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
