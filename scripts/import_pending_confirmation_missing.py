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

  · **O banco de destino sai da coluna `Status` e da `Trade Date`** (mesa,
    22/09/2026):

        Status = Ok  e Trade Date dentro de 12 meses  →  ok
        Status = Ok  e Trade Date anterior a isso     →  backlog
        Status ≠ Ok                                    →  pending

    É a leitura da mesa sobre o arquivo dela. O `_pc_target_category` do app
    responde pelo PENDING STATUS, e por isso não serve para a carga: numa
    planilha inteira de operações já resolvidas ele jogaria no `pending` toda
    linha cujo Pending Status não estivesse na lista de resolvidos do app.
    Quem tem Status Ok e um Pending Status que o app não considera resolvido é
    CONTADO e avisado — a tela deriva o Status do Pending Status, e a
    manutenção das 11:30 vai mover essas linhas para o `pending`.

  · **O nome casa por IGUALDADE primeiro.** Sem match exato, procura o mais
    parecido — e só o aplica se ele passar do limiar (padrão 90%) E ganhar do
    segundo colocado por uma margem (padrão 3 pontos). Abaixo disso, ou empatado,
    o SPN fica EM BRANCO e o nome vai para o relatório. Um SPN parecido não é um
    SPN: ele leva a operação para outra contraparte, com Owner, Economic Group e
    Signature Type de outra contraparte junto, e nada na tela acusa.

  · **A leitura dos bancos é ESTRITA.** Se um dos três não abrir (a instância
    vizinha com a trava, `.wal` de outra versão), o script PARA. Lida como
    "banco vazio", a falha faria ele reinserir como novo tudo que já estava lá.

  · A gravação é um INSERT em lote, UMA abertura por banco, pela camada do app
    (`duckdb_write`: trava exclusiva e semáforo, que é o que a faz conviver com
    a instância do time). Não há o que apagar — só entra Trade Number que não
    existe em banco nenhum —, e o upsert do app faria 3 deletes por linha: numa
    planilha de 80 mil, 240 mil operações no share, uma a uma.

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
import time
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
# Piso do "melhor candidato" do relatório (só informativo — aplicar é só acima
# do limiar). Abaixo disto não é parecido com nada: é o nome menos distante do
# cadastro, e dizê-lo custa uma varredura caractere a caractere do cadastro
# inteiro, por nome.
PISO_RELATORIO = 0.60


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
        # `get_close_matches` compara o nome procurado contra a lista inteira
        # REUSANDO o índice interno do texto procurado (ele fixa a `seq2` uma vez
        # e troca a `seq1`): num arquivo de 80 mil linhas com milhares de nomes
        # distintos, montar um comparador por par — que é o jeito óbvio de
        # escrever isto — custa minutos.
        pares = [(difflib.SequenceMatcher(None, chave, n).ratio() * 100, n)
                 for n in difflib.get_close_matches(chave, self.nomes, n=3,
                                                    cutoff=self.limiar / 100.0)]
        if not pares:
            # Ninguém passou do limiar: o melhor parecido ainda serve ao
            # RELATÓRIO — é o que deixa alguém decidir de fora. Mas com PISO:
            # abaixo de 60% não existe candidato, existe o nome menos distante
            # do cadastro inteiro, que não ajuda ninguém (`PETROBRAS
            # DISTRIBUIDORA` → `CARGILL ALIMENTOS, 57%`). E procurar sem piso
            # custa caro: sem corte o difflib compara caractere a caractere
            # contra TODOS os nomes, e eram 156 s dos 178 s de uma carga de 80
            # mil linhas — o script parecia travado logo depois do cabeçalho.
            melhor = difflib.get_close_matches(chave, self.nomes, n=1, cutoff=PISO_RELATORIO)
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


def _amostra(guardadas, motivo, d, teto):
    """Guarda as primeiras linhas puladas de cada motivo.

    Uma contagem diz QUANTAS ficaram de fora; só a linha diz POR QUÊ. Foi o que
    faltou quando 80 mil linhas viraram mil e quinhentas: o número estava na
    tela e não havia como saber se era Trade Number em branco, fórmula sem valor
    em cache ou a aba errada do arquivo."""
    l = guardadas.setdefault(motivo, [])
    if len(l) < max(0, teto):
        l.append(d)


def insere(categoria, linhas):
    """INSERT em lote, UMA abertura por banco.

    Não passa pelo `_pc_upsert_rows` do app de propósito: ele apaga o Trade
    Number nos TRÊS bancos antes de inserir (é o que move a linha de balde) e
    decide o destino pelo PENDING STATUS. Aqui nada precisa ser apagado — só
    entra Trade Number que não existe em banco nenhum —, o destino é a coluna
    Status, e 80 mil linhas × 3 deletes seriam 240 mil operações no share, uma
    a uma, contra as três aberturas desta função.

    A abertura é a do app (`duckdb_write`): trava exclusiva de arquivo e
    semáforo, que é o que faz a gravação conviver com a instância do time."""
    from apps.pages import routes as R
    from apps.pages.platform import pending_confirmation as PC
    caminho = os.path.join(R._PC_DB_DIR, PC._PC_DBS[categoria])
    PC._pc_ensure_db(caminho)
    cols = ', '.join('"{}"'.format(c) for c in PC._PC_COLUMNS)
    ph = ', '.join('?' for _ in PC._PC_COLUMNS)
    dados = [[r.get(c, '') for c in PC._PC_COLUMNS] for r in linhas]
    with R.duckdb_write(caminho) as con:
        con.executemany('INSERT INTO {} ({}) VALUES ({})'.format(PC._PC_TABLE, cols, ph), dados)


def le_planilha(caminho, erros_xl, aba=None):
    """(linhas, resolvidos, faltando) — cada linha é {coluna da página: texto}."""
    import openpyxl
    wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
    # A aba: a ATIVA é a que estava aberta quando salvaram o arquivo, e num
    # arquivo de várias abas ela pode ser a errada — daí sair uma carga pequena
    # sem erro nenhum. As abas e o tamanho de cada uma vão para a tela; `--aba`
    # escolhe pelo nome.
    print('abas: %s' % '  '.join(
        '%s(%d linhas)' % (s.title, s.max_row or 0) for s in wb.worksheets))
    ws = wb[aba] if aba else wb.active
    print('aba lida: %s' % ws.title)
    it = ws.iter_rows(values_only=True)
    # O cabeçalho nem sempre é a primeira linha (título, logo, linha em branco
    # acima). É cabeçalho a primeira linha que trouxer o Trade Number ou o
    # Client; sem isso, as colunas resolvem por engano contra a linha de título
    # e a planilha inteira sai vazia.
    cab, pulados_topo = None, 0
    for row in it:
        if row is None:
            continue
        nomes = {_norm(v) for v in row if v not in (None, '')}
        if nomes & {_norm(a) for pc in ('Trade Number', 'Client') for a in FONTES[pc]}:
            cab = row
            break
        pulados_topo += 1
    if cab is None:
        return [], {}, sorted(FONTES)
    if pulados_topo:
        print('cabeçalho na linha %d (%d linha(s) acima dele ignoradas)'
              % (pulados_topo + 1, pulados_topo))
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
    ap.add_argument('--aba', default=None, help='nome da aba (padrão: a ativa)')
    ap.add_argument('--amostra', type=int, default=5,
                    help='quantas linhas puladas mostrar de cada motivo (padrão: 5)')
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

    linhas, resolvidos, faltando = le_planilha(
        caminho, getattr(R, '_XL_ERROR_TEXT', set()), args.aba)
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
    print('ANTES da carga, o que os bancos já tinham:')
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
        # O rótulo diz que isto é o ANTES: lido como resultado da carga, ele
        # responde a pergunta errada — foi o que aconteceu na primeira corrida.
        print('  já no banco %-8s %d linha(s), %d com Trade Number'
              % (cat + ':', len(rows), n))

    cad = Cadastro(PC._pc_refdata_by_name(), args.limiar, args.margem)
    print('Reference Data    : %d contraparte(s)' % len(cad.nomes))
    print('-' * 78)

    corte = PC._pc_cutoff_date()
    hoje = datetime.now().date()
    print('corte dos 12 meses: %s' % corte.strftime('%d/%m/%Y'))
    print('-' * 78)

    lote, vistos, amostras = [], set(), {}
    pulados_tn, sem_tn, repetidos, sem_trade_date = 0, 0, 0, 0
    por_nome, por_status, por_pending = {}, {}, {}
    desalinhadas = 0
    t0 = time.time()
    for n_linha, d in enumerate(linhas, 1):
        # Uma linha de vida a cada 10 mil: no share, uma planilha deste tamanho
        # leva minutos, e saída que demora tem de dizer que está viva — parada,
        # ela é indistinguível de travada, e foi lida como o fim da carga.
        if n_linha % 10000 == 0:
            print('   ... %d/%d linhas (%.0f%%), %d a inserir, %.0fs'
                  % (n_linha, len(linhas), 100.0 * n_linha / len(linhas),
                     len(lote), time.time() - t0))
            sys.stdout.flush()
        cliente = d.get('Client', '')
        info = por_nome.setdefault(_norm(cliente), {
            'nome': cliente, 'tipo': '(não consultado)', 'pct': 0.0, 'alt': '',
            'refdata': '', 'spn': '', 'linhas': 0, 'inseridas': 0})
        info['linhas'] += 1

        tn = str(d.get('Trade Number', '') or '').strip()
        if not tn:
            sem_tn += 1
            _amostra(amostras, 'sem Trade Number', d, args.amostra)
            continue
        if tn in existentes:
            pulados_tn += 1
            _amostra(amostras, 'já nos bancos', d, args.amostra)
            continue
        if tn in vistos:                 # a mesma linha duas vezes na planilha
            repetidos += 1
            _amostra(amostras, 'repetido na planilha', d, args.amostra)
            continue
        vistos.add(tn)

        # O de-para só roda para a linha que VAI ENTRAR. Ele varre as ~7 mil
        # contrapartes do cadastro a cada nome novo, e rodá-lo antes dos pulos
        # fazia a planilha inteira pagar o custo para descartar 98% dela — a
        # corrida parecia travada logo depois do cabeçalho.
        rec, tipo, pct, alt = cad.casa(cliente)
        if info['tipo'] == '(não consultado)':
            info.update({'tipo': tipo, 'pct': pct, 'alt': alt,
                         'refdata': str(rec.get('COUNTERPARTY', '') or ''),
                         'spn': str(rec.get('SPN', '') or '')})

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
        r['Aging'] = str((hoje - trade_dt).days) if trade_dt else ''

        # ── O banco de destino (mesa, 22/09/2026) ────────────────────────────
        # Quem decide é a coluna **Status** da planilha, não o Pending Status:
        #   Status = Ok  e Trade Date dentro de 12 meses → ok
        #   Status = Ok  e Trade Date anterior           → backlog
        #   Status ≠ Ok                                   → pending
        # É a leitura da mesa sobre o arquivo dela. O `_pc_target_category` do
        # app responde pelo PENDING STATUS, e por isso não serve aqui: numa
        # planilha inteira de operações já resolvidas ele jogaria no `pending`
        # toda linha cujo Pending Status não estivesse na lista de resolvidos.
        status_ok = _norm(r.get('Status', '')) == 'ok'
        if not trade_dt:
            sem_trade_date += 1
        if not status_ok:
            destino = 'pending'
        elif trade_dt and trade_dt < corte:
            destino = 'backlog'
        else:
            # Sem Trade Date não há como dizer se passou dos 12 meses: fica no
            # `ok`, que é o que a coluna Status afirma, e a contagem acima
            # denuncia quantas são.
            destino = 'ok'
        por_status[r.get('Status', '') or '(vazio)'] = \
            por_status.get(r.get('Status', '') or '(vazio)', 0) + 1
        ps = r.get('Pending Status', '') or '(vazio)'
        por_pending[ps] = por_pending.get(ps, 0) + 1
        # A tela e a manutenção das 11:30 derivam o Status do PENDING STATUS. Uma
        # linha que a planilha diz Ok com um Pending Status que o app não
        # considera resolvido volta para o `pending` na primeira manutenção — e
        # some da fila de resolvidas sem que ninguém tenha mexido nela.
        if status_ok and trade_dt and trade_dt >= corte \
                and not PC._pc_is_ok_status(r.get('Pending Status', '')):
            desalinhadas += 1
        lote.append((destino, r))
        info['inseridas'] += 1

    # A conta FECHA com o total lido, e é impressa fechando: sem ela, "1.530 a
    # inserir" numa planilha de 80 mil não diz se as outras 78 mil foram
    # puladas por um motivo conhecido ou se o script simplesmente não as viu.
    print('=' * 78)
    print('RESULTADO (a planilha tem %d linhas, em %.0fs)' % (len(linhas), time.time() - t0))
    print('  A INSERIR       : %d' % len(lote))
    print('  puladas, já nos bancos: %d (o Trade Number já existe)' % pulados_tn)
    print('  puladas, sem Trade Number: %d' % sem_tn)
    print('  puladas, repetidas na planilha: %d' % repetidos)
    soma = len(lote) + pulados_tn + sem_tn + repetidos
    if soma != len(linhas):
        print('  ATENÇÃO: a conta não fecha (%d ≠ %d) — avise quem mantém o script'
              % (soma, len(linhas)))
    for motivo, exemplos in sorted(amostras.items()):
        if not exemplos:
            continue
        print('  exemplo(s) de "%s":' % motivo)
        for d in exemplos:
            print('     Trade Number=%-18r Client=%-28r Status=%-10r Trade Date=%r' % (
                d.get('Trade Number', ''), str(d.get('Client', ''))[:28],
                d.get('Status', ''), d.get('Trade Date', '')))
    contagem = {}
    for destino, _r in lote:
        contagem[destino] = contagem.get(destino, 0) + 1
    print('destino           : %s' % ('  '.join('%s=%d' % (k, contagem.get(k, 0))
                                                for k in ('ok', 'backlog', 'pending')) or '—'))
    print('Status na planilha: %s' % '  '.join(
        '%s=%d' % kv for kv in sorted(por_status.items(), key=lambda x: -x[1])[:8]))
    print('Pending Status    : %s' % '  '.join(
        '%s=%d' % kv for kv in sorted(por_pending.items(), key=lambda x: -x[1])[:8]))
    if sem_trade_date:
        print('sem Trade Date    : %d  (não dá para dizer se passou dos 12 meses)' % sem_trade_date)
    if desalinhadas:
        # Não é erro deste script: é o que a tela fará com estas linhas amanhã.
        print('\nATENÇÃO: %d linha(s) com Status = Ok e um Pending Status que o app NÃO\n'
              'considera resolvido (%s). A tela deriva o Status do Pending Status,\n'
              'e a manutenção das 11:30 vai mover essas linhas para o banco pending.'
              % (desalinhadas, ', '.join(sorted(PC._PC_OK_STATUSES)) + ' ou "Exception *"'))

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
    for cat in ('ok', 'backlog', 'pending'):
        novas = [r for destino, r in lote if destino == cat]
        if not novas:
            continue
        insere(cat, novas)
        print('GRAVADO %-8s %d linha(s)' % (cat + ':', len(novas)))
    print('\nGRAVADO: %d linha(s) inserida(s).' % len(lote))
    return 0


if __name__ == '__main__':
    sys.exit(main())
