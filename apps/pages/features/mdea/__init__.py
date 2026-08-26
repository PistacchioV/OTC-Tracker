# -*- coding: utf-8 -*-
"""Manual Deals EA — o que o EA automático não pode considerar.

Duas rotinas no mesmo card, porque a pergunta é a mesma ("que operações
fecharam hoje e precisam sair do EA automático?") e a resposta muda de produto:

  Other Publisher → todo dia às 20:00, com as operações do PRÓPRIO DIA (D+0);
  FWD Start       → às 16:30 do dia da **Strike Set Date**, com o re-booking.

São dois horários e dois botões Run, e não um só, porque as datas de referência
são diferentes: o Other Publisher olha o dia que está acabando, o FWD Start
olha as operações que fixaram hoje — que foram bookadas semanas atrás.

⚠️ **O Deal do FWD Start é o do VANILLA.** No dia da fixação a mesa cancela o
FWD Start e faz um booking novo, já como vanilla, com Deal ID NOVO — e é esse o
número que o EA automático vê. O par é calculado no pull do NDF
(`_ndf_drop_fwdstart_rebooks`, no routes) e GRAVADO por `record_rebooks`,
porque em nenhum outro momento os dois lados se veem juntos — é a ÚNICA entrada
desta feature vinda de fora, e o routes a alcança pelo entrypoint.

Como no `bacc`, o scheduler roda aqui e o REGISTRO fica no wiring do routes.
"""
