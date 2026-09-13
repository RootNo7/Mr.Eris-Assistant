/**
 * ERISOrb
 * Drives the visual state of the central "core" avatar and its status line.
 * Also exposes a hook to paint the wave bars from live microphone amplitude
 * while listening, so the console visibly reacts to your voice rather than
 * just looping a canned animation.
 */
class ERISOrb {
    constructor() {
        this.el = document.getElementById('coreOrb');
        this.stateText = document.getElementById('coreStateText');
        this.stateHint = document.getElementById('coreStateHint');
        this.bars = this.el ? Array.from(this.el.querySelectorAll('.wave-bars rect')) : [];

        this.labels = {
            idle: ['Standby', 'Type or speak to begin'],
            listening: ['Listening', 'Speak now — release when done'],
            thinking: ['Processing', 'Reasoning through your request'],
            speaking: ['Responding', 'Playing spoken reply'],
            offline: ['Offline', 'Cannot reach the ERIS engine'],
        };
    }

    setState(state) {
        if (!this.el) return;
        this.el.dataset.state = state;
        const [label, hint] = this.labels[state] || this.labels.idle;
        if (this.stateText) this.stateText.textContent = label;
        if (this.stateHint) this.stateHint.textContent = hint;
        window.erisStore.set({ orbState: state });
    }

    /** Paint bar heights from a 0..1 amplitude value while listening. */
    paintAmplitude(amp) {
        if (!this.bars.length) return;
        const base = 8;
        const max = 46;
        this.bars.forEach((bar, i) => {
            const wobble = 0.55 + 0.45 * Math.sin(Date.now() / 90 + i * 1.3);
            const h = Math.max(base, Math.min(max, base + amp * max * wobble));
            bar.setAttribute('height', h.toFixed(1));
            bar.setAttribute('y', (110 - h / 2).toFixed(1));
        });
    }

    resetBars() {
        this.bars.forEach((bar) => {
            bar.removeAttribute('height');
            bar.removeAttribute('y');
        });
    }
}

window.erisOrb = new ERISOrb();
