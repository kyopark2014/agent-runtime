import boto3
import utils
import json
import os

from bedrock_agentcore.memory import MemoryClient

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
    print(f"Trying to create agent: {runtime_name}")

    # create agent runtime
    agentRuntimeArn = None
    try:        
        # create agent runtime
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
        print(f"response of create agent runtime: {response}")

        agentRuntimeArn = response['agentRuntimeArn']
        print(f"agentRuntimeArn: {agentRuntimeArn}")

    except client.exceptions.ConflictException as e:
        print(f"[ERROR] ConflictException: {e}")

    # create memory
    print(f"create agent memory!")    
    print(f"Trying to create memory: {runtime_name}")

    memoryId = None
    try:
        memory_client = MemoryClient(region_name=aws_region)
        memories = memory_client.list_memories()
        print(f"memories: {memories}")

        result = memory_client.create_memory(
            name=runtime_name,
            description=f"Memory for {runtime_name}",
            event_expiry_days=7, # 7 - 365 days
            # memory_execution_role_arn=memory_execution_role_arn
        )
        print(f"result of create memory: {result}") 
        
        if "memoryId" in result:
            memoryId = result['memoryId']
            print(f"memoryId: {memoryId}")
        else:
            print(f"memoryId is not found")
            
    except Exception as e:
        print(f"[ERROR] {e}")
        pass   

    try:
        fname = 'agentcore.json'
        with open(fname, 'r') as f:
            config = json.load(f)
        
        if agentRuntimeArn is not None:
            config['agent_runtime_arn'] = agentRuntimeArn
        if memoryId is not None:
            config['memory_id'] = memoryId
            
        with open(fname, 'w') as f:
            json.dump(config, f)
        print(f"{fname} updated")
    except Exception as e:
        print(f"[ERROR] {e}")
        pass   

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