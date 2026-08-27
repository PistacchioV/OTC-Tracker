# -*- coding: utf-8 -*-
"""BACC EA Metrics — o e-mail diário (16:00 BRT) com as operações manuais.

Sexta vertical, e a primeira com um SCHEDULER. O laço em si veio junto
(`commands.scheduler_loop`), mas o REGISTRO dele continua sendo do `routes.py`:
`_schedule_on_start('bacc-ea', …)` é o gancho de plataforma que o `record_once`
do blueprint consome, e chamá-lo daqui exigiria importar o `routes` no corpo do
módulo — o ciclo que a regra das features proíbe. A linha vive no bloco de
wiring, ao lado do import do entrypoint.

A fonte do anexo é a MESMA `manual_conf.load_all()` que o Track Confirmations
mostra — um relatório que conta de outro jeito descreve uma fila que a tela não
tem, e a mesa deixa de acreditar nos dois. O `manual_conf` é módulo horizontal
(como o `cgd_docs` para o Onboarding): as regras que já moram nele
(`split_notional_ccy`, `STATUS_OK`) são consultadas, não copiadas.
"""
