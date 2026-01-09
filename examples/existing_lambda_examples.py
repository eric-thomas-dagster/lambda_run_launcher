"""
Examples of Using Existing Lambda Functions

This file demonstrates how to use existing Lambda functions that already have
their own expected payload format, without requiring changes to the Lambda code.

The Lambda Run Launcher supports multiple payload modes to accommodate existing
Lambda functions.
"""

import dagster as dg


# ============================================================================
# Example 1: Existing Lambda expecting simple config dictionary
# ============================================================================

# Suppose you have an existing Lambda function that expects:
# {
#   "source_bucket": "...",
#   "destination_bucket": "...",
#   "file_pattern": "..."
# }

@dg.op(
    config_schema={
        "source_bucket": str,
        "destination_bucket": str,
        "file_pattern": str,
    }
)
def copy_files_op(context: dg.OpExecutionContext):
    """Op that invokes existing S3 copy Lambda."""
    config = context.op_config
    context.log.info(f"Copying files from {config['source_bucket']}")
    return {"status": "initiated"}


# Configure agent with payload_mode='ops_only' to send just the op config
# dagster.yaml:
#   run_launcher:
#     config:
#       payload_mode: 'ops_only'

@dg.job(tags={"lambda/function_name": "existing-s3-copy-function"})
def copy_files_job():
    """Job using existing Lambda function with ops_only mode."""
    copy_files_op()


# The Lambda receives:
# {
#   "copy_files_op": {
#     "config": {
#       "source_bucket": "my-bucket",
#       "destination_bucket": "other-bucket",
#       "file_pattern": "*.csv"
#     }
#   }
# }


# ============================================================================
# Example 2: Existing Lambda expecting just config values
# ============================================================================

# If your Lambda expects a flat config like:
# {"api_key": "...", "endpoint": "...", "data": [...]}

@dg.op(
    config_schema={
        "api_key": str,
        "endpoint": str,
        "data": list,
    }
)
def api_call_op(context: dg.OpExecutionContext):
    """Op that invokes existing API Lambda."""
    config = context.op_config
    context.log.info(f"Calling API at {config['endpoint']}")
    return {"status": "called"}


# Configure agent with payload_mode='custom' to extract specific config
# dagster.yaml:
#   run_launcher:
#     config:
#       payload_mode: 'custom'
#       payload_config_path: 'ops.api_call_op.config'

@dg.job(tags={"lambda/function_name": "existing-api-caller"})
def api_call_job():
    """Job using existing Lambda with custom path extraction."""
    api_call_op()


# The Lambda receives exactly:
# {
#   "api_key": "...",
#   "endpoint": "...",
#   "data": [...]
# }


# ============================================================================
# Example 3: Existing Lambda expecting full run_config
# ============================================================================

# If your Lambda function is already designed to work with Dagster's run_config

@dg.op(config_schema={"input_file": str, "output_file": str})
def transform_op(context: dg.OpExecutionContext):
    """Op for data transformation."""
    context.log.info("Transforming data")
    return {"transformed": True}


@dg.op(config_schema={"destination": str})
def load_op(context: dg.OpExecutionContext):
    """Op for loading data."""
    context.log.info("Loading data")
    return {"loaded": True}


# Configure agent with payload_mode='config_only'
# dagster.yaml:
#   run_launcher:
#     config:
#       payload_mode: 'config_only'

@dg.job(tags={"lambda/function_name": "existing-etl-function"})
def etl_job():
    """Job using existing Lambda expecting run_config."""
    transform_op()
    load_op()


# The Lambda receives:
# {
#   "ops": {
#     "transform_op": {
#       "config": {"input_file": "...", "output_file": "..."}
#     },
#     "load_op": {
#       "config": {"destination": "..."}
#     }
#   }
# }


# ============================================================================
# Example 4: Per-job payload mode override
# ============================================================================

# You can also set payload mode per-job using tags

@dg.op(config_schema={"message": str})
def legacy_op(context: dg.OpExecutionContext):
    """Op for legacy Lambda."""
    return {"sent": True}


@dg.job(
    tags={
        "lambda/function_name": "legacy-function",
        "lambda/payload_mode": "ops_only",  # Override global payload_mode
    }
)
def legacy_job():
    """Job that overrides payload mode for specific Lambda."""
    legacy_op()


# ============================================================================
# Example 5: Multiple Lambda functions with different formats
# ============================================================================

# You might have different Lambda functions expecting different formats

@dg.op(config_schema={"old_format": dict})
def legacy_processing(context: dg.OpExecutionContext):
    """Uses old Lambda expecting ops_only."""
    return {"status": "legacy_done"}


@dg.op(config_schema={"new_format": dict})
def modern_processing(context: dg.OpExecutionContext):
    """Uses new Lambda expecting full payload."""
    return {"status": "modern_done"}


# For this scenario, use different deployments or configure per-job
# Or deploy multiple agents with different configurations

@dg.job(
    tags={
        "lambda/function_name": "legacy-processor",
        # This would use agent's global payload_mode
    }
)
def mixed_legacy_job():
    """Uses legacy Lambda function."""
    legacy_processing()


@dg.job(
    tags={
        "lambda/function_name": "modern-processor",
        # This would use agent's global payload_mode
    }
)
def mixed_modern_job():
    """Uses modern Lambda function."""
    modern_processing()


# ============================================================================
# Example 6: Gradual migration approach
# ============================================================================

# When migrating from existing Lambda functions to Dagster orchestration,
# you can start with 'ops_only' or 'config_only' mode, then gradually
# update Lambda functions to accept the 'full' payload for richer metadata

@dg.op(config_schema={"input_data": str})
def migration_step_1(context: dg.OpExecutionContext):
    """Initial migration: Lambda unchanged, uses ops_only mode."""
    return {"migrated": "step1"}


# Step 1: Deploy with payload_mode='ops_only'
# Step 2: Lambda function continues working unchanged
# Step 3: Gradually update Lambda to accept full payload
# Step 4: Switch to payload_mode='full' for richer context


# ============================================================================
# Configuration Examples
# ============================================================================

"""
# dagster.yaml for existing Lambda functions expecting ops config:

instance:
  run_launcher:
    module: app.lambda_run_launcher
    class: LambdaRunLauncher
    config:
      payload_mode: 'ops_only'
      default_function_name: 'existing-lambda-function'
      region_name: 'us-east-1'

---

# dagster.yaml for extracting specific config path:

instance:
  run_launcher:
    module: app.lambda_run_launcher
    class: LambdaRunLauncher
    config:
      payload_mode: 'custom'
      payload_config_path: 'ops.my_op.config'
      default_function_name: 'existing-lambda-function'
      region_name: 'us-east-1'

---

# dagster.yaml for full run_config:

instance:
  run_launcher:
    module: app.lambda_run_launcher
    class: LambdaRunLauncher
    config:
      payload_mode: 'config_only'
      default_function_name: 'existing-lambda-function'
      region_name: 'us-east-1'

---

# dagster.yaml for new Lambda functions (full metadata):

instance:
  run_launcher:
    module: app.lambda_run_launcher
    class: LambdaRunLauncher
    config:
      payload_mode: 'full'  # Default
      default_function_name: 'new-lambda-function'
      region_name: 'us-east-1'
"""


# ============================================================================
# Definitions
# ============================================================================

defs = dg.Definitions(
    jobs=[
        copy_files_job,
        api_call_job,
        etl_job,
        legacy_job,
        mixed_legacy_job,
        mixed_modern_job,
    ],
)
