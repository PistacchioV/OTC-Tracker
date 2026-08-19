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

# Locks e transações dos bancos de arquivo: lock EXCLUSIVO no arquivo para
# escrever (vale entre processos, não só entre threads) e COMPARTILHADO para
# ler. O `duckdb is None` acima continua sendo o teste de "a lib não está aqui";
# estes só são usados depois dele.
from apps.pages.database_access import duckdb_read, duckdb_write

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
    # `Trade ID` é a CHAVE da linha, e ela não é sempre a mesma coisa: o FWD
    # Start é chaveado pelo B3 ID (chaveá-lo pelo Deal criaria uma segunda linha
    # para o mesmo trade no mapeamento seguinte), os demais pelo Deal da Athena.
    #
    # Havia um `Athena ID` ao lado, e ele foi RETIRADO da tela: para os produtos
    # chaveados pelo Deal ele repetia o Trade ID, e no FWD Start vinha vazio — ou
    # seja, não acrescentava nada em linha nenhuma. A coluna continua existindo no
    # banco (o `ensure_db` só ACRESCENTA), então o dado antigo está lá e voltar
    # atrás é devolver o nome a esta lista.
    'Trade ID',
    'Cetip ID',
    'Moeda',
    'Notional',
    # O notional COM a moeda dele, como um texto só ('USD 1500000'). Não é a
    # coluna `Moeda` ao lado: aquela é o ATIVO da confirmação, e em mercadoria
    # ela guarda a commodity (OLEO, PLATTS) — que não é moeda nenhuma. Aqui a
    # moeda vem de onde ela realmente mora em cada produto (ver
    # `_mc_notional_ccy` no routes), e é ela que o relatório do BACC reparte em
    # duas colunas.
    'Notional Amount CCY',
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

# O RÓTULO de cada coluna, em INGLÊS — que é como todo texto visível do app
# nasce (§2). Os NOMES das colunas continuam os da planilha legada, em
# português, e não podem mudar: eles são o esquema dos dois DuckDB, e renomear
# um quebraria o banco de quem já o tem em disco. Um mapa resolve os dois: o
# banco fala 'Data de vencimento', a tela mostra 'Settlement Date'.
#
# Toda coluna entra aqui, inclusive as que já eram inglesas, para este mapa ser
# a lista COMPLETA do que a tela mostra — assim a tradução br/es da tela
# (`COLTR`, no template) tem um lugar só para casar, e uma coluna nova sem
# rótulo salta aos olhos em vez de aparecer com o nome do banco.
COLUMN_LABELS = {
    'Pending': 'Pending',
    'Aging Confirmação': 'Aging',
    'Legal Entity': 'Legal Entity',
    'Cliente': 'Counterparty',
    'E-mail Subject': 'E-mail Subject',
    'Produto': 'Product',
    'LOB': 'LOB',
    'Trade ID': 'Trade ID',
    # O nome da coluna é da planilha legada; o que o código escreve nela é, e
    # sempre foi, o `B3_ID` do deal. O rótulo passa a dizer o que está lá —
    # renomear a COLUNA quebraria o arquivo de quem já a tem no banco.
    'Cetip ID': 'B3 ID',
    # Moeda virou o ATIVO SUBJACENTE: para câmbio segue a moeda (USD), para
    # commodities entra a commodity da confirmação (OLEO, PLATTS…) — é ela que
    # separa os documentos de um mesmo cliente×dia e acha a confirmação EXATA na
    # pasta.
    'Moeda': 'Underlying Asset',
    # Notional em câmbio, QUANTIDADE em commodities (toneladas, barris): é a
    # mesma coluna carregando as duas grandezas, e o rótulo diz as duas.
    'Notional': 'Notional/Qty',
    'Notional Amount CCY': 'Notional Amount CCY',
    'Data Operação': 'Trade Date',
    'Data de vencimento': 'Settlement Date',
    'Data de envio validação Registro': 'Registration Validation Sent',
    'Data validação Registro': 'Registration Validated',
    'Data EA enviado p/ cliente': 'EA Sent to Client',
    'Data Callback': 'Callback Date',
    'Data envio validação OTC': 'OTC Validation Sent',
    'Conferido OTC': 'Validated by OTC',
    # Os três carimbos aparecem com o rótulo curto, encostados no VALIDADO
    # correspondente — é assim que a planilha era lida.
    'Time Stamp OTC': 'Time Stamp',
    'OTC Comments': 'OTC Comments',
    'Data envio validação MO/FO': 'MO/FO Validation Sent',
    'VALIDADO p/ MO': 'Validated by MO',
    'Time Stamp MO': 'Time Stamp',
    'MO Comments': 'MO Comments',
    'VALIDADO p/ FO': 'Validated by FO',
    'Time Stamp FO': 'Time Stamp',
    'FO Comments': 'FO Comments',
    'Enviado p/ cliente (desbloqueado no fep)': 'Sent to Client (FepWeb released)',
    'Nome fep': 'FepWeb Name',
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
#
# **SEM ACENTO**, e isso não é estilo. `confirmation_type()` compara
# `upper_norm(produto)` com esta tupla, e o `upper_norm` normaliza em NFKD e
# descarta as marcas de combinação — um 'TERMO DE RESILIÇÃO' cadastrado aqui
# chegaria à comparação como 'TERMO DE RESILICAO' e NUNCA casaria consigo mesmo:
# o tipo não resolveria, a pasta não seria achada (`_product_folder` faz o mesmo
# lookup) e nada disso daria erro. Por isso o código é ASCII; o texto com acento
# é assunto de rótulo, não de código.
CONFIRMATION_TYPES = ('NDF VANILLA', 'NDF FWD START', 'NDF OTHER PUBLISHER',
                      'NDF COMM', 'OPTION COMM', 'FXO',
                      'SWAP', 'SWAP CORPORATE', 'TERMO DE RESILICAO',
                      # Os tres documentos que alteram uma confirmacao ja
                      # existente, em vez de confirmar uma operacao nova. Em
                      # INGLES como todo texto do app, e em MAIUSCULA e SEM
                      # ACENTO como os demais: o valor e CODIGO, comparado por
                      # `upper_norm`, e nao rotulo de tela.
                      'AMENDMENT', 'ADDENDUM', 'RERATIFICATION')

# Os três estágios, na ordem em que a esteira anda.
STAGE_OTC, STAGE_MO, STAGE_FO = 'OTC', 'MO', 'FO'
PENDING_OTC = 'Pending OTC'
PENDING_MO = 'Pending MO'
PENDING_FO = 'Pending FO'
PENDING_MOFO = 'Pending MO/FO'
# Estados fora das três mesas (§254):
#   * Pending Legal — HOLD manual: a confirmação aguarda o jurídico e fica fora
#     da fila do OTC até alguém soltá-la (grade/modal ou o card do Monitor). É o
#     ÚNICO estado que se escreve à mão junto com o Pending OTC que o desfaz.
#   * Pending FepWeb — DERIVADO: todas as validações feitas e o documento ainda
#     não foi enviado ao cliente. Nunca se digita — nasce das colunas de
#     validação e morre quando o 'Enviado p/ cliente' é preenchido.
PENDING_LEGAL = 'Pending Legal'
PENDING_FEPWEB = 'Pending FepWeb'
STATUS_OK = 'Ok'

# A coluna que fecha o ciclo: com ela preenchida (e as validações feitas) a
# confirmação é Ok; sem ela, fica em Pending FepWeb aguardando o envio.
SENT_COLUMN = 'Enviado p/ cliente (desbloqueado no fep)'

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
#
# Estes números são o **fallback**: o prazo de cada mesa é cadastrável em
# /mapping (`manual-conf-sla`), e o que está aqui é o que valia quando ele era
# fixo no código — para o comportamento ser idêntico até alguém editar a tabela.
SLA_BIZDAYS = {
    STAGE_OTC: 3,
    STAGE_MO: 4,
    STAGE_FO: 6,
}

# O seed do cadastro. As três mesas, uma linha cada — a etapa é a chave, e não há
# uma quarta: quem valida é OTC, MO ou FO.
SLA_SEED = tuple(
    {'STAGE': st, 'BIZDAYS': str(SLA_BIZDAYS[st]), 'NOTES': nota}
    for st, nota in (
        (STAGE_OTC, 'Dias úteis da data da operação até o OTC conferir'),
        (STAGE_MO, 'Dias úteis até o MO validar — corre em paralelo ao FO'),
        (STAGE_FO, 'Dias úteis até o FO validar — corre em paralelo ao MO'),
    )
)


def sla_upgrade(rows):
    """Garante uma linha por mesa e normaliza a etapa para MAIÚSCULO.

    Roda na LEITURA, pelo mesmo motivo do `validation_upgrade`: a instância que
    já abriu a tela de mapping tem o arquivo em disco e nunca mais receberia o
    seed. Etapa repetida some — a primeira ganha, senão duas linhas disputariam
    o prazo da mesma mesa.
    """
    out, vistos = [], set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        r = dict(r)
        st = upper_norm(r.get('STAGE'))
        if st not in SLA_BIZDAYS or st in vistos:
            continue
        r['STAGE'] = st
        vistos.add(st)
        out.append(r)
    for s in SLA_SEED:
        if s['STAGE'] not in vistos:
            out.append(dict(s))
            vistos.add(s['STAGE'])
    return out


# O cadastro é lido a CADA linha do Monitor (três etapas por linha), então ele é
# cacheado por mtime em vez de reler o disco: edição na tela continua valendo no
# request seguinte, que é o contrato dos mappings.
_SLA_CACHE = {'mtime': None, 'val': None}


def sla_days():
    """Mesa → dias úteis de prazo, do cadastro `manual-conf-sla`.

    Prazo em branco (ou que não seja um número) devolve o valor histórico do
    `SLA_BIZDAYS`: uma célula limpa pela tela não pode virar "sem prazo", que é
    como uma confirmação atrasada deixaria de acender o vermelho em silêncio.
    """
    try:
        mtime = os.path.getmtime(_mapping_path('manual-conf-sla'))
    except OSError:
        mtime = None
    if _SLA_CACHE['val'] is not None and _SLA_CACHE['mtime'] == mtime:
        return _SLA_CACHE['val']
    out = dict(SLA_BIZDAYS)
    for r in _mapping_rows('manual-conf-sla'):
        st = upper_norm(r.get('STAGE'))
        if st not in out:
            continue
        try:
            out[st] = int(float(str(r.get('BIZDAYS', '')).strip().replace(',', '.')))
        except (TypeError, ValueError):
            pass
    _SLA_CACHE.update(mtime=mtime, val=out)
    return out


def sla_deadline(row, stage):
    """A data limite daquela etapa: trade date + N dias úteis. None sem data."""
    d = parse_date(row.get('Data Operação'))
    n = sla_days().get(str(stage or '').upper())
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

def _mapping_path(key):
    return os.path.join(_MAPPINGS_DIR, '%s.json' % key)


def _mapping_rows(key):
    """Cadastro de /mapping lido do disco a cada chamada — edição na tela vale na
    próxima leitura, sem restart. Importar `routes` daqui seria circular.

    O `upgrade` do cadastro da esteira é aplicado AQUI, e não só na tela de
    /mapping: era essa a diferença entre os dois leitores. O `_MAPPING_DEFS` do
    `routes` roda o upgrade ao servir a tela, mas quem lê a regra a cada linha do
    Monitor é esta função — e ela via o arquivo CRU. Numa instância que nunca
    abriu o /mapping (ou que abriu e não salvou), a `OPTION EDG` do formato
    antigo virava um coringa de FXO e mandava TODA opção de câmbio para o FO, e o
    SWAP CORPORATE, sem linha nenhuma, caía no DEFAULT_RULE (OTC + MO) — a regra
    errada, porque nele o FO também valida.
    """
    import json
    try:
        with open(_mapping_path(key), encoding='utf-8') as fh:
            rows = json.load(fh)
    except Exception:
        rows = []
    rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    if key == 'manual-conf-validation':
        return validation_upgrade(rows)
    if key == 'manual-conf-sla':
        return sla_upgrade(rows)
    return rows


# Quem valida a confirmação de cada tipo. Uma linha por tipo, na ordem da lista.
# Constante de módulo (e não literal dentro do `_MAPPING_DEFS`) porque o `upgrade`
# também precisa dela: ele completa o arquivo já existente com os tipos que ainda
# não têm linha nenhuma.
VALIDATION_SEED = (
    {'PRODUCT': 'NDF VANILLA', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED',
     'FO': 'EXEMPT', 'NOTES': 'Termo de moeda'},
    {'PRODUCT': 'NDF FWD START', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED',
     'FO': 'EXEMPT', 'NOTES': 'Termo de moeda com início futuro'},
    {'PRODUCT': 'NDF OTHER PUBLISHER', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED',
     'FO': 'EXEMPT', 'NOTES': 'Termo de moeda com publicador não-BACEN'},
    {'PRODUCT': 'NDF COMM', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED',
     'FO': 'EXEMPT', 'NOTES': 'Termo de mercadoria'},
    {'PRODUCT': 'OPTION COMM', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED',
     'FO': 'EXEMPT', 'NOTES': 'Opção de mercadoria'},
    {'PRODUCT': 'FXO', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED',
     'FO': 'EXEMPT', 'NOTES': 'Opção de câmbio'},
    {'PRODUCT': 'FXO', 'LOB': 'EDG', 'OTC': 'REQUESTED', 'MO': 'REQUESTED',
     'FO': 'REQUESTED', 'NOTES': 'Opção de EDG — o FO também valida'},
    {'PRODUCT': 'SWAP', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED',
     'FO': 'REQUESTED', 'NOTES': ''},
    {'PRODUCT': 'SWAP CORPORATE', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED',
     'FO': 'REQUESTED', 'NOTES': ''},
    # Termo de resilição — o distrato da operação. Entra no caminho da maioria
    # (OTC + MO). É SEED, não regra fixa: quem sabe se o FO valida o distrato de
    # um produto é a mesa, e a resposta se corrige em um clique no /mapping. O
    # que o seed não pode é deixar o tipo sem linha, porque aí ele cairia no
    # DEFAULT_RULE sem ninguém ter decidido nada.
    {'PRODUCT': 'TERMO DE RESILICAO', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED',
     'FO': 'EXEMPT', 'NOTES': 'Termo de resilição (distrato)'},
    # Aditamento / Aditivo / Reratificação: documentos que ALTERAM uma
    # confirmação já emitida. Entram no caminho da maioria (OTC + MO), como o
    # distrato. É SEED, não regra fixa — quem sabe se o FO valida a alteração de
    # um produto é a mesa, e a resposta se corrige em um clique no /mapping. O
    # que o seed não pode é deixar o tipo SEM linha: aí ele cairia no
    # DEFAULT_RULE sem ninguém ter decidido nada.
    {'PRODUCT': 'AMENDMENT', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED',
     'FO': 'EXEMPT', 'NOTES': 'Aditamento'},
    {'PRODUCT': 'ADDENDUM', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED',
     'FO': 'EXEMPT', 'NOTES': 'Aditivo'},
    {'PRODUCT': 'RERATIFICATION', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'REQUESTED',
     'FO': 'EXEMPT', 'NOTES': 'Reratificação'},
)


def validation_upgrade(rows):
    """Traz o cadastro da esteira para os nomes do Electronic Inventory.

    Roda na LEITURA, e é obrigatório: a instância que já abriu a tela de mapping
    tem o arquivo em disco e nunca mais receberia o seed novo. Sem isto, a coluna
    PRODUCT — que agora é um `select` — abriria um cadastro 'OPTION' com o
    primeiro item da lista selecionado, e o primeiro Save do usuário trocaria o
    produto da linha sem ninguém pedir.

    Três conversões, e a primeira é a que não pode se perder: 'OPTION EDG' não é
    um produto, é a opção de câmbio **na LOB EDG**. Ela vira PRODUCT 'FXO' com
    LOB 'EDG' — que é o desenho Produto × LOB que a tabela sempre teve, e o
    único jeito de a regra "EDG também passa pelo FO" continuar existindo.

    A terceira é o 'NDF' genérico, que existiu entre dois commits do mesmo dia e
    podia significar tanto Vanilla quanto FWD Start. Ele vira 'NDF VANILLA', e a
    ambiguidade não custa nada: as duas linhas nascem do seed com a MESMA regra
    (OTC + MO), então as duas leituras dão no mesmo resultado.
    """
    out, vistos = [], set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        r = dict(r)
        prod = upper_norm(r.get('PRODUCT'))
        lob = str(r.get('LOB') or '').strip()
        if prod == 'OPTION EDG':
            prod, lob = 'FXO', (lob or 'EDG')
        elif prod == 'NDF':
            prod = 'NDF VANILLA'
        r['PRODUCT'] = confirmation_type(prod, lob)
        r['LOB'] = lob
        # A tradução pode encostar duas linhas na mesma chave (o arquivo antigo
        # tinha 'OPTION' e poderia ganhar 'FXO'). A primeira ganha: descartar a
        # segunda é o que evita duas regras concorrentes para o mesmo par.
        chave = (r['PRODUCT'].upper(), lob.upper())
        if chave in vistos:
            continue
        vistos.add(chave)
        out.append(r)

    # Tipo que ainda não tem linha NENHUMA entra com a do seed. Sem isto, o
    # arquivo de uma instância que já abriu a tela de mapping ficaria sem os
    # tipos novos, e eles cairiam no DEFAULT_RULE (OTC + MO) — o que para o
    # SWAP CORPORATE é a regra ERRADA, porque nele o FO também valida.
    #
    # O teste é pelo PRODUTO, não pelo par Produto × LOB: quem apagou a linha
    # coringa de um produto e deixou só a da sua LOB fez isso de propósito, e
    # ressuscitar a coringa mudaria o comportamento de toda LOB não cadastrada.
    com_linha = {p for p, _l in vistos}
    for s in VALIDATION_SEED:
        if s['PRODUCT'].upper() not in com_linha:
            out.append(dict(s))
            com_linha.add(s['PRODUCT'].upper())
    return out


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


def split_notional_ccy(v):
    """(moeda, valor) da coluna `Notional Amount CCY`.

    A coluna guarda os dois num texto só ('USD 1500000') porque é assim que ela
    é lida na tela — o valor sem a moeda ao lado não diz nada em quem opera duas
    moedas no mesmo dia. Quem precisa das partes separadas é o relatório do
    BACC, que as manda para DUAS colunas da planilha, e é este o único lugar que
    sabe reparti-las: um `split(' ')` espalhado pelos consumidores divergiria no
    primeiro valor com espaço de milhar.

    A moeda é o PRIMEIRO token e só vale se tiver 3 letras — é código ISO, e um
    valor solto na célula (linha antiga, digitação à mão) devolve moeda vazia e
    o texto inteiro como valor, em vez de comer o primeiro dígito.
    """
    t = re.sub(r'\s+', ' ', str(v or '')).strip()
    if not t:
        return '', ''
    ccy, _sep, resto = t.partition(' ')
    if len(ccy) == 3 and ccy.isalpha():
        return ccy.upper(), resto.strip()
    return '', t


def pending_stage(row, rules=None):
    """Em que etapa a confirmação está, das colunas de validação.

    Deriva do estado, não de um campo digitado: uma coluna 'Pending' escrita à
    mão discordaria das datas ao lado dela no primeiro reject, e a tela mostraria
    uma etapa que já passou. As DUAS exceções são deliberadas (§254):

      * 'Pending Legal' gravado na linha é um hold manual e VENCE a derivação —
        a confirmação está fora da fila até alguém soltá-la;
      * o fim da esteira tem dois degraus: validações feitas SEM o Enviado p/
        cliente é 'Pending FepWeb' (aguardando envio); Ok exige a data do envio.
    """
    if upper_norm(row.get('Pending')) == upper_norm(PENDING_LEGAL):
        return PENDING_LEGAL

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
    if not _filled(row, SENT_COLUMN):
        return PENDING_FEPWEB
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
        # O `with` fecha a conexão e solta o lock em QUALQUER saída, inclusive na
        # exceção: uma conexão vazada segura o lock de escrita do DuckDB até o
        # processo morrer, e aí a tela some para TODOS.
        with duckdb_write(path) as con:
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
        # `duckdb_read`: lock COMPARTILHADO (as leituras da tela não se excluem
        # entre si) e fechamento garantido na saída do bloco.
        with duckdb_read(path) as con:
            cols = ', '.join('"{}"'.format(c) for c in DB_COLUMNS)
            raw = con.execute('SELECT {} FROM {}'.format(cols, TABLE)).fetchall()
    except Exception:
        _LOG.warning('[manual-conf] consulta falhou em %s:\n%s', path, traceback.format_exc())
        return []
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
    """Roda (sql, params) numa transação de escrita só.

    O laço de retentativa que estava escrito aqui passou a ser do `duckdb_write`
    — as leituras read-only da tela são rápidas mas frequentes, e o DuckDB recusa
    a escrita enquanto uma delas está aberta; quem espera e volta a tentar agora
    é o contexto, num lugar só e para todos os bancos.

    E é UMA transação para o lote inteiro: metade das operações não fica gravada
    quando a outra metade falha."""
    if duckdb is None:
        return False
    path = db_path(category)
    ensure_db(path)
    try:
        with duckdb_write(path) as con:
            for sql, params in ops:
                con.execute(sql, params)
        return True
    except Exception:
        _LOG.warning('[manual-conf] escrita falhou em %s:\n%s', category,
                     traceback.format_exc())
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


def set_email_subjects(pairs):
    """Grava o assunto do e-mail de recap nas linhas indicadas.

    `pairs` é {Trade ID: assunto}. Recebe o LOTE inteiro de propósito: o Monitor
    resolve dezenas de confirmações por carregamento, e um `find_row` por chave
    releria os dois bancos dezenas de vezes para escrever meia dúzia de células.

    O e-mail é a FONTE dessa coluna — ela se chama 'E-mail Subject' e guarda o
    assunto do recap que está na pasta da confirmação. Por isso o valor é
    reescrito quando muda, e não só quando a célula está vazia: se o recap foi
    substituído, o assunto antigo passou a apontar para um e-mail que não existe
    mais. Igual não escreve nada — sem isso, cada abertura do Monitor
    reescreveria a esteira inteira sem uma célula mudar.

    Devolve quantas linhas foram efetivamente gravadas.
    """
    alvo = {}
    for k, v in (pairs or {}).items():
        k = str(k or '').strip()
        v = str(v or '').strip()
        if k and v:
            alvo[k] = v
    if not alvo:
        return 0
    n = 0
    for row in load_all():
        chave = str(row.get(KEY_COLUMN, '') or '').strip()
        novo = alvo.get(chave)
        if not novo or str(row.get('E-mail Subject', '') or '').strip() == novo:
            continue
        row['E-mail Subject'] = novo
        upsert_row(row)
        n += 1
    return n


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
    # Tipo NOVO: nunca existiu com outro nome, então não há pasta antiga para
    # varrer. A entrada existe (vazia) de propósito — a lista é declarada tipo a
    # tipo, e um tipo AUSENTE daqui não se distingue de um tipo cujo histórico
    # alguém esqueceu de declarar.
    'TERMO DE RESILICAO':  (),
    # Tipos NOVOS: nunca existiram sob outro nome, entao nao ha pasta antiga a
    # varrer. A entrada vazia e obrigatoria — um tipo AUSENTE daqui nao se
    # distingue de um tipo cujo historico alguem esqueceu de declarar.
    'AMENDMENT':           (),
    'ADDENDUM':            (),
    'RERATIFICATION':      (),
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


def _extra_card(stage, pending_value, rows, docs_for=None):
    """Card do Monitor para um estado FORA das três mesas (Legal / FepWeb).

    O mesmo agrupamento por documento dos cards de mesa, sem regra de validação
    (o estado não é de mesa nenhuma) e sem SLA. Os `keys` do grupo são o que os
    botões de ação dos cards usam (soltar para o OTC / marcar enviado)."""
    grupos = {}
    for r in rows:
        if r.get('Pending') != pending_value:
            continue
        gk = group_key(r)
        item = grupos.get(gk)
        if item is None:
            item = {k: r.get(k, '') for k in MONITOR_FIELDS}
            item['Tipo'] = confirmation_type(r.get('Produto'), r.get('LOB'))
            item.update({'stage': stage, 'keys': [], 'trades': [], 'docs': []})
            if docs_for:
                item['docs'] = docs_for(r) or []
            grupos[gk] = item
        k = str(r.get(KEY_COLUMN, '') or '')
        if k:
            item['keys'].append(k)
            item['trades'].append(k)
        if _aging_int(r.get('Aging Confirmação')) > _aging_int(item.get('Aging Confirmação')):
            item['Aging Confirmação'] = r.get('Aging Confirmação', '')
        # Quantas operações do grupo estão SEM Data Callback. É contagem e não
        # bandeira porque o documento cobre várias operações: dizer só "falta
        # callback" num grupo de dez esconde se falta em uma ou nas dez.
        #
        # O card que a mostra é o de **Pending FepWeb** (a tela decide): ali a
        # confirmação está validada e esperando o envio ao cliente, e o callback
        # é justamente o que precisa ter acontecido ANTES desse envio. Nos
        # demais estados a coluna ainda está em aberto por construção, e um
        # badge vermelho ali só diria que a esteira mal começou.
        if not _filled(r, 'Data Callback'):
            item['no_callback'] = item.get('no_callback', 0) + 1
    itens = list(grupos.values())
    for it in itens:
        it['count'] = len(it['keys'])
        it['key'] = it['keys'][0] if it['keys'] else ''
        it.setdefault('no_callback', 0)
    itens.sort(key=lambda i: -_aging_int(i.get('Aging Confirmação')))
    return {'stage': stage, 'label': pending_value, 'count': len(itens),
            'trades': sum(i['count'] for i in itens), 'items': itens}


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
    # Os dois estados FORA das mesas (§254) viram cards nas pontas: Pending
    # Legal ANTES do OTC (a confirmação ainda não entrou na fila) e Pending
    # FepWeb DEPOIS do FO (validada, aguardando o envio ao cliente). Sem regra
    # de mesa e sem SLA — não há prazo cadastrado para etapas que não assinam.
    cards.insert(0, _extra_card('LEGAL', PENDING_LEGAL, rows, docs_for))
    cards.append(_extra_card('FEPWEB', PENDING_FEPWEB, rows, docs_for))
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
