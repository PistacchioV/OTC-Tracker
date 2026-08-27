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
  `main`. **`visual-refresh-prod` é a branch que a instância do JPM roda**, e ela
  é a `visual-refresh` MAIS um commit no `apps/config.py`: **dados**, bancos e
  share em
  `\\Nawest.ad.jpmorganchase.com\lac\BRA\intra` em vez de dentro da aplicação e
  `I:\`. A diferença é **um bloco de seis linhas** (entre `── ENV:DEV ──` e
  `── /ENV ──`) e nada mais — código só nasce na dev e chega lá por merge
  (`/commit` publica na dev; `/commitjp` faz o merge e troca o bloco). Corrigir
  direto na prod é criar uma divergência que ninguém vê até o merge seguinte
  conflitar.
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
  da aplicação — o `meta` da Recon FXO era a frase pronta em português e por isso
  o resumo do alerta é montado na tela a partir de `counts`, ficando o `meta`
  só para a notificação do sino, que é texto gravado uma vez.
- **E-mail: o cabeçalho é cor sólida + gradiente CSS, nunca imagem/VML.** O
  `<v:rect>` do Outlook pintava o banner ora mais estreito que a célula (faixa
  sólida à direita), ora na largura da janela inteira. Ver o comentário em
  `partials/email-gradient-header.html`; `_attach_email_gradient` é no-op de
  propósito. A proibição é do BANNER, cuja largura tem de acompanhar a célula:
  um `v:roundrect` de **largura fixa** para botão é o caso em que o VML se
  comporta, e é o único jeito de o Outlook desktop arredondar canto. E botão
  ganha altura com `height` + `line-height`, nunca com padding vertical —
  o Word ignora padding em cima/embaixo de link e o botão sai magro
  (HANDOFF §257).

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
| `recon_cgd.py` | motor da reconciliação de CGD (lista do FEP × posição da B3) — tradução do workflow Alteryx `Batimento CGD` |
| `cgd_docs.py` | o banco da lista de CGDs do SharePoint (Onboarding · Tracking Docs) |
| `otc_boxparse.py` | parser do e-mail de booking recap |
| `otc_tickets.py` | store JSON do Support Center |
| `otc_emails.py`, `webpush.py`, `forecast_charts.py`, `otc_boxscan.py`, `recon_payrec.py`, `recon_comitente.py` | — |

**`confirmation_pdfs.py` tem um padrão a seguir:** FX Options é a exceção
correta. `opcao_fx_pdf()` monta o PDF a partir do *HTML já renderizado* do
documento (a mesma string que vira o `.doc`), via `_WordHtmlToFlowables` — as
duas saídas não têm como divergir. Documento novo deve nascer assim
(HANDOFF §139) — e é o que a **Opção de palm oil** faz: `word_html_pdf(doc_html)`
é a função genérica desse caminho, e o registro de quem usa qual é o
`_CONF_OPT_PDF_FROM_HTML` (o `opcao_pdf`, réplica em reportlab, continua
servindo só as duas famílias que nasceram antes). Ali isso não é estilo: o
Anexo I do palm oil tem **19** colunas e o `opcao_pdf` imprime as 16 de sempre —
o documento assinado sairia sem a Taxa de Conversão da Mercadoria, que é como o
preço em MYR vira USD.

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

- **A página carrega o SweetAlert2 LOCAL** (`plugins/sweetalert2/sweetalert2.min.js`),
  nunca o CDN: a instância do JPM roda sem internet, e do CDN a lib não chega.
  Sem ela, todo `Swal.fire` da página morre com `Swal is not defined` DENTRO do
  handler — e o que se perde não é o balão, é a **ação que vinha depois dele**: o
  Delete da linha não apaga, o Run não avisa, e a tela não diz nada. Quarenta e
  seis templates usam o caminho local; quatro ainda apontam para o CDN.
- **A página carrega o `plugins/jquery/jquery.min.js` ANTES do bloco de
  DataTables.** O `vendors.min.js` do tema **não** expõe o jQuery, então sem essa
  linha todo plugin dali para baixo morre com `jQuery is not defined` e a página
  abre com a barra de ferramentas e **sem tabela nenhuma** — o erro fica só no
  console do navegador, e na tela parece uma página que "não carregou os dados".
  Foi o que aconteceu com o Tracking Docs e a Recon CGD, as duas únicas telas com
  DataTables que nasceram sem ela.
- **Declare o `dom`.** Sem ele o DataTables desenha o próprio campo de busca e o
  próprio `Show N entries`, que duplicam os da barra de ferramentas da casa e
  aparecem soltos por cima do cabeçalho. O padrão é
  `dom: "rt<'d-md-flex justify-content-between align-items-center mt-2'ip>"` —
  tabela, info e paginação, nada mais.
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
  inteiro (spec `.ops-row-act`): **32×32 travado com min/max nos DOIS eixos**
  (`min/max-width` **e** `min/max-height`, mais `box-sizing:border-box` — com só
  a largura travada, uma regra de tema com `min-height` em `.btn` deixa um botão
  mais alto que o vizinho, e 32×34 não é um quadrado arredondado), `padding:0`,
  `border-radius:10px !important`, ícone Tabler `1rem`, tooltip colorido
  (`data-bs-custom-class="tooltip-{cor}"` — e o CSS de `tooltip-{cor}` tem de
  estar na página).
  - **O ícone nunca leva `.fs-13`.** É classe do tema com `font-size:13px
    !important`, e `!important` não se resolve por especificidade: ela vence a
    regra da página e o ícone sai com 13 px onde o app usa 16 — o quadrado fica
    do tamanho certo e o desenho dentro dele, menor. Foi o que fez o Index B3
    Results e o Reference Data parecerem de outra tela (HANDOFF §290). A regra da
    página vai `.btn-act > i { font-size:1rem !important }`, como cinto de
    segurança para quem copiar o markup de outro lugar.
  - **Tooltip em botão que a tabela redesenha se inicializa DELEGADO**, no
    primeiro hover — os `<td>` são reescritos a cada redraw do DataTables, então
    um laço no load pega só as linhas da primeira página e paginar devolve botões
    mudos. `title=` sozinho é o balão cinza do navegador, não o padrão.
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
  bg-gradient` (dropdown com o conjunto COMPLETO, nesta ordem: **Copy · CSV ·
  Excel · Print · PDF** — menos que isso é bug de consistência, foi o Track
  Confirmations com só CSV e Copy. A implementação é DataTables Buttons como no
  New Deals; numa tabela sem `buttons:` no init, crie
  `new $.fn.dataTable.Buttons(table, …)` depois e dispare pelos itens do
  dropdown com `table.button('<nome>:name').trigger()`. Exporta o que está NA
  TELA — filtros e ordenação aplicados, só colunas visíveis. CSV com
  `fieldSeparator: ';'` e `bom: true`, que é o que o Excel pt-BR precisa para
  separar colunas e manter acentos; Excel exige o snippet síncrono de registro
  do JSZip depois do `buttons.html5` — HANDOFF §247), **Import** = teal
  `#4a849b`, **Mapping/refresh** = `btn-success bg-gradient`, **Clear
  Filters** = `btn-outline-secondary`. `Show [N] entries` ao lado. A barra vai
  com **`mb-3`, não `mb-2`**: o DataTables desenha a própria caixa encostada no
  elemento anterior e come a margem do irmão de cima, então o `mb-2` mede 0 px
  na tela e os botões ficam colados no cabeçalho (HANDOFF §233).
- **O menu Export termina no `Advanced Export`**, e ele é uma linha por tela:
  `otcExportAdvanced('#tabela', { daily: '<endpoint do dia>' })`, opt-in como o
  `otcCellCopy` e no-op onde o `export-advanced.js` não estiver carregado. Ele se
  enxerta na collection do Buttons (ou num `<ul>` da página, com `menu:`) e faz
  o export pelo MESMO Buttons — um gerador próprio seria um segundo CSV, com
  outro separador e outro BOM. Três coisas decidem se ele funciona (HANDOFF §304):
  - **`daily` é o endpoint que a PRÓPRIA página consulta** para desenhar um dia
    (`{columns, rows}`; as recons usam `recon_date`/`data`, o resto `date`/`rows`).
    Ler os JSON do cache por fora seria uma segunda regra sobre os mesmos
    arquivos. Tela sem arquivo-dia não declara `daily` e a seção nasce
    desabilitada com o motivo escrito — some, e parece defeito.
  - **O intervalo pede `exact=1` e confere o `source_date` da resposta.** As
    telas de posição andam para trás até dez dias úteis quando falta arquivo — o
    que as mantém populadas —, e numa SÉRIE isso é o arquivo de outro dia
    carimbado com a data pedida. Endpoint com fallback tem de aceitar o `exact` e
    devolver a data do arquivo que leu.
  - **Dia sem arquivo é pulado, não é erro**; o que falha leva o motivo junto; e
    há teto de 60 s por dia, porque a leitura é em série e um dia que não
    responde segurava a fila inteira.
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
- **Sugestão/autocomplete de domínio aberto NUNCA usa `<datalist>` nativo.** O
  popup é do navegador: ignora o tema, não acompanha a largura do campo e, com
  lista grande (as ~560 contrapartes do Reference Data), cobre a tela inteira —
  foi o Counterparty do MT300 no /mapping. O padrão é o dropdown próprio
  **abaixo do campo, com a MESMA largura e `max-height` (~220px) com rolagem**:
  `mapAttachDrop`/`.map-ac-drop` no mapping.html (refdata e `type: 'datalist'`)
  e `.ar-ac-drop` no Add/Edit Deal do New Deals. Detalhes que importam: o
  clique do item é por **`mousedown`** (dispara antes do `blur` do input) e
  reemite `input`/`change` — é o que deixa o `wireRefdata` completar os campos
  irmãos —, e o esconder vem DEPOIS desses eventos, senão o próprio `input`
  reabre a lista. O domínio continua aberto: a lista é sugestão, não trava.
- **Data é SEMPRE `dd/mm/aaaa` na tela, e `<input type="date">` visível é
  proibido.** O campo nativo desenha no locale do SISTEMA: no Windows do JP isso
  é `mm/dd/yyyy`, e a mesa lê `03/04` como 3 de abril onde o campo quis dizer 4
  de março — um erro de data que não dá erro nenhum. Há dois jeitos aceitos, e os
  dois mostram `dd/mm/aaaa`:
  - **flatpickr com `altInput`** — o padrão geral, e o do
    `otcDateField`/`otcDateSync` (expostos pelo `static/js/export-advanced.js`,
    que é o único helper de data do app). Ele esconde o input original — que
    segue com o `value` em **ISO**, e por isso o código em volta não muda — e
    desenha ao lado o campo em dd/mm/aaaa. O flatpickr é global (vem no
    `vendors.min.js`), mas a chamada leva guard: sem ele o campo tem de degradar
    para texto comum, não quebrar. **Quem escreve no campo por código avisa o
    picker** (`el._flatpickr.setDate(v, false)`, ou `otcDateSync('#modal')`): o
    `value` do original muda, mas o campo que se VÊ é o outro, e ele ficaria com
    a data anterior — abrir o modal numa linha e depois noutra mostraria a data
    da primeira.
  - **jQuery daterangepicker `singleDatePicker`** com
    `locale: { format: 'DD/MM/YYYY' }`, nas páginas que já carregam os assets
    dele (Other Products Summary, NDF Summary, MtM, Accrual, Control Panel,
    dashboard). Fallback: campo de texto dd/mm/aaaa.

  O `type="date"` só continua legítimo **invisível**, como picker atrás de um
  campo de texto readonly em dd/mm/aaaa — é o `.date-wrap` das duas Recons
  (`opacity:0` por cima do texto) e o botão de calendário do CGD no Reference
  Data. Ali o que se lê é sempre o texto; o nativo é só o calendário.

---

## 4. Bancos e concorrência

São dois bancos:

- **DuckDB** (`Users_OTCTracker.db`) — tabelas `users` e `verification_codes`.
  As **notificações moram noutro arquivo** (`Notifications_OTCTracker.db`,
  `Config.NOTIFICATIONS_DATABASE_PATH`), com `notifications` e
  `push_subscriptions`. O lock desta camada é por ARQUIVO: com as quatro juntas,
  cada gravação de notificação — e elas acontecem a cada ação de qualquer pessoa
  — segurava o arquivo inteiro em modo exclusivo, e com ele o login, a allowlist
  do `Page_Access` e a gestão de usuários; some a isso o sino, que consulta por
  aba aberta, e o banco vivia travado. Quem abre o de notificação é o
  `get_notif_connection()`, com o mesmo contrato do `get_db_connection()`.
  A separação acontece **sozinha na subida** (`_ensure_notif_db`, chamado pelo
  `record_once` do blueprint), copiando o que está no arquivo antigo — um script
  "rode depois do pull" é a forma mais confiável de a mesa ficar sem o sino.
  **Na subida, e nunca no poll do sino**: o `_ensure_notif_db` abre o banco em
  modo READ-WRITE e, na primeira vez, migra — no share isso segurou o lock
  exclusivo por 9,4 segundos —, e ele ficava no topo do `get_notif_connection`,
  onde quem pagava a conta era a consulta mais repetida do app, a única que abre
  sem lock nenhum e a declarada de melhor esforço. O DuckDB não perdoa: um
  handle read-only aberto (outra aba, outra thread, a instância vizinha que
  enxerga o mesmo share) **bloqueia** a abertura read-write, e o open estoura com
  *"the process cannot access the file because it is being used by another
  process"* — que não diz nada sobre schema. Como o flag só é marcado no fim, a
  falha o deixava em `False` e todo poll seguinte tentava de novo: um 500 por aba
  a cada 8 segundos, cada um custando uma tentativa de lock exclusivo no share.
  Hoje o caminho de LEITURA não chama o ensure, uma **sonda** (`_notif_schema_pronto`,
  leitura com lock compartilhado) evita a abertura read-write no caso normal, o
  ensure que falha **espera** 5 min antes de tentar de novo, e a ABERTURA do sino
  está dentro do `try` — sem conexão ele devolve a lista vazia, na mesma forma da
  resposta de sucesso. `check_notif_db_boot.py` prende as quatro. É idempotente e **não apaga** o que
  copiou: o antigo fica como backup. `scripts/split_notifications_db.py
  --dry-run` mostra o que vai ser copiado antes de reiniciar.
  Três detalhes que não dão erro nenhum: o schema é comitado numa transação
  SEPARADA da cópia (juntos, uma linha ruim desfazia o `CREATE TABLE` e o app
  subia sem a tabela, com o sino estourando a cada consulta); a sequência
  `seq_notif_id` nasce depois do maior `id` migrado, porque o DuckDB não deixa
  alterar sequência de que uma coluna depende (`ALTER … RESTART` não existe e o
  `DROP` bate em *dependency error*); e `NULL` vira `''` nas colunas `NOT NULL`,
  senão UMA linha antiga aborta o lote inteiro.
  `DB_PATH` é o `Config.DATABASE_PATH`, e ele sai do **`Config.DATABASE_DIR`**,
  que é a pasta de TODOS os bancos do app: o da lista de CGDs (`cgd_docs.DB_PATH`),
  os três do Pending Confirmation
  (`_PC_DB_DIR`), os dois da esteira (`manual_conf._DB_DIR`), o de comitentes
  (`recon_comitente.DB_PATH`) e os três scripts de migração. **Nenhum deles monta
  o caminho por conta própria** — cada um que montasse ficaria lendo o banco
  local no dia em que os outros fossem para o share, sem erro nenhum. Caminho
  **normalizado para absoluto**, então não depende do diretório de trabalho;
  relativo é **recusado na subida** (`must be an absolute path`), em vez de virar
  uma árvore criada por engano dentro do cwd. Mover tudo de lugar é uma coisa só:
  `OTC_DATABASE_DIR` no `.env` (ou o bloco de ENV do config na branch de prod —
  §2). `DATABASE_PATH` continua movendo só o banco de usuários.
- **Os JSON** (cache dos arquivos-dia, cadastros do /mapping, tickets,
  `RefData.json`, calendário, templates do File Interpreter) saem do
  **`Config.DATA_DIR`**, e o caminho é montado pelo **`apps/pages/data_paths.py`**
  — `data_path()` para ler, `data_write()` para gravar, `mapping_file(key, base)`
  para um cadastro. **Nenhum módulo monta `static/data` por conta própria**, e o
  `check_config_names.py` recusa por AST quem tentar.

  Isso existe porque o cache é **gitignorado**: os módulos montavam o caminho a
  partir do próprio `__file__`, o que amarra o dado ao diretório do CÓDIGO. Na
  dev as duas pastas são a mesma e nada aparece; na instância do JPM não são, e
  um checkout novo não tem arquivo-dia nenhum — a tela abre, a API responde
  **200** e o gráfico vem vazio, como se não houvesse operação no dia. É a falha
  que menos parece falha.

  Duas garantias sustentam a troca: a **leitura cai para a cópia empacotada**
  quando o arquivo não existe no `DATA_DIR` (`anbima.json`, `Subjacente.json`, as
  seeds — sem isso, subir apontando para um share vazio apagaria os 42 cadastros
  versionados), e a **escrita nunca cai** — gravar dentro do checkout é gravar
  onde o próximo `git pull` conflita e a outra instância não enxerga. Na subida,
  `_seed_data_dir()` copia para o `DATA_DIR` o que vem versionado e ainda não
  está lá, **sem nunca sobrescrever**: o arquivo que já está no share é o que a
  mesa editou pela tela, e ele vence. `db/` fica de fora — é do `DATABASE_DIR`,
  e copiar banco por cima de banco corrompe dado.

  **O `/static/data/...` do NAVEGADOR também sai do `DATA_DIR`.** São 71 `fetch`
  em 15 telas lendo JSON por URL estática (`RefData.json`, `Subjacente.json`,
  `anbima.json`, os cadastros do /mapping), e como URL estática o Flask os
  serviria da pasta do CÓDIGO — a ponta que a regra acima não alcançava. A rota
  `static_data_file` resolve pelo mesmo `data_path()` e é mais específica que o
  `/static/<path:filename>` embutido, então ganha dele no roteamento; a dev não
  vê diferença, porque lá as duas pastas são a mesma. Sem ela a mesa editava o
  Reference Data pela tela, o app gravava no share e a tela recarregava
  mostrando a cópia versionada, de antes do último pull — nenhum erro, dois
  arquivos, e a edição que "não salvou" salva no lugar certo. A rota entrega
  **raiz e caminho relativo separados** ao `send_from_directory`: quem recusa o
  `..` é o `safe_join` dele, e com o caminho já resolvido a pasta traversada
  vira a raiz permitida (`/static/data/../../config.py` serviria o config).
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
- **A leitura SEM lock (`unlocked=True`) é do poll do sino, e só dele.** Ela
  dispensa até o lock compartilhado — o que coordena PROCESSOS —, então não
  espera nem por uma gravação em curso; em troca, pode pegar o arquivo no meio
  de um commit e falhar. Ali é aceitável porque o sino é consulta de MELHOR
  ESFORÇO: o endpoint já devolve o sino vazio quando a consulta falha, e o poll
  seguinte corrige. **Em qualquer outro lugar é um tiro no pé que não dá erro**
  — a allowlist do `Page_Access`, o login e o papel que filtra os tickets
  DECIDEM coisas, e um dado parcial ali vira autorização errada. O
  `check_unlocked_reads.py` prende os pontos de chamada por AST e barra por nome
  as funções de autorização. O aviso `file_lock_skipped` sai **uma vez por
  banco**, não por leitura: ele é WARNING, WARNING passa pelo gate que silencia
  o ruído de INFO, e uma linha por poll seria a maior parte do log.
- **Quem só faz SELECT abre com `get_db_connection(readonly=True)`.** O caminho
  de escrita é EXCLUSIVO nos dois níveis — `BoundedSemaphore(1)` dentro do
  processo e lock de arquivo exclusivo entre eles —, então uma consulta aberta
  por ali põe toda leitura numa fila de UM. Com o banco no share, onde cada
  operação custa ida e volta de rede, o sino da topbar (uma consulta por aba
  aberta) consome a fila sozinho e a página que o usuário pediu espera atrás
  dela: a tela levava MINUTOS, sem erro nenhum no log, porque ninguém falhou —
  todo mundo esperou. A leitura toma lock COMPARTILHADO e um semáforo de
  `DATABASE_READ_CONCURRENCY`, e segue excluída do escritor, que é a garantia
  que importa. Os sete chamadores de leitura estão migrados; escrita continua
  no modo padrão.
- **A allowlist do `Page_Access` é cacheada por SID** (`_get_page_access`), com
  invalidação na escrita e TTL de 30 s por cima. Os dois existem por razões
  diferentes: a invalidação cobre a mudança feita NESTE processo, e o TTL cobre
  a instância vizinha que editou o mesmo banco. Era a consulta mais repetida do
  app — toda navegação e toda batida do sino — relendo o mesmo valor.
- **Nunca faça trabalho lento segurando o lock** (rede, SMTP, varredura de
  arquivos, renderização de template). `_push_notify` é o modelo: lê a lista de
  inscritos, fecha, e só então dispara os HTTP pushes. A topbar consulta
  notificações a cada 15 s por aba aberta — esse lock é tomado o tempo todo.
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
  (`start-prod.bat`, **`--threads=16`**) e o `gunicorn-cfg.py` fixa
  `workers = 1`. Com mais de um processo o singleton e o `_cache_lock` não
  protegem nada, o banco de usuários não abre no segundo processo e cada
  processo sobe os próprios schedulers (pulls duplicados). O padrão do waitress
  é **4**, e com os dados no share a maior parte de um request é espera de rede
  com a thread parada segurando a vaga: quatro esperas dessas param o servidor
  inteiro, inclusive o arquivo estático e a página que nem banco usa.

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
  - A página é dividida em **seis seções** — Intraday, Settlement Reporting,
    Pending Confirmation, Economic Affirmation, Reference Data e Application —,
    e o que
    agrupa não é o que a rotina FAZ e sim *quando* ela acontece e sobre o que
    responde: não há seção de "salvamento de arquivo", o Save CETIP Files está
    na Intraday (roda ao longo do pregão) e o Save Daily Settlement Files na
    Settlement Reporting. A **Application** é a única que não fala de operação:
    ela guarda as rotinas sobre a própria ferramenta, e hoje tem um card só, o
    **New Version Released** — o aviso de que há versão nova e de que ela
    precisa ser iniciada à mão. A versão dele NÃO se digita: sai do `link.txt`
    que fica ao lado do `start-otc-tracker.bat`, na pasta Application (o caminho
    pende do `SHARED_DRIVE_ROOT`, §8, e `OTC_VERSION_FILE` o move). Sem versão
    reconhecida o envio é **recusado** — um aviso de "nova versão" sem o número
    não diz nada a quem recebe —, e o destinatário é quem está `Active` no
    cadastro de usuários, não quem está `Pending`. A seção de cada card **é o DOM**: o cabeçalho
    (`data-cp-hdr`), a
    `.row.cp-cards` logo abaixo, e os cards dentro dela. Havia um mapa
    card → grupo escrito à mão no JS, e ele envelhecia calado no dia em que um
    card mudasse de seção: o cabeçalho ficava sozinho na tela, ou sumia com
    cards embaixo dele. Card novo só precisa nascer dentro de uma seção.
  - O que se esconde de quem não tem acesso é o **`.cp-reveal` do card**, e só
    depois a coluna que ficou sem nenhum card visível: a coluna empilhada (dois
    cards) levava junto o card que a pessoa PODE ver.
  - O **`id` é o token** gravado no `Page_Access` (`/control-panel#<id>`) —
    renomeá-lo revoga o acesso em silêncio. A **ordem** de
    `_CONTROL_PANEL_CARDS` é a da tela, seção por seção, porque é ela que monta
    a checklist do `/page-access` (HANDOFF §285).
- **Tela de administração.** `/page-access` (admin/master) é o editor;
  `/api/page-access/<sid>` GET/POST persiste. A checklist é montada no
  navegador a partir do DOM vivo do menu, agrupada pela hierarquia completa,
  com o Control Panel explodido em seção própria.
- **Support Center: a unidade da visibilidade é a MESA, não a pessoa.** Quem é
  do Back Office vê os chamados abertos pelo Back Office, quem é do Middle vê os
  do Middle — a fila de uma mesa é assunto da mesa, e antes o colega que abriu o
  mesmo pedido ontem não tinha como saber. **Ver não é poder**: editar, comentar
  e apagar continuam sendo do REQUESTER (e do master), então o chamado do colega
  abre em leitura. Três detalhes que não dão erro nenhum:
  - o papel fica **gravado no ticket** (`requester_role`), e é o de quem abriu,
    não o que a pessoa tem hoje: sair do BO para o MO não leva os chamados
    antigos para a fila nova;
  - o ticket ANTERIOR a essa coluna tem o papel resolvido no cadastro de
    usuários (`_tk_roles_by_sid`, uma consulta por LOTE e com cache — por
    ticket, a listagem abriria o banco de usuários uma vez por linha da tela).
    Sem esse resgate, a fila inteira de antes sumiria da mesa que a abriu, e um
    chamado que some é pior do que um que aparece para gente demais;
  - **papel vazio não casa com nada.** Dois usuários sem papel no cadastro não
    são uma mesa, e tratá-los como uma abriria a fila de um para o outro — nesse
    caso vale a regra antiga, só o próprio.

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
- O tipo de coluna **`refdata`** liga o campo ao Reference Data
  (`/api/reference-data/counterparties`): escolhido **qualquer** um dos três —
  nome, SPN ou Tax ID —, os outros dois se preenchem. É o mesmo cliente escrito
  de três jeitos, e digitar os três à mão é criar a chance de o SPN de um
  conviver com o nome de outro: a linha casaria por um identificador e apareceria
  no consumidor com o outro. O tipo é genérico, então o próximo cadastro que
  precise disso não reescreve nada (o `mt300` é o primeiro — HANDOFF §280).
- **`file`** opcional aponta o registro para um JSON **já existente** em vez de
  `mappings/<key>.json`. `swap-index` usa isso para editar o mesmo
  `SwapIndex.json` que a página de Index Results edita — um arquivo, dois
  editores, sem chance de divergirem. Ao fazer isso, **declare também as
  colunas extras do arquivo** (`STATUS`/`MAKER`/`CHECKER`): o POST reescreve o
  arquivo inteiro e derrubaria o que não estivesse declarado (HANDOFF §188).

São **43** mappings hoje: `currency-base`, `interbook-ndf`, `publisher-ndf`,
`le-accronym`, `le-spn`, `commodities-b3`, `bank-name`, `fxo-conv-rate`,
`ndf-pdf-cpty`, `swap-curves`, `cetip-files`, `api-links`, `opb3-events`,
`swap-ir-client`, `swap-ir-term`, `swap-index`, `swap-funcionalidade`,
`swap-amortizacao`, `swap-code-labels`, `ndfc-ir-exempt`, `ndfc-advice-split`,
`b3-accounts`, `fxo-internal-cpty`, `fxo-book-disregard`,
`bankers-email`, `manual-conf-validation`, `manual-conf-sla`, `quotes-equity`,
`quotes-commodity`, `gdt-codes`, `settlement-exception`, `mt300`, e os sete
`dce-*` dos domínios DCE (`dce-country`, `dce-type-of-derivative`,
`dce-type-of-swap`, `dce-type-of-verification`, `dce-functionality`,
`dce-underlying-asset-category`, `dce-underlying-asset`), mais os quatro do CGD
(`cgd-stage`, `cgd-b3-participante`, `cgd-garantidor`, `cgd-conta-encerrada` —
os três últimos eram abas do `Auxiliar.xlsx` do batimento) — seeds vazios com os
JSONs versionados, como os dois Quotes (o `dce-underlying-asset` tem ~14 mil
linhas). As colunas dos `dce-*` carregam `lang` (chave i18n): o `colLabel` do
mapping.html traduz cabeçalho, filtro, export e modal — coluna sem `lang`
continua no label inglês.

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
  ler separado da parte fixa (HANDOFF §164). `commodities-b3` tem a coluna
  **TRADE TYPE** (VANILLA / ASIAN / BOTH; em branco = BOTH): a linha só vale
  para o tipo de trade que ela diz, e é o que permite um market ter códigos
  diferentes por tipo — o BRT_IPE tem DUAS linhas: a `SPECIAL`, **só ASIAN**,
  leva os dois códigos (`B3 CODE` = `CO"MY"` para o contrato do mês seguinte à
  liquidação e `B3 CODE FAR` = `CO1-2` para dois meses ou mais — HANDOFF §212)
  e a `PREFIX`, **só VANILLA**, o `CO"MY"` padrão (§251). O WTI segue o mesmo
  desenho: `PREFIX`/VANILLA `WTI"MY"` e `FIXED`/ASIAN `CL1` (§252). Os mapas
  dos consumidores são por tipo (`{mkt: {V, A}}` — `_box_commodity_maps` e os
  dois JS), com valor plano do formato antigo valendo para os dois. Carrega
  ainda o **Tipo de Cotação / Fonte de Informação** escritos nos arquivos
  Conecta (`QUOTE TYPE NDF`, `QUOTE TYPE OPT`, `INFO SOURCE`): a coluna guarda
  o **código do layout**, e há duas colunas de tipo de cotação porque os
  layouts de Termo e Opção usam domínios diferentes (letra vs número) para a
  mesma mercadoria. Coluna em branco — ou subjacente sem linha — devolve o
  default histórico `A` / `5` / `358` (`_b3_quote_cfg`); o flag **FIXED QUOTE
  foi aposentado** (§252): o F/340 das linhas que eram YES está materializado
  nas colunas, e o upgrade faz isso ao ler arquivo antigo antes de remover o
  flag. A cópia da regra no navegador é o `static/js/b3-quote-config.js`, e
  `check_quote_type.py` prova que as duas concordam (HANDOFF §177). A tabela
  do /mapping abre ordenada por MARKET A→Z (só a exibição; o arquivo mantém a
  ordem de cadastro) e todo mapping ordena por clique no header.
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
  (HANDOFF §216). A coluna **`USE`** decide se a linha entra: `Disregard` tira
  do batimento, **antes do merge**, as linhas da Athena cuja **contraparte** casa
  com o nome cadastrado — é a perna interna que não tem par na CETIP e
  viraria `Unmatched Athena` todo dia (a conta GEM é a semeada assim). Cortar
  depois do merge não adiantaria: o DealID dela já teria ocupado a chave em
  `base_athena_para_match` e poderia roubar o par de uma operação de verdade. O
  corte é **cego a pontuação** (`_nome_cru`), olha as **DUAS** colunas de
  contraparte (`CounterpartyName` e `MatchingCounterpartyName`: a operação
  intragrupo chega ao relatório pelos dois lados, e é a segunda que a tela mostra
  em ATH Cntpy — cortar por uma só deixava metade do par na recon exibindo o nome
  que o cadastro mandou tirar, HANDOFF §228) e é **avisado** no painel — linha que
  some sem dizer nada vira "sumiu uma operação da recon". Uma linha `Disregard`
  deixa de valer como renomeação/espelho: uma linha, uma decisão. O `upgrade`
  mora no **`recon_fxo`**, e não no `routes`, porque quem lê esse cadastro a cada
  run é o motor — com ele só na tela de /mapping, a instância que nunca abriu
  aquela tela leria o JSON cru, sem a coluna. O Counterparty → CNPJ **não tem
  cadastro**: sai do Reference Data (`lookup_cnpj` indexa COUNTERPARTY, FX CASH
  ACCRONYM e SPN pelo mesmo TAX ID), porque um de-para paralelo seria uma segunda
  lista dos mesmos clientes e envelheceria sozinho.
- **`bankers-email`** — nome do banker → e-mail, o Cc do e-mail de coleta de
  assinatura. O `BANKER` do Reference Data traz o GRUPO por extenso ("Fulano e
  Sicrano") e é esta lista que resolve cada nome num endereço. Era o
  `signature_collection_bankers.json`, mantido à mão: banker novo só entrava por
  commit, e até lá o e-mail saía sem ele no Cc. Hoje o arquivo é o
  `mappings/bankers-email.json`, como os demais cadastros, e mudou de
  `{"bankers": [...]}` para a LISTA que o /mapping entende. Cadastro vazio deixa
  o Cc só com as caixas fixas e o e-mail vai embora do mesmo jeito, então
  `_sigcoll_bankers_index` **avisa no log** quando a lista volta vazia.
- **`fxo-book-disregard`** — a MESMA exclusão do cadastro acima, por outro
  identificador que não o nome da contraparte. A perna interbook é a mesa contra
  a mesa, não tem registro na CETIP e viraria `Unmatched Athena` todo dia. Cada
  linha é uma **conjunção de até três critérios `coluna = valor`**, com a coluna
  escolhida num dropdown do cabeçalho real do relatório
  (`_ATHENA_FXO_COLUMNS`): um critério tira tudo que tem aquele valor naquela
  coluna, dois tiram só o que tem os dois, três só o que tem os três.
  - **A coluna é ESCOLHIDA, não fixada.** A primeira versão deste cadastro tinha
    colunas fixas `TRADING BOOK` / `OTHER BOOK` — nomes que o relatório da Athena
    **não tem** (ele tem `Portfolio`, `CounterpartyName`, `INT_EXT`…), e a regra
    nunca casaria. Quem sabe em que coluna mora cada valor é quem opera; a lista
    do dropdown é conveniência de tela e pode envelhecer sem quebrar nada, porque
    o motor aceita o nome que estiver gravado.
  - **Par pela metade não conta** (coluna sem valor, ou valor sem coluna): é o
    que permite escrever a regra de um critério só sem inventar coringa. E a
    linha SEM critério nenhum é **ignorada** — sem nada a exigir ela casaria com
    o relatório inteiro, e a linha vazia criada por engano na tela apagaria o
    lado da Athena da recon.
  - O **valor** é comparado por `_nome_cru` (cego a caixa, espaço e pontuação) e
    o **nome da coluna** também é resolvido normalizado (`INT_EXT` ≡ `int ext`),
    porque a grafia depende de quem gerou o arquivo.
  - **Regra que cite coluna inexistente é PULADA com aviso**, nunca com o
    critério ignorado: ignorando, a regra passaria a exigir menos e derrubaria
    mais linhas do que o cadastro pediu.

  O `upgrade` traduz o formato antigo (as três colunas fixas) para os pares,
  preservando os VALORES e levando o nome antigo para o dropdown — de onde ele é
  corrigido em um clique. O corte é **antes do merge**, pela mesma razão do outro
  cadastro (depois, o DealID da linha cortada já teria ocupado a chave), e é
  **avisado** no painel. O endpoint `/reconciliation-fxo/run` toca os **dois**
  cadastros antes de rodar, só para materializar o seed: o motor lê o JSON direto
  (importar `routes` seria circular) e não tem como semear — sem isso, na
  instância em que ninguém abriu a tela de /mapping o arquivo não existe e as
  regras não valem, sem erro nenhum.
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
    documento com dois nomes. São **doze tipos, sempre em MAIÚSCULO e SEM
    ACENTO** (é código, não rótulo — a comparação entre as telas é feita sobre
    ele):

    `NDF VANILLA` · `NDF FWD START` · `NDF OTHER PUBLISHER` · `NDF COMM` ·
    `OPTION COMM` · `FXO` · `SWAP` · `SWAP CORPORATE` · `TERMO DE RESILICAO` ·
    `AMENDMENT` · `ADDENDUM` · `RERATIFICATION`

    O **sem acento** não é estilo: `confirmation_type()` compara
    `upper_norm(produto)` com a tupla, e o `upper_norm` normaliza em NFKD e
    descarta as marcas de combinação. Um `TERMO DE RESILIÇÃO` cadastrado com
    cedilha chegaria à comparação como `TERMO DE RESILICAO` e **nunca casaria
    consigo mesmo** — o tipo não resolveria e a pasta não seria achada
    (`_product_folder` faz o mesmo lookup), sem erro nenhum. O lado bom da mesma
    normalização é que quem digita "Termo de Resilição" com acento no cadastro
    resolve para o código certo.

    As três páginas de NDF do New Deals gravam o mesmo Product Type e têm cada
    uma o seu tipo aqui: o documento que sai de cada uma é diferente, e um `NDF`
    genérico obrigava a adivinhar qual delas gerou a linha.

    **Tipo novo mexe em três listas**, e as três têm teste: `CONFIRMATION_TYPES`,
    `TYPE_FOLDER_LEGACY` (com tupla VAZIA quando o tipo nunca existiu sob outro
    nome — a entrada existe para um tipo ausente não se confundir com um
    histórico esquecido) e `VALIDATION_SEED`, sem a qual o tipo cairia no
    `DEFAULT_RULE` sem ninguém ter decidido nada.
  - **A pasta É o código do tipo** — `TYPE_FOLDER` é a identidade, e é ela que os
    quatro `save` do New Deals e o upload manual consultam em vez de escrever a
    string. Antes o app gravava num nome bonito (`FX Options`) e o upload no
    código (`FXO`): o mesmo produto em duas pastas, e como o Monitor procurava o
    PDF só onde o app grava, a confirmação subida à mão ficava invisível com o
    arquivo lá. Dar ao app um segundo nome recriava a divergência pela outra
    ponta; o share já está cheio de pastas com o nome do tipo, que é o que a mesa
    reconhece.
  - **`TYPE_FOLDER_LEGACY` é só de LEITURA**, e é obrigatório: os nomes antigos
    (`NDF Vanilla`, `NDF FWD Start`, `NDF Other Publisher`, `NDF Commodities`,
    `Commodities Options`, `FX Options`, `Swap`, `Swap Corporate`) continuam
    cheios no share. Quem procura o documento usa
    **`confirmation_folders()`** — a pasta de escrita primeiro, as antigas
    depois, e o mesmo nome de arquivo só uma vez. `confirmation_folder()`
    (singular) devolve só a de escrita. Unificar o nome sem isto apagaria da tela
    toda confirmação anterior, com os arquivos intactos no share.
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
- **`b3-accounts`** — as contas B3 de cada entidade nossa (LE · Nome
  Simplificado · Conta · Tipo · Reference Data Name · Messaging), e ele responde
  TRÊS perguntas. Era o `b3-omnibus-account`, que listava só a conta
  guarda-chuva e onde **estar na tabela era a resposta** (§287).
  - **A conta identifica o cliente?** Só **CLIENT 1 / CLIENT 2** são
    guarda-chuva: nelas o nome que vem da B3 é o do titular do omnibus, e o
    cliente é resolvido por **CNPJ** contra o `RefData.json`. Com a conta
    PRÓPRIA dentro da mesma tabela, quem responde passou a ser o **TIPO** — se
    voltasse a ser a presença na lista, a posição da casa iria procurar cliente
    pelo CNPJ onde não há cliente nenhum. As duas comparações (CNPJ e conta) são
    **só de dígitos** — os lados guardam pontuação diferente, e comparar string
    casa silenciosamente nada (§197). O tipo é um `select` e a leitura é cega a
    caixa e acento (`Própria` ≡ `OWN`, `CLIENTE 1` ≡ `CLIENT 1`): digitado à
    mão, um `Cliente1` viraria conta própria sem erro nenhum.
  - **Quem é o Participante** do header dos arquivos TER (campo X(20), "Nome
    Simplificado do Emissor"): `_ter_file_header(le, …)` resolve pela **LE da
    visão** que está sendo gerada, e o motor completa com espaços até os 20
    caracteres. Era o dicionário fixo `_TER_PARTICIPANT_NAME`, com a mesma
    resposta repetida no `source_note` do File Interpreter. O que sobrou fixo é
    a tradução `_TER_BUCKET_LE` — o gerador fala em balde (`BANCO`) e o cadastro
    em LE (`JPM`). **LE sem Nome Simplificado levanta erro** dizendo qual falta,
    em vez de mandar para a B3 um header com o campo em branco.
  - **A mensageria sai na visão desta conta?** Coluna **MESSAGING**
    (Consider/Disregard). A liquidação intragrupo chega pelos DOIS arquivos,
    espelhada, e as duas pontas virando e-mail cobrariam duas vezes o mesmo
    pagamento: o Banco assina; MGT, Lawton e Atacama são `Disregard`. Era uma
    regra escrita no endpoint (`casa == MGT e contraparte == Banco`) que conhecia
    esse par e só ele — Lawton e Atacama passavam direto (§306). **Conta fora do
    cadastro GERA**: é a conta de terceiro, e travá-la por falta de linha calaria
    a rotina inteira onde ninguém abriu o /mapping. O `upgrade` completa a coluna
    pelo seed (por conta e por LE) — um default cego `Consider` faria a mensagem
    sair pelas duas pontas, e `Disregard` cego a faria não sair de nenhuma, que é
    pior porque some sem erro.
  - O **Reference Data Name** é como a entidade está escrita no Reference Data,
    e existe porque o Nome Simplificado ao lado é o apelido de 20 caracteres da
    B3 (`INTRAGLAWTONFDO`), que não endereça documento nenhum. A coluna é do tipo
    `refdata`, então o nome se escolhe da lista.
  - **Estar no cadastro é ser conta INTERNA** — a tabela lista as contas B3 das
    nossas entidades e nada mais —, e é por aí que o BCC de compliance sabe que a
    contraparte é o Lawton ou a Atacama, em vez de casar o prefixo do Nome
    Simplificado.
- **`fxo-conv-rate`** — alimenta as duas colunas de Taxa de Conversão da
  confirmação de FXO asiática (Moeda Base → nome da taxa + Venda/Compra) e vem
  semeado só com USD → USD PTAX / Venda; moeda não cadastrada gera aviso no
  painel em vez de imprimir em branco (HANDOFF §139).
- **`quotes-equity`** e **`quotes-commodity`** — o código do Ativo Subjacente do
  Index B3 → o **símbolo de mercado** que o Yahoo entende (`AAPL34` →
  `AAPL34.SA`). As OPÇÕES da tela não saem daqui: elas vêm do `Subjacente.json`
  ao vivo, separadas pelo campo `Classe` e só as `ACTIVE` — este cadastro só
  traduz. O `seed` vai **vazio de propósito**: os dois arquivos são versionados
  (471 + 17 linhas) e repetir centenas de pares no `routes.py` criaria uma
  segunda lista para divergir da primeira. Código sem símbolo devolve **404
  pedindo cadastro** e nunca tenta o código como ticker — a resposta seria um
  404 obscuro da fonte em vez de "falta cadastrar" (HANDOFF §266). A lista de
  moedas da PTAX **não é cadastro**: é o domínio do endpoint do BCB.
  - **Em commodities as DUAS colunas aceitam o padrão `"MY"`** — a mesma notação
    do `commodities-b3` (letra do mês + ano; `_` = espaço literal), e uma linha
    passa a valer para **todos os vencimentos** daquela mercadoria:
    `BO"MY"` → `ZL"MY".CBT` resolve `BOK6` → `ZLK26.CBT`. Eram 70 linhas para 10
    mercadorias, e mais uma linha a cada vencimento que a B3 abrisse. Quem
    expande é o `quotes.symbol_lookup`, e ele resolve as duas assimetrias que
    condenavam o de-para literal: o **ano** tem um dígito ou dois na B3 e sempre
    dois no símbolo de mercado (o dígito único cai na década corrente, virando
    para a seguinte quando o ano ficaria mais de um ano no passado — contrato
    futuro aponta para a frente), e o `"MY"` do símbolo fica no **meio**
    (`ZL"MY".CBT`), porque o sufixo de bolsa vem depois do vencimento.
  - O miolo casado **tem de ser mês+ano de contrato**, e o prefixo mais longo
    vence: sem as duas regras, `C_"MY"` (milho) casaria com `CCZ6` (cacau) e com
    `COZ6` (Brent) e devolveria o preço da mercadoria errada, em silêncio.
    Linha **sem** `"MY"` continua literal e **vence** o padrão — é assim que se
    cadastra a exceção de um vencimento só, ou o contrato contínuo (`C 1` →
    `ZC=F`). Equities não têm vencimento e são todas literais; o motor é um só,
    sem ramo por tipo.
  - O registro do de-para (sufixos de bolsa do Yahoo, códigos de mês, as 471
    equities e as pendências conhecidas) está em
    [`DE_PARA_TICKERS_COTACOES.md`](DE_PARA_TICKERS_COTACOES.md), gerado em Word
    pelo `scripts/build_sop_docx.py` como o SOP e o Guia.

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

### A coluna de CPF/CNPJ da contraparte das Live Position mostra o NOME

Nas três telas (NDF, Option e Swap Characteristics) essa coluna resolve o nome
no `RefData.json`. Vazio continua vazio; documento **sem cadastro volta como
número mascarado**, não em branco — apagá-lo esconderia quem falta cadastrar. A
chave normaliza o zero à esquerda **dos dois lados** (`_lp_taxid_key`): 158 dos
553 cadastros começam com zero, e comparar sem normalizar casa nada em silêncio
(§197). A coluna da **Parte** não muda — é a nossa perna, e o nome dela já está
na célula ao lado.

**Essa coluna tem outros leitores, e eles não são a tela.** Os dois Settlement
Advice (NDF Commodities e Opção) consomem o payload do Live Position e tiravam
dali o CPF/CNPJ para resolver o cliente da conta omnibus. Hoje usam a resolução
da própria coluna, e `_lp_is_taxid` é o que separa "resolveu" (nome) de "não
resolveu" (documento) — o teste é a ausência de LETRA, porque razão social com
número (`3M DO BRASIL`) não pode ser confundida com documento. São três funções
de propósito: `_lp_cpty_name_by_taxid` é a resolução CRUA (`''` sem cadastro) que
os consumidores usam, e `_lp_cpty_by_taxid` é a de EXIBIÇÃO, que cai para o
número (HANDOFF §291).

### O Holidays Calendar monta a lista de calendários do REGISTRO

Os calendários vêm de `apps/static/data/holiday-calendars.json` (semeado por
`_HOLIDAY_CAL_SEED` com os onze de sempre, cacheado por mtime), e é dele que
saem as **quatro** superfícies da tela: as pills da barra lateral, as opções do
`<select>` do modal, o mapa de cores do popup do feriado e o CSS. Eram cinco
listas escritas à mão — inclusive o `_HOLIDAY_FILE_MAP` que o
`/api/holidays/save` consultava — e nenhuma delas podia conhecer um calendário
criado pela tela (HANDOFF §288).

- **Calendário novo nasce de uma planilha**, pelo botão *Create New Calendar*:
  uma aba, coluna A a data e coluna B a descrição (a terceira, Holiday Type,
  não entra). O cabeçalho é descartado por **não ser data**, nunca por posição.
- A **cor é sorteada de uma paleta** (`_HOLIDAY_CAL_PALETTE`), preferindo as que
  ninguém usa, e o **CSS dele nasce no navegador** (`hcInjectCalendarCss`) a
  partir dessa cor — CSS de calendário criado hoje não estaria escrito no
  arquivo. Os onze built-in mantêm as classes do `<style>` da página; a função
  só gera para `hc-cal-<slug>`.
- O **slug vira caminho em disco e classe de CSS**, então só aceita
  `[a-z0-9_-]` — é ele que entra num `os.path.join`.
- O JS mantém `HC_CAL_FALLBACK` (os mesmos onze) para o fetch que falha, e
  `check_holiday_calendars.py` compara seed × fallback campo a campo.
- O registro está no `.gitignore` — o seed o recria, e versioná-lo daria
  conflito de merge a cada calendário criado pela tela.

### O Onboarding conta o aging, e a esteira do CGD é DERIVADA

A lista de CGDs vem do SharePoint (`Sharepoint-CGD.xlsx` → `cgd_sharepoint.db`,
pelo `scripts/import_cgd_sharepoint.py`), e duas colunas dela não são lidas como
estão:

- **`Aging` é refeito a cada leitura** (`cgd_docs.aging_of`), em dias ÚTEIS
  ANBIMA, da `Data Solicitação` até hoje — ou até o `Conclusion - Stamp`, quando
  ele existe: o CGD que concluiu parou de envelhecer. O da planilha é do dia da
  exportação e envelheceria parado no banco por semanas. Sem `Data Solicitação`
  o aging fica **vazio**, nunca zero: zero se lê como "entrou hoje".
- **O formulário de abertura vive no SERVIDOR** (`REQUEST_FORM`): rótulo, coluna
  do banco, tipo, obrigatoriedade e dica de cada campo. Dele saem DUAS coisas — o
  modal de *New Request* (partial `partials/onboarding-new-request.html`, incluído
  pelo Overview e pelo Tracking Docs) e o `REQUEST_FIELDS` que segura o documento
  no Banking. Escrito no template, o dia em que um campo deixasse de ser
  obrigatório o modal pararia de pedi-lo e a fila continuaria cobrando. O
  `REQUEST_FIELDS` fica ANTES do `STAGE_STAMP` no módulo, que o consome na
  leitura: definido depois, o Banking nasceria com a lista vazia e a fila ficaria
  permanentemente zerada, sem erro nenhum. E o `check_cgd_docs` confere que toda
  coluna citada no formulário EXISTE — nome errado ali não dá erro, o
  `update_row` ignora a chave e o campo preenchido some no caminho.
- **A esteira tem QUATRO mesas, e o `Banking` é a PRIMEIRA**: Banking · Legal ·
  OTC · CEM MO. Banking é quem abre a solicitação, e o documento sai de lá quando
  os campos **obrigatórios do formulário** estão preenchidos (`REQUEST_FIELDS`:
  `Data Solicitação`, `Razão Social`, `CNPJ`, `Signature Type` — os `*` do
  formulário; `Grupo` e `Dominio` são opcionais e cobrá-los deixaria na fila uma
  solicitação que já pode seguir). O nome da coluna do banco nem sempre é o do
  formulário: `CGD - Solicitação` é a `Data Solicitação` e `CGD - Tipo de
  Assinatura` é o `Signature Type`. Era um cartão só, `Banking OTC`, e ele juntava
  duas mesas que trabalham em momentos diferentes — a que pede o contrato e a que
  o confere depois de assinado.
- **O `Apêndice` do formulário é ARQUIVO e não tem coluna**: ele vai para o
  Electronic Inventory da contraparte, pasta `Transactional`, com o prefixo
  `CGD TEMPLATE` (`APPENDIX_EI_TYPE`/`APPENDIX_EI_SUBTYPE`) — é onde os
  documentos por cliente já vivem, e uma pasta nova só do Onboarding seria um
  segundo lugar para o mesmo papel. A contraparte é a **primeira linha** da Razão
  Social: o campo pede todas as entidades do grupo e a pasta do inventário é de
  UM cliente. O upload vem **antes** da gravação da linha — ele é a parte que
  depende do share e é a que falha; na ordem inversa, um share fora do ar deixaria
  a solicitação criada sem o template, sem nada na tela dizendo isso. E o
  `REQUEST_FIELDS` filtra `f['column']`: sendo obrigatório e sem coluna, o
  Apêndice entraria na regra do Banking como a coluna `''`, que nunca está
  preenchida — TODO documento ficaria preso na primeira fila, para sempre e sem
  erro nenhum.
- **`Signature Type` é domínio fechado de TRÊS valores** (`SIGNATURE_TYPES`):
  `FepWeb`, `DocuSign` e `Manual`. O valor gravado é o código em inglês —
  *Física* é só como o `Manual` aparece na tela em português, e gravar os dois
  faria metade da lista deixar de casar com a outra metade. Na grade, o campo é um
  `select` alimentado pelo servidor (`signature_types` no payload de
  `/api/onboarding/docs`), e o valor JÁ GRAVADO entra na lista mesmo fora dos três
  — escondê-lo faria o primeiro Save trocar o tipo da linha sem ninguém pedir. Não
  é cadastro do /mapping: é o domínio de UM campo, não um de-para.
- **A etapa** de todo documento que não está encerrado sai do cadastro
  **`cgd-stage`** (STATUS → mesa) e, sem linha cadastrada, é derivada pelo
  primeiro carimbo que falta — solicitação incompleta → Banking,
  `Emissão`/`Signature Date` → Legal, `OTC - STAMP` → OTC, `MO - STAMP` → CEM MO. O item vem
  MARCADO como derivado, para ninguém confundir dedução com cadastro. Documento
  com todos os carimbos e ainda não `Active` fica na ÚLTIMA mesa: devolvê-lo sem
  etapa o faria sumir das quatro filas, e um pendente que some é pior que um
  pendente na fila errada.

- **Encerrado não é pendência de ninguém.** `is_active` responde só pelo
  `Active` (comparação EXATA: `Inactive` normaliza para `INACTIVE`, que CONTÉM
  `ACTIVE`, e um teste por pedaço contaria o morto como vivo), e quem tira o
  documento das filas é o **`is_closed`** — `Active`, `Inactive` e `Cancelado`
  (por pedaço, que a grafia vem do SharePoint e é livre). Sem ele o encerrado
  caía na fila do **Legal**, que é a primeira etapa sem carimbo em quem nunca
  começou, e ficava lá envelhecendo para sempre no topo — empurrando para baixo
  o que alguém de fato tem de fazer. O Overview mostra **quatro** números que
  FECHAM (`total = pending + active + closed`): com três, a diferença entre o
  total e a soma era justamente o que tinha sumido das filas.
- **O badge de status é o do app** (`badge rounded-pill text-bg-* bg-gradient`),
  não uma paleta própria da página — e o teste do `INACTIV` vem ANTES do do
  `ACTIVE` pela mesma razão de cima: com o `indexOf('ACTIVE')` sozinho, o
  documento morto saía com o mesmo verde do que está de pé, que é exatamente a
  diferença que a coluna existe para dizer. No **Overview** a cor é da MESA (a
  do cartão), e não do status: lá o badge responde "de quem é a fila".

O `_id` do banco é interno e **não é estável entre importações** — ele endereça a
linha que a tela está editando, e a importação seguinte renumera tudo.

### A recon de CGD lê o D-1, e o cache tem de casar com ele

`recon_cgd` bate a lista do FEP contra a posição da B3 do **último dia útil**.
Cinco coisas:

- **o arquivo da B3 é o que a rotina Save CETIP Files GRAVA**, na pasta de
  DESTINO (`CETIP_DEST_ROOT` — a mesma raiz e o mesmo env var do `recon_fxo`),
  `{AAAA}/{MM}. {Month}/{DD}/CETIP21_{AAMMDD}_DPOSICAO-NET.txt`. Não é a pasta de
  ORIGEM: ali está o arquivo cru que a B3 despeja, com o nome do dia do download,
  e quem o filtra, renomeia para a convenção da casa e o guarda no dia certo é a
  rotina. Lendo a origem, a recon leria antes de a rotina passar — e no dia em que
  ela não rodasse acharia um arquivo e diria que está tudo certo com a posição da
  véspera. O nome SEM o `.txt` fica como segunda tentativa, para o arquivo posto
  na pasta à mão;

- **a lista do FEP vem do ANEXO de um e-mail, não de uma pasta**
  (`baixar_fep_do_box`): o `.xlsx` do relatório do FepWeb chega em
  `Inbox > Automatico > FEPWEB-CGD-ContratoGlobalDerivativos - SEM FILTRO DATAS`
  do box compartilhado — o MESMO que a varredura de booking recap e a Recon de
  Comitentes já leem. Ninguém salva esse arquivo em disco, então apontar o
  batimento para uma pasta era apontá-lo para um arquivo que alguém teria de
  copiar à mão todo dia, e no dia em que esquecesse a recon rodaria com a lista
  da semana passada sem dizer nada. Lê-se o e-mail **mais recente**
  (`Sort('[ReceivedTime]', True)` — o relatório é reemitido e a pasta acumula, e
  a ordem natural devolve o mais ANTIGO), e o **assunto e a data** do e-mail
  escolhido voltam no resultado como `fep_file`: "de que dia é esta lista" é a
  primeira pergunta de quem olha uma quebra, e o nome do temporário em que o
  anexo foi salvo não responde nenhuma. `path` explícito vence (upload manual e
  testes); sem Outlook — o Linux, a máquina de desenvolvimento — cai para
  `CGD_INPUT_ROOT` **avisando qual das duas fontes valeu**, porque rodar com a
  lista errada e não saber é a única falha daqui que não aparece: ela devolve
  uma tela plausível. Nada é apagado nem movido no box: a rotina só LÊ;

- as contas que definem "nosso" saem do cadastro `b3-accounts` (`ACCOUNT TYPE =
  OWN` + `LE` em `CGD_LES`), nunca de dois números escritos no filtro; cadastro
  vazio **avisa** em vez de deixar o arquivo inteiro entrar no batimento;
- **CNPJ compara por dígito** dos dois lados (§197), e a linha da B3 que vem sem
  CNPJ é resolvida pelo cadastro `cgd-b3-participante` — sem cadastro ela sai, e
  a recon diz quantas saíram;
- o cache do dia é gravado com a data da POSIÇÃO. A leitura sem data usa o mesmo
  default (`dia_util_anterior`), e não `hoje`: com `today()` de um lado só, o
  batimento rodava e o GET seguinte dizia que ninguém tinha rodado.

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

**A linha que NETA ZERO diz `0.00` no Receive** (`_opssum_rows`), e não sai com
as duas células em branco: vazio se lê como "não deu para calcular", e aqui o
zero é o resultado — a operação liquida por valores que se anulam. Fica no
Receive porque é o lado que a Direction já aponta (`total >= 0` → RECEIVE); o
Pay continua vazio, senão a mesma linha diria que paga e recebe zero ao mesmo
tempo. O gêmeo do NDF Summary (`_ndfsum_collect`) **não** mudou — a regra foi
pedida para o Other Products, e igualar os dois é outra decisão (§264).

**O Trade Level abre por Product → LOB → Counterparty**, nessa precedência, que
é a da conferência: o produto agrupa, a LOB separa a mesa dentro dele e o
cliente ordena a lista final. Só por Counterparty, swap, termo e opção do mesmo
cliente ficavam intercalados. O `initTable` da página aceita um número **ou uma
lista** de índices de ordenação; o Settlement Summary não passa nada e continua
abrindo na ordem em que o servidor mandou. Os índices são posicionais, então
`check_ops_trade_swap.py` confere que os três casam com o cabeçalho real —
índice errado ordena pela coluna vizinha sem erro nenhum.

**Equity é registrado na B3 como SWAP, então a linha já existe — o que falta é
o outro lado.** O `br-onshore-settlements` (Swap Athena) é **só de CEM** e não
tem equity: sem isso a linha saía com o nome curto da B3 (`SAFRABM`), sem
Internal ID, sem Settlement e com as três colunas de valor em branco — e, sem
Settlement, ficava fora do Settlement Summary. `_ops_equity_link(ref)` monta o
que o Athena daria, por uma rota de três paradas: **Operations B3 (Título) →
Latam Desk Position (`CLEARING_TRD_ID_INT`/`CLNT` → `Deal_Ref`) → OTM
Settlements (`270WI`/`270WC` + `Deal_Ref`)**. Qual perna é a do Título sai de
**qual coluna de clearing casou** — INT leva ao `270WI`, CLNT ao `270WC`. Do OTM
saem: Internal ID, contraparte (Reference Data pelo `Cpty SPN`), Settlement, e as
três colunas do aviso — **Curva Banco = os fluxos positivos, Curva Cliente = os
negativos, Resultado Bruto = a soma**. O Type é **trocado** pelo ativo subjacente
(não completado: VCP/Calculado vem do arquivo de eventos, que não tem equity, e
toda linha sairia dizendo `Calculado`) — e o subjacente sai de uma **cadeia**,
porque nenhuma fonte preenche sempre: `Underlying_Name` → `UNDERLYING_RIC` do
Latam → `Underlying` do OTM → `Instrument_Name` → `RIC` → `Instrument_ID`. As
duas primeiras colunas são de derivativo *sobre* um ativo e vêm vazias no swap de
equity, onde o próprio instrumento é a ação; foi assim que as linhas de EDG
apareceram com o Type em branco já tendo Internal ID e valor. O prazo do IR sai do **`Trade_Date` do
Latam**, porque a posição de swap não tem essas operações. O de-para lê o
**último** Latam disponível e compara **só dígitos, sem zeros à esquerda**. O
produto continua `SWAP` — é como a B3 registra, e é dessa linha que sai o
Settlement B3; quem rotula é a LOB (`EQUITIES` quando não há token cadastrado).
Partir do OTM em vez do Título criava uma **segunda linha** para o mesmo trade
(HANDOFF §227).

**O mesmo elo é o plano B da OPÇÃO de equity** (`_optadv_collect`). Ali o
Resultado Apurado sai do OTM pelo **sufixo da `Combinação de operações`** da Live
Position de Opção — campo que a opção de **ação** não preenche. Sem sufixo não
havia valor, e o efeito era duplo e calado: a linha aparecia no Trade Level com a
célula **vazia** e **sumia do Settlement Summary**, que descarta quem não tem o
que liquidar. O elo responde por **duas** coisas — o valor e o **SPN**, e é o SPN
que troca o `SAFRABM` da B3 pela razão social do cadastro, que é por onde o
Summary agrupa. Três coisas que não dão erro nenhum: ele vem **depois** do sufixo
(quando o sufixo existe é join direto, e é o mais confiável dos dois), a chave é
o **Título em MAIÚSCULA** (a mesma forma que o swap usa — outra grafia não casa
nada, em silêncio) e é resolvido **uma vez por linha**, senão o valor e o SPN
podem vir de trades diferentes (HANDOFF §281).

**Perna interna não gera aviso**, e a regra NÃO é "o nome começa em BANCO" —
isso derrubaria Banco Safra, Bradesco e Santander, que são clientes.
`_ops_is_internal_cpty` responde pelo cadastro `le-spn` (SPN, nome, e o **token
da LE** como palavra, porque o `Reference Data Name` nasce vazio em algumas
entidades) e pelo `_pc_is_internal_counterparty`, que é a resposta que o Pending
Confirmation já dá para a mesma pergunta. O que a marca tira é o **documento**,
não a linha: ela **fica** no Trade Level (visão de trade) **e no Settlement
Summary** (visão de liquidação — a perna interna liquida, e o total tem de fechar
com o Trade Level), sem marca nenhuma na tela; e **sai** do Settlement
Advice, que é o documento endereçado ao cliente, e do **e-mail de TED**, porque
não se transfere dinheiro para si mesmo — o `_is_jpmorgan` do TED não cobre isso
sozinho, já que a entidade pode ser um fundo nosso sem "J.P. Morgan" no nome
(HANDOFF §229/§234).

**O nome da contraparte sai do SPN, nunca do texto do arquivo.** O
`br-onshore-settlements` traz o `CounterParty` como texto livre da mesa
(`S T E S A L`) e o `SPN` ao lado; `_athena_settlements(ref)` troca um pelo
outro via `_otm_cpty_name` — cadastro `le-spn` quando é entidade nossa, Reference
Data quando é cliente, ignorando zeros à esquerda dos dois lados. É **uma coleta
só** para a página Swap Athena, o Settlement Advice de Swap e o Trade Level:
resolver o nome em cada tela é como elas passariam a mostrar clientes diferentes
para a mesma operação — e é por esse nome que a alíquota do `swap-ir-client` é
procurada. O OTM Settlements faz o mesmo pelo **`Cpty SPN`** da própria linha, e
**na leitura**, não na importação: corrigir o Reference Data vale na hora, sem
reimportar o dia. Sem SPN ou sem cadastro, o nome do arquivo fica — a linha não
pode sair anônima.

### A Recon FXO tem DOIS lados órfãos, e o join precisa ser `outer`

**A chave é o `DealID`; o `MatchingDealID` é a segunda tentativa, e só entra
quando ele existe do lado da B3.** Duas condições, e as duas importam. A
prioridade do DealID evita a mesma operação casar duas vezes (com o desempate
escolhendo qualquer uma). O filtro contra as `Combinação de operações` da base
âncora é o que impede o **`Unmatched Athena` fantasma**: o MatchingDealID
identifica a perna do OUTRO lado, quase nunca tem registro na CETIP, e cada valor
sem par entrava no join `outer` como uma linha a mais da Athena sem
correspondência — a MESMA operação repetida pela chave da perna oposta. Por isso
`base_athena_para_match` recebe as chaves da B3: sem elas não há como saber o que
descartar. Efeito colateral conhecido e histórico: quem casa por MatchingDealID
**aparece duas vezes** — uma `Matched` naquela chave e uma `Unmatched Athena` na
chave própria, que a CETIP não tem.

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

### O card de Confirmations do New Deals Monitor mostra UM ciclo só — e ele termina no OTC

`New → Generated → … → Success` é a geração, e depois dela só o **Pending
OTC** segura o grupo aberto: validado o OTC, a confirmação conta como **100%**
no card/seção e sai do e-mail de pendências das 19h. Pending MO/FO é assunto do
Confirmations Monitor — o New Deals Monitor cobra a ação da mesa de OTC, e
manter o grupo aberto por etapa alheia cobraria trabalho que não é dela.
`_conf_esteira_stages` traduz toda etapa depois do OTC para `Ok` na leitura, e
o e-mail conta `Ok` como concluído junto com `Success`. Quando o grupo já tem
linha na esteira, a etapa dela **vence** o status do documento (mostrar
`Generated` numa confirmação já em Pending OTC é parar o relógio na metade), e
o anel de progresso fecha em verde no `Ok`.

O join é pelos **Trade IDs** (`_conf_segregate` coleta `Deal` e `B3_ID` de cada
grupo), nunca por contraparte × mercadoria: os dois lados normalizam nome e
mercadoria de jeitos diferentes, e um de-para por texto casaria errado em
silêncio. Os dois identificadores vão juntos porque a chave da esteira é o Deal
para quase todo produto e o **B3 ID** para o FWD Start. O grupo vale pela
operação **menos avançada** (`_CONF_STAGE_ORDER`) — dizer `Ok` porque uma das dez
foi validada esconderia as nove restantes —, e operação que ainda não entrou na
esteira não conta, senão um documento recém-gerado nasceria vermelho. O índice é
lido **uma vez por request** e passado aos quatro cards: dentro do
`_conf_stage_counts` ele abriria os dois DuckDB oito vezes na mesma tela.

### O ciclo da esteira tem cinco paradas, e duas não são de mesa (§254)

`(Pending Legal, opcional) → Pending OTC → Pending MO e/ou FO → Pending FepWeb
→ Ok`. **Pending Legal** é hold manual (vence a derivação até ser solto).
**`Pending OTC` digitado REABRE a esteira** (§255): confirmação regerada volta
para a fila do OTC — o upsert limpa as três validações e o Enviado p/ cliente
(carimbos caem no undo; comentários ficam) e a mesa de OTC Ops é exigida quando
há algo a limpar; numa linha só em hold ele age como o release de antes.
**Pending FepWeb** é derivado e nunca se digita: validações feitas, envio
pendente — **Ok exige o `Enviado p/ cliente` preenchido**. Toda gravação da
esteira espelha no Pending Confirmation via `_mc_pc_sync` (chave MC `Trade ID`
= PC `Trade Number`): o estágio entra verbatim no Pending Status, e o Ok vira
Pending Digital Signature / Pending Original pelo SIGNATURE TYPE do RefData.
O Monitor tem CINCO cards (Legal e FepWeb nas pontas, botões de soltar/enviar
com trava da mesa de OTC Ops).

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

**Só as páginas genéricas de NDF trazem a entidade no deal** (campo `LE`:
JPM/MGT/LAWTON, resolvido do Settlement Location pelo `le-accronym`). Mercadoria
e FXO não têm o campo, e o fallback para `TradingBook` escrevia o nome do BOOK
(`ALUM-BRAZIL-BANCO`) na coluna Legal Entity. `_mc_legal_entity` resolve pela
lista `_MC_JPM_SOURCES`: mercadoria **e FXO** são sempre **JPM** — a mesa booka
termo e opção de commodity e a opção de câmbio no Banco J.P. Morgan, e é uma
entidade só. A FXO ficava em BRANCO esperando cadastro linha a linha, e as
confirmações que fechavam em Success no New Deals chegavam ao Track
Confirmations sem Legal Entity nenhuma — uma coluna vazia que ninguém tinha como
preencher, porque a resposta é sempre a mesma. A lista é a da **Legal Entity**, e
não a de LOB (`_COMMODITY_SOURCES`): a FXO é CEM e ainda assim é bookada no
Banco, então amarrar as duas perguntas na mesma resposta erraria uma das duas. A
razão social sai do `le-spn` (LE → NAME), nunca de um literal — `JPM` →
`BANCO J.P MORGAN S.A`.

### O prazo da esteira, e por que ele é em dias ÚTEIS

Cada mesa tem um SLA contado da **DATA DA OPERAÇÃO** (trade date) e não da data
em que a confirmação foi gerada — o prazo é do trade, e gerar o documento com
atraso não compra tempo novo. **OTC D+3, MO D+4, FO D+6**. Eles não se somam: MO
e FO correm em paralelo depois do OTC, e os dois contam do mesmo trade date.

Os prazos são **cadastráveis** (`manual-conf-sla`, uma linha por mesa) e o
`SLA_BIZDAYS` virou o fallback com os valores históricos. Quem lê é
`sla_days()`, cacheado por mtime porque o Monitor pergunta o prazo três vezes por
linha; **prazo em branco devolve o valor histórico**, e não "sem prazo" — uma
célula limpa pela tela apagaria o vermelho de toda confirmação atrasada em
silêncio.

**Dias úteis pelo calendário ANBIMA**, o mesmo `static/data/anbima.json` que o
resto do app usa (`manual_conf` relê o arquivo em vez de importar o `routes`, que
seria circular — o que se repete é a leitura, não o dado). O `aging` também é em
dias úteis: contando corridos, a confirmação de sexta-feira nascia com três dias
de atraso na segunda, e o vermelho aparecia sem ninguém ter deixado de
trabalhar.

`sla_state()` devolve a luz — `ok` (2+ dias de folga), `warn` (véspera ou o
próprio dia), `late`, e **`done` para a etapa já validada**: o prazo dela parou
de correr, e mantê-la vermelha cobraria um trabalho que já foi feito. No Monitor
o item vale pela operação **mais apertada** do grupo (um documento cobre várias
operações; se uma estourou, o grupo estourou). O verde é neutro no card de
propósito — pintar o que está no prazo é pintar quase a fila inteira, e aí o
vermelho some no meio.

**Preencher a coluna de validação pela GRADE do Track é validar**, e passa
pelas mesmas três regras do `mark_validated` — carimbo de quem assinou, mesa
certa e justificativa fora do prazo. Antes, `api_mc_upsert` copiava
`VALIDADO p/ MO` como texto livre: a validação entrava sem dono, sem motivo do
atraso e assinada por qualquer papel. O que separa validação de ajuste de
cadastro é a **transição** (a coluna estava vazia e passou a ter data), o prazo é
medido no estado **anterior** (depois da escrita a própria `sla_state` diz
`done`), a data digitada é preservada, apagar a data apaga o carimbo, e o lote é
tudo-ou-nada (HANDOFF §232).

**Passado o prazo, a validação exige justificativa.** `mark_validated` levanta
`SlaCommentRequired` e o endpoint devolve **409 com `sla_comment_required`** —
409 e não 400 porque o pedido está bem formado, o *estado* é que pede mais um
campo. O motivo vai para a coluna daquela mesa (`OTC Comments`, `MO Comments`,
`FO Comments`) — uma por etapa, porque o atraso do MO não explica o do FO e um
campo único faria a segunda mesa sobrescrever a explicação da primeira. A tela é
onde se pede; o endpoint é onde se garante.

### A cobrança das validações é um card do Control Panel (§257)

`confescalation` manda por e-mail o que está parado na esteira, e lê a **mesma**
`manual_conf.load_all()` com o `Pending` derivado que o Track e o Monitor
mostram — um relatório que conta de outro jeito cobra uma fila que a tela não
tem, e a mesa deixa de acreditar nos dois. São **sete listas** de destinatários
(`_CE_REC_KEYS`), uma por e-mail: OTC, Sales Support (rotina), Sales Support
(escalação) e os quatro grupos de Front Office de `_CE_FO_GROUPS`. Quatro coisas
que não dão erro nenhum quando se mexe:

- o grupo de FO casa pelo **tipo de confirmação** (`confirmation_type`), nunca
  pelo texto cru da coluna. **`OPTION EDG` não é produto** — é `FXO` × LOB
  `EDG`; cadastrado como produto, o grupo nunca casa com linha nenhuma, em
  silêncio;
- **Pending FO sem grupo vai para `unmatched`** (amarelo no card e linha no
  log), porque confirmação que some do relatório é confirmação que ninguém
  cobra;
- a rotina é segunda e quinta, e o feriado **ROLA** para o próximo dia útil —
  `_ce_is_routine_day` pergunta ao contrário (*que segunda/quinta desemboca em
  hoje?*), senão a semana inteira se perde quando a quinta é feriado;
- a escalação leva o **último dia** (`left == 0`) e o vencido, nunca a véspera:
  o `warn` do SLA acende em D-1, e escalar ali chega com a mesa ainda dentro do
  prazo. `empty` (nada pendente) e `no_recipient` (lista vazia) são desfechos
  **distintos** — o segundo é cobrança que não saiu de casa.

### O BACC EA Metrics é a mesma esteira, extraída para o time de métricas

O card **BACC EA Metrics** (Control Panel › *Economic Affirmation Routines*,
ao lado do Manual Deals EA e do MT300) manda, todo dia útil ANBIMA às
**16:00 BRT**, um e-mail com as operações manuais em anexo `.xlsx`. A fonte é a
MESMA `manual_conf.load_all()` que o Track Confirmations mostra, com DOIS cortes
e ordenada pelo **Aging do maior para o menor** — quem espera há mais tempo vem
primeiro, como na fila do Monitor (a chave da ordenação é numérica: o aging é
gravado como TEXTO, e por texto `'10'` viria antes de `'9'`; vazio vai para o
fim, porque linha sem idade não encabeça um relatório de atraso).

- **Sem Data Callback**, e o teste é a CÉLULA em branco, não um status. O
  callback é a conferência por telefone com o cliente e é ele que fecha a
  operação manual do ponto de vista da métrica; a planilha é a lista do que
  ainda falta. A coluna vazia é exatamente o que o Track Confirmations mostra —
  derivar de um Pending ou de um estágio criaria uma segunda regra, que
  discordaria da tela no primeiro caso de borda.
- **Pending diferente de `Ok`**, e este é o status, porque `Ok` é justamente o
  nome do fim da esteira: a confirmação que terminou saiu da fila. De quebra,
  isso deixa o anexo restrito ao banco `pending` — o mesmo conjunto que o
  Monitor mostra, e o único cujo E-mail Subject o app preenche sozinho.
- **O notional ocupa TRÊS colunas**, e as duas últimas saem repartidas da coluna
  `Notional Amount CCY` da esteira por `manual_conf.split_notional_ccy`:
  `Notional/Qty` (o número cru), `National Currency` (o CÓDIGO) e
  `Notional Amount` (o VALOR). A moeda **não sai da coluna `Moeda`**: aquela é o
  ATIVO da confirmação e em mercadoria guarda a commodity (OLEO, PLATTS), que
  não é moeda nenhuma — era isso que essa coluna dizia antes.
- **O TIPO é declarado por coluna** (`text` / `num` / `money` / `date`), não
  adivinhado do conteúdo. A versão anterior escrevia como inteiro tudo que
  "parecia dígito", e errava dos dois lados: um notional com centavos
  (`250000.50`) não passava no teste e ia para o Excel como TEXTO — sem somar e
  sem ordenar —, e um Trade ID todo numérico viraria número, perdendo o zero à
  esquerda. `_bacc_num` aceita as duas escritas que convivem no banco
  (`1500000` e `1.500.000,00`).
- **`money` é valor e leva a máscara de milhar; `num` é contagem e não leva** —
  o Aging em `12,00` dias não quer dizer nada. E o código da máscara é escrito na
  convenção INVARIANTE do formato de arquivo (`#,##0.00`, com `,` de milhar e
  `.` de decimal), **sempre**: quem desenha a célula é o Excel de quem abre, com
  o separador do idioma DELE, e num Excel pt-BR esse mesmo código sai
  `1.500.000,00`. Escrever `#.##0,00` (a máscara como ela se lê em português)
  produziria um código malformado e o valor sairia errado sem erro nenhum. Valor
  que não parseia fica texto e **sem** máscara: máscara sobre texto não faz nada,
  mas prometeria um número. A largura da coluna mede o que se VÊ — `1500000` são
  7 caracteres e a célula desenha 12; sem isso a coluna nasce estreita e o Excel
  mostra `####`.
- **A mesma falta vira badge no Monitor**, e só no card de **Pending FepWeb**:
  ali a confirmação está validada esperando o envio ao cliente, e o callback é o
  que precisa ter acontecido ANTES desse envio — nos outros estados a coluna
  está em aberto por construção, e o vermelho só diria que a esteira mal
  começou. O item traz `no_callback` como CONTAGEM (`_extra_card`), não como
  bandeira: um documento cobre várias operações, e "falta callback" num grupo de
  dez não diz se falta em uma ou nas dez — por isso o número aparece no badge a
  partir de duas. A cor não reusa a do prazo (`.mc-sla-late`): as duas marcas
  podem valer ao mesmo tempo, e o vermelho daqui diz que falta um passo, não que
  estourou o relógio.
- **Planilha vazia VAI assim mesmo.** Um dia sem operação manual é ele próprio a
  métrica, e o único motivo de não enviar é lista de TO em branco
  (`no_recipient`), que o card mostra em âmbar — é relatório que não saiu de casa.
- As colunas de `_BACC_COLUMNS` são contrato com quem consolida, **grafia
  incluída**: `Conterparty Name` está escrito assim de propósito. `Born Age`,
  `Notional Amount` e `Notional Amount USD` saem sempre **vazias** (preenchidas
  do outro lado) e continuam no arquivo porque a POSIÇÃO das colunas é o que o
  consumidor casa. `Comments` carrega o **assunto do e-mail de recap**.
- **Auto-fit é contagem de caracteres**, não medida de texto: o openpyxl não tem
  auto-fit de verdade. Daí o teto por coluna — o assunto em `Comments` tem 120
  caracteres e, sem ele, empurraria as outras onze para fora da tela.
- O corpo do e-mail **não repete a tabela**: ele nomeia o anexo e diz quantas
  linhas são, que é o que distingue "não havia nada hoje" de "o anexo veio
  truncado".

### A coluna E-mail Subject se escreve sozinha

Ela guarda o assunto do **recap interno** que está na pasta da confirmação, e
quem sabe a resposta é o arquivo — não quem digita. Quem varre a pasta é
`_mc_confirmation_docs`, então a coluna se atualiza nos dois lugares que o
chamam: o `/api/manual-confirmation/docs` (os chips de e-mail dos cards do
Monitor) e a **tela de validação**. `_mc_email_subject` lê o assunto memorizado
por **(caminho, mtime, tamanho)** — o caminho sozinho manteria o assunto do
e-mail substituído pela vida do processo —, `_mc_sync_email_subjects` junta
`{Trade ID: assunto}` e `_mc.set_email_subjects` grava **só o que mudou**, num
lote por chamada.

**O casamento é em DOIS passos, e a ordem separa o certo do plausível:**

1. **pelo Trade ID no NOME do arquivo** — a mesa salva
   `Internal Recap DBH-1AAA.msg` ao lado do PDF de cada operação, e este passo é
   exato;
2. **recap ÚNICO na pasta** — ninguém nomeia operação, mas só há um e-mail; ele
   é o recap daquele booking e vale para o grupo inteiro (é o recap nomeado por
   contraparte/data).

Fora disso **não se escreve nada**. A primeira versão pegava o *primeiro* recap
da pasta e o carimbava em todas as operações do grupo: a `DBH-1BBB` ficava com o
e-mail da `DBH-1AAA`, e uma operação **sem recap próprio** recebia o assunto de
outra confirmação — porque a pasta é cliente × dia × produto e guarda mais de uma
(OLEO e PLATTS do mesmo dia), e `_mc_confirmation_docs` cai para a listagem
inteira quando o funil não casa. Célula vazia pede o dado; célula errada aponta
para um e-mail que não confirma aquele trade.

Três coisas que não dão erro nenhum: sem o "só o que mudou", cada abertura do
Monitor reescreveria a esteira inteira; sem o lote, cada chave releria os dois
DuckDB (o Monitor manda até 200 itens de uma vez); e a falha da gravação é
engolida com log, porque listar documentos é o serviço que a página pediu — um
banco travado não pode transformar o Monitor inteiro em "no PDF".

Dois limites conhecidos: o arquivo só é reconhecido como recap se o NOME contém
`internal` ou `recap` (`_MC_MAIL_TOKENS`) — salvo com outro nome ele não vira
chip nem assunto —, e a coluna só se preenche quando alguém OLHA a confirmação
(card do Monitor ou tela de validação). Linha que já saiu da esteira (banco `ok`)
não passa por nenhum dos dois e fica com a célula como estava.

### Validar é abrir o documento, não clicar num botão

O Validate do Monitor abre **`/manual-confirmation/validate`** (PDF do Electronic
Inventory de um lado, checklist do outro), e não carimba no clique: quem assina
está dizendo que olhou o documento.

Ela é **irmã** da `confirmations/validate.html` (o checklist do OTC no New Deals)
e não uma evolução dela — aquela valida a confirmação que a tela de geração
acabou de produzir, chaveada por contraparte × mercadoria × data; esta valida uma
**etapa da esteira**, chaveada pelos Trade IDs do grupo, e serve as três mesas.
Fundi-las obrigaria uma a carregar os dois modelos de chave.

**Gerar é gravar.** O checklist do New Deals fecha o ciclo do DOCUMENTO
(New → Generated → Success) e **não carimba a etapa do OTC na esteira** — o
`_mc_stamp_otc_validated` foi removido dos quatro `/validate` do New Deals, e só
o `_mc_stamp_generated` continua. Carimbando, a confirmação nascia já na mesa
seguinte e a fila de Pending OTC do Monitor ficava vazia por construção: o OTC
não tinha onde conferir o que ele mesmo acabara de emitir, com o D+3 correndo em
silêncio. **E ele não avisa no sino**: os quatro `/validate` do New Deals
emitiam um `Confirmation Validated`, e a mesma confirmação gerava DOIS itens
dizendo validado — este, do documento, e o `Validated by OTC` da esteira, que é
o que a mesa precisa ver (diz quem assinou, quantas operações e para quem). O
ciclo do documento continua no card de Confirmations do New Deals Monitor, que é
onde ele já era acompanhado.

**O aviso da esteira leva ao Confirmations Monitor**, e não à página que emitiu
o documento: quem recebe vai CONFERIR a confirmação, e conferir é lá. O rótulo
`page` é `'Confirmation'` (o mesmo da esteira — ver `_NOTIF_PAGE_URL`); o
produto vive no texto do aviso, que é onde ele continua legível.

**GERAR também é só no Monitor**, e com isso o ciclo inteiro mora num lugar só.
O botão **Confirmation** saiu da barra das quatro páginas de New Deals (o
contêiner `.confirmationBtn` e o diálogo de grupos foram apagados): o card de
**Pending OTC** oferece **Generate** enquanto não há PDF na pasta da confirmação
e **Validate** depois que há — é a mesma condição que já riscava o botão, agora
com um destino em vez de um aviso. Só o OTC (nas etapas de MO e FO, sem contrato
o botão continua riscado: elas conferem o papel, não o produzem).

O que traduz uma coisa na outra é **`/manual-confirmation/generate?keys=…`**: a
esteira conhece a LINHA (Trade ID, Produto, data da operação) e o New Deals
conhece o GRUPO (contraparte × mercadoria × família), que é a unidade do
documento. O casamento é pelos **Trade IDs** — os mesmos do card de Confirmations
do New Deals Monitor —, nunca por contraparte × mercadoria, que seria um de-para
por texto entre dois cadastros que normalizam nomes de jeitos diferentes. Sem
destino, a rota devolve 404 com a `manual-generate-error.html` dizendo o motivo
exato (produto sem tela, linha sem data, arquivo-dia sem a operação); um 404 seco
não diz qual dos três é.

No editor sobrou **um botão**: o `Salvar Word + PDF no Inventory`. O
`Imprimir / Salvar PDF` saiu dos nove templates de confirmação — o PDF é gravado
no Inventory, e imprimir por fora produzia um documento que a esteira não vê. E
quando o editor foi aberto pelo Monitor (a rota manda **`mc_keys`** na URL), a
tela que abre depois de gravar é a validação da **ESTEIRA**, não o checklist do
documento: é o mesmo ato — quem gerou está com o papel na frente e assina pela
mesa de OTC. Validando, a confirmação segue para MO/FO; fechando sem validar, ela
continua em Pending OTC, agora com o PDF na pasta, e o card volta a oferecer
Validate. Sem `mc_keys` nada muda (abre o checklist do documento), e é por isso
que o `openValidate` é o único ponto tocado nos nove arquivos.

O ciclo do DOCUMENTO (New → Generated → Success) continua fechando no card de
Confirmations do New Deals Monitor sem ninguém marcar nada: quando o grupo já tem
linha na esteira, **a etapa dela vence o status do documento**, e
`_conf_esteira_stages` traduz toda etapa depois do OTC para `Ok`.

**Validar é SÓ no Monitor.** O botão Validate saiu dos diálogos de
Confirmations das quatro páginas de New Deals (FWD Start, NDF Comm, Opt Comm,
Opt FXO) — dois lugares validando era ter duas respostas para a mesma pergunta
(HANDOFF §241).

**Validar e Rejeitar vivem os dois na tela de validação**, não no card do
Monitor. São as duas respostas à mesma pergunta — o documento está certo? — e as
duas exigem tê-lo aberto; no card, o Reject ficava a um clique de quem nunca viu
o papel. O card tem um botão só. O Reject continua sendo só das mesas seguintes
(`can_reject = stage != OTC`): o OTC é quem monta o documento e não tem a quem
devolvê-lo.

**O aviso do sino vai para a mesa em que a confirmação CAIU**, e não para o
time inteiro (`_MC_STAGE_NOTIFY_ROLES`): Pending OTC → `BO`, Pending MO →
`MO`+`BO`, Pending FO → `FO`+`BO`, Pending MO/FO → as três. `MASTER` entra em
todas (sem isso o superusuário perde a esteira de vista, em silêncio) e `ADMIN`
em nenhuma. A etapa sai de `pending_stage(row)` **depois** do carimbo — do
ESTADO, não da etapa que acabou de ser assinada —, e é isso que faz o cadastro
`manual-conf-validation` valer de graça: produto isento de FO nunca avisa o FO.
Confirmação em `Ok` volta a avisar todos. O Back Office entra em todas porque
**assinar e receber são perguntas diferentes**: assinar é um ato de uma mesa só,
receber é acompanhar, e o documento é dele. Para isso a coluna `target_role`
passou a aceitar vários papéis separados por vírgula (`_notif_roles`), com o
valor antigo de um papel só continuando válido (HANDOFF §231).

**Cada etapa é assinada pela SUA mesa** (`_MC_STAGE_ROLE`): Pending OTC → papel
`BO` (a mesa de OTC Ops é o Back Office do cadastro de papéis), Pending MO → `MO`,
Pending FO → `FO`. É o que separa as funções — quem monta o documento não pode
assiná-lo pela mesa seguinte. **Master é a única exceção; `ADMIN` NÃO é passe
livre**, porque administrar acessos não é sentar na mesa. Rejeitar segue a mesma
regra: é a outra resposta à mesma pergunta. Três camadas, e a que vale é a
última: no Monitor o botão verde vira um de só leitura, na tela de validação
somem os dois botões, e o endpoint devolve **403 com `stage_forbidden`**. Abrir a
tela continua livre de propósito — esconder a confirmação faria o OTC deixar de
ver o que o MO está conferindo.

**O checklist muda por mesa: MO e FO conferem só os DADOS ECONÔMICOS**
(`CHECKLIST_ECONOMICO` = operações da Tabela de Referência + datas). Contraparte,
CNPJ e a data do CGD são cadastro e contrato, e quem responde por eles é o OTC,
que é quem monta o documento — pedir os quatro itens às três mesas faria duas
delas assinarem por uma conferência que não é sua.

### As colunas novas do banco não precisam de script de migração

`ensure_db()` roda `ALTER TABLE … ADD COLUMN IF NOT EXISTS` para toda coluna de
`DB_COLUMNS` que faltar. Isso importa porque `apps/static/data/db/` está no
`.gitignore`: o banco da instância do time é anterior à coluna, e o `INSERT` —
que lista as colunas explicitamente — falharia com *column not found*, derrubando
as duas telas depois de um pull. **Coluna nova em `COLUMNS` é só isso**; não
escreva um script em `scripts/` para ela.

### O relatório do dia é o MAIS RECENTE, não o primeiro em ordem alfabética

O Latam Desk Position é **reemitido no mesmo dia**, e quando é, a pasta passa a
ter dois `FbiRptLatamDeskPostion-NY-*`: o consumido de manhã só é apagado quando
alguma linha entrou (`kept`), e o novo chega ao lado. `sorted(...)[0]` pegava o
**mais antigo** e regravava o JSON do dia com a posição da manhã dizendo
*"sucesso, N linhas"* — falha que se reporta como êxito. O Save Daily Settlement
era pior: processava os dois na ordem crua do `os.listdir`, então o vencedor
dependia do sistema de arquivos e os dois caminhos podiam **discordar sobre qual
é o relatório do dia**.

`_latam_pick_source` é o seletor único dos dois — **mtime mais recente, nome só
desempata**. Os preteridos **ficam em disco** (apagar um arquivo que não foi lido
destrói a única cópia) e voltam em `ignored`, que o SweetAlert do import mostra:
pasta com dois relatórios é o estado que produz o defeito, e ele não pode ficar
invisível. Isso alcança mais do que a tela — `_latam_equity_b3_index` lê o
**último** Latam disponível, então um Latam parado na manhã deixa o swap **e a
opção** de equity sem valor (HANDOFF §281).

### A inversão da moeda fraca é do PAR, não da coluna

A API manda o strike da moeda fraca como **moeda/BRL** (3,33 MXN por real;
1,2956 CNH por real) e a aplicação inteira trabalha com **R$/moeda**. Quem
decide a inversão é `_ndf_weak_leg(qty_ccy, other_ccy)`: a moeda fraca **em
qualquer das duas pernas**, porque qual delas carrega o notional depende de como
a mesa bookou, não da moeda. Par com as **duas** pernas fracas devolve `None` —
sem BRL não há convenção para apontar, e inverter seria chute.

A inversão acontece **uma vez, na importação**; daí para a frente o `Rate`
gravado é R$/moeda e ninguém mais mexe nele. O arquivo TER só **arredonda** pelas
casas do cadastro (`INV DECIMALS`). Antes eram duas regras olhando pernas
opostas — a importação a `Other Quantity Units`, o TER a `Quantity Currency` —, e
como as condições são complementares o arquivo saía certo **por compensação**,
enquanto a coluna Rate da tela, o contravalor do MT300 (`qty × rate`) e a taxa do
Intrag ficavam com o valor cru sempre que o notional estava na moeda fraca
(HANDOFF §282).

### Outras

- **`Sent` e `Success` só voltam para Amend por dado ECONÔMICO**
  (`_ND_AMEND_KEEP_STATUS`). `Sent` é o arquivo de registro já enviado à B3 e vem
  **antes** do `Success`, então a janela desprotegida era justamente a da espera
  do retorno: um pull que trocasse o Other Book devolvia para a fila, sem
  Checker, a operação que a mesa acabou de mandar registrar. A célula segue
  **destacada** (`AmendChanged`) nos dois casos — o que não regride é o status —,
  e os demais status caem para `Amend` sempre. A varredura do box de commodities
  **não** tem essa proteção de propósito: a regra dela é a mesma do caminho do
  navegador (`otc-fileupload.js`), e mexer num lado só faria o mesmo recap
  amendar de dois jeitos (HANDOFF §283).
- **O Strike do NDF FWD Start não derruba um Success para Amend.** O que a B3
  registra é o **Strike Set Offset** — o spread sobre uma taxa que só se conhece
  no dia do fixing; o Strike da linha é a projeção dessa taxa no momento do
  booking, e a Athena a recalcula a cada pull. A operação não mudou, mudou o
  mercado, e sem isso todo FWD Start já registrado voltava sozinho para a fila. A
  célula continua destacada (o campo entra em `AmendChanged` como qualquer
  outro); o que não regride é o status. A lista é
  `_ND_AMEND_COSMETIC_BY_PRODUCT`, **por produto** — o Strike é econômico em
  todos os outros —, e por isso `_nd_api_amend` recebe o `product` de quem
  chama. Produto vazio ("não sei") vale só a lista geral: o default é econômico,
  porque um campo esquecido virando Amend custa uma revisão e o contrário custa
  uma operação registrada errada.
- **`Notional Amount CCY` é a moeda DO NOTIONAL, e a coluna `Moeda` ao lado não
  serve para isso**: aquela é o ATIVO da confirmação, e em mercadoria guarda a
  commodity (OLEO, PLATTS). A moeda vem do campo que a carrega em CADA produto
  (`_MC_NOTIONAL_CCY_FIELD`), e não de uma cadeia de fallback — um `first(...)`
  genérico pegaria o primeiro campo preenchido, que nem sempre é o que a mesa
  chama de moeda do notional: **Strike Currency** em termo e opção de mercadoria
  e em opção de câmbio, **Quantity Currency** nos NDF genéricos. A célula guarda
  os dois num texto só (`USD 1500000`) com o número CRU — a formatação é
  ortogonal e mora na tela, e gravar `1,500,000.00` obrigaria o relatório do BACC
  a desfazer a máscara para escrever um número no Excel. Ela é escrita no
  MAPEAMENTO, então vale para as linhas novas; as antigas ficam em branco porque
  a moeda de mercadoria não existe em lugar nenhum da linha para ser derivada
  depois.
- **`blank` no filtro por coluna traz o que está VAZIO.** É o único jeito de
  procurar a ausência: o campo casa por conteúdo, e "nada" não se digita. O termo
  vira a regex `^\s*$` com **smart search desligado** — ligado, o DataTables
  reescreve a expressão e ela deixa de casar a célula vazia. A palavra só é
  reservada quando é a ÚNICA coisa no campo, senão uma contraparte chamada
  "Blank Trading" ficaria impossível de procurar; e o `title` do campo é onde ela
  se anuncia, porque num texto livre ninguém adivinha que existe.
- **Os NOMES das colunas da esteira são os da planilha legada, os RÓTULOS são
  ingleses.** Os nomes (`Data de vencimento`, `Moeda`, `VALIDADO p/ MO`) são o
  esquema dos dois DuckDB e não podem mudar — renomear um quebraria o banco de
  quem já o tem em disco. Quem traduz é o `COLUMN_LABELS`, que por isso é a lista
  **COMPLETA** das colunas: coluna sem entrada apareceria na tela com o nome do
  banco. A tradução br/es fica no `COLTR` do template, e não em `data-lang`,
  porque o cabeçalho é montado em JS depois do load — o I18nManager traduz os
  `[data-lang]` uma vez, no load. Nas LISTAS (edição em massa, painel de colunas)
  vale o `labelFull`: os três `Time Stamp` compartilham o rótulo curto de
  propósito, e só quando há empate o nome do banco entra, porque ele já diz a
  mesa.
- **Thread de scheduler não tem application context.** `render_template` (o
  corpo dos e-mails) e `current_app` (o `_get_logo_path`) exigem um, e sem ele o
  disparo morre com *Working outside of application context*. O sintoma engana:
  o botão **Run** do Control Panel funciona, porque roda dentro de um request, e
  só o automático falha — foi assim que o aviso das 19:00 do Deals Monitor parou
  em silêncio. Use `with _app_context():` (no-op dentro de um request; o app é
  capturado no `record_once` do blueprint) e envolva a **montagem inteira** da
  mensagem, não só o `render_template` — envolver só ele troca o erro por outro
  três linhas abaixo, no logo.
- **Jobs agendados rodam no horário do Brasil, não no do servidor.**
  `_br_now()` (`zoneinfo` `America/Sao_Paulo`, caindo para `-03:00` fixo quando
  falta `tzdata` — o caso Windows) sustenta o e-mail de pendências das 19:00/
  19:30, a manutenção das 11:30 do Pending Confirmation e a planilha de
  Pending das 10:45 (HANDOFF §240). `datetime.now()` é o
  relógio local do servidor e disparava tudo na hora errada, em silêncio. Como
  a instância reinicia várias vezes ao dia, `_ndm_pending_catch_up()` também
  dispara na subida as janelas já passadas do dia; o arquivo de claim em disco
  é o que impede isso de virar e-mail repetido.
- **Os três schedulers de IMPORTAÇÃO só trabalham entre 08:00 e 20:00 BRT** — a
  API de NDF, a de FXO e a varredura do box de commodities. O **intervalo de
  cada um continua sendo o dele** (20/60/30 min); o que a janela decide é se
  aquele tique faz alguma coisa, e o `continue` fica **antes do `try`** — dentro
  dele o poll já teria custado a ida à Athena. As duas pontas são **inclusivas**
  (o tique das 20h em ponto ainda importa) e a janela é cadastrável em
  `IMPORT_POLL_WINDOW`; valor malformado deixa a janela **sempre aberta** com
  aviso no log, porque um `.env` digitado errado não pode desligar a importação
  do dia em silêncio. Ela aparece no log de subida dos três, ao lado do
  intervalo (HANDOFF §283).
- **O Pending Status tem TRÊS donos, e eles não se pisam.** Quem escreve a coluna
  do Pending Confirmation depende do produto:
  1. **Só NDF Vanilla e NDF Other Publisher** caem na regra de **prazo e
     assinatura** (`_pc_signature_pending_status`): prazo (Settlement − Trade)
     ≤ 60 dias corridos → `Exception FepWeb`; senão, pelo SIGNATURE TYPE do
     Reference Data — Internal → `Exception Digital Fep Web`, Digital →
     `Pending Digital Signature`, Manual **e não cadastrado** → `Pending
     Original`. É uma função só, chamada pelo New Deals, pela importação do
     Pending Update e pela edição em massa da tela; eram três cópias e elas
     divergiam em silêncio (o prazo curto saía com dois rótulos diferentes e o
     ramo `internal` só existia num dos lados).
  2. **Todo o resto passa pela esteira** de validação, e o Pending Status dele é
     a **etapa** (`_PC_ESTEIRA_STATUSES`). Prazo e assinatura **não opinam**:
     `_pc_signature_status` recebe o status atual e devolve a etapa intacta
     quando ela é de esteira. Sem isso, mexer na data de uma linha em `Pending
     MO` a devolvia para `Pending Original` e a confirmação sumia da fila da
     mesa sem ninguém ter validado nada — a tela manda o Pending Status atual no
     payload do `/derive` justamente para o servidor saber disso, e a importação
     lê o estágio que cada Trade Number já tem antes do upsert. **FWD Start
     entra na esteira mesmo com prazo curto**, e por isso o teste de produto vem
     ANTES do de prazo em `_generic_nd_pending_status`.
  3. **A regra do VENCIDO é a única universal** (`_pc_apply_auto_rules`):
     Maturity ≤ hoje e status **não resolvido** → `Exception FepWeb` **e** Status
     `Ok`, em qualquer produto e qualquer etapa, esteira inclusive. O teste é
     `not _pc_is_ok_status(...)` e não "começa com Pending": *Abonado via PDF* e
     *Client Treasury Allowance* também são pendências e ficavam de fora,
     envelhecendo para sempre numa operação já liquidada. As duas colunas mudam
     juntas — é isso que move a linha para o DB `ok`.
- **A planilha de Pending de uma data anterior sobrescreve o arquivo de sempre,
  e isso é intencional.** O card Pending Confirmations Spreadsheet Metrics aceita
  uma **Reference date** (padrão hoje, futuro bloqueado). Hoje = a rotina de
  sempre, situação viva dos três DBs. Data anterior monta a planilha do
  **snapshot** daquele dia (`cache/pending-confirmation/AAAA/MM/DD`, a foto que a
  manutenção das 11:30 grava) e grava no **mesmo** `PENDING - Outstanding
  Confirmation OTC.xlsx`: o time global de métricas lê esse caminho por OLEDB
  (`Confirmation_Latam`) e tem um caminho só — um arquivo datado ao lado não
  seria visto por quem consome. Pedida a data anterior, grava-se, o time puxa, e
  a corrida seguinte (Run com a data de hoje, ou a rotina das 10:45) devolve o
  arquivo. Três regras que não dão erro nenhum se caírem:
  - o snapshot **não** é refiltrado por `_pc_target_category` — ele já é o balde
    `pending` daquele dia, e recomputar responderia pelo calendário de hoje;
  - snapshot ausente é **404**, nunca queda para os dados de hoje: como o nome do
    arquivo é o mesmo, nada distinguiria a planilha certa da errada;
  - o **`ref` do `_pcx_status_write`** é o que diz que foto está no share neste
    momento (linha âmbar no card). Sem ela, o arquivo com dado de 08/08 é
    indistinguível do de hoje — o preço de reusar o nome canônico. Ela cai
    sozinha na gravação seguinte, que reescreve o status inteiro.
- **A API nunca entrega a perna Lawton como deal próprio.** O arquivo visão
  Lawton do registro TER (Other Publisher e FWD Start) sai de um **espelho
  sintetizado no envio** (`_nd_lawton_mirror` → o mesmo
  `_generic_ndf_ter_line`): deal do balde BANCO com LAWTON no Client gera a
  visão invertida. O par é por **termos econômicos** (`_nd_lawton_sig`: trade
  date, settlement, notional), nunca por Deal ID — cada perna intragrupo tem o
  seu —, e uma perna Lawton explícita no lote consome UMA assinatura para o
  espelho daquele trade não duplicar (HANDOFF §243).
- **Os textos da Parte A do FWD Start vivem no `routes.py` de propósito**
  (Banco J.P. Morgan S.A. / Filial Brasileira, resolvidos pela LE do grupo):
  a grafia é a do documento assinado, diferente da do Reference Data que o
  `le-spn` guarda. Não os converta em mapping — seria uma segunda lista das
  mesmas entidades (HANDOFF §239). LE ausente/mista deixa a Parte A em branco
  com aviso, e o Save recusa (`400 missing_partea`).
- **Botão de e-mail precisa de endereço ABSOLUTO, e ele é configuração.**
  `url_for` é relativo (não serve fora do navegador) e `request.url_root` não
  existe na thread de um scheduler — num Run local ele devolveria
  `http://localhost:5005`, link morto para quem recebe. `_otc_app_url()` lê
  **`OTC_TRACKER_URL`** do `.env` e, sem ela, monta `http://<hostname>:8051`
  — a porta é o **`routes.APP_PORT`**, UMA constante, porque o número aparece em
  três lugares que se leem de fora do código (o botão de e-mail, o link do
  e-mail de versão nova e o `run.py`) e os três diziam 8050 enquanto a instância
  subia na 8051. Botão de e-mail com a porta errada não dá erro: leva a pessoa a
  uma página que não abre. Defina a variável na instância do
  time — o padrão só acerta se o hostname resolver na rede de quem lê o e-mail
  (HANDOFF §257).
- **`reportlab` é importado preguiçosamente** (PDFs de confirmação e folha de
  liquidação do NDF Summary): sem a lib o e-mail sai *sem* o anexo, em vez de
  falhar.
- **Só `isCancelled = true` significa cancelado** na Athena. `isDead` é estado
  interno e esses registros *são* importados (`_api_rec_is_cancelled`, §173).
- **No File Interpreter** (a tela; TODO o nome é `file-interpreter` desde
  2026-08-21 — página `/file-interpreter`, APIs `/api/file-interpreter/*` e
  dados em `static/data/file-interpreter/`. O legado não quebra: a URL antiga
  `/file-interface` redireciona, as APIs antigas são ALIAS das novas (aba
  aberta com HTML de antes do deploy), o valor antigo no `Page_Access` é
  normalizado na leitura (`_get_page_access`), o sino aceita os dois rótulos
  nos três mapas, e a pasta antiga é MIGRADA na subida — template criado pela
  tela na instância do time não está no git, e renomear diretório não pode
  sumir com cadastro de runtime), **"campo em branco" se cadastra como Source
  `Fixed` com valor VAZIO** — nunca como Page com o dropdown limpo ou origem "—": Source =
  Page significa "o gerador manda o valor" (o motor injeta o calculado pelo
  `seq`; o detalhe da origem é documentação), então limpar o detalhe não
  esvazia nada, em silêncio. Foi a Data de Fixing do FWD Start (HANDOFF §249).
- **Um template do File Interpreter pode ter VARIANTES por par de pernas**
  (`base_key` + `le_pair`, criadas pelo Add Template do cabeçalho): o gerador
  continua chamando o motor pela chave BASE e quem escolhe a variante é o
  motor (`_fi_variant_key`), pelo par do deal — variante ligada à página vence
  a sem página; sem variante para o par, vale o base byte a byte. A variante é
  cópia completa (mais campos podem virar Fixed — conta, Participante do
  header, que aí dispensa o `b3-accounts`) e pode cadastrar o **`file_name`**
  do arquivo gerado (em branco = `{PREFIX}_{BUCKET}.txt` de sempre). Três
  coisas que não dão erro nenhum: o par das **quatro** páginas que geram
  arquivo (FWD Start, Other Publisher, Commodities e agora o **Vanilla**) usa a
  regra do BUCKET — linha com cliente JPM é a perna espelhada → `LAWTON x JPM`
  —, e o preview de cada uma escolhe a variante por essa MESMA regra, senão a
  tela mostra um layout e a B3 recebe outro. O `pairSimple` (LE × contraparte,
  `MGT x JPM`) segue no espelho do navegador mas nenhuma página o usa: ele era
  do tempo em que o Vanilla só exibia. A cópia da regra no navegador
  é o `static/js/fi-ter-pair.js` e `check_fi_variants.py` prova que as duas
  concordam; e o modal de criação **achata o `source_by_page`** da página
  escolhida nos campos planos — sem isso o override herdado do base venceria
  a edição feita na variante, em silêncio.
- **Nem toda variante é por par de pernas.** Os arquivos da **Intrag** (seção
  `Intrag` da biblioteca: `intrag-ndf` e `intrag-option`, `;`-delimitados, 30 e
  38 colunas, sem header) se dividem por **PRODUTO**, e é o `variant_label` que
  as nomeia — `le_pair` fica vazio. O rótulo é **só de tela**: quem o motor
  consulta para escolher variante continua sendo o `le_pair`, então as quatro
  versões (`NDF Commodities`, `NDF Vanilla / Other Publisher`, `Opt
  Commodities`, `Opt FXO`) são **catálogo** — documentam o layout que
  `_save_intrag_ndf_entry`, `_save_intrag_ndf_moeda_entry` e
  `_save_intrag_opt_entry` gravam, e por isso nascem `status: library`. Sem o
  rótulo as duas versões apareciam as duas como "Default" na tela, e a tabela
  de moeda é a de mercadoria com **outro significado** da coluna Trade Price em
  diante — cada divergência vive num `source_by_page` do base. Onde se alcança
  a versão é o seletor **Versions** do cartão do template (a variante não vive
  no rail), e ele é um `select` e não uma fileira de chips porque o Termo tem
  quinze.
- **O Source Field/Value aceita FÓRMULA cadastrada** (builder por dropdowns no
  Edit Sources e no modal da variante): `FIELD`, `DATE`, `BIZDIFF`, `ADDBIZ`,
  `LOOKUP(mapping; IN; OUT; Campo)` e `CASE(Campo; DE=PARA; …)`, argumentos por
  `;`, campo casado com o deal pelo nome da COLUNA cego a caixa/espaço. No
  `CASE`, valor fora da lista devolve VAZIO e o motor o completa com espaços na
  largura — é assim que se cadastra "e no resto, branco" (o Tipo Média
  Asiático em branco para VANILLA). E o page-spec é **relido a cada abertura
  do preview** (`fiLoadSpec`), então template editado vale no próximo duplo
  clique, sem refresh da página; fetch que falha mantém o spec em memória. Fórmula **vence o valor do
  gerador** (e Fixed vence tudo); texto que não parseia continua documentação
  — é o que mantém todo cadastro existente byte a byte. Quem executa é
  `_fi_calc_value` (hook `deal=` do `_fi_build_line`) e o espelho do preview
  é `FiTer.calc` (com `FiTer.prime` carregando ANBIMA e os mappings do
  LOOKUP); `check_fi_calc.py` compara as duas cópias. O BIZDIFF é
  zero-padded pela LARGURA do format (9(01) → `3`, 9(02) → `03`). E a
  **Cotação para o Vencimento (campo 15 do TER) EFETIVA** (> 0 — Fixed da
  variante ou fórmula) **desloca as datas das linhas de verificação (tipo 2)
  N dias úteis para frente**, no calendário do deal: no gerador do NDF
  Commodities, no Vanilla (o único das três páginas genéricas que emite tipo 2,
  e emite nos DOIS caminhos — download e Send Conecta, senão o arquivo baixado
  para conferência difere do que vai para a B3) e nos previews das duas
  páginas — hoje o campo nasce em branco, então nada muda sem cadastro.
- **Notificação nova exige o rótulo `page` nos TRÊS mapas de destino** —
  `_NOTIF_PAGE_URL` (routes.py), `PAGE_URL` do `partials/topbar.html` e do
  `static/js/sw-push.js`. Sem a entrada o aviso aparece normal e o clique não
  vai a lugar nenhum (o item nasce `<div>` em vez de `<a>`, sem erro no
  console) — foi o TED Release, e havia NOVE páginas assim. Depois de mexer em
  `_create_notification` ou nos mapas, rode `check_notif_page_url.py`: o
  check 7 varre o routes.py por AST e recusa rótulo literal fora do mapa
  (HANDOFF §246).
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
- **Fora do Windows, `OTC_SHARED_DRIVE_ROOT` é obrigatória.** Todo destino no
  share pende dela (`Config.SHARED_DRIVE_ROOT`, o padrão é `I:\`), e o app
  **recusa subir** com um valor relativo — que é o que o `I:\` é em qualquer
  sistema que não seja Windows. Sem isso o `os.makedirs` do dia a dia criava a
  árvore inteira dentro do diretório de trabalho: as pastas
  `I:\Confirmation\...` na raiz do repositório vieram daí, e é por isso que a
  falha agora é na subida e não em silêncio. Na instância do time a variável
  não é necessária — `os.path.join('I:\\', 'Confirmation', …)` devolve o mesmo
  literal que estava fixo antes, byte a byte.

  **E nenhum módulo escreve a raiz à mão.** O `Config.SHARED_DRIVE_ROOT` só vale
  para quem pergunta a ele: um `r"I:\Confirmation\..."` no fonte mantém AQUELE
  caminho na letra mapeada depois de a instância do JPM passar a falar com o
  UNC — e a falha aparece como *"o arquivo do dia não chegou"*, não como erro de
  configuração, porque quem lê o arquivo simplesmente não o encontra. Era o caso
  das três recons (`recon_fxo`, `recon_comitente` e `recon_payrec`: a raiz das
  posições CETIP, as duas pastas do Comitente e a de entrada do Pay/Rec) e dos
  cinco scripts que espelham um destino do app. Na dev nada muda — o default
  do config **é** o `I:\`, e o `os.path.join` devolve o literal de antes. O
  `check_config_names.py` guarda a regra: varre por AST os literais dos módulos
  versionados de `apps/` e recusa qualquer coisa que comece por letra de unidade
  ou `\\servidor` (comentário e docstring ficam de fora por construção, então o
  caminho citado em prosa continua permitido).
- **SMTP** usa `mailhost.jpmchase.net` (relay interno, porta 25, sem auth) —
  fora da rede JPM o envio falha silenciosamente.
- **API `getTrades` da Athena** (`apps/pages/athena_api.py`): importa New Deals
  de NDF/FXO (botão manual + schedulers no app, NDF a cada 20 min, FXO de hora
  em hora, **os dois só entre 08:00 e 20:00 BRT** — ver §7). Precisa da rede JPM — fora dela o scheduler falha em silêncio
  (erros repetidos rebaixados para `debug`). `build_session()` marca
  `trust_env=False` **de propósito**: herdar o proxy corporativo foi o que
  causou o `WinError 10061` na máquina Windows do time. O SSO Kerberos no
  Windows precisa de `requests-negotiate-sspi`, que está **comentado** no
  `requirements.txt` (só Windows) — instale na instância do JPM. O endpoint em
  si não é mais constante: vem do mapping `api-links`, com
  `BASE_URL`/`TRADES_ENDPOINT` sobrando como fallback do New Deals.
- **API de internet (BCB e Yahoo, na página Quotes): mesma sessão da Athena, mas
  o proxy volta — e é uma FILA.** A sessão é a mesma (`build_session`, Kerberos),
  só que esses hosts são EXTERNOS: o `trust_env=False` que protege a Athena
  também os deixa sem proxy, e em boa parte da rede JPM a conexão só sai por ele.
  A saída é tentada em ordem — `QUOTES_PROXY` (padrão
  `http://proxy.jpmchase.net:**9443**`) → proxy do sistema (`getproxies()`, as
  Opções de Internet no Windows) → `10443` → conexão direta —, e a primeira que
  responder fica memorizada no processo. O proxy do sistema é **copiado** para a
  sessão, nunca herdado: com `trust_env=True` ele voltaria a valer para a Athena.
  A **10443 é a porta do app de desktop e não atende em toda máquina** (responde
  *connection refused*, o mesmo `WinError 10061` por outro motivo). Erro de rede
  tenta a próxima rota, erro HTTP para na hora — menos 407/502/504, que vêm do
  proxy. Nada disso exige `.env` por máquina; `QUOTES_PROXY=` vazio força o
  direto (HANDOFF §266).
- **A instância do time roda com o reloader desligado**: depois de um
  `git pull` que tocou `routes.py` ou um template, o Flask **tem de ser
  reiniciado** ou o código velho continua servindo. Vários "não está
  funcionando" vieram daí. Edição de mapping pela tela é a exceção — vale no
  request seguinte.
- **O `config.py` é o arquivo que fica para trás.** Ele é o único que se ajusta
  à mão na instância, e `git pull` **não sobrescreve arquivo modificado**: o
  resto da árvore atualiza e ele não, deixando o checkout com dois commits
  misturados. Foi assim que a instância subiu com o `manual_conf.py` novo e o
  `config.py` velho (`AttributeError: … has no attribute 'DATABASE_DIR'`, vinte
  frames dentro de um import). Hoje `create_app` confere
  `_REQUIRED_CONFIG_NAMES` **antes** dos blueprints e recusa subir dizendo o
  nome que falta e o comando (`git checkout -- apps/config.py`) — nunca caindo
  para um default, que faria o app abrir o banco LOCAL com os bancos no share,
  sem erro nenhum. **Chave nova do config que outro módulo leia direto do
  `Config` entra nessa lista** (HANDOFF §308).
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
| `import_cgd_sharepoint.py` | carrega a lista de CGDs do SharePoint (`Sharepoint-CGD.xlsx`) no DuckDB do Onboarding (`--xlsx`, `--sheet`, `--dry-run`, `--schema-only`). REESCREVE a tabela: rodar de novo dá o mesmo resultado |

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

---

## 10. As verticais (`apps/pages/features/`)

O `routes.py` tem **39 mil linhas** porque toda funcionalidade nasceu nele: 1293
funções de topo, 371 rotas, 514 constantes. A saída é levar **uma feature de
cada vez** para `apps/pages/features/<nome>/`, seguindo a skill
[`separation-of-concerns`](.claude/skills/separation-of-concerns/SKILL.md).

```
features/<nome>/
├── entrypoint.py   as rotas: sessão → comando/consulta → JSON. Só código de status.
├── commands.py     escrita (gravar + avisar + e-mail). Sem regra de negócio.
├── queries.py      leitura, sem efeito nenhum.
├── domain.py       as regras. PURAS: sem Flask, sem banco, sem SMTP.
└── infra/          persistence.py · mail.py · mappers.py
```

Extraídas até aqui: **`support`** (450 linhas / 6 rotas), **`onboarding`**
(154 / 7), **`reconciliation_fxo`** (101 / 4), **`quotes`** (129 / 3),
**`holidays`** (331 / 5), **`bacc`** (490 / 2), **`mt300`** (384 / 2),
**`appver`** (320 / 2), **`mdea`** (491 / 2), **`conf_escalation`** (576 / 2),
**`daily_metric`** (300 / 2), **`weekly_escalation`** (140 / 2),
**`recon_comitente`** (125 / 3), **`recon_payrec`** (160 / 5),
**`recon_cgd`** (75 / 5), **`boxscan`** (350 / 3), **`sigcoll`** (200 / 2),
**`pcx`** (420 / 2), **`forecast`** (180 / 3, só o card — o coletor é
plataforma), **`deals_monitor`** (650 / 3), **`cetip`** (830 / 2), **`intrag`** (1250 / 15,
verbatim + o gancho `_intrag_engine()` para os gravadores chamados pelos saves
do New Deals), **`counterparty_details`** (720 / 18, verbatim — os LEITORES
`_cpd_path/_cpd_load/_cpd_find` e os normalizadores compartilhados ficaram no
routes) e **`electronic_inventory`** (90 / 4, só a casca — os helpers `_ei_*`
são plataforma: Track, TED e os saves de confirmação usam os mesmos).
O `routes.py` saiu de 39.696 para 31.012 linhas.

**O guarda ganhou a seção 9** (`check_soc_layers`): desmonta o bytecode de toda
função das features e cobra que cada `LOAD_GLOBAL` exista no módulo — é o que
pega o nome que a religação por AST deixou escapar, que só viraria `NameError`
quando aquele caminho rodasse (pegou um `traceback` sem import no pcx no
primeiro giro).

**`deals_monitor` e `cetip` foram movidos VERBATIM** (`engine.py` +
`entrypoint.py`): os nomes internos foram preservados — inclusive para os
testes que os trocam — e o que é de plataforma é alcançado por `_R().<nome>`
(busca atrasada gerada por AST). A separação interna em domain/queries/commands
é trabalho futuro; a fronteira com o `routes.py`, e o guarda que a prende, já
valem. A ferramenta que faz isso é o `extract_verbatim.py` (scratchpad da
sessão): copia os corpos por AST e religa todo `Name(Load)` sem dono.

**O `bacc` foi o primeiro com SCHEDULER, e o registro dele NÃO veio junto.** O
laço vive em `commands.scheduler_loop`, mas o `_schedule_on_start('bacc-ea', …)`
fica no bloco de wiring do `routes.py`, ao lado do import do entrypoint:
chamá-lo do corpo do módulo da feature exigiria importar o `routes` ali — o
ciclo que a regra abaixo proíbe. O gancho é de plataforma; a feature só expõe o
`start_scheduler`. O mesmo desenho vale para `mt300`, `mdea` e
`conf_escalation`; o `appver` não tem scheduler (só o botão do card). E os
laços todos respeitam **`OTC_DISABLE_SCHEDULERS=1`** (`_start_schedulers`): é o
kill-switch dos testes que sobem o app várias vezes — um catch-up de
16h/17h/19h30 num processo de TESTE tentaria reivindicar o slot REAL do dia.

**O `mdea` tem a única entrada de fora**: o pull do NDF grava os pares
(vanilla ↔ FWD Start) via `_mdea.record_rebooks(...)` — import atrasado dentro
da função, porque os entrypoints só são importados no fim do `routes.py`. E o
`_otc_app_url` NÃO foi com o `conf_escalation`: endereço absoluto para botão de
e-mail é plataforma (§7), e ficou no `routes.py` para o próximo e-mail com botão
não importar a vertical da cobrança.

**O `holidays` foi o primeiro com fronteira a decidir.** Ele tinha três
referências de entrada, e as três eram para o `_anbima_holidays` — que não é o
calendário DAQUELA tela e sim o de dias úteis do app inteiro (SLA da esteira,
aging do CGD, schedulers, D-1 das recons). Ele é **horizontal** e ficou no
`routes.py` esperando o `platform/`; vir junto obrigaria meia dúzia de features
a importar a vertical de Feriados para saber se sexta é dia útil. Entrada não
é sinal de que a feature não sai — é sinal de que há plataforma misturada nela.

Nem toda vertical tem `domain.py`: o do Onboarding é o `apps/pages/cgd_docs.py`,
e ele **fica onde está** porque a Recon de CGD e o /mapping também o consultam —
é horizontal, não vertical. Feature cujo domínio já mora num módulo próprio
delega a ele em vez de criar um arquivo vazio.

### As regras que não dão erro nenhum quando se quebram

- **Módulo de feature nunca importa NOME do `routes` — só o MÓDULO, e dentro da
  função.** Esta é a que causa perda silenciosa. Sessenta e um dos oitenta
  scripts de `scripts/tests/` trocam atributos no `routes` para não encostar em
  dado real (`R.DB_PATH = tmp`, `R._create_notification = espião`,
  `R.OTM_JSON_ROOT = tmp`). Um `from apps.pages.routes import get_db_connection`
  no topo do módulo **congela o valor no import**: o teste troca o atributo, o
  módulo continua com o original, e o teste passa lendo o banco de VERDADE. O
  jeito certo é `from apps.pages import routes` DENTRO da função e `routes.X` no
  ponto de uso — busca atrasada, que de quebra torna o ciclo impossível.
- **Entrypoint que o `routes.py` não importa é rota que não existe.** Em Flask o
  `@blueprint.route` só roda quando o módulo é importado. Sem a linha no bloco
  do fim do `routes.py`, a página responde **404** e a subida não diz nada. O
  bloco fica no FIM de propósito: as features buscam no `routes` o que ainda é
  de plataforma, e importá-las no topo fecharia o ciclo.
- **Guarda que varre `routes.py` por AST para de cobrir o que saiu de lá.** São
  32 scripts com o caminho escrito na mão, e o `check_unlocked_reads` casa por
  **nome de função** — o `_tk_roles_by_sid` virou `roles_by_sid` e saiu da lista
  proibida em silêncio. Ao mover código, atualize o guarda na MESMA mudança.
  Quando o guarda varre o arquivo INTEIRO, a correção é fazê-lo ler o
  `routes.py` **mais** `features/**/*.py` de uma vez — é o que o
  `check_notif_page_url` faz hoje (`_fontes_com_rotas`), e assim ele não precisa
  ser editado a cada extração. O sintoma de não fazer isso nem sempre é
  vermelho: às vezes é uma asserção que simplesmente deixa de existir.
- **O teste da feature é o que autoriza a extração.** O Support Center foi o
  primeiro porque nada no resto do `routes.py` o chamava (zero referências de
  entrada) **e** o `check_tickets.py` já o prendia ponta a ponta por HTTP.
  Extrair sem uma rede dessas é mudar 39 mil linhas no escuro. Feature sem teste
  de caracterização: escreva o teste primeiro, com o código ainda no lugar.

`check_soc_layers.py` prende tudo isso, inclusive subindo o app para conferir as
rotas no `url_map` — import escrito e import que executou são coisas diferentes.

### A ordem das próximas fatias

Ela sai do **acoplamento medido**, não do tamanho. Entrada = quantas funções de
fora chamam o grupo; saída = de quantas ele depende:

| Candidato | linhas | entrada | saída | |
|---|---|---|---|---|
| `support` | 450 | **0** | 15 | ✅ feito |
| `onboarding` (CGD) | 154 | **0** | 3 | ✅ feito |
| `reconciliation-fxo` | 101 | **0** | 4 | ✅ feito |
| `quotes` | 129 | **0** | 4 | ✅ feito |
| `holidays` | 331 | 3 | 11 | ✅ feito |
| `bacc` | 490 | 2 rotas | 17 | ✅ feito |
| `mt300` | 384 | 2 rotas | 16 | ✅ feito |
| `appver` | 320 | 2 rotas | 12 | ✅ feito |
| `mdea` | 491 | 2 rotas + 1 gancho | 18 | ✅ feito |
| `conf_escalation` | 576 | 2 rotas | 19 | ✅ feito |
| `daily_metric` · `weekly_escalation` | ~300+140 | 2+2 rotas | — | ✅ feito |
| `recon_comitente` · `recon_payrec` · `recon_cgd` | ~360 | 3+5+5 rotas | — | ✅ feito |
| `boxscan` | ~350 | 3 rotas + scheduler | — | ✅ feito |
| `sigcoll` · `pcx` · `forecast` | ~800 | 2+2+3 rotas | — | ✅ feito |
| `deals_monitor` · `cetip` (verbatim) | ~1480 | 3+2 rotas | — | ✅ feito |
| `intrag` · `counterparty_details` · `electronic_inventory` | ~2060 | 15+18+4 rotas | — | ✅ feito |
| `file-interpreter` | 307 | **43** | 4 | tarde |
| `mapping` | 1263 | 39 | 35 | tarde |
| `notificações` | 393 | **161** | 9 | é PLATAFORMA, não feature |

As notificações, o e-mail, a sessão/autorização e o acesso a banco são
**horizontais**: o lugar delas é `apps/pages/platform/infra/`, e é para lá que a
ponte atrasada das features vai apontar quando forem extraídas. Enquanto isso
não acontece, a busca em `routes` é andaime declarado — está escrita como tal
nos docstrings de `infra/persistence.py` e `infra/mail.py`.
