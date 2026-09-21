# -*- coding: utf-8 -*-
"""As regras PURAS das recompras do catalogo. Sem Flask, sem banco, sem arquivo.

Uma pagina e uma entrada do `catalog` (colunas, layout da B3, de onde sai a
posicao, que conferencias o Check faz), e tudo aqui recebe essa entrada: produto
novo e uma linha no catalogo, nao uma funcao nova.

O caminho da linha:

  planilha (rotulos OU nomes de campo do catalogo, cegos a caixa e acento)
    -> linha da tela (`linhas_da_planilha`)
    -> a POSICAO completa o que a planilha deixou em branco (`completar`) —
       achada pelo B3 ID, ou por CARACTERISTICAS quando ela chega sem id
       (`casar_por_caracteristicas`, so com candidato UNICO)
    -> o veredito de TRES estados (`conferir`)
    -> os valores do arquivo da B3 (`campos_*`), montado pelo motor do File
       Interpreter.

Nada se inventa: o que a planilha nao traz e a posicao nao responde fica VAZIO
e vira aviso por CODIGO (§486) — a tela diz a frase.
"""
import re
import unicodedata
from datetime import date, datetime, timedelta

from apps.pages.features.unwinds import catalog
from apps.pages.features.unwinds import domain as fase1

STATUS_NOVO = fase1.STATUS_NOVO
STATUS_PENDENTE = fase1.STATUS_PENDENTE
STATUS_APROVADO = fase1.STATUS_APROVADO
STATUS_ENVIADO = fase1.STATUS_ENVIADO
STATUS_ENVIAVEL = fase1.STATUS_ENVIAVEL
CHECK_OK, CHECK_NOK, CHECK_NA = fase1.CHECK_OK, fase1.CHECK_NOK, fase1.CHECK_NA

# O que NAO vem da planilha nem se edita na grade: a chave, os dois veredictos
# (estado da esteira e conferencia apurada) e o rastro. Coluna de planilha com
# um desses rotulos e IGNORADA — um `Status = Sent` colado de outra aba nao pode
# pular o 4-olhos.
NAO_EDITAVEL = ('_id', 'Status', 'Check', 'Maker', 'Checker', 'MyNumber', 'SentFiles',
                'SentAt', 'Warnings', 'ImportedAt', 'PositionDate', 'SourceFile',
                'PositionFound')

TOLERANCIA = 0.01           # um centavo, como a Fase 1
BASE_DU = 252.0
CCY_REAIS = ('BRL', 'BRR')


def aviso(code, text, **params):
    return {'code': code, 'params': params, 'text': text}


class Recusa(ValueError):
    """Uma recusa com CODIGO (§486): a tela diz a frase pelo `e_<code>` e o
    texto e so o fallback. `status` e o HTTP que o entrypoint devolve."""

    def __init__(self, code, text, status=400, **params):
        ValueError.__init__(self, text)
        self.code, self.text, self.status, self.params = code, text, status, params

    def payload(self):
        return {'success': False, 'code': self.code, 'params': self.params,
                'message': self.text}


def norm(s):
    """Minusculas, sem acento, so letras e digitos: `Original Quantity`,
    `original_quantity` e `ORIGINAL QUANTITY` sao a mesma coluna."""
    t = unicodedata.normalize('NFKD', str(s or '')).lower()
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]', '', t)


def norm_nome(s):
    """Nome de contraparte para comparar: sem acento, sem pontuacao, espacos unicos."""
    t = unicodedata.normalize('NFKD', str(s or '')).upper()
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^A-Z0-9 ]', ' ', t).split())


def digitos(v):
    return ''.join(ch for ch in str(v or '') if ch.isdigit())


# ==============================================================================
#  LEITURA DE CELULA
# ==============================================================================

def numero(v, taxa=False):
    """Numero de uma celula de planilha ou de TELA, ou None.

    Numero de verdade (o xlsx entrega float) passa direto. Texto segue a regra
    da casa (`_num_tela` das Tools, `numero_flex` da Fase 1): o ULTIMO separador
    manda (`587,224.31` = `587.224,31`), e com um separador so tres digitos
    depois dele e MILHAR — menos numa TAXA (`taxa=True`), onde `5.374` e 5,374."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v or '').strip()
    if not t or t in ('-', '—'):
        return None
    neg = t.startswith('-') or (t.startswith('(') and t.endswith(')'))
    t = t.strip('()').lstrip('+-').replace('%', '').replace(' ', '').strip()
    ult_v, ult_p = t.rfind(','), t.rfind('.')
    if ult_v >= 0 and ult_p >= 0:
        dec = max(ult_v, ult_p)
        t = t[:dec].replace(',', '').replace('.', '') + '.' + t[dec + 1:]
    elif ult_v >= 0 or ult_p >= 0:
        i = max(ult_v, ult_p)
        if t.count(t[i]) > 1:           # `1,234,567`: separador repetido so e milhar
            t = t.replace(t[i], '')
        else:
            milhar = (not taxa) and len(t) - i - 1 == 3
            t = (t[:i] + t[i + 1:]) if milhar else (t[:i] + '.' + t[i + 1:])
    try:
        x = float(t)
    except ValueError:
        return None
    return -x if neg else x


_EXCEL_EPOCH = date(1899, 12, 30)


def data_iso(v):
    """Data de celula -> 'AAAA-MM-DD', ou None. Aceita `datetime`/`date` (xlsx),
    serial do Excel, `dd/mm/aaaa` (a casa escreve assim, §7), ISO e `aaaammdd`.
    `mm/dd` NUNCA: as duas leituras dao dias diferentes na mesma celula."""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 20000 < float(v) < 80000:
            return (_EXCEL_EPOCH + timedelta(days=int(v))).isoformat()
        v = str(int(v))
    t = str(v or '').strip()
    if not t:
        return None
    t = t.split(' ')[0].split('T')[0]
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%Y%m%d', '%d-%m-%Y', '%d.%m.%Y'):
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def texto(v):
    """Texto de celula. Numero inteiro que o Excel guardou como float (a conta
    `73760009.0`, o contrato) volta sem a cauda."""
    if v is None:
        return ''
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (datetime, date)):
        return v.isoformat()[:10]
    return str(v).strip()


def valor_da_celula(v, kind):
    """(valor, erro) na forma do TIPO da coluna. Celula vazia e (None, None)."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None, None
    if kind == 'date':
        d = data_iso(v)
        return (d, None) if d else (texto(v), 'unwind_bad_date')
    if kind in ('money', 'rate'):
        n = numero(v, taxa=(kind == 'rate'))
        return (n, None) if n is not None else (texto(v), 'unwind_bad_number')
    return texto(v), None


# ==============================================================================
#  A PLANILHA
# ==============================================================================

def indice_de_colunas(page):
    """{rotulo ou campo normalizado: campo}. O que nao se importa fica fora."""
    idx = {}
    for campo, rotulo, _k in page['columns']:
        if campo in NAO_EDITAVEL:
            continue
        idx.setdefault(norm(rotulo), campo)
        idx.setdefault(norm(campo), campo)
    return idx


def mapear_cabecalho(header, page):
    """({coluna: campo}, [rotulos nao reconhecidos]) de uma linha de cabecalho."""
    idx = indice_de_colunas(page)
    mapa, sobra, usados = {}, [], set()
    for i, h in enumerate(header or []):
        n = norm(h)
        if not n:
            continue
        campo = idx.get(n)
        if campo and campo not in usados:
            mapa[i] = campo
            usados.add(campo)
        else:
            sobra.append(texto(h))
    return mapa, sobra


def linhas_da_planilha(rows, page, max_busca=15):
    """(linhas, avisos) de uma planilha. A linha de cabecalho e a PRIMEIRA, entre
    as `max_busca` do topo, que reconhece ao menos DUAS colunas do catalogo —
    planilha com titulo em cima continua sendo lida.

    Sem cabecalho reconhecivel levanta `Recusa('unwind_sheet_header_unknown')`:
    zero linhas por nao achar coluna nenhuma NAO e "nada para importar"."""
    rows = [list(r or []) for r in (rows or [])]
    kinds = catalog.column_kinds(page)
    hi, mapa, sobra = None, {}, []
    for i, r in enumerate(rows[:max_busca]):
        m, s = mapear_cabecalho(r, page)
        if len(m) >= 2:
            hi, mapa, sobra = i, m, s
            break
    if hi is None:
        raise Recusa('unwind_sheet_header_unknown',
                     'No header row with the columns of this page was found (use the '
                     'column labels or field names of the grid)')
    avisos = []
    if sobra:
        avisos.append(aviso('unwind_sheet_columns_ignored',
                            'Columns not in this page were ignored: ' + ', '.join(sobra),
                            colunas=', '.join(sobra)))
    linhas = []
    for n, r in enumerate(rows[hi + 1:], start=hi + 2):
        if not any(texto(c) for c in r):
            continue
        linha = {}
        for i, campo in mapa.items():
            bruto = r[i] if i < len(r) else None
            val, erro = valor_da_celula(bruto, kinds.get(campo, 'text'))
            if erro:
                avisos.append(aviso(erro, 'Row %d: %s could not be read (%s)' % (n, campo, val),
                                    linha=n, campo=campo, valor=str(val)))
                val = None
            if val is not None and val != '':
                linha[campo] = val
        if linha:
            linha['_sheet_row'] = n
            linhas.append(linha)
    return linhas, avisos


def chave_natural(linha):
    """A tupla da chave natural (`catalog.NATURAL_KEY`), ou None."""
    for campos in catalog.NATURAL_KEY:
        vals = [norm(linha.get(c)) for c in campos]
        if vals[0]:
            return (campos[0],) + tuple(vals)
    return None


# ==============================================================================
#  A POSICAO (Live Position) — ja traduzida pela `queries` para chaves canonicas
# ==============================================================================
# `queries.posicoes()` entrega cada linha do Live Position como um dict com as
# MESMAS chaves para os tres produtos (`contract`, `party_account`,
# `cpty_account`, `counterparty`, `taxid`, `original`, `before`, `strike`,
# `maturity`, `trade_date`, `underlying`, `currency`, `side`, `option_type`,
# `lob`, `our_curve`, `cpty_curve`, `role`, `unit_premium`, `premium_mode`,
# `weighted_asian`, `asian_dates`, `cpty_warning`). A contraparte chega
# RESOLVIDA (guarda-chuva pelo `b3-accounts`, nome pelo Reference Data): isso e
# leitura de cadastro, e o `domain` nao le cadastro.

# campo da linha <- chave da posicao, e o tipo de comparacao da divergencia
_DA_POSICAO = (
    ('Contract', 'contract', 'text'),
    ('Counterparty', 'counterparty', 'name'),
    ('TaxID', 'taxid', 'doc'),
    ('OriginalNotional', 'original', 'num'),
    ('UnwoundBefore', 'before', 'num'),
    ('Strike', 'strike', 'rate'),
    ('TradeDate', 'trade_date', 'text'),
    ('MaturityDate', 'maturity', 'text'),
    ('Underlying', 'underlying', 'name'),
    ('Commodity', 'underlying', 'name'),
    ('Currency', 'currency', 'name'),
    ('OptionType', 'option_type', 'name'),
    ('Side', 'side', 'name'),
    ('LOB', 'lob', 'name'),
    ('OurCurve', 'our_curve', 'name'),
    ('CptyCurve', 'cpty_curve', 'name'),
    ('Role', 'role', 'name'),
    ('UnitPremium', 'unit_premium', 'rate'),
)

# As divergencias que a mesa precisa VER (a planilha vence, mas o valor da
# posicao fica dito): as que mudam o saldo e a contraparte.
_DIVERGENCIA_AVISA = ('Counterparty', 'TaxID', 'OriginalNotional', 'UnwoundBefore',
                      'Strike', 'MaturityDate', 'OptionType', 'Side', 'Role')


def _iguais(a, b, modo):
    if modo in ('num', 'rate'):
        x, y = numero(a, taxa=(modo == 'rate')), numero(b, taxa=(modo == 'rate'))
        if x is None or y is None:
            return False
        tol = TOLERANCIA if modo == 'num' else max(1e-8, abs(y) * 1e-9)
        return abs(x - y) <= tol
    if modo == 'doc':
        return digitos(a).lstrip('0') == digitos(b).lstrip('0')
    return norm(a) == norm(b)


def completar(linha, pos, page):
    """Preenche com a posicao o que a planilha deixou em BRANCO e devolve os
    avisos. O que a planilha TROUXE vence — foi a mesa que digitou —, mas a
    divergencia nas colunas que mudam saldo ou contraparte vira aviso com os dois
    valores. Campos que nao sao coluna da pagina guardam o que o arquivo da B3
    precisa (contas, lado, modalidade, datas da asiatica)."""
    campos = set(catalog.fields(page))
    avisos = []
    for campo, chave, modo in _DA_POSICAO:
        if campo not in campos:
            continue
        pv = pos.get(chave)
        if pv is None or pv == '':
            continue
        atual = linha.get(campo)
        if atual is None or atual == '':
            linha[campo] = pv
        elif campo in _DIVERGENCIA_AVISA and not _iguais(atual, pv, modo):
            avisos.append(aviso('unwind_differs_from_position',
                                '%s differs from the Live Position (sheet %s, position %s)'
                                % (campo, atual, pv), campo=campo, planilha=str(atual),
                                posicao=str(pv)))
    for interno, chave in (('PartyAccount', 'our_account'), ('CptyAccount', 'their_account'),
                           ('RegPartyAccount', 'party_account'),
                           ('RegCptyAccount', 'cpty_account'),
                           ('PremiumMode', 'premium_mode'), ('Comprado', 'comprado'),
                           ('WeightedAsian', 'weighted_asian')):
        if pos.get(chave) not in (None, ''):
            linha[interno] = pos.get(chave)
    if pos.get('asian_dates'):
        linha['VerificationDates'] = list(pos['asian_dates'])
    if pos.get('cpty_warning'):
        avisos.append(pos['cpty_warning'])
    if pos.get('account_warning'):
        avisos.append(pos['account_warning'])
    return avisos


_CRITERIOS = (
    # campo da linha, chave da posicao, modo
    ('TaxID', 'taxid', 'doc'),
    ('Counterparty', 'counterparty', 'name'),
    ('MaturityDate', 'maturity', 'text'),
    ('Strike', 'strike', 'rate'),
    ('OriginalNotional', 'original', 'num'),
    ('Underlying', 'underlying', 'contains'),
    ('Commodity', 'underlying', 'contains'),
    ('OptionType', 'option_type', 'name'),
    ('Currency', 'currency', 'name'),
)
MIN_CRITERIOS = 2


def _casa(valor, pv, modo):
    if pv is None or pv == '':
        return False
    if modo == 'contains':
        a, b = norm(valor), norm(pv)
        return bool(a) and bool(b) and (a in b or b in a)
    if modo == 'name':
        return norm_nome(valor) == norm_nome(pv) if norm_nome(valor) else False
    return _iguais(valor, pv, modo)


def casar_por_caracteristicas(linha, posicoes):
    """(posicao, aviso) da linha que chegou SEM B3 ID.

    Casa por tudo o que a planilha TROUXE entre contraparte, vencimento,
    strike, nocional original, ativo, tipo de opcao e moeda — cada criterio
    presente TEM de bater. So devolve a posicao quando o candidato e UNICO:
    dois candidatos e escolher um e recomprar o contrato errado, calado. Com
    menos de `MIN_CRITERIOS` nao se tenta (duas opcoes do mesmo cliente casam
    so pelo nome)."""
    usados = [(c, k, m) for c, k, m in _CRITERIOS
              if linha.get(c) not in (None, '') and not (c == 'Counterparty' and linha.get('TaxID'))]
    nomes = [c for c, _k, _m in usados]
    if len(usados) < MIN_CRITERIOS:
        return None, aviso('unwind_match_not_enough',
                           'Without a B3 ID the row needs at least %d characteristics to be '
                           'matched against the Live Position (has: %s)'
                           % (MIN_CRITERIOS, ', '.join(nomes) or '-'),
                           minimo=MIN_CRITERIOS, criterios=', '.join(nomes))
    achadas = [p for p in posicoes or []
               if all(_casa(linha.get(c), p.get(k), m) for c, k, m in usados)]
    if len(achadas) == 1:
        return achadas[0], aviso('unwind_matched_by_characteristics',
                                 'B3 ID %s found in the Live Position by %s'
                                 % (achadas[0].get('contract'), ', '.join(nomes)),
                                 contrato=achadas[0].get('contract') or '',
                                 criterios=', '.join(nomes))
    if not achadas:
        return None, aviso('unwind_match_none',
                           'No Live Position contract matches %s' % ', '.join(nomes),
                           criterios=', '.join(nomes))
    return None, aviso('unwind_match_ambiguous',
                       '%d Live Position contracts match %s — fill in the B3 ID'
                       % (len(achadas), ', '.join(nomes)),
                       n=len(achadas), criterios=', '.join(nomes))


def posicao_pelo_contrato(contrato, posicoes):
    """A posicao do B3 ID (sem caixa nem espaco), ou None."""
    alvo = norm(contrato)
    if not alvo:
        return None
    for p in posicoes or []:
        if norm(p.get('contract')) == alvo:
            return p
    return None


# ==============================================================================
#  O VEREDITO (Check) — tres estados
# ==============================================================================

def _balance(linha):
    orig = numero(linha.get('OriginalNotional'))
    antes = numero(linha.get('UnwoundBefore'))
    if antes is None and linha.get('PositionFound'):
        antes = 0.0                 # a posicao existe e nunca foi recomprada
    agora = numero(linha.get('UnwoundNotional'))
    faltam = [n for n, v in (('OriginalNotional', orig), ('UnwoundBefore', antes),
                             ('UnwoundNotional', agora)) if v is None]
    if faltam:
        return None, aviso('unwind_check_missing', 'Missing to check the balance: '
                           + ', '.join(faltam), teste='balance', campos=', '.join(faltam))
    aberto = orig - antes
    if abs(agora) > aberto + TOLERANCIA:
        return False, aviso('unwind_exceeds_balance',
                            'Unwound %.2f exceeds the open balance %.2f' % (abs(agora), aberto),
                            recomprado=round(abs(agora), 2), saldo=round(aberto, 2))
    return True, None


def fx_da_linha(linha, page):
    """A paridade que leva o resultado a reais: 1 com a taxa em reais (a pagina
    nao tem coluna de paridade, ou a moeda e BRL); senao a `FXRate` digitada."""
    if 'FXRate' not in catalog.fields(page):
        return 1.0
    fx = numero(linha.get('FXRate'), taxa=True)
    if fx is not None:
        return fx
    if str(linha.get('Currency') or '').strip().upper() in CCY_REAIS:
        return 1.0
    return None


def resultado_termo(linha, page):
    """O resultado refeito pela formula do termo (a da Fase 1):
    `Qtd x (Termination - Strike) x sinal x FX / (1 + pre)^(DU/252)`, com o
    sinal do LADO da posicao (comprado +1, vendido -1). (valor, faltam)."""
    q = numero(linha.get('UnwoundNotional'))
    k = numero(linha.get('Strike'), taxa=True)
    t = numero(linha.get('TerminationRate'), taxa=True)
    pre = numero(linha.get('PreFWDRate'), taxa=True)
    du = numero(linha.get('DU'))
    fx = fx_da_linha(linha, page)
    lado = linha.get('Comprado')
    faltam = [n for n, v in (('UnwoundNotional', q), ('Strike', k), ('TerminationRate', t),
                             ('PreFWDRate', pre), ('DU', du), ('FXRate', fx),
                             ('Side', lado)) if v is None]
    if faltam:
        return None, faltam
    fv = abs(q) * (t - k) * (1 if lado else -1) * fx
    return fv / ((1.0 + pre / 100.0) ** (du / BASE_DU)), []


def _termo(linha, page):
    res, faltam = resultado_termo(linha, page)
    informado = numero(linha.get('Result'))
    if informado is None:
        faltam = faltam + ['Result']
    if faltam:
        return None, aviso('unwind_check_missing', 'Missing to recompute the result: '
                           + ', '.join(faltam), teste='termo', campos=', '.join(faltam))
    if abs(informado - res) > TOLERANCIA:
        return False, aviso('unwind_result_mismatch',
                            'Result does not match the recomputed value',
                            informado=informado, calculado=round(res, 2))
    return True, None


def _premio(linha):
    q = numero(linha.get('UnwoundNotional'))
    unit = numero(linha.get('UnitPremium'), taxa=True)
    if unit is None:
        unit = numero(linha.get('UnitPrice'), taxa=True)
    informado = numero(linha.get('Result'))
    faltam = [n for n, v in (('UnwoundNotional', q), ('UnitPremium', unit),
                             ('Result', informado)) if v is None]
    if faltam:
        return None, aviso('unwind_check_missing', 'Missing to check the amount: '
                           + ', '.join(faltam), teste='premio', campos=', '.join(faltam))
    calc = abs(q) * unit
    if abs(abs(informado) - calc) > TOLERANCIA:
        return False, aviso('unwind_amount_mismatch',
                            'Settlement amount does not match quantity x unit premium',
                            informado=informado, calculado=round(calc, 2))
    return True, None


def conferir(linha, page):
    """(veredito, avisos). `OK` so quando TODAS as conferencias da pagina
    rodaram e fecharam; uma que nao fecha e `NOK`; uma que nao pode rodar (falta
    numero) e `-` — nunca "passou por omissao"."""
    resultados, avisos = [], []
    for teste in page.get('checks') or ():
        if teste == 'balance':
            r, a = _balance(linha)
        elif teste == 'termo':
            r, a = _termo(linha, page)
        elif teste == 'premio':
            r, a = _premio(linha)
        else:
            r, a = None, aviso('unwind_check_unknown', 'Unknown check ' + teste, teste=teste)
        resultados.append(r)
        if a:
            avisos.append(a)
    if not resultados:
        return CHECK_NA, avisos
    if any(r is False for r in resultados):
        return CHECK_NOK, avisos
    if all(r is True for r in resultados):
        return CHECK_OK, avisos
    return CHECK_NA, avisos


def direcao_do_resultado(linha):
    """RECEIVE/PAY pelo SINAL do resultado (nunca um campo digitado, §488);
    '' sem resultado ou com resultado zero."""
    r = numero(linha.get('Result'))
    if r is None or r == 0:
        return ''
    return 'RECEIVE' if r > 0 else 'PAY'


def codigos(avisos):
    """Os codigos dos avisos, sem repetir, na ordem em que apareceram."""
    vistos, out = set(), []
    for a in avisos or []:
        c = (a or {}).get('code')
        if c and c not in vistos:
            vistos.add(c)
            out.append(c)
    return out


# ==============================================================================
#  O ARQUIVO DA B3
# ==============================================================================
# O ARQUIVO e montado pelo motor do File Interpreter (`_fi_build_line`) a partir
# do template do catalogo (`page['b3']['layout']`). O que mora aqui sao os
# VALORES por seq, ja na largura (posicional) ou no formato (delimitado) — os
# literais dos campos de identificacao (`SWAP`, `0014`, `OPC  00014`...) vao
# pelo gerador porque os dois templates de antecipacao estao como `library`,
# sem nenhum campo `Fixed`: um `Fixed` cadastrado na tela VENCE o gerador.
#
# Cada funcao devolve (blocos, faltas): `blocos` = {bloco: {seq: texto}} e
# `faltas` = [nome do campo] — quem envia RECUSA enquanto houver falta.

def _ymd(iso):
    d = data_iso(iso)
    return d.replace('-', '') if d else ''


def _fmt(valor, formato):
    return fase1.formatar_b3(valor, formato)


def _posicional(layout, valores, obrigatorios, faltas):
    out = {}
    for seq, nome, formato in layout:
        bruto = valores.get(seq)
        txt = _fmt(bruto, formato)
        if txt is None:
            faltas.append('%s %s (%s)' % (seq, nome, bruto))
            txt = ' ' * (fase1.largura(formato) or 0)
        elif (bruto is None or bruto == '') and seq in obrigatorios:
            faltas.append('%s %s' % (seq, nome))
        out[seq] = txt
    return out


def total_ou_parcial(linha):
    """'total', 'parcial' ou None (nao da para dizer): total e o saldo ZERAR."""
    orig = numero(linha.get('OriginalNotional'))
    antes = numero(linha.get('UnwoundBefore'))
    if antes is None and linha.get('PositionFound'):
        antes = 0.0
    agora = numero(linha.get('UnwoundNotional'))
    if None in (orig, antes, agora):
        return None
    return 'total' if (orig - antes - abs(agora)) <= TOLERANCIA else 'parcial'


def papel_swap(v):
    """`Role` -> '00' (Ponta 1) / '01' (Ponta 2), ou None."""
    t = norm(v)
    if t in ('00', '0', 'ponta1', 'p1', '1', 'leg1'):
        return '00'
    if t in ('01', 'ponta2', 'p2', '2', 'leg2'):
        return '01'
    return None


def _sim_nao(v):
    """`Keep Premium` -> '00' (sim) / '01' (nao) — a ordem do manual."""
    t = norm(v)
    if t in ('sim', 's', 'yes', 'y', '00', '0', 'true'):
        return '00'
    if t in ('nao', 'n', 'no', '01', '1', 'false'):
        return '01'
    return None


SWAP_HEADER = (
    ('1', 'ID do Sistema', 'X(05)'), ('2', 'ID Tipo de Linha', '9(01)'),
    ('3', 'Código da Operação', '9(04)'), ('4', 'Participante', 'X(20)'),
    ('5', 'Data', '9(08)'), ('6', 'Versão do Layout', '9(05)'), ('7', 'Filler', 'X(60)'),
)
SWAP_REGISTRO = (
    ('1', 'ID do Sistema', 'X(05)'), ('2', 'ID Tipo de Linha', '9(01)'),
    ('3', 'Código operação', '9(04)'), ('4', 'Código do Contrato', 'X(11)'),
    ('5', 'Papel', '9(02)'), ('6', 'Meu Número', '9(10)'),
    ('7', 'Fator para Antecipação (Ponta1)', '9(10)V9(08)'),
    ('8', 'Fator para Antecipação (Ponta2)', '9(10)V9(08)'),
    ('9', 'Data Antecipação', '9(08)'), ('10', 'Banco Liquidante', '9(08)'),
    ('11', 'Valor Para Antecipação', '9(14)V9(02)'), ('12', 'Mantém Prêmios', '9(02)'),
    ('13', 'Data de Liquidação', '9(08)'),
)


def campos_swap_0014(linha, participante, hoje_ymd):
    """SWAP 0014 (`swap-antecipacao`, §4.2.10). O valor para antecipacao OU os
    dois fatores; `Mantem Premios` so na antecipacao PARCIAL (o manual: "nao deve
    ser preenchido em caso de antecipacao total")."""
    faltas = []
    papel = papel_swap(linha.get('Role'))
    if papel is None:
        faltas.append('5 Papel (Role: %s)' % (linha.get('Role') or '-'))
    f1 = numero(linha.get('FactorLeg1'), taxa=True)
    f2 = numero(linha.get('FactorLeg2'), taxa=True)
    valor = numero(linha.get('Result'))
    if valor is None and (f1 is None or f2 is None):
        faltas.append('11 Valor Para Antecipação (or 7/8 factors)')
    mantem = None
    tp = total_ou_parcial(linha)
    if tp is None:
        faltas.append('12 Mantém Prêmios (total or partial? OriginalNotional/UnwoundBefore/'
                      'UnwoundNotional)')
    elif tp == 'parcial':
        mantem = _sim_nao(linha.get('KeepPremium'))
        if mantem is None:
            faltas.append('12 Mantém Prêmios (Keep Premium is required on a partial unwind)')
    antecip = _ymd(linha.get('UnwindDate')) or hoje_ymd
    reg = _posicional(SWAP_REGISTRO, {
        '1': 'SWAP', '2': '1', '3': '0014', '4': linha.get('Contract'), '5': papel,
        '6': linha.get('MyNumber'), '7': f1, '8': f2, '9': antecip, '10': '',
        '11': None if valor is None else abs(valor), '12': mantem,
        '13': _ymd(linha.get('SettlementDate')) or '',
    }, ('4', '6', '9'), faltas)
    hdr = _posicional(SWAP_HEADER, {'1': 'SWAP', '2': '0', '3': '0014', '4': participante,
                                    '5': hoje_ymd, '6': '00001', '7': ''}, ('4',), faltas)
    return {'header': hdr, 'registro': reg}, faltas


def _opc_num(valor, casas):
    """Numero do OPC delimitado: virgula decimal obrigatoria, sem milhar, sem
    sinal (nenhum campo do 0014 e assinado)."""
    if valor is None:
        return ''
    from decimal import Decimal, ROUND_HALF_UP
    d = abs(Decimal(repr(float(valor)))).quantize(Decimal(1).scaleb(-casas),
                                                   rounding=ROUND_HALF_UP)
    return format(d, 'f').replace('.', ',')


def pagador_premio(v):
    """`Premium Payer` -> '1' (Titular) / '2' (Lancador), ou None."""
    t = norm(v)
    if t in ('1', 'titular', 'holder', 'buyer', 'comprador'):
        return '1'
    if t in ('2', 'lancador', 'writer', 'seller', 'vendedor'):
        return '2'
    return None


def modalidade(v, com_premio):
    """`Modalidade de liquidacao do premio` da posicao -> 1/2/3. Sem premio e
    sem resposta, 1 (Sem Modalidade); com premio, sem resposta e falta."""
    t = norm(v)
    if t in ('1', '2', '3'):
        return t
    if 'bilateral' in t:
        return '3'
    if 'bruta' in t:
        return '2'
    if 'sem' in t:
        return '1'
    return None if com_premio else '1'


def campos_opc_0014(linha, participante, hoje_ymd):
    """OPC 0014 (`antecipacao-opcao`, §5.3.2) — DELIMITADO por `;`. As contas
    4/5 sao as do REGISTRO (Parte/Contraparte da posicao), nao "nos x eles".
    Media asiatica PONDERADA pede as linhas tipo 2 com a quantidade por data, que
    a planilha nao traz: recusa em vez de mandar a contagem sem as linhas."""
    faltas = []
    q = numero(linha.get('UnwoundNotional'))
    base = numero(linha.get('UnwoundBase'))
    unit = numero(linha.get('UnitPremium'), taxa=True)
    valor = numero(linha.get('Result'))
    pagador = pagador_premio(linha.get('PremiumPayer'))
    com_premio = unit is not None
    if com_premio and pagador is None:
        faltas.append('14 Pagador do Prêmio (Premium Payer: %s)' % (linha.get('PremiumPayer') or '-'))
    if com_premio and valor is None:
        faltas.append('10 Valor Financeiro da Antecipação')
    mod = modalidade(linha.get('PremiumMode'), com_premio)
    if mod is None:
        faltas.append('12 Modalidade (%s)' % (linha.get('PremiumMode') or '-'))
    if linha.get('WeightedAsian'):
        faltas.append('15 weighted Asian average: the type-2 lines (quantity per date) '
                      'are not supported yet')
    parte = fase1.conta8(linha.get('RegPartyAccount') or linha.get('PartyAccount'))
    cpty = fase1.conta8(linha.get('RegCptyAccount') or linha.get('CptyAccount'))
    vals = {
        '1': 'OPC  00014', '2': '1', '3': str(linha.get('Contract') or '').strip(),
        '4': parte, '5': cpty, '6': str(linha.get('MyNumber') or ''),
        '7': _opc_num(q, 8), '8': _opc_num(base, 8), '9': _opc_num(unit, 8),
        '10': _opc_num(valor, 2), '11': '', '12': mod or '',
        '13': _ymd(linha.get('UnwindDate')) or hoje_ymd,
        '14': (pagador or '') if com_premio else '', '15': '0',
    }
    for seq, nome in (('3', 'Código do Contrato'), ('4', 'Parte (Conta)'),
                      ('5', 'Contraparte (Conta)'), ('6', 'Meu número'),
                      ('7', 'Quantidade a antecipar')):
        if not vals[seq]:
            faltas.append('%s %s' % (seq, nome))
    hdr = {'1': 'OPC  00014', '2': '0', '3': participante or '', '4': hoje_ymd, '5': '00001'}
    if not participante:
        faltas.append('header 3 Entidade que gerou o Arquivo')
    return {'header': hdr, 'registro': vals}, faltas


def campos_ter_0014(linha, participante, hoje_ymd):
    """TER 0014 (`antecipacao-termo-multiclasses`) do termo de MERCADORIA: os
    MESMOS nomes e formatos da Fase 1 (`fase1.valores_ter_0014`), com a
    quantidade no campo 9 e a paridade no 14 (a taxa termo e na moeda cotada).
    Asiatico pede as linhas tipo 2 com as datas de verificacao — recusa."""
    faltas = []
    comprado = linha.get('Comprado')
    papel = None if comprado is None else (fase1.PAPEL_COMPRADO if comprado else fase1.PAPEL_VENDIDO)
    antecip = _ymd(linha.get('UnwindDate')) or hoje_ymd
    campos = {
        'Nº Controle Interno': str(linha.get('MyNumber') or '') or None,
        'Lançamento do Participante (Conta)': fase1.conta8(linha.get('PartyAccount')) or None,
        'Papel (Posição do participante)': papel,
        'Contraparte': fase1.conta8(linha.get('CptyAccount')) or None,
        'Contrato': str(linha.get('Contract') or '').strip() or None,
        'Valor Base a Antecipar': (None if numero(linha.get('UnwoundNotional')) is None
                                   else abs(numero(linha.get('UnwoundNotional')))),
        'Data Antecipação': antecip,
        'Data Liquidação': _ymd(linha.get('SettlementDate')) or antecip,
        'Taxa Termo': numero(linha.get('TerminationRate'), taxa=True),
        'Taxa Juros': numero(linha.get('PreFWDRate'), taxa=True),
        'Taxa de Câmbio (R$/Moeda Cotada)': None,
        'Liquidante': '',
        'Quantidade de Datas de Verificação': '000',
    }
    fx = numero(linha.get('FXRate'), taxa=True)
    if fx is None and str(linha.get('Currency') or '').strip().upper() in CCY_REAIS:
        fx = 1.0
    campos['Taxa de Câmbio (R$/Moeda Cotada)'] = fx
    if linha.get('VerificationDates'):
        faltas.append('16 Asian contract: the type-2 lines (verification dates) are not '
                      'supported yet')
    valores, av = fase1.valores_ter_0014(campos)
    faltas.extend('%s %s' % (a['params'].get('seq', ''), a['params'].get('campo', ''))
                  for a in av)
    if not participante:
        faltas.append('header 4 Participante')
    return {'header': {'4': participante or '', '5': hoje_ymd},
            'registro-dados-fixos': valores}, faltas


# layout -> (funcao, bloco do registro)
GERADORES = {
    'swap-antecipacao': (campos_swap_0014, 'registro'),
    'antecipacao-opcao': (campos_opc_0014, 'registro'),
    'antecipacao-termo-multiclasses': (campos_ter_0014, 'registro-dados-fixos'),
}


def nome_do_arquivo(page, visao):
    """`UNWIND_<PRODUTO>_<VISAO>.txt` — o produto no nome porque o Batch Conecta
    e UMA pasta para todos, e o `UNWIND_BANCO.txt` e o da Fase 1."""
    prod = re.sub(r'[^A-Z0-9]+', '_', page['dir'].upper()).strip('_')
    vis = {'JPM': 'BANCO'}.get(str(visao or '').upper(), str(visao or '').upper() or 'BANCO')
    return 'UNWIND_%s_%s.txt' % (prod, vis)
