# AgentCore Browser

## Nova Act
현재(2025.7) Nova Act는 Preview이며 한국에서 사용이 불가하므로 vpn을 이용해 amazon.com 아이디로 key를 발급합니다. 이후 아래와 같이 nova-act를 설치합니다.

```text
pip install nova-act
```

아래와 같이 실행하면 amazon.com에서 coffee maker를 검색할 수 있습니다.

```python
from nova_act import NovaAct
with NovaAct(starting_page="https://www.amazon.com") as nova:  
	nova.act("search for a coffee maker")
```

## Refernece

[Introducing Amazon Nova Act](https://labs.amazon.science/blog/nova-act)

[Github - Nova Act](https://labs.amazon.science/blog/nova-act)
