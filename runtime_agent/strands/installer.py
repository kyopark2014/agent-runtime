#!/usr/bin/env python3
"""
Unified installation script
Sequentially executes: IAM policy creation -> Docker image build and ECR push -> AgentCore runtime creation/update
All functionality integrated into a single file
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

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.json")

def load_config():
    """Load config.json file."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        print(f"Failed to parse config.json file: {e}")
        config = {}
        session = boto3.Session()
        region = session.region_name
        config['region'] = region
        config['projectName'] = "agent-runtime"
        
        sts = boto3.client("sts")
        response = sts.get_caller_identity()
        accountId = response["Account"]
        config['accountId'] = accountId
        
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    
    return config

def update_config(key, value):
    """Update config.json with a key-value pair."""
    try:
        config = load_config()
        config[key] = value
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"Error updating config: {e}")
        return False

# ============================================================================
# IAM Policy and Role Creation Functions
# ============================================================================

def create_bedrock_agentcore_policy(config):
    """Create IAM policy for Bedrock AgentCore access"""
    region = config['region']
    accountId = config['accountId']
    projectName = config.get('projectName', 'agentcore')
    
    policy_name = f"AmazonBedrockAgentCoreRuntimePolicyFor{projectName}"
    policy_description = f"Policy for accessing Bedrock AgentCore Runtime endpoints"
    
    # Comprehensive policy document for Bedrock AgentCore access
    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "BedrockAgentAccess",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:*"
                ],
                "Resource": [
                    "*"
                ]
            },
            {
                "Sid": "SecretsManagerAccess",
                "Effect": "Allow",
                "Action": [
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret",
                    "secretsmanager:UpdateSecret",
                    "secretsmanager:CreateSecret",
                    "secretsmanager:PutSecretValue"
                ],
                "Resource": [
                    f"arn:aws:secretsmanager:{region}:*:secret:{projectName}/cognito/credentials*",
                    f"arn:aws:secretsmanager:{region}:*:secret:{projectName}/credentials*"
                ]
            },
            {
                "Sid": "CognitoAccess",
                "Effect": "Allow",
                "Action": [
                    "cognito-idp:*"
                ],
                "Resource": "*"
            },
            {
                "Sid": "ECRAccess",
                "Effect": "Allow",
                "Action": [
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchGetImage",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:DescribeRepositories",
                    "ecr:ListImages",
                    "ecr:DescribeImages"
                ],
                "Resource": "*"
            },
            {
                "Sid": "LogsAccess",
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams"
                ],
                "Resource": [
                    f"arn:aws:logs:{region}:*:log-group:/aws/bedrock-agentcore/*",
                    f"arn:aws:logs:{region}:*:log-group:/aws/bedrock-agentcore/*:log-stream:*"
                ]
            },
            {
                "Sid": "CloudWatchAccess",
                "Effect": "Allow",
                "Action": [
                    'cloudwatch:ListMetrics', 
                    'cloudwatch:GetMetricData',
                    'cloudwatch:GetMetricStatistics',
                    'cloudwatch:GetMetricWidgetImage',
                    'cloudwatch:GetMetricData',
                    'cloudwatch:GetMetricData',
                    'xray:PutTraceSegments',
                    'xray:PutTelemetryRecords',
                    'xray:PutAttributes',
                    'xray:GetTraceSummaries',
                    'logs:CreateLogGroup',
                    'logs:DescribeLogStreams', 
                    'logs:DescribeLogGroups', 
                    'logs:CreateLogStream', 
                    'logs:PutLogEvents'
                ],
                "Resource": "*"
            },
            {
                "Sid": "S3Access",
                "Effect": "Allow",
                "Action": [
                    "s3:*",
                    "bedrock:*"
                ],
                "Resource": "*"
            },
            {
                "Sid": "EC2Access",
                "Effect": "Allow",
                "Action": [
                    "ec2:*"
                ],
                "Resource": "*"
            }
        ]
    }
    
    try:
        iam_client = boto3.client('iam')
        
        # Check if policy already exists
        try:
            existing_policy = iam_client.get_policy(PolicyArn=f"arn:aws:iam::{accountId}:policy/{policy_name}")
            print(f"Existing policy found: {existing_policy['Policy']['Arn']}")
            
            # List all policy versions
            versions_response = iam_client.list_policy_versions(PolicyArn=existing_policy['Policy']['Arn'])
            versions = versions_response['Versions']
            
            # If we have 5 versions, delete the oldest non-default version
            if len(versions) >= 5:
                print(f"Policy has {len(versions)} versions, cleaning up old versions...")
                
                # Find non-default versions to delete
                non_default_versions = [v for v in versions if not v['IsDefaultVersion']]
                
                if non_default_versions:
                    # Delete the oldest non-default version
                    oldest_version = non_default_versions[0]
                    iam_client.delete_policy_version(
                        PolicyArn=existing_policy['Policy']['Arn'],
                        VersionId=oldest_version['VersionId']
                    )
                    print(f"✓ Deleted old policy version: {oldest_version['VersionId']}")
                else:
                    # If all versions are default, we need to set a different version as default first
                    for version in versions[1:]:  # Skip the current default
                        try:
                            iam_client.set_default_policy_version(
                                PolicyArn=existing_policy['Policy']['Arn'],
                                VersionId=version['VersionId']
                            )
                            # Now delete the old default
                            iam_client.delete_policy_version(
                                PolicyArn=existing_policy['Policy']['Arn'],
                                VersionId=versions[0]['VersionId']
                            )
                            print(f"✓ Switched default version and deleted old version: {versions[0]['VersionId']}")
                            break
                        except Exception as e:
                            print(f"Failed to switch version {version['VersionId']}: {e}")
                            continue
            
            # Create policy version
            response = iam_client.create_policy_version(
                PolicyArn=existing_policy['Policy']['Arn'],
                PolicyDocument=json.dumps(policy_document),
                SetAsDefault=True
            )
            print(f"✓ Policy update completed: {response['PolicyVersion']['VersionId']}")
            return existing_policy['Policy']['Arn']
            
        except iam_client.exceptions.NoSuchEntityException:
            # Create new policy
            response = iam_client.create_policy(
                PolicyName=policy_name,
                PolicyDocument=json.dumps(policy_document),
                Description=policy_description
            )
            print(f"✓ New policy created: {response['Policy']['Arn']}")
            return response['Policy']['Arn']
            
    except Exception as e:
        print(f"Policy creation failed: {e}")
        return None

def attach_policy_to_role(role_name, policy_arn):
    """Attach policy to IAM role"""
    try:
        iam_client = boto3.client('iam')
        
        # Attach policy to role
        response = iam_client.attach_role_policy(
            RoleName=role_name,
            PolicyArn=policy_arn
        )
        print(f"✓ Policy attached successfully: {policy_arn}")
        return True
        
    except Exception as e:
        print(f"Policy attachment failed: {e}")
        return False

def create_trust_policy_for_bedrock(config):
    """Create trust policy for Bedrock AgentCore"""
    accountId = config['accountId']
    
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "bedrock-agentcore.amazonaws.com"
                },
                "Action": "sts:AssumeRole"
            },
            {
                "Effect": "Allow",
                "Principal": {
                    "AWS": f"arn:aws:iam::{accountId}:root"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    return trust_policy

def create_bedrock_agentcore_role(config):
    """Create IAM role for Bedrock AgentCore MCP access"""
    projectName = config.get('projectName', 'agentcore')
    role_name = f"AmazonBedrockAgentCoreRuntimeRoleFor{projectName}"
    policy_arn = create_bedrock_agentcore_policy(config)
    
    if not policy_arn:
        print("Role creation aborted due to policy creation failure")
        return None
    
    try:
        iam_client = boto3.client('iam')
        
        # Check if role already exists
        try:
            existing_role = iam_client.get_role(RoleName=role_name)
            print(f"Existing role found: {existing_role['Role']['Arn']}")
            
            # Update trust policy
            trust_policy = create_trust_policy_for_bedrock(config)
            iam_client.update_assume_role_policy(
                RoleName=role_name,
                PolicyDocument=json.dumps(trust_policy)
            )
            print("✓ Trust policy updated successfully")
            
            # Attach policy
            attach_policy_to_role(role_name, policy_arn)
            
            return existing_role['Role']['Arn']
            
        except iam_client.exceptions.NoSuchEntityException:
            # Create new role
            trust_policy = create_trust_policy_for_bedrock(config)
            
            response = iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description="Role for Bedrock AgentCore MCP access"
            )
            print(f"✓ New role created: {response['Role']['Arn']}")
            
            # Attach policy
            attach_policy_to_role(role_name, policy_arn)
            
            return response['Role']['Arn']
            
    except Exception as e:
        print(f"Role creation failed: {e}")
        return None

def create_iam_policies():
    """Create IAM policies and roles"""
    print(f"\n{'='*60}")
    print("Creating IAM policies and roles")
    print(f"{'='*60}")
    
    try:
        config = load_config()
        
        # Create Bedrock AgentCore policy
        print("\n1. Creating Bedrock AgentCore policy...")
        policy_arn = create_bedrock_agentcore_policy(config)
        
        # Create Bedrock AgentCore role
        print("\n2. Creating Bedrock AgentCore role...")
        role_arn = create_bedrock_agentcore_role(config)
        
        if not role_arn:
            print("Role creation failed")
            return False
        
        # Update AgentCore configuration
        print("\n3. Updating AgentCore configuration...")
        update_config('agent_runtime_role', role_arn)
        print(f"✓ AgentCore configuration updated: {role_arn}")
        
        print("\n✓ IAM policies and roles creation completed")
        return True
        
    except Exception as e:
        print(f"Error creating IAM policies: {e}")
        return False

# ============================================================================
# Docker Build and ECR Push Functions
# ============================================================================

def check_aws_cli():
    """Check if AWS CLI is installed."""
    if not shutil.which("aws"):
        print("Error: AWS CLI is not installed")
        return False
    return True

def check_aws_credentials():
    """Check AWS credentials."""
    try:
        sts = boto3.client("sts")
        sts.get_caller_identity()
        return True
    except NoCredentialsError:
        print("Error: AWS credentials are not configured properly")
        return False
    except Exception as e:
        print(f"Error: Failed to verify AWS credentials: {e}")
        return False

def ensure_ecr_repository(ecr_client, repository_name, region):
    """Check if ECR repository exists, create if it doesn't."""
    try:
        ecr_client.describe_repositories(repositoryNames=[repository_name])
        print(f"Repository {repository_name} exists.")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'RepositoryNotFoundException':
            print(f"Repository {repository_name} does not exist. Creating it...")
            try:
                ecr_client.create_repository(repositoryName=repository_name)
                print(f"Repository {repository_name} created successfully.")
                return True
            except Exception as create_error:
                print(f"Error: Failed to create repository: {create_error}")
                return False
        else:
            print(f"Error: Failed to check repository: {e}")
            return False

def docker_login(account_id, region):
    """Login to AWS ECR using Docker."""
    ecr_registry = f"{account_id}.dkr.ecr.{region}.amazonaws.com"
    
    try:
        ecr_client = boto3.client("ecr", region_name=region)
        token_response = ecr_client.get_authorization_token()
        token = token_response['authorizationData'][0]['authorizationToken']
        
        # Decode base64 token
        username, password = base64.b64decode(token).decode('utf-8').split(':')
        
        # Login to Docker
        login_cmd = [
            "docker", "login",
            "--username", username,
            "--password-stdin",
            ecr_registry
        ]
        
        process = subprocess.Popen(
            login_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input=password)
        
        if process.returncode != 0:
            print(f"Error: Docker login failed: {stderr}")
            return False
        
        return True
            
    except Exception as e:
        print(f"Error: Failed to login to ECR: {e}")
        return False

def run_docker_command(command, description):
    """Run Docker command and handle errors."""
    print(f"===== {description} =====")
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=False,
            text=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: {description} failed: {e}")
        return False
    except Exception as e:
        print(f"Error: {description} failed: {e}")
        return False

def push_to_ecr():
    """Build Docker image and push to ECR"""
    print(f"\n{'='*60}")
    print("Building Docker image and pushing to ECR")
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
        
        # Build Docker image
        if not run_docker_command(
            ["docker", "build", "-t", f"{ecr_repository}:{image_tag}", "."],
            "Building Docker Image"
        ):
            return False
        
        # Tag for ECR repository
        if not run_docker_command(
            ["docker", "tag", f"{ecr_repository}:{image_tag}", ecr_uri],
            "Tagging for ECR Repository"
        ):
            return False
        
        # Push to ECR
        if not run_docker_command(
            ["docker", "push", ecr_uri],
            "Pushing Image to ECR Repository"
        ):
            return False
        
        # Complete
        print("===== Complete =====")
        print("Image has been successfully built and pushed to ECR.")
        print(f"Image URI: {ecr_uri}")
        
        # Store image tag in config for later use
        update_config('latest_image_tag', image_tag)
        update_config('ecr_repository', ecr_repository)
        
        return True
        
    except Exception as e:
        print(f"Error building and pushing Docker image: {e}")
        return False

# ============================================================================
# Agent Runtime Creation/Update Functions
# ============================================================================

def get_latest_image_tag(config):
    """Get the latest image tag from ECR."""
    try:
        aws_region = config['region']
        project_name = config.get('projectName')
        current_folder_name = os.path.basename(os.getcwd())
        repository_name = f"{project_name}_{current_folder_name}"
        
        ecr_client = boto3.client('ecr', region_name=aws_region)
        response = ecr_client.describe_images(repositoryName=repository_name)
        images = response['imageDetails']
        
        if not images:
            print(f"Error: No images found in repository {repository_name}")
            return None
        
        # Get latest image
        images_sorted = sorted(images, key=lambda x: x['imagePushedAt'], reverse=True)
        latest_image = images_sorted[0]
        
        if 'imageTags' not in latest_image or not latest_image['imageTags']:
            print(f"Error: Latest image has no tags")
            return None
        
        image_tag = latest_image['imageTags'][0]
        print(f"Latest image tag: {image_tag}")
        return image_tag
        
    except Exception as e:
        print(f"Error getting latest image tag: {e}")
        return None

def update_agentcore_json(agent_runtime_arn):
    """Update config.json with agent runtime ARN."""
    try:
        update_config('agent_runtime_arn', agent_runtime_arn)
        print(f"✓ config.json updated with agent_runtime_arn: {agent_runtime_arn}")
        return True
    except Exception as e:
        print(f"Error updating config.json: {e}")
        return False

def create_agent_runtime_func(config, repository_name, image_tag):
    """Create a new Agent Runtime."""
    aws_region = config['region']
    account_id = config['accountId']
    agent_runtime_role = config.get('agent_runtime_role')
    
    if not agent_runtime_role:
        print("Error: agent_runtime_role not found in config.json")
        return None
    
    # Replace hyphens with underscores for agent runtime name (AWS validation requirement)
    runtime_name = repository_name.replace('-', '_')
    print(f"Creating agent runtime: {runtime_name}")
    
    try:
        client = boto3.client('bedrock-agentcore-control', region_name=aws_region)
        
        response = client.create_agent_runtime(
            agentRuntimeName=runtime_name,
            agentRuntimeArtifact={
                'containerConfiguration': {
                    'containerUri': f"{account_id}.dkr.ecr.{aws_region}.amazonaws.com/{repository_name}:{image_tag}"
                }
            },
            networkConfiguration={"networkMode": "PUBLIC"}, 
            roleArn=agent_runtime_role
        )
        
        print(f"✓ Agent runtime created: {response['agentRuntimeArn']}")
        return response['agentRuntimeArn']
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConflictException':
            print(f"Agent runtime {runtime_name} already exists")
            return None
        else:
            print(f"Error creating agent runtime: {e}")
            return None
    except Exception as e:
        print(f"Error creating agent runtime: {e}")
        return None

def update_agent_runtime_func(config, repository_name, agent_runtime_id, image_tag):
    """Update an existing Agent Runtime."""
    aws_region = config['region']
    account_id = config['accountId']
    agent_runtime_role = config.get('agent_runtime_role')
    
    if not agent_runtime_role:
        print("Error: agent_runtime_role not found in config.json")
        return None
    
    print(f"Updating agent runtime: {repository_name}")
    
    try:
        client = boto3.client('bedrock-agentcore-control', region_name=aws_region)
        
        response = client.update_agent_runtime(
            agentRuntimeId=agent_runtime_id,
            description="Update agent runtime",
            agentRuntimeArtifact={
                'containerConfiguration': {
                    'containerUri': f"{account_id}.dkr.ecr.{aws_region}.amazonaws.com/{repository_name}:{image_tag}"
                }
            },
            roleArn=agent_runtime_role,
            networkConfiguration={"networkMode": "PUBLIC"},
            protocolConfiguration={"serverProtocol": "HTTP"}
        )
        
        print(f"✓ Agent runtime updated: {response['agentRuntimeArn']}")
        return response['agentRuntimeArn']
        
    except Exception as e:
        print(f"Error updating agent runtime: {e}")
        return None

def create_agent_runtime():
    """Create/update AgentCore runtime"""
    print(f"\n{'='*60}")
    print("Creating/updating AgentCore runtime")
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
        
        print(f"Repository name: {repository_name}")
        print(f"Runtime name: {runtime_name}")
        
        # Get latest image tag
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
                print(f"Agent runtime {runtime_name} already exists")
                is_exist = True
                agent_runtime_id = agent_runtime['agentRuntimeId']
                break
        
        # Create or update agent runtime
        if is_exist:
            print(f"Updating agent runtime: {runtime_name}")
            agent_runtime_arn = update_agent_runtime_func(config, repository_name, agent_runtime_id, image_tag)
        else:
            print(f"Creating agent runtime: {runtime_name}")
            agent_runtime_arn = create_agent_runtime_func(config, repository_name, image_tag)
        
        if not agent_runtime_arn:
            print("Error: Failed to create/update agent runtime")
            return False
        
        # Update config.json
        update_agentcore_json(agent_runtime_arn)
        
        print("\n✓ Agent runtime creation/update completed")
        return True
        
    except Exception as e:
        print(f"Error creating/updating agent runtime: {e}")
        return False

# ============================================================================
# Main Function
# ============================================================================

def main():
    """Main function: Execute the entire installation process."""
    print("\n" + "="*60)
    print("AgentCore Runtime Installation Script")
    print("="*60)
    
    # Check config.json
    config = load_config()
    
    print(f"Configuration file loaded successfully")
    print(f"  - Project Name: {config.get('projectName')}")
    print(f"  - Region: {config.get('region')}")
    print(f"  - Account ID: {config.get('accountId')}")
    
    # Execute each step
    steps = [
        ("Creating IAM policies and roles", create_iam_policies),
        ("Building Docker image and pushing to ECR", push_to_ecr),
        ("Creating/updating AgentCore runtime", create_agent_runtime),
    ]
    
    for step_name, step_func in steps:
        if not step_func():
            print(f"\nInstallation failed: Error occurred in step '{step_name}'.")
            print("   Previous steps completed, but installation was aborted.")
            sys.exit(1)
    
    # Output final results
    print("\n" + "="*60)
    print("All installation steps completed successfully!")
    print("="*60)
    
    # Output final config.json information
    config = load_config()
    
    role_arn = config.get('agent_runtime_role')
    arn = config.get('agent_runtime_arn')
    
    if role_arn:
        print(f"\nCreated AgentCore Runtime Role ARN: {role_arn}")
    if arn:
        print(f"Created AgentCore Runtime ARN: {arn}")
    
    if role_arn and arn:
        print("\nInstallation complete!")
    else:
        print("\nInstallation completed with warnings!")

if __name__ == "__main__":
    main()
