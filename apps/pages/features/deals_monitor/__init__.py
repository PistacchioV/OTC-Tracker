# -*- coding: utf-8 -*-
"""New Deals Monitor — o snapshot dos cards e o e-mail de pendências (19h/19h30).

Fronteira decidida: `domain.py` (catálogo de cards, LE da linha, taxonomia do
e-mail, parse dos horários — puro), `queries.py` (o snapshot que a página E o
e-mail leem — uma contagem só —, os blocos de pendência e o status do aviso),
`infra/persistence.py` (destinatários, claim de slot cross-process e o desfecho
do último disparo) e `commands.py` (o envio, o disparo com claim, o catch-up de
restart e o scheduler — o REGISTRO continua no wiring do routes, via
`start_scheduler` do entrypoint). Toda travessia entre camadas é pelo ATRIBUTO
do módulo, que é o que deixa os espiões do check_ndm_pending_sched
interceptarem; o que é de plataforma chega por busca atrasada (`_R()`).
"""
