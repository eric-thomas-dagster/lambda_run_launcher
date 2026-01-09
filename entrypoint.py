#!/usr/bin/env python3
"""Entrypoint for Dagster+ Agent with Lambda Run Launcher

This script bootstraps the Dagster Cloud agent with the custom Lambda run launcher.
It handles environment variable expansion in configuration and starts the agent.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict


def expand_env_vars(content: str, env_vars: Dict[str, str]) -> str:
    """Expand environment variables in configuration content.

    Supports syntax: ${VAR_NAME} or ${VAR_NAME:default_value}

    Args:
        content: Configuration file content
        env_vars: Dictionary of environment variables

    Returns:
        Content with environment variables expanded
    """

    def replace_var(match):
        var_expr = match.group(1)

        # Check if there's a default value
        if ":" in var_expr:
            var_name, default_value = var_expr.split(":", 1)
        else:
            var_name = var_expr
            default_value = ""

        # Get value from environment or use default
        value = env_vars.get(var_name, default_value)

        if not value and not default_value:
            print(
                f"Warning: Environment variable {var_name} not set and no default provided",
                file=sys.stderr,
            )

        return value

    # Replace ${VAR} or ${VAR:default} patterns
    pattern = r"\$\{([^}]+)\}"
    return re.sub(pattern, replace_var, content)


def validate_required_env_vars() -> Dict[str, str]:
    """Validate and retrieve required environment variables.

    Returns:
        Dictionary of environment variables

    Raises:
        SystemExit: If required variables are missing
    """
    env_vars = dict(os.environ)

    # Required for Dagster Cloud agent
    required_vars = [
        "DAGSTER_CLOUD_AGENT_TOKEN",
    ]

    # Recommended but not strictly required
    recommended_vars = [
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
    ]

    missing_required = [var for var in required_vars if not env_vars.get(var)]

    if missing_required:
        print("Error: Missing required environment variables:", file=sys.stderr)
        for var in missing_required:
            print(f"  - {var}", file=sys.stderr)
        print("\nAgent cannot start without these variables.", file=sys.stderr)
        sys.exit(1)

    missing_recommended = [var for var in recommended_vars if not env_vars.get(var)]
    if missing_recommended:
        print("Warning: Missing recommended environment variables:", file=sys.stderr)
        for var in missing_recommended:
            print(f"  - {var}", file=sys.stderr)

    return env_vars


def process_dagster_yaml(env_vars: Dict[str, str]) -> None:
    """Process dagster.yaml to expand environment variables.

    Args:
        env_vars: Dictionary of environment variables
    """
    dagster_yaml_path = Path("/app/dagster.yaml")

    if not dagster_yaml_path.exists():
        print(f"Error: {dagster_yaml_path} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Processing {dagster_yaml_path}")

    # Read original content
    with open(dagster_yaml_path, "r") as f:
        original_content = f.read()

    # Expand environment variables
    expanded_content = expand_env_vars(original_content, env_vars)

    # Write back expanded content
    with open(dagster_yaml_path, "w") as f:
        f.write(expanded_content)

    print("Environment variables expanded in dagster.yaml")


def start_agent() -> None:
    """Start the Dagster Cloud agent.

    This launches the agent using dagster-cloud CLI.
    """
    print("Starting Dagster Cloud agent with Lambda run launcher...")
    print(f"DAGSTER_HOME: {os.environ.get('DAGSTER_HOME', '/app')}")
    print(f"AWS_REGION: {os.environ.get('AWS_REGION', 'not set')}")

    # Launch the agent
    cmd = ["dagster-cloud", "agent", "run"]

    print(f"Executing: {' '.join(cmd)}")

    try:
        # Run the agent (this will run indefinitely)
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: Agent exited with code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\nAgent stopped by user")
        sys.exit(0)


def main():
    """Main entrypoint function."""
    print("=" * 60)
    print("Dagster+ Agent with Lambda Run Launcher")
    print("=" * 60)

    # Step 1: Validate environment variables
    print("\n[1/3] Validating environment variables...")
    env_vars = validate_required_env_vars()
    print("✓ Environment variables validated")

    # Step 2: Process dagster.yaml
    print("\n[2/3] Processing dagster.yaml configuration...")
    process_dagster_yaml(env_vars)
    print("✓ Configuration processed")

    # Step 3: Start agent
    print("\n[3/3] Starting Dagster Cloud agent...")
    start_agent()


if __name__ == "__main__":
    main()
