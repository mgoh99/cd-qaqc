// Clearspace UI — main.js

// Auto-dismiss flash messages after 4 seconds
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.flash-msg').forEach(el => {
        setTimeout(() => {
            el.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            el.style.opacity = '0';
            el.style.transform = 'translateY(-0.5rem)';
            setTimeout(() => el.remove(), 300);
        }, 4000);
    });
});
