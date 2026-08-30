/**
 * CatRank Comprehensive Bilingual Translation Module (English / Russian)
 */
const translations = {
    en: {
        "current_email_label": "Current Email",
        "new_email_label": "New Email Address",
        "confirm_with_password_label": "Confirm with Current Password",
        "enter_current_password_placeholder": "Enter current password to authorize",
        "toast_wrong_pass_email": "Current password is required to change email.",
        "toast_email_updated": "Account email updated successfully!",

        "reg_success_badge": "Account Created!",
        "check_email_title": "Please Check Your Email",
        "check_email_desc_prefix": "We've sent a verification link to",
        "check_email_desc_suffix": "Please click the link in your inbox to activate your account and start voting!",
        "email_spam_hint_title": "Didn't receive the email?",
        "email_spam_hint_desc": "Check your spam folder, or wait a minute before requesting another link.",
        "goto_login_now": "Go to Sign In",

        "current_password_label": "Current Password",
        "current_password_placeholder": "Enter your current password",
        "toast_wrong_current_pass": "Current password is incorrect.",
        "toast_email_rate_limit": "Email rate limit exceeded. Please wait a moment.",

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
        "nav_menu": "Menu",

        // Mobile Bottom Nav
        "mobile_nav_feed": "Feed",
        "mobile_nav_leaderboard": "Rankings",
        "mobile_nav_upload": "Upload",
        "mobile_nav_profile": "Account",

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
        "feed_subtitle": "Click any cat photo to preview, like, and join the conversation",
        "champion_badge": "Community Champion #1",
        "champion_desc": "The most beloved cat of the community with",
        "champion_votes": "votes! Click below to see all ranked cats.",
        "votes": "votes",
        "view_and_comment_btn": "View & Comment",
        "leaderboard_podium_btn": "Leaderboard Podium",
        "featured_spotlight": "Featured Spotlight",
        "funny_cats_title": "Funny & Cute Cats Compilation",
        "funny_cats_desc": "Enjoy the cutest cat moments and vote for your favorite feline friends uploaded by the community today!",
        "share_cat_btn": "Share Your Cat Photo",
        "search_placeholder": "Search cats by name...",
        "all_cats_filter": "All Cats",
        "top_voted_filter": "Most Voted",
        "newest_filter": "Newest",
        "no_cats_title": "No cats uploaded yet",
        "no_cats_desc": "Be the first to share your feline friend with the world!",
        "btn_upload_first": "Upload First Cat",
        "click_to_view": "Click to inspect & comment",
        "vote_btn": "Vote",
        "voted_btn": "Voted",

        // Upload Page & Cat Bio
        "upload_page_title": "Upload Cat Photo",
        "upload_daily_limit": "Share your cat photo and join the community leaderboard!",
        "cat_name_label": "Cat Name",
        "cat_name_placeholder": "e.g. Luna, Simba, Mochi, Barsik",
        "cat_bio_label": "Cat Bio / Story (Optional)",
        "cat_bio_placeholder": "Tell us about your cat's personality, favorite habits, or story...",
        "photo_label": "Photo (PNG, JPG, WEBP, max 5MB)",
        "drop_drag_text": "Click to browse or drag & drop",
        "drop_format_text": "PNG, JPG, or WEBP up to 5MB",
        "preview_label": "Preview",
        "remove_preview_btn": "Remove",
        "upload_submit_btn": "Upload Photo",

        // Modals & Comment System
        "modal_comments_heading": "Comments",
        "reply_btn": "Reply",
        "delete_btn": "Delete",
        "edit_btn": "Edit",
        "save_btn": "Save",
        "cancel_btn": "Cancel",
        "replying_to": "Replying to",
        "cancel_reply_btn": "Cancel Reply",
        "comment_placeholder": "Add a comment...",
        "reply_placeholder": "Write a reply...",
        "comment_submit_btn": "Send",
        "loading_comments": "Loading comments...",
        "no_comments": "No comments yet. Be the first to say something nice!",
        "cat_details_title": "Cat Details",
        "cat_story_title": "About this cat",

        // Authentication & Security
        "welcome_back_title": "Welcome Back",
        "login_subtitle": "Sign in to vote, comment, and upload cat pictures",
        "email_label": "Email Address",
        "password_label": "Password",
        "confirm_password_label": "Confirm Password",
        "signin_submit_btn": "Sign In",
        "signup_submit_btn": "Create Account",
        "join_community_title": "Join CatRank",
        "register_subtitle": "Create an account to upload, vote, and share cat pictures",
        "display_name_label": "Display Name / Username",
        "display_name_placeholder": "e.g. CatWhisperer",
        "no_account_text": "Don't have an account?",
        "has_account_text": "Already have an account?",
        "goto_register_link": "Create an account / Sign Up",
        "goto_login_link": "Sign In here",
        "forgot_password_title": "Forgot Password?",
        "forgot_password_subtitle": "Enter your email and we will send you a password reset link",
        "forgot_password_link": "Forgot password?",
        "forgot_password_btn": "Send Reset Link",
        "back_to_login": "Back to Sign In",
        "reset_password_title": "Reset Password",
        "reset_password_subtitle": "Enter your new password below to secure your account",
        "new_password_label": "New Password",
        "confirm_new_password_label": "Confirm New Password",
        "reset_password_btn": "Update Password",
        "toast_reset_sent": "Reset link sent to your email! Please check your inbox.",
        "toast_pass_updated": "Password updated successfully! Redirecting...",
        "toast_otp_expired": "Password reset link has expired or is invalid. Please request a new one.",

        // Registration Extras
        "optional_badge": "Optional",
        "avatar_upload_label": "Profile Avatar (Optional)",
        "avatar_upload_hint": "Click to upload a custom avatar photo (PNG, JPG, WEBP)",
        "phone_label": "Phone Number",
        "phone_placeholder": "+998 90 123 45 67",
        "bio_label": "Short Bio",
        "bio_placeholder": "Tell us about your love for cats...",

        // User Not Found
        "user_not_found_title": "User Not Found",
        "user_not_found_desc": "This user profile does not exist or has been removed from the platform.",
        "back_to_feed_btn": "Back to Feed",

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
        "tab_basic_info": "Basic Info",
        "tab_security": "Account & Security",
        "change_email_label": "Change Email Address",
        "new_email_placeholder": "new_email@example.com",
        "change_email_btn": "Update Email",
        "change_password_label": "Change Password",
        "new_password_placeholder": "New password (min 6 chars)",
        "change_password_btn": "Change Password",
        "phone_number_label": "Phone Number",

        // Admin Dashboard
        "admin_title": "Admin Dashboard",
        "admin_subtitle": "Manage all community uploads, user profiles, comments, and platform statistics",
        "admin_total_cats": "Total Uploaded Cats",
        "admin_total_votes": "Total Community Votes",
        "admin_total_users": "Active Creators",
        "admin_total_comments": "Total Comments",
        "admin_tab_cats": "Uploaded Cats",
        "admin_tab_users": "Community Users",
        "admin_tab_comments": "Comments Management",
        "admin_edit_modal_title": "Edit Cat Details",
        "admin_edit_user_title": "Edit User Profile",
        "admin_edit_comment_title": "Edit Comment",
        "uploader_label": "Uploader Display Name",
        "votes_count_label": "Votes Count",
        "cat_bio_admin_label": "Cat Bio / Description",
        "admin_table_title": "All Uploaded Cats",
        "admin_users_title": "All Registered Creators",
        "admin_comments_title": "All Community Comments",
        "th_photo": "Photo",
        "th_name": "Name",
        "th_uploader": "Uploader",
        "th_votes": "Votes",
        "th_date": "Date",
        "th_actions": "Actions",
        "th_user": "User",
        "th_email": "Email",
        "th_phone": "Phone",
        "th_role": "Role",
        "th_cat_count": "Cats",
        "th_total_likes": "Total Votes",
        "th_cat": "Cat",
        "th_comment": "Comment",
        "th_commenter": "Commenter",
        "search_cats_placeholder": "Search cats...",
        "search_users_placeholder": "Search users by name, email, or phone...",
        "search_comments_placeholder": "Search comments by text or user...",
        "role_admin": "Admin",
        "role_user": "Member",
        "btn_edit": "Edit",
        "btn_force_delete": "Force Delete",
        "btn_view_profile": "View Profile",
        "admin_force_delete_confirm": "Admin: Force Delete this cat? This will permanently delete the cat record, comments, likes, and image storage file.",
        "admin_force_delete_user_confirm": "Admin: Force Delete this user and all their uploaded cats, comments, and records?",
        "admin_delete_comment_confirm": "Admin: Delete this comment permanently?",
        "admin_edit_user_email": "User Email",
        "admin_edit_user_phone": "User Phone Number",
        "admin_edit_user_role": "User Role",
        "comment_text_label": "Comment Text",
        "toast_user_updated": "User profile updated successfully!",
        "toast_comment_updated": "Comment updated successfully!",
        "toast_comment_deleted": "Comment deleted successfully!",

        // Leaderboard Page
        "leaderboard_title": "Leaderboard",
        "leaderboard_subtitle": "The most loved cats ranked by the global community",
        "rank_th": "Rank",
        "cat_th": "Cat",
        "uploader_th": "Uploader",
        "votes_th": "Total Votes",
        "podium_first": "Champion",
        "podium_second": "Runner Up",
        "podium_third": "3rd Place",

        // Toasts & General
        "toast_signin_success": "Welcome back! Redirecting...",
        "toast_signup_success": "Account created successfully! Redirecting...",
        "toast_signout_success": "Signed out successfully.",
        "toast_profile_updated": "Profile updated successfully!",
        "toast_upload_success": "Cat uploaded successfully! Redirecting...",
        "toast_need_signin_vote": "Please sign in to vote for cats.",
        "toast_need_signin_comment": "Please sign in to post comments.",
        "toast_comment_posted": "Comment posted!",
        "toast_reply_posted": "Reply posted!",
        "toast_cooldown": "Please wait {sec}s before voting or commenting again.",
        "file_error_invalid_type": "Invalid image file. Only JPG, JPEG, PNG, WEBP, and GIF are allowed.",
        "file_error_too_large": "Image size exceeds 5MB limit. Please choose a smaller photo."
    },

    ru: {
        "current_email_label": "Текущий Email",
        "new_email_label": "Новый Email адрес",
        "confirm_with_password_label": "Подтвердите текущим паролем",
        "enter_current_password_placeholder": "Введите текущий пароль для подтверждения",
        "toast_wrong_pass_email": "Для изменения email требуется ввести правильный текущий пароль.",
        "toast_email_updated": "Email аккаунта успешно обновлен!",

        "reg_success_badge": "Аккаунт создан!",
        "check_email_title": "Пожалуйста, проверьте вашу почту",
        "check_email_desc_prefix": "Мы отправили ссылку для подтверждения на",
        "check_email_desc_suffix": "Пожалуйста, перейдите по ссылке в письме, чтобы активировать аккаунт и начать голосовать!",
        "email_spam_hint_title": "Не пришло письмо?",
        "email_spam_hint_desc": "Проверьте папку Спам или подождите минуту перед повторным запросом.",
        "goto_login_now": "Перейти ко входу",

        "current_password_label": "Текущий пароль",
        "current_password_placeholder": "Введите текущий пароль",
        "toast_wrong_current_pass": "Неверный текущий пароль.",
        "toast_email_rate_limit": "Лимит отправки превышен. Пожалуйста, подождите пару секунд.",

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
        "nav_menu": "Меню",

        // Mobile Bottom Nav
        "mobile_nav_feed": "Лента",
        "mobile_nav_leaderboard": "Рейтинг",
        "mobile_nav_upload": "Загрузка",
        "mobile_nav_profile": "Профиль",

        // Notifications
        "notifications_title": "Уведомления",
        "notif_mark_read": "Прочитать все",
        "notif_empty": "Нет новых уведомлений",
        "notif_footer": "История активности",
        "notif_clear_all": "Очистить всё",
        "notif_new": "новое",
        "notif_liked": "оценил(а) вашего котика",
        "notif_commented": "прокомментировал(а)",
        "notif_replied": "ответил(а) на ваш комментарий к",

        // Feed & Home Page
        "feed_title": "Лента сообщества",
        "feed_subtitle": "Нажмите на фото котика, чтобы открыть просмотр, проголосовать и оставить комментарий",
        "champion_badge": "Чемпион сообщества #1",
        "champion_desc": "Самый любимый котик сообщества с",
        "champion_votes": "голосами! Нажмите ниже, чтобы увидеть всех лидеров.",
        "votes": "голосов",
        "view_and_comment_btn": "Смотреть и комментировать",
        "leaderboard_podium_btn": "Подиум лидеров",
        "featured_spotlight": "В центре внимания",
        "funny_cats_title": "Смешная и милая подборка котиков",
        "funny_cats_desc": "Наслаждайтесь самыми милыми моментами и голосуйте за любимых пушистиков, опубликованных сегодня!",
        "share_cat_btn": "Поделиться фото котика",
        "search_placeholder": "Поиск котиков по имени...",
        "all_cats_filter": "Все котики",
        "top_voted_filter": "Популярные",
        "newest_filter": "Новые",
        "no_cats_title": "Котиков пока нет",
        "no_cats_desc": "Будьте первым, кто поделится своим пушистым другом с миром!",
        "btn_upload_first": "Загрузить первого котика",
        "click_to_view": "Нажмите для просмотра и комментариев",
        "vote_btn": "Голос",
        "voted_btn": "Вам нравится",

        // Upload Page & Cat Bio
        "upload_page_title": "Загрузить фото котика",
        "upload_daily_limit": "Поделитесь фото котика и участвуйте в общем рейтинге!",
        "cat_name_label": "Кличка котика",
        "cat_name_placeholder": "напр. Барсик, Луна, Симба, Моти",
        "cat_bio_label": "Описание / История котика (необязательно)",
        "cat_bio_placeholder": "Расскажите о характере котика, его привычках или забавной истории...",
        "photo_label": "Фотография (PNG, JPG, WEBP, до 5 МБ)",
        "drop_drag_text": "Нажмите для выбора или перетащите файл",
        "drop_format_text": "PNG, JPG или WEBP до 5 МБ",
        "preview_label": "Предпросмотр",
        "remove_preview_btn": "Удалить",
        "upload_submit_btn": "Опубликовать фото",

        // Modals & Comment System
        "modal_comments_heading": "Комментарии",
        "reply_btn": "Ответить",
        "delete_btn": "Удалить",
        "edit_btn": "Редактировать",
        "save_btn": "Сохранить",
        "cancel_btn": "Отмена",
        "replying_to": "Ответ пользователю",
        "cancel_reply_btn": "Отменить ответ",
        "comment_placeholder": "Написать комментарий...",
        "reply_placeholder": "Написать ответ...",
        "comment_submit_btn": "Отправить",
        "loading_comments": "Загрузка комментариев...",
        "no_comments": "Комментариев пока нет. Напишите добрый отзыв первым!",
        "cat_details_title": "Информация о котике",
        "cat_story_title": "Об этом котике",

        // Authentication & Security
        "welcome_back_title": "С возвращением",
        "login_subtitle": "Войдите, чтобы голосовать, комментировать и добавлять котиков",
        "email_label": "Электронная почта",
        "password_label": "Пароль",
        "confirm_password_label": "Подтверждение пароля",
        "signin_submit_btn": "Войти в аккаунт",
        "signup_submit_btn": "Создать аккаунт",
        "join_community_title": "Регистрация в CatRank",
        "register_subtitle": "Создайте профиль, чтобы публиковать котиков и голосовать",
        "display_name_label": "Имя пользователя / Никнейм",
        "display_name_placeholder": "напр. CatWhisperer",
        "no_account_text": "Еще нет аккаунта?",
        "has_account_text": "Уже есть аккаунт?",
        "goto_register_link": "Зарегистрироваться",
        "goto_login_link": "Войти здесь",
        "forgot_password_title": "Забыли пароль?",
        "forgot_password_subtitle": "Введите ваш email, и мы отправим ссылку для восстановления пароля",
        "forgot_password_link": "Забыли пароль?",
        "forgot_password_btn": "Отправить ссылку",
        "back_to_login": "Вернуться ко входу",
        "reset_password_title": "Сброс пароля",
        "reset_password_subtitle": "Введите новый пароль для защиты вашего аккаунта",
        "new_password_label": "Новый пароль",
        "confirm_new_password_label": "Подтвердите новый пароль",
        "reset_password_btn": "Сохранить пароль",
        "toast_reset_sent": "Ссылка для сброса отправлена на почту! Проверьте входящие.",
        "toast_pass_updated": "Пароль успешно изменен! Перенаправление...",
        "toast_otp_expired": "Ссылка для сброса пароля истекла или недействительна. Запросите новую.",

        // Registration Extras
        "optional_badge": "Необязательно",
        "avatar_upload_label": "Аватар профиля (необязательно)",
        "avatar_upload_hint": "Нажмите, чтобы загрузить аватарку (PNG, JPG, WEBP)",
        "phone_label": "Номер телефона",
        "phone_placeholder": "+998 90 123 45 67",
        "bio_label": "О себе",
        "bio_placeholder": "Расскажите о себе и вашей любви к котикам...",

        // User Not Found
        "user_not_found_title": "Пользователь не найден",
        "user_not_found_desc": "Данного профиля не существует или он был удален с платформы.",
        "back_to_feed_btn": "Вернуться в ленту",

        // Profile Page
        "profile_bio_default": "Участник CatRank • Любитель кошек",
        "stat_uploads": "Публикаций",
        "stat_total_votes": "Всего голосов",
        "edit_profile_btn": "Редактировать",
        "change_photo": "Изменить",
        "edit_profile_title": "Редактирование профиля",
        "profile_photo_label": "Фотография профиля",
        "upload_new_photo": "Выбрать фото",
        "btn_default_avatar": "Сбросить",
        "cancel_modal_btn": "Отмена",
        "save_changes_btn": "Сохранить",
        "profile_uploads_heading": "Мои публикации",
        "loading_profile_cats": "Загрузка котиков...",
        "tab_basic_info": "Основное",
        "tab_security": "Безопасность",
        "change_email_label": "Изменить Email",
        "new_email_placeholder": "new_email@example.com",
        "change_email_btn": "Обновить Email",
        "change_password_label": "Изменить пароль",
        "new_password_placeholder": "Новый пароль (мин. 6 симв.)",
        "change_password_btn": "Изменить пароль",
        "phone_number_label": "Номер телефона",

        // Admin Dashboard
        "admin_title": "Панель администратора",
        "admin_subtitle": "Управление публикациями, пользователями, комментариями и статистика",
        "admin_total_cats": "Всего котиков",
        "admin_total_votes": "Всего голосов",
        "admin_total_users": "Авторов",
        "admin_total_comments": "Комментариев",
        "admin_tab_cats": "Опубликованные котики",
        "admin_tab_users": "Пользователи",
        "admin_tab_comments": "Управление комментариями",
        "admin_edit_modal_title": "Редактирование котика",
        "admin_edit_user_title": "Редактирование профиля",
        "admin_edit_comment_title": "Редактирование комментария",
        "uploader_label": "Имя автора",
        "votes_count_label": "Количество голосов",
        "cat_bio_admin_label": "Описание / История котика",
        "admin_table_title": "Все загруженные котики",
        "admin_users_title": "Все зарегистрированные авторы",
        "admin_comments_title": "Все комментарии сообщества",
        "th_photo": "Фото",
        "th_name": "Кличка",
        "th_uploader": "Автор",
        "th_votes": "Голоса",
        "th_date": "Дата",
        "th_actions": "Действия",
        "th_user": "Пользователь",
        "th_email": "Email",
        "th_phone": "Телефон",
        "th_role": "Роль",
        "th_cat_count": "Котиков",
        "th_total_likes": "Голосов",
        "th_cat": "Котик",
        "th_comment": "Комментарий",
        "th_commenter": "Автор комментария",
        "search_cats_placeholder": "Поиск котиков...",
        "search_users_placeholder": "Поиск пользователей по имени, email или телефону...",
        "search_comments_placeholder": "Поиск комментариев по тексту или автору...",
        "role_admin": "Администратор",
        "role_user": "Участник",
        "btn_edit": "Изменить",
        "btn_force_delete": "Удалить",
        "btn_view_profile": "Профиль",
        "admin_force_delete_confirm": "Админ: Удалить этого котика навсегда? Это действие удалит запись, фото и комментарии.",
        "admin_force_delete_user_confirm": "Админ: Удалить этого пользователя и все его публикации и комментарии?",
        "admin_delete_comment_confirm": "Админ: Удалить этот комментарий навсегда?",
        "admin_edit_user_email": "Email пользователя",
        "admin_edit_user_phone": "Телефон пользователя",
        "admin_edit_user_role": "Роль пользователя",
        "comment_text_label": "Текст комментария",
        "toast_user_updated": "Профиль пользователя успешно обновлен!",
        "toast_comment_updated": "Комментарий успешно обновлен!",
        "toast_comment_deleted": "Комментарий удален!",

        // Leaderboard Page
        "leaderboard_title": "Таблица лидеров",
        "leaderboard_subtitle": "Самые популярные котики по результатам голосования сообщества",
        "rank_th": "Место",
        "cat_th": "Котик",
        "uploader_th": "Автор",
        "votes_th": "Всего голосов",
        "podium_first": "Чемпион",
        "podium_second": "2-е место",
        "podium_third": "3-е место",

        // Toasts & General
        "toast_signin_success": "С возвращением! Перенаправление...",
        "toast_signup_success": "Аккаунт успешно создан! Перенаправление...",
        "toast_signout_success": "Вы успешно вышли из аккаунта.",
        "toast_profile_updated": "Профиль успешно обновлен!",
        "toast_upload_success": "Котик успешно загружен! Перенаправление...",
        "toast_need_signin_vote": "Пожалуйста, войдите, чтобы голосовать.",
        "toast_need_signin_comment": "Пожалуйста, войдите, чтобы оставлять комментарии.",
        "toast_comment_posted": "Комментарий опубликован!",
        "toast_reply_posted": "Ответ опубликован!",
        "toast_cooldown": "Пожалуйста, подождите {sec} сек. перед следующим действием.",
        "file_error_invalid_type": "Недопустимый формат файла. Разрешены только JPG, JPEG, PNG, WEBP и GIF.",
        "file_error_too_large": "Размер файла превышает 5 МБ. Выберите файл меньшего размера."
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
    const enBtns = document.querySelectorAll(".lang-btn-en");
    const ruBtns = document.querySelectorAll(".lang-btn-ru");
    
    enBtns.forEach(btn => {
        if (currentLang === "en") {
            btn.className = "lang-btn-en px-2.5 py-1 text-xs font-black bg-indigo-600 text-white rounded-lg shadow-sm transition cursor-default";
        } else {
            btn.className = "lang-btn-en px-2.5 py-1 text-xs font-bold text-slate-700 hover:text-indigo-600 hover:bg-slate-200/80 rounded-lg transition cursor-pointer";
        }
    });

    ruBtns.forEach(btn => {
        if (currentLang === "ru") {
            btn.className = "lang-btn-ru px-2.5 py-1 text-xs font-black bg-indigo-600 text-white rounded-lg shadow-sm transition cursor-default";
        } else {
            btn.className = "lang-btn-ru px-2.5 py-1 text-xs font-bold text-slate-700 hover:text-indigo-600 hover:bg-slate-200/80 rounded-lg transition cursor-pointer";
        }
    });
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
