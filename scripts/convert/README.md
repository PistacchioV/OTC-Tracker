# `scripts/convert/` — a carga JSON → DuckDB, repartida

A conversão dos JSONs para os bancos DuckDB, em **nove fatias** que podem ser
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
| `01_cadastros.py` | os JSONs ÚNICOS (feriados, RefData/CPD, mappings, control-panel, file-interpreter) |
| `02_1_new_deals_ndf.py` | `cache/new deals/NDF` |
| `02_2_new_deals_option.py` | `cache/new deals/Option` |
| `02_3_new_deals_swap.py` | `cache/new deals/Swap` |
| `02_4_new_deals_intrag.py` | `cache/new deals/Intrag` |
| `02_5_b3_files_ndf.py` | `cache/b3 files/NDF` |
| `02_6_b3_files_option.py` | `cache/b3 files/Option` |
| `02_7_b3_files_swap.py` | `cache/b3 files/Swap` |
| `02_8_b3_files_operations.py` | `cache/b3 files/Operations` |
| `02_9_daily_settlement.py` | `cache/daily settlement` |
| `02_10_pending_confirmation.py` | `cache/pending-confirmation` |
| `02_11_payrec.py` | `cache/payrec` |
| `02_12_reconciliation.py` | `cache/reconciliation` |
| `99_outros.py` | o RESTO de `cache/` — a rede de segurança |

---

## Como rodar

Um comando só:

```bash
python scripts/convert/00_completo.py
```

Ou repartido — **catorze** arquivos, em qualquer ordem, ao mesmo tempo:

```bash
python scripts/convert/01_cadastros.py
python scripts/convert/02_1_new_deals_ndf.py
python scripts/convert/02_2_new_deals_option.py
python scripts/convert/02_3_new_deals_swap.py
python scripts/convert/02_4_new_deals_intrag.py
python scripts/convert/02_5_b3_files_ndf.py
python scripts/convert/02_6_b3_files_option.py
python scripts/convert/02_7_b3_files_swap.py
python scripts/convert/02_8_b3_files_operations.py
python scripts/convert/02_9_daily_settlement.py
python scripts/convert/02_10_pending_confirmation.py
python scripts/convert/02_11_payrec.py
python scripts/convert/02_12_reconciliation.py
python scripts/convert/99_outros.py
```

**As duas rotinas grandes entram repartidas por dentro.** New Deals e B3 Files
eram um bloco cada e viravam o gargalo: as outras quatro terminam em minutos e
três pessoas ficavam esperando a maior. Agora cada uma vira quatro fatias, uma
por pasta de produto.

### Se um bloco ainda for grande

`--bloco NOME` desce mais um nível, sem precisar de arquivo novo:

```bash
python scripts/convert/02_1_new_deals_ndf.py --bloco Vanilla
python scripts/convert/02_1_new_deals_ndf.py --bloco Commodities
```

Ele **substitui** o escopo da fatia, não soma — não rode
`02_1_new_deals_ndf.py` em paralelo com um `--bloco` dele. Para saber que
blocos existem, peça um que não existe: o aviso lista o que há naquele nível.

O que **não** vale é rodar o `00_completo` junto com os outros: aí sim dois
processos escreveriam no mesmo banco. Ou o `00`, ou os catorze.

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
