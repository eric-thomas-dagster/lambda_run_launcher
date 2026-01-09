"""
Example Existing Lambda Handler

This shows what an existing Lambda function might look like and how it would
receive payloads from the Dagster Lambda Run Launcher with different payload modes.
"""

import json
import logging
from typing import Any, Dict

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ============================================================================
# Example 1: Simple existing Lambda expecting flat config
# ============================================================================

def simple_existing_lambda(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Existing Lambda that expects a simple config dictionary.

    Expected payload:
    {
        "source_bucket": "my-bucket",
        "destination_bucket": "other-bucket",
        "file_pattern": "*.csv"
    }

    Use with Dagster agent configured with:
    - payload_mode: 'custom'
    - payload_config_path: 'ops.my_op.config'
    """
    logger.info("Simple existing Lambda handler")

    # Extract expected fields directly from event
    source_bucket = event.get("source_bucket")
    destination_bucket = event.get("destination_bucket")
    file_pattern = event.get("file_pattern")

    logger.info(f"Source: {source_bucket}")
    logger.info(f"Destination: {destination_bucket}")
    logger.info(f"Pattern: {file_pattern}")

    # Your existing business logic here
    result = process_files(source_bucket, destination_bucket, file_pattern)

    return {
        "statusCode": 200,
        "body": json.dumps(result)
    }


# ============================================================================
# Example 2: Existing Lambda expecting ops config structure
# ============================================================================

def ops_aware_lambda(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Existing Lambda that understands Dagster ops config structure.

    Expected payload (from payload_mode='ops_only'):
    {
        "my_op": {
            "config": {
                "param1": "value1",
                "param2": "value2"
            }
        }
    }
    """
    logger.info("Ops-aware Lambda handler")

    # Extract first op's config (common pattern for single-op jobs)
    ops_config = event
    logger.info(f"Received ops config: {json.dumps(ops_config, indent=2)}")

    results = {}
    for op_name, op_data in ops_config.items():
        logger.info(f"Processing op: {op_name}")
        config = op_data.get("config", {})

        # Process this op's config
        result = process_op_config(op_name, config)
        results[op_name] = result

    return {
        "statusCode": 200,
        "body": json.dumps(results)
    }


# ============================================================================
# Example 3: Existing Lambda expecting full run_config
# ============================================================================

def run_config_lambda(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Existing Lambda that works with Dagster's full run_config.

    Expected payload (from payload_mode='config_only'):
    {
        "ops": {
            "op1": {"config": {...}},
            "op2": {"config": {...}}
        },
        "resources": {...},
        "execution": {...}
    }
    """
    logger.info("Run config Lambda handler")

    # Extract ops configuration
    ops_config = event.get("ops", {})
    resources_config = event.get("resources", {})

    logger.info(f"Processing {len(ops_config)} ops")

    results = {}
    for op_name, op_data in ops_config.items():
        config = op_data.get("config", {})
        result = process_with_resources(op_name, config, resources_config)
        results[op_name] = result

    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "completed",
            "results": results
        })
    }


# ============================================================================
# Example 4: Migrated Lambda that can handle both formats
# ============================================================================

def adaptive_lambda(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda that can handle both old format and new Dagster format.

    This is useful during migration when you want backward compatibility.

    Handles:
    - Old format: {"source": "...", "destination": "..."}
    - Dagster ops_only: {"my_op": {"config": {...}}}
    - Dagster full: {"dagster_run": {...}, "run_config": {...}, ...}
    """
    logger.info("Adaptive Lambda handler")
    logger.info(f"Received event keys: {list(event.keys())}")

    # Detect format
    if "dagster_run" in event:
        # Full Dagster payload
        logger.info("Processing full Dagster payload")
        return handle_dagster_full_payload(event)

    elif any(isinstance(v, dict) and "config" in v for v in event.values()):
        # Looks like ops config
        logger.info("Processing Dagster ops config")
        return handle_dagster_ops_payload(event)

    else:
        # Legacy format
        logger.info("Processing legacy payload format")
        return handle_legacy_payload(event)


def handle_dagster_full_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle full Dagster payload."""
    dagster_run = event.get("dagster_run", {})
    run_config = event.get("run_config", {})

    run_id = dagster_run.get("run_id")
    job_name = dagster_run.get("job_name")

    logger.info(f"Processing Dagster run: {run_id} (job: {job_name})")

    # Extract ops config
    ops_config = run_config.get("ops", {})
    results = {}

    for op_name, op_data in ops_config.items():
        config = op_data.get("config", {})
        results[op_name] = process_op_config(op_name, config)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "run_id": run_id,
            "status": "completed",
            "results": results
        })
    }


def handle_dagster_ops_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle Dagster ops-only payload."""
    results = {}

    for op_name, op_data in event.items():
        config = op_data.get("config", {})
        results[op_name] = process_op_config(op_name, config)

    return {
        "statusCode": 200,
        "body": json.dumps({"status": "completed", "results": results})
    }


def handle_legacy_payload(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle legacy payload format."""
    # Your existing business logic unchanged
    source = event.get("source")
    destination = event.get("destination")

    result = process_files(source, destination, "*")

    return {
        "statusCode": 200,
        "body": json.dumps(result)
    }


# ============================================================================
# Helper functions (your existing business logic)
# ============================================================================

def process_files(source: str, destination: str, pattern: str) -> Dict[str, Any]:
    """Your existing file processing logic."""
    logger.info(f"Processing files: {source} -> {destination} ({pattern})")

    # Your actual file processing code here
    files_processed = 42

    return {
        "files_processed": files_processed,
        "source": source,
        "destination": destination
    }


def process_op_config(op_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Process a single op's configuration."""
    logger.info(f"Processing op '{op_name}' with config: {config}")

    # Your processing logic here
    return {
        "op": op_name,
        "status": "processed",
        "config_keys": list(config.keys())
    }


def process_with_resources(
    op_name: str,
    config: Dict[str, Any],
    resources: Dict[str, Any]
) -> Dict[str, Any]:
    """Process with resource configuration."""
    logger.info(f"Processing op '{op_name}' with resources")

    # Your processing logic that uses resources
    return {
        "op": op_name,
        "status": "processed_with_resources",
        "resources_used": list(resources.keys())
    }


# ============================================================================
# Migration Strategy Example
# ============================================================================

"""
Migration Strategy for Existing Lambda Functions:

PHASE 1: No Changes Required (payload_mode='ops_only' or 'custom')
----------------------------------------------------------------------
- Keep existing Lambda code unchanged
- Configure Dagster agent with appropriate payload_mode
- Lambda receives only what it expects
- Works immediately with zero Lambda code changes

Example dagster.yaml:
  run_launcher:
    config:
      payload_mode: 'ops_only'  # or 'custom' with payload_config_path

PHASE 2: Optional Enhancement (payload_mode='config_only')
----------------------------------------------------------------------
- Optionally update Lambda to accept full run_config
- Enables multiple ops per job
- Still minimal changes to Lambda

PHASE 3: Full Integration (payload_mode='full')
----------------------------------------------------------------------
- Update Lambda to accept full Dagster payload
- Access run metadata, environment variables
- Full integration with Dagster Cloud
- Best for new Lambda functions

Backward Compatibility:
----------------------------------------------------------------------
Use the adaptive_lambda pattern above to support all formats during migration.
"""


# ============================================================================
# Real-World Example: Existing ETL Lambda
# ============================================================================

def real_world_etl_lambda(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Real example: Existing ETL Lambda that expects:
    {
        "input_table": "raw_data",
        "output_table": "processed_data",
        "date_range": {"start": "2024-01-01", "end": "2024-01-31"},
        "filters": ["status=active", "type=premium"]
    }

    Dagster job config:
    ```python
    @dg.op(config_schema={
        "input_table": str,
        "output_table": str,
        "date_range": dict,
        "filters": list
    })
    def etl_op(context):
        pass

    @dg.job(tags={"lambda/function_name": "existing-etl-lambda"})
    def etl_job():
        etl_op()
    ```

    Agent config:
    ```yaml
    payload_mode: 'custom'
    payload_config_path: 'ops.etl_op.config'
    ```

    Lambda receives exactly what it expects - no code changes needed!
    """
    logger.info("ETL Lambda handler (existing, unchanged)")

    # Extract parameters (your existing code)
    input_table = event.get("input_table")
    output_table = event.get("output_table")
    date_range = event.get("date_range", {})
    filters = event.get("filters", [])

    logger.info(f"ETL: {input_table} -> {output_table}")
    logger.info(f"Date range: {date_range}")
    logger.info(f"Filters: {filters}")

    # Your existing ETL logic here (unchanged!)
    records_processed = run_etl_pipeline(
        input_table, output_table, date_range, filters
    )

    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "success",
            "records_processed": records_processed
        })
    }


def run_etl_pipeline(input_table, output_table, date_range, filters):
    """Your existing ETL pipeline logic."""
    # Unchanged existing code
    return 1000  # records processed
