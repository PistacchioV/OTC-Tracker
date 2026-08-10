"""Confirmations Monitor: quem RECEBE o aviso de cada etapa da esteira.

Assinar e receber sao perguntas diferentes. Assinar e um ATO e e de uma mesa so
(`_MC_STAGE_ROLE`: Pending OTC -> BO, Pending MO -> MO, Pending FO -> FO). Receber
e acompanhar, e o Back Office acompanha a esteira inteira -- foi ele que montou o
documento e e para ele que o reject volta.

O que este script prende:

  1. a etapa que decide o destino e o ESTADO DEPOIS do carimbo
     (`pending_stage`), nao a etapa que acabou de ser assinada. "O OTC validou"
     nao diz a quem interessa; "isto agora esta em Pending MO" diz;
  2. os quatro rotulos de `_MC_STAGE_NOTIFY_ROLES` batendo com as constantes
     `manual_conf.PENDING_*`. Eles sao escritos por extenso (o modulo e importado
     preguicosamente), e se um mudasse de um lado so a etapa cairia no `else` e o
     aviso voltaria a ir para TODOS, sem erro nenhum;
  3. varios papeis numa notificacao so -- a coluna `target_role` sempre guardou
     um papel, e Pending MO precisa avisar dois. O filtro do sino tem de casar a
     lista E continuar casando o valor antigo de um papel so;
  4. a matriz de quem assina cada etapa, do outro lado da mesma regra.

Nao encosta em dado real: o DuckDB do filtro e in-memory e o cadastro e stub.
"""
import io
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import duckdb                                              # noqa: E402
from apps.pages import routes as R                         # noqa: E402
from apps.pages import manual_conf as M                    # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('== 1. os rotulos das etapas batem com o manual_conf ==')
check('as quatro etapas pendentes tem destinatario',
      sorted(R._MC_STAGE_NOTIFY_ROLES),
      sorted([M.PENDING_OTC, M.PENDING_MO, M.PENDING_FO, M.PENDING_MOFO]))
check('   e `Ok` NAO tem (o fim da esteira vai para todos)',
      M.STATUS_OK in R._MC_STAGE_NOTIFY_ROLES, False)

print('\n== 2. quem recebe cada etapa ==')
check('Pending MO avisa MO e BO', set(R._MC_STAGE_NOTIFY_ROLES[M.PENDING_MO]),
      {'MO', 'BO', 'MASTER'})
check('   e nao o FO', 'FO' in R._MC_STAGE_NOTIFY_ROLES[M.PENDING_MO], False)
check('Pending FO avisa FO e BO', set(R._MC_STAGE_NOTIFY_ROLES[M.PENDING_FO]),
      {'FO', 'BO', 'MASTER'})
check('   e nao o MO', 'MO' in R._MC_STAGE_NOTIFY_ROLES[M.PENDING_FO], False)
check('Pending OTC avisa so o BO', set(R._MC_STAGE_NOTIFY_ROLES[M.PENDING_OTC]),
      {'BO', 'MASTER'})
check('as duas mesas em paralelo avisam as duas',
      set(R._MC_STAGE_NOTIFY_ROLES[M.PENDING_MOFO]), {'MO', 'FO', 'BO', 'MASTER'})
# ADMIN foi deixado de fora pelo mesmo motivo que o tirou da validacao.
check('ADMIN nao entra em nenhuma',
      any('ADMIN' in v for v in R._MC_STAGE_NOTIFY_ROLES.values()), False)

print('\n== 3. o destino sai do ESTADO, nao da etapa assinada ==')
# Produto sem linha no cadastro cai em OTC + MO (DEFAULT_RULE), entao o FO nao
# valida esse documento -- e nao pode ser avisado por ele.
_real = M._mapping_rows
try:
    M._mapping_rows = lambda key: ([{'PRODUCT': 'FXO', 'LOB': '', 'OTC': 'REQUESTED',
                                     'MO': 'REQUESTED', 'FO': 'REQUESTED'}]
                                   if key == 'manual-conf-validation' else _real(key))

    def linha(**kw):
        r = {'Produto': 'FXO', 'LOB': '', 'Conferido OTC': '', 'VALIDADO p/ MO': '',
             'VALIDADO p/ FO': ''}
        r.update(kw)
        return r

    so_otc = linha()
    pos_otc = linha(**{'Conferido OTC': '10/08/2026'})
    pos_mo = linha(**{'Conferido OTC': '10/08/2026', 'VALIDADO p/ MO': '10/08/2026'})
    pos_fo = linha(**{'Conferido OTC': '10/08/2026', 'VALIDADO p/ FO': '10/08/2026'})
    fechada = linha(**{'Conferido OTC': '10/08/2026', 'VALIDADO p/ MO': '10/08/2026',
                       'VALIDADO p/ FO': '10/08/2026'})

    check('antes do OTC carimbar, o aviso e do BO',
          R._mc_notify_roles([so_otc]), 'BO,MASTER')
    check('depois do OTC, as duas mesas seguintes',
          set(R._mc_notify_roles([pos_otc]).split(',')), {'MO', 'FO', 'BO', 'MASTER'})
    check('com o MO ja dado, so falta o FO',
          set(R._mc_notify_roles([pos_mo]).split(',')), {'FO', 'BO', 'MASTER'})
    check('   e o MO sai da lista', 'MO' in R._mc_notify_roles([pos_mo]).split(','), False)
    check('com o FO ja dado, so falta o MO',
          set(R._mc_notify_roles([pos_fo]).split(',')), {'MO', 'BO', 'MASTER'})
    check('confirmacao fechada volta a avisar TODOS',
          R._mc_notify_roles([fechada]), '')
    # Um documento cobre varias operacoes e o cadastro e por Produto x LOB: o
    # lote pode cair em etapas diferentes. Recortar pela primeira linha deixaria
    # a outra mesa sem aviso.
    check('lote em etapas diferentes une os papeis',
          set(R._mc_notify_roles([pos_mo, pos_fo]).split(',')),
          {'MO', 'FO', 'BO', 'MASTER'})
    check('   e uma linha fechada no meio nao alarga o alvo',
          set(R._mc_notify_roles([pos_mo, fechada]).split(',')), {'FO', 'BO', 'MASTER'})
finally:
    M._mapping_rows = _real

print('\n== 4. varios papeis numa notificacao so ==')
check('lista normalizada', R._notif_roles(['mo', ' BO ', 'MO']), 'MO,BO')
check('   um papel so continua valendo', R._notif_roles('ADMIN'), 'ADMIN')
check('   vazio e vazio', R._notif_roles(''), '')
check('   e uma string com virgula tambem entra', R._notif_roles('MO,BO'), 'MO,BO')

# O filtro do sino: a lista tem de casar por MEMBRO, e o valor antigo (um papel
# so, gravado antes desta mudanca) tem de continuar casando.
con = duckdb.connect(':memory:')
con.execute("CREATE TABLE n (id INT, target_role VARCHAR)")
con.execute("INSERT INTO n VALUES (1, ''), (2, 'ADMIN'), (3, 'MO,BO,MASTER'), (4, 'FO,BO,MASTER')")
SQL = ("SELECT id FROM n WHERE (COALESCE(target_role,'') = '' "
       "OR list_contains(string_split(target_role, ','), ?)) ORDER BY id")
for papel, esperado in (('MO', [1, 3]), ('FO', [1, 4]), ('BO', [1, 3, 4]),
                        ('MASTER', [1, 3, 4]), ('ADMIN', [1, 2]), ('HUB', [1])):
    check('o feed de %-6s ve %s' % (papel, esperado),
          [r[0] for r in con.execute(SQL, [papel]).fetchall()], esperado)
con.close()

print('\n== 5. e o push acorda os mesmos papeis ==')
SRC = io.open('apps/pages/routes.py', encoding='utf-8').read()
blk = SRC.split('def _push_notify', 1)[1].split('\ndef ', 1)[0]
check('o push monta um IN, nao uma igualdade', 'role IN (' in blk, True)
check('   com os papeis BINDADOS, nao interpolados',
      "'?' * len(papeis)" in blk and "role IN ({})'.format" not in blk, True)
check('   e pela mesma normalizacao do feed', '_notif_roles(target_role)' in blk, True)

print('\n== 6. do outro lado: quem ASSINA cada etapa ==')
check('Pending OTC e do Back Office', R._MC_STAGE_ROLE['OTC'], 'BO')
check('Pending MO e do MO', R._MC_STAGE_ROLE['MO'], 'MO')
check('Pending FO e do FO', R._MC_STAGE_ROLE['FO'], 'FO')
# Assinar e de UMA mesa; receber e de varias. Se os dois mapas coincidissem,
# alguem teria fundido as duas perguntas.
check('assinar e receber sao mapas diferentes',
      set(R._MC_STAGE_ROLE.values()) == set(R._MC_STAGE_NOTIFY_ROLES[M.PENDING_MO]), False)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
