# Example Dagster Project with Lambda Components

This is a complete example showing how to use the Lambda Function Component to define your Dagster pipelines purely in YAML.

## Project Structure

```
dagster_lambda_example/
├── __init__.py                     # Loads component YAMLs
├── setup.py                        # Package configuration
├── dagster_cloud.yaml              # Routes to Lambda agent
├── components/
│   ├── lambda_component.py         # Component class (copy from examples/)
│   └── daily_metrics.yaml          # Example asset component
└── README.md                       # This file
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -e .
```

### 2. Copy the Component Class

```bash
# Copy the lambda_component.py to your components directory
cp ../../lambda_component.py components/
```

### 3. Create Component YAML Files

See `components/daily_metrics.yaml` for an example. Create more components as needed:

```yaml
# components/my_lambda_asset.yaml
type: components.lambda_component.LambdaFunctionComponent

attributes:
  lambda_config:
    function_name: my-lambda-function
    invocation_type: Event
    payload_mode: full

  asset:
    key: my_asset
    description: My Lambda-backed asset
```

### 4. Configure Agent Routing

Create `dagster_cloud.yaml` in your project root:

```yaml
locations:
  - location_name: lambda_jobs
    code_source:
      package_name: dagster_lambda_example
    agent_queue: lambda  # Routes to Lambda agent
```

### 5. Deploy to Dagster Cloud

```bash
dagster-cloud deployment deploy
```

## Testing Locally

Run the Dagster UI locally:

```bash
dagster dev
```

Then navigate to http://localhost:3000

## Component Examples

### Simple Asset

```yaml
type: components.lambda_component.LambdaFunctionComponent

attributes:
  lambda_config:
    function_name: my-processor
    invocation_type: Event
    payload_mode: full

  asset:
    key: processed_data
    config_schema:
      input_path:
        type: string
      output_path:
        type: string
```

### Asset with Schedule

```yaml
type: components.lambda_component.LambdaFunctionComponent

attributes:
  lambda_config:
    function_name: daily-report
    invocation_type: Event
    payload_mode: full

  asset:
    key: daily_report
    group_name: reporting

  schedule:
    cron_schedule: "0 9 * * *"  # 9 AM daily
    execution_timezone: America/New_York
```

### Multi-Step Job

```yaml
type: components.lambda_component.LambdaFunctionComponent

attributes:
  lambda_config:
    function_name: etl-handler
    invocation_type: RequestResponse
    payload_mode: ops_only

  job_name: etl_pipeline

  ops:
    - name: extract
      config_schema:
        source:
          type: string
    - name: transform
      config_schema:
        rules:
          type: array
    - name: load
      config_schema:
        destination:
          type: string
```

### Existing Lambda Function

```yaml
type: components.lambda_component.LambdaFunctionComponent

attributes:
  lambda_config:
    function_name: existing-lambda
    invocation_type: Event
    payload_mode: custom
    payload_config_path: "ops.my_asset.config"

  asset:
    key: my_asset
    config_schema:
      # Your existing Lambda's expected format
      bucket:
        type: string
      prefix:
        type: string
```

## Adding More Assets

Simply create new YAML files in the `components/` directory. They'll be automatically discovered and loaded by `Definitions.from_yaml_directory()`.

## Configuration Options

### Lambda Config
- `function_name`: Lambda function name or ARN (required)
- `invocation_type`: `Event` (async) or `RequestResponse` (sync)
- `payload_mode`: `full`, `config_only`, `ops_only`, or `custom`
- `payload_config_path`: For custom mode, path to extract (e.g., `ops.my_op.config`)

### Asset Config
- `key`: Asset key (required)
- `description`: Asset description
- `group_name`: Asset group
- `deps`: List of upstream asset keys
- `config_schema`: Configuration schema
- `metadata`: Asset metadata
- `partitions_def`: `daily`, `weekly`, `monthly`, or `static`
- `partition_keys`: For static partitions

### Job Config (alternative to asset)
- `job_name`: Job name (required if using ops)
- `job_description`: Job description
- `ops`: List of op configurations

### Schedule Config
- `cron_schedule`: Cron expression (required)
- `execution_timezone`: Timezone (default: UTC)

## Next Steps

1. Create Lambda functions in AWS
2. Configure Lambda agent in ECS (see main README)
3. Create component YAML files for your use cases
4. Deploy to Dagster Cloud
5. Monitor execution in Dagster Cloud UI

## Troubleshooting

**Components not loading?**
- Check YAML syntax: `yamllint components/*.yaml`
- Verify `component_type` path matches your structure
- Ensure `lambda_component.py` is in the `components/` directory

**Lambda not invoked?**
- Verify `dagster_cloud.yaml` routes to Lambda agent queue
- Check Lambda function name is correct
- Verify Lambda agent has IAM permissions

**Wrong payload format?**
- Check `payload_mode` setting
- For `custom` mode, verify `payload_config_path` extracts correctly
- Test with `full` mode first, then customize

## Resources

- [Component Examples README](../README.md)
- [Lambda Run Launcher Main README](../../../README.md)
- [Dagster Components Guide](https://docs.dagster.io/guides/build/components)
