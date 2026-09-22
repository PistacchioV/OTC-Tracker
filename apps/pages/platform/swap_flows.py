# -*- coding: utf-8 -*-
"""Os arquivos-dia de SWAP da B3 lidos por CONTRATO — a posição (DPOSICAO-SWAP)
e o fluxo (DFLUXO) — e a amortização de um evento: que percentual amortiza
neste fluxo, e sobre qual base.

Nasceu na feature Tools, para o pré-preenchimento do Swap Calculator pelo
B3 ID (§426/§427), e veio para a platform quando o Swap VCP (§452) fez a
MESMA pergunta — o notional que amortiza no fluxo do dia — e uma feature não
importa outra (SoC-003). A Tools continua expondo os nomes antigos como
aliases (`queries._fluxos_do_contrato`, `domain.base_da_amortizacao`…): os
testes e o `check_soc_layers` os procuram lá, e o pré-preenchimento chama
pelo alias do próprio módulo, que é onde o teste troca.

Nada aqui importa `routes` no topo: é busca atrasada dentro da função, como
toda platform.
"""
import os
import unicodedata
from datetime import date

from apps.pages import data_store as _store
from apps.pages.precificador import liquidacao


def _R():
    from apps.pages import routes
    return routes


# ── o pré-preenchimento pelo B3 ID ──────────────────────────────────────────
#
# A posição de swap (DPOSICAO-SWAP) é POSICIONAL — 170 campos em ordem, com
# nomes repetidos por perna —, e é o Live Position Swap Characteristics que
# a lê assim. Os índices abaixo são os das colunas que a mesa citou, contados
# NA POSIÇÃO (o `_SWAPCHAR_LABELS` do routes): a primeira e a segunda coluna
# de mesmo nome são a ponta da Parte e a da Contraparte.
POS = {
    'tipo_contrato': 0, 'contrato': 2, 'conta_cp': 7, 'doc_cp': 8, 'inicio': 11, 'vencimento': 12,
    'valor_base': 14, 'remanescente': 15, 'valor_inicial': 24, 'data_termo': 25,
    'tipo_amort': 38, 'identificador': 145,
    # ponta 1 (Parte → ativa) / ponta 2 (Contraparte → passiva)
    'pct': (39, 49), 'indice': (40, 50), 'sinal': (42, 52), 'taxa': (43, 53),
    'nome_classe': (69, 74), 'cupom_limpo': (76, 78), 'data_cotacao': (77, 79),
    # `Denominação` (Parte/Contraparte): o texto livre da curva VCP — o que as
    # colunas não dizem, lido pelo Swap Calculator (§479).
    'denominacao': (70, 75),
    # `Data de Fixing IPCA (Parte/Contraparte)` — FE/FF do arquivo. Chama-se
    # Data e traz `1`/`2`: a defasagem em meses do número-índice (M-1/M-2), que
    # o Swap Calculator usa na perna de IPCA DIRETO.
    'fixing_ipca': (160, 161),
}


FLX = {'contrato': 0, 'identificador': 10, 'tipo_amort': 8, 'evento': 11,
        'taxa_amort': (16, 21), 'inicio': 22, 'fim': 23,
        # `Sinal/Taxa de Juros Parte` e `... Contraparte`: a taxa contratada
        # DAQUELE fluxo, na mesma ordem das pontas da posição (Parte → ativa,
        # Contraparte → passiva). É o plano B do Swap Calculator quando a
        # coluna de taxa da posição vem vazia.
        'sinal_juros': (12, 17), 'taxa_juros': (13, 18)}


def norm(s):
    """Minúsculas sem acento, espaços colapsados — como o `_fcst_norm`."""
    s = unicodedata.normalize('NFKD', str(s or '').lower())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(s.split())


def numero_da_posicao(v):
    """Célula numérica do arquivo de posição (vírgula DECIMAL, sem milhar)."""
    s = str(v or '').strip()
    if not s:
        return None
    try:
        return float(s.replace(' ', '').replace(',', '.'))
    except ValueError:
        return None


def base_da_amortizacao(texto):
    """O `Tipo Amortização` do fluxo → a base do Swap Calculator, ou `None`.

    A coluna tem quatro respostas no cadastro `swap-amortizacao`, e duas delas
    NÃO são uma base — são a ausência de amortização neste fluxo:

        Sobre Valor Base Original      → base = original
        Sobre Valor Base Remanescente  → base = remanescente
        Na Data de Vencimento          → At Maturity; no fluxo, nada
        Sem Troca de Amortização       → Sem Troca; não amortiza nunca

    Por isso a pergunta "qual base" e a pergunta "amortiza aqui?" são duas
    funções: colapsá-las faria um swap que amortiza só no vencimento cair na
    lista do que "não deu para puxar" e aparecer em vermelho na tela, quando o
    cadastro respondeu com precisão que não há amortização neste fluxo.
    """
    t = norm(texto)
    if not t:
        return None
    if 'remanesc' in t or 'saldo' in t:
        return liquidacao.SOBRE_REMANESCENTE
    if 'original' in t or 'percentual' in t or 'valor base' in t:
        return liquidacao.SOBRE_ORIGINAL
    if 'vencimento' in t:
        # `Na Data de Vencimento` tem base PRÓPRIA na tela (At Maturity): as
        # outras duas descrevem uma PARCELA, e dizer "sobre o valor original"
        # num contrato que só amortiza no fim afirma um cronograma que ele não
        # tem. Num fluxo intermediário o percentual é zero e a base não muda
        # nada de qualquer jeito (`amortiza_no_fluxo` responde isso).
        return liquidacao.AT_MATURITY
    if 'sem troca' in t:
        # Contrato que NUNCA amortiza: o principal volta inteiro no fim, que é
        # o que `At Maturity` diz. Respondia `Sobre Valor Base Original` — o
        # default histórico da tela — com o argumento de que o percentual é
        # zero e a base não muda número nenhum. Não muda mesmo; muda o que a
        # tela AFIRMA, e é esse o ponto: o Swap Calculator abria um contrato
        # marcado "Sem Troca de Amortização" no Live Position dizendo "sobre o
        # notional original — parcela constante", um cronograma de parcelas que
        # aquele swap não tem. É o mesmo argumento que já valia para `Na Data
        # de Vencimento`, e ele vale aqui com mais força ainda — só que o At
        # Maturity também não serve: ele afirma a devolução do principal no
        # encerramento, e este contrato não tem evento de amortização NENHUM.
        # Por isso a base própria (`SEM_TROCA`), que é zero em todo fluxo.
        return liquidacao.SEM_TROCA
    return None


def por_nome(row, nome):
    """O valor da coluna `nome`, cego à CAIXA do cabeçalho.

    O arquivo da B3 escreve `Data vencimento` com v minúsculo e `Tipo de
    Contrato` com C maiúsculo, e a leitura por nome só existe para o arquivo
    ESTREITO — onde não se pode contar com o índice. Um `row.get` com a grafia
    errada devolve vazio e a regra do bullet simplesmente não roda, sem erro."""
    if nome in row:
        return row[nome]
    alvo = norm(nome)
    for k, v in row.items():
        if norm(k) == alvo:
            return v
    return ''


def tipo_de_contrato(texto):
    """`Tipo de Contrato` da posição → `'Bullet'`, `'Cashflow'` ou `''`.

    A B3 escreve `02` para bullet e `01` para cashflow, com zero à esquerda e às
    vezes com a cauda decimal do Excel. Vale também o texto já traduzido, porque
    a posição às vezes chega pela leitura por NOME de coluna (arquivo estreito)
    em vez da posicional.

    Fora desses dois, `''` — e isso é LACUNA, não "cashflow". Um bullet lido
    como cashflow não amortiza no vencimento e o fator do Swap VCP sai com o
    principal inteiro dentro dele (§470).

    Mora aqui, e não na Tools, porque quem pergunta são as DUAS: o Swap
    Calculator (a base do ajuste) e o Swap VCP (a amortização). A Tools a expõe
    pelo nome antigo — duas funções com a mesma pergunta e respostas diferentes
    (`'Bullet'` numa, `'bullet'` na outra) é como uma comparação passa a ser
    sempre falsa sem ninguém ver.
    """
    t = norm(texto)
    if not t:
        return ''
    if 'bullet' in t:
        return 'Bullet'
    if 'cashflow' in t or 'cash flow' in t:
        return 'Cashflow'
    d = t.replace('.0', '').strip().lstrip('0')
    return {'2': 'Bullet', '1': 'Cashflow'}.get(d, '')


def amortiza_no_fluxo(texto):
    """O fluxo amortiza? `Na Data de Vencimento` e `Sem Troca de Amortização`
    dizem que não — e é resposta, não lacuna."""
    t = norm(texto)
    if not t:
        return None
    return not ('vencimento' in t or 'sem troca' in t)


def celula(vals, i):
    v = vals[i] if i < len(vals) else ''
    return '' if v is None else str(v).strip()


def iso(v):
    d = _R()._fcst_parse_date(v) if v else None
    return d.strftime('%Y-%m-%d') if d else ''


def subpastas_num(pasta):
    """Os nomes NUMÉRICOS de subpasta (ano, mês ou dia), do maior para o menor."""
    try:
        nomes = _store.listdir(pasta)
    except OSError:
        return []
    return sorted((n for n in nomes
                   if n.isdigit() and _store.isdir(os.path.join(pasta, n))),
                  reverse=True)


def swap_day_file(file_tpl, ref=None):
    """(path, dref) do arquivo de posição de swap mais recente que EXISTE.

    O caminho normal é o `_swap_day_path`: anda até dez dias úteis para trás a
    partir do D-1, que é o que cobre o dia cujo arquivo ainda não foi salvo.
    Aqueles dez dias são um TETO, porém, e o que está atrás dele não é "sem
    posição" — é a última posição que a mesa tem. Sem esta segunda porta, uma
    rotina de save parada por duas semanas fazia o B3 ID responder *not found*,
    que se lê como "esse swap não existe" e não como "o arquivo do dia não
    chegou".

    Passado o teto, o mais recente é achado descendo a árvore `AAAA/MM/DD` pelo
    fim — três `listdir`, e não um `stat` por dia, que no share é ida e volta de
    rede por dia varrido. Nada ADIANTE do `ref` entra: ele é o mesmo ponto de
    partida da janela, e um arquivo de hoje que entrasse por uma porta e ficasse
    de fora da outra faria a mesma consulta responder duas coisas."""
    R = _R()
    ref = ref or R._prev_anbima_bizday(date.today())
    path, dref = R._swap_day_path(ref, file_tpl)
    if path:
        return path, dref
    raiz = os.path.join(R.B3_JSON_ROOT, 'Swap')
    for ano in subpastas_num(raiz):
        for mes in subpastas_num(os.path.join(raiz, ano)):
            base = os.path.join(raiz, ano, mes)
            for dia in subpastas_num(base):
                try:
                    d = date(int(ano), int(mes), int(dia))
                except ValueError:
                    continue
                if d > ref:
                    continue
                dref = d.strftime('%y%m%d')
                p = os.path.join(base, dia, file_tpl.format(dref))
                if _store.isfile(p):
                    return p, dref
    return None, None


def fluxos_do_contrato(contrato, ident, dia_posicao=None):
    """As linhas do DFLUXO daquele contrato, em ordem de evento.

    O DFLUXO é procurado a partir do dia da POSIÇÃO, e não do D-1: os dois
    arquivos são gravados lado a lado mas são dois arquivos, e cada um andando
    para trás por conta própria pode parar em dias diferentes — o fluxo de
    ontem contra a posição da semana passada não dá erro nenhum, dá um período
    que não é o daquele saldo.

    A chave é o **Código do contrato**, e o `Código Identificador` só responde
    quando a posição não traz contrato nenhum. Ele PARECE uma chave e não é: na
    instância ele guarda a LOB (`CEM`), e aceitá-lo ao lado do contrato trazia
    para dentro do fluxo de UM swap os eventos de todos os outros da mesma mesa
    — milhares deles. O efeito não era uma tela vazia: o "último evento até
    hoje" passava a ser o de outro contrato, e o "evento anterior" quase sempre
    tinha a MESMA data, o que fazia o Flow start sair igual ao Flow end.
    """
    R = _R()
    path, _dref = swap_day_file('73760_{}_DFLUXO.json', ref=dia_posicao)
    if not path:
        return []
    try:
        src = R._db_day_records(path) or []
    except Exception:                                       # noqa: BLE001
        return []
    chave = norm(contrato).replace(' ', '') or norm(ident).replace(' ', '')
    if not chave:
        return []
    saida = []
    for row in src:
        vals = list(row.values())
        if len(vals) < 20:
            continue                                        # mock esparso: sem fluxo
        c = norm(celula(vals, FLX['contrato'])).replace(' ', '')
        i = norm(celula(vals, FLX['identificador'])).replace(' ', '')
        if (c or i) != chave:                           # o contrato manda; o ident supre
            continue
        saida.append({
            'evento': iso(celula(vals, FLX['evento'])),
            'inicio': iso(celula(vals, FLX['inicio'])),
            'fim': iso(celula(vals, FLX['fim'])),
            'tipo_amort': R._lp_amort_label(celula(vals, FLX['tipo_amort'])),
            'taxa_amort': numero_da_posicao(celula(vals, FLX['taxa_amort'][0]))
            if celula(vals, FLX['taxa_amort'][0]) else
            numero_da_posicao(celula(vals, FLX['taxa_amort'][1])),
            'taxa_juros': [numero_da_posicao(celula(vals, i)) for i in FLX['taxa_juros']],
            'sinal_juros': [celula(vals, i) for i in FLX['sinal_juros']],
        })
    return sorted(saida, key=lambda f: f['evento'])


def periodo_do_evento(fluxos, x, inicio_swap, data_operacao, hoje):
    """O período de acumulação de UM evento do DFLUXO, gravado no próprio item.

    Escreve `p_inicio`, `p_fim` e `p_assumido`. O fim é a data do evento — é o
    dia em que o fluxo liquida. Para o início há quatro candidatos, nesta ordem:

    1. o **evento ANTERIOR** — o fluxo abre onde o outro fechou;
    2. a **`Data início`** do swap, no primeiro fluxo: é o dia em que o
       contrato começou a correr;
    3. a **`Data operação termo`** (a data de contratação), para o contrato que
       veio sem data de início;
    4. a `Data Início Composição da Taxa` do PRÓPRIO evento, como último
       recurso — ela nem sempre é o começo do período.

    E o candidato só vale se for ANTERIOR ao fim: um período que abre no dia em
    que fecha não é um período, é o sintoma de a coluna não responder o que se
    perguntou. Era assim que o Flow start saía igual ao Flow end — pelo evento
    anterior de mesma data (o DFLUXO repete a data quando há mais de um
    lançamento no dia) ou pela composição de taxa que o arquivo carimba com a
    data do evento —, e uma janela de zero dia não acusa erro nenhum: ela
    liquida com juros zero.
    """
    fim = x['evento'] or x['fim'] or hoje
    anterior = ''
    for y in fluxos:
        if y['evento'] and y['evento'] < fim and y['evento'] > anterior:
            anterior = y['evento']
    x['p_fim'] = fim
    for exato, candidato in ((True, anterior), (True, inicio_swap),
                             (False, data_operacao), (False, x['inicio'])):
        if candidato and candidato < fim:
            x['p_inicio'], x['p_assumido'] = candidato, not exato
            return x
    x['p_inicio'], x['p_assumido'] = '', False
    return x


def amortizacao_do_evento(x, tipo_amort_posicao):
    """A amortização de UM evento: `p_amort` (o percentual) e `p_base_amort`.

    `Tipo Amortização` e `Taxa Amortização` do PRÓPRIO evento — a coluna já diz
    se amortiza sobre o valor base original, sobre o remanescente ou só no
    vencimento, e a taxa já traz quanto amortiza NAQUELA data. Sem a coluna no
    fluxo vale o `Tipo de amortização` da posição.
    """
    tipo = x['tipo_amort'] or tipo_amort_posicao
    x['p_base_amort'] = base_da_amortizacao(tipo) or ''
    if amortiza_no_fluxo(tipo) is False:
        # "Na Data de Vencimento" / "Sem Troca de Amortização": não é lacuna,
        # é a resposta — o fluxo não amortiza.
        x['p_amort'] = '0'
    elif x['taxa_amort'] is not None:
        # CINCO casas, não quatro. O percentual de amortização multiplica um
        # notional de centenas de milhões, e a 5ª casa vale dinheiro: num VBR
        # de R$ 282,8 mi, `0,7246%` contra `0,72464%` são R$ 113 de diferença no
        # valor amortizado. O arredondamento aqui não era exibição — era o
        # número que ia para o campo e para o cálculo.
        x['p_amort'] = '{:.5f}'.format(x['taxa_amort'])
    else:
        # O evento existe no DFLUXO e a `Taxa Amortização` dele está vazia:
        # num contrato que amortiza por fluxo, a célula em branco é o fluxo
        # que só paga juros (o cronograma traz 33,33 nos três últimos e nada
        # nos outros). Zero é a resposta, não a ausência dela — em branco a
        # tela marcava "não deu para puxar" e a mesa digitava 0 à mão.
        x['p_amort'] = '0'
    return x


# ── o que o Swap VCP pergunta (§452) ──────────────────────────────────────────

def posicoes_swap(ref):
    """{contrato normalizado → dict} da POSIÇÃO de swap mais recente até `ref`
    (andando para trás como o `_swap_day_path`): o que o VCP precisa por
    contrato — VBR (`Valor Base Remanescente`), valor base e inicial, `Tipo de
    amortização`, o `Tipo de Contrato` (bullet/cashflow) com a `Data
    Vencimento` ao lado, e o `Código Identificador` (a LOB). Uma leitura para a tela
    inteira, nunca uma por linha. Vazio sem arquivo."""
    R = _R()
    path, dref = R._swap_day_path(ref, '73760_{}_DPOSICAO-SWAP.json')
    if not path:
        return {}, None
    try:
        src = R._db_day_records(path) or []
    except Exception:                                       # noqa: BLE001
        return {}, None
    out = {}
    for row in src:
        vals = list(row.values())
        if len(vals) < 120:
            contrato = row.get('Contrato', '')
            ident = row.get('Código Identificador', row.get('Codigo Identificador', ''))
            item = {'contrato': str(contrato or '').strip(), 'identificador': str(ident or '').strip(),
                    'tipo_amort': '', 'remanescente': numero_da_posicao(row.get('Valor Base Remanescente', '')),
                    'valor_base': numero_da_posicao(row.get('Valor base', '')),
                    'valor_inicial': numero_da_posicao(row.get('Valor base inicial', '')),
                    'tipo_contrato': tipo_de_contrato(por_nome(row, 'Tipo de Contrato')),
                    'vencimento': iso(por_nome(row, 'Data vencimento'))}
        else:
            item = {'contrato': celula(vals, POS['contrato']),
                    'identificador': celula(vals, POS['identificador']),
                    'tipo_amort': R._swapchar_amort_text(celula(vals, POS['tipo_amort'])),
                    'remanescente': numero_da_posicao(celula(vals, POS['remanescente'])),
                    'valor_base': numero_da_posicao(celula(vals, POS['valor_base'])),
                    'valor_inicial': numero_da_posicao(celula(vals, POS['valor_inicial'])),
                    'tipo_contrato': tipo_de_contrato(celula(vals, POS['tipo_contrato'])),
                    'vencimento': iso(celula(vals, POS['vencimento']))}
        chave = norm(item['contrato']).replace(' ', '')
        if chave:
            out.setdefault(chave, item)
    return out, R._b3_dref_to_iso(dref)


def amortizacao_do_dia(contrato, ident, ref_iso, tipo_amort_posicao, dia_posicao=None):
    """A amortização do evento do DFLUXO que LIQUIDA em `ref_iso` (AAAA-MM-DD)
    para este contrato — `p_amort` (percentual, texto) e `p_base_amort` (a
    base), pela mesma regra do Swap Calculator (`amortizacao_do_evento`).
    `None` quando o contrato não tem evento nesse dia."""
    fluxos = fluxos_do_contrato(contrato, ident, dia_posicao)
    for x in fluxos:
        if x.get('evento') == ref_iso:
            return amortizacao_do_evento(x, tipo_amort_posicao)
    return None

