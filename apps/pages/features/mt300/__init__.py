# -*- coding: utf-8 -*-
"""MT300 — as mensagens do dia para o grupo confirmar (19:30 BRT).

Todo dia útil, um e-mail com as operações de **NDF Vanilla** do dia cujas
contrapartes estão no cadastro `mt300`. A mensagem MT300 é confirmada por um
grupo específico de clientes, e é o cadastro que diz quem — empresa nova do
grupo entra pela tela, sem release.

**Sem operação de ninguém da lista, o e-mail NÃO sai.** Ele pede para casar o
trade no DVP; sem trade não há o que casar, e uma tabela vazia faria quem
recebe procurar o que não existe. É a mesma regra do Manual Deals EA, e o
oposto do BACC EA Metrics, onde a planilha vazia é ela própria a métrica.

Como no `bacc`, o scheduler roda aqui mas o REGISTRO
(`_schedule_on_start('mt300', …)`) fica no bloco de wiring do `routes.py`.
"""
