let currentSession = null;

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
    if (user && user.user_metadata && user.user_metadata.avatar_url) {
        return user.user_metadata.avatar_url;
    }
    const name = (user && user.user_metadata && user.user_metadata.display_name) 
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
    if (typeof supabaseClient === "undefined" || !supabaseClient) return;
    try {
        const { data: { session } } = await supabaseClient.auth.getSession();
        currentSession = session;
        const authSection = document.getElementById("auth-section");
        if (!authSection) return;
        
        if (session && session.user) {
            const displayName = getUserDisplayName(session.user);
            const avatarUrl = getAvatarUrl(session.user);
            const profileText = typeof t === "function" ? t("nav_profile") : "Profile";
            const signOutText = typeof t === "function" ? t("nav_signout") : "Sign Out";
            
            authSection.innerHTML = `
                <div class="flex items-center gap-1.5">
                    <a href="/profile" class="flex items-center gap-2 px-2.5 py-1.5 bg-slate-100/90 hover:bg-slate-200/90 rounded-xl transition group shadow-2xs">
                        <img src="${avatarUrl}" alt="Avatar" onerror="handleAvatarError(this, '${displayName.replace(/'/g, "\\'")}')" class="w-6 h-6 rounded-full bg-white border border-slate-200 object-cover">
                        <span class="text-xs font-bold text-slate-800 max-w-[100px] truncate hidden sm:inline">${displayName}</span>
                    </a>
                    <button onclick="handleLogout()" class="px-3 py-1.5 text-xs font-bold text-rose-600 bg-rose-50 hover:bg-rose-100 rounded-xl transition flex items-center gap-1 shadow-2xs" title="${signOutText}">
                        <i class="fa-solid fa-right-from-bracket text-xs"></i>
                        <span class="hidden sm:inline">${signOutText}</span>
                    </button>
                </div>
            `;

            // Only load page-specific authenticated data when it is actually needed.
            // Notifications are fetched when the bell is opened, not on every page load.
            if (typeof syncUserLikes === "function" && document.querySelector('[id^="heart-icon-"]')) {
                syncUserLikes();
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
        const { data, error } = await supabaseClient.auth.signInWithPassword({ email, password });
        if (error) {
            showToast(error.message, "error");
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<i class="fa-solid fa-right-to-bracket text-xs"></i> <span>${typeof t === "function" ? t("signin_submit_btn") : "Sign In"}</span>`;
            }
        } else {
            showToast(typeof t === "function" ? t("toast_signin_success") : "Welcome back! Redirecting...", "success");
            setTimeout(() => {
                window.location.href = "/";
            }, 600);
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
    const phoneElem = document.getElementById("reg-phone");
    const bioElem = document.getElementById("reg-bio");
    const passElem = document.getElementById("reg-password");
    const confirmElem = document.getElementById("reg-confirm-password");
    const btn = document.getElementById("register-btn");

    if (!emailElem || !passElem) return;

    const displayName = (nameElem ? nameElem.value.trim() : "") || emailElem.value.split("@")[0];
    const email = emailElem.value.trim().toLowerCase();
    const phone = phoneElem ? phoneElem.value.trim() : "";
    const bio = bioElem ? bioElem.value.trim() : "";
    const password = passElem.value;
    const confirmPassword = confirmElem ? confirmElem.value : password;

    if (!email || !password) {
        showToast("Please provide all required fields.", "error");
        return;
    }

    if (password !== confirmPassword) {
        showToast("Passwords do not match.", "error");
        return;
    }

    if (password.length < 6) {
        showToast("Password must be at least 6 characters.", "error");
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-xs"></i> <span>Creating account...</span>';
    }

    const avatarUrl = `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(displayName)}&backgroundColor=b6e3f4,c0aede,d1d4f9`;

    try {
        const redirectTo = `${window.location.origin}/login?verified=1`;
        const { data, error } = await supabaseClient.auth.signUp({
            email,
            password,
            options: {
                emailRedirectTo: redirectTo,
                data: {
                    display_name: displayName,
                    phone_number: phone,
                    bio: bio,
                    avatar_url: avatarUrl
                }
            }
        });

        if (error) {
            const msg = String(error.message || "");
            const lower = msg.toLowerCase();
            if (lower.includes("already registered") || lower.includes("already exists")) {
                showToast("An account with this email already exists. Please sign in or use Forgot Password.", "error");
            } else {
                showToast(msg || "Could not create the account.", "error");
            }
            return;
        }

        const user = data && data.user ? data.user : null;
        const session = data && data.session ? data.session : null;
        const identities = user && Array.isArray(user.identities) ? user.identities : null;

        // When Confirm Email is enabled, Supabase intentionally returns an
        // obfuscated/fake user for an existing confirmed email. That object has
        // no identities, so do not show a false "Account Created" success state.
        if (user && identities && identities.length === 0) {
            showToast("An account with this email already exists. Please sign in or use Forgot Password.", "error");
            return;
        }

        const formCard = document.getElementById("reg-card-container");
        const successCard = document.getElementById("reg-success-card");
        const emailDisp = document.getElementById("registered-email-display");
        const successTitle = document.querySelector("#reg-success-card h2");
        const successPrefix = document.querySelector("#reg-success-card [data-i18n='check_email_desc_prefix']");
        const successSuffix = document.querySelector("#reg-success-card [data-i18n='check_email_desc_suffix']");

        if (emailDisp) emailDisp.innerText = email;

        if (session) {
            // Confirm Email is disabled in Supabase, so there is no verification
            // email to send. Create/sync the profile now and tell the user the truth.
            try {
                const verifyRes = await fetch("/api/user/profile/ensure", {
                    method: "POST",
                    headers: { "Authorization": `Bearer ${session.access_token}` }
                });
                if (!verifyRes.ok) {
                    const verifyData = await verifyRes.json().catch(() => ({}));
                    console.warn("Profile ensure after signup failed:", verifyData.error || verifyRes.statusText);
                }
            } catch (profileErr) {
                console.warn("Profile ensure after signup failed:", profileErr);
            }

            showToast("Account created successfully. You can sign in now.", "success");
            setTimeout(() => {
                window.location.href = "/";
            }, 700);
            return;
        }

        // No session means Supabase is requiring email confirmation. The signup
        // call itself sends the verification email; we only show the confirmation UI.
        if (formCard && successCard) {
            if (successTitle) successTitle.textContent = "Please Check Your Email";
            if (successPrefix) successPrefix.textContent = "We've sent a verification link to";
            if (successSuffix) successSuffix.textContent = "Please click the link in your inbox to activate your account and finish registration.";
            formCard.classList.add("hidden");
            successCard.classList.remove("hidden");
            showToast("Verification email sent. Please check your inbox and spam folder.", "success");
        } else {
            showToast("Verification email sent. Please check your inbox.", "success");
        }
    } catch (err) {
        showToast("Connection error: " + (err && err.message ? err.message : err), "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-user-plus text-xs"></i> <span>' + (typeof t === "function" ? t("signup_submit_btn") : "Create Account") + '</span>';
        }
    }
}

async function handleLogout() {
    if (typeof supabaseClient === "undefined" || !supabaseClient) return;
    await supabaseClient.auth.signOut();
    showToast(typeof t === "function" ? t("toast_signout_success") : "Signed out successfully.");
    setTimeout(() => {
        window.location.href = "/";
    }, 400);
}

window.addEventListener("catrank_language_changed", checkAuth);
document.addEventListener("DOMContentLoaded", checkAuth);
