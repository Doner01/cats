async function authRequest(path, payload, method = 'POST', authenticated = false) {
    const headers = {'Content-Type': 'application/json'};
    if (authenticated) {
        if (!supabaseClient) throw new Error('Authentication is unavailable.');
        const {data: {session}} = await supabaseClient.auth.getSession();
        if (!session) throw new Error('Please sign in again.');
        headers.Authorization = `Bearer ${session.access_token}`;
    }
    const res = await fetch(path, {method, headers, body: JSON.stringify(payload)});
    let data = {};
    try { data = await res.json(); } catch (_) {}
    if (!res.ok) {
        const error = new Error(data.error || 'This request could not be completed.');
        error.code = data.code || '';
        error.status = res.status;
        throw error;
    }
    return data;
}

async function signInWithPasswordThroughApp(email, password) {
    try {
        const tokens = await authRequest('/api/auth/login', {email, password});
        return await supabaseClient.auth.setSession(tokens);
    } catch (error) { return {data: null, error}; }
}

async function startGoogleSignIn(link = false) {
    const buttons = document.querySelectorAll('[data-google-button]');
    buttons.forEach(b => b.disabled = true);
    try {
        if (!supabaseClient) throw new Error('Sign-in is unavailable.');
        const res = await fetch('/api/auth/options');
        const options = await res.json();
        if (!res.ok || !options.google_enabled) throw new Error(options.error || 'Google sign-in is not enabled yet.');
        const {data: {session}} = await supabaseClient.auth.getSession();
        if (link && !session) throw new Error('Please sign in before connecting Google.');
        const intent = {next: link ? '/profile' : getLoginDestination(), userId: link ? session.user.id : null, started: Date.now()};
        sessionStorage.setItem('catrank_oauth_intent', JSON.stringify(intent));
        const params = {provider: 'google', options: {redirectTo: window.location.origin + '/auth/callback', queryParams: {prompt: 'select_account'}}};
        const {error} = link ? await supabaseClient.auth.linkIdentity(params) : await supabaseClient.auth.signInWithOAuth(params);
        if (error) throw error;
    } catch (error) {
        sessionStorage.removeItem('catrank_oauth_intent');
        showToast(error.message, 'error');
        buttons.forEach(b => b.disabled = false);
    }
}

async function completeGoogleSignIn() {
    const message = document.getElementById('oauth-status');
    if (!message) return;
    try {
        const params = new URLSearchParams(window.location.search);
        const code = params.get('code');
        const providerError = params.get('error') || new URLSearchParams(window.location.hash.slice(1)).get('error');
        const intent = JSON.parse(sessionStorage.getItem('catrank_oauth_intent') || 'null');
        history.replaceState(null, '', '/auth/callback');
        if (providerError) throw new Error('Google sign-in was cancelled or could not be completed.');
        if (!code || !intent || Date.now() - intent.started > 10 * 60 * 1000) throw new Error('This sign-in attempt has expired. Please start again.');
        const {data, error} = await supabaseClient.auth.exchangeCodeForSession(code);
        if (error || !data.session) throw new Error('Could not verify this sign-in. Please start again in the same browser.');
        if (intent.userId && data.session.user.id !== intent.userId) {
            await supabaseClient.auth.signOut({scope: 'local'});
            throw new Error('The connected account did not match. Please sign in again.');
        }
        await authRequest('/api/auth/bootstrap', {}, 'POST', true);
        sessionStorage.removeItem('catrank_oauth_intent');
        const destination = new URL(intent.next || '/', window.location.origin);
        window.location.replace(destination.origin === window.location.origin && destination.pathname !== '/auth/callback' ? destination.pathname + destination.search + destination.hash : '/');
    } catch (error) {
        sessionStorage.removeItem('catrank_oauth_intent');
        message.textContent = error.message || 'Sign-in could not be completed.';
        document.getElementById('oauth-back')?.classList.remove('hidden');
    }
}

const accountSecurityState = {
    session: null,
    user: null,
    identities: [],
    hasEmailPassword: false,
    hasGoogle: false
};

let activeSecurityMethod = null;

function securityText(key, fallback) {
    if (typeof t !== 'function') return fallback;
    const value = t(key);
    return value && value !== key ? value : fallback;
}

function setSecurityHidden(id, hidden) {
    const element = document.getElementById(id);
    if (element) element.classList.toggle('hidden', hidden);
}

function setSecurityStatusText(id, message, kind = 'info') {
    const element = document.getElementById(id);
    if (!element) return;
    element.textContent = message || '';
    element.classList.remove('text-slate-500', 'text-rose-600', 'text-emerald-600', 'text-indigo-600');
    element.classList.add(kind === 'error' ? 'text-rose-600' : kind === 'success' ? 'text-emerald-600' : kind === 'active' ? 'text-indigo-600' : 'text-slate-500');
}

function setMethodBadge(id, connected, alternateText = '') {
    const element = document.getElementById(id);
    if (!element) return;
    const label = alternateText || (connected ? securityText('connected_badge', 'Connected') : securityText('not_connected_badge', 'Not connected'));
    element.textContent = label;
    element.className = connected
        ? 'text-[10px] font-black rounded-full px-2 py-0.5 bg-emerald-50 text-emerald-700'
        : 'text-[10px] font-black rounded-full px-2 py-0.5 bg-slate-100 text-slate-500';
}


function friendlySecurityAuthError(error, fallback) {
    const code = String(error?.code || '').toLowerCase();
    const message = String(error?.message || '');
    if (['user_already_exists', 'email_exists', 'identity_already_exists'].includes(code) || /already.*(registered|exists|used)/i.test(message)) {
        return securityText('signin_method_in_use', 'That email is already connected to another account.');
    }
    return message || fallback;
}

function providerSetForUser(user, identities) {
    const providers = new Set();
    for (const identity of identities || []) {
        if (identity && identity.provider) providers.add(String(identity.provider));
    }
    const appMeta = user?.app_metadata || {};
    const listed = Array.isArray(appMeta.providers) ? appMeta.providers : [];
    for (const provider of listed) providers.add(String(provider));
    if (appMeta.provider) providers.add(String(appMeta.provider));
    return providers;
}

function getProviderIdentityEmail(user, provider, identities = null) {
    const wanted = String(provider || '').toLowerCase();
    const list = Array.isArray(identities)
        ? identities
        : (Array.isArray(user?.identities) ? user.identities : []);

    for (const identity of list) {
        if (!identity || String(identity.provider || '').toLowerCase() !== wanted) continue;
        const data = identity.identity_data && typeof identity.identity_data === 'object'
            ? identity.identity_data
            : {};
        const email = String(data.email || identity.email || '').trim().toLowerCase();
        if (email) return email;
    }
    return '';
}

function getProfileEmailForUser(user, identities = null) {
    if (!user) return '';
    const primaryEmail = String(user.email || '').trim().toLowerCase();
    const list = Array.isArray(identities)
        ? identities
        : (Array.isArray(user.identities) ? user.identities : []);
    const providers = providerSetForUser(user, list);
    const primaryProvider = String(user?.app_metadata?.provider || '').toLowerCase();
    const googleEmail = getProviderIdentityEmail(user, 'google', list);

    // A Supabase account can keep its original Google identity even after the
    // account's primary/email-password address is changed. For profiles, show
    // the Google identity email when Google is the account's original/only
    // sign-in provider so the UI does not pretend that Google is using the
    // newer password email.
    if (googleEmail && (primaryProvider === 'google' || (providers.has('google') && !providers.has('email')))) {
        return googleEmail;
    }
    return primaryEmail || googleEmail;
}

async function refreshAccountSecuritySession() {
    if (!supabaseClient) throw new Error('Authentication is unavailable.');
    const sessionResult = await supabaseClient.auth.getSession();
    const session = sessionResult?.data?.session || null;
    if (!session) throw new Error('Please sign in again.');
    let user = session.user;
    try {
        const result = await supabaseClient.auth.getUser();
        if (!result.error && result.data?.user) user = result.data.user;
    } catch (_) {}
    accountSecurityState.session = session;
    accountSecurityState.user = user;
    if (typeof currentSession !== 'undefined') currentSession = session;
    return {session, user};
}

async function loadConnectedMethods() {
    const container = document.getElementById('connected-methods');
    if (!container || !supabaseClient) return;
    try {
        const {user} = await refreshAccountSecuritySession();
        let identities = [];
        try {
            const identityResult = await supabaseClient.auth.getUserIdentities();
            if (!identityResult.error) identities = identityResult.data?.identities || [];
        } catch (_) {
            identities = Array.isArray(user.identities) ? user.identities : [];
        }
        accountSecurityState.identities = identities;
        const providers = providerSetForUser(user, identities);
        accountSecurityState.hasEmailPassword = Boolean(user.email) && providers.has('email');
        accountSecurityState.hasGoogle = providers.has('google');

        const methods = [];
        if (accountSecurityState.hasEmailPassword) methods.push('Email');
        if (accountSecurityState.hasGoogle) methods.push('Google');
        container.textContent = methods.join(' · ') || securityText('no_methods_found', 'No methods found');

        const googleIdentityEmail = getProviderIdentityEmail(user, 'google', identities);
        const emailValue = document.getElementById('security-email-value');
        if (emailValue) {
            if (accountSecurityState.hasEmailPassword) emailValue.textContent = user.email;
            else if (accountSecurityState.hasGoogle && (googleIdentityEmail || user.email)) {
                const googleOnlyEmail = googleIdentityEmail || user.email;
                emailValue.textContent = securityText('google_email_only', `${googleOnlyEmail} · Google only`).replace('{email}', googleOnlyEmail);
            } else emailValue.textContent = securityText('email_not_connected_desc', 'Email/password sign-in is not connected.');
        }
        setMethodBadge('security-email-status', accountSecurityState.hasEmailPassword, !accountSecurityState.hasEmailPassword && user.email && accountSecurityState.hasGoogle ? securityText('google_only_badge', 'Google only') : '');
        const emailAction = document.getElementById('security-email-action');
        if (emailAction) emailAction.querySelector('span').textContent = accountSecurityState.hasEmailPassword ? securityText('change_btn', 'Change') : securityText('manage_btn', 'Manage');

        setMethodBadge('security-google-status', accountSecurityState.hasGoogle);
        const googleValue = document.getElementById('security-google-value');
        if (googleValue) {
            googleValue.textContent = accountSecurityState.hasGoogle
                ? (googleIdentityEmail
                    ? `${googleIdentityEmail} · Google`
                    : securityText('google_connected_desc', 'Google is connected to this CatRank account.'))
                : securityText('google_signin_desc', 'Use your Google account as another sign-in method.');
        }
        setSecurityHidden('connect-google', accountSecurityState.hasGoogle);
        setSecurityHidden('security-google-manage', !accountSecurityState.hasGoogle);
        setSecurityHidden('unlink-google-controls', !(accountSecurityState.hasGoogle && accountSecurityState.hasEmailPassword));
        const unlink = document.getElementById('disconnect-google');
        if (unlink) {
            unlink.classList.toggle('hidden', !(accountSecurityState.hasGoogle && accountSecurityState.hasEmailPassword));
            unlink.onclick = () => disconnectGoogle();
        }
        const googleNote = document.getElementById('google-password-note');
        if (googleNote) googleNote.textContent = securityText('disconnect_google_help', 'Disconnect Google only after email/password sign-in is working.');

        refreshSecurityAuxiliaryCards();
        refreshSecurityMethodActionButtons();
    } catch (error) {
        container.textContent = securityText('methods_load_error', 'Could not load sign-in methods. Reopen settings to retry.');
        console.warn('Account security load failed:', error);
    }
}

function defaultSecurityActionLabel(method) {
    if (method === 'email') {
        return accountSecurityState.hasEmailPassword
            ? securityText('change_btn', 'Change')
            : securityText('manage_btn', 'Manage');
    }
    return securityText('manage_btn', 'Manage');
}

function refreshSecurityMethodActionButtons() {
    const buttonIds = {
        email: 'security-email-action',
        google: 'security-google-manage'
    };
    for (const [method, id] of Object.entries(buttonIds)) {
        const button = document.getElementById(id);
        if (!button) continue;
        const panel = document.getElementById(`security-${method}-panel`);
        const isOpen = activeSecurityMethod === method && panel && !panel.classList.contains('hidden');
        const label = isOpen ? securityText('close_btn', 'Close') : defaultSecurityActionLabel(method);
        const labelNode = button.querySelector('span');
        if (labelNode) labelNode.textContent = label;
        else button.textContent = label;
        button.setAttribute('aria-expanded', String(Boolean(isOpen)));
        button.classList.toggle('bg-slate-100', Boolean(isOpen));
        button.classList.toggle('border-slate-300', Boolean(isOpen));
    }
}

function refreshSecurityAuxiliaryCards() {
    const managerOpen = Boolean(activeSecurityMethod);
    setSecurityHidden('password-security-card', managerOpen || !accountSecurityState.hasEmailPassword);
    setSecurityHidden('password-security-note', managerOpen || accountSecurityState.hasEmailPassword);
    setSecurityHidden('sessions-security-card', managerOpen);
}

function closeSecurityMethod(method) {
    setSecurityHidden(`security-${method}-panel`, true);
    if (!activeSecurityMethod || activeSecurityMethod === method) activeSecurityMethod = null;
    refreshSecurityAuxiliaryCards();
    refreshSecurityMethodActionButtons();
}

function toggleSecurityMethod(method) {
    if (!['email', 'google'].includes(method)) return;
    const panel = document.getElementById(`security-${method}-panel`);
    if (!panel) return;

    const isOpen = activeSecurityMethod === method && !panel.classList.contains('hidden');
    if (isOpen) {
        closeSecurityMethod(method);
        return;
    }

    // Open immediately so the control always feels responsive, even if
    // refreshing the Supabase identity data takes a moment or fails.
    for (const name of ['email', 'google']) {
        setSecurityHidden(`security-${name}-panel`, name !== method);
    }
    panel.classList.remove('hidden');
    activeSecurityMethod = method;
    refreshSecurityAuxiliaryCards();
    refreshSecurityMethodActionButtons();

    // Refresh/prepare the method asynchronously without blocking the UI.
    Promise.resolve(openSecurityMethod(method)).catch((error) => {
        console.warn('Could not prepare account security method:', error);
    });
}

async function openSecurityMethod(method) {
    if (!['email', 'google'].includes(method)) return;

    // Make the target panel visible first, before any network/session work.
    for (const name of ['email', 'google']) {
        setSecurityHidden(`security-${name}-panel`, name !== method);
    }
    activeSecurityMethod = method;
    refreshSecurityAuxiliaryCards();
    refreshSecurityMethodActionButtons();

    if (!accountSecurityState.user) await loadConnectedMethods();

    if (method === 'email') {
        const state = accountSecurityState;
        const help = document.getElementById('security-email-help');
        const save = document.getElementById('security-email-save');
        const inputWrap = document.getElementById('security-email-input-wrap');
        setSecurityHidden('security-email-password-auth', !state.hasEmailPassword);
        setSecurityHidden('security-email-google-only', state.hasEmailPassword || !state.hasGoogle);
        if (inputWrap) inputWrap.classList.toggle('hidden', !state.hasEmailPassword);
        if (help) {
            help.textContent = state.hasEmailPassword
                ? securityText('change_email_help', 'Changing your email requires your current password and email confirmation. Your old email stays active until confirmation finishes.')
                : securityText('add_email_google_help', 'Use password recovery to create email/password access for this Google account.');
        }
        if (save) {
            save.classList.toggle('hidden', !state.hasEmailPassword);
            save.textContent = securityText('change_email_btn', 'Update Email');
        }
    }

    refreshSecurityAuxiliaryCards();
    refreshSecurityMethodActionButtons();
}

async function reauthenticateCurrentPassword(password) {
    const state = accountSecurityState;
    const originalId = state.user?.id;
    const email = state.user?.email;
    if (!originalId || !email) throw new Error(securityText('reauth_unavailable', 'Password verification is not available for this account.'));
    const tokens = await authRequest('/api/auth/login', {email, password});
    const result = await supabaseClient.auth.setSession(tokens);
    if (result.error || !result.data?.session) throw result.error || new Error('Could not refresh your session.');
    if (String(result.data.session.user.id) !== String(originalId)) {
        await supabaseClient.auth.signOut({scope: 'local'});
        throw new Error('The verified account did not match your current account. Please sign in again.');
    }
    accountSecurityState.session = result.data.session;
    accountSecurityState.user = result.data.session.user;
    if (typeof currentSession !== 'undefined') currentSession = result.data.session;
    return result.data.session;
}


async function saveEmailSignInMethod() {
    const state = accountSecurityState;
    if (!state.user || !supabaseClient) return;
    if (!state.hasEmailPassword) {
        showToast(securityText('add_email_google_help', 'Use password recovery to create email/password access for this Google account.'), 'info');
        return;
    }
    const input = document.getElementById('security-email-input');
    const button = document.getElementById('security-email-save');
    const newEmail = String(input?.value || '').trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(newEmail) || newEmail.length > 254) {
        showToast(securityText('invalid_email_error', 'Enter a valid email address.'), 'error');
        input?.focus();
        return;
    }
    if (newEmail === String(state.user.email || '').toLowerCase()) {
        showToast(securityText('same_email_info', 'This is already your current email address.'), 'info');
        return;
    }
    if (button) button.disabled = true;
    try {
        const password = String(document.getElementById('security-email-current-password')?.value || '');
        if (!password) throw new Error(securityText('current_password_required', 'Enter your current password.'));
        const result = await authRequest('/api/user/security', {action: 'email', value: newEmail, current_password: password}, 'PUT', true);
        if (typeof showImportantAlert === 'function') showImportantAlert(result.message || securityText('email_change_sent', 'Check your email to confirm the change.'), 'success', {title: securityText('email_signin_title', 'Email & password')});
        if (input) input.value = '';
        const pass = document.getElementById('security-email-current-password');
        if (pass) pass.value = '';
        closeSecurityMethod('email');
    } catch (error) {
        if (typeof showImportantAlert === 'function') showImportantAlert(friendlySecurityAuthError(error, securityText('email_method_error', 'Could not update email sign-in.')), 'error', {title: securityText('security_title', 'Sign-in & security')});
    } finally {
        if (button) button.disabled = false;
    }
}

async function disconnectGoogle() {
    const field = document.getElementById('unlink-current-password');
    const password = field?.value || '';
    if (!accountSecurityState.hasEmailPassword) {
        showToast(securityText('google_disconnect_requires_email', 'Add a working email & password method before disconnecting Google.'), 'info');
        return;
    }
    if (!password) {
        showToast(securityText('password_to_disconnect_google', 'Enter your current password before disconnecting Google.'), 'info');
        field?.focus();
        return;
    }
    const button = document.getElementById('disconnect-google');
    if (button) button.disabled = true;
    try {
        await authRequest('/api/user/security', {action: 'unlink_google', current_password: password}, 'PUT', true);
        field.value = '';
        if (typeof showImportantAlert === 'function') showImportantAlert(securityText('google_disconnected_success', 'Google disconnected. Your email/password sign-in remains available.'), 'success', {title: 'Google'});
        closeSecurityMethod('google');
        await loadConnectedMethods();
    } catch (error) {
        if (typeof showImportantAlert === 'function') showImportantAlert(error.message, 'error', {title: 'Google'});
    } finally {
        if (button) button.disabled = false;
    }
}

async function signOutOtherSessions() {
    try {
        const {error} = await supabaseClient.auth.signOut({scope: 'others'});
        if (error) throw error;
        if (typeof showImportantAlert === 'function') showImportantAlert(securityText('other_sessions_signed_out', 'Other sessions signed out. Existing access tokens expire at their normal expiry time.'), 'success', {title: securityText('sessions_title', 'Other sessions')});
    } catch (error) { if (typeof showImportantAlert === 'function') showImportantAlert(error.message, 'error', {title: securityText('sessions_title', 'Other sessions')}); }
}

Object.assign(window, {
    loadConnectedMethods,
    openSecurityMethod,
    closeSecurityMethod,
    toggleSecurityMethod,
    saveEmailSignInMethod,
    disconnectGoogle,
    signOutOtherSessions,
    startGoogleSignIn
});

function bindAccountSecurityControls() {
    const handlers = {
        'security-email-action': () => toggleSecurityMethod('email'),
        'security-google-manage': () => toggleSecurityMethod('google'),
        'security-email-save': () => saveEmailSignInMethod(),
        'disconnect-google': () => disconnectGoogle(),
        'signout-other-sessions-btn': () => signOutOtherSessions()
    };
    for (const [id, handler] of Object.entries(handlers)) {
        const element = document.getElementById(id);
        if (!element) continue;
        element.onclick = null;
        element.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            handler();
        });
    }
}

// Event delegation is a second safety net. It keeps the controls working
// even if profile markup is rendered/replaced after DOMContentLoaded.
document.addEventListener('click', (event) => {
    const target = event.target instanceof Element ? event.target.closest('[data-security-toggle]') : null;
    if (!target) return;
    const method = target.getAttribute('data-security-toggle');
    if (!method) return;
    event.preventDefault();
    toggleSecurityMethod(method);
});

document.addEventListener('DOMContentLoaded', () => {
    bindAccountSecurityControls();
    completeGoogleSignIn();
});
window.addEventListener('catrank_language_changed', () => {
    if (document.getElementById('tab-content-security') && !document.getElementById('tab-content-security').classList.contains('hidden')) {
        loadConnectedMethods();
    }
});
