"""
Lambda Function Component for Dagster

A custom component that allows users to define Lambda-backed assets, ops,
and jobs purely in YAML configuration.

Based on: https://docs.dagster.io/guides/build/components/creating-new-components/component-customization

Usage:
    1. Copy this file to your Dagster project
    2. Create component YAML files (see examples below)
    3. Load components using dg.Definitions.from_yaml()
"""

from typing import Any, Dict, List, Optional

import dagster as dg
from dagster import AssetExecutionContext, OpExecutionContext
from pydantic import BaseModel, Field


# ============================================================================
# Component Parameter Models
# ============================================================================


class LambdaConfig(BaseModel):
    """Configuration for Lambda function invocation."""

    function_name: str = Field(
        description="Lambda function name or ARN to invoke"
    )
    invocation_type: str = Field(
        default="Event",
        description="Invocation type: 'Event' (async) or 'RequestResponse' (sync)",
    )
    payload_mode: str = Field(
        default="full",
        description="Payload mode: 'full', 'config_only', 'ops_only', or 'custom'",
    )
    payload_config_path: Optional[str] = Field(
        default=None,
        description="Config path for custom payload mode (e.g., 'ops.my_op.config')",
    )


class OpConfig(BaseModel):
    """Configuration for an op."""

    name: str = Field(description="Op name")
    config_schema: Optional[Dict[str, Any]] = Field(
        default=None, description="Op config schema"
    )
    description: Optional[str] = Field(default=None, description="Op description")


class AssetConfig(BaseModel):
    """Configuration for an asset."""

    key: str = Field(description="Asset key")
    deps: Optional[List[str]] = Field(
        default=None, description="Upstream asset dependencies"
    )
    config_schema: Optional[Dict[str, Any]] = Field(
        default=None, description="Asset config schema"
    )
    description: Optional[str] = Field(default=None, description="Asset description")
    group_name: Optional[str] = Field(default=None, description="Asset group name")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description="Asset metadata"
    )
    partitions_def: Optional[str] = Field(
        default=None,
        description="Partitions definition type: 'daily', 'weekly', 'monthly', 'static'",
    )
    partition_keys: Optional[List[str]] = Field(
        default=None, description="Static partition keys (if partitions_def='static')"
    )


class ScheduleConfig(BaseModel):
    """Configuration for a schedule."""

    cron_schedule: str = Field(description="Cron schedule expression")
    execution_timezone: Optional[str] = Field(
        default="UTC", description="Execution timezone"
    )


class LambdaFunctionParams(BaseModel):
    """Parameters for Lambda Function Component."""

    # Lambda configuration
    lambda_config: LambdaConfig = Field(
        description="Lambda function configuration"
    )

    # Asset or Op configuration (mutually exclusive)
    asset: Optional[AssetConfig] = Field(
        default=None,
        description="Asset configuration (creates a @dg.asset)",
    )
    ops: Optional[List[OpConfig]] = Field(
        default=None,
        description="Op configurations (creates ops in a job)",
    )

    # Job configuration (only used if ops are defined)
    job_name: Optional[str] = Field(
        default=None,
        description="Job name (required if ops are defined)",
    )
    job_description: Optional[str] = Field(
        default=None, description="Job description"
    )

    # Schedule configuration
    schedule: Optional[ScheduleConfig] = Field(
        default=None, description="Schedule configuration"
    )


# ============================================================================
# Lambda Function Component
# ============================================================================


class LambdaFunctionComponent(dg.Component):
    """
    A component that creates Lambda-backed Dagster assets or jobs.

    Supports:
    - Single Lambda function as an asset
    - Multiple ops in a job calling Lambda functions
    - Schedules
    - Asset dependencies
    - Partitions
    - All Lambda run launcher tags
    """

    params_schema = LambdaFunctionParams

    def build_defs(self, context: dg.ComponentLoadContext) -> dg.Definitions:
        """Build Dagster definitions from component parameters."""
        params: LambdaFunctionParams = context.params

        # Build tags for Lambda run launcher
        lambda_tags = {
            "lambda/function_name": params.lambda_config.function_name,
            "lambda/invocation_type": params.lambda_config.invocation_type,
            "lambda/payload_mode": params.lambda_config.payload_mode,
        }

        if params.lambda_config.payload_config_path:
            lambda_tags[
                "lambda/payload_config_path"
            ] = params.lambda_config.payload_config_path

        # Case 1: Asset-based component
        if params.asset:
            return self._build_asset_defs(params, lambda_tags)

        # Case 2: Job-based component (with ops)
        elif params.ops:
            return self._build_job_defs(params, lambda_tags)

        else:
            raise ValueError(
                "Component must define either 'asset' or 'ops' configuration"
            )

    def _build_asset_defs(
        self, params: LambdaFunctionParams, lambda_tags: Dict[str, str]
    ) -> dg.Definitions:
        """Build definitions for asset-based component."""
        asset_config = params.asset

        # Parse dependencies
        deps = None
        if asset_config.deps:
            deps = [dg.AssetKey(dep) for dep in asset_config.deps]

        # Parse partitions
        partitions_def = None
        if asset_config.partitions_def:
            if asset_config.partitions_def == "daily":
                partitions_def = dg.DailyPartitionsDefinition(start_date="2024-01-01")
            elif asset_config.partitions_def == "weekly":
                partitions_def = dg.WeeklyPartitionsDefinition(
                    start_date="2024-01-01"
                )
            elif asset_config.partitions_def == "monthly":
                partitions_def = dg.MonthlyPartitionsDefinition(
                    start_date="2024-01-01"
                )
            elif asset_config.partitions_def == "static" and asset_config.partition_keys:
                partitions_def = dg.StaticPartitionsDefinition(
                    asset_config.partition_keys
                )

        # Create asset function
        @dg.asset(
            key=dg.AssetKey(asset_config.key),
            deps=deps,
            config_schema=asset_config.config_schema,
            description=asset_config.description,
            group_name=asset_config.group_name,
            metadata=asset_config.metadata,
            partitions_def=partitions_def,
            tags=lambda_tags,
        )
        def lambda_asset(context: AssetExecutionContext):
            """Asset backed by Lambda function invocation."""
            config = context.op_execution_context.op_config

            # Log invocation details
            context.log.info(
                f"Invoking Lambda: {params.lambda_config.function_name}"
            )
            context.log.info(f"Invocation type: {params.lambda_config.invocation_type}")
            context.log.info(f"Payload mode: {params.lambda_config.payload_mode}")

            if config:
                context.log.info(f"Config: {config}")

            # The Lambda run launcher will handle the actual invocation
            # This asset just needs to complete successfully
            return {
                "lambda_function": params.lambda_config.function_name,
                "invocation_type": params.lambda_config.invocation_type,
                "status": "invoked",
            }

        assets = [lambda_asset]

        # Create schedule if configured
        schedules = []
        if params.schedule:
            schedule = dg.ScheduleDefinition(
                name=f"{asset_config.key}_schedule",
                target=dg.AssetSelection.keys(asset_config.key),
                cron_schedule=params.schedule.cron_schedule,
                execution_timezone=params.schedule.execution_timezone,
            )
            schedules.append(schedule)

        return dg.Definitions(assets=assets, schedules=schedules)

    def _build_job_defs(
        self, params: LambdaFunctionParams, lambda_tags: Dict[str, str]
    ) -> dg.Definitions:
        """Build definitions for job-based component."""
        if not params.job_name:
            raise ValueError("job_name is required when ops are defined")

        # Create ops
        ops_list = []
        for op_config in params.ops:

            @dg.op(
                name=op_config.name,
                config_schema=op_config.config_schema,
                description=op_config.description,
            )
            def lambda_op(context: OpExecutionContext):
                """Op backed by Lambda function invocation."""
                config = context.op_config

                # Log invocation details
                context.log.info(
                    f"Invoking Lambda: {params.lambda_config.function_name}"
                )
                context.log.info(
                    f"Invocation type: {params.lambda_config.invocation_type}"
                )
                context.log.info(f"Payload mode: {params.lambda_config.payload_mode}")

                if config:
                    context.log.info(f"Op config: {config}")

                # The Lambda run launcher will handle the actual invocation
                return {
                    "lambda_function": params.lambda_config.function_name,
                    "op_name": context.op.name,
                    "status": "completed",
                }

            ops_list.append(lambda_op)

        # Create job
        @dg.job(
            name=params.job_name,
            description=params.job_description,
            tags=lambda_tags,
        )
        def lambda_job():
            """Job containing Lambda-backed ops."""
            # Execute ops in sequence
            for op_fn in ops_list:
                op_fn()

        jobs = [lambda_job]

        # Create schedule if configured
        schedules = []
        if params.schedule:
            schedule = dg.ScheduleDefinition(
                name=f"{params.job_name}_schedule",
                job=lambda_job,
                cron_schedule=params.schedule.cron_schedule,
                execution_timezone=params.schedule.execution_timezone,
            )
            schedules.append(schedule)

        return dg.Definitions(jobs=jobs, schedules=schedules)


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    print("Lambda Function Component")
    print("=" * 80)
    print()
    print("This component allows you to define Lambda-backed assets and jobs")
    print("purely in YAML configuration.")
    print()
    print("See example YAML files:")
    print("  - lambda_asset_example.yaml")
    print("  - lambda_job_example.yaml")
    print("  - lambda_with_schedule_example.yaml")
    print()
