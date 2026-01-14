#!/usr/bin/env python3
"""
Update script
Forces Docker image push to ECR and updates AgentCore runtime
References installer.py for Docker build/push and runtime update functionality
"""

import subprocess
import sys
import os
import json
import shutil
import base64
from datetime import datetime
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Import functions from installer.py
script_dir = os.path.dirname(os.path.abspath(__file__))
installer_path = os.path.join(script_dir, "installer.py")

# Add script directory to path to import installer functions
sys.path.insert(0, script_dir)

# Import necessary functions from installer
from installer import (
    load_config,
    update_config,
    check_aws_cli,
    check_aws_credentials,
    ensure_ecr_repository,
    docker_login,
    run_docker_command,
    get_latest_image_tag,
    update_agentcore_json,
    update_agent_runtime_func,
    create_agent_runtime_func
)

def push_to_ecr_force():
    """Force build Docker image and push to ECR (overwrites existing images)"""
    print(f"\n{'='*60}")
    print("Force building Docker image and pushing to ECR")
    print(f"{'='*60}")
    
    try:
        # Use current time as tag
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
        # Load config
        config = load_config()
        aws_account_id = config.get("accountId")
        aws_region = config.get("region")
        project_name = config.get("projectName")
        
        if not all([aws_account_id, aws_region, project_name]):
            print("Error: Missing required configuration in config.json")
            print("Required: accountId, region, projectName")
            return False
        
        # Get current folder name
        current_folder_name = os.path.basename(os.getcwd())
        print(f"CURRENT_FOLDER_NAME: {current_folder_name}")
        
        # Construct ECR repository name
        ecr_repository = f"{project_name}_{current_folder_name}"
        print(f"ECR_REPOSITORY: {ecr_repository}")
        
        # Construct image tag and ECR URI
        image_tag = timestamp
        ecr_uri = f"{aws_account_id}.dkr.ecr.{aws_region}.amazonaws.com/{ecr_repository}:{image_tag}"
        
        # Display configuration
        print("===== Checking AWS Configuration =====")
        print(f"AWS Account ID: {aws_account_id}")
        print(f"AWS Region: {aws_region}")
        print(f"ECR Repository: {ecr_repository}")
        print(f"ECR URI: {ecr_uri}")
        
        # Check AWS CLI
        if not check_aws_cli():
            return False
        
        # Check AWS credentials
        print("===== Checking AWS Credentials =====")
        if not check_aws_credentials():
            return False
        
        # Check/create ECR repository
        print("===== Checking ECR Repository =====")
        ecr_client = boto3.client("ecr", region_name=aws_region)
        if not ensure_ecr_repository(ecr_client, ecr_repository, aws_region):
            return False
        
        # ECR Login
        print("===== AWS ECR Login =====")
        if not docker_login(aws_account_id, aws_region):
            return False
        
        # Build Docker image (force rebuild)
        print("===== Force Building Docker Image =====")
        if not run_docker_command(
            ["docker", "build", "--no-cache", "-t", f"{ecr_repository}:{image_tag}", "."],
            "Force Building Docker Image"
        ):
            return False
        
        # Tag for ECR repository
        if not run_docker_command(
            ["docker", "tag", f"{ecr_repository}:{image_tag}", ecr_uri],
            "Tagging for ECR Repository"
        ):
            return False
        
        # Force push to ECR (overwrites if tag exists)
        print("===== Force Pushing Image to ECR Repository =====")
        if not run_docker_command(
            ["docker", "push", ecr_uri],
            "Force Pushing Image to ECR Repository"
        ):
            return False
        
        # Complete
        print("===== Complete =====")
        print("Image has been successfully built and force pushed to ECR.")
        print(f"Image URI: {ecr_uri}")
        
        # Store image tag in config for later use
        update_config('latest_image_tag', image_tag)
        update_config('ecr_repository', ecr_repository)
        
        return image_tag
        
    except Exception as e:
        print(f"Error building and pushing Docker image: {e}")
        return None

def update_agent_runtime():
    """Update AgentCore runtime with the latest image"""
    print(f"\n{'='*60}")
    print("Updating AgentCore runtime")
    print(f"{'='*60}")
    
    try:
        config = load_config()
        aws_region = config['region']
        project_name = config.get('projectName')
        
        # Get current folder name
        current_folder_name = os.path.basename(os.getcwd())
        repository_name = f"{project_name}_{current_folder_name}"
        # Replace hyphens with underscores for agent runtime name (AWS validation requirement)
        runtime_name = repository_name.replace('-', '_')
        
        print(f"\n1. Repository name: {repository_name}")
        print(f"Runtime name: {runtime_name}")
        
        # Get latest image tag from config (just pushed)
        image_tag = config.get('latest_image_tag')
        if not image_tag:
            print("Error: latest_image_tag not found in config.json")
            print("Attempting to get latest image tag from ECR...")
            image_tag = get_latest_image_tag(config)
            if not image_tag:
                print("Error: Could not get latest image tag")
                return False
        
        print(f"Using image tag: {image_tag}")
        
        # Check if agent runtime already exists
        client = boto3.client('bedrock-agentcore-control', region_name=aws_region)
        response = client.list_agent_runtimes()
        agent_runtimes = response.get('agentRuntimes', [])
        
        is_exist = False
        agent_runtime_id = None
        
        for agent_runtime in agent_runtimes:
            if agent_runtime['agentRuntimeName'] == runtime_name:
                print(f"Agent runtime {runtime_name} found")
                is_exist = True
                agent_runtime_id = agent_runtime['agentRuntimeId']
                break
        
        if not is_exist:
            print(f"Error: Agent runtime {runtime_name} does not exist")
            print("Please create it first using installer.py")
            return False
        
        # Update agent runtime
        print("\n2. Updating Agent Runtime...")
        print(f"Updating agent runtime: {runtime_name}")
        agent_runtime_arn = update_agent_runtime_func(config, repository_name, agent_runtime_id, image_tag)
        
        if not agent_runtime_arn:
            print("Error: Failed to update agent runtime")
            return False
        
        # Update config.json
        update_agentcore_json(agent_runtime_arn)
        
        print("\n✓ Agent runtime update completed")
        return True
        
    except Exception as e:
        print(f"Error updating agent runtime: {e}")
        return False

def main():
    """Main function: Force push Docker image and update AgentCore runtime"""
    print("\n" + "="*60)
    print("AgentCore Runtime Update Script")
    print("="*60)
    
    # Check config.json
    config = load_config()
    
    print(f"Configuration file loaded successfully")
    print(f"  - Project Name: {config.get('projectName')}")
    print(f"  - Region: {config.get('region')}")
    print(f"  - Account ID: {config.get('accountId')}")
    
    # Step 1: Force push Docker image to ECR
    print("\n" + "="*60)
    print("Step 1: Force pushing Docker image to ECR")
    print("="*60)
    image_tag = push_to_ecr_force()
    
    if not image_tag:
        print("\nUpdate failed: Error occurred while pushing Docker image to ECR.")
        sys.exit(1)
    
    # Step 2: Update AgentCore runtime
    print("\n" + "="*60)
    print("Step 2: Updating AgentCore runtime")
    print("="*60)
    if not update_agent_runtime():
        print("\nUpdate failed: Error occurred while updating AgentCore runtime.")
        sys.exit(1)
    
    # Output final results
    print("\n" + "="*60)
    print("Update completed successfully!")
    print("="*60)
    
    # Output final config.json information
    config = load_config()
    
    arn = config.get('agent_runtime_arn')
    image_tag = config.get('latest_image_tag')
    
    if arn:
        print(f"\nUpdated AgentCore Runtime ARN: {arn}")
    if image_tag:
        print(f"Updated Image Tag: {image_tag}")
    
    print("\nUpdate complete!")

if __name__ == "__main__":
    main()
