class ChatUI {
    constructor() {
        this.messages = [];
        this.isLoading = false;
        this.initializeElements();
        this.setupEventListeners();
        this.initializeWelcomeMessage();
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
            this.addMessage('죄송합니다. 오류가 발생했습니다: ' + error.message, 'assistant', true);
        } finally {
            this.setLoading(false);
        }
    }

    async callAPI(message) {
        const response = await fetch('/api/chat', {
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

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        // Handle streaming response
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let fullResponse = '';

        while (true) {
            const { done, value } = await reader.read();
            
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.substring(6));
                        
                        if (data.type === 'chunk' || data.type === 'done') {
                            fullResponse = data.content;
                            // Update the message in real-time
                            this.updateStreamingMessage(fullResponse);
                        } else if (data.type === 'error') {
                            throw new Error(data.content);
                        } else if (data.type === 'info') {
                            console.log('Info:', data.content);
                        }
                    } catch (e) {
                        if (e instanceof SyntaxError) {
                            // Ignore JSON parse errors for keepalive messages
                            continue;
                        }
                        throw e;
                    }
                }
            }
        }

        return fullResponse;
    }

    updateStreamingMessage(content) {
        // Find the last assistant message (the loading one) and update it
        const messages = this.chatMessages.querySelectorAll('.message.assistant');
        if (messages.length > 0) {
            const lastMessage = messages[messages.length - 1];
            const contentDiv = lastMessage.querySelector('.message-content');
            if (contentDiv && lastMessage.classList.contains('loading')) {
                // Remove loading class and update content
                lastMessage.classList.remove('loading');
                contentDiv.innerHTML = this.formatMessage(content);
            }
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