#!/bin/bash
# Build and push Docker image for Dagster+ Agent with Lambda Run Launcher

set -e

# Configuration
REGISTRY="${ECR_REGISTRY:-}"  # Set to your ECR registry URL
IMAGE_NAME="${IMAGE_NAME:-dagster-lambda-agent}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "================================================"
echo "  Dagster Lambda Agent - Build and Push"
echo "================================================"

# Check if registry is set
if [ -z "$REGISTRY" ]; then
    echo -e "${RED}Error: ECR_REGISTRY environment variable not set${NC}"
    echo "Usage: ECR_REGISTRY=123456789012.dkr.ecr.us-east-1.amazonaws.com ./build-and-push.sh"
    exit 1
fi

FULL_IMAGE_NAME="${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"

echo -e "\n${GREEN}[1/4]${NC} Building Docker image..."
echo "Image: ${FULL_IMAGE_NAME}"

# Build the image
docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" ..

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Docker build failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Build successful"

# Tag the image
echo -e "\n${GREEN}[2/4]${NC} Tagging image..."
docker tag "${IMAGE_NAME}:${IMAGE_TAG}" "${FULL_IMAGE_NAME}"
echo -e "${GREEN}✓${NC} Image tagged"

# Get AWS region from registry URL
REGION=$(echo $REGISTRY | cut -d'.' -f4)

echo -e "\n${GREEN}[3/4]${NC} Logging into ECR..."
echo "Region: ${REGION}"

# Login to ECR
aws ecr get-login-password --region "${REGION}" | \
    docker login --username AWS --password-stdin "${REGISTRY}"

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: ECR login failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} ECR login successful"

# Push the image
echo -e "\n${GREEN}[4/4]${NC} Pushing image to ECR..."
docker push "${FULL_IMAGE_NAME}"

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Docker push failed${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Image pushed successfully"

echo -e "\n${GREEN}================================================${NC}"
echo -e "${GREEN}  Build and Push Complete!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "Image URL: ${FULL_IMAGE_NAME}"
echo ""
echo "Next steps:"
echo "  1. Update your ECS task definition to use this image"
echo "  2. Set required environment variables (see env.example)"
echo "  3. Deploy the updated task definition to ECS"
