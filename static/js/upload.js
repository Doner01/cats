let previewObjectUrl = null;
const fileInput = document.getElementById("cat-file");
const previewContainer = document.getElementById("preview-container");
const previewImg = document.getElementById("image-preview");
const dropZone = document.getElementById("drop-zone");

const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
const ALLOWED_IMAGE_EXTS = ['jpg', 'jpeg', 'png', 'webp', 'jfif', 'gif'];
const MAX_IMAGE_SIZE = 5 * 1024 * 1024; // 5MB

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
    if (!file) return;
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    if (!ALLOWED_IMAGE_EXTS.includes(ext) || (!ALLOWED_IMAGE_TYPES.includes(file.type) && file.type !== '')) {
        showToast(typeof t === 'function' ? t('file_error_invalid_type') : "Invalid image format. Allowed: JPG, JPEG, PNG, WEBP, GIF.", "error");
        fileInput.value = "";
        if (previewContainer) previewContainer.classList.add("hidden");
        return;
    }
    if (file.size > MAX_IMAGE_SIZE) {
        showToast(typeof t === 'function' ? t('file_error_too_large') : "Image must be smaller than 5MB.", "error");
        fileInput.value = "";
        if (previewContainer) previewContainer.classList.add("hidden");
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

        if (typeof supabaseClient === "undefined" || !supabaseClient) {
            showToast("Supabase client not initialized.", "error");
            return;
        }

        const { data: { session } } = await supabaseClient.auth.getSession();
        if (!session) {
            showToast(typeof t === 'function' ? t('toast_need_signin_vote') : "Please sign in to upload a cat.", "info");
            setTimeout(() => window.location.href = "/login", 800);
            return;
        }

        const nameInput = document.getElementById("cat-name");
        const submitBtn = document.getElementById("submit-btn");

        if (!fileInput.files || fileInput.files.length === 0) {
            showToast("Please select an image file.", "error");
            return;
        }

        const file = fileInput.files[0];
        const ext = (file.name.split('.').pop() || '').toLowerCase();
        if (!ALLOWED_IMAGE_EXTS.includes(ext)) {
            showToast("Invalid file format. Allowed: JPG, PNG, WEBP, GIF.", "error");
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

            const result = await res.json();

            if (res.ok) {
                showToast(typeof t === 'function' ? t('toast_upload_success') : "Cat uploaded successfully! Redirecting...", "success");
                setTimeout(() => {
                    window.location.href = "/";
                }, 800);
            } else {
                showToast(result.error || "Upload failed.", "error");
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up text-xs"></i> <span>' + (typeof t === 'function' ? t('upload_submit_btn') : "Upload Photo") + '</span>';
            }
        } catch (err) {
            showToast("Network error: " + err.message, "error");
            submitBtn.disabled = false;
            submitBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up text-xs"></i> <span>' + (typeof t === 'function' ? t('upload_submit_btn') : "Upload Photo") + '</span>';
        }
    });
}
