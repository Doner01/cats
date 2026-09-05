/* Comment likes are separate from cat votes and are private per account. */
(function () {
    const likedCommentIds = new Set();
    const pending = new Map();
    const knownCommentIds = new Set();
    let ownerId = null;
    let accountEpoch = 0;
    let syncVersion = 0;
    let syncedCatId = null;

    function resetOwner(nextOwner) {
        if (ownerId === nextOwner) return;
        ownerId = nextOwner;
        accountEpoch++;
        pending.clear();
        syncVersion++;
        likedCommentIds.clear();
        knownCommentIds.clear();
        paintButtons();
    }

    function isCurrentOwner(session, epoch) {
        return epoch === accountEpoch && ownerId === session?.user?.id
            && (typeof currentSession === 'undefined' || currentSession?.user?.id === ownerId);
    }

    function label(key, fallback) {
        return typeof t === 'function' ? t(key) : fallback;
    }

    function paintButtons() {
        document.querySelectorAll('[data-comment-like-id]').forEach(button => {
            const id = String(button.dataset.commentLikeId || '');
            if (!id) return;
            const liked = likedCommentIds.has(id);
            const icon = button.querySelector('[data-comment-like-icon]');
            const count = button.querySelector('[data-comment-like-count]');
            if (icon) icon.textContent = liked ? '♥' : '♡';
            if (count && button.dataset.commentLikeCount !== undefined) count.textContent = button.dataset.commentLikeCount;
            button.setAttribute('aria-pressed', String(liked));
            button.setAttribute('aria-label', label(liked ? 'unlike_comment' : 'like_comment', liked ? 'Unlike comment' : 'Like comment'));
            button.classList.toggle('is-liked', liked);
        });
    }

    async function getSession() {
        if (typeof currentSession !== 'undefined' && currentSession?.access_token) return currentSession;
        if (typeof supabaseClient === 'undefined' || !supabaseClient) return null;
        try {
            const result = await supabaseClient.auth.getSession();
            return result?.data?.session || null;
        } catch (_) { return null; }
    }

    async function syncCommentLikes(ids) {
        const version = ++syncVersion;
        const catId = typeof activeModalCatId !== 'undefined' ? String(activeModalCatId || '') : '';
        const modalVersion = typeof modalRequestVersion !== 'undefined' ? modalRequestVersion : 0;
        if (syncedCatId !== catId) {
            syncedCatId = catId;
            likedCommentIds.clear();
            knownCommentIds.clear();
        }
        const session = await getSession();
        if (version !== syncVersion) return;
        resetOwner(session?.user?.id || null);
        if (!session?.access_token) { paintButtons(); return; }
        const epoch = accountEpoch;
        const requestVersion = syncVersion;
        const uniqueIds = Array.from(new Set((ids || []).map(String).filter(Boolean)))
            .filter(id => !knownCommentIds.has(id) && !pending.has(id));
        const isCurrent = () => requestVersion === syncVersion && isCurrentOwner(session, epoch)
            && (typeof activeModalCatId === 'undefined'
                || (String(activeModalCatId || '') === catId && modalRequestVersion === modalVersion));
        try {
            // The API accepts at most 100 ids. Later pages only request ids we
            // have not synchronized, instead of dropping everything after 100.
            for (let offset = 0; offset < uniqueIds.length; offset += 100) {
                if (!isCurrent()) return;
                const batch = uniqueIds.slice(offset, offset + 100);
                const response = await fetch('/api/user/comment-likes?ids=' + encodeURIComponent(batch.join(',')), {
                    headers: { 'Authorization': 'Bearer ' + session.access_token }
                });
                if (!response.ok) throw new Error('Could not load comment likes.');
                const data = await response.json();
                if (!isCurrent()) return;
                const liked = new Set((data.liked_comment_ids || []).map(String));
                batch.forEach(id => {
                    // An in-flight snapshot cannot undo an optimistic vote.
                    if (pending.has(id) || knownCommentIds.has(id)) return;
                    likedCommentIds[liked.has(id) ? 'add' : 'delete'](id);
                    knownCommentIds.add(id);
                });
                paintButtons();
            }
            paintButtons();
        } catch (_) {
            if (isCurrent()) paintButtons();
        }
    }

    function setButtonState(id, liked, count) {
        const safeCount = Math.max(0, Number(count) || 0);
        document.querySelectorAll('[data-comment-like-id="' + CSS.escape(id) + '"]').forEach(button => {
            button.dataset.commentLikeCount = String(safeCount);
            const countElement = button.querySelector('[data-comment-like-count]');
            const icon = button.querySelector('[data-comment-like-icon]');
            if (countElement) countElement.textContent = String(safeCount);
            if (icon) icon.textContent = liked ? '♥' : '♡';
            button.setAttribute('aria-pressed', String(liked));
            button.setAttribute('aria-label', label(liked ? 'unlike_comment' : 'like_comment', liked ? 'Unlike comment' : 'Like comment'));
            button.classList.toggle('is-liked', liked);
        });
    }

    async function toggleCommentLike(commentId, event) {
        event?.preventDefault();
        event?.stopPropagation();
        const id = String(commentId || '');
        if (!id || pending.has(id)) return;
        const mutation = Symbol(id);
        pending.set(id, mutation);
        const releasePending = () => {
            if (pending.get(id) === mutation) pending.delete(id);
        };
        const initialEpoch = accountEpoch;
        const session = await getSession();
        if (initialEpoch !== accountEpoch) { releasePending(); return; }
        if (!session?.access_token) {
            releasePending();
            if (typeof showToast === 'function') showToast(typeof t === 'function' ? t('toast_need_signin_comment') : 'Please sign in to like comments.', 'info');
            if (typeof getCatLoginUrl === 'function') setTimeout(() => { window.location.href = getCatLoginUrl(); }, 500);
            return;
        }
        resetOwner(session.user?.id || null);
        const epoch = accountEpoch;
        pending.set(id, mutation);
        if (!isCurrentOwner(session, epoch)) { releasePending(); return; }
        const button = document.querySelector('[data-comment-like-id="' + CSS.escape(id) + '"]');
        const countElement = button?.querySelector('[data-comment-like-count]');
        const previousLiked = likedCommentIds.has(id);
        const previousCount = Math.max(0, Number(countElement?.textContent || button?.dataset.commentLikeCount || 0) || 0);
        const nextLiked = !previousLiked;
        const nextCount = Math.max(0, previousCount + (nextLiked ? 1 : -1));
        likedCommentIds[nextLiked ? 'add' : 'delete'](id);
        setButtonState(id, nextLiked, nextCount);
        try {
            const response = await fetch('/api/comments/' + encodeURIComponent(id) + '/like', {
                method: nextLiked ? 'PUT' : 'DELETE',
                headers: { 'Authorization': 'Bearer ' + session.access_token }
            });
            let data = {};
            try { data = await response.json(); } catch (_) {}
            if (!isCurrentOwner(session, epoch)) return;
            if (!response.ok) throw new Error(data.error || 'Could not update comment like.');
            knownCommentIds.add(id);
            const serverLiked = Boolean(data.liked);
            const serverCount = Math.max(0, Number(data.likes_count) || 0);
            likedCommentIds[serverLiked ? 'add' : 'delete'](id);
            setButtonState(id, serverLiked, serverCount);
            if (typeof loadedComments !== 'undefined') {
                const comment = loadedComments.find(item => String(item.id) === id);
                if (comment) comment.likes_count = serverCount;
            }
            window.dispatchEvent(new CustomEvent('catrank_comment_like_changed', { detail: { id, liked: serverLiked, likes_count: serverCount } }));
        } catch (error) {
            if (!isCurrentOwner(session, epoch)) return;
            knownCommentIds.delete(id);
            likedCommentIds[previousLiked ? 'add' : 'delete'](id);
            setButtonState(id, previousLiked, previousCount);
            if (typeof showToast === 'function') showToast(error.message || 'Could not update comment like.', 'error');
        } finally {
            releasePending();
        }
    }

    window.toggleCommentLike = toggleCommentLike;
    window.syncCommentLikes = syncCommentLikes;
    window.addEventListener('catrank_comments_rendered', event => syncCommentLikes(event.detail?.commentIds || []));
    window.addEventListener('catrank_auth_changed', () => {
        resetOwner(typeof currentSession !== 'undefined' ? currentSession?.user?.id || null : null);
        const ids = typeof loadedComments !== 'undefined' ? loadedComments.map(comment => String(comment.id)) : [];
        syncCommentLikes(ids);
    });
    window.addEventListener('catrank_language_changed', paintButtons);
    window.addEventListener('catrank_viewer_closed', () => {
        syncVersion++;
        syncedCatId = null;
        likedCommentIds.clear();
        knownCommentIds.clear();
    });
}());
