# -*- coding: utf-8 -*-
"""Insere nos bancos do Pending Confirmation o que a planilha tem e eles NÃO têm.

    python scripts/import_pending_confirmation_missing.py                 # só relata
    python scripts/import_pending_confirmation_missing.py --gravar
    python scripts/import_pending_confirmation_missing.py --xlsx "C:\\...\\arquivo.xlsx"

Sem `--gravar` ele não escreve nada: lê a planilha, resolve os nomes contra o
Reference Data, diz o que faria e gera o relatório dos nomes. Rodar assim
primeiro é o jeito de conferir os matches ANTES de mexer na prod.

O que ele faz, e por quê cada coisa é assim:

  · **Trade Number que já está em QUALQUER um dos três bancos é PULADO.** Este
    script só acrescenta o que falta; ele não corrige linha existente e não
    apaga nada. Quem reconstrói os bancos a partir da planilha é o
    `import_pending_confirmation.py` — e aquele APAGA o que não estiver nela,
    backlog inclusive, que é só história e não se repovoa.

  · **SPN, Client e Owner saem do Reference Data**, não da planilha: são o
    cadastro, e é por eles que a tela junta a operação ao Economic Group, ao
    Signature Type e ao banker. O resto (LOB, Product Type, Trade Date,
    Maturity Date, Trade Number, Pending Status, EA, datas de envio e retorno,
    Break Reason, comentários, FepWeb ID) vem da planilha.

  · **O nome casa por IGUALDADE primeiro.** Sem match exato, procura o mais
    parecido — e só o aplica se ele passar do limiar (padrão 90%) E ganhar do
    segundo colocado por uma margem (padrão 3 pontos). Abaixo disso, ou empatado,
    o SPN fica EM BRANCO e o nome vai para o relatório. Um SPN parecido não é um
    SPN: ele leva a operação para outra contraparte, com Owner, Economic Group e
    Signature Type de outra contraparte junto, e nada na tela acusa.

  · **A leitura dos bancos é ESTRITA.** Se um dos três não abrir (a instância
    vizinha com a trava, `.wal` de outra versão), o script PARA. Lida como
    "banco vazio", a falha faria ele reinserir como novo tudo que já estava lá.

  · A gravação é a do app (`_pc_upsert_rows`): a linha é reencaminhada ao banco
    a que pertence AGORA (backlog acima de 12 meses, ok se resolvida, senão
    pending) e passa pelas regras automáticas de Aging/Status. Reescrever isso
    aqui faria a planilha entrar com uma regra e a tela ler com outra.

Relatório dos nomes (`--relatorio`, padrão ao lado da planilha): uma linha por
nome DISTINTO da planilha, com o tipo do match, o %, o nome e o SPN do Reference
Data e quantas linhas dependiam dele.
"""
import argparse
import csv
import difflib
import io
import os
import re
import sys
import unicodedata
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)

NOME_PADRAO = 'Copy of PENDING - Outstanding Confirmation OTC.xlsx'
# Onde procurar quando ninguém passou `--xlsx`: o Downloads é onde ela cai.
CANDIDATOS = [
    os.path.join(os.path.expanduser('~'), 'Downloads', NOME_PADRAO),
    os.path.join(os.path.expanduser('~'), 'Downloads',
                 'PENDING - Outstanding Confirmation OTC.xlsx'),
    os.path.join(ROOT, 'scripts', NOME_PADRAO),
    os.path.join(ROOT, 'scripts', 'PENDING - Outstanding Confirmation OTC.xlsx'),
]

# Coluna da PÁGINA → cabeçalhos aceitos na planilha. Duas escritas convivem: a
# do "PENDING - Outstanding Confirmation" e a do "Pending Update", que a tela
# também importa. A resolução é pelo NOME do cabeçalho (a ordem das colunas
# muda entre versões do arquivo); cabeçalho que não aparecer é relatado.
FONTES = {
    'Status':         ('Status',),
    'LOB':            ('LOB',),
    'Client':         ('Client', 'End Counterparty Desc', 'Counterparty'),
    'Product Type':   ('Product Type',),
    'Trade Date':     ('Trade Date', 'Booking Date'),
    'Maturity Date':  ('Maturity Date', 'Settlement Date'),
    'Trade Number':   ('Trade Number', 'Deal Name'),
    'Pending Status': ('Pending Status',),
    'EA':             ('EA',),
    'Send Date':      ('JP sending documentation', 'Send Date'),
    'Return Date':    ('Client return the document', 'Return Date'),
    'Break Reason':   ('Break Reason',),
    'Comments':       ('Overall Comments', 'Comments'),
    'FepWeb ID':      ('Trade Number IS FEP WEB', 'FepWeb ID'),
    'Pendência':      ('Pendência',),
}
# Guardadas dd/mm/aaaa, que é como o filtro da tela as lê. `Pendência` NÃO está
# aqui: ela virou texto livre quando as colunas de abono saíram da página.
DATAS = {'Trade Date', 'Maturity Date', 'EA', 'Send Date', 'Return Date'}


def _norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]', '', s.lower())


def _texto(v, erros_xl):
    """Célula → texto. Fórmula com erro (`#NULL!`, `#N/A`) NÃO é dado: vira
    vazio, senão entra no banco e sai na próxima planilha como se fosse."""
    if v is None:
        return ''
    if isinstance(v, datetime):
        return v.strftime('%d/%m/%Y')
    s = str(v).strip()
    if s.upper() in erros_xl or s.lower() in ('nan', 'nat', 'none'):
        return ''
    if re.fullmatch(r'-?\d+\.0', s):      # openpyxl devolve inteiro como '123.0'
        s = s[:-2]
    return s


class Cadastro(object):
    """O Reference Data por nome, com o match por semelhança."""

    def __init__(self, by_name, limiar, margem):
        self.by_name = by_name
        self.nomes = list(by_name.keys())
        self.limiar = limiar
        self.margem = margem
        self.cache = {}

    def casa(self, cliente):
        """(rec, tipo, pct, alternativa). `tipo`: exato | semelhante | fraco |
        ambiguo | sem-nome | sem-cadastro.

        O resultado é memoizado por nome: o mesmo cliente aparece em dezenas de
        linhas e a comparação varre o cadastro inteiro."""
        chave = _norm(cliente)
        if chave in self.cache:
            return self.cache[chave]
        r = self._casa(chave)
        self.cache[chave] = r
        return r

    def _casa(self, chave):
        if not chave:
            return {}, 'sem-nome', 0.0, ''
        rec = self.by_name.get(chave)
        if rec is not None:
            return rec, 'exato', 100.0, ''
        if not self.nomes:
            return {}, 'sem-cadastro', 0.0, ''
        pares = []
        for n in self.nomes:
            m = difflib.SequenceMatcher(None, chave, n)
            # `real_quick_ratio`/`quick_ratio` são tetos baratos: quem não
            # alcança o limiar nem no teto não precisa da conta inteira.
            if m.real_quick_ratio() * 100 < self.limiar or m.quick_ratio() * 100 < self.limiar:
                continue
            pares.append((m.ratio() * 100, n))
        if not pares:
            # Ninguém passou do limiar: o melhor parecido ainda serve ao
            # RELATÓRIO — é o que deixa alguém decidir de fora.
            melhor = difflib.get_close_matches(chave, self.nomes, n=1, cutoff=0.0)
            if melhor:
                pct = difflib.SequenceMatcher(None, chave, melhor[0]).ratio() * 100
                return {}, 'fraco', pct, self._nome(melhor[0])
            return {}, 'sem-cadastro', 0.0, ''
        pares.sort(reverse=True)
        pct, nome = pares[0]
        segundo = pares[1] if len(pares) > 1 else (0.0, '')
        if segundo[0] and (pct - segundo[0]) < self.margem:
            # Dois nomes igualmente parecidos: escolher um é tirar no par ou
            # ímpar qual contraparte recebe a operação.
            return {}, 'ambiguo', pct, '%s (%.0f%%) / %s (%.0f%%)' % (
                self._nome(nome), pct, self._nome(segundo[1]), segundo[0])
        return self.by_name[nome], 'semelhante', pct, self._nome(nome)

    def _nome(self, chave_norm):
        return str((self.by_name.get(chave_norm) or {}).get('COUNTERPARTY', '') or chave_norm)


def le_planilha(caminho, erros_xl):
    """(linhas, resolvidos, faltando) — cada linha é {coluna da página: texto}."""
    import openpyxl
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    try:
        cab = next(it)
    except StopIteration:
        return [], {}, sorted(FONTES)
    idx = {}
    for i, h in enumerate(cab):
        n = _norm(h)
        if n and n not in idx:
            idx[n] = i
    resolvidos, faltando = {}, []
    for pc, aceitos in FONTES.items():
        for a in aceitos:
            if _norm(a) in idx:
                resolvidos[pc] = (idx[_norm(a)], a)
                break
        else:
            faltando.append(pc)
    linhas = []
    for row in it:
        if row is None or not any(v not in (None, '') for v in row):
            continue
        d = {}
        for pc, (i, _src) in resolvidos.items():
            d[pc] = _texto(row[i], erros_xl) if i < len(row) else ''
        linhas.append(d)
    try:
        wb.close()
    except Exception:                                            # noqa: BLE001
        pass
    return linhas, resolvidos, sorted(faltando)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--xlsx', default=None, help='a planilha (padrão: Downloads)')
    ap.add_argument('--db-dir', default=None,
                    help='pasta dos bancos (padrão: a da aplicação, Config.DATABASE_DIR)')
    ap.add_argument('--limiar', type=float, default=90.0,
                    help='%% mínimo do match por semelhança (padrão: 90)')
    ap.add_argument('--margem', type=float, default=3.0,
                    help='pontos de vantagem sobre o 2º colocado (padrão: 3)')
    ap.add_argument('--relatorio', default=None, help='CSV dos nomes (padrão: ao lado da planilha)')
    ap.add_argument('--gravar', action='store_true', help='grava (sem isto, só relata)')
    args = ap.parse_args()

    caminho = args.xlsx
    if not caminho:
        for c in CANDIDATOS:
            if os.path.isfile(c):
                caminho = c
                break
    if not caminho or not os.path.isfile(caminho):
        sys.exit('planilha não encontrada. Passe --xlsx, ou deixe "%s" no Downloads.'
                 % NOME_PADRAO)

    from apps.pages import routes as R
    from apps.pages.platform import pending_confirmation as PC
    if args.db_dir:
        R._PC_DB_DIR = args.db_dir

    print('planilha : %s' % caminho)
    print('bancos   : %s' % R._PC_DB_DIR)
    print('modo     : %s' % ('GRAVA' if args.gravar else 'só relata (use --gravar)'))
    print('-' * 78)

    linhas, resolvidos, faltando = le_planilha(caminho, getattr(R, '_XL_ERROR_TEXT', set()))
    print('linhas na planilha: %d' % len(linhas))
    print('colunas lidas     : %s' % ', '.join(
        '%s←%s' % (pc, src) for pc, (_i, src) in sorted(resolvidos.items())))
    if faltando:
        # Coluna que não veio não é erro — o arquivo muda de versão. Mas tem de
        # aparecer: em silêncio, ela entraria vazia no banco sem ninguém notar.
        print('colunas AUSENTES  : %s  (entram vazias)' % ', '.join(faltando))
    if 'Trade Number' in faltando or 'Client' in faltando:
        sys.exit('ERRO: sem Trade Number ou sem Client não há o que inserir.')

    # Os Trade Numbers que JÁ existem. `strict=True`: banco que não abre PARA o
    # script — lido como vazio, ele reinseriria como novo tudo que já está lá.
    existentes = set()
    for cat in ('backlog', 'pending', 'ok'):
        try:
            rows = PC._pc_load_rows(cat, strict=True)
        except Exception as e:                                    # noqa: BLE001
            sys.exit('ERRO: não deu para ler o banco %s (%s: %s).\n'
                     'Nada foi gravado — sem essa leitura o script não sabe o que já existe.'
                     % (cat, type(e).__name__, e))
        n = 0
        for r in rows:
            tn = str(r.get('Trade Number', '') or '').strip()
            if tn:
                existentes.add(tn)
                n += 1
        print('banco %-8s %d linha(s), %d com Trade Number' % (cat + ':', len(rows), n))

    cad = Cadastro(PC._pc_refdata_by_name(), args.limiar, args.margem)
    print('Reference Data    : %d contraparte(s)' % len(cad.nomes))
    print('-' * 78)

    lote, vistos = [], set()
    pulados_tn, sem_tn, repetidos = 0, 0, 0
    por_nome = {}
    for d in linhas:
        cliente = d.get('Client', '')
        rec, tipo, pct, alt = cad.casa(cliente)
        info = por_nome.setdefault(_norm(cliente), {
            'nome': cliente, 'tipo': tipo, 'pct': pct, 'alt': alt,
            'refdata': str(rec.get('COUNTERPARTY', '') or ''),
            'spn': str(rec.get('SPN', '') or ''), 'linhas': 0, 'inseridas': 0})
        info['linhas'] += 1

        tn = str(d.get('Trade Number', '') or '').strip()
        if not tn:
            sem_tn += 1
            continue
        if tn in existentes:
            pulados_tn += 1
            continue
        if tn in vistos:                 # a mesma linha duas vezes na planilha
            repetidos += 1
            continue
        vistos.add(tn)

        trade_dt = R._parse_date_any(d.get('Trade Date', ''))
        mat_dt = R._parse_date_any(d.get('Maturity Date', ''))
        r = {c: '' for c in PC._PC_COLUMNS}
        for pc in PC._PC_COLUMNS:
            if pc in d:
                r[pc] = d[pc]
        for pc in DATAS:
            dt = R._parse_date_any(d.get(pc, ''))
            if pc in PC._PC_COLUMNS:
                r[pc] = dt.strftime('%d/%m/%Y') if dt else ''
        # Cadastro vence planilha nestes três: é o que liga a operação ao
        # Economic Group, ao Signature Type e ao banker.
        r['SPN'] = str(rec.get('SPN', '') or '')
        r['Client'] = str(rec.get('COUNTERPARTY', '') or '') or cliente
        r['Owner'] = str(rec.get('BANKER', '') or '') or PC._pc_banker_for_spn(r['SPN'])
        r['Economic Group'] = str(rec.get('ECONOMIC GROUP', '') or '')
        r['Signature Type'] = str(rec.get('SIGNATURE TYPE', '') or '')
        if not str(r.get('Pending Status', '') or '').strip():
            # Em branco na planilha, vale a regra do app (prazo × assinatura) —
            # não o vazio, que na tela é uma pendência sem nome.
            r['Pending Status'], r['Status'] = PC._pc_signature_status(rec, trade_dt, mat_dt, '')
        lote.append(r)
        info['inseridas'] += 1

    print('a inserir         : %d' % len(lote))
    print('já nos bancos     : %d (Trade Number existente — pulados)' % pulados_tn)
    print('sem Trade Number  : %d' % sem_tn)
    print('repetidos na planilha: %d' % repetidos)
    contagem = {}
    for r in lote:
        contagem[PC._pc_target_category(r)] = contagem.get(PC._pc_target_category(r), 0) + 1
    print('destino           : %s' % ('  '.join('%s=%d' % kv for kv in sorted(contagem.items()))
                                      or '—'))

    ruins = {t: [] for t in ('fraco', 'ambiguo', 'sem-cadastro', 'sem-nome')}
    semelhantes = []
    for info in por_nome.values():
        if info['tipo'] == 'semelhante':
            semelhantes.append(info)
        elif info['tipo'] in ruins:
            ruins[info['tipo']].append(info)
    print('-' * 78)
    print('nomes distintos   : %d  (exatos: %d)' % (
        len(por_nome), sum(1 for i in por_nome.values() if i['tipo'] == 'exato')))
    if semelhantes:
        print('por SEMELHANÇA (aplicados, ≥%.0f%%):' % args.limiar)
        for i in sorted(semelhantes, key=lambda x: -x['pct'])[:20]:
            print('   %5.1f%%  %-42s → %s' % (i['pct'], i['nome'][:42], i['refdata']))
    for tipo, rotulo in (('ambiguo', 'AMBÍGUOS (SPN em branco)'),
                         ('fraco', 'abaixo do limiar (SPN em branco)'),
                         ('sem-cadastro', 'sem nada parecido (SPN em branco)'),
                         ('sem-nome', 'linha sem Client')):
        if ruins[tipo]:
            print('%s: %d' % (rotulo, len(ruins[tipo])))
            for i in sorted(ruins[tipo], key=lambda x: -x['linhas'])[:15]:
                print('   %-42s %3d linha(s)   %s' % (
                    i['nome'][:42], i['linhas'],
                    ('melhor: %s (%.0f%%)' % (i['alt'], i['pct'])) if i['alt'] else ''))

    destino_rel = args.relatorio or os.path.join(
        os.path.dirname(os.path.abspath(caminho)),
        'match-refdata-%s.csv' % datetime.now().strftime('%Y%m%d-%H%M'))
    with io.open(destino_rel, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';')
        w.writerow(['Nome na planilha', 'Match', '%', 'Nome no Reference Data', 'SPN',
                    'Linhas na planilha', 'A inserir', 'Melhor candidato'])
        for i in sorted(por_nome.values(), key=lambda x: (x['tipo'] != 'exato', -x['linhas'])):
            w.writerow([i['nome'], i['tipo'], '%.1f' % i['pct'], i['refdata'], i['spn'],
                        i['linhas'], i['inseridas'], i['alt']])
    print('-' * 78)
    print('relatório dos nomes: %s' % destino_rel)

    if not args.gravar:
        print('\nNADA FOI GRAVADO. Confira o relatório e rode de novo com --gravar.')
        return 0
    if not lote:
        print('\nnada a inserir.')
        return 0
    PC._pc_upsert_rows(lote)
    print('\nGRAVADO: %d linha(s) inserida(s).' % len(lote))
    return 0


if __name__ == '__main__':
    sys.exit(main())
