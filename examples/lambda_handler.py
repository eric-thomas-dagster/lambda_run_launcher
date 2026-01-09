"""
Example Lambda Handler for Dagster Jobs

This is a simple example Lambda function that receives payloads from the
Dagster Lambda Run Launcher and processes them.

Deploy this function to AWS Lambda and configure your Dagster jobs to invoke it.
"""

import json
import logging
from typing import Any, Dict

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle Dagster run invocation.

    Args:
        event: Payload from Dagster Lambda Run Launcher containing:
            - dagster_run: Run metadata (run_id, job_name, etc.)
            - run_config: Job configuration
            - environment_variables: Environment context
            - dagster_cloud: Dagster Cloud info
            - metadata: Launcher metadata

        context: Lambda context object

    Returns:
        Response dictionary with status and result
    """
    logger.info("=" * 60)
    logger.info("Dagster Lambda Handler - Example")
    logger.info("=" * 60)

    try:
        # Extract run information
        dagster_run = event.get("dagster_run", {})
        run_id = dagster_run.get("run_id", "unknown")
        job_name = dagster_run.get("job_name", "unknown")
        deployment_name = dagster_run.get("deployment_name", "unknown")
        location_name = dagster_run.get("location_name", "unknown")

        logger.info(f"Run ID: {run_id}")
        logger.info(f"Job Name: {job_name}")
        logger.info(f"Deployment: {deployment_name}")
        logger.info(f"Location: {location_name}")

        # Extract run configuration
        run_config = event.get("run_config", {})
        logger.info(f"Run Config: {json.dumps(run_config, indent=2)}")

        # Extract environment variables
        env_vars = event.get("environment_variables", {})
        logger.info(f"Environment Variables: {list(env_vars.keys())}")

        # Extract Dagster Cloud info
        dagster_cloud = event.get("dagster_cloud", {})
        org_id = dagster_cloud.get("org_id")
        deployment_id = dagster_cloud.get("deployment_id")
        logger.info(f"Org ID: {org_id}")
        logger.info(f"Deployment ID: {deployment_id}")

        # Extract metadata
        metadata = event.get("metadata", {})
        launched_at = metadata.get("launched_at")
        launcher_version = metadata.get("launcher_version")
        logger.info(f"Launched At: {launched_at}")
        logger.info(f"Launcher Version: {launcher_version}")

        # ====================================================================
        # YOUR BUSINESS LOGIC HERE
        # ====================================================================

        # Example: Process configuration
        result = process_dagster_job(run_config, env_vars)

        # ====================================================================
        # End of business logic
        # ====================================================================

        logger.info("=" * 60)
        logger.info("Execution Complete")
        logger.info("=" * 60)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "run_id": run_id,
                "job_name": job_name,
                "status": "success",
                "result": result,
            }),
        }

    except Exception as e:
        logger.error(f"Error processing Dagster run: {str(e)}", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "run_id": event.get("dagster_run", {}).get("run_id", "unknown"),
                "status": "error",
                "error": str(e),
            }),
        }


def process_dagster_job(config: Dict[str, Any], env_vars: Dict[str, str]) -> Dict[str, Any]:
    """Process the Dagster job configuration.

    This is where you implement your actual business logic.

    Args:
        config: Job configuration from Dagster
        env_vars: Environment variables

    Returns:
        Result dictionary
    """
    logger.info("Processing Dagster job...")

    # Example: Extract op configs
    ops_config = config.get("ops", {})

    # Example: Process each op configuration
    results = {}
    for op_name, op_config in ops_config.items():
        logger.info(f"Processing op: {op_name}")
        logger.info(f"Op config: {json.dumps(op_config, indent=2)}")

        # Your logic here
        # For example, you might:
        # - Read data from S3
        # - Process data
        # - Write results back to S3 or a database
        # - Call other AWS services

        results[op_name] = {
            "status": "completed",
            "processed": True,
        }

    return {
        "ops_processed": len(ops_config),
        "results": results,
    }


# Example: More complex handler with different job types
def route_by_job_name(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Example handler that routes to different logic based on job name."""

    job_name = event.get("dagster_run", {}).get("job_name", "")

    if job_name == "etl_job":
        return handle_etl_job(event, context)
    elif job_name == "reporting_job":
        return handle_reporting_job(event, context)
    else:
        return lambda_handler(event, context)


def handle_etl_job(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle ETL-specific jobs."""
    logger.info("Handling ETL job...")
    # Your ETL logic here
    return {"statusCode": 200, "body": json.dumps({"status": "etl_complete"})}


def handle_reporting_job(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle reporting-specific jobs."""
    logger.info("Handling reporting job...")
    # Your reporting logic here
    return {"statusCode": 200, "body": json.dumps({"status": "report_generated"})}
