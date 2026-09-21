# -*- coding: utf-8 -*-
"""Leituras das recompras do catalogo: as linhas do arquivo-dia, o finder por
`_id` e a POSICAO do Live Position traduzida para as chaves canonicas que o
`product/domain` entende.

A posicao sai dos MESMOS coletores das telas de Live Position
(`_lpndf_collect`, `_lpopt_collect`) e, no swap, do mesmo DPOSICAO-SWAP que o
Swap Characteristics e o Swap Calculator leem (`platform/swap_flows`) — a
recompra e a posicao tem de mostrar o mesmo contrato do mesmo jeito. As regras
de leitura sao as ja escritas (§488/§511/§513): numero de TELA, saldo = Valor
Base − Valor Antecipado, conta comparada por DIGITOS, e na conta GUARDA-CHUVA
(`b3-accounts`, pelo TIPO) o cliente e o CPF/CNPJ, nunca o titular.
"""
import traceback
from datetime import datetime

from apps.pages import data_store as _store
from apps.pages.features.unwinds import catalog
from apps.pages.features.unwinds import domain as fase1
from apps.pages.features.unwinds.infra import product_store
from apps.pages.features.unwinds.product import domain
from apps.pages.platform import swap_flows as _sf


def _R():
    from apps.pages import routes
    return routes


def _ref(date_str):
    d = _R()._parse_date_any(str(date_str or '')) if date_str else None
    return datetime(d.year, d.month, d.day) if d else None


def entries(page, date_str):
    """As linhas do arquivo-dia de `date_str` (vazio sem data ou sem arquivo)."""
    ref = _ref(date_str)
    if ref is None:
        return []
    fp = product_store.day_path(page, ref)
    try:
        st = _store.stat(fp)
    except OSError:
        return []
    out = _R()._day_json(fp, st.st_mtime, st.st_size)
    return [e for e in (out if isinstance(out, list) else [])
            if isinstance(e, dict) and e.get(catalog.KEY_FIELD)]


def find(page, row_id, date_str):
    """(caminho, lista MUTAVEL, indice) da linha `_id` no arquivo-dia; sem data
    ou sem linha, (caminho|None, [], None). Leitura FRESCA do armazem (nao o
    memo do `_day_json`): quem chama vai alterar e gravar."""
    alvo = str(row_id or '').strip()
    ref = _ref(date_str)
    if not alvo or ref is None:
        return None, [], None
    fp = product_store.day_path(page, ref)
    lst = product_store.read_day(fp)
    for i, e in enumerate(lst):
        if isinstance(e, dict) and str(e.get(catalog.KEY_FIELD) or '') == alvo:
            return fp, lst, i
    return fp, lst, None


# ── A posicao ────────────────────────────────────────────────────────────────

def _cells(dados):
    """As linhas de um coletor de Live Position como dict coluna -> celula (o
    coletor entrega LISTA posicional alinhada com `columns`)."""
    cols = list(dados.get('columns') or [])
    out = []
    for r in dados.get('rows') or []:
        if isinstance(r, dict):
            out.append(r)
            continue
        r = list(r or [])
        out.append({c: ('' if i >= len(r) or r[i] is None else str(r[i]).strip())
                    for i, c in enumerate(cols)})
    return out


def _asiaticas(cel):
    datas = []
    for col, v in cel.items():
        if domain.norm(col).startswith('mediaasiaticadata'):
            d = domain.data_iso(v)
            if d:
                datas.append(d)
    return sorted(set(datas))


def _taxid_por_nome(nome):
    """O CPF/CNPJ do Reference Data pela razao social ('' sem cadastro)."""
    if not nome:
        return ''
    try:
        rec = _R()._refdata_by_name().get(_R()._pc_norm(nome)) or {}
    except Exception:                                       # noqa: BLE001
        _R().log.warning('[UNWIND] Reference Data ilegivel ao buscar o CNPJ de %r:\n%s',
                         nome, traceback.format_exc())
        return ''
    return str(rec.get('TAX ID') or '').strip()


def _contas(parte, cpty):
    """(nossa, deles, aviso): a conta NOSSA e a que o `b3-accounts` conhece. A
    posicao e do participante, entao a Parte e a nossa na regra; conta fora do
    cadastro fica dita — e o arquivo da B3 recusa (§8, a visao sai da conta)."""
    R = _R()
    if R._b3_account_le(parte):
        return parte, cpty, None
    if R._b3_account_le(cpty):
        return cpty, parte, None
    return parte, cpty, domain.aviso(
        'unwind_party_not_ours', 'Account %s of the position is not in B3 Accounts' % parte,
        conta=str(parte or ''))


def _ndf(cel):
    R = _R()
    omnibus = bool(R._b3_is_omnibus(cel.get('Codigo da Contraparte')))
    nome, doc, aviso_cpty = fase1.contraparte_da_posicao(cel, omnibus)
    nossa, deles, aviso_conta = _contas(cel.get('Codigo da Parte'), cel.get('Codigo da Contraparte'))
    return {
        'contract': cel.get('Contrato', ''),
        'party_account': cel.get('Codigo da Parte', ''),
        'cpty_account': cel.get('Codigo da Contraparte', ''),
        'our_account': nossa, 'their_account': deles,
        'counterparty': nome or '',
        'taxid': doc or _taxid_por_nome(nome),
        'original': domain.numero(cel.get('Valor Base no registro')),
        'before': domain.numero(cel.get('Valor Antecipado')) or 0.0,
        'strike': (domain.numero(cel.get('Taxa Forward'), taxa=True)
                   or domain.numero(cel.get('Taxa a Termo em Reais'), taxa=True)),
        'trade_date': domain.data_iso(cel.get('Data de Emissao')) or '',
        'maturity': domain.data_iso(cel.get('Data de Vencimento')) or '',
        'underlying': cel.get('Codigo do Ativo Subjacente', ''),
        'currency': str(cel.get('Simbolo da Moeda', '') or '').upper(),
        'comprado': fase1.comprado_na_posicao(cel),
        'asian_dates': _asiaticas(cel),
        'cpty_warning': aviso_cpty, 'account_warning': aviso_conta,
    }


def _opcao(cel):
    R = _R()
    conta = cel.get('Contraparte (Conta)', '')
    doc = cel.get('CPF/CNPJ Cliente Contraparte', '')
    apelido = cel.get('Contraparte (Nome simplificado)', '')
    aviso_cpty = None
    if R._b3_is_omnibus(conta):
        # A coluna do CPF/CNPJ ja vem com o NOME quando o documento tem cadastro.
        if doc and not fase1.parece_documento(doc):
            nome = doc
        else:
            nome = ''
            aviso_cpty = domain.aviso('unwind_cpty_not_registered',
                                      'The counterparty %s is not in the Reference Data' % doc,
                                      taxid=doc)
    else:
        nome = R._lp_cpty_by_account(conta) or (doc if doc and not fase1.parece_documento(doc) else '')
        if not nome:
            nome = apelido
            aviso_cpty = domain.aviso('unwind_cpty_short_name',
                                      'Account %s has no Reference Data name: the B3 short name '
                                      '%s was kept' % (conta, apelido), conta=conta, apelido=apelido)
    tipo = domain.norm(cel.get('Tipo de Opção', ''))
    lado = domain.norm(cel.get('Posição da Parte', ''))
    nossa, deles, aviso_conta = _contas(cel.get('Parte (Conta)'), conta)
    return {
        'contract': cel.get('Código IF', ''),
        'party_account': cel.get('Parte (Conta)', ''), 'cpty_account': conta,
        'our_account': nossa, 'their_account': deles,
        'counterparty': nome, 'taxid': doc if fase1.parece_documento(doc) else _taxid_por_nome(nome),
        'option_type': ('Call' if ('call' in tipo or 'compra' in tipo)
                        else 'Put' if ('put' in tipo or 'venda' in tipo) else ''),
        'side': ('Titular' if 'titular' in lado
                 else 'Lançador' if 'lancador' in lado else ''),
        'strike': domain.numero(cel.get('Strike (valor)'), taxa=True),
        'original': domain.numero(cel.get('Quantidade')),
        'before': domain.numero(cel.get('Quantidade Antecipada')) or 0.0,
        'trade_date': domain.data_iso(cel.get('Data Registro')) or '',
        'maturity': domain.data_iso(cel.get('Data Vencimento')) or '',
        'underlying': cel.get('Ativo subjacente / Moeda base', ''),
        'currency': cel.get('Moeda do ativo / Moeda cotada', ''),
        'unit_premium': domain.numero(cel.get('Prêmio Unitário'), taxa=True),
        'premium_mode': cel.get('Modalidade de liquidação do prêmio', ''),
        'weighted_asian': 'ponder' in domain.norm(cel.get('Média Asiática', '')),
        'asian_dates': _asiaticas(cel),
        'cpty_warning': aviso_cpty, 'account_warning': aviso_conta,
    }


# Os indices do DPOSICAO-SWAP que o `swap_flows.POS` ainda nao nomeia (a ordem
# do `_B3_SWAP_HEADERS['swap_position']`).
_SWAP_PARTE, _SWAP_DOC_PARTE, _SWAP_ANTECIPADO = 3, 4, 16
_LOB_MAX = 6


def _swap(row):
    """Uma linha CRUA do DPOSICAO-SWAP (170 campos em ordem; o mock esparso da
    dev resolve pelo nome, como o `swap_flows.posicoes_swap`)."""
    R = _R()
    vals = list(row.values())
    if len(vals) >= 120:
        c = lambda i: _sf.celula(vals, i)                   # noqa: E731
        cel = {'contrato': c(_sf.POS['contrato']), 'parte': c(_SWAP_PARTE),
               'doc_parte': c(_SWAP_DOC_PARTE), 'cp': c(_sf.POS['conta_cp']),
               'doc_cp': c(_sf.POS['doc_cp']), 'inicio': c(_sf.POS['inicio']),
               'venc': c(_sf.POS['vencimento']), 'base': c(_sf.POS['valor_base']),
               'antecipado': c(_SWAP_ANTECIPADO), 'ident': c(_sf.POS['identificador']),
               'curva': (c(_sf.POS['nome_classe'][0]) or c(_sf.POS['indice'][0]),
                         c(_sf.POS['nome_classe'][1]) or c(_sf.POS['indice'][1]))}
    else:
        n = lambda k: str(_sf.por_nome(row, k) or '').strip()   # noqa: E731
        cel = {'contrato': n('Contrato'), 'parte': n('Participante'),
               'doc_parte': n('CPF/CNPJ Cliente Parte'), 'cp': n('Contraparte'),
               'doc_cp': n('CPF/CNPJ Cliente Contraparte'), 'inicio': n('Data início'),
               'venc': n('Data vencimento'), 'base': n('Valor base'),
               'antecipado': n('Valor Antecipado'), 'ident': n('Código Identificador'),
               'curva': (n('Curva Parte'), n('Curva Contraparte'))}
    if R._b3_account_le(cel['parte']):
        nossa, deles, doc, papel, curvas, aviso_conta = (
            cel['parte'], cel['cp'], cel['doc_cp'], 'Ponta 1', cel['curva'], None)
    elif R._b3_account_le(cel['cp']):
        nossa, deles, doc, papel, curvas, aviso_conta = (
            cel['cp'], cel['parte'], cel['doc_parte'], 'Ponta 2', cel['curva'][::-1], None)
    else:
        nossa, deles, doc, papel, curvas = cel['parte'], cel['cp'], cel['doc_cp'], '', cel['curva']
        aviso_conta = domain.aviso('unwind_party_not_ours',
                                   'Neither account of the swap is in B3 Accounts (%s / %s)'
                                   % (cel['parte'], cel['cp']), conta=cel['parte'])
    aviso_cpty = None
    nome_doc = R._lp_cpty_name_by_taxid(doc) if domain.digitos(doc) else ''
    if R._b3_is_omnibus(deles):
        nome = nome_doc
        if not nome:
            aviso_cpty = domain.aviso('unwind_cpty_not_registered',
                                      'The counterparty %s is not in the Reference Data' % doc,
                                      taxid=doc)
    else:
        nome = R._lp_cpty_by_account(deles) or nome_doc
        if not nome:
            aviso_cpty = domain.aviso('unwind_no_counterparty',
                                      'The position identifies no counterparty', conta=deles)
    ident = str(cel['ident'] or '').strip().upper()
    return {
        'contract': cel['contrato'], 'party_account': cel['parte'], 'cpty_account': cel['cp'],
        'our_account': nossa, 'their_account': deles, 'role': papel,
        'counterparty': nome, 'taxid': R._lp_fmt_cnpj(doc) if domain.digitos(doc) else '',
        'original': _sf.numero_da_posicao(cel['base']),
        'before': _sf.numero_da_posicao(cel['antecipado']) or 0.0,
        'trade_date': _sf.iso(cel['inicio']), 'maturity': _sf.iso(cel['venc']),
        # O `Codigo Identificador` do swap guarda a LOB (§427), nao um id.
        'lob': ident if (ident.isalpha() and len(ident) <= _LOB_MAX) else '',
        'our_curve': curvas[0], 'cpty_curve': curvas[1],
        'cpty_warning': aviso_cpty, 'account_warning': aviso_conta,
    }


def posicoes(page, ref):
    """(posicoes canonicas, data da posicao lida em ISO) do produto da pagina.
    Produto sem posicao (`position: None`) devolve ([], '')."""
    R = _R()
    kind = page.get('position')
    if kind == catalog.POS_NDF:
        dados = R._lpndf_collect(ref) or {}
        return [_ndf(c) for c in _cells(dados)], dados.get('source_date') or ''
    if kind == catalog.POS_OPCAO:
        dados = R._lpopt_collect(ref) or {}
        return [_opcao(c) for c in _cells(dados)], dados.get('source_date') or ''
    if kind == catalog.POS_SWAP:
        path, dref = _sf.swap_day_file('73760_{}_DPOSICAO-SWAP.json', ref.date()
                                       if hasattr(ref, 'date') else ref)
        if not path:
            return [], ''
        src = R._db_day_records(path) or []
        return [_swap(r) for r in src if isinstance(r, dict)], R._b3_dref_to_iso(dref)
    return [], ''


def dias_uteis(inicio_iso, fim_iso):
    """Dias uteis ANBIMA em (inicio, fim], ou None sem as duas datas."""
    a, b = _ref(inicio_iso), _ref(fim_iso)
    if a is None or b is None:
        return None
    return _R()._anbima_biz_diff(a, b)


def template_blocks(key):
    tpl = _R()._fi_tpl_cached(key)
    if tpl is None:
        raise domain.Recusa('unwind_template_missing',
                            'file-interpreter template missing: ' + str(key), 500, key=key)
    return list(tpl.get('blocks') or [])
