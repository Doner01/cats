const userFavoriteCatIds = new Set();
const pendingFavorites = new Set();
let favoritesOwnerId = null;
let favoritesReady = false;
let favoritesRevision = 0;
let favoritesSync = null;
let favoritesEpoch = 0;

function favoriteLabel(key) {
    const labels = {save_cat: 'Save cat', unsave_cat: 'Remove from favorites', favorites_error: 'Could not load favorites. Please try again.', favorite_saved: 'Saved to favorites', favorite_removed: 'Removed from favorites'};
    return typeof t === 'function' ? t(key) : labels[key] || key;
}

function updateFavoriteButtons() {
    const update = (button, id) => {
        const saved = userFavoriteCatIds.has(String(id));
        button.setAttribute('aria-pressed', String(saved));
        button.setAttribute('aria-label', favoriteLabel(saved ? 'unsave_cat' : 'save_cat'));
        button.title = favoriteLabel(saved ? 'unsave_cat' : 'save_cat');
        button.disabled = !id || pendingFavorites.has(String(id));
    };
    document.querySelectorAll('[data-save-cat-id]').forEach(button => update(button, button.dataset.saveCatId));
    const modalButton = document.getElementById('modal-save-btn');
    if (modalButton) update(modalButton, typeof activeModalCatId !== 'undefined' ? activeModalCatId : null);
}

function resetFavorites() {
    favoritesEpoch++;
    userFavoriteCatIds.clear();
    favoritesOwnerId = null;
    favoritesReady = false;
    favoritesSync = null;
    favoritesRevision++;
    updateFavoriteButtons();
}

async function syncUserFavorites(session = currentSession) {
    if (!session?.user?.id || !session.access_token) return false;
    const owner = String(session.user.id);
    if (favoritesOwnerId !== owner) {
        resetFavorites();
        favoritesOwnerId = owner;
    }
    if (favoritesReady) { updateFavoriteButtons(); return true; }
    if (favoritesSync) return favoritesSync;
    const revision = favoritesRevision;
    const task = (async () => {
        try {
            const response = await fetch('/api/user/favorite-ids', {headers: {Authorization: `Bearer ${session.access_token}`}});
            if (!response.ok) return false;
            const data = await response.json();
            if (owner !== favoritesOwnerId || revision !== favoritesRevision) return false;
            userFavoriteCatIds.clear();
            (data.favorite_cat_ids || []).forEach(id => userFavoriteCatIds.add(String(id)));
            favoritesReady = true;
            updateFavoriteButtons();
            return true;
        } catch (_) { return false; }
    })();
    favoritesSync = task;
    try { return await task; }
    finally { if (favoritesSync === task) favoritesSync = null; }
}

async function toggleFavorite(catId, event) {
    event?.stopPropagation();
    if (!catId || pendingFavorites.has(String(catId))) return;
    const id = String(catId);
    pendingFavorites.add(id);
    updateFavoriteButtons();
    let owner = null;
    let previous = false;
    let changed = false;
    let epoch = favoritesEpoch;
    try {
        const result = typeof supabaseClient !== 'undefined' && supabaseClient
            ? await supabaseClient.auth.getSession() : null;
        const session = result?.data?.session;
        if (!session) {
            window.location.href = getCatLoginUrl(id);
            return;
        }
        owner = String(session.user.id);
        if (!await syncUserFavorites(session)) throw new Error(favoriteLabel('favorites_error'));
        if (owner !== favoritesOwnerId) return;
        epoch = favoritesEpoch;
        previous = userFavoriteCatIds.has(id);
        changed = true;
        favoritesRevision++;
        if (previous) userFavoriteCatIds.delete(id);
        else userFavoriteCatIds.add(id);
        updateFavoriteButtons();
        const response = await fetch(`/api/cats/${encodeURIComponent(id)}/favorite`, {
            method: previous ? 'DELETE' : 'PUT',
            headers: {Authorization: `Bearer ${session.access_token}`}
        });
        const data = await response.json();
        if (owner !== favoritesOwnerId || epoch !== favoritesEpoch) return;
        if (!response.ok) throw new Error(data.error || favoriteLabel('favorites_error'));
        if (data.saved) userFavoriteCatIds.add(id);
        else userFavoriteCatIds.delete(id);
        showToast(favoriteLabel(data.saved ? 'favorite_saved' : 'favorite_removed'), 'success');
        window.dispatchEvent(new CustomEvent('catrank_favorites_changed'));
    } catch (error) {
        if (owner === favoritesOwnerId && epoch === favoritesEpoch && changed) {
            if (previous) userFavoriteCatIds.add(id);
            else userFavoriteCatIds.delete(id);
        }
        showToast(error.message || favoriteLabel('favorites_error'), 'error');
    } finally {
        pendingFavorites.delete(id);
        updateFavoriteButtons();
    }
}

window.addEventListener('catrank_language_changed', updateFavoriteButtons);
