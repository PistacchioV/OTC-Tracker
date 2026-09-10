# CLAUDE.md

Guia para o Claude Code trabalhar neste repositório. Reescrito do zero em
09/09/2026: a versão anterior tinha 3.300 linhas acumuladas em ~430 sessões.
O histórico de cada decisão continua no [`HANDOFF.md`](HANDOFF.md) — um `§N`
neste arquivo aponta para a seção de lá.

O OTC Tracker é uma aplicação Flask **interna do JPMorgan** que cobre o ciclo
de vida de derivativos de balcão: registro, economic affirmation, liquidação e
documentos transacionais. Duas coisas explicam quase toda regra não óbvia
abaixo: **um processo só serve a mesa inteira**, e **os dados vivem num share
SMB**, onde cada `stat`, cada abertura de banco e cada lock é ida e volta de
rede.

---

## 1. Comandos

```bash
source .venv311/bin/activate        # o diretório diz 311, o Python é 3.12
pip install -r requirements.txt
flask run --port=5005               # macOS: NUNCA 5000 (AirPlay) — §9
gunicorn --config gunicorn-cfg.py run:app   # produção alternativa; a instância usa waitress
```

```bash
npm install && npm run dev          # gulp em watch: scss/**/*.scss → static/css/
npm run build
```

Copie `env.sample` para `.env` com pelo menos `FLASK_APP=run.py`. Fora do
Windows **`OTC_SHARED_DRIVE_ROOT` é obrigatória** (§9). O modo debug é a flag
`DEBUG` no topo do `run.py`, não o `.env`.

```bash
OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_<nome>.py
```

---

## 2. As regras que não se negociam

- **Branch de trabalho: `StreamFlow`. Prod do JPM: `StreamFlow-prod`.** A prod
  é a dev MAIS um commit no `apps/config.py` — o bloco de seis linhas entre
  `── ENV:DEV ──` e `── /ENV ──` (dados, bancos e share em
  `\\Nawest.ad.jpmorganchase.com\lac\BRA\intra` em vez de dentro do checkout e
  `I:\`). Código nasce na dev e chega lá por merge (`/commit` publica na dev,
  `/commitjp` faz o merge). Corrigir direto na prod cria divergência invisível
  até o merge seguinte conflitar. Nunca presuma `main`.
- **O bloco DEV BYPASS (`/dev-login`) do `routes.py` nunca vai para o
  repositório.** É removido antes de cada commit e restaurado depois.
- **Nunca fixe um de-para novo no código.** Tudo que é mapeável se cadastra
  pela tela `/mapping` (§6). Regra permanente do usuário.
- **Um processo só.** waitress `--threads=16`, `workers = 1` no gunicorn. Com
  dois processos o singleton do banco, o `_cache_lock` e os schedulers deixam
  de proteger qualquer coisa (§4).
- **Caminho de dado nunca se monta à mão.** JSONs pelo `data_paths.py`
  (`data_path`/`data_write`/`mapping_file`), bancos pelo `Config.DATABASE_DIR`,
  share pelo `Config.SHARED_DRIVE_ROOT`. Um literal `I:\...` ou
  `static/data/...` no fonte continua lendo o lugar antigo no dia em que os
  dados mudam de casa, sem erro nenhum. `check_config_names.py` recusa por AST.
- **`json.dump` é proibido fora do funil `_atomic_write_json`** em
  `apps/pages` (`check_duck_writers.py`), e o funil grava NO BANCO: desde
  09/09/2026 (§434) escrita e leitura de dado são só nos DuckDB — não existe
  mais JSON como cópia de escrita nem espelho. Leitura de dado é pelo
  `data_store` (`read`/`isfile`/`stat`/`listdir`/`walk`), nunca `open` +
  `json.load` num caminho do `DATA_DIR`.
- **Todo valor de request/sessão/planilha/e-mail entra no SQL como parâmetro
  `?`.** Só DDL sobre identificadores do próprio código (`_PC_TABLE`,
  `_PC_COLUMNS`) monta string. Referência vendorizada:
  `Docs/SQL_Injection_Prevention_Cheat_Sheet.md`.
- **Design: tokens `--vr-*`/`--ins-*`, jamais `--bs-*`** (o tema não os define;
  caem no fallback claro e viram cartão branco no escuro). A pintura atual é o
  StreamFlow (`static/css/streamflow.css` + `streamflow.js`), camada carregada
  DEPOIS do `visual-refresh.css` que redefine os mesmos tokens — por isso
  continua se escrevendo `--vr-*`. Armadilhas do vidro em §7.
- **i18n: texto visível nasce em INGLÊS e é traduzido por `data-lang`**
  (`static/data/translations/{en,br,es}.json`). O `I18nManager` traduz UMA vez
  no load; o que o JS insere depois sai de um mapa `_TRANS` local com `t()`
  lendo `localStorage['__OTC_TRACKER_LANG__']`. Texto de servidor exibido pela
  tela vem ESTRUTURADO (a lista, não a frase).
- **E-mail: cabeçalho é cor sólida + gradiente CSS, nunca imagem/VML** (o
  `<v:rect>` do Outlook pintava o banner na largura errada). VML só em botão de
  largura FIXA (`v:roundrect`); botão ganha altura com `height` +
  `line-height`, nunca padding vertical (§257).
- **Escale com threads, não com workers.** Com os dados no share a maior parte
  de um request é espera de rede com a thread parada; 4 threads (padrão do
  waitress) param o servidor inteiro.

---

## 3. Arquitetura

### Ciclo do request

`run.py` lê `DEBUG` → `DebugConfig`/`ProductionConfig` (`apps/config.py`) →
`create_app()` (`apps/__init__.py`) registra extensões e importa
`apps.pages.routes`. **Um único blueprint** (`pages_blueprint`) é dono de todas
as rotas. `create_app` confere `_REQUIRED_CONFIG_NAMES` antes dos blueprints e
recusa subir se o `config.py` ficou para trás num pull (§9).

### Onde o código mora

| Camada | O que é |
|---|---|
| `apps/pages/routes.py` (~13,6 mil linhas) | casca e plataforma miúda: sessão/authz-endpoints, sino, `_MAPPING_DEFS`, leitores `_ndfc_*`/`_ndfsum_*`/`_ndfadv_*`, Daily Settlement `_ds_*`, wiring das features e os ALIASES (`_x = _pf_anbima._x`) |
| `apps/pages/platform/` (17 módulos) | infra horizontal: `anbima`, `authz`, `db`, `dates`, `json_cache`, `mail`, `notifications` e os motores `settlement`, `confirmations`, `counterparty`, `forecast`, `electronic_inventory`, `manual_confirmation`, `file_interpreter`, `pending_confirmation`, `operations_b3`, `new_deals` |
| `apps/pages/features/<nome>/` (44 verticais) | `entrypoint.py` (rotas) · `commands.py` (escrita) · `queries.py` (leitura) · `domain.py` (regras puras) · `infra/` — todas em desenho fino; não existe mais `engine.py` |
| `apps/pages/database_access.py` | a camada de banco: permit + lock de arquivo + farol de eventos (§4) |
| `data_store.py` · `duck_read.py` · `json_to_duckdb.py` | o ARMAZÉM (o `DATA_DIR` como sistema de arquivos virtual sobre os DuckDB), a fachada de leitura com os nomes antigos, o motor de conversão (§4) |
| `data_paths.py` · `request_cache.py` | caminhos de dado; `once_per_request`/`req_cached` |
| `manual_conf.py` · `cgd_docs.py` · `otc_tickets.py` | donos dos bancos da esteira, do Onboarding e do store de tickets |
| `athena_api.py` · `otc_boxparse.py` · `otc_boxscan.py` · `otc_emails.py` · `webpush.py` | Athena (SSO Kerberos), parser do recap, varredura do box, e-mails, push |
| `recon_fxo.py` · `recon_cgd.py` · `recon_payrec.py` · `recon_comitente.py` | motores das recons |
| `confirmation_pdfs.py` · `forecast_charts.py` · `quotes.py` · `precificador/` | PDFs em reportlab, gráficos, cotações, motor de mercado das Tools (puro, sem Flask) |

Templates: `layouts/base.html` → `layouts/vertical.html` (o único layout) →
`pages/*.html`. `partials/sidenav.html` é o único menu.

### Adicionar uma página

1. Rota no entrypoint da vertical (ou no `routes.py` se for plataforma)
   devolvendo `render_template('pages/<nome>.html', segment='<nome>')`.
2. Template em `apps/templates/pages/` estendendo o layout.
3. SCSS opcional em `apps/static/scss/`.
4. Tabela → padrão de tabela do §7, sem exceção.
5. Notificação nova → rótulo nos TRÊS mapas (§8, Notificações).

### As regras das verticais (quebram sem erro)

- **Feature nunca importa NOME do `routes`, só o MÓDULO, e dentro da função**
  (`from apps.pages import routes` → `routes.X`). Cinquenta e tantos testes
  trocam atributos no `routes` (`R.DB_PATH = tmp`, `R._create_notification =
  espião`); um `from routes import X` congela o valor no import e o teste passa
  lendo dado REAL.
- **Toda travessia entre camadas é pelo atributo do módulo**
  (`queries._x(...)`), nunca `from .queries import x` — é o que deixa o espião
  interceptar a chamada que vem de outra camada. `domain` é puro: não importa
  `routes`, não toca banco nem SMTP; para log usa
  `logging.getLogger('otc_tracker')`.
- **Entrypoint que o `routes.py` não importa é rota que não existe** (404, sem
  aviso). O bloco de imports fica no FIM do `routes.py` de propósito.
- **Scheduler de feature é registrado no `routes.py`** (`_schedule_on_start`),
  não no módulo da feature — importar `routes` de lá fecharia o ciclo. Todos
  respeitam `OTC_DISABLE_SCHEDULERS=1` (kill-switch dos testes).
- **Platform nunca importa feature nem nome do routes**; o que ainda é do
  `routes` é busca atrasada dentro da função. Estado mora na platform (alias de
  objeto rebindado apontaria para o velho); constante que referencia outro
  módulo da platform importa direto.
- **Chamada interna do módulo não passa pelo alias**: teste que troca função
  chamada por DENTRO da fatia troca nos dois lugares. `session` do Flask é
  superfície de patch (`routes.session`).
- **Guarda que varre `routes.py` por AST para de cobrir o que saiu de lá.**
  Ao mover código, atualize o guarda na mesma mudança; o certo é varrer
  `routes.py` + `features/**` + `platform/**` de uma vez (`_fontes_com_rotas`).
- **Mexeu no motor `json_to_duckdb.py`: regere `scripts/standalone/` e
  `scripts/convert/`** (`build_duckdb_standalone.py`, `build_convert_split.py`)
  e commite. `check_duckdb_standalone.py`/`check_convert_split.py` reprovam.

`check_soc_layers.py` prende tudo isso, inclusive subindo o app e conferindo o
`url_map`, e desmonta o bytecode das features cobrando que todo `LOAD_GLOBAL`
exista no módulo (`__module__` mente sob `functools.wraps`; quem diz é o
`co_filename`).

---

## 4. Dados, bancos e concorrência

### Onde cada coisa vive

- **`Config.DATA_DIR`** — a raiz dos CAMINHOS de dado: arquivos-dia
  (`cache/<rotina>/.../AAAA/MM/DD`), os 45 cadastros do `/mapping`
  (`mappings/`), `RefData.json`, `CounterpartyDetails.json`, calendários,
  templates do File Interpreter, tickets, control-panel. O app fala nesses
  caminhos `.json`, mas desde §434 o CONTEÚDO vive nos bancos (seção
  seguinte); no disco ficam só o que não é JSON (anexos, imagens de ticket,
  `.lock` do claim) e `translations/`. Gitignorado, montado por
  `data_paths.py`. Na subida `_seed_data_dir()` importa para o banco o JSON
  versionado que o banco não tem, **sem sobrescrever** (o que está no banco é
  o que a mesa editou), e copia o que não é JSON; `db/` fica de fora.
  **Leitura cai para a cópia empacotada** (pelo `data_path()`) quando o banco
  não tem o caminho; **escrita nunca cai**.
- **`Config.DATABASE_DIR`** (`OTC_DATABASE_DIR`) — TODOS os bancos: usuários,
  notificações, os três do Pending Confirmation, os dois da esteira, o do
  Onboarding, o de comitentes e os bancos por produto do armazém em `db/`.
  Absoluto obrigatório; relativo é recusado na subida.
- **`Config.SHARED_DRIVE_ROOT`** (`OTC_SHARED_DRIVE_ROOT`, padrão `I:\`) — os
  destinos do share: confirmações, Electronic Inventory, CETIP, B3 Files, os
  pontos de entrada das recons, o `link.txt` da versão.
- **`/static/data/...` do navegador também sai do `DATA_DIR`**: a rota
  `static_data_file` resolve pelo `data_path()` e vence o `/static/<path>`
  embutido; serve RefData/CPD/calendários do BANCO quando fresco. Raiz e caminho
  relativo vão separados ao `send_from_directory` (é o `safe_join` dele que
  recusa `..`).

### O ARMAZÉM: escrita e leitura SÓ nos bancos (09/09/2026, §434)

Todo dado do app vive nos DuckDB, e só neles. O `apps/pages/data_store.py`
apresenta o `DATA_DIR` como um **sistema de arquivos virtual** sobre os
bancos: o app continua falando em caminhos de `.json` (`jp`, `fpath`), mas
`read`/`isfile`/`stat`/`listdir`/`walk`/`day_files`/`remove` respondem pelo
`_manifest` e pelas tabelas, e o funil `_atomic_write_json` grava a tabela
do caminho (reconstruída sob a trava exclusiva do arquivo, pelo
`duckdb_write`) — nenhum JSON é escrito. O espelho (`duck_mirror`) e a cura
síncrona/quarentena deixaram de existir; o `duck_read` é só a fachada com os
nomes que o app conhecia (`day_records`, `dataset_rows`, `refdata_rows`,
`calendar_rows`, `day_files`, `prefetch_days`).

- **O banco é o de sempre, e a tabela-dia é SÓ o canal cru** (§437). Mesma
  quebra por produto (`db/` espelha a árvore de origem), mesmo `_manifest`
  (caminho, mtime, tamanho, targets). Quem diz que banco/tabela um caminho
  ocupa é `json_to_duckdb.target_of` — o mesmo da importação de JSON legado,
  então banco importado e banco gravado pela tela têm uma forma só. Os
  `mtime`/`fsize` do manifest passaram a ser o relógio da gravação e o
  tamanho do texto: são só a chave dos memos. **Arquivo-dia (`cache/`) vira
  `_seq`/`_raw` e nada mais; payload-objeto de dia vira só a `<tabela>__raw`**
  — o DuckDB lê o CATÁLOGO inteiro a cada `connect`, e 250 dias × 170
  colunas tipadas do DPOSICAO-TER eram 524 blocos de metadado (134 MB em
  sub-blocos de 4 KB, cada um uma ida e volta no share): minutos por
  abertura. Só com `_seq`/`_raw`, 7 blocos. Datasets (mappings, RefData, CPD,
  registro) continuam tipados + `_raw`: um banco, uma tabela, catálogo
  barato. Banco antigo na forma tipada segue legível; `scripts/slim_duckdb.py`
  o leva à forma nova NO LUGAR, copiando do próprio banco (nunca do JSON).
- **Payload-OBJETO volta EXATO** (recons, `.meta.json`, ponteiros `_last`):
  além das sub-tabelas de análise, o objeto inteiro vai como texto na tabela
  `<tabela>__raw` de uma linha. Banco anterior a isto tem o objeto sem o
  `__raw`; `reconstruivel` faz a importação reconvertê-lo mesmo com o manifest
  casando. Todo `.json` do `DATA_DIR` tem banco — inclusive os ponteiros
  `_last` e configs sem data, que antes ficavam de fora porque o JSON
  respondia por eles.
- **Caminho fora do `DATA_DIR` é disco de verdade.** As funções do armazém
  caem em `os.*` para o que não é `.json` sob a raiz de dados (o share dos
  documentos, uploads, anexos) e para `translations/` (i18n, versionada como
  código) e `db/`. É o que torna a troca `open+json.load → _store.read`
  segura onde o chamador não sabe de onde o caminho veio — e é por isso que a
  varredura mecânica trocou os ~110 leitores, 185 `isfile`, 34 varreduras e
  24 `stat` de uma vez.
- **A cópia empacotada continua sendo do `data_path()`**: `_seed_data_dir`
  importa para o banco, na subida, todo JSON versionado que o banco não tem;
  antes disso, `data_path()` devolve o caminho do repositório (fora da raiz,
  lido do disco). O armazém em si nunca cai para o pacote — um leitor com
  caminho explícito lê o que pediu, ou nada (é o que deixa um teste com a
  raiz num tmp ler só o que gravou).
- **Legado em disco: importação PREGUIÇOSA no ponto, nunca na enumeração.**
  A primeira leitura de um caminho que o banco não tem e o disco tem responde
  pelo ARQUIVO na hora e manda a importação para uma thread (`store-import`,
  uma por caminho, que desiste sob a trava se o banco ganhou o caminho nesse
  meio-tempo — `so_se_ausente`): no share um DPOSICAO-TER leva dezenas de
  segundos para entrar no banco, e importá-lo dentro do request parava quem
  clicou e derrubava em OCUPADO quem lia o mesmo banco. Teste que precisa do
  banco pronto chama `data_store.import_wait()`. O TEXTO do arquivo entra no
  memo de processo com o carimbo do disco (a chave que o manifest vai ter):
  os leitores seguintes do mesmo caminho e o aquecimento não releem o share
  até a importação landar. `listdir`/`walk`/`day_files` são só
  pelo banco — arquivo que ninguém leu fica invisível para quem enumera, e
  por isso o cutover pede a carga completa
  (`scripts/convert_json_to_duckdb.py --meses 0`): a instância tem 12 meses
  nos bancos, o resto só no disco.
- **O "mudou?" é o `stat` do PRÓPRIO `.db`** (o DuckDB reescreve o arquivo no
  checkpoint), memoizado por request; o manifest de cada banco fica em cache
  enquanto o `.db` não muda, e o canal cru de cada caminho no memo de
  processo por (rel, mtime, fsize) com teto em bytes (`OTC_DUCK_DAY_MEMO_MB`).
  O `_day_json` do daycache continua memoizando o payload PARSEADO por
  (mtime, tamanho); o `_day_prefetch` lê em lote (uma abertura por banco).
- **OCUPADO** (a instância vizinha com a trava exclusiva): UMA retentativa
  curta (`OTC_DUCK_READ_LOCK_SECONDS`, padrão 20 — é o share, não a dev), depois a **última cópia boa
  em memória**; sem cópia, `BancoOcupado` (um `IOError`, que os `except` dos
  leitores tratam como arquivo ilegível). A disputa perdida marca o banco por
  `OTC_DUCK_BUSY_SKIP_SECONDS` (60): as leituras seguintes nem tentam.
  **Não há mais JSON para cair.** E OCUPADO nunca é "não existe":
  `isfile`/`exists`/`stat` respondem pela última cópia boa em memória (a
  chave do memo é o carimbo) e, sem ela, também levantam `BancoOcupado` quando
  o banco está preso sem manifest conhecido — lido como "não existe", um
  read-modify-write (`if exists: ler; alterar; gravar`) gravaria só o
  registro novo por cima do dia inteiro. O que escapa do handler cai no
  tratador global (`_handle_database_busy`, `routes.py`): 503 JSON
  `error=database_busy` com `Retry-After`, nunca 500 HTML. O claim diário
  lê ocupado como "a outra instância cuida" (não envia). E `_cpd_load` (o
  Counterparty Details) NUNCA devolve `[]` por falha de leitura: quem grava
  faz ler → achar/criar o registro → `_cpd_save_list(data)`, e a lista vazia
  reescrevia o cadastro inteiro com um registro (§436). Ocupado sobe (503);
  outra falha sobe com o motivo no log; só caminho ausente é lista vazia.
- **O que se paga:** a gravação reconstrói a tabela DENTRO do request, sob a
  trava exclusiva — no share são os segundos que o espelho pagava em
  background — e o `_cache_lock` de quem faz read-modify-write fica preso
  durante ela. Uma gravação que falha levanta (a camada `database_access`
  retenta a abertura por disputa).
- **Script que mexe em dado grava pelo `data_store.write`** e resolve o
  caminho pelo `data_paths` (`import_cgd_auxiliar`, `update_b3_ids`,
  `update_base_from_xlsx`, os editores do CounterpartyDetails,
  `dev_seed_positions`): um JSON escrito em disco dentro do `DATA_DIR` é
  invisível para o app até alguém rodar a importação — e ela sobrescreveria
  o que a tela gravou depois.
- **Rollback**: `scripts/export_duckdb_to_json.py` reconstrói do banco os
  JSONs que têm diferença com o disco (ausentes ou mais velhos que o carimbo
  do banco); `--dry-run`, `--force`, `--only <subárvore>`. Reverter o commit
  e rodá-lo é o caminho de volta.
- **Ler em LOTE continua valendo** (§428): quem vai ler a árvore inteira
  chama `_day_prefetch(dias)` antes do laço; `data_store.prefetch` agrupa por
  banco e lê o manifest e as tabelas numa abertura. `check_daycache.py` §8
  MEDE.
- **Portão em memória** (`db_gate`) dá PREFERÊNCIA ao escritor dentro do
  processo, e a ORDEM é a mesma nos dois lados: portão, depois trava de
  arquivo. O `duckdb_write` DECLARA a escrita antes de pedir a trava
  exclusiva (leitor novo do armazém espera, os em voo terminam) e drena de
  novo depois dela (o poll sem trava do sino). Na ordem inversa o escritor
  segurava a trava esperando o portão e o leitor segurava o portão esperando
  a trava: 12 s por gravação com leitores ativos, e o banco marcado OCUPADO
  por 60 s. `check_duck_gate.py` prende os dois sentidos e §6 MEDE a
  gravação sob oito leitores em laço. ENTRE instâncias o portão não alcança:
  o escritor deixa uma INTENÇÃO (`<db>.lock.w`) enquanto pede a trava, e o
  leitor com trava recua até 1 s se ela é recente (um `stat` por abertura;
  órfã de mais de 60 s é ignorada). Sem isso a gravação da instância vizinha
  esperava até 8 s por um instante sem leitor; com, 0,3 s (§7 prende). O motor `json_to_duckdb` não importa `apps` (o standalone copia
  o corpo); `check_duck_read.py` prende o armazém ponta a ponta.

### A camada `database_access`

Toda abertura de DuckDB passa por `duckdb_read`/`duckdb_write` (nunca
`duckdb.connect` cru): semáforo por banco (`DATABASE_READ_CONCURRENCY` = **8**
desde 09/09/2026; era 4 contra 16 threads), lock de arquivo `.lock` via
portalocker (compartilhado na leitura, exclusivo na escrita), retry REAL da
abertura em escrita por disputa (`DATABASE_LOCK_RETRY_LIMIT`), e o farol de
eventos (`local_permit_*`, `file_lock_*`, `connection_opened/closed`) que o
painel lê. Custo medido: 12,67 ms por abertura pela camada contra 12,82 crua —
a abertura domina. `DATABASE_ACCESS_PATHS` é só a conferência de gravabilidade
da subida e NÃO liga o farol; os caminhos do espelho são dinâmicos.

### Os dois bancos de plataforma

- **`Users_OTCTracker.db`** (`users`, `verification_codes`) — conexão
  singleton atrás de `_duckdb_conn_lock`; `get_db_connection()` devolve um
  handle que **segura o lock até o `close()`**: todo chamador é
  `conn = get_db_connection()` + `try … finally: conn.close()`. Sem o
  `finally` o app inteiro trava para todo mundo. **Quem só faz SELECT abre com
  `readonly=True`** (lock compartilhado + semáforo); o caminho de escrita é fila
  de UM.
- **`Notifications_OTCTracker.db`** (`notifications`, `push_subscriptions`) —
  separado porque cada gravação de notificação segurava o banco de usuários em
  exclusivo. `get_notif_connection()`, mesmo contrato. A separação acontece
  sozinha na subida (`_ensure_notif_db`, no `record_once`; idempotente, não
  apaga o antigo; schema numa transação SEPARADA da cópia; `seq_notif_id`
  nasce depois do maior id; NULL vira `''` em `NOT NULL`). **O ensure roda na
  subida e nunca no poll**: uma sonda de leitura (`_notif_schema_pronto`) com
  TRÊS respostas — `True`, `False` (falta tabela) e `None` (não deu para olhar:
  arquivo em uso, classificado por mensagem) — evita a abertura read-write; o
  ensure que falha espera 5 min. `check_notif_db_boot.py`.
- **Leitura SEM lock (`unlocked=True`) é do poll do sino, e só dele** (melhor
  esforço: falha devolve sino vazio). Em autorização, dado parcial vira acesso
  errado — `check_unlocked_reads.py` barra por nome. O `_UnlockedReadGate`
  coordena o poll `read_only` com o `duckdb_write` do `_create_notification`
  (mesmo arquivo, configurações diferentes → "different configuration"); no
  teto degrada, nunca enfileira. Poll que ainda esbarra serve `_notif_last_good`
  (por SID × papel, teto 10 min — preserva o alarme de conexão vazada).
- **Assinaturas de "arquivo em uso" moram no `database_access`**
  (`FILE_IN_USE_SIGNATURES`/`is_file_in_use`, `True` também para
  `DatabaseLockTimeout`); `_notif_arquivo_em_uso` é alias. Aviso
  `file_lock_skipped` sai uma vez por banco.
- **A tabela do sino é expurgada** (`_notif_purge_old`, thread `notif-purge` 3
  min após a subida e diária; `OTC_NOTIF_RETENTION_DAYS` = 90, `0` desliga).
  O poll filtra `created_at >= CURRENT_DATE` (sem `DATE()` na coluna).
- **Todo request tem um RASTRO de banco** (`database_access.DbTrace`, aberto
  no `before_request`): cada operação da camada entra com o NOME do banco,
  modo, segundos e categoria, e o `duck_read` anota queda para o JSON e cura.
  A linha `[slow-request]` termina com o resumo, e o laço `slow-request-watch`
  loga a cada 30 s o request em voo há mais de 30 s **com a PILHA da thread**
  (`trace_stack`) — é o que separa "lento no banco" de "preso num lock em
  memória" ou "lendo JSON no share", e vale para o request sem operação
  nenhuma. O resumo diz também a operação EM CURSO (banco, modo, fase
  `permit`/`trava`/`abrindo`/`aberta`, há quantos segundos): é o que separa
  "esperando a trava do vizinho" de "preso dentro do `duckdb.connect`"
  (§436). Todo evento do farol leva `thread=`. Thread de fundo que quer o
  mesmo usa `trace_begin`/`trace_end` à mão (o `summary-warm` e a
  `store-import` fazem).
  `check_db_trace.py`.
- **Lock de arquivo com `timeout` leva `NON_BLOCKING`** (portalocker): sem o
  flag o timeout é ignorado com um aviso na subida e a espera não tem teto.
  Foi o claim diário (`_claim_daily_slot`).

### Regras de concorrência (a parte que quebra para todos)

- **Allowlist do `Page_Access` cacheada por SID** (TTL 30 s + invalidação na
  escrita: uma cobre este processo, a outra a instância vizinha) e a renovação
  é **SINGLE-FLIGHT** (`_page_access_inflight`): uma página dispara dezenas de
  `/static/*` ao mesmo tempo. `refresh_session_role` pula `/static*`.
  `check_db_read_path.py` §2b.
- **`ensure_db` roda UMA vez por processo e por arquivo** (`manual_conf`,
  `cgd_docs`): a conferência de schema abre em ESCRITA (trava exclusiva entre
  instâncias), e ficava em toda LEITURA. O que segue conferido é se o ARQUIVO
  existe; a marca só é posta quando dá certo.
- **Nunca trabalho lento segurando lock** (rede, SMTP, varredura, template).
  `_push_notify` é o modelo: lê inscritos, fecha, dispara.
- **Caches JSON são read-modify-write sob `with _cache_lock:` no ciclo
  INTEIRO** (ler → alterar → `_atomic_write_json`). `_cache_lock` não é
  reentrante: nunca chame helper que trava de dentro do bloco.
- **Conexões dos bancos por produto fecham no `finally`**; vazada, segura o lock
  de escrita pela vida do processo.
- **Um `stat` por LINHA é invisível na dev e custa minutos no share.** O cache
  por mtime evita reler o arquivo, não o `getmtime` que decide. Remédio:
  `once_per_request` (`request_cache.py`) — memoiza só dentro de UM request,
  sem TTL (edição na tela vale no request seguinte), e **fora de request não
  memoiza nada** (a rotina agendada tem de ver o arquivo mudar).
  `check_stat_por_linha.py` MEDE. Já protegidos: `_refdata_by_taxid`,
  `manual_conf.sla_days`, `_pc_metrics_history`, `_anbima_stamp`, os quatro
  finders do New Deals (`_nd_file_list`, do mais novo ao mais antigo, leitura
  pelo `_day_json`) e a listagem do Electronic Inventory (`_ei_walk` por
  `scandir`, sem `stat` por arquivo).
- **O calendário ANBIMA em memória acompanha o mtime do `anbima.json`**
  (`_anbima_stamp`): feriado cadastrado vale no request seguinte. Calendário
  FIXADO à mão (teste com mtime `None`) nunca é recarregado.
- **SQLite** (`apps/db.sqlite3`) não é usado pela lógica; `create_all()` roda
  uma vez na subida.

> DuckDB recusando abrir depois de rodar sob outra versão (`replaying WAL`):
> renomeie o `.wal` para o lado — o `.db` está íntegro.

---

## 5. Autenticação e autorização

**Login por SID** (1 letra + 6 dígitos), sem senha: `awmpy.get_phonebook_data`
traz nome/e-mail/cargo; SID no banco **e** IP igual ao gravado → sessão
direta; senão código de 6 dígitos por SMTP (`verification_codes`, 10 min) e
`/verify-2fa`. Sessão: `authenticated`, `user_sid`, `user_name`, `user_email`,
`user_role`.

- **Papéis** (`Role` no banco): `ADMIN`, `BO`, `MO`, `FO`, `INSTITUTIONAL`,
  `HUB`. **Master** é por SID (`_MASTER_SIDS = {'E930179'}` em
  `platform/authz.py`), não concedível; `_session_is_admin()` = ADMIN ou
  master. Só o master altera acesso de admin/master e escapa de toda restrição.
- **Por página**: `users.Page_Access` é array JSON de URLs. Vazio = não
  configurado = acesso total (admins incluídos). `enforce_page_access`
  bloqueia quem tem allowlist e redireciona para `_safe_landing(allowed)` — o
  dashboard é concedível, não sempre permitido. `_ALWAYS_ALLOWED_PATHS` =
  `{'/users-profile', '/page-access'}`. `/api/*` e `/static*` nunca são
  bloqueados aqui.
- **Por card (Control Panel)**: tokens `/control-panel#<id>`
  (`_CONTROL_PANEL_CARDS`, na ordem da tela — monta a checklist do
  `/page-access`); `enforce_control_panel_cards` bloqueia o endpoint da rotina
  sem o card (`_CP_ENDPOINT_CARD`). **O `id` é o token gravado**: renomear
  revoga em silêncio. A seção do card é o DOM (`data-cp-hdr` + `.row.cp-cards`),
  nunca um mapa no JS. Seis seções: Intraday, Settlement Reporting, Pending
  Confirmation, Economic Affirmation, Reference Data, Application (o card *New
  Version Released* lê a versão do `link.txt` ao lado do
  `start-otc-tracker.bat`; sem versão o envio é recusado; destinatário é quem
  está `Active`).
- **`refresh_session_role`** (`before_request` próprio): o papel do cadastro
  alcança quem já está logado em até 30 s, pela mesma leitura da allowlist.
  `None` não mexe (banco mudo não rebaixa a mesa); `''` mexe (é revogação);
  master não é tocado; só grava quando muda. `check_session_role.py`.
- **Support Center: a unidade de visibilidade é a MESA** (`requester_role`
  gravado no ticket; ticket antigo resolve pelo cadastro em lote,
  `_tk_roles_by_sid`); ver não é poder (editar/comentar/apagar é do requester e
  do master); papel vazio não casa com nada.

---

## 6. Mappings (os de-para que se editam na tela)

Entrada em `_MAPPING_DEFS` (`key → {label, columns, seed[, file, upgrade]}`) +
item no `TYPES` de `mapping.html`. Arquivo em `static/data/mappings/<key>.json`
(versionado; `BaseMoeda.json` também está lá). `_mapping_rows(key)` semeia na
primeira leitura e cacheia por mtime — **edição vale no request seguinte, sem
restart**. API `/api/mappings/<key>` GET/POST; o POST substitui o arquivo
inteiro; valores **não são trimados** (`'C '` é código B3). O front mantém os
literais antigos como fallback. `upgrade` converte formato antigo na leitura;
**seed só roda quando o arquivo não existe** — correção de seed não alcança
quem já tem o cadastro, e por isso precisa de `upgrade`. `autofill` preenche
outra coluna; tipo **`refdata`** liga nome/SPN/Tax ID ao Reference Data (um
escolhido, os outros dois se preenchem). **`file`** aponta para um JSON já
existente (o `swap-index` edita o mesmo `SwapIndex.json` do Index Results —
declare as colunas extras, senão o POST as derruba).

São **45**: `currency-base`, `interbook-ndf`, `commodities-b3`,
`publisher-ndf`, `le-accronym`, `le-spn`, `bank-name`, `fxo-conv-rate`,
`ndf-pdf-cpty`, `swap-curves`, `cetip-files`, `api-links`,
`manual-conf-validation`, `manual-conf-sla`, `fxo-internal-cpty`,
`fxo-book-disregard`, `opb3-events`, `swap-ir-client`, `swap-ir-term`,
`bankers-email`, `swap-index`, `ndfc-ir-exempt`, `b3-accounts`,
`ndfc-advice-split`, `tools-swap-index`, `opb3-msg-asset`,
`swap-funcionalidade`, `swap-amortizacao`, `swap-code-labels`,
`quotes-equity`, `quotes-commodity`, `mt300`, `settlement-exception`,
`gdt-codes`, os sete `dce-*` e os quatro `cgd-*`.

### Regras fáceis de quebrar pela tela

- **`opb3-events`** — regra Tipo Título × Tipo Operação × Status B3, campo em
  branco = coringa, `USE` Consider/Disregard. Disregard vence; Tipo Título com
  um Consider próprio vira lista branca; sem Consider não é filtrado. A MESMA
  resposta para NDF Summary, Other Products, avisos e mensageria (§213).
- **`publisher-ndf`** — linha sem Match Tokens casa só com o texto completo;
  `NOTES = BACEN` é o que roteia para Vanilla (§166).
- **`commodities-b3`/`cetip-files`** — padrão, não literal: `"MY"` = letra do
  mês + ano, `_` = espaço, `YYMMDD` = Reference Date. `TRADE TYPE`
  (VANILLA/ASIAN/BOTH) por linha (BRT_IPE e WTI têm duas); `QUOTE TYPE
  NDF/OPT` e `INFO SOURCE` guardam o código do layout Conecta, default
  `A`/`5`/`358` (`_b3_quote_cfg`); cópia no navegador em
  `b3-quote-config.js`, `check_quote_type.py` prova a paridade.
- **`api-links`** — uma linha por uso × produto (`New Deals` × NDF/FXO/
  Commodities/Swaps, `Unwinds` vazio de propósito, `Recon FXO`, `Intrag DCE`,
  `Daily Settlement` × NDF = `getTradesBySettle`); `SOURCE` API × Bob Report;
  `YYYYMMDD` é a data; produto é o parâmetro da API, não a página. O
  `settlement` da API é LISTA e o valor é o primeiro item numérico de `Rolled
  Positions` (§425).
- **`fxo-internal-cpty`** — `INVERT DIRECTION = Yes` é a perna espelhada e só
  entra com Ctpty e Dir os dois NOK; `USE = Disregard` corta ANTES do merge, por
  `_nome_cru`, nas DUAS colunas de contraparte, avisando no painel. O `upgrade`
  mora no `recon_fxo`. CNPJ sai do Reference Data (`lookup_cnpj`).
- **`fxo-book-disregard`** — conjunção de até três `coluna = valor` com a
  coluna ESCOLHIDA do cabeçalho real (`_ATHENA_FXO_COLUMNS`); par pela metade
  não conta; linha sem critério é ignorada; coluna inexistente PULA a regra com
  aviso. O `/reconciliation-fxo/run` toca os dois cadastros para semear.
- **`manual-conf-validation`** — Produto × LOB → OTC/MO/FO `REQUESTED`/
  `EXEMPT`; LOB em branco = coringa; MO e FO em paralelo; produto sem linha cai
  em OTC + MO com aviso. PRODUCT é `select` sobre
  `manual_conf.CONFIRMATION_TYPES` — **doze tipos em MAIÚSCULO SEM ACENTO**
  (`upper_norm` compara em NFKD; `TERMO DE RESILIÇÃO` com cedilha nunca casaria
  consigo mesmo). **A pasta É o código** (`TYPE_FOLDER`); `TYPE_FOLDER_LEGACY`
  é só leitura (`confirmation_folders()` = escrita + antigas). Tipo novo mexe
  em `CONFIRMATION_TYPES`, `TYPE_FOLDER_LEGACY` (tupla vazia se nunca existiu)
  e `VALIDATION_SEED`. O `upgrade` traduz nomes antigos E completa os tipos sem
  linha (por produto). `OPTION EDG` vira `FXO` × LOB `EDG`.
- **`b3-accounts`** — responde três perguntas: só `CLIENT 1/2` são omnibus
  (cliente por CNPJ, só dígitos; conta própria não procura cliente — quem
  decide é o TIPO, cego a caixa/acento); Participante do header TER
  (`_ter_file_header`, LE sem Nome Simplificado levanta erro); `MESSAGING`
  Consider/Disregard (intragrupo chega pelos dois arquivos; conta fora do
  cadastro GERA). Estar no cadastro é ser conta INTERNA.
- **`tools-swap-index`** — curva da posição → indexador do Swap Calculator;
  `Exact` vence `Contains`, token mais longo vence; VCP resolve pelo `Nome
  Tipo/Classe`, que é a SEGUNDA pergunta em toda curva; sem linha o índice fica
  em branco e a nota DIZ o que a posição trazia; `INDEX` tem de ser do motor
  (`liquidacao.INDEXADORES`). O `Código Identificador` da posição NÃO é chave
  (guarda a LOB); quem casa o DFLUXO é o `Código do contrato` (§427). O período
  de cada fluxo é do servidor (`p_inicio`/`p_fim`), candidato não anterior ao
  fim é descartado.
- **`quotes-*`** — código → símbolo Yahoo; opções da tela = `Subjacente.json`
  ativo ∪ linhas literais do cadastro; sem símbolo é 404 pedindo cadastro; em
  commodities as DUAS colunas aceitam `"MY"` (`quotes.symbol_lookup`, ano de 1
  ou 2 dígitos, sufixo de bolsa depois do vencimento, prefixo mais longo vence,
  literal vence padrão). Registro em `DE_PARA_TICKERS_COTACOES.md`.
- **`ndfc-ir-exempt`** (uma lista para Advice e Trade Level),
  **`ndfc-advice-split`** (um aviso por mercadoria, depois do split por net),
  **`bankers-email`** (Cc da coleta de assinatura; vazio avisa no log),
  **`opb3-msg-asset`** (token do Type → rótulo no assunto; contém, mais longo
  vence, sem linha não põe rótulo), **`fxo-conv-rate`** (moeda não cadastrada
  avisa em vez de imprimir em branco), **`swap-index`** (C00 → VCP; Termo e
  Opção não têm de-para), **`cgd-*`** (colunas na ordem das abas do
  `Auxiliar.xlsx`; `import_cgd_auxiliar.py` carrega).

---

## 7. O padrão de tela

### Tabela (referência: `new_deals-ndf-vanilla.html`)

- SweetAlert2 e jQuery **LOCAIS** (`plugins/sweetalert2/`, `plugins/jquery/`
  ANTES do DataTables): a instância roda sem internet e o `vendors.min.js` não
  expõe o jQuery — sem isso a página abre sem tabela, erro só no console.
- `dom: "rt<'d-md-flex justify-content-between align-items-center mt-2'ip>"`.
- **Centralizada**: `th` `.7rem` centro/middle (quebra permitida), `td` `.8rem`
  centro/middle `nowrap`. Não existe regra global; com `scrollX` os clones
  `.dt-scroll-headInner`/`.dataTables_scrollHeadInner thead th` levam as mesmas
  regras **com `!important`** (o DataTables remove o id da tabela clonada e a
  regra da página perde para `table.dataTable thead th`). `table-centered` não
  existe em CSS nenhum. `check_table_center.py`.
- **Linha de filtro por coluna** como 2ª linha do `<thead>`, montada ANTES do
  `.DataTable()` com `orderCellsTop: true` (no `initComplete` ela fica no
  `<thead>` escondido do corpo rolável). Centralização dos inputs vem do
  `visual-refresh.css`. `blank` sozinho no campo casa célula vazia.
- **Botões de ação: squircle 32×32** travado nos DOIS eixos, `padding:0`,
  `border-radius:10px !important`, ícone Tabler `1rem` (nunca `.fs-13`),
  tooltip colorido delegado no primeiro hover (os `<td>` são reescritos a cada
  redraw). Regra GLOBAL no `visual-refresh.css`; ordem Confirm `ti-check` →
  Edit `ti-edit` → Delete `ti-trash` → Send `ti-brand-telegram`; edição Save
  `ti-device-floppy` + Cancel `ti-x`. `check_row_action_buttons.py`.
- **Toolbar** `mb-3` (o DataTables come a margem do irmão), `.btn-toolbar-all`;
  cores por função: Columns soft-primary, Add Row primary, Export info
  (**Copy · CSV · Excel · Print · PDF**, DataTables Buttons; CSV `;` + BOM;
  Excel exige o registro síncrono do JSZip), Import teal `#4a849b`,
  Mapping/refresh success, Clear Filters outline-secondary. Export termina no
  **Advanced Export** (`otcExportAdvanced('#t', { daily: '<endpoint que a
  própria página consulta>' })`, `exact=1` + confere `source_date`, dia sem
  arquivo é pulado, teto 60 s/dia — §304).
- **Alinhamento com `scrollX` são TRÊS coisas**: `columns.adjust()` depois de
  todo draw (+ passe atrasado 150 ms + `resize`); `autoWidth: true`; regras de
  `th` repetidas nos clones com `white-space: normal`.
- **Seleção de célula em TODA tabela**: extensão `select` (New Deals, Intrag)
  ou `table-std.js` + `otcCellCopy('#id', { skip: [...] })` DEPOIS do
  `.DataTable()` (por tabela quando há uma por card).
- **Números** `#,##0.00` com `tabular-nums`; taxa NÃO é valor (Strike fica com
  as casas que tem); formatação só no `display`, sort pelo cru. **Status** é
  badge pill `bg-gradient`.
- **Autocomplete nunca é `<datalist>`**: dropdown próprio abaixo do campo, mesma
  largura, `max-height` ~220px, item por `mousedown` (antes do `blur`),
  reemitindo `input`/`change` (`mapAttachDrop`, `.ar-ac-drop`).
- **Data é SEMPRE `dd/mm/aaaa` e `<input type="date">` visível é proibido** (o
  nativo desenha no locale do sistema — `mm/dd` no Windows do JP). flatpickr
  com `altInput` (`otcDateField`/`otcDateSync` do `export-advanced.js`; quem
  escreve por código chama `el._flatpickr.setDate`; largura em CLASSE porque o
  `style=` fica no campo escondido; ícone como background SVG embutido) ou
  daterangepicker `singlePicker` `DD/MM/YYYY`. `type="date"` só invisível atrás
  de texto readonly (`.date-wrap` das recons).

### Layout e vidro

- **Não use `.card` para widget seu** — o `extra_css` da página carrega ANTES
  do tema e perde. Padrão: `<div>` com classe própria (`.ndm-card`,
  `.fxo-widget`) com `--vr-card-*`/`--vr-grad`. Pela mesma ordem, classe
  Bootstrap de mesma especificidade vence a da página mesmo com `!important`,
  e o `background: … !important` do `.card` apaga `background-image` (cartão
  com gradiente vai no `streamflow.css`).
- **`backdrop-filter` cria contexto de empilhamento**: `z-index` vai no
  WRAPPER, nunca no menu; o `.wrapper` fica sem `z-index`.
- **Dentro de uma raiz de backdrop o desfoque do filho não amostra nada**:
  dropdown dentro de card tem fundo SÓLIDO; modal/offcanvas/toast/Swal pendem do
  `<body>`.
- **Regra de brilho alcança as DUAS famílias de seletor** (estrutural
  `[class*="-widget"]` e as quinze classes próprias), calibrada por tipo de
  superfície.
- **`.modal-content.liquid-glass` é exceção da regra genérica das
  sobreposições** (`--sf-overlay-bg` a 82% matava o vidro dos modais, §387).
- **Modo de efeitos reduzidos** (`sf-reduced` no `<html>`, decidido pela IIFE
  do `streamflow.js`: WebGL por software ou Firefox no Windows;
  `localStorage.__OTC_TRACKER_FX__` vence): sem blur, alfa não é material —
  superfícies viram cor SÓLIDA (seção 16 do CSS). Token do modo vai como
  `html.sf-reduced:not([data-bs-theme=dark])`. Valide forçando `'reduced'`.
- Cor só de tema claro precisa do par `[data-bs-theme=dark]`.

---

## 8. Armadilhas por domínio (não dão erro nenhum)

### New Deals

- **Contraparte vem do accronym do End Counterparty, nunca do Settlement
  Location** (que é a NOSSA perna). Ordem em `_ndf_ref_by_accronym`: accronym
  exato → sem sufixo → se perna interna, identidade da entidade
  (`_ndf_le_refdata`) → senão o SPN da API → nada (badge *Missing
  Counterparty*, que é a falha desejada). Amend recheca; linha achada por
  `(Deal, Client)`, e só pelo Deal se ele for único no arquivo-dia.
- **`table.rows({search:'none'})` NÃO é "tudo do dia"** — é a última busca. O
  servidor monta a lista pela Reference Date (`_generic_nd_mapping_candidates`).
- **Coluna nova nas páginas de NDF mexe em 14 lugares** (`COL_TO_JSON_FIELD`,
  `AMEND_FIELD_COLS`, `dealJsonToRow`, `ND_COL_KEYS`, `columnDefs`,
  `columnLabels`, edição em massa, `SF_COLS`, `SF_LABEL_TO_FIELD`,
  `extractRowDeal`, `rowDataToNdfDeal`, `rowMaker`…); `MAKER_COL_INDEX`.
- **`Sent` e `Success` só voltam para Amend por dado ECONÔMICO**
  (`_ND_AMEND_KEEP_STATUS`); o Strike do FWD Start é cosmético
  (`_ND_AMEND_COSMETIC_BY_PRODUCT`, por produto — produto vazio = econômico).
  A varredura do box não tem a proteção de propósito (paridade com
  `otc-fileupload.js`).
- **Só `isCancelled` é cancelado** na Athena; `isDead` importa normalmente.
- **A inversão da moeda fraca é do PAR** (`_ndf_weak_leg`), uma vez na
  importação; o TER só arredonda pelo `INV DECIMALS`.
- **A API nunca entrega a perna Lawton/MGT**: `_nd_lawton_mirror` e
  `_nd_mgt_mirror` sintetizam no envio, pareando por termos econômicos
  (`_nd_lawton_sig`), com `force_values` por linha para a conta do omnibus.
- **Os textos da Parte A do FWD Start vivem no `routes.py`** de propósito (a
  grafia é a do documento assinado) — LE ausente deixa em branco com aviso e o
  Save recusa (`400 missing_partea`).
- **Cache das três páginas genéricas: `NDF/Vanilla`, `NDF/FwdStart`,
  `NDF/OtherPublisher` SEM espaço** (`check_nd_cache_dirs.py`).
- `otc_boxparse.py` e `otc-fileupload.js` são duas cópias da mesma regra;
  `check_boxparse.py` prova (precisa do `jsc` do macOS).
- Só produtos de `_MC_CONFIRMATION_SOURCES` geram documento na esteira;
  `_mc_save_from_deal` é chamado de dentro de `_pc_save_from_deal` e não
  retroage (`backfill_manual_confirmations.py`). Mercadoria e FXO são sempre
  JPM (`_MC_JPM_SOURCES`); razão social do `le-spn`.

### Live Position (cinco telas, um JS)

- `live-position-swap-characteristics.js` serve cinco páginas por `data-api`;
  contrato: ids `swapchar-page`/`swapchar-table` — renomear deixa a página em
  branco. Acréscimos são aditivos/opt-in.
- **Andam até dez dias úteis para trás** quando falta arquivo
  (`_opt_dposicao_path`/`_swap_day_path`), sinalizando a data LIDA. O Edit
  manda `source_date` com `exact=True` e roda sob `_cache_lock`.
- **A coluna CPF/CNPJ mostra o NOME** (`_lp_cpty_by_taxid`, zero à esquerda
  normalizado dos dois lados; sem cadastro volta o número). `_lp_is_taxid`
  separa resolveu/não resolveu (ausência de LETRA). Swap Characteristics:
  erro de planilha vira vazio (`_swapchar_is_xl_error`) e linha sem documento
  resolve pela conta CETIP (`_lp_cpty_by_account`, recusa omnibus e ambígua).
- **Quatro células vazias juntas no VCP é o JOIN**, não cadastro:
  `_vcp_position_map` é fallback da DPOSICAO-SWAP pelo `Contrato` (§431).
- **O Latam é reemitido no dia**: `_latam_pick_source` = mtime mais recente;
  preteridos ficam em disco e voltam em `ignored`.

### Liquidação (Other Products, NDF Summary, Settlement Advice)

- **`_ops_trade_rows(settle_ref)` é o único lugar que sabe quais famílias
  existem** (SWAP + NDF Commodities); página, cards e e-mail de TED chamam
  ele. Status do aviso vive no overlay `other-products-summary_YYYYMMDD.json`
  por contraparte × LOB × produto. Linha que neta zero diz `0.00` no Receive.
  Trade Level ordena Product → LOB → Counterparty (`check_ops_trade_swap.py`).
- **Equity é SWAP na B3; o outro lado vem do elo** `_ops_equity_link`
  (Operations B3 → Latam → OTM), Type trocado pelo subjacente por cadeia; o
  mesmo elo é o plano B da opção de equity (`_optadv_collect`, chave Título
  MAIÚSCULO, resolvido uma vez por linha).
- **Perna interna não gera aviso** (`_ops_is_internal_cpty` pelo `le-spn` +
  `_pc_is_internal_counterparty`, nunca "começa com BANCO"): fica no Trade
  Level e no Summary, sai do Advice e do TED.
- **Nome da contraparte sai do SPN** (`_athena_settlements` → `_otm_cpty_name`;
  OTM pelo `Cpty SPN`, na leitura).
- **IR do termo de moeda é CALCULADO** (`_ndfsum_ir_apply`, §423): 0,005%,
  isento pelo `ndfc-ir-exempt`, piso de R$ 1,00 acumulado no mês no ledger
  `ndf-ir-ledger_AAAAMM.json`; o import do Cockpit reusa as mesmas funções
  (`_ndfc_apply_ir`), o calculado vence o `VL_TAX_INCOME`. **A cura do ledger é
  INCREMENTAL e roda FORA do `_cache_lock`** (§432 — era o Summary
  "infinito"): grava dia a dia, só o dia pedido fica de fora com `ir_partial`;
  laço `ndfsum-ir-warm` cura até a véspera; `/data` devolve `collect_failed`
  como JSON. Other Products segue o mesmo desenho.
- **A tabela do PDF do Advice tem largura MEDIDA** (`stringWidth`, escada de
  fonte, `Paragraph`), nunca `515/N`.

### Esteira de confirmação manual

- Ciclo: `(Pending Legal) → Pending OTC → Pending MO e/ou FO → Pending FepWeb
  → Ok`. Legal é hold manual; FepWeb é derivado; Ok exige `Enviado p/
  cliente`; `Pending OTC` digitado REABRE (limpa validações). Toda gravação
  espelha no Pending Confirmation (`_mc_pc_sync`).
- **SLA em dias ÚTEIS ANBIMA a partir do TRADE DATE**: OTC D+3, MO D+4, FO D+6
  em paralelo (`manual-conf-sla`, branco = histórico). `sla_state()`: ok/warn/
  late/**done**. Passado o prazo a validação exige justificativa (409
  `sla_comment_required`, coluna por mesa).
- **Cada etapa é assinada pela SUA mesa** (`_MC_STAGE_ROLE`: OTC → `BO`, MO →
  `MO`, FO → `FO`); `ADMIN` é lido como `BO` (`_MC_ROLE_ALIAS`, só o Pending
  OTC) nas DUAS perguntas — assinar e ser avisado
  (`_MC_STAGE_NOTIFY_ROLES`, derivado). Endpoint devolve 403
  `stage_forbidden`. MO e FO conferem só `CHECKLIST_ECONOMICO`.
- **Validar é abrir o documento** (`/manual-confirmation/validate`), nunca um
  clique no card; Validate e Reject vivem lá (Reject só das mesas seguintes).
  **Gerar também é só no Monitor** (Pending OTC oferece Generate/Validate;
  `/manual-confirmation/generate?keys=…` casa pelos Trade IDs; 404 explicado).
  Os `/validate` do New Deals só carimbam `_mc_stamp_generated`, não a etapa
  do OTC, e não avisam no sino.
- **Preencher a coluna de validação pela grade do Track é validar** (mesmas
  regras do `mark_validated`; a transição é vazio → data; lote tudo-ou-nada).
- **E-mail Subject se escreve sozinho** (`_mc_sync_email_subjects`): por Trade
  ID no nome do arquivo, ou recap ÚNICO na pasta; fora disso nada. Memo por
  (caminho, mtime, tamanho); grava só o que mudou, em lote.
- **Aviso do sino vai para a mesa em que a confirmação CAIU** (etapa do ESTADO
  depois do carimbo); `MASTER` em todas, `ADMIN` em nenhuma; `target_role`
  aceita vários papéis por vírgula. Destino do aviso é o Confirmations Monitor
  (`page = 'Confirmation'`).
- **Callback**: falta de `Data Callback` é badge só no card Pending FepWeb (como
  CONTAGEM) e TRAVA o Mark as sent (409 `callback_required`).
- Nomes de coluna são os da planilha legada (schema dos DuckDB); rótulos pelo
  `COLUMN_LABELS` completo. Coluna nova em `DB_COLUMNS` é só isso — `ensure_db`
  faz `ADD COLUMN IF NOT EXISTS`, sem script.
- **Cobrança** (`conf_escalation`, sete listas em `domain.REC_KEYS`; seg/qui
  rolando feriado, escalação em `left == 0`; grupo de FO casa por
  `confirmation_type`; Pending FO sem grupo vai para `unmatched`).
- **BACC EA Metrics** (16:00 BRT, `.xlsx`): sem Data Callback, Pending ≠ Ok,
  Aging decrescente numérico; tipo por coluna, máscara `#,##0.00` invariante;
  planilha vazia VAI; `Conterparty Name` é grafia de contrato.

### Pending Confirmation

- **Pending Status tem TRÊS donos**: NDF Vanilla/Other Publisher pela regra de
  prazo e assinatura (`_pc_signature_pending_status`: ≤ 60 dias → `Exception
  FepWeb`, senão pelo SIGNATURE TYPE); todo o resto pela ETAPA da esteira
  (`_PC_ESTEIRA_STATUSES`, FWD Start incluído mesmo com prazo curto); a regra
  do VENCIDO é universal (`_pc_apply_auto_rules`: Maturity ≤ hoje e não
  resolvido → `Exception FepWeb` + `Ok`).
- **A manutenção das 11:30 ABORTA quando uma leitura falha**
  (`_pc_load_rows(strict=True)`) — a leitura tolerante lê falha como banco
  vazio e o backlog não volta (§406). O chip `Status = Pending` esconde o
  backlog.
- **Planilha de data anterior sobrescreve o arquivo de sempre** (o time global
  lê um caminho só); snapshot não é refiltrado; ausente é 404; o `ref` do
  status diz que foto está no share.
- **`_pc_metrics_history` cresce um snapshot por dia**: enumeração pelo
  `_manifest`, `_day_prefetch`, `once_per_request` (§429).
- **Os dois Summaries são AQUECIDOS em background** (`summary-warm`, 4 min
  após a subida e a cada 30 min na janela 08–20 BRT; `OTC_SUMMARY_WARM_MINUTES`,
  `0` desliga): as MESMAS coletas do request para hoje, num
  `test_request_context`, enchendo o memo de processo do `day_payload`. No
  share cada abertura fria custa segundos e os dois abrem uma dúzia de bancos
  em série; o clique depois do aquecimento paga só o `stat`. Uma linha de
  WARNING por rodada com o rastro (§433). E `_latam_all_dates` é memoizada
  por processo (TTL 5 min, esquecida pelo `_latam_save`): era um `os.walk` da
  raiz inteira do OTM a cada chamada, no caminho do Other Products.

### Recons

- **FXO**: chave `DealID`, `MatchingDealID` só quando existe do lado da B3;
  join `outer` (o `Unmatched Athena` só existe por isso); `_veio_da_b3` antes
  do merge; `pd.notna(x) and bool(x)` (nunca `is True` — `numpy.bool_`);
  `_aplicar_perna_espelhada` só nas linhas com os dois lados. Justificativa é
  do TRADE (`recon-fxo-comments.json`, `aplicar_comentarios` na gravação e na
  leitura; `_status` cru fora de `COLUMNS`).
- **Pay/Rec**: `SPB - outros bancos` casa só com BANCO (`_match_allowed`, pelo
  `bank-name`, por PALAVRA nunca substring, `banco` é token significativo,
  direção entra pela mesma porta, vale nos três estágios; fora do cadastro
  responde NÃO). Só linha `Sucesso` entra (`check_spb_status.py`).
- **CGD**: lê o D-1 do arquivo que o Save CETIP Files GRAVA (`CETIP_DEST_ROOT`),
  a lista do FEP vem do ANEXO do e-mail mais recente do box
  (`baixar_fep_do_box`; `path` vence; sem Outlook cai para `CGD_INPUT_ROOT`
  avisando); contas nossas do `b3-accounts`; CNPJ por dígito; cache gravado
  com a data da POSIÇÃO.

### Onboarding (CGD)

- Lista do SharePoint (`import_cgd_sharepoint.py` → `cgd_sharepoint.db`).
  **`Aging` é refeito a cada leitura** em dias úteis até hoje ou o `Conclusion -
  Stamp`; sem `Data Solicitação` fica vazio, nunca zero.
- **Formulário no SERVIDOR** (`REQUEST_FORM` → modal e `REQUEST_FIELDS`); o
  Apêndice é ARQUIVO (EI da contraparte, `CGD TEMPLATE`), sem coluna, e o
  upload vem ANTES da gravação. `_domain_in_appendix` é pseudo-coluna.
- **Três mesas, Legal e OTC em PARALELO** (`pending_stages` é lista); Legal
  fecha com o Taxonomy, OTC com o modal (abonado + B3 ID por `b3_id_column`),
  CEM MO com Complete. Etapas do `cgd-stage` ou DERIVADAS dos carimbos.
  **Encerrado não é pendência** (`is_closed`: Active/Inactive/Cancelado;
  `is_active` compara EXATO — `INACTIVE` contém `ACTIVE`). `Signature Type` é
  domínio fechado (`SIGNATURE_TYPES`), valor gravado entra na lista. `_id` não
  é estável entre importações.

### Holidays e calendário

- Calendários saem do registro `holiday-calendars.json` (seed
  `_HOLIDAY_CAL_SEED`, gitignorado): pills, `<select>`, cores e CSS. Novo nasce
  de planilha (coluna A data, B descrição; cabeçalho descartado por não ser
  data); cor da paleta; slug `[a-z0-9_-]` (vira caminho e classe); CSS gerado
  no navegador. `HC_CAL_FALLBACK` = os onze; `check_holiday_calendars.py`.
- `_anbima_holidays` é horizontal (SLA, aging, schedulers, D-1) e mora na
  platform, não na vertical.

### File Interpreter

- Nome é `file-interpreter` em tudo; legado redireciona/alias/normaliza/migra.
- **Campo em branco se cadastra como `Fixed` VAZIO**, nunca Page com dropdown
  limpo (Source = Page é "o gerador manda").
- **Variantes por par de pernas** (`base_key` + `le_pair`, `_fi_variant_key`),
  regra do BUCKET nas quatro páginas geradoras e nos previews; `file_name`
  cadastrável; o modal achata o `source_by_page`. Intrag divide por PRODUTO via
  `variant_label` (só de tela, catálogo `status: library`).
- **Fórmulas** (`FIELD`, `DATE`, `BIZDIFF`, `ADDBIZ`, `LOOKUP`, `CASE`) em
  `_fi_calc_value` e espelho `FiTer.calc` (`check_fi_calc.py`); precedência
  `force_values` > Fixed > fórmula > gerador; spec relido a cada preview;
  Cotação para o Vencimento efetiva desloca as linhas tipo 2.

### Notificações, e-mail e schedulers

- **Notificação nova exige o rótulo `page` nos TRÊS mapas** (`_NOTIF_PAGE_URL`,
  `PAGE_URL` do `topbar.html` e do `sw-push.js`); sem ele o clique não vai a
  lugar nenhum. `check_notif_page_url.py` varre por AST.
- **Thread de scheduler não tem application context**: `with _app_context():`
  em volta da montagem INTEIRA do e-mail (o botão Run funciona e o automático
  morre em silêncio).
- **Jobs rodam no horário do Brasil** (`_br_now`), com catch-up na subida
  (`_ndm_pending_catch_up`, claim em disco). **Os três schedulers de
  importação só entre 08:00 e 20:00 BRT** (`IMPORT_POLL_WINDOW`; malformado =
  sempre aberta com aviso), `continue` antes do `try`.
- **Botão de e-mail precisa de endereço ABSOLUTO**: `_otc_app_url()` lê
  `OTC_TRACKER_URL` ou monta `http://<hostname>:APP_PORT` (`routes.APP_PORT`,
  `OTC_TRACKER_PORT`, padrão 8051 — UMA constante para os três lugares).
- `reportlab` é importado preguiçosamente (sem ele, e-mail sem anexo).
- Um Delete que só apaga da tela reaparece como bug do IMPORT (o upsert
  preserva status da linha que ainda está no arquivo): a tela remove DEPOIS do
  sucesso do servidor (§430).
- `Docs/` e `docs/` coexistem; capturas em `docs/sop-screenshots/` com
  `git -c core.ignorecase=false add`. SOP e Guia são gerados do `.md` por
  `build_sop_docx.py`.
- `confirmation_pdfs.py`: documento novo nasce do HTML renderizado
  (`word_html_pdf`, `_CONF_OPT_PDF_FROM_HTML`), não de réplica em reportlab.

---

## 9. Ambiente local e instância do time

- **`awmpy` é interna do JPM** (não está no PyPI): fora da rede, stub mínimo
  no venv + `/dev-login` do DEV BYPASS.
- **macOS: porta 5005.** `duckdb` e `flask-minify` obrigatórios.
- **`OTC_SHARED_DRIVE_ROOT` obrigatória fora do Windows** (o app recusa valor
  relativo; `I:\` é relativo em qualquer sistema que não seja Windows — as
  pastas `I:\Confirmation\...` na raiz do repo vieram daí).
- **SMTP** `mailhost.jpmchase.net:25` sem auth; fora da rede falha em silêncio.
- **Athena**: `build_session()` com `trust_env=False` (o proxy corporativo
  causava `WinError 10061`); no Windows exige `requests-negotiate-sspi`
  (declarado com marcador de plataforma; sem ele `401` no
  `/adfs/oauth2/authorize/wia`, e o `build_session` LEVANTA nomeando o
  pacote). Três timeouts: `REQUEST_TIMEOUT` 30 s (um produto/dia),
  `REPORT_TIMEOUT` 180 s (EOD da Recon FXO, Intrag DCE, `getTradesBySettle`),
  `CONNECT_TIMEOUT` 10 s; cadastráveis, malformado cai no padrão com aviso.
  `check_athena_sso.py`.
- **BCB/Yahoo (Quotes)**: mesma sessão, proxy volta como FILA (`QUOTES_PROXY`
  → proxy do sistema COPIADO → `10443` → direto), primeira que responde fica.
- **A instância roda sem reloader**: pull que tocou `.py` ou template exige
  restart. Mapping pela tela é a exceção.
- **`PYTHONPYCACHEPREFIX` no `.bat`** apontando para `%LOCALAPPDATA%` (nunca
  `%TEMP%`, nunca `PYTHONDONTWRITEBYTECODE`): sem isso a subida fica minutos
  gravando `__pycache__` no share sem imprimir nada. O `start-otc-tracker.bat`
  mora no share, fora do repo (§322).
- **Parêntese dentro de bloco `( … )` do `.bat` vai escapado** (`^(`/`^)`) —
  erro de PARSE. `check_bat_blocks.py`.
- **`SECRET_KEY` é estado da máquina**: sem variável, o app mantém
  `%LOCALAPPDATA%\OTC-Tracker\secret_key.txt` (0600, `OTC_SECRET_KEY_FILE`);
  variável vence e é relida no `create_app`. Caminho ingravável recusa a
  subida.
- **O `config.py` é o arquivo que fica para trás** (é editado à mão na
  instância; `git pull` não sobrescreve modificado): `_REQUIRED_CONFIG_NAMES`
  recusa subir dizendo o nome e o comando. Chave nova lida do `Config` por
  outro módulo entra na lista.
- Cada pessoa roda a própria instância sobre o MESMO `db/` do share — é por
  isso que toda disputa de arquivo entre "instâncias vizinhas" existe.
- `flask_login`, `flask_wtf`, `flask_migrate` estão no requirements e não são
  usados.

---

## 10. Scripts e testes

### `scripts/` (rodam uma vez na instância depois do pull; idempotentes)

| Script | Para quê |
|---|---|
| `update_pending_confirmation_dbs.py` · `..._bankers.py` | migrações de schema do Pending Confirmation |
| `import_manual_confirmations.py` | cria os dois DuckDB da esteira e semeia do `MANUAIS.xlsx` |
| `backfill_manual_confirmations.py` | traz para a esteira o que foi mapeado antes dela (FWD Start pelo B3 ID; `--dry-run` lembra as chaves da passada) |
| `import_cgd_sharepoint.py` · `import_cgd_auxiliar.py` | lista de CGDs e as três abas do `Auxiliar.xlsx` |
| `split_notifications_db.py --dry-run` | mostra o que a separação do sino vai copiar |
| `dev_seed_positions.py` | só na DEV: reemite a última posição B3 numa data recente (`--from … --force`) |
| `convert_json_to_duckdb.py` + `scripts/convert/` (40 fatias) | a IMPORTAÇÃO JSON → DuckDB (o cutover do §434 e o legado fora da janela), incremental por `_manifest`, `--meses` 12 por padrão (`0` = tudo), `--only/--force/--dry-run/--bloco`; reconverte sozinho o payload-objeto sem `__raw` |
| `slim_duckdb.py [--db-dir] [--only cache] [--dry-run]` | emagrece os bancos de arquivo-dia JÁ existentes para a forma do §437 (lista só `_seq`/`_raw`, objeto só `__raw`), copiando do PRÓPRIO banco e trocando o arquivo; com o app PARADO; idempotente |
| `export_duckdb_to_json.py` | o ROLLBACK: reconstrói do banco os JSONs com diferença (`--dry-run`, `--force`, `--only`); `check_export_rollback.py` prova que cada forma volta exata |
| `scripts/standalone/` (40, GERADOS por `build_duckdb_standalone.py`) | os mesmos conversores para máquina sem o código (`pip install duckdb` só) — nunca editar à mão |
| `build_sop_docx.py` | SOP e Guia em Word a partir do `.md` |
| `diag_ndfsum_account.py [AAAA-MM-DD]` | DIAGNÓSTICO da coluna Account do Settlement Summary: nome da linha → SPN no Reference Data → registro do Counterparty Details → defaults → conta, dizendo onde a cadeia quebra (§436) |

`apps/static/data/db/` é gitignorado: bancos não vêm no pull. Telas vazias
depois de um pull são migração não rodada, não bug.

### `scripts/tests/` (120 scripts)

Autocontidos, sem framework, `ok`/`FAIL` por asserção, saída 0/1, sem tocar
dado real (tmp, stubs de Outlook/SMTP). O
[`README.md`](scripts/tests/README.md) mapeia script → módulo — **rode o
correspondente depois de mexer no módulo**, com
`OTC_SHARED_DRIVE_ROOT=/tmp/otc-share`. Vários sobem o app e trocam atributos
no `routes` (por isso a regra de import atrasado do §3). Os que MEDEM em vez
de conferir texto: `check_stat_por_linha`, `check_duck_gate`,
`check_daycache` §8, `check_db_read_path`. `check_boxparse` precisa do `jsc`.

---

## 11. Como trabalhar aqui

- **Rede antes, rede depois.** Mudança em módulo com teste: rode o teste antes
  (para saber o que já falha — `check_about_page`, `check_holiday_calendars`,
  `check_modal_standard` e `check_req_cache` têm falhas pré-existentes
  conhecidas em 09/09/2026) e depois. Feature sem teste
  de caracterização: escreva o teste primeiro.
- **Guardas na mesma mudança.** Mover função = atualizar o guarda que a cita;
  tipo novo = três listas; notificação nova = três mapas; mapping novo =
  `_MAPPING_DEFS` + `TYPES`; motor de conversão = regerar os splits.
- **A causa-raiz vai no commit e no HANDOFF**, não a lista de arquivos. O
  padrão do repositório é `tipo(escopo): o que estava errado e por quê`.
- **Não versione**: `apps/static/data/control-panel/`, `*.bak`,
  `apps/pages/routes 2.py`, `apps/pages/cotaçoes.py`, as pastas `I:\...` da
  raiz, `.claude/skills/`, capturas `.png`, caches de runtime. Nunca `git add
  -A`/`.`/`-u`.
- **Na dúvida sobre a instância** (§9): pull feito? restart feito? aba
  recarregada? log de módulo só sai em WARNING. Share frio e pastas gêmeas
  (`B3 Files` × `b3 files`) explicam a maioria dos "não funciona".
- **macOS**: não há `timeout`; no zsh, `--include='*.py'` vai entre aspas.
