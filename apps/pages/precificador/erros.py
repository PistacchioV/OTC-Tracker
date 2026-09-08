# -*- coding: utf-8 -*-
"""A base comum das falhas do motor — molde separado dos valores.

Toda fonte que o motor consulta (BCB, NY Fed, Banco da Finlândia) tem a sua
exceção, e cada uma diz qual fonte falhou e por quê. As telas capturam a BASE
(`ErroDeFonte`) — assim uma fonte nova, ou uma rota que passa a usar uma fonte
que antes não usava, não escapa para um traceback.

O molde fica separado dos valores de propósito: uma frase já montada com a
data dentro não serve de chave para nada, e ``str(exc)`` continua devolvendo a
frase pronta para o log e para a tela.
"""


class ErroFerramenta(Exception):
    """Erro com molde e valores; ``str()`` devolve a frase montada."""

    def __init__(self, molde, **valores):
        self.molde = molde
        self.valores = valores
        super().__init__(montar(molde, valores))

    @classmethod
    def de(cls, exc):
        """Reembrulha um erro de baixo sem achatá-lo em texto."""
        molde, valores = partes(exc)
        return cls(molde, **valores)


def montar(molde, valores):
    """A frase montada, ou o molde cru quando os valores não fecham — um
    ``KeyError`` dentro do ``raise`` apagaria o erro de verdade."""
    if not valores:
        return molde
    try:
        return molde.format(**valores)
    except (KeyError, IndexError, ValueError):
        return molde


def partes(exc):
    """``(molde, valores)`` de qualquer exceção — a que não tem molde devolve
    a própria frase, sem valores."""
    molde = getattr(exc, 'molde', None)
    if molde is None:
        return str(exc), {}
    return molde, getattr(exc, 'valores', {}) or {}


class ErroDeFonte(ErroFerramenta, RuntimeError):
    """Falha ao obter dado de uma fonte externa — toda fonte herda desta."""


class ErroDeDado(ErroFerramenta, ValueError):
    """Dado de entrada que não fecha. Herda de ``ValueError`` porque as
    rotas capturam ``ValueError`` — o tipo continua o mesmo para quem
    captura, e ganha o molde para quem exibe."""
