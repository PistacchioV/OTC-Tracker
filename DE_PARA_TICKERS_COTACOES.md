# De-para de Tickers — Cotações (OTC Tracker)

> Registro do de-para entre o **Código do Ativo Subjacente** (o mesmo do Index B3)
> e o **símbolo de mercado** que a página *Apps › Quotes* usa para buscar preço.
> Documento gerado dos cadastros vivos em 18/08/2026.

---

## 1. Onde este de-para vive

O de-para **não é código**: é cadastro, editável na tela `/mapping` e válido no
request seguinte, sem restart.

| Cadastro (tela `/mapping`) | Arquivo versionado | Linhas hoje |
|---|---|---|
| Quotes — Commodities | `apps/static/data/mappings/quotes-commodity.json` | 17 |
| Quotes — Equities | `apps/static/data/mappings/quotes-equity.json` | 471 |

Três coisas que este cadastro **não** é:

- **Não é a lista de instrumentos da tela.** Essa vem do `Subjacente.json` do
  Index B3 ao vivo, separada pelo campo `Classe` e só os `ACTIVE` — ativo novo
  cadastrado no Index B3 aparece em Cotações no mesmo dia. Este cadastro só
  TRADUZ o código em símbolo.
- **Não cobre a PTAX.** A lista de moedas do BCB é o domínio do endpoint
  (Olinda), não um de-para.
- **Não é um wrapper de `yfinance`.** O app fala direto com o endpoint `chart`
  do Yahoo Finance, com a mesma sessão autenticada da Athena. O de-para é o
  mesmo que a biblioteca usaria — o símbolo é do Yahoo, não da lib.

Código sem símbolo cadastrado devolve **404 pedindo cadastro**; o app nunca
tenta o código B3 como se fosse ticker.

---

## 2. Sufixo de bolsa do Yahoo Finance

O símbolo do Yahoo é `TICKER` + sufixo da bolsa. Sufixo errado é 404, não preço
errado. Os que aparecem neste de-para, conforme a página oficial de bolsas e
provedores do Yahoo Finance:

| Sufixo | Bolsa | Onde aparece aqui |
|---|---|---|
| `.CBT` | Chicago Board of Trade (CBOT) | grãos — milho, soja, óleo de soja, trigo |
| `.NYB` | ICE Futures US | softs — café, açúcar, cacau, algodão |
| `.NYM` | New York Mercantile Exchange (NYMEX) | petróleo Brent |
| `.CME` | Chicago Mercantile Exchange | não usado hoje |
| `.CMX` | COMEX | não usado hoje |
| `.SA` | Sao Paulo Stock Exchange (BOVESPA / B3) | ações e BDRs brasileiros |
| *(sem sufixo)* | bolsas dos EUA (NYSE, NASDAQ) | ações internacionais |
| `^` (prefixo) | índice, não papel | `^BVSP`, `^GSPC`, `^NDX` |
| `=F` (sufixo) | contrato futuro **contínuo** (1º vencimento) | `ZC=F`, `BZ=F` |
| `.PA` `.AS` `.L` `.DE` `.MI` `.MC` `.TO` | Paris, Amsterdã, Londres, XETRA, Milão, Madri, Toronto | ver §6 (pendência) |

---

## 3. Código de mês do contrato futuro

Padrão de mercado, igual nos dois lados (B3 e Yahoo) — é só o **ano** que muda
de largura.

| Mês | Código | Mês | Código |
|---|---|---|---|
| Janeiro | F | Julho | N |
| Fevereiro | G | Agosto | Q |
| Março | H | Setembro | U |
| Abril | J | Outubro | V |
| Maio | K | Novembro | X |
| Junho | M | Dezembro | Z |

---

## 4. Commodities — uma linha por mercadoria, não por vencimento

Contrato futuro tem vencimento, e o de-para por código fechado pedia **uma
linha por mês de cada mercadoria** — 70 linhas para 10 mercadorias, mais uma
linha nova a cada vencimento que a B3 abrisse.

As duas colunas do cadastro aceitam o **padrão `"MY"`**, a mesma notação do
cadastro *Commodities × B3*:

- `"MY"` (entre aspas) = onde entram a **letra do mês** e o **ano**;
- `_` = um **espaço literal** no código B3 (o milho na B3 é `C ` com espaço).

```
   cadastro                        resultado
   BO"MY"  →  ZL"MY".CBT           BOK6   →  ZLK26.CBT
   C_"MY"  →  ZC"MY".CBT           C K6   →  ZCK26.CBT
   CO"MY"  →  BZ"MY".NYM           COZ29  →  BZZ29.NYM
```

Duas assimetrias que o padrão resolve sozinho:

1. **O ano tem larguras diferentes nos dois lados.** A B3 escreve um dígito
   (`BOK6`) ou dois (`COZ29`); o Yahoo escreve sempre dois (`ZLK26`). O dígito
   único é resolvido na década corrente, virando para a próxima quando o ano
   cairia mais de um ano no passado — contrato futuro aponta para a frente, e
   `5` em 2026 é 2025 (o vencimento recém-liquidado), nunca 2015.
2. **O `"MY"` do símbolo fica no meio** (`ZL"MY".CBT`), porque o sufixo de bolsa
   vem depois do vencimento.

Uma linha **sem** `"MY"` continua sendo de-para literal e **vence** o padrão —
é assim que se cadastra a exceção de um vencimento só, ou o contrato contínuo.

### 4.1 O cadastro completo

| Código B3 (padrão) | Símbolo de mercado | Mercadoria / bolsa |
|---|---|---|
| `BO1` | `ZL=F` | OLEO DE SOJA — contrato continuo (1o vencimento). Linha LITERAL: vence o padrao BO"MY", que so casa mes+ano. |
| `C 1` | `ZC=F` | MILHO — contrato continuo (1o vencimento) |
| `CC1` | `CC=F` | CACAU — contrato continuo (1o vencimento) |
| `CO1` | `BZ=F` | PETROLEO BRENT — contrato continuo (1o vencimento) |
| `KC1` | `KC=F` | CAFE — contrato continuo (1o vencimento) |
| `S 1` | `ZS=F` | SOJA — contrato continuo (1o vencimento) |
| `W 1` | `ZW=F` | TRIGO — contrato continuo (1o vencimento) |
| `BO"MY"` | `ZL"MY".CBT` | OLEO DE SOJA — Soybean Oil (CBOT) |
| `C_"MY"` | `ZC"MY".CBT` | MILHO — Corn (CBOT) |
| `CC"MY"` | `CC"MY".NYB` | CACAU — Cocoa (ICE Futures US) |
| `CO"MY"` | `BZ"MY".NYM` | PETROLEO BRENT — Brent Last Day Financial (NYMEX). Era CO"MY".NYB, que o Yahoo nao tem. |
| `CT"MY"` | `CT"MY".NYB` | ALGODAO — Cotton No. 2 (ICE Futures US) |
| `DF"MY"` | `DF"MY".NYB` | CAFE — simbolo herdado do app de desktop, nao confirmado na fonte |
| `KC"MY"` | `KC"MY".NYB` | CAFE — Coffee C (ICE Futures US) |
| `S_"MY"` | `ZS"MY".CBT` | SOJA — Soybean (CBOT) |
| `SB"MY"` | `SB"MY".NYB` | ACUCAR — Sugar No. 11 (ICE Futures US) |
| `W_"MY"` | `ZW"MY".CBT` | TRIGO — Chicago SRW Wheat (CBOT) |

### 4.2 Como as 17 linhas cobrem os subjacentes do dia

Os 904 códigos da classe COMMODITIES ativos no Index B3 hoje resolvem assim —
**221 deles** ganham símbolo por essas 17 linhas (antes eram 70 linhas para 70
códigos, e nenhum vencimento novo):

| Família | Códigos B3 que casam | Símbolo resultante |
|---|---|---|
| Óleo de soja | 21 — BOF7, BOH7, BOH8, BOK6 … | `ZL` + mês/ano |
| Milho | 17 — C H7, C H8, C K6, C K7 … | `ZC` + mês/ano |
| Cacau | 10 — CCH7, CCH8, CCK6, CCK7 … | `CC` + mês/ano |
| Petróleo Brent | 47 — COF7, COF8, COF9, COG29 … | `BZ` + mês/ano |
| Algodão | 16 — CTH7, CTH8, CTH9, CTK18 … | `CT` + mês/ano |
| Café (ver §6) | 8 — DFF7, DFK6, DFK7, DFN6 … | `DF` + mês/ano |
| Café C | 37 — KCH0, KCH19, KCH20, KCH6 … | `KC` + mês/ano |
| Soja | 35 — S F7, S F8, S H7, S H8 … | `ZS` + mês/ano |
| Açúcar | 17 — SBH0, SBH19, SBH6, SBH7 … | `SB` + mês/ano |
| Trigo | 6 — W H7, W K6, W K7, W N6 … | `ZW` + mês/ano |

Exemplo de expansão, código a código (amostra):

| Código B3 | Símbolo | | Código B3 | Símbolo |
|---|---|---|---|---|
| `BOK6` | `ZLK26.CBT` | | `C K6` | `ZCK26.CBT` |
| `CCZ6` | `CCZ26.NYB` | | `COZ6` | `BZZ26.NYM` |
| `COG29` | `BZG29.NYM` | | `CTZ6` | `CTZ26.NYB` |
| `KCZ6` | `KCZ26.NYB` | | `S X6` | `ZSX26.CBT` |
| `SBH6` | `SBH26.NYB` | | `W Z6` | `ZWZ26.CBT` |
| `BO1` | `ZL=F` | | `CO1` | `BZ=F` |

---

## 5. Equities — as duas regras

Ação e índice não têm vencimento, então aqui **toda linha é literal**. Mas ela
segue duas regras, e é bom que estejam escritas:

1. **Papel brasileiro** — o código do Index B3 é o próprio ticker, e leva o
   sufixo da B3: `PETR4` → `PETR4.SA`, `AAPL34` → `AAPL34.SA` (BDR). São **389**
   das 471 linhas.
2. **Papel internacional** — o código do Index B3 vem no formato Bloomberg
   (`AAPL UW`, `AMZN US`), com o código de bolsa depois do espaço; o Yahoo usa
   o ticker sozinho para os EUA: `AAPL UW` → `AAPL`. São **82** linhas.

Índice não é papel e leva `^`: `IBOVESPA` → `^BVSP`, `SPX QUANTO` → `^GSPC`,
`NDX` → `^NDX`.

### 5.1 Códigos de bolsa Bloomberg que aparecem no cadastro

| Código Bloomberg | Bolsa | Sufixo Yahoo correspondente |
|---|---|---|
| `US`, `UN`, `UQ`, `UW`, `UP`, `UR` | bolsas dos EUA (NYSE, NASDAQ e afins) | *(nenhum)* |
| `FP` | Euronext Paris | `.PA` |
| `NA` | Euronext Amsterdã | `.AS` |
| `LN` | London Stock Exchange | `.L` |

### 5.2 O cadastro completo

#### Ações (386)

| Código B3 | Símbolo | | Código B3 | Símbolo | | Código B3 | Símbolo |
|---|---|---|---|---|---|---|---|
| `AAPL34` | `AAPL34.SA` |  | `ABCB4` | `ABCB4.SA` |  | `ABEV3` | `ABEV3.SA` |
| `ADBE34` | `ADBE34.SA` |  | `AESB3` | `AESB3.SA` |  | `AGRO3` | `AGRO3.SA` |
| `AIRB34` | `AIRB34.SA` |  | `ALOS3` | `ALOS3.SA` |  | `ALOS99` | `ALOS99.SA` |
| `ALSO3` | `ALSO3.SA` |  | `ALUP11` | `ALUP11.SA` |  | `AMAR3` | `AMAR3.SA` |
| `AMBP3` | `AMBP3.SA` |  | `AMER3` | `AMER3.SA` |  | `AMZO34` | `AMZO34.SA` |
| `ANIM3` | `ANIM3.SA` |  | `ARGE11` | `ARGE11.SA` |  | `ARGT39` | `ARGT39.SA` |
| `ARML3` | `ARML3.SA` |  | `ASAI3` | `ASAI3.SA` |  | `ASML34` | `ASML34.SA` |
| `AUAU3` | `AUAU3.SA` |  | `AUAU99` | `AUAU99.SA` |  | `AURA33` | `AURA33.SA` |
| `AURE3` | `AURE3.SA` |  | `AVGO34` | `AVGO34.SA` |  | `AXIA3` | `AXIA3.SA` |
| `AZEV4` | `AZEV4.SA` |  | `AZZA3` | `AZZA3.SA` |  | `BABA34` | `BABA34.SA` |
| `BAER39` | `BAER39.SA` |  | `BALM4` | `BALM4.SA` |  | `BBAS3` | `BBAS3.SA` |
| `BBDC3` | `BBDC3.SA` |  | `BBDC4` | `BBDC4.SA` |  | `BBOI11` | `BBOI11.SA` |
| `BBSE3` | `BBSE3.SA` |  | `BCIA11` | `BCIA11.SA` |  | `BCPX39` | `BCPX39.SA` |
| `BCRI11` | `BCRI11.SA` |  | `BEEF3` | `BEEF3.SA` |  | `BERK34` | `BERK34.SA` |
| `BHIA3` | `BHIA3.SA` |  | `BIDI11` | `BIDI11.SA` |  | `BIDI4` | `BIDI4.SA` |
| `BIDU34` | `BIDU34.SA` |  | `BIEO39` | `BIEO39.SA` |  | `BIJR39` | `BIJR39.SA` |
| `BIOM3` | `BIOM3.SA` |  | `BITH11` | `BITH11.SA` |  | `BITI11` | `BITI11.SA` |
| `BIWM39` | `BIWM39.SA` |  | `BIXC39` | `BIXC39.SA` |  | `BIYE39` | `BIYE39.SA` |
| `BKBR3` | `BKBR3.SA` |  | `BKNG34` | `BKNG34.SA` |  | `BKWB39` | `BKWB39.SA` |
| `BLAK34` | `BLAK34.SA` |  | `BMEB4` | `BMEB4.SA` |  | `BMGB4` | `BMGB4.SA` |
| `BMOB3` | `BMOB3.SA` |  | `BNDA39` | `BNDA39.SA` |  | `BOAC34` | `BOAC34.SA` |
| `BOVA11` | `BOVA11.SA` |  | `BOVV11` | `BOVV11.SA` |  | `BOVX11` | `BOVX11.SA` |
| `BPAC11` | `BPAC11.SA` |  | `BPAN4` | `BPAN4.SA` |  | `BRAP3` | `BRAP3.SA` |
| `BRAV3` | `BRAV3.SA` |  | `BRBI11` | `BRBI11.SA` |  | `BRDT3` | `BRDT3.SA` |
| `BRFS3` | `BRFS3.SA` |  | `BRIT3` | `BRIT3.SA` |  | `BRKM5` | `BRKM5.SA` |
| `BRPR3` | `BRPR3.SA` |  | `BRSR6` | `BRSR6.SA` |  | `BRXC11` | `BRXC11.SA` |
| `BSIL39` | `BSIL39.SA` |  | `BSLV39` | `BSLV39.SA` |  | `BTCI11` | `BTCI11.SA` |
| `BTHF11` | `BTHF11.SA` |  | `BTLG11` | `BTLG11.SA` |  | `BURA39` | `BURA39.SA` |
| `BUTL39` | `BUTL39.SA` |  | `CACR11` | `CACR11.SA` |  | `CAFR31` | `CAFR31.SA` |
| `CAML3` | `CAML3.SA` |  | `CASH3` | `CASH3.SA` |  | `CBAV3` | `CBAV3.SA` |
| `CCME11` | `CCME11.SA` |  | `CCRO3` | `CCRO3.SA` |  | `CEAB3` | `CEAB3.SA` |
| `CHIP11` | `CHIP11.SA` |  | `CHVX34` | `CHVX34.SA` |  | `CIEL3` | `CIEL3.SA` |
| `CLIN11` | `CLIN11.SA` |  | `CMIG3` | `CMIG3.SA` |  | `CMIG4` | `CMIG4.SA` |
| `CMIN3` | `CMIN3.SA` |  | `COCA34` | `COCA34.SA` |  | `COGN3` | `COGN3.SA` |
| `CORN11` | `CORN11.SA` |  | `COWC34` | `COWC34.SA` |  | `CPFE3` | `CPFE3.SA` |
| `CPLE3` | `CPLE3.SA` |  | `CPLE6` | `CPLE6.SA` |  | `CPTS11` | `CPTS11.SA` |
| `CRAA11` | `CRAA11.SA` |  | `CRFB3` | `CRFB3.SA` |  | `CSAN3` | `CSAN3.SA` |
| `CSED3` | `CSED3.SA` |  | `CTGP34` | `CTGP34.SA` |  | `CURY3` | `CURY3.SA` |
| `CVCB3` | `CVCB3.SA` |  | `CXSE3` | `CXSE3.SA` |  | `CYRE3` | `CYRE3.SA` |
| `CYRE4` | `CYRE4.SA` |  | `DESK3` | `DESK3.SA` |  | `DEVA11` | `DEVA11.SA` |
| `DEXP3` | `DEXP3.SA` |  | `DIRR3` | `DIRR3.SA` |  | `DISB34` | `DISB34.SA` |
| `DIVO11` | `DIVO11.SA` |  | `DOLA11` | `DOLA11.SA` |  | `DOTZ3` | `DOTZ3.SA` |
| `DTEX3` | `DTEX3.SA` |  | `DXCO3` | `DXCO3.SA` |  | `ECOR3` | `ECOR3.SA` |
| `EGIE3` | `EGIE3.SA` |  | `ELET3` | `ELET3.SA` |  | `ELET6` | `ELET6.SA` |
| `EMBJ3` | `EMBJ3.SA` |  | `EMBR3` | `EMBR3.SA` |  | `ENAT3` | `ENAT3.SA` |
| `ENEV3` | `ENEV3.SA` |  | `ENGI11` | `ENGI11.SA` |  | `ENJU3` | `ENJU3.SA` |
| `EQTL3` | `EQTL3.SA` |  | `ESTC3` | `ESTC3.SA` |  | `ETHE11` | `ETHE11.SA` |
| `EUCA4` | `EUCA4.SA` |  | `EVEN3` | `EVEN3.SA` |  | `EVTC31` | `EVTC31.SA` |
| `EXXO34` | `EXXO34.SA` |  | `EZTC3` | `EZTC3.SA` |  | `FESA4` | `FESA4.SA` |
| `FGAA11` | `FGAA11.SA` |  | `FLRY3` | `FLRY3.SA` |  | `FRAS3` | `FRAS3.SA` |
| `GARE11` | `GARE11.SA` |  | `GDXB39` | `GDXB39.SA` |  | `GFSA3` | `GFSA3.SA` |
| `GGBR4` | `GGBR4.SA` |  | `GGPS3` | `GGPS3.SA` |  | `GGRC11` | `GGRC11.SA` |
| `GMAT3` | `GMAT3.SA` |  | `GMCO34` | `GMCO34.SA` |  | `GOAU3` | `GOAU3.SA` |
| `GOAU4` | `GOAU4.SA` |  | `GOGL34` | `GOGL34.SA` |  | `GOLD11` | `GOLD11.SA` |
| `GOLL4` | `GOLL4.SA` |  | `GRND3` | `GRND3.SA` |  | `GSGI34` | `GSGI34.SA` |
| `GTWR11` | `GTWR11.SA` |  | `HAPV3` | `HAPV3.SA` |  | `HASH11` | `HASH11.SA` |
| `HBOR3` | `HBOR3.SA` |  | `HBRE3` | `HBRE3.SA` |  | `HBSA3` | `HBSA3.SA` |
| `HFOF11` | `HFOF11.SA` |  | `HGBS11` | `HGBS11.SA` |  | `HGLG11` | `HGLG11.SA` |
| `HGRE11` | `HGRE11.SA` |  | `HGRU11` | `HGRU11.SA` |  | `HODL11` | `HODL11.SA` |
| `HOSI11` | `HOSI11.SA` |  | `HSAF11` | `HSAF11.SA` |  | `HSML11` | `HSML11.SA` |
| `HYPE3` | `HYPE3.SA` |  | `IFCM3` | `IFCM3.SA` |  | `IGTI11` | `IGTI11.SA` |
| `INBR32` | `INBR32.SA` |  | `INTB3` | `INTB3.SA` |  | `IRBR3` | `IRBR3.SA` |
| `IRDM11` | `IRDM11.SA` |  | `IRIM11` | `IRIM11.SA` |  | `ISAE4` | `ISAE4.SA` |
| `ITLC34` | `ITLC34.SA` |  | `ITSA3` | `ITSA3.SA` |  | `ITSA4` | `ITSA4.SA` |
| `ITUB3` | `ITUB3.SA` |  | `ITUB4` | `ITUB4.SA` |  | `IVVB11` | `IVVB11.SA` |
| `JALL3` | `JALL3.SA` |  | `JBSS3` | `JBSS3.SA` |  | `JBSS32` | `JBSS32.SA` |
| `JHSF3` | `JHSF3.SA` |  | `JNJB34` | `JNJB34.SA` |  | `JPMC34` | `JPMC34.SA` |
| `JSLG3` | `JSLG3.SA` |  | `KEPL3` | `KEPL3.SA` |  | `KLBN11` | `KLBN11.SA` |
| `KNCA11` | `KNCA11.SA` |  | `KNCR11` | `KNCR11.SA` |  | `KNHY11` | `KNHY11.SA` |
| `KNIP11` | `KNIP11.SA` |  | `KNRI11` | `KNRI11.SA` |  | `KNSC11` | `KNSC11.SA` |
| `KORE11` | `KORE11.SA` |  | `LAME4` | `LAME4.SA` |  | `LAVV3` | `LAVV3.SA` |
| `LEVE3` | `LEVE3.SA` |  | `LIFE11` | `LIFE11.SA` |  | `LIGT3` | `LIGT3.SA` |
| `LILY34` | `LILY34.SA` |  | `LJQQ3` | `LJQQ3.SA` |  | `LOGG3` | `LOGG3.SA` |
| `LREN3` | `LREN3.SA` |  | `LVBI11` | `LVBI11.SA` |  | `LWSA3` | `LWSA3.SA` |
| `MBRF3` | `MBRF3.SA` |  | `MCDC34` | `MCDC34.SA` |  | `MCRE11` | `MCRE11.SA` |
| `MDNE3` | `MDNE3.SA` |  | `MELI34` | `MELI34.SA` |  | `MELK3` | `MELK3.SA` |
| `MGLU3` | `MGLU3.SA` |  | `MILS3` | `MILS3.SA` |  | `MOTV3` | `MOTV3.SA` |
| `MOVI3` | `MOVI3.SA` |  | `MRFG3` | `MRFG3.SA` |  | `MRVE3` | `MRVE3.SA` |
| `MSCD34` | `MSCD34.SA` |  | `MSFT34` | `MSFT34.SA` |  | `MTRE3` | `MTRE3.SA` |
| `MULT3` | `MULT3.SA` |  | `MUTC34` | `MUTC34.SA` |  | `MXRF11` | `MXRF11.SA` |
| `MYPK3` | `MYPK3.SA` |  | `NASD11` | `NASD11.SA` |  | `NATU3` | `NATU3.SA` |
| `NEOE3` | `NEOE3.SA` |  | `NFLX34` | `NFLX34.SA` |  | `NIKE34` | `NIKE34.SA` |
| `NSLU11` | `NSLU11.SA` |  | `NTCO3` | `NTCO3.SA` |  | `NVDC34` | `NVDC34.SA` |
| `ODPV3` | `ODPV3.SA` |  | `ONCO3` | `ONCO3.SA` |  | `OPCT3` | `OPCT3.SA` |
| `ORCL34` | `ORCL34.SA` |  | `ORVR3` | `ORVR3.SA` |  | `PAGS34` | `PAGS34.SA` |
| `PCAR3` | `PCAR3.SA` |  | `PCIP11` | `PCIP11.SA` |  | `PETR4` | `PETR4.SA` |
| `PFIZ34` | `PFIZ34.SA` |  | `PGMN3` | `PGMN3.SA` |  | `PINE4` | `PINE4.SA` |
| `PLPL3` | `PLPL3.SA` |  | `PNVL3` | `PNVL3.SA` |  | `POMO3` | `POMO3.SA` |
| `POMO4` | `POMO4.SA` |  | `POSI3` | `POSI3.SA` |  | `PRIO3` | `PRIO3.SA` |
| `PSSA3` | `PSSA3.SA` |  | `PTBL3` | `PTBL3.SA` |  | `PVBI11` | `PVBI11.SA` |
| `PYPL34` | `PYPL34.SA` |  | `QBTC11` | `QBTC11.SA` |  | `QETH11` | `QETH11.SA` |
| `QUAL3` | `QUAL3.SA` |  | `QUBT34` | `QUBT34.SA` |  | `RAIL3` | `RAIL3.SA` |
| `RAIZ4` | `RAIZ4.SA` |  | `RANI3` | `RANI3.SA` |  | `RAPT4` | `RAPT4.SA` |
| `RBRY11` | `RBRY11.SA` |  | `RDOR3` | `RDOR3.SA` |  | `RECR11` | `RECR11.SA` |
| `RECV3` | `RECV3.SA` |  | `RENT3` | `RENT3.SA` |  | `RENT4` | `RENT4.SA` |
| `RIAA3` | `RIAA3.SA` |  | `RIOT34` | `RIOT34.SA` |  | `ROMI3` | `ROMI3.SA` |
| `ROXO34` | `ROXO34.SA` |  | `RRRP3` | `RRRP3.SA` |  | `RURA11` | `RURA11.SA` |
| `RVBI11` | `RVBI11.SA` |  | `RZAK11` | `RZAK11.SA` |  | `RZTR11` | `RZTR11.SA` |
| `SANB11` | `SANB11.SA` |  | `SANB3` | `SANB3.SA` |  | `SANB4` | `SANB4.SA` |
| `SAPR11` | `SAPR11.SA` |  | `SAPR3` | `SAPR3.SA` |  | `SAPR4` | `SAPR4.SA` |
| `SBFG3` | `SBFG3.SA` |  | `SBSP3` | `SBSP3.SA` |  | `SCVB11` | `SCVB11.SA` |
| `SEER3` | `SEER3.SA` |  | `SEQL3` | `SEQL3.SA` |  | `SHOW3` | `SHOW3.SA` |
| `SHUL4` | `SHUL4.SA` |  | `SIMH3` | `SIMH3.SA` |  | `SIMN34` | `SIMN34.SA` |
| `SLCE3` | `SLCE3.SA` |  | `SMAC11` | `SMAC11.SA` |  | `SMAL11` | `SMAL11.SA` |
| `SMFT3` | `SMFT3.SA` |  | `SMTO3` | `SMTO3.SA` |  | `SNCI11` | `SNCI11.SA` |
| `SOJA3` | `SOJA3.SA` |  | `SOLH11` | `SOLH11.SA` |  | `SOMA3` | `SOMA3.SA` |
| `SPXB11` | `SPXB11.SA` |  | `SPXI11` | `SPXI11.SA` |  | `SPXR11` | `SPXR11.SA` |
| `SQIA3` | `SQIA3.SA` |  | `SRNA3` | `SRNA3.SA` |  | `STBP3` | `STBP3.SA` |
| `SUZB3` | `SUZB3.SA` |  | `SUZB5` | `SUZB5.SA` |  | `SYNE3` | `SYNE3.SA` |
| `TAEE11` | `TAEE11.SA` |  | `TAEE3` | `TAEE3.SA` |  | `TAEE4` | `TAEE4.SA` |
| `TASA4` | `TASA4.SA` |  | `TECK11` | `TECK11.SA` |  | `TEND3` | `TEND3.SA` |
| `TFCO4` | `TFCO4.SA` |  | `TGAR11` | `TGAR11.SA` |  | `TIET11` | `TIET11.SA` |
| `TIMP3` | `TIMP3.SA` |  | `TIMS3` | `TIMS3.SA` |  | `TOTS3` | `TOTS3.SA` |
| `TRAD3` | `TRAD3.SA` |  | `TRIG11` | `TRIG11.SA` |  | `TRIS3` | `TRIS3.SA` |
| `TRPL4` | `TRPL4.SA` |  | `TRXF11` | `TRXF11.SA` |  | `TSLA34` | `TSLA34.SA` |
| `TSMC34` | `TSMC34.SA` |  | `TTEN3` | `TTEN3.SA` |  | `TUPY3` | `TUPY3.SA` |
| `TVRI11` | `TVRI11.SA` |  | `UGPA3` | `UGPA3.SA` |  | `UNIP6` | `UNIP6.SA` |
| `USIM5` | `USIM5.SA` |  | `UTLL11` | `UTLL11.SA` |  | `VALE3` | `VALE3.SA` |
| `VAMO3` | `VAMO3.SA` |  | `VAMO99` | `VAMO99.SA` |  | `VBBR3` | `VBBR3.SA` |
| `VGHF11` | `VGHF11.SA` |  | `VGIP11` | `VGIP11.SA` |  | `VGIR11` | `VGIR11.SA` |
| `VIIA3` | `VIIA3.SA` |  | `VINO11` | `VINO11.SA` |  | `VISA34` | `VISA34.SA` |
| `VISC11` | `VISC11.SA` |  | `VIVA3` | `VIVA3.SA` |  | `VIVT3` | `VIVT3.SA` |
| `VLID3` | `VLID3.SA` |  | `VRTA11` | `VRTA11.SA` |  | `VULC3` | `VULC3.SA` |
| `VVAR3` | `VVAR3.SA` |  | `VVEO3` | `VVEO3.SA` |  | `WALM34` | `WALM34.SA` |
| `WEGE3` | `WEGE3.SA` |  | `WFCO34` | `WFCO34.SA` |  | `WIZC3` | `WIZC3.SA` |
| `WIZS3` | `WIZS3.SA` |  | `XBIT11` | `XBIT11.SA` |  | `XETH11` | `XETH11.SA` |
| `XFIX11` | `XFIX11.SA` |  | `XINA11` | `XINA11.SA` |  | `XPBR31` | `XPBR31.SA` |
| `XPLG11` | `XPLG11.SA` |  | `XPML11` | `XPML11.SA` |  | `XPSF11` | `XPSF11.SA` |
| `YDUQ3` | `YDUQ3.SA` |  | `ZAMP3` | `ZAMP3.SA` |  |  |  |

#### Ações Internacionais (67)

| Código B3 | Símbolo | | Código B3 | Símbolo | | Código B3 | Símbolo |
|---|---|---|---|---|---|---|---|
| `AA UN` | `AA` |  | `AAPL UN` | `AAPL` |  | `AAPL UQ` | `AAPL` |
| `AAPL US` | `AAPL` |  | `AAPL UW` | `AAPL` |  | `ABBV US` | `ABBV` |
| `ADBE US` | `ADBE` |  | `AEM UN` | `AEM` |  | `AIR FP` | `AIR` |
| `AIR FP_PA` | `AIR` |  | `AKAM US` | `AKAM` |  | `AMD UQ` | `AMD` |
| `AMD UR` | `AMD` |  | `AMD US` | `AMD` |  | `AMD UW` | `AMD` |
| `AMZN UQ` | `AMZN` |  | `AMZN US` | `AMZN` |  | `AMZN UW` | `AMZN` |
| `AMZN UW_43` | `AMZN` |  | `APD UN` | `APD` |  | `ASML NA` | `ASML` |
| `ASML US` | `ASML` |  | `ATVI UW_43` | `ATVI` |  | `AU UN` | `AU` |
| `AVGO US` | `AVGO` |  | `AVGO UW` | `AVGO` |  | `AZN LN` | `AZN` |
| `AZN UQ` | `AZN` |  | `AZN US` | `AZN` |  | `AZN UW` | `AZN` |
| `BABA UN` | `BABA` |  | `BABA UN_43` | `BABA` |  | `BABA US` | `BABA` |
| `BRK/B UN` | `BRK-B` |  | `BRK/B UP` | `BRK-B` |  | `BRK/B US` | `BRK-B` |
| `BUD UN` | `BUD` |  | `BUD US` | `BUD` |  | `C UN` | `BUSHELS` |
| `CAR US` | `CAR` |  | `CAR UW` | `CAR` |  | `EA US` | `EA` |
| `EA UW` | `EA` |  | `EA UW_43` | `EA` |  | `GOOG UQ` | `GOOG` |
| `GOOG US` | `GOOG` |  | `GOOG UW` | `GOOG` |  | `GOOGL UQ` | `GOOGL` |
| `GOOGL US` | `GOOGL` |  | `GOOGL UW` | `GOOGL` |  | `JNJ UN` | `JNJ` |
| `LLY UN` | `LLY` |  | `LLY US` | `LLY` |  | `LULU UW` | `LULU` |
| `MSFT UQ` | `MSFT` |  | `MSFT US` | `MSFT` |  | `MSFT UW` | `MSFT` |
| `MT NA` | `MT` |  | `MT NA_PA` | `MT` |  | `NVDA UQ` | `NVDA` |
| `NVDA US` | `NVDA` |  | `NVDA UW` | `NVDA` |  | `NVO UN` | `NVO` |
| `NVO US` | `NVO` |  | `PANW UW` | `PANW` |  | `QQQ UQ` | `QQQ` |
| `T UN` | `T` |  |  |  |  |  |  |

#### Indices (2)

| Código B3 | Símbolo | | Código B3 | Símbolo | | Código B3 | Símbolo |
|---|---|---|---|---|---|---|---|
| `IBOVESPA` | `^BVSP` |  | `SPX QUANTO` | `^GSPC` |  |  |  |

#### Indices Internacionais (16)

| Código B3 | Símbolo | | Código B3 | Símbolo | | Código B3 | Símbolo |
|---|---|---|---|---|---|---|---|
| `AAXJ UP` | `AAXJ` |  | `AAXJ UQ` | `AAXJ` |  | `AAXJ US` | `AAXJ` |
| `BOTZ UQ` | `BOTZ` |  | `BOTZ US` | `BOTZ` |  | `DEDZ0` | `DEDZ0.SA` |
| `DEDZ3` | `DEDZ3.SA` |  | `DEDZ9` | `DEDZ9.SA` |  | `GLD UP` | `GLD` |
| `GLD US` | `GLD` |  | `ICLN UP` | `ICLN` |  | `ICLN UQ` | `ICLN` |
| `ICLN US` | `ICLN` |  | `NDX` | `^NDX` |  | `QQQ UP` | `QQQ` |
| `QQQ US` | `QQQ` |  |  |  |  |  |  |

---

## 6. Pendências conhecidas

O que este registro deixa em aberto — nenhuma delas dá erro na tela, todas
aparecem como "sem dado" ou como preço de outro papel:

| # | Item | Situação |
|---|---|---|
| 1 | `DF"MY"` → `DF"MY".NYB` | Símbolo herdado do app de desktop. **Não confirmado na fonte**: `DFK26.NYB` e `DFH27.NYB` respondem 404 no Yahoo. Precisa da confirmação da mesa sobre que mercadoria é o `DF` da B3. |
| 2 | `CO"MY"` (Brent) | Estava como `CO"MY".NYB`, que o Yahoo **não tem** (404). Corrigido para `BZ"MY".NYM` — *Brent Crude Oil Last Day Financial*, confirmado na fonte. |
| 3 | 6 papéis não-americanos com código Bloomberg | `AIR FP`, `AIR FP_PA`, `ASML NA`, `MT NA`, `MT NA_PA`, `AZN LN` estão cadastrados com o ticker **nu**, que no Yahoo é a listagem AMERICANA. Para `ASML` e `AZN` existe ADR nos EUA e o preço vem em USD; para `AIR` (Airbus) o ticker nu é outra empresa. O correto seria `AIR.PA`, `ASML.AS`, `MT.AS`, `AZN.L`. |
| 4 | Códigos contínuos (`C 1`, `S 1`, `W 1`, `BO1`, `CC1`, `CO1`, `KC1`) | Antes apontavam para valores inválidos (`BUSHELS`, ou o mesmo `ZSK25.CBT` repetido em 18 linhas). Cadastrados agora como o contínuo do Yahoo (`ZC=F`, `ZS=F`, …), que é o 1º vencimento. Confirmar com a mesa se é essa a leitura de `1` na B3. |
| 5 | Mercadorias do Index B3 ainda sem símbolo | 683 dos 904 subjacentes ativos da classe COMMODITIES não têm de-para (LME, Platts, gás, minério, boi, etc.). Não é erro: nem toda mercadoria registrada na B3 é cotada no Yahoo. Cada uma que a mesa precisar entra como **uma** linha `"MY"`. |

---

## 7. Fontes

- Yahoo Finance — *Exchanges and data providers on Yahoo Finance* (tabela de
  sufixos de bolsa): https://help.yahoo.com/kb/exchanges-data-providers-yahoo-finance-sln2310.html
- Yahoo Finance — endpoint `chart` usado pelo app e pela biblioteca `yfinance`:
  `https://query1.finance.yahoo.com/v8/finance/chart/<simbolo>`
- Conferência dos símbolos deste documento, um a um, contra o endpoint acima em
  18/08/2026: `ZCZ26.CBT`, `ZSX26.CBT`, `ZWZ26.CBT`, `ZLZ26.CBT`, `KCZ26.NYB`,
  `SBH27.NYB`, `CTZ26.NYB`, `CCZ26.NYB`, `BZZ26.NYM` — todos responderam com o
  nome do contrato. `DFH27.NYB` e `COZ26.NYB` responderam 404 (itens 1 e 2 do §6).
- Banco Central do Brasil — Olinda/PTAX (a aba de moedas, que não usa este de-para):
  https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/

---

*Gerado dos cadastros `quotes-commodity.json` e `quotes-equity.json`. Ao alterar
o de-para pela tela `/mapping`, regenere este documento para o registro seguir
valendo.*
