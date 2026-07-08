#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ============================================================================
#  TEMPLATE DE LAUNCHER LOCAL — SOMENTE PARA DESENVOLVIMENTO/CAPTURA DE TELAS
# ----------------------------------------------------------------------------
#  Copie para a raiz do repo como devrun.py (que está no .gitignore) e rode:
#      cp scripts/sop-capture/devrun.example.py devrun.py
#      python devrun.py
#
#  ⚠️  NUNCA comite este bypass dentro de apps/ nem versione o devrun.py.
#      A rota /dev-login abaixo autentica a sessão SEM validação e existe
#      apenas para renderizar as telas localmente (HANDOFF, pitfall #11).
#
#  Ele faz duas coisas que a rede corporativa normalmente fornece:
#    1. Stub da lib interna `awmpy` (não existe no PyPI) só para o import passar.
#    2. Uma rota /dev-login que popula a sessão para as páginas renderizarem.
# ============================================================================
import os
import sys
import types
from datetime import datetime, timezone, timedelta

os.environ.setdefault('SECRET_KEY', 'dev-screenshot-key-fixed')
os.environ.setdefault('DEBUG', 'True')

# 1) stub da lib interna de phonebook (apenas para o import de apps.pages.routes)
_awmpy = types.ModuleType('awmpy')
_awmpy.get_phonebook_data = lambda sid: {
    'SID': sid, 'Name': 'Operador Demo',
    'Email': 'operador.demo@example.com', 'Role': 'Operations'}
sys.modules['awmpy'] = _awmpy

ROOT = os.path.dirname(os.path.abspath(__file__))
# se rodando a partir de scripts/sop-capture, ajuste para a raiz do repo:
if os.path.basename(ROOT) == 'sop-capture':
    ROOT = os.path.dirname(os.path.dirname(ROOT))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from flask import session, redirect                       # noqa: E402
from apps.config import config_dict                        # noqa: E402
from apps import create_app                                # noqa: E402

app = create_app(config_dict['Debug'])


@app.route('/dev-login')                                   # ⚠️ LOCAL ONLY
def dev_login():
    session['authenticated'] = True
    session['user_sid'] = 'X000000'
    session['user_name'] = 'Operador Demo'
    session['user_email'] = 'operador.demo@example.com'
    session['user_role'] = 'Operations'
    session['remember_me'] = True
    session['session_expires_at'] = (
        datetime.now(tz=timezone.utc) + timedelta(days=1)).isoformat()
    session.pop('locked', None)
    return redirect('/dashboard')


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8050, debug=False, use_reloader=False, threaded=True)
