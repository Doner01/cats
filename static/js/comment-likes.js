(function () {
    const likedCommentIds = new Set();
    const knownIds = new Set();
    const pending = new Map();
    const revisions = new Map();
    let ownerId = typeof currentSession !== 'undefined' ? currentSession?.user?.id || null : null;
    let accountEpoch = 0;
    let syncVersion = 0;

    function label(key, fallback) {
        return typeof t === 'function' ? t(key) : fallback;
    }

    function buttonsFor(id) {
        return Array.from(document.querySelectorAll('[data-comment-like-id]'))
            .filter(button => String(button.dataset.commentLikeId) === id);
    }

    function paintButtons() {
        document.querySelectorAll('[data-comment-like-id]').forEach(button => {
            const id = String(button.dataset.commentLikeId || '');
            if (!id) return;
            const liked = likedCommentIds.has(id);
            const icon = button.querySelector('[data-comment-like-icon]');
            const count = button.querySelector('[data-comment-like-count]');
            if (icon) icon.textContent = liked ? '♥' : '♡';
            if (count) count.textContent = button.dataset.commentLikeCount || '0';
            button.setAttribute('aria-pressed', String(liked));
            button.setAttribute('aria-label', label(liked ? 'unlike_comment' : 'like_comment', liked ? 'Unlike comment' : 'Like comment'));
            button.classList.toggle('is-liked', liked);
            button.disabled = pending.has(id);
        });
    }

    function setCount(id, count) {
        buttonsFor(id).forEach(button => {
            button.dataset.commentLikeCount = String(Math.max(0, Number(count) || 0));
        });
        paintButtons();
    }

    function changeOwner(id) {
        if (id === ownerId) return;
        for (const [commentId, task] of pending) {
            if (task.changed) setCount(commentId, task.previousCount);
        }
        ownerId = id;
        accountEpoch++;
        syncVersion++;
        likedCommentIds.clear();
        knownIds.clear();
        pending.clear();
        revisions.clear();
        paintButtons();
    }

    async function getSession() {
        if (typeof currentSession !== 'undefined' && currentSession?.access_token) return currentSession;
        if (typeof supabaseClient === 'undefined' || !supabaseClient) return null;
        try {
            return (await supabaseClient.auth.getSession())?.data?.session || null;
        } catch (_) { return null; }
    }

    function viewerKey() {
        const cat = typeof activeModalCatId !== 'undefined' ? activeModalCatId || '' : '';
        const version = typeof modalRequestVersion !== 'undefined' ? modalRequestVersion : 0;
        return String(cat) + ':' + version;
    }

    async function readLikes(ids, session) {
        const response = await fetch('/api/user/comment-likes?ids=' + encodeURIComponent(ids.join(',')), {
            headers: {Authorization: 'Bearer ' + session.access_token}
        });
        if (!response.ok) throw new Error(label('comment_like_error', 'Could not load comment likes. Please try again.'));
        const data = await response.json();
        return new Set((data.liked_comment_ids || []).map(String));
    }

    async function syncCommentLikes(ids) {
        const uniqueIds = Array.from(new Set((ids || []).map(String).filter(Boolean)));
        let run = ++syncVersion;
        let epoch = accountEpoch;
        const viewer = viewerKey();
        if (!uniqueIds.length) { paintButtons(); return; }
        const session = await getSession();
        if (epoch !== accountEpoch || run !== syncVersion || viewer !== viewerKey()) return;
        changeOwner(session?.user?.id || null);
        epoch = accountEpoch;
        run = ++syncVersion;
        if (!session?.access_token || !ownerId) { paintButtons(); return; }
        try {
            for (let offset = 0; offset < uniqueIds.length; offset += 100) {
                const batch = uniqueIds.slice(offset, offset + 100);
                const before = new Map(batch.map(id => [id, revisions.get(id) || 0]));
                const liked = await readLikes(batch, session);
                if (epoch !== accountEpoch || run !== syncVersion || viewer !== viewerKey()) return;
                batch.forEach(id => {
                    if (pending.has(id) || (revisions.get(id) || 0) !== before.get(id)) return;
                    likedCommentIds[liked.has(id) ? 'add' : 'delete'](id);
                    knownIds.add(id);
                });
                paintButtons();
            }
        } catch (_) {
            // Public counts still work when personal state cannot be loaded.
        }
    }

    async function toggleCommentLike(commentId, event) {
        event?.preventDefault();
        event?.stopPropagation();
        const id = String(commentId || '');
        if (!id || pending.has(id)) return;
        const task = {changed: false, previousCount: 0};
        pending.set(id, task);
        paintButtons();
        let epoch = accountEpoch;
        let previousLiked = false;
        const isCurrent = () => epoch === accountEpoch && pending.get(id) === task;
        try {
            const session = await getSession();
            if (!isCurrent()) return;
            if (!session?.access_token || !session?.user?.id) {
                if (typeof showToast === 'function') showToast(label('toast_need_signin_comment', 'Please sign in to like comments.'), 'info');
                if (typeof getCatLoginUrl === 'function') window.location.href = getCatLoginUrl();
                return;
            }
            if (ownerId !== session.user.id) {
                changeOwner(session.user.id);
                epoch = accountEpoch;
                pending.set(id, task);
            }
            if (!knownIds.has(id)) {
                const liked = await readLikes([id], session);
                if (!isCurrent()) return;
                likedCommentIds[liked.has(id) ? 'add' : 'delete'](id);
                knownIds.add(id);
            }
            previousLiked = likedCommentIds.has(id);
            task.previousCount = Math.max(0, Number(buttonsFor(id)[0]?.dataset.commentLikeCount) || 0);
            task.changed = true;
            revisions.set(id, (revisions.get(id) || 0) + 1);
            likedCommentIds[previousLiked ? 'delete' : 'add'](id);
            setCount(id, task.previousCount + (previousLiked ? -1 : 1));
            const response = await fetch('/api/comments/' + encodeURIComponent(id) + '/like', {
                method: previousLiked ? 'DELETE' : 'PUT',
                headers: {Authorization: 'Bearer ' + session.access_token}
            });
            let data = {};
            try { data = await response.json(); } catch (_) {}
            if (!isCurrent()) return;
            if (!response.ok) throw new Error(data.error || label('comment_like_error', 'Could not update comment like.'));
            const serverLiked = Boolean(data.liked);
            const serverCount = Math.max(0, Number(data.likes_count) || 0);
            likedCommentIds[serverLiked ? 'add' : 'delete'](id);
            setCount(id, serverCount);
            if (typeof loadedComments !== 'undefined') {
                const comment = loadedComments.find(item => String(item.id) === id);
                if (comment) comment.likes_count = serverCount;
            }
            window.dispatchEvent(new CustomEvent('catrank_comment_like_changed', {detail: {id, liked: serverLiked, likes_count: serverCount}}));
        } catch (error) {
            if (!isCurrent()) return;
            if (task.changed) {
                likedCommentIds[previousLiked ? 'add' : 'delete'](id);
                setCount(id, task.previousCount);
            }
            if (typeof showToast === 'function') showToast(error.message || label('comment_like_error', 'Could not update comment like.'), 'error');
        } finally {
            if (isCurrent()) {
                revisions.set(id, (revisions.get(id) || 0) + 1);
                pending.delete(id);
                paintButtons();
            }
        }
    }

    window.toggleCommentLike = toggleCommentLike;
    window.syncCommentLikes = syncCommentLikes;
    window.addEventListener('catrank_comments_rendered', event => syncCommentLikes(event.detail?.commentIds || []));
    window.addEventListener('catrank_auth_changed', () => {
        changeOwner(typeof currentSession !== 'undefined' ? currentSession?.user?.id || null : null);
        const ids = typeof loadedComments !== 'undefined' ? loadedComments.map(comment => String(comment.id)) : [];
        return syncCommentLikes(ids);
    });
    window.addEventListener('catrank_language_changed', paintButtons);
}());
