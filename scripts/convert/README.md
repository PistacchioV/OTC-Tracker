# `scripts/convert/` — a carga JSON → DuckDB, repartida

A conversão dos JSONs para os bancos DuckDB, em **39 fatias** que podem ser
rodadas por pessoas diferentes ao mesmo tempo.

Esta é a versão que roda **dentro do checkout**: ela pergunta ao `Config` do app
onde estão a origem (`DATA_DIR`) e o destino (`DATABASE_DIR`). Para uma máquina
que **não tem o código do OTC Tracker** existe o `scripts/standalone/`, com o
mesmo corte e os caminhos do share fixos.

O `scripts/convert_json_to_duckdb.py` continua existindo e é a carga completa
num comando só — o `00_completo.py` daqui é ele, com o mesmo escopo.

---

## Por que são vários

A carga completa no share leva horas de rede. Repartida, ela pode ser rodada
**em paralelo**, e é seguro: os bancos são **um por produto**, então duas fatias
nunca escrevem no mesmo arquivo. Isso é prendido por teste
(`scripts/tests/check_convert_split.py`).

| arquivo | escopo |
|---|---|
| `00_completo.py` | tudo — cadastros + todos os blocos de `cache/` |
| `01_cadastros.py` | o RESTO dos cadastros — calendários, RefData/CPD e os JSONs da raiz. É o complemento das quatro fatias abaixo: pasta de cadastro NOVA cai aqui |
| `01_1_mappings.py` | `mappings/` — os 43 cadastros do /mapping, um banco cada |
| `01_2_file_interpreter.py` | `file-interpreter/` — templates e variantes |
| `01_3_control_panel.py` | `control-panel/` — o estado das rotinas |
| `01_4_tickets.py` | `tickets/` — o store do Support Center |
| `02_1_new_deals_ndf_vanilla.py` | `new deals/NDF/Vanilla` — costuma ser o maior arquivo-dia do app |
| `02_2_new_deals_ndf_fwdstart.py` | `new deals/NDF/FwdStart` — o FWD Start (a pasta é SEM espaço) |
| `02_3_new_deals_ndf_otherpublisher.py` | `new deals/NDF/OtherPublisher` |
| `02_4_new_deals_ndf_commodities.py` | `new deals/NDF/Commodities` — o termo de mercadoria |
| `02_5_new_deals_option_fxo.py` | `new deals/Option/FXO` — a opção de câmbio |
| `02_6_new_deals_option_commodities.py` | `new deals/Option/Commodities` |
| `02_7_new_deals_swap_rates.py` | `new deals/Swap/Rates` |
| `02_8_new_deals_swap_commodities.py` | `new deals/Swap/Commodities` |
| `02_9_new_deals_intrag_ndf.py` | `new deals/Intrag/NDF` |
| `02_10_new_deals_intrag_option.py` | `new deals/Intrag/Option` |
| `02_11_new_deals_intrag_swap.py` | `new deals/Intrag/Swap` |
| `02_12_b3_files_ndf.py` | `b3 files/NDF` — DPOSICAO e DFLUXO da rotina Save CETIP Files |
| `02_13_b3_files_option.py` | `b3 files/Option` |
| `02_14_b3_files_swap.py` | `b3 files/Swap` — o maior dos quatro, e o único cujo dia guarda três arquivos (posição · fluxo · agenda de prêmios), um banco cada |
| `02_15_b3_files_operations.py` | `b3 files/Operations` |
| `02_16_daily_settlement_otm_settlement.py` | `daily settlement/otm-settlement` — o `.meta` ao lado vem no MESMO banco |
| `02_17_daily_settlement_ndf_cockpit.py` | `daily settlement/ndf-cockpit` |
| `02_18_daily_settlement_operations_b3.py` | `daily settlement/operations-b3` — o arquivo DERIVADO que a página lê (JPM + MGT + o que a tela edita) |
| `02_19_daily_settlement_operacoes_jpm.py` | `daily settlement/operacoes-jpm` — uma das ORIGENS dele |
| `02_20_daily_settlement_operacoes_mgt.py` | `daily settlement/operacoes-mgt` — a outra |
| `02_21_daily_settlement_eventos_swap_jpm.py` | `daily settlement/eventos-swap-jpm` |
| `02_22_daily_settlement_eventos_swap_mgt.py` | `daily settlement/eventos-swap-mgt` |
| `02_23_daily_settlement_latam_desk_position.py` | `daily settlement/latam-desk-position` |
| `02_24_daily_settlement_swap_kapital_hybrids.py` | `daily settlement/swap-kapital-hybrids` |
| `02_25_daily_settlement_cognos.py` | `daily settlement/cognos` |
| `02_26_daily_settlement_br_onshore_settlements.py` | `daily settlement/br-onshore-settlements` |
| `02_27_daily_settlement_other_products_summary.py` | `daily settlement/other-products-summary` |
| `02_28_pending_confirmation.py` | `pending-confirmation` — os snapshots diários |
| `02_29_payrec.py` | `payrec` — o histórico da recon de Pay/Rec |
| `02_30_reconciliation_fxo.py` | `reconciliation/fxo` — o cache por data da recon de FXO |
| `02_31_reconciliation_cgd.py` | `reconciliation/cgd` — idem, a de CGD |
| `02_32_reconciliation_payrec.py` | `reconciliation/payrec` — idem, a de Pay/Rec |
| `99_outros.py` | o RESTO de `cache/` — a rede de segurança |

---

## Como rodar

Um comando só:

```bash
python scripts/convert/00_completo.py
```

Ou repartido — **trinta e oito** arquivos, em qualquer ordem, ao mesmo tempo:

```bash
python scripts/convert/01_cadastros.py
python scripts/convert/01_1_mappings.py
python scripts/convert/01_2_file_interpreter.py
python scripts/convert/01_3_control_panel.py
python scripts/convert/01_4_tickets.py
python scripts/convert/02_1_new_deals_ndf_vanilla.py
python scripts/convert/02_2_new_deals_ndf_fwdstart.py
python scripts/convert/02_3_new_deals_ndf_otherpublisher.py
python scripts/convert/02_4_new_deals_ndf_commodities.py
python scripts/convert/02_5_new_deals_option_fxo.py
python scripts/convert/02_6_new_deals_option_commodities.py
python scripts/convert/02_7_new_deals_swap_rates.py
python scripts/convert/02_8_new_deals_swap_commodities.py
python scripts/convert/02_9_new_deals_intrag_ndf.py
python scripts/convert/02_10_new_deals_intrag_option.py
python scripts/convert/02_11_new_deals_intrag_swap.py
python scripts/convert/02_12_b3_files_ndf.py
python scripts/convert/02_13_b3_files_option.py
python scripts/convert/02_14_b3_files_swap.py
python scripts/convert/02_15_b3_files_operations.py
python scripts/convert/02_16_daily_settlement_otm_settlement.py
python scripts/convert/02_17_daily_settlement_ndf_cockpit.py
python scripts/convert/02_18_daily_settlement_operations_b3.py
python scripts/convert/02_19_daily_settlement_operacoes_jpm.py
python scripts/convert/02_20_daily_settlement_operacoes_mgt.py
python scripts/convert/02_21_daily_settlement_eventos_swap_jpm.py
python scripts/convert/02_22_daily_settlement_eventos_swap_mgt.py
python scripts/convert/02_23_daily_settlement_latam_desk_position.py
python scripts/convert/02_24_daily_settlement_swap_kapital_hybrids.py
python scripts/convert/02_25_daily_settlement_cognos.py
python scripts/convert/02_26_daily_settlement_br_onshore_settlements.py
python scripts/convert/02_27_daily_settlement_other_products_summary.py
python scripts/convert/02_28_pending_confirmation.py
python scripts/convert/02_29_payrec.py
python scripts/convert/02_30_reconciliation_fxo.py
python scripts/convert/02_31_reconciliation_cgd.py
python scripts/convert/02_32_reconciliation_payrec.py
python scripts/convert/99_outros.py
```

**As duas rotinas grandes são repartidas até o PRODUTO** — que é a folha da
árvore (abaixo dele já vem `AAAA/MM/DD`) e a unidade em que cada banco é
escrito. Elas eram um bloco cada e viravam o gargalo: as outras quatro rotinas
terminam em minutos e o resto da equipe ficava esperando a maior. Repartir só
até `new deals/NDF` ainda deixaria o **Vanilla** — o maior arquivo-dia do app —
junto com os outros três.

**Um escopo é sempre o caminho do que ele produz** — e é por isso que o Daily
Settlement é repartido por ARQUIVO (ali quem separa os produtos é o nome, não a
pasta) e que cada RECONCILIAÇÃO é uma fatia: as três têm pasta e banco próprios
em `cache/reconciliation/`.

No **B3 Files** o produto é uma PASTA de bancos: a pasta do dia de cada produto
guarda mais de um arquivo — o Swap tem posição, fluxo e agenda de prêmios —, e
cada um vira o seu `.db`. A fatia continua sendo por produto (`b3 files/Swap`,
que escreve os três); para repartir mais, `--bloco 73760_DPOSICAO-SWAP` desce
até um arquivo.

Uma pasta que a sua instância não tenha vira um aviso e a fatia sai limpa; e um
produto que não esteja na lista (`new deals/NDF/Asian`) cai no `99_outros`, que
poda por caminho.

### Se um bloco ainda for grande

`--bloco NOME` desce mais um nível, sem precisar de arquivo novo:

```bash
python scripts/convert/02_12_b3_files_ndf.py --bloco Extra
```

Ele **substitui** o escopo da fatia, não soma — não rode
`02_12_b3_files_ndf.py` em paralelo com um `--bloco` dele. Para saber que
blocos existem, peça um que não existe: o aviso lista o que há naquele nível.

O que **não** vale é rodar o `00_completo` junto com os outros: aí sim dois
processos escreveriam no mesmo banco. Ou o `00`, ou os trinta e oito.

O `99_outros` parece dispensável e não é: ele pega qualquer bloco de `cache/`
que não tenha script próprio, e a poda dele é por **caminho** — tanto uma rotina
nova (`cache/equity`) quanto uma pasta nova dentro de uma já coberta
(`cache/new deals/Equity`) caem ali. Sem ele, uma pasta que a dev não tem
ficaria de fora sem ninguém perceber.

---

## A janela de 12 meses

Os arquivo-dia são convertidos **só dos últimos 12 meses** por padrão. O
histórico entra numa **segunda passada**:

```bash
python scripts/convert/02_2_b3_files.py             # os últimos 12 meses
python scripts/convert/02_2_b3_files.py --meses 0   # depois, o histórico INTEIRO
```

A janela sai declarada na saída, junto da origem e do destino. Duas coisas que
ela não faz:

- **não recorta os cadastros** — o `01_cadastros.py` nem aceita `--meses`,
  porque nenhum daqueles JSONs tem data para cortar;
- **não apaga banco de formato antigo.** Aqueles guardam o histórico inteiro e a
  passada com janela escreve só doze meses; quem limpa é o `--meses 0`.

A data vem do **caminho** do arquivo (`AAAA/MM/DD`), nunca do `mtime`: um dia de
2024 recopiado para o share este mês continua sendo de 2024.

---

## O que esperar

- **Idempotente e incremental** (`_manifest` por banco): rodar de novo só
  reconverte o que mudou, e a segunda rodada terminar em `convertidos: 0` é o
  resultado normal.
- **`| já cobertos por outro conversor: N`** no `01_cadastros` não é perda: são
  o RefData/CPD e os arquivos de calendário, que as etapas `refdata` e
  `holidays` da mesma rodada convertem.
- **`convertidos: 0 | inalterados: 0` numa primeira rodada** quer dizer que a
  rotina não existe nesta instância, e o script diz isso com todas as letras,
  listando as rotinas que ele achou.
- **Erro num arquivo não para o resto** — sai no resumo, com o motivo.
- `--dry-run` mostra o que faria sem escrever nada; `--force` reconverte tudo;
  `--data-dir`/`--out-dir` mudam origem e destino.

---

## Não edite a lista de rotinas aqui

Ela mora no motor (`apps.pages.json_to_duckdb.ROTINAS_CACHE`), porque os DOIS
splits a consomem. Escrita em cada script, um bloco acrescentado num lado
ficaria coberto só pelo `99_outros` do outro — e a diferença apareceria como uma
fatia que demora muito mais do que a irmã, nunca como erro.

E os arquivos desta pasta são **gerados**:

```bash
python scripts/build_convert_split.py
```

O `check_convert_split.py` reprova quem esquecer de rodar, e o gerador REMOVE a
fatia que saiu do `ROTINAS_CACHE` — um arquivo órfão continuaria rodando com um
escopo que ninguém mais declara, agora coberto também pelo `99_outros`: dois
processos no mesmo banco, sem nada na pasta dizendo isso.
