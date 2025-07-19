import boto3
import utils
import json
import os

projectName = utils.projectName
aws_region = utils.bedrock_region
agent_runtime_role = utils.agent_runtime_role
accountId = utils.accountId

current_folder_name = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
target = current_folder_name.split('/')[-1]
print(f"target: {target}")

repositoryName = projectName.replace('-', '_')+'_'+target
print(f"repositoryName: {repositoryName}")

# get lagtest image
ecr_client = boto3.client('ecr', region_name=aws_region)
response = ecr_client.describe_images(repositoryName=repositoryName)
images = response['imageDetails']
print(f"images: {images}")

# get latest image
images_sorted = sorted(images, key=lambda x: x['imagePushedAt'], reverse=True)
latestImage = images_sorted[0]
print(f"latestImage: {latestImage}")
imageTags = latestImage['imageTags'][0]
print(f"imageTags: {imageTags}")

client = boto3.client('bedrock-agentcore-control', region_name=aws_region)
response = client.list_agent_runtimes()
print(f"response: {response}")

isExist = False
agentRuntimeId = None
agentRuntimes = response['agentRuntimes']
targetAgentRuntime = repositoryName
if len(agentRuntimes) > 0:
    for agentRuntime in agentRuntimes:
        agentRuntimeName = agentRuntime['agentRuntimeName']
        print(f"agentRuntimeName: {agentRuntimeName}")
        if agentRuntimeName == targetAgentRuntime:
            print(f"agentRuntimeName: {agentRuntimeName} is already exists")
            agentRuntimeId = agentRuntime['agentRuntimeId']
            print(f"agentRuntimeId: {agentRuntimeId}")
            isExist = True        
            break

# Check for duplicate Agent Runtime name
def create_agent_runtime():
    runtime_name = targetAgentRuntime
    print(f"create agent runtime!")    
    print(f"Trying to create: {runtime_name}")
    try:        
        response = client.create_agent_runtime(
            agentRuntimeName=runtime_name,
            agentRuntimeArtifact={
                'containerConfiguration': {
                    'containerUri': f"{accountId}.dkr.ecr.{aws_region}.amazonaws.com/{repositoryName}:{imageTags}"
                }
            },
            networkConfiguration={"networkMode":"PUBLIC"}, 
            roleArn=agent_runtime_role
        )
        print(f"response: {response}")

        agentRuntimeArn = response['agentRuntimeArn']
        print(f"agentRuntimeArn: {agentRuntimeArn}")

        # save agentRuntimeArn to json file
        fname = 'agent_runtime_arn.json'
        config = {
            "agent_runtime_arn": agentRuntimeArn
        }
        with open(fname, 'w') as f:
            json.dump(config, f)
        print(f"{fname} updated")
    
    except client.exceptions.ConflictException as e:
        print(f"[ERROR] ConflictException: {e}")

def update_agent_runtime():
    print(f"update agent runtime: {targetAgentRuntime}")

    response = client.update_agent_runtime(
        agentRuntimeId=agentRuntimeId,
        description="Update agent runtime",
        agentRuntimeArtifact={
            'containerConfiguration': {
                'containerUri': f"{accountId}.dkr.ecr.{aws_region}.amazonaws.com/{targetAgentRuntime}:{imageTags}"
            }
        },
        roleArn=agent_runtime_role,
        networkConfiguration={"networkMode":"PUBLIC"},
        protocolConfiguration={"serverProtocol":"HTTP"}
    )
    print(f"response: {response}")

print(f"isExist: {isExist}")
if isExist:
    print(f"update agent runtime: {targetAgentRuntime}, imageTags: {imageTags}")
    update_agent_runtime()
else:
    print(f"create agent runtime: {targetAgentRuntime}, imageTags: {imageTags}")
    create_agent_runtime()