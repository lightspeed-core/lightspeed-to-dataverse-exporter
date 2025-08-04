# Onboarding - Lightspeed to Dataverse Exporter

## Architecture Overview

```
┌─────────────────┐      POST       ┌─────────────────┐
│  Data Collector │ ──────────────> │    Ingress      │
│  (this service) │                 │    Service      │
└─────────────────┘                 └─────────────────┘
                                              │
                                              │ notify
                                              ▼
                                    ┌─────────────────┐
                                    │ insights-storage│
                                    │    -broker      │
                                    └─────────────────┘
                                              │
                                              │ store
                                              ▼
                                    ┌─────────────────┐
                                    │   S3 Bucket     │
                                    │   (final data)  │
                                    └─────────────────┘
```

**Note:** This diagram shows data transport to internal Red Hat systems. A separate process handles transport from S3 to Dataverse (not shown).

## Required Setup

### Service ID

Define your service ID to distinguish different Lightspeed products.

**Steps:**
1. **Choose ID** - Use a shortcut version of your project (e.g., `openshiftlightspeed` → `ols`)
2. **Register to Ingress** - Include in `INGRESS_VALID_UPLOAD_TYPES` environment variable. Example PR:  
   https://github.com/RedHatInsights/insights-ingress-go/pull/536
3. **Register for insights-storage-broker** - Include as `MONITORED_SERVICES`. Example PR:  
   https://gitlab.cee.redhat.com/service/app-interface/-/merge_requests/150353
4. **Define route** - Add Ingress to S3 bucket routing. Example PR:  
   https://github.com/RedHatInsights/insights-storage-broker/pull/272 (follow the format, omit bucket definition)

**Review required:** Contact `@crc-integrations-team` in `#forum-consoledot` (Slack) (and cc Ondrej Metelka).

### Identity ID (Optional)

Used to distinguish specific Lightspeed deployments within product. Exposed in Dataverse for data filtering.

**Example:** In OpenShift context, this is typically the cluster ID.

### Data Requirements

The configured `data_dir` must contain JSON files. Files can be in the root directory or nested in subdirectories - the service will recursively scan for `*.json` files.

### Ingress Authentication

Authentication method varies per product/instance depending on what's available in the deployment environment.

**OpenShift:** Uses cluster pull-secret containing credentials for authentication.

## Testing

### 1. Create Mock Data

Create test directory structure:
```bash
mkdir -p test-data/feedback
```

Create sample JSON file:
```bash
cat > test-data/feedback/test-feedback.json << 'EOF'
{"user_id": "user_id_placeholder", "timestamp": "2025-07-24 13:16:49.140050+00:00", "conversation_id": "123e4567-e89b-12d3-a456-426614174000", "user_question": "What is XYZ", "llm_response": "Some elaborate answer", "sentiment": 1, "user_feedback": ""}
EOF
```

### 2. Send to Ingress

**Generate Authentication Token (for stage testing):**

If testing against the stage environment, generate an ingress auth token from your offline token:

```bash
# Get your offline token from https://access.stage.redhat.com/management/api
# Then generate the ingress auth token:
python scripts/ingress_token_from_offline_token.py --offline-token YOUR_OFFLINE_TOKEN --env stage
export INGRESS_SERVER_AUTH_TOKEN="your-auth-token"
```

**Create test configuration:**
```bash
cat > test-config.yaml << 'EOF'
data_dir: "./test-data"
service_id: "your-service-id"
ingress_server_url: "https://your-stage-ingress-url/api/v1/data/ingest"  # use staging for testing
identity_id: "test-instance"
collection_interval: 60
cleanup_after_send: false
EOF
```

**Run the service:**
```bash
uv run python -m src.main --config test-config.yaml --log-level DEBUG
```


### 3. Verify Data in S3

TBD - requires access to internal bucket.

Temporary verification is available through Ondrej Metelka or Juan Diaz Suarez by providing the request_id from Ingress (logged after successful export). 
