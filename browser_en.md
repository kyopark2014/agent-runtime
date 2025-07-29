# AgentCore Browser

With the AgentCore Browser Tool, generative AI applications can control a browser to perform safe searches.

## Nova Act
Nova Act is in Preview, so you need to use a VPN to get a key with an amazon.com account if you are not in USA and prepare for use as follows.

```text
export NOVA_ACT_API_KEY="your_api_key"
```

Then install nova-act as follows.

```text
pip install nova-act
```

You can search for a coffee maker on amazon.com by running the following.

```python
from nova_act import NovaAct
with NovaAct(starting_page="https://www.amazon.com") as nova:  
	nova.act("search for a coffee maker")
```

## Browser Search Implementation

Using Nova Act and playwright, you can obtain search results for prompts as follows. For detailed code, refer to [mcp_browser.py](https://github.com/kyopark2014/mcp/blob/main/application/mcp_browser.py).

```python
starting_page = "https://www.google.com"
with NovaAct(
    cdp_endpoint_url=ws_url,
    cdp_headers=headers,
    preview={"playwright_actuation": True},
    nova_act_api_key=nova_act_key,
    starting_page=starting_page,
) as nova_act:
    search_result = nova_act.act(prompt)    
    final_result = f"Successfully searched for '{prompt}' on Amazon. The search results are now visible in the browser. You can view the products, prices, and descriptions in the browser window."
```

To display search results in the execution environment, we use a BrowserViewerServer as follows, which utilizes DCV. Also, since we use asyncio to run the agent, we execute the browser in a thread as follows.

```python
from interactive_tools.browser_viewer import BrowserViewerServer

with browser_session(bedrock_region) as client:
    ws_url, headers = client.generate_ws_headers()

    viewer = BrowserViewerServer(client, port=8000)
    viewer_url = viewer.start(open_browser=True)

    result_queue = queue.Queue()
    error_queue = queue.Queue()
    
    nova_thread = threading.Thread(
	target=_nova_act_worker,
	args=(prompt, ws_url, headers, result_queue, error_queue)
    )
    nova_thread.start()
    nova_thread.join()  # Wait for completion
    
    if not result_queue.empty():
	result = result_queue.get()	
	if not isinstance(result, str):
	    result = str(result)
```

Prepare [mcp_server_browser.py](https://github.com/kyopark2014/mcp/blob/main/application/mcp_server_browser.py) and MCP tool.

```python
@mcp.tool()
def browser_search(keyword: str) -> str:
    """
    Search web site with the given keyword.
    keyword: the keyword to search
    return: the result of search
    """
    logger.info(f"browser --> keyword: {keyword}")

    return browser.live_view_with_nova_act(keyword)
```



## Execution Results

After setting the starting_page to "www.amazon.com" and asking "Search a coffee maker.", it searches for "coffee maker" using the browser as follows.

<img width="1217" height="808" alt="image" src="https://github.com/user-attachments/assets/3b2c9ae5-dc94-4d69-bbde-76a049c6b151" />

Based on the results obtained, it responds as follows.

<img width="700" alt="image" src="https://github.com/user-attachments/assets/54e19bb1-a2de-4ce8-b958-b2544a31a35" />

For general purposes, set the starting_point to "www.google.com" and then ask questions like "Please summarize the content of https://github.com/awslabs/amazon-bedrock-agentcore-samples/tree/main." At this time, it performs searches based on the entered information as follows.

<img width="700" alt="image" src="https://github.com/user-attachments/assets/29c7ce18-ce26-4832-bc8-d36d271657c9" />

The search results ultimately obtained are as follows.

<img width="700" alt="image" src="https://github.com/user-attachments/assets/b7fe446f-5c09-4940-baf-35622774aa6d" />


## Reference

[Introducing Amazon Nova Act](https://labs.amazon.science/blog/nova-act)

[Github - Nova Act](https://labs.amazon.science/blog/nova-act)
