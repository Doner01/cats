function feedbackText(en, ru) {
    return typeof currentLang !== 'undefined' && currentLang === 'ru' ? ru : en;
}

function friendlyFormError(status, kind = 'form') {
    const messages = {
        401: ['Your session expired. Please sign in again.', 'Сессия истекла. Пожалуйста, войдите снова.'],
        403: ["You don't have permission to do that.", 'У вас нет разрешения на это действие.'],
        429: kind === 'comment'
            ? ["You're commenting too quickly. Please wait a moment.", 'Вы отправляете комментарии слишком быстро. Подождите немного.']
            : ['Too many attempts. Please wait a moment.', 'Слишком много попыток. Подождите немного.'],
        503: kind === 'comment'
            ? ['Comments are temporarily unavailable. Please try again.', 'Комментарии временно недоступны. Попробуйте ещё раз.']
            : ['Service is temporarily unavailable. Please try again.', 'Сервис временно недоступен. Попробуйте ещё раз.'],
        network: ['Connection problem. Check your internet and try again.', 'Проблема с соединением. Проверьте интернет и попробуйте ещё раз.']
    };
    return feedbackText(...(messages[status] || (kind === 'comment'
        ? ['Could not post your comment. Please try again.', 'Не удалось отправить комментарий. Попробуйте ещё раз.']
        : ['Could not save your changes. Please try again.', 'Не удалось сохранить изменения. Попробуйте ещё раз.'])));
}

function showInlineError(target, message = '') {
    const host = typeof target === 'string' ? document.getElementById(target) : target;
    if (!host) return;
    let status = host.matches('[data-inline-error]') ? host : host.querySelector('[data-inline-error]');
    if (!status) {
        status = document.createElement('p');
        status.dataset.inlineError = '';
        status.className = 'form-inline-error';
        host.appendChild(status);
    }
    status.setAttribute('role', 'alert');
    status.textContent = message;
    status.hidden = !message;
    status.classList.toggle('hidden', !message);
}

function showToast(message, type = 'info', options = {}) {
    const text = String(message ?? '').trim();
    if (!text) return;
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }
    if ([...container.children].some(item => item.dataset.message === text)) return;
    // Bound the stack so it cannot grow over the page controls.
    while (container.children.length >= 2) container.firstElementChild.remove();
    const toast = document.createElement('div');
    toast.className = 'global-toast global-toast--' + (['success', 'error', 'info', 'warning'].includes(type) ? type : 'info');
    toast.dataset.message = text;
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    const icon = document.createElement('span');
    icon.className = 'global-toast__icon';
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = type === 'success' ? '✓' : type === 'error' ? '!' : 'i';
    const copy = document.createElement('div');
    const title = document.createElement('strong');
    title.textContent = options.title || (type === 'success' ? feedbackText('Saved', 'Готово')
        : type === 'error' ? feedbackText('Something went wrong', 'Что-то пошло не так') : feedbackText('Notice', 'Уведомление'));
    const body = document.createElement('p');
    body.textContent = text;
    copy.append(title, body);
    const close = document.createElement('button');
    close.type = 'button';
    close.textContent = '×';
    close.setAttribute('aria-label', feedbackText('Close notification', 'Закрыть уведомление'));
    let timer;
    const dismiss = () => { clearTimeout(timer); toast.remove(); };
    close.addEventListener('click', dismiss);
    toast.append(icon, copy, close);
    container.appendChild(toast);
    positionGlobalToasts();
    const schedule = () => { timer = setTimeout(dismiss, type === 'error' ? 6000 : 4500); };
    toast.addEventListener('mouseenter', () => clearTimeout(timer));
    toast.addEventListener('mouseleave', schedule);
    toast.addEventListener('focusin', () => clearTimeout(timer));
    toast.addEventListener('focusout', schedule);
    schedule();
}

function positionGlobalToasts() {
    const host = document.getElementById('toast-container');
    if (!host) return;
    host.style.top = '';
    const modal = document.getElementById('cat-detail-modal');
    const modalOpen = modal && !modal.classList.contains('hidden');
    const protectedControl = modalOpen ? modal.querySelector('[data-modal-initial-focus]') : document.querySelector('.glass-nav');
    if (!protectedControl) return;
    const control = protectedControl.getBoundingClientRect();
    const stack = host.getBoundingClientRect();
    if (stack.left < control.right && stack.right > control.left && stack.top < control.bottom && stack.bottom > control.top) {
        host.style.top = `${control.bottom + 12}px`;
    }
}
window.addEventListener('resize', positionGlobalToasts);

function showConfirmModal(options = {}) {
    return new Promise((resolve) => {
        const modal = document.getElementById("custom-confirm-modal");
        const box = document.getElementById("custom-confirm-box");
        const titleEl = document.getElementById("custom-confirm-title");
        const msgEl = document.getElementById("custom-confirm-message");
        const iconBg = document.getElementById("custom-confirm-icon-bg");
        const iconEl = document.getElementById("custom-confirm-icon");
        const cancelBtn = document.getElementById("custom-confirm-cancel-btn");
        const actionBtn = document.getElementById("custom-confirm-action-btn");

        if (!modal || !box) {
            resolve(window.confirm(options.message || "Are you sure?"));
            return;
        }

        const isDanger = options.danger !== false;
        const lang = (typeof currentLang !== "undefined" && currentLang) ? currentLang : (localStorage.getItem("catrank_lang") || "en");
        
        const defaultTitle = isDanger 
            ? (lang === "ru" ? "Подтверждение удаления" : "Confirm Action")
            : (lang === "ru" ? "Внимание" : "Notice");

        const defaultConfirmText = isDanger
            ? (lang === "ru" ? "Удалить" : "Delete")
            : (lang === "ru" ? "Продолжить" : "Confirm");

        const defaultCancelText = lang === "ru" ? "Отмена" : "Cancel";

        if (titleEl) titleEl.textContent = options.title || defaultTitle;
        if (msgEl) msgEl.textContent = options.message || "";
        
        if (cancelBtn) cancelBtn.textContent = options.cancelText || defaultCancelText;
        if (actionBtn) {
            actionBtn.replaceChildren();
            const actionLabel = document.createElement("span");
            actionLabel.textContent = String(options.confirmText || defaultConfirmText);
            actionBtn.appendChild(actionLabel);
        }

        if (options.hideCancel && cancelBtn) {
            cancelBtn.classList.add("hidden");
        } else if (cancelBtn) {
            cancelBtn.classList.remove("hidden");
        }

        if (isDanger) {
            if (iconBg) iconBg.className = "w-12 h-12 rounded-2xl bg-rose-50 border border-rose-100 flex items-center justify-center flex-shrink-0 text-rose-600 shadow-xs";
            if (iconEl) iconEl.className = options.icon || "fa-solid fa-trash-can text-xl";
            if (actionBtn) actionBtn.className = "px-5 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-700 active:bg-rose-800 text-white text-xs font-bold transition shadow-md flex items-center gap-1.5";
        } else {
            if (iconBg) iconBg.className = "w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center flex-shrink-0 text-indigo-600 shadow-xs";
            if (iconEl) iconEl.className = options.icon || "fa-solid fa-circle-question text-xl";
            if (actionBtn) actionBtn.className = "px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white text-xs font-bold transition shadow-md flex items-center gap-1.5";
        }
        modal.classList.remove("hidden", "opacity-0", "pointer-events-none");
        modal.classList.add("flex", "opacity-100", "pointer-events-auto");
        box.classList.remove("scale-95");
        box.classList.add("scale-100");

        function cleanup(result) {
            modal.classList.remove("opacity-100", "pointer-events-auto");
            modal.classList.add("opacity-0", "pointer-events-none");
            box.classList.remove("scale-100");
            box.classList.add("scale-95");
            setTimeout(() => {
                modal.classList.remove("flex");
                modal.classList.add("hidden");
            }, 200);

            if (cancelBtn) cancelBtn.removeEventListener("click", onCancel);
            if (actionBtn) actionBtn.removeEventListener("click", onConfirm);
            modal.removeEventListener("click", onBackdrop);
            document.removeEventListener("keydown", onKey);
            resolve(result);
        }

        function onCancel(e) {
            e.preventDefault();
            cleanup(false);
        }

        function onConfirm(e) {
            e.preventDefault();
            cleanup(true);
        }

        function onBackdrop(e) {
            if (e.target === modal) {
                e.preventDefault();
                cleanup(false);
            }
        }

        function onKey(e) {
            if (e.key === "Escape") {
                e.preventDefault();
                cleanup(false);
            }
            if (e.key === "Enter" && !options.hideCancel) {
                e.preventDefault();
                cleanup(true);
            }
        }

        if (cancelBtn) cancelBtn.addEventListener("click", onCancel);
        if (actionBtn) actionBtn.addEventListener("click", onConfirm);
        modal.addEventListener("click", onBackdrop);
        document.addEventListener("keydown", onKey);
        
        if (actionBtn) actionBtn.focus();
    });
}
window.showConfirmModal = showConfirmModal;
