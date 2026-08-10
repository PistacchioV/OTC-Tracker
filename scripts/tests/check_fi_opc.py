"""File Interface OPC (Opcoes Flexiveis VCP): o cadastro comanda, byte a byte.

Os dois geradores do arquivo OPC — api_fxo_send_conecta (FXO_Banco.txt) e
api_send_conecta do opt-commodities (OPC_Banco.txt) — deixaram de carregar os
literais e a ordem dos campos no codigo: a montagem virou
_fi_build_line('opcoes-flexiveis-vcp', ...), e o template JSON e a autoridade.
A troca NAO PODE mudar um byte do que vai para a B3.

As funcoes _legacy_* abaixo sao a copia autocontida da montagem ANTIGA
(capturada antes da refatoracao, com os literais que moravam no codigo:
'OPC  00002', Tipo Indicador '3'/'4', Tipo de Exercicio '2', o Tipo de
Cotacao '1' do FXO — o docstring antigo dizia '2', mas producao sempre
escreveu '1' — e o f=['']*63 cujo 63o elemento vazio produz o token vazio
final). Sao elas que geram os goldens: linha nova == golden, ramo a ramo.

Nao encosta em dado real: so as funcoes de montagem de linha, nada de
CONECTA_NEW_PATH; o teste de "editou Fixed -> linha muda" usa um template
copiado para tempfile, com _FILE_INTERFACE_DIR monkeypatchado.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                            # noqa: E402

KEY = 'opcoes-flexiveis-vcp'
FXO_PAGE = '/new_deals-opt-fxo'
COMM_PAGE = '/new_deals-opt-commodities'

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# ─────────────────────────────────────────────────────────────────────────────
#  LEGADO — copia fiel da montagem pre-refatoracao (routes.py, antes de o
#  cadastro comandar). Recebe os VALORES ja computados (as funcoes _cli/_num/
#  _date etc. nao mudaram de lugar nem de forma; o que a refatoracao trocou
#  foi a MONTAGEM) e coloca cada um no indice f[] em que o codigo antigo o
#  escrevia, com os literais que o codigo antigo carregava.
# ─────────────────────────────────────────────────────────────────────────────

def _legacy_header(today):
    return 'OPC  00002;0;JPMORGANBM;{};00002;'.format(today)


def _legacy_fxo_registro(v):
    f = [''] * 63
    f[0]  = 'OPC  00002'
    f[1]  = '1'
    f[2]  = '4'                                   # FXO: Tipo Indicador
    f[3]  = v['cli']
    f[4]  = v['dir_code']
    f[6]  = v['cpty']
    f[7]  = v['taxid']
    f[8]  = v['opt']
    f[9]  = v['trade_date']
    f[10] = v['settle_date']
    f[11] = v['underlying']
    f[12] = v['qty']
    f[13] = v['strike']
    f[14] = '1'
    f[16] = '2'
    f[17] = '1'                                   # FXO: Tipo de Cotacao ('1' em producao, nao o '2' do docstring)
    f[18] = 'S' if v['brl'] else ''
    f[19] = v['fix_end'] if v['vanilla'] else ''  # FXO: fixing do ativo = ultimo fixing (VANILLA)
    f[20] = ''                                    # FXO: fixing da moeda sempre em branco
    f[23] = v['meu_numero']
    f[24] = v['deal']
    f[26] = v['premium']
    f[28] = v['modalidade']
    f[32] = v['spot_date']
    if v['vanilla']:
        f[47] = ''
        f[48] = '0'
    else:
        f[47] = '1'
        f[48] = v['biz']
    return ';'.join(f)


def _legacy_comm_registro(v):
    f = [''] * 63
    f[0]  = 'OPC  00002'
    f[1]  = '1'
    f[2]  = '3'
    f[3]  = v['cli']
    f[4]  = v['dir_code']
    f[6]  = v['cpty']
    f[7]  = v['taxid']
    f[8]  = v['opt']
    f[9]  = v['trade_date']
    f[10] = v['settle_date']
    f[11] = v['underlying']
    f[12] = v['qty']
    f[13] = v['strike']
    f[14] = '1'
    f[16] = '2'
    f[17] = v['quote_type']                       # _b3_quote_cfg(...)['opt'] (§177)
    f[18] = 'S' if v['brl'] else ''
    f[19] = v['fix_start'] if v['vanilla'] else ''
    f[20] = v['fxconv'] if (not v['brl'] or v['vanilla']) else ''
    f[23] = v['meu_numero']
    f[24] = v['deal']
    f[26] = v['premium']
    f[28] = v['modalidade']
    f[32] = v['spot_date']
    if v['vanilla']:
        f[47] = ''
        f[48] = '0'
    else:
        f[47] = '1'
        f[48] = v['biz']
    return ';'.join(f)


def _legacy_fxo_fixing(d):
    return 'OPC  00002;2;{};;;'.format(d)


def _legacy_comm_fixing(d, fx):
    return 'OPC  00002;2;{};{};;'.format(d, fx)


# ─────────────────────────────────────────────────────────────────────────────
#  NOVO — o dicionario {seq do template: valor} que o endpoint refatorado
#  monta (so campos nao-Fixed; os literais saem do cadastro).
# ─────────────────────────────────────────────────────────────────────────────

def _vals_fxo(v):
    return {
        '4':  v['cli'],
        '5':  v['dir_code'],
        '7':  v['cpty'],
        '8':  v['taxid'],
        '9':  v['opt'],
        '10': v['trade_date'],
        '11': v['settle_date'],
        '12': v['underlying'],
        '13': v['qty'],
        '14': v['strike'],
        '19': 'S' if v['brl'] else '',
        '20': v['fix_end'] if v['vanilla'] else '',
        '24': v['meu_numero'],
        '25': v['deal'],
        '27': v['premium'],
        '29': v['modalidade'],
        '33': v['spot_date'],
        '48': '' if v['vanilla'] else '1',
        '49': '0' if v['vanilla'] else v['biz'],
    }


def _vals_comm(v):
    return {
        '4':  v['cli'],
        '5':  v['dir_code'],
        '7':  v['cpty'],
        '8':  v['taxid'],
        '9':  v['opt'],
        '10': v['trade_date'],
        '11': v['settle_date'],
        '12': v['underlying'],
        '13': v['qty'],
        '14': v['strike'],
        '18': v['quote_type'],
        '19': 'S' if v['brl'] else '',
        '20': v['fix_start'] if v['vanilla'] else '',
        '21': v['fxconv'] if (not v['brl'] or v['vanilla']) else '',
        '24': v['meu_numero'],
        '25': v['deal'],
        '27': v['premium'],
        '29': v['modalidade'],
        '33': v['spot_date'],
        '48': '' if v['vanilla'] else '1',
        '49': '0' if v['vanilla'] else v['biz'],
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Ramos sinteticos (valores como os helpers do endpoint os produzem)
# ─────────────────────────────────────────────────────────────────────────────

FXO_VANILLA = {                                   # cliente comum, USD, com premio
    'cli': '73760009', 'dir_code': '1', 'cpty': '73760102',
    'taxid': '12345678000199', 'opt': 'C', 'trade_date': '20260810',
    'settle_date': '20261110', 'underlying': 'USDBRL', 'qty': '1000000,00',
    'strike': '5,4321', 'brl': False, 'vanilla': True, 'asian': False,
    'fix_end': '20261108', 'meu_numero': '1234567890', 'deal': 'FXO-1001',
    'premium': '0,0123', 'modalidade': '1', 'spot_date': '20260812', 'biz': '0'}

FXO_ASIAN = {                                     # asiatica, strike em BRL
    'cli': '73760009', 'dir_code': '2', 'cpty': '73760102',
    'taxid': '98765432000155', 'opt': 'P', 'trade_date': '20260803',
    'settle_date': '20261005', 'underlying': 'USDBRL', 'qty': '250000,00',
    'strike': '5,25', 'brl': True, 'vanilla': False, 'asian': True,
    'fix_end': '20261001', 'meu_numero': '2345678901', 'deal': 'FXO-1002',
    'premium': '0,05', 'modalidade': '1', 'spot_date': '20260805', 'biz': '4'}

FXO_LAWTON = {                                    # perna interna: sem tax id, contas trocadas, modalidade 2
    'cli': '73760009', 'dir_code': '1', 'cpty': '00041007',
    'taxid': '', 'opt': 'C', 'trade_date': '20260810',
    'settle_date': '20261110', 'underlying': 'USDBRL', 'qty': '1000000,00',
    'strike': '5,4321', 'brl': False, 'vanilla': True, 'asian': False,
    'fix_end': '20261108', 'meu_numero': '3456789012', 'deal': 'FXO-1003',
    'premium': '0,0123', 'modalidade': '2', 'spot_date': '20260810', 'biz': '0'}

FXO_EMPTY = {                                     # campos vazios (datas ilegiveis, sem premio, TradeType em branco)
    'cli': '73760009', 'dir_code': '1', 'cpty': '73760102',
    'taxid': '', 'opt': '', 'trade_date': '', 'settle_date': '',
    'underlying': '', 'qty': '', 'strike': '', 'brl': False,
    'vanilla': False, 'asian': False, 'fix_end': '',
    'meu_numero': '4567890123', 'deal': '', 'premium': '',
    'modalidade': '1', 'spot_date': '', 'biz': ''}

COMM_VANILLA_QIC = {                              # commodity vanilla, cotada em cents (valores ja /100), nao-BRL
    'cli': '73760009', 'dir_code': '1', 'cpty': '73760102',
    'taxid': '11222333000144', 'opt': 'C', 'trade_date': '20260810',
    'settle_date': '20261210', 'underlying': 'C Z7', 'qty': '5000,00',
    'strike': '4,3575', 'brl': False, 'vanilla': True, 'asian': False,
    'quote_type': '5', 'fix_start': '20261205', 'fxconv': '20261208',
    'meu_numero': '5678901234', 'deal': 'OPC-2001', 'premium': '0,215',
    'modalidade': '1', 'spot_date': '20260812', 'biz': '0'}

COMM_ASIAN_BRL = {                                # commodity asiatica em BRL: f[20] (seq 21) em branco
    'cli': '73760009', 'dir_code': '2', 'cpty': '73760102',
    'taxid': '55666777000188', 'opt': 'P', 'trade_date': '20260803',
    'settle_date': '20261102', 'underlying': 'BRT_IPE', 'qty': '10000,00',
    'strike': '450,75', 'brl': True, 'vanilla': False, 'asian': True,
    'quote_type': '9', 'fix_start': '20261026', 'fxconv': '20261030',
    'meu_numero': '6789012345', 'deal': 'OPC-2002', 'premium': '12,5',
    'modalidade': '1', 'spot_date': '20260805', 'biz': '5'}

COMM_BANK = {                                     # Banco J.P Morgan: contas invertidas, modalidade 3 (trade != spot)
    'cli': '00041007', 'dir_code': '1', 'cpty': '73760009',
    'taxid': '', 'opt': 'C', 'trade_date': '20260810',
    'settle_date': '20261210', 'underlying': 'HOZ6', 'qty': '2000,00',
    'strike': '2,15', 'brl': False, 'vanilla': True, 'asian': False,
    'quote_type': '5', 'fix_start': '20261205', 'fxconv': '20261208',
    'meu_numero': '7890123456', 'deal': 'OPC-2003', 'premium': '',
    'modalidade': '3', 'spot_date': '20260812', 'biz': '0'}


print('\n== 1. FXO: linha nova == golden legado, ramo a ramo ==')
for label, v in (('vanilla cliente', FXO_VANILLA), ('asiatica BRL', FXO_ASIAN),
                 ('perna Lawton', FXO_LAWTON), ('campos vazios', FXO_EMPTY)):
    check('registro FXO · ' + label,
          R._fi_build_line(KEY, 'registro', _vals_fxo(v), page_url=FXO_PAGE),
          _legacy_fxo_registro(v))

print('\n== 2. Opt Commodities: linha nova == golden legado, ramo a ramo ==')
for label, v in (('vanilla cents', COMM_VANILLA_QIC), ('asiatica BRL', COMM_ASIAN_BRL),
                 ('perna Banco', COMM_BANK)):
    check('registro Comm · ' + label,
          R._fi_build_line(KEY, 'registro', _vals_comm(v), page_url=COMM_PAGE),
          _legacy_comm_registro(v))

print('\n== 3. header e linhas de fixing (tipo 2) ==')
check('header', R._fi_build_line(KEY, 'header', {'4': '20260810'}, page_url=FXO_PAGE),
      _legacy_header('20260810'))
check('fixing FXO (moeda em branco)',
      R._fi_build_line(KEY, 'registro-media-asiatica', {'3': '20261001'}, page_url=FXO_PAGE),
      _legacy_fxo_fixing('20261001'))
check('fixing Comm BRL (moeda = mesma data)',
      R._fi_build_line(KEY, 'registro-media-asiatica', {'3': '20261026', '4': '20261026'},
                       page_url=COMM_PAGE),
      _legacy_comm_fixing('20261026', '20261026'))
check('fixing Comm nao-BRL (moeda em branco)',
      R._fi_build_line(KEY, 'registro-media-asiatica', {'3': '20261026', '4': ''},
                       page_url=COMM_PAGE),
      _legacy_comm_fixing('20261026', ''))

print('\n== 4. forma da linha: 63 tokens (62 campos + vazio final) ==')
line = R._fi_build_line(KEY, 'registro', _vals_fxo(FXO_VANILLA), page_url=FXO_PAGE)
check('63 tokens na linha de dados', len(line.split(';')), 63)
check('token final vazio', line.endswith(';'), True)
check('header com 6 tokens', len(R._fi_build_line(KEY, 'header', {'4': '20260810'},
                                                  page_url=FXO_PAGE).split(';')), 6)

print('\n== 5. o cadastro comanda: editar um Fixed muda a linha ==')
tmp = tempfile.mkdtemp(prefix='fi-opc-')
_orig_dir = R._FILE_INTERFACE_DIR
try:
    shutil.copy(os.path.join(_orig_dir, KEY + '.json'), os.path.join(tmp, KEY + '.json'))
    with open(os.path.join(tmp, KEY + '.json'), encoding='utf-8') as fh:
        tpl = json.load(fh)
    for b in tpl['blocks']:
        if b['id'] == 'registro':
            for f in b['fields']:
                if f['seq'] == '17':              # Tipo de Exercicio: Fixed '2' -> '9'
                    f['source_detail'] = '9'
    with open(os.path.join(tmp, KEY + '.json'), 'w', encoding='utf-8') as fh:
        json.dump(tpl, fh, ensure_ascii=False, indent=2)
        fh.write('\n')
    R._FILE_INTERFACE_DIR = tmp
    R._fi_tpl_cache.clear()
    edited = R._fi_build_line(KEY, 'registro', _vals_fxo(FXO_VANILLA), page_url=FXO_PAGE)
    check('Fixed editado sai na linha', edited.split(';')[16], '9')
    check('resto da linha intacto',
          [t for i, t in enumerate(edited.split(';')) if i != 16],
          [t for i, t in enumerate(line.split(';')) if i != 16])
finally:
    R._FILE_INTERFACE_DIR = _orig_dir
    R._fi_tpl_cache.clear()
    shutil.rmtree(tmp, ignore_errors=True)

check('template original de volta',
      R._fi_build_line(KEY, 'registro', _vals_fxo(FXO_VANILLA), page_url=FXO_PAGE), line)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
