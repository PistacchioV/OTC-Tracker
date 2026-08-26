# -*- coding: utf-8 -*-
"""Materializar em disco os cadastros que o motor lê — e por que isso existe."""

# Os dois cadastros que decidem o que SAI do batimento antes do merge.
CADASTROS = ('fxo-internal-cpty', 'fxo-book-disregard')


def seed_registries():
    """Toca os dois cadastros da recon só para o SEED ir para o disco.

    O motor lê o JSON **direto** — importar o `routes` de lá seria circular — e
    por isso não tem como semear. Sem este toque, na instância em que ninguém
    abriu a tela de `/mapping` o arquivo não existe, o cadastro volta vazio e as
    regras de exclusão simplesmente não valem: a recon roda, responde 200, e
    mostra como quebra a perna interna que o cadastro mandava tirar. Nada no
    log, nada na tela.

    Ver a nota em `features/support/infra/persistence.py` sobre a busca
    ATRASADA: o `_mapping_rows` ainda é do `routes`, e 61 testes trocam
    atributos lá.
    """
    from apps.pages import routes
    for chave in CADASTROS:
        routes._mapping_rows(chave)
