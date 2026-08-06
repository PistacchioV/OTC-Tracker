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
from datetime import datetime

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
    'Data envio validação MO/FO',
    'VALIDADO p/ MO',
    'Time Stamp MO',
    'VALIDADO p/ FO',
    'Time Stamp FO',
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

# Os três estágios, na ordem em que a esteira anda.
STAGE_OTC, STAGE_MO, STAGE_FO = 'OTC', 'MO', 'FO'
PENDING_OTC = 'Pending OTC'
PENDING_MO = 'Pending MO'
PENDING_FO = 'Pending FO'
PENDING_MOFO = 'Pending MO/FO'
STATUS_OK = 'Ok'

REQUESTED = 'REQUESTED'
EXEMPT = 'EXEMPT'


# =============================================================================
# Normalizações
# =============================================================================

def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]', '', s.lower())


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
    """
    exact, wildcard = {}, {}
    for r in _mapping_rows('manual-conf-validation'):
        prod = norm(r.get('PRODUCT'))
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
    prod, l = norm(produto), norm(lob)
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


def aging(row):
    """Dias desde que a confirmação foi enviada para validação do OTC.

    É a idade da PENDÊNCIA, não da operação: uma operação de três meses atrás
    cuja confirmação saiu ontem não está atrasada. Sem a data de envio, cai na
    data da operação, que é o que a planilha antiga tinha.
    """
    d = parse_date(row.get('Data envio validação OTC')) or parse_date(row.get('Data Operação'))
    if not d:
        return None
    return (datetime.now().date() - d).days


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
    """Cria o banco vazio se ele não existir, para a tela abrir antes do primeiro
    import."""
    if os.path.isfile(path):
        return
    if duckdb is None:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # close() em finally: uma conexão vazada segura o lock de escrita do
        # DuckDB até o processo morrer, e aí a tela some para TODOS.
        con = duckdb.connect(path)
        try:
            cols = ', '.join('"{}" VARCHAR'.format(c) for c in DB_COLUMNS)
            con.execute('CREATE TABLE IF NOT EXISTS {} ({})'.format(TABLE, cols))
        finally:
            con.close()
        _LOG.info('[manual-conf] banco vazio criado em %s', path)
    except Exception:
        _LOG.warning('[manual-conf] não consegui criar %s', path)


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


def mark_validated(key, stage, sid):
    """Valida uma etapa: carimba a data, o horário e o SPN de quem validou.

    Ao sair do OTC, carimba também a Data envio validação MO/FO — é o mesmo
    instante, e deixar quem valida preencher isso à mão faria a idade da segunda
    etapa nascer errada.
    """
    row = find_row(key)
    if row is None:
        return None
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

# Produto → pasta do Electronic Inventory. É o MESMO nome que os quatro `save`
# de confirmação usam ao gravar; um segundo nome aqui faria a pasta existir e o
# Monitor procurar noutra.
PRODUCT_FOLDER = {
    'NDF COMM': 'NDF Commodities',
    'OPTION COMM': 'Commodities Options',
    'OPTION': 'FX Options',
    'NDF FWD START': 'NDF FWD Start',
}

_MONTH_EN = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May',
             6: 'June', 7: 'July', 8: 'August', 9: 'September', 10: 'October',
             11: 'November', 12: 'December'}


def confirmation_folder(row):
    """(cliente, caminho relativo da pasta) do documento daquela confirmação.

    A pasta é DERIVADA da própria linha — cliente, produto e data da operação —,
    e não de um campo gravado. É isso que faz o botão *Abrir* funcionar para as
    confirmações que já existiam antes de o carimbo existir: um link guardado só
    aparece nas que foram salvas depois, e essas são justamente as que ninguém
    precisa procurar.

    (None, None) quando falta o que forma o caminho.
    """
    cliente = str(row.get('Cliente', '') or '').strip()
    produto = PRODUCT_FOLDER.get(str(row.get('Produto', '') or '').strip().upper())
    d = parse_date(row.get('Data Operação'))
    if not (cliente and produto and d):
        return None, None
    rel = '/'.join(['Confirmations', '%04d' % d.year,
                    '%02d. %s' % (d.month, _MONTH_EN[d.month]),
                    '%02d' % d.day, produto])
    return cliente, rel


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
MONITOR_FIELDS = ('Data Operação', 'Cliente', 'Produto', 'LOB', 'Trade ID',
                  'Aging Confirmação')


# O que define UMA confirmação. O documento é emitido por contraparte × produto ×
# data de negociação (e a LOB acompanha), cobrindo todas as operações do grupo —
# então o Monitor tem de mostrar UM item por documento, não um por trade. Uma
# lista com dez linhas do mesmo cliente no mesmo dia é uma confirmação só, e
# validar dez vezes o mesmo papel é o erro que isso evita.
GROUP_FIELDS = ('LOB', 'Cliente', 'Produto', 'Data Operação')


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
                sem_cadastro.add('%s · %s' % (str(r.get('Produto') or '—'),
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
                item.update({'stage': stage, 'keys': [], 'trades': [], 'docs': []})
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
    warnings = []
    if sem_cadastro:
        warnings.append(
            'Sem cadastro de validação para: ' + ', '.join(sorted(sem_cadastro)) +
            '. Enquanto isso essas confirmações seguem por OTC e MO.')
    return {'cards': cards, 'warnings': warnings}
