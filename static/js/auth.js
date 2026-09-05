let currentSession = null;
let authCheckVersion = 0;

function setCurrentSession(session) {
    const previousAccountId = currentSession?.user?.id;
    const accountChanged = currentSession?.user?.id !== session?.user?.id;
    currentSession = session;
    if (accountChanged) {
        if (typeof resetFavorites === 'function') resetFavorites();
        if (typeof resetPrivateViewerState === 'function') resetPrivateViewerState();
        const path = window.location.pathname;
        if (previousAccountId && (['/profile', '/admin', '/upload'].includes(path) || path.startsWith('/user/'))) {
            // These pages hold contact details, moderation data or forms in
            // the DOM. Rebuild them for the new account, including cross-tab logout.
            if (document.body) document.body.style.visibility = 'hidden';
            window.location.reload();
        }
    }
    return accountChanged;
}

function getLoginDestination() {
    const next = new URLSearchParams(window.location.search).get('next') || '/';
    try {
        const url = new URL(next, window.location.origin);
        if (url.origin !== window.location.origin || !next.startsWith('/') || next.startsWith('//')) return '/';
        if (['/login', '/register', '/forgot-password', '/reset-password', '/auth/callback'].includes(url.pathname)) return '/';
        return url.pathname + url.search + url.hash;
    } catch (_) { return '/'; }
}
let pendingAvatarUpload = false;

function escapeHtmlText(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function safeImageUrl(value, fallbackName = 'Cat') {
    const url = String(value || '').trim();
    try {
        const parsed = new URL(url);
        if (parsed.protocol === 'https:' && !parsed.username && !parsed.password) return parsed.href;
    } catch (_) {}
    return getFallbackAvatarSvg(fallbackName);
}

function dataUrlToBlob(dataUrl) {
    const [meta, base64] = dataUrl.split(',');
    const mime = (meta.match(/data:([^;]+)/) || [])[1] || 'image/webp';
    const bytes = atob(base64 || '');
    const arr = new Uint8Array(bytes.length);
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
    return new Blob([arr], { type: mime });
}

async function uploadPendingRegistrationAvatar(session) {
    if (!session || !session.access_token || !session.user || !session.user.email) return;
    if (pendingAvatarUpload) return;
    pendingAvatarUpload = true;
    try {
        const raw = localStorage.getItem('catrank_pending_avatar');
        if (!raw) return;
        const pending = JSON.parse(raw);
        if (!pending || String(pending.email || '').toLowerCase() !== String(session.user.email).toLowerCase() || !pending.dataUrl) return;
        if (pending.createdAt && Date.now() - Number(pending.createdAt) > 24 * 60 * 60 * 1000) {
            localStorage.removeItem('catrank_pending_avatar');
            return;
        }

        const blob = dataUrlToBlob(pending.dataUrl);
        const form = new FormData();
        form.append('avatar', blob, 'avatar.webp');
        const res = await fetch('/api/user/avatar', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${session.access_token}` },
            body: form
        });
        if (res.ok) localStorage.removeItem('catrank_pending_avatar');
    } catch (err) {
        console.warn('Pending avatar upload skipped:', err);
    } finally {
        pendingAvatarUpload = false;
    }
}

function getFallbackAvatarSvg(name) {
    const initial = (name || 'C').trim().charAt(0).toUpperCase() || 'C';
    const colors = ['#6366f1', '#ec4899', '#8b5cf6', '#3b82f6', '#10b981', '#f59e0b', '#06b6d4'];
    let hash = 0;
    for (let i = 0; i < (name || '').length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    const color = colors[Math.abs(hash) % colors.length];
    return `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"><rect width="64" height="64" rx="32" fill="${encodeURIComponent(color)}"/><text x="50%" y="54%" text-anchor="middle" dominant-baseline="middle" fill="%23ffffff" font-family="system-ui, -apple-system, sans-serif" font-size="26" font-weight="bold">${encodeURIComponent(initial)}</text></svg>`;
}

function handleAvatarError(imgElem, name = "Cat") {
    if (!imgElem) return;
    imgElem.onerror = null;
    imgElem.src = getFallbackAvatarSvg(name);
}

function getAvatarUrl(user) {
    const meta = user && user.user_metadata && typeof user.user_metadata === 'object'
        ? user.user_metadata
        : {};
    const providerAvatar = meta.avatar_url || meta.picture || '';
    if (providerAvatar) return providerAvatar;

    const name = meta.display_name
        || meta.full_name
        || meta.name
        || ((user && user.email) ? user.email.split('@')[0] : 'Cat');
    return `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(name)}&backgroundColor=b6e3f4,c0aede,d1d4f9`;
}

function getUserDisplayName(user) {
    if (user && user.user_metadata && user.user_metadata.display_name) {
        return user.user_metadata.display_name;
    }
    return (user && user.email) ? user.email.split('@')[0] : 'Cat Lover';
}

async function checkAuth() {
    if (window.location.pathname === "/auth/callback") return;
    if (typeof supabaseClient === "undefined" || !supabaseClient) return;
    const version = ++authCheckVersion;
    try {
        const { data: { session } } = await supabaseClient.auth.getSession();
        if (version !== authCheckVersion) return;
        const accountChanged = setCurrentSession(session);
        if (accountChanged) window.dispatchEvent(new CustomEvent('catrank_auth_changed'));
        if (typeof updateModalAuth === 'function') updateModalAuth();
        if (typeof syncUserFavorites === 'function' && session) syncUserFavorites(session);
        const authSection = document.getElementById("auth-section");
        if (!authSection) return;
        
        if (session && session.user) {
            await uploadPendingRegistrationAvatar(session);
            if (version !== authCheckVersion || session.user.id !== currentSession?.user?.id) return;
            const path = window.location.pathname;
            if (path === "/login" || path === "/register") {
                window.location.replace(getLoginDestination());
                return;
            }
            const displayName = getUserDisplayName(session.user);
            const avatarUrl = getAvatarUrl(session.user);
            const profileText = typeof t === "function" ? t("nav_profile") : "Profile";
            const signOutText = typeof t === "function" ? t("nav_signout") : "Sign Out";
            
            const safeDisplayName = escapeHtmlText(displayName);
            const safeAvatarUrl = escapeHtmlText(safeImageUrl(avatarUrl, displayName));
            authSection.innerHTML = `
                <div class="flex items-center gap-1.5">
                    <a href="/profile" class="flex items-center gap-2 px-2.5 py-1.5 bg-slate-100/90 hover:bg-slate-200/90 rounded-xl transition group shadow-2xs">
                        <img data-auth-avatar src="${safeAvatarUrl}" alt="Avatar" class="w-6 h-6 rounded-full bg-white border border-slate-200 object-cover">
                        <span class="text-xs font-bold text-slate-800 max-w-[100px] truncate hidden sm:inline">${safeDisplayName}</span>
                    </a>
                    <button onclick="handleLogout()" class="px-3 py-1.5 text-xs font-bold text-rose-600 bg-rose-50 hover:bg-rose-100 rounded-xl transition flex items-center gap-1 shadow-2xs" title="${escapeHtmlText(signOutText)}">
                        <i class="fa-solid fa-right-from-bracket text-xs"></i>
                        <span class="hidden sm:inline">${escapeHtmlText(signOutText)}</span>
                    </button>
                </div>
            `;
            const authAvatar = authSection.querySelector('[data-auth-avatar]');
            if (authAvatar) authAvatar.addEventListener('error', () => handleAvatarError(authAvatar, displayName), { once: true });

            if (typeof syncUserLikes === "function") {
                syncUserLikes();
            }
            if (typeof fetchNotifications === "function") {
                fetchNotifications();
            }
        } else {
            const signInText = typeof t === "function" ? t("nav_signin") : "Sign In";
            const signUpText = typeof t === "function" ? t("nav_signup") : "Sign Up";
            
            authSection.innerHTML = `
                <a href="/login" class="px-3 py-1.5 text-xs font-bold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-xl transition flex items-center gap-1.5">
                    <i class="fa-solid fa-right-to-bracket text-xs text-slate-500"></i>
                    <span>${signInText}</span>
                </a>
                <a href="/register" class="hidden sm:inline-flex px-3.5 py-1.5 text-xs font-bold text-indigo-600 bg-indigo-50 hover:bg-indigo-100 rounded-xl transition items-center gap-1.5">
                    <i class="fa-solid fa-user-plus text-xs text-indigo-500"></i>
                    <span>${signUpText}</span>
                </a>
            `;
        }
    } catch (err) {
        console.error("Auth status check error:", err);
    }
}

async function handleLogin() {
    if (typeof supabaseClient === "undefined" || !supabaseClient) {
        showToast("Supabase client is not initialized.", "error");
        return;
    }
    const emailElem = document.getElementById("email");
    const passElem = document.getElementById("password");
    const btn = document.getElementById("login-btn");
    
    if (!emailElem || !passElem) return;
    const email = emailElem.value.trim();
    const password = passElem.value;

    if (!email || !password) {
        showToast("Please provide both email and password.", "error");
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-xs"></i> <span>Signing in...</span>`;
    }

    try {
        const { data, error } = await signInWithPasswordThroughApp(email, password);
        if (error) {
            showToast(error.message, "error");
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<i class="fa-solid fa-right-to-bracket text-xs"></i> <span>${typeof t === "function" ? t("signin_submit_btn") : "Sign In"}</span>`;
            }
        } else {
            if (data && data.session) await uploadPendingRegistrationAvatar(data.session);
            const release = data?.catrank?.google_release || null;
            if (release?.status === 'released') {
                showToast('Signed in. Your old Google sign-in was released and can now be used for a separate CatRank account.', 'success');
            } else if (release?.status === 'pending') {
                showToast('Signed in. Your old Google sign-in is still reserved and CatRank will retry releasing it on your next password sign-in.', 'warning');
            } else {
                showToast(typeof t === "function" ? t("toast_signin_success") : "Welcome back! Redirecting...", "success");
            }
            window.location.href = getLoginDestination();
        }
    } catch (err) {
        showToast("Connection error: " + err.message, "error");
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-right-to-bracket text-xs"></i> <span>${typeof t === "function" ? t("signin_submit_btn") : "Sign In"}</span>`;
        }
    }
}

async function handleSignUp() {
    if (typeof supabaseClient === "undefined" || !supabaseClient) {
        showToast("Supabase client is not initialized.", "error");
        return;
    }
    const nameElem = document.getElementById("reg-display-name");
    const emailElem = document.getElementById("reg-email");
    const passElem = document.getElementById("reg-password");
    const confirmElem = document.getElementById("reg-confirm-password");
    const btn = document.getElementById("register-btn");

    if (!emailElem || !passElem) return;
    const displayName = (nameElem ? nameElem.value.trim() : "") || emailElem.value.split('@')[0];
    const email = emailElem.value.trim().toLowerCase();
    const password = passElem.value;
    const confirmPassword = confirmElem ? confirmElem.value : password;

    if (!email || !password) {
        showToast(typeof t === "function" && currentLang === "ru" ? "Пожалуйста, заполните все обязательные поля." : "Please provide all required fields.", "error");
        return;
    }

    if (password !== confirmPassword) {
        showToast(typeof t === "function" && currentLang === "ru" ? "Пароли не совпадают." : "Passwords do not match.", "error");
        return;
    }

    if (password.length < 8) {
        showToast(typeof t === "function" && currentLang === "ru" ? "Пароль должен быть не менее 8 символов." : "Password must be at least 8 characters.", "error");
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-xs"></i> <span>Creating account...</span>`;
    }
    const avatarUrl = `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(displayName)}&backgroundColor=b6e3f4,c0aede,d1d4f9`;
    if (typeof customAvatarDataUrl !== "undefined" && customAvatarDataUrl) {
        try {
            localStorage.setItem('catrank_pending_avatar', JSON.stringify({ email, dataUrl: customAvatarDataUrl, createdAt: Date.now() }));
        } catch (_) {
        }
    }

    try {
        const res = await fetch("/api/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                email,
                password,
                display_name: displayName,
                avatar_url: avatarUrl
            })
        });

        const result = await res.json();

        if (!res.ok) {
            showToast(result.error || "Registration failed.", "error");
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<i class="fa-solid fa-user-plus text-xs"></i> <span>${typeof t === "function" ? t("signup_submit_btn") : "Create Account"}</span>`;
            }
            return;
        }

        if (result.requires_email_confirmation) {
            showToast(result.message || "Account created. Check your email to confirm it before signing in.", "success");
            const alertBox = document.getElementById('register-alert-box');
            if (alertBox) {
                alertBox.textContent = `If ${email} is new, check that inbox for the confirmation message before signing in.`;
                alertBox.classList.remove('hidden');
            }
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<i class="fa-solid fa-envelope-circle-check text-xs"></i> <span>Confirmation sent</span>';
            }
            passElem.value = '';
            if (confirmElem) confirmElem.value = '';
            return;
        }
        const { data: signInData, error: signInError } = await signInWithPasswordThroughApp(email, password);
        if (signInError) {
            showToast("Account created. Please sign in.", "success");
            window.location.href = "/login";
            return;
        }
        if (signInData && signInData.session) await uploadPendingRegistrationAvatar(signInData.session);
        showToast("Account created! Welcome to CatRank!", "success");
        window.location.href = "/";

    } catch (err) {
        showToast("Connection error: " + err.message, "error");
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i class="fa-solid fa-user-plus text-xs"></i> <span>${typeof t === "function" ? t("signup_submit_btn") : "Create Account"}</span>`;
        }
    }
}

async function handleLogout() {
    if (typeof supabaseClient === "undefined" || !supabaseClient) return;
    const { error } = await supabaseClient.auth.signOut({scope: "local"});
    if (error) { showToast(error.message, "error"); return; }
    showToast(typeof t === "function" ? t("toast_signout_success") : "Signed out successfully.");
    setTimeout(() => {
        window.location.href = "/";
    }, 400);
}

window.addEventListener("catrank_language_changed", checkAuth);
document.addEventListener("DOMContentLoaded", checkAuth);

if (supabaseClient) {
    supabaseClient.auth.onAuthStateChange((event, session) => {
        authCheckVersion++;
        setCurrentSession(session);
        if (typeof updateModalAuth === 'function') updateModalAuth();
        window.dispatchEvent(new CustomEvent('catrank_auth_changed'));
        if (['INITIAL_SESSION', 'SIGNED_IN', 'USER_UPDATED', 'SIGNED_OUT'].includes(event)) setTimeout(checkAuth, 0);
    });
}
