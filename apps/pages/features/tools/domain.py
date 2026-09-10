# -*- coding: utf-8 -*-
"""As regras puras das Tools: ler número de formulário e classificar uma ponta.

Sem Flask, sem rede, sem arquivo. O que o domínio precisa saber do mundo (as
linhas do cadastro, as células da posição) chega por parâmetro.
"""
import re
import unicodedata

from apps.pages.precificador import contagem, liquidacao
from apps.pages.precificador.calendario import para_data
from apps.pages.precificador.erros import ErroFerramenta


class ErroFormulario(ErroFerramenta, ValueError):
    """Campo em branco ou que não é número — a tela mostra o motivo."""


def decimal(texto, campo, padrao=None):
    """Lê um número aceitando o padrão americano E o brasileiro.

    Os campos voltam do navegador já formatados (`10,000,000.00`, `14.0000 %`),
    e quem digita pode escrever `1.500,50`. A regra é a mesma do `tools.js`:

    * vírgula e ponto juntos → o ÚLTIMO separador é o decimal;
    * só vírgula → decimal;
    * vários pontos → todos milhar;
    * um ponto só → decimal.
    """
    texto = str(texto or '').strip().replace('%', '').replace(' ', '').replace(' ', '')
    if not texto:
        if padrao is None:
            raise ErroFormulario('fill in the {campo} field', campo=campo)
        return padrao
    if ',' in texto and '.' in texto:
        if texto.rfind(',') > texto.rfind('.'):
            normalizado = texto.replace('.', '').replace(',', '.')
        else:
            normalizado = texto.replace(',', '')
    elif ',' in texto:
        normalizado = texto.replace(',', '.')
    elif texto.count('.') > 1:
        normalizado = texto.replace('.', '')
    else:
        normalizado = texto
    try:
        return float(normalizado)
    except ValueError:
        raise ErroFormulario('{campo}: "{texto}" is not a number', campo=campo, texto=texto) from None


def numero_do_form(valores, campo, rotulo, padrao=None):
    """Número solto (notional, preço) — sem conversão de percentual."""
    return decimal(valores.get(campo), rotulo, padrao)


def taxa_do_form(valores, campo, rotulo, padrao=None):
    """Aceita 17, 17%, 0.17 — sempre devolve decimal."""
    bruto = str(valores.get(campo) or '').strip()
    numero = decimal(bruto, rotulo, padrao)
    return numero / 100.0 if abs(numero) >= 1.0 or '%' in bruto else numero


def fx8(valor):
    """Cotação de moeda como texto: no mínimo 4 casas (a PTAX é publicada com
    4), no máximo 8 (a precisão que a mesa usa), sem zeros inventados à
    direita — '5.1253' fica '5.1253', 5.12345678 fica inteiro (§439)."""
    s = '{:.8f}'.format(float(valor))
    inteiro, dec = s.split('.')
    dec = dec.rstrip('0')
    return inteiro + '.' + (dec + '0000')[:4] if len(dec) < 4 else inteiro + '.' + dec


def ligado(valores, campo):
    return str(valores.get(campo) or '').lower() in ('1', 'on', 'true')


def texto_data(valores, campo):
    """ISO ou dd/mm/aaaa → `date`; vazio → None."""
    v = str(valores.get(campo) or '').strip()
    return para_data(v) if v else None


def ponta_do_form(form, prefixo):
    """Uma das duas pontas da liquidação — só os campos que o índice usa."""
    def campo(nome):
        return '{}_{}'.format(prefixo, nome)

    def texto(nome):
        return str(form.get(campo(nome)) or '').strip()

    def opcional(nome, rotulo):
        return numero_do_form(form, campo(nome), rotulo) if texto(nome) else None

    indexador = form.get(campo('indexador')) or liquidacao.PRE
    lado = 'receiving' if prefixo == 'ativa' else 'paying'
    taxa = 0.0
    if indexador != liquidacao.FATOR:
        taxa = taxa_do_form(form, campo('taxa'), '{} leg rate'.format(lado), 0.0)
    # No CDI a taxa é o SPREAD e o percentual é campo próprio: a posição traz os
    # dois na mesma perna (100% do CDI + 1,07%), e um campo só não os expressa.
    # `100` e `1.10` valem a mesma coisa — quem digita escreve dos dois jeitos.
    percentual = 1.0
    if indexador == liquidacao.CDI and texto('percentual'):
        bruto = numero_do_form(form, campo('percentual'), '{} leg % of CDI'.format(lado))
        percentual = bruto / 100.0 if abs(bruto) > 5 else bruto
    return liquidacao.Ponta(
        indexador=indexador, taxa=taxa, percentual=percentual,
        convencao=form.get(campo('convencao')) or contagem.DU_252,
        regime=form.get(campo('regime')) or contagem.COMPOSTO,
        moeda=form.get(campo('moeda')) or liquidacao.SEM_CONVERSAO,
        ptax_inicial=opcional('ptax_inicial', '{} leg initial fixing'.format(lado)),
        ptax_final=opcional('ptax_final', '{} leg final fixing'.format(lado)),
        ni_inicial=opcional('ni_inicial', '{} leg initial index number'.format(lado)),
        ni_final=opcional('ni_final', '{} leg final index number'.format(lado)),
        fator_manual=opcional('fator', '{} leg factor'.format(lado)),
        ativo=texto('ativo'),
        preco_inicial=opcional('preco_inicial', '{} leg initial price'.format(lado)),
        preco_final=opcional('preco_final', '{} leg final price'.format(lado)),
        tenor=form.get(campo('tenor')) or '3 month',
        data_fixing=para_data(texto('data_fixing')) if texto('data_fixing') else None,
        taxa_indice=(taxa_do_form(form, campo('taxa_indice'), '{} leg fixing rate'.format(lado))
                     if texto('taxa_indice') else None),
        lookback=int(texto('lookback') or 0), shift=int(texto('shift') or 0))


# ── o pré-preenchimento pela posição de swap ────────────────────────────────

def norm(s):
    """Minúsculas sem acento, espaços colapsados — como o `_fcst_norm`."""
    s = unicodedata.normalize('NFKD', str(s or '').lower())
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(s.split())


def classificar_indice(regras, nome_curva, nome_classe=''):
    """A regra do cadastro `tools-swap-index` que casa com a curva da ponta.

    ``nome_curva`` é o Nome Curva do `swap-index` (DI, PREFIXADO 252D, DOLAR
    DOS EUA…). Quando ele é **VCP** a curva de verdade está no Nome Tipo/Classe
    da posição (``nome_classe``) — é isso que a mesa pediu: "se estiver como
    VCP, pegar a informação da coluna Nome Tipo/Classe".

    Precedência: `Exact` vence `Contains`, e entre os `Contains` vence o token
    mais longo — `DOLAR DOS EUA 30/360` tem de ganhar de `DOLAR`. Sem regra →
    ``None``, e a tela deixa o índice em branco, sinalizado.

    O Nome Tipo/Classe é tentado em DOIS casos, não só no VCP: quando a curva
    não casa com regra nenhuma ele volta como segunda pergunta. Um `Código
    índice` que o `swap-index` não conhece chega aqui como o próprio código
    (`C03`), que não casa com nada — e desistir ali deixaria a ponta em branco
    tendo a curva escrita na coluna ao lado."""
    alvos = []
    for candidato in (nome_curva, nome_classe):
        n = norm(candidato)
        if n and n != 'vcp' and n not in alvos:
            alvos.append(n)
    for alvo in alvos:
        exatas, contidas = [], []
        for r in regras or []:
            tok = norm(r.get('MATCH', ''))
            if not tok:
                continue
            modo = norm(r.get('MODE', '')) or 'contains'
            if modo.startswith('exact'):
                if tok == alvo:
                    exatas.append(r)
            elif tok in alvo:
                contidas.append(r)
        if exatas:
            return exatas[0]
        if contidas:
            return max(contidas, key=lambda r: len(norm(r.get('MATCH', ''))))
    return None


def numero_da_posicao(v):
    """Célula numérica do arquivo de posição (vírgula DECIMAL, sem milhar)."""
    s = str(v or '').strip()
    if not s:
        return None
    try:
        return float(s.replace(' ', '').replace(',', '.'))
    except ValueError:
        return None


def sinal_da_posicao(v):
    """'1' (ou '-') é negativo; o resto, positivo."""
    s = str(v or '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    return -1.0 if s in ('1', '01', '-') else 1.0


def base_da_amortizacao(texto):
    """O `Tipo Amortização` do fluxo → a base do Swap Calculator, ou `None`.

    A coluna tem quatro respostas no cadastro `swap-amortizacao`, e duas delas
    NÃO são uma base — são a ausência de amortização neste fluxo:

        Sobre Valor Base Original      → base = original
        Sobre Valor Base Remanescente  → base = remanescente
        Na Data de Vencimento          → só amortiza no fim; no fluxo, nada
        Sem Troca de Amortização       → não amortiza

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
        # Não amortiza nunca: aqui o original é o default histórico da tela, e
        # com o percentual em zero ele não muda número nenhum.
        return liquidacao.SOBRE_ORIGINAL
    return None


def amortiza_no_fluxo(texto):
    """O fluxo amortiza? `Na Data de Vencimento` e `Sem Troca de Amortização`
    dizem que não — e é resposta, não lacuna."""
    t = norm(texto)
    if not t:
        return None
    return not ('vencimento' in t or 'sem troca' in t)


def tipo_de_contrato(valor):
    """`Tipo de Contrato` da posição → 'Bullet' | 'Cashflow' | ''.

    A B3 escreve `02` para bullet e `01` para cashflow, com zero à esquerda e
    às vezes com cauda decimal do Excel — a mesma normalização do Live
    Position, para as duas telas lerem o arquivo do mesmo jeito.
    """
    v = str(valor or '').strip()
    if v.endswith('.0'):
        v = v[:-2]
    if v.isdigit():
        v = str(int(v))
    return {'2': 'Bullet', '1': 'Cashflow'}.get(v, '')


def tenor_do_texto(texto, padrao=None):
    """`TSFR3M` / `EURIBOR 6M` / `3 month` → o tenor da tela ('3 month')."""
    t = norm(texto)
    m = re.search(r'(\d+)\s*m\b|(\d+)\s*month|(\d+)\s*mes', t)
    if m:
        n = int(next(g for g in m.groups() if g))
        return {1: '1 month', 3: '3 month', 6: '6 month', 12: '12 month'}.get(n, padrao)
    if '1 week' in t or 'semana' in t or '1w' in t:
        return '1 week'
    return padrao


def montar_ponta(regra, pct, taxa, sinal, nome_classe, cotacao_inicial,
                 deslocamento=None):
    """Os campos de UMA ponta do formulário a partir das células da posição.

    Devolve ``(campos, faltando)``: os campos prontos para o formulário e a
    lista do que não deu para puxar — a tela deixa esses em branco e os
    sinaliza. Nunca inventa: índice sem regra fica vazio, moeda sem coluna fica
    vazia, cotação inicial sem célula fica vazia."""
    campos = {'indexador': '', 'taxa': '', 'percentual': '', 'convencao': '', 'regime': '',
              'moeda': '', 'tenor': '', 'taxa_indice': '', 'ptax_inicial': '',
              'ptax_final': '', 'ptax_offset': '', 'ni_inicial': '', 'preco_inicial': '',
              'ativo': ''}
    faltando = []
    if not regra:
        return campos, ['indexador']
    idx = str(regra.get('INDEX', '') or '').strip()
    if idx not in liquidacao.INDEXADOR_POR_CODIGO:
        # Índice que o MOTOR não conhece é o mesmo que índice nenhum, e tem de
        # sair pela mesma porta: a ponta em branco e SINALIZADA. Devolvê-lo
        # punha no `<select>` da tela um valor sem opção correspondente — o
        # campo ficava vazio, a nota de "não identificou" não aparecia (o
        # servidor tinha respondido um índice) e não havia nada explicando o
        # branco. O cadastro é editado à mão numa tela cujo `select` pode
        # guardar o valor de um seed antigo (foi o `cdi_percentual`, código da
        # Renda Fixa, no primeiro seed do `tools-swap-index`).
        return campos, ['indexador']
    campos['indexador'] = idx
    conv, reg = liquidacao.convencao_padrao(idx)
    campos['convencao'] = str(regra.get('DAY COUNT', '') or '').strip() or conv
    campos['regime'] = str(regra.get('REGIME', '') or '').strip() or reg
    # No CDI as duas colunas da posição entram em campos DIFERENTES: o
    # `Percentual` no percentual e a `Taxa` (com o `Sinal Taxa`) no spread. A
    # perna sem spread deixa o campo vazio — zero afirmaria um spread de zero,
    # e vazio é o que a posição de fato traz.
    if idx == liquidacao.CDI:
        if pct is None:
            faltando.append('percentual')
        else:
            campos['percentual'] = '{:.4f}'.format(pct)
        campos['taxa'] = '' if taxa is None else '{:.4f}'.format(taxa * sinal)
    else:
        valor = 0.0 if idx in (liquidacao.MOEDA, liquidacao.FATOR) else (
            (taxa * sinal) if taxa is not None else None)
        if valor is None:
            faltando.append('taxa')
        else:
            campos['taxa'] = '{:.4f}'.format(valor)
    # a moeda, onde o índice declara uma
    if idx in liquidacao.DECLARAM_MOEDA:
        moeda = str(regra.get('CURRENCY', '') or '').strip().upper() \
            or liquidacao.MOEDA_DO_INDEXADOR.get(idx, '')
        if moeda:
            campos['moeda'] = moeda
        else:
            faltando.append('moeda')
    if idx in liquidacao.COM_FIXING:
        tenor = (str(regra.get('TENOR', '') or '').strip()
                 or tenor_do_texto(nome_classe) or '')
        if tenor:
            campos['tenor'] = tenor
        else:
            faltando.append('tenor')
    # a cotação inicial do ativo — a coluna "Cupom Limpo" da posição
    if idx in liquidacao.COM_MOEDA:
        if cotacao_inicial is not None:
            campos['ptax_inicial'] = fx8(cotacao_inicial)
        else:
            faltando.append('ptax_inicial')
        # A `Data de Cotação` ao lado NÃO é uma data: é o DESLOCAMENTO em dias
        # úteis (02 = D-2) da PTAX que o contrato manda usar. Guardá-la como
        # data faria o campo mostrar 02/01/1900 sem erro nenhum.
        if deslocamento is None:
            faltando.append('ptax_offset')
        else:
            campos['ptax_offset'] = str(int(deslocamento))
    elif idx == liquidacao.IPCA:
        if cotacao_inicial is not None:
            campos['ni_inicial'] = '{:.6f}'.format(cotacao_inicial)
        else:
            faltando.append('ni_inicial')
    elif idx == liquidacao.EQUITY:
        campos['ativo'] = str(nome_classe or '').strip()
        if cotacao_inicial is not None:
            campos['preco_inicial'] = '{:.6f}'.format(cotacao_inicial)
        else:
            faltando.append('preco_inicial')
    return campos, faltando
