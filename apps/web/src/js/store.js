/**
 * ERISStore
 * A tiny, dependency-free pub/sub state container. Keeps the console's
 * modules (ui, voice, orb, app) decoupled: any module can read/patch shared
 * state and any module can subscribe to react to changes, without every
 * file needing to know about every other file.
 */
class ERISStore {
    constructor(initial = {}) {
        this.state = { ...initial };
        this.listeners = new Set();
    }

    get(key) {
        return key ? this.state[key] : this.state;
    }

    set(patch) {
        this.state = { ...this.state, ...patch };
        this.listeners.forEach((fn) => {
            try { fn(this.state, patch); } catch (e) { console.error('Store listener error:', e); }
        });
    }

    subscribe(fn) {
        this.listeners.add(fn);
        return () => this.listeners.delete(fn);
    }
}

window.erisStore = new ERISStore({
    connected: false,
    authEnabled: false,
    provider: '--',
    model: '--',
    version: '--',
    sessionStart: Date.now(),
    messageCount: 0,
    factsCount: 0,
    toolsCount: 0,
    pendingApprovalsCount: 0,
    orbState: 'idle', // idle | listening | thinking | speaking | offline
    speakReplies: (localStorage.getItem('eris_speak_replies') === 'true'),
    autoSend: (localStorage.getItem('eris_auto_send') !== 'false'),
    micLang: localStorage.getItem('eris_mic_lang') || 'en-US',
});
