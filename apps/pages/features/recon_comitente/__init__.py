# -*- coding: utf-8 -*-
"""Recon de Comitentes — a casca da tela; o motor é o `recon_comitente.py`.

O motor (leitura do box, batimento, SQLite, e-mail) é módulo horizontal e fica
onde está: o /mapping e os scripts também o consultam. Aqui moram só as três
rotas e a orquestração do Run — inclusive a taxonomia de erro que a tela
distingue (ocupado ≠ quebrado ≠ desfecho desconhecido).
"""
