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
from apps.pages import routes as R                       # noqa: E402

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
    {'TYPE': 'PREFIX', 'MARKET': 'JA_CADASTRADO', 'B3 CODE': 'ZZ"MY"'},
]
up = R._commodities_b3_upgrade([dict(r) for r in old])
by = {r['MARKET']: r for r in up}
check('prefixo simples',      by['HU_RBOB_NYMEX']['B3 CODE'], 'XB"MY"')
check('espaco vira _',        by['C_CBOT']['B3 CODE'],        'C_"MY"')
check('FIXED intocado',       by['NG_NYMEX']['B3 CODE'],      'NG1')
check('FCPO vira PREFIX',     by['FCPO_BURSA_MYR']['TYPE'],   'PREFIX')
check('FCPO ganha o padrao',  by['FCPO_BURSA_MYR']['B3 CODE'], 'KO"MY"BNMK')
check('BRT_IPE segue SPECIAL', by['BRT_IPE']['TYPE'],         'SPECIAL')
check('linha nova intocada',  by['JA_CADASTRADO']['B3 CODE'], 'ZZ"MY"')
# idempotencia: rodar de novo nao pode dobrar o "MY"
again = R._commodities_b3_upgrade(up)
check('idempotente', {r['MARKET']: r['B3 CODE'] for r in again},
      {r['MARKET']: r['B3 CODE'] for r in up})

print('\n== 4. o codigo emitido nao mudou (menos o FCPO, de proposito) ==')
# Prefixos como estavam ANTES, direto do codigo-fonte antigo.
LEGACY_PREFIX = {
    'HU_RBOB_NYMEX': 'XB', 'HO_NYMEX': 'HO', 'SB_ICE': 'SB', 'C_CBOT': 'C ',
    'S_CBOT': 'S ', 'BO_CBOT': 'BO', 'CC_ICE': 'CC', 'W_CBOT': 'W ',
    'SM_CBOT': 'SM', 'CT_ICE': 'CT', 'KC_ICE': 'KC', 'WTI_NYMEX': 'WTI',
}
seed = {r['MARKET']: r for r in R._MAPPING_DEFS['commodities-b3']['seed'] if r.get('MARKET')}
fixed = {m: r['B3 CODE'] for m, r in seed.items() if r['TYPE'] == 'FIXED'}
dyn = {m: r['B3 CODE'] for m, r in seed.items() if r['TYPE'] == 'PREFIX'}
for contract in ('Dec26', 'May27', 'Jan30'):
    p = B._contract_parts(contract)
    for mkt, old_prefix in LEGACY_PREFIX.items():
        was = old_prefix + p[0] + p[1]
        now = B.calculate_b3_id(mkt, contract, False, fixed, dyn)
        check('%s %s' % (mkt, contract), now, was)

check('FCPO (mudanca pedida)', B.calculate_b3_id('FCPO_BURSA_MYR', 'Dec26', False, fixed, dyn),
      'KOZ6BNMK')
check('BRT_IPE vanilla', B.calculate_b3_id('BRT_IPE', 'Dec26', True, fixed, dyn), 'COZ6')
check('BRT_IPE asian',   B.calculate_b3_id('BRT_IPE', 'Dec26', False, fixed, dyn), 'CO1-2')
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

print('\n== 6. padrao dos arquivos CETIP ==')
check('offset e final', R._cetip_split_pattern('CETIP21_YYMMDD_DPOSICAO-SWAP'),
      (8, '_dposicao-swap'))
check('extensao descartada', R._cetip_split_pattern('SIC_YYMMDD_DCADCOMITENTES.TXT'),
      (4, '_dcadcomitentes'))
check('sem YYMMDD', R._cetip_split_pattern('SEM_DATA'), None)
check('aplica a data', R._cetip_apply_date('73760_YYMMDD_DPOSICAO.CETIP21', '260731'),
      '73760_260731_DPOSICAO.CETIP21')
check('aplica em minusculo tambem', R._cetip_apply_date('x_yymmdd_y', '260731'), 'x_260731_y')

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
    m = R._cetip_make_matcher(pattern, 'test')
    for name in should:
        check('%s casa %s' % (pattern.split('_')[-1], name), m(name.lower()), True)
        check('  (o antigo tambem casava)', legacy(name.lower()), True)
    for name in shouldnt:
        check('%s NAO casa %s' % (pattern.split('_')[-1], name), m(name.lower()), False)

# data invalida na posicao do YYMMDD -> nao casa
mm = R._cetip_make_matcher('CETIP21_YYMMDD_DPOSICAO-SWAP', 'test')
check('data nao numerica nao casa', mm('cetip21_abcdef_dposicao-swap.txt'), False)
check('nome curto demais nao casa', mm('dposicao-swap.txt'), False)

print('\n== 7. as 15 regras continuam de pe ==')
tmp = tempfile.mkdtemp()
R._MAPPINGS_DIR = tmp                    # nao encosta no arquivo real
R._mapping_cache.pop('cetip-files', None)
rules = R._cetip_rules()
check('15 regras', len(rules), 15)
check('todas com match', all(callable(r['match']) for r in rules), True)
check('todas com dest_name', all(callable(r['dest_name']) for r in rules), True)
labels = [r['label'] for r in rules]
check('labels batem com o comportamento',
      sorted(labels), sorted(R._CETIP_BEHAVIOUR.keys()))

by_label = {r['label']: r for r in rules}
# os offsets tem de ser os mesmos que estavam fixos no codigo
OLD_DS = {'NDF Position (DPOSICAO C21)': 8, 'SWAP Position (DPOSICAO-SWAP)': 8,
          'Option Position (OPC DPOSICAO)': 4, 'Option Movement (OPC DMOVIMENTO)': 4,
          'Term Movement (DMOVIMENTO C21)': 8, 'SWAP Movement (DMOVIMENTO-SWAP)': 8,
          'SWAP Flow (DFLUXO_SWAP)': 8, 'SWAP Premium Agenda (DAGENDAPREMIOS)': 8,
          'SWAP Indexers (INDEXADORESSWAP_VCP)': 8, 'Operations (DOPERACOES)': 8,
          'COE (DRESUMOEMISSOR-COE)': 8, 'Accelerator Agent (MID DAGENTEACELERADOR)': 8,
          'Term Position (DPOSICAO-TER)': 4, 'SIC Contract Position (DPOSCONTRATOSIC)': 4,
          'Comitente Registry (DCADCOMITENTES)': 4}
for label, ds in OLD_DS.items():
    check('offset %s' % label[:28], by_label[label]['date_start'], ds)

# os nomes de destino tem de sair iguais aos das lambdas antigas
OLD_DEST = {
    'NDF Position (DPOSICAO C21)': '73760_260731_DPOSICAO.CETIP21',
    'SWAP Position (DPOSICAO-SWAP)': '73760_260731_DPOSICAO-SWAP.CETIP21',
    'Option Position (OPC DPOSICAO)': '73760_260731_DPOSICAO.OPC',
    'Option Movement (OPC DMOVIMENTO)': '73760_260731_DMOVIMENTO_3.OPC',
    'Term Movement (DMOVIMENTO C21)': '73760_260731_DMOVIMENTO.CETIP21',
    'SWAP Movement (DMOVIMENTO-SWAP)': '73760_260731_DMOVIMENTO-SWAP.CETIP21',
    'SWAP Flow (DFLUXO_SWAP)': '73760_260731_DFLUXO.CETIP21',
    'SWAP Premium Agenda (DAGENDAPREMIOS)': '73760_260731_DAGENDAPREMIOS.CETIP21',
    'SWAP Indexers (INDEXADORESSWAP_VCP)': 'CETIP21_260731_INDEXADORESSWAP_VCP.TXT',
    'Operations (DOPERACOES)': '73760_260731_DOPERACOES.CETIP21',
    'COE (DRESUMOEMISSOR-COE)': 'CETIP21_260731_SP_DRESUMOEMISSOR-COE.TXT',
    'Accelerator Agent (MID DAGENTEACELERADOR)': '73760_260731_MID_DAGENTEACELERADOR.CETIP21',
    'Term Position (DPOSICAO-TER)': '73760_260731_DPOSICAO-TER.TER',
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
      by_label['Term Position (DPOSICAO-TER)'].get('attach_sales_support'), True)
check('Operations mantem os 2 filtros',
      len(by_label['Operations (DOPERACOES)']['json']['filters']), 2)
check('OPC mantem extra_dest',
      bool(by_label['Option Position (OPC DPOSICAO)'].get('extra_dest')), True)
check('TER mantem extra_dest',
      bool(by_label['Term Position (DPOSICAO-TER)'].get('extra_dest')), True)
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
rules2 = R._cetip_rules()
check('so a linha valida entra', [r['label'] for r in rules2],
      ['SWAP Position (DPOSICAO-SWAP)'])

import shutil                                            # noqa: E402
shutil.rmtree(tmp, ignore_errors=True)
print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails[:12])))
sys.exit(1 if fails else 0)
