"""Swap VCP: o fallback do arquivo de EVENTOS para a POSICAO e por CAMPO.

A tela do VCP nao tem fonte propria. A base sao os avisos de inexistencia de PU
do Operations B3 (Titulo -> Codigo do Contrato, Conta -> PARTE / Conta) e as
QUATRO colunas da direita — PARTE / Indexador, CONTRAPARTE / Conta,
CONTRAPARTE / CPF/CNPJ e CONTRAPARTE / Indexador — saem do arquivo de eventos,
com a POSICAO de swap como segunda fonte (§431). Depois disso o nome da
contraparte e resolvido no RefData pela conta ou pelo CPF/CNPJ.

O que este guarda prende e a ARMADILHA do fallback: ele era

    ev = events.get(cc) or posicao.get(cc, {})

e `events.get(cc)` devolve um dict com as quatro chaves ainda que TODAS venham
vazias. Dict de valores vazios e VERDADEIRO, entao o `or` nunca chegava a
posicao: contrato PRESENTE no arquivo de eventos com as pernas em branco saia
com as quatro celulas vazias — a mesma tela de quem nao esta no arquivo, e sem
nada distinguindo as duas. O mesmo vale linha a linha dentro do arquivo de
eventos: ele tem uma linha por EVENTO, o mesmo contrato aparece em varias, e
guardar so a PRIMEIRA calava as demais quando ela vinha sem as pernas.

Nao encosta em dado real: os tres arquivos-dia sao sinteticos, escritos num
tempfile, e o RefData e trocado por um stub.
"""
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


REF = datetime(2026, 9, 8)
TMP = tempfile.mkdtemp(prefix='vcp-join-')

# ── o arquivo de EVENTOS, escrito com os nomes reais das colunas ────────────
#  Repare que a conta da contraparte mora em "CONTRAPARTE / Contraparte" — nao
#  em "CONTRAPARTE / Conta", que e o nome da COLUNA DA TELA.
def _evento(contrato, conta='', cnpj='', pix='', cix=''):
    return {'Código do Contrato': contrato, 'PARTE / Indexador': pix,
            'CONTRAPARTE / Contraparte': conta, 'CONTRAPARTE / CPF/CNPJ': cnpj,
            'CONTRAPARTE / Indexador': cix}


EVENTOS = [
    # 1. completo — o evento responde tudo
    _evento('21C00035804', '73760.10-2', '16.404.287/0001-55', 'VCP', 'VCP'),
    # 2. presente, mas com as pernas em BRANCO: era aqui que o `or` matava o
    #    fallback e as quatro celulas saiam vazias.
    _evento('24H02170822'),
    # 3. presente e PARCIAL: a conta veio, os indexadores nao. O fallback tem
    #    de completar so o que falta, sem trocar o que o evento respondeu.
    _evento('21D00032629', '73760.55-5'),
    # 3b. a MESMA operacao numa segunda linha de evento, agora com o resto.
    #     Guardando so a primeira, ela ficaria de fora.
    _evento('21D00032629', '', '11.111.111/0001-11', 'DI', 'PRE'),
]

# ── a POSICAO (DPOSICAO-SWAP): headerless, lida por INDICE ──────────────────
_H = R._B3_SWAP_HEADERS['swap_position']


def _posicao(contrato, conta, cnpj, cod_ix1, cod_ix2, classe=''):
    """Uma linha da posicao com os 170 campos do layout, so os que o VCP le."""
    vals = [''] * len(_H)
    vals[R._VCP_POS_IDX['contrato']] = contrato
    vals[R._VCP_POS_IDX['cpty_conta']] = conta
    vals[R._VCP_POS_IDX['cpty_cnpj']] = cnpj
    vals[R._VCP_POS_IDX['parte_ix']] = cod_ix1
    vals[R._VCP_POS_IDX['cpty_ix']] = cod_ix2
    vals[R._VCP_POS_IDX['classe']] = classe
    from apps.pages.json_to_duckdb import nomes_unicos
    return dict(zip(nomes_unicos(list(_H), chave=lambda s: s), vals))


POSICAO = [
    _posicao('24H02170822', '73760.22-2', '22.222.222/0001-22', 'C03', 'C99'),
    _posicao('21D00032629', '73760.99-9', '99.999.999/0001-99', 'C03', 'C03'),
    # 4. so na posicao, sem evento nenhum
    _posicao('24H02170664', '73760.33-3', '33.333.333/0001-33', 'C03', 'C99'),
]

OPS = [
    {'Tipo Operação': 'AVISO DE INEXISTENCIA DE PU', 'Título': c, 'Conta': '73760.00-9'}
    for c in ('21C00035804', '24H02170822', '21D00032629', '24H02170664', '99Z00000001')
] + [{'Tipo Operação': 'REGISTRO', 'Título': '21C00035804', 'Conta': '73760.00-9'}]


def _escrever():
    ev_dir = os.path.join(TMP, 'ds', '2026', '09', '08')
    pos_dir = os.path.join(TMP, 'b3', 'Swap', '2026', '09', '08')
    os.makedirs(ev_dir, exist_ok=True)
    os.makedirs(pos_dir, exist_ok=True)
    with io.open(os.path.join(ev_dir, 'eventos-swap-jpm_20260908.json'), 'w',
                 encoding='utf-8') as fh:
        json.dump(EVENTOS, fh)
    with io.open(os.path.join(pos_dir, '73760_260908_DPOSICAO-SWAP.json'), 'w',
                 encoding='utf-8') as fh:
        json.dump(POSICAO, fh)


_escrever()

# ── stubs: os tres caminhos e o RefData ─────────────────────────────────────
R.OTM_JSON_ROOT = os.path.join(TMP, 'ds')
R.B3_JSON_ROOT = os.path.join(TMP, 'b3')
R._opb3_load = lambda ref: ('', [dict(o) for o in OPS])
R._vcp_refdata_maps = lambda: ({'7376022 2'.replace(' ', ''): 'CLIENTE DA CONTA'},
                               {'16404287000155': 'SUZANO SA',
                                '11111111000111': 'CLIENTE DO CNPJ'})

paginas = {r[1]: r for r in R._vcp_collect(REF)['rows']}

# ── 1. so os avisos entram, e cada contrato uma vez ─────────────────────────
check('so os AVISO DE INEXISTENCIA DE PU viram linha', len(paginas), 5)

# ── 2. evento completo: a posicao nao opina ─────────────────────────────────
l = paginas['21C00035804']
check('evento completo mantem a conta do evento', l[5], '73760.10-2')
check('evento completo mantem o CNPJ do evento', l[6], '16.404.287/0001-55')
check('evento completo resolve o nome pelo CNPJ (conta omnibus)', l[0], 'SUZANO SA')

# ── 3. O DEFEITO: evento presente com as pernas VAZIAS ──────────────────────
l = paginas['24H02170822']
check('evento vazio cai na POSICAO (conta)', l[5], '73760.22-2')
check('evento vazio cai na POSICAO (CPF/CNPJ)', l[6], '22.222.222/0001-22')
check('evento vazio cai na POSICAO (PARTE / Indexador)', bool(l[3]), True)
check('evento vazio cai na POSICAO (CONTRAPARTE / Indexador)', bool(l[7]), True)
check('evento vazio: o nome sai da conta da posicao', l[0], 'CLIENTE DA CONTA')

# ── 4. evento PARCIAL: o evento vence celula a celula ───────────────────────
l = paginas['21D00032629']
check('parcial: a conta do EVENTO vence a da posicao', l[5], '73760.55-5')
check('parcial: o CNPJ vem da 2a linha de evento, nao da posicao',
      l[6], '11.111.111/0001-11')
check('parcial: o indexador da 2a linha de evento vence', l[3], 'DI')

# ── 5. sem evento nenhum: a posicao responde inteira ────────────────────────
l = paginas['24H02170664']
check('sem evento: conta da posicao', l[5], '73760.33-3')
check('sem evento: CPF/CNPJ da posicao', l[6], '33.333.333/0001-33')

# ── 6. em nenhuma das duas: quatro celulas vazias, sem estourar ─────────────
l = paginas['99Z00000001']
check('sem fonte nenhuma: as quatro celulas vazias',
      [l[3], l[5], l[6], l[7]], ['', '', '', ''])
check('sem fonte nenhuma: o Codigo do Contrato continua na tela', l[1], '99Z00000001')

# ── 7. o mapa de eventos nao devolve mais dict de valores vazios ────────────
mapa = R._vcp_events_map(REF)
check('o contrato sem pernas continua no mapa (mas vazio)',
      mapa.get(R._acc_digits('24H02170822')),
      {'parte_ix': '', 'cpty_conta': '', 'cpty_cnpj': '', 'cpty_ix': ''})
check('as duas linhas do mesmo contrato se somam',
      mapa[R._acc_digits('21D00032629')]['cpty_cnpj'], '11.111.111/0001-11')

shutil.rmtree(TMP, ignore_errors=True)

if fails:
    print('FAILED: %d check(s)' % len(fails))
    sys.exit(1)
print('all ok')
