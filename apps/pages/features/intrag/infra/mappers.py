# -*- coding: utf-8 -*-
"""O CSV de retorno do Batch Conecta → `{chave: B3 ID}`."""
from apps.pages.features.intrag import domain


def _intrag_build_b3_map(csv_path, match_col, match_val, b3_col, sem_recompra=False):
    """Parse the Boletas CSV (no header) → {b3_key → Intrag ID (col A)} for rows
    whose `match_col` STARTS WITH `match_val`.

    Prefixo, e não igualdade: a coluna ecoa o texto do instrumento que o app
    enviou, e a MESMA tela de NDF manda dois — `NDF - TERMO MERCADORIA` e
    `NDF - TERMO DE MOEDAS`. Com igualdade exata, a linha de moeda voltava no
    CSV e era descartada aqui ANTES do casamento: o Mapping dizia "N mapped"
    (as de mercadoria) e o termo de moedas ficava sem Intrag ID, sem erro
    nenhum. O filtro é só a FAMÍLIA da linha; quem pareia de verdade é o B3
    ID, que é exato e único — alargar o filtro não tem como casar cruzado.

    `match_val=None` não filtra família (o SWAP, mesa 23/10/2026): na boleta de
    swap a coluna B é a CARTEIRA (`INTRAGJP633`), não o instrumento, e o filtro
    `SWAP` — uma suposição de antes de o arquivo existir — descartava TODA
    linha de swap antes do casamento; o Mapping respondia "No matching
    operations" com o B3 ID ali na coluna C. `sem_recompra` pula a linha que se
    diz recompra (`UNWIND_MARKS`): a boleta da antecipação leva o MESMO B3 ID do
    contrato, e sem filtro de família ela poderia dar ao swap o Intrag ID da
    recompra."""
    import csv as _csv
    out = {}
    with open(csv_path, 'r', encoding='latin-1', newline='') as fh:
        sample = fh.read(4096); fh.seek(0)
        delim = ';' if sample.count(';') > sample.count(',') else ','
        for row in _csv.reader(fh, delimiter=delim):
            if len(row) <= max(match_col, b3_col):
                continue
            if match_val is not None and \
                    not str(row[match_col]).strip().upper().startswith(match_val):
                continue
            if sem_recompra and any(m in _sem_acento_upper(' '.join(row))
                                    for m in UNWIND_MARKS):
                continue
            b3, intrag_id = domain._intrag_b3_key(row[b3_col]), str(row[0]).strip()
            if b3 and intrag_id:
                out.setdefault(b3, intrag_id)
    return out


# ── Intrag Unwind: o Intrag ID da RECOMPRA (mesa, 28/09/2026) ────────────────
# O mesmo CSV de Boletas, mas o B3 ID da recompra e o do contrato ORIGINAL — a
# boleta do registro tem o mesmo numero. Casar so pelo B3 ID daria a recompra o
# Intrag ID da operacao original. Por isso a linha tem de SE DIZER recompra: o
# B3 ID numa celula E uma das marcas abaixo em qualquer celula (cego a caixa e
# acento). O layout da boleta de antecipacao nao foi visto — a marca e a
# suposicao, e o B3 ID que so aparece em linha sem marca volta como
# `so_original` (a tela avisa em vez de gravar o ID errado).
UNWIND_MARKS = ('RECOMPRA', 'ANTECIPA', 'UNWIND', 'RESILI')


def _sem_acento_upper(txt):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFKD', str(txt or ''))
                   if not unicodedata.combining(c)).upper()


def _intrag_unwind_b3_map(csv_path):
    """-> ({b3_key: Intrag ID (col A)} das linhas de RECOMPRA, {b3_key} que so
    aparecem em linha SEM a marca)."""
    import csv as _csv
    marcadas, sem_marca = {}, set()
    with open(csv_path, 'r', encoding='latin-1', newline='') as fh:
        sample = fh.read(4096); fh.seek(0)
        delim = ';' if sample.count(';') > sample.count(',') else ','
        for row in _csv.reader(fh, delimiter=delim):
            if len(row) < 2:
                continue
            intrag_id = str(row[0]).strip()
            chaves = {domain._intrag_b3_key(c) for c in row[1:]} - {''}
            if not intrag_id or not chaves:
                continue
            texto = _sem_acento_upper(' '.join(row))
            if any(m in texto for m in UNWIND_MARKS):
                for k in chaves:
                    marcadas.setdefault(k, intrag_id)
            else:
                sem_marca |= chaves
    return marcadas, sem_marca - set(marcadas)
