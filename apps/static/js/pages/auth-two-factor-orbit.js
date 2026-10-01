/**
 * Two Factor — the code is typed into six fields; when it is complete, the
 * digits orbit, the ring holds until /verify-2fa responds, and the screen
 * says Verified (redirects) or shakes with the reason.
 *
 * The orbit and the POST run in PARALLEL: the animation never delays the
 * answer, and a server slower than the orbit keeps the ring spinning.
 * Warnings and errors go out by code + _TRANS (the server sends `code`; the
 * `message` is only the fallback).
 */
(function () {
    'use strict';

    var _TRANS = {
        en: {
            idle: 'Enter your 6-digit code',
            loading: 'Verifying…',
            success: 'Access granted — redirecting…',
            failed: 'Verification failed',
            e_format: 'Please enter a valid 6-digit code.',
            e_invalid: 'Invalid verification code.',
            e_attempts: 'Too many incorrect attempts. Please request a new code.',
            e_expired: 'Verification code has expired. Please request a new one.',
            e_session_expired: 'Session expired. Please sign in again.',
            e_network: 'Request failed. Please try again.',
            r_sent: 'A new code has been sent.',
            r_send_failed: 'Failed to send the email. Please try again.',
            r_cooldown: 'A code was just sent. Please wait a moment before requesting another.',
            r_too_many: 'Too many code requests. Please wait a few minutes and try again.',
            r_user_not_found: 'User not found.',
            r_session_expired: 'Session expired. Please sign in again.'
        },
        br: {
            idle: 'Digite seu código de 6 dígitos',
            loading: 'Verificando…',
            success: 'Acesso liberado — redirecionando…',
            failed: 'Falha na verificação',
            e_format: 'Digite um código válido de 6 dígitos.',
            e_invalid: 'Código de verificação inválido.',
            e_attempts: 'Tentativas incorretas demais. Solicite um novo código.',
            e_expired: 'O código expirou. Solicite um novo.',
            e_session_expired: 'Sessão expirada. Entre novamente.',
            e_network: 'A requisição falhou. Tente novamente.',
            r_sent: 'Um novo código foi enviado.',
            r_send_failed: 'Não foi possível enviar o e-mail. Tente novamente.',
            r_cooldown: 'Um código acabou de ser enviado. Aguarde um momento antes de pedir outro.',
            r_too_many: 'Pedidos de código demais. Aguarde alguns minutos e tente novamente.',
            r_user_not_found: 'Usuário não encontrado.',
            r_session_expired: 'Sessão expirada. Entre novamente.'
        },
        es: {
            idle: 'Ingrese su código de 6 dígitos',
            loading: 'Verificando…',
            success: 'Acceso concedido — redirigiendo…',
            failed: 'Falló la verificación',
            e_format: 'Ingrese un código válido de 6 dígitos.',
            e_invalid: 'Código de verificación inválido.',
            e_attempts: 'Demasiados intentos incorrectos. Solicite un nuevo código.',
            e_expired: 'El código expiró. Solicite uno nuevo.',
            e_session_expired: 'Sesión expirada. Inicie sesión nuevamente.',
            e_network: 'La solicitud falló. Inténtelo de nuevo.',
            r_sent: 'Se envió un nuevo código.',
            r_send_failed: 'No se pudo enviar el correo. Inténtelo de nuevo.',
            r_cooldown: 'Se acaba de enviar un código. Espere un momento antes de pedir otro.',
            r_too_many: 'Demasiadas solicitudes de código. Espere unos minutos e inténtelo de nuevo.',
            r_user_not_found: 'Usuario no encontrado.',
            r_session_expired: 'Sesión expirada. Inicie sesión nuevamente.'
        }
    };

    function lang() {
        var l = 'en';
        try { l = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) { /* sem storage */ }
        return _TRANS[l] ? l : 'en';
    }
    function t(key, fallback) {
        var v = _TRANS[lang()][key];
        if (v) return v;
        return fallback || _TRANS.en[key] || key;
    }

    var ORBIT_MS = 1600;
    var SUCCESS_HOLD_MS = 1500;
    var ERROR_RESET_MS = 1400;
    var MIN_LOADING_MS = 700;   // resposta rápida não pula o anel
    var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    document.addEventListener('DOMContentLoaded', function () {
        var form = document.getElementById('twoFactorForm');
        var stage = document.getElementById('tfaStage');
        var inputsBox = document.getElementById('tfaInputs');
        if (!form || !stage || !inputsBox) return;

        var inputs = Array.prototype.slice.call(inputsBox.querySelectorAll('input'));
        var status = document.getElementById('tfaStatus');
        var orbit = document.getElementById('tfaOrbit');
        var ring = document.getElementById('tfaRing');
        var loading = document.getElementById('tfaLoading');
        var percent = document.getElementById('tfaPercent');
        var success = document.getElementById('tfaSuccess');
        var errorBox = document.getElementById('tfaError');
        var confirmBtn = document.getElementById('tfaConfirm');

        var state = 'idle';
        var timers = [];

        function later(fn, ms) { timers.push(setTimeout(fn, ms)); }
        function clearTimers() { timers.forEach(clearTimeout); timers = []; }

        function setStatus(key) {
            status.classList.add('is-swap');
            later(function () {
                status.textContent = t(key);
                status.classList.remove('is-swap');
            }, reduced ? 0 : 180);
        }
        function showError(code, fallback) {
            errorBox.textContent = t('e_' + (code || 'invalid'), fallback);
            errorBox.classList.add('is-shown');
        }
        function clearError() {
            errorBox.classList.remove('is-shown');
            errorBox.textContent = '';
        }
        function code() { return inputs.map(function (i) { return i.value; }).join(''); }

        // ── digitação ───────────────────────────────────────────────────────
        function fillFrom(index, digits) {
            for (var k = 0; k < digits.length && index + k < inputs.length; k++) {
                inputs[index + k].value = digits.charAt(k);
                inputs[index + k].classList.add('is-filled');
            }
            var next = Math.min(index + digits.length, inputs.length - 1);
            inputs[next].focus();
            if (code().length === inputs.length) verify();
        }

        inputs.forEach(function (input, index) {
            input.addEventListener('input', function () {
                if (state === 'loading' || state === 'success') return;
                // o dígito é lido ANTES do reset, que esvazia os campos
                var digits = input.value.replace(/\D/g, '');
                var from = index;
                if (state === 'error') { resetError(); from = 0; }   // código novo recomeça do 1º
                input.value = '';
                input.classList.remove('is-filled');
                if (digits) fillFrom(from, digits);
            });
            input.addEventListener('keydown', function (e) {
                if (state === 'loading' || state === 'success') { e.preventDefault(); return; }
                if (e.key === 'Backspace' && !input.value && index > 0) {
                    inputs[index - 1].value = '';
                    inputs[index - 1].classList.remove('is-filled');
                    inputs[index - 1].focus();
                    e.preventDefault();
                } else if (e.key === 'ArrowLeft' && index > 0) {
                    inputs[index - 1].focus();
                } else if (e.key === 'ArrowRight' && index < inputs.length - 1) {
                    inputs[index + 1].focus();
                }
            });
            // colar o código inteiro (do e-mail) preenche os seis campos
            input.addEventListener('paste', function (e) {
                e.preventDefault();
                if (state === 'loading' || state === 'success') return;
                if (state === 'error') resetError();
                var text = (e.clipboardData || window.clipboardData).getData('text') || '';
                var digits = text.replace(/\D/g, '').slice(0, inputs.length);
                if (digits) fillFrom(digits.length === inputs.length ? 0 : index, digits);
            });
            input.addEventListener('focus', function () { input.select(); });
        });

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            verify();
        });

        // ── órbita: cada dígito sai do SEU campo ────────────────────────────
        function playOrbit() {
            ring.innerHTML = '';
            var stageBox = stage.getBoundingClientRect();
            var cx = stageBox.left + stageBox.width / 2;
            // raio + meia altura do dígito cabem na meia altura do palco
            var radius = Math.min(66, stageBox.height / 2 - 30, stageBox.width / 2 - 40);
            inputs.forEach(function (input, i) {
                var box = input.getBoundingClientRect();
                var angle = (i / inputs.length) * Math.PI * 2 - Math.PI / 2;
                var node = document.createElement('div');
                node.className = 'tfa-node';
                node.textContent = input.value;
                node.style.setProperty('--sx', (box.left + box.width / 2 - cx) + 'px');
                node.style.setProperty('--dx', (Math.cos(angle) * radius) + 'px');
                node.style.setProperty('--dy', (Math.sin(angle) * radius) + 'px');
                node.style.animationDelay = (i * 50) + 'ms';
                ring.appendChild(node);
            });
            orbit.classList.add('is-active');
            void ring.offsetWidth;
            ring.classList.add('is-spin');
        }

        // ── o anel segura até a resposta chegar ─────────────────────────────
        var progressRaf = null;
        function startProgress() {
            var start = performance.now();
            function tick(now) {
                // aproxima de 90% e espera lá: o 100 é a resposta do servidor
                var p = 1 - Math.exp(-(now - start) / 900);
                percent.textContent = Math.round(p * 90);
                progressRaf = requestAnimationFrame(tick);
            }
            progressRaf = requestAnimationFrame(tick);
        }
        function stopProgress() {
            if (progressRaf) cancelAnimationFrame(progressRaf);
            progressRaf = null;
        }

        function verify() {
            if (state === 'loading' || state === 'success') return;
            var value = code();
            if (!/^\d{6}$/.test(value)) {
                showError('format');
                shake();
                var firstEmpty = inputs.filter(function (i) { return !i.value; })[0];
                (firstEmpty || inputs[0]).focus();
                return;
            }
            state = 'loading';
            clearTimers();
            clearError();
            confirmBtn.disabled = true;
            inputs.forEach(function (i) { i.blur(); });

            var request = fetch('/verify-2fa', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                body: JSON.stringify({ code: value })
            }).then(function (resp) {
                return resp.json().then(function (data) { return { ok: resp.ok, data: data || {} }; });
            }).catch(function () {
                return { ok: false, data: { code: 'network' } };
            });

            var orbitDone = new Promise(function (resolve) {
                if (reduced) { resolve(); return; }
                playOrbit();
                inputsBox.classList.add('is-hidden');
                later(resolve, ORBIT_MS + 150);
            });

            orbitDone.then(function () {
                orbit.classList.remove('is-active');
                ring.classList.remove('is-spin');
                ring.innerHTML = '';
                inputsBox.classList.add('is-hidden');
                setStatus('loading');
                loading.classList.add('is-active');
                startProgress();
                var minLoading = new Promise(function (resolve) { later(resolve, reduced ? 0 : MIN_LOADING_MS); });
                return Promise.all([request, minLoading]).then(function (r) { return r[0]; });
            }).then(function (res) {
                stopProgress();
                if (res.ok && res.data.success) {
                    percent.textContent = '100';
                    onSuccess(res.data.redirect || '/dashboard');
                } else {
                    onError(res.data.code, res.data.message);
                }
            });
        }

        function onSuccess(redirect) {
            state = 'success';
            later(function () {
                loading.classList.remove('is-active');
                spawnConfetti();
                success.classList.add('is-active');
                setStatus('success');
                later(function () { window.location.href = redirect; }, reduced ? 300 : SUCCESS_HOLD_MS);
            }, reduced ? 0 : 200);
        }

        function onError(errCode, fallback) {
            state = 'error';
            loading.classList.remove('is-active');
            inputsBox.classList.remove('is-hidden');
            inputs.forEach(function (i) { i.classList.add('is-error'); });
            setStatus('failed');
            showError(errCode, fallback);
            shake();
            confirmBtn.disabled = false;
            if (errCode === 'session_expired') {
                later(function () { window.location.href = '/auth-2-sign-in'; }, 2200);
                return;
            }
            later(function () { if (state === 'error') resetError(true); }, ERROR_RESET_MS);
        }

        // limpa o código errado; a frase do erro fica até a próxima digitação
        function resetError(keepMessage) {
            clearTimers();
            state = 'idle';
            inputs.forEach(function (i) {
                i.value = '';
                i.classList.remove('is-error', 'is-filled');
            });
            if (!keepMessage) clearError();
            setStatus('idle');
            inputs[0].focus();
        }

        function shake() {
            stage.classList.remove('is-shake');
            void stage.offsetWidth;
            stage.classList.add('is-shake');
        }

        function spawnConfetti() {
            if (reduced) return;
            var css = getComputedStyle(document.documentElement);
            var colors = ['--sf-cyan', '--sf-blue', '--sf-indigo', '--sf-violet', '--sf-fuchsia', '--sf-mint', '--ins-success']
                .map(function (v) { return css.getPropertyValue(v).trim(); })
                .filter(Boolean);
            if (!colors.length) colors = ['#29c5f6', '#007bff', '#8b5cf6'];
            var count = 24;
            for (var i = 0; i < count; i++) {
                var angle = (i / count) * Math.PI * 2 + (Math.random() - 0.5) * 0.25;
                var dist = 90 + Math.random() * 70;
                var size = 6 + Math.random() * 9;
                var color = colors[i % colors.length];
                var dot = document.createElement('div');
                dot.className = 'tfa-confetti';
                dot.style.width = size + 'px';
                dot.style.height = size + 'px';
                dot.style.background = color;
                dot.style.boxShadow = '0 0 12px ' + color;
                dot.style.borderRadius = i % 4 === 0 ? '2px' : (i % 4 === 1 ? '50% 0 50% 0' : '50%');
                dot.style.setProperty('--cx', (Math.cos(angle) * dist) + 'px');
                dot.style.setProperty('--cy', (Math.sin(angle) * dist) + 'px');
                dot.style.animationDelay = (100 + Math.random() * 150) + 'ms';
                success.appendChild(dot);
            }
        }

        // ── reenviar ────────────────────────────────────────────────────────
        var resend = document.getElementById('resendCodeLink');
        if (resend) {
            resend.addEventListener('click', function (e) {
                e.preventDefault();
                if (resend.dataset.busy === '1') return;
                resend.dataset.busy = '1';
                fetch('/resend-code', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' }
                }).then(function (r) {
                    return r.json().then(function (d) { return { ok: r.ok, data: d || {} }; });
                }).catch(function () {
                    return { ok: false, data: { code: 'network' } };
                }).then(function (res) {
                    resend.dataset.busy = '0';
                    var ok = res.ok && res.data.success;
                    var key = res.data.code === 'network' ? 'e_network' : 'r_' + (res.data.code || (ok ? 'sent' : 'send_failed'));
                    var msg = t(key, res.data.message);
                    if (ok && state === 'error') resetError();
                    if (window.Swal) {
                        Swal.fire({ text: msg, icon: ok ? 'success' : 'error', confirmButtonText: 'OK' });
                    } else {
                        alert(msg);
                    }
                    if (res.data.code === 'session_expired') window.location.href = '/auth-2-sign-in';
                });
            });
        }

        inputs[0].focus();
    });
})();
