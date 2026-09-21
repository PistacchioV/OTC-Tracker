# -*- coding: utf-8 -*-
"""O Deal Ticket de SWAP e as regras PURAS que Bullet e Cashflow dividem.

Horizontal (platform) desde 21/09/2026: nasceu como o `domain` do Swap Bullet
(`features/swap_bullet`, §480) e saiu de lá quando o Swap Cashflow
(`features/swap_cashflow`) passou a ler o MESMO Deal Ticket — feature não
importa feature, e as duas páginas lendo cópias diferentes do parser
divergiriam no primeiro rótulo novo. O Bullet re-exporta tudo pelo `domain`
dele, sem mudança de comportamento (`check_swap_bullet.py` prende byte a
byte); o que é só do Bullet (o registro 0301 de Pagamento Final) ficou lá, e
o que é só do Cashflow (o registro de Fluxo Não Constante e a tabela Cash
Flow) está na vertical dele.

Sem Flask, sem arquivo, sem rede, sem `routes`: o que entra é texto (a grade
do xlsx ou o texto do PDF do Deal Ticket) e um dicionário de deal; o que sai
é o deal e os valores de cada campo dos arquivos da B3 que as duas páginas
geram igual — o Registro de Prêmio (código 0897, seção 4.2.11), a linha da
Intrag Swap e o deal no formato das confirmações.

Três decisões que explicam o desenho:

* **O DT tem duas pernas com os MESMOS rótulos** (Percentual, Categoria,
  Curva, Sinal, Juros, Limites, uma vez no bloco *Curva VCP* e outra no
  *Curva Vanilla*). O parser separa os blocos pela COLUNA do cabeçalho do
  bloco (xlsx) ou pela ORDEM de aparição (PDF) — e depois quem é Parte A
  (a NOSSA perna, a Parte do arquivo) e Parte B (a contraparte) é decidido
  pelo `Ativo VCP`/`Ativo Curva Vanilla`: quem é "ativo" numa curva é quem a
  carrega. A grade da tela e o arquivo falam em Parte A/Parte B; VCP e
  Vanilla são só o jeito de o DT chegar.
* **O de-para de texto → código B3 é CADASTRO** (§2 do CLAUDE.md): a
  funcionalidade (`swap-funcionalidade`), sinal e Sim/Não e a Adesão
  (`swap-code-labels`), a curva do DT → `Curva X(03)` (`swap-bullet-curve`) e
  o tipo de amortização (`swap-amortizacao`). O módulo recebe as LINHAS dos
  cadastros como argumento — é puro — e responde pelo casamento normalizado
  (sem acento, sem caixa, tokens de ligação fora). Código que não resolve é
  LACUNA sinalizada no preview e recusada no Send, nunca um valor presumido.
* **A denominação da curva VCP é a fórmula da mesa**, portada de um Excel:
  `{Curva} : {Proper(Categoria)} Código {Código} – Descrição: {Descrição} –
  Preco Inicial: {Preço} – Fonte de informacao: {Fonte} – Data de cotacao:
  {dd-mmm-aaaa} - Cupom limpo = Strike - {Denominação linha 3} -
  Denominação: {Denominação linha 1}`, com os acentos tirados e cortada/
  completada em 320 (o X(320) do campo). O texto fica no deal (`VcpText`)
  e é editável; em branco, o arquivo recompõe daqui.
"""
import hashlib
import re
import unicodedata
from datetime import date, datetime

# ── Colunas da página (a ordem da grade) ─────────────────────────────────────
# Cada tupla: (chave no deal, rótulo em inglês da coluna). É o contrato com o
# template (`SWB_COLS`/`SWB_FIELDS`), com o File Interpreter (`linked_pages
# [].columns` são estes rótulos) e com o `_fi_deal_get` (que casa o rótulo com
# a chave cego a caixa e espaço — 'Curve A Pct' ≡ 'CurveAPct').
SWB_COLUMNS = (
    ('Type', 'Swap Type'),
    ('Client', 'Client'),
    ('ClientDT', 'Client (Deal Ticket)'),
    ('SPN', 'SPN'),
    ('ClientAccount', 'Client B3 Account'),
    ('ClientTaxId', 'Client Tax ID'),
    ('StartDate', 'Start Date'),
    ('MaturityDate', 'Maturity Date'),
    ('Currency', 'Currency'),
    ('Notional', 'Notional'),
    # O Deal Ticket da CEM (mesa, 21/09/2026) traz o valor base nas DUAS moedas
    # e a paridade do início; o da EDG não — ali as duas ficam em branco.
    ('FXStart', 'FX Start'),
    ('NotionalFC', 'Notional (Foreign Ccy)'),
    ('Adhesion', 'Adhesion'),
    ('Functionality', 'Functionality'),
    ('PremiumSchedule', 'Premium Schedule'),
    ('PremiumDate', 'Premium Date'),
    ('PremiumPayer', 'Premium Payer'),
    ('PremiumAmount', 'Premium Amount'),
    ('Reset', 'Reset'),
    ('NotionalIndex', 'Notional Update Index'),
    ('NotionalObsDate', 'Notional Observation Date'),
    ('NotionalDescription', 'Notional Update Description'),
    ('VcpHolder', 'VCP Holder'),
    ('VanillaHolder', 'Vanilla Holder'),
    ('CurveACategory', 'Curve A Category'),
    ('CurveAPct', 'Curve A Pct'),
    ('CurveA', 'Curve A'),
    ('CurveASign', 'Curve A Sign'),
    ('CurveARate', 'Curve A Rate'),
    ('CurveACap', 'Curve A Cap'),
    ('CurveAFloor', 'Curve A Floor'),
    ('CurveAQuote', 'Curve A Quote'),
    ('CurveADCC', 'Curve A DCC'),
    ('CurveACleanCoupon', 'Curve A Clean Coupon'),
    ('CurveBCategory', 'Curve B Category'),
    ('CurveBPct', 'Curve B Pct'),
    ('CurveB', 'Curve B'),
    ('CurveBSign', 'Curve B Sign'),
    ('CurveBRate', 'Curve B Rate'),
    ('CurveBCap', 'Curve B Cap'),
    ('CurveBFloor', 'Curve B Floor'),
    ('CurveBQuote', 'Curve B Quote'),
    ('CurveBDCC', 'Curve B DCC'),
    ('CurveBCleanCoupon', 'Curve B Clean Coupon'),
    ('VcpCurve', 'VCP Curve'),
    ('VcpCode', 'VCP Code'),
    ('VcpCategory', 'VCP Category'),
    ('VcpDescription', 'VCP Description'),
    ('InitialPrice', 'Initial Price'),
    ('InfoSource', 'Info Source'),
    ('QuoteDate', 'Quote Date'),
    ('QuoteDateCode', 'Quote Date D-n'),
    ('Denomination1', 'Denomination 1'),
    ('Denomination2', 'Denomination 2'),
    ('Denomination3', 'Denomination 3'),
    ('VcpText', 'VCP Text'),
    ('Observations', 'Observations'),
    ('Maker', 'Maker'),
    ('Checker', 'Checker'),
)
SWB_FIELDS = tuple(k for k, _ in SWB_COLUMNS)
SWB_LABELS = tuple(lbl for _, lbl in SWB_COLUMNS)
SWB_DATE_FIELDS = ('StartDate', 'MaturityDate', 'PremiumDate', 'QuoteDate', 'NotionalObsDate')

# Os literais que a página reconhece como "a nossa perna" no DT (Ativo VCP /
# Ativo Curva Vanilla / Pagador do Prêmio). Cego a caixa e acento.
_OUR_SIDE_RE = re.compile(r'J\.?\s*P\.?\s*MORGAN|\bJPM\b', re.I)
_ATACAMA_RE = re.compile(r'ATACAMA', re.I)

STATUS_SENDABLE = ('New', 'Approved')


# ── Normalização ─────────────────────────────────────────────────────────────

def norm(s):
    """Sem acento, MAIÚSCULO, só letras e dígitos — a chave de comparação de
    tudo que vem do DT (rótulos e valores) contra os cadastros."""
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]', '', s.upper())


def strip_accents(s):
    s = unicodedata.normalize('NFKD', str(s or ''))
    return ''.join(c for c in s if not unicodedata.combining(c))


_STOPWORDS = {'DE', 'DO', 'DA', 'DOS', 'DAS', 'COM', 'E', 'A', 'O'}


def _tokens(s):
    s = strip_accents(str(s or '')).upper()
    return {t for t in re.split(r'[^A-Z0-9]+', s) if t and t not in _STOPWORDS}


def code_by_label(rows, text, code_key='CODE', label_key='LABEL', width=2, field=None,
                  field_key='FIELD'):
    """Código B3 (zero-padded em `width`) da linha do cadastro cujo LABEL casa
    com `text`: exato normalizado, depois pelo CONJUNTO de tokens sem as
    palavras de ligação ('Opção de Arrependimento' ≡ 'OPCAO ARREPENDIMENTO').
    `field` restringe às linhas daquele FIELD (o `swap-code-labels` guarda
    vários de-para no mesmo cadastro). Sem casamento → ''."""
    alvo = norm(text)
    if not alvo:
        # '+' e '-' não sobrevivem à normalização: casam pelo literal.
        lit = str(text or '').strip()
        for r in rows or []:
            if field is not None and norm(r.get(field_key, '')) != norm(field):
                continue
            if lit and str(r.get(label_key, '') or '').strip() == lit:
                code = str(r.get(code_key, '') or '').strip()
                return code.zfill(width) if code.isdigit() else code
        return ''
    cands = []
    for r in rows or []:
        if field is not None and norm(r.get(field_key, '')) != norm(field):
            continue
        cands.append((norm(r.get(label_key, '')), _tokens(r.get(label_key, '')),
                      str(r.get(code_key, '') or '').strip()))
    for n, _t, code in cands:
        if n == alvo:
            return code.zfill(width) if code.isdigit() else code
    toks = _tokens(text)
    for _n, t, code in cands:
        if t and t == toks:
            return code.zfill(width) if code.isdigit() else code
    return ''


def spn_key(v):
    """Só dígitos, sem zeros à frente e sem o rabo `.0` (a mesma régua do
    `_spn_key` do routes — a SPN chega como texto, número ou planilha)."""
    s = str(v or '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    return re.sub(r'\D', '', s).lstrip('0')


def le_for_spn(rows, spn):
    """A linha do cadastro `le-spn` (Legal Entity × SPN) cuja SPN casa — a
    SPN de uma entidade NOSSA (ATACAMA, MGT, LAWTON, JPM) não está no
    Reference Data, está aqui. → dict {LE, NAME, SPN} ou None."""
    alvo = spn_key(spn)
    if not alvo:
        return None
    for r in rows or []:
        if spn_key(r.get('SPN', '')) == alvo and str(r.get('LE', '') or '').strip():
            return {'LE': str(r.get('LE', '')).strip().upper(), 'NAME': str(r.get('NAME', '') or '').strip(),
                    'SPN': str(r.get('SPN', '') or '').strip()}
    return None


def curve_code(rows, curve_name, category):
    """`Curva X(03)` da B3 para a curva do DT, pelo cadastro `swap-bullet-curve`
    (DT CURVE × MATCH Exact/Contains → B3 CODE). Exact vence Contains; entre
    os Contains vence o token mais longo. Categoria VCP sem linha cai na linha
    cujo DT CURVE é 'VCP' (é assim que 'MSFT US' vira C00 sem cadastrar cada
    ativo). Sem resposta → ''."""
    alvo = norm(curve_name)
    exato, contem = '', ('', -1)
    for r in rows or []:
        pat = norm(r.get('DT CURVE', ''))
        code = str(r.get('B3 CODE', '') or '').strip()
        if not pat or not code:
            continue
        mode = norm(r.get('MATCH', 'Exact'))
        if mode == 'CONTAINS':
            if alvo and pat in alvo and len(pat) > contem[1]:
                contem = (code, len(pat))
        elif pat == alvo:
            exato = code
    if exato:
        return exato
    if contem[0]:
        return contem[0]
    if norm(category) == 'VCP':
        for r in rows or []:
            if norm(r.get('DT CURVE', '')) == 'VCP' and str(r.get('B3 CODE', '') or '').strip():
                return str(r['B3 CODE']).strip()
    return ''


# ── Números e datas do DT ────────────────────────────────────────────────────

def parse_number(text):
    """'346.000,00' → 346000.0 · '9,772,760.00' → 9772760.0 · '100,00%' → 100.0
    · '117% Spot' → 117.0 · '82.820000' → 82.82 · 'BRL 346.000,00' → 346000.0.
    None quando não há número. O separador decimal é o ÚLTIMO dos dois
    sinais quando os dois aparecem; só um sinal com três dígitos depois é
    milhar ('346.000' → 346000), senão decimal."""
    s = str(text or '').strip()
    m = re.search(r'[-+]?\d[\d.,]*', s.replace(' ', ''))
    if not m:
        return None
    num = m.group(0)
    neg = num.startswith('-')
    num = num.lstrip('+-')
    if '.' in num and ',' in num:
        dec = num[max(num.rfind('.'), num.rfind(','))]
        num = num.replace('.' if dec == ',' else ',', '').replace(dec, '.')
    elif ',' in num:
        parts = num.split(',')
        if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and not s.rstrip().endswith('%')):
            num = num.replace(',', '')
        else:
            num = num.replace(',', '.')
    elif num.count('.') > 1:
        num = num.replace('.', '')
    try:
        v = float(num)
    except ValueError:
        return None
    return -v if neg else v


_MONTHS = {
    'JAN': 1, 'FEB': 2, 'FEV': 2, 'MAR': 3, 'APR': 4, 'ABR': 4, 'MAY': 5, 'MAI': 5,
    'JUN': 6, 'JUL': 7, 'AUG': 8, 'AGO': 8, 'SEP': 9, 'SET': 9, 'OCT': 10, 'OUT': 10,
    'NOV': 11, 'DEC': 12, 'DEZ': 12,
}
_MONTHS_PT = ('jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez')


def parse_date(text):
    """Data do DT → `date`. Aceita '15-Sep-26', '04/jun/27', '7-Jun-27',
    '15/09/2026', '2026-09-15', '20260915' e datetime/date. None se não lê."""
    if isinstance(text, datetime):
        text = text.date()
    if isinstance(text, date):
        return _safe_date(text.year, text.month, text.day)
    s = str(text or '').strip().split(' ')[0].split('T')[0]
    if not s:
        return None
    m = re.fullmatch(r'(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _safe_date(y, mo, d)
    m = re.fullmatch(r'(\d{4})(\d{2})(\d{2})', s)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.fullmatch(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})', s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        return _safe_date(y, mo, d)
    m = re.fullmatch(r'(\d{1,2})[/.\- ]([A-Za-z]{3})[A-Za-z]*[/.\- ](\d{2,4})', s)
    if m:
        mo = _MONTHS.get(strip_accents(m.group(2)).upper())
        y = int(m.group(3))
        if y < 100:
            y += 2000
        return _safe_date(y, mo, int(m.group(1))) if mo else None
    return None


def _safe_date(y, mo, d):
    # O Excel lê '15/ago/31' digitado como 1931 (dois dígitos 30-99 → 19xx) e
    # a célula chega assim; um DT de derivativo não tem data antes de 1990.
    if y is not None and y < 1990:
        y += 100
    try:
        return date(y, mo, d)
    except (ValueError, TypeError):
        return None


def iso(d):
    return d.strftime('%Y-%m-%d') if d else ''


def ymd(text):
    d = parse_date(text)
    return d.strftime('%Y%m%d') if d else ''


# ── O Deal Ticket: rótulos ───────────────────────────────────────────────────
# Rótulo normalizado (`norm`) → (bloco, chave). Bloco 'leg' são os rótulos que
# se repetem nas duas curvas; o parser decide a perna pela coluna/ordem.
_DT_LABELS = {
    'CLIENTE': ('top', 'Client'),
    'SPN': ('top', 'SPN'),
    'INICIO': ('top', 'StartDate'),
    'VENCIMENTO': ('top', 'MaturityDate'),
    'VALORBASE': ('top', 'Notional'),
    'FUNCIONALIDADES': ('top', 'Functionality'),
    'FUNCIONALIDADE': ('top', 'Functionality'),
    'ATIVOVCP': ('top', 'VcpHolder'),
    'ATIVOCURVAVANILLA': ('top', 'VanillaHolder'),
    'AGENDADEPREMIOS': ('top', 'PremiumSchedule'),
    'AGENDADEPREMIO': ('top', 'PremiumSchedule'),
    'DATADEPAGAMENTODOPREMIO': ('top', 'PremiumDate'),
    'PAGADORDOPREMIO': ('top', 'PremiumPayer'),
    'PREMIO': ('top', 'PremiumAmount'),
    'PERCENTUAL': ('leg', 'Pct'),
    'CATEGORIA': ('leg', 'Category'),
    'CURVA': ('leg', 'Curve'),
    'SINAL': ('leg', 'Sign'),
    'JUROS': ('leg', 'Rate'),
    'LIMSUPERIOR': ('leg', 'Cap'),
    'LIMITESUPERIOR': ('leg', 'Cap'),
    'LIMINFERIOR': ('leg', 'Floor'),
    'LIMITEINFERIOR': ('leg', 'Floor'),
    'PRECOINICIALCUPOMLIMPO': ('info', 'InitialPrice'),
    'PRECOINICIALCUPOMLIMPODOSPOT': ('info', 'InitialPrice'),
    'PRECOINICIAL': ('info', 'InitialPrice'),
    'FONTEDEINFORMACAO': ('info', 'InfoSource'),
    'DATADECOTACAO': ('info', 'QuoteDate'),
    'DENOMINACAO': ('info', 'Denomination'),
    'CATEGORIADACURVAVCP': ('ind', 'VcpCategory'),
    'CODIGO': ('ind', 'VcpCode'),
    'CURVAVCP': ('ind', 'VcpCurve'),          # com valor ao lado; sem valor é o cabeçalho do bloco
    'DESCRICAODACURVAVCP': ('ind', 'VcpDescription'),
}
_DT_BLOCK_HEADERS = {'CURVAVCP': 'vcp', 'CURVAVANILLA': 'vanilla', 'INFORMACOESCURVASVCP': 'info',
                     'INFORMACOESDOINDICADOR': 'ind'}
_DT_STOP_LABELS = {'OBS', 'INFORMACOESNECESSARIASPARAREGISTRO', 'LINKPARAOMANUALDEOPERACOES',
                   'DEALTICKETSWAPVCP'}
_DT_TITLE_RE = re.compile(r'^\s*SWAP\b', re.I)


def _label_of(cell):
    """(bloco, chave) se a célula é um rótulo do DT; None se é valor."""
    n = norm(cell)
    if not n:
        return None
    n = n.rstrip(':')
    if n.startswith('SINAL'):
        n = 'SINAL'
    if n.startswith('PRECOINICIAL'):
        n = 'PRECOINICIAL'          # 'Preço Inicial(Cupom Limpo) - % do Spot' e variantes
    if n in _DT_LABELS:
        return _DT_LABELS[n]
    return None


def is_dt_grid(grid):
    """A grade é um Deal Ticket? Precisa de Valor Base + Vencimento."""
    achou = set()
    for row in grid or []:
        for c in row:
            n = norm(c)
            if n in ('VALORBASE', 'VENCIMENTO', 'DEALTICKETSWAPVCP'):
                achou.add(n)
    return 'VALORBASE' in achou and 'VENCIMENTO' in achou


def parse_dt_grid(grid):
    """A grade de UMA aba do xlsx → os campos crus do DT (`raw`).

    Chaves 'top'/'info'/'ind' saem direto; as das pernas saem como
    `vcp_<Chave>` e `vanilla_<Chave>` pelo bloco cuja coluna de cabeçalho é a
    mais próxima à esquerda do rótulo. O valor de um rótulo são as células
    NÃO vazias à direita, na mesma linha, até o próximo rótulo/cabeçalho —
    juntas com espaço ('BRL' | '9,772,760.00' → 'BRL 9,772,760.00'). A
    Denominação continua nas linhas seguintes da mesma coluna enquanto a
    coluna do rótulo estiver vazia."""
    raw = {'_title': ''}
    header_cols = {}          # col → bloco ('vcp'/'vanilla'/'info')
    header_row = None
    ind_row = None
    rows = [list(r) for r in (grid or [])]
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            n = norm(cell)
            if n in ('CURVAVANILLA', 'INFORMACOESCURVASVCP') or (n == 'CURVAVCP' and not _value_right(row, ci)):
                header_cols[ci] = _DT_BLOCK_HEADERS[n]
                header_row = ri if header_row is None else min(header_row, ri)
            elif n == 'INFORMACOESDOINDICADOR':
                ind_row = ri
            elif not raw['_title'] and _DT_TITLE_RE.match(str(cell or '')) and 'DEALTICKET' not in n:
                raw['_title'] = str(cell).strip()
    denom_col = None
    denom_after_row = None
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            lab = _label_of(cell)
            if lab is None:
                continue
            bloco, chave = lab
            if bloco == 'leg':
                if header_row is None or ri <= header_row:
                    continue
                if ind_row is not None and ri > ind_row:
                    continue
                perna = _nearest_block(header_cols, ci)
                if perna not in ('vcp', 'vanilla'):
                    continue
                raw[perna + '_' + chave] = _value_right(row, ci)
            elif bloco == 'ind':
                if chave == 'VcpCurve':
                    v = _value_right(row, ci)
                    if v and (ind_row is None or ri > ind_row):
                        raw['VcpCurve'] = v
                    continue
                raw[chave] = _value_right(row, ci)
            elif chave == 'Denomination':
                raw['Denomination'] = [_value_right(row, ci)]
                denom_col, denom_after_row = ci, ri
            else:
                if chave in raw and raw[chave]:
                    continue
                raw[chave] = _value_right(row, ci)
    if denom_col is not None:
        for ri in range(denom_after_row + 1, min(denom_after_row + 6, len(rows))):
            row = rows[ri]
            if denom_col < len(row) and norm(row[denom_col]):
                break
            v = _value_right(row, denom_col)
            if not v:
                break
            if _label_of(v) is not None or norm(v) in _DT_STOP_LABELS:
                break
            raw['Denomination'].append(v)
    return raw


def _nearest_block(header_cols, ci):
    best, best_col = None, -1
    for col, bloco in header_cols.items():
        if col <= ci and col > best_col:
            best, best_col = bloco, col
    return best


def _value_right(row, ci):
    """Células não vazias à direita de `ci` até o próximo rótulo, com espaço.
    A célula IMEDIATAMENTE à direita é valor mesmo quando o texto coincide
    com um rótulo ('Ativo VCP | Cliente', 'Pagador do Premio | Cliente'):
    o rótulo `Cliente` do topo do DT é também a resposta dessas duas
    perguntas."""
    out = []
    for cj in range(ci + 1, min(len(row), ci + 12)):
        v = str(row[cj] if row[cj] is not None else '').strip()
        if not v:
            # Rótulo sem valor nas 3 colunas seguintes é rótulo em BRANCO: a
            # varredura não atravessa para o bloco vizinho ('Lim Superior'
            # vazio pegava a 3ª linha da Denominação, três blocos à direita).
            if out or cj - ci >= 3:
                break
            continue
        if norm(v) in _DT_BLOCK_HEADERS or norm(v) in _DT_STOP_LABELS:
            break
        if cj > ci + 1 and _label_of(v) is not None:
            break
        out.append(v)
    return ' '.join(out)


def parse_dt_text(text):
    """O texto de UM Deal Ticket em PDF → `raw` (o mesmo contrato do parser da
    grade). O texto vem sem coluna: os rótulos são achados em ORDEM e o valor
    de cada um é o que há entre ele e o rótulo seguinte. Três cuidados:

    * os rótulos das pernas se repetem — a 1ª aparição é a curva VCP e a 2ª a
      Vanilla (a ordem das colunas do DT);
    * 'Cliente' e 'Premio' são rótulos E respostas ('Ativo VCP Cliente'): um
      achado SEM valor logo depois de um rótulo também sem valor, na mesma
      linha, é o valor dele;
    * a Denominação continua nas linhas seguintes, coladas ao fim de outros
      rótulos ('Juros 0,00% Cupom Limpo inicial em percentual'): o que sobra
      depois do número do último rótulo numérico da linha é a continuação.
      A linha 'OBS:' e tudo o que vem nela ficam fora."""
    flat = str(text or '').replace('\r', '\n')
    labels = sorted(set(list(_DT_LABELS) + list(_DT_BLOCK_HEADERS) + ['OBS']), key=len, reverse=True)
    rx = re.compile(r'(?<![A-Za-z])(' + '|'.join(_label_regex(l) for l in labels) + r')\s*:?', re.I)
    line_starts = [0] + [m.end() for m in re.finditer(r'\n', flat)]

    def line_of(pos):
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo

    hits = []
    obs_lines = set()
    for m in rx.finditer(flat):
        # O DT imprime os rótulos com inicial MAIÚSCULA; 'em percentual' no
        # meio de uma denominação é texto, não o rótulo Percentual.
        if not (m.group(1)[:1].isupper() or m.group(1)[:1].isdigit()):
            continue
        n = norm(m.group(1))
        if n.startswith('SINAL'):
            n = 'SINAL'
        if n.startswith('PRECOINICIAL'):
            n = 'PRECOINICIAL'
        ln = line_of(m.start())
        if n == 'OBS' or n in _DT_STOP_LABELS:
            obs_lines.add(ln)
            continue
        hits.append([m.start(), m.end(), n, ln])
    hits = [h for h in hits if h[3] not in obs_lines]
    # valor de cada achado = até o próximo achado
    for i, h in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(flat)
        h.append(flat[h[1]:end])
    # 'Cliente'/'Premio' como VALOR do rótulo anterior sem valor, na mesma linha
    merged = []
    for h in hits:
        if merged and not h[4].strip() and not merged[-1][4].strip() and merged[-1][3] == h[3] \
                and h[2] in ('CLIENTE', 'PREMIO', 'JUROS', 'CURVA'):
            merged[-1][4] = flat[merged[-1][1]:h[1]]
            merged[-1][1] = h[1]
            continue
        merged.append(h)
    hits = merged

    raw = {'_title': ''}
    mt = re.search(r'^\s*(Swap\b[^\n]*)$', flat, re.I | re.M)
    if mt and 'DEAL TICKET' not in mt.group(1).upper():
        raw['_title'] = mt.group(1).strip()
    seen_leg = {}
    denom_line = None
    tails = {}          # linha → o que sobrou depois do último rótulo numérico
    NUMERIC_LEG = ('Pct', 'Rate', 'Cap', 'Floor')
    for i, (a, b, n, ln, val) in enumerate(hits):
        val_line = val.split('\n')[0].strip()
        if n in _DT_BLOCK_HEADERS and not (n == 'CURVAVCP' and val_line):
            continue
        lab = _DT_LABELS.get(n)
        if not lab:
            continue
        bloco, chave = lab
        last_on_line = (i + 1 >= len(hits)) or hits[i + 1][3] != ln
        if bloco == 'leg':
            k = seen_leg.get(chave, 0)
            perna = 'vcp' if k == 0 else 'vanilla'
            seen_leg[chave] = k + 1
            if chave in NUMERIC_LEG and last_on_line:
                m2 = re.match(r'^\s*([-+]?[\d.,]+\s*%?(?:\s*Spot)?)\s+(\S.*)$', val_line, re.I)
                if m2:
                    val_line, tails[ln] = m2.group(1).strip(), m2.group(2).strip()
            elif chave == 'Sign' and last_on_line:
                m2 = re.match(r'^\s*((?:\+/-\s*)?[+-])\s+(\S.*)$', val_line)
                if m2:
                    val_line, tails[ln] = m2.group(1), m2.group(2).strip()
            raw[perna + '_' + chave] = val_line
        elif chave == 'Denomination':
            if 'Denomination' not in raw:
                raw['Denomination'] = [x.strip() for x in val.split('\n') if x.strip()]
                denom_line = ln
        elif chave == 'VcpCurve':
            if val_line:
                raw['VcpCurve'] = val_line
        else:
            if raw.get(chave):
                continue
            raw[chave] = val_line
    if denom_line is not None:
        for ln in range(denom_line + 1, denom_line + 5):
            if ln in obs_lines:
                break
            if ln in tails and tails[ln]:
                raw['Denomination'].append(tails[ln])
    return raw


def _label_regex(label_norm):
    """'DATADEPAGAMENTODOPREMIO' → regex tolerante a espaço/acentos entre as
    letras ('Data de Pagamento do Premio'). Cada caractere pode ser seguido de
    espaços, pontuação leve e diacríticos."""
    parts = []
    for ch in label_norm:
        parts.append(_CHAR_CLASS.get(ch, re.escape(ch.lower())) + r'[\s./()\-]*')
    return ''.join(parts)


_CHAR_CLASS = {
    'A': '[AaÁáÀàÂâÃãÄä]', 'E': '[EeÉéÊêÈè]', 'I': '[IiÍíÎî]', 'O': '[OoÓóÔôÕõ]',
    'U': '[UuÚúÜü]', 'C': '[CcÇç]',
}
for _c in 'BDFGHJKLMNPQRSTVWXYZ':
    _CHAR_CLASS[_c] = '[%s%s]' % (_c, _c.lower())
for _d in '0123456789':
    _CHAR_CLASS[_d] = _d


# ── Do `raw` ao deal ─────────────────────────────────────────────────────────

def _is_ours(text):
    """O texto do DT aponta para a NOSSA perna? 'Banco JP Morgan', 'JPM',
    'Banco' sozinho. 'Cliente', 'Atacama' ou o nome de um cliente (mesmo um
    'Banco Safra') não."""
    t = strip_accents(str(text or ''))
    return bool(_OUR_SIDE_RE.search(t)) or norm(t) in ('BANCO', 'BANK', 'JPM', 'JPMORGAN')


def _clean_pct(text):
    v = parse_number(text)
    return '' if v is None else ('%.2f' % v)


def _clean_rate(text):
    v = parse_number(text)
    return '' if v is None else ('%.4f' % v)


def _clean_limit(text):
    v = parse_number(text)
    return '' if v is None or v == 0 else ('%.8f' % v).rstrip('0').rstrip('.')


def deal_from_raw(raw, trade_date_iso, deal_id=None):
    """`raw` (do xlsx ou do PDF) → o deal da grade. Puro: contas, SPN→cadastro,
    códigos e dias úteis são completados por `commands` depois.

    Parte A = a NOSSA perna (JPM, a Parte do arquivo): a curva cujo "Ativo" é
    o Banco. Parte B = a contraparte. Cliente 'Atacama' → par JPM x ATACAMA
    (o B2B); qualquer outro → JPM x CLI."""
    def g(k):
        return str(raw.get(k, '') or '').strip()

    vcp = {k[4:]: v for k, v in raw.items() if k.startswith('vcp_')}
    van = {k[8:]: v for k, v in raw.items() if k.startswith('vanilla_')}
    vcp_holder, van_holder = g('VcpHolder'), g('VanillaHolder')
    # Quem carrega o VCP? Se o Banco é o "Ativo VCP", A=VCP e B=Vanilla.
    if _is_ours(vcp_holder) and not _is_ours(van_holder):
        a, b = vcp, van
        a_cat, b_cat = 'VCP', 'JUROS'
    else:
        a, b = van, vcp
        a_cat, b_cat = 'JUROS', 'VCP'
    client = g('Client')
    is_ata = bool(_ATACAMA_RE.search(client))
    pair = 'JPM x ATACAMA' if is_ata else 'JPM x CLI'
    notional_txt = g('Notional')
    ccy = ''
    mccy = re.search(r'\b([A-Z]{3})\b', strip_accents(notional_txt).upper())
    if mccy and not mccy.group(1).isdigit():
        ccy = mccy.group(1)
    notional = parse_number(notional_txt)
    denom = raw.get('Denomination') or []
    if isinstance(denom, str):
        denom = [denom]
    denom = [str(x).strip() for x in denom if str(x).strip()]
    prem_sched = g('PremiumSchedule')
    prem_amt = parse_number(g('PremiumAmount'))
    deal = {
        'Type': 'Pagamento Final',
        'Title': g('_title'),
        'Pair': pair,
        # LE da linha: JPM contra cliente; ATACAMA no B2B (a perna intragrupo,
        # que gera o arquivo do Banco E o espelho da Atacama).
        'LE': 'ATACAMA' if is_ata else 'JPM',
        'Client': client,
        'ClientDT': client,
        'SPN': re.sub(r'\.0$', '', g('SPN')),
        'ClientAccount': '',
        'ClientTaxId': '',
        'StartDate': iso(parse_date(g('StartDate'))),
        'MaturityDate': iso(parse_date(g('MaturityDate'))),
        'Currency': ccy or 'BRL',
        'Notional': '' if notional is None else ('%.2f' % notional),
        'Adhesion': 'CGD',
        'Functionality': g('Functionality') or 'N/A',
        'PremiumSchedule': 'Sim' if norm(prem_sched) in ('SIM', 'YES', 'S', 'Y') else 'Não',
        'PremiumDate': iso(parse_date(g('PremiumDate'))),
        'PremiumPayer': g('PremiumPayer'),
        'PremiumAmount': '' if prem_amt is None else ('%.2f' % prem_amt),
        'Reset': 'Não',
        'LOB': 'EDG',
        'VcpHolder': vcp_holder,
        'VanillaHolder': van_holder,
        'CurveACategory': (a.get('Category') or a_cat).strip().upper(),
        'CurveAPct': _clean_pct(a.get('Pct')) or '100.00',
        'CurveA': a.get('Curve', '').strip(),
        'CurveASign': _sign(a.get('Sign')),
        'CurveARate': _clean_rate(a.get('Rate')) or '0.0000',
        'CurveACap': _clean_limit(a.get('Cap')),
        'CurveAFloor': _clean_limit(a.get('Floor')),
        'CurveBCategory': (b.get('Category') or b_cat).strip().upper(),
        'CurveBPct': _clean_pct(b.get('Pct')) or '100.00',
        'CurveB': b.get('Curve', '').strip(),
        'CurveBSign': _sign(b.get('Sign')),
        'CurveBRate': _clean_rate(b.get('Rate')) or '0.0000',
        'CurveBCap': _clean_limit(b.get('Cap')),
        'CurveBFloor': _clean_limit(b.get('Floor')),
        'VcpCurve': g('VcpCurve') or vcp.get('Curve', '').strip(),
        'VcpCode': re.sub(r'\.0$', '', g('VcpCode')),
        'VcpCategory': g('VcpCategory'),
        'VcpDescription': g('VcpDescription'),
        'InitialPrice': g('InitialPrice'),
        'InfoSource': g('InfoSource'),
        'QuoteDate': iso(parse_date(g('QuoteDate'))),
        'QuoteDateCode': '',
        'Denomination1': denom[0] if len(denom) > 0 else '',
        'Denomination2': denom[1] if len(denom) > 1 else '',
        'Denomination3': denom[2] if len(denom) > 2 else '',
        'VcpText': '',
        'TradeDate': trade_date_iso,
        'Status': 'New', 'Maker': '', 'Checker': '',
    }
    if prem_amt in (None, 0) and norm(prem_sched) not in ('SIM', 'YES', 'S', 'Y'):
        deal['PremiumSchedule'] = 'Não'
        deal['PremiumDate'] = deal['PremiumDate'] if deal['PremiumDate'] else ''
    # A chave da linha é um id INTERNO (hash do DT): o Deal Ticket não traz
    # número de operação, então a coluna Deal nasce em BRANCO para a mesa
    # preencher, e o B3 ID chega depois (Mapping / edição).
    deal['_id'] = deal_id or make_deal_id(deal)
    deal['Deal'] = ''
    deal['B3ID'] = ''
    deal['VcpText'] = vcp_text(deal)
    return deal


def _sign(text):
    """'+' / '-' — o ÚLTIMO sinal do texto: no PDF o rótulo 'Sinal +/-' chega
    colado ao valor ('+/- -')."""
    sinais = re.findall(r'[+-]', str(text or ''))
    return '-' if sinais and sinais[-1] == '-' else '+'


def make_deal_id(deal, prefix='SWB-'):
    """Chave INTERNA determinística do deal — o DT não traz número de
    operação. É o que deixa reimportar o mesmo arquivo sem duplicar (upsert
    por `_id`); a coluna Deal é da mesa. O `prefix` diz a página: `SWB-` no
    Bullet, `SWC-` no Cashflow."""
    base = '|'.join(norm(deal.get(k, '')) for k in
                    ('Client', 'StartDate', 'MaturityDate', 'Notional', 'VcpCurve', 'Pair'))
    return prefix + hashlib.sha1(base.encode('utf-8')).hexdigest()[:8].upper()


# ── A denominação da curva VCP (a fórmula da mesa) ──────────────────────────

def _proper(s):
    return ' '.join(w[:1].upper() + w[1:].lower() for w in str(s or '').split())


def _fmt_dd_mmm_aaaa(iso_date):
    d = parse_date(iso_date)
    if not d:
        return str(iso_date or '')
    return '%02d-%s-%04d' % (d.day, _MONTHS_PT[d.month - 1], d.year)


def vcp_text(deal, width=320):
    """O texto do campo Descrição (X(320)) da perna VCP, como a fórmula do
    Excel da mesa o monta — inclusive o travessão (–) entre os itens e o
    'Cupom limpo = Strike'. Segmentos sem valor caem fora; acentos saem
    (a fórmula tirava ã/ç/ó — aqui saem todos); o resultado é cortado em
    `width` e completado com espaços pelo motor do File Interpreter."""
    parts = [
        '%s : %s Código %s' % (deal.get('VcpCurve', ''), _proper(deal.get('VcpCategory', '')),
                               deal.get('VcpCode', '')),
        'Descrição: %s' % deal.get('VcpDescription', ''),
        'Preco Inicial: %s' % deal.get('InitialPrice', ''),
        'Fonte de informacao: %s' % deal.get('InfoSource', ''),
        'Data de cotacao: %s' % _fmt_dd_mmm_aaaa(deal.get('QuoteDate', '')),
    ]
    txt = ' – '.join(parts)
    tail = ['Cupom limpo = Strike']
    if str(deal.get('Denomination3', '') or '').strip():
        tail.append(str(deal['Denomination3']).strip())
    tail.append('Denominação: %s' % str(deal.get('Denomination1', '') or '').strip())
    txt += ' - ' + ' - '.join(tail)
    txt = strip_accents(txt)
    return txt[:width]


# ── Formatação B3 ────────────────────────────────────────────────────────────

def b3_num(value, int_digits, dec_digits):
    """9(int)v9(dec): número → dígitos sem ponto, zero-padded. None/'' → ''."""
    if value in (None, ''):
        return ''
    try:
        v = float(str(value).replace(',', '.')) if not isinstance(value, (int, float)) else float(value)
    except ValueError:
        return ''
    s = ('%.' + str(dec_digits) + 'f') % abs(v)
    ip, _, dp = s.partition('.')
    return ip.zfill(int_digits)[-int_digits:] + (dp if dec_digits else '')


def _blank(n):
    return ' ' * n


def _digits(s):
    return re.sub(r'\D', '', str(s or ''))


# ── As visões do deal (quem é Parte e quem é Contraparte em cada arquivo) ────

VIEWS = ('client', 'bank', 'atacama')


def view_sides(deal, view, accounts):
    """(parte, contraparte) de uma VISÃO do deal, cada lado como dict
    {le, account, taxid, curve: 'A'|'B', name}. `accounts` =
    {'JPM': '73760009', 'ATACAMA': '85398005', ...} (contas PRÓPRIAS do
    cadastro b3-accounts, só dígitos).

      client  → Parte JPM  · Contraparte cliente (conta do Reference Data ou
                omnibus + CNPJ)                                — par JPM x CLI
      bank    → Parte JPM  · Contraparte ATACAMA               — par JPM x ATACAMA
      atacama → Parte ATACAMA · Contraparte JPM (curvas trocadas) — ATACAMA x JPM
    """
    jpm = {'le': 'JPM', 'account': accounts.get('JPM', ''), 'taxid': '', 'curve': 'A',
           'name': 'JPM'}
    if view == 'client':
        cli = {'le': 'CLI', 'account': _digits(deal.get('ClientAccount')),
               'taxid': _digits(deal.get('ClientTaxId')), 'curve': 'B',
               'name': deal.get('Client', '')}
        return jpm, cli
    ata = {'le': 'ATACAMA', 'account': accounts.get('ATACAMA', ''), 'taxid': '', 'curve': 'B',
           'name': 'ATACAMA'}
    if view == 'bank':
        return jpm, ata
    ata_p = dict(ata, curve='B')
    jpm_c = dict(jpm, curve='A')
    return ata_p, jpm_c


def le_pair(view):
    return {'client': 'JPM x CLI', 'bank': 'JPM x ATACAMA', 'atacama': 'ATACAMA x JPM'}[view]


def is_b2b(deal):
    """O deal é o B2B Banco × Atacama? Pela LE da linha (ATACAMA) ou pelo par."""
    return norm(deal.get('LE', '')) == 'ATACAMA' or 'ATACAMA' in norm(deal.get('Pair', ''))


def views_of(deal):
    """As visões que o deal gera: cliente → ['client']; B2B → ['bank', 'atacama']."""
    return ['bank', 'atacama'] if is_b2b(deal) else ['client']


def _curve(deal, side):
    """Os campos da curva da perna `side` ('A'/'B') do deal."""
    p = 'Curve' + side
    return {
        'category': norm(deal.get(p + 'Category', '')),
        'pct': deal.get(p + 'Pct', ''),
        'name': deal.get(p, ''),
        'code': deal.get(p + 'Code', ''),
        'sign': deal.get(p + 'Sign', '+'),
        'rate': deal.get(p + 'Rate', ''),
        'cap': deal.get(p + 'Cap', ''),
        'floor': deal.get(p + 'Floor', ''),
    }


# ── O registro 0897 (Prêmio) ─────────────────────────────────────────────────

def premium_applies(deal):
    amt = parse_number(deal.get('PremiumAmount'))
    return norm(deal.get('PremiumSchedule')) in ('SIM', 'YES', 'S', 'Y') and bool(amt) \
        and bool(parse_date(deal.get('PremiumDate')))


def _ponta(account, parte_acc, contra_acc):
    """00 (Ponta 1) para a MENOR conta, 01 (Ponta 2) para a maior — o critério
    do manual (4.2.12): 'a conta do participante que tiver o MENOR número
    será a ponta 01'."""
    menor = min(_digits(parte_acc) or '0', _digits(contra_acc) or '0', key=lambda s: int(s or 0))
    return '00' if _digits(account) == menor else '01'


def premium_values(deal, view, accounts, swap_my_number, my_number, participant, today_ymd):
    """(header, registro, fluxo) do 0897 — cada um {seq: valor na largura}.

    Registro: 1 evento; Meu Número Reg. Contrato = o Meu Número do 0301 da
    mesma visão; Parte/Contraparte as mesmas; Papel = a PONTA da Parte pela
    conta menor. Fluxo: data e valor do prêmio; Titular = a PONTA de quem
    PAGA (pelo mesmo critério da conta menor — nos exemplos da mesa o
    cliente 74220005 paga e sai 01, o Banco 73760009 paga e sai 00 nas duas
    visões do B2B)."""
    parte, contra = view_sides(deal, view, accounts)
    header = {'1': 'SWAP ', '2': '0', '3': '0897', '4': str(participant or '').ljust(20)[:20],
              '5': today_ymd, '6': _blank(14)}
    reg = {'1': 'SWAP ', '2': '1', '3': '0897', '4': '0001',
           '5': _digits(swap_my_number).zfill(10)[-10:],
           '6': _digits(my_number).zfill(10)[-10:],
           '7': parte['account'].zfill(8)[-8:] if parte['account'] else _blank(8),
           '8': contra['account'].zfill(8)[-8:] if contra['account'] else _blank(8),
           '9': _ponta(parte['account'], parte['account'], contra['account'])}
    payer_ours = _is_ours(deal.get('PremiumPayer', ''))
    payer_acc = (parte if parte['le'] == 'JPM' else contra)['account'] if payer_ours \
        else (contra if parte['le'] == 'JPM' else parte)['account']
    flow = {'1': ymd(deal.get('PremiumDate')).ljust(8),
            '2': b3_num(deal.get('PremiumAmount'), 10, 2) or _blank(12),
            '3': _ponta(payer_acc, parte['account'], contra['account']),
            '4': _blank(30)}
    return header, reg, flow


PREMIUM_RECORD_LENGTH = 52


# ── Lacunas: o que o Send recusa ─────────────────────────────────────────────

def missing_for_send(deal, codes, accounts):
    """Lista de lacunas que impedem o arquivo — cada item diz o campo. Vazia =
    pode enviar."""
    faltas = []
    if not ymd(deal.get('StartDate')):
        faltas.append('Start Date')
    if not ymd(deal.get('MaturityDate')):
        faltas.append('Maturity Date')
    if parse_number(deal.get('Notional')) in (None, 0):
        faltas.append('Notional')
    if not codes.get('functionality'):
        faltas.append('Functionality (no B3 code in /mapping › Swap — Funcionalidade)')
    if not codes.get('adhesion'):
        faltas.append('Adhesion (no B3 code in /mapping › Swap — Sinal e Sim/Não)')
    for side in ('A', 'B'):
        if not codes.get('curve' + side):
            faltas.append('Curve %s (%r has no B3 code in /mapping › Swap Bullet — Curve)'
                          % (side, deal.get('Curve' + side, '')))
    if not accounts.get('JPM'):
        faltas.append('JPM own account (B3 Accounts)')
    if is_b2b(deal):
        if not accounts.get('ATACAMA'):
            faltas.append('ATACAMA own account (B3 Accounts)')
    else:
        # A contraparte é a do Reference Data pela SPN do DT: sem SPN, ou com
        # SPN que o cadastro não tem, o nome e a conta não têm de onde vir.
        if not _digits(deal.get('SPN')):
            faltas.append('SPN (the Deal Ticket has no SPN)')
        elif norm(deal.get('ClientRefData')) != 'OK':
            faltas.append('SPN %s not found in Reference Data' % deal.get('SPN'))
        if not _digits(deal.get('ClientAccount')):
            faltas.append('Client B3 Account')
    vcp_side = 'A' if norm(deal.get('CurveACategory')) == 'VCP' else \
        ('B' if norm(deal.get('CurveBCategory')) == 'VCP' else '')
    if vcp_side:
        if not _digits(deal.get('VcpCode')):
            faltas.append('VCP Code (Tipo/Classe)')
        if parse_number(deal.get('InitialPrice')) is None:
            faltas.append('Initial Price')
    if norm(deal.get('PremiumSchedule')) in ('SIM', 'YES', 'S', 'Y'):
        if not parse_date(deal.get('PremiumDate')):
            faltas.append('Premium Date')
        if not parse_number(deal.get('PremiumAmount')):
            faltas.append('Premium Amount')
        if not str(deal.get('PremiumPayer') or '').strip():
            faltas.append('Premium Payer')
    return faltas


# ── Depois do B3 ID: o que a operação REGISTRADA dispara ─────────────────────
# O B3 ID chega pela edição da linha (a mesa copia do retorno da B3). Com ele
# o deal é o `Success` das outras páginas de New Deals, e daí nascem:
#   * no B2B (Banco × Atacama), a linha da **Intrag Swap** — a visão da
#     ATACAMA (Parte Atacama, Contraparte Banco), na carteira dela;
#   * contra cliente, a linha do **Pending Confirmation** e a da esteira de
#     **Manual Confirmations** (Produto `SWAP` quando há Opção de
#     Arrependimento, `SWAP CORPORATE` sem ela), chaveadas pelo B3 ID.
# Aqui ficam só as regras; quem grava é o `commands`.

# A carteira da ATACAMA na Intrag. O NDF e a Opção intragrupo usam a
# INTRAGJP552 (o Lawton); o Monitor lê as duas (`deals_monitor/domain`).
INTRAG_SWAP_PORTFOLIO = 'INTRAGJP633'

# Os 36 campos da linha da Intrag Swap, na ORDEM das colunas da página
# `/intrag-swap` (`ENTRY_FIELDS` do template) — é o contrato do arquivo
# `Intrag-Swap-AAAAMMDD.txt` (`;` entre os valores).
INTRAG_SWAP_FIELDS = (
    'carteira', 'b3_id', 'start_date', 'maturity_date', 'base_value',
    'funcionalidades', 'parte', 'curva_parte', 'contraparte', 'curva_contraparte',
    'agenda_premios', 'premium_payment_date', 'premium_payer', 'premio',
    'pct_1', 'ref_code_1', 'categoria_1', 'codigo_1', 'sinal_1', 'juros_1',
    'lim_sup_1', 'lim_inf_1', 'quote_date_1', 'desc_vcp_1', 'preco_inicial_1',
    'pct_2', 'ref_code_2', 'categoria_2', 'codigo_2', 'sinal_2', 'juros_2',
    'lim_sup_2', 'lim_inf_2', 'quote_date_2', 'desc_vcp_2', 'preco_inicial_2',
)

_INTRAG_BANK_NAME = 'Banco JP Morgan'
_INTRAG_ATACAMA_NAME = 'Atacama'


def has_withdrawal_option(deal):
    """A funcionalidade do DT é a Opção de Arrependimento?"""
    return 'ARREPENDIMENTO' in norm(deal.get('Functionality', ''))


def confirmation_source(deal):
    """O Produto da esteira / Product Type do Pending Confirmation: `SWAP`
    com Opção de Arrependimento, `SWAP CORPORATE` sem ela (regra da mesa)."""
    return 'SWAP' if has_withdrawal_option(deal) else 'SWAP CORPORATE'


def plain_num(v):
    """Número como a Intrag o lê: sem separador de milhar, sem zeros à direita
    ('346000.00' → '346000', '100.00' → '100', '0.0000' → '0'); '' se não é número."""
    n = parse_number(v)
    if n is None:
        return ''
    s = ('%.8f' % n).rstrip('0').rstrip('.')
    return s or '0'


def _functionality_text(deal):
    txt = str(deal.get('Functionality') or '').strip()
    return '' if norm(txt) in ('', 'NA', 'N', 'NAO', 'NENHUMA', 'NONE', 'SEM') else txt


def intrag_swap_entry(deal, codes):
    """A linha da Intrag Swap do B2B — a visão da ATACAMA: Parte = Atacama com
    a perna DELA (a Curva B do deal, a contraparte do Banco), Contraparte =
    Banco com a Curva A. Bloco 1 é a curva da Parte, bloco 2 a da
    Contraparte; só a perna VCP leva Código (Tipo/Classe), Data de Cotação,
    Descrição (a denominação e o ativo) e Preço Inicial. `codes` são os
    códigos B3 das curvas (`queries.codes_for`)."""
    prem = norm(deal.get('PremiumSchedule')) in ('SIM', 'YES', 'S', 'Y')

    def leg(side):
        c = _curve(deal, side)
        vcp = c['category'] == 'VCP'
        desc = '; '.join(x for x in (str(deal.get('Denomination1') or '').strip(),
                                     str(deal.get('VcpCurve') or '').strip()) if x)
        return {
            'pct': plain_num(c['pct']),
            'ref_code': str(codes.get('curve' + side) or ''),
            'categoria': 'VCP' if vcp else str(c['name'] or '').strip().upper(),
            'codigo': _digits(deal.get('VcpCode')) if vcp else '',
            'sinal': 'Negativo' if str(c['sign'] or '+').strip() == '-' else 'Positivo',
            'juros': plain_num(c['rate']) or '0',
            'lim_sup': plain_num(c['cap']),
            'lim_inf': plain_num(c['floor']),
            'quote_date': iso(parse_date(deal.get('QuoteDate'))) if vcp else '',
            'desc_vcp': desc if vcp else '',
            'preco_inicial': str(deal.get('InitialPrice') or '').strip() if vcp else '',
        }

    parte, contra = leg('B'), leg('A')
    entry = {
        'carteira': INTRAG_SWAP_PORTFOLIO,
        'b3_id': str(deal.get('B3ID') or '').strip(),
        'start_date': iso(parse_date(deal.get('StartDate'))),
        'maturity_date': iso(parse_date(deal.get('MaturityDate'))),
        'base_value': plain_num(deal.get('Notional')),
        'funcionalidades': _functionality_text(deal),
        'parte': _INTRAG_ATACAMA_NAME,
        'curva_parte': 'VCP' if parte['categoria'] == 'VCP' else 'Vanilla',
        'contraparte': _INTRAG_BANK_NAME,
        'curva_contraparte': 'VCP' if contra['categoria'] == 'VCP' else 'Vanilla',
        'agenda_premios': 'Sim' if prem else 'Não',
        'premium_payment_date': iso(parse_date(deal.get('PremiumDate'))) if prem else '',
        'premium_payer': ((_INTRAG_BANK_NAME if _is_ours(deal.get('PremiumPayer', ''))
                           else _INTRAG_ATACAMA_NAME) if prem else ''),
        'premio': plain_num(deal.get('PremiumAmount')) if prem else '',
    }
    for n, lg in ((1, parte), (2, contra)):
        for k, v in lg.items():
            entry['%s_%d' % (k, n)] = v
    entry.update({
        '_deal': str(deal.get('_id') or deal.get('Deal') or ''),
        '_client': str(deal.get('Client') or ''),
        'status': 'New', 'maker': '', 'checker': '',
    })
    return entry


# ── A confirmação (Swap com Opção de Arrependimento) ─────────────────────────
# O que o documento precisa saber do deal e que a esteira não tem como
# adivinhar: a perna que carrega o Fator Equities (a VCP) e como o Preço
# Inicial se apura.
#
# **O Cupom Limpo diz de onde sai o Preço Inicial.** No DT ele é o campo
# 'Preço Inicial (Cupom Limpo)' ('100.00% Spot', '150%') junto com a 3ª linha
# da Denominação ('Preco in ativo Close 15-Sep-26'). Quando aparece **Close**,
# o preço é o fechamento do ativo naquele dia — o app busca a cotação (Quotes)
# e o Strike é o percentual sobre ela. Quando só diz **Spot**, o preço foi
# acertado na hora e não há de onde puxar: Preço Inicial e Strike ficam em
# BRANCO e o painel exige que a mesa os preencha antes de salvar.
_CLOSE_RE = re.compile(r'\bCLOSE\b[\s:\-]*(\d{1,2}[-/ ][A-Za-z]{3,9}[-/ ]\d{2,4})?', re.I)


def cupom_limpo(deal):
    """{'mode': 'close'|'spot'|'', 'date': ISO|'', 'pct': float|None} — como o
    Preço Inicial se apura (ver acima). `pct` é o percentual do Cupom Limpo
    ('100.00% Spot' → 100.0; em branco → None)."""
    txt = ' '.join(str(deal.get(k) or '') for k in ('InitialPrice', 'Denomination3', 'Denomination2'))
    pct = parse_number(deal.get('InitialPrice'))
    m = _CLOSE_RE.search(strip_accents(txt))
    if m:
        d = parse_date(m.group(1)) if m.group(1) else None
        return {'mode': 'close', 'date': iso(d) if d else '', 'pct': pct}
    if re.search(r'\bSPOT\b', strip_accents(txt), re.I):
        return {'mode': 'spot', 'date': '', 'pct': pct}
    return {'mode': '', 'date': '', 'pct': pct}


def vcp_side(deal):
    """'A' ou 'B': a perna que carrega o Fator Equities (a VCP); '' se nenhuma."""
    if norm(deal.get('CurveACategory')) == 'VCP':
        return 'A'
    if norm(deal.get('CurveBCategory')) == 'VCP':
        return 'B'
    return ''


def confirmation_deal(deal):
    """O deal no formato que a segregação das confirmações e a esteira leem
    (o das páginas de New Deals): `Deal`/`B3_ID` = o B3 ID (a chave da linha
    da esteira), `SettlementDate` = vencimento, `TaxID` = CNPJ da contraparte,
    `Status` = Success quando há B3 ID (registrado na B3 é o que Success
    significa nas outras páginas), e o que só o swap sabe em `_conf_*`."""
    b3 = str(deal.get('B3ID') or '').strip()
    out = dict(deal)
    out.update({
        'Deal': b3, 'B3_ID': b3,
        'SettlementDate': deal.get('MaturityDate', ''),
        'TaxID': deal.get('ClientTaxId', ''),
        'Status': 'Success' if b3 else (deal.get('Status') or 'New'),
        'Acronym': str(deal.get('Client') or '').strip(),
        '_conf_kind': confirmation_source(deal),
        '_conf_vcp_side': vcp_side(deal),
        '_conf_cupom': cupom_limpo(deal),
        '_conf_withdrawal': has_withdrawal_option(deal),
    })
    return out
