# -*- coding: utf-8 -*-
"""Disco: os destinatários do card, as raízes de origem/destino no share, a
cópia do arquivo do dia e o JSON de posição (VCP) que a rotina alimenta.

As RAÍZES (`CETIP_SOURCE_ROOT`/`CETIP_DEST_ROOT`) ficam no `routes`: recon_fxo
e recon_cgd leem a mesma raiz de destino — são plataforma (§8: nenhum módulo
escreve a raiz à mão).
"""
import os
import traceback

from apps.pages.features.cetip import domain


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


_CETIP_RECIPIENTS_FILE = os.path.normpath(os.path.join(
    _R().data_dir(), 'control-panel',
    'cetip_distribution_recipients.json'))


def _load_cetip_recipients():
    try:
        with open(_CETIP_RECIPIENTS_FILE, encoding='utf-8') as fh:
            d = _R().json.load(fh)
        if isinstance(d, dict):
            return {k: d.get(k, '') or '' for k in domain._CETIP_RECIPIENT_KEYS}
    except Exception:
        pass
    return {k: '' for k in domain._CETIP_RECIPIENT_KEYS}


def _save_cetip_recipients(rec):
    """Grava as três listas. Recebe o DICIONÁRIO inteiro, não um argumento por
    lista: com três chaves, uma assinatura posicional deixaria uma chamada de dois
    argumentos apagar a terceira em silêncio — que é justamente o que o POST
    fazia quando o payload vinha sem uma delas (ver `_cetip_merge_recipients`)."""
    os.makedirs(os.path.dirname(_CETIP_RECIPIENTS_FILE), exist_ok=True)
    with open(_CETIP_RECIPIENTS_FILE, 'w', encoding='utf-8') as fh:
        _R().json.dump({k: str((rec or {}).get(k, '') or '') for k in domain._CETIP_RECIPIENT_KEYS},
                  fh, ensure_ascii=False, indent=2)


def _cetip_merge_recipients(payload):
    """As listas salvas com as do payload por cima — só as chaves que VIERAM.

    Sobrescrever as três com o que o payload traz apagaria a lista de quem não
    está no corpo: o botão Run manda o que está na tela, e uma tela antiga (ou um
    POST de fora) não conhece a chave nova. Devolve (rec, mudou)."""
    rec = _load_cetip_recipients()
    mudou = False
    for k in domain._CETIP_RECIPIENT_KEYS:
        if k in (payload or {}):
            rec[k] = str(payload.get(k) or '').strip()
            mudou = True
    return rec, mudou


def _ensure_cetip_roots():
    """At server start, make sure the CETIP source/destination ROOT folders exist;
    create them if missing. Windows-only (the I:\\ paths are JPM network paths) —
    skipped elsewhere so dev machines don't create junk dirs from backslash paths."""
    if os.name != 'nt':
        return
    for root in (_R().CETIP_SOURCE_ROOT, _R().CETIP_DEST_ROOT):
        try:
            if not os.path.isdir(root):
                os.makedirs(root, exist_ok=True)
                _R().log.info("[cetip] created root folder: %s", root)
        except Exception:
            _R().log.warning("[cetip] could not create root %s:\n%s", root, traceback.format_exc())


def _cetip_save_file(src_path, dest_path):
    """Replicate the Alteryx DynamicInput→DbFileOutput pass: read the raw file as
    Latin-1 (CodePage 28591) and rewrite it with CRLF line endings to the new
    location. Latin-1 is a byte-for-byte mapping, so content is preserved; only
    line endings are normalised to CRLF — matching what the KPI process expects."""
    with open(src_path, 'r', encoding='latin-1', newline='') as f:
        lines = f.read().splitlines()
    out = '\r\n'.join(lines)
    if lines:
        out += '\r\n'
    with open(dest_path, 'w', encoding='latin-1', newline='') as f:
        f.write(out)


def _cetip_update_vcp_json(src_path):
    """Refresh the existing VCP.json IN PLACE from the saved INDEXADORESSWAP_VCP
    file (';'-delimited, Latin-1). File columns: A=Qualification ID, B=Description,
    C=Additional Description, D=Level 1 Classification, E=Status (Habilitado →
    ACTIVE / Bloqueado → INACTIVE).

    Upsert by "ID da Qualificação": existing rows have their STATUS/descriptions/
    classification updated (MAKER/CHECKER preserved); new IDs are appended with
    Produto=SWAP. Rows not present in the file (e.g. the OPC entries) are left
    untouched. Best-effort — returns the path or None."""
    try:
        with open(src_path, 'r', encoding='latin-1', newline='') as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        if not lines:
            return None
        # Skip a header row if the file ships with one.
        first = [c.strip().lower() for c in lines[0].split(';')]
        if any('qualif' in c or c == 'status' or 'classif' in c or 'descri' in c for c in first):
            lines = lines[1:]

        # Load the existing table + index by Qualification ID (as string).
        current = []
        if os.path.isfile(_R().VCP_JSON):
            try:
                with open(_R().VCP_JSON, encoding='utf-8') as fh:
                    current = _R().json.load(fh) or []
            except Exception:
                current = []
        by_id = {str(r.get('ID da Qualificação')): r for r in current}

        added = updated = 0
        for ln in lines:
            f = ln.split(';')
            def g(i):
                return f[i].strip() if i < len(f) else ''
            qid_raw = g(0)
            if not qid_raw:
                continue
            try:
                qid = int(''.join(ch for ch in qid_raw if ch.isdigit() or ch == '-'))
            except ValueError:
                qid = qid_raw
            st = _R()._fcst_norm(g(4))
            status = 'ACTIVE' if 'habilitad' in st else ('INACTIVE' if 'bloquead' in st else g(4))
            row = by_id.get(str(qid))
            if row is None:
                current.append({
                    'STATUS':                              status,
                    'ID da Qualificação':                  qid,
                    'Descrição da Qualificação':           g(1),
                    'Descrição Adicional da Qualificação': g(2),
                    'Classificação Nível 1':               g(3),
                    'Produto':                             'SWAP',
                    'MAKER':                               None,
                    'CHECKER':                             None,
                })
                by_id[str(qid)] = current[-1]
                added += 1
            else:
                row['STATUS'] = status
                row['Descrição da Qualificação'] = g(1)
                row['Descrição Adicional da Qualificação'] = g(2)
                row['Classificação Nível 1'] = g(3)
                updated += 1

        with open(_R().VCP_JSON, 'w', encoding='utf-8') as fh:
            _R().json.dump(current, fh, ensure_ascii=False, indent=2)
        _R().log.info("[cetip] VCP.json refreshed: %d updated, %d added (%d total)",
                 updated, added, len(current))
        return _R().VCP_JSON
    except Exception:
        _R().log.warning("[cetip] VCP.json update failed:\n%s", traceback.format_exc())
        return None
