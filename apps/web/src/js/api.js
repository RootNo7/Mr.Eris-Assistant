/**
 * ERISApiClient
 * Encapsulates every REST endpoint exposed by backend/server/app.py, plus
 * SSE text streaming for /api/chat/stream. One method per endpoint so the
 * UI layer never needs to know about fetch/headers/error shapes directly.
 */
class ERISApiClient {
    constructor(baseUrl = '') {
        this.baseUrl = baseUrl;
    }

    getHeaders(extraHeaders = {}) {
        const headers = { ...extraHeaders };
        const storedKey = localStorage.getItem('eris_api_key');
        if (storedKey) headers['X-ERIS-API-Key'] = storedKey;
        return headers;
    }

    async _req(path, { method = 'GET', body, headers } = {}) {
        const response = await fetch(`${this.baseUrl}${path}`, {
            method,
            headers: this.getHeaders({
                ...(body ? { 'Content-Type': 'application/json' } : {}),
                ...headers,
            }),
            body: body ? JSON.stringify(body) : undefined,
        });
        if (response.status === 401) throw new Error('401 Unauthorized');
        if (!response.ok) {
            let detail = response.statusText;
            try {
                const errJson = await response.json();
                detail = errJson.detail || detail;
            } catch (e) { /* body wasn't JSON */ }
            throw new Error(detail || `Request to ${path} failed`);
        }
        if (response.status === 204) return null;
        return await response.json();
    }

    // ---- System ----
    getHealth() { return this._req('/api/health'); }
    getSystemStats() { return this._req('/api/system/stats'); }
    getProviders() { return this._req('/api/providers'); }
    getTools() { return this._req('/api/tools'); }

    /** Feature-detect whether this browser can reliably read a streamed fetch body. */
    static supportsStreaming() {
        return typeof window.ReadableStream !== 'undefined' && !!window.fetch;
    }

    // ---- Session memory ----
    getMemory() { return this._req('/api/memory'); }
    clearMemory() { return this._req('/api/memory', { method: 'DELETE' }); }

    // ---- Long-term facts ----
    getFacts() { return this._req('/api/memory/facts'); }
    addFact(key, value, category = 'general') {
        return this._req('/api/memory/facts', { method: 'POST', body: { key, value, category } });
    }
    deleteFact(key) {
        return this._req(`/api/memory/facts/${encodeURIComponent(key)}`, { method: 'DELETE' });
    }

    // ---- Chat ----
    postChat(prompt, clearHistory = false) {
        return this._req('/api/chat', { method: 'POST', body: { prompt, clear_history: clearHistory } });
    }

    /**
     * Send a chat message reliably.
     *
     * Tries Server-Sent Events streaming first (for the live typing effect),
     * but falls back automatically to a single non-streaming POST /api/chat
     * request if:
     *   - this browser/webview can't read streamed fetch bodies at all,
     *   - the server never opens the stream within CONNECT_TIMEOUT_MS, or
     *   - the stream opens but delivers nothing at all before erroring out.
     *
     * This matters in practice: some embedded/mobile WebViews (and some
     * proxies) buffer or drop chunked responses, which previously looked
     * exactly like "ERIS never replied" with no error shown. Now it just
     * quietly gets the same answer a different way.
     *
     * handlers: { onChunk(text), onError(Error), onDone(), onFallback() }
     */
    async sendMessage(prompt, clearHistory = false, handlers = {}) {
        const { onChunk, onError, onDone, onFallback } = handlers;

        if (!ERISApiClient.supportsStreaming()) {
            return this._sendNonStreaming(prompt, clearHistory, handlers);
        }

        const CONNECT_TIMEOUT_MS = 8000;
        const IDLE_TIMEOUT_MS = 25000;
        const controller = new AbortController();
        let receivedAny = false;
        let settled = false;
        let idleTimer = null;

        const connectTimer = setTimeout(() => {
            if (!receivedAny && !settled) { settled = true; controller.abort(); }
        }, CONNECT_TIMEOUT_MS);

        const armIdleTimer = () => {
            clearTimeout(idleTimer);
            idleTimer = setTimeout(() => {
                if (!settled) { settled = true; controller.abort(); }
            }, IDLE_TIMEOUT_MS);
        };
        const clearTimers = () => { clearTimeout(connectTimer); clearTimeout(idleTimer); };

        try {
            const response = await fetch(`${this.baseUrl}/api/chat/stream`, {
                method: 'POST',
                headers: this.getHeaders({ 'Content-Type': 'application/json' }),
                body: JSON.stringify({ prompt, clear_history: clearHistory }),
                signal: controller.signal,
            });
            clearTimeout(connectTimer);

            if (response.status === 401) {
                clearTimers();
                if (onError) onError(new Error('401 Unauthorized'));
                return;
            }
            if (!response.ok || !response.body) {
                clearTimers();
                if (onFallback) onFallback();
                return this._sendNonStreaming(prompt, clearHistory, handlers);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            armIdleTimer();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                armIdleTimer();

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    const trimmed = line.trim();
                    if (!trimmed.startsWith('data: ')) continue;
                    const dataStr = trimmed.replace(/^data:\s*/, '');

                    if (dataStr === '[DONE]') { clearTimers(); if (onDone) onDone(); return; }
                    try {
                        const parsed = JSON.parse(dataStr);
                        if (parsed.error) { clearTimers(); if (onError) onError(new Error(parsed.error)); return; }
                        if (parsed.chunk) { receivedAny = true; if (onChunk) onChunk(parsed.chunk); }
                    } catch (e) {
                        console.warn('Failed to parse SSE payload:', dataStr);
                    }
                }
            }
            clearTimers();
            if (onDone) onDone();
        } catch (err) {
            clearTimers();
            if (receivedAny) {
                // Partial reply already on screen — surface the interruption instead of
                // silently retrying, which would duplicate text the person already sees.
                if (onError) onError(err.name === 'AbortError' ? new Error('Connection stalled mid-reply.') : err);
                return;
            }
            // Nothing arrived at all: most likely this environment can't sustain a
            // streamed response. Retry once, plainly, rather than leaving silence.
            if (onFallback) onFallback();
            return this._sendNonStreaming(prompt, clearHistory, handlers);
        }
    }

    async _sendNonStreaming(prompt, clearHistory, { onChunk, onError, onDone }) {
        try {
            const res = await this.postChat(prompt, clearHistory);
            if (onChunk) onChunk(res.response);
            if (onDone) onDone();
        } catch (err) {
            if (onError) onError(err);
        }
    }

    // ---- Orchestration ----
    postOrchestrate({ goal, max_steps, max_tool_calls, max_seconds, clear_history = false }) {
        return this._req('/api/orchestrate', {
            method: 'POST',
            body: { goal, max_steps, max_tool_calls, max_seconds, clear_history },
        });
    }

    // ---- Voice settings (server-side profile used by the CLI/desktop voice pipeline) ----
    getVoiceSettings() { return this._req('/api/settings/voice'); }
    updateVoiceSettings(updates) { return this._req('/api/settings/voice', { method: 'PUT', body: updates }); }
    listVoiceProfiles() { return this._req('/api/settings/voice/profiles'); }
    selectVoiceProfile(profile) { return this._req('/api/settings/voice/profiles', { method: 'POST', body: profile }); }

    // ---- Approvals ----
    getPendingApprovals(sessionId) {
        const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : '';
        return this._req(`/api/approvals/pending${qs}`);
    }
    getApproval(id) { return this._req(`/api/approvals/${encodeURIComponent(id)}`); }
    approveApproval(id, decidedBy = 'user') {
        return this._req(`/api/approvals/${encodeURIComponent(id)}/approve`, { method: 'POST', body: { decided_by: decidedBy } });
    }
    rejectApproval(id, decidedBy = 'user') {
        return this._req(`/api/approvals/${encodeURIComponent(id)}/reject`, { method: 'POST', body: { decided_by: decidedBy } });
    }
    cancelApproval(id, decidedBy = 'user') {
        return this._req(`/api/approvals/${encodeURIComponent(id)}/cancel`, { method: 'POST', body: { decided_by: decidedBy } });
    }
}

window.erisApi = new ERISApiClient();
