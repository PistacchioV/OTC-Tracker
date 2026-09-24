"""
check_four_eyes.py -- o maker/checker e ligado na PROD e desligado na DEV (§553).

Na dev quem testa e uma pessoa so, e toda aprovacao/envio da propria linha
voltava 403 `same_user`. O interruptor e `Config.FOUR_EYES` (bloco de ambiente
do `config.py`: `_FOUR_EYES = False` na dev, `True` na prod), e ha UMA pergunta
no servidor (`platform.authz.is_own_change`) e UM flag no navegador
(`OTC_FOUR_EYES`). O que se prende:

  1. `is_own_change` com o flag ligado: o proprio maker e barrado, maker vazio
     nunca e "o proprio", caixa e espaco nao importam;
  2. com o flag desligado, ninguem e barrado;
  3. o checkout de DEV nasce desligado (o bloco de ambiente);
  4. nenhuma trava do servidor compara maker e SID A MAO fora do helper --
     uma que escapasse continuaria dando 403 na dev, calada;
  5. toda comparacao com CURRENT_USER/CURRENT_USER_SID no navegador passa pelo
     `OTC_FOUR_EYES`, e a pagina define o flag.
"""
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.config import Config                             # noqa: E402
from apps.pages.platform import authz as A                 # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('== 3. o checkout de DEV nasce desligado ==')
cfg = open(os.path.join(ROOT, 'apps/config.py'), encoding='utf-8').read()
bloco = re.search(r'# ── ENV:(\w+).*?# ── /ENV', cfg, re.DOTALL)
if bloco and bloco.group(1) == 'DEV':
    check('ENV:DEV -> Config.FOUR_EYES False', Config.FOUR_EYES, False)
else:
    check('ENV:PROD -> Config.FOUR_EYES True', Config.FOUR_EYES, True)

_orig = Config.FOUR_EYES
try:
    print('\n== 1. flag ligado (prod) ==')
    Config.FOUR_EYES = True
    check('o proprio maker e barrado', A.is_own_change('A111111', 'A111111'), True)
    check('   cego a caixa e espaco', A.is_own_change(' a111111 ', 'A111111'), True)
    check('outro usuario passa', A.is_own_change('A111111', 'B222222'), False)
    check('maker vazio nunca e "o proprio"', A.is_own_change('', ''), False)
    check('   nem None', A.is_own_change(None, 'A111111'), False)

    print('\n== 2. flag desligado (dev) ==')
    Config.FOUR_EYES = False
    check('o proprio maker passa', A.is_own_change('A111111', 'A111111'), False)
finally:
    Config.FOUR_EYES = _orig

print('\n== 4. nenhuma trava do servidor fora do helper ==')
cru = re.compile(r"""(\bmaker\b[^\n]*==\s*(\(?sid|user_sid|user\b)|\['?(maker|Maker|MAKER)'?\]\s*==|"""
                 r"""get\(['"](maker|Maker|MAKER)['"]\)\s*==|r\[-3\][^\n]*==\s*sid)""", re.I)
achados = []
for base, _, arqs in os.walk(os.path.join(ROOT, 'apps', 'pages')):
    for a in arqs:
        if not a.endswith('.py') or a == 'routes 2.py':
            continue
        p = os.path.join(base, a)
        for n, linha in enumerate(open(p, encoding='utf-8'), 1):
            s = linha.split('#', 1)[0]
            if cru.search(s) and 'is_own_change' not in s:
                achados.append('%s:%d %s' % (os.path.relpath(p, ROOT), n, s.strip()))
check('comparacoes maker x SID a mao', achados, [])

print('\n== 5. o navegador ==')
cmp_js = re.compile(r'[=!]==\s*CURRENT_USER(_SID)?\b|\bCURRENT_USER(_SID)?\s*[=!]==')
sem_flag, sem_def = [], []
pasta = os.path.join(ROOT, 'apps', 'templates', 'pages')
for a in sorted(os.listdir(pasta)):
    if not a.endswith('.html'):
        continue
    txt = open(os.path.join(pasta, a), encoding='utf-8').read()
    linhas = [(n, l) for n, l in enumerate(txt.split('\n'), 1) if cmp_js.search(l)]
    if not linhas:
        continue
    if 'var OTC_FOUR_EYES' not in txt:
        sem_def.append(a)
    for n, l in linhas:
        if 'OTC_FOUR_EYES' not in l:
            sem_flag.append('%s:%d %s' % (a, n, l.strip()[:90]))
check('toda comparacao passa pelo OTC_FOUR_EYES', sem_flag, [])
check('toda pagina que compara define o flag', sem_def, [])

print('\n%s' % ('FAIL: %d' % len(fails) if fails else 'OK'))
sys.exit(1 if fails else 0)
