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
import boto3
import logging
from datetime import datetime
from botocore.exceptions import ClientError, NoCredentialsError

logging.basicConfig(
    level=logging.INFO,
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("installer")

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.json")

sys.path.insert(0, script_dir)

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
        pass
    
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
    
    policy_name = f"BedrockAgentCoreMCPRoleFor{projectName}"
    policy_description = f"Policy for accessing Bedrock AgentCore MCP endpoints"
    
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
                    "secretsmanager:UpdateSecret"
                ],
                "Resource": [
                    f"arn:aws:secretsmanager:{region}:*:secret:{projectName.lower()}/credentials*",
                    f"arn:aws:secretsmanager:{region}:*:secret:{projectName}/cognito/credentials*"
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
                "Sid": "S3VectorsAccess",
                "Effect": "Allow",
                "Action": [
                    "s3vectors:*"
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
            },
            {
                "Sid": "CloudFrontAccess",
                "Effect": "Allow",
                "Action": [
                    "cloudfront:ListDistributions",
                    "cloudfront:GetDistribution",
                    "cloudfront:DescribeDistribution",
                    "cloudfront:ListCloudFrontOriginAccessIdentities",
                    "cloudfront:GetCloudFrontOriginAccessIdentity",
                    "cloudfront:ListInvalidations",
                    "cloudfront:GetInvalidation",
                    "cloudfront:ListStreamingDistributions",
                    "cloudfront:GetStreamingDistribution"
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
    role_name = f"BedrockAgentCoreMCPRoleFor{projectName}"
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
        # Convert hyphens to underscores for ECR repository name (AWS validation requirement)
        ecr_repository = f"{project_name}_{current_folder_name}".replace('-', '_')
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
# Cognito Setup Functions (from create_bearer_token.py)
# ============================================================================

def get_cognito_config(config, cognito_config):
    """Get or initialize Cognito configuration"""
    region = config['region']
    project_name = config.get('projectName', 'agentcore')
    
    user_pool_name = cognito_config.get('user_pool_name')
    user_pool_id = cognito_config.get('user_pool_id')
    
    if not user_pool_name:
        user_pool_name = f"{project_name}-agentcore-user-pool"
        print(f"No user pool name found in config, using default user pool name: {user_pool_name}")
        cognito_config.setdefault('user_pool_name', user_pool_name)
    
    # If user_pool_id is not set, try to find existing user pool by name
    if not user_pool_id and user_pool_name:
        cognito_client = boto3.client('cognito-idp', region_name=region)
        try:
            response = cognito_client.list_user_pools(MaxResults=60)
            for pool in response['UserPools']:
                if pool['Name'] == user_pool_name:
                    user_pool_id = pool['Id']
                    print(f"Found cognito user pool: {user_pool_id}")
                    cognito_config['user_pool_id'] = user_pool_id
                    break
        except Exception as e:
            print(f"Warning: Could not search for existing user pools: {e}")
    
    client_name = cognito_config.get('client_name')
    if not client_name:
        client_name = f"{project_name}-agentcore-client"
        print(f"No client name found in config, using default client name: {client_name}")
        cognito_config['client_name'] = client_name
    
    client_id = cognito_config.get('client_id')
    if not client_id and user_pool_id:
        cognito_client = boto3.client('cognito-idp', region_name=region)
        response = cognito_client.list_user_pool_clients(UserPoolId=user_pool_id)
        for client in response['UserPoolClients']:
            if client['ClientName'] == client_name:
                client_id = client['ClientId']
                print(f"Found cognito client: {client_id}")
                cognito_config['client_id'] = client_id
                break
    
    username = cognito_config.get('test_username')
    password = cognito_config.get('test_password')
    if not username or not password:
        print("No test username found in config, using default username and password. Please check config.json and update the test username and password.")
        username = f"{project_name}-test-user@example.com"
        password = "TestPassword123!"
        cognito_config['test_username'] = username
        cognito_config['test_password'] = password
    
    # Set default identity pool name if not provided
    identity_pool_name = cognito_config.get('identity_pool_name')
    if not identity_pool_name:
        identity_pool_name = f"{project_name}-agentcore-identity-pool"
        print(f"No identity pool name found in config, using default: {identity_pool_name}")
        cognito_config['identity_pool_name'] = identity_pool_name
    
    # Save config (matching create_bearer_token.py behavior)
    config['cognito'] = cognito_config
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    
    return cognito_config

def create_user_pool(user_pool_name, region):
    """Create Cognito User Pool"""
    cognito_client = boto3.client('cognito-idp', region_name=region)
    
    print("Creating new Cognito User Pool...")
    response = cognito_client.create_user_pool(
        PoolName=user_pool_name,
        Policies={
            'PasswordPolicy': {
                'MinimumLength': 8,
                'RequireUppercase': True,
                'RequireLowercase': True,
                'RequireNumbers': True,
                'RequireSymbols': False
            }
        },
        AutoVerifiedAttributes=['email'],
        UsernameAttributes=['email'],
        MfaConfiguration='OFF',
        AdminCreateUserConfig={
            'AllowAdminCreateUserOnly': True
        }
    )
    user_pool_id = response['UserPool']['Id']
    
    return user_pool_id

def create_client(user_pool_id, client_name, region):
    """Create Cognito App Client"""
    cognito_client = boto3.client('cognito-idp', region_name=region)
    
    response = cognito_client.create_user_pool_client(
        UserPoolId=user_pool_id,
        ClientName=client_name,
        GenerateSecret=False,
        ExplicitAuthFlows=[
            'ALLOW_USER_PASSWORD_AUTH',
            'ALLOW_REFRESH_TOKEN_AUTH'
        ]
    )
    client_id = response['UserPoolClient']['ClientId']
    
    return client_id

def create_cognito_user_pool(config):
    """Create Cognito User Pool and App Client"""
    region = config['region']
    cognito_config = config.get('cognito', {})
    cognito_config = get_cognito_config(config, cognito_config)
    
    user_pool_name = cognito_config['user_pool_name']
    user_pool_id = cognito_config.get('user_pool_id')
    
    # Verify if user_pool_id exists, if not create a new one
    if user_pool_id:
        cognito_client = boto3.client('cognito-idp', region_name=region)
        try:
            cognito_client.describe_user_pool(UserPoolId=user_pool_id)
            print(f"✓ User Pool exists: {user_pool_id}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print(f"Warning: User Pool '{user_pool_id}' does not exist. Creating new one...")
                user_pool_id = None
            else:
                raise
    
    user_pool_created = False
    if not user_pool_id:
        user_pool_id = create_user_pool(user_pool_name, region)
        print(f"✓ User Pool created successfully: {user_pool_id}")
        cognito_config['user_pool_id'] = user_pool_id
        user_pool_created = True
    
    client_name = cognito_config['client_name']
    client_id = cognito_config.get('client_id')
    
    # If user pool was just created, or client_id doesn't exist, create a new client
    # Also verify if client_id exists for the current user_pool_id
    if user_pool_created or not client_id:
        print("Creating new App client for User Pool...")
        client_id = create_client(user_pool_id, client_name, region)
        print(f"✓ App client created successfully: {client_id}")
        cognito_config['client_id'] = client_id
    else:
        # Verify if client_id exists for the current user_pool_id
        cognito_client = boto3.client('cognito-idp', region_name=region)
        try:
            response = cognito_client.describe_user_pool_client(
                UserPoolId=user_pool_id,
                ClientId=client_id
            )
            print(f"✓ App client exists: {client_id}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                print(f"Warning: App client '{client_id}' does not exist. Creating new one...")
                client_id = create_client(user_pool_id, client_name, region)
                print(f"✓ App client created successfully: {client_id}")
                cognito_config['client_id'] = client_id
            else:
                raise
    
    # Save config
    config['cognito'] = cognito_config
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    print(f"✓ Client ID updated in config.json: {client_id}")
    
    return user_pool_id, client_id, cognito_config

def check_user(user_pool_id, username, region):
    """Check if user exists in Cognito User Pool"""
    cognito_idp_client = boto3.client('cognito-idp', region_name=region)
    try:
        response = cognito_idp_client.admin_get_user(
            UserPoolId=user_pool_id,
            Username=username
        )
        print(f"✓ User '{username}' already exists")
        return True
    except cognito_idp_client.exceptions.UserNotFoundException:
        print(f"User '{username}' does not exist, creating...")
        return False
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"User Pool '{user_pool_id}' does not exist, user cannot be checked")
            return False
        else:
            raise

def create_user(user_pool_id, username, password, region):
    """Create user in Cognito User Pool"""
    cognito_idp_client = boto3.client('cognito-idp', region_name=region)
    try:
        cognito_idp_client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=username,
            UserAttributes=[
                {
                    'Name': 'email',
                    'Value': username
                },
                {
                    'Name': 'email_verified',
                    'Value': 'true'
                }
            ],
            TemporaryPassword=password,
            MessageAction='SUPPRESS'  # Don't send welcome email
        )
        
        cognito_idp_client.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=username,
            Password=password,
            Permanent=True
        )
        print(f"✓ Password set for user '{username}'")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"Error: User Pool '{user_pool_id}' does not exist. Cannot create user.")
            raise
        else:
            print(f"Warning: Could not set permanent password: {e}")
            print("User may need to change password on first login")
            return False
    except Exception as e:
        print(f"Warning: Could not set permanent password: {e}")
        print("User may need to change password on first login")
        return False

def create_test_user(config):
    """Create a test user in Cognito User Pool"""
    region = config['region']
    cognito_config = config.get('cognito', {})
    user_pool_id = cognito_config.get('user_pool_id')
    username = cognito_config.get('test_username')
    password = cognito_config.get('test_password')
    
    if not user_pool_id:
        raise ValueError("User Pool ID is required. Please create Cognito User Pool first.")
    
    if not username or not password:
        project_name = config.get('projectName', 'agentcore')
        print("No test username found in config, using default username and password. Please check config.json and update the test username and password.")
        username = f"{project_name}-test-user@example.com"
        password = "TestPassword123!"
        cognito_config['test_username'] = username
        cognito_config['test_password'] = password
    
    if not check_user(user_pool_id, username, region):
        print(f"Creating test user in User Pool: {user_pool_id}")
        create_user(user_pool_id, username, password, region)
    print(f"✓ User '{username}' created successfully")
    
    config['cognito'] = cognito_config
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return config

def create_cognito_identity_pool(user_pool_id, client_id, config):
    """Create Cognito Identity Pool"""
    region = config['region']
    cognito_config = config.get('cognito', {})
    identity_pool_name = cognito_config.get('identity_pool_name')
    identity_pool_id = cognito_config.get('identity_pool_id')
    
    if not identity_pool_id:
        identity_client = boto3.client('cognito-identity', region_name=region)
        response = identity_client.create_identity_pool(
            IdentityPoolName=identity_pool_name,
            AllowUnauthenticatedIdentities=False,
            CognitoIdentityProviders=[
                {
                    'ProviderName': f'cognito-idp.{region}.amazonaws.com/{user_pool_id}',
                    'ClientId': client_id,
                    'ServerSideTokenCheck': False
                }
            ]
        )
        identity_pool_id = response['IdentityPoolId']
        print(f"✓ Identity Pool created successfully: {identity_pool_id}")
        # Note: identity_pool_id is not saved to cognito_config here to match create_bearer_token.py behavior
        # It will be saved in setup_cognito() function
    
    return identity_pool_id

def update_agentcore_config_with_cognito(user_pool_id, identity_pool_id, client_id, discovery_url, config):
    """Update AgentCore configuration with Cognito information"""
    cognito_config = config.get('cognito', {})
    cognito_config.update({
        'client_id': client_id,
        'user_pool_id': user_pool_id,
        'identity_pool_id': identity_pool_id,
        'discovery_url': discovery_url
    })
    config['cognito'] = cognito_config
    
    # Save configuration file
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    
    print(f"AgentCore configuration updated successfully: {config_path}")

def create_cognito_bearer_token(config):
    """Get a fresh bearer token from Cognito"""
    try:
        region = config['region']
        cognito_config = config['cognito']
        client_id = cognito_config['client_id']
        username = cognito_config['test_username']
        password = cognito_config['test_password']
        
        # Create Cognito client
        client = boto3.client('cognito-idp', region_name=region)
        
        # Authenticate and get tokens
        response = client.initiate_auth(
            ClientId=client_id,
            AuthFlow='USER_PASSWORD_AUTH',
            AuthParameters={
                'USERNAME': username,
                'PASSWORD': password
            }
        )
        
        auth_result = response['AuthenticationResult']
        access_token = auth_result['AccessToken']
        
        print("Successfully obtained fresh Cognito tokens")
        return access_token
        
    except Exception as e:
        print(f"Error getting Cognito token: {e}")
        return None

def save_bearer_token(secret_name, bearer_token, region):
    """Save bearer token to AWS Secrets Manager"""
    try:
        client = boto3.client('secretsmanager', region_name=region)
        
        # Create secret value with bearer_token
        secret_value = {
            "bearer_token": bearer_token
        }
        
        # Convert to JSON string
        secret_string = json.dumps(secret_value)
        
        # Check if secret already exists
        try:
            client.describe_secret(SecretId=secret_name)
            # Secret exists, update it
            client.put_secret_value(
                SecretId=secret_name,
                SecretString=secret_string
            )
            print(f"✓ Bearer token updated in secret manager")
        except client.exceptions.ResourceNotFoundException:
            # Secret doesn't exist, create it
            client.create_secret(
                Name=secret_name,
                SecretString=secret_string,
                Description="MCP Server Cognito credentials with bearer key and token"
            )
            print(f"✓ Bearer token created in secret manager")
            
    except Exception as e:
        print(f"Error saving bearer token: {e}")

def setup_cognito():
    """Setup Cognito User Pool, Identity Pool, and Bearer Token"""
    print(f"\n{'='*60}")
    print("Setting up Cognito authentication")
    print(f"{'='*60}")
    
    try:
        config = load_config()
        region = config['region']
        project_name = config.get('projectName', 'agentcore')
        
        # 1. Create Cognito User Pool
        print("\n1. Creating Cognito User Pool...")
        user_pool_id, client_id, cognito_config = create_cognito_user_pool(config)
        config['cognito'] = cognito_config
        
        # 2. Create Cognito Identity Pool
        print("\n2. Creating Cognito Identity Pool...")
        identity_pool_id = create_cognito_identity_pool(user_pool_id, client_id, config)
        cognito_config['identity_pool_id'] = identity_pool_id
        config['cognito'] = cognito_config
        
        # 3. Update AgentCore Configuration
        print("\n3. Updating AgentCore Configuration...")
        discovery_url = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/openid-configuration"
        update_agentcore_config_with_cognito(user_pool_id, identity_pool_id, client_id, discovery_url, config)
        
        # 4. Create test user
        print("\n4. Creating test user...")
        config = create_test_user(config)
        
        # 5. Create Bearer token
        print("\n5. Creating Bearer token...")
        bearer_token = create_cognito_bearer_token(config)
        if not bearer_token:
            print("Warning: Failed to create bearer token")
            return False
        
        # 6. Save bearer token
        print("\n6. Saving Bearer token...")
        secret_name = f'{project_name.lower()}/credentials'
        config['secret_name'] = secret_name
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        print(f"✓ secret_name updated in config.json: {secret_name}")
        
        save_bearer_token(secret_name, bearer_token, region)
        
        print("\n✓ Cognito setup completed")
        print("  - Cognito User Pool and Identity Pool created")
        print("  - App client authentication flows configured")
        print("  - Test user created")
        print("  - Bearer token generated and saved")
        
        return True
        
    except Exception as e:
        print(f"Error setting up Cognito: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================================
# Knowledge Base Creation Functions (from s3vector.py)
# ============================================================================

def create_bucket(bucket_name, region):
    """Create S3 bucket for Knowledge Base storage"""
    s3 = boto3.client('s3', region_name=region)
    response = s3.list_buckets()
    buckets = response.get('Buckets', [])
    if not any(bucket['Name'] == bucket_name for bucket in buckets):
        logger.info(f"bucket_name: {bucket_name} is not exists.")
        
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={'LocationConstraint': region}
        )
        logger.info(f"bucket_name: {bucket_name} is created.")    
        
        s3.put_object(Bucket=bucket_name, Key='docs/')
        logger.info(f"docs folder is created in {bucket_name}.")
    else:
        logger.info(f"bucket_name: {bucket_name} is already exists.")

def setup_knowledge_base(config):
    import s3vector
    """Setup Knowledge Base if needed - uses s3vector.create_knowledge_base"""
    aws_region = config.get('region')
    project_name = config.get('projectName')
    account_id = config.get('accountId')
    
    if not aws_region or not project_name:
        print("Error: Missing required configuration (region or projectName)")
        return None
    
    try:        
        # Check if Knowledge Base with same name already exists before creating
        bedrock_agent = boto3.client('bedrock-agent', region_name=aws_region)
        response = bedrock_agent.list_knowledge_bases(maxResults=50)
        knowledge_bases = response.get('knowledgeBaseSummaries', [])
        
        # Find knowledge base with matching name
        knowledge_base_id = None
        for knowledge_base in knowledge_bases:
            if knowledge_base['name'] == project_name:
                knowledge_base_id = knowledge_base['knowledgeBaseId']
                print(f"✓ Found existing Knowledge Base '{project_name}' with ID: {knowledge_base_id}")
                # Update config with found knowledge_base_id
                update_config('knowledge_base_id', knowledge_base_id)
                return knowledge_base_id
        
        # Ensure S3 bucket exists before creating Knowledge Base
        bucket_name = config.get("bucket_name", "")
        if not bucket_name:
            bucket_name = f"storage-for-{project_name}-{account_id}-{aws_region}"
            update_config('bucket_name', bucket_name)
        
        # If not found, create using s3vector
        # Create bucket if it doesn't exist
        print(f"Checking S3 bucket: {bucket_name}")
        create_bucket(bucket_name, aws_region)
        

        print(f"Knowledge Base '{project_name}' not found. Creating new Knowledge Base...")
        s3vector.create_knowledge_base(project_name, aws_region)
        
        # Reload config to get the knowledge_base_id that was saved by s3vector
        updated_config = load_config()
        knowledge_base_id = updated_config.get('knowledge_base_id')
        
        if knowledge_base_id:
            print(f"✓ Knowledge Base setup completed: {knowledge_base_id}")
        else:
            print(f"✗ Failed to setup Knowledge Base - knowledge_base_id not found in config")
        
        return knowledge_base_id
    except Exception as e:
        print(f"Error setting up Knowledge Base: {e}")
        logger.error(f"Error setting up Knowledge Base: {e}", exc_info=True)
        return None

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
        # Convert hyphens to underscores for agent runtime name (AWS validation requirement)
        repository_name = repository_name.replace('-', '_')
                
        ecr_client = boto3.client('ecr', region_name=aws_region)
        
        # Check if repository exists first
        try:
            ecr_client.describe_repositories(repositoryNames=[repository_name])
        except ClientError as e:
            if e.response['Error']['Code'] == 'RepositoryNotFoundException':
                print(f"Error: ECR repository '{repository_name}' does not exist.")
                print(f"Please run the Docker build and push step first to create the repository.")
                return None
            else:
                raise
        
        response = ecr_client.describe_images(repositoryName=repository_name)
        images = response['imageDetails']
        
        if not images:
            print(f"Error: No images found in repository {repository_name}")
            print(f"Please run the Docker build and push step first to push an image.")
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
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'RepositoryNotFoundException':
            print(f"Error: ECR repository '{repository_name}' does not exist.")
            print(f"Please run the Docker build and push step first to create the repository.")
        else:
            print(f"Error getting latest image tag: {e}")
        return None
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
    
    # Convert hyphens to underscores for agent runtime name (AWS validation requirement)
    runtime_name = repository_name.replace('-', '_')
    
    # Check if Cognito configuration exists for JWT Authorizer
    cognito_config = config.get('cognito', {})
    if not cognito_config.get('client_id') or not cognito_config.get('discovery_url'):
        print("Error: Cognito configuration not found in config.json")
        print("Please run Cognito setup step first")
        return None
    
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
            roleArn=agent_runtime_role,
            protocolConfiguration={"serverProtocol": "MCP"},
            authorizerConfiguration={
                "customJWTAuthorizer": {
                    "allowedClients": [
                        cognito_config['client_id']
                    ],
                    "discoveryUrl": cognito_config['discovery_url']
                }
            }
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
    
    # Check if Cognito configuration exists for JWT Authorizer
    cognito_config = config.get('cognito', {})
    authorizer_config = None
    if cognito_config.get('client_id') and cognito_config.get('discovery_url'):
        authorizer_config = {
            "customJWTAuthorizer": {
                "allowedClients": [
                    cognito_config['client_id']
                ],
                "discoveryUrl": cognito_config['discovery_url']
            }
        }
    
    try:
        client = boto3.client('bedrock-agentcore-control', region_name=aws_region)
        
        update_params = {
            'agentRuntimeId': agent_runtime_id,
            'description': "Update agent runtime",
            'agentRuntimeArtifact': {
                'containerConfiguration': {
                    'containerUri': f"{account_id}.dkr.ecr.{aws_region}.amazonaws.com/{repository_name}:{image_tag}"
                }
            },
            'roleArn': agent_runtime_role,
            'networkConfiguration': {"networkMode": "PUBLIC"},
            'protocolConfiguration': {"serverProtocol": "MCP"}
        }
        
        # Add authorizer configuration if Cognito is configured
        if authorizer_config:
            update_params['authorizerConfiguration'] = authorizer_config
        
        response = client.update_agent_runtime(**update_params)
        
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
        
        # Setup Knowledge Base if needed (from create_mcp_runtime.py)
        print("\n1. Setting up Knowledge Base...")
        knowledge_base_id = setup_knowledge_base(config)
        
        # Update knowledge_base_name if not set
        knowledge_base_name = config.get("knowledge_base_name", "")
        if not knowledge_base_name:
            knowledge_base_name = project_name
            update_config('knowledge_base_name', knowledge_base_name)
        
        # Get current folder name
        current_folder_name = os.path.basename(os.getcwd())
        repository_name = f"{project_name}_{current_folder_name}"
        
        # Convert hyphens to underscores for agent runtime name (AWS validation requirement)
        repository_name = repository_name.replace('-', '_')
        
        print(f"\n2. Repository name: {repository_name}")
        print(f"   Agent runtime name: {repository_name}")
        
        # Get latest image tag
        image_tag = get_latest_image_tag(config)
        if not image_tag:
            print("\nError: Could not get latest image tag")
            print("This usually means:")
            print("  1. The ECR repository does not exist yet")
            print("  2. No Docker images have been pushed to the repository")
            print("\nPlease ensure the 'Building Docker image and pushing to ECR' step completed successfully.")
            return False
        
        print(f"Using image tag: {image_tag}")
        
        # Check if agent runtime already exists
        client = boto3.client('bedrock-agentcore-control', region_name=aws_region)
        response = client.list_agent_runtimes()
        agent_runtimes = response.get('agentRuntimes', [])
        
        is_exist = False
        agent_runtime_id = None
        
        for agent_runtime in agent_runtimes:
            if agent_runtime['agentRuntimeName'] == repository_name:
                print(f"Agent runtime {repository_name} already exists")
                is_exist = True
                agent_runtime_id = agent_runtime['agentRuntimeId']
                break
        
        # Create or update agent runtime
        print("\n3. Creating/updating Agent Runtime...")
        if is_exist:
            print(f"Updating agent runtime: {repository_name}")
            agent_runtime_arn = update_agent_runtime_func(config, repository_name, agent_runtime_id, image_tag)
        else:
            print(f"Creating agent runtime: {repository_name}")
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
        ("Setting up Cognito authentication", setup_cognito),
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
