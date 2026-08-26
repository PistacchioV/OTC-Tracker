# -*- coding: utf-8 -*-
"""O estado do banco do CGD — que aqui é uma pergunta só, e ela importa."""
import os

from apps.pages import cgd_docs


def db_ready():
    """(existe?, caminho).

    O caminho volta JUNTO, e não é zelo: a tela o mostra quando o arquivo não
    existe. Sem ele, *"nenhum documento"* é indistinguível de *"o script de
    importação nunca rodou nesta instância"* — e as duas se resolvem de jeitos
    opostos. O banco está no `.gitignore`, então o segundo caso é o normal num
    checkout novo.
    """
    return os.path.isfile(cgd_docs.DB_PATH), cgd_docs.DB_PATH
