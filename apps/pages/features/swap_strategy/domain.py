# -*- coding: utf-8 -*-
"""Regras puras da tela Strategy: ler as consultas de estratégia da B3.

Dois relatórios do MID de Swap chegam pelo dropzone, e o nome do arquivo NÃO
diz qual é (`Swap-MID-ConsultaDadosEstrategia (3).tsv`, `.csv`, `.xls`…):

- **ConsultaEstrategiaContratos** — a LISTA: Código da Estratégia · Nome da
  Estratégia · Código do Contrato, uma linha por contrato;
- **ConsultaDadosEstrategia** — os DADOS de UMA estratégia: um cabeçalho de
  título ("B3 S.A. …", "Data e Hora da Consulta: …", "Critério de Busca:") e,
  a partir da linha que começa em "Código do Contrato", uma linha por contrato
  com colunas PRÓPRIAS de cada estratégia (Indicador_1, taxa Cupom_2, Moeda_Libor…).

Os dois têm "Código do Contrato", e é por ele que tudo se casa: a linha do
cabeçalho é a que traz essa coluna (o título acima dela varia), o contrato
perde o `#` com que a B3 o escreve, e as colunas que não são identidade viram
os DADOS da estratégia, na ordem do arquivo — não há lista fixa de campo,
porque cada estratégia tem os seus.

Sem Flask, sem banco, sem `routes`.
"""
import re
import unicodedata
from datetime import date, datetime

# Colunas de IDENTIDADE: o resto da linha é dado da estratégia.
COL_CONTRACT = 'codigo do contrato'
COL_CODE = 'codigo da estrategia'
COL_NAME = 'nome da estrategia'

_CONSULTA_RE = re.compile(r'data e hora da consulta\s*:?\s*(.+)$', re.I)


class StrategyFileError(ValueError):
    """Arquivo que não é uma consulta de estratégia. Leva CÓDIGO (§486)."""

    def __init__(self, code, params=None):
        super().__init__(code)
        self.code = code
        self.params = params or {}


def norm_label(s):
    """Rótulo comparável: sem acento, minúsculo, espaços colapsados."""
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', s).strip().lower()


def norm_contract(s):
    """`#23F02430278` → `23F02430278` (a B3 escreve com `#` para o Excel não
    ler o `E` como expoente; o `#` não é do código)."""
    return re.sub(r'\s+', '', str(s or '')).lstrip('#').strip().upper()


def _br_number(v):
    """Número de planilha → texto no formato da B3 (`51.670.430,98`)."""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer() and abs(v) < 1e15):
        s = str(int(v))
        dec = ''
    else:
        # `repr` é o menor texto que volta ao mesmo float (133233419.7, e não
        # 133233419.700000003); notação científica cai no formato fixo.
        s = repr(float(v))
        if 'e' in s or 'E' in s:
            s = ('%.10f' % v).rstrip('0').rstrip('.')
        s, _, dec = s.partition('.')
    neg = s.startswith('-')
    s = s.lstrip('-')
    grupos = []
    while len(s) > 3:
        grupos.insert(0, s[-3:])
        s = s[:-3]
    grupos.insert(0, s)
    out = '.'.join(grupos) + (',' + dec if dec else '')
    return ('-' if neg else '') + out


def cell_text(v):
    """Célula → texto como a B3 mostra: data dd/mm/aaaa, número pt-BR."""
    if v is None:
        return ''
    if isinstance(v, datetime):
        return v.strftime('%d/%m/%Y')
    if isinstance(v, date):
        return v.strftime('%d/%m/%Y')
    if isinstance(v, (int, float)):
        return _br_number(v)
    return str(v).strip()


def _header_index(rows):
    for i, r in enumerate(rows):
        if any(norm_label(c) == COL_CONTRACT for c in (r or [])):
            return i
    return None


def _unique_labels(header):
    """Rótulos do cabeçalho, com repetidos numerados (`taxa`, `taxa (2)`)."""
    out, vistos = [], {}
    for c in header:
        lb = cell_text(c)
        if not lb:
            out.append('')
            continue
        n = vistos.get(lb, 0) + 1
        vistos[lb] = n
        out.append(lb if n == 1 else '{} ({})'.format(lb, n))
    return out


def parse_rows(rows):
    """Linhas de uma consulta de estratégia → `{consulta, kind, records}`.

    `records` é uma lista de `{Contract, StrategyCode, StrategyName, Details}`
    — `Details` é a lista `[[rótulo, valor], …]` na ordem do arquivo, ou `None`
    quando o arquivo é a LISTA (não traz dado de estratégia nenhum). O mesmo
    contrato repetido no arquivo fica com a ÚLTIMA linha."""
    rows = [list(r or []) for r in (rows or [])]
    hi = _header_index(rows)
    if hi is None:
        raise StrategyFileError('strategy_header_unknown')
    consulta = ''
    for r in rows[:hi]:
        for c in r:
            m = _CONSULTA_RE.search(cell_text(c))
            if m:
                consulta = m.group(1).strip()
    labels = _unique_labels(rows[hi])
    normed = [norm_label(lb) for lb in labels]
    i_contract = normed.index(COL_CONTRACT)
    i_code = normed.index(COL_CODE) if COL_CODE in normed else None
    i_name = normed.index(COL_NAME) if COL_NAME in normed else None
    ident = {i_contract, i_code, i_name}
    detail_idx = [i for i, lb in enumerate(labels) if lb and i not in ident]
    kind = 'data' if detail_idx else 'list'

    def cel(r, i):
        return cell_text(r[i]) if (i is not None and i < len(r)) else ''

    por_contrato = {}
    for r in rows[hi + 1:]:
        contrato = norm_contract(cel(r, i_contract))
        if not contrato:
            continue
        por_contrato[contrato] = {
            'Contract': contrato,
            'StrategyCode': cel(r, i_code),
            'StrategyName': cel(r, i_name),
            'Details': [[labels[i], cel(r, i)] for i in detail_idx] if detail_idx else None,
        }
    if not por_contrato:
        raise StrategyFileError('strategy_file_empty')
    return {'consulta': consulta, 'kind': kind, 'records': list(por_contrato.values())}


def merge(existing, parsed, file_name, who, now_iso):
    """Funde o que o arquivo trouxe no cadastro: `(lista nova, novos, atualizados)`.

    A chave é o contrato. O que o arquivo NÃO traz não apaga o que já está
    lá: a lista não zera os dados (ela não os tem) e os dados não zeram o nome
    da estratégia (a consulta de dados não traz o nome). Dado que veio vence
    o gravado — é a consulta mais nova da B3."""
    by = {}
    ordem = []
    for e in existing or []:
        k = norm_contract((e or {}).get('Contract'))
        if k and k not in by:
            by[k] = dict(e)
            ordem.append(k)
    novos = atualizados = 0
    for rec in parsed.get('records') or []:
        k = rec['Contract']
        cur = by.get(k)
        if cur is None:
            cur = {'_id': k, 'Contract': k, 'StrategyCode': '', 'StrategyName': '',
                   'Details': None}
            by[k] = cur
            ordem.append(k)
            novos += 1
        else:
            atualizados += 1
        if rec.get('StrategyCode'):
            cur['StrategyCode'] = rec['StrategyCode']
        if rec.get('StrategyName'):
            cur['StrategyName'] = rec['StrategyName']
        if rec.get('Details') is not None:
            cur['Details'] = rec['Details']
            cur['DetailsFile'] = file_name
            cur['DetailsQueriedAt'] = parsed.get('consulta') or ''
        cur['ImportedAt'] = now_iso
        cur['ImportedBy'] = who
    return [by[k] for k in ordem], novos, atualizados


def status_of(entry):
    """`Complete` com os dados da estratégia; `Pending` só com a lista."""
    return 'Complete' if (entry or {}).get('Details') else 'Pending'
