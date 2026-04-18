/**
 * file:// 로 index.html 을 열면 fetch('/api/chat') → file:///api/chat 이 되어 실패합니다.
 * HTTP로 Flask 에 접속하면 같은 출처라 상대 경로만 쓰고, file 일 때는 로컬 서버 URL을 붙입니다.
 * 포트 변경 시: <meta name="chat-api-base" content="http://127.0.0.1:8080"> 를 넣거나 getApiBase의 기본 포트를 맞춥니다.
 */
function getApiBase() {
    const meta = document.querySelector('meta[name="chat-api-base"]');
    if (meta && meta.content && meta.content.trim()) {
        return meta.content.trim().replace(/\/$/, '');
    }
    const proto = window.location.protocol;
    const host = window.location.host;
    if (proto === 'file:' || proto === 'blob:' || !host) {
        return 'http://127.0.0.1:5001';
    }
    return '';
}

/** 백엔드가 꺼져 있을 때 (ERR_CONNECTION_REFUSED 등) 사용자 안내 */
function formatFetchError(err) {
    const msg = (err && err.message) ? String(err.message) : String(err);
    const base = getApiBase() || window.location.origin;
    if (
        msg.includes('Failed to fetch') ||
        msg.includes('NetworkError') ||
        msg.includes('Load failed') ||
        msg.includes('fetch')
    ) {
        return (
            '백엔드 서버에 연결할 수 없습니다.\n\n' +
            '터미널에서 프로젝트 루트 기준:\n' +
            '  cd chat_ui && python app.py\n\n' +
            `그다음 브라우저에서 ${base.replace(/\/$/, '')}/ 로 열었는지 확인하세요. ` +
            '(다른 포트면 PORT 환경 변수와 <meta name="chat-api-base"> 를 맞추세요.)'
        );
    }
    return msg;
}

function ensureBackendStatusBanner() {
    let el = document.getElementById('backendStatus');
    if (!el) {
        el = document.createElement('div');
        el.id = 'backendStatus';
        el.className = 'backend-status';
        el.setAttribute('role', 'status');
        document.body.insertBefore(el, document.body.firstChild);
    }
    return el;
}

/** 개발용 콘솔 로그 (주소 뒤 ?debug=1 또는 localStorage.chat_ui_debug=1) */
function chatUiDebug() {
    try {
        if (typeof localStorage !== 'undefined' && localStorage.getItem('chat_ui_debug') === '1') {
            return true;
        }
        return typeof location !== 'undefined' && /(?:\?|&)debug=1(?:&|$)/.test(location.search);
    } catch {
        return false;
    }
}

function chatLog(/* ...args */) {
    if (!chatUiDebug()) {
        return;
    }
    // eslint-disable-next-line no-console
    console.log('[chat_ui]', ...arguments);
}

function chatInfo(/* ...args */) {
    // eslint-disable-next-line no-console
    console.info('[chat_ui]', ...arguments);
}

async function pingBackend() {
    const base = getApiBase();
    const url = `${base}/health`;
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 4000);
    try {
        const r = await fetch(url, { method: 'GET', signal: ctrl.signal });
        clearTimeout(t);
        return r.ok;
    } catch {
        clearTimeout(t);
        return false;
    }
}

class ChatUI {
    constructor() {
        this.messages = [];
        this.isLoading = false;
        this.initializeElements();
        this.setupEventListeners();
        this.initializeWelcomeMessage();
        this.refreshBackendBanner();
    }

    initializeElements() {
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.clearButton = document.getElementById('clearButton');
        this.modelSelect = document.getElementById('modelSelect');
        this.charCount = document.getElementById('charCount');
    }

    setupEventListeners() {
        this.sendButton.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.messageInput.addEventListener('input', () => this.handleInputChange());
        this.clearButton.addEventListener('click', () => this.clearChat());
    }

    initializeWelcomeMessage() {
        document.getElementById('welcomeTime').textContent = this.getCurrentTime();
    }

    async refreshBackendBanner() {
        const el = ensureBackendStatusBanner();
        const ok = await pingBackend();
        if (ok) {
            el.hidden = true;
            el.textContent = '';
            return;
        }
        const base = getApiBase() || window.location.origin;
        el.hidden = false;
        el.innerHTML =
            '<strong>백엔드가 응답하지 않습니다.</strong> ' +
            '<code style="background:rgba(0,0,0,.08);padding:2px 6px;border-radius:4px;">cd chat_ui && python app.py</code> 실행 후 ' +
            `<a href="${base}/" style="color:inherit;">${base}/</a> 로 접속해 보세요.`;
    }

    handleInputChange() {
        const text = this.messageInput.value.trim();
        const length = text.length;

        this.charCount.textContent = `${length} / 2000`;
        this.sendButton.disabled = length === 0 || this.isLoading || length > 2000;

        // Auto-resize textarea
        this.messageInput.style.height = 'auto';
        this.messageInput.style.height = Math.min(this.messageInput.scrollHeight, 120) + 'px';
    }

    async sendMessage() {
        const text = this.messageInput.value.trim();
        if (!text || this.isLoading) return;

        // Add user message
        this.addMessage(text, 'user');
        this.messageInput.value = '';
        this.handleInputChange();

        // Show loading
        this.setLoading(true);
        const loadingId = this.addLoadingMessage();

        try {
            const response = await this.callAPI(text);
            
            // Remove loading message only if streaming didn't already update it
            const loadingElement = this.chatMessages.querySelector(`[data-id="${loadingId}"]`);
            if (loadingElement && loadingElement.classList.contains('loading')) {
                this.removeMessage(loadingId);
                this.addMessage(response, 'assistant');
            } else {
                // Streaming already updated the message, just add it to history
                this.messages.push({
                    id: Date.now() + Math.random(),
                    content: response,
                    role: 'assistant',
                    timestamp: new Date()
                });
            }
        } catch (error) {
            this.removeMessage(loadingId);
            this.addMessage('죄송합니다. 오류가 발생했습니다: ' + formatFetchError(error), 'assistant', true);
            this.refreshBackendBanner();
        } finally {
            this.setLoading(false);
        }
    }

    async callAPI(message) {
        const url = `${getApiBase()}/api/chat`;
        chatInfo('POST /api/chat', url, { model: this.modelSelect.value, messageLen: message.length });
        chatLog('자세한 SSE 로그는 URL에 ?debug=1 또는 localStorage.chat_ui_debug=1');

        let response;
        try {
            response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    model: this.modelSelect.value,
                    stream: true,
                    history: this.messages.slice(-10) // Send last 10 messages for context
                })
            });
        } catch (e) {
            throw new Error(formatFetchError(e));
        }

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        chatLog('response headers', Object.fromEntries(response.headers.entries()));

        // Handle streaming response (SSE text/event-stream)
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let fullResponse = '';
        let chunkSeq = 0;

        while (true) {
            const { done, value } = await reader.read();

            if (done) {
                chatLog('stream reader done, buffer remainder len=', buffer.length);
                break;
            }

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() ?? ''; // Keep incomplete line in buffer

            for (const rawLine of lines) {
                const line = rawLine.replace(/\r$/, '');
                if (!line.startsWith('data: ')) {
                    continue;
                }

                const payload = line.slice(6).trim();
                if (!payload) {
                    continue;
                }

                try {
                    const data = JSON.parse(payload);

                    if (data.type === 'chunk' || data.type === 'done') {
                        fullResponse = data.content;
                        chunkSeq += 1;
                        const len = fullResponse != null ? String(fullResponse).length : 0;
                        if (chunkSeq === 1 || data.type === 'done' || chunkSeq % 8 === 0) {
                            chatInfo(`SSE ${data.type} #${chunkSeq} 누적 길이=${len}`);
                        } else {
                            chatLog(`SSE ${data.type} #${chunkSeq} len=${len}`);
                        }
                        if (chatUiDebug()) {
                            chatLog('preview(120자):', fullResponse != null ? String(fullResponse).slice(0, 120) : '');
                        }
                        this.updateStreamingMessage(fullResponse);
                    } else if (data.type === 'error') {
                        throw new Error(data.content);
                    } else if (data.type === 'info') {
                        chatInfo('SSE info:', data.content);
                    }
                } catch (e) {
                    if (e instanceof SyntaxError) {
                        chatLog('skip non-JSON SSE line:', payload.slice(0, 80));
                        continue;
                    }
                    throw e;
                }
            }
        }

        this.finishStreamingAssistantMessage();
        chatInfo('callAPI finished, total response length=', fullResponse != null ? String(fullResponse).length : 0);

        return fullResponse;
    }

    /**
     * 스트리밍 동안 여러 번 호출됨. 첫 청크 이후에도 동일한 [data-streaming] 버블을 계속 갱신해야 함
     * (이전 코드는 첫 청크에서만 .loading 이 있어서 이후 청크가 화면에 반영되지 않았음).
     */
    updateStreamingMessage(content) {
        const el = this.chatMessages.querySelector('.message.assistant[data-streaming="true"]');
        if (!el) {
            chatInfo('updateStreamingMessage: no [data-streaming] bubble (skipped)');
            return;
        }
        const contentDiv = el.querySelector('.message-content');
        if (!contentDiv) {
            return;
        }
        el.classList.remove('loading');
        const text = content == null ? '' : String(content);
        contentDiv.innerHTML = this.formatMessage(text);
        this.scrollToBottom();
    }

    /** 스트림 종료 후 DOM 마무리(같은 답변이 히스토리에 이중으로 쌓이지 않게 data-streaming 만 제거) */
    finishStreamingAssistantMessage() {
        const el = this.chatMessages.querySelector('.message.assistant[data-streaming="true"]');
        if (!el) {
            return;
        }
        el.removeAttribute('data-streaming');
        if (!el.querySelector('.message-time')) {
            const t = document.createElement('div');
            t.className = 'message-time';
            t.textContent = this.getCurrentTime();
            el.appendChild(t);
        }
    }

    addMessage(content, role, isError = false) {
        const messageId = Date.now() + Math.random();
        const message = { id: messageId, content, role, timestamp: new Date(), isError };
        this.messages.push(message);

        const messageElement = this.createMessageElement(message);
        this.chatMessages.appendChild(messageElement);
        this.scrollToBottom();

        return messageId;
    }

    addLoadingMessage() {
        const messageElement = document.createElement('div');
        messageElement.className = 'message assistant loading';
        messageElement.setAttribute('data-streaming', 'true');
        messageElement.innerHTML = `
            <div class="message-content">
                <div class="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        `;

        const loadingId = Date.now() + Math.random();
        messageElement.dataset.id = loadingId;

        this.chatMessages.appendChild(messageElement);
        chatLog('addLoadingMessage data-streaming=true id=', loadingId);
        this.scrollToBottom();

        return loadingId;
    }

    removeMessage(messageId) {
        const element = this.chatMessages.querySelector(`[data-id="${messageId}"]`);
        if (element) {
            element.remove();
        }
    }

    createMessageElement(message) {
        const messageElement = document.createElement('div');
        messageElement.className = `message ${message.role} ${message.isError ? 'error' : ''}`;
        messageElement.dataset.id = message.id;

        messageElement.innerHTML = `
            <div class="message-content">${this.formatMessage(message.content)}</div>
            <div class="message-time">${this.formatTime(message.timestamp)}</div>
        `;

        return messageElement;
    }

    formatMessage(content) {
        // Basic markdown-like formatting
        return content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    formatTime(timestamp) {
        return timestamp.toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    getCurrentTime() {
        return new Date().toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    setLoading(loading) {
        this.isLoading = loading;
        this.sendButton.disabled = loading || this.messageInput.value.trim().length === 0;
        this.messageInput.disabled = loading;

        if (loading) {
            this.sendButton.innerHTML = `
                <div class="spinner"></div>
            `;
        } else {
            this.sendButton.innerHTML = `
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                </svg>
            `;
        }
    }

    clearChat() {
        if (confirm('모든 대화를 삭제하시겠습니까?')) {
            this.messages = [];
            this.chatMessages.innerHTML = `
                <div class="message assistant">
                    <div class="message-content">
                        대화가 초기화되었습니다. 새로운 대화를 시작해보세요!
                    </div>
                    <div class="message-time">${this.getCurrentTime()}</div>
                </div>
            `;
        }
    }

    scrollToBottom() {
        setTimeout(() => {
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        }, 100);
    }
}

// Initialize chat UI when page loads
document.addEventListener('DOMContentLoaded', () => {
    new ChatUI();
});