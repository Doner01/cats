document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.nav-desktop-links a, .mobile-bottom-nav a').forEach(link => {
        if (link.pathname === location.pathname) link.setAttribute('aria-current', 'page');
    });
    document.querySelectorAll('[onclick^="openCatModal"]').forEach(control => {
        if (control.tagName !== 'BUTTON') {
            control.setAttribute('role', 'button');
            control.tabIndex = 0;
            control.addEventListener('keydown', event => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    control.click();
                }
            });
        }
    });
    const stack = [];
    const modals = [...document.querySelectorAll('.modal-backdrop')];
    const focusable = modal => [...modal.querySelectorAll('button, a[href], input:not([type=hidden]), textarea, select, [tabindex="0"]')].filter(el => !el.disabled && el.getClientRects().length);
    const observer = new MutationObserver(() => {
        modals.forEach(modal => {
            const visible = !modal.classList.contains('hidden');
            const index = stack.findIndex(item => item.modal === modal);
            if (visible && index < 0) {
                const previous = document.activeElement;
                stack.push({ modal, previous });
                modal.setAttribute('role', 'dialog');
                modal.setAttribute('aria-modal', 'true');
                if (!modal.hasAttribute('aria-labelledby') && !modal.hasAttribute('aria-label')) modal.setAttribute('aria-label', modal.querySelector('h2,h3')?.textContent || 'Dialog');
                modal.tabIndex = -1;
                (modal.querySelector('[data-modal-initial-focus]') || focusable(modal)[0] || modal).focus({preventScroll: true});
            } else if (!visible && index >= 0) {
                const [{previous}] = stack.splice(index, 1);
                if (previous?.isConnected) previous.focus({preventScroll: true});
            }
        });
        document.body.style.overflow = stack.length ? 'hidden' : '';
    });
    modals.forEach(modal => observer.observe(modal, {attributes: true, attributeFilter: ['class']}));
    document.addEventListener('keydown', event => {
        const modal = stack.at(-1)?.modal;
        if (!modal) return;
        if (event.key === 'Tab') {
            const controls = focusable(modal);
            const first = controls[0] || modal;
            const last = controls.at(-1) || modal;
            if (event.shiftKey && (document.activeElement === first || document.activeElement === modal)) {event.preventDefault();last.focus();}
            else if (!event.shiftKey && document.activeElement === last) {event.preventDefault();first.focus();}
        }
        if (event.key === 'Escape') {
            if (modal.id === 'custom-confirm-modal') return;
            // While a comment is being edited, Escape cancels that editor.
            // Do not also close the parent cat viewer.
            if (modal.id === 'cat-detail-modal' && modal.querySelector('.comment-inline-editor')) return;
            if (modal.id === 'cat-detail-modal') closeCatModal();
            else if (modal.id === 'edit-profile-modal') closeEditProfileModal();
            else modal.classList.add('hidden');
        }
    });
});
