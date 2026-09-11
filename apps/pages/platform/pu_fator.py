# -*- coding: utf-8 -*-
"""O arquivo de *Registro de Atualização de PU / Fator (SWAP)* da B3 — o
`ACCRUAL_<VIEW>-<LOB>.txt` do Batch Conecta — gerado pelo File Interpreter
(`swap-atualizacao-pu-fator`), uma linha por perna VCP por visão (BANCO
sempre; LAWTON/ATACAMA quando a contraparte do grupo é deles).

Nasceu na feature Accrual e veio para a platform quando o Swap VCP (§452)
passou a mandar o MESMO arquivo — uma feature não importa outra (SoC-003).
O Accrual continua expondo os nomes antigos como aliases (`domain._ACC_*`,
`commands._acc_swap_records`…): os testes e o guarda de camadas os procuram
lá. A regra do papel/curva (`01` para a conta MAIOR) e o Fator sem PU (22
espaços) estão descritos no cadastro do template, não aqui.
"""
import os
import re
import traceback
from datetime import datetime

from apps.pages import data_store as _store


def _R():
    from apps.pages import routes
    return routes


ACC_FI_KEY = 'swap-atualizacao-pu-fator'            # cadastro do File Interface


VIEW_BY_PREFIX = {'73760': 'BANCO', '04880': 'BANCO', '85398': 'ATACAMA', '00041': 'LAWTON'}


VIEW_PART_NAME = {'BANCO': 'JPMORGANBM', 'LAWTON': 'INTRAGLAWTONFDO', 'ATACAMA': 'INTRAGATACAMAFDO'}


LOB_TAG = {'CEM': 'CEM', 'EDG': 'EDG', 'Hybrids': 'HYB', 'Commodities': 'COMM'}


def acc_swap_fator(f):
    """Factor → 2 integer + 8 decimal digits, no separator, absolute. 1.0 → '0100000000'."""
    try:
        n = abs(float(str(f or '').replace(',', '.')))
    except (ValueError, TypeError):
        n = 0.0
    ip, fp = '{:.8f}'.format(n).split('.')
    return ip[-2:].rjust(2, '0') + fp


ACCRUAL_SOURCE_ROOT = os.getenv('ACCRUAL_SOURCE_ROOT', os.path.join(
    _R().Config.SHARED_DRIVE_ROOT, 'Confirmation', 'Derivativos', 'OTC Tracker', 'Regulatory',
    'Accrual'))


def accrual_source_dir(ymd):
    """ACCRUAL_SOURCE_ROOT\\YYYY\\mm. Month\\DD for a 'YYYYMMDD' run date."""
    ref = datetime.strptime(ymd, '%Y%m%d')
    month_folder = ref.strftime('%m') + '. ' + _R()._EN_MONTH_NAMES[ref.month - 1]
    return os.path.join(ACCRUAL_SOURCE_ROOT, ref.strftime('%Y'), month_folder, ref.strftime('%d'))


def acc_swap_header(view, today):
    """Linha de header (tipo 0) — literais e larguras do cadastro; participante
    e data entram por seq."""
    return _R()._fi_build_line(ACC_FI_KEY, 'header',
                          {'4': VIEW_PART_NAME.get(view, view), '5': today},
                          page_url='/accrual-swap')


def acc_swap_records(row, today):
    """Return a list of {view, line} for one accrual row (empty when no VCP leg)."""
    codigo = str(row[0] or '').strip()
    accP, idxP = row[3], str(row[5] or '').strip().upper()
    accC, idxC = row[6], str(row[8] or '').strip().upper()
    fatP, fatC = row[9], row[10]
    digP = re.sub(r'\D', '', str(accP or '')); digC = re.sub(r'\D', '', str(accC or ''))
    numP = int(digP or '0'); numC = int(digC or '0')
    roleP = '01' if numP > numC else '00'
    roleC = '01' if numC > numP else '00'
    legs = []                                       # (curva, fator) per VCP leg
    if idxP == 'VCP': legs.append((roleP, fatP))
    if idxC == 'VCP': legs.append((roleC, fatC))
    if not legs:
        return []
    prefP, prefC = digP[:5], digC[:5]
    updaters = [(roleP, prefP)]                      # PARTE (our house entity) always updates
    if prefC in VIEW_BY_PREFIX and prefC != prefP:
        updaters.append((roleC, prefC))             # group counterparty also submits its view
    out = []
    for papel, pref in updaters:
        view = VIEW_BY_PREFIX.get(pref)
        if not view:
            continue
        for curva, fat in legs:
            meu = ''.join(_R().random.choice('0123456789') for _ in range(10))
            line = _R()._fi_build_line(ACC_FI_KEY, 'registro',
                                  {'4': codigo, '5': papel, '7': curva,
                                   '8': today, '9': meu,
                                   '11': acc_swap_fator(fat)},
                                  page_url='/accrual-swap')
            out.append({'view': view, 'line': line})
    return out


def accrual_file_name(view, lob_tag):
    """O nome do Accrual: `ACCRUAL_<VIEW>-<LOB>.txt`."""
    return 'ACCRUAL_{}-{}.txt'.format(view, lob_tag)


def view_of_account(acct):
    """A visão (BANCO / LAWTON / ATACAMA) de uma conta CETIP pelos cinco
    primeiros dígitos, ou '' quando a conta não é de entidade do grupo — é a
    MESMA leitura que o `acc_swap_records` faz para decidir quem atualiza."""
    return VIEW_BY_PREFIX.get(re.sub(r'\D', '', str(acct or ''))[:5], '')


def is_intragroup(conta_parte, conta_contraparte):
    """O swap é intragrupo (BANCO x LAWTON) — isto é, a contraparte é uma
    entidade do grupo com participante PRÓPRIO?

    É a MESMA pergunta que o `acc_swap_records` faz para decidir se há uma
    segunda visão atualizando: a conta da contraparte tem prefixo de grupo
    **e** de visão diferente da parte. O `!=` é o que separa a Lawton do
    omnibus do próprio Banco (73760.10-2): a conta é do grupo, mas a visão é
    a mesma — o swap ali é contra CLIENTE, e um arquivo só."""
    v = view_of_account(conta_contraparte)
    return bool(v) and v != view_of_account(conta_parte)


def vcp_file_name(view, intragrupo=False):
    """O nome do arquivo do Swap VCP (§452).

    Swap contra CLIENTE: **VCP_CLIENT.TXT** — um arquivo só, sem a LOB no
    nome (pedido da mesa). Swap **intragrupo** (BANCO x LAWTON): cada
    participante manda o SEU, e o nome diz de quem é — **VCP_BANCO.TXT** e
    **VCP_LAWTON.TXT**. Sem isso os dois cairiam no mesmo nome e o
    `_unique_filepath` salvaria um deles como "(1)", com a visão só legível
    dentro do header.

    A visão do cliente que não seja a do Banco (raro) entra no nome pelo
    mesmo motivo.
    """
    if intragrupo:
        return 'VCP_{}.TXT'.format(view)
    return 'VCP_CLIENT.TXT' if view == 'BANCO' else 'VCP_CLIENT_{}.TXT'.format(view)


def write_view_files(by_view, lob_tag, today, evidence_dir=None, name_fn=None):
    """Grava um arquivo por visão a partir de `{view: [linhas de registro]}` —
    no Batch Conecta e (best-effort) na pasta de evidência do dia. Devolve
    [{filename, path, view, count}].

    `name_fn(view, lob_tag)` dá o nome; sem ele vale o do Accrual
    (`ACCRUAL_<VIEW>-<LOB>.txt`), que era o miolo do `_acc_write_batch_files`.
    O Swap VCP passa o `vcp_file_name`."""
    if not by_view:
        return []
    os.makedirs(_R().CONECTA_NEW_PATH, exist_ok=True)
    if evidence_dir:
        try:
            os.makedirs(evidence_dir, exist_ok=True)
        except Exception:                                   # noqa: BLE001
            _R().log.warning('[accrual] could not create evidence dir %s:\n%s', evidence_dir, traceback.format_exc())
    generated = []
    for view in ('BANCO', 'LAWTON', 'ATACAMA'):
        lines = by_view.get(view)
        if not lines:
            continue
        content = '\n'.join([acc_swap_header(view, today)] + lines)
        fpath = _R()._unique_filepath(_R().CONECTA_NEW_PATH,
                                      (name_fn or accrual_file_name)(view, lob_tag))
        with open(fpath, 'w', encoding='utf-8') as fh:
            fh.write(content)
        if evidence_dir and _store.isdir(evidence_dir):
            try:
                with open(os.path.join(evidence_dir, os.path.basename(fpath)), 'w', encoding='utf-8') as fh:
                    fh.write(content)
            except Exception:                               # noqa: BLE001
                _R().log.warning('[accrual] evidence copy failed for %s:\n%s', fpath, traceback.format_exc())
        generated.append({'filename': os.path.basename(fpath), 'path': fpath, 'view': view, 'count': len(lines)})
    return generated

