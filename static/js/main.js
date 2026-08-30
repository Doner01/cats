function formatCommentText(rawComment) {
    if (!rawComment) return { text: '', replyTo: null };
    let text = String(rawComment);
    let replyTo = null;

    if (text.startsWith("[reply:")) {
        const endIdx = text.indexOf("]");
        if (endIdx !== -1) {
            const tagContent = text.substring(7, endIdx); // after reply prefix
            const parts = tagContent.split(":");
            replyTo = parts.length > 1 ? parts[1].trim() : parts[0].trim();
            text = text.substring(endIdx + 1).trim();
        }
    }
    return { text: text, replyTo: replyTo };
}

/**
 * CatRank Core Interaction & Modal Engine
 */

let lastLikeTime = 0;
let lastCommentTime = 0;
const COOLDOWN_MS = 15000; // 10s cooldown

let activeModalCatId = null;
let activeReplyParentId = null;
const catDetailCache = new Map();
let likedCatIdsCache = null;
let activeReplyAuthorName = null;

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeJsString(str) {
    if (!str) return '';
    return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

// ----------------------------------------------------
// Cat Detail Modal & Feed Interaction
// ----------------------------------------------------

function resetCatModalState() {
    const modalNameElem = document.getElementById("modal-cat-name");
    const modalImgElem = document.getElementById("modal-cat-img");
    const bioBox = document.getElementById("modal-cat-bio-box");
    const bioText = document.getElementById("modal-cat-bio-text");
    const commentsList = document.getElementById("modal-comments-list");
    const commentsCount = document.getElementById("modal-comments-count");
    const countBadge = document.getElementById("modal-comments-count-badge");
    const commentInput = document.getElementById("modal-comment-input");

    if (modalNameElem) modalNameElem.innerText = "";
    if (modalImgElem) {
        modalImgElem.src = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100' fill='%231e293b'></svg>";
    }
    if (bioBox) bioBox.classList.add("hidden");
    if (bioText) bioText.innerText = "";
    if (commentsList) {
        const loadingText = typeof t === 'function' ? t('loading_comments') : 'Loading comments...';
        commentsList.innerHTML = `<div class="py-10 text-center text-slate-400"><i class="fa-solid fa-spinner fa-spin text-base text-indigo-500 mb-2"></i><p class="text-xs font-medium">${loadingText}</p></div>`;
    }
    if (commentsCount) commentsCount.innerText = "(0)";
    if (countBadge) {
        const label = typeof t === 'function' ? (currentLang === 'ru' ? 'комментариев' : 'comments') : 'comments';
        countBadge.innerText = `0 ${label}`;
    }
    if (commentInput) commentInput.value = "";
    cancelReply();
}

async function openCatModal(catId) {
    if (!catId) return;
    activeModalCatId = catId;

    // Reset previous modal data completely before opening new modal
    resetCatModalState();

    const modal = document.getElementById("cat-detail-modal");
    if (!modal) return;

    modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";

    // Instant optimistic populate from clicked cat card in DOM if available
    const card = document.querySelector(`[data-cat-id="${catId}"]`);
    const modalNameElem = document.getElementById("modal-cat-name");
    const modalImgElem = document.getElementById("modal-cat-img");

    if (card) {
        const cardName = card.dataset.catName;
        const cardImg = card.querySelector("img");
        if (cardName && modalNameElem) modalNameElem.innerText = cardName;
        if (cardImg && cardImg.src && modalImgElem) modalImgElem.src = cardImg.src;
    } else {
        if (modalNameElem) modalNameElem.innerText = typeof t === "function" && currentLang === "ru" ? "Загрузка..." : "Loading...";
    }

    try {
        let cat = catDetailCache.get(String(catId));
        if (!cat) {
            const res = await fetch(`/api/cats/${catId}`);
            if (!res.ok) throw new Error("Cat details request failed");
            const data = await res.json();
            cat = data.cat || data;
            if (cat) catDetailCache.set(String(catId), cat);
        }
        if (cat) {
            if (modalNameElem) modalNameElem.innerText = cat.name || "Whiskers";
            if (modalImgElem) modalImgElem.src = cat.image_url || "";

            // Display cat bio / story if present
            const catBio = cat.bio || cat.description || "";
            const bioBox = document.getElementById("modal-cat-bio-box");
            const bioText = document.getElementById("modal-cat-bio-text");
            if (catBio && bioBox && bioText) {
                bioText.innerText = catBio;
                bioBox.classList.remove("hidden");
            }
        }
    } catch (err) {
        console.error("Failed to load cat details:", err);
    }

    loadCatComments(catId);
}

function closeCatModal() {
    const modal = document.getElementById("cat-detail-modal");
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.style.overflow = "auto";
    activeModalCatId = null;

    // Reset and forget all previous data immediately upon closing
    resetCatModalState();
}

// Close modal on escape key
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        closeCatModal();
    }
});

// Close modal when clicking backdrop outside dialog
const catDetailModalElem = document.getElementById("cat-detail-modal");
if (catDetailModalElem) {
    catDetailModalElem.addEventListener("click", (e) => {
        if (e.target === catDetailModalElem) {
            closeCatModal();
        }
    });
}

// ----------------------------------------------------
// Like & Community Voting System
// ----------------------------------------------------

async function syncUserLikes() {
    if (!currentSession || !currentSession.access_token) return;
    try {
        const res = await fetch("/api/user/liked-cats", {
            headers: { "Authorization": `Bearer ${currentSession.access_token}` }
        });
        if (!res.ok) return;
        const data = await res.json();
        likedCatIdsCache = new Set((data.liked_cat_ids || []).map(String));

        likedCatIdsCache.forEach(id => {
            const heartElem = document.getElementById(`heart-icon-${id}`);
            if (heartElem) heartElem.innerText = "❤️";
        });
    } catch (e) {
        console.error("Failed to sync liked cats:", e);
    }
}

async function toggleLike(catId, event) {
    if (event) event.stopPropagation();

    if (typeof supabaseClient === "undefined" || !supabaseClient) {
        showToast("Supabase client not initialized.", "error");
        return;
    }

    const session = currentSession || (await supabaseClient.auth.getSession()).data.session;
    if (!session) {
        showToast(typeof t === "function" ? t("toast_need_signin_vote") : "Please sign in to vote for cats!", "info");
        setTimeout(() => window.location.href = "/login", 800);
        return;
    }

    const now = Date.now();
    if (now - lastLikeTime < COOLDOWN_MS) {
        const remaining = Math.ceil((COOLDOWN_MS - (now - lastLikeTime)) / 1000);
        const cooldownMsg = typeof t === "function" ? t("toast_cooldown", { sec: remaining }) : `Cooldown: Please wait ${remaining}s before voting again.`;
        showToast(cooldownMsg, "info");
        return;
    }
    lastLikeTime = now;

    const countElem = document.getElementById(`like-count-${catId}`);
    const heartElem = document.getElementById(`heart-icon-${catId}`);
    const prevCount = parseInt(countElem ? countElem.innerText : "0", 10) || 0;
    const isLiked = heartElem ? heartElem.innerText === "❤️" : false;

    // Optimistic UI update
    const nextLiked = !isLiked;
    const nextCount = nextLiked ? prevCount + 1 : Math.max(0, prevCount - 1);

    if (heartElem) heartElem.innerText = nextLiked ? "❤️" : "🤍";
    if (countElem) countElem.innerText = nextCount;

    try {
        const res = await fetch(`/api/cats/${catId}/like`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        const data = await res.json();
        if (res.ok) {
            const serverLiked = data.status === "liked";
            if (countElem) countElem.innerText = data.likes_count;
            if (heartElem) heartElem.innerText = serverLiked ? "❤️" : "🤍";
            showToast(serverLiked ? "Voted!" : "Vote removed", "success");
            if (typeof fetchNotifications === "function") fetchNotifications();
        } else {
            // Revert
            if (countElem) countElem.innerText = prevCount;
            if (heartElem) heartElem.innerText = isLiked ? "❤️" : "🤍";
            showToast(data.error || "Failed to update vote.", "error");
        }
    } catch (err) {
        if (countElem) countElem.innerText = prevCount;
        if (heartElem) heartElem.innerText = isLiked ? "❤️" : "🤍";
        showToast("Network error. Please try again.", "error");
    }
}

// ----------------------------------------------------
// Threaded Comments & Replies Engine (Single-Depth)
// ----------------------------------------------------

function startReply(commentId, authorName, rootCommentId = null) {
    activeReplyParentId = rootCommentId || commentId;
    activeReplyAuthorName = authorName;

    const banner = document.getElementById("modal-reply-banner");
    const targetNameElem = document.getElementById("modal-reply-target-name");
    const input = document.getElementById("modal-comment-input");

    if (banner && targetNameElem) {
        targetNameElem.innerText = `@${authorName}`;
        banner.classList.remove("hidden");
    }
    if (input) {
        const placeholderText = typeof t === "function" ? t("reply_placeholder") : "Write a reply... (15s cooldown)";
        input.placeholder = placeholderText;
        input.focus();
    }
}

function cancelReply() {
    activeReplyParentId = null;
    activeReplyAuthorName = null;

    const banner = document.getElementById("modal-reply-banner");
    const input = document.getElementById("modal-comment-input");

    if (banner) {
        banner.classList.add("hidden");
    }
    if (input) {
        input.placeholder = typeof t === "function" ? t("comment_placeholder") : "Add a comment... (15s cooldown)";
    }
}

async function loadCatComments(catId) {
    try {
        const res = await fetch(`/api/cats/${catId}/comments`);
        const data = await res.json();
        const comments = data.comments || [];
        const container = document.getElementById("modal-comments-list");
        const countElem = document.getElementById("modal-comments-count");
        const countBadge = document.getElementById("modal-comments-count-badge");

        if (countElem) {
            countElem.innerText = `(${comments.length})`;
        }
        if (countBadge) {
            const label = typeof t === "function" ? (currentLang === 'ru' ? "комментариев" : "comments") : "comments";
            countBadge.innerText = `${comments.length} ${label}`;
        }

        if (!container) return;

        if (comments.length === 0) {
            const noCommentsText = typeof t === "function" ? t("no_comments") : "No comments yet. Be the first to say something nice!";
            container.innerHTML = `
                <div class="py-10 text-center text-slate-400 space-y-2">
                    <i class="fa-regular fa-comment-dots text-3xl text-slate-300"></i>
                    <p class="text-xs font-medium">${noCommentsText}</p>
                </div>
            `;
            return;
        }

        let currentUserId = null;
        if (typeof currentSession !== "undefined" && currentSession && currentSession.user) {
            currentUserId = currentSession.user.id;
        }

        const rootComments = [];
        const repliesByParent = {};
        const allCommentIds = new Set(comments.map(c => String(c.id)));

        comments.forEach(c => {
            const rawPid = c.parent_id;
            const pid = (rawPid && String(rawPid).trim() !== "" && String(rawPid).trim().toLowerCase() !== "null" && String(rawPid).trim().toLowerCase() !== "none" && String(rawPid).trim().toLowerCase() !== "undefined") ? String(rawPid).trim() : null;
            
            if (pid && allCommentIds.has(pid)) {
                if (!repliesByParent[pid]) {
                    repliesByParent[pid] = [];
                }
                repliesByParent[pid].push(c);
            } else {
                rootComments.push(c);
            }
        });

        const replyBtnText = typeof t === "function" ? t("reply_btn") : "Reply";
        const deleteBtnText = typeof t === "function" ? t("delete_btn") : "Delete";
        const replyingToText = typeof t === "function" ? t("replying_to") : "Replying to";

        container.innerHTML = rootComments.map(c => {
            const authorDisplayName = c.user_name || "Cat Lover";
            const userTarget = c.user_id || c.user_name || '';
            const avatar = c.user_avatar || `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(authorDisplayName)}&backgroundColor=b6e3f4,c0aede,d1d4f9`;
            const isOwner = currentUserId && String(c.user_id) === String(currentUserId);
            const replies = repliesByParent[String(c.id)] || [];
            const rootId = String(c.id);

            const repliesHtml = replies.map(r => {
                const rAuthorName = r.user_name || "Cat Lover";
                const rUserTarget = r.user_id || r.user_name || '';
                const rAvatar = r.user_avatar || `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(rAuthorName)}&backgroundColor=b6e3f4,c0aede,d1d4f9`;
                const rIsOwner = currentUserId && String(r.user_id) === String(currentUserId);
                const safeRAuthorName = escapeHtml(rAuthorName);
                const jsSafeRAuthorName = escapeJsString(rAuthorName);

                return `
                    <div class="comment-reply-card flex items-start gap-2.5 mt-2">
                        <a href="/user/${encodeURIComponent(rUserTarget)}" class="flex-shrink-0">
                            <img src="${rAvatar}" alt="Avatar" onerror="handleAvatarError(this, '${jsSafeRAuthorName}')" class="w-6 h-6 rounded-full bg-slate-50 border border-slate-200 object-cover">
                        </a>
                        <div class="flex-grow min-w-0">
                            <div class="flex items-center justify-between gap-1">
                                <div class="flex items-center gap-1.5 flex-wrap">
                                    <a href="/user/${encodeURIComponent(rUserTarget)}" class="text-xs font-black text-slate-900 hover:text-indigo-600 transition">${safeRAuthorName}</a>
                                    <span class="text-[10px] text-indigo-700 bg-indigo-50 border border-indigo-100/80 px-2 py-0.5 rounded-full font-bold flex items-center gap-1">
                                        <i class="fa-solid fa-reply text-[8px]"></i>
                                        <span>${replyingToText} @${escapeHtml(r.reply_to_name || authorDisplayName)}</span>
                                    </span>
                                    <span class="text-[10px] text-slate-400 font-medium">${(r.created_at || '').slice(0, 10)}</span>
                                </div>
                                <div class="flex items-center gap-1">
                                    <button onclick="startReply('${rootId}', '${jsSafeRAuthorName}', '${rootId}')" class="text-[11px] font-bold text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 px-1.5 py-0.5 rounded-md transition" title="${replyBtnText}">
                                        <i class="fa-solid fa-reply text-[9px]"></i>
                                    </button>
                                    ${rIsOwner ? `
                                        <button onclick="deleteComment('${r.id}', event)" class="text-slate-400 hover:text-rose-600 transition p-1 text-xs" title="${deleteBtnText}">
                                            <i class="fa-solid fa-trash-can"></i>
                                        </button>
                                    ` : ''}
                                </div>
                            </div>
                            <p class="text-xs text-slate-700 mt-1 leading-relaxed break-words font-medium">${escapeHtml(formatCommentText(r.comment).text)}</p>
                        </div>
                    </div>
                `;
            }).join("");

            const safeAuthorDisplayName = escapeHtml(authorDisplayName);
            const jsSafeAuthorDisplayName = escapeJsString(authorDisplayName);

            return `
                <div class="p-3.5 rounded-2xl bg-white border border-slate-200 shadow-sm hover:border-slate-300 transition">
                    <div class="flex items-start gap-3">
                        <a href="/user/${encodeURIComponent(userTarget)}" class="flex-shrink-0">
                            <img src="${avatar}" alt="Avatar" onerror="handleAvatarError(this, '${jsSafeAuthorDisplayName}')" class="w-8 h-8 rounded-full bg-slate-50 border border-slate-200 object-cover">
                        </a>
                        <div class="flex-grow min-w-0">
                            <div class="flex items-center justify-between gap-2">
                                <div class="flex items-center gap-2">
                                    <a href="/user/${encodeURIComponent(userTarget)}" class="text-xs font-black text-slate-900 hover:text-indigo-600 transition">${safeAuthorDisplayName}</a>
                                    <span class="text-[10px] text-slate-400 font-medium">${(c.created_at || '').slice(0, 10)}</span>
                                </div>
                                <div class="flex items-center gap-1">
                                    <button onclick="startReply('${rootId}', '${jsSafeAuthorDisplayName}', '${rootId}')" class="text-xs font-bold text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 px-2.5 py-1 rounded-xl transition flex items-center gap-1 border border-indigo-100">
                                        <i class="fa-solid fa-reply text-[10px]"></i>
                                        <span>${replyBtnText}</span>
                                    </button>
                                    ${isOwner ? `
                                        <button onclick="deleteComment('${c.id}', event)" class="text-slate-400 hover:text-rose-600 transition p-1 text-xs ml-1" title="${deleteBtnText}">
                                            <i class="fa-solid fa-trash-can"></i>
                                        </button>
                                    ` : ''}
                                </div>
                            </div>
                            <p class="text-xs text-slate-800 mt-1.5 leading-relaxed break-words font-medium">${escapeHtml(formatCommentText(c.comment).text)}</p>
                        </div>
                    </div>

                    ${replies.length > 0 ? `
                        <div class="comment-thread-line space-y-1.5 mt-2.5">
                            ${repliesHtml}
                        </div>
                    ` : ''}
                </div>
            `;
        }).join("");
    } catch (e) {
        console.error("Comments error:", e);
    }
}

async function submitComment(event) {
    if (event) event.preventDefault();

    if (typeof supabaseClient === "undefined" || !supabaseClient) {
        showToast("Supabase client not initialized.", "error");
        return;
    }
    const session = currentSession || (await supabaseClient.auth.getSession()).data.session;
    if (!session) {
        showToast(typeof t === "function" ? t("toast_need_signin_comment") : "Please sign in to post comments.", "info");
        setTimeout(() => window.location.href = "/login", 800);
        return;
    }

    const input = document.getElementById("modal-comment-input");
    const submitBtn = document.getElementById("modal-comment-submit-btn");
    if (!input || !activeModalCatId) return;

    const commentText = input.value.trim();
    if (!commentText) return;

    const now = Date.now();
    if (now - lastCommentTime < COOLDOWN_MS) {
        const remaining = Math.ceil((COOLDOWN_MS - (now - lastCommentTime)) / 1000);
        const cooldownMsg = typeof t === "function" ? t("toast_cooldown", { sec: remaining }) : `Cooldown: Please wait ${remaining}s before commenting again.`;
        showToast(cooldownMsg, "info");
        return;
    }
    lastCommentTime = now;

    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-xs"></i>';
    }

    const isReply = !!activeReplyParentId;
    const payload = {
        comment: commentText,
        parent_id: activeReplyParentId || null,
        reply_to_name: activeReplyAuthorName || null
    };

    try {
        const res = await fetch(`/api/cats/${activeModalCatId}/comments`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${session.access_token}`
            },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            input.value = "";
            cancelReply();
            loadCatComments(activeModalCatId);
            showToast(isReply ? "Reply posted!" : "Comment posted!", "success");
            if (typeof fetchNotifications === "function") fetchNotifications();
        } else {
            const err = await res.json();
            showToast(err.error || "Failed to post comment.", "error");
        }
    } catch (e) {
        showToast("Error posting comment: " + e.message, "error");
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fa-solid fa-paper-plane text-xs"></i> <span>Send</span>';
        }
    }
}

async function deleteComment(commentId, event) {
    if (event) event.stopPropagation();
    if (!currentSession) return;

    const confirmed = typeof showConfirmModal === 'function'
        ? await showConfirmModal({
            title: typeof t === 'function' && currentLang === 'ru' ? "Удаление комментария" : "Delete Comment",
            message: typeof t === 'function' && currentLang === 'ru' ? "Вы уверены, что хотите удалить этот комментарий?" : "Are you sure you want to delete this comment?",
            confirmText: typeof t === 'function' && currentLang === 'ru' ? "Удалить" : "Delete",
            danger: true
        })
        : confirm("Are you sure you want to delete this comment?");

    if (!confirmed) return;

    try {
        const res = await fetch(`/api/comments/${commentId}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${currentSession.access_token}` }
        });
        if (res.ok) {
            showToast("Comment deleted!", "success");
            if (activeModalCatId) {
                loadCatComments(activeModalCatId);
            }
        } else {
            showToast("Failed to delete comment.", "error");
        }
    } catch (e) {
        showToast("Error: " + e.message, "error");
    }
}

// ----------------------------------------------------
// Notifications Bell & Dropdown
// ----------------------------------------------------

function toggleNotificationsDropdown() {
    const dropdown = document.getElementById("notifications-dropdown");
    if (!dropdown) return;
    dropdown.classList.toggle("hidden");
    if (!dropdown.classList.contains("hidden")) {
        fetchNotifications();
    }
}

// Close notifications dropdown on outside click
document.addEventListener("click", (e) => {
    const wrapper = document.getElementById("notifications-dropdown-wrapper");
    const dropdown = document.getElementById("notifications-dropdown");
    if (wrapper && dropdown && !wrapper.contains(e.target)) {
        dropdown.classList.add("hidden");
    }
});

async function fetchNotifications() {
    if (!currentSession || !currentSession.access_token) return;
    try {
        const res = await fetch("/api/notifications", {
            headers: { "Authorization": `Bearer ${currentSession.access_token}` }
        });
        if (!res.ok) return;
        const data = await res.json();
        const list = data.notifications || [];
        const badge = document.getElementById("notif-badge");
        const listContainer = document.getElementById("notifications-list");

        if (badge) {
            if (data.unread_count > 0) {
                badge.innerText = data.unread_count;
                badge.classList.remove("hidden");
            } else {
                badge.classList.add("hidden");
            }
        }

        if (listContainer) {
            if (list.length === 0) {
                listContainer.innerHTML = `<div class="p-8 text-center text-slate-400">No notifications yet</div>`;
                return;
            }

            listContainer.innerHTML = list.map(n => {
                const isRead = n.is_read;
                const avatar = n.actor_avatar || getFallbackAvatarSvg(n.actor_name);
                return `
                    <div class="p-3 flex items-start gap-2.5 transition hover:bg-slate-50 ${isRead ? 'opacity-70' : 'bg-indigo-50/40'}">
                        <img src="${avatar}" alt="Avatar" class="w-8 h-8 rounded-full object-cover border border-slate-200 flex-shrink-0">
                        <div class="flex-grow min-w-0">
                            <p class="text-xs text-slate-800 leading-snug">${escapeHtml(n.message)}</p>
                            <span class="text-[10px] text-slate-400">${(n.created_at || '').slice(0, 10)}</span>
                        </div>
                    </div>
                `;
            }).join("");
        }
    } catch (e) {
        console.error("Failed to fetch notifications:", e);
    }
}

async function markAllNotificationsRead() {
    if (!currentSession) return;
    try {
        await fetch("/api/notifications/read-all", {
            method: "POST",
            headers: { "Authorization": `Bearer ${currentSession.access_token}` }
        });
        fetchNotifications();
    } catch (e) {
        console.error("Error marking all read:", e);
    }
}

window.addEventListener("catrank_language_changed", () => {
    if (activeModalCatId) {
        loadCatComments(activeModalCatId);
    }
});
