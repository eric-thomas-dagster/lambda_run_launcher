"""
Example Dagster Job Using Lambda Run Launcher

This example shows how to define Dagster jobs that will be executed
by invoking AWS Lambda functions.
"""

import dagster as dg


# ============================================================================
# Example 1: Simple job with async Lambda invocation
# ============================================================================

@dg.op(config_schema={"message": str})
def async_op(context: dg.OpExecutionContext):
    """Example op that will be executed by Lambda asynchronously."""
    message = context.op_config["message"]
    context.log.info(f"Message: {message}")
    return {"status": "processed", "message": message}


@dg.job(
    tags={
        "lambda/function_name": "dagster-example-handler",
        "lambda/invocation_type": "Event",  # Async
    }
)
def async_lambda_job():
    """Job that invokes Lambda asynchronously (fire and forget)."""
    async_op()


# ============================================================================
# Example 2: Job with sync Lambda invocation
# ============================================================================

@dg.op(
    config_schema={
        "input_data": str,
        "processing_mode": str,
    }
)
def sync_op(context: dg.OpExecutionContext):
    """Example op that will be executed by Lambda synchronously."""
    input_data = context.op_config["input_data"]
    mode = context.op_config["processing_mode"]

    context.log.info(f"Processing {input_data} in {mode} mode")

    return {"result": "completed"}


@dg.job(
    tags={
        "lambda/function_name": "dagster-sync-handler",
        "lambda/invocation_type": "RequestResponse",  # Sync
    }
)
def sync_lambda_job():
    """Job that invokes Lambda synchronously and waits for response."""
    sync_op()


# ============================================================================
# Example 3: Job with Lambda ARN
# ============================================================================

@dg.op
def arn_based_op(context: dg.OpExecutionContext):
    """Example op using full Lambda ARN."""
    context.log.info("Executing with Lambda ARN")
    return {"status": "success"}


@dg.job(
    tags={
        "lambda/function_arn": "arn:aws:lambda:us-east-1:123456789012:function:my-dagster-handler",
        "lambda/invocation_type": "Event",
    }
)
def arn_lambda_job():
    """Job that uses full Lambda ARN."""
    arn_based_op()


# ============================================================================
# Example 4: Asset with Lambda execution
# ============================================================================

@dg.asset(
    compute_kind="lambda",
    metadata={
        "lambda_function": "dagster-asset-processor",
    },
)
def processed_data(context: dg.AssetExecutionContext) -> dict:
    """Asset that will be processed by Lambda."""
    context.log.info("Processing asset via Lambda")
    return {"records_processed": 1000}


# Define asset job with Lambda tags
lambda_asset_job = dg.define_asset_job(
    "lambda_asset_job",
    selection="processed_data",
    tags={
        "lambda/function_name": "dagster-asset-processor",
        "lambda/invocation_type": "Event",
    },
)


# ============================================================================
# Example 5: Configurable job (function name in config)
# ============================================================================

@dg.op
def configurable_op(context: dg.OpExecutionContext):
    """Op for configurable job."""
    context.log.info("Running configurable job")
    return {"status": "done"}


@dg.job(
    config={
        "execution": {
            "config": {
                "lambda_function": "dagster-configurable-handler",
                "invocation_type": "Event",
            }
        }
    }
)
def configurable_lambda_job():
    """Job where Lambda function is specified in config."""
    configurable_op()


# ============================================================================
# Example 6: Multi-op job
# ============================================================================

@dg.op(config_schema={"input_path": str})
def extract(context: dg.OpExecutionContext):
    """Extract data."""
    input_path = context.op_config["input_path"]
    context.log.info(f"Extracting from {input_path}")
    return {"data": ["record1", "record2", "record3"]}


@dg.op
def transform(context: dg.OpExecutionContext, data: dict):
    """Transform data."""
    records = data["data"]
    context.log.info(f"Transforming {len(records)} records")
    return {"transformed": [r.upper() for r in records]}


@dg.op(config_schema={"output_path": str})
def load(context: dg.OpExecutionContext, transformed: dict):
    """Load data."""
    output_path = context.op_config["output_path"]
    data = transformed["transformed"]
    context.log.info(f"Loading {len(data)} records to {output_path}")
    return {"loaded": len(data)}


@dg.job(
    tags={
        "lambda/function_name": "dagster-etl-handler",
        "lambda/invocation_type": "Event",
    }
)
def etl_lambda_job():
    """ETL job executed by Lambda."""
    extracted = extract()
    transformed = transform(extracted)
    load(transformed)


# ============================================================================
# Definitions
# ============================================================================

defs = dg.Definitions(
    jobs=[
        async_lambda_job,
        sync_lambda_job,
        arn_lambda_job,
        configurable_lambda_job,
        etl_lambda_job,
    ],
    assets=[processed_data],
)
