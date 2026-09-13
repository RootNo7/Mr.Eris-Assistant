/**
 * ERIS Console — Main Controller
 */
document.addEventListener('DOMContentLoaded', async () => {
    const api = window.erisApi;
    const ui = window.erisUI;
    const orb = window.erisOrb;
    const voice = window.erisVoice;
    const store = window.erisStore;

    let isProcessing = false;
    const $ = (id) => document.getElementById(id);

    const promptInput = $('promptInput');
    const sendBtn = $('sendBtn');
    const micBtn = $('micBtn');
    const speakToggleBtn = $('speakToggleBtn');
    const dockLive = $('dockLive');
    const dockLiveText = $('dockLiveText');
    const orbHeard = $('orbHeard');

    // ================================================================
    // Boot
    // ================================================================
    initVoiceUiDefaults();
    wireStatColumn();
    wireAdvancedModal();
    wireDock();
    wireConversationActions();
    wireMemoryPanel();
    wireApprovalsPanel();
    wireOrchestratePanel();
    wireVoicePanel();
    wireAuthModal();
    wireWelcomeChips();

    await loadInitialState();
    startHealthPolling();
    startSystemStatsPolling();
    startApprovalsPolling();
    startClock();

    // ================================================================
    // Stat column (mobile/tablet slide-over)
    // ================================================================
    function wireStatColumn() {
        $('statusToggleBtn').addEventListener('click', () => ui.toggleStatColumn());
        $('statCloseBtn').addEventListener('click', () => ui.closeStatColumn());
        $('refreshEngineBtn').addEventListener('click', async () => {
            try { ui.updateHealth(await api.getHealth()); } catch (e) { ui.setOfflineStatus(); }
        });
    }

    // ================================================================
    // Advanced modal (Memory / Tools / Approvals / Orchestrate / Voice)
    // ================================================================
    function wireAdvancedModal() {
        $('advancedBtn').addEventListener('click', () => ui.openAdvancedModal());
        $('advancedCloseBtn').addEventListener('click', () => ui.closeAdvancedModal());
        document.getElementById('advancedModal').addEventListener('click', (e) => {
            if (e.target.id === 'advancedModal') ui.closeAdvancedModal();
        });
        document.querySelectorAll('.ctx-tab').forEach((btn) => {
            btn.addEventListener('click', () => ui.switchContextTab(btn.dataset.tab));
        });
        document.querySelectorAll('[data-open-tab]').forEach((btn) => {
            btn.addEventListener('click', () => ui.openAdvancedModal(btn.dataset.openTab));
        });
    }

    // ================================================================
    // Command dock: text send + voice mic + speak toggle
    // ================================================================
    function wireDock() {
        promptInput.addEventListener('input', () => {
            promptInput.style.height = 'auto';
            promptInput.style.height = Math.min(120, promptInput.scrollHeight) + 'px';
        });

        promptInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendPrompt();
            }
        });

        sendBtn.addEventListener('click', handleSendPrompt);

        if (!voice.supportsSTT) {
            micBtn.disabled = true;
            micBtn.title = 'Speech recognition is not supported in this browser';
        } else {
            micBtn.addEventListener('click', () => {
                if (voice.isListening) {
                    voice.stopListening();
                } else {
                    dockLive.hidden = false;
                    dockLiveText.textContent = 'Listening…';
                    micBtn.classList.add('is-listening');
                    orb.setState('listening');
                    orb.resetBars();
                    voice.startListening(store.get('micLang'));
                }
            });

            voice.onInterim = (text) => {
                dockLiveText.textContent = text;
                if (orbHeard) orbHeard.textContent = text;
            };
            voice.onFinal = (text) => {
                promptInput.value = text;
                promptInput.dispatchEvent(new Event('input'));
                if (orbHeard) orbHeard.textContent = text;
                if (store.get('autoSend')) handleSendPrompt();
            };
            voice.onAmplitude = (amp) => orb.paintAmplitude(amp);
            voice.onError = (err) => ui.toast(`Voice input error: ${err}`, 'error');
            voice.onEnd = () => {
                micBtn.classList.remove('is-listening');
                dockLive.hidden = true;
                orb.resetBars();
                if (!isProcessing) orb.setState('idle');
            };
        }

        speakToggleBtn.addEventListener('click', () => {
            const next = !store.get('speakReplies');
            store.set({ speakReplies: next });
            localStorage.setItem('eris_speak_replies', String(next));
            syncSpeakToggleUi();
            ui.toast(next ? 'ERIS will speak replies aloud' : 'Spoken replies turned off', 'success');
        });
    }

    function syncSpeakToggleUi() {
        const on = store.get('speakReplies');
        speakToggleBtn.classList.toggle('is-active', on);
        if (!voice.supportsTTS) {
            speakToggleBtn.disabled = true;
            speakToggleBtn.title = 'Speech synthesis is not supported in this browser';
        }
    }

    function initVoiceUiDefaults() {
        syncSpeakToggleUi();
        $('autoSendToggle').checked = store.get('autoSend');
        $('micLangSelect').value = store.get('micLang');
    }

    function wireWelcomeChips() {
        document.querySelectorAll('.chip-suggest').forEach((chip) => {
            chip.addEventListener('click', () => {
                promptInput.value = chip.dataset.fill;
                promptInput.dispatchEvent(new Event('input'));
                handleSendPrompt();
            });
        });
    }

    // ================================================================
    // Conversation header actions: Clear / Extract
    // ================================================================
    function wireConversationActions() {
        $('clearConvoBtn').addEventListener('click', handleClearMemory);
        $('newSessionBtn').addEventListener('click', handleClearMemory);
        $('extractConvoBtn').addEventListener('click', handleExtractConversation);
    }

    function handleExtractConversation() {
        const bubbles = Array.from(document.querySelectorAll('#messages .msg'));
        if (!bubbles.length) {
            ui.toast('Nothing to extract yet', 'error');
            return;
        }
        const lines = ['# ERIS Conversation Export', `Exported ${new Date().toLocaleString()}`, ''];
        bubbles.forEach((bubble) => {
            const role = bubble.classList.contains('user') ? 'You' : 'ERIS';
            const time = bubble.querySelector('.msg-time')?.textContent || '';
            const text = bubble.querySelector('.msg-text')?.textContent || '';
            lines.push(`### ${role} — ${time}`, text, '');
        });
        const blob = new Blob([lines.join('\n')], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `eris-conversation-${Date.now()}.md`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        ui.toast('Conversation exported', 'success');
    }

    // ================================================================
    // Chat send / stream (with automatic non-streaming fallback)
    // ================================================================
    async function handleSendPrompt() {
        const text = promptInput.value.trim();
        if (!text || isProcessing) return;

        isProcessing = true;
        sendBtn.disabled = true;
        promptInput.value = '';
        promptInput.style.height = 'auto';
        orb.setState('thinking');
        if (orbHeard) orbHeard.textContent = text;

        ui.appendMessage('user', text);
        const assistantEl = ui.appendMessage('assistant', '', true);
        let fullText = '';
        let firstChunk = true;
        let usedFallback = false;

        await api.sendMessage(text, false, {
            onFallback: () => { usedFallback = true; },
            onChunk: (chunk) => {
                if (firstChunk) { orb.setState('thinking'); firstChunk = false; }
                fullText += chunk;
                ui.updateStreamingBubble(assistantEl, fullText, false);
            },
            onError: (error) => {
                fullText += (fullText ? '\n\n' : '') + `Error: ${error.message}`;
                ui.updateStreamingBubble(assistantEl, fullText, true, true);
                ui.toast(error.message, 'error');
                isProcessing = false;
                sendBtn.disabled = false;
                orb.setState('idle');
            },
            onDone: async () => {
                ui.updateStreamingBubble(assistantEl, fullText, true);
                if (usedFallback) ui.appendNote(assistantEl, 'Delivered without live streaming for reliability.');
                isProcessing = false;
                sendBtn.disabled = false;
                await loadFacts();
                if (store.get('speakReplies') && fullText) {
                    orb.setState('speaking');
                    const speed = Number($('voiceSpeedRange').value) || 1.0;
                    voice.speak(fullText, { rate: speed, onEnd: () => orb.setState('idle') });
                } else {
                    orb.setState('idle');
                }
            },
        });
    }

    // ================================================================
    // Memory / facts panel
    // ================================================================
    function wireMemoryPanel() {
        $('addFactBtn').addEventListener('click', () => $('factForm').classList.remove('hidden'));
        $('cancelFactBtn').addEventListener('click', () => $('factForm').classList.add('hidden'));
        $('saveFactBtn').addEventListener('click', async () => {
            const key = $('factKeyInput').value.trim();
            const value = $('factValueInput').value.trim();
            const category = $('factCategoryInput').value.trim() || 'general';
            if (!key || !value) { ui.toast('Fact needs both a key and a value', 'error'); return; }
            try {
                await api.addFact(key, value, category);
                $('factKeyInput').value = '';
                $('factValueInput').value = '';
                $('factCategoryInput').value = '';
                $('factForm').classList.add('hidden');
                await loadFacts();
                ui.toast('Fact saved', 'success');
            } catch (err) {
                ui.toast(`Failed to save fact: ${err.message}`, 'error');
            }
        });
    }

    async function handleDeleteFact(key) {
        try { await api.deleteFact(key); await loadFacts(); }
        catch (err) { ui.toast(`Failed to delete fact: ${err.message}`, 'error'); }
    }

    async function loadFacts() {
        try {
            const res = await api.getFacts();
            ui.renderFacts(res.facts || [], handleDeleteFact);
        } catch (err) { console.warn('Failed to load facts:', err); }
    }

    async function handleClearMemory() {
        if (!confirm('Start a new session? This clears the current conversation context.')) return;
        try {
            await api.clearMemory();
            ui.showWelcomeHero();
            ui.toast('New session started', 'success');
        } catch (err) { ui.toast(`Failed to clear memory: ${err.message}`, 'error'); }
    }

    // ================================================================
    // Approvals panel
    // ================================================================
    function wireApprovalsPanel() {
        $('refreshApprovalsBtn').addEventListener('click', loadApprovals);
    }

    async function loadApprovals() {
        try {
            const res = await api.getPendingApprovals();
            ui.renderApprovals(res.approvals || [], {
                onApprove: async (id) => {
                    try { await api.approveApproval(id); ui.toast('Approved', 'success'); await loadApprovals(); }
                    catch (e) { ui.toast(e.message, 'error'); }
                },
                onReject: async (id) => {
                    try { await api.rejectApproval(id); ui.toast('Rejected', 'success'); await loadApprovals(); }
                    catch (e) { ui.toast(e.message, 'error'); }
                },
            });
        } catch (err) { console.warn('Failed to load approvals:', err); }
    }

    function startApprovalsPolling() {
        loadApprovals();
        setInterval(loadApprovals, 15000);
    }

    // ================================================================
    // Orchestration panel
    // ================================================================
    function wireOrchestratePanel() {
        $('runOrchBtn').addEventListener('click', async () => {
            const goal = $('orchGoalInput').value.trim();
            if (!goal) { ui.toast('Describe a goal for ERIS to run', 'error'); return; }
            const btn = $('runOrchBtn');
            btn.disabled = true;
            btn.textContent = 'Running…';
            orb.setState('thinking');
            try {
                const res = await api.postOrchestrate({
                    goal,
                    max_steps: Number($('orchMaxSteps').value) || undefined,
                    max_tool_calls: Number($('orchMaxToolCalls').value) || undefined,
                    max_seconds: Number($('orchMaxSeconds').value) || undefined,
                });
                ui.renderOrchestrationTrace(res.steps || []);
                if (res.final_answer) ui.appendMessage('assistant', res.final_answer);
                ui.toast(`Task ${res.status}`, res.status === 'completed' ? 'success' : 'error');
                await loadFacts();
            } catch (err) {
                ui.toast(`Orchestration failed: ${err.message}`, 'error');
            } finally {
                btn.disabled = false;
                btn.textContent = 'Run task';
                orb.setState('idle');
            }
        });
    }

    // ================================================================
    // Voice panel
    // ================================================================
    function wireVoicePanel() {
        $('autoSendToggle').addEventListener('change', (e) => {
            store.set({ autoSend: e.target.checked });
            localStorage.setItem('eris_auto_send', String(e.target.checked));
        });
        $('micLangSelect').addEventListener('change', (e) => {
            store.set({ micLang: e.target.value });
            localStorage.setItem('eris_mic_lang', e.target.value);
        });
        $('voiceSpeedRange').addEventListener('input', (e) => {
            $('voiceSpeedValue').textContent = `${Number(e.target.value).toFixed(2)}x`;
        });
        $('saveVoiceProfileBtn').addEventListener('click', saveVoiceProfile);
        loadVoiceSettings();
    }

    async function loadVoiceSettings() {
        try {
            const res = await api.getVoiceSettings();
            const p = res.active_profile;
            $('voiceStyleSelect').value = p.response_style || 'neutral';
            $('voiceVerbositySelect').value = p.verbosity || 'normal';
            $('voiceSpeedRange').value = p.speaking_speed || 1.0;
            $('voiceSpeedValue').textContent = `${Number(p.speaking_speed || 1.0).toFixed(2)}x`;
            $('wakeWordInput').value = p.wake_word || 'eris';
            $('wakeWordToggle').checked = !!p.wake_word_enabled;
        } catch (err) {
            console.warn('Voice settings unavailable (auth required or backend offline):', err.message);
        }
    }

    async function saveVoiceProfile() {
        const btn = $('saveVoiceProfileBtn');
        btn.disabled = true;
        try {
            await api.updateVoiceSettings({
                response_style: $('voiceStyleSelect').value,
                verbosity: $('voiceVerbositySelect').value,
                speaking_speed: Number($('voiceSpeedRange').value),
                wake_word: $('wakeWordInput').value.trim() || 'eris',
                wake_word_enabled: $('wakeWordToggle').checked,
            });
            ui.toast('Voice profile saved', 'success');
        } catch (err) {
            ui.toast(`Failed to save voice profile: ${err.message}`, 'error');
        } finally {
            btn.disabled = false;
        }
    }

    // ================================================================
    // System stats polling (CPU/RAM/disk card)
    // ================================================================
    function startSystemStatsPolling() {
        const tick = async () => {
            try { ui.updateSystemStats(await api.getSystemStats()); }
            catch (e) { /* card just shows placeholders */ }
        };
        tick();
        setInterval(tick, 5000);
    }

    // ================================================================
    // Auth modal
    // ================================================================
    function wireAuthModal() {
        $('saveAuthKeyBtn').addEventListener('click', async () => {
            const key = $('authKeyInput').value.trim();
            if (!key) return;
            localStorage.setItem('eris_api_key', key);
            $('authModal').classList.add('hidden');
            $('authErrorMsg').classList.add('hidden');
            await loadInitialState();
        });
        $('authKeyInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') $('saveAuthKeyBtn').click();
        });
    }

    function showAuthModal() { $('authModal').classList.remove('hidden'); }

    // ================================================================
    // Initial state + polling
    // ================================================================
    async function loadInitialState() {
        try {
            const health = await api.getHealth();
            ui.updateHealth(health);

            if (health.auth_enabled && !localStorage.getItem('eris_api_key')) {
                showAuthModal();
                return;
            }

            const toolsRes = await api.getTools();
            ui.renderTools(toolsRes.tools || []);

            await loadFacts();
            await loadVoiceSettings();

            const memoryRes = await api.getMemory();
            if (memoryRes.history && memoryRes.history.length > 0) {
                ui.hideWelcomeHero();
                for (const msg of memoryRes.history) ui.appendMessage(msg.role, msg.text);
            } else {
                ui.showWelcomeHero();
            }
            orb.setState('idle');
        } catch (err) {
            console.error('Failed to load initial state:', err);
            if (err.message.includes('401')) showAuthModal();
            else ui.setOfflineStatus();
        }
    }

    function startHealthPolling() {
        setInterval(async () => {
            try { ui.updateHealth(await api.getHealth()); }
            catch (err) { ui.setOfflineStatus(); }
        }, 10000);
    }

    function startClock() {
        store.set({ sessionStart: Date.now() });
        const tick = () => {
            const now = new Date();
            ui.tickClock(now);
            ui.tickUptime(Date.now() - store.get('sessionStart'));
        };
        tick();
        setInterval(tick, 1000);
    }
});
