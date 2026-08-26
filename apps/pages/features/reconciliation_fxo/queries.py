# -*- coding: utf-8 -*-
"""A leitura da Recon de FXO: a última execução, ou a de uma data."""
from apps.pages import recon_fxo


def last(recon_date):
    """O resultado em cache daquele dia.

    Sem data, o motor decide o padrão — e ele é o **dia útil anterior**, o mesmo
    que a página usa para abrir. Com `hoje` de um lado só, o batimento rodava e
    a leitura seguinte dizia que ninguém tinha rodado.
    """
    return recon_fxo.load_last(recon_date)
