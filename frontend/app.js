/**
 * ERIS Web Client Logic
 * Interfaces with the FastAPI backend for session management and SSE text streaming.
 */

const API_BASE = 'http://localhost:8000/api/v1/chat';

// DOM Elements
const sessionListEl = document.getElementById('session-list');
const chatHistoryEl = document.getElementById('chat-history');
const currentSessionTitleEl = document.getElementById('current-session-title');
const chatForm = document.getElementById('chat-form');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const newSessionBtn = document.getElementById('new-session-btn');

let currentSessionId = null;

// Initialize
document.addEventListener('DOMContentLoaded', loadSessions);
newSessionBtn.addEventListener('click', createNewSession);
chatForm.addEventListener('submit', handleSendMessage);

// Enable Enter to send (Shift+Enter for newline)
userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
});

async function loadSessions() {
    try {
        const res = await fetch(`${API_BASE}/sessions`);
        const sessions = await res.json();
        renderSessionList(sessions);
    } catch (err) {
        console.error("Failed to load sessions", err);
    }
}

function renderSessionList(sessions) {
    sessionListEl.innerHTML = '';
    sessions.forEach(session => {
        const div = document.createElement('div');
        div.className = `session-item ${session.session_id === currentSessionId ? 'active' : ''}`;
        div.textContent = session.title || "New Session";
        div.onclick = () => selectSession(session.session_id, session.title);
        sessionListEl.appendChild(div);
    });
}

async function createNewSession() {
    try {
        const res = await fetch(`${API_BASE}/sessions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: `Session ${new Date().toLocaleTimeString()}` })
        });
        const data = await res.json();
        await loadSessions();
        selectSession(data.session_id, data.title);
    } catch (err) {
        console.error("Failed to create session", err);
    }
}

function selectSession(sessionId, title) {
    currentSessionId = sessionId;
    currentSessionTitleEl.textContent = title;
    chatHistoryEl.innerHTML = '<div class="system-message">Session connected. Start typing...</div>';
    
    // Enable inputs
    userInput.disabled = false;
    sendBtn.disabled = false;
    userInput.focus();

    // Re-render to update active class
    Array.from(sessionListEl.children).forEach(el => {
        el.classList.remove('active');
        if (el.onclick.toString().includes(sessionId)) el.classList.add('active');
    });
}

function appendMessage(role, text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;
    msgDiv.textContent = text;
    chatHistoryEl.appendChild(msgDiv);
    chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
    return msgDiv; // Return element so we can append streamed text to it
}

async function handleSendMessage(e) {
    e.preventDefault();
    if (!currentSessionId || !userInput.value.trim()) return;

    const text = userInput.value.trim();
    userInput.value = '';
    
    // Disable input during generation
    userInput.disabled = true;
    sendBtn.disabled = true;

    // Show user message
    appendMessage('user', text);

    // Create empty assistant message box for streaming
    const assistantMsgEl = appendMessage('assistant', '...');

    try {
        // We use fetch to send a POST request, then manually read the SSE stream
        const response = await fetch(`${API_BASE}/sessions/${currentSessionId}/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, temperature: 0.7 })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        assistantMsgEl.textContent = ''; // Clear the '...'

        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            
            // SSE chunks are separated by double newlines
            const parts = buffer.split('\n\n');
            buffer = parts.pop(); // Keep the last incomplete part in the buffer

            for (const part of parts) {
                if (part.startsWith('data: ')) {
                    const dataStr = part.replace('data: ', '').trim();
                    if (dataStr === '[DONE]') break;
                    
                    try {
                        const dataObj = JSON.parse(dataStr);
                        if (dataObj.delta) {
                            assistantMsgEl.textContent += dataObj.delta;
                            chatHistoryEl.scrollTop = chatHistoryEl.scrollHeight;
                        } else if (dataObj.error) {
                            assistantMsgEl.textContent += `\n[Error: ${dataObj.error}]`;
                        }
                    } catch (e) {
                        console.error("Error parsing JSON stream chunk", e);
                    }
                }
            }
        }
    } catch (err) {
        console.error("Stream failed", err);
        assistantMsgEl.textContent = "[Connection Error]";
    } finally {
        userInput.disabled = false;
        sendBtn.disabled = false;
        userInput.focus();
    }
}
