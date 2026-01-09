# Dockerfile for Dagster+ Agent with Lambda Run Launcher
#
# This extends the official Dagster Cloud agent image and adds the custom
# Lambda run launcher for executing jobs as Lambda function invocations.

FROM dagster/dagster-cloud-agent:latest

# Set working directory
WORKDIR /app

# Copy the custom launcher code
COPY app/ /app/

# Copy agent configuration
COPY dagster.yaml /app/dagster.yaml

# Copy entrypoint script
COPY entrypoint.py /app/entrypoint.py

# Install additional dependencies if needed
# (boto3 is typically already included in the agent image)
RUN pip install --no-cache-dir boto3>=1.26.0

# Set Python path to include /app
ENV PYTHONPATH=/app:${PYTHONPATH}
ENV DAGSTER_HOME=/app

# Make entrypoint executable
RUN chmod +x /app/entrypoint.py

# Use custom entrypoint
ENTRYPOINT ["python", "/app/entrypoint.py"]
