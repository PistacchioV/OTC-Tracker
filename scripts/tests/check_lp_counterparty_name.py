#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_lp_counterparty_name.py — a coluna de CPF/CNPJ da CONTRAPARTE nas tres
Live Position mostra o NOME, nao o numero.

Nas tres telas (NDF, Option e Swap Characteristics) a coluna de CPF/CNPJ da
contraparte passou a resolver o nome no RefData. Tres regras, e as tres erram em
silencio se cairem:

  1. **vazio continua vazio** — a celula em branco nao pode virar um nome de
     ninguem nem um CPF mascarado de nada;
  2. **documento SEM cadastro devolve o numero mascarado**, e nao branco: o
     numero e o unico dado que a linha tem sobre a contraparte, e apaga-lo
     esconderia justamente quem falta cadastrar;
  3. **os dois lados normalizam o zero a esquerda**. O RefData guarda mascarado
     (00.514.820/0001-00) e a posicao da B3 guarda so numeros, as vezes sem o
     zero da frente. Comparar sem normalizar casa silenciosamente NADA — e 158
     dos 553 cadastros do RefData comecam com zero, entao seria mais de um quarto
     da base saindo como numero.

E a coluna da PARTE — que e a nossa perna — continua o documento: troca-la pelo
nome faria a celula repetir o "Nome da Parte"/"Parte (Nome simplificado)" que ja
esta ao lado.

Escreve so em `tempfile` (as posicoes sinteticas); o RefData lido e o do repo, e
nao e alterado.
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
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, 'scripts', 'tests'))

from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# Um cadastro REAL do RefData do repo, e de proposito um com zero a esquerda.
RD = json.load(io.open(os.path.join(ROOT, 'apps', 'static', 'data', 'RefData.json'),
                       encoding='utf-8'))
alvo = next(r for r in RD
            if ''.join(c for c in str(r.get('TAX ID', '')) if c.isdigit()).startswith('0')
            and str(r.get('COUNTERPARTY', '')).strip())
TAX_MASK = str(alvo['TAX ID'])
TAX_DIG = ''.join(c for c in TAX_MASK if c.isdigit())
TAX_SEM_ZERO = TAX_DIG.lstrip('0')
NOME = str(alvo['COUNTERPARTY']).strip()

print('\n== 1. o xlookup ==')
print('  (cadastro de teste: %s -> %s)' % (TAX_MASK, NOME))
check('mascarado resolve', R._lp_cpty_by_taxid(TAX_MASK), NOME)
check('so digitos resolve', R._lp_cpty_by_taxid(TAX_DIG), NOME)
# O caso que o zero-fill existe para cobrir.
check('SEM o zero a esquerda resolve igual', R._lp_cpty_by_taxid(TAX_SEM_ZERO), NOME)
check('com espaco em volta resolve', R._lp_cpty_by_taxid('  ' + TAX_DIG + ' '), NOME)

print('\n== 2. vazio continua vazio ==')
for v in ('', None, '   '):
    check('%r -> vazio' % v, R._lp_cpty_by_taxid(v), '')

print('\n== 3. sem cadastro, o numero fica (mascarado) ==')
check('CNPJ desconhecido', R._lp_cpty_by_taxid('99999999000199'), '99.999.999/0001-99')
check('CPF desconhecido', R._lp_cpty_by_taxid('12345678901'), '123.456.789-01')
# Texto que nao e documento passa direto — a coluna as vezes traz '-' ou 'N/A'.
check('texto nao vira nada', R._lp_cpty_by_taxid('N/A'), 'N/A')

print('\n== 4. a chave normaliza os dois lados ==')
check('13 digitos viram CNPJ de 14', R._lp_taxid_key('1234567800019'), '01234567800019')
check('14 ficam como estao', R._lp_taxid_key('01234567800019'), '01234567800019')
check('10 viram CPF de 11', R._lp_taxid_key('1234567890'), '01234567890')
check('a mascara nao atrapalha', R._lp_taxid_key('00.514.820/0001-00'), '00514820000100')
check('sem digito nenhum devolve vazio', R._lp_taxid_key('N/A'), '')
# O indice do RefData e reindexado pela MESMA chave, senao o lado do cadastro
# fica com os digitos crus e o da posicao com o zero-fill.
check('o indice tem a chave normalizada',
      R._lp_taxid_names().get(R._lp_taxid_key(TAX_MASK)), NOME)

print('\n== 5. as tres telas, com posicao sintetica ==')
tmp = tempfile.mkdtemp(prefix='lp-cpty-')
root_orig = R.B3_JSON_ROOT
try:
    R.B3_JSON_ROOT = tmp
    ref = R._prev_anbima_bizday(datetime.now())
    dref = ref.strftime('%y%m%d')
    sub = R._b3_date_subpath(dref)

    def grava(produto, nome_arq, data):
        d = os.path.join(tmp, produto, sub)
        os.makedirs(d, exist_ok=True)
        with io.open(os.path.join(d, nome_arq), 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(data, ensure_ascii=False))

    def coluna(payload, rotulo):
        i = payload['columns'].index(rotulo)
        return [r[i] for r in payload['rows']]

    # ── NDF ──────────────────────────────────────────────────────────────
    grava('NDF', '73760_{}_DPOSICAO-TER.json'.format(dref), [
        {'CPF/CNPJ da Contraparte': TAX_SEM_ZERO, 'CPF/CNPJ do Participante': TAX_DIG},
        {'CPF/CNPJ da Contraparte': '', 'CPF/CNPJ do Participante': TAX_DIG},
        {'CPF/CNPJ da Contraparte': '99999999000199', 'CPF/CNPJ do Participante': TAX_DIG},
    ])
    ndf = R._lpndf_collect(ref)
    check('NDF: contraparte vira nome / vazio / numero',
          coluna(ndf, 'CPF/CNPJ da Contraparte'),
          [NOME, '', '99.999.999/0001-99'])
    # A coluna do Participante e a NOSSA perna e nao foi tocada: o 'Nome da
    # Parte' ja esta ao lado, e trocar as duas repetiria a informacao.
    check('NDF: o Participante continua o documento cru',
          coluna(ndf, 'CPF/CNPJ do Participante'), [TAX_DIG] * 3)

    # ── Option ───────────────────────────────────────────────────────────
    grava('Option', '73760_{}_DPOSICAO.json'.format(dref), [
        {'CPF/CNPJ Cliente Contraparte': TAX_SEM_ZERO, 'CPF/CNPJ Cliente Parte': TAX_DIG},
        {'CPF/CNPJ Cliente Contraparte': '', 'CPF/CNPJ Cliente Parte': TAX_DIG},
        {'CPF/CNPJ Cliente Contraparte': '99999999000199', 'CPF/CNPJ Cliente Parte': TAX_DIG},
    ])
    opt = R._lpopt_collect(ref)
    check('Option: contraparte vira nome / vazio / numero',
          coluna(opt, 'CPF/CNPJ Cliente Contraparte'),
          [NOME, '', '99.999.999/0001-99'])
    # A da Parte continua MASCARADA (era o comportamento de antes das duas).
    check('Option: a Parte continua o CPF/CNPJ mascarado',
          coluna(opt, 'CPF/CNPJ Cliente Parte'), [R._lp_fmt_cnpj(TAX_DIG)] * 3)

    # ── Swap Characteristics ─────────────────────────────────────────────
    # Arquivo SEM cabecalho: 146 campos lidos por POSICAO, e o CPF/CNPJ da
    # contraparte e o indice 8. Por isso o codigo casa pelo ROTULO e nao pelo
    # indice — indice errado pega a coluna vizinha sem erro nenhum.
    def linha_swap(cnpj):
        vals = [''] * 146
        vals[8] = cnpj
        return {'c%d' % i: v for i, v in enumerate(vals)}
    grava('Swap', '73760_{}_DPOSICAO-SWAP.json'.format(dref),
          [linha_swap(TAX_SEM_ZERO), linha_swap(''), linha_swap('99999999000199')])
    sw = R._swapchar_collect(ref.date())
    check('Swap: contraparte vira nome / vazio / numero',
          coluna(sw, 'CPF/CNPJ Cliente Contraparte'),
          [NOME, '', '99.999.999/0001-99'])
    check('Swap: o indice 8 e mesmo o da coluna',
          R._SWAPCHAR_LABELS[8], 'CPF/CNPJ Cliente Contraparte')
finally:
    R.B3_JSON_ROOT = root_orig
    shutil.rmtree(tmp, ignore_errors=True)

print('\n== 6. o registro de quais colunas viram nome ==')
check('NDF', R._LPNDF_CPTY_NAME_COLS, {'CPF/CNPJ da Contraparte'})
check('Option', R._LPOPT_CPTY_NAME_COLS, {'CPF/CNPJ Cliente Contraparte'})
check('Swap', R._SWAPCHAR_CPTY_NAME_COLS, {'CPF/CNPJ Cliente Contraparte'})
# A da Parte saiu do conjunto de mascara? Nao — ela CONTINUA la, sozinha.
check('Option: so a Parte continua mascarada',
      R._LPOPT_CNPJ_COLS, {'CPF/CNPJ Cliente Parte'})

print('\n== 7. quem mais LE essa coluna ==')
# O Settlement Advice de NDF Commodities consome a TELA do Live Position e
# tirava o CPF/CNPJ dessa celula para resolver o cliente por tras da conta
# omnibus (§197). Trocar a celula pelo nome zerou esse lookup em SILENCIO — o
# aviso sairia endereçado ao titular do guarda-chuva. Hoje os dois usam a MESMA
# resolucao, e o que separa "resolveu" de "nao resolveu" e `_lp_is_taxid`.
check('nome com numero NAO e documento', R._lp_is_taxid('3M DO BRASIL LIMITADA'), False)
check('CNPJ mascarado e documento', R._lp_is_taxid('00.514.820/0001-00'), True)
check('CNPJ cru e documento', R._lp_is_taxid('00514820000100'), True)
check('CPF mascarado e documento', R._lp_is_taxid('123.456.789-01'), True)
check('vazio nao e documento', R._lp_is_taxid(''), False)
check('numero curto demais nao e documento', R._lp_is_taxid('123'), False)
# A resolucao CRUA, que e a que o aviso usa: sem cadastro devolve '' (e o aviso
# cai para o nome da posicao), nao o numero.
check('resolucao crua: com cadastro', R._lp_cpty_name_by_taxid(TAX_DIG), NOME)
check('resolucao crua: sem cadastro devolve vazio',
      R._lp_cpty_name_by_taxid('99999999000199'), '')
check('e a de exibicao cai para o numero',
      R._lp_cpty_by_taxid('99999999000199'), '99.999.999/0001-99')
# E o aviso nao pode voltar a fazer o lookup por conta propria.
SRC = io.open(os.path.join(ROOT, 'apps', 'pages', 'routes.py'), encoding='utf-8').read()
check('o aviso nao refaz o lookup por CNPJ',
      "cliente = _refdata_by_taxid().get(cnpj, '')" in SRC, False)
check('ele le a celula ja resolvida', "cliente = '' if _lp_is_taxid(doc) else doc" in SRC, True)

print('\nFALHAS: %d' % len(fails))
sys.exit(1 if fails else 0)
