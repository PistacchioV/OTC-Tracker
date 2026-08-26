# -*- coding: utf-8 -*-
"""Os arquivos do card e o store dos pares de re-booking do FWD Start."""
import json
import os
import traceback

from apps.pages.data_paths import data_dir
from apps.pages.features.mdea import domain


def _routes():
    """Busca ATRASADA — ver `features/support/infra/persistence.py`.

    `_DAILY_METRIC_DIR`, o claim de slot diário, o `_cache_lock`, o
    `_atomic_write_json`, o `_generic_nd_cfg` e o `log` são plataforma e moram
    no `routes`; e os testes trocam atributos lá.
    """
    from apps.pages import routes
    return routes


def metric_dir():
    return _routes()._DAILY_METRIC_DIR


def recipients_file():
    return os.path.join(metric_dir(), 'manual_deals_ea_recipients.json')


def status_file():
    return os.path.join(metric_dir(), 'manual_deals_ea_status.json')


def claim_file():
    return os.path.join(metric_dir(), 'manual_deals_ea_sent.json')


# Onde o par (vanilla ↔ FWD Start) é gravado, no arquivo do dia da FIXAÇÃO — que
# é o dia em que o e-mail sai, e por isso a chave de leitura.
#
# ⚠️ FORA do `NEW_DEALS_CACHE_ROOT`. Este store nasceu lá dentro
# (`NDF/FwdStartRebooks`) e o New Deals Monitor criou um card sozinho para ele,
# na seção Others: o Monitor varre o cache e trata **todo diretório novo como um
# produto**, que é o que faz um produto novo aparecer sem código. O par de
# re-booking não é um produto — é estado da rotina Manual Deals EA —, e por isso
# ele mora no cache DELA.
REBOOK_DIR = os.path.normpath(os.path.join(
    data_dir(), 'cache', 'manual-deals-ea', 'fwdstart-rebooks'))


def rebook_path(ref):
    return os.path.join(REBOOK_DIR, ref.strftime('%Y'), ref.strftime('%m'),
                        ref.strftime('%Y%m%d') + '_fwdstart_rebooks.json')


def record_rebooks(rebooks, ref):
    """Grava os pares (vanilla, FWD Start) do dia da fixação.

    Read-modify-write sob o `_cache_lock`, como todo cache-dia: o pull roda em
    thread de scheduler e pode encontrar o arquivo já escrito por uma corrida
    anterior do mesmo dia (a API é puxada a cada 20 min). A chave da deduplicação
    é o **Deal do vanilla** — o mesmo par reaparece em toda corrida seguinte
    enquanto a API devolver o registro.
    """
    if not rebooks:
        return
    R = _routes()
    path = rebook_path(ref)
    with R._cache_lock:
        try:
            with open(path, encoding='utf-8') as fh:
                atual = json.load(fh)
            if not isinstance(atual, list):
                atual = []
        except (IOError, OSError, json.JSONDecodeError):
            atual = []
        vistos = {str(r.get('Deal') or '') for r in atual if isinstance(r, dict)}
        novos = 0
        for d, fwd in rebooks:
            deal = str(d.get('Deal') or '').strip()
            if not deal or deal in vistos:
                continue
            vistos.add(deal)
            novos += 1
            fwd = fwd if isinstance(fwd, dict) else {'deal': fwd}
            atual.append({
                'Deal': deal,
                'FwdStartDeal': str(fwd.get('deal') or '').strip(),
                # A Trade Date do FWD START (não a do vanilla): é ela que diz se
                # a operação foi bookada e fixou no mesmo dia — ver
                # `queries.rows`.
                'FwdStartTradeDate': str(fwd.get('trade') or '').strip(),
                'Client': str(d.get('Client') or '').strip(),
                'Acronym': str(d.get('Acronym') or '').strip(),
                'SPN': str(d.get('SPN') or '').strip(),
                'LE': str(d.get('LE') or '').strip(),
                'TradeDate': str(d.get('TradeDate') or '').strip(),
                'SettlementDate': str(d.get('SettlementDate') or '').strip(),
            })
        if not novos:
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            R._atomic_write_json(path, atual)
        except Exception:                                   # noqa: BLE001
            R.log.warning('[manual-deals-ea] não consegui gravar os re-bookings:\n%s',
                          traceback.format_exc())


def rebook_rows(ref):
    try:
        with open(rebook_path(ref), encoding='utf-8') as fh:
            rows = json.load(fh)
    except (IOError, OSError, json.JSONDecodeError):
        return []
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def day_deals(product, ref):
    """Deals do arquivo-dia de um produto genérico de NDF."""
    cfg = _routes()._generic_nd_cfg(product)
    if not cfg:
        return []
    path = os.path.join(cfg['dir'], ref.strftime('%Y'), ref.strftime('%m'),
                        ref.strftime('%Y%m%d') + cfg['suffix'])
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (IOError, OSError, json.JSONDecodeError):
        return []
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def load_recipients():
    try:
        with open(recipients_file(), encoding='utf-8') as fh:
            d = json.load(fh)
        if isinstance(d, dict):
            return {'to': str(d.get('to', '') or ''),
                    'cc': str(d.get('cc', domain.CC_DEFAULT) or '')}
    except Exception:                                       # noqa: BLE001
        pass
    return {'to': '', 'cc': domain.CC_DEFAULT}


def save_recipients(d):
    os.makedirs(metric_dir(), exist_ok=True)
    atual = load_recipients()
    # Merge, não substituição: o payload traz o que está na tela, e uma tela que
    # não conhecesse uma das chaves apagaria aquela lista ao gravar.
    for k in ('to', 'cc'):
        if k in (d or {}):
            atual[k] = str((d or {}).get(k) or '').strip()
    _routes()._atomic_write_json(recipients_file(), atual)


def claim_slot(slot):
    """Reserva o disparo EM DISCO — a instância reinicia várias vezes ao dia e o
    catch-up precisa saber o que já saiu, senão o mesmo e-mail vai embora a cada
    subida."""
    R = _routes()
    return R._claim_daily_slot(claim_file(), metric_dir(), slot, 32, 'manual-deals-ea')


def release_slot(slot):
    """Devolve o slot quando o envio falhou (SMTP fora do ar): o catch-up da
    próxima volta tenta de novo. Sem isto uma falha transitória custaria o
    e-mail do dia."""
    _routes()._release_daily_slot(claim_file(), slot, 'manual-deals-ea')


def write_status(kind, result, when):
    R = _routes()
    try:
        os.makedirs(metric_dir(), exist_ok=True)
        atual = read_status()
        atual[kind] = {'result': result, 'at': when.strftime('%d/%m/%Y %H:%M:%S')}
        R._atomic_write_json(status_file(), atual)
    except Exception:                                       # noqa: BLE001
        R.log.warning('[manual-deals-ea] não consegui gravar o status:\n%s',
                      traceback.format_exc())


def read_status():
    try:
        with open(status_file(), encoding='utf-8') as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:                                       # noqa: BLE001
        return {}
