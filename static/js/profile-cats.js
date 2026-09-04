const profileCatsState = {uploads: [], own: false, tab: 'uploads', page: 1, request: 0, dirty: false};

function configureProfileCats(cats, own) {
    profileCatsState.uploads = cats;
    profileCatsState.own = Boolean(own);
    document.getElementById('profile-favorites-tab').classList.toggle('hidden', !own);
    return switchProfileCatsTab(own ? profileCatsState.tab : 'uploads');
}

function profileGridMessage(title, description, retry = false) {
    const grid = document.getElementById('user-cats-grid');
    grid.innerHTML = `<div class="profile-grid-message"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p>${retry ? `<button type="button" onclick="loadFavoriteCats(profileCatsState.page)">${escapeHtml(t('try_again'))}</button>` : ''}</div>`;
}

function renderProfileCats(cats, ownUploads = false) {
    const grid = document.getElementById('user-cats-grid');
    if (!cats.length) {
        const favorites = profileCatsState.tab === 'favorites';
        profileGridMessage(t(favorites ? 'favorites_empty' : 'no_cats_title'), t(favorites ? 'favorites_empty_hint' : 'no_cats_desc'));
        return;
    }
    grid.innerHTML = cats.map(cat => {
        const id = escapeHtml(cat.id);
        const actionId = escapeJsString(cat.id);
        const name = escapeHtml(cat.name || 'Cat');
        const rawBio = String(cat.bio || cat.description || '');
        const bio = escapeHtml(rawBio);
        const owner = escapeHtml(cat.user_name || 'Cat Lover');
        const avatar = escapeHtml(safeImageUrl(cat.user_avatar, cat.user_name || 'Cat Lover'));
        const image = escapeHtml(safeImageUrl(cat.image_url, cat.name || 'Cat'));
        const likes = Math.max(0, Number(cat.likes_count) || 0);
        const liked = userLikedCatIds.has(String(cat.id));
        return `<article id="cat-card-${id}" data-cat-id="${id}" data-cat-modal-id="${id}" data-cat-name="${name}" data-likes="${likes}" class="cat-card feed-card">
            <div class="profile-cat-owner"><a href="/user/${encodeURIComponent(cat.user_id || '')}" class="cat-owner-link"><img src="${avatar}" alt="${owner}" loading="lazy" onerror="handleAvatarError(this, this.alt)"><span>${owner}</span></a></div>
            <button type="button" class="cat-img-wrapper cat-open" onclick="openCatModal('${actionId}')" aria-label="${name}"><img data-cat-photo src="${image}" alt="${name}" loading="lazy" decoding="async"></button>
            <div class="feed-card-body"><div class="cat-title-row"><h3>${name}</h3><button id="like-btn-${id}" type="button" onclick="toggleLike('${actionId}', event)" class="vote-button" aria-label="${escapeHtml(t('like_cat'))}" aria-pressed="${liked}"><span id="heart-icon-${id}" aria-hidden="true">${liked ? '❤️' : '🤍'}</span><span id="like-count-${id}">${likes}</span></button></div>
            <div class="cat-credit"><time datetime="${escapeHtml(cat.created_at || '')}">${escapeHtml(String(cat.created_at || '').slice(0,10))}</time><div class="flex items-center gap-2">
                ${ownUploads ? `<button type="button" onclick="startEditCat('${actionId}', event)" class="save-cat-button profile-cat-edit-button" aria-label="${escapeHtml(currentLang === 'ru' ? 'Редактировать котика' : 'Edit cat')}" title="${escapeHtml(currentLang === 'ru' ? 'Редактировать' : 'Edit')}"><i class="fa-regular fa-pen-to-square" aria-hidden="true"></i></button><button type="button" data-delete-cat-id="${id}" onclick="deleteMyCat('${actionId}', event)" class="save-cat-button profile-cat-delete-button" aria-label="${escapeHtml(t('delete_cat'))}" title="${escapeHtml(t('delete_cat'))}"><i class="fa-solid fa-trash-can" aria-hidden="true"></i></button>` : ''}
                <button type="button" class="save-cat-button" data-save-cat-id="${id}" onclick="toggleFavorite('${actionId}', event)" aria-label="${escapeHtml(t('save_cat'))}" aria-pressed="false"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M6 3h12v18l-6-4-6 4V3Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg></button>
            </div></div></div>
            ${ownUploads ? `<div id="cat-editor-${id}" class="profile-cat-inline-editor profile-cat-inline-editor--compact hidden">
                <div class="profile-cat-editor-head">
                    <div class="profile-cat-editor-title"><strong>${escapeHtml(currentLang === 'ru' ? 'Редактировать публикацию' : 'Edit post')}</strong></div>
                    <button type="button" class="profile-cat-editor-close" onclick="cancelEditCat('${actionId}', event)" aria-label="${escapeHtml(currentLang === 'ru' ? 'Закрыть редактор' : 'Close editor')}"><i class="fa-solid fa-xmark" aria-hidden="true"></i></button>
                </div>
                <label class="profile-cat-editor-field profile-cat-editor-field--row"><span>${escapeHtml(currentLang === 'ru' ? 'Имя' : 'Name')}</span><input id="cat-edit-name-${id}" type="text" maxlength="80" value="${name}" autocomplete="off"></label>
                <label class="profile-cat-editor-field profile-cat-editor-field--row profile-cat-editor-field--bio"><span>${escapeHtml(currentLang === 'ru' ? 'Описание' : 'Bio')}</span><div class="profile-cat-editor-textarea-wrap"><textarea id="cat-edit-bio-${id}" maxlength="1000" rows="2" oninput="updateCatEditCount('${actionId}')">${bio}</textarea><small><span id="cat-edit-count-${id}">${rawBio.length}</span>/1000</small></div></label>
                <div class="profile-cat-editor-actions">
                    <button type="button" class="profile-cat-editor-cancel" onclick="cancelEditCat('${actionId}', event)">${escapeHtml(currentLang === 'ru' ? 'Отмена' : 'Cancel')}</button>
                    <button id="cat-edit-save-${id}" type="button" class="profile-cat-editor-save" onclick="saveEditedCat('${actionId}', event)"><i class="fa-solid fa-check" aria-hidden="true"></i><span>${escapeHtml(currentLang === 'ru' ? 'Сохранить' : 'Save')}</span></button>
                </div>
            </div>` : ''}
        </article>`;
    }).join('');
    updateFavoriteButtons();
}


function updateCatEditCount(catId) {
    const id = String(catId);
    const textarea = document.getElementById(`cat-edit-bio-${id}`);
    const count = document.getElementById(`cat-edit-count-${id}`);
    if (textarea && count) count.textContent = String(textarea.value.length);
}

function startEditCat(catId, event) {
    if (event) event.stopPropagation();
    if (!profileCatsState.own || profileCatsState.tab !== 'uploads') return;
    document.querySelectorAll('.profile-cat-inline-editor').forEach(editor => {
        if (editor.id !== `cat-editor-${catId}`) editor.classList.add('hidden');
    });
    const editor = document.getElementById(`cat-editor-${catId}`);
    if (!editor) return;
    editor.classList.remove('hidden');
    updateCatEditCount(catId);
    requestAnimationFrame(() => document.getElementById(`cat-edit-name-${catId}`)?.focus());
}

function cancelEditCat(catId, event) {
    if (event) event.stopPropagation();
    const editor = document.getElementById(`cat-editor-${catId}`);
    if (editor) editor.classList.add('hidden');
}

async function saveEditedCat(catId, event) {
    if (event) event.stopPropagation();
    if (!currentSession?.access_token) {
        showToast(currentLang === 'ru' ? 'Сначала войдите в аккаунт.' : 'Please sign in first.', 'error');
        return;
    }
    const id = String(catId);
    const nameInput = document.getElementById(`cat-edit-name-${id}`);
    const bioInput = document.getElementById(`cat-edit-bio-${id}`);
    const saveBtn = document.getElementById(`cat-edit-save-${id}`);
    const name = String(nameInput?.value || '').trim();
    const bio = String(bioInput?.value || '').trim();
    if (!name) {
        showToast(currentLang === 'ru' ? 'Введите имя котика.' : 'Enter a cat name.', 'error');
        nameInput?.focus();
        return;
    }
    if (name.length > 80 || bio.length > 1000) return;
    const oldHtml = saveBtn ? saveBtn.innerHTML : '';
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i><span>Saving...</span>';
    }
    try {
        const response = await fetch(`/api/cats/${encodeURIComponent(id)}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${currentSession.access_token}`
            },
            body: JSON.stringify({name, bio})
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || (currentLang === 'ru' ? 'Не удалось сохранить изменения.' : 'Could not save changes.'));
        const cat = profileCatsState.uploads.find(item => String(item.id) === id);
        if (cat) {
            cat.name = name;
            cat.bio = bio;
            cat.description = bio;
        }
        renderProfileCats(profileCatsState.uploads, true);
        showToast(currentLang === 'ru' ? 'Публикация обновлена.' : 'Cat post updated.', 'success');
    } catch (error) {
        showToast(error.message || (currentLang === 'ru' ? 'Не удалось сохранить изменения.' : 'Could not save changes.'), 'error');
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = oldHtml;
        }
    }
}

function switchProfileCatsTab(tab) {
    if (tab === 'favorites' && !profileCatsState.own) return;
    profileCatsState.tab = tab === 'favorites' ? 'favorites' : 'uploads';
    profileCatsState.request++;
    document.getElementById('profile-uploads-tab').setAttribute('aria-pressed', String(profileCatsState.tab === 'uploads'));
    document.getElementById('profile-favorites-tab').setAttribute('aria-pressed', String(profileCatsState.tab === 'favorites'));
    document.getElementById('favorites-private-note').classList.toggle('hidden', profileCatsState.tab !== 'favorites');
    document.getElementById('favorites-pagination').classList.add('hidden');
    if (profileCatsState.tab === 'favorites') return loadFavoriteCats(1);
    renderProfileCats(profileCatsState.uploads, profileCatsState.own);
}

async function loadFavoriteCats(page = 1) {
    if (!profileCatsState.own || profileCatsState.tab !== 'favorites') return;
    profileCatsState.page = Math.max(1, page);
    profileCatsState.dirty = false;
    const request = ++profileCatsState.request;
    document.getElementById('favorites-pagination').classList.add('hidden');
    profileGridMessage(t('loading_favorites'), '');
    try {
        const {data: {session}} = await supabaseClient.auth.getSession();
        if (!session?.user) throw new Error(t('login_to_favorites'));
        if (request !== profileCatsState.request) return;
        const response = await fetch(`/api/user/favorites?page=${profileCatsState.page}`, {headers: {Authorization: `Bearer ${session.access_token}`}});
        const data = await response.json();
        if (request !== profileCatsState.request || currentSession?.user?.id !== session.user.id) return;
        if (!response.ok) throw new Error(data.error || t('favorites_error'));
        if (!data.cats?.length && profileCatsState.page > 1) return loadFavoriteCats(profileCatsState.page - 1);
        renderProfileCats(data.cats || []);
        document.getElementById('favorites-prev').disabled = profileCatsState.page <= 1;
        document.getElementById('favorites-next').disabled = !data.has_next;
        document.getElementById('favorites-page').textContent = `${t('page_label')} ${profileCatsState.page}`;
        document.getElementById('favorites-pagination').classList.toggle('hidden', profileCatsState.page === 1 && !data.has_next);
    } catch (error) {
        if (request === profileCatsState.request) profileGridMessage(t('favorites_error'), error.message, true);
    }
}

window.addEventListener('catrank_favorites_changed', () => {
    if (profileCatsState.tab !== 'favorites') return;
    if (activeModalCatId) profileCatsState.dirty = true;
    else loadFavoriteCats(profileCatsState.page);
});
window.addEventListener('catrank_viewer_closed', () => {
    if (profileCatsState.dirty) loadFavoriteCats(profileCatsState.page);
});
window.addEventListener('catrank_auth_changed', () => {
    if (!currentSession?.user) {
        profileCatsState.own = false;
        document.getElementById('profile-favorites-tab').classList.add('hidden');
        switchProfileCatsTab('uploads');
    }
});
window.addEventListener('catrank_language_changed', () => switchProfileCatsTab(profileCatsState.tab));
window.addEventListener('catrank_like_changed', event => {
    const cat = profileCatsState.uploads.find(item => String(item.id) === event.detail.id);
    if (cat) cat.likes_count = event.detail.likes_count;
});
