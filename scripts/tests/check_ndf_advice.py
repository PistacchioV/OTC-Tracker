"""Other Products > NDF > Settlement Advice: o aviso do Termo de Mercadoria.

Uma linha nasce de QUATRO fontes que nao se conhecem:

  Operations B3 --Titulo--> B3 ID e o universo (Resgate + TER + Type COMMODITIES)
        |-- = Contrato --> Posicao NDF --> Nº da Confirmacao, datas, quantidade,
        |                                  codigo do subjacente
        |                                       |-- Subjacente.json --> COMMODITY(COD)
        |-- sufixo do Nº da Confirmacao --> OTM Settlements --> Resultado Apurado
        |-- nome da contraparte --> RefData/CPD --> Settlement Net

O que este teste prende (tudo falha SEM erro no console):

  1. o UNIVERSO. Tres peneiras — Tipo Operacao = Resgate, Tipo Titulo = TER e a
     coluna derivada Type = COMMODITIES. Errar qualquer uma traz para o aviso do
     cliente operacao que nao e dele (uma opcao, um termo de cambio).

  2. o join do OTM pelo SUFIXO. O Trade Id do OTM e o Nº da Confirmacao carregam
     o mesmo identificador DEPOIS do hifen e prefixos diferentes antes. Comparar
     a string inteira nao casa nada, e a coluna de valor sai vazia.

  3. o IR. 0,005% so quando o BANCO paga (apurado < 0); LAWTON isenta; e o IR
     ENCOLHE o liquido, nunca aumenta.

  4. a Cotacao Mercadoria da ASIATICA. Sem data unica de fixing, o valor e o
     mes/ano da 1a data de verificacao, escrito "Media Fev/2027" — nao a data.

Nao encosta em dado real: as fontes vao para um tempfile e as raizes do modulo
voltam no finally.
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                        # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(path):
    return io.open(path, encoding='utf-8').read()


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False)


# O cadastro de Subjacente e o de contraparte sao stubs: o teste nao depende do
# cadastro real nem o suja.
# Stub da FUNCAO, nao do cache: `_subjacente_map` revalida o mtime do arquivo
# real e recarregaria por cima de um cache preenchido na mao.
R._subjacente_map = lambda: {'OAHDY': 'ALUMINIO', 'CAFX': 'CAFE'}
R._ndfsum_refdata_spn = lambda: {R._fcst_norm('AMG BRASIL S.A.'): {'spn': '9', 'taxid': '1'}}
R._cpd_load = lambda: [{'SPN': '9', 'COUNTERPARTY': 'AMG BRASIL S.A.',
                        'NET': {'value': 'Pay/Rec', 'status': 'Active'}}]

REF = datetime(2026, 8, 5)


def opb3(titulo, tipo_op='RESGATE', tipo_tit='TER', cpty='CLI'):
    return {'Conta': '73760.00-9', 'Tipo Operação': tipo_op, 'Título': titulo,
            'Tipo Título': tipo_tit, 'Valor': '1,00', 'Data Liquidação': '05/08/2026',
            'Contraparte (Nome Simpl.)': cpty}


def ter(contrato, classe, cpty, conf, emissao, subj, fix_moeda, fix_ativo, qtd, asian=''):
    """Registro da posicao NDF no formato que `_lpndf_collect` le.

    As datas de media asiatica sao um bloco POSICIONAL: a 1a e a chave de indice
    100 do registro. Por isso o preenchimento ate 100 — sem ele a coluna
    "Media Asiatica (data) 1" nem existe, e o caminho da asiatica nao e exercido.
    """
    rec = {c: '' for c in R._LPNDF_COLUMNS}
    rec.update({'Contrato': contrato, 'Classe do Ativo Subjacente': classe,
                'Nome da Contraparte': cpty, 'Codigo Identificador': conf,
                'Data de Emissao': emissao, 'Codigo do Ativo Subjacente': subj,
                'Data de Fixing da Moeda': fix_moeda,
                'Data de Fixing do Ativo Subjacente': fix_ativo,
                'Valor Base no registro': qtd, 'Nome da Parte': 'BANCO J.P. MORGAN S.A.'})
    while len(rec) < 100:
        rec['_pad%03d' % len(rec)] = ''
    rec['_asian1'] = asian
    return rec


tmp = tempfile.mkdtemp(prefix='ndfadv-')
ds, b3 = os.path.join(tmp, 'ds'), os.path.join(tmp, 'b3')
day = os.path.join(ds, '2026', '08', '05')

write_json(os.path.join(day, 'operations-b3_20260805.json'), [
    opb3('C1'),                                   # entra — banco pagando
    opb3('C2'),                                   # entra — LAWTON, tambem pagando
    opb3('C3'),                                   # entra — banco recebendo
    opb3('X3', tipo_op='PAGAMENTO DE PREMIO'),    # nao e Resgate
    opb3('X4', tipo_tit='OPC'),                   # nao e TER
    opb3('F5'),                                   # TER Resgate, mas Type = cambio
])
# O OTM traz PREFIXO diferente e o trade partido em duas linhas de fluxo.
write_json(os.path.join(day, 'otm-settlement_20260805.json'), [
    {'Trade Id': 'OTM-1NR000', 'Amount': '-2000000.00', 'Currency': 'BRL'},
    {'Trade Id': 'OTM-1NR000', 'Amount': '-28144.04', 'Currency': 'BRL'},
    {'Trade Id': 'OTM-1NR00R', 'Amount': '-500000.00', 'Currency': 'BRL'},
    {'Trade Id': 'OTM-1NR00S', 'Amount': '2036775.45', 'Currency': 'BRL'},
    {'Trade Id': 'OTM-OUTRO', 'Amount': '9999.00', 'Currency': 'BRL'},
])
POS = R._prev_anbima_bizday(REF).strftime('%y%m%d')
write_json(os.path.join(b3, 'NDF', R._b3_date_subpath(POS),
                        '73760_{}_DPOSICAO-TER.json'.format(POS)), [
    ter('C1', 'COMMODITIES', 'AMG BRASIL S.A.', 'DBH-1NR000', '20250603',
        'OAHDY', '20260803', '20260804', '702'),
    # Asiatica: SEM data unica de fixing do ativo -> mes/ano da 1a verificacao
    ter('C2', 'COMMODITIES', 'LAWTON MULTIMERCADO EXCLUSIVO FUNDO DE INVESTIMENTO '
        'CREDITO PRIVADO', 'DBH-1NR00R', '20250603', 'CAFX', '20260803', '', '702',
        asian='20270215'),
    ter('C3', 'COMMODITIES', 'AMG BRASIL S.A.', 'DBH-1NR00S', '20250603',
        'OAHDY', '20260803', '20260804', '702'),
    ter('F5', 'TAXAS DE CAMBIO', 'OUTRO CLIENTE', 'DBH-FX', '20250603',
        'USD', '20260803', '20260804', '1'),
])

_ds_root, _b3_root = R.OTM_JSON_ROOT, R.B3_JSON_ROOT
try:
    R.OTM_JSON_ROOT, R.B3_JSON_ROOT = ds, b3
    items = R._ndfadv_collect(REF)
finally:
    R.OTM_JSON_ROOT, R.B3_JSON_ROOT = _ds_root, _b3_root
    shutil.rmtree(tmp, ignore_errors=True)

COL = {c: i for i, c in enumerate(R._NDFADV_COLUMNS)}
by_b3 = {r['cells'][COL['B3 ID']]: r for r in items}


def cell(b3id, col):
    return by_b3[b3id]['cells'][COL[col]]


# ─────────────────────────────────────────────────────────────────────────────
print('\n== 1. o universo: Resgate + TER + Type COMMODITIES ==')
check('so os termos de mercadoria entram', sorted(by_b3), ['C1', 'C2', 'C3'])
check('premio nao e resgate', 'X3' in by_b3, False)
check('opcao nao e TER', 'X4' in by_b3, False)
check('termo de CAMBIO nao entra', 'F5' in by_b3, False)

print('\n== 2. a linha, coluna a coluna ==')
check('Contraparte vem da posicao NDF', cell('C1', 'Contraparte'), 'AMG BRASIL S.A.')
check('B3 ID e o Titulo do Operations B3', cell('C1', 'B3 ID'), 'C1')
check('Nº da Confirmacao e o Codigo Identificador', cell('C1', 'Nº da Confirmação'), 'DBH-1NR000')
check('Data de Inicio', cell('C1', 'Data de Início da Operação'), '03/06/2025')
# COMMODITY(CODIGO), como na planilha do usuario.
check('Ativo Subjacente resolve a commodity', cell('C1', 'Ativo Subjacente'), 'ALUMINIO(OAHDY)')
check('Ptax = data de fixing da MOEDA', cell('C1', 'Ptax'), '03/08/2026')
check('Quantidade', cell('C1', 'Quantidade da Operação'), '702.00')
check('Settlement Net vem do cadastro', cell('C1', 'Settlement Net'), 'Pay/Rec')
# Sem cadastro, o default seguro (o mesmo da recon) em vez de "sem netting".
check('sem cadastro cai em Total Net', cell('C2', 'Settlement Net'), 'Total Net')

print('\n== 3. Cotacao Mercadoria: data unica x media asiatica ==')
check('com fixing do ativo, a data', cell('C1', 'Cotação Mercadoria'), '04/08/2026')
# Sem data unica, o mes/ano da 1a verificacao — e por extenso, nao a data.
check('sem fixing, a media do mes', cell('C2', 'Cotação Mercadoria'), 'Média Fev/2027')

print('\n== 4. o OTM entra pelo SUFIXO, somado ==')
# Trade Id 'OTM-1NR000' x Nº da Confirmacao 'DBH-1NR000': prefixos diferentes, o
# identificador e o que vem depois do hifen. E as duas linhas de fluxo somam.
check('as duas linhas do mesmo trade somam', cell('C1', 'Resultado Apurado (R$)'), '-2,028,144.04')
check('o outro trade nao vaza', cell('C3', 'Resultado Apurado (R$)'), '2,036,775.45')

print('\n== 5. o IR de 0,005% ==')
# Banco pagando (apurado < 0) -> 0,005% sobre o modulo, arredondado a 2 casas.
check('banco pagando paga IR', cell('C1', 'IR 0,005% (R$)'), '101.41')
# E o IR ENCOLHE o que se movimenta: -2.028.144,04 + 101,41.
check('o liquido encolhe', cell('C1', 'Resultado Líquido (R$)'), '-2,028,042.63')
# Apurado positivo = o banco recebe -> nao ha retencao.
check('banco recebendo nao paga IR', cell('C3', 'IR 0,005% (R$)'), '0.00')
check('e o liquido fica cheio', cell('C3', 'Resultado Líquido (R$)'), '2,036,775.45')
# LAWTON e isenta MESMO com o banco pagando — e a primeira condicao da formula.
check('LAWTON isenta mesmo pagando', cell('C2', 'IR 0,005% (R$)'), '0.00')
check('e por isso o liquido dela e o cheio',
      cell('C2', 'Resultado Líquido (R$)'), '-500,000.00')

print('\n== 6. a pagina esta LIGADA ==')
SRC = read('apps/pages/routes.py')
check('rota da pagina',
      "@blueprint.route('/other-products-ndf-settlement-advice')" in SRC, True)
check('endpoint de dados',
      "@blueprint.route('/api/other-products-ndf-settlement-advice/data')" in SRC, True)
NAV = read('apps/templates/partials/sidenav.html')
check('o sidenav aponta para a pagina',
      'href="/other-products-ndf-settlement-advice"' in NAV, True)
HTML = read('apps/templates/pages/other-products-ndf-settlement-advice.html')
check('usa o visualizador generico', 'live-position-swap-characteristics.js' in HTML, True)
check('o data-api aponta para o endpoint',
      'data-api="/api/other-products-ndf-settlement-advice/data"' in HTML, True)
for hook in ('id="swapchar-page"', 'id="swapchar-table"'):
    check('o contrato com o JS: %s' % hook, hook in HTML, True)
check('uma largura por coluna',
      len(re.findall(r'#swapchar-table th:nth-child\((\d+)\)', HTML)),
      len(R._NDFADV_COLUMNS) + 2)
# O Print Advice ainda nao existe para NDF Commodities — botao que 404 e pior
# que botao ausente.
check('sem botao de aviso ainda', 'swPrintAdvice' in HTML, False)

OTM = read('apps/templates/pages/otm-settlements.html')
check('a toolbar do OTM ganhou respiro',
      '#otm-page .card-body > .d-flex.justify-content-between' in OTM, True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
