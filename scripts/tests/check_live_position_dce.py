# -*- coding: utf-8 -*-
"""Live Position › DCE e o DPOSICAOCONTRATODCE no Save CETIP Files (§729).

  1. o cadastro CETIP Files tem a regra; ela casa o nome antigo
     (`CETIP21_AAMMDD_DPOSICAOCONTRATODCE`) e o do envelope da Return
     (`73760_CETIP21_AAMMDD_SP_DPOSICAOCONTRATODCE…`); salva como
     `73760_AAMMDD_DPOSICAOCONTRATODCE.CETIP21`, e o JSON tem o MESMO nome que a
     tela pede, na categoria DCE;
  2. a exportação (`has_header: 'auto'`) dá o mesmo JSON com e sem cabeçalho;
  3. os códigos viram texto pelos CADASTROS (o `dce-position-codes` novo e os
     `dce-*`), o ativo pela categoria, números com as casas do layout, datas
     dd/mm/aaaa; código sem cadastro fica como veio;
  4. a API e a página, com o arquivo-dia de um dublê.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_live_position_dce.py
"""
import io
import os
import sys
import tempfile
from datetime import date

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

import run                                                 # noqa: E402
from apps.pages import routes as R                         # noqa: E402
from apps.pages.features.cetip import domain as CD         # noqa: E402
from apps.pages.features.live_positions import domain as LD, queries as LQ   # noqa: E402

app = run.app
fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


DREF = '261029'
TIPO = 'DCE Contract Position (DPOSICAOCONTRATODCE)'

print('== 1. a regra do Save CETIP Files ==')
with app.app_context():
    from apps.pages.features.cetip import queries as CQ
    regra = {r['label']: r for r in CQ._cetip_rules()}.get(TIPO)
check('a regra existe no cadastro (seed + upgrade)', bool(regra), True)
if regra:
    check('casa o nome antigo', bool(regra['match']('cetip21_%s_dposicaocontratodce.txt' % DREF)), True)
    check('casa o envelope da Return',
          bool(regra['match']('73760_cetip21_%s_sp_dposicaocontratodce.txt.zip.s1' % DREF)), True)
    check('não casa o DPOSICAO-SWAP', bool(regra['match']('cetip21_%s_dposicao-swap.txt' % DREF)), False)
    dest = regra['dest_name'](DREF)
    check('salva como 73760_AAMMDD_DPOSICAOCONTRATODCE.CETIP21', dest, '73760_%s_DPOSICAOCONTRATODCE.CETIP21' % DREF)
    check('   e o JSON tem o nome que a tela pede',
          os.path.splitext(dest)[0] + '.json', LQ.DCE_FILE.format(DREF))
    check('   na categoria DCE, cabeçalho auto', ((regra.get('json') or {}).get('category'),
                                                  (regra.get('json') or {}).get('has_header')), ('DCE', 'auto'))
check('o seed e o upgrade têm a linha',
      any(r['TYPE'] == TIPO for r in R._cetip_files_upgrade([dict(x) for x in R._CETIP_FILES_SEED if x['TYPE'] != TIPO])), True)
check('o comportamento casa pelo nome entre parênteses', bool(CD._cetip_behaviour_for(TIPO).get('json')), True)

print('\n== 2. com e sem cabeçalho dão o mesmo JSON ==')
LABS = list(R._B3_SWAP_HEADERS['dce_contract_position'])
check('o layout tem os 57 campos do manual', len(LABS), 57)
linha = ['20261029', '20261030', 'DCE0261234567', '01', '02', 'MN0000001', '3', '20271030',
         '73760.00-9', '73760.10-2', '000123', '12.345.678/0001-90', 'CLIENTE TESTE SA',
         '0000000010000000000000', '00000000010000', '0000000100', '1', '220', '1', 'USD', 'USD',
         '02', '01', '02', 'BRXXXX', '', 'CME', '1', '13', 'N.A.', '01', '000456',
         '98.765.432/0001-10', 'BANK XYZ', '1', '02', '', '', '', '', '', '11', '01',
         '0000000005250000', '02', '02', '', '', '', '', '', '', '', '', '', '', '']
check('a linha sintética tem 57 campos', len(linha), 57)
tmp = tempfile.mkdtemp(prefix='dce-')
saidas = {}
gravado = {}
_aw0 = R._atomic_write_json
R._atomic_write_json = lambda p, rows: gravado.__setitem__(p, rows)
try:
    for nome, cab in (('sem', False), ('com', True)):
        src = os.path.join(tmp, nome + '.txt')
        with io.open(src, 'w', encoding='latin-1', newline='') as fh:
            if cab:
                fh.write(';'.join('Campo %d' % (i + 1) for i in range(57)) + '\r\n')
            fh.write(';'.join(linha) + '\r\n')
        gravado.clear()
        R._b3_export_json(src, {'category': 'DCE', 'has_header': 'auto',
                                'header_key': 'dce_contract_position'},
                          '73760_%s_DPOSICAOCONTRATODCE.CETIP21' % DREF, DREF)
        rows = list(gravado.values())[0] if gravado else []
        saidas[nome] = [list(r.values()) for r in rows]
finally:
    R._atomic_write_json = _aw0
check('sem cabeçalho: uma linha de dado', len(saidas.get('sem', [])), 1)
check('com cabeçalho: o cabeçalho não vira dado', saidas.get('com'), saidas.get('sem'))

print('\n== 3. códigos → texto pelos cadastros ==')
dce = {k: LD.code_table(R._mapping_rows(k), 'REFERENCE CODE', 'DOMAIN') for k in LD.DCE_TABLES}
codes = LD.position_codes(R._mapping_rows('dce-position-codes'))
assets = LD.asset_table(R._mapping_rows('dce-underlying-asset'))
row = dict(zip(LABS, LD.display_row(LABS, linha, dce, codes, assets)))
check('Tipo de DCE 01', row['Tipo de DCE'], 'RESOLUCAO 3.824')
check('Tipo de Mercado 02', row['Tipo de Mercado'], 'BALCAO')
check('Tipo de Derivativo 3 (dce-type-of-derivative)', row['Tipo de Derivativo'], 'Opções')
check('Entrega Física 02 / Garantias 01', (row['Entrega Física'], row['Garantias']), ('NAO', 'SIM'))
check('Posição da Parte - Opção 11', row['Posição da Parte - Opção'], 'TITULAR')
check('Tipo de Opção 01', row['Tipo de Opção'], 'COMPRA')
check('Tipo de Verificação 02 (dce-type-of-verification)', row['Tipo de Verificação'], 'EUROPEIA')
check('Mês de Referência 13', row['Mês de Referência'], 'N.A.')
check('Categoria 1 e o ativo 220 DENTRO dela (o código repete entre categorias)',
      (row['Categoria do Ativo Subjacente'], row['Ativo Subjacente da Parte']),
      (dce['dce-underlying-asset-category'].get('1'), assets.get((LD.norm(dce['dce-underlying-asset-category'].get('1')), '220'))))
check('   e é texto, não o código', row['Ativo Subjacente da Parte'] not in ('', '220'), True)
check('Moeda sem cadastro fica como veio', row['Moeda Cotada'], 'USD')
check('datas dd/mm/aaaa', (row['Data de Registro'], row['Data de Vencimento']), ('29/10/2026', '30/10/2027'))
check('Valor Base 9(14,05) sem separador', row['Valor Base do Contrato'], '100,000,000.00')
check('Strike 9(10,06) com as casas que tem', row['Strike'], '5.25')
check('Quantidade 9(10,04)', row['Quantidade'], '1')
check('número com vírgula vale como veio', LD.fmt_num('1.234,5', 4), '1,234.5')
check('código com zero à esquerda casa', LD.code_key('07'), LD.code_key('7'))

print('\n== 4. a API e a página ==')
_p0, _r0 = R._swap_day_path, R._db_day_records
R._swap_day_path = lambda ref, tpl, max_back=10, exact=False, category='Swap': (
    ('/x/' + tpl.format('261029'), '261029') if category == 'DCE' else (None, None))
R._db_day_records = lambda p: [dict(zip(LABS, linha))]
try:
    c = app.test_client()
    with c.session_transaction() as s:
        s.update({'authenticated': True, 'user_sid': 'A111111', 'user_name': 'T', 'user_role': 'ADMIN',
                  'session_ip': '127.0.0.1'})
    d = c.get('/api/live-position-dce/data?date=2026-10-29').get_json()
    check('API responde com as 57 colunas', (d.get('success'), len(d.get('columns') or [])), (True, 57))
    check('   uma linha, traduzida', (len(d.get('rows') or []), (d.get('rows') or [[]])[0][3]), (1, 'RESOLUCAO 3.824'))
    check('   e diz o dia lido', d.get('source_date'), '2026-10-29')
    html = c.get('/live-position-dce').get_data(as_text=True)
    check('a página abre com a API dela', 'data-api="/api/live-position-dce/data"' in html, True)
    check('   e está no menu', 'href="/live-position-dce"' in html, True)
finally:
    R._swap_day_path, R._db_day_records = _p0, _r0

print(('\nFALHAS (%d): %s' % (len(fails), fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
