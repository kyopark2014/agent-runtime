# AgentCore Browser


현재 Nova Act는 한국에서 사용이 불가하므로 vpn을 이용해 amazon.com 아이디로 key를 발급합니다.

```text
pip install nova-act
from nova_act import NovaAct
with NovaAct(starting_page="[https://www.amazon.com](https://www.amazon.com/)") as nova:  
	nova.act("search for a coffee maker")
```

## Refernece

[Introducing Amazon Nova Act](https://labs.amazon.science/blog/nova-act)

[Github - Nova Act](https://labs.amazon.science/blog/nova-act)
