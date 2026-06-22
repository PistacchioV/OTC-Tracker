/**
 * Template Name: OTC Tracker - Admin & Dashboard Template
 * By (Author): JPM
 * Module/App (File Name): Auth Two Factor
 */

class TwoFactorAuth {
    constructor(containerSelector = '.two-factor') {
        this.container = document.querySelector(containerSelector);

        if (!this.container) {
            console.error(`TwoFactorAuth: Container "${containerSelector}" not found.`);
            return;
        }

        this.inputs = Array.from(this.container.querySelectorAll('input'));
        if (this.inputs.length === 0) {
            console.error('TwoFactorAuth: No input fields found in the container.');
            return;
        }

        this.form = this.container.closest('form');
        this.confirmBtn = this.form?.querySelector('button[type="submit"]');
        this.init();
    }

    init() {
        this.inputs[0].focus();

        this.inputs.forEach((input, index) => {
            input.setAttribute('inputmode', 'numeric');
            input.setAttribute('maxlength', '1');

            input.addEventListener('input', (e) => this.handleInput(e, index));
            input.addEventListener('keydown', (e) => this.handleKeyDown(e, index));
            input.addEventListener('paste', this.preventPaste);
        });

        // Bind the form submit so both the Confirm button click AND pressing
        // Enter inside any digit input route through handleSubmit (which POSTs
        // the code) instead of the browser's default GET reload.
        if (this.form) {
            this.form.addEventListener('submit', (e) => this.handleSubmit(e));
        } else if (this.confirmBtn) {
            this.confirmBtn.addEventListener('click', (e) => this.handleSubmit(e));
        } else {
            console.warn('TwoFactorAuth: Submit form/button not found.');
        }
    }

    handleInput(e, index) {
        let value = e.target.value.replace(/\D/g, ''); // digits only

        if (value.length > 1) value = value.charAt(0);
        this.inputs[index].value = value;

        if (value && index < this.inputs.length - 1) {
            this.inputs[index + 1].focus();
        }
    }

    handleKeyDown(e, index) {
        if (e.key === 'Backspace' && !this.inputs[index].value && index > 0) {
            this.inputs[index - 1].focus();
        }
    }

    preventPaste(e) {
        e.preventDefault();
    }

    handleSubmit(e) {
        e.preventDefault();
        const code = this.inputs.map(input => input.value).join('');

        if (!/^\d+$/.test(code) || code.length !== this.inputs.length) {
            this.showError('Please enter a valid verification code.');
            setTimeout(() => this.clearError(), 3000);
            return;
        }

        if (this.submitting) return;
        this.submitting = true;
        this.clearError();
        if (this.confirmBtn) this.confirmBtn.disabled = true;

        fetch('/verify-2fa', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify({ code: code })
        })
            .then((resp) => resp.json().then((data) => ({ ok: resp.ok, data: data })))
            .then(({ ok, data }) => {
                if (ok && data && data.success) {
                    window.location.href = data.redirect || '/dashboard';
                    return;
                }
                this.submitting = false;
                if (this.confirmBtn) this.confirmBtn.disabled = false;
                this.showError((data && data.message) || 'Invalid or expired code. Please try again.');
                this.inputs.forEach((inp) => { inp.value = ''; });
                this.inputs[0].focus();
            })
            .catch(() => {
                this.submitting = false;
                if (this.confirmBtn) this.confirmBtn.disabled = false;
                this.showError('Request failed. Please try again.');
            });
    }

    showError(message) {
        if (!this.errorSpan) {
            this.errorSpan = document.createElement('span');
            this.errorSpan.className = 'text-danger d-block mb-3';
            this.inputs[0].parentElement.insertAdjacentElement('afterend', this.errorSpan);
        }
        this.errorSpan.textContent = message;
    }

    clearError() {
        if (this.errorSpan) {
            this.errorSpan.remove();
            this.errorSpan = null;
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    new TwoFactorAuth();
})
