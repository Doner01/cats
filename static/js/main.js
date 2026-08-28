let lastLikeTime = 0;
let lastCommentTime = 0;
const COOLDOWN_MS = 10000; // 10 seconds anti-spam

let activeModalCatId = null;
let activeReplyParentId = null;
let activeReplyAuthorName = null;

function escapeJsString(str) {
    if (!str) return '';
    return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function timeAgo(dateString) {
    if (!dateString) return '';
    const now = new Date();
    const date = new Date(dateString);
    const seconds = Math.floor((now - date) / 1000);

    if (seconds < 60) return `${Math.max(1, seconds)}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return dateString.slice(0, 10);
}

// Search Filter
function filterCats() {
    const input = document.getElementById("search-input");
    if (!input) return;
    const query = input.value.toLowerCase().trim();
    const cards = document.querySelectorAll(".cat-feed-card");
    const noResults = document.getElementById("no-search-results");
    let visibleCount = 0;

    cards.forEach(card => {
        const name = (card.getAttribute("data-cat-name") || "").toLowerCase();
        if (name.includes(query)) {
            card.classList.remove("hidden");
            visibleCount++;
        } else {
            card.classList.add("hidden");
        }
    });

    if (noResults) {
        if (visibleCount === 0 && query.length > 0) {
            noResults.classList.remove("hidden");
        } else {
            noResults.classList.add("hidden");
        }
    }
}

// Sync user's previously liked cats on page load
async function syncUserLikes() {
    if (!currentSession) return;
    try {
        const res = await fetch("/api/user/liked-cats", {
            headers: { "Authorization": `Bearer ${currentSession.access_token}` }
        });
        if (!res.ok) return;
        const data = await res.json();
        const likedIds = new Set(data.liked_cat_ids || []);

        likedIds.forEach(id => {
            const heartElem = document.getElementById(`heart-icon-${id}`);
            if (heartElem) {
                heartElem.className = "fa-solid fa-heart text-rose-500 text-sm group-hover/btn:scale-125 transition-transform";
            }
        });
        
        if (activeModalCatId && likedIds.has(activeModalCatId)) {
            const modalHeartElem = document.getElementById("modal-heart-icon");
            if (modalHeartElem) {
                modalHeartElem.className = "fa-solid fa-heart text-base text-rose-500 transition-transform group-hover:scale-125";
            }
        }
    } catch (e) {
        console.error("Failed to sync liked cats:", e);
    }
}

// Toggle Like
async function toggleLike(catId, event) {
    if (event) event.stopPropagation();

    if (typeof supabaseClient === "undefined" || !supabaseClient) {
        showToast("Supabase client not initialized.", "error");
        return;
    }
    const { data: { session } } = await supabaseClient.auth.getSession();
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
    const modalCountElem = document.getElementById(`modal-like-count`);
    const modalHeartElem = document.getElementById(`modal-heart-icon`);

    const prevCount = parseInt(countElem ? countElem.innerText : (modalCountElem ? modalCountElem.innerText : "0"), 10) || 0;
    const isLiked = heartElem ? heartElem.classList.contains("fa-solid") : (modalHeartElem ? modalHeartElem.classList.contains("fa-solid") : false);

    // Double-click heart burst animation
    const dblHeart = document.getElementById("double-click-heart");
    if (dblHeart && !isLiked) {
        dblHeart.classList.remove("hidden");
        setTimeout(() => dblHeart.classList.add("hidden"), 600);
    }

    // Optimistic UI Update
    const nextLiked = !isLiked;
    const nextCount = nextLiked ? prevCount + 1 : Math.max(0, prevCount - 1);

    if (heartElem) {
        heartElem.className = nextLiked ? "fa-solid fa-heart text-rose-500 text-sm group-hover/btn:scale-125 transition-transform" : "fa-regular fa-heart text-rose-500 text-sm group-hover/btn:scale-125 transition-transform";
    }
    if (countElem) countElem.innerText = nextCount;
    if (modalHeartElem) {
        modalHeartElem.className = nextLiked ? "fa-solid fa-heart text-base text-rose-500 transition-transform group-hover:scale-125" : "fa-regular fa-heart text-base text-rose-500 transition-transform group-hover:scale-125";
    }
    if (modalCountElem) modalCountElem.innerText = nextCount;

    try {
        const res = await fetch(`/api/cats/${catId}/like`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        const data = await res.json();
        if (res.ok) {
            const serverLiked = data.status === "liked";
            if (countElem) countElem.innerText = data.likes_count;
            if (heartElem) {
                heartElem.className = serverLiked ? "fa-solid fa-heart text-rose-500 text-sm group-hover/btn:scale-125 transition-transform" : "fa-regular fa-heart text-rose-500 text-sm group-hover/btn:scale-125 transition-transform";
            }
            if (modalCountElem) modalCountElem.innerText = data.likes_count;
            if (modalHeartElem) {
                modalHeartElem.className = serverLiked ? "fa-solid fa-heart text-base text-rose-500 transition-transform group-hover:scale-125" : "fa-regular fa-heart text-base text-rose-500 transition-transform group-hover:scale-125";
            }
            showToast(serverLiked ? (typeof t === "function" ? t("toast_voted") : "Voted!") : (typeof t === "function" ? t("toast_vote_removed") : "Vote removed"), "success");
            fetchNotifications();
        } else {
            // Revert
            if (countElem) countElem.innerText = prevCount;
            if (heartElem) {
                heartElem.className = isLiked ? "fa-solid fa-heart text-rose-500 text-sm group-hover/btn:scale-125 transition-transform" : "fa-regular fa-heart text-rose-500 text-sm group-hover/btn:scale-125 transition-transform";
            }
            if (modalCountElem) modalCountElem.innerText = prevCount;
            if (modalHeartElem) {
                modalHeartElem.className = isLiked ? "fa-solid fa-heart text-base text-rose-500 transition-transform group-hover:scale-125" : "fa-regular fa-heart text-base text-rose-500 transition-transform group-hover:scale-125";
            }
            showToast(data.error || "Failed to update vote.", "error");
        }
    } catch (err) {
        if (countElem) countElem.innerText = prevCount;
        if (heartElem) {
            heartElem.className = isLiked ? "fa-solid fa-heart text-rose-500 text-sm group-hover/btn:scale-125 transition-transform" : "fa-regular fa-heart text-rose-500 text-sm group-hover/btn:scale-125 transition-transform";
        }
        if (modalCountElem) modalCountElem.innerText = prevCount;
        if (modalHeartElem) {
            modalHeartElem.className = isLiked ? "fa-solid fa-heart text-base text-rose-500 transition-transform group-hover:scale-125" : "fa-regular fa-heart text-base text-rose-500 transition-transform group-hover:scale-125";
        }
        showToast("Network error. Please try again.", "error");
    }
}

// Open Cat Modal
async function openCatModal(catId) {
    activeModalCatId = catId;
    cancelReply();
    
    const modal = document.getElementById("cat-detail-modal");
    if (!modal) return;

    modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";

    document.getElementById("modal-cat-name").innerText = "Loading...";
    document.getElementById("modal-comments-list").innerHTML = `<p class="text-xs text-slate-400 py-8 text-center">${typeof t === "function" ? t("loading_comments") : 'Loading comments...'}</p>`;

    try {
        const res = await fetch(`/api/cats/${catId}`);
        const data = await res.json();
        const cat = data.cat;
        if (!cat) return;

        document.getElementById("modal-cat-image").src = cat.image_url;
        document.getElementById("modal-cat-name").innerText = cat.name;

        const bioElem = document.getElementById("modal-cat-bio");
        const catBio = String(cat.bio || "").trim();
        if (bioElem) {
            bioElem.textContent = catBio;
            bioElem.classList.toggle("hidden", !catBio);
        }
        
        const uploadedOnText = typeof t === "function" ? t("uploaded_on") : "Uploaded on";
        document.getElementById("modal-cat-date").innerText = `${uploadedOnText} ${(cat.created_at || '').slice(0, 10)}`;
        document.getElementById("modal-like-count").innerText = cat.likes_count || 0;
        
        const authorName = cat.user_name || "Cat Lover";
        const authorTarget = cat.user_id || cat.user_name || '';
        const authorLink = document.getElementById("modal-author-link");
        const authorAvatar = document.getElementById("modal-author-avatar");
        const authorNameElem = document.getElementById("modal-author-name");
        
        if (authorLink) authorLink.href = `/user/${encodeURIComponent(authorTarget)}`;
        if (authorNameElem) {
            authorNameElem.href = `/user/${encodeURIComponent(authorTarget)}`;
            authorNameElem.innerText = authorName;
        }
        
        const avatarUrl = cat.user_avatar || `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(authorName)}&backgroundColor=b6e3f4,c0aede,d1d4f9`;
        if (authorAvatar) {
            authorAvatar.src = avatarUrl;
            authorAvatar.onerror = function() { handleAvatarError(this, authorName); };
        }

        const heartElem = document.getElementById(`heart-icon-${cat.id}`);
        const isLiked = heartElem ? heartElem.classList.contains("fa-solid") : false;
        const modalHeartElem = document.getElementById("modal-heart-icon");
        if (modalHeartElem) {
            modalHeartElem.className = isLiked ? "fa-solid fa-heart text-base text-rose-500 transition-transform group-hover:scale-125" : "fa-regular fa-heart text-base text-rose-500 transition-transform group-hover:scale-125";
        }

        loadCatComments(catId);
    } catch (err) {
        showToast("Error loading cat details: " + err.message, "error");
    }
}

function closeCatModal() {
    const modal = document.getElementById("cat-detail-modal");
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.style.overflow = "auto";
    activeModalCatId = null;
    cancelReply();
}

// Reply Management
function startReply(commentId, authorName) {
    activeReplyParentId = commentId;
    activeReplyAuthorName = authorName;

    const banner = document.getElementById("modal-reply-banner");
    const targetNameElem = document.getElementById("modal-reply-target-name");
    const input = document.getElementById("modal-comment-input");

    if (banner && targetNameElem) {
        targetNameElem.innerText = `@${authorName}`;
        banner.classList.remove("hidden");
    }
    if (input) {
        const placeholderText = typeof t === "function" ? t("reply_placeholder") : `Write a reply... (10s cooldown)`;
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
        input.placeholder = typeof t === "function" ? t("comment_placeholder") : "Add a comment... (10s cooldown)";
    }
}

// Load Comments & Replies
function normalizeParentId(value) {
    if (value === null || value === undefined) return null;
    const str = String(value).trim();
    if (!str || ["null", "none", "undefined"].includes(str.toLowerCase())) return null;
    return str;
}

function buildCommentTree(comments) {
    const byId = {};
    const roots = [];

    comments.forEach(comment => {
        byId[String(comment.id)] = { ...comment, children: [] };
    });

    comments.forEach(comment => {
        const id = String(comment.id);
        const node = byId[id];
        const parentId = normalizeParentId(comment.parent_id);
        if (parentId && byId[parentId]) {
            byId[parentId].children.push(node);
        } else {
            roots.push(node);
        }
    });

    return roots;
}

function encodedHandlerValue(value) {
    return encodeURIComponent(String(value || "")).replace(/'/g, "%27");
}

function renderCommentNode(comment, currentUserId, parentAuthorName, depth = 0) {
    const authorDisplayName = String(comment.user_name || "Cat Lover");
    const userTarget = String(comment.user_id || authorDisplayName || "");
    const avatar = String(comment.user_avatar || `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(authorDisplayName)}&backgroundColor=b6e3f4,c0aede,d1d4f9`);
    const isOwner = !!currentUserId && String(comment.user_id) === String(currentUserId);
    const replyBtnText = typeof t === "function" ? t("reply_btn") : "Reply";
    const deleteBtnText = typeof t === "function" ? t("delete_btn") : "Delete";
    const replyingToText = typeof t === "function" ? t("replying_to") : "Replying to";
    const safeAuthor = escapeHtml(authorDisplayName);
    const safeAvatar = escapeHtml(avatar);
    const safeComment = escapeHtml(String(comment.comment || ""));
    const safeUserTarget = encodeURIComponent(userTarget);
    const replyAuthorEncoded = encodedHandlerValue(authorDisplayName);
    const commentId = String(comment.id);
    const parentLabel = parentAuthorName || comment.reply_to_name || "";
    const children = Array.isArray(comment.children) ? comment.children : [];

    const childIndent = Math.min(depth + 1, 4);
    const childNodes = children.map(child =>
        renderCommentNode(child, currentUserId, authorDisplayName, childIndent)
    ).join("");

    const rootClasses = depth === 0
        ? "p-3.5 rounded-2xl bg-white border border-slate-200/80 shadow-xs hover:border-slate-300 transition"
        : "p-3 rounded-2xl bg-white border border-slate-100 shadow-xs hover:border-slate-200 transition";

    const avatarSize = depth === 0 ? "w-8 h-8" : "w-7 h-7";
    const replyBadge = parentLabel ? `
        <span class="text-[10px] text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded-md font-semibold flex items-center gap-1">
            <i class="fa-solid fa-reply text-[8px]"></i>
            <span>${replyingToText} @${escapeHtml(parentLabel)}</span>
        </span>
    ` : "";

    return `
        <div class="${rootClasses}">
            <div class="flex items-start gap-3">
                <a href="/user/${safeUserTarget}" class="flex-shrink-0">
                    <img src="${safeAvatar}" alt="Avatar" onerror="handleAvatarError(this, decodeURIComponent('${replyAuthorEncoded}'))" class="${avatarSize} rounded-full bg-slate-50 border border-slate-200 object-cover">
                </a>
                <div class="flex-grow min-w-0">
                    <div class="flex items-center justify-between gap-2">
                        <div class="flex items-center gap-2 min-w-0 flex-wrap">
                            <a href="/user/${safeUserTarget}" class="text-xs font-bold text-slate-900 hover:text-indigo-600 transition truncate">${safeAuthor}</a>
                            ${replyBadge}
                            <span class="text-[10px] text-slate-400 font-medium">${escapeHtml((comment.created_at || '').slice(0, 10))}</span>
                        </div>
                        <div class="flex items-center gap-1 flex-shrink-0">
                            <button type="button" data-reply-id="${escapeHtml(commentId)}" data-reply-author="${escapeHtml(authorDisplayName)}" onclick="startReply(this.dataset.replyId, this.dataset.replyAuthor)" class="text-[11px] font-bold text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 px-2 py-0.5 rounded-lg transition flex items-center gap-1">
                                <i class="fa-solid fa-reply text-[10px]"></i>
                                <span>${replyBtnText}</span>
                            </button>
                            ${isOwner ? `
                                <button type="button" onclick="deleteComment('${escapeHtml(commentId)}', event)" class="text-slate-400 hover:text-rose-600 transition p-1 text-xs ml-1" title="${deleteBtnText}">
                                    <i class="fa-solid fa-trash-can"></i>
                                </button>
                            ` : ""}
                        </div>
                    </div>
                    <p class="text-xs text-slate-700 mt-1 leading-relaxed break-words font-medium">${safeComment}</p>
                </div>
            </div>
            ${children.length ? `
                <div class="ml-5 pl-3 border-l-2 border-indigo-100 space-y-2 mt-2">
                    ${childNodes}
                </div>
            ` : ""}
        </div>
    `;
}

async function loadCatComments(catId) {
    try {
        const res = await fetch(`/api/cats/${catId}/comments`);
        const data = await res.json();
        const comments = Array.isArray(data.comments) ? data.comments : [];
        const container = document.getElementById("modal-comments-list");
        const countElem = document.getElementById("modal-comments-count");
        const countBadge = document.getElementById("modal-comments-count-badge");

        if (countElem) countElem.innerText = `(${comments.length})`;
        if (countBadge) {
            const label = typeof t === "function" ? (currentLang === 'ru' ? "комментариев" : "comments") : "comments";
            countBadge.innerText = `${comments.length} ${label}`;
        }

        if (!container) return;

        if (comments.length === 0) {
            const noCommentsText = typeof t === "function" ? t("no_comments") : "No comments yet. Be the first to say something nice!";
            container.innerHTML = `
                <div class="py-12 text-center text-slate-400 space-y-2">
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

        const roots = buildCommentTree(comments);
        container.innerHTML = roots.map(comment => renderCommentNode(comment, currentUserId)).join("");
    } catch (e) {
        console.error("Comments error:", e);
        const container = document.getElementById("modal-comments-list");
        if (container) {
            container.innerHTML = `<p class="text-xs text-rose-500 py-8 text-center">Failed to load comments.</p>`;
        }
    }
}

// Submit Comment
async function submitComment(event) {
    event.preventDefault();
    if (!activeModalCatId) return;

    if (typeof supabaseClient === "undefined" || !supabaseClient) {
        showToast("Supabase client not initialized.", "error");
        return;
    }
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (!session) {
        showToast(typeof t === "function" ? t("toast_need_signin_comment") : "Please sign in to post comments.", "info");
        setTimeout(() => window.location.href = "/login", 800);
        return;
    }

    const input = document.getElementById("modal-comment-input");
    const text = input.value.trim();
    if (!text) return;

    const now = Date.now();
    if (now - lastCommentTime < COOLDOWN_MS) {
        const remaining = Math.ceil((COOLDOWN_MS - (now - lastCommentTime)) / 1000);
        const cooldownMsg = typeof t === "function" ? t("toast_cooldown", { sec: remaining }) : `Cooldown: Please wait ${remaining}s before commenting again.`;
        showToast(cooldownMsg, "info");
        return;
    }
    lastCommentTime = now;

    const btn = document.getElementById("modal-comment-btn");
    if (btn) btn.disabled = true;

    const payload = {
        comment: text,
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
        const data = await res.json();
        if (res.ok) {
            const isReply = !!activeReplyParentId;
            showToast(isReply ? (typeof t === "function" ? t("toast_reply_posted") : "Reply posted!") : (typeof t === "function" ? t("toast_comment_posted") : "Comment posted!"), "success");
            input.value = "";
            cancelReply();
            await loadCatComments(activeModalCatId);
            const commentsContainer = document.getElementById("modal-comments-container");
            if (commentsContainer) {
                commentsContainer.scrollTop = commentsContainer.scrollHeight;
            }
            if (typeof fetchNotifications === "function") {
                fetchNotifications();
            }
        } else {
            showToast(data.error || "Failed to post comment.", "error");
        }
    } catch (e) {
        showToast("Error posting comment: " + e.message, "error");
    } finally {
        if (btn) btn.disabled = false;
    }
}

// Delete Comment with Custom Modal Dialog
async function deleteComment(commentId, event) {
    if (event) event.stopPropagation();

    const confirmTitle = typeof t === "function" ? (currentLang === "ru" ? "Удаление комментария" : "Delete Comment") : "Delete Comment";
    const confirmMsg = typeof t === "function" ? t("delete_comment_confirm") : "Are you sure you want to delete this comment?";
    const confirmBtn = typeof t === "function" ? (currentLang === "ru" ? "Удалить" : "Delete") : "Delete";
    const cancelBtn = typeof t === "function" ? (currentLang === "ru" ? "Отмена" : "Cancel") : "Cancel";

    const confirmed = await showConfirmModal({
        title: confirmTitle,
        message: confirmMsg,
        confirmText: confirmBtn,
        cancelText: cancelBtn,
        danger: true,
        icon: "fa-solid fa-trash-can"
    });

    if (!confirmed) return;

    if (typeof supabaseClient === "undefined" || !supabaseClient) {
        showToast("Supabase client not initialized.", "error");
        return;
    }
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (!session) {
        showToast(typeof t === "function" ? t("toast_need_signin_comment") : "Please sign in to delete comments.", "error");
        return;
    }

    try {
        const res = await fetch(`/api/comments/${commentId}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        const data = await res.json();
        if (res.ok) {
            showToast(typeof t === "function" ? t("toast_comment_deleted") : "Comment deleted!", "success");
            if (activeModalCatId) {
                loadCatComments(activeModalCatId);
            }
        } else {
            showToast(data.error || "Failed to delete comment.", "error");
        }
    } catch (e) {
        showToast("Error deleting comment: " + e.message, "error");
    }
}

// Delete Cat Photo with Custom Modal Dialog
async function deleteCat(catId, event) {
    if (event) event.stopPropagation();

    const confirmTitle = typeof t === "function" ? (currentLang === "ru" ? "Удаление публикации" : "Delete Cat Photo") : "Delete Cat Photo";
    const confirmMsg = typeof t === "function" ? t("delete_cat_confirm") : "Are you sure you want to delete this cat photo?";
    const confirmBtn = typeof t === "function" ? (currentLang === "ru" ? "Удалить" : "Delete") : "Delete";
    const cancelBtn = typeof t === "function" ? (currentLang === "ru" ? "Отмена" : "Cancel") : "Cancel";

    const confirmed = await showConfirmModal({
        title: confirmTitle,
        message: confirmMsg,
        confirmText: confirmBtn,
        cancelText: cancelBtn,
        danger: true,
        icon: "fa-solid fa-trash-can"
    });

    if (!confirmed) return;

    if (typeof supabaseClient === "undefined" || !supabaseClient) {
        showToast("Supabase client not initialized.", "error");
        return;
    }
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (!session) {
        showToast("Please sign in.", "error");
        return;
    }

    try {
        const res = await fetch(`/api/cats/${catId}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        const data = await res.json();
        if (res.ok) {
            showToast(typeof t === "function" ? t("toast_cat_deleted") : "Cat photo deleted!", "success");
            const card = document.getElementById(`cat-card-${catId}`);
            if (card) {
                card.style.transition = "all 0.3s ease";
                card.style.opacity = "0";
                setTimeout(() => card.remove(), 300);
            }
            if (typeof loadProfile === "function") {
                loadProfile();
            }
        } else {
            showToast(data.error || "Failed to delete cat photo.", "error");
        }
    } catch (e) {
        showToast("Error deleting cat: " + e.message, "error");
    }
}

// ==========================================
// NOTIFICATIONS SYSTEM (REAL-TIME POLLING & DROPDOWN)
// ==========================================
let currentNotifications = [];

function toggleNotificationsDropdown(event) {
    if (event) event.stopPropagation();
    const dropdown = document.getElementById("notifications-dropdown");
    if (!dropdown) return;
    const isHidden = dropdown.classList.contains("hidden");
    if (isHidden) {
        dropdown.classList.remove("hidden");
        fetchNotifications();
    } else {
        dropdown.classList.add("hidden");
    }
}

// Close dropdown when clicking outside
document.addEventListener("click", (e) => {
    const container = document.getElementById("notifications-menu-container");
    const dropdown = document.getElementById("notifications-dropdown");
    if (container && dropdown && !container.contains(e.target)) {
        dropdown.classList.add("hidden");
    }
});

async function fetchNotifications() {
    if (typeof supabaseClient === "undefined" || !supabaseClient) return;
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (!session) return;

    try {
        const res = await fetch("/api/notifications", {
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        if (!res.ok) return;
        const data = await res.json();
        currentNotifications = data.notifications || [];
        const unreadCount = data.unread_count || 0;

        // Update Badge
        const badge = document.getElementById("notifications-badge");
        const unreadPill = document.getElementById("notif-unread-pill");
        
        if (badge) {
            if (unreadCount > 0) {
                badge.innerText = unreadCount > 99 ? '99+' : unreadCount;
                badge.classList.remove("hidden");
            } else {
                badge.classList.add("hidden");
            }
        }

        if (unreadPill) {
            if (unreadCount > 0) {
                const newText = typeof t === "function" ? t("notif_new") : "new";
                unreadPill.innerText = `${unreadCount} ${newText}`;
                unreadPill.classList.remove("hidden");
            } else {
                unreadPill.classList.add("hidden");
            }
        }

        renderNotificationsList();
    } catch (e) {
        console.warn("Notifications fetch error:", e);
    }
}

function renderNotificationsList() {
    const listElem = document.getElementById("notifications-list");
    if (!listElem) return;

    if (currentNotifications.length === 0) {
        const emptyText = typeof t === "function" ? t("notif_empty") : "No notifications yet";
        listElem.innerHTML = `
            <div class="p-8 text-center text-slate-400 space-y-2">
                <i class="fa-solid fa-bell-slash text-2xl opacity-40"></i>
                <p class="text-xs font-medium">${emptyText}</p>
            </div>
        `;
        return;
    }

    listElem.innerHTML = currentNotifications.map(n => {
        let typeIcon = '<i class="fa-solid fa-heart text-rose-500 text-[10px]"></i>';
        let typeBg = 'bg-rose-50';
        if (n.type === 'comment') {
            typeIcon = '<i class="fa-solid fa-comment text-indigo-500 text-[10px]"></i>';
            typeBg = 'bg-indigo-50';
        } else if (n.type === 'reply') {
            typeIcon = '<i class="fa-solid fa-reply text-purple-500 text-[10px]"></i>';
            typeBg = 'bg-purple-50';
        } else if (n.type === 'rank_up') {
            typeIcon = '<i class="fa-solid fa-trophy text-amber-500 text-[10px]"></i>';
            typeBg = 'bg-amber-50';
        }

        const isUnread = !n.is_read;
        const unreadClass = isUnread ? 'bg-indigo-50/40 font-semibold' : 'bg-white';
        const actorAvatar = n.actor_avatar || `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(n.actor_name || 'Cat')}&backgroundColor=b6e3f4,c0aede,d1d4f9`;

        return `
            <div class="p-3.5 flex items-start gap-3 hover:bg-slate-50 transition cursor-pointer ${unreadClass} group" onclick="handleNotificationClick('${n.id}', '${n.cat_id || ''}')">
                <div class="relative flex-shrink-0">
                    <img src="${actorAvatar}" alt="Avatar" onerror="handleAvatarError(this, '${escapeHtml(n.actor_name || 'Cat')}')" class="w-9 h-9 rounded-full border border-slate-200 object-cover bg-slate-50 shadow-xs">
                    <div class="absolute -bottom-1 -right-1 w-4 h-4 rounded-full ${typeBg} border border-white flex items-center justify-center shadow-xs">
                        ${typeIcon}
                    </div>
                </div>
                
                <div class="flex-grow min-w-0 pr-1">
                    <p class="text-xs text-slate-800 leading-snug">
                        <strong class="font-bold text-slate-900">${escapeHtml(n.actor_name || 'Cat Lover')}</strong>
                        <span class="text-slate-600 font-normal"> ${escapeHtml(n.message)}</span>
                    </p>
                    <span class="text-[10px] text-slate-400 font-normal mt-0.5 inline-block">${timeAgo(n.created_at)}</span>
                </div>

                ${n.cat_image ? `
                    <div class="w-9 h-9 rounded-xl overflow-hidden border border-slate-200 bg-slate-100 flex-shrink-0 shadow-xs">
                        <img src="${n.cat_image}" alt="Cat" class="w-full h-full object-cover">
                    </div>
                ` : ''}

                <div class="flex items-center gap-1 flex-shrink-0 self-center">
                    ${isUnread ? '<span class="w-2 h-2 rounded-full bg-indigo-600 flex-shrink-0"></span>' : ''}
                    <button onclick="event.stopPropagation(); deleteNotification('${n.id}');" class="text-slate-300 hover:text-rose-600 p-1 text-xs opacity-0 group-hover:opacity-100 transition" title="Delete notification">
                        <i class="fa-solid fa-xmark"></i>
                    </button>
                </div>
            </div>
        `;
    }).join("");
}

async function handleNotificationClick(notifId, catId) {
    if (typeof supabaseClient === "undefined" || !supabaseClient) return;
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (!session) return;

    try {
        await fetch(`/api/notifications/${notifId}/read`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        const n = currentNotifications.find(x => x.id === notifId);
        if (n) n.is_read = true;
        fetchNotifications();
    } catch (e) {
        console.warn("Read notification error:", e);
    }

    const dropdown = document.getElementById("notifications-dropdown");
    if (dropdown) dropdown.classList.add("hidden");

    if (catId) {
        openCatModal(catId);
    }
}

async function markAllNotificationsRead() {
    if (typeof supabaseClient === "undefined" || !supabaseClient) return;
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (!session) return;

    try {
        await fetch("/api/notifications/read-all", {
            method: "POST",
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        showToast(typeof t === "function" ? t("toast_all_notifs_read") : "All notifications marked as read", "success");
        fetchNotifications();
    } catch (e) {
        console.warn("Mark all read error:", e);
    }
}

async function deleteNotification(notifId) {
    if (typeof supabaseClient === "undefined" || !supabaseClient) return;
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (!session) return;

    try {
        await fetch(`/api/notifications/${notifId}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        currentNotifications = currentNotifications.filter(x => x.id !== notifId);
        renderNotificationsList();
        fetchNotifications();
    } catch (e) {
        console.warn("Delete notif error:", e);
    }
}

async function clearAllNotifications() {
    if (typeof supabaseClient === "undefined" || !supabaseClient) return;
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (!session) return;

    try {
        await fetch("/api/notifications/clear-all", {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        showToast(typeof t === "function" ? t("toast_notifs_cleared") : "All notifications cleared", "info");
        currentNotifications = [];
        renderNotificationsList();
        fetchNotifications();
    } catch (e) {
        console.warn("Clear notifications error:", e);
    }
}

// Background polling every 30s
setInterval(() => {
    if (currentSession) {
        fetchNotifications();
    }
}, 30000);

// Close modal on ESC key
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        closeCatModal();
    }
});

// Close modal on outside click
document.addEventListener("click", (e) => {
    const modal = document.getElementById("cat-detail-modal");
    if (modal && e.target === modal) {
        closeCatModal();
    }
});
