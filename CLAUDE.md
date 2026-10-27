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
  é a dev MAIS um commit no `apps/config.py` — o bloco entre `── ENV:DEV ──`
  e `── /ENV ──` (dados, bancos e share em
  `\\Nawest.ad.jpmorganchase.com\lac\BRA\intra` em vez de dentro do checkout e
  `I:\`, o Batch Conecta em `New`/`Return` em vez de `New - UAT`/`Return -
  UAT` — `_CONECTA_SUFFIX`, §551 —, e o maker/checker LIGADO, que na dev é
  desligado — `_FOUR_EYES`, §553). Código nasce na dev e chega lá por merge
  (`/commit` publica na dev, `/commitjp` faz o merge). Corrigir direto na
  prod cria divergência invisível até o merge seguinte conflitar. Nunca
  presuma `main`.
- **Stratos: `OTC-Tracker-Stratos`** (§677) — a dev MAIS o bloco
  `ENV:STRATOS` no `apps/config.py`, a pasta `stratos/` (o overlay do
  repositório do Stratos, `singing-moose-flask`: o `solution.py`/`run.py` do
  template com os blocos DO NOT DELETE intactos, o `otc_stratos.py` e o
  `requirements.txt` GERADO) e o `stratos-sync.bat`, que leva `apps/` para
  `src/apps/` lá. Mora numa worktree própria (`OTC Tracker Stratos`) — nunca
  faça checkout dela neste working tree; `/commitstratos` faz o merge e
  `/commitall` publica nas três. Três mudanças da dev quebram o Stratos sem
  quebrar a dev: renomear o que a ponte (`otc_stratos.py`) usa pelo nome — as
  funções do `apps.create_app` que a montagem chama (`_require_config_names`,
  `_seed_data_dir`, `register_blueprints`…), as do `routes` que ela chama
  (`_set_session`, `get_user_by_sid`…) e os endpoints que ela intercepta
  (`logout`, `unlock`…) —, citar o proxy on-premise nas portas antigas — mesmo
  em comentário, o scan do `stratos push` recusa o arquivo — e mexer (nome,
  assinatura, retorno) nos helpers PRIVADOS do `scripts/recover_duckdb_wal.py`
  (`_recupera_local`, `_a_copiar`, `_manifest_linhas`…) ou no
  `slim_duckdb.emagrecer`, que o `stratos/exporta_dados.py` (a cópia dos bancos
  do share para o Stratos, §678) chama por dentro. O
  `stratos/tests/check_stratos.py` pega as três — a última rodando o
  `check_exporta_dados.py` —, menos o `unlock` renomeado: no teste o IP bate e
  o Unlock do próprio OTC destrava sem a ponte. **No Stratos os bancos são os
  mesmos DuckDB, no Shared Drive (EFS) da solução** (§681, que revê o §678):
  a ponte (`_raiz_no_shared_drive`) aponta o `OTC_STRATOS_ROOT` para ele antes
  do `import apps`, e a chave da sessão vai junto. O porte para o Stratos NoSQL
  (MongoDB) ficou para depois da virada; a prod segue na instância da equipe
  até o Stratos estar 100%, e os passos que faltam (a chegada do pacote sem
  pisar nos bancos em uso, o backup de hora em hora) estão no §681. As travas
  no EFS têm PROVA (§689, `stratos/src/prova_travas.py`, rota
  `/stratos/prova-travas`, só do master): o risco é o NFS emular o `flock` com
  trava POSIX, que é do PROCESSO — um segundo descritor no mesmo arquivo a
  converte e fechá-lo a solta —, e as conferências `mesmo_processo_*` o acusam.
  As pastas do share que o app usa chegam e saem por uma PONTE (§683):
  `stratos/ponte_share.py` numa máquina da rede do JPM e os manifestos da
  thread do contêiner, com a regra no `stratos/src/ponte_comum.py`. Pasta NOVA
  do share na dev entra na lista `PASTAS` de lá, senão no Stratos ela fica
  vazia sem erro nenhum, e com o SENTIDO certo (`entrada`, `saida`, `ambos`
  ou `desce`): pasta que o app só GRAVA e nunca lê é `desce` (§690) — o
  espelho a pula e o alinhar só registra na base o que o share tem, sem subir
  gigabytes que o app não usa. Até a virada a ponte é ESPELHO (só do share
  para o Stratos) e nunca escreve no share. Caminho do share passa pelo
  `ponte_comum.longo` (`\\?\UNC\…`): o Electronic Inventory tem pasta acima
  do limite de 248 caracteres do Windows.
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
- **Design: UM tema e UM JS de casca** (rebranding no visual do Pane,
  19/10/2026, §630): `static/scss/otc.scss` → `static/css/otc.css` e
  `static/js/otc.js`. Não existe camada carregada depois redefinindo token —
  `app.css`, `visual-refresh.css`, `streamflow.css`, `tools.css` e os JS delas
  foram APAGADOS, e o `check_theme_toggle.py` recusa template que volte a
  carregá-los. **Token é `--otc-*`** (texto `--otc-text/-2/-3`, superfícies
  `--otc-fill`/`--otc-glass`/`--otc-menu-bg`, matizes `--otc-blue…danger`,
  raios `--otc-r-*`, movimento `--otc-dur-*`/`--otc-ease*`); `--ins-*` é o
  prefixo do Bootstrap e, como `--vr-*`/`--sf-*`, virou APELIDO que lê os
  tokens novos (§2d do SCSS) — página antiga segue certa, página nova escreve
  `--otc-*`. **Jamais `--bs-*`**: o tema não os define, caem no fallback claro
  e viram placa branca no escuro. Mexeu no `otc.scss`: `npx gulp styles` e
  commite o `otc.css` junto (o `?v=` sai do `asset_v`). Armadilhas em §7.
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
`create_app()` (`apps/__init__.py`) configura a camada `database_access`,
semeia o `DATA_DIR` e importa `apps.pages.routes`. **Um único blueprint** (`pages_blueprint`) é dono de todas
as rotas. `create_app` confere `_REQUIRED_CONFIG_NAMES` antes dos blueprints e
recusa subir se o `config.py` ficou para trás num pull (§9).

### Onde o código mora

| Camada | O que é |
|---|---|
| `apps/pages/routes.py` (~13,6 mil linhas) | casca e plataforma miúda: sessão/authz-endpoints, sino, `_MAPPING_DEFS`, leitores `_ndfc_*`/`_ndfsum_*`/`_ndfadv_*`, Daily Settlement `_ds_*`, wiring das features e os ALIASES (`_x = _pf_anbima._x`) |
| `apps/pages/platform/` (25 módulos) | infra horizontal: `anbima`, `authz`, `db`, `dates`, `json_cache`, `mail`, `email_validation`, `notifications`, `task_runs`, `user_photos` (a foto `images/users/<sid>.jpg`, uma listagem por minuto) e os motores `settlement`, `confirmations`, `counterparty`, `forecast`, `electronic_inventory`, `manual_confirmation`, `file_interpreter`, `pending_confirmation`, `operations_b3`, `new_deals` |
| `apps/pages/features/<nome>/` (49 verticais) | `entrypoint.py` (rotas) · `commands.py` (escrita) · `queries.py` (leitura) · `domain.py` (regras puras) · `infra/` — todas em desenho fino; não existe mais `engine.py` |
| `apps/pages/database_access.py` | a camada de banco: permit + lock de arquivo + farol de eventos (§4) |
| `data_store.py` · `duck_read.py` · `json_to_duckdb.py` | o ARMAZÉM (o `DATA_DIR` como sistema de arquivos virtual sobre os DuckDB), a fachada de leitura com os nomes antigos, o motor de conversão (§4) |
| `data_paths.py` · `request_cache.py` | caminhos de dado; `once_per_request`/`req_cached` |
| `manual_conf.py` · `cgd_docs.py` · `otc_tickets.py` | donos dos bancos da esteira, do Onboarding e do store de tickets |
| `athena_api.py` · `otc_boxparse.py` · `otc_boxscan.py` · `otc_emails.py` · `webpush.py` | Athena (SSO Kerberos), parser do recap, varredura do box, e-mails, push |
| `recon_fxo.py` · `recon_cgd.py` · `recon_payrec.py` · `recon_comitente.py` · `recon_conf_matching.py` | motores das recons |
| `confirmation_pdfs.py` · `quotes.py` · `precificador/` | PDFs em reportlab, cotações, motor de mercado das Tools (puro, sem Flask) |

Templates: `layouts/base.html` → `layouts/vertical.html` (o único layout) →
`pages/*.html`. `partials/sidenav.html` é o único menu.

### Adicionar uma página

1. Rota no entrypoint da vertical (ou no `routes.py` se for plataforma)
   devolvendo `render_template('pages/<nome>.html', segment='<nome>')`.
2. Template em `apps/templates/pages/` estendendo o layout.
3. CSS da tela no `<style>` do `{% block extra_css %}`, só o que é DELA e
   com tokens `--otc-*` (§7, Layout e vidro). O SCSS é um só e é do tema.
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
  (`cache/<rotina>/.../AAAA/MM/DD`), os 48 cadastros do `/mapping`
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
  **O Batch Conecta é `Config.CONECTA_NEW_PATH`/`CONECTA_RETURN_PATH`**
  (§551): a DEV grava os arquivos gerados em `Batch Conecta\New - UAT` e o
  Mapping B3 ID lê de `Return - UAT`; a PROD usa `New`/`Return`. O sufixo é o
  `_CONECTA_SUFFIX` do bloco de ambiente — gerador novo grava pelo
  `routes.CONECTA_NEW_PATH`, nunca montando a pasta. **E o NOME na New começa
  pela conta da visão** (mesa, 20/10/2026, §646): `73760009.TCO_BANCO.txt` —
  `routes._conecta_file_name(visão, nome)`, a conta PRÓPRIA da LE no
  `b3-accounts` (aceita a LE, o balde `BANCO` e o par `MGT x CLI`). Os nomes
  saem TODOS antes do primeiro arquivo (visão sem conta recusa o lote), um
  arquivo é de UMA visão só (as Opções juntavam Banco e Lawton no
  `FXO_Banco.txt`) e o download do preview fica sem a conta — MENOS nos
  SWAPS (Bullet, Cashflow, Cetes; equipe, 26/10/2026, §698): ali o Send com
  download e o Export do preview levam a conta como a New (o arquivo baixado é
  o que vai ao Conecta); no preview a visão sem conta fica com o nome de
  sempre, e quem recusa é o Send. `check_conecta_file_name.py` §5 varre por
  AST: quem lê o `CONECTA_NEW_PATH` chama o nomeador; §6 prende os swaps.
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
  **Poll com o arquivo PARADO não abre o banco** (§614): carimbo
  `(mtime_ns, tamanho)` do `.db` + `.wal` igual, mesmo dia e cópia com menos
  de 30 s → serve o `_notif_last_good`. Notificação nova mexe no `.wal`; query
  que falhou grava `stamp=None` e nunca vira atalho.
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
  `scandir`, sem `stat` por arquivo), o RefData por SPN/nome
  (`_fxo_refdata_by_spn`, `_pc_refdata_by_name`: builder memoizado, wrapper
  devolve `{}` na falha SEM memoizar e entrega CÓPIAS) e o
  `recon_payrec._mapping_rows` (§614). No navegador, `/api/me/access` é UMA
  promessa por página (`window.otcMeAccess()`, `base.html`) — não faça `fetch`
  próprio dele.
- **O calendário ANBIMA em memória acompanha o mtime do `anbima.json`**
  (`_anbima_stamp`): feriado cadastrado vale no request seguinte. Calendário
  FIXADO à mão (teste com mtime `None`) nunca é recarregado.
- **Não há ORM**: SQLAlchemy/Flask-Migrate saíram (08/10/2026, §627) — nada os usava.
  O único SQLite que sobra é o banco de comitentes, pelo `sqlite_read`/
  `sqlite_write` da `database_access`.

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
`user_role`, `session_ip`.

- **`/verify-2fa` e `/resend-code` respondem `{success, code, message}`**
  (`_auth_json` + `_AUTH_MSG_CODES`, §616): a tela de 2FA diz o aviso pelo
  `_TRANS` do `auth-two-factor-orbit.js`; frase NOVA no `verify_code` /
  `_code_send_allowed` entra no mapa, senão sai sem código (só o fallback em
  inglês). Sem `pending_sid` é JSON `session_expired`, nunca redirect (o fetch
  lia HTML). A animação corre em PARALELO ao POST — não a ponha na frente dele.
- **A sessão só cai se o IP mudar** (mesa, 24/09/2026, §552): não há prazo,
  auto-lock por inatividade nem *Keep me signed in*. Ela é permanente (cookie
  renovado a cada request, `PERMANENT_SESSION_LIFETIME` de 365 dias) e o
  `enforce_session_ip` a encerra quando o IP do request difere do
  `session_ip`; o login seguinte cai no código por e-mail. Sessão sem
  `session_ip` é carimbada, não derrubada — teste que monta sessão à mão e
  confere se o cookie foi reemitido tem de pôr o `session_ip`. O Lock Screen
  MANUAL do menu continua. **A página que ficou aberta descobre isso no
  clique seguinte** (§557): o `static/js/session-guard.js` (no `<head>` do
  `base.html`, só com sessão) embrulha o `fetch` — 401 de um `/api/*` vira o
  aviso traduzido "Sessão encerrada" e a volta ao login, e a promessa da
  página fica pendente para o erro cru dela ("Not authenticated") não cobrir o
  aviso. Todo 401 de `/api/*` é "sem sessão"; não use 401 para outra coisa. A
  troca de IP loga em WARNING (`[enforce_session_ip]`).
- **Database Explorer (`/database-explorer`, Data Base) é só do MASTER**
  (§673): os bancos DuckDB do `DATABASE_DIR` na tela, com Edit, Delete e
  alteração em lote. Quem segura é a ROTA (`_session_is_master`), não o
  `Page_Access` — vazio é acesso total —, e a página fica fora da checklist do
  /page-access (`authz._MASTER_ONLY_PATHS`). Banco e tabela só entram no SQL
  conferidos no catálogo do próprio banco; valor, sempre `?`. Cada linha vai
  com `rowid` + impressão digital, conferidos sob a trava: a linha que mudou
  desde a leitura RECUSA o pedido inteiro. **Banco do armazém (com
  `_manifest`) é só leitura**: o app o lê pelo `_raw` e memoriza pelo carimbo,
  então a coluna tipada editada ali não chegaria às telas. **O JSON abre em
  COLUNAS** (`domain.expand`): objeto de objetos vira uma linha por chave,
  lista de registros uma por item, objeto vazio não vira linha; a tabela
  "chave + JSON" do armazém (`__meta`, `__raw`, `_seq`/`_raw`) já abre assim, e
  o seletor View volta ao cru; com uma coluna de data ela abre ordenada pelo
  dia, o seletor Day mostra UM dia com a quebra inteira dele, e o rodapé soma
  as colunas decimais do que está filtrado. A visão expandida é só leitura. Toda gravação
  loga `[db-explorer]` em WARNING com SID, banco, tabela e colunas.
- **Maker/checker (4-olhos) só vale na PROD e no Stratos** (§553, §677):
  `Config.FOUR_EYES`, do bloco de ambiente (`_FOUR_EYES = False` na dev, onde
  uma pessoa só testa; no `ENV:STRATOS` ele nasce ligado, e a variável de
  ambiente `OTC_FOUR_EYES=0` o desliga). Trava NOVA de "o próprio maker não
  aprova/envia" pergunta ao
  `platform.authz.is_own_change(maker, sid)` no servidor e é condicionada ao
  `OTC_FOUR_EYES` no navegador (a página o define ao lado do
  `CURRENT_USER`/`CURRENT_USER_SID`) — comparar maker e SID à mão continua
  dando 403 na dev, calado, e o `check_four_eyes.py` recusa. Teste que PROVA a
  trava liga o flag (`Config.FOUR_EYES = True`) antes de subir o app.

- **Papéis** (`Role` no banco): `ADMIN`, `BO`, `MO`, `FO`, `INSTITUTIONAL`,
  `HUB`. **Master** é por SID (`_MASTER_SIDS = {'E930179'}` em
  `platform/authz.py`), não concedível; `_session_is_admin()` = ADMIN ou
  master. Só o master altera acesso de admin/master e escapa de toda restrição.
- **Por página**: `users.Page_Access` é array JSON de URLs. Vazio = não
  configurado = acesso total (admins incluídos). `enforce_page_access`
  bloqueia quem tem allowlist e redireciona para `_safe_landing(allowed)` — o
  dashboard é concedível, não sempre permitido. `_ALWAYS_ALLOWED_PATHS` =
  `{'/users-profile', '/page-access', '/user-home', '/settings'}` (as duas
  últimas são pessoais, §632). `/api/*` e `/static*` nunca são bloqueados
  aqui.
- **Acesso TOTAL é o marcador `["*"]`, não a lista** (§686): a lista que
  cobre todas as páginas controláveis é gravada assim (`_set_page_access`) e a
  leitura a expande para as páginas do MOMENTO — a página nova entra
  habilitada para quem tem o Full access, admin ou não. A subida converte uma
  vez quem já tinha tudo (`page_access_upgrade_full`).
- **Por card (Control Panel)**: tokens `/control-panel#<id>`
  (`_CONTROL_PANEL_CARDS`, na ordem da tela — monta a checklist do
  `/page-access`); `enforce_control_panel_cards` bloqueia o endpoint da rotina
  sem o card (`_CP_ENDPOINT_CARD`). **O `id` é o token gravado**: renomear
  revoga em silêncio. A seção do card é o DOM (`data-cp-hdr` + `.row.cp-cards`),
  nunca um mapa no JS. Seis seções: Intraday, Settlement Reporting, Pending
  Confirmation, Economic Affirmation, Reference Data, Application; dezesseis cards
  (o `check_control_panel_sections.py` conta — card novo mexe nele). O card *New
  Version Released* lê a versão do `link.txt` ao lado do
  `start-otc-tracker.bat`; sem versão o envio é recusado; destinatário é quem
  está `Active`.
- **`refresh_session_role`** (`before_request` próprio): o papel do cadastro
  alcança quem já está logado em até 30 s, pela mesma leitura da allowlist —
  e o CARGO também (`Position` → `user_position`, o que o rodapé do sidenav
  mostra; a tela Users esquece o cache ao gravar, então ali vale na hora).
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
(versionado; `BaseMoeda.json` também está lá) — é a SEED que a subida importa
para o banco, não o cadastro. Três nascem SÓ do `seed` do `_MAPPING_DEFS`, sem
`.json` (`opb3-msg-asset`, `swap-cetes-leg`, `swap-bullet-curve`), e isso não é
falta. **O app não grava mais JSON aqui** (§434): um `.json` de cadastro
não versionado num checkout é sobra da gravação em disco de antes de
09/09/2026 (na dev o `DATA_DIR` é o próprio checkout), e quando o arquivo
passa a ser versionado o `git pull` recusa (`untracked working tree file would
be overwritten`) — renomeie o solto e puxe (§671). `_mapping_rows(key)` semeia na
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
outra coluna (pelo que as linhas já cadastradas usam); **`derive: {from, format}`** PROPÕE o valor a partir de outra coluna (`{}` = o valor digitado, em maiúsculas), sem sobrescrever o que foi digitado à mão (§559); tipo **`refdata`** liga nome/SPN/Tax ID ao Reference Data (um
escolhido, os outros dois se preenchem). **`file`** aponta para um JSON já
existente (o `swap-index` edita o mesmo `SwapIndex.json` do Index Results —
declare as colunas extras, senão o POST as derruba).

São **52**: `swap-bullet-curve`, `swap-termo-index`, `swap-cetes-leg`, `currency-base`, `interbook-ndf`, `commodities-b3`,
`publisher-ndf`, `le-accronym`, `le-spn`, `bank-name`, `fxo-conv-rate`,
`ndf-pdf-cpty`, `swap-curves`, `cetip-files`, `api-links`,
`manual-conf-validation`, `manual-conf-sla`, `fxo-internal-cpty`,
`fxo-book-disregard`, `opb3-events`, `swap-ir-client`, `swap-ir-term`,
`bankers-email`, `swap-index`, `ndfc-ir-exempt`, `b3-accounts`,
`ndfc-advice-split`, `tools-swap-index`, `opb3-msg-asset`,
`swap-funcionalidade`, `swap-amortizacao`, `swap-code-labels`,
`quotes-equity`, `quotes-commodity`, `mt300`, `settlement-exception`,
`gdt-codes`, `equity-leg-prefix`, os sete `dce-*`, os quatro `cgd-*` e os três `wht-*`
(`wht-codes`, `wht-company`, `wht-non-resident`).

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
  Commodities/Swaps, `Unwinds` × NDF = `getTradesBySettle` (a recompra de NDF
  FX, §640), `Recon FXO`, `Intrag DCE`, `Daily Settlement` × NDF =
  `getTradesBySettle`); `SOURCE` API × Bob Report;
  `YYYYMMDD` é a data; produto é o parâmetro da API, não a página. O
  `settlement` da API é LISTA e o valor é o primeiro item numérico de `Rolled
  Positions` (§425) — **no cross SEM BRL (USD × GBP, USD × EUR) é o SEGUNDO**:
  ali o primeiro é o notional da moeda (mesa, 22/09/2026; `_ndfc_api_rolled`).
- **`swap-cetes-leg`** (§650) — a perna do e-mail das Cetes (`we pay`/`we rec`,
  token; `Exact` vence `Contains`, o mais longo vence) → curva B3, Tipo/Classe
  da VCP, se leva a taxa FIXA (`RATE`) e o texto da Descrição com `{fx}`,
  `{rate}`, `{dn}`. Exatamente uma das duas pernas é fixa; perna sem linha é
  lacuna (`swt_leg_unmapped`) e o Send recusa.
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
  vence, sem linha não põe rótulo), **`fxo-conv-rate`** (na tela **Currency Conversion Rate** — serve FXO e NDF, a chave ficou pelo cadastro gravado; Moeda Base digitada propõe `<MOEDA> PTAX`; moeda não cadastrada
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
  centro/middle `nowrap`. **Desde o rebranding a regra é GLOBAL, no tema**
  (`table.dataTable > thead > tr > th` / `> tbody > tr > td`, e o clone
  `.dt-scroll-headInner thead th` **com `!important`** — o DataTables remove o
  id da tabela clonada); a tela declara só a LARGURA das colunas. Tabela que
  NÃO é DataTable continua declarando a sua. `table-centered` não existe em
  CSS nenhum. `check_table_center.py` cobra a regra no tema e a das tabelas
  soltas nas telas. **A ÚNICA exceção é a tabela de Users › Roles, alinhada à
  ESQUERDA** (mesa, 20/10/2026): o guarda a tem em `A_ESQUERDA` e cobra o
  `left` nela; tela nova não entra lá sem a mesa pedir.
- **Filtro é o FUNIL "de Excel" no cabeçalho** (mesa, 29/09/2026; §591):
  `static/js/excel-filter.js`, carregado pelo `base.html` DEPOIS dos scripts
  da página, liga-se SOZINHO a toda DataTable (as que existem e as que nascem
  depois, pelo `init.dt`). Menu: ordenar A→Z/Z→A, limpar a coluna, busca
  (aceita LISTA colada, `123; 456`), valores distintos com caixinhas e
  **(Vazias)**, **Adicionar seleção atual ao filtro** (pesquisando numa coluna
  já filtrada, SOMA em vez de trocar), OK/Cancelar. A lista de cada coluna sai
  das linhas que passam nos filtros das OUTRAS. O valor comparado é o que a
  célula DESENHA (`render('display')`, sem HTML) — nunca `data()[col]`, que
  numa tabela de objetos é `undefined`. **Data `dd/mm/aaaa` ordena como DATA**
  (02/10/2026, §618): o helper registra o tipo `otc-dmy` na FRENTE dos nativos (com
  hora e dentro de badge também) — o `date` do DataTables lê `05/09` como 9 de
  maio e a coluna caía em texto, ordenando pelo DIA no clique, no A→Z e na
  lista do funil. Tabela que nasceu antes dele tem o tipo zerado e redetectado
  ao ligar (`redetectTypes`); página nova não registra detector próprio. Página nova não escreve nada; coluna
  sem funil = cabeçalho vazio, checkbox, Actions ou `searchable: false`;
  tabela fora com `data-excel-filter="off"`; `serverSide` e `searching:
  false` ficam de fora (a segunda desliga TODA filtragem — são as tabelas
  ocultas do Export). **O funil só alcança DataTable**: lista montada à mão
  fica sem ele — era a Support Center › Tickets List, que virou DataTable
  (§662) com a busca e o Filter By no `ext.search` (o `column().search()` o
  funil zera a cada draw). **O funil é uma PEÇA do flex do cabeçalho** do
  DataTables 2 (`.dt-column-header`: título · funil · ícone de ordenação),
  nunca absoluto no canto do th: nas telas que fixam a largura da coluna
  no CSS (as Intrag, o Reference Data) ele ficava POR CIMA do texto. O
  título é que cede (quebra, ou "…"), palavra não se parte, e o helper
  ALARGA a coluna cujo título ficou cortado (`widenTruncated`: `sWidthOrig`
  + `adjust`, até três passadas — tabela `table-layout: fixed` ignora
  `min-width` no th) **ou EMPILHADO em mais de duas linhas** (§680): o funil,
  a ordenação e o respiro do centro levam ~80px do th, e numa coluna numérica
  de 130px o título ficava em 31px, uma palavra por linha. A largura de duas
  linhas sai da fonte real (`twoLineWidth`, canvas).
  **A antiga linha de filtro por coluna (2ª linha do `<thead>`) é REMOVIDA
  pelo helper** (mesa, 29/09/2026, §597 — escondida não bastava). O DataTables
  redesenha o cabeçalho a partir do layout que leu na init (`aoHeader`, uma
  entrada por `<tr>` com o `.row`), então apagar só do DOM não segura: ela sai
  no `options.dt`, que ele dispara ANTES de ler o cabeçalho, e — para a tabela
  que nasceu antes do helper ou a linha montada no `initComplete` — do
  `aoHeader` E do DOM depois da init. Linha de filtro é a que tem campo e
  nenhuma célula com texto: cabeçalho de duas linhas de TÍTULO (o Dashboard do
  Pending Confirmation) fica. Tabela fora do funil (`data-excel-filter="off"`,
  `serverSide`, `searching: false`) e a grade própria do File Interpreter (não
  é DataTable) ficam com a linha: ali ela é o único filtro. O código dela nas
  páginas é dívida morta — não escreva linha de filtro em página nova. **Todo "Clear Filters" limpa os
  funis** (o helper reconhece o botão pelo id/`data-lang`); página com uma
  tabela por card dá ao botão `data-oxf-table="#id"` e ele limpa só aquela
  (os dois Summaries). **A linha nasce ESCONDIDA pelo CSS** (§610,
  `otc.scss` §7, pelas classes/ids que as páginas usam): o helper só a
  tira na init, e na instância a init demora — a linha ficava na tela o tempo
  todo da carga. E **callback do DataTables não usa a variável `table`**: o
  `drawCallback` da primeira pintura roda antes da atribuição — use
  `this.api()` ou guarde (`if (!table) return`); estourar ali derruba a
  inicialização inteira da página. Com `scrollX` o DataTables deixa uma CÓPIA do
  cabeçalho no corpo (altura zero): o funil dela fica `visibility: hidden`
  (some da vista mas OCUPA o espaço, para a medida das colunas bater). O `sf-multi.js` e o §462 (delegação no
  container) continuam valendo para o que ainda filtra por campo.
- **Botões de ação: squircle 32×32** travado nos DOIS eixos, `padding:0`,
  `border-radius:10px !important`, ícone Tabler `1rem` (nunca `.fs-13`),
  tooltip colorido delegado no primeiro hover (os `<td>` são reescritos a cada
  redraw). Regra GLOBAL no `otc.scss` §6b (a página NÃO redeclara o
  `.btn-act`), POR CLASSE: botão de linha NOVO (o `btn-row-b2b` do Create
  B2B, §699) entra nas duas listas de lá — a da forma e o par com `.d-none` —,
  senão sai como a pílula redonda do `.btn`; ordem Confirm `ti-check` →
  Edit `ti-edit` → Delete `ti-trash` → Send `ti-brand-telegram`; edição Save
  `ti-device-floppy` + Cancel `ti-x`. **A COR é semântica e o guarda varre TODA
  página**: Confirm/Approve `btn-success`, Edit `btn-info`, Delete `btn-danger`,
  Send `btn-primary`, Save `btn-success`, Cancel `btn-secondary` — duas telas
  novas nasceram com o Edit em `btn-warning` e nada acusou, porque o guarda só
  olhava as duas páginas de referência. `check_row_action_buttons.py`.
  **`d-none` esconde botão de linha** (§497): a regra de FORMATO declarava
  `display: inline-flex !important`, mesma especificidade do `.d-none` e
  carregada depois dele, e todo `toggleClass('d-none', …)` de botão de ação era
  mudo — o botão ficava na tela e só o servidor recusava. No `otc.scss` §6b o
  `!important` vai só na GEOMETRIA, e o par `.btn-row-x.d-none` (0,2,0) garante
  os dois lados; página nova não escreve nada.
  **O Edit da linha SEMPRE abre um MODAL** (regra da mesa, 28/09/2026, §572):
  nunca `<input>` nas células com Save/Cancel na coluna Actions. O modal é o
  padrão `liquid-glass`, traz TODOS os campos editáveis (inclusive os de
  coluna oculta) e manda ao servidor só o que MUDOU. As três recompras
  (catálogo, NDF FX, Intrag Unwind) editavam na linha. `check_edit_modal.py`
  reprova página com Edit sem modal e o par `btn-row-save`/`btn-row-cancel`.
- **Toolbar** `mb-3` (o DataTables come a margem do irmão), `.btn-toolbar-all`;
  cores por função: Columns soft-primary, Add Row primary, Export info
  (**Copy · CSV · Excel · Print · PDF**, DataTables Buttons; CSV `;` + BOM;
  Excel exige o registro síncrono do JSZip), Import teal `#4a849b`,
  Mapping/refresh success, Clear Filters outline-secondary. **O teal do Import
  e o ícone do campo de data moram no `otc.scss`**, não copiados no
  `<style>` de cada página: eram iguais em seis e faltavam na sétima, que saiu
  com o Import laranja e a data sem ícone (§490). A classe é
  `.btn-toolbar-import`; o ícone vale por `.otc-datefield` E por `#apiRefDate`
  (com o `altInput` do flatpickr o campo visível herda a classe, não o id). Export termina no
  **Advanced Export** (`otcExportAdvanced('#t', { daily: '<endpoint que a
  própria página consulta>' })`, `exact=1` + confere `source_date`, dia sem
  arquivo é pulado, teto 60 s/dia — §304). **Export próprio não existe**: um
  CSV escrito à mão diverge do resto do app no primeiro acento (§461). A
  exceção é o `/mapping`: a grade é DataTable (o funil vem sozinho; cada
  cadastro tem colunas próprias, então trocar de cadastro RECONSTRÓI a tabela e
  salvar só troca as linhas, mantendo filtro e página), mas o Export segue o
  próprio — o da casa sem o Advanced (cadastro não tem dia), sobre as linhas
  que a grade mostra, Excel pelo SheetJS com toda célula como TEXTO e sem trim
  e PDF pelo pdfmake, carregados só no clique (§556). Célula
  editável sai pelo VALUE do campo, num `format.body` (o texto de um `<input>`
  é vazio, e a coluna sairia em branco) — modelo em `formatExportData`.
  **O nome do arquivo é UM padrão: `<Página ou tabela> - OTC Tracker - OTC
  Processing System`** (mesa, 21/10/2026, §664) — `Reference Data - OTC
  Tracker - OTC Processing System.xlsx`, no /mapping o CADASTRO (`API-Bob
  Reports Links - …`), sem data. Quem decide é o `export-advanced.js`
  (`patchNames`): ele embrulha os cinco botões (Copy, CSV, Excel, Print, PDF)
  no clique e põe o mesmo texto como TÍTULO dentro do arquivo (linha 1 do
  Excel, topo do PDF/Print). A PÁGINA é o `{% block title %}` (o `<title>`
  antes do " | ", em inglês — o `<h4>` é traduzido; travessão vira espaço), e
  por isso página que exporta TEM o bloco. A TABELA é o `data-export-name` do
  `<table>` — página com mais de uma o declara em cada uma (Summaries, Index B3
  Results, Intrag DCE Swap, Accrual/MtM por LOB); o `name` do
  `otcExportAdvanced` escreve nele. **Página não escreve `title`/`filename`
  em botão de export** (seria ignorado); export que não é do Buttons (o
  /mapping, o CSV da Recon FXO) chama `otcExportName`/`otcExportTitle`, e o CSV
  gerado no servidor (bases das Tools, My Tasks) usa o mesmo sufixo. A barra
  vira hífen no NOME e fica no título. `check_export_padrao.py` §3 (estático) e
  `check_export_name.py` (executa o export no Chromium). O mesmo guarda prende,
  no estilo do `check_modal_standard`, a LISTA de quem está fora do menu (quinze
  telas com o menu pela metade, o `reconciliation-fxo` com Csv/Copy próprios),
  que não pode crescer.
- **Alinhamento com `scrollX` são TRÊS coisas**: `columns.adjust()` depois de
  todo draw (+ passe atrasado 150 ms + `resize`); `autoWidth: true`; regras de
  `th` repetidas nos clones com `white-space: normal`.
- **Título do cabeçalho centrado sobre a COLUNA, não sobre a sobra** (§603):
  no flex `título · funil · ordenação` do DataTables 2 o título centrava no
  espaço que sobrava, ~20px à esquerda do corpo. O `excel-filter.js`
  (`centerTitles`/`centerAndAdjust`) reserva à ESQUERDA do título a largura do
  que está à direita dele e pede o `columns.adjust` — alargar só o th (o
  `widenTruncated`) deixava cabeçalho e corpo com larguras diferentes. Só no th
  centralizado; página que trava o th (`nowrap` + `min-width`) limita o respiro
  por `data-oxf-cap`. Página nova não escreve nada, e não centraliza à mão.
- **Seleção de célula em TODA tabela, SOZINHA** (mesa, 30/09/2026, §600): o
  `table-std.js` é carregado pelo `base.html` depois dos scripts da página e se
  liga a toda DataTable pelo `init.dt`, como o funil — página nova não escreve
  nada. Fica de fora a tabela com a extensão `select` por célula (New Deals,
  Intrag, recompras: seleção e Ctrl+C próprios) e a marcada
  `data-cell-copy="off"`; o `otcCellCopy('#id', { skip: [...] })` da página
  segue valendo para excluir colunas. O visual é UM: contorno azul de 2px (a
  célula da extensão `select` também, pelo mesmo `<style>`). O Ctrl+C é um
  listener só e copia a tabela do ÚLTIMO clique; com o foco num campo, o
  Ctrl+C/Ctrl+V é do campo. **O Ctrl+C das páginas com `select` e sem handler
  próprio é o do `clipboard.js`**, e ele percorre as tabelas pelo NÓ: no
  DataTables 2 o `tables({api:true})` não tem `.every()`, e era um `TypeError`
  que deixava Intrag, Swap Bullet/Cashflow e as recompras sem copiar nada.
- **O checkbox de "select all" do cabeçalho é clicável em toda tabela** (§668):
  coluna sem ordenação não desenha o `span.dt-column-order` (12px vazios, que o
  funil ainda reservava à esquerda), e o título com um campo dentro não encolhe
  abaixo dele (`otc.scss`). Num `<th>` de 50px o título ia a 0px e o span
  ficava POR CIMA do checkbox — o clique caía nele, e a Intrag (NDF, Option,
  Swap, DCE NDF/Option) não marcava nada. Página nova não escreve nada;
  `check_table_center.py` §4.
- **Números** `#,##0.00` com `tabular-nums`; taxa NÃO é valor (Strike fica com
  as casas que tem); formatação só no `display`, sort pelo cru.
- **A pílula de STATUS é uma só: texto BRANCO e em Proper** (mesa, 21/10/2026,
  §649). A tela marca o badge com `otc-status` e segue escolhendo o TOM pela
  classe de sempre (`text-bg-*`, `bg-*`, `bg-*-subtle`, `badge-soft-*`); o
  tema (`otc.scss` §6d) o pinta CHEIO, com o texto branco, e o `otc.js` (§9c)
  reescreve o texto pela regra do PROPER do Excel — maiúscula a letra depois
  de não-letra, minúscula a depois de letra: "SENT" → "Sent", "Pending OTC" →
  "Pending Otc", "Unmatched B3" fica —, inclusive no que chega depois (redraw,
  tradução). O DADO não muda: o funil e o export (o `Buttons.stripData`
  embrulhado no `export-advanced.js`) passam pela mesma `otcProperize`, para
  a lista e o arquivo dizerem o que a célula diz. Badge que não é status
  (contagem, produto, LOB, moeda, papel, prioridade, aviso) fica SEM a marca —
  "NDF" não pode virar "Ndf". Função de status nova sem a marca: o
  `check_status_pill.py` recusa.
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
  (some junto, em `Sent`). **As colunas têm largura FIXA** (§698): Bloco 150px
  e Campo 280px quebrando dentro dela, Formato no conteúdo, Valor com a sobra —
  com o layout automático e o Bloco sem quebra, o título de bloco de 98
  caracteres do 0301 de fluxo não constante levava metade da tabela.
  `check_file_preview_buttons.py`.
- **As telas de SWAP são CARDS, não tabela** (mesa, 21/10/2026, §650): Bullet,
  Cashflow e Cetes mostram uma operação por card (`static/js/deal-cards.js` +
  `otc.scss` §6e `.otc-deal-card`) — caixa de seleção, status, os números, os
  quatro botões de linha da casa pelo status, Select all, duplo clique =
  preview. O componente só DESENHA: a página segue dona dos dados e das
  ações, e a **DataTable fica por baixo, escondida, como a fonte do Export da
  casa** (some só `.nd-table-area`/`.nd-table-foot`). Um card por OPERAÇÃO (a
  chave interna). No catálogo é a flag `cards` com `title`/`subtitle`/`facts`/
  `meta`/`lob`; NDF e Opções seguem em tabela. **Deal e B3 ID são os dois
  PRIMEIROS fatos, à vista mesmo em branco (`—`)** — no pé, que só mostra o que
  tem valor, sumiam justamente quando faltavam (§655). A **pílula da LOB**
  (`lob: fn(e)`, CEM teal × EDG roxo, `.otc-deal-card__lob`) é SUAVE e sem a
  marca `otc-status`: não é status, e o Proper a leria "Cem". **O Edit do card
  edita o Trade Date** (§656): ele vai em `changes`, o `trade_date` do payload
  segue sendo o dia ATUAL (por onde a linha é achada), e o `edit` dos três
  backends a MUDA de arquivo-dia (`persistence.move_day`: destino primeiro;
  em branco fica o anterior). `check_swap_edit_dates.py`.
- **A linha da Intrag Swap mora no dia do TRADE DATE, não da Data Início**
  (mesa, 21/10/2026, §656): os dois pontos que a gravam (o B2B do
  Bullet/Cashflow no `swap_new_deals.b3_mapped`, a Cetes) passam o Trade Date.
  A Data Início é COLUNA da linha — na Cetes é o Effective, em geral futuro, e
  no dia dele a linha "não fluía" para a Intrag no dia do mapping. A página
  pesquisa pelo chip **Trade Date** (o dia do arquivo; a Data Início virou
  filtro de coluna) e a API devolve esse dia em `_day`, que Edit, Approve,
  Delete e Send mandam de volta (`dayOf` na página) — nunca a coluna Data
  Início. O Send agrupa um arquivo `Intrag-Swap-AAAAMMDD` por esse dia.
- **Autocomplete nunca é `<datalist>`**: dropdown próprio abaixo do campo, mesma
  largura, `max-height` ~220px, item por `mousedown` (antes do `blur`),
  reemitindo `input`/`change` (`mapAttachDrop`, `.ar-ac-drop`).
- **Data é SEMPRE `dd/mm/aaaa` e `<input type="date">` é proibido** (o nativo
  desenha no locale do sistema — `mm/dd` no Windows do JP — e o calendário do
  SISTEMA não aceita o Today nem acompanha a digitação; as recons e a Reference
  Data que o usavam invisível viraram flatpickr em 22/10/2026, §675). flatpickr
  com `altInput` (`otcDateField`/`otcDateSync` do `export-advanced.js`; quem
  escreve por código chama `el._flatpickr.setDate`; largura em CLASSE porque o
  `style=` fica no campo escondido; ícone como background SVG embutido) ou
  daterangepicker `singlePicker` `DD/MM/YYYY`. **O comportamento é de TODO
  datepicker e mora no `static/js/date-std.js`** (mesa, 22/10/2026, §675),
  carregado pelo `footer-scripts.html` em toda página ANTES dos scripts dela:
  ele embrulha o `flatpickr` na criação e reconhece os dois plugins na
  primeira interação e numa varredura depois da carga — página nova não escreve
  nada. O **botão TODAY** no pé dos dois calendários é dele (estilo
  `.otc-dp-foot`/`.otc-dp-today` no tema). **E o campo se DIGITA: só os
  NÚMEROS, as barras se escrevem sozinhas** (mesa, 22/09/2026; `otcDateMask`,
  no campo que se VÊ — o altInput, ou o próprio input no flatpickr direto). No
  flatpickr SEM altInput o `setDate` dispara um `input` no mesmo campo, e a
  máscara tem uma trava contra o laço. Sem ela o parse frouxo do flatpickr lê `2208/2026` como uma data
  QUALQUER, sem erro nenhum. A data INTEIRA vai ao picker na hora
  (`setDate`) — o código em volta lê o ISO do input original, e ele só nasceria
  no blur: clicar direto no botão exportaria o intervalo anterior. O clique
  SELECIONA a data inteira, e o calendário ACOMPANHA a digitação (dia e mês →
  vai ao mês; data inteira e real → marca); `31/02` e texto pela metade voltam
  à última data válida ao sair do campo — o parse frouxo do flatpickr os lia
  como outra data (§636). A mesma regra da Quotes (§508) mora aqui no HELPER,
  não na página. **O input ORIGINAL guarda ISO** (`dateFormat: 'Y-m-d'`): campo
  que nasce com `dd/mm/aaaa` no `value` não vira data no picker — era o Trade
  Date do Edit dos swaps. E o altInput HERDA a classe do original: página que
  liga o helper por classe depois de montar parte do formulário pegava também
  os campos visíveis, e cada um virava um SEGUNDO picker que relia a data como
  ISO (o cronograma do Cashflow mostrava 01/01/2026) — o helper hoje recusa
  campo que já é altInput (`_otcMask`, §656).
  `check_export_padrao.py` §5, `check_swap_edit_dates.py`.

### Layout e vidro

- **CSS de PLUGIN (daterangepicker, flatpickr) vai no `{% block extra_css %}`**,
  antes do `otc.css` (§701): carregado no fim da página ele vence o tema, e o
  calendário sai branco com o texto claro no escuro (era o Pay/Rec).
  `check_theme_toggle.py` recusa.
- **O `<style>` da página carrega ANTES do `otc.css`** — é a regra que explica
  quase todo "minha regra não pegou". Regra da tela precisa de peso de id ou
  de classe (`#ops-page .x`) para vencer componente do tema; e o tema, ao
  contrário, escreve as regras genéricas de widget com peso ZERO
  (`:where(.content-page) :where(...)`) para a tela sempre vencer. Peso zero
  perde até para seletor de ELEMENTO do Bootstrap (o `font-size` do `h3`):
  título de widget no tema leva peso (0,1,0) de propósito.
- **O que a tela pode usar em vez de CSS próprio** (todos no `otc.scss`):
  `.page-title-head` (título grande + `.otc-page-sub`), `.otc-page-bar` com
  `.otc-stats`/`.otc-stat` (`__label`/`__value`: o número conta e pisca
  sozinho) e `.otc-page-actions`, `.otc-legend`, `.otc-count`, `.otc-chip`
  (`--chip`), `.otc-banner` (caixa de aviso), `.otc-mini-table(-wrap)` (tabela
  montada em JS, Swal/preview), `.otc-icon-tile` (ícone em gradiente com
  glifo branco, `--hue`), `.nd-deal-card`, `.btn-chip`, badges
  `bg-*-subtle`/`badge-soft-*`, segmento `nav-pills` com `data-otc-seg` (a
  lente desliza pelo `otc.js`). O cabeçalho dos widgets de número
  (`x-widget__head` · `__icon` · `__title`) é do tema: a tela declara só o que
  difere (ícone de 40px, título em caixa alta, margem).
- **O ladrilho de ícone ao lado do título é AUTOMÁTICO**: o `layouts/vertical.html`
  copia para o `.page-title-head` o ícone da tela no menu lateral (item de
  submenu sem ícone herda o do grupo; fora do menu, o do menu do usuário),
  num script síncrono logo depois do conteúdo — no `otc.js` o título já teria
  sido pintado e pularia. Tela nova não escreve nada; tela que desenha o
  próprio (`-product-icon`, `<i class="ti">` no h4) fica com o dela.
- **A mesma página em DOIS lugares do menu: um DONO, o resto é atalho com
  `data-nav-alias`** (mesa, 21/10/2026, §654). O menu (`otc.js`,
  `findActive`) acendia a PRIMEIRA folha com o endereço — Intrag › DCE ›
  Option abria New Deals › DCE › Option. Hoje acende o item CLICADO (lembrado
  na aba, `__OTC_NAV_PICK__`) e, aberta por favorito ou link, o dono; o
  ladrilho do título também procura o dono. Link novo que repete um endereço
  do menu leva a marca, senão o `check_nav_alias.py` recusa.
- **Tabela em painel PRÓPRIO (fora de `.card`) tinha o topo do cabeçalho
  CORTADO** (§486): o `.table-responsive` (`overflow:auto`) cortava o checkbox
  e a primeira linha do rótulo. Está resolvido NA RAIZ, no `otc.scss` §7
  (`.table-responsive > .dt-container { margin-top: 0 }` + respiro em
  `margin-top`) — tela nova não escreve nada, e **não se conserta com
  `padding-top` na página** (padding fica dentro da área que rola, §49).
- **Não use `.card` para widget seu**: `<div>` com classe própria
  (`.ndm-card`, `.fxo-widget`). A família `-widget/-panel/-tile` (classe que
  TERMINA assim, sem `__`) já é placa de vidro pelo seletor estrutural do
  `otc.scss` §10a; cartão com gradiente vai no tema. **No Pane card não sobe
  no hover** — `translateY` de hover, `backdrop-filter`, sombra, borda e raio
  de card na página são resto do tema antigo e saem.
- **Estado visual de widget seu (`is-ok`/`is-check`) leva PREFIXO DE ID**
  (`#ops-page .ops-recon.is-ok`, como o `#ndm-page` do Intraday Monitor) —
  §464, e o `check_summary_glow.py` cobra. O seletor estrutural do tema hoje
  tem peso zero, mas o prefixo é o que mantém o estado acima de qualquer
  componente do tema que carregue depois. Medir o `box-shadow` computado
  exige esperar a `transition` do tema (~0,3 s): lido na hora, ele devolve a
  cor ANTIGA no meio da animação e a sonda mente.
- **`backdrop-filter` cria contexto de empilhamento**: `z-index` vai no
  WRAPPER, nunca no menu; o `.wrapper` fica sem `z-index`.
- **Filho de placa NUNCA ganha `z-index`** (§637): a borda de luz e o brilho
  da placa ficam em `z-index: -1` (ela é `isolation: isolate`), e o conteúdo
  fica por cima sem camada própria. Com `> * { z-index: 1 }` o header do card
  virava camada fechada e o menu aberto nele (Export, Columns) ia para BAIXO
  da tabela do body. E cartão com menu não leva `overflow: hidden` — corta o
  menu na borda. `check_dropdown_layers.py`.
- **Dentro de uma raiz de backdrop o desfoque do filho não amostra nada**:
  dropdown dentro de card tem fundo SÓLIDO; modal/offcanvas/toast/Swal pendem do
  `<body>`.
- **Regra de brilho alcança as DUAS famílias de seletor** (estrutural
  `[class*="-widget"]` e as quinze classes próprias), calibrada por tipo de
  superfície.
- **Movimento é um SISTEMA** (`otc.scss` §2/§4): duração e curva só por
  token (`--otc-dur-fast/base/spring/enter/exit`, `--otc-ease`,
  `--otc-ease-out`, `--otc-spring`); entra com ease-out, sai mais curto. O
  tema faz a ENTRADA de toda placa e o "afundar" de gel dos botões (`otc.js`)
  — animação de entrada própria na página (`@keyframes …fade/rise`) é resto e
  sai. Menu e tooltip são do Popper (`transform` inline): anima-se
  `scale`/`translate` INDIVIDUAIS, nunca `transform`. Modal entra como gota
  **sem escala** (§6h) — o `shown.bs.modal` dispara durante a entrada e escala
  muda a largura que o DataTables mede. Saída do Swal tem keyframe PRÓPRIO
  (`otc-swal-out`): mesmo nome com `reverse` não reinicia e o popup não fecha.
- **O Send é o "Contrail"** (`otc.scss` §6c + `otc.js`), a animação do VÍDEO
  de referência (`memory: referencia-visual-pane`, §644): no clique o rótulo
  some e o avião vai na PONTA de um preenchimento que avança da esquerda; o
  "Sent" (✓ na linha) só aparece com o resultado lido do JSON; na volta o
  preenchimento recua até um ponto e o rótulo volta. **O botão fica com a COR
  DELE do começo ao fim** (mesa, 20/10/2026, §641/§644): o preenchimento é a cor
  do TEXTO do botão em transparência (clareia o azul), e nada vira verde nem
  vermelho — erro é só o tremor. **O Send EM LOTE da barra também voa** (§642): classe
  `otc-send-batch` no botão — a animação sem a pílula do `.btn-send` —, e
  tela nova com Send em lote a põe; `check_send_contrail.py` varre as telas.
  Não se reimplementa por página.
- **Ícone que gira tem UM ritmo: `--otc-spin-dur` (1,2 s por volta)** — o
  `ti-spin`/`ti-loader*`, o `.is-busy` (refresh ocupado, que vira o ARCO do
  loader: as setas do refresh são anti-horárias), o anel `spinner-border` do
  Bootstrap, o anel do `Swal.showLoading()` (`.swal2-loader`, §694) e o `.otc-spin`, no `otc.scss` (§644, §647). Spinner próprio de
  tela (anel de CSS, svg do Lucide) leva a classe `.otc-spin` — keyframes de
  giro na página o `check_send_contrail` §7 recusa. **O movimento reduzido
  NÃO toca nele** (§647): as máquinas do JP têm as animações do Windows
  desligadas (`prefers-reduced-motion: reduce`), e o `1ms` da seção 11, num
  giro infinito, eram MIL voltas por segundo — o ícone tremendo "para trás",
  que o §644 não alcançou por ter medido só na dev. O que diz "estou
  trabalhando" está na lista `$otc-progress`, fora da regra; o resto roda uma
  vez e para (`animation-iteration-count: 1`). Indicador novo de progresso
  entra na lista. Teste de animação também com `reduced_motion='reduce'`.
- **A aparência vai para o `<html>` ANTES do primeiro paint** (script
  síncrono do `partials/head-css.html`): `data-bs-theme`, `data-accent`,
  `data-wall`, `data-glass` e a classe `is-solid`, lidos de
  `localStorage.__OTC_TRACKER_UI__` (o `__OTCTRACKER_CONFIG__` antigo é
  migrado). O botão sol/lua troca pelo `otcUI.set` e suprime as transições
  (`otc-theme-switching`). `check_theme_toggle.py`.
- **Modo opaco** (`is-solid` no `<html>`, máquina SEM GPU — as do JPM):
  WebGL por software, Firefox no Windows ou o Windows sem "Efeitos de
  transparência" (`prefers-reduced-transparency`, §634) — `decideSolid` do
  `otc.js`, a sonda memoizada em `sessionStorage.__OTC_FX_AUTO__` para o
  `<head>` não piscar vidro; `localStorage.__OTC_TRACKER_FX__` =
  `reduced`/`full` (o switch "Reduce transparency") vence TODOS. **O modo é
  UMA classe**: nada de `@media (prefers-reduced-transparency)` no CSS — era
  ele que deixava tudo sólido nas máquinas do JPM com o switch desligado, e no
  Mac (que não manda o sinal) não se via. Sem blur, alfa não é material:
  superfícies viram cor SÓLIDA (§11 do SCSS); token do modo vai como
  `:root.is-solid` (+ o par escuro). Valide forçando `'reduced'`, e o sinal do
  Windows pelo CDP (`Emulation.setEmulatedMedia`). **O modo opaco é também
  MOVIMENTO leve** (§636): sem View Transition entre páginas, entrada em
  esmaecer curto sem cascata, título parado — por software era o segundo e
  meio de cada troca de página. A refração do vidro exige GPU em QUALQUER modo
  (`weakGpu()`, a mesma sonda) e roda no tempo ocioso. Meça custo de casca com
  o Chrome sem GPU (`--disable-gpu`) e a CPU desacelerada pelo CDP.
- **Card de contagem tem a animação do KPI em TODA tela** (§631): o `otc.js`
  (`initStats`) faz contar e piscar todo `.otc-stat__value`,
  `*-widget__value`, `.acc-stat__value`, `.ob-stat__n` e `.widget-val`, e o
  tema dá o hover. A primeira carga não pisca. **O card de TOTAL é
  preenchido e mais escuro** por uma regra só do tema: tela nova marca o
  card com `otc-stat--total` (ou `x-widget--total`) e não escreve cor.
- **A seção Pinned da barra é só de INICIATIVAS** (§631, "Initiatives
  Pinned" desde §633): `window.otcPins` (`has`/`toggle`/`sync`), chave
  `otc_pinned_projects_<SID>`. Não há mais página fixada nem editor.
- **O aviso de AÇÃO é a pílula preta do Pane** (§632): `window.otcToast(msg,
  { undo })` (otc.js §3d) — "Done: <tarefa>" com Undo, abaixo da barra. Swal
  é para erro e confirmação, não para dizer que algo deu certo.
- **O foco é a ILHA** (`window.otcFocus`, otc.js §3e): estado no localStorage,
  servidor avisado a cada passo (`/api/user-home/focus`). Tela nova que inicia
  foco chama `otcFocus.start`, nunca conta tempo por conta própria.
- **Os FAVORITOS são o botão flutuante** (`window.otcFab`, otc.js §3f, mesa
  21/10/2026, §658): o "AssistiveTouch" do iPad no material da casa — o botão
  de vidro redondo com o "+" (vira "×" aberto), que se ARRASTA para QUALQUER
  lugar e fica onde foi solto (§659; captura no `pointerdown`;
  `__OTC_FAB_POS__` guarda `x`/`y` em FRAÇÃO da área útil da janela), nasce à
  ESQUERDA da barra do topo enquanto não há lugar gravado, e esmaece parado. O
  painel abre abaixo, acima ou ao lado conforme a altura do botão, favorita a
  página atual e lista os favoritos em BLOCOS como o menu lateral (os títulos
  de seção do primeiro nível, na ordem do menu — `menuIndex`; fora do menu,
  "Others"): a lista é do SID no documento da User
  Home (`/api/user-home/favorites`, `domain.clean_favorites`: só caminho deste
  app, sem repetir, até 24) e o navegador guarda uma CÓPIA
  (`otc_favorites_<SID>`) para desenhar sem ir ao share — o servidor é lido
  quando o painel abre. Nome e ícone saem do menu DONO (`pageLeaf`, a regra do
  §654), no idioma de quem vê; o rótulo gravado é só o plano B. Remover tem o
  Undo da pílula (`otcToast`). Fica em 1040: abaixo de modal e offcanvas.
  `check_fab_favorites.py`.
- **O papel de parede é o SVG do Pane** (`partials/wallpaper.html`, cores em
  `--w-*` no otc.scss §2b, sem bolhas). O "leitoso" do claro era ele, não o
  vidro (§632) — antes de mexer em alfa de vidro, MEÇA o pixel atrás da placa.
  **`.otc-wall` é a CAMADA** (fixa em tela cheia); o botão de cada parede na
  gaveta é `.otc-wall-swatch` (§634: com o mesmo nome, os dez botões saíam da
  gaveta e viravam uma faixa no meio da página). **A miniatura de cada parede
  é `data-art="<parede>"` + `background: var(--w-art)`**: a MESMA paleta do
  §2b, no tema atual — gradiente escrito à mão tinha uma versão só e a gaveta
  do claro parecia escura. **São DOIS desenhos no mesmo SVG** (21/10/2026,
  §669): o do Pane (`otc-wall__pane`) e o FLOW (`otc-wall__flow` — Fjord,
  Glacier: fita em serpentina e câmaras em relevo, luz vindo de baixo), e a
  parede escolhe por `--w-pane`/`--w-flow`. A miniatura do flow é um SVG
  embutido gerado pela `otc-flow-art` com as mesmas cores. O desfoque do flow
  é só o halo e o reflexo (`.g`), que o modo opaco tira. **As LISAS são a
  paleta do sistema, uma cor por tom** (mesa, 22/10/2026, §672): Abyss,
  Midnight, Slate e Steel só no tema escuro, Fog e Frost só no claro
  (`WALL_TONE`; a gaveta esconde as do outro tema pelo `data-tone`), e no
  outro tema cada uma vale pela da outra ponta (`WALL_PAIR`, e o CSS define as
  duas versões). A Frost é o `:root` sem `data-wall` (Abyss no escuro), mas a
  PADRÃO de quem nunca escolheu é a **Aurora com o vidro Clear** (26/10/2026:
  `WALL_BASE`/`WALL_DEFAULT` do `otc.js` e o `<head>` dizem o mesmo; quem já
  gravou uma escolha fica com ela). Cor escura no tema claro (e o contrário) apagava o título e o
  breadcrumb, que ficam DIRETO sobre o fundo. Parede RETIRADA entra na lista
  `retiradas` do `head-css.html`, que devolve à padrão quem a tinha gravada.
  Parede nova entra no §2b, na lista `WALLS` e nos três mapas `walls` do
  `settings.js`: o `check_wallpapers.py` cobra os quatro.
- **A casca é presa na BORDA ESQUERDA, sem centralizar** (§634): menu a
  `--otc-inset` (10px) da borda, conteúdo a `--otc-side-gap` (18px) dele
  (`--otc-content-l`, que o desafixar zera para o `--otc-gutter`), barra do
  topo e toasts a `--otc-gutter` da direita. Centrada em 1840px, o menu ficava
  longe da borda numa tela larga e o desafixar (que o recolhe pela própria
  largura) só o encostava nela. **O rodapé é ABSOLUTO no pé da casca**
  (`.content-page` com 100vh no mínimo): fim da janela na tela curta, depois do
  conteúdo na longa — o espaço dele é o `padding-bottom` da casca.
- **Troca de página é View Transition entre documentos** (§632): os nomes da
  barra lateral, do topo e do papel de parede só existem durante a navegação
  (`otc-vt-nav`, posta pelo `pageswap`/`pagereveal` do `head-css.html`, que
  tem de ouvir antes do primeiro paint). O Chromium do Playwright não dispara
  o `pagereveal`: teste a transição com `channel='chrome'`. O menu pré-busca
  o HTML da tela no hover (Speculation Rules) — link de AÇÃO (logout, lock,
  download, API) fica fora da lista.
- Cor só de tema claro precisa do par `[data-bs-theme=dark]`.
- **Caminho em `url()` no `otc.scss` é RELATIVO ao CSS** (`../images/auth.jpg`,
  `../fonts/…`): no Stratos o `otc_stratos.py` põe o prefixo da solução no
  HTML que sai — até no `url(` do `<style>` da página —, não no `.css`. O
  `otc.css` vai como está e a relativa resolve contra o `<link>` dele, que já
  leva o prefixo; um `/static/…` absoluto, que na dev funciona, lá pede o
  arquivo FORA da solução: a tela fica sem a imagem ou a fonte, sem erro
  nenhum, e o `check_stratos.py` não o vê. E regra que morava no `app.css`
  apagado (§630) e não foi trazida para o tema some calada — foi o caso da foto
  das telas de login (`.card-side-img`, §678), cuja imagem nem era pedida.

---

## 8. Armadilhas por domínio (não dão erro nenhum)

### New Deals

- **Contraparte vem do acronym do End Counterparty, nunca do Settlement
  Location** (que é a NOSSA perna). Ordem em `_ndf_ref_by_accronym`: acronym
  exato → sem sufixo → se perna interna, identidade da entidade
  (`_ndf_le_refdata`) → senão o SPN da API → nada (badge *Missing
  Counterparty*, que é a falha desejada). Amend recheca; linha achada por
  `(Deal, Client)`, e só pelo Deal se ele for único no arquivo-dia.
- **Toda gravação das seis telas espera o servidor e pinta o que ELE gravou**
  (§685, `static/js/nd-write.js`): Edit, Confirm, Send, Apply Column e Delete.
  O bulk responde par a par (`done`/`not_found`/`refused`); o PATCH devolve o
  `status` gravado (Edit numa linha Sent/Success segue a régua do Amend:
  econômico → `Amend`, cosmético → fica); o **send-conecta confere status e
  4-olhos no SERVIDOR antes do arquivo e marca `Sent` no mesmo pedido**
  (`status_failed` = o arquivo já foi, não reenviar); o Mapping só apaga o
  retorno que absorveu INTEIRO; o status do Confirm/Send é o DADO da célula —
  o `missing-counterparty.js` troca o badge no DOM. Gravação nova nessas telas
  usa o `otcNdWrite`, nunca `fetch(...).catch(console.warn)`
  (`check_nd_write_ui.py`, `check_nd_write_verdict.py`).
- **A busca (`cache/search`) das telas lê o dia ESTRITO** (§608):
  `_day_files(..., strict=True)` e `_day_json(..., strict=True)` — banco
  ocupado sem cópia em memória ou ilegível SOBE (503 com o motivo, aviso
  `nd-search-*` na tela). O `_day_json` sem `strict` devolvia `[]` calado, e
  a tabela abria vazia com `success: true` logo depois de uma gravação mudar
  o carimbo do dia. Toda falha dele vai para o log (`[daycache]`) e serve a
  última cópia em memória quando há. Busca nova nasce estrita.
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
- **O import do dropzone não decide sozinho se a operação é nova** (§625):
  a grade só tem o que a busca carregou. Linha que ela não acha vai num POST
  com `_import`, e o SERVIDOR procura (`_nd_import_upsert`: Deal + Acronym,
  depois Deal + Client, em todos os dias do produto) e aplica a regra do
  Amend do box scan (B3 ID preservado). Sem isso a mesma operação entrava
  duas vezes — Client reenriquecido ou Trade Date corrigida — ou era
  substituída como `New`, perdendo o B3 ID. POST de cache novo que recebe
  import passa pelo `_import_resposta`.
- **O Mapping B3 ID do New Deals entra em QUALQUER status** (mesa, 02/10/2026,
  §626): a trava de só `Sent`/`Error` saiu dos três JS (NDF Comm, Opt Comm, Opt
  FXO) e do `_generic_nd_mapping_candidates` (FWD Start, Other Publisher; o
  Vanilla já era assim). Ficam fora `Canceled` e `Success` COM B3 ID. Quem o
  retorno não traz só vira `Error` se esperava resposta
  (`_ND_MAPPING_ERRORABLE`, no endpoint) — Approved/Pending ficam como estão.
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
  (a pasta do Inventory é o tipo). O Vanilla ganha `source` de
  confirmação quando a LE é MGT (`_generic_nd_mc_source`) e nasce `Pending
  OTC`; o do BANCO só quando é ASIÁTICO ou BRL FIXED (§703,
  `_generic_nd_vanilla_conf`), no documento do termo de moeda do Banco,
  família `vanilla` (`/confirmation/ndf-fwdstart/vanilla`); o resto do
  Vanilla do Banco segue sem esteira. O FWD Start do BANCO deixou de listar
  os de MGT, e o Generate do Monitor escolhe o editor pela Legal Entity.
  **O ID é UMA regra** (equipe, 27/10/2026, §703) no Pending, na esteira, no
  Nº e no FepWeb ID: FWD Start e swaps pelo B3 ID; Vanilla, FXO, NDF e opção
  de commodities pelo Deal. Quem a diz é o `_mc_conf_trade_keys` (por deal,
  `_conf_src`) e o `_conf_num_field` — Save novo grava o FepWeb ID por ele,
  nunca por `d.get('Deal')` (o FWD Start ficava sem o FepWeb ID).
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
- **A taxa do XML do termo de moeda é `Strike` OU `Rate`** (§563, #OTC-0042):
  o FWD Start grava `Strike`, o Vanilla só `Rate`; lendo só o `Strike`, o XML da
  MGT saía zerado. E o vencimento do XML é lido antes de qualquer perna ser
  recusada.
- **`valor`/`valorEstrangeiro` do XML têm TRÊS regras, uma por documento**
  (§593, `legs_fn` do `_conf_ndf_xml`): **FXO** → `TotalNotional` e
  `TotalNotional × Strike` (`_conf_fxo_legs`); **MGT × cliente** (Vanilla e FWD
  Start de MGT) → `Notional` e `Notional × Rate`, sempre (`_conf_mgt_fx_legs`);
  **FWD Start do BANCO** → o `_conf_fx_legs`, que DIVIDE pela taxa quando o
  notional vem em BRL (mesa: "fwd start é diferente"). Não unifique: mexer no
  `_conf_fx_legs` leva o Banco junto. **No FXO e no NDF Vanilla de MGT, com
  várias operações no documento** (mesa, 23/10/2026, §682): o par
  `valor`/`valorEstrangeiro` é o da operação de MAIOR valor em BRL, não a soma
  (`valor_do_maior`); a `dataVencimento` é a mais distante; e o
  `numeroContrato` leva o acronym — `FXO_<AAAAMMDD>_<moeda>_<acronym>`,
  `NDF_<AAAAMMDD>_<moeda>_<acronym>` —, senão dois clientes no mesmo dia e
  moeda davam o mesmo contrato no FepWeb. Os outros documentos seguem somando
  e com o número sem acronym.
- **O prêmio D0 das páginas de opção é uma FAIXA, não um Swal** (§565,
  `premium-d0.js`): contada da grade a cada draw, por qualquer caminho de
  entrada; o box scan também toca o sino.
- Só produtos de `_MC_CONFIRMATION_SOURCES` geram documento na esteira;
  `_mc_save_from_deal` é chamado de dentro de `_pc_save_from_deal` e **não
  retroage** — quem recupera o passado é o `backfill_manual_confirmations.py`,
  e **produto novo na lista exige família nova lá** (`check_mc_backfill.py`
  prende a paridade). Sem ela as operações NOVAS entram na esteira e as
  ANTIGAS ficam invisíveis para sempre no Confirmations Monitor, sem erro
  nenhum — foi o que aconteceu com o `NDF VANILLA` de MGT. Mercadoria e FXO são
  sempre JPM (`_MC_JPM_SOURCES`); razão social do `le-spn`.
- **As colunas do Confirmations Monitor descem até o pé da janela** (§701), com
  a folga do sidenav (`--otc-inset`), medida pelo JS (`fitCards`) a partir do
  topo do CARD — medida na `.row g-3`, sobrava o gutter.
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
- **O Monitor é o INTRADAY MONITOR** (`/intraday-monitor`, Intraday › Monitor;
  §567, §631): as tarefas do dia em cima (catálogo `domain.TASKS`, agenda de dias e
  horário limite no card `intradaytasks` do Control Panel), o detalhe produto ×
  status embaixo. Recon conclui ao RODAR no dia, zona com ZERO em aberto (a
  regra do aviso das 19h, `queries._fechados`). **Zona sem nada importado no
  dia não é tarefa** (equipe, 27/10/2026, §705): como a Branch Reversal, só
  EXISTE com movimento (`due` e `conditional`) — ia para Completed com
  "Nothing imported" e poluía o quadro. Quem diz que a recon rodou é o
  **registro de execuções** (`platform/task_runs.record`, chamado no `run` de
  cada recon): recon nova que vira tarefa grava lá, senão o cartão nunca fecha.
  **A Intrag conta desde o import** como `Awaiting B3 ID`
  (`domain.intrag_destino`, a MESMA regra dos pontos que gravam o espelho —
  mudou lá, muda aqui). `/new-deals-monitor` redireciona e vale na allowlist.
  **Recon NOVA entra no catálogo `domain.TASKS` e grava `task_runs.record` no
  `run`** (regra da mesa; o §4d do teste varre o `url_map` e reprova recon de
  fora). O Pay/Rec só conclui no End process (`done_on: 'end'`); a Branch
  Reversal é tarefa condicional. **As rotinas do Control Panel também são tarefas** (tipo
  `routine`, §577): Save CETIP Files (diária, grava no Save com arquivo salvo;
  sem registro — instância de outra pessoa com código velho — fecha pelo aviso
  `CETIP Files Saved` do dia no sino, `_cetip_saved_notif`) e
  Confirmations Escalation (segunda e quinta, grava quando o PACOTE da rotina
  sai sem erro, pelo Run do card ou pelo automático como `Automatic`). **Swap Accrual e Swap MtM são tarefas
  MENSAIS** (`month` no catálogo, `domain.janela_mensal`, mesa 30/09/2026):
  Accrual no último dia útil ANBIMA, MtM ATÉ o 4º (uma vez; prazo no fim da janela);
  rodar a recon é 50%, conclui no End process (`task_runs` `event='end'`), que
  no MtM vale em qualquer dia da janela. **Mensal não tem dia da semana**
  (§611): no Control Panel a linha é UMA pílula com a regra, que só liga ou
  desliga, e quem diz o dia devido é a janela — os `days` salvos não filtram.
  O aviso das 19h é DAQUI (`_intraday_pending`)
  e se configura no card `intradaytasks` (o `dealsmonitor` saiu). O card de D-1
  aponta cada pendência com a data no link (`static/js/deep-link.js`:
  `?tradedate=`/`?date=`) — página que vira destino lê `otcLinkDmy()`/
  `otcLinkIso()`. Teste não grava no registro (`task_runs._em_teste`).
  **Owner e backup por tarefa × produto × LE** (§701/§703, botão Owners;
  edita o BO e o admin): `control-panel/intraday_assignments.json` pelo
  `domain.clean_assignments`; o produto só nas três tarefas de zona
  (`domain.assign_products`: os cards da zona; card de confirmação novo entra
  no `ASSIGN_CONF_PRODUCTS`), e só BO/ADMIN/master são designáveis. Quem é
  designado agora é avisado no SEU sino (página `Intraday Monitor`).
  `check_intraday_monitor.py`, `check_intraday_owners.py`.
- **O Monitor não recebe lista de produto: ele VARRE o `cache/new deals/`**
  e agrupa pelos dois primeiros níveis não numéricos do caminho (§454). Quem
  diz que um produto EXISTE é o `_NDM_CARDS` (`deals_monitor/domain.py`); o
  pkey sem card vira o genérico `extra-<pkey>`, que desenha no grupo *Others*
  do rodapé, sem link de página, e cuja chave **não começa com `intrag-`** —
  então o e-mail de pendências o classifica como **Registration** (o único
  teste de zona é o prefixo da chave). Foi o que aconteceu com as duas telas
  de DCE, que gravam dia no mesmo cache desde sempre. Card novo mexe em
  `_NDM_CARDS`, `_NDM_TAXONOMY` e nos `GROUPS` do
  `intraday-monitor.html`; **o front nunca fabrica card** (o `intrag-swap`
  nascia de um placeholder no JS e o mesmo produto aparecia duas vezes na
  tela). `les` só se a entidade sair mesmo do portfolio code — sem a chave, o
  card não desenha subitem, em vez de desenhar um LAW/ATA inventado.
  **A varredura aceita MAIS DE UMA RAIZ** (§491): árvore fora do
  `cache/new deals/` entra com o pkey PREFIXADO (`PREFIXO_UNWIND`), senão um
  `NDF/FX` de lá soma no mesmo card de um `NDF/FX` daqui. E **o card pode
  declarar onde FECHA** (`done`): quem não fecha em `Success` — a recompra
  fecha em `Sent` ou, com o retorno da B3 mapeado, `Success` (§582) — ficaria
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
  **Intrag Swap** (visão da ATACAMA, carteira INTRAGJP633, arquivo-dia do
  TRADE DATE — §656, abaixo —, 36 campos = `ENTRY_FIELDS` da página); contra cliente o
  **Pending Confirmation + esteira** pela porta de sempre
  (`_pc_save_from_deal`), Produto `SWAP` com Opção de Arrependimento e
  `SWAP CORPORATE` sem, chave = B3 ID, LOB do deal (EDG), ativo = curva
  VCP. A confirmação (`/confirmation/swap-edg/opcao-arrependimento`, um
  documento por operação) lê o **Cupom Limpo**: `Close dd-mmm-aa` busca o
  fechamento em Quotes (símbolo do `quotes-equity` pelo rótulo da curva) e
  o Strike é o % sobre ele; `Spot` deixa Preço Inicial e Strike em BRANCO e
  obrigatórios. XML só com o valor em BRL. Platform lê os deals do dia por
  `routes._swap_bullet_engine()` (platform não importa feature).
  **Linha com B3 ID é `Success`, e fica** (§554): editar outro campo ou
  reimportar o DT substituindo não a devolve a Pending/Amend — era assim que
  ela chegava a `Approved` COM o B3 ID. **O Mapping B3 ID lê o retorno da
  B3** (`RETURN_PATH`, botão verde da toolbar, `/mapping-b3`): o retorno
  ecoa o 0301 depois do 4º `;`, e o casamento é pelo **Meu Número** (pos.
  11-20; `MyNumber` na visão cliente/banco, `MyNumberMirror` na do Atacama),
  com conta do cliente + datas + valor base como plano B só com candidato
  único (`platform/swap_deal_ticket.parse_return_line`/`match_return`). Eco
  com outro status → `Error` com o texto da B3 (`MappingError`); `Sent` sem
  retorno → `Error`; B3 ID com status atrasado → curado para `Success`. O
  arquivo de retorno só é apagado quando TODAS as linhas de swap dele
  casaram: o Swap Cashflow também registra 0301.
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
- **Swap Cetes** (`features/swap_cetes/`, §650): o `#N cetip usd irs` do e-mail
  das Cetes (Banco × Lawton) → o 0301 na **versão 1** do layout
  (`swap-pagamento-final`, header 38 + registro 1899 — não o v3 do Bullet),
  nas visões do Banco e do Lawton, byte a byte com o arquivo da mesa. A Parte
  leva a curva que RECEBE; o **Valor Base é em REAIS** (USD notional × fx rate
  for reference); o mesmo Meu Número nas duas visões. Página do catálogo em
  cards, com o **Mapping B3 ID** (`mapping`) e sem Econ. Affirmation; no
  Success, a **Intrag Swap na visão do LAWTON** (INTRAGJP552). A Cetes é **SEMPRE CEM** (`domain.LOB`: fora do `EDITABLE`, o
  `refresh` a repõe), e o card diz Party = Banco e Counterparty = Lawton. O que cada
  perna é na B3 é o cadastro `swap-cetes-leg`. **No `.msg` do Outlook o bloco
  chega uma CÉLULA por linha** (§652): a tabela põe um `<p class=MsoNormal>`
  dentro de cada `<td>`, e o `html_to_lines` quebra em cada parágrafo — `#9`,
  `cetip usd irs`, `booking:`, `F Talioli`. O `domain.blocks` lê as duas
  formas; o `html_to_lines` NÃO foi mudado (o Trade Recap do Swap Cashflow
  depende do parágrafo por linha). Corpo em texto puro se quebra no
  `email_reader`, nunca no `html_to_lines` (qualquer `<mailto:…>` o faria ler
  como HTML e juntar tudo numa linha). `check_swap_cetes.py`.
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
  **No 0034 o Sinal/Taxa de Juros de cada ponta é o da curva dela no 0301**
  (P1 = a ponta da menor conta), e **a termo** o campo 22 é o FX inicial com
  qualquer índice, toda curva (a VCP inclusive, ao contrário do Bullet) leva
  Sinal/Juros, e o Cupom Limpo vai em branco mas a Data de Cotação VAI — sem a
  coluna, o D-n do termo (§700). `check_swap_cashflow.py`.
- **O B2B do swap é × o FUNDO da LOB: EDG × Atacama, CEM × Lawton** (equipe,
  26/10/2026, §699). `swap_deal_ticket.B2B_FUNDS`/`b2b_fund`/`set_pair`: a LE
  da linha (ATACAMA/LAWTON) diz o fundo, as visões são `bank` + `atacama` ou
  `lawton` (arquivos `…_LAWTON.txt`, a conta e o participante do fundo no
  `b3-accounts`) e a Intrag Swap vai na carteira dele (INTRAGJP633 ×
  INTRAGJP552). `le_pair(view, deal)`: a visão do Banco é contra o fundo do
  DEAL — chamador que não passa o deal cai na Atacama. O card do deal contra
  cliente (Bullet e Cashflow) tem o **Create B2B** (`static/js/swap-deal.js`,
  `otcSwapB2B`): as pernas A e B trocadas campo a campo (`CurveA…` ↔
  `CurveB…`), LE/Client = o fundo, o pagador do prêmio invertido, sem Deal/B3
  ID/SPN/conta, e o modal de Add aberto para editar; sem LOB não há B2B. A
  guarda-chuva de cliente sem conta própria é a **CLIENT 1** (73760.10-2), e o
  preview/Send releem a do cadastro (`with_current_omnibus`). Nas telas de swap
  o botão é **Add Deal**; a curva do card diz o spread (`otcSwapCurveText`:
  "CDI + 3.00%") e o Type sai no idioma da tela (`otcSwapTypeLabel`). **O modal dos swaps formata** (`otcSwapModalPrep`, §700):
  valores `#,##0.00`, FX Start com 8 casas, CNPJ mascarado e os holders pela
  CONTA B3 (só leitura — o texto do DT segue gravado, o e-mail o lê); o Save
  devolve o dado cru, e o que só mudou de formato volta como estava. E **em
  BLOCOS** (`otcSwapModalLayout`, §701): campo que nenhum bloco nomeia vai para
  "Other", nunca some. **O card tem as MARCAS** (Bullet e Cashflow, §701):
  Forward Start, Atualização de Notional, Curva VCP e Prêmio, detectadas pelos
  campos (`otcSwapFlags`) e corrigíveis com um clique — só a correção é gravada
  (`SwapFlags`, `<api>/flags`, sem mexer no status, preservada no reimport), e
  ela NÃO muda o arquivo da B3. **O Economic Affirmation leva também a operação
  MARCADA** (a linha ou o card, `_selected`), não-IF e em qualquer data; sem
  marcada, só as IF do dia. A Opt FXO não tem a rota do Economic Affirmation.
- **O swap da CEM chega no CORPO do "Internal Trade Recap", não em planilha**
  (mesa, 24/09/2026, §555). O corpo é PARÁGRAFO do Outlook (`<p
  class=MsoNormal>`), não tabela — a única `<table>` é a do AFR, e era ela que
  o import lia e recusava. O leitor (`swap_deal_ticket.html_to_lines` →
  `parse_trade_recap`) separa o e-mail em SEÇÕES numeradas (`I)`, `II)`…) sob
  a linha `<Cliente> SPN : n`; **toda** seção numerada abre uma nova, senão as
  linhas do TRS se somariam ao swap de cima. **Só `Onshore … Swap` é
  importada** (`is_onshore_swap`): o e-mail traz o XCCY offshore, o TRS e o
  EPP, que voltam como ignorados. Parte A = a perna que o BANCO recebe (a que
  o cliente PAGA); valor base = o notional em BRL, o da moeda em Notional
  (Foreign Ccy), `Initial FX` em FX Start; `At maturity` = 100% no último
  fluxo. **O recap também chega no formato da Boticario** (§697): seção por
  LETRA (`B) USD/BRL Onshore Cross-currency Swap`), contraparte pelo CNPJ do
  Party B quando não há linha de SPN, `USD Notional:`, a tabela do cronograma
  uma célula por linha (com a coluna de amortização), e o **FX de booking**
  (`FX: 5.40`) que faz o Valor Base = FX × o notional na moeda. O `Initial FX`
  que é uma FIXAÇÃO futura (`PTAX-V 06-Nov-2026`) é a **Atualização de
  Notional**, e o 0301 vai **a termo** (FWD Start): Data da operação (19),
  Índice Termo do cadastro `swap-termo-index` (20, o domínio do layout: 15 =
  DOLAR), 100% (21), D-n ANBIMA da fixação ao início (99) — fixação no próprio
  dia do início vira VCP (00) com PU, Tipo/Classe e Denominação (22-24) — e o
  **Cupom Limpo (47/49) em BRANCO**. **Term SOFR vai como VCP** (C00 pelas
  linhas `nM TERM SFR` do `swap-bullet-curve`, que têm o Tipo/Classe do
  VCP.json na coluna VCP CODE), a fórmula do e-mail na Denominação; ela vai na
  curva VCP do CLIENTE quando ele está na guarda-chuva (a regra da macro).
  **A categoria das pernas sai dos CADASTROS**, nunca de lista no
  código: curva do recap → código B3 (`swap-bullet-curve`) → `Nome Categoria`
  no Swap Index (`swap-index`, pelo código). USD é **TAXAS DE CAMBIO**, código
  220 (mesa, 24/09/2026) — a linha `USD → 220` se cadastra no /mapping.
  **Perna TAXAS DE CAMBIO no 0301**: taxa e sinal nos campos de juros, e a
  cotação inicial no **Cupom Limpo** (47/49, "Curva Moeda ou VCP"), que nasce
  do FX Start; a **Data de Cotação D-n** (48/50) é a coluna `Curve X Quote` e,
  como o recap não a diz, é lacuna (`swc_fx_quote`) — nunca D-1 presumido. A
  LOB também fica em branco (o recap não diz).
- **Swap Calculator: contrato de ESTRATÉGIA puxa as pontas do Live Position ›
  Swap › Strategy** (§602). Na posição as duas curvas são `VCP`; índice, taxa,
  percentual, convenção, cotação inicial, D-n da moeda e lookback só existem na
  consulta da estratégia, e ela VENCE a Denominação (o achado desta fica como
  informação). **A Parte é o `Indicador_2`, não o `_1`** (mesa, 30/09/2026):
  na `Aporte SOFR Flex x ME` (Parte = Banco) vem `_1 = USD`, `_2 = SOFR`, e o
  banco RECEBE o SOFR — lido ao contrário, o resultado saía com o valor certo e
  o SINAL trocado. Quem diz é `swap_strategies.PONTA_PARTE`/`PONTA_CONTRAPARTE`,
  nunca o número solto (o Settlement Advice usa as mesmas). Os campos
  NUMERADOS (`Valor Inicial n`, `Fixing n`) são do INDICADOR n e só servem à
  ponta cujo indicador é a própria moeda — na ponta de SOFR o `Fixing` é o do
  índice (D-1), e a moeda usa os sem número (`Cotação Inicial Moeda`, `Data
  Cotação Moeda Final`). O `_n` do `Lookback da Taxa_n` numera a TAXA
  flutuante: vale o da ponta, senão o ÚNICO; dois diferentes não se chutam.
  Indicador que é código de moeda (`USD`) casa pelo nome do `currency-base`.
  Só a lista importada (sem dados) é lacuna dita (`estrategia`).
- **Swap Calculator: a Denominação diz o PISO do índice e ONDE o
  multiplicador incide** (mesa, 30/09/2026, §599). `[Max(0%, Term SOFR) +
  0,90%]*1.17647` é `(max(0; SOFR) + 0,90%) × k`; `Max 0%, Term SOFR * 1,17647
  + 1,12%` é `max(0; SOFR) × k + 1,12%` — o MESMO k em lugares diferentes, e
  quem diz é a ESTRUTURA do texto (`descricao_curva._base_do_multiplicador`: o
  `*` multiplica um grupo com spread dentro → a soma; colado no índice, ou num
  grupo sem spread → só o índice), nunca um padrão por contrato. Na ponta:
  `Ponta.piso` (só nas com fixing — Term SOFR, EURIBOR) e
  `Ponta.mult_no_indice` (também no SOFR composto); na tela, o campo do piso e
  o seletor "The multiplier applies to", que só aparecem quando existem; na
  memória xlsx, o piso é `MAX(piso; fixing)` como fórmula. O intérprete lê
  também `act360` sem barra e, como informação, frequência, convenção de dia
  útil, calendários e o D-2 do SOFR — para não voltarem como "não entendido".
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
- **NDF Calculator: QUATRO contas, escolhidas pelo tipo do termo** (mesa,
  08/10/2026, §629; `queries.calcular_ndf`). MOEDA com BRL no par: fixing =
  PTAX do vencimento − offset; na ASIÁTICA, a média ARITMÉTICA da PTAX de cada
  data de verificação − offset. MOEDA sem BRL (cross): `nocional × (fix − fwd)
  × PTAX da moeda BASE` (vencimento − offset), e o fixing em branco é a
  paridade base ÷ cotada dos dois boletins do dia. MERCADORIA com strike em
  USD: `qtd × (preço − strike) × PTAX da Data de Fixing da Moeda` — a data
  REAL, sem offset. MERCADORIA com strike em REAIS (`Taxa a Termo em Reais` =
  `S` na posição — é uma FLAG, não um número): a conta é em reais e não leva
  PTAX no fim, mas o preço do Quotes é USD e vai a reais ANTES da diferença,
  pela MÉDIA da PTAX na janela de verificação (a confirmação
  `ndf-comm-strike-brl`). Multiplicar a diferença pela PTAX converteria o strike
  em reais de novo. Média com um dia sem PTAX é erro dizendo QUAL dia. A série
  sai de UMA chamada ao BCB (`cambio.ptax_periodo`), e a memória xlsx escreve
  cada dia com a média por fórmula.
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
- **A OPÇÃO de Commodities também tem e-mail PRÓPRIO** (mesa, 20/10/2026,
  §637; `domain.linhas_do_recap_opcoes_commodities`): o "Trade Recap … Unwind",
  uma tabela por perna, `Client` (facing o cliente) e `Banco` (o B2B Banco ×
  Lawton), SEM B3 ID — o `Contract` dele (`27-Mar`) é o mês do futuro. Cada
  perna casa só com o SEU tipo de contrato (`_leg` × `internal` da posição);
  nome do cliente e datas da opção só DESEMPATAM. Quantidade em unidades (a da
  B3), números do e-mail (prêmio em USD, coluna FX Rate só nesta página), sinal
  do banco (no B2B o contrário da perna Client), pagador = o lançador.
- **A recompra de SWAP da EDG chega no recap do TRS** (mesa, 21/10/2026, §657;
  `domain.linhas_do_recap_swap_trs`, flag `recap: 'swap-trs'` no catálogo): o
  "Internal Recap - <ticker> TRS onshore Unwind (20-Oct-26)" é UMA tabela
  TRANSPOSTA — rótulos na 1ª coluna, uma TRANCHE por coluna (`TOTAL` fora) —, e
  o **CETIP ID é o B3 ID** (a posição se acha por ele). Nocional recomprado =
  **ações × strike original** (o campo 11). As pernas vêm na visão de QUEM o
  rótulo nomeia (`(RDOR Recebe)`/`(RDOR Paga …)`/`(JPM Paga)`): a perna que o
  cliente RECEBE é a curva DELE, a que ele PAGA é a NOSSA, e o **fator de cada
  leg = round(valor de liquidação ÷ VBR + 1, 8)** (mesa, §660: o VBR é o `Valor
  Base Remanescente` do Live Position Swap, a coluna 15 — a mesma regra do fator
  do Swap VCP; o valor vai com o sinal de quem recebe a curva — `LegSides`; sem
  posição não há VBR e não há fator). Com os dois, VBR × (fator nosso − fator
  deles) = o (A + B) do banco, que é o `Result` (o caixa, sinal do banco)
  e vem do TOTAL do e-mail — refazê-lo pela soma das pernas trocaria o centavo,
  e por isso `recalcular_swap` só refaz nocional/caixa vazios ou com o insumo
  mudado. A data é a do ASSUNTO, a liquidação o "D+n" do rótulo (ANBIMA), a
  parcial NÃO mantém prêmios. O Check ganhou `fatores` (`_CK_SWAP_B3`): o caixa
  refeito pelos fatores (VBR × diferença) bate com o `Result` na tolerância do
  arredondamento na 8ª casa (VBR × 2e-8 + 1 centavo — até ~3 centavos do
  e-mail). **Party e Counterparty saem do Live Position**, pela MESMA cascata
  da tela Swap Characteristics (§660): o CPF/CNPJ pelo Reference Data e, sem
  ele, a conta CETIP pelo B3 ACCOUNT (que recusa guarda-chuva e conta ambígua);
  na Party o nome do `b3-accounts` e a LE são só o plano B. **As duas telas de swap (CEM e EDG) são CARDS**
  (`deal-cards.js`, flag `cards` do catálogo): ids, Party/Counterparty, a pílula
  da LOB, o Check junto do status; a DataTable fica escondida como fonte do
  Export. `check_unwind_swap_trs.py`.
- **As onze telas do catálogo carregam pelo FILTRO INTELIGENTE** (mesa,
  21/10/2026, §661) — o mesmo da Fase 1 (§620) e das telas de New Deals: a
  barra de chips entre o dropzone e a grade, o chip padrão da Reference Date
  (o dia do arquivo, `_day`; o campo Reference Date da barra de ferramentas o
  move e continua sendo o dia do Import), e `POST <api>/cache/search`
  (`product/queries.search`, a árvore DO produto, leitura estrita, o
  `_deal_matches`). As ações da linha e do card mandam o `_day` DA LINHA
  (`dayOf`) — uma recompra de outro dia que a busca trouxe não está no dia da
  Reference Date. No modo cards (as de swap) a barra é o único filtro: o funil
  é da tabela, que fica escondida.
- **O backend das onze é UM, e o produto é parâmetro**
  (`features/unwinds/product/` + `infra/product_store.py`, §526): pasta
  (`dir`), posição (`position`: swap/option/ndf/None), conferências (`checks`)
  e layout da B3 saem da entrada do `catalog.py`; a API é a regra
  `/api/unwinds/<path:sub>` (que a estática da Fase 1 vence;
  `page_and_action` separa produto de um ou dois segmentos da ação). **Entra
  PLANILHA**, lida pelo conteúdo, com cabeçalho de rótulos OU campos da grade;
  **e-mail (`.msg`/`.eml`/`.htm`) entra pela TABELA colada do Excel no corpo**
  (mesa, 28/09/2026; `email_file.tabelas`): as MESMAS colunas da planilha, vale
  a primeira `<table>` com o cabeçalho da página e alguma linha (assinatura
  antes não atrapalha), texto puro com TAB também; sem ela,
  `unwind_email_table_unknown`. O parser do aviso da Fase 1 não se aplica.
  **O NDF Commodities tem e-mail PRÓPRIO** (mesa, 28/09/2026;
  `domain.linhas_do_recap_commodities`, lido ANTES do genérico): uma tabela
  por perna (`Leg` … `PV BRL`; colado como UMA tabela, toda linha `Leg` é um
  cabeçalho NOVO — a perna Banco não tem o `Risk Deal ID`), só `Client` e `Banco` entram (a `JPMOCC` é
  offshore), o `Risk Deal ID` NÃO entra em perna nenhuma (o B3 ID vem do Live
  Position, por strike + original), Pre FWD Rate = 0 (e aí o Check dispensa o
  DU). O sinal do PV é o do BANCO, pela `Original Position` + strikes. **A grade
  mostra o número do E-MAIL como veio** (mesa, 28/09/2026, §570): o Excel
  arredonda (`96.85`, `5.2087`) e refazer a precisão pelo FV USD/PV BRL punha
  na tela um strike e uma paridade que o e-mail não tem. Quando a conta com os
  números mostrados não fecha com o PV, o Check dá NOK e a coluna **OTC Tracker
  Result** (`CalcResult`, não editável) diz o que o app calculou — vazia quando
  bate. **O Edit que muda dado ECONÔMICO refaz as contas** (§571,
  `commands._refazer_calculos`): DU se uma data mudou, Result pela fórmula do
  termo e Direction pelo sinal — o que foi digitado no mesmo Save vence. O casamento com o Live Position aceita o arredondado: sem candidato
  exato, vale o contrato cujo strike/volume ARREDONDA para as casas exibidas
  (ainda ÚNICO), e a linha continua com o valor do e-mail; sem nenhum, o aviso
  diz o contrato mais perto e os dois valores (`unwind_match_none_near`). A posição (os MESMOS
  coletores do Live Position) só preenche o que a planilha deixou em BRANCO:
  divergência vira aviso e a planilha vence. **Sem B3 ID, casa por
  características só com candidato ÚNICO** (≥ 2 critérios, todos batendo);
  ambíguo não chuta. Chave natural = Contract (ou DealID) + UnwindDate;
  re-import volta a linha a `Imported` mantendo `_id`/Nº de controle, e linha
  `Sent` não se sobrescreve. Check de três estados (`balance`, `termo`,
  `premio`): OK só com TODAS rodando e fechando. Arquivo da B3 pelo motor do
  File Interpreter: TER 0014 (quantidade no 9, paridade no 14), SWAP 0014
  (**111** caracteres pela soma do template, não os 99 que o manual imprime; na
  forma da PLANILHA DE ANTECIPAÇÃO da mesa, §657: **papel pela CONTA MENOR** —
  Ponta 1 = a de menor número, manual 4.2.12, o `_ponta` do 0897 do Bullet;
  era "a Participante é nossa", que só acerta quando a nossa é a menor —,
  fatores 7/8 = a curva da Ponta 1 e a da Ponta 2, **campo 11 = o NOCIONAL**
  (`UnwoundNotional`, nunca o caixa), Data Antecipação = o dia em que o arquivo
  é GERADO (o `TODAY()` da planilha), Liquidante e Data de Liquidação (13) em
  branco, Mantém Prêmios só na parcial) e OPC 0014 (contas do
  REGISTRO, modalidade da posição). **O TER 0014 é o MESMO para asiático e não
  asiático** (mesa, 28/09/2026): as datas de verificação não vão (campo 16 =
  `000`); só a média asiática PONDERADA da opção ainda recusa. COE/DCE não têm
  layout: `unwind_no_b3_file`, e no Monitor fecham em `Imported`/`Approved`.
  **O NDF de Commodities segue a Fase 1** (mesa, 28/09/2026): Deal ID = o
  `Codigo Identificador` do Live Position (a chave da esteira; sem ele, o
  `_id`); Pending Confirmation + esteira no IMPORT (`UNWIND NDF COMM`, que sai
  junto no Delete e recusa linha carimbada); o Termo de Resilição pela mesma
  família `termo-resilicao` (a linha vai no formato da Fase 1 por
  `domain.para_o_termo`, com a MERCADORIA no eixo do grupo e o XML na moeda do
  contrato, `XmlCcy`/`XmlFxRate`); e a liquidação entra no `_ndfadv_collect`
  como `UNWIND` — com ela o Trade Level, o Summary, a TED e o aviso impresso
  do Other Products (o Título dela sai da leitura do Operations B3, senão o
  caixa sairia duas vezes). O Live Position traz o MESMO contrato na visão de
  cada entidade nossa (Banco × Lawton duas vezes, a do Lawton com a conta
  `41007`): a conta vai a oito dígitos e vale UMA visão por contrato, a da
  entidade que não é fundo (`uma_visao_por_contrato`). **O B2B gera as DUAS visões**
  (mesa, 28/09/2026, §578): contraparte que também é nossa no `b3-accounts`
  (e não guarda-chuva) ganha o arquivo na visão dela
  (`commands._espelho` → `domain.espelho_b2b`: contas trocadas, lado
  invertido), `UNWIND_NDF_COMMODITIES_LAWTON.txt` ao lado do do Banco. Só o
  layout do termo (`LAYOUTS_COM_ESPELHO`). O Participante do header vai por
  `force_values` — o template da antecipação o tem `Fixed` em `JPMORGANBM`.
  **A Opção de Commodities e o Swap EDG seguem o MESMO desenho** (mesa,
  21/10/2026, §670 — "toda recompra contra CLIENTE tem o Termo; contra
  Atacama/Lawton, o arquivo da Intrag"): `PAGINAS_COM_TERMO` liga a esteira
  (`UNWIND OPTION COMM`, `UNWIND SWAP`) e o Termo, o MESMO modelo e as mesmas
  colunas — o `para_o_termo` muda só os valores (opção: o eixo é o
  `Underlying` e o recomprado é quantidade; swap: o Valor Base em BRL) e o XML
  declara o produto recomprado (`XML_TIPO`: `OPTION`/`SWAP`, o swap só em
  reais; Termo que junta produtos AVISA). A liquidação lê por PÁGINA
  (`settlement_rows(ref, dirs=…)`): o aviso de termo e o Pay/Rec seguem só com
  o NDF de Commodities (`commodity_settlement_rows`); a opção entra no
  `_optadv_collect` (sem IR — só o prêmio paga) e o swap no Trade Level e no
  `_swadv_collect` pela MESMA leitura (`_ops_swap_unwind_rows`: as pernas na
  visão do banco por `curvas_do_banco`, o IR do swap), o contrato FORA da
  leitura da B3 nos dois. A perna do fundo fica na tela e sai do documento.
  Os outros produtos do catálogo (Options FXO/EDG, Swap CEM, COE, DCE)
  **ainda NÃO têm** Termo, esteira, Cockpit nem Summary.
  `check_unwind_products.py`, `check_unwind_settlement.py`.
- **A recompra de NDF FX vem da API de liquidação** (mesa, 20/10/2026, §640):
  o bloco `termination` do MESMO `getTradesBySettle` do Cockpit, com o `Cetip
  ID` do contrato (`domain.recompras_da_api`, o de-para do e-mail campo a
  campo; o DU é contado no ANBIMA, a API não o traz). A posição se acha pelo
  B3 ID (`posicao_pelo_contrato`, a visão do Banco antes da do fundo). O pull
  pede a data E o dia útil seguinte (a recompra liquida em D0 ou D+1, e o
  endpoint é por LIQUIDAÇÃO), só aceita o termination que liquida na data
  pedida (a parcial antiga volta junto no vencimento), grava no dia da
  RECOMPRA e **só a NOVA** — o laço roda a cada 30 min, e reimportar
  reescreveria a linha editada. A leitura do dia é estrita. O endereço é a
  linha `Unwinds` × NDF do `api-links`, com o Daily Settlement de plano B (o
  `upgrade` não alcança quem lê pelo `athena_api`). **O SINAL do `Settlement
  Quantity` é o do banco** (positivo = recebe), conferido numa amostra só: o
  Check diz NOK se vier invertido. O e-mail ficou como PLANO B no dropzone;
  a varredura do Outlook saiu (dois caminhos automáticos importariam a mesma
  recompra duas vezes). `check_unwind_api.py`.
- **No e-mail (plano B) a ponte até o contrato é o `Código Identificador` do
  Live Position, e ele vem de DUAS formas**: TRUNCADO nos 14 da direita (o aviso traz
  `STP-XE-10G5U5X-0-0` e a posição, `XE-10G5U5X-0-0`) ou INTEIRO
  (`ATS-4T6-2W4YU86-0-0` nos dois lados). O casamento tem TRÊS passadas
  (mesa, 02/10/2026, §621): a igualdade EXATA, os 14 da ESQUERDA dos dois lados — só
  com candidato ÚNICO, porque ids da mesma família diferem no FIM
  (`…-0-0` × `…-1-0`) — e, sem eles, os 14 da DIREITA dos dois lados.
  Truncando só o lado do aviso, a posição que guarda o id inteiro nunca casava,
  e o import saía sem contrato e sem contraparte com a linha bem ali na tela ao
  lado. A exata vem antes porque cada truncagem joga fora um pedaço do id. O aviso NÃO se basta — moeda, lado da posição, contas
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
  para conferir): "passou por omissão" não existe. Quando não fecha, a coluna
  **OTC Tracker Result** (`CalcResult`, não editável, §573) mostra o que o app
  calculou; e o Edit reconfere pelas COLUNAS da grade
  (`domain.reconferir_linha`). **O que LIQUIDA é o valor do E-MAIL, mesmo
  divergente** (mesa, 02/10/2026, §624): o `Result` é o Input Termination Fee
  e a conta nunca o troca — nem no Edit econômico (aqui a NDF FX diverge do
  catálogo, §571) —, e a direção é o SINAL dele (`domain.direcao_da_linha`, que
  Cockpit, Summary, Pay/Rec, Intrag e Termo leem; a coluna `Direction` só
  responde com Result vazio). Pela direção da conta, a recompra sem posição no
  Live Position ficava FORA do Cockpit e do Summary, e a que divergia saía com
  o sinal da conta.
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
- **Termo de Resilição e Pending Confirmation são SÓ contra o CLIENTE** (mesa,
  28/09/2026, §580): recompra com fundo nosso numa ponta (o B2B Banco × Lawton/
  Atacama, `queries.e_do_fundo` pelo `b3-accounts`) não entra na esteira, na
  segregação do Monitor nem no grupo do Termo — nas DUAS telas (NDF FX e o
  catálogo). Ela vai para a **Intrag › Unwind** no **IMPORT** (e o Edit a
  atualiza; o Delete a tira se lá ela ainda é `New`) — **nunca no Send** (mesa,
  28/09/2026, §582, e já dito antes): nem toda recompra é registrada na B3 pelo
  OTC Tracker, e a instrução da Intrag não pode depender disso. A linha JÁ
  ENVIADA que o reimport MANTÉM também vai (§583) — só as gravadas deixavam de
  fora justamente a recompra enviada antes da regra. Porta única:
  `intrag_da_recompra` da Fase 1 (a planilha de onze colunas é uma para todos os
  produtos; o catálogo entra por `product/commands.intrag`, no formato
  `para_o_termo`). A liquidação (Summary, Advice, Pay/Rec) continua com as duas.
  **O Intrag ID da recompra** (§585) é coluna da Intrag › Unwind (depois do
  Status), digitável no Edit (novo = `Success`) e puxado pelo **Mapping Intrag
  ID** do CSV de Boletas do Return — mas SÓ da linha que se diz recompra
  (`mappers.UNWIND_MARKS`: RECOMPRA/ANTECIPA/UNWIND/RESILI; a Situação que o
  arquivo manda é `Recomprado Totalmente/Parcialmente`). O B3 ID da recompra é
  o do contrato original, que tem boleta PRÓPRIA: casado só pelo B3 ID, a
  recompra levaria o Intrag ID da operação original. O que só aparece na boleta
  original volta em `only_original`, sem gravar. O card do Monitor fecha em
  `Sent` ou `Success`.
- **A chave da recompra no Pending e na esteira é PRÓPRIA** (§696):
  `UNW-<Athena ID>-<AAAAMMDD da liquidação>` na Fase 1 e `UNW-<_id>` no
  catálogo (`unwinds.domain.chave_esteira`; o deal leva `_mc_key`, que vence no
  `_conf_segregate` e no `_mc_conf_trade_keys`). O Athena ID cru é o `DEAL NAME`
  do trade ORIGINAL — o `Deal` com que a Vanilla e a Other Publisher gravam a
  confirmação dele —, e com a mesma chave a recompra reescrevia a original no
  Pending, nunca entrava na esteira e o Delete dela apagava a original. O `Deal`
  do deal da recompra segue o Athena ID (o documento e o XML o leem). Dados de
  antes: `scripts/migrate_unwind_esteira_keys.py`.
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
- **O Termo de Resilição tem card na zona Confirmations do Intraday Monitor**
  (`conf-unwind-termo`, bloco Unwinds; mesa, 28/09/2026, §588): a MESMA
  segregação do Confirmations Monitor (`_conf_unwind_groups` — só contra o
  cliente, contraparte × moeda/mercadoria), etapa pela esteira. É card SÓ de
  Confirmations: a taxonomia é chaveada pela chave inteira, e o
  `check_ndm_cards` aceita `conf-*` sem gêmeo no catálogo da B3.
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
  o card declara `done: ('Sent', 'Success')` — é onde ela fecha —, e não declara `les`,
  porque a entidade sai da CONTA e quem a traduz é cadastro (§491).
- **A rota da página é PRÓPRIA** (`/unwinds/ndf/fx`, três segmentos): o
  catch-all só atende `/<template>`.
- **O dropzone lê `.msg`, `.eml` e o corpo solto, pelo CONTEÚDO**
  (`infra/email_file.py` — magic do CFB, cabeçalhos MIME), não pela extensão:
  o Outlook renomeia anexo e um `.msg` chega como `.txt` sem aviso. O assunto
  sai do arquivo quando ele o carrega; só o corpo solto cai para o nome.
- **Os botões da linha são os QUATRO da casa** (§7): Confirm, Edit, Delete,
  Send, e **aparecem em TODO status** (mesa, 28/09/2026, §574): a tela não
  esconde ação pelo Status — quem recusa o que o status não permite é o
  servidor, com a frase traduzida. **Linha `Sent` também se EDITA** (mesa,
  28/09/2026, §575): o Save a devolve a `Pending` e ela só volta à B3 depois do
  checker; e se REENVIA (§579: a B3 recusou, o arquivo sumiu da pasta). O que
  segue travado em `Sent` é o Delete e o reimport. O preview do arquivo da B3 é o **duplo clique** na linha e o Termo de
  Resilição se gera no **Confirmations Monitor** — um olho e um documento na
  coluna Actions eram dois caminhos a mais para onde já se chega. A **edição
  segue o 4-olhos das páginas de Intrag**: salvar põe a linha em `Pending` e
  marca o maker, `Approved` é outro usuário conferindo (o próprio é 403), e
  **`Pending` não é enviável** — `STATUS_ENVIAVEL` é `Imported` (veio da
  máquina, intocada), `Approved` (mexida e conferida) e `Sent` (reenvio). O `Status` e o `Check`
  ficam fora dos campos editáveis: um é estado da esteira, o outro é veredito
  apurado.
- **A tela carrega pelo FILTRO INTELIGENTE** (mesa, 02/10/2026, §620): o mesmo
  das páginas de New Deals, em `POST /api/unwinds/ndf/fx/cache/search`
  (`queries.search`, `_deal_matches`, leitura ESTRITA). A Reference Date é o
  chip padrão sobre a pseudo-coluna `_day` — o dia do ARQUIVO-DIA, que a busca
  acrescenta numa CÓPIA da linha e que limita os dias lidos. As ações da linha
  (Edit, Confirm, Delete, Send, Preview) mandam o `_day` DA LINHA (`dayOf`),
  nunca a Reference Date: o `queries.find` com data só olha aquele dia, e uma
  linha de outro dia trazida pela busca daria "not found". Import, varredura e
  Mapping B3 seguem gravando no dia da Reference Date.
- **O `Status` é a PRIMEIRA coluna de dado**, logo depois das Actions: em
  dezoito colunas, no fim da grade a resposta "esta linha já foi?" só aparece
  depois de rolar a tabela inteira.
- **O gatilho de tudo que vem depois é o IMPORT**, não o Send (mesa,
  18/09/2026, invertendo a decisão de dois dias antes): Pending Confirmation,
  esteira (Track + Monitor), NDF Cockpit e o Settlement Summary recebem a
  recompra assim que ela chega. A recompra é **elegível** para o documento
  desde aí (`confirmation_deal` devolve `Success`), e o que se paga é que uma
  recompra corrigida ou apagada depois já deixou linha — a correção é
  reimportar (o upsert refaz pela mesma chave). **A Intrag TAMBÉM nasce no
  IMPORT** (§582): ela chegou a ficar no Send, e a recompra que não passa pelo
  Send do OTC Tracker nunca chegava à Intrag.
- **O retorno da B3 vira `Success` pelo Mapping B3 ID** (mesa, 28/09/2026,
  §582/§587; botão verde das DUAS telas, `commands.mapear_retornos`): o
  retorno é `Numero;Codigo IF;Cod. Oper.;Descricao;Texto da Linha Original` —
  vale a linha com `EXECUCAO OK` (ou SUCESSO) na Descrição, o B3 ID da recompra
  (o `Contract`) no **Codigo IF** e o texto ecoando uma ANTECIPAÇÃO
  (`domain.e_antecipacao`: `TER  1` + `0014`). **O Mapping do New Deals
  ignora essas linhas** (`new_deals/entrypoint._e_antecipacao`): ele apagava
  todo arquivo com `TER` na posição 57, e o retorno da recompra sumia antes de
  ser lido. UMA
  varredura cobre a NDF FX e as onze do catálogo nos últimos
  `RETORNO_LOOKBACK_DIAS` (10) dias corridos; o arquivo de retorno só é apagado
  quando TODAS as linhas de dado dele casaram (a pasta é a do New Deals).
  `Success` é registro como o `Sent` (`STATUS_REGISTRADO`): não se apaga nem se
  sobrescreve no reimport, e o Monitor fecha nos dois.
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
- **Toda ação da página toca o sino** (Import, pull da API, Edit, Confirm, Delete,
  Send, Termo salvo), porque o arquivo-dia é da mesa inteira. A exceção é o
  `dry_run` do Import: ali nada foi gravado, é a pergunta das duplicatas.
- **Import e varredura são em LOTE** (mesa, 02/10/2026, §622): o
  `import_emails`/`import_email_uploads` lê a posição UMA vez e faz UM upsert,
  UMA passada de esteira (`_pc_save_from_deals`/`_mc_save_from_deals`: uma
  leitura e uma escrita por banco), uma de Intrag e uma de Cockpit; o pull da
  API grava pelo MESMO funil (`_montar_linhas` + `_gravar`, um upsert por dia
  de recompra). Um e-mail por vez abria cada banco
  uma vez POR RECOMPRA no share: 79 recompras passavam de uma hora. E-mail que
  falha volta em `failed` sem derrubar os outros; a tela manda os arquivos em
  fatias de 25. Caminho NOVO de gravação por recompra entra no lote, nunca num
  laço de chamadas unitárias.
- **O pull roda sozinho a cada 30 min**, em laço PRÓPRIO da vertical
  (`unwinds/commands.scheduler_loop`, registrado no `routes.py` como
  `unwind-api`, `OTC_UNWIND_API_POLL_MIN`), dentro da janela de importação e
  não dentro de outra feature: **feature não importa feature** nesta casa —
  é o `check_soc_layers` que segura. **Pull sem recompra nova não toca o
  sino** (quase sempre não há), e a data que a API não respondeu vai para o
  log em WARNING mesmo sem linha nenhuma. Até 20/10/2026 o laço era a
  varredura do Outlook (§640).

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
- **Swap › Strategy** (`/live-position-swap-strategy`, `features/swap_strategy`,
  §602): os dois relatórios do MID de Swap da B3 (ConsultaEstrategiaContratos =
  a lista, ConsultaDadosEstrategia = os dados de UMA estratégia) entram pelo
  dropzone em qualquer formato e são lidos pelo CONTEÚDO — o cabeçalho é a
  linha com "Código do Contrato", e é DELA que sai o separador (o título "B3
  S.A. - BRASIL, BOLSA, BALCÃO" tem vírgulas). O `#` do contrato sai. Os dois se
  FUNDEM por contrato (a lista não apaga dados, os dados não apagam o nome);
  Status `Complete`/`Pending`. Contraparte e LOB NÃO são do arquivo: saem do
  Swap Characteristics na leitura. O cadastro é lido pela platform
  (`platform/swap_strategies.py`), porque o Swap Calculator e o Settlement
  Advice também perguntam. `check_swap_strategy.py`.

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
- **O aviso de liquidação da RECOMPRA é PRÓPRIO** (mesa, 28/09/2026, §569),
  no NDF Summary e no Termo de Commodities do Other Products — e, desde o §670,
  no aviso de Opção (Opção de Commodities: quantidade original × recomprada e
  prêmio unitário) e no de Swap (Swap EDG: o Valor Base Recomprado ao lado do
  original; o `build_swap_settlement_emails` agrupa por `unwind`): nunca neta com o
  vencimento, o assunto é `(Recompra) Liquidação de Operação de Derivativo
  (<produto>) + Callback - …`, o `.eml` sai em alta prioridade (`importance`
  no draft → `Importance`/`X-Priority`) e a tabela troca o Fixing/Cotação
  Mercadoria por nocional recomprado, taxa pré e taxa de recompra. A linha da
  recompra traz o PRÓPRIO cabeçalho (`headers`), e o bloqueador de linha
  incompleta confere cada linha pelo dela.
- **`_ops_trade_rows(settle_ref)` é o único lugar que sabe quais famílias
  existem** (SWAP + NDF Commodities + opção); página, cards e e-mail de TED
  chamam ele. Família cuja coleta LEVANTOU fica em `g._ops_trade_failed` e o
  card de reconciliação a marca `failed` (badge **Erro**, §613) — sem isso
  `0 = 0` saía como batido. Status do aviso vive no overlay `other-products-summary_YYYYMMDD.json`
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
- **Swap VCP de EQUITY: o OTM é a PERFORMANCE, sem o principal** (§606,
  `principal_fora_da_curva`, pela LOB `EDG`): o principal não é tirado da
  curva nem somado na prova real. Descontado, o bullet de equity no vencimento
  perdia o 1,0 do fator (22I01597022: 1,1106 × 2,1106 do Swap Calculator) e a
  Diferença saía ZERO, porque a prova real somava o mesmo principal de volta.
  CEM/Hybrids seguem com o principal na curva.
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
- **A conta do cliente no aviso, com o BANCO pagando, é o `DEFAULT_RECEIVE`**
  (mesa, 29/09/2026, §597; `otc_emails._client_account_for_bank_paying`). Os
  defaults do Reference Data são a visão do CLIENTE (PAY = de onde ele paga,
  RECEIVE = onde ele recebe) e o aviso é a visão do BANCO: Resultado Final
  negativo é o banco pagando, o cliente recebendo. Os quatro avisos (prêmio,
  NDF, swap, termo/opção de commodities) imprimiam o `DEFAULT_PAY` — com PAY
  interna e RECEIVE externa, o documento mandava o dinheiro para a conta errada.
  Sem RECEIVE aprovado o aviso mostra `—`, nunca a conta de PAY. É o mesmo
  cruzamento da coluna Account do Settlement Summary (`_ndfsum_account_fmt`).
  `check_advice_account.py`.
- **Perna interna não gera aviso** (`_ops_is_internal_cpty` pelo `le-spn` +
  `_pc_is_internal_counterparty`, nunca "começa com BANCO"): fica no Trade
  Level e no Summary, sai do Advice e do TED — o e-mail de TED do NDF faz a
  mesma pergunta por SPN (§451); entidade nossa fora do `le-spn`/INTERNAL
  ainda passa, e se corrige no cadastro. **A SSI anexada ao TED é
  procurada em TODAS as pastas gêmeas do Electronic Inventory**
  (`_ei_client_dir_names`): olhar só a vencedora do scan dizia "não
  localizada" com o arquivo salvo na outra.
- **O Advanced Export tem teto POR PÁGINA** (`daily.timeout`, §562) e uma
  segunda passada nos dias que falharam; o Operations B3 declara 180 s, e o
  mapa da coluna Type fica em memória pelo carimbo de cada posição.
- **Nome da contraparte sai do SPN** (`_athena_settlements` → `_otm_cpty_name`;
  OTM pelo `Cpty SPN`, na leitura; o **Kapital Hybrids** pela coluna
  `Counterparty SPN` — mesa, 30/09/2026, §601): `le-spn` para entidade nossa,
  depois o Reference Data; o texto do arquivo é só o plano B.
- **CEMHYB liquida pelo Kapital Hybrids, não pelo OTM nem pelo Athena**
  (§605): o swap híbrido não está no Swap Athena nem no OTM. No Settlement
  Advice, no Trade Level/Summary do Other Products e na página Swap VCP, a
  linha CEMHYB tira do Hybrids (`_swaphyb_curvas`, pelo CETIP ID via
  `mapping_swap-hyb` ou pelo Kapital ID do Athena) o Internal ID (= Kapital
  ID), a contraparte pela SPN e os valores (Σ positivos, Σ negativos, a soma) —
  a escolha é da LINHA inteira, para Banco + Cliente = Bruto fechar. Sem o
  trade no Hybrids vale o de sempre. As pernas se agrupam numa função só
  (`_swaphyb_groups`), a mesma da página do Hybrids. Indexador Banco/Cliente
  do aviso sai sempre em MAIÚSCULAS, e no contrato de estratégia vem do
  Strategy (`PONTA_PARTE` = banco).
- **IR do termo de moeda é CALCULADO** (`_ndfsum_ir_apply`, §423): 0,005%,
  isento pelo `ndfc-ir-exempt`, piso de R$ 1,00 acumulado no mês no ledger
  `ndf-ir-ledger_AAAAMM.json`. **O piso é do MÊS** (mesa, 22/10/2026, §674):
  alcançado, toda liquidação seguinte da contraparte no mês retém, mesmo
  centavos — a entrada do ledger grava `reached`, e a antiga sem ele vale pelo
  `withheld` > 0 (`_ndfsum_ir_reached`). O import do Cockpit reusa as mesmas funções
  (`_ndfc_apply_ir`), o calculado vence o `VL_TAX_INCOME`. **A cura do ledger é
  INCREMENTAL e roda FORA do `_cache_lock`** (§432 — era o Summary
  "infinito"): grava dia a dia, só o dia pedido fica de fora com `ir_partial`;
  laço `ndfsum-ir-warm` cura até a véspera; `/data` devolve `collect_failed`
  como JSON. Other Products segue o mesmo desenho.
- **Os cards B3 × Internal do NDF Summary contam só as contas PRÓPRIAS**
  (§561, mesa, 25/09/2026): no lado B3, a QUANTIDADE só soma o resgate cuja
  `Conta` é a `OWN` de JPM ou MGT no `b3-accounts` (73760.00-9, 04880.00-6 —
  `_ndfsum_count_accounts`); o VALOR soma todas as linhas. O mesmo contrato chega
  por mais de uma visão (intragrupo espelhado, guarda-chuva) e cada uma contava
  como operação. O `matched` do card compara essa contagem.
  `check_ndfsum_card_count.py`.
- **A tabela do PDF do Advice tem largura MEDIDA** (`stringWidth`, escada de
  fonte, `Paragraph`), nunca `515/N`.
- **No Cockpit, `VL_FORWARD_RATE` é a forward do trade date e
  `VL_STRIKE_PRICE` é o FIXING** (é o que a Trade Level chama de FORWARD RATE
  e FIXING RATE; o `_ndfc_strike_calc` deriva o fixing do forward). Na API o
  `Strike` é a forward e o `Spot` do evento é o fixing — o §421 tinha cruzado
  os dois pelo nome. O Fixing do aviso é o Spot da API guardado em
  `_nc_fixing` na importação (`_ndfsum_fixing`); sem ele, a célula FIXING
  RATE; nunca a forward (§438).

- **Regulatory › WHT (`/regulatory/wht`, `features/wht`, §692) bate o IR do
  DECÊNDIO** (01–10, 11–20, 21–fim; recolhido no 1º dia útil depois) com o
  relatório "Posição de Tributos" do HUB. O lado OTC são as MESMAS linhas das
  telas de liquidação — o `email_trades` do `_ndfsum_collect` e o
  `_ops_trade_rows` —, só as que o BANCO paga, e elas FLUEM sozinhas: o
  `/data` dos dois Summaries entrega o dia (`routes._wht_engine().flow`), e o
  import do Cockpit e o Save Daily Settlement Files o recoletam em background.
  O armazém é um documento por MÊS (`wht/wht_AAAAMM.json`), uma fatia por dia ×
  fonte que a coleta SUBSTITUI (coleta vazia não cria o dia — senão o aviso de
  dia faltando sumiria). O Import Settlements é um TRABALHO em segundo plano,
  com os dias em paralelo (§694); o prêmio de opção entra como UMA linha com o
  net do dia. **Termo e opção de COMMODITIES vão com o Trade Id do OTM**
  (`85000H-1PMHHP`, §695), não com o Nº da Confirmação: o Trade Level o traz
  em `_otm_id` (`routes._ndfadv_otm_ids`, pelo sufixo) e o `queries._ops_id`
  escolhe. **A mercadoria é LOB, não produto** (equipe, 26/10/2026):
  Product só `NDF`/`OPTION`/`SWAP`, e termo e opção de mercadoria são
  `× COMMODITIES`; o NDF do Cockpit é `CEM` e a classe `INDICES
  INTERNACIONAIS` é `EDG` — UMA regra (`domain.produto_lob`) na coleta e na
  LEITURA (o mês já gravado sai certo), e o `wht-codes` separa pela coluna
  LOB (o `upgrade` converte o cadastro gravado com `NDF COMM`/`OPTION COMM`). **O imposto que cada operação informa ao HUB é a
  QUEBRA do piso de R$ 1,00 do mês** (`domain.allocate`), não o que foi retido:
  os decêndios anteriores ao que passou do piso ficam zerados, no que passou
  cada operação leva o SEU imposto e a que cruzou leva também o acumulado dos
  anteriores (`OTC_IR`; o `Devido` é o da própria operação). Código, tributo,
  prefixo do documento e se há piso saem do `wht-codes`, NUNCA do código; a
  empresa/filial do EasyTributos, do `wht-company`. O arquivo do HUB (as
  `Unmatched OTC`) tem quatro linhas por operação, reconstruídas do exemplo da
  equipe (`domain.hub_file_lines`, 60/233/84/85) — o `check_wht.py` prende o
  exemplo byte a byte. Coluna nova no Trade Level que o WHT precise lê-se no
  adaptador (`queries.ndf_rows`/`ops_rows`), nunca numa segunda leitura dos
  arquivos. **Edit, Confirm, Delete, o lote e o Add Row** (§702): a linha da
  tabela é montada na LEITURA e a coleta seguinte substitui a fatia do dia, então
  a correção NÃO se grava na linha — vai no documento do mês (`edits`), por linha
  de ORIGEM (`otc_key` = o id da operação, `hub_key` = `HUB|<hub_key>`), e é
  aplicada antes do batimento (`queries.otc_lines`/`hub_rows_of`, a leitura
  ÚNICA do `build` e do HUB File); o que se apaga vai para `deleted` e a operação
  incluída à mão para `manual`. Tudo nasce `Pending` e outro usuário confirma
  (`authz.is_own_change`); o HUB File recusa linha pendente. As colunas
  editáveis, o lado e o tipo são `domain.EDIT_COLS` (a tela as recebe do
  servidor); a LE é JPM ou MGT. **OTC_TD é o Trade Date** (só do OTC, o
  `_trade_date` das linhas do Trade Level e o `trade_date` do NDF Summary) e
  **OTC_ET/HUB_ET a data do evento**, a que o batimento compara; o IR do
  swap no Add Row é a regressiva pelo prazo do Trade Date (`queries.derive`, a
  `_ops_swap_ir_rate`). A recompra é sempre `UNWIND` (`domain.event_of`, também
  na leitura). O status sai em caixa alta pelo `data-case="upper"` da pílula
  (o `otc.js` pula o Proper nela, no funil e no export).

### Esteira de confirmação manual

- **Opção de commodities de CO1-2 (Brent rolling) usa o documento da família
  COMUM** (mesa, 01/10/2026, §615): `_conf_opt_family` = `_conf_deal_family`, e
  o ticker sai com a frase de rolagem do `_conf_co12_text` (sem
  `SettlementDate`/`FixingEndDate`, o `CO1-2` cru). A família `co1-2` nunca
  teve template — separá-la de novo exige o template junto.

- **A data do documento ("São Paulo, <data>") é a da OPERAÇÃO, nunca a do dia
  em que a confirmação é gerada** (mesa, 30/09/2026, §598), em TODO template:
  gerado em D+n, o documento diria uma data em que nada aconteceu. Quem a dá é
  o `data_extenso` do `conf`, pela `TradeDate` do deal (sem ela, a `Data
  Operação` da esteira, que o Generate do Monitor manda como `?date=`); no
  Termo de Resilição é a data da RECOMPRA. Template novo imprime
  `{{ conf.data_extenso }}` no fecho e põe `data_extenso` na lista de campos do
  painel — o Swap EDG tinha a data do Word de exemplo fixa no HTML.
- Ciclo: `(Pending Legal) → Pending OTC → Pending MO e/ou FO → Pending FepWeb
  → Ok`. Legal é hold manual; FepWeb é derivado; Ok exige `Enviado p/
  cliente`; `Pending OTC` digitado REABRE (limpa validações). Toda gravação
  espelha no Pending Confirmation (`_mc_pc_sync`, leitura ESTRITA das linhas do
  lote): a etapa entra verbatim e o Ok vira o status de assinatura pela regra
  do PRÓPRIO Pending (`_pc_signature_pending_status`, sem o prazo) **só enquanto
  o Pending está numa etapa da esteira** — depois o status é da equipe
  (Concluded, Signed Digitally) e a esteira não o reescreve (§696).
- **Laço que grava várias linhas confere TUDO antes da primeira** (§696): cada
  `mark_validated`/`save_changes` é uma transação, e a recusa no meio deixava
  metade assinada sem espelho. O Validate pergunta ao
  `manual_conf.validation_blocker` (a MESMA regra do `mark_validated`), o
  arrastar SIMULA o caminho (`_mc_move_one(..., dry=True)`); e o que ainda
  levanta no meio (banco ocupado) espelha no Pending o que já gravou
  (`_mc_sync_parcial` ou `finally`). Endpoint novo da esteira em laço segue o
  mesmo desenho.
- **O Edit do Track manda só o campo MEXIDO** (`data-orig` no modal, §696): a
  linha vem da última carga da página, e mandá-la inteira apagava a validação
  que outra mesa deu depois. E desfazer uma validação pela grade é da mesa da
  ETAPA (403 para as outras); o OTC reabre a esteira inteira pelo `Pending OTC`.
  **A grade tem as travas do Monitor** (§701): MO/FO antes do OTC é 409
  `stage_not_pending` (pelo `validation_blocker`), desfazer só a do OTC com MO/FO
  validados é `mc_reopen_instead`, e o Enviado p/ cliente pela grade é o Mark as
  sent — do OTC, só em Pending FepWeb (`mc_not_fepweb`) e com callback
  (`callback_required`, menos MGT).
- **A tela do Pending Confirmation grava só o que MUDOU** (§701): manda a linha
  como a CARREGOU (`orig`/`origs`) e o upsert aplica a diferença sobre a linha
  relida estrita; apagada por outra pessoa é 409 `pc_row_gone`; sem `orig`
  (Add Row) grava inteira. O Delete do Pending e da esteira LEVANTA na falha, e a
  grade só tira a linha com o servidor confirmando.
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
- **O card do Monitor é o DOCUMENTO** (§564): confirmação já gerada agrupa
  pelo `Confirmation Link` (que a geração carimba em toda operação do PDF), não
  pelos campos — eles divergiam da segregação e partiam uma confirmação em dois
  cards (o Validate carimba as chaves do CARD). Com vários PDFs casando na
  pasta, vale o do link, no card e na janela de validação. O ativo das
  commodities é UMA função para o documento e para a Moeda da esteira
  (`_conf_merc_default`: Commodities → Subjacente → Underlying Asset).
- **Callback**: falta de `Data Callback` é badge só no card Pending FepWeb (como
  CONTAGEM) e TRAVA o Mark as sent (409 `callback_required`). **MGT × cliente não tem
  callback** (mesa, 28/09/2026, §581): `_mc_row_is_mgt` (a Legal Entity da
  linha) tira a linha do badge — injetada no `monitor_payload` como
  `callback_exempt` — e do 409.
- Nomes de coluna são os da planilha legada (schema dos DuckDB); rótulos pelo
  `COLUMN_LABELS` completo. Coluna nova em `DB_COLUMNS` é só isso — `ensure_db`
  faz `ADD COLUMN IF NOT EXISTS`, sem script.
- **Cobrança** (`conf_escalation`, sete listas em `domain.REC_KEYS`; seg/qui
  rolando feriado, escalação em `left == 0`; grupo de FO casa por
  `confirmation_type`; Pending FO sem grupo vai para `unmatched`).
- **BACC EA Metrics** (16:00 BRT, `.xlsx`): sem Data Callback, Pending ≠ Ok,
  Aging decrescente numérico; tipo por coluna, máscara `#,##0.00` invariante;
  planilha vazia VAI; `Conterparty Name` é grafia de contrato.

### Intraday › Initiatives e Tasks (§631, §633)

- **Na tela e no ENDEREÇO é INITIATIVES** (mesa, 20/10/2026, §633/§638): a
  página é `/initiatives` e `/initiatives/<id>`; `/projects` e
  `/projects/<id>` REDIRECIONAM (com o `?task=`), e o `Page_Access` gravado com
  `/projects` vale para a página nova pelo `authz._renomeadas` — é assim que se
  renomeia URL sem revogar acesso. A API (`/api/projects`), os ids
  (`PRJ-0001`), as chaves de tradução (`pj-*`) e o código seguem `projects`:
  não aparecem no navegador. O sino grava `Initiatives`/`Initiative Lead`, e os três mapas
  têm também o `Projects` dos avisos já gravados. Texto novo nessas telas diz
  "initiative", nunca "project" — `Projects` é uma das CATEGORIAS.
- **Categoria é lista fechada** (`domain.CATEGORIES`: Process Review, Tech
  Issue, Projects, B3 - Improvements, Stomp/Red), gravada em inglês como o
  status e traduzida na tela (`cat_<valor>`). Criar exige; a iniciativa de
  antes não tem e a edição pede uma (`category_required`). A lista filtra por
  categoria (menu ao lado do status, lembrado por quem vê) e os contadores do
  topo acompanham a categoria escolhida.
- **Um documento só** (`features/projects/infra/store.py`,
  `projects/projects.json` no armazém), ler → alterar → gravar dentro do
  `store.mutate`; o id (`PRJ-0001`) e os ids filhos são CONTADORES gravados —
  apagado nunca volta (o projeto fixado na barra de alguém abriria outro).
- **Lead, time e responsável = usuários Active com papel BO ou ADMIN**, mais a
  própria sessão BO/Admin/master (`queries.eligible`). Regra da mesa.
- **O TIME da iniciativa** (`members`, §639): os envolvidos além do Lead, mesmo
  sem tarefa — sem repetir e sem o Lead; quem já estava segue nele fora do BO
  (a regra do Lead gravado). Quem ENTRA é avisado (`Initiative Member`,
  preferência `project_member`). **O responsável de cada tarefa sai dos
  ENVOLVIDOS** — Lead, time e quem já tem tarefa (`domain.assignable`); fora
  deles é 400 `assignee_not_in_team`, e o responsável que a tarefa já tem é
  mantido. A User Home tem a MESMA regra de envolvido em
  `user_home.domain.envolvidos` (feature não importa feature): mudou uma,
  muda a outra. Tela que abre o modal ou a gaveta de tarefa passa os
  envolvidos da iniciativa (`involved` ou `people`), senão o menu oferece
  todos os elegíveis e só o servidor recusa.
- **O avatar mostra a FOTO** (`images/users/<sid>.jpg`, a mesma da barra) de
  quem a tem (§634): cada pessoa do `eligible` leva `photo`, e o `avatar()` do
  `projects-common.js` a acha pelo SID (plano B: o nome exato — os
  participantes da reunião vêm do Outlook por nome) — tela nova não passa
  nada. Quem responde é `platform/user_photos.url`, que LISTA a pasta uma vez
  por minuto: um `stat` por pessoa, com o código no share, é uma ida à rede
  por avatar.
- **A API vale para `/initiatives` OU `/tasks`** (`entrypoint._can_see`): a Tasks
  move as tarefas dos projetos. A página `/initiatives/<id>` confere na rota —
  o `enforce_page_access` não a vê (não está no menu).
- **Os modais esperam as listas da página** (`afterMeta`, §636): Lead,
  responsável e ícone vêm na resposta da página, que no JP leva segundos, e o
  menu do tema não abre `<select>` vazio. Página nova que abre estes modais
  chama `P.setMeta` no sucesso e `P.metaFailed()` na falha.
- **O MARCO é o EVENTO da iniciativa** (mesa, 21/10/2026, §648): nasce do
  **New event** da barra da página (`OtcPj.openEventModal`), com hora,
  duração, tipo e local (`domain.validate_milestone`; tipo e duração em lista
  fechada, `EVENT_TYPES`/`EVENT_LENGTHS`, no `meta`; sem hora é o dia inteiro
  e não tem duração). **O card Milestones SÓ MOSTRA**: o clique num marco abre
  o mesmo modal, que é onde ele se edita, se dá por atingido e se apaga. O
  PATCH só muda o que veio (`MILESTONE_FIELDS`).
- **Botão da barra da página lê a iniciativa CARREGADA** (§648,
  `carregada()` do `project-detail.js`): no JP a página leva segundos, e o
  Edit clicado antes disso guardava o `state.p` vazio — o modal abria em
  branco, sem o que foi preenchido na criação. O clique espera a carga; o
  `openProjectModal` em modo edição sem iniciativa não abre.
- **Os ALERTAS** (§701, card `initiativealerts` do Control Panel): 08:00 BRT de
  dia útil, só `On going` — mais de 5 dias úteis sem atualização, 2 dias úteis
  para o prazo dela ou de uma tarefa aberta, o dia do fim (`domain.alerts`). UM
  e-mail por iniciativa (o box do card + quem está nela, CC do card) e o sino só
  dos envolvidos (preferência `initiative_alerts`); cada alerta sai UMA vez pela
  chave, e o e-mail que falha não marca. `check_initiative_alerts.py`.
- Toda escrita devolve o PROJETO inteiro; a tela se redesenha dele. Atividade
  e erro saem ESTRUTURADOS (`kind`/`code` + params), traduzidos no
  `projects-common.js`. Chave de tradução das telas é `pj-*`/`tsk-*` — `tk-*`
  é do Support Center.

### Intraday › User Home e Settings (§632)

- **Um documento por USUÁRIO** (`user-home/<SID>.json`, `features/user_home`):
  eventos do Outlook, foco, as preferências da Settings e os FAVORITOS do botão
  flutuante (§658). As duas páginas são
  pessoais e estão no `_ALWAYS_ALLOWED_PATHS`.
- **Os projetos chegam pelo `routes`** (`_projects_doc`/`_projects_directory`/
  `_projects_meta`) e o Projects pergunta pelo `_user_wants(sid, chave)` antes
  de tocar o sino de UMA pessoa — aviso pessoal novo entra no
  `domain.DEFAULT_SETTINGS['notify']` e no `_PREF_KEY` do Projects.
- **Sync = Outlook da máquina pelo COM**, substituindo o gravado; o filtro do
  `Restrict` tenta `mm/dd` e `dd/mm` e confere cada item pela data real.
  **Reunião é ZOOM** (link do Local ou do corpo; o Join abre `zoommtg://`).
  O colega vê "em reunião até…", NUNCA o assunto. **O calendário padrão do
  perfil só vale se o perfil é de quem clicou** (§633): o link do e-mail
  aponta para a máquina de quem o mandou, e sem a conferência as reuniões do
  dono da máquina iam para a Home de outra pessoa —
  `calendar_not_accessible` (409).
- **"Vence hoje" às 08:00** (`user-home-due`, claim diário em disco;
  `commands.run_once`). Leitura que falha DEVOLVE o dia (§633) — reservado e
  não enviado, ninguém tentava de novo até amanhã.
- **O CSV das minhas tarefas neutraliza fórmula** (`= + - @` ganham o
  apóstrofo: o título é digitado por qualquer um que cria a tarefa) e diz
  `1 of 3`, nunca `1/3` (o Excel lê como data).
- **A trava do armazém é por SID** (`store._lock_of`): uma só fazia a gravação
  de um segurar a Home de todos.
- `check_user_home.py`.

### Arrastar entre colunas (§632)

- **Confirmations Monitor** (`/api/manual-confirmation/move`): soltar é ASSINAR
  a etapa pelas mesmas funções da tela do documento; a mesa move só a SUA
  etapa, um passo; admin/master qualquer coluna (para trás reabre).
  **Onboarding Overview**: soltar abre o formulário da etapa. **Intraday
  Monitor**: ajuste manual registrado (`task_runs.set_override`); a mesa (BO)
  devolve ao cálculo o ajuste que ELA fez (o Undo da pílula, o "↺ auto").
  Nenhum arrasto grava por um caminho próprio — vai pela regra que o botão já
  usa.
- **A coluna REAL manda, não o `from` da tela** (§633): o quadro não se
  atualiza no meio do arrasto, e a permissão conferida contra o `from` do
  request deixava um card velho reabrir uma confirmação Ok ou assinar a etapa
  de outra mesa. Linha fora do lugar é 409 `stale_card` e nada é gravado (no
  Confirmations Monitor para todos; no Intraday Monitor para a mesa).
- **O arrasto do Tasks cancela sozinho** sem `pointerup` (`pointercancel`,
  `blur` da janela, ponteiro de volta sem botão): o card volta ao lugar, em
  vez de seguir o mouse até o próximo clique cair numa coluna qualquer.
- `check_mc_move.py` §6, `check_intraday_monitor.py` §4h.

### Pending Confirmation

- **O Dashboard (`/dashboard-pending-confirmation`, Pending Confirmation ›
  Dashboard; `features/pc_dashboard`, §596) é a fila `pending` numa tabela
  dinâmica**: linhas Economic Group × Owner × Signature Type, colunas trimestre
  da Trade Date (`2026 T1`) × Pending Status. O filtro é a FAIXA de pendência — a
  coluna Status do Main —, e a lista de faixas sai do `_pc_aging_band_label`
  (nunca uma cópia dos rótulos). A fonte é o banco `pending` lido AO VIVO e
  ESTRITO (`_pc_load_rows('pending', strict=True)`: ocupado sobe, nunca vira
  tabela vazia), e a tela se ATUALIZA SOZINHA (a cada 30 s com a aba visível e
  ao voltar para ela; o Refresh lê na hora), trocando só as linhas quando as
  colunas não mudam — funil, ordem e página ficam. Export é o menu da casa
  (Buttons + Advanced): o Buttons 3.2 exporta o cabeçalho de duas linhas.
- **O card Daily Metric tem DOIS relatórios para a mesma lista**: o Run
  (confirmações) e o **Pending CGD** (`/api/control-panel/daily-metric/cgd-run`,
  §596) — os clientes com CGD pendente no Track Docs (`cgd_docs.outcome ==
  'pending'`), na mesma estrutura do e-mail: por grupo econômico, aging em dias
  ÚTEIS, as mesas com que o CGD está e o banker pela SPN no RefData. A rota
  nova entra no `_CP_ENDPOINT_CARD` como `dailymetric`. **Ele roda só às
  sextas, e por isso NÃO se diz diário**: o assunto é `Metric - Pending CGD
  Brazil OTC - <data>` (`domain.cgd_subject`), o cabeçalho acompanha e o corpo
  fala em *weekly analysis* — o card continua sendo o do Daily Metric.
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
- **Pay/Rec: a recompra de NDF de Commodities é COMM TER, não COMM OPT**
  (mesa, 28/09/2026, §576). No `cashflows` ela chega como UMA perna só no
  Trade Id, e a regra do `_jpm_cashflows` (mais de uma perna = COMM TER, uma =
  COMM OPT) a lia como prêmio de opção. Quem diz que é recompra é a vertical
  (`commodity_settlement_rows`, as que liquidam no dia, passadas pelo Run como
  `unwind_rows`): casa pelo Trade Id (exato ou os 14 da direita) ou, sem ele,
  por contraparte (sem pontuação e sufixo societário) + valor dentro de R$ 1,00,
  cada recompra UMA perna. Vertical ilegível não derruba a recon (avisa no log).
- **Pay/Rec: o Pending Payment / Pending Receivement passa para os dias
  seguintes** até casar ou ser justificado (§704, `_apply_carry_forward`). O
  dia anterior é o mais recente com resultado NO ARMAZÉM (`_prev_finalized`): o
  histórico do End process e, sem ele, o do Run — nunca `glob` no disco, que
  desde o §434 não tem o histórico e achava o JSON legado de julho. Marcar
  depois do End process grava no HISTÓRICO (é dele que a tela e o dia seguinte
  leem). `check_payrec_carry.py` (armazém de verdade; os outros testes stubam o
  `_prev_finalized`).
- **Pay/Rec: o SWAP casa e liquida até R$20** (`_TOL_SWAP`, 21/10/2026, §665):
  o lado interno sai líquido do IR regressivo do cadastro, e o pago difere em
  alguns reais. A janela larga é uma passada PRÓPRIA no fim do `_reconcile`
  (`_swap_mate`), depois dos exatos e dos centavos — o casamento é só por
  VALOR, e no meio do laço o swap roubaria o par exato de quem vem depois. Ela
  exige o MESMO sentido e prefere a mesma contraparte (`_cpty_key`). Quem diz
  que é swap é o lado JPM (a perna do cliente chega pelo SPB como NDF). O
  carry-forward e o match manual usam a mesma janela (`_manual_tol`: todo o
  lado JPM da seleção SWAP **ou EQUITIES** — `_MANUAL_TOL_SWAP_PRODUCTS`, §668;
  a tela recebe `data-match-tol-swap` e a lista em
  `data-match-tol-swap-products`, sem literal no JS). No MOTOR o EQUITIES segue
  no R$1, como o resto. `check_payrec_swap_tol.py`.
- **Pay/Rec: UM arquivo por TIPO na pasta de insumos** (mesa, 21/10/2026,
  §668). O tipo é o `_classify_source` (pelo nome, por dentro: a cópia
  `HistoricoMensagensJPM_… (1).csv` é o mesmo tipo do original; JPM e MGT são
  dois). Fica o salvo por ÚLTIMO e os outros do tipo são APAGADOS
  (`_one_per_kind`), nos dois caminhos do Run: na pasta vale o mais recente
  (`_saved_at` = o maior entre modificação e CRIAÇÃO — copiar pelo Explorer
  preserva a modificação do original); pelo dropzone o que chega vence o da
  pasta, e no lote vence o último. Apagar que falha (arquivo aberto no Excel)
  fica avisado no log e o arquivo não é lido. Tipo desconhecido não entra na
  disputa. `check_payrec_run.py` §1b.
- **Pay/Rec: as três listas são DataTable, com o funil** (mesa, 21/10/2026,
  §666); o Summary segue tabela comum (ordenar levaria o TOTAL para o meio).
  A instância é UMA por tabela: o `render` roda de novo a cada Justify, Cancel
  e Match, e só troca as linhas (`clear` + `rows.add` + `draw(false)`) —
  recriar apagaria os funis no meio do trabalho. **As marcas da linha** (Branch,
  Manual e **Tolerance**, a do Settled que o motor casou sem bater no centavo:
  `|difference| ≥ 0,005`, fora o match manual) são pílulas com o texto no
  `::before` (`data-tag`): no nó, "BANCO X Branch Reversal" viraria outra
  contraparte no funil. `check_payrec_run.py`.
- **Pay/Rec: o match manual é UMA linha no Settled** (mesa, 21/10/2026, §670):
  o `_apply_groups` grava o grupo pelo `_manual_settled_row` — o lado JPM e o
  do cliente na mesma linha, os totais, a diferença Cliente − JPM e as pernas
  originais em `manual_rows`. O dia gravado antes junta as pernas soltas na
  LEITURA (`_junta_manuais`, no `load_last` e na resposta do Match), sem
  regravar. `check_payrec_manual_match.py`.
- **Pay/Rec: o botão Match casa À MÃO o que o motor deixou solto** (mesa,
  02/10/2026, §617/§623): duas ou mais linhas marcadas do Pending Payment e/ou
  do Pending Receivement, só as de UM lado (a que tem JPM e cliente já foi
  casada pelo motor), da MESMA contraparte pela `_cpty_key(_norm_cpty(…))` —
  as variantes dos fundos e do Banco (Atacama, Lawton, `BCO J.P`) viram uma só;
  a TELA tem a cópia (`normCpty` + `cptyKey`) e a paridade é EXECUTADA no `node`
  (`check_payrec_manual_match.py`, §668: sem o `normCpty` a janela travava o
  botão para o Atacama por extenso). O LADO de cada
  linha (JPM ou Client) decide a conta (`_manual_balance`): com os DOIS lados
  presentes é PAR — total JPM × total Client, a DIFERENÇA dentro de
  `_MANUAL_TOL` (= `_TOL_SETTLED`); só um lado é ESTORNO — a SOMA dentro dela.
  Exigir débito × crédito deixava o Match apagado para duas pernas JPM e uma
  Client no MESMO Pending Payment, que é o caso mais comum. O servidor confere tudo de novo e recusa
  por código (`match_*`). O grupo vai para `manual-matches/<data>.json` e é
  **reaplicado no fim de todo Run** (`_apply_manual_matches`) — o Run regrava o
  dia do zero, e gravado só no resultado o par voltaria a Pending; linha que
  sumiu do insumo derruba o grupo inteiro (log), nunca metade. O Summary não é
  recalculado (ele vem dos insumos crus). `check_payrec_manual_match.py`.
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
- **Pay/Rec: a Branch Settlement sai do OPERATIONS B3, pelas CONTAS** (§560,
  G&O "Branch Settlement Control"). Só as liquidações 04880.00-6 (MGT própria)
  × 73760.20-5 (guarda-chuva do Banco para o cliente da MGT): a **reversão** é
  o net delas × −1 (a 205 pagou a MGT → na reversão a MGT paga o Banco) e vira
  UMA linha `branch: 'reversal'` no Pending Payment/Receivement. **Ela casa
  com o extrato da MGT** (§566, `_reversal_leg`): a TED contra a conta
  `/OTC DERIVATIVES PRODUCTS` do Banco no RLDOCREC (ou o interbancário da MGT),
  no sentido OPOSTO, dita na visão do Banco — nunca com o LTR do JPM, que é do
  B2B, nem com perna de cliente; a conta do Banco nunca é par de cliente. As contas são
  do `b3-accounts` por LE × TIPO (`commands.branch_accounts`), nunca número no
  código. **O B2B é o net de TODA liquidação Banco × MGT**
  (73760.00-9 × 04880.00-6 **mais** 73760.20-5 × 04880.00-6, visão do Banco;
  mesa, 25/09/2026) e casa com o LTR do Histórico de Mensagens JPM: tem a sua
  linha (`branch: 'b2b'`) no Pay/Rec e fica fora do e-mail. A rota ANTIGA
  (04880.00-6 × 04880.10-9) fica fora da conta, avisada no log e no `.eml`, até
  o cenário ficar só na 205. O botão **Branch Settl.** só existe com a rota nova
  e na data de HOJE; baixa um `.eml` (X-Unsent, sem `From`) para o VP com as
  contas de origem/destino do Counterparty Details (default APROVADO; faltando,
  aviso por código) e a lista das operações — contraparte, bruto e IR vêm do
  Cockpit pelo B3 ID. Destinatários no card `branchsettlement` do Control Panel.
  A perna intragrupo do Cockpit (`BANCO J.P MORGAN S.A`, sem o ponto) não entra
  mais no lado JPM como cliente (`_entity_side`). `check_payrec_branch.py`.
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
- **Tax ID é CNPJ formatado no FUNIL** (`cgd_docs.fmt_cnpj`, `TAXID_COLUMNS`,
  no `padroniza` e na leitura do `load_all`): entidade a entidade (`;`),
  12–14 dígitos viram `xx.xxx.xxx/xxxx-xx` com o zero perdido de volta; CPF,
  estrangeiro e `N/A` ficam como vieram. O modal (Add Row/Edit e a edição em
  massa) tem a máscara de CNPJ e a `otcDateMask` nas datas; a Legal Name não
  corta (uma entidade por linha).
- **O New Request toca o sino de BO e MO** (#OTC-0045, §604), as mesas das
  etapas OTC e CEM MO (Legal não é papel no app); só o New Request, não a
  edição. Rótulo `Onboarding` → Tracking Docs nos três mapas; melhor esforço.
  **O prefixo do anexo sai do Doc Type** (#OTC-0046): o subtype do upload ao
  EI era `CGD TEMPLATE` fixo no JS, e o CSA era gravado como CGD. O mapa é do
  servidor (`cgd_docs.appendix_subtypes`: `CSA TEMPLATE`, `APPENDIX
  TEMPLATE`…); arquivos já gravados não são renomeados.
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

- **Os campos From/To se DIGITAM** (§508): o clique seleciona o texto, a
  máscara põe as barras (`22082026` → 22/08/2026), e o calendário acompanha —
  com dia e mês ele vai para o mês, com a data inteira ele a escolhe (o
  `clickApply`, e o callback grava o `state`). Desde 22/10/2026 isso é do
  `date-std.js` para todo daterangepicker do app (§675); o `typeableDate` do
  `quotes.js` ficou só com o Enter, que dispara a busca. **O `keyup` do
  daterangepicker é desligado**: ele relê o texto com parse frouxo do moment e
  desfazia a navegação no meio da digitação. Data futura é puxada para hoje (o
  `maxDate`), e texto pela metade volta à última data válida ao fechar — quem
  reescreve é o próprio plugin, no `hide`.

### Save CETIP Files

- **Os crus chegam na Return do Batch Conecta, compactados e num ENVELOPE**
  (20/10/2026, §643): `73760_CETIP_261019_SP_<arquivo>[.txt].zip.S<seq>`. O
  SISTEMA pode ter HÍFEN (`CETIP21-DEP`, `CETIP21-SAP`, §645) — sem ele no
  `_CETIP_ENVELOPE`, esses arquivos nem eram vistos e ficavam na Return. A
  rotina compara pelo nome ANTIGO (`domain._cetip_nome_legado`: sem o
  participante, o `_SP`, o `.zip` e a sequência), então o cadastro
  `cetip-files` vale como está e o SOURCE aceita as duas grafias. Ela TRAZ os
  da data para a pasta de origem do dia (byte a byte, nome como chegou), abre o
  zip num temporário (`_cetip_texto_cru`: um arquivo só, senão erro), salva no
  destino como sempre e só então APAGA da Return o que já está na origem — o
  que não se copiou fica lá. A Return é a mesma dos Mapping B3 ID: só se toca no
  envelope do participante 73760 e da data (retorno de registro, outro dia,
  outro participante ficam). Duas entregas do mesmo arquivo: vale a sequência
  maior. Reprocessar um dia lê da origem. `check_cetip_return.py`.
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
- **As agendas do FX Holiday Schedule saem do REGISTRO**
  (`fx_schedule_names`, §607), nunca de `listdir` da raiz de dados: no armazém
  isso abre TODOS os bancos de `db/`, e um banco de posição preso no share
  pendurava o GET — e as páginas de New Deals que o chamam na abertura ficavam
  sem toolbar. Vale para qualquer request: nada de `listdir`/`walk` da raiz.
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
- **Varredura de TODOS os templates é `_fi_all_templates()`** (§609),
  single-flight por pasta e leitura PARALELA (`OTC_FI_READ_WORKERS`, 8): o
  `page-spec` (chamado por toda página de New Deals ao abrir) passa com
  `espera=False` — leitura em voo é 503 na hora, sem segurar thread — e o
  `_fi_variant_key` espera. Frio, no share, são ~40 aberturas de 5-10 s
  (§610). Não escreva outro laço de `listdir` + `_fi_tpl_cached` na pasta.
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

- **O id da linha no sino é a REFERÊNCIA da tela, não a chave interna**
  (§558): nas telas de Intrag o `deal_id` das rotas é o Athena ID (o `_deal`
  das páginas que nascem do New Deals) e a mesa fala em B3 ID — o texto passa
  por `intrag/entrypoint._notif_ref` (B3 ID da linha, sem ele a chave).
  `check_intrag_notif_ref.py`.
- **Cópia para outra tela que falha é DITA na tela** (§696): espelho de
  melhor esforço (Pending Confirmation, esteira, Intrag) chama
  `platform/mirrors.falhou(alvo, ref, exc)` no `except` — além do log, o
  `after_request` põe no `X-OTC-Mirror-Failed` de `/api/*` e o
  `session-guard.js` avisa depois do Swal da página. `_pc_save_from_deal` e
  `_mc_save_from_deal` devolvem o veredito (True/None/False). Tela não afirma
  cópia que não conferiu ("sent to Intrag" saiu). A remoção que não saiu (a
  recompra apagada) é `falhou(..., remocao=True)`, com frase própria.
- **A linha da Intrag acompanha a origem que muda de dia ou de chave** (§701):
  a gravação da Intrag procura só no dia de destino, então quem muda o Trade
  Date/Data da Recompra ou o Deal LEVA a linha antes
  (`persistence._intrag_relocate`, pelos `_intrag_follow*`; nos swaps
  `swap_new_deals.intrag_follow`). Edit novo que muda o dia de uma origem com
  espelho na Intrag chama o mesmo, senão a operação aparece duas vezes.
- **Aviso do PRÓPRIO sistema mostra o logo** (ator `SYSTEM`/"OTC Tracker"): no
  sino e no toast o ladrilho do sidenav, na cor do accent (`isSystemNotif`,
  `topbar.html`). Rotina nova que avisa no sino usa esse ator.
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
  o box de commodities e a API da recompra. `check_import_window.py` §5 varre
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
- **O one pager executivo (`Docs/OTC_Tracker_One_Pager.html`, §663) é HTML
  autocontido, não tela do app**: PT e EN no mesmo arquivo (par de `<span
  lang>`; texto novo vai nos DOIS), abre em inglês, cabe na janela por zoom
  (busca binária) e imprime em UMA A4 deitada pelo `zoom: .61` da impressão.
  Mexeu no conteúdo: confira o PDF nos dois idiomas — o PT, mais longo, é o
  que passa para a segunda folha. Texto para a diretoria: "equipe", nunca
  "mesa".
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
  no venv + `/dev-login` do DEV BYPASS. No Stratos ela também não existe, e o
  `otc_stratos.py` (`_garante_awmpy`) põe no lugar uma casca do
  `stratosblocks.utilities.get_phonebook_data([sid])`, com as mesmas chaves
  (`nameFull`, `email`, `positionName`): o `routes` não muda, e a chamada
  `awmpy.get_phonebook_data(sid)` do `get_user_data_from_phonebook` e as três
  chaves que ele lê são o contrato da casca. Fora dele, o pedido de acesso do
  Stratos nasce com o nome do SSO, sem o e-mail do phonebook nem o cargo, e a
  tela não acusa nada (no máximo um `[phonebook] FAILED` no log) — o
  `stratos/tests/check_stratos.py` pega. A dev nunca importa o
  `stratosblocks` (§678).
- **macOS: porta 5005.** `duckdb` e `flask-minify` obrigatórios.
- **`OTC_SHARED_DRIVE_ROOT` obrigatória fora do Windows** (o app recusa valor
  relativo; `I:\` é relativo em qualquer sistema que não seja Windows — as
  pastas `I:\Confirmation\...` na raiz do repo vieram daí).
- **SMTP** `mailhost.jpmchase.net:25` sem auth; fora da rede falha em silêncio.
  **No Stratos o relay não responde**: a ponte troca o `smtplib.SMTP` pelo
  Email block do stratos-blocks (`stratos/src/email_stratos.py`, §691; os
  senders não mudam, porque todos leem `smtplib.SMTP` na hora do envio). Sender
  novo usa o mesmo `with smtplib.SMTP(...) as server: server.sendmail(...)`;
  imagem do corpo vai por `cid:` (o block casa pelo NOME do arquivo, e a ponte
  reescreve o `cid:`). `OTC_STRATOS_EMAIL=0` volta ao SMTP.
- **Athena**: `build_session()` com `trust_env=False` (o proxy corporativo
  causava `WinError 10061`); no Windows exige `requests-negotiate-sspi`
  (declarado com marcador de plataforma; sem ele `401` no
  `/adfs/oauth2/authorize/wia`, e o `build_session` LEVANTA nomeando o
  pacote). Três timeouts: `REQUEST_TIMEOUT` 30 s (um produto/dia),
  `REPORT_TIMEOUT` 180 s (EOD da Recon FXO, Intrag DCE, `getTradesBySettle`),
  `CONNECT_TIMEOUT` 10 s; cadastráveis, malformado cai no padrão com aviso.
  `check_athena_sso.py`.
- **BCB/Yahoo (Quotes)**: mesma sessão, proxy volta como FILA (`QUOTES_PROXY`,
  a 9443 → proxy do sistema COPIADO → direto), primeira que responde fica. A
  porta antiga do desktop saiu da fila e não se escreve nem em comentário
  (§677: o scan do Stratos recusa); no Stratos o `QUOTES_PROXY` é vazio e a
  rota do sistema é o proxy dele.
  **O proxy do JPM responde 407 e o `requests` não sabe autenticar nele**
  (o SSPI negocia com o servidor, não com o proxy): as Tools
  (`precificador/rede.py`) caem para o WinHTTP com auto-logon e, por último,
  o WinInet da macro da mesa (§450); a Quotes ainda não tem essa queda.
  **No Stratos o Codex (a API de dados de mercado do JPM) pode tomar o lugar
  do Yahoo** — em investigação no §679, com a sonda `stratos/sonda_codex.py`
  (só na branch do Stratos): a ponte (`otc_stratos.py`) embrulharia o
  `quotes.fetch_ohlc` sem mexer na dev — todo chamador o lê pelo atributo do
  módulo —, com o identificador do Codex numa coluna NOVA do cadastro
  `quotes-equity` (nunca regra no código) e o Yahoo como queda para o símbolo
  sem esse identificador, para o que falha e fora de request (o token do
  Codex é do usuário logado; rotina de fundo não tem usuário). No desktop ele
  também livraria do 407 o que a Quotes busca no Yahoo; fica para decidir.
- **A instância roda sem reloader**: pull que tocou `.py` ou template exige
  restart. Mapping pela tela é a exceção.
- **A instância roda com o DebugConfig** (o ProductionConfig exige cookie
  seguro e ela é HTTP). Por isso o que é só da DEV pergunta
  `app.config['OTC_LIVE_RELOAD']` (DEBUG **e** o `flask run`, que marca
  `FLASK_RUN_FROM_CLI`), nunca o DEBUG: recarga de template e o `stat` do
  `asset_v` por DEBUG eram ~17 idas ao share por página (§636).
  Estático com o token atual (`asset_v`) sai imutável no cache; token escrito
  à mão segue revalidando.
- **`PYTHONPYCACHEPREFIX` no `.bat`** apontando para `%LOCALAPPDATA%` (nunca
  `%TEMP%`, nunca `PYTHONDONTWRITEBYTECODE`): sem isso a subida fica minutos
  gravando `__pycache__` no share sem imprimir nada. O `start-otc-tracker.bat`
  roda do share, mas desde 21/09/2026 é VERSIONADO (§518) — fora do repo ele
  ficava fora da revisão e do `check_bat_blocks.py`, e foi por isso que a linha
  do §322 nunca chegou nele. Copie o do repositório por cima do que está no
  share; o que a instância executa é o de lá, e o `otc-tracker.ico` vai junto,
  na mesma pasta.
- **O `start-otc-tracker.bat` sobe com DUPLO CLIQUE, sem DevShell** (§628): o
  app roda no 3.13 e no 3.12, e o `.bat` **procura o 3.13 PRIMEIRO e, sem ele,
  o 3.12** (§653) — em cada um, o PRÓPRIO em `%LOCALAPPDATA%\OTC-Tracker\
  python313`/`python312`, depois o do usuário, pelo `HKCU`, e por último o
  `python` do PATH na versão certa — o do **DevShell**, que não se registra no
  `HKCU` (§667); o `OTC_PYTHON` (caminho do `python.exe`) vence a busca toda.
  **Em parte das máquinas a política de grupo BARRA o instalador do
  python.org** ("This program is blocked by group policy", §667): ali o Python
  é o do DevShell (`ds tool install python3.12`) — abrir o `.bat` de dentro do
  DevShell, ou `setx OTC_PYTHON` uma vez. Máquina que já
  sobe pelo 3.12 fica nele até ganhar um 3.13 (para migrar: um 3.13 do
  usuário, ou apagar a `python312` — o `.bat` instala o 3.13 sozinho). Sem
  Python nenhum ele instala o 3.13 (`PY313_VERSION`) e, sem o instalador dele,
  o 3.12 — sem admin, a partir de `Application\installers\` ou do python.org,
  e só se o instalador for ASSINADO; `PIP_INDEX_URL` no Artifactory; o retrato do requirements DENTRO da
  pasta do Python; o navegador abre quando o servidor RESPONDE; e atalhos com
  o `otc-tracker.ico` no Desktop e na pasta `Application` (alvo `cmd.exe /c`,
  para poder FIXAR; uma vez por máquina e por lançador, `atalho <nome>.ok`). O
  `.bat` não tem ícone próprio — o Windows desenha um só para todo `.bat`, e
  `.exe` não roda na máquina do JPM —, por isso o atalho. O e-mail de versão
  nova e o card falam em duplo clique (`check_app_version`). **O
  `start-otc-tracker_naeast.bat` é só um LANÇADOR** dele (`OTC_NOME`,
  `OTC_LAUNCHER`, `OTC_ESPELHO_LOCAL=1`): a lógica é uma, e os dois `.bat` vão
  juntos para a mesma pasta.
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
  relativos ao diretório atual. Hoje é a sub-rotina `:espelha` do
  `start-otc-tracker.bat`, ligada pelo lançador `start-otc-tracker_naeast.bat`
  (§628), e o §524 lista o que falta para virar o padrão. **O código de saída do
  robocopy é um BITMASK**: 0–7 é sucesso, 8+ é falha — `if errorlevel 1`
  abortaria em toda cópia bem-sucedida. E **`/COPY:DAT` PRESERVA o timestamp da
  origem**: data de arquivo no share não diz quando o deploy rodou (foi o que
  me fez descartar esta hipótese uma vez).
- **O `hotfix.bat` leva a correção pontual para a versão NO AR** (o que
  difere entre o checkout da `StreamFlow-prod` e a pasta do `link.txt`; sem
  argumento lista, `hotfix apply` copia) e, como o `stratos-sync.bat`, **puxa
  do GitHub antes** (§688): `git pull --ff-only` em bloco com auto-chamada,
  branch conferida e `apps\` sem nada fora do git — pull que falha ou checkout
  sujo só lista, o `apply` recusa. A correção nasce no repositório (dev → prod
  pelo merge), nunca editada no checkout da máquina.
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
- **A versão do DuckDB tem de ser a MESMA em todas as instâncias** (§651): um
  banco CRIADO por uma versão nova (o 2.0) não abre na antiga ("version number
  999, but we can only read 64-68"), e o armazém cria `.db` o tempo todo — uma
  máquina adiantada faria bancos que as outras leem como ILEGÍVEIS. Troca de
  Python (o 3.13 foi verificado: o app sobe e a suíte passa) não obriga a
  trocar o DuckDB; troca de DuckDB é de todas as máquinas juntas. Por isso o
  `requirements.txt` diz **`duckdb>=0.10,<2`** (§653): o PyPI já entrega o
  2.0.0, e todo Python NOVO (o 3.13 que o `.bat` instala) faz `pip install`
  do zero. Subir o teto é decisão de todas as instâncias juntas.

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
| `fill_cgd_from_refdata_spn.py [--dry-run] [--force] [--db] [--refdata]` | completa o Tracking Docs pelo **SPN**: Economic Group, ECI, CASID e UCN do Reference Data. Chave de dígitos (sem zero à esquerda e sem `.0`), célula com o grupo (`;`) junta os valores, **SPN ambíguo no cadastro não preenche** a coluna divergente, só o vazio (`0`/`N/A` contam) sem `--force`, UMA abertura do banco (`cgd_docs.update_rows`). `check_cgd_spn_fill.py` |
| `fill_fepweb_ids_fwdstart.py [--gravar]` | preenche o FepWeb ID do Pending das confirmações de NDF FWD Start JÁ geradas (§703: o Save procurava a linha pelo Deal, e a do FWD Start é chaveada pelo B3 ID). Lê o `numeroContrato` do XML ao lado do PDF do `Confirmation Link` da esteira e só preenche o vazio; sem `--gravar` só relata; idempotente |
| `import_file_interpreter_template.py [--key <k>] [--force] [--dry-run]` | leva ao BANCO um template do File Interpreter corrigido no repositório. O `.json` versionado é a SEED, e a semeadura da subida não sobrescreve o que o banco tem (§434/§488): sem este script o motor segue lendo o layout velho e o arquivo vai errado para a B3, sem erro nenhum. Template que o banco tem EDITADO (algum `source` preenchido) fica de fora sem `--force` |
| `migrate_unwind_esteira_keys.py [--gravar]` | leva as recompras do Pending e da esteira da chave antiga (Athena ID cru / Deal ID) para a PRÓPRIA (`UNW-…`, §696): a linha `UNWIND …` da chave antiga muda de chave (destino primeiro), a confirmação ORIGINAL que a recompra reescreveu no Pending é refeita pelo `_generic_nd_pc_trigger` (o que a equipe tinha preenchido nela não volta — a lista sai no fim) e a recompra que nunca entrou na esteira entra pela porta do import. Sem `--gravar` só relata; idempotente |
| `split_notifications_db.py --dry-run` | mostra o que a separação do sino vai copiar |
| `dev_seed_positions.py` | só na DEV: reemite a última posição B3 numa data recente (`--from … --force`) |
| `convert_json_to_duckdb.py` + `scripts/convert/` (40 fatias) | a IMPORTAÇÃO JSON → DuckDB (o cutover do §434 e o legado fora da janela), incremental por `_manifest`, `--meses` 12 por padrão (`0` = tudo), `--only/--force/--dry-run/--bloco`; reconverte sozinho o payload-objeto sem `__raw` |
| `slim_duckdb.py [--db-dir] [--only cache] [--dry-run]` | emagrece os bancos de arquivo-dia JÁ existentes para a forma do §437 (lista só `_seq`/`_raw`, objeto só `__raw`), copiando do PRÓPRIO banco e trocando o arquivo; com o app PARADO; idempotente; RECUSA banco em limbo de checkpoint (vai pelo recover); o `_manifest` é recriado pelo SCHEMA e não por `AS SELECT` — o CTAS deixa a PRIMARY KEY para trás e o banco vira somente-leitura (§443) |
| `recover_duckdb_wal.py [--db-dir] [--only] [--work-dir] [--dry-run] [--no-slim] [--all] [--descartar-wal]` | tira do LIMBO de checkpoint (§442: `.wal.checkpoint`/`.wal.recovery` ao lado, ou `.wal` > 16 MB) copiando `.db` + WALs para um disco LOCAL, abrindo em escrita + `CHECKPOINT`, emagrecendo e trocando no share; o que substituiu vai para `db/_recuperado/<carimbo>/` (apague depois de conferir); TODAS as instâncias paradas, mesma versão de duckdb (banco preso por processo VIVO é PULADO com `EM USO`, sem tocar em nada — `--lock-seconds` regula a espera e `--insistir N` fica tentando os pulados, porque a trava do vizinho vai e volta); a cópia local perde o somente-leitura herdado do share, a pasta de `--work-dir` é PROVADA (renome) antes de qualquer cópia e o `.wal.recovery` — que É a fusão do `.wal` com o `.wal.checkpoint`, e o destino que o `MoveFileW` do DuckDB recusa — não vai para a cópia local quando os dois estão lá; rename negado na abertura da cópia faz o script FUNDIR os dois WALs à mão, por cópia, e abrir de novo (§444); `--only` aceita um `.db` só, e `--descartar-wal` é o WAL que NÃO REPLAYA — segue com o `.db` sozinho, perdendo o que veio depois do último checkpoint (§447) |
| `export_duckdb_to_json.py` | o ROLLBACK: reconstrói do banco os JSONs com diferença (`--dry-run`, `--force`, `--only`); `check_export_rollback.py` prova que cada forma volta exata |
| `scripts/standalone/` (GERADOS por `build_duckdb_standalone.py`) | os mesmos conversores para máquina sem o código (`pip install duckdb` só): o motor UMA vez no `_motor.py` e uma casca por fatia — entrega-se a PASTA; nunca editar à mão |
| `build_sop_docx.py` | SOP e Guia em Word a partir do `.md` |
| `fix_asian_dates_xlsx.py <xlsx> [--dry-run] [--feriados CAL=arq] [--calendario IPE]` | conserta as datas da Média Asiática de um Excel do Live Position Option numa aba NOVA (§537): mesmo mês → reordena; dois meses → o mês com MAIS datas inteiro, dia útil a dia útil no calendário do Holidays **do ATIVO da linha** (`Ativo subjacente / Moeda base`: `CO1-2` → IPE, `USD` → ANBIMA, §595; ativo fora da lista NÃO é ajustado e vai para o log; planilha sem a coluna usa o `--calendario`); empate fica e vai para o log; data em fim de semana ou feriado do calendário do ativo é REMOVIDA antes de decidir (a mesa, 29/09/2026), e o ano de toda data precisa ter feriado no calendário. Calendário sem feriado no ano PARA — sem feriado, dia útil vira dia de semana |
| `diag_ndfsum_account.py [AAAA-MM-DD]` | DIAGNÓSTICO da coluna Account do Settlement Summary: nome da linha → SPN no Reference Data → registro do Counterparty Details → defaults → conta, dizendo onde a cadeia quebra (§436) |
| `diag_pending_confirmation_db.py [--db backlog\|pending\|ok\|todos] [--db-dir] [--out] [--csv] [--so-resumo]` | DESPEJA o conteúdo dos três bancos do Pending Confirmation (uma aba por banco) e, na tela, o RESUMO que costuma responder a pergunta: linhas, a Trade Date mais velha e a mais nova, o histograma por ano e **quantas linhas têm data ILEGÍVEL**, com amostra do texto cru. "A busca não traz nada antes de tal dia" tem duas causas que se parecem e se consertam ao contrário — não há nada mais velho, ou há e a data está num formato que o app não lê (serial do Excel, `26/8/25`), e aí a linha some de todo filtro por data sem erro nenhum. Só LÊ, roda com o app de pé (abre pelo `duckdb_read`), e banco em uso ou ilegível **para com o motivo** em vez de imprimir zero linha. O `.xlsx` sai com toda célula como TEXTO (o contrato `26E04610365` vira `#NULL!` numa célula numérica, §477) |
| `diag_boot_imports.py` | DIAGNÓSTICO da SUBIDA (§522/§524): `python -X importtime` num subprocesso, com o farol do app passando direto para a tela e um pulso a cada 5 s (segundos · módulos · último módulo) — saída que demora tem de dizer que está viva, senão doze minutos de subida são indistinguíveis de um travamento. Rodá-lo de um clone LOCAL é o CONTROLE do experimento, não erro de uso: mesmos dados no share, só o código em disco local — caiu de minutos para segundos, o custo é ler o código pelo SMB; não caiu, é o que o import EXECUTA. Vale rodar os dois |

`apps/static/data/db/` é gitignorado: bancos não vêm no pull. Telas vazias
depois de um pull são migração não rodada, não bug.

### `scripts/tests/` (222 scripts)

Autocontidos, sem framework, `ok`/`FAIL` por asserção, saída 0/1, sem tocar
dado real (tmp, stubs de Outlook/SMTP). O
[`README.md`](scripts/tests/README.md) mapeia script → módulo — **rode o
correspondente depois de mexer no módulo**, com
`OTC_SHARED_DRIVE_ROOT=/tmp/otc-share`. Vários sobem o app e trocam atributos
no `routes` (por isso a regra de import atrasado do §3). Os que MEDEM em vez
de conferir texto: `check_stat_por_linha`, `check_duck_gate`,
`check_daycache` §8, `check_db_read_path`, `check_page_switch` §1. `check_boxparse` precisa do `jsc`.

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
