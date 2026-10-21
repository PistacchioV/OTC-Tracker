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
STATUS_SUCESSO = fase1.STATUS_SUCESSO
STATUS_REGISTRADO = fase1.STATUS_REGISTRADO
CHECK_OK, CHECK_NOK, CHECK_NA = fase1.CHECK_OK, fase1.CHECK_NOK, fase1.CHECK_NA

# O que NAO vem da planilha nem se edita na grade: a chave, os dois veredictos
# (estado da esteira e conferencia apurada) e o rastro. Coluna de planilha com
# um desses rotulos e IGNORADA — um `Status = Sent` colado de outra aba nao pode
# pular o 4-olhos.
NAO_EDITAVEL = ('_id', 'Status', 'Check', 'CalcResult', 'Maker', 'Checker', 'MyNumber', 'SentFiles',
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
    # `21/09/26` e `21-Sep-26` sao como o Excel cola a data num e-mail (a
    # celula vai como TEXTO, no formato de exibicao dela).
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%Y%m%d', '%d-%m-%Y', '%d.%m.%Y', '%d/%m/%y',
                '%d-%b-%y', '%d-%b-%Y'):
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
    if kind in ('money', 'rate', 'qty'):
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


# ==============================================================================
#  O E-MAIL DE RECOMPRA DE NDF DE COMMODITIES (mesa, 28/09/2026)
# ==============================================================================
# A mesa fecha a recompra num e-mail com UMA tabela por perna, cada uma com o
# cabecalho `Leg · Trade Date · Fixing · … · Unwind Strike · FV USD · FX Rate ·
# PV BRL · Direction · Unwind`. Entram so as pernas `Client` e `Banco` — a
# `JPMOCC` e offshore, nao tem contrato na B3. O `Risk Deal ID` NAO entra em
# perna nenhuma (pedido da mesa): quem identifica o contrato e o Live Position.
# O Pre FWD Rate e ZERO (a liquidacao e em T+0, nao ha desconto).
#
# **A grade mostra o numero do E-MAIL, como veio** (mesa, 28/09/2026): o
# e-mail traz o que o Excel EXIBE (`96.85` na celula que vale 96,84626,
# `5.2087` na que vale 5,20867), e e esse o numero que a mesa confere na tela.
# Refazer a precisao pelo FV USD e pelo PV BRL punha na grade um strike e uma
# paridade que o e-mail nao tem. Quando a conta com os numeros mostrados nao
# fecha com o PV BRL, o Check da NOK e a coluna `CalcResult` diz o resultado
# que o OTC Tracker calculou — a divergencia fica a vista, nunca escondida.

_RECAP_COLS = {
    'leg': 'leg', 'tradedate': 'TradeDate', 'originalposition': 'posicao',
    'originalvolume': 'OriginalNotional', 'originalstrike': 'Strike',
    'unwindvolume': 'UnwoundNotional', 'unwindstrike': 'TerminationRate',
    'fvusd': 'fv', 'fxrate': 'FXRate', 'pvbrl': 'pv', 'direction': 'direcao',
}
_RECAP_PERNAS = ('client', 'banco')


def _rotulo_recap(h):
    return norm(re.sub(r'\(.*?\)', '', str(h or '')))


def _casas(t):
    t = texto(t).replace(' ', '')
    i = max(t.rfind('.'), t.rfind(','))
    return len(t) - i - 1 if i >= 0 else 0


def _banco_comprou(posicao):
    """`Client Sells` -> o banco COMPROU; `BJPM Sells` -> o banco VENDEU.
    None quando o texto nao diz quem e o lado."""
    p = norm_nome(posicao).split()
    if len(p) < 2 or p[-1] not in ('SELLS', 'BUYS', 'SELL', 'BUY'):
        return None
    compra = p[-1].startswith('BUY')
    return (not compra) if p[0] == 'CLIENT' else compra


def linhas_do_recap_commodities(tabelas):
    """(linhas, avisos) do e-mail de recompra de NDF de Commodities, ou None
    quando nenhuma tabela tem o cabecalho dele (`Leg` + `Unwind Strike`)."""
    linhas, avisos, achou = [], [], False
    for t in tabelas or []:
        # O trecho colado do Excel costuma ser UMA tabela com um cabecalho
        # `Leg ...` por perna — e as pernas NAO tem as mesmas colunas (a do
        # Client tem o `Risk Deal ID`, a do Banco nao). Toda linha que abre com
        # `Leg` e um cabecalho NOVO e vale para as linhas de baixo; lendo so o
        # primeiro, a perna Banco saia com as colunas deslocadas uma casa.
        mapa = None
        for n, r in enumerate(t or [], start=1):
            cab = [_rotulo_recap(h) for h in r]
            if cab and cab[0] == 'leg':
                if 'unwindstrike' in cab:
                    achou = True
                    mapa = {i: _RECAP_COLS[c] for i, c in enumerate(cab) if c in _RECAP_COLS}
                else:
                    mapa = None
                continue
            if mapa is None:
                continue
            cel = {k: (r[i] if i < len(r) else '') for i, k in mapa.items()}
            perna = norm(cel.get('leg'))
            if perna not in _RECAP_PERNAS:
                continue
            q = numero(cel.get('UnwoundNotional'))
            k = numero(cel.get('Strike'), taxa=True)
            tt = numero(cel.get('TerminationRate'), taxa=True)
            fx = numero(cel.get('FXRate'), taxa=True)
            pv = numero(cel.get('pv'))
            linha = {'PreFWDRate': 0.0, '_sheet_row': n}
            d = data_iso(cel.get('TradeDate'))
            if d:
                linha['TradeDate'] = d
            for campo, v in (('OriginalNotional', numero(cel.get('OriginalNotional'))),
                             ('Strike', k), ('UnwoundNotional', q)):
                if v is not None:
                    linha[campo] = v
            # As casas que a celula MOSTRA: o Excel arredonda o strike e o
            # volume da perna Banco, e o casamento com o Live Position tem de
            # aceitar o valor que arredonda para o mostrado (`_mostrado`).
            linha['_shown'] = {c: _casas(cel.get(c)) for c in ('Strike', 'OriginalNotional')
                               if texto(cel.get(c))}
            if tt is not None:
                linha['TerminationRate'] = tt
            if fx is not None:
                linha['FXRate'] = fx
            comprou = _banco_comprou(cel.get('posicao'))
            if comprou is not None:
                linha['Comprado'] = comprou
            # O PV vem em modulo; o sinal e o do BANCO (a regra do Check:
            # comprado ganha quando a Termination passa do Strike).
            if pv is not None:
                sinal = None
                if comprou is not None and tt is not None and k is not None and tt != k:
                    sinal = 1 if (tt > k) == comprou else -1
                dtxt = norm_nome(cel.get('direcao'))
                pelo_texto = None
                if dtxt.startswith('CLIENT '):
                    pelo_texto = -1 if 'RECEIVE' in dtxt else (1 if 'PAY' in dtxt else None)
                if sinal is None:
                    sinal = pelo_texto
                elif pelo_texto is not None and pelo_texto != sinal:
                    avisos.append(aviso('unwind_recap_direction_differs',
                                        'Row %d: the Direction of the e-mail (%s) does not match '
                                        'the position and the strikes' % (n, texto(cel.get('direcao'))),
                                        linha=n, direcao=texto(cel.get('direcao'))))
                if sinal is None:
                    avisos.append(aviso('unwind_recap_no_sign',
                                        'Row %d: could not tell whether the bank pays or receives'
                                        % n, linha=n))
                else:
                    linha['Result'] = round(abs(pv) * sinal, 2)
            linhas.append(linha)
    if not achou:
        return None
    return linhas, avisos


# ── O e-mail de recompra de OPCAO de Commodities (mesa, 20/10/2026) ──────────
# O "INTERNAL JPMorgan Trade Recap - <estrutura> Unwind": uma tabela por perna,
# `Leg · Client · Original B/S · Direction of Unwind · Commodity · Option Type ·
# Contract · Original Strike · Unwind Strike · Fixing Date · Original Volume
# (lots) · Unwind Volume (lots) · Unwind Volume (<unidade>) · Settlement Date ·
# Premium (USD/<unidade>) · Total Premium USD · FX BRL/USD · Total Premium BRL ·
# Premium Payment Date`. O e-mail NAO traz o B3 ID: o `Contract` dele (`27-Mar`)
# e o vencimento do FUTURO, e lido como B3 ID enchia a grade de lixo — quem acha
# o contrato e o Live Position, pelas caracteristicas (o padrao do NDF).
#
#   * `Client` e a perna FACING o cliente; `Banco` e o B2B Banco x Lawton. Cada
#     uma so casa com o SEU tipo de contrato (`_leg`): a mesma opcao existe nas
#     duas, com strike e volume iguais, e sem isso as duas seriam "ambiguas";
#   * a QUANTIDADE e na unidade da mercadoria (a da B3, o nocional total do New
#     Deals): `Unwind Volume (<unidade>)`, e a original pela mesma razao
#     unidade/lote (48 lotes x 3.472.000/31);
#   * o SINAL e o do banco: na perna Client, `Client Sells` = o banco recompra e
#     PAGA; na perna Banco o B2B anda ao contrario (o banco desfaz com o fundo o
#     que desfez com o cliente). O valor e o `Total Premium BRL`;
#   * quem paga para fechar e sempre o LANCADOR (a opcao comprada vale; quem a
#     vendeu devolve o valor) — e o `Premium Payer` do OPC 0014;
#   * os numeros ficam os do E-MAIL (premio em USD por unidade, a paridade na
#     coluna FX Rate), como no NDF (§570).
_RECAP_OPC_PERNAS = ('client', 'banco')


def _rotulo_recap_opc(h):
    """O rotulo com a UNIDADE: as duas `Unwind Volume` so se separam por ela."""
    t = norm(h)
    if t.startswith('unwindvolume'):
        return 'unwindlots' if 'lot' in t else 'unwindunits'
    if t.startswith('originalvolume'):
        return 'originallots' if 'lot' in t else 'originalunits'
    return _rotulo_recap(h)


def linhas_do_recap_opcoes_commodities(tabelas):
    """(linhas, avisos) do e-mail de recompra de opcao de Commodities, ou None
    quando nenhuma tabela tem o cabecalho dele (`Leg` + `Option Type`)."""
    linhas, avisos, achou = [], [], False
    for t in tabelas or []:
        mapa = None
        for n, r in enumerate(t or [], start=1):
            cab = [_rotulo_recap_opc(h) for h in r]
            if cab and cab[0] == 'leg':
                # cada `Leg ...` e um cabecalho NOVO (as pernas coladas numa
                # tabela so), como no NDF
                if 'optiontype' in cab:
                    achou = True
                    mapa = dict((c, i) for i, c in reversed(list(enumerate(cab))))
                else:
                    mapa = None
                continue
            if mapa is None:
                continue
            cel = lambda k: (r[mapa[k]] if k in mapa and mapa[k] < len(r) else '')   # noqa: E731
            perna = norm(cel('leg'))
            if perna not in _RECAP_OPC_PERNAS:
                continue
            linha = {'_sheet_row': n, '_leg': perna, '_client': texto(cel('client')),
                     '_dates': [d for d in (data_iso(cel('fixingdate')),
                                            data_iso(cel('settlementdate'))) if d]}
            tipo = norm(cel('optiontype'))
            if tipo in ('call', 'put'):
                linha['OptionType'] = tipo.capitalize()
            k = numero(cel('originalstrike'), taxa=True)
            if k is not None:
                linha['Strike'] = k
            lotes_o, lotes_u = numero(cel('originallots')), numero(cel('unwindlots'))
            unid_u = numero(cel('unwindunits'))
            if unid_u is not None:
                linha['UnwoundNotional'] = unid_u
            unid_o = numero(cel('originalunits'))
            if unid_o is None and lotes_o is not None and lotes_u and unid_u is not None:
                unid_o = round(lotes_o * unid_u / lotes_u, 6)
            if unid_o is not None:
                linha['OriginalNotional'] = unid_o
            premio = numero(cel('premium'), taxa=True)
            if premio is not None:
                linha['UnitPremium'] = premio
            fx = numero(cel('fxbrlusd'), taxa=True)
            if fx is not None:
                linha['FXRate'] = fx
            pago = data_iso(cel('premiumpaymentdate'))
            if pago:
                linha['SettlementDate'] = pago
            total = numero(cel('totalpremiumbrl'))
            if total is None:
                usd = numero(cel('totalpremiumusd'))
                total = usd * fx if (usd is not None and fx is not None) else None
            dire = norm_nome(cel('directionofunwind')).split()
            sinal = None
            if len(dire) >= 2 and dire[0] == 'CLIENT':
                sinal = -1 if dire[-1].startswith('SELL') else (1 if dire[-1].startswith('BUY') else None)
                if sinal is not None and perna == 'banco':
                    sinal = -sinal
            if total is not None:
                if sinal is None:
                    avisos.append(aviso('unwind_recap_no_sign',
                                        'Row %d: could not tell whether the bank pays or receives'
                                        % n, linha=n))
                else:
                    linha['Result'] = round(abs(total) * sinal, 2)
            if premio:
                linha['PremiumPayer'] = 'Lançador'
            linhas.append(linha)
    if not achou:
        return None
    return linhas, avisos


# ── O e-mail de recompra de SWAP da EDG: o TRS onshore (mesa, 21/10/2026) ────
# O "Internal Recap - <ticker> TRS onshore Unwind (20-Oct-26)" (§657) e UMA
# tabela TRANSPOSTA: os rotulos na primeira coluna e uma TRANCHE por coluna
# (`#1`…`#n`; o `TOTAL` nao e operacao):
#
#   Unwind Parcial/Total · Data de execução original · Deal ID · Instrumento ID ·
#   CETIP ID · Número de ações · Strike Original · Preço de Unwind ·
#   (A) Perna Equity (RDOR Recebe) ajustado para 1 dia de DI ·
#   (B) Perna Funding (RDOR Paga DI + 0.50%) ajustado para 1 dia de DI ·
#   (A + B) Valor Total de Liquidação (RDOR Recebe em D+1)
#
#   * o CETIP ID e o B3 ID — o contrato se acha no Live Position por ele;
#   * o NOCIONAL recomprado e acoes x strike original (o campo 11 do SWAP 0014);
#   * as pernas vem na visao de QUEM o rotulo nomeia ("RDOR Recebe": o valor e
#     o que o cliente ganha nela). A perna que ele RECEBE e a curva DELE, a que
#     ele PAGA e a NOSSA; o valor de liquidacao de cada perna vai com o sinal de
#     quem a recebe, e o FATOR e valor / VBR + 1, na 8a casa (mesa, 21/10/2026,
#     §660 — o VBR e o Valor Base Remanescente do Live Position, a mesma regra do
#     fator do Swap VCP); com os dois, VBR x (fator nosso − fator deles) = o
#     (A + B) do banco. Sem a posicao nao ha VBR, e sem VBR nao ha fator;
#   * o (A + B) e o CAIXA, e o `Result` leva o sinal do BANCO (o cliente recebe
#     = o banco paga = negativo); o "D+n" do rotulo da a liquidacao;
#   * a data da recompra e a do ASSUNTO ("(20-Oct-26)");
#   * a parcial NAO mantem os premios (a planilha da mesa: `IF(TOTAL;"  ";"01")`).

_TRS_ROTULOS = (
    # (prefixo do rotulo normalizado, chave)
    ('unwindparcialtotal', 'tipo'), ('unwindtotalparcial', 'tipo'),
    ('datadeexecucaooriginal', 'trade'), ('originaltradedate', 'trade'),
    ('dealid', 'deal'), ('instrumentoid', 'instr'), ('instrumentid', 'instr'),
    ('cetipid', 'cetip'), ('b3id', 'cetip'),
    ('numerodeacoes', 'acoes'), ('quantidadedeacoes', 'acoes'), ('numberofshares', 'acoes'),
    ('strikeoriginal', 'strike'), ('originalstrike', 'strike'),
    ('precodeunwind', 'preco'), ('unwindprice', 'preco'),
)
_BANCO_RE = re.compile(r'\b(JPM|JPMC|JPMORGAN|J P MORGAN|BANCO|BANK)\b')
_VERBO_RE = re.compile(r'^(.*?)\b(RECEBE|RECEIVES|RECEIVE|PAGA|PAYS|PAY)\b')
_ASSUNTO_DATA_RE = re.compile(r'\((\d{1,2}-[A-Za-z]{3}-\d{2,4})\)')
_PERNA_RE = re.compile(r'^\(\s*([AB])\s*\)')
_TOTAL_RE = re.compile(r'^\(\s*A\s*\+\s*B\s*\)', re.I)


def _quem_e_verbo(rotulo):
    """('cliente'|'banco', 'recebe'|'paga') do parentese do rotulo — "(RDOR
    Recebe)", "(RDOR Paga DI + 0.50%)", "(JPM Receives)" —, ou None."""
    for trecho in re.findall(r'\(([^()]*)\)', str(rotulo or '')):
        m = _VERBO_RE.match(norm_nome(trecho))
        if m and m.group(1).strip():
            quem = 'banco' if _BANCO_RE.search(m.group(1)) else 'cliente'
            return quem, ('recebe' if m.group(2).startswith('RECE') else 'paga')
    return None


def _outro(quem):
    return 'banco' if quem == 'cliente' else 'cliente'


def linhas_do_recap_swap_trs(tabelas, assunto=''):
    """(linhas, avisos) do recap de recompra do TRS da EDG, ou None quando
    nenhuma tabela tem as linhas dele (`CETIP ID` + `Número de ações`)."""
    dia = None
    m = _ASSUNTO_DATA_RE.search(str(assunto or ''))
    if m:
        dia = data_iso(m.group(1))
    for t in tabelas or []:
        rot = [(texto(r[0]) if r else '') for r in t or []]
        chaves = {}
        pernas, total = {}, None
        for i, r0 in enumerate(rot):
            n = norm(r0)
            if not n:
                continue
            if _TOTAL_RE.match(r0) or n.startswith('abvalortotal') or 'valortotaldeliquidacao' in n:
                total = i
                continue
            mp = _PERNA_RE.match(r0)
            if mp:
                campo = ('EquityLeg' if 'equity' in n else 'FundingLeg' if 'funding' in n
                         else ('EquityLeg' if mp.group(1).upper() == 'A' else 'FundingLeg'))
                pernas[campo] = i
                continue
            for pref, k in _TRS_ROTULOS:
                if n.startswith(pref) and k not in chaves:
                    chaves[k] = i
                    break
        if 'cetip' not in chaves or 'acoes' not in chaves:
            continue
        cab = next((r for r in t if r and norm(r[0]) == 'tranche'), t[0])
        largura = max(len(r) for r in t)
        avisos, linhas = [], []
        lados = {}
        visoes = set()
        for campo, i in pernas.items():
            qv = _quem_e_verbo(rot[i])
            if qv is not None:
                visoes.add(qv[0])
                lados[campo] = qv[0] if qv[1] == 'recebe' else _outro(qv[0])
        visao = visoes.pop() if len(visoes) == 1 else None
        if visao:
            lados['visao'] = visao
        qv_total = _quem_e_verbo(rot[total]) if total is not None else None
        d_mais = re.search(r'D\s*\+\s*(\d+)', rot[total], re.I) if total is not None else None

        def cel(r, j):
            row = t[r] if r is not None and r < len(t) else []
            return row[j] if j < len(row) else ''

        for j in range(1, largura):
            nome = texto(cel(t.index(cab), j)) if cab in t else ''
            if norm(nome) == 'total':
                continue
            contrato = texto(cel(chaves['cetip'], j))
            if not contrato and not texto(cel(chaves['acoes'], j)):
                continue
            num = re.sub(r'\D', '', nome) or str(j)
            linha = {'_sheet_row': int(num)}
            if not contrato:
                avisos.append(aviso('unwind_recap_no_cetip',
                                    'Tranche %s: the e-mail has no CETIP ID' % (nome or j),
                                    linha=int(num)))
                continue
            linha['Contract'] = contrato
            for k, campo in (('deal', 'DealID'), ('instr', 'InstrumentID')):
                v = texto(cel(chaves.get(k), j)) if k in chaves else ''
                if v:
                    linha[campo] = v
            tipo = tipo_informado(cel(chaves.get('tipo'), j)) if 'tipo' in chaves else None
            if tipo:
                linha['UnwindType'] = 'Total' if tipo == 'total' else 'Partial'
                if tipo == 'parcial':
                    linha['KeepPremium'] = 'Não'
            d = data_iso(cel(chaves.get('trade'), j)) if 'trade' in chaves else None
            if d:
                linha['TradeDate'] = d
            if dia:
                linha['UnwindDate'] = dia
            for k, campo, taxa in (('acoes', 'Shares', False), ('strike', 'Strike', True),
                                   ('preco', 'UnwindPrice', True)):
                v = numero(cel(chaves.get(k), j), taxa=taxa) if k in chaves else None
                if v is not None:
                    linha[campo] = v
            for campo, i in pernas.items():
                v = numero(cel(i, j))
                if v is not None:
                    linha[campo] = v
            if lados:
                linha['LegSides'] = dict(lados)
            mudou = set()
            tv = numero(cel(total, j)) if total is not None else None
            if tv is not None and qv_total is not None:
                quem, verbo = qv_total
                recebe = tv if verbo == 'recebe' else -tv
                linha['Result'] = round(recebe if quem == 'banco' else -recebe, 2)
                mudou.add('Result')
            if d_mais:
                linha['_d_mais'] = int(d_mais.group(1))
            recalcular_swap(linha, mudou)
            if not lados.get('visao') or 'Result' not in linha:
                avisos.append(aviso('unwind_recap_no_sign',
                                    'Tranche %s: could not tell whether the bank pays or receives'
                                    % num, linha=int(num)))
            linhas.append(linha)
        return linhas, avisos
    return None


def recalcular_swap(linha, mudou=()):
    """O nocional, os fatores e o caixa do swap a partir do que a linha TEM
    (§657) — no import do recap (com a posicao, que da o VBR) e no Edit que
    muda acoes, strike, pernas, VBR ou papel. O que a pessoa digitou no MESMO
    Save vence (`mudou`): nocional, Result e fatores editados a mao ficam, e o
    Check confere.

      nocional = acoes x strike original (o campo 11 do SWAP 0014);
      fator de cada leg = round(valor de liquidacao / VBR + 1, 8) (mesa,
        21/10/2026, §660): o valor vai com o sinal de quem RECEBE a curva
        (`LegSides`) e o VBR e o Valor Base Remanescente do Live Position —
        sem VBR nao ha fator;
      Result (o banco) = a soma das pernas na visao do banco;
      Factor Leg 1/2 = o fator da Ponta 1 e o da Ponta 2, pelo papel.

    O nocional e o caixa so se refazem VAZIOS ou quando o que os forma mudou
    (acoes/strike; as pernas): o Edit so do papel nao troca o (A + B) do
    e-mail pela soma das pernas, que difere dele no centavo. Muta e devolve a
    linha."""
    mudou = set(mudou or ())

    def _vazio(c):
        return linha.get(c) in (None, '')

    q, k = numero(linha.get('Shares')), numero(linha.get('Strike'), taxa=True)
    if q is not None and k is not None and 'UnwoundNotional' not in mudou and \
            (_vazio('UnwoundNotional') or mudou & {'Shares', 'Strike'}):
        linha['UnwoundNotional'] = round(abs(q) * k, 2)
    vbr = numero(linha.get('VBR'))
    lados = linha.get('LegSides') or {}
    visao = lados.get('visao')
    fatores, valores = {}, []
    if visao in ('cliente', 'banco'):
        for campo in ('EquityLeg', 'FundingLeg'):
            v, quem = numero(linha.get(campo)), lados.get(campo)
            if v is None or quem not in ('cliente', 'banco'):
                continue
            valores.append(v)
            if vbr:
                liquidacao = v if quem == visao else -v
                fatores[quem] = round(liquidacao / abs(vbr) + 1.0, 8)
    if 'banco' in fatores and 'cliente' in fatores:
        linha['FactorOurs'], linha['FactorTheirs'] = fatores['banco'], fatores['cliente']
    if len(valores) == 2 and 'Result' not in mudou and \
            (_vazio('Result') or mudou & {'EquityLeg', 'FundingLeg'}):
        soma = valores[0] + valores[1]
        linha['Result'] = round(soma if visao == 'banco' else -soma, 2)
    papel = papel_swap(linha.get('Role'))
    nosso = numero(linha.get('FactorOurs'), taxa=True)
    deles = numero(linha.get('FactorTheirs'), taxa=True)
    if papel and nosso is not None and deles is not None and not (mudou & {'FactorLeg1', 'FactorLeg2'}):
        linha['FactorLeg1'], linha['FactorLeg2'] = (nosso, deles) if papel == '00' else (deles, nosso)
    return linha


# O leitor de e-mail PROPRIO de cada pagina (`catalog` -> `recap`): recebe as
# tabelas e o assunto.
LEITORES_RECAP = {'swap-trs': linhas_do_recap_swap_trs}


# As recompras do catálogo que têm esteira e Termo de Resilição (mesa,
# 28/09/2026): pasta da página -> o source da esteira (o Product Type do
# Pending Confirmation).
PAGINAS_COM_TERMO = {'NDF/Commodities': 'UNWIND NDF COMM'}


def chave_da_esteira(linha):
    """A chave da recompra na esteira e no Pending Confirmation: o Deal ID (o
    `Codigo Identificador` do Live Position); sem ele, o `_id` interno —
    estável entre reimports, porque o upsert o preserva."""
    return (texto((linha or {}).get('DealID'))
            or texto((linha or {}).get(catalog.KEY_FIELD)))


def para_o_termo(page, linha):
    """A linha no formato que a Fase 1 lê (Termo, esteira): o `AthenaID` é a
    chave da esteira e a "moeda" do agrupamento é a MERCADORIA — o eixo
    contraparte × ativo das confirmações de NDF de Commodities (§457)."""
    l = dict(linha or {})
    l.update({
        'AthenaID': chave_da_esteira(linha),
        'Currency': (texto(l.get('Commodity')) or texto(l.get('Currency'))).upper(),
        'MoedaDoContrato': texto((linha or {}).get('Currency')).upper(),
        'ClientAcronym': '',
        '_page': page['path'],
    })
    return l


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
    # O Deal ID do NDF de Commodities e o `Codigo Identificador` do Live
    # Position (mesa, 28/09/2026): e o numero pelo qual a operacao original se
    # identifica, o Nº da Confirmacao do Termo e a chave da esteira.
    ('DealID', 'deal_id', 'text'),
    ('Counterparty', 'counterparty', 'name'),
    ('TaxID', 'taxid', 'doc'),
    # a NOSSA entidade, dona da conta (o nome do Reference Data no b3-accounts)
    ('Party', 'party', 'name'),
    ('OriginalNotional', 'original', 'num'),
    ('UnwoundBefore', 'before', 'num'),
    # o VBR do swap (Valor Base Remanescente): a base dos fatores (§660)
    ('VBR', 'vbr', 'num'),
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


def _casa(valor, pv, modo, casas=None):
    """`casas`: as decimais que a celula MOSTRAVA — o valor da posicao casa
    quando arredonda para o mostrado (meia unidade da ultima casa)."""
    if pv is None or pv == '':
        return False
    if modo == 'contains':
        a, b = norm(valor), norm(pv)
        return bool(a) and bool(b) and (a in b or b in a)
    if modo == 'name':
        return norm_nome(valor) == norm_nome(pv) if norm_nome(valor) else False
    if casas is not None and modo in ('num', 'rate'):
        x, y = numero(valor, taxa=(modo == 'rate')), numero(pv, taxa=(modo == 'rate'))
        if x is None or y is None:
            return False
        return abs(x - y) <= 0.5 * 10 ** -casas + 1e-9
    return _iguais(valor, pv, modo)


def _aviso_sem_contrato(linha, posicoes, usados, nomes, mostrado):
    """`unwind_match_none`, dizendo o contrato MAIS PERTO quando um criterio
    so o separou (o valor do e-mail e o da posicao lado a lado): e o que a mesa
    precisa para saber se o e-mail ou a posicao esta errado."""
    params = {'criterios': ', '.join(nomes)}
    texto_ = 'No Live Position contract matches %s' % ', '.join(nomes)
    if len(usados) >= 2:
        for c, k, m in usados:
            outros = [u for u in usados if u[0] != c]
            quase = uma_visao_por_contrato(
                [p for p in posicoes or []
                 if all(_casa(linha.get(c2), p.get(k2), m2, mostrado.get(c2))
                        for c2, k2, m2 in outros)])
            if not quase:
                continue
            alvo = numero(linha.get(c), taxa=(m == 'rate'))
            if alvo is not None and m in ('num', 'rate'):
                quase.sort(key=lambda p: abs((numero(p.get(k), taxa=(m == 'rate')) or 0) - alvo))
            p = quase[0]
            params.update({'campo': c, 'contrato': p.get('contract') or '',
                           'planilha': texto(linha.get(c)), 'posicao': texto(p.get(k))})
            texto_ += ' (closest: B3 ID %s, %s %s in the e-mail and %s in the position)' % (
                params['contrato'], c, params['planilha'], params['posicao'])
            return aviso('unwind_match_none_near', texto_, **params)
    return aviso('unwind_match_none', texto_, **params)


def ao_mostrado(linha, pos):
    """Tira as marcas internas da linha depois do casamento. Os numeros ficam
    os do E-MAIL (mesa, 28/09/2026): o casamento aceita o valor arredondado,
    mas a grade mostra o que a mesa mandou — nao o valor exato da posicao."""
    for k in ('_shown', '_leg', '_client', '_dates'):
        linha.pop(k, None)


def _da_perna(linha, posicoes):
    """So os contratos do tipo da PERNA (o recap de opcao, `_leg`): `client` e
    contrato com cliente; `banco` e o B2B com entidade nossa (o Lawton), que
    a `queries` marca como `internal`. Sem perna, todos."""
    perna = linha.get('_leg')
    if perna == 'client':
        return [p for p in posicoes or [] if not p.get('internal')]
    if perna == 'banco':
        return [p for p in posicoes or [] if p.get('internal')]
    return list(posicoes or [])


def _desempatar(linha, achadas):
    """(contratos, pistas usadas) quando MAIS DE UM casou pelos criterios. O
    e-mail traz o que nao e criterio porque nao bate letra a letra com a
    posicao: o cliente abreviado (`M. Dias`) e as datas da opcao (o fixing ou a
    liquidacao — qual delas a B3 chama de vencimento depende do registro). Cada
    pista so estreita: a que eliminaria todos e ignorada, e o resultado ainda
    tem de ser UNICO para casar."""
    usadas = []
    nome = norm(linha.get('_client'))
    datas = set(linha.get('_dates') or ())
    pistas = []
    if nome and linha.get('_leg') != 'banco':           # no B2B o "Client" nao e a contraparte
        pistas.append(('Client', lambda p: nome in norm(p.get('counterparty'))))
    if datas:
        pistas.append(('Fixing/Settlement Date', lambda p: p.get('maturity') in datas))
    for rotulo, pista in pistas:
        if len(achadas) <= 1:
            break
        restam = [p for p in achadas if pista(p)]
        if restam and len(restam) < len(achadas):
            achadas = restam
            usadas.append(rotulo)
    return achadas, usadas


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
    mostrado = linha.get('_shown') or {}
    posicoes = _da_perna(linha, posicoes)
    achadas = uma_visao_por_contrato(
        [p for p in posicoes or []
         if all(_casa(linha.get(c), p.get(k), m) for c, k, m in usados)])
    if not achadas and mostrado:
        # O e-mail traz o numero como o Excel o EXIBE: vale a posicao cujo
        # valor arredonda para o mostrado — continua exigindo candidato UNICO.
        achadas = uma_visao_por_contrato(
            [p for p in posicoes or []
             if all(_casa(linha.get(c), p.get(k), m, mostrado.get(c)) for c, k, m in usados)])
    achadas, pistas = _desempatar(linha, achadas)
    nomes = nomes + pistas
    if len(achadas) == 1:
        return achadas[0], aviso('unwind_matched_by_characteristics',
                                 'B3 ID %s found in the Live Position by %s'
                                 % (achadas[0].get('contract'), ', '.join(nomes)),
                                 contrato=achadas[0].get('contract') or '',
                                 criterios=', '.join(nomes))
    if not achadas:
        return None, _aviso_sem_contrato(linha, posicoes, usados, nomes, mostrado)
    return None, aviso('unwind_match_ambiguous',
                       '%d Live Position contracts match %s — fill in the B3 ID'
                       % (len(achadas), ', '.join(nomes)),
                       n=len(achadas), criterios=', '.join(nomes))


def uma_visao_por_contrato(posicoes):
    """As posicoes com UMA linha por contrato. O Live Position traz o mesmo
    contrato na visao de cada entidade nossa (Banco x Lawton aparece duas
    vezes): contadas como dois candidatos, a perna Banco nunca casava — era
    "ambiguo" com um contrato so. Vale a visao de menor `view_rank` (a do
    Banco antes da do fundo); empate fica com a primeira."""
    melhor, ordem = {}, []
    for p in posicoes or []:
        k = norm(p.get('contract')) or id(p)
        if k not in melhor:
            ordem.append(k)
            melhor[k] = p
        elif p.get('view_rank', 2) < melhor[k].get('view_rank', 2):
            melhor[k] = p
    return [melhor[k] for k in ordem]


def posicao_pelo_contrato(contrato, posicoes):
    """A posicao do B3 ID (sem caixa nem espaco), ou None — na visao que vale
    quando o contrato aparece mais de uma vez (`uma_visao_por_contrato`)."""
    alvo = norm(contrato)
    if not alvo:
        return None
    achadas = uma_visao_por_contrato([p for p in posicoes or []
                                      if norm(p.get('contract')) == alvo])
    return achadas[0] if achadas else None


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
    if pre == 0 and du is None:
        du = 0.0                        # sem juros o desconto e 1: o DU nao muda nada
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


def _premio(linha, page):
    """O valor financeiro = quantidade x premio unitario, levado a reais pela
    paridade quando a pagina a tem (a opcao de Commodities: premio em USD por
    unidade, resultado em BRL — os numeros do e-mail); nas outras, x 1."""
    q = numero(linha.get('UnwoundNotional'))
    unit = numero(linha.get('UnitPremium'), taxa=True)
    if unit is None:
        unit = numero(linha.get('UnitPrice'), taxa=True)
    informado = numero(linha.get('Result'))
    fx = fx_da_linha(linha, page)
    faltam = [n for n, v in (('UnwoundNotional', q), ('UnitPremium', unit),
                             ('FXRate', fx), ('Result', informado)) if v is None]
    if faltam:
        return None, aviso('unwind_check_missing', 'Missing to check the amount: '
                           + ', '.join(faltam), teste='premio', campos=', '.join(faltam))
    # Na ORDEM de quem fez a conta: o total na moeda do premio vai a centavos e
    # so entao a reais (`139,930.00 x 5.0340 = 704,407.62` no e-mail; sem o
    # arredondamento do meio, 1 centavo a mais e um NOK que nao existe).
    calc = round(abs(q) * unit, 2) * fx
    if abs(abs(informado) - calc) > TOLERANCIA:
        return False, aviso('unwind_amount_mismatch',
                            'Settlement amount does not match quantity x unit premium',
                            informado=informado, calculado=round(calc, 2))
    return True, None


def _fatores(linha):
    """O caixa refeito pelos FATORES (§657/§660): VBR x (fator nosso − fator
    deles), com o nosso e o deles pelo papel (Ponta 1 = Factor Leg 1) — a
    conta inversa do fator (valor de liquidacao / VBR + 1): o que o arquivo
    leva tem de dar o caixa combinado. A tolerancia e a do arredondamento dos
    fatores na 8a casa (VBR x 1e-8 em cada um), mais o centavo."""
    vr = numero(linha.get('VBR'))
    f1 = numero(linha.get('FactorLeg1'), taxa=True)
    f2 = numero(linha.get('FactorLeg2'), taxa=True)
    papel = papel_swap(linha.get('Role'))
    res = numero(linha.get('Result'))
    faltam = [n for n, v in (('VBR', vr), ('FactorLeg1', f1), ('FactorLeg2', f2),
                             ('Role', papel), ('Result', res)) if v is None]
    if faltam:
        return None, aviso('unwind_check_missing', 'Missing to check the factors: '
                           + ', '.join(faltam), teste='fatores', campos=', '.join(faltam))
    nosso, deles = (f1, f2) if papel == '00' else (f2, f1)
    calc = abs(vr) * (nosso - deles)
    if abs(calc - res) > TOLERANCIA + abs(vr) * 2e-8:
        return False, aviso('unwind_factor_mismatch',
                            'Settlement amount does not match VBR x (our factor - their factor)',
                            informado=res, calculado=round(calc, 2))
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
            r, a = _premio(linha, page)
        elif teste == 'fatores':
            r, a = _fatores(linha)
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


# O que, mudado no Edit, refaz as contas da linha (`commands._refazer_calculos`).
CAMPOS_ECONOMICOS = ('OriginalNotional', 'UnwoundBefore', 'UnwoundNotional', 'Strike',
                     'TerminationRate', 'FXRate', 'PreFWDRate', 'DU', 'Currency',
                     'UnwindDate', 'SettlementDate', 'MaturityDate',
                     # o swap (§657/§660): acoes, pernas, VBR e papel refazem
                     # nocional e fatores
                     'Shares', 'EquityLeg', 'FundingLeg', 'Role', 'VBR')


def mesmo_valor(a, b):
    """O valor gravado e o do Save sao o mesmo? Numero compara como numero
    (`100000` gravado e `100,000.00` digitado sao iguais), o resto como texto."""
    na, nb = numero(a, taxa=True), numero(b, taxa=True)
    if na is not None and nb is not None:
        return abs(na - nb) < 1e-12
    return texto(a) == texto(b)


_DIVERGENCIAS = ('unwind_result_mismatch', 'unwind_amount_mismatch', 'unwind_factor_mismatch')


def resultado_calculado(avisos):
    """O resultado que o OTC Tracker calculou, quando ele NAO bate com o
    informado (a coluna `CalcResult`); None quando bate ou nao deu para
    conferir — a coluna so fala quando ha divergencia."""
    for a in avisos or []:
        if (a or {}).get('code') in _DIVERGENCIAS:
            return (a.get('params') or {}).get('calculado')
    return None


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
    """'total', 'parcial' ou None (nao da para dizer): total e o saldo ZERAR.
    Sem saldo para conferir, vale o que o e-mail DISSE (`UnwindType`, o
    "Unwind Parcial/Total" do recap do TRS, §657)."""
    tp = total_ou_parcial_pelo_saldo(linha)
    return tp if tp is not None else tipo_informado(linha.get('UnwindType'))


def total_ou_parcial_pelo_saldo(linha):
    orig = numero(linha.get('OriginalNotional'))
    antes = numero(linha.get('UnwoundBefore'))
    if antes is None and linha.get('PositionFound'):
        antes = 0.0
    agora = numero(linha.get('UnwoundNotional'))
    if None in (orig, antes, agora):
        return None
    return 'total' if (orig - antes - abs(agora)) <= TOLERANCIA else 'parcial'


def tipo_informado(v):
    """`Total`/`Parcial`/`Partial` -> 'total'/'parcial', ou None."""
    t = norm(v)
    if t == 'total':
        return 'total'
    if t in ('parcial', 'partial'):
        return 'parcial'
    return None


def papel_pela_conta(nossa, deles):
    """O PAPEL no swap pela CONTA: '00' (Ponta 1) quando a NOSSA e a de menor
    numero, '01' (Ponta 2) quando e a maior — o criterio do manual (4.2.12: "a
    conta do participante que tiver o MENOR numero sera a ponta 01"), o mesmo
    do 0897 do Swap Bullet (`swap_deal_ticket._ponta`) e da planilha de
    antecipacao da mesa (`IF(VALUE(nossa)>VALUE(deles);"01";"00")`). None sem
    as duas contas. Ate 21/10/2026 o papel era "Ponta 1 se a conta Participante
    da posicao e nossa", o que so acerta quando a nossa e a menor (§657)."""
    a, b = digitos(nossa).lstrip('0'), digitos(deles).lstrip('0')
    if not a or not b:
        return None
    return '01' if int(a) > int(b) else '00'


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
    """SWAP 0014 (`swap-antecipacao`, §4.2.10) na forma da planilha de
    antecipacao da mesa (§657): o valor para antecipacao e o NOCIONAL que sai
    do contrato (`UnwoundNotional`; no TRS, acoes x strike original) com os
    DOIS fatores; a Data Antecipacao e o dia em que o arquivo e gerado (o
    `TODAY()` da planilha — o recap chega no fim da tarde e o arquivo vai no
    dia seguinte, que e o D+1 da liquidacao), e a Data de Liquidacao (13,
    opcional) vai em branco, como na planilha. `Mantem Premios` so na
    antecipacao PARCIAL (o manual: "nao deve ser preenchido em caso de
    antecipacao total")."""
    faltas = []
    papel = papel_swap(linha.get('Role'))
    if papel is None:
        faltas.append('5 Papel (Role: %s)' % (linha.get('Role') or '-'))
    f1 = numero(linha.get('FactorLeg1'), taxa=True)
    f2 = numero(linha.get('FactorLeg2'), taxa=True)
    if f1 is None or f2 is None:
        faltas.append('7/8 Fator para Antecipação (Factor Leg 1 / Factor Leg 2)')
    valor = numero(linha.get('UnwoundNotional'))
    if valor is None:
        faltas.append('11 Valor Para Antecipação (Unwound Notional)')
    mantem = None
    tp = total_ou_parcial(linha)
    if tp is None:
        faltas.append('12 Mantém Prêmios (total or partial? OriginalNotional/UnwoundBefore/'
                      'UnwoundNotional)')
    elif tp == 'parcial':
        mantem = _sim_nao(linha.get('KeepPremium'))
        if mantem is None:
            faltas.append('12 Mantém Prêmios (Keep Premium is required on a partial unwind)')
    reg = _posicional(SWAP_REGISTRO, {
        '1': 'SWAP', '2': '1', '3': '0014', '4': linha.get('Contract'), '5': papel,
        '6': linha.get('MyNumber'), '7': f1, '8': f2, '9': hoje_ymd, '10': '',
        '11': None if valor is None else abs(valor), '12': mantem, '13': '',
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
    Asiatico ou nao, o arquivo e o MESMO (mesa, 28/09/2026): a antecipacao nao
    leva as datas de verificacao — o campo 16 vai `000` e nao ha linha tipo 2."""
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


def espelho_b2b(linha):
    """A MESMA recompra na visao da CONTRAPARTE, quando ela tambem e nossa (o
    B2B Banco x Lawton): as duas contas trocam de lugar e o lado se inverte —
    o comprado de um e o vendido do outro. O resto (contrato, quantidade,
    taxas, datas) e do contrato e nao muda."""
    comprado = linha.get('Comprado')
    return dict(linha, PartyAccount=linha.get('CptyAccount'),
                CptyAccount=linha.get('PartyAccount'),
                Comprado=None if comprado is None else not comprado)


def nome_do_arquivo(page, visao):
    """`UNWIND_<PRODUTO>_<VISAO>.txt` — o produto no nome porque o Batch Conecta
    e UMA pasta para todos, e o `UNWIND_BANCO.txt` e o da Fase 1."""
    prod = re.sub(r'[^A-Z0-9]+', '_', page['dir'].upper()).strip('_')
    vis = {'JPM': 'BANCO'}.get(str(visao or '').upper(), str(visao or '').upper() or 'BANCO')
    return 'UNWIND_%s_%s.txt' % (prod, vis)
