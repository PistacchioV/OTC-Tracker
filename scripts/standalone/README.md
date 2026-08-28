# Conversores standalone — JSON → DuckDB

Estes scripts materializam os JSONs do OTC Tracker como bancos DuckDB. Eles são
**autocontidos**: rodam em qualquer máquina, sem o código da aplicação por
perto e sem acesso ao `config.py`.

```
pip install duckdb
```

Só isso. Nenhuma outra dependência.

---

## Por que são vários

A carga completa no share é longa. Repartida, ela pode ser **rodada em paralelo
por várias pessoas** — cada uma com o seu arquivo, ninguém esperando o outro
terminar.

Isso é seguro porque **os bancos são um por produto**: duas fatias nunca
escrevem no mesmo `.db`. Rodar sete ao mesmo tempo dá exatamente o mesmo
resultado de rodar tudo em sequência.

| Arquivo | O que converte |
|---|---|
| `00_completo.py` | Tudo de uma vez — para quem prefere um comando só |
| `01_cadastros.py` | Os JSONs **únicos**, sem quebra por dia: feriados, RefData/CounterpartyDetails, mappings, control-panel, file-interpreter, cadastros B3 |
| `02_1_new_deals.py` | `cache/new deals` — NDF (Vanilla, FWD Start, Other Publisher, Commodities), Opção (Commodities, FXO), Swap e Intrag. **É a maior fatia** |
| `02_2_b3_files.py` | `cache/b3 files` — as posições e fluxos da rotina Save CETIP Files |
| `02_3_daily_settlement.py` | `cache/daily settlement` — OTM, NDF Cockpit, Operações JPM/MGT, Eventos Swap, Cognos, BR Onshore, Latam Desk |
| `02_4_pending_confirmation.py` | `cache/pending-confirmation` — os snapshots diários |
| `02_5_payrec.py` | `cache/payrec` — o histórico da recon de Pay/Rec |
| `02_6_reconciliation.py` | `cache/reconciliation` — os caches por data das reconciliações |
| `99_outros.py` | Toda rotina de `cache/` que **não** tem arquivo próprio acima. Existe para uma rotina nova nunca ficar sem conversor — se não houver nenhuma, ele não faz nada, e isso é o resultado esperado |

**Para cobrir tudo**, rode `01` + os seis `02_*` + `99` (ou apenas `00_completo`).

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
start python 02_1_new_deals.py
start python 02_2_b3_files.py
start python 02_3_daily_settlement.py
```

---

## O que esperar

- **Idempotente e incremental.** Cada banco guarda um `_manifest` com caminho,
  mtime e tamanho de cada arquivo convertido, e só reconverte o que mudou.
  Rodar de novo sem nada alterado não reescreve nada — e é normal a segunda
  rodada terminar com `convertidos: 0`.
- **Erro num arquivo não para o resto.** Ele sai no resumo do fim, com o motivo,
  e os demais continuam.
- **Um banco por produto, uma tabela por dia.** O caminho de `cache/` vira o
  nome do banco (`daily_new_deals_ndf_vanilla.db`, `daily_b3_files_swap.db`) e
  cada dia é uma tabela `d_AAAAMMDD`. Onde a rotina não se ramifica em pastas —
  o Daily Settlement, que grava os dez arquivos do dia na mesma pasta — quem dá
  o banco é o **nome do arquivo** (`daily_settlement_otm.db`,
  `daily_settlement_ndf_cockpit.db`).
- **Um banco por JSON** para os cadastros (`mappings_mt300.db`,
  `file_interpreter_termo.db`, `subjacente.db`).
- **Bancos de formatos antigos são removidos** quando a fatia que os cobre roda.

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
