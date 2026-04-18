# Chat UI (`chat_ui/`)

저장소 루트의 **Agent Skills** 스택과 동일하게, Flask가 정적 UI와 API를 제공하고 백엔드는 **`application/langgraph_agent.run_langgraph_agent`** 로 Bedrock·MCP 에이전트를 실행합니다. (Streamlit `application/app.py` 과 같은 에이전트 진입점, MCP/스킬 기본값은 서버 코드에 고정.)

## 특징

- 모델 선택(Claude / OpenAI OSS / Nova 등, `application/info.py` 기준)
- **`POST /api/chat`** 기본 **SSE(`text/event-stream`)** 스트리밍 — 진행 중 마크다운 청크 갱신
- 멀티턴: 요청 시 **최근 10개** 메시지를 `history`로 전달 → `history_mode` 자동 `Enable`/`Disable`
- 개발용 **CORS** (`/api/*`, `/health`)
- `file://` 로 HTML만 열 때는 `script.js` 기본 `http://127.0.0.1:5001` 또는 `<meta name="chat-api-base">` 로 API 베이스 지정

## 백엔드에서 쓰는 기본값 (`app.py`)

| 항목 | 값 |
|------|-----|
| 기본 MCP 서버 | `tavily`, `knowledge base`, `web_fetch` |
| Debug mode | `Enable` (도구/스트림 알림이 `FlaskNotificationQueue` → SSE `info`/`chunk` 등으로 전달되는 데 사용) |
| Reasoning | `Disable` |
| Skill mode | `Enable` |
| 폴백 모델명 | `Claude 4.5 Sonnet` |
| `default_skills` 미설정 시 | `skill-creator`, `graphify` 를 로드 설정에 보강 |

실제 호출은 `chat.update(model, debug, reasoning, skill)` 후 `langgraph_agent.run_langgraph_agent(...)` 입니다.

## 설치 및 실행

프로젝트 **루트 README**의 AWS 자격·설정(`config.toml`, Secrets 등)을 먼저 맞춰야 에이전트가 동작합니다.

```bash
cd chat_ui
pip install -r requirements.txt
python app.py
```

- 기본 포트: **5001** (`PORT` 환경 변수로 변경 가능).
- 브라우저: 터미널에 나온 주소(예: `http://127.0.0.1:5001/`)로 접속. **`index.html`을 파일로 직접 열지 말고** Flask 루트로 여는 것을 권장합니다.
- 포트를 바꾼 경우 `index.html`의 `<meta name="chat-api-base" content="http://127.0.0.1:8080">` 등으로 클라이언트 베이스 URL을 맞춥니다.

## 프로젝트 구조

```
chat_ui/
├── app.py              # Flask, LangGraph 에이전트 연동, SSE
├── index.html          # 모델 선택 + 채팅 UI
├── script.js           # /api/chat SSE, /health 프리플라이트
├── style.css
├── requirements.txt    # Flask 등 (에이전트 본체는 상위 application 의존성)
└── README.md
```

## API

### `POST /api/chat`

**Body (JSON)**

| 필드 | 설명 |
|------|------|
| `message` | 필수. 사용자 메시지 |
| `model` | 선택. 미지정 시 기본 폴백 모델명 사용 |
| `stream` | 선택. 기본 `true` → SSE. `false` 이면 JSON 한 번에 응답 |
| `history` | 선택. `{ "role": "user"\|"assistant", "content": "..." }[]` |

**스트리밍(`stream: true`)** — `text/event-stream`, 줄 단위 `data: {json}`

| `type` | 의미 |
|--------|------|
| `chunk` | 누적 답변 마크다운(같은 스트림에서 갱신) |
| `info` | 도구/알림 문자열 |
| `done` | 최종 본문 |
| `error` | 오류 메시지 |

**비스트리밍(`stream: false`)** — JSON:

```json
{
  "response": "…",
  "model": "Claude 4.5 Sonnet",
  "timestamp": "2026-04-18T12:00:00.000000"
}
```

### `GET /api/models`

Claude / OpenAI OSS / Nova 그룹별 모델 문자열 목록(JSON).

### `GET /health`

`{"status": "healthy", "timestamp": "..."}` — 프론트 연결 가능 여부 확인용.

## 제한·주의

- UI에는 **Temperature 슬라이더 없음**; OpenAI/Anthropic 직접 REST가 아니라 **저장소의 Bedrock·에이전트 파이프라인**을 탑니다.
- `chat_ui/requirements.txt`는 Flask 위주입니다. LangGraph/MCP/Bedrock 등은 **상위 `application` 및 루트 환경**이 필요합니다.

## 라이선스·기여

저장소 루트의 라이선스 및 기여 안내를 따릅니다.
