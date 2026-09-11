# -*- coding: utf-8 -*-
"""O backfill da esteira: TODO produto que gera documento tem caminho de volta.

`_mc_save_from_deal` roda no MAPEAMENTO e nao retroage. Quem traz para a
esteira o que ja estava mapeado quando o produto passou a gerar documento e o
`scripts/backfill_manual_confirmations.py` — e ele varre por PASTA do cache.

A armadilha e que as duas listas vivem longe uma da outra: `produto entra na
esteira` mora em `_MC_CONFIRMATION_SOURCES` (plataforma) e `pasta que o
backfill varre` mora no `FAMILIES` (script). Um produto novo na primeira sem
entrada na segunda nao da erro nenhum: as operacoes NOVAS entram na esteira e
as ANTIGAS ficam invisiveis para sempre no Confirmations Monitor. Foi o que
aconteceu com o `NDF VANILLA` de MGT (§453) — a regra de runtime estava certa e
nao havia como recuperar o que ja estava mapeado.

O que este teste prende:

  1. **paridade**: nenhum source de `_MC_CONFIRMATION_SOURCES` fica sem familia
     no `FAMILIES`, e nenhuma familia aponta para um source que a plataforma nao
     conhece;
  2. **a regra e UMA**: a familia de source CONDICIONAL (o Vanilla) resolve pelo
     `_generic_nd_mc_source` do mapeamento, nao por um segundo teste de `LE`
     escrito no script — com dois, backfill e mapeamento discordariam de quem
     tem documento;
  3. **o Vanilla do BANCO continua FORA**: um `source` fixo na familia traria a
     pagina inteira (a de maior volume) para a esteira, que e exatamente o que o
     §453 decidiu nao fazer;
  4. **a PASTA e a do gerador**. As tres paginas genericas gravam em
     `NDF/Vanilla`, `NDF/FwdStart` e `NDF/OtherPublisher` — sem espaco. O script
     escrevia `NDF/FWD Start`, que e o ROTULO de tela: uma pasta inexistente nao
     levanta, casa com nada, e o backfill do FWD Start varria ZERO arquivo em
     silencio. O `check_nd_cache_dirs.py` prende essa grafia nos quatro arquivos
     do app e nao alcanca `scripts/` — por isso a familia generica passa a tirar
     a pasta do proprio `_GENERIC_ND_PRODUCTS`, em vez de repetir a string.
"""
import os, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages import routes as R                                    # noqa: E402
from apps.pages.platform import new_deals as ND                       # noqa: E402
import scripts.backfill_manual_confirmations as BF                    # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('== 1. paridade: todo source que gera documento tem pasta no backfill ==')
sources_bf = {cfg['source'] for cfg in BF.FAMILIES.values()}
check('nenhum source da esteira sem familia no backfill',
      sorted(R._MC_CONFIRMATION_SOURCES - sources_bf), [])
check('nenhuma familia apontando para source que a plataforma nao conhece',
      sorted(sources_bf - R._MC_CONFIRMATION_SOURCES), [])
check('toda familia declara a chave (deal ou b3id)',
      sorted({cfg['key'] for cfg in BF.FAMILIES.values()}), ['b3id', 'deal'])
# O FWD Start e chaveado pelo B3 ID (`_generic_nd_pc_trigger`); com a chave
# errada o backfill criaria a linha com o nome do deal e o mapeamento seguinte
# criaria uma SEGUNDA linha com o B3 ID.
check('o FWD Start entra pelo B3 ID',
      BF.FAMILIES['NDF FWD Start']['key'], 'b3id')

print('\n== 2. a familia condicional pergunta a regra do MAPEAMENTO ==')
vanilla = BF.FAMILIES.get('NDF Vanilla')
check('a pagina Vanilla e varrida', vanilla is not None, True)
if vanilla:
    check('e declarada como CONDICIONAL (generic), nao com source fixo',
          vanilla.get('generic'), 'vanilla')
    # É o que garante uma resposta só: o script chama esta função, e é a MESMA
    # que o `_generic_nd_pc_trigger` usa no mapeamento.
    mgt = {'LE': 'MGT', 'Deal': 'D1', 'Client': 'ACME S.A.'}
    banco = {'LE': 'JPM', 'Deal': 'D2', 'Client': 'ACME S.A.'}
    check('MGT contra cliente -> o source da familia',
          ND._generic_nd_mc_source(vanilla['generic'], mgt), vanilla['source'])
    check('BANCO -> None (fica fora da esteira, como o §453 decidiu)',
          ND._generic_nd_mc_source(vanilla['generic'], banco), None)
    check('e a regra e a MESMA funcao que o mapeamento usa',
          ND._generic_nd_mc_source is R._generic_nd_mc_source, True)

print('\n== 3. a pasta e a do GERADOR, nunca um literal no script ==')
# Toda familia tem de apontar para uma pasta que alguem ESCREVE. A generica sai
# do `_GENERIC_ND_PRODUCTS`; as outras sao subpastas literais do cache.
escritas = {os.path.basename(cfg['dir']) for cfg in R._GENERIC_ND_PRODUCTS.values()}
escritas.add(os.path.basename(R.NDF_COMM_CACHE_DIR))
for nome, cfg in sorted(BF.FAMILIES.items()):
    raiz = BF.family_root(cfg, R)
    check('%-20s -> %s' % (nome, os.path.basename(raiz)),
          (' ' in os.path.basename(raiz)), False)
check('a familia do FWD Start aponta para a pasta REAL (FwdStart, sem espaco)',
      os.path.basename(BF.family_root(BF.FAMILIES['NDF FWD Start'], R)), 'FwdStart')
check('e a do Vanilla idem',
      os.path.basename(BF.family_root(BF.FAMILIES['NDF Vanilla'], R)), 'Vanilla')
check('as genericas saem do _GENERIC_ND_PRODUCTS, nao de string no script',
      sorted(BF.family_root(c, R) for c in BF.FAMILIES.values() if c.get('generic')),
      sorted(R._GENERIC_ND_PRODUCTS[c['generic']]['dir']
             for c in BF.FAMILIES.values() if c.get('generic')))
check('nenhuma pasta com espaco no nome (o rotulo de tela nunca e caminho)',
      [n for n, c in sorted(BF.FAMILIES.items())
       if ' ' in os.path.basename(BF.family_root(c, R))], [])

print('\n== 4. o script sabe contar o que ficou fora da regra ==')
# Sem este contador a linha do resumo do Vanilla diria `varridos=5000
# criados=12` e pareceria defeito, em vez de "a maioria e do BANCO".
src = open(os.path.join(ROOT, 'scripts', 'backfill_manual_confirmations.py'),
           encoding='utf-8').read()
check('o resumo por familia mostra fora-da-regra', 'fora-da-regra' in src, True)
check('e o total tambem', "totals['fora_regra']" in src, True)
check('o save usa o source resolvido por DEAL, nao o da familia',
      'R._mc_save_from_deal(deal, deal_source, trade_number=key)' in src, True)

print('\n== 5. ponta a ponta: o MGT entra, o BANCO nao ==')
# O laco inteiro do script, com a pasta do Vanilla apontada para um tmp FORA do
# DATA_DIR (assim o armazem cai em os.walk) e a gravacao dublada: nada real e
# tocado, e o que se prova e o que chega ao `_mc_save_from_deal`.
import json, shutil, tempfile                                          # noqa: E402
from apps.pages import manual_conf as MC                               # noqa: E402

tmp = tempfile.mkdtemp(prefix='check-mc-backfill-')
_dir_orig = R._GENERIC_ND_PRODUCTS['vanilla']['dir']
_save_orig, _find_orig, _argv = R._mc_save_from_deal, MC.find_row, sys.argv
try:
    dia = os.path.join(tmp, '2026', '09', '10')
    os.makedirs(dia)
    with open(os.path.join(dia, 'ndf.json'), 'w', encoding='utf-8') as fh:
        json.dump([
            {'Status': 'Success', 'LE': 'MGT', 'Deal': 'MGT-1',
             'Client': 'ACME S.A.', 'SPN': '111', 'TradeDate': '10/09/2026'},
            {'Status': 'Success', 'LE': 'JPM', 'Deal': 'BCO-1',
             'Client': 'ACME S.A.', 'SPN': '111', 'TradeDate': '10/09/2026'},
            {'Status': 'Mapped', 'LE': 'MGT', 'Deal': 'MGT-2',
             'Client': 'ACME S.A.', 'SPN': '111', 'TradeDate': '10/09/2026'},
        ], fh)

    gravados = []
    R._GENERIC_ND_PRODUCTS['vanilla']['dir'] = tmp
    R._mc_save_from_deal = lambda deal, source, trade_number=None: gravados.append(
        (trade_number, source, deal.get('LE')))
    # O dublê responde como a esteira real: a linha passa a existir DEPOIS da
    # gravação. Sem isso a rede de segurança do script ("não gravou") dispararia
    # por causa do próprio dublê.
    MC.find_row = lambda k: ({'Trade ID': k}
                             if any(g[0] == k for g in gravados) else None)
    sys.argv = ['backfill', '--source', 'NDF VANILLA']
    BF.main()

    check('so o deal de MGT chega ao _mc_save_from_deal',
          gravados, [('MGT-1', 'NDF VANILLA', 'MGT')])
finally:
    R._GENERIC_ND_PRODUCTS['vanilla']['dir'] = _dir_orig
    R._mc_save_from_deal, MC.find_row, sys.argv = _save_orig, _find_orig, _argv
    shutil.rmtree(tmp, ignore_errors=True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
