# AgentCore Browser

## Nova Act
현재(2025.7) Nova Act는 Preview이며 한국에서 사용이 불가하므로 vpn을 이용해 amazon.com 아이디로 key를 발급한후 아래와 같이 사용준비를 합니다.

```text
export NOVA_ACT_API_KEY="your_api_key"
```

이후 아래와 같이 nova-act를 설치합니다.

```text
pip install nova-act
```

아래와 같이 실행하면 amazon.com에서 coffee maker를 검색할 수 있습니다.

```python
from nova_act import NovaAct
with NovaAct(starting_page="https://www.amazon.com") as nova:  
	nova.act("search for a coffee maker")
```

## Browser 검색 구현

Nova Act와 playwright를 이용하여 아래와 같이 prompt에 대한 검색 결과를 얻을 수 있습니다.

```python
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

검색결과를 실행 환경에서 보여주기 위하여, 아래와 같은 BrowserViewerServer를 이용하는데 이것은 DCV를 이용합니다. 또한 agent를 실행하기 위하여 asyncio를 쓰고 있으므로 아래와 같이 browser는 thread로 실행하였습니다.

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


## 실행 결과

"Search a coffee maker."로 질문하면 아래와 같이 browser를 이용하여 "coffee maker"를 검색합니다.

<img width="1217" height="808" alt="image" src="https://github.com/user-attachments/assets/3b2c9ae5-dc94-4d69-bbde-76a049c6b151" />

이때 얻어진 결과를 바탕으로 아래와 같이 답변합니다.

<img width="798" height="762" alt="image" src="https://github.com/user-attachments/assets/54e19bb1-a2de-4ce8-b958-4f2544a31a35" />


## Refernece

[Introducing Amazon Nova Act](https://labs.amazon.science/blog/nova-act)

[Github - Nova Act](https://labs.amazon.science/blog/nova-act)
