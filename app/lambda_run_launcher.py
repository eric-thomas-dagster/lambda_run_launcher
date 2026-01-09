"""Lambda Run Launcher for Dagster

A custom run launcher that invokes AWS Lambda functions for Dagster job execution.
Supports both synchronous (RequestResponse) and asynchronous (Event) invocations.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from dagster import (
    Field,
    Noneable,
    Permissive,
    StringSource,
)
from dagster._core.errors import DagsterLaunchFailedError
from dagster._core.launcher import LaunchRunContext, RunLauncher


# Lambda payload size limit (256KB)
LAMBDA_PAYLOAD_SIZE_LIMIT = 256000
LAMBDA_PAYLOAD_WARNING_THRESHOLD = 230000  # Warn at 90% of limit

# Version for metadata tracking
LAUNCHER_VERSION = "1.0.0"


class LambdaRunLauncher(RunLauncher):
    """RunLauncher that invokes AWS Lambda functions for each Dagster job run.

    This launcher supports both synchronous (RequestResponse) and asynchronous (Event)
    Lambda invocations. The Lambda function to invoke and invocation type can be
    specified per-job via tags or run configuration, with fallbacks to global defaults.

    Configuration:
        default_function_name (Optional[str]): Default Lambda function name/ARN if not
            specified per-job.
        default_invocation_type (str): Default invocation type ('Event' or 'RequestResponse').
            Defaults to 'Event'.
        region_name (str): AWS region name. Defaults to 'us-east-1'.
        env_vars (Optional[List[str]]): List of environment variable names to include
            in the Lambda payload.
        sync_timeout (int): Timeout in seconds for synchronous invocations. Defaults to 300.
        invoke_kwargs (Optional[Dict]): Additional keyword arguments to pass to
            boto3 Lambda.invoke().

    Example configuration in dagster.yaml:
        run_launcher:
          module: 'lambda_run_launcher'
          class: 'LambdaRunLauncher'
          config:
            default_function_name: 'dagster-default-runner'
            default_invocation_type: 'Event'
            region_name: 'us-east-1'
            env_vars:
              - DAGSTER_CLOUD_ORG_ID
              - DAGSTER_CLOUD_DEPLOYMENT_ID
            sync_timeout: 300
    """

    def __init__(
        self,
        default_function_name: Optional[str] = None,
        default_invocation_type: str = "Event",
        region_name: str = "us-east-1",
        env_vars: Optional[List[str]] = None,
        sync_timeout: int = 300,
        invoke_kwargs: Optional[Dict[str, Any]] = None,
        payload_mode: str = "full",
        payload_config_path: Optional[str] = None,
        inst_data: Optional[Any] = None,
    ):
        """Initialize the Lambda run launcher.

        Args:
            default_function_name: Default Lambda function name/ARN
            default_invocation_type: Default invocation type ('Event' or 'RequestResponse')
            region_name: AWS region name
            env_vars: List of environment variable names to pass to Lambda
            sync_timeout: Timeout for synchronous invocations (seconds)
            invoke_kwargs: Additional boto3 invoke parameters
            payload_mode: Payload format mode ('full', 'config_only', 'ops_only', 'custom')
            payload_config_path: JSONPath for extracting payload in 'custom' mode (e.g., 'ops.my_op.config')
            inst_data: Dagster instance data (used by ConfigurableClass)
        """
        self._default_function_name = default_function_name
        self._default_invocation_type = default_invocation_type
        self._region_name = region_name
        self._env_vars = env_vars or []
        self._sync_timeout = sync_timeout
        self._invoke_kwargs = invoke_kwargs or {}
        self._payload_mode = payload_mode
        self._payload_config_path = payload_config_path
        self._inst_data = inst_data

        # Validate invocation type
        if default_invocation_type not in ["Event", "RequestResponse"]:
            raise ValueError(
                f"Invalid default_invocation_type: {default_invocation_type}. "
                f"Must be 'Event' or 'RequestResponse'."
            )

        # Validate payload mode
        valid_modes = ["full", "config_only", "ops_only", "custom"]
        if payload_mode not in valid_modes:
            raise ValueError(
                f"Invalid payload_mode: {payload_mode}. "
                f"Must be one of: {', '.join(valid_modes)}"
            )

        # Validate custom mode has config path
        if payload_mode == "custom" and not payload_config_path:
            raise ValueError(
                "payload_config_path is required when payload_mode is 'custom'"
            )

        # Initialize boto3 Lambda client
        self._lambda_client = boto3.client("lambda", region_name=region_name)

        super().__init__()

    @classmethod
    def config_type(cls):
        """Return the configuration schema for this launcher."""
        return {
            "default_function_name": Field(
                Noneable(StringSource),
                is_required=False,
                description="Default Lambda function name or ARN if not specified per-job",
            ),
            "default_invocation_type": Field(
                str,
                is_required=False,
                default_value="Event",
                description="Default invocation type: 'Event' (async) or 'RequestResponse' (sync)",
            ),
            "region_name": Field(
                str,
                is_required=False,
                default_value="us-east-1",
                description="AWS region name",
            ),
            "env_vars": Field(
                Noneable([str]),
                is_required=False,
                description="List of environment variable names to pass to Lambda",
            ),
            "sync_timeout": Field(
                int,
                is_required=False,
                default_value=300,
                description="Timeout in seconds for synchronous invocations",
            ),
            "invoke_kwargs": Field(
                Noneable(Permissive()),
                is_required=False,
                description="Additional keyword arguments for boto3 Lambda.invoke()",
            ),
            "payload_mode": Field(
                str,
                is_required=False,
                default_value="full",
                description=(
                    "Payload format mode:\n"
                    "- 'full': Complete payload with run metadata, config, env vars (default)\n"
                    "- 'config_only': Just the run_config dictionary\n"
                    "- 'ops_only': Just the ops config from run_config.ops\n"
                    "- 'custom': Extract specific path from run_config using payload_config_path"
                ),
            ),
            "payload_config_path": Field(
                Noneable(str),
                is_required=False,
                description=(
                    "Dot-notation path to extract from run_config in 'custom' mode\n"
                    "Examples: 'ops.my_op.config', 'resources.database.config'"
                ),
            ),
        }

    @classmethod
    def from_config_value(cls, inst_data, config_value):
        """Create launcher instance from configuration."""
        return cls(inst_data=inst_data, **config_value)

    @property
    def inst_data(self):
        """Return instance data."""
        return self._inst_data

    @inst_data.setter
    def inst_data(self, val):
        """Set instance data."""
        self._inst_data = val

    def launch_run(self, context: LaunchRunContext) -> None:
        """Launch a Dagster run by invoking a Lambda function.

        This method:
        1. Extracts the Lambda function identifier from tags/config
        2. Determines the invocation type (sync vs async)
        3. Builds a comprehensive payload with run metadata and configuration
        4. Validates payload size against Lambda limits
        5. Invokes the Lambda function via boto3
        6. Emits Dagster engine events for tracking
        7. Handles responses for synchronous invocations

        Args:
            context: Launch context containing run information

        Raises:
            DagsterLaunchFailedError: If Lambda invocation fails
        """
        run = context.dagster_run
        instance = context.instance

        try:
            # Step 1: Get Lambda function identifier
            function_id = self._get_lambda_function_identifier(context)
            if not function_id:
                raise DagsterLaunchFailedError(
                    f"No Lambda function specified for run {run.run_id}. "
                    f"Set 'lambda/function_name' tag or configure default_function_name."
                )

            # Step 2: Determine invocation type
            invocation_type = self._get_invocation_type(context)

            instance.report_engine_event(
                f"Preparing to invoke Lambda function '{function_id}' "
                f"with invocation type '{invocation_type}'",
                run,
            )

            # Step 3: Build payload
            payload = self._build_lambda_payload(context)

            # Step 4: Validate payload size
            payload_json = json.dumps(payload)
            payload_bytes = payload_json.encode("utf-8")
            payload_size = len(payload_bytes)

            if payload_size > LAMBDA_PAYLOAD_SIZE_LIMIT:
                raise DagsterLaunchFailedError(
                    f"Payload size ({payload_size} bytes) exceeds Lambda limit "
                    f"({LAMBDA_PAYLOAD_SIZE_LIMIT} bytes). "
                    f"Consider reducing run_config size or implementing S3 overflow."
                )

            if payload_size > LAMBDA_PAYLOAD_WARNING_THRESHOLD:
                instance.report_engine_event(
                    f"Warning: Payload size ({payload_size} bytes) is approaching "
                    f"Lambda limit ({LAMBDA_PAYLOAD_SIZE_LIMIT} bytes)",
                    run,
                )

            # Step 5: Invoke Lambda
            invoke_params = {
                "FunctionName": function_id,
                "InvocationType": invocation_type,
                "Payload": payload_bytes,
                **self._invoke_kwargs,
            }

            response = self._lambda_client.invoke(**invoke_params)

            # Step 6: Store invocation metadata in instance
            request_id = response.get("ResponseMetadata", {}).get("RequestId", "unknown")

            instance.report_engine_event(
                f"Successfully invoked Lambda function '{function_id}' "
                f"(type: {invocation_type}, request_id: {request_id}, "
                f"payload_size: {payload_size} bytes)",
                run,
            )

            # Step 7: Handle sync response if applicable
            if invocation_type == "RequestResponse":
                self._handle_sync_response(context, response, function_id)

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "ResourceNotFoundException":
                raise DagsterLaunchFailedError(
                    f"Lambda function '{function_id}' not found. "
                    f"Verify the function exists and you have permission to invoke it."
                ) from e
            elif error_code == "AccessDeniedException":
                raise DagsterLaunchFailedError(
                    f"Access denied when invoking Lambda function '{function_id}'. "
                    f"Verify IAM permissions include lambda:InvokeFunction."
                ) from e
            elif error_code == "RequestEntityTooLargeException":
                raise DagsterLaunchFailedError(
                    f"Payload too large for Lambda function '{function_id}'. "
                    f"Consider reducing run_config size."
                ) from e
            else:
                raise DagsterLaunchFailedError(
                    f"Failed to invoke Lambda function '{function_id}': "
                    f"{error_code} - {error_message}"
                ) from e

        except Exception as e:
            raise DagsterLaunchFailedError(
                f"Unexpected error launching run {run.run_id}: {e}"
            ) from e

    def _handle_sync_response(
        self,
        context: LaunchRunContext,
        response: Dict[str, Any],
        function_id: str,
    ) -> None:
        """Handle response from synchronous Lambda invocation.

        Args:
            context: Launch context
            response: boto3 Lambda invoke response
            function_id: Lambda function identifier
        """
        run = context.dagster_run
        instance = context.instance

        status_code = response.get("StatusCode")
        function_error = response.get("FunctionError")

        if function_error:
            # Lambda executed but returned an error
            payload = response.get("Payload")
            error_payload = json.loads(payload.read()) if payload else {}

            instance.report_engine_event(
                f"Lambda function '{function_id}' returned error: {function_error}. "
                f"Payload: {json.dumps(error_payload)}",
                run,
            )
        elif status_code == 200:
            # Successful execution
            payload = response.get("Payload")
            result = json.loads(payload.read()) if payload else {}

            instance.report_engine_event(
                f"Lambda function '{function_id}' completed successfully. "
                f"Result preview: {json.dumps(result)[:200]}...",
                run,
            )
        else:
            instance.report_engine_event(
                f"Lambda function '{function_id}' returned status code {status_code}",
                run,
            )

    def terminate(self, run_id: str) -> bool:
        """Terminate a run.

        Lambda functions cannot be terminated once invoked, so this always returns False.

        Args:
            run_id: ID of the run to terminate

        Returns:
            False (Lambda functions cannot be terminated)
        """
        if self._instance:
            self._instance.report_engine_event(
                "Lambda functions cannot be terminated after invocation. "
                "The function will continue to execute until completion or timeout.",
                run_id=run_id,
            )
        return False

    def can_terminate(self, _run_id: str) -> bool:
        """Check if a run can be terminated.

        Args:
            _run_id: ID of the run (unused - Lambda functions cannot be terminated)

        Returns:
            False (Lambda functions cannot be terminated)
        """
        return False

    def _get_lambda_function_identifier(self, context: LaunchRunContext) -> Optional[str]:
        """Extract Lambda function identifier from tags or config.

        Priority order:
        1. Run tag: 'lambda/function_name' or 'lambda/function_arn'
        2. Job config: execution.config.lambda_function
        3. Global default: default_function_name from launcher config

        Args:
            context: Launch context

        Returns:
            Lambda function name or ARN, or None if not found
        """
        run = context.dagster_run

        # Priority 1: Check run tags
        function_id = run.tags.get("lambda/function_name") or run.tags.get(
            "lambda/function_arn"
        )
        if function_id:
            return function_id

        # Priority 2: Check job config
        job_config = run.run_config.get("execution", {}).get("config", {})
        function_id = job_config.get("lambda_function")
        if function_id:
            return function_id

        # Priority 3: Use global default
        return self._default_function_name

    def _get_invocation_type(self, context: LaunchRunContext) -> str:
        """Determine invocation type (sync vs async).

        Priority order:
        1. Run tag: 'lambda/invocation_type'
        2. Job config: execution.config.invocation_type
        3. Global default: default_invocation_type from launcher config
        4. Hardcoded default: 'Event' (async)

        Args:
            context: Launch context

        Returns:
            'Event' (async) or 'RequestResponse' (sync)

        Raises:
            ValueError: If invocation type is invalid
        """
        run = context.dagster_run

        # Priority 1: Check run tags
        invocation_type = run.tags.get("lambda/invocation_type")
        if invocation_type:
            if invocation_type not in ["Event", "RequestResponse"]:
                raise ValueError(
                    f"Invalid invocation_type in tags: {invocation_type}. "
                    f"Must be 'Event' or 'RequestResponse'."
                )
            return invocation_type

        # Priority 2: Check job config
        job_config = run.run_config.get("execution", {}).get("config", {})
        invocation_type = job_config.get("invocation_type")
        if invocation_type:
            if invocation_type not in ["Event", "RequestResponse"]:
                raise ValueError(
                    f"Invalid invocation_type in config: {invocation_type}. "
                    f"Must be 'Event' or 'RequestResponse'."
                )
            return invocation_type

        # Priority 3: Use global default
        return self._default_invocation_type

    def _build_lambda_payload(self, context: LaunchRunContext) -> Dict[str, Any]:
        """Build the Lambda payload based on configured payload_mode.

        Supports multiple payload modes:
        - 'full': Complete payload with run metadata, config, env vars (default)
        - 'config_only': Just the run_config dictionary
        - 'ops_only': Just the ops config from run_config.ops
        - 'custom': Extract specific path from run_config

        Args:
            context: Launch context

        Returns:
            Dictionary ready for JSON serialization
        """
        run = context.dagster_run

        # Build based on payload mode
        if self._payload_mode == "full":
            # Full comprehensive payload (default)
            return self._build_full_payload(context)

        elif self._payload_mode == "config_only":
            # Just the run configuration
            return run.run_config

        elif self._payload_mode == "ops_only":
            # Just the ops configuration
            return run.run_config.get("ops", {})

        elif self._payload_mode == "custom":
            # Extract specific path from run_config
            return self._extract_config_path(run.run_config, self._payload_config_path)

        else:
            # Fallback to full payload (should never happen due to validation)
            return self._build_full_payload(context)

    def _build_full_payload(self, context: LaunchRunContext) -> Dict[str, Any]:
        """Build the full comprehensive Lambda payload.

        Payload structure:
        {
          "dagster_run": {...},  # Run metadata
          "run_config": {...},   # Full run configuration
          "environment_variables": {...},  # Environment variables
          "dagster_cloud": {...},  # Dagster Cloud info
          "metadata": {...}  # Launcher metadata
        }

        Args:
            context: Launch context

        Returns:
            Dictionary ready for JSON serialization
        """
        run = context.dagster_run

        payload = {
            "dagster_run": {
                "run_id": run.run_id,
                "job_name": run.job_name,
                "deployment_name": run.tags.get("dagster/deployment_name"),
                "location_name": run.tags.get("dagster/code_location"),
                "agent_id": run.tags.get("dagster/agent_id"),
                "pipeline_name": run.pipeline_name,
                "status": run.status.value if run.status else None,
                "tags": run.tags,
            },
            "run_config": run.run_config,
            "environment_variables": self._build_environment_variables(context),
            "dagster_cloud": {
                "org_id": run.tags.get("dagster_cloud/org_id"),
                "deployment_id": run.tags.get("dagster_cloud/deployment_id"),
            },
            "metadata": {
                "launched_at": datetime.now(timezone.utc).isoformat(),
                "launcher_version": LAUNCHER_VERSION,
                "region": self._region_name,
            },
        }

        return payload

    def _extract_config_path(
        self, config: Dict[str, Any], path: str
    ) -> Dict[str, Any]:
        """Extract a value from config using dot notation path.

        Examples:
            path='ops.my_op.config' extracts config['ops']['my_op']['config']
            path='resources.database' extracts config['resources']['database']

        Args:
            config: Configuration dictionary
            path: Dot-notation path (e.g., 'ops.my_op.config')

        Returns:
            Extracted value

        Raises:
            KeyError: If path doesn't exist in config
        """
        keys = path.split(".")
        value = config

        for key in keys:
            if not isinstance(value, dict):
                raise KeyError(
                    f"Cannot access key '{key}' in path '{path}': "
                    f"value is not a dictionary"
                )
            if key not in value:
                raise KeyError(
                    f"Key '{key}' not found in path '{path}'. "
                    f"Available keys: {list(value.keys())}"
                )
            value = value[key]

        return value

    def _build_environment_variables(self, _context: LaunchRunContext) -> Dict[str, str]:
        """Gather environment variables to pass to Lambda.

        This includes environment variables specified in the launcher configuration
        (env_vars parameter) that are present in the current environment.

        Args:
            _context: Launch context (unused - reserved for future code location env var support)

        Returns:
            Dictionary of environment variable name-value pairs
        """
        env_vars = {}

        # Include specified environment variables
        for var_name in self._env_vars:
            value = os.environ.get(var_name)
            if value is not None:
                env_vars[var_name] = value

        # Always include Dagster-specific variables if present
        dagster_vars = [
            "DAGSTER_CLOUD_ORG_ID",
            "DAGSTER_CLOUD_DEPLOYMENT_ID",
            "DAGSTER_CLOUD_API_TOKEN",
        ]
        for var_name in dagster_vars:
            if var_name not in env_vars:
                value = os.environ.get(var_name)
                if value is not None:
                    env_vars[var_name] = value

        return env_vars
