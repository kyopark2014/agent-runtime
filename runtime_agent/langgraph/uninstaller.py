#!/usr/bin/env python3
"""
Unified uninstallation script
Sequentially deletes: AgentCore runtime -> ECR repository -> IAM role -> IAM policy
All functionality integrated into a single file
"""

import sys
import os
import json
import time
import argparse
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.json")

def load_config():
    """Load config.json file."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"Failed to parse config.json file: {e}")
        print("Error: config.json file is required for uninstallation")
        return None
    
    return config

# ============================================================================
# Agent Runtime Deletion Functions
# ============================================================================

def delete_agent_runtime():
    """Delete AgentCore runtime and wait for deletion to complete"""
    print(f"\n{'='*60}")
    print("Deleting AgentCore runtime")
    print(f"{'='*60}")
    
    try:
        config = load_config()
        if not config:
            return False
            
        aws_region = config.get('region')
        project_name = config.get('projectName')
        agent_runtime_arn = config.get('agent_runtime_arn')
        
        if not all([aws_region, project_name]):
            print("Error: Missing required configuration in config.json")
            print("Required: region, projectName")
            return False
        
        # Get current folder name
        current_folder_name = os.path.basename(os.getcwd())
        repository_name = f"{project_name}_{current_folder_name}"
        # Convert hyphens to underscores for agent runtime name (AWS validation requirement)
        runtime_name = repository_name.replace('-', '_')
        
        try:
            client = boto3.client('bedrock-agentcore-control', region_name=aws_region)
            deletion_requested = False
            actual_runtime_name = None
            
            # If agent_runtime_arn is in config, use it
            if agent_runtime_arn:
                # Extract agent runtime ID from ARN
                # ARN format: arn:aws:bedrock-agentcore:region:account:runtime/runtime-name-runtimeId
                runtime_id = agent_runtime_arn.split('/')[-1] if '/' in agent_runtime_arn else None
                
                if runtime_id:
                    try:
                        client.delete_agent_runtime(agentRuntimeId=runtime_id)
                        print(f"✓ Agent runtime deletion requested: {agent_runtime_arn}")
                        deletion_requested = True
                        # Get actual runtime name from ARN or list
                        try:
                            response = client.list_agent_runtimes()
                            agent_runtimes = response.get('agentRuntimes', [])
                            for agent_runtime in agent_runtimes:
                                if agent_runtime['agentRuntimeId'] == runtime_id:
                                    actual_runtime_name = agent_runtime['agentRuntimeName']
                                    break
                        except:
                            actual_runtime_name = runtime_name
                    except ClientError as e:
                        if e.response['Error']['Code'] == 'ResourceNotFoundException':
                            print(f"Agent runtime not found (may already be deleted): {agent_runtime_arn}")
                            return True
                        else:
                            print(f"Error deleting agent runtime: {e}")
                            return False
            
            # Fallback: List and find by name
            if not deletion_requested:
                response = client.list_agent_runtimes()
                agent_runtimes = response.get('agentRuntimes', [])
                
                for agent_runtime in agent_runtimes:
                    # Use runtime_name (with underscores) for comparison
                    if agent_runtime['agentRuntimeName'] == runtime_name:
                        runtime_id = agent_runtime['agentRuntimeId']
                        actual_runtime_name = agent_runtime['agentRuntimeName']
                        try:
                            client.delete_agent_runtime(agentRuntimeId=runtime_id)
                            print(f"✓ Agent runtime deletion requested: {agent_runtime['agentRuntimeArn']}")
                            deletion_requested = True
                            break
                        except ClientError as e:
                            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                                print(f"Agent runtime not found (may already be deleted): {actual_runtime_name}")
                                return True
                            else:
                                print(f"Error deleting agent runtime: {e}")
                                return False
                
                if not deletion_requested:
                    print(f"Agent runtime {runtime_name} not found (may already be deleted)")
                    return True
            
            # Wait for deletion to complete
            if deletion_requested:
                # Use actual runtime name if available, otherwise use runtime_name
                name_to_check = actual_runtime_name if actual_runtime_name else runtime_name
                return wait_for_runtime_deletion(config, name_to_check)
            else:
                return True
            
        except Exception as e:
            print(f"Error deleting agent runtime: {e}")
            return False
            
    except Exception as e:
        print(f"Error deleting agent runtime: {e}")
        return False

def wait_for_runtime_deletion(config, runtime_name, max_wait_time=600):
    """Wait for AgentCore runtime to be completely deleted (check every 10 seconds)"""
    aws_region = config.get('region')
    if not aws_region:
        print("Error: region not found in config.json")
        return False
    
    print(f"\nWaiting for AgentCore runtime '{runtime_name}' to be deleted...")
    print("Checking every 10 seconds...")
    
    client = boto3.client('bedrock-agentcore-control', region_name=aws_region)
    start_time = time.time()
    check_count = 0
    
    while True:
        check_count += 1
        elapsed_time = time.time() - start_time
        
        try:
            response = client.list_agent_runtimes()
            agent_runtimes = response.get('agentRuntimes', [])
            
            # Check if the specific runtime still exists
            runtime_exists = False
            for agent_runtime in agent_runtimes:
                if agent_runtime['agentRuntimeName'] == runtime_name:
                    runtime_exists = True
                    break
            
            if not runtime_exists:
                print(f"✓ AgentCore runtime '{runtime_name}' has been successfully deleted")
                print(f"  (Checked {check_count} times, elapsed time: {elapsed_time:.1f} seconds)")
                return True
            
            # Check timeout
            if elapsed_time >= max_wait_time:
                print(f"\nTimeout: AgentCore runtime '{runtime_name}' still exists after {max_wait_time} seconds")
                print("  Please check manually or try again later")
                return False
            
            # Wait 10 seconds before next check
            print(f"  [{check_count}] Runtime still exists, waiting 10 seconds... (elapsed: {elapsed_time:.1f}s)")
            time.sleep(10)
            
        except Exception as e:
            print(f"Error checking runtime status: {e}")
            return False

# ============================================================================
# ECR Repository Deletion Functions
# ============================================================================

def delete_ecr_repository():
    """Delete ECR repository and all images"""
    print(f"\n{'='*60}")
    print("Deleting ECR repository")
    print(f"{'='*60}")
    
    try:
        config = load_config()
        if not config:
            return False
            
        aws_region = config.get('region')
        project_name = config.get('projectName')
        ecr_repository = config.get('ecr_repository')
        
        if not all([aws_region, project_name]):
            print("Error: Missing required configuration in config.json")
            print("Required: region, projectName")
            return False
        
        # Get repository name
        if not ecr_repository:
            # Get current folder name
            current_folder_name = os.path.basename(os.getcwd())
            ecr_repository = f"{project_name}_{current_folder_name}"
        
        print(f"Repository name: {ecr_repository}")
        
        try:
            ecr_client = boto3.client('ecr', region_name=aws_region)
            
            # Check if repository exists
            try:
                ecr_client.describe_repositories(repositoryNames=[ecr_repository])
            except ClientError as e:
                if e.response['Error']['Code'] == 'RepositoryNotFoundException':
                    print(f"ECR repository {ecr_repository} not found (may already be deleted)")
                    return True
                else:
                    print(f"Error checking repository: {e}")
                    return False
            
            # List all images in the repository
            try:
                response = ecr_client.list_images(repositoryName=ecr_repository)
                image_ids = response.get('imageIds', [])
                
                if image_ids:
                    print(f"Found {len(image_ids)} images in repository. Deleting...")
                    # Delete all images
                    ecr_client.batch_delete_image(
                        repositoryName=ecr_repository,
                        imageIds=image_ids
                    )
                    print(f"✓ Deleted {len(image_ids)} images from repository")
                else:
                    print("No images found in repository")
            except ClientError as e:
                if e.response['Error']['Code'] != 'RepositoryNotFoundException':
                    print(f"Warning: Error deleting images: {e}")
            
            # Delete repository
            try:
                ecr_client.delete_repository(
                    repositoryName=ecr_repository,
                    force=True  # Force delete even if images exist
                )
                print(f"✓ ECR repository deleted: {ecr_repository}")
                return True
            except ClientError as e:
                if e.response['Error']['Code'] == 'RepositoryNotFoundException':
                    print(f"ECR repository {ecr_repository} not found (may already be deleted)")
                    return True
                else:
                    print(f"Error deleting repository: {e}")
                    return False
                    
        except Exception as e:
            print(f"Error deleting ECR repository: {e}")
            return False
            
    except Exception as e:
        print(f"Error deleting ECR repository: {e}")
        return False

# ============================================================================
# IAM Role and Policy Deletion Functions
# ============================================================================

def detach_policy_from_role(role_name, policy_arn):
    """Detach policy from IAM role"""
    try:
        iam_client = boto3.client('iam')
        
        # Detach policy from role
        iam_client.detach_role_policy(
            RoleName=role_name,
            PolicyArn=policy_arn
        )
        print(f"✓ Policy detached successfully: {policy_arn}")
        return True
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchEntity':
            print(f"Policy not attached to role (may already be detached): {policy_arn}")
            return True
        else:
            print(f"Policy detachment failed: {e}")
            return False
    except Exception as e:
        print(f"Policy detachment failed: {e}")
        return False

def delete_iam_role(config):
    """Delete IAM role"""
    projectName = config.get('projectName', 'agentcore')
    role_name = f"AmazonBedrockAgentCoreRuntimeRoleFor{projectName}"
    
    try:
        iam_client = boto3.client('iam')
        
        # Check if role exists
        try:
            existing_role = iam_client.get_role(RoleName=role_name)
            role_arn = existing_role['Role']['Arn']
            
            # List attached policies
            attached_policies = iam_client.list_attached_role_policies(RoleName=role_name)
            for policy in attached_policies.get('AttachedPolicies', []):
                detach_policy_from_role(role_name, policy['PolicyArn'])
            
            # List inline policies
            inline_policies = iam_client.list_role_policies(RoleName=role_name)
            for policy_name in inline_policies.get('PolicyNames', []):
                try:
                    iam_client.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
                    print(f"✓ Deleted inline policy: {policy_name}")
                except Exception as e:
                    print(f"Warning: Failed to delete inline policy {policy_name}: {e}")
            
            # Delete role
            iam_client.delete_role(RoleName=role_name)
            print(f"✓ IAM role deleted: {role_arn}")
            return True
            
        except iam_client.exceptions.NoSuchEntityException:
            print(f"IAM role {role_name} not found (may already be deleted)")
            return True
            
    except Exception as e:
        print(f"Role deletion failed: {e}")
        return False

def delete_iam_policy(config):
    """Delete IAM policy and all versions"""
    accountId = config.get('accountId')
    projectName = config.get('projectName', 'agentcore')
    policy_name = f"AmazonBedrockAgentCoreRuntimePolicyFor{projectName}"
    policy_arn = f"arn:aws:iam::{accountId}:policy/{policy_name}"
    
    try:
        iam_client = boto3.client('iam')
        
        # Check if policy exists
        try:
            existing_policy = iam_client.get_policy(PolicyArn=policy_arn)
            
            # List all policy versions
            versions_response = iam_client.list_policy_versions(PolicyArn=policy_arn)
            versions = versions_response['Versions']
            
            # Delete all non-default versions first
            for version in versions:
                if not version['IsDefaultVersion']:
                    try:
                        iam_client.delete_policy_version(
                            PolicyArn=policy_arn,
                            VersionId=version['VersionId']
                        )
                        print(f"✓ Deleted policy version: {version['VersionId']}")
                    except Exception as e:
                        print(f"Warning: Failed to delete policy version {version['VersionId']}: {e}")
            
            # Delete default version (must be last)
            if versions:
                default_version = next((v for v in versions if v['IsDefaultVersion']), None)
                if default_version:
                    try:
                        iam_client.delete_policy_version(
                            PolicyArn=policy_arn,
                            VersionId=default_version['VersionId']
                        )
                        print(f"✓ Deleted default policy version: {default_version['VersionId']}")
                    except Exception as e:
                        print(f"Warning: Failed to delete default policy version: {e}")
            
            # Delete policy
            iam_client.delete_policy(PolicyArn=policy_arn)
            print(f"✓ IAM policy deleted: {policy_arn}")
            return True
            
        except iam_client.exceptions.NoSuchEntityException:
            print(f"IAM policy {policy_name} not found (may already be deleted)")
            return True
            
    except Exception as e:
        print(f"Policy deletion failed: {e}")
        return False

def delete_iam_resources():
    """Delete IAM role and policy"""
    print(f"\n{'='*60}")
    print("Deleting IAM role and policy")
    print(f"{'='*60}")
    
    try:
        config = load_config()
        if not config:
            return False
        
        accountId = config.get('accountId')
        if not accountId:
            print("Error: accountId not found in config.json")
            return False
        
        # Delete role first (it references the policy)
        print("\n1. Deleting IAM role...")
        if not delete_iam_role(config):
            print("Warning: Failed to delete IAM role")
        
        # Delete policy
        print("\n2. Deleting IAM policy...")
        if not delete_iam_policy(config):
            print("Warning: Failed to delete IAM policy")
        
        print("\n✓ IAM resources deletion completed")
        return True
        
    except Exception as e:
        print(f"Error deleting IAM resources: {e}")
        return False

# ============================================================================
# Main Function
# ============================================================================

def main():
    """Main function: Execute the entire uninstallation process."""
    parser = argparse.ArgumentParser(description="AgentCore Runtime Uninstaller")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt and proceed with deletion"
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("AgentCore Runtime Uninstallation Script")
    print("="*60)
    
    # Check config.json
    config = load_config()
    if not config:
        print("\nError: Cannot proceed without config.json")
        sys.exit(1)
    
    print(f"Configuration file loaded successfully")
    print(f"  - Project Name: {config.get('projectName')}")
    print(f"  - Region: {config.get('region')}")
    print(f"  - Account ID: {config.get('accountId')}")
    
    # Confirm deletion (skip if --yes flag is provided)
    if not args.yes:
        print("\n" + "="*60)
        print("WARNING: This will delete all resources created by installer.py")
        print("="*60)
        response = input("\nAre you sure you want to continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Uninstallation cancelled.")
            sys.exit(0)
    
    # Execute each step in reverse order
    steps = [
        ("Deleting AgentCore runtime", delete_agent_runtime),
        ("Deleting ECR repository", delete_ecr_repository),
        ("Deleting IAM role and policy", delete_iam_resources),
    ]
    
    for step_name, step_func in steps:
        if not step_func():
            print(f"\nWarning: Error occurred in step '{step_name}'.")
            print("   Continuing with remaining steps...")    

    # Output final results
    print("\n" + "="*60)
    print("Uninstallation process completed!")
    print("="*60)

if __name__ == "__main__":
    main()
