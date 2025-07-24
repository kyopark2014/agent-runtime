import boto3
# Initialize the boto3 client
cp_client = boto3.client(
 'bedrock-agentcore-control',
 region_name="us-west-2",
 endpoint_url="https://bedrock-agentcore-control.us-west-2.amazonaws.com"
)
# List Code Interpreters
# response = cp_client.list_code_interpreters()
# print(response)

try:
    response = cp_client.create_api_key_credential_provider(
        name='tavilyapikey-agentcore',
        apiKey='tvly-'
    )
    print(response)
except Exception as e:
    print(e)
    pass

response = cp_client.list_api_key_credential_providers()
print(response)







