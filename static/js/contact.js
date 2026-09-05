const contactForm = document.getElementById('contact-form');
contactForm?.addEventListener('submit', event => {
    const button = contactForm.querySelector('button[type="submit"]');
    if (button.disabled) { event.preventDefault(); return; }
    button.disabled = true;
    button.textContent = 'Sending…';
    contactForm.setAttribute('aria-busy', 'true');
});
window.addEventListener('pageshow', () => {
    const button = contactForm?.querySelector('button[type="submit"]');
    if (button) { button.disabled = false; button.textContent = 'Send message'; }
    contactForm?.removeAttribute('aria-busy');
});
document.getElementById('contact-errors')?.focus();
