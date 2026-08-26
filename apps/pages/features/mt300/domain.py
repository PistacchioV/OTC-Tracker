# -*- coding: utf-8 -*-
"""As regras da mensagem — puras: os dois lados chegam JÁ normalizados."""

# O Cc nasce com a caixa do OTC Ops: a mesa acompanha toda mensagem do grupo.
CC_DEFAULT = 'brazil.otc.ops@jpmorgan.com'
TIME = (19, 30)


def subject(ref):
    return 'MT300 - {}'.format(ref.strftime('%d/%m/%Y'))


def matches(cnpj, spn, nome, alvos):
    """O deal é de alguém da lista? Os três identificadores chegam normalizados
    (dígitos do CNPJ, SPN sem zeros, nome achatado), e basta UM casar.

    O CNPJ vem primeiro porque é o único que não muda de grafia — o mesmo
    cliente chega como 'NESTLE BRASIL LTDA' num arquivo e 'NESTLE BRASIL LTDA.'
    noutro, e o SPN às vezes vem vazio. O nome é o último recurso, por TOKENS
    (todas as palavras presentes), que é o que sobrevive ao ponto final e ao 'E'
    que some do meio.
    """
    for a_cnpj, a_spn, a_tokens in alvos:
        if a_cnpj and cnpj and a_cnpj == cnpj:
            return True
        if a_spn and spn and a_spn == spn:
            return True
        if a_tokens and nome and all(t in nome for t in a_tokens):
            return True
    return False


def position(d):
    """`JPM buys USD / sells BRL` — a operação por extenso.

    Os dois verbos são SEMPRE opostos: comprar uma moeda do par é vender a
    outra, e escrevê-los de forma independente abriria espaço para a linha dizer
    que a mesa comprou as duas. A direção é a do deal; as moedas são a do
    Quantity e a do Other Quantity, na mesma ordem em que as colunas aparecem.
    """
    le = str(d.get('LE', '') or '').strip().upper() or 'JPM'
    qty_ccy = str(d.get('QuantityCurrency', '') or '').strip()
    other_ccy = str(d.get('OtherQuantityCurrency', '') or '').strip()
    if not qty_ccy or not other_ccy:
        return ''
    compra = 'BUY' in str(d.get('Direction', '') or '').upper()
    v1, v2 = ('buys', 'sells') if compra else ('sells', 'buys')
    return '{} {} {} / {} {}'.format(le, v1, qty_ccy, v2, other_ccy)


def signed_qty(qty, direction):
    """O SINAL vem da DIREÇÃO da operação, não do arquivo: o notional é gravado
    sempre positivo, e no MT300 a venda é negativa. Sem isto as duas pontas do
    mesmo trade sairiam idênticas na mensagem."""
    if qty is not None and 'SELL' in str(direction or '').upper():
        return -qty
    return qty
