# -*- coding: utf-8 -*-
"""RED Clients — Rapid Exposure (§730): a regra, PURA.

A planilha diária de exposição (aba "JPM Entities-Open Settlements") traz na
coluna K o ECI dos clientes. Contraparte do Reference Data com o ECI na lista
é RED: a marca `RED` vai no registro e o STATUS vira `RED`. Na rodada seguinte
sem o ECI, a marca sai e o RED volta a ACTIVE.

A marca é separada do STATUS de propósito: um cliente PENDING (esperando
aprovação) fica PENDING — e a APROVAÇÃO lê a marca e o devolve como RED, não
como ACTIVE (`index_b3/entrypoint`, a ação `approve`).
"""
import unicodedata

SHEET = 'JPM Entities-Open Settlements'
ECI_COL = 10                 # coluna K
STATUS_RED = 'RED'
STATUS_ACTIVE = 'ACTIVE'
FLAG = 'RED'                 # o campo da marca no registro do Reference Data


def _norm(s):
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ''.join(c for c in s.upper() if c.isalnum())


def same_sheet(nome):
    """A aba é achada pelo nome sem caixa, espaço nem pontuação: o Excel de
    quem salva pode trocar o hífen ou deixar um espaço no fim."""
    return _norm(nome) == _norm(SHEET)


def eci_key(v):
    """O ECI como chave: só dígitos, sem zero à esquerda. A planilha pode
    trazê-lo como número (`220349472.0`, o xls lido pelo xlrd) e o cadastro
    como texto com zeros. Vazio ou com letra → ''."""
    if isinstance(v, float):
        if v != v or not v.is_integer():
            return ''
        v = int(v)
    s = str(v if v is not None else '').strip()
    if s.endswith('.0') and s[:-2].isdigit():
        s = s[:-2]
    if not s.isdigit():
        return ''
    return str(int(s)) if int(s) else ''


def ecis_da_aba(linhas):
    """Os ECIs da coluna K (o cabeçalho e as linhas sem ECI caem sozinhos)."""
    out = set()
    for ln in linhas or []:
        if ln is None or len(ln) <= ECI_COL:
            continue
        k = eci_key(ln[ECI_COL])
        if k:
            out.add(k)
    return out


def aplicar(registros, ecis):
    """Marca/desmarca cada contraparte NO LUGAR e devolve o resumo.

    - ECI na lista: ganha a marca; ACTIVE vira RED; RED fica; qualquer outro
      status (PENDING…, INACTIVE) fica como está — a aprovação é que o leva a
      RED;
    - ECI fora da lista: a marca sai; RED volta a ACTIVE.
    """
    entrou, saiu, red, pendentes = [], [], [], []
    casados = set()
    mudou = False
    for rec in registros or []:
        if not isinstance(rec, dict):
            continue
        k = eci_key(rec.get('ECI'))
        nome = str(rec.get('COUNTERPARTY', '') or '').strip()
        status = str(rec.get('STATUS', '') or '').strip().upper()
        if k and k in ecis:
            casados.add(k)
            if not rec.get(FLAG):
                rec[FLAG] = 'Y'
                entrou.append(nome)
                mudou = True
            if status == STATUS_ACTIVE:
                rec['STATUS'] = STATUS_RED
                mudou = True
            if rec.get('STATUS') == STATUS_RED:
                red.append(nome)
            else:
                pendentes.append({'name': nome, 'status': rec.get('STATUS') or ''})
        else:
            if rec.get(FLAG):
                rec.pop(FLAG, None)
                saiu.append(nome)
                mudou = True
            if status == STATUS_RED:
                rec['STATUS'] = STATUS_ACTIVE
                mudou = True
    return {'changed': mudou, 'entered': sorted(entrou), 'left': sorted(saiu),
            'red': sorted(red), 'flagged_not_red': pendentes,
            'eci_total': len(ecis), 'eci_matched': len(casados),
            'eci_unmatched': len(ecis - casados)}
