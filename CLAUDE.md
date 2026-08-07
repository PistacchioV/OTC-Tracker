# CLAUDE.md

Guia para o Claude Code (claude.ai/code) trabalhar neste repositório.

O OTC Tracker é uma aplicação Flask que cobre o ciclo de vida de derivativos de
balcão: registro, economic affirmation, liquidação e documentos transacionais.
É uma aplicação **interna do JPMorgan**, servida de um processo único para uma
mesa inteira — o que explica quase todas as regras não óbvias abaixo.

---

## 1. Comandos

```bash
# Ambiente (o diretório chama-se .venv311 mas o Python é 3.12)
source .venv311/bin/activate
pip install -r requirements.txt

# Desenvolvimento — no macOS use 5005, NUNCA 5000 (ver §8)
flask run --port=5005

# Produção (Gunicorn, 0.0.0.0:5005)
gunicorn --config gunicorn-cfg.py run:app
```

```bash
# Front-end
npm install          # ou bun install
npm run dev          # gulp em watch: SCSS → CSS
npm run build        # compilação única
```

Copie `env.sample` para `.env` e defina no mínimo `FLASK_APP=run.py`. O modo
debug **não** vem do `.env`: é a flag `DEBUG` no topo do `run.py`.

Gulp compila `apps/static/scss/**/*.scss` → `apps/static/css/` e copia os
plugins de `node_modules` para `apps/static/plugins/`.

---

## 2. Regras da casa (as que não se negociam)

- **A branch de trabalho é `visual-refresh`** (desde 26/07/2026; `apple-design`
  foi incorporada e aposentada). Todo commit e push vai para lá — nunca presuma
  `main`.
- **Nunca fixe um de-para novo no código.** Qualquer coisa mapeável tem de ser
  cadastrável pela tela `/mapping` — é regra permanente do usuário. Ver §6.
- **O bloco DEV BYPASS (`/dev-login`) do `routes.py` nunca vai para o
  repositório.** Ele é removido antes de cada commit. Se o único diff do
  `routes.py` for esse bloco, basta não incluir o arquivo no `git add`.
- **Mantenha um processo só.** Ver §4 — com mais de um, os locks não protegem
  nada e os schedulers duplicam.
- **Design: tokens `--vr-*` e `--ins-*`, jamais `--bs-*`.** O tema não define os
  `--bs-*`, então eles caem no fallback claro e produzem cartão branco no tema
  escuro. Ver §7.
- **i18n: todo texto visível nasce em INGLÊS e é traduzido por `data-lang`**
  (arquivos `apps/static/data/translations/{en,br,es}.json`) — em toda página,
  SweetAlert incluído. O `I18nManager` do `app.js` traduz os `[data-lang]` UMA
  vez, no load: **o que o JS insere depois nunca passa por ele**. Texto montado
  dinamicamente (cards, itens de lista, SweetAlerts) sai de um mapa `_TRANS`
  local com `t()`, lendo `localStorage['__OTC_TRACKER_LANG__']` — o padrão do
  swapchar e do Confirmations Monitor. Texto de servidor que a tela exibe deve
  vir **estruturado** (a lista, não a frase), para a frase ser montada no idioma
  da aplicação.
- **E-mail: o cabeçalho é cor sólida + gradiente CSS, nunca imagem/VML.** O
  `<v:rect>` do Outlook pintava o banner ora mais estreito que a célula (faixa
  sólida à direita), ora na largura da janela inteira. Ver o comentário em
  `partials/email-gradient-header.html`; `_attach_email_gradient` é no-op de
  propósito.

---

## 3. Arquitetura

### Ciclo do request

`run.py` lê `DEBUG` → escolhe `DebugConfig` ou `ProductionConfig` de
`apps/config.py` → chama `create_app()` em `apps/__init__.py`. A fábrica
registra as extensões e descobre os blueprints iterando a tupla
`apps = ('pages',)`, importando `apps.<nome>.routes`.

Existe **um único blueprint** (`pages_blueprint`, em `apps/pages/__init__.py`)
que é dono de todas as rotas. A lógica vive em `apps/pages/routes.py`
(~29,3 mil linhas). Ao lado dele, `apps/pages/` guarda módulos auxiliares
importados pelas rotas — nenhum tem blueprint próprio:

| Módulo | O que é |
|---|---|
| `athena_api.py` | cliente da API `getTrades` da Athena (SSO Kerberos/ADFS — §8) |
| `confirmation_pdfs.py` | réplicas em reportlab dos documentos Word |
| `manual_conf.py` | a esteira de confirmação manual (os dois DuckDBs, as derivadas, o agrupamento) |
| `recon_fxo.py` | motor da reconciliação de FXO (DPOSICAO × Athena EOD) |
| `otc_boxparse.py` | parser do e-mail de booking recap |
| `otc_tickets.py` | store JSON do Support Center |
| `otc_emails.py`, `webpush.py`, `forecast_charts.py`, `otc_boxscan.py`, `recon_payrec.py`, `recon_comitente.py` | — |

**`confirmation_pdfs.py` tem um padrão a seguir:** FX Options é a exceção
correta. `opcao_fx_pdf()` monta o PDF a partir do *HTML já renderizado* do
documento (a mesma string que vira o `.doc`), via `_WordHtmlToFlowables` — as
duas saídas não têm como divergir. Documento novo deve nascer assim
(HANDOFF §139).

**`otc_boxparse.py` é a segunda cópia de uma regra que também vive no
navegador** (`static/js/pages/otc-fileupload.js`). As duas precisam concordar
campo a campo, e `scripts/tests/check_boxparse.py` é o que prova
(HANDOFF §157).

### Herança de templates

```
layouts/base.html            ← esqueleto HTML
  └── layouts/vertical.html  ← o único layout (menu à esquerda)
        └── pages/*.html
```

`layouts/horizontal.html` e `partials/horizontal-nav.html` **foram apagados**
(HANDOFF §175): eram a navegação de demonstração do template comprado.
`partials/sidenav.html` é o único menu do app.

### Adicionar uma página

1. Rota em `apps/pages/routes.py` devolvendo
   `render_template('pages/<nome>.html', segment='<nome>')`
2. Template em `apps/templates/pages/<nome>.html` estendendo um layout
3. Opcionalmente SCSS em `apps/static/scss/` (o Gulp pega todo `*.scss`)
4. Se a página tem tabela, ela segue o **padrão de tabela** abaixo — sem exceção.

### O padrão de tabela (referência: `new_deals-ndf-vanilla.html`)

Todo o app segue o desenho das páginas de New Deals. Página nova com tabela
nasce assim; página velha que divergir é bug de consistência (a varredura de
2026-08-07 alinhou Reference Data, Index B3, Mapping, os dois Summaries, as
Live Positions, o Track Confirmations e as três Recons).

- **Tabela centralizada.** `th`: `text-align:center !important;
  vertical-align:middle !important; font-size:.7rem` (quebra de linha
  permitida no header). `td`: `text-align:center; vertical-align:middle;
  font-size:.8rem; white-space:nowrap` (+ ellipsis nas colunas de dado).
  Com `scrollX`, os clones `.dt-scroll-headInner` / `.dataTables_scrollHeadInner`
  precisam das mesmas regras — o DataTables remove o id da tabela clonada.
- **Linha de filtro por coluna** como 2ª linha do `<thead>`, montada **antes**
  do `.DataTable()` com `orderCellsTop: true` (ver a armadilha em §7). Inputs
  pequenos (12px/28px), texto centralizado, placeholder = nome da coluna.
- **Botões de ação da linha**: **squircle** colorido — geometria única no app
  inteiro (spec `.ops-row-act`): **32×32 travado com min/max** (nenhuma regra
  de tema pode esticar um botão), `padding:0`, `border-radius:10px !important`,
  ícone Tabler `1rem`, tooltip colorido (`data-bs-custom-class="tooltip-{cor}"`).
  A classe `rounded-circle` ainda aparece no markup por história, mas **o CSS da
  página fixa o squircle** — sem o override o raio do tema sai OVAL, porque
  círculo só é círculo em botão já quadrado. Ordem e cores canônicas:
  **Confirm** `ti-check`/success → **Edit** `ti-edit`/info → **Delete**
  `ti-trash`/danger → **Send** `ti-brand-telegram`/primary; em modo edição,
  **Save** `ti-device-floppy`/success + **Cancel** `ti-x`/secondary. Wrapper
  `d-flex justify-content-center gap-1`.
- **Toolbar** — todos os botões levam `.btn-toolbar-all` (`font-size:.75rem;
  padding:.25rem .6rem`; hover `translateY(-1px)`, active `scale(.96)`), e as
  cores são fixas por função: **Columns** = `btn-soft-primary` (dropdown de
  checkboxes), **Add Row** = `btn-primary bg-gradient`, **Export** = `btn-info
  bg-gradient` (dropdown com ao menos CSV e Copy; exporta o que está NA TELA —
  filtros e ordenação aplicados, só colunas visíveis), **Import** = teal
  `#4a849b`, **Mapping/refresh** = `btn-success bg-gradient`, **Clear
  Filters** = `btn-outline-secondary`. `Show [N] entries` ao lado.
- **Alinhamento valor × coluna é parte do padrão**, e são TRÊS coisas — a Recon
  FXO saiu desalinhada duas vezes por ter só a primeira. Com `scrollX` o
  cabeçalho vive numa tabela irmã do corpo:
  1. depois de todo `rows.add(...).draw()` chame **`table.columns.adjust()`**,
     mais um segundo passe atrasado (`setTimeout(…, 150)` com
     `.adjust().draw(false)`) e um handler de `resize`;
  2. **`autoWidth: true`**. Com `false` o DataTables não mede nada e cada tabela
     é dimensionada pelo navegador a partir do próprio conteúdo — o cabeçalho
     carrega o nome longo e o campo de filtro, fica sempre mais largo, e o
     desencontro **cresce coluna a coluna**;
  3. as regras de `th` valem para o CLONE também. O DataTables **remove o id**
     da tabela do cabeçalho, então `#minha-tabela th` não alcança o cabeçalho
     que se vê: repita o seletor em `.dt-scroll-head thead th`,
     `.dt-scroll-headInner thead th` e `.dataTables_scrollHeadInner thead th`.
     Sem isso o header fica com a fonte e o padding do tema e o corpo com os da
     página, e as duas tabelas medem larguras diferentes. O header vai com
     `white-space: normal` — com `nowrap`, um nome longo impõe uma largura
     mínima que o corpo não tem.

  Confira o alinhamento em TODA tela nova antes de dar por pronta.
- **Seleção de célula para copiar — em TODA tabela, sem exceção.** Há dois
  caminhos, e conferir só um deles esconde metade das telas: New Deals e as três
  de Intrag usam a extensão `select` do DataTables (`items:'cell'`); todas as
  outras carregam o **`static/js/table-std.js`** e chamam
  `otcCellCopy('#id', { skip: [0, 1] })` **depois do `.DataTable()`** (skip =
  checkbox e Actions). Mesmo visual (azul `#b3d7ff`/`#0066cc`, hover
  `cursor:cell`, flash verde ao copiar), Ctrl/Cmd+C copia com `\t`/`\n` (cola
  no Excel), Esc limpa. O helper é idempotente e delega no nó da tabela, então
  sobrevive a redraws; ele ignora cliques em `input`/`select`/`button`, então
  convive com edição na linha. Numa página que monta **uma tabela por card**
  (Accrual e MtM de Swap), a chamada é por tabela, dentro do laço — um seletor
  fixo pegaria só a primeira.
- **Linha de filtro por coluna: texto e placeholder centralizados**, e isso vem
  do `visual-refresh.css` (`table thead th input[...]`), não de cada página. O
  seletor é estrutural porque cada tela batiza a classe do próprio campo, e era
  essa repetição que fazia a tela nova nascer sem a regra — 10 das 27 páginas
  com filtro por coluna estavam sem ela.
- **Números.** Valor sai em `#,##0.00`
  (`toLocaleString('en-US', {min/maxFractionDigits: 2})`) com
  `font-variant-numeric: tabular-nums`. **Taxa não é valor**: Strike fica com as
  casas que tem (a Recon FXO usa 8) — duas casas fariam dois strikes diferentes
  aparecerem iguais na tela. A formatação é **ortogonal**: só o `display`; o
  `sort` sai pelo número cru (senão `1,000.00` vem antes de `9.00`) e o `filter`
  pelo texto que está na tela, porque quem digita no filtro copia o que vê.
- **Status** sempre como badge pill `bg-gradient` (mapa de cores por status).

---

## 4. Bancos e concorrência

São dois bancos:

- **DuckDB** (`Users_OTCTracker.db`) — tabelas `users` e `verification_codes`.
  `DB_PATH` é **relativo**, resolvido a partir do diretório do módulo
  (`apps/static/data/db/`), então funciona em qualquer máquina.
- **SQLite** (`apps/db.sqlite3`) — Flask-SQLAlchemy. Hoje **não é usado** pela
  lógica da aplicação; `configure_database()` chama `db.create_all()` **uma vez
  na subida**, não a cada request.

> Se o DuckDB recusar abrir depois de rodar sob outra versão
> (`INTERNAL Error … replaying WAL`), renomeie o `Users_OTCTracker.db.wal`
> perdido para o lado — o `.db` principal está íntegro.

### A parte que quebra o app para todos

O app serve vários usuários de **um processo só**, então isto importa mais do
que parece:

- O DuckDB de usuários é uma **conexão singleton atrás de um lock global**
  (`_duckdb_conn_lock`). `get_db_connection()` devolve um `_DuckDBHandle` que
  **segura o lock até o `close()`**. Todo chamador tem de ser
  `conn = get_db_connection()` seguido de `try: … finally: conn.close()` — os
  21 chamadores atuais são. Sem o `finally`, o lock nunca é liberado e **o app
  inteiro trava para todo mundo**, não só para o request que falhou.
- **Nunca faça trabalho lento segurando o lock** (rede, SMTP, varredura de
  arquivos, renderização de template). `_push_notify` é o modelo: lê a lista de
  inscritos, fecha, e só então dispara os HTTP pushes. A topbar consulta
  notificações a cada 8 s por aba aberta — esse lock é tomado o tempo todo.
- Conexões por banco (os DuckDBs do Pending Confirmation) são abertas sob
  demanda com retry/backoff e **têm de fechar no `finally`**: uma conexão
  vazada segura o lock de escrita pela vida do processo e derruba a página.
- Caches JSON (arquivos-dia do New Deals, mappings, MTM) são
  read-modify-write, então precisam de `with _cache_lock:` em volta do ciclo
  **inteiro** (ler → alterar → `_atomic_write_json`). A escrita atômica sozinha
  evita corrupção, não perda de atualização. `_cache_lock` é um `Lock` comum
  (**não reentrante**): nunca chame um helper que trava de dentro de um bloco
  travado.
- **Escale com threads, não com workers.** Produção é waitress
  (`start-prod.bat`, 4 threads) e o `gunicorn-cfg.py` fixa `workers = 1`. Com
  mais de um processo o singleton e o `_cache_lock` não protegem nada, o banco
  de usuários não abre no segundo processo e cada processo sobe os próprios
  schedulers (pulls duplicados).

### SQL injection

Referência: [`Docs/SQL_Injection_Prevention_Cheat_Sheet.md`](Docs/SQL_Injection_Prevention_Cheat_Sheet.md)
— o cheat sheet da OWASP, vendorizado no repo (CC BY-SA 3.0, cabeçalho de
proveniência no topo; para atualizar, rebaixe o arquivo, não edite à mão).

O código já segue a defesa primária e precisa continuar assim:

- **Todo valor vindo de request, sessão, planilha ou e-mail entra como
  parâmetro `?`**, nunca interpolado:
  `conn.execute("SELECT Page_Access FROM users WHERE SID = ?", [sid])`. No
  DuckDB a lista de parâmetros é o segundo argumento do `execute`;
  `executemany` para lotes.
- As poucas queries com `'...{}'.format(...)` são **DDL sobre identificadores
  do próprio código** (`_PC_TABLE`, colunas de `_PC_COLUMNS`) — nome de tabela
  e de coluna não podem ser bindados, e é o único caso que o cheat sheet
  permite montar string. Mantenha essas listas como constantes de módulo: no
  instante em que um nome puder vir do request, ele precisa de validação
  contra uma tupla fixa (a "Defense Option 3"), não de escape.
- O login é por SID vindo do phonebook, mas o SID **ainda** chega ao banco como
  parâmetro bindado — não "otimize" para f-string.

---

## 5. Autenticação e autorização

### Login

Não há usuário/senha: a autenticação é por **SID** de funcionário.

1. O usuário informa o SID (1 letra + 6 dígitos, ex. `A123456`)
2. `awmpy.get_phonebook_data(sid)` traz nome, e-mail e cargo do phonebook
3. SID no banco **e** IP do cliente igual ao IP gravado → sessão direta
4. Caso contrário → código de 6 dígitos gravado em `verification_codes`,
   enviado por SMTP, e o usuário vai para a tela de 2FA
5. `/verify-2fa` valida o código (10 min de validade) e marca
   `session['authenticated'] = True`

Chaves de sessão: `authenticated`, `user_sid`, `user_name`, `user_email`,
`user_role`.

### Papéis e acesso

A autorização vive no `routes.py` e é aplicada em três camadas (before_request,
JS do menu, feed de notificações).

- **Papéis.** `user_role` vem do banco (`ADMIN`, `BO`, `MO`, `FO`,
  `INSTITUTIONAL`, `HUB`). **Master** é superusuário fixado por SID
  (`_MASTER_SIDS`, hoje `{'E930179'}`) — **não** é papel concedível, então não
  se atribui pela gestão de usuários. `_session_is_master()` é por SID;
  `_session_is_admin()` = papel `ADMIN` **ou** master. Só o master altera o
  acesso de um admin (ou de outro master), e só ele escapa de toda restrição.
- **Por página.** `users.Page_Access` guarda um array JSON de URLs permitidas.
  Vazio/ausente = *não configurado* = acesso total. `_load_nav_urls()` extrai
  de `partials/sidenav.html` o conjunto de páginas controláveis.
  `enforce_page_access` (before_request) bloqueia quem tem allowlist
  configurada. Admins também são barrados **se o master os configurou**;
  não configurados (inclusive admins) mantêm acesso total.
  - `_ALWAYS_ALLOWED_PATHS` é **apenas** `{'/users-profile', '/page-access'}`.
    **O dashboard NÃO é sempre permitido** — ele virou concedível, e é por isso
    que o bloqueio redireciona para `_safe_landing(allowed)` (uma página que a
    pessoa realmente alcança, com `/users-profile` como último recurso) e não
    para `/dashboard`, que ela pode não ter.
  - Requests `/api/*` e `/static*` nunca são bloqueados aqui: têm a própria
    autenticação.
- **Por card (Control Panel).** A página é controlada por card: tokens
  `"/control-panel#<id>"` (registro `_CONTROL_PANEL_CARDS`) liberam rotinas
  individuais. A página abre com ≥1 card liberado (`_cp_page_allowed`);
  `enforce_control_panel_cards` bloqueia o endpoint de cada rotina sem o card
  (`_CP_ENDPOINT_CARD`). Uma concessão legada da página inteira implica todos
  os cards.
- **Tela de administração.** `/page-access` (admin/master) é o editor;
  `/api/page-access/<sid>` GET/POST persiste. A checklist é montada no
  navegador a partir do DOM vivo do menu, agrupada pela hierarquia completa,
  com o Control Panel explodido em seção própria.

---

## 6. Mappings (os de-para que se editam na tela, não no código)

**Nunca fixe um de-para novo no código.** Acrescente uma entrada em
`_MAPPING_DEFS` no `routes.py` (`key → {label, columns, seed[, file, upgrade]}`)
e um item no array `TYPES` de `apps/templates/pages/mapping.html`.

- Os arquivos ficam em `apps/static/data/mappings/` (um JSON por mapping,
  versionado). `BaseMoeda.json` também está lá (movido em `f789d02` — o caminho
  antigo `apps/static/data/BaseMoeda.json` não existe mais).
- `_mapping_rows(key)` semeia o arquivo na primeira leitura e cacheia por
  mtime: **edição na tela vale no request seguinte, sem restart** — ao
  contrário de mudanças no `routes.py`, que exigem reinício na instância do
  time.
- O seed tem de carregar **exatamente** os valores que estavam fixos no código,
  para o comportamento ser idêntico até alguém editar a tabela.
- API genérica `/api/mappings/<key>` GET/POST. O POST **substitui o arquivo
  inteiro**. Os valores **não são trimados** de propósito (o espaço no fim de
  códigos B3 como `'C '` faz parte do código).
- O front-end consome via `fetch` e mantém os literais antigos como fallback,
  então um fetch que falha degrada para o comportamento anterior.
- `upgrade` opcional converte formatos antigos na leitura; `autofill` opcional
  numa coluna `select` faz o modal preencher outra coluna a partir das linhas
  já cadastradas.
- **`file`** opcional aponta o registro para um JSON **já existente** em vez de
  `mappings/<key>.json`. `swap-index` usa isso para editar o mesmo
  `SwapIndex.json` que a página de Index Results edita — um arquivo, dois
  editores, sem chance de divergirem. Ao fazer isso, **declare também as
  colunas extras do arquivo** (`STATUS`/`MAKER`/`CHECKER`): o POST reescreve o
  arquivo inteiro e derrubaria o que não estivesse declarado (HANDOFF §188).

São **24** mappings hoje: `currency-base`, `interbook-ndf`, `publisher-ndf`,
`le-accronym`, `le-spn`, `commodities-b3`, `bank-name`, `fxo-conv-rate`,
`ndf-pdf-cpty`, `swap-curves`, `cetip-files`, `api-links`, `opb3-events`,
`swap-ir-client`, `swap-ir-term`, `swap-index`, `swap-funcionalidade`,
`swap-amortizacao`, `swap-code-labels`, `ndfc-ir-exempt`, `ndfc-advice-split`,
`b3-omnibus-account`, `fxo-internal-cpty`, `manual-conf-validation`.

### Os que têm regra fácil de quebrar pela tela

- **`opb3-events`** — quais linhas do Operations B3 entram numa apuração de
  liquidação, e é a MESMA resposta para o NDF Summary, o Other Products, os
  avisos e a mensageria. A linha é uma **regra** sobre Tipo Título × Tipo
  Operação × Status B3, com **campo em branco = coringa** e `USE` = Consider /
  Disregard. Precedência: Disregard vence; um Tipo Título com ao menos um
  Consider próprio vira lista branca; Tipo Título sem Consider não é filtrado.
  Era o `swap-b3-events` (só o Tipo Operação do swap) — HANDOFF §213, inclusive
  a mudança de semântica da tabela vazia.
- **`publisher-ndf`** — uma linha **sem** Match Tokens casa **só com o texto
  completo** (é o que permite `PTAX` e `PTAX|BRR|PTAX` serem cadastros
  independentes), e a coluna **`NOTES = BACEN` é o que roteia para Vanilla** em
  vez de Other Publisher. Tirar o `BACEN` da linha `PTAX` manda PTAX puro para
  Other Publisher — o único jeito de quebrar o comportamento histórico
  (HANDOFF §166).
- **`commodities-b3`** e **`cetip-files`** — o texto cadastrado carrega um
  **padrão**, não um literal: `"MY"` entre aspas é letra do mês B3 + ano
  (`X_"MY"` → `X Z7`), `_` é espaço literal, e `YYMMDD` num nome de arquivo
  CETIP é a Reference Date do card. O trecho `MY` é destacado na tabela para
  ler separado da parte fixa (HANDOFF §164). `commodities-b3` carrega ainda o
  **B3 CODE FAR** (a linha `SPECIAL` do BRT_IPE leva DOIS códigos: `B3 CODE` =
  `CO"MY"` para o contrato do mês seguinte e `B3 CODE FAR` = `CO1-2` para dois
  meses ou mais à frente; vanilla usa sempre o do mês — HANDOFF §212) e o
  **Tipo de Cotação / Fonte de Informação** escritos nos arquivos Conecta
  (`QUOTE TYPE NDF`, `QUOTE TYPE OPT`, `INFO SOURCE`): a coluna guarda o
  **código do layout**, e há duas colunas de tipo de cotação porque os layouts
  de Termo e Opção usam domínios diferentes (letra vs número) para a mesma
  mercadoria. Coluna em branco — ou subjacente sem linha — devolve o valor
  histórico (`_b3_quote_cfg`), que é o que o seed grava; a cópia da regra no
  navegador é o `static/js/b3-quote-config.js`, e `check_quote_type.py` prova
  que as duas concordam (HANDOFF §177).
- **`api-links`** — o endpoint da Athena, uma linha por **uso × produto**
  (`New Deals` × NDF/FXO/Commodities/Swaps, mais `Unwinds`), com `YYYYMMDD`
  marcando a data de referência. Produto aqui é o parâmetro `product` da API,
  **não a página**: NDF é um produto alimentando três páginas (Vanilla, Other
  Publisher, FWD Start), separadas por roteamento e não por endereço. `PRODUCT`
  em branco é coringa daquele uso. `date` é sempre reescrito; `product` só na
  linha coringa — linha específica de produto é usada como cadastrada, já que
  foi escolhida *por* produto. A linha `Unwinds` vai **vazia de propósito**:
  sem URL o consumidor falha pedindo cadastro, enquanto `New Deals` cai no
  endereço histórico (HANDOFF §173). O uso **`Recon FXO`** é outra Athena — o
  relatório EOD do `bob-reports`, não o `getTrades` — e a data dele fica no
  **caminho** (`AAAA-MM-DD`), que é justamente para o que o placeholder serve.
- **`fxo-internal-cpty`** — a perna interna da reconciliação de FXO. A coluna
  **`INVERT DIRECTION`** decide *quando* a regra vale: `No` renomeia sempre;
  `Yes` é a perna espelhada e só entra quando Ctpty **e** JPM Dir estão os dois
  NOK — aplicá-la sempre inverteria a direção de operações que estavam certas
  (HANDOFF §216). O Counterparty → CNPJ **não tem cadastro**: sai do Reference
  Data (`lookup_cnpj` indexa COUNTERPARTY, FX CASH ACCRONYM e SPN pelo mesmo
  TAX ID), porque um de-para paralelo seria uma segunda lista dos mesmos
  clientes e envelheceria sozinho.
- **`manual-conf-validation`** — quem valida a confirmação de cada produto
  (Produto × LOB → OTC / MO / FO, `REQUESTED` ou `EXEMPT`). **LOB em branco é
  coringa** do produto. MO e FO correm em **paralelo**, não em fila. Produto
  sem linha cai em OTC + MO e a tela **avisa** — em vez de deixar a confirmação
  parada num Pending que ninguém sabe de quem é (HANDOFF §217).
  - A coluna **PRODUCT é um `select`** sobre `manual_conf.CONFIRMATION_TYPES` —
    **uma lista só**, e ela tem QUATRO consumidores: o *Confirmation Type* do
    upload do Electronic Inventory (`routes._EI_CONFIRMATION_TYPES` aponta para
    ela), a **pasta** em que o documento é gravado (`TYPE_FOLDER`), este cadastro
    e o dropdown de Produto do Track Confirmations. Eram listas escritas à mão, e
    o cadastro dizia `OPTION` onde a tela de upload dizia `FXO`: o mesmo
    documento com dois nomes. São **oito tipos, sempre em MAIÚSCULO** (é código,
    não rótulo — a comparação entre as telas é feita sobre ele):

    | Tipo | Pasta no Electronic Inventory |
    |---|---|
    | `NDF VANILLA` | `NDF Vanilla` |
    | `NDF FWD START` | `NDF FWD Start` |
    | `OTHER PUBLISHER` | `NDF Other Publisher` |
    | `NDF COMM` | `NDF Commodities` |
    | `OPTION COMM` | `Commodities Options` |
    | `FXO` | `FX Options` |
    | `SWAP` | `Swap` |
    | `SWAP CORPORATE` | `Swap Corporate` |

    As três páginas de NDF do New Deals gravam o mesmo Product Type e têm cada
    uma o seu tipo aqui: o documento que sai de cada uma é diferente, e um `NDF`
    genérico obrigava a adivinhar qual delas gerou a linha.
  - **`TYPE_FOLDER` é a fonte única do nome da pasta**, para os dois jeitos de um
    documento chegar ao share: o `save` do app e o **upload manual**. Eles
    gravavam em pastas diferentes para o mesmo produto (`FXO` × `FX Options`), e
    como o Monitor procura PDF só onde o app grava, a confirmação subida à mão
    ficava invisível para ele com o arquivo lá. Os quatro nomes de pasta
    históricos (`NDF Commodities`, `Commodities Options`, `FX Options`,
    `NDF FWD Start`) **não podem mudar** — renomeá-los deixaria para trás tudo o
    que já foi gravado.
  - Os dois lados da comparação passam por **`manual_conf.confirmation_type()`**,
    que traduz a nomenclatura de quem criou a linha (`OPTION`, e o `NDF` × LOB
    `COMMODITY` da planilha legada) para o nome único. Ele classifica **pela
    pasta** (`_product_folder`) antes de aceitar um nome que já está na lista —
    `NDF` × COMMODITY tem um produto que por acaso está lá, e devolvê-lo direto o
    classificaria como termo de moeda.
  - O **`upgrade` faz duas coisas**, e as duas são obrigatórias. Traduz os nomes
    antigos (sem ele, a instância que já tem o arquivo em disco abriria o
    `select` sem a opção correspondente, e o primeiro Save trocaria o produto da
    linha sem ninguém pedir) e **completa o arquivo com os tipos que não têm
    linha nenhuma**, a partir do `_MC_VALIDATION_SEED`. Sem a segunda, um tipo
    novo cairia no `DEFAULT_RULE` (OTC + MO) — que para o `SWAP CORPORATE` é a
    regra errada, porque nele o FO também valida. A completação é **por produto,
    não por par Produto × LOB**: quem apagou a linha coringa e deixou só a da sua
    LOB fez isso de propósito.
  - `OPTION EDG` **não era um produto**: era a opção de câmbio na LOB EDG, e o
    `upgrade` a converte em `FXO` × LOB `EDG` — o desenho Produto × LOB que a
    tabela sempre teve.
- **`swap-index`** — código de curva B3 → nome (`C00` → `VCP`). Aponta para o
  **mesmo `SwapIndex.json`** da página de Index Results (ver `file` acima), e
  toda tradução código→texto do módulo de Swap passa por registro:
  `swap-funcionalidade`, `swap-amortizacao` e `swap-code-labels`. Live Position
  **Termo e Opção não têm de-para nenhum** — só formatação de número e data —,
  então não há o que cadastrar lá (HANDOFF §188).
- **`ndfc-ir-exempt`** — quem NÃO paga o IR de 0,005% do termo de mercadoria. A
  **mesma lista serve o Settlement Advice e o Trade Level**: mesmo imposto,
  mesma operação, e duas listas divergiriam com uma tela retendo e a outra não.
  O seed vai **além da fórmula da planilha** (que isentava só LAWTON) porque
  ATACAMA / BANCO / JPMorgan foram pedidos por nome (HANDOFF §195).
- **`ndfc-advice-split`** — contrapartes que recebem **um aviso por mercadoria**
  (semeado com `MONDELEZ`). O split roda **depois** do split por tipo de net,
  então um Pay/Rec da Mondelez sai por direção *e* por mercadoria (§196).
- **`b3-omnibus-account`** — contas B3 que **não** identificam o cliente
  (`73760.10-2`). Nessas linhas o nome que vem da B3 é o do titular do omnibus;
  o cliente é resolvido por **CNPJ** contra o `RefData.json`. As duas
  comparações (CNPJ e conta) são **só de dígitos** — os lados guardam
  pontuação diferente, e comparar string casa silenciosamente nada (§197).
- **`fxo-conv-rate`** — alimenta as duas colunas de Taxa de Conversão da
  confirmação de FXO asiática (Moeda Base → nome da taxa + Venda/Compra) e vem
  semeado só com USD → USD PTAX / Venda; moeda não cadastrada gera aviso no
  painel em vez de imprimir em branco (HANDOFF §139).

---

## 7. Armadilhas que não dão erro nenhum

Esta seção é o que o código **não** conta. Cada item aqui custou pelo menos uma
rodada de depuração.

### A contraparte vem do accronym do End Counterparty, nunca do Settlement Location

A ordem em `_ndf_ref_by_accronym` é: accronym (exato, depois sem o sufixo da
entidade) → **se o accronym for perna interna**, a identidade da própria
entidade (`_ndf_le_refdata`: o Reference Data Name do `le-spn` buscado por nome
normalizado, depois os accronyms da LE, depois o SPN cadastrado) → **senão** o
SPN da API → nada. Três coisas para não confundir:

- o **Settlement Location é a *nossa* perna**, não a da contraparte. Jogá-lo no
  lookup fez um cliente resolver para Banco J.P. Morgan. O argumento `le` de
  `_ndf_ref_by_accronym` tem de ser a entidade do accronym *da própria
  contraparte* (`_ndf_le_from_accronym(end_cp)`), que é `None` a menos que a
  contraparte seja perna interna do JPM (HANDOFF §147/§148);
- o `SPN` da API já carregou o SPN da Legal Entity; hoje carrega o da
  contraparte, por isso é o **último** passo — e nunca é consultado para perna
  interna, o que reintroduziria a armadilha acima por outro caminho (§174);
- **perna interna resolve pelo nome legal da entidade**, porque nome de book
  (`LM-FWDECOMBRR FXC`) não tem accronym no Reference Data — foi isso que
  deixou essas linhas sem SPN/Client/Tax ID. A linha **mantém o accronym da
  API** (o book), e o badge só poupa perna interna que voltou com SPN.

Nada casando = linha vazia + badge "Missing Counterparty", que é a falha
desejada: pede cadastro em vez de inventar contraparte. Num **amend da API** a
contraparte é rechecada e aplicada; a linha gravada é achada por
`(Deal, Client)` e, quando o Client mudou, **só pelo Deal ID se ele for único
no arquivo-dia** — senão o amend entraria como linha duplicada. Um deal
`Success` só volta para `Amend` quando o **accronym** mudou de entidade; um
lookup melhor do mesmo accronym apenas realça as células. Esse badge é só DOM,
por isso os filtros por coluna roteiam o termo `missing c…` (9+ caracteres,
para não colidir com "Missing Index B3") pelo `missing-counterparty.js` em vez
da busca do DataTables.

### `table.rows({search:'none', page:'all'})` NÃO é "tudo do dia"

Devolve as linhas **carregadas**, e as tabelas de New Deals são frequentemente
carregadas de uma busca no servidor (`/cache/search`, os chips do topo).
Qualquer ação montada varrendo a tabela cobre só a última busca. O mapping do
arquivo de retorno da B3 foi corrigido mandando a **Reference Date** e deixando
o servidor montar a lista a partir do arquivo-dia
(`_generic_nd_mapping_candidates`, HANDOFF §152) — o que também significa que o
servidor persiste em deals que não estão na tela. A limitação continua valendo
para Opt FXO / Opt Commodities / NDF Commodities, que têm endpoints próprios.

### Inserir uma coluna nas páginas de NDF do New Deals mexe em 14 lugares

`<th>` do cabeçalho, `<th>` da linha de filtro, `COL_TO_JSON_FIELD`,
`AMEND_FIELD_COLS`, `dealJsonToRow`, `ND_COL_KEYS`, `columnDefs` ocultas,
`columnLabels`, opções da edição em massa, `SF_COLS`, `SF_LABEL_TO_FIELD`,
`extractRowDeal`, `rowDataToNdfDeal`, `rowMaker`. Índice desatualizado aqui já
causou corrupção silenciosa de dados **duas vezes** (HANDOFF §132). A coluna
Maker é alcançada pela constante `MAKER_COL_INDEX` — mantenha assim.

### Duas armadilhas de tela que não aparecem no console (HANDOFF §218)

- **A linha de filtro por coluna tem de ser montada ANTES do `.DataTable()`**,
  com `orderCellsTop: true`. Com `scrollX: true` o DataTables desenha o
  cabeçalho duas vezes (a cópia visível vai para `.dt-scroll-headInner`, o
  `<thead>` real fica escondido no corpo rolável), e `api.table().node()`
  devolve a tabela do **corpo** — acrescentar a linha no `initComplete` a deixa
  no DOM e invisível.
- **Não use `.card` para um widget seu.** O `layouts/base.html` carrega o
  `extra_css` da página **antes** do `head-css.html`, então o `.card` do tema
  (`background-color`, `border`, `border-radius`, `color`) vence qualquer regra
  da página sem `!important`. O padrão da casa é um `<div>` com classe própria
  (`.ndm-card`, `.fxo-widget`, `.mc-card`), usando `--vr-card-*` e `--vr-grad`.

Complementando, no mesmo tema: a **animação padrão do ícone** (about → sidenav
→ New Deals Monitor) é `transform: scale(1.1) rotate(-4deg)` com sombra mais
funda no hover do card. Cor só de tema claro precisa do par
`[data-bs-theme=dark]`, senão a marca some no escuro.

### Um arquivo JS comanda CINCO páginas

`static/js/pages/live-position-swap-characteristics.js` é um visualizador
genérico `{columns, rows}` escolhido pelo `data-api` da página: Live Position
Swap Characteristics, Other Products Swap (Athena · Events · VCP) e as duas de
Settlement Advice (Swap e NDF Commodities). O contrato são os ids
**`swapchar-page`** e **`swapchar-table`** mais o `data-api` — renomear
qualquer um deixa a página **em branco, sem erro no console**. O que é
específico de uma página (o botão Print Advice) vai no `<script>` dela, e o que
for acrescentado ao arquivo compartilhado tem de ser **aditivo**: o array
`statuses` por linha e o `window.scLoad` são opt-in, então as páginas que não
mandam nada se comportam exatamente como antes (HANDOFF §184/§190).

### A família de liquidação do Other Products lê as MESMAS linhas

Settlement Summary, Trade Level e as duas de Settlement Advice leem as mesmas
linhas derivadas — o card conta o que a tabela mostra, e o aviso imprime o que
a tabela mostra. **`_ops_trade_rows(settle_ref)` é o único lugar que sabe quais
famílias de produto existem** (hoje SWAP + NDF Commodities); a página, os cards
de reconciliação e o e-mail de TED chamam todos ele. O endpoint de TED remontava
a lista sozinho e silenciosamente parou de pedir os TEDs de commodities no dia
em que NDF entrou (HANDOFF §199). O status do aviso (`New → Generated → Sent`)
vive uma vez só, no overlay do dia
`other-products-summary_YYYYMMDD.json`, chaveado por **contraparte × LOB ×
produto**, e as duas telas leem essa mesma chave (§183/§189/§190).

### A Recon FXO tem DOIS lados órfãos, e o join precisa ser `outer`

O status da 1ª coluna tem quatro estados, na ordem da gravidade — que é também a
ordenação padrão da tabela (por rank, não alfabética):

| Status | O que é | Cor |
|---|---|---|
| `Unmatched B3` | está na CETIP/B3, não achou par na Athena (falta bookar) | vermelho |
| `Unmatched Athena` | está na Athena, não achou par na B3 (falta registrar) | vermelho |
| `Partial - <campos>` | casou, e os campos listados divergem | laranja |
| `Matched` | fechou | verde |

O `Unmatched Athena` **só existe porque o merge é `outer`**. Com o `left`
anterior, a operação que existia só na Athena simplesmente não aparecia na tela —
uma quebra do mesmo tamanho, com a diferença de que ninguém a via. Três coisas
quebram junto quando se mexe nisso:

- `df_anc['_veio_da_b3'] = True` antes do merge é o que distingue as duas
  órfãs depois dele: as duas saem com metade das colunas vazias;
- `alerta_chave_duplicada` vem `NaN` na linha só-Athena, e **`if nan` é
  verdadeiro** — o teste é `pd.notna(x) and bool(x)`. E não `x is True`: depois
  do merge o valor é um `numpy.bool_`, e `numpy.True_ is True` é **falso**, o que
  apagava a marca de todas as linhas;
- `_aplicar_perna_espelhada` recebe a máscara das linhas com os dois lados. A
  assinatura que ela procura (Ctpty e Dir os dois NOK) acontece por falta de par
  numa órfã, e ela "corrigiria" a linha para um par que não existe.

**A justificativa é do TRADE, não da execução.** O comentário fica em
`apps/static/data/recon-fxo-comments.json` (fora do cache por data, no
`.gitignore`), chaveado pela `Combinação de operações`, e `aplicar_comentarios()`
roda na gravação **e na leitura** — um comentário escrito hoje aparece na recon
de ontem que já está em cache. Com comentário, `Unmatched`/`Partial` viram
`Justified`; `Matched` não (comentar o que fechou é anotação, e promovê-lo
esconderia o único estado que não pede atenção). O status cru fica em `_status`,
**fora de `COLUMNS`** — é ele que permite apagar o comentário e a linha voltar a
dizer `Partial - Cntpy` em vez de ficar `Justified` para sempre.

### A esteira de confirmação manual é um gancho para a frente

`_mc_save_from_deal` espelha para Manual Confirmations a operação que acabou de
ser mapeada, e é chamado **de dentro de `_pc_save_from_deal`** de propósito:
quem decide se um deal vira confirmação de cliente (perna interna? intragrupo?)
é aquela função, e repetir o teste criaria uma segunda resposta para a mesma
pergunta. Ele dispara no instante em que o deal vira `Success` — **não
retroage**. Tudo que foi mapeado antes de a esteira existir alimentou o Pending
Confirmation e parou ali; é para isso que existe o
`backfill_manual_confirmations.py` (§9). Só os produtos de
`_MC_CONFIRMATION_SOURCES` geram documento: NDF Vanilla e Other Publisher
ficam de fora de propósito.

### Outras

- **Jobs agendados rodam no horário do Brasil, não no do servidor.**
  `_br_now()` (`zoneinfo` `America/Sao_Paulo`, caindo para `-03:00` fixo quando
  falta `tzdata` — o caso Windows) sustenta o e-mail de pendências das 19:00/
  19:30 e a manutenção das 11:30 do Pending Confirmation. `datetime.now()` é o
  relógio local do servidor e disparava tudo na hora errada, em silêncio. Como
  a instância reinicia várias vezes ao dia, `_ndm_pending_catch_up()` também
  dispara na subida as janelas já passadas do dia; o arquivo de claim em disco
  é o que impede isso de virar e-mail repetido.
- **`reportlab` é importado preguiçosamente** (PDFs de confirmação e folha de
  liquidação do NDF Summary): sem a lib o e-mail sai *sem* o anexo, em vez de
  falhar.
- **Só `isCancelled = true` significa cancelado** na Athena. `isDead` é estado
  interno e esses registros *são* importados (`_api_rec_is_cancelled`, §173).
- **`Docs/` e `docs/` coexistem** (3 arquivos versionados no capitalizado, 47
  no minúsculo — artefato de filesystem case-insensitive). As capturas ficam em
  **`docs/sop-screenshots/`** minúsculo, que é o que o `SOP_PROCESSAMENTO_OTC.md`
  e o `GUIA_DO_USUARIO_OTC_TRACKER.md` referenciam. Como o diretório em disco é
  `Docs`, um `git add docs/...` comum grava o caminho **capitalizado** e os
  arquivos caem noutra árvore — invisível no macOS, imagem quebrada no
  Linux/Windows. Use
  `git -c core.ignorecase=false add docs/sop-screenshots/` e confira o índice.
  Os dois documentos são gerados do `.md` (a fonte única) por
  `scripts/build_sop_docx.py`, que aceita o arquivo de origem como argumento
  opcional (§155 para as armadilhas de captura).

---

## 8. Ambiente local e instância do time

- **`awmpy` é biblioteca interna do JPMorgan** e não está no PyPI. Sem ela o
  app falha no login/registro (consulta ao phonebook). Para **dev fora da rede
  JPM**, um stub mínimo de `awmpy` no venv deixa o servidor subir — login real
  por SID não funciona, então use a rota `/dev-login` do DEV BYPASS (bloco que
  é removido antes de todo commit — §2).
- **macOS: use `flask run --port=5005`.** A porta 5000 é do AirPlay Receiver e
  devolve 403 "AirTunes". O venv aqui é Python 3.12 (no diretório `.venv311`);
  `duckdb` e `flask-minify` são obrigatórios (ambos no `requirements.txt`).
- **SMTP** usa `mailhost.jpmchase.net` (relay interno, porta 25, sem auth) —
  fora da rede JPM o envio falha silenciosamente.
- **API `getTrades` da Athena** (`apps/pages/athena_api.py`): importa New Deals
  de NDF/FXO (botão manual + schedulers no app, NDF a cada 20 min, FXO de hora
  em hora). Precisa da rede JPM — fora dela o scheduler falha em silêncio
  (erros repetidos rebaixados para `debug`). `build_session()` marca
  `trust_env=False` **de propósito**: herdar o proxy corporativo foi o que
  causou o `WinError 10061` na máquina Windows do time. O SSO Kerberos no
  Windows precisa de `requests-negotiate-sspi`, que está **comentado** no
  `requirements.txt` (só Windows) — instale na instância do JPM. O endpoint em
  si não é mais constante: vem do mapping `api-links`, com
  `BASE_URL`/`TRADES_ENDPOINT` sobrando como fallback do New Deals.
- **A instância do time roda com o reloader desligado**: depois de um
  `git pull` que tocou `routes.py` ou um template, o Flask **tem de ser
  reiniciado** ou o código velho continua servindo. Vários "não está
  funcionando" vieram daí. Edição de mapping pela tela é a exceção — vale no
  request seguinte.
- `flask_login`, `flask_wtf` e `flask_migrate` estão no `requirements.txt` mas
  **não são usados**; o app gerencia sessão e banco diretamente.

---

## 9. Scripts e testes

### Migrações de uma vez só (`scripts/`)

Rodam **uma vez na instância do time depois do pull**. Todas idempotentes.

| Script | Para quê |
|---|---|
| `update_pending_confirmation_dbs.py` | migração de schema do Pending Confirmation (§128) |
| `update_pending_confirmation_bankers.py` | idem, coluna de banker |
| `import_manual_confirmations.py` | **cria** os dois DuckDBs da esteira e semeia do `MANUAIS.xlsx` (`--xlsx`, `--schema-only`) |
| `backfill_manual_confirmations.py` | traz para a esteira o que foi mapeado **antes** dela existir (`--dry-run`, `--source`) |

> `apps/static/data/db/` está no **`.gitignore`**, então os bancos **não vêm no
> pull**. Sem rodar `import_manual_confirmations.py` as duas telas de Manual
> Confirmation abrem vazias e **não há nada errado com o código** — é a mesma
> classe de "não funciona" que as migrações do Pending Confirmation já
> produziram.

O `backfill_manual_confirmations.py` reusa as **mesmas** funções que o
mapeamento chama (`_pc_is_internal_counterparty` + `_mc_save_from_deal`) em vez
de reescrever a regra. Duas armadilhas dele: **FWD Start é chaveado pelo B3 ID,
não pelo Deal** (chavear pelo Deal cria uma segunda linha para o mesmo trade no
mapeamento seguinte), e o `--dry-run` precisa lembrar as chaves da própria
passada — o mesmo Deal aparece em vários arquivos-dia, e sem isso ele prometia
73 linhas onde o run real criava 39.

### Testes de regressão (`scripts/tests/`)

Scripts autocontidos, sem framework: cada um imprime `ok`/`FAIL` por asserção,
sai 0/1, resolve a raiz do repo pelo próprio caminho e **não toca em dado real**
(tickets vão para `tempfile`, o DuckDB é recriado em tmp, Outlook/SMTP são
stubados). O [`scripts/tests/README.md`](scripts/tests/README.md) mapeia cada
script ao módulo que ele protege — **rode o correspondente depois de mexer
naquele módulo**. `check_boxparse.py` é o único que precisa de binário externo
(o `jsc` do macOS, para rodar a cópia da regra que vive no navegador), então não
roda na máquina Windows do time (§163).
