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
import threading
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
from apps.pages.data_paths import data_dir, data_path, data_write, mapping_file, mapping_write
from apps.pages.database_access import duckdb_read, duckdb_write
from apps.pages.request_cache import once_per_request as _once_per_request
# Só o Config: importar o `routes` daqui seria circular (é ele quem importa este
# módulo). O que se repete é a LEITURA da configuração, não o dado.
from apps.config import Config
from apps.pages import data_store as _store  # noqa: E402

_LOG = logging.getLogger(__name__)

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
# A pasta dos bancos vem do Config: ela muda de lugar quando a instância do time
# aponta para o share, e os dois bancos da esteira têm de ir junto com os do
# resto do app — metade no share e metade local é o pior dos dois mundos.
_DB_DIR = Config.DATABASE_DIR
# Os mappings continuam DENTRO da aplicação: são cadastro versionado, vêm no
# pull e não são banco.
_MAPPINGS_DIR = data_write('mappings')

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
    # Rótulo pedido em 2026-09-01: a coluna guarda o numeroContrato do FepWeb —
    # o MESMO que a geração grava na coluna FepWeb ID do Pending Confirmation —
    # e "Name" dizia outra coisa. Só o rótulo muda; o nome do banco fica.
    'Nome fep': 'FepWeb ID',
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


@_once_per_request
def sla_days():
    """Mesa → dias úteis de prazo, do cadastro `manual-conf-sla`.

    Prazo em branco (ou que não seja um número) devolve o valor histórico do
    `SLA_BIZDAYS`: uma célula limpa pela tela não pode virar "sem prazo", que é
    como uma confirmação atrasada deixaria de acender o vermelho em silêncio.

    `@_once_per_request` pela mesma razão do `_refdata_by_taxid`: o Monitor
    pergunta o prazo TRÊS vezes por linha (via `sla_state`), e o cache por mtime
    evita reler o cadastro sem evitar o `stat` que decide se ele mudou. No share
    esse stat é ida à rede, e ele ficava dentro do laço de linhas.
    """
    try:
        mtime = _store.getmtime(_mapping_path('manual-conf-sla'))
    except OSError:
        mtime = None
    if _SLA_CACHE['val'] is not None and _SLA_CACHE['mtime'] == mtime:
        return _SLA_CACHE['val']
    linhas = _mapping_rows_try('manual-conf-sla')
    if linhas is None:
        # Leitura falhou: nada entra no cache (guardado sob o carimbo, o prazo
        # de fábrica valia até alguém editar o cadastro). Serve o último prazo
        # conhecido, ou o histórico.
        return _SLA_CACHE['val'] or dict(SLA_BIZDAYS)
    out = dict(SLA_BIZDAYS)
    for r in linhas:
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
    return mapping_file(key, _MAPPINGS_DIR)


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
    rows = _mapping_rows_try(key)
    if rows is None:
        # Falhou (banco ocupado/ilegível): a última leitura BOA deste cadastro,
        # e só sem nenhuma o seed via upgrade — lido como vazio, o
        # `validation_upgrade([])` aplicava as regras de FÁBRICA e mandava
        # confirmações para as mesas erradas enquanto a trava durasse.
        return _MAP_LAST_GOOD.get(key) or _mapping_upgrade(key, [])
    return rows


_MAP_LAST_GOOD = {}


def _mapping_upgrade(key, rows):
    if key == 'manual-conf-validation':
        return validation_upgrade(rows)
    if key == 'manual-conf-sla':
        return sla_upgrade(rows)
    return rows


def _mapping_rows_try(key):
    """`_mapping_rows` que devolve `None` quando a leitura FALHOU (distinto de
    cadastro ausente, que é `[]` + upgrade) — para quem cacheia não guardar a
    falha sob o carimbo (`sla_days`)."""
    try:                                        # DB-first (fase 3)
        from apps.pages import duck_read
        rows = duck_read.dataset_rows(_mapping_path(key))
    except FileNotFoundError:
        rows = []
    except Exception as exc:                                # noqa: BLE001
        _LOG.warning('[manual-conf] cadastro %s ilegível (%s: %s)', key,
                     type(exc).__name__, exc)
        return None
    rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    rows = _mapping_upgrade(key, rows)
    _MAP_LAST_GOOD[key] = rows
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
    # Termo de resilição — o distrato da operação. O trilho é **só OTC** (mesa,
    # 18/09/2026): o distrato não reabre economia nenhuma, e o que o MO e o FO
    # conferem é a economia da operação, que já passou por eles quando ela
    # nasceu. Continua sendo SEED, não regra fixa — a resposta se corrige em um
    # clique no /mapping —, e o que o seed não pode é deixar o tipo sem linha,
    # porque aí ele cairia no DEFAULT_RULE (OTC + MO) sem ninguém ter decidido.
    {'PRODUCT': 'TERMO DE RESILICAO', 'LOB': '', 'OTC': 'REQUESTED', 'MO': 'EXEMPT',
     'FO': 'EXEMPT', 'NOTES': 'Termo de resilição (distrato) — só OTC valida'},
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

    # 18/09/2026 — o Termo de Resilição passou a ser validado SÓ pelo OTC. O
    # seed nasceu OTC + MO no dia anterior, e seed não alcança quem já tem o
    # cadastro (§6): sem esta correção a instância seguiria mandando o distrato
    # para o Pending MO, e a esteira nunca fecharia sozinha.
    #
    # Só mexe na linha que está EXATAMENTE como o seed antigo a deixou. Mesa
    # que já editou decidiu alguma coisa, e decisão da mesa não se desfaz
    # sozinha num upgrade — que é a razão de este bloco ser tão estreito.
    for r in out:
        if upper_norm(r.get('PRODUCT')) != 'TERMO DE RESILICAO':
            continue
        if str(r.get('LOB') or '').strip():
            continue
        if (upper_norm(r.get('OTC')) == 'REQUESTED'
                and upper_norm(r.get('MO')) == 'REQUESTED'
                and upper_norm(r.get('FO')) == 'EXEMPT'):
            r['MO'] = 'EXEMPT'
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
        try:                                    # DB-first (fase 3)
            from apps.pages import duck_read
            path = data_path('anbima.json')
            datas = duck_read.calendar_dates(path)
            if datas is None:
                datas = {d['date'] for d in (_store.read(path) or []) if d.get('date')}
            _ANBIMA['feriados'] = datas
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


# Os bancos já conferidos POR ESTE PROCESSO — ver `ensure_db`.
_ENSURED = set()
_ENSURED_LOCK = threading.Lock()


def ensure_db(path):
    """Cria o banco vazio se ele não existir e ACRESCENTA as colunas que faltam.

    A segunda parte é o que dispensa um script de migração: o banco fica fora do
    repositório (`apps/static/data/db/` está no .gitignore), então a instância do
    time tem o dela desde antes de a coluna existir. Sem isto, o primeiro
    `INSERT` — que lista as colunas explicitamente — falharia com "column not
    found" e a tela inteira sumiria depois de um pull.

    **Roda UMA vez por processo e por arquivo.** `ADD COLUMN IF NOT EXISTS` é
    idempotente, mas não é de graça: a conferência abre o banco em ESCRITA —
    trava de arquivo EXCLUSIVA entre processos e semáforo de UM dentro dele —
    e ela ficava no `load_rows`, ou seja, em toda LEITURA. Cada abertura do
    Track, do Monitor, do BACC e da escalação tomava a trava exclusiva dos
    dois bancos só para descobrir que não havia coluna a acrescentar, excluindo
    por alguns segundos os leitores das outras instâncias sobre o mesmo `db/`
    do share (§8) — e quando a vizinha estava lendo, o open estourava com
    *"used by another process"*, engolido logo abaixo. Uma trava exclusiva por
    leitura, sem pista nenhuma no log. O schema é o do CÓDIGO, então a
    resposta não muda dentro do processo; o que continua sendo conferido a
    cada chamada é se o ARQUIVO existe (um `stat`, que o `load_rows` já
    pagava), porque um banco apagado por fora tem de renascer.
    """
    if duckdb is None:
        return
    novo = not _store.isfile(path)
    if not novo:
        with _ENSURED_LOCK:
            if path in _ENSURED:
                return
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
        # Só depois de a conferência DAR CERTO: a que falhou (arquivo em uso
        # por outro processo) volta a ser tentada na chamada seguinte.
        with _ENSURED_LOCK:
            _ENSURED.add(path)
    except Exception:
        _LOG.warning('[manual-conf] não consegui preparar %s:\n%s', path, traceback.format_exc())


def load_rows(category, strict=False):
    """As linhas de um banco da esteira.

    `strict=True` é de quem vai GRAVAR a partir do que leu: a leitura que falha
    (banco ocupado pela instância vizinha, ilegível) LEVANTA em vez de responder
    lista vazia. Lida como "vazio", ela fazia o `find_row` dizer que a operação
    não existe, e a gravação seguinte trocava a linha inteira por uma em branco
    com só a célula editada (§546). A tela, que só mostra, segue tolerante.
    """
    path = db_path(category)
    ensure_db(path)
    if duckdb is None or not _store.isfile(path):
        return []
    try:
        # `duckdb_read`: lock COMPARTILHADO (as leituras da tela não se excluem
        # entre si) e fechamento garantido na saída do bloco.
        with duckdb_read(path) as con:
            cols = ', '.join('"{}"'.format(c) for c in DB_COLUMNS)
            raw = con.execute('SELECT {} FROM {}'.format(cols, TABLE)).fetchall()
    except Exception:
        _LOG.warning('[manual-conf] consulta falhou em %s:\n%s', path, traceback.format_exc())
        if strict:
            raise
        return []
    rules = validation_rules()
    out = []
    for r in raw:
        row = {c: ('' if v is None else str(v)) for c, v in zip(DB_COLUMNS, r)}
        refresh_derived(row, rules)
        # Pseudo-campo de EXIBIÇÃO (começa com '_', o INSERT filtra por
        # DB_COLUMNS e ele nunca persiste): produto que não passa por validação
        # de FO mostra N/A nas três colunas da mesa — a célula vazia ali se
        # leria como "falta validar", e não falta. Gravar 'N/A' no banco seria
        # pior: viraria uma "validação" no dia em que o cadastro mudasse o
        # produto para REQUESTED.
        rule, _found = rule_for(row.get('Produto'), row.get('LOB'), rules)
        row['_fo_na'] = not rule[STAGE_FO]
        out.append(row)
    return out


def load_all(strict=False):
    """As linhas dos dois bancos, com a etapa recalculada (`strict`: ver `load_rows`).

    Uma linha pode estar fisicamente no banco errado — ela só migra quando é
    gravada —, então a categoria de exibição vem do `Pending` recalculado, não do
    arquivo em que a linha estava.
    """
    return load_rows('pending', strict) + load_rows('ok', strict)


def _write_exec(category, ops, raise_errors=False):
    """Roda (sql, params) numa transação de escrita só. `raise_errors`: a falha
    SOBE (depois do WARNING) em vez de virar `False`.

    O laço de retentativa que estava escrito aqui passou a ser do `duckdb_write`
    — as leituras read-only da tela são rápidas mas frequentes, e o DuckDB recusa
    a escrita enquanto uma delas está aberta; quem espera e volta a tentar agora
    é o contexto, num lugar só e para todos os bancos.

    E é UMA transação para o lote inteiro: metade das operações não fica gravada
    quando a outra metade falha."""
    if duckdb is None:
        if raise_errors:
            raise RuntimeError('duckdb indisponível: a esteira não grava')
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
        if raise_errors:
            raise
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
    esteira fecha (e de volta, quando um reject a reabre).

    No banco de destino o DELETE e o INSERT são UMA transação, e o banco de
    origem só perde a linha DEPOIS de o destino gravar: apagar primeiro e
    inserir numa segunda abertura perdia a operação inteira quando o INSERT
    falhava (§546). E a falha do destino SOBE: ignorada, a tela respondia
    `success` com a linha que nunca chegou ao banco — a validação aparecia
    feita, o sino anunciava, e nada estava gravado."""
    refresh_derived(row)
    key = str(row.get(KEY_COLUMN, '') or '').strip()
    target = target_category(row)
    cols = ', '.join('"{}"'.format(c) for c in DB_COLUMNS)
    ph = ', '.join('?' for _ in DB_COLUMNS)
    ops = []
    if key:
        ops.append(('DELETE FROM {} WHERE trim("{}") = ?'.format(TABLE, KEY_COLUMN), [key]))
    ops.append(('INSERT INTO {} ({}) VALUES ({})'.format(TABLE, cols, ph),
                [str(row.get(c, '') or '') for c in DB_COLUMNS]))
    _write_exec(target, ops, raise_errors=True)
    for cat in ('pending', 'ok'):
        if cat != target:
            _delete_key(cat, key)
    return target


_SEL_ROW = 'SELECT {} FROM {} WHERE trim("{}") = ? LIMIT 1'


def mutate_row(key, fn):
    """Ler → alterar → gravar UMA linha da esteira com a leitura DENTRO da
    transação de escrita (trava EXCLUSIVA do arquivo). Devolve a linha gravada,
    ou `None` quando a chave não está na esteira.

    `fn(row)` altera a linha no lugar; levantar dentro dela desfaz tudo (é como
    o `mark_validated` recusa o atraso sem justificativa).

    Existe porque cada pessoa roda a PRÓPRIA instância sobre o mesmo `db/`: MO e
    FO validam em paralelo, e o desenho `find_row` → alterar → `upsert_row`
    (linha inteira) fazia a segunda gravação apagar a assinatura da primeira —
    o MO lia, o FO lia, o MO gravava, o FO gravava a cópia dele com o `VALIDADO
    p/ MO` vazio. Uma trava em memória não alcança o outro processo; a trava do
    arquivo, sim, e ela já é paga pela gravação.

    A linha que muda de banco (a esteira fechou → ok; reabriu → pending) é
    gravada no DESTINO antes de sair da origem — no pior caso sobra uma
    duplicata, nunca uma operação perdida (§546)."""
    k = str(key or '').strip()
    if not k:
        return None
    if duckdb is None:
        raise RuntimeError('duckdb indisponível: a esteira não grava')
    cols = ', '.join('"{}"'.format(c) for c in DB_COLUMNS)
    ph = ', '.join('?' for _ in DB_COLUMNS)
    del_sql = 'DELETE FROM {} WHERE trim("{}") = ?'.format(TABLE, KEY_COLUMN)
    ins_sql = 'INSERT INTO {} ({}) VALUES ({})'.format(TABLE, cols, ph)
    # O cadastro de validação é lido ANTES de pedir a trava: dentro dela seria
    # uma ida ao share com a esteira presa para todas as instâncias.
    rules = validation_rules()
    for cat in ('pending', 'ok'):
        path = db_path(cat)
        ensure_db(path)
        if not _store.isfile(path):
            continue
        with duckdb_write(path) as con:
            r = con.execute(_SEL_ROW.format(cols, TABLE, KEY_COLUMN), [k]).fetchone()
            if r is None:
                continue
            row = {c: ('' if v is None else str(v)) for c, v in zip(DB_COLUMNS, r)}
            fn(row)
            refresh_derived(row, rules)
            vals = [str(row.get(c, '') or '') for c in DB_COLUMNS]
            target = target_category(row)
            if target != cat:
                _write_exec(target, [(del_sql, [k]), (ins_sql, vals)], raise_errors=True)
            con.execute(del_sql, [k])
            if target == cat:
                con.execute(ins_sql, vals)
            return row
    return None


# Recalculadas a cada gravação — nunca "mudança" de quem editou.
_DERIVED_ON_SAVE = ('Pending', 'Aging Confirmação')


def changes_between(antes, depois):
    """As colunas que a edição MUDOU (`depois` × `antes`), para `save_changes`.

    `Pending` é derivada, com UMA exceção gravada à mão: o hold `Pending Legal`
    (§254). Pôr o hold é mudança; tirá-lo (o Legal Release, ou o `Pending OTC`
    da grade numa linha em hold) grava vazio e deixa a derivação decidir."""
    ch = {}
    for c in DB_COLUMNS:
        if c in _DERIVED_ON_SAVE:
            continue
        novo = str((depois or {}).get(c, '') or '')
        if novo != str((antes or {}).get(c, '') or ''):
            ch[c] = novo
    legal_antes = upper_norm((antes or {}).get('Pending')) == upper_norm(PENDING_LEGAL)
    legal_depois = upper_norm((depois or {}).get('Pending')) == upper_norm(PENDING_LEGAL)
    if legal_depois and not legal_antes:
        ch['Pending'] = PENDING_LEGAL
    elif legal_antes and not legal_depois:
        ch['Pending'] = ''
    return ch


def save_changes(antes, depois):
    """Grava só o que mudou de `antes` para `depois`, sobre a linha RELIDA sob a
    trava (`mutate_row`) — a edição de quem abriu a tela antes não desfaz a
    validação que outra mesa deu nesse meio. Devolve a linha gravada, ou
    `None` quando ela saiu da esteira."""
    key = str((antes or {}).get(KEY_COLUMN, '') or (depois or {}).get(KEY_COLUMN, '') or '').strip()
    ch = changes_between(antes, depois)
    if not ch:
        return find_row(key)
    return mutate_row(key, lambda row: row.update(ch))


def delete_row(key):
    for cat in ('pending', 'ok'):
        _delete_key(cat, key)


def row_untouched(key):
    """A linha da esteira ainda NAO foi tocada pela mesa?

    "Tocada" e qualquer carimbo que so uma pessoa poe: o documento gerado, as
    tres validacoes (com os seus time stamps), o callback e o envio ao cliente.
    A pergunta existe para quem APAGA a operacao de origem: apagar a linha
    junto e o certo enquanto ela e so uma pendencia aberta — e e destruir
    registro de maker/checker depois que alguem assinou.

    Linha que nao existe e "nao ha o que preservar" (True): quem pergunta
    quer saber se pode seguir.
    """
    row = find_row(key)
    if row is None:
        return True
    marcas = ['Data envio validação OTC', 'Data Callback', SENT_COLUMN]
    marcas += [c for par in STAGE_COLUMNS.values() for c in par]
    return not any(_filled(row, c) for c in marcas)


def find_row(key):
    """A linha de um Trade ID, olhando os dois bancos.

    `None` quer dizer que a operação NÃO ESTÁ na esteira — nunca "não deu para
    ler": quem pergunta costuma gravar em seguida (a grade do Track, o espelho
    do New Deals, as validações), e a leitura que falha LEVANTA (§546)."""
    k = str(key or '').strip()
    if not k:
        return None
    for r in load_all(strict=True):
        if str(r.get(KEY_COLUMN, '') or '').strip() == k:
            return r
    return None


# O que só a ORIGEM da operação preenche (o espelho do New Deals, a planilha):
# linha sem nenhum deles é a casca que o §546 deixava — Trade ID, callback,
# FepWeb ID e nada que diga que operação é.
IDENTITY_COLUMNS = ('Produto', 'Cliente', 'Data Operação', 'Notional')


def is_hollow(row):
    """A linha é uma CASCA — tem chave e nenhum dado da operação?"""
    return bool(str((row or {}).get(KEY_COLUMN, '') or '').strip()) and \
        not any(_filled(row, c) for c in IDENTITY_COLUMNS)


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
    return _set_cells('E-mail Subject', pairs)


def set_fepweb_ids(pairs):
    """Grava o numeroContrato do FepWeb na coluna 'Nome fep' (rótulo FepWeb ID).

    `pairs` é {Trade ID: numeroContrato}. A FONTE é a coluna FepWeb ID do
    Pending Confirmation, gravada pela geração da confirmação
    (`_conf_pc_set_fepweb`) — o elo é o mesmo do `_mc_pc_sync`
    (MC `Trade ID` = PC `Trade Number`). Mesmo contrato do E-mail Subject:
    lote inteiro, só o que mudou.
    """
    return _set_cells('Nome fep', pairs)


def _set_cells(column, pairs):
    """Grava `pairs` ({Trade ID: valor}) na coluna, em lote, só o que mudou.

    Recebe o LOTE inteiro de propósito (um `find_row` por chave releria os dois
    bancos dezenas de vezes) e o valor igual não escreve nada — sem isso, cada
    sincronização reescreveria a esteira inteira sem uma célula mudar."""
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
        if not novo or str(row.get(column, '') or '').strip() == novo:
            continue
        # Só a CÉLULA, sobre a linha relida sob a trava: a leitura acima é do
        # começo do request, e gravar a linha inteira dela desfazia a validação
        # que outra mesa deu nesse meio (o Monitor sincroniza a cada abertura).
        if mutate_row(chave, lambda r, v=novo: r.__setitem__(column, v)) is not None:
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
    def _carimba(row):
        if link:
            row['Confirmation Link'] = str(link)
        if subject and not _filled(row, 'E-mail Subject'):
            row['E-mail Subject'] = str(subject)
        if not _filled(row, 'Data envio validação OTC'):
            row['Data envio validação OTC'] = fmt_date(when or datetime.now().date())
    return mutate_row(key, _carimba)


class SlaCommentRequired(Exception):
    """Carimbo fora do prazo sem justificativa.

    Exceção, e não um `return None`: quem chama precisa distinguir "não achei a
    linha" de "achei e recusei", para a tela pedir o comentário em vez de dizer
    que a confirmação não existe.
    """


class StageNotPending(Exception):
    """MO/FO assinando antes do OTC. A mensagem é o Trade ID."""


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
    if stage not in (STAGE_OTC, STAGE_MO, STAGE_FO):
        return None
    comment = str(comment or '').strip()

    def _valida(row):
        # O prazo é medido na linha RELIDA sob a trava (`mutate_row`): é ela
        # que vai ser gravada, e levantar aqui desfaz a transação inteira.
        #
        # A ETAPA também: MO e FO conferem o documento que o OTC validou, e
        # assinar antes dele era possível por POST direto. E validar de novo
        # uma etapa já validada não troca o carimbo de quem assinou primeiro.
        rule, _found = rule_for(row.get('Produto'), row.get('LOB'))
        if stage != STAGE_OTC and rule[STAGE_OTC] and not _filled(row, 'Conferido OTC'):
            raise StageNotPending(str(row.get(KEY_COLUMN, '') or key).strip())
        if _filled(row, STAGE_COLUMNS[stage][0]):
            return
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
        else:
            row['VALIDADO p/ FO'] = hoje
            row['Time Stamp FO'] = stamp_now(sid)
    return mutate_row(key, _valida)


def reject(key, stage, sid, comment):
    """Reject de MO ou FO: a confirmação volta para Pending OTC.

    Limpa o Conferido OTC **e** as validações já dadas: o documento vai ser
    refeito, e um 'VALIDADO p/ MO' carimbado sobre a versão anterior seria um
    aval que ninguém deu à versão nova. O carimbo do reject fica na coluna do
    estágio que rejeitou, para a tela poder dizer quem devolveu e quando.
    """
    def _rejeita(row):
        for col in ('Conferido OTC', 'Time Stamp OTC', 'VALIDADO p/ MO', 'Time Stamp MO',
                    'VALIDADO p/ FO', 'Time Stamp FO', 'Data envio validação MO/FO'):
            row[col] = ''
        row['Time Stamp %s' % stage] = 'REJEITADO %s' % stamp_now(sid)
    return mutate_row(key, _rejeita)


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
    # As RECOMPRAS (§488). O Pending Confirmation as classifica por produto
    # recomprado ('UNWIND NDF', 'UNWIND SWAP'…, os valores do Product Type
    # daquela tela), mas o DOCUMENTO de todas é um só — o Termo de Resilição —,
    # e por isso todas caem no mesmo tipo e na mesma pasta. Sem estas linhas o
    # `confirmation_type` devolveria 'UNWIND NDF' como se fosse um tipo, e a
    # linha cairia no DEFAULT_RULE da validação, sem ninguém ter decidido nada.
    'UNWIND NDF':         'TERMO DE RESILICAO',
    'UNWIND NDF COMM':    'TERMO DE RESILICAO',
    'UNWIND OPTION':      'TERMO DE RESILICAO',
    'UNWIND OPTION COMM': 'TERMO DE RESILICAO',
    'UNWIND SWAP':        'TERMO DE RESILICAO',
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


# O produto RECOMPRADO no rótulo do card, por Product Type da recompra. O
# **tipo** do documento é um só para toda recompra — TERMO DE RESILICAO, venha
# ela de termo, opção ou swap —, e é ele que escolhe a pasta e a regra de
# validação; na FILA do Monitor, porém, três cards com o mesmo nome não dizem
# qual operação cada um distrata (mesa, 18/09/2026). Isto é RÓTULO de tela, não
# um de-para de negócio: o tipo continua sendo o que o cadastro e a pasta usam,
# e cada fase nova da recompra acrescenta uma linha aqui junto com o seu
# Product Type.
_UNWIND_PRODUCT_LABEL = {'UNWIND NDF': 'NDF FX'}


def confirmation_label(produto, lob=''):
    """O nome que a TELA mostra para a confirmação: o tipo do documento e,
    na recompra, o produto que foi recomprado (`TERMO DE RESILICAO NDF FX`).

    Só rótulo. Quem resolve pasta, cadastro de validação e Confirmation Type
    continua sendo o `confirmation_type` — juntar as duas coisas classificaria
    a recompra num tipo que não existe em lugar nenhum."""
    tipo = confirmation_type(produto, lob)
    extra = _UNWIND_PRODUCT_LABEL.get(upper_norm(produto)) if tipo else ''
    return '{} {}'.format(tipo, extra) if extra else tipo


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
                  'Trade ID', 'Aging Confirmação', 'Confirmation Link')


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
    """A chave do card. Confirmação JÁ GERADA agrupa pelo DOCUMENTO: o
    `Confirmation Link` que a geração carimba em TODA operação que o PDF cobre
    (`mark_generated`). É ele, e não os campos, que diz quais operações são a
    mesma confirmação — os campos podem divergir da segregação que montou o
    documento:

      * commodity com `Commodities` em branco no deal: o documento a juntava
        pelo Subjacente e a esteira gravava o código B3 na Moeda. 6 operações
        num PDF viravam cards de 5 + 1, e o Validate carimbava só as 5;
      * linha antiga (antes do §457) com Moeda `BRL`: o USD e o EUR do mesmo
        cliente num card só, que mostrava — e validava — o PDF de um deles
        para os dois (#OTC-0043).

    Sem link (ainda não gerada), valem os campos."""
    link = str(row.get('Confirmation Link', '') or '').strip()
    if link:
        return ('link', link)
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
            item['Tipo'] = confirmation_label(r.get('Produto'), r.get('LOB'))
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
                item['Tipo'] = confirmation_label(r.get('Produto'), r.get('LOB'))
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
