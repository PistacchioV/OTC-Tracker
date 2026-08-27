# -*- coding: utf-8 -*-
"""As escritas do MtM — a geração das linhas do arquivo B3 (por livro e para o
COE), a gravação na pasta do Batch Conecta e o batimento contra o retorno.
"""
import os
import traceback
from datetime import datetime

from apps.pages.features.mtm import domain
from apps.pages.features.mtm.infra import persistence

def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _mtm_fi_registro_fields():
    """Campos do bloco de registro do cadastro MID — rótulos (preview) e
    larguras (fatiar a linha pronta de volta em células)."""
    tpl = _R()._fi_tpl_cached(domain._MTM_FI_KEY)
    block = next((b for b in (tpl or {}).get('blocks', [])
                  if b.get('id') == 'registro-emissao'), None)
    if block is None:
        raise ValueError('file-interpreter template missing: {}/registro-emissao'.format(domain._MTM_FI_KEY))
    return block.get('fields', [])


def _mtm_cpty_of(row):
    """Lawton / Atacama / None from the book row's CONTRAPARTE / Conta (idx 4)."""
    acct = _R()._acc_digits(row[4] if len(row) > 4 else '')
    if acct == domain._MTM_GEN_LAWTON_ACCT:
        return 'LAWTON'
    if acct in domain._MTM_GEN_ATACAMA_ACCT:
        return 'ATACAMA'
    return None


def _mtm_swap_line(cid, party_key, sinal, v, ymd):
    """UMA linha de registro (tipo 1): literais Fixed saem do cadastro; os
    valores calculados entram por seq e são usados verbatim — byte a byte o
    que sempre foi enviado."""
    return _R()._fi_build_line(domain._MTM_FI_KEY, 'registro-emissao', {
        '4': domain._mtm_rand_meunum(), '5': str(cid or ''),
        '6': domain._MTM_GEN_PARTY[party_key], '7': domain._MTM_GEN_PARTY_ACCT[party_key],
        '8': sinal, '9': domain._mtm_valor_fixed(domain._mtm_gen_min_value(v), 10),
        '12': ymd,
    }, page_url='/mtm-swap')


def _mtm_swap_header(party_key, today):
    """Linha de header (tipo 0) — literais e larguras do cadastro; participante
    e data entram por seq."""
    return _R()._fi_build_line(domain._MTM_FI_KEY, 'header',
                          {'4': domain._MTM_GEN_PARTY[party_key], '5': today},
                          page_url='/mtm-swap')


def _mtm_generate_book(book_key, rows, ymd):
    """Files for one swap book: MtM_BANCO-<suffix> always; plus the book's fixed
    counterparty file (EDG→Atacama, CEM/Hybrids→Lawton) with the mirror rows
    (opposite sign) for that book's intragroup contracts."""
    suffix = domain._MTM_GEN_BOOK_SUFFIX.get(book_key)
    if not suffix:
        return {}
    book_cpty = domain._MTM_GEN_BOOK_CPTY.get(book_key)     # ATACAMA (EDG) / LAWTON (CEM,HYB)
    today = datetime.now().strftime('%Y%m%d')
    banco = 'MtM_BANCO-' + suffix
    files = {banco: {'view': 'BANCO',
                     'header': _mtm_swap_header('BANCO', today), 'lines': []}}
    for row in rows:
        v = _R()._mtm_parse_num(row[7]) or 0.0            # Valor MTM (display) → float
        cid = row[0]
        sinal = '00' if v >= 0 else '01'
        files[banco]['lines'].append(_mtm_swap_line(cid, 'BANCO', sinal, v, ymd))
        # Mirror only the rows whose counterparty matches the book's fixed side.
        if book_cpty and _mtm_cpty_of(row) == book_cpty:
            fn = 'MtM_' + book_cpty + '-' + suffix
            files.setdefault(fn, {'view': book_cpty,
                                  'header': _mtm_swap_header(book_cpty, today), 'lines': []})
            files[fn]['lines'].append(_mtm_swap_line(cid, book_cpty, '01' if v >= 0 else '00', v, ymd))
    return files


def _mtm_generate_coe(rows, ymd):
    today = datetime.now().strftime('%Y%m%d')
    f = {'view': 'BANCO', 'cols': domain._MTM_GEN_COE_COLS, 'header': domain._mtm_coe_header(today), 'rows': []}
    for row in rows:
        v = _R()._mtm_parse_num(row[domain._MTM_COE_VALOR_IDX]) or 0.0
        f['rows'].append({
            'Tipo IF': 'COE  ', 'Tipo de Linha': '1', 'Código operação': '0475',
            'Código do Instrumento Financeiro': str(row[0] or ''), 'Conta do Emissor': '73760401',
            'Data Referência': ymd, 'Valor MTM': domain._mtm_valor_fixed(domain._mtm_gen_min_value(v), 16),
            'Débito/Crédito': '+' if v >= 0 else '-',
        })
    return {'MtM_BANCO-COE': f}


def _mtm_write_gen_files(files, ymd):
    """Write each file (.txt, Latin-1, CRLF) to CONECTA_NEW_PATH and the day's MTM
    source folder. Returns list of written paths (best-effort)."""
    dests = [_R().CONECTA_NEW_PATH, persistence._mtm_source_dir(ymd)]
    written = []
    for fname, fdata in files.items():
        content = '\r\n'.join(domain._mtm_file_lines(fdata)) + '\r\n'
        for d in dests:
            try:
                os.makedirs(d, exist_ok=True)
                path = os.path.join(d, fname + '.txt')
                with open(path, 'w', encoding='latin-1', newline='') as fh:
                    fh.write(content)
                written.append(path)
            except Exception:
                _R().log.error('[mtm] write %s → %s failed:\n%s', fname, d, traceback.format_exc())
    return written


def _mtm_gen_preview(files):
    """Preview payload: per file, the parsed columns/rows for the modal table.
    Arquivos MID são fatiados de volta da linha PRONTA pelas larguras do
    cadastro — os rótulos vêm dos `field` do template, então renomear/editar
    pela tela muda o preview no próximo duplo clique."""
    out = []
    for fn, fd in files.items():
        if 'lines' in fd:
            cols, cuts, pos = [], [], 0
            for f in _mtm_fi_registro_fields():
                w = _R()._fi_width(f.get('format')) or 0
                cols.append(f.get('field', ''))
                cuts.append((pos, pos + w))
                pos += w
            rows = [[ln[a:b] for a, b in cuts] for ln in fd['lines']]
        else:
            cols = fd['cols']
            rows = [[r[c] for c in fd['cols']] for r in fd['rows']]
        out.append({'filename': fn + '.txt', 'view': fd['view'], 'cols': cols,
                    'header': fd['header'], 'rows': rows})
    return out


def _mtm_run_recon(data, rows):
    """Build {ID → registered MtM} from the ConsultaInformacoesAtualizMID rows (house
    account only) and flag each page row Success/Check by value equality. Mutates
    data (recon map + status). Returns a summary dict."""
    fmap = {}
    for i in range(domain._MTM_RECON_DATA_ROW, len(rows)):
        row = rows[i]
        if _R()._acc_digits(_R()._cc_cell(row, domain._MTM_FILTER_COL)) != domain._MTM_ACCOUNT:      # col D
            continue
        key = domain._mtm_recon_key(_R()._cc_cell(row, 0))                              # col A
        val = domain._mtm_parse_num_br(_R()._cc_cell(row, domain._MTM_RECON_VALUE_COL))        # col G (BRL format)
        if not key or val is None:
            continue
        fmap.setdefault(key, round(val, 2))

    recon_out, ok_rows, check_rows = {}, 0, 0
    for lob, table in (data.get('tables') or {}).items():
        vidx = domain._MTM_COE_VALOR_IDX if lob == 'COE' else domain._MTM_VALOR_IDX
        for r in table or []:
            if not r or len(r) < 5:
                continue
            key = domain._mtm_recon_key(r[0])
            if key not in fmap:
                continue
            fv = fmap[key]
            pv = _R()._mtm_parse_num(r[vidx])
            # Compare against the value we'd register: a page 0.00 is generated as
            # 0.01 (B3 rejects a zero MtM), so it should reconcile with the file's 0.01.
            ok = (pv is not None and round(domain._mtm_gen_min_value(pv), 2) == fv)
            recon_out[str(r[-1])] = {'ok': ok, 'file': '{:,.2f}'.format(fv)}
            r[-4] = 'Success' if ok else 'Check'                            # status
            if ok: ok_rows += 1
            else:  check_rows += 1
    data['recon'] = recon_out
    return {'success_rows': ok_rows, 'check_rows': check_rows, 'map_entries': len(fmap)}
