# -*- coding: utf-8 -*-
"""Escrita da tela Strategy: import dos arquivos da B3, Edit e Delete.

Todo ciclo é read-modify-write INTEIRO sob o `_cache_lock` (§4): lê o
cadastro fresco, altera, grava pelo funil. Leitura que falha SOBE — lida como
vazia, a gravação seguinte apagaria o cadastro inteiro.
"""
import os
from datetime import datetime

from apps.pages.features.swap_strategy import domain, queries

# Só o que o usuário edita no modal: o contrato é a chave, e Status,
# Contraparte e LOB são calculados.
EDITABLE = ('StrategyCode', 'StrategyName')
MAX_BYTES = 20 * 1024 * 1024


class CommandError(Exception):
    def __init__(self, code, params=None, status=400):
        super().__init__(code)
        self.code = code
        self.params = params or {}
        self.status = status


def _R():
    from apps.pages import routes
    return routes


def _save(entries):
    fp = queries.store_path()
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    _R()._atomic_write_json(fp, entries)


def _now():
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%S')


def parse_file(raw, file_name):
    """Bytes do arquivo → o `parse_rows` do domain. O formato é o do CONTEÚDO
    (tsv, csv, xls, xlsx, tabela HTML com nome .xls): o leitor é o mesmo do
    Latam (`_latam_read_rows`)."""
    if not raw:
        raise CommandError('strategy_file_empty_upload')
    if len(raw) > MAX_BYTES:
        raise CommandError('strategy_file_too_large')
    R = _R()
    fmt = R._latam_sniff_format(raw)
    try:
        if fmt == 'text':
            rows = _read_text(raw)
        else:
            rows, fmt = R._latam_read_rows(raw)
    except Exception as exc:                                   # noqa: BLE001
        raise CommandError('strategy_file_unreadable',
                           {'motivo': '{}: {}'.format(type(exc).__name__, exc)})
    try:
        return domain.parse_rows(rows)
    except domain.StrategyFileError as exc:
        raise CommandError(exc.code, exc.params)


def _read_text(raw):
    """Texto delimitado. O separador sai da linha do CABEÇALHO ("Código do
    Contrato"), não da primeira: o título "B3 S.A. - BRASIL, BOLSA, BALCÃO"
    tem vírgulas, e escolhido por ele o arquivo inteiro partiria errado."""
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1252', errors='replace')
    lines = text.splitlines()
    alvo = next((ln for ln in lines if domain.COL_CONTRACT in domain.norm_label(ln)), '')
    sep = max(('\t', ';', ',', '|'), key=lambda s: alvo.count(s))
    if not alvo.count(sep):
        sep = '\t'
    return [ln.split(sep) for ln in lines]


def import_file(raw, file_name, sid=''):
    parsed = parse_file(raw, file_name)
    with _R()._cache_lock:
        atual = queries.read_all()
        novo, novos, atualizados = domain.merge(atual, parsed, file_name, sid, _now())
        _save(novo)
    return {'kind': parsed['kind'], 'consulta': parsed['consulta'],
            'contracts': len(parsed['records']), 'new': novos, 'updated': atualizados}


def edit(contract, fields, sid=''):
    k = domain.norm_contract(contract)
    mudou = {f: str(v if v is not None else '').strip()
             for f, v in (fields or {}).items() if f in EDITABLE}
    if not k:
        raise CommandError('strategy_not_found', status=404)
    with _R()._cache_lock:
        atual = queries.read_all()
        alvo = next((e for e in atual if domain.norm_contract(e.get('Contract')) == k), None)
        if alvo is None:
            raise CommandError('strategy_not_found', status=404)
        alvo.update(mudou)
        alvo['EditedBy'] = sid
        alvo['EditedAt'] = _now()
        _save(atual)
    return alvo


def delete(contracts):
    ks = {domain.norm_contract(c) for c in (contracts or []) if domain.norm_contract(c)}
    if not ks:
        raise CommandError('strategy_no_rows')
    with _R()._cache_lock:
        atual = queries.read_all()
        resto = [e for e in atual if domain.norm_contract(e.get('Contract')) not in ks]
        removidos = len(atual) - len(resto)
        if removidos:
            _save(resto)
    return removidos
