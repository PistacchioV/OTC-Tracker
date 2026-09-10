# -*- coding: utf-8 -*-
"""A fachada de LEITURA sobre o armazém (`data_store`) — os nomes que o app e
os testes conhecem desde a fase 3 (`day_records`, `dataset_rows`,
`refdata_rows`, `calendar_rows`, `day_files`, `prefetch_days`…), agora todos
respondendo pelo banco e SÓ por ele (HANDOFF §434).

O que este módulo era — a leitura DB-only com cura síncrona, quarentena,
disjuntor, freio e o memo de processo — saiu com o espelho: não há mais JSON
para curar nem para cair. O que sobrou é tradução de assinatura: cada função
abaixo recebe o caminho (ou o par banco/tabela) de sempre e devolve o que o
`data_store.read` devolve. `None` continua querendo dizer "não há dado" para
quem já tratava assim.
"""
import os

from apps.pages import data_store as _S
from apps.pages import json_to_duckdb as _core

# Superfícies que os testes e o routes ainda consultam.
_LEITURA_TETO = _S._LEITURA_TETO
_OCUPADO_JANELA = _S._OCUPADO_JANELA
ocupado_forget = _S.ocupado_forget
_ocupado_marcado = _S._ocupado_marcado
day_memo_forget = _S.memo_forget
BancoOcupado = _S.BancoOcupado


def _data_root():
    return _S.data_root()


def day_payload(path):
    """O conteúdo de UM arquivo-dia (a lista original, na ordem do arquivo).
    `None` quando o banco não o tem."""
    try:
        return _S.read(path)
    except FileNotFoundError:
        return None


def day_records(path):
    """Leitura de um arquivo-dia payload-LISTA. Levanta `FileNotFoundError`
    quando não há — o `except (IOError, ...)` do chamador continua valendo."""
    return _S.read(path)


def dataset_rows(path):
    """Um JSON de DATASET (mappings, cadastros B3, Subjacente…), pelo caminho."""
    return _S.read(path)


def dataset_records(path):
    """Os registros de um dataset, ou `None` quando não há."""
    try:
        return _S.read(path)
    except FileNotFoundError:
        return None


def _rel_path(rel):
    return os.path.join(_S.data_root(), *rel.split('/'))


def raw_records(db_name, table, rel, expected_path=None, manifest_key=None):
    """Os registros originais de `rel` — pelo caminho, como tudo aqui. O par
    banco/tabela é ignorado: quem decide é o `target_of` do motor.
    `expected_path` continua sendo o guarda da superfície de patch: quem lê
    de outro arquivo lê pelo caminho dele."""
    path = expected_path if expected_path is not None else _rel_path(rel)
    try:
        return _S.read(path)
    except FileNotFoundError:
        return None


def table_rows(db_name, table, rel, schema='main', order_by=None, heal=None,
               manifest_key=None, expected_path=None, sync_kind=None):
    """As linhas de uma tabela — hoje o payload do caminho `rel`."""
    return raw_records(db_name, table, rel, expected_path=expected_path)


def refdata_rows(expected_path=None):
    return raw_records('reference_data.db', 'refdata', 'RefData.json',
                       expected_path=expected_path)


def cpd_records(expected_path=None):
    return raw_records('reference_data.db', 'counterparty_details',
                       'CounterpartyDetails.json', expected_path=expected_path)


def calendar_registry():
    """O registro de calendários — `None` quando o banco não o tem (e aí vale
    o seed da vertical)."""
    try:
        return _S.read(_rel_path(_core.REGISTRY_FILE))
    except FileNotFoundError:
        return None


def calendar_rows(path, nome=None):
    """As linhas de um arquivo de calendário: `[{'date','title','calendar'}]`,
    com a data como STRING ISO. `None` quando não há."""
    try:
        linhas = _S.read(path)
    except FileNotFoundError:
        return None
    if not isinstance(linhas, list):
        return None
    out = []
    for r in linhas:
        if not isinstance(r, dict):
            continue
        d = r.get('date', '')
        out.append({'date': d.isoformat() if hasattr(d, 'isoformat') else (d or ''),
                    'title': r.get('title', r.get('name', '')) or '',
                    'calendar': r.get('calendar', '') or (nome or '')})
    return out


def calendar_dates(path, nome=None):
    linhas = calendar_rows(path, nome=nome)
    if linhas is None:
        return None
    return {r['date'] for r in linhas if r.get('date')}


def day_files(raiz, sufixo=''):
    """`(caminho, nome, mtime, tamanho)` dos arquivos-dia de uma árvore, pelo
    banco. `None` quando a árvore não tem banco nenhum."""
    itens = list(_S.day_files(raiz, sufixo=sufixo))
    return itens if itens else (None if not _S.isdir(raiz) else [])


def prefetch_days(dias):
    """Aquece o memo para as triplas do `_day_files`: `{caminho: registros}`."""
    caminhos = []
    for item in (dias or []):
        try:
            caminhos.append(item[0])
        except (TypeError, IndexError):
            continue
    return _S.prefetch(caminhos)
