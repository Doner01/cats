async function authRequest(path, payload, method = 'POST', authenticated = false) {
    const headers = {'Content-Type': 'application/json'};
    if (authenticated) {
        const {data: {session}} = await supabaseClient.auth.getSession();
        if (!session) throw new Error('Please sign in again.');
        headers.Authorization = `Bearer ${session.access_token}`;
    }
    const res = await fetch(path, {method, headers, body: JSON.stringify(payload)});
    const data = await res.json();
    if (!res.ok) {
        const error = new Error(data.error || 'This request could not be completed.');
        error.code = data.code || '';
        error.status = res.status;
        throw error;
    }
    return data;
}

function accountText(key, fallback) {
    if (typeof t === 'function') {
        const translated = t(key);
        if (translated && translated !== key) return translated;
    }
    return fallback;
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

async function loadConnectedMethods() {
    const container = document.getElementById('connected-methods');
    if (!container || !supabaseClient) return;
    try {
        const {data, error} = await supabaseClient.auth.getUserIdentities();
        if (error) throw error;
        const identities = data.identities || [];
        const google = identities.find(i => i.provider === 'google');
        const email = identities.some(i => i.provider === 'email');
        container.textContent = identities.map(i => {
            if (i.provider === 'google') return 'Google';
            if (i.provider === 'email') return accountText('email_method', 'Email');
            if (i.provider === 'phone') return accountText('phone_method', 'Phone');
            return i.provider;
        }).join(' · ') || accountText('no_connected_methods', 'No sign-in methods found');
        document.getElementById('connect-google')?.classList.toggle('hidden', Boolean(google));
        document.getElementById('unlink-google-controls')?.classList.toggle('hidden', !google || !email);
        const unlink = document.getElementById('disconnect-google');
        if (unlink) {
            unlink.classList.toggle('hidden', !google || !email);
            unlink.onclick = () => disconnectGoogle();
        }
        document.getElementById('google-password-note')?.classList.toggle('hidden', !google || email);
    } catch (_) { container.textContent = accountText('connected_methods_error', 'Could not load sign-in methods. Reopen settings to retry.'); }
}

async function disconnectGoogle() {
    const field = document.getElementById('unlink-current-password');
    const password = field?.value || '';
    if (!password) { showToast(accountText('disconnect_google_password_required', 'Enter your current password before removing Google.'), 'info'); field?.focus(); return; }
    const button = document.getElementById('disconnect-google');
    button.disabled = true;
    try {
        await authRequest('/api/user/security', {action: 'unlink_google', current_password: password}, 'PUT', true);
        field.value = '';
        showToast(accountText('google_disconnected', 'Google sign-in removed. Your password sign-in remains available.'), 'success');
        await loadConnectedMethods();
    } catch (error) { showToast(error.message, 'error'); }
    finally { button.disabled = false; }
}

async function signOutOtherSessions() {
    try {
        const {error} = await supabaseClient.auth.signOut({scope: 'others'});
        if (error) throw error;
        showToast(accountText('other_sessions_signed_out', 'Other sessions will not be renewed. They may stay active briefly.'), 'success');
    } catch (error) { showToast(error.message, 'error'); }
}

document.addEventListener('DOMContentLoaded', completeGoogleSignIn);
