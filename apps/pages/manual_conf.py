# -*- coding: utf-8 -*-
"""Manual Confirmations — a esteira de validação de uma confirmação gerada.

Duas telas leem daqui:

  * **Confirmations Monitor** — os cards Pending OTC / Pending MO / Pending FO,
    com a lista de confirmações paradas em cada etapa;
  * **Track Confirmations** — a tabela inteira, com edição em massa.

E dois DuckDB guardam as linhas: `manual_confirmations_pending` (a esteira ainda
não terminou) e `manual_confirmations_ok` (terminou). Mesma divisão do Pending
Confirmation, e pela mesma razão: a tela abre lendo só o que ainda pede ação.

### A esteira

Uma confirmação nasce quando a operação é mapeada no New Deals, e caminha:

    (gerada) → Pending OTC → Pending MO e/ou Pending FO → Ok

Quem valida cada etapa vem do cadastro `manual-conf-validation`, por **Produto ×
LOB**: Termo e Opção de commodities, FXO e NDF FWD Start passam por OTC e MO;
swap e opção de EDG passam por OTC, MO e FO. `REQUESTED` = precisa validar,
`EXEMPT` = não precisa. Sem linha cadastrada o produto cai no par OTC + MO, que
é o caminho da maioria — e a tela **avisa** que falta cadastro, em vez de deixar
uma confirmação parada num Pending que ninguém sabe de quem é.

MO e FO correm em PARALELO, não em fila: as duas validam a mesma confirmação
depois do OTC, e a linha só sai de pendente quando as duas que foram pedidas
responderam. Encadear as duas atrasaria a segunda por nada.

Um reject de MO ou de FO devolve a confirmação para **Pending OTC** e limpa o
Conferido OTC — é o OTC que refaz o documento. Limpar também as validações já
dadas é de propósito: o documento vai mudar, e um "VALIDADO p/ MO" carimbado
sobre a versão anterior seria um aval que ninguém deu.

### Colunas

As três colunas de carimbo do arquivo original se chamavam todas 'Time Stamp'.
No banco elas não podem: viraram `Time Stamp OTC` / `MO` / `FO`. A tela mostra as
três com o rótulo curto, encostadas em quem validou, que é como se lê.
"""

import logging
import os
import re
import time
import traceback
import unicodedata
from datetime import datetime, timedelta

try:
    import duckdb
except Exception:                                    # pragma: no cover
    duckdb = None

_LOG = logging.getLogger(__name__)

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_DB_DIR = os.path.normpath(os.path.join(_MODULE_DIR, '..', 'static', 'data', 'db'))
_MAPPINGS_DIR = os.path.normpath(os.path.join(_MODULE_DIR, '..', 'static', 'data', 'mappings'))

DBS = {
    'pending': 'manual_confirmations_pending.db',
    'ok': 'manual_confirmations_ok.db',
}
TABLE = 'manual_confirmations'

# As colunas do arquivo, na ordem em que a tela as mostra. `Trade ID` aparecia
# DUAS vezes na lista original (uma cópia colada); coluna repetida não existe num
# banco, e a segunda não acrescentava nada.
COLUMNS = [
    'Pending',
    'Aging Confirmação',
    'Legal Entity',
    'Cliente',
    'E-mail Subject',
    'Produto',
    'LOB',
    'Trade ID',
    'Cetip ID',
    'Moeda',
    'Notional',
    'Data Operação',
    'Data de vencimento',
    'Data de envio validação Registro',
    'Data validação Registro',
    'Data EA enviado p/ cliente',
    'Data Callback',
    'Data envio validação OTC',
    'Conferido OTC',
    'Time Stamp OTC',
    # A justificativa do atraso, quando a mesa carimba fora do prazo. Fica ao
    # lado do carimbo dela, que é onde se procura o porquê.
    'OTC Comments',
    'Data envio validação MO/FO',
    'VALIDADO p/ MO',
    'Time Stamp MO',
    'MO Comments',
    'VALIDADO p/ FO',
    'Time Stamp FO',
    'FO Comments',
    'Enviado p/ cliente (desbloqueado no fep)',
    'Nome fep',
]

# Coluna técnica: o endereço da tela de validação da confirmação daquele trade.
# Fica FORA da tabela — é o destino do botão "Abrir" do Monitor, não um dado que
# alguém lê ou digita. Guardá-la na linha é o que permite ir do item do card ao
# documento sem o Monitor ter de reconstruir, por produto, como se chega lá.
INTERNAL_COLUMNS = ['Confirmation Link']

# O esquema do banco = o que a tela mostra + o que ela usa por baixo.
DB_COLUMNS = COLUMNS + INTERNAL_COLUMNS

# Rótulo curto de cada carimbo. A tela mostra 'Time Stamp' três vezes, do lado
# do VALIDADO correspondente — é assim que a planilha era lida.
COLUMN_LABELS = {
    'Time Stamp OTC': 'Time Stamp',
    'Time Stamp MO': 'Time Stamp',
    'Time Stamp FO': 'Time Stamp',
    # Moeda virou ATIVO: para câmbio segue a moeda (USD), para commodities entra
    # a commodity da confirmação (OLEO, PLATTS…) — é ela que separa os
    # documentos de um mesmo cliente×dia e acha a confirmação EXATA na pasta.
    'Moeda': 'Ativo',
}

# Colunas de data (a tela usa máscara nelas, e o import normaliza para dd/mm/aaaa).
DATE_COLUMNS = [
    'Data Operação', 'Data de vencimento', 'Data de envio validação Registro',
    'Data validação Registro', 'Data EA enviado p/ cliente', 'Data Callback',
    'Data envio validação OTC', 'Conferido OTC', 'Data envio validação MO/FO',
    'VALIDADO p/ MO', 'VALIDADO p/ FO', 'Enviado p/ cliente (desbloqueado no fep)',
]

# Derivadas: recalculadas na leitura, nunca digitadas. Estão no banco porque
# vieram no arquivo, mas quem manda é o cálculo — senão a planilha importada
# discordaria da tela no dia seguinte.
DERIVED_COLUMNS = ['Pending', 'Aging Confirmação']

# A chave da linha. Trade ID identifica a operação; é por ele que o New Deals
# reencontra a linha e que o delete apaga uma só.
KEY_COLUMN = 'Trade ID'

# ── Os tipos de confirmação ─────────────────────────────────────────────────
# UMA lista, quatro consumidores: o **Confirmation Type** do upload do Electronic
# Inventory (`routes._EI_CONFIRMATION_TYPES`), a PASTA em que o documento é
# gravado (`TYPE_FOLDER`), o cadastro Produto × LOB da esteira
# (`manual-conf-validation`) e o dropdown de Produto do Track Confirmations.
# Eram listas escritas à mão, e por isso o cadastro falava 'OPTION' onde a tela
# de upload falava 'FXO' — o mesmo documento com dois nomes, e uma regra de
# validação que nunca casava com a linha que ela deveria reger.
#
# TUDO EM MAIÚSCULO, sempre: o tipo é um código, não um rótulo, e a comparação
# entre as telas é feita sobre ele.
#
# As três páginas de NDF do New Deals (Vanilla, FWD Start, Other Publisher)
# gravam o mesmo Product Type e têm cada uma o seu tipo de confirmação aqui: o
# documento que sai de cada uma é diferente, e um 'NDF' genérico obrigava a
# adivinhar qual delas gerou a linha.
#
# Ela mora aqui, e não no `routes.py`, porque este módulo não importa aquele (o
# contrário seria circular) e porque é aqui que a esteira compara produtos.
CONFIRMATION_TYPES = ('NDF VANILLA', 'NDF FWD START', 'NDF OTHER PUBLISHER',
                      'NDF COMM', 'OPTION COMM', 'FXO',
                      'SWAP', 'SWAP CORPORATE')

# Os três estágios, na ordem em que a esteira anda.
STAGE_OTC, STAGE_MO, STAGE_FO = 'OTC', 'MO', 'FO'
PENDING_OTC = 'Pending OTC'
PENDING_MO = 'Pending MO'
PENDING_FO = 'Pending FO'
PENDING_MOFO = 'Pending MO/FO'
STATUS_OK = 'Ok'

REQUESTED = 'REQUESTED'
EXEMPT = 'EXEMPT'

# Os itens que cada mesa confere antes de carimbar. O servidor manda a LISTA de
# códigos; a frase de cada um é montada na tela, no idioma da aplicação.
#
# **MO e FO conferem só os DADOS ECONÔMICOS** — as operações da Tabela de
# Referência e as datas. Contraparte/CNPJ e a data do CGD são cadastro e
# contrato: quem responde por eles é o OTC, que é quem monta o documento. Pedir
# os quatro itens às três mesas faria duas delas assinarem por uma conferência
# que não é sua, e a assinatura de um checklist é justamente o que se procura
# quando uma confirmação é questionada.
CHECKLIST_ECONOMICO = ('operations', 'dates')
CHECKLIST = {
    STAGE_OTC: ('counterparty', 'cgd') + CHECKLIST_ECONOMICO,
    STAGE_MO: CHECKLIST_ECONOMICO,
    STAGE_FO: CHECKLIST_ECONOMICO,
}


def checklist_for(stage):
    return list(CHECKLIST.get(str(stage or '').upper(), CHECKLIST_ECONOMICO))


# Coluna de carimbo de cada etapa: (a data da validação, o carimbo com quem).
STAGE_COLUMNS = {
    STAGE_OTC: ('Conferido OTC', 'Time Stamp OTC'),
    STAGE_MO: ('VALIDADO p/ MO', 'Time Stamp MO'),
    STAGE_FO: ('VALIDADO p/ FO', 'Time Stamp FO'),
}

# Onde fica a justificativa de atraso de cada mesa. Uma coluna por etapa, e não
# uma só: o atraso do MO não explica o atraso do FO, e um campo compartilhado
# faria a segunda mesa sobrescrever a explicação da primeira.
STAGE_COMMENT_COLUMN = {
    STAGE_OTC: 'OTC Comments',
    STAGE_MO: 'MO Comments',
    STAGE_FO: 'FO Comments',
}

# ── O SLA de cada mesa ──────────────────────────────────────────────────────
# Dias ÚTEIS a contar da DATA DA OPERAÇÃO (trade date), não da data em que a
# confirmação foi gerada: o prazo é do trade, e gerar o documento com atraso não
# compra tempo novo. Úteis pelo mesmo calendário ANBIMA do aging — o prazo só
# corre em dia de pregão.
#
# As mesas correm em PARALELO depois do OTC, e por isso os prazos não se somam:
# D+4 do MO e D+6 do FO são os dois contados do mesmo trade date.
SLA_BIZDAYS = {
    STAGE_OTC: 3,
    STAGE_MO: 4,
    STAGE_FO: 6,
}


def sla_deadline(row, stage):
    """A data limite daquela etapa: trade date + N dias úteis. None sem data."""
    d = parse_date(row.get('Data Operação'))
    n = SLA_BIZDAYS.get(str(stage or '').upper())
    if not d or n is None:
        return None
    return _add_bizdays(d, n)


def sla_state(row, stage, hoje=None):
    """Como aquela etapa está contra o prazo.

    Devolve `{'deadline', 'left', 'level'}`. `left` são os dias ÚTEIS que faltam
    (negativo = passou), e `level` é a luz:

      * `ok`   — folga de 2 dias úteis ou mais
      * `warn` — falta 1 dia ou é hoje
      * `late` — o prazo passou

    A etapa JÁ VALIDADA sai como `done`: o prazo dela deixou de correr, e mantê-la
    vermelha faria a tela cobrar um trabalho que já foi feito.
    """
    stage = str(stage or '').upper()
    col_data, _col_stamp = STAGE_COLUMNS.get(stage, ('', ''))
    deadline = sla_deadline(row, stage)
    if col_data and str(row.get(col_data, '') or '').strip():
        return {'deadline': deadline, 'left': None, 'level': 'done'}
    if not deadline:
        return {'deadline': None, 'left': None, 'level': 'ok'}
    hoje = hoje or datetime.now().date()
    if hoje > deadline:
        left = -_bizdays_between(deadline, hoje)
    else:
        left = _bizdays_between(hoje, deadline)
    return {'deadline': deadline, 'left': left,
            'level': 'late' if left < 0 else ('warn' if left <= 1 else 'ok')}


# As luzes na ordem da gravidade. É por ela que o grupo escolhe a sua: o item do
# Monitor é UM documento cobrindo várias operações, e vale a mais apertada.
_SLA_ORDEM = ('done', 'ok', 'warn', 'late')


def sla_breached(row, stage, hoje=None):
    """A validação desta etapa está FORA DO PRAZO? É o que torna a justificativa
    obrigatória — a pergunta é feita no instante do carimbo, não depois."""
    return sla_state(row, stage, hoje)['level'] == 'late'


def stage_history(row):
    """O histórico das três etapas da linha: quando e por quem.

    É o que a tela de validação mostra no topo — e é o que responde "quem
    conferiu isto?" sem abrir o Track.
    """
    out = []
    for stage in (STAGE_OTC, STAGE_MO, STAGE_FO):
        col_data, col_stamp = STAGE_COLUMNS[stage]
        stamp = str(row.get(col_stamp, '') or '').strip()
        out.append({
            'stage': stage,
            'date': str(row.get(col_data, '') or '').strip(),
            'stamp': stamp,
            # Um reject carimba 'REJEITADO <quando> · <quem>' na coluna da mesa
            # que devolveu, e a data ao lado é limpa — sem esta marca a linha
            # apareceria simplesmente como "não validada", perdendo o que houve.
            'rejected': stamp.upper().startswith('REJEITADO'),
        })
    return out


# =============================================================================
# Normalizações
# =============================================================================

def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]', '', s.lower())


def upper_norm(v):
    """MAIÚSCULO com o espaço preservado ('NDF COMM').

    Não é o `norm()`: aquele minusculiza e cola tudo ('ndfcomm'), e comparar
    nome de produto com nome de pasta exige o espaço de volta.
    """
    t = unicodedata.normalize('NFKD', str(v or ''))
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', t).strip().upper()


def parse_date(v):
    """dd/mm/aaaa, aaaa-mm-dd, dd-mm-aaaa ou datetime → date. None se não for data."""
    if v in (None, ''):
        return None
    if isinstance(v, datetime):
        return v.date()
    if hasattr(v, 'year') and hasattr(v, 'month'):
        return v
    s = str(v).strip()
    if not s:
        return None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def fmt_date(d):
    return d.strftime('%d/%m/%Y') if d else ''


def stamp_now(sid):
    """O carimbo de uma validação: quando e QUEM.

    Os dois juntos num campo só, de propósito — separá-los deixaria a tela com
    uma coluna de hora sem dono, e é o dono que se procura quando uma validação
    é questionada.
    """
    return '%s · %s' % (datetime.now().strftime('%d/%m/%Y %H:%M'), str(sid or '').strip() or '—')


# =============================================================================
# O cadastro da esteira
# =============================================================================

def _mapping_rows(key):
    """Cadastro de /mapping lido do disco a cada chamada — edição na tela vale na
    próxima leitura, sem restart. Importar `routes` daqui seria circular."""
    import json
    try:
        with open(os.path.join(_MAPPINGS_DIR, '%s.json' % key), encoding='utf-8') as fh:
            rows = json.load(fh)
    except Exception:
        return []
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def validation_rules():
    """(produto, lob) → {'OTC': bool, 'MO': bool, 'FO': bool}, do cadastro.

    A busca é por Produto **e** LOB, caindo para a linha do produto com LOB em
    branco. LOB em branco é coringa: a maioria dos produtos valida igual em toda
    LOB, e obrigar uma linha por LOB faria a tela pedir cadastro a cada LOB nova.

    Os dois lados da comparação passam pelo `confirmation_type()`: o cadastro é
    feito com os nomes do Electronic Inventory ('FXO'), e as linhas do banco
    carregam a nomenclatura de quem as criou ('OPTION', 'NDF' × COMMODITY). Sem o
    tradutor, cada uma dessas linhas caía no DEFAULT_RULE — com um aviso de
    "produto sem cadastro" para um produto que estava cadastrado.
    """
    exact, wildcard = {}, {}
    for r in _mapping_rows('manual-conf-validation'):
        prod = norm(confirmation_type(r.get('PRODUCT'), r.get('LOB')))
        if not prod:
            continue
        rule = {stage: norm(r.get(stage)).startswith('requested')
                for stage in (STAGE_OTC, STAGE_MO, STAGE_FO)}
        lob = norm(r.get('LOB'))
        (exact if lob else wildcard)[(prod, lob) if lob else prod] = rule
    return exact, wildcard


# Sem cadastro, o caminho da maioria: OTC + MO. Não é um palpite solto — é o que
# vale para termo e opção de commodities, FXO e NDF FWD Start, que são os quatro
# produtos que alimentam esta tela hoje. A tela avisa quando caiu aqui.
DEFAULT_RULE = {STAGE_OTC: True, STAGE_MO: True, STAGE_FO: False}


def rule_for(produto, lob, rules=None):
    """(regra, achou_cadastro) do par Produto × LOB."""
    exact, wildcard = rules if rules is not None else validation_rules()
    prod, l = norm(confirmation_type(produto, lob)), norm(lob)
    if (prod, l) in exact:
        return exact[(prod, l)], True
    if prod in wildcard:
        return wildcard[prod], True
    return dict(DEFAULT_RULE), False


# =============================================================================
# Derivação: em que etapa a confirmação está
# =============================================================================

def _filled(row, col):
    return bool(str(row.get(col, '') or '').strip())


def pending_stage(row, rules=None):
    """Em que etapa a confirmação está, das colunas de validação.

    Deriva do estado, não de um campo digitado: uma coluna 'Pending' escrita à
    mão discordaria das datas ao lado dela no primeiro reject, e a tela mostraria
    uma etapa que já passou.
    """
    rule, _found = rule_for(row.get('Produto'), row.get('LOB'), rules)

    if rule[STAGE_OTC] and not _filled(row, 'Conferido OTC'):
        return PENDING_OTC

    falta = []
    if rule[STAGE_MO] and not _filled(row, 'VALIDADO p/ MO'):
        falta.append(PENDING_MO)
    if rule[STAGE_FO] and not _filled(row, 'VALIDADO p/ FO'):
        falta.append(PENDING_FO)
    if len(falta) == 2:
        return PENDING_MOFO          # as duas ao mesmo tempo, não em fila
    if falta:
        return falta[0]
    return STATUS_OK


# Feriados ANBIMA, lidos do MESMO arquivo que o resto do app usa
# (`static/data/anbima.json`). Importar o `routes`, que já tem o carregador,
# seria circular — e uma segunda lista de feriados envelheceria sozinha, então o
# que se repete aqui é só a leitura, não o dado.
_ANBIMA = {'feriados': None}


def _anbima_holidays():
    if _ANBIMA['feriados'] is None:
        import json
        try:
            path = os.path.normpath(os.path.join(_MODULE_DIR, '..', 'static', 'data', 'anbima.json'))
            with open(path, encoding='utf-8') as fh:
                _ANBIMA['feriados'] = {d['date'] for d in (json.load(fh) or []) if d.get('date')}
        except Exception:
            # Sem o arquivo o aging vira a contagem só de dias de semana, que
            # erra por feriado mas não some da tela nem estoura o request.
            _LOG.warning('[manual-conf] anbima.json não pôde ser lido; o aging '
                         'vai contar dias úteis sem os feriados')
            _ANBIMA['feriados'] = set()
    return _ANBIMA['feriados']


def _bizdays_between(inicio, fim):
    """Dias ÚTEIS de `inicio` (exclusive) até `fim` (inclusive), calendário ANBIMA.

    Contagem por iteração e não por fórmula: a janela do aging é de dias a poucas
    semanas, e uma fórmula de semanas × 5 ainda precisaria varrer os feriados do
    intervalo. Data futura devolve 0 — negativo num "há quantos dias" não
    significa nada.
    """
    if not inicio or not fim or fim <= inicio:
        return 0
    feriados = _anbima_holidays()
    n, d = 0, inicio
    while d < fim:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.strftime('%Y-%m-%d') not in feriados:
            n += 1
    return n


def _add_bizdays(inicio, n):
    """`inicio` + n dias ÚTEIS (ANBIMA). n = 0 devolve a própria data."""
    if not inicio:
        return None
    feriados = _anbima_holidays()
    d, restam = inicio, int(n or 0)
    while restam > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.strftime('%Y-%m-%d') not in feriados:
            restam -= 1
    return d


def aging(row):
    """Dias ÚTEIS desde que a confirmação foi enviada para validação do OTC.

    É a idade da PENDÊNCIA, não da operação: uma operação de três meses atrás
    cuja confirmação saiu ontem não está atrasada. Sem a data de envio, cai na
    data da operação, que é o que a planilha antiga tinha.

    ÚTEIS pelo calendário ANBIMA, não corridos: a esteira só anda em dia de
    pregão, e contar sábado, domingo e feriado fazia uma confirmação de
    sexta-feira nascer com três dias de atraso na segunda — o vermelho do card
    aparecia sem ninguém ter deixado de trabalhar.
    """
    d = parse_date(row.get('Data envio validação OTC')) or parse_date(row.get('Data Operação'))
    if not d:
        return None
    return _bizdays_between(d, datetime.now().date())


def refresh_derived(row, rules=None):
    """Recalcula as duas derivadas na linha, no lugar."""
    row['Pending'] = pending_stage(row, rules)
    a = aging(row)
    row['Aging Confirmação'] = str(a) if a is not None else ''
    return row


def target_category(row):
    return 'ok' if row.get('Pending') == STATUS_OK else 'pending'


# =============================================================================
# Persistência
# =============================================================================

def db_path(category):
    return os.path.join(_DB_DIR, DBS[category])


def ensure_db(path):
    """Cria o banco vazio se ele não existir e ACRESCENTA as colunas que faltam.

    A segunda parte é o que dispensa um script de migração: o banco fica fora do
    repositório (`apps/static/data/db/` está no .gitignore), então a instância do
    time tem o dela desde antes de a coluna existir. Sem isto, o primeiro
    `INSERT` — que lista as colunas explicitamente — falharia com "column not
    found" e a tela inteira sumiria depois de um pull.

    `ADD COLUMN IF NOT EXISTS` é idempotente, então isto pode rodar a cada
    leitura sem custo.
    """
    if duckdb is None:
        return
    novo = not os.path.isfile(path)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # close() em finally: uma conexão vazada segura o lock de escrita do
        # DuckDB até o processo morrer, e aí a tela some para TODOS.
        con = duckdb.connect(path)
        try:
            cols = ', '.join('"{}" VARCHAR'.format(c) for c in DB_COLUMNS)
            con.execute('CREATE TABLE IF NOT EXISTS {} ({})'.format(TABLE, cols))
            existentes = {r[1] for r in con.execute(
                "PRAGMA table_info('{}')".format(TABLE)).fetchall()}
            for c in DB_COLUMNS:
                if c not in existentes:
                    # DDL sobre IDENTIFICADOR do próprio código (DB_COLUMNS é
                    # constante de módulo): nome de coluna não pode ser bindado,
                    # e é o único caso em que se monta a string.
                    con.execute('ALTER TABLE {} ADD COLUMN IF NOT EXISTS "{}" VARCHAR'
                                .format(TABLE, c))
                    _LOG.info('[manual-conf] coluna %r acrescentada a %s', c, path)
        finally:
            con.close()
        if novo:
            _LOG.info('[manual-conf] banco vazio criado em %s', path)
    except Exception:
        _LOG.warning('[manual-conf] não consegui preparar %s:\n%s', path, traceback.format_exc())


def load_rows(category):
    path = db_path(category)
    ensure_db(path)
    if duckdb is None or not os.path.isfile(path):
        return []
    try:
        con = duckdb.connect(path, read_only=True)
    except Exception:
        _LOG.warning('[manual-conf] não consegui abrir %s', path)
        return []
    try:
        cols = ', '.join('"{}"'.format(c) for c in DB_COLUMNS)
        raw = con.execute('SELECT {} FROM {}'.format(cols, TABLE)).fetchall()
    except Exception:
        _LOG.warning('[manual-conf] consulta falhou em %s:\n%s', path, traceback.format_exc())
        return []
    finally:
        con.close()
    rules = validation_rules()
    out = []
    for r in raw:
        row = {c: ('' if v is None else str(v)) for c, v in zip(DB_COLUMNS, r)}
        refresh_derived(row, rules)
        out.append(row)
    return out


def load_all():
    """As linhas dos dois bancos, com a etapa recalculada.

    Uma linha pode estar fisicamente no banco errado — ela só migra quando é
    gravada —, então a categoria de exibição vem do `Pending` recalculado, não do
    arquivo em que a linha estava.
    """
    return load_rows('pending') + load_rows('ok')


def _write_exec(category, ops):
    """Roda (sql, params) numa conexão de escrita, com retentativa: as leituras
    read-only da tela são rápidas mas frequentes, e o DuckDB recusa a escrita
    enquanto uma delas está aberta."""
    if duckdb is None:
        return False
    path = db_path(category)
    ensure_db(path)
    for attempt in range(6):
        try:
            con = duckdb.connect(path)
        except Exception:
            time.sleep(0.05 * (2 ** attempt))
            continue
        try:
            for sql, params in ops:
                con.execute(sql, params)
            return True
        except Exception:
            _LOG.warning('[manual-conf] escrita falhou em %s:\n%s', category,
                         traceback.format_exc())
            return False
        finally:
            con.close()
    _LOG.warning('[manual-conf] desisti da escrita (banco ocupado) em %s', category)
    return False


def _delete_key(category, key):
    if not key:
        return
    _write_exec(category, [('DELETE FROM {} WHERE trim("{}") = ?'.format(TABLE, KEY_COLUMN),
                            [str(key).strip()])])


def _insert_into(category, row):
    # Colunas explícitas: um banco antigo com colunas a mais continua aceitando o
    # INSERT (elas ficam NULL); um VALUES posicional quebraria.
    cols = ', '.join('"{}"'.format(c) for c in DB_COLUMNS)
    ph = ', '.join('?' for _ in DB_COLUMNS)
    _write_exec(category, [('INSERT INTO {} ({}) VALUES ({})'.format(TABLE, cols, ph),
                            [str(row.get(c, '') or '') for c in DB_COLUMNS])])


def upsert_row(row):
    """Grava uma linha: recalcula as derivadas, apaga a chave dos DOIS bancos e
    insere no que ela agora pertence. É isso que move a linha pending→ok quando a
    esteira fecha (e de volta, quando um reject a reabre)."""
    refresh_derived(row)
    key = str(row.get(KEY_COLUMN, '') or '').strip()
    target = target_category(row)
    for cat in ('pending', 'ok'):
        _delete_key(cat, key)
    _insert_into(target, row)
    return target


def delete_row(key):
    for cat in ('pending', 'ok'):
        _delete_key(cat, key)


def find_row(key):
    """A linha de um Trade ID, olhando os dois bancos."""
    k = str(key or '').strip()
    if not k:
        return None
    for r in load_all():
        if str(r.get(KEY_COLUMN, '') or '').strip() == k:
            return r
    return None


def blank_row(**kw):
    row = {c: '' for c in DB_COLUMNS}
    row.update({k: v for k, v in kw.items() if k in row})
    return refresh_derived(row)


# =============================================================================
# As transições da esteira
# =============================================================================

def mark_generated(key, when=None, link=None, subject=None):
    """Confirmação gerada: carimba a Data envio validação OTC.

    A data só é carimbada se ainda estiver em branco — regerar o documento não
    reinicia a idade da pendência, senão uma confirmação parada há duas semanas
    volta a parecer nova a cada tentativa.

    O **link**, ao contrário, é sempre reescrito: ele aponta para o documento
    ATUAL, e um endereço da versão anterior levaria quem valida ao papel errado.
    """
    row = find_row(key)
    if row is None:
        return None
    if link:
        row['Confirmation Link'] = str(link)
    if subject and not _filled(row, 'E-mail Subject'):
        row['E-mail Subject'] = str(subject)
    if not _filled(row, 'Data envio validação OTC'):
        row['Data envio validação OTC'] = fmt_date(when or datetime.now().date())
    upsert_row(row)
    return row


class SlaCommentRequired(Exception):
    """Carimbo fora do prazo sem justificativa.

    Exceção, e não um `return None`: quem chama precisa distinguir "não achei a
    linha" de "achei e recusei", para a tela pedir o comentário em vez de dizer
    que a confirmação não existe.
    """


def mark_validated(key, stage, sid, comment=''):
    """Valida uma etapa: carimba a data, o horário e o SPN de quem validou.

    Ao sair do OTC, carimba também a Data envio validação MO/FO — é o mesmo
    instante, e deixar quem valida preencher isso à mão faria a idade da segunda
    etapa nascer errada.

    Passado o prazo da mesa (ver `SLA_BIZDAYS`), o `comment` é OBRIGATÓRIO e vai
    para a coluna daquela etapa. A checagem é feita aqui, e não só na tela: a
    tela é onde se pede, mas o endpoint é onde se garante — e o motivo do atraso
    é justamente o que alguém vai procurar depois.
    """
    row = find_row(key)
    if row is None:
        return None
    comment = str(comment or '').strip()
    if sla_breached(row, stage) and not comment:
        raise SlaCommentRequired(stage)
    if comment:
        col = STAGE_COMMENT_COLUMN.get(str(stage or '').upper())
        if col:
            row[col] = comment
    hoje = fmt_date(datetime.now().date())
    if stage == STAGE_OTC:
        row['Conferido OTC'] = hoje
        row['Time Stamp OTC'] = stamp_now(sid)
        if not _filled(row, 'Data envio validação MO/FO'):
            row['Data envio validação MO/FO'] = hoje
    elif stage == STAGE_MO:
        row['VALIDADO p/ MO'] = hoje
        row['Time Stamp MO'] = stamp_now(sid)
    elif stage == STAGE_FO:
        row['VALIDADO p/ FO'] = hoje
        row['Time Stamp FO'] = stamp_now(sid)
    else:
        return None
    upsert_row(row)
    return row


def reject(key, stage, sid, comment):
    """Reject de MO ou FO: a confirmação volta para Pending OTC.

    Limpa o Conferido OTC **e** as validações já dadas: o documento vai ser
    refeito, e um 'VALIDADO p/ MO' carimbado sobre a versão anterior seria um
    aval que ninguém deu à versão nova. O carimbo do reject fica na coluna do
    estágio que rejeitou, para a tela poder dizer quem devolveu e quando.
    """
    row = find_row(key)
    if row is None:
        return None
    for col in ('Conferido OTC', 'Time Stamp OTC', 'VALIDADO p/ MO', 'Time Stamp MO',
                'VALIDADO p/ FO', 'Time Stamp FO', 'Data envio validação MO/FO'):
        row[col] = ''
    row['Time Stamp %s' % stage] = 'REJEITADO %s' % stamp_now(sid)
    upsert_row(row)
    return row


# =============================================================================
# Onde o documento foi gravado
# =============================================================================

# Tipo de confirmação → PASTA do Electronic Inventory. Fonte única do nome da
# pasta, para os dois jeitos de um documento chegar lá: o `save` que o app faz ao
# gerar a confirmação e o **upload manual** da tela de Electronic Inventory.
#
# Eles gravavam em pastas DIFERENTES para o mesmo produto: o upload usava o nome
# do tipo cru ('FXO') e o app um nome bonito ('FX Options'). O Monitor procura
# PDF só onde o app grava, então a confirmação subida à mão ficava invisível para
# ele, com o arquivo lá no share.
#
# **A pasta É o código do tipo**, e é por isso que este mapa é a identidade: o
# share já está cheio de pastas com o nome do tipo ('NDF COMM'), que é como o
# upload manual sempre gravou, e é esse o nome que o time reconhece. Ter um
# segundo nome só para a escrita do app recriava a divergência pela outra ponta.
# O mapa continua existindo — em vez de o chamador escrever a string — porque é
# ele que garante que os quatro consumidores digam a mesma coisa.
TYPE_FOLDER = {t: t for t in CONFIRMATION_TYPES}

# As pastas que o app usou ANTES de a pasta virar o código do tipo. São só de
# LEITURA: o documento novo vai para o nome do tipo, mas tudo o que já foi
# gravado continua nelas, e o Monitor tem de achar. Sem isto, unificar o nome
# apagaria da tela todas as confirmações antigas — com os arquivos intactos no
# share, que é a pior forma de sumir.
TYPE_FOLDER_LEGACY = {
    'NDF VANILLA':         ('NDF Vanilla',),
    'NDF FWD START':       ('NDF FWD Start',),
    'NDF OTHER PUBLISHER': ('NDF Other Publisher', 'OTHER PUBLISHER'),
    'NDF COMM':            ('NDF Commodities',),
    'OPTION COMM':         ('Commodities Options',),
    'FXO':                 ('FX Options',),
    'SWAP':                ('Swap',),
    'SWAP CORPORATE':      ('Swap Corporate',),
}

# Produto (o que está gravado na linha) → pasta. É o TYPE_FOLDER mais os apelidos
# que o New Deals usa ao criar a linha ('OPTION' é o nome dele para o FXO) e o
# nome antigo do Other Publisher, que ficou em cadastros já salvos.
PRODUCT_FOLDER = dict(TYPE_FOLDER, **{
    'OPTION':          'FXO',
    'OTHER PUBLISHER': 'NDF OTHER PUBLISHER',
})

_MONTH_EN = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May',
             6: 'June', 7: 'July', 8: 'August', 9: 'September', 10: 'October',
             11: 'November', 12: 'December'}


def _product_folder(row):
    """A subpasta de produto do Electronic Inventory para a linha.

    Duas nomenclaturas convivem no banco: a do New Deals ('NDF COMM' × CEM) e a
    da planilha legada ('NDF' × COMMODITY). A pasta é a mesma — e resolver só a
    primeira deixava as confirmações antigas 'sem PDF' com o PDF lá.
    """
    # norm() aqui NÃO serve: ela minusculiza e cola tudo ('ndfcomm'), e nem o
    # lookup nem os startswith casariam. A pasta compara em MAIÚSCULO com espaço.
    prod = upper_norm(row.get('Produto'))
    lob = upper_norm(row.get('LOB'))
    direto = PRODUCT_FOLDER.get(prod)
    if direto:
        return direto
    if prod.startswith('NDF FWD'):
        return 'NDF FWD START'
    if 'SWAP' in prod:
        return 'SWAP CORPORATE' if 'CORP' in prod else 'SWAP'
    e_comm = 'COMMODIT' in lob or 'COMM' in prod
    if prod.startswith('NDF'):
        # NDF que não é de mercadoria é o termo de moeda das páginas de Vanilla /
        # Other Publisher. Antes isto devolvia None, e a linha ficava sem pasta —
        # ou seja, sem chance de o Monitor achar o documento dela.
        return 'NDF COMM' if e_comm else 'NDF VANILLA'
    if prod.startswith(('OPCAO', 'OPTION', 'OPT')):
        return 'OPTION COMM' if e_comm else 'FXO'
    return None


# Pasta → tipo de confirmação, o inverso exato do TYPE_FOLDER. A pasta JÁ é a
# classificação do produto (é ela que separa termo de opção e câmbio de
# mercadoria), então o tipo sai dela em vez de repetir a mesma árvore de decisão
# com outro nome — duas respostas para a mesma pergunta é exatamente o que
# separou 'OPTION' de 'FXO'.
_FOLDER_TYPE = {pasta: tipo for tipo, pasta in TYPE_FOLDER.items()}


def confirmation_type(produto, lob=''):
    """O tipo de confirmação da linha, um dos `CONFIRMATION_TYPES`.

    É o tradutor entre as nomenclaturas que convivem no banco ('OPTION' do New
    Deals, 'NDF' × COMMODITY da planilha legada, 'NDF FWD START') e o nome único
    que as três telas mostram. Produto que não se sabe traduzir volta como veio,
    em maiúsculo: melhor um nome estranho na tela do que um produto reclassificado
    à força para a regra de validação errada.
    """
    prod = upper_norm(produto)
    if not prod:
        return ''
    # A pasta vem ANTES do nome já canônico, e a ordem importa: a linha legada
    # 'NDF' × COMMODITY tem um produto que POR ACASO está na lista, e devolvê-lo
    # direto a classificaria como termo de moeda — que é outro documento, outra
    # pasta e outra regra de validação.
    folder = _product_folder({'Produto': produto, 'LOB': lob})
    if folder in _FOLDER_TYPE:
        return _FOLDER_TYPE[folder]
    if prod in CONFIRMATION_TYPES:
        return prod
    if 'SWAP' in prod:
        return 'SWAP CORPORATE' if 'CORP' in prod else 'SWAP'
    if prod.startswith('NDF'):
        return 'NDF VANILLA'
    return prod


def confirmation_folder(row):
    """(cliente, caminho relativo da pasta) do documento daquela confirmação.

    A pasta é DERIVADA da própria linha — cliente, produto e data da operação —,
    e não de um campo gravado. É isso que faz o botão *Abrir* funcionar para as
    confirmações que já existiam antes de o carimbo existir: um link guardado só
    aparece nas que foram salvas depois, e essas são justamente as que ninguém
    precisa procurar.

    (None, None) quando falta o que forma o caminho.

    É a pasta de ESCRITA — a do nome do tipo. Para procurar um documento use
    `confirmation_folders`, que devolve também as pastas antigas.
    """
    cliente, rels = confirmation_folders(row)
    return (cliente, rels[0]) if rels else (None, None)


def confirmation_folders(row):
    """(cliente, [caminhos relativos]) onde o documento daquela linha pode estar.

    O primeiro é o de sempre — a pasta com o nome do tipo, que é onde o app
    grava. Os demais são as pastas de nome antigo (`TYPE_FOLDER_LEGACY`), que
    continuam cheias no share: quem procura o PDF tem de olhar nas duas, ou a
    unificação do nome faria as confirmações de antes sumirem da tela.

    (None, []) quando falta o que forma o caminho.
    """
    cliente = str(row.get('Cliente', '') or '').strip()
    produto = _product_folder(row)
    d = parse_date(row.get('Data Operação'))
    if not (cliente and produto and d):
        return None, []
    prefixo = ['Confirmations', '%04d' % d.year,
               '%02d. %s' % (d.month, _MONTH_EN[d.month]), '%02d' % d.day]
    pastas = [produto] + [p for p in TYPE_FOLDER_LEGACY.get(produto, ()) if p != produto]
    return cliente, ['/'.join(prefixo + [p]) for p in pastas]


# =============================================================================
# O que o Monitor mostra
# =============================================================================

# Um card por etapa, na ordem da esteira.
MONITOR_STAGES = (
    (STAGE_OTC, PENDING_OTC),
    (STAGE_MO, PENDING_MO),
    (STAGE_FO, PENDING_FO),
)

# Os campos que o item da lista do card mostra. É o mínimo para reconhecer a
# confirmação sem abrir: quando, de quem, o quê.
MONITOR_FIELDS = ('Data Operação', 'Cliente', 'Produto', 'LOB', 'Moeda',
                  'Trade ID', 'Aging Confirmação')


# O que define UMA confirmação. O documento é emitido por contraparte × produto ×
# data de negociação (e a LOB acompanha), cobrindo todas as operações do grupo —
# então o Monitor tem de mostrar UM item por documento, não um por trade. Uma
# lista com dez linhas do mesmo cliente no mesmo dia é uma confirmação só, e
# validar dez vezes o mesmo papel é o erro que isso evita.
# O Ativo entra na chave: OLEO e PLATTS do mesmo cliente no mesmo dia são DUAS
# confirmações, com dois documentos — agrupá-las faria um Validar dar baixa nas
# duas de uma vez.
GROUP_FIELDS = ('LOB', 'Cliente', 'Produto', 'Data Operação', 'Moeda')


def group_key(row):
    return tuple(norm(row.get(f)) for f in GROUP_FIELDS)


def _aging_int(v):
    s = str(v or '').strip()
    return int(s) if s.lstrip('-').isdigit() else 0


def monitor_payload(docs_for=None):
    """Os cards do Monitor: cada etapa com a sua lista de CONFIRMAÇÕES.

    'Pending MO/FO' entra nos DOIS cards — a confirmação está parada de verdade
    nas duas mesas, e mostrá-la só num deles esconderia trabalho da outra.

    `docs_for(row)` é injetado pela camada de rotas (ela é quem sabe resolver a
    pasta do Electronic Inventory); sem ele o item sai sem documentos, e o card
    continua mostrando a pendência — que existe do mesmo jeito.
    """
    rows = load_rows('pending')
    rules = validation_rules()
    cards, sem_cadastro = [], set()
    for stage, label in MONITOR_STAGES:
        grupos = {}
        for r in rows:
            rule, found = rule_for(r.get('Produto'), r.get('LOB'), rules)
            if not found:
                # O aviso nomeia o TIPO, que é o nome que a pessoa vai procurar
                # no cadastro — dizer 'OPTION' mandaria procurar por uma opção
                # que a tela de mapping não oferece mais.
                sem_cadastro.add('%s · %s' % (
                    confirmation_type(r.get('Produto'), r.get('LOB')) or '—',
                    str(r.get('LOB') or '—')))
            if not rule[stage]:
                continue
            p = r.get('Pending')
            if p != label and not (p == PENDING_MOFO and stage in (STAGE_MO, STAGE_FO)):
                continue
            gk = group_key(r)
            item = grupos.get(gk)
            if item is None:
                item = {k: r.get(k, '') for k in MONITOR_FIELDS}
                # `Produto` continua CRU no item — é ele que resolve a pasta do
                # Electronic Inventory em /docs. `Tipo` é o nome que a tela
                # mostra, o mesmo do cadastro e do Confirmation Type do upload.
                item['Tipo'] = confirmation_type(r.get('Produto'), r.get('LOB'))
                item.update({'stage': stage, 'keys': [], 'trades': [], 'docs': []})
                # O prazo é da ETAPA do card (OTC D+3, MO D+4, FO D+6 do trade
                # date). O item guarda a luz e os dias que faltam; a frase é
                # montada na tela, no idioma da aplicação.
                st = sla_state(r, stage)
                item['sla'] = {'level': st['level'], 'left': st['left'],
                               'deadline': fmt_date(st['deadline'])}
                # Os documentos são resolvidos UMA vez por grupo: eles são do
                # grupo, não do trade — a pasta é a mesma para todos eles.
                if docs_for:
                    item['docs'] = docs_for(r) or []
                grupos[gk] = item
            k = str(r.get(KEY_COLUMN, '') or '')
            if k:
                item['keys'].append(k)
                item['trades'].append(k)
            # A idade do grupo é a da operação que espera há MAIS tempo: é ela
            # que diz há quanto tempo aquele documento está parado.
            if _aging_int(r.get('Aging Confirmação')) > _aging_int(item.get('Aging Confirmação')):
                item['Aging Confirmação'] = r.get('Aging Confirmação', '')
            # E o prazo do grupo é o da operação MAIS APERTADA. O documento é um
            # só e cobre todas elas: se uma já estourou, o grupo inteiro está
            # atrasado — mostrar o prazo da mais folgada esconderia isso.
            st = sla_state(r, stage)
            atual = item.get('sla') or {}
            if _SLA_ORDEM.index(st['level']) > _SLA_ORDEM.index(atual.get('level', 'done')):
                item['sla'] = {'level': st['level'], 'left': st['left'],
                               'deadline': fmt_date(st['deadline'])}
        itens = list(grupos.values())
        for it in itens:
            it['count'] = len(it['keys'])
            # `key` continua existindo para quem só precisa de uma referência.
            it['key'] = it['keys'][0] if it['keys'] else ''
        # Mais antigo primeiro: é a fila, e quem espera há mais tempo vem antes.
        itens.sort(key=lambda i: -_aging_int(i.get('Aging Confirmação')))
        cards.append({'stage': stage, 'label': label,
                      'count': len(itens),
                      'trades': sum(i['count'] for i in itens),
                      'items': itens})
    # A frase do aviso é montada NA TELA, no idioma selecionado — o servidor só
    # diz QUAIS produtos estão sem cadastro. `warnings` (em PT) permanece para
    # qualquer consumidor antigo.
    faltantes = sorted(sem_cadastro)
    warnings = []
    if faltantes:
        warnings.append(
            'Sem cadastro de validação para: ' + ', '.join(faltantes) +
            '. Enquanto isso essas confirmações seguem por OTC e MO.')
    return {'cards': cards, 'warnings': warnings, 'missing_validation': faltantes}
