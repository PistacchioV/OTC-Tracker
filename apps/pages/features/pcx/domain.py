# -*- coding: utf-8 -*-
"""O contrato da planilha e as regras puras do card."""

FILENAME = 'PENDING - Outstanding Confirmation OTC.xlsx'

# (cabeçalho da planilha, coluna da página, é data?). A LISTA INTEIRA — nomes
# e ORDEM — é o layout que o time global pediu por extenso (§256): coluna com
# `None` é a que a página não tem, e sai VAZIA de propósito, mantendo a
# posição, para a query do consumidor continuar achando cada nome no lugar.
COLUMNS = [
    ('LOB',                                  'LOB',            False),
    ('Client',                               'Client',         False),
    ('Aging',                                'Aging',          False),
    ('Status',                               'Status',         False),
    ('Product Type',                         'Product Type',   False),
    ('Trade Date',                           'Trade Date',     True),
    ('Maturity Date',                        'Maturity Date',  True),
    ('Trade Number',                         'Trade Number',   False),
    ('Pending Status',                       'Pending Status', False),
    ('Owner',                                'Owner',          False),
    ('EA',                                   'EA',             True),
    ('JP sending documentation',             'Send Date',      True),
    ('Client return the document',           'Return Date',    True),
    ('JP verify power of attorney SENT',     None,             True),
    ('JP verify power of attorney received', None,             True),
    ('Data Devolução 2º Via',                None,             True),
    ('Vias',                                 None,             False),
    ('Devolvido Por',                        None,             False),
    ('Controle Envio Draft',                 None,             True),
    ('Break Reason',                         'Break Reason',   False),
    ('Controle 2º Via',                      None,             False),
    ('Ano',                                  None,             False),
    ('Document type',                        None,             False),
    ('Overall Comments',                     'Comments',       False),
    ('Economic Group',                       'Economic Group', False),
    ('Signature Type',                       'Signature Type', False),
    ('Pending IS',                           None,             False),
    ('Trade Number IS FEP WEB',              None,             False),
    ('Baixa Sem Abono',                      None,             False),
    ('Pendência',                            None,             False),
    ('Abono',                                None,             False),
]


class NoSnapshot(Exception):
    """Não existe foto do Pending daquele dia. Carrega o caminho procurado — a
    mensagem tem de dizer ONDE se procurou, senão "sem snapshot" é indistinguível
    de "a data está errada"."""

    def __init__(self, path, ref):
        super().__init__(path)
        self.path = path
        self.ref = ref


def time_of(raw):
    """(hh, mm) do disparo em BRT. Entrada inválida cai no padrão — um typo na
    variável de ambiente não pode matar a rotina."""
    try:
        hh, mm = (int(x) for x in str(raw).split(':')[:2])
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except (ValueError, TypeError):
        pass
    return 10, 45

