"""Tipo de Cotacao / Fonte de Informacao: cadastro, nao literal no codigo.

Eram tres literais espalhados: no arquivo de Termo, `'F' if is_fixed else 'A'` e
`'340' if is_fixed else '358'`; no de Opcao, `f[17] = '5'`. Commodity nova com
cotacao diferente exigia alterar codigo e reiniciar o servidor.

Agora saem das colunas QUOTE TYPE NDF / QUOTE TYPE OPT / INFO SOURCE do mapping
Commodities x B3. Tres armadilhas moram aqui:

  * **coluna vazia (ou subjacente sem linha) tem de devolver o valor
    historico** — senao o dia em que alguem editar a tabela por outro motivo o
    arquivo sai diferente;
  * a coluna B3 CODE e um PADRAO nas linhas PREFIX ('HO"MY"', 'C_"MY"',
    'KO"MY"BNMK'), entao achar a linha do subjacente 'HOZ6' nao e comparacao de
    igualdade (§164);
  * a regra tem DUAS copias — servidor e navegador —, porque o arquivo Conecta e
    montado nos dois lados (preview/download na tela, envio no servidor). Elas
    tem de responder igual.

Nao encosta em dado real: o mapping e stub em memoria.
"""
import io
import json
import os
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('\n== 1. achar a linha do subjacente ==')
for pat, code, exp in (
        ('NACX0005', 'NACX0005', True),
        ('NACX0005', 'nacx0005', True),          # caixa nao importa
        ('NACX0005', 'NAEB0011', False),
        ('HO"MY"',   'HOZ6', True),
        ('HO"MY"',   'HO', False),               # sem mes/ano nao e contrato
        ('HO"MY"',   'HUZ6', False),
        ('C_"MY"',   'C Z7', True),              # o _ e um espaco de verdade
        ('C_"MY"',   'CZ7', False),
        ('KO"MY"BNMK', 'KOZ7BNMK', True),        # padrao com sufixo
        ('KO"MY"BNMK', 'KOZ7', False),
        ('', 'HOZ6', False),
        ('HO"MY"', '', False)):
    check('%-12r x %-10r' % (pat, code), R._b3_code_matches(pat, code), exp)

print('\n== 2. o que sai para cada subjacente ==')
# O flag FIXED QUOTE foi aposentado (§252): o F/340 das linhas que eram YES
# esta MATERIALIZADO nas colunas (o upgrade faz isso ao ler arquivo antigo);
# coluna vazia ou subjacente sem linha cai no default unico A / 5 / 358.
STUB = [
    {'TYPE': 'FIXED', 'B3 CODE': 'NACX0005', 'QUOTE TYPE NDF': 'F', 'INFO SOURCE': '340'},
    {'TYPE': 'PREFIX', 'B3 CODE': 'HO"MY"'},
    {'TYPE': 'PREFIX', 'B3 CODE': 'C_"MY"',
     'QUOTE TYPE NDF': 'X', 'QUOTE TYPE OPT': '9', 'INFO SOURCE': '999'},
    {'TYPE': 'FIXED', 'B3 CODE': 'ZZFIX',
     'QUOTE TYPE NDF': '', 'QUOTE TYPE OPT': '', 'INFO SOURCE': ''},
]
_orig = R._mapping_rows
R._mapping_rows = lambda key: STUB if key == 'commodities-b3' else _orig(key)
try:
    check('F/340 materializado na linha', R._b3_quote_cfg('NACX0005'),
          {'ndf': 'F', 'opt': '5', 'source': '340'})
    check('linha sem as colunas -> A/358', R._b3_quote_cfg('HOZ6'),
          {'ndf': 'A', 'opt': '5', 'source': '358'})
    check('cadastrado manda', R._b3_quote_cfg('C Z7'),
          {'ndf': 'X', 'opt': '9', 'source': '999'})
    check('coluna VAZIA cai no default', R._b3_quote_cfg('ZZFIX'),
          {'ndf': 'A', 'opt': '5', 'source': '358'})
    check('subjacente sem linha nenhuma', R._b3_quote_cfg('NAO_EXISTE'),
          {'ndf': 'A', 'opt': '5', 'source': '358'})
    check('subjacente vazio', R._b3_quote_cfg(''),
          {'ndf': 'A', 'opt': '5', 'source': '358'})
finally:
    R._mapping_rows = _orig

print('\n== 3. seed e upgrade escrevem o comportamento historico ==')
seed = R._MAPPING_DEFS['commodities-b3']['seed']
falta = [r.get('B3 CODE') for r in seed
         if not all(k in r for k in ('QUOTE TYPE NDF', 'QUOTE TYPE OPT', 'INFO SOURCE'))]
check('toda linha do seed tem as tres colunas', falta, [])
# Os markets que eram FIXED QUOTE = YES carregam o F/340 escrito nas colunas;
# o flag em si nao existe mais em linha nenhuma (§252).
_ERAM_YES = {'FO_0.5%_ROT_BRG_FOB', 'FO_0.5%_SING_FOB', 'COAL_HCC_FOB_AUS_TSI'}
errados = [(r.get('MARKET'), r.get('QUOTE TYPE NDF'), r.get('INFO SOURCE')) for r in seed
           if (r.get('QUOTE TYPE NDF'),
               r.get('INFO SOURCE')) != (('F', '340') if r.get('MARKET') in _ERAM_YES
                                         else ('A', '358'))]
check('e com o valor que o codigo usava', errados, [])
check('a Opcao nasce com o 5', {r.get('QUOTE TYPE OPT') for r in seed}, {'5'})
check('o flag aposentado nao esta no seed',
      [r.get('B3 CODE') for r in seed if 'FIXED QUOTE' in r], [])
check('os PTS* sairam do seed',
      [r for r in seed if str(r.get('B3 CODE') or '').startswith('PTS')], [])

antiga = [{'TYPE': 'FIXED', 'MARKET': 'X', 'B3 CODE': 'ABC', 'FIXED QUOTE': 'YES'}]
up = R._commodities_b3_upgrade(antiga)
check('linha antiga ganha as colunas (o YES materializa F/340)',
      (up[0]['QUOTE TYPE NDF'], up[0]['QUOTE TYPE OPT'], up[0]['INFO SOURCE']),
      ('F', '5', '340'))
check('   e o flag sai da linha', 'FIXED QUOTE' in up[0], False)
limpa = [{'B3 CODE': 'ABC', 'FIXED QUOTE': 'YES', 'QUOTE TYPE NDF': '',
          'QUOTE TYPE OPT': '', 'INFO SOURCE': ''}]
check('coluna apagada na tela continua apagada',
      [R._commodities_b3_upgrade(limpa)[0][k] for k in
       ('QUOTE TYPE NDF', 'QUOTE TYPE OPT', 'INFO SOURCE')], ['', '', ''])
pts_antigo = [{'TYPE': 'FIXED', 'MARKET': '', 'B3 CODE': 'PTS005', 'FIXED QUOTE': 'YES'},
              {'TYPE': 'FIXED', 'MARKET': 'NG_NYMEX', 'B3 CODE': 'NG1'}]
check('os PTS* saem do arquivo antigo na migracao',
      [r.get('B3 CODE') for r in R._commodities_b3_upgrade(pts_antigo)], ['NG1'])

print('\n== 4. nenhum consumidor guarda mais o literal ==')
src = io.open('apps/pages/routes.py', encoding='utf-8').read()
check('Termo: sem o F/A no codigo', "'F' if is_fixed else 'A'" in src, False)
check('Termo: sem o 340/358 no codigo', "'340' if is_fixed else '358'" in src, False)
check('Termo: le do cadastro', "tipo_cotacao = _q['ndf']" in src, True)
check('Termo: fonte le do cadastro', "fonte_info   = _q['source']" in src, True)
# Desde o File Interface v3 a montagem e por seq do template (values dict).
check('Opcao: sem o 5 literal', "f[17] = '5'" in src and "'18': '5'" in src, False)
check('Opcao: le do cadastro',
      "'18': _b3_quote_cfg(_sh(deal.get('UnderlyingAsset', '')))['opt']" in src, True)

NDF_PAGES = ['new_deals-ndf-commodities', 'new_deals-ndf-vanilla',
             'new_deals-ndf-otherpublisher', 'new_deals-ndf-fwdstart']
for name in NDF_PAGES + ['new_deals-opt-commodities']:
    page = io.open('apps/templates/pages/%s.html' % name, encoding='utf-8').read()
    check('%s carrega o helper' % name, 'js/b3-quote-config.js' in page, True)
    check('%s sem lista literal de fixed' % name, '_FIXED_UND' in page, False)
    if name in NDF_PAGES:
        check('%s le do cadastro' % name,
              'var _q          = B3Quote.cfg(underlying);' in page, True)
        check('%s sem o F/A literal' % name, "isFixed ? 'F' : 'A'" in page, False)
    else:
        check('%s le do cadastro' % name,
              "f[17] = B3Quote.cfg(_sh(deal.UnderlyingAsset || '')).opt;" in page, True)

print('\n== 5. paridade Python x navegador ==')
JSC = '/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc'
CASES = [('NACX0005', 'NACX0005'), ('NACX0005', 'NAEB0011'), ('HO"MY"', 'HOZ6'),
         ('HO"MY"', 'HO'), ('C_"MY"', 'C Z7'), ('C_"MY"', 'CZ7'),
         ('KO"MY"BNMK', 'KOZ7BNMK'), ('KO"MY"BNMK', 'KOZ7'), ('', 'HOZ6')]
if not os.path.exists(JSC):
    print('  --  jsc ausente (Windows): a paridade nao roda aqui')
else:
    js = io.open('apps/static/js/b3-quote-config.js', encoding='utf-8').read()
    prog = ('var window = {};\n'
            'var fetch = function(){return {then:function(){return this;},'
            'catch:function(){return this;}};};\n' + js +
            '\nvar B = window.B3Quote;\nvar out = [];\n'
            'var cases = %s;\n'
            'for (var i = 0; i < cases.length; i++) '
            'out.push(B.matches(cases[i][0], cases[i][1]));\n'
            'out.push(B.cfg("QUALQUER"));\n'
            'print(JSON.stringify(out));\n' % json.dumps(CASES))
    res = subprocess.run([JSC, '-e', prog], capture_output=True, text=True)
    if res.returncode != 0:
        check('o jsc rodou', res.stderr.strip()[:200], '')
    else:
        got = json.loads(res.stdout.strip())
        js_match, js_cfg = got[:-1], got[-1]
        py_match = [R._b3_code_matches(p, c) for p, c in CASES]
        check('matches: mesma resposta nos dois lados', js_match, py_match)
        # Sem cadastro carregado, o navegador tem de dar o mesmo default.
        _o = R._mapping_rows
        R._mapping_rows = lambda key: [] if key == 'commodities-b3' else _o(key)
        try:
            check('cfg sem cadastro: mesmo default', js_cfg, R._b3_quote_cfg('QUALQUER'))
        finally:
            R._mapping_rows = _o

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
