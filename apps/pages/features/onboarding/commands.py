# -*- coding: utf-8 -*-
"""As escritas do Onboarding: gravar e apagar, a linha e o lote.

O lote existe porque a grade edita várias linhas com o mesmo valor de uma vez.
Uma requisição por linha faria a tela abrir o banco N vezes e deixaria o lote
pela metade se a rede caísse no meio; aqui ou grava tudo, ou o erro é um só.
"""
from apps.pages import cgd_docs


def save_one(row_id, values):
    """Grava numa linha que já existe. Devolve o id dela."""
    cgd_docs.update_row(row_id, values)
    return row_id


def create(values):
    """Cria a linha e devolve o `_id` que o banco deu."""
    return cgd_docs.add_row(values)


def save_many(ids, values):
    """O mesmo valor em várias linhas. Devolve quantas foram."""
    for uid in ids:
        cgd_docs.update_row(str(uid).strip(), values)
    return len(ids)


def delete_one(row_id):
    cgd_docs.delete_row(row_id)


def delete_many(ids):
    """Apaga o lote e devolve quantos documentos SAÍRAM.

    Os ids passam por um `set`: o `_id` é a CHAVE da linha (o `DELETE` casa por
    valor, não por posição), então a ordem é indiferente — mas um id repetido na
    lista faria a contagem devolvida mentir sobre quantos documentos saíram.
    """
    unicos = sorted({str(x).strip() for x in ids if str(x).strip()})
    for uid in unicos:
        cgd_docs.delete_row(uid)
    return len(unicos)
