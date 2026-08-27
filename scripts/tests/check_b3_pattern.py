"""Notacao de padrao do B3 Code (Commodities x B3) e da lista de arquivos CETIP.

Cobre:
  1. split_b3_pattern / build_b3_code em Python;
  2. PARIDADE com o JS (as duas copias, otc-fileupload.js e
     deals-processing-table.js, executadas de verdade no JavaScriptCore);
  3. o upgrade das linhas gravadas no formato antigo;
  4. os codigos emitidos para os 12 markets PREFIX + FCPO continuam os mesmos
     de antes da mudanca (o unico que muda de proposito e o FCPO);
  5. o padrao SOURCE/DEST dos arquivos CETIP: match, offset da data e
     equivalencia com os predicados antigos.

O jsc so existe no macOS; fora dele a parte 2 e pulada e o resto roda.
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

JSC = '/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc'

from apps.pages import otc_boxparse as B                 # noqa: E402
from apps.pages import routes as R
from apps.pages.features.cetip import engine as CE  # noqa: E402                       # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('\n== 1. split_b3_pattern ==')
check('aspas no fim',      B.split_b3_pattern('XB"MY"'),     ('XB', ''))
check('texto depois',      B.split_b3_pattern('KO"MY"BNMK'), ('KO', 'BNMK'))
check('_ vira espaco',     B.split_b3_pattern('C_"MY"'),     ('C ', ''))
check('_ nos dois lados',  B.split_b3_pattern('X_"MY"_Y'),   ('X ', ' Y'))
check('sem aspas = legado', B.split_b3_pattern('XB'),        ('XB', ''))
check('minusculo casa',    B.split_b3_pattern('PI"my"'),     ('PI', ''))
check('espaco dentro',     B.split_b3_pattern('PI" MY "'),   ('PI', ''))
check('vazio',             B.split_b3_pattern(''),           ('', ''))
check('None',              B.split_b3_pattern(None),         ('', ''))

print('\n== 2. build_b3_code ==')
check('XB"MY" + Dec26',    B.build_b3_code('XB"MY"', 'Dec26'),    'XBZ6')
check('C_"MY" + Dec26',    B.build_b3_code('C_"MY"', 'Dec26'),    'C Z6')
check('KO"MY"BNMK + Dec26', B.build_b3_code('KO"MY"BNMK', 'Dec26'), 'KOZ6BNMK')
check('PI"MY" + Nov28',    B.build_b3_code('PI"MY"', 'Nov28'),    'PIX8')
check('XXX"MY"XXXX',       B.build_b3_code('XXX"MY"XXXX', 'Dec27'), 'XXXZ7XXXX')
check('legado sem aspas',  B.build_b3_code('XB', 'Dec26'),        'XBZ6')
check('contrato ilegivel devolve a frente',
      B.build_b3_code('KO"MY"BNMK', 'lixo'), 'KO')
check('mes de 1 letra (May)', B.build_b3_code('SB"MY"', 'May27'), 'SBK7')
check('ano de 4 digitos usa o ultimo',
      B.build_b3_code('SB"MY"', 'May2027'), 'SBK7')

print('\n== 2b. strip_b3_marker: rede contra consumidor pre-§164 ==')
# Um cliente com o JS antigo em cache concatena o mes/ano no padrao INTEIRO:
# 'HO"MY"' + 'U' + '6'. Apagar o marcador devolve o codigo certo.
check('HO"MY"U6 -> HOU6',   B.strip_b3_marker('HO"MY"U6'),     'HOU6')
check('XB"MY"Z6 -> XBZ6',   B.strip_b3_marker('XB"MY"Z6'),     'XBZ6')
check('KO"MY"BNMKZ6',       B.strip_b3_marker('KO"MY"BNMKZ6'), 'KOBNMKZ6')
check('codigo bom nao muda', B.strip_b3_marker('HOU6'),        'HOU6')
check('fixo nao muda',      B.strip_b3_marker('PCRUDTB1'),     'PCRUDTB1')
check('minusculo tambem',   B.strip_b3_marker('HO"my"U6'),     'HOU6')
check('espaco no marcador', B.strip_b3_marker('HO" MY "U6'),   'HOU6')
check('vazio',              B.strip_b3_marker(''),             '')
check('None',               B.strip_b3_marker(None),           '')
# o que o build_b3_code emite ja esta certo — passar pela rede nao pode mexer
for pat, ctr in (('XB"MY"', 'Dec26'), ('C_"MY"', 'Dec26'), ('KO"MY"BNMK', 'Dec26')):
    code = B.build_b3_code(pat, ctr)
    check('idempotente sobre %r' % code, B.strip_b3_marker(code), code)

print('\n== 3. o upgrade migra o formato antigo ==')
old = [
    {'TYPE': 'PREFIX', 'MARKET': 'HU_RBOB_NYMEX', 'B3 CODE': 'XB'},
    {'TYPE': 'PREFIX', 'MARKET': 'C_CBOT', 'B3 CODE': 'C '},
    {'TYPE': 'FIXED', 'MARKET': 'NG_NYMEX', 'B3 CODE': 'NG1'},
    {'TYPE': 'SPECIAL', 'MARKET': 'FCPO_BURSA_MYR', 'B3 CODE': ''},
    {'TYPE': 'SPECIAL', 'MARKET': 'BRT_IPE', 'B3 CODE': ''},
    {'TYPE': 'PREFIX', 'MARKET': 'WTI_NYMEX', 'B3 CODE': 'WTI"MY"'},
    {'TYPE': 'PREFIX', 'MARKET': 'JA_CADASTRADO', 'B3 CODE': 'ZZ"MY"'},
]
up = R._commodities_b3_upgrade([dict(r) for r in old])
by = {r['MARKET']: r for r in up if r['MARKET'] not in ('BRT_IPE', 'WTI_NYMEX')}
check('prefixo simples',      by['HU_RBOB_NYMEX']['B3 CODE'], 'XB"MY"')
check('espaco vira _',        by['C_CBOT']['B3 CODE'],        'C_"MY"')
check('FIXED intocado',       by['NG_NYMEX']['B3 CODE'],      'NG1')
check('FCPO vira PREFIX',     by['FCPO_BURSA_MYR']['TYPE'],   'PREFIX')
check('FCPO ganha o padrao',  by['FCPO_BURSA_MYR']['B3 CODE'], 'KO"MY"BNMK')
check('linha nova intocada',  by['JA_CADASTRADO']['B3 CODE'], 'ZZ"MY"')
# TRADE TYPE (§251): linha antiga sem a coluna vale para os dois (BOTH); a
# SPECIAL do BRT_IPE sempre foi a regra da asiatica e a migracao dela cria a
# linha PREFIX da vanilla — os dois codigos, um por tipo.
check('linha antiga vira BOTH', by['HU_RBOB_NYMEX']['TRADE TYPE'], 'BOTH')
brt = [r for r in up if r['MARKET'] == 'BRT_IPE']
check('BRT_IPE: uma linha por tipo',
      [(r['TYPE'], r['TRADE TYPE'], r['B3 CODE']) for r in brt],
      [('SPECIAL', 'ASIAN', 'CO"MY"'), ('PREFIX', 'VANILLA', 'CO"MY"')])
# WTI (§252): a migracao restringe o PREFIX a vanilla e cria a linha FIXED
# CL1 da asiatica.
wti = [r for r in up if r['MARKET'] == 'WTI_NYMEX']
check('WTI: uma linha por tipo',
      [(r['TYPE'], r['TRADE TYPE'], r['B3 CODE']) for r in wti],
      [('PREFIX', 'VANILLA', 'WTI"MY"'), ('FIXED', 'ASIAN', 'CL1')])
# idempotencia: rodar de novo nao pode dobrar o "MY" nem re-somar a linha
# vanilla do BRT_IPE
again = R._commodities_b3_upgrade([dict(r) for r in up])
check('idempotente', {r['MARKET']: r['B3 CODE'] for r in again},
      {r['MARKET']: r['B3 CODE'] for r in up})
check('idempotente no numero de linhas', len(again), len(up))
# quem APAGOU a linha vanilla pela tela (SPECIAL ja migrada) manda: nao re-nasce
so_special = [{'TYPE': 'SPECIAL', 'MARKET': 'BRT_IPE', 'TRADE TYPE': 'ASIAN',
               'B3 CODE': 'CO"MY"', 'B3 CODE FAR': 'CO1-2'}]
check('vanilla apagada nao volta',
      len(R._commodities_b3_upgrade([dict(r) for r in so_special])), 1)

print('\n== 4. o codigo emitido nao mudou (menos o FCPO, de proposito) ==')
# Prefixos como estavam ANTES, direto do codigo-fonte antigo.
# WTI saiu daqui: a asiatica dele passou a ser o CL1 FIXED (§252, mudanca
# pedida) — os checks explicitos dele estao logo abaixo.
LEGACY_PREFIX = {
    'HU_RBOB_NYMEX': 'XB', 'HO_NYMEX': 'HO', 'SB_ICE': 'SB', 'C_CBOT': 'C ',
    'S_CBOT': 'S ', 'BO_CBOT': 'BO', 'CC_ICE': 'CC', 'W_CBOT': 'W ',
    'SM_CBOT': 'SM', 'CT_ICE': 'CT', 'KC_ICE': 'KC',
}
# Mapas montados do seed com a MESMA leitura por TRADE TYPE do
# `_box_commodity_maps` ({mkt: {'V': …, 'A': …}}, §251) — o BRT_IPE tem duas
# linhas (SPECIAL/ASIAN e PREFIX/VANILLA) e um dict por market esconderia uma.
fixed, dyn, spc = {}, {}, {}


def _tt_flags(r):
    tt = str(r.get('TRADE TYPE') or '').strip().upper()
    return ('V',) if tt == 'VANILLA' else ('A',) if tt == 'ASIAN' else ('V', 'A')


for r in R._MAPPING_DEFS['commodities-b3']['seed']:
    m = r.get('MARKET')
    if not m:
        continue
    if r['TYPE'] == 'SPECIAL':
        for f in _tt_flags(r):
            spc.setdefault(m, {})[f] = {'near': r['B3 CODE'], 'far': r.get('B3 CODE FAR', '')}
    elif r['TYPE'] == 'PREFIX':
        for f in _tt_flags(r):
            dyn.setdefault(m, {})[f] = r['B3 CODE']
    else:
        for f in _tt_flags(r):
            fixed.setdefault(m, {})[f] = r['B3 CODE']
for contract in ('Dec26', 'May27', 'Jan30'):
    p = B._contract_parts(contract)
    for mkt, old_prefix in LEGACY_PREFIX.items():
        was = old_prefix + p[0] + p[1]
        now = B.calculate_b3_id(mkt, contract, False, fixed, dyn)
        check('%s %s' % (mkt, contract), now, was)

check('FCPO (mudanca pedida)', B.calculate_b3_id('FCPO_BURSA_MYR', 'Dec26', False, fixed, dyn),
      'KOZ6BNMK')
# WTI (§252, mudanca pedida): vanilla segue o padrao de contrato; asiatica
# usa o continuo CL1, literal, sem mes/ano.
check('WTI vanilla segue o contrato',
      B.calculate_b3_id('WTI_NYMEX', 'Dec26', True, fixed, dyn), 'WTIZ6')
check('WTI asiatica e o CL1',
      B.calculate_b3_id('WTI_NYMEX', 'Dec26', False, fixed, dyn), 'CL1')
# O seed traz os dois codigos do BRT_IPE, agora um por TRADE TYPE (§251): a
# linha SPECIAL (near/far) e SO da asiatica e a vanilla tem linha PREFIX
# propria. O codigo emitido nao mudou: vanilla COZ6, asiatica sem data CO1-2.
check('o seed cadastra a SPECIAL so para a asiatica', spc.get('BRT_IPE'),
      {'A': {'near': 'CO"MY"', 'far': 'CO1-2'}})
check('   e a PREFIX so para a vanilla', dyn.get('BRT_IPE'), {'V': 'CO"MY"'})
check('BRT_IPE vanilla', B.calculate_b3_id('BRT_IPE', 'Dec26', True, fixed, dyn, spc), 'COZ6')
check('BRT_IPE asian',   B.calculate_b3_id('BRT_IPE', 'Dec26', False, fixed, dyn, spc), 'CO1-2')
# O filtro por tipo em si: uma linha VANILLA nao responde pela asiatica (cai na
# regra generica de prefixo) e vice-versa; BOTH e formato antigo valem para os dois.
TYPED = {'ZZ_FOO': {'V': 'ZV"MY"'}}
check('linha VANILLA nao vale para asiatica',
      B.calculate_b3_id('ZZ_FOO', 'Dec26', False, {}, TYPED), 'ZZZ6')
check('   mas vale para vanilla',
      B.calculate_b3_id('ZZ_FOO', 'Dec26', True, {}, TYPED), 'ZVZ6')
check('formato antigo (plano) vale para os dois',
      B.calculate_b3_id('ZZ_FOO', 'Dec26', False, {}, {'ZZ_FOO': 'ZP"MY"'}), 'ZPZ6')
check('FIXED tipado tambem filtra',
      B.calculate_b3_id('NG_NYMEX', 'Dec26', True, {'NG_NYMEX': {'A': 'NG1'}}, {}), 'NGZ6')
# Consequencia de tirar a linha do cadastro, escrita aqui para nao virar
# surpresa: sem a linha SPECIAL o market cai na regra generica de prefixo e sai
# 'BRT' + mes/ano. E o mesmo que acontece com qualquer market sem cadastro, mas
# aqui o codigo errado se PARECE com um codigo certo.
check('sem a linha SPECIAL cai no prefixo generico',
      B.calculate_b3_id('BRT_IPE', 'Dec26', False, fixed, dyn, {}), 'BRTZ6')
check('FIXED continua literal', B.calculate_b3_id('NG_NYMEX', 'Dec26', False, fixed, dyn), 'NG1')
check('market desconhecido usa o trecho antes do _',
      B.calculate_b3_id('ZZ_FOO', 'Dec26', False, fixed, dyn), 'ZZZ6')

print('\n== 5. paridade com o JS (jsc) ==')
if not os.path.exists(JSC):
    print('  --  jsc ausente (nao e macOS) — parte pulada')
else:
    CASES = [('XB"MY"', 'Dec26'), ('C_"MY"', 'Dec26'), ('KO"MY"BNMK', 'Dec26'),
             ('PI"MY"', 'Nov28'), ('XXX"MY"XXXX', 'Dec27'), ('XB', 'Dec26'),
             ('KO"MY"BNMK', 'lixo'), ('S_"MY"', 'May27'), ('X_"MY"_Y', 'Jan30'),
             ('PI" my "', 'Feb29')]
    for jsfile in ('apps/static/js/pages/otc-fileupload.js',
                   'apps/static/js/pages/deals-processing-table.js'):
        src = io.open(jsfile, encoding='utf-8').read()
        # recorta as 3 funcoes de que o teste precisa
        need = []
        for fn in ('splitB3Pattern', 'buildB3Code', 'contractParts'):
            m = re.search(r'\n    function ' + fn + r'\(.*?\n    \}\n', src, re.S)
            assert m, '%s: nao achei %s' % (jsfile, fn)
            need.append(m.group(0))
        mre = re.search(r'\n    var B3_MY_RE = [^\n]+\n', src)
        assert mre, '%s: nao achei B3_MY_RE' % jsfile
        mmc = re.search(r'\n    var MONTH_CODES = \{.*?\n    \};\n', src, re.S)
        mmn = re.search(r'\n    var MONTH_NAMES_ABBR = \{.*?\n    \};\n', src, re.S)
        harness = (mmc.group(0) + mmn.group(0) + mre.group(0) + ''.join(need) +
                   '\nvar OUT = [];\n' +
                   'var CASES = ' + json.dumps(CASES) + ';\n' +
                   'for (var i = 0; i < CASES.length; i++) {'
                   '  OUT.push(buildB3Code(CASES[i][0], CASES[i][1])); }\n'
                   'print(JSON.stringify(OUT));\n')
        fd, path = tempfile.mkstemp(suffix='.js')
        os.write(fd, harness.encode('utf-8'))
        os.close(fd)
        try:
            r = subprocess.run([JSC, path], capture_output=True, text=True)
            out = (r.stdout or '').strip()
            if not out:
                check('%s executou' % os.path.basename(jsfile), r.stderr.strip()[:200], '')
                continue
            js_out = json.loads(out)
        finally:
            os.unlink(path)
        py_out = [B.build_b3_code(p, c) for p, c in CASES]
        for (pat, con), j, p_ in zip(CASES, js_out, py_out):
            check('%s: %s + %s' % (os.path.basename(jsfile)[:12], pat, con), j, p_)

# ── BRT_IPE: a regra vive em TRES lugares (o Python e as duas copias JS) ──────
# O check_boxparse.py so compara o otc-fileupload.js; o deals-processing-table.js
# ja divergiu dele antes (§164, o FCPO saia '.KOZ7BNMK F' de um lado e 'KOZ7BNMK'
# do outro). Aqui as DUAS copias sao executadas contra o mesmo Python.
print('\n== 5b. calculateB3Id do BRT_IPE nas duas copias JS ==')
SPECIAL = {'BRT_IPE': {'near': 'CO"MY"', 'far': 'CO1-2'}}
# (contrato, data de liquidacao, vanilla) -> o codigo esperado
IPE_CASES = [('Mar27', '05/01/2027', False, 'CO1-2'),   # 2 meses a frente
             ('Mar27', '02/02/2027', False, 'COH7'),    # 1 mes a frente
             ('Mar27', '28/02/2027', False, 'COH7'),    # o DIA nao conta
             ('Jan27', '05/12/2026', False, 'COF7'),    # vira o ano
             ('Mar27', '05/12/2026', False, 'CO1-2'),   # 3 meses
             ('Mar27', '05/03/2027', False, 'CO1-2'),   # mesmo mes
             ('Mar27', '',           False, 'CO1-2'),   # sem data = como era
             ('Mar27', 'lixo',       False, 'CO1-2'),
             ('Mar27', '2027-02-02', False, 'COH7'),    # o input date manda ISO
             ('Mar27', '05/01/2027', True,  'COH7'),    # vanilla nao mudou
             ('Mar27', '',           True,  'COH7')]
if not os.path.exists(JSC):
    print('  --  jsc ausente (nao e macOS) — so o Python')
for ctr, sd, van, exp in IPE_CASES:
    check('py: %s %s van=%s' % (ctr, sd or '(sem data)', van),
          B.calculate_b3_id('BRT_IPE', ctr, van, {}, {}, SPECIAL, sd), exp)
if os.path.exists(JSC):
    for jsfile in ('apps/static/js/pages/otc-fileupload.js',
                   'apps/static/js/pages/deals-processing-table.js'):
        src = io.open(jsfile, encoding='utf-8').read()
        need = []
        for fn in ('splitB3Pattern', 'buildB3Code', 'contractParts',
                   'contractMonthYear', 'dateMonthYear', 'monthsAhead',
                   'b3MapEntry', 'calculateB3Id'):
            m = re.search(r'\n    function ' + fn + r'\(.*?\n    \}\n', src, re.S)
            assert m, '%s: nao achei %s' % (jsfile, fn)
            need.append(m.group(0))
        # O MONTH_ABBR_ORDER ocupa DUAS linhas — o padrao de uma linha so
        # recortava metade do array, e o jsc reclamava de sintaxe num ponto que
        # nao tinha nada a ver com o teste.
        for var, pat in (('B3_MY_RE', r'\n    var B3_MY_RE = [^\n]+\n'),
                         ('MONTH_ABBR_ORDER', r'\n    var MONTH_ABBR_ORDER = \[.*?\];\n')):
            m = re.search(pat, src, re.S)
            assert m, '%s: nao achei %s' % (jsfile, var)
            need.append(m.group(0))
        mmc = re.search(r'\n    var MONTH_CODES = \{.*?\n    \};\n', src, re.S)
        mmn = re.search(r'\n    var MONTH_NAMES_ABBR = \{.*?\n    \};\n', src, re.S)
        harness = (mmc.group(0) + mmn.group(0) + ''.join(need) +
                   '\nvar MARKET_FIXED_CODES = {}, MARKET_DYNAMIC_PREFIX = {};\n' +
                   'var MARKET_SPECIAL_CODES = ' + json.dumps(SPECIAL) + ';\n' +
                   'var CASES = ' + json.dumps([[c, d, v] for c, d, v, _ in IPE_CASES]) + ';\n' +
                   'var OUT = CASES.map(function (x) {'
                   '  return calculateB3Id("BRT_IPE", x[0], x[2], x[1]); });\n'
                   'print(JSON.stringify(OUT));\n')
        fd, path = tempfile.mkstemp(suffix='.js')
        os.write(fd, harness.encode('utf-8'))
        os.close(fd)
        try:
            r = subprocess.run([JSC, path], capture_output=True, text=True)
            out = (r.stdout or '').strip()
            if not out:
                check('%s executou' % os.path.basename(jsfile), r.stderr.strip()[:300], '')
                continue
            js_out = json.loads(out)
        finally:
            os.unlink(path)
        for (ctr, sd, van, exp), js in zip(IPE_CASES, js_out):
            check('%s: %s %s van=%s' % (os.path.basename(jsfile)[:12], ctr,
                                        sd or '(sem data)', van), js, exp)

print('\n== 6. padrao dos arquivos CETIP ==')
check('offset e final', CE._cetip_split_pattern('CETIP21_YYMMDD_DPOSICAO-SWAP'),
      (8, '_dposicao-swap'))
check('extensao descartada', CE._cetip_split_pattern('SIC_YYMMDD_DCADCOMITENTES.TXT'),
      (4, '_dcadcomitentes'))
check('sem YYMMDD', CE._cetip_split_pattern('SEM_DATA'), None)
check('aplica a data', CE._cetip_apply_date('73760_YYMMDD_DPOSICAO.CETIP21', '260731'),
      '73760_260731_DPOSICAO.CETIP21')
check('aplica em minusculo tambem', CE._cetip_apply_date('x_yymmdd_y', '260731'), 'x_260731_y')

# O match novo tem de aceitar o que o antigo aceitava e recusar o que recusava.
LEGACY = [
    ('CETIP21_YYMMDD_DPOSICAO-SWAP', lambda n: 'dposicao-swap.txt' in n,
     ['CETIP21_260731_DPOSICAO-SWAP.TXT', 'cetip21_260731_dposicao-swap.txt'],
     ['CETIP21_260731_DPOSICAO_C21.TXT', 'CETIP21_260731_DMOVIMENTO-SWAP.TXT']),
    ('CETIP21_YYMMDD_DPOSICAO_C21', lambda n: 'dposicao_c21.txt' in n,
     ['CETIP21_260731_DPOSICAO_C21.TXT'],
     ['CETIP21_260731_DPOSICAO-SWAP.TXT']),
    ('OPC_YYMMDD_DPOSICAO', lambda n: 'opc_' in n and '_dposicao.txt' in n,
     ['OPC_260731_DPOSICAO.TXT'],
     ['OPC_260731_DMOVIMENTO.TXT', 'CETIP21_260731_DPOSICAO_C21.TXT']),
    ('OPC_YYMMDD_DMOVIMENTO',
     lambda n: ('opc_' in n and '_dmovimento.txt' in n
                and '_15h00.txt' not in n and '_18h30.txt' not in n),
     ['OPC_260731_DMOVIMENTO.TXT'],
     # as variantes de horario ficam de fora sozinhas: o padrao casa o nome
     # INTEIRO, entao o _15H00 no fim ja nao bate
     ['OPC_260731_DMOVIMENTO_15H00.TXT', 'OPC_260731_DMOVIMENTO_18H30.TXT']),
    ('SIC_YYMMDD_DCADCOMITENTES', lambda n: '_dcadcomitentes.txt' in n,
     ['SIC_260731_DCADCOMITENTES.TXT'], ['SIC_260731_DPOSCONTRATOSIC.TXT']),
]
for pattern, legacy, should, shouldnt in LEGACY:
    m = CE._cetip_make_matcher(pattern, 'test')
    for name in should:
        check('%s casa %s' % (pattern.split('_')[-1], name), m(name.lower()), True)
        check('  (o antigo tambem casava)', legacy(name.lower()), True)
    for name in shouldnt:
        check('%s NAO casa %s' % (pattern.split('_')[-1], name), m(name.lower()), False)

# data invalida na posicao do YYMMDD -> nao casa
mm = CE._cetip_make_matcher('CETIP21_YYMMDD_DPOSICAO-SWAP', 'test')
check('data nao numerica nao casa', mm('cetip21_abcdef_dposicao-swap.txt'), False)
check('nome curto demais nao casa', mm('dposicao-swap.txt'), False)

print('\n== 7. o seed e o comportamento cobrem os MESMOS tipos ==')
tmp = tempfile.mkdtemp()
R._MAPPINGS_DIR = tmp                    # nao encosta no arquivo real
R._mapping_cache.pop('cetip-files', None)
rules = CE._cetip_rules()
# O numero cresce quando a CETIP publica um arquivo novo; o que nao pode
# variar e a PARIDADE com o comportamento, conferida logo abaixo — um tipo
# so no seed nunca vira anexo, e um so no codigo nunca roda.
check('uma regra por linha do seed', len(rules), len(R._CETIP_FILES_SEED))
check('todas com match', all(callable(r['match']) for r in rules), True)
check('todas com dest_name', all(callable(r['dest_name']) for r in rules), True)
labels = [r['label'] for r in rules]
check('labels batem com o comportamento',
      sorted(labels), sorted(CE._CETIP_BEHAVIOUR.keys()))

by_label = {r['label']: r for r in rules}
# os offsets tem de ser os mesmos que estavam fixos no codigo
OLD_DS = {'NDF Position (DPOSICAO C21)': 8, 'SWAP Position (DPOSICAO-SWAP)': 8,
          'Option Position (OPC DPOSICAO)': 4, 'Option Movement (OPC DMOVIMENTO)': 4,
          'NDF Movement (DMOVIMENTO C21)': 8, 'SWAP Movement (DMOVIMENTO-SWAP)': 8,
          'SWAP Flow (DFLUXO_SWAP)': 8, 'SWAP Premium Agenda (DAGENDAPREMIOS)': 8,
          'SWAP Indexers (INDEXADORESSWAP_VCP)': 8, 'Operations (DOPERACOES)': 8,
          'COE (DRESUMOEMISSOR-COE)': 8, 'Accelerator Agent (MID DAGENTEACELERADOR)': 8,
          'NDF Position (DPOSICAO-TER)': 4, 'SIC Contract Position (DPOSCONTRATOSIC)': 4,
          'Comitente Registry (DCADCOMITENTES)': 4}
for label, ds in OLD_DS.items():
    check('offset %s' % label[:28], by_label[label]['date_start'], ds)

# os nomes de destino tem de sair iguais aos das lambdas antigas
OLD_DEST = {
    'NDF Position (DPOSICAO C21)': '73760_260731_DPOSICAO.CETIP21',
    'SWAP Position (DPOSICAO-SWAP)': '73760_260731_DPOSICAO-SWAP.CETIP21',
    'Option Position (OPC DPOSICAO)': '73760_260731_DPOSICAO.OPC',
    'Option Movement (OPC DMOVIMENTO)': '73760_260731_DMOVIMENTO_3.OPC',
    'NDF Movement (DMOVIMENTO C21)': '73760_260731_DMOVIMENTO.CETIP21',
    'SWAP Movement (DMOVIMENTO-SWAP)': '73760_260731_DMOVIMENTO-SWAP.CETIP21',
    'SWAP Flow (DFLUXO_SWAP)': '73760_260731_DFLUXO.CETIP21',
    'SWAP Premium Agenda (DAGENDAPREMIOS)': '73760_260731_DAGENDAPREMIOS.CETIP21',
    'SWAP Indexers (INDEXADORESSWAP_VCP)': 'CETIP21_260731_INDEXADORESSWAP_VCP.TXT',
    'Operations (DOPERACOES)': '73760_260731_DOPERACOES.CETIP21',
    'COE (DRESUMOEMISSOR-COE)': 'CETIP21_260731_SP_DRESUMOEMISSOR-COE.TXT',
    'Accelerator Agent (MID DAGENTEACELERADOR)': '73760_260731_MID_DAGENTEACELERADOR.CETIP21',
    'NDF Position (DPOSICAO-TER)': '73760_260731_DPOSICAO-TER.TER',
    'SIC Contract Position (DPOSCONTRATOSIC)': '73760_260731_DPOSCONTRATOSIC.txt',
    'Comitente Registry (DCADCOMITENTES)': 'SIC_260731_DCADCOMITENTES.txt',
}
for label, exp in OLD_DEST.items():
    check('dest %s' % label[:28], by_label[label]['dest_name']('260731'), exp)

# o comportamento (json/vcp/anexos) tem de ter sobrevivido a fusao
check('SWAP Position mantem o json',
      by_label['SWAP Position (DPOSICAO-SWAP)']['json']['header_key'], 'swap_position')
check('Indexers mantem vcp_update',
      by_label['SWAP Indexers (INDEXADORESSWAP_VCP)'].get('vcp_update'), True)
check('OPC mantem anexo CEM',
      by_label['Option Position (OPC DPOSICAO)'].get('attach_cem_latam'), True)
check('TER mantem anexo Sales Support',
      by_label['NDF Position (DPOSICAO-TER)'].get('attach_sales_support'), True)
check('Operations mantem os 2 filtros',
      len(by_label['Operations (DOPERACOES)']['json']['filters']), 2)
check('OPC mantem extra_dest',
      bool(by_label['Option Position (OPC DPOSICAO)'].get('extra_dest')), True)
check('TER mantem extra_dest',
      bool(by_label['NDF Position (DPOSICAO-TER)'].get('extra_dest')), True)
check('sem extra_dest onde nao havia',
      'extra_dest' in by_label['COE (DRESUMOEMISSOR-COE)'], False)

print('\n== 8. linha invalida na tela nao derruba a rotina ==')
R._atomic_write_json(os.path.join(tmp, 'cetip-files.json'), [
    {'TYPE': 'SWAP Position (DPOSICAO-SWAP)', 'SOURCE': 'CETIP21_YYMMDD_DPOSICAO-SWAP',
     'DEST': '73760_YYMMDD_DPOSICAO-SWAP.CETIP21', 'EXTRA DEST': ''},
    {'TYPE': 'Sem data', 'SOURCE': 'ARQUIVO_SEM_TOKEN', 'DEST': 'X', 'EXTRA DEST': ''},
    {'TYPE': '', 'SOURCE': 'CETIP21_YYMMDD_X', 'DEST': 'Y', 'EXTRA DEST': ''},
])
R._mapping_cache.pop('cetip-files', None)
rules2 = CE._cetip_rules()
check('so a linha valida entra', [r['label'] for r in rules2],
      ['SWAP Position (DPOSICAO-SWAP)'])

import shutil                                            # noqa: E402
shutil.rmtree(tmp, ignore_errors=True)
print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails[:12])))
sys.exit(1 if fails else 0)
