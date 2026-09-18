# -*- coding: utf-8 -*-
"""As regras puras da recompra (unwind). Sem Flask, sem banco, sem SMTP.

O e-mail `BRL NDF Unwind Notification` do Athena traz DUAS tabelas
`Atributo | Valor` — 'Before Unwind' (a operacao original) e 'After Unwind'
(a recompra). Aqui elas viram um registro, e nada mais: o de-para para os
campos do arquivo da B3 (TER 0014, secao 4.9.3 do manual) nao mora no codigo,
como todo de-para desta casa.

Duas coisas que a amostra ensinou e que nao sao obvias:

  * **o assunto carrega DOIS identificadores**
    (`..._STP-XE-10G5U5X-0-0_E5VL-3ICSK0W`). O primeiro e o Athena ID, e bate
    com a linha da tabela; o segundo ainda nao sabemos o que e, entao ele e
    GUARDADO com nome proprio em vez de descartado ou confundido com o Athena
    ID.
  * **o valor que chega em `Notional CCY` pode nao ser codigo ISO** (a amostra
    traz `USB` num termo de USD/BRL). O dominio NAO conserta: quem traduz
    codigo de moeda e cadastro, e um `USB -> USD` escondido aqui viraria a
    regra que ninguem acha no dia em que o Athena mandar outro codigo torto.
    O valor sobe como veio, e quem monta o arquivo decide.
"""
import re

# Titulo da tabela -> secao do registro. O titulo vem do Word com espaco no
# fim ('Before Unwind '), ja limpo pelo leitor.
SECOES = {
    'before unwind': 'before',
    'after unwind':  'after',
}

# A linha de cabecalho das duas tabelas. Nao e dado.
_CABECALHO = ('attribute', 'value')

# `Nome_<id1>_<id2>` no fim do assunto. Os ids do Athena tem letras, digitos e
# hifen; o `_` e o separador.
_IDS_ASSUNTO = re.compile(r'_([A-Za-z0-9][A-Za-z0-9-]*)')

_NUM_LIXO = re.compile(r'[^\d.+-]')


def norm(s):
    return ' '.join(str(s or '').split()).strip().lower()


def numero(txt):
    """'42,227.42' -> 42227.42; '' ou texto -> None.

    O e-mail vem em formato AMERICANO (virgula de milhar, ponto decimal), que
    e o que o Athena manda. Nao confundir com a coluna brasileira das telas."""
    t = str(txt or '').strip()
    if not t:
        return None
    t = _NUM_LIXO.sub('', t.replace(',', ''))
    try:
        return float(t)
    except ValueError:
        return None


def ids_do_assunto(subject):
    """Os identificadores do assunto, na ordem. Para
    'BRL NDF Unwind Notification_STP-XE-10G5U5X-0-0_E5VL-3ICSK0W' devolve
    ['STP-XE-10G5U5X-0-0', 'E5VL-3ICSK0W']."""
    return _IDS_ASSUNTO.findall(str(subject or ''))


def secoes_das_tabelas(tabelas):
    """As tabelas do leitor -> {secao: [(atributo, valor), ...]} + os titulos
    que nao reconhecemos.

    A primeira linha de cada tabela e o TITULO (uma celula so, `colspan=2`);
    a segunda e o cabecalho `Attribute | Value`. O resto e par."""
    out, desconhecidos = {}, []
    for t in tabelas or []:
        titulo = norm(t[0][0]) if t and t[0] else ''
        chave = SECOES.get(titulo)
        if not chave:
            if titulo:
                desconhecidos.append(t[0][0])
            continue
        pares = []
        for linha in t[1:]:
            if len(linha) < 2:
                continue
            if tuple(norm(c) for c in linha[:2]) == _CABECALHO:
                continue
            pares.append((linha[0], linha[1]))
        out[chave] = pares
    return out, desconhecidos


def parse_notification(tabelas, subject=''):
    """As tabelas ja lidas -> o registro da recompra.

    Recebe as TABELAS, nunca o HTML: o dominio e puro e quem le arquivo/e-mail
    e o `infra`. Quem junta os dois e o `commands`.

    Devolve `secoes` (dict por secao, ultimo valor vence), `pares` (a ordem
    original, que e a que o aviso de liquidacao reproduz) e `avisos` no
    formato {code, params, text} do §486 — a tela diz pelo `_TRANS`."""
    pares, desconhecidos = secoes_das_tabelas(tabelas)
    avisos = []
    for titulo in desconhecidos:
        avisos.append({'code': 'unwind_unknown_table', 'params': {'title': titulo},
                       'text': 'Unrecognised table in the notification: %s' % titulo})
    for chave in ('before', 'after'):
        if chave not in pares:
            avisos.append({'code': 'unwind_missing_section', 'params': {'section': chave},
                           'text': 'The notification has no "%s unwind" table' % chave})
    secoes = {}
    for chave, lista in pares.items():
        d = {}
        for atributo, valor in lista:
            if atributo in d and d[atributo] != valor:
                avisos.append({'code': 'unwind_duplicate_attr',
                               'params': {'attr': atributo, 'section': chave},
                               'text': 'Attribute %r appears twice in "%s"' % (atributo, chave)})
            d[atributo] = valor
        secoes[chave] = d
    ids = ids_do_assunto(subject)
    athena_id = (secoes.get('before', {}).get('Athena ID') or (ids[0] if ids else '')).strip()
    if ids and athena_id and ids[0] != athena_id:
        avisos.append({'code': 'unwind_id_mismatch',
                       'params': {'subject': ids[0], 'table': athena_id},
                       'text': 'Subject id %s does not match the table id %s' % (ids[0], athena_id)})
    return {'athena_id': athena_id,
            'notification_id': ids[1] if len(ids) > 1 else '',
            'subject_ids': ids,
            'secoes': secoes,
            'pares': pares,
            'avisos': avisos}


# ==============================================================================
#  A PONTE ATE O CONTRATO DA B3
# ==============================================================================
# O aviso do Athena nao traz o contrato da B3, e o campo 8 do TER 0014
# (`Contrato`) EXIGE ele. A ponte e o `Codigo Identificador` do Live Position
# NDF: os 14 caracteres da DIREITA do Athena ID sao o que a posicao guarda
# ('STP-XE-10G5U5X-0-0' -> 'XE-10G5U5X-0-0'), e a linha que casar responde pelo
# `Contrato`.
IDENT_LEN = 14


def identificador(athena_id):
    """Os 14 caracteres da direita do Athena ID — o `Codigo Identificador` da
    posicao. Id mais curto que isso volta inteiro (nao se inventa prefixo)."""
    t = str(athena_id or '').strip()
    return t[-IDENT_LEN:] if len(t) > IDENT_LEN else t


def contrato_por_identificador(linhas, athena_id):
    """(contrato, posicao) da linha do Live Position NDF cujo `Codigo
    Identificador` casa com o Athena ID; (None, None) se nao houver.

    Recebe as LINHAS (o dominio e puro). Casa sem caixa e sem branco. Duas
    linhas com o mesmo identificador devolvem a PRIMEIRA e quem chama avisa:
    escolher em silencio entre duas posicoes e recomprar a errada."""
    alvo = identificador(athena_id).strip().upper()
    if not alvo:
        return None, None
    achadas = [l for l in (linhas or [])
               if str(l.get('Codigo Identificador', '') or '').strip().upper() == alvo]
    if not achadas:
        return None, None
    pos = achadas[0]
    return (str(pos.get('Contrato', '') or '').strip() or None), pos


# ==============================================================================
#  A PROVA REAL DOS VALORES
# ==============================================================================
# O aviso traz o resultado E as parcelas que o produzem, entao da para REFAZER
# a conta e recusar um aviso que nao fecha. UMA formula serve os dois casos,
# conferida contra tres operacoes reais (uma em moeda estrangeira e duas de
# nocional fixo em reais, estas ultimas contra a planilha da mesa):
#
#     Nocional ME   = Unwound Amount            (nocional em moeda estrangeira)
#                   = Unwound Amount / Strike   (nocional FIXO EM REAIS)
#     Valor Futuro  = Nocional ME x (Termination Rate - Strike) x sinal
#     Resultado     = Valor Futuro / (1 + Pre FWD Rate)^(DU/252)
#
#   sinal = +1 com o banco COMPRADO no termo original, -1 com o banco vendido:
#   comprado ganha quando a taxa SOBE, vendido quando ela cai. A posicao NAO
#   esta no aviso — vem do Live Position NDF, pela mesma ponte do contrato.
#
# **O QUE O AVISO AFIRMA NAO SE PODE USAR NO NOCIONAL FIXO EM REAIS.** Nas duas
# amostras de 2026 o e-mail trouxe Future Value, Present Value, Calculated
# Termination Fee e ate a Direction ERRADOS — afirmava Present Value -222,75
# num caso cujo resultado e +42,80, e Direction PAY numa recompra em que o
# banco RECEBE. Copiar esses campos para o aviso mandaria ao cliente o valor
# errado com o sinal errado. O unico campo certo nos tres casos e o **Input
# Termination Fee**, e e contra ele que a conta se confere.
TOLERANCIA = 0.01          # um centavo: o aviso ja vem arredondado a 2 casas
BASE_DU = 252.0


def _perto(a, b, tol=TOLERANCIA):
    return a is not None and b is not None and abs(a - b) <= tol


def resultado_apurado(depois):
    """O resultado da recompra: o **Input Termination Fee**, nunca o Present
    Value (ver o bloco acima — no nocional fixo em reais o Present Value do
    aviso esta errado, em valor e em sinal)."""
    return numero(depois.get('Input Termination Fee'))


def notional_me(antes, depois, brl_fixed):
    """O nocional em MOEDA ESTRANGEIRA da parcela recomprada.

    Com o nocional fixo em reais o `Unwound Amount` vem em BRL e se divide
    pelo Strike — foi assim que 59.999,98 / 5,2039 deu os 11.529,81 da
    planilha da mesa. **Qual e a moeda estrangeira o aviso nao diz**: vem do
    Live Position NDF, e por isso o aviso nao se monta sem a posicao."""
    unw = numero(depois.get('Unwound Amount'))
    if unw is None:
        return None
    if not brl_fixed:
        return unw
    strike = numero(antes.get('Strike'))
    return (unw / strike) if strike else None


def conferir_apuracao(antes, depois, brl_fixed=False, comprado=None):
    """Refaz o resultado a partir das parcelas e compara com o Input
    Termination Fee.

    `conferido` tem TRES respostas: True (fecha), False (NAO fecha, e diz
    qual parcela) e None (nao da para conferir — parcela ausente, ou a
    posicao do banco nao resolvida). As tres sao diferentes: um aviso sem
    parcela e um aviso errado nao podem sair iguais."""
    def _nao_da(code, text):
        return {'conferido': None, 'fv_calc': None, 'resultado_calc': None,
                'notional_me': None, 'direcao_calc': '',
                'avisos': [{'code': code, 'params': {}, 'text': text}]}

    if comprado is None:
        return _nao_da('unwind_position_unknown',
                       'The bank position (bought/sold) was not resolved in the Live Position')
    me = notional_me(antes, depois, brl_fixed)
    strike = numero(antes.get('Strike'))
    term = numero(depois.get('Termination Rate'))
    pre = numero(depois.get('Pre FWD Rate'))
    du = numero(depois.get('DU'))
    fee = resultado_apurado(depois)
    if None in (me, strike, term, pre, du, fee):
        return _nao_da('unwind_check_missing',
                       'The notification is missing a figure needed to re-check the result')
    fv = me * (term - strike) * (1 if comprado else -1)
    res = fv / ((1.0 + pre / 100.0) ** (du / BASE_DU))
    avisos = []
    if not _perto(fee, res):
        avisos.append({'code': 'unwind_result_mismatch',
                       'params': {'informado': fee, 'calculado': round(res, 2)},
                       'text': 'Input Termination Fee does not match the recomputed result'})
    # A direcao e do SINAL do resultado, nunca do campo Direction do aviso.
    direcao = 'RECEIVE' if res > 0 else ('PAY' if res < 0 else '')
    do_email = str(depois.get('Direction', '') or '').strip().upper()
    if direcao and do_email and direcao != do_email:
        avisos.append({'code': 'unwind_direction_mismatch',
                       'params': {'email': do_email, 'calculado': direcao},
                       'text': 'The notification Direction disagrees with the sign of the result'})
    return {'conferido': not any(a['code'] == 'unwind_result_mismatch' for a in avisos),
            'fv_calc': fv, 'resultado_calc': res, 'notional_me': me,
            'direcao_calc': direcao, 'avisos': avisos}


# ==============================================================================
#  O QUE O AVISO PRECISA DA POSICAO (Live Position NDF)
# ==============================================================================
# O aviso do Athena nao se basta. Quatro coisas so existem na posicao, e as
# quatro chegam pela MESMA ponte (os 14 da direita do Athena ID -> `Codigo
# Identificador`):
#
#   `Contrato`                              -> campo 8 do TER 0014
#   `Simbolo da Moeda`                      -> a moeda estrangeira. No nocional
#                                              fixo em reais o aviso so diz
#                                              'BRR', e sem isto o e-mail ao
#                                              cliente sairia com o valor em
#                                              reais rotulado como se fosse a
#                                              moeda da operacao
#   `Descricao da posicao do Participante`  -> o SINAL do resultado
#   `Valor Base no registro` - `Valor Antecipado` -> o SALDO
#
# O `Valor Antecipado` e o acumulado JA recomprado, em moeda estrangeira: na
# posicao conferida (587.224,31 - 155.652,49) os 155.652,49 sao exatamente a
# soma das duas recompras do mesmo Athena ID (11.529,81 + 144.122,68). E o
# `Valor Base no registro` e o Notional do e-mail dividido pelo Strike. E por
# isso que o Notional do aviso NAO e o saldo: ele e o registrado na origem, e
# nao desconta recompra anterior nenhuma.

# O marcador do nocional fixo em reais e o codigo de moeda do Athena. 'BRL'
# entra junto porque o dia em que o Athena mandar o ISO a regra nao pode virar
# silenciosamente "nao e fixo em reais" — que e o caso que da valor errado.
CCY_FIXO_EM_REAIS = ('BRR', 'BRL')

_POS_COMPRADO = ('COMPRAD', 'COMPRA', 'LONG')
_POS_VENDIDO = ('VENDED', 'VENDA', 'SHORT')


def fixo_em_reais(antes):
    """A recompra e de um termo com nocional FIXO EM REAIS?"""
    return str(antes.get('Notional CCY', '') or '').strip().upper() in CCY_FIXO_EM_REAIS


def numero_flex(txt):
    """Numero que pode vir em formato BR ou US — o da POSICAO, que passa por
    formatacao de tela antes de chegar aqui.

    A regra e o ULTIMO separador manda: '587,224.31' e '587.224,31' sao os
    mesmos 587224.31. Com um separador so, tres digitas depois dele e milhar
    ('1,234' = 1234); qualquer outra quantidade e decimal ('1,5' = 1.5).
    O `numero()` continua existindo para o E-MAIL, que e sempre americano —
    misturar os dois leitores e como se perde um fator de mil sem erro."""
    t = str(txt or '').strip()
    if not t:
        return None
    neg = t.startswith('-') or (t.startswith('(') and t.endswith(')'))
    t = t.strip('()').lstrip('+-').strip()
    ult_v, ult_p = t.rfind(','), t.rfind('.')
    if ult_v >= 0 and ult_p >= 0:
        dec = max(ult_v, ult_p)
        t = t[:dec].replace(',', '').replace('.', '') + '.' + t[dec + 1:]
    elif ult_v >= 0 or ult_p >= 0:
        i = max(ult_v, ult_p)
        t = (t[:i] + t[i + 1:]) if len(t) - i - 1 == 3 else (t[:i] + '.' + t[i + 1:])
    try:
        v = float(_NUM_LIXO.sub('', t))
    except ValueError:
        return None
    return -v if neg else v


def comprado_na_posicao(pos):
    """True/False/None a partir de `Descricao da posicao do Participante`.

    `None` e "nao deu para dizer", e quem chama NAO assume nada: o sinal do
    resultado depende disto, e chutar inverte quem paga."""
    d = str((pos or {}).get('Descricao da posicao do Participante', '') or '').strip().upper()
    if not d:
        return None
    if any(t in d for t in _POS_COMPRADO):
        return True
    if any(t in d for t in _POS_VENDIDO):
        return False
    return None


def saldo_da_posicao(pos):
    """`Valor Base no registro` - `Valor Antecipado`, em moeda estrangeira.
    Sem o valor base nao ha saldo (None); sem antecipado, o antecipado e zero
    — posicao que nunca foi recomprada nao traz a coluna preenchida."""
    base = numero_flex((pos or {}).get('Valor Base no registro'))
    if base is None:
        return None
    return base - (numero_flex((pos or {}).get('Valor Antecipado')) or 0.0)


def notional_original_me(antes):
    """O nocional ORIGINAL em moeda estrangeira — o que vai no aviso. No fixo
    em reais divide pelo Strike, e o resultado e o `Valor Base no registro` da
    posicao (conferido: 3.055.856,61 / 5,2039 = 587.224,31)."""
    n = numero(antes.get('Notional'))
    if n is None:
        return None
    if not fixo_em_reais(antes):
        return n
    strike = numero(antes.get('Strike'))
    return (n / strike) if strike else None


def conta8(valor):
    """A conta CETIP nos seus OITO digitos. A mesma conta aparece
    '73760.10-2' num arquivo e '7376010 2' no outro, e o Live Position entrega
    a do Lawton como '41007' — sem os zeros nao casa com nada (§487). Irmao do
    `_acct8` do `platform/email_validation`, repetido aqui porque o `domain` e
    puro e nao importa camada de fora por duas linhas."""
    d = ''.join(ch for ch in str(valor or '') if ch.isdigit())
    return d.zfill(8) if d else ''


def dados_da_posicao(pos):
    """O que a posicao entrega ao aviso E ao arquivo, com um AVISO por coisa
    que faltou — nenhuma delas se inventa.

    **As duas contas saem daqui, nao de cadastro.** A recompra e de uma
    operacao JA REGISTRADA: a posicao carrega `Codigo da Parte` e `Codigo da
    Contraparte` exatamente como foram para a B3 no registro. Resolver conta
    por cadastro (a OWN do `b3-accounts`, o `B3 ACCOUNT` do Reference Data)
    seria refazer, por outro caminho e com outro risco, uma conta que ja esta
    respondida — e os dois cadastros nem concordam entre si para a nossa
    ponta. O nome e o CPF/CNPJ da contraparte vem pelo mesmo caminho, e e o
    que o aviso precisa: nenhuma busca por apelido."""
    avisos = []
    contrato = str((pos or {}).get('Contrato', '') or '').strip() or None
    moeda = str((pos or {}).get('Simbolo da Moeda', '') or '').strip().upper() or None
    conta_parte = conta8((pos or {}).get('Codigo da Parte')) or None
    conta_cpty = conta8((pos or {}).get('Codigo da Contraparte')) or None
    nome_cpty = str((pos or {}).get('Nome da Contraparte', '') or '').strip() or None
    taxid_cpty = str((pos or {}).get('CPF/CNPJ da Contraparte', '') or '').strip() or None
    comprado = comprado_na_posicao(pos)
    saldo = saldo_da_posicao(pos)
    for valor, code, texto in (
            (contrato, 'unwind_no_contract', 'The position has no B3 contract'),
            (moeda,    'unwind_no_currency', 'The position has no currency symbol'),
            (comprado, 'unwind_position_unknown', 'The position side (bought/sold) is unreadable'),
            (saldo,    'unwind_no_balance', 'The position has no registered base to compute the balance'),
            (conta_parte, 'unwind_no_participant_account', 'The position has no party account'),
            (conta_cpty, 'unwind_no_counterparty_account', 'The position has no counterparty account')):
        if valor is None:
            avisos.append({'code': code, 'params': {}, 'text': texto})
    return {'contrato': contrato, 'moeda': moeda, 'comprado': comprado,
            'saldo': saldo, 'conta_parte': conta_parte, 'conta_contraparte': conta_cpty,
            'nome_contraparte': nome_cpty, 'taxid_contraparte': taxid_cpty,
            'avisos': avisos}


# ==============================================================================
#  OS VALORES DO ARQUIVO DA B3  (TER 0014 — Antecipacao de Contrato a Termo)
# ==============================================================================
# Secao 4.9.3 do manual de Enviar Arquivos (versao 14/09/2026, pag. 730-732):
# posicional, 133 caracteres, tres blocos. O ARQUIVO e montado pelo motor do
# File Interpreter a partir do template `antecipacao-termo-multiclasses`; o que
# mora aqui sao os VALORES nomeados que o `Source: Page` de cada campo busca.
# Formato, posicao e preenchimento sao do motor — nunca se monta a linha a mao.
#
# As decisoes de cada campo, e de onde saiu cada uma:
#
#   4  Nº Controle Interno  -> numero proprio de 10 digitos, dado no import e
#                              preservado no re-import (o molde do Meu Numero
#                              do Swap Bullet)
#   5  Lancamento do Part.  -> `Codigo da Parte` da POSICAO. A recompra e de
#                              operacao JA REGISTRADA: a conta que foi para a
#                              B3 no registro esta na propria linha, e ler o
#                              cadastro seria arriscar divergir dela (o
#                              RefData tem o omnibus 73760.10-2 no nome do
#                              banco; a posicao entrega o proprio 73760.00-9)
#   6  Papel                -> 0 comprado / 1 vendido, da POSICAO
#   7  Contraparte          -> `Codigo da Contraparte` da POSICAO, pela mesma
#                              razao
#   8  Contrato             -> `Contrato` da posicao, pela ponte do identificador
#   9  Valor Base a Antecip.-> o nocional recomprado em MOEDA ESTRANGEIRA. No
#                              fixo em reais e o `Unwound Amount / Strike`: o
#                              contrato na B3 e em moeda estrangeira, e o
#                              `Valor Antecipado` da posicao (que e o acumulado
#                              destes campos) confere com a soma das recompras
#                              convertidas — 11.529,81 + 144.122,68 = 155.652,49
#  10  Data Antecipacao     -> HOJE
#  11  Data Liquidacao      -> HOJE
#  12  Taxa Termo           -> Termination Rate
#  13  Taxa Juros           -> Pre FWD Rate
#  14  Taxa de Cambio       -> 1 quando a TAXA TERMO e em reais (o arquivo sai
#                              '000100000000', que e o 9(04)V9(08) de
#                              1,00000000). So e diferente de 1 quando a taxa
#                              termo NAO e em BRL — mercadoria, por exemplo, em
#                              que o strike e em USD/bushel: ai vai a paridade
#                              USD/BRL. NAO e branco: um campo vazio aqui nao e
#                              "neutro", e um fator ausente
#  15  Liquidante           -> ESPACOS (a mesa nao preenche)
#  16  Qtd Datas de Verific.-> '000' quando o contrato nao tem media
#
# O bloco `registro-dados-variaveis` so existe para contrato com media
# (asiatico): sem datas de verificacao ele NAO sai.
TER_VERSAO_LAYOUT = '00002'
TER_CODIGO_OPERACAO = '0014'
TER_RECORD_LENGTH = 133      # o `record_length` do cadastro, conferido aqui

PAPEL_COMPRADO, PAPEL_VENDIDO = '0', '1'


def campos_ter_0014(antes, depois, posicao, hoje, conta_participante='',
                    conta_contraparte='', controle_interno='',
                    taxa_termo_em_brl=True, paridade=None):
    """Os valores nomeados do TER 0014 para o motor do File Interpreter.

    `hoje` e um `date`. Devolve (campos, avisos): campo que nao se pode
    responder sai como `None` e entra nos avisos — nunca como zero ou branco,
    que o motor mandaria para a B3 sem reclamar."""
    fixo = fixo_em_reais(antes)
    pos = dados_da_posicao(posicao)
    avisos = list(pos['avisos'])
    base = notional_me(antes, depois, fixo)
    if base is None:
        avisos.append({'code': 'unwind_no_base', 'params': {},
                       'text': 'Could not derive the unwound notional in foreign currency'})
    papel = None
    if pos['comprado'] is not None:
        papel = PAPEL_COMPRADO if pos['comprado'] else PAPEL_VENDIDO
    # As contas sao as da POSICAO — o `dados_da_posicao` ja avisou o que faltou.
    # Os parametros existem so para o chamador que precise sobrepor (a perna
    # espelhada do New Deals faz isso com o omnibus).
    conta_participante = conta8(conta_participante) or pos['conta_parte']
    conta_contraparte = conta8(conta_contraparte) or pos['conta_contraparte']
    # Campo 14: 1 com a taxa termo em reais; a paridade USD/BRL quando ela
    # esta em outra moeda (mercadoria). Sem a paridade no caso que a exige, o
    # campo fica None e avisa — mandar 1 ali multiplicaria o valor pela moeda
    # errada, calado.
    if taxa_termo_em_brl:
        taxa_cotada = 1.0
    else:
        taxa_cotada = paridade
        if taxa_cotada is None:
            avisos.append({'code': 'unwind_no_parity', 'params': {},
                           'text': 'The forward rate is not in BRL: the USD/BRL parity is required'})
    d = hoje.strftime('%Y%m%d')
    campos = {
        'Nº Controle Interno': str(controle_interno or '') or None,
        'Lançamento do Participante (Conta)': str(conta_participante or '') or None,
        'Papel (Posição do participante)': papel,
        'Contraparte': str(conta_contraparte or '') or None,
        'Contrato': pos['contrato'],
        'Valor Base a Antecipar': base,
        'Data Antecipação': d,
        'Data Liquidação': d,
        'Taxa Termo': numero(depois.get('Termination Rate')),
        'Taxa Juros': numero(depois.get('Pre FWD Rate')),
        'Taxa de Câmbio (R$/Moeda Cotada)': taxa_cotada,
        'Liquidante': '',                            # espacos, por decisao da mesa
        'Quantidade de Datas de Verificação': '000',
    }
    return campos, avisos


# ==============================================================================
#  DO VALOR NOMEADO PARA A LINHA DE 133 CARACTERES
# ==============================================================================
# O motor do File Interpreter (`_fi_build_line`) recebe os valores por SEQ, ja
# formatados na largura do campo — e o que ele faz sozinho e so completar com
# espacos o que vier curto. Quem formata numero posicional e quem chama, como
# faz o `_generic_ndf_ter_line` do New Deals. Aqui isso e uma funcao PURA, o
# que deixa o teste provar a linha inteira sem subir o app.
#
# O de-para seq -> nome vive ao lado do formato do MANUAL, e o teste confere os
# dois contra a `position` do cadastro: largura que discorde do cadastro
# deslocaria todos os campos seguintes sem mudar o tamanho da linha — o defeito
# que nao acusa.
TER_0014_LAYOUT = (
    ('4',  'Nº Controle Interno',                 '9(10)'),
    ('5',  'Lançamento do Participante (Conta)',  '9(08)'),
    ('6',  'Papel (Posição do participante)',     '9(01)'),
    ('7',  'Contraparte',                         '9(08)'),
    ('8',  'Contrato',                            'X(11)'),
    ('9',  'Valor Base a Antecipar',              '9(14)V9(02)'),
    ('10', 'Data Antecipação',                    '9(08)'),
    ('11', 'Data Liquidação',                     '9(08)'),
    ('12', 'Taxa Termo',                          '9(12)V9(08)'),
    ('13', 'Taxa Juros',                          '9(02)V9(08)'),
    ('14', 'Taxa de Câmbio (R$/Moeda Cotada)',    '9(04)V9(08)'),
    ('15', 'Liquidante',                          '9(08)'),
    ('16', 'Quantidade de Datas de Verificação',  '9(03)'),
)

_FMT_DEC = re.compile(r'^9\((\d+)\)V9\((\d+)\)$')
_FMT_NUM = re.compile(r'^9\((\d+)\)$')
_FMT_TXT = re.compile(r'^X\s*\((\d+)\)$')


def largura(formato):
    """Quantos caracteres o campo ocupa, pelo formato do manual."""
    m = _FMT_DEC.match(formato or '')
    if m:
        return int(m.group(1)) + int(m.group(2))
    for rx in (_FMT_NUM, _FMT_TXT):
        m = rx.match(formato or '')
        if m:
            return int(m.group(1))
    return None


def formatar_b3(valor, formato):
    """Um valor na largura e na convencao do campo posicional.

    `None` e `''` saem em BRANCO na largura — a B3 aceita campo opcional em
    branco, e e o que a mesa manda no Liquidante. Zero NAO e o mesmo que
    branco: `0` sai '00000000' e diz "zero", enquanto branco diz "nao se
    aplica". Numero que nao parseia devolve None, para o chamador avisar em
    vez de mandar zeros.
    """
    larg = largura(formato)
    if larg is None:
        return None
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return ' ' * larg
    m = _FMT_TXT.match(formato or '')
    if m:
        return str(valor)[:larg].ljust(larg)
    m = _FMT_DEC.match(formato or '')
    if not m:                       # 9(n) inteiro: conta, data, papel
        # A mascara do cadastro CETIP ('73760.00-9') nao passa por Decimal — e
        # e justamente a forma em que a conta chega da posicao.
        s = re.sub(r'\D', '', str(valor))
        return s.zfill(larg) if 0 < len(s) <= larg else None
    from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
    try:
        d = Decimal(str(valor).replace(',', '').strip())
    except (InvalidOperation, ValueError):
        return None
    if d < 0:                       # nenhum campo do 0014 e assinado
        d = -d
    inteiros, casas = int(m.group(1)), int(m.group(2))
    q = d.quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    ip = int(q)
    fp = int((q - ip).scaleb(casas))
    s = str(ip).zfill(inteiros) + str(fp).zfill(casas)
    return s if len(s) == larg else None          # estourou a largura: avisa


def valores_ter_0014(campos):
    """Os valores do `campos_ter_0014` na forma que o motor espera: `{seq:
    texto ja na largura}`. Devolve (valores, avisos).

    Campo que o `campos_ter_0014` nao soube responder (`None`) sai em BRANCO e
    entra nos avisos — a linha continua com os 133 caracteres para o preview
    mostrar onde esta o buraco, e quem envia RECUSA enquanto houver aviso.
    Mandar zeros seria a B3 aceitar um arquivo que ninguem conferiu."""
    valores, avisos = {}, []
    for seq, nome, formato in TER_0014_LAYOUT:
        bruto = (campos or {}).get(nome)
        texto = formatar_b3(bruto, formato)
        if texto is None:
            texto = ' ' * (largura(formato) or 0)
            avisos.append({'code': 'unwind_ter_campo_invalido',
                           'params': {'seq': seq, 'campo': nome,
                                      'valor': str(bruto)},
                           'text': 'Field {} ({}) does not fit the layout {}'.format(
                               seq, nome, formato)})
        elif bruto is None and nome != 'Liquidante':
            avisos.append({'code': 'unwind_ter_campo_vazio',
                           'params': {'seq': seq, 'campo': nome},
                           'text': 'Field {} ({}) has no value'.format(seq, nome)})
        valores[seq] = texto
    return valores, avisos


# ==============================================================================
#  A LINHA DA TELA
# ==============================================================================
# As colunas da pagina `/unwinds/ndf/fx`. Os rotulos nascem em INGLES e a tela
# os traduz pelo `data-lang`/`_TRANS` — aqui e so o par campo x rotulo, na
# ordem em que a grade os mostra.
# O `Status` vem PRIMEIRO: e a coluna que responde "esta linha ja foi?", e a
# grade tem dezoito colunas — no fim dela a resposta so aparece depois de
# rolar a tabela inteira, que e o mesmo que nao estar la. E a posicao que as
# paginas irmas usam (a Intrag Unwind a fixa logo depois das Acoes).
UNW_FIELDS = (
    'Status', 'AthenaID', 'Contract', 'Counterparty', 'TaxID', 'Currency',
    'OriginalNotional', 'UnwoundNotional', 'Strike', 'TerminationRate',
    'PreFWDRate', 'DU', 'Result', 'Direction', 'SettlementDate',
    'TradeDate', 'MaturityDate', 'BRLFixed', 'Check',
)
UNW_LABELS = (
    'Status', 'Athena ID', 'B3 ID', 'Counterparty', 'Tax ID', 'Ccy',
    'Original Notional', 'Unwound Notional', 'Strike', 'Termination Rate',
    'Pre FWD Rate', 'DU', 'Result', 'Direction', 'Settlement Date',
    'Trade Date', 'Maturity Date', 'BRL Fixed', 'Check',
)

# O ciclo da linha. `Imported` e o que o box scan grava; `Sent` e depois de o
# arquivo ir para o Batch Conecta.
#
# Entre os dois entra o 4-OLHOS da edicao, que e o mesmo das paginas de Intrag:
# editar a linha a poe em `Pending` e marca o MAKER; `Approved` e outro usuario
# conferindo. Uma linha `Pending` NAO e enviavel — edicao que ninguem conferiu
# indo para a B3 e exatamente o que o gate existe para segurar —, e por isso o
# `STATUS_ENVIAVEL` tem `Imported` (veio da maquina, intocada) e `Approved`
# (mexida e conferida), nunca `Pending`.
STATUS_NOVO, STATUS_ENVIADO = 'Imported', 'Sent'
STATUS_PENDENTE, STATUS_APROVADO = 'Pending', 'Approved'
STATUS_ENVIAVEL = (STATUS_NOVO, STATUS_APROVADO)

# O que a edicao de linha NAO toca. A chave, porque e por ela que a linha se
# acha; os dois veredictos, porque sao apurados e nao digitados; e o rastro do
# 4-olhos — quem edita nao escreve o proprio carimbo de conferido.
UNW_NAO_EDITAVEL = ('AthenaID', 'Check', 'Status', 'Maker', 'Checker',
                    'MyNumber', 'SentFiles', 'SentAt', 'Warnings',
                    'ImportedAt', 'PositionDate')

# O veredito da conferencia, para a coluna `Check`. Tres estados, como o
# `conferido` do `conferir_apuracao`: nao existe "deu certo por omissao".
CHECK_OK, CHECK_NOK, CHECK_NA = 'OK', 'NOK', '-'


def linha_da_recompra(rec, posicao, hoje, contrato=None):
    """A linha da tela a partir do registro do e-mail (`parse_notification`) e
    da linha do Live Position. Devolve (linha, avisos).

    Nao decide nada sozinha: o que o e-mail nao responde e a posicao nao
    completa sai VAZIO e entra nos avisos. `contrato` sobrepoe o da posicao
    (a ponte ja o achou pelo identificador)."""
    antes = dict((rec or {}).get('secoes', {}).get('before') or {})
    depois = dict((rec or {}).get('secoes', {}).get('after') or {})
    pos = dados_da_posicao(posicao)
    avisos = list((rec or {}).get('avisos') or []) + list(pos['avisos'])
    fixo = fixo_em_reais(antes)
    conf = conferir_apuracao(antes, depois, fixo, pos['comprado'])
    avisos.extend(conf['avisos'])
    veredito = {True: CHECK_OK, False: CHECK_NOK}.get(conf['conferido'], CHECK_NA)
    linha = {
        'AthenaID': (rec or {}).get('athena_id') or '',
        'NotificationID': (rec or {}).get('notification_id') or '',
        'Contract': contrato or pos['contrato'] or '',
        'Counterparty': pos['nome_contraparte'] or '',
        'TaxID': pos['taxid_contraparte'] or '',
        'ClientAcronym': depois.get('Client') or '',
        'Currency': pos['moeda'] or '',
        'NotionalCCY': antes.get('Notional CCY') or '',
        'BRLFixed': 'YES' if fixo else 'NO',
        'OriginalNotional': notional_original_me(antes),
        # O nocional recomprado NAO depende do lado da posicao: e o
        # `Unwound Amount` (dividido pelo strike no fixo em reais). Lendo-o
        # do resultado da conferencia, a coluna ficava VAZIA sempre que a
        # posicao nao resolvia o lado — e e exatamente aí que a mesa precisa
        # ver o numero para entender o que falta.
        'UnwoundNotional': notional_me(antes, depois, fixo),
        'UnwoundAmount': depois.get('Unwound Amount') or '',
        'Strike': numero(antes.get('Strike')),
        'TerminationRate': numero(depois.get('Termination Rate')),
        'PreFWDRate': numero(depois.get('Pre FWD Rate')),
        'DU': numero(depois.get('DU')),
        'Result': resultado_apurado(depois),
        # A direcao e a do SINAL do resultado, nunca o campo `Direction` do
        # e-mail: na amostra fixa em reais ele dizia PAY numa recompra a
        # RECEBER. O campo do e-mail fica guardado para a conferencia.
        # O LADO da posicao (comprado/vendido) e o SINAL do resultado sao
        # duas coisas, e confundi-las inverte o campo 6 do arquivo: nesta
        # amostra o banco esta VENDIDO e RECEBE. O lado vem da posicao e fica
        # guardado; a direcao e so o sinal.
        'Comprado': pos['comprado'],
        'Direction': conf['direcao_calc'] or '',
        'EmailDirection': depois.get('Direction') or '',
        'TradeDate': antes.get('Trade Date') or '',
        'MaturityDate': antes.get('Maturity Date') or '',
        'SettlementDate': hoje.strftime('%Y-%m-%d'),
        'PartyAccount': pos['conta_parte'] or '',
        'CptyAccount': pos['conta_contraparte'] or '',
        'Balance': pos['saldo'],
        'Check': veredito,
        'Status': STATUS_NOVO,
        'Warnings': _codigos(avisos),
    }
    return linha, avisos


def _codigos(avisos):
    """Os codigos dos avisos, sem repetir e na ordem em que apareceram — a
    posicao ausente e vista pelo leitor da posicao E pela conferencia, e a
    mesma frase duas vezes na tela nao diz nada a mais."""
    vistos, out = set(), []
    for a in avisos or []:
        c = a.get('code')
        if c and c not in vistos:
            vistos.add(c)
            out.append(c)
    return out


# ==============================================================================
#  O TERMO DE RESILIÇÃO  (o distrato da operação recomprada)
# ==============================================================================
# O documento que as duas Partes assinam pela recompra. O corpo é texto fixo
# (o Word que a mesa redigiu); o que muda é o **Anexo I**, uma linha por
# operação resilida com sete colunas:
#
#   Confirmação nº            -> o **Athena ID** (decisão da mesa, 18/09/2026):
#                                é por ele que a confirmação da operação
#                                original se identifica, e é o número que chega
#                                no aviso de recompra
#   Registro CETIP nº         -> o contrato na B3, que a ponte do identificador
#                                achou na posição
#   Resilição                 -> Total ou Parcial, pela comparação do
#                                recomprado com o SALDO da posição
#   Valor Base Liquidado      -> o nocional recomprado, em moeda ESTRANGEIRA
#                                (é o campo 9 do TER 0014 — o mesmo número que
#                                foi para a B3, e não o nocional original)
#   Valor de Resilição        -> o resultado apurado, em REAIS, em módulo: a
#                                coluna ao lado é que diz quem paga
#   Pagador do Valor de Res.  -> Parte A (nós) ou Parte B (a contraparte), pelo
#                                SINAL do resultado, nunca pelo `Direction` do
#                                e-mail (§488)
#   Novo Valor Base           -> o que sobra do saldo depois desta recompra;
#                                na resilição TOTAL não se aplica
#
# Nada aqui se inventa: o que a recompra não responde sai VAZIO e entra nos
# avisos — um documento assinado com um número plausível e errado é pior que um
# campo que a mesa tem de preencher.
RESILICAO_TOTAL = 'Total'
RESILICAO_PARCIAL = 'Parcial'
NAO_APLICAVEL = 'Não Aplicável'
# Um centavo de moeda estrangeira: o saldo da posição e o recomprado vêm de
# arredondamentos diferentes (a posição imprime 2 casas), e uma recompra que
# zera o contrato pode fechar em 587.224,31 contra 587.224,3099.
TOL_SALDO = 0.01

PAGADOR_PARTE_A = 'Parte A'
PAGADOR_PARTE_B = 'Parte B'


def num_br(valor, casas=2):
    """Número no formato do documento (milhar '.', decimal ','). Irmão do
    `_conf_fmt_num` da platform, repetido aqui porque o `domain` é puro e não
    importa camada de fora por cinco linhas — como o `conta8` acima."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return ''
    v = valor if isinstance(valor, (int, float)) else numero_flex(valor)
    if v is None:
        return str(valor).strip()
    s = '{:,.{d}f}'.format(v, d=casas)
    return s.replace(',', '\x00').replace('.', ',').replace('\x00', '.')


def recompra_total(linha):
    """A recompra encerra o contrato? True / False / **None** (não dá para
    dizer, porque a posição não trouxe o saldo).

    A resposta serve o Termo de Resilição (Total × Parcial) E a planilha da
    Intrag (a Situação), e por isso mora numa função só."""
    recomprado = numero_flex((linha or {}).get('UnwoundNotional'))
    saldo = numero_flex((linha or {}).get('Balance'))
    if recomprado is None or saldo is None:
        return None
    return recomprado >= saldo - TOL_SALDO


def termo_linha(linha):
    """Uma linha do Anexo I a partir da linha da recompra. -> (row, avisos)."""
    avisos = []
    athena_id = str((linha or {}).get('AthenaID') or '').strip()
    contrato = str((linha or {}).get('Contract') or '').strip()
    if not contrato:
        avisos.append({'code': 'unwind_termo_sem_contrato',
                       'params': {'athena_id': athena_id},
                       'text': 'Recompra sem contrato da B3 — a coluna Registro CETIP nº '
                               'sai vazia'})
    moeda = str((linha or {}).get('Currency') or '').strip()
    recomprado = numero_flex((linha or {}).get('UnwoundNotional'))
    saldo = numero_flex((linha or {}).get('Balance'))
    resultado = numero_flex((linha or {}).get('Result'))
    direcao = str((linha or {}).get('Direction') or '').strip().upper()

    # Total x Parcial: o saldo da posição é o que ainda está aberto ANTES desta
    # recompra. A pergunta é UMA (`recompra_total`) porque a resposta vai em
    # dois lugares — a cláusula do Termo e a Situação da planilha da Intrag —,
    # e duas leituras do mesmo saldo é como os dois documentos passariam a
    # discordar sobre o contrato estar encerrado.
    total = recompra_total(linha)
    if total is None:
        tipo, novo_base = '', ''
        avisos.append({'code': 'unwind_termo_sem_saldo',
                       'params': {'athena_id': athena_id},
                       'text': 'Sem o saldo da posição não dá para dizer se a resilição é '
                               'total ou parcial — preencha a coluna no painel'})
    elif total:
        tipo, novo_base = RESILICAO_TOTAL, NAO_APLICAVEL
    else:
        tipo = RESILICAO_PARCIAL
        novo_base = '{} {}'.format(moeda, num_br(saldo - recomprado)).strip()

    # O pagador é o SINAL do resultado: recebemos -> paga a Parte B.
    if direcao == 'RECEIVE':
        pagador = PAGADOR_PARTE_B
    elif direcao == 'PAY':
        pagador = PAGADOR_PARTE_A
    else:
        pagador = ''
        avisos.append({'code': 'unwind_termo_sem_direcao',
                       'params': {'athena_id': str((linha or {}).get('AthenaID') or '')},
                       'text': 'Resultado sem sinal apurado — preencha o pagador no painel'})

    return {
        # Confirmação nº é o Athena ID, não o B3 ID: é o número pelo qual a
        # confirmação da operação original se identifica (decisão da mesa).
        'numConf':        athena_id,
        'registroCetip':  contrato,
        'resilicao':      tipo,
        'valorBaseLiq':   '{} {}'.format(moeda, num_br(recomprado)).strip() if recomprado is not None else '',
        # O Valor de Resilição vai em MÓDULO: quem paga está na coluna ao lado,
        # e um valor negativo ali leria como se a Parte pagasse um valor
        # negativo — que é o mesmo que receber.
        'valorResilicao': 'R$ {}'.format(num_br(abs(resultado))) if resultado is not None else '',
        'pagador':        pagador,
        'novoValorBase':  novo_base,
    }, avisos


def termo_rows(linhas):
    """As linhas do Anexo I de um grupo de recompras. -> (rows, avisos)."""
    rows, avisos = [], []
    for l in linhas or []:
        row, av = termo_linha(l)
        rows.append(row)
        avisos.extend(av)
    return rows, avisos
