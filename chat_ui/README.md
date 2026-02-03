# LLM Chat UI

다양한 LLM 모델을 테스트할 수 있는 웹 기반 채팅 인터페이스입니다.

## 특징

- 🤖 다중 LLM 모델 지원 (GPT, Claude 등)
- 🎛️ Temperature 조절 기능
- 💬 실시간 채팅 인터페이스
- 📱 반응형 디자인
- ⚡ 빠른 응답 및 스트리밍 지원
- 🎨 모던하고 직관적인 UI/UX

## 지원 모델

- OpenAI GPT-3.5 Turbo
- OpenAI GPT-4
- Anthropic Claude 3 Haiku
- Anthropic Claude 3 Sonnet
- (추가 모델 확장 가능)

## 설치 및 실행

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env` 파일을 생성하고 API 키를 설정하세요:

```bash
# OpenAI API Key (선택사항)
OPENAI_API_KEY=your_openai_api_key_here

# Anthropic API Key (선택사항)
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Flask 설정
DEBUG=True
SECRET_KEY=your_secret_key_here
```

### 3. 서버 실행

```bash
python app.py
```

서버가 시작되면 브라우저에서 `http://localhost:5000`으로 접속하세요.

## 프로젝트 구조

```
chat_ui/
├── app.py              # Flask 백엔드 서버
├── index.html          # 메인 HTML 페이지
├── script.js           # 프론트엔드 JavaScript
├── style.css           # CSS 스타일
├── requirements.txt    # Python 의존성
└── README.md          # 이 파일
```

## 사용법

1. 웹 브라우저에서 애플리케이션에 접속
2. 상단에서 원하는 LLM 모델 선택
3. Temperature 슬라이더로 응답 창의성 조절
4. 하단 입력창에 메시지 입력 후 전송
5. AI 응답 확인 및 대화 계속

## API 엔드포인트

### POST /api/chat
채팅 메시지를 처리합니다.

**Request Body:**
```json
{
  "message": "사용자 메시지",
  "model": "gpt-3.5-turbo",
  "temperature": 0.7,
  "history": []
}
```

**Response:**
```json
{
  "response": "AI 응답",
  "model": "gpt-3.5-turbo",
  "timestamp": "2024-01-30T12:00:00"
}
```

### GET /api/models
사용 가능한 모델 목록을 반환합니다.

### GET /health
서버 상태를 확인합니다.

## 개발자 정보

현재는 Mock 응답을 사용하고 있습니다. 실제 LLM API를 연결하려면:

1. `app.py`에서 해당 함수들의 주석을 해제
2. API 키를 환경변수로 설정
3. 필요한 경우 추가 의존성 설치

## 커스터마이징

### 새로운 모델 추가

1. `index.html`의 select 옵션에 모델 추가
2. `app.py`의 `handle_chat_request` 함수에 모델 처리 로직 추가

### 스타일 변경

`style.css`를 수정하여 UI 디자인을 커스터마이징할 수 있습니다.

## 라이선스

MIT License

## 기여

이슈 리포트나 풀 리퀘스트를 환영합니다!