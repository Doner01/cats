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
    const displayName = (nameElem ? nameElem.value.trim() : "") || emailElem.value.split('@')[0];
    const email = emailElem.value.trim();
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
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-xs"></i> <span>Creating account...</span>`;
    }

    // Avatar calculation
    let avatarUrl = `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(displayName)}&backgroundColor=b6e3f4,c0aede,d1d4f9`;
    if (typeof customAvatarDataUrl !== "undefined" && customAvatarDataUrl) {
        avatarUrl = customAvatarDataUrl;
    }

    try {
        const { data, error } = await supabaseClient.auth.signUp({ 
            email, 
            password,
            options: {
                data: {
                    display_name: displayName,
                    phone_number: phone,
                    bio: bio,
                    avatar_url: avatarUrl
                }
            }
        });
        
        if (error) {
            showToast(error.message, "error");
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = `<i class="fa-solid fa-user-plus text-xs"></i> <span>${typeof t === "function" ? t("signup_submit_btn") : "Create Account"}</span>`;
            }
        } else {
            // Show the prominent confirmation card
            const formCard = document.getElementById("reg-card-container");
            const successCard = document.getElementById("reg-success-card");
            const emailDisp = document.getElementById("registered-email-display");

            if (formCard && successCard) {
                if (emailDisp) emailDisp.innerText = email;
                formCard.classList.add("hidden");
                successCard.classList.remove("hidden");
                showToast(typeof t === "function" && currentLang === "ru" ? "Аккаунт создан! Проверьте вашу почту." : "Account created! Please check your email.", "success");
            } else {
                showToast(typeof t === "function" ? t("toast_signup_success") : "Account created successfully! Redirecting...", "success");
                setTimeout(() => {
                    window.location.href = "/";
                }, 800);
            }
        }
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
    await supabaseClient.auth.signOut();
    showToast(typeof t === "function" ? t("toast_signout_success") : "Signed out successfully.");
    setTimeout(() => {
        window.location.href = "/";
    }, 400);
}

window.addEventListener("catrank_language_changed", checkAuth);
document.addEventListener("DOMContentLoaded", checkAuth);
