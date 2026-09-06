let previewObjectUrl = null;
const fileInput = document.getElementById("cat-file");
const previewContainer = document.getElementById("preview-container");
const previewImg = document.getElementById("image-preview");
const dropZone = document.getElementById("drop-zone");

const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
const ALLOWED_IMAGE_EXTS = ['jpg', 'jpeg', 'png', 'webp', 'jfif', 'gif'];
const uploadConfig = document.getElementById('upload-config');
const configuredMax = Number(uploadConfig?.dataset.maxBytes || 0);
const MAX_IMAGE_SIZE = Number.isFinite(configuredMax) && configuredMax > 0 ? configuredMax : 5 * 1024 * 1024;
const MAX_IMAGE_MB = Math.max(1, Math.floor(MAX_IMAGE_SIZE / (1024 * 1024)));

if (fileInput) {
    fileInput.addEventListener("change", () => {
        if (fileInput.files && fileInput.files.length > 0) {
            handleFileSelect(fileInput.files[0]);
        }
    });
}

if (dropZone) {
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        showInlineError("upload-form");
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.add('border-indigo-500', 'bg-indigo-50/50'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => dropZone.classList.remove('border-indigo-500', 'bg-indigo-50/50'), false);
    });

    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files.length > 0) {
            fileInput.files = files;
            handleFileSelect(files[0]);
        }
    });
}

function handleFileSelect(file) {
    showInlineError("upload-form");
    if (!file) return;
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    if (!ALLOWED_IMAGE_EXTS.includes(ext) || (!ALLOWED_IMAGE_TYPES.includes(file.type) && file.type !== '')) {
        showInlineError("upload-form", typeof t === 'function' ? t('file_error_invalid_type') : "Invalid image format. Allowed: JPG, JPEG, PNG, WEBP, GIF.");
        clearUploadPreview();
        return;
    }
    if (file.size > MAX_IMAGE_SIZE) {
        showInlineError("upload-form", `Image must be smaller than ${MAX_IMAGE_MB}MB.`);
        clearUploadPreview();
        return;
    }

    if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl);
    previewObjectUrl = URL.createObjectURL(file);
    if (previewImg) previewImg.src = previewObjectUrl;
    if (previewContainer) previewContainer.classList.remove("hidden");
}

const uploadForm = document.getElementById("upload-form");
if (uploadForm) {
    uploadForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        showInlineError("upload-form");

        if (typeof supabaseClient === "undefined" || !supabaseClient) {
            showInlineError("upload-form", friendlyFormError(503));
            return;
        }

        const { data: { session } } = await supabaseClient.auth.getSession();
        if (!session) {
            showInlineError("upload-form", friendlyFormError(401));
            return;
        }

        const nameInput = document.getElementById("cat-name");
        const submitBtn = document.getElementById("submit-btn");

        if (!fileInput.files || fileInput.files.length === 0) {
            showInlineError("upload-form", "Please select an image file.");
            return;
        }

        const file = fileInput.files[0];
        const ext = (file.name.split('.').pop() || '').toLowerCase();
        if (!ALLOWED_IMAGE_EXTS.includes(ext)) {
            showInlineError("upload-form", "Invalid file format. Allowed: JPG, PNG, WEBP, GIF.");
            return;
        }

        const bioInput = document.getElementById("cat-bio");
        const formData = new FormData();
        formData.append("file", file);
        formData.append("name", nameInput.value.trim() || "Whiskers");
        if (bioInput) {
            formData.append("bio", bioInput.value.trim());
        }

        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-xs"></i> <span>Uploading cat...</span>';

        try {
            const res = await fetch("/api/cats/upload", {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${session.access_token}`
                },
                body: formData
            });

            const responseText = await res.text();
            let result = {};
            try {
                result = responseText ? JSON.parse(responseText) : {};
            } catch (_) {
                result = { error: res.status >= 500 ? "The server could not complete the upload. Please try again." : responseText };
            }

            if (res.ok) {
                showToast(typeof t === 'function' ? t('toast_upload_success') : "Cat uploaded successfully! Redirecting...", "success");
                setTimeout(() => {
                    window.location.href = "/";
                }, 800);
            } else {
                showInlineError("upload-form", res.status === 400 ? feedbackText("Please check the image and upload details.", "Проверьте изображение и данные загрузки.") : friendlyFormError(res.status));
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up text-xs"></i> <span>' + (typeof t === 'function' ? t('upload_submit_btn') : "Upload Photo") + '</span>';
            }
        } catch (err) {
            showInlineError("upload-form", friendlyFormError("network"));
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up text-xs"></i> <span>' + (typeof t === 'function' ? t('upload_submit_btn') : "Upload Photo") + '</span>';
        }
    });
}
