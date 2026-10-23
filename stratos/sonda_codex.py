#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sonda_codex.py — confere, na máquina do JPM, se o Codex responde pelos ativos
que a Quotes busca hoje no Yahoo.

    python stratos/sonda_codex.py                      (3 de cada grupo do quotes-equity)
    python stratos/sonda_codex.py --todos              (o cadastro inteiro)
    python stratos/sonda_codex.py --ids PETR4-BR AAPL-US   (identificadores à mão)
    python stratos/sonda_codex.py --dias 15 --csv C:\\Temp\\sonda.csv

Roda com o python em que o Codex já funciona (no desktop ele usa o seu login
sozinho). Não toca em banco nem em cadastro: lê a SEED do `quotes-equity`
versionada no repositório, que pode estar atrás do que a equipe cadastrou na
tela.

O identificador tentado é um PALPITE desta sonda, não uma regra do app: o
padrão FactSet `TICKER-PAÍS` (`AAPL` → `AAPL-US`, `ABEV3.SA` → `ABEV3-BR`). O
que ela responde é se o palpite pega, e que fechamento o Codex devolve. A
regra de verdade vai para o cadastro (/mapping) depois. Índices (`^BVSP`),
outras bolsas e commodities ficam sem palpite: teste-os com `--ids`.
"""
import argparse
import csv
import io
import json
import os
import sys
from datetime import date, timedelta

WT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
SEED = os.path.join(WT, 'apps', 'static', 'data', 'mappings', 'quotes-equity.json')
CAMPOS = ['fp_open_price', 'fp_low_price', 'fp_high_price', 'fp_close_price', 'fp_volume']


def palpite(simbolo):
    """O identificador FactSet que a sonda tenta para um símbolo do Yahoo."""
    s = str(simbolo or '').strip().upper()
    if s.endswith('.SA'):
        return s[:-3] + '-BR'
    if s and not any(ch in s for ch in '.=^'):
        return s + '-US'
    return None


def amostra(linhas, por_grupo):
    """Os primeiros `por_grupo` símbolos distintos de cada NOTES (grupo)."""
    vistos, grupos, out = set(), {}, []
    for r in linhas:
        simbolo = str(r.get('SYMBOL') or '').strip()
        if not simbolo or simbolo in vistos:
            continue
        grupo = str(r.get('NOTES') or '').strip() or '(sem grupo)'
        if por_grupo and grupos.get(grupo, 0) >= por_grupo:
            continue
        vistos.add(simbolo)
        grupos[grupo] = grupos.get(grupo, 0) + 1
        out.append((str(r.get('LABEL') or ''), simbolo, grupo))
    return out


def sonda(fetcher, ident, d1, d2):
    """(situação, data, fechamento) do identificador no Codex."""
    try:
        df = fetcher.fetch(CAMPOS, [ident], d1, d2)
    except Exception as exc:                                 # noqa: BLE001
        return 'ERRO ' + (str(exc).strip().splitlines() or [type(exc).__name__])[0][:120], '', ''
    if df is None or getattr(df, 'empty', True):
        return 'SEM DADOS', '', ''
    if 'fp_close_price' not in getattr(df, 'columns', []):
        return 'SEM fp_close_price (colunas: %s)' % ', '.join(map(str, df.columns))[:120], '', ''
    fech = df['fp_close_price'].dropna()
    if fech.empty:
        return 'FECHAMENTO VAZIO', '', ''
    fech = fech.sort_index()
    quando = fech.index[-1]
    quando = quando.strftime('%d/%m/%Y') if hasattr(quando, 'strftime') else str(quando)
    return 'OK', quando, '{:,.4f}'.format(float(fech.iloc[-1]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--todos', action='store_true', help='o cadastro inteiro, não a amostra')
    ap.add_argument('--por-grupo', type=int, default=3, help='quantos de cada grupo na amostra')
    ap.add_argument('--ids', nargs='+', default=None, help='identificadores do Codex, à mão')
    ap.add_argument('--dias', type=int, default=10, help='janela de dias corridos até hoje')
    ap.add_argument('--csv', default=None, help='grava também um CSV (separador ;)')
    args = ap.parse_args(argv)
    try:
        from codex.api import Codex
    except ImportError as exc:
        print('ERRO: o Codex não está neste python (%s). Rode com o python em que o\n'
              '     `from codex.api import Codex` funciona.' % exc)
        return 1
    fetcher = Codex()
    d2 = date.today()
    d1 = d2 - timedelta(days=max(1, args.dias))
    if args.ids:
        alvos = [('', '', '(à mão)', i) for i in args.ids]
    else:
        linhas = json.load(io.open(SEED, encoding='utf-8'))
        alvos = [(rot, sim, grp, palpite(sim))
                 for rot, sim, grp in amostra(linhas, 0 if args.todos else args.por_grupo)]
    print('Codex, %s a %s, %d ativo(s)\n' % (d1.strftime('%d/%m/%Y'), d2.strftime('%d/%m/%Y'), len(alvos)))
    print('%-12s %-12s %-14s %-11s %14s  %s' % ('RÓTULO', 'YAHOO', 'CODEX', 'DATA', 'FECHAMENTO', 'SITUAÇÃO'))
    saida, ok = [], 0
    for rot, sim, grp, ident in alvos:
        if not ident:
            situ, quando, fech = 'SEM PALPITE (use --ids)', '', ''
        else:
            situ, quando, fech = sonda(fetcher, ident, d1, d2)
        ok += situ == 'OK'
        print('%-12s %-12s %-14s %-11s %14s  %s' % (rot[:12], sim[:12], (ident or '-')[:14],
                                                    quando, fech, situ))
        saida.append([rot, sim, grp, ident or '', quando, fech, situ])
    print('\n%d de %d responderam' % (ok, len(alvos)))
    if args.csv:
        with io.open(args.csv, 'w', encoding='utf-8-sig', newline='') as fh:
            w = csv.writer(fh, delimiter=';')
            w.writerow(['ROTULO', 'YAHOO', 'GRUPO', 'CODEX', 'DATA', 'FECHAMENTO', 'SITUACAO'])
            w.writerows(saida)
        print('CSV: %s' % args.csv)
    return 0


if __name__ == '__main__':
    sys.exit(main())
