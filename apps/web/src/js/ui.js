/**
 * ERISUi
 * Pure rendering + DOM-wiring helpers. Nothing here calls the network
 * directly (that's app.js's job) — this module only knows how to paint
 * state onto the dashboard.
 */
class ERISUi {
    constructor() {
        this.$ = (id) => document.getElementById(id);
        this.messages = this.$('messages');
        this.welcome = this.$('welcome');
        this.transcript = this.$('transcript');
    }

    // ---------------------------------------------------------------- HUD --
    updateHealth(health) {
        const online = health.status === 'ok';
        this.setConnection(online);

        this.$('engineProvider').textContent = health.active_provider || '--';
        this.$('engineModel').textContent = health.model || '--';
        this.$('engineVersion').textContent = health.version || '--';
        const authEl = this.$('engineAuth');
        authEl.textContent = health.auth_enabled ? 'Required' : 'Open';
        authEl.classList.toggle('warn', !!health.auth_enabled);

        const chip = this.$('providerChip');
        if (chip) chip.textContent = `${health.active_provider || '--'} · ${health.model || '--'}`;

        window.erisStore.set({
            connected: online,
            authEnabled: !!health.auth_enabled,
            provider: health.active_provider,
            model: health.model,
            version: health.version,
        });
    }

    setConnection(online) {
        const pill = this.$('statusPill');
        const text = this.$('statusPillText');
        pill.classList.toggle('online', online);
        pill.classList.toggle('offline', !online);
        text.textContent = online ? 'Online' : 'Offline';

        const engineStatus = this.$('engineStatus');
        if (engineStatus) {
            engineStatus.textContent = online ? 'Online' : 'Offline';
            engineStatus.classList.toggle('ok', online);
            engineStatus.classList.toggle('warn', !online);
        }

        if (window.erisOrb) {
            const current = window.erisStore.get('orbState');
            if (!online) window.erisOrb.setState('offline');
            else if (current === 'offline') window.erisOrb.setState('idle');
        }
    }

    setOfflineStatus() {
        this.setConnection(false);
        this.$('engineProvider').textContent = '--';
        this.$('engineModel').textContent = '--';
        const chip = this.$('providerChip');
        if (chip) chip.textContent = 'offline';
    }

    updateSystemStats(stats) {
        const note = this.$('resourceNote');
        if (!stats.available) {
            note.hidden = false;
            this.$('cpuPercentText').textContent = '—';
            this.$('ramPercentText').textContent = '—';
            this.$('diskText').textContent = '—';
            this.$('cpuMeterFill').style.width = '0%';
            this.$('ramMeterFill').style.width = '0%';
            return;
        }
        note.hidden = true;
        const cpu = stats.cpu_percent ?? 0;
        const ram = stats.ram_percent ?? 0;
        this.$('cpuPercentText').textContent = `${cpu.toFixed(0)}%`;
        this.$('ramPercentText').textContent = `${ram.toFixed(0)}% (${stats.ram_used_gb}/${stats.ram_total_gb} GB)`;
        this.$('diskText').textContent = `${stats.disk_used_gb}/${stats.disk_total_gb} GB`;

        const cpuFill = this.$('cpuMeterFill');
        cpuFill.style.width = `${Math.min(100, cpu)}%`;
        cpuFill.classList.toggle('warn', cpu >= 70 && cpu < 90);
        cpuFill.classList.toggle('danger', cpu >= 90);

        const ramFill = this.$('ramMeterFill');
        ramFill.style.width = `${Math.min(100, ram)}%`;
        ramFill.classList.toggle('warn', ram >= 70 && ram < 90);
        ramFill.classList.toggle('danger', ram >= 90);
    }

    tickClock(now) {
        const clock = this.$('hudClock');
        const date = this.$('hudDate');
        if (clock) clock.textContent = now.toLocaleTimeString([], { hour12: false });
        if (date) date.textContent = now.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
    }

    tickUptime(ms) {
        const el = this.$('hudUptime');
        if (!el) return;
        const totalSec = Math.floor(ms / 1000);
        const h = String(Math.floor(totalSec / 3600)).padStart(2, '0');
        const m = String(Math.floor((totalSec % 3600) / 60)).padStart(2, '0');
        const s = String(totalSec % 60).padStart(2, '0');
        el.textContent = `${h}:${m}:${s}`;
    }

    // ----------------------------------------------------------- Welcome --
    hideWelcomeHero() { if (this.welcome) this.welcome.classList.add('hidden'); }
    showWelcomeHero() {
        if (this.welcome) this.welcome.classList.remove('hidden');
        if (this.messages) this.messages.innerHTML = '';
        window.erisStore.set({ messageCount: 0 });
        this.updateStatBoxes();
    }

    // ---------------------------------------------------------- Messages --
    appendMessage(role, text, streaming = false) {
        this.hideWelcomeHero();
        const wrap = document.createElement('div');
        wrap.className = `msg ${role}`;

        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar';
        avatar.textContent = role === 'user' ? 'You' : 'E';

        const body = document.createElement('div');
        body.className = 'msg-body';

        const meta = document.createElement('div');
        meta.className = 'msg-meta';
        const roleEl = document.createElement('span');
        roleEl.className = 'msg-role';
        roleEl.textContent = role === 'user' ? 'You' : 'ERIS';
        const timeEl = document.createElement('span');
        timeEl.className = 'msg-time';
        timeEl.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        meta.appendChild(roleEl);
        meta.appendChild(timeEl);

        const textEl = document.createElement('div');
        textEl.className = 'msg-text' + (streaming ? ' is-streaming' : '');
        textEl.textContent = text;

        body.appendChild(meta);
        body.appendChild(textEl);
        wrap.appendChild(avatar);
        wrap.appendChild(body);
        this.messages.appendChild(wrap);
        this._scrollToBottom();

        window.erisStore.set({ messageCount: window.erisStore.get('messageCount') + 1 });
        this.updateStatBoxes();

        return textEl;
    }

    appendNote(textEl, note) {
        if (!textEl || !textEl.parentElement) return;
        let noteEl = textEl.parentElement.querySelector('.msg-note');
        if (!noteEl) {
            noteEl = document.createElement('div');
            noteEl.className = 'msg-note';
            textEl.parentElement.appendChild(noteEl);
        }
        noteEl.textContent = note;
    }

    updateStreamingBubble(el, text, done, isError = false) {
        el.textContent = text;
        el.classList.toggle('is-streaming', !done);
        el.classList.toggle('is-error', isError);
        this._scrollToBottom();
    }

    _scrollToBottom() {
        if (this.transcript) this.transcript.scrollTop = this.transcript.scrollHeight;
    }

    // -------------------------------------------------------------- Stats --
    updateStatBoxes() {
        const s = window.erisStore.get();
        const setEl = (id, v) => { const el = this.$(id); if (el) el.textContent = v; };
        setEl('statMessages', s.messageCount);
    }

    // -------------------------------------------------------------- Facts --
    renderFacts(facts, onDelete) {
        window.erisStore.set({ factsCount: facts.length });

        // Mini preview (always-visible stat column)
        const mini = this.$('factsMiniList');
        mini.innerHTML = '';
        if (!facts.length) {
            mini.innerHTML = '<div class="empty-note">No facts stored yet.</div>';
        } else {
            facts.slice(0, 4).forEach((fact) => {
                const row = document.createElement('div');
                row.className = 'mini-item';
                row.innerHTML = `<span class="mi-key">${this._esc(fact.key)}</span><span class="mi-val">${this._esc(fact.value)}</span>`;
                mini.appendChild(row);
            });
        }

        // Full manageable list (advanced modal)
        const container = this.$('factsList');
        container.innerHTML = '';
        if (!facts.length) {
            container.innerHTML = '<div class="empty-note">No stored facts yet. ERIS learns these automatically as you talk, or add one manually.</div>';
            return;
        }
        facts.forEach((fact) => {
            const card = document.createElement('div');
            card.className = 'item-card';
            card.innerHTML = `
                <div class="item-card-head">
                    <div>
                        <div class="item-title">${this._esc(fact.key)}</div>
                        <div class="item-sub">${this._esc(fact.value)}</div>
                    </div>
                    <button class="icon-mini-btn" title="Delete fact">
                        <svg viewBox="0 0 24 24"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    </button>
                </div>
                <div class="item-actions"><span class="tag">${this._esc(fact.category || 'general')}</span></div>
            `;
            card.querySelector('.icon-mini-btn').addEventListener('click', () => onDelete(fact.key));
            container.appendChild(card);
        });
    }

    // -------------------------------------------------------------- Tools --
    renderTools(tools) {
        window.erisStore.set({ toolsCount: tools.length });

        const mini = this.$('toolsMiniList');
        mini.innerHTML = '';
        if (!tools.length) {
            mini.innerHTML = '<div class="empty-note">No tools registered.</div>';
        } else {
            tools.slice(0, 4).forEach((tool) => {
                const row = document.createElement('div');
                row.className = 'mini-item';
                row.innerHTML = `<span class="mi-key">${this._esc(tool.name)}</span>`;
                mini.appendChild(row);
            });
        }

        const container = this.$('toolsList');
        container.innerHTML = '';
        if (!tools.length) {
            container.innerHTML = '<div class="empty-note">No tools registered.</div>';
            return;
        }
        tools.forEach((tool) => {
            const card = document.createElement('div');
            card.className = 'item-card';
            card.innerHTML = `<div class="item-title">${this._esc(tool.name)}</div><div class="item-sub">${this._esc(tool.description)}</div>`;
            container.appendChild(card);
        });
    }

    // --------------------------------------------------------- Approvals --
    renderApprovals(approvals, handlers) {
        window.erisStore.set({ pendingApprovalsCount: approvals.length });

        const countEl = this.$('ctxApprovalsBadge');
        if (countEl) {
            countEl.hidden = approvals.length === 0;
            countEl.textContent = approvals.length ? String(approvals.length) : '';
        }
        const dot = this.$('advancedBtnDot');
        if (dot) dot.hidden = approvals.length === 0;

        const alertBtn = this.$('approvalsAlertBtn');
        const alertText = this.$('approvalsAlertText');
        if (alertBtn) {
            alertBtn.classList.toggle('hidden', approvals.length === 0);
            if (alertText) alertText.textContent = `${approvals.length} pending approval${approvals.length === 1 ? '' : 's'}`;
        }

        const container = this.$('approvalsList');
        container.innerHTML = '';
        if (!approvals.length) {
            container.innerHTML = '<div class="empty-note">No pending approvals. All clear.</div>';
            return;
        }
        approvals.forEach((a) => {
            const card = document.createElement('div');
            card.className = 'item-card';
            card.innerHTML = `
                <div class="item-card-head">
                    <div class="item-title">${this._esc(a.tool_name)} — ${this._esc(a.action)}</div>
                    <span class="tag risk-${a.risk_level}">T${a.risk_level}</span>
                </div>
                <div class="item-sub">${this._esc(a.reason)}</div>
                <div class="item-actions">
                    <button class="btn-solid small" data-act="approve">Approve</button>
                    <button class="btn-ghost small" data-act="reject">Reject</button>
                </div>
            `;
            card.querySelector('[data-act="approve"]').addEventListener('click', () => handlers.onApprove(a.approval_id));
            card.querySelector('[data-act="reject"]').addEventListener('click', () => handlers.onReject(a.approval_id));
            container.appendChild(card);
        });
    }

    // ------------------------------------------------------ Orchestration --
    renderOrchestrationTrace(steps) {
        const container = this.$('orchTrace');
        container.innerHTML = '';
        steps.forEach((step) => {
            const div = document.createElement('div');
            div.className = `trace-step status-${step.status}`;
            div.innerHTML = `
                <div><span class="step-idx">#${step.step_index}</span> <span class="tag">${this._esc(step.status)}</span></div>
                <div class="step-thought">${this._esc(step.thought)}</div>
                ${step.tool_name ? `<div class="step-tool">→ ${this._esc(step.tool_name)}(${this._esc(JSON.stringify(step.tool_args || {}))})</div>` : ''}
                ${step.observation ? `<div class="step-tool">${this._esc(step.observation)}</div>` : ''}
            `;
            container.appendChild(div);
        });
    }

    // -------------------------------------------------------------- Tabs --
    switchContextTab(tabName) {
        document.querySelectorAll('.ctx-tab').forEach((t) => t.classList.toggle('is-active', t.dataset.tab === tabName));
        document.querySelectorAll('.ctx-view').forEach((v) => v.classList.toggle('is-active', v.dataset.view === tabName));
    }

    openAdvancedModal(tabName) {
        if (tabName) this.switchContextTab(tabName);
        this.$('advancedModal').classList.remove('hidden');
    }
    closeAdvancedModal() { this.$('advancedModal').classList.add('hidden'); }

    openStatColumn() { this.$('statColumn').classList.add('is-open'); }
    closeStatColumn() { this.$('statColumn').classList.remove('is-open'); }
    toggleStatColumn() { this.$('statColumn').classList.toggle('is-open'); }

    // ------------------------------------------------------------- Toast --
    toast(message, type = 'info') {
        const stack = this.$('toastStack');
        const el = document.createElement('div');
        el.className = `toast ${type}`;
        el.textContent = message;
        stack.appendChild(el);
        setTimeout(() => {
            el.style.opacity = '0';
            el.style.transition = 'opacity 0.25s ease';
            setTimeout(() => el.remove(), 260);
        }, 3600);
    }

    _esc(str) {
        const div = document.createElement('div');
        div.textContent = str == null ? '' : String(str);
        return div.innerHTML;
    }
}

window.erisUI = new ERISUi();
