# -*- coding: utf-8 -*-
"""Live Position › DCE: a leitura de uma linha do DPOSICAOCONTRATODCE (§729).

PURO: não importa `routes`, não lê banco. Recebe as tabelas de código já
montadas (dos cadastros do /mapping) e devolve a linha como a tela a mostra.

O layout é o da B3 (Manual "Receber Arquivos", Derivativos Realizados no
Exterior, pp. 422-424): 57 campos de dado, na ordem do arquivo. Os campos de
TIPO vêm como NÚMERO — `07`, `11`, `01` — e o texto de cada número NUNCA está
aqui: está nos cadastros. O que fica em código é só QUAL tabela responde a cada
coluna, que é o próprio layout.
"""
import unicodedata

# Origem do texto de cada coluna de código:
#   ('codes', FIELD)       → cadastro `dce-position-codes`, linhas daquele FIELD
#   ('dce', chave)         → um dos cadastros públicos `dce-*` (Dominios_DCE)
#   ('asset', coluna_cat)  → `dce-underlying-asset`, pela CATEGORIA da coluna dada
#   ('date',)              → AAAAMMDD
#   ('num', casas)         → número com as casas do layout (9(n,casas))
#   ('value', casas)       → idem, mostrado como valor (#,##0.00)
SIM_NAO = ('codes', 'Sim/Não')
POSICAO = ('codes', 'Posição')
KIND = {
    'Data de Registro': ('date',),
    'Data de Início': ('date',),
    'Data de Vencimento': ('date',),
    'Tipo de DCE': ('codes', 'Tipo de DCE'),
    'Tipo de Mercado': ('codes', 'Tipo de Mercado'),
    'Tipo de Derivativo': ('dce', 'dce-type-of-derivative'),
    'Valor Base do Contrato': ('value', 5),
    'Quantidade': ('num', 4),
    'Multiplicador': ('num', 2),
    'Categoria do Ativo Subjacente': ('dce', 'dce-underlying-asset-category'),
    'Ativo Subjacente da Parte': ('asset', 'Categoria do Ativo Subjacente'),
    'Funcionalidade': ('dce', 'dce-functionality'),
    'Moeda Cotada': ('codes', 'Moeda'),
    'Moeda de Liquidação': ('codes', 'Moeda'),
    'Entrega Física': SIM_NAO,
    'Garantias': SIM_NAO,
    'Liquidação em CCP': SIM_NAO,
    'Bolsa Negociada': ('codes', 'Bolsa Negociada'),
    'País de Origem da Bolsa Negociada': ('dce', 'dce-country'),
    'Mês de Referência': ('codes', 'Mês de Referência'),
    'Contraparte Identificada': SIM_NAO,
    'País de Origem da Contraparte': ('dce', 'dce-country'),
    'Contraparte Relacionada (Coligada)': SIM_NAO,
    'Posição da Parte - Futuro': POSICAO,
    'Preço - Futuro': ('num', 6),
    'Posição da Parte - Termo': POSICAO,
    'Termo Asiático': SIM_NAO,
    'Preço - Termo': ('num', 6),
    'Posição da Parte - Opção': ('codes', 'Posição Opção'),
    'Tipo de Opção': ('codes', 'Tipo de Opção'),
    'Strike': ('num', 6),
    'Tipo de Verificação': ('dce', 'dce-type-of-verification'),
    'Opção Asiática': SIM_NAO,
    'Categoria do Ativo Subjacente da Contraparte': ('dce', 'dce-underlying-asset-category'),
    'Ativo Subjacente da Contraparte': ('asset', 'Categoria do Ativo Subjacente da Contraparte'),
    'Tipo de Swap': ('dce', 'dce-type-of-swap'),
    'Swap Asiático': SIM_NAO,
    'Posição da Parte - CDS': ('codes', 'Posição CDS'),
    'Tipo de Origem': ('codes', 'Tipo de Origem'),
    'Origem': ('codes', 'Origem'),
    'Posição da Parte - Nota Estruturada': POSICAO,
    'Posição da Parte - CFD': POSICAO,
    'Posição da Parte - Swaption': POSICAO,
}

# Os cadastros públicos que a tela consulta (os `dce-*` do /mapping).
DCE_TABLES = sorted({k[1] for k in KIND.values() if k[0] == 'dce'})


def norm(s):
    """Texto para comparar: sem acento, maiúsculo, espaços simples."""
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(s.upper().split())


def code_key(v):
    """O código como chave: `07` e `7` são o mesmo; texto vale sem caixa."""
    v = str(v or '').strip()
    if v.isdigit():
        return str(int(v))
    return norm(v)


def code_table(rows, code_col, label_col):
    """{código: texto} de um cadastro de duas colunas (os `dce-*`)."""
    out = {}
    for r in rows or []:
        k = code_key(r.get(code_col, ''))
        if k != '' and k not in out:
            out[k] = str(r.get(label_col, '') or '').strip()
    return out


def position_codes(rows):
    """{FIELD normalizado: {código: texto}} do `dce-position-codes`."""
    out = {}
    for r in rows or []:
        k = code_key(r.get('CODE', ''))
        if k == '':
            continue
        out.setdefault(norm(r.get('FIELD', '')), {})[k] = str(r.get('LABEL', '') or '').strip()
    return out


def asset_table(rows):
    """{(CATEGORIA normalizada, código): texto} do `dce-underlying-asset`.
    O código do ativo REPETE entre categorias (o mesmo `1` é um açúcar e uma
    moeda): a chave é o par."""
    out = {}
    for r in rows or []:
        k = (norm(r.get('CATEGORY', '')), code_key(r.get('REFERENCE CODE', '')))
        if k[1] != '' and k not in out:
            out[k] = str(r.get('DOMAIN', '') or '').strip()
    return out


def fmt_date(v):
    v = str(v or '').strip()
    if len(v) == 8 and v.isdigit() and v != '00000000':
        return '%s/%s/%s' % (v[6:8], v[4:6], v[0:4])
    return v


def parse_num(v, casas):
    """O número do arquivo. O layout o escreve SEM separador (`9(14,05)` são
    19 dígitos, as cinco últimas casas decimais); se vier com vírgula ou ponto
    decimal, vale como veio. Vazio ou ilegível → None."""
    s = str(v or '').strip()
    if not s:
        return None
    neg = s.startswith('-')
    s = s.lstrip('+-')
    try:
        if ',' in s:
            n = float(s.replace('.', '').replace(',', '.'))
        elif '.' in s:
            n = float(s)
        elif s.isdigit():
            n = int(s) / (10 ** casas)
        else:
            return None
    except ValueError:
        return None
    return -n if neg else n


def fmt_num(v, casas, valor=False):
    n = parse_num(v, casas)
    if n is None:
        return str(v or '').strip()
    if valor:
        return '{:,.2f}'.format(n)
    # taxa, preço e quantidade ficam com as casas que têm (sem zeros à direita)
    txt = '{:,.{}f}'.format(n, casas)
    if '.' in txt:
        txt = txt.rstrip('0').rstrip('.')
    return txt


def display_row(labels, values, dce, codes, assets):
    """A linha como a tela mostra: código → texto pelos cadastros (sem texto,
    fica o código — nunca vazio), datas dd/mm/aaaa, números formatados.

    `labels` e `values` vêm na ordem do arquivo. `dce` = {chave do cadastro:
    {código: texto}}; `codes` = `position_codes(...)`; `assets` =
    `asset_table(...)`."""
    raw = dict(zip(labels, values))
    out = []
    for lab, v in zip(labels, values):
        v = str(v or '').strip()
        kind = KIND.get(lab)
        if not kind or v == '':
            out.append(v)
        elif kind[0] == 'date':
            out.append(fmt_date(v))
        elif kind[0] in ('num', 'value'):
            out.append(fmt_num(v, kind[1], valor=kind[0] == 'value'))
        elif kind[0] == 'codes':
            out.append(codes.get(norm(kind[1]), {}).get(code_key(v)) or v)
        elif kind[0] == 'dce':
            out.append((dce.get(kind[1]) or {}).get(code_key(v)) or v)
        elif kind[0] == 'asset':
            cat_cod = raw.get(kind[1], '')
            cat_txt = (dce.get('dce-underlying-asset-category') or {}).get(code_key(cat_cod), '')
            out.append(assets.get((norm(cat_txt), code_key(v))) or v)
        else:
            out.append(v)
    return out
