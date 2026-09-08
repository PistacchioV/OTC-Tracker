# -*- coding: utf-8 -*-
"""Tools (Apps › Tools) — as ferramentas de mercado portadas do *Precificação Swap*.

Cinco telas sob o item **Tools** do menu (o antigo item Quotes virou o pai;
o Quotes continua sendo a primeira filha e mora na vertical `quotes`):

    /tools/fixed-income      CDB/LCI/debênture — bruto, IR, IOF e líquido
    /tools/swap-calculator   o ajuste de um swap no fim do fluxo, ponta a ponta
    /tools/sofr-index        SOFR composto do NY Fed, com lookback e shift
    /tools/term-sofr         estrutura a termo realizada + a curva da CME importada
    /tools/euribor           EURIBOR diária, base local desde 2006

O **motor é o `apps/pages/precificador/`** (calendário, contagem, CDI, câmbio,
SOFR, Term SOFR, EURIBOR, renda fixa, liquidação) e fica fora da vertical de
propósito: é um pacote puro de mercado, como o `quotes.py` é o motor das
Cotações. O que mora aqui é a casca — leitura de formulário (`domain`), a
montagem dos contextos das telas (`queries`), as escritas (`commands`) e as
rotas (`entrypoint`).

**As telas são renderizadas no servidor** (POST do formulário → a mesma página
com o resultado), ao contrário do padrão JS+API das outras verticais: o
resultado de uma liquidação são quatro quadros e três tabelas montados a partir
de dataclasses, e serializá-los para o navegador remontar seria uma segunda
cópia do desenho. Como o DOM inteiro existe no load, o `I18nManager` traduz os
`data-lang` do resultado também — só o que o motor escreve (descrições, erros)
chega em inglês, como nas Cotações.

O **Swap Calculator pré-preenche pelo B3 ID** (o Contrato ou o Código
Identificador da posição de swap): contraparte, datas, notional, amortização e
as duas pontas saem do DPOSICAO-SWAP e do DFLUXO do último dia útil, com a
classificação do índice pelo cadastro `tools-swap-index` (/mapping). O que não
se consegue puxar volta em branco e SINALIZADO — nunca um valor inventado.
"""
