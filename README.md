# Dagster+ Agent with Lambda Run Launcher

A custom Dagster+ agent that extends the standard agent with a Lambda Run Launcher, enabling job execution as AWS Lambda function invocations instead of spinning up new ECS tasks or containers.

## Overview

This project provides a complete, deployable custom Dagster+ agent:

- **Agent**: Runs in ECS (always-on) with custom Lambda run launcher
- **Code Locations**: Standard Dagster code locations
- **Job Execution**: Invokes AWS Lambda functions instead of creating containers

### Architecture

```
┌─────────────────────────────────┐
│   Dagster Cloud (SaaS)          │
└──────────────┬──────────────────┘
               │ gRPC API
┌──────────────▼──────────────────┐
│   Custom Agent (ECS)            │
│   - Base Dagster+ Agent         │
│   - Lambda Run Launcher         │
└──────────┬─────────────┬────────┘
           │             │
    ┌──────▼──────┐ ┌───▼────────────┐
    │ Lambda      │ │ Lambda         │
    │ (sync call) │ │ (async event)  │
    └─────────────┘ └────────────────┘
```

## Multi-Agent Architecture (Typical Setup)

**Important**: Dagster agents can only be configured with a **single run launcher**. In most production scenarios, you'll want to orchestrate **both**:

1. **Lambda functions** (using this Lambda run launcher)
2. **Python code** (using standard ECS/Kubernetes run launcher)

Since each agent supports only one run launcher, you'll need to deploy **multiple agents** and use **agent queues** to route jobs appropriately.

### Typical Production Architecture

```
┌──────────────────────────────────────────────────────────────┐
│   Dagster Cloud (SaaS)                                       │
│   - Receives all job requests                                │
│   - Routes to appropriate agent based on queue tags          │
└────────────────┬────────────────────┬────────────────────────┘
                 │                    │
        ┌────────▼────────┐  ┌────────▼────────────┐
        │ Lambda Agent    │  │ ECS Agent           │
        │ (Queue: lambda) │  │ (Queue: ecs)        │
        │ ECS Fargate     │  │ ECS Fargate         │
        └────┬──────┬─────┘  └────┬────────────────┘
             │      │              │
      ┌──────▼─┐ ┌─▼──────┐  ┌────▼──────────────┐
      │Lambda  │ │Lambda  │  │ECS Tasks          │
      │(sync)  │ │(async) │  │(Python code)      │
      └────────┘ └────────┘  └───────────────────┘
```

### Agent Queues

**Important**: Agent queues are configured at the **code location level** in Dagster Cloud, not per-job. Each code location is assigned to a specific agent queue, and all jobs in that location are routed to the corresponding agent.

**Lambda Agent** - Handles Lambda function invocations:
```yaml
# dagster.yaml for Lambda agent
instance:
  agent:
    queues:
      - lambda  # This agent processes code locations assigned to "lambda" queue
  run_launcher:
    module: lambda_run_launcher
    class: LambdaRunLauncher
```

**ECS Agent** - Handles Python code execution:
```yaml
# dagster.yaml for ECS agent
instance:
  agent:
    queues:
      - ecs  # This agent processes code locations assigned to "ecs" queue
  run_launcher:
    module: dagster_aws.ecs
    class: EcsRunLauncher
```

### Configuring Code Locations with Queues

You need to create **separate code locations** for Lambda and ECS jobs, each specifying its target queue in `dagster_cloud.yaml`.

#### Example Repository Structure:

```
my-dagster-repo/
├── lambda_jobs/          # Code location for Lambda agent
│   ├── dagster_cloud.yaml   # Specifies queue: lambda
│   ├── __init__.py
│   └── jobs.py              # Jobs that invoke Lambda functions
│
└── python_jobs/         # Code location for ECS agent
    ├── dagster_cloud.yaml   # Specifies queue: ecs
    ├── __init__.py
    └── jobs.py              # Jobs that run Python code
```

#### Code Location Configuration

**lambda_jobs/dagster_cloud.yaml**:
```yaml
locations:
  - location_name: lambda_jobs
    code_source:
      package_name: lambda_jobs
    agent_queue: lambda  # Routes to Lambda agent
```

**python_jobs/dagster_cloud.yaml**:
```yaml
locations:
  - location_name: python_jobs
    code_source:
      package_name: python_jobs
    agent_queue: ecs  # Routes to ECS agent
```

#### Example Job Definitions

**lambda_jobs/jobs.py** (served by Lambda agent):
```python
import dagster as dg

@dg.op(config_schema={"api_endpoint": str})
def call_api(context):
    """Lightweight API call - runs in Lambda."""
    pass

@dg.job(
    tags={
        "lambda/function_name": "my-handler",
        "lambda/invocation_type": "Event"
    }
)
def api_job():
    """Automatically routed to Lambda agent via agent_queue: lambda."""
    call_api()

defs = dg.Definitions(jobs=[api_job])
```

**python_jobs/jobs.py** (served by ECS agent):
```python
import dagster as dg
import pandas as pd

@dg.op
def process_data(context):
    """Heavy processing - runs in ECS."""
    df = pd.DataFrame({"data": range(1000000)})
    return df

@dg.job
def processing_job():
    """Automatically routed to ECS agent via agent_queue: ecs."""
    process_data()

defs = dg.Definitions(jobs=[processing_job])
```

### When to Use Lambda vs ECS Agent

| Use Lambda Agent | Use ECS Agent |
|------------------|---------------|
| Configuration-driven jobs | Python code execution |
| Invoking existing Lambda functions | Custom pip dependencies |
| Fast execution (<15 min) | Long-running jobs (>15 min) |
| Event-driven workflows | Stateful computations |
| Instant invocation (no cold start) | Memory-intensive tasks (>10GB) |
| API integrations | GPU/specialized hardware |

### Deployment: Two Agents

#### 1. Deploy Lambda Agent

```bash
# Build Lambda agent
cd lambda_run_launcher/infra
export ECR_REGISTRY=your-registry
export IMAGE_NAME=dagster-lambda-agent
./build-and-push.sh

# Deploy to ECS
aws ecs register-task-definition \
  --cli-input-json file://ecs-task-definition-lambda.json

aws ecs create-service \
  --cluster your-cluster \
  --service-name dagster-lambda-agent \
  --task-definition dagster-lambda-agent \
  --desired-count 1
```

#### 2. Deploy ECS Agent (Standard Dagster+ Agent)

```bash
# Use standard Dagster+ ECS agent
# Configure with ECS run launcher and queue: ecs

# Example ECS agent dagster.yaml
cat > dagster-ecs.yaml << EOF
instance:
  class: DagsterCloudAgentInstance
  agent:
    queues:
      - ecs
  run_launcher:
    module: dagster_aws.ecs
    class: EcsRunLauncher
    config:
      cluster: your-ecs-cluster
      subnets:
        - subnet-xxxxx
      security_group_ids:
        - sg-xxxxx
EOF

# Deploy ECS agent
aws ecs create-service \
  --cluster your-cluster \
  --service-name dagster-ecs-agent \
  --task-definition dagster-ecs-agent \
  --desired-count 1
```

### Agent Configuration Files

Create two separate agent configurations:

**Lambda Agent** (`dagster-lambda.yaml`):
```yaml
instance:
  class: DagsterCloudAgentInstance
  agent:
    queues:
      - lambda  # Only handle jobs tagged with queue: lambda
  run_launcher:
    module: lambda_run_launcher
    class: LambdaRunLauncher
    config:
      default_function_name: ${DEFAULT_LAMBDA_FUNCTION}
      region_name: ${AWS_REGION:us-east-1}
      payload_mode: ${PAYLOAD_MODE:full}
```

**ECS Agent** (`dagster-ecs.yaml`):
```yaml
instance:
  class: DagsterCloudAgentInstance
  agent:
    queues:
      - ecs  # Only handle jobs tagged with queue: ecs
  run_launcher:
    module: dagster_aws.ecs
    class: EcsRunLauncher
    config:
      cluster: your-ecs-cluster
      subnets:
        - subnet-xxxxx
      security_group_ids:
        - sg-xxxxx
      task_definition: dagster-run-worker
```

### Performance Comparison

**Single ECS Agent** (all jobs):
- Every job waits for ECS task to spin up (~30-60 seconds)
- Resource contention during high-volume periods
- Fixed concurrency limits

**Multi-Agent Setup** (Lambda + ECS):
- Lambda jobs execute **instantly** (no task startup wait)
- Unlimited concurrency for lightweight jobs
- ECS only for jobs that actually need it

**Key Benefit**: Sub-second job startup for Lambda vs 30-60 second ECS task startup

**Example Impact**: A job that runs every 5 minutes with 10-second execution:
- **ECS**: 40-second total (30s startup + 10s execution) = 8 jobs/hour max
- **Lambda**: 10-second total (instant startup + 10s execution) = 360 jobs/hour possible

### Default Queue Behavior

If you **don't** configure agent queues:
- All agents will attempt to process all code locations
- First agent to claim the job wins
- Can lead to failures if wrong agent picks up a job

**Best Practice**: Always configure explicit queues in production:
- **Agents**: Configure `queues: [lambda]` or `queues: [ecs]` in agent's dagster.yaml
- **Code Locations**: Add `agent_queue: lambda` or `agent_queue: ecs` in each location's dagster_cloud.yaml
- **Result**: Deterministic routing, jobs always go to the correct agent

**Configuration on BOTH sides is required**: The code location declares its requirements (`agent_queue`), and the agent declares its capabilities (`queues`).

### Complete Setup Workflow

1. **Deploy Two Agents**:
   - Lambda agent with `queues: [lambda]` in dagster.yaml
   - ECS agent with `queues: [ecs]` in dagster.yaml

2. **Structure Your Repository**:
   ```
   my-repo/
   ├── lambda_jobs/
   │   ├── dagster_cloud.yaml  # agent_queue: lambda
   │   └── jobs.py
   └── python_jobs/
       ├── dagster_cloud.yaml  # agent_queue: ecs
       └── jobs.py
   ```

3. **Configure Queue Routing**:
   - Each code location specifies its target queue in `dagster_cloud.yaml`
   - Add `agent_queue: lambda` or `agent_queue: ecs` to each location

4. **Deploy to Dagster Cloud**:
   - Push your code to Git (or deploy via CLI)
   - Dagster Cloud reads `dagster_cloud.yaml` from each location
   - Jobs automatically route to correct agent based on `agent_queue`

**Important**: Both the agent (via `queues: [...]`) and code location (via `agent_queue: ...`) must specify matching queue names.

### Monitoring Multiple Agents

In Dagster Cloud UI:
- Go to **Deployment Settings** > **Agents**
- You'll see both agents listed with their queues
- Monitor health and job assignment for each agent
- View which agent executed each run in run details
- Each code location shows which queue (and therefore agent) serves it

## Project Structure

```
lambda_run_launcher/
├── Dockerfile                      # Custom agent image (extends dagster-cloud-agent)
├── dagster.yaml                    # Agent configuration
├── requirements.txt                # Python dependencies
├── README.md                       # This file
│
├── app/                            # Lambda run launcher code
│   ├── __init__.py
│   └── lambda_run_launcher.py     # Main launcher implementation
│
├── infra/                          # Deployment infrastructure
│   ├── build-and-push.sh          # Docker build and push script
│   ├── ecs-task-definition.json   # ECS task definition template
│   ├── iam-policy.json            # IAM policy for agent role
│   └── env.example                # Environment variables template
│
└── examples/                       # Usage examples
    ├── dagster_job_example.py     # Dagster job examples
    └── lambda_handler.py          # Example Lambda handler
```

## Quick Start

### Prerequisites

- AWS Account with ECR, ECS, and Lambda access
- Dagster Cloud organization and deployment
- Docker installed locally
- AWS CLI configured

### Step 1: Build and Push Docker Image

```bash
# Set your ECR registry
export ECR_REGISTRY=123456789012.dkr.ecr.us-east-1.amazonaws.com

# Build and push the agent image
cd infra
chmod +x build-and-push.sh
./build-and-push.sh
```

### Step 2: Configure IAM Permissions

Create an IAM role for the ECS task with Lambda invocation permissions:

```bash
# Create the role (if it doesn't exist)
aws iam create-role \
  --role-name DagsterLambdaAgentRole \
  --assume-role-policy-document file://trust-policy.json

# Attach the Lambda invocation policy
aws iam put-role-policy \
  --role-name DagsterLambdaAgentRole \
  --policy-name LambdaInvocationPolicy \
  --policy-document file://iam-policy.json
```

### Step 3: Store Dagster Cloud Agent Token

```bash
# Store agent token in Secrets Manager
aws secretsmanager create-secret \
  --name dagster/agent-token \
  --secret-string "your-agent-token-from-dagster-cloud"
```

### Step 4: Deploy to ECS

```bash
# Register task definition
aws ecs register-task-definition \
  --cli-input-json file://ecs-task-definition.json

# Create or update ECS service
aws ecs create-service \
  --cluster your-cluster-name \
  --service-name dagster-lambda-agent \
  --task-definition dagster-lambda-agent \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}"
```

### Step 5: Deploy Example Lambda Function

```bash
# Create deployment package
cd examples
zip lambda_handler.zip lambda_handler.py

# Deploy Lambda function
aws lambda create-function \
  --function-name dagster-example-handler \
  --runtime python3.11 \
  --handler lambda_handler.lambda_handler \
  --role arn:aws:iam::123456789012:role/lambda-execution-role \
  --zip-file fileb://lambda_handler.zip
```

### Step 6: Create and Run Dagster Job

```python
import dagster as dg

@dg.op
def my_op(context):
    context.log.info("Running in Lambda!")
    return {"status": "success"}

@dg.job(
    tags={
        "lambda/function_name": "dagster-example-handler",
        "lambda/invocation_type": "Event"
    }
)
def my_lambda_job():
    my_op()
```

Deploy this code to your Dagster Cloud code location and run the job!

## Configuration

### Agent Configuration (dagster.yaml)

The agent configuration supports environment variable expansion using `${VAR_NAME}` or `${VAR_NAME:default}` syntax:

```yaml
instance:
  class: DagsterCloudAgentInstance

  run_launcher:
    module: lambda_run_launcher
    class: LambdaRunLauncher
    config:
      default_function_name: ${DEFAULT_LAMBDA_FUNCTION:}
      default_invocation_type: ${DEFAULT_INVOCATION_TYPE:Event}
      region_name: ${AWS_REGION:us-east-1}
      env_vars:
        - DAGSTER_CLOUD_ORG_ID
        - DAGSTER_CLOUD_DEPLOYMENT_ID
      sync_timeout: ${LAMBDA_SYNC_TIMEOUT:300}
```

### Environment Variables

Required:
- `DAGSTER_CLOUD_AGENT_TOKEN` - Agent authentication token from Dagster Cloud

Recommended:
- `AWS_REGION` - AWS region for Lambda functions
- `DEFAULT_LAMBDA_FUNCTION` - Default Lambda function name
- `DEFAULT_INVOCATION_TYPE` - Default invocation type (Event or RequestResponse)

See `infra/env.example` for complete list.

## Lambda Run Launcher Features

### Invocation Types

**Asynchronous (Event)** - Default
```python
@dg.job(tags={"lambda/invocation_type": "Event"})
def async_job():
    my_op()
```

- Fire-and-forget execution
- No timeout limits (besides Lambda's 15-minute max)
- Suitable for long-running or background jobs

**Synchronous (RequestResponse)**
```python
@dg.job(tags={"lambda/invocation_type": "RequestResponse"})
def sync_job():
    my_op()
```

- Agent waits for Lambda completion
- Response available in engine events
- Limited to 15-minute Lambda max execution time

### Specifying Lambda Functions

**Per-Job Tags (Recommended)**
```python
@dg.job(tags={"lambda/function_name": "my-lambda"})
def job1():
    pass
```

**Using ARN**
```python
@dg.job(tags={"lambda/function_arn": "arn:aws:lambda:..."})
def job2():
    pass
```

**Run Configuration**
```python
@dg.job(config={
    "execution": {
        "config": {
            "lambda_function": "my-lambda",
            "invocation_type": "Event"
        }
    }
})
def job3():
    pass
```

**Global Default**
Set `DEFAULT_LAMBDA_FUNCTION` environment variable in ECS task.

### Lambda Payload Structure

Your Lambda function receives a comprehensive payload:

```json
{
  "dagster_run": {
    "run_id": "uuid",
    "job_name": "my_job",
    "deployment_name": "prod",
    "location_name": "my_location",
    "agent_id": "agent-id",
    "tags": {...}
  },
  "run_config": {
    "ops": {
      "my_op": {
        "config": {...}
      }
    }
  },
  "environment_variables": {
    "DAGSTER_CLOUD_ORG_ID": "...",
    "AWS_REGION": "..."
  },
  "dagster_cloud": {
    "org_id": "...",
    "deployment_id": "..."
  },
  "metadata": {
    "launched_at": "2026-01-09T12:00:00Z",
    "launcher_version": "1.0.0",
    "region": "us-east-1"
  }
}
```

### Using Existing Lambda Functions

If you have existing Lambda functions that expect a different payload format, you don't need to modify them! The launcher supports multiple payload modes to accommodate existing Lambda functions.

#### Payload Mode: `full` (Default)

Sends the comprehensive payload structure shown above. Best for new Lambda functions built specifically for Dagster.

```yaml
# dagster.yaml
run_launcher:
  config:
    payload_mode: 'full'  # Default, can be omitted
```

#### Payload Mode: `config_only`

Sends only the `run_config` dictionary. Useful if your existing Lambda expects Dagster's config structure.

```yaml
# dagster.yaml
run_launcher:
  config:
    payload_mode: 'config_only'
```

Your Lambda receives:
```json
{
  "ops": {
    "my_op": {
      "config": {
        "param1": "value1"
      }
    }
  }
}
```

#### Payload Mode: `ops_only`

Sends only the ops configuration from `run_config.ops`. Perfect for Lambda functions that process op configs.

```yaml
# dagster.yaml
run_launcher:
  config:
    payload_mode: 'ops_only'
```

Your Lambda receives:
```json
{
  "my_op": {
    "config": {
      "param1": "value1"
    }
  }
}
```

#### Payload Mode: `custom`

Extracts a specific path from `run_config` using dot notation. Ideal for Lambda functions expecting a specific config structure.

```yaml
# dagster.yaml
run_launcher:
  config:
    payload_mode: 'custom'
    payload_config_path: 'ops.my_op.config'
```

Your Lambda receives exactly the extracted value:
```json
{
  "param1": "value1",
  "param2": "value2"
}
```

#### Migration Strategy

**Phase 1: No Lambda Changes** (Start here for existing functions)
```yaml
payload_mode: 'custom'
payload_config_path: 'ops.my_op.config'
```
Your existing Lambda continues to work without any code changes!

**Phase 2: Optional Enhancement**
```yaml
payload_mode: 'config_only'
```
Update Lambda to handle multiple ops if needed.

**Phase 3: Full Integration** (For new Lambda functions)
```yaml
payload_mode: 'full'
```
Access rich metadata, environment variables, and Dagster Cloud info.

#### Example: Existing S3 Copy Lambda

Suppose you have an existing Lambda that expects:
```json
{
  "source_bucket": "my-bucket",
  "destination_bucket": "other-bucket",
  "file_pattern": "*.csv"
}
```

Dagster job:
```python
@dg.op(config_schema={
    "source_bucket": str,
    "destination_bucket": str,
    "file_pattern": str
})
def copy_files(context):
    pass

@dg.job(tags={"lambda/function_name": "existing-s3-copy"})
def copy_job():
    copy_files()
```

Agent config:
```yaml
payload_mode: 'custom'
payload_config_path: 'ops.copy_files.config'
```

**No Lambda code changes needed!** The launcher extracts and sends exactly what your Lambda expects.

See `examples/existing_lambda_examples.py` and `examples/existing_lambda_handler.py` for more detailed examples.

## IAM Permissions

### ECS Task Role (Agent)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction",
        "lambda:InvokeAsync"
      ],
      "Resource": "arn:aws:lambda:*:*:function:dagster-*"
    }
  ]
}
```

### Lambda Execution Role

Standard Lambda execution role plus any additional permissions your functions need (S3, DynamoDB, etc.)

## Examples

See the `examples/` directory for:

- `dagster_job_example.py` - Various job patterns using Lambda launcher (new Lambda functions)
- `lambda_handler.py` - Example Lambda function handler (new Lambda functions)
- `existing_lambda_examples.py` - How to use existing Lambda functions with different payload modes
- `existing_lambda_handler.py` - Example existing Lambda handlers and migration patterns
- `multi_agent_example.py` - **Multi-agent setup with Lambda + ECS agents, queue routing, and job examples**
- `dagster_cloud_lambda.yaml` - **Example dagster_cloud.yaml for Lambda code location (agent_queue: lambda)**
- `dagster_cloud_ecs.yaml` - **Example dagster_cloud.yaml for ECS code location (agent_queue: ecs)**

## Deployment

### Local Development

1. Build image locally:
   ```bash
   docker build -t dagster-lambda-agent:dev .
   ```

2. Run locally (testing):
   ```bash
   docker run -e DAGSTER_CLOUD_AGENT_TOKEN=your-token \
              -e AWS_REGION=us-east-1 \
              -e AWS_ACCESS_KEY_ID=xxx \
              -e AWS_SECRET_ACCESS_KEY=xxx \
              dagster-lambda-agent:dev
   ```

### Production Deployment

1. **Use ECR for image storage**
   ```bash
   cd infra
   ECR_REGISTRY=your-registry.amazonaws.com ./build-and-push.sh
   ```

2. **Use Secrets Manager for sensitive data**
   - Store agent token in Secrets Manager
   - Reference in ECS task definition

3. **Use IAM roles instead of access keys**
   - Assign IAM role to ECS task
   - No need for AWS credentials in environment

4. **Enable CloudWatch logging**
   - Configure in ECS task definition
   - Monitor agent logs in CloudWatch

5. **Use ECS Service for high availability**
   - Set desired count to 1 (agent should run as singleton)
   - Enable ECS Service auto-recovery

## Monitoring

### Agent Logs

View agent logs in CloudWatch Logs:
```bash
aws logs tail /ecs/dagster-lambda-agent --follow
```

### Lambda Execution

Check Lambda logs for job execution:
```bash
aws logs tail /aws/lambda/dagster-example-handler --follow
```

### Dagster UI

- View run logs in Dagster Cloud UI
- Check engine events for Lambda invocation details
- Monitor run status and results

## Troubleshooting

### Agent Not Starting

**Check:**
- Agent token is valid and stored in Secrets Manager
- ECS task role has permissions to read secrets
- Network configuration allows outbound HTTPS to Dagster Cloud

**Logs:**
```bash
aws logs tail /ecs/dagster-lambda-agent --follow
```

### Lambda Not Invoked

**Check:**
- Lambda function name/ARN is correct
- IAM role has `lambda:InvokeFunction` permission
- Lambda function exists in the specified region

**Verify permissions:**
```bash
aws lambda get-function --function-name dagster-example-handler
```

### Payload Too Large

**Error:** `Payload exceeds Lambda limit (256KB)`

**Solutions:**
- Reduce run_config size
- Store large data in S3 and pass references
- Use environment variables instead of config where possible

### Function Not Found

**Error:** `Lambda function 'xxx' not found`

**Check:**
- Function name is spelled correctly
- Function exists in the same region as configured
- Agent has permission to invoke the function

## Limitations

1. **Execution Time**: Lambda has 15-minute maximum timeout
2. **Payload Size**: 256KB limit on request payload
3. **No Termination**: Cannot stop Lambda functions once invoked
4. **No Code Execution**: Lambda functions must be pre-deployed
5. **Async Status**: No built-in status tracking for async invocations

## Performance & Scalability

### Why Lambda for Lightweight Jobs?

**Instant Execution**: Lambda functions are already running - no container startup time
- **Lambda**: <1 second to start execution
- **ECS Task**: 30-60 seconds to spin up container

**High Concurrency**: Lambda scales automatically
- **Lambda**: Thousands of concurrent executions
- **ECS Task**: Limited by cluster capacity

**Event-Driven**: Perfect for reactive workflows
- Trigger on S3 events, API calls, schedule events
- No waiting for containers to be ready

### Performance Comparison

**Scenario**: API webhook that triggers data validation (5-second execution)

| Approach | Startup Time | Execution Time | Total Time | Max Throughput |
|----------|--------------|----------------|------------|----------------|
| **ECS Task** | 30-60s | 5s | **35-65s** | ~60 jobs/hour |
| **Lambda** | <1s | 5s | **~6s** | Thousands/hour |

**Result**: Lambda is **6-10x faster** for lightweight jobs

### Real-World Use Cases

**Use Lambda Agent for**:
- **Webhooks**: Respond to external events instantly
- **Data validation**: Quick checks on incoming data
- **Notifications**: Send alerts without delay
- **Triggers**: Start longer processes quickly
- **API integrations**: Call external services
- **Status checks**: Poll for changes frequently

**Use ECS Agent for**:
- **Data processing**: Transform large datasets with pandas/spark
- **ML training**: Long-running model training
- **Batch jobs**: Process thousands of records
- **Complex pipelines**: Multi-step Python workflows

## Advanced Topics

### Custom Environment Variables

Add custom variables to pass to Lambda:

1. Add to `env_vars` in dagster.yaml:
   ```yaml
   env_vars:
     - CUSTOM_API_KEY
     - DATABASE_URL
   ```

2. Set in ECS task definition:
   ```json
   "environment": [
     {"name": "CUSTOM_API_KEY", "value": "xxx"}
   ]
   ```

### Multiple Lambda Functions

Use different Lambda functions for different job types:

```python
@dg.job(tags={"lambda/function_name": "etl-handler"})
def etl_job():
    pass

@dg.job(tags={"lambda/function_name": "reporting-handler"})
def reporting_job():
    pass
```

### Routing Logic in Lambda

Implement routing in your Lambda handler:

```python
def lambda_handler(event, context):
    job_name = event['dagster_run']['job_name']

    if job_name == 'etl_job':
        return handle_etl(event)
    elif job_name == 'reporting_job':
        return handle_reporting(event)
```

### Callback Mechanism (Future)

For async invocations, implement callbacks:

```python
# In Lambda
def report_status_to_dagster(run_id, status):
    # Call Dagster Cloud API to update run status
    pass
```

## Upgrading

To upgrade the agent:

1. Pull latest Dagster Cloud agent image:
   ```bash
   docker pull dagster/dagster-cloud-agent:latest
   ```

2. Rebuild custom image:
   ```bash
   cd infra
   ./build-and-push.sh
   ```

3. Update ECS service with new image:
   ```bash
   aws ecs update-service \
     --cluster your-cluster \
     --service dagster-lambda-agent \
     --force-new-deployment
   ```

## Contributing

Contributions welcome! Please:
- Follow existing code style
- Add tests for new features
- Update documentation
- Test with both sync and async invocations

## Support and Resources

- **Dagster Docs**: https://docs.dagster.io
- **AWS Lambda Docs**: https://docs.aws.amazon.com/lambda/
- **AWS ECS Docs**: https://docs.aws.amazon.com/ecs/
- **Project Issues**: [GitHub Issues](#)

## Related Projects

- [ACA Agent](https://github.com/eric-thomas-dagster/aca-agent) - Azure Container Apps example
- [Dagster AWS](https://github.com/dagster-io/dagster/tree/master/python_modules/libraries/dagster-aws) - Official AWS integration

## License

This project follows Dagster's licensing.

## Version History

### 1.0.0 (2026-01-09)
- Initial release
- Custom agent extending Dagster+ base agent
- Lambda Run Launcher with sync/async support
- Complete ECS deployment setup
- Example Lambda handlers and Dagster jobs
- Comprehensive documentation

---

## Quick Reference

### Build and Deploy
```bash
# Build Lambda agent image
cd infra && ./build-and-push.sh

# Deploy Lambda agent
aws ecs update-service --cluster xxx --service dagster-lambda-agent --force-new-deployment
```

### Configure Code Locations with Queues

**Create dagster_cloud.yaml in each code location**:

**lambda_jobs/dagster_cloud.yaml**:
```yaml
locations:
  - location_name: lambda_jobs
    code_source:
      package_name: lambda_jobs
    agent_queue: lambda  # Routes to Lambda agent
```

**python_jobs/dagster_cloud.yaml**:
```yaml
locations:
  - location_name: python_jobs
    code_source:
      package_name: python_jobs
    agent_queue: ecs  # Routes to ECS agent
```

**Lambda Job Example** (in `lambda_jobs` code location):
```python
@dg.job(tags={
    "lambda/function_name": "my-handler"
})
def lambda_job():
    my_op()
```

**ECS Job Example** (in `python_jobs` code location):
```python
@dg.job
def python_job():
    my_python_op()
```

**Note**: Queue routing is determined by `agent_queue` in dagster_cloud.yaml, not job tags.

### Agent Configuration

**Lambda Agent** (dagster.yaml):
```yaml
instance:
  agent:
    queues: [lambda]
  run_launcher:
    module: lambda_run_launcher
    class: LambdaRunLauncher
```

**ECS Agent** (separate dagster.yaml):
```yaml
instance:
  agent:
    queues: [ecs]
  run_launcher:
    module: dagster_aws.ecs
    class: EcsRunLauncher
```

### Payload Modes (Existing Lambda Functions)

```yaml
# Full payload (default - new Lambda functions)
payload_mode: 'full'

# Just run_config (existing Lambda expecting Dagster config)
payload_mode: 'config_only'

# Just ops config (existing Lambda processing ops)
payload_mode: 'ops_only'

# Extract specific path (existing Lambda with custom format)
payload_mode: 'custom'
payload_config_path: 'ops.my_op.config'
```

### View Logs
```bash
# Lambda agent logs
aws logs tail /ecs/dagster-lambda-agent --follow

# ECS agent logs
aws logs tail /ecs/dagster-ecs-agent --follow

# Lambda function logs
aws logs tail /aws/lambda/my-handler --follow
```

### Common Commands

```bash
# Check agent status in Dagster Cloud
# Go to: Deployment Settings > Agents

# Test Lambda invocation
aws lambda invoke --function-name my-handler response.json

# Monitor ECS services
aws ecs describe-services --cluster xxx --services dagster-lambda-agent dagster-ecs-agent
```
