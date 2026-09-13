/**
 * ERISVoice
 * Wraps the browser's native Web Speech APIs so the console can listen and
 * speak without any server-side audio plumbing:
 *  - SpeechRecognition -> live transcription into the prompt field
 *  - SpeechSynthesis    -> reads ERIS's replies aloud
 *  - getUserMedia + AnalyserNode -> real mic amplitude for the orb animation
 *
 * Everything here runs entirely client-side. If the browser doesn't support
 * these APIs, the console degrades gracefully to text-only.
 */
class ERISVoice {
    constructor() {
        const SpeechRecognitionImpl = window.SpeechRecognition || window.webkitSpeechRecognition;
        this.supportsSTT = !!SpeechRecognitionImpl;
        this.supportsTTS = 'speechSynthesis' in window;

        this.recognition = null;
        this.isListening = false;
        this.audioCtx = null;
        this.analyser = null;
        this.micStream = null;
        this.rafId = null;

        this.onInterim = () => {};
        this.onFinal = () => {};
        this.onEnd = () => {};
        this.onAmplitude = () => {};
        this.onError = () => {};

        if (this.supportsSTT) {
            this.recognition = new SpeechRecognitionImpl();
            this.recognition.continuous = false;
            this.recognition.interimResults = true;
            this.recognition.maxAlternatives = 1;

            this.recognition.onresult = (event) => {
                let interim = '';
                let final = '';
                for (let i = event.resultIndex; i < event.results.length; i++) {
                    const transcript = event.results[i][0].transcript;
                    if (event.results[i].isFinal) final += transcript;
                    else interim += transcript;
                }
                if (interim) this.onInterim(interim);
                if (final) this.onFinal(final.trim());
            };

            this.recognition.onerror = (event) => {
                this.onError(event.error);
                this.stopListening();
            };

            this.recognition.onend = () => {
                this.isListening = false;
                this._stopAmplitudeLoop();
                this.onEnd();
            };
        }
    }

    setLanguage(lang) {
        if (this.recognition) this.recognition.lang = lang || 'en-US';
    }

    startListening(lang) {
        if (!this.supportsSTT || this.isListening) return false;
        this.setLanguage(lang);
        try {
            this.recognition.start();
            this.isListening = true;
            this._startAmplitudeLoop();
            return true;
        } catch (e) {
            this.onError(e.message || 'mic-start-failed');
            return false;
        }
    }

    stopListening() {
        if (this.recognition && this.isListening) {
            try { this.recognition.stop(); } catch (e) { /* no-op */ }
        }
        this.isListening = false;
        this._stopAmplitudeLoop();
    }

    async _startAmplitudeLoop() {
        try {
            if (!this.audioCtx) this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            this.micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const source = this.audioCtx.createMediaStreamSource(this.micStream);
            this.analyser = this.audioCtx.createAnalyser();
            this.analyser.fftSize = 256;
            source.connect(this.analyser);
            const data = new Uint8Array(this.analyser.frequencyBinCount);

            const tick = () => {
                if (!this.analyser) return;
                this.analyser.getByteFrequencyData(data);
                const avg = data.reduce((a, b) => a + b, 0) / data.length;
                this.onAmplitude(Math.min(1, avg / 90));
                this.rafId = requestAnimationFrame(tick);
            };
            tick();
        } catch (e) {
            // Amplitude visualization is a nice-to-have; recognition still works without mic-level access.
            console.warn('Mic amplitude stream unavailable:', e.message);
        }
    }

    _stopAmplitudeLoop() {
        if (this.rafId) cancelAnimationFrame(this.rafId);
        this.rafId = null;
        if (this.micStream) {
            this.micStream.getTracks().forEach((t) => t.stop());
            this.micStream = null;
        }
        this.analyser = null;
    }

    speak(text, { rate = 1.0, onStart, onEnd } = {}) {
        if (!this.supportsTTS || !text) {
            if (onEnd) onEnd();
            return;
        }
        window.speechSynthesis.cancel();
        const clean = text.replace(/[*_`#]/g, '');
        const utterance = new SpeechSynthesisUtterance(clean);
        utterance.rate = Math.max(0.5, Math.min(2, rate));
        utterance.onstart = () => onStart && onStart();
        utterance.onend = () => onEnd && onEnd();
        utterance.onerror = () => onEnd && onEnd();
        window.speechSynthesis.speak(utterance);
    }

    stopSpeaking() {
        if (this.supportsTTS) window.speechSynthesis.cancel();
    }
}

window.erisVoice = new ERISVoice();
