# -*- coding: utf-8 -*-
"""O Onboarding como a TELA o recebe: o formulário e os domínios dos campos."""
from apps.pages import cgd_docs


def form_context():
    """O formulário de New Request para o template.

    Vem do MÓDULO, nunca escrito no HTML: o mesmo `REQUEST_FORM` define os
    campos do modal **e** os obrigatórios que seguram o documento no Banking.
    Escritos no template, o dia em que um campo deixasse de ser obrigatório o
    modal pararia de pedi-lo e a fila continuaria cobrando.
    """
    return {'cgd_form': cgd_docs.REQUEST_FORM,
            'cgd_signature_types': cgd_docs.SIGNATURE_TYPES}


def field_domains():
    """As listas com que a tela monta cada campo de edição.

    Elas vão no MESMO payload das colunas de propósito: uma lista escrita no
    template seria uma segunda cópia, e ela envelhece calada no dia em que a do
    servidor mudar — o campo continuaria oferecendo a opção que saiu.
    """
    return {'columns': cgd_docs.COLUMNS,
            'id_column': cgd_docs.ID_COLUMN,
            'date_columns': list(cgd_docs.DATE_COLUMNS),
            'stages': list(cgd_docs.STAGES),
            'signature_types': list(cgd_docs.SIGNATURE_TYPES),
            'signature_column': cgd_docs.SIGNATURE_COLUMN,
            'doc_types': list(cgd_docs.DOC_TYPES),
            'doc_type_column': cgd_docs.DOC_TYPE_COLUMN,
            'guarantor_options': list(cgd_docs.GUARANTOR_OPTIONS)}


def with_stage(row):
    """A linha mais a etapa em que ela parou. Alterada no lugar.

    A etapa vai JUNTO da linha porque a tabela mostra onde cada documento
    parou, e recalcular isso no navegador seria a mesma regra escrita duas
    vezes. `_closed` existe pelo mesmo motivo: encerrado NÃO tem etapa (ninguém
    trabalha nele) e a célula saía em branco — que se lê como *"ainda não chegou
    em ninguém"*, justamente o contrário. Uma cópia do `is_closed` no JS
    discordaria da do módulo no primeiro status novo que a lista trouxesse.
    """
    etapa, derivada = cgd_docs.pending_stage(row)
    row['_stage'] = etapa or ''
    row['_stage_derived'] = bool(derivada)
    row['_closed'] = bool(cgd_docs.is_closed(row))
    return row
