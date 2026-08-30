/**
 * CatRank Modern Toast Notification & Custom Dialog Component
 */

function showToast(message, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        container.className = "fixed bottom-5 right-5 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none px-4 sm:px-0";
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    
    let iconHtml = '<i class="fa-solid fa-circle-info text-blue-400 text-sm"></i>';
    let borderColor = "border-slate-800";
    
    if (type === "success") {
        iconHtml = '<i class="fa-solid fa-circle-check text-emerald-400 text-sm"></i>';
        borderColor = "border-emerald-500/30";
    } else if (type === "error") {
        iconHtml = '<i class="fa-solid fa-circle-exclamation text-rose-400 text-sm"></i>';
        borderColor = "border-rose-500/30";
    }

    toast.className = `flex items-center gap-3 px-4 py-3 bg-slate-900/95 backdrop-blur-md text-white text-xs font-semibold rounded-2xl shadow-xl border ${borderColor} transition-all transform duration-300 translate-y-4 opacity-0 pointer-events-auto select-none`;
    
    toast.innerHTML = `
        <div class="flex-shrink-0">${iconHtml}</div>
        <div class="flex-grow">${message}</div>
        <button onclick="this.parentElement.remove()" class="text-slate-400 hover:text-white transition text-xs p-1 focus:outline-none">
            <i class="fa-solid fa-xmark"></i>
        </button>
    `;

    container.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.remove("translate-y-4", "opacity-0");
    });

    setTimeout(() => {
        toast.classList.add("translate-y-4", "opacity-0");
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

/**
 * Custom Styled Promise-Based Confirmation Dialog (Replaces native browser confirm())
 * @param {Object} options - { title, message, confirmText, cancelText, danger, icon, hideCancel }
 * @returns {Promise<boolean>}
 */
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
            // Fallback to native if elements not mounted
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
        if (actionBtn) actionBtn.innerHTML = `<span>${options.confirmText || defaultConfirmText}</span>`;

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

        // Open modal
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

// Global alias
window.showConfirmModal = showConfirmModal;
