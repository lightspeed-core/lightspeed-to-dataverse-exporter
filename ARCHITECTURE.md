# Architecture Documentation

## System Architecture

The following diagram shows the overall system architecture and data flow:

```mermaid
---
config:
  layout: dagre
---
flowchart TD
 subgraph Clients["Clients"]
        A1["Lightspeed Client 1"]
        A2["Lightspeed Client 2"]
        A3["Lightspeed Client N"]
  end
 subgraph Cloud["Cloud: c.r.c"]
        API["API Endpoint: Ingress"]
        S3[("S3 Bucket")]
        SQS[/"AWS SQS (Queue)"/]
  end
 subgraph MP_Plus["Cluster: MP+"]
        W1["Worker 1"]
        W2["Worker 2"]
        W3["Worker N"]
  end
 subgraph Snowflake["Snowflake"]
        EXT[("External Stage")]
        PIPE["Snowpipe"]
        DB_RAW[("snowpipe_db")]
        DB_TARGET[("lightspeedarchives_db<br/>(SADP - Raw Data)")]
  end
 subgraph Astro["Astro (Airflow)"]
        SCHED["Astro Scheduler"]
        DBT["Dbt Transformations"]
  end
    API --> S3
    S3 -- Put Object event --> SQS
    A1 --> API
    A2 --> API
    A3 --> API
    SQS --> W1 & W2 & W3
    W1 --> EXT
    W2 --> EXT
    W3 --> EXT
    EXT --> PIPE
    PIPE --> DB_RAW
    SCHED --> DBT
    DB_RAW --> DBT
    DBT --> DB_TARGET
```

**Note**: In Dataverse terminology, the `lightspeedarchives_db` serves as a **SADP (Source-Aligned Data Product)** - it contains all raw data from the source system. Client-specific **Aggregate Products** are created through DBT views that partition and filter this data by client/identifier, providing tailored access without duplicating the underlying data.

## Service Logic Flow

The Data Collection Service implements a robust flow with clear separation between single-shot and continuous operation modes.

### Overview

The service starts with configuration logging and mode detection, then delegates to specialized handlers:

- **Single-shot mode**: Execute one collection cycle and exit
- **Continuous mode**: Run periodic collection loop with graceful shutdown support

### Complete Logic Flow

```mermaid
graph TD
    A["`**Service Start**
    run() method called`"] --> B["`**Log Configuration**
    - Data directory
    - Service ID  
    - Identity ID`"]
    
    B --> C{"`**Mode Detection**
    collection_interval configured?`"}
    
    C -->|No| D["`**Single-Shot Mode**
    _run_single_shot()`"]
    C -->|Yes| E["`**Continuous Mode**
    _run_continuous()`"]
    
    %% Single-Shot Flow
    D --> D1[Log: Starting collection]
    D1 --> D2[Execute data collection]
    D2 --> D3[Log: Completed, exiting]
    D3 --> D4["`**Exit Service**`"]
    
    D2 -->|KeyboardInterrupt| D5[Log: Stopped by user]
    D5 --> D4
    
    D2 -->|OSError/RequestException| D6[Log error & re-raise]
    D6 --> D7["`**Exit with Error**
    (Non-zero code)`"]
    
    %% Continuous Flow  
    E --> E1["`user_interrupted = false`"]
    E1 --> E2{"`**Main Loop**
    shutdown_event set?`"}
    
    E2 -->|No| E3[Log: Starting collection]
    E3 --> E4[Calculate next_collection time]
    E4 --> E5[Execute data collection]
    E5 --> E6{"`Processing time
    > interval?`"}
    
    E6 -->|No| E7["`**Normal Wait**
    Log wait time`"]
    E7 --> E8{"`Shutdown during wait?
    shutdown_event.wait(time)`"}
    E8 -->|Yes| E9[Log: Shutdown requested]
    E8 -->|No| E2
    
    E6 -->|Yes| E10["`**Overtime Warning**
    Log overtime seconds`"]
    E10 --> E2
    
    %% Error Handling in Continuous Mode
    E5 -->|KeyboardInterrupt| E11["`Log: Stopped by user
    user_interrupted = true`"]
    E11 --> E12{"`**Exit Decision**
    user_interrupted?`"}
    
    E5 -->|OSError/RequestException| E13[Log error]
    E13 --> E14{shutdown_event set?}
    E14 -->|No| E15["`**Retry Logic**
    Log: Retrying in X seconds`"]
    E15 --> E16{"`Shutdown during retry?
    shutdown_event.wait(retry_interval)`"}
    E16 -->|Yes| E17[Log: Shutdown during retry]
    E16 -->|No| E2
    E14 -->|Yes| E18[Log: Skip retry, exiting]
    
    %% Final Collection Logic
    E2 -->|Yes| E12
    E9 --> E12
    E17 --> E12
    E18 --> E12
    
    E12 -->|Yes| E19["`**Skip Final Collection**
    User wants immediate exit`"]
    E12 -->|No| E20["`**Final Collection**
    Log: Performing final collection`"]
    
    E20 --> E21[Execute final data collection]
    E21 --> E22["`**Graceful Exit**`"]
    
    E21 -->|KeyboardInterrupt| E23[Log: Final collection interrupted]
    E21 -->|Other Exception| E24["`**Bubble Up Exception**
    Indicates potential data loss`"]
    
    E19 --> E25["`**Immediate Exit**`"]
    E23 --> E25
    
    %% Styling
    classDef startEnd fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef process fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef decision fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef error fill:#ffebee,stroke:#b71c1c,stroke-width:2px
    classDef success fill:#e8f5e8,stroke:#2e7d32,stroke-width:2px
    
    class A,D4,D7,E22,E24,E25 startEnd
    class B,D1,D2,D3,D5,E1,E3,E4,E5,E7,E9,E10,E11,E13,E15,E17,E18,E19,E20,E21,E23 process
    class C,E2,E6,E8,E12,E14,E16 decision
    class D6,D7,E24 error
    class D4,E22,E25 success
```

### Exit Scenarios

| Exit Trigger | Final Collection | Behavior |
|-------------|------------------|----------|
| SIGTERM signal | ✅ Yes | Sets shutdown_event → graceful loop exit → final collection |
| Ctrl+C (KeyboardInterrupt) | ❌ No | Immediate exit from loop, no final collection |
| Single-shot completion | ❌ No | Normal exit after one collection cycle |

### Error Handling Strategy

| Error Type | Single-Shot Mode | Continuous Mode |
|------------|------------------|-----------------|
| KeyboardInterrupt | Log + Exit | Log + Exit (no final collection) |
| OSError/RequestException | Log + Re-raise | Log + Retry indefinitely* |
| Final Collection Error | N/A | Bubble up (indicates data loss) |

**\* Retry Behavior in Continuous Mode:**
- Service errors (OSError/RequestException) trigger retry logic
- Retries continue indefinitely until either:
  - The operation succeeds, OR  
  - A shutdown event is received during retry wait
- No final collection is performed for service errors alone
- Final collection only occurs when the main loop exits due to shutdown_event

This architecture ensures reliable data collection with appropriate responses to different termination scenarios while maintaining operational visibility through comprehensive logging.
