# -*- coding: utf-8 -*-
"""check_equity_leg_prefix.py — o cadastro que diz a que PERNA pertence cada
Trade Id do OTM (`equity-leg-prefix`).

O elo de equity — Operations B3 → Latam Desk Position → OTM — é quem dá
cliente, SPN e as três colunas de valor do Settlement Advice e o Internal ID de
EDG no Swap VCP. Um `Deal_Ref` cobre DUAS operações (a contra o cliente externo
e a contra a nossa entidade), e o relatório traz os dois identificadores da B3
na mesma linha: o PREFIXO do Trade Id é o que diz qual é qual.

Os dois jeitos de quebrar isso não dão erro nenhum, e são opostos:

  1. prefixo DESCONHECIDO → `_ops_eq_trade_key` devolve `(None, '')`, a linha
     do OTM é descartada antes de agrupar e o aviso sai com o nome curto da B3
     (a NOSSA perna) e os valores em branco. Foi o `270RI`;
  2. prefixo na perna ERRADA → a linha exibe a contraparte da OUTRA ponta, com
     valor, sem nada indicando a troca. É pior que o primeiro, e foi o que
     quase aconteceu por ler a letra final do prefixo como mnemônico: `WI`
     interna e `WC` cliente é coincidência dos dois primeiros — **`270RI` é de
     CLIENTE**, e cliente externo aparece com RI.

Por isso o de-para é cadastro e não literal, e por isso a correção do seed tem
`upgrade`: o seed só roda quando o arquivo NÃO existe, e quem já leu uma vez
ficaria com a perna trocada para sempre.
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

falhas = []


def check(rotulo, obtido, esperado):
    ok = obtido == esperado
    print(('  ok  ' if ok else ' FAIL ') + rotulo +
          ('' if ok else '\n        got=%r\n        exp=%r' % (obtido, esperado)))
    if not ok:
        falhas.append(rotulo)


from apps.pages import routes as R                                    # noqa: E402
from apps.pages.platform import settlement as S                       # noqa: E402

print('== 1. o seed: quem é de quem ==')
seed = {r['PREFIX']: r['LEG'] for r in R._MAP_EQ_LEG_SEED}
check('270WI é da nossa entidade', seed.get('270WI'), 'Internal')
check('270WC é do cliente', seed.get('270WC'), 'Client')
# A regra do negócio, não a letra do prefixo.
check('270RI é do CLIENTE — a letra final não decide', seed.get('270RI'), 'Client')
check('o cadastro do repositório concorda com o seed',
      {r['PREFIX']: r['LEG'] for r in R._mapping_rows('equity-leg-prefix')}, seed)

print('\n== 2. o cadastro manda nos prefixos ==')
_rows_real = R._mapping_rows
try:
    R._mapping_rows = lambda k: ([
        {'PREFIX': '270WI', 'LEG': 'Internal'},
        {'PREFIX': '270WC', 'LEG': 'Client'},
        {'PREFIX': '270RI', 'LEG': 'Client'},
    ] if k == 'equity-leg-prefix' else [])
    col = dict((p, c) for c, p in S._ops_eq_leg_prefixes())
    check('270RI vai para a coluna do CLIENTE', col.get('270RI'), 'CLEARING_TRD_ID_CLNT')
    check('270WI vai para a coluna INTERNA', col.get('270WI'), 'CLEARING_TRD_ID_INT')
    check('o Trade Id casa e o Deal_Ref sai sem zeros à esquerda',
          S._ops_eq_trade_key('270RI0258485'), ('270RI', '258485'))
    check('prefixo fora do cadastro não vira chave',
          S._ops_eq_trade_key('270XX0258485'), (None, ''))

    # Prefixo que é começo de outro: o MAIS LONGO tem de vencer, senão a ordem
    # do cadastro decidiria a perna.
    R._mapping_rows = lambda k: ([
        {'PREFIX': '270', 'LEG': 'Internal'},
        {'PREFIX': '270RI', 'LEG': 'Client'},
    ] if k == 'equity-leg-prefix' else [])
    check('o prefixo mais longo vence', S._ops_eq_trade_key('270RI0258485')[0], '270RI')

    # Cadastro vazio cai na semente: uma leitura falha não pode apagar o elo
    # inteiro (nome curto da B3 e valores em branco em TODA linha).
    R._mapping_rows = lambda k: []
    check('cadastro vazio cai na semente',
          sorted(p for _c, p in S._ops_eq_leg_prefixes()), ['270RI', '270WC', '270WI'])
    check('e a semente também põe 270RI no cliente',
          dict((p, c) for c, p in S._ops_eq_leg_prefixes())['270RI'], 'CLEARING_TRD_ID_CLNT')
finally:
    R._mapping_rows = _rows_real

print('\n== 3. o upgrade alcança quem já semeou errado ==')
ruim = [{'PREFIX': '270WI', 'LEG': 'Internal', 'NOTES': 'Perna da nossa entidade'},
        {'PREFIX': '270RI', 'LEG': 'Internal', 'NOTES': 'Perna da nossa entidade'}]
saida = R._equity_leg_prefix_upgrade([dict(r) for r in ruim])
check('o 270RI do seed errado é corrigido na leitura',
      saida[1]['LEG'], 'Client')
check('e o 270WI, que estava certo, não é tocado', saida[0]['LEG'], 'Internal')
# Correção de estreia, não regra permanente: o que a mesa editou fica.
editado = [{'PREFIX': '270RI', 'LEG': 'Internal', 'NOTES': 'a mesa decidiu assim'}]
check('linha editada pela mesa não é mexida',
      R._equity_leg_prefix_upgrade([dict(r) for r in editado])[0]['LEG'], 'Internal')
check('o upgrade está pendurado na definição do mapping',
      R._MAPPING_DEFS['equity-leg-prefix'].get('upgrade'), R._equity_leg_prefix_upgrade)

print('\n== 4. a aba existe na tela ==')
html = open(os.path.join(ROOT, 'apps/templates/pages/mapping.html'), encoding='utf-8').read()
check("a aba 'equity-leg-prefix' está no TYPES", "key: 'equity-leg-prefix'" in html, True)

print('\nFALHAS: %d' % len(falhas))
if falhas:
    for f in falhas:
        print('  - %s' % f)
sys.exit(1 if falhas else 0)
