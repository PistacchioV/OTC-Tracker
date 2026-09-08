# -*- coding: utf-8 -*-
"""precificador — o motor das ferramentas de mercado (Apps › Tools).

Porte do pacote `precificador` do projeto *Precificação Swap* (as planilhas
VBA do curso viraram módulos Python) para dentro do OTC Tracker. Vieram só os
módulos que as cinco telas de Tools consomem:

    calendario    dias úteis (ANBIMA, SOFR, EURIBOR/TARGET2, US+BR), WORKDAY,
                  NETWORKDAYS−1, EDATE
    contagem      day count (DU/252, ACT/360, ACT/365, 30/360, 30E/360, ACT/ACT)
                  e regime (composto/simples)
    cdi           série 4389 do BCB e o acúmulo diário do CDI realizado
    cambio        PTAX de fechamento de qualquer moeda do boletim do BCB
    sofr          fixings do NY Fed, composição com lookback/shift, e a base
                  histórica local (overnight, médias e SOFR Index)
    term_sofr     a curva a termo da CME importada do relatório da B3
    euribor       EURIBOR diária do Banco da Finlândia, com base local
    renda_fixa    CDB/LCI/debênture: bruto, IR, IOF, líquido
    liquidacao    o ajuste de um swap no fim do fluxo, ponta a ponta
    planilha      leitor de .xlsx/.csv/.tsv sem dependência
    bases         o armazém das bases locais (DATA_DIR/tools, via o funil)
    rede          a saída HTTP — a MESMA fila de rotas do Quotes

Três coisas mudaram no porte, e as três são regras da casa (CLAUDE.md):

* **a rede é a do Quotes** (`apps/pages/quotes.py`): sessão Kerberos da
  Athena e a fila proxy cadastrado → proxy do sistema → conexão direta, com a
  rota boa memorizada. O `rede.py` original tinha a própria cadeia e as
  próprias variáveis de ambiente (`PRECIFICADOR_*`); duas cadeias no mesmo
  processo é ter duas respostas para "por onde saio para a internet";
* **os feriados vêm do Holidays Calendar** (`anbima.json`, `sofr.json`,
  `euribor.json` do `DATA_DIR`, pelo registro `holiday-calendars.json`), não
  de arquivos próprios — um calendário editado pela tela vale aqui no request
  seguinte. Fora do alcance do arquivo da EURIBOR vale a regra do TARGET2;
* **as bases locais gravam pelo funil** (`_atomic_write_json`) em
  `DATA_DIR/tools/`, com os seeds versionados em `tools/seed/` para a
  instância não nascer sem os vinte anos de EURIBOR e os oito de SOFR.

Texto que chega à tela — rótulos das listas, descrições e erros — nasce em
INGLÊS (§2). O molde separado dos valores (`ErroFerramenta`, as descrições
das pontas) continua: é o que permite à tela montar a frase sem concatenar
número dentro de chave de tradução.
"""
