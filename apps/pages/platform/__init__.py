# -*- coding: utf-8 -*-
"""As HORIZONTAIS (`apps/pages/platform/`) — a fase seguinte às 43 verticais.

O que mora aqui é o que várias features usam e nenhuma é dona: o calendário de
dias úteis, as notificações do sino, e (nas próximas fatias) e-mail, sessão e
os motores compartilhados. A regra de fronteira é a MESMA das features, com os
sentidos invertidos:

- **feature pode importar platform; platform NUNCA importa feature.**
- **platform não importa NOME do `routes`** — o que ainda é do `routes`
  (caminhos de banco, primitivas DuckDB) é alcançado por busca ATRASADA
  (`from apps.pages import routes` dentro da função), como andaime declarado,
  até aquela camada ter a própria fatia. É o que mantém válidos os testes que
  trocam atributos no `routes` (`R.NOTIF_DB_PATH = tmp`).
- **o `routes.py` mantém os nomes antigos como ALIAS** apontando para cá:
  as features seguem alcançando por `routes.<nome>` sem mudar, e os testes que
  trocam a FUNÇÃO no `routes` continuam interceptando todo mundo. Só quem troca
  o ESTADO (um set de feriados, um flag de subida) passa a trocá-lo aqui,
  porque o estado mora aqui.

Quem prende as regras é o `scripts/tests/check_soc_layers.py` (seção 10).
"""
