/**
 * CatRank Bilingual Translation Module (English / Russian)
 */
const translations = {
    en: {
        // Navigation
        "nav_brand": "CatRank",
        "nav_feed": "Feed",
        "nav_leaderboard": "Leaderboard",
        "nav_upload": "Upload Cat",
        "nav_signin": "Sign In",
        "nav_signup": "Sign Up",
        "nav_signout": "Sign Out",
        "nav_profile": "Profile",
        "nav_admin": "Admin Panel",
        "nav_notifications": "Notifications",

        // Notifications
        "notifications_title": "Notifications",
        "notif_mark_read": "Mark all read",
        "notif_empty": "No notifications yet",
        "notif_footer": "Activity updates",
        "notif_clear_all": "Clear all",
        "notif_new": "new",
        "notif_liked": "liked your cat photo",
        "notif_commented": "commented on",
        "notif_replied": "replied to your comment on",

        // Feed & Home Page
        "feed_title": "Community Feed",
        "feed_subtitle": "Click any cat photo to preview, like, and comment",
        "champion_badge": "Community Champion #1",
        "champion_desc": "The most beloved cat of the community with",
        "champion_votes": "votes! Click below to see all ranked cats.",
        "view_and_comment": "View & Comment",
        "leaderboard_podium": "Leaderboard Podium",
        "featured_badge": "Featured Spotlight",
        "featured_title": "Funny & Cute Cats Compilation",
        "featured_desc": "Enjoy the cutest cat moments and vote for your favorite feline friends uploaded by the community today!",
        "share_cat_btn": "Share Your Cat Photo",
        "search_placeholder": "Search cats by name...",
        "no_cats_title": "No cats uploaded yet",
        "no_cats_desc": "Be the first to share your feline friend with the world!",
        "upload_first_btn": "Upload First Cat",
        "no_search_title": "No matching cats found",
        "no_search_desc": "Try searching for a different name",
        "uploaded_on": "Uploaded on",
        "by_author": "by",
        "votes": "votes",
        "double_click_hint": "Double click photo to vote",

        // Modal & Threaded Comments
        "modal_comments_title": "Comments",
        "comment_placeholder": "Add a comment... (10s cooldown)",
        "reply_placeholder": "Write a reply... (10s cooldown)",
        "reply_btn": "Reply",
        "replying_to": "Replying to",
        "cancel_reply": "Cancel",
        "post_btn": "Post",
        "no_comments": "No comments yet. Be the first to say something nice!",
        "loading_comments": "Loading comments...",
        "delete_comment_confirm": "Are you sure you want to delete this comment?",
        "delete_cat_confirm": "Are you sure you want to delete this cat photo?",
        "view_replies": "replies",
        "delete_btn": "Delete",
        "close_modal": "Close",

        // Leaderboard Page
        "hall_of_fame": "Hall of Fame",
        "leaderboard_title": "Cat Leaderboard",
        "leaderboard_subtitle": "Ranked by total community votes • Click any cat to preview",
        "added_date": "Added",
        "no_leaderboard_cats": "No cats on the leaderboard yet.",
        "leaderboard_remaining_title": "Community Rankings (Rank #4+)",
        "all_top_cats_on_podium": "All top cats are showcased on the podium above!",

        // Upload Page
        "upload_page_title": "Upload Cat Photo",
        "upload_daily_limit": "Share your cat photo and join the community leaderboard!",
        "cat_name_label": "Cat Name",
        "cat_name_placeholder": "e.g. Luna, Simba, Mochi",
        "photo_label": "Photo (PNG, JPG, WEBP, max 5MB)",
        "drop_drag_text": "Click to browse or drag & drop",
        "drop_format_text": "PNG, JPG, or WEBP up to 5MB",
        "preview_label": "Preview",
        "upload_submit_btn": "Upload Photo",
        "uploading_btn": "Uploading...",

        // Auth Pages
        "welcome_back_title": "Welcome Back",
        "login_subtitle": "Sign in to vote, comment, and upload cat pictures",
        "join_community_title": "Join CatRank",
        "register_subtitle": "Create an account to upload, vote, and share cat pictures",
        "email_label": "Email Address",
        "password_label": "Password",
        "confirm_password_label": "Confirm Password",
        "display_name_label": "Display Name / Username",
        "display_name_placeholder": "e.g. CatWhisperer",
        "signin_submit_btn": "Sign In",
        "signup_submit_btn": "Create Account",
        "no_account_text": "Don't have an account?",
        "has_account_text": "Already have an account?",
        "goto_register_link": "Create an account / Sign Up",
        "goto_login_link": "Sign In here",

        // Profile Page
        "profile_bio_default": "CatRank Member • Cat enthusiast",
        "stat_uploads": "Uploads",
        "stat_total_votes": "Total Votes",
        "edit_profile_btn": "Edit Profile",
        "change_photo": "Change",
        "edit_profile_title": "Edit Profile",
        "profile_photo_label": "Profile Photo",
        "upload_new_photo": "Choose Photo",
        "btn_default_avatar": "Reset",
        "cancel_modal_btn": "Cancel",
        "save_changes_btn": "Save Changes",
        "profile_uploads_heading": "Uploaded Cats",
        "loading_profile_cats": "Loading cats...",

        // Admin Dashboard
        "admin_title": "Admin Dashboard",
        "admin_subtitle": "Manage all community uploads, user profiles, and platform statistics",
        "admin_total_cats": "Total Uploaded Cats",
        "admin_total_votes": "Total Community Votes",
        "admin_total_users": "Active Creators",
        "admin_tab_cats": "Uploaded Cats",
        "admin_tab_users": "Community Users",
        "admin_edit_modal_title": "Edit Cat Details",
        "admin_edit_user_title": "Edit User Profile",
        "uploader_label": "Uploader Display Name",
        "votes_count_label": "Votes Count",
        "admin_table_title": "All Uploaded Cats",
        "admin_users_title": "All Registered Creators",
        "th_photo": "Photo",
        "th_name": "Name",
        "th_uploader": "Uploader",
        "th_votes": "Votes",
        "th_date": "Date",
        "th_actions": "Actions",
        "th_user": "User",
        "th_user_id": "User ID",
        "th_cat_count": "Cats",
        "th_total_likes": "Total Votes",
        "btn_edit": "Edit",
        "btn_force_delete": "Force Delete",
        "btn_view_profile": "View Profile",
        "admin_force_delete_confirm": "Admin: Force Delete this cat? This will permanently delete the cat record, comments, likes, and image storage file.",
        "admin_force_delete_user_confirm": "Admin: Force Delete this user and all their uploaded cats, comments, and records?",

        // Toasts and Alerts
        "toast_need_signin_vote": "Please sign in to vote for cats!",
        "toast_need_signin_comment": "Please sign in to post comments.",
        "toast_cooldown": "Cooldown: Please wait {sec}s before voting or commenting again.",
        "toast_voted": "Voted!",
        "toast_vote_removed": "Vote removed",
        "toast_comment_posted": "Comment posted!",
        "toast_reply_posted": "Reply posted!",
        "toast_comment_deleted": "Comment deleted!",
        "toast_cat_deleted": "Cat photo deleted!",
        "toast_cat_updated": "Cat details updated!",
        "toast_profile_synced": "Profile updated across all records!",
        "toast_cat_force_deleted": "Cat permanently force deleted!",
        "toast_user_force_deleted": "User and all records force deleted!",
        "toast_notif_read": "Notification marked as read",
        "toast_all_notifs_read": "All notifications marked as read",
        "toast_notifs_cleared": "All notifications cleared",
        "toast_signin_success": "Signed in successfully!",
        "toast_signup_success": "Account created! Welcome to CatRank.",
        "toast_signout_success": "Signed out successfully."
    },
    ru: {
        // Navigation
        "nav_brand": "CatRank",
        "nav_feed": "Лента",
        "nav_leaderboard": "Рейтинг",
        "nav_upload": "Загрузить котика",
        "nav_signin": "Войти",
        "nav_signup": "Регистрация",
        "nav_signout": "Выйти",
        "nav_profile": "Профиль",
        "nav_admin": "Админ-панель",
        "nav_notifications": "Уведомления",

        // Notifications
        "notifications_title": "Уведомления",
        "notif_mark_read": "Прочитать все",
        "notif_empty": "Уведомлений пока нет",
        "notif_footer": "История активности",
        "notif_clear_all": "Очистить всё",
        "notif_new": "новых",
        "notif_liked": "понравилось ваше фото котика",
        "notif_commented": "оставил(а) комментарий к",
        "notif_replied": "ответил(а) на ваш комментарий к",

        // Feed & Home Page
        "feed_title": "Лента сообщества",
        "feed_subtitle": "Нажмите на фото любого котика, чтобы посмотреть, проголосовать и оставить комментарий",
        "champion_badge": "Чемпион сообщества #1",
        "champion_desc": "Самый любимый котик сообщества, набравший",
        "champion_votes": "голосов! Нажмите ниже, чтобы посмотреть всех лидеров.",
        "view_and_comment": "Смотреть и обсудить",
        "leaderboard_podium": "Пьедестал рейтинга",
        "featured_badge": "Рекомендуемое видео",
        "featured_title": "Подборка забавных и милых котиков",
        "featured_desc": "Наслаждайтесь самыми милыми моментами и голосуйте за любимых пушистиков от участников сообщества!",
        "share_cat_btn": "Поделиться фото котика",
        "search_placeholder": "Поиск котиков по имени...",
        "no_cats_title": "Котиков пока не добавили",
        "no_cats_desc": "Станьте первым, кто покажет своего пушистого друга миру!",
        "upload_first_btn": "Загрузить первого котика",
        "no_search_title": "Котики не найдены",
        "no_search_desc": "Попробуйте изменить поисковый запрос",
        "uploaded_on": "Дата публикации",
        "by_author": "автор",
        "votes": "голосов",
        "double_click_hint": "Двойной клик по фото для голоса",

        // Modal & Threaded Comments
        "modal_comments_title": "Комментарии",
        "comment_placeholder": "Написать комментарий... (задержка 10 сек)",
        "reply_placeholder": "Написать ответ... (задержка 10 сек)",
        "reply_btn": "Ответить",
        "replying_to": "Ответ пользователю",
        "cancel_reply": "Отмена",
        "post_btn": "Отправить",
        "no_comments": "Комментариев пока нет. Будьте первым, кто напишет что-то доброе!",
        "loading_comments": "Загрузка комментариев...",
        "delete_comment_confirm": "Вы уверены, что хотите удалить этот комментарий?",
        "delete_cat_confirm": "Вы уверены, что хотите удалить это фото котика?",
        "view_replies": "ответов",
        "delete_btn": "Удалить",
        "close_modal": "Закрыть",

        // Leaderboard Page
        "hall_of_fame": "Зал славы",
        "leaderboard_title": "Рейтинг котиков",
        "leaderboard_subtitle": "Ранжировано по сумме голосов сообщества • Нажмите для просмотра",
        "added_date": "Добавлен",
        "no_leaderboard_cats": "В рейтинге пока нет котиков.",
        "leaderboard_remaining_title": "Рейтинг участников (с 4-го места)",
        "all_top_cats_on_podium": "Все лучшие котики представлены на пьедестале почета выше!",

        // Upload Page
        "upload_page_title": "Загрузить фото котика",
        "upload_daily_limit": "Поделитесь фото своего любимца и поборитесь за первое место!",
        "cat_name_label": "Кличка котика",
        "cat_name_placeholder": "например: Луна, Симба, Моти, Барсик",
        "photo_label": "Фотография (PNG, JPG, WEBP, до 5 МБ)",
        "drop_drag_text": "Нажмите для выбора или перетащите файл",
        "drop_format_text": "PNG, JPG или WEBP до 5 МБ",
        "preview_label": "Предпросмотр",
        "upload_submit_btn": "Опубликовать фото",
        "uploading_btn": "Загрузка...",

        // Auth Pages
        "welcome_back_title": "С возвращением",
        "login_subtitle": "Войдите, чтобы голосовать, комментировать и загружать фото",
        "join_community_title": "Присоединиться к CatRank",
        "register_subtitle": "Создайте аккаунт, чтобы делиться фото, голосовать и участвовать в рейтинге",
        "email_label": "Электронная почта",
        "password_label": "Пароль",
        "confirm_password_label": "Подтверждение пароля",
        "display_name_label": "Имя пользователя / Никнейм",
        "display_name_placeholder": "например: Котолюб",
        "signin_submit_btn": "Войти",
        "signup_submit_btn": "Зарегистрироваться",
        "no_account_text": "Ещё нет аккаунта?",
        "has_account_text": "Уже есть аккаунт?",
        "goto_register_link": "Создать новый аккаунт",
        "goto_login_link": "Войти в систему",

        // Profile Page
        "profile_bio_default": "Участник сообщества CatRank • Любитель кошек",
        "stat_uploads": "Публикаций",
        "stat_total_votes": "Всего голосов",
        "edit_profile_btn": "Редактировать профиль",
        "change_photo": "Изменить",
        "edit_profile_title": "Редактирование профиля",
        "profile_photo_label": "Аватар профиля",
        "upload_new_photo": "Выбрать фото",
        "btn_default_avatar": "Сбросить",
        "cancel_modal_btn": "Отмена",
        "save_changes_btn": "Сохранить изменения",
        "profile_uploads_heading": "Загруженные котики",
        "loading_profile_cats": "Загрузка котиков...",

        // Admin Dashboard
        "admin_title": "Панель администратора",
        "admin_subtitle": "Управление публикациями, профилями пользователей и статистикой платформы",
        "admin_total_cats": "Всего котиков",
        "admin_total_votes": "Всего голосов",
        "admin_total_users": "Авторов на платформе",
        "admin_tab_cats": "Загруженные котики",
        "admin_tab_users": "Пользователи сообщества",
        "admin_edit_modal_title": "Редактирование данных котика",
        "admin_edit_user_title": "Редактирование профиля пользователя",
        "uploader_label": "Имя автора",
        "votes_count_label": "Количество голосов",
        "admin_table_title": "Все загруженные котики",
        "admin_users_title": "Все зарегистрированные авторы",
        "th_photo": "Фото",
        "th_name": "Кличка",
        "th_uploader": "Автор",
        "th_votes": "Голоса",
        "th_date": "Дата",
        "th_actions": "Действия",
        "th_user": "Пользователь",
        "th_user_id": "ID пользователя",
        "th_cat_count": "Котиков",
        "th_total_likes": "Всего лайков",
        "btn_edit": "Изменить",
        "btn_force_delete": "Принудительно удалить",
        "btn_view_profile": "Открыть профиль",
        "admin_force_delete_confirm": "Администратор: Принудительно удалить этого котика? Это безвозвратно удалит запись, все комментарии, лайки и файл изображения.",
        "admin_force_delete_user_confirm": "Администратор: Принудительно удалить этого пользователя и все его публикации, комментарии и данные?",

        // Toasts and Alerts
        "toast_need_signin_vote": "Пожалуйста, войдите в аккаунт, чтобы голосовать!",
        "toast_need_signin_comment": "Пожалуйста, войдите в аккаунт, чтобы писать комментарии.",
        "toast_cooldown": "Подождите {sec} сек перед следующим действием.",
        "toast_voted": "Голос учтён!",
        "toast_vote_removed": "Голос отменён",
        "toast_comment_posted": "Комментарий добавлен!",
        "toast_reply_posted": "Ответ опубликован!",
        "toast_comment_deleted": "Комментарий удалён!",
        "toast_cat_deleted": "Фото котика удалено!",
        "toast_cat_updated": "Данные котика обновлены!",
        "toast_profile_synced": "Профиль синхронизирован по всей платформе!",
        "toast_cat_force_deleted": "Котик принудительно удалён!",
        "toast_user_force_deleted": "Пользователь и все связанные данные удалены!",
        "toast_notif_read": "Уведомление прочитано",
        "toast_all_notifs_read": "Все уведомления отмечены как прочитанные",
        "toast_notifs_cleared": "Все уведомления очищены",
        "toast_signin_success": "Вы успешно вошли в аккаунт!",
        "toast_signup_success": "Аккаунт создан! Добро пожаловать в CatRank.",
        "toast_signout_success": "Вы вышли из аккаунта."
    }
};

let currentLang = localStorage.getItem("catrank_lang") || "en";

function t(key, params = {}) {
    let dict = translations[currentLang] || translations["en"];
    let text = dict[key] || translations["en"][key] || key;
    for (const [k, v] of Object.entries(params)) {
        text = text.replace(new RegExp(`\\{${k}\\}`, 'g'), v);
    }
    return text;
}

function applyTranslations() {
    document.documentElement.lang = currentLang;
    
    // Update plain text attributes
    document.querySelectorAll("[data-i18n]").forEach(el => {
        const key = el.getAttribute("data-i18n");
        if (key) {
            el.innerText = t(key);
        }
    });

    // Update placeholders
    document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
        const key = el.getAttribute("data-i18n-placeholder");
        if (key) {
            el.placeholder = t(key);
        }
    });

    // Update titles
    document.querySelectorAll("[data-i18n-title]").forEach(el => {
        const key = el.getAttribute("data-i18n-title");
        if (key) {
            el.title = t(key);
        }
    });

    // Update language switcher active buttons styling
    const enBtn = document.getElementById("lang-btn-en");
    const ruBtn = document.getElementById("lang-btn-ru");
    if (enBtn && ruBtn) {
        if (currentLang === "en") {
            enBtn.className = "px-2 py-1 text-xs font-black bg-white text-indigo-600 rounded-lg shadow-xs transition";
            ruBtn.className = "px-2 py-1 text-xs font-bold text-slate-600 hover:text-slate-900 rounded-lg transition";
        } else {
            ruBtn.className = "px-2 py-1 text-xs font-black bg-white text-indigo-600 rounded-lg shadow-xs transition";
            enBtn.className = "px-2 py-1 text-xs font-bold text-slate-600 hover:text-slate-900 rounded-lg transition";
        }
    }
}

function setLanguage(lang) {
    if (!["en", "ru"].includes(lang)) return;
    currentLang = lang;
    localStorage.setItem("catrank_lang", lang);
    document.cookie = `catrank_lang=${lang}; path=/; max-age=31536000`;
    applyTranslations();
    window.dispatchEvent(new CustomEvent("catrank_language_changed", { detail: { lang } }));
}

document.addEventListener("DOMContentLoaded", () => {
    applyTranslations();
});
