#!/usr/bin/env python3
"""
Unified uninstallation script
Sequentially deletes: AgentCore runtime -> ECR repository -> Knowledge Base resources -> Cognito resources -> IAM role -> IAM policy
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
                    # Try both repository_name and runtime_name (with underscores)
                    if agent_runtime['agentRuntimeName'] == runtime_name or agent_runtime['agentRuntimeName'] == repository_name:
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
                    print(f"Agent runtime {runtime_name} (or {repository_name}) not found (may already be deleted)")
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
    role_name = f"BedrockAgentCoreMCPRoleFor{projectName}"
    
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
    policy_name = f"BedrockAgentCoreMCPRoleFor{projectName}"
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
            # Note: Default version cannot be deleted directly; it will be deleted when the policy is deleted
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
            
            # Delete policy (this will automatically delete the default version)
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
# Cognito and Secrets Manager Deletion Functions
# ============================================================================

def delete_secrets_manager_secret(config):
    """Delete Secrets Manager secret"""
    try:
        aws_region = config.get('region')
        project_name = config.get('projectName')
        secret_name = config.get('secret_name')
        
        if not aws_region or not project_name:
            print("Error: Missing required configuration in config.json")
            return False
        
        if not secret_name:
            secret_name = f'{project_name.lower()}/credentials'
        
        try:
            secrets_client = boto3.client('secretsmanager', region_name=aws_region)
            
            # Check if secret exists
            try:
                secrets_client.describe_secret(SecretId=secret_name)
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print(f"Secrets Manager secret {secret_name} not found (may already be deleted)")
                    return True
                else:
                    print(f"Error checking secret: {e}")
                    return False
            
            # Delete secret
            try:
                secrets_client.delete_secret(
                    SecretId=secret_name,
                    ForceDeleteWithoutRecovery=True
                )
                print(f"✓ Secrets Manager secret deleted: {secret_name}")
                return True
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print(f"Secrets Manager secret {secret_name} not found (may already be deleted)")
                    return True
                else:
                    print(f"Error deleting secret: {e}")
                    return False
                    
        except Exception as e:
            print(f"Error deleting Secrets Manager secret: {e}")
            return False
            
    except Exception as e:
        print(f"Error deleting Secrets Manager secret: {e}")
        return False

def delete_cognito_test_user(config):
    """Delete Cognito test user"""
    try:
        aws_region = config.get('region')
        cognito_config = config.get('cognito', {})
        user_pool_id = cognito_config.get('user_pool_id')
        username = cognito_config.get('test_username')
        
        if not aws_region:
            print("Error: Missing required configuration in config.json")
            return False
        
        if not user_pool_id or not username:
            print("Cognito user pool ID or test username not found in config.json, skipping test user deletion")
            return True
        
        try:
            cognito_client = boto3.client('cognito-idp', region_name=aws_region)
            
            # Check if user exists
            try:
                cognito_client.admin_get_user(
                    UserPoolId=user_pool_id,
                    Username=username
                )
            except cognito_client.exceptions.UserNotFoundException:
                print(f"Cognito test user '{username}' not found (may already be deleted)")
                return True
            
            # Delete user
            cognito_client.admin_delete_user(
                UserPoolId=user_pool_id,
                Username=username
            )
            print(f"✓ Cognito test user deleted: {username}")
            return True
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'UserNotFoundException':
                print(f"Cognito test user '{username}' not found (may already be deleted)")
                return True
            else:
                print(f"Error deleting Cognito test user: {e}")
                return False
        except Exception as e:
            print(f"Error deleting Cognito test user: {e}")
            return False
            
    except Exception as e:
        print(f"Error deleting Cognito test user: {e}")
        return False

def delete_cognito_app_client(config):
    """Delete Cognito App Client"""
    try:
        aws_region = config.get('region')
        cognito_config = config.get('cognito', {})
        user_pool_id = cognito_config.get('user_pool_id')
        client_id = cognito_config.get('client_id')
        client_name = cognito_config.get('client_name')
        
        if not aws_region:
            print("Error: Missing required configuration in config.json")
            return False
        
        if not user_pool_id:
            print("Cognito user pool ID not found in config.json, skipping app client deletion")
            return True
        
        try:
            cognito_client = boto3.client('cognito-idp', region_name=aws_region)
            
            # If client_id is available, use it directly
            if client_id:
                try:
                    cognito_client.delete_user_pool_client(
                        UserPoolId=user_pool_id,
                        ClientId=client_id
                    )
                    print(f"✓ Cognito App Client deleted: {client_id}")
                    return True
                except ClientError as e:
                    if e.response['Error']['Code'] == 'ResourceNotFoundException':
                        print(f"Cognito App Client {client_id} not found (may already be deleted)")
                        return True
                    else:
                        print(f"Error deleting Cognito App Client: {e}")
                        return False
            
            # Otherwise, try to find by name
            if client_name:
                try:
                    response = cognito_client.list_user_pool_clients(UserPoolId=user_pool_id)
                    for client in response.get('UserPoolClients', []):
                        if client['ClientName'] == client_name:
                            cognito_client.delete_user_pool_client(
                                UserPoolId=user_pool_id,
                                ClientId=client['ClientId']
                            )
                            print(f"✓ Cognito App Client deleted: {client_name}")
                            return True
                    print(f"Cognito App Client {client_name} not found (may already be deleted)")
                    return True
                except Exception as e:
                    print(f"Error finding/deleting Cognito App Client: {e}")
                    return False
            
            print("Cognito App Client ID or name not found in config.json, skipping app client deletion")
            return True
                
        except Exception as e:
            print(f"Error deleting Cognito App Client: {e}")
            return False
            
    except Exception as e:
        print(f"Error deleting Cognito App Client: {e}")
        return False

def delete_cognito_identity_pool(config):
    """Delete Cognito Identity Pool"""
    try:
        aws_region = config.get('region')
        project_name = config.get('projectName')
        cognito_config = config.get('cognito', {})
        identity_pool_id = cognito_config.get('identity_pool_id')
        identity_pool_name = cognito_config.get('identity_pool_name')
        
        if not aws_region or not project_name:
            print("Error: Missing required configuration in config.json")
            return False
        
        if not identity_pool_name:
            identity_pool_name = f"{project_name}-agentcore-identity-pool"
        
        try:
            identity_client = boto3.client('cognito-identity', region_name=aws_region)
            
            # If identity_pool_id is available, use it directly
            if identity_pool_id:
                try:
                    identity_client.delete_identity_pool(IdentityPoolId=identity_pool_id)
                    print(f"✓ Cognito Identity Pool deleted: {identity_pool_id}")
                    return True
                except ClientError as e:
                    if e.response['Error']['Code'] == 'ResourceNotFoundException':
                        print(f"Cognito Identity Pool {identity_pool_id} not found (may already be deleted)")
                        return True
                    else:
                        print(f"Error deleting Cognito Identity Pool: {e}")
                        return False
            
            # Otherwise, try to find by name
            try:
                response = identity_client.list_identity_pools(MaxResults=60)
                for pool in response.get('IdentityPools', []):
                    if pool['IdentityPoolName'] == identity_pool_name:
                        identity_client.delete_identity_pool(IdentityPoolId=pool['IdentityPoolId'])
                        print(f"✓ Cognito Identity Pool deleted: {identity_pool_name}")
                        return True
                print(f"Cognito Identity Pool {identity_pool_name} not found (may already be deleted)")
                return True
            except Exception as e:
                print(f"Error finding/deleting Cognito Identity Pool: {e}")
                return False
                
        except Exception as e:
            print(f"Error deleting Cognito Identity Pool: {e}")
            return False
            
    except Exception as e:
        print(f"Error deleting Cognito Identity Pool: {e}")
        return False

def delete_cognito_user_pool(config):
    """Delete Cognito User Pool"""
    try:
        aws_region = config.get('region')
        project_name = config.get('projectName')
        cognito_config = config.get('cognito', {})
        user_pool_id = cognito_config.get('user_pool_id')
        user_pool_name = cognito_config.get('user_pool_name')
        
        if not aws_region or not project_name:
            print("Error: Missing required configuration in config.json")
            return False
        
        if not user_pool_name:
            user_pool_name = f"{project_name}-agentcore-user-pool"
        
        try:
            cognito_client = boto3.client('cognito-idp', region_name=aws_region)
            
            # If user_pool_id is available, use it directly
            if user_pool_id:
                try:
                    cognito_client.delete_user_pool(UserPoolId=user_pool_id)
                    print(f"✓ Cognito User Pool deleted: {user_pool_id}")
                    return True
                except ClientError as e:
                    if e.response['Error']['Code'] == 'ResourceNotFoundException':
                        print(f"Cognito User Pool {user_pool_id} not found (may already be deleted)")
                        return True
                    else:
                        print(f"Error deleting Cognito User Pool: {e}")
                        return False
            
            # Otherwise, try to find by name
            try:
                response = cognito_client.list_user_pools(MaxResults=60)
                for pool in response.get('UserPools', []):
                    if pool['Name'] == user_pool_name:
                        cognito_client.delete_user_pool(UserPoolId=pool['Id'])
                        print(f"✓ Cognito User Pool deleted: {user_pool_name}")
                        return True
                print(f"Cognito User Pool {user_pool_name} not found (may already be deleted)")
                return True
            except Exception as e:
                print(f"Error finding/deleting Cognito User Pool: {e}")
                return False
                
        except Exception as e:
            print(f"Error deleting Cognito User Pool: {e}")
            return False
            
    except Exception as e:
        print(f"Error deleting Cognito User Pool: {e}")
        return False

def delete_cognito_resources():
    """Delete all Cognito and Secrets Manager resources"""
    print(f"\n{'='*60}")
    print("Deleting Cognito and Secrets Manager resources")
    print(f"{'='*60}")
    
    try:
        config = load_config()
        if not config:
            return False
        
        aws_region = config.get('region')
        project_name = config.get('projectName')
        
        if not all([aws_region, project_name]):
            print("Error: Missing required configuration in config.json")
            print("Required: region, projectName")
            return False
        
        # Delete in reverse order of creation (respecting dependencies)
        # This order ensures that dependent resources are deleted before their dependencies
        steps = [
            ("1. Deleting Secrets Manager secret", lambda: delete_secrets_manager_secret(config)),
            ("2. Deleting Cognito test user", lambda: delete_cognito_test_user(config)),
            ("3. Deleting Cognito App Client", lambda: delete_cognito_app_client(config)),
            ("4. Deleting Cognito Identity Pool", lambda: delete_cognito_identity_pool(config)),
            ("5. Deleting Cognito User Pool", lambda: delete_cognito_user_pool(config)),
        ]
        
        success_count = 0
        for step_name, step_func in steps:
            print(f"\n{step_name}...")
            if step_func():
                success_count += 1
            else:
                print(f"Warning: Failed to complete step '{step_name}'")
        
        print(f"\n✓ Cognito and Secrets Manager resources deletion completed ({success_count}/{len(steps)} steps successful)")
        return True
        
    except Exception as e:
        print(f"Error deleting Cognito and Secrets Manager resources: {e}")
        return False

# ============================================================================
# Knowledge Base Deletion Functions
# ============================================================================

def delete_data_source(config):
    """Delete Knowledge Base data source and wait for deletion to complete"""
    try:
        aws_region = config.get('region')
        project_name = config.get('projectName')
        knowledge_base_id = config.get('knowledge_base_id')
        data_source_name = config.get('data_source_name')
        
        if not all([aws_region, project_name]):
            print("Error: Missing required configuration in config.json")
            return False
        
        if not knowledge_base_id:
            print("Knowledge base ID not found in config.json, skipping data source deletion")
            return True
        
        if not data_source_name:
            data_source_name = f"data-source-for-{project_name}-{aws_region}"
        
        try:
            bedrock_agent = boto3.client('bedrock-agent', region_name=aws_region)
            
            # List data sources to find the data source ID
            response = bedrock_agent.list_data_sources(knowledgeBaseId=knowledge_base_id)
            data_sources = response.get('dataSources', [])
            
            data_source_id = None
            for data_source in data_sources:
                if data_source.get('dataSourceName') == data_source_name:
                    data_source_id = data_source.get('dataSourceId')
                    break
            
            if data_source_id:
                bedrock_agent.delete_data_source(
                    knowledgeBaseId=knowledge_base_id,
                    dataSourceId=data_source_id
                )
                print(f"✓ Data source deletion requested: {data_source_name}")
                
                # Wait for data source deletion to complete
                print(f"Waiting for data source '{data_source_name}' to be deleted...")
                max_wait_time = 300  # 5 minutes
                start_time = time.time()
                check_count = 0
                
                while True:
                    check_count += 1
                    elapsed_time = time.time() - start_time
                    
                    try:
                        response = bedrock_agent.list_data_sources(knowledgeBaseId=knowledge_base_id)
                        data_sources = response.get('dataSources', [])
                        
                        # Check if the data source still exists
                        data_source_exists = False
                        for ds in data_sources:
                            if ds.get('dataSourceId') == data_source_id:
                                data_source_exists = True
                                break
                        
                        if not data_source_exists:
                            print(f"✓ Data source '{data_source_name}' has been successfully deleted")
                            print(f"  (Checked {check_count} times, elapsed time: {elapsed_time:.1f} seconds)")
                            return True
                        
                        # Check timeout
                        if elapsed_time >= max_wait_time:
                            print(f"\nTimeout: Data source '{data_source_name}' still exists after {max_wait_time} seconds")
                            print("  Continuing with next step...")
                            return True  # Continue even if timeout
                        
                        # Wait 5 seconds before next check
                        if check_count % 6 == 0:  # Print every 30 seconds
                            print(f"  [{check_count}] Data source still exists, waiting... (elapsed: {elapsed_time:.1f}s)")
                        time.sleep(5)
                        
                    except Exception as e:
                        # If we can't list data sources, assume it's deleted
                        print(f"  Could not verify data source status (may be deleted): {e}")
                        return True
                
            else:
                print(f"Data source {data_source_name} not found (may already be deleted)")
                return True
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print(f"Data source {data_source_name} not found (may already be deleted)")
                return True
            else:
                print(f"Error deleting data source: {e}")
                return False
        except Exception as e:
            print(f"Error deleting data source: {e}")
            return False
            
    except Exception as e:
        print(f"Error deleting data source: {e}")
        return False

def delete_knowledge_base(config):
    """Delete Knowledge Base and wait for deletion to complete"""
    try:
        aws_region = config.get('region')
        project_name = config.get('projectName')
        knowledge_base_id = config.get('knowledge_base_id')
        
        if not all([aws_region, project_name]):
            print("Error: Missing required configuration in config.json")
            return False
        
        if not knowledge_base_id:
            # Try to find by name
            knowledge_base_name = project_name
            try:
                bedrock_agent = boto3.client('bedrock-agent', region_name=aws_region)
                response = bedrock_agent.list_knowledge_bases(maxResults=50)
                knowledge_bases = response.get('knowledgeBaseSummaries', [])
                
                for kb in knowledge_bases:
                    if kb['name'] == knowledge_base_name:
                        knowledge_base_id = kb['knowledgeBaseId']
                        break
            except Exception as e:
                print(f"Warning: Could not find knowledge base by name: {e}")
        
        if not knowledge_base_id:
            print("Knowledge base ID not found in config.json, skipping knowledge base deletion")
            return True
        
        try:
            bedrock_agent = boto3.client('bedrock-agent', region_name=aws_region)
            bedrock_agent.delete_knowledge_base(knowledgeBaseId=knowledge_base_id)
            print(f"✓ Knowledge base deletion requested: {knowledge_base_id}")
            
            # Wait for knowledge base deletion to complete
            print(f"Waiting for Knowledge Base '{knowledge_base_id}' to be deleted...")
            max_wait_time = 600  # 10 minutes
            start_time = time.time()
            check_count = 0
            
            while True:
                check_count += 1
                elapsed_time = time.time() - start_time
                
                try:
                    response = bedrock_agent.list_knowledge_bases(maxResults=50)
                    knowledge_bases = response.get('knowledgeBaseSummaries', [])
                    
                    # Check if the knowledge base still exists
                    kb_exists = False
                    for kb in knowledge_bases:
                        if kb['knowledgeBaseId'] == knowledge_base_id:
                            kb_exists = True
                            break
                    
                    if not kb_exists:
                        print(f"✓ Knowledge Base '{knowledge_base_id}' has been successfully deleted")
                        print(f"  (Checked {check_count} times, elapsed time: {elapsed_time:.1f} seconds)")
                        return True
                    
                    # Check timeout
                    if elapsed_time >= max_wait_time:
                        print(f"\nTimeout: Knowledge Base '{knowledge_base_id}' still exists after {max_wait_time} seconds")
                        print("  Continuing with next step...")
                        return True  # Continue even if timeout
                    
                    # Wait 10 seconds before next check
                    if check_count % 6 == 0:  # Print every 60 seconds
                        print(f"  [{check_count}] Knowledge Base still exists, waiting... (elapsed: {elapsed_time:.1f}s)")
                    time.sleep(10)
                    
                except Exception as e:
                    # If we can't list knowledge bases, assume it's deleted
                    print(f"  Could not verify Knowledge Base status (may be deleted): {e}")
                    return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print(f"Knowledge base {knowledge_base_id} not found (may already be deleted)")
                return True
            else:
                print(f"Error deleting knowledge base: {e}")
                return False
        except Exception as e:
            print(f"Error deleting knowledge base: {e}")
            return False
            
    except Exception as e:
        print(f"Error deleting knowledge base: {e}")
        return False

def delete_s3_vector_index(config):
    """Delete S3 Vector Index and wait for deletion to complete"""
    try:
        aws_region = config.get('region')
        project_name = config.get('projectName')
        account_id = config.get('accountId')
        s3_vector_bucket_name = config.get('s3_vector_bucket_name')
        s3_vector_index_name = config.get('s3_vector_index_name')
        
        if not all([aws_region, project_name, account_id]):
            print("Error: Missing required configuration in config.json")
            return False
        
        if not s3_vector_bucket_name:
            s3_vector_bucket_name = f"s3-vector-for-{project_name}-{account_id}-{aws_region}"
        
        if not s3_vector_index_name:
            s3_vector_index_name = f"s3-vector-index-for-{project_name}-{account_id}-{aws_region}"
        
        try:
            s3vectors_client = boto3.client('s3vectors', region_name=aws_region)
            
            # List indexes to find the index
            try:
                response = s3vectors_client.list_indexes(vectorBucketName=s3_vector_bucket_name)
                indexes = response.get('indexes', [])
                
                index_arn = None
                for index in indexes:
                    if index.get('indexName') == s3_vector_index_name:
                        index_arn = index.get('indexArn')
                        break
                
                if index_arn:
                    s3vectors_client.delete_index(indexArn=index_arn)
                    print(f"✓ S3 Vector index deletion requested: {s3_vector_index_name}")
                    
                    # Wait for index deletion to complete
                    print(f"Waiting for S3 Vector index '{s3_vector_index_name}' to be deleted...")
                    max_wait_time = 300  # 5 minutes
                    start_time = time.time()
                    check_count = 0
                    
                    while True:
                        check_count += 1
                        elapsed_time = time.time() - start_time
                        
                        try:
                            response = s3vectors_client.list_indexes(vectorBucketName=s3_vector_bucket_name)
                            indexes = response.get('indexes', [])
                            
                            # Check if the index still exists
                            index_exists = False
                            for idx in indexes:
                                if idx.get('indexArn') == index_arn or idx.get('indexName') == s3_vector_index_name:
                                    index_exists = True
                                    break
                            
                            if not index_exists:
                                print(f"✓ S3 Vector index '{s3_vector_index_name}' has been successfully deleted")
                                print(f"  (Checked {check_count} times, elapsed time: {elapsed_time:.1f} seconds)")
                                return True
                            
                            # Check timeout
                            if elapsed_time >= max_wait_time:
                                print(f"\nTimeout: S3 Vector index '{s3_vector_index_name}' still exists after {max_wait_time} seconds")
                                print("  Continuing with next step...")
                                return True  # Continue even if timeout
                            
                            # Wait 5 seconds before next check
                            if check_count % 6 == 0:  # Print every 30 seconds
                                print(f"  [{check_count}] Index still exists, waiting... (elapsed: {elapsed_time:.1f}s)")
                            time.sleep(5)
                            
                        except Exception as e:
                            # If we can't list indexes, assume it's deleted
                            print(f"  Could not verify index status (may be deleted): {e}")
                            return True
                else:
                    print(f"S3 Vector index {s3_vector_index_name} not found (may already be deleted)")
                    return True
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print(f"S3 Vector bucket {s3_vector_bucket_name} not found, skipping index deletion")
                    return True
                else:
                    raise
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print(f"S3 Vector index {s3_vector_index_name} not found (may already be deleted)")
                return True
            else:
                print(f"Error deleting S3 Vector index: {e}")
                return False
        except Exception as e:
            print(f"Error deleting S3 Vector index: {e}")
            return False
            
    except Exception as e:
        print(f"Error deleting S3 Vector index: {e}")
        return False

def delete_s3_vector_bucket(config):
    """Delete S3 Vector Bucket"""
    try:
        aws_region = config.get('region')
        project_name = config.get('projectName')
        account_id = config.get('accountId')
        s3_vector_bucket_name = config.get('s3_vector_bucket_name')
        
        if not all([aws_region, project_name, account_id]):
            print("Error: Missing required configuration in config.json")
            return False
        
        if not s3_vector_bucket_name:
            s3_vector_bucket_name = f"s3-vector-for-{project_name}-{account_id}-{aws_region}"
        
        try:
            s3vectors_client = boto3.client('s3vectors', region_name=aws_region)
            
            # List vector buckets to find the bucket ARN
            response = s3vectors_client.list_vector_buckets(maxResults=50)
            vector_buckets = response.get('vectorBuckets', [])
            
            bucket_arn = None
            for bucket in vector_buckets:
                if bucket.get('vectorBucketName') == s3_vector_bucket_name:
                    bucket_arn = bucket.get('vectorBucketArn')
                    break
            
            if bucket_arn:
                s3vectors_client.delete_vector_bucket(vectorBucketArn=bucket_arn)
                print(f"✓ S3 Vector bucket deleted: {s3_vector_bucket_name}")
                return True
            else:
                print(f"S3 Vector bucket {s3_vector_bucket_name} not found (may already be deleted)")
                return True
                
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print(f"S3 Vector bucket {s3_vector_bucket_name} not found (may already be deleted)")
                return True
            else:
                print(f"Error deleting S3 Vector bucket: {e}")
                return False
        except Exception as e:
            print(f"Error deleting S3 Vector bucket: {e}")
            return False
            
    except Exception as e:
        print(f"Error deleting S3 Vector bucket: {e}")
        return False

def delete_knowledge_base_role(config):
    """Delete Knowledge Base IAM role and inline policy"""
    try:
        aws_region = config.get('region')
        project_name = config.get('projectName')
        role_name = f"role-knowledge-base-for-{project_name}-{aws_region}"
        policy_name = f"knowledge-base-for-{project_name}-{aws_region}"
        
        if not all([aws_region, project_name]):
            print("Error: Missing required configuration in config.json")
            return False
        
        try:
            iam_client = boto3.client('iam')
            
            # Check if role exists
            try:
                existing_role = iam_client.get_role(RoleName=role_name)
                role_arn = existing_role['Role']['Arn']
                
                # Delete inline policy
                try:
                    iam_client.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
                    print(f"✓ Deleted inline policy: {policy_name}")
                except ClientError as e:
                    if e.response['Error']['Code'] == 'NoSuchEntity':
                        print(f"Inline policy {policy_name} not found (may already be deleted)")
                    else:
                        print(f"Warning: Failed to delete inline policy {policy_name}: {e}")
                
                # Delete role
                iam_client.delete_role(RoleName=role_name)
                print(f"✓ Knowledge Base IAM role deleted: {role_arn}")
                return True
                
            except iam_client.exceptions.NoSuchEntityException:
                print(f"Knowledge Base IAM role {role_name} not found (may already be deleted)")
                return True
                
        except Exception as e:
            print(f"Error deleting Knowledge Base role: {e}")
            return False
            
    except Exception as e:
        print(f"Error deleting Knowledge Base role: {e}")
        return False

def delete_s3_bucket(config):
    """Delete S3 bucket for Knowledge Base storage"""
    try:
        aws_region = config.get('region')
        project_name = config.get('projectName')
        account_id = config.get('accountId')
        bucket_name = config.get('bucket_name')
        
        if not all([aws_region, project_name, account_id]):
            print("Error: Missing required configuration in config.json")
            return False
        
        if not bucket_name:
            bucket_name = f"storage-for-{project_name}-{account_id}-{aws_region}"
        
        try:
            s3_client = boto3.client('s3', region_name=aws_region)
            
            # Check if bucket exists
            try:
                s3_client.head_bucket(Bucket=bucket_name)
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    print(f"S3 bucket {bucket_name} not found (may already be deleted)")
                    return True
                else:
                    print(f"Error checking bucket: {e}")
                    return False
            
            # List and delete all objects
            try:
                paginator = s3_client.get_paginator('list_objects_v2')
                pages = paginator.paginate(Bucket=bucket_name)
                
                for page in pages:
                    if 'Contents' in page:
                        objects = [{'Key': obj['Key']} for obj in page['Contents']]
                        if objects:
                            s3_client.delete_objects(
                                Bucket=bucket_name,
                                Delete={'Objects': objects}
                            )
                            print(f"✓ Deleted {len(objects)} objects from bucket")
            except Exception as e:
                print(f"Warning: Error deleting objects from bucket: {e}")
            
            # Delete bucket
            try:
                s3_client.delete_bucket(Bucket=bucket_name)
                print(f"✓ S3 bucket deleted: {bucket_name}")
                return True
            except ClientError as e:
                if e.response['Error']['Code'] == 'NoSuchBucket':
                    print(f"S3 bucket {bucket_name} not found (may already be deleted)")
                    return True
                else:
                    print(f"Error deleting bucket: {e}")
                    return False
                    
        except Exception as e:
            print(f"Error deleting S3 bucket: {e}")
            return False
            
    except Exception as e:
        print(f"Error deleting S3 bucket: {e}")
        return False

def delete_knowledge_base_resources():
    """Delete all Knowledge Base related resources created by installer.py"""
    print(f"\n{'='*60}")
    print("Deleting Knowledge Base resources")
    print(f"{'='*60}")
    
    try:
        config = load_config()
        if not config:
            return False
        
        # Check if knowledge base removal is enabled
        is_removed = config.get('is_removed', False)
        if not is_removed:
            print("Knowledge Base removal is disabled (is_removed=False)")
            print("Skipping Knowledge Base resources deletion")
            return True
        
        aws_region = config.get('region')
        project_name = config.get('projectName')
        
        if not all([aws_region, project_name]):
            print("Error: Missing required configuration in config.json")
            print("Required: region, projectName")
            return False
        
        # Delete in reverse order of creation (respecting dependencies)
        # This order ensures that dependent resources are deleted before their dependencies
        steps = [
            ("1. Deleting data source", lambda: delete_data_source(config)),
            ("2. Deleting knowledge base", lambda: delete_knowledge_base(config)),
            ("3. Deleting S3 Vector index", lambda: delete_s3_vector_index(config)),
            ("4. Deleting S3 Vector bucket", lambda: delete_s3_vector_bucket(config)),
            ("5. Deleting Knowledge Base IAM role", lambda: delete_knowledge_base_role(config)),
            ("6. Deleting S3 bucket", lambda: delete_s3_bucket(config)),
        ]
        
        success_count = 0
        for step_name, step_func in steps:
            print(f"\n{step_name}...")
            if step_func():
                success_count += 1
            else:
                print(f"Warning: Failed to complete step '{step_name}'")
        
        print(f"\n✓ Knowledge Base resources deletion completed ({success_count}/{len(steps)} steps successful)")
        return True
        
    except Exception as e:
        print(f"Error deleting Knowledge Base resources: {e}")
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
    print(f"  - Knowledge Base removal: {config.get('is_removed', False)}")
    
    # Confirm deletion (skip if --yes flag is provided)
    if not args.yes:
        print("\n" + "="*60)
        print("WARNING: This will delete all resources created by installer.py")
        print("="*60)
        response = input("\nAre you sure you want to continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Uninstallation cancelled.")
            sys.exit(0)
    
    # Execute each step in reverse order of creation (respecting dependencies)
    # This ensures that resources that depend on others are deleted first
    steps = [
        ("1. Deleting AgentCore runtime", delete_agent_runtime),
        ("2. Deleting ECR repository", delete_ecr_repository),
        ("3. Deleting Knowledge Base resources", delete_knowledge_base_resources),
        ("4. Deleting Cognito and Secrets Manager resources", delete_cognito_resources),
        ("5. Deleting IAM role and policy", delete_iam_resources),
    ]
    
    success_count = 0
    for step_name, step_func in steps:
        if step_func():
            success_count += 1
        else:
            print(f"\nWarning: Error occurred in step '{step_name}'.")
            print("   Continuing with remaining steps...")
    
    print(f"\nCompleted {success_count}/{len(steps)} main steps")    

    # Output final results
    print("\n" + "="*60)
    print("Uninstallation process completed!")
    print("="*60)

if __name__ == "__main__":
    main()
