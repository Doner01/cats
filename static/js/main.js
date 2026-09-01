const pendingLikes = new Set();
let modalRequestVersion = 0;
let lastCommentTime = 0;
const COOLDOWN_MS = 2000; // 2s anti-spam cooldown

let activeModalCatId = null;
let activeModalBio = '';
let activeReplyParentId = null;
let activeReplyAuthorName = null;
const userLikedCatIds = new Set();

function getModalCatIds() {
    const ids = [];
    const seen = new Set();
    document.querySelectorAll("[data-cat-modal-id]").forEach(element => {
        const id = String(element.dataset.catModalId || "").trim();
        if (id && !seen.has(id)) {
            seen.add(id);
            ids.push(id);
        }
    });
    return ids;
}

function updateModalNavigation() {
    const previousButton = document.getElementById("modal-prev-cat");
    const nextButton = document.getElementById("modal-next-cat");
    const ids = getModalCatIds();
    const canNavigate = Boolean(activeModalCatId) && ids.length > 1 && ids.includes(String(activeModalCatId));
    const previousLabel = typeof t === "function" ? t("previous_cat") : "Previous cat";
    const nextLabel = typeof t === "function" ? t("next_cat") : "Next cat";

    [previousButton, nextButton].forEach(button => {
        if (button) button.classList.toggle("hidden", !canNavigate);
    });
    if (previousButton) {
        previousButton.title = previousLabel;
        previousButton.setAttribute("aria-label", previousLabel);
    }
    if (nextButton) {
        nextButton.title = nextLabel;
        nextButton.setAttribute("aria-label", nextLabel);
    }
}

function navigateCatModal(direction) {
    const ids = getModalCatIds();
    if (!activeModalCatId || ids.length < 2) return;
    const currentIndex = ids.indexOf(String(activeModalCatId));
    if (currentIndex < 0) return;
    const nextIndex = (currentIndex + direction + ids.length) % ids.length;
    if (ids[nextIndex] !== String(activeModalCatId)) return openCatModal(ids[nextIndex]);
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

function escapeJsString(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\r/g, '\\r')
        .replace(/\n/g, '\\n');
}

function formatCommentText(rawComment) {
    if (!rawComment) return { text: '', replyTo: null };
    let text = String(rawComment);
    let replyTo = null;

    if (text.startsWith("[reply:")) {
        const endIdx = text.indexOf("]");
        if (endIdx !== -1) {
            const tagContent = text.substring(7, endIdx);
            const parts = tagContent.split(":");
            replyTo = parts.length > 1 ? parts[1].trim() : parts[0].trim();
            text = text.substring(endIdx + 1).trim();
        }
    }
    return { text: text, replyTo: replyTo };
}

function resetCatModalState() {
    activeModalBio = '';
    closeCatBio();
    document.getElementById('modal-bio-more')?.classList.add('hidden');
    const modalNameElem = document.getElementById("modal-cat-name");
    const modalImgElem = document.getElementById("modal-cat-img");
    const bioBox = document.getElementById("modal-cat-bio-box");
    const bioText = document.getElementById("modal-cat-bio-text");
    const commentsList = document.getElementById("modal-comments-items");
    const commentsCount = document.getElementById("modal-comments-count");
    const countBadge = document.getElementById("modal-comments-count-badge");
    const commentInput = document.getElementById("modal-comment-input");
    const modalLikeCount = document.getElementById("modal-like-count");
    const modalHeartIcon = document.getElementById("modal-heart-icon");

    if (modalNameElem) modalNameElem.innerText = "";
    if (modalImgElem) {
        modalImgElem.src = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100' fill='%231e293b'></svg>";
    }
    if (bioBox) bioBox.classList.add("hidden");
    if (bioText) bioText.innerText = "";
    const commentsScroll = document.getElementById("modal-comments-list");
    if (commentsScroll) commentsScroll.scrollTop = 0;
    document.getElementById("modal-owner-link")?.classList.add("hidden");
    const date = document.getElementById("modal-cat-date");
    if (date) date.textContent = "";
    if (commentsList) {
        const loadingText = typeof t === 'function' ? t('loading_comments') : 'Loading comments...';
        commentsList.innerHTML = `<div class="py-10 text-center text-slate-400"><i class="fa-solid fa-spinner fa-spin text-base text-indigo-500 mb-2"></i><p class="text-xs font-medium">${loadingText}</p></div>`;
    }
    if (commentsCount) commentsCount.innerText = "(0)";
    if (countBadge) {
        const label = typeof t === 'function' ? (currentLang === 'ru' ? 'комментариев' : 'comments') : 'comments';
        countBadge.innerText = `0 ${label}`;
    }
    if (modalLikeCount) modalLikeCount.innerText = "0";
    if (modalHeartIcon) modalHeartIcon.innerText = "🤍";
    if (commentInput) commentInput.value = "";
    cancelReply();
}

async function openCatModal(catId) {
    if (!catId) return;
    activeModalCatId = String(catId);
    const requestVersion = ++modalRequestVersion;

    resetCatModalState();

    const modal = document.getElementById("cat-detail-modal");
    if (!modal) return;

    const content = document.getElementById("cat-detail-scroll");
    if (content) content.scrollTop = 0;
    modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
    updateModalNavigation();
    updateModalAuth();
    if (typeof updateFavoriteButtons === 'function') updateFavoriteButtons();
    const card = document.querySelector(`[data-cat-id="${catId}"]`);
    const countElem = document.getElementById(`like-count-${catId}`);
    const heartElem = document.getElementById(`heart-icon-${catId}`);
    const modalNameElem = document.getElementById("modal-cat-name");
    const modalImgElem = document.getElementById("modal-cat-img");
    const modalLikeCount = document.getElementById("modal-like-count");
    const modalHeartIcon = document.getElementById("modal-heart-icon");

    if (card) {
        const cardName = card.dataset.catName;
        const cardImg = card.querySelector(".cat-open img") || card.querySelector("img");
        if (cardName && modalNameElem) modalNameElem.innerText = cardName;
        if (cardImg && cardImg.src && modalImgElem) modalImgElem.src = cardImg.src;
    } else {
        if (modalNameElem) modalNameElem.innerText = typeof t === "function" && currentLang === "ru" ? "Загрузка..." : "Loading...";
    }

    if (countElem && modalLikeCount) {
        modalLikeCount.innerText = countElem.innerText.trim() || "0";
    }
    if (modalHeartIcon) {
        const isLiked = userLikedCatIds.has(String(catId)) || (heartElem && heartElem.innerText.trim() === "❤️");
        modalHeartIcon.innerText = isLiked ? "❤️" : "🤍";
    }
    try {
        const res = await fetch(`/api/cats/${catId}`);
        if (res.ok) {
            const data = await res.json();
            if (requestVersion !== modalRequestVersion) return;
            const cat = data.cat || data;
            if (modalNameElem) modalNameElem.innerText = cat.name || "Whiskers";
            if (modalImgElem) modalImgElem.src = cat.image_url || "";
            if (modalImgElem) modalImgElem.alt = cat.name || "Cat";
            updateModalOwner(cat);
            if (modalLikeCount) modalLikeCount.innerText = cat.likes_count !== undefined ? cat.likes_count : 0;
            if (modalHeartIcon) {
                modalHeartIcon.innerText = userLikedCatIds.has(String(catId)) ? "❤️" : "🤍";
            }

            const catBio = String(cat.bio || cat.description || "").trim();
            const bioBox = document.getElementById("modal-cat-bio-box");
            const bioText = document.getElementById("modal-cat-bio-text");
            if (catBio && bioBox && bioText) {
                activeModalBio = String(catBio).trim();
                bioText.textContent = activeModalBio.replace(/\s+/g, ' ');
                bioBox.classList.remove("hidden");
                if (typeof requestAnimationFrame === 'function') requestAnimationFrame(updateCatBioPreview);
                else updateCatBioPreview();
            }
        } else {
            if (requestVersion !== modalRequestVersion) return;
            showToast("Could not load this cat. Please try again.", "error");
        }
    } catch (err) {
        if (requestVersion === modalRequestVersion) showToast("Could not load this cat. Please try again.", "error");
    }
    if (requestVersion === modalRequestVersion) loadCatComments(catId);
}

function closeCatModal() {
    const modal = document.getElementById("cat-detail-modal");
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.style.overflow = "auto";
    activeModalCatId = null;
    modalRequestVersion++;
    resetCatModalState();
    updateModalNavigation();
    window.dispatchEvent(new CustomEvent('catrank_viewer_closed'));
}

function setCatBioExpanded(expanded) {
    const text = document.getElementById('modal-cat-bio-text');
    const button = document.getElementById('modal-bio-more');
    if (!text || !button) return;

    const shouldExpand = Boolean(expanded && activeModalBio);
    text.classList.toggle('is-expanded', shouldExpand);
    if (!shouldExpand) text.scrollTop = 0;

    button.setAttribute('aria-expanded', shouldExpand ? 'true' : 'false');
    const key = shouldExpand ? 'show_less_bio' : 'read_full_bio';
    button.setAttribute('data-i18n', key);
    button.textContent = typeof t === 'function'
        ? t(key)
        : (shouldExpand ? 'Show less' : 'Read full bio');
}

function updateCatBioPreview() {
    const text = document.getElementById('modal-cat-bio-text');
    const button = document.getElementById('modal-bio-more');
    if (!text || !button) return;

    const isExpanded = text.classList.contains('is-expanded');
    if (isExpanded) {
        button.classList.toggle('hidden', !activeModalBio);
        return;
    }

    button.classList.toggle('hidden', !activeModalBio || text.scrollHeight <= text.clientHeight + 1);
}

function toggleCatBio() {
    if (!activeModalCatId || !activeModalBio) return;
    const text = document.getElementById('modal-cat-bio-text');
    if (!text) return;
    setCatBioExpanded(!text.classList.contains('is-expanded'));
}

// Keep these names as compatibility helpers for any older cached markup/scripts.
function openCatBio() {
    if (!activeModalCatId || !activeModalBio) return;
    setCatBioExpanded(true);
}

function closeCatBio() {
    setCatBioExpanded(false);
}

function getCatLoginUrl(catId = activeModalCatId) {
    const destination = new URL(window.location.href);
    if (catId) destination.searchParams.set('cat', String(catId));
    return '/login?next=' + encodeURIComponent(destination.pathname + destination.search + destination.hash);
}

function updateModalAuth() {
    const signedIn = typeof currentSession !== 'undefined' && Boolean(currentSession?.user);
    document.getElementById('modal-comment-form')?.classList.toggle('hidden', !signedIn);
    document.getElementById('modal-login-prompt')?.classList.toggle('hidden', signedIn);
    const login = document.getElementById('modal-login-link');
    if (login) login.href = getCatLoginUrl();
    if (!signedIn) cancelReply();
}

function updateModalOwner(cat) {
    const link = document.getElementById('modal-owner-link');
    const name = document.getElementById('modal-owner-name');
    const avatar = document.getElementById('modal-owner-avatar');
    if (link && cat.user_id) {
        link.href = '/user/' + encodeURIComponent(cat.user_id);
        link.classList.remove('hidden');
        if (name) name.textContent = cat.user_name || 'Cat Lover';
        if (avatar) {
            avatar.onerror = () => handleAvatarError(avatar, cat.user_name || 'Cat Lover');
            avatar.src = safeImageUrl(cat.user_avatar, cat.user_name || 'Cat Lover');
        }
    }
    const date = document.getElementById('modal-cat-date');
    if (date) {
        date.textContent = String(cat.created_at || '').slice(0, 10);
        date.dateTime = cat.created_at || '';
    }
}

function likeModalPhoto(event) {
    event?.stopPropagation();
    if (activeModalCatId && !userLikedCatIds.has(String(activeModalCatId))) toggleLike(activeModalCatId, event);
}

const catDetailModalElem = document.getElementById("cat-detail-modal");
if (catDetailModalElem) {
    catDetailModalElem.addEventListener("click", (e) => {
        if (e.target === catDetailModalElem) closeCatModal();
    });
}

document.addEventListener("keydown", event => {
    if (!activeModalCatId || !catDetailModalElem || catDetailModalElem.classList.contains("hidden")) return;
    const confirmation = document.getElementById("custom-confirm-modal");
    if (confirmation && !confirmation.classList.contains("hidden")) return;
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const target = event.target;
    if (target && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        navigateCatModal(event.key === "ArrowLeft" ? -1 : 1);
    }
});

function toggleModalLike(event) {
    if (event) event.stopPropagation();
    if (activeModalCatId) {
        toggleLike(activeModalCatId, event);
    }
}

async function syncUserLikes() {
    if (!currentSession || !currentSession.access_token) return;
    try {
        const res = await fetch("/api/user/liked-cats", {
            headers: { "Authorization": `Bearer ${currentSession.access_token}` }
        });
        if (!res.ok) return;
        const data = await res.json();
        userLikedCatIds.clear();
        (data.liked_cat_ids || []).forEach(id => userLikedCatIds.add(String(id)));

        document.querySelectorAll('[id^="heart-icon-"]').forEach(heart => {
            const id = heart.id.slice('heart-icon-'.length);
            const liked = userLikedCatIds.has(id);
            heart.innerText = liked ? "❤️" : "🤍";
            document.getElementById(`like-btn-${id}`)?.setAttribute('aria-pressed', String(liked));
        });

        if (activeModalCatId) {
            const modalHeart = document.getElementById("modal-heart-icon");
            if (modalHeart) modalHeart.innerText = userLikedCatIds.has(String(activeModalCatId)) ? "❤️" : "🤍";
        }
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

    const { data: { session } } = await supabaseClient.auth.getSession();
    if (!session) {
        showToast(typeof t === "function" ? t("toast_need_signin_vote") : "Please sign in to vote for cats!", "info");
        setTimeout(() => window.location.href = getCatLoginUrl(catId), 800);
        return;
    }

    if (pendingLikes.has(String(catId))) return;
    pendingLikes.add(String(catId));
    const countElem = document.getElementById(`like-count-${catId}`);
    const heartElem = document.getElementById(`heart-icon-${catId}`);
    const modalCount = document.getElementById("modal-like-count");
    const modalHeart = document.getElementById("modal-heart-icon");

    const isModal = String(activeModalCatId) === String(catId);
    const isCurrentlyLiked = userLikedCatIds.has(String(catId)) || (heartElem ? heartElem.innerText === "❤️" : (isModal && modalHeart ? modalHeart.innerText === "❤️" : false));
    const prevCount = parseInt(isModal && modalCount ? modalCount.innerText : (countElem ? countElem.innerText : "0"), 10) || 0;

    const nextLiked = !isCurrentlyLiked;
    const nextCount = nextLiked ? prevCount + 1 : Math.max(0, prevCount - 1);

    if (nextLiked) userLikedCatIds.add(String(catId));
    else userLikedCatIds.delete(String(catId));

    if (heartElem) heartElem.innerText = nextLiked ? "❤️" : "🤍";
    if (countElem) countElem.innerText = nextCount;
    if (modalHeart && String(activeModalCatId) === String(catId)) modalHeart.innerText = nextLiked ? "❤️" : "🤍";
    if (modalCount && String(activeModalCatId) === String(catId)) modalCount.innerText = nextCount;
    if (nextLiked && String(activeModalCatId) === String(catId)) {
        const heartBurst = document.getElementById("double-click-heart");
        if (heartBurst) {
            heartBurst.classList.remove("hidden");
            setTimeout(() => heartBurst.classList.add("hidden"), 700);
        }
    }

    try {
        const res = await fetch(`/api/cats/${catId}/like`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        const data = await res.json();
        if (res.ok) {
            const serverLiked = data.status === "liked";
            if (serverLiked) userLikedCatIds.add(String(catId));
            else userLikedCatIds.delete(String(catId));

            if (countElem) countElem.innerText = data.likes_count;
            if (heartElem) heartElem.innerText = serverLiked ? "❤️" : "🤍";
            if (modalHeart && String(activeModalCatId) === String(catId)) modalHeart.innerText = serverLiked ? "❤️" : "🤍";
            if (modalCount && String(activeModalCatId) === String(catId)) modalCount.innerText = data.likes_count;
            document.getElementById(`like-btn-${catId}`)?.setAttribute('aria-pressed', String(serverLiked));
            const card = document.querySelector(`[data-cat-id="${catId}"]`);
            if (card) card.dataset.likes = String(data.likes_count);
            document.getElementById('modal-like-btn')?.setAttribute('aria-pressed', String(userLikedCatIds.has(String(activeModalCatId))));
            window.dispatchEvent(new CustomEvent('catrank_like_changed', {detail: {id: String(catId), likes_count: data.likes_count}}));
            showToast(serverLiked ? "Voted!" : "Vote removed", "success");
            if (typeof fetchNotifications === "function") fetchNotifications();
        } else {
            if (isCurrentlyLiked) userLikedCatIds.add(String(catId));
            else userLikedCatIds.delete(String(catId));

            if (countElem) countElem.innerText = prevCount;
            if (heartElem) heartElem.innerText = isCurrentlyLiked ? "❤️" : "🤍";
            if (modalHeart && String(activeModalCatId) === String(catId)) modalHeart.innerText = isCurrentlyLiked ? "❤️" : "🤍";
            if (modalCount && String(activeModalCatId) === String(catId)) modalCount.innerText = prevCount;
            showToast(data.error || "Failed to update vote.", "error");
        }
    } catch (err) {
        if (isCurrentlyLiked) userLikedCatIds.add(String(catId));
        else userLikedCatIds.delete(String(catId));

        if (countElem) countElem.innerText = prevCount;
        if (heartElem) heartElem.innerText = isCurrentlyLiked ? "❤️" : "🤍";
        if (modalHeart && String(activeModalCatId) === String(catId)) modalHeart.innerText = isCurrentlyLiked ? "❤️" : "🤍";
        if (modalCount && String(activeModalCatId) === String(catId)) modalCount.innerText = prevCount;
        showToast("Network error. Please try again.", "error");
    } finally {
        pendingLikes.delete(String(catId));
    }
}

function startReply(commentId, authorName, rootCommentId = null) {
    if (typeof currentSession === 'undefined' || !currentSession?.user) {
        window.location.href = getCatLoginUrl();
        return;
    }
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
        const placeholderText = typeof t === "function" ? t("reply_placeholder") : "Write a reply...";
        input.placeholder = placeholderText;
        input.focus();
    }
}

function cancelReply() {
    activeReplyParentId = null;
    activeReplyAuthorName = null;

    const banner = document.getElementById("modal-reply-banner");
    const input = document.getElementById("modal-comment-input");

    if (banner) banner.classList.add("hidden");
    if (input) {
        input.placeholder = typeof t === "function" ? t("comment_placeholder") : "Add a comment...";
    }
}

async function loadCatComments(catId) {
    const requestVersion = modalRequestVersion;
    try {
        const res = await fetch(`/api/cats/${catId}/comments`);
        const data = await res.json();
        if (String(activeModalCatId) !== String(catId) || requestVersion !== modalRequestVersion) return;
        if (!res.ok) throw new Error(data.error || 'Could not load comments.');
        const comments = data.comments || [];
        const container = document.getElementById("modal-comments-items");
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
            const avatar = escapeHtml(c.user_avatar || `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(authorDisplayName)}&backgroundColor=b6e3f4,c0aede,d1d4f9`);
            const isOwner = currentUserId && String(c.user_id) === String(currentUserId);
            const replies = repliesByParent[String(c.id)] || [];
            const rootId = String(c.id);

            const repliesHtml = replies.map(r => {
                const rAuthorName = r.user_name || "Cat Lover";
                const rUserTarget = r.user_id || r.user_name || '';
                const rAvatar = escapeHtml(r.user_avatar || `https://api.dicebear.com/7.x/bottts/svg?seed=${encodeURIComponent(rAuthorName)}&backgroundColor=b6e3f4,c0aede,d1d4f9`);
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
                                        <button onclick="deleteComment('${r.id}', event)" class="w-6 h-6 rounded-lg bg-slate-100 hover:bg-rose-600 text-slate-400 hover:text-white transition flex items-center justify-center text-xs ml-1 shadow-2xs" title="${deleteBtnText}">
                                            <i class="fa-solid fa-trash-can text-[9px]"></i>
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
                <div class="comment-card p-3.5 rounded-2xl bg-white border border-slate-200 shadow-sm hover:border-slate-300 transition">
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
                                        <button onclick="deleteComment('${c.id}', event)" class="w-7 h-7 rounded-lg bg-slate-100 hover:bg-rose-600 text-slate-400 hover:text-white transition flex items-center justify-center text-xs ml-2 shadow-2xs" title="${deleteBtnText}">
                                            <i class="fa-solid fa-trash-can text-[10px]"></i>
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
        if (String(activeModalCatId) !== String(catId) || requestVersion !== modalRequestVersion) return;
        const container = document.getElementById('modal-comments-items');
        if (container) {
            container.textContent = 'Could not load comments. ';
            const retry = document.createElement('button');
            retry.type = 'button';
            retry.className = 'text-indigo-600 font-bold';
            retry.textContent = 'Try again';
            retry.addEventListener('click', () => loadCatComments(catId));
            container.appendChild(retry);
        }
    }
}

async function submitComment(event) {
    if (event) event.preventDefault();
    const submittedVersion = modalRequestVersion;

    if (typeof supabaseClient === "undefined" || !supabaseClient) {
        showToast("Supabase client not initialized.", "error");
        return;
    }
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (submittedVersion !== modalRequestVersion) return;
    if (!session) {
        showToast(typeof t === "function" ? t("toast_need_signin_comment") : "Please sign in to post comments.", "info");
        setTimeout(() => window.location.href = getCatLoginUrl(), 800);
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
        const cooldownMsg = typeof t === "function" ? t("toast_cooldown", { sec: remaining }) : `Please wait ${remaining}s...`;
        showToast(cooldownMsg, "info");
        return;
    }
    lastCommentTime = now;

    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-xs"></i>';
    }

    const submittedCatId = activeModalCatId;
    const isReply = !!activeReplyParentId;
    const payload = {
        comment: commentText,
        parent_id: activeReplyParentId || null,
        reply_to_name: activeReplyAuthorName || null
    };

    try {
        const res = await fetch(`/api/cats/${submittedCatId}/comments`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${session.access_token}`
            },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            if (activeModalCatId === submittedCatId && submittedVersion === modalRequestVersion) {
                input.value = "";
                cancelReply();
                loadCatComments(submittedCatId);
            }
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

function toggleNotificationsDropdown() {
    const dropdown = document.getElementById("notifications-dropdown");
    if (!dropdown) return;
    dropdown.classList.toggle("hidden");
    if (!dropdown.classList.contains("hidden")) {
        fetchNotifications();
    }
}

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
                const avatar = escapeHtml(n.actor_avatar || getFallbackAvatarSvg(n.actor_name));
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
        const res = await fetch("/api/notifications/read-all", {
            method: "POST",
            headers: { "Authorization": `Bearer ${currentSession.access_token}` }
        });
        if (!res.ok) throw new Error('Could not mark notifications read.');
        fetchNotifications();
    } catch (e) {
        showToast(e.message, "error");
    }
}

window.addEventListener("catrank_language_changed", () => {
    updateModalAuth();
    updateModalNavigation();
    if (activeModalCatId) {
        loadCatComments(activeModalCatId);
    }
});

document.addEventListener('DOMContentLoaded', () => {
    const bioText = document.getElementById('modal-cat-bio-text');
    if (bioText && typeof ResizeObserver !== 'undefined') {
        new ResizeObserver(updateCatBioPreview).observe(bioText);
    }
    const catId = new URLSearchParams(window.location.search).get('cat');
    if (catId && /^[a-zA-Z0-9_-]{1,64}$/.test(catId)) openCatModal(catId);
});
window.addEventListener('resize', updateCatBioPreview);
