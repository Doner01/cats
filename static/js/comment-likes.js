/* Comment likes are separate from cat votes and are private per account. */
(function () {
    const likedCommentIds = new Set();
    const pending = new Set();

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
        const uniqueIds = Array.from(new Set((ids || []).map(id => String(id)).filter(Boolean))).slice(0, 100);
        if (!uniqueIds.length) {
            likedCommentIds.clear();
            paintButtons();
            return;
        }
        const session = await getSession();
        if (!session?.access_token) {
            uniqueIds.forEach(id => likedCommentIds.delete(id));
            paintButtons();
            return;
        }
        const catId = typeof activeModalCatId !== 'undefined' ? String(activeModalCatId || '') : '';
        const version = typeof modalRequestVersion !== 'undefined' ? modalRequestVersion : 0;
        try {
            const response = await fetch('/api/user/comment-likes?ids=' + encodeURIComponent(uniqueIds.join(',')), {
                headers: { 'Authorization': 'Bearer ' + session.access_token }
            });
            if (typeof activeModalCatId !== 'undefined' && (String(activeModalCatId || '') !== catId || modalRequestVersion !== version)) return;
            if (!response.ok) throw new Error('Could not load comment likes.');
            const data = await response.json();
            uniqueIds.forEach(id => likedCommentIds.delete(id));
            (data.liked_comment_ids || []).forEach(id => likedCommentIds.add(String(id)));
            paintButtons();
        } catch (_) {
            // Counts remain useful even when the per-user state request is unavailable.
            paintButtons();
        }
    }

    function setButtonState(id, liked, count) {
        const safeCount = Math.max(0, Number(count) || 0);
        document.querySelectorAll('[data-comment-like-id="' + id.replace(/"/g, '') + '"]').forEach(button => {
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
        const session = await getSession();
        if (!session?.access_token) {
            if (typeof showToast === 'function') showToast(typeof t === 'function' ? t('toast_need_signin_comment') : 'Please sign in to like comments.', 'info');
            if (typeof getCatLoginUrl === 'function') setTimeout(() => { window.location.href = getCatLoginUrl(); }, 500);
            return;
        }
        const button = document.querySelector('[data-comment-like-id="' + id.replace(/"/g, '') + '"]');
        const countElement = button?.querySelector('[data-comment-like-count]');
        const previousLiked = likedCommentIds.has(id);
        const previousCount = Math.max(0, Number(countElement?.textContent || button?.dataset.commentLikeCount || 0) || 0);
        const nextLiked = !previousLiked;
        const nextCount = Math.max(0, previousCount + (nextLiked ? 1 : -1));
        pending.add(id);
        likedCommentIds[nextLiked ? 'add' : 'delete'](id);
        setButtonState(id, nextLiked, nextCount);
        try {
            const response = await fetch('/api/comments/' + encodeURIComponent(id) + '/like', {
                method: nextLiked ? 'PUT' : 'DELETE',
                headers: { 'Authorization': 'Bearer ' + session.access_token }
            });
            let data = {};
            try { data = await response.json(); } catch (_) {}
            if (!response.ok) throw new Error(data.error || 'Could not update comment like.');
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
            likedCommentIds[previousLiked ? 'add' : 'delete'](id);
            setButtonState(id, previousLiked, previousCount);
            if (typeof showToast === 'function') showToast(error.message || 'Could not update comment like.', 'error');
        } finally {
            pending.delete(id);
        }
    }

    window.toggleCommentLike = toggleCommentLike;
    window.syncCommentLikes = syncCommentLikes;
    window.addEventListener('catrank_comments_rendered', event => syncCommentLikes(event.detail?.commentIds || []));
    window.addEventListener('catrank_auth_changed', () => {
        const ids = typeof loadedComments !== 'undefined' ? loadedComments.map(comment => String(comment.id)) : [];
        syncCommentLikes(ids);
    });
    window.addEventListener('catrank_language_changed', paintButtons);
}());
