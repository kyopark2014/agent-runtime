import boto3
import utils

projectName = utils.projectName
aws_region = utils.bedrock_region
agent_runtime_role = utils.agent_runtime_role
accountId = utils.accountId

# get lagtest image
ecr_client = boto3.client('ecr', region_name=aws_region)
response = ecr_client.describe_images(repositoryName=projectName)
print(f"response of describe_images: {response}")
latestImage = response['imageDetails'][-1]
print(f"latestImage: {latestImage}")
imageTags = latestImage['imageTags'][0]
print(f"imageTags: {imageTags}")

# Call the CreateAgentRuntime operation
client = boto3.client('bedrock-agentcore-control', region_name=aws_region)
response = client.create_agent_runtime(
    agentRuntimeName=projectName.replace('-', '_'),
    agentRuntimeArtifact={
        'containerConfiguration': {
            'containerUri': f"{accountId}.dkr.ecr.{aws_region}.amazonaws.com/{projectName}:{imageTags}"
        }
    },
    networkConfiguration={"networkMode":"PUBLIC"}, 
    roleArn=agent_runtime_role
)
print(response)
