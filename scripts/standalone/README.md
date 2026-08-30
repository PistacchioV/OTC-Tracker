# Conversores standalone — JSON → DuckDB

Estes scripts materializam os JSONs do OTC Tracker como bancos DuckDB. Eles são
**autocontidos**: rodam em qualquer máquina, sem o código da aplicação por
perto e sem acesso ao `config.py`.

```
pip install duckdb
```

Só isso. Nenhuma outra dependência.

> **Rodando DENTRO do checkout, use o `scripts/convert/`.** Ele tem o mesmo
> corte em fatias, mas pergunta ao `Config` onde estão a origem e o destino
> em vez de carregar os caminhos do share fixos — e não é uma cópia do motor,
> então nunca fica para trás. Esta pasta existe para a máquina que **não tem** o
> código do app.

---

## Por que são vários

A carga completa no share é longa. Repartida, ela pode ser **rodada em paralelo
por várias pessoas** — cada uma com o seu arquivo, ninguém esperando o outro
terminar.

Isso é seguro porque **os bancos são um por produto**: duas fatias nunca
escrevem no mesmo `.db`. Rodar vinte e oito ao mesmo tempo dá exatamente o mesmo
resultado de rodar tudo em sequência.

**As duas rotinas grandes são repartidas até o PRODUTO** — que é a folha da
árvore (abaixo dele já vem `AAAA\MM\DD`) e a unidade em que cada banco é
escrito. Repartir só até `new deals/NDF` ainda deixaria o **Vanilla**, o maior
arquivo-dia do app, junto com os outros três.

Uma pasta que a sua instância não tenha vira um aviso e a fatia sai limpa.

| Arquivo | O que converte |
|---|---|
| `00_completo.py` | tudo — cadastros + todos os blocos de `cache/` |
| `01_cadastros.py` | os JSONs ÚNICOS (feriados, RefData/CPD, mappings, control-panel, file-interpreter) |
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
| `02_14_b3_files_swap.py` | `b3 files/Swap` — costuma ser o maior dos quatro |
| `02_15_b3_files_operations.py` | `b3 files/Operations` |
| `02_16_daily_settlement_otm_settlement.py` | `daily settlement/otm-settlement` — o `.meta` ao lado vem no MESMO banco |
| `02_17_daily_settlement_ndf_cockpit.py` | `daily settlement/ndf-cockpit` |
| `02_18_daily_settlement_operations_b3.py` | `daily settlement/operations-b3` |
| `02_19_daily_settlement_operacoes_jpm.py` | `daily settlement/operacoes-jpm` |
| `02_20_daily_settlement_eventos_swap_jpm.py` | `daily settlement/eventos-swap-jpm` |
| `02_21_daily_settlement_cognos.py` | `daily settlement/cognos` |
| `02_22_daily_settlement_br_onshore_settlements.py` | `daily settlement/br-onshore-settlements` |
| `02_23_daily_settlement_other_products_summary.py` | `daily settlement/other-products-summary` |
| `02_24_pending_confirmation.py` | `pending-confirmation` — os snapshots diários |
| `02_25_payrec.py` | `payrec` — o histórico da recon de Pay/Rec |
| `02_26_reconciliation.py` | `reconciliation` — os caches por data das reconciliações |
| `99_outros.py` | o RESTO de `cache/` — a rede de segurança |

**Para cobrir tudo**, rode `01` + os vinte e seis `02_*` + `99` (ou apenas `00_completo`).

### Se um bloco ainda for grande

`--bloco NOME` desce mais um nível, sem precisar de arquivo novo:

```
python 02_12_b3_files_ndf.py --bloco Extra
```

Ele **substitui** o escopo da fatia, não soma — não rode `02_12_b3_files_ndf.py`
em paralelo com um `--bloco` dele. Para saber que blocos existem, peça um que
não existe: o aviso lista o que há naquele nível.

---

## Como rodar

Sem argumento nenhum, a origem e o destino já são os do share:

```
python 01_cadastros.py
python 02_1_new_deals_ndf_vanilla.py
python 02_2_new_deals_ndf_fwdstart.py
python 02_3_new_deals_ndf_otherpublisher.py
python 02_4_new_deals_ndf_commodities.py
python 02_5_new_deals_option_fxo.py
python 02_6_new_deals_option_commodities.py
python 02_7_new_deals_swap_rates.py
python 02_8_new_deals_swap_commodities.py
python 02_9_new_deals_intrag_ndf.py
python 02_10_new_deals_intrag_option.py
python 02_11_new_deals_intrag_swap.py
python 02_12_b3_files_ndf.py
python 02_13_b3_files_option.py
python 02_14_b3_files_swap.py
python 02_15_b3_files_operations.py
python 02_16_daily_settlement_otm_settlement.py
python 02_17_daily_settlement_ndf_cockpit.py
python 02_18_daily_settlement_operations_b3.py
python 02_19_daily_settlement_operacoes_jpm.py
python 02_20_daily_settlement_eventos_swap_jpm.py
python 02_21_daily_settlement_cognos.py
python 02_22_daily_settlement_br_onshore_settlements.py
python 02_23_daily_settlement_other_products_summary.py
python 02_24_pending_confirmation.py
python 02_25_payrec.py
python 02_26_reconciliation.py
python 99_outros.py
```

Os vinte e oito, para copiar:

```
python 01_cadastros.py
python 02_1_new_deals_ndf_vanilla.py
python 02_2_new_deals_ndf_fwdstart.py
python 02_3_new_deals_ndf_otherpublisher.py
python 02_4_new_deals_ndf_commodities.py
python 02_5_new_deals_option_fxo.py
python 02_6_new_deals_option_commodities.py
python 02_7_new_deals_swap_rates.py
python 02_8_new_deals_swap_commodities.py
python 02_9_new_deals_intrag_ndf.py
python 02_10_new_deals_intrag_option.py
python 02_11_new_deals_intrag_swap.py
python 02_12_b3_files_ndf.py
python 02_13_b3_files_option.py
python 02_14_b3_files_swap.py
python 02_15_b3_files_operations.py
python 02_16_daily_settlement.py
python 02_17_pending_confirmation.py
python 02_18_payrec.py
python 02_19_reconciliation.py
python 99_outros.py
```

O share tem **dois endereços para o mesmo lugar** — o UNC e a letra `I:`
mapeada —, e qual deles existe depende da máquina. Os scripts tentam nessa
ordem e usam o primeiro que responder:

```
\\Nawest.ad.jpmorganchase.com\lac\BRA\intra\...\static\data
I:\Confirmation\Derivativos\OTC Tracker\Application\static\data
```

O destino é a pasta `db` dentro da origem. A primeira linha da saída diz qual
caminho valeu — confira antes de deixar rodando:

```
origem : \\Nawest.ad.jpmorganchase.com\...\static\data
destino: \\Nawest.ad.jpmorganchase.com\...\static\data\db
escopo : cadastros (sem quebra por dia)
```

Opções:

| Flag | Para quê |
|---|---|
| `--dry-run` | Só lista o que seria convertido, sem escrever nada |
| `--force` | Reconverte tudo, mesmo o que não mudou |
| `--data-dir` | Outra origem |
| `--out-dir` | Outro destino |

Exemplo de uma rodada em paralelo, no Windows:

```
start python 01_cadastros.py
start python 02_1_new_deals_ndf_vanilla.py
start python 02_4_new_deals_ndf_commodities.py
start python 02_5_new_deals_option_fxo.py
start python 02_14_b3_files_swap.py
```

---

## O que esperar

- **Idempotente e incremental.** Cada banco guarda um `_manifest` com caminho,
  mtime e tamanho de cada arquivo convertido, e só reconverte o que mudou.
  Rodar de novo sem nada alterado não reescreve nada — e é normal a segunda
  rodada terminar com `convertidos: 0`.
- **Erro num arquivo não para o resto.** Ele sai no resumo do fim, com o motivo,
  e os demais continuam.
- **A pasta `db` espelha a árvore de origem.** O caminho de `cache/` vira
  PASTA e o produto vira o arquivo; **ano, mês e dia não viram pasta** — eles
  já são a tabela `d_AAAAMMDD` dentro do banco:

  ```
  db/
  ├── cache/
  │   ├── new deals/NDF/Vanilla.db          (uma tabela por dia)
  │   ├── new deals/Option/FXO.db
  │   ├── b3 files/Swap.db
  │   ├── daily settlement/otm-settlement.db
  │   ├── daily settlement/cognos.db
  │   └── pending-confirmation.db
  ├── mappings/mt300.db
  ├── control-panel/mt300_status.db
  ├── file-interpreter/termo.db
  ├── reference_data.db
  └── Subjacente.db                          (os JSONs de raiz ficam na raiz)
  ```

  Onde a rotina não se ramifica em pastas — o Daily Settlement, que grava os
  dez arquivos do dia na mesma pasta — quem dá o banco é o **nome do arquivo**,
  dentro da pasta da rotina.
- **A janela é de 12 meses por padrão.** Os arquivo-dia mais antigos que isso
  não são convertidos e saem contados como `fora da janela`. A carga completa no
  share leva horas de rede, e o dado recente é o que a mesa consulta — o
  histórico entra numa SEGUNDA passada:

  ```
  python 02_14_b3_files_swap.py            # os últimos 12 meses (padrão)
  python 02_14_b3_files_swap.py --meses 0  # depois, o histórico INTEIRO
  ```

  A janela sai declarada na primeira linha da saída, junto da origem e do
  destino, e `--meses N` a muda. Duas coisas que ela NÃO faz:
  - **não recorta os cadastros** — o `01_cadastros.py` nem recebe o argumento,
    porque nenhum daqueles JSONs tem data para cortar;
  - **não apaga banco de formato antigo.** Aqueles guardam o histórico inteiro,
    e a passada com janela escreve só doze meses: trocar um pelo outro seria uma
    perda até a segunda passada terminar. Quem limpa é o `--meses 0`, que é o
    que de fato substitui o que estava lá.

  A data vem do **caminho** do arquivo (`AAAA/MM/DD`), nunca da data em que ele
  foi gravado: um dia de 2024 recopiado para o share este mês continua sendo de
  2024.
- **Bancos de formatos antigos são removidos** quando a fatia que os cobre roda
  **sem janela** (`--meses 0`).
- **`convertidos: 0 | inalterados: 0` numa primeira rodada quer dizer que a
  rotina não está naquela máquina**, e o script diz isso com todas as letras:

  ```
  == daily -> daily_<produto>.db (um por produto)
     convertidos: 0 | inalterados: 0
     ! cache/daily settlement: bloco ausente em disco.
       Dentro de cache há: b3 files, new deals, payrec
  ```

  A lista de rotinas encontradas é o que resolve o caso: se a pasta está lá com
  **outro nome**, é ela que aparece ali. A grafia em si não atrapalha — o
  script casa `b3 files`, `B3 Files` e `B3-Files` como a mesma rotina —, mas um
  nome de fato diferente precisa de `--data-dir` ou de um ajuste na pasta.

---

## Não edite estes arquivos

Eles são **gerados** a partir de `apps/pages/json_to_duckdb.py`, que é o motor
que a própria aplicação usa — é isso que garante que o banco gerado aqui seja
igual ao que o app produz. Para atualizá-los depois de uma mudança no motor:

```
python scripts/build_duckdb_standalone.py
```

O teste `scripts/tests/check_duckdb_standalone.py` reprova qualquer divergência
entre estes arquivos e o motor.

A **lista de rotinas** (quais ganham um `02_*` próprio) também não se edita aqui
nem no gerador: ela mora no motor (`ROTINAS_CACHE`), porque o `scripts/convert/`
a consome também. Escrita nos dois lugares, uma rotina acrescentada num lado
ficaria coberta só pelo `99_outros` do outro — e a diferença apareceria como uma
fatia que demora muito mais do que a irmã, nunca como erro.
`scripts/tests/check_convert_split.py` prende isso.
