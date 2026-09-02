# Supabase email templates

Paste each HTML file into the corresponding Supabase Auth email template. These files are not Flask/Jinja templates. Keep the Go-template variables intact. Security notifications must be enabled individually; templates alone do not send email.

| Template file | Suggested subject |
|---|---|
| confirm_signup.html | Confirm your CatRank account |
| reset_password.html | Reset your CatRank password |
| change_email.html | Confirm your new CatRank email |
| password_changed.html | Your CatRank password changed |
| email_changed.html | Your CatRank email changed |
| identity_linked.html | A sign-in method was added to CatRank |
| identity_unlinked.html | A sign-in method was removed from CatRank |

Send through Supabase Custom SMTP using Resend. Do not add Resend keys to browser code. Set a verified sender domain and a monitored reply address in your provider settings where supported. Disable click tracking for authentication links.

Sources: [Supabase email templates](https://supabase.com/docs/guides/auth/auth-email-templates), [Resend SMTP setup](https://resend.com/docs/send-with-supabase-smtp).
