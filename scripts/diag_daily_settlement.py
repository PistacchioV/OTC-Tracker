#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diag_daily_settlement.py — por que o card Save Daily Settlement guardou
N de M linhas.

O card devolve só a contagem (`<tipo>: 0 of 5000 line(s)`), e "0 de 5 mil" tem
meia dúzia de causas que não dão erro nenhum: o nome do arquivo casou com outro
spec, o header não está na linha que o spec diz, um filtro de coluna derrubou
tudo (a coluna dos filtros é 1-BASED), ou o extractor não ACHOU a coluna pelo
nome — e a coluna some da tela em branco, sem uma linha de log.

Este script roda o MESMO caminho do card (`_ds_match_spec` + o extractor do
spec) e imprime o que ele viu: o spec que casou, a linha de header, as colunas
que resolveram e as que ficaram em None, e quantas linhas cada filtro comeu.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share \
        python scripts/diag_daily_settlement.py "<arquivo>" [AAAA-MM-DD]

A data é a Reference date do card (padrão: hoje) — ela IMPORTA nos specs que
filtram por data (Kapital Hybrids só guarda a liquidação DO DIA).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps.pages import routes as R          # noqa: E402


def _norm(s):
    return R._fcst_norm(str(s or ''))


def _cabecalho(rows, hidx):
    print('  header (linha %d): %d coluna(s)' % (hidx + 1, len(rows[hidx]) if hidx < len(rows) else 0))
    if hidx < len(rows):
        for i, h in enumerate(rows[hidx], start=1):
            print('     col %3d: %r' % (i, str(h or '').strip()))


def _resolvidas(idx_map, rows, hidx):
    """Imprime coluna pedida → índice achado, separando as que ficaram em None —
    é o que deixa a célula em branco na tela sem erro nenhum."""
    faltando = [c for c, i in idx_map.items() if i is None]
    for c, i in idx_map.items():
        alvo = '' if i is None else repr(str(rows[hidx][i]).strip() if i < len(rows[hidx]) else '')
        print('     %-28s → %s %s' % (c, 'NÃO ACHADA' if i is None else 'col %d' % (i + 1), alvo))
    if faltando:
        print('  !! %d coluna(s) não encontradas no header: %s'
              % (len(faltando), ', '.join(faltando)))
        print('     (cada uma sai VAZIA em todas as linhas — o header do arquivo '
              'mudou de nome ou o spec está lendo a linha errada)')


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    caminho = sys.argv[1]
    ref = R._parse_date_any(sys.argv[2]) if len(sys.argv) > 2 else R._br_now().date()
    if ref is None:
        print('data inválida: %r' % sys.argv[2])
        return 2
    ref = R.datetime(ref.year, ref.month, ref.day)
    nome = os.path.basename(caminho)
    with open(caminho, 'rb') as fh:
        raw = fh.read()
    print('\narquivo : %s  (%.2f MB)' % (nome, len(raw) / 1048576.0))
    print('reference date: %s' % ref.strftime('%d/%m/%Y'))

    spec = R._ds_match_spec(nome)
    if not spec:
        print('\n>> NENHUM spec casou com este nome — o card o conta como IGNORADO.')
        print('   O casamento é pelo INÍCIO do nome, em minúsculas:')
        for s in R._DS_IMPORTS:
            print('     %-24s %s' % (s['key'], s['label']))
        return 1
    print('\nspec    : %s (%s) → %s' % (spec['key'], spec['label'], spec['json']))

    # ── os extractores próprios ──────────────────────────────────────────────
    if spec.get('swaphyb'):
        rows = R._swaphyb_read_rows(raw)
        print('linhas lidas: %d' % len(rows))
        hidx = 0
        for i, r in enumerate(rows[:15]):
            low = [_norm(c) for c in r]
            if any('confirmation' in c for c in low) or \
               (any('settlement date' in c for c in low) and any(c == 'amount' for c in low)):
                hidx = i
                break
        _cabecalho(rows, hidx)
        norm = [_norm(h) for h in rows[hidx]]
        i_settle = [i for i, n in enumerate(norm)
                    if n == 'settlement date' or n.startswith('settlement date')]
        i_cpty = next((i for i, n in enumerate(norm)
                       if 'counterparty' in n and 'name' in n), None)
        print('  Settlement Date → %s' % ([i + 1 for i in i_settle] or 'NÃO ACHADA'))
        print('  Counterparty Name → %s' % ('col %d' % (i_cpty + 1) if i_cpty is not None
                                            else 'NÃO ACHADA (sai em branco)'))
        datas = {}
        for row in rows[hidx + 1:]:
            if not any(str(c).strip() for c in row):
                continue
            d = None
            for si in i_settle:
                d = R._swaphyb_parse_date(str(row[si]).strip() if si < len(row) else '')
                if d:
                    break
            datas[d] = datas.get(d, 0) + 1
        print('\n  Settlement Date encontradas (o spec guarda SÓ a da reference date):')
        for d, n in sorted(datas.items(), key=lambda kv: (kv[0] is None, kv[0])):
            marca = '  <<< a reference date' if d == ref.date() else ''
            print('     %-12s %5d linha(s)%s'
                  % (d.strftime('%d/%m/%Y') if d else 'NÃO PARSEOU', n, marca))
        recs, total = R._swaphyb_extract(raw, ref)
        print('\n>> guardaria %d de %d linha(s)' % (len(recs), total))
        return 0

    if spec.get('otm'):
        rows = R._ds_read_rows(raw)
        print('linhas lidas: %d' % len(rows))
        _cabecalho(rows, 0)
        hnorm = [_norm(h) for h in rows[0]]

        def col_idx(name):
            n = _norm(name)
            if n in hnorm:
                return hnorm.index(n)
            for i, h in enumerate(hnorm):
                if h and (n in h or h in n):
                    return i
            return None
        print('\n  colunas do relatório:')
        _resolvidas({c: col_idx(c) for c in R._OTM_COLUMNS}, rows, 0)
        recs, kept, deleted, filtered = R._otm_extract(rows)
        print('\n  col 14 == DELETE       → %d linha(s) fora' % deleted)
        print('  col 22 fora de %s → %d linha(s) fora' % (sorted(R._OTM_KEEP_CODES), filtered))
        print('\n>> guardaria %d de %d linha(s)' % (kept, kept + deleted + filtered))
        return 0

    if spec.get('latam'):
        rows, fmt = R._latam_read_rows(raw)
        print('linhas lidas: %d (formato %s)' % (len(rows), fmt))
        _cabecalho(rows, 0)
        recs, kept, filtered, _cmap, missing = R._latam_extract(rows)
        if missing:
            print('  !! colunas não encontradas no header: %s' % ', '.join(missing))
        print('\n>> guardaria %d de %d linha(s) (%d filtradas)' % (kept, kept + filtered, filtered))
        return 0

    if spec.get('ndfc') or spec.get('cog'):
        rows = R._ndfc_read_rows(raw) if spec.get('ndfc') else R._cog_read_rows(raw)
        hidx = (R._NDFC_HEADER_ROW - 1) if spec.get('ndfc') else 0
        cols = R._NDFC_COLUMNS if spec.get('ndfc') else R._COG_COLUMNS
        print('linhas lidas: %d' % len(rows))
        _cabecalho(rows, hidx)
        hnorm = [_norm(h) for h in rows[hidx]]

        def col_idx(name):
            n = _norm(name)
            if n in hnorm:
                return hnorm.index(n)
            for i, h in enumerate(hnorm):
                if h and (n in h or h in n):
                    return i
            return None
        print('\n  colunas do relatório:')
        _resolvidas({c: col_idx(c) for c in cols}, rows, hidx)
        recs, kept = (R._ndfc_extract(rows) if spec.get('ndfc') else R._cog_extract(rows))
        print('\n>> guardaria %d linha(s)' % kept)
        return 0

    # ── o caminho genérico (`_ds_process`): header do spec + filtros por coluna ──
    rows = R._ds_read_rows(raw)
    hidx = spec['header'] - 1
    print('linhas lidas: %d' % len(rows))
    if len(rows) <= hidx:
        print('>> o arquivo tem MENOS linhas que o header do spec (linha %d) — 0 guardadas'
              % spec['header'])
        return 1
    _cabecalho(rows, hidx)
    # Quantas linhas cada filtro derruba, um a um — a coluna do spec é 1-BASED.
    comeu = {}
    total = 0
    vistos = {}
    for row in rows[hidx + 1:]:
        if not any(R._ds_cell(row, i) for i in range(len(row))):
            continue
        total += 1
        for f in spec['filters']:
            rot = '%s col %s %s' % (f[0], f[1], sorted(f[2]) if len(f) > 2 else '')
            if f[0] == 'nonempty_any':
                mau = not any(R._ds_cell(row, c - 1) for c in f[1])
            elif f[0] == 'not_startswith':
                cel = R._ds_cell(row, f[1] - 1).upper()
                mau = any(cel.startswith(p.upper()) for p in f[2])
            else:
                kind, col, allowed = f
                v = R._ds_cell(row, col - 1)
                vistos.setdefault(rot, {})
                chave = ''.join(ch for ch in v if ch.isdigit()) if kind == 'digits' else v.upper()
                vistos[rot][chave] = vistos[rot].get(chave, 0) + 1
                mau = chave not in allowed
            if mau:
                comeu[rot] = comeu.get(rot, 0) + 1
                break
    print('\n  filtros (a coluna do spec é 1-BASED — confira contra o header acima):')
    for f in spec['filters']:
        rot = '%s col %s %s' % (f[0], f[1], sorted(f[2]) if len(f) > 2 else '')
        print('     %-60s derrubou %d' % (rot, comeu.get(rot, 0)))
        for chave, n in sorted(vistos.get(rot, {}).items(), key=lambda kv: -kv[1])[:12]:
            print('          valor %-24r %5d linha(s)' % (chave, n))
    recs, tot = R._ds_process(raw, spec)
    print('\n>> guardaria %d de %d linha(s)' % (len(recs), tot))
    return 0


if __name__ == '__main__':
    sys.exit(main())
