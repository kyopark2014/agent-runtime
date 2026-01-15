import logging
import sys
import json
import boto3
import os

logging.basicConfig(
    level=logging.INFO,  # Default to INFO level
    format='%(filename)s:%(lineno)d | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger("s3vector")

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, "config.json")

def load_config():
    config = None

    try:    
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        raise e
    
    return config

config = load_config()

aws_region = config.get('region')
accountId = config.get('accountId')
projectName = config.get('projectName')

def create_bucket(bucket_name, region):
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

# Bucket for Knowledge Base
bucket_name = config.get("bucket_name")
print(f"bucket_name: {bucket_name}")

if not bucket_name:
    bucket_name = f"storage-for-{projectName}-{accountId}-{aws_region}"
    config['bucket_name'] = bucket_name
    print(f"bucket_name: {bucket_name}")
    
    create_bucket(bucket_name, aws_region)

    # write bucket name
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
                
def create_knowledge_base(knowledge_base_name, region):
    # Create role    
    role_name = f"role-knowledge-base-for-{projectName}-{region}"

    # IAM policy document for knowledge base role
    knowledge_base_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "BedrockAllStatement",
                "Action": "bedrock:*",
                "Resource": "*",
                "Effect": "Allow"
            },
            {
                "Sid": "BedrockAgentStatement",
                "Action": [
                    "bedrock-agent:*"
                ],
                "Resource": "*",
                "Effect": "Allow"
            },
            {
                "Sid": "BedrockInvokeInferenceProfileStatement",
                "Effect": "Allow",
                "Action": [
                    "bedrock:GetInferenceProfile",
                    "bedrock:InvokeModel"
                ],
                "Resource": "*"
            },
            {
                "Sid": "S3BucketStatement",
                "Effect": "Allow",
                "Action": ["s3:*"],
                "Resource": "*"
            },
            {
                "Sid": "S3VectorsStatement",
                "Effect": "Allow",
                "Action": [
                    "s3vectors:*"
                ],
                "Resource": "*"
            }
        ]
    }

    # Trust policy for Bedrock service
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }

    iam = boto3.client('iam', region_name=region)    
    response = iam.list_roles(MaxItems=200)    
    roles = response.get('Roles', [])
    role_arn = None
    if not any(role['RoleName'] == role_name for role in roles):
        logger.info(f"role_name: {role_name} is not exists.")
        response = iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust_policy))
        role_arn = response['Role']['Arn']
        logger.info(f"role_arn: {role_arn}")
        
        iam.put_role_policy(RoleName=role_name, PolicyName=f"knowledge-base-for-{projectName}-{region}", PolicyDocument=json.dumps(knowledge_base_policy))
        
        logger.info(f"role_name: {role_name} is created.")
    else:
        logger.info(f"role_name: {role_name} is already exists.")

        # Get the existing role ARN
        for role in roles:
            if role['RoleName'] == role_name:
                role_arn = role['Arn']
                logger.info(f"role_arn: {role_arn}")
                break
        
        # Update trust policy for existing role
        iam.update_assume_role_policy(RoleName=role_name, PolicyDocument=json.dumps(trust_policy))
        logger.info(f"Updated trust policy for existing role: {role_name}")
        
        # Update policy for existing role to ensure all permissions
        iam.put_role_policy(RoleName=role_name, PolicyName=f"knowledge-base-for-{projectName}-{region}", PolicyDocument=json.dumps(knowledge_base_policy))
        logger.info(f"Updated policy for existing role: {role_name}")
    
    # Create S3 Vector Bucket client
    client = boto3.client('s3vectors', region_name=region)

    s3_vector_bucket_name = f"s3-vector-for-{projectName}-{accountId}-{region}"
    logger.info(f"s3_vector_bucket_name: {s3_vector_bucket_name}")
            
    response = client.list_vector_buckets(maxResults=50)
    vectorBuckets = response.get('vectorBuckets', [])
    if not any(vectorBucket['vectorBucketName'] == s3_vector_bucket_name for vectorBucket in vectorBuckets):
        response = client.create_vector_bucket(vectorBucketName=s3_vector_bucket_name)
        logger.info(f"response of create_vector_bucket: {response}")

        logger.info(f"s3_vector_bucket_name: {s3_vector_bucket_name} is created.")
        # Refresh list to fetch ARN after creation
        response = client.list_vector_buckets(maxResults=50)
        vectorBuckets = response.get('vectorBuckets', [])
    else:
        logger.info(f"s3_vector_bucket_name: {s3_vector_bucket_name} is already exists.")

    # Resolve ARN for the target bucket
    for vectorBucket in vectorBuckets:
        if vectorBucket.get('vectorBucketName') == s3_vector_bucket_name:
            s3_vector_bucket_arn = vectorBucket.get('vectorBucketArn', '')
            logger.info(f"s3_vector_bucket_arn: {s3_vector_bucket_arn}")
            break
    if not s3_vector_bucket_arn:
        # As a fallback, try describing the bucket if API exists; otherwise raise
        logger.error("Failed to resolve s3_vector_bucket_arn after creation/list. Aborting.")
        raise ValueError("s3_vector_bucket_arn is empty")
    
    config['s3_vector_bucket_name'] = s3_vector_bucket_name        
    config['s3_vector_bucket_arn'] = s3_vector_bucket_arn
        
    s3_vector_index_name = f"s3-vector-index-for-{projectName}-{accountId}-{region}"
    logger.info(f"s3_vector_index_name: {s3_vector_index_name}")
    config['s3_vector_index_name'] = s3_vector_index_name
    
    response = client.list_indexes(vectorBucketName=s3_vector_bucket_name)
    indexes = response.get('indexes', [])
    
    if not any(index['indexName'] == s3_vector_index_name for index in indexes):
        response = client.create_index(
            vectorBucketArn=s3_vector_bucket_arn,
            indexName=s3_vector_index_name,
            dataType='float32',
            dimension=1024,
            distanceMetric='cosine'                
        )
        logger.info(f"response of create_index: {response}")

        logger.info(f"{s3_vector_index_name} is created.")
    else:
        logger.info(f"{s3_vector_index_name} is already exists.")

    response = client.list_indexes(vectorBucketName=s3_vector_bucket_name)
    indexes = response.get('indexes', [])
    for index in indexes:
        if index['indexName'] == s3_vector_index_name:
            s3_vector_index_arn = index['indexArn']
            logger.info(f"s3_vector_index_arn: {s3_vector_index_arn}")
            break
    
    config['s3_vector_index_arn'] = s3_vector_index_arn
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    # Create knowledge base
    # parsingModelArn = f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-3-7-sonnet-20250219-v1:0"
    # parsingModelArn = f"arn:aws:bedrock:{region}::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"
    account_id = config.get('accountId')
    if not account_id:
        raise ValueError("account_id is not found")
    parsingModelArn = f"arn:aws:bedrock:{region}:{account_id}:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0"
    embeddingModelArn = f"arn:aws:bedrock:{region}::foundation-model/amazon.titan-embed-text-v2:0"

    knowledge_base_name = projectName
        
    bedrock_agent = boto3.client('bedrock-agent', region_name=region)
    response = bedrock_agent.create_knowledge_base(
        name=knowledge_base_name,
        description=f"Knowledge base for {projectName} using s3 vector",
        roleArn=role_arn,
        knowledgeBaseConfiguration={
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": embeddingModelArn, 
                "embeddingModelConfiguration": {
                    "bedrockEmbeddingModelConfiguration": {
                        "dimensions": 1024,
                        "embeddingDataType": "FLOAT32"
                    }
                },
                "supplementalDataStorageConfiguration": {
                    "storageLocations": [
                        {
                            "s3Location": {
                                "uri": f"s3://{bucket_name}"
                            },
                            "type": "S3"
                        }
                    ]
                }
            }
        },
        storageConfiguration={
            "type": "S3_VECTORS",
            "s3VectorsConfiguration": {
                "vectorBucketArn": s3_vector_bucket_arn,
                "indexArn": s3_vector_index_arn
            }
        }
    )
    # Extract the actual knowledge base ID from the response
    knowledge_base_id = response['knowledgeBase']['knowledgeBaseId']
    config['knowledge_base_id'] = knowledge_base_id
    logger.info(f"knowledge_base_id: {knowledge_base_id}")

    # data source of knowledge base 
    data_source_name = config.get('data_source_name', "")
    logger.info(f"data_source_name: {data_source_name}")
    if not data_source_name:
        data_source_name = f"data-source-for-{projectName}-{region}"
        config['data_source_name'] = data_source_name
        logger.info(f"data_source_name: {data_source_name}")

        bedrock_agent = boto3.client('bedrock-agent', region_name=region)
        response = bedrock_agent.list_data_sources(knowledgeBaseId=knowledge_base_id)
        data_sources = response.get('dataSources', [])
        logger.info(f"data_sources: {data_sources}")

        # Check if data source exists
        existing_data_source = None
        for data_source in data_sources:
            if data_source.get('dataSourceName') == data_source_name:
                existing_data_source = data_source
                break

        if not existing_data_source:
            try:
                response = bedrock_agent.create_data_source(
                    knowledgeBaseId=knowledge_base_id,
                    name=data_source_name,
                    description=f"Data source for {projectName} using s3 vector",
                    dataSourceConfiguration={
                        "type": "S3",
                        "s3Configuration": {
                            "bucketArn": f"arn:aws:s3:::{bucket_name}",
                            "inclusionPrefixes": ["docs/"]
                        }
                    },
                    dataDeletionPolicy="RETAIN",
                    vectorIngestionConfiguration={
                        'parsingConfiguration': {
                            'bedrockFoundationModelConfiguration': {
                                'modelArn': parsingModelArn,
                                'parsingModality': 'MULTIMODAL'
                            },
                            'parsingStrategy': 'BEDROCK_FOUNDATION_MODEL'
                        }
                    }
                )
                logger.info(f"Created data source: {data_source_name}")
            except Exception as e:
                if "already exists" in str(e):
                    logger.info(f"Data source {data_source_name} already exists.")
                else:
                    logger.error(f"Failed to create data source: {e}")
                    raise e
        else:
            logger.info(f"Data source {data_source_name} already exists.")

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
