# -*- coding: utf-8 -*-
"""As regras do WHT (Withholding Tax), PURAS: não importam o `routes`, não
tocam banco nem arquivo. Quem traz os dados é o `queries`; quem grava é o
`commands`.

O IR das liquidações é recolhido por DECÊNDIO: 01–10, 11–20 e 21–último dia,
cada um pago no primeiro dia útil depois do seu fim. A página bate, decêndio a
decêndio, o que o OTC Tracker liquidou (o lado OTC) com o relatório "Posição de
Tributos" do HUB (o EasyTributos). Quatro coisas moram aqui:

  · o calendário do decêndio (`decendio_*`, `payment_date`);
  · a QUEBRA do piso de R$ 1,00 (`allocate`), que é a regra que o relatório do
    HUB precisa refletir e o recolhimento de fato não reflete;
  · o código de cada operação (`resolve_code`, sobre as linhas do cadastro
    `wht-codes` — nenhum código mora no código);
  · o batimento OTC × HUB (`match`) e o layout do arquivo que leva ao HUB as
    operações que ele não tem (`hub_file_lines`).
"""
import calendar
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

IR_MIN = 1.00            # o piso do mês por contraparte (§423, §674)
TOL = 0.01               # valor e imposto batem até 1 centavo

# Os produtos como o cadastro `wht-codes` os conhece (coluna PRODUCT).
PRODUCTS = ('NDF', 'NDF COMM', 'OPTION', 'OPTION COMM', 'SWAP')
# O número do documento no arquivo e no relatório do HUB tem no máximo 18
# caracteres, e o que o OTC Tracker gera começa pelo prefixo do produto.
DOC_MAX = 18
_PREFIXO = re.compile(r'^(NDF|OPT|SWP|CON|COO|COS)-(.+)$')

ST_MATCHED = 'Matched'
ST_PARTIAL = 'Partial'
ST_ONLY_OTC = 'Unmatched OTC'
ST_ONLY_HUB = 'Unmatched HUB'
STATUSES = (ST_ONLY_HUB, ST_ONLY_OTC, ST_PARTIAL, ST_MATCHED)

# (chave do check, nome que o Partial lista). O nome vai no Status da linha, e
# a pílula de status passa pelo Proper do Excel (§649): por isso "Tax" e não "IR".
CHECKS = (('TD', 'Trade Date'), ('GV', 'Gross Value'), ('IR', 'Tax'),
          ('cntpy', 'Counterparty'), ('id', 'Code'), ('tributo', 'Tributo'),
          ('LE', 'Legal Entity'))


# ── Texto, número e data ────────────────────────────────────────────────────
def norm(s):
    """Maiúsculas, sem acento, espaço colapsado."""
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', s).strip().upper()


def alnum(s):
    return re.sub(r'[^A-Z0-9]', '', norm(s))


def digits(s):
    return re.sub(r'\D', '', str(s or ''))


def cnpj_key(s):
    """CNPJ/CPF comparável: só dígitos, com o zero à esquerda que a planilha
    come de volta (CNPJ de 12-13 dígitos é um CNPJ lido como número)."""
    d = digits(s)
    if 11 < len(d) < 14:
        d = d.zfill(14)
    return d


def num(v):
    """Número de planilha ou de tela, BR ou US: o ÚLTIMO separador é o decimal
    quando há os dois; só vírgula é decimal; vários pontos são milhar. `None`
    quando não há número — que é diferente de zero."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace('R$', '').replace('\xa0', '').replace(' ', '')
    if not s:
        return None
    neg = s.startswith('-') or s.endswith('-') or (s.startswith('(') and s.endswith(')'))
    s = s.strip('()+-')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.') if s.rfind(',') > s.rfind('.') else s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '') if s.count(',') > 1 else s.replace(',', '.')
    elif s.count('.') > 1:
        s = s.replace('.', '')
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


def parse_date(v):
    """`date` de dd/mm/aaaa, dd/mm/aa, aaaa-mm-dd ou datetime; None se não é data."""
    if v is None or v == '':
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()[:19]
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d/%m/%y', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M:%S'):
        try:
            return datetime.strptime(s if ' ' in fmt else s[:10], fmt).date()
        except ValueError:
            continue
    return None


def dmy(d):
    return d.strftime('%d/%m/%Y') if d else ''


def r2(x):
    """Arredonda a 2 casas meio-para-cima (o `round` do Python é o do banqueiro)."""
    return float(Decimal(str(x or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


# ── O decêndio ──────────────────────────────────────────────────────────────
def decendio_of(d):
    """(ano, mês, n) do decêndio de `d`: 1 = 01–10, 2 = 11–20, 3 = 21–fim."""
    return d.year, d.month, (1 if d.day <= 10 else 2 if d.day <= 20 else 3)


def decendio_n(d):
    return decendio_of(d)[2]


def decendio_bounds(year, month, n):
    ini = {1: 1, 2: 11, 3: 21}[n]
    fim = {1: 10, 2: 20, 3: calendar.monthrange(year, month)[1]}[n]
    return date(year, month, ini), date(year, month, fim)


def decendio_key(year, month, n):
    return '%04d-%02d-D%d' % (year, month, n)


def payment_date(end, is_bizday):
    """O recolhimento: o primeiro dia útil DEPOIS do fim do decêndio."""
    d = end + timedelta(days=1)
    for _ in range(15):
        if is_bizday(d):
            return d
        d += timedelta(days=1)
    return d


def month_key(d):
    return '%04d%02d' % (d.year, d.month)


# ── O piso de R$ 1,00, quebrado por operação ────────────────────────────────
def allocate(rows):
    """O IR que cada operação tem de mostrar no relatório do HUB.

    O piso de R$ 1,00 é do MÊS, por contraparte (§423, §674): enquanto o
    acumulado do mês não alcança R$ 1,00, nada é retido e a liquidação sai
    bruta; quando alcança, retém-se o acumulado. O relatório do HUB mostra o
    imposto onde ele foi RECOLHIDO (as operações anteriores zeradas e a que
    passou do piso com tudo), mas o que tem de constar é o imposto de cada
    operação no seu decêndio:

      · decêndio ANTERIOR ao que passou do piso: zero (naquele decêndio não
        havia imposto a recolher, e é assim que ele foi informado);
      · o decêndio em que o acumulado passou de R$ 1,00: cada operação com o
        SEU imposto, e a que passou leva também o que veio dos decêndios
        anteriores do mês (que lá foram informados zerados);
      · decêndio seguinte: cada operação com o seu imposto;
      · mês que não alcança o piso: tudo zero.

    `rows` = [{'id', 'bucket', 'date' (date), 'devido' (float), 'floor' (bool),
    'seq'}]; operação sem piso (o swap, com a tabela regressiva) mostra o
    próprio imposto. Devolve {id: IR informado}. A ordem dentro do mês é a
    data e depois `seq` (a ordem estável de chegada)."""
    out, baldes = {}, {}
    for r in rows:
        if not r.get('floor'):
            out[r['id']] = r2(r.get('devido') or 0.0)
            continue
        d = r['date']
        baldes.setdefault((r.get('bucket') or '', d.year, d.month), []).append(r)
    for items in baldes.values():
        items.sort(key=lambda r: (r['date'], r.get('seq') or 0))
        acc, cruza = 0.0, None
        for i, r in enumerate(items):
            acc = r2(acc + (r.get('devido') or 0.0))
            if (r.get('devido') or 0.0) > 0 and acc >= IR_MIN:
                cruza = i
                break
        if cruza is None:
            for r in items:
                out[r['id']] = 0.0
            continue
        k = decendio_n(items[cruza]['date'])
        carry = r2(sum((r.get('devido') or 0.0) for r in items if decendio_n(r['date']) < k))
        for i, r in enumerate(items):
            v = 0.0 if decendio_n(r['date']) < k else (r.get('devido') or 0.0)
            if i == cruza:
                v += carry
            out[r['id']] = r2(v)
    return out


# ── O código da operação (cadastro `wht-codes`) ─────────────────────────────
def _tokens(s):
    return set(t for t in re.split(r'[^A-Z0-9]+', norm(s)) if t)


def resolve_code(rows, product, lob='', event='', taxable=True, resident=True):
    """A linha do `wht-codes` da operação, ou None.

    PRODUCT tem de ser o mesmo; TAXATION em branco vale para os dois; LOB,
    EVENT e RESIDENCE em branco são coringa. A linha mais ESPECÍFICA vence
    (LOB > EVENT > RESIDENCE), e no empate a primeira do cadastro."""
    prod = norm(product)
    want_tax = 'TAXABLE' if taxable else 'EXEMPT'
    want_res = 'RESIDENT' if resident else 'NON-RESIDENT'
    ev = _tokens(event)
    best, score = None, -1
    for r in rows or ():
        if norm(r.get('PRODUCT')) != prod:
            continue
        tx = norm(r.get('TAXATION'))
        if tx and tx != want_tax:
            continue
        s = 0
        lb = norm(r.get('LOB'))
        if lb:
            if lb != norm(lob):
                continue
            s += 4
        e = _tokens(r.get('EVENT'))
        if e:
            if not e <= ev:
                continue
            s += 2
        rs = norm(r.get('RESIDENCE'))
        if rs:
            if rs.replace(' ', '-') != want_res:
                continue
            s += 1
        if s > score:
            best, score = r, s
    return best


def yes(v):
    return norm(v) in ('YES', 'Y', 'SIM', 'S', 'TRUE', '1')


def doc_number(prefix, internal_id):
    """O número do documento do arquivo que vai ao HUB: `<PREFIXO>-<id>`, no
    máximo 18 caracteres."""
    iid = str(internal_id or '').strip().upper()
    p = str(prefix or '').strip().upper()
    return ((p + '-' + iid) if p and iid else iid)[:DOC_MAX]


def doc_matches(hub_doc, otc_doc, otc_id):
    """O Docto do HUB é desta operação?

    O HUB guarda no máximo 18 caracteres: a operação que entrou pelo sistema
    vem com o identificador cortado (`STP-4T6-3LS149D-0-`), a que entrou pelo
    arquivo do OTC Tracker vem com o prefixo (`SWP-270RI70427368`)."""
    h = str(hub_doc or '').strip().upper()
    iid = str(otc_id or '').strip().upper()
    if not h or not iid:
        return False
    if h in (str(otc_doc or '').strip().upper(), iid, iid[:DOC_MAX]):
        return True
    m = _PREFIXO.match(h)
    if m:
        resto = m.group(2)
        if resto == iid or (len(h) >= DOC_MAX and iid.startswith(resto)):
            return True
    return False


# ── O batimento ─────────────────────────────────────────────────────────────
def _mesmo_nome(a, b):
    a, b = alnum(a), alnum(b)
    if not a or not b:
        return False
    if a == b:
        return True
    curto, longo = sorted((a, b), key=len)
    return len(curto) >= 6 and longo.startswith(curto)


def _check_cntpy(o, h):
    ca, cb = cnpj_key(o.get('taxid')), cnpj_key(h.get('cnpj'))
    if ca and cb:
        return ca == cb
    return _mesmo_nome(o.get('counterparty'), h.get('name'))


def _iguais(a, b):
    return norm(a) == norm(b) and bool(norm(a))


def _checks(o, h):
    return {
        'TD': bool(o.get('date')) and o.get('date') == h.get('date'),
        'GV': o.get('gross') is not None and h.get('gross') is not None
              and abs(o['gross'] - h['gross']) <= TOL + 1e-9,
        'IR': abs((o.get('ir') or 0.0) - (h.get('ir') or 0.0)) <= TOL + 1e-9,
        'cntpy': _check_cntpy(o, h),
        'id': _iguais(o.get('code'), h.get('code')),
        'tributo': _iguais(o.get('tributo'), h.get('tributo')),
        'LE': _iguais(o.get('le'), h.get('le')),
    }


def _melhor(otc, cands, h):
    """Entre as operações OTC que o Docto aponta (índices), a mais parecida com
    a linha do HUB: mesma entidade, mesma contraparte, mesma data, bruto mais perto."""
    def nota(i):
        o = otc[i]
        return (not _iguais(o.get('le'), h.get('le')),
                not _check_cntpy(o, h),
                o.get('date') != h.get('date'),
                abs((o.get('gross') or 0.0) - (h.get('gross') or 0.0)), i)
    return min(cands, key=nota)


def match(otc, hub):
    """Pares (otc, hub): cada linha do HUB casa com UMA operação OTC pelo
    Docto (`doc_matches`); o que sobra de cada lado vem sozinho. A ordem é a
    das operações OTC e depois a das linhas do HUB que ficaram sem par."""
    livres = list(range(len(otc)))
    par_de = {}
    sobra_hub = []
    for hi, h in enumerate(hub):
        cands = [i for i in livres if doc_matches(h.get('docto'), otc[i].get('doc'),
                                                  otc[i].get('internal_id'))]
        if not cands:
            sobra_hub.append(hi)
            continue
        i = _melhor(otc, cands, h)
        livres.remove(i)
        par_de[i] = hi
    pares = [(o, hub[par_de[i]] if i in par_de else None) for i, o in enumerate(otc)]
    pares += [(None, hub[hi]) for hi in sobra_hub]
    return pares


def _money(v):
    return None if v is None else r2(v)


def row_of(o, h):
    """A linha da tabela para um par do batimento."""
    if o and h:
        ck = _checks(o, h)
        diff = [nome for k, nome in CHECKS if not ck[k]]
        status = ST_MATCHED if not diff else ST_PARTIAL
    else:
        ck, diff = {}, []
        status = ST_ONLY_OTC if o else ST_ONLY_HUB
    o, h = o or {}, h or {}
    row = {
        'key': (o.get('id') or ('HUB|' + str(h.get('key') or ''))),
        'Status': status if status != ST_PARTIAL else '%s - %s' % (ST_PARTIAL, ', '.join(diff)),
        'status': status,
        'differences': diff,
        'Internal ID': o.get('internal_id') or h.get('docto') or '',
        'B3 Id': o.get('b3_id') or '',
        'Product': o.get('product') or '',
        'LOB': o.get('lob') or '',
        'Event': o.get('event') or '',
        'OTC_TD': dmy(o.get('date')), 'HUB_TD': dmy(h.get('date')),
        'OTC_GV': _money(o.get('gross')), 'HUB_GV': _money(h.get('gross')),
        'OTC_IR': _money(o.get('ir')) if o else None, 'HUB_IR': _money(h.get('ir')) if h else None,
        'Devido': _money(o.get('devido')) if o else None,
        'OTC_cntpy': o.get('counterparty') or '', 'HUB_cntpy': h.get('name') or '',
        'OTC_id': o.get('code') or '', 'HUB_id': h.get('code') or '',
        'OTC_tributo': o.get('tributo') or '', 'HUB_tributo': h.get('tributo') or '',
        'OTC_LE': o.get('le') or '', 'HUB_LE': h.get('le') or '',
        'OTC_taxid': o.get('taxid') or '', 'HUB_taxid': h.get('cnpj') or '',
        'HUB_doc': h.get('docto') or '', 'OTC_doc': o.get('doc') or '',
        'HUB_file': h.get('file') or '',
    }
    for k, _nome in CHECKS:
        row['Check_' + k] = ck.get(k) if ck else None
    return row


def summary(rows):
    """O resumo do topo: por CÓDIGO (o T.Oper), quantas operações, o bruto e o
    imposto de cada lado. Cada lado conta pelo SEU código — uma operação com o
    código divergente aparece nas duas linhas, que é exatamente o que se quer
    ver."""
    acc = {}

    def linha(code, tributo):
        return acc.setdefault(code or '—', {'code': code or '—', 'tributo': tributo or '',
                                            'otc_n': 0, 'otc_gross': 0.0, 'otc_ir': 0.0,
                                            'hub_n': 0, 'hub_gross': 0.0, 'hub_ir': 0.0})
    for r in rows:
        if r['status'] != ST_ONLY_HUB:
            a = linha(r['OTC_id'], r['OTC_tributo'])
            a['otc_n'] += 1
            a['otc_gross'] += r['OTC_GV'] or 0.0
            a['otc_ir'] += r['OTC_IR'] or 0.0
        if r['status'] != ST_ONLY_OTC:
            a = linha(r['HUB_id'], r['HUB_tributo'])
            if not a['tributo']:
                a['tributo'] = r['HUB_tributo']
            a['hub_n'] += 1
            a['hub_gross'] += r['HUB_GV'] or 0.0
            a['hub_ir'] += r['HUB_IR'] or 0.0
    out = []
    for code in sorted(acc):
        a = acc[code]
        for k in ('otc_gross', 'otc_ir', 'hub_gross', 'hub_ir'):
            a[k] = r2(a[k])
        a['diff_gross'] = r2(a['otc_gross'] - a['hub_gross'])
        a['diff_ir'] = r2(a['otc_ir'] - a['hub_ir'])
        out.append(a)
    return out


def counts(rows):
    c = {s: 0 for s in STATUSES}
    for r in rows:
        c[r['status']] = c.get(r['status'], 0) + 1
    c['total'] = len(rows)
    return c


# ── O relatório do HUB ("Posição de Tributos", EasyTributos) ────────────────
_HDR = (  # (chave, teste sobre o rótulo sem pontuação)
    ('contribuinte', lambda k: k == 'CONTRIBUINTE'),
    ('filial', lambda k: k == 'FILIAL'),
    ('emissao', lambda k: k.startswith('EMISS')),
    ('code', lambda k: k == 'TOPER'),
    ('docto', lambda k: k == 'DOCTO'),
    ('noaux', lambda k: k == 'NOAUX'),
    ('gross', lambda k: k.startswith('VLRLAN')),
    ('rend', lambda k: k.startswith('RENDTRIB')),
    ('tributo', lambda k: k == 'TRIBUTO'),
    ('fato', lambda k: k.startswith('FATOGER')),
    ('vcto', lambda k: k == 'VCTO'),
    ('pagto', lambda k: k == 'PAGTO'),
    ('ir', lambda k: k.startswith('VLRTRIB')),
    ('ndocrec', lambda k: k == 'NDOCREC'),
    ('sis', lambda k: k == 'SIS'),
)


def _header(cells):
    """{chave: coluna} quando a linha é o cabeçalho do relatório, senão None."""
    m = {}
    for i, c in enumerate(cells):
        k = alnum(c)
        if not k:
            continue
        for chave, teste in _HDR:
            if chave not in m and teste(k):
                m[chave] = i
                break
    return m if ('contribuinte' in m and 'code' in m and 'docto' in m) else None


def parse_hub_report(rows, file_name=''):
    """As linhas de operação do relatório, de qualquer formato que o leitor de
    planilha devolva (lista de listas). O relatório vem em BLOCOS por empresa
    ("Empresa: 00001 - Banco J.P. Morgan S.A."), cada um com o seu cabeçalho; a
    coluna do nome do contribuinte não tem rótulo (é a do lado do CNPJ).

    Devolve (registros, info) — info diz as empresas vistas e quantas linhas
    ficaram de fora, para o "0 linhas" não ser mudo."""
    out, empresas, empresa, cols = [], [], '', None
    ignoradas = 0

    def texto_de(c):
        # Número inteiro de planilha (o CNPJ gravado como número) sem o ".0".
        if isinstance(c, float) and c.is_integer():
            return str(int(c))
        return '' if c is None else str(c)
    for r in rows or ():
        cells = [texto_de(c).strip() for c in (r or ())]
        texto = ' '.join(c for c in cells if c)
        m = re.match(r'^EMPRESA\s*:?\s*(\d+)', norm(texto))
        if m:
            empresa = m.group(1).zfill(5)
            if empresa not in empresas:
                empresas.append(empresa)
            continue
        h = _header(cells)
        if h:
            cols = h
            continue
        if cols is None:
            continue

        def cel(k):
            i = cols.get(k)
            return cells[i] if (i is not None and i < len(cells)) else ''
        cnpj, docto = cnpj_key(cel('contribuinte')), cel('docto').upper()
        if not docto or len(cnpj) < 11:
            if any(cells):
                ignoradas += 1
            continue
        # O nome: a primeira célula preenchida entre o CNPJ e a próxima coluna rotulada.
        ci = cols['contribuinte']
        prox = min([i for i in cols.values() if i > ci] or [len(cells)])
        nome = next((cells[i] for i in range(ci + 1, min(prox, len(cells))) if cells[i]), '')
        fato = parse_date(cel('fato')) or parse_date(cel('emissao'))
        out.append({
            'empresa': empresa, 'cnpj': cnpj, 'name': nome, 'filial': cel('filial'),
            'emissao': parse_date(cel('emissao')), 'code': cel('code').upper(),
            'docto': docto, 'noaux': cel('noaux'),
            'gross': num(cel('gross')), 'rend': num(cel('rend')),
            'tributo': cel('tributo').upper(), 'date': fato,
            'vcto': parse_date(cel('vcto')), 'pagto': parse_date(cel('pagto')),
            'ir': num(cel('ir')) or 0.0, 'ndocrec': cel('ndocrec'), 'sis': cel('sis'),
            'file': file_name,
        })
    return out, {'empresas': empresas, 'ignored': ignoradas, 'header': cols is not None}


def hub_key(h):
    """A identidade da linha do HUB dentro do mês (a reimportação a substitui)."""
    return '|'.join((h.get('empresa') or '', h.get('docto') or '', h.get('code') or '',
                     h.get('tributo') or '', (h.get('date') or '').isoformat()
                     if hasattr(h.get('date'), 'isoformat') else str(h.get('date') or '')))


def darf_of(code_or_tributo):
    return digits(code_or_tributo)[:4]


# ── O arquivo que leva ao HUB as operações que ele não tem ──────────────────
#  Reconstruído do arquivo que a planilha auxiliar da equipe gera (quatro
#  linhas por operação). Valor é 15 inteiros + 2 decimais (17 posições),
#  alíquota 2 + 2 (4), data ddmmaaaa, texto alinhado à esquerda com espaço:
#
#    1  empresa(5) filial(4) CNPJ/CPF(14) documento(18) data do movimento(8)
#       tipo de operação(11)                                               60
#    2  g rendimento · h/i/j deduções IR/IOF/CPMF · k IRRF · l IOF · m CPMF ·
#       n valor da operação · o IRRF retido antes · p prejuízo compensado ·
#       q base IRRF · r base IOF · s base CPMF (13 × 17) · t/u/v alíquotas
#       IRRF/IOF/CPMF (3 × 4)                                             233
#    3  w1–w4 rendimento/imposto residual, rendimento base, imposto
#       complementar (4 × 17) · z data da aplicação(8) · y data de inclusão(8) 84
#    4  ex1–ex5 suspenso, isenção, custas, advogado, depósito (5 × 17)        85
#
#  Os campos de texto que a planilha deixa em branco depois da data de inclusão
#  (documento auxiliar, centro de custo, observação…) não aparecem no arquivo
#  de exemplo e não são escritos.
_VAL, _ALIQ = 17, 4


def _v(x, n=_VAL):
    cents = int(Decimal(str(abs(x or 0.0))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) * 100)
    return str(cents).zfill(n)[-n:]


def _t(s, n):
    return str(s or '')[:n].ljust(n)


def hub_file_lines(items, inclusion):
    """As linhas do arquivo. `items` = [{'empresa', 'filial', 'cnpj', 'doc',
    'date' (date), 'code', 'gross', 'ir', 'rate' (% ou None)}]."""
    linhas = []
    for it in items:
        g = it.get('gross') or 0.0
        ir = it.get('ir') or 0.0
        rate = it.get('rate') or 0.0
        linhas.append(''.join((
            digits(it.get('empresa')).zfill(5)[-5:], digits(it.get('filial')).zfill(4)[-4:],
            cnpj_key(it.get('cnpj')).zfill(14)[-14:], _t(it.get('doc'), DOC_MAX),
            it['date'].strftime('%d%m%Y'), _t(it.get('code'), 11))))
        valores = [g, 0, 0, 0, ir, 0, 0, g, 0, 0, g, 0, 0]
        linhas.append(''.join(_v(x) for x in valores) + _v(rate, _ALIQ) + _v(0, _ALIQ) + _v(0, _ALIQ))
        linhas.append(''.join(_v(0) for _ in range(4)) + ' ' * 8 + inclusion.strftime('%d%m%Y'))
        linhas.append(''.join(_v(0) for _ in range(5)))
    return linhas


# ── Mensagens estruturadas (a tela as diz no idioma de quem usa, §486) ──────
class WhtError(Exception):
    def __init__(self, code, text, **params):
        Exception.__init__(self, text)
        self.code, self.params, self.text = code, params, text


def aviso(code, text, **params):
    return {'code': code, 'params': params, 'text': text}
