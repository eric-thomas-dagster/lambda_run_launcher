# Dockerfile for Dagster+ Agent with Lambda Run Launcher
#
# This extends the official Dagster Cloud agent image and adds the custom
# Lambda run launcher for executing jobs as Lambda function invocations.

FROM dagster/dagster-cloud-agent:latest

# Set working directory
WORKDIR /app

# Copy the custom launcher code
COPY app/ /app/app/

# Copy agent configuration
COPY dagster.yaml /app/dagster.yaml

# Install additional dependencies if needed
# (boto3 is typically already included in the agent image)
RUN pip install --no-cache-dir boto3>=1.26.0

# Set Python path to include /app so app.lambda_run_launcher is importable
ENV PYTHONPATH=/app:${PYTHONPATH}
ENV DAGSTER_HOME=/app

# Use default dagster-cloud-agent entrypoint
# The base image already handles:
# - Reading dagster.yaml
# - Environment variable substitution
# - Starting the agent
