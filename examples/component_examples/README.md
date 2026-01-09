# Lambda Function Component Examples

This directory contains examples of using the Lambda Function Component to define Lambda-backed Dagster assets and jobs purely in YAML.

## Quick Start

### 1. Copy the Component to Your Project

```bash
cp lambda_component.py your_dagster_project/components/
```

### 2. Create a Component YAML File

Create a YAML file in your Dagster project (e.g., `components/my_lambda_asset.yaml`):

```yaml
component_type: components.lambda_component.LambdaFunctionComponent

params:
  lambda_config:
    function_name: my-lambda-function
    invocation_type: Event
    payload_mode: full

  asset:
    key: my_asset
    description: My Lambda-backed asset
```

### 3. Load Components in Your Dagster Code

```python
# your_dagster_project/__init__.py
import dagster as dg

# Load all component YAML files
defs = dg.Definitions.from_yaml_directory("components")
```

### 4. Deploy to Dagster Cloud

Make sure your `dagster_cloud.yaml` routes this code location to the Lambda agent:

```yaml
locations:
  - location_name: lambda_jobs
    code_source:
      package_name: your_dagster_project
    agent_queue: lambda  # Routes to Lambda agent
```

## Examples Overview

### Simple Asset
**File**: `lambda_asset_simple.yaml`

Basic Lambda-backed asset with configuration schema.

### Asset with Dependencies
**File**: `lambda_asset_with_deps.yaml`

Asset that depends on upstream assets and runs on a schedule.

### Partitioned Asset
**File**: `lambda_asset_partitioned.yaml`

Daily partitioned asset for time-series data processing.

### Existing Lambda Function
**File**: `lambda_existing_function.yaml`

Wraps an existing Lambda function with custom payload format.

### Multi-Step Job
**File**: `lambda_job_multi_step.yaml`

Job with multiple ops for ETL pipeline.

### Static Partitions
**File**: `lambda_static_partitions.yaml`

Asset with static partitions (e.g., by region, customer).

## Component Parameters

### Lambda Configuration (`lambda_config`)

```yaml
lambda_config:
  function_name: string       # Required: Lambda function name or ARN
  invocation_type: string     # Optional: "Event" (async) or "RequestResponse" (sync)
  payload_mode: string        # Optional: "full", "config_only", "ops_only", "custom"
  payload_config_path: string # Optional: For custom mode, e.g., "ops.my_op.config"
```

### Asset Configuration (`asset`)

```yaml
asset:
  key: string                 # Required: Asset key
  description: string         # Optional: Asset description
  group_name: string          # Optional: Asset group
  deps: [string]              # Optional: Upstream asset dependencies
  config_schema: object       # Optional: Configuration schema
  metadata: object            # Optional: Asset metadata
  partitions_def: string      # Optional: "daily", "weekly", "monthly", "static"
  partition_keys: [string]    # Optional: For static partitions
```

### Job Configuration (`ops` and `job_name`)

```yaml
job_name: string              # Required if ops are defined
job_description: string       # Optional: Job description

ops:
  - name: string              # Required: Op name
    description: string       # Optional: Op description
    config_schema: object     # Optional: Op configuration schema
```

### Schedule Configuration (`schedule`)

```yaml
schedule:
  cron_schedule: string       # Required: Cron expression
  execution_timezone: string  # Optional: Timezone (default: UTC)
```

## Configuration Schema Types

When defining `config_schema`, use the following types:

```yaml
config_schema:
  string_field:
    type: string
    default: "value"

  number_field:
    type: number
    default: 42

  boolean_field:
    type: boolean
    default: true

  array_field:
    type: array
    default: ["item1", "item2"]

  object_field:
    type: object
    default:
      key1: value1
      key2: value2
```

## Payload Modes

### `full` (Default)
Sends complete Dagster payload with run metadata, config, and environment variables.

**Use case**: New Lambda functions designed to work with Dagster

### `config_only`
Sends just the `run_config` dictionary.

**Use case**: Existing Lambda expecting Dagster's run config structure

### `ops_only`
Sends just the ops configuration from `run_config.ops`.

**Use case**: Existing Lambda expecting ops-level config

### `custom`
Extracts specific path from run_config using dot notation.

**Use case**: Existing Lambda with custom payload format

**Example**:
```yaml
lambda_config:
  payload_mode: custom
  payload_config_path: "ops.my_op.config"
```

This extracts `run_config["ops"]["my_op"]["config"]` and sends only that.

## Project Structure Example

```
your_dagster_project/
├── __init__.py
├── components/
│   ├── lambda_component.py           # The component class
│   ├── daily_metrics.yaml            # Asset component
│   ├── etl_pipeline.yaml             # Job component
│   └── regional_reports.yaml         # Partitioned asset
└── dagster_cloud.yaml                # Routes to Lambda agent
```

## Best Practices

1. **Use Asset Components for Independent Data Products**
   - Each asset represents a distinct data output
   - Good for parallel processing
   - Easier dependency management

2. **Use Job Components for Sequential Pipelines**
   - Multiple steps that must run in order
   - Good for ETL workflows
   - Better error handling for multi-step processes

3. **Choose Invocation Type Carefully**
   - `Event` (async): Fire-and-forget, better for parallelism
   - `RequestResponse` (sync): Wait for completion, better for sequential dependencies

4. **Match Payload Mode to Your Lambda**
   - `full`: Use for new Lambdas you control
   - `custom`: Use for existing Lambdas you can't change

5. **Use Partitions for Time-Series or Segmented Data**
   - Daily/weekly/monthly for time-based processing
   - Static partitions for regions, customers, etc.

## Testing Locally

Test your component YAML before deploying:

```python
# test_component.py
import dagster as dg

# Load single component
defs = dg.Definitions.from_yaml_file("components/my_lambda_asset.yaml")

# Verify it loads without errors
print(f"Assets: {len(defs.assets)}")
print(f"Jobs: {len(defs.jobs)}")
print(f"Schedules: {len(defs.schedules)}")
```

Run with:
```bash
python test_component.py
```

## Troubleshooting

### Component doesn't load
- Check YAML syntax (use `yamllint`)
- Verify `component_type` path is correct
- Ensure required fields are present

### Lambda not invoked
- Verify `lambda/function_name` tag is set
- Check agent is configured with LambdaRunLauncher
- Verify code location is routed to Lambda agent queue

### Wrong payload format
- Check `payload_mode` setting
- For `custom` mode, verify `payload_config_path` is correct
- Test payload extraction with simple config first

## Additional Resources

- [Dagster Components Guide](https://docs.dagster.io/guides/build/components)
- [Lambda Run Launcher README](../../README.md)
- [Existing Lambda Examples](../existing_lambda_examples.py)
