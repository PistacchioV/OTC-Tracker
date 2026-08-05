"""About: a vitrine do sistema, e o que a faz envelhecer sem ninguem notar.

A pagina About e a unica descricao do produto que alguem de fora le. Ela nao
quebra quando fica desatualizada — so passa a mentir. Este teste prende as
quatro formas de isso acontecer:

  1. carta apontando para uma pagina que nao existe. O link responde 404 e
     ninguem clica em todas as ~40 cartas para descobrir.

  2. icone que nao existe no pacote Tabler. Nao da erro: fica so o espaco em
     branco. Ja aconteceu (ti-currency-exchange no /mapping).

  3. chave `data-lang` sem traducao. O texto do HTML sobrevive em pt-BR, entao
     em EN e ES a carta aparece em portugues e ninguem reclama.

  4. FEATURE NOVA que ninguem anunciou. Este e o unico item que exige
     manutencao: a lista abaixo e das paginas que a About TEM de citar. Quando
     uma pagina nova entrar no menu e for para valer, ela entra aqui tambem — ou
     o teste falha e lembra.

Nao encosta em dado real: renderiza a pagina pelo endpoint com sessao de teste.
"""
import io
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8', errors='ignore').read()


from apps import create_app                                   # noqa: E402
from apps.config import DebugConfig                           # noqa: E402

app = create_app(DebugConfig)
cl = app.test_client()
with cl.session_transaction() as s:
    s['authenticated'] = True
    s['user_sid'] = 'T000000'
    s['user_name'] = 'T'
    s['user_role'] = 'ADMIN'
    s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()

resp = cl.get('/about')
HTML = resp.data.decode('utf-8')

print('== 1. a pagina abre ==')
check('GET /about', resp.status_code, 200)

print('\n== 2. todo link de carta leva a algum lugar ==')
hrefs = sorted(set(re.findall(r'<a href="(/[a-z0-9_/-]+)" class="ab-feat__link"', HTML)))
check('ha cartas com link', len(hrefs) > 30, True)
broken = []
for u in hrefs:
    st = cl.get(u).status_code
    if st not in (200, 302):
        broken.append((u, st))
check('nenhum link quebrado', broken, [])

print('\n== 3. todo icone existe no pacote Tabler ==')
VENDORS = read('apps/static/css/vendors.min.css')
icons = sorted(set(re.findall(r'<i class="ti (ti-[a-z0-9-]+)"', HTML)))
check('ha icones', len(icons) > 20, True)
check('nenhum icone inexistente', [i for i in icons if ('.%s:' % i) not in VENDORS], [])

print('\n== 4. toda chave data-lang tem traducao nos tres idiomas ==')
keys = sorted(set(re.findall(r'data-lang="([\w.-]+)"', HTML)))
check('ha chaves', len(keys) > 50, True)
for lang in ('en', 'br', 'es'):
    d = json.loads(read('apps/static/data/translations/%s.json' % lang))
    check('%s sem chave orfa' % lang, sorted(k for k in keys if k not in d), [])

print('\n== 5. as features do sistema estao anunciadas ==')
# Quando uma pagina nova entrar no menu e for para valer, ela entra aqui — ou o
# teste falha e lembra que a About ficou para tras.
MUST = [
    # New Deals
    '/new_deals-ndf-commodities', '/new_deals-ndf-fwdstart', '/new_deals-ndf-otherpublisher',
    '/new_deals-ndf-vanilla', '/new_deals-opt-commodities', '/new_deals-opt-fxo',
    '/new-deals-monitor',
    # Daily Settlement
    '/ndf-cockpit', '/other-products-summary', '/other-products-swap-settlement-advice',
    '/other-products-ndf-settlement-advice', '/otm-settlements', '/operations-b3', '/cognos',
    # Live Position
    '/live-position-ndf', '/live-position-swap-characteristics', '/live-position-option',
    '/live-position-swap-cashflow', '/live-position-swap-premium',
    # Regulatory / Reconciliations
    '/accrual-swap', '/mtm-swap', '/intrag-ndf',
    '/reconciliation-comitente', '/reconciliation-payrec',
    # Apps / Data Base
    '/control-panel', '/pending-confirmation', '/electronic-inventory', '/tickets-list',
    '/metrics-pending-confirmation', '/page-access', '/holidays-calendar', '/file-interpreter',
    '/index-b3', '/reference-data', '/mapping',
]
missing = [u for u in MUST if u not in hrefs]
check('nenhuma feature sem carta', missing, [])

print('\n== 6. o fluxo cobre o ciclo inteiro ==')
# Parava no mapeamento; hoje o ciclo vai ate a confirmacao e a liquidacao.
steps = re.findall(r'<div class="ab-step__title"[^>]*>([^<]+)</div>', HTML)
check('seis passos', len(steps), 6)
check('termina na liquidacao', steps[-1].strip().lower() in ('liquidação', 'settlement', 'liquidación'), True)
# Seis passos so cabem lado a lado se a linha puder quebrar.
check('a linha de passos quebra em telas medias', 'flex-md-row flex-wrap' in HTML, True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
