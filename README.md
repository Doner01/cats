# 🐱 CatRank — Ultimate Community Cat Voting & Leaderboard Platform

**CatRank** is a modern, full-featured web platform for sharing cat photos, participating in community voting, exploring live ranked leaderboards, discussing cat photos in threaded comment discussions, and managing community creators via a comprehensive administrator dashboard.

Built with **Python (Flask)**, **Supabase (PostgreSQL Auth & Storage)**, **Tailwind CSS**, and modern JavaScript.

---

## 🌟 Key Features

1. **🏆 Community Feed & Live Leaderboard**:
   - Ranked leaderboard with top 3 Champion podium (Gold, Silver, Bronze).
   - Live optimistic voting system with 10-second spam protection cooldown.
   - Real-time client-side search and instant filters (*All Cats, Most Voted, Newest*).
   - Top #1 Champion spotlight banner and featured YouTube video showcase.

2. **💬 Single-Depth Threaded Comment & Reply System**:
   - Interactive full-screen image preview modal for inspecting cats.
   - Single-depth threaded discussions with vertical connector lines and `@username` reply badges.
   - Real-time comment submission, deletion, and in-app activity notifications.

3. **📸 Cat Photo Upload with Story/Bio & File Security**:
   - Upload cat photo with cat name and optional **Cat Bio / Story**.
   - Strict binary magic-number validation supporting **PNG, JPG, JPEG, WEBP, GIF, JFIF** (max 5MB).
   - User-isolated Supabase Storage paths (`{user_id}/{filename}`) with full Row Level Security (RLS).

4. **👤 Comprehensive User Profile & Account Settings**:
   - Display name, avatar, bio, email badge, and phone number support.
   - Profile management modal with tabs for **Basic Info** and **Account & Security** (email change, password change).
   - Public creator profile URLs (`/user/<user_id>`) with verified user validation (404 for non-existent IDs).

5. **🔐 Authentication & Password Recovery**:
   - Email/password authentication via Supabase Auth.
   - Optional profile avatar, phone number, and bio inputs during registration.
   - Forgot Password & Reset Password workflow with automatic recovery token handling.

6. **🛡️ Multi-Section Admin Dashboard (`/admin`)**:
   - **Uploaded Cats**: Live editing of cat names, bio, and vote totals; permanent force delete.
   - **Community Users**: Creator table displaying avatars, emails, phone numbers, roles, upload counts, and vote aggregates; live user profile editor and account management.
   - **Comments Management**: Search and moderate community comments across all cats.

7. **📱 Fully Responsive Multi-Device UI & Bilingual Support**:
   - Responsive layouts optimized for **Mobile Phones (<640px)**, **Tablets / Planshet (640px–1024px)**, and **Desktop PC (≥1024px)**.
   - Mobile-optimized bottom navigation bar for one-thumb phone usage.
   - Complete bilingual internationalization for **English (EN)** and **Russian (RU)**.

---

## 🚀 Quick Start & Installation

### 1. Prerequisites
- Python 3.9+ installed
- Node.js (optional) / Git

### 2. Setup Virtual Environment

#### On Windows:
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

#### On Linux / macOS / Arch / CachyOS:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. VS Code / IDE Python Environment Selection
To ensure Pyright / VS Code resolves all imports cleanly without warnings:
1. Open VS Code in the project folder.
2. Press `Ctrl + Shift + P` (or `Cmd + Shift + P` on Mac).
3. Search for: **`Python: Select Interpreter`**.
4. Choose the interpreter inside your `./venv` directory (e.g. `./venv/bin/python` or `.\venv\Scripts\python.exe`).

### 4. Supabase Database Migration
1. Open your [Supabase Project Dashboard](https://supabase.com/dashboard).
2. Go to the **SQL Editor**.
3. Copy the entire contents of `supabase_migration.sql` and run it.
4. This will create the `profiles`, `cats`, `likes`, `comments`, and `notifications` tables, storage buckets (`cat-images`, `avatars`), and all Row Level Security (RLS) policies.

### 5. Configure Environment Variables
Create a `.env` file in the root directory (or copy from `.env.example`):
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
SECRET_KEY=your-flask-secret-key
ADMIN_EMAIL=your-admin-email@example.com
```

### 6. Run the Application

#### Development Mode:
```bash
python app.py
```
Open your browser and navigate to: `http://localhost:5000`

#### Production Mode with Gunicorn:
```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

---

## 📁 Project Architecture

```
CatRank/
├── app.py                      # Core Flask application, routing, APIs, and security
├── supabase_migration.sql      # Complete PostgreSQL schema, triggers, & RLS policies
├── requirements.txt            # Python dependencies
├── vercel.json                 # Vercel serverless deployment configuration
├── pyrightconfig.json          # Pyright / VS Code type checker configuration
├── .vscode/
│   └── settings.json           # VS Code Python environment settings
├── templates/
│   ├── base.html               # Base layout, navbar, mobile bottom bar, and modal
│   ├── index.html              # Home feed, champion spotlight, video banner
│   ├── leaderboard.html        # Community leaderboard & podium
│   ├── upload.html             # Cat photo upload with name, bio, dropzone
│   ├── profile.html            # User account page, gallery, and settings modal
│   ├── login.html              # Sign in page with forgot password link
│   ├── register.html           # Registration form with optional phone & avatar
│   ├── forgot_password.html    # Password reset link request page
│   ├── reset_password.html     # New password configuration page
│   └── admin.html              # Admin dashboard (Cats, Users, Comments)
└── static/
    ├── css/
    │   └── style.css           # Modern design system, glassmorphism, responsive queries
    └── js/
        ├── auth.js             # Supabase Auth, registration, session management
        ├── main.js             # Modal interactions, voting, threaded comments
        ├── translations.js     # Bilingual translation engine (EN / RU)
        ├── toast.js            # Toast notifications
        └── upload.js           # Client-side image validation & drag-drop handling
```

---

## 📄 License
MIT License. Built for cat lovers worldwide! 🐾


## Storage architecture

- Supabase: Auth + PostgreSQL tables (`profiles`, `cats`, `likes`, `comments`, `notifications`).
- Cloudflare R2: cat images and profile avatars.
- `cats.image_url` and `profiles.avatar_url` store the public R2 URL.
- The Flask backend uploads/deletes R2 objects; the browser loads images directly from the R2 public domain.
- Do not commit `.env`. Configure `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`, and the R2 variables in your deployment environment.

## Registration and password-reset email behavior

- Registration uses `supabase.auth.signUp()` with an explicit `emailRedirectTo` of `/login?verified=1`. When Supabase requires email confirmation, the signup call itself sends the verification email and the site shows the Check Your Email card.
- The registration client detects Supabase's obfuscated existing-user response (`user.identities` empty) and does not show a false account-created state.
- For verification emails to be sent, enable the Email provider and **Confirm Email** in Supabase Authentication settings. If Confirm Email is disabled, Supabase returns a session immediately and there is no verification email to send.
- Password reset uses `resetPasswordForEmail()`. Supabase intentionally does not reveal whether an email exists and does not send a reset email when no user is associated with that address; the page therefore uses neutral wording instead of claiming a message was definitely sent.

## Account email-change flow

The profile email-change form now uses Supabase Auth confirmation instead of the server admin API. A user must verify the current password, a confirmation email is sent to the requested new address, and the account email is synchronized into `profiles` only after Supabase completes the confirmation redirect.

For the exact flow requested (confirmation to the **new email only**), disable **Secure email change** in Supabase Authentication > Providers > Email. Supabase documents that this sends the confirmation to the new email only; with Secure email change enabled, the normal flow requires confirmation on both the current and new addresses.

Do **not** use a server-side `auth.admin.update_user_by_id(..., {"email": ...})` for a normal user's email change because that bypasses the confirmation flow.

Make sure the production site URL and `/profile` are included in Supabase Authentication URL configuration so the confirmation redirect is accepted.


## Performance optimizations

This build reduces unnecessary work on every request:
- Public feed and leaderboard reads use short in-process caching (default 8 seconds) and invalidate immediately after uploads, edits, deletes, and votes.
- Feed/leaderboard queries select only required columns instead of `*`.
- Avatar resolution no longer performs one Supabase Auth Admin request per card; it uses the stored avatar URL or a deterministic local fallback.
- Notifications are fetched only when the notification menu is opened, instead of on every page load.
- User like synchronization only runs on pages that actually contain vote controls.
- Profile page loading no longer calls the profile-existence endpoint on every visit; profile creation is checked only when account data is edited.
- Cat modal details are cached for the current page session.
- Public static assets receive browser cache headers.
- Homepage feed/leaderboard images use lazy decoding/loading, and the YouTube embed is lazy-loaded by the browser.
- Supabase SQL indexes were added for the feed, leaderboard, likes, comments, and notifications.
- A `toggle_cat_like` SQL function provides a fast atomic one-RPC vote path, with a compatibility fallback for older databases.

After deploying this build, run the updated `supabase_migration.sql` once so the performance indexes and `toggle_cat_like` function are created.
