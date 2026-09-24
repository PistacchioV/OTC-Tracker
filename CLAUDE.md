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
  `json.load` num caminho do `DATA_DIR`. **O guarda varre os DOIS sentidos**
  desde 21/09/2026 (§523, um percorredor só): a leitura crua é a mais
  traiçoeira, porque `json.load(data_path('X.json'))` devolve a SEED DO
  REPOSITÓRIO e ignora o que a mesa editou pela tela — a página abre, a API
  responde 200 e o cadastro mostra o valor de fábrica. Só passam os quatro que
  ALIMENTAM o banco ou são o armazém, cada um preso por um MARCADOR à função
  que o justifica; `json.loads(` fica de fora (opera sobre texto já em mãos).
- **`data_path()` NÃO é montagem de caminho — ele ABRE UM DUCKDB** (§522): por
  dentro pergunta ao armazém se o arquivo existe (`_existe` →
  `data_store.exists`), e no share, frio, isso custa de segundos a minutos. Daí
  `X = data_path('Y.json')` no NÍVEL DE MÓDULO pagar a abertura dentro do
  IMPORT, que na instância é a subida com o app sem atender — e não dar erro
  nenhum na dev, onde os dados são locais (§9). Vale também para o
  `mapping_file`/`with_fallback`, que caem nele **sem um `data_path` visível na
  linha**. Resolva no PRIMEIRO USO: `__getattr__` de módulo onde os testes
  TROCAM o atributo (`R.DOMINIO_JSON = base` — virando função, o patch pararia
  de valer em silêncio e o teste leria dado real, §3) e FUNÇÃO onde o nome é
  lido de DENTRO do próprio arquivo (`__getattr__` de módulo não alcança isso:
  daria `NameError`). `check_boot_lazy_paths.py` MEDE e varre por AST.
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
  tela vem ESTRUTURADO (a lista, não a frase). **Vale para TODO aviso, erro e
  alerta, em qualquer página** (regra do usuário, 17/09/2026): o servidor manda
  `{code, params, text}` e a tela diz pelo `_TRANS` (`w_<code>`/`e_<code>`),
  com o `text` só de fallback — modelo em `recon_cgd.Aviso`/`avisos_payload` e
  `recon_conf_matching.ReconErro` (§486); título de `Swal` também passa pelo
  `t()`. A dívida do resto do app está medida no HANDOFF §486.
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
| `apps/pages/platform/` (18 módulos) | infra horizontal: `anbima`, `authz`, `db`, `dates`, `json_cache`, `mail`, `email_validation`, `notifications` e os motores `settlement`, `confirmations`, `counterparty`, `forecast`, `electronic_inventory`, `manual_confirmation`, `file_interpreter`, `pending_confirmation`, `operations_b3`, `new_deals` |
| `apps/pages/features/<nome>/` (49 verticais) | `entrypoint.py` (rotas) · `commands.py` (escrita) · `queries.py` (leitura) · `domain.py` (regras puras) · `infra/` — todas em desenho fino; não existe mais `engine.py` |
| `apps/pages/database_access.py` | a camada de banco: permit + lock de arquivo + farol de eventos (§4) |
| `data_store.py` · `duck_read.py` · `json_to_duckdb.py` | o ARMAZÉM (o `DATA_DIR` como sistema de arquivos virtual sobre os DuckDB), a fachada de leitura com os nomes antigos, o motor de conversão (§4) |
| `data_paths.py` · `request_cache.py` | caminhos de dado; `once_per_request`/`req_cached` |
| `manual_conf.py` · `cgd_docs.py` · `otc_tickets.py` | donos dos bancos da esteira, do Onboarding e do store de tickets |
| `athena_api.py` · `otc_boxparse.py` · `otc_boxscan.py` · `otc_emails.py` · `webpush.py` | Athena (SSO Kerberos), parser do recap, varredura do box, e-mails, push |
| `recon_fxo.py` · `recon_cgd.py` · `recon_payrec.py` · `recon_comitente.py` · `recon_conf_matching.py` | motores das recons |
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
  Ela é SÍNCRONA — enquanto roda, o app não atende —, então acima de 30 s
  avisa que é ela que segura a subida e aponta o
  `convert_json_to_duckdb.py`. **E ela só roda quando o que vem empacotado
  MUDOU** (§519): o carimbo `_seed_stamp.txt`, a impressão digital de
  (caminho, mtime, tamanho) de cada arquivo, calculada na mesma varredura.
  Igual ao gravado, a passada inteira é pulada — ela era idempotente e
  pagava **177 aberturas de DuckDB no share** para descobrir que não tinha o
  que fazer, ~15 min de subida com o app sem atender. O carimbo mora no
  `DATABASE_DIR` de propósito (apagar os bancos apaga o carimbo junto; no
  disco local ele sobreviveria a um `db/` apagado e o cadastro nunca
  voltaria), passada INCOMPLETA (banco ocupado/ilegível) **não** carimba, e
  `OTC_SEED_ALWAYS=1` força. E na DEV, onde o checkout É o `DATA_DIR`
  (`origem` e `alvo` o mesmo arquivo), ela NÃO reimporta na subida o objeto
  que o banco tem sem canal: o `read` cai para esse mesmo arquivo e importa
  em background. Na mesma situação, `cache/` inteiro fica FORA da semeadura:
  arquivo-dia não vem do repositório (`cache/**/*.json` é gitignorado) e
  convertê-lo na subida é fazer o cutover dentro do boot, a ~2 s por arquivo,
  com o app sem atender — quem carrega dia é o `convert_json_to_duckdb.py`
  (com o app parado) ou a primeira leitura da data. Uma linha de log lembra
  que, até lá, quem ENUMERA dia só vê o que está no banco (§447).
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
- **O registro do `_manifest` é DELETE + INSERT, nunca `INSERT OR REPLACE`**
  (§443): o upsert do DuckDB exige uma PRIMARY KEY, e o banco que passou pelo
  slim antigo não tem mais a dele — o `CREATE TABLE … AS SELECT` copia os
  dados e deixa a chave para trás. Sem isso o banco vira SOMENTE-LEITURA sem
  aviso: as leituras seguem perfeitas e toda gravação morre em `Binder Error:
  There are no UNIQUE/PRIMARY KEY constraints`, no fim do request.
- **Payload-OBJETO volta EXATO** (recons, `.meta.json`, ponteiros `_last`):
  além das sub-tabelas de análise, o objeto inteiro vai como texto na tabela
  `<tabela>__raw` de uma linha. Banco anterior a isto tem o objeto sem o
  `__raw` — **`SemCanal`** (um `IOError` com o caminho e o remédio, §442),
  nunca "ausente": `read` cai para o JSON legado em disco se ele existe e a
  importação SUBSTITUI o objeto sem canal (`so_se_ausente` = ausente OU sem
  canal; a gravação da tela sempre tem `__raw` e vence); a semeadura
  reimporta da cópia do repositório o objeto que o banco tem sem canal
  (`tem_raw`), avisando. Leitor que engole `Exception` como "não há"
  esconde isso (era o "template missing" do File Interpreter): ocupado
  sobe, o resto vai para o log com o motivo. Todo `.json` do `DATA_DIR` tem banco — inclusive os ponteiros
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
  raiz num tmp ler só o que gravou). Para o `data_path()`, banco OCUPADO
  conta como EXISTE no `DATA_DIR` — lido como "não há", ele caía para a
  seed do repositório e o cadastro editado sumia enquanto durasse a trava
  (§440). E "há base viva?" se pergunta ao armazém, nunca a
  `os.path.isfile`: as bases das Tools (`precificador/bases.py`) eram
  re-semeadas e regravadas a cada leitura por isso.
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
  `error=database_busy` com `Retry-After`, nunca 500 HTML. Banco ILEGÍVEL
  (o `.db` existe e o DuckDB não abre: `.wal` de outra versão, arquivo
  truncado) é `BancoIlegivel`, subclasse do ocupado: mesma resposta, nunca
  "vazio"; UM WARNING por banco por minuto diz qual e por quê, e o 503 sai
  como `database_unreadable` (§441). **Toda OUTRA exceção que escapa de uma
  rota `/api/*` vira JSON 500 com `tipo: mensagem`** (`_handle_api_exception`,
  §449) e o traceback no log como `[api-error]`; a tela lia a página HTML do
  Flask e mostrava só `Unexpected token '<'`. O claim diário
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
  teto degrada, nunca enfileira. O leitor que chega com escritor
  declarado DESISTE no teto (`try_enter_read`, sem se registrar), senão
  várias abas se revezam, a contagem nunca zera e a escrita bate no
  `read_only` aberto (§547). Poll que ainda esbarra serve `_notif_last_good`
  (por SID × papel, teto 10 min — preserva o alarme de conexão vazada).
- **Assinaturas de "arquivo em uso" moram no `database_access`**
  (`FILE_IN_USE_SIGNATURES`/`is_file_in_use`, `True` também para
  `DatabaseLockTimeout`); `_notif_arquivo_em_uso` é alias. Aviso
  `file_lock_skipped` sai uma vez por banco.
- **A tabela do sino é expurgada** (`_notif_purge_old`, thread `notif-purge` 3
  min após a subida e diária; `OTC_NOTIF_RETENTION_DAYS` = 90, `0` desliga).
  O poll filtra `created_at >= CURRENT_DATE` (sem `DATE()` na coluna).
- **Mensagem de erro de API leva o MOTIVO, não só "não deu"** (§476): ela é a
  única coisa que a mesa vê, e um `except Exception` que responde uma frase fixa
  não distingue dado ausente de fonte fora do ar — o relato chega sem nada por
  onde começar, e a investigação recomeça do zero a cada vez. `tipo: mensagem`
  na resposta e o traceback inteiro no log, que é o desenho do
  `_handle_api_exception`. Foi assim que o `Could not read the swap position`
  do Swap Calculator, que resistiu a três tentativas de adivinhação, virou um
  diagnóstico de dois minutos assim que passou a dizer o `ValueError`.
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
- **Quem vai GRAVAR lê estrito, fresco e sob a trava** (§548): o loader do
  leitor (tolerante, com cache) lê ocupado como vazio, e a gravação seguinte
  escreve só o registro novo por cima do resto. Dentro do processo, o ciclo
  inteiro sob o `_cache_lock` com `*_load_for_write`/`_day_records_for_write`.
  ENTRE instâncias (a esteira: MO e FO validam em paralelo) o `_cache_lock`
  não alcança: relê DENTRO do `duckdb_write` (`manual_conf.mutate_row`) e
  grava só o que mudou (`save_changes`). Cache nunca guarda a leitura que
  falhou: mantém o último valor bom e não carimba. Upsert entre categorias grava
  o DESTINO primeiro e só então limpa as outras (pior caso: duplicata, não
  perda).
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

> **`.wal.checkpoint`/`.wal.recovery` ao lado de um `.db` é o LIMBO de
> checkpoint do DuckDB (§442)**: um checkpoint começou (o `.wal` bateu os
> 16 MB do `checkpoint_threshold`) e o processo morreu antes de terminar.
> Daí TODA abertura, mesmo só leitura, refaz o replay dos dois WALs (na
> instância, 75 MB a 1,1 GB por banco, pelo share: os "minutos por
> abertura" que pareciam banco ocupado), e toda abertura em escrita ainda
> os funde num `.wal.recovery` antes — e é morta de novo. O app avisa na
> subida (`[boot] banco em RECUPERAÇÃO DE CHECKPOINT`); a saída é
> `scripts/recover_duckdb_wal.py` com TODAS as instâncias paradas: recupera
> numa cópia LOCAL (segundos), emagrece, troca. Nunca apague o WAL à mão:
> o dado desde o último checkpoint só existe nele. O `slim_duckdb.py`
> recusa banco nesse estado (o `ATTACH` refaria o replay pelo share).
>
> **O WAL que NÃO REPLAYA é o outro fim do mesmo §442** (`Catalog Error:
> Failure while replaying WAL file "….db.wal": Table with name "d_20260119"
> already exists!`): o `.db` e o `.wal` ao lado deixaram de ser o mesmo par
> (checkpoint que gravou o catálogo sem truncar o WAL, `.db` trocado com o
> WAL antigo ao lado, WAL de outra versão do duckdb — cada pessoa roda a
> própria instância sobre o MESMO `db/`). Aqui NENHUMA abertura passa do
> replay, nem a de leitura: o banco é `BancoIlegivel` para sempre e o log
> repete o traceback a cada request. Fundir, inverter a ordem, tentar cada
> WAL sozinho ou recuperar no disco local não muda nada — a única saída é
> DESCARTAR o WAL (`recover_duckdb_wal.py --all --descartar-wal --only
> <o banco>`), o que
> perde o que foi gravado depois do último checkpoint (no `cache/` isso
> volta na importação ou na rotina do dia). É opt-in de propósito, e o WAL
> original vai inteiro para `db/_recuperado/`. O aviso de ILEGÍVEL do
> `data_store` reconhece o caso (`wal_replay_falhou`) e imprime esse
> comando — na leitura e na SEMEADURA da subida, que ramifica o ilegível
> ANTES do ocupado (a herança do §441 junta os dois para LER e os separa
> para AGIR: o ocupado sai sozinho na próxima subida, este não sai de
> nenhuma). A sonda da subida NÃO o vê (um `.wal` pequeno não é limbo).

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
restart**. **Banco ocupado SOBE, nunca vira seed** (§548): o Save
substitui a lista inteira, e o seed lido como cadastro seria gravado por cima.
O GET da tela é `strict=True`; o POST exige a página `/mapping`, e o
`swap-index` gravado por aqui entra no maker-checker do Index B3.
API `/api/mappings/<key>` GET/POST; o POST substitui o arquivo
inteiro; valores **não são trimados** (`'C '` é código B3). O front mantém os
literais antigos como fallback. `upgrade` converte formato antigo na leitura;
**seed só roda quando o arquivo não existe** — correção de seed não alcança
quem já tem o cadastro, e por isso precisa de `upgrade`. `autofill` preenche
outra coluna; tipo **`refdata`** liga nome/SPN/Tax ID ao Reference Data (um
escolhido, os outros dois se preenchem). **`file`** aponta para um JSON já
existente (o `swap-index` edita o mesmo `SwapIndex.json` do Index Results —
declare as colunas extras, senão o POST as derruba).

São **47**: `swap-bullet-curve`, `currency-base`, `interbook-ndf`, `commodities-b3`,
`publisher-ndf`, `le-accronym`, `le-spn`, `bank-name`, `fxo-conv-rate`,
`ndf-pdf-cpty`, `swap-curves`, `cetip-files`, `api-links`,
`manual-conf-validation`, `manual-conf-sla`, `fxo-internal-cpty`,
`fxo-book-disregard`, `opb3-events`, `swap-ir-client`, `swap-ir-term`,
`bankers-email`, `swap-index`, `ndfc-ir-exempt`, `b3-accounts`,
`ndfc-advice-split`, `tools-swap-index`, `opb3-msg-asset`,
`swap-funcionalidade`, `swap-amortizacao`, `swap-code-labels`,
`quotes-equity`, `quotes-commodity`, `mt300`, `settlement-exception`,
`gdt-codes`, `equity-leg-prefix`, os sete `dce-*` e os quatro `cgd-*`.

### Regras fáceis de quebrar pela tela

- **`opb3-events`** — regra Tipo Título × Tipo Operação × Status B3, campo em
  branco = coringa, `USE` Consider/Disregard. Disregard vence; Tipo Título com
  um Consider próprio vira lista branca; sem Consider não é filtrado. A MESMA
  resposta para NDF Summary, Other Products, avisos e mensageria (§213).
- **`publisher-ndf`** — linha sem Match Tokens casa só com o texto completo;
  `NOTES = BACEN` é o que roteia para Vanilla (§166).
- **`commodities-b3`/`cetip-files`** — padrão, não literal: `"MY"` = letra do
  mês + ano, `_` = espaço (no B3 Code, em QUALQUER TYPE: quem diz que é
  padrão é o marcador, e o `_` vira espaço até no FIXED — §544), `YYMMDD` = Reference Date. `TRADE TYPE`
  (VANILLA/ASIAN/BOTH) por linha (BRT_IPE e WTI têm duas); `QUOTE TYPE
  NDF/OPT` e `INFO SOURCE` guardam o código do layout Conecta, default
  `A`/`5`/`358` (`_b3_quote_cfg`); cópia no navegador em
  `b3-quote-config.js`, `check_quote_type.py` prova a paridade.
- **`api-links`** — uma linha por uso × produto (`New Deals` × NDF/FXO/
  Commodities/Swaps, `Unwinds` vazio de propósito, `Recon FXO`, `Intrag DCE`,
  `Daily Settlement` × NDF = `getTradesBySettle`); `SOURCE` API × Bob Report;
  `YYYYMMDD` é a data; produto é o parâmetro da API, não a página. O
  `settlement` da API é LISTA e o valor é o primeiro item numérico de `Rolled
  Positions` (§425) — **no cross SEM BRL (USD × GBP, USD × EUR) é o SEGUNDO**:
  ali o primeiro é o notional da moeda (mesa, 22/09/2026; `_ndfc_api_rolled`).
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
  (`liquidacao.INDEXADORES`). **Curva `pre` sai sempre `composto`** (§466): o
  seed trazia `simples` nas três curvas pré e a perna pré-preenchida nascia
  Simple enquanto a tela em branco nascia Compound — e seed só roda quando o
  arquivo não existe, então quem conserta o cadastro de quem já o tem é o
  `upgrade`. O `Código Identificador` da posição NÃO é chave
  (guarda a LOB); quem casa o DFLUXO é o `Código do contrato` (§427). O período
  de cada fluxo é do servidor (`p_inicio`/`p_fim`), candidato não anterior ao
  fim é descartado.
- **`quotes-*`** — código → símbolo Yahoo; opções da tela = `Subjacente.json`
  ativo ∪ linhas literais do cadastro; sem símbolo é 404 pedindo cadastro; em
  commodities as DUAS colunas aceitam `"MY"` (`quotes.symbol_lookup`, ano de 1
  ou 2 dígitos, sufixo de bolsa depois do vencimento, prefixo mais longo vence,
  literal vence padrão). Registro em `DE_PARA_TICKERS_COTACOES.md`.
- **`cetip-files`** — a regra VIVA de quais arquivos a rotina salva: arquivo
  que não está aqui não é salvo, e nenhum código diz o contrário. Como o
  `seed` só roda com o arquivo AUSENTE (§6) e a instância já tem o cadastro,
  **arquivo novo exige o `upgrade`** (`_cetip_files_upgrade`), que casa pelo
  nome entre PARÊNTESES do TYPE — o prefixo é descrição e pode ter sido
  reescrito na tela. Dois arquivos não são posição e atualizam uma BASE depois
  de salvos: `INDEXADORESSWAP_VCP` → `VCP.json` e
  `CADASTROCURVASMOEDASFEEDERDOMINIOS` → `Dominio.json` (§492).
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
  **Com `scrollX` a delegação é no CONTAINER da tabela**
  (`dt.table().container()`), nunca em `#tabela thead` (§462): o `scrollX`
  CLONA o cabeçalho para o topo rolante e esconde o original, e é no clone que
  a pessoa digita — `#tabela thead` alcança só o original escondido (o clone
  perde o id, como na regra de centralização acima). O evento não chega e
  digitar não faz nada, sem erro nenhum. Tabela `scrollX: false` não tem clone
  e funciona dos dois jeitos — o container cobre os dois casos. E **quem tem
  linha de filtro tem Clear Filters** alcançando as DUAS cópias do cabeçalho.
  **Filtro aceita LISTA** (`123; 456`, `,`/`;`/quebra de linha — os Trade IDs
  colados de uma coluna do Excel): a linha passa se QUALQUER valor casar. No
  navegador é o `sf-multi.js` (`otcSfMulti.columnSearch`, regex OR — a busca
  padrão do DataTables faria E entre as palavras; e o colar troca as quebras
  por `; `, que o `<input>` comeria), no servidor o `_filter_tokens` do
  `_deal_matches`. Milhar (`1,250,000`) é UM valor. `check_sf_multi.py`.
  `check_export_padrao.py` recusa `#tabela thead` em página `scrollX` **sem
  lista de exceção**: é bug silencioso, não dívida de estilo.
- **Botões de ação: squircle 32×32** travado nos DOIS eixos, `padding:0`,
  `border-radius:10px !important`, ícone Tabler `1rem` (nunca `.fs-13`),
  tooltip colorido delegado no primeiro hover (os `<td>` são reescritos a cada
  redraw). Regra GLOBAL no `visual-refresh.css`; ordem Confirm `ti-check` →
  Edit `ti-edit` → Delete `ti-trash` → Send `ti-brand-telegram`; edição Save
  `ti-device-floppy` + Cancel `ti-x`. **A COR é semântica e o guarda varre TODA
  página**: Confirm/Approve `btn-success`, Edit `btn-info`, Delete `btn-danger`,
  Send `btn-primary`, Save `btn-success`, Cancel `btn-secondary` — duas telas
  novas nasceram com o Edit em `btn-warning` e nada acusou, porque o guarda só
  olhava as duas páginas de referência. `check_row_action_buttons.py`.
  **`d-none` esconde botão de linha — e só voltou a esconder em 18/09/2026**
  (§497): a regra de FORMATO do `partials/head-css.html` declara `display:
  inline-flex !important` nessas quinze classes, mesma especificidade do
  `.d-none` do `app.css` e carregada DEPOIS dele, então todo
  `toggleClass('d-none', …)` de botão de ação era mudo — o botão continuava na
  tela e só o servidor recusava. O par `.btn-row-x.d-none` (0,2,0) no mesmo
  arquivo resolve para o app inteiro; página nova não escreve nada.
  **Editor inline acha a célula pela API (`table.cell(linha, coluna)`), nunca
  pelo índice do `<td>`**: coluna escondida sai do DOM, e daí o i-ésimo `td`
  deixa de ser o i-ésimo campo — o que se digita numa coluna é gravado no
  campo de outra, calado.
- **Toolbar** `mb-3` (o DataTables come a margem do irmão), `.btn-toolbar-all`;
  cores por função: Columns soft-primary, Add Row primary, Export info
  (**Copy · CSV · Excel · Print · PDF**, DataTables Buttons; CSV `;` + BOM;
  Excel exige o registro síncrono do JSZip), Import teal `#4a849b`,
  Mapping/refresh success, Clear Filters outline-secondary. **O teal do Import
  e o ícone do campo de data moram no `streamflow.css` (§50)**, não copiados no
  `<style>` de cada página: eram iguais em seis e faltavam na sétima, que saiu
  com o Import laranja e a data sem ícone (§490). A classe é
  `.btn-toolbar-import`; o ícone vale por `.otc-datefield` E por `#apiRefDate`
  (com o `altInput` do flatpickr o campo visível herda a classe, não o id). Export termina no
  **Advanced Export** (`otcExportAdvanced('#t', { daily: '<endpoint que a
  própria página consulta>' })`, `exact=1` + confere `source_date`, dia sem
  arquivo é pulado, teto 60 s/dia — §304). **Export próprio não existe**: um
  CSV escrito à mão diverge do resto do app no primeiro acento (§461). Célula
  editável sai pelo VALUE do campo, num `format.body` (o texto de um `<input>`
  é vazio, e a coluna sairia em branco) — modelo em `formatExportData`.
  **O nome do arquivo é o do DOCUMENTO** — tela, card quando há mais de um, e a
  data de referência em `AAAAMMDD`, que é como o Advanced Export carimba os
  dele —, nunca o id da `<table>`: `ops-summary-table.csv` não diz nem de que
  tela nem de que dia é. Página com duas tabelas passa `name` explícito, senão
  as duas baixam o mesmo nome (o `defaultName` é o título da página).
  `check_export_padrao.py` prende as três coisas, no estilo do
  `check_modal_standard`: a LISTA de quem já está fora (quinze telas com o menu
  pela metade, o `reconciliation-fxo` com Csv/Copy próprios, o
  `index-b3-results` com quatro tabelas e um nome só) não pode crescer.
- **Alinhamento com `scrollX` são TRÊS coisas**: `columns.adjust()` depois de
  todo draw (+ passe atrasado 150 ms + `resize`); `autoWidth: true`; regras de
  `th` repetidas nos clones com `white-space: normal`.
- **Seleção de célula em TODA tabela**: extensão `select` (New Deals, Intrag)
  ou `table-std.js` + `otcCellCopy('#id', { skip: [...] })` DEPOIS do
  `.DataTable()` (por tabela quando há uma por card).
- **Números** `#,##0.00` com `tabular-nums`; taxa NÃO é valor (Strike fica com
  as casas que tem); formatação só no `display`, sort pelo cru. **Status** é
  badge pill `bg-gradient`.
- **Excel exportado: ID que parece número sai como TEXTO** (§477). O
  `excelHtml5` do Buttons grava como número todo texto que casa
  `^-?\d+(\.\d+)?([eE]-?\d+)?$`, e o contrato B3 `26E04610365` casa — para o
  Excel é 26 × 10^4610365 e a célula abre como `#NULL!` (só a letra E
  dispara; `26G…` é texto). O `#NULL!` NUNCA está no dado: nasce no Excel de
  quem abre o arquivo, e por isso sanitizar o literal (MtM, Swap
  Characteristics) não resolvia. O `patchExcelIds` do `export-advanced.js`
  reescreve no `customize` a célula cujo `<v>` é `dígitos E dígitos` ou 16+
  dígitos (o Excel guarda 15) como `inlineStr`; vale para todo `extend:
  'excel'`, encadeando o `customize` da página. Por isso **toda página com
  `buttons.html5` carrega o `export-advanced.js` DEPOIS dele e com
  `asset_v`** — o Buttons copia o `action` na construção do botão.
  `check_export_excel_ids.py` executa o export no Chromium e cobra os dois.
- **Excel exportado: DATA sai como DATA** (§537). O Buttons só reconhece
  `aaaa-mm-dd`, e toda tela escreve `dd/mm/aaaa`: a data chegava como texto
  (General), sem ordenar nem filtrar por mês. O mesmo `customize` do
  `export-advanced.js` (`asDates`) grava o serial do Excel com numFmt
  `dd/mm/yyyy` EXPLÍCITO — o numFmt 14 do Buttons é a data curta do Windows de
  quem abre, `mm/dd` no JP. Data inválida fica texto. Mesmo guarda.
- **Preview de arquivo é o `otcFilePreview` (`static/js/file-preview.js`)**
  (§480): uma aba por arquivo/visão, tabela Bloco · Campo · Formato · Valor
  com o badge da origem do cadastro e o arquivo cru embaixo. A página passa
  `files` (campos do servidor ou do gerador do navegador + `blockFields` do
  template) e os botões do rodapé; não desenha tabela própria. **O rodapé é
  Export · Edit · Close em toda tela que gera arquivo** (`buttons`): página
  sem endpoint de download usa `download: 'raw'` — o helper baixa o arquivo
  cru de cada aba, com o `file_name` e o `encoding` dela (`cp1252` onde a B3
  conta bytes, §480) — e o Edit é um `onEdit` que dispara o Edit da LINHA
  (some junto, em `Sent`). `check_file_preview_buttons.py`.
- **Autocomplete nunca é `<datalist>`**: dropdown próprio abaixo do campo, mesma
  largura, `max-height` ~220px, item por `mousedown` (antes do `blur`),
  reemitindo `input`/`change` (`mapAttachDrop`, `.ar-ac-drop`).
- **Data é SEMPRE `dd/mm/aaaa` e `<input type="date">` visível é proibido** (o
  nativo desenha no locale do sistema — `mm/dd` no Windows do JP). flatpickr
  com `altInput` (`otcDateField`/`otcDateSync` do `export-advanced.js`; quem
  escreve por código chama `el._flatpickr.setDate`; largura em CLASSE porque o
  `style=` fica no campo escondido; ícone como background SVG embutido) ou
  daterangepicker `singlePicker` `DD/MM/YYYY`. `type="date"` só invisível atrás
  de texto readonly (`.date-wrap` das recons). **E o campo se DIGITA: só os
  NÚMEROS, as barras se escrevem sozinhas** (mesa, 22/09/2026;
  `otcDateMask`, aplicada pelo `otcDateField` ao **altInput**, que é o campo que
  se vê). Sem ela o parse frouxo do flatpickr lê `2208/2026` como uma data
  QUALQUER, sem erro nenhum. A data INTEIRA vai ao picker na hora
  (`setDate`) — o código em volta lê o ISO do input original, e ele só nasceria
  no blur: clicar direto no botão exportaria o intervalo anterior. A mesma
  regra da Quotes (§508) mora aqui no HELPER, não na página.
  `check_export_padrao.py` §5.

### Layout e vidro

- **Tabela em painel PRÓPRIO (fora de `.card`) tinha o topo do cabeçalho
  CORTADO** (§486): o `app.css` do tema puxa o `.dt-container` 12px para cima e
  o `.table-responsive` (`overflow:auto`) corta o checkbox e a primeira linha
  do rótulo. Está resolvido NA RAIZ, no `streamflow.css` §49b
  (`.table-responsive > .dt-container { margin-top: 0 }` + respiro em
  `margin-top`, ANTES da regra do `.card`, que tem a mesma especificidade) —
  tela nova não escreve nada, e **não se conserta com `padding-top` na página**
  (padding fica dentro da área que rola, §49). Mexeu no `streamflow.css`, sobe
  o `?v=` do `head-css.html`.
- **Não use `.card` para widget seu** — o `extra_css` da página carrega ANTES
  do tema e perde. Padrão: `<div>` com classe própria (`.ndm-card`,
  `.fxo-widget`) com `--vr-card-*`/`--vr-grad`. Pela mesma ordem, classe
  Bootstrap de mesma especificidade vence a da página mesmo com `!important`,
  e o `background: … !important` do `.card` apaga `background-image` (cartão
  com gradiente vai no `streamflow.css`).
- **Estado visual de widget seu (`is-ok`/`is-check`) leva PREFIXO DE ID**
  (`#ops-page .ops-recon.is-ok`, como o `#ndm-page` do New Deals Monitor) —
  §464. Classe que termina em `-widget` casa com o seletor ESTRUTURAL do tema
  (`div[class*="-widget"]:not([class*="__"]):not(.row)`, §23.1 do
  `streamflow.css`), que declara `box-shadow` com especificidade **0,3,1** e
  carrega DEPOIS do `extra_css`: a regra da página (0,2,0) perde pelos dois
  critérios. Nada some, o cartão continua bonito e só falta a informação — a
  classe ESTÁ no elemento e o token resolve certo. Medir o `box-shadow`
  computado exige esperar a `transition` do tema (~0,3 s): lido na hora, ele
  devolve a cor ANTIGA no meio da animação e a sonda mente.
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
- **O Confirm da linha leva New E Amend direto para `Approved`** (§540, mesa
  23/09/2026); **`Pending` é só do Save do modal de Edit**. Nas seis páginas de
  NDF/Opção a regra é o `directToApproved` do JS (com as travas de contraparte
  e ativo); no Swap Bullet/Cashflow é o `commands.set_status`.
- **O servidor confere o 4-olhos do PATCH** (`_nd_guard_updates`, §548):
  Maker/Checker saem da SESSÃO, o próprio Maker não leva Pending → Approved
  (`same_user`), e Sent/Success não voltam por aba velha
  (`status_regression`). O JS é conveniência.
- **As datas de verificação do asiático têm UMA fonte**
  (`_asian_verification_dates`, §549): as linhas tipo 2 e o campo 59 contam
  as MESMAS datas; sem `FXHolidaySchedule` (a API não manda) vale o ANBIMA, e
  calendário ilegível LEVANTA. Eram dois calendários, e o 07/09 foi à B3.
- **Só `isCancelled` é cancelado** na Athena; `isDead` importa normalmente.
- **O veredito do `mapping-b3` sai da GRAVAÇÃO, nunca da intenção** (§521): os
  quatro endpoints decidiam o Status pelo arquivo de retorno da B3 e o
  devolviam à tela sem olhar se o arquivo-dia foi gravado, atrás de um
  `if file_path is not None:` e de um `except Exception: pass` — linha não
  achada pelo `(Deal, Client)` EXATO, ou `BancoOcupado` da instância vizinha
  (que ali é ESPERADO, §4), e a grade pintava um B3 ID que o banco não tem. Hoje
  a gravação é o funil `_grava_mapeamento`, que DIZ se gravou: sem `saved` não
  vai B3 ID, o status é **`Failed`** e não `Error` (`Error` é o veredito da B3, e
  confundi-los manda a mesa procurar no arquivo de retorno um problema que está
  do lado de cá), as duas saídas logam `[MAPPING-B3]` com deal e cliente, o que
  não gravou não vira espelho em Intrag nem Pending Confirmation, e o sino conta
  os GRAVADOS. Nas seis telas o `saved` é testado ANTES do `Success`.
  `check_nd_mapping_b3.py`.
- **O notional do NDF é SEMPRE o da moeda que não é BRL nem USD** (§485,
  `_ndf_notional_leg`): com BRL no par, a outra perna (USD/BRL → USD, CNH/BRL
  → CNH); sem BRL, a que não é USD (USD/CNH → CNH); nenhuma das duas BRL/USD
  (MXN/CLP) fica como bookado. A Athena pode bookar a `Quantity` em qualquer
  perna — o import move o notional para a `OTHER QUANTITY` quando a perna é a
  Other, trocando as moedas; sem Other Quantity fica como veio. Por isso
  `IsBRRFixed` não nasce mais da API. **A posição é da moeda do notional e
  quem a diz são `Pay CCY`/`Rec CCY`** (recebemos → compra, pagamos → venda);
  o `Type` é só fallback, virado quando o notional trocou de perna num par
  sem BRL. Confia nos RÓTULOS da API: se `Quantity Currency` rotular ao
  contrário do valor, o número sai da perna errada.
- **A inversão da moeda fraca é do PAR** (`_ndf_weak_leg`, cadastro `Weak
  Ccy` do `currency-base`), uma vez na importação, e NÃO exige BRL: exatamente
  uma perna fraca inverte (USD/CNH inclusive); zero ou duas, não. O TER
  **não** arredonda mais pelo `INV DECIMALS` (§474): o
  campo 18 é `9(12)V9(8)` e vai com as OITO casas, sempre — o cadastro segue
  valendo no que a tela mostra. E o campo 16 é `9(14)V9(2)`: os dois decimais
  são os do notional, não um `'00'` colado — o gerador ARREDONDAVA para
  inteiro, e 5.158.000,75 ia à B3 como 5.158.001,00 sem mudar a largura da
  linha. Vale para Vanilla, FWD Start e Other Publisher; o Commodities tem
  gerador próprio e ficou como estava.
- **A API nunca entrega a perna Lawton/MGT**: `_nd_lawton_mirror` e
  `_nd_mgt_mirror` sintetizam no envio, pareando por termos econômicos
  (`_nd_lawton_sig`), com `force_values` por linha para a conta do omnibus e
  para o **CPF/CNPJ Cliente Parte** (campo 7) — na visão CLI x MGT a parte é o
  omnibus 73760.20-5, que não identifica ninguém, e o documento sai do deal
  ORIGINAL (o espelho zera o `TaxID`, que é do campo 9 e é intragrupo). O
  preview do modal tem a cópia da regra (§445).
- **A Data de Fixação do FWD Start (campo 36 do TER) é a Strike Set Date + UM
  dia útil ANBIMA** (mesa, 18/09/2026). Ela avançava pelo VÃO de dias úteis
  entre a Last Fixing Date e a Settlement Date — a mesma conta dos campos 15 e
  39, que continuam com ele —, e num vencimento longo isso jogava o início do
  contrato semanas à frente da data em que o strike é fixado. Mexer aqui mexe
  em DOIS lugares: o gerador (`platform/new_deals.py`) e o espelho `_legacy_*`
  do `check_fi_ter.py`, que é golden byte a byte — o teste aponta a posição
  exata (233-240) quando eles divergem.
- **Os textos da Parte A do FWD Start vivem no `routes.py`** de propósito (a
  grafia é a do documento assinado) — LE ausente deixa em branco com aviso e o
  Save recusa (`400 missing_partea`).
- **Cache das três páginas genéricas: `NDF/Vanilla`, `NDF/FwdStart`,
  `NDF/OtherPublisher` SEM espaço** (`check_nd_cache_dirs.py`).
- `otc_boxparse.py` e `otc-fileupload.js` são duas cópias da mesma regra;
  `check_boxparse.py` prova (precisa do `jsc` do macOS).
- **NDF de MGT contra cliente tem documento PRÓPRIO e entra na esteira**
  (§453): `ndf-mgt-strike-me.html` serve Vanilla e FWD Start, com a Parte A
  fixa na filial brasileira da JPMORGAN CHASE e o eixo de grupo por PRODUTO
  (a pasta do Inventory é o tipo). O Vanilla só ganha `source` de
  confirmação quando a LE é MGT (`_generic_nd_mc_source`) e nasce `Pending
  OTC`; o do BANCO segue sem esteira. O FWD Start do BANCO deixou de listar
  os de MGT, e o Generate do Monitor escolhe o editor pela Legal Entity.
  **FWD Start é numerado pelo B3 ID em QUALQUER LE** (mesa, 23/09/2026; §539):
  coluna Nº do Anexo I E `numeroContrato` do XML, no documento do BANCO e no
  de MGT (`_conf_mgt_num_field`, `num_field` do `_conf_ndf_xml`; sem B3 ID o
  XML cai no Athena ID avisando). O **Vanilla de MGT** segue com o Athena ID
  (o `Deal`, §484). O título do documento MGT é só "CONFIRMAÇÃO DE
  OPERAÇÕES DE DERIVATIVOS", sem "Nº" nem número. As chaves da esteira não
  mudam com isso.
- **O eixo do ATIVO da confirmação é UM, e vale nos TRÊS lugares** (§457):
  a segregação dos grupos (`_conf_segregate`), a escolha do grupo na geração
  (`_conf_pick_eligible`) e a coluna `Moeda` da ESTEIRA, que é quem monta o
  card do Monitor. No termo de moeda ele é a **Moeda Base** (a estrangeira do
  par), e quem responde é `_conf_fwdstart_moeda`, pelo `_mc_moeda_do_ativo` —
  ler a `QuantityCurrency` crua ali fazia duas operações da mesma contraparte
  em moedas diferentes, **cotadas em BRL**, caírem num card só; o Generate
  abria o documento de uma e a outra sumia. Para a linha antiga que já está no
  banco com o eixo velho, o `_mc_generate_url` devolve o grupo da LINHA
  CLICADA (não o primeiro que casar) e loga um aviso.
- Só produtos de `_MC_CONFIRMATION_SOURCES` geram documento na esteira;
  `_mc_save_from_deal` é chamado de dentro de `_pc_save_from_deal` e **não
  retroage** — quem recupera o passado é o `backfill_manual_confirmations.py`,
  e **produto novo na lista exige família nova lá** (`check_mc_backfill.py`
  prende a paridade). Sem ela as operações NOVAS entram na esteira e as
  ANTIGAS ficam invisíveis para sempre no Confirmations Monitor, sem erro
  nenhum — foi o que aconteceu com o `NDF VANILLA` de MGT. Mercadoria e FXO são
  sempre JPM (`_MC_JPM_SOURCES`); razão social do `le-spn`.
- **O Monitor é uma TABELA por zona, não uma parede de cartões** (mesa,
  22/09/2026). Eram 34 cartões, um por produto, quase todos zerados: a frase
  "No operations imported for this date." repetida 28 vezes e 2.900px de
  rolagem para dizer que o dia estava parado. A pergunta da tela é uma só — o
  que ainda precisa de ação, e onde —, e ela se responde COMPARANDO produtos,
  que é leitura de tabela: uma linha por produto, contagens por status em
  colunas alinhadas, 1.563px e o dia inteiro numa tela. As colunas de status
  são a UNIÃO do que aparece NA ZONA (B3 fala New/Pending/Approved/Sent/Success
  e a esteira das Confirmations fala Pending OTC/MO/FO/Ok — lista fixa mostraria
  coluna vazia de um lado e esconderia status do outro), e a coluna-resumo se
  chama **Open**, nunca "Pending": já existe um STATUS com esse nome, e duas
  colunas homônimas na mesma tabela não se distinguem. **O que é "em aberto" é
  a MESMA regra do aviso das 19h** (`Success`/`Ok` mais o que o card declara em
  `done`, comparado sem caixa): duas definições fariam a tela e o e-mail
  cobrarem números diferentes da mesma mesa no mesmo dia. Produto sem movimento
  fica RECOLHIDO atrás de uma linha que diz quantos são — sumir calado faria
  "sem movimento" e "produto que não existe" virarem a mesma coisa na tela. E
  **as três zonas não se somam num total**: a mesma operação aparece no registro
  da B3 e no espelho da Intrag, e somá-las inventaria um número que nenhuma das
  duas telas confere.
- **A tabela do Monitor tem PESO** (mesa, 22/09/2026). A primeira versão dela
  respondia certo e parecia vazia: o resumo da zona era uma frase cinza de
  .78rem jogada à direita, e num dia parado a tela inteira era três lajotas
  brancas com uma linha de texto. O que mudou: o resumo virou NÚMERO grande
  (aberto em âmbar, importado em neutro), a zona ganhou o fio do gradiente da
  casa no topo, as contagens viraram PASTILHAS (um dígito colorido solto se
  perde no branco da linha) e o dia parado virou uma pílula verde que DIZ, no
  lugar de meia tela de branco. O vão entre o nome do produto e as colunas de
  número — meio metro de branco numa tela larga, porque o nome fica com toda a
  sobra — é hoje a **composição da linha**: a mesma barra da zona, produto a
  produto, que dá a forma do dia sem ler dígito nenhum. As duas barras saem da
  MESMA função (`segmentos`) e a cor de cada status mora numa variável
  (`--st-fg`/`--st-bg`) que serve à pastilha e ao segmento — duas definições
  sairiam com proporções diferentes no dia em que uma mudasse. A coluna da
  composição é a única sem largura fixa (é ela que recebe a sobra), a primeira
  tem piso de 220px (sem ele o nome quebra em duas linhas) e abaixo de 900px a
  barra da linha some: ali não há sobra, e o que tem de caber é o nome e as
  contagens.
- **A Intrag Unwind é bloco PRÓPRIO, fora do de NDF** (mesa, 22/09/2026): a
  tela dela é de todos os produtos, e dentro do bloco de NDF ela afirmava que a
  recompra espelhada é de termo de moeda — a de opção e a de swap caem na mesma
  página. As `intrag-unwind-dce-*` continuam cada uma na família do SEU produto:
  essas sim são uma tela por produto.
- **O Monitor não recebe lista de produto: ele VARRE o `cache/new deals/`**
  e agrupa pelos dois primeiros níveis não numéricos do caminho (§454). Quem
  diz que um produto EXISTE é o `_NDM_CARDS` (`deals_monitor/domain.py`); o
  pkey sem card vira o genérico `extra-<pkey>`, que desenha no grupo *Others*
  do rodapé, sem link de página, e cuja chave **não começa com `intrag-`** —
  então o e-mail de pendências o classifica como **Registration** (o único
  teste de zona é o prefixo da chave). Foi o que aconteceu com as duas telas
  de DCE, que gravam dia no mesmo cache desde sempre. Card novo mexe em
  `_NDM_CARDS`, `_NDM_TAXONOMY` e nos `GROUPS` do
  `new-deals-monitor.html`; **o front nunca fabrica card** (o `intrag-swap`
  nascia de um placeholder no JS e o mesmo produto aparecia duas vezes na
  tela). `les` só se a entidade sair mesmo do portfolio code — sem a chave, o
  card não desenha subitem, em vez de desenhar um LAW/ATA inventado.
  **A varredura aceita MAIS DE UMA RAIZ** (§491): árvore fora do
  `cache/new deals/` entra com o pkey PREFIXADO (`PREFIXO_UNWIND`), senão um
  `NDF/FX` de lá soma no mesmo card de um `NDF/FX` daqui. E **o card pode
  declarar onde FECHA** (`done`): quem não fecha em `Success` — a recompra
  acaba em `Sent`, porque o B3 ID de volta ainda não existe para ela — ficaria
  pendente no aviso das 19h para sempre. E **o card pode declarar uma `lob`**
  (§517): os DOIS cards de swap — Equities (`EDG`) e CEM (`CEM`) — leem as
  MESMAS pastas, e quem decide é a coluna LOB da LINHA (`_ndm_bucket`, balde
  `<pasta>#<LOB>`; a contagem é por linha, não por arquivo). **Não existe card
  `Swap Bullet`**: bullet e cashflow são FORMATO de contrato, e a CEM também
  tem bullet — é a mesma razão de não existir página "Swap CEM". LOB que não
  diz o card NÃO é chutada: vira `<pasta>/No LOB` e aparece no Others, porque
  escolher um dos dois somaria a operação na mesa errada em silêncio.
  `check_ndm_cards.py`, cujo §7 resolve
  o link do card pelo `url_map` e não pelo nome do arquivo (página com rota
  própria não segue a convenção do catch-all) — e aceita rota ESTÁTICA de um
  segmento antes do catch-all, que é o caso das páginas do catálogo de New
  Deals.

- **Swap Bullet (New Deals › Swap › Bullet) nasce do DEAL TICKET, não da
  API** (§480, `features/swap_bullet/`): xlsx (uma aba por operação: cliente
  e B2B Banco × Atacama) ou PDF no dropzone. **Parte A é a NOSSA perna e
  Parte B a contraparte**, decididas pelo `Ativo VCP`; os rótulos das duas
  curvas se repetem e o parser separa por COLUNA (xlsx) ou ORDEM (PDF), e
  `Cliente`/`Premio` são rótulo E resposta. Texto → código é cadastro:
  `swap-funcionalidade`, `swap-code-labels` (FIELD `Adesão`, por `upgrade`)
  e o novo `swap-bullet-curve` (curva do DT → `Curva X(03)`; a linha `VCP`
  apanha todo ativo VCP). Lacuna recusa o LOTE. A denominação da curva VCP
  é a fórmula do Excel da mesa (`domain.vcp_text`, coluna `VCP Text`). Só a
  perna JUROS leva Sinal/Juros; só a VCP leva PU (SEMPRE `1.00000000`),
  Tipo/Classe, Cupom Limpo (`100.0000000`) e a Data de Cotação em D-n
  ANBIMA; a **Descrição VCP só vai na curva da PARTE** (a ponta ativa da
  visão) e só se ela é VCP — Banco com, Cliente e Atacama sem; o Cap vai na
  perna em que o DT o declara.
  O prêmio vai no 0897 (template `swap-registro-premio`), Titular do 0301 é
  PARTE/CONTRAPARTE de quem paga, Papel/Titular do 0897 são a PONTA pela
  conta MENOR. B2B gera Banco + espelho da Atacama (Meu Número próprio); os
  quatro Meu Número nascem no import e o re-import os preserva.
  A contraparte é IDENTIFICADA pela SPN do DT (Client = `COUNTERPARTY` do
  Reference Data; o texto do DT fica em `ClientDT`; SPN fora do cadastro é
  lacuna; editar a SPN re-puxa o cadastro; SPN de entidade NOSSA responde
  pelo `le-spn` — Atacama vira o B2B). A chave da linha é o `_id`
  interno (oculto): Deal nasce em BRANCO e B3 ID é coluna própria. O
  Economic Affirmation (IF, D0) reproduz o Deal Ticket no e-mail
  (`otc_emails.build_swap_bullet_affirmation_emails`), só para contraparte
  com conta CETIP própria. Dropzone, Import (dry-run → duplicatas → `/cache/batch`,
  substituída = `Amend`) e filtro inteligente (`/cache/search`,
  `_deal_matches`) são o MESMO molde das páginas de New Deals — não
  reinvente. `check_swap_bullet.py` compara os seis arquivos byte a byte
  com os exemplos da mesa. **O arquivo é gravado em cp1252** (§480): o
  Conecta conta BYTES, e o travessão `–` da denominação VCP é 1 byte em
  cp1252 e 3 em utf-8 — em utf-8 o registro passava de 1927 e a B3
  recusava (`Campo 126 conteúdo inválido`, com `â€“` na linha).
  **O B3 ID novo na linha é o MAPEAMENTO** (§481): Status `Success` sem
  passar por Pending, e `commands.b3_mapped` dispara — no B2B a linha da
  **Intrag Swap** (visão da ATACAMA, carteira INTRAGJP633, arquivo-dia da
  Data Início, 36 campos = `ENTRY_FIELDS` da página); contra cliente o
  **Pending Confirmation + esteira** pela porta de sempre
  (`_pc_save_from_deal`), Produto `SWAP` com Opção de Arrependimento e
  `SWAP CORPORATE` sem, chave = B3 ID, LOB do deal (EDG), ativo = curva
  VCP. A confirmação (`/confirmation/swap-edg/opcao-arrependimento`, um
  documento por operação) lê o **Cupom Limpo**: `Close dd-mmm-aa` busca o
  fechamento em Quotes (símbolo do `quotes-equity` pelo rótulo da curva) e
  o Strike é o % sobre ele; `Spot` deixa Preço Inicial e Strike em BRANCO e
  obrigatórios. XML só com o valor em BRL. Platform lê os deals do dia por
  `routes._swap_bullet_engine()` (platform não importa feature).
- **Swap Cashflow e Options EDG são UMA tela e um CATÁLOGO**
  (`features/new_deals/catalog.py` + `pages/new_deals-product.html`, o molde do
  Swap Bullet; 21/09/2026). **Não existe página "Swap CEM"**: o swap da CEM é
  bullet ou cashflow, e o que encaixa CEM e EDG na mesma tela é a coluna **LOB**
  (select `EDG`/`CEM`, no Bullet também). As colunas de swap são as do Bullet
  COPIADAS (feature não importa feature) e o `check_new_deals_catalog.py` cobra
  a paridade. **O Deal Ticket da CEM** trouxe o que o da EDG não tinha, e entrou
  nas DUAS páginas: `FXStart`, `NotionalFC`, Cotação/DCC/Cupom Limpo POR CURVA
  (`CurveXQuote`/`CurveXDCC`/`CurveXCleanCoupon`), o bloco de Atualização de
  Notional e `Observations` — aditivo no `SWB_COLUMNS`, em branco no deal da
  EDG. O **cronograma** do cashflow (a tabela Cash Flow do DT) é a lista
  `CashFlows` do deal, editada no modal; na grade ele é a CONTAGEM (`Flows`),
  que por isso não se digita. Select que é cadastro (`AmortizationType` ←
  `swap-amortizacao`) chega resolvido pelo servidor (`selects_from_mapping`).
  **A API de cada página tem prefixo ESTÁTICO**, não `/api/new-deals/<path>`:
  as genéricas `/api/new-deals/<product>/cache/search` e `/send-conecta` casam o
  slug como `product` e respondem "Unknown product". O `opt-edg` segue em
  stub (`cache/search` vazio, o resto 501 `nd_backend_pending`).
- **Swap Cashflow é o backend do swap da CEM** (`features/swap_cashflow/`,
  §526). O Deal Ticket é o MESMO do Bullet, e feature não importa feature:
  parser, visões, 0897, lacunas, Intrag e o deal das confirmações moram em
  `platform/swap_deal_ticket.py` (puro) e `platform/swap_new_deals.py`
  (leitura pelo CONTEÚDO, cadastros, `enrich`, `b3_mapped`) — o `domain` do
  Bullet só RE-EXPORTA, e o `check_swap_bullet` segue byte a byte. O cashflow
  soma a tabela **Cash Flow** → `CashFlows` (`_CF_HEADERS`) e os rótulos do DT
  da CEM (`_CEM_LABELS`) — as duas são SUPOSIÇÃO sem amostra, isoladas de
  propósito. **A LOB não é chutada**: sem o DT dizer, é lacuna `swc_no_lob`.
  Arquivos: o **0301 de Fluxo Não Constante** (4.2.7 v00003,
  `swap-fluxo-nao-constante-v3`, 2021 caracteres), o **0034 do cronograma**
  (4.2.8, template novo `swap-fluxo-contrato-nao-constante`) e o 0897; cp1252,
  `SWAP_CF_`/`FLUXO_SWAP_CF_`/`PREMIO_SWAP_CF_<LOB>_<VISÃO>.txt`. Perna JUROS
  INTERNACIONAIS é RECUSADA (`swc_intl_curve`: os campos SOFR/TERM SOFR não são
  gerados), IPCA e termo também faltam. O `_conf_load_swap` lê Bullet E
  Cashflow (`routes._swap_cashflow_engine`) — sem isso o Generate do Monitor não
  achava a operação —, e o backfill tem as famílias da pasta `Swap/Cashflow`.
  `check_swap_cashflow.py`.
- **Swap Calculator: a `Denominação` da curva VCP é CONTRATO, e o IR sai do
  CADASTRO** (§479). A posição traz nas colunas 70/75 o texto livre da curva
  (`(3M SOFR + 0.75%)*1.1765 A/360`), e o `*1.1765` só existe ali. Quem o lê é
  `precificador/descricao_curva.py` — interpretador de REGRAS, de propósito:
  cada achado sai com o trecho de onde veio e o que sobra com número e
  operador vai para `nao_lido`, sinalizado; denominação nova = linha nova em
  `_REGRAS`, nunca um modelo. `domain.aplicar_descricao` é UMA função para o
  prefill e para o texto colado na tela (`/api/tools/swap-calculator/curve`);
  a denominação VENCE a coluna quando divergem, guardando `anterior`. Os dois
  campos (descrição, multiplicador) só aparecem na perna VCP (`vcp` do
  prefill, ou o link da tela). O
  `Ponta.multiplicador` incide na taxa ANUAL que capitaliza — `(1 + r·k)^τ`,
  nunca no fator — e a memória xlsx o põe DENTRO da capitalização. O IR do
  Swap Calculator vem de `RegraIR` (`queries.regra_ir_do_cliente`): a exceção
  do `swap-ir-client` vence a direção (a regra do Trade Level, pelas mesmas
  `_swap_ir_excecao`/`_swap_ir_faixas` da platform), fora dela as faixas do
  `swap-ir-term` só com o banco pagando. `check_tools_descricao.py`.
- **Tools › NDF Calculator, Unwind NDF Calculator e Option Calculator** (§510):
  o motor é o `precificador/derivativos.py` (PURO), e as três telas são o
  desenho da Fixed Income — formulário à esquerda, a conta ABERTA em parcelas à
  direita (`entrypoint._calculadora`). **O resultado é sempre o do BANCO, e a
  direção é o SINAL dele**, nunca um campo digitado (§488). NDF: `Nocional ME ×
  (Fixing − Termo) × sinal`, IR de 0,005% só quando o banco PAGA — o piso de
  R$ 1,00 é do balde MENSAL e a tela DIZ que não o decide. Recompra: a MESMA
  fórmula do `unwinds.domain.conferir_apuracao` (feature não importa feature,
  então a conta está em dois lugares — o `check_tools_calculators.py` cobra a
  paridade nas TRÊS operações reais do §488); DU em branco é contado no ANBIMA,
  e o saldo são as três parcelas do Termo (`Zero` quando zera). Opção: payoff de
  quem é TITULAR, prêmio separado do exercício (liquidam em dias diferentes),
  vários preços = asiática (média aritmética); barreira e rebate NÃO são
  apurados. Fixing/paridade em branco buscam a PTAX de venda pela MESMA
  `_ptax_do_fixing` do Swap Calculator e dizem de que dia é; sem PTAX e sem
  número é erro em frase com o motivo. **O menu de Tools é em ORDEM ALFABÉTICA
  pelo rótulo em inglês** — item novo entra no lugar, não no fim.
- **Unwind NDF Calculator: os dias úteis aparecem NO CAMPO assim que as duas
  datas existem** (§516): na busca pelo B3 ID, na carga e a cada troca de data,
  contados pelo SERVIDOR no ANBIMA (`/api/tools/business-days`, a mesma
  `derivativos.dias_uteis_ate` do motor — o JS não conta dia útil, §509) e
  marcados como automáticos (`du_auto`, o esquema do fixing). Marcado, o
  Calculate RECONTA (não sobra o DU da data anterior); digitar apaga a marca e
  aí vale o digitado — é como se reproduz o DU do aviso do Athena. O prefill
  deixa o DU em branco DE PROPÓSITO: a data de liquidação é do formulário, e a
  posição não a conhece. Resposta de uma data antiga é descartada (contador de
  pedidos), senão duas trocas rápidas deixariam o número da primeira.
- **As três calculadoras têm Export — a memória de cálculo do swap, na MESMA
  lógica** (§515, `infra/memoria_derivativos.py`): fórmula encadeada até as
  entradas, com o VALOR gravado junto (o `_cache_das_formulas`/`_selar` do
  `memoria_xlsx`, reaproveitados — não reescritos), timbre do banco, parte
  devedora NOMEADA, nome `Memória de Cálculo <produto> - CETIP ID - contraparte -
  data` (`NDF`, `Recompra NDF`, `Opção`; o swap diz `Swap`).
  **Só as funções que o avaliador conhece** (as quatro operações, `^`,
  IF/AND/MAX/ABS/ROUND): a média da asiática é a SOMA explícita das células
  dividida pela contagem, não AVERAGE — função fora do avaliador sai com o cache
  errado e o Modo Protegido mostra o número errado. O `check_tools_calculators`
  cobra que o cache da planilha seja o número do MOTOR (nas três recompras reais
  inclusive). A rota é UMA (`/tools/<tool>/extract`, que a estática do swap
  vence), o botão é o mesmo `#tl-export` com `formaction` (o JS do swap já era
  genérico) e o `<form>` das três tem `action` EXPLÍCITO. **O prefill da opção
  traz a PARIDADE** (a PTAX, D-n pela `Data de fixing da moeda do ativo`), e o
  JS zera a procedência da busca anterior antes de escrever a nova. **No menu,
  as calculadoras vivem no grupo Tools › Calculators** (terceiro nível, como New
  Deals › Swap); cada nível é alfabético por conta própria.
- **Calculadoras de NDF e de opção: mercadoria COTADA EM CENTAVOS multiplica o
  preço do Quotes por 0,01** (§514, `_fator_de_centavos`): quem diz é o
  `Fator Conversao` = 0,01 do Index B3 (`Subjacente`), pela MESMA regra da casa
  do booking recap (`otc_boxparse._is_cents_factor` — só 0,01 é centavos, e a
  regra é do ATIVO, nunca da moeda). O registro na B3 é em UNIDADE de moeda (o
  strike do CTZ6 é 0,6960 US$/lb) e a bolsa cota em centavos (81,15 ¢/lb): sem
  o fator a opção saía CEM vezes dentro do dinheiro, e a conta fechava consigo
  mesma. A nota da tela DIZ que multiplicou. **O NDF Calculator cobre o termo de
  MERCADORIA** (a classe do ativo que a posição trouxe): o nocional é
  quantidade, o fixing é o PREÇO do ativo (do Quotes; média na asiática — série
  pela metade não é média) e a PARIDADE, que é a PTAX, leva a diferença a reais;
  ali o fixing em branco NÃO vira PTAX (seria a cotação da moeda no lugar do
  preço) — é erro dizendo de onde ele vem. **A moeda da posição vem por NOME**
  (`DOLAR DOS EUA`) ou código Sisbacen (`220`): quem traduz é o cadastro
  `currency-base` (`_moeda_iso`), e coluna vazia cai na `Moeda` do ativo no
  Index B3.
- **Option Calculator: a contraparte NÃO é o `Nome simplificado` da posição**
  (§513 — ele é apelido de conta: `JPMORGANBM`, `INTRAGLAWTONFDO`). Conta
  GUARDA-CHUVA (a 73760.10-2; quem diz é o `b3-accounts` pelo TIPO, nunca o
  número no código) → o cliente é o `CPF/CNPJ Cliente Contraparte`, que a tela
  já resolve pelo Reference Data; documento sem cadastro deixa o nome VAZIO
  avisando. Qualquer outra conta → o nome sai do Reference Data pela CONTA
  CETIP (`_lp_cpty_by_account`, que recusa guarda-chuva e conta com mais de um
  nome); sem cadastro fica o apelido, AVISANDO. **A comparação de conta é por
  DÍGITOS**: a posição de NDF escreve `73760.10-2` e a de opção `73760102`. E
  **a moeda do preço sai do `Strike/Limitador/Barreiras em Reais` (S/N)**: `S`
  = sem conversão; `N` = a moeda cotada, com a paridade levando a reais.
- **A taxa que a conta USOU volta para o CAMPO** (§512, NDF `fixing` e opção
  `paridade`): em branco o Calculate busca a PTAX e a escreve no campo da
  esquerda com a procedência embaixo, marcada como automática (`<campo>_auto`,
  hidden). **Enquanto a marca existe o Calculate REBUSCA** — senão trocar o
  vencimento deixaria a PTAX do vencimento anterior no campo, calada; digitar
  no campo apaga a marca (`input[data-tl-auto]` no `tools.js`) e aí vale o
  digitado. O prefill já traz a PTAX quando a data do fixing passou. **Data de
  fixing no FUTURO não tem PTAX**: o `ptax_moeda` anda para trás sozinho e
  devolveria a última cotação como se fosse a do fixing — é erro em frase.
- **As três calculadoras puxam a POSIÇÃO pelo B3 ID** (§511, o esquema do Swap
  Calculator; `partials/tools-position-lookup.html` + `/api/tools/<tool>/prefill`
  + o IIFE `[data-tl-prefill]` do `tools.js`). A fonte é o MESMO coletor da tela
  de Live Position (`_lpndf_collect`, `_lpopt_collect`) e a leitura é a MESMA da
  vertical de Unwinds, repetida em `tools/queries.py` porque feature não importa
  feature: **número de TELA** (`_num_tela`: o último separador manda, e três
  dígitos depois de um separador só são milhar — MENOS numa taxa, onde `5.374`
  é 5,374: `taxa=True`), **saldo = `Valor Base no registro − Valor Antecipado`**,
  e **na conta guarda-chuva o cliente é a coluna do CPF/CNPJ, nunca o titular**
  (`_b3_is_omnibus`; documento sem cadastro deixa o nome VAZIO avisando). O
  lado ilegível NÃO se chuta (o sinal depende dele). Na recompra a posição dá o
  contrato ORIGINAL e o nocional nasce com o saldo MARCADO como aproximação; as
  taxas do negócio ficam para a mesa. **Na opção os preços de verificação vêm
  do QUOTES** (`_fixings_do_quotes`): um na vanilla, a série `Média Asiática
  (data) N` na asiática, numa chamada só — câmbio pela PTAX de VENDA da moeda
  base, commodities pelo `quotes-commodity` (com o `"MY"`), o resto pelo
  `quotes-equity`; vale o Close do pregão ou o último antes dele. **Série pela
  metade não é média**: data futura ou sem preço deixa `fixings` SINALIZADO com
  a nota dizendo quantas faltam, e símbolo fora do cadastro diz qual cadastro.
  O `lado` da opção é o da PARTE do registro e vai marcado como aproximação.
  Notas e erros chegam por CÓDIGO + params (§486).
- **Swap Calculator: a data do fixing da taxa a termo conta no calendário do
  ÍNDICE, não no ANBIMA** (§509, `liquidacao.calendario_do_fixing`): Term SOFR =
  calendário SOFR do Holidays (*US Government Securities business days*),
  EURIBOR = TARGET2/BCE. O D-2 contava pelo ANBIMA em TRÊS lugares — o motor
  (que recebia o `cal` do formulário, que é o da contagem de dias do contrato),
  o pré-preenchimento e o JS da tela, que lia o `anbima.json` — e errava em todo
  feriado americano que não é brasileiro: fluxo começando na segunda 22/06/2026
  dava 18/06, quando a sexta 19/06 é Juneteenth e o certo é 17/06. A taxa que
  entrava era a do dia errado e a conta fechava consigo mesma. A tela não conta
  mais dia útil nenhum: pergunta ao servidor (`/api/tools/fixing-date`), e sem
  resposta deixa o campo como está. O SOFR COMPOSTO já usava o calendário SOFR.
  `check_tools.py` §9.
- **Swap Calculator, perna de EQUITY: o `Cupom Limpo` da posição pode ser um
  PERCENTUAL, e quem diz é a Denominação** (§507). `Preco in ativo - 100.00%
  Close 20-Sep-24` = o preço inicial é o FECHAMENTO do papel naquele pregão ×
  o cupom (`queries.aplicar_cupom_limpo`, `domain.preco_inicial_do_cupom`); a
  tela punha o `100.0000` no Initial price e a conta fechava consigo mesma. O
  interpretador lê `cupom_limpo` e `cupom_data` (`% Close`, `1.5 Close` = fator
  150%, `% Spot`, `Preco Inicial: x%`; meses em inglês e português), e a tela
  mostra o trio cupom · fechamento · preço lado a lado, replicando o terceiro
  no Initial price — que continua sendo o campo que o cálculo lê. **Só age
  quando a denominação declarou o cupom**: sem isso a perna segue com o Cupom
  Limpo como preço. Sem data (`Spot`) ou sem cotação, o Initial price fica em
  BRANCO e sinalizado, com o motivo (símbolo fora do `quotes-equity`, rede) —
  nunca o percentual no lugar do preço. E **o campo Rate multiplier só existe
  quando HÁ multiplicador (≠ 1)**: vazio em toda perna VCP, ele fazia a mesa
  procurar um num contrato que não tem. `check_tools_equity.py` §7.
- **Swap Calculator: o remanescente PODE ser maior que o original** (§478).
  Swap com atualização de notional (principal corrigido pelo índice ou por
  aditivo) carrega um saldo acima do valor registrado, e o motor recusava a
  conta como digitação errada. O original é só a base da parcela `Sobre Valor
  Base Original`; `amortizar()` limita a parcela ao saldo. Não reponha a trava.
- **Swap Calculator, perna IPCA: o fixing M-1/M-2 busca o número-índice
  FINAL no IBGE** (`precificador/ipca.py`, tabela 1737 variável 2266, §449):
  M-n contado da liquidação do fluxo. O INICIAL é do contrato (a cotação
  inicial da posição, ou o digitado) e só cai para o IBGE em branco — M-2 do
  início dava o mês errado. **Só o cupom é juros**: a correção fica no
  principal (`fator_correcao`, como o `fator_cambial`), é o que a planilha
  da mesa faz — **mas a correção que fica no principal é a do que CARREGA**:
  no fluxo que AMORTIZA, a parte do principal que sai hoje liquida CORRIGIDA
  (§471, `PontaLiquidada.amortizacao_devolvida` = `amortizado × fator_cambial ×
  fator_correcao`), e o bruto do fluxo intermediário é `(juros + devolvido)` de
  cada ponta. Em duas pontas nominais em reais os dois devolvidos são iguais e
  a parcela se cancela — foi por isso que ela pôde ficar fora da apuração desde
  sempre. Num DI × IPCA de VBR 254 mi amortizando 0,72% eram R$ 391,8 mil
  separando a tela da planilha; no VENCIMENTO nada muda, porque ali o valor de
  cada ponta já carrega o principal inteiro. Mês não publicado NÃO vem na série
  e é erro com o mês, nunca o anterior. A **taxa de amortização vai com CINCO
  casas** (§471, `'{:.5f}'` no `amortizacao_do_evento` + `pct5` no `tools.js`):
  ela multiplica o notional, e num original de R$ 282,8 mi a 5ª casa vale
  R$ 113 no amortizado — os dois lados andam juntos, porque o blur do `pct` de
  4 casas reescrevia o campo e é o campo que o cálculo lê (o defeito do §439,
  em outro campo). No pré-preenchimento, evento do DFLUXO sem Taxa Amortização é
  **0%**, não lacuna — e a **taxa contratada que a posição não traz também
  nasce 0%**, fora da lista do que "não deu para puxar" (§458, fora do CDI
  também): o motor já lia branco como 0,0, e sinalizar em vermelho pedia que
  se digitasse à mão o zero que a conta assumia.
- **Swap Calculator, perna SOFR: o spread SOMA à taxa composta, não
  multiplica o fator** (§469, `liquidacao.py`, o ramo do `SOFR`): "Compounded SOFR +
  spread" é a mesma figura do Term SOFR e da EURIBOR, que já faziam
  `capitalizar(índice + spread)` — só o SOFR multiplicava
  `fator_composto × (1+spread·τ)`, acrescentando o termo cruzado
  `sofr · spread · τ²`, que não existe em contrato nenhum. Não é
  arredondamento: no swap da SABESP (16/03 a 15/09/2026, US$ 17,5 mi a 3,66% +
  1,84%) ele sozinho valia **R$ 15,7 mil**, com a planilha da mesa e o sistema
  do banco de um lado e a tela do outro. O **CDI é o caso diferente e segue
  multiplicativo de propósito** (o percentual incide na taxa DIÁRIA e o spread
  é capitalização à parte, que é como a B3 apura) — `check_tools.py` §2 prende
  os dois lados. A **taxa composta do SOFR está certa e é conferível**: bate
  dígito a dígito com a razão do SOFR Index publicado pelo NY Fed
  (`compor_por_indice`), que é o teste a fazer quando alguém trouxer uma
  divergência de casa decimal — lookback, shift e arredondamento do fator
  diário mudam o número, e nenhum deles é "o certo" sem o contrato dizer.
- **A linha do `quotes.fetch_ohlc` vem FORMATADA para a tela** (`'{:,.6f}'`),
  não em número: quem a lê para calcular parseia (`_preco_da_celula`), nunca
  `float()` cru (§476). Acima de 999,99 entra a vírgula de MILHAR e o `float`
  levanta — e levantava para FORA do `swap_prefill` inteiro, com a tela dizendo
  "Could not read the swap position" numa perna de equity. Abaixo disso a mesma
  conta funcionava, e o defeito parecia ser "de alguns contratos".
- **Swap Calculator › Export: a memória de cálculo é FÓRMULA, não valor**
  (§455, `features/tools/infra/memoria_xlsx.py`): toda célula derivada do
  .xlsx é fórmula de Excel encadeada até as entradas, e os dias do índice vão
  inteiros numa aba por ponta (o fator do dia escrito sobre a taxa daquele
  dia, com o `ROUND(...,8)` do padrão B3/CETIP quando a tela o pede) — a aba
  principal REFERENCIA a célula do acumulado. **E fórmula vai com o VALOR
  gravado junto**: o openpyxl escreve o cache vazio (`<f>…</f><v></v>`), e
  quem abre sem recalcular — Modo de Exibição Protegido (todo arquivo baixado
  pelo navegador entra nele), painel de visualização, Excel Online, preview do
  anexo — mostra a célula EM BRANCO; era a memória inteira chegando sem um
  número, com os rótulos no lugar (o `fullCalcOnLoad` não alcança: ele manda
  recalcular na ABERTURA, e nenhum desses leitores calcula). O cache sai da
  PRÓPRIA fórmula, por um avaliador no módulo (`_cache_das_formulas`,
  injetado no zip pelo `_selar`) — escrito à mão seria a planilha afirmando um
  número que a fórmula não dá. **E o `<v>` vazio não tem grafia única** (§467): o
  openpyxl troca de serializador conforme o ambiente — com `lxml` (que NÃO está
  no requirements) o escritor incremental fecha a tag, `<v></v>`; sem ele o
  ElementTree serializa vazio como `<v />`. Casar com uma só devolve, na
  máquina que tem a outra, o arquivo EXATAMENTE como saía antes, sem um valor e
  sem erro nenhum — foi a correção passando na dev e não na instância. O teste
  que só gera e lê não vê isso (ele roda no ambiente de quem o chama): o guarda
  escreve as DUAS grafias à mão (§9b). Mexer na conta aqui sem mexer no
  motor entrega uma memória que não explica o número que a mesa mandou:
  `check_tools_memoria.py` recalcula a planilha e cobra o motor. **Memória de
  liquidação não tem valor FUTURO**: cada ponta fecha na linha do que ela
  liquida ali — juros no fluxo intermediário, valor da ponta no vencimento —,
  e há um diferencial só. O `<form>` da tela tem `action` EXPLÍCITO — o botão
  troca o destino por `formaction`, e sem ele o Calculate seguinte baixaria
  uma planilha; ele é `submit` de verdade (baixa sem JS) e o `tools.js` só
  intercepta para DESLIGAR o spinner, porque navegação que baixa arquivo não
  emite evento nenhum. O documento é do BANCO: timbre em A1, nada do sistema
  que o gerou (nem no `docProps/app.xml`), e nome `Memória de Cálculo <produto>
  - CETIP ID - contraparte - data` (`Swap`, `NDF`, `Recompra NDF`, `Opção` — é o
  que distingue os arquivos na pasta de quem baixou), com segmento vazio sumindo. Ele se lê como
  DOCUMENTO: valores à ESQUERDA, timbre ancorado com deslocamento em EMU
  (`add_image(img, 'A1')` cola no canto e esconde a imagem), e texto
  EXECUTIVO — sem linguagem de conversa nem de aula, com a parte devedora
  NOMEADA. O guarda varre o texto das abas e recusa as frases proibidas.
- **Intrag DCE NDF: o extrato são CINCO relatórios, não um** (§473): um por
  portfólio/carteira, em hosts diferentes, e o Import passa por todos numa
  clicada (`athena_api.registered_links`, plural, com a mesma precedência do
  singular e URL repetida entrando uma vez). **Relatório que falha não derruba
  os outros** — volta em `failed` com o motivo, e só quando NENHUM responde é
  erro. O `_api_link_rows` lê DB-first e **não passa pelo `_mapping_rows`**: o
  `upgrade` do cadastro não alcança quem importa, então linha nova no seed só
  chega à rotina depois de alguém salvar na tela `/mapping` — é por isso que
  cada rotina carrega o próprio fallback (o desta traz as cinco carteiras).
  Trade Date é a **12ª** coluna de dado (na Option é a 4ª) e o mapping casa por
  `NDF - TERMO`, não por `OPCAO`. **No filtro inteligente a coluna que comanda o
  fetch se acha pelo RÓTULO (`isDate`), nunca por índice fixo**, e o mapa de
  TIPOS é o dos rótulos da própria página: herdados do molde, o chip de data
  filtrava Participant Position (inclusive o chip padrão de hoje, que ABRE a
  tela) e toda coluna caía em `text`, perdendo datas e números.
- **Intrag DCE Swap: a unidade é o DEAL e a linha é traduzida no servidor**
  (§448). A planilha do dropzone traz duas tabelas (pernas e fluxos)
  ligadas pelo Deal Name; o arquivo `Intrag-DCE-Swap-AAAAMMDD.txt` é UMA
  linha por deal montada do par Pay + Rec (`domain._dce_swap_intrag_fields`,
  porte do script da mesa — o teste compara byte a byte). Send/preview
  leem o arquivo-dia, nunca as células da tela; deal sem Pay+Rec recusa o
  lote. Os `Fixed` do template `intrag-dce-swap` vencem o gerador.

### Unwinds (recompra) — Fase 1: NDF de moeda (§488)

- **As outras onze páginas de recompra são UMA tela e um CATÁLOGO**
  (`features/unwinds/catalog.py` + `pages/unwinds-product.html`, 21/09/2026):
  Swap CEM/EDG, NDF Commodities, Options FXO/Commodities/EDG, COE e os quatro
  DCE. Página nova é uma ENTRADA no catálogo (colunas `[campo, rótulo, tipo]`,
  layout da B3, rótulos do breadcrumb), nunca uma cópia do template — e o link
  do menu tem de existir, senão o `check_unwind_catalog.py` reprova (menu ×
  catálogo). A da Fase 1 segue com template PRÓPRIO: o guarda dela lê o
  `var UNW_COLS` do HTML. Os nomes de CAMPO do mesmo conceito são os da Fase 1
  (`Contract`, `UnwoundNotional`, `Result`, `Direction`…), porque é por eles
  que a Intrag, o Termo e a esteira leem a recompra; o que muda por produto é
  o RÓTULO — e por isso a chave de tradução da coluna sai do rótulo
  (`unw-col-original-quantity`), não do campo. **A chave da linha é o `_id`
  interno** (coluna escondida, a última): NDF/Opção de Commodities e FXO chegam
  sem identificador.
- **O backend das onze é UM, e o produto é parâmetro**
  (`features/unwinds/product/` + `infra/product_store.py`, §526): pasta
  (`dir`), posição (`position`: swap/option/ndf/None), conferências (`checks`)
  e layout da B3 saem da entrada do `catalog.py`; a API é a regra
  `/api/unwinds/<path:sub>` (que a estática da Fase 1 vence;
  `page_and_action` separa produto de um ou dois segmentos da ação). **Entra
  PLANILHA**, lida pelo conteúdo, com cabeçalho de rótulos OU campos da grade;
  **e-mail responde `unwind_email_format_pending`** — não há amostra do aviso
  destes produtos, e o parser da Fase 1 não se aplica. A posição (os MESMOS
  coletores do Live Position) só preenche o que a planilha deixou em BRANCO:
  divergência vira aviso e a planilha vence. **Sem B3 ID, casa por
  características só com candidato ÚNICO** (≥ 2 critérios, todos batendo);
  ambíguo não chuta. Chave natural = Contract (ou DealID) + UnwindDate;
  re-import volta a linha a `Imported` mantendo `_id`/Nº de controle, e linha
  `Sent` não se sobrescreve. Check de três estados (`balance`, `termo`,
  `premio`): OK só com TODAS rodando e fechando. Arquivo da B3 pelo motor do
  File Interpreter: TER 0014 (quantidade no 9, paridade no 14), SWAP 0014
  (**111** caracteres pela soma do template, não os 99 que o manual imprime;
  papel pela conta NOSSA; Mantém Prêmios só na parcial) e OPC 0014 (contas do
  REGISTRO, modalidade da posição). Asiático é RECUSADO (faltam as linhas tipo
  2). COE/DCE não têm layout: `unwind_no_b3_file`, e no Monitor fecham em
  `Imported`/`Approved`. **Ainda NÃO têm** Termo de Resilição, esteira, Intrag,
  Cockpit nem Settlement Summary — só a Fase 1 tem. `check_unwind_products.py`.
- **A ponte até o contrato é o `Código Identificador` do Live Position, e ele
  vem de DUAS formas**: TRUNCADO nos 14 da direita (o aviso traz
  `STP-XE-10G5U5X-0-0` e a posição, `XE-10G5U5X-0-0`) ou INTEIRO
  (`ATS-4T6-2W4YU86-0-0` nos dois lados). O casamento tenta a igualdade EXATA
  primeiro e só depois compara os 14 da direita dos DOIS lados — truncando só o
  lado do aviso, a posição que guarda o id inteiro nunca casava, e o import
  saía sem contrato e sem contraparte com a linha bem ali na tela ao lado. A
  exata vem antes porque a truncagem joga fora o prefixo, e dois ids diferentes
  podem terminar igual. O aviso NÃO se basta — moeda, lado da posição, contas
  e contraparte só existem na posição.
- **Numa conta GUARDA-CHUVA o `Nome da Contraparte` da posição NÃO é a
  contraparte** — é o titular da conta, que somos nós (`BANCO J.P. MORGAN
  S/A`, a CLIENT 1). Quem identifica o cliente é o `CPF/CNPJ da Contraparte`,
  e quem diz se a conta é guarda-chuva é o `b3-accounts` (`_b3_is_omnibus`,
  pelo TIPO): a resposta chega PRONTA ao `domain`, que é puro. A coluna do
  CPF/CNPJ carrega as duas coisas (o NOME quando o documento tem cadastro, o
  documento quando não tem): sem cadastro o nome fica VAZIO avisando, nunca
  cai no titular — afirmar o banco como cliente mandaria o Termo de Resilição
  para a pasta do banco com ele como Parte B. O par nome × CNPJ se fecha no
  `commands` pelo Reference Data. **O aviso da contraparte sai SEPARADO** dos
  outros (`aviso_contraparte`): o TER 0014 identifica as duas pontas pelas
  CONTAS, e misturado ele recusaria o arquivo por uma falta que não é dele.
- **As contas saem da POSIÇÃO, não de cadastro**: a recompra é de operação já
  registrada, e `Codigo da Parte`/`Codigo da Contraparte` estão na linha como
  foram para a B3. É o que resolve, sem escolher, a divergência entre o RefData
  (omnibus `73760.10-2` no nome do banco) e o `b3-accounts` (própria
  `73760.00-9`).
- **A direção é o SINAL do resultado, nunca o campo `Direction`**: na amostra
  fixa em reais o e-mail diz `PAY` numa recompra a RECEBER, e erra também
  `Future Value`, `Present Value` e `Calculated Termination Fee` — só o
  `Input Termination Fee` é confiável. E **o LADO da posição não é a
  direção**: o banco pode estar vendido e receber (era o campo 6 do TER saindo
  invertido).
- **Fixo em reais é `Notional CCY ∈ (BRR, BRL)`**: o `Unwound Amount` vem em
  reais e se divide pelo strike — na B3 o contrato é em moeda estrangeira.
  `BRL` entra junto para o dia em que o Athena mandar o ISO a regra não virar
  "não é fixo em reais", que é o caso que dá valor errado.
- **O veredito da conferência tem TRÊS estados** (fecha / não fecha / não dá
  para conferir): "passou por omissão" não existe.
- **O Novo Valor Base do Termo são TRÊS parcelas** (mesa, 18/09/2026): o
  nocional **ORIGINAL** (o do aviso), menos o que a posição já mostra como
  recomprado (`Valor Antecipado`), menos o recomprado agora. As três são
  COLUNAS da tela — corrigir a posição na grade tem de mudar o número do
  documento, e um saldo que só existe dentro do código não se confere. O
  `Total × Parcial` sai do MESMO número (Total é ele zerar, e aí a coluna diz
  **Zero** — não "Não Aplicável": o saldo é um valor, e "não se aplica" deixa o
  leitor sem saber se ele acabou ou se ninguém o calculou), senão o Termo diz
  encerrado com saldo aberto na coluna ao lado. Sem posição nenhuma a conta
  ainda sai, pelo original, presumindo zero — e DIZENDO que presumiu: o
  documento é assinado.
- **A esteira nasce e morre com a recompra.** Apagar a recompra tira a linha do
  Pending Confirmation e da esteira (`esteira_sem_a_recompra`) — sem isso ficava
  um card de Pending OTC de uma operação que não existe mais, com o Generate
  respondendo "nenhuma operação encontrada no arquivo-dia" para sempre. **Mas
  não por cima de carimbo**: linha com documento gerado, validação de qualquer
  mesa, callback ou envio ao cliente é REGISTRO, e aí o Delete RECUSA
  (`manual_conf.row_untouched`). Reimportar noutro dia move a `Data Operação`
  da linha INTOCADA para o arquivo-dia novo (`esteira_data_da_operacao`): o
  `_mc_save_from_deal` nunca sobrescreve linha existente — de propósito —, e
  sem isso a linha seguia apontando para o dia em que a recompra não está mais.
- **No card do Monitor o Termo diz o produto RECOMPRADO**
  (`manual_conf.confirmation_label`, `TERMO DE RESILICAO NDF FX`): o TIPO é um
  só para termo, opção e swap, e na fila três cards com o mesmo nome não dizem
  qual operação cada um distrata. É rótulo de TELA — pasta, cadastro de
  validação e Confirmation Type continuam no `confirmation_type`.
- **O Termo também gera o XML do FepWeb** (mesa, 18/09/2026), ao lado do `.doc`
  e do `.pdf` e com o mesmo nome base, como toda confirmação da casa. `valor` é
  o liquidado em **reais** e `valorEstrangeiro` é ele dividido pela **taxa da
  recompra** — não pelo strike do registro, que é o que nomeia o Valor Base
  Liquidado do Anexo I: os dois números do XML falam da liquidação, os do Anexo
  falam do contrato. `tipoOperacao` é `NDF` (a operação resilida é um termo de
  moeda) e **`tipoEvento` é `RE`, de resilição** (mesa, 22/09/2026; era `R`) — com o `N` de novo o FepWeb
  cadastraria o distrato como operação nova.
- **Campo 13 do TER 0014 é PERCENTUAL ao ano** (13,75 → `1375000000`);
  **campo 14** é `1` com a taxa termo em BRL e a paridade USD/BRL fora dela —
  branco ali não é neutro. **Campo 9** é o valor RECOMPRADO em moeda
  estrangeira, nunca o nocional original (o mesmo contrato antecipa mais de
  uma vez, e o `Valor Antecipado` da posição é a soma deste campo).
- **A visão do arquivo sai do `b3-accounts`** (`_b3_account_le` pela conta do
  campo 5), nunca de um de-para no código; conta fora do cadastro RECUSA.
- **O arquivo-dia fica em `cache/unwinds/`, FORA de `cache/new deals/`**: o
  Monitor varre aquela árvore e criaria um card `extra-` sozinho (§454). O
  caminho é `data_paths.unwinds_cache_root()` e não se escreve à mão em lugar
  nenhum: a recompra grava por ele e o Monitor varre por ele (§491).
- **Ela TEM card no Monitor** (`unwind-ndf-fx`, coluna B3 Registration, grupo
  NDF): a chave não leva prefixo `intrag-` porque a recompra é registro na B3,
  o card declara `done: ('Sent',)` — é onde ela fecha —, e não declara `les`,
  porque a entidade sai da CONTA e quem a traduz é cadastro (§491).
- **A rota da página é PRÓPRIA** (`/unwinds/ndf/fx`, três segmentos): o
  catch-all só atende `/<template>`.
- **O dropzone lê `.msg`, `.eml` e o corpo solto, pelo CONTEÚDO**
  (`infra/email_file.py` — magic do CFB, cabeçalhos MIME), não pela extensão:
  o Outlook renomeia anexo e um `.msg` chega como `.txt` sem aviso. O assunto
  sai do arquivo quando ele o carrega; só o corpo solto cai para o nome.
- **Os botões da linha são os QUATRO da casa** (§7): Confirm, Edit, Delete,
  Send. O preview do arquivo da B3 é o **duplo clique** na linha e o Termo de
  Resilição se gera no **Confirmations Monitor** — um olho e um documento na
  coluna Actions eram dois caminhos a mais para onde já se chega. A **edição
  segue o 4-olhos das páginas de Intrag**: salvar põe a linha em `Pending` e
  marca o maker, `Approved` é outro usuário conferindo (o próprio é 403), e
  **`Pending` não é enviável** — `STATUS_ENVIAVEL` é `Imported` (veio da
  máquina, intocada) e `Approved` (mexida e conferida). O `Status` e o `Check`
  ficam fora dos campos editáveis: um é estado da esteira, o outro é veredito
  apurado.
- **O `Status` é a PRIMEIRA coluna de dado**, logo depois das Actions: em
  dezoito colunas, no fim da grade a resposta "esta linha já foi?" só aparece
  depois de rolar a tabela inteira.
- **O gatilho de tudo que vem depois é o IMPORT**, não o Send (mesa,
  18/09/2026, invertendo a decisão de dois dias antes): Pending Confirmation,
  esteira (Track + Monitor), NDF Cockpit e o Settlement Summary recebem a
  recompra assim que ela chega. A recompra é **elegível** para o documento
  desde aí (`confirmation_deal` devolve `Success`), e o que se paga é que uma
  recompra corrigida ou apagada depois já deixou linha — a correção é
  reimportar (o upsert refaz pela mesma chave). **A Intrag continua no SEND**:
  ali a linha é INSTRUÇÃO ao custodiante, não cobrança de documento.
- **A recompra é PROJETADA no arquivo-dia do NDF Cockpit** da sua data de
  LIQUIDAÇÃO, marcada com `_nc_unwind` e chaveada por `UNW-<athena id>`. Duas
  coisas seguram isso: o import do Cockpit **preserva** essas linhas
  (`_ndfc_keep_unwinds`) — ele monta o dia inteiro a partir da API, onde a
  recompra não existe, e sem isso o próximo Run a apagaria sem erro nenhum —,
  e o **Summary as IGNORA** (`unw_ids` no `_ndfsum_collect`), porque continua
  lendo a recompra da vertical, que é quem sabe que não há resgate da B3 para
  conferir. Lidas dos dois lados, o mesmo caixa sairia DUAS vezes no Trade
  Level e no IR do dia — o ledger monta o dia inteiro de uma vez (§423).
- **A projeção RECALCULA o IR do DIA INTEIRO** (`_ndfc_reapply_ir`, §501):
  quem escreve o `VL_TAX_INCOME` é o `_ndfc_apply_ir`, e ele só rodava DENTRO do
  import da API — a recompra chegava à tela em que a mesa acompanha o acúmulo
  do imposto com a célula vazia, e o IR das OUTRAS linhas da mesma contraparte
  ficava velho, porque o piso de R$ 1,00 é do balde do MÊS e a recompra passou a
  somar nele. É a MESMA função do Run (uma segunda implementação divergiria no
  primeiro caso de borda), roda **FORA do `_cache_lock`** (a cura do ledger trava
  por dentro, §432) e casa as linhas pelo `_nc_id`. **E a projeção acompanha a
  vertical**: Delete e mudança da data de liquidação tiram a linha do dia antigo
  — o `_ndfc_keep_unwinds` a preserva do Run, então sem isso ela ficaria lá para
  sempre, com o caixa fantasma no Trade Level e no IR do dia.
- **A recompra se DIZ recompra na tela**: a marca `Unwind` na coluna Status do
  Cockpit e do Trade Level do Summary — a coluna Status porque é a primeira que
  se lê e porque o filtro dela passa a achar as recompras do dia pelo nome. Ela
  viaja na QUINTA posição da cauda de meta, depois do `_nc_id`, e a cauda é
  ADITIVA (quem a lê conta do começo, `len(_NDFC_COLUMNS) + n`). Pela mesma
  marca a recompra sai do `_opb3_internal_ter_map`: ela carrega o MESMO contrato
  da original e não tem resgate da B3 para bater — somada ali, mudaria o lado JP
  de um contrato que a B3 informa sozinha.
- **O trilho de validação do Termo é SÓ OTC** (mesa, 18/09/2026): o distrato
  não reabre economia nenhuma, e o que o MO e o FO conferem é a economia da
  operação, que já passou por eles quando ela nasceu. É `VALIDATION_SEED`, e
  seed não alcança quem já tem o cadastro (§6) — quem conserta a instância é o
  `validation_upgrade`, e só a linha que ainda está EXATAMENTE como o seed
  antigo a deixou: mesa que editou decidiu, e decisão da mesa não se desfaz
  num upgrade.
- **O Termo de Resilição é arquivado na pasta da CONTRAPARTE**, pelo mesmo
  caminho das confirmações de New Deals
  (`<Cliente>\Confirmations\AAAA\mm. Month\dd\<pasta do TIPO>`, via
  `_ei_resolve_client_dir`). **Sem contraparte o Save RECUSA**: o acrônimo caía
  num literal `'UNWIND'` e o `create=True` fazia nascer uma pasta com esse nome
  no Electronic Inventory, ao lado das contrapartes de verdade — o documento
  ficava salvo, a tela não acusava nada, e ele não estava onde a mesa procura.
- **Toda ação da página toca o sino** (Import, Box Scan, Edit, Confirm, Delete,
  Send, Termo salvo), porque o arquivo-dia é da mesa inteira. A exceção é o
  `dry_run` do Import: ali nada foi gravado, é a pergunta das duplicatas.
- **A varredura roda sozinha a cada 30 min**, em laço PRÓPRIO da vertical
  (`unwinds/commands.scheduler_loop`, registrado no `routes.py` como
  `unwind-boxscan`) e não dentro do `features/boxscan`: **feature não importa
  feature** nesta casa — nenhuma das 49 importa, e é o `check_soc_layers` que
  segura. O que as duas compartilham é o INTERVALO, a mesma
  `BOX_SCAN_POLL_MIN`, para a mesa ter um botão só. A tela sempre prometeu os
  30 minutos; até 18/09/2026 não havia laço nenhum registrado, e a recompra só
  entrava no clique do Import. **Varredura vazia não toca o sino** (a caixa
  está vazia quase sempre; um aviso a cada 30 min é o fim do sino), e e-mail
  que o parser recusou vai para o log em WARNING mesmo sem linha nenhuma — ele
  ficou no box.
- **A varredura é no INBOX, o mesmo por onde entra o booking recap de NDF Comm
  e Opt Comm** (`scan_unwind_box` chama o `_connect_inbox` do
  `scan_new_deals_box`): o aviso do Athena chega na caixa de entrada, não na
  subpasta das liquidações, que era onde a primeira versão o procurava — ali
  ele voltava "nenhum e-mail", calado. **O ARQUIVAMENTO não acompanhou**: o
  e-mail importado vai para a `Unwind` das liquidações
  (`OTC_UNWIND_ARCHIVE_FOLDER`), que é o que separa o que já entrou do que
  falta. `OTC_UNWIND_SOURCE_FOLDER` preenchida volta a varrer uma subpasta —
  e **tupla vazia não se passa ao `resolve_folder`**: ele devolveria a RAIZ da
  caixa, que não tem mensagem nenhuma.
- **O box scan procura a pasta na RAIZ da caixa e depois no Inbox**
  (`resolve_folder`), dizendo no log por onde achou; a árvore do Outlook não
  distingue os dois níveis, e presumir um deles arquiva o e-mail numa pasta
  nova e vazia com o nome da certa. A caixa é a `brazil.otc.ops` — a
  `brazil_otc_settlements` está DENTRO dela.

### Dashboard (o painel do `index.html`)

- **Quem CONTA como deal é quem tem identificador — `Deal`, `B3ID` ou `_id`**
  (§489). O teste era só pelo `Deal`, e o Swap Bullet nasce com ele em BRANCO
  (§480): o produto inteiro era invisível, com `Swap Deals = 0` e as operações
  na tela ao lado.
- **`_is_bank` é o `_jpm_re`, NUNCA `'banco' in cl`** (§489, o mesmo engano que
  o `_ops_is_internal_cpty` já documenta): a regra crua derrubava BANCO SAFRA,
  BRADESCO e SANTANDER — clientes de verdade, em todos os produtos. E a grafia
  real é `BANCO J.P. MORGAN S/A`, com ponto depois do P, que não casa com
  `'j.p morgan'`: era por isso que o `'banco'` solto tinha virado o único que
  pegava a perna do banco.
- **Os QUATRO cards de produto somam o Total** (NDF, Options, Swap, Unwinds) —
  é como a mesa confere a tela.
- **O `?v=` do `dashboard.js` sobe quando ele muda**: é a mesma disciplina do
  CSS (§7), e sem ela o navegador da mesa serve o arquivo antigo e o número
  novo nasce em branco.

### Live Position (cinco telas, um JS)

- `live-position-swap-characteristics.js` serve cinco páginas por `data-api`;
  contrato: ids `swapchar-page`/`swapchar-table` — renomear deixa a página em
  branco. Acréscimos são aditivos/opt-in.
- **Do `Código Identificador` para a direita, o Swap Characteristics mostra o
  arquivo INTEIRO** (§472): a tela parava na coluna 146 e a posição tem 170. A
  cauda do `_SWAPCHAR_LABELS` SAI do `_B3_SWAP_HEADERS` — os 146 primeiros já
  eram idênticos, e duas listas para a mesma leitura POSICIONAL desalinham sem
  erro nenhum. **`Data de Fixing IPCA` se chama Data e não é data**: traz `1`/`2`
  (a defasagem M-1/M-2, §449) e tem tipo próprio (`ipca_fix`) — pelo nome cairia
  no `_fcst_parse_date`. É de lá que o Swap Calculator pré-preenche o fixing da
  perna de IPCA **direto** (no VCP quem responde é o `Nome Tipo/Classe`); sem
  resposta a lacuna é SINALIZADA, nunca M-1 presumido.
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

- **Settlement Type (Trade Level do Other Products e do NDF Summary, à direita
  da Counterparty; mesa, 21/09/2026) sai da DATA NA POSIÇÃO — a MESMA leitura
  dos cards do topo** (`_ops_settlement_counts`), em MAIÚSCULAS
  (`_ops_settle_type_dates`/`_ops_settle_type_join`): opção que vence hoje é
  `EXERCISE` e a de `Data de Liquidação do Prêmio` hoje é `PREMIUM`; termo que
  vence é `MATURITY`; swap na agenda de prêmios do dia é `PREMIUM`, o que VENCE
  hoje na posição é `MATURITY` e o que tem evento no DFLUXO sem vencer é
  `CASHFLOW` (`_ops_swap_event_contracts`, os mesmos arquivos e a mesma coluna de
  data do `_FORECAST_SOURCES`). **A primeira versão perguntava só ao EVENTO da
  B3 e saiu VAZIA na instância em tudo que não era swap de equity**: o evento
  chega depois, e onde o Tipo Título não tem Consider próprio ele entra na
  liquidação sem regra nenhuma para dizer o tipo (§6, `opb3-events`) — nada
  quebra, a coluna só não diz. O evento virou o PLANO B e a fonte do que data
  nenhuma diz: a coluna `SETTLEMENT TYPE` do `opb3-events` (domínio fechado;
  `_opb3_settle_type`, a regra mais específica vence) é onde a mesa cadastra a
  antecipação como `Unwind`. Sem data e sem evento a célula fica VAZIA. **A
  recompra de NDF é `UNWIND` pela vertical**, e **no NDF Summary a linha do
  Cockpit sem evento é `MATURITY`, sempre** (o universo dela é o
  `getTradesBySettle`; condicionar ao `venc` da posição deixava o tipo vazio
  justamente nas linhas em `Check`, cujo resgate não casou). As linhas dos
  avisos de termo e de opção carregam `settle_type` — é o que a geração dos
  avisos vai ler. No NDF Summary as `cells` são posicionais: o TAX virou
  `_NDFSUM_TAX_CELL`.
- **`_ops_trade_rows(settle_ref)` é o único lugar que sabe quais famílias
  existem** (SWAP + NDF Commodities); página, cards e e-mail de TED chamam
  ele. Status do aviso vive no overlay `other-products-summary_YYYYMMDD.json`
  por contraparte × LOB × produto. Linha que neta zero diz `0.00` no Receive.
  Trade Level ordena Product → LOB → Counterparty (`check_ops_trade_swap.py`).
- **Equity é SWAP na B3; o outro lado vem do elo** `_ops_equity_link`
  (Operations B3 → Latam → OTM), Type trocado pelo subjacente por cadeia; o
  mesmo elo é o plano B da opção de equity (`_optadv_collect`, chave Título
  MAIÚSCULO, resolvido uma vez por linha).
- **As três colunas de valor do Settlement Advice de swap saem do OTM
  Settlements; o Swap Athena é o PLANO B** (§468, `_ops_otm_por_trade`, na
  platform):
  o OTM é o arquivo do fluxo de caixa que de fato liquida, e é dele que o Trade
  Level já tirava o seu Settlement — enquanto o aviso lia as curvas do Athena, a
  MESMA operação no MESMO dia saía com um número na tela e outro no documento
  que vai ao cliente. A ponte até a linha do OTM é o **`Kapital ID` do Athena,
  que é o `Trade Id` de lá**, e em equity o `internal_id` do elo Latam → OTM
  (o Swap Athena é só de CEM). A regra do SINAL é a mesma dos outros dois
  lugares que leem arquivo de fluxo (o elo de equity e o Kapital Hybrids):
  Curva Banco = Σ positivos, Curva Cliente = Σ negativos, Resultado Bruto = a
  soma. **A escolha da fonte é da LINHA INTEIRA, nunca coluna a coluna** — é o
  que garante `Curva Banco + Curva Cliente = Resultado Bruto` no papel, que é o
  primeiro lugar onde o cliente olha. Trade sem NENHUM `Amount` legível não
  entra no índice: a ausência tem de poder ser distinguida do zero.
  `check_ops_trade_equity.py` §6 prende os dois lados (OTM e o plano B) e a
  soma de cada linha.
- **Swap VCP: o fator da perna VCP é `(juros + diff B3 da OUTRA perna) ÷
  VBR + 1`, na 8ª casa** (§452, `other_products/domain.py`): juros = |curva
  do OTM pelo Athena ID| − notional amortizado (VBR × % do DFLUXO do dia,
  base pelo tipo — a regra do Swap Calculator, agora em
  `platform/swap_flows.py`); a diff é `Valor Juros` da B3 (Swap Eventos,
  lido CRU — a coleta de exibição arredonda) − juros JP na perna calculada.
  **Só a perna VCP tem fator** (a calculada sai "-"). O arquivo é o do
  Accrual (`platform/pu_fator.py`) com nome PRÓPRIO: `VCP_CLIENT.TXT`
  contra cliente e `VCP_<VISÃO>.TXT` no intragrupo — e intragrupo é visão
  da contraparte DIFERENTE da parte (`is_intragroup`), não "conta do
  grupo": o omnibus 73760.10-2 é do Banco e ali o swap é de cliente. Valor
  que não resolve é `None`, nunca zero.
- **NÃO amortizar tem duas formas, e cada uma tem a SUA base** (§456/§458,
  `platform/swap_flows.base_da_amortizacao`): `Na Data de Vencimento` → **At
  Maturity** (o principal volta no encerramento) e `Sem Troca de Amortização`
  → **Sem Troca** (`liquidacao.SEM_TROCA`, o notional nunca amortiza). As
  outras duas bases descrevem uma PARCELA, e escolher qualquer base errada
  faz a tela AFIRMAR um cronograma que o contrato não tem — era o Swap
  Calculator abrindo como "parcela constante sobre o original" um swap
  marcado `Sem Troca` no Live Position, e depois como devolução no
  vencimento. Número nenhum muda (`amortiza_no_fluxo` já zera o percentual
  nos dois casos); o que muda é o que a tela diz. No `Sem Troca` a BASE vence
  o percentual — `amortizar()` devolve zero ANTES de olhar para ele, senão um
  `100` esquecido no campo devolveria o principal inteiro num swap que não
  devolve nada. A mesma função responde ao fator VCP.
- **Swap VCP: BULLET no vencimento amortiza 100%** (§470,
  `other_products/domain.calcular`): `Na Data de Vencimento` responde "neste
  FLUXO não amortiza" (`amortiza_no_fluxo`) — regra certa, escrita para os
  fluxos INTERMEDIÁRIOS de um cashflow. No bullet não há intermediário: o único
  fluxo é o vencimento, e com 0% o `juros = |curva| − 0` carrega o PRINCIPAL
  junto com os juros. O fator sai com um **1,0 inteiro a mais** (VBR 9,8 mi com
  curva de 13,5 mi virava 2,369 em vez de 1,369) e o `VCP_*.TXT` manda a B3
  liquidar o dobro. Quem diz que o contrato é bullet é a POSIÇÃO (`Tipo de
  Contrato`, `02` = bullet e `01` = cashflow — o mesmo código que o Swap
  Characteristics traduz na coluna), e quem diz que hoje é o vencimento é a
  `Data Vencimento` dela; as duas chegam ao `domain` RESPONDIDAS, porque ele é
  puro. A base é **At Maturity**, que calcula sobre o SALDO — num contrato que
  já amortizou antes, o original é maior e a conta pelo original só não erra
  pelo `min`. Tipo de Contrato que não responde é LACUNA, nunca "cashflow", e
  num bullet o **Tipo Amortização sai como `Na Data de Vencimento`** quando o
  arquivo deixa a célula vazia — ele DIZ por que a amortização é de 100%.
  **E perna SEM fluxo no dia não amortizou nada** (§470, segunda rodada):
  `juros()` devolve `None`, nunca `−amortizado`. O `amortizado` sai das DUAS
  pernas, o que é certo num cashflow; na perna sem curva ele dava `−principal`,
  e como a `diff_b3` é `B3 menos o nosso`, o principal voltava SOMADO ao fator
  da perna VCP — os 100% entravam por uma porta e saíam pela outra, e o fator
  ficava idêntico ao de antes. **E a prova real compara CAIXA BRUTO**: cada
  perna entra como `juros + amortizado`, e a perna sem fluxo entra como ZERO —
  a mesma leitura que o `interno` faz do OTM. Montar só os juros funcionava no
  cashflow porque as duas pernas amortizam a mesma parcela e o principal se
  cancela; no bullet só uma amortiza, o principal sobrava e a linha ficava sem
  veredito.
- **No Swap VCP a `Diferença` É o veredito** (§459): o valor sai DENTRO do
  badge (verde/amarelo), como o batimento do Accrual Swap colore o fator
  registrado — não há badge de texto ao lado. Sem veredito não há cor.
- **Email Validation (Swap VCP e NDF Other Publisher): quem decide o cenário é
  a CONTA, nunca o nome** (§487, `platform/email_validation.py`). Contra
  cliente (guarda-chuva `CLIENT 1/2` do `b3-accounts`) só o Banco lança e não
  há o que casar; contra INSTITUIÇÃO FINANCEIRA (conta própria de terceiro) o
  lançamento é de duplo comando e outro integrante do time confere o fator/a
  taxa — sai só a tabela (`if`); com **Lawton/Atacama numa das pontas**
  (`if_fund`) sai a tabela MAIS o arquivo da visão do fundo, porque quem
  valida é quem insere essa ponta na B3. O anexo é montado **em memória pelo
  MESMO gerador do Send** (`pu_fator` / `_ndfop_conecta_fields(swap=True)`) e
  **nada vai para o Batch Conecta nem muda status**: pedir validação não é
  enviar. A conta é normalizada para os OITO dígitos antes da pergunta — o
  Live Position de NDF entrega a do Lawton como `41007`, que não casa com o
  `00041.00-7` do cadastro nem com o prefixo `00041`, e a linha do fundo
  passava por IF comum, sem o anexo e sem erro. Conta em branco NÃO é IF. O
  Other Publisher só sabe espelhar o Lawton: outro fundo vai sem anexo e volta
  em `warnings` (`fund_without_file`). Sai de `otc.tracker@jpmorgan.com` para
  `brazil.otc.ops@jpmorgan.com`, sem Cc. `check_email_validation.py`.
- **Perna interna não gera aviso** (`_ops_is_internal_cpty` pelo `le-spn` +
  `_pc_is_internal_counterparty`, nunca "começa com BANCO"): fica no Trade
  Level e no Summary, sai do Advice e do TED — o e-mail de TED do NDF faz a
  mesma pergunta por SPN (§451); entidade nossa fora do `le-spn`/INTERNAL
  ainda passa, e se corrige no cadastro. **A SSI anexada ao TED é
  procurada em TODAS as pastas gêmeas do Electronic Inventory**
  (`_ei_client_dir_names`): olhar só a vencedora do scan dizia "não
  localizada" com o arquivo salvo na outra.
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
- **No Cockpit, `VL_FORWARD_RATE` é a forward do trade date e
  `VL_STRIKE_PRICE` é o FIXING** (é o que a Trade Level chama de FORWARD RATE
  e FIXING RATE; o `_ndfc_strike_calc` deriva o fixing do forward). Na API o
  `Strike` é a forward e o `Spot` do evento é o fixing — o §421 tinha cruzado
  os dois pelo nome. O Fixing do aviso é o Spot da API guardado em
  `_nc_fixing` na importação (`_ndfsum_fixing`); sem ele, a célula FIXING
  RATE; nunca a forward (§438).

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
- **A grade do Track EDITA, não cria** (§546): chave ausente é 404 e só o Add
  Row cria linha, mandando `_new`. O `find_row` lê em modo `strict`, e uma
  leitura que falha LEVANTA. Lida como "não existe", a edição em massa trocava
  a operação por uma CASCA (Trade ID + Callback Date) e o `upsert_row` apagava
  a verdadeira. Casca já gravada se refaz com
  `backfill_manual_confirmations.py --repair`.
- **Gravação na esteira é `mutate_row`/`save_changes`, nunca `find_row` +
  `upsert_row` da linha inteira** (§548): cada mesa roda a própria instância, e
  a segunda assinatura apagava a primeira. MO/FO não assinam antes do OTC
  (409 `StageNotPending`); Delete é do OTC e recusa linha carimbada.
- **Preencher a coluna de validação pela grade do Track é validar** (mesmas
  regras do `mark_validated`; a transição é vazio → data; lote tudo-ou-nada).
- **"Não há PDF na pasta" tem TRÊS estados** (§502, a regra do §486): há PDF ·
  olhei e não há · NÃO DEU para olhar. O `/api/manual-confirmation/docs` responde
  `null` no item que levantou (guarda por item: um não derruba os outros) e a
  tela tem frase própria nas três línguas, deixando o botão como está — o `catch`
  do lote inteiro escrevia a frase do caso VERIFICADO e oferecia Validate ao
  lado, e foi assim que se abriu a validação de um documento que ninguém gerou.
  Status de erro não passa mais por resposta boa (o 503 de banco ocupado e o 500
  com o motivo são JSON). E o lote vai **FATIADO, oito por vez EM SÉRIE**: a
  primeira fatia aquece a varredura da raiz e uma fatia que falha leva só os oito
  dela — em paralelo seriam seis idas simultâneas ao share.
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
- **O intervalo do Advanced Export daqui é por COLUNA de data, não por
  arquivo-dia** (mesa, 22/09/2026; `/api/pending-confirmation/range` + o modo
  `range` do `export-advanced.js`, que EXCLUI o `daily`): um combobox escolhe
  `Trade Date` (o padrão) ou `Maturity Date`, e a busca vai aos **três** bancos
  numa requisição só. A operação daqui não vive num dia — ela anda entre
  `pending`, `ok` e `backlog` conforme o status resolve e o prazo vira —, e as
  fotos das 11:30 respondiam outra pergunta: a FILA de cada dia, com a mesma
  operação repetida em todas as fotos em que ainda estava pendente e em nenhuma
  se já estivesse resolvida antes da primeira. Sem Reference Date (não há
  arquivo a carimbar), deduplicado por Trade Number (a linha fica nos dois
  bancos até a manutenção reencaminhá-la), coluna por LISTA BRANCA (o nome vem
  do navegador), linha sem a data pedida fora e CONTADA, e leitura `strict` —
  banco ilegível responde com o motivo, porque planilha curta não se distingue
  de intervalo sem movimento. `check_pc_export_range.py`.
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
- **Pay/Rec: o NDF do lado JPM é a liquidação do dia como o Cockpit a monta**
  (§538, `routes._ndfc_liquidacao_do_dia`): a API `getTradesBySettle` mais as
  RECOMPRAS que ela ainda não traz (decidido pelo DEAL,
  `_ndfc_unwinds_fora_da_api`, a mesma regra do import do Cockpit), com o IR
  calculado, **sem regravar o dia do Cockpit**. **Dia já importado no Cockpit
  (carimbo `.meta.json`, NÃO o arquivo-dia, que a projeção da recompra cria)
  é lido de lá sem chamar a API** (§541): o `getTradesBySettle` segurava o Run
  por minutos. O `settlement.csv` da pasta é
  IGNORADO (dobraria o NDF). A conta é a dele: `SETTLEMENT + TAX` por cliente
  × LE, e LEGAL fora do JPM fica de fora (`_jpm_cockpit`). API fora do ar PARA
  o Run (`ndf_source_failed`): sem NDF, toda perna de cliente vira pendência.
- **Pay/Rec**: `SPB - outros bancos` casa só com BANCO (`_match_allowed`, pelo
  `bank-name`, por PALAVRA nunca substring, `banco` é token significativo,
  direção entra pela mesma porta, vale nos três estágios; fora do cadastro
  responde NÃO). Só linha `Sucesso` entra (`check_spb_status.py`).
  **O `_cli_spb` tem TRÊS portas de entrada, e a terceira exige o código E o
  prefixo JUNTOS** (§525): `STR0007` na coluna de código **mais** `STS - ` no
  começo da descrição, de onde sai a contraparte. Cada um sozinho criaria perna
  de cliente SEM DINHEIRO atrás — que ou casa com uma perna JPM legítima,
  escondendo uma quebra de verdade, ou vira pendência fantasma. O prefixo é
  ANCORADO (o hífen DENTRO do nome sobrevive, que um `split('-')` comeria), a
  linha NÃO sai como `bank` (tem contraparte e casa por NOME; marcada como
  banco cairia na tolerância de R$ 20 do interbancário) e descrição sem
  contraparte fica de fora **DIZENDO o motivo no log** — o que some calado é o
  que ninguém conserta, e foi assim que este defeito durou. Duas suposições
  estão escritas no código para o dia em que forem falsas: direção `Pay` fixa e
  produto `NDF` (nenhum dos dois entra no casamento).
- **CGD**: lê o D-1 do arquivo que o Save CETIP Files GRAVA (`CETIP_DEST_ROOT`),
  a lista do FEP vem do ANEXO do e-mail mais recente do box
  (`baixar_fep_do_box`; `path` vence; sem Outlook cai para `CGD_INPUT_ROOT`
  avisando); contas nossas do `b3-accounts`; CNPJ por dígito; cache gravado
  com a data da POSIÇÃO.
- **Conf. Matching** (FepWeb × Athena, §486) faz UMA pergunta: a confirmação
  das operações de ontem foi gerada no FepWeb? **Nos dois lados é `Ok`, sempre
  — ela NÃO conversa com o Pending Confirmation** (sem prazo, sem Pending
  Status: a primeira versão classificava a assinatura e uma operação que ESTAVA
  no FepWeb saía `Pending`). Só na Athena é `Missing FepWeb`, **salvo
  `SIGNATURE TYPE = Internal`**, que é `Ok`: a confirmação não é gerada. A
  regra é uma função (`_status`), reaplicada no dia já gravado. O FepWeb é o
  ANEXO do e-mail `(REPORT) FEPWeb - Operacoes D-4`, lido pela MESMA
  `baixar_fep_do_box` da CGD (`assunto` + `aceita` + `extensoes`), e **não há
  plano B em pasta**: sem o e-mail o Run LEVANTA, com os avisos do box em
  `reasons`. **O anexo é `.xls`, e `.xls` é só o nome** (lê-se pelo conteúdo,
  `_latam_read_rows`; a CGD segue só `.xlsx`); o relatório de um dia chega na
  NOITE dele, então a janela do `aceita` começa no próprio dia; **a `Data
  Operação` é BRASILEIRA (`dd/mm/aaaa`) desde 18/09/2026** — o relatório vinha
  americano e MUDOU, e o `fep_date` nunca cai para o outro formato (as duas
  leituras dão dias diferentes na mesma célula e só dia > 12 denuncia a troca).
  Linha que só faz sentido em `mm/dd` fica de FORA avisando
  (`fep_date_mmdd`), em vez de virar "outra data": o formato velho de volta
  esvaziaria o batimento sem erro nenhum. Athena é a
  API de NDF do New Deals. Cliente por CHAVE (CNPJ sem zero à esquerda × SPN);
  internas saem de CADASTRO (`interbook-ndf`, `le-accronym`, `ECONOMIC
  GROUP`), nunca das listas do workflow. Comentário é do trade e não muda o
  Status. Linha chaveada pelo RÓTULO + `columns` no payload (o contrato do
  Advanced Export por intervalo).

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
- **O `Status` é `select` de TRÊS opções** (§520, `STATUS_OPTIONS`):
  `Cancelled` está lá porque é um dos QUATRO cards do Track Docs (`OUTCOMES`) —
  fora da lista ninguém cancela um CGD pelo app. A grafia é a de TÍTULO (a da
  lista e a que o `stamp_mo` grava), NÃO derivada do `ACTIVE_STATUS`, que é o
  valor normalizado com que `is_active` compara. **O domínio não FECHA o
  campo**: o Status é texto livre do SharePoint e é ele que o `cgd-stage` traduz
  em etapa — o valor gravado entra na lista, e o `selectDe` compara cego à caixa
  (senão `ACTIVE` e `Active` virariam duas linhas para o mesmo status).
- **A Razão Social sai em MAIÚSCULAS, e a padronização é no FUNIL de gravação**
  (§520, `UPPERCASE_COLUMNS` + `padroniza()`), alcançando os TRÊS caminhos —
  New Request, edição da grade e a importação do SharePoint. Só nos dois
  primeiros ela se desfaria sozinha: a importação REESCREVE a tabela inteira. É
  `upper()` e não `_norm()` — o acento FICA, porque tirá-lo mudaria o nome da
  empresa e é por este texto que a pasta da contraparte é procurada no
  Electronic Inventory (pasta gêmea não nasce daí: o `_ei_match_key` já compara
  em maiúsculas e sem pontuação).
- **O `_id` muda a cada importação do SharePoint** (§548): a escrita por
  `_id` leva a GERAÇÃO (`cgd_meta`) que a tela leu, e geração velha é 409
  `onboarding_reimported` — sem isso, uma tela aberta antes carimbava outro CGD.
- **O Apêndice aceita VÁRIOS arquivos** (§520): todos na MESMA pasta do EI com o
  mesmo prefixo, separados pelo marcador de cópia do inventário
  (`_ei_version_prefix`). Soltar ACUMULA e o seletor SUBSTITUI; mesmo nome e
  tamanho entra uma vez só. Os uploads vão **EM SÉRIE** (cada um é uma ida ao
  share, e o `_ei_next_ordinal` decide o número da cópia), e falha no meio para
  a cadeia, não cria a linha e NOMEIA o arquivo.

### Quotes

- **Os campos From/To se DIGITAM** (§508, `typeableDate` no `quotes.js`): o
  clique seleciona o texto, a máscara põe as barras (`22082026` → 22/08/2026),
  e o calendário acompanha — com dia e mês ele vai para o mês, com a data
  inteira ele a marca. Só a data INTEIRA vale para a busca. **O `keyup` do
  daterangepicker é desligado nesses campos**: ele relê o texto com parse
  frouxo do moment e desfazia a navegação no meio da digitação. Data futura é
  puxada para hoje (o `maxDate`), e texto pela metade volta à última data
  válida no blur — quem reescreve é o próprio plugin, no `hide`.

### Save CETIP Files

- **O catálogo de comportamento casa pelo nome entre PARÊNTESES do TYPE**
  (`_cetip_behaviour_for`): o prefixo do rótulo é descrição e é digitado na
  tela. Junção pelo rótulo inteiro deixa a linha SEM comportamento — o arquivo
  continua sendo salvo e some do JSON, do e-mail e do recorte do BACC, sem erro
  nenhum (`dict.get` de chave inexistente é um dicionário vazio, que é
  exatamente o que "sem comportamento" parece).
- **Dois arquivos atualizam uma BASE depois de salvos**, e não viram JSON de
  posição: `INDEXADORESSWAP_VCP` → `VCP.json` (`vcp_update`) e
  `CADASTROCURVASMOEDASFEEDERDOMINIOS` → `Dominio.json` (`dominio_update`,
  §492).
- **Na `Dominio.json` a chave é o QUADRUPLO** (grupo, subgrupo, `Codigo
  TipoIF`, identificador), NÃO o identificador: o mesmo id vale para vários
  tipos de instrumento (o IGP-M é o `104` em CCB, CCE, CCI…) e repete 202 vezes
  na base. Chaveado só pelo id, o upsert reescreveria a linha de um instrumento
  com a descrição de outro.
- **O identificador é normalizado dos DOIS lados** (`_dominio_id`): a base veio
  de planilha e guarda float (`14056.0`), o arquivo é texto (`14056`).
  Comparados como vêm, nada casa e a tabela inteira entra de novo a cada
  rodada — 4 mil linhas duplicadas por dia, caladas.
- **A `Data Inclusao` do arquivo não entra na base** (pedido da mesa), e
  `Classificação`/`MAKER`/`CHECKER` da linha existente sobrevivem: são da mesa,
  não do arquivo. Linha da base ausente do arquivo fica INTACTA, como no gêmeo
  do VCP.
- **Leitura em cp1252, não latin-1**: os dois só diferem na faixa `0x80-0x9F`,
  que é onde moram o travessão e as aspas curvas das descrições — em latin-1
  eles viram caracteres de controle invisíveis (§480).
- **`attach_ops` é o anexo do e-mail de STAGE 1** (o `CETIP Files Saved`, para
  o Brazil OTC Ops). Os quatro `attach_*` anteriores são todos do stage 2
  (Sales Support, CEM Latam, BACC recortado, HUB inteiro); o de stage 1 nunca
  levou anexo, e o cadastro de domínios é o primeiro (§492). O caminho anexado
  é o do arquivo JÁ SALVO no destino, nunca o da origem — é o que foi salvo que
  se confere, e a origem some no dia seguinte.

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
- **Template corrigido no repositório NÃO alcança o motor** (§488): o `.json`
  versionado é a SEED e a semeadura da subida não sobrescreve o que o banco
  tem (§434). O motor segue lendo o layout velho, sem erro nenhum, e o arquivo
  vai errado para a B3. Quem leva é
  `scripts/import_file_interpreter_template.py` (pula o que a mesa editou na
  tela; `--force` insiste), e ele roda DEPOIS do pull.
- **Os layouts de RECOMPRA já existem sob o nome da B3 — *antecipação***:
  `antecipacao-termo-multiclasses` (TER 0014, §4.9.3, 133 caracteres),
  `swap-antecipacao` (cód. 0035, 99) e `antecipacao-opcao` (cód. 0036, 149).
  Procurar por "unwind" não acha nenhum.

### Notificações, e-mail e schedulers

- **Notificação nova exige o rótulo `page` nos TRÊS mapas** (`_NOTIF_PAGE_URL`,
  `PAGE_URL` do `topbar.html` e do `sw-push.js`); sem ele o clique não vai a
  lugar nenhum. `check_notif_page_url.py` varre por AST.
- **Thread de scheduler não tem application context**: `with _app_context():`
  em volta da montagem INTEIRA do e-mail (o botão Run funciona e o automático
  morre em silêncio).
- **Jobs rodam no horário do Brasil** (`_br_now`), com catch-up na subida
  (`_ndm_pending_catch_up`, claim em disco). **Os quatro schedulers de
  importação só entre 08:00 e 20:00 BRT** (`IMPORT_POLL_WINDOW`; malformado =
  sempre aberta com aviso), `continue` antes do `try` — as duas APIs da Athena,
  o box de commodities e o box da recompra. `check_import_window.py` §5 varre
  os quatro por AST, pelo PAR (arquivo, função): dois deles se chamam
  `scheduler_loop`, e chaveada só pelo nome a varredura perderia o segundo sem
  falhar nada.
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
- **Bloco "Definição das Partes" de export do Word desalinha NA TELA** (§550):
  o navegador aplica o tab e o recuo `supportLists` juntos. Documento com esse
  bloco inclui `conf-partes-align.js` só no bloco `not doc_only` (JS, não CSS:
  `<style>` valeria no Word).

---

## 9. Ambiente local e instância do time

- **A dev é um macOS; a instância do time é Windows** (e o Excel da mesa
  é o Windows também). Defeito que só existe no Windows não se VÊ aqui:
  `win32com`/Outlook, o proxy 407, o `%LOCALAPPDATA%`, e o que o Excel faz
  com a planilha exportada (§477: o `#NULL!` nasce ao abrir o `.xlsx`, não no
  dado). Sem Excel na dev, o que se testa é o ARQUIVO (o `sheet1.xml` dentro
  do zip), como faz o `check_export_excel_ids.py`.
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
  **O proxy do JPM responde 407 e o `requests` não sabe autenticar nele**
  (o SSPI negocia com o servidor, não com o proxy): as Tools
  (`precificador/rede.py`) caem para o WinHTTP com auto-logon e, por último,
  o WinInet da macro da mesa (§450); a Quotes ainda não tem essa queda.
- **A instância roda sem reloader**: pull que tocou `.py` ou template exige
  restart. Mapping pela tela é a exceção.
- **`PYTHONPYCACHEPREFIX` no `.bat`** apontando para `%LOCALAPPDATA%` (nunca
  `%TEMP%`, nunca `PYTHONDONTWRITEBYTECODE`): sem isso a subida fica minutos
  gravando `__pycache__` no share sem imprimir nada. O `start-otc-tracker.bat`
  roda do share, mas desde 21/09/2026 é VERSIONADO (§518) — fora do repo ele
  ficava fora da revisão e do `check_bat_blocks.py`, e foi por isso que a linha
  do §322 nunca chegou nele. Copie o do repositório por cima do que está no
  share; o que a instância executa é o de lá. **Todo `ds` do `.bat` leva
  `call`**: `ds` é script do shell, e um `.bat` que chama outro sem `call`
  entrega o controle de vez — o pipe da versão antiga escondia isso.
- **A subida de ~12 min é o BYTECODE recompilado pelo SMB** (§524). O
  `new-otc-deploy.bat` cria uma pasta de versão NOVA a cada deploy e o
  `start-otc-tracker.bat` chaveia o cache pela versão
  (`pycache\%VERSION_PATH%`): versão nova é cache VAZIO, e para recompilar os
  ~313 módulos o Python lê cada `.py` INTEIRO pelo share, com o `routes.py` de
  711 KB no meio. Pior: o deploy manda `__pycache__` para o share justamente
  para evitar isso, e o `PYTHONPYCACHEPREFIX` **SUBSTITUI** o lugar onde o
  Python procura bytecode — o `__pycache__` ao lado do fonte nunca é lido, e as
  duas mudanças se anulam. A saída é **espelhar o código para o disco local**
  (robocopy `/MIR` + `pushd` no espelho, ~45 MB e ~770 arquivos, `static\data`
  já fora): na instância, **11m49s → 63s**. SÓ O CÓDIGO se move — `DATA_DIR`,
  `DATABASE_DIR` e `SHARED_DRIVE_ROOT` são UNC absolutos no `config.py`, não
  relativos ao diretório atual. Hoje isso vive no `start-otc-tracker_naeast.bat`
  (para MEDIR), e o §524 lista o que falta promover. **O código de saída do
  robocopy é um BITMASK**: 0–7 é sucesso, 8+ é falha — `if errorlevel 1`
  abortaria em toda cópia bem-sucedida. E **`/COPY:DAT` PRESERVA o timestamp da
  origem**: data de arquivo no share não diz quando o deploy rodou (foi o que
  me fez descartar esta hipótese uma vez).
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
| `import_pending_confirmation_missing.py [--xlsx] [--db-dir] [--limiar 90] [--margem 3] [--relatorio] [--gravar]` | ACRESCENTA aos três bancos o que a planilha `PENDING - Outstanding Confirmation OTC.xlsx` tem e eles não têm (mesa, 22/09/2026). **Trade Number que já está em qualquer um dos três é PULADO** — este não corrige linha existente e não apaga nada; quem reconstrói é o `import_pending_confirmation.py`, e aquele APAGA o que não estiver na planilha, backlog inclusive. **SPN, Client e Owner saem do Reference Data** (é o cadastro que liga a operação ao Economic Group, ao Signature Type e ao banker); o resto vem da planilha. O nome casa por IGUALDADE e, sem ela, pelo mais parecido — **só acima do limiar e com vantagem sobre o segundo colocado**, senão o SPN fica em branco e o nome vai para o relatório CSV: um SPN quase certo leva a operação para outra contraparte, com o Owner e o grupo de outra contraparte junto, e nada na tela acusa. O relatório traz o melhor candidato só **acima de 60%**: abaixo disso não há candidato, há o nome menos distante do cadastro inteiro (`PETROBRAS DISTRIBUIDORA` → `CARGILL ALIMENTOS, 57%`), e procurá-lo sem piso custava 156 s dos 178 s de uma carga de 80 mil linhas — o de-para varre as ~7 mil contrapartes a cada nome novo, e por isso também só roda para a linha que VAI ENTRAR. Com piso, 33 s. O laço imprime uma linha de vida a cada 10 mil: parado, ele é indistinguível de travado, e foi assim que a primeira carga foi interrompida e a varredura do ANTES (que agora se anuncia como tal) foi lida como o resultado. **O banco de destino é a coluna `Status` da planilha × a `Trade Date`** (mesa, 22/09/2026): `Ok` dentro de 12 meses → `ok`, `Ok` mais velha → `backlog`, **qualquer coisa que não seja `Ok` → `pending`** — e não o `_pc_target_category` do app, que responde pelo PENDING STATUS e jogaria no `pending` uma planilha inteira de operações já resolvidas. Linha com `Status = Ok` e um Pending Status que o app não lê como resolvido é CONTADA e avisada: a tela deriva o Status do Pending Status, e a manutenção das 11:30 moveria essas linhas para o `pending`. Leitura dos bancos `strict` (banco que não abre PARA o script — lido como vazio, ele reinseriria tudo como novo), gravação em INSERT de lote com UMA abertura por banco pelo `duckdb_write` (o upsert do app faria 3 deletes por linha: 240 mil operações no share numa planilha de 80 mil, que carregam em 100 s por este caminho), e **sem `--gravar` não escreve nada**. A leitura da planilha diz as ABAS e qual leu (`--aba` escolhe; a ativa é a que estava aberta quando salvaram, e num arquivo de várias ela pode ser a errada) e acha o CABEÇALHO na primeira linha que traga Trade Number ou Client, não na linha 1 — título ou linha em branco acima fazia as colunas resolverem contra a linha errada e a planilha sair vazia. O resumo FECHA a conta com o total lido (inseridas + já nos bancos + sem Trade Number + repetidas) e mostra exemplos de cada motivo: a contagem diz quantas ficaram de fora, só a linha diz por quê. `check_pc_import_missing.py` |
| `import_manual_confirmations.py` | cria os dois DuckDB da esteira e semeia do `MANUAIS.xlsx` |
| `backfill_manual_confirmations.py [--dry-run] [--source] [--repair]` | traz para a esteira o que foi mapeado antes dela (FWD Start pelo B3 ID; `--dry-run` lembra as chaves da passada). **`--repair` refaz as CASCAS** (§546): linha só com Trade ID + Callback/FepWeb ID é reconstruída pelo `_mc_save_from_deal` a partir do deal, e o que a casca tinha volta por cima; casca sem deal no cache é listada no fim. A família de página genérica tira a PASTA do `_GENERIC_ND_PRODUCTS` e o SOURCE do `_generic_nd_mc_source`, por deal — é o que faz o Vanilla entrar só no de MGT (§453) e o que impede o rótulo de tela (`NDF/FWD Start`) de virar caminho. Source de `_MC_CONFIRMATION_SOURCES` sem família aqui = operação antiga invisível para sempre no Monitor: `check_mc_backfill.py` |
| os scripts que leem RefData/calendário/arquivos-dia (`create_counterparty_folders`, `create_cetip_folders`, `import_pending_confirmation`, `update_pending_confirmation_*`, `backfill_manual_confirmations`, `export_new_deals_excel`, `fix_cgd_economic_group`) | leem pelo ARMAZÉM e pelo `data_path` (§440): o `apps/static/data/*.json` do checkout é a seed, não o dado |
| `import_cgd_sharepoint.py` · `import_cgd_auxiliar.py` | lista de CGDs e as três abas do `Auxiliar.xlsx` |
| `import_file_interpreter_template.py [--key <k>] [--force] [--dry-run]` | leva ao BANCO um template do File Interpreter corrigido no repositório. O `.json` versionado é a SEED, e a semeadura da subida não sobrescreve o que o banco tem (§434/§488): sem este script o motor segue lendo o layout velho e o arquivo vai errado para a B3, sem erro nenhum. Template que o banco tem EDITADO (algum `source` preenchido) fica de fora sem `--force` |
| `split_notifications_db.py --dry-run` | mostra o que a separação do sino vai copiar |
| `dev_seed_positions.py` | só na DEV: reemite a última posição B3 numa data recente (`--from … --force`) |
| `convert_json_to_duckdb.py` + `scripts/convert/` (40 fatias) | a IMPORTAÇÃO JSON → DuckDB (o cutover do §434 e o legado fora da janela), incremental por `_manifest`, `--meses` 12 por padrão (`0` = tudo), `--only/--force/--dry-run/--bloco`; reconverte sozinho o payload-objeto sem `__raw` |
| `slim_duckdb.py [--db-dir] [--only cache] [--dry-run]` | emagrece os bancos de arquivo-dia JÁ existentes para a forma do §437 (lista só `_seq`/`_raw`, objeto só `__raw`), copiando do PRÓPRIO banco e trocando o arquivo; com o app PARADO; idempotente; RECUSA banco em limbo de checkpoint (vai pelo recover); o `_manifest` é recriado pelo SCHEMA e não por `AS SELECT` — o CTAS deixa a PRIMARY KEY para trás e o banco vira somente-leitura (§443) |
| `recover_duckdb_wal.py [--db-dir] [--only] [--work-dir] [--dry-run] [--no-slim] [--all] [--descartar-wal]` | tira do LIMBO de checkpoint (§442: `.wal.checkpoint`/`.wal.recovery` ao lado, ou `.wal` > 16 MB) copiando `.db` + WALs para um disco LOCAL, abrindo em escrita + `CHECKPOINT`, emagrecendo e trocando no share; o que substituiu vai para `db/_recuperado/<carimbo>/` (apague depois de conferir); TODAS as instâncias paradas, mesma versão de duckdb (banco preso por processo VIVO é PULADO com `EM USO`, sem tocar em nada — `--lock-seconds` regula a espera e `--insistir N` fica tentando os pulados, porque a trava do vizinho vai e volta); a cópia local perde o somente-leitura herdado do share, a pasta de `--work-dir` é PROVADA (renome) antes de qualquer cópia e o `.wal.recovery` — que É a fusão do `.wal` com o `.wal.checkpoint`, e o destino que o `MoveFileW` do DuckDB recusa — não vai para a cópia local quando os dois estão lá; rename negado na abertura da cópia faz o script FUNDIR os dois WALs à mão, por cópia, e abrir de novo (§444); `--only` aceita um `.db` só, e `--descartar-wal` é o WAL que NÃO REPLAYA — segue com o `.db` sozinho, perdendo o que veio depois do último checkpoint (§447) |
| `export_duckdb_to_json.py` | o ROLLBACK: reconstrói do banco os JSONs com diferença (`--dry-run`, `--force`, `--only`); `check_export_rollback.py` prova que cada forma volta exata |
| `scripts/standalone/` (40, GERADOS por `build_duckdb_standalone.py`) | os mesmos conversores para máquina sem o código (`pip install duckdb` só) — nunca editar à mão |
| `build_sop_docx.py` | SOP e Guia em Word a partir do `.md` |
| `fix_asian_dates_xlsx.py <xlsx> [--dry-run] [--feriados] [--calendario IPE]` | conserta as datas da Média Asiática de um Excel do Live Position Option numa aba NOVA (§537): mesmo mês → reordena; dois meses → o mês com MAIS datas inteiro, dia útil a dia útil no calendário do Holidays (IPE); empate fica e vai para o log. Calendário sem feriado no ano PARA — sem feriado, dia útil vira dia de semana |
| `diag_ndfsum_account.py [AAAA-MM-DD]` | DIAGNÓSTICO da coluna Account do Settlement Summary: nome da linha → SPN no Reference Data → registro do Counterparty Details → defaults → conta, dizendo onde a cadeia quebra (§436) |
| `diag_pending_confirmation_db.py [--db backlog\|pending\|ok\|todos] [--db-dir] [--out] [--csv] [--so-resumo]` | DESPEJA o conteúdo dos três bancos do Pending Confirmation (uma aba por banco) e, na tela, o RESUMO que costuma responder a pergunta: linhas, a Trade Date mais velha e a mais nova, o histograma por ano e **quantas linhas têm data ILEGÍVEL**, com amostra do texto cru. "A busca não traz nada antes de tal dia" tem duas causas que se parecem e se consertam ao contrário — não há nada mais velho, ou há e a data está num formato que o app não lê (serial do Excel, `26/8/25`), e aí a linha some de todo filtro por data sem erro nenhum. Só LÊ, roda com o app de pé (abre pelo `duckdb_read`), e banco em uso ou ilegível **para com o motivo** em vez de imprimir zero linha. O `.xlsx` sai com toda célula como TEXTO (o contrato `26E04610365` vira `#NULL!` numa célula numérica, §477) |
| `diag_boot_imports.py` | DIAGNÓSTICO da SUBIDA (§522/§524): `python -X importtime` num subprocesso, com o farol do app passando direto para a tela e um pulso a cada 5 s (segundos · módulos · último módulo) — saída que demora tem de dizer que está viva, senão doze minutos de subida são indistinguíveis de um travamento. Rodá-lo de um clone LOCAL é o CONTROLE do experimento, não erro de uso: mesmos dados no share, só o código em disco local — caiu de minutos para segundos, o custo é ler o código pelo SMB; não caiu, é o que o import EXECUTA. Vale rodar os dois |

`apps/static/data/db/` é gitignorado: bancos não vêm no pull. Telas vazias
depois de um pull são migração não rodada, não bug.

### `scripts/tests/` (163 scripts)

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
