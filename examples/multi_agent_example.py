"""
Multi-Agent Example: Lambda and ECS Agents

This example demonstrates how to use multiple agents with different run launchers:
- Lambda Agent: For lightweight, config-driven, or existing Lambda functions
- ECS Agent: For Python code execution with dependencies

IMPORTANT: Queue routing is configured at the CODE LOCATION level in Dagster Cloud,
not via job tags.

Setup:
1. Deploy Lambda agent with queues: [lambda]
2. Deploy ECS agent with queues: [ecs]
3. In Dagster Cloud UI, create two code locations:
   - "lambda_jobs" → assign queue: "lambda" (contains jobs from this file)
   - "python_jobs" → assign queue: "ecs" (contains Python execution jobs)
4. All jobs in "lambda_jobs" location automatically route to Lambda agent
5. All jobs in "python_jobs" location automatically route to ECS agent

This file would be deployed as the "lambda_jobs" code location.
Create a separate file/location for "python_jobs" (ECS jobs).
"""

import dagster as dg


# ============================================================================
# Lambda Agent Jobs
# These would be in the "lambda_jobs" code location (queue: lambda)
# ============================================================================

@dg.op(config_schema={"api_endpoint": str, "api_key": str})
def call_api(context: dg.OpExecutionContext):
    """Lightweight API call - perfect for Lambda."""
    endpoint = context.op_config["api_endpoint"]
    context.log.info(f"Calling API: {endpoint}")
    # In Lambda, this would make the actual API call
    return {"status": "called", "endpoint": endpoint}


@dg.job(
    tags={
        "lambda/function_name": "api-caller",
        "lambda/invocation_type": "Event",
    }
)
def api_trigger_job():
    """Lightweight job that runs in Lambda.

    Routes to Lambda agent because this code location is assigned queue: lambda.
    """
    call_api()


@dg.op(config_schema={"source_bucket": str, "file_pattern": str})
def trigger_etl(context: dg.OpExecutionContext):
    """Trigger ETL by sending event - Lambda is perfect for this."""
    bucket = context.op_config["source_bucket"]
    context.log.info(f"Triggering ETL for {bucket}")
    return {"triggered": True}


@dg.job(
    tags={
        "lambda/function_name": "etl-trigger",
    }
)
def etl_trigger_job():
    """Job that triggers heavy processing - runs quickly in Lambda.

    Routes to Lambda agent because this code location is assigned queue: lambda.
    """
    trigger_etl()


# ============================================================================
# ECS Agent Jobs
# These would be in a SEPARATE "python_jobs" code location (queue: ecs)
# ============================================================================

@dg.op
def load_large_dataset(context: dg.OpExecutionContext):
    """Load and process large dataset - needs ECS resources."""
    context.log.info("Loading 10GB dataset...")
    # This would import pandas, load data, etc.
    # Requires Python environment with dependencies
    import pandas as pd

    # Simulate heavy processing
    df = pd.DataFrame({"data": range(1000000)})
    context.log.info(f"Loaded {len(df)} records")

    return {"records": len(df)}


@dg.op
def train_model(context: dg.OpExecutionContext, dataset: dict):
    """Train ML model - needs ECS compute and libraries."""
    context.log.info("Training model...")
    # This would use scikit-learn, pytorch, etc.
    # Requires Python environment with ML libraries

    records = dataset["records"]
    context.log.info(f"Training on {records} records")

    return {"model_id": "model-123", "accuracy": 0.95}


@dg.job
def ml_training_job():
    """Heavy ML job that needs ECS compute and Python libraries.

    Routes to ECS agent because "python_jobs" code location is assigned queue: ecs.
    """
    dataset = load_large_dataset()
    train_model(dataset)


@dg.op(config_schema={"query": str})
def run_complex_query(context: dg.OpExecutionContext):
    """Complex query that takes 20 minutes - needs ECS."""
    query = context.op_config["query"]
    context.log.info(f"Running long query: {query}")
    # This would run for > 15 minutes (Lambda's limit)
    # import time
    # time.sleep(1200)  # 20 minutes

    return {"rows": 1000000}


@dg.job
def long_running_job():
    """Job that exceeds Lambda's 15-minute limit.

    Routes to ECS agent because "python_jobs" code location is assigned queue: ecs.
    """
    run_complex_query()


# ============================================================================
# Mixed Workflow: Lambda Trigger → ECS Processing
# ============================================================================
# Note: These would be in SEPARATE code locations with different queues

@dg.op
def check_new_data(context: dg.OpExecutionContext):
    """Quick check for new data - runs in Lambda."""
    context.log.info("Checking for new data...")
    # Quick S3 list or database query
    return {"has_new_data": True, "file_count": 42}


@dg.job(tags={"lambda/function_name": "data-checker"})
def check_data_job():
    """Lightweight checker job in Lambda.

    In "lambda_jobs" code location (queue: lambda).
    """
    result = check_new_data()
    return result


@dg.op
def process_data(context: dg.OpExecutionContext):
    """Heavy data processing - runs in ECS."""
    context.log.info("Processing large dataset...")
    # Heavy pandas/spark processing
    return {"processed": 1000000}


@dg.job
def process_data_job():
    """Heavy processing job in ECS.

    Would be in "python_jobs" code location (queue: ecs).
    """
    process_data()


# In practice, you'd use sensors or schedules to chain these:
# 1. check_data_job runs every 5 minutes in Lambda (lambda_jobs location)
# 2. If new data found, trigger process_data_job in ECS (python_jobs location)


# ============================================================================
# Configuration-Driven Lambda Jobs (Existing Functions)
# ============================================================================

@dg.op(
    config_schema={
        "source_bucket": str,
        "destination_bucket": str,
        "file_pattern": str,
    }
)
def copy_files(context: dg.OpExecutionContext):
    """Copy files using existing Lambda function."""
    context.log.info("Invoking S3 copy Lambda...")
    return {"status": "copied"}


# Using existing Lambda with custom payload mode
@dg.job(
    tags={
        "lambda/function_name": "existing-s3-copy",
    }
)
def s3_copy_job():
    """Uses existing Lambda function (no code changes needed).

    In "lambda_jobs" code location (queue: lambda).
    """
    copy_files()


# ============================================================================
# Asset Examples with Mixed Execution
# ============================================================================
# Note: Assets in different code locations execute on different agents
# - Assets in "lambda_jobs" location → Lambda agent
# - Assets in "python_jobs" location → ECS agent

@dg.asset(compute_kind="lambda")
def api_data(context: dg.AssetExecutionContext) -> dict:
    """Fetch data from API - quick Lambda job.

    In "lambda_jobs" code location (queue: lambda).
    """
    context.log.info("Fetching API data...")
    return {"records": [{"id": 1}, {"id": 2}]}


@dg.asset(
    compute_kind="python",
    deps=[api_data],
)
def processed_api_data(context: dg.AssetExecutionContext, api_data: dict) -> dict:
    """Process API data with Python libraries - ECS job.

    Would be in "python_jobs" code location (queue: ecs).
    """
    context.log.info("Processing with pandas...")
    # Heavy processing with Python libraries
    import pandas as pd
    df = pd.DataFrame(api_data["records"])
    return {"processed_count": len(df)}


@dg.asset(
    compute_kind="lambda",
    deps=[processed_api_data],
)
def notification(context: dg.AssetExecutionContext, processed_api_data: dict) -> dict:
    """Send notification - quick Lambda job.

    In "lambda_jobs" code location (queue: lambda).
    """
    count = processed_api_data["processed_count"]
    context.log.info(f"Sending notification for {count} records...")
    return {"notified": True}


# Asset job definitions
# These would be defined in their respective code locations
lambda_assets = [api_data, notification]
ecs_assets = [processed_api_data]

api_data_job = dg.define_asset_job(
    "api_data_job",
    selection=lambda_assets,
    tags={"lambda/function_name": "asset-processor"},
)

processing_job = dg.define_asset_job(
    "processing_job",
    selection=ecs_assets,
)


# ============================================================================
# Decision Guide: Lambda vs ECS Code Locations
# ============================================================================

"""
Put jobs in "lambda_jobs" code location (Lambda agent) when:
✓ Job is configuration-driven (no complex Python code)
✓ Using existing Lambda functions
✓ Job completes in < 15 minutes
✓ Memory needs < 10GB
✓ Minimal or no pip dependencies
✓ API calls, triggers, notifications
✓ Cost optimization is important

Put jobs in "python_jobs" code location (ECS agent) when:
✓ Job executes Python code with dependencies
✓ Job takes > 15 minutes
✓ Job needs > 10GB memory
✓ Job requires custom packages (pandas, sklearn, etc.)
✓ Job needs GPU or specialized hardware
✓ Stateful computation
✓ Complex data processing

Examples:

Lambda Agent:
- Trigger jobs (send SQS message, call API)
- Simple transformations (JSON parsing, filtering)
- Existing Lambda function orchestration
- Event-driven workflows
- Data validation checks

ECS Agent:
- ML model training
- Large dataset processing (pandas, spark)
- Long-running queries (>15 min)
- Complex transformations with dependencies
- Jobs requiring specific Python versions
"""


# ============================================================================
# Common Patterns
# ============================================================================

# Pattern 1: Separate code locations for different agent types
"""
Project Structure:
  lambda_jobs/          # Code location with queue: lambda
    ├── __init__.py
    └── jobs.py         # Lightweight, config-driven jobs

  python_jobs/          # Code location with queue: ecs
    ├── __init__.py
    └── jobs.py         # Python code execution jobs

All jobs in lambda_jobs automatically route to Lambda agent.
All jobs in python_jobs automatically route to ECS agent.
"""

# Pattern 2: Lambda for orchestration, ECS for processing
"""
lambda_jobs location: check_data_job → checks for new data
python_jobs location: process_data_job → heavy processing

Use sensors/schedules to trigger cross-location workflows.
"""

# Pattern 3: Mixed asset pipeline across locations
"""
lambda_jobs: api_data asset → Fetch data (quick)
python_jobs: processed_api_data asset → Process (heavy)
lambda_jobs: notification asset → Send alert (quick)

Cross-location asset dependencies work seamlessly.
"""

# Pattern 4: Existing Lambda orchestration
"""
lambda_jobs location with payload_mode='custom' to invoke existing
Lambda functions without modifying their code.
Example: s3_copy_job using existing-s3-copy Lambda
"""

# Pattern 5: Cost optimization
"""
lambda_jobs location: 80% of lightweight jobs → $1-2/month
python_jobs location: 20% of heavy jobs → only pay when running
Result: 30-50% cost savings vs all-ECS setup
"""


# ============================================================================
# Definitions
# ============================================================================

defs = dg.Definitions(
    jobs=[
        # Lambda agent jobs
        api_trigger_job,
        etl_trigger_job,
        check_data_job,
        s3_copy_job,

        # ECS agent jobs
        ml_training_job,
        long_running_job,
        process_data_job,

        # Asset jobs (mixed)
        api_data_job,
        processing_job,
    ],
    assets=[
        api_data,
        processed_api_data,
        notification,
    ],
)
