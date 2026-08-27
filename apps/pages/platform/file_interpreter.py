# -*- coding: utf-8 -*-
"""O motor do File Interpreter — templates, variantes por par de pernas,
fórmulas (`_fi_calc_value`) e a montagem de linha (`_fi_build_line`).

Movido VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10). É horizontal:
os geradores TER das quatro páginas de New Deals e os previews chamam tudo
isto; a cópia da regra no navegador é o `static/js/fi-ter-pair.js` +
`FiTer.calc`, e `check_fi_variants.py` / `check_fi_calc.py` provam que as
cópias concordam.

O `routes.py` mantém os nomes como ALIAS. O **`_FILE_INTERPRETER_DIR` FICA no
`routes` de propósito**: é a superfície de patch dos check_fi_* (que apontam a
pasta de templates para um tmp), e a platform o lê por `routes.<nome>` — a
mesma razão do `_B3_DATA_DIR` (§314). O calendário e os mappings do LOOKUP
também são alcançados por busca atrasada (`_anbima_*`, `_mapping_rows`),
porque testes os trocam no `routes`. O ESTADO do cache de template
(`_fi_tpl_cache`, mutado in place) mora aqui e o alias segue vivo.
"""
import json
import logging
import os
import re

from apps.pages.data_paths import data_dir

log = logging.getLogger('otc_tracker')

# A pasta chamava-se `file-interface` (o endereço antigo da página). Template
# criado PELA TELA na instância do time não está no git: na subida, o que
# ficou na pasta antiga é movido para a nova (sem sobrescrever o que já
# existe) — renomear diretório não pode sumir com cadastro de runtime.
_FI_LEGACY_DIR = os.path.normpath(os.path.join(
    data_dir(), 'file-interface'))

# A chave é também o nome do arquivo em disco: o regex é o que impede um
# path traversal via URL (`../../`) além de padronizar o kebab-case.
_FI_KEY_RE = re.compile(r'^[a-z0-9][a-z0-9-]{1,63}$')

_FI_FIELD_KEYS = ('seq', 'field', 'format', 'position', 'required',
                  'content', 'description', 'source', 'source_detail',
                  'source_note')
# `variant_label` é o rótulo da variante quando ela NÃO é por par de pernas —
# as da Intrag são por PRODUTO (NDF Commodities, Opt FXO). Só rótulo: quem o
# motor consulta para escolher a variante continua sendo o `le_pair`.
_FI_META_KEYS = ('name', 'system_id', 'category', 'manual_section',
                 'manual_pages', 'manual_version', 'description',
                 'file_name_rule', 'notes', 'base_key', 'le_pair',
                 'variant_label', 'file_name')


def _fi_path(key):
    from apps.pages import routes
    return os.path.join(routes._FILE_INTERPRETER_DIR, key + '.json')


def _fi_load(key):
    """Template completo (dict) ou None. Sem cache: a página é de consulta
    eventual e os arquivos são pequenos — mtime-cache aqui seria zelo à toa."""
    try:
        with open(_fi_path(key), encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _fi_clean_template(key, payload):
    """Normaliza o template recebido do POST → (dict, None) ou (None, erro).

    Igual aos mappings, valores NÃO são trimados: conteúdo de campo B3 pode
    carregar espaço significativo. A validação é de FORMA (tipos e chaves
    conhecidas), não de conteúdo — o dono do layout é o manual da B3, não o app."""
    if not isinstance(payload, dict):
        return None, 'payload must be an object'
    out = {'key': key}
    for k in _FI_META_KEYS:
        out[k] = str(payload.get(k, '') or '')
    if not out['name'].strip():
        return None, 'name is required'
    # `file_name` vira nome de arquivo em disco na geração: só o basename e
    # só caracteres inofensivos — um '../' cadastrado não pode virar caminho.
    out['file_name'] = re.sub(r'[^A-Za-z0-9._ -]', '',
                              os.path.basename(out['file_name'])).strip()
    ft = str(payload.get('file_type', '') or '').strip().lower()
    out['file_type'] = ft if ft in ('positional', 'delimited') else 'positional'
    sep = payload.get('separator')
    out['separator'] = (str(sep) if sep not in (None, '') else None) \
        if out['file_type'] == 'delimited' else None
    rl = payload.get('record_length')
    try:
        out['record_length'] = int(rl) if rl not in (None, '') else None
    except (TypeError, ValueError):
        out['record_length'] = None
    st = str(payload.get('status', '') or '').strip().lower()
    out['status'] = st if st in ('active', 'library') else 'library'
    pages = []
    for p in (payload.get('linked_pages') or []):
        if isinstance(p, dict) and str(p.get('url', '') or '').startswith('/'):
            entry = {'label': str(p.get('label', '') or '').strip(),
                     'url': str(p['url']).strip()}
            # As COLUNAS da página vivem aqui (cadastráveis, nada fixo no
            # código): são as opções do dropdown de Origem quando Source=Page.
            cols = [str(c) for c in (p.get('columns') or []) if str(c).strip()]
            if cols:
                entry['columns'] = cols
            pages.append(entry)
    out['linked_pages'] = pages
    blocks = []
    for b in (payload.get('blocks') or []):
        if not isinstance(b, dict):
            continue
        fields = []
        for f in (b.get('fields') or []):
            if not isinstance(f, dict):
                continue
            fld = {k: str(f.get(k, '') or '') for k in _FI_FIELD_KEYS}
            # Origem POR PÁGINA: quando o mesmo template serve páginas que
            # preenchem o campo de jeitos diferentes, o texto de cada página
            # vive aqui e o source/source_detail plano fica como o comum.
            sbp = f.get('source_by_page')
            if isinstance(sbp, dict):
                clean_sbp = {}
                for url, ov in sbp.items():
                    if isinstance(ov, dict) and str(url).startswith('/'):
                        clean_sbp[str(url)] = {
                            'source': str(ov.get('source', '') or ''),
                            'source_detail': str(ov.get('source_detail', '') or ''),
                            'source_note': str(ov.get('source_note', '') or '')}
                if clean_sbp:
                    fld['source_by_page'] = clean_sbp
            fields.append(fld)
        blocks.append({'id': str(b.get('id', '') or '').strip() or 'block-%d' % (len(blocks) + 1),
                       'title': str(b.get('title', '') or '').strip() or 'Block',
                       'note': str(b.get('note', '') or ''),
                       'fields': fields})
    out['blocks'] = blocks
    return out, None


# ── O cadastro COMANDA previews e geração ────────────────────────────────────
#  O template do File Interface é a autoridade da ESTRUTURA da linha: ordem dos
#  campos, largura (format) e os literais dos campos Fixed. O código continua
#  dono dos VALORES calculados — o gerador entrega strings já formatadas por
#  seq, usadas VERBATIM, para a troca ser byte a byte idêntica ao que sempre
#  foi enviado à B3 (as excentricidades históricas ficam no gerador, não no
#  motor). Editar um Fixed, reordenar ou acrescentar campo pela tela muda o
#  arquivo e o preview sem tocar em código.

_fi_tpl_cache = {}   # key -> (mtime, dict) — edição na tela vale no request seguinte


def _fi_tpl_cached(key):
    """Template com cache por mtime, como os mappings — geradores e previews
    leem a cada request e o arquivo só é reparseado quando muda."""
    path = _fi_path(key)
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return None
    hit = _fi_tpl_cache.get(key)
    if hit and hit[0] == mt:
        return hit[1]
    data = _fi_load(key)
    if data is not None:
        _fi_tpl_cache[key] = (mt, data)
    return data


# ── Variantes por par de pernas (LE pair) ───────────────────────────────────
#  Um template pode ser VARIANTE de outro: `base_key` aponta o template-mãe e
#  `le_pair` diz para qual par de pernas ele vale ('MGT x JPM'). O gerador
#  continua chamando o motor pela chave BASE — quem escolhe a variante é o
#  motor, pelo par do deal. Sem par, ou sem variante cadastrada para o par,
#  vale o base: o comportamento de sempre, byte a byte. A variante é uma
#  cópia completa do layout, então nela mais campos podem virar Fixed (conta
#  da parte/contraparte, Nome Simplificado do header) sem tocar em código.

_FI_LE_PAIRS = ('JPM x MGT', 'JPM x CLI', 'MGT x CLI', 'JPM x ATACAMA',
                'MGT x JPM', 'ATACAMA x JPM', 'LAWTON x JPM', 'JPM x LAWTON')


def _fi_le_pair_norm(pair):
    """'mgt × Jpm ' ≡ 'MGT x JPM' — comparação cega a caixa, espaço extra e ao
    sinal de vezes. O que se grava é o texto do cadastro."""
    s = str(pair or '').upper().replace('×', 'X')
    return ' '.join(s.split())


def _fi_variant_key(base_key, page_url=None, le_pair=None):
    """Chave EFETIVA do template para (página, par de pernas). A variante
    ligada à página vence a variante sem página nenhuma (coringa); variante
    ligada só a OUTRAS páginas não vale aqui. Sem par ou sem variante → o
    próprio base."""
    from apps.pages import routes
    want = _fi_le_pair_norm(le_pair)
    if not want:
        return base_key
    wildcard = None
    try:
        names = sorted(os.listdir(routes._FILE_INTERPRETER_DIR))
    except OSError:
        return base_key
    for fn in names:
        if not fn.endswith('.json'):
            continue
        t = _fi_tpl_cached(fn[:-5])
        if not t or str(t.get('base_key', '') or '') != base_key:
            continue
        if _fi_le_pair_norm(t.get('le_pair')) != want:
            continue
        pages = [p.get('url') for p in (t.get('linked_pages') or [])]
        if not pages:
            wildcard = wildcard or t.get('key')
        elif not page_url or page_url in pages:
            return t.get('key')
    return wildcard or base_key


def _fi_variant_file_name(base_key, page_url=None, le_pair=None):
    """`file_name` da variante efetiva — o nome do arquivo gerado quando o
    cadastro define um. '' = usa o nome padrão do gerador."""
    key = _fi_variant_key(base_key, page_url, le_pair)
    tpl = _fi_tpl_cached(key)
    return str((tpl or {}).get('file_name', '') or '').strip()


def _fi_width(fmt):
    """Largura em caracteres de um formato do manual: X(n)/9(n) → n,
    9(a)V9(b) → a+b (o V é decimal implícito, não ocupa posição).
    None = formato que o motor não sabe medir."""
    m = re.fullmatch(r'9\((\d+)\)V9\((\d+)\)', str(fmt or ''))
    if m:
        return int(m.group(1)) + int(m.group(2))
    m = re.fullmatch(r'[X9]\((\d+)\)', str(fmt or ''))
    return int(m.group(1)) if m else None


def _fi_field_src(field, page_url=None):
    """source/source_detail/source_note efetivos: o override da página
    (source_by_page) vence o texto comum do campo."""
    ov = (field.get('source_by_page') or {}).get(page_url or '')
    return ov if ov else field


def _fi_seq_key(seq):
    s = str(seq or '').strip()
    return s.lstrip('0') or '0' if s.isdigit() else s


# ── Cálculo CADASTRÁVEL de campo (Source Calculated) ────────────────────────
#  O Source Field/Value pode carregar uma FÓRMULA em vez de texto livre, e aí o
#  motor calcula o valor — nada de código novo para um campo derivado. O
#  catálogo é pequeno e nomeado (argumentos separados por ';', campo = nome da
#  COLUNA da página, casado com o campo do deal cego a caixa/espaço):
#    FIELD(Campo)                       → o valor do campo, como está
#    DATE(Campo)                        → o campo como data AAAAMMDD
#    BIZDIFF(Campo A; Campo B)          → dias úteis ANBIMA entre A e B,
#                                         zero-padded pela largura do format
#                                         (9(01) → '3', 9(02) → '03')
#    ADDBIZ(Campo; N)                   → data do campo + N dias úteis (AAAAMMDD)
#    LOOKUP(mapping; COL IN; COL OUT; Campo) → linha do mapping cuja COL IN
#                                         casa com o campo (normalizado exato),
#                                         devolvendo COL OUT
#    CASE(Campo; DE=PARA; DE=PARA; …)   → de-para em linha sobre o valor do
#                                         campo (comparação normalizada). Valor
#                                         não listado devolve VAZIO, que o motor
#                                         completa com espaços na largura do
#                                         format — é assim que se cadastra
#                                         "e no resto, branco"
#  Texto que NÃO parseia como fórmula continua documentação: o valor do
#  gerador vale, como sempre — é o que mantém todo cadastro existente
#  byte a byte. A cópia do navegador é o FiTer.calc (fi-ter-pair.js).
_FI_CALC_RE = re.compile(r'^\s*(BIZDIFF|ADDBIZ|DATE|FIELD|LOOKUP|CASE)\s*\((.*)\)\s*$',
                         re.I | re.S)


def _fi_deal_get(deal, name):
    """Campo do deal pelo NOME DA COLUNA da página: 'Last Fixing Date' ≡
    'LastFixingDate' — a comparação ignora caixa e tudo que não é letra ou
    dígito. Sem campo, ''."""
    want = re.sub(r'[^A-Z0-9]', '', str(name or '').upper())
    if not want:
        return ''
    for k, v in (deal or {}).items():
        if re.sub(r'[^A-Z0-9]', '', str(k).upper()) == want:
            return re.sub(r'<[^>]+>', '', str(v or '')).strip()
    return ''


def _fi_calc_value(spec, deal, fmt=''):
    """Executa uma fórmula cadastrada sobre o deal. None = não é fórmula (ou
    argumento inválido): o chamador mantém o valor do gerador — a fórmula mal
    cadastrada degrada para o comportamento de sempre, nunca derruba o
    arquivo."""
    from apps.pages import routes
    m = _FI_CALC_RE.match(str(spec or ''))
    if not m or deal is None:
        return None
    fn = m.group(1).upper()
    args = [a.strip() for a in m.group(2).split(';')]
    try:
        if fn == 'FIELD':
            return _fi_deal_get(deal, args[0])
        if fn == 'DATE':
            dt = routes._parse_date_any(_fi_deal_get(deal, args[0]))
            return dt.strftime('%Y%m%d') if dt else ''
        if fn == 'BIZDIFF':
            a = routes._parse_date_any(_fi_deal_get(deal, args[0]))
            b = routes._parse_date_any(_fi_deal_get(deal, args[1]))
            s = str(routes._anbima_biz_diff(a, b))
            w = _fi_width(fmt)
            return s.zfill(w)[:w] if w else s
        if fn == 'ADDBIZ':
            dt = routes._parse_date_any(_fi_deal_get(deal, args[0]))
            d2 = routes._anbima_add_biz(dt, int(args[1])) if dt else None
            return d2.strftime('%Y%m%d') if d2 else ''
        if fn == 'CASE':
            alvo = re.sub(r'[^A-Z0-9]', '', _fi_deal_get(deal, args[0]).upper())
            for par in args[1:]:
                if '=' not in par:
                    continue
                de, para = par.split('=', 1)
                if re.sub(r'[^A-Z0-9]', '', de.upper()) == alvo:
                    return para
            return ''
        if fn == 'LOOKUP':
            key, col_in, col_out, fld = (args + ['', '', '', ''])[:4]
            alvo = re.sub(r'[^A-Z0-9]', '', _fi_deal_get(deal, fld).upper())
            if not alvo:
                return ''
            for row in routes._mapping_rows(key):
                v = re.sub(r'[^A-Z0-9]', '', str(row.get(col_in, '') or '').upper())
                if v and v == alvo:
                    return str(row.get(col_out, '') or '')
            return ''
    except Exception:
        return None
    return None


def _fi_effective_seq_value(key, block_id, seq, values, page_url=None,
                            le_pair=None, deal=None):
    """Valor EFETIVO de um campo (por seq) como o motor o montaria: Fixed do
    cadastro (variante/override da página) > fórmula cadastrada > valor do
    gerador. É o que deixa OUTRA regra depender de um campo cadastrável — o
    deslocamento das linhas de verificação lê aqui a Cotação para o
    Vencimento."""
    tpl = _fi_tpl_cached(_fi_variant_key(key, page_url, le_pair))
    blk = _fi_block_of(tpl, block_id) or _fi_block_of(_fi_tpl_cached(key), block_id)
    for f in (blk or {}).get('fields', []):
        if _fi_seq_key(f.get('seq')) != _fi_seq_key(seq):
            continue
        src = _fi_field_src(f, page_url)
        if str(src.get('source', '')) == 'Fixed':
            return str(src.get('source_detail', ''))
        calc = _fi_calc_value(src.get('source_detail'), deal, f.get('format'))
        if calc is not None:
            return calc
        break
    vals = {_fi_seq_key(k): ('' if v is None else str(v))
            for k, v in (values or {}).items()}
    return vals.get(_fi_seq_key(seq), '')


def _fi_block_of(tpl, block_id):
    for b in (tpl or {}).get('blocks', []):
        if b.get('id') == block_id:
            return b
    return None


def _fi_build_line(key, block_id, values, page_url=None, le_pair=None, deal=None):
    """Monta UMA linha do arquivo a partir do cadastro do File Interface.

    `values` = {seq: string JÁ formatada} dos campos não-Fixed ('4' e '04'
    valem o mesmo). Fixed sai do cadastro (override por página vence) padded
    pela largura do format (X → espaços à direita, 9 → zeros à esquerda;
    Fixed vazio = campo em branco na largura). Valor de gerador é usado
    verbatim, apenas completado com espaços se vier mais curto que o format —
    nunca truncado nem reformatado. Posicional concatena; delimitado junta
    com o separator do template e fecha com token vazio (padrão OPC).
    Template/bloco ausente levanta ValueError: arquivo para a B3 não pode
    sair meio montado em silêncio.

    `le_pair` escolhe a VARIANTE do template ('MGT x JPM'): a cadastrada para
    o par vence; variante sem o bloco cai de volta no bloco do base — uma
    variante criada antes de o base ganhar um bloco não pode derrubar a
    geração inteira."""
    eff_key = _fi_variant_key(key, page_url, le_pair)
    tpl = _fi_tpl_cached(eff_key)
    block = _fi_block_of(tpl, block_id)
    if eff_key != key and (tpl is None or block is None):
        eff_key = key
        tpl = _fi_tpl_cached(key)
        block = _fi_block_of(tpl, block_id)
    if tpl is None or block is None:
        raise ValueError('file-interpreter template missing: {}/{}'.format(eff_key, block_id))
    positional = tpl.get('file_type') != 'delimited'
    vals = {_fi_seq_key(k): ('' if v is None else str(v)) for k, v in (values or {}).items()}
    parts = []
    for f in block.get('fields', []):
        src = _fi_field_src(f, page_url)
        fixed = str(src.get('source', '')) == 'Fixed'
        val = str(src.get('source_detail', '')) if fixed \
            else vals.get(_fi_seq_key(f.get('seq')), '')
        if not fixed and deal is not None:
            # Fórmula cadastrada no Source Field/Value vence o valor do
            # gerador; texto que não parseia continua documentação (None).
            calc = _fi_calc_value(src.get('source_detail'), deal, f.get('format'))
            if calc is not None:
                val = calc
        if positional:
            w = _fi_width(f.get('format'))
            if w is not None and len(val) < w:
                if fixed and val and str(f.get('format', '')).startswith('9'):
                    val = val.rjust(w, '0')
                else:
                    val = val.ljust(w)
        parts.append(val)
    if positional:
        return ''.join(parts)
    sep = tpl.get('separator') or ';'
    return sep.join(parts) + sep
