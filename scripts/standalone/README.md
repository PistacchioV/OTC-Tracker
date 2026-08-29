# Conversores standalone — JSON → DuckDB

Estes scripts materializam os JSONs do OTC Tracker como bancos DuckDB. Eles são
**autocontidos**: rodam em qualquer máquina, sem o código da aplicação por
perto e sem acesso ao `config.py`.

```
pip install duckdb
```

Só isso. Nenhuma outra dependência.

> **Rodando DENTRO do checkout, use o `scripts/convert/`.** Ele tem o mesmo
> corte em nove fatias, mas pergunta ao `Config` onde estão a origem e o destino
> em vez de carregar os caminhos do share fixos — e não é uma cópia do motor,
> então nunca fica para trás. Esta pasta existe para a máquina que **não tem** o
> código do app.

---

## Por que são vários

A carga completa no share é longa. Repartida, ela pode ser **rodada em paralelo
por várias pessoas** — cada uma com o seu arquivo, ninguém esperando o outro
terminar.

Isso é seguro porque **os bancos são um por produto**: duas fatias nunca
escrevem no mesmo `.db`. Rodar catorze ao mesmo tempo dá exatamente o mesmo
resultado de rodar tudo em sequência.

**As duas rotinas grandes entram repartidas por dentro.** New Deals e B3 Files
eram um bloco cada e viravam o gargalo: as outras quatro terminam em minutos e
três pessoas ficavam esperando a maior. Agora cada uma vira quatro fatias, uma
por pasta de produto.

| Arquivo | O que converte |
|---|---|
| `00_completo.py` | Tudo de uma vez — para quem prefere um comando só |
| `01_cadastros.py` | Os JSONs **únicos**, sem quebra por dia: feriados, RefData/CounterpartyDetails, mappings, control-panel, file-interpreter, cadastros B3 |
| `02_1_new_deals_ndf.py` | `cache/new deals/NDF` — Vanilla, FWD Start, Other Publisher e Commodities |
| `02_2_new_deals_option.py` | `cache/new deals/Option` — Commodities e FXO |
| `02_3_new_deals_swap.py` | `cache/new deals/Swap` — Rates e Commodities |
| `02_4_new_deals_intrag.py` | `cache/new deals/Intrag` — NDF e Opção |
| `02_5_b3_files_ndf.py` | `cache/b3 files/NDF` — DPOSICAO e DFLUXO |
| `02_6_b3_files_option.py` | `cache/b3 files/Option` |
| `02_7_b3_files_swap.py` | `cache/b3 files/Swap` — costuma ser o maior dos quatro |
| `02_8_b3_files_operations.py` | `cache/b3 files/Operations` |
| `02_9_daily_settlement.py` | `cache/daily settlement` — OTM, NDF Cockpit, Operações JPM/MGT, Eventos Swap, Cognos, BR Onshore, Latam Desk |
| `02_10_pending_confirmation.py` | `cache/pending-confirmation` — os snapshots diários |
| `02_11_payrec.py` | `cache/payrec` — o histórico da recon de Pay/Rec |
| `02_12_reconciliation.py` | `cache/reconciliation` — os caches por data das reconciliações |
| `99_outros.py` | Todo bloco de `cache/` que **não** tem arquivo próprio acima. A poda é por CAMINHO, então tanto uma rotina nova (`cache/equity`) quanto uma pasta nova dentro de uma já coberta (`cache/new deals/Equity`) caem aqui. Se não houver nada fora da lista, ele não faz nada, e isso é o resultado esperado |

**Para cobrir tudo**, rode `01` + os doze `02_*` + `99` (ou apenas `00_completo`).

### Se um bloco ainda for grande

`--bloco NOME` desce mais um nível, sem precisar de arquivo novo:

```
python 02_1_new_deals_ndf.py --bloco Vanilla
python 02_1_new_deals_ndf.py --bloco Commodities
```

Ele **substitui** o escopo da fatia, não soma — não rode `02_1_new_deals_ndf.py`
em paralelo com um `--bloco` dele. Para saber que blocos existem, peça um que
não existe: o aviso lista o que há naquele nível.

---

## Como rodar

Sem argumento nenhum, a origem e o destino já são os do share:

```
python 01_cadastros.py
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
start python 02_1_new_deals_ndf.py
start python 02_2_new_deals_option.py
start python 02_5_b3_files_ndf.py
start python 02_7_b3_files_swap.py
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
  python 02_7_b3_files_swap.py             # os últimos 12 meses (padrão)
  python 02_7_b3_files_swap.py --meses 0   # depois, o histórico INTEIRO
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
