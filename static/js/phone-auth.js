/* Phone OTP controls. Supabase sends the SMS; this file never stores the code. */
(function () {
    const state = {
        login: { phone: '', sent: false, busy: false, nextAllowedAt: 0, timer: null },
        register: { phone: '', sent: false, busy: false, nextAllowedAt: 0, timer: null }
    };
    let phoneAuthEnabled = false;

    function text(key, fallback) {
        return typeof t === 'function' ? t(key) : fallback;
    }

    function byId(id) {
        return document.getElementById(id);
    }

    function setPhoneStatus(mode, message, kind) {
        const status = byId(mode + '-phone-status');
        if (!status) return;
        status.textContent = message || '';
        status.classList.remove('text-slate-500', 'text-rose-600', 'text-emerald-600');
        status.classList.add(kind === 'error' ? 'text-rose-600' : kind === 'success' ? 'text-emerald-600' : 'text-slate-500');
    }

    function normalizedPhone(value) {
        const phone = String(value || '').replace(/[\s()-]/g, '');
        return /^\+[1-9]\d{7,14}$/.test(phone) ? phone : '';
    }

    function setAuthMethod(mode, method) {
        const emailPanel = document.querySelector('[data-auth-email-panel="' + mode + '"]');
        const phonePanel = document.querySelector('[data-auth-phone-panel="' + mode + '"]');
        if (emailPanel) emailPanel.classList.toggle('hidden', method !== 'email');
        if (phonePanel) phonePanel.classList.toggle('hidden', method !== 'phone');
        document.querySelectorAll('[data-auth-method-button^="' + mode + '-"]').forEach(button => {
            const active = button.dataset.authMethodButton === mode + '-' + method;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-selected', String(active));
        });
        const disabledNote = byId(mode + '-phone-disabled');
        if (disabledNote) disabledNote.classList.toggle('hidden', method !== 'phone' || phoneAuthEnabled);
        if (method === 'phone') {
            const first = byId(mode === 'login' ? 'login-phone' : 'register-phone-name');
            first?.focus();
        }
    }

    function setCodeStep(mode, visible) {
        const codeStep = byId(mode + '-phone-code-step');
        const send = byId(mode + '-phone-send');
        const verify = byId(mode + '-phone-verify');
        if (codeStep) codeStep.classList.toggle('hidden', !visible);
        if (send) send.classList.toggle('hidden', visible);
        if (verify) verify.classList.toggle('hidden', !visible);
    }

    function updateResendButton(mode) {
        const button = byId(mode + '-phone-resend');
        if (!button) return;
        const remaining = Math.max(0, state[mode].nextAllowedAt - Date.now());
        button.disabled = remaining > 0 || state[mode].busy || !phoneAuthEnabled;
        if (remaining > 0) {
            button.textContent = text('resend_in_seconds', 'Resend in {sec}s').replace('{sec}', String(Math.ceil(remaining / 1000)));
        } else {
            button.textContent = text('resend_code', 'Resend code');
        }
        if (state[mode].timer) window.clearTimeout(state[mode].timer);
        if (remaining > 0) state[mode].timer = window.setTimeout(() => updateResendButton(mode), Math.min(remaining, 1000));
    }

    function resetPhoneFlow(mode) {
        const current = state[mode];
        if (!current) return;
        current.phone = '';
        current.sent = false;
        current.busy = false;
        current.nextAllowedAt = 0;
        if (current.timer) window.clearTimeout(current.timer);
        const phone = byId(mode === 'login' ? 'login-phone' : 'register-phone');
        const code = byId(mode + '-phone-code');
        if (phone) phone.value = '';
        if (code) code.value = '';
        setCodeStep(mode, false);
        updateResendButton(mode);
        setPhoneStatus(mode, '', 'info');
        phone?.focus();
    }

    async function sendPhoneCode(mode, event) {
        event?.preventDefault();
        const current = state[mode];
        if (!current || current.busy) return;
        if (!phoneAuthEnabled) {
            setPhoneStatus(mode, text('phone_not_ready', 'Phone sign-in is unavailable until SMS is configured.'), 'error');
            return;
        }
        if (current.nextAllowedAt > Date.now()) {
            updateResendButton(mode);
            return;
        }
        const phoneInput = byId(mode === 'login' ? 'login-phone' : 'register-phone');
        const phone = normalizedPhone(phoneInput?.value);
        if (!phone) {
            setPhoneStatus(mode, text('phone_format_error', 'Enter a phone number with its country code, for example +998901234567.'), 'error');
            phoneInput?.focus();
            return;
        }
        const nameInput = byId('register-phone-name');
        const displayName = mode === 'register' ? String(nameInput?.value || '').trim() : '';
        if (mode === 'register' && (!displayName || displayName.length > 40)) {
            setPhoneStatus(mode, text('display_name_required', 'Choose a display name up to 40 characters.'), 'error');
            nameInput?.focus();
            return;
        }
        current.busy = true;
        const send = byId(mode + '-phone-send');
        if (send) send.disabled = true;
        updateResendButton(mode);
        try {
            const response = await fetch('/api/auth/phone/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone, mode, display_name: displayName })
            });
            let data = {};
            try { data = await response.json(); } catch (_) {}
            if (!response.ok) throw new Error(data.error || text('phone_send_error', 'Could not send the SMS code.'));
            current.phone = phone;
            current.sent = true;
            current.nextAllowedAt = Date.now() + Math.max(30, Number(data.retry_after) || 60) * 1000;
            setCodeStep(mode, true);
            setPhoneStatus(mode, text('phone_code_sent', 'Code sent. Check your phone.'), 'success');
            byId(mode + '-phone-code')?.focus();
        } catch (error) {
            setPhoneStatus(mode, error.message || text('phone_send_error', 'Could not send the SMS code.'), 'error');
        } finally {
            current.busy = false;
            if (send && !current.sent) send.disabled = false;
            updateResendButton(mode);
        }
    }

    async function uploadPhoneAvatar(session) {
        const custom = typeof customAvatarDataUrl !== 'undefined' ? customAvatarDataUrl : null;
        if (!custom || !session?.access_token || typeof dataUrlToBlob !== 'function') return;
        try {
            const form = new FormData();
            form.append('avatar', dataUrlToBlob(custom), 'avatar.webp');
            const response = await fetch('/api/user/avatar', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + session.access_token },
                body: form
            });
            if (response.ok && typeof customAvatarDataUrl !== 'undefined') customAvatarDataUrl = null;
        } catch (_) {
            // The account is already usable; the user can change the avatar in Profile.
        }
    }

    async function verifyPhoneCode(mode, event) {
        event?.preventDefault();
        const current = state[mode];
        if (!current || current.busy || !current.sent) return;
        const codeInput = byId(mode + '-phone-code');
        const token = String(codeInput?.value || '').trim();
        if (!/^\d{6}$/.test(token)) {
            setPhoneStatus(mode, text('phone_code_error', 'Enter the six-digit SMS code.'), 'error');
            codeInput?.focus();
            return;
        }
        current.busy = true;
        const verify = byId(mode + '-phone-verify');
        if (verify) verify.disabled = true;
        try {
            const response = await fetch('/api/auth/phone/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone: current.phone, token })
            });
            let data = {};
            try { data = await response.json(); } catch (_) {}
            if (!response.ok) throw new Error(data.error || text('phone_verify_error', 'This code is invalid or expired.'));
            if (!supabaseClient) throw new Error('Sign-in is unavailable.');
            const result = await supabaseClient.auth.setSession({ access_token: data.access_token, refresh_token: data.refresh_token });
            if (result?.error) throw result.error;
            if (mode === 'register') await uploadPhoneAvatar(result?.data?.session || data.session);
            setPhoneStatus(mode, text('phone_signed_in', 'Phone verified. Redirecting…'), 'success');
            window.location.href = mode === 'login' ? getLoginDestination() : '/';
        } catch (error) {
            setPhoneStatus(mode, error.message || text('phone_verify_error', 'This code is invalid or expired.'), 'error');
        } finally {
            current.busy = false;
            if (verify) verify.disabled = false;
        }
    }

    async function loadPhoneOptions() {
        document.querySelectorAll('[data-phone-send-button]').forEach(button => { button.disabled = true; });
        try {
            const response = await fetch('/api/auth/options');
            const data = await response.json();
            phoneAuthEnabled = response.ok && data.phone_enabled === true;
        } catch (_) {
            phoneAuthEnabled = false;
        }
        document.querySelectorAll('[data-phone-send-button]').forEach(button => { button.disabled = !phoneAuthEnabled; });
        ['login', 'register'].forEach(mode => updateResendButton(mode));
        const activeMode = document.querySelector('[data-auth-method-button].is-active')?.dataset.authMethodButton;
        if (activeMode) setAuthMethod(activeMode.startsWith('register-') ? 'register' : 'login', activeMode.endsWith('-phone') ? 'phone' : 'email');
    }

    window.setAuthMethod = setAuthMethod;
    window.sendPhoneCode = sendPhoneCode;
    window.verifyPhoneCode = verifyPhoneCode;
    window.resetPhoneFlow = resetPhoneFlow;
    window.phoneAuthState = state;

    document.addEventListener('DOMContentLoaded', loadPhoneOptions);
    window.addEventListener('catrank_language_changed', () => {
        ['login', 'register'].forEach(mode => updateResendButton(mode));
    });
}());
