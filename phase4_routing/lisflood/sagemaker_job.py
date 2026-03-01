"""
sagemaker_job.py — SageMaker Processing Job launcher for LISFLOOD.

Configures and launches a SageMaker Processing Job using either
the mock LISFLOOD container (default) or a real LISFLOOD-FP image.
Supports local-mode execution for testing without AWS credentials.
"""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_INSTANCE_TYPE = "ml.m5.large"
DEFAULT_VOLUME_SIZE_GB = 30
DEFAULT_MAX_RUNTIME_SECS = 900  # 15 min
DEFAULT_REGION = "us-east-1"

# S3 paths
S3_BUCKET = os.environ.get("FLOODWATCH_S3_BUCKET", "floodwatch-uploads")
S3_INPUT_PREFIX = "lisflood/input"
S3_OUTPUT_PREFIX = "lisflood/output"


def build_processing_job_config(
    job_name: str | None = None,
    container_image_uri: str | None = None,
    role_arn: str | None = None,
    instance_type: str = DEFAULT_INSTANCE_TYPE,
    volume_size_gb: int = DEFAULT_VOLUME_SIZE_GB,
    max_runtime_secs: int = DEFAULT_MAX_RUNTIME_SECS,
) -> dict:
    """
    Build a SageMaker Processing Job configuration dict.

    Args:
        job_name:            Custom job name (auto-generated if None).
        container_image_uri: ECR URI for the LISFLOOD container.
        role_arn:            IAM execution role ARN.
        instance_type:       SageMaker instance type.
        volume_size_gb:      Attached EBS volume size.
        max_runtime_secs:    Maximum run time before timeout.

    Returns:
        Dict matching the ``create_processing_job`` API shape.
    """
    if job_name is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        job_name = f"floodwatch-lisflood-{ts}"

    if container_image_uri is None:
        container_image_uri = os.environ.get(
            "LISFLOOD_IMAGE_URI",
            "mock-lisflood-fp:latest",
        )

    if role_arn is None:
        role_arn = os.environ.get(
            "SAGEMAKER_ROLE_ARN",
            "arn:aws:iam::000000000000:role/floodwatch-sagemaker-role",
        )

    config = {
        "ProcessingJobName": job_name,
        "ProcessingResources": {
            "ClusterConfig": {
                "InstanceCount": 1,
                "InstanceType": instance_type,
                "VolumeSizeInGB": volume_size_gb,
            }
        },
        "StoppingCondition": {
            "MaxRuntimeInSeconds": max_runtime_secs,
        },
        "AppSpecification": {
            "ImageUri": container_image_uri,
        },
        "RoleArn": role_arn,
        "ProcessingInputs": [
            {
                "InputName": "dem-data",
                "S3Input": {
                    "S3Uri": f"s3://{S3_BUCKET}/{S3_INPUT_PREFIX}/dem/",
                    "LocalPath": "/opt/ml/processing/input/dem",
                    "S3DataType": "S3Prefix",
                    "S3InputMode": "File",
                },
            },
            {
                "InputName": "rainfall-data",
                "S3Input": {
                    "S3Uri": f"s3://{S3_BUCKET}/{S3_INPUT_PREFIX}/rainfall/",
                    "LocalPath": "/opt/ml/processing/input/rainfall",
                    "S3DataType": "S3Prefix",
                    "S3InputMode": "File",
                },
            },
        ],
        "ProcessingOutputConfig": {
            "Outputs": [
                {
                    "OutputName": "flood-rasters",
                    "S3Output": {
                        "S3Uri": f"s3://{S3_BUCKET}/{S3_OUTPUT_PREFIX}/{job_name}/",
                        "LocalPath": "/opt/ml/processing/output",
                        "S3UploadMode": "EndOfJob",
                    },
                }
            ]
        },
        "Tags": [
            {"Key": "Project", "Value": "FloodWatch"},
            {"Key": "Phase", "Value": "4"},
            {"Key": "Component", "Value": "LISFLOOD"},
        ],
    }

    logger.info("Built SageMaker Processing Job config: %s", job_name)
    return config


def launch_processing_job(config: dict, local_mode: bool = False) -> dict:
    """
    Launch a SageMaker Processing Job.

    Args:
        config:     Job configuration from ``build_processing_job_config``.
        local_mode: If True, run the mock container locally instead.

    Returns:
        Dict with job ARN (production) or local output paths (local mode).
    """
    job_name = config["ProcessingJobName"]

    if local_mode:
        logger.info("Running LISFLOOD in LOCAL mode (no AWS)")
        from phase4_routing.lisflood.mock_container import run_mock_simulation

        result = run_mock_simulation(output_dir="./outputs/lisflood")
        return {
            "mode": "local",
            "job_name": job_name,
            "status": "Completed",
            **result,
        }

    # Production: submit to SageMaker
    import boto3

    client = boto3.client(
        "sagemaker",
        region_name=os.environ.get("AWS_REGION", DEFAULT_REGION),
    )

    logger.info("Submitting SageMaker Processing Job: %s", job_name)
    response = client.create_processing_job(**config)

    return {
        "mode": "sagemaker",
        "job_name": job_name,
        "job_arn": response["ProcessingJobArn"],
        "status": "InProgress",
    }


def get_job_status(job_name: str) -> dict:
    """Check the status of a SageMaker Processing Job."""
    import boto3

    client = boto3.client(
        "sagemaker",
        region_name=os.environ.get("AWS_REGION", DEFAULT_REGION),
    )
    response = client.describe_processing_job(ProcessingJobName=job_name)

    return {
        "job_name": job_name,
        "status": response["ProcessingJobStatus"],
        "exit_message": response.get("ExitMessage", ""),
        "failure_reason": response.get("FailureReason", ""),
    }
