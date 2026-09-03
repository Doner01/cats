import re

with open("templates/admin.html", "r") as f:
    content = f.read()

js_replacement = """
let currentTab = 'cats';
let currentPage = { cats: 1, users: 1, comments: 1 };
const LIMIT = 50;

function switchAdminTab(tab) {
    currentTab = tab;
    const tabs = ['cats', 'users', 'comments'];
    const inactiveClass = "pb-3 text-xs sm:text-sm font-extrabold text-slate-400 hover:text-slate-200 transition flex items-center gap-2 flex-shrink-0";
    const activeClass = "pb-3 text-xs sm:text-sm font-extrabold text-indigo-400 border-b-2 border-indigo-500 transition flex items-center gap-2 flex-shrink-0";

    tabs.forEach(t => {
        document.getElementById(`admin-tab-${t}`).classList.add("hidden");
        document.getElementById(`admin-tab-btn-${t}`).className = inactiveClass;
    });

    document.getElementById(`admin-tab-${tab}`).classList.remove("hidden");
    document.getElementById(`admin-tab-btn-${tab}`).className = activeClass;
    
    loadTabData(tab);
}

async function loadTabData(tab) {
    const searchInput = document.getElementById(`admin-search-${tab}`);
    const search = searchInput ? searchInput.value.trim() : "";
    const page = currentPage[tab];
    
    try {
        const res = await fetch(`/api/admin/${tab}?page=${page}&limit=${LIMIT}&search=${encodeURIComponent(search)}`, {
            headers: { "Authorization": `Bearer ${currentSession.access_token}` }
        });
        const data = await res.json();
        
        if (tab === 'cats') {
            allAdminCats = data.cats || [];
            renderAdminCats(allAdminCats);
        } else if (tab === 'users') {
            allAdminUsers = data.users || [];
            renderAdminUsers(allAdminUsers);
        } else if (tab === 'comments') {
            allAdminComments = data.comments || [];
            renderAdminComments(allAdminComments);
        }
        
        renderPagination(tab, data.page, data.total, data.limit);
    } catch (e) {
        showToast("Error loading data: " + e.message, "error");
    }
}

function renderPagination(tab, page, total, limit) {
    const totalPages = Math.ceil(total / limit) || 1;
    let paginationDiv = document.getElementById(`admin-pagination-${tab}`);
    if (!paginationDiv) {
        paginationDiv = document.createElement("div");
        paginationDiv.id = `admin-pagination-${tab}`;
        paginationDiv.className = "flex items-center justify-between p-4 border-t border-slate-100 bg-slate-50";
        document.getElementById(`admin-tab-${tab}`).appendChild(paginationDiv);
    }
    
    paginationDiv.innerHTML = `
        <span class="text-xs text-slate-500 font-medium">Page ${page} of ${totalPages} (Total: ${total})</span>
        <div class="flex gap-2">
            <button onclick="changePage('${tab}', -1)" ${page <= 1 ? 'disabled' : ''} class="px-3 py-1 bg-white border border-slate-200 text-slate-600 rounded-lg text-xs font-bold hover:bg-slate-50 disabled:opacity-50">Prev</button>
            <button onclick="changePage('${tab}', 1)" ${page >= totalPages ? 'disabled' : ''} class="px-3 py-1 bg-white border border-slate-200 text-slate-600 rounded-lg text-xs font-bold hover:bg-slate-50 disabled:opacity-50">Next</button>
        </div>
    `;
}

function changePage(tab, delta) {
    currentPage[tab] += delta;
    loadTabData(tab);
}

// Debounce search function
let searchTimeout;
function handleSearch(tab, value) {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        currentPage[tab] = 1;
        loadTabData(tab);
    }, 500);
}

function filterAdminCats(query) { handleSearch('cats', query); }
function filterAdminUsers(query) { handleSearch('users', query); }
function filterAdminComments(query) { handleSearch('comments', query); }

async function loadAdminData() {
    if (!currentSession || !currentSession.access_token) {
        showToast("Please sign in with an admin account.", "error");
        setTimeout(() => window.location.href = "/login", 800);
        return;
    }

    try {
        const res = await fetch("/api/admin/overview", {
            headers: { "Authorization": `Bearer ${currentSession.access_token}` }
        });
        
        if (!res.ok) {
            const errData = await res.json();
            showToast(errData.error || "Admin access denied.", "error");
            setTimeout(() => window.location.href = "/", 1000);
            return;
        }

        const data = await res.json();
        document.getElementById("stat-total-cats").innerText = data.total_cats || 0;
        document.getElementById("stat-total-likes").innerText = data.total_likes || 0;
        document.getElementById("stat-total-users").innerText = data.total_users || 0;
        document.getElementById("stat-total-comments").innerText = data.total_comments || 0;

        loadTabData(currentTab);

    } catch (e) {
        showToast("Error loading admin data: " + e.message, "error");
    }
}
"""

# Replace the block from `let allAdminCats` down to the end of `loadAdminData`
start_match = re.search(r'let allAdminCats = \[\];', content)
end_match = re.search(r'function safeAdminImageUrl', content)

if start_match and end_match:
    new_content = content[:start_match.start()] + js_replacement + "\n" + content[end_match.start():]
    
    # We also need to remove the frontend filtering logic since we do it via API now.
    new_content = re.sub(r'function filterAdminCats.*?\}\n', '', new_content, flags=re.DOTALL)
    new_content = re.sub(r'function filterAdminUsers.*?\}\n', '', new_content, flags=re.DOTALL)
    new_content = re.sub(r'function filterAdminComments.*?\}\n', '', new_content, flags=re.DOTALL)
    
    with open("templates/admin.html", "w") as f:
        f.write(new_content)
    print("Patched admin.html")
else:
    print("Could not find targets in admin.html")

