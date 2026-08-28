const fileInput = document.getElementById("cat-file");
const previewContainer = document.getElementById("preview-container");
const previewImg = document.getElementById("image-preview");
const dropZone = document.getElementById("drop-zone");

if (fileInput) {
    fileInput.addEventListener("change", () => {
        if (fileInput.files && fileInput.files[0]) {
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
        if (files && files.length > 0) {
            fileInput.files = files;
            handleFileSelect(files[0]);
        }
    });
}

function handleFileSelect(file) {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
        showToast("Image must be smaller than 5MB.", "error");
        if (fileInput) fileInput.value = "";
        if (previewContainer) previewContainer.classList.add("hidden");
        return;
    }
    if (previewImg) previewImg.src = URL.createObjectURL(file);
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
            showToast(typeof t === "function" ? t("toast_need_signin_vote") : "Please sign in to upload a cat.", "info");
            setTimeout(() => window.location.href = "/login", 800);
            return;
        }

        const nameInput = document.getElementById("cat-name");
        const bioInput = document.getElementById("cat-bio");
        const submitBtn = document.getElementById("submit-btn");

        if (!fileInput.files || fileInput.files.length === 0) {
            showToast("Please select an image file.", "error");
            return;
        }

        const formData = new FormData();
        formData.append("file", fileInput.files[0]);
        formData.append("name", nameInput.value.trim());
        formData.append("bio", bioInput ? bioInput.value.trim() : "");

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin text-xs"></i> <span>${typeof t === "function" ? t("uploading_btn") : "Uploading..."}</span>`;
        }

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
                showToast("Cat uploaded successfully! Redirecting...", "success");
                setTimeout(() => {
                    window.location.href = "/";
                }, 800);
            } else {
                showToast(result.error || "Upload failed.", "error");
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = `<i class="fa-solid fa-cloud-arrow-up text-xs"></i> <span>${typeof t === "function" ? t("upload_submit_btn") : "Upload Photo"}</span>`;
                }
            }
        } catch (err) {
            showToast("Network error: " + err.message, "error");
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = `<i class="fa-solid fa-cloud-arrow-up text-xs"></i> <span>${typeof t === "function" ? t("upload_submit_btn") : "Upload Photo"}</span>`;
            }
        }
    });
}
