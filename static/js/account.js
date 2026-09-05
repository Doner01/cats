async function authRequest(path, payload, method = 'POST', authenticated = false) {
    const headers = {'Content-Type': 'application/json'};
    if (authenticated) {
        if (!supabaseClient) throw new Error('Authentication is unavailable.');
        const {data: {session}} = await supabaseClient.auth.getSession();
        if (!session) throw new Error('Please sign in again.');
        headers.Authorization = `Bearer ${session.access_token}`;
    }
    const res = await fetch(path, {method, headers, body: JSON.stringify(payload || {})});
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
        const authResult = await supabaseClient.auth.setSession({
            access_token: tokens.access_token,
            refresh_token: tokens.refresh_token
        });
        if (!authResult.error && authResult.data) {
            authResult.data.catrank = {google_release: tokens.google_release || null};
        }
        return authResult;
    } catch (error) {
        return {data: null, error};
    }
}

function safeLocalDestination(value, fallback = '/') {
    const raw = String(value || fallback);
    try {
        const url = new URL(raw, window.location.origin);
        const blocked = new Set(['/login', '/register', '/forgot-password', '/reset-password', '/auth/callback']);
        if (url.origin !== window.location.origin || !raw.startsWith('/') || raw.startsWith('//') || blocked.has(url.pathname)) {
            return fallback;
        }
        return `${url.pathname}${url.search}${url.hash}`;
    } catch (_) {
        return fallback;
    }
}

async function startGoogleSignIn() {
    const buttons = document.querySelectorAll('[data-google-button]');
    buttons.forEach(button => { button.disabled = true; });
    try {
        if (!supabaseClient) throw new Error('Google sign-in is unavailable.');

        // Google is deliberately only a normal sign-in / registration path.
        // There is no user-facing manual Connect/Disconnect flow. CatRank may
        // internally unlink a stale Google identity after an email change.
        const sessionResult = await supabaseClient.auth.getSession();
        if (sessionResult?.data?.session?.user) {
            throw new Error('You are already signed in. Sign out before choosing another account.');
        }

        const response = await fetch('/api/auth/options');
        const options = await response.json().catch(() => ({}));
        if (!response.ok || !options.google_enabled) {
            throw new Error(options.error || 'Google sign-in is not enabled yet.');
        }

        const intent = {
            mode: 'signin',
            next: typeof getLoginDestination === 'function' ? getLoginDestination() : '/',
            started: Date.now()
        };
        sessionStorage.setItem('catrank_oauth_intent', JSON.stringify(intent));

        const {error} = await supabaseClient.auth.signInWithOAuth({
            provider: 'google',
            options: {
                redirectTo: `${window.location.origin}/auth/callback`,
                queryParams: {prompt: 'select_account'}
            }
        });
        if (error) throw error;
    } catch (error) {
        try { sessionStorage.removeItem('catrank_oauth_intent'); } catch (_) {}
        if (typeof showToast === 'function') showToast(error?.message || 'Google sign-in failed.', 'error');
        buttons.forEach(button => { button.disabled = false; });
    }
}

function oauthIdentityEmail(identity) {
    if (!identity || typeof identity !== 'object') return '';
    const data = identity.identity_data && typeof identity.identity_data === 'object'
        ? identity.identity_data
        : {};
    return String(data.email || identity.email || '').trim().toLowerCase();
}

async function normalizeGoogleIdentitiesAfterOAuth(fallbackUser) {
    // CatRank allows exactly the Google identity whose verified email matches
    // auth.users.email. Old Google identities are removed as soon as Supabase
    // gives us a safe alternate identity to keep.
    let user = fallbackUser || null;
    try {
        const fresh = await supabaseClient.auth.getUser();
        if (!fresh.error && fresh.data?.user) user = fresh.data.user;
    } catch (_) {}

    const primaryEmail = String(user?.email || '').trim().toLowerCase();
    if (!primaryEmail) throw new Error('Google did not return a usable account email.');

    const identityResult = await supabaseClient.auth.getUserIdentities();
    if (identityResult.error) throw identityResult.error;

    let identities = Array.isArray(identityResult.data?.identities)
        ? [...identityResult.data.identities]
        : [];
    const googleIdentities = identities.filter(
        identity => String(identity?.provider || '').toLowerCase() === 'google'
    );
    const matchingGoogle = googleIdentities.filter(
        identity => oauthIdentityEmail(identity) === primaryEmail
    );
    const staleGoogle = googleIdentities.filter(
        identity => oauthIdentityEmail(identity) !== primaryEmail
    );

    // If the Google account used for this OAuth login does not match the
    // current CatRank email, remove stale Google identities only when another
    // identity can safely remain, then reject the login.
    if (!matchingGoogle.length) {
        for (const identity of staleGoogle) {
            if (identities.length <= 1) break;
            const {error} = await supabaseClient.auth.unlinkIdentity(identity);
            if (!error) identities = identities.filter(item => item?.id !== identity?.id);
        }
        const mismatch = new Error(
            `This Google account does not match your CatRank email (${primaryEmail}). ` +
            `Use Google with ${primaryEmail}, or use email/password.`
        );
        mismatch.code = 'google_email_mismatch';
        throw mismatch;
    }

    // A matching Google account is now available. Remove every old Google
    // identity so changing the CatRank email does not leave two Google
    // accounts entering the same CatRank user.
    for (const identity of staleGoogle) {
        if (identities.length <= 1) {
            const error = new Error('CatRank could not safely remove the old Google sign-in.');
            error.code = 'google_cleanup_failed';
            throw error;
        }
        const {error} = await supabaseClient.auth.unlinkIdentity(identity);
        if (error) {
            const cleanupError = new Error(
                'Google sign-in matched your CatRank email, but the old Google identity could not be released. ' +
                'Enable Supabase manual identity linking/unlinking and try again.'
            );
            cleanupError.code = 'google_cleanup_failed';
            throw cleanupError;
        }
        identities = identities.filter(item => item?.id !== identity?.id);
    }

    return user;
}

async function completeGoogleSignIn() {
    const status = document.getElementById('oauth-status');
    if (!status) return;

    let sessionEstablished = false;
    try {
        const params = new URLSearchParams(window.location.search);
        const hashParams = new URLSearchParams(String(window.location.hash || '').replace(/^#/, ''));
        const code = String(params.get('code') || '').trim();
        const providerError = params.get('error') || hashParams.get('error');
        const intent = JSON.parse(sessionStorage.getItem('catrank_oauth_intent') || 'null');

        // Remove the OAuth code from browser history immediately.
        history.replaceState(null, '', '/auth/callback');

        if (providerError) throw new Error('Google sign-in was cancelled or could not be completed.');
        if (!code || !intent || intent.mode !== 'signin' || !Number(intent.started)) {
            throw new Error('This Google sign-in attempt is invalid. Please start again.');
        }
        if (Date.now() - Number(intent.started) > 10 * 60 * 1000) {
            throw new Error('This Google sign-in attempt has expired. Please start again.');
        }

        const {data, error} = await supabaseClient.auth.exchangeCodeForSession(code);
        if (error || !data?.session?.user) {
            throw error || new Error('Could not verify this Google sign-in. Please start again in the same browser.');
        }
        sessionEstablished = true;

        // Normalize provider identities before CatRank accepts the OAuth login.
        // This guarantees that only the Google identity matching the current
        // CatRank email remains connected once a safe replacement exists.
        await normalizeGoogleIdentitiesAfterOAuth(data.session.user);

        // Profile creation is idempotent and keyed only by the verified
        // Supabase user id. OAuth never chooses or rewrites another user's id.
        await authRequest('/api/auth/bootstrap', {}, 'POST', true);

        sessionStorage.removeItem('catrank_oauth_intent');
        const destination = safeLocalDestination(intent.next, '/');
        window.location.replace(destination);
    } catch (error) {
        try { sessionStorage.removeItem('catrank_oauth_intent'); } catch (_) {}
        // Do not leave a half-initialized authenticated browser behind if
        // Supabase OAuth succeeded but CatRank profile bootstrap failed.
        if (sessionEstablished) {
            try { await supabaseClient.auth.signOut({scope: 'local'}); } catch (_) {}
        }
        status.textContent = error?.message || 'Google sign-in could not be completed.';
        document.getElementById('oauth-back')?.classList.remove('hidden');
    }
}

const accountSecurityState = {
    session: null,
    user: null,
    identities: [],
    hasEmailPassword: false,
    hasGoogle: false,
    hasAnyGoogleIdentity: false
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

function setMethodBadge(id, connected, alternateText = '') {
    const element = document.getElementById(id);
    if (!element) return;
    const label = alternateText || (connected ? securityText('connected_badge', 'Available') : securityText('not_connected_badge', 'Not used'));
    element.textContent = label;
    element.className = connected
        ? 'text-[10px] font-black rounded-full px-2 py-0.5 bg-emerald-50 text-emerald-700'
        : 'text-[10px] font-black rounded-full px-2 py-0.5 bg-slate-100 text-slate-500';
}

function friendlySecurityAuthError(error, fallback) {
    const code = String(error?.code || '').toLowerCase();
    const message = String(error?.message || '');
    if (code === 'google_email_mismatch') {
        return 'This Google sign-in no longer matches your CatRank email. Use your CatRank email/password, or choose Google with the same email as your CatRank account.';
    }
    if (['user_already_exists', 'email_exists', 'identity_already_exists'].includes(code) || /already.*(registered|exists|used)/i.test(message)) {
        return securityText('signin_method_in_use', 'That email is already used by another account.');
    }
    return message || fallback;
}

function providerSetForUser(user, identities) {
    const providers = new Set();
    for (const identity of identities || []) {
        if (identity?.provider) providers.add(String(identity.provider).toLowerCase());
    }
    const appMeta = user?.app_metadata || {};
    const listed = Array.isArray(appMeta.providers) ? appMeta.providers : [];
    for (const provider of listed) providers.add(String(provider).toLowerCase());
    if (appMeta.provider) providers.add(String(appMeta.provider).toLowerCase());
    return providers;
}

function hasPasswordSignInForUser(user, providers) {
    if (!user?.email && !user?.phone) return false;
    if (providers?.has?.('email')) return true;
    if (providers?.has?.('phone') && user?.app_metadata?.catrank_password_enabled === true) return true;
    if (user?.app_metadata?.catrank_password_enabled === true) return true;
    // Compatibility for accounts created by older CatRank builds. This value
    // is only a UX hint; sensitive actions still verify the real password.
    return user?.user_metadata?.catrank_password_enabled === true;
}

function getProviderIdentityEmail(user, provider, identities = null) {
    const wanted = String(provider || '').toLowerCase();
    const list = Array.isArray(identities)
        ? identities
        : (Array.isArray(user?.identities) ? user.identities : []);

    for (const identity of list) {
        if (!identity || String(identity.provider || '').toLowerCase() !== wanted) continue;
        const data = identity.identity_data && typeof identity.identity_data === 'object' ? identity.identity_data : {};
        const email = String(data.email || identity.email || '').trim().toLowerCase();
        if (email) return email;
    }
    return '';
}

function getProviderIdentityEmails(user, provider, identities = null) {
    const wanted = String(provider || '').toLowerCase();
    const list = Array.isArray(identities)
        ? identities
        : (Array.isArray(user?.identities) ? user.identities : []);
    const emails = [];
    for (const identity of list) {
        if (!identity || String(identity.provider || '').toLowerCase() !== wanted) continue;
        const data = identity.identity_data && typeof identity.identity_data === 'object' ? identity.identity_data : {};
        const email = String(data.email || identity.email || '').trim().toLowerCase();
        if (email && !emails.includes(email)) emails.push(email);
    }
    return emails;
}

function getMatchingGoogleEmail(user, identities = null) {
    const primaryEmail = String(user?.email || '').trim().toLowerCase();
    if (!primaryEmail) return '';
    return getProviderIdentityEmails(user, 'google', identities).find(email => email === primaryEmail) || '';
}

function getProfileEmailForUser(user, identities = null) {
    if (!user) return '';
    const primaryEmail = String(user.email || '').trim().toLowerCase();
    const list = Array.isArray(identities)
        ? identities
        : (Array.isArray(user.identities) ? user.identities : []);
    const providers = providerSetForUser(user, list);
    const googleEmail = getProviderIdentityEmail(user, 'google', list);
    const hasPassword = hasPasswordSignInForUser(user, providers);

    // Once password sign-in exists, auth.users.email is the CatRank account
    // email and is the value users expect to see after changing email.
    // A Google identity keeps its own provider email and remains a separate
    // sign-in route to the same Supabase user; it must not replace the account
    // email in the profile UI just because this user originally joined Google.
    if (hasPassword && primaryEmail) return primaryEmail;

    // Google-only accounts naturally show the Google identity email.
    return googleEmail || primaryEmail;
}

async function refreshAccountSecuritySession() {
    if (!supabaseClient) throw new Error('Authentication is unavailable.');
    const sessionResult = await supabaseClient.auth.getSession();
    const session = sessionResult?.data?.session || null;
    if (!session) throw new Error('Please sign in again.');

    let user = session.user;
    try {
        const current = await supabaseClient.auth.getUser();
        if (!current.error && current.data?.user) user = current.data.user;
    } catch (_) {}

    // getSession() may contain a cached user object after an email change.
    // Keep the access/refresh tokens, but replace the embedded user with the
    // authoritative getUser() result so the rest of the UI sees the new email.
    const freshSession = user === session.user ? session : {...session, user};
    if (typeof currentSession !== 'undefined' && currentSession?.user?.id !== session.user.id) {
        throw new Error('Your session changed. Please reopen account settings.');
    }
    accountSecurityState.session = freshSession;
    accountSecurityState.user = user;
    if (typeof setCurrentSession === 'function') setCurrentSession(freshSession);
    return {session: freshSession, user};
}

async function loadConnectedMethods() {
    const container = document.getElementById('connected-methods');
    if (!container || !supabaseClient) return;

    try {
        const {user} = await refreshAccountSecuritySession();
        let identities = Array.isArray(user.identities) ? user.identities : [];
        try {
            const result = await supabaseClient.auth.getUserIdentities();
            if (!result.error && Array.isArray(result.data?.identities)) identities = result.data.identities;
        } catch (_) {}

        accountSecurityState.identities = identities;
        const providers = providerSetForUser(user, identities);
        accountSecurityState.hasEmailPassword = hasPasswordSignInForUser(user, providers);
        const googleEmails = getProviderIdentityEmails(user, 'google', identities);
        const matchingGoogleEmail = getMatchingGoogleEmail(user, identities);
        accountSecurityState.hasAnyGoogleIdentity = googleEmails.length > 0;
        accountSecurityState.hasGoogle = Boolean(matchingGoogleEmail);

        const methods = [];
        if (accountSecurityState.hasEmailPassword) methods.push('Email/password');
        if (accountSecurityState.hasGoogle) methods.push('Google');
        if (providers.has('phone')) methods.push('Phone');
        container.textContent = methods.join(' · ') || securityText('no_methods_found', 'No sign-in methods found');

        const googleEmail = matchingGoogleEmail || getProviderIdentityEmail(user, 'google', identities);
        const emailValue = document.getElementById('security-email-value');
        if (emailValue) {
            if (accountSecurityState.hasEmailPassword) {
                emailValue.textContent = user.email || user.phone || 'Password sign-in';
            } else if (accountSecurityState.hasGoogle && (googleEmail || user.email)) {
                emailValue.textContent = `${googleEmail || user.email} · no CatRank password`;
            } else {
                emailValue.textContent = 'No password sign-in is configured.';
            }
        }
        setMethodBadge(
            'security-email-status',
            accountSecurityState.hasEmailPassword,
            !accountSecurityState.hasEmailPassword && accountSecurityState.hasGoogle ? 'Google only' : ''
        );

        const emailAction = document.getElementById('security-email-action');
        if (emailAction) {
            const label = emailAction.querySelector('span');
            if (label) label.textContent = accountSecurityState.hasEmailPassword ? 'Manage' : 'Add password';
        }

        const primaryEmail = String(user.email || '').trim().toLowerCase();
        const googleValue = document.getElementById('security-google-value');
        const googleNote = document.getElementById('security-google-note');
        if (googleValue) {
            if (accountSecurityState.hasGoogle) {
                googleValue.textContent = `${matchingGoogleEmail} · Google sign-in`;
            } else if (accountSecurityState.hasAnyGoogleIdentity && primaryEmail) {
                googleValue.textContent = 'Old Google sign-in is waiting to be released.';
            } else {
                googleValue.textContent = 'This account does not currently use Google sign-in.';
            }
        }
        if (googleNote) {
            if (accountSecurityState.hasGoogle) {
                googleNote.textContent = 'Google can sign in because its verified email matches your current CatRank email.';
            } else if (accountSecurityState.hasAnyGoogleIdentity && primaryEmail) {
                googleNote.textContent = `The old Google email no longer signs in here. After you sign in with ${primaryEmail} + password, CatRank permanently releases that old Google identity so it can be used for a separate account.`;
            } else if (primaryEmail) {
                googleNote.textContent = `To use Google, sign out and choose Continue with Google using ${primaryEmail}.`;
            } else {
                googleNote.textContent = 'Google is available only when its verified email matches the current CatRank email.';
            }
        }
        setMethodBadge(
            'security-google-status',
            accountSecurityState.hasGoogle,
            accountSecurityState.hasGoogle ? '' : (accountSecurityState.hasAnyGoogleIdentity ? 'Release pending' : '')
        );

        refreshSecurityAuxiliaryCards();
        refreshSecurityMethodActionButtons();
    } catch (error) {
        container.textContent = securityText('methods_load_error', 'Could not load sign-in methods. Reopen settings to retry.');
        console.warn('Account security load failed:', error);
    }
}

function refreshSecurityMethodActionButtons() {
    const button = document.getElementById('security-email-action');
    if (!button) return;
    const panel = document.getElementById('security-email-panel');
    const isOpen = activeSecurityMethod === 'email' && panel && !panel.classList.contains('hidden');
    const label = button.querySelector('span');
    if (label) {
        label.textContent = isOpen
            ? securityText('close_btn', 'Close')
            : (accountSecurityState.hasEmailPassword ? securityText('manage_btn', 'Manage') : 'Add password');
    }
    button.setAttribute('aria-expanded', String(Boolean(isOpen)));
    button.classList.toggle('bg-slate-100', Boolean(isOpen));
    button.classList.toggle('border-slate-300', Boolean(isOpen));
}

function refreshSecurityAuxiliaryCards() {
    const managerOpen = activeSecurityMethod === 'email';
    setSecurityHidden('password-security-card', managerOpen || !accountSecurityState.hasEmailPassword);
    setSecurityHidden('password-security-note', managerOpen || accountSecurityState.hasEmailPassword);
    setSecurityHidden('sessions-security-card', managerOpen);
}

function closeSecurityMethod(method) {
    if (method !== 'email') return;
    setSecurityHidden('security-email-panel', true);
    if (activeSecurityMethod === 'email') activeSecurityMethod = null;
    refreshSecurityAuxiliaryCards();
    refreshSecurityMethodActionButtons();
}

function toggleSecurityMethod(method) {
    if (method !== 'email') return;

    if (!accountSecurityState.hasEmailPassword) {
        window.location.href = '/set-password';
        return;
    }

    const panel = document.getElementById('security-email-panel');
    if (!panel) return;
    const isOpen = activeSecurityMethod === 'email' && !panel.classList.contains('hidden');
    if (isOpen) {
        closeSecurityMethod('email');
        return;
    }
    panel.classList.remove('hidden');
    activeSecurityMethod = 'email';
    refreshSecurityAuxiliaryCards();
    refreshSecurityMethodActionButtons();
    Promise.resolve(openSecurityMethod('email')).catch(error => console.warn('Could not prepare account security:', error));
}

async function openSecurityMethod(method) {
    if (method !== 'email') return;
    if (!accountSecurityState.user) await loadConnectedMethods();
    if (!accountSecurityState.hasEmailPassword) {
        window.location.href = '/set-password';
        return;
    }

    setSecurityHidden('security-email-password-auth', false);
    setSecurityHidden('security-email-google-only', true);
    const inputWrap = document.getElementById('security-email-input-wrap');
    if (inputWrap) inputWrap.classList.remove('hidden');
    const help = document.getElementById('security-email-help');
    if (help) {
        help.textContent = 'Changing your sign-in email requires your current password and Supabase email confirmation. When the new email becomes active, Google sign-in with a different email is reset for CatRank.';
    }
    const save = document.getElementById('security-email-save');
    if (save) {
        save.classList.remove('hidden');
        save.textContent = securityText('change_email_btn', 'Update Email');
    }
}

async function saveEmailSignInMethod() {
    const state = accountSecurityState;
    if (!state.user || !supabaseClient) return;
    if (!state.hasEmailPassword) {
        window.location.href = '/set-password';
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
        const passwordField = document.getElementById('security-email-current-password');
        const password = String(passwordField?.value || '');
        if (!password) throw new Error(securityText('current_password_required', 'Enter your current password.'));

        const result = await authRequest(
            '/api/user/security',
            {action: 'email', value: newEmail, current_password: password},
            'PUT',
            true
        );
        if (typeof showImportantAlert === 'function') {
            showImportantAlert(
                result.message || 'Check your inboxes to confirm the email change.',
                'success',
                {title: 'Email & password'}
            );
        }
        if (input) input.value = '';
        if (passwordField) passwordField.value = '';
        closeSecurityMethod('email');
    } catch (error) {
        const message = friendlySecurityAuthError(error, 'Could not update your sign-in email.');
        if (typeof showImportantAlert === 'function') showImportantAlert(message, 'error', {title: 'Sign-in & security'});
        else showToast(message, 'error');
    } finally {
        if (button) button.disabled = false;
    }
}

async function refreshAfterEmailConfirmation() {
    if (!supabaseClient || window.location.pathname !== '/profile') return;
    const params = new URLSearchParams(window.location.search);
    if (params.get('email_confirmed') !== '1') return;

    try {
        // Email-change links can return with a session whose embedded user is
        // stale. Refresh it, then sync the confirmed auth email into profiles.
        await supabaseClient.auth.refreshSession();
        const {user} = await refreshAccountSecuritySession();
        await authRequest('/api/auth/bootstrap', {}, 'POST', true);

        const currentEmail = String(user?.email || '').trim().toLowerCase();
        if (typeof showImportantAlert === 'function') {
            showImportantAlert(
                currentEmail
                    ? `Email confirmation processed. Current CatRank email: ${currentEmail}. If it has not changed yet, confirm the other inbox too. Google sign-in now works only with a Google account using this same email.`
                    : 'Email confirmation processed. If your project requires both inboxes, complete both confirmation links. Google sign-in works only when its email matches your current CatRank email.',
                'success',
                {title: 'Email confirmation'}
            );
        }
    } catch (error) {
        console.warn('Could not refresh confirmed email state:', error);
    } finally {
        params.delete('email_confirmed');
        const query = params.toString();
        history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash || ''}`);
    }
}

async function signOutOtherSessions() {
    try {
        const {error} = await supabaseClient.auth.signOut({scope: 'others'});
        if (error) throw error;
        if (typeof showImportantAlert === 'function') {
            showImportantAlert(
                securityText('other_sessions_signed_out', 'Other sessions signed out. Existing access tokens expire at their normal expiry time.'),
                'success',
                {title: securityText('sessions_title', 'Other sessions')}
            );
        }
    } catch (error) {
        if (typeof showImportantAlert === 'function') showImportantAlert(error.message, 'error', {title: securityText('sessions_title', 'Other sessions')});
        else showToast(error.message, 'error');
    }
}

Object.assign(window, {
    loadConnectedMethods,
    openSecurityMethod,
    closeSecurityMethod,
    toggleSecurityMethod,
    saveEmailSignInMethod,
    signOutOtherSessions,
    startGoogleSignIn,
    completeGoogleSignIn,
    providerSetForUser,
    hasPasswordSignInForUser,
    getProviderIdentityEmail,
    getProfileEmailForUser,
    refreshAfterEmailConfirmation
});

function bindAccountSecurityControls() {
    const handlers = {
        'security-email-action': () => toggleSecurityMethod('email'),
        'security-email-save': () => saveEmailSignInMethod(),
        'signout-other-sessions-btn': () => signOutOtherSessions()
    };
    for (const [id, handler] of Object.entries(handlers)) {
        const element = document.getElementById(id);
        if (!element) continue;
        element.onclick = null;
        element.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            handler();
        });
    }
}

document.addEventListener('click', event => {
    const target = event.target instanceof Element ? event.target.closest('[data-security-toggle="email"]') : null;
    if (!target) return;
    event.preventDefault();
    toggleSecurityMethod('email');
});

document.addEventListener('DOMContentLoaded', () => {
    bindAccountSecurityControls();
    completeGoogleSignIn();
    refreshAfterEmailConfirmation();
});

window.addEventListener('catrank_language_changed', () => {
    const security = document.getElementById('tab-content-security');
    if (security && !security.classList.contains('hidden')) loadConnectedMethods();
});
