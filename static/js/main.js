const pendingLikes = new Map();
let modalRequestVersion = 0;
let lastCommentTime = 0;
const COOLDOWN_MS = 2000; // 2s anti-spam cooldown

let activeModalCatId = null;
let commentsRequestVersion = 0;
let loadedComments = [];
let nextCommentsCursor = null;
let commentsTotal = 0;
let commentsLoading = false;
let activeModalBio = '';
let activeReplyParentId = null;
let activeReplyAuthorName = null;
let serverClockOffsetMs = 0;
let commentEditExpiryTimer = null;
const userLikedCatIds = new Set();
let viewerAccountEpoch = 0;
let likedCatsRequestVersion = 0;
let likedCatsSync = null;

function resetPrivateViewerState() {
    viewerAccountEpoch++;
    likedCatsRequestVersion++;
    likedCatsSync = null;
    userLikedCatIds.clear();
    pendingLikes.clear();
    document.querySelectorAll('[id^="heart-icon-"]').forEach(heart => {
        heart.innerText = '🤍';
        document.getElementById(`like-btn-${heart.id.slice('heart-icon-'.length)}`)?.setAttribute('aria-pressed', 'false');
    });
    const modalHeart = document.getElementById('modal-heart-icon');
    if (modalHeart) modalHeart.innerText = '🤍';
    document.getElementById('modal-like-btn')?.setAttribute('aria-pressed', 'false');
    notificationsRequestVersion++;
    notificationsFetchTask = null;
    notificationsCache = [];
    notificationsUnreadCount = 0;
    closeNotificationsDropdown();
    renderNotifications();
    closeCommentEditModal();
    cancelReply();
}

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


function setModalCatImage(src, altText = 'Cat') {
    const image = document.getElementById('modal-cat-img');
    const media = document.querySelector('.cat-detail-media');
    const url = String(src || '').trim();

    if (image) {
        image.src = url || "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100' fill='%23e2e8f0'></svg>";
        image.alt = String(altText || 'Cat');
    }

    if (!media) return;
    if (!url || url.startsWith('data:image/svg+xml')) {
        media.style.removeProperty('--cat-blur-image');
        media.classList.remove('has-photo');
        return;
    }

    const cssUrl = url.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/[\r\n]/g, '');
    media.style.setProperty('--cat-blur-image', `url("${cssUrl}")`);
    media.classList.add('has-photo');
}

function resetCatModalState() {
    closeCommentEditModal();
    commentsRequestVersion++;
    if (commentEditExpiryTimer) clearTimeout(commentEditExpiryTimer);
    commentEditExpiryTimer = null;
    loadedComments = [];
    nextCommentsCursor = null;
    commentsTotal = 0;
    commentsLoading = false;
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
        setModalCatImage('', 'Cat');
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
    catId = String(catId);
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
    const card = document.querySelector(`[data-cat-id="${CSS.escape(catId)}"]`);
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
        if (cardImg && cardImg.src && modalImgElem) setModalCatImage(cardImg.src, cardName || 'Cat');
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
        const res = await fetch(`/api/cats/${encodeURIComponent(catId)}`);
        if (res.ok) {
            const data = await res.json();
            if (requestVersion !== modalRequestVersion) return;
            const cat = data.cat || data;
            if (modalNameElem) modalNameElem.innerText = cat.name || "Whiskers";
            if (modalImgElem) setModalCatImage(cat.image_url || "", cat.name || "Cat");
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
    if (requestVersion === modalRequestVersion) await loadCatComments(catId);
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
    text.textContent = shouldExpand ? activeModalBio : activeModalBio.replace(/\s+/g, ' ');
    text.classList.toggle('is-expanded', shouldExpand);
    text.setAttribute('tabindex', shouldExpand && text.scrollHeight > text.clientHeight + 1 ? '0' : '-1');
    document.getElementById('modal-cat-bio-box')?.classList.toggle('is-expanded', shouldExpand);
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
        text.setAttribute('tabindex', text.scrollHeight > text.clientHeight + 1 ? '0' : '-1');
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
    updateCatBioPreview();
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
    const session = currentSession;
    if (!session?.access_token) return;
    if (likedCatsSync) return likedCatsSync;
    const epoch = viewerAccountEpoch;
    const version = ++likedCatsRequestVersion;
    const task = (async () => { try {
        const res = await fetch("/api/user/liked-cats", {
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        if (!res.ok) return;
        const data = await res.json();
        if (epoch !== viewerAccountEpoch || version !== likedCatsRequestVersion || session.user?.id !== currentSession?.user?.id) return;
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
    } })();
    likedCatsSync = task;
    try { return await task; }
    finally { if (likedCatsSync === task) likedCatsSync = null; }
}

async function toggleLike(catId, event) {
    if (event) event.stopPropagation();
    catId = String(catId || '');
    if (!catId || pendingLikes.has(catId)) return;

    if (typeof supabaseClient === "undefined" || !supabaseClient) {
        showToast("Supabase client not initialized.", "error");
        return;
    }

    const epoch = viewerAccountEpoch;
    const mutation = Symbol(catId);
    pendingLikes.set(catId, mutation);
    const releasePending = () => {
        if (pendingLikes.get(catId) === mutation) pendingLikes.delete(catId);
    };
    let session;
    try {
        const result = await supabaseClient.auth.getSession();
        session = result?.data?.session;
    } catch (_) {
        releasePending();
        showToast('Could not check your session. Please try again.', 'error');
        return;
    }
    if (epoch !== viewerAccountEpoch || (session && session.user?.id !== currentSession?.user?.id)) {
        releasePending();
        return;
    }
    if (!session) {
        releasePending();
        showToast(typeof t === "function" ? t("toast_need_signin_vote") : "Please sign in to vote for cats!", "info");
        setTimeout(() => window.location.href = getCatLoginUrl(catId), 800);
        return;
    }

    // A snapshot started before this mutation must not overwrite the vote.
    likedCatsRequestVersion++;
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
        const res = await fetch(`/api/cats/${encodeURIComponent(catId)}/like`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        const data = await res.json();
        if (epoch !== viewerAccountEpoch || session.user?.id !== currentSession?.user?.id) return;
        if (res.ok) {
            const serverLiked = data.status === "liked";
            if (serverLiked) userLikedCatIds.add(String(catId));
            else userLikedCatIds.delete(String(catId));

            if (countElem) countElem.innerText = data.likes_count;
            if (heartElem) heartElem.innerText = serverLiked ? "❤️" : "🤍";
            if (modalHeart && String(activeModalCatId) === String(catId)) modalHeart.innerText = serverLiked ? "❤️" : "🤍";
            if (modalCount && String(activeModalCatId) === String(catId)) modalCount.innerText = data.likes_count;
            document.getElementById(`like-btn-${catId}`)?.setAttribute('aria-pressed', String(serverLiked));
            const card = document.querySelector(`[data-cat-id="${CSS.escape(catId)}"]`);
            if (card) card.dataset.likes = String(data.likes_count);
            document.getElementById('modal-like-btn')?.setAttribute('aria-pressed', String(userLikedCatIds.has(String(activeModalCatId))));
            window.dispatchEvent(new CustomEvent('catrank_like_changed', {detail: {id: String(catId), likes_count: data.likes_count}}));
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
        if (epoch !== viewerAccountEpoch || session.user?.id !== currentSession?.user?.id) return;
        if (isCurrentlyLiked) userLikedCatIds.add(String(catId));
        else userLikedCatIds.delete(String(catId));

        if (countElem) countElem.innerText = prevCount;
        if (heartElem) heartElem.innerText = isCurrentlyLiked ? "❤️" : "🤍";
        if (modalHeart && String(activeModalCatId) === String(catId)) modalHeart.innerText = isCurrentlyLiked ? "❤️" : "🤍";
        if (modalCount && String(activeModalCatId) === String(catId)) modalCount.innerText = prevCount;
        showToast("Network error. Please try again.", "error");
    } finally {
        if (epoch === viewerAccountEpoch) likedCatsRequestVersion++;
        releasePending();
    }
}

function startReply(commentId, authorName, rootCommentId = null) {
    if (typeof currentSession === 'undefined' || !currentSession?.user) {
        window.location.href = getCatLoginUrl();
        return;
    }
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

const COMMENT_EDIT_WINDOW_MS = 2 * 60 * 1000;

function commentEditDeadline(comment) {
    const created = Date.parse(String(comment?.created_at || ''));
    return Number.isFinite(created) ? created + COMMENT_EDIT_WINDOW_MS : Number.POSITIVE_INFINITY;
}

function commentCanBeEdited(comment) {
    return commentEditDeadline(comment) > Date.now() + serverClockOffsetMs;
}

function renderCommentEditControl(comment) {
    const id = escapeHtml(comment?.id || '');
    const actionId = escapeJsString(comment?.id || '');
    const allowed = commentCanBeEdited(comment);
    const title = allowed ? '' : (typeof t === 'function' ? t('comment_edit_expired') : 'Editing is available for two minutes after posting.');
    const label = typeof t === 'function' ? t('edit_btn') : 'Edit';
    return `<button type="button" data-edit-comment-id="${id}" ${allowed ? `onclick="editComment('${actionId}')"` : 'disabled aria-disabled="true"'} class="comment-action-button comment-edit-button ${allowed ? '' : 'is-disabled'}" title="${escapeHtml(title)}"><i class="fa-regular fa-pen-to-square" aria-hidden="true"></i><span>${escapeHtml(label)}</span></button>`;
}

function renderCommentLikeControl(comment) {
    const id = escapeHtml(comment?.id || '');
    const actionId = escapeJsString(comment?.id || '');
    const count = Math.max(0, Number(comment?.likes_count) || 0);
    const label = typeof t === 'function' ? t('like_comment') : 'Like comment';
    return `<button type="button" class="comment-action-button comment-like-button" data-comment-like-id="${id}" data-comment-like-count="${count}" aria-pressed="false" aria-label="${escapeHtml(label)}" onclick="toggleCommentLike('${actionId}', event)"><span data-comment-like-icon aria-hidden="true">♡</span><span data-comment-like-count>${count}</span></button>`;
}

function updateCommentEditControls() {
    const commentsById = new Map(loadedComments.map(comment => [String(comment.id), comment]));
    document.querySelectorAll('[data-edit-comment-id]').forEach(button => {
        const comment = commentsById.get(String(button.dataset.editCommentId));
        if (!comment) return;
        const allowed = commentCanBeEdited(comment);
        button.disabled = !allowed;
        button.setAttribute('aria-disabled', String(!allowed));
        button.classList.toggle('is-disabled', !allowed);
        button.title = allowed ? '' : (typeof t === 'function' ? t('comment_edit_expired') : 'Editing is available for two minutes after posting.');
    });
}

function scheduleCommentEditExpiry() {
    if (commentEditExpiryTimer) clearTimeout(commentEditExpiryTimer);
    const now = Date.now() + serverClockOffsetMs;
    const deadlines = loadedComments.map(commentEditDeadline).filter(Number.isFinite).filter(deadline => deadline > now);
    if (!deadlines.length) {
        updateCommentEditControls();
        return;
    }
    const delay = Math.max(50, Math.min(60 * 1000, Math.min(...deadlines) - now + 25));
    commentEditExpiryTimer = setTimeout(() => {
        updateCommentEditControls();
        scheduleCommentEditExpiry();
    }, delay);
}

async function loadCatComments(catId, append = false, posted = null) {
    if (append && (commentsLoading || !nextCommentsCursor)) return;
    const requestVersion = modalRequestVersion;
    const commentsVersion = ++commentsRequestVersion;
    commentsLoading = true;
    const cursor = append ? nextCommentsCursor : null;
    try {
        const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : '';
        const res = await fetch(`/api/cats/${encodeURIComponent(catId)}/comments${query}`);
        const data = await res.json();
        if (String(activeModalCatId) !== String(catId) || requestVersion !== modalRequestVersion || commentsVersion !== commentsRequestVersion) return;
        if (!res.ok) throw new Error(data.error || 'Could not load comments.');
        const serverTime = Date.parse(String(data.server_time || ''));
        if (Number.isFinite(serverTime)) serverClockOffsetMs = serverTime - Date.now();
        const incoming = data.comments || [];
        // Comments are chronological: oldest at the top, newest at the bottom.
        // A just-posted comment/reply must be appended, never prepended.
        const combined = append ? [...loadedComments, ...incoming] : (posted ? [...incoming, posted] : incoming);
        loadedComments = Array.from(new Map(combined.map(c => [String(c.id), c])).values());

        // Keep a deterministic chronological order even if the API/cache returns
        // rows in an unexpected order.
        loadedComments.sort((a, b) => {
            const aTime = Date.parse(String(a.created_at || '')) || 0;
            const bTime = Date.parse(String(b.created_at || '')) || 0;
            if (aTime !== bTime) return aTime - bTime;
            return String(a.id || '').localeCompare(String(b.id || ''));
        });
        nextCommentsCursor = data.next_cursor || null;
        if (Number.isFinite(data.total)) commentsTotal = data.total;
        else if (!append) commentsTotal = loadedComments.length;
        const comments = loadedComments;
        const container = document.getElementById("modal-comments-items");
        const countElem = document.getElementById("modal-comments-count");
        const countBadge = document.getElementById("modal-comments-count-badge");

        if (countElem) countElem.innerText = `(${commentsTotal})`;
        if (countBadge) {
            const label = typeof t === "function" ? (currentLang === 'ru' ? "комментариев" : "comments") : "comments";
            countBadge.innerText = `${commentsTotal} ${label}`;
        }

        if (!container) return;
        closeCommentEditModal();

        if (comments.length === 0) {
            const noCommentsText = typeof t === "function" ? t("no_comments") : "No comments yet. Be the first to say something nice!";
            container.innerHTML = `
                <div class="py-10 text-center text-slate-400 space-y-2">
                    <i class="fa-regular fa-comment-dots text-3xl text-slate-300"></i>
                    <p class="text-xs font-medium">${noCommentsText}</p>
                </div>
            `;
            if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
                window.dispatchEvent(new CustomEvent('catrank_comments_rendered', {detail: {catId: String(catId), commentIds: []}}));
            }
            scheduleCommentEditExpiry();
            return;
        }

        let currentUserId = null;
        if (typeof currentSession !== "undefined" && currentSession && currentSession.user) {
            currentUserId = currentSession.user.id;
        }

        const rootComments = [];
        const repliesByParent = Object.create(null);
        const allCommentIds = new Set(comments.map(c => String(c.id)));
        const commentsById = new Map(comments.map(c => [String(c.id), c]));

        comments.forEach(c => {
            const rawPid = c.parent_id;
            let pid = (rawPid && String(rawPid).trim() !== "" && String(rawPid).trim().toLowerCase() !== "null" && String(rawPid).trim().toLowerCase() !== "none" && String(rawPid).trim().toLowerCase() !== "undefined") ? String(rawPid).trim() : null;
            
            const seen = new Set([String(c.id)]);
            while (pid && commentsById.has(pid) && commentsById.get(pid).parent_id) {
                if (seen.has(pid)) { pid = null; break; }
                seen.add(pid);
                const ancestor = String(commentsById.get(pid).parent_id);
                if (!commentsById.has(ancestor)) break;
                pid = ancestor;
            }
            if (pid && allCommentIds.has(pid) && pid !== String(c.id)) {
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

        container.innerHTML = rootComments.map(c => {
            const authorDisplayName = c.user_name || "Cat Lover";
            const userTarget = c.user_id || c.user_name || '';
            const avatar = escapeHtml(safeImageUrl(c.user_avatar, authorDisplayName));
            const isOwner = currentUserId && String(c.user_id) === String(currentUserId);
            const replies = repliesByParent[String(c.id)] || [];
            const rootId = escapeJsString(c.id);

            const repliesHtml = replies.map(r => {
                const rAuthorName = r.user_name || "Cat Lover";
                const rUserTarget = r.user_id || r.user_name || '';
                const rAvatar = escapeHtml(safeImageUrl(r.user_avatar, rAuthorName));
                const replyId = escapeJsString(r.id);
                const rIsOwner = currentUserId && String(r.user_id) === String(currentUserId);
                const safeRAuthorName = escapeHtml(rAuthorName);
                const jsSafeRAuthorName = escapeJsString(rAuthorName);
                const rawReplyTarget = String(r.reply_to_name || authorDisplayName).trim();
                const replyTarget = escapeHtml(rawReplyTarget);
                const isDirectReplyToRoot = rawReplyTarget.toLowerCase() === String(authorDisplayName).trim().toLowerCase();
                const replyContextHtml = isDirectReplyToRoot ? '' : `
                    <div class="comment-reply-context"><i class="fa-solid fa-turn-up" aria-hidden="true"></i><span><strong>@${replyTarget}</strong></span></div>
                `;
                const createdLabel = `${escapeHtml((r.created_at || '').slice(0, 10))}${r.updated_at ? ' · edited' : ''}`;

                return `
                    <div data-comment-id="${escapeHtml(r.id)}" class="comment-reply-card">
                        <a href="/user/${encodeURIComponent(rUserTarget)}" class="comment-avatar-link">
                            <img src="${rAvatar}" alt="Avatar" onerror="handleAvatarError(this, '${jsSafeRAuthorName}')" class="comment-avatar comment-avatar--reply">
                        </a>
                        <div class="comment-body">
                            <div class="comment-meta-row">
                                <div class="comment-author-line">
                                    <a href="/user/${encodeURIComponent(rUserTarget)}" class="comment-author">${safeRAuthorName}</a>
                                    <span class="comment-date">${createdLabel}</span>
                                </div>
                            </div>
                            ${replyContextHtml}
                            <p class="comment-text">${escapeHtml(formatCommentText(r.comment).text)}</p>
                            <div class="comment-actions">
                                ${renderCommentLikeControl(r)}
                                <button type="button" onclick="startReply('${replyId}', '${jsSafeRAuthorName}', '${rootId}')" class="comment-action-button comment-reply-button" title="${escapeHtml(replyBtnText)}"><i class="fa-regular fa-comment-dots" aria-hidden="true"></i><span>${escapeHtml(replyBtnText)}</span></button>
                                ${rIsOwner ? `
                                    ${renderCommentEditControl(r)}
                                    <button type="button" onclick="deleteComment('${replyId}', event)" class="comment-action-button comment-delete-button" title="${escapeHtml(deleteBtnText)}"><i class="fa-regular fa-trash-can" aria-hidden="true"></i><span>${escapeHtml(deleteBtnText)}</span></button>
                                ` : ''}
                            </div>
                        </div>
                    </div>
                `;
            }).join("");

            const safeAuthorDisplayName = escapeHtml(authorDisplayName);
            const jsSafeAuthorDisplayName = escapeJsString(authorDisplayName);
            const createdLabel = `${escapeHtml((c.created_at || '').slice(0, 10))}${c.updated_at ? ' · edited' : ''}`;

            return `
                <article data-comment-id="${escapeHtml(c.id)}" class="comment-card">
                    <a href="/user/${encodeURIComponent(userTarget)}" class="comment-avatar-link">
                        <img src="${avatar}" alt="Avatar" onerror="handleAvatarError(this, '${jsSafeAuthorDisplayName}')" class="comment-avatar">
                    </a>
                    <div class="comment-body">
                        <div class="comment-meta-row">
                            <div class="comment-author-line">
                                <a href="/user/${encodeURIComponent(userTarget)}" class="comment-author">${safeAuthorDisplayName}</a>
                                <span class="comment-date">${createdLabel}</span>
                            </div>
                        </div>
                        <p class="comment-text">${escapeHtml(formatCommentText(c.comment).text)}</p>
                        <div class="comment-actions">
                            ${renderCommentLikeControl(c)}
                            <button type="button" onclick="startReply('${rootId}', '${jsSafeAuthorDisplayName}', '${rootId}')" class="comment-action-button comment-reply-button" title="${escapeHtml(replyBtnText)}"><i class="fa-regular fa-comment-dots" aria-hidden="true"></i><span>${escapeHtml(replyBtnText)}</span></button>
                            ${isOwner ? `
                                ${renderCommentEditControl(c)}
                                <button type="button" onclick="deleteComment('${rootId}', event)" class="comment-action-button comment-delete-button" title="${escapeHtml(deleteBtnText)}"><i class="fa-regular fa-trash-can" aria-hidden="true"></i><span>${escapeHtml(deleteBtnText)}</span></button>
                            ` : ''}
                        </div>
                        ${replies.length > 0 ? `
                            <div class="comment-thread-line">
                                ${repliesHtml}
                            </div>
                        ` : ''}
                    </div>
                </article>
            `;
        }).join("");
        if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
            window.dispatchEvent(new CustomEvent('catrank_comments_rendered', {detail: {catId: String(catId), commentIds: comments.map(c => String(c.id))}}));
        }
        scheduleCommentEditExpiry();

        if (posted && posted.id) {
            const postedElement = container.querySelector(`[data-comment-id="${CSS.escape(String(posted.id))}"]`);
            if (postedElement && typeof postedElement.scrollIntoView === 'function') {
                postedElement.scrollIntoView({behavior: 'smooth', block: 'nearest'});
            }
        }

        if (nextCommentsCursor) {
            const more = document.createElement('button');
            more.type = 'button';
            more.className = 'comments-load-more';
            more.textContent = 'Load more comments';
            more.addEventListener('click', async () => {
                more.disabled = true;
                await loadCatComments(catId, true);
                more.disabled = false;
            });
            container.appendChild(more);
        }
    } catch (e) {
        if (String(activeModalCatId) !== String(catId) || requestVersion !== modalRequestVersion || commentsVersion !== commentsRequestVersion) return;
        const container = document.getElementById('modal-comments-items');
        if (container) {
            if (!append) container.textContent = 'Could not load comments. ';
            else showToast('Could not load more comments. Please retry.', 'error');
            const retry = document.createElement('button');
            retry.type = 'button';
            retry.className = 'text-indigo-600 font-bold';
            retry.textContent = 'Try again';
            retry.addEventListener('click', () => loadCatComments(catId, append));
            container.appendChild(retry);
        }
    } finally {
        if (commentsVersion === commentsRequestVersion) commentsLoading = false;
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
            const posted = await res.json();
            if (activeModalCatId === submittedCatId && submittedVersion === modalRequestVersion) {
                input.value = "";
                cancelReply();
                await loadCatComments(submittedCatId, false, posted.comment);
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

let notificationsCache = [];
let notificationsUnreadCount = 0;
let notificationsRequestVersion = 0;
let notificationsFetchTask = null;

function notificationUiText(enText, ruText) {
    return (typeof currentLang !== 'undefined' && currentLang === 'ru') ? ruText : enText;
}

function closeNotificationsDropdown() {
    const dropdown = document.getElementById("notifications-dropdown");
    const toggle = document.getElementById("notifications-toggle-btn");
    if (dropdown) dropdown.classList.add("hidden");
    if (toggle) toggle.setAttribute("aria-expanded", "false");
}

function toggleNotificationsDropdown() {
    const dropdown = document.getElementById("notifications-dropdown");
    const toggle = document.getElementById("notifications-toggle-btn");
    if (!dropdown) return;

    const willOpen = dropdown.classList.contains("hidden");
    dropdown.classList.toggle("hidden", !willOpen);
    if (toggle) toggle.setAttribute("aria-expanded", willOpen ? "true" : "false");
    if (willOpen) fetchNotifications();
}

document.addEventListener("click", (e) => {
    const wrapper = document.getElementById("notifications-dropdown-wrapper");
    if (wrapper && !wrapper.contains(e.target)) closeNotificationsDropdown();
});

function notificationTypeMeta(type) {
    switch (String(type || '').toLowerCase()) {
        case 'like':
            return { icon: 'fa-solid fa-heart', className: 'notification-type--like' };
        case 'reply':
            return { icon: 'fa-solid fa-reply', className: 'notification-type--reply' };
        case 'comment':
            return { icon: 'fa-solid fa-comment', className: 'notification-type--comment' };
        default:
            return { icon: 'fa-solid fa-bell', className: 'notification-type--default' };
    }
}

function notificationMessage(notification) {
    const actor = String(notification.actor_name || 'Someone');
    const cat = String(notification.cat_name || 'your cat');
    const type = String(notification.type || '').toLowerCase();

    if (typeof currentLang !== 'undefined' && currentLang === 'ru') {
        if (type === 'like') return `${actor} поставил(а) лайк коту ${cat}`;
        if (type === 'comment') return `${actor} оставил(а) комментарий к ${cat}`;
        if (type === 'reply') return `${actor} ответил(а) на ваш комментарий к ${cat}`;
    }

    if (notification.message) return String(notification.message);
    if (type === 'like') return `${actor} liked your cat ${cat}!`;
    if (type === 'comment') return `${actor} commented on your cat ${cat}!`;
    if (type === 'reply') return `${actor} replied to your comment on ${cat}!`;
    return notificationUiText('You have a new notification.', 'У вас новое уведомление.');
}

function notificationRelativeTime(rawDate) {
    const timestamp = Date.parse(String(rawDate || ''));
    if (!Number.isFinite(timestamp)) return '';

    const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
    const ru = typeof currentLang !== 'undefined' && currentLang === 'ru';
    if (seconds < 45) return ru ? 'сейчас' : 'now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}${ru ? ' мин' : 'm'}`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}${ru ? ' ч' : 'h'}`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}${ru ? ' д' : 'd'}`;

    try {
        return new Date(timestamp).toLocaleDateString(ru ? 'ru-RU' : 'en-US', {
            month: 'short', day: 'numeric', year: new Date(timestamp).getFullYear() !== new Date().getFullYear() ? 'numeric' : undefined
        });
    } catch (_error) {
        return String(rawDate || '').slice(0, 10);
    }
}

function updateNotificationBadge(count) {
    notificationsUnreadCount = Math.max(0, Number(count) || 0);
    const badge = document.getElementById("notif-badge");
    const pill = document.getElementById("notifications-unread-count");

    if (badge) {
        if (notificationsUnreadCount > 0) {
            badge.textContent = notificationsUnreadCount > 99 ? '99+' : String(notificationsUnreadCount);
            badge.classList.remove("hidden");
        } else {
            badge.classList.add("hidden");
        }
    }

    if (pill) {
        if (notificationsUnreadCount > 0) {
            pill.textContent = String(notificationsUnreadCount);
            pill.classList.remove("hidden");
        } else {
            pill.classList.add("hidden");
        }
    }

    const markAll = document.getElementById('notifications-mark-all-btn');
    if (markAll) markAll.disabled = notificationsUnreadCount === 0;
}

function renderNotifications() {
    const listContainer = document.getElementById("notifications-list");
    const clearAll = document.getElementById('notifications-clear-all-btn');
    const footerHint = document.getElementById('notification-footer-hint-text');
    if (footerHint) {
        footerHint.textContent = notificationUiText(
            'Open a notification to view the cat. Click an avatar for the profile.',
            'Нажмите уведомление, чтобы открыть кота. Нажмите аватар, чтобы открыть профиль.'
        );
    }

    updateNotificationBadge(notificationsUnreadCount);
    if (clearAll) clearAll.disabled = notificationsCache.length === 0;
    if (!listContainer) return;

    if (notificationsCache.length === 0) {
        listContainer.innerHTML = `
            <div class="notification-empty-state">
                <div class="notification-empty-icon"><i class="fa-regular fa-bell-slash" aria-hidden="true"></i></div>
                <strong>${escapeHtml(notificationUiText('No notifications yet', 'Уведомлений пока нет'))}</strong>
                <span>${escapeHtml(notificationUiText('Likes, comments and replies will appear here.', 'Лайки, комментарии и ответы появятся здесь.'))}</span>
            </div>
        `;
        return;
    }

    listContainer.innerHTML = notificationsCache.map(n => {
        const id = escapeJsString(String(n.id || ''));
        const catId = escapeJsString(String(n.cat_id || ''));
        const actorId = escapeJsString(String(n.actor_id || ''));
        const commentId = escapeJsString(String(n.comment_id || ''));
        const actorName = escapeHtml(String(n.actor_name || 'CatRank user'));
        const avatar = escapeHtml(safeImageUrl(n.actor_avatar, n.actor_name));
        const message = escapeHtml(notificationMessage(n));
        const relative = escapeHtml(notificationRelativeTime(n.created_at));
        const fullDate = escapeHtml(String(n.created_at || '').replace('T', ' ').replace('Z', '').slice(0, 19));
        const isRead = Boolean(n.is_read);
        const meta = notificationTypeMeta(n.type);
        const targetLabel = n.cat_id
            ? notificationUiText('Open cat', 'Открыть кота')
            : notificationUiText('Open profile', 'Открыть профиль');

        return `
            <article class="notification-item ${isRead ? 'is-read' : 'is-unread'}" data-notification-id="${escapeHtml(String(n.id || ''))}">
                <button
                    type="button"
                    class="notification-avatar-button"
                    onclick="openNotificationProfile('${id}', '${actorId}', event)"
                    title="${escapeHtml(notificationUiText('Open profile', 'Открыть профиль'))}: ${actorName}"
                    aria-label="${escapeHtml(notificationUiText('Open profile', 'Открыть профиль'))}: ${actorName}"
                >
                    <img src="${avatar}" alt="${actorName}" class="notification-avatar" onerror="handleAvatarError(this, '${escapeJsString(String(n.actor_name || 'Cat'))}')">
                    <span class="notification-type-badge ${meta.className}" aria-hidden="true"><i class="${meta.icon}"></i></span>
                </button>

                <button
                    type="button"
                    class="notification-content-button"
                    onclick="openNotification('${id}', '${catId}', '${actorId}', '${commentId}', event)"
                    aria-label="${escapeHtml(targetLabel)}"
                >
                    <span class="notification-message">${message}</span>
                    <span class="notification-meta">
                        <time title="${fullDate}">${relative}</time>
                        ${!isRead ? `<span class="notification-new-label">${escapeHtml(notificationUiText('New', 'Новое'))}</span>` : ''}
                    </span>
                </button>

                <div class="notification-item-actions">
                    ${!isRead ? `
                        <button
                            type="button"
                            class="notification-mini-button"
                            onclick="markNotificationRead('${id}', event)"
                            title="${escapeHtml(notificationUiText('Mark as read', 'Отметить прочитанным'))}"
                            aria-label="${escapeHtml(notificationUiText('Mark as read', 'Отметить прочитанным'))}"
                        ><i class="fa-solid fa-check" aria-hidden="true"></i></button>
                    ` : ''}
                    <button
                        type="button"
                        class="notification-mini-button notification-mini-button--danger"
                        onclick="clearNotification('${id}', event)"
                        title="${escapeHtml(notificationUiText('Remove notification', 'Удалить уведомление'))}"
                        aria-label="${escapeHtml(notificationUiText('Remove notification', 'Удалить уведомление'))}"
                    ><i class="fa-solid fa-xmark" aria-hidden="true"></i></button>
                </div>
            </article>
        `;
    }).join('');
}

async function fetchNotifications() {
    const session = currentSession;
    if (!session?.access_token) return;
    if (notificationsFetchTask) return notificationsFetchTask;
    const epoch = viewerAccountEpoch;
    const version = ++notificationsRequestVersion;
    const listContainer = document.getElementById("notifications-list");

    const task = (async () => { try {
        if (listContainer && notificationsCache.length === 0) {
            listContainer.innerHTML = `<div class="notification-loading"><i class="fa-solid fa-spinner fa-spin"></i><span>${escapeHtml(notificationUiText('Loading activity…', 'Загрузка…'))}</span></div>`;
        }
        const res = await fetch("/api/notifications", {
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        if (version !== notificationsRequestVersion) return;
        if (!res.ok) throw new Error(notificationUiText('Could not load notifications.', 'Не удалось загрузить уведомления.'));

        const data = await res.json();
        if (version !== notificationsRequestVersion || epoch !== viewerAccountEpoch || session.user?.id !== currentSession?.user?.id) return;
        notificationsCache = Array.isArray(data.notifications) ? data.notifications : [];
        notificationsUnreadCount = Math.max(0, Number(data.unread_count) || 0);
        renderNotifications();
    } catch (e) {
        if (version !== notificationsRequestVersion || epoch !== viewerAccountEpoch || session.user?.id !== currentSession?.user?.id) return;
        if (listContainer) {
            listContainer.innerHTML = `
                <div class="notification-empty-state notification-empty-state--error">
                    <div class="notification-empty-icon"><i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i></div>
                    <strong>${escapeHtml(notificationUiText('Could not load notifications', 'Не удалось загрузить уведомления'))}</strong>
                    <button type="button" class="notification-retry-button" onclick="fetchNotifications()">${escapeHtml(notificationUiText('Try again', 'Повторить'))}</button>
                </div>
            `;
        }
        console.error("Failed to fetch notifications:", e);
    } })();
    notificationsFetchTask = task;
    try { return await task; }
    finally { if (notificationsFetchTask === task) notificationsFetchTask = null; }
}

async function markNotificationRead(notificationId, event = null) {
    if (event) event.stopPropagation();
    if (!currentSession || !notificationId) return false;
    const epoch = viewerAccountEpoch;
    const session = currentSession;

    const item = notificationsCache.find(n => String(n.id) === String(notificationId));
    if (item?.is_read) return true;

    try {
        const res = await fetch(`/api/notifications/${encodeURIComponent(notificationId)}/read`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        if (epoch !== viewerAccountEpoch || session.user?.id !== currentSession?.user?.id) return false;
        if (!res.ok) throw new Error(notificationUiText('Could not mark notification as read.', 'Не удалось отметить уведомление прочитанным.'));

        notificationsRequestVersion++;
        notificationsFetchTask = null;
        const currentItem = notificationsCache.find(n => String(n.id) === String(notificationId));
        if (currentItem && !currentItem.is_read) {
            currentItem.is_read = true;
            notificationsUnreadCount = Math.max(0, notificationsUnreadCount - 1);
        }
        renderNotifications();
        return true;
    } catch (e) {
        if (event) showToast(e.message, "error");
        return false;
    }
}

async function markAllNotificationsRead() {
    if (!currentSession || notificationsUnreadCount === 0) return;
    const epoch = viewerAccountEpoch;
    const session = currentSession;
    const button = document.getElementById('notifications-mark-all-btn');
    if (button) button.disabled = true;

    try {
        const res = await fetch("/api/notifications/read-all", {
            method: "POST",
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        if (epoch !== viewerAccountEpoch || session.user?.id !== currentSession?.user?.id) return;
        if (!res.ok) throw new Error(notificationUiText('Could not mark notifications read.', 'Не удалось отметить уведомления прочитанными.'));

        notificationsRequestVersion++;
        notificationsFetchTask = null;
        notificationsCache.forEach(n => { n.is_read = true; });
        notificationsUnreadCount = 0;
        renderNotifications();
    } catch (e) {
        showToast(e.message, "error");
    } finally {
        if (button) button.disabled = notificationsUnreadCount === 0;
    }
}

async function clearNotification(notificationId, event = null) {
    if (event) event.stopPropagation();
    if (!currentSession || !notificationId) return;
    const epoch = viewerAccountEpoch;
    const session = currentSession;

    try {
        const res = await fetch(`/api/notifications/${encodeURIComponent(notificationId)}`, {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        if (epoch !== viewerAccountEpoch || session.user?.id !== currentSession?.user?.id) return;
        if (!res.ok) throw new Error(notificationUiText('Could not remove notification.', 'Не удалось удалить уведомление.'));

        notificationsRequestVersion++;
        notificationsFetchTask = null;
        const removed = notificationsCache.find(n => String(n.id) === String(notificationId));
        notificationsCache = notificationsCache.filter(n => String(n.id) !== String(notificationId));
        if (removed && !removed.is_read) notificationsUnreadCount = Math.max(0, notificationsUnreadCount - 1);
        renderNotifications();
    } catch (e) {
        showToast(e.message, "error");
    }
}

async function clearAllNotifications() {
    if (!currentSession || notificationsCache.length === 0) return;
    const epoch = viewerAccountEpoch;
    const session = currentSession;

    const confirmed = typeof showConfirmModal === 'function'
        ? await showConfirmModal({
            title: notificationUiText('Clear notifications?', 'Очистить уведомления?'),
            message: notificationUiText('This removes all notifications from your list. This cannot be undone.', 'Все уведомления будут удалены из списка. Это действие нельзя отменить.'),
            confirmText: notificationUiText('Clear all', 'Очистить всё'),
            danger: true
        })
        : confirm(notificationUiText('Clear all notifications?', 'Очистить все уведомления?'));
    if (!confirmed || epoch !== viewerAccountEpoch || session.user?.id !== currentSession?.user?.id) return;

    const button = document.getElementById('notifications-clear-all-btn');
    if (button) button.disabled = true;
    try {
        const res = await fetch("/api/notifications/clear-all", {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${session.access_token}` }
        });
        if (epoch !== viewerAccountEpoch || session.user?.id !== currentSession?.user?.id) return;
        if (!res.ok) throw new Error(notificationUiText('Could not clear notifications.', 'Не удалось очистить уведомления.'));

        notificationsRequestVersion++;
        notificationsFetchTask = null;
        notificationsCache = [];
        notificationsUnreadCount = 0;
        renderNotifications();
    } catch (e) {
        showToast(e.message, "error");
    } finally {
        if (button) button.disabled = notificationsCache.length === 0;
    }
}

async function focusNotificationComment(commentId) {
    if (!commentId || !activeModalCatId) return;
    const targetId = String(commentId);

    for (let page = 0; page < 10; page++) {
        const target = document.querySelector(`[data-comment-id="${targetId}"]`);
        if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
            target.classList.add('notification-target-highlight');
            window.setTimeout(() => target.classList.remove('notification-target-highlight'), 2600);
            return;
        }
        if (!nextCommentsCursor) break;
        await loadCatComments(activeModalCatId, true);
    }
}

async function openNotification(notificationId, catId, actorId, commentId, event = null) {
    if (event) event.stopPropagation();
    if (notificationId) await markNotificationRead(notificationId);
    closeNotificationsDropdown();

    if (catId && typeof openCatModal === 'function') {
        await openCatModal(catId);
        if (commentId) await focusNotificationComment(commentId);
        return;
    }
    if (actorId) {
        window.location.href = `/user/${encodeURIComponent(actorId)}`;
    }
}

async function openNotificationProfile(notificationId, actorId, event = null) {
    if (event) event.stopPropagation();
    if (notificationId) await markNotificationRead(notificationId);
    closeNotificationsDropdown();
    if (actorId) window.location.href = `/user/${encodeURIComponent(actorId)}`;
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

function commentEditorLabel(enText, ruText) {
    return (typeof currentLang !== 'undefined' && currentLang === 'ru') ? ruText : enText;
}

let activeInlineCommentEditor = null;

function closeCommentEditModal() {
    if (!activeInlineCommentEditor) return;
    const { root, textNode, actionsNode, form, keyHandler } = activeInlineCommentEditor;
    if (keyHandler) document.removeEventListener('keydown', keyHandler);
    if (form?.isConnected) form.remove();
    if (textNode) textNode.hidden = false;
    if (actionsNode) actionsNode.hidden = false;
    if (root) root.classList.remove('is-editing-comment');
    activeInlineCommentEditor = null;
}

function editComment(commentId) {
    const comment = loadedComments.find(c => String(c.id) === String(commentId));
    if (!comment) return;

    if (!commentCanBeEdited(comment)) {
        showToast(
            typeof t === 'function'
                ? t('comment_edit_expired')
                : commentEditorLabel('Editing is available for two minutes after posting.', 'Редактирование доступно в течение двух минут после публикации.'),
            'info'
        );
        updateCommentEditControls();
        return;
    }

    closeCommentEditModal();

    const root = document.querySelector(`[data-comment-id="${CSS.escape(String(commentId))}"]`);
    const body = root?.querySelector('.comment-body');
    const textNode = body?.querySelector('.comment-text');
    const actionsNode = body?.querySelector('.comment-actions');
    if (!root || !body || !textNode || !actionsNode) return;

    const form = document.createElement('form');
    form.className = 'comment-inline-editor';
    form.setAttribute('aria-label', commentEditorLabel('Edit comment', 'Редактирование комментария'));

    const topRow = document.createElement('div');
    topRow.className = 'comment-inline-editor__top';

    const status = document.createElement('span');
    status.className = 'comment-inline-editor__status';
    status.innerHTML = '<span></span>';
    status.querySelector('span').textContent = commentEditorLabel('Editing comment', 'Редактирование');

    const counter = document.createElement('span');
    counter.className = 'comment-inline-editor__counter';
    topRow.append(status, counter);

    const textareaWrap = document.createElement('div');
    textareaWrap.className = 'comment-inline-editor__field';

    const textarea = document.createElement('textarea');
    textarea.className = 'comment-inline-editor__textarea';
    textarea.value = String(comment.comment || '');
    textarea.maxLength = 300;
    textarea.required = true;
    textarea.rows = 3;
    textarea.setAttribute('aria-label', commentEditorLabel('Edit comment text', 'Текст комментария'));
    textareaWrap.appendChild(textarea);

    const footer = document.createElement('div');
    footer.className = 'comment-inline-editor__footer';

    const controls = document.createElement('div');
    controls.className = 'comment-inline-editor__controls';

    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'comment-inline-editor__button comment-inline-editor__button--cancel';
    cancel.textContent = commentEditorLabel('Cancel', 'Отмена');

    const save = document.createElement('button');
    save.type = 'submit';
    save.className = 'comment-inline-editor__button comment-inline-editor__button--save';
    save.innerHTML = '<i class="fa-solid fa-check" aria-hidden="true"></i><span></span>';
    save.querySelector('span').textContent = commentEditorLabel('Save', 'Сохранить');

    controls.append(cancel, save);
    footer.append(controls);
    form.append(topRow, textareaWrap, footer);

    textNode.hidden = true;
    actionsNode.hidden = true;
    root.classList.add('is-editing-comment');
    textNode.insertAdjacentElement('afterend', form);

    const refreshCounter = () => {
        counter.textContent = `${textarea.value.length}/300`;
        save.disabled = !textarea.value.trim();
    };
    refreshCounter();
    textarea.addEventListener('input', refreshCounter);

    const keyHandler = event => {
        if (event.key === 'Escape' && !save.dataset.saving) {
            // Escape belongs to the inline editor first. Prevent the global
            // modal handler from also closing the whole cat viewer.
            event.preventDefault();
            event.stopImmediatePropagation();
            closeCommentEditModal();
        }
    };
    document.addEventListener('keydown', keyHandler);
    activeInlineCommentEditor = { root, textNode, actionsNode, form, keyHandler };

    cancel.addEventListener('click', closeCommentEditModal);

    requestAnimationFrame(() => {
        textarea.focus();
        textarea.setSelectionRange(textarea.value.length, textarea.value.length);
        root.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });

    const catId = activeModalCatId;
    const version = modalRequestVersion;

    form.addEventListener('submit', async event => {
        event.preventDefault();
        const nextComment = textarea.value.trim();
        if (!nextComment || save.dataset.saving) return;

        save.dataset.saving = '1';
        save.disabled = true;
        cancel.disabled = true;
        textarea.disabled = true;
        save.querySelector('span').textContent = commentEditorLabel('Saving…', 'Сохранение…');

        try {
            const result = await authRequest(
                `/api/comments/${encodeURIComponent(commentId)}`,
                {comment: nextComment},
                'PUT',
                true
            );

            closeCommentEditModal();
            if (activeModalCatId === catId && modalRequestVersion === version) {
                await loadCatComments(
                    catId,
                    false,
                    {...comment, comment: result.comment, updated_at: result.updated_at || new Date().toISOString()}
                );
            }
            showToast(commentEditorLabel('Comment updated.', 'Комментарий обновлён.'), 'success');
        } catch (error) {
            if (error?.code === 'edit_window_expired') {
                closeCommentEditModal();
                updateCommentEditControls();
            } else {
                delete save.dataset.saving;
                save.disabled = false;
                cancel.disabled = false;
                textarea.disabled = false;
                save.querySelector('span').textContent = commentEditorLabel('Save', 'Сохранить');
            }
            showToast(
                error?.message || commentEditorLabel('Could not update comment.', 'Не удалось обновить комментарий.'),
                'error'
            );
        }
    });
}
