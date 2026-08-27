# -*- coding: utf-8 -*-
"""As escritas do Onboarding: gravar e apagar, a linha e o lote.

O lote existe porque a grade edita várias linhas com o mesmo valor de uma vez.
Uma requisição por linha faria a tela abrir o banco N vezes e deixaria o lote
pela metade se a rede caísse no meio; aqui ou grava tudo, ou o erro é um só.

Os três CARIMBOS da esteira também moram aqui: quem escreve a data e o SID é o
SERVIDOR, nunca o navegador — um relógio errado ou um SID digitado assinariam a
etapa por outra pessoa.
"""
from datetime import datetime

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


# ── Os carimbos da esteira ───────────────────────────────────────────────────

def _hoje():
    return datetime.now().strftime('%d/%m/%Y')


def stamp_taxonomy(row_id, sid):
    """Legal anexou o Taxonomy: a coluna guarda QUANDO e QUEM (data · SID).

    O SID vai na mesma célula de propósito — a coluna não está em DATE_COLUMNS,
    então o texto sobrevive à releitura; numa coluna de data o fmt_date jogaria
    o SID fora.
    """
    stamp = '{} {} · {}'.format(_hoje(), datetime.now().strftime('%H:%M'),
                                str(sid or '').strip().upper())
    cgd_docs.update_row(row_id, {cgd_docs.LEGAL_STAMP: stamp})
    return stamp


def stamp_otc(row_id, sid, issue_date, signature_date, b3_id):
    """OTC anexou o CGD abonado: Emissão, Data de Assinatura e o B3 ID — na
    coluna da LE em que a solicitação foi aberta (`b3_id_column`). O
    `OTC - STAMP` fecha a mesa com a data de hoje."""
    linha = [r for r in cgd_docs.load_all()
             if str(r.get(cgd_docs.ID_COLUMN)) == str(row_id)]
    le = linha[0].get(cgd_docs.LEGAL_ENTITY_COLUMN, '') if linha else ''
    valores = {
        'Emissão': str(issue_date or '').strip(),
        'Signature Date': str(signature_date or '').strip(),
        cgd_docs.b3_id_column(le): str(b3_id or '').strip(),
        cgd_docs.OTC_STAMP: _hoje(),
    }
    cgd_docs.update_row(row_id, valores)
    return valores


def stamp_mo(row_id, sid):
    """CEM MO conferiu abonado + taxonomy: fecha a esteira. O documento sai das
    filas pelo `Status = Active`, e o `Conclusion - Stamp` é o que PARA o aging
    — sem ele o CGD concluído continuaria envelhecendo."""
    valores = {cgd_docs.MO_STAMP: _hoje(),
               'Conclusion - Stamp': _hoje(),
               'Status': cgd_docs.ACTIVE_STATUS.title()}
    cgd_docs.update_row(row_id, valores)
    return valores


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
