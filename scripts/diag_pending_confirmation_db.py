# -*- coding: utf-8 -*-
"""Extrai o CONTEÚDO dos bancos do Pending Confirmation (backlog, pending, ok).

    python scripts/diag_pending_confirmation_db.py                 # o backlog
    python scripts/diag_pending_confirmation_db.py --db todos      # os três
    python scripts/diag_pending_confirmation_db.py --db ok --csv
    python scripts/diag_pending_confirmation_db.py --so-resumo     # sem arquivo

Duas coisas, e a segunda é a que costuma responder a pergunta:

1. o DESPEJO do banco num arquivo (uma aba por banco), tal como ele está
   gravado — `SELECT *`, colunas legadas inclusive;
2. o RESUMO na tela: quantas linhas, a Trade Date mais velha e a mais nova, o
   histograma por ano e — o ponto — **quantas linhas têm data ILEGÍVEL**, com
   amostras do texto cru.

O item 2 existe porque "a busca não traz nada antes de tal dia" tem duas causas
que se parecem e se consertam de jeitos opostos: ou o banco não tem nada mais
velho, ou tem e a data está num formato que o app não lê (serial do Excel,
`26/8/25`, texto com sujeira) — aí a linha some de todo filtro por data sem erro
nenhum. O resumo separa as duas em uma passada.

Notas de leitura:

  · O despejo é o que está GRAVADO. As colunas `Aging` e `Status` são
    recalculadas na LEITURA da tela (hoje − Trade Date), então elas aqui podem
    estar velhas — a tela está certa, o banco é que guarda o valor do dia em que
    a linha foi escrita pela última vez.
  · A abertura passa pela camada do app (`duckdb_read`): lock de arquivo
    compartilhado e semáforo, que é o que deixa rodar com o app DE PÉ. Banco em
    uso ou ilegível **para este banco com o motivo** em vez de imprimir zero
    linha — uma tabela vazia é indistinguível de um banco que não abriu, e é
    exatamente essa confusão que o script existe para desfazer.
  · Só LÊ. Não grava nada em banco nenhum.
  · O arquivo sai em .xlsx com TODA célula como TEXTO: o Trade Number
    `26E04610365` vira `#NULL!` no Excel se a célula for numérica (§477), e é
    justamente a coluna pela qual se procura a operação. Com `--csv` o arquivo é
    `;` + BOM (o padrão do app) — e aí o Excel converte na abertura, porque a
    conversão é dele, não do arquivo.
"""
import argparse
import csv
import io
import os
import sys
import traceback
from collections import Counter

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'
# Fora do Windows a raiz do share é obrigatória (§9). Aqui ela não é usada para
# nada — os bancos vêm do DATABASE_DIR —, mas sem ela o import do config recusa.
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)

DBS = {
    'backlog': 'pending-confirmation-backlog.db',
    'pending': 'pending-confirmation-pending.db',
    'ok': 'pending-confirmation-ok.db',
}
TABELA = 'pending_confirmation'


def _parse_data(v):
    """As quatro escritas que o app entende (`platform/dates._parse_date_any`).

    Importar a do app amarraria o diagnóstico ao boot do app; o que importa aqui
    é fazer a MESMA pergunta que o filtro faz, e a lista é esta."""
    from datetime import datetime
    s = str(v or '').strip()
    if not s:
        return None
    s = s.split('T')[0].split(' ')[0]
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%Y%m%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _db_dir():
    """A pasta dos bancos é a do APP (`Config.DATABASE_DIR`).

    Montá-la à mão aqui faria o script ler o banco LOCAL enquanto o app lê o do
    share: o despejo "dá certo" e responde sobre outro arquivo."""
    from apps.config import Config
    return Config.DATABASE_DIR


def ler(caminho):
    """Todas as linhas e os nomes das colunas, como estão no banco."""
    from apps.pages.database_access import duckdb_read
    with duckdb_read(caminho) as con:
        cur = con.execute('SELECT * FROM {}'.format(TABELA))
        cols = [d[0] for d in cur.description]
        return cols, cur.fetchall()


def resumo(nome, cols, linhas):
    print('  linhas: %d   colunas: %d' % (len(linhas), len(cols)))
    if not linhas:
        # Zero linha num banco que ABRIU é resposta, não falha: dizê-lo assim
        # evita que se procure defeito onde não há dado.
        print('  (o banco abriu e está VAZIO)')
        return
    for campo in ('Trade Date', 'Maturity Date'):
        if campo not in cols:
            print('  %-14s coluna não existe neste banco' % campo)
            continue
        i = cols.index(campo)
        datas, vazias, ilegiveis = [], 0, []
        for r in linhas:
            cru = r[i]
            if str(cru or '').strip() == '':
                vazias += 1
                continue
            d = _parse_data(cru)
            if d is None:
                ilegiveis.append(str(cru))
            else:
                datas.append(d)
        print('  %-14s %d com data   %d em branco   %d ILEGÍVEIS' % (
            campo, len(datas), vazias, len(ilegiveis)))
        if datas:
            print('  %-14s mais velha: %s     mais nova: %s' % (
                '', min(datas).strftime('%d/%m/%Y'), max(datas).strftime('%d/%m/%Y')))
            anos = Counter(d.year for d in datas)
            print('  %-14s por ano: %s' % (
                '', '  '.join('%d=%d' % (a, anos[a]) for a in sorted(anos))))
        if ilegiveis:
            # A amostra é o que diz QUAL formato é — e é o que se leva para
            # quem vai corrigir a origem.
            amostra = sorted(set(ilegiveis))[:10]
            print('  %-14s amostra do texto ilegível: %s' % ('', ', '.join(repr(x) for x in amostra)))
    if 'Pending Status' in cols:
        i = cols.index('Pending Status')
        c = Counter(str(r[i] or '(vazio)') for r in linhas)
        print('  Pending Status: %s' % '  '.join(
            '%s=%d' % (k, v) for k, v in c.most_common(8)))


def escreve_xlsx(destino, abas):
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Font
    wb = Workbook(write_only=True)
    for nome, cols, linhas in abas:
        ws = wb.create_sheet(title=nome[:31])
        cab = []
        for c in cols:
            cel = WriteOnlyCell(ws, value=c)
            cel.font = Font(bold=True)
            cel.number_format = '@'
            cab.append(cel)
        ws.append(cab)
        for r in linhas:
            saida = []
            for v in r:
                cel = WriteOnlyCell(ws, value='' if v is None else str(v))
                cel.number_format = '@'          # TEXTO — §477
                saida.append(cel)
            ws.append(saida)
    wb.save(destino)


def escreve_csv(destino, cols, linhas):
    # `;` + BOM: o separador e a marca que o Excel do JP espera (§7).
    with io.open(destino, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        w.writerow(cols)
        for r in linhas:
            w.writerow(['' if v is None else str(v) for v in r])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db', default='backlog', choices=sorted(DBS) + ['todos'],
                    help='qual banco extrair (padrão: backlog)')
    ap.add_argument('--out', default=None, help='arquivo de saída')
    ap.add_argument('--db-dir', default=None,
                    help='outra pasta de bancos (o padrão é a do app)')
    ap.add_argument('--csv', action='store_true',
                    help='CSV (;+BOM) em vez de .xlsx — um arquivo por banco')
    ap.add_argument('--so-resumo', action='store_true', help='não gera arquivo')
    args = ap.parse_args()

    from datetime import datetime
    pasta = args.db_dir or _db_dir()
    alvos = sorted(DBS) if args.db == 'todos' else [args.db]
    print('bancos em: %s\n' % pasta)

    lidos, falhou = [], []
    for cat in alvos:
        caminho = os.path.join(pasta, DBS[cat])
        print('== %s (%s)' % (cat, DBS[cat]))
        if not os.path.isfile(caminho):
            print('  ARQUIVO NÃO EXISTE\n')
            falhou.append(cat)
            continue
        print('  %.1f MB   modificado em %s' % (
            os.path.getsize(caminho) / 1048576.0,
            datetime.fromtimestamp(os.path.getmtime(caminho)).strftime('%d/%m/%Y %H:%M')))
        try:
            cols, linhas = ler(caminho)
        except Exception as e:                                   # noqa: BLE001
            # Em uso pela instância vizinha, `.wal` de outra versão, arquivo
            # truncado: o motivo VAI para a tela. Silenciar aqui devolveria uma
            # planilha vazia que se lê como "não há nada gravado".
            print('  NÃO DEU PARA LER: %s: %s' % (type(e).__name__, e))
            print(''.join('    ' + l for l in traceback.format_exc().splitlines(True)))
            falhou.append(cat)
            continue
        resumo(cat, cols, linhas)
        lidos.append((cat, cols, linhas))
        print()

    if lidos and not args.so_resumo:
        carimbo = datetime.now().strftime('%Y%m%d-%H%M')
        if args.csv:
            for cat, cols, linhas in lidos:
                destino = args.out if (args.out and len(lidos) == 1) else \
                    'pending-confirmation-%s-%s.csv' % (cat, carimbo)
                escreve_csv(destino, cols, linhas)
                print('CSV: %s  (%d linhas)' % (os.path.abspath(destino), len(linhas)))
        else:
            destino = args.out or ('pending-confirmation-%s-%s.xlsx' % (
                args.db if args.db != 'todos' else 'tres-bancos', carimbo))
            escreve_xlsx(destino, lidos)
            print('XLSX: %s  (%s)' % (os.path.abspath(destino),
                                      ', '.join('%s=%d' % (c, len(r)) for c, _, r in lidos)))

    if falhou:
        print('\nnão lidos: %s' % ', '.join(falhou))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
