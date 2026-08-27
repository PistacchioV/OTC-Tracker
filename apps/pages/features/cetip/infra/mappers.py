# -*- coding: utf-8 -*-
"""Cabeçalho do arquivo B3 → índice de coluna. O nome da coluna é procurado
normalizado (`_fcst_norm`), com `avoid` para o caso em que um nome é SUBSTRING
do outro ('parte (conta)' dentro de 'contraparte (conta)') — sem ele o filtro
compararia a mesma coluna duas vezes e deixaria passar conta externa.
"""
def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _cetip_bacc_col(header, spec):
    """Índice da coluna da parte (ou da contraparte) no arquivo salvo.

    Pelo NOME quando o arquivo traz cabeçalho; pelo índice quando não traz (aí o
    cabeçalho é o padrão do código — `_B3_SWAP_HEADERS` —, e resolver por nome não
    acrescentaria nada). O índice também é o último recurso quando o nome não casa,
    que é o mesmo desenho do `_b3_filter_rows`.

    `avoid` descarta a coluna cujo nome contenha aquele texto, e não é zelo: em
    `'contraparte (conta)'` cabe `'parte (conta)'` inteiro, então sem ele o lado da
    parte casaria com a coluna da contraparte quando ela vem antes no cabeçalho — o
    filtro compararia a MESMA coluna duas vezes e deixaria passar linha de cliente.
    """
    if header:
        alvo = [_R()._fcst_norm(t) for t in (spec.get('column') or [])]
        evitar = _R()._fcst_norm(spec.get('avoid', ''))
        nomes = [(i, _R()._fcst_norm(h)) for i, h in enumerate(header)]
        ok = lambda n: not (evitar and evitar in n)
        for t in alvo:
            for i, n in nomes:                       # nome exato primeiro
                if n == t and ok(n):
                    return i
        for t in alvo:
            for i, n in nomes:                       # depois por conteúdo
                if t and t in n and ok(n):
                    return i
    idx = spec.get('index')
    return idx if isinstance(idx, int) and idx >= 0 else None
