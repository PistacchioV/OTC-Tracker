# -*- coding: utf-8 -*-
"""As escritas das Tools: o import do Term SOFR e as sincronizações."""
from apps.pages.precificador import euribor, sofr, term_sofr


def importar_term_sofr(nome, dados):
    """Recebe o relatório da B3 e guarda as cotações de Term SOFR."""
    resultado = term_sofr.importar(nome, dados)
    return {
        'ok': True, 'file': nome,
        'rows_read': resultado.linhas_lidas, 'used': resultado.aproveitadas,
        'new': resultado.novas, 'updated': resultado.atualizadas,
        'start': resultado.inicio.isoformat() if resultado.inicio else None,
        'end': resultado.fim.isoformat() if resultado.fim else None,
        'tickers': resultado.tickers, 'ignored': resultado.ignorados,
    }


def sincronizar_sofr():
    """A carga profunda do NY Fed — desde 2018, ano a ano."""
    return sofr.sincronizar(profundo=True)


def sincronizar_euribor():
    """A carga profunda do Banco da Finlândia (~50 requisições)."""
    return euribor.sincronizar(profundo=True, passo=5)
