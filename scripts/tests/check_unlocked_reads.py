"""A leitura SEM lock so vale onde um dado velho nao decide nada.

`duckdb_read_unlocked` / `sqlite_read_unlocked` abrem o banco dispensando o lock
de arquivo — o que coordena PROCESSOS. A leitura deixa de esperar por qualquer
gravacao em curso, e em troca pode pegar o arquivo no meio de um commit: falhar,
ou (no share) ver um estado parcial.

Isso e aceitavel em UM lugar: o poll do sino. Ele e a consulta mais repetida do
app (uma por aba a cada poucos segundos), e e de MELHOR ESFORCO — o endpoint ja
devolve o sino vazio quando a consulta falha, e o poll seguinte corrige. Um
aviso que aparece alguns segundos depois nao muda decisao nenhuma.

Em qualquer outro lugar e um tiro no pe, e o tipo que nao da erro: a allowlist
do `Page_Access`, o login e o papel que filtra os tickets DECIDEM coisas. Um
dado parcial ali vira uma autorizacao errada — alguem vendo a tela de outra
mesa, ou perdendo a propria —, e nada na tela diz que foi leitura suja.

Este script prende os pontos de chamada. Chamada nova fora da lista falha, e uma
da lista que sumir tambem falha (pedindo que saia daqui).
"""
import ast
import io
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# funcao que pode chamar → quantas vezes. Nada mais.
PERMITIDO = {
    'get_notif_connection': 1,      # o wrapper, no ramo `unlocked=True`
    'api_get_notifications': 1,     # o poll do sino, o unico consumidor
}

# E as funcoes que NUNCA podem: elas decidem acesso.
PROIBIDO_SEMPRE = ('_read_page_access', '_get_page_access', '_set_page_access',
                   'get_user_by_sid', 'insert_new_user', 'verify_code',
                   'save_verification_code', '_tk_roles_by_sid',
                   '_session_is_master', '_session_is_admin')

ALVOS = ('duckdb_read_unlocked', 'sqlite_read_unlocked')

achadas = {}
for raiz, dirs, arqs in os.walk(os.path.join(ROOT, 'apps')):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for a in arqs:
        if not a.endswith('.py') or a.endswith(' 2.py'):
            continue
        caminho = os.path.join(raiz, a)
        try:
            arv = ast.parse(io.open(caminho, encoding='utf-8').read())
        except SyntaxError:
            continue
        if os.path.basename(caminho) == 'database_access.py':
            continue                       # e onde elas sao DEFINIDAS
        # de qual funcao parte cada chamada
        for no in ast.walk(arv):
            if not isinstance(no, ast.FunctionDef):
                continue
            for x in ast.walk(no):
                if not isinstance(x, ast.Call):
                    continue
                nome = getattr(x.func, 'id', '') or getattr(x.func, 'attr', '')
                # A chamada DIRETA da primitiva...
                if nome in ALVOS:
                    achadas[no.name] = achadas.get(no.name, 0) + 1
                    continue
                # ...e a que passa pelo wrapper (`unlocked=True`). Sem esta, a
                # varredura via so o wrapper e dava por seguro justamente o
                # consumidor — que e o que importa vigiar.
                for kw in x.keywords:
                    if kw.arg == 'unlocked' and getattr(kw.value, 'value', None) is True:
                        achadas[no.name] = achadas.get(no.name, 0) + 1

print('== quem lê sem lock ==')
for f, n in sorted(achadas.items()):
    print('     %s (%dx)' % (f, n))
novos = sorted(f for f in achadas if f not in PERMITIDO)
check('nenhuma chamada fora da lista', novos, [])
sumiram = sorted(f for f in PERMITIDO if f not in achadas)
check('e a lista não guarda quem já saiu', sumiram, [])
demais = sorted(f for f in achadas if f in PERMITIDO and achadas[f] > PERMITIDO[f])
check('nenhuma ganhou chamada a mais', demais, [])

print('\n== e quem NUNCA pode ==')
# Redundante com o teste acima hoje, e de propósito: se a lista `PERMITIDO`
# crescer sem que ninguém pense, estas continuam barradas por nome.
proibidas = sorted(f for f in PROIBIDO_SEMPRE if f in achadas)
check('nenhuma função de autorização lê sem lock', proibidas, [])

print('\n== o wrapper recusa gravação sem lock ==')
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
sys.path.insert(0, ROOT)
from apps.pages import routes as R                          # noqa: E402

# Gravar sem lock CORROMPE o arquivo em vez de só ler torto — e a camada já
# recusa por baixo; aqui é o segundo cinto, no wrapper que a aplicação usa.
try:
    R.get_notif_connection(readonly=False, unlocked=True)
    check('unlocked sem readonly levanta', 'não levantou', 'ValueError')
except ValueError:
    check('unlocked sem readonly levanta', 'ValueError', 'ValueError')
except Exception as e:                                      # noqa: BLE001
    check('unlocked sem readonly levanta', type(e).__name__, 'ValueError')

print('\n== o aviso não inunda o log ==')
# `file_lock_skipped` sai em WARNING, e WARNING passa pelo gate que silencia o
# ruído de INFO. Uma linha por leitura seria a maior parte do log, com o sino
# consultando por aba aberta.
_da = io.open(os.path.join(ROOT, 'apps', 'pages', 'database_access.py'),
              encoding='utf-8').read()
check('o aviso é uma vez por banco, não por leitura',
      '_unlocked_warned' in _da, True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
