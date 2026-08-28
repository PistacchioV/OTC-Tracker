# Handoff: About Page + Correções de Navegação e UI — OTC Tracker

**Data:** 2026-06-11  
**Status:** Em andamento

---

## ⚠️ PRÁTICA OBRIGATÓRIA — Design de páginas/UI

**Toda alteração de página ou UI DEVE seguir, sempre:**
1. A skill **`/emil-design-eng`** — feedback de press (`:active scale(0.97)`), curvas de easing custom (`cubic-bezier(0.23,1,0.32,1)`), durações < 300ms, `prefers-reduced-motion`, animar só `transform`/`opacity`, stagger de entrada, popovers origin-aware, etc.
2. O guia **[`DESIGN-apple.md`](DESIGN-apple.md)** — tokens (Action Blue `#0066cc`, tipografia SF Pro com letter-spacing negativo, tiles claro/escuro, hairlines, raio 18px, sem sombras em chrome), hierarquia e paleta.

Isto vale para qualquer criação/edição de tela (novas páginas, cards, tabelas, modais, botões). Não é opcional.

**Padrões de UI a seguir:**
- **Botão de visibilidade de colunas** (show/hide columns): rótulo **"Columns"** com ícone **`ti-columns`** (padrão em `index-b3-results.html`, `reference-data.html`). NÃO usar "Show/Hide".
- **LINHA DE FILTRO POR COLUNA — PADRÃO (igual New Deals):** tabelas de dados devem ter uma 2ª linha no
  `<thead>` com um `<input>` de busca por coluna. Markup: inputs `form-control form-control-sm` (arredondados
  sutis, `bg-tertiary`/`bg-light-subtle`), placeholder = nome da coluna; **`orderCellsTop: true`** (sort na
  linha de título, não no filtro) + `autoWidth: true` p/ alinhar com `scrollX`; wire `keyup/change` →
  `dt.column(col).search(val).draw()`. **Emil:** foco com anel Action Blue (`box-shadow 0 0 0 3px rgba(0,102,204,.15)`),
  transição `150ms cubic-bezier(0.23,1,0.32,1)` só em `border-color`/`box-shadow`/`background`, hover atrás de
  `@media (hover:hover)`, classe `sc-has-val` (tint azul quando o filtro tem valor), guard `prefers-reduced-motion`.
  Referência: `new_deals-ndf-commodities.html` (`#column-search-inputs`), `live-position-swap-characteristics.html`.
- **BLOCO DE LARGURAS POR COLUNA:** incluir no `<style>` da página um bloco "Colunas específicas com larguras
  adequadas — um bloco por coluna" (`#table th/td:nth-child(N) { min-width; width }`, um comentário com o nome
  da coluna) para ajuste fino de largura quando necessário. Padrão em `new_deals-*` e `live-position-swap-characteristics`.
- **BOTÕES DE ACTION — PADRÃO OBRIGATÓRIO (formato):** os botões da coluna Actions são **quadrados
  arredondados** (não círculos), cores semânticas (`btn-info` azul editar · `btn-success` verde aprovar/
  confirmar · `btn-danger` vermelho deletar · `btn-primary` enviar). Um bloco CSS **global** em
  `apps/templates/partials/head-css.html` força `30×30px`, `border-radius:7px !important` (vence o
  `rounded-circle` do Bootstrap) e centraliza o ícone, mirando as classes funcionais existentes
  (`btn-row-*`, `acc-act-*`, `ops-row-del`, `ar-*`, `btn-rd-*`). **É só o formato** — cada página mantém
  os seus próprios botões/handlers/cores. Ao criar uma página nova, use essas classes funcionais (ou
  `btn btn-info/success/danger btn-sm` + uma dessas classes) para herdar o formato automaticamente.
- **ADD ROW — PADRÃO OBRIGATÓRIO (modal GLASS):** sempre que uma página tiver ação **Add row**, ela deve
  abrir um **modal com um campo por coluna** (padrão New Deals), NÃO adicionar uma linha inline em branco.
  O modal usa **glassmorphism/liquid glass** e botões de rodapé **só-ícone** (sem texto):
  - `modal-content` **DEVE** ter a classe **`liquid-glass`** (CSS global em `scss/components/_modal.scss` →
    `app.css`; blur/opacidade já prontos, funciona em light/dark).
  - `modal-dialog`: `modal-lg modal-dialog-centered modal-dialog-scrollable`; header `py-2` com título
    `fs-6` + `<i class="ti ti-plus">`.
  - **Rodapé (`modal-footer py-2`)**: apenas ícones — **Cancel** = `btn btn-sm btn-danger` com
    `ti ti-x` (vermelho, `data-bs-dismiss="modal"`); **Save** = `btn btn-sm btn-success` com
    `ti ti-device-floppy` (verde). SEM texto nos botões.
  - Referências vivas: `new_deals-ndf-commodities.html` (`#addRowModal`, origem do padrão),
    `otm-settlements.html` (`#otmAddModal` — serve Add **e** Edit, título alterna via `#otmModalTitle`),
    `other-products-summary.html` / `ndf-summary.html` (`#opsAddModal`).
- **MAKER/CHECKER + PERSISTÊNCIA (padrão Accrual/Intrag):** páginas com CRUD por linha (Edit/Delete/Confirm)
  persistem TODA alteração/inclusão no JSON do dia. Cada registro carrega meta `status/maker/checker/id`
  (no OTM: chaves `_ot_status`/`_ot_maker`/`_ot_checker`/`_ot_id`; `_otm_collect` anexa `[status,maker,checker,id]`
  no fim de cada row). Lifecycle: importado/inserido = **OK**; **Edit** → **Pending** (maker = usuário, checker
  limpo); **Confirm** só por **outro** usuário (guard `maker == sid` → 403 `same_user`) → volta a **OK**.
  Endpoints `/api/otm-settlements/row/{add,edit,delete,confirm}`. Ações são delegadas em jQuery
  (`.off().on(... , '.btn-row-*')`) para sobreviver a redraws do DataTables; após cada mutação →
  `load()` recarrega + `fetchNotifications()`.
- **⚠️ PADRÃO DE BADGES + BOTÕES DE AÇÃO (SÓLIDO — igual Intrag/New Deals):** NÃO usar o estilo soft
  (`bg-*-subtle text-*` / `btn-soft-*`). O padrão adotado (2026-07-06) é SÓLIDO:
  - **Status badge:** `<span class="badge {cls} bg-gradient">` — New=`bg-info text-white`,
    Pending=`text-bg-warning`, OK/Success=`text-bg-success`, Sent=`badge-sent` (#17a2b8).
  - **Botões de ação:** `btn btn-{cor} btn-sm rounded-circle btn-row-{ação}` — Edit=`btn-info`,
    Confirm=`btn-success`, Delete=`btn-danger`, Send=`btn-primary` (`ti-brand-telegram`). Dimensionar
    com CSS scoped no `<style>` da página: `#<tabela> td .btn-sm.rounded-circle { width:28px;height:28px;
    flex:0 0 28px;padding:0;font-size:13px;display:inline-flex;align-items:center;justify-content:center;
    border-radius:50%; }`. Aplicado em operations-b3, otm-settlements, ndf-cockpit (paridade com
    intrag-option/ndf). Ref viva: `intrag-option.html` (`_optActionsCell`, `statusBadge`).
  - **Centralização do badge de status:** centralizar na **COLUNA**, via `columnDefs`
    (`{ targets: [<STATUS_COL_INDEX>], className: 'text-center' }`), **não** em cada ponto que escreve a
    célula. A célula de Status é reescrita por vários caminhos (rowMaker, mapping B3, aprovação na coluna
    Actions, edição em massa) e alinhar em cada um deles volta a desencontrar assim que alguém mexer num.
    `columnDefs` também é o que sobrevive a coluna escondida — o DataTables tira a coluna oculta do DOM e
    índices de CSS `nth-child` andam. Ver §153.
- **DROPDOWN EXPORT — PADRÃO OBRIGATÓRIO (⚠️ evita translúcido):** o dropdown do DataTables Buttons `extend:'collection'` (Copy/CSV/Excel/PDF) nasce **semi-transparente** (opções quase invisíveis). SEMPRE incluir o bloco CSS de `.dt-button-collection` com fundo sólido (`#fff` / dark `#2b2f3a`), sombra, `opacity:1` e texto opaco — **NÃO escopar** sob o `#id` da página (o DataTables anexa o `.dt-button-collection` ao `<body>`, então uma regra escopada não pega). Referência viva: `accrual-swap.html` (linhas ~170-208), `live-position-swap-characteristics.html`. Também garantir `buttons.print.min.js` carregado quando houver Print (senão os Buttons falham em silêncio).
- **Todo botão** deve ter feedback: `:active` press (`scale(0.97)`, `.9` em ícone-circular) + hover (lift `translateY(-1px)` + sombra) atrás de `@media (hover:hover)`, com guard `prefers-reduced-motion`.
- **DATE PICKER — PADRÃO OBRIGATÓRIO (⚠️ evita erro recorrente):** usar **jQuery `daterangepicker`** com `singleDatePicker`, EXATAMENTE como em `mtm-swap.html`, `accrual-swap.html` e `control-panel.html`. **NUNCA** usar `<input type="date">` nativo (herda o locale do SO → mostra `mm/dd/yyyy` no ambiente Windows do JP) e **não** confiar num flatpickr "global" do bundle (falhou de forma intermitente em `other-products-summary`).
  - **Assets na própria página** (não assumir que estão no bundle): no `extra_css` → `plugins/daterangepicker/daterangepicker.css`; no `extra_javascript` → `plugins/daterangepicker/moment.min.js` + `plugins/daterangepicker/daterangepicker.js`.
  - **⚠️ jQuery PRÓPRIO ANTES dos plugins:** o `vendors.min.js` global **NÃO** expõe um `jQuery` utilizável (dá `jQuery is not defined` / `$.fn undefined` → daterangepicker não registra e o calendário não abre; DataTables também quebra). SEMPRE carregar `<script src="…/plugins/jquery/jquery.min.js">` como **primeiro** script do `extra_javascript` (antes de datatables/daterangepicker/chartjs). Padrão em `accrual-swap.html` / `mtm-swap.html`. Bug real corrigido em `other-products-summary` e no dashboard/Live Position (sessão 2026-07-04).
  - **Init resiliente:** se o init do picker roda depois de um `await` (ex.: `await loadTranslations()` no dashboard) e o plugin ainda não estiver pronto, **re-tentar** (`setTimeout` ~50ms, até ~2s) em vez de cair no fallback de texto de forma permanente — senão fica intermitente por timing de carregamento.
  - **Markup:** `<input type="text" id="..." readonly autocomplete="off">` (sem `type=date`).
  - **Init:** `$('#id').daterangepicker({ singleDatePicker:true, autoApply:true, showDropdowns:true, locale:{ format:'DD/MM/YYYY' }, startDate: moment() /*, maxDate: moment() só se quiser bloquear datas futuras */ }, function(start){ /* start.format('YYYY-MM-DD') → backend */ });`
  - **Ler a data escolhida:** `$('#id').data('daterangepicker').startDate.format('YYYY-MM-DD')`.
  - Referência viva: `other-products-summary.html` (sessão 2026-07-04).

---

## 1. Objetivo

Adicionar uma página "About" interna à aplicação OTC Tracker (dentro do layout com sidebar/topbar), modelada visualmente na `landing.html` existente mas sem seções de preço/compra. A página deve descrever o que a ferramenta faz, mostrar o fluxo operacional, e suportar o sistema de tradução (EN/BR/ES) via `data-lang`. Paralelamente, foram corrigidos bugs de navegação (logo redirecionando para sign-in) e UI (ícone de notificação fora de centro).

---

## 2. Contexto essencial

### Stack
- **Backend:** Python 3.12 + Flask, blueprint único (`pages_blueprint` em `apps/pages/routes.py`)
- **DB:** DuckDB (`Users_OTCTracker.db`) para users/2FA; SQLite (`apps/db.sqlite3`) inicializado mas não usado
- **Frontend:** Bootstrap 5, Tabler Icons (`ti ti-*`), Lucide Icons (`data-lucide`), SCSS compilado via Gulp
- **Auth:** SID-based (JPMorgan interno). Sessão gerenciada manualmente. Chave: `session['authenticated']`
- **Templates:** herança `layouts/vertical.html` → `{% block page_content %}` (NÃO `{% block content %}`)
- **Traduções:** JSON em `apps/static/data/translations/{en,br,es}.json`, ativadas por `data-lang="chave"` no HTML

### Restrições importantes
- `awmpy` é biblioteca interna JPMorgan — não disponível fora da rede. Login/register falham fora do ambiente JPM
- `DB_PATH` do DuckDB já usa caminho relativo via `os.path.dirname(__file__)` — OK ✅
- `RETURN_PATH` e `CONECTA_NEW_PATH` (pastas B3 Conecta) movidos para variáveis de ambiente no `.env` ✅
- SMTP relay interno (`mailhost.jpmchase.net`) — e-mails de 2FA só funcionam dentro da rede JPM
- `SECRET_KEY` estava comentada no `.env`, gerando chave aleatória a cada restart (invalidava sessões)

### Decisões tomadas
- `about.html` usa `layouts/vertical.html` (in-app), não `base.html` (standalone)
- Gradiente do hero usa cores hardcoded (`#0d6efd` → `#34369b`) com `!important` porque `var(--bs-primary)` é sobrescrita pelo tema e aparecia branca/transparente
- Logo no hero usa `<img>` simples (sem classes `logo-light`/`logo-dark`), porque essas classes são toggles do sidebar e deixavam os dois logos visíveis simultaneamente no hero
- Ícone do Step 2 ("Revisão") usa `ti ti-clipboard-check` — `ti-table-check` não existe nessa versão do Tabler Icons instalada
- SECRET_KEY definida como valor fixo no `.env` para persistência de sessão entre restarts

---

## 3. O que já foi feito

### Criado
1. **`apps/templates/pages/about.html`** — página About completa com:
   - Hero com gradiente azul, logo (`logo.png` 90px), badge JPMorganChase, título, descrição, 2 botões CTA
   - 4 stat cards (Contract Types, Integration, Traceability, Access)
   - 6 capability cards (NDF Comm, Opt Comm, Index B3, Submit B3, Mapping B3, User Mgmt)
   - Fluxo "How it Works" em 4 steps com ícones e setas
   - 2 info cards (Notifications, Auth)
   - Tech stack grid (Python/Flask, DuckDB, Bootstrap, DataTables, Dropzone, Gunicorn)
   - CTA card azul com 3 botões
   - Todos os textos com `data-lang` para suporte a tradução

### Modificado
2. **`apps/pages/routes.py`**
   - Adicionado route `/about` (auth-protected)
   - Route `/` alterado: se autenticado → redireciona para `/dashboard`; se não → sign-in (era sempre sign-in)

3. **`apps/templates/partials/sidenav.html`**
   - Adicionado link "About" no menu (com ícone `data-lucide="info"`)
   - Logo da sidebar: `href="/"` → `href="/dashboard"`

4. **`apps/templates/partials/topbar.html`**
   - Logo da topbar: `href="/"` → `href="/dashboard"` (ambos `logo-light` e `logo-dark`)
   - Adicionado `<style>` para centralizar ícone SVG Lucide dentro das notification badges (problema: Lucide substitui `<i>` por `<svg width="24" height="24">` ignorando o `style` inline; solução: CSS `.notification-badge svg { width:10px; height:10px; }`)

5. **`apps/static/data/translations/en.json`** — 38 chaves `about-*` adicionadas (inglês)

6. **`apps/static/data/translations/br.json`** — 38 chaves `about-*` adicionadas (português)

7. **`apps/static/data/translations/es.json`** — 38 chaves `about-*` adicionadas (espanhol)

8. **`.env`**
   - `SECRET_KEY` descomentada e definida como valor fixo (`otctracker-jpm`)

### Descartado / Problemas resolvidos
- **Tentativa inicial com `logo-light`/`logo-dark` no hero** → descartada porque essas classes Bootstrap são toggles do sidebar baseados em `data-menu-color` e não funcionam em outros contextos (ambos os logos ficavam visíveis)
- **`var(--bs-primary)` no gradiente** → descartado; o tema sobrescreve essa variável para uma cor clara tornando o hero branco. Substituído por `#0d6efd` hardcoded com `!important`
- **`ti ti-table-check` no Step 2** → ícone não existe nessa versão; substituído por `ti ti-clipboard-check`
- **`data-lang` removidos pelo usuário** → o usuário editou o arquivo manualmente e removeu os atributos; foram restaurados numa edição subsequente

---

## 4. Estado atual

### Funciona
- Página `/about` carrega dentro do layout com sidebar/topbar ✅
- Link "About" aparece no sidenav ✅
- Gradiente azul do hero aparece corretamente ✅
- Logo único (sem duplicação) no hero ✅
- Todos os `data-lang` presentes → traduções funcionais ✅
- Logo da topbar e sidenav vão para `/dashboard` ✅
- Route `/` inteligente: redireciona autenticados para `/dashboard` ✅
- `SECRET_KEY` fixa → sessão persiste entre restarts ✅
- Ícone das notification badges centralizado ✅

### Não testado em produção
- Traduções (depende do sistema de i18n do `app.js` carregar os JSONs)
- Auth real (depende de `awmpy` — ambiente JPM apenas)
- Notificações em tempo real (depende de dados reais na DB)

### Pendente / em aberto
- Ver seção 5 e 6

---

## 5. Próximos passos

1. **Testar a página `/about`** no browser após restart do servidor Flask — verificar se hero, logo, gradiente e traduções aparecem corretamente
2. **Testar troca de idioma** (EN/BR/ES) na topbar e verificar se os textos `about-*` traduzem corretamente
3. **Verificar o link "About" no sidenav** — garantir que aparece na posição correta e que o item fica highlighted quando a rota é `/about`
4. **Revisar o segmento ativo** — a route passa `segment='about'`; verificar se o CSS do sidenav destaca o item correto (procurar lógica de `active` no sidenav baseada em `segment`)
5. **Verificar topbar.html** — confirmar que a mudança de `href="/dashboard"` está visível e que o logo não abre nova aba
6. **(Opcional) Melhorar o About** — adicionar mais módulos ao capability section conforme a aplicação evolui (ex.: Pending Confirmation, Manual Confirmation, Regulatory)

---

## 6. Perguntas em aberto

- **Segmento ativo no sidenav:** O sidenav usa `segment` para destacar o item ativo? Se sim, o valor `'about'` está correto ou precisa de ajuste no HTML do sidenav (classe `active`)?
- **Logo do hero em dark mode:** `logo.png` tem fundo transparente? Se o usuário usar tema dark, o logo pode ficar invisível. Pode ser necessário usar `logo-white.png` ou aplicar `filter: brightness(0) invert(1)` via CSS quando o tema for escuro
- **SECRET_KEY em produção:** O valor `otctracker-jpm` é adequado para produção? Deve ser substituído por uma string aleatória longa antes do deploy
- **Notificação badge em outros browsers:** O fix CSS com `!important` para o SVG do Lucide foi testado apenas visualmente — confirmar que funciona no Chrome/Firefox/Edge que o time usa
- **Página About acessível sem auth?** Atualmente é auth-protected. Faz sentido ter uma versão pública (para a tela de login)?

---

## 7. Artefatos relevantes

### Arquivos criados/modificados nesta sessão
```
apps/templates/pages/about.html          ← CRIADO (470 linhas)
apps/pages/routes.py                     ← MODIFICADO (route /, /about)
apps/templates/partials/sidenav.html     ← MODIFICADO (link About + logo href)
apps/templates/partials/topbar.html      ← MODIFICADO (logo href + notification CSS)
apps/static/data/translations/en.json   ← MODIFICADO (38 chaves about-*)
apps/static/data/translations/br.json   ← MODIFICADO (38 chaves about-*)
apps/static/data/translations/es.json   ← MODIFICADO (38 chaves about-*)
.env                                     ← MODIFICADO (SECRET_KEY definida)
```

### Chaves de tradução adicionadas (prefixo `about-`)
```
about-hero-desc
about-stat-contracts, about-stat-contracts-sub
about-stat-integration, about-stat-integration-sub
about-stat-traceability, about-stat-traceability-sub
about-stat-access, about-stat-access-sub
about-features-label, about-features-title
about-feat-ndf-desc, about-feat-opt-desc, about-feat-index-desc
about-feat-submit-title, about-feat-submit-desc
about-feat-mapping-title, about-feat-mapping-desc
about-feat-users-title, about-feat-users-desc
about-access
about-flow-label, about-flow-title
about-step1-title, about-step1-desc
about-step2-title, about-step2-desc
about-step3-title, about-step3-desc
about-step4-title, about-step4-desc
about-notif-title, about-notif-desc
about-auth-title, about-auth-desc
about-tech-label, about-tech-title
about-cta-title, about-cta-desc
```

### Snippet: route /about em routes.py
```python
@blueprint.route('/about')
def about():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/about.html', segment='about')
```

### Snippet: route / corrigido
```python
@blueprint.route('/')
def index():
    if session.get('authenticated'):
        return redirect(url_for('pages_blueprint.dashboard'))
    return render_template('pages/auth-2-sign-in.html', segment='auth-2-sign-in')
```

### Snippet: CSS do hero (about.html)
```css
.about-hero {
    background: linear-gradient(135deg, #0d6efd 0%, #34369b 100%) !important;
    border-radius: 1rem;
    padding: 4rem 2rem;
    color: #fff !important;
}
.about-hero h1, .about-hero h2, .about-hero h3,
.about-hero h4, .about-hero h5, .about-hero span,
.about-hero p { color: #fff !important; }
.about-hero .lead { color: rgba(255,255,255,.85) !important; }
```

### Snippet: fix notification badge (topbar.html)
```css
.notification-item .notification-badge {
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}
.notification-item .notification-badge svg {
  width: 10px !important;
  height: 10px !important;
  display: block;
  flex-shrink: 0;
}
```

### Snippet: Padrão de formatação para as tabelas nas paginas
<style>
#xxx-table th {
      white-space: nowrap;
      text-overflow: ellipsis;
      min-width: 120px;
      padding: 8px 12px;
      text-align: center !important;
      vertical-align: middle !important;
      font-size: 0.7rem;
  }
</style>

### Comandos para rodar
```bash
# Ativar venv e rodar
source .venv311/bin/activate
flask run

# Ou com gunicorn
gunicorn --config gunicorn-cfg.py run:app
```

---

## 10. Sessão 2026-06-11 (continuação) — Auth, Sidenav, Pending Confirmation

### O que foi feito

#### Auth — `apps/templates/pages/auth-2-sign-in.html` + `apps/pages/routes.py`
- **Form corrigido:** adicionados `action="/login" method="POST"` e `name="sid"` no input — antes o form submetia GET para `/?` e o SID nunca chegava ao backend
- **Flash messages:** adicionado bloco `{% with get_flashed_messages %}` no template para mostrar erros (SID inválido, conta Pending/Inactive)
- **Bug de aspas curvas (Jinja2):** expressão `{% if category == 'error' %}` tinha aspas tipográficas `'` geradas pelo editor, causando `unexpected char` — corrigido para aspas ASCII

#### "Keep me signed in" — implementação completa
- **Checkbox:** adicionado `name="remember_me"`, removido `checked=""` padrão (antes sempre enviava como marcado)
- **`login()`:** lê `remember_me = request.form.get('remember_me') == 'on'` e passa para `_handle_existing_user`
- **`_handle_existing_user()`:** aceita `remember_me`, repassa para `_set_session()` (IP match) ou armazena em `session['pending_remember_me']` (fluxo 2FA)
- **`_set_session()`:** define `session.permanent = remember_me`, armazena `session['session_expires_at']` — 30 dias (marcado) ou 8 horas (desmarcado)
- **`verify_2fa()`:** pop de `pending_remember_me` antes de chamar `_set_session`
- **`before_request` no blueprint:** valida server-side o `session_expires_at` em todo request, limpando a sessão se expirada — independe de browser restaurar cookies
- **`apps/config.py`:** `from datetime import timedelta` + `PERMANENT_SESSION_LIFETIME = timedelta(days=30)` em Production e Debug

#### Sidenav — `apps/templates/partials/sidenav.html`
- Título da seção: `Navigation` → `Main`
- Ícone do item Dashboards: `circle-gauge` → `layout-grid`
- Badge `02` removido; substituído por `menu-arrow`
- Item **About** movido para logo abaixo de Dashboards (dentro de Main), removido do lugar antigo (após Users)

#### Pending Confirmation — `apps/templates/pages/pending-confirmation.html`
- **Widgets:** altura uniforme (`align-items-stretch`), `line-clamp: 2` nos títulos, avatares reduzidos para 40px
- **Toolbar:** padrão idêntico ao NDF Commodities — card-header com `Show [n] entries per page` acima, DataTables DOM com botões alinhados à esquerda abaixo (`btn-toolbar d-flex`)
- Classe `btn-toolbar-all` aplicada nos botões Add Row e Export

### Padrões identificados nesta sessão

- **Padrão de toolbar DataTables:** card-header com select `data-table-set-rows-per-page` + DataTables DOM com `btn-toolbar d-flex flex-wrap align-items-center`. Ver NDF Commodities como referência canônica.
- **Aspas Jinja2:** nunca usar aspas tipográficas curvas (`'`) dentro de expressões `{{ }}` ou `{% %}`; causam `unexpected char` no lexer.
- **"Keep me signed in" server-side:** validação por timestamp em `session['session_expires_at']` via `@blueprint.before_request` é obrigatória — browsers modernos restauram session cookies e ignoram a ausência de `session.permanent`.

---

## 11. Sessão 2026-06-14 — Holidays Calendar: design, contraste, animações Emil

### O que foi feito

#### Holidays Calendar — nova página
- **`apps/templates/pages/holidays-calendar.html`** criado com layout completo: sidebar de calendários arrastáveis, FullCalendar integrado (Month/Week/Day/List/Year), modal de criação/edição de feriados, SweetAlert2 para popup de detalhes ao clicar num evento
- **`apps/static/js/pages/apps-holidays-calendar.js`** criado: classe `CalendarSchedule`, carregamento assíncrono dos JSONs de feriados, lógica de drag-and-drop, persistência via `/api/holidays/save`
- **`apps/static/data/anbima.json`** e **`apps/static/data/sofr.json`** adicionados

#### Fix 1 — Textos das views não apareciam (list view)
- O CSS cobria apenas as 4 cores customizadas (purple/teal/indigo/pink) na list view do FullCalendar
- As 7 cores semânticas Bootstrap (primary/secondary/success/danger/info/warning/dark) não tinham regra de override — o `<a>` da list view usava cor padrão de link, sobrescrevendo a herança do `<tr>`
- Adicionadas regras `.fc-list-event.bg-*-subtle` para todas as variantes Bootstrap

#### Fix 2 — Contraste (ICEAGS e IPE invisíveis)
- `text-info` do Bootstrap = `#0dcaf0` → contraste 1.7:1 com fundo branco — **invisível**
- `text-warning` = `#ffc107` → contraste ~2:1 — muito fraco
- Substituídos por versões escuras com contraste adequado:
  - ICEAGS (info): `#0dcaf0` → **`#0284c7`** (sky-600, contraste ~4.5:1)
  - IPE (warning): `#f59e0b` → **`#b45309`** (amber-700, contraste ~4.8:1)
- Fix aplicado em `.fc-daygrid-event` e `.fc-list-event` para todas as views

#### Fix 3 — Botões de view sem texto visível
- CSS sobrescrevia `background-color` dos botões mas não forçava `color: #fff`
- Bootstrap theme calculava cor de texto por contraste e escolhia cor escura sobre fundo azul
- Adicionado `color: #fff !important` em todos os estados (normal, hover, active)
- Adicionado `buttonIcons: false` no JS para garantir labels de texto em todos os botões

#### Design Apple — event badges pill
- `.fc-daygrid-event`: `border-radius: 999px`, `border-width: 0`, `font-weight: 600`, `font-size: 0.70rem`
- `.fc-daygrid-more-link`: estilizado com `color: #0066cc`

#### Animações Emil (mesmo padrão da sidebar)
- `.fc-daygrid-event` recebeu a mesma curva e tempo dos pills da sidebar (`transition: transform 140ms cubic-bezier(0.23, 1, 0.32, 1), box-shadow 140ms ...`)
- `:active`: `scale(0.96)` (press feedback)
- `:hover` (gated em `@media (hover: hover)`): `translateY(-2px)` + `box-shadow: 0 3px 10px rgba(0,0,0,0.12)` — lift vertical em vez de translateX horizontal (que ficaria estranho em badges dentro de células)

#### Script commit-push seguro
- **`scripts/commit-push.sh`** criado: remove automaticamente o bloco DEV BYPASS do `routes.py` antes do commit, faz push, e restaura a versão dev local após
- **Workflow obrigatório**: sempre que `routes.py` estiver entre os arquivos a commitar, usar este fluxo (ou fazê-lo manualmente)

### Padrões identificados nesta sessão

- **FullCalendar list view + Bootstrap classes:** `text-*` no `<tr>` NÃO cascateia para `<a>` interno porque o browser default link style tem prioridade. É obrigatório ter regra explícita `.fc-list-event.bg-*-subtle a { color: ... !important }` para cada variante de cor.
- **Contraste mínimo em badges:** Bootstrap `text-info` (`#0dcaf0`) e `text-warning` (`#ffc107`) têm contraste < 3:1 sobre fundo branco/claro — nunca usar diretamente em texto sobre fundos claros sem override.
- **FC toolbar buttons:** ao sobrescrever `background-color` de `.fc-button-primary`, sempre incluir `color: #fff !important` — o tema Bootstrap recalcula a cor do texto e pode escolher escuro.
- **Emil em calendário:** `translateX` não faz sentido em badges horizontais; usar `translateY(-2px)` para o lift effect.
- **Commit+push com routes.py:** bloco DEV BYPASS nunca vai para o repositório. Usar `scripts/commit-push.sh` ou o processo manual de backup → strip → commit → push → restore.

### Arquivos criados/modificados nesta sessão
```
apps/templates/pages/holidays-calendar.html   ← CRIADO
apps/static/js/pages/apps-holidays-calendar.js ← CRIADO
apps/static/data/anbima.json                  ← CRIADO
apps/static/data/sofr.json                    ← CRIADO
scripts/commit-push.sh                        ← CRIADO
apps/pages/routes.py                          ← MODIFICADO (outras mudanças da branch)
apps/templates/pages/about.html               ← MODIFICADO
apps/templates/pages/new_deals-ndf-commodities.html ← MODIFICADO
apps/templates/pages/new_deals-opt-commodities.html ← MODIFICADO
apps/templates/partials/footer.html           ← MODIFICADO
apps/static/images/logo-black.png             ← MODIFICADO
apps/static/images/logo-sm-black.png          ← ADICIONADO
apps/templates/pages/NDF Comm - Strike USD.html ← ADICIONADO
```

---

## 12. Sessão 2026-06-14 (continuação) — Recon Comitente: score colors, notificações

### O que foi feito

#### Fix: cores das colunas de score não aparecendo (`reconciliation-comitente.html`)
- **Causa raiz:** Bootstrap 5 `table-striped` usa `box-shadow: inset 0 0 0 9999px var(--bs-table-accent-bg)` que renderiza sobre o `background-color`. Em linhas pares, o `dataTables.bootstrap5.min.css` tem regra com `!important` que sobrescreve `backgroundColor` inline.
- **Fix 1 (CSS):** adicionado `box-shadow: none !important` em `#recon-table td.score-cell` — desativa o overlay do striped nessas células.
- **Fix 2 (JS):** `scoreCell()` alterada para usar `td.style.setProperty('background-color', c, 'important')` — inline `!important` vence qualquer regra de stylesheet, incluindo as do plugin DataTables Bootstrap 5.
- Resultado: todas as colunas Score (Name, Addr, Phone, Email, Fins, Start, CNAE, Avg) mostram gradiente verde/vermelho em todas as linhas.

#### Notificação ao gerar reconciliação (`routes.py`)
- Adicionado `_create_notification()` no endpoint `/reconciliation-comitente/run` após processamento bem-sucedido (total > 0).
- **action:** `Recon Generated` | **page:** `Recon Comitente` | **detail:** `N records — OK:X Check:Y Amend:Z (YYYY-MM-DD)`

#### Atualização de notificação imediata sem refresh de página (`topbar.html` + `reconciliation-comitente.html`)
- `fetchNotifications` exposta como `window.fetchNotifications` no topbar para ser acessível de qualquer página.
- `window.fetchNotifications()` chamada após sucesso de `runAuto()` e `processFiles()` — notificação aparece imediatamente no dropdown.
- `ACTION_META` atualizado: `'Recon Generated': { icon: 'shield-check', color: 'bg-success' }`
- `PAGE_URL` atualizado: `'Recon Comitente': '/reconciliation-comitente'`

#### Fix email Outlook: fundo branco no logo/header (`email-template-recon-comitente.html`)
- **Causa:** CSS `background: linear-gradient(...)` shorthand reseta `background-color`. Outlook não suporta gradientes → fundo branco.
- **Fix:** `bgcolor="#1a2c5e"` no atributo HTML do `<td>` + `background:#1a2c5e` como primeiro valor no `style` (antes do gradiente).

### Padrões identificados nesta sessão

- **Bootstrap 5 `table-striped` box-shadow:** nunca confiar em `background-color` inline para sobrescrever cells com `table-striped`. Usar dupla abordagem: `box-shadow: none !important` no CSS da célula + `td.style.setProperty('background-color', c, 'important')` no JS.
- **`window.fetchNotifications` pattern:** expor a função de refresh de notificações globalmente permite que qualquer página a chame após uma ação que gera notificação — sem polling extra ou mudança de página.
- **Outlook email `bgcolor`:** sempre usar atributo HTML `bgcolor` em `<td>` como fallback para Outlook. CSS `background` shorthand reseta `background-color` — usar `background-color` separado OU setar `background:#color;background:linear-gradient(...)` em sequência (mas `bgcolor` no HTML é mais seguro).

### Arquivos modificados nesta sessão
```
apps/templates/pages/reconciliation-comitente.html  ← score colors fix (CSS + JS)
apps/templates/pages/email-template-recon-comitente.html ← bgcolor Outlook fix
apps/templates/partials/topbar.html                ← window.fetchNotifications, ACTION_META, PAGE_URL
apps/pages/routes.py                               ← _create_notification em /reconciliation-comitente/run
```

### Commits desta sessão
- `f6615d9` — fix email header bgcolor Outlook
- `4452448` — fix(recon-comitente): score cell colors + notification on recon generated
- `db2a580` — feat(notifications): instant refresh after recon + Recon Comitente action meta

---

## 8. Instruções para a próxima sessão

**Tom e abordagem:**
- O projeto está sendo desenvolvido para uma área de Back Office de Derivativos OTC do Banco JP Morgan que cuida dos produtos Swap, NDF, Opções e COE, sem CCP (garantia). Os ativos envolvidos podem ser, Rates, Paridade de Moedas, Commodities, Equities em geral como índices, Ações.
- O projeto permitirá acesso de diversas areas que tenham correlação com OTC, como áreas de Middle Office, Front Office, HUB, mesas de produtos e bankers. Por isso, ela terá segregação de acessos. Sempre crie e/ou altere códigos com isso mente deixando a estrutura preparada para esse propósito. Caso ainda não tenha a segregação definida, deixe um placeholder para ser impletmentado posteriormente.
- O caminho raiz do projeto é '/Users/giullianoaccarinideluccia/Desktop/OTC Tracker'
- O usuário é desenvolvedor familiarizado com o projeto — respostas diretas e técnicas, sem explicar o óbvio
- Prefere edições cirúrgicas em arquivos específicos, não rewrites completos
- Edita arquivos manualmente no IDE — sempre verificar o estado atual do arquivo antes de editar (não assumir que está como a sessão anterior deixou)
- Português nas respostas
- Todos os textos/headers/avisos/notificações devem conter data-lang para traduçao nos json es, en e br ('apps/static/data/translations')
- Sempre informar no final de cada ediçao os arquivos/códigos que foram editados
- Evitar preâmbulo e resumos desnecessários, explique diretamente e resumido o que foi alterado e o porque, sem ser prolixo.
- Mantenha sempre o layout do projeto, buscando exemplos de outras páginas já efetuadas para manter o padrão como um todo.
- Alertas ou questionamentos com yes/no/cancel, sempre utilizar sweet alert, modelos em 'apps/templates/pages/misc-sweet-alerts.html'
- Sempre verificar questão de contraste em questão de vizualização, para cores de letras, ícones, fundos e etc, o projeto alem de funcional, tem que ser perfeito visualmente.
- Na parte de Products > New Deals, todos os produtos (Swap, Opção e NDF) seguem um padrão em comum: importar informações pelo dropzone (seja por .msg, .html, .xml, .xlsx), processar as informaçoes como instruido, inserir na tabela, enviar o arquivo e mapear os deals; Approved, Pending, Sent, Success, Error e etc, serão os status padrão para todos. Sempre refletir as alteraçoes no json respectivo do dia, considerando as restrições de maker and checker.
- Sempre atualizar o handoff com novos padrões identificados e ao final de cada sessão atualizar com novos resumos. Nunca deletar ou sobreescrever algo que ja esteja no arquivo sem pedir permissão.

**Armadilhas a evitar:**
1. **Não usar `var(--bs-primary)` no hero** — o tema sobrescreve essa variável; sempre usar `#0d6efd` hardcoded com `!important`
2. **Não usar classes `logo-light`/`logo-dark` fora do sidenav/topbar** — são toggles de visibilidade baseados em `data-menu-color`; fora do contexto do layout, ambas ficam visíveis
3. **Verificar ícones Tabler antes de usar** — nem todos os ícones da documentação existem na versão instalada. Se um ícone não aparecer, substituir por equivalente comum (`ti-clipboard-check`, `ti-check`, `ti-eye`, etc.)
4. **`data-lang` no `<a>` substitui TODO o conteúdo** — se um link tem ícone `<i>` dentro, o `data-lang` vai sobrescrever o ícone junto com o texto. Usar `data-lang` apenas em elementos que contêm só texto, ou criar um `<span>` interno para o texto
5. **O usuário pode editar os arquivos manualmente** — sempre ler o arquivo atual antes de editar; não confiar no estado da sessão anterior
6. **`block page_content`** — páginas in-app sempre usam `{% block page_content %}`, nunca `{% block content %}`
7. **SECRET_KEY** — já está definida no `.env`; não alterar sem avisar o usuário
8. **Bootstrap `text-info` / `text-warning` em fundos claros** — `#0dcaf0` e `#ffc107` têm contraste < 2:1 sobre branco. Nunca usar diretamente como cor de texto visível; substituir por `#0284c7` (info) e `#b45309` (warning)
9. **FullCalendar list view + classes Bootstrap** — `text-*` no `<tr>` não cascateia para `<a>` interno (link style tem prioridade). Sempre adicionar regra explícita `.fc-list-event.bg-*-subtle a { color: ... !important }` para cada cor
10. **FC toolbar buttons com background sobrescrito** — ao mudar `background-color` de `.fc-button-primary`, sempre adicionar `color: #fff !important` — o Bootstrap theme recalcula a cor e pode escolher texto escuro
11. **Commit+push com `routes.py`** — o bloco DEV BYPASS (`/dev-login`) nunca vai para o repositório. Usar `scripts/commit-push.sh` ou: backup → remover bloco → commit+push → restaurar backup
12. **Mensagens de Swal/notificação construídas dinamicamente (contagens, listas, resultados de rotina) NÃO podem vir prontas em texto do backend** — o backend deve retornar apenas dados estruturados (ex.: `processed: [{type,kept,total}]`, `skipped`, `source`) e o **frontend monta o texto com `t('chave','fallback EN')`**, para seguir o idioma da UI. `data-lang` estático não funciona em HTML injetado depois do load; usar o helper `t()` (padrão `_TRANS_CACHE`). O texto padrão/fallback é sempre **inglês**, com as chaves nos 3 JSON (en/br/es). Exemplo real: mensagem do Daily Settlement no Control Panel (`buildDsMessage` em `control-panel.html` + chaves `cp-files-processed-via`, `cp-of`, `cp-lines`, `cp-ignored`, `cp-src-dropzone`, `cp-src-folder`, `cp-nothing`).
13. **O mapa "página da notificação → URL" tem TRÊS cópias** — `_NOTIF_PAGE_URL` (`routes.py`), `PAGE_URL` em `partials/topbar.html` e `PAGE_URL` em `static/js/sw-push.js`. Ao criar um `page` novo de notificação, atualizar as três; faltar numa delas faz o clique cair no dashboard em silêncio (o sino, o toast e o push clicam por caminhos diferentes). Ver §161.
14. **`custom-table.js` não enxerga linhas criadas depois do load** — ele fotografa `this.rows` no construtor e auto-inicializa no `DOMContentLoaded`. Numa tabela populada por `fetch` (ou re-renderizada a cada mutação) ele fica com zero linhas, e o `data-table-delete-row` dele apaga só do DOM, sem passar pelo backend. Em página com dados assíncronos, não incluir o script — fazer busca/filtro/ordenação/paginação na própria página. Ver §161.

---

## 9. Referência de Design — Apple Design Language

> Fonte: `DESIGN-apple.md` (análise de 5 páginas Apple: homepage, environment, store, iPhone 17 Pro buy page, accessories index).  
> Usar como referência de princípios visuais para manter o OTC Tracker com qualidade de UI de primeiro nível.

---

### 9.1 Filosofia central

- **Photography-first / Product-first**: UI recede para o produto falar. Nenhum elemento decorativo compete com o conteúdo principal.
- **Alternância de tiles**: seções alternam canvas claro (branco/parchment) ↔ escuro (near-black). A mudança de cor É o divisor de seção — sem bordas, sem gradientes decorativos.
- **Single accent color**: um único azul interativo para TUDO (`#0066cc`). Nenhuma segunda cor de marca. Toda ação "clique aqui" usa essa cor.
- **Elevação mínima**: o único drop-shadow do sistema (`rgba(0,0,0,0.22) 3px 5px 30px`) é reservado para imagens de produto sobre superfície. Nunca em cards, botões ou texto.

---

### 9.2 Paleta de cores (tokens)

```
/* Brand & Accent */
--apple-primary:          #0066cc;   /* Action Blue — único cor interativa */
--apple-primary-focus:    #0071e3;   /* focus ring */
--apple-primary-on-dark:  #2997ff;   /* links em tiles escuros */

/* Surfaces */
--apple-canvas:           #ffffff;   /* canvas principal */
--apple-parchment:        #f5f5f7;   /* off-white alternado, footer */
--apple-pearl:            #fafafc;   /* botão ghost secundário */
--apple-tile-1:           #272729;   /* tile escuro principal */
--apple-tile-2:           #2a2a2c;   /* tile escuro — micro-step claro */
--apple-tile-3:           #252527;   /* tile escuro — micro-step escuro */
--apple-black:            #000000;   /* nav global, video background */
--apple-chip-translucent: #d2d2d7;   /* chip circular sobre foto (~64% alpha) */

/* Text */
--apple-ink:              #1d1d1f;   /* headlines + body em fundo claro */
--apple-body-on-dark:     #ffffff;   /* texto em tiles escuros */
--apple-body-muted:       #cccccc;   /* copy secundário em tiles escuros */
--apple-ink-muted-80:     #333333;   /* body em surface-pearl */
--apple-ink-muted-48:     #7a7a7a;   /* texto desativado + fine-print */

/* Borders */
--apple-divider-soft:     #f0f0f0;   /* anel sutil em botões secundários */
--apple-hairline:         #e0e0e0;   /* borda 1px em utility cards */
```

---

### 9.3 Tipografia

| Token | Família | Size | Weight | Line-H | Letter-Sp | Uso |
|---|---|---|---|---|---|---|
| `hero-display` | SF Pro Display | 56px | 600 | 1.07 | -0.28px | Hero principal |
| `display-lg` | SF Pro Display | 40px | 600 | 1.10 | 0 | Títulos de tile |
| `display-md` | SF Pro Text | 34px | 600 | 1.47 | -0.374px | Section heads |
| `lead` | SF Pro Display | 28px | 400 | 1.14 | +0.196px | Subcopy de tile |
| `lead-airy` | SF Pro Text | 24px | 300 | 1.50 | 0 | Lead arejado (raro) |
| `tagline` | SF Pro Display | 21px | 600 | 1.19 | +0.231px | Tagline / sub-nav |
| `body-strong` | SF Pro Text | 17px | 600 | 1.24 | -0.374px | Ênfase inline |
| `body` | SF Pro Text | 17px | 400 | 1.47 | -0.374px | Parágrafo padrão |
| `caption` | SF Pro Text | 14px | 400 | 1.43 | -0.224px | Caption, botão |
| `button-large` | SF Pro Text | 18px | 300 | 1.0 | 0 | CTA store hero (raro) |
| `fine-print` | SF Pro Text | 12px | 400 | 1.0 | -0.12px | Footer / legal |
| `nav-link` | SF Pro Text | 12px | 400 | 1.0 | -0.12px | Links de nav |

**Substituto open-source:** Inter (Google Fonts, variable) — adicionar `letter-spacing: -0.01em` em display, `font-feature-settings: "ss03"`.

**Escada de pesos:** `300 / 400 / 600 / 700`. **500 é deliberadamente ausente.**

---

### 9.4 Espaçamento

```
--apple-space-xxs:     4px;
--apple-space-xs:      8px;
--apple-space-sm:      12px;
--apple-space-md:      17px;
--apple-space-lg:      24px;   /* padding interno de utility cards */
--apple-space-xl:      32px;
--apple-space-xxl:     48px;
--apple-space-section: 80px;   /* padding vertical de product tile */
```

---

### 9.5 Border Radius

```
--apple-r-none: 0px;       /* tiles full-bleed */
--apple-r-xs:   5px;       /* chips inline (raro) */
--apple-r-sm:   8px;       /* utility buttons, inline card images */
--apple-r-md:   11px;      /* pearl button capsule */
--apple-r-lg:   18px;      /* store/accessories utility cards */
--apple-r-pill: 9999px;    /* CTAs primários, chips, search — assinatura Apple */
--apple-r-full: 9999px;    /* botões circulares sobre foto */
```

---

### 9.6 Componentes chave

#### Botões
| Componente | BG | Texto | Radius | Padding |
|---|---|---|---|---|
| `button-primary` | `#0066cc` | `#fff` | pill | 11px 22px |
| `button-secondary-pill` | transparent | `#0066cc` | pill | 11px 22px |
| `button-dark-utility` | `#1d1d1f` | `#fff` | 8px | 8px 15px |
| `button-pearl-capsule` | `#fafafc` | `#333` | 11px | 8px 14px |
| `button-store-hero` | `#0066cc` | `#fff` | pill | 14px 28px |
| `button-icon-circular` | `#d2d2d7` @64% | `#1d1d1f` | 50% | 44×44px |

**Active state universal:** `transform: scale(0.95)` — sem mudança de cor.

#### Cards
- **`product-tile-light`**: full-bleed, bg `#fff`, padding `80px`, sem radius.
- **`product-tile-dark`**: full-bleed, bg `#272729`, padding `80px`, texto `#fff`.
- **`store-utility-card`**: bg `#fff`, borda `1px #e0e0e0`, radius `18px`, padding `24px`.
- **`configurator-option-chip`**: bg `#fff`, texto `#1d1d1f`, radius pill, padding `12px 16px`.
- **`floating-sticky-bar`**: bg `#f5f5f7` @80% + `backdrop-filter: blur()`, height `64px`.

#### Elevação (hierarquia completa)
| Nível | Tratamento | Uso |
|---|---|---|
| Flat | sem shadow, sem borda | tiles, nav, footer |
| Hairline | `1px rgba(0,0,0,0.08)` | utility cards, sub-nav |
| Backdrop blur | `backdrop-filter: blur(N)` | sub-nav frosted, sticky bar |
| Product shadow | `rgba(0,0,0,0.22) 3px 5px 30px` | renders de produto — APENAS aqui |

---

### 9.7 Regras de ouro (Do's and Don'ts)

**✅ Fazer:**
- `#0066cc` para TODA ação interativa — links, CTAs, focus rings. Nenhuma exceção.
- Headlines: SF Pro Display 600 com letter-spacing negativo.
- Body: 17px / 400 / line-height 1.47 — nunca 16px.
- Alternar tiles light ↔ dark para ritmo de seção. A troca de cor É o divisor.
- `border-radius: 9999px` para o CTA primário — é a assinatura visual de ação.
- Drop-shadow (`rgba(0,0,0,0.22) 3px 5px 30px`) apenas em imagens de produto sobre superfície.
- Active state: `transform: scale(0.95)` em todos os botões.

**❌ Não fazer:**
- Segunda cor de destaque — tudo interativo é Action Blue.
- Shadows em cards, botões ou texto.
- Gradientes decorativos como fundo — atmosfera vem de fotografia.
- `font-weight: 500` — a escada é 300/400/600/700.
- Radius em tiles full-bleed — tiles são retangulares edge-to-edge.
- Line-height < 1.47 em body copy.
- `primary-on-dark (#2997ff)` em superfícies claras.

---

### 9.8 Grid & Responsivo

| Breakpoint | Largura | Mudança principal |
|---|---|---|
| Wide desktop | ≥1441px | conteúdo trava em 1440px |
| Desktop | 1069–1440px | layout completo, grid 4–5 col |
| Small desktop | 1024–1068px | tiles com margin gutters |
| Tablet landscape | 834–1023px | nav completa retorna |
| Tablet portrait | 736–833px | nav colapsa para hamburger |
| Large phone | 641–735px | padding 48px (vs 80px) |
| Phone | 420–640px | stack 1-col, render 80% largura |
| Small phone | ≤419px | hero typography cai para 28px |

**Max content width:** ~980px (texto) / ~1440px (grids) / full-bleed (product tiles).  
**Touch targets mínimos:** 44×44px.

---

### 9.9 Aplicabilidade ao OTC Tracker

Usar como referência para:
- **Hierarquia tipográfica** das páginas internas — manter coerência de pesos e tamanhos.
- **Paleta de cores** para novos componentes — preferir cores semânticas sólidas, sem gradientes decorativos.
- **Elevação e profundidade** — limitar shadows ao mínimo necessário; usar `border` sutil em cards.
- **Botões** — manter o padrão pill para CTAs primários quando aplicável.
- **Contraste** — respeitar as regras de cor-em-dark vs. cor-em-light (ex.: nunca usar Action Blue em fundo escuro sem verificar; usar variante `on-dark`).
- **Espaçamento** — a grade de 8px base do Apple é compatível com Bootstrap (que também usa múltiplos de 8px via `rem`).

> ⚠️ O OTC Tracker usa Bootstrap 5 + Tabler theme, não SF Pro. Adaptar os princípios ao sistema existente — não substituir as classes Bootstrap por tokens Apple diretamente.

---

## 12. Sessão 2026-06-15 — Export Dropdown Opacity + Comitente Toolbar

### O que foi feito

#### Fix de opacidade no dropdown Export (DataTables `collection`) — múltiplas páginas
- O dropdown gerado pelo DataTables para botões `extend: 'collection'` tinha fundo semi-transparente, tornando as opções (CSV, Excel, PDF, Print) praticamente invisíveis.
- **Solução:** adicionado bloco CSS com `.dt-button-collection` forçando fundo sólido (`#fff`), sombra e texto opaco. Suporte a dark mode via `[data-bs-theme="dark"]`.
- **Arquivos corrigidos:**
  - `apps/templates/pages/reference-data.html`
  - `apps/templates/pages/index-b3-results.html`
  - `apps/templates/pages/pending-confirmation.html`
  - `apps/templates/pages/new_deals-opt-commodities.html`
  - `apps/templates/pages/new_deals-ndf-commodities.html`
  - `apps/templates/pages/reconciliation-comitente.html`

#### Reconciliation Comitente — reestruturação do toolbar
- **Removido:** filtro Max Score (input + botão Filter) do Card Header 2 — ficou só o seletor de Date.
- **Adicionado:** botões Export (collection: CSV/Excel/PDF/Print) e Columns (colvis) no Card Header 3.
- **Removidos:** `filterByScore()` e listener `$('#btnFilterScore')`, referência a `#max-score` no `clearFilters()`.
- **Script adicionado:** `buttons.print.min.js` que estava faltando (causava falha silenciosa na criação dos Buttons).

### Padrão crítico identificado: DataTables 2.x + Buttons 3.x sem `B` no dom

**Problema:** quando o `dom` do DataTable não contém `B`, a instância de Buttons não é criada automaticamente. Chamar `new $.fn.dataTable.Buttons(table, {...})` fora do `initComplete` pode falhar silenciosamente se `extend: 'print'` estiver presente sem o `buttons.print.min.js` carregado.

**Armadilha adicional:** adicionar `<'d-none'B>` ao dom quebra o cálculo de posição do scroll head quando `scrollX: true` está ativo, cortando o header da tabela e fazendo o filter row desaparecer.

**Solução correta para botões fora do dom:**
```javascript
initComplete: function() {
    var api = this.api();
    try {
        new $.fn.dataTable.Buttons(api, {
            buttons: [ /* ... */ ]
        });
        api.buttons().container().appendTo($('#meuWrap'));
    } catch(e) { console.error('Buttons init:', e); }
    // ... resto do initComplete
}
```

**Scripts obrigatórios para collection + print:**
```html
<script src=".../dataTables.buttons.min.js"></script>
<script src=".../buttons.bootstrap5.min.js"></script>
<script src=".../jszip.min.js"></script>
<script src=".../buttons.html5.min.js"></script>
<script src=".../buttons.print.min.js"></script>  <!-- obrigatório para extend:'print' -->
```

---

## 13. Sessão 2026-06-15 (continuação) — Reconciliation Comitente: filtro por coluna + conflito B/scrollX

### Conflito crítico: `B` no dom + `scrollX: true` + filter row manual

**Problema confirmado:** qualquer posição de `B` no `dom` string do DataTable (`B` antes do `tr`, depois do `ip`, dentro de wrapper `d-none`, dentro de wrapper `position-absolute`) **quebra a linha de filtro por coluna** quando `scrollX: true` está ativo. Isso acontece porque qualquer referência a `B` altera o cálculo de largura do scroll head do DataTables 2.x, mesmo que o container seja invisível ou fora do fluxo.

**Regra definitiva para páginas com `scrollX: true` + filter row manual:**
- **NÃO usar `B` no `dom` de forma alguma** — nem com `d-none`, nem com `position-absolute`, nem antes, nem depois
- `buttons:[]` no config sem `B` no dom: Buttons extension **não é inicializado** nessa versão (DataTables 2.x + Buttons 3.x)
- `headerCallback` **não existe** nesta versão do DataTables — grep no `.min.js` retornou vazio

**Estado atual da página `reconciliation-comitente.html`:**
- Filter row por coluna: ✅ funciona (sem `B` no dom)
- Botões Export/Columns: ❌ pendente — requer solução alternativa que não use `B` no dom

**Solução pendente para botões sem `B` no dom:**
- Opção A: Criar botões Bootstrap manualmente no card-header (HTML puro) que chamam `table.button()` via DataTables Buttons API inicializado com `new $.fn.dataTable.Buttons(api, config)` fora do contexto do dom — **não testado ainda**
- Opção B: Remover `scrollX: true` e usar `overflow-x: auto` via CSS no wrapper — elimina o scroll head clonado, mas muda o comportamento visual
- Opção C: Investigar se a versão instalada tem uma API de layout (`layout:{}`) que não conflita com o scroll head

### O que foi feito nesta sessão
- Filter row: restaurado e funcional (sem `B` no dom, injeção manual em `initComplete` nas duas theads)
- `formatExportData`: função adicionada (strip HTML) para uso futuro quando botões forem implementados
- Botões Export/Columns: removidos temporariamente até solução definitiva ser encontrada

---

## 14. Mapping de Moedas — código interno (final "B") → ISO 3 letras

> Mapping de uso frequente no desenvolvimento de New Deals (Fwd Start e Other Publisher). Os feeds internos usam códigos de moeda com terminação "B" (ou variantes) que devem ser normalizados para o código ISO padrão de 3 letras.

| Código interno | ISO 3 letras |
|---|---|
| USB | USD |
| EUB | EUR |
| GBB | GBP |
| CHB | CHF |
| NOB | NOK |
| COB | COP |
| PEB | PEN |
| CLB | CLP |
| TWF | TWD |
| BRR | BRL |
| BRL | BRL |
| USD | USD |
| RMB | CNH |

**Notas:**
- `BRR` → `BRL` e `BRL` → `BRL`: ambos os códigos internos mapeiam para BRL (ver seção 13 / memória [[project_new_deals_conecta]] — strike BRL nunca divide por 100; checar via `brl`/`isBrl`, nunca `BRR`).
- `TWF` → `TWD` (não termina em "B") e `RMB` → `CNH` (RMB = renminbi → offshore CNH) são exceções ao padrão "final B".
- `USD` e `BRL` já vêm no formato ISO em alguns feeds — manter no mapping para idempotência (input já normalizado retorna o próprio valor).

---

## 15. Sessão 2026-06-19 — Coluna Accronym (NDF/Opt) + insert de coluna em DataTable

### O que foi feito

#### Rename `Acronym` → `Accronym` (commodities NDF + Opt)
- Trocado **apenas o texto exibido** (th, placeholder, labels do modal, export headers, `<option>` do seletor de colunas, label do smart-filter, mass-edit, comentário CSS) + valor de tradução **EN** (`nd-col-acronym`, `col-acronym` → "Accronym"). br/es seguem "Sigla".
- **Mantidas as chaves de dados JSON** (`Acronym` em `COL_TO_JSON_FIELD`, `deal.Acronym`, lado direito de `SF_LABEL_TO_FIELD`, payload do cache) — renomear quebraria a releitura de deals já cacheados.

#### Coluna Accronym entre SPN e Client (fwdstart + otherpublisher)
- Comportamento espelhado de commodities: campo `#ar-acronym` no modal com autocomplete (`arBuildDrop`) que auto-preenche `#ar-spn`/`#ar-client`/`#ar-taxid` (agora `disabled`) via RefData.
- **Fonte do autocomplete = `FX CASH ACCRONYM`** (não COMMODITIES) — são páginas FX NDF. Commodities usa `COMMODITIES ACCRONYM`.
- Layouts: fwdstart passou de 27→28 colunas (Maker 26→27); otherpublisher de 25→26 (Maker 24→25). otherpublisher **não tem** Strike Set Date/Offset.

#### SheetJS adicionado
- `apps/static/plugins/xlsx/xlsx.full.min.js` (build standalone 0.20.3, baixado do cdn.sheetjs.com) + `<script>` em fwdstart e otherpublisher antes de `otc-fileupload.js`.
- `gulp plugins` copia por-plugin de `node_modules` e **não limpa** `plugins/`, então o arquivo manual sobrevive ao build.

### Padrão crítico: INSERIR uma coluna no meio de um DataTable destas páginas New Deals

Inserir 1 coluna desloca **todos** os índices ≥ ponto de inserção. Pontos a ajustar (checklist completo):
1. **CSS** `th/td:nth-child(N)` — renumerar e adicionar a nova.
2. **Header row** + **filter row** (2 `<th>`).
3. **`COL_TO_JSON_FIELD`** (mapa col→campo).
4. **`dealJsonToRow`** (array da linha).
5. **Export** `columnLabels` (ATENÇÃO: nessas páginas estava com labels STALE de commodities — corrigido para os reais).
6. **Seletor de coluna** do mass-edit (`<option value="N">`).
7. **Smart-filter** `SF_COLS` (`dtCol`) + `SF_LABEL_TO_FIELD` (label→campo).
8. **`columnDefs`** target oculto (Maker).
9. **Constantes**: `SKIP_EDIT_COLS`, `DATE_COL_INDICES`, `*_COL_INDEX`.
10. **Loop save-edit** (`for colIdx ... <= N`).
11. **Dois extratores** de deal a partir do row (`extractRowDeal` parcial + `rowDataToNdfDeal`/reconstruct com `overrides`+`Maker`).
12. **Modal**: `arOpenEditModal` (`d[N]`), `arBuildDeal`, `arClearFields`.
13. **Refs hardcoded por índice** (perigoso): Client (`?client=` nas APIs de cache, chaves de seleção `rowId|client|index`, `clientRaw`, `rowsToDelete.client`), Maker (`rowMaker`, 4-eyes maker-checker, `cell(rowIdx, Maker)`).

**Validação:** contar `<th>` da header row == `<th>` da filter row == nº de elementos do array de `dealJsonToRow`.

**Armadilhas confirmadas nesta sessão:**
- Há **código morto copiado de commodities** nestas páginas FX: `buildDropdown` (in-cell autocomplete) **nunca é chamado**; bloco `type==='acronym'`/`'underlying'` e `refreshRowMissingBadge` (cols 14/15/28) são no-op (`_ASSET_NDF` sempre vazio). Constantes `MARKET_COL_INDEX`/`UNDERLYING_COL_INDEX`/etc. definidas mas não usadas. Não confiar nelas; ajustar só o que é LIVE.
- `_sh(d[10])` aparecia tanto como Client (chaves de seleção) quanto, após o insert, como Accronym (extratores/modal) — **não** dá pra `replace_all` cego; editar por contexto.

### Pendente / bloqueado
- **Import fwdstart `Brazil_NDF_Blotter_Extended*.xlsx`**: contraparte resolvida por **Accronym OU SPN (o que achar primeiro)** no RefData. NÃO existe parser de Excel ainda (`otc-fileupload.js` só lê `.msg`/`.eml`; `buildRow` é layout commodities). SheetJS já adicionado. **Aguardando o mapeamento das colunas do blotter** (usuário enviará) para construir o parser. Nota: `loadRefData` em `otc-fileupload.js` indexa só por acrônimo → para resolver por SPN será preciso um índice por SPN também.

### Arquivos modificados nesta sessão
```
apps/templates/pages/new_deals-ndf-commodities.html      ← Acronym→Accronym (display)
apps/templates/pages/new_deals-opt-commodities.html      ← Acronym→Accronym (display)
apps/static/data/translations/en.json                    ← nd-col-acronym/col-acronym → "Accronym"
apps/templates/pages/new_deals-ndf-fwdstart.html         ← coluna Accronym + modal + SheetJS
apps/templates/pages/new_deals-ndf-otherpublisher.html   ← coluna Accronym + modal + SheetJS
apps/templates/partials/sidenav.html                     ← removidos ícones dos subitens Live Position
apps/static/plugins/xlsx/xlsx.full.min.js                ← ADICIONADO (SheetJS 0.20.3)
```

---

## 16. Sessão 2026-06-22 — Notificação "Sent" duplicada + Export recon + About

### Sistema de notificações (sino do topbar)
- Backend: `_create_notification(actor_sid, actor_name, action, page, detail)` em `apps/pages/routes.py` grava na tabela DuckDB `notifications`. O sino (`apps/templates/partials/topbar.html`) faz **polling** de `/api/notifications` e renderiza um dropdown (badge de não-lidos via `otc_notif_last_seen_id` no localStorage). Não é toast — é um centro de atividade passivo.
- `ACTION_META` (em topbar.html) mapeia `action` → ícone/cor. Ações conhecidas: `New Deals`, `Status Updated`, `Deal Updated`, `Deal Deleted`, `Bulk Delete`, `Bulk Update`, `Sent to B3`, `B3 Mapped`, `Recon Generated`, `Access Request`, etc.

### Bug: envio gerava 2 entradas no sino
Ao enviar (bulk OU row-level), o frontend faz `POST send-conecta` → backend cria **"Sent to B3"** (correto), e logo depois faz `PATCH cache` com `{Status:'Sent'}` → endpoint de update via `if 'Status' in _fields` criava **"Status Updated → Sent"** (redundante). Resultado: popup SweetAlert + 2 itens no sino.

**Fix:** suprimir a notificação "Status Updated" quando o novo status for `'Sent'` (o único caminho para `Status='Sent'` é o fluxo de envio, que já emite "Sent to B3"). Aplicado nos **3** endpoints de update:
- `api_update_deal_cache` (Opt Comm, ~1521)
- `api_ndf_update_deal_cache` (NDF Comm, ~2164)
- `api_generic_nd_update_cache` (fwd-start/other-publishers, ~3404)

Padrão: `if 'Status' in _fields: if str(_fields.get('Status','')) != 'Sent': _create_notification(... 'Status Updated' ...)`.

Detalhe útil: o SweetAlert2 só mostra **um** popup por vez (uma nova chamada substitui a anterior) — então "ver duas notificações" nunca é double-binding de Swal; investigar outras fontes (backend/sino).

### Export buttons em reconciliation-comitente.html
Bug: os botões de export **nunca apareciam** porque a config `buttons:` não existia e o `dom` não tinha `'B'` — só havia o container vazio `<div id="reconExportWrap">`.

**Fix (padrão p/ botões em container custom):**
1. Adicionar `buttons: [...]` na init do DataTable (collection dropdown Copy/CSV/Excel/Print/PDF, usando `formatExportData` p/ stripar HTML; `columns: ':visible'`, `modifier:{page:'all'}`).
2. No `initComplete`: `api.buttons().container().appendTo('#reconExportWrap');`
Libs já incluídas na página (jszip, pdfmake, vfs_fonts, buttons.html5/print). Tabela tem 30 colunas (0-29; SC() também gera coluna).

### About page atualizada
`apps/templates/pages/about.html`: 3 cards novos (NDF Forward Start, NDF Other Publisher, Reconciliation Comitente) + botões no hero (5) e CTA (6). i18n `about-feat-{fwd,other,recon}-{title,desc}` em en/br/es.

### Arquivos modificados nesta sessão
```
apps/pages/routes.py                                     ← dedup "Status Updated" quando Status=='Sent' (3 endpoints)
apps/templates/pages/reconciliation-comitente.html       ← config buttons + appendTo #reconExportWrap
apps/templates/pages/about.html                          ← 3 cards + botões hero/CTA dos novos módulos
apps/static/data/translations/{en,br,es}.json            ← chaves about-feat-{fwd,other,recon}-*
```

---

## 17. Sessão 2026-06-22 (continuação) — Intrag: coluna Status + lifecycle, checkbox clear, BRR→BRL

### Coluna Status (após Actions) em intrag-ndf e intrag-option

Inserida a coluna **Status** logo após Actions (col index 2). Lifecycle **completo apenas em intrag-ndf** (persistido no `*_intrag_ndf.json`); **intrag-option é visual-only** (sem backend de lifecycle ainda — decisão do usuário).

**Máquina de estados (intrag-ndf):**
| Transição | Gatilho | Regra |
|---|---|---|
| → **New** | 1ª gravação no JSON | `_save_intrag_ndf_entry` seta `status='New'`; em re-save **preserva** o status existente |
| New/Approved → **Sent** | botão Send | Send permitido **só** se status ∈ {New, Approved} |
| qualquer edição → **Pending** | edit row-level salvo | grava `maker = user_sid` |
| Pending → **Approved** | botão Approve (✓ verde, só aparece em Pending) | **maker ≠ checker** validado no servidor (403 em self-approval; grava `checker`) |

### Backend (`apps/pages/routes.py`)
- `_save_intrag_ndf_entry`: entry agora carrega `status`/`maker`/`checker`; `'New'` na 1ª escrita, **preservado** em re-save (idx existente).
- Helper `_find_intrag_ndf_entry(deal_id, trade_date)` — acha entry por deal id (estreita pelo arquivo do dia via trade_date; se não achar, varre todos os `*_intrag_ndf.json`). Reusado por send/edit/approve.
- `POST /api/intrag/ndf/edit` → atualiza campos, seta `Pending`, grava maker, limpa checker.
- `POST /api/intrag/ndf/approve` → `Pending`→`Approved`; **403 se maker == checker**; grava checker.
- `api_intrag_ndf_send_file`: novo payload `items:[{deal_id, cells}]` (retrocompatível com `rows`); após escrever os .txt, vira `New/Approved → Sent` nos entries persistidos.

### Padrão: INSERIR coluna no início dos dados (índice +1) nas páginas intrag
Mesma lógica do checklist da seção 15, aplicada às tabelas DataTables client-side de intrag. intrag-ndf passou data 2-31→**3-32**, hidden id 32→**33**; intrag-option data 2-39→**3-40**, id 40→**41**. Pontos ajustados:
1. Header row + filter row (novo `<th>` Status).
2. `columnDefs`: `visible:false` no id deslocado + **render do badge** em `targets:2` (raw value → `statusBadge()`).
3. `drawCallback` / `selectAll` / change de checkbox / `[data-del-selected]`: `d[id]` deslocado.
4. `exportCols` (range das colunas de dados +1).
5. Toggle de colunas (`data-column` = i+3).
6. `SF_COLS` `dtCol` (todos +1; em intrag-option é o `map(...dtCol:i+3)`).
7. `_intragRowData` `slice(3,33)`; handler de edit `d[i+3]`; save handler insere a célula de status após Actions e usa o id deslocado.

**Status badge dinâmico + i18n:** o badge é renderizado por JS com `data-lang="intrag-status-*"`. O `applyTranslations()` (em `app.js`) re-varre `[data-lang]` a cada troca de idioma → traduz no switch; no 1º paint pós-load assíncrono mostra inglês (mesmo comportamento de todo conteúdo dinâmico de célula). Header da coluna traduz normalmente.

### Fix: limpar checkboxes após Send (intrag-ndf)
No sucesso do `sendIntragItems`, `selectedRowIds.clear()` antes do redraw — o `drawCallback` então re-sincroniza checkboxes das linhas, o selectAll e os botões de toolbar (Send/Delete).

### i18n: BRR → BRL (apenas valores)
Trocado o **texto exibido** "Is BRR Fixed?" → "Is BRL Fixed?" (en), "BRR Fixado?" → "BRL Fixado?" (br), "¿BRR Fijado?" → "¿BRL Fijado?" (es). **Chaves mantidas** (`nd-col-is-brr-fixed`, `col-is-brr-fixed`) — são referenciadas por `data-lang` em fwdstart/otherpublisher; renomeá-las quebraria o lookup. (Ver mapping de moeda na seção 14: BRR é código interno que normaliza p/ BRL.)

### Chaves de tradução adicionadas (en/br/es)
```
intrag-col-status, intrag-btn-approve
intrag-status-new / -pending / -approved / -sent
```

### Decisões em aberto / não feitas (confirmadas com o usuário)
- intrag-option **sem** backend de lifecycle — status é só badge visual ("New", preservado em edição). Para lifecycle real precisaria de rota `/api/intrag/option` + `_intrag_option.json` espelhando intrag-ndf.
- `INTRAG_NDF_SEND_DIR` continua caminho Windows hardcoded (`I:\...`) — não funciona no Mac local.
- O gating de Send (só New/Approved) é **client-side**; o servidor só vira `Sent` os elegíveis (consistente com o padrão frontend-driven de New Deals).

### Arquivos modificados nesta sessão
```
apps/pages/routes.py                                     ← status no _save_intrag_ndf_entry + _find_intrag_ndf_entry + /edit + /approve + send-file items/Sent
apps/templates/pages/intrag-ndf.html                     ← coluna Status, shift +1, badge, Approve, gating Send, edit→Pending, clear checkbox pós-send
apps/templates/pages/intrag-option.html                  ← coluna Status visual + shift +1
apps/static/data/translations/{en,br,es}.json            ← intrag-col-status/-btn-approve/-status-*; "Is BRL Fixed?" (BRR→BRL)
```

### Commits desta sessão
- `feat(intrag): Status column + lifecycle (New/Pending/Approved/Sent)`
- `i18n(brr→brl): display "Is BRL Fixed?" label across en/br/es`
- `fix(intrag-ndf): clear ticked checkboxes after successful send`

---

## 18. Sessão 2026-06-22 (cont.) — Emails Premium/Economic Affirmation, CounterpartyDetails, fixes UI

### Intrag — larguras de coluna pós-insert de Status (continuação seção 17)
- A coluna **Status** foi inserida em `nth-child(3)` mas o bloco CSS de larguras não tinha sido deslocado → off-by-one. Corrigido em **ambas** as páginas: `intrag-ndf` (Contract Type 3→4 … Discount Factor 32→33, +regra Status 110px) e `intrag-option` (Portfolio 3→4 … Asian Option Average 40→41). Comentário do bloco atualizado para `(3)=Status (4..N)=dados`.
- Commits: `fix(intrag-ndf): shift column widths +1...`, `fix(intrag-option): shift column widths +1...`.

### Emails de liquidação/confirmação — `apps/pages/otc_emails.py` (NOVO módulo)
Porta a lógica legada `email_Premio` (Premium D0) e `email_if` (Economic Affirmation contra IF) do CommodiXchange para o web app. Espelha o padrão do `recon_comitente.py` (módulo separado + win32com guardado por try/except — Windows/JPM only, degrada com mensagem "win32com não disponível").

- **Premium (opt comm):** filtra `SpotDate == hoje` (dd/mm/yyyy), agrupa por (Acronym, Commodities), separa **cliente** (`B3 ACCOUNT == '73760.10-2'`) e **participante** (`!=`). Constrói o HTML (tabela + Resultado Apurado/IR 0,005%/Final + instruções de pagamento + dados bancários) e abre rascunho no Outlook (`.Display()`). CC cliente = "Liquidação"; participante = "brazil.otc.ops@jpmorgan.com".
- **Economic Affirmation (opt + ndf comm):** filtra `TradeDate == hoje`, `B3 ACCOUNT != '73760.00-9'` (conta JPM) e contraparte **não-Lawton**. Tabela estilo termo (Posição, Data Op, Valor Base, Taxa Forward=Strike, Moeda/Ativo, fixing início/fim mercadoria, fixing moeda, vencimento). Subject sufixo "Termo de Mercadoria" (ndf) / "Opção Mercadoria" (opt).
- **Rotas** (`routes.py`, após mapping-b3): `POST /api/new-deals/opt-commodities/premium-email`, `.../opt-commodities/economic-affirmation`, `.../ndf-commodities/economic-affirmation`. Recebem `{deals:[...]}`, retornam `{ok, count, opened, error}`. `count==0` → frontend mostra "nada a gerar".
- **Frontend:** botões **Premium** (opt) e **Econ. Affirmation** (opt+ndf) nas toolbars (novos slots no `dom`: `premiumBtn`, `econAffBtn`). Coletam todas as linhas via `rowDataToOptDeal`/`rowDataToNdfDeal`. Swal de resultado. i18n `nd-btn-premium`, `nd-btn-econaff`, `swal-email-*`, `swal-premium-none`, `swal-econaff-none`.

**Mapeamento legado (tkinter idx) → campo web** (resolvido pelos nomes do `COL_TO_JSON_FIELD`):
`item[1]`=TradeDate, `[2]`=Market(+Commodities), `[3]`=Direction (Sell/Buy), `[4]`=Instrument, `[6]`=Strike, `[9]`=TotalNotional, `[10]`=SettlementDate, `[15]`=FXConvDate (fixing moeda), `[16]`=FixingStartDate, `[17]`=FixingEndDate, `[18]`=Acronym, `[19]`=Premium, `[22]`=SpotDate, `[23]`=Contract.

### CounterpartyDetails.json (NOVO) + popup na Reference Data
- `apps/static/data/CounterpartyDetails.json` — 439 SPNs únicos (seed do RefData), campos `CGD/BANK/AGENCY/ACCOUNT/CONTACTS` **vazios** (usuário popula). Indexado por SPN.
- `reference-data.html`: duplo-clique numa linha (SPN = col 9) → SweetAlert com os detalhes da contraparte (lookup por SPN). i18n `rd-cp-*`.
- O e-mail Premium "cliente" (Resultado < 0) lê banco/agência/conta deste JSON via SPN; CNPJ vem do TAX ID do RefData.

### Alerta "prêmio hoje" no import (opt comm)
- `processDropzone` (otc-fileupload.js, **compartilhado** com NDF) agora **retorna Promise** resolvendo `{totalDeals, shownSwal}` (antes não retornava nada). NDF ignora o retorno.
- Opt comm encadeia `.then()`: se `totalDeals>0`, conta linhas com `SpotDate==hoje` e mostra Swal com a contagem. i18n `swal-premium-today-*`.

### Fix UI — contraste checkbox não-selecionado
- `.form-check-input-light` (scss/components/_forms.scss) tinha `border-color: rgba(light,0.9)` → quase invisível em fundo claro. Trocado para `rgba(dark,0.4)` (light mode) + `[data-bs-theme=dark]` `rgba(light,0.45)` + hover. **Rodar `npm run build`** (gulp) p/ recompilar — o app carrega `app.css` compilado, não o scss. Prefixo de var do tema é `--ins-`, não `--bs-`.

### Fix UI — notificações read-state (topbar.html)
- Antes: high-water mark `otc_notif_last_seen_id` + handler `show.bs.dropdown` que marcava **tudo** lido ao abrir.
- Agora: **conjunto de IDs lidos** (`otc_notif_read_ids`, cap 500). Abrir o dropdown **não** marca nada; clicar numa notificação marca **só ela** (`markRead`); "Mark All as Read" marca todas (`markAllRead`). Migração one-time do modelo antigo. Visual: classe `notif-unread` (tint + dot azul).

### Clear Filters na Reference Data
- Novo slot `clearFiltersWrapper` no `dom` + botão no `initComplete` (padrão `btn-outline-secondary` + `ti-filter-off` + `data-lang="btn-clear-filters"`). Limpa inputs de `#refdata-search-row` e `api.columns().search('').draw()`.

### Padrões/decisões desta sessão
- **`processDropzone` agora retorna Promise** `{totalDeals, shownSwal}` — callers podem encadear lógica pós-import sem clobber de Swal.
- **Emails Outlook = win32com `.Display()` (rascunho p/ revisão)**, módulo separado, guard try/except como `recon_comitente.run_auto`. Não envia automático.
- **Contas B3 de referência:** JPM = `73760.00-9`; bucket Premium "cliente" = `73760.10-2`. ⚠️ No RefData de teste **todos** os 553 registros têm `73760.10-2` → split/filtro colapsa localmente; em produção difere.
- **Recompilar SCSS:** mudanças em `apps/static/scss/**` exigem `npm run build`; o tema usa prefixo `--ins-`.

### Pendências / em aberto
- **Popular `CounterpartyDetails.json`** (banco/agência/conta/CGD/contatos) — sem isso o e-mail Premium cliente sai com "—".
- **Confirmar mapeamento** no e-mail participante: usei FXConvDate→"Fixing Moeda" e FixingEndDate→"Fixing Mercadoria".
- **EA layout para opção:** atualmente usa a tabela estilo termo (forward) para ambas as páginas; se opção precisar de colunas próprias (strike/prêmio), ajustar `_economic_affirmation_email`.

### Arquivos criados/modificados nesta sessão
```
apps/pages/otc_emails.py                              ← CRIADO (builders + Outlook opener)
apps/static/data/CounterpartyDetails.json            ← CRIADO (439 SPNs, campos vazios)
apps/pages/routes.py                                  ← 3 rotas de email
apps/templates/pages/new_deals-opt-commodities.html  ← botões Premium/EA + alerta import
apps/templates/pages/new_deals-ndf-commodities.html  ← botão EA
apps/templates/pages/reference-data.html             ← duplo-clique popup + Clear Filters
apps/templates/partials/topbar.html                  ← notificações read-state por ID
apps/static/js/pages/otc-fileupload.js               ← processDropzone retorna Promise
apps/static/scss/components/_forms.scss              ← contraste checkbox (+ recompilado app*.css)
apps/static/data/translations/{en,br,es}.json        ← rd-cp-*, nd-btn-*, swal-email/premium-today/econaff-*
apps/templates/pages/intrag-ndf.html                 ← larguras coluna +1 (Status)
apps/templates/pages/intrag-option.html              ← larguras coluna +1 (Status)
```

### Commits desta sessão (cont.)
- `fix(intrag-ndf): shift column widths +1 after Status column insert`
- `fix(intrag-option): shift column widths +1 after Status column insert`
- `feat(new-deals): Premium D0 + Economic Affirmation e-mails, CP details, UI fixes`

---

## 19. Sessão 2026-06-22 (cont.) — Reference Data: editor Counterparty (glass) + padrão de contraste de checkbox

### 19.1 Editor de Counterparty no duplo-clique (`reference-data.html`)
O antigo popup (tabela `info`/SPN/CGD/Bank/Agency/Account/Contacts) foi substituído por um
**editor liquid-glass com modo view ↔ edit**. Estrutura em **3 zonas**, cada uma com botão **Add**
(visível só em edit):

- **CGD** — lista de valores (N entradas). View: cards; Edit: inputs + Add/remover.
- **Dados Bancários** — dividido em **PAY** e **RECEIVE**; cada um lista de `{bank, agency, account}`.
  O campo **Bank** é um **select2 com autocomplete** populado por `CP_BANKS` (BB-001, Santander-033,
  Bradesco-237, Itaú-341, JPM-376, Citibank-745, BofA ML-755).
- **Contatos** — em **edit**, um card editável por contato (`Name, Phone, E-mail, Rules[multi], Status`);
  em **view**, duas linhas resumo — **Settlement** e **Negotiation** — listando os contatos cuja
  `rules` inclui aquela regra, juntos por `; `. Regras: `CP_RULES` (Negotiation, Repurchase, Settlement,
  Confirmation Letter, Settlement Advice, Contact Confirmation, IOF).

**Botões de ação** = 2 **ícones** no header (sem texto):
- primário: ✎ Edit (view) ↔ ✓ Save (edit)
- secundário: ✕ Close (view) ↔ ↩ Cancel (edit, descarta e volta pra view)

**Visual/animação** (emil-design-eng): popup `.cp-glass` (bg translúcido + `backdrop-filter blur(22px)`
+ sheen `::before` + sombra; dark mode próprio). Entrada `cpGlassIn` 200ms `cubic-bezier(.23,1,.32,1)`,
saída `cpGlassOut` 140ms (exit mais rápido); `transform-origin: center` (é modal); respeita
`prefers-reduced-motion`. Botões com `:active { transform: scale(.92) }`. select2 usa
`dropdownParent: $(popup)` para funcionar dentro do focus-trap do SweetAlert2.

**Modelo de dados normalizado** (`_normCp`) — aceita o formato legado plano e o novo estruturado:
```
{ SPN, COUNTERPARTY,
  CGD: ["..."],
  BANKING: { PAY:[{bank,agency,account}], RECEIVE:[...] },
  CONTACTS: [{name,phone,email,rules:[],status}] }
```
`CounterpartyDetails.json` continua no formato plano antigo (campos vazios) — `_normCp` converte na
leitura; nenhum migration necessário.

**⚠️ Persistência ainda é só em memória.** Save atualiza `_CPDETAILS[spn]` + toast
"Saved (session only)" / "Salvo (somente nesta sessão)". **Falta endpoint backend** para gravar em
`CounterpartyDetails.json` (próximo passo se quiser persistir entre reloads).

i18n novos (en/br/es): `rd-cp-zone-bank, rd-cp-pay, rd-cp-receive, rd-cp-edit, rd-cp-save,
rd-cp-cancel, rd-cp-saved, rd-cp-c-name, rd-cp-c-phone, rd-cp-c-email, rd-cp-c-rules,
rule-settlement, rule-negotiation, cp-none, cp-add, swal-close`.

### 19.2 Contraste de checkbox como padrão app-wide (`_forms.scss`)
O contraste de borda do checkbox não-marcado usado em New Deals NDF/Opt Comm
(`.form-check-input-light`) virou **padrão global**. Adicionado em `_forms.scss`:
```scss
.form-check-input:not(:checked) { border-color: rgba(var(--bs-dark-rgb), 0.4); &:hover { … 0.6 } }
[data-bs-theme="dark"] .form-check-input:not(:checked) { border-color: rgba(var(--bs-light-rgb),0.45); &:hover{ …0.65 } }
```
Agora **todo** checkbox (não só os marcados `-light`) lê bem contra linhas claras. Só a borda do
estado não-marcado é alterada; estado marcado mantém o fill. Switches em dark mode têm regra de maior
especificidade, então não regridem. **Recompilado** `npm run build` → `app*.css`.

### Arquivos (seção 19)
```
apps/templates/pages/reference-data.html      ← editor glass (CSS + JS dblclick reescrito)
apps/static/scss/components/_forms.scss        ← .form-check-input:not(:checked) global (+ recompilado)
apps/static/data/translations/{en,br,es}.json  ← +16 chaves rd-cp-*/rule-*/cp-*/swal-close
```

### Pendências (seção 19)
- ~~Endpoint p/ persistir `CounterpartyDetails.json`~~ → feito na seção 20.
- Popular `CounterpartyDetails.json` com dados reais → script de import na seção 20.

---

## 20. Sessão 2026-06-22 (cont.) — Persistência CP, date picker, badges, botões sólidos, e-mails Premium/EA

### 20.1 Persistência do editor de Counterparty
- **Endpoint** `POST /api/counterparty-details/save` em `routes.py` (logo antes da seção
  GENERIC NEW-DEALS CACHE). Auth check; recebe `{SPN, COUNTERPARTY, CGD, BANKING, CONTACTS}`;
  faz upsert por SPN em `CounterpartyDetails.json` (grava `.bak` com timestamp antes de salvar);
  preserva COUNTERPARTY existente se vier vazio.
- **Front-end** (`reference-data.html`): o Save do diálogo agora faz `fetch` p/ o endpoint.
  Feedback inline via `flashSaved(popup, text, type)` (`pending`→spinner `cpSpin` próprio, pois
  Tabler não anima `.ti-spin`; `ok`→verde; `error`→vermelho). **Não** usa `Swal.fire` toast
  (fecharia o diálogo — SweetAlert2 tem um único container). `rd-cp-saved` deixou de ser
  "session only".

### 20.2 Campo CGD = date picker (dd/mm/yyyy)
Cada linha de CGD tem botão de calendário que sobrepõe um `<input type="date">` nativo (opacity 0);
no `change` escreve a data como **dd/mm/yyyy** no input de texto. Helpers `_ymdToBr` / `_brToYmd`.
Sem dependência externa (flatpickr não está realmente wired nos assets).

### 20.3 Rules como badges + scroll no edit
- Rules do contato = `select2` multiple; as tags são estilizadas como **badges** (pills azuis).
- **Scroll** (fix importante): em edit o diálogo passava da viewport e escondia campos + footer.
  Causa = flexbox: `.cp-body` precisava de `min-height: 0` p/ encolher e rolar. `.swal2-html-container`
  vira `display:flex !important` (vence inline do SweetAlert), `flex-direction:column`, `max-height:88vh`;
  `.cp-glass` cap `92vh`. Header (`.cp-head`) e footer (`.cp-footer`) ficam fixos (`flex:0 0 auto`),
  body rola.

### 20.4 Botões do diálogo (modelo "Edit Record")
Movidos do header para um **footer** (bottom-right), sólidos com ícones brancos:
`is-close` (vermelho, ✕) · `is-save` (verde, `ti-device-floppy`) · `is-edit` (azul, lápis).
Ordem: cancelar (vermelho) à esquerda, salvar/editar à direita. `refreshButtons()` troca classe+ícone
conforme modo view/edit.

### 20.5 E-mails Premium (D0) e Economic Affirmation — ajustes finais
- **Banco no Premium negativo**: quando `final < 0` (JPM paga a contraparte) usa `BANKING.PAY`
  (`_first_bank(cp, 'PAY')`; fallback RECEIVE → flat). `prefer` parametriza o bucket.
- **To do Premium** = e-mails dos contatos de **Settlement** (`_contacts_emails(cp, _SETTLEMENT_KEYWORDS)`,
  keywords `('settlement','repurchase')`, dedup).
- **CC**: Premium = `Liquidação; Brazil Comm Sales`; Economic Affirmation (opt+ndf) =
  `brazil.otc.ops@jpmorgan.com; Brazil Comm Sales`.
- **View do duplo-clique** (Settlement/Negotiation): mostra **e-mails** (dedup) agrupados por
  keyword nas rules — Settlement←`settlement`/`repurchase`; Negotiation←`negotiation`/`confirmation`/`letter`.

### 20.6 Script de import de contatos
`scripts/import_client_contacts.py` — lê a planilha **CONTATO DE CLIENTES** (auto-localiza no
`~/Downloads` ou recebe path), dados a partir da **linha 5**, colunas **B=SPN, C=nome, D=ativo(A),
E=contato, F=fone, G=e-mail, H=Rule**. Casa por SPN **ignorando zeros à esquerda** (planilha e JSON);
agrupa contatos por SPN, mapeia rules p/ as canônicas, status A/I→Active/Inactive; substitui CONTACTS
do SPN (preserva CGD/BANKING), anexa SPNs novos; `.bak` antes de gravar. Flags `--dry-run`, path arg.
Deps: pandas + openpyxl (instalados). Rodar: `python3 scripts/import_client_contacts.py [--dry-run]`.

### Arquivos (seção 20)
```
apps/pages/routes.py                          ← endpoint /api/counterparty-details/save
apps/pages/otc_emails.py                       ← _first_bank(prefer), _contacts_emails, To/CC, PAY
apps/templates/pages/reference-data.html        ← persistência, date picker, badges, footer, scroll fix
apps/static/data/translations/{en,br,es}.json   ← +rd-cp-saving/-save-error/-pickdate
scripts/import_client_contacts.py               ← NOVO import da planilha
```

### Pendências (seção 20)
- Popular `CounterpartyDetails.json` (rodar o script com a planilha real no Downloads).
- Confirmar semântica PAY/RECEIVE vs sinal do resultado se surgir caso de `final > 0` com banco da CP.

---

## 21. Sessão 2026-06-23 — E-mail .eml (cross-machine), contas bancárias maker/checker + Default PAY/RECEIVE

### 21.0 ⚠️ REGRA GLOBAL: SPN ignora zeros à esquerda
**Sempre** que casar SPN entre planilha e `CounterpartyDetails.json` (ou qualquer lookup de SPN),
**desconsiderar zeros à esquerda nos dois lados**: `000123` e `123` são a mesma contraparte.
Helper canônico: `norm_spn()` nos scripts; `_norm_spn()` em `routes.py`. (pandas lê `123` como `'123.0'` →
o helper também tira o `.0`.)

### 21.1 Geração de e-mail Premium/EA agora é download .eml (não win32com)
- **Causa:** `win32com.Dispatch('Outlook.Application')` roda **no servidor** (Flask/Gunicorn), então só
  abria o Outlook **na máquina do servidor** — nunca na do usuário remoto. Não há como acionar o Outlook
  local do usuário a partir do servidor num app web.
- **Fix:** `otc_emails.build_drafts_download(drafts, sender_email)` gera **`.eml`** (1 draft) ou **`.zip`**
  de `.eml` (vários), com header **`X-Unsent: 1`** (faz o Outlook abrir como **rascunho editável**) e
  `From` = e-mail do SID logado (`session['user_email']`). As 3 rotas
  (`premium-email`, `opt/ndf economic-affirmation`) retornam o arquivo via `_email_drafts_response()`
  (helper em routes) com `Content-Disposition: attachment` + header `X-Draft-Count`; quando não há nada a
  gerar, retornam JSON `{ok:true,count:0}`.
- **Frontend:** `_handleEmailResponse` (opt) e bloco inline (ndf) ramificam por `Content-Type`: JSON →
  "nada a gerar"/erro; binário → baixam o blob (cria `<a download>`), Swal "Drafts Downloaded". i18n
  `swal-email-ok-*` atualizado.
- `open_outlook_drafts` foi **removido**. Não é mais 100% automático: o usuário baixa e abre o arquivo
  (limitação de segurança do browser; pode marcar "sempre abrir .eml" no Chrome/Edge p/ abrir sozinho).
- **Formatação Premium:** `<br>` entre o bloco de valores (Apurado/IR/Final) e o bloco bancário; labels
  bancários (Nome/banco, Agência, Conta-corrente, CNPJ) agora também em **negrito**. Conta JPM corrigida
  p/ `5116003`.

### 21.2 Novo modelo de contas bancárias (`BANKING.ACCOUNTS` + defaults)
Substitui o `BANKING.PAY/RECEIVE` plano. Por registro em `CounterpartyDetails.json`:
```
BANKING: {
  ACCOUNTS: [ {id, bank, agency, account, status:'Active'|'Pending', maker, checker} ],
  DEFAULT_PAY:     {current, pending, maker, checker},
  DEFAULT_RECEIVE: {current, pending, maker, checker}
}
```
- `_first_bank(cp, prefer)` em `otc_emails.py` agora usa `DEFAULT_<prefer>.current` (conta **aprovada**)
  → primeira ativa → legado PAY/RECEIVE → flat. **Só o `current` (default aprovado) entra nos e-mails**;
  `pending` não afeta nada até ser aprovado.
- Migração automática: `_bank_norm()` (routes) e `_normBank()` (JS) convertem PAY/RECEIVE/flat legados em
  ACCOUNTS na leitura — sem migration destrutivo.

### 21.3 Maker/checker das contas + Default
- **Cadastrar conta** (UI) → `POST .../banking/account/add` → status **Pending**, `maker=SID`.
- **Aprovar conta** → `.../account/approve` → **403 se maker==checker**; vira **Active**, grava `checker`.
- **Excluir** → `.../account/delete` (limpa refs de default).
- **Definir Default PAY/RECEIVE** (decisão do usuário: **também passa por maker/checker**) →
  `.../default/set` (só conta Active) grava `slot.pending` + `maker`; `.../default/approve`
  (**403 se maker==checker**) move `pending→current`, grava `checker`.
- **Import = Active** (decisão do usuário): a planilha oficial é seed confiável; só contas cadastradas
  manualmente na página passam pelo fluxo Pending→Active.
- Endpoints todos em `routes.py` (após `/api/counterparty-details/save`, que agora **preserva** BANKING e
  só grava CGD/CONTACTS/COUNTERPARTY). `_cpd_save_list` faz `.bak` antes de gravar.

### 21.4 UI reference-data (editor glass)
A zona **Banking Data** virou interativa (fora do view/edit gate): lista de contas com badge
Active/Pending, botões **PAY**/**RECEIVE** (★ = default atual; tracejado = default pending),
**Approve** (✓, só em Pending, desabilitado p/ próprio maker), **Excluir**, e form **Add** (select2 Bank +
Agency + Account). Banner de "Pending default" com Approve. Tudo via `bankFetch()` → atualiza
`bankState` + `_CPDETAILS[spn].BANKING` + `refreshBankZone()`. Funções: `_normBank`, `_renderBankZone`,
`_accBadge`, `_accLabel`. i18n novos: `rd-cp-acc-active/-pending`, `rd-cp-pending-default`,
`rd-cp-acc-need-active`.

### 21.5 Scripts de import (zeros à esquerda)
- `scripts/import_cgd_bank.py` (sessão anterior): `CGD_Bank.xlsx` H=SPN, N=CGD, O/P/Q=Bank/Agency/CC →
  espelha em PAY/RECEIVE (modelo antigo).
- `scripts/import_dados_bancarios.py` (**NOVO**): `dados_bancarios.xlsx` A=SPN, C=Bank, D=Agency, E=CC.
  1+ contas por SPN → `BANKING.ACCOUNTS` (Active, maker/checker='IMPORT'); **idempotente** (dedup por
  bank+agency+account, preserva ids/defaults/CGD/CONTACTS); se a CP ficar com **1 conta** e sem default,
  vira default de PAY e RECEIVE. `--dry-run` + path arg. Roda:
  `python3 scripts/import_dados_bancarios.py [--dry-run]`.

### Arquivos (seção 21)
```
apps/pages/otc_emails.py                         ← .eml builders (X-Unsent/From), _first_bank usa defaults, formatação Premium
apps/pages/routes.py                             ← _email_drafts_response; modelo BANKING + 5 endpoints maker/checker; save preserva BANKING
apps/templates/pages/new_deals-opt-commodities.html ← download blob (_handleEmailResponse)
apps/templates/pages/new_deals-ndf-commodities.html ← download blob (inline)
apps/templates/pages/reference-data.html         ← zona Banking maker/checker + Default (CSS+JS) 
apps/static/data/translations/{en,br,es}.json    ← swal-email-ok-*, rd-cp-acc-*
scripts/import_dados_bancarios.py                ← NOVO import de contas (ACCOUNTS model)
```

### 21.6 Default mais claro + notificações no sino (incremento)
- **UI:** cada conta default mostra um **chip explícito** (`★ Default PAY` azul / `★ Default RECEIVE`
  ciano; `⏳ pending` quando proposto), além do estado ★ no botão; a linha da conta default ganha
  `box-shadow inset 2px 0 0 #0d6efd` (`.cp-acc-row.is-default`). Botões PAY/RECEIVE têm `title` (tooltip
  "Set as Default PAY/RECEIVE"). Botões de editor (Add/excluir) agora **sólidos** com ícone branco
  (`.cp-addbtn` azul, `.cp-remove`/`.cp-acc-del` vermelho). i18n `rd-cp-default-pay/-receive`,
  `rd-cp-set-pay/-receive`, `rd-cp-pending-short`.
- **Notificações:** os 5 endpoints de banking chamam `_create_notification` (helper `_notify_bank`,
  page=`Reference Data`) → ações `Bank Account Added/Approved/Deleted`, `Bank Default Set/Approved`.
  `ACTION_META` (building-bank/star/trash) + `PAGE_URL['Reference Data']='/reference-data'` no topbar.
  `bankFetch` chama `window.fetchNotifications()` no sucesso → sino atualiza na hora (padrão da seção 12).

### Pendências (seção 21)
- Rodar `import_dados_bancarios.py` com a planilha real no Downloads.
- Testar o fluxo maker/checker no app rodando (2 SIDs) — gating de Default e self-approval.
- `_build_cpdetails_index` (otc_emails) ainda casa SPN por string upper, **não** normaliza zeros à
  esquerda — alinhar com a regra 21.0 se aparecer mismatch nos e-mails.


---

## 22. Sessão 2026-06-23 (cont.) — Intrag Option: pipeline New Deals Opt → JSON + página

### Pipeline (espelha o Intrag NDF)
Quando um deal de **New Deals Opt Comm** vira **Status=Success** e a contraparte é **Banco J.P. Morgan**
(intragrupo), grava um entry no JSON diário `*_intrag_opt.json` com `status='New'`.
- **Backend** (`routes.py`): `INTRAG_OPT_CACHE_DIR` (`.../cache/new deals/Intrag/Option/YYYY/MM/`),
  `_save_intrag_opt_entry(deal)` + `_maybe_save_intrag_opt(deal)` (filtro JPM). GET `/api/intrag/option`
  (mesma assinatura do `/api/intrag/ndf`: `date`/`date_from`/`date_to` → `{success, entries}`).
- **Gatilhos**: `api_update_deal_cache` (opt PATCH, Status→Success) e `api_mapping_b3` (opt, Success).
- **Re-save preserva** `status/maker/checker` **e** `my_number/cetip_number` (gerados 1×).

### Mapeamento de colunas (parcial — restante o usuário define depois)
| Coluna intrag-opt | Origem / regra |
|---|---|
| Portfolio | fixo `INTRAGJP552` |
| System ID | fixo `OPCAO` |
| Line Type ID | fixo `1` |
| Registration Date | TradeDate `dd/mm/yyyy` |
| **Buyer Account** (era Holder) | Direction BUY→`00041.00-7`, SELL→`73760.00-9` |
| **Buyer Name** (era Holder) | `73760.00-9`→`BANCO J.P MORGAN S.A`, `00041.00-7`→`LAWTON MULTIMERCADO-FI` |
| Contract | Instrument Put→`OFVC`, Call→`OFCC` |
| **B3 ID** (era CETIP Contract) | `B3_ID` |
| My Number | aleatório 10 dígitos |
| **Seller Account** (era Writer) | inverso do Buyer Account |
| **Seller Name** (era Writer) | inverso do Buyer Name |
| Start Date | TradeDate `dd/mm/yyyy` |
| Maturity Date | SettlementDate `dd/mm/yyyy` |
| CETIP Number | aleatório 16 chars (alfanum) |
| SISBACEN Currency Code | fixo `COM` |
| Currency Symbol | 3 primeiras letras de Commodities |

Contas intragrupo: `73760.00-9`=JPM, `00041.00-7`=Lawton.

### Frontend (`intrag-option.html`)
- **Fix de espaçamento** acima dos headers (scrollX clone cortava o checkbox): `padding-top` no
  `.dt-scroll-head`/`thead th`.
- Renames nos `<th>` + `OPT_COLS` + i18n (`intrag-opt-col-4/5/7/10/11`): Holder→Buyer, Writer→Seller,
  CETIP Contract→B3 ID.
- `OPT_ENTRY_FIELDS` (38 chaves = ordem de OPT_COLS) + `intragOptLoad()` (fetch `/api/intrag/option`,
  monta linhas `[checkbox, actions, status, …38 dados, _deal]`) chamado no load. Convive com o Add manual.

### Pendências (seção 22)
- **Colunas restantes** (17–37: Investment Amount … Asian Option Average + Trade Type col 9) — o usuário
  enviará o mapeamento; já existem como placeholders vazios em `_save_intrag_opt_entry`/`OPT_ENTRY_FIELDS`.
- Intrag Option **ainda sem lifecycle backend** (send/approve/edit) como o NDF — status é só badge; o load
  popula do JSON. Quando precisar, espelhar `/api/intrag/ndf/{send-file,edit,approve}`.

### 22.1 Colunas restantes + lifecycle + geração de arquivo (cont.)
**Colunas 17–37** (`_save_intrag_opt_entry`): Premium (`investment_amount`, `.2f`), FX Base
(`fx_base_value`=TotalNotional `.2f`), Unwind Amount/Unit Price (`prepaid_value`/`prepayment_unit_price`,
vazios), Call/Put Strike (`.8f`, strike×cents só se ccy≠BRL e QuotedInCents=YES; por instrument),
Call/Put Unit Premium (idem com PremiumPerUnit), Exercise=`EUROPEIA`, Info Source=`COMMODITIES`,
Bulletin=`9`, **Fixing** (`maturity_rate`=dias úteis weekday entre FixingEndDate e SettlementDate, sem
calendário), **Fixing Description** (`maturity_rate_desc`=`D-<n>`), **Exchange** (`query_source`=Bolsa de
Negociacao do Subjacente por UnderlyingAsset), Ticker=UnderlyingAsset, Quantity=TotalNotional `.2f`,
Premium Payment Date=SpotDate dd/mm/yyyy, Asian Option Average=`APLICÁVEL`/`NÃO APLICÁVEL`.
Renames i18n: col-17 Premium, 19 Unwind Amount, 20 Unwind Unit Price, 31 Fixing, 32 Fixing Description,
33 Exchange.

**Lifecycle (espelha NDF)**: `_find_intrag_opt_entry` + `/api/intrag/option/{send-file,edit,approve}`.
- edit→`Pending` (maker); approve `Pending`→`Approved` (**403 maker==checker**); send `New/Approved`→`Sent`.
- **Arquivo**: `Intrag-Option-YYYYMMDD.txt` na **mesma pasta padrão do NDF** (`INTRAG_NDF_SEND_DIR\YYYY\mm. Mmmm\dd`),
  linhas = 38 colunas separadas por `;`, agrupado por Registration Date (col data idx 3). Sufixo ` (n)` se já existir.
- **Frontend** (`intrag-option.html`): botões row Approve (só em Pending, via drawCallback) + Send + Send em
  lote (`btnSendOpt`), `_intragRowData`=`slice(3,41)` (38 cols), `_itemFromRow`, edit do modal → POST edit →
  Pending. Validado e2e.

### Pendências (atualizado seção 22)
- Colunas 17–37 e lifecycle: **feitos**. Falta só `Trade Type` (col 9) e `Redemption Value`/`Barrier Rate`/
  `Bulletin Time` (sem regra definida) — placeholders vazios.
- `INTRAG_NDF_SEND_DIR` é caminho Windows (`I:\...`) — geração de arquivo só funciona no ambiente JPM.

---

## 23. Sessão 2026-06-24 — E-mail DL aliases, dark checkbox, UI fixes, Recon upload/notfound, Intrag Opt cont.

### 23.1 E-mail .eml — saga de encoding + resolução de listas de distribuição
Sequência de fixes no `build_eml_bytes` (`otc_emails.py`) até funcionar no Outlook:
1. **Quoted-printable** (multipart/alternative, default) corrompia o HTML (`=3D`, `=C3=A7`, soft-breaks
   cortando tags) → trocado por **single-part `text/html` + `Content-Transfer-Encoding: 8bit`**.
2. **To/Cc UTF-8 cru** → Outlook lê header como Latin-1 → mojibake (`LiquidaÃ§Ã£o`).
3. **MIME-encoded** (`=?utf-8?...?=`) → Outlook **não decodifica** nome no Cc de rascunho.
4. **Causa real**: "Liquidação"/"Brazil Comm Sales" são **listas de distribuição** — um nome sem `<email>`
   não resolve num `.eml`. **Solução**: mapa `_RECIPIENT_ALIASES` (nome→destinatários reais, matched
   ASCII-folded/lowercase) + `_resolve_recipients` aplicado a To/Cc. Subject continua RFC-2047 encoded.
   - `Liquidação` → `BRSP_Settlement_Ops; brsp_financial_control; brazil_otc_settlements@jpmorgan.com; joao.hira@jpmorgan.com; latam.mumbai.acc@jpmorgan.com`
   - `Brazil Comm Sales` → `Brazil_Comm_Sales`
   - Para adicionar listas: editar o dict `_RECIPIENT_ALIASES`.
- **Formatação Premium**: `<br>` entre bloco de valores e bancário; labels bancários em negrito; conta JPM `5116003`.

### 23.2 ⚠️ Dark mode: `--ins-light-rgb` é uma cor ESCURA (37,38,48)
Sob `[data-bs-theme=dark]` o tema redefine `--ins-light-rgb` para `37,38,48` (escuro). Então
`rgba(var(--ins-light-rgb), α)` fica **escuro/invisível** no dark — foi o bug do contraste dos checkboxes.
**Regra**: para bordas/fills claros em dark mode use **branco literal** `rgba(255,255,255,α)`, não a var.
Fix aplicado em `_forms.scss` (`.form-check-input:not(:checked)` / `-light` no dark: borda .85 + fill .18).

### 23.3 Counterparty banking (continuação seção 21)
- Botões PAY/RECEIVE viraram **sólidos** (`.cp-defbtn`): cinza=não-default, azul=Default PAY (★),
  teal=Default RECEIVE (★), âmbar=pending. Chips explícitos `★ Default PAY/RECEIVE` na conta. Handler em
  `[data-defset]`.
- **Notificações** das ações de banking: detalhe inclui **SPN + nome da contraparte** (`_bank_detail`);
  clicar abre `/reference-data?spn=<n>` e a página **pré-filtra a coluna SPN** (initComplete lê `?spn=`).
- **SweetAlert** quando o próprio maker tenta aprovar (botões `data-own`, `ownApprovalAlert`) — fecha o
  editor (container único do Swal), aceitável pois a aprovação está bloqueada.

### 23.4 Intrag Option (cont. seção 22)
- Trade Type=`002`, Redemption Value=`0.00` (demais sem regra = placeholders).

### 23.5 Reconciliation Comitente
- **Upload manual**: cada um dos 3 slots agora aceita **drag-and-drop** (handler `drop` atribui o arquivo
  ao `<input>` via DataTransfer + trigger change). Texto "Clique ou arraste um arquivo".
- **"Files not found"**: `run_auto` checa cada fonte independentemente e retorna `missing:['b3_cgd','party','dcad']`;
  o Swal lista **exatamente** qual faltou e a fonte (e-mail vs drive `I:\`). Classe `ReconFilesMissing`. i18n `rc-miss-*`.
- **Date picker**: ícone de calendário visível (`ti-calendar`) dentro do campo (o `input[type=date]` é
  transparente sobreposto e escondia o ícone nativo); clique abre via `showPicker()`.

### Commits desta sessão (2026-06-23/24)
- import_dados_bancarios + CGD/bank scripts; .eml delivery + banking maker/checker; dark checkbox; default
  toggles + bell deep-link; SweetAlert own-approval; .eml fixes (QP→8bit, DL aliases); intrag-option pipeline
  + colunas + lifecycle + arquivo; recon drag-drop + missing-files + date icon.

## 24. Sessão 2026-06-24 (cont.) — Footer padrão, header intrag, notificação refdata, alinhamento tabela

### 24.1 Footer padronizado (`© 2026 OTC Tracker by JPMorgan Chase & Co.`)
- Assinatura uniformizada em todas as páginas (commit `1101b45`). Modelo único de texto/estilo.

### 24.2 Intrag — espaçamento de header + auto-load
- `intrag-ndf.html` e `intrag-option.html`: `padding-top` acima dos headers (estava "comendo" checkbox/título).
- `intrag-option`: ao entrar na página carrega automaticamente os dados de **trade date = hoje**
  (`_todayDmy()` + chip de filtro em Registration Date), paridade com a lógica do intrag-ndf.

### 24.3 Notificação de novo registro Reference Data
- `api_b3_add`: quando `table=='refdata'`, a notificação usa **page='Reference Data'** (antes saía "Index B3"),
  detalhe `SPN <n> · <counterparty> (Pending approval)`. Sino faz deep-link `/reference-data?spn=<n>`.
- `topbar.html`: `PAGE_URL['Reference Data']='/reference-data'` + parsing de `?spn=` para esse page.

### 24.4 Reference Data — alinhamento de tabela (scrollX) e colunas de controle
- Corpo desalinhado dos headers: causado por `scrollX` sem larguras fixas. Fix = `table-layout:fixed`
  + bloco de larguras `nth-child` (15 colunas) cobrindo **`#ref-data-table` E `.dt-scroll-head`/`.dataTables_scrollHead`**
  (o clone do header perde o id da tabela). Bloco no topo do `<style>` da página.
- **Pontinhos (…) nos checkboxes**: `text-overflow:ellipsis` aplicado às células de controle. Fix = escopar
  ellipsis às **colunas de dados** (`nth-child(n+3)`); colunas 1–2 (checkbox/Actions) ganham
  `overflow:visible; text-align:center; text-overflow:clip`.
- **Coluna Actions não aumentava**: `style="width:..."` inline vencia o CSS por especificidade. Fix =
  remover inline dos `<th>` de checkbox/Actions; Actions definida em **140px** via CSS.

### Commits (24)
- `1101b45` footer + recon not-found i18n · `2e5933a` intrag header/auto-load · `e883089` notif refdata
  deep-link · `1990822` align tabela refdata · `1a05be1` ellipsis/Actions refdata.

---

## 25. Sessão 2026-06-24 (cont.) — Reference Data: maker/checker em CGD + Contacts, polish do glass editor

### O que foi feito

Estendido o padrão maker/checker (já existente no Banking) para as **3 seções** do editor glass de counterparty (`reference-data.html`): **CGD**, **Banking Data** e **Contacts**. Tudo que é **adicionado ou editado** entra como `Pending` e exige aprovação por um **SID diferente** (maker ≠ checker). Edição de um item aprovado volta para `Pending` (re-aprovação).

#### Backend — `apps/pages/routes.py`
- Helpers: `_cgd_norm`, `_contacts_norm`, `_cpd_get_record`, `_contact_disp`.
  - CGD vira lista de itens `{id,value,status,maker,checker}` (status ∈ Pending|Active).
  - Contato ganha `appr` (Pending|Active) + `maker`/`checker`; `status` continua sendo o **business** Active/Inactive.
  - Dados legados (strings soltas no CGD, contatos sem `appr`) são importados como `Active` com maker/checker `IMPORT`.
- 8 endpoints novos (mesmo molde dos de Banking):
  - `/api/counterparty-details/cgd/{add,edit,approve,delete}`
  - `/api/counterparty-details/contact/{add,edit,approve,delete}`
  - Guarda `same_user` (403) quando maker == checker na aprovação; cada ação dispara `_notify_bank` (page "Reference Data", deep-link por SPN).
- `/api/counterparty-details/save` deixou de sobrescrever CGD/CONTACTS — cada seção é gerida pelos endpoints próprios (só atualiza COUNTERPARTY).

#### Frontend — `apps/templates/pages/reference-data.html`
- `_normCp` reescrito p/ devolver CGD e CONTACTS como objetos com workflow.
- Novas zonas interativas `_renderCgdZone` / `_renderContactZone` (espelham `_renderBankZone`): Add inline, badge de status, botões Approve/Edit/Delete por item, edição inline.
- Removido o modo edit/save em massa (footer agora só tem botão **Close**); as 3 zonas são sempre interativas como o Banking.

#### Notificações por seção — `apps/templates/partials/topbar.html`
- `ACTION_META`: `CGD Added/Edited/Approved/Deleted` e `Contact Added/Edited/Approved/Deleted` (ícones Lucide + cores). Deep-link por SPN herdado de "Reference Data".

#### Polish do glass editor (pedidos da sessão)
- **Dropdown select2 ultrapassa o fundo do SweetAlert**: `.cp-glass { overflow: visible }` + `border-radius` no `.swal2-html-container` p/ manter o recorte arredondado.
- **Botões confirm/cancel sólidos**: `.cp-okbtn` verde / `.cp-cxbtn` vermelho, ícone branco centralizado (também aplicado a `.cp-add-submit`/`.cp-add-cancel`); `.cp-editbtn` azul.
- **Máscara de data no CGD**: handler `input` em `.cp-cgd-val` formata dígitos → `dd/mm/yyyy` (insere `/` sozinho), além do date-picker nativo.

### Padrões identificados
- **Maker/checker por item (CGD/Contacts/Banking):** modelo canônico = itens com `{id,...,status/appr,maker,checker}`, endpoints `add/edit/approve/delete`, `edit` reseta para `Pending`, aprovação bloqueada se `maker == CURRENT_USER` (`data-own` no front + guarda `same_user` no back). Reaproveitar `bankFetch`, `flashSaved`, `ownApprovalAlert`, `_accBadge`.
- **Contato tem 2 status distintos:** `status` (business Active/Inactive, editável) ≠ `appr` (estado de aprovação). Nunca misturar.
- **select2 dentro de SweetAlert glass:** manter `dropdownParent` = popup (evita bug de foco no campo de busca) e liberar `overflow: visible` no popup p/ a lista não ser cortada.

### Arquivos modificados nesta sessão
```
apps/pages/routes.py                       ← helpers + 8 endpoints CGD/Contact + /save ajustado
apps/templates/pages/reference-data.html   ← zonas CGD/Contacts interativas, handlers, CSS, máscara de data
apps/templates/partials/topbar.html        ← ACTION_META das notificações CGD/Contact
```

---

## 26. Sessão 2026-06-25 — Novo produto **Option FXO** (página, import XLSX, Conecta, dashboard)

### O que foi feito

Criado o produto **Option FXO** de ponta a ponta, replicando o fluxo de **Option Commodities** mas para opções de **câmbio** (FX). Página própria, backend de cache próprio, parser de blotter XLSX, geração de arquivo Conecta (B3) e integração completa no dashboard.

#### Nova página — `apps/templates/pages/new_deals-opt-fxo.html`
- Réplica de `new_deals-opt-commodities.html` **sem** as colunas: `Commodities`, `Contract`, `Quoted in Cents`, `Market`, `FXConvDate`.
- **Show entries** padrão **50** (opções 50/100/150/200) — mesmo ajuste aplicado a opt-comm e ndf-comm.
- Reindexação de todos os acessos posicionais (`d[N]`, `cell(row,col)`, `this.data()[N]`) após a remoção das colunas. Pontos que escaparam dos geradores e foram corrigidos: `extractRowDeal` (índices), `this.data()[26]→[23]` (SpotDate), `this.data()[34]→[29]` (RowID).
- Link na sidenav (`/new_deals-opt-fxo`), card no **About** e entrada no **dashboard**.

#### Backend cache FXO — `apps/pages/routes.py`
- `OPT_FXO_CACHE_DIR` = `.../cache/new deals/Option/FXO` (separado de Commodities p/ rotular no dashboard).
- Endpoints próprios `opt-fxo` (save/search/PATCH/DELETE/bulk) gravando `YYYY/MM/YYYYMMDD_optfxo.json`, chaveado por **Deal+Client** (upsert).

#### Import de blotter XLSX (`Brazil_FXO_Blotter_Extended_*_YYYYMMDD.xlsx`)
- Endpoint `api_fxo_import_xlsx` (com `dry_run`) + `api_fxo_cache_batch`. Parser openpyxl.
- **Filtros de linha** (descarta se vazio): coluna **O (SPN)**, **P (End Counterparty)**, **Q (End Counterparty Description)**.
- Mapeamentos-chave: `UnderlyingAsset = Strike Currency`; `SpotDate = Premium Date (col M)` (dd/mm/yyyy); `TradeType` = VANILLA/ASIAN conforme datas de fixing; `FXHolidaySchedule = ANBIMA`; Put/Call → `Option (Put)/(Call)`.
- **Add/Edit modal**: referência agora é o **SPN** (não mais Accronym). SPN é autocomplete; preenche FX CASH Accronym/Counterparty/Tax ID via `_fxoFillFromSpn`. Subjacente filtrado por `Classe === 'TAXAS DE CAMBIO'`.
- **Dedup no import** (Deal+Client): se já existem na tabela, SweetAlert lista os duplicados → **Replace** (substitui com `Status=Amend`), **No** (descarta os dup, importa o resto), **Cancel** (não importa nada).

#### Geração Conecta (B3) — `api_fxo_send_conecta`
- Arquivo **`FXO_Banco.txt`** (mesma lógica de não-sobrescrita do opt-comm; mesmo mapping de B3-ID via `api_fxo_mapping_b3`).
- `f[2]` (Tipo Indicador) = **4**; `f[17]` (Tipo de Cotação) = **1**.
- Data de fixing: **VANILLA** → `f[19]` = última data de fixing do ativo subjacente, `f[20]` vazio; **ASIAN** → `f[19]`/`f[20]` vazios + sub-linhas `OPC 00002;2;...` com contagem de dias úteis ANBIMA entre primeira/última fixing.

#### Dashboard — `api_dashboard_stats` + `dashboard.js`
- **FXO incluído** em Deal Distribution (3ª fatia `Option FXO`, cor `#10b981`), Deal Flow Analytics (3ª barra), recent deals e filtro de produto.
- **Contagem de deals**: FXO tem **1 linha por deal** (sem perna lawton). Conjunto de contagem = `(_is_fxo and not _is_bank) or (not _is_fxo and _is_lawton)` — exclui **Banco JP Morgan** dos FXO. (Corrige o bug "fixo em 6".)
- **Top 5 Commodities → Top 5 Underlying Assets**: rótulo = `Commodities or Commodity or UnderlyingAsset` (commodities mostram o **nome** da commodity; FXO mostra a **moeda**).
- **Top 5 Clients empilhado por produto**: barra horizontal com um dataset por produto (`by_product` no backend), gradiente `hGradient`, `stack:'clients'`, legenda no rodapé. Exclui banco e lawton.
- **Aviso de prêmio D0** (SpotDate = hoje): agora escopado **apenas aos deals sendo importados agora** (snapshot `_preKeys` antes do dropzone) — aplicado a FXO **e** opt-comm.

### Padrões identificados
- **Reindexação de DataTable posicional:** ao remover colunas, auditar **todos** os acessos `d[N]`, `cell(_,N)` **e literais** `this.data()[N]`; geradores baseados em `d[` não pegam `data()[`. Validar com `node --check` no maior script inline (após stripar `{{ }}`/`{% %}`).
- **FXO não tem perna lawton:** diferente de commodities/NDF, é 1 linha por deal — a lógica de contagem/dedup do dashboard precisa tratar `_is_fxo` à parte.
- **Cache por produto em diretório próprio** (`Option/FXO` vs `Option/Commodities`) permite rotular a origem no dashboard sem campo extra.

### Arquivos modificados nesta sessão
```
apps/templates/pages/new_deals-opt-fxo.html          ← nova página FXO (import, preview, Conecta, modal por SPN)
apps/pages/routes.py                                 ← cache opt-fxo, import XLSX, Conecta FXO, dashboard FXO
apps/static/js/pages/dashboard.js                    ← pie/flow 3 séries, Top5 Underlying, Top5 Clients empilhado
apps/templates/pages/new_deals-opt-commodities.html  ← show entries 50/100/150/200, premio D0 escopado
apps/templates/pages/new_deals-ndf-commodities.html  ← show entries 50/100/150/200
apps/templates/partials/sidenav.html                 ← link FXO
apps/templates/partials/topbar.html                  ← PAGE_URL 'Opt FXO'
apps/templates/pages/index.html                      ← 'Top 5 Underlying Assets'
apps/templates/pages/about.html                      ← card FXO
apps/templates/pages/index-b3-results.html           ← lazy-init VCP/Domain (duplo header em tab scrollX oculta)
apps/static/data/translations/{en,br,es}.json        ← chaves FXO/import/dedup/underlying
```

### Commits (26)
- `0e46359` nova página FXO · `317a98d` remove Quoted in Cents + índices · `1d4d8cf` import XLSX + remove Market/FXConvDate · `d67791f` preview + Conecta + B3 mapping · `1a0aa64` Underlying=Strike Ccy, SpotDate←Premium · `258fc0f` valida Underlying contra 'TAXAS DE CAMBIO' · `41552b6` About + dashboard + animação import · `d55ba83` dashboard FXO + Top5 Underlying + Cotação=1 · `3f88916` dedup Deal+Client (Amend) · `cb99305` FXO conta exceto Banco JP + premio D0 escopado · `99cd7b2` lookup por SPN + filtro col O · `962918c` Top 5 Clients empilhado por produto.

---

## 27. Sessão 2026-06-25 (cont.) — Control Panel (hub de rotinas) + 1ª rotina: Salvar Arquivos CETIP

### O que foi feito

Criada a página **Control Panel** (`/control-panel`) — um *hub extensível* de rotinas operacionais que
**salvam arquivos para os Daily Settlements** e processos que não exigem página dedicada. A 1ª rotina é a
tradução do **fluxo Alteryx "Salvar Arquivos"** (CETIP) para Python.

#### Nova página — `apps/templates/pages/control-panel.html`
- Estilo Apple (cards com hairline border, radius 16px, hover lift). Seção **Daily Settlements** com grid
  de *routine cards*.
- **Padrão de card reutilizável:** cada card declara `data-endpoint` (POST) e opcionalmente
  `data-date-input="<id>"`. Um runner genérico `cpRunRoutine(btn)` (delegação de clique em `.cp-run-btn`)
  faz o POST, mostra loading (`ti-loader-2 ti-spin`) e o resultado via **SweetAlert** (sucesso/erro).
  Adicionar rotina futura = só inserir um card novo; o JS já cobre tudo.
- **Contrato do endpoint:** retorna `{success:true, message:'<html>'}` ou `{success:false, error:'...'}`.
- i18n: `cp-*` (en/br/es). Swal traduzido via padrão `_TRANS_CACHE` + `t()`.
- Link no sidenav (seção *Apps*, após Electronic Inventory, ícone `sliders-horizontal`).

#### Rotina 1: Salvar Arquivos CETIP — `apps/pages/routes.py`
Tradução fiel do `.yxmd` (Directory → Filter → DynamicInput → Formula → Select → DbFileOutput → Email).
- Endpoint `POST /api/control-panel/cetip-settlement` (body opcional `{date:'YYYY-MM-DD', send_email:bool}`;
  **default = D-1 ANBIMA** via `_prev_anbima_bizday(now)` — pula fim de semana e feriados ANBIMA). O input
  da página é pré-preenchido com esse D-1 (passado pelo route via `cetip_default_date`).
- **Fonte:** `CETIP_SOURCE_ROOT\{YYYY}\{MM}\{DD}` (pasta diária da B3). **Destino:**
  `CETIP_DEST_ROOT\{sub}\20{YY}\{MM}` — **ano/mês vêm da data embutida no nome do arquivo**, não de hoje.
- **`_CETIP_RULES`** = 8 regras (1 por branch do Alteryx). Cada regra: `match` (predicado no FileName =
  expressão do Filter), `date_start` (offset 0-based do YYMMDD no nome: **6** p/ `OPCAO_*`, **8** p/ os
  `CETIP21`), `dest_name(ref)` (renomeia p/ `73760_{YYMMDD}_{TIPO}`), `dest_sub` (subpasta destino).
  Tipos: DPOSICAO_C21→`Arquivos Posiçao`, DPOSICAO-SWAP→`Posiçao`, OPCAO DPOSICAO→`Posiçao`,
  OPCAO DMOVIMENTO→`Movimento\OPÇÃO` (exclui `_15H00`/`_18H30`), DMOVIMENTO_C21→`Movimento\TERMO`,
  DMOVIMENTO-SWAP→`Movimento\SWAP`, DFLUXO_SWAP→`Posiçao` (vira `_DFLUXO.CETIP21`), DOPERACOES→`Posiçao`.
  ⚠️ Nomes de pasta acentuados são literais e devem bater 1:1 (`Posiçao`, `OPÇÃO`).
- **`_cetip_save_file`**: lê o arquivo como Latin-1 (CodePage 28591 do Alteryx) e reescreve com CRLF —
  Latin-1 é mapa byte-a-byte (conteúdo preservado); só normaliza quebras de linha p/ CRLF (= o que o KPI
  espera). **Não** escreve BOM (28591 não é Unicode → Alteryx ignora WriteBOM). [decisão consciente]
- **`_send_cetip_confirmation`**: espelha o tool Email (assunto "Arquivos CETIP salvos!", SMTP relay JPM,
  best-effort). Notificação `_create_notification('CETIP Files Saved','Control Panel', ...)`.
- Loop = 1 passada por regra (espelha branches independentes do Alteryx: 1 arquivo pode ir p/ >1 destino).

#### Notificação — `apps/templates/partials/topbar.html`
- `ACTION_META['CETIP Files Saved']` (ícone `file-export`, `bg-success`) + `PAGE_URL['Control Panel']`.

### Padrões identificados
- **Control Panel é a casa das "rotinas sem página":** processos batch/file-saving que antes eram Alteryx
  entram aqui como cards. Reaproveitar `cpRunRoutine` + contrato `{success,message|error}`.
- **Alteryx → Python:** `Substring(s,start,len)` é 0-based = `s[start:start+len]` (idêntico ao Python).
  Filtros `Contains` = `in`; `!Contains` = `not in`. CodePage 28591 = Latin-1 (byte-exato).
- Caminhos `I:\...` (CETIP_SOURCE_ROOT/DEST_ROOT) só funcionam no ambiente JPM, como INTRAG_NDF_SEND_DIR.

### Pendências
- O XML colado veio **truncado** após o branch DOPERACOES; mapeei 8 tipos. Se o fluxo real tiver tipos
  adicionais (ex.: variações `_15H00`/`_18H30`, outros DMOVIMENTO), basta acrescentar regras em `_CETIP_RULES`.
- Confirmar com o usuário o **formato exato do nome dos arquivos-fonte** (validar offsets 6/8) e se o
  downstream exige BOM no output (hoje não escrevemos BOM).

### Arquivos criados/modificados nesta sessão
```
apps/templates/pages/control-panel.html        ← CRIADO (hub + card CETIP + runner genérico)
apps/pages/routes.py                           ← rota /control-panel + _CETIP_RULES + helpers + endpoint
apps/templates/partials/sidenav.html           ← link Control Panel (Apps)
apps/templates/partials/topbar.html            ← ACTION_META + PAGE_URL da notificação CETIP
apps/static/data/translations/{en,br,es}.json  ← chaves control-panel + cp-*
```

## 28. Sessão 2026-06-25 (cont.) — Settlement Forecast (Alteryx→Python) + gráficos Chart.js diários

### O que foi feito

Tradução do fluxo Alteryx **"Settlement Forecast v2"** para Python e novo card **Settlement Forecast** no
Control Panel (à direita do File-Saving). Projeta as liquidações dos **próximos 14 dias úteis (ANBIMA) a
partir de hoje**, quebradas por **produto** e por **entidade**, e envia relatório por e-mail à OTC Ops BR.

#### File-Saving agora também gera JSONs tidy — `apps/pages/routes.py`
- Ao rodar **Salvar Arquivos CETIP**, além de copiar os arquivos, grava JSONs em
  **`apps/static/data/cache/b3 files/{NDF,Option,Swap}/`** (NDF=TER, Option=OPC, Swap=posição/fluxo/prêmio).
  Pasta no `.gitignore` (`b3 files/**/*.json`).
- `_CETIP_RULES` ganhou config `json` em 5 regras + nova regra **DAGENDAPREMIOS** (é de Swap).
- **TER e OPC têm header na linha 1**; arquivos de **SWAP são headerless** → headers-padrão fixos em
  `_B3_SWAP_HEADERS_RAW` (swap_position tem nomes duplicados → dedupe p/ `_2`/`_3`).
- `_b3_export_json(...)`: lê Latin-1, monta list-of-dicts, dedup de header, aplica **filtros de conta**
  (comparação só-dígitos via `_digits`) p/ não duplicar. Filtros: TER col B *Código da Parte* ∈
  {73760009, 04880006}; OPC col E *Parte (conta)* = 73760009; SWAP pos col D / Fluxo col C / DAGENDA *Parte*
  ∈ {73760009, 04880006}. **O que não bate é excluído do JSON.**

#### Taxonomia de produto (8 produtos)
`NDF Moeda, NDF Commodities, Opt FXO, OPT Comm, OPT EDG, SWAP CEM, SWAP EDG, SWAP CEMHYB`.
- **NDF**: col M *Classe do Ativo Subjacente* → COMMOD/MERCAD = NDF Commodities, resto = NDF Moeda.
- **OPC**: col N *Classe do Ativo Subjacente* → TAXA DE CAMBIO/MOEDA = Opt FXO, Commodities = OPT Comm, resto = OPT EDG.
- **SWAP**: col *Código Identificador* → CEM / EDG / CEMHYB.
- Entidades: `_FCST_ENTITY_MAP` 00041007→LAWTON, 04880006→MGT, 85398005→ATACAMA.

#### Backend forecast — `apps/pages/routes.py`
- `_FORECAST_SOURCES` (5 fontes) com tokens de campo resolvidos **por nome** (case-insensitive "contains"),
  robusto a variação posicional. `_forecast_spine()` = próximos 14 dias úteis ANBIMA a partir de hoje.
- `_forecast_collect` loga diagnóstico por arquivo: `[forecast] <fonte>: N rows, M counted | date=... entity=... product=...`.
- Endpoints: `POST /api/control-panel/settlement-forecast/data` (JSON do forecast) e
  `.../email` (recebe `{date, images:{by_product, by_entity}}`, recalcula e envia).
- E-mail **To = `brazil.otc.ops@jpmorgan.com`** (`CETIP_OTC_OPS_EMAIL`), assunto "Settlement Forecast".

#### Gráficos (Chart.js, NÃO ApexCharts/matplotlib) — `apps/static/js/pages/settlement-forecast.js`
- **Mesmo modelo do "Deal Flow Analytics"** do index, porém **diário**. Stacked bar, `vGradient`, cores Apple,
  `maxBarThickness`, `borderRadius`. Y máx **900**.
- Plugin `valueLabels`: **labels sempre visíveis** (valor por segmento em branco quando o segmento é grande +
  **badge estilo tooltip** com o total no topo de cada barra) — aparecem na imagem do e-mail (não por hover).
- Plugin `whiteBg`: fundo branco no PNG (não sai transparente/preto).
- **Render→PNG client-side** (path A): a página renderiza em canvas offscreen (`#fcstStageProduct`,
  `#fcstStageEntity`), exporta `canvas.toDataURL('image/png')` e o backend embute via `cid` no e-mail.
  Tudo disparado pelo **botão Run** do card (`runForecast`): fetch /data → render→export → POST /email.

#### Dashboard — `apps/static/js/pages/dashboard.js` + `index.html`
- "Recent Deals" **substituído** pelo gráfico de **forecast por produto** (`#forecast-product-chart`,
  `loadForecastChart()`/`buildForecastProductChart()`, mesmo estilo Deal Flow com hover tooltip).

#### Control Panel — `apps/templates/pages/control-panel.html`
- Layout em **2 colunas** (`row g-3 g-xl-4`): esq. = header *Daily Settlements / File-Saving Routines* + card
  CETIP; dir. = header *Forecasts & Reports / Settlement Reporting* + card Settlement Forecast.
- E-mail HTML: `email-template-settlement-forecast.html` (header gradiente, banner de data, 2 gráficos via cid;
  **sem tabelas e sem donut Product Mix**). ⚠️ Jinja: usar `e['values']` (não `e.values` → colide com dict.values).

### Padrões identificados
- **Gerar JSON tidy no momento do File-Saving** (campos nomeados + filtros de dedup) é mais robusto p/ gráficos
  do que reparsear TXT/CSV depois. Resolução de campo **por token de nome** evita quebra por mudança de coluna.
- **Gráfico .js → imagem no e-mail sem headless browser:** renderiza no canvas do cliente e exporta PNG (path A).
- Reaproveitar helpers de Chart.js do dashboard (`vGradient`, `hexToRgba`, `ins`, `premiumTooltip`).

### Pendências / próxima sessão
- **Testar no ambiente JPM:** rodar Salvar Arquivos CETIP (regenera JSONs com filtros) → Settlement Forecast.
- Se algum produto/entidade vier vazio, ajustar tokens em `_FORECAST_SOURCES` / colunas dos filtros em
  `_CETIP_RULES.json` com base nos logs `[forecast] ...`.
- `forecast_charts.py` (matplotlib) e deps `matplotlib`/`seaborn` ficaram **não usados** (path A venceu).

### Arquivos criados/modificados nesta sessão
```
apps/pages/routes.py                                       ← _b3_export_json + json em _CETIP_RULES + backend forecast + 2 endpoints
apps/static/js/pages/settlement-forecast.js               ← CRIADO/reescrito p/ Chart.js (stacked diário, valueLabels, export PNG)
apps/static/js/pages/dashboard.js                         ← gráfico forecast por produto no index
apps/templates/pages/control-panel.html                   ← layout 2 colunas + card Settlement Forecast + canvas offscreen
apps/templates/pages/index.html                           ← Recent Deals → card de forecast
apps/templates/pages/email-template-settlement-forecast.html ← CRIADO (e-mail só com os 2 gráficos)
apps/pages/forecast_charts.py                             ← CRIADO (matplotlib, fallback não usado)
apps/static/data/translations/{en,br,es}.json             ← cp-sec-fc-*, cp-r-fcst-*, dash-forecast-*
.gitignore                                                ← b3 files/**/*.json, alteryx_flow.py, _chart_preview/
requirements.txt                                          ← matplotlib/seaborn (não usados)
```

---

## 29. Sessão 2026-06-25/26 — Update Contacts, DB lazy init, boot debug/prod, forecast latest, swap dedup, NDF-edit fix, FXO→Intrag, role cards

Bloco de melhorias e correções espalhado por 4 commits: `21acb18`, `0209b70`, `75626df`, `890d9aa`.

### Dashboard / About / E-mails (`21acb18`)
- **Filtro de produto no Settlement Forecast do index**: dropdown default **All** + uma opção por produto
  (`_forecastProductFilter`, `populateForecastFilter`, `syncForecastFilterUI`) em `dashboard.js` +
  `#fc-product-menu` no `index.html`.
- **Linha "Total" nos tooltips** do index (forecast E deal flow): callback `totalFooter(items)` somando
  `it.parsed.y`, ligado via `callbacks.footer`; estilo do footer no `premiumTooltip`.
- **about.html**: 4 novos cards de feature (Control Panel `ti-adjustments-horizontal` — *atenção: `ti-sliders-horizontal`
  não existe no Tabler*, é nome Lucide; Settlement Forecast, Reference Data, Intrag) + hero generalizado p/
  "OTC Derivatives" (não só commodities).
- **Padronização de e-mails**: assinatura única `Regards,\nOTC Tracker — Brazil OTC Operations` + footer
  automático, **corpo sempre em inglês** (templates `email-template-settlement-forecast.html` e
  `email-template-cetip-saved.html`).
- **Card "Update Contacts" no Control Panel** (seção Reference Data): transforma `scripts/import_client_contacts.py`
  em função nativa `_import_client_contacts(filename, raw_bytes)` + helpers (`_cc_read_rows` openpyxl/csv,
  `_cc_cell`, `_cc_parse_rules`, `_CONTACT_RULE_MAP`); endpoint `POST /api/control-panel/import-contacts`;
  handler `cpRunUpload(btn)` (FormData). **Regra de import**: agrupa por SPN, **só importa linhas Ativas**
  (`_cc_cell(row, _CC_ACTIVE).upper() == 'A'`); SPN que casa → CONTACTS substituídos; SPN só no JSON →
  intocado; SPN só na planilha → novo registro. Colunas: SPN=1,NAME=2,ACTIVE=3,CONTACT=4,PHONE=5,EMAIL=6,RULE=7;
  `DATA_START_ROW=5`.

### DB lazy init + lock fix (`0209b70`)
- **Erro no Windows JPM** (`DuckDB IOException "file used by another process"` + `RuntimeError: release unlocked lock`):
  o supervisor do reloader abria o DuckDB no import. Corrigido com **init lazy** — `_ensure_db_initialized()`
  (flags `_db_init_done`/`_db_init_lock`/`_db_init_tls`) chamado no topo de `get_db_connection()` em vez de
  `init_db()` eager no import. Removido `release()` duplo do lock no branch de retry da IOException.

### Boot debug/prod + flask run (`21acb18` / `75626df`)
- `run.py`: `DEBUG = os.getenv('DEBUG','True') not in ('0','false','no','off')`.
- **`start.bat`** (criado): `start.bat` = debug (`python run.py`, 8050); `start.bat prod` = produção
  (`waitress-serve --host=0.0.0.0 --port=5005 run:app`). **`.flaskenv`** criado (FLASK_APP/HOST/PORT).
  `waitress==3.0.0` no requirements. **Porta 8050** (5000 bloqueada pelo AirPlay do macOS); `flask run` liga só
  em 127.0.0.1 → preferir `python run.py` (0.0.0.0).

### Forecast: dashboard "latest" vs Control Panel estrito (`75626df`)
- **Dashboard** usa o **JSON mais recente disponível** (D-1 → D-2 → …): `_forecast_has_files(ref)`,
  `_forecast_latest_ref(max_back=10)`; endpoint `/data` aceita `mode:'latest'`. **Control Panel** continua
  **exigindo D-1** (modo estrito). `index.html` mostra `#forecast-asof` com a data efetiva.

### Settlement Forecast: contagem de swaps por Tipo de Contrato (`890d9aa`)
- No `swap_pos`, **Tipo de Contrato = 1** (fluxo de caixa) → conta **só pelo arquivo de fluxo**;
  **Tipo = 2** (bullet/pagamento final) → conta pela **col M (Data vencimento) do arquivo de posição**.
  Implementado via `'count_where': (['tipo de contrato', ...], {'2'})` na fonte + gate por linha em
  `_forecast_collect` (normaliza sufixo `.0`) antes do check de data. Evita dupla contagem.

### Reference Data: editar contas bancárias (`890d9aa`)
- Faltava botão de edição nas contas bancárias do editor de Counterparty. Adicionados `_bankEditForm(a)`
  (select2 banco + agência + conta), `_renderBankZone(bk, editId)`, botão lápis `cp-acc-edit` e endpoint
  `POST /api/counterparty-details/banking/account/edit` (reseta status Pending, maker=sid, checker='').

### NDF Comm: persistência/notificação de edição row-level (`890d9aa`)
- **Bug**: o save da edição inline disparava PATCH e **ignorava a resposta** (só `.catch()`); backend
  `_find_ndf_deal_in_cache` fazia match exato → **404 fantasma** por diferença de espaço → não persistia nem
  notificava. **Fix**: (1) backend trim-tolerante (`.strip()` nos dois lados em Deal+Client, 6 lookups);
  (2) save-edit checa `res.ok` e cai em **`POST /cache?notify=1`** com `rowDataToNdfDeal` no fallback;
  (3) `notify=1` cria notificação **"Deal Updated / NDF Comm"**; (4) toast de erro se tudo falhar.

### Opt FXO → Intrag Option (`890d9aa`)
- Deals **Opt-FXO** de **Banco J.P. Morgan** que chegam a **Success** geram entry no **mesmo** `intrag_opt.json`
  do opt-comm. Reuso de `_save_intrag_opt_entry(deal, is_fxo=True)` — **7 campos sobrescritos p/ FXO**:
  INFORMATION SOURCE=**SISBACEN**, EXCHANGE(query_source)=**BACEN**, TICKER=**USD**, CURRENCY SYMBOL=**USD**,
  BULLETIN=**3**, BULLETIN TIME=**18:00**, SISBACEN CURRENCY CODE=**220**; resto = mesma lógica do opt-comm.
  Gateado por `_maybe_save_intrag_fxo(deal)` e engatado nos **2 caminhos** que põem FXO em Success: PATCH manual
  (`/api/new-deals/opt-fxo/cache/<id>`) e mapeamento B3 (`api_fxo_mapping_b3`). FXO não tem `QuotedInCents`
  (default NO → sem /100) nem `Commodities`/Subjacente (campos sobrescritos), então a lógica compartilhada
  funciona sem ajuste.

### User Roles: animação de feedback nos cards (`890d9aa`)
- Cards de role com `.role-card`: **hover-lift** (`translateY(-4px)` + sombra, ease-out
  `cubic-bezier(0.23,1,0.32,1)` 200ms, só `@media (hover:hover)`) + **press feedback Apple** (`:active`
  `scale(0.97)` 120ms). **Botões "Details" removidos** de cada card (mantido o contador de membros).

### Padrões / lembretes
- `_save_intrag_opt_entry` agora serve opt-comm e FXO via flag `is_fxo` — FXO e comm compartilham o
  `intrag_opt.json` e aparecem juntos na página intrag-option (sem mudança de frontend).
- `scripts/commit-push.sh` remove só o **bloco** `/dev-login`, **não** a linha do allowlist
  (`pages_blueprint.dev_login` em `_LOCK_ALLOWED_ENDPOINTS`) — ao commitar manualmente, **stripar as duas**.

### Arquivos modificados (commit `890d9aa`)
```
apps/pages/routes.py                              ← FXO→Intrag (is_fxo), NDF-edit fix, banking edit, swap dedup
apps/pages/otc_emails.py                          ← correção de aliases de destinatários
apps/templates/pages/users-roles.html            ← .role-card (hover+press), remove Details
apps/templates/pages/new_deals-ndf-commodities.html ← save-edit com res.ok + fallback POST /cache?notify=1
apps/templates/pages/reference-data.html          ← botão/forms de edição de conta bancária
apps/templates/partials/topbar.html               ← ACTION_META (Bank Account Edited, etc.)
apps/templates/pages/intrag-option.html           ← ajuste manual
apps/static/data/translations/{en,br,es}.json     ← swal-save-failed
```

---

## 30. Sessão 2026-06-29 — Scripts de boot (.bat) split, ícones de notificação, Forecast (2 datas + rótulos Option), export de usuários, B3 JSON por data + Operations, Settlement Net Type

Conjunto de melhorias/correções. Commits: `882c7c2`, `3d2ebbb`, `0450753`, `a7190d3`, `8b8afd0`,
`7ca45c8`, `68d54ec`, `b8df645`, `fada183`, `e8ac551`, `944c6ff`, `5d0acc5`.

### Scripts de boot Windows: split debug/prod + robustez (`882c7c2`, `3d2ebbb`, `0450753`)
- **`start.bat` removido**; substituído por **`start-debug.bat`** (DEBUG, Werkzeug, porta **8050**) e
  **`start-prod.bat`** (PRODUÇÃO, **waitress**, porta **8050** — antes era 5005; ajustado a pedido).
- **Detecção de python ancorada em `%~dp0`** (`set "BASE=%~dp0"`): procura `Scripts\python.exe` (venv na raiz do
  projeto — caso da máquina JP, `C:\Users\E930179\ds\OTCTracker`), depois `OTCTracker\Scripts`, `.venv311`, `.venv`,
  e por fim `python`/`py` do PATH. **Não depende do `cd`** (perfil em drive de rede do JP quebrava o relativo).
- **`pip install -r requirements.txt` no boot, best-effort**: `--timeout 10 --retries 1`; se o pypi estiver
  bloqueado (rede JPM), **avisa e continua** com o que já está no venv. Arg **`noinstall`** pula a instalação.
- ⚠️ O venv da máquina JP fica na **raiz do projeto** (`<proj>\Scripts\python.exe`), não em subpasta.

### Ícones de notificação (Lucide ≠ Tabler) (`a7190d3`)
- O map de notificações do `topbar.html` usa nomes **Lucide** (`<i data-lucide=...>`). `CETIP Files Saved` usava
  `file-export` e `Contacts Updated` usava `address-book` — **inexistentes no Lucide** → só a bolinha colorida, sem
  ícone. Corrigido p/ **`file-output`** e **`book-user`**. (`chart-bar` do Forecast já era válido.)

### Settlement Forecast: opções contam em 2 datas (`8b8afd0`)
- A fonte **`opc`** (opções FXO/Comm/EDG) agora conta cada contrato na **Data do Vencimento (col M)** **e** na
  **Data de Liquidação do Prêmio (col BN)**. Novo `'date2'` na fonte + `'date2_index': 65` (fallback por índice).
- `_forecast_collect`: junta as datas num `set` de slots (dedup quando caem no mesmo dia útil); conta por produto
  **e** entidade em cada data. Resolução de coluna virou **insensível a acentos** (`_fcst_norm` via `unicodedata`).
- Cobre **index e Control Panel** (mesmo backend `_forecast_payload`).

### Forecast: rótulos OPT/Opt → Option (`7ca45c8`, `68d54ec`)
- `Opt FXO`/`OPT Comm`/`OPT EDG`/`OPT Equities` → **`Option FXO`/`Option Commodities`/`Option EDG`/`Option Equities`**.
  Alterado em `_FCST_PRODUCT_ORDER`, `_fcst_opt_class_product`, `_fcst_option_product` (routes) + color maps
  `dashboard.js` e `settlement-forecast.js`. **Não** mexe em `Opt FXO` como **nome de página** (menu/notificações).

### Script export de usuários (`b8df645`)
- **`scripts/export_users_excel.py`**: extrai a tabela `users` do `Users_OTCTracker.db` (DuckDB) → Excel em
  `~/Downloads/users_export_<ts>.xlsx` (abas **Users** + **Summary** por Status/Role). Abre **read-only** com
  **fallback de cópia** (`.db`+`.wal` → temp) se o app estiver segurando o lock do DuckDB.

### Reference Data: alinhamento do badge de contato (`fada183`)
- Badge **Active** do contato desalinhado (herdava `margin-top:6px` de `.cp-acc-main .badge`). Nome+badge agora num
  wrapper flex centralizado **`.cp-acc-namebadge`** (mesmo padrão do CGD).

### B3 JSON por ano/mês/dia + export de Operations (`e8ac551`)
- Os JSONs do cache **`b3 files`** passam a ser gravados em **`<categoria>/YYYY/MM/DD/`** (antes soltos na pasta do
  produto): helper **`_b3_date_subpath(dref)`** (`YYMMDD → YYYY/MM/DD`). `_b3_export_json` recebe `dref`; leitores
  do forecast (`_forecast_collect`, `_forecast_has_files`) ajustados.
- **Operations passou a gerar JSON** no fluxo de file-saving: regra DOPERACOES ganhou `json` config (categoria
  **Operations**, headerless → header padrão `_B3_SWAP_HEADERS['operations']` com **37 colunas** fornecidas pelo
  usuário). `Operations/.gitkeep` criado (os `*.json` são gitignored, gerados em runtime).
- ⚠️ JSONs antigos na estrutura plana deixam de ser lidos; basta rodar **Save CETIP Files** de novo (regerado diário).

### Intrag NDF: largura coluna Trading Unit (`944c6ff`)
- `#intrag-ndf-table` col 22 (Trading Unit): **120px → 160px** (edição manual do usuário).

### Reference Data: seção **Settlement Net Type** por counterparty (`5d0acc5`)
- Nova seção no editor de Counterparty (entre CGD e Banking): **Settlement Net Type** ∈ {**Total Net**, **Pay/Rec**,
  **No Net**}, **padrão Total Net**. Fluxo **maker/checker** idêntico ao CGD: editar → **Pending**; aprovar exige
  **outro SID** (`same_user` bloqueia) → **Active**.
- **Backend**: `_net_norm` + `_CP_NET_TYPES`; `NET` normalizado no `_cpd_get_record` (e no novo-registro default);
  endpoints **`/api/counterparty-details/net/edit`** (valida valor, status=Pending, maker=sid) e
  **`/net/approve`** (guard same_user, status=Active, checker=sid). Notificações **`Net Type Edited`/`Approved`**.
- **Frontend** (`reference-data.html`): `_renderNetZone`/`_netFormRow`, `var netEditing`, `refreshNetZone`,
  handlers `cp-net-edit`/`cp-net-edit-save`/`cp-net-edit-cancel`/`cp-net-approve`, `syncCache` inclui `NET`,
  normalização em `_normCp` (legacy → Total Net/Active). Modelo em CounterpartyDetails.json:
  `NET: {value,status,maker,checker}`.
- **Topbar**: ícones das notificações `arrow-left-right` (Edited/warning) e `badge-check` (Approved/success).
- **i18n**: `rd-cp-net` em en/br/es. Testado end-to-end (edit→Pending, valor inválido→400, approve self→403
  same_user, approve outro→Active, persistido).

### Padrões / lembretes
- **Nomes de ícone de notificação são Lucide** (`data-lucide`), não Tabler — validar contra `lucide.min.js`
  (PascalCase) antes de usar (ex.: `file-output`, `book-user`, `arrow-left-right`, `badge-check`).
- Rótulos do Forecast são **compartilhados** entre index/Control Panel/e-mail (vêm do backend `_forecast_payload`).
- Dev server **sem reloader ativo** (máquina local): após editar `routes.py`, **reiniciar** para registrar rotas
  novas (durante esta sessão os endpoints `net/*` davam 404 até reiniciar; confirmados no `url_map` de app novo).

### Arquivos modificados (sessão)
```
start-debug.bat / start-prod.bat (start.bat removido)  ← boot split + venv %~dp0 + requirements best-effort
scripts/export_users_excel.py                          ← novo: export Excel de usuários (DuckDB read-only + copy fallback)
apps/pages/routes.py                                   ← forecast 2 datas + _fcst_norm; rótulos Option; b3 json YYYY/MM/DD + Operations; Settlement Net Type (endpoints + _net_norm)
apps/templates/pages/reference-data.html               ← badge contato alinhado; seção Settlement Net Type
apps/templates/pages/intrag-ndf.html                   ← largura Trading Unit 160px
apps/templates/partials/topbar.html                    ← ícones CETIP/Contacts + Net Type Edited/Approved
apps/static/js/pages/dashboard.js                      ← color map rótulos Option
apps/static/js/pages/settlement-forecast.js            ← color map rótulos Option
apps/static/data/translations/{en,br,es}.json          ← rd-cp-net
apps/static/data/cache/b3 files/Operations/.gitkeep    ← nova categoria
```

---

## 31. Sessão 2026-06-30 — Badge "Missing Counterparty" (New Deals) + arredondamento da última barra empilhada (index)

### A) Missing Counterparty nas 5 páginas de New Deals
Espelha o padrão **Missing Index B3**, mas para contrapartes **não cadastradas em `RefData.json`**. Aparece nas
páginas: **opt-commodities, ndf-commodities, opt-fxo, ndf-fwdstart, ndf-otherpublisher**.

- **Módulo compartilhado** `apps/static/js/missing-counterparty.js` (`window.MissingCounterparty.init(cfg)`),
  incluído via `<script>` em cada página. Evita duplicar ~120 linhas com índices diferentes ×5.
- **Match:** contraparte registrada sse **SPN** (normalizado, zeros à esquerda) **ou Accronym** (COMMODITIES ou
  FX CASH) casar com algum registro de RefData. Se nenhum casar e houver identificador → **missing**. (comm/ndf
  enriquecem por Accronym; FXO por SPN — quando não casa, as colunas de contraparte ficam vazias.)
- **Badge** (`bg-danger rounded-pill`, `data-lang="badge-missing-cp"`) é **DOM-only** (nunca toca `cell.data()`),
  então **coexiste** com o Missing Index B3 (que faz swap do `data()` do Status). Regra: chamar `_cpRefresh()`
  **sempre depois** de `refreshAllMissingBadges()` em todos os call sites (drawCallback, data-load, load do RefData).
- **Onde aparece:** Status (col 2, append) + colunas de contraparte **enriquecidas/vazias** (não a coluna-chave):
  - opt-comm / ndf-comm: info `[8,10,11]` (SPN, Client, TaxID); chave = Accronym(9).
  - opt-fxo: info `[9,10,11]` (Accronym, Client, TaxID); chave = SPN(8).
  - ndf-fwdstart / ndf-otherpublisher: info `[9,11,12]` (SPN, Client, TaxID); chave = Accronym(10).
- **Registrar + reload:** edit/approve em linha *missing* abre Swal → **Reload Data** (`reloadAndEnrich`: refetch
  RefData, **re-enriquece** SPN/Client/TaxID/Accronym de cada linha e remove o badge) ou **Go to Reference Data**
  (`/reference-data`). Guards adicionados no `.btn-row-edit` e no branch `currentStatus==='Pending'` do approve.
- **i18n:** `badge-missing-cp`, `swal-missing-cp-title`, `swal-missing-cp-html`, `swal-reload-data`,
  `swal-goto-refdata` em en/br/es.
- **Wiring por página (6 edições):** include do script; `_cpRefresh()` após o RefData load, no drawCallback e no
  data-load (depois do B3); bloco `_cp()`/`_cpRefresh()` antes do handler de edit (config de colunas/`acrField`);
  guards em edit e approve.

### B) index.html — última barra empilhada com ponta arredondada (`dashboard.js`)
- **Problema:** `borderRadius` estático por dataset só arredonda se o produto for o **último dataset**, não o
  último **visível** de cada barra (varia por barra conforme produtos com valor 0).
- **Fix:** helper `stackEndRadius(R, orientation)` (scriptable borderRadius) + `_lastVisibleDatasetAt(chart,i)`
  (`chart.isDatasetVisible`) — arredonda só a ponta externa do **segmento de topo visível** de cada barra, com
  `borderSkipped:false`. Aplicado em **Settlement Forecast** (`vertical`, topo) e **Top 5 Clients** (`horizontal`,
  direita). (Deal Flow Analytics tem o mesmo padrão estático nas linhas 175-177 — não pedido, não alterado.)

### Padrões identificados
- **Badge cross-cutting coexistente:** quando duas lógicas de badge disputam a mesma célula (Status), manter uma
  **DOM-only** (append/remove `.missing-cp-badge`) e garantir ordem de execução (a DOM-only roda por último). Evita
  refatorar o swap de `data()` da lógica existente.
- **Stacked bar "pill end" no Chart.js:** usar `borderRadius` scriptable + `isDatasetVisible` para arredondar só o
  topo **visível** por barra; `borderSkipped:false` + objeto de cantos por orientação (vertical=top, horizontal=right).

### Arquivos criados/modificados nesta sessão
```
apps/static/js/missing-counterparty.js                 ← CRIADO (módulo compartilhado do badge)
apps/templates/pages/new_deals-opt-commodities.html    ← include + wiring (6 pontos)
apps/templates/pages/new_deals-ndf-commodities.html    ← include + wiring (6 pontos)
apps/templates/pages/new_deals-opt-fxo.html            ← include + wiring (6 pontos)
apps/templates/pages/new_deals-ndf-fwdstart.html       ← include + wiring (6 pontos)
apps/templates/pages/new_deals-ndf-otherpublisher.html ← include + wiring (6 pontos)
apps/static/js/pages/dashboard.js                      ← stackEndRadius/_lastVisibleDatasetAt + 2 charts
apps/static/data/translations/{en,br,es}.json          ← badge-missing-cp + swal-missing-cp-* + swal-reload-data/goto-refdata
```
> ⚠️ Validado por sintaxe (`node --check`, JSON). **Não testado em runtime** (precisa de deal com contraparte
> realmente fora do RefData para ver o badge, e do index renderizado para o arredondamento).

---

## 32. Sessão 2026-06-30 (cont.) — Página Accrual → Swap (classificação por LOB) + Deal Flow rounding

### A) Deal Flow Analytics — mesmo fix de arredondamento (`dashboard.js`)
- A pedido do usuário, o `borderRadius` estático das 3 séries do **Deal Flow Analytics** (NDF Comm / Option Comm /
  Option FXO, `stack:'deals'`) foi trocado por `stackEndRadius(6, 'vertical')` + `borderSkipped:false` (mesmo helper
  da seção 31). Agora a ponta arredondada fica sempre no topo visível de cada barra.

### B) Nova página **Accrual → Swap** (`/accrual-swap`)
Página nova (skill **emil-design-eng** + `DESIGN-apple.md`) que importa o **VCP** e separa cada swap por LOB.

- **Template** `apps/templates/pages/accrual-swap.html` (Apple Design Language + motion Emil):
  - **4 widgets de contagem** (CEM, EDG, Hybrids, Commodities) — hairline 18px, hover-lift gated `@media(hover)`,
    stagger-in, **count-up** (ease-out cubic) ao atualizar.
  - **Dropzone slim/minimalista** (HTML5 nativo, max-width 560px, dashed; estados `is-drag`/`is-busy` com spinner) —
    propositalmente mais enxuto que o Dropzone/Filepond das páginas de New Deals.
  - **4 tabelas DataTables** (uma por LOB) com **filter row por coluna** (2ª linha do thead + `orderCellsTop`),
    **Clear filters**, **Columns** (dropdown de show/hide próprio, sem depender de `buttons.colVis`) e
    **show entries 50/100/150/200** (default 50).
  - i18n via `data-lang` (estático) + `t()`/`_TRANS` (dinâmico injetado pós-i18n global).
- **Sidenav** (`partials/sidenav.html`): nova seção colapsável **Accrual** (ícone Lucide `percent`) com sub-item
  **SWAP → /accrual-swap**, inserida antes de *Live Position*.
- **Backend** (`routes.py`): rota `GET /accrual-swap` + endpoint `POST /api/accrual-swap/process`. Pipeline:
  1. Lê o arquivo (`_cc_read_rows`, openpyxl/csv). **Headers na linha 9** (`_ACC_HEADER_ROW`).
  2. **Coluna A**: remove `#`. **Coluna K**: mantém só as contas-casa `73760.00-9` e `04880.00-6` (compara por dígitos).
  3. Junta o contrato (col A) ao **último JSON de posição swap salvo** (`_swap_pos_latest_records` → `Swap/YYYY/MM/DD/
     73760_{YYMMDD}_DPOSICAO-SWAP.json`), lê o campo **`Código Identificador`** e classifica via `_accrual_lob`
     (CEMHYB/HYB→Hybrids, COMM→Commodities, EDG→EDG, CEM→CEM — **ordem importa**, CEMHYB antes de CEM).
  4. Cada tabela mantém **colunas A,F,K,L,N,Q,R,T** (`_ACC_KEEP_COLS=[0,5,10,11,13,16,17,19]`); contagem por LOB → widgets.
  - Join key = `Contrato` do swap_position (resolvido por nome exato, evitando colidir com `Tipo de Contrato`), com
    fallback por dígitos. Retorna `{headers, tables, counts, ref_date, diagnostics}` (diagnostics = total/kept/matched).

### Padrões / pontos de atenção
- **Ícones de notificação/menu são Lucide** (`data-lucide`, kebab); o bundle guarda PascalCase — `percent`→`Percent`,
  `columns-3`→`Columns3`, `filter-x`→`FilterX`, `loader-2`→`Loader2` (todos válidos).
- **swap_position headers** têm nomes duplicados (dedupe `_2`/`_3` no `_b3_export_json`), mas `Contrato` e
  `Código Identificador` são únicos → referência por nome exato é segura.
- **Assunções a validar no ambiente JPM:** (1) col A do VCP = contrato que casa com `Contrato` do swap_position;
  (2) contas col K corretas; (3) tokens de LOB (inclui **COMM** p/ Commodities, ausente no `_fcst_lob` do forecast).
  O endpoint retorna `diagnostics` (lidos/mantidos/classificados) p/ calibrar.

### Arquivos criados/modificados nesta sessão
```
apps/templates/pages/accrual-swap.html        ← CRIADO (página completa: widgets, dropzone, 4 DataTables)
apps/pages/routes.py                           ← rota /accrual-swap + endpoint process + helpers (_accrual_lob, _swap_pos_*)
apps/templates/partials/sidenav.html           ← seção Accrual → SWAP
apps/static/js/pages/dashboard.js              ← Deal Flow rounding (stackEndRadius)
apps/static/data/translations/{en,br,es}.json  ← nav-accrual + acc-*
```
> ⚠️ Validado por sintaxe (Jinja2 parse, `node --check`, `ast.parse`, JSON). **Não testado em runtime** — precisa do
> ambiente com sessão autenticada + um JSON de posição swap salvo p/ a classificação por LOB funcionar de fato.

---

## 33. Sessão 2026-06-30 (cont.) — Accrual → Swap: overhaul completo (tabelas CRUD, maker/checker, date picker, colunas fixas)

Evolução grande da página **Accrual → Swap** (atualiza/expande a seção 32). **Testado end-to-end no dev server (8050)**.
Commits: `c259381`, `699f94d`, `c919d61`, `318fb82`, `cb6112b` (+ os de chart/missing-cp da seção 31).

### Página `/accrual-swap` — estado atual
- **Sidenav/topbar/horizontal-nav:** o item **"Accrual"** (ícone `calculator`) aponta **direto** p/ `/accrual-swap`
  (removida a rota inexistente `/regulatory/accrual` que dava 404). Não é mais collapsible.
- **4 widgets** CEM/EDG/Hybrids/Commodities — count-up **0→valor ao entrar na página** (carrega today via `/data`),
  + pop de feedback (scale) quando o valor muda.
- **Dropzone slim** aceita `.xlsx/.xlsm/.csv/.tsv`.
- **Card date-picker** (entre dropzone e tabelas): `daterangepicker singleDatePicker` **dd/mm/yyyy**, default **hoje**,
  ícone calendário dentro do campo; botão **Load** (ícone `refresh-cw`) carrega o JSON da data via `/data?date=`.
- **4 tabelas DataTables** (uma por LOB), **colunas fixas sempre visíveis** (mesmo sem import):
  - Fixas: **checkbox** (select-all), **Actions** (edit/delete/send), **Status**.
  - 11 colunas de dados **hardcoded** (`_ACC_FIXED_HEADERS` no backend = `ACC_FIXED_HEADERS` no front, **mesma ordem**):
    `Código IF, Data Início, Data Vencimento, PARTE / Conta, PARTE / Nome Simplificado, PARTE / Indexador,
    CONTRAPARTE / Conta, CONTRAPARTE / Nome Simplificado, CONTRAPARTE / Indexador, Fator Parte, Fator Contraparte`.
  - Filtros por coluna (placeholder = nome da coluna), **25 rows** default, Columns (show/hide), Clear filters.
  - **Botões/badges = padrão New Deals**: Actions = `btn btn-info/danger/primary btn-sm rounded-circle` + ícones Tabler
    (`ti-edit`/`ti-trash`/`ti-brand-telegram`; save=`ti-device-floppy`, cancel=`ti-x`). Status badge `badge badge-label
    {bg-info text-white|text-bg-warning|text-bg-info} rounded-pill` (New/Pending/Sent).

### Backend (`routes.py`)
- **Mapeamento das colunas** — `_ACC_DISPLAY_SRC = [0,5,6,10,11,13,16,17,19,None,None]` (col 0-based; None=placeholder):
  Código IF←**A**(0, `#` removido), Data Início←**F**(5), **Data Vencimento←G**(6), PARTE/Conta←**K**(10),
  PARTE/Nome←**L**(11), PARTE/Indexador←**N**(13), CONTRAPARTE/Conta←**Q**(16), CONTRAPARTE/Nome←**R**(17),
  CONTRAPARTE/Indexador←**T**(19). **Fator Parte / Fator Contraparte = vazios** (grab depois).
- **Headers na linha 9**; filtro col **K** (`_ACC_ACCOUNT_COL=10`) só contas-casa `73760.00-9`/`04880.00-6` (por dígitos);
  join `Código IF` ↔ `Contrato` do **último JSON de posição swap salvo** → `Código Identificador` → LOB
  (`_accrual_lob`: CEMHYB/HYB→Hybrids, COMM→Commodities, EDG, CEM).
- **Encoding robusto** (`_cc_read_rows`): tenta utf-8-sig → cp1252 → latin-1, escolhe o 1º **sem U+FFFD** (acentos OK).
- **Row layout persistida:** `[ ...11 data cells..., status, maker, checker, id ]` — **id é a última célula**;
  status default `New`. id = `'{lob}-{idx}'`.
- **JSON salvo** em `static/data/cache/accrual/YYYY/MM/DD/accrual_swap_YYYYMMDD.json` (gitignored) — inclui
  `headers/tables/counts/diagnostics/date/saved_at/source_file`.
- **Endpoints** (`date`-aware, default hoje): `GET /api/accrual-swap/data?date=` · `POST /process` ·
  `/row/delete` · `/rows/delete` (bulk) · `/row/edit` · `/row/send`. Helpers `_accrual_load/_accrual_save/_accrual_find`.
- **Maker/checker:** edit → status **Pending**, maker = `session.user_sid`, checker reset; send → guard **same_user**
  (quem alterou não envia → 403 `same_user`), senão status **Sent** + checker. **Persistem no JSON.**

### Frontend (`accrual-swap.html`) — pontos-chave
- `renderTable` sempre usa `ACC_FIXED_HEADERS` (colunas fixas). Colunas DataTables: `[checkbox, actions, status(data:n),
  data0..data(n-1)]`; meta (status/maker/checker/id) acessada via `row().data()` (não são colunas). `getRowId = d[d.length-1]`.
- **Seleção/bulk delete:** `selectedByTable[tableId]` (Set de ids); **select-all opera só na PÁGINA ATUAL**
  (`{page:'current',search:'applied'}`) e `syncSelectionUI` **poda ids inexistentes** → contagem do bulk = exata.
  Bulk button aparece com `sel.size > 1`.
- **Edit inline:** células de dados viram inputs (td 3..3+n-1); save → `POST /row/edit` → `dt.row.data(j.row)`.
- `currentDate` = data exibida; enviado em todos os edit/delete/send. count-up via `countTo`.

### Padrões / lembretes
- **Decode de texto:** sempre multi-encoding com guarda de `'�'` (latin-1 nunca falha, é o último recurso).
- **Status/maker/checker em rows-array:** id SEMPRE a última célula; meta nas 3 anteriores (`r[-4]=status, r[-3]=maker,
  r[-2]=checker, r[-1]=id`); data = `r[:-4]`. Edit no backend usa `ndata = len(target)-4`.
- **Colunas fixas data-driven:** quando os headers vêm de arquivo mas precisam ser fixos, hardcodar a lista (back+front
  na mesma ordem) e mapear dados por `_DISPLAY_SRC` (col-fonte ou None=placeholder).
- **daterangepicker** (não flatpickr): `singleDatePicker` + `moment` (ambos em `plugins/daterangepicker/`).
- **Pendência:** Fator Parte/Contraparte vazios (grab a definir). Se mais colunas mudarem de fonte, ajustar só `_ACC_DISPLAY_SRC`.

### Arquivos (sessão)
```
apps/templates/pages/accrual-swap.html         ← página completa (tabelas CRUD, date picker, seleção, status, count-up)
apps/pages/routes.py                           ← _ACC_FIXED_HEADERS/_ACC_DISPLAY_SRC, encoding, endpoints data/edit/delete/send
apps/templates/partials/{sidenav,topbar,horizontal-nav}.html ← Accrual → /accrual-swap (direto)
apps/static/js/pages/dashboard.js              ← arredondamento última barra (stackEndRadius numérico + borderSkipped)
apps/templates/pages/index.html                ← cache-bust dashboard.js (?v=20260630a)
apps/static/js/missing-counterparty.js         ← (sessão 31) badge Missing Counterparty
apps/templates/pages/new_deals-*.html          ← (sessão 31) Missing Counterparty nas 5 páginas
apps/static/data/translations/{en,br,es}.json  ← acc-* (incl. status/actions/date/load), badge-missing-cp
.gitignore                                     ← cache/accrual/**/*.json
```

## 34. Sessão 2026-06-30 (cont.) — Accrual: fatores CEM/EDG/HYB, coluna Comments, import por pasta, notificações; CETIP .TER/.OPC

Continuação do Accrual → Swap (expande seções 32/33) + ajuste no CETIP file-saving. **Testado end-to-end no dev (8050 +
instância temporária 8051 com `ACCRUAL_SOURCE_ROOT` override)**. Commits: `ff5a6fb` (fatores CEM/EDG/HYB + Missing
Accrual + CETIP paths), `ba3ddc8` (Comments, import-folder, abs, notificações).

### A) CETIP file-saving — cópias secundárias `.TER`/`.OPC`
- `CETIP_NDF_SHARE` → **`I:\CETIP_NDF`** (regra `.TER` / DPOSICAO-TER) e `CETIP_OPTIONS_SHARE` → **`I:\CETIP_OPTIONS`**
  (regra `.OPC` / DPOSICAO.OPC). Mecanismo `extra_dest` já existia (loop em `routes.py` faz `os.makedirs(extra)` +
  `_cetip_save_file`); só os caminhos mudaram. Override por env (`CETIP_NDF_SHARE`/`CETIP_OPTIONS_SHARE`).

### B) Enriquecimento de Fatores (CEM/EDG/HYB) — tradução do VBA Alteryx
- **Mesmo dropzone, roteado pelo nome** (`fileKind`): VCP→`/process`; **CEM/EDG/HYB**→`POST /api/accrual-swap/factors`
  (form `kind`+`date`). Match **Código IF = CETIP ID** (fallback dígitos, `_acc_factor_keys`).
- **CEM** (visão Banco **LE 228**): Kapital(col B)→LE via aba **'Kapital CETIP'** (col E) do xlsx. LE **228 normal**
  (`PARTE/VCP=col I`, `CONTRAPARTE/VCP=col J`); só **199 invertido** (`PARTE=J`, `CONTRA=I`); duplicado 228/199 → mantém
  228; outras visões (123→MGT) ignoradas. **Kapital match sem zero à esquerda** (`lstrip('0')` nas duas abas: `00777`==`777`).
- **EDG** direto: CETIP=A, Fator Parte=B, Fator Contraparte=C. **HYB** direto: **CETIP=B**, Fator Parte=**L**(idx11),
  Fator Contraparte=**M**(idx12). Mapa `_ACC_FACTOR_KINDS` (kind→lob+parser).
- Lado **não-VCP → '-'**; VCP sem fator **ou** sem match → status **'Missing Accrual'** (badge `text-bg-warning`).
- Fatores formato **americano `#.00000000`** (8 casas, arredondado, **sempre absoluto/`abs`**). `_acc_parse_num` aceita
  BR (`1.234,56`) e US (`1,234.56`) + milhar.
- Helpers: `_acc_parse_num/_acc_fmt_factor/_acc_le_norm/_acc_read_sheets/_acc_parse_cem_factors/
  _acc_parse_direct_factors(cetip_col,parte_col,contra_col)/_acc_apply_factors`.

### C) Coluna Comments + migração de layout
- **`Comments`** = 12ª coluna fixa (editável, persiste). `_ACC_FIXED_HEADERS`/`ACC_FIXED_HEADERS` e
  `_ACC_DISPLAY_SRC=[...,None,None,None]`. **Novo layout de linha:** `[12 data..., status, maker, checker, id]` (16 cells).
- **`_accrual_migrate`** (chamado em `_accrual_load`): JSON antigo (15 cells / 11 data) recebe `''` inserido **antes do
  bloco meta** → vira 16 (Comments na posição certa); seta `headers` p/ os fixos atuais. Front sempre usa `ACC_FIXED_HEADERS`.

### D) Import direto da pasta (sem dropzone)
- Card de data agora **full-width** (`max-width:none`) + botão **"Import from folder"** (`folder-input`, outline).
- `POST /api/accrual-swap/import-folder {date}` → lê de **`ACCRUAL_SOURCE_ROOT\YYYY\MM. Month\DD`** (env, default
  `I:\Confirmation\Derivativos\OTC Tracker\Regulatory\Accrual`; run = último dia útil ANBIMA do mês). Acha o **VCP** (nome
  c/ `vcp`/`instrumentofin`) → `_accrual_build_result` → `_accrual_persist(result, vcp, ymd=<data>)`; depois aplica
  **cada** CEM/EDG/HYB presente (basename `startswith` kind) em sequência, salva, retorna `applied[]`. Erro limpo se a
  pasta não existe.
- **Refactor:** VCP processing extraído p/ `_accrual_build_result(rows)` (core, sem I/O) + `_accrual_persist(result,
  source_file, ymd=None)` (default hoje; ymd = data do run). `/process` e `/import-folder` reusam ambos.

### E) Status sort + Notificações topbar
- Coluna **Status** com render **type-aware** (idx 2): p/ `sort`/`type` retorna `'0'+status` se Missing Accrual senão
  `'1'+status` → após import com `missing>0`, `dt.order([2,'asc'])` deixa **Missing Accrual no topo**.
- **Notificações** (`page='Accrual'`, deep-link `/accrual-swap`): `Accrual Imported` (VCP/folder), `Accrual Mapped`
  (factors), `Accrual Updated` (edit), `Accrual Sent` (send), `Accrual Deleted` (delete/bulk). `ACTION_META`+`PAGE_URL`
  em `topbar.html`. `_create_notification` nos 6 endpoints.

### Arquivos (sessão 34)
```
apps/pages/routes.py                           ← CETIP paths; fatores CEM/EDG/HYB; Comments+migração; refactor build/persist; import-folder; 6 notif
apps/templates/pages/accrual-swap.html         ← fileKind routing, factor result, Comments, status sort, card full-width, botão import-folder
apps/templates/partials/topbar.html            ← ACTION_META + PAGE_URL (Accrual)
apps/static/data/translations/{en,br,es}.json  ← acc-st-missing accrual, acc-factors-*, acc-import-*
```

### Pendências / lembretes
- **Commodities** ainda sem arquivo de fatores (só CEM/EDG/HYB definidos) → adicionar 4ª entrada em `_ACC_FACTOR_KINDS`.
- Caminhos `I:\...` só resolvem no ambiente JPM; em dev usar env override (`ACCRUAL_SOURCE_ROOT`, `CETIP_*_SHARE`).
- Para testar import-folder no dev: instância temporária com env override + seed de swap-position JSON (classificação LOB).

## 35. Sessão 2026-06-30/07-01 — Accrual: geração de arquivos SWAP, preview, Confirm, Validation, Recon, End Process; polish Apple

Fechamento do fluxo EOM do Accrual → Swap (expande 32/33/34). **Testado end-to-end no dev (8050 via `/dev-login` SID
A000000 + instâncias temporárias 8051-8055 com env overrides `CONECTA_NEW_PATH`, `ACCRUAL_SOURCE_ROOT`, `SMTP_HOST`→porta
morta p/ falha rápida)**. Commits de `6df1b96` até `4b174ec`. **E-mails sempre em inglês.**

### A) Export por tabela + date picker compacto (`6df1b96`)
- Cada tabela ganhou botões de export (modelo New Deals: Excel JSZip / CSV bom / Copy) + dropdown de export legível
  (`b3baa11`, corrige contraste do menu). Date picker do card compactado.

### B) Geração de arquivos SWAP em lote — "Send batch" (`d66cc3a`)
- Botão **Send batch** por tabela → `POST /api/accrual-swap/send-batch {lob, date}`. Gera `ACCRUAL_<VIEW>-<LOB>.txt`
  **quebrado por view** na pasta **Batch Conecta** (`CONECTA_NEW_PATH`) **e** (best-effort) na pasta de evidência
  (`110c64b`, ver F).
- **Header** por view: `_acc_swap_header(view,today) = 'SWAP 00015' + name.ljust(20) + today`. Mapas:
  `_ACC_VIEW_BY_PREFIX={'73760':'BANCO','04880':'BANCO','85398':'ATACAMA','00041':'LAWTON'}`,
  `_ACC_VIEW_PART_NAME={'BANCO':'JPMORGANBM','LAWTON':'INTRAGLAWTONFDO','ATACAMA':'INTRAGATACAMAFDO'}`.
- **Linha de registro** (`_acc_swap_records`): `'SWAP '+'1'+'0015'+codigo+papel+'00'+curva+today+meu+' '*22+fator`.
- `_acc_write_batch_files(data, lob, today, evidence_dir=None)` — escreve nos dois destinos com o mesmo basename.

### C) Preview PU/Fator (duplo-clique) — vertical + Confirm (`d66cc3a`, `cba1c13`)
- **Duplo-clique** numa linha abre modal (modelo New Deals) com os registros SWAP daquela operação.
- Banco×Lawton → **2 colunas**; VCP×VCP → **4 colunas**; `73760.10-2` (só uma ponta VCP) → **2 colunas**.
- **Preview na vertical** (`cba1c13`): campos viram linhas, cada registro é uma coluna. Ações do modal: só ícones **Send**
  e **Close** (X vermelho / X branco), sem "Generate file".
- **Confirm** (maker/checker) nas colunas de Action p/ aprovar mudanças de fator.

### D) Validation (EOM) — e-mail OTC Ops (`d0e19c3`, `f539334`, `fa46b67`)
- Botão **Validation** no card de data → gera **todos** os batch files (geral, todas as LOBs) + envia e-mail
  **`Accrual EOM - DD/MM/YYYY - Validation`** (título "Accrual", não "ACCRUAL" — `fa46b67`) de `otc.tracker@` p/
  `brazil.otc.ops@`. **Anexa só os arquivos Lawton e Atacama** (não Banco).
- **E-mail em background thread** (`f539334`): SMTP síncrono travava a resposta ("network error"). Fix: `render_template`
  + `_get_logo_path` rodam no request context; a thread só faz SMTP. Template
  `email-template-accrual-validation.html`. Cor do botão neutralizada (depois virou ghost azul em I).

### E) Recon (`operacoes`) — match por fator (`66be733`, `96be733→b171be0`)
- Botão **Recon** lê `operacoes.*` da pasta **ou** do dropzone (`fileKind`). **Lógica final SIMPLES** (2 tentativas
  erradas descartadas — ver adiante): col **F** já traz a ponta; basta checar se **Fator Parte/Contraparte** aparece
  entre os fatores registrados (col **P**) daquele **Código IF**.
- `_acc_run_recon(data, rows)`: monta `by_cif` (cif_key→[floats arredondados] de col P, filtrando marker
  `_ACC_RECON_MARKER='REGISTRO DE PU/FATOR'`, header na linha 5, contas `_ACC_RECON_ACCOUNTS={'04880006','73760009'}`);
  por perna VCP `ok = round(accv,8) in regset`. Status **Success** (todas OK) ou **Check**. `factorRender` desenha badge
  **verde** (matched) / **vermelho + tooltip** (divergência). Check habilita **Comments** inline.
- Endpoints `/api/accrual-swap/recon` e `/row/comment` (seta `target[-5]`).

### F) End Process — e-mail Final Status (`ed53965`, `e08d162`, `110c64b`)
- Botão **End Process** (ao lado de Recon). **Gate:** todas as linhas com status **Check** precisam estar comentadas;
  se não, sweet alert lista as pendentes.
- E-mail **`Accrual Swap - EOM - Final Status - DD/MM/YYYY`** de `otc.tracker@` p/ `brazil.otc.ops@`, **CC**
  `_ACC_ENDPROC_CC=['renato.montoza@jpmorgan.com','danilo.camposfonseca@jpmchase.com']` (são **OTC Ops**, não Middle
  Office — menção "cc Middle Office" removida do sweet alert em `e08d162`).
  - **Com Check** → tabela LOB/Código IF/Status/Comment. **Sem Check** → bloco "No divergences found" + caminho da pasta.
  - Template `email-template-accrual-endprocess.html` (vars `has_check`/`checks`/`folder`). Background thread.
- **Evidência** (`110c64b`): arquivos de accrual gravados **também** em
  `ACCRUAL_SOURCE_ROOT\YYYY\MM. Month\DD` (além da pasta Batch Conecta); o e-mail aponta p/ essa pasta (`folder`).

### G) Bloqueio Missing Accrual (`d5c5f10`)
- **Send batch** e **Validation** não geram nada se qualquer linha (da tabela respectiva p/ send-batch, geral p/
  validation) estiver com status **Missing Accrual**. `_acc_missing_accrual_rows(data, lobs)` → retorna
  `error:'missing_accrual'`; front mostra sweet alert com a lista (`showMissingAccrual`).

### H) Polish (Apple / DESIGN-apple.md)
- **Sweet alerts centralizados** (`1c96974`, `ecbaf84`, `b171be0`): todos os resultados (factor, recon, import via
  dropzone, send-batch, import-folder) convertidos de **toast lateral** → **modal centralizado** com backdrop
  desfocado (`.swal2-backdrop-show { background: rgba(0,0,0,.25); backdrop-filter: blur(4px); }`). `deferToast` faz
  double-rAF antes do `Swal.fire`. **Modelo dos New Deals.**
- **Spinner/hover confiável** (`1c96974`): lucide **não** preserva `class` no SVG gerado → spinner puro-CSS
  `.acc-spinner` (border + `currentColor`). `accBtnBusy(btn,on)` salva/restaura innerHTML. Feedback de hover em todos os
  botões (tabela + card).
- **Botões no accent único** (`4b174ec`): removidos roxo (Recon #6f42c1), verde (End Process #157347), cinza
  (Validation) — fora da paleta. **Load + End Process** = pill **preenchido** Action Blue; **Import / Validation /
  Recon** = pill **ghost** (transparente, texto/borda azul). Menores (altura 38→32px, fonte .82→.77rem, ícones 16→14px,
  pill radius). Sombra de hover suavizada (`0 2px 6px rgba(0,0,0,.10)`). Date input 32px + pill.

### CETIP / B3 (correções desta sessão)
- **DCADCOMITENTES** (`761b77d`): rotina CETIP salva o `dcadcomitentes` no destino + lista no e-mail; recon comitente
  (`recon_comitente.py`) lê de `os.path.join(_CETIP_DEST_BASE, year, 'MM. Month', day, 'SIC_<data>_DCADCOMITENTES.txt')`.
- **NDF-comm Quoted in Cents** (`9d1231a`): commodity com Fator Conversão `0.01` era exibido como **não**-cents (valor
  stored obsoleto + colisão de mapa HOH7). Fix: re-derivar do fator vivo, mapa preferindo `0.01`, helper `_ndfIsCents`.
- **B3 JSON com indentação** (`58ca137`): `json.dump(..., indent=2)` (estavam numa linha só).

### Erros corrigidos (histórico p/ não repetir)
- **Recon errado 2×**: (1) matching por tamanho de conta ponta→curva; (2) versão col-B/col-AC — ambos descartados.
  Usuário: "esquece essa logica esta errada" → col F já dá a ponta, é só **membership de fator na col P**.
- **Validation "network error"**: SMTP síncrono → background thread (renderizar HTML+logo no request, thread só SMTP).
- **Spinner estático**: lucide não preserva class no SVG → CSS `.acc-spinner`.
- **Swal virando barra lateral**: reportado 2×; converter **todos** `toast:true/position:'top-end'` → centralizado.

### Arquivos (sessão 35)
```
apps/pages/routes.py                                   ← send-batch/preview/validation/recon/end-process/comment; _acc_swap_*, _acc_write_batch_files, _acc_run_recon, _acc_missing_accrual_rows, _ACC_ENDPROC_CC; bloqueio Missing Accrual; DCADCOMITENTES; b3 indent
apps/pages/recon_comitente.py                          ← lê DCADCOMITENTES do destino CETIP (_CETIP_DEST_BASE)
apps/templates/pages/accrual-swap.html                 ← Send batch, preview vertical, Confirm, Validation, Recon, End Process; sweet alerts centralizados; .acc-spinner; botões accent único (Apple)
apps/templates/pages/email-template-accrual-validation.html   ← (novo) e-mail Validation EOM
apps/templates/pages/email-template-accrual-endprocess.html   ← (novo) e-mail Final Status (has_check/checks/folder)
apps/static/js/pages/new_deals-ndf-comm.js (ou template)      ← _ndfIsCents (Quoted in Cents 0.01)
apps/static/data/translations/{en,br,es}.json          ← acc-prev-*, acc-confirm, acc-batch-*, acc-validation-*, acc-recon-*, acc-comment-ph, acc-st-success/check, acc-missing-*, acc-endproc-*
```

### Pendências / lembretes
- **Commodities** ainda sem arquivo de fatores (herdado da seção 34).
- Recon depende de `operacoes.*` com header na linha 5, contas `04880006`/`73760009`, marker `REGISTRO DE PU/FATOR`.
- CC do End Process (`renato.montoza`, `danilo.camposfonseca`) são **OTC Ops** — nunca rotular como Middle Office.
- **Emails em inglês.** Caminhos `I:\...` só no ambiente JPM (env override em dev).

## 36. Sessão 2026-07-01 — Dashboard (Top 5 por período + cantos arredondados), CETIP e-mail "Not found", script de pastas

Commits: `c3b4603`, `12becdf`, `c7d38c8`, `8bf05ff`, `2b679c7`. **Testado no dev (8050 via `/dev-login`)**; template
CETIP renderizado standalone com Jinja.

### A) Dashboard — Top 5 cards seguem o filtro Month/Year/All (`c3b4603`)
- **Bug:** o estado vazio fazia `card-body.innerHTML = '<p>No deals found</p>'`, **apagando o `<canvas>`**. Na carga
  inicial (`month` = mês corrente, muitas vezes vazio) os 3 canvases eram removidos; ao trocar p/ Year/All,
  `getElementById(...)` retornava **null** e a função saía cedo (`if (!ctx) return;`) → mensagem presa p/ sempre. O
  backend `/api/dashboard-stats?period=` **já filtrava certo** (`_file_in_period`) — o defeito era 100% front.
- **Fix:** helper **`_setChartEmpty(canvas, isEmpty)`** em `dashboard.js` — esconde o wrapper (`canvas.parentElement`) +
  mostra um `<p class="dash-empty-msg">` reutilizável, **sem remover o canvas**. Ao voltar a ter dados, restaura o
  wrapper. Aplicado em `buildClientsChart`/`buildProductsChart`/`buildCommoditiesChart` (`if (_setChartEmpty(ctx,
  !top5.length)) return;`). Agora alterna em qualquer direção (vazio↔dados). Badges de período já eram atualizados por
  `updatePeriodBadges`.

### B) Dashboard — cantos arredondados das barras empilhadas (`c3b4603`, `12becdf`)
- **`stackEndRadius`** reescrito: retorna **objeto por-canto** (`{topLeft,topRight,bottomLeft,bottomRight}`) +
  `borderSkipped:false` — o combo que o **Chart.js v4 honra** no segmento do topo (número + `borderSkipped:'bottom'` era
  descartado). Assinatura `stackEndRadius(R, edge)`: `'bottom'`→vertical (arredonda topo), `'left'`→horizontal (arredonda
  direita). Aplicado em Deal Flow (`buildFlowChart`), Top Clients (`buildClientsChart`) e Monthly.
- **Settlement Forecast — plugin de clip (`12becdf`):** o approach por-segmento só arredonda o **segmento do topo**, que
  no forecast costuma ser um sliver fino de SWAP/Option → o Chart.js clampa o raio à altura minúscula e a ponta fica
  reta. Plugin **`roundedStackTopClip`** (registrado só no chart do forecast via `plugins:[...]`) recorta cada coluna num
  retângulo de **topo arredondado da pilha inteira** antes das barras desenharem (`beforeDatasetsDraw` calcula topo/base
  por categoria, `ctx.clip(path)`; `afterDatasetsDraw` faz `restore`), garantindo a ponta arredondada **independente da
  espessura** do produto do topo (gradientes intactos). Forecast passou a `borderRadius:0` (o plugin arredonda).
- **Cache-bust** `dashboard.js` em `index.html`: `20260630a`→`20260701b`.

### C) CETIP e-mail — arquivos "Not found" na tabela (`c7d38c8`, `2b679c7`)
- No loop de `_CETIP_RULES` (`api_cp_cetip_settlement`), rastreio **`rule_matched`**; regras sem arquivo correspondente
  na pasta origem viram lista **`missing`** com o **nome esperado** derivado da data (`rule['dest_name'](ref.strftime(
  '%y%m%d'))`). Passado só ao e-mail do **OTC Ops** (Sales Support fica intacto).
- `_send_cetip_email(..., missing=None)` → template `email-template-cetip-saved.html`: nova **coluna Status** (pill verde
  **Saved** / âmbar **Not found**, nome esperado em cinza ou `—`) + **badge de contagem "Not Found"** (âmbar) ao lado do
  "File(s) Saved" (aparece só quando há faltantes) + frase na intro. Loop `missing_files` após `saved_files`.
- **Linter CSS (`2b679c7`):** VSCode acusava erro no `style="{% if %}..."` (parseava o Jinja como CSS). Fix: escolher a
  **tag `<td>` inteira** via `{% if missing_count %}`/`{% else %}` (50%+padding vs 100%), deixando cada `style` como CSS
  estático. **Regra geral: nunca colocar `{% %}`/`{{ }}` dentro de um atributo `style`.**

### D) Script — pré-criar pastas da origem CETIP (`8bf05ff`)
- **`scripts/create_cetip_folders.py`** (stdlib pura, sem deps): cria `CETIP_SOURCE_ROOT\YYYY\MM. Month\DD` (mesma
  convenção da rotina + `EN_MONTH_NAMES`) **só para dias úteis ANBIMA** (lê `apps/static/data/anbima.json`, weekday<5 e
  não-feriado — mesma regra de `_prev_anbima_bizday`).
- Flags: `--year YYYY [YYYY...]` (ano cheio), `--start/--end YYYY-MM-DD` (intervalo), `--root` (senão `$CETIP_SOURCE_ROOT`
  ou o default do routes.py), **`--dry-run`** (simula, não escreve). **Idempotente** (`os.makedirs(exist_ok=True)`, conta
  "Already existed"; nunca mexe no conteúdo das pastas).
- Acha `anbima.json` relativo (sobe 1 nível a partir de `scripts/`) — rodar a cópia dentro do repo.
- **Nota de ambiente (JPM):** erro `No Python at ...python3.12\latest\python.exe` = venv `OTCTracker` órfão (base Python
  sumiu), **não é do script**. Como é stdlib pura, rodar com qualquer Python 3: `py ...\scripts\create_cetip_folders.py`.

### Arquivos (sessão 36)
```
apps/static/js/pages/dashboard.js              ← _setChartEmpty; stackEndRadius objeto+edge; plugin roundedStackTopClip (forecast)
apps/templates/pages/index.html                ← cache-bust dashboard.js 20260701b
apps/pages/routes.py                           ← missing[] no loop CETIP; _send_cetip_email(missing=...)
apps/templates/pages/email-template-cetip-saved.html  ← coluna Status (Saved/Not found), badge Not Found, sem Jinja em style
scripts/create_cetip_folders.py                ← (novo) cria pastas ano/mês/dia p/ dias úteis ANBIMA
```

---

## 37. Sessão 2026-07-01 (cont.) — Electronic Inventory (pastas de contraparte) + B3 ID no modal New Deals → Success/Intrag

Commits: `01b588e` (Electronic Inventory), `20bdd4d` (B3 ID modal). **Não testado em runtime** (paths de rede
`I:\...` só existem no ambiente JPM; helpers validados isoladamente + sintaxe/JSON OK).

### A) Electronic Inventory — árvore de pastas por contraparte (`01b588e`)
- **`scripts/create_counterparty_folders.py`** (novo, stdlib pura — mesmo estilo de `create_cetip_folders.py`): lê
  `apps/static/data/RefData.json` (553 registros) e cria `ELECTRONIC_INVENTORY_ROOT\<Contraparte>\{Confirmations,
  Transactional, SSI}`. Flags: `--root` (senão `$ELECTRONIC_INVENTORY_ROOT` ou o default do routes.py), `--active-only`,
  `--dry-run`. Idempotente.
- **Sanitização Windows:** remove chars ilegais `<>:"/\|?*` + controle, colapsa espaços, tira dot/espaço final →
  `BUNGE ALIMENTOS S/A` vira pasta `BUNGE ALIMENTOS SA` (regra pedida: `/` → "").
- **Detecção tolerante de já-existentes:** compara por **chave normalizada** (`norm_key` = sanitizado + upper). Uma pasta
  criada antes com sanitização diferente é **reusada**, não duplicada; só as subpastas faltantes são criadas.
- **`routes.py`:** const `ELECTRONIC_INVENTORY_ROOT` (env-overridable, default `I:\Confirmation\Derivativos\OTC Tracker\
  Electronic Inventory`) + `EI_SUBFOLDERS` + helpers `_ei_sanitize` / `_ensure_counterparty_folders` (mesma lógica do
  script — manter em sync). Best-effort: nunca levanta exceção (share pode estar offline em dev; loga `log.warning`).
- **Hook automático:** em `api_b3_update`, quando o **checker aprova** um registro de Reference Data (`action=='approve'`
  + `table=='refdata'` → `ACTIVE`), chama `_ensure_counterparty_folders(rec['COUNTERPARTY'])`.

### B) B3 ID no modal de edição das 5 páginas New Deals → flip Sent/Error para Success + Intrag (`20bdd4d`)
- Modal de edição (`arOpenEditModal` + `#ar-save-btn`) das 5 páginas ganhou campo **`#ar-b3id`** (prefill da coluna B3 ID
  da linha). Ao salvar com **B3 ID preenchido** E status atual **`Sent` ou `Error`** → `Status='Success'` (senão mantém
  `Pending`/`New`). Backend já dispara o pipeline Intrag em `Status→Success` (gate intragrupo Banco J.P. Morgan).
- **Leitura do status atual no front:** o status vem como HTML badge em `d[STATUS_COL_INDEX]` (=2 em todas); extraído via
  `div.innerHTML → textContent`.
- **Índices por página:** opt-comm/opt-fxo/ndf-comm → Deal `d[3]`, B3_ID `d[4]`; ndf-fwdstart/otherpublisher → Deal
  `d[4]`, B3_ID `d[5]`. fwdstart/otherpublisher constroem o payload via `arBuildDeal()` (promoção feita no save handler,
  fora do build).
- **Bug corrigido:** páginas NDF apagavam o B3 ID no edit (`B3_ID: ''` hardcoded no payload); agora enviam o valor do campo.
- **routes.py:** o **PATCH genérico** `/api/new-deals/<product>/cache/<deal_id>` (fwd-start/other-publishers) **não**
  disparava o Intrag — adicionado `_save_intrag_ndf_entry` em `Status→Success` + Banco JPM (paridade com o endpoint
  dedicado da ndf-commodities). opt-comm/opt-fxo/ndf-comm já disparavam.
- **i18n:** `nd-b3id-hint`, `swal-b3-confirmed-title`, `swal-b3-confirmed-text` (en/br/es).

### Padrões identificados
- **Pipeline New Deals→Intrag é sempre gated por Client = Banco J.P. Morgan** (`_maybe_save_intrag_*` / checagem `'banco'
  in cl and 'morgan' in cl`). Deals de outras contrapartes vão a Success sem entrada no Intrag — comportamento correto.
- **Sanitização de nome de diretório Windows:** helper compartilhado entre script standalone e routes.py; comparar por
  chave normalizada para reaproveitar pastas pré-existentes em vez de duplicar.
- **Modal de edição New Deals:** o botão Edit abre o modal `arOpenEditModal` (não a edição inline `btn-row-save-edit`,
  que é caminho legado); qualquer novo campo de edição vai no modal + prefill + payload do `#ar-save-btn`.

### Arquivos (sessão 37)
```
scripts/create_counterparty_folders.py         ← (novo) árvore de pastas Electronic Inventory por contraparte
apps/pages/routes.py                            ← ELECTRONIC_INVENTORY_ROOT + _ei_sanitize/_ensure_counterparty_folders +
                                                  hook approve refdata; Intrag NDF no PATCH genérico
apps/templates/pages/new_deals-opt-commodities.html   ← campo B3 ID + flip Sent/Error→Success
apps/templates/pages/new_deals-opt-fxo.html           ← idem
apps/templates/pages/new_deals-ndf-commodities.html   ← idem (+ fix B3_ID:'')
apps/templates/pages/new_deals-ndf-fwdstart.html      ← idem (arBuildDeal)
apps/templates/pages/new_deals-ndf-otherpublisher.html← idem (arBuildDeal)
apps/static/data/translations/{en,br,es}.json         ← nd-b3id-hint, swal-b3-confirmed-title/text
```

---

## 38. Sessão 2026-07-01 (cont.) — Notificações do sino com deep-link por data (Accrual ?date=, New Deals ?tradedate=)

Commit: `86eb12a`. **Páginas carregam 200 com os params no dev**; token e parse validados isoladamente.
Deep-link de accrual/new deals não testado com dados reais (máquina dev sem cache de accrual/new deals).

### Sintoma / causa raiz
- Clicar numa notificação de **Accrual** "não fazia nada": a navegação (`PAGE_URL['Accrual']='/accrual-swap'`)
  **já estava correta**, mas a página **sempre carregava `loadByDate(todayISO())`** — hoje costuma estar vazio, então
  recarregava a mesma view vazia (percepção de "nada aconteceu"). Idem New Deals: filtro padrão fixo em Trade Date = hoje.

### A) Accrual — landing na data certa
- **`accrual-swap.html`**: load inicial agora lê **`?date=YYYY-MM-DD`** da URL; senão busca a **última data com dados**
  e cai nela; senão hoje. (substitui `loadByDate(todayISO())`).
- **routes.py**: `_accrual_latest_ymd()` (escaneia `accrual_swap_*.json` sob `ACCRUAL_JSON_ROOT`, pega o maior YYYYMMDD)
  + rota **`GET /api/accrual-swap/latest`** → `{success, date}`.

### B) Token de data nas notificações + deep-link no topbar (mecanismo unificado)
- **Helper `_nd_token(value)`** (routes.py, após `_create_notification`): retorna sufixo **` [ND:YYYY-MM-DD]`** para o
  `detail`; aceita `date`/`YYYYMMDD`/`YYYY-MM-DD`/`dd-mm-yyyy`/`dd/mm/yyyy` (usa `_parse_date_any`); `''` se inválido.
- **Topbar** (`renderNotifications`): faz regex `\[ND:(\d{4}-\d{2}-\d{2})\]` no detalhe, **remove o token do texto
  exibido**, e monta o URL: página **Accrual → `?date=`**, páginas **New Deals → `?tradedate=`** (mapa
  `NEW_DEALS_PAGES`). Sem token → cai no default da própria página (hoje). Reaproveita o padrão do deep-link `?spn=` do
  Reference Data.
- **Accrual (11 call sites)**: token com `data.get('date')` / `ymd` / `result.get('date')` conforme o que está em escopo.
- **New Deals (single-deal)**: token com `updated_deal.get('TradeDate')` nos PATCH (Status/Deal Updated de opt-comm,
  opt-fxo, ndf-comm e genérico fwdstart/otherpub) e nos DELETE (capturado `removed = deals.pop(idx)`), e no upsert
  `?notify=1` da ndf-comm (`data.get('TradeDate')`).

### C) New Deals — filtro Trade Date honra `?tradedate=`
- Nas **5 páginas**, o bloco "Default filter: Trade Date = today" passou a: se `?tradedate=YYYY-MM-DD` presente →
  converte p/ dd/mm/yyyy e usa; senão hoje. **Via sidenav (sem param) = hoje** (comportamento pedido).

### Escopo deliberado (não coberto)
- Notificações **bulk** (Sent to B3, B3 Mapped, Bulk Delete/Update, import XLSX FXO) **não** recebem token → abrem no
  default (hoje). Motivo: múltiplos deals podem ter trade dates diferentes; o batch diário normalmente é do dia.
- Add de deal via **modal não gera notificação** (endpoints save/cache não notificam) — nada a deep-linkar ali.

### Padrões identificados
- **Deep-link por data via token no detail:** `_nd_token` no backend + parse/strip no topbar é o padrão reutilizável
  para qualquer página data-driven; o topbar decide o nome do query param por página. Nunca exibir o token cru.
- **Páginas data-driven não devem forçar "hoje" no load:** honrar query param, senão última data com dados.

### Arquivos (sessão 38)
```
apps/pages/routes.py                          ← _accrual_latest_ymd + /api/accrual-swap/latest; _nd_token; tokens nas
                                                notificações de Accrual (11) e New Deals single-deal (PATCH/DELETE/upsert)
apps/templates/pages/accrual-swap.html        ← load inicial: ?date= / última data / hoje
apps/templates/partials/topbar.html           ← NEW_DEALS_PAGES; parse+strip [ND:] → ?date=/?tradedate=
apps/templates/pages/new_deals-opt-commodities.html   ← filtro Trade Date honra ?tradedate=
apps/templates/pages/new_deals-opt-fxo.html           ← idem
apps/templates/pages/new_deals-ndf-commodities.html   ← idem
apps/templates/pages/new_deals-ndf-fwdstart.html      ← idem
apps/templates/pages/new_deals-ndf-otherpublisher.html← idem
```

---

## 39. Sessão 2026-07-01 (cont.) — Intrag: Send/Delete/Select-All respeitam o filtro (bug "N rows not sendable")

Commit: `8c2c3fc`. **Páginas carregam 200 no dev.**

### Sintoma / causa raiz
- Com o filtro `Registration Date = 30/06/2026` mostrando 3 de 46 linhas, o **Send** falhava com *"Cannot send — 43
  row(s) are not in a sendable state — only New or Approved can be sent."* (46 − 3 = 43).
- Causa: o **Select All** (e Send/Delete) usavam **`table.rows()`**, que retorna **todo o dataset** (46), ignorando o
  filtro. Marcar o select-all selecionava as 46; o Send então avaliava linhas fora do filtro (statuses variados) e
  bloqueava.

### Fix
- Todas as operações passam a usar **`table.rows({ search: 'applied' })`** (só as linhas que casam com o filtro/busca):
  select-all (add + set de checkboxes), Send (toolbar `btnSend*`), Delete (`data-del-selected`) e a **contagem `total`**
  que define o estado checked/indeterminate do header checkbox.
- Aplicado em **`intrag-option.html`** (id col `d[41]`) e **`intrag-ndf.html`** (id col `d[33]`) — paridade.
- Mantidas (inofensivas): `api.rows().every` do `drawCallback` (só seta checkbox/approve nas linhas renderizadas) e o
  `table.rows().every` do sucesso do Send (atualiza status→Sent por `id` das linhas enviadas).

### Padrão identificado
- **DataTables + seleção/ações em massa:** sempre iterar `table.rows({ search: 'applied' })`, nunca `table.rows()`, ao
  traduzir seleção → operação (send/delete/approve) e ao contar o total para o estado do "select all". `table.rows()`
  ignora o filtro e opera no dataset inteiro. Vale para as toolbars de New Deals e Intrag.

### Arquivos (sessão 39)
```
apps/templates/pages/intrag-option.html  ← select-all/send/delete/contagem com {search:'applied'}
apps/templates/pages/intrag-ndf.html     ← idem (paridade)
```

---

## 40. Sessão 2026-07-01 (cont.) — Padrão único de badge da coluna Status (forma Intrag + cores New Deals)

Commit: `d14d54f`. **7 páginas carregam 200 no dev.**

### PADRÃO OFICIAL — coluna Status (usar em TODA página nova)
- **Forma/estilo:** `<span class="badge <cls> bg-gradient">Texto</span>` — o estilo do Intrag (com `bg-gradient`).
  **Nunca** usar `badge-label` nem `rounded-pill` em badge de status (pílula/plano fica reservado a outros badges,
  ex.: Quoted YES/NO/Missing).
- **Cores (paleta New Deals):**
  | Status | Classe |
  |---|---|
  | New | `bg-info text-white` (azul) |
  | Pending | `text-bg-warning` (âmbar) |
  | Amend | `text-bg-warning` (âmbar) |
  | Approved | `text-bg-secondary` (cinza) |
  | Sent | `text-bg-info` (ciano) |
  | Success | `text-bg-success` (verde) |
  | Error | `text-bg-danger` (vermelho) |

### O que mudou
- **New Deals (5 páginas):** os 11 badges de status por página (mapa `STATUS_BADGE` + `statusHtml` + inlines de
  transição) migraram de `badge badge-label <cls> rounded-pill` → **`badge <cls> bg-gradient`**. Cores mantidas (já eram
  o padrão). Badges **Quoted** (YES/NO/Missing) permanecem `rounded-pill` (não são status).
- **Intrag Option / Intrag NDF:** já usavam a forma `bg-gradient` (via `OPT_STATUS_META`/`NDF_STATUS_META`); **cores
  alinhadas** à paleta New Deals — **New** `text-bg-secondary`→`bg-info text-white` e **Approved**
  `text-bg-success`→`text-bg-secondary` (Pending/Sent já iguais). Intrag só tem 4 status (New/Pending/Approved/Sent).

### Padrão identificado
- **Badge de status = `badge <cls> bg-gradient` + paleta acima.** Documentado como padrão para novas colunas Status.
  O marcador `badge-label` era o que distinguia status de outros badges nas New Deals; foi removido dos status.

### Arquivos (sessão 40)
```
apps/templates/pages/new_deals-opt-commodities.html   ← status badges → bg-gradient (sem badge-label/rounded-pill)
apps/templates/pages/new_deals-opt-fxo.html           ← idem
apps/templates/pages/new_deals-ndf-commodities.html   ← idem
apps/templates/pages/new_deals-ndf-fwdstart.html      ← idem
apps/templates/pages/new_deals-ndf-otherpublisher.html← idem
apps/templates/pages/intrag-option.html               ← OPT_STATUS_META: New=azul, Approved=cinza
apps/templates/pages/intrag-ndf.html                  ← NDF_STATUS_META: New=azul, Approved=cinza
```

---

## 41. Sessão 2026-07-01 (cont.) — Nova página MtM-Swap (front-end + back-end), réplica da Accrual + COE

Commits: `ee31344` (front-end), `eccd111` (back-end). **Front-end validado no dev (200); back-end com round-trip
de JSON OK; datas ANBIMA conferidas (Jun→30/06/2026, penúltimo Mai→29/05/2026).** Import real depende do share JPM.

### Estrutura (réplica da Accrual-Swap)
- Página **`/mtm-swap`** (template `mtm-swap.html`, copiado da accrual). Sidenav "MtM" → `/mtm-swap`.
- **Widgets:** COE (primeiro) + CEM/EDG/Hybrids/Commodities. **Tabelas:** CEM/EDG/Hybrids/Commodities + **COE (última)**.
- **Books swap** colunas: Código IF, Data Início, PARTE/Conta, Nome Simplificado Parte, CONTRAPARTE/Conta,
  Nome Simplificado Contraparte, Data Vencimento, Valor MTM, Comments (+ checkbox/actions/status).
- **Tabela COE** tem colunas PRÓPRIAS: Código do COE, Nome Simplificado Emissor, Conta Emissor, Nome Figura, Comments.
  Front-end: `MTM_COE_HEADERS` + `headersFor(lob)`. Comments **sempre editável** (MtM não tem status 'check').
- **Date picker default = último dia útil do MÊS ANTERIOR (ANBIMA)** — calc client-side lendo `anbima.json`.

### Back-end (routes.py, seção "MtM")
- Consts: `MTM_SOURCE_ROOT` (`I:\…\Regulatory\MTM`, env), `MTM_JSON_ROOT` (cache/mtm), `_MTM_DISPLAY_SRC=[0,2,3,4,5,7,10,
  None,None]` (A,C,D,E,F,H,K; Valor MTM/Comments sem fonte), `_MTM_COE_SRC=[0,1,2,3,None]`, `_MTM_COE_REFDATE_COL=6`.
- **Swap** (`…SemAtualMID`): filtra **col D = 73760.00-9**; `Código IF`=col A sem `#`; classifica pelo Código Identificador
  da **posição swap mais recente** (`_accrual_lob`: CEMHYB/HYB→Hybrids, COMM→Commodities, EDG, CEM). ⚠️ **Valor MTM vazio**
  (arquivo "sem atualização"); **K→Data Vencimento** (assunção a confirmar).
- **COE** (`…ConsultaMTMCOE`): filtra **col G = último dia útil do PENÚLTIMO mês** (vs. hoje; jul→29/05); A(sem`#`)/B/C/D.
- **Sem header row fixa** — itera todas as linhas e filtra por conta/refdate (cabeçalho/preâmbulo descartados).
- Endpoints `/api/mtm-swap/`: data, latest, import-folder (lê os 2 arquivos de `MTM_SOURCE_ROOT\YYYY\mm. Month\DD`),
  process (dropzone), row/comment|edit|send(maker≠checker)|delete, rows/delete. Notif `MTM Imported|Updated|Sent|Deleted`
  (page 'MtM', deep-link `?date=`).

### Assunções a confirmar com o usuário
1. **K = Data Vencimento** e **Valor MTM vazio** (arquivo é "sem atualização de MID"). Se K for Valor MTM, trocar o mapa.
2. `MTM_SOURCE_ROOT` = `Regulatory\MTM\YYYY\mm. Month\DD` — a imagem mostrava `MTM\2026\2026\...` (**2026 duplicado**).
3. Filtro COE (penúltimo mês) relativo a **hoje**, não à data carregada.
4. `.xls` antigo depende de xlrd (o reader compartilhado cobre xlsx/xlsm/csv/tsv).

### Arquivos (sessão 41)
```
apps/templates/pages/mtm-swap.html            ← (novo) página; COE headers próprios, Comments editável, botões podados
apps/pages/routes.py                          ← rota /mtm-swap + seção MtM (build swap/COE, endpoints, CRUD, datas ANBIMA)
apps/templates/partials/sidenav.html          ← link MtM → /mtm-swap
apps/templates/partials/topbar.html           ← PAGE_URL['MtM'], ACTION_META MTM *, deep-link ?date=
apps/static/data/translations/{en,br,es}.json ← chaves mtm-*
```

---

## 42. Sessão 2026-07-01 (cont.) — Badge de Status em Accrual/MtM no padrão + botões restaurados na MtM

Commit: `87b9945`.

- **Status badge (accrual-swap + mtm-swap):** `statusBadge()` migrou para o padrão da seção 40 — `badge <cls>
  bg-gradient` (removidos `badge-label` e `rounded-pill`). O mapa `ACC_STATUS_BADGE` já usava a paleta padrão
  (New=`bg-info text-white`, Pending=warning, Sent=info, Success=success); acrescenta os status próprios da accrual
  `missing accrual`/`check` (âmbar).
- **MtM — botões restaurados** (usuário: "todos os botões serão necessários no MTM também"): Validation/Recon/End Process
  (date card) e Send batch (por tabela). O **dropzone** continua roteando para `/api/mtm-swap/process` (detecta swap/COE
  por nome) — NÃO usa o branching accrual `fileKind`→recon/factors (classificaria errado os arquivos MtM).
- **Pendente:** back-end MtM de `validation`/`recon`/`end-process`/`send-batch`/`factors` — os botões chamam esses
  endpoints (404 por ora). A semântica no MtM difere da accrual (MtM não tem factors); precisa de spec do usuário sobre o
  que cada rotina faz no MtM (os arquivos `Stream_level_MTM`, `VCP_CETIP_MTM` da pasta provavelmente entram aqui).

### Arquivos (sessão 42)
```
apps/templates/pages/accrual-swap.html  ← statusBadge → bg-gradient
apps/templates/pages/mtm-swap.html      ← statusBadge → bg-gradient; botões Validation/Recon/End Process/Send batch restaurados
```

### Ajuste (commit `11ec336`)
- **Tabela COE ganhou coluna `Valor MTM` antes de Comments.** COE agora: Código do COE, Nome Simplificado Emissor,
  Conta Emissor, Nome Figura, **Valor MTM** (vazio — sem fonte no arquivo, igual aos books swap), Comments. Atualizados
  `MTM_COE_HEADERS` (front) e `_MTM_COE_HEADERS`/`_MTM_COE_SRC=[0,1,2,3,None,None]` (back).
- Confirmado pelo usuário: caminho **sem** `2026` duplicado (`Regulatory\MTM\YYYY\mm. Month\DD`) está correto.





---

## 43. Sessão 2026-07-01 (cont.) — Fix save MtM (mkdir) + cor do status Sent (teal)

Commits: `4a9f38c` (fix save), `354f32c` (cor Sent).

- **Bug MtM save (`4a9f38c`):** `import-folder` e `process` retornavam 500 "Failed to save" — `_atomic_write_json` usa
  `tempfile.mkstemp(dir=…)` que exige o diretório existente, mas o MtM não fazia `os.makedirs`. Novo **`_mtm_save()`**
  cria `cache/mtm/YYYY/MM/DD` antes de gravar (como a accrual). Ambos endpoints agora usam `_mtm_save`.
- **Cor do status Sent (`354f32c`):** New e Sent eram ambos ciano (`#0dcaf0`) e ficavam iguais. Nova classe global
  **`.badge.badge-sent`** (`#17a2b8`, teal, texto branco) em `partials/head-css.html` — mais escuro que o ciano do New,
  sem ficar cinza como o Approved. Sent trocou de `text-bg-info`→`badge-sent` em **todas** as páginas com coluna Status:
  New Deals (5, mapa `STATUS_BADGE` + badges inline dos handlers de send), Intrag (2, `*_STATUS_META`), Accrual, MtM.
  **Passa a integrar o padrão da seção 40:** Sent = `badge-sent` (teal `#17a2b8`).
- **Nota:** o "Network error" no dropzone do usuário (vs. o JSON 500 no dev) indicava servidor dele com `routes.py`
  desatualizado/duplicado (`routes 2.py`) — orientado a `git pull` + apagar `routes 2.py` + restart.

### Arquivos (sessão 43)
```
apps/pages/routes.py                    ← _mtm_save (mkdir antes de gravar); import-folder/process usam _mtm_save
apps/templates/partials/head-css.html   ← .badge.badge-sent (#17a2b8) global
apps/templates/pages/{5 new_deals, intrag-option, intrag-ndf, accrual-swap, mtm-swap}.html ← Sent → badge-sent
```

---

## 44. Sessão 2026-07-01 (cont.) — MtM: mapeia Valor MTM do book CEM (VCP_CETIP_MTM)

Commit: `33c43c4`. **Testado no dev via /process (round-trip): valor 2dp com sinal + comentário de zero OK.**

- **`_cc_read_rows` agora aceita `.txt`** (auto-detecta delimitador: tab > `;` > vírgula — assim os separadores de
  milhar por vírgula dentro dos números não quebram as colunas).
- **Arquivo CEM `VCP_CETIP_MTM`** (A=Trade Name, B=Counterparty Name, C=CETIP ID, D=MTM in BRL; campos vêm entre aspas
  simples): `_mtm_apply_cem_values` filtra **B <> `bco j.p. morgan s.a. 2768 - gem br - rates`** (fica o lado da
  contraparte), casa **C (CETIP ID) → Código IF** do book CEM, e grava **D arredondado a 2 casas (com sinal)** em Valor
  MTM (idx 7). **Valor 0/0.00 → grava `0.00` + Comments `Valor MtM não poder ser ZERO`** (idx 8). `_mtm_parse_num` tira
  aspas + separador de milhar e faz `float`.
- Detecção do arquivo: `_mtm_is_cem_value_name` = nome contém `vcp_cetip_mtm` e não é `.msg` (ignora o e-mail
  `Brazil_VCP_CETIP_MTM….msg`).
- Integrado no **import-folder** (lê o arquivo da pasta e aplica ao CEM antes do finalize) e no **dropzone /process**
  (aplica ao CEM já carregado; exige o swap importado antes). Diagnostics: `cem_value_file/cem_matched/cem_zeros`.
- **Pendente:** arquivos de valor MTM dos outros books (EDG, Hybrids, Commodities, COE) — mesma mecânica, aguardando
  spec de cada arquivo/coluna. Formato de exibição do Valor MTM = `{:.2f}` (ex. `-1802855.65`), sem separador de milhar.

### Arquivos (sessão 44)
```
apps/pages/routes.py   ← _cc_read_rows .txt; _mtm_is_cem_value_name/_mtm_parse_num/_mtm_apply_cem_values;
                         integra no import-folder e /process
```

---

## 45. Sessão 2026-07-01 (cont.) — MtM: Valor formato #,##0.00 + match tolerante; EDG/COE via Stream; sidenav limpo

Commits: `7ca5940` (formato+match CEM), `0df98bc` (EDG/COE Stream), `d59b5c3` (sidenav).

### MtM — valores
- **Formato `#,##0.00`** (`{:,.2f}`) no Valor MTM (ex. `-1,802,855.65`).
- **CEM (VCP_CETIP_MTM):** match da contraparte agora tolerante via `_mtm_norm_party` (remove aspas+acentos+TODOS os
  espaços, lowercase) — robusto a espaçamento/acentos no nome `Bco J.P. Morgan S.A. 2768 - GEM BR - RATES`.
- **EDG/COE (Stream_level_MTM — assumido):** `_mtm_apply_edg_values` — col A=ID, col B=valor. **IDs começando com `JP`
  → tabela COE** (match Código do COE, idx 4/5); **demais → EDG** (match Código IF, idx 7/8). `#,##0.00` com sinal;
  zero → `0.00` + comentário `Valor MtM não poder ser ZERO`. Integrado no import-folder e /process. `.txt` suportado no
  `_cc_read_rows` (auto-detecta delimitador). **Confirmar com o usuário:** nome do arquivo (assumido `Stream_level_MTM`)
  e semântica de "ir para COE" (implementado = mapear valor em linha COE já existente, por match de ID; não cria/move linha).

### Sidenav (`d59b5c3`)
- Removidos: subitem **Email** (Data Base) e as seções demo **Custom Pages** (Pages/FAQ/Pricing/Empty/Timeline/Sitemap/
  Search/Coming Soon/Terms) e **Layouts** (Layout Options/Sidebars/Topbar) inteiras. Components e demais intactos.

### Nota recorrente
- O IDE/macOS voltou a duplicar `routes.py`→`routes 2.py` durante edições; restaurado (routes 2.py = HEAD + DEV BYPASS).
  Se acontecer no ambiente do usuário, apagar `routes 2.py` e garantir `routes.py` real + restart.

### Arquivos (sessão 45)
```
apps/pages/routes.py                    ← formato #,##0.00; _mtm_norm_party; _mtm_apply_edg_values (+ .txt no _cc_read_rows)
apps/templates/partials/sidenav.html    ← remove Email, Custom Pages, Layouts
```

---

## 46. Sessão 2026-07-01 (cont.) — MtM: fix col G, arquivo EDG, geração de arquivos Conecta (Send batch + preview)

Commits: `22651dc` (fixes), `0ecfcff` (geração + preview).

### Fixes (`22651dc`)
- **Nome Simplificado Contraparte** passa a puxar **col G (6)**, não H (`_MTM_DISPLAY_SRC[5]=6`).
- Arquivo de valores EDG/COE detectado por nome base **`EDG`** (`_mtm_is_edg_value_name`, qualquer extensão).

### Geração de arquivos (`0ecfcff`)
- **Backend** (`_mtm_generate_book`/`_mtm_generate_coe`/`_mtm_write_gen_files`): arquivos **fixed-width** por book.
  - Swap (EDG/CEM/HYB): `MtM_BANCO-<suf>` sempre + `MtM_LAWTON/ATACAMA-<suf>` **dinâmico** quando a contraparte
    (col CONTRAPARTE/Conta) for Lawton `00041.00-7` / Atacama `83985.00-5`,`04880.00-6` — linha espelho com **sinal
    invertido**. COE: `MtM_BANCO-COE`.
  - Campos: `ID Sistema="MID  "`, tipo-linha `1` (header `0`), operação `0848` (COE `0475`), Meu Número=10 aleatórios,
    Código Contrato/Instrumento = ID **cru** (sem padding), Nome Parte **20ch** (JPMORGANBM+10 / INTRAGATACAMAFDO+4 /
    INTRAGLAWTONFDO+5), Conta Parte `73760009` (COE Conta Emissor `73760401`), Sinal `00`(>=0)/`01`(<0) [COE Déb/Créd
    `+`/`-`], Valor **abs** zero-pad (swap 10+2=12 díg; COE 16+2=18), Notional min/max = 6 espaços, Data Ref = **datepicker**
    (header usa **hoje**).
  - Salva `.txt` (latin-1, CRLF) em **`CONECTA_NEW_PATH`** (Batch Conecta/New) **e** na **pasta origem MTM do dia**
    (`_mtm_source_dir`).
- **Endpoint** `POST /api/mtm-swap/send-batch` (por book) → escreve arquivos e devolve **preview** (colunas+linhas).
- **Front**: botão Send batch abre **modal de preview** (uma tabela por arquivo, colunas da spec). Testado (BANCO+LAWTON
  com sinal invertido, valor/formato corretos).
- **Pendente:** botão **Validation** = gerar TODOS os arquivos + e-mail (criar template MTM) anexando Lawton/Atacama.
  Confirmar: Conta Parte na visão da contraparte (usei `73760009` fixo conforme spec literal).

### Nota
- Novo episódio de `routes 2.py` (IDE) durante o commit fez o strip falhar; o commit `0ecfcff` saiu **correto** (geração,
  sem DEV BYPASS = HEAD). Recuperado: apagado `routes 2.py`, reanexado DEV BYPASS ao working, `strip(working)==HEAD`.

### Arquivos (sessão 46)
```
apps/pages/routes.py                 ← col G; EDG filename; geração Conecta + /api/mtm-swap/send-batch
apps/templates/pages/mtm-swap.html   ← Send batch → modal de preview
```

---

## 47. Sessão 2026-07-01 (cont.) — Status "Missing MtM" + Comments só em Check + ordem permanente (Missing primeiro)

Commit: `2fd4e4f`.

- **Status "Missing MtM"** (`_MTM_STATUS_MISSING`): ao aplicar valores, IDs **sem** valor MtM correspondente recebem
  status `Missing MtM`. CEM (via VCP_CETIP_MTM) e EDG+COE (via `EDG.*`). Os apply passaram a rodar **após o finalize**
  (linhas já com status em `-4`); `_mtm_apply_cem_values` retorna `(matched,zeros,missing)`, `_mtm_apply_edg_values`
  retorna `(edg,coe,zeros,missing)`. `_mtm_build_from_folder` finaliza antes de aplicar.
- **Comments (MtM)** volta a ser **editável só em status `Check`** (habilitado pela Recon — **ainda não implementada no
  MtM**); travado (texto plano) nos demais. (Correção: não abre em Missing.)
- **Ordem permanente por status** em **accrual E mtm**: `order: [[2,'asc']]` no DataTable + sort key genérico
  (`k.indexOf('missing')===0 ? '0' : '1'`) → qualquer status "Missing …" fica **primeiro**. Badge `missing mtm` = âmbar.
- Testado: CEM com 1 casado (New+valor) e 1 sem match (`Missing MtM`); pages 200.

### Arquivos (sessão 47)
```
apps/pages/routes.py                  ← _MTM_STATUS_MISSING; apply c/ Missing MtM (finalize antes); callers
apps/templates/pages/mtm-swap.html    ← Comments só em Check; badge missing mtm; sort genérico; order [[2,asc]]
apps/templates/pages/accrual-swap.html← sort genérico; order [[2,asc]] (Missing primeiro permanente)
```

---

## 48. Sessão 2026-07-01 (cont.) — MtM: Código Conta Parte por visão + contraparte fixa por book

Commits: `8396790` (Conta Parte por visão), `427873b` (contraparte fixa por book).

### Código Conta Parte por visão (`8396790`)
- Na geração dos arquivos Conecta, o campo **Código Conta Parte** deixa de ser fixo `73760009` e passa a variar
  conforme a visão do arquivo (`_MTM_GEN_PARTY_ACCT`):
  - **Banco** → `73760009`
  - **Lawton** → `00041007`
  - **Atacama** → `85398005`
- `_mtm_swap_fields(cid, party_key, sinal, v, ymd)` usa `_MTM_GEN_PARTY_ACCT[party_key]`.

### Contraparte fixa por book (`427873b`)
- Cada book espelha **somente** as linhas cuja contraparte casa com o lado fixo do book (`_MTM_GEN_BOOK_CPTY`):
  - **EDG → Atacama** (`MtM_ATACAMA-EDG`)
  - **CEM → Lawton** (`MtM_LAWTON-CEM`)
  - **Hybrids → Lawton** (`MtM_LAWTON-HYB`)
- `_mtm_generate_book`: só espelha row (sinal invertido) quando `_mtm_cpty_of(row) == book_cpty`; usa `book_cpty`
  (não a cpty por linha) para nome/party/conta do arquivo. Evita combinações fora da lista (ex.: linha Lawton dentro
  de EDG entra só no `MtM_BANCO-EDG`, **não** cria `MtM_LAWTON-EDG`).
- Testado: EDG → `MtM_BANCO-EDG` + `MtM_ATACAMA-EDG` (conta 85398005); CEM → `MtM_BANCO-CEM` + `MtM_LAWTON-CEM`
  (conta 00041007).

### Pendências MtM (abertas)
- **Botão Validation**: gerar TODOS os arquivos + e-mail (criar template MTM) anexando Lawton/Atacama.
- **Recon MtM**: produzir status `Check` que habilita edição de Comments (ainda não implementado).
- **Arquivos de valor Hybrids/Commodities**: aguardando layout/spec do usuário.

### Nota recorrente
- Novos episódios de `routes 2.py` (IDE/macOS) durante os commits; recuperado antes de cada edição
  (`routes 2.py = HEAD + DEV BYPASS ✓`, `mv` de volta, syntax OK). Commits saíram limpos (`strip==HEAD`, sem DEV BYPASS).

### Arquivos (sessão 48)
```
apps/pages/routes.py   ← _MTM_GEN_PARTY_ACCT (Conta Parte por visão); _MTM_GEN_BOOK_CPTY + _mtm_generate_book (cpty fixa/book)
```

---

## 49. Sessão 2026-07-01 (cont.) — MtM Hybrids: mapeamento via Stream_level_MTM + botão New Mapping

Commit: `4b3c197`.

### mapping_swap-hyb.json (novo)
- `apps/static/data/mapping_swap-hyb.json` — lista de objetos `{b3_id, hybrids_id, trade_name}` (13 seeds fornecidos
  pelo usuário). É a ponte Trade Name (do arquivo de valores) → B3 ID (= Código IF na tabela Hybrids).

### Mapeamento de valor Hybrids (arquivo `Stream_level_MTM`)
- Layout do arquivo: **col A = Trade Name**, col B = Stream ID, C = MTM in pnl currency, D = PNL Currency,
  **col E (idx 4) = MTM in scaling currency** (valor usado), F = Scaling Currency, G+ = SPN/LEOU/contraparte.
- `_mtm_apply_hyb_values(hyb_rows, file_rows, mapping)`: **SUMIF** — soma col E agrupando por Trade Name (normalizado
  via `_mtm_norm_party`, tolerante a espaços/acentos); para cada entrada do mapping resolve `b3_id → Σ`; casa contra
  `Código IF` (row[0]) da tabela Hybrids e escreve **Valor MTM** (`#,##0.00` com sinal; zero → `0.00` + comentário).
  Linha Hybrids sem valor → **status `Missing MtM`** (`row[-4]`). Retorna `(matched, zeros, missing)`.
- `_mtm_is_hyb_value_name` = basename contém `stream_level_mtm`. `_mtm_load_hyb_mapping()` lê o JSON.
- Integrado em `_mtm_build_from_folder` **após o finalize** (mesma ordem de CEM/EDG) + diagnostics `hyb_*`.
  Também roda no `/process` (dropzone) por reusar o mesmo build.

### Botão "New Mapping" (só no card Hybrids)
- `renderTable`: botão extra na toolbar apenas quando `lob.card === 'Hybrids'`; `wireToolbar` liga `.acc-new-mapping`.
- `newMapping()`: modal Swal estilo add-row (New Deals) com 3 inputs + headers (B3 ID / Hybrids ID / Trade Name) e dois
  botões **só-ícone**: save (verde `#157347`, `ti-device-floppy`) e cancel (vermelho `#dc3545`, `ti-x`). `preConfirm`
  valida os 3 campos e faz `POST /api/mtm-swap/mapping/add`.
- **Endpoint** `POST /api/mtm-swap/mapping/add` (`api_mtm_mapping_add`): valida os 3 campos, faz append no JSON via
  `_atomic_write_json(_MTM_HYB_MAP_PATH, ...)`.
- i18n en/br/es: `mtm-new-mapping`, `mtm-nm-required`, `mtm-nm-saved`.

### Teste
- SUMIF verificado: CBA (3 linhas, uma com espaços extras) = `254.995.871,52`; MRS (`-1000,50`+`500,25`) = `-500,25`;
  B3 ID sem match → `Missing MtM`. Rota `/api/mtm-swap/mapping/add` → 401 sem auth (registrada). Servidor 8050 OK.

### Arquivos (sessão 49)
```
apps/static/data/mapping_swap-hyb.json   ← novo (seed do mapping Hybrids)
apps/pages/routes.py                     ← _mtm_apply_hyb_values / _mtm_is_hyb_value_name / _mtm_load_hyb_mapping;
                                            integração no build; endpoint /api/mtm-swap/mapping/add
apps/templates/pages/mtm-swap.html       ← botão New Mapping (Hybrids) + modal newMapping()
apps/static/data/translations/{en,br,es}.json ← chaves mtm-new-mapping / mtm-nm-required / mtm-nm-saved
```

---

## 50. Sessão 2026-07-01 (cont.) — mtm-swap: referências visíveis Accrual → MtM

Commit: `2bf02f2`.

- A página mtm-swap foi copiada da accrual-swap; sobravam textos visíveis "Accrual". Trocados:
  título da aba (`Accrual — Swap` → `MtM — Swap`), banner CSS, comentários, e os Swal de "Missing".
- **Chaves i18n compartilhadas**: os Swal usavam `acc-missing-title`/`acc-factors-missing` (também usadas pela
  accrual-swap). Alterar o VALOR dessas chaves quebraria a página Accrual → criei chaves **MtM-específicas**
  `mtm-missing-title`, `mtm-missing-desc`, `mtm-factors-missing` (en/br/es) e apontei o template para elas.
  **Regra:** nunca reusar/alterar chaves `acc-*` para textos exclusivos do MtM; criar `mtm-*`.
- **Não alterado** (não é visível ao usuário): nomes internos de função JS (`showAccrualPreview`,
  `buildAccrualRecords`, `downloadAccrualFile`, `showMissingAccrual`) e o código de erro de protocolo
  do backend `missing_accrual`. A chave de badge-class `'missing accrual'` foi mantida (inofensiva; MtM usa
  `'missing mtm'`).
- routes.py NÃO entrou no commit (o M local dele é só o bloco DEV BYPASS).

### Arquivos (sessão 50)
```
apps/templates/pages/mtm-swap.html            ← título/banner/comentários + Swal com chaves mtm-*
apps/static/data/translations/{en,br,es}.json ← mtm-missing-title / mtm-missing-desc / mtm-factors-missing
```

---

## 51. Sessão 2026-07-01 (cont.) — MtM: e-mails Validation/End Process + fix duplo-clique

Commit: `9c75f51`.

### E-mails (mesma lógica da Accrual)
- **Remetente/destinatário** (ambos): `otc.tracker@jpmorgan.com` (`SHARED_MAILBOX`) → `brazil.otc.ops@jpmorgan.com`
  (`CETIP_OTC_OPS_EMAIL`). **Sem CC** (a Accrual tem CC Middle Office; o MtM não). Envio em `threading.Thread`
  (SMTP lento não trava a resposta HTTP; arquivos já gravados).
- **`POST /api/mtm-swap/validation`** (`api_mtm_validation`): bloqueia se houver linha `Missing MtM`
  (`_mtm_missing_rows`, retorna `error='missing_accrual'` p/ reusar o modal `showMissingAccrual` do front). Gera TODOS
  os arquivos: `_mtm_generate_book` p/ CEM/EDG/Hybrids + `_mtm_generate_coe` p/ COE; grava via `_mtm_write_gen_files`
  (Batch Conecta + pasta do dia). **Anexa só os arquivos view LAWTON/ATACAMA** (path em `CONECTA_NEW_PATH`). Assunto
  `MtM EOM - dd/mm/yyyy - Validation`. Retorno `{files, attached, total, mail:'queued'}`.
- **`POST /api/mtm-swap/end-process`** (`api_mtm_end_process`): `_mtm_check_status_rows` → bloqueia se algum `Check`
  estiver **sem comentário** (`error='uncommented'`, `pending` → modal do front). E-mail com tabela dos Checks
  (LOB/Código IF/Status/Comment) **ou** bloco "No divergences found". Assunto `MtM Swap - EOM - Final Status - dd/mm/yyyy`.
- **Templates novos**: `email-template-mtm-validation.html` e `email-template-mtm-endprocess.html` (copiados dos da
  Accrual, wording MtM). Mesmas variáveis: validation `{ref_date_fmt, generated_files[filename/view/count],
  attachment_names, current_year}`; endprocess `{ref_date_fmt, has_check, checks[lob/codigo/comment], folder, current_year}`.
- **Layout de linha MtM** (importante p/ helpers): data cells + `[status(-4), maker(-3), checker(-2), id(-1)]`;
  **Comments = índice -5**. NÃO usar o guard `len(r) < 15` da Accrual (linha MtM tem ~13 cells); usei `len(r) < 5`.
- **Pendente:** a **Recon** (define status `Check` e habilita edição de Comments) ainda não existe — usuário enviará a
  lógica. Até lá, End Process cai no caso "no divergence".

### Fix duplo-clique (bug reportado)
- O dblclick na tabela MtM disparava `showAccrualPreview` (preview PU/Factor, Accrual-only) → Swal
  "This swap has no VCP leg to update." **Removido o binding `dblclick.accrow`** no `wireRowActions`. As funções
  `showAccrualPreview/buildAccrualRecords/downloadAccrualFile` ficaram como dead code (inofensivas, não chamadas).

### Arquivos (sessão 51)
```
apps/pages/routes.py                                 ← api_mtm_validation / api_mtm_end_process + helpers + 2 senders
apps/templates/pages/email-template-mtm-validation.html   ← novo
apps/templates/pages/email-template-mtm-endprocess.html   ← novo
apps/templates/pages/mtm-swap.html                   ← remove dblclick preview PU/Factor
```

---

## 52. Sessão 2026-07-01/02 — MtM: Recon (ConsultaInformacoesAtualizMID) + zero→0.01 + End Process Cc

Commit: `cccc961`.

### Recon `POST /api/mtm-swap/recon` (`api_mtm_recon`)
- Arquivo de recon = `ConsultaInformacoesAtualizMID`: **col A = ID** (remove `#`) casa contra `Código IF` da tabela;
  filtro **col D = `73760.00-9`**; **col G = MtM** (linha 8 = header, linha 9+ = dados). Lê do dropzone **ou** da
  pasta do dia.
- Match → status **`Success`** (pill verde). Divergência → **`Check`** (pill vermelho + tooltip com o valor do arquivo)
  e **habilita a edição de Comments** naquela linha. (Fecha a pendência antiga "Recon MtM produz status Check".)
- `valorRender`/`reconPill` renderizam a célula Valor MTM e os pills no mesmo padrão gradiente dos status badges.
- Notificação **'MTM Mapped'** no topbar; chave i18n `mtm-recon-file` (en/br/es).

### Outros no mesmo commit
- **Import zero → 0.01**: MtM zero registra `0.01` (gera `000000000001` no arquivo) + comentário automático.
- **End Process e-mail**: adiciona **Cc** (mesmo From/To/Cc do accrual-swap).
- **accrual-swap**: pills de recon com `bg-gradient` (padroniza com os status badges).

### Arquivos (sessão 52)
```
apps/pages/routes.py                          ← api_mtm_recon + valor/recon render + zero→0.01 + End Process Cc
apps/templates/pages/mtm-swap.html            ← valorRender/reconPill, célula Valor MTM
apps/templates/pages/accrual-swap.html        ← pills recon bg-gradient
apps/templates/partials/topbar.html           ← notificação 'MTM Mapped'
apps/static/data/translations/{en,br,es}.json ← mtm-recon-file
```

---

## 53. Sessão 2026-07-02 — Control Panel / Save Cetip Files: 3º e-mail CEM Latam BA (.OPC)

Commit: `8517b0c`.

- Novo **3º e-mail** (from `otc.tracker@jpmorgan.com`): **To = CEM Latam BA** (5 destinatários; override via env
  `CETIP_CEM_LATAM_EMAILS`), **Cc = brazil.otc.ops**, anexa o arquivo `73760_*_DPOSICAO.OPC` (flag
  `attach_cem_latam` na regra **Option Position**). Saudação `Hello CEM Latam BA,`; reusa o template do Sales Support.
- **Sales Support**: saudação `Good morning` → `Hello, Sales Support.`
- Retorno da rotina inclui `email_sent.cem_latam`.

### Arquivos (sessão 53)
```
apps/pages/routes.py   ← 3º e-mail CEM Latam BA (.OPC) na rotina Save Cetip Files + saudação Sales Support
```

---

## 54. Sessão 2026-07-02 — Dashboard Settlement Forecast: range 15/20/30d + período default Ano Atual

Commit: `866323d`.

- **Card Settlement Forecast (index.html)**: novo dropdown de **range** (15/20/30 dias úteis) além do dropdown de
  período. Backend: `FORECAST_BIZDAYS = 15`, `FORECAST_RANGE_CHOICES = (15, 20, 30)`; `_forecast_spine(anchor, count)`
  usa `count or FORECAST_BIZDAYS`; `_forecast_payload(ref, days)` repassa `count=days` e retorna `'days': len(spine)`;
  `api_cp_forecast_data` valida `days` contra `FORECAST_RANGE_CHOICES`.
- **Dropdown de período** (Current Month/Year/All) passa a **default = Current Year** (os 3 badges Top5 usam
  `dash-filter-year`).
- **dashboard.js**: `_forecastDays=15`, `wireForecastRange()`, `renderForecastSub()` (substitui `{n}` em
  `dash-forecast-sub`; `MutationObserver` no `#forecast-sub` re-preenche após troca de idioma); `loadForecastChart`
  envia `days:_forecastDays`; init chama `loadDashboard('year')` + `wireForecastRange()`.
- ⚠️ **Nota de dev**: `flask run` com DEBUG mostra "Debug mode: off" (sem reload) — alterações em `.py` exigem
  **restart do servidor** para valer. Confundir isso custou tempo depurando "range não muda".
- i18n `dash-fc-range-days` (days/dias/días); `dash-forecast-sub` passou a usar `{n}`.

### Arquivos (sessão 54)
```
apps/pages/routes.py                          ← FORECAST_RANGE_CHOICES + days no spine/payload/endpoint
apps/static/js/pages/dashboard.js             ← range 15/20/30 + subtitle + default 'year'
apps/templates/pages/index.html               ← dropdown range + default Ano Atual + subtitle #forecast-sub
apps/static/data/translations/{en,br,es}.json ← dash-fc-range-days + dash-forecast-sub {n}
```

---

## 55. Sessão 2026-07-02 — New Deals FXO: aviso de prêmio D0 + MtM zero na tabela

Commits: `8421ccf`, `97c279c`, `1b62fe3`, `d604d46`, `e3498d7`.

### Aviso de prêmio D0 (FXO)
- **Bug original**: o botão chamava `/api/new-deals/opt-fxo/premium-email` que **não existia** → `_handleEmailResponse`
  baixava o HTML 404 como `.eml` (falso sucesso). Criado o endpoint espelhando opt-commodities:
  `api_fxo_premium_email()` → `otc_emails.build_premium_emails(deals, asset_label='Taxas de Câmbio', ref_key='FX CASH ACCRONYM')`.
- **"Nenhuma operação"**: FXO grava `Acronym = ref['FX CASH ACCRONYM']`, mas `build_premium_emails` indexava RefData por
  `COMMODITIES ACCRONYM` (códigos diferentes, ex. `ABBELETR` vs `ABBELTBR`). Corrigido com o parâmetro **`ref_key`**;
  `_build_refdata_index(key=...)` passa a aceitar a coluna.
- **`.eml` vazio/sem título**: `_safe_filename` mantinha acentos (`'ê'.isalnum()` → True) → `Content-Disposition`
  não-ASCII pode ser descartado sob gunicorn. Corrigido para **transliterar p/ ASCII** (NFKD + drop combining +
  keep `isascii()`).
- **Contatos/dados bancários não puxados**: `_build_cpdetails_index` casava SPN exato; SPNs FXO podem ter zeros à
  esquerda. Adicionado **`_norm_spn`** (tira `.0` e zeros à esquerda) no index e no lookup `_premium_cliente_email`.
  (Nota: o CounterpartyDetails de dev está sanitizado — 0 contatos/banking; só a resolução de SPN foi validável local.)

### MtM zero → 0.01 na tabela (`e3498d7`)
- Antes, MtM importado = 0 ficava **0 na tabela** e só virava `0.01` nos arquivos/preview. Adicionado
  `_mtm_normalize_zeros(data)` (belt-and-suspenders): converte Valor MTM **exato-zero não-branco → `0.01`** +
  `_MTM_ZERO_COMMENT`, preservando brancos. Roda no `_mtm_build_from_folder` (após applies) **e** no `api_mtm_data`
  (repara legado + persiste). Complementa o zero→0.01 do import da seção 52.

### Arquivos (sessão 55)
```
apps/pages/routes.py         ← endpoint api_fxo_premium_email; _mtm_normalize_zeros (import + load-repair)
apps/pages/otc_emails.py     ← build_premium_emails(asset_label, ref_key); _safe_filename ASCII; _norm_spn no CPDetails
```

---

## 56. Sessão 2026-07-02 — Intrag NDF/Option: coluna Intrag ID + botão/endpoint de mapping + Clear Filters

Commits: `44ff87d`, `edefc08`, `21db3d0`.

### Coluna "Intrag ID" (após Status) — ndf e option
- Nova coluna no índice DOM/data **3** (logo após Status). Todos os índices de coluna dos dois templates foram
  deslocados **+1** (data cols, `row-id`, `TRADE_DATE_COL`/`OPT_REGDATE_COL`, `exportCols`, `columnDefs` hidden,
  `data-column`, `_intragRowData` slice, edit `d[i+4]`, `SF_COLS` dtCol +1). `SF_COLS` ganha
  `{label:'Intrag ID', dtCol:3, type:'text'}` (no option é **push** ao final p/ manter `SF_COLS[3]=Registration Date`).
- **Larguras por coluna**: as regras `nth-child(N)` (inclusive as clonadas em `.dt-scroll-head`) foram bumpadas +1;
  nova regra Intrag ID em `nth-child(4)` = 140px.

### Botão + endpoint de mapping (lê `Boletas*.csv` da pasta Return)
- Botão verde `ti-refresh` (`btnMappingNdf` / `btnMappingOpt`) **após o Add Row**. Coleta as linhas com B3 ID e
  POSTa; ao voltar `Success` preenche a célula 3 (Intrag ID) e seta a célula 2 (Status) → `Success`.
- Backend (**arquivo sem header, casa por conteúdo de linha**):
  - `_intrag_b3_key(v)` = strip + `lstrip('0')`; `_intrag_find_export_csv()` = `boletas*.csv` mais recente em `RETURN_PATH`
    (⚠️ corrigido de `export*` → **`boletas*`** a pedido do usuário); `_intrag_build_b3_map(csv, match_col, match_val, b3_col)`
    (latin-1, sniff `;`/`,`); `_intrag_run_mapping(...)` grava `intrag_id` **e `status='Success'`** via `_cache_lock` +
    `_atomic_write_json`.
  - **NDF**: `col B = 'NDF - TERMO MERCADORIA'`, `col C = B3 ID`, `col A = Intrag ID` →
    `api_intrag_ndf_mapping_intrag_id` = `_intrag_run_mapping(deals, 1, 'NDF - TERMO MERCADORIA', 2, _find_intrag_ndf_entry)`.
  - **Option**: `col C = 'OPCAO'`, `col I = B3 ID`, `col A = Intrag ID` →
    `api_intrag_option_mapping_intrag_id` = `_intrag_run_mapping(deals, 2, 'OPCAO', 8, _find_intrag_opt_entry)`.
- **Atualização retroativa**: o JSON já existente é reescrito com o `intrag_id` da coluna A ("só a data carregada").

### Fixes acessórios
- **Badge de status legado (branco/invisível)** ao puxar operações antigas pelo filtro inteligente: `statusBadge`
  ficou **defensivo** — remove HTML, casa status conhecido case-insensitive, senão cai em `New` (nunca renderiza badge
  sem classe). Adicionado `'Success': text-bg-success` (`intrag-status-success`) ao META de ambos.
- **Clear Filters no intrag-option** (`21db3d0`): era **gap de paridade** (nunca existiu no option, só no ndf), não
  regressão. Botão `btnClearFilters` (`ti-filter-off`) após o Send + handler que zera inputs de coluna,
  `intragDateRanges`, `sfActive`, chips, input e faz `table.columns().search('').draw()`.

### i18n
- `intrag-col-intrag-id` ("Intrag ID"), `intrag-status-success` ("Success"), `btn-clear-filters` (já existia).

### Arquivos (sessão 56)
```
apps/pages/routes.py                          ← helpers _intrag_* + endpoints mapping ndf/option
apps/templates/pages/intrag-ndf.html          ← coluna Intrag ID (idx 3) + botão mapping + statusBadge defensivo + larguras
apps/templates/pages/intrag-option.html       ← idem + botão Clear Filters (paridade)
apps/static/data/translations/{en,br,es}.json ← intrag-col-intrag-id + intrag-status-success
```

---

## 57. Sessão 2026-07-02 (cont.) — intrag-option fixes + New Deals: B3 ID → Success em todas as páginas + FXO JSON em ordem de colunas

Commits: `0714498`, `dae3130`.

### intrag-option: badge Sent, Excel export, dropdown translúcido (`0714498`)
- **`.badge.badge-sent`**: a regra CSS existia no intrag-ndf (`background-color:#17a2b8`) mas **faltava** no option →
  operações antigas em **Sent** renderizavam badge sem fundo (branco/quase invisível). Copiada a regra.
- **Excel não extraía**: o registro do JSZip dependia só de uma IIFE em parse-time (o `ready()` só fazia
  `window.JSZip = JSZip`). Movido o registro completo `$.fn.dataTable.Buttons.jszip(JSZip)` p/ dentro do `ready()`
  antes do init (como no ndf), IIFE redundante removida, `bom:true` no CSV.
- **Dropdown do Export translúcido**: faltava o bloco CSS `div.dt-button-collection` (fundo sólido/borda/sombra) +
  `fade:0`. Adicionado (idêntico ao ndf).

### New Deals: inserir B3 ID no editar → Success (5 páginas) (`dae3130`)
- Regra do usuário: **inserir o B3 ID é o último passo do ciclo** (feito manual quando não há arquivo de retorno
  Conecta p/ mapear). Então preencher o B3 ID no modal de edição de uma linha existente promove o status **direto p/
  Success**, e o PATCH de cada página empurra p/ a Intrag correspondente (gate contraparte Banco JP).
- Frontend: `promoteToSuccess = !!editRowId && !!b3id` (opt-fxo/opt-comm/ndf-comm) e
  `!!editRowId && !!deal.B3_ID` (fwdstart/otherpublisher — estrutura `arBuildDeal`). **Removido** em todas o bloco
  frágil que lia `curStatus` da linha via `editTr` (que ficava stale e jogava p/ Pending). Antes o gate era
  `curStatus === 'Sent' || 'Error'`.
- Backends já existentes: opt-comm→`_maybe_save_intrag_opt`; fxo→`_maybe_save_intrag_fxo`; ndf-comm→`_save_intrag_ndf_entry`
  (7687); fwd-start/other-publishers compartilham o endpoint genérico (9666)→`_save_intrag_ndf_entry`.

### FXO: _optfxo.json em ordem de colunas (`dae3130`)
- Bug: o JSON do FXO vinha com as características em **ordem alfabética** (não ordem de colunas). Nada no código
  atual ordena — a origem é legado; a leitura é toda por chave (`deal.get`), então não quebra display/Intrag, mas
  o usuário pediu ordem de colunas.
- `_FXO_FIELD_ORDER` (= ordem das colunas da tabela / do import) + helper `_fxo_order_deal(d)` (conhecidos em ordem
  canônica, extras preservados, **Maker/Checker por último**). Aplicado em **todos os 4 pontos de escrita**:
  `api_save_fxo_cache` (add/upsert), `api_update_fxo_cache` (PATCH), `api_fxo_bulk_patch_deal_cache`,
  `_fxo_persist_deals` (import/batch). Entradas antigas alfabéticas são corrigidas na próxima gravação.

### Arquivos (sessão 57)
```
apps/pages/routes.py                              ← _FXO_FIELD_ORDER + _fxo_order_deal nos 4 writes FXO
apps/templates/pages/intrag-option.html           ← .badge-sent + JSZip no ready() + div.dt-button-collection + bom/fade
apps/templates/pages/new_deals-opt-fxo.html       ← promoteToSuccess = !!editRowId && !!b3id
apps/templates/pages/new_deals-opt-commodities.html      ← idem
apps/templates/pages/new_deals-ndf-commodities.html      ← idem
apps/templates/pages/new_deals-ndf-fwdstart.html         ← promoteToSuccess = !!editRowId && !!deal.B3_ID
apps/templates/pages/new_deals-ndf-otherpublisher.html   ← idem
```

---

## 58. Sessão 2026-07-03 — MtM-Swap: zero fica 0.00 na tabela + file preview por duplo clique (modelo Accrual)

### Contas de referência (MtM / intragrupo)
| Entidade | Conta      | Dígitos    |
|----------|------------|------------|
| Banco    | 73760.00-9 | `73760009` |
| Atacama  | 85398.00-5 | `85398005` |
| Lawton   | 00041.00-7 | `00041007` |
| MGT      | 04880.00-6 | `04880006` |

**Regras de contraparte (quem opera contra quem):**
- **Atacama** opera **apenas contra o Banco** → gera linha-espelho (visão Banco + visão Atacama).
- **Lawton** opera **apenas contra o Banco** → gera linha-espelho (visão Banco + visão Lawton).
- **MGT** opera **apenas contra o Banco e cliente externo** — **nunca** contra Lawton/Atacama → **não** é contraparte de espelho.
- **Banco** opera com todas + cliente externo.

### Estrutura dos arquivos gerados (por LOB × visão)
Todas as linhas dos books têm o **Banco como parte** (filtro col D = `73760009`). Os arquivos:

| Arquivo          | Conteúdo                                                        |
|------------------|-----------------------------------------------------------------|
| `MtM_BANCO-CEM`  | tudo que for **Banco × Lawton** ou **× cliente externo**        |
| `MtM_BANCO-EDG`  | tudo que for **Banco × Atacama** ou **× cliente externo**       |
| `MtM_BANCO-HYB`  | tudo que for **Banco × Lawton** ou **× cliente externo**        |
| `MtM_LAWTON-CEM` | tudo que for **Lawton × Banco** (espelho, sinal invertido)      |
| `MtM_LAWTON-HYB` | tudo que for **Lawton × Banco** (espelho)                       |
| `MtM_ATACAMA-EDG`| tudo que for **Atacama × Banco** (espelho)                      |
| `MtM_BANCO-COE`  | arquivo único, visão Banco                                      |

`_mtm_generate_book`: sempre grava **todas** as linhas no `MtM_BANCO-<suffix>`; a linha-espelho (sinal oposto) vai ao `MtM_<CPTY>-<suffix>` **apenas** quando `_mtm_cpty_of(row)` == cpty fixa do book (EDG→Atacama, CEM/Hybrids→Lawton). Cliente externo entra só no BANCO. Por isso o file preview mostra 1 linha (externo) ou 2 (intragrupo).

### Valor zero → 0.00 na tabela; 1 na última casa só no preview/arquivo (`58`)
- **Regra:** valores das planilhas entram **exatamente** como estão (só ajuste de formatação `#,##0.00`). Zero (`0.00`) **permanece 0.00 na tabela** + comentário `MtM não pode ser Zero`. Apenas no **preview e no arquivo gerado** o zero vira **1 na última casa disponível** (0.01 → `…0001`), pois a B3 rejeita MtM zero.
- Back-end: `_mtm_apply_cem_values`/`_mtm_apply_edg_values`/`_mtm_apply_hyb_values` e `_mtm_normalize_zeros` **não convertem mais** zero→0.01 (mantêm 0.00 + comentário). Novo helper **`_mtm_gen_min_value(v)`** (0.00→0.01) usado só em `_mtm_swap_fields` e `_mtm_generate_coe`. **Recon** compara via `_mtm_gen_min_value` (página 0.00 casa com o 0.01 registrado na B3 → evita `Check` falso).
- ⚠️ Datasets antigos salvos com `0.01` (regra anterior) continuam `0.01`; só reprocessando o arquivo voltam a `0.00`.

### File preview por duplo clique (modelo Accrual)
- Duplo clique numa linha → **`POST /api/mtm-swap/row/preview`** (`api_mtm_row_preview`): gera as linhas fixo-width **de uma única linha** (mesmo gerador do Send batch: `_mtm_generate_coe`/`_mtm_generate_book`), **sem** escrever em disco. Bloqueia com `missing_mtm` se a linha estiver `Missing MtM`.
- Front-end **`renderMtmRowPreview`** replica o modal da Accrual: **layout vertical** (1 linha por campo, 1 coluna por registro), botões **download (telegram)** + **cancelar (x)**. Contratos intragrupo (Banco × Atacama / Banco × Lawton) mostram **as 2 linhas** (visão Banco + visão contraparte) como colunas. `downloadMtmFiles` baixa cada `.txt` (header + linha(s)). `mtmFilesPreviewHtml` (horizontal) segue sendo usado só pelo Send batch.
- i18n en/br/es: `mtm-rowprev-title`, `mtm-rowprev-missing`.

### Fix `_MTM_GEN_ATACAMA_ACCT` (bug de dígitos trocados)
- Estava `{'83985005', '04880006'}` — `83985005` era **transposição** de `85398005` (Atacama) e `04880006` é **MGT** (não é espelho). Por isso a 2ª linha "Banco × Atacama" **não aparecia**. Corrigido para `{'85398005'}`.

### Arquivos (sessão 58)
```
apps/pages/routes.py                          ← _mtm_gen_min_value; apply/normalize mantêm 0.00; recon via gen_min;
                                                 _MTM_GEN_ATACAMA_ACCT={'85398005'}; endpoint /api/mtm-swap/row/preview
apps/templates/pages/mtm-swap.html            ← dblclick preview vertical (renderMtmRowPreview/downloadMtmFiles)
apps/static/data/translations/{en,br,es}.json ← mtm-rowprev-title / mtm-rowprev-missing
```

---

## 59. Sessão 2026-07-04 — Dashboard (index): passo de refinamento Emil no CSS

Escopo: só CSS do `<style>` de `index.html`. `dashboard.js` **não** tocado (já completo:
`hoverOffset:8`, `duration:700`, `easing:'easeOutQuart'`, gradientes dark-aware em todos os charts).
Preservado o glassmorphism e toda a estrutura; edições cirúrgicas no bloco já existente.

### O que foi feito (correção de anti-padrões Emil)
- **Token de easing:** `#dash-page { --dash-ease-out: cubic-bezier(0.23,1,0.32,1) }`; entrada `.dash-fade-in`
  passou de `ease` fraco → curva forte.
- **Botões:** removido `transition: all 0.25s ease` (animava layout à toa) → props específicas
  (`transform`/cores/shadow). Adicionado **press feedback `.btn:active { scale(0.97) }`** (não existia).
- **Hover gating:** `card:hover` (lift + shadow) e `avatar-title` scale movidos para dentro de
  `@media (hover:hover) and (pointer:fine)` — no toque o `:hover` dava falso-positivo e travava o lift.
- **Curvas custom** aplicadas em `box-shadow`/`transform` das transições de card.
- **Dropdowns origin-aware:** `.dropdown-menu.show` com scale-in `0.17s` + `transform-origin: top right`
  (menus são `dropdown-menu-end`) — nunca de `scale(0)`. Item com `padding-left` deslizando 1.5rem no hover.
- **Seta "View All":** `translateX(3px)` no hover do `.link-reset`.
- **`prefers-reduced-motion`:** mantém os fades (só opacity), zera todo movimento/scale/nudge e troca o
  scale-in do dropdown por fade — exigido pela prática obrigatória (§8).

Nenhum texto novo → sem novas chaves `data-lang`. Tudo escopado em `#dash-page` (sidebar/topbar intactos).

### Padrões identificados nesta sessão
- **`transition: all` é anti-padrão:** listar props específicas (`transform`, cores, `box-shadow`) — mais
  barato e previsível; `all` anima propriedades de layout sem necessidade.
- **Hover sempre atrás de `@media (hover:hover) and (pointer:fine)`** em qualquer efeito de card/ícone —
  no touch o `:hover` "gruda" após o tap e prende o estado (lift/scale).
- **`:active { scale(0.97) }`** é o padrão de press feedback do projeto para botões (alinhado ao Emil;
  Apple usa 0.95 — manter 0.97 aqui por consistência com o resto do dashboard).
- **Dropdown Bootstrap origin-aware:** animar `.dropdown-menu.show` com `transform-origin: top right` para
  `dropdown-menu-end` (cresce do gatilho). Reduced-motion troca por fade puro.

### ⚠️ Nota de ambiente / git
- A branch de trabalho real é **`apple-design`** (checkout principal em `/Desktop/OTC Tracker`). A `main` está
  no boilerplate OTC Tracker original (2 commits) — worktrees criados a partir de `main` **não** têm o projeto real.
  Sempre partir de `apple-design`.

### Arquivos (sessão 59)
```
apps/templates/pages/index.html   ← refinamento Emil no <style> (tokens, :active, hover gating,
                                     dropdown origin-aware, arrow nudge, prefers-reduced-motion)
```

---

## 60. Sessão 2026-07-04 — Dashboard: Swap card, Top 5 unificado, Live Position + mock DB

Escopo: reestruturação do dashboard (`index.html` + `dashboard.js` + `routes.py`) e criação de uma
**base de dados MOCK apenas para teste visual**. Modelo conceitual de 4 cards:
1. **Consolidado** de tudo que foi operado (ano/mês/tudo) — stat cards + distribution + deal flow.
2. **Top 5 Ranking** do que foi operado (Clients / Products / Underlying).
3. **Live Position** — "foto" do que ainda está em estoque/custódia, independente de quando foi operado.
4. **Settlement Forecast** — visão futura do que vai liquidar no range escolhido.

### ⚠️⚠️ REGRA CRÍTICA — nunca commitar a base MOCK
A base de dados de teste **JAMAIS** pode ir para o GitHub — é só para visualização local.
Proteções em vigor (verificadas com `git check-ignore` / `git status`):
- New deals mock → sufixo **`*_mock.json`** → `.gitignore: **/*_mock.json`.
- B3 files mock → sob `apps/static/data/cache/b3 files/` → já ignorado por `b3 files/**/*.json`.
- Gerador **`gen_mock.py`** vive no **scratchpad** (fora do repo), é idempotente (apaga mocks antigos
  antes de regravar), `random.seed(42)`. Contas: BANCO `73760.00-9`, LAWTON `00041.00-7`,
  MGT `04880.00-6`, ATACAMA `85398.00-5`.

### (1) Stat card "Swap Deals" — contagem real (antes fixo em 0)
- `api_dashboard_stats`: `_type_from_product` retorna `NDF`/`OPT`/`SWAP`; adicionado
  `swap_lawton = [d for d in lawton_deals if _fam(d)=='SWAP']`, `swap_total`, `monthly_swap`;
  retorno agora inclui `dist_swap` + `monthly_swap`.
- `dashboard.js`: `buildPieChart(ndf,opt,fxo,swap)` ganhou fatia **Swap** (amber `#f59e0b`);
  `buildFlowChart(...)` ganhou barra empilhada Swap; callers passam `data.dist_swap`/`data.monthly_swap`.

### (2) Top 5 — 3 cards unificados em UM
- Os 3 cards (Clients / Products / Underlying) viraram **um card só**, colunas separadas por
  **linha pontilhada** (`border-end border-dashed`, `row g-0`), estilo do primeiro card.
- **Header único** `Top 5 Ranking` (`data-lang="dash-top5-ranking"`) alinhado à esquerda; cada gráfico
  com **subtítulo** (`<h5 class="fs-sm text-muted fw-semibold mb-3">`).
- **Removidos** os badges coloridos de período ("Current Year"). Canvases: `top5-clients-chart`,
  `top5-products-chart`, `top5-commodities-chart`.

### (3) NOVO card "Live Position" — estoque em custódia por data
- Card abaixo do Top 5 com **date picker à direita**; reference date padrão = **D-1 ANBIMA**
  (`_prev_anbima_bizday`). Puxa a **quantidade de operações ainda em estoque** dos arquivos de posição
  da data escolhida.
- Endpoint **`/api/dashboard-live-position`** (`api_dashboard_live_position`): lê os arquivos de posição
  (`_LIVE_POSITION_SOURCES`: NDF `DPOSICAO-TER` ndfclass, Options `DPOSICAO` optclass,
  Swap `DPOSICAO-SWAP` lob) para a data ref; retorna `ref_date`, `ref_date_fmt`, `total`, `by_product`,
  `by_entity`, `sources`.
- **Breakdown por entidade (esquerda)** — inclui **BANCO** (`73760009`), LAWTON, MGT, ATACAMA na ordem
  fixa `_LIVE_ENTITY_ORDER = ['BANCO','LAWTON','MGT','ATACAMA']` (`_LIVE_ENTITY_MAP`, `_live_map_entity`).
- **Barra por produto (direita)** — **ordem alfabética** (`sorted(by_product)`) e inclui **COE** como item
  fixo em **0** (`_LIVE_PLACEHOLDER_PRODUCTS = ['COE']`, `by_product.setdefault('COE',0)`).
  ⏳ **Pendente:** o usuário enviará a **lógica de contagem do COE** — plugar no `by_product` (o item já existe).
- `dashboard.js`: `buildLivePositionChart(data)` (barra horizontal, gradiente por barra,
  `stackEndRadius(6,'left')`), `renderLiveEntityStats(entities)`, `loadLivePosition(dateStr)`,
  `wireLivePosition()`. Cache em `_liveData`; `rerenderCharts` re-renderiza no theme-switch.
- **Date picker = jQuery `daterangepicker`** (PADRÃO OBRIGATÓRIO, §topo) — assets `moment.min.js` +
  `daterangepicker.js`/`.css` incluídos no próprio `index.html`. `wireLivePosition()` inicializa
  `singleDatePicker` (`DD/MM/YYYY`); `_liveDrp` guarda a instância; sync do D-1 via `setStartDate`.
  ⚠️ Primeira tentativa usou flatpickr "global" — **abandonado** por violar a regra (não confiar no
  bundle; ver `other-products-summary`). Fallback a texto dd/mm/yyyy se o plugin não carregar.
- **Fix classificação LOB de Swap (CEMHYB vinha 0):** `_fcst_lob` testava `'CEM'` **antes** do HYB,
  e o identificador do híbrido contém `'CEMHYB'` (que contém `'CEM'`) → todo híbrido caía em CEM.
  Corrigido testando `'CEMHYB'/'HYB'` **primeiro** (espelha `_accrual_lob`, mesmo campo "Código
  Identificador"). Afeta Live Position **e** Settlement Forecast (função compartilhada).

### Fixes de texto (duplo espaço)
- Settlement Forecast: "`product  as of`" → "`product as of`" (removido `ms-1` de `#forecast-asof`).
- Live Position: mesmo bug entre o texto e "as of" → removido `ms-1` de `#live-asof`.
- Ordem de fade ajustada: Live Position `dash-fade-in-4`, Settlement Forecast `dash-fade-in-5`
  (nova classe `.dash-fade-in-5 { animation-delay: 0.50s }`).

### i18n (7 chaves novas em en/br/es)
`dash-top5-ranking`, `dash-live-title`, `dash-live-sub`, `dash-live-refdate`, `dash-live-total`,
`dash-live-byproduct`, `dash-live-empty`.

### ⚠️ Incidente — `routes.py` sumiu do disco (recuperado)
Durante a sessão, `apps/pages/routes.py` **desapareceu**, substituído por cópias-conflito
`routes 2.py` (Jul 2, antigo) e `routes 3.py` (Jul 4 22:19, atual com todas as edições) — padrão típico de
**sync iCloud/IDE** (projeto está no `~/Desktop`). Restaurado a partir de `routes 3.py` (compila, byte a byte
igual), servidor sobe do `routes.py` restaurado, endpoint validado. Depois **confirmado idêntico e as duas
cópias numeradas foram apagadas** — sobrou só `routes.py`.
**Recomendação:** mover o projeto para fora do Desktop/iCloud (ex.: `~/dev/OTC Tracker`) ou desativar o sync
nessa pasta; fechar abas duplicadas no editor.

### Validação
Servidor em **http://127.0.0.1:8050/dev-login**. `/api/dashboard-live-position` (ref D-1 = 2026-07-03):
`total 175 | entities ['BANCO','LAWTON','MGT','ATACAMA'] | products ['COE','NDF Commodities','NDF Moeda',
'Option Commodities','Option EDG','Option FXO','SWAP CEM','SWAP CEMHYB','SWAP EDG']`.

### Arquivos (sessão 60)
```
apps/pages/routes.py                          ← swap_total/dist_swap/monthly_swap; _LIVE_* maps/order/placeholder;
                                                 _LIVE_POSITION_SOURCES; endpoint /api/dashboard-live-position
apps/templates/pages/index.html               ← Top 5 unificado (1 card, border-dashed); card Live Position
                                                 (date picker D-1, entity stats, canvas); fixes duplo-espaço; fade-in-5
apps/static/js/pages/dashboard.js             ← Swap no pie/flow; Live Position (build/load/wire, gradiente por barra)
apps/static/data/translations/{en,br,es}.json ← 7 chaves dash-top5-ranking / dash-live-*
scratchpad/gen_mock.py (FORA do repo)         ← gerador idempotente da base MOCK (NUNCA commitar os *_mock.json / b3)
```

---

## 61. Sessão 2026-07-05 — Other Products Summary: card NDF Commodities (contagem correta) + robustez de snapshot + Swap alfabético

Escopo: consertar a contagem de liquidação do card **NDF Commodities** na página
**Other Products Summary** (`/other-products-summary`), que não puxava os deals liquidando
na data do picker a partir do `DPOSICAO-TER`. Backend em `_ops_settlement_counts`
(`routes.py`). Commits: `e68e6e1`, `dca138c`, `66b9e9c`, `7715385`.

### Regra da contagem NDF Commodities (o que o card faz)
Conta operações onde, no **último JSON de posição TER disponível**:
`Data de Vencimento` (formato **yyyymmdd** no json, ex. `20260702`) == data do picker
(o picker manda **yyyy-mm-dd**; o backend compara via `_fcst_parse_date` → objetos `date`,
então formato não importa) **E** `Classe do Ativo Subjacente` == `COMMODITIES`.

### (1) Snapshot por família (`e68e6e1`)
- `_forecast_latest_ref()` escolhe **uma data global** (1ª pasta com QUALQUER arquivo).
  Se o TER não estava salvo nessa data exata → `os.path.isfile` falhava e o loop dava
  `continue` **em silêncio** → card NDF = 0 enquanto Swap/Option mostravam número.
- Novo helper **`_ops_src_latest_path(src)`** — cada família resolve a SUA própria data
  de snapshot mais recente (walk-back D-1 ANBIMA, 10 dias úteis). `log.warning [ops] …`
  quando não acha arquivo (não zera mais em silêncio).

### (2) Resolver de coluna por match EXATO (`dca138c`)
- `_fcst_resolve_key`: **igualdade exata** de nome tem prioridade sobre "contains".
  Assim `data de vencimento` casa a coluna literal "Data de Vencimento" mesmo que exista
  "Data de Vencimento Antecipado" (que contém a string). Token NDF passou a
  `['data de vencimento', 'vencimento']`.

### (3) Card NDF delega ao `_forecast_collect` (`66b9e9c`) — paridade com o index
- O card NDF agora **reutiliza `_forecast_collect`** (mesma função do Settlement Forecast do
  `index.html`): spine de 1 dia na data do picker, lê `by_product['NDF Commodities'][0]`.
  Garante que os dois cards **nunca divergem** (mesmo arquivo, mesmo campo de data, mesmo
  mapeamento `Classe do Ativo Subjacente → NDF Commodities` via `_fcst_ndf_product`).
- `ndf` é pulado no loop por-fonte (`if fam == 'ndf': continue`); Swap/Option/COE seguem
  no loop com sub-eventos (flow/premium/maturity) que o forecast não quebra.
- Frontend verificado e limpo: template (`ops-w-ndf-total`/`-maturity`), JS (`w.ndf`) e
  i18n (`ops-w-ndf`="NDF Commodities" em en/br/es) todos consistentes.

### (4) Card Swap em ordem alfabética (`7715385`)
- Sub-linhas reordenadas: **Flow → Maturity → Premium** (só ordem visual das divs).

### Arquivos (sessão 61)
```
apps/pages/routes.py                          ← _ops_src_latest_path; _ops_settlement_counts
                                                 (NDF delega a _forecast_collect); _fcst_resolve_key
                                                 (match exato); _FORECAST_SOURCES ndf date token
apps/templates/pages/other-products-summary.html ← card Swap: sub-linhas Flow/Maturity/Premium
```

---

## 62. Sessão 2026-07-05 (continuação) — Other Products Summary: card Swap tipo=2 → Flow vs Maturity

Escopo: no card **Swap** do `/other-products-summary`, um swap **tipo de contrato = 2** é um
contrato de **fluxo** (aparece no `DFLUXO` com vários eventos). Antes, o card contava tipo=2
sempre como **Maturity** (via `DPOSICAO-SWAP`, `Data Vencimento == picker`) e **todos** os eventos
do `DFLUXO` na data do picker como **Flow** — sem distinguir se o evento de fluxo era o
**pagamento final (vencimento)** ou um **fluxo intermediário**. Commit `ee4509c`.

### Regra implementada (`_ops_settlement_counts`, `routes.py`)
Join por **`Código Identificador`** entre `DPOSICAO-SWAP` e `DFLUXO`:
1. **Maturity** — `DPOSICAO-SWAP`, tipo=2, `Data Vencimento == data do picker` → conta em Maturity
   (inalterado). Agora também guarda o `Código Identificador` desses contratos em `swap_mat_ids`.
2. **Flow** — `DFLUXO`, `Data de Ocorrência do Evento == data do picker`, **exceto** se o
   `Código Identificador` estiver em `swap_mat_ids` (vencimento do contrato = data do picker):
   nesse caso o evento é o pagamento final → **pulado** (não duplica com Maturity).
3. tipo=2 com `Data Vencimento ≠ picker` e evento de fluxo na data do picker → cai em **Flow**.

`swap_pos` roda **antes** de `swap_flx` na ordem de `_FORECAST_SOURCES`, então `swap_mat_ids` já
está populado quando o Flow é lido. Novo helper de resolução: `id_key = _fcst_resolve_key(keys,
_ID_TOKENS)` com `_ID_TOKENS = ['código identificador','codigo identificador','identificador']`.

### Padrão identificado
- **Split Flow/Maturity de swap tipo=2:** o `DFLUXO` sozinho não sabe qual evento é o vencimento;
  é preciso cruzar com `DPOSICAO-SWAP` por `Código Identificador`. O evento cuja data coincide com
  o `Data Vencimento` do próprio contrato é Maturity, não Flow.

### ⚠️ Nota de dados (mock)
No mock atual os IDs de `DPOSICAO-SWAP` e `DFLUXO` **não têm overlap** (gerados aleatoriamente),
então as contagens do mock não mudam. A lógica está correta para os arquivos **reais**, onde um
contrato tipo=2 aparece nos dois arquivos com o mesmo `Código Identificador`.

### Arquivos (sessão 62)
```
apps/pages/routes.py   ← _ops_settlement_counts: swap_mat_ids + join Código Identificador
                          (swap_flx exclui eventos de contratos que vencem na data do picker)
```

---

## 63. Sessão 2026-07-05 — NOVA página Live Position › Swap › Characteristics

Rota **`/live-position-swap-characteristics`** (sidenav *Daily Settlement › Live Position › Swap ›
Characteristics* — o item já existia, só troquei o `href` de âncora para a rota). "Foto" read-only do
book de swap em custódia numa **reference date** (default **D-1 ANBIMA**), lida do **DPOSICAO-SWAP**
(mesma fonte do card Live Position do dashboard). Commit `114d2f8`.

### Layout (fiel ao projeto)
1. **5 widgets** (modelo `ops-widget`): Tipo de Contrato (Cashflow/Bullet), LOB (CEM/EDG/COMM/HYB),
   Indexadores (VCP/Calculado), Funcionalidades (Forward Start/Notional/Prêmio/Arrependimento/Sem
   Funcionalidade) e **Total** (card azul destacado).
2. **Filtro inteligente** (modelo New Deals: chips por coluna + dropdown com badge de tipo) + Clear +
   **card de reference date** (daterangepicker `dd/mm/yyyy`, D-1 ANBIMA; padrão obrigatório do §topo:
   jQuery próprio antes dos plugins + init resiliente com retry).
3. Toolbar **Columns** (`ti-columns`) + **Export** (Copy/CSV/Excel) e **tabela** (checkbox + Status +
   146 colunas de características).

### Backend (`_swapchar_*` em routes.py)
- **`_SWAPCHAR_LABELS`** = lista canônica das 146 colunas (idêntica a
  `_B3_SWAP_HEADERS_RAW['swap_position']`). Vive no servidor (single source of truth); o endpoint
  devolve `columns` + `rows` (**arrays posicionais** — resolve os nomes de coluna duplicados, que um
  dict colapsaria).
- **`_swapchar_collect(ref)`**: lê DPOSICAO-SWAP; hoje bindam **Tipo (idx0), Contraparte (idx7),
  Data vencimento (idx12), Funcionalidade (idx20), Código Identificador (idx145)** — únicas presentes
  no arquivo; resto placeholder. Widgets: Tipo (1=Cashflow/2=Bullet) e LOB (`_swapchar_lob`:
  HYB→COMM→EDG→CEM) computam; **Indexadores e Funcionalidades ficam em 0** (⏳ usuário enviará a lógica
  de contagem).
- **Formatações:** `_swapchar_fmt_cell` por tipo de coluna (`_swapchar_coltype`): **date** →
  `dd/mm/yyyy` (via `_fcst_parse_date`); **func** → `_swapchar_func_text`; **value** →
  `_swapchar_fmt_value` (`#,##0.00`, guard numérico).
- **Funcionalidade (`_SWAPCHAR_FUNC_MAP`):** código → texto limpo (sem `_`/parênteses):
  0 SEM FUNCIONALIDADE · 1 KNOCK IN · 2 KNOCK OUT · 3 KNOCK INOUT · 4 SWAPTION · 5 COMPOUND ·
  **6 OPCAO ARREPENDIMENTO** · 7 KNOCK IN COM OPCAO · 8 KNOCK OUT COM OPCAO · 9 SWAP COM PRÊMIO.
  Fallback textual (`OPCAO_ARREPEND` → `OPCAO ARREPENDIMENTO`).
- Endpoint **`/api/live-position-swap-characteristics/data?date=`** (default D-1 ANBIMA).

### Padrões / notas
- **Colunas com nomes repetidos → arrays posicionais**, não dict. Header e dados nunca desalinham.
- **Front-end monta o `<thead>` e as `columns` do DataTables a partir do `columns` do servidor** —
  a lista de 146 nunca é duplicada no template/JS.
- Validado em servidor de teste (porta 8051, não tocar na 8050 do usuário): 45 linhas, 146 colunas,
  Tipo 24/21, LOB CEM 18/EDG 12/HYB 15, datas dd/mm/yyyy.

### Arquivos (sessão 63)
```
apps/pages/routes.py                                       ← _SWAPCHAR_*, _swapchar_*, rota + endpoint
apps/templates/pages/live-position-swap-characteristics.html ← CRIADO
apps/static/js/pages/live-position-swap-characteristics.js   ← CRIADO
apps/templates/partials/sidenav.html                       ← href do item Characteristics
apps/static/data/translations/{en,br,es}.json              ← 21 chaves sc-*
```

### Ajuste 63.1 (commit `1557c21`) — subconjunto de colunas + pull posicional + fix Export
- **Tabela reduzida a 66 colunas** (subconjunto do layout do desk, não as 146): índices em
  **`_SWAPCHAR_DISPLAY_IDX`** (0-based na lista de 146), derivados das letras de coluna do Excel das
  fotos de referência. `_SWAPCHAR_DISPLAY_LABELS = [_SWAPCHAR_LABELS[i] for i in _SWAPCHAR_DISPLAY_IDX]`.
- **Valores lidos POSICIONALMENTE** (`list(row.values())[i]`): o JSON de posição salvo (headerless
  parseado com `_B3_SWAP_HEADERS`) carrega os 146 campos **em ordem**, então índice = posição, e os
  nomes de coluna repetidos resolvem sem ambiguidade. Fallback name-resolve só para o **mock esparso**
  (4 campos): `full = len(vals) >= 120`.
- **Fix do dropdown Export translúcido** aplicado (bloco `.dt-button-collection` **não escopado** —
  ver padrão obrigatório no topo do handoff).
- Validado: mock esparso (66 cols, 4 campos nos lugares certos) + json full-width sintético de 146
  valores (`V0..V145` → cada célula na posição correta, `Data vencimento 20260715 → 15/07/2026`).

### Ajuste 63.2 (commit `0ce4228`) — linha de filtro por coluna
- Segunda linha no `<thead>` (`.sc-th-filter`) com `<input>` por coluna (padrão `accrual-swap`);
  checkbox e Status sem filtro. **`orderCellsTop: true`** (sort na linha de título, não no filtro) +
  `autoWidth: true` para alinhamento com `scrollX`. Wire `keyup/change` → `dt.column(col).search().draw()`.
- **Coexiste com o smart filter:** `reapplyChips` reaplica os inputs da linha de filtro junto com os
  chips; o botão **Clear** limpa ambos.

### Ajuste 63.5 (commit `78422fd`) — header/body desalinhados: remover scrollX
- Com `scrollX: true` o DataTables **clona o thead** numa tabela separada (`.dt-scroll-head`) e o body fica
  em `#swapchar-table` → as larguras divergem (header desalinha do body) e o thead interativo/inputs podem
  ir para o clone. Para esta tabela a solução robusta é **`scrollX: false` + `autoWidth: false`**: header e
  body ficam na **mesma tabela** (nunca desalinham) e o `.table-responsive` (overflow-x) provê o scroll
  horizontal; as larguras vêm do bloco `nth-child`. (Nas páginas New Deals, que usam scrollX, o alinhamento
  depende de `table.columns.adjust().draw(false)` após o load — ver `_fixTableHeader`.)

### Ajuste 63.4 (commit `5778abc`) — filtro estilo New Deals + fix Tipo 01/02 + Search/Clear + larguras
- **Fix Tipo de Contrato:** o arquivo real traz `01`/`02` (zero à esquerda). O código comparava com
  `'1'`/`'2'` → coluna mostrava "01" e o widget Contract Type ficava 0/0. Corrigido normalizando com
  `if tv.isdigit(): tv = str(int(tv))` (display **e** widget). Agora `01→Bullet`, `02→Cashflow` contam.
- **Linha de filtro por coluna** repaginada no padrão New Deals (`form-control form-control-sm`) + polish
  Emil (foco Action Blue, transição 150ms curva forte, `sc-has-val` tint, hover gated) — ver padrão no topo.
- **Botão Search** (`btn btn-secondary bg-gradient btn-search`) no lugar do antigo Clear ao lado do smart
  filter (commita o chip). **Clear filters** movido para o card da tabela, ao lado do Export (limpa chips +
  inputs da linha de filtro).
- **Bloco de larguras por coluna** (`nth-child` 1..68, um por coluna com o nome no comentário) no `<style>`.
- i18n: +`sc-search`; `sc-clear-filters` → "Clear filters/Limpar filtros/Limpiar filtros".

### Ajuste 63.3 (commit `ad57497`) — Tipo de Contrato invertido + Tipo de amortização mapeado
- **Tipo de Contrato:** `01 → Bullet`, `02 → Cashflow` (⚠️ invertido do que estava) — na célula da
  tabela **e** na contagem do widget Contract Type (`bullet`/`cashflow`).
- **Tipo de amortização (idx38):** novo tipo de coluna **`amort`** (`_swapchar_coltype` →
  `_SWAPCHAR_AMORT_MAP`/`_swapchar_amort_text`). Mostra o texto no lugar do número, sem parênteses:
  `00 Sobre Valor Base Original · 01 Sobre Valor Base Remanescente · 03 Na Data de Vencimento ·
  04 Sem Troca de Amortização`. Fallback extrai o texto entre parênteses se o arquivo já vier "NN (texto)".

---

## 64. Sessão 2026-07-05 — Save CETIP Files: INDEXADORESSWAP_VCP → VCP.json (existente)

Adicionado o arquivo **`CETIP21_YYMMDD_INDEXADORESSWAP_VCP.TXT`** à rotina **Salvar Arquivos CETIP**
(`_CETIP_RULES`): é salvo na pasta de destino e, após salvar, **atualiza o `VCP.json` JÁ EXISTENTE**
(`apps/static/data/VCP.json`, 2195 linhas — tabela de qualificações). Commits `83ecb20`, `fdda01a`.

⚠️ **Correção `fdda01a`:** a 1ª versão criava um `vcp_indexers.json` novo — **errado**. O alvo é o
`VCP.json` existente (consumido por `index-b3.html` e por `routes.py:~9058`). Schema dele:
`STATUS` (ACTIVE/INACTIVE) · `ID da Qualificação` (int) · `Descrição da Qualificação` ·
`Descrição Adicional da Qualificação` · `Classificação Nível 1` · `Produto` (SWAP/OPC) · `MAKER` · `CHECKER`.

### Regra + upsert
- Nova entrada em `_CETIP_RULES` (`match: 'indexadoresswap_vcp.txt'`, `date_start: 8`,
  `dest_name: CETIP21_{}_INDEXADORESSWAP_VCP.TXT`, flag **`'vcp_update': True'`**). Por estar em
  `_CETIP_RULES`, entra no fluxo de save e no "missing" quando ausente.
- **`_cetip_update_vcp_json(src_path)`** (`VCP_JSON`): ';'-delimitado, Latin-1, pula header se presente.
  Colunas do arquivo: **A=Qualification ID, B=Description, C=Additional Description,
  D=Level 1 Classification, E=Status** — `Habilitado→ACTIVE` / `Bloqueado→INACTIVE`.
- **UPSERT por `ID da Qualificação`** (não sobrescreve o arquivo inteiro): IDs existentes têm
  STATUS/descrições/classificação atualizados (**MAKER/CHECKER preservados**); IDs novos são
  adicionados com `Produto=SWAP`, MAKER/CHECKER null. Linhas não presentes no arquivo (ex.: as **42 OPC**)
  ficam intactas. Validado em cópia: update ACTIVE→INACTIVE + novo ID + 42 OPC preservadas.

### Pendente
- ⏳ Plugar o `VCP.json` no widget **Indexadores (VCP/Calculado)** da página Swap Characteristics
  quando o usuário enviar a lógica de classificação.

### Arquivos (sessão 64)
```
apps/pages/routes.py   ← _CETIP_RULES +INDEXADORESSWAP_VCP; VCP_JSON;
                          _cetip_update_vcp_json (upsert por ID no VCP.json existente); hook no save
```

---

## 65. Sessão 2026-07-05 — NOVA página Other Products › OTM Settlements + card Control Panel

### Página `/otm-settlements` (commit `a819c53`)
Sidenav *Daily Settlement › Other Products › OTM* (o item já existia apontando p/ `/other-products-otm`
sem rota — apontei p/ `/otm-settlements`). Substitui a macro VBA "Settlement - OTM". Modelada na Swap
Characteristics (widgets + filtro por coluna + Columns/Export + date picker; **sem** scrollX).
- **4 widgets:** RATES, EQUITIES, COMMODITIES, **TOTAL** (card azul). Contam **Trade Ids ÚNICOS** por
  **Asset Class** (`_otm_asset_bucket`: COMMODITIES→commodities, EQUITIES→equities, INTEREST_RATE→rates);
  um Trade Id pode ter várias linhas. TOTAL = nº de Trade Ids distintos. **Cpty Name** é salvo **UPPER**
  no JSON (no `_otm_import`).
- **Tabela:** checkbox, actions (placeholder), status (Break Reason vazio→OK / preenchido→Break) + as
  **18 colunas** (`_OTM_COLUMNS`). Datas dd/mm/yyyy, Amount `#,##0.00`. Bloco de larguras `nth-child`.
- **Import (`/api/otm-settlements/import`):** replica `CleanSettlementOTM` da macro — lê `cashflows_*.xlsx`
  de `OTM_SOURCE_ROOT` (tratado como **TAB-delimited**, como o VBA `OpenText Tab:=True`; fallback xlsx-zip
  real via openpyxl). Limpeza: (A) descarta linhas com **col 14 == "DELETE"**; (B) normaliza **col 22** p/
  texto 4 dígitos; (C) mantém só col 22 ∈ **{0228, 0123}**. Extrai as 18 colunas **por nome de header**,
  grava `static/data/cache/daily settlement/YYYY/MM/DD/otm-settlement_YYYYMMDD.json` (**today**) e **deleta
  o .xlsx** consumido. Validado: kept 2 / deleted 1 (DELETE) / filtered 1 (código fora).
- `.gitignore`: `apps/static/data/cache/daily settlement/**/*.json` (dados de runtime, não commitar).
- Endpoint de leitura: `/api/otm-settlements/data?date=` (default today).

### Card Control Panel "Save Daily Settlement Files" (commits `c5e43f4`, `facdf5b`, `229dea3`)
- `.cp-card` na coluna **Daily Settlements / File-Saving Routines** (ao lado do Save CETIP Files).
- **Dropzone** (`facdf5b`): no lugar do date picker, um dropzone dependency-free (drag/drop + click, chips
  com remover). Os arquivos ficam anexos e só processam ao clicar **Save files**. Se o dropzone estiver
  vazio, o backend varre **`SETTLEMENTS_ROOT`** (`I:\…\OTC Tracker\Settlements`); se não houver nada em
  ambos → **Swal de aviso** ("Nenhum arquivo encontrado…").
- **Processamento (`229dea3`, `382231f`) — tradução dos imports de texto do VBA `ImportarTexto`** (OpenText
  Tab). `_DS_IMPORTS` (um spec por arquivo): lê tab-delimited (fallback xlsx-zip), pega a linha de header
  (1-based), filtra as linhas e grava um JSON por tipo em
  `static/data/cache/daily settlement/YYYY/MM/DD/<tipo>_YYYYMMDD.json` (today). Arquivos da **pasta** são
  deletados após processar (mirror do VBA `Kill`); uploads do dropzone não. As **fórmulas Excel de
  enriquecimento** (Tipo/Contraparte via XLOOKUP) **NÃO** entram (não são "import de texto").
- **`382231f` — OTM incluído no card:** o card agora processa **TODOS** os arquivos, inclusive o OTM
  (`cashflows*`). O núcleo do OTM virou **`_otm_extract(rows)`** (limpeza CleanSettlementOTM + 18 colunas +
  Cpty UPPER), reusado pela página OTM **e** pelo card. Spec com flag `'otm': True` → `_ds_handle` usa
  `_otm_extract` e grava no **mesmo** `otm-settlement_YYYYMMDD.json` que a página OTM lê. **Cada página
  mantém o processamento individual** (a OTM tem seu `/api/otm-settlements/import`). `_ds_write` extraído
  para o append/delete comum.

  | Arquivo (match) | Header | Filtros | JSON |
  |---|---|---|---|
  | `cashflows*` | — | CleanSettlementOTM (col14≠DELETE, col22∈{0228,0123}) → 18 colunas (`_otm_extract`) | otm-settlement |
  | `Operacoes*` | linha 5 | col2 dígitos=`73760009` **e** col10 ∈ {OPC,OFVC,OFCC,SWAP,TER,COE} | operacoes-jpm |
  | `MGT.*` | linha 5 | col2 dígitos=`04880006` **e** col10 ∈ {…} | operacoes-mgt |
  | `Swap-InstrumentoFinanceiro-ConsultaContrato*` | linha 7 | col2=`CONFIRMADO` **e** col23 dígitos=`73760009` | eventos-swap-jpm |
  | `SwapMGT.*` | linha 7 | col2=`CONFIRMADO` **e** col23 dígitos=`04880006` | eventos-swap-mgt |
  | `FXO Detail*` | linha 1 | (nenhum; pula se A1="No Data Available…") | tss-fx |
  | `BrazilOnshoreSettlementsWarningFile*` | linha 1 | (nenhum) | br-onshore-settlements |
  | `FbiRptLatamDeskPo*` | linha 1 | col62 **ou** col63 não-vazia (`nonempty_any`) | latam-desk-position |

  Validado (dropzone): OTM 1/3, Operações JPM 2/4, Eventos Swap 1/3, BR Onshore 2/2, Latam 3/4. ⏳
  Enriquecimento/destinos finais ficam para depois. (BR On/Latam usam `Workbooks.Open` no VBA — o
  `_ds_read_rows` trata tab-delimited/xlsx-zip; filtro OR via kind `nonempty_any`.)
- i18n: `cp-r-ds-*`, `cp-ds-*`, `cp-nofiles-title`; página OTM: `otm-*`.
- **About (`6bfd26a`):** novo grupo **Daily Settlement** em `about.html` (cards Swap Characteristics, OTM
  Settlements, Other Products Summary) + descrição do Control Panel atualizada; i18n `about-cap-dailysettle`,
  `about-feat-swapchar/-otm/-opssum-*`.
- Show entries (padrão New Deals) adicionado em OTM/Swap Characteristics/Other Products Summary
  (commits `e0ce5fb`, `4f83ff1`, `53bf70b`): OTM default 200 (200,500,1000..10000); OPS Trade Level
  default 50 (50..300).

### Arquivos (sessão 65)
```
apps/pages/routes.py                          ← OTM_* (source/json roots, _OTM_COLUMNS), _otm_read_rows/
                                                 _otm_import/_otm_collect, rotas /otm-settlements + /api/...;
                                                 stub api_cp_daily_settlement_save
apps/templates/pages/otm-settlements.html     ← CRIADO
apps/static/js/pages/otm-settlements.js       ← CRIADO
apps/templates/pages/control-panel.html       ← card Save Daily Settlement Files
apps/templates/partials/sidenav.html          ← href OTM → /otm-settlements
apps/static/data/translations/{en,br,es}.json ← otm-*, cp-r-ds-*/cp-ds-*
.gitignore                                    ← cache daily settlement
```

---

## 66. Sessão 2026-07-05 — NOVA página Operations B3 + timestamp "última atualização"

### Página `/operations-b3` (commit `8449ed7`)
Sidenav *Daily Settlement › B3 Files › Operations* (o item já existia com âncora morta → apontei p/
`/operations-b3`). **Mesmo padrão do OTM Settlements** (widgets + filtro por coluna + Columns/Export +
date picker + Show entries; sem scrollX). Vista curada do arquivo B3 "Operações".
- **14 colunas** (`_OPB3_COLUMNS`): Conta, Tipo Operação, C/V, Título, Tipo Título, Tipo de Regime,
  Data Vencimento, Valor, Modalidade Liquidação, Status, Data Liquidação, Contraparte (Nome Simpl.),
  Conta Contraparte, Num Ctrl Operação. (+ checkbox/actions/status padrões). Datas dd/mm/yyyy, Valor `#,##0.00`.
- **Import (`/api/operations-b3/import`):** varre `OPB3_SOURCE_ROOT` (default = `SETTLEMENTS_ROOT`) por
  `Operacoes*`, lê via `_ds_read_rows` (mesma lógica do Save Daily Settlement Files). **Header na LINHA 5**,
  dados da linha 6 → JSON só da linha 5 pra baixo (`_opb3_extract`). **Deleta** o fonte após. JSON:
  `daily settlement/YYYY/MM/DD/operations-b3_YYYYMMDD.json`.
- **Widgets dinâmicos** (`_opb3_breakdown`): **Tipo Operação**, **Tipo Título**, **Modalidade Liquidação** —
  cada um com **total + sub-itens por valor distinto** (contagem, ordenado por count desc). 4º card = **Total**
  (nº de operações). Sub-itens renderizados no front (`renderWidgets`/`renderSubs`). ⏳ ajustar métricas depois.
- **Timestamp "última atualização"** ao lado do date picker: vem da **LINHA 2, COLUNA A** do arquivo
  (HH:MM:SS, ex. `17:21:12`) — o horário de extração.

### Timestamp — sidecar meta (OTM + Operations B3)
- `<json>.meta.json` = `{"updated": "HH:MM:SS"}` (helpers `_ds_meta_path`/`_ds_write_updated`/`_ds_read_updated`;
  fallback = mtime do arquivo). OTM usa o **horário do import** (o cashflows não tem horário no arquivo);
  Operations B3 usa a **linha 2 col A**. Ambas as páginas exibem `#*-updated` ao lado do date picker.
- Coberto pelo `.gitignore` (`daily settlement/**/*.json` pega o `.meta.json`).

### Arquivos (sessão 66)
```
apps/pages/routes.py                          ← _ds_meta/_ds_write_updated/_ds_read_updated; OTM updated;
                                                 OPB3_* + _opb3_extract/_opb3_import/_opb3_collect/_opb3_breakdown;
                                                 rotas /operations-b3 + /api/operations-b3/{data,import}
apps/templates/pages/operations-b3.html       ← CRIADO
apps/static/js/pages/operations-b3.js         ← CRIADO
apps/templates/pages/otm-settlements.html     ← span #otm-updated
apps/static/js/pages/otm-settlements.js       ← seta timestamp (t('updated'))
apps/templates/partials/sidenav.html          ← Operations → /operations-b3
apps/static/data/translations/{en,br,es}.json ← ob-*
```

---

## 67. Sessão 2026-07-05 — Padrão botões de Action (formato) + Add row via modal

### Botões de Action — só o FORMATO (commit `fd63f27`)
Padronizado o **formato** dos botões da coluna Actions para **quadrados arredondados** (não círculos),
via CSS **global** em `apps/templates/partials/head-css.html`. Um único bloco mira as classes funcionais
já existentes (`btn-row-edit/delete/confirm/send/approve`, `acc-act-edit/send/del`, `ops-row-del`,
`ar-confirm/edit/delete`, `btn-rd-edit/confirm/delete`) forçando `30×30px`, `border-radius:7px !important`
(vence o `rounded-circle !important` do Bootstrap por vir depois no `<style>` do head) e centralização do
ícone. **Nenhum markup/handler alterado** — cada página mantém seus botões, cores semânticas
(`btn-info`/`btn-success`/`btn-danger`/`btn-primary`) e conjuntos (algumas têm Send, outras só Delete).
⚠️ Foi pedido explicitamente: **"o padrão do formato apenas, não os botões em si"** — por isso OTM/
Operations B3 (que têm só um kebab placeholder) **não** ganharam botões edit/approve/delete.

### Add row → modal (commit `54f5d1e`)
Padrão: toda ação **Add row** abre um **modal com um campo por coluna** (como os New Deals `#addRowModal`),
em vez de linha inline em branco. A única página que usava add-row **inline** era a
`other-products-summary` → convertida: `#opsAddModal` (modal-lg) com `#opsAddFields` gerado dinamicamente
a partir dos headers da tabela (pulando checkbox/actions/status); o botão Add abre o modal guardando a `dt`
ativa em `_opsAdd`; o Save monta a linha (`[checkbox, actionsCell, statusCell('New'), inp(v)…]`) e faz
`dt.row.add(...).draw()`. Células continuam editáveis inline, semeadas com os valores do modal.
i18n: `ops-add-title/save`, `ops-cancel`. (mtm-swap não tem add-row; index-b3-results já era "new_deals style".)

Ambos os padrões estão registrados no topo do handoff como **PADRÃO OBRIGATÓRIO**.

### Arquivos (sessão 67)
```
apps/templates/partials/head-css.html          ← CSS global do formato dos botões de action
apps/templates/pages/other-products-summary.html ← #opsAddModal + handler abre modal + Save (row.add)
apps/static/data/translations/{en,br,es}.json  ← ops-add-title/save, ops-cancel
```

---

## 68. Sessão 2026-07-05 — Páginas NDF: Live Position NDF + NDF Summary

### Live Position NDF (`/live-position-ndf`, commit `3d92ef6`)
Sidenav *Daily Settlement › Live Position › NDF* (item existia com âncora morta → apontei p/ a rota).
**Clone do Live Position Swap Characteristics** (widgets + smart filter chip bar + Search + per-column
filter + Columns/Export + Show entries + date picker; sem scrollX, tabela única). Adaptações:
- **14 colunas** (`_LPNDF_COLUMNS`, iguais às de Operations B3): Conta, Tipo Operação, C/V, Título,
  Tipo Título, Tipo de Regime, Data Vencimento, Valor, Modalidade Liquidação, Status, Data Liquidação,
  Contraparte (Nome Simpl.), Conta Contraparte, Num Ctrl Operação. Resolvidas **por nome de header** no
  `DPOSICAO-TER` (arquivo TER tem header próprio). Datas dd/mm/yyyy, Valor `#,##0.00`.
- **Bloco Média Asiática dinâmico:** para linhas com `Tipo Media Asiática == ARITMETICA`, as colunas
  **depois** dessa coluna trazem datas `yyyymmdd` (data a data). São anexadas como colunas dinâmicas
  (`_lpndf_collect`): só valores `yyyymmdd` (8 dígitos) são considerados, exibidos dd/mm/yyyy; demais em
  branco. Rótulos = header da fonte ou "Média Asiática N".
- **Widgets** = placeholders (Metric A/B/C + Total = nº de operações). ⏳ definir métricas.
- Fonte: `_ndf_ter_path` (walk-back D-1 ANBIMA por `73760_YYMMDD_DPOSICAO-TER.json`). Endpoint
  `/api/live-position-ndf/data?date=`.
- ⚠️ O mock TER tem só 8 colunas (sem os 14 nomes nem o bloco asiático) → na dev aparece a estrutura com
  células vazias; no arquivo real (headers batendo) popula.

### NDF Summary (`/ndf-summary`, commit `3d92ef6`)
Sidenav *Daily Settlement › NDF › Summary*. **Base: Other Products Summary** (mantido o `#ops-page` +
classes `ops-` p/ reusar todo o JS: initTable, add-row modal, show entries, colvis, delete, filtro).
- **4 cards** no topo (de `/api/ndf-summary/cards`, lê o último `DPOSICAO-TER`): **Vanilla, Other
  Publisher, T+0, Total**. Total = nº de operações; Vanilla/Other/T+0 = placeholder 0 (⏳ classificação).
- **Trade Level** (11 colunas, imagem): LEGAL, HM COUNTERPARTY, ID_SOURCE_DEAL, VL_NOTIONAL_FC,
  VL_FORWARD_RATE, SETTLEMENT, ID_CETIP, CCY, SETTLEMENT_B3, VL_FIXING_RATE, DIFFERENCE.
- **Settlement Summary** (7 colunas): Counterparty, Receive, Pay, Settlement Net, Direction,
  Internal Account, Observação.
- Tabelas são worksheet manual (add-row via modal — padrão). i18n `ndf-c-*`, `ln-*`.

### Arquivos (sessão 68)
```
apps/pages/routes.py                          ← _LPNDF_COLUMNS/_ndf_ter_path/_lpndf_collect + rotas
                                                 /live-position-ndf + /api/...; /ndf-summary + /api/ndf-summary/cards
apps/templates/pages/live-position-ndf.html   ← CRIADO (clone swap-characteristics)
apps/static/js/pages/live-position-ndf.js     ← CRIADO
apps/templates/pages/ndf-summary.html         ← CRIADO (base other-products-summary)
apps/templates/partials/sidenav.html          ← NDF>Summary → /ndf-summary; LivePos>NDF → /live-position-ndf
apps/static/data/translations/{en,br,es}.json ← ln-*, ndf-c-*
```

---

## 69. Sidenav drill-down (master → detail) — nova navegação

**Pedido:** trocar o comportamento do sidenav: ao clicar num item COM subitens, em vez de
expandir a lista para baixo (accordion do tema), o menu **desliza** para mostrar **apenas os
subitens daquele item**, com **breadcrumb no topo** para voltar os níveis. Só o COMPORTAMENTO
muda — o visual/estrutura dos itens é mantido.

**Como foi feito (não mexer no HTML dos itens):**
- Novo `apps/static/js/sidenav-drilldown.js` (incluído no `partials/footer-scripts.html` DEPOIS do
  `app.js`). CSS scoped no `<style>` de `partials/sidenav.html` (prefixo `dd-`).
- **DESACOPLADO do menu original:** o `ul.side-nav` do tema é apenas **escondido**
  (`.dd-source-hidden { display:none !important }`) — o `app.js`/Bootstrap/SimpleBar continuam
  operando nele sem efeito visível. O drill-down vive num container próprio `.dd-nav` (crumbs +
  `.dd-stage`). Cada nível é um **`ul.side-nav` novo** (clones dos `<li>`) → herda 100% do estilo do
  tema (hrefs, `data-lang`, lucide, `.active`).
- ⚠️ **GOTCHA CRÍTICO — capturar o menu ANTES do app.js:** o `<script>` roda durante o parse do body
  (antes do `DOMContentLoaded`), então captura um **clone PRISTINE** do `ul.side-nav` logo no topo do
  IIFE (`var PRISTINE = ...cloneNode(true)`). Se clonar depois, o `app.js` já expandiu collapses e o
  Bootstrap está no meio da animação (`.collapse`↔`.collapsing`), o que **corrompe o parse/strip** →
  o accordion vaza e o auto-open falha. Todo o build usa `PRISTINE`. O strip remove QUALQUER
  `.collapse, .collapsing, ul.sub-menu` (querySelectorAll, à prova de estado de animação).
- Um **branch** = `<a>` com submenu vira gatilho de drill-in (removido `data-bs-toggle`). Setas: o
  tema usa `chevron-down` (▾) por padrão; forço `.dd-branch .menu-arrow { transform: rotate(-90deg)
  !important }` → sempre **▸ (direita)**. **Leaf** = link normal. **Back row** no topo de cada nível.
- **Breadcrumb** para no **penúltimo nível** (todos os crumbs são clicáveis); o nível atual NÃO entra
  no breadcrumb pois já aparece na back row (evita duplicação). Esconde no root (`.dd-at-root`).
- **Auto-open:** no load abre direto no nível da página atual (match `location.pathname` × href do
  leaf) e marca `.active`. Crumb raiz = literal "Menu" (NÃO usar `menu-title` — traduz p/ "Navigation").
- **i18n:** clones carregam `data-lang` → `applyTranslations()` global traduz. Chamadas de globais do
  browser são qualificadas (`window.lucide`, `window.requestAnimationFrame`).

**Animação (skill /emil-design-eng):** só `transform`/`opacity` (GPU), ease-out forte
`cubic-bezier(.23,1,.32,1)`, 240ms, **CSS transitions** (interrompível, não keyframes). Painel entra
de `translateX(100%)`/`opacity .35` (nunca `scale(0)`); no back entra da esquerda. O painel que sai é
congelado como overlay `position:absolute` para o painel novo (em fluxo) **definir a altura** — sem
animar layout/height. Stagger leve das linhas (26ms, cap 9) só na entrada. `prefers-reduced-motion`:
controller pula o slide, CSS remove transforms/stagger. Press feedback: `scale(.96)`/`.985`.

**Testado (jsdom + headless Chrome no runtime real com app.js):** `/otm-settlements` e `/dashboard`
→ original escondido, **0** collapse/submenu vazando, auto-open (`Menu / Daily Settlement / Other
Products`), breadcrumb no penúltimo, setas ▸, drill/back/crumb ok. ✅ (Testar sobre o HTML cru NÃO
reproduz o bug do accordion — precisa do DOM pós-app.js; ver gotcha acima.)

**Refinamentos (mesma sessão, pós-1º commit):**
- **Cor do breadcrumb:** usar `var(--ins-sidenav-item-color)` / `-hover-color` (com `inherit` ficava
  quase invisível no sidenav escuro).
- **Ícones nas transições:** `lucide.createIcons()` varre o DOM ao vivo, então tem que rodar DEPOIS
  que o painel entra no DOM (`refreshIcons()` após o `appendChild` nos 2 caminhos da transição) —
  senão os `<i data-lucide>` do painel novo ficam sem converter (invisíveis) ao drillar/voltar.
- **Index no root:** `/dashboard` (e `/`) NÃO auto-drilla nos subitens de Dashboards; mostra o root
  com "Dashboards" destacado (`INDEX_PATHS`).
- **Só root tem ícone:** em níveis não-root o `.menu-icon` dos itens é removido no `fillPanel`
  (`if (openPath.length) remove`). A back row mantém o chevron.
- **SWAP→Swap / OPTION→Option:** literais em caixa alta no `sidenav.html` corrigidos + `es.json`
  (estava `SWAP`/`OPCIÓN`). ⚠️ o `applyTranslations` do tema é método do `I18nManager` (NÃO existe
  `window.applyTranslations`), então os painéis do drill mostram o LITERAL do HTML — por isso o
  literal precisa já estar no caso certo.

**Limitação conhecida:** modo **condensed** (sidebar só-ícones com fly-out no hover) usava a estrutura
`.collapse` que agora fica oculta — nesse modo o drill funciona mas sem texto/breadcrump ideais. Não
foi pedido; refinar se necessário.

### Arquivos (sessão 69)
```
apps/static/js/sidenav-drilldown.js        ← CRIADO (controller drill-down)
apps/templates/partials/sidenav.html       ← CSS dd-* no <style>
apps/templates/partials/footer-scripts.html← inclui sidenav-drilldown.js após app.js
```

## 70. Sessão 2026-07-06 — Live Position NDF: todas as datas da média asiática (dd/mm/yyyy, cap 60)

**Pedido:** no Live Position NDF só aparecia a **primeira** data da média asiática; precisa mostrar
**todas** (algumas ops têm >40 datas). O padrão no JSON é trio de colunas por fixing: **coluna com a
data / coluna vazia / coluna com 0** — trazer **apenas as colunas com as datas**, formatadas
**dd/mm/yyyy** no front. Depois: **limitar a 60 colunas** (chegava a 145, inviável).

**Como foi feito (`_lpndf_collect`, `routes.py`, commits `76426ac` + `6dd4933`):**
- As chaves de coluna passam a vir da **UNIÃO ordenada de TODAS as chaves de todos os registros**
  (antes usava só `data[0]`, que na op vanilla-first não tinha o bloco asiático) — preserva a ordem
  de aparição.
- `date_keys = [k for k in asian_keys if any(is_yyyymmdd(rec.get(k,'')) for rec in data)]` — só
  entram colunas em que **algum** registro tem um valor `YYYYMMDD` válido (descarta a vazia e o 0).
- **Cap:** `_LPNDF_MAX_ASIAN = 60`; `date_keys = date_keys[:_LPNDF_MAX_ASIAN]`.
- Labels sequenciais `'Média Asiática {}'.format(i+1)`; cada valor formatado **dd/mm/yyyy** por célula.

**⚠️ Nota de dados (dev):** o TER JSON do cache local é uma variante reduzida de 8 colunas (sem bloco
asiático), então **não dá para testar com dado real localmente** — validado com dado sintético
(vanilla-first + 3/5 linhas com data → 5 colunas; 200 datas → cap 60).

### Arquivos (sessão 70)
```
apps/pages/routes.py   ← _lpndf_collect (união de chaves, filtro is_yyyymmdd, cap 60, fmt dd/mm/yyyy) + const _LPNDF_MAX_ASIAN
```

## 71. Sessão 2026-07-06 — Intrag Option (filtro server-fetch + filtros de coluna) + Export Excel + Notificações

**(1) Filtro inteligente = busca no servidor (não filtro de tabela) — `eabd1d6`.**
Pedido: a Intrag Option tem que funcionar como a **Intrag NDF** — o filtro inteligente **busca** as
operações nos JSONs (server-fetch), não filtra linhas já carregadas. Apagar o filtro **não** pode
mostrar todas as linhas geradas.
- Em `pages/intrag-option.html`: `SF_COLS` marca Registration Date com `isDate=true`; novo `_dmyToIso`;
  `intragOptLoad()` → `intragLoad(qs, colFilters)` que faz `GET /api/intrag/option?qs`. O botão Search
  monta `qs` a partir dos chips de data (`date=` / `date_from` / `date_to`) + chips de coluna
  client-side. Removidos `applyOptFilters()` e a auto-chamada ao remover chip / backspace.
- Load inicial: `sfAddFilter(SF_COLS[3], _todayDmy()); sfSearchBtn.click();`.
- **Backend não mudou** — `/api/intrag/option` já aceitava `date`/`date_from`/`date_to`.

**(2) Filtros de coluna Status e Intrag ID — `eabd1d6`.**
Na linha de filtros por coluna, os `<th>` de **Status** e **Intrag ID** estavam vazios. Adicionados
`<input placeholder="Status">` e `<input placeholder="Intrag ID">`.

**(3) Export Excel não funcionava (na verdade: linhas vazias) — `eabd1d6`.**
Causa raiz (achada via teste de paginação jsdom): `fmtExport`/`formatExportData` liam do **DOM
`node`**, que é **null** para linhas fora da página atual → o book exportava ~metade das linhas
vazias. Fix: usar o **model `data`** quando `node` é null.
```js
function fmtExport(data, row, column, node){
  if (node){ var inp=$(node).find('input[type!="checkbox"]'); if(inp.length) return inp.val()||''; }
  return (data==null?'':String(data)).replace(/<[^>]*>/g,'').trim();
}
```
Aplicado em **8 páginas** (intrag-ndf, intrag-option, pending-confirmation, 5 new_deals). Adicionado
`title:'…'` aos botões Copy/CSV/Excel/Print. Verificado: **0** linhas vazias após o fix.

**(4) Notificações — "Mark All as Read" fecha o dropdown — `eabd1d6`.**
Em `partials/topbar.html`, após marcar tudo como lido, fecha o dropdown via
`bootstrap.Dropdown.getOrCreateInstance(toggle).hide()`.

**(5) Badges DATE/NUMBER do filtro inteligente invisíveis — `ced199c`.**
A Intrag Option só tinha `.sf-type-text`; faltavam `.sf-type-date`/`.sf-type-number` (a `.sf-type-badge`
força `color:#fff` sem fundo → branco no branco). Adicionadas iguais à NDF:
`.sf-type-date{background:#0dcaf0;color:#000!important}` e `.sf-type-number{background:#ffc107;color:#000!important}`.

### Arquivos (sessão 71)
```
apps/templates/pages/intrag-option.html   ← SF server-fetch, filtros Status/Intrag ID, fmtExport, CSS badges DATE/NUMBER
apps/templates/pages/intrag-ndf.html       ← fmtExport (fallback model data)
apps/templates/pages/pending-confirmation.html + 5 new_deals-*.html ← formatExportData (fallback model data)
apps/templates/partials/topbar.html        ← Mark All as Read fecha o dropdown
```

## 72. Sessão 2026-07-06 — Padrão SÓLIDO de badges/botões nas páginas Daily Settlement (`97d9ce7`)

**Pedido:** adotar como **padrão** o estilo **sólido** do Intrag (badge cheio + botão de ação
circular sólido) nas páginas Daily Settlement recém-criadas (que estavam no estilo *soft*).

**Padrão SÓLIDO (referência = Intrag NDF):**
- **Badges:** `<span class="badge {cls} bg-gradient">` — New=`bg-info text-white`,
  Pending=`text-bg-warning`, OK=`text-bg-success`, Sent=`badge-sent` (#17a2b8).
- **Botões de ação:** `btn btn-{cor} btn-sm rounded-circle btn-row-{ação}` — Edit=`btn-info`,
  Confirm=`btn-success`, Delete=`btn-danger`, Send=`btn-primary`; tamanho **28px** via CSS scoped
  (`width:28px;height:28px;flex:0 0 28px;padding:0;border-radius:50%;inline-flex center`).

Aplicado em `operations-b3.js`, `otm-settlements.js`, `ndf-cockpit.js` (statusBadge + actionsHtml) e
o CSS 28px nos respectivos `.html`. **Já documentado como padrão** na seção de maker/checker.

### Arquivos (sessão 72)
```
apps/static/js/pages/{operations-b3,otm-settlements,ndf-cockpit}.js ← statusBadge + actionsHtml sólidos
apps/templates/pages/{operations-b3,otm-settlements,ndf-cockpit}.html ← CSS 28px botão circular + bump ?v
```

## 73. Sessão 2026-07-06 — NOVA página Live Position › Option (`c741069`, `99cb00b`)

Clone da **Live Position NDF** (seção 68) trocando NDF→Option. Fonte: `Option/…/73760_{dref}_DPOSICAO.json`
(gerado do `DPOSICAO.OPC`, header próprio → resolução por NOME). Rota `/live-position-option`, API
`/api/live-position-option/data`. **60 colunas** do book de opções (`Código IF … Trigger Proporção`),
datas (`Data …`) → dd/mm/yyyy, valores (`Valor …`) → #,##0.00. Bloco dinâmico **"Média Asiática (data) N"**
para colunas `yyyymmdd` extras não mapeadas (cap 60). Filtro inteligente + per-column + Columns/Export
(mesmo motor da NDF). Sidenav Live Position › Option agora aponta pra rota real (era placeholder).

**Fix `99cb00b`:** reference date default = **hoje** aparecia vazio (o daterangepicker não escreve o
campo no init) → seto `input.value` explícito; e a tabela não carregava porque `wireDatePicker()` rodava
ANTES de `load()` — se o plugin falhasse, bloqueava tudo. Reordenei: `load()` primeiro, resto em
try/catch. Bump `?v`.

**⚠️ Nota (dev):** o `DPOSICAO.json` local é uma variante reduzida (poucas chaves) → células vêm vazias
na dev; com o arquivo real (header completo) as colunas resolvem por nome.

### Arquivos (sessão 73)
```
apps/pages/routes.py                            ← _LPOPT_* + _opt_dposicao_path + _lpopt_collect + rota/API
apps/templates/pages/live-position-option.html  ← CRIADO (larguras genéricas p/ 60 colunas)
apps/static/js/pages/live-position-option.js    ← CRIADO (ids lo*/lnopt-*)
apps/templates/partials/sidenav.html            ← link Option → /live-position-option
```

## 74. Sessão 2026-07-06 — NOVA página Reconciliation › Pay/Rec (engine do Alteryx PayRec)

**O quê:** bate pagamentos × recebimentos (lado JPM × lado cliente), reproduzindo o fluxo Alteryx
"PayRec". Página `/reconciliation-payrec` (skill /emil-design-eng): **dropzone que segura os arquivos até
clicar Run** (nada automático) + botão **Import from folder** (pasta de rede) + **Run** + **End process**.
Blocos: **Summary**, **Pending Payment**, **Pending Receivement**, **Settled** (headers navy, chips OK/Not OK).
Módulo dedicado `apps/pages/recon_payrec.py`. Rotas em routes.py: page + `/data` + `/run` + `/end-process`.

### Pipeline (VERIFICADO contra o gabarito do Alteryx — 10 settled, Summary OK/OK/OK)
Extraído via subagente que leu `scripts/Codigo_VBA_TratarArquivos.` (arquivo de apoio Alteryx, **gitignored**,
NUNCA commitar). Lado **JPM/Cockpit** (Union de 3 fontes):
- **`settlement.csv`** (CSV `,` com aspas) → **NDF**: valor = `Tax Income + Amount`, filtro
  `Settlement Net ∈ {TOTAL_NET, PAYREC_NET}`, **soma por `Client`**; Product='NDF', cpty=Client UPPER.
- **`cashflows_*.xlsx`** (sheet `data`) → **COMM TER / SWAP**: filtros `Owner Legal Entity=0228`,
  `Cashflow Event≠DELETE`, `!Contains(Cpty,'Bco J.P.')`, exclui Bilateral (`BANCO`). **Netting por cliente**
  (as pernas de ~12,5M do Lawton somam 230.927,66). COMM TER = Trade Id com >1 perna; SWAP = Asset Class
  INTEREST_RATE. Nomes Lawton/Atacama/BcoJP canonizados.
- **`FXO Detail*.xlsx`** (sheet `FXO Detail`) → **FXO**: valor = `ATH SET AMT`, `Direction=PAY`→negativo.

Lado **cliente** (Union de 3 fontes, `;` Latin-1):
- **`rlctahis.csv`** (SDConta interna): **allowlist `nHistorico`** {9409,4407,9410,4408,9411,4419,9385,4413,
  9386,4414,4406,AA,4409} (redutor principal); remap `5347/0512026-0 → 9409` **E** `sDescricao='DEBITO NDF'`
  (FX transfer da conta câmbio → Receive); DEBITO→Receive/senão Pay; drop `sNomeTitular='/OTC DERIVATIVES
  PRODUCTS'`; threshold `|v|>1`.
- **`rlDocTed01.csv`** (SDConta externa TED): valor=`nValor` ABS, titular=`sNomeEmissor`,
  conta=`nBancoEmissor-nAgDebitada-nCcDebitada`, sistema `SDConta - conta externa`, sDescricao='DEBITO NDF'→Receive.
- **`HistoricoMensagensJPM_*.csv`** (SPB externa): filtro `Descrição Evento` contém `Derivativos`/`LMA-COMM-BR`
  (o `Status='Sucesso'` do Alteryx é MORTO — a planilha real nem tem essa coluna); nome = `Replace('Operacao
  de Derivativos-','')` + `Replace('LMA-COMM-BR ','')`; sempre Pay (valor negativo).

**Match:** valor arredondado à unidade (join só por valor), greedy 1-para-1; `Difference = Client − JPM`;
Settled se `|diff| < 0,005` (senão Pending); tolerância SPB `diff > -0,50`. **Summary** agregado por
Pay/Receive: Check Qty = qtde igual; Check Value = `|somaJPM − somaCli| < 1` (TOTAL usa < 0,005).

### ⚠️ Gotchas críticos (descobertos iterando com dados reais)
- **Parse numérico BR vs US por célula:** CSVs BR (`.`=milhar `,`=decimal); cashflows/FXO xlsx podem vir US
  do pandas. `_num()` auto-detecta (ver regra dot-only 3-dígitos = milhar). Leitura CSV tenta `;`+Latin-1,
  depois `,`+aspas+UTF-8. **Errar isso deu 28 bilhões** (linha de saldo não filtrada + parse errado).
- **IR 0,005% no COMM TER:** aplica **só quando o NET é Pay** (negativo), **sobre o líquido** (NÃO por perna —
  por perna quebra o Lawton, que tem perna de pagamento mas net Receive). AMG (net Pay -219.047,36) → com IR
  → **-219.036,41** (casa). **Fundos internos Lawton/Atacama são ISENTOS** de IR (`_IR_EXEMPT_CPTY`).
- **settlement.csv:** manter `TOTAL_NET` **E** `PAYREC_NET` (o YARA é PAYREC_NET e precisa entrar).
- **`_ds_process`/leitura:** os statements têm `sNomeTitular` que NÃO pode ser `/OTC DERIVATIVES PRODUCTS`.
- Testado montando os 6 arquivos sintéticos que reproduzem o dia → **10 settled, 0 pending, TOTAL 4.906.489,04**.

### End process + histórico (`7ee9def`)
Ao clicar **End process**: (1) salva o status do dia em **`static/data/cache/payrec/yyyy/mm/dd/payrec_status_
yyyymmdd.json`** (histórico permanente, gitignored), independente do e-mail; (2) envia e-mail. Mudar a
**reference date** puxa o status salvo daquele dia (`load_last` prioriza histórico finalizado → cache de
trabalho → vazio) e **limpa a tela** se não houver. `_load_flat(date)` NÃO faz fallback pro `_last` (senão
mostrava o último resultado em qualquer data). Reference date default = **hoje** (`be40a2c`).

### E-mail (template próprio)
`send_payrec_email` → `pages/email-template-recon-payrec.html` (Summary + Pending + Settled, headers navy).
To=`brazil.otc.ops@jpmorgan.com`, **Cc = Renato + Danilo** (`renato.montoza@jpmorgan.com`,
`danilo.camposfonseca@jpmchase.com` — mesmos do Settlement Forecast/MTM/Accrual `_ACC_ENDPROC_CC`).
Assunto **em inglês, sem prefixo**: `Pay/Rec — OTC Settlement Status - dd/mm/yyyy`. Swal do End process
pergunta só "deseja enviar?" (sem citar destinatários).

### Arquivos (sessão 74)
```
apps/pages/recon_payrec.py                          ← CRIADO (engine completo)
apps/templates/pages/reconciliation-payrec.html     ← CRIADO
apps/static/js/pages/reconciliation-payrec.js       ← CRIADO
apps/templates/pages/email-template-recon-payrec.html ← CRIADO
apps/pages/routes.py                                ← 4 rotas payrec
apps/templates/partials/sidenav.html                ← link Reconciliation › Pay/Rec
apps/static/data/translations/{en,br,es}.json       ← chaves pr-*
.gitignore                                          ← scripts/Codigo_VBA_TratarArquivos* + cache/payrec/**
```

## 75. Sessão 2026-07-06 — NOVA página Daily Settlement › Other Products › Option › Cognos (`baab78b`, `a91adff`)

Clone do **OTM Settlements** (seção 65) trocando `otm`→`cog`. Fonte: **`FXO Detail - Beta.xlsx`** (header
ROW 1). Rota `/cognos`, API `/api/cognos/data` + `/import` + CRUD (`/row/{add,edit,delete,confirm}`).
Maker/checker (`_cg_*`), JSON por dia (`cognos_YYYYMMDD.json` no cache daily settlement), modal glass.

- **37 colunas** (`_COG_COLUMNS`): `Athena ID … Direction`. O arquivo tem ~100 colunas (A..CU); resolvo por
  NOME. **Duas "Client Type"** (col S e col CM) → a 2ª entra como `Client Type 2` (mapeada positionalmente
  via `_COG_DUP_HEADER`, exibida como "Client Type"). `col_idx` usa set `used` p/ não repetir índice.
- **Datas → dd/mm/yyyy** (`_COG_DATE_COLS`): PRM DUE DT, Expiry Date From/To, TRN DT, Trade Date, Event Trade
  Date, OPT STRT/END/SET DT. `_cog_fmt_date` trata `yyyy-mm-dd` **e** `Event Trade Date` = `jul 2, 2026
  12:00:00 AM` (`%b %d, %Y %I:%M:%S %p`).
- **Widgets** adaptados: **Call / Put / Total** (contados por `Call Put Indicator`).
- **SEM filtro de linhas** — mantém TODAS as linhas com dado (confirmado: o Alteryx NÃO tem fluxo Cognos;
  FXO Detail lá só alimenta o PayRec com 3 colunas). Só filtra COLUNAS (as 37 de ~100).
- **Duas formas de importar:** botão "Import FXO Detail" na página **OU** Control Panel (a regra `_DS_IMPORTS`
  que casava `fxo detail` — era `tss-fx`, sem consumidores — virou `cognos` com flag `cog` em `_ds_handle`).

### Arquivos (sessão 75)
```
apps/pages/routes.py                     ← _COG_* + _cog_* + rotas + hook CP (spec cognos + _ds_handle cog)
apps/templates/pages/cognos.html         ← CRIADO (widgets Call/Put/Total, larguras genéricas 37 cols)
apps/static/js/pages/cognos.js           ← CRIADO (ids cog*, /api/cognos/*)
apps/templates/partials/sidenav.html     ← link Option › Cognos → /cognos
apps/static/data/translations/{en,br,es}.json ← cog-* espelhadas de otm-* + Call/Put/import/nav
```

## 76. Sessão 2026-07-07 — Live Position NDF: widgets Vanilla/Other Publisher/T+0 (classificação do NDF Summary)

**Pedido:** aplicar na **Live Position NDF** os **mesmos widgets do NDF Summary** (Vanilla / Other
Publisher / T+0 / Total), **descartando o filtro de Data de Vencimento** e contando sobre a posição
viva. Os widgets da LP NDF eram placeholder (Metric A/B/C) desde a sessão 68.

**Como foi feito (`_lpndf_collect` em `routes.py`):** dentro do loop de linhas já existente, classifico
cada registro **só quando `Classe do Ativo Subjacente` = TAXAS DE CAMBIO** (FX), pelo mesmo critério dos
cards do NDF Summary — porém **sem** o filtro `Data de Vencimento == picker`:
- `Tipo do Contrato` = **SISBACEN** + `Código da Cotação` = 0 → **T+0**;
- **SISBACEN** + Cotação ≠ 0 → **Vanilla**;
- **FEEDER** → **Other Publisher**.
Cotação vazia/não-numérica = 0 (igual ao NDF Summary). `Total` segue **`len(data)`** = contagem de toda a
posição viva (todas as linhas, inclusive NDF não-FX) — por isso `Vanilla+Other+T+0` pode ser < Total se
houver NDF de commodity na posição. Tipo/cotação resolvidos aceitando **as duas grafias** (`do`/`de`),
como o NDF Summary, para não zerar os buckets se o header vier com "de".

**Front:** os 3 widgets placeholder viraram Vanilla/Other Publisher/T+0 (ícones `ti-exchange`/`ti-news`/
`ti-calendar-event`, cores primary/info/success, ids/`data-lang` `ln-w-vanilla|other|t0`); Total intacto.
O JS lia `w.a/w.b/w.c` (inexistentes no payload → sempre 0); passou a ler `w.vanilla/w.other_publisher/
w.t0/w.total`. Chaves i18n `ln-w-a/b/c` → `ln-w-vanilla/other/t0` (Vanilla / Other Publisher / T+0) nos 3
JSON. Bump `?v=20260707`.

**⚠️ Dev:** o mock TER local tem só 8 colunas (sem Classe/Tipo/Cotação) → na dev os 3 buckets ficam 0 e
Total = nº de linhas; no arquivo real (headers completos) popula. Verificado com teste sintético da
classificação (usando o `_fcst_norm` real): t0=3, vanilla=2, other=2, total=9 — cobre zero BR (`0,00`),
cotação vazia, classe acentuada, decimal BR, linha não-FX (fora dos buckets) e tipo desconhecido.

### Arquivos (sessão 76)
```
apps/pages/routes.py                          ← _lpndf_collect: classificação FX+Tipo+Cotação (sem filtro de vencimento)
apps/templates/pages/live-position-ndf.html   ← 3 widgets → Vanilla/Other Publisher/T+0 + bump ?v
apps/static/js/pages/live-position-ndf.js     ← mapeia w.vanilla/other_publisher/t0/total
apps/static/data/translations/{en,br,es}.json ← ln-w-a/b/c → ln-w-vanilla/other/t0
```

### 76.1 — Live Position NDF: + widget **Commodities**
5º widget na LP NDF: **Commodities** = contagem simples de `Classe do Ativo Subjacente` = Commodities
(lógica única, independente de Tipo/Cotação). Ordem: Vanilla · Other Publisher · T+0 · Commodities · Total.
Grid dos widgets `row-cols-xxl-4` → `row-cols-xxl-5`. Ícone `ti-package`, cor warning. `_lpndf_collect`:
`widgets['commodities']` no init + `elif classe_val == comm_norm`. JS mapeia `w.commodities`; i18n
`ln-w-commodities`="Commodities" (en/br/es); bump `?v=20260707b`. Teste sintético: commodities=2 ok.

### 76.2 — Centralização do conteúdo (td) das tabelas
Conteúdo das células centralizado horizontalmente (`text-align: center` na regra `tbody td` /
`#ops-page table.dataTable td`, que já existia — o `thead th` já era centralizado). Aplicado nas 8
páginas: Live Position (NDF, Option, Swap Characteristics), OTM Settlements, NDF Cockpit, Cognos,
NDF Summary e Other Products Summary. CSS inline no `<style>` de cada template → sem bump de `?v`.
Obs.: `.ops-num` (right-align p/ números) nas summaries está apenas *definida*, nunca aplicada; se um
dia for usada, as células passam a centralizar junto (coerente com o pedido).

### 76.3 — Centralização do td: + Operations B3
Mesma centralização (76.2) aplicada à `operations-b3.html` (`#opb3-table tbody td` + `text-align: center`).

### 76.4 — Varredura de branding (UBold / Coderthemes)
Varredura em todo o projeto (incl. minificados/binários e `Docs/`): **0** ocorrências de "Coderthemes"
(o rename já removera tudo) e só **2** de "UBold" em código/docs → trocadas em `README.md` (título
"UBold Flask" → "OTC Tracker Flask"; raiz da árvore `UBold/` → `OTC Tracker/`). A única outra ocorrência
é a linha 3093 deste HANDOFF ("boilerplate UBold original") — **referência histórica** ao template de
origem, mantida (descreve o estado pré-rename; §8 proíbe sobrescrever sem permissão).

## 77. Sessão 2026-07-08 — Quoted in Cents (tolerante) + Settlement Forecast (Tipo "02") + Bullet/Cashflow + LOB/prêmios

### 77.1 Quoted in Cents tolerante (New Deals Opt Comm / NDF Comm) — `284198b`, `1ac135b`
"Quoted in Cents" ⇔ `Fator Conversao == 0.01` do `Subjacente.json`. O parse estrito `=== 0.01` falhava quando
o fator vinha como string / com vírgula / float com ruído. Novo helper `isCentsFactor()` (aceita
string/vírgula/float), `parseFator()` e `_mergeSubjEntry()` (em conflito de códigos, prioriza a entrada
"cents"). Aplicado em `otc-fileupload.js` e `deals-processing-table.js`. Gotcha: o mock do `Subjacente.json`
tem fator float limpo `0.01`, então o bug só aparecia em códigos de conflito (HOH7, BOQ6).

### 77.2 Settlement Forecast: contar swaps com Tipo de Contrato "02" — `17c66e7`
A contagem de swaps liquidando (Dashboard › Settlement Forecast, por CEMHYB/EDG/CEM) não pegava swaps cujo
"Tipo de Contrato" (coluna A do deposição swap) vinha como `02`/`01` (com zero à esquerda). `_forecast_collect`
(count_where) normaliza `if cwv.isdigit(): cwv = str(int(cwv))` (`02`→`2`) nos dois consumidores.

### 77.3 Bullet/Cashflow por Tipo de Contrato — `655ca38`
Convenção confirmada pelo usuário: **`02` = Bullet, `01` = Cashflow**. Corrigido nas swap-characteristics
(`'Bullet' if rv=='2' else 'Cashflow' if rv=='1'`) e nos widgets (`if tv=='2': bullet / elif tv=='1': cashflow`).

### 77.4 Classificação de prêmios (DAGENDAPREMIOS) + LOB sem match — `cfd2b80`, `4270a1a`
Prêmios do `DAGENDAPREMIOS` classificados via join por contrato (`_swap_contract_ident_map`,
`_fcst_norm_contract`, novo modo `lob_join`). `_fcst_lob` deixa de assumir `CEMHYB` como default → retorna
`None`; linhas sem LOB reconhecido saem da contagem ("melhor ficar sem classificação do que classificar errado";
`if pmode in ('lob','lob_join') and product is None: continue`).

---

## 78. Sessão 2026-07-08 — Notificações: live toast + Intrag (notif de ação + linha extra)

### 78.1 Live toast espelhando o sino — `b7ab46b`, `6d61789`, `ee51dde`
Toda notificação do sino agora também aparece como **live toast**. Localização final: **top-right**, abaixo da
topbar (`#otc-toast-container { top: var(--ins-topbar-height,64px) }`). Mesmo texto/funcionalidade do sino
(`buildNotif`/`notifBodyHtml`/`showToast`/`toastNew` em `partials/topbar.html`). **Filtro:** não dispara para
ações do próprio usuário (`CURRENT_USER_SID`/`isOwnAction`).

### 78.2 Intrag: notificações de ação + linha extra — `5be4063`
As páginas Intrag NDF/Option não trigavam notificação nas ações → adicionado `_create_notification` em edit
('Deal Updated'), approve ('Status Updated') e send-file ('Intrag Sent'). Removida a "linha extra" inútil do
header dessas páginas. `ACTION_META`/`PAGE_URL` no topbar ganham 'Intrag Sent' e as URLs Intrag Option/NDF.

---

## 79. Sessão 2026-07-08 — Reconciliation Pay/Rec: Net Type + End Process (justificar) + e-mail

### 79.1 Batimento por Net Type da contraparte — `e13930d`
O batimento agora respeita o tipo de net da contraparte. Fonte: join `RefData.json` (COUNTERPARTY→SPN) →
`CounterpartyDetails.json` (SPN→`NET.value` ∈ Total Net / Pay/Rec / No Net). Regras: **Total Net** = 1 registro
líquido; **Pay/Rec** = 2 pernas; **No Net** = trade a trade. Sem classificação → **descarta** a linha (não vira
CEMHYB default). Helpers em `apps/pages/recon_payrec.py` (`_load_net_type_map`, `_net_type_for`, `_emit_records`;
`_jpm_settlement`/`_jpm_cashflows`/`_jpm_fxo` recebem `net_map`).

### 79.2 End Process: verificar pendências e justificar — `2fb1629`, `a235835`
Ao clicar **End Process**, se houver status `pending` nas tabelas (summary / pending receive / pending payment)
→ SweetAlert (EN + `data-lang`) oferecendo **justificar** ou **rodar de novo**. Justificar → habilita coluna de
comentário + Actions (edit/confirm) só nas linhas pendentes; justificativa preenchida → status **Justified**
(persistido, re-`justify_row`). Fechar / rodar de novo → só fecha. **A coluna Comment na TELA foi revertida em
`a235835`** ("na tela ficou feio") — fica só no modo justificar e no e-mail. Rota `/reconciliation-payrec/justify`.

### 79.3 E-mail End Process: coluna Comment + badges coloridos + fix linter — `de969b8`, `993dca3`, `723bffb`
E-mail inclui coluna **Comments** quando houver justificativas no dia (`has_comments` calculado em
`send_payrec_email`). Badges de Status/Check saem **coloridos** também no e-mail (macros Jinja `status_badge`/
`check_badge` em `email-template-recon-payrec.html`). Erros do linter CSS do VS Code (Jinja dentro de `style=""`)
eliminados movendo os `{% if %}` para **fora** dos atributos de estilo.

---

## 80. Sessão 2026-07-08/09 — Page Access (admin): controle de acesso por página

Nova página **/page-access** (só admin) para escolher quais páginas cada usuário acessa. Enforcement escolhido
pelo usuário: **esconder no menu + bloquear URL**; default = **acesso total até o admin restringir**. —
`827ab2d`, `0e0c23d`, `506994f`, `a5723de`, `7158e04`, `2cdc044`, `938f268`, `6c48fe4`

**Backend:** coluna `users.Page_Access` (JSON de URLs; vazio = não-configurado = acesso total; migração
`ALTER TABLE users ADD COLUMN Page_Access`). `_load_nav_urls()` faz parse do sidenav (fonte única das páginas
controláveis). `_ALWAYS_ALLOWED_PATHS = {/dashboard, /dashboard-2, /users-profile, /page-access}`.
`enforce_page_access` (before_request) redireciona `/dashboard` se a página configurada não está no allowlist.
`/api/me/access` (sidebar) e `/api/page-access/<sid>` (GET/POST admin; POST valida `u in _NAV_URLS`). Filtro de
notificações por página acessível (`_NOTIF_PAGE_URL`).

**Frontend:** link "Page Access" no sidenav (server-render p/ admin). Página redesenhada no padrão
**emil-design-eng** (motion, avatares reais via `<ASSETS>/images/users/<sid>.jpg`, botão Save compacto). Skill
`emil-design-eng` habilitada em `.claude/skills/` (`.gitignore`: `.claude/*` + `!.claude/skills/`). Agrupamento
das páginas na tela: **hierárquico completo** — breadcrumb `Seção › Grupo › Subgrupo` derivado do sidenav em
document-order (`compareDocumentPosition` protege contra motores que não devolvem os matches em ordem de
documento; descoberto porque o jsdom agrupa por seletor).

### Arquivos (sessão 80)
```
apps/pages/routes.py                       ← Page_Access, _load_nav_urls, enforce_page_access, /page-access, /api/me/access, /api/page-access
apps/templates/pages/page-access.html      ← NOVA página admin (buildPages hierárquico, renderSections, motion Emil)
apps/templates/partials/sidenav.html       ← link Page Access + script de hiding por acesso
.claude/skills/emil-design-eng/SKILL.md    ← skill copiada de .agents/skills/ p/ discovery do Claude Code
```

---

## 81. Sessão 2026-07-09 — Categoria Master + sidenav (remove Menu Levels/Disabled Menu)

### 81.1 Categoria Master — `c2ce1fb`
Novo perfil **Master** (apenas SID **E930179**), acima de admin. **Fixado por SID** (`_MASTER_SIDS`), não por
role no banco — não dá pra conceder a mais ninguém via gestão de usuários. `_session_is_master()` (SID);
`_session_is_admin()` = role ADMIN **ou** master. Master é sempre isento de restrições (enforce_page_access,
filtro de notificações, sidebar) e é o **único** que pode alterar o acesso de **admins** (ou de outro master):
`_target_needs_master(sid)` → POST `/api/page-access` retorna **403** e o GET marca `locked`; a tela trava os
alvos admin/master em read-only (`lockEditor`). Restrição aplicada pelo Master a um admin passa a valer de fato
(admins deixaram de ser isentos por padrão). Login fixa `session['user_role']='MASTER'` por SID; `MASTER` em
`ROLE_META` (ícone `ti-crown`); herda todos os poderes de admin (link Page Access, editar/excluir usuários) e
aparece como "Master". Conta Master protegida: só o próprio Master a edita/exclui.

### 81.2 Sidenav: remove Menu Levels + Disabled Menu — `c2ce1fb`
Removida a seção "Menu Items" (Menu Levels / Disabled Menu) — eram itens de demonstração do tema sem rota
navegável (`javascript:void(0)` / `href="#!"`), logo não controláveis por acesso.

---

## 82. Sessão 2026-07-09 — Control Panel: acesso por card + descrição do card Daily Settlement

### 82.1 Control Panel em seção própria (acesso por card) — `f6ef4cd`
Na tela de Page Access, o Control Panel saiu do grupo normal e virou **seção dedicada**, com um item por
**card/rotina**: `Save CETIP Files` (cetip), `Save Daily Settlement Files` (daily), `Settlement Forecast`
(forecast), `Update Contacts` (contacts). Tokens `/control-panel#<id>` guardados no mesmo allowlist das páginas.
**Enforcement:** a página abre se houver **≥1 card** concedido (`_cp_page_allowed`); cada endpoint de rotina
exige o seu card (`enforce_control_panel_cards` before_request + `_CP_ENDPOINT_CARD`; **403** caso contrário).
Retrocompat: grant legado da página inteira `/control-panel` libera **todos** os cards. Cliente esconde os cards
não concedidos (e a coluna inteira quando fica vazia). Registros `_CONTROL_PANEL_CARDS` / `_CP_CARD_TOKENS` /
`_cp_card_allowed`; `data-cp-card` em cada `.cp-card`; `PA_CP_CARDS` no page-access injeta a seção.

### 82.2 Descrição do card Daily Settlement — `0b9a277`
A rotina de save já está pronta → removida a nota "Saving logic in progress" do **fallback HTML** do card (as
traduções `en/br/es` já traziam a descrição final; o `data-lang` já substituía em runtime).

### Arquivos (sessões 81–82)
```
apps/pages/routes.py                       ← _MASTER_SIDS/_session_is_master, MASTER em ROLE_META, control-panel cards + enforcement, guards master
apps/templates/partials/sidenav.html       ← remove Menu Items; link Page Access p/ ADMIN|MASTER; hiding card-aware do Control Panel
apps/templates/pages/page-access.html      ← is_master (lock admin/master), seção Control Panel por card (PA_CP_CARDS)
apps/templates/pages/control-panel.html    ← data-cp-card + hiding por card; descrição do card Daily Settlement
apps/templates/pages/users-roles.html      ← edit/delete de usuários liberado p/ MASTER
```

## 83. Sessão 2026-07-15 — New Deals OPT/NDF Commodities: preview do Strike/Prêmio Unitário como #,##0.00000000 (`6d212eb`)

No **preview do duplo clique** (SweetAlert que reproduz o arquivo Conecta) das páginas **New Deals › Opt Commodities**
e **NDF Commodities**, o Strike (e o Prêmio Unitário no OPT) passou a aparecer formatado como `#,##0.00000000`
(milhar agrupado + 8 casas) — **só na visualização**, para leitura. O arquivo gerado (backend) continua no formato
original. **A conversão de "quoted in cents" (÷100) permanece 100% fiel**: a linha `if (div100) n = n / 100;` ficou
intacta; só a formatação de saída de `_num()` (usada exclusivamente por Strike/Prêmio Unitário no `buildConectaFields`)
mudou para `n.toLocaleString('en-US', { minimumFractionDigits: 8, maximumFractionDigits: 8 })`.

- OPT: `f[13]` (Strike, ÷100 se qic) e `f[26]` (Prêmio Unitário, ÷100 se qic).
- NDF: `f[17]` (Strike, ÷100 se `qic && ccy≠BRL`).
- Observação: o formato pede **exatamente 8 casas**, então um valor com mais de 8 decimais aparece arredondado no
  preview (o arquivo real mantém a precisão cheia) — é o padrão do domínio B3.

**Arquivos:** `apps/templates/pages/new_deals-opt-commodities.html`, `apps/templates/pages/new_deals-ndf-commodities.html`.

## 84. Sessão 2026-07-15 — Other Products › Swap: páginas de settlement Events / Athena / VCP / Kapital Hybrids

Quatro páginas **read-only** sob **Daily Settlements › Other Products › Swap**, todas no mesmo padrão do template
`other-products-swap-athena.html` (`id="swapchar-page"` + `data-api`, reaproveitando o JS genérico
`live-position-swap-characteristics.js`, que monta colunas/linhas dinamicamente a partir do payload
`{widgets:{total}, columns, rows, updated}`).

### 84.1 Events / Athena / VCP (`8851379`, `a9e3164`, `47148c2`, `adbeef7`, `145acc5`)
- **Events** — view do JSON `eventos-swap-jpm`; `_EVENTS_COLUMNS` fixa as **63 colunas** de reporte
  (`_ds_display_collect(ref, 'eventos-swap-jpm', _EVENTS_COLUMNS)`).
- **Athena** — view do JSON `br-onshore-settlements`; `_ATHENA_COLUMNS` (9 col.), value cols
  (`Owner curve`/`Counterparty curve`/`BRL Net Amount`) em `#,##0.00`; **ordenado por CounterParty A→Z**.
- **VCP** — cross-join Operations B3 (`AVISO DE INEXISTENCIA DE PU`) × Events; nome da contraparte resolvido por
  **conta no RefData** quando conta ≠ `73760.10-2`, com fallback por **CNPJ** só no omnibus `73760.10-2`; a coluna
  `CONTRAPARTE / Conta` vem de "CONTRAPARTE / Contraparte" no Events; **ordenado por Contraparte A→Z**.

### 84.2 NOVA página Kapital Hybrids (`ed12dc2`, `f003802`)
Rota `/other-products-swap-kapital-hybrids` + endpoint `/api/other-products-swap-kapital-hybrids/data`; item no
sidenav (chave `kapital-hybrids` em en/br/es).

- **Import** — arquivo `BANCO_UPCOMING_PAYMENTS.csv` (**delimitado por vírgula**), processado por extrator próprio
  (`_swaphyb_*`, não o caminho tab genérico) via flag `swaphyb` no `_DS_IMPORTS` + branch no `_ds_handle`. Filtra
  **Settlement Date = hoje** (o arquivo tem **duas** colunas "Settlement Date", `dd/mmm/yyyy` e `mm/dd/yyyy` — o mesmo
  dia; qualquer uma que bata com hoje mantém a linha). Grava JSON `swap-kapital-hybrids_YYYYMMDD.json`.
- **Display** (`_swaphyb_collect`) — colapsa as linhas por-perna do arquivo em **1 linha por trade** (Kapital ID =
  Trade Confirmation ID):
  - **Owner curve** = Σ Amounts positivos;
  - **Counterparty curve** = Σ Amounts negativos (mantida **negativa**);
  - **BRL Net Amount** = Owner **+** Counterparty (net de caixa, ex.: −946.428,52) — decisão do usuário
    (AskUserQuestion): net = soma dos fluxos, não `Owner − Counterparty`;
  - **Cetip ID** puxado de `mapping_swap-hyb.json` (`hybrids_id` → `b3_id`).
  - 14 colunas (a coluna **Trade** foi removida em `f003802`); ordenado por **Kapital ID A→Z**.
- **Colunas:** `Kapital ID, Cetip ID, Trade Date, Settlement Date, Stream Notional, Stream Notional Currency,
  Coupon Rate, Currency, DCF, Counterparty SPN, Counterparty Name, Owner curve, Counterparty curve, BRL Net Amount`.

**Arquivos:** `apps/pages/routes.py` (`_SWAPHYB_JSON`, spec `_DS_IMPORTS`, branch `_ds_handle`, `_swaphyb_read_rows`,
`_swaphyb_num`, `_swaphyb_parse_date`, `_swaphyb_extract`, `_swaphyb_kap_to_cetip`, `_swaphyb_collect`, rota+endpoint,
`_SWAPHYB_COLUMNS`), `apps/templates/pages/other-products-swap-kapital-hybrids.html`, `apps/templates/partials/sidenav.html`,
`apps/static/data/translations/{en,br,es}.json`. Mapping: `apps/static/data/mapping_swap-hyb.json`.

## 85. Sessão 2026-07-15 — Live Position Option/NDF: datas asiáticas em colunas fixas + Swap Flow amortização (`ed12dc2`)

### 85.1 Datas da Média Asiática por posição FIXA de coluna
Antes, `_lpopt_collect`/`_lpndf_collect` achavam as datas asiáticas por **heurística** (qualquer coluna não-mapeada
com um `yyyymmdd`), o que desalinhava. Agora é **posicional determinístico** — o JSON preserva **toda** coluna física
na ordem do arquivo (import `_b3_export_json`, header por `;`, headers repetidos/vazios ganham sufixo `_2`…), então
`keys[80]` = coluna Excel **CC** e `keys[100]` = **CW**:
- **Option (dposicao.opc):** `_LPOPT_ASIAN_START = 80` (CC), passo `_LPOPT_ASIAN_STEP = 3` → CC, CF, CI, … (pula a
  coluna em branco + a coluna "0" entre cada data).
- **NDF (dposicao.ter):** `_LPNDF_ASIAN_START = 100` (CW), passo 3 → CW, CZ, DC, …
- Em cada grade, inclui a data enquanto **algum** registro tiver `yyyymmdd` naquela posição; para no primeiro slot sem
  data (fim do bloco de fixings). Linhas vanilla (sem asiática) são ignoradas.

### 85.2 Nome das colunas asiáticas **unificado**
NDF e Option agora usam **exatamente** `Média Asiática (data) 1 … n` (o NDF vinha sem o "(data)").

### 85.3 Live Position Swap Flow — "Tipo Amortização" com a mesma nomenclatura do Swap Characteristics
`_lp_amort_label` passou a usar o **mesmo mapa** `_SWAPCHAR_AMORT_MAP` (0→Sobre Valor Base Original, 1→Sobre Valor
Base Remanescente, 3→Na Data de Vencimento, 4→Sem Troca de Amortização) + extração de "NN (texto)" e tolerância a
".0"; o mapa antigo `_SWAP_AMORT_TYPE` foi removido.

**Arquivos:** `apps/pages/recon_payrec.py` **não**; tudo em `apps/pages/routes.py`
(`_LPOPT_ASIAN_START/STEP`, `_LPNDF_ASIAN_START/STEP`, `_lpopt_collect`, `_lpndf_collect`, `_lp_amort_label`).

## 86. Sessão 2026-07-15 — Reconciliation Pay/Rec: Total Net do lado cliente (geral), COMM TER trade-level, tolerância de centavos

### 86.1 Colapso Total Net do lado cliente — geral (`28b1fea`)
Antes, só **Atacama** e **Lawton** (funções dedicadas) tinham as pernas do lado **cliente** somadas; qualquer outra
contraparte **Total Net** (ex.: **Marfrig**) ficava com várias linhas de cliente que somavam o valor único do JPM,
sem casar. Novo `_net_total_net_client(client, net_map)` colapsa as pernas do cliente de **toda** contraparte Total
Net em **1 registro por (contraparte, LE, produto)** — espelhando o lado JPM (que já emite 1 valor netado por grupo
Total Net). Canoniza variantes de nome via `_norm_cpty`. **Subsume** o antigo `_net_lawton_client` (removido); Atacama
continua tratado por `_net_atacama_client` (roda antes); contrapartes **Pay/Rec**/**No Net** e o ruído SPB
(`drop_if_unmatched`) ficam intactos. (Marfrig: 2 pernas SWAP → 1 linha netada → **Settled**.)

### 86.2 COMM TER — imposto (IR 0,005%) é **trade-level** (`c479581`, revisão de `28b1fea`)
O imposto é retido **por trade**: neta as pernas do cashflows **por Trade Id** primeiro e aplica o fator
`_COMM_TER_FEE = 1 − 0,00005` **só no net negativo (Pay) de cada trade**; depois soma. Aplicar por-perna crua
super-tributava estruturas a termo cujas pernas mensais se cancelam dentro da trade (Novelis dava 13.018.447,79 em vez
de **13.000.851,95**). Uma trade que neta **positivo** e os fundos isentos (Lawton, Atacama) **não** sofrem imposto.
Ex.: trade +100.000 (receber) e trade −20.000 (pagar) → bruto 80.000, imposto 20.000·0,005% = 1,00, **líquido
80.001,00** (o valor pago cai pelo imposto, então o recebido sobe).

### 86.3 Tolerância de "Settled" = centavos (< R$1) (`9a5a924`)
O limite por-linha de Settled era `< 0,005` (meio centavo) — estrito demais; linhas **já pareadas** com poucos
**centavos** de resíduo (imposto 0,005%; soma de pernas do cliente arredondadas em centavos) ficavam em **Pending**.
Novo `_TOL_SETTLED = 1,0` (< R$1, alinhado ao `_TOL_CHECK_VALUE` do resumo) + **fallback de pareamento** pelo valor de
cliente mais próximo dentro de R$1 (para diferenças de centavos que cruzam a fronteira `,50` da chave whole-unit e não
casavam). Quebras reais (≥ R$1) seguem em **Pending**.

### 86.4 (contexto — mesma leva) rlctahis SWAP hist codes + netting Lawton/Atacama (`f3f6e0b`, `484a19c`)
No `rlctahis` (SDConta interna) os nHistorico **4406, 9385, 4413** são **SWAP** (não NDF): `_SDCONTA_HIST_SWAP`,
`product` propagado em `_cli_finalize`. Netting do lado cliente para Atacama (`_net_atacama_client`, EQUITIES por LE)
e Lawton (agora via `_net_total_net_client`).

**Arquivos:** `apps/pages/recon_payrec.py` (`_TOL_SETTLED`, `_COMM_TER_FEE` doc, `_jpm_cashflows` COMM TER por-trade,
`_net_total_net_client` [substitui `_net_lawton_client`], call em `run_payrec`, `_reconcile` fallback+tolerância,
`_SDCONTA_HIST_SWAP`).

### Commits (sessão 2026-07-15)
```
6d212eb  new-deals preview Strike/Prêmio Unitário #,##0.00000000
ed12dc2  Kapital Hybrids page + Live Position asian dates (CC/CW) + amort labels
f003802  Kapital Hybrids: remove coluna Trade
28b1fea  recon-payrec: Total Net client collapse geral + COMM TER trade-level (1ª versão)
c479581  recon-payrec: COMM TER IR fee per-trade-net (não per-leg)
9a5a924  recon-payrec: Settled dentro de centavos (< R$1) + fallback de match
```

---

## 87. Sessão 2026-07-20 — Ambiente: pasta OFICIAL no Desktop (Python 3.12, awmpy stub, WAL, SSH)

A partir desta sessão a **pasta oficial do projeto** é `/Users/pistacchio/Desktop/OTC Tracker`
(clone limpo da branch `apple-design` do GitHub). A pasta antiga do iCloud
(`.../com~apple~CloudDocs/Desktop/OTC Tracker`) tinha arquivos **descarregados na nuvem** (só
placeholders — `routes.py` nem existia localmente) e um venv quebrado.

Setup para rodar neste Mac (não estava óbvio):
- **venv `.venv311` recriado com Python 3.12** (Homebrew). O `python@3.11` foi removido da máquina;
  o venv que veio junto apontava para caminhos de outra máquina/usuário e não abria.
- **`requirements.txt` ganhou `duckdb` + `flask-minify`** (`ad91911`) — ambos usados no código
  (duckdb em routes/recon; flask-minify em `run.py`) mas faltavam, quebrando um ambiente novo.
- **Stub de `awmpy`** criado no site-packages do venv (a lib interna do JPM não existe fora da rede).
  Consequência: o **login real por SID/phonebook não funciona** localmente — usar `/dev-login`
  (bloco DEV BYPASS). Dentro da rede JPM o login normal volta a funcionar.
- **WAL incompatível**: `Users_OTCTracker.db.wal` (gerado por outra versão do DuckDB) impedia abrir o
  banco (`INTERNAL Error … replaying WAL`). Renomeado para `Users_OTCTracker.db.wal.incompatible-bak`
  (o `.db` principal está intacto). Se reaparecer após rodar com outra versão do duckdb, repetir.
- **Porta**: no macOS a **porta 5000 é do AirPlay Receiver** (retorna 403 "AirTunes"). Rodar em **5005**:
  `flask run --port=5005`.
- **`DB_PATH` NÃO é mais caminho Windows hardcoded** — hoje é relativo
  (`static/data/db/Users_OTCTracker.db`). A nota antiga do CLAUDE.md sobre isso ficou desatualizada
  (corrigida nesta sessão).

**GitHub via SSH**: chave `ed25519` gerada (`~/.ssh/id_ed25519`), pública adicionada em
github.com/settings/ssh, remote trocado para `git@github.com:PistacchioV/OTC-Tracker.git`. O push por
HTTPS não funcionava (sem credencial). O processo do **DEV BYPASS** continua: `routes.py` é stripado
do bloco `/dev-login` antes de cada commit e restaurado depois (ver seção do commit-push).


## 88. Sessão 2026-07-20 — Recon Pay/Rec: colapsar pendente carregado com a liquidação efetiva do dia (`f7ee5cd`)

**Sintoma:** um item marcado como `Pending Payment/Receivement` em D-anterior (ex.: JPM esperava
**receber** 134.006,40 da EVONIK) que **liquidou hoje** (o recebimento efetivo entrou no lado
cliente/banco) continuava aparecendo como **duas linhas** — o pendente carregado + o atual de hoje —
mesmo com **valor e contraparte batendo**.

**Causa:** o motor (`_reconcile`) só casa **JPM × cliente do MESMO dia**. O atual de hoje não tinha
contraparte JPM no dia (a expectativa do JPM foi lançada no dia em que ficou pendente), então virou um
`Pending` solto do lado cliente; e o `_apply_carry_forward` apenas **reanexava** o item carregado como
pendente, sem casá-lo contra o atual.

**Fix** (`apps/pages/recon_payrec.py`, `_apply_carry_forward`): antes de reexibir um item carregado,
tenta casá-lo contra a atualização de hoje — **mesma LE, mesma direção, o lado OPOSTO preenchido, valor
dentro da tolerância de centavos (< R$1)** — e colapsa os dois numa única linha **Settled**, com
comentário rastreável (`… — liquidado`). Guardas: só casa contra `Pending` puro (nunca outro item
carregado); exige exatamente um lado preenchido em cada; não colapsa em mismatch de valor ou direção.
Validado com 5 cenários (Evonik, M Dias com nome diferente/valor igual, sem-atual, mismatch, direção
oposta). **Para ver o efeito: reprocessar o Pay/Rec do dia** (ele puxa o histórico finalizado do dia
anterior).


## 89. Sessão 2026-07-20 — Control Panel: card Daily Metric — Outstanding Confirmation Brazil OTC (`3303c03`, `215b263`)

Novo card na seção **Forecasts & Reports** do Control Panel, no padrão dos demais:
- Campos **TO / CC / BCC** **persistidos** em `apps/static/data/control-panel/daily_metric_recipients.json`
  (carregam ao abrir, salvam no `blur` e antes de cada Run) — não precisa redigitar.
- **Reference date fixa = hoje** (readonly, excluída do flatpickr via `.cp-datefield[data-fixed]`).
- Botão **Run** que salva os destinatários e dispara o e-mail (BCC só no envelope, nunca no cabeçalho).
- Placeholders em inglês, separador **`;`** (o backend `_parse_emails` aceita `,`/`;`/espaço).

Backend: card id **`dailymetric`** em `_CONTROL_PANEL_CARDS` + `_CP_ENDPOINT_CARD`; endpoints
`/api/control-panel/daily-metric/recipients` (GET/POST) e `/run`, ambos sob o controle de acesso por card.
⚠️ **Escopo escolhido = "só o scaffold"**: o **corpo do e-mail é placeholder** ("Métrica a ser
definida"). Toda a canalização (persistência + envio + destinatários) está pronta; falta definir a
**fonte/conteúdo da métrica**. JS no `CP_GROUP` do template (`dailymetric: 'reporting'`).


## 90. Sessão 2026-07-20 — About: reescrita refletindo TODAS as features atuais (`7b4af78`)

A seção de capabilities do `about.html` foi reescrita para espelhar a navegação real do app (7 grupos,
**30 cards**). Novidades: grupo **Live Position** (NDF/Swap/Option); Daily Settlement expandido
(NDF Summary&Cockpit, Swap Athena/VCP/Events/Kapital Hybrids, Option Cognos, Operations B3);
**Reconciliations** ganha Pay/Rec; **Apps** ganha File Interpreter, Holidays Calendar, Page Access.
Corrigido o Swap Characteristics (movido para Live Position, onde a rota vive) e o stat de contratos
(3 · NDF/Opções/Swap). **Só features reais entram** — placeholders (Unwinds, DCE, E-financeira, WHT,
CGD, Settlement Advice, Manual Confirmation, etc.) ficam de fora. Botões Live Position e Pay/Rec no hero.
23 chaves novas de tradução em **`br/en/es.json`** (idiomas são br/en/es, padrão `en`; chave ausente
mantém o texto inline). Motion mantido no padrão emil-design-eng (scroll-reveal + stagger com easing
custom, hover/press atrás de `@media (hover:hover)`, `prefers-reduced-motion`), stagger estendido p/ 8.


## 91. Sessão 2026-07-20 — Metrics: dashboard de Pending Confirmation (>30 dias) (`44bec16`)

Nova página **`/metrics-pending-confirmation`** (link "Metrics" do sidenav repontado de `/metrics`).
Modelo visual do `dashboards/index.html` (Chart.js) + emil-design-eng.

- **Card KPI**: volume de confirmações pendentes >30d (número grande + tendência + mini-stats). Seed do
  relatório externo (imagem) até acumular histórico interno.
- **Gráfico de histórico** (combo: barras de volume + linha de variação %) com **dropdown de escopo**
  (`>30` default / `All`) e **de range** (Current Year / Last 24 Months / Daily=mês corrente).
- **Top 5 Offenders** (>30d): **bankers** (por # de clientes distintos), **clients** e **economic groups**
  (por # de confirmações). Barras horizontais.

Backend (`routes.py`): rota + APIs `/api/metrics-pending-confirmation/offenders` e `/history`; helpers
`_pc_latest_snapshot_rows` (último snapshot diário; fallback DB de pending ao vivo), `_pc_metrics_offenders`,
`_pc_metrics_history`. **Gotchas de dados** (confirmados com o usuário):
- **Owner = o grupo INTEIRO de bankers tratado como UM nome** (não splitar por `;`) — o grupo é o mesmo
  time; o RefData não tem campo BANKER (0/439). Ranking de banker = # de clientes distintos por grupo.
- **Aging é numérico**; filtro **`> 30`**.
- **Fonte = snapshots diários** `static/data/cache/pending-confirmation/YYYY/MM/DD/pending-confirmation_*.json`
  (a "foto do dia", gerada pela manutenção das 11:30); fallback = DB de pending ao vivo.
- **Seed do histórico** em `apps/static/data/pending-confirmation-metrics-history.json` (volume mensal
  Jun/2023→Jun/2026 + diário jul/2026, do relatório externo). O MoM/DoD % é derivado na API.
- **Estado atual**: offenders e o escopo "All" ficam vazios até os snapshots diários acumularem dados
  internos (o DB de pending estava vazio); o histórico >30 já vem do seed.


### Commits (sessão 2026-07-20)
```
f7ee5cd  recon-payrec: casar item pendente carregado com a liquidação efetiva do dia
ad91911  deps: adicionar duckdb e flask-minify ao requirements
3303c03  control-panel: card Daily Metric — Outstanding Confirmation Brazil OTC
215b263  control-panel: placeholders do Daily Metric em inglês + separador ;
7b4af78  about: refletir todas as features atuais + Live Position, Pay/Rec, Cognos, etc.
44bec16  metrics: dashboard de Pending Confirmation (>30 dias)
```

### Arquivos (sessão 2026-07-20)
```
apps/pages/recon_payrec.py                             ← _apply_carry_forward: colapso carried × atual do dia
apps/pages/routes.py                                   ← Daily Metric card (endpoints/persistência) + Metrics PC (rota/APIs/helpers)
requirements.txt                                       ← + duckdb, flask-minify
apps/templates/pages/control-panel.html                ← card Daily Metric (UI + JS + acesso)
apps/static/data/control-panel/daily_metric_recipients.json  ← destinatários persistidos (runtime; não versionar)
apps/templates/pages/about.html                        ← reescrita das capabilities (30 cards, 7 grupos)
apps/static/data/translations/{br,en,es}.json          ← +23 chaves about-*
apps/templates/pages/metrics-pending-confirmation.html ← NOVA página (KPI + histórico + top-5)
apps/static/js/pages/metrics-pending-confirmation.js   ← NOVO (Chart.js: combo + barras horizontais)
apps/static/data/pending-confirmation-metrics-history.json  ← NOVO seed do histórico >30d
apps/templates/partials/sidenav.html                   ← link Metrics → /metrics-pending-confirmation
```

---

## 92. Sessão 2026-07-20/21 — Metrics PC: Top 5 Bankers por contratos + cor semântica do change (`7aca230`, `6277acc`)

- **Top 5 Bankers** passou a contar **nº de contratos/confirmações** por grupo Owner (cada linha = um
  contrato), não clientes distintos. Rótulo/tooltip = "Contracts".
- **Cor semântica do "change"** no gráfico de histórico (pendência é métrica que se quer reduzir):
  linha/pontos ficam **verdes ao cair (bom)**, **cinza estável**, **vermelhos ao subir (ruim)**. Segmentos
  coloridos pelo ponto de destino, legenda e seta no tooltip. Consistente com o badge do KPI.


## 93. Sessão 2026-07-20/21 — Dashboard/Forecast: manter SWAP CEMHYB (e todo produto padrão) em zero (`ec4c6ba`)

`_forecast_matrix` só incluía produtos presentes no `mapping`, então um produto sem liquidação na janela
(ex.: **SWAP CEMHYB**, sem hybrids nos próximos 30 dias úteis) **sumia** do gráfico e do e-mail. Agora
`_forecast_payload` faz **seed de `_FCST_PRODUCT_ORDER` com série zero** antes da matriz — o conjunto de
produtos fica estável e nenhum desaparece.


## 94. Sessão 2026-07-20/21 — Pending Confirmation: widgets, filtro Aging e ordenação de datas (`655b43d`, `51fd62d`)

- **Widgets (contagem):** o total de cada faixa de Aging voltou a contar **todas** as linhas pendentes (=
  tabela/Excel; ex.: >30 = 329), e cada card ganhou uma **linha "Others"** (catch-all no JS: 8 tipos
  conhecidos + `others`) — a quebra sempre soma o total. Culpado eram linhas com Pending Status fora dos 8
  tipos (ex.: **"Exception Fep Web"**). A tentativa anterior (total = soma dos 8) subcontava; revertida.
- **Filtro Aging com operadores** na linha de filtro por coluna: `>30`, `>=30`, `<15`, `<=30` (custom
  search numérico do DataTables; número puro segue substring). "Clear Filters" reseta.
- **Ordenação de datas** (Trade/Maturity/EA/Send/Return/Baixa/Pendência/Abono): `columnDef` com `render`
  ortogonal `yyyymmdd` — antes ordenavam como texto `dd/mm/yyyy` (por dia).


## 95. Sessão 2026-07-20/21 — Daily Metric: e-mail real (crescimento >30d + pivot) (`ae7d1db`, `3f0a3b0`, `31a1e90`)

O card Daily Metric passou a enviar um **e-mail real** (`email-template-daily-metric.html`), modelado no
relatório externo:
- **Métrica de crescimento >30d** visual e enxuta: número + tendência colorida MoM + **gráfico de barras**
  (valor em cima, mês/ano embaixo, email-safe via atributos `height`/`bgcolor`) + **2º gráfico diário**
  (day-over-day, mês corrente).
- **Pivot por ECONOMIC GROUP** (do **RefData.json**, por SPN→nome), **verde/FepWeb = SIGNATURE TYPE
  DIGITAL** do grupo, banker do RefData, Operations fixo = **Priscila Babilonia**, Business em linha única.
- **Gotchas:** o `RefData.json` tem `ECONOMIC GROUP`/`SIGNATURE TYPE`/`BANKER` por contraparte (helpers
  `_pc_refdata_lookup`, `_pc_metrics_pivot`, `_pc_bar_series`). Colisão de nome: existe outro `_MONTH_ABBR`
  (dict) no módulo → o do daily-metric é `_DM_MONTH_ABBR`. Jinja **nunca** dentro de `style="..."` (o
  linter CSS do VSCode reclama) — valores dinâmicos via atributos `bgcolor`/`height`/`<font color>`.


## 96. Sessão 2026-07-20/21 — Weekly Escalation CEM/EDG: card + e-mail (`6503e8f`)

Novo card no Control Panel (**TO/CC** persistidos em `weekly_escalation_recipients.json`, mesmo tamanho dos
demais), para rodar **toda sexta**. Envia `email-template-weekly-escalation.html`: pendentes **>30 dias**
divididos por **LOB (CEM e EDG)** — match exato normalizado (`cem`/`edg`, evita `CEMHYB`) —, agrupados por
**banker** (RefData, total por banker) e quebrados por **EMPRESA/cliente** (não grupo econômico). Endpoints
`/api/control-panel/weekly-escalation/{recipients,run}` sob acesso por card. Run é manual (não há scheduler
automático de sexta — a cadência é operacional).


### Commits (continuação sessão 2026-07-20/21)
```
7aca230  metrics: Top 5 Bankers por quantidade de contratos
ec4c6ba  dashboard/forecast: manter SWAP CEMHYB (produto padrão) em zero
655b43d  pending-confirmation: total conta todas as linhas + linha Others
51fd62d  pending-confirmation: filtro Aging (>, <, >=, <=) + ordenação de datas
6277acc  metrics: cor semântica do change (down=verde/flat=cinza/up=vermelho)
ae7d1db  daily-metric: template do e-mail (crescimento >30d + pivot)
3f0a3b0  daily-metric: pivot por grupo econômico (RefData) + barras + day-over-day
31a1e90  daily-metric: remover Jinja de dentro de style= (linter CSS)
6503e8f  control-panel: card + e-mail de Weekly Escalation CEM/EDG (>30 dias)
```

### Arquivos (continuação sessão 2026-07-20/21)
```
apps/pages/routes.py                                   ← forecast seed; Daily Metric e-mail (pivot/barras/RefData); Weekly Escalation (card/endpoints/dados)
apps/templates/pages/metrics-pending-confirmation.html ← (n/a)
apps/static/js/pages/metrics-pending-confirmation.js   ← Top5 Bankers=contratos; cor semântica do change
apps/templates/pages/pending-confirmation.html         ← widgets (Others/total); filtro Aging operadores; ordenação datas
apps/templates/pages/email-template-daily-metric.html  ← NOVO template (crescimento >30d + pivot grupo econômico)
apps/templates/pages/email-template-weekly-escalation.html ← NOVO template (CEM/EDG por banker/empresa)
apps/templates/pages/control-panel.html                ← card Weekly Escalation (TO/CC) + JS + acesso
apps/static/data/control-panel/weekly_escalation_recipients.json ← destinatários TO/CC (runtime; não versionar)
```


## 97. Sessão 2026-07-21 — Control Panel duas seções + Live Position ordenação + Pending filtros AND (`661d741`, `11407d4`, `f735916`)

- **Control Panel — duas seções com header** (`661d741`): todos os cards passam a viver sob um bloco
  header+cards, garantindo que cada card tenha título/agrupamento visível (antes um grupo ficava sem cabeçalho).
- **Live Position — ordenação cronológica das colunas de data** (`11407d4`): NDF/Swap/Option ordenam as
  colunas de data por data real (não string), consistente com a Média Asiática (ver §85).
- **Pending Confirmation — filtros de coluna interligados (AND)** (`f735916`): múltiplos filtros de coluna
  aplicam em conjunto (AND) + ajustes no modal.


## 98. Sessão 2026-07-21 — NOVA página Electronic Inventory (biblioteca de docs por contraparte)

Nova página **Electronic Inventory** — biblioteca de documentos (PDF) por contraparte, lendo do share `I:`.
Sequência de commits pela ordem em que os problemas apareceram no ambiente JP:

- `c9b9d3f` — página inicial (dropdown de contrapartes + lista de docs + preview).
- `5676738` — estado visível quando o fetch de contrapartes falha (sessão/rede) + bump de cache do JS.
- `7cf68db` — **dropdown com fundo opaco** (light/dark, `#ffffff`/`#1b1e24`) + z-index/sombra maiores — não
  fica mais transparente/confuso (`var(--bs-body-bg)` não era opaco sob o tema glass).
- `05cdf7e` — **varredura do share `I:` com timeout (4s)** — não trava mais quando o drive de rede está lento;
  nomes do RefData carregam na hora, status `share slow`.
- `7ae6668` — **cache + background-warm** da varredura; badge **"no folder" só quando o scan COMPLETO**
  confirma ausência (tri-state `on_disk`: `False`=ausente, `None`=ainda escaneando), com repolling a cada 4s —
  não marca mais falso "no folder" enquanto o `I:` ainda está sendo lido.
- `c611be1` — **PDF viewer em card próprio abaixo da lista**; lista **só PDFs** (`ext != '.pdf': continue`);
  viewer alto (78vh) com spinner de loading; resolve de pasta usa o **cache do scan** (sem re-`listdir` do
  share) — muito mais rápido.
- `cab0a35` — **dropdown pagina ao rolar** (paginação incremental de 60, preservando scroll) — antes limitava
  em 60 e parava na ~"AUMOVIO"; teclado também avança e faz `scrollIntoView`.

Engine (routes.py): `_ei_scan_root_worker()`/`_ei_scan_root(grace=6.0)` + `_EI_ROOT_CACHE`
(ts/exists/dirs/complete/scanning) sob `_EI_ROOT_CACHE_LOCK`; `api_ei_clients` devolve
`scan_complete`/`share_slow` e `on_disk` tri-state; `_ei_resolve_client_dir` usa `_EI_ROOT_CACHE['dirs']`;
`_ei_iter_files` filtra `.pdf`.


## 99. Sessão 2026-07-21 — Pending Confirmation: `Exception *` conta como OK (`1174a94`, `5b11529`, `074f544`)

Regra: linhas com **`Pending Status = Exception *`** passam a contar como **OK (resolvido)** — excluídas de
todas as métricas de confirmações pendentes — **tanto na base atual quanto em edições futuras**.

- `1174a94` — no upsert/manutenção, `Exception*` é roteado para o **DB `ok`** (não `pending`); widgets,
  dashboard e e-mail o excluem; filtro defensivo em snapshots antigos.
- `5b11529` — **Metrics (>30 dias)**: o histórico exclui `Exception*` ao contar dos snapshots JSON — consistente
  com widgets/dashboard/e-mail.
- `074f544` — **filtro STATUS** re-agrupa pela **categoria atual recomputada** (`_pc_target_category`) — rows
  `Exception*`/`OK` não vazam mais para o filtro **Pending** mesmo antes da migração física entre DBs.

Helper central: `_pc_is_ok_status(v)` = `_pc_norm(v).startswith('exception') or n in _PC_OK_STATUSES`.
No template `pending-confirmation.html`, `updateWidgets()` pula `^\s*exception` (`_pcStrip(d[11])`).


## 100. Sessão 2026-07-21 — Upload modal (Electronic Inventory): menos translúcido + ícone de calendário (`590ccf6`)

Modal Upload liquid-glass mais opaco (escopo local: `#eiUploadModal .modal-content.liquid-glass`
→ `rgba(255,255,255,0.92)`, dark `rgba(26,29,35,0.94)`) + ícone de calendário (SVG background) no campo `#eiUpDate`.


## 101. Sessão 2026-07-21 — E-mails: header de gradiente bulletproof (Outlook + modernos), num partial compartilhado

Longa iteração no header do e-mail **Daily Metric** até funcionar no Outlook do JP, depois **refatorado num
partial** e aplicado a **todos** os templates. Ordem dos commits (cada um resolveu um sintoma real no Outlook):

`fe3fc8c`→`4a29f82`→`fb93f59` (assinatura "Institutional Services by OTC Tracker"; badges Digitally/Manually
signed; header azul; texto "OTC Derivatives"; primeira tentativa VML) → `33d93b1` (VML quebrava: logo no canto,
faixa à direita — voltou ao sólido) → `cc9c54c` (gradiente `#6aa2ea→#4f8ae2→#3f63c9`) → `3bcc58d`/`9164280`
(gradiente no Outlook via **imagem** — `<td background=url>` e VML `type=frame`; PNG anexado por Content-ID
`otc_gradient`; helper `_get_email_asset`) → `dbf2953`/`d7aae08`/`e779bc8` (badges 120px iguais; `mso-width-percent`
= % da **página** causou full-width → revertido para 820px fixo + wrapper mso) → `dea2149` (pivot com
`table-layout:fixed`+`colgroup`+`word-break` — nomes longos estavam esticando o card >820px e empurrando o
header) → `73a9acb` (**`<center>` + tabela `align=center`/`margin:auto`** centraliza no Outlook — "bingo").

**Refatoração** (`f926866`): header extraído para **`partials/email-gradient-header.html`** (params
`header_title`, `header_subtitle|safe`, `header_logo_height`, `header_width`), com **context processor**
`_inject_email_grad_url` expondo `grad_url` app-wide (`url_for(... 'images/email-header-gradient.png',
_external=True)`, fallback `cid:otc_gradient`). VML `v:rect`+`v:fill type=frame` para Outlook, `<td background>`
+CSS `linear-gradient` para modernos, sólido `#4f8ae2` quando imagens bloqueadas, logo `display:inline-block`.
Aplicado ao daily-metric e aos 9 templates. Asset novo: **`apps/static/images/email-header-gradient.png`**
(820×220, gradiente diagonal). A antiga imagem em `static/data/image` deixou de ser usada.

**Fix largura + emenda** (`98b2302`): `header_width` parametriza VML rect + tabela central — corrige a emenda
quando o container não é 820px (settlement-forecast/recon 760, accrual/mtm/cetip 600-620, weekly 720). A barra de
data separada foi recolorida `#1a2c5e→#3f63c9`.

**Fix "divisão" do Settlement Forecast** (`5525d6a`): a barra de data separada era a origem da divisão sob o
header — **removida**; Reference Date movido para o **subtítulo do header** (`header_subtitle = 'Reference Date
&nbsp;·&nbsp; <strong>' ~ ref_date_fmt ~ '</strong>'`; recon-* usam `recon_date_fmt`). Header único e coeso nos 8.


## 102. Sessão 2026-07-21 — NOVO card "Pending Signature Confirmations — Collection" (`ac252de`, `1433dfe`)

Novo card no Control Panel (inglês + data-lang) que **segrega as confirmações pendentes de assinatura por
contraparte** e gera **1 `.eml` por contraparte** (num zip) como **rascunho** (header `X-Unsent`) para o Downloads.
Base de referência: página **Pending Confirmation**; escopo: **Pending Digital Signature + Pending Original**.

- **From**: `is.trade.doc@jpmchase.com`.
- **To**: contatos do **CounterpartyDetails** (via `otc_emails._contacts_emails`, com fallback para todos os
  contatos da contraparte).
- **CC**: **bankers da contraparte** + `brazil.otc.ops@jpmorgan.com` + `is.trade.doc@jpmchase.com` (fixos).
  Os bankers vêm de **`apps/static/data/signature_collection_bankers.json`** (58 contatos, `{name,email}`, domínios
  `xx→jpmorgan`/`xxxx→jpmchase`, deduplicado por email). **Resolução do banker**: RefData `BANKER` quando existe,
  **senão a coluna `Owner`** da linha do Pending Confirmation (`1433dfe` — muitas contrapartes, ex. ABB, têm
  `BANKER=None` no RefData mas `Owner` preenchido; o grupo é splitado por `[;,/&]| e ` e cada nome resolvido via a
  JSON de bankers).
- **Corpo/tabela/assinatura**: conforme legado (Prezados… tabela Aging/Product Type/Trade Date/Maturity
  Date/Trade Number… portal `www.jpmorganportaldigital.com`… assinatura Banco J.P. Morgan S.A. com telefone da 1ª
  linha removido e `brsp_otc`→`is.trade.doc@jpmchase.com`). Disclaimer varia: digital→"Pendente de Assinatura
  Digital", senão "Pendente de Assinatura".

Engine (routes.py): `_sigcoll_groups()` (agrupa por `(disclaimer, spn|nome)`), `_sigcoll_build_drafts()`,
`_sigcoll_cc_emails(banker_group, bankers)`, `_sigcoll_to_emails`, `_sigcoll_email_html/table_html/signature_html`,
`_sigcoll_bankers_index()`. Endpoints `/api/control-panel/signature-collection/{preview(GET),generate(POST)}` sob
acesso por card (registry `signaturecollection`, ícone `ti-writing-sign`); `generate` →
`otc_emails.build_drafts_download(drafts, _SIGCOLL_FROM)` → attachment + `_create_notification`. i18n: 8 chaves em
`translations/{en,br,es}.json`.


### Commits (sessão 2026-07-21)
```
661d741  control-panel: duas seções (header + cards) para todo card ter título
11407d4  live-position: ordenação cronológica das colunas de data (NDF/Swap/Option)
f735916  pending-confirmation: filtros de coluna interligados (AND) + modal
c9b9d3f  electronic-inventory: NOVA página (biblioteca de docs por contraparte)
5676738  electronic-inventory: estado visível quando o fetch falha + bump cache JS
7cf68db  electronic-inventory: dropdown com fundo opaco (light/dark) + z-index
05cdf7e  electronic-inventory: varredura do share I: com timeout (4s) + share slow
7ae6668  electronic-inventory: cache + warm; 'no folder' só com scan completo (tri-state)
c611be1  electronic-inventory: PDF viewer em card próprio; só PDFs; resolve via cache
590ccf6  electronic-inventory: modal Upload menos translúcido + ícone de calendário
cab0a35  electronic-inventory: dropdown pagina ao rolar (60 incremental, preserva scroll)
1174a94  pending-confirmation: 'Exception *' conta como OK (excluído das métricas)
5b11529  metrics-pending-confirmation: histórico >30d exclui Exception* (OK)
074f544  pending-confirmation: filtro STATUS re-agrupa pela categoria recomputada
fe3fc8c..73a9acb  email-daily-metric: iteração do header (badges/gradiente/VML/centralização)
9164280,3bcc58d  email-daily-metric: gradiente no Outlook via imagem (PNG cid/url_for)
f926866  emails: header de gradiente bulletproof num partial + context processor grad_url
98b2302  emails: header_width parametrizado (VML+tabela) + recolor barra de data
5525d6a  emails: remove barra de data separada → Reference Date no subtítulo do header
ac252de  control-panel: card 'Pending Signature Confirmations — Collection' (.eml/zip)
1433dfe  signature-collection: CC dos bankers via Owner quando RefData BANKER vazio
```

### Arquivos (sessão 2026-07-21)
```
apps/pages/routes.py                                   ← EI scan/cache/endpoints; _pc_is_ok_status + roteamento Exception*→ok;
                                                          _get_email_asset + context processor grad_url; feature signature-collection
apps/pages/otc_emails.py                               ← build_drafts_download/build_eml_bytes/_contacts_emails (reuso p/ signature-collection)
apps/templates/pages/electronic-inventory.html         ← NOVA página (dropdown opaco, doc-list+PDF viewer cards, upload modal)
apps/static/js/pages/electronic-inventory.js           ← loadClients (poll/share_slow), combo paginado, preview com spinner
apps/templates/pages/pending-confirmation.html         ← updateWidgets() pula Exception*
apps/templates/pages/metrics-pending-confirmation.html ← (histórico exclui Exception* — lógica em routes.py)
apps/templates/partials/email-gradient-header.html     ← NOVO partial do header (VML+CSS, params title/subtitle/logo_height/width)
apps/static/images/email-header-gradient.png           ← NOVO asset (820×220 gradiente diagonal p/ VML Outlook)
apps/templates/pages/email-template-*.html             ← 10 templates usam o partial do header (daily-metric + 9)
apps/templates/pages/control-panel.html                ← card signature-collection (icon ti-writing-sign) + JS preview/generate + CP_GROUP
apps/static/data/signature_collection_bankers.json     ← NOVO (58 bankers {name,email}, domínios substituídos, dedup)
apps/static/data/translations/{en,br,es}.json          ← 8 chaves do card signature-collection
```


## 103. Sessão 2026-07-22 — 2ª varredura de segurança + fix do gradiente no e-mail Pay/Rec (`9ca309a`, `e66437e`, `a4e5af9`)

Varredura de segurança para produção (só correções que **não mudam output nem fluxo** de
usuário legítimo), limpeza de menções a desenvolvimento fora do ambiente JPM, e um fix no
cabeçalho do e-mail de fim de dia do Pay/Rec. Detalhe do CSP no `Docs/SECURITY-PHASE2.md`
(itens 2A.1/2A.2 marcados como feitos).

### Segurança (`9ca309a`, só `routes.py`)
- **2FA anti-brute-force.** O código de 6 dígitos (espaço 10⁶) era adivinhável na janela de
  10 min porque `verify_code` não limitava tentativas. Nova coluna
  **`verification_codes.attempts`** (migração adiciona em bancos existentes, default 0): cada
  palpite errado gasta 1 tentativa e ao atingir **`MAX_2FA_ATTEMPTS=5`** o código é queimado
  (`used=TRUE`) e nunca mais valida. Um código correto dentro do limite segue funcionando.
- **Anti email-bombing / brute-force por códigos novos.** `_code_send_allowed(sid)` impõe
  **cooldown de 30s** (`CODE_RESEND_COOLDOWN_SECONDS`) e **teto de 5 códigos/15 min**
  (`MAX_CODES_PER_WINDOW`/`CODE_WINDOW_MINUTES`), aplicado em `_initiate_2fa` e `/resend-code`.
  **Fail-open** em erro de DB — o e-mail de 2FA nunca trava por causa do throttle.
- **CSPRNG no 2FA.** `generate_verification_code` passou de `random` (Mersenne Twister,
  previsível) para `secrets.choice`. Mesmo formato de 6 dígitos (`import secrets` adicionado).
- **Auth faltante em endpoints de escrita.** `/api/b3/{add,update,delete}` (gravam/apagam
  Reference Data e Index B3) e `/api/fx-holiday-schedules` eram alcançáveis **sem sessão** —
  não há portão global de auth, cada rota se verifica e estas quatro esqueciam. Adicionado o
  guard `401` (mesmo do `api_holidays_save` vizinho).
- **Autorização por page-access nos endpoints b3.** `enforce_page_access` ignora paths `/api/`,
  então quem não tinha a página concedida ainda chamava a API direto. Novo helper
  **`_user_can_access_page(url)`** replica a regra: `table=='refdata'`→`/reference-data`, senão
  `/index-b3`. Master e usuários sem allowlist (acesso total) passam — nada muda para quem usa
  a página legitimamente; só bloqueia o acesso lateral por URL (403).
- **CSP report-only.** Const `_CSP_REPORT_ONLY` + header `Content-Security-Policy-Report-Only`
  em toda resposta + coletor **`POST /csp-report`** (sem auth, loga e responde 204). **Não
  bloqueia nada** — serve para afinar a allowlist antes de virar a chave (ver SECURITY-PHASE2 2A).

**Residual (mudaria comportamento, precisa de decisão):** CSRF por token (Fase 2B), mensagens
de erro genéricas, `DEBUG` default False, infra hardcoded (SMTP/master SID). Ver SECURITY-PHASE2.

### Limpeza de menções a dev externo (`e66437e`)
Comentários que expunham desenvolvimento fora do ambiente JPM ("stub off-env", "lib interna que
não existe no PyPI", "coisas que a rede corporativa normalmente fornece", "strip before commit"
do DEV BYPASS) reescritos de forma neutra. Sem mudança funcional. Arquivos: `routes.py` (entrada
`dev_login` removida do `_LOCK_ALLOWED_ENDPOINTS`), `scripts/backfill_cetip_position_files.py`,
`scripts/pending_confirmation_daily.py`, `scripts/sop-capture/{capture_screens,devrun.example}.py`.
(Docs markdown — CLAUDE.md/HANDOFF/DESIGN — **não** foram tocados; ainda citam macOS/AirPlay/DEV BYPASS.)

### Fix do gradiente no e-mail Pay/Rec (`a4e5af9`, só `recon_payrec.py`)
O cabeçalho do e-mail de fim de dia às vezes saía **barra azul sólida** em vez do gradiente.
Causa-raiz: `send_payrec_email` anexava só o logo e **não passava `grad_url`** nem anexava a
imagem do gradiente — a variável vinha do context processor global `_inject_email_grad_url`, que
prefere `url_for(_external=True)`. Quando o envio sai **sem contexto de request** (scheduler), a
URL externa falha e cai em `cid:otc_gradient`, mas o payrec **nunca anexava** essa imagem → Outlook
pintava a cor de fallback `#4f8ae2`. Somado ao bloqueio de imagens externas do Outlook, variava dia
a dia. **Fix:** anexar `email-header-gradient.png` inline (`Content-ID: <otc_gradient>`) e passar
`grad_url='cid:otc_gradient'` explícito no `render_template` — mesmo padrão do daily-metric. Imagem
inline renderiza offline, não é bloqueada e independe da origem do envio. Confirmar no próximo envio real.

### Commits (sessão 2026-07-22)
```
9ca309a  fix(security): hardening de 2FA, autorização de API e CSP report-only
e66437e  chore(scripts): remover menções a desenvolvimento fora do ambiente JPM
a4e5af9  fix(recon-payrec): gradiente do cabeçalho sumindo no e-mail de fim de dia
```

### Arquivos (sessão 2026-07-22)
```
apps/pages/routes.py                        ← 2FA attempts/throttle/secrets, verify_code, _code_send_allowed,
                                               _user_can_access_page, guards b3/fx, CSP report-only + /csp-report
apps/pages/recon_payrec.py                  ← send_payrec_email: gradiente inline (cid:otc_gradient) + grad_url
scripts/backfill_cetip_position_files.py    ← comentário do stub awmpy neutralizado
scripts/pending_confirmation_daily.py       ← idem
scripts/sop-capture/capture_screens.py      ← docstring sem menção a stub/dev-login externo
scripts/sop-capture/devrun.example.py       ← comentários neutralizados (mantém função)
Docs/SECURITY-PHASE2.md                     ← 2A.1/2A.2 marcados feitos + linha do commit 9ca309a
```

## 104. Sessão 2026-07-23 — Metrics offenders live + polish de toasts (`4962acc`, `39aabc7`, `38230db`, `60f022c`)

- **Top 5 Offenders sempre do DuckDB pending live (`39aabc7`).** O endpoint
  `/api/metrics-pending-confirmation/offenders` usava o snapshot diário, então edições na
  base de pendentes só apareciam no dashboard no dia seguinte. Agora lê direto do DuckDB
  pending (mesmo filtro que descarta `Exception*`). Os snapshots seguem alimentando só o
  histórico, o e-mail Daily Metric e a Weekly Escalation — nada muda nesses fluxos.
- **Badge de source removido (`60f022c`).** Com a fonte fixa em live, o badge "Source: live
  pending DB" virou ruído; o endpoint continua retornando `source` no JSON, só não exibe.
- **Subtítulo do Top 5 Bankers (`38230db`).** "By contracts…" → "By confirmations pending
  > 30 days", igual aos cards vizinhos.
- **Toasts de notificação mais opacos (`4962acc`).** `--ins-toast-bg` para 95% só em
  `.otc-notif-toast` (topbar.html), sem recompilar SCSS e sem afetar os demais toasts.

## 105. Sessão 2026-07-23 — NDF Cockpit: contrato via TER/Operations B3, PUBLISHER, CCY, strike, filtro de legal entity

Cadeia de 6 commits que faz o Cockpit se completar sozinho a partir das outras fontes de
NDF. **Tudo em tempo de exibição** — nada é persistido no JSON do dia, então mudanças nas
fontes refletem no próximo load; valor importado/digitado no modal sempre tem precedência.

- **`198b785` — CD_CETIP_RETURN via Live Position NDF + coluna PUBLISHER.** Linha do
  SETTLEMENT chega sem retorno CETIP; o athena id (ID_SOURCE_DEAL) existe no DPOSICAO-TER
  como right-14 do `Codigo Identificador`, junto do contrato. Novo `_ndfc_b3_maps` lê o TER
  mais recente (D-1 ANBIMA, recua até 10 dias) e monta athena→contrato e contrato→publisher
  (`Nome do Feeder` = BACEN → "BACEN", senão `Tela funcao Consulta`). Sem match → sentinel
  `_NDFC_MISSING_B3` renderizado como badge warning "Missing B3 ID". Coluna PUBLISHER à
  direita de VL_FORWARD_RATE; add/edit/import mapeiam células por posição de `_NDFC_COLUMNS`,
  então o modal ganhou o campo sozinho.
- **`feaaa86` — resgate via Operations B3 + colunas CCY.** Segunda chance antes do Missing:
  procura no operations-b3 do dia um Resgate/TER com Valor a ≤5 BRL do SETTLEMENT, aceito só
  se o DPOSICAO-TER confirmar Taxa Forward = VL_FORWARD_RATE (6 casas) e Valor Base =
  VL_NOTIONAL_FC (±0,01), e o CNPJ resolver no RefData.json para o mesmo NM_COUNTERPARTY.
  Novas colunas CCY_NOTIONAL_LC/FC: FC do `Simbolo da Moeda`; LC do `Codigo Sisbacen da
  Moeda Cotada` via de-para interno (220→USD, 978→EUR, …) — código fora do de-para aparece
  como o próprio número, de propósito. `_ndfc_valnum` tolera formato BR e US; mapas de
  contrato em maiúsculas (pub_map era case-sensitive).
- **`a6c5887` — cross-currency inverte CCY_LC/FC.** Sem BRL nas pontas o TER carrega as
  moedas invertidas em relação ao cockpit; a inversão vale só para o par derivado do lookup.
- **`a58c2e7` — VL_STRIKE_PRICE calculado.** Porte da fórmula Excel da mesa: strike =
  VL_FORWARD_RATE ± |SETTLEMENT| / VL_NOTIONAL_FC, sinal + quando o settlement concorda com
  a `Descricao` da posição do Participante no TER (COMPRADOR com positivo / VENDEDOR com
  negativo). **Cross-currency exibe `-` por ora** (settlement em BRL ÷ notional do cross sai
  na unidade errada; conversão será definida depois — pendência declarada pelo usuário).
- **`d7a470b` + `8c4dba4` — filtro de legal entity.** Só LEGAL começando com BANCO JP /
  JPMORGAN CHASE aparece (LAWTON… fora); nada é apagado do JSON e LEGAL em branco continua
  visível. Widgets contam só as linhas visíveis. O fix `8c4dba4` normaliza pontuação antes
  de comparar ("BANCO J.P. MORGAN S.A" ≡ "BANCO JP") — o filtro literal só deixava JPMORGAN
  CHASE passar.

## 106. Sessão 2026-07-23 — Recon Pay/Rec: todos os settlement types + prioridade da perna nomeada (revertida)

- **`0b0e8a3` — todos os settlement types entram.** O lado JPM só aceitava Settlement Net ∈
  {TOTAL_NET, PAYREC_NET} (porte fiel do Alteryx), mas o netting real vem do
  CounterpartyDetails/overrides, não da coluna — o filtro derrubava em silêncio toda
  contraparte No Net (sintoma: Saint-Gobain sem pernas de nenhum lado). Agora toda linha
  não-JPM entra e a redução por net type decide (No Net mantém pernas, Total Net neta tudo,
  Pay/Rec separa direções, Canalização mantém recebimentos e soma pagamentos).
- **`0cce0d8` → revertido por `59f1409` (a pedido).** O `_mate_rank` dava prioridade à perna
  nomeada (RLDOCREC/SDConta/SPB derivativos) sobre a anônima no match por valor. Com o
  revert, os três pontos de escolha do `_reconcile` voltam a primeiro-candidato-livre /
  valor-mais-próximo. **Volta o sintoma conhecido**: como a pasta lê em ordem alfabética
  (HistoricoMensagens* antes de RLDOCREC.csv), um recebimento que bate com um interbancário
  anônimo do SPB e com o TED nomeado pode casar com o anônimo — linha liquida com Client
  vazio e o recebimento nomeado sobra como pendência. Trade-off avisado; decisão do usuário.

## 107. Sessão 2026-07-23 — NOVA página Daily Settlement › NDF › Other Publisher (send TAXA p/ Conecta)

`/ndf-other-publisher` — 7 commits (`cb6e1c3` → `fb1041f`). Página **derivada** (modelo
Swap VCP): as linhas são recalculadas a cada load e só um **overlay por dia** é persistido
(JSON ao lado do Cockpit, indexado por B3 ID).

### Derivação (`cb6e1c3`, `799afdf`)
Operations B3 do dia com Tipo Operação = `PENDENTE_CAMBIO` (filtro tolerante a
acento/caixa/separador: ≡ "Pendente Câmbio"); cada operação liga às outras páginas de NDF
pelo contrato CETIP. Colunas: **CLIENT** (NM_COUNTERPARTY do Cockpit) · **B3 ID** (Título)
· **ATHENA ID** · **CCY FC** (CCY_NOTIONAL_FC) · **TX PARIDADE** (VL_STRIKE_PRICE, 8 casas)
· **CCY LC** (fixo BRL) · **TX COTADA** (fixo 1.00000000) · **CONTA PARTE / CONTA
CONTRAPARTE** (Live Position NDF, `contr_map` do `_ndfc_b3_maps` ganhou Codigo da
Parte/Contraparte). O índice do Cockpit é montado das linhas de **exibição** dele
(`_ndfop_cockpit_index`), não do JSON cru — contratos recuperados via athena id ou resgate
Operations B3 (§105) valem aqui de graça. PENDENTE_CAMBIO sem correspondência fica listada
com campos vazios (esconder o furo seria pior).

### Overlay: edit / delete / status (`ef8a65e`)
`{B3 ID → {status, maker, checker, cells, deleted}}`. Edit grava só células alteradas em
`cells` (vencem o derivado no próximo load), linha volta a Pending, editor vira maker.
Delete é lápide `deleted: true` — nada some da fonte, desfaz-se editando o JSON.
**Gotcha resolvido em `799afdf`**: a chave do overlay é o B3 ID e o CLIENT entrou na frente
dele — a proteção da coluna-chave era por índice fixo 0 e passaria a proteger a coluna
errada; agora resolve por nome (`_NDFOP_KEY_COL = _NDFOP_COLUMNS.index('B3 ID')` no backend,
`c === 'B3 ID'` readonly no modal).

### Larguras de coluna — ida e volta (`ef8a65e`, `0e52c52`, `799afdf`)
Diagnóstico real do "width não aplica": table-layout automático (9 colunas cabendo no card →
browser redistribui a sobra), `style="width:100%"` inline vencendo o CSS, e dois pisos de
min-width escondidos (120px thead, 96px input de filtro). O fix `table-layout: fixed +
width: max-content` funcionou mas foi **revertido a pedido** em `799afdf` — larguras voltam
a ser sugestão, por escolha do usuário. Ficou: padding toolbar↔header no `.table-responsive`
(não na tabela, senão rola junto no scroll horizontal) e headers em UPPER via
`text-transform` na 1ª tr do thead (linha de filtros fora, para não subir placeholder).

### Send para o Batch Conecta (`a6e7df8`, `3fe916b`, `fb1041f`)
- **Dois níveis**: botão por linha (telegram, padrão New Deals) e `#nopSendBatch` na toolbar
  (btn-soft-primary, só "Send"), que aparece com 2+ checkboxes. Mesmo endpoint
  `/api/ndf-other-publisher/send`.
- **Arquivos** em `CONECTA_NEW_PATH` (Batch Conecta\New) via `_unique_filepath`:
  `TAXA_BANCO.txt` sempre; `TAXA_LAWTON.txt` só com linha contra a Lawton (C.Parte
  `00041007`), com Participante ↔ C.Parte invertidos.
- **Linha posicional de 86 chars** portada das fórmulas Excel da mesa
  (`_ndfop_conecta_fields`): `TER  ` + `1` + `0015` + 10 dígitos aleatórios
  (MID(RAND();3;10)) + participante `73760009` + espaço + contraparte zfill(8) + contrato
  ljust(10) + 12 espaços + TX PARIDADE e TX COTADA no posicional 4+8 sem separador
  (5.55 → `000555000000`) + `000`. TX COTADA sai do valor da linha — edição manual flui
  para o arquivo.
- **Headers (43 chars)**: banco `TER  00015` + `JPMORGANBM` + 10 espaços + aaaammdd +
  `00001`; lawton `TER  00015` + `INTRAGLAWTONFDO` + 5 espaços + aaaammdd + `00001`
  (`fb1041f` — o arquivo saía sem header; padrão copiado do TCO_LAWTON, participante fecha
  em 20 chars nos dois). **Atenção**: `INTRAGLAWTONFDO` é herdado do TCO — se o TAXA usar
  outro nome, é uma constante só a trocar.
- **Tudo-ou-nada**: TX PARIDADE ausente/inválida em qualquer linha aborta o lote apontando
  os B3 IDs — nunca sai meio arquivo no share.
- **Status Sent (`fb1041f`)**: após gerar os arquivos, as linhas ganham `status: Sent` +
  `checker` = quem enviou no overlay (semântica do New Deals; badge `badge-sent` global do
  head-css). A gravação é **best-effort de propósito** — os arquivos já estão no share,
  falha ali loga mas não reporta o envio como erro.
- **Preview no duplo clique**: popover absoluto no `#nop-page` (transform-origin top left,
  scale-in), campos do Conecta na vertical; linha Lawton mostra duas colunas — Banco ×
  Lawton e Lawton × Banco. Preview e arquivo saem da **mesma** `_ndfop_conecta_fields`,
  então o que se vê é o que sai — exceto o nº interno, que regenera a cada envio como o
  RAND() da planilha.

### Pendências desta página
- Validar os arquivos TAXA num envio real no ambiente JPM (nome do participante Lawton).
- Strike cross-currency no Cockpit adiado (§105) → TX PARIDADE dessas linhas vem vazia e o
  send delas aborta até lá.

### Commits (sessão 2026-07-23)
```
4962acc  style(topbar): toasts de notificação levemente mais opacos
39aabc7  fix(metrics): top-5 offenders lendo sempre do DuckDB pending live
38230db  style(metrics): padronizar subtítulo do card Top 5 Bankers
60f022c  style(metrics): remover badge de source do card Top 5 Offenders
198b785  feat(ndf-cockpit): preencher CD_CETIP_RETURN via Live Position NDF + coluna PUBLISHER
feaaa86  feat(ndf-cockpit): resgate via Operations B3 para Missing B3 ID + colunas CCY
a6c5887  fix(ndf-cockpit): inverter CCY_LC/CCY_FC quando o NDF é cross-currency
a58c2e7  feat(ndf-cockpit): calcular VL_STRIKE_PRICE a partir do settlement e da posição TER
d7a470b  feat(ndf-cockpit): exibir só legal entities JPM (BANCO JP / JPMORGAN CHASE)
8c4dba4  fix(ndf-cockpit): filtro de legal entity ignorando pontuação (BANCO J.P. MORGAN)
0b0e8a3  fix(recon-payrec): considerar todos os settlement types do settlement.csv
0cce0d8  fix(recon-payrec): perna nomeada tem prioridade no match, preenchendo o Client
cb6e1c3  feat(ndf-other-publisher): nova página em Daily Settlement › NDF
ef8a65e  feat(ndf-other-publisher): edit/delete nas linhas + larguras de coluna e headers UPPER
0e52c52  fix(ndf-other-publisher): larguras de coluna ignoradas pelo browser + respiro na toolbar
799afdf  feat(ndf-other-publisher): colunas CLIENT, CCY FC e CCY LC + revert do layout fixo
59f1409  revert(recon-payrec): volta a prioridade da perna nomeada no match
a6e7df8  feat(ndf-other-publisher): send para o Batch Conecta (TAXA) + preview no duplo clique
3fe916b  style(ndf-other-publisher): botão de send em lote no padrão da toolbar
fb1041f  feat(ndf-other-publisher): status Sent após o envio + header no TAXA_LAWTON
```

### Arquivos (sessão 2026-07-23)
```
apps/pages/routes.py                                ← Cockpit: _ndfc_b3_maps, resgate B3, CCY, strike, filtro legal;
                                                       Other Publisher: bloco _ndfop_* completo (collect/edit/delete/
                                                       preview/send); metrics offenders live
apps/pages/recon_payrec.py                          ← settlement types; _mate_rank (entrou e saiu)
apps/static/js/pages/ndf-cockpit.js                 ← badge Missing B3 ID / PUBLISHER
apps/static/js/pages/ndf-other-publisher.js         ← página nova (?v=20260723h): tabela, modal edit, send, preview
apps/templates/pages/ndf-other-publisher.html       ← template novo (widths, UPPER, popover CSS, batch send)
apps/templates/partials/sidenav.html                ← item Other Publisher em Daily Settlement › NDF
apps/templates/partials/topbar.html                 ← opacidade dos toasts
apps/templates/pages/metrics-pending-confirmation.html  ← subtítulo + badge de source removido
apps/static/js/pages/metrics-pending-confirmation.js    ← idem
apps/static/data/translations/{en,br,es}.json       ← chaves nop-* (inclui nop-send, nop-edit-title)
```

## 108. Sessão 2026-07-23 — NDF Summary: Trade Level, Settlement Summary, avisos de liquidação e batimento B3 × interno

Página **Daily Settlements › NDF Summary** deixou de ser placeholder e virou a consolidação
diária dos NDFs de moeda. Tudo é **derivado** (o Cockpit + Operations B3 + TER + CounterpartyDetails)
— nada persiste no disco exceto o *overlay* de status do dia. Também entraram ajustes menores em
Electronic Inventory, Reference Data e nos subjects dos avisos de prêmio.

### Trade Level (`ddecf06`, `2fb19dc`)
`_ndfsum_collect(ref)` em `routes.py` monta as linhas espelhando as linhas de DISPLAY do NDF Cockpit
e juntando com Operations B3. Ordem final das 13 células:
`[LEGAL, NM_COUNTERPARTY, ATHENA ID(ID_SOURCE_DEAL), B3 ID(CD_CETIP_RETURN), TRADE DATE, SETTLEMENT DATE,
NOTIONAL FC(VL_NOTIONAL_FC), CCY_NOTIONAL_FC, FORWARD RATE(VL_FORWARD_RATE), SETTLEMENT, SETTLEMENT B3,
FIXING RATE(VL_STRIKE_PRICE), TAX(VL_TAX_INCOME)]`.
- **TRADE/SETTLEMENT DATE** vêm do `contr_map[b3]['emissao'/'venc']` (Data de Emissão / Vencimento do
  TER), formatadas por `_ter_date`; sem match no TER → em branco.
- **SETTLEMENT B3**: pega o `Valor` cru do Operations B3 casando por B3 ID; `DIFFERENCE = SETTLEMENT − SETTLEMENT B3`
  com tolerância `_NDFSUM_TOL = 5.0` → ícone de check (ok) ou X; badge de status OK/Check.
- **Parsing de valor** (pegadinha que já mordeu antes): as células de DISPLAY do Cockpit são
  US-formatadas (`1,000.00`) → usar `_mtm_parse_num` (US). O `Valor` cru do Operations B3 usa
  `_ndfc_valnum` (BR/US-tolerante). **Não** trocar um pelo outro.

### Settlement Summary (`ddecf06`, `2fb19dc`, `bf30c7e`)
Net por contraparte, guiado pelo *net type* do CounterpartyDetails (`_ndfsum_net_type`):
Total Net (1 linha netada) · Pay/Rec (1 por direção) · No Net (1 por trade); default Total Net.
- **Direction** pelo sinal do net; **ACCOUNT** vem do modelo BANKING (`DEFAULT_PAY`/`DEFAULT_RECEIVE` →
  ACCOUNTS[]), formatado por `_ndfsum_account_fmt` como `BCO: 341 | AG: 0910 | CC: 967` (banco em 3 dígitos
  zfill; no template BCO:/AG:/CC: ficam em negrito).
- Coluna **Observação** removida; card centralizado (`col-xxl-8`, `justify-content-center`);
  placeholders dos filtros centralizados.

### Avisos de liquidação — Generate (`2fb19dc`, `bf30c7e`)
Botão **Generate** no toolbar do card Settlement Summary. `POST /api/ndf-summary/settlement-emails`
→ `build_ndf_settlement_emails(trades, ref_date)` em `otc_emails.py` gera drafts `.eml` (X-Unsent →
rascunho editável no Outlook) num zip `Avisos_Liquidacao_ddmmyy_NDF.zip`.
- Agrupamento por (contraparte, classe legal via `_ndf_legal_class` = MGT se JPMORGANCHASE senão JPM)
  × net type. Tabela de dados: `Nº da Confirmação(Athena ID) · Data de Início · Notional Original(com CCY,
  ex. USD 5.100.000,00) · Resultado Apurado · IR(0,005%) · Resultado Líquido(=Settlement−IR)`.
- Valores por linha com `R$` e negativos entre parênteses `(R$ 2.500,00)` via `_brl`.
- **Banco**: MGT positivo → JPMORGAN CHASE BANK (BRASIL) 488/0001/985181643, CNPJ 46.518.205/0001-64;
  senão BANCO JP MORGAN S/A 376/0011/5116003, CNPJ 33.172.537/0001-98 (`_JPM_BANK_KV`).
- **Subject**: `Liquidação de Operação de Derivativo (Termo de Moeda) - dd/mm/yyyy - CONTRAPARTE`,
  com ` x JPMORGAN CHASE` no fim quando MGT.
- **Status Generated persiste**: overlay `ndf-summary_YYYYMMDD.json` (`_ndfsum_meta_path/load/save`)
  keyed por contraparte {status, maker, at}; gravado best-effort após a geração, relido no próximo `/data`.
- SweetAlert em inglês (com `data-lang`) ao final informando nº de avisos × nº de contrapartes
  (headers `X-Draft-Count` / `X-Counterparty-Count`). **Correção**: o `ndf-summary.html` só incluía o JS
  do sweetalert2, faltava o CSS → dialog sem estilo; incluído `sweetalert2.min.css` no extra_css.

### Batimento B3 × interno nos cards (`203dfe5`, `a07f971`)
Os 3 cards do topo (Vanilla / Other Publisher / Total) viraram um **batimento de quantidade e valor**
entre B3 e interno, por categoria. Decisão de fonte de dados (confirmada com o usuário):
- **Interno** = `[PROD] Cockpit.SETTLEMENT` cru; **B3** = `Valor` cru do Operations B3 (resgates).
  É **bruto × bruto** — o IR (`VL_TAX_INCOME`) só entra no Settlement Summary, **nunca** no batimento.
- O Operations B3 mistura NDF de moeda, de commodity, etc.; então **os dois lados são filtrados** por um
  whitelist de FX vindo do Live Position NDF (`_ndfsum_fx_map`): contratos com Classe do Ativo Subjacente
  == TAXAS DE CAMBIO e Vencimento == data de referência; SISBACEN (inclui T+0) → `vanilla`, FEEDER → `other`.
  Contrato fora do whitelist é ignorado nos dois lados.
- `recon[cat]` = {b3_count, b3_value, int_count, int_value, diff_value, matched}; `matched` = contagem igual
  **e** `abs(b3_value − int_value) ≤ _NDFSUM_TOL`. Card sem match ganha anel âmbar (`.ops-recon.is-unmatched`).
- **Alinhamento OPS/VALUE** (`a07f971`): header e linhas eram grids `auto` independentes → desalinhavam.
  Fixado para `grid-template-columns: 1fr 2.75rem 7rem` (mesma geometria) + títulos OPS/VALUE à direita.
- Design conforme `/emil-design-eng`: sem animação por-update (os cards renderizam a cada load),
  cores semânticas OK/Verificar, `tabular-nums` alinhados à direita.

### Outros (`b0e5fee`, `0d2e6eb`, `4978a71`, `9ab7ab3`)
- **Electronic Inventory**: select-all ao focar os campos (busca de contraparte + datas de upload);
  blocos extras de upload no mesmo tamanho/layout do primeiro; X em cada dropzone para remover arquivo
  anexado por engano. JS bump `?v=20260723a`.
- **Reference Data**: opção `INTERNAL` no Signature Type (Digital/Manual/Internal).
- **New Deals (avisos de prêmio)**: `build_premium_emails(deals, asset_label=…)` — FXO usa
  `Opção de Moeda`, Opt Comm usa `Opção de Commodities`. Subject:
  `(Pagamento de Prêmio) Liquidação de Operação de Derivativo (<asset_label>) - dd/mm/yyyy - CONTRAPARTE`.
- **Script** `scripts/export_electronic_inventory_excel.py`: varre `ELECTRONIC_INVENTORY_ROOT`, monta
  workbook openpyxl com abas Transacionais/SSI/Confirmações (nome do arquivo + contraparte), salva em
  `~/Downloads`; suporta long_path (MAX_PATH Windows), `--root`/`--out`.

### Faixa branca no e-mail (sem mudança de código)
O template ganhou fundo full-canvas (body bgcolor + table bgcolor + VML `<v:background>` MSO) — é o único
mecanismo que o Word pinta de ponta a ponta. A faixa branca que o usuário ainda via é **chrome do cliente**
(canvas de composição do Word / container do OWA), fora do controle do e-mail; o enviado renderiza correto.
Perguntado via AskUserQuestion → usuário optou por **manter o cinza como está** (sem alteração).

### Pendências / pontos em aberto (não bloqueantes, sinalizados ao usuário)
- **T+0** hoje entra dobrado em Vanilla no batimento — fácil de separar em categoria própria se o desk quiser.
- O whitelist de FX filtra por **Vencimento == data de referência**; se o desk considerar "liquidando" por
  outra data (ex. data de liquidação financeira ≠ vencimento), trocar o campo em `_ndfsum_fx_map`.
- As tabelas dos avisos usam os cabeçalhos **sem os dois-pontos** do spec original, para casar com o template
  do aviso de prêmio; dá pra restaurar se pedirem.

### Commits (sessão 2026-07-23, continuação — NDF Summary)
```
ddecf06  feat(ndf-summary): Trade Level do Cockpit + Settlement Summary netado por contraparte
9ab7ab3  feat(scripts): export do Electronic Inventory para Excel (Downloads)
b0e5fee  feat(electronic-inventory): select-all nos campos, blocos do upload no padrão do inicial e X nos dropzones
2fb19dc  feat(ndf-summary): datas do TER, avisos de liquidação (Generate) e ajustes do Settlement Summary
0d2e6eb  feat(reference-data): opção INTERNAL no Signature Type
bf30c7e  feat(ndf-summary): refinamentos dos avisos (banco MGT, CCY, R$), status Generated persistido e fundo VML no e-mail
a0752bc  fix(ndf-summary): botão Generate no card certo + CSS do SweetAlert faltando
4978a71  feat(new-deals): rótulo do ativo no subject do aviso de prêmio (Opção de Commodities / Opção de Moeda)
203dfe5  feat(ndf-summary): cards viram batimento B3 × interno por categoria
a07f971  fix(ndf-summary): alinhar os cabeçalhos OPS/VALUE do batimento com os números
```

### Arquivos (sessão 2026-07-23, continuação — NDF Summary)
```
apps/pages/routes.py                    ← _ndfsum_collect (Trade Level, Settlement Summary, recon), _ndfsum_net_type,
                                           _ndfsum_refdata_spn, _ndfsum_account_fmt, _ndfsum_meta_*, _ndfsum_fx_map,
                                           _ndfsum_money, endpoints /api/ndf-summary/{data,settlement-emails};
                                           build_premium_emails asset_label (FXO/Opt Comm)
apps/pages/otc_emails.py                ← build_ndf_settlement_emails, _ndf_settlement_email, _ndf_legal_class,
                                           _JPM_BANK_KV, _brl (R$ + negativos entre parênteses), _email_shell VML
apps/templates/pages/ndf-summary.html   ← 3 cards de batimento (.ops-recon), Trade Level, Settlement Summary centralizado,
                                           botão Generate, SweetAlert, sweetalert2 CSS/JS, setRecon(), fillTables()
apps/templates/pages/reference-data.html ← option INTERNAL no Signature Type
apps/static/js/pages/electronic-inventory.js ← select-all, blocos extras no padrão, X nos dropzones (?v=20260723a)
apps/static/data/translations/{en,br,es}.json ← ops-generate, ops-gen-*, ndf-r-ops/value/internal/ok/check
scripts/export_electronic_inventory_excel.py  ← NOVO: varredura do Electronic Inventory → Excel no Downloads
```

---

## 109. Branch `visual-refresh` — Redesign visual (Nova / Linear / Raycast / Vercel)

> **Escopo/branch:** todo o redesign visual vive na branch **`visual-refresh`** (NÃO na `main`). É uma
> **camada aditiva de override** que NÃO altera markup nem lógica das páginas — refina fundo, tipografia,
> gradientes, cards, navegação e adiciona animações. Para reverter por completo basta remover os dois
> `<link>`/`<script>` em `partials/head-css.html` / `partials/footer-scripts.html`.

### 109.1 A camada de override — arquivos
```
apps/static/css/visual-refresh.css   ← override de estilo, carregado DEPOIS de app.css
apps/static/js/visual-refresh.js     ← IIFE que constrói o drawer, o nav de topo customizável,
                                        o pin da sidebar e o editor "Personalizar menu"
```
- Ambos são **aditivos**: compatíveis com o tema nativo (`data-bs-theme` light/dark) e com os
  `--ins-*` do tema OTC Tracker. **NÃO usar `--bs-*`** (a maioria é indefinida no tema → cai no fallback
  `#fff` e gera bug no dark). Use sempre os tokens `--ins-*` (nativos) ou `--vr-*` (desta camada).

### 109.2 Tokens de design (`:root` em `visual-refresh.css`)
```
--vr-accent-1: #0066cc   (azul)     --vr-accent-3: #8b5cf6   (roxo)
--vr-accent-2: #5e5ce6   (índigo)   --vr-accent-4: #d946ef   (magenta)
--vr-grad:  linear-gradient(100deg, #0066cc, #5e5ce6 50%, #8b5cf6 80%, #d946ef)   ← GRADIENTE DE MARCA
--vr-card-radius: 18px
--vr-ease:  cubic-bezier(0.22, 1, 0.36, 1)
--vr-card-bg / --vr-card-border / --vr-card-shadow[-hover]  ← superfícies (mudam por tema)
--vr-page-bg / --vr-glow-a/b/c / --vr-grid-line            ← fundo + glow radial (mudam por tema)
```
- O gradiente de marca `--vr-grad` é o **mesmo** do `--ab-grad` do about.html
  (azul → índigo → roxo → magenta). Use-o para qualquer superfície de destaque (logo, tiles de ícone,
  barras de item ativo, hero panels).
- Dark = preto profundo estilo Nova (`--ins-body-bg: #08080d`). Light = `#f4f5f9` com glow visível.

### 109.3 Navegação — drawer + pin + nav de topo customizável (`visual-refresh.js`)
- **Sidebar vira DRAWER deslizante:** `.sidenav-menu { transform: translateX(-100%) }`; abre com
  `body.vr-nav-open` (botão de menu `.vr-menu-btn` no topbar) sobre um backdrop. Navegação COMPLETA
  preservada (nada foi removido do sidenav.html).
- **Pin/dock (fixar a sidebar):** botão `.vr-pin-btn` dentro do menu → `body.vr-nav-pinned`. Em
  `≥992px` a sidebar **docka** (largura fixa `--ins-sidenav-width`, 240px) e o `.content-page` /
  `.app-topbar` recuam com `margin-left`. **Bug corrigido (`b2dd137`):** ao pinnar, forçar
  `data-sidenav-size="default"` (salvando o valor anterior em `localStorage["otc_nav_prevsize"]` e
  restaurando ao despinnar) — senão um resíduo do modo nativo `on-hover` fazia a sidebar dockada
  colapsar/expandir no hover. Há também um lock de largura CSS em `body.vr-nav-pinned .sidenav-menu`.
- **Nav de topo customizável (`#vr-topnav`):** links centrais no navbar, escolhidos pelo usuário
  (máx. 7, default = Dashboard/Live Position NDF/Pending/Pay-Rec/Reference Data). Persistidos em
  `localStorage["otc_topnav_<SID>"]`. A árvore de opções é construída **a partir da própria sidebar**
  (`buildSections()` → grupos/subgrupos/folhas), com desambiguação de rótulos genéricos
  (set `GENERIC` + contagem de duplicados → mostra o contexto do grupo pai).
- **Editor "Personalizar menu" (`openEditor`)**: painel com TODAS as páginas agrupadas por seção/subgrupo
  destacados (`.vr-navcfg__group` / `.vr-navcfg__grouphead` / `.vr-navcfg__sub`), checkboxes recursivos.
- **⚠️ SEGREGAÇÃO DE ACESSO (obrigatória):** tanto a sidebar (`sidenav.html`, pruning client-side) quanto
  o nav de topo e o editor filtram por `/api/me/access` (`{is_admin, configured, pages:[]}`). O gate
  `isAllowed(href)` do customizer é ao menos tão restritivo quanto o da sidebar — só pode aparecer no
  top menu / menu / personalização o que o usuário tem permissão. Ao mexer em navegação, manter esse gate.

### 109.4 Animação de ícone padrão "card" (about → index → metrics → sidenav)
Padrão de motion nascido no **about.html** (`.ab-feat__icon`) e propagado:
- **Ícone:** `transition: transform 260ms var(--vr-ease)`; no hover do card/link →
  `transform: scale(1.1) rotate(-4deg)` (no sidenav/top usei `scale(1.16) rotate(-6deg)`), o card levanta
  `translateY(-6px)`.
- **Sempre** atrás de `@media (hover:hover) and (pointer:fine)` + reset em `@media (prefers-reduced-motion: reduce)`.
- Aplicado nos ícones dos cards iniciais do **index.html** (`.dash-stat__icon`) e das mini-chips do
  **metrics-pending-confirmation.html** (`.pcm-mini__icon`).

### 109.5 Ícone do sidenav = tile de gradiente com glifo branco (igual about) — `1c475a1`
- `.side-nav … .menu-icon` virou um **tile 30×30, `border-radius:9px`, `background: var(--vr-grad)`,
  glifo `#fff`**, com brilho índigo (`box-shadow: 0 4px 12px rgba(94,92,230,.28)`). Mesma paleta dos
  ícones do about (glifo branco + tile de gradiente de marca).
- SVG interno forçado a `17×17` e `color:#fff`; item ativo mantém glifo branco com sombra mais forte
  (o `color: var(--vr-accent-2)` antigo do ativo foi trocado por `#fff`, senão o glifo sumia no gradiente).
- Hover usa a animação-card (`scale(1.1) rotate(-4deg)`), com guarda de reduced-motion.

### 109.6 Paleta harmônica dos cards do Dashboard (index.html) — `dd94c05`
Alinhada ao gradiente de marca (removido o amarelo/laranja que quebrava a harmonia):
```
.dash-stat--ndf   { --c1:#1866dc; --c2:#3d8bfd }   (azul)
.dash-stat--opt   { --c1:#4f46e5; --c2:#7c73ff }   (índigo)
.dash-stat--swap  { --c1:#8b3ff0; --c2:#a855f7 }   (roxo)
.dash-stat--total { --c1:#c026d3; --c2:#e455f5 }   (magenta)
```

### 109.7 i18n — REGRA (vale para toda UI adicionada nesta camada)
Texto **default sempre em inglês** no HTML **com `data-lang="<chave>"`**; adicionar/atualizar a chave nos
três JSONs `apps/static/data/translations/{en,br,es}.json`. `applyTranslations()` só sobrescreve se a
chave existir e for truthy (chave ausente → mantém o default inglês). Chaves adicionadas nesta leva:
nav customizer (`vr-cfg-*`), hero (`dash-hero-*`).

### Commits (branch `visual-refresh` — redesign; mais recentes → base)
```
1c475a1  Give sidenav icons the about-style gradient tile
d1ff8e5  Move the card-style icon animation to the sidenav; revert the top menu
9193bd5  Add icons and hover animation to the top menu bar items   (revertido por d1ff8e5)
6405dfd  Drop "at a glance" from the Dashboard hero subtitle
dd94c05  Harmonize dashboard card palette and animate initial card icons
b2dd137  Fix pinned sidebar on-hover glitch, expand nav customizer, polish Control Panel
cd57e56  Restyle notification toasts + fix dashboard dropdown stacking
b702c34  i18n: English defaults + data-lang for the added UI (nav customizer, hero)
3f4c29f  Apply gradient bento to summary widgets + fix all date fields globally
e410feb  Add pin/dock option for the sidebar (content resizes to fit)
15bff4f  Make the center navbar links user-customizable
2abf0a1  Global page header: gradient-glow hero panel (applies to all pages)
7ca11e4  Restructure Dashboard + Metrics headers (Nova hero + bento stats)
9d08cc1  Redesign Dashboard + Pending-Confirmation Metrics (Nova style)
129e263  Design: segmented theme toggle, borderless menu icon, black favicon, About redesign
502576c  Restore full navigation via slide-in drawer
9485630  Restructure navigation into floating horizontal navbar (Nova style)
d1d2cdb  Add modern visual-refresh layer (Linear/Vercel/Raycast style)   ← base da camada
```

### Arquivos (branch `visual-refresh`)
```
apps/static/css/visual-refresh.css   ← camada de override (tokens --vr-*, sidenav drawer+pin+tiles,
                                        cards, hero, nav customizer, animações)
apps/static/js/visual-refresh.js      ← drawer, pin (forceFixedSidenav/restoreSidenavSize),
                                        nav de topo customizável, editor "Personalizar menu"
apps/templates/partials/head-css.html / footer-scripts.html ← <link>/<script> da camada
apps/templates/pages/index.html       ← paleta harmônica dos cards + animação dos ícones + hero sem "at a glance"
apps/templates/pages/metrics-pending-confirmation.html ← ícones nas mini-chips + animação
apps/templates/pages/about.html        ← origem do padrão de ícone (tile de gradiente + motion)
apps/static/data/translations/{en,br,es}.json ← chaves vr-cfg-*, dash-hero-*
```

## 110. Sessão 2026-07-24 — Control Panel: TO/CC editáveis nos cards de e-mail (`658b7e1`, `7826b49`)

- **Settlement Forecast** (`658b7e1`) e **Save CETIP Files** (`7826b49`) ganharam campos TO/CC editáveis
  no próprio card do Control Panel, persistidos em JSON de runtime dentro de
  `apps/static/data/control-panel/` (pasta **untracked, nunca commitar** — destinatários de produção).
- No Save CETIP Files o TO é **por e-mail de área** (cada área tem seu destinatário).
- E-mails desses fluxos passaram a usar o header no padrão daily-metric (ver §111).

## 111. Sessão 2026-07-24 — Header de gradiente vira PADRÃO de todos os e-mails (`89b9e37`, `97036bb`)

- `89b9e37`: o header do daily-metric (ghost-table MSO + faixa de gradiente via `cid:` embutido)
  virou o padrão e foi aplicado a **todos** os templates de e-mail (accrual, MTM, cetip-saved,
  recon comitente/payrec, settlement forecast, …). Helper central: `_attach_email_gradient(msg_related)`
  em `routes.py` anexa o PNG do gradiente como related part.
- `588b213` tentou fazer o rect VML acompanhar a largura real do `td`; **revertido** em `4b8f0ad`
  (largura fixa é o que renderiza certo no Outlook clássico). Não reintroduzir.
- `97036bb`: os dois últimos templates fora do padrão — **Verification Code** (`email-verification.html`)
  e **Account Activated** — entraram no padrão; `send_verification_email` / `send_account_activated_email`
  agora chamam `_attach_email_gradient`.

## 112. Sessão 2026-07-24 — NDF Summary: refinamentos, TEDs e T+0 de volta

- `3acf3bb` Print Advice gera avisos **só das contrapartes selecionadas** (checkbox da tabela).
- `353a93a` resultado líquido do aviso encolhe com o IR também quando negativo.
- `dc6a48a` ação **Confirm** no Settlement Summary (status Generated → Sent).
- `07d0aa8` ≤2 avisos = download direto dos `.eml` (sem zip); botões de ação padronizados.
- `7410c72` todos os botões de ação no formato do Delete (quadrado com cantos arredondados —
  **padrão do app: nunca botão-bola**).
- `99831cb` **botão TEDs**: e-mail de liberação de TED com as SSIs anexas
  (template `email-template-ted-release.html`).
- `21a9eb9` **card T+0 restaurado** como batimento próprio: `_ndfsum_fx_map` lê o Código da Cotação
  (SISBACEN + cotação 0 → `t0`; ≠0 → `vanilla`; FEEDER → `other`); o recon acumula por chave
  `('vanilla','t0','other','total')` — T+0 tinha sumido quando os cards viraram batimento B3×interno.

## 113. Sessão 2026-07-26/27 — Electronic Inventory: causa-raiz do upload no Win11 (`fe8d7f2`, `a651e08`)

- Sintoma (usuários Win11): clicar em Upload Documents não abria o modal (ou abria o file picker direto).
  Duas tentativas anteriores (`4f1bfee`, `f4457cc` — remover backdrop-filter) NÃO eram a causa.
- **Causa-raiz (`fe8d7f2`)**: `.modal-dialog` ficava parqueado em `opacity:0` e dependia da animação
  (`forwards`) para aparecer. Windows 11 com "Animation Effects" desligado ⇒
  `prefers-reduced-motion: reduce` ⇒ animação não roda ⇒ **modal invisível** (o clique caía no
  dropzone invisível, por isso o file picker "direto"). Fix app-wide em
  `scss/components/_modal.scss` + patch manual em `app.css`/`app.min.css` (sem node/gulp neste Mac):
  estado de repouso visível, animação `zoomInModal .1s ease-out` **sem `forwards`**, `transition: none`.
- `a651e08`: com a causa-raiz resolvida, o kill-switch de backdrop-filter foi removido e o **blur do
  fundo voltou** ao modal de upload (opacidades de painel 92%/94% mantidas).

## 114. Branch principal agora é `visual-refresh` (merge `35954f0`)

- Desde 26/07/2026 **todo o trabalho vai para `visual-refresh`** (antes `apple-design`).
  `apple-design` foi mergeada (`35954f0`) e não recebe mais commits.
- Skill `/commit` e a memória do Claude já apontam para a branch nova.
- O bloco DEV BYPASS local em `routes.py` hoje tem **23 linhas** (inclui
  `_LOCK_ALLOWED_ENDPOINTS.add('pages_blueprint.dev_login')` — sem isso o auto-lock intercepta o
  `/dev-login`). Continua NUNCA indo para o repo (ver skill `/commit`).

## 115. Sessão 2026-07-27 — Ajustes da camada visual-refresh

- `090d190` **Pay/Rec recon**: dropzone branco no dark — tokens `--bs-*` indefinidos trocados por
  `--ins-*` (reforça a regra da §109.1).
- `4f51650` ícones **Index B3/Intrag** centralizados no tile de gradiente
  (`.menu-icon .icon-b3/.icon-intrag` 17×17 inline-flex) + animação-card nos ícones dos cards do
  **Control Panel** (`.cp-card__icon`).
- `0278367` **sidebar pinada perdia os textos**: o config.js do tema re-aplica
  `data-sidenav-size="condensed"` ≤1140px por cima do pin. Fix em `visual-refresh.js`:
  `enforcePinnedSize()` + MutationObserver no atributo + listener de resize forçam `"default"`
  enquanto `body.vr-nav-pinned` e ≥992px (seta o atributo direto, de propósito NÃO via
  `forceFixedSidenav` para não salvar "condensed" como tamanho anterior do usuário).
- `c6bc42c` **Dashboard**: contagens dos cards em `#,##0` e valores **visíveis** nos gráficos —
  plugin custom Chart.js `valueLabelPlugin` (id `vrValueLabels`, `afterDatasetsDraw`), modo
  `bar-end` (total na ponta da barra, branco por dentro se cortar) e `arc` (rótulo branco com
  sombra, pula fatias <5%); ligado em liveChart, clientsChart, productsChart, commoditiesChart e
  pieChart via `plugins:[valueLabelPlugin]` + `options.plugins.vrValueLabels={mode}`.
- `72d249b` assinatura do **Weekly Escalation** = "Institutional Services by OTC Tracker"
  (igual daily metric).
- `f6b779c`/`83c3abf` **Reference Data**: BANCO JOHN DEERE S/A - 217 nas opções de banco
  (editor de duplo clique E dropdown de conta nova — lista única `CP_BANKS`, ordem numérica);
  botões check/confirm no padrão quadrado arredondado (`border-radius:7px !important` em
  `.btn-act` e `.cp-glass .btn-xs`).
- **Verificação de sintaxe JS neste Mac**: usar o JavaScriptCore
  (`/System/Library/Frameworks/JavaScriptCore.framework/Versions/Current/Helpers/jsc -e "new Function(readFile('arquivo.js'))"`)
  — checagem de chaves via python dá falso positivo com regex literals.

## 116. Sessão 2026-07-27 — New Deals: filtro Status ≠ Success + NOVA página Products › Monitor (`b02b910`)

- **Filtro padrão novo** em todas as páginas New Deals: além de Trade Date = today, `Status <> Success`
  (modo de texto `'not'` em `_deal_matches`).
- **NOVA página `/new-deals-monitor`** — primeiro item da seção **Products** no sidenav (controla os
  sub-itens: new deals, unwinds, intrag…): um card por produto (catálogo `_NDM_CARDS`; NDF Commodities,
  FWD Start, Other Publisher, Option Commodities, FXO, Intrag NDF/Option, e placeholders
  "In development" para Equity Options/Swap Equities/Swap CEM), reference date = today com histórico
  dia-a-dia (daterangepicker). API `/api/new-deals/monitor` varre `NEW_DEALS_CACHE_ROOT` por arquivos
  `YYYYMMDD*`, agrupa por caminho de produto e conta por Status; produtos fora do catálogo aparecem
  como extras. Visual segue as regras da §109 (bento cards, chips de status, barra proporcional,
  stagger de entrada, i18n `ndm-*`).
- **Seção Components REMOVIDA do sidenav** (era só suporte de desenvolvimento; 678 linhas fora) —
  some automaticamente do Page Access também, porque o checklist é construído do DOM vivo da sidebar.

## 117. Sessão 2026-07-27 — Operations B3: coluna Type + Mensageria (`58cf073`, `d78ad52`, `2470497`)

### Coluna Type (derivada, sempre a última)
- `_opb3_collect` appenda um **Type** derivado por registro (`_opb3_tipo_for`): match do Título contra a
  live position da categoria via `_opb3_tipo_maps(ref)` (walk-back ≤10 dias úteis ANBIMA por categoria
  sob `B3_JSON_ROOT`). Regra: **OPC** → CLASSE DO ATIVO SUBJACENTE = TAXAS DE CAMBIO → `TAXAS DE CAMBIO`,
  COMMODITIES → `COMMODITIES`, resto → `EQUITIES`; **TER** → valor de CLASSE DO ATIVO SUBJACENTE;
  **SWAP** → código identificador (CEM-/EDG-…). No front, header `Type` com `data-lang="ob-col-type"`;
  `dataCols()` exclui a coluna dos modais Add/Edit (ela não é editável).

### Mensageria (drafts .eml para o time do piloto)
- Botão **Mensageria** ao lado do Import + dois cards **CEM** e **Equities** com TO/CC
  (blur-save em `_OPB3_MSG_RECIPIENTS_FILE`, dentro de `control-panel/` — untracked).
  Roteamento: `_opb3_msg_route_key(tipo)` → `'equities'` se o tipo normalizado contém
  equit/edg/acao, senão `'cem'` (**premissa ajustável** se o split do piloto for outro).
- Elegíveis: só linhas com Modalidade de Liquidação `Bilateral*`/`Bruta*`. Segregação: um draft por
  `(tipo título, Conta Contraparte, tipo operação)`. Nome da contraparte: `RefData.json`
  (`B3 ACCOUNT` → `COUNTERPARTY`), fallback Nome Simplificado.
- **Subject**: PAGAMENTO DE PREMIO → `Prêmio {Swap|NDF|Opção} - Liquidação Banco x {cpty} - dd/mm/yyyy`;
  demais → `{Tipo Op} {label} - Liquidação Banco x {cpty} - dd/mm/yyyy`.
- **Frase do fluxo** (`_msg_flow_phrase`, destaque amarelo): soma ≥0 →
  `Banco recebe do(a) {cpty} R$ #.##0,00`; negativa → `Banco paga {cpty} R$ #.##0,00`
  (**sem** "ao(à)" — pedido explícito).
- **Batimento interno**: TER → Cockpit (`_opb3_internal_ter_map`), prêmio de Swap → DAGENDAPREMIOS
  (`_opb3_internal_swapprem_map`). Se TODOS os contratos do grupo casarem e a diferença for
  > R$ 0,005 → linha verde `Favor considerar: Banco recebe/paga … R$ #.##0,00`; 100% igual → omite.
- **BCC de compliance** (`2470497`): contraparte simplificada `INTRAGATACAMA*` → BCC
  `gdt.br.derivatives@restricted.chase.com`; `INTRAGLAWTON*` **e** título SWAP **e** Banco recebe →
  mesmo BCC; demais casos Lawton → BCC vazio. `build_eml_bytes` ganhou header `Bcc:`.
- Shell padrão dos avisos (`_email_shell`) com novo parâmetro `footer_extra` →
  **"JPMC Internal Use Only"** abaixo da assinatura, só nos e-mails de mensageria.
- Tabela do draft com as 12 colunas do print da B3 (`_MSG_TABLE_HEADERS`); intro
  Bom dia / Favor acatar / Obrigado(a)!; resposta via `_email_drafts_response`
  (1 → `.eml`, N → zip `mensageria_YYYYMMDD.zip`, From = e-mail do usuário logado).
- Testado ponta-a-ponta com o smoke DB: 11 drafts, segregação/subjects/roteamento/BCC verificados.

### Sidenav (`d78ad52`)
- **Operations B3** virou filho direto de **Daily Settlement** (grupo "B3 Files" removido);
  item placeholder **Settlement Messages** removido.

## 118. smoke_db.py — massa de dados fictícia LOCAL (nunca commitar) (`80bf075`)

- `smoke_db.py` na raiz gera dados fake para visualização local: b3 files
  (DPOSICAO-TER/DPOSICAO/DPOSICAO-SWAP/DFLUXO, últimos 5 dias úteis), New Deals `*_mock.json` de hoje
  e operations-b3 do dia (Títulos casando com os contratos das posições geradas, contrapartes
  INTRAG* — Atacama/Lawton/MGT — para exercitar as regras de BCC).
- **NUNCA commitar**: o script está no `.gitignore` (bloco "local dev stubs", junto do stub `awmpy.py`)
  e os dados caem nos patterns já ignorados (`b3 files/**/*.json`, `**/*_mock.json`,
  `daily settlement/**/*.json`).

## 119. Sessão 2026-07-27/28 — API Athena (`getTrades`): cliente, imports, schedulers e reconciliação

### Cliente (`bc0e3e1`, `e1beb7f`, `11c755c`)
- **NOVO módulo `apps/pages/athena_api.py`** — cliente do `getTrades` com SSO Kerberos ADFS/IDAnywhere:
  **User-Agent Trident** (sem isso o ADFS serve a página de login HTML em vez de negociar Negotiate) e
  replay dos `form_post` auto-submetidos até vir o JSON. Um fetch por produto.
- **Endpoint PROD** (`11c755c`): `athena-app` / `brazil-trade-data-api` — saiu o UAT
  (`athena-app-uat` / `brazil-cem-ai-market-data-api`). Os quatro produtos (NDF, Commodities, FXO,
  Swaps) respondem no PROD, então Commodities/Swaps deixaram de levantar `NotImplementedError`.
- **`build_session()` com `trust_env=False`** (`e1beb7f`): o `requests` herdava o proxy corporativo,
  que recusa hosts internos — era a causa do **WinError 10061** na instância Windows (o browser vai
  direto). `ATHENA_CA_BUNDLE` fica disponível se a validação TLS esbarrar na CA interna.
- `requests` e `reportlab` entram no `requirements.txt`; **`requests-negotiate-sspi` fica comentado**
  (Windows-only — instalar na instância JPM). Fora da rede JPM o scheduler falha silencioso (erro
  repetido rebaixado a debug) e sem `requests` nem sobe.

### Import de FXO e NDF (`bc0e3e1`, `e1beb7f`, `216ae52`, `c14d0e5`, `f9621da`)
- FXO: a API devolve as mesmas colunas do blotter XLSX → a construção linha→deal foi extraída para
  `_fxo_deal_from_row`, compartilhada pelas duas fontes (mesmos filtros e derivações).
- **Roteamento do NDF** (um pull, trade date = hoje): Instrument Type `FXForwardStartNDF` → **FWD Start**,
  exceto Strike Set Date = hoje (pulada — será cancelada e rebookada como vanilla); senão
  Publisher ≠ PTAX → **Other Publisher**; o resto → **NDF Vanilla**.
  **"PTAX" é match EXATO** (`f9621da`): o teste antigo `"PTAX" in publisher` engolia as variantes
  (`PTAX|USB|WMR|4` etc.), que devem cair na Other Publisher.
- Descartados: registros `isCancelled`/`isDead` (nos dois produtos) e End Counterparty =
  **`GLOBAL_HOLDING_BOOK`** (book interno, não é operação de cliente — `216ae52`).
- **Contraparte pelo End Counterparty** (`c14d0e5`): código estilo FX Cash Acronym (ex. `CMBB-LAW`)
  contra o `FX CASH ACCRONYM` do RefData, **sem** fallback pelo SPN do payload. Sem cadastro →
  SPN/Client/Tax ID vazios + badge Missing Counterparty, e o Accronym mostra o código da API.
- **ASIAN só com janela de fixing real** (first preenchido e ≠ last): sem isso o fallback do last
  fixing para a Expiration Date tornava toda vanilla ASIAN.
- **MXB→MXN** no mapa de moedas e **Rate gravado como 1/rate** quando a perna cotada é moeda fraca
  (MXN/CNH/COP/PEN/CLP) — a API manda Moeda/BRL, mas página, Conecta e Intrag trabalham com R$/moeda.
- Persistência **new-only** por `Deal+Client`: um poll periódico jamais reseta o status de um deal já
  trabalhado (diferente do fluxo XLSX, que pergunta antes de substituir).

### Schedulers (`bc0e3e1`, `c7f91a9`)
- NDF a cada **20 min** (`NDF_API_POLL_MIN`) e FXO a cada **1 hora** (`FXO_API_POLL_MIN`, padrão 60 —
  era 10 min). Threads daemon, erro repetido rebaixado a debug.

### Reconciliação Amend / Canceled (`f07af44`)
Os pulls deixaram de ser insert-only — cada deal da API é batido com o cache (chave `Deal+Client`):
- **Amend**: campo de dado diferente aplica o valor novo, Status vira `Amend` e os nomes dos campos vão
  para `AmendChanged`; o front converte a lista em índices de coluna e pinta as células em vermelho-claro
  pelo mesmo mecanismo do amend por e-mail (sobrevive a draw/reload). **Fora da comparação**: campos de
  workflow (`Status`/`B3_ID`/`Maker`/`Checker`) e de enriquecimento (`SPN`/`Client`/`TaxID`, que o RefData
  altera sem a operação ter mudado).
- **Canceled**: registro `isCancelled`/`isDead` cuja operação já foi importada tem o Status trocado para
  `Canceled` e **sai de todas as métricas e arquivos** — dashboard (distribuição/deal flow/totais),
  monitor (status e LEs), send-conecta (genéricos, FXO e commodities) e mapping B3. Cancelado não é
  reaberto por amend; cancelado nunca importado segue ignorado. Badge escuro nas quatro páginas.
- Notificações passam a trazer os três números (imported / amended / canceled).

### Deep-link (`3dc3a7d`)
- A página nova **NDF Vanilla** entrou no `PAGE_URL` das notificações (e no grupo New Deals, com
  deep-link de `?tradedate=`) — sem isso "New Deals in NDF Vanilla" não era clicável.

## 120. Sessão 2026-07-27/28 — NDF genéricos (Vanilla nova · Other Publisher · FWD Start)

### Página nova NDF Vanilla (`e1beb7f`)
- Criada sobre o template do Other Publisher, CRUD pelo cache genérico (produto `vanilla`), item no
  sidenav e card no Monitor.

### Colunas e apresentação
- **Other Quantity Currency** depois de Quantity Currency nas três páginas (`4478d38`), vinda do
  Other Quantity Units da API convertida para ISO (BRR→BRL); FX Pair idem (USB/BRR → USD/BRL). Todos os
  índices posteriores (toggle, exports, hidden targets, modal, `ND_COL_KEYS`) deslocados e auditados.
- **`ND_COL_KEYS` = colunas VISÍVEIS** (`c14d0e5`): a lista pulava `nd-col-acronym`, então do SPN em
  diante cada cabeçalho recebia a chave da coluna seguinte (Accronym exibia "Client", Client exibia
  "Tax ID"…). O `each()` percorre só o DOM do scroll-head — colunas ocultas (Rate no FWD Start,
  Is BRR Fixed no Other Publisher, Maker em todas) **não** aparecem lá.
- Ordenação padrão **Client A→Z** (`order [[11,'asc']]`) nas três (`d8ba4b1`); Vanilla com pageLength
  50 (`3fcb74c`).
- **Is BRR Fixed?** vira badge YES/NO (verde/amarelo) na Vanilla e FWD Start (`21d6ab6`) — render de
  *display* do DataTables, o dado da célula segue `"YES"/"NO"` cru (filtros/export/edição inalterados).
  Other Publisher fica de fora porque a coluna está oculta lá.
- **Missing Counterparty** (`3fcb74c`, `3907225`): o badge da coluna Status **substitui** o conteúdo da
  célula (guardado no nó para restauração) em vez de esconder os filhos — `children().hide()` não
  alcança text nodes, e o "New" continuava aparecendo ao lado. Vale para as **seis** páginas que usam o
  helper `missing-counterparty.js`; busters `?v=20260728a`.
- **Contraparte cadastrada depois do import** (`3fa7a07`): `/cache/search` re-enriquece na leitura —
  deal com SPN vazio cujo Acronym passou a existir no RefData ganha SPN/Client/Tax ID — e **regrava o
  arquivo do dia**. Antes o `reloadAndEnrich` só corrigia o DOM e sair/voltar mostrava a linha vazia.

### Mapping B3 (`6bbc32b`, `a6257bf`, `c6dab82`)
- Endpoint genérico `/api/new-deals/<produto>/mapping-b3` criado — antes o 404 em HTML estourava no
  front como "Unexpected token <". Mesma lógica do ndf-commodities (varre a pasta Return, linhas TER
  com EXECUCAO OK, marca Success/Error + B3_ID, apaga os retornos processados), com uma diferença:
  **o match do deal usa os 14 caracteres da direita**, que é o que os arquivos TER novos gravam no
  Código Identificador.
- Na **Vanilla** o mapping roda também com Status = New — o registro na B3 é feito por outra ferramenta
  por enquanto, não há transição Sent nessa página.
- O handler do botão gravava o B3 ID na coluna 4 (Deal) em vez da 5 (`a6257bf`) — era só visual, o cache
  em disco sempre gravou certo (um F5 já restaurava).

### Pending Confirmation e dashboard (`909a6de`, `a6257bf`, `4478d38`, `a194e7a`)
- Deal mapeado (Status→Success no PATCH ou no bulk-patch) segue para o Pending Confirmation como os
  demais produtos, com **Pending Status pelas regras de assinatura**: (Settlement − Trade) ≤ 60 dias
  corridos → `Exception FepWeb` (as três páginas); FWD Start → `Pending OTC`; Other Publisher/Vanilla
  pelo `SIGNATURE TYPE` do RefData — Internal → `Exception Digital Fep Web`, Digital →
  `Pending Digital Signature`, Manual e sem cadastro → `Pending Original`. `_pc_save_from_deal` ganhou o
  parâmetro `pending_status`. **Product Type = `NDF` simples** (não um rótulo por página).
- **FWD Start**: o pending é chaveado pelo **B3 ID** mapeado, não pelo Deal (`4478d38`).
- Dashboard: o bucket NDF foi dividido em sub-buckets (vanilla/otherpub/fwdstart, padrão do split
  FXO×OPT). **`_gen_ndf_counted`** (`a194e7a`): LE JPM conta sempre; LE MGT só contra cliente externo
  (Client sem Lawton e sem J.P. Morgan); outras LEs ficam fora — sem isso os espelhos intragrupo
  (MGT×JPM junto com JPM×MGT) contavam o mesmo deal duas vezes. Vale só para os **dois gráficos**;
  card inicial de NDF (`ndf_total`) e Top 5 seguem a regra antiga, de propósito.

### Intrag
- As três genéricas **não** alimentavam a Intrag NDF (`c6dab82` removeu os gatilhos do PATCH e do
  mapping, com comentário de onde reativar). **Reativado em `f9621da`**: Vanilla/OP **contra o Lawton**
  alimentam a Intrag NDF no layout do arquivo "Instrucao NDF Moeda" quando o Status vira Success —
  campos de mercadoria em N/A, nocional convertido para a moeda estrangeira, posição do fundo = inversa
  da Direction da linha do banco.

### Novo market de commodities (`aeec6a7`, `3c5e701`)
- `FO_0.5%_ROT_BRG_FOB` → ativo subjacente B3 **NAEB0011** (análogo do `FO_0.5%_SING_FOB` → NACX0005),
  FX holiday **PLATTS-EUROPE** (Rotterdam Barges), underlying **FIXO** (tipoCotacao F / fonteInfo 340).
  Já registrado no `Subjacente/Dominio.json`, então não gera Missing Index B3. Vale só para NDF Comm e
  Opt Comm — **fora** do `FIXED_UND` das três páginas de NDF de moeda.

## 121. Arquivo TER (Conecta) dos NDFs de moeda — regras finas

Layout posicional de **648 chars**, criado em `4478d38` — `api_generic_nd_send_conecta(product)` serve
`fwd-start` (prefixo `FWDSTART`) e `other-publishers` (prefixo `OTHERPUBLISHER`), com a flag `is_fwd`
separando as regras. Três arquivos por entidade: **BANCO** (`JPMORGANBM`), **LAWTON**
(`INTRAGLAWTONFDO` — perna espelho, cliente = Banco JPM) e **MGT** (`MORGANBC`).

- **Contas pela LE do deal** (`216ae52`): o Lançamento do Participante deixou de depender do nome do
  cliente — JPM → `73760009`, MGT → `04880006`. Contraparte pela matriz: LE JPM → MGT `04880006`,
  demais `73760102`; LE MGT → JPM `73760009`, demais `04880109`; Lawton mantém `00041007` nas duas LEs.
- **LE Lawton** (`45b29ed`): força parte `00041007` × contraparte `73760009` (banco, CNPJ em branco) no
  arquivo LAWTON. Antes só o Client contendo "J.P. Morgan" era detectado e o deal caía no bucket BANCO.
- **Valor Base / Quantidade** (`45b29ed`): o payload do OP manda a coluna como **`Notional`** (só o NDF
  Comm usa `TotalNotional`) — o servidor aceita os dois, nessa ordem. Antes saía zerado.
- **BRL fixed** (`45b29ed`, só no OP): a moeda estrangeira vira **Moeda de Referência** e o BRL a
  **Moeda Cotada**.
- **Fonte de Informação** (`45b29ed`): só o publisher **exatamente** `PTAX` vale `0`; PTAX* e demais
  publishers valem `1`.
- **Cotação para Fixing** (`45b29ed`) e **Boletim** (`f74f791`): **em branco no OP**. No FWD Start
  seguem valendo (diferença de dias úteis e PTAX=3 / demais=1, respectivamente).
- **Fonte de Consulta / Tela ou Função de Consulta** (`97fe07b`): o de-para publisher → códigos B3 casa
  o nome exato da planilha e, se falhar, **casa por token** — a Athena manda o publisher composto
  (`PTAX|USB|WMR|4`) e os dois campos saíam em branco. Tokens: `BFIX` → 14399/2,
  `BCENTRAL`|`OBSERVADO` → 11703/5, `SBSP`|`BCRP` → 11683/5, `WMR` → 247/0, `TRM` → 11682/5.
  Fonte de Consulta = **1 char**; Tela/Função = **8 chars à direita**, completada com espaços à esquerda.
- **Posições verificadas** na linha de 648 chars (índices 0-based do Python): fonte info `[86:90]`,
  Moeda Ref `[90:93]`, Moeda Cot `[93:96]`, Valor Base `[97:113]`, Trade+Settlement `[151:167]`,
  **Boletim `[167:168]`**, Tipo de Cotação `[168:169]`, **Fonte de Consulta `[178:179]`**,
  **Tela/Função `[179:187]`**, Cotação para Fixing `[253:254]`.
- **⚠️ Espelho JS obrigatório**: cada regra existe **duas vezes** — no servidor e em
  `buildConectaFields(deal, bizDayCount)` do template (preview do duplo clique, array `f[0..58]`:
  f[11] Fonte de Informação, f[21] Boletim, f[25] Fonte de Consulta, f[26] Tela/Função, f[38] Cotação
  para Fixing). O template do Other Publisher é OP-only (não precisa de gate `is_fwd`); mexeu numa
  regra, mexa nos dois lados.
- **Chaves do payload**: legal entity é **`LE`** (não `LegalEntity`) — um teste com a chave errada cai
  no bucket BANCO sem erro nenhum.
- Assunções documentadas: Data de Fixação do OP usa Strike Set Date (a página não tem o campo);
  "diferença de dias úteis" = dias ANBIMA em (last fixing, settlement]; Vanilla segue sem send próprio.

## 122. Sessão 2026-07-28 — Confirmações portadas da macro (NDF Commodities e Opção de Commodities)

### NDF Commodities (`a2f8b2c`)
- **Segregação** contraparte × mercadoria × família de moeda do strike, por trade date, sempre
  excluindo as pontas internas (Client = Banco J.P. Morgan ou Lawton — banco×lawton e lawton×banco não
  geram confirmação de cliente) e os `Canceled`.
- **Famílias** (saem do deal): `strike-usd`, `brl` (BRR/BRL), `platts` (bolsa Bloomberg no Subjacente) e
  `palm-oil` — **brl-platts e palm-oil ficam como "template pending"** até os `.doc` chegarem.
- Botão **Confirmation** na página lista os grupos da data com status e ações; a geração abre o
  documento pré-preenchido com as regras legadas: CGD do `CounterpartyDetails` por extenso, CNPJ
  formatado, Tabela de Referência (comprador Parte B quando o banco vende, strike × Fator Conversão em
  pt-BR, bullet "Não Aplicável", normalizações de ticker, texto dinâmico do CO1-2 com dias úteis ANBIMA).
- **Ciclo próprio por grupo** (day-files em `cache/confirmations/ndf-comm`): New → Generated (Word+PDF
  salvos) → Success (janela de validação com checklist ao lado do preview do PDF — só valida com tudo
  marcado).
- O **`.doc` é o próprio HTML do documento** (o Word abre HTML nativamente; os `.doc` legados já eram
  Word-HTML) e o **PDF é réplica reportlab** (A4 paisagem). Variantes: `platts` troca o Anexo para
  Código/Fonte de Divulgação; `brl` remove a PTAX pontual (USD PTAX = média entre as Datas
  Inicial/Final de Verificação, preenchidas com a janela de fixing) e o Anexo vira 15 colunas com
  Forward em R$.
- Os Word-HTML originais ficam em `templates/pages` como **referência**; os operacionais são os de
  **`templates/confirmations/`**.

### XML do contrato (FepWeb) (`ddd0a63`)
- Cada confirmação salva gera também o `.xml` com o nome do `numeroContrato`, na mesma pasta.
  Valores dos **deals-fonte** (não das linhas editadas no painel): `valor` = Σ notional × strike
  ajustado pelo quoted-in-cents (Fator Conversão do Subjacente, ou ÷100 quando YES) × Spot FXRate;
  `valorEstrangeiro` = a mesma soma sem o câmbio; `moedaEstrangeira` em código ISO numérico;
  `cnpjBanco` fixo; `cnpjCliente` = Tax ID; datas em `yyyymmdd` (vencimento = maior settlement do grupo).
- `numeroContrato`: várias operações → `NDF_Comm_YYYYMMDD_MERCADORIA`; uma → nome do deal
  (Mondelez: `Deal_MERCADORIA`). Ao gerar, ele é gravado na coluna **FepWeb ID** do Pending Confirmation
  (match por Trade Number = deal, varrendo os 3 DBs).
- A geração passou a **exigir status Success** nas operações (antes bastava não ser New/Pending).

### Opção de Commodities (`f9621da`)
- Mesma engenharia do NDF Comm: segregação contraparte × mercadoria × família (**CO1-2 vira família
  própria, template pendente**), página de geração com painel de edição, Word+PDF+XML no Electronic
  Inventory (pasta **Commodities Options**), ciclo New → Generated → Success, botão Confirmation na
  página e card no monitor.
- No **Anexo I a coluna Nº usa o Deal name** (opção não tem mais mnemônico). O XML reaproveita o
  contrato do NDF com `tipoOperacao=Option` e prefixo `Opt_Comm` no `numeroContrato` — por isso
  `_conf_ndf_xml` só ganhou parâmetros.

### Onde os arquivos são salvos (`53efeb2`) — **corrigido**
- Antes: `<EI_ROOT>\Confirmations\YYYY\mm. Mês\dd\<produto>` — uma árvore solta na raiz do share, e a
  **pasta da contraparte** (a que o Electronic Inventory navega e onde o upload manual grava) ficava
  vazia; ninguém achava as confirmações geradas.
- Agora: **`<EI_ROOT>\<Contraparte>\Confirmations\YYYY\mm. Month\dd\<produto>`**, resolvendo a
  contraparte por `parteb_nome` (fallback: acrônimo) via `_ei_resolve_client_dir(create=True)` — mesmo
  match tolerante e mesma criação de subpastas do upload. O mês usa `_ei_month_folder` (**inglês**)
  para cair na MESMA pasta mensal dos uploads, em vez de duplicar "07. Julho"/"07. July". As gravações
  passam por `_ei_long_path` (o caminho novo repete o nome da contraparte e estoura MAX_PATH em nomes
  longos).

### Detalhes de template e layout
- **Jinja fora de CSS/JS** (`c44a147`): o VS Code valida `<style>` como CSS e `<script>` como JS puros
  e acusava 8 erros por template. O `{% if doc_only %}` dentro do `<style>` virou regra estática
  `body.doc-only #doc-body` (a classe vem do Jinja no atributo do `<body>`, contexto HTML) e o
  `{{ conf|tojson }}` foi para um bloco `<script type="application/json">` lido com `JSON.parse`.
  **Padrão a seguir em qualquer template novo.**
- **Blocos de assinatura** (`40ccbe8`): o nome da parte fica em linha própria e os dois campos
  `Por:/____/Nome:` dividem uma única linha da tabela, lado a lado — antes saíam em escadinha no
  impresso (idem testemunhas). A réplica PDF acompanha (`confirmation_pdfs.py`).
- **`validate.html`** parametrizada por produto (`api_base`) e sem Jinja dentro de JS (`f9621da`).
- **`btn-primary` respeitando `.btn-sm`** (`6a4c386`): o tema Apple fixava padding/font-size literais no
  `.btn-primary` e no `.btn-outline-primary`, atropelando as variáveis `--ins-btn-*` do `.btn-sm` — no
  modal de Confirmations o **Open** saía maior que o **Validate**. O tamanho fixo agora só vale em
  `:not(.btn-sm):not(.btn-lg)`. **Sem node nesta máquina**: o `app.css` compilado foi editado à mão
  espelhando o SCSS — o próximo `npm run build` regenera igual.

### Spot FXRate (`543c9c4`)
- O booking recap traz `SpotFXRate` ao lado do FXConvDate e a informação era descartada. O parser
  compartilhado (`otc-fileupload`) passa a ler a coluna (header tolerante a espaços/caixa), grava no
  cache e **inclui a coluna no diff de Amend**. A coluna entra antes do FXConvDate na NDF Comm e Opt
  Comm, integrada a filtros, smart filter (number), toggle, exports, traduções e modal. Contagem de
  `<th>` conferida: **31 NDF / 36 Opt**. Deals já importados ficam com a coluna vazia.

## 123. Sessão 2026-07-27/28 — New Deals Monitor: zonas, contagem por LE e cards de Confirmations

- **Zonas** (`c6dab82`, `2ce62a7`, `a2f8b2c`): os cards deixaram a grade única e viraram três zonas —
  **B3 Registration** (larga, à esquerda), **Confirmations** e **Intrag** (com divisor). Cada subgrupo
  (NDF / Options / Swaps) é uma **linha**, com os cards de B3 à esquerda e os das outras zonas na mesma
  altura; abaixo de `xl` as metades empilham com o rótulo "Intrag — <grupo>". Produtos fora do catálogo
  caem numa seção **Others** de largura total. `#ndmZones` com `padding-bottom` para a última linha não
  encostar no rodapé (`6af6534`).
- **Status do Intrag em minúscula** (`ca599d7`): os caches do Intrag NDF/Option guardam o lifecycle na
  chave `status` (minúscula, convenção própria), mas o contador lia só `Status` — chave ausente caía no
  default `New` e todo deal do Intrag aparecia como New para sempre. O contador tenta as duas chaves.
- **Contagem por LE nos cards** (`14204f6`, `315ec0a`, `89564b1`, `c7f91a9`): cada card mostra a
  contagem por entidade abaixo dos chips — NDFs genéricos com JPM/MGT/LAW; NDF Comm, Commodities
  Options, FX Options e Swap CEM com JPM/LAW; Equity Options e Swap Equities com JPM/ATA; Intrag com
  LAW/ATA. Na Intrag a entidade vem do portfolio code: **`INTRAGJP552` = LAW, `INTRAGJP633` = ATA**
  (dict explícito; código inesperado conta como ATA). Os LEs viajam como **lista ordenada**, não dict,
  para o front não depender de ordenação de chaves do JSON.
  - **Regra final do `_ndm_deal_le` nos três NDFs genéricos** (`c7f91a9`): `LE=MGT` → MGT; Client
    contendo LAWTON → LAW; resto → JPM. As tentativas anteriores usavam a heurística de perna-espelho
    ("Client é o Banco J.P. Morgan") e classificavam MGT×JPM como LAW, porque o nome da MGT no RefData
    também casa com o regex de J.P. Morgan. **Os demais produtos B3 mantêm a convenção de espelho**,
    correta lá.
- **Cards de Confirmations** (`ddd0a63`, `6af6534`): NDF Commodities (ciclo completo), Commodities
  Options e FX Options (segregação contraparte × commodity / contraparte, pontas banco/Lawton fora) e
  **NDF FWD Start** (segregação por contraparte — NDF de moeda não tem mercadoria — somando as duas
  grafias de pasta do cache, `FwdStart` e `FWD Start`). Os que ainda não têm template ficam em New.
  - **FX Options passou a ciclo completo em `ae8b816`** (§139): o card não conta mais só a segregação —
    tem estado por grupo (New → Generated → Success) vindo de `_conf_state_load(ref, 'opt-fxo')`, igual
    ao NDF Commodities.
- Renomeados no catálogo (`14204f6`): Option Commodities → **Commodities Options**; Option FXO →
  **FX Options**.
- **Ícones das zonas** (`1ed2cec`): B3 Registration e Intrag usam os **mesmos SVGs do sidenav**
  (Index B3 e Intrag), num bloco oculto no fim do template que o JS clona (`zoneSvg`), evitando duplicar
  paths gigantes na string. Os três ícones de título ganharam a **animação padrão** no hover
  (`scale(1.1) rotate(-4deg)` + sombra, a cadeia about → sidenav → cards), com `prefers-reduced-motion`.

## 124. Sessão 2026-07-28 — NDF Summary (Settlement Summary)

- **Coluna Observation** (`4cf4a7a`): editável na célula e persistida no mesmo overlay diário do status
  (`/api/ndf-summary/observation`) — sobrevive a reload e troca de reference date; texto vazio limpa.
  Linhas manuais do Add row ficam fora do save (a célula de contraparte delas é um input, não um nome do
  cockpit que o overlay possa chavear). Feedback discreto na célula (borda azul = salvo, vermelha =
  falhou) e o dado da linha é atualizado junto, para um sort/filtro não redesenhar com o valor antigo.
- **Coluna Account cruzada** (`195e164`): a Direction é visão do **BANCO**, mas os defaults PAY/RECEIVE
  do Reference Data são visão da **CONTRAPARTE** — a coluna mostrava a conta errada. Agora cruza:
  Direction PAY (banco paga, cliente recebe) → default de **RECEIVE**; Direction RECEIVE → default de
  **PAY**. O e-mail de TEDs usa a mesma fonte.
- **Observation automática** (`195e164`): classificação das contas default do cliente (interna = BCO 376
  / JPMorgan) — ambas internas → "Pay and Receive Internal"; nenhuma → "Pay and Receive External";
  mistas → "Pay Internal | Receive External" (ou o inverso). **A observação manual prevalece**; apagar o
  texto manual restaura a automática no reload.
- **Ficha de Liquidação em PDF anexa** (`a6f6f8f`): para as 6 contrapartes que a macro legada tratava
  (ABB Automacao, ABB Eletrificacao, ABB Eletrificacao Filial 0003, Hitachi Energy, Phinia e Veolia
  Water Technologies), o aviso de liquidação leva um PDF com o mesmo conteúdo do cartão branco do
  e-mail. Nome: `<contraparte> - <yyyymmdd>.pdf`; match tolerante a caixa/acentos/traços; Pay/Rec com
  dois avisos gera um PDF por aviso. Usa **reportlab importado de forma preguiçosa** — sem a lib o
  e-mail sai **sem** o anexo, não falha. O `build_eml_bytes` ganhou **anexos genéricos**
  (multipart/mixed envolvendo o corpo, wordmark inline preservado via multipart/related); **sem anexos o
  formato antigo permanece byte a byte**, então os demais e-mails não mudaram.
- **Largura** (`4cf4a7a` → `ec930b0` → `f419006`): col-xxl-8 → 10 → 11 → **col-12**, com a coluna
  Direction travada em **84px** — foi preciso o card inteiro para Account e Observation caberem sem
  scroll horizontal. Botões de ação por linha (`.ops-row-act`) travados em **32px** (min/max-width e
  height), porque uma regra do tema alargava o check na instância da equipe.

## 125. Sessão 2026-07-28 — Pending Confirmation

- **Colunas removidas** (`57c7eca`): **Baixa Sem Abono** e **Abono** saem de cabeçalho, filtros,
  Show/Hide, smart filter e modal. A coluna **Pendência deixa de ser data** — campo de texto livre, sem
  datepicker e sem ordenação cronológica.
- **Economic Group e Signature Type do RefData** (`57c7eca`): preenchidos em todo insert vindo dos feeds
  pelo novo `_pc_refdata_enrich` (chave SPN, fallback nome do Client), que roda no `_pc_save_from_deal`
  (todas as páginas de New Deals) e no import do xlsx Pending Update.
- **INSERT nomeando colunas** (em vez de VALUES posicional): o app funciona também contra um DB ainda
  não migrado (colunas legadas extras ficam NULL) — **sem janela de quebra entre o pull e o script**.
- **Dark mode e modal** (`f148d62`): os campos auto usavam `var(--bs-secondary-bg)` — este tema só
  define tokens `--ins-*`, então o fallback claro `#e9ecef` valia sempre e os campos ficavam brancos no
  escuro (trocados por `--ins-tertiary-bg`/`--ins-secondary-color`; reforça a regra da §109.1). O Edit
  preenchia o modal com o **HTML cru** das células (Status aparecia como `&lt; 10 dias…`) — todos os
  campos passam pelo `_pcStrip`.

## 126. Sessão 2026-07-28 — NOVA página Intrag Swap (`77b8b29`)

- `/intrag-swap` com as **36 colunas** do layout B3 de swap (CARTEIRA, Código B3, datas, partes/curvas,
  prêmio e os dois blocos de curva — o segundo ganha sufixo "(2)" **só na UI**; o `.txt` leva apenas os
  valores na ordem do layout).
- Mesmo ciclo da Intrag NDF: day-files `YYYYMMDD_intrag_swap.json` em `cache/new deals/Intrag/Swap`,
  **New → Pending → Approved → Sent** com 4-eyes (maker ≠ checker), Send gerando
  `Intrag-Swap-YYYYMMDD.txt` na mesma pasta de rede **agrupado por Data Início**, e Mapping Intrag ID
  pelo CSV Boletas (**assume 'SWAP' na col B e B3 ID na col C** — espelho da NDF; se o retorno diferir,
  ajustar num ponto só).
- Headers/filtros/modal são **gerados em JS a partir de `SWAP_COLS`** para não triplicar 36 blocos
  estáticos de HTML. **Sem feed automático** — linhas entram pelo Add Row.
- Sidenav: item **Swap** no menu Intrag (entra no Page Access automaticamente) e "Intrag Swap" nos mapas
  de notificação (routes + topbar). No mesmo commit saíram os placeholders **SPB** e **SDConta** do
  Daily Settlement (âncoras `#spb`/`#sdconta` sem página real).

## 127. Sessão 2026-07-28 — Correções diversas

- **Tema: padrão único light/dark** (`50c2bcf`) — usuários com config antiga no localStorage (tema
  `system`, corpo claro com sidenav/topbar escuros, ou cores avulsas do customizer) ficavam presos a um
  visual fora do padrão. O `config.js` **normaliza a config no load de toda página** (tema ≠ dark vira
  light; cores de topbar/menu seguem sempre o tema) e **regrava o localStorage**, consertando o usuário
  afetado no primeiro reload. O `changeTheme` só conhece light/dark (ramo `system` aposentado) e a opção
  System saiu do customizer. Cache-busters em `config.js`/`app.js`, que não tinham nenhum.
- **Topbar: nav central não sobrepõe os controles** (`e56c3fe`) — o nav é `position: absolute` para ficar
  centrado na página, e fora do fluxo passava por cima de sino/tema/idioma/usuário quando a janela
  encolhia. **Abaixo de 1500px** ele entra no fluxo flex entre o logo e os controles, com `min-width: 0`
  e scroll horizontal de scrollbar escondida (cobre quem personalizou até 7 atalhos). Acima de 1500px o
  layout original fica intacto; abaixo de 992px o nav já era escondido. Cache-buster no
  `visual-refresh.css`, que não tinha.
- **Electronic Inventory: listagem escondia não-PDF** (`81ecc7f`) — o filtro `ext != .pdf` deixava uma
  SSI escaneada em **JPG** (caso AMAGGI) invisível: a página mostrava 0 arquivos com o documento na
  pasta. O filtro passa a aceitar o **mesmo whitelist do Upload** (.pdf, imagens, .msg/.eml, office,
  .zip). Lixo de sistema segue fora por não estar no whitelist.
- **Reference Data: edit de conta bancária dava `not_found`** (`d7cb876`) — causa-raiz: registros
  antigos do `CounterpartyDetails.json` guardam BANKING como PAY/RECEIVE, **sem lista ACCOUNTS nem ids**.
  O modal (que lê o JSON estático) inventava um id aleatório no navegador e o backend re-migrava o
  legado **em memória a cada request com outros uuids, sem nunca persistir** — o id nunca batia (caso
  SUZANO SA). Agora o `_cpd_load` **migra todos os registros para o formato canônico** (ACCOUNTS/contatos
  com id estável, CGD em itens, NET presente) e **persiste na primeira leitura em que algo mudou**;
  a normalização é idempotente e também roda na subida do app. O JSON versionado foi junto já migrado;
  na instância da equipe o arquivo local é migrado na subida (com `.bak` automático).
- **OTM Settlements** (`ea0e4bb`): ordenação padrão **Cpty Name A→Z, depois Trade Id A→Z** (a tabela
  abria com `order: []`, na ordem crua do arquivo). Os índices são resolvidos **pelo nome da coluna**
  (+3 das fixas), então sobrevivem a mudanças na lista de colunas do servidor.
- **Operations B3 / Mensageria** (`ed12d8c`): resgate de TER saía como "Resgate NDF" no subject — a
  macro que a página substitui usa **"Vencimento de Termo"** e o time reconhece o e-mail por esse nome.
  O "Favor considerar" comparava as somatórias com tolerância de meio centavo **sem arredondar**, o que
  podia engolir divergência real de R$ 0,01: agora os dois lados são arredondados ao centavo e qualquer
  diferença ≥ 1 centavo mostra a linha.
- **Daily Metric vira draft** (`960ce05`): o card do Control Panel disparava o e-mail direto pelo SMTP,
  sem revisão. `_send_daily_metric_email` virou **`_build_daily_metric_eml`** — mesma mensagem, com
  `X-Unsent: 1`, devolvida em base64 e baixada pela página (padrão dos avisos de prêmio). **O draft leva
  o header `Bcc`** (diferente do envio real, onde o BCC fica só no envelope) para o campo aparecer
  preenchido no Outlook. Não havia agendador — o único caminho era o botão Run. Textos do card e da
  notificação: Sent → **Draft**.
- **Daily Metric e Weekly Escalation leem do DB** (`f9621da`): passam a ler direto do DB pending
  (Aging/Status recalculados na leitura) — o snapshot diário podia estar defasado e vira apenas fallback.
- **`update_base_from_xlsx` grava SIGNATURE TYPE** (`a2add2e`): a planilha Atualizar Base ganhou a
  coluna K; o script grava no RefData casando pelo SPN, com a regra dos demais campos (célula vazia não
  sobrescreve). Contador novo no relatório de dry-run/apply.

## 128. ⚠️ Scripts a rodar UMA VEZ na instância da equipe (após o pull)

Migrações idempotentes — rodar na raiz do projeto, com o venv ativo:

```bash
python scripts/update_pending_confirmation_dbs.py       # 57c7eca — remove Baixa Sem Abono/Abono dos 3 DuckDBs
                                                        #           e preenche Economic Group/Signature Type pelo RefData
python scripts/update_pending_confirmation_bankers.py   # 8c15508 — regrava Owner (banker) pelo BANKER do RefData
                                                        #           (chave SPN sem zeros à esquerda; fallback nome do Client)
```

- Os dois são **idempotentes**; a página lê dos DBs, então corrigir os DBs corrige a página.
- O `CounterpartyDetails.json` **não** precisa de script: a migração roda sozinha na subida do app, com
  `.bak` automático (`d7cb876`).
- Dependências novas na instância JPM: `pip install -r requirements.txt` (traz `requests` e `reportlab`)
  **e, para o SSO da API Athena no Windows**, descomentar/instalar `requests-negotiate-sspi`.

## 129. Sessão 2026-07-28 — New Deals Monitor: sombreado de progresso nos cards (`9ac78d8`)

Pedido: card com operação e status ainda ≠ Success mostra um **sombreado que dá sensação de
profundidade** (não a cor do card, não um anel duro), mudando de cor conforme os deals avançam —
vermelho em New, verde quando tudo vira Success.

- **Progresso ponderado por status**, não binário: `STATUS_WEIGHT = {New: 0, Pending: .25,
  Generated: .4, Approved: .6, Sent: .8, Success: 1}`; `progressOf(c)` = Σ(peso × contagem) / total,
  clampado em [0,1]. Status desconhecido pesa 0 (fica vermelho — chama atenção, que é o desejado).
  Card **sem operação nenhuma** devolve `null` e não ganha halo.
- **Cor interpolada em duas pernas** (`progressRgb`): #dc3545 → #f7b84b (0→.5) → #1a8a4a (.5→1). O JS
  escreve só os canais RGB numa CSS var (`--ndm-prog: 220, 53, 69`) e o CSS monta os `rgba(...)` com
  os alfas de cada camada — uma var por card, sem gerar CSS por estado.
- **Três camadas de sombra** (contato 2px, média 10–24px, halo largo 22–50px) + borda em alfa .3.
  Sem `0 0 0 1px`: o anel colorido era exatamente o que o usuário rejeitou. Variantes para
  `.is-done` (verde mais discreto, o card pronto não precisa gritar), `[data-bs-theme=dark]`
  (alfas maiores) e hover.
- **O bloco `.ndm-card--prog` fica DEPOIS do `:hover`** no CSS — mesma especificidade, quem vem por
  último ganha; se subir, o hover padrão engole o halo.
- Testado com a matemática isolada no JavaScriptCore (9 casos: tudo New → rgb(220,53,69); tudo
  Success → verde + `.is-done`; 2 Generated → âmbar; status desconhecido → vermelho).

## 130. Sessão 2026-07-28 — Intrag NDF: termo de moeda uma coluna à esquerda (`bc3cd5e`)

`_save_intrag_ndf_moeda_entry` (routes.py ~15049) grava a linha do Intrag quando um NDF de **moeda**
vira Success. Da coluna **Trade Price** até **Observation** cada valor andava uma casa à direita em
relação ao layout de mercadoria: a taxa forward caía em Asian Fwd Avg Rate, o publisher em Comm
Fixing e o offset do fixing em Adjustment Type.

- Layout correto (chave interna → coluna da tabela): `strike` = Trade Price `0` · `strike_currency` =
  Settlement Parity `BRL` · `expiry_month_year` = Maturity Month/Year `N/A` · `anbima_bizdays` =
  Spot Fixing `N/A` · **`fixed_0` = Forward Rate (R$/CCY) = taxa** · `na_1` = Asian Fwd Avg Rate `N/A` ·
  **`na_2` = Information Source = publisher** · **`weekday_bizdays` = Comm Fixing = D-N** ·
  `trade_type_label` = Adjustment Type `N/A` · `strike_ccy_label` = Observation `N/A` · `na_3` =
  Discount Factor `N/A`. Antes de Trade Price nada se move.
- ⚠️ **As chaves têm nomes legados** (`na_1`, `weekday_bizdays`, `strike_ccy_label`) e é exatamente
  isso que escondia o desalinhamento — cada uma agora tem o nome da coluna em comentário ao lado.
  A ordem real das colunas está em `NDF_COLS`/`ENTRY_FIELDS` no `intrag-ndf.html` (~linha 519):
  **confira lá antes de mexer**, não pelo nome da chave.
- Com o shift, Comm Fixing passa a levar o D-N igual às linhas de mercadoria — era o sinal de que o
  layout de moeda é que estava errado, não o de commodity.
- **Linhas já gravadas no cache mantêm o layout antigo** — a correção vale para os deals que virarem
  Success daqui pra frente. Migrar as existentes precisa de script (não feito; pedir informando a
  data de corte).

## 131. Framework de Mapping — de-paras saem do código e viram cadastro em tela

Pedido do usuário: **"não pode ter nenhum mapping hardcoded, tudo que ser possível cadastrar novos
mappings via tela"**. Nasceu em `bc5aea4` e cresceu em `2b168a9`, `f579d26`, `2feb2bd`, `4e4992c`,
`f789d02`, `88dc43d`. Leia esta seção antes de acrescentar qualquer de-para novo ao código.

### Como funciona

- **Registro único** `_MAPPING_DEFS` em `routes.py` (~14240): `chave → {label, columns, seed[, file,
  upgrade]}`. Cada coluna é `{key, label[, type:'select', options[, autofill]]}`.
- **Arquivos** em `apps/static/data/mappings/` (`_MAPPINGS_DIR`), um JSON por mapping, **versionados**.
  `file` sobrescreve o caminho (é o caso do `BaseMoeda.json`, que mora na mesma pasta desde `f789d02`).
- **`_mapping_rows(key)`** cria o arquivo com o SEED na primeira leitura e **cacheia por mtime** — o
  comportamento não muda até alguém editar, e **edição pela tela vale na requisição seguinte, sem
  restart** (diferente de mudança em `routes.py`, que exige restart na instância da equipe).
- **API genérica** `/api/mappings/<key>` GET/POST. O POST **substitui o arquivo inteiro** e coerciona as
  chaves para as colunas do registro. ⚠️ Valores **não são trimados de propósito**: em código B3 como
  `'C '` o espaço final faz parte do código.
- **Tela** `/mapping` (`mapping.html`, item Mapping na seção Data Base do sidenav), layout do Electronic
  Inventory: rail à esquerda com a lista (array `TYPES`, um item por mapping) e card à direita com Add
  (modal glass, um campo por coluna), Export (CSV `;` com BOM + copiar tab-separated, sobre as linhas
  filtradas), filtro por coluna, Show N entries e **paginação** (`f579d26`).
- **`upgrade`** (opcional): callable que converte linhas de formato antigo na leitura — usado no
  `interbook-ndf` para arquivos que ficaram no formato `RULE`.
- **`autofill`** (opcional, numa coluna `select`): nome de OUTRA coluna. Ao escolher o valor, a tela
  copia para essa outra coluna o que as linhas **já cadastradas** usam para aquele valor (LE `JPM` →
  Settlement Location `BRAZIL`). Respeita edição manual: só sobrescreve se o destino está vazio ou tem
  o valor da opção anterior. É genérico — qualquer mapping pode usar.

### Mappings existentes

| chave | label | para quê |
|---|---|---|
| `currency-base` | Currency Base | `BaseMoeda.json`: código B3 da moeda + **Athena Code**, **Weak Ccy** e **Inverse Decimals** (absorveu o antigo `currency-codes`) |
| `interbook-ndf` | Interbook API (NDF) | pares que marcam perna interbook no import da API |
| `publisher-ndf` | Publisher × B3 (NDF) | feeder → Fonte de Informação / Fonte de Consulta / Tela ou Função de Consulta |
| `le-accronym` | Legal Entity × Accronym | LE por accronym e por Settlement Location |
| `commodities-b3` | Commodities × B3 Code | market Athena → código B3, Holiday Calendar e **Fixed Quote** (absorveu `fixed-underlyings`) |
| `bank-name` | Bank Name | bancos do editor de contraparte (ID COMPE, nome, ISPB, Tax ID) |
| `fxo-conv-rate` | FXO Conversion Rate | as duas colunas de Taxa de Conversão do Anexo I da confirmação **Asian** de FX Options (Moeda Base → nome da taxa + Venda/Compra). Seed só com `USD → USD PTAX / Venda`; moeda sem cadastro vira aviso no painel (§139) |
| `swap-curves` | Swap Curves (Athena × B3) | vazio, criado para uso futuro |

### Consumidores no front

Páginas que precisavam dos valores em JS fazem `fetch('/api/mappings/<key>')` e **substituem literais
que ficam como fallback** (se o fetch falhar, o comportamento é o de antes): `_FIXED_UND` e os mapas
`MARKET_*`/`MARKET_TO_FX_HOLIDAY` (`otc-fileupload.js`, `deals-processing-table.js`), `CP_BANKS`
(`reference-data.html`), `_PUB_ROWS` (NDF Other Publisher e FWD Start). O `BaseMoeda.json` é lido por
`fetch('/static/data/mappings/BaseMoeda.json')` — **o caminho mudou em `f789d02`**, quem copiar código
antigo vai pegar 404.

## 132. Sessão 2026-07-29 — Interbook por par livre + coluna Other Book (`2feb2bd`)

### Interbook: o par virou configuração, não regra fechada

O mapping `interbook-ndf` tinha as combinações de campos presas na coluna `RULE` (`OTHER BOOK x
SETTLEMENT LOCATION` / `END COUNTERPARTY x TRADING BOOK`): dava para cadastrar valores novos, mas não um
**par de campos** novo. Agora cada linha escolhe os dois campos:

- Colunas: `FIELD A` (select com os campos do getTrades) · `VALUE A` · `FIELD B` · `VALUE B` ·
  `BOTH WAYS`. Opções de campo em `_MAP_INTERBOOK_FIELDS`.
- `_ndf_interbook_rules()` devolve `(campo A, valor A, campo B, valor B)` com os valores achatados por
  `_ndf_flat`; `_ndf_is_interbook(norm)` lê o campo **direto do registro normalizado**, então par inédito
  (ex. Publisher × Quantity Currency) funciona sem tocar em código.
- **`BOTH WAYS = YES`** casa também com os valores **trocados entre os dois campos** — é o que a regra de
  End Counterparty × Trading Book precisa, porque a mesma operação chega uma vez por ponta.
- As 11 linhas antigas foram convertidas; `_interbook_upgrade` converte na leitura arquivo que ainda
  esteja no formato `RULE`.

### Coluna Other Book nas três páginas

Entre TradingBook e Settlement Location: **vanilla/OP col 26, FWD Start col 28**, alimentada pelo campo
`Other Book` da API (era a informação que decidia o descarte do interbook e não aparecia na tela).
Deals importados antes disso ficam com a coluna vazia até o próximo pull.

⚠️ **Inserir coluna nessas páginas mexe em 14 lugares**: `<th>` do header, `<th>` da linha de filtro,
`COL_TO_JSON_FIELD`, `AMEND_FIELD_COLS`, `dealJsonToRow`, `ND_COL_KEYS` (i18n do header), `columnDefs`
(colunas ocultas), `columnLabels`, options do mass edit, `SF_COLS`, `SF_LABEL_TO_FIELD`,
`extractRowDeal`, `rowDataToNdfDeal` e `rowMaker`.

### Dois índices defasados que apareceram no caminho

- **Maker parado em `e1beb7f`**: as seis referências de célula do Maker apontavam para a coluna 25
  (27 no FWD), que era o Maker naquele commit. Depois entraram Is BRR Fixed e Settlement Location e a 25
  passou a ser o **TradingBook** — editar ou aprovar gravava o SID na célula do book, a checagem de
  quatro olhos comparava SID com nome de book (não bloqueava depois de um reload) e o fallback POST do
  `rowDataToNdfDeal` persistia esse SID **como TradingBook**. Agora é a constante **`MAKER_COL_INDEX`**
  ao lado de `STATUS_COL_INDEX`: ao inserir coluna nova, atualize só ela. ⚠️ Deals com `TradingBook` em
  formato de SID perderam o book original e precisam voltar do Athena.
- **Settlement Location no smart filter**: estava em `SF_COLS` mas não em `SF_LABEL_TO_FIELD`, então o
  filtro era descartado antes do POST e a tela não reagia. Ao adicionar coluna ao smart filter, as
  **duas** listas precisam da entrada.

## 133. Sessão 2026-07-29 — Publisher × B3 e Legal Entity × Accronym (`4e4992c`, `f789d02`, `88dc43d`)

### Publisher (feeder) × B3

O feeder da Athena decidia Fonte de Informação, Fonte de Consulta e Tela/Função de Consulta por
dicionário hardcoded — um no servidor (send-conecta genérico) e outro **repetido em cada página**.

- Colunas: `PUBLISHER` (nome exato) · `TOKENS` (casa por trecho, separado por vírgula) · `FONTE INFO` ·
  `FONTE CONSULTA` · `TELA CONSULTA` · `NOTES` (guarda o que eram comentários: BLOOMBERG / REUTERS /
  OUTROS, que explicam o código da Fonte de Consulta).
- Ordem de resolução: **nome exato primeiro, token depois** (`_ndf_publisher_row`). A Athena manda o
  feeder composto (`PTAX|USB|WMR|4` → REUTERS - WMR).
- ⚠️ **A linha do PTAX fica sem token de propósito**: é isso que mantém o PTAX puro em Fonte de
  Informação `0` sem arrastar as variantes, que valem `1`. Se alguém preencher `PTAX` em TOKENS, todo
  feeder composto passa a valer 0 e o arquivo sai errado.
- Sem linha casada: Fonte de Informação `1` e os dois códigos em branco (era o comportamento antigo).
  No FWD Start o **Boletim** é derivado (`0` → `3`, senão `1`), não duplicado.
- **Corrigiu divergência preview × arquivo**: o FWD Start decidia por `indexOf('PTAX')` e o servidor por
  igualdade, então feeder composto aparecia como Fonte 0 / Boletim 3 na tela e saía 1 / 1 no arquivo.

### Legal Entity × Accronym (grafia com dois C, no nome e no header)

- Colunas: `LE` (**dropdown** — / JPM / MGT / LAWTON, com `autofill` da Settlement Location) ·
  `ACCRONYM` · `SETTLEMENT LOCATION`.
- Resolução da LE em `_ndf_deal_from_api`: **linha do accronym vence** (é a específica), senão a da
  Settlement Location, senão a location crua. O de-para `BRAZIL→JPM / JPMCBB→MGT` que estava no código
  virou as três linhas do seed.
- **O "não quero criar 200 linhas de Lawton/Banco/MGT no Reference Data" foi resolvido sem coluna de
  sufixo**: `_ndf_accronym_variants` tenta o End Counterparty exato e depois **o código sem o último
  trecho depois do hífen** (`CMBB-LAW` → `CMBB`), exigindo base ≥ 3 caracteres. Então o cadastro segue
  com **uma linha por contraparte** servindo as três entidades. O mapping fica para o caso que não segue
  padrão nenhum (código do cliente na entidade que não é base+sufixo).
- `_generic_nd_reenrich` usa a mesma regra e **normaliza o Acronym gravado** para o do RefData: deal já
  importado com `CMBB-LAW` se resolve na próxima visita à página, **sem novo pull da API**.

### O caso das pernas internas (End Counterparty = nome de book) — `7e4a7f8`

Sintoma que motivou o ajuste: nas três páginas de NDF, operações com accronym `LM-FXECOMBRR FXC` e
`LM-FXECOMBRR JPMCBB FXC` apareciam com **LE JPM** (vinha da Settlement Location `BRAZIL`, que para essas
pernas está errada) e **Missing Counterparty** em SPN/Client/Tax ID — a contraparte é a própria entidade,
não um cliente, e o accronym que a API manda é nome de book.

- **`_ndf_le_accronyms(le)`** resolve isso sem coluna nova: cadastre para a LE **tanto os códigos que a
  API manda** (os nomes de book) **quanto o accronym da entidade no Reference Data**. O
  `_ndf_ref_by_accronym` tenta, em ordem: código exato → accronym base → **qualquer código cadastrado
  para aquela LE** (o nome da LE entra como último candidato). Assim uma linha de cadastro por entidade
  atende todos os books dela, e cliente normal nunca é sequestrado pela entidade, porque o exato vem
  primeiro.
- Entidades já presentes no `RefData.json`: **`JPMORGANBM`** (BANCO J.P MORGAN S.A, SPN 23779) e
  **`LAWTON`** (LAWTON MULTIMERCADO EXCLUSIVO, SPN 37862). ⚠️ **Não existe linha do MGT** — enquanto
  ninguém criar essa contraparte no Reference Data, as pernas de MGT continuam Missing Counterparty (a LE
  já sai certa). É **uma** linha, não 200.
- O `Acronym` da tabela passa a mostrar o código do Reference Data (ex. `JPMORGANBM`) quando a linha é
  encontrada. O nome do book segue visível nas colunas **Trading Book / Other Book**.
- No re-enriquecimento, quando o accronym gravado identifica a LE pelo mapping, **a LE é corrigida** —
  as linhas que já estão no cache se acertam na próxima visita à página. Só mexe em linha sem SPN, então
  operação já enriquecida não é tocada.

### BaseMoeda.json mudou de lugar

Foi para `apps/static/data/mappings/BaseMoeda.json` (`git mv`, histórico preservado). Acompanharam: o
`file` do registro `currency-base`, os dois `fetch` das páginas de NDF e o `_moeda_num_code` — que
aproveitou para **ler pelo loader do mapping** em vez de abrir o arquivo na mão: antes cacheava em
módulo e só pegava edição da tela depois de **reiniciar o servidor**, ou seja, os códigos de moeda dos
arquivos TER usavam o valor antigo.

## 134. Sessão 2026-07-30 — Reference Date no pull da API Athena

Campo **Reference Date** (input `date`, id `apiRefDate`, **default hoje**) na toolbar das quatro páginas
que puxam da API — Opt FXO, NDF Vanilla, Other Publisher e FWD Start — ao lado do botão Import. É a data
que o `getTrades` usa; antes era sempre o relógio do servidor, então não havia como reimportar um dia
anterior sem mexer no código.

- Servidor: `_api_ref_date(value)` aceita `YYYY-MM-DD` (o que o input date manda), `YYYYMMDD` (formato da
  API) e `DD/MM/YYYY`; **vazio ou inválido cai em hoje** e loga warning. `_ndf_api_pull` e `_fxo_api_pull`
  ganharam `ref_date=None`; os endpoints `/api/new-deals/{ndf,opt-fxo}/import-api` leem `ref_date` do JSON
  do POST.
- ⚠️ Em `_ndf_api_pull` a variável **`now` é a data de referência**, não o relógio — ela decide o arquivo
  do dia, a regra do Strike Set Date "de hoje" que descarta FWD Start e o dia procurado nos
  cancelamentos. No FXO o equivalente é `ref_dt`. Se um dia voltar a chamar `datetime.now()` dentro dessas
  funções, o pull retroativo grava no arquivo errado.
- **Os schedulers não passam a data** (o default `None` mantém hoje): poll de 20 min do NDF e horário do
  FXO seguem puxando o dia corrente.
- Notificação ganha sufixo ` (ref DD/MM/YYYY)` **só quando a data não é hoje**, para import retroativo não
  se confundir com o do dia no feed.
- O texto da confirmação passou a mostrar a data escolhida (`{date}` nas chaves `swal-ndf-api-text` /
  `swal-fxo-api-text`, substituído no front por `apiRefDateLabel()` em DD/MM/YYYY). Chave nova do rótulo:
  `nd-ref-date`.
- Verificação: 16 casos do parser/sufixo e das assinaturas, 32 checagens de front (campo montado, default
  hoje, rótulo, `ref_date` no corpo do POST) executando o bloco real das quatro páginas, e 6 chamadas dos
  endpoints com o cliente Athena stubado, conferindo a data que chega na API e a devolvida no JSON.

### Ajustes depois do primeiro teste do usuário

- **Formato: `<input type="date">` renderiza no locale do navegador** (mm/dd/yyyy em en-US). Virou input
  de texto com **flatpickr `dateFormat: 'd/m/Y'`**, o mesmo padrão de `pending-confirmation` e
  `control-panel`. A tela mostra dd/mm/yyyy; `apiRefDate()` converte para ISO no POST e
  `apiRefDateLabel()` devolve o que está na tela.
- ⚠️ **"Import de outra data não funciona"**: o import funcionava — as três páginas de NDF e a de FXO
  abrem com **filtro padrão Trade Date = hoje** (chip do smart filter, busca server-side), então o que
  foi importado de outro dia ficava fora da consulta. Pior: numa reimportação o `imported` volta 0 (a
  persistência é new-only), e o alerta "0" reforçava a impressão de falha. Agora `sfSetTradeDate(dmy)`
  reposiciona o chip de Trade Date e refaz a busca; ela é chamada **ao trocar a data no campo** e
  **depois do import quando a data não é hoje** (antes de mexer na tabela, para pegar também o que já
  estava gravado daquele dia). Quem importa o dia corrente não vê diferença nenhuma.
- Nada a mudar em `athena_api.py`: o `date` já era parâmetro do `getTrades` (`?product=NDF&date=YYYYMMDD`)
  e sempre foi repassado — o que estava fixo era o chamador, que mandava o relógio do servidor.
- **Ícone de calendário**: o input é de texto (flatpickr), então não tem o ícone nativo do `type=date`.
  CSS `#apiRefDate` com o SVG em `background-image` nas quatro páginas, com variante dark — mesmo
  tratamento dos campos de data do `pending-confirmation`.
- **Scheduler é sempre hoje**, confirmado com o usuário: ele não passa `ref_date` e o default `None` cai
  em hoje. Só o botão Import manda a data do campo.

### Prestação de contas do pull (o "veio 0, era 128")

Reclamação de import que devolvia 0 quando se esperava 128. O retorno e o alerta não diziam **onde** os
registros foram parar — API vazia, tudo cancelado na origem e filtro de interbook produziam o mesmo zero.

- Os dois pulls agora **logam a conta fechada** (`[ndf-api] pull ref=... : N fetched · roteados fwd/op/
  vanilla · importados · amendados · dead/cancelados na API · interbook · strike set na data`) e devolvem
  **`dead`** no JSON, que antes só existia como efeito colateral (`canceled`, que conta apenas os deals
  que já estavam num arquivo — numa base recém-apagada é sempre 0 e some da vista).
- O alerta das quatro páginas mostra a linha de breakdown (`apiBreakdown(res)`), e quando **nada** entrou
  ele **não fecha sozinho** — antes sumia em 2–3 s levando a informação embora.
- Ao investigar isso: `_generic_nd_persist_new_deals` grava pelo **TradeDate do deal**, não pela data de
  referência, então import retroativo cai no arquivo certo — o zero não vinha daí.

## 135. Sessão 2026-07-30 — Varredura de SQL injection e de concorrência dos bancos

### SQL injection: nada injetável

Levantamento por **AST** (grep não pega chamada multilinha): **102 pontos de execução de SQL** em todos os
`.py` do projeto. 78 são string literal, 6 são `pandas.read_csv`/`_pc_write_exec`, e as **18 montadas** foram
conferidas uma a uma:

- **DDL sobre identificador do próprio código** — `_PC_TABLE` / `_PC_COLUMNS` (constantes de módulo), e
  `TABLE`/`PAGE_COLUMNS`/`DROP_COLS` nos scripts. Nome de tabela e coluna **não podem ser bindados**; é o
  caso em que o cheat sheet do OWASP admite montar string. ⚠️ Se um dia um desses nomes puder vir de
  request, o caminho é **allow-list contra tupla fixa**, não escaping.
- **`IN ({})`** (`_conf_pc_set_fepweb`) — o `{}` recebe `?, ?, ?`; os valores vão como parâmetros.
- **`INTERVAL '{}'`** (2FA, linhas ~1068 e ~1155) — DuckDB não aceita bind dentro de literal de intervalo;
  os valores são `int` constantes (`CODE_EXPIRY_MINUTES`, cooldown, janela).

Nenhum valor de request, sessão, planilha ou e-mail é interpolado em SQL. Referência incorporada em
`Docs/SQL_Injection_Prevention_Cheat_Sheet.md`, regra no CLAUDE.md.

### Concorrência: como o app aguenta vários usuários

Produção é **um único processo** (waitress do `start-prod.bat`, default de 4 threads; `gunicorn-cfg.py`
fixa `workers = 1`). Dentro dele:

- **DuckDB de usuários = conexão singleton atrás de lock global.** `get_db_connection()` devolve um
  `_DuckDBHandle` que **segura `_duckdb_conn_lock` até o `close()`**. Auditado: os **20** callers têm
  `conn = get_db_connection()` seguido imediatamente de `try/finally: conn.close()`. Um `finally`
  faltando trava a aplicação para **todos** — não é um erro localizado.
- **Nada lento sob esse lock** (conferido por AST): sem SMTP, HTTP, varredura de share ou render de
  template com a conexão na mão. `_push_notify` é o modelo: lê os inscritos, fecha, e só então manda os
  pushes. O topbar consulta notificações a cada 8 s por aba, então esse lock é pedido o tempo todo.
- **Corrigido**: `_pc_ensure_db` fechava fora de `finally` — erro no `CREATE TABLE` vazava a conexão e o
  DuckDB ficava **travado até o processo morrer**, derrubando a página de Pending Confirmation para todos.

### Lost update nos caches JSON (corrigido)

`_atomic_write_json` garante que o arquivo nunca fica pela metade; **não** garante que a alteração de
outro usuário sobreviva. Os ciclos ler → alterar → gravar precisam de `_cache_lock` inteiro. New Deals já
estava correto (39 pontos); faltavam 12:

- **`_cache_lock` virou `RLock`.** Era `Lock`: helper que trancasse por conta própria, chamado de um bloco
  que já trancava, seria **deadlock** — e é exatamente o caso de `_conf_state_save` (os 4 callers trancam).
- **MtM Swap**: os 5 endpoints de linha, o normalize-zeros do `api_mtm_data` e o mapping-add passaram a
  envolver load → alterar → gravar.
- **Os três pesados** (`process`, `validation`, `recon`) **não** podem ter o lock em volta da leitura de
  planilha nem da escrita no share — travaria todo mundo por segundos. Neles o lock cobre um **reload
  dentro do bloco** + alteração + gravação, então o objeto lido antes da parte lenta nunca é regravado
  em cima do trabalho de outro.
- `_opb3_msg_save_recipients` (payload traz só um card), semente do `_mapping_rows` (com re-teste dentro
  do lock) e a gravação + invalidação de cache do `api_mappings`.
- ⚠️ **O que o lock não resolve**: dois usuários editando o **mesmo mapping** em abas separadas. O POST
  manda a tabela inteira, então quem salvar depois sobrescreve as linhas do outro. Resolver pede
  versionamento (mtime devolvido pelo front) — **não implementado**, está comentado no código.
- `api_mtm_import_folder` ficou como está de propósito: ele reconstrói o dataset do zero, não é
  read-modify-write.

Verificação: teste com **24 threads** comentando linhas diferentes do mesmo dataset MtM — 24/24
sobrevivem, zero deadlock. Para provar que o teste não é vazio, rodei o mesmo cenário com o lock
neutralizado: **22 das 24 alterações se perdem**.

### ⚠️ Manter em um processo

Com mais de um processo o lock do singleton e o `_cache_lock` **não protegem nada**: o DuckDB de usuários
não abre no segundo processo (lock de escrita), os JSONs voltam a ter lost update e **cada processo sobe
seus próprios schedulers** (pull duplicado da Athena). Escalar aqui é aumentando **threads**, não workers.
O teto de concorrência hoje é o do waitress (4 threads): endpoint lento — pull da API, varredura do share,
export — ocupa uma thread do início ao fim.

## 136. Sessão 2026-07-30 — Top menu: 8 atalhos por usuário

`MAX` em `visual-refresh.js` (`initTopNavCustom`) de 7 → 8, com o texto do hint atualizado nos três
idiomas (o número aparece escrito nas traduções, além de interpolado no default do JS). **Cache-buster do
`visual-refresh.js` bumpado** (`?v=20260730a`) — sem isso o navegador serve o JS antigo e o oitavo atalho
continua bloqueado. O overflow do nav já era tratado (abaixo de 1500px entra no fluxo com scroll
horizontal, §127), então o 8º item degrada igual aos outros.

**Correção seguinte (o painel continuava dizendo "max 7").** O JS interpolava o `MAX` certo, mas
`applyI18n()` sobrescreve o `innerHTML` do hint com o valor de `vr-cfg-hint` do JSON de tradução — e
`I18nManager` (`apps/static/js/app.js`) busca `/static/data/translations/<lang>.json` **sem cache-buster**,
então o navegador serve a tradução antiga indefinidamente. Bumpar o `?v=` do JS não resolve: quem manda no
texto é o JSON. Consertado tirando o número do JSON: as três traduções passaram a usar o placeholder
`{max}` e o painel roda `fixHintMax()` — `.replace(/\{max\}/g, MAX).replace(/\b\d+\b/, MAX)` — antes **e**
depois da tradução (`applyI18n()` agora devolve a promise justamente para isso). O segundo `replace` é o que
salva o usuário com JSON velho em cache: um número escrito à mão no arquivo é reescrito para o `MAX` real.
Regra geral: **número de limite nunca escrito na tradução**, sempre placeholder, senão o texto diverge do
comportamento até o cache expirar.

## 137. Sessão 2026-07-30 — Other Products › Latam Desk Position (página nova)

Página nova em **Daily Settlements › Other Products › Latam Desk Position**, no URL que já existia no
sidenav e no horizontal-nav (`/other-products-swap-latamdeskposition`) e que até agora dava 404 — o item de
menu e a chave de tradução `latam-desk-position` estavam lá desde antes. Modelada na página **OTM
Settlements**: JSON por dia, widgets, filtro por coluna, Columns/Export e CRUD maker/checker (add → `OK`,
edit → `Pending` com o maker, confirm por OUTRO usuário → `OK`, trava de quatro olhos igual à do OTM).

**Arquivo de origem:** `FbiRptLatamDeskPostion-NY-*` na pasta **Settlements** (`SETTLEMENTS_ROOT`, override
`LATAM_SOURCE_ROOT`). O nome do arquivo tem o typo **"Postion"** — o relatório é assim; a **página** é
"Position". O match é `startswith('fbirptlatamdeskpo')`, então cobre os dois.

**Filtro replicado da macro.** O VBA aplica `AutoFilter Field:=62, Criteria1:="<>"`, copia as visíveis,
limpa, aplica `Field:=63, Criteria1:="<>"` e ANEXA a partir de A2. Traduzido para: mantém a linha quando a
coluna **62 (BJ, `CLEARING_TRD_ID_IN…`)** OU a **63 (BK, `CLEARING_TRD_ID_CLN…`)** está preenchida.
Diferença deliberada: a linha que tem as **duas** colunas preenchidas entra **uma vez** — a macro a copiaria
duas vezes (uma em cada passada). O índice sai do header resolvido e cai na posição 62/63 da macro só se o
header dos dois `CLEARING_TRD_ID_*` não for reconhecido, então uma coluna inserida no relatório não quebra o
filtro.

**Datas.** O arquivo mistura layouts (`2030-01-16 00:00:00.0`, `20260108`) e usa o **epoch como "sem data"**
(`1969-12-31 19:00:00.0` = 0 em EST; `1970-01-01` em UTC). `_latam_date()` normaliza tudo para
**dd/mm/yyyy** e devolve `''` para as duas datas de epoch — na importação **e** na exibição (defensivo: JSON
antigo ou linha inserida à mão também saem limpos). Texto que não é data nenhuma (`N/A`) é preservado.
Colunas tratadas como data: `_LATAM_DATE_COLS` = Maturity_Date, Trade_Date, PREMIUM_SETT, LAST_PMT_DATE,
REBATE_SCHEDULE, BARRIER_SCHEDULE.

**Colunas (`_LATAM_COLUMNS`, 38).** Cada entrada é `(label, candidatos de header)`. Vários headers do
relatório só foram vistos **truncados** na planilha, então o segundo candidato é o texto cortado e vale como
**prefixo**: `'CLEARING_TRD_ID_IN'` acha `CLEARING_TRD_ID_INTERNAL`, `'Ty'` acha `Type`, `'Instrument_'` acha
`Instrument_ID`. `_latam_col_map()` resolve em duas passadas — header IGUAL primeiro, depois prefixo **do
candidato mais longo para o mais curto** — e cada coluna do arquivo é usada por um label só (é isso que
impede `Counterparty` de roubar a coluna de `Counterparty_Type`, e `id` de roubar `Deal_ID`). O que não
resolver sai vazio na página e aparece como `missing` na resposta do import + `log.warning`: **se alguma
coluna vier vazia depois do primeiro import real, o conserto é uma linha em `_LATAM_COLUMNS`**, não código.

**O relatório NÃO é diário.** A página abre no **último JSON disponível** (`_latam_latest_ref()`, que varre
a árvore `cache/daily settlement/YYYY/MM/DD/latam-desk-position_YYYYMMDD.json`), não no de hoje: o JS chama
`/data` **sem** `?date=` e o servidor devolve a última data que tem arquivo, com `latest: true`, e o picker é
sincronizado com ela. Escolher uma data no picker passa a pedir aquele dia exato; dia sem arquivo mostra
"Sem dados nesta data · Último disponível: dd/mm/yyyy" (o payload traz `dates`, as 60 datas mais recentes).
O sidecar `<json>.meta.json` guarda `{updated, file}` — a página mostra a hora do import e o **nome do
arquivo de origem**, que importa justamente porque a posição pode ser de outro dia.

**Card do Control Panel.** O spec `latam-desk` em `_DS_IMPORTS` já existia (filtro genérico
`nonempty_any [62,63]`) e passou a ter `'latam': True`, com um branch novo em `_ds_handle` que usa
`_latam_extract` — **card e página gravam exatamente o mesmo JSON** (testado registro por registro). A
descrição do card agora nomeia o arquivo (`FbiRptLatamDeskPostion-NY-*`) nos três idiomas. Diferença
proposital: o **card apaga** o arquivo de origem (mirror do `Kill` da macro, como os outros), o **import da
própria página não apaga** — o relatório não é diário e pode precisar ser reprocessado depois de ajustar um
label.

**Números não foram tocados.** `Strike` e `START_SPOT` aparecem no Excel como
`64.605.999.999.999.900.000` porque o Excel em pt-BR lê o `.` de `646.05999999999900000` como separador de
milhar — lendo o arquivo direto em Python o valor vem certo, e nenhuma formatação/arredondamento foi
aplicada (`FX Rate` continua `5.09849999999999`). Se a mesa quiser `#,##0.00` nessas colunas, é uma regra a
mais no `_latam_collect`.

**Widgets** (escolha desta sessão, o pedido não especificou): **Calls** (CALLPUT=C), **Puts** (CALLPUT=P),
**Counterparties** (distintas) e **Total** (linhas).

Arquivos: `apps/pages/routes.py` (bloco Latam Desk Position + spec/branch do card),
`apps/templates/pages/other-products-swap-latamdeskposition.html`,
`apps/static/js/pages/other-products-swap-latamdeskposition.js`, `control-panel.html`, traduções
(`ldp-*` + `cp-r-ds-desc`). O URL já estava no sidenav, então entra automaticamente no `/page-access`
(`_load_nav_urls` → 69 páginas controláveis).

**Correção no mesmo dia (página abria vazia e o calendário não abria).** Três coisas foram endurecidas
depois do primeiro uso real:

1. **Campo de data = HOJE, síncrono.** O campo agora recebe a data de hoje na primeira linha do
   `wireDatePicker()`, **antes** de qualquer plugin — se o calendário não carregar, o usuário vê a data em
   vez do placeholder `dd/mm/yyyy`. Os **dados continuam vindo do último arquivo disponível** (`load(null)`),
   e a data real da posição aparece ao lado, em "Dados de dd/mm/yyyy · Atualizado hh:mm · arquivo".
2. **Calendário com fallback.** Primário agora é o **flatpickr**, que vem no `vendors.min.js` (JS *e* CSS) de
   todas as páginas — não depende dos plugins carregados pela própria página, como o daterangepicker. A
   cadeia é flatpickr → daterangepicker → campo digitável, e tanto o ícone quanto o campo chamam
   `openPicker()`.
3. **Boot blindado.** Cada `wire*()` roda dentro do seu próprio `try/catch` e o boot só usa
   `DOMContentLoaded` se `document.readyState === 'loading'` (senão chama direto). Antes, um único erro —
   por exemplo `wireActions()` com o jQuery ausente — derrubava tudo o que vinha depois: calendário e
   `load()`. É exatamente o conjunto de sintomas que apareceu (campo vazio, tabela sem cabeçalho, sem os
   botões Columns/Export, que só existem depois do `buildTable`). O `catch` do `load()` também parou de ser
   mudo: erro vai para o console e para a faixa ao lado do botão de import.

**Armadilha do flatpickr (campo nascia vazio mesmo com a correção acima).** `defaultDate`/`setDate` do
flatpickr, quando recebem uma **string**, parseiam com o `dateFormat` configurado — aqui `d/m/Y`. Só
`Date`, timestamp ou string terminando em `Z`/`GMT` escapam disso (dá para ver no `vendors.min.js`:
`/Z$/.test(c)||/GMT$/.test(c)`). Passando o ISO `'2026-07-30'`, ele tenta ler `20` como dia, falha e
**LIMPA o input** — inclusive por cima do valor que o nosso código tinha acabado de escrever. Por isso a
página abria com o placeholder `dd/mm/yyyy` enquanto a OTM (que usa daterangepicker com
`moment(today,'YYYY-MM-DD')`, formato explícito) abria certa. Corrigido com `isoToDate()` devolvendo um
`Date` de verdade, mais um `if (!inp.value) inp.value = toDMY(today)` depois de criar o calendário. O
harness de front tinha um ponto cego aqui: o stub do flatpickr não mexia no input. Agora ele imita o real
(escreve quando recebe `Date`, limpa quando não consegue parsear) e o teste **falha** contra o código
anterior — verificado.

**`Could not load the data (HTTP 404)`.** 404 na rota da API significa que o `routes.py` **em memória** não
tem o endpoint. Como o Flask do time roda com o reloader desligado, o cenário típico é "deu pull e não
reiniciou": o Jinja recarrega o template sozinho, o `/static` serve o JS novo do disco, mas as rotas
continuam as antigas — e a página ainda pode aparecer vinda do cache do browser. A mensagem de erro agora
diz isso explicitamente em vez de só mostrar o código HTTP.

**O arquivo real é `.xls` — e "`.xls`" aqui é só o nome.** O relatório chega como
`FbiRptLatamDeskPostion-NY-2026-07-29.xls` (~23 MB). O leitor anterior só sabia PK (xlsx) e texto: um
`.xls` binário caía no ramo de texto, era decodificado como latin-1, o header saía com **uma coluna**, as
colunas 62/63 ficavam vazias e o filtro descartava **todas** as linhas — a página vazia sem erro. A macro
nunca precisou disso porque o `Workbooks.Open` do Excel fareja o conteúdo sozinho. `_latam_read_rows()`
agora fareja também, pela **assinatura do conteúdo** e não pela extensão, e devolve `(linhas, formato)`:

- `PK` → **xlsx** (openpyxl, via `_ds_read_rows`);
- `D0 CF 11 E0 A1 B1 1A E1` → **xls** binário/OLE2 (`xlrd`, import tardio como o reportlab; sem a lib o
  erro diz o que instalar em vez de ler bytes como texto). Datas viram ISO pelo `xldate_as_tuple` e número
  inteiro perde o `.0` (SPN `281808.0` → `281808`);
- começa com `<` e tem `<table>` → **tabela HTML** salva com nome de planilha (parser de `<tr>/<td>` com
  `html.parser`, sem dependência nova);
- resto → **texto** delimitado, com o sniff de TAB → `;` → `,` → `|`.

`xlrd>=2.0.1` entrou no `requirements.txt` (xlrd 2.x lê **só** `.xls`, que é exatamente o caso) — **precisa
de `pip install -r requirements.txt` na instância**. O formato detectado volta na resposta do import e
aparece no alerta, então "0 linhas" passa a dizer *como* o arquivo foi lido.

**O arquivo agora é consumido.** O import da página passou a apagar o arquivo de origem, como a macro fazia
— mas **só quando alguma linha entrou**: apagar um arquivo que não foi lido (formato inesperado, header
diferente) destruiria a única cópia antes de dar para investigar. A resposta traz `deleted`, e o alerta diz
"arquivo de origem apagado".

**Sniff de delimitador (primeira versão, hoje parte do leitor acima).** `_latam_read_rows()` substitui o `_ds_read_rows` nos dois caminhos
(página e card): se o header partido por TAB der **uma coluna só**, testa `;`, `,` e `|`. Sem isso, um
arquivo com outro separador "carrega" como uma coluna gigante, as colunas 62/63 ficam vazias, o filtro
descarta **todas** as linhas e a página fica vazia sem erro nenhum. A resposta do import agora traz
`read`, `filtered`, `header_cols` e `missing`, e o alerta mostra os quatro — `header_cols = 1` diz na hora
que o problema é o delimitador, não o filtro.

**Nota de limpeza nas traduções:** `en.json`/`br.json`/`es.json` tinham `nd-col-other-book` e
`col-other-book` **duplicados** (dois blocos, valores `OtherBook` e `Other Book`). A reescrita dos arquivos
deduplicou mantendo o valor que já ganhava no browser (`JSON.parse` fica com a última ocorrência), então o
comportamento não mudou.

## 138. Sessão 2026-07-30 — Exportações: checkbox/Actions, entidades HTML e #NULL!

Três defeitos distintos na extração da **Pending Confirmation** (valem para Copy/CSV/Excel/Print/PDF).

**1. Checkbox e Actions saíam na planilha.** O `exportOptions` já dizia `columns: ':gt(1)'`, mas esse
seletor é **posicional do jQuery** e o `thead` da tabela tem **DUAS linhas** (títulos + linha de filtros):
o jQuery enumera 2×N elementos `<th>`, e os `<th>` das colunas 0 e 1 da **segunda** linha caem em posição
> 1 — voltando para a seleção. Resultado: coluna A com o `value="option"` do checkbox e coluna B com
Actions. Trocado por uma função, que recebe o índice da **coluna** e não do nó:
`function exportFromStatus(idx) { return idx > 1; }`. Seletor por função é API documentada e já usada no
repo (`dt.rows(function (idx, data, node) …)` em `ndf-summary.html`).
**O mesmo `':gt(1)'` estava em mais 9 páginas** (OTM, Cognos, NDF Cockpit, Operations B3, Live Position
NDF/Option/Swap Characteristics, NDF Other Publisher, Latam Desk Position) — 27 botões, todos corrigidos
com um `exportFromData(idx)` local.

**2. `&gt;=`, `&lt;` e `H&amp;M` na planilha.** `formatExportData` tem dois caminhos: com nó do DOM usa
`$(node).text()` (decodifica), sem nó usa o dado do modelo. Como o export roda com
`modifier: {page:'all'}`, **só as linhas da página atual têm nó** — as demais caíam no fallback, que
removia as tags mas **não decodificava as entidades**. Por isso as primeiras ~200 linhas saíam certas e o
resto saía com `&gt;= 30 e &lt; 60 dias de pendência`. O fallback agora remove as tags **e** decodifica via
`decodeHtmlEntities()` (textarea + innerHTML, o parser do próprio browser; as tags saem antes, então nada
de HTML chega ao `innerHTML`).

**3. `#NULL!` em algumas células — não era a exportação.** Lendo o `buttons.html5.min.js`: uma célula só
vira número/erro quando o texto casa com um dos type-matchers (`/^\-?\d+$/`, moeda, `%`, data ISO);
qualquer outra coisa vira `inlineStr`, ou seja, **texto**. Logo o `#NULL!` estava no **dado**. Origem:
`_pc_import_update` lê a planilha "Pending Update" com `openpyxl(data_only=True)`, que devolve o **valor em
cache** da fórmula — e, quando a fórmula está com erro, esse valor é o texto `'#NULL!'`. Ele era gravado no
banco, aparecia na tela e saía na extração. Agora o `cell()` do import trata os literais de erro do Excel
(`_XL_ERROR_TEXT`: `#NULL!`, `#N/A`, `#REF!`, `#VALUE!`, `#DIV/0!`, `#NAME?`, `#NUM!`, `#SPILL!`, `#CALC!`,
`#GETTING_DATA`) como vazio. **Mudança de comportamento:** a linha cujo *Deal Name* é um erro de fórmula
passa a ser **pulada** (entra na contagem `skipped`), pela regra que já existia para Deal Name vazio — e
isso é melhor do que antes, porque `#NULL!` como Trade Number é a **chave** da linha: todas as linhas
quebradas colidiam entre si no `_pc_upsert_row` (delete por Trade Number + insert). Erro de fórmula em
coluna que não é chave vira vazio e a linha entra normalmente.

Testes: as três funções de export foram **executadas de verdade** (recortadas do template) contra os
valores que apareceram na planilha do usuário — 16 asserções, incluindo `&gt;=`/`&lt;`/`&amp;`/`&quot;`,
badge com tag+entidade, colunas 0/1 fora e 20 de 22 dentro; e o import foi rodado com um .xlsx real
contendo `#NULL!`, `#REF!` e `#N/A`, conferindo `updated`, `skipped` e que nada com `#` chega ao banco.

## 139. Sessão 2026-07-30 — Confirmações de FX Options: Vanilla e Asian (`ae8b816`)

A página **FX Options** era a última do grupo Confirmations do Monitor que só sabia **contar** a
segregação: não tinha botão Confirmation, documento, save nem ciclo. Agora tem o caminho completo, igual
ao NDF Commodities (§122) e ao Commodities Options: botão na página → grupos da data → página de geração
pré-preenchida com painel de edição → save com **Word + PDF + XML** no Electronic Inventory (pasta
**`FX Options`**) → New → Generated → Success com o checklist de validação (`validate.html`, `api_base`
`/api/confirmation/opt-fxo`).

### Os dois documentos foram portados NO LUGAR — e isso foi provado

Regra do usuário, literal: **"não misture templates nem altere nada, tem que manter 100% do texto
original"**. Cada `.doc` exportado do Word virou template Jinja por um script de porte que **só** faz três
coisas: troca valor por `{{ }}`, transforma a linha do Anexo I num `{% for r in conf.rows %}` e anexa o
painel de edição + CSS + JS. O script **aborta se qualquer âncora não for encontrada exatamente uma vez** —
nada de "quase casou".

- `option-fx-vanilla-strike-me.html` — **12 colunas** no Anexo I, já vinha com os marcadores `<<...>>`.
- `option-fx-asian-strike-me.html` — **16 colunas** (⚠️ o usuário trocou o arquivo no meio da sessão; o
  plano anterior assumia 14). As duas colunas a mais são **Taxa de Conversão** e **Tipo de Taxa de
  Conversão**, entre *Data de Pagamento do Prêmio* e *Preço de Exercício*. Este veio **preenchido com uma
  operação real** (deal `D5XO-S7U6K`, TAM, 14/07/2026, 4 linhas de exemplo), então o porte teve de
  remover os literais do exemplo e colapsar as 4 linhas num único `{% for %}`.

**A prova de fidelidade:** um teste renderiza cada template com exatamente os valores que estavam no
arquivo original e compara **palavra a palavra** (lista de palavras com as tags substituídas por `''` —
comparar linha a linha dá ~46 falsos positivos, que são só re-segmentação de `<span>`). Resultado
**4.449/4.449 (Vanilla)** e **3.963/3.963 (Asian)**, com dois deltas documentados e aceitos: `<<ITEM>>`→`1`
e `S.A.`→`S.A` (a assinatura passou a espelhar o campo Parte B do §2b). Refaça esse teste se um dia
mexer nos templates.

**Única alteração que não é troca de valor:** o `<meta charset>` dos dois exports dizia `windows-1252` mas
o arquivo está gravado em UTF-8 — na tela não dava problema (o header HTTP manda), mas o `.doc` salvo
abriria no Word com os acentos quebrados. Corrigido para `utf-8`.

### ⚠️ O PDF sai do próprio documento, não de uma segunda transcrição

Nas confirmações anteriores o texto legal existe **duas vezes**: o template Jinja e a réplica reportlab em
`confirmation_pdfs.py`, que precisam ser mantidas em sincronia à mão. Isso brigaria com o "manter 100% do
original", então aqui **`opcao_fx_pdf(conf, variant, doc_html)` recebe o HTML já renderizado** (o mesmo que
vira o `.doc`) e o converte para flowables. As duas saídas **não têm como divergir**.

- `_WordHtmlToFlowables(HTMLParser)` (`confirmation_pdfs.py:1140`) transpõe parágrafos, ênfases (`b/i/u/
  sub/sup`), tabelas com grade, `<hr>`/borda do Word e as quebras de página (`<br style="page-break-before">`
  → `PageBreak`). Títulos `h1..h6` caem no estilo `doctitle` (Times-Bold 12 centralizado) — o título do
  documento é um `<h2>` no export, e sem isso saía alinhado à esquerda e sem negrito.
- **Duas armadilhas resolvidas, não repita:** (1) o Word abre `<i>` **antes** do `<p>` e fecha **depois**,
  o que faz o reportlab estourar `Parse error: saw </para> instead of expected </i>` — por isso existe a
  pilha `self.open`, que fecha as ênfases no fim do bloco e reabre no bloco seguinte; (2) com 16 colunas a
  7,5pt os nomes de deal quebravam no meio (`D5XO-S7U6K` sumia do texto extraído) — tabelas de grade com
  `ncol > 12` usam fonte adaptativa `max(5.5, 7.5 * 12 / ncol)`, o que obrigou a guardar as células como
  string crua durante o parse e só virar `Paragraph` no `_table()`, onde `ncol` é conhecido.
- Verificado com `pypdf`: **todas** as palavras do documento chegam ao PDF, na ordem, nas duas variantes.
  (`pypdf` foi instalado só para o teste e **desinstalado depois** — não está no `requirements.txt`.)

### As quatro regras do produto que a lógica respeita

Estão comentadas no cabeçalho do bloco (`routes.py:21057`), mas repetindo porque é o que diferencia FXO
dos outros produtos de confirmação:

1. **A família é o `TradeType`** (`VANILLA` / `ASIAN`), **não** a moeda do strike — são dois documentos
   diferentes, não duas variantes do mesmo. Sem First/Last Fixing o import já classifica como VANILLA, e o
   default do `_conf_fxo_family` cobre o deal digitado à mão sem o campo.
2. **A "mercadoria" da segregação é a Moeda Base** (`UnderlyingAsset`) — opção de câmbio não tem
   mercadoria. Segregação = contraparte × moeda base × família, pontas internas fora, só status Success.
3. **Data de Exercício:** no Vanilla é a **Last Fixing Date**; no Asian é **"Não Aplicável"** e quem aparece
   é o par First/Last Fixing nas Datas Inicial e Final de Verificação (cláusula 4.2.c: na asiática a data de
   exercício *é* a data final, por definição).
4. **Preço de Exercício com no mínimo 4 casas decimais**, mais quando a taxa tem. Pedido literal: *"os
   strikes escreva sempre com no mínimo 4 casas decimais, se tiver mais coloque mais, se tiver menos
   complete com 0"*. O cache grava sempre 6 casas (`'{:.6f}'`), então `_conf_fxo_strike` **derruba o zero
   que não significa nada antes de aplicar o piso** — senão todo strike sairia com 6.

Demais campos: Tipo da Opção ← `Instrument` (Call→Compra, Put→Venda) · Comprador ← `Direction` (Sell →
Parte B) · Valor Base ← `TotalNotional` · Prêmio ← `Premium` em R$ · Data de Pagamento do Prêmio ←
`SpotDate` · Data de Vencimento ← `SettlementDate`.

### XML do contrato

`_conf_ndf_xml` ganhou dois parâmetros em vez de uma cópia: `ccy_field` (default `StrikeCurrency`, aqui
**`UnderlyingAsset`**) e `warn_no_spot` (aqui **False** — opção de câmbio não traz Spot FXRate, então o
aviso do NDF só faria barulho). Sai com `tipoOperacao Option`, `numeroContrato` com prefixo **`Opt_FXO`**,
`moedaEstrangeira` pelo código de cadastro da Currency Base (USD → 220).

⚠️ **Ponto em aberto, decidido pela regra do usuário** (*"para o valor em moeda estrangeira é o
totalnotional × strike"*): como o strike já é BRL por USD, `valor` e `valorEstrangeiro` saem com o **mesmo
número** — no teste, `101400000.00` — ou seja, a perna "estrangeira" carrega um número em reais. Se o
FepWeb esperar a perna estrangeira em dólar, o certo é `valorEstrangeiro = TotalNotional` puro. Está do
jeito que foi pedido; confirmar com a mesa antes de mudar.

### Taxa de Conversão é cadastro, não constante — mapping `fxo-conv-rate`

As duas colunas novas do Asian **não** foram hardcoded: o Anexo II define **uma taxa por moeda** e há moeda
com mais de uma possível (ARS MAE × ARS WMCO), logo é de-para (§131). Nasce com **só a linha do
documento-modelo**: `USD → USD PTAX / Venda`. **Moeda sem cadastro vira aviso amarelo no painel** — nunca
sai em branco na confirmação silenciosamente. Cadastre as demais em **/mapping › FXO Conversion Rate**.

### Onde mexer

| arquivo | o quê |
|---|---|
| `apps/pages/routes.py:21057` | bloco inteiro da confirmação FXO (~411 linhas) |
| `apps/pages/confirmation_pdfs.py:1140` | `_WordHtmlToFlowables` + `opcao_fx_pdf` |
| `apps/templates/confirmations/option-fx-{vanilla,asian}-strike-me.html` | os dois documentos portados |
| `apps/templates/pages/new_deals-opt-fxo.html` | botão Confirmation (`dom` do DataTables + bloco do modal) |
| `apps/static/data/mappings/fxo-conv-rate.json` | seed do de-para |

O card **FX Options** do Monitor deixou de ser contagem e passou ao ciclo completo (`_conf_optfxo_groups` +
`_conf_state_load(ref, 'opt-fxo')`) — ver §123.

**Teste ponta a ponta** (`check_fxo_flow.py`, scratchpad — não versionado): day-file sintético com 2 asian
+ 1 vanilla + 1 perna interna JPM, passando por segregação → páginas de geração → XML → trava do CGD.
Tudo verde. Vale recriar se mexer no fluxo. Atenção ao montar teste com `test_client`: o
`enforce_session_expiry` derruba sessão sem `session_expires_at` e **tudo volta 401**.

## 140. Sessão 2026-07-30 — Batch das APIs: re-booking de FWD Start e Amend só por dado econômico

Duas regras de negócio novas no pull automático da Athena. As duas são **invisíveis no código de quem
só lê o roteamento** — leia esta seção antes de mexer em `_ndf_api_pull` ou em `_nd_api_amend`.

### 1. O re-booking de um FWD Start que fixou não entra no NDF Vanilla

**O que a mesa faz:** no dia em que um FWD Start fixa (Strike Set Date), a operação é **cancelada** e
**re-bookada** com **outro Deal ID**, já como NDF vanilla. As duas pontas são a mesma operação — mas
como o Deal ID é novo, nenhuma chave (`Deal`+`Client`) as reconhece como par, e o re-booking entrava na
página de Vanilla como negócio novo.

**Como o par é reconhecido** (`_ndf_rebook_key`): **contraparte + notional + data de vencimento**, com a
**Trade Date do vanilla igual à Strike Set Date do FWD Start**. Strike e trade date **não** entram:
o strike é justamente o que a fixação define (o FWD Start nem chega a ter `Rate` gravado) e a data de
negociação do re-booking é outra por construção. A contraparte casa por SPN, com o accronym de reserva;
o notional entra em valor absoluto (a direção viaja no `Direction`, não no sinal).

**De onde saem os FWD Start comparados — duas fontes, unidas:**
1. **o próprio pull**: o registro do FWD Start que fixa na data de referência. Ele deixou de ser
   descartado com `(None, None)` e agora volta no alvo `_fwd-start-fixing` — não é gravado em página
   nenhuma (era esse o comportamento e continua sendo), mas o deal é montado para virar chave;
2. **o cache das páginas de FWD Start** dos últimos `_NDF_REBOOK_LOOKBACK_MONTHS` (24) meses, nas **duas
   grafias de pasta** de produção (`FwdStart` e `FWD Start`). Esta é a fonte que importa no dia a dia: o
   FWD Start foi bookado semanas ou meses antes e mora no arquivo do dia **dele**, não no de hoje.
   Cancelado entra na varredura de propósito — estar cancelado é justamente o sinal de que o re-booking
   aconteceu.

⚠️ **Direção do erro, de propósito:** chave incompleta (falta notional, vencimento, contraparte ou data)
**não casa com nada** e o deal **é importado**. Descartar de menos custa uma linha duplicada que o
operador apaga; descartar de mais some com uma operação sem ninguém ver. Todo descarte sai no
`log.info` com o Deal do vanilla, o Deal do FWD Start casado e os três valores que bateram, e vai no
retorno do pull em `skipped_fwd_rebook` / `skipped_fwd_rebook_deals`.

**Só o pull da API.** O import por XLSX não passa por aqui.

### 2. Deal já **Success** só cai para Amend quando muda informação econômica

`_nd_api_amend` é **compartilhado pelos quatro produtos que puxam da API** (NDF Vanilla, Other Publisher,
FWD Start e FXO) — a mudança vale para todos de uma vez.

Antes, qualquer diferença entre o deal guardado e a versão da API virava `Status = 'Amend'`. Uma operação
já **registrada** voltava para a fila por causa de um detalhe de booking, e alguém tinha de revisar de
novo à toa. Agora:

- **quem não está Success**: nada mudou — qualquer diferença vira Amend;
- **quem está Success**: só cai para Amend com mudança **econômica**. O valor novo é gravado e **a célula
  é destacada como sempre** (`AmendChanged`), mas o Success fica de pé.

**O que é cosmético** — lista curta de propósito, em `_ND_AMEND_COSMETIC`:
- **`OtherBook` e `TradingBook`** — os dois books são onde a operação está pendurada dentro do banco;
  contraparte, valor e prazo do negócio não mudam quando ela troca de book;
- **troca de accronym dentro da MESMA entidade** (JPM→JPM, MGT→MGT, LAWTON→LAWTON).

Todo o resto é econômico **por default** — vencimento, notional, strike/`Rate`, `Direction` (compra ×
venda), `Instrument` (put × call), `Premium`, `SpotDate` (pagamento do prêmio) e qualquer campo que
ninguém previu. É a direção segura: um campo esquecido aparecendo como Amend custa uma revisão; o
contrário custa uma operação registrada errada.

**Como a "mesma entidade" é decidida** (`_nd_amend_same_entity`), em duas fontes:
1. **a coluna `LE` do deal** quando o produto tem uma (os três NDFs) — ela já é derivada do accronym e da
   settlement location, ou seja, *é* a entidade;
2. **o accronym**, quando não há coluna LE (é o caso do **FXO**): LE cadastrada no mapping `le-accronym`
   e, se o código não estiver cadastrado, o **sufixo depois do último hífen** (`CMBB-LAW` → `LAW`) — o
   mesmo corte de `_ndf_accronym_variants`. Entidade desconhecida **nunca empata**: dois códigos que
   ninguém sabe de onde vêm podem ser de entidades diferentes.

⚠️ **A armadilha que quase entrou:** o loop de comparação **grava** cada campo em `stored` conforme
percorre. Perguntar a `stored` "a LE mudou?" no meio do caminho responderia sempre que **não**, porque a
LE já teria sido sobrescrita se viesse antes do `Acronym` na iteração. Por isso existe o
`before = dict(stored)` — a decisão é sempre contra a foto do deal **antes** de qualquer escrita.

**Contraparte propriamente dita não chega aqui:** `SPN`, `Client` e `TaxID` estão em `_ND_AMEND_SKIP`
(vêm do RefData e o re-enriquecimento os mexe sem a operação ter mudado), e `Client` ainda é **parte da
chave** de persistência — um cliente diferente é um deal novo, não um amend.

**Testes** (scratchpad, não versionados): `check_amend_rebook.py` cobre as duas regras no nível das
funções (8 casos de amend em NDF + 5 em FXO, e 10 casos de emparelhamento incluindo os que **não** podem
casar); `check_ndf_pull.py` roda o `_ndf_api_pull` inteiro com um payload falso da Athena e confere o que
foi gravado em cada arquivo do dia.

## 141. Sessão 2026-07-30 — Deals Monitor: aviso diário de pendências por e-mail (19h00 e 19h30)

E-mail automático para **brazil.otc.ops@jpmorgan.com** com o que ainda não fechou no Monitor.
Assunto fixo **`Pending Action - Deals Monitor`**, corpo em **inglês**, cabeçalho com o degradê azul e o
logo dos demais templates (`partials/email-gradient-header.html`).

### O que entra na lista

Um card entra quando **tem operação** (`total > 0`) **e** ainda **não está 100% Success**; a quantidade é
`total − Success`. Cada linha traz **Type · Product · Detail · Pending**, com os chips do card abaixo do
detalhe (`2 New, 1 Amend`) — assim o e-mail diz de *que* ação a pendência é, não só quantas são. Subtotal
por tipo e total geral no fim.

- **Type** = a zona da tela: **Registration** (B3), **Confirmation** e **Intrag**.
- **Product / Detail** saem de `_NDM_TAXONOMY` (NDF × Commodities/Vanilla/FWD Start/Other Publisher,
  Option × Commodities/FX/Equity, Swap × …). Card fora do catálogo (os "Others", que nascem sozinhos
  quando aparece um diretório novo no cache) cai no label do próprio card — **nunca some do e-mail por
  falta de cadastro**.

⚠️ **As contagens saem de `_ndm_monitor_snapshot`, o MESMO código que alimenta a página.** Ele foi
extraído do endpoint `/api/new-deals/monitor` justamente para isso. Uma segunda contagem própria do
e-mail divergiria da tela no primeiro ajuste de regra, e a mesa passaria a não confiar em nenhuma das
duas.

### Três detalhes que o teste pegou

1. **`Success` é comparado SEM caixa.** O cache do Intrag grava o status em minúsculo (`'success'`), e o
   Monitor conta a string crua — contar só a grafia `'Success'` deixaria **todo card de Intrag
   eternamente pendente**. Falso alarme diário é o jeito mais rápido de a mesa parar de ler o e-mail.
2. **Registro em Success com confirmação não gerada AINDA é pendência** — e está certo assim. O card de
   Confirmation tem ciclo próprio (New → Generated → Success), então o deal pode estar registrado e a
   confirmação continuar em aberto. As duas linhas aparecem separadas, uma em cada Type.
3. **Nada pendente → nenhum e-mail.** `_send_ndm_pending_email` devolve `'empty'` e não envia. Um e-mail
   intitulado "Pending Action" com a lista vazia é ruído, e resolve sozinho o fim de semana (sem
   operação, sem aviso).

### Agendamento

`_NDM_PENDING_TIMES` (env `DEALS_MONITOR_PENDING_TIMES`, default `19:00,19:30`) — o segundo disparo é
lembrete, com a lista já atualizada. Horário inválido na env cai no default em vez de matar o aviso.

⚠️ **Trava de disparo EM DISCO** (`deals_monitor_pending_sent.json`, em `control-panel/`): com o reloader
do Werkzeug ligado o módulo é importado em **dois processos**, cada um com o seu scheduler. Persistência
de deal é idempotente e sobrevive a isso — **e-mail não**. `_ndm_pending_claim_slot('YYYY-MM-DD 19:00')`
reserva o disparo antes de enviar; o segundo processo lê o arquivo e desiste. Guarda só os últimos 16.

### Destinatários e envio manual — card no Control Panel

Card **`dealsmonitor`** ("Deals Monitor — Pending Action"), no grupo **Reporting**, com TO / CC salvos no
blur e botão **Run**. É por ele que se troca o destinatário — nada de editar código.

- `GET/POST /api/control-panel/deals-monitor/recipients` grava
  `deals_monitor_pending_recipients.json` (em `control-panel/`, **não versionado**).
- **Sem nada salvo vale o default `brazil.otc.ops@jpmorgan.com`**, e **limpar os dois campos volta ao
  default** em vez de desligar a rotina: um card em branco não pode significar "aviso desligado" sem
  ninguém perceber. Para trocar o destinatário, escreva o novo — não apague.
- `POST /api/control-panel/deals-monitor/run` dispara na hora (aceita `date`), útil para não esperar as
  19h. Devolve "Nothing pending" quando não há o que avisar.
- Registrado em `_CONTROL_PANEL_CARDS` + `_CP_ENDPOINT_CARD` (gate por card do before_request) e no
  `CP_GROUP` do template — **os três**: sem o `CP_GROUP` o cabeçalho da seção some quando o usuário só
  tem esse card.

**Teste**: `check_monitor_email.py` (scratchpad) monta um dia sintético no cache, confere o que a regra
considera pendente (incluindo os três detalhes acima) e renderiza o template de verdade — sem SMTP.
`check_slot.py` cobre a trava de disparo duplo. `check_cp_card.py` cobre o card: registro, GET/POST dos
destinatários, o Run e o gate por card.

## 142. Sessão 2026-07-30 — Ctrl+C das tabelas não copiava nada (secure context)

**Sintoma:** selecionar célula em qualquer tabela (New Deals, Pending Confirmation, Mapping…) e apertar
Ctrl+C não copiava nada. Sem erro na tela, sem aviso.

### Causa-raiz

`navigator.clipboard` **só existe em secure context**: `https`, ou `http` em `localhost`/`127.0.0.1`. A
aplicação é servida em **`http://<IP-da-maquina>:8050`** (`start-prod.bat`) — que **não é** secure
context. Ali o objeto é `undefined`, e `navigator.clipboard.writeText(...)` estoura um `TypeError`
**antes de existir promise**, então nem o `.catch()` do próprio código rodava. Falha 100% silenciosa.

⚠️ **Por isso passou despercebido:** na máquina de quem desenvolve o acesso é por `localhost`, que **é**
secure context. O recurso funciona no dev e falha para todo mundo na instância da equipe. Vale para
qualquer API web restrita a secure context (clipboard, geolocation, notificações, service worker) —
**teste pelo IP, não pelo localhost**.

O botão **Copy** dos exports do DataTables sempre funcionou: a lib usa `document.execCommand('copy')`, a
API legada, que não exige secure context. Era a única cópia que a mesa conseguia usar.

### Correção

**`apps/static/js/clipboard.js`** (novo, carregado em `partials/footer-scripts.html`, ou seja, em **toda**
página) expõe **`window.otcCopyText(texto)`**, que devolve sempre uma promise:

1. secure context com `navigator.clipboard` → API moderna;
2. senão → `<textarea>` fora da tela + `document.execCommand('copy')`;
3. API moderna que **rejeita** (aba sem foco, permissão negada) também cai no caminho 2.

Detalhes que o fallback exige: o textarea precisa estar **visível** (`position:fixed; left:-9999px`) —
com `display:none`/`visibility:hidden` o `execCommand` devolve `false`; e a seleção do usuário é salva e
restaurada, senão copiar apaga o que estava selecionado na página.

As 8 chamadas diretas a `navigator.clipboard.writeText` (6 páginas de New Deals, Pending Confirmation e o
Copy do Mapping) passaram a usar o helper. **Não crie chamada nova a `navigator.clipboard` — use
`otcCopyText`.**

### Ctrl+C genérico para as tabelas que não tinham

Só 7 páginas tinham handler de Ctrl+C. Index B3, Intrag (NDF/Option/Swap), MTM Swap, Accrual Swap e
Metrics têm seleção de célula e **nenhuma** cópia. O `clipboard.js` instala um handler genérico que
monta o texto a partir das células/linhas selecionadas de qualquer DataTable, agrupando **por linha**
(com `\t` entre colunas e `\n` entre linhas) para o conteúdo colar como retângulo no Excel.

Ele sai de cena em três casos: evento já tratado pela página (`defaultPrevented`), foco em
input/textarea/select/contenteditable, e texto selecionado na página (aí o Ctrl+C nativo faz melhor).

⚠️ **O listener fica em `window`, não em `document`** — e isso é essencial. O evento borbulha
`target → document → window`, então os handlers das páginas (registrados em `document` via jQuery) rodam
**antes**, e o `defaultPrevented` já chega decidido no genérico. Registrar em `document` criaria disputa
de ordem com as 7 páginas que já têm handler próprio.

**Teste**: `check_clipboard.js` (scratchpad) roda o arquivo no JavaScriptCore com um DOM de mentira
(não há node nesta máquina) e cobre os dois caminhos de cópia, a rejeição da API moderna, o textarea
fora da tela e as três condições de desistência do handler global.

---

## §143 — FXO marcava "Missing Counterparty" com o accronym cadastrado no mapping

**Sintoma** (30/07/2026): linhas de perna interna em New Deals FXO com o badge vermelho
"Missing Counterparty" nas colunas Accronym / Client / Tax ID, mesmo com `CMBB` e `CMBB-LAW`
cadastrados no mapping **Legal Entity × Accronym**. O NDF resolvia as mesmas contrapartes.

**Causa-raiz — enriquecimento por SPN, e só.** `_fxo_deal_from_row` procurava a contraparte
**exclusivamente pelo SPN** (`refmap.get(_norm_spn(spn))`, índice do Reference Data) e gravava
`'Acronym': ref.get('FX CASH ACCRONYM') or ''`. Na perna interna o SPN que a API manda é de
**book** (`5068198`) — nunca esteve nem estará no Reference Data —, então `ref` vinha `{}` e a
coluna Accronym ficava **vazia**.

O resgate existe no front (`missing-counterparty.js`): `isMissing()` consulta o mapping
le-accronym antes de marcar. Mas ele procura **o valor da célula Accronym** no mapping — e com a
célula vazia não há o que procurar. O cadastro estava certo; o código nunca chegava a consultá-lo.

O NDF não tinha o problema porque `_ndf_deal_from_api` já fazia as duas coisas:
enriquecia por accronym (`_ndf_ref_by_accronym`) e gravava `'Acronym': ... or end_cp`.

**Correção** (`_fxo_deal_from_row`, vale para o pull da API **e** para o import de XLSX, que
compartilham o builder):

1. SPN sem registro → tenta pelo **End Counterparty**, que é o accronym da contraparte
   (`_ndf_ref_by_accronym(refmap_acr, end_cp, _ndf_le_from_accronym(end_cp))`).
2. `'Acronym'` cai para `end_cp` quando o Reference Data não tem nada — a coluna deixa de mentir
   que não há informação, e o badge passa a ter o que consultar no mapping.
3. **Settlement Location não entra nessa resolução**: ela diz respeito à *nossa* perna, não à
   contraparte. Usá-la para achar a contraparte casaria a linha errada. (O NDF usa a location
   para derivar a coluna LE, que é outra coisa.)

`_fxo_refdata_by_accronym(refmap_spn=None)` passa a ser o único lugar que monta o índice
FX CASH ACCRONYM → registro; substituiu **três** cópias inline do mesmo laço.

**Armadilha resolvida junto — o backfill não pode devolver o deal para a fila.** Os deals já
gravados têm `Acronym: ''`; no primeiro pull depois do deploy o campo vira `CMBB`. Como `Acronym`
é campo comparado no amend (§140), *todo* deal interno que já estava Success voltaria a Amend de
uma vez. `_nd_amend_is_economic` ganhou a exceção: **accronym aparecendo onde a célula estava
vazia, com o SPN intacto, é enriquecimento nosso que melhorou, não troca de contraparte** — a
célula é destacada, o status não regride. SPN diferente junto = é outra contraparte, continua
Amend.

**Front alinhado**: `missing-counterparty.js` comparava o accronym como string exata enquanto o
backend compara achatado (`_ndf_flat`: só letras e números). Agora usa o mesmo achatamento, então
espaço/hífen/caixa a mais no cadastro não fazem o badge reaparecer. Cache-buster `?v=20260730b`
nas 6 páginas que carregam o arquivo.

**Testes** (scratchpad): `check_fxo_cp.py` monta o deal a partir do **record real** da API que o
usuário mandou e verifica a premissa (SPN ausente do RefData), o match no mapping, o Accronym
preenchido, o badge antes/depois e que a contraparte de cliente normal continua vindo do SPN.
`check_fxo_amend.py` cobre os cinco casos do amend: backfill fica Success, troca de entidade vira
Amend, JPM→JPM continua Success, Strike vira Amend, SPN+accronym juntos viram Amend.

**Depende de restart** (`routes.py`) na instância do time. Os deals já importados são corrigidos
sozinhos no próximo pull da API (horário no FXO) ou clicando Import.

---

## §144 — Prêmio D0 não gerava nada com a Spot Date de hoje em todas as linhas

**Sintoma** (30/07/2026): em New Deals FXO, com **Spot Date = hoje** em todas as operações, o botão
**Premium** respondia "Nothing to Generate — No operations with premium payment (Spot Date) due today".

**A Spot Date não era a culpada.** O filtro `_date_br(d['SpotDate']) == _today_br()` passava. O que
derrubava tudo vinha depois: `build_premium_emails` resolvia a contraparte **só pelo accronym**
(`ref = _build_refdata_index(ref_key)`, `rec = ref.get(acronym)`). A conta B3 sai desse registro, e o
e-mail só é gerado para o bucket `73760.10-2` — com `rec = {}` a conta vem vazia, nunca bate, e o deal
é descartado **em silêncio**.

E o accronym é **opcional** no Reference Data: há contraparte cadastrada com a coluna em branco. A
própria tela provava isso — Client e Tax ID preenchidos (achados pelo **SPN**) e a coluna Accronym
vazia na mesma linha.

**Segundo defeito, achado junto.** `_group_by_acronym_commodity` agrupava por `(Acronym, Commodities)`.
Com o accronym vazio, **contrapartes diferentes caíam no mesmo grupo** — um e-mail só, com os deals de
todo mundo, endereçado a quem calhasse de estar em primeiro. Nunca apareceu porque o grupo de accronym
vazio morria no filtro da conta B3 logo em seguida; consertar o primeiro defeito sem este teria
transformado um e-mail que não saía num e-mail errado que sai.

**Correção** (`otc_emails.py`):

- `_build_refdata_spn_index()` + `_ref_for_deal(by_acronym, by_spn, deal)`: resolve pelo accronym e,
  quando ele não resolve, **pelo SPN** — que é obrigatório e é a chave usada no resto do projeto.
- `_group_by_acronym_commodity` cai para `'SPN:<normalizado>'` na chave quando não há accronym.
- `build_premium_emails` e `build_economic_affirmation_emails` passam a usar `_ref_for_deal`; nome e
  Tax ID caem para os do próprio deal quando o Reference Data não tem.

**Efeito colateral corrigido de propósito na Econ. Affirmation**: a afirmação é para instituição
financeira, e exclui quem está em `EXCLUDED_B3_AFFIRMATION`. Com o accronym vazio a conta B3 vinha em
branco, não batia com nenhuma da lista de exclusão, e **um cliente passava por instituição financeira
e recebia uma afirmação que não é dele**. Resolvendo pelo SPN, ele volta a ser excluído.

**Testes**: `check_premium.py` (scratchpad) reproduz o caso da tela — mesmo deal, mesma Spot Date, com
e sem accronym —, isola o filtro de Spot Date para provar que não era ele, cobre o agrupamento de duas
contrapartes sem accronym e as regressões (Lawton fora, bucket errado fora, cliente sem afirmação de
IF, IF continua recebendo).

---

## §145 — Confirmation / Premium / Econ. Affirmation subiram para junto do "Show entries"

Os três botões viviam na barra de ferramentas da DataTable, dividindo espaço com Columns, Add Row,
Export, Reference Date, Import e Clear Filters — fila longa demais para achar o botão certo de
primeira. Passaram para o `card-header` do "Show N entries", à direita do seletor.

**Só o lugar no DOM mudou.** Os contêineres mantêm as classes `confirmationBtn` / `premiumBtn` /
`econAffBtn`, que é o que o JS de cada página procura (`document.querySelector('.premiumBtn')`) para
criar o botão dentro — nenhum handler foi tocado. Nos três `dom:` das DataTables os `<'...Btn me-2'>`
correspondentes saíram.

Páginas: `new_deals-opt-fxo` e `new_deals-opt-commodities` (os três botões) e `new_deals-ndf-commodities`
(Confirmation e Econ. Affirmation — não tem Premium). As demais páginas de New Deals (NDF Vanilla,
FWD Start, Other Publisher) **não têm nenhum dos três**, então não havia o que mover.

---

## §146 — Confirmação de FXO: Anexo I com 3 cabeçalhos e operações faltando

**Sintoma** (30/07/2026): na tela da confirmação de Opção de Câmbio, o Anexo I aparecia com **três
cabeçalhos empilhados** e só **2 das 3** operações; a assinatura ficava desalinhada; e o documento
corria de ponta a ponta do monitor ("esparramado").

**Duas causas somadas**, e é a soma que produz o sintoma exato.

**1. `</tbody>` dentro do laço** (`option-fx-vanilla-strike-me.html`, linha 3262):
`</tbody>{% endfor %}</table>`. Cada iteração fechava o `<tbody>`, então o parser do navegador punha a
1ª operação em `#ops-tbody` e jogava as demais em `<tbody>` implícitos criados por ele. No Asian era a
outra ponta do mesmo erro: `{% endfor %}</table>` sem `</tbody>` nenhum. Agora `{% endfor %}</tbody></table>`
nos dois.

**2. O molde de linha do editor era o CABEÇALHO** (`rowProto = tbody.rows[0]`). O cabeçalho mora dentro
do mesmo `<tbody>` — é assim que o Word exporta —, então `renderTable()` limpava o tbody e colava N
cópias dele. Como o cabeçalho não tem célula `[data-k]`, nada era preenchido.

Juntando: `renderTable()` substituía `#ops-tbody` (cabeçalho + operação 1) por 3 cabeçalhos, enquanto as
operações 2 e 3 — que estavam nos `<tbody>` implícitos — ficavam intocadas. **3 cabeçalhos + operações
2 e 3.** Exatamente o print. O molde passou a ser a primeira linha com `[data-k]`, e `renderTable()`
recoloca o cabeçalho antes das operações.

**Assinatura desalinhada.** As duas colunas são alinhadas no Word empilhando parágrafos VAZIOS, o que
só funciona enquanto o nome da contraparte couber em **uma linha** — "RAINBOW DEFENSIVOS AGRICOLAS
LTDA" quebra em duas e empurra o "Por:/Nome:" da esquerda para baixo. No PDF era pior: `_emit`
descarta parágrafo vazio (vira respiro, não linha), então a coluna da direita perdia todo o
espaçamento. Resolvido alinhando a célula pelo **rodapé** — `#sig-table > tbody > tr > td
{ vertical-align: bottom }` na tela e `VALIGN BOTTOM` nas tabelas sem borda do
`_WordHtmlToFlowables` (as duas são a de assinatura e a de testemunhas).

**"Esparramado".** O documento é export do Word em **paisagem** (`@page WordSection1`), e no navegador
não havia largura máxima: o parágrafo ocupava o monitor inteiro. Ganhou a mesma coluna centrada dos
documentos de Commodities (`max-width: 940px`), **só na tela** — `body:not(.doc-only)`. O `.doc` que a
contraparte recebe continua sendo o do Word, sem uma linha de diferença. As tabelas largas (Anexo I
tem 11 no Vanilla e 16 no Asian) rolam dentro do próprio bloco em vez de esticar a página de volta.

**Teste**: `check_conf_fxo_doc.py` (scratchpad) roda os dois templates nos dois modos (tela e
documento) e verifica: 1 cabeçalho + N operações dentro do `#ops-tbody`, cabeçalho como primeira linha
e única sem `[data-k]`, nenhuma operação fora do tbody, o molde do editor, a coluna de leitura só na
tela, o alinhamento da assinatura, e gera os dois PDFs de verdade.

---

## §147 — NDF trazendo a contraparte ERRADA (cliente virava o próprio Banco J.P. Morgan)

**Sintoma** (30/07/2026): uma operação de Other Publisher com `End Counterparty: "SOMICHEL"` e
`End Counterparty Description: "SOCIEDADE MICHELIN…"` chegou na tela como **SPN 23779 · GN NDF BJPM ·
BANCO J.P MORGAN S.A · 33.172.537/0001-98**.

**Causa-raiz — a Settlement Location decidindo quem é a contraparte.** Em `_ndf_deal_from_api`:

```python
le = _ndf_le_from_accronym(end_cp) or _ndf_le_from_location(loc) or loc
ref = _ndf_ref_by_accronym(refmap_acr, end_cp, le)     # <- le vinha da location
```

`SOMICHEL` não está cadastrado como accronym, então a LE caía para a da **Settlement Location**
(`BRAZIL` → `JPM`). E o último passo de `_ndf_ref_by_accronym` varre os accronyms daquela LE no
Reference Data: achou `GN NDF BJPM` e devolveu o **Banco J.P. Morgan**. Silenciosamente, numa operação
que segue para registro na B3 e para confirmação.

A Settlement Location é a **nossa** perna, não a da contraparte. Esse passo existe para perna interna
(End Counterparty que é nome de book JPM) e só pode ser alcançado quando o **próprio accronym da
contraparte** identifica uma entidade.

**Correção**:

- `le_cp = _ndf_le_from_accronym(end_cp)` — entidade **da contraparte**, `None` quando ela não é perna
  interna. A coluna LE da tela continua caindo para a Settlement Location; só a busca da contraparte
  deixou de usá-la.
- `_ndf_ref_by_accronym(..., le, refmap_spn=, spn=)` ganhou um passo intermediário: **o SPN que a
  própria API manda**. Ele identifica a contraparte sozinho, então vem antes do passo da LE, que é
  palpite. É por ele que a Michelin (cadastrada com accronym `MICHBRA`, diferente do `SOMICHEL` da
  API) é resolvida corretamente.
- Ordem final: accronym exato → accronym sem sufixo de entidade → **SPN da API** → accronyms da LE
  (só se a contraparte for perna interna).
- `_generic_nd_reenrich` tinha o mesmo defeito aplicado a quem já está no arquivo (caía para
  `deal['LE']`, que veio da location). Passa `le_map` apenas.

Nada casando, SPN/Client/TaxID ficam vazios e a página marca "Missing Counterparty" — que é o erro
certo: pede cadastro em vez de inventar contraparte.

**Teste**: `check_ndf_cp.py` (scratchpad) usa o record real da API e um Reference Data montado para o
cenário (Banco J.P. Morgan com `GN NDF BJPM`, Michelin com accronym diferente): a operação resolve
para a Michelin pelo SPN, contraparte desconhecida fica vazia em vez de virar JPMorgan, perna interna
continua resolvendo pela LE do próprio accronym, e o re-enriquecimento não reintroduz o erro.

**Depende de restart** e de novo pull. As operações já gravadas com a contraparte errada **não são
corrigidas sozinhas**: o `_generic_nd_reenrich` só mexe em deal com SPN vazio, e essas têm o SPN
(errado) do banco preenchido. Precisam ser conferidas à mão.

---

## §148 — O SPN da API não identifica a contraparte (traz o da LE)

Correção da §147: o passo "SPN da API" que eu tinha acabado de acrescentar **foi removido**.

O usuário confirmou (30/07/2026) que a API hoje devolve em `SPN` o SPN da **Legal Entity**, não o da
contraparte — é correção pendente no time responsável pela API. Usar esse campo como chave
reintroduziria exatamente o erro da §147 por outro caminho: a linha resolveria para a entidade JPM em
vez do cliente.

**Onde isso mudou**:

- `_ndf_ref_by_accronym` voltou à assinatura `(refmap_acr, acr, le=None)`. Ordem: accronym exato →
  accronym sem sufixo de entidade → accronyms da LE (só quando a contraparte é perna interna).
  Quando a API for corrigida, o SPN volta como passo **entre** o accronym e a LE — está anotado no
  docstring.
- `_fxo_deal_from_row` **inverteu a ordem**: agora procura primeiro pelo accronym da contraparte
  (End Counterparty) e só usa o SPN da API como último recurso, para não perder o que já resolvia por
  ele. Antes o SPN era a chave primária — o FXO enriquecia toda linha pelo campo que traz a LE.
- O `SPN` mostrado na tela do FXO passa a ser o do **Reference Data** quando a contraparte foi
  resolvida; o da API só aparece enquanto não há cadastro nenhum a que recorrer.

Sem cadastro, a linha fica vazia e a página marca "Missing Counterparty" — que é o comportamento
desejado: pedir cadastro em vez de inventar contraparte.

**Teste**: `check_ndf_cp.py` foi atualizado para a regra nova — a operação da Michelin fica vazia
enquanto o accronym não estiver no Reference Data, resolve certo assim que estiver, e em nenhum dos
casos vira o Banco J.P. Morgan.

---

## §149 — Confirmar um deal New na coluna Actions vai direto para Approved

Antes, o botão de confirmar (✓) levava `New` **e** `Amend` para `Pending`. O passo `Pending` existe
para quem **editou** submeter a alteração à revisão — e nesse caminho, clicando o ✓ direto na linha
sem abrir o modal, não houve edição nenhuma. Agora:

- **New → Approved** direto;
- **Amend → Pending**, sem mudança: ali a API alterou dado econômico e alguém tem de olhar.

Indo direto para Approved valem as **mesmas travas** do Pending → Approved, porque de Approved o deal
segue para Send/B3: contraparte não cadastrada (`_cp().rowMissing`) e ativo fora do Index B3
(`_isAssetMissing`) barram a aprovação com o mesmo aviso de sempre. A trava de *maker ≠ approver*
**não** se aplica aqui — é justamente o atalho que se está pedindo —, mas o aprovador vira o Maker,
então o **Send continua exigindo outro usuário**. A cadeia perdeu um par de olhos (o de New→Pending),
não os dois.

Vale nas 6 páginas de New Deals (NDF Vanilla / Commodities / FWD Start / Other Publisher, Opt
Commodities / FXO). A única diferença entre elas é o índice da coluna do ativo (13 no FXO, 14 nas
demais) — o mesmo que a trava do Pending já usava em cada página.

---

## §150 — NDF Other Publisher: Data de Fixing do Ativo Subjacente sempre em branco

Campo 19 do arquivo Conecta (`f[18]` no builder da página, `_pos(fix_single, 8)` no servidor). No
Other Publisher ele passa a sair **sempre com as 8 posições preenchidas com espaço**, em vez da data
do fixing único. Vale para o arquivo **e** para o preview — os dois saem do mesmo
`buildConectaFields`, e o servidor foi ajustado junto para o arquivo enviado não divergir da tela.

O **FWD Start não mudou**: `api_generic_nd_send_conecta` atende os dois produtos, então o branqueamento
é condicionado a `if not is_fwd`.

`tipo_media` ('A'/'N') **não** depende deste campo — sai de `asian_fix`, que olha a janela de fixing —,
então zerar a data não reclassifica a operação. `fixSingle` continua sendo calculado na página pelo
mesmo motivo.

---

## §151 — Agendamentos em horário de Brasília (o aviso das 19h não saiu)

O aviso de pendências do Deals Monitor não foi disparado em 30/07/2026. **Duas causas possíveis, as
duas tratadas:**

**1. Fuso.** Os agendamentos usavam `datetime.now()`, que é o horário **local do servidor** — e a
instância do time não roda necessariamente em BRT. Entraram `_BR_TZ` e `_br_now()` (`zoneinfo`
`America/Sao_Paulo`, com fallback para o offset fixo `-03:00` quando o `tzdata` não está instalado —
caso do Windows; o Brasil não tem horário de verão desde 2019, então o offset fixo não é aproximação).
Passaram a usar `_br_now()` o scheduler do aviso (19:00 / 19:30) **e** o da manutenção diária de
Pending Confirmation (11:30), que tinha o mesmo defeito silencioso.

**2. Restart depois do horário.** A instância roda com o reloader desligado, então todo pull pede
restart — e vários aconteceram neste dia. Subindo às 19h31, o loop calculava o próximo slot como
"amanhã 19:00" e o aviso do dia simplesmente não saía, **sem erro nenhum no log**.
`_ndm_pending_catch_up()` roda no start e dispara os slots de **hoje** que já passaram e que ninguém
reivindicou. O arquivo de claim (`deals_monitor_pending_sent.json`) é o que impede que isso vire
e-mail repetido a cada restart.

**Diagnóstico para a próxima vez.** O log do start agora imprime os horários **e** a hora do servidor
ao lado da hora de Brasília — se estiverem diferentes, o fuso da máquina está fora. E cada disparo
registra o resultado (`enviado` / `empty` / erro), o que antes não existia: quando o aviso não chegava,
não dava para distinguir "não foi enviado" de "não havia pendência", já que o aviso não é mandado
quando não há nada pendente (decisão da §141).

**Teste**: `check_tz_conecta.py` (scratchpad) confere o offset e o tipo de retorno de `_br_now()`,
recupera dois slots perdidos num start às 23h, garante que um segundo restart no mesmo dia **não**
repete o e-mail, que slot futuro não dispara, e cobre o campo de fixing da §150.

---

## §152 — Mapping do arquivo de retorno pegava só o que estava na tela

**Sintoma** (30/07/2026): o botão **Mapping B3** mapeava apenas parte das operações do dia.

**Causa-raiz.** A lista de deals era montada varrendo `table.rows({search:'none', page:'all'})` —
e, apesar do `search:'none'`, a **tabela pode ser o resultado de uma busca no servidor**
(`/cache/search`, as fichas de filtro da barra). Ou seja: `page:'all'` traz todas as linhas
*carregadas*, não todas as do dia. Filtrou antes de mapear → o que ficou de fora não foi mapeado, sem
aviso nenhum.

**Correção.** O cliente não monta mais a lista: manda só a **Reference Date** (`ref_date`, o campo
`#apiRefDate`), e o servidor monta a partir do **arquivo do dia** em
`_generic_nd_mapping_candidates()`. É o servidor que grava o B3 ID no cache, então operação que não
está na tela também é atualizada — a tela só não redesenha o que não está renderizado. O parâmetro
`deals` continua aceito para chamadas com lista explícita.

**Qualquer status no Vanilla.** No Vanilla o registro na B3 é feito por outra ferramenta, então o
mapping tem de olhar **todos** os status, e não só New/Sent/Error. As outras páginas mantêm o filtro
antigo (o `product != 'vanilla'` em `_generic_nd_mapping_candidates`). Ficam sempre de fora:

- `Canceled` — cancelado na API, fora do fluxo;
- `Success` **com B3 ID** — não há o que mapear, e uma segunda passada só poderia perder informação.

**A armadilha que isso criou, e a trava.** A regra antiga era "não achou no retorno → `Error`".
Varrendo o dia inteiro em qualquer status, isso derrubaria para `Error` operações que **nem foram
registradas ainda** (Approved/Pending) — e um `Success` sem B3 ID. Só vira `Error` quem estava num
status que espera retorno (`_ND_MAPPING_ERRORABLE = {New, Sent, Error}`); os demais ficam como estão,
e sem `updates` não há escrita no arquivo.

**Contagem.** Só entra em `results` quem **mudou** — senão o "N deal(s) mapped" da notificação e os
contadores da tela passariam a contar o dia inteiro.

**Vale para as três páginas do endpoint genérico** (Vanilla, Other Publisher, FWD Start). Opt FXO,
Opt Commodities e NDF Commodities têm endpoints próprios e **continuam montando a lista pela tabela** —
mesma limitação, ainda não corrigida.

**Teste**: `check_mapping_b3.py` (scratchpad) cria um dia com um deal por status e um arquivo de
retorno de verdade (com `TER` nas posições 57-59), e confere: quem entra na varredura, quem é
promovido a Success com B3 ID, que o `Pending` sem retorno não vira Error, que o `Success` e o
`Canceled` ficam intocados, e que a contagem só considera quem mudou.

---

## §153 — Badge da coluna Status sempre centralizado

O conteúdo da célula de Status é reescrito por vários caminhos (rowMaker, mapping B3, aprovação na
coluna Actions, edição em massa) e nem todos embrulhavam o `<span class="badge">` do mesmo jeito — a
coluna ficava com badge ora à esquerda, ora no meio, dependendo de quem escreveu por último.

Centralizar por **coluna** (`columnDefs` com `targets: [2]`, `className: 'text-center'`) independe de
quem escreveu a célula, e é por isso que a correção é ali e não em cada ponto de escrita. `targets: 2`
vale para as 6 páginas — `STATUS_COL_INDEX` é 2 em todas. Usar `columnDefs` em vez de CSS com
`nth-child` também é o que sobrevive a coluna escondida: o DataTables tira a coluna oculta do DOM e os
índices de `nth-child` andariam.

---

## §154 — Monitor: o verde do card concluído sumia no tema claro

O sombreado de progresso do New Deals Monitor (§129) ia do vermelho ao verde. No **dark** ficou como
esperado; no **claro**, o card 100% Success praticamente não mostrava o verde, enquanto o vermelho dos
pendentes se lia inteiro.

**Duas causas somadas.**

1. O card concluído usa opacidades **menores** de propósito (`.is-done`: .08/.14/.09 contra .12/.22/.14
   do card em andamento) — "resolvido não precisa gritar". No escuro isso funciona; no claro apagava o
   halo.
2. O verde do gradiente é `#1a8a4a`, escuro demais para virar halo sobre fundo branco. O vermelho
   `#dc3545` sobrevive à mesma redução; o verde não.

**Correção, só no tema claro** (a regra `[data-bs-theme=dark] … .ndm-card--prog` vem depois e tem a
mesma especificidade, então continua vencendo no escuro — o dark ficou byte a byte como estava; o
hover do concluído no escuro precisou de uma regra própria porque o `:hover` tem especificidade maior
e passava por cima):

- opacidades do `.is-done` sobem para .14/.28/.18 (borda .34), o peso do card em andamento;
- a cor vira **literal `#16a34a`** em vez de `var(--ndm-prog)`.

**Por que literal.** O JS escreve `--ndm-prog` no atributo `style` do card
(`style="--ndm-prog: r, g, b"`), e **declaração inline vence qualquer seletor** — redefinir a variável
no CSS não teria efeito nenhum. Como `.is-done` é por definição 100% Success, a cor é conhecida, e
escrevê-la direto é mais simples do que disputar a cascata. Os cards em andamento continuam com a cor
interpolada pelo JS.

---

## §155 — Guia do Usuário em Word e recaptura das 46 telas

**O que foi entregue** (commit `7694bc9`): `GUIA_DO_USUARIO_OTC_TRACKER.md` (fonte única) e o
`.docx` gerado a partir dele, para circular na área. Cobre visão geral, primeiros passos (login por
SID + 2FA), o passo a passo por página e três perguntas frequentes.

**As 46 telas foram recapturadas.** As anteriores eram de 20/07 e o layout mudou muito desde então.
Entraram 14 telas que ainda não existiam: Monitor, Mapping, NDF Vanilla, Electronic Inventory,
Metrics, Live Position Cashflow/Premium, Intrag Swap e os módulos de Swap.

**Duas armadilhas da captura — anote antes de recapturar de novo.**

1. **As telas de New Deals saem VAZIAS.** O `DATA_EPS` do `capture_screens.py` não cobre os endpoints
   dessas páginas (elas carregam por `POST /api/new-deals/<produto>/cache/search`, que o interceptor
   não mocka). Solução usada: popular o **cache do dia** com operações fictícias
   (`scratchpad/seed_demo_deals.py`) e capturar; a página carrega sozinha. O Monitor se popula junto,
   porque lê os mesmos arquivos.
2. **Com dados fictícios, toda linha vira "Missing Counterparty".** As contrapartes inventadas não
   estão no Reference Data, e o guia mostraria o sistema como se estivesse quebrado. Foi preciso
   cadastrar **temporariamente** 6 contrapartes fictícias no `RefData.json` (com `B3 ACCOUNT`
   `73760.10-2` e o mesmo accronym usado nos deals), capturar, e **restaurar o arquivo**. Conferir a
   restauração por `md5` **e** por `git status` — o arquivo é versionado.

Depois da captura: apagar os arquivos de cache de demonstração e restaurar o `RefData.json`. Nenhum
dado real de cliente, conta ou credencial pode ficar nas imagens (regra do SOP §8.2).

**Armadilha de repositório — `Docs/` × `docs/`.** O repo tem **as duas grafias** (21 arquivos em
`Docs/`, 33 em `docs/`), resultado de ter sido criado num filesystem case-insensitive. Os prints ficam
em **`docs/` minúsculo**, que é o caminho que o SOP e o guia referenciam. Como o diretório em disco se
chama `Docs`, o `git add docs/sop-screenshots/...` **grava com `D` maiúsculo** e os arquivos novos
caem numa árvore diferente — no Mac não se nota, mas em Linux/Windows as imagens somem do documento.
Use `git -c core.ignorecase=false add docs/sop-screenshots/` e confira com
`git diff --cached --name-only | sed 's|/.*||' | sort | uniq -c`.

**`build_sop_docx.py` passou a aceitar o arquivo de origem por argumento** — sem argumento continua
gerando o SOP exatamente como antes; com argumento converte qualquer Markdown do repo. Foi assim que
o guia foi gerado, em vez de existir um segundo conversor. O Word do SOP foi regerado junto, porque
aponta para as mesmas telas.

**Dependências instaladas no venv:** `playwright` (+ `playwright install chromium`) e `python-docx`.
O `devrun.py` (launcher com o bypass `/dev-login`) fica na raiz, **gitignored** — confira com
`git check-ignore -v devrun.py` antes de qualquer commit.

**O que o guia ainda NÃO cobre:** Daily Settlement e os módulos de Swap em profundidade. Os prints
dessas telas já estão capturados; falta o texto.

---

## §156 — Operação cancelada na API sai da tabela em vez de virar badge (`d8bc8c2`)

Um registro que volta do `getTrades` com `isCancelled`/`isDead` **não existe mais na origem**. O
comportamento antigo — marcar como `Canceled` e deixar na tela — convidava alguém a registrar na B3 um
negócio que já morreu: o deal continuava visível, editável e a um clique de ser aprovado. Agora a
linha é **apagada** do arquivo do dia.

**A exceção é o deal que JÁ foi registrado na B3** (`Status = Success` **com** `B3_ID` preenchido).
Esse existe lá fora e cancelá-lo é ação humana na B3, então apagar a linha esconderia a pendência em
vez de resolvê-la — ele continua virando `Canceled` e à vista. `Success` **sem** `B3_ID` nunca chegou
a ser registrado e é apagado como os demais.

`_nd_cancel_in_file` passa a devolver **`(removidas, marcadas)`** e os dois pulls (NDF genérico e FXO)
somam as duas contagens **em separado** — no log, no retorno do endpoint e no breakdown do alerta de
Import (chave nova `swal-api-removed` nos três idiomas). Sem separar, "veio 0" não distinguiria linha
apagada de linha mantida.

---

## §157 — Varredura automática do box a cada 30 min (NDF Comm e Opt Comm) (`6dd15a4`)

O box só era varrido quando alguém clicava em **Import com o dropzone vazio**. Um booking recap que
chegasse fora desse momento ficava parado até alguém abrir a página. Agora um scheduler próprio
(`BOX_SCAN_POLL_MIN`, default 30) faz a mesma varredura sozinho, para os dois produtos, e arquiva o
e-mail processado.

### ⚠️ `otc_boxparse.py` é a SEGUNDA cópia de uma regra de negócio

O caminho manual parseia o e-mail **no navegador** (`otc-fileupload.js`), e o servidor não tem DOM. Por
isso nasceu `apps/pages/otc_boxparse.py`: um porte de `parseEmailHtml` + `buildRow` para Python puro
(`html.parser.HTMLParser`, sem dependência nova). É a mesma armadilha do espelho JS/servidor do arquivo
TER (§121).

**O que mantém as duas honestas é `scratchpad/check_boxparse.py`**, que executa o JS de verdade no
**JavaScriptCore** (`jsc`, já presente no macOS — não há `node` nesta máquina) e compara campo a campo.
Ele pegou duas divergências reais, ambas já corrigidas:

1. **Arredondamento do `toLocaleString`.** `2.675` → `2.68` no JS; `'{:.2f}'.format` do Python faria
   `2.67`, porque desempata para par sobre o **binário exato** em vez da representação decimal curta.
   A equivalência correta é `Decimal(repr(n)).quantize(Decimal('0.01'), ROUND_HALF_UP)`.
2. **Data fora de faixa.** `new Date(2026, 1, 30)` normaliza para 02/03; o Python levantaria
   `ValueError`. O helper `_to_date` soma dias sobre o dia 1º para reproduzir isso.

**Mexeu num dos dois lados, rode o `check_boxparse.py`.**

### Decisões do scheduler

- **Dedup por `Deal` + `Acronym`**, a mesma chave do navegador. Deal já conhecido vira `Amend`
  preservando o `B3_ID` e **limpando o Checker** (amend pede nova aprovação); deal novo entra como `New`.
- **E-mail cujo parse não achou nenhuma linha NÃO é arquivado** — fica no box com warning no log,
  porque arquivar esconderia um layout que o parser não soube ler.
- **`Maker = 'BOX'`**, mesma convenção do pull da Athena (que grava `'API'`). Ninguém humano importou,
  então a trava de quatro olhos segue válida e qualquer usuário pode aprovar.
- Os mapas Commodities × B3 saem do **cadastro** (`/mapping`), não de literais duplicados aqui (§131).
- Persistência sob `_cache_lock` no ciclo **inteiro** ler → alterar → gravar: o `_atomic_write_json`
  sozinho evita arquivo pela metade, não perda de atualização de outro usuário.

`POST /api/new-deals/box-scan/run` dispara na hora, para conferir o agendamento na instância da equipe
sem esperar os 30 min. Fora do Windows/Outlook a varredura devolve `unavailable` e o scheduler registra
em `info`, não como erro.

---

## §158 — Observation do Settlement Summary ficava à esquerda (`db1c6ba`)

A `td` já era centralizada, mas o texto da Observation vive dentro de um `<input>` que ocupa 100% da
célula e **não herda o `text-align` do pai** — o valor digitado ficava à esquerda enquanto o resto da
linha estava centrado.

A regra foi para a **classe** `.ops-obs-inp`, não para o ponto de escrita: a célula é reescrita pelo
render da tabela **e** pelo save do próprio campo, e alinhar em cada um deles volta a desencontrar
assim que alguém mexer num só (mesma lição da §153).

---

## §159 — Pending Confirmation: novo status "Pending Legal" (`f8bfcf1`)

Entra nos **seis** cards de faixa de Aging, no mapa dos widgets, no select de edição em massa e na
lista do modal de add/edit.

**A posição não é cosmética.** O `updateWidgets()` casa a linha do DOM com o `TYPE_ORDER` **por
índice** (`querySelectorAll('.float-end b')` → `TYPE_ORDER[j]`), então a nova linha e a nova entrada do
array têm de entrar **na mesma posição nos seis cards**. Ficou entre *Pending FO* e *Pending MO*,
mantendo a ordem alfabética que os cards já seguiam.

> Armadilha da edição: nem todos os cards usam `<span class="text-success">` para o bullet — alguns
> usam `<span style="color: #99BF00;">`. Um regex preso à classe altera só parte deles e o
> desalinhamento por índice acontece **em silêncio**. Casar o bullet genericamente
> (`<span [^>]*><i class="ti ti-point-filled"></i></span>`) e conferir a contagem antes de gravar.

**Nada a mudar no backend**: ele classifica por categoria (`_pc_is_ok_status`), e "Pending Legal" não
casa com `exception*` nem com os status de OK, então cai em pendente sozinho — conta nos widgets, no
dashboard de Metrics, no Daily Metric e na Weekly Escalation sem tratamento especial.

---

## §160 — Recon Pay/Rec: só conta como pago o que tem Status 'Sucesso' (`f9af52a`)

O `HistoricoMensagensJPM_*.csv` / `..._MGT_*.csv` é um **LOG de mensagens SPB**: carrega tanto as que
liquidaram quanto as que falharam ou foram rejeitadas.

`_cli_spb` (`apps/pages/recon_payrec.py`) tem **duas trilhas de captura** e só a segunda olhava a
coluna A. A trilha do cliente de derivativos (`Descrição Evento` com *Derivativos* / *LMA-COMM-BR*)
emitia um **Pay** para qualquer linha com a descrição certa, **inclusive as rejeitadas**.

**O efeito não é só inflar o total do lado cliente.** Uma perna sem dinheiro por trás ou casa por valor
com uma perna JPM legítima — e aí **esconde uma quebra real**, que passa a aparecer como `Settled` —
ou vira uma pendência que ninguém consegue rastrear até o arquivo de origem.

A checagem subiu para o **topo do laço**, antes de decidir a trilha, e a duplicata da trilha
interbancária saiu. Vale para os dois arquivos: JPM e MGT caem no mesmo parser (`_classify_source` só
troca o rótulo do sistema e a Legal Entity).

**Mantida a semântica da comparação que já rodava em produção** — `_norm()` (tira acento, caixa e
não-alfanuméricos) e teste de **substring**, não igualdade estrita — porque não há amostra dos arquivos
no repo para confirmar o literal exato da coluna. Assim `'Sucesso '` ou `'Sucesso.'` continuam passando
como antes. Se algum dia aparecer um status legítimo que não contenha "sucesso" (algo como
"Efetivada"), é aqui que se ajusta.

> **Impacto operacional:** no dia em que houver mensagem rejeitada, o lado cliente encolhe e operações
> que apareciam como `Settled` passam a `Pending`. É o comportamento correto, mas muda o número na tela
> de quem já usa a página — avisar antes de rodar a recon seguinte.

---

## §161 — Support Center: backend dos tickets (`c8185e7`)

As três páginas do Support Center eram **maquete**: linhas de exemplo no HTML, formulário que fazia
`POST` para `"#"` e nenhum armazenamento.

### Armazenamento — `apps/pages/otc_tickets.py` (módulo novo)

JSON único em `apps/static/data/tickets/tickets.json`, no formato
`{"seq": N, "tickets": [...]}`. Todo ciclo **ler → alterar → gravar** dentro de um lock e terminando em
escrita atômica: a escrita atômica sozinha não evita *lost update* (dois requests que leiam a mesma
versão fariam o segundo apagar a alteração do primeiro — mesma regra do `_cache_lock`).

**O contador do ID sequencial (`#OTC-0001`, `#OTC-0002`, …) vive NO ARQUIVO** e não é derivado do maior
ID existente. Derivar reaproveitaria o número de um ticket apagado, e dois tickets com o mesmo ID
quebram o histórico e o link do e-mail de encerramento.

O arquivo entra no **`.gitignore`**: é dado de runtime por instância. Versionar traria os tickets da
máquina de dev para produção e faria o contador de ID **andar para trás** a cada pull.

### Regras que o SERVIDOR impõe (não só a tela)

`requester`, `SID` e `status` **não são aceitos do corpo do request** — vêm da sessão, e todo ticket
nasce `New`. Aceitá-los do cliente deixaria qualquer um abrir ticket em nome de outra pessoa (testado
mandando `{"status":"Closed","requester_sid":"E930179","id":"OTC-9999"}`: os três são ignorados).

| ação | quem pode |
|---|---|
| ver | master vê todos; os demais só os próprios |
| criar | qualquer autenticado |
| status · due date | **só o master** |
| subject/description/priority/tags | o requester enquanto aberto; o master sempre |
| apagar · comentar | o requester ou o master |

> **Decisão não pedida explicitamente, registrada porque é uma escolha:** o master vê todos os tickets,
> cada usuário vê só os dele. É a leitura coerente com "notificações de ticket novo só para o master" e
> "apagar só o requester ou o master". Se o time quiser todo mundo vendo tudo, é uma linha em
> `_tk_visible_tickets`.

### `notifications.target_sid` — coluna nova (MIGRAÇÃO)

`ALTER` idempotente no padrão do `_migrate_schema`. **`target_role` não resolvia o pedido**: as
atualizações vão só para o requester, e o papel dele (BO/MO/FO/…) é compartilhado com o time inteiro.

- `target_sid` preenchido é **mais forte** que `target_role`: só aquele SID vê — nem o master.
- Notificação antiga, com `target_sid` NULL, **continua visível para todos** (`COALESCE(...) = ''`).
- O **Web Push acompanha o mesmo filtro** — senão o celular do time apitaria por uma notificação que só
  o requester consegue abrir.
- Ticket novo continua em `target_role='MASTER'`, que já isolava: `'MASTER'` **não é papel de banco**, é
  o valor que `_set_session` grava para os SIDs de `_MASTER_SIDS`.

Ao adicionar um `page` novo de notificação, lembrar das **três** cópias do mapa página → URL:
`_NOTIF_PAGE_URL` (routes.py), `PAGE_URL` em `partials/topbar.html` e `PAGE_URL` em
`static/js/sw-push.js`. Faltar numa delas faz o clique cair no dashboard.

### E-mail de encerramento

Template `pages/email-template-ticket-closed.html`, requester no **To** e
`brazil.otc.ops@jpmorgan.com` em **Cc**.

**Dispara só na TRANSIÇÃO** para `Resolved`/`Closed`: sem o par `was_final`/`is_final`, salvar de novo
um ticket já encerrado (mudando a prioridade, por exemplo) reenviaria o aviso. Reabrir limpa o
`closed_at`, então encerrar outra vez avisa de novo — que é o que o requester espera.

**Falha de SMTP não desfaz o encerramento** — o ticket já está gravado e a tela diz explicitamente que
o e-mail não saiu. Sem esse aviso alguém acreditaria que o requester foi informado.

### Telas

`ticket-create.html` foi **removida** (e tirada do `sidenav.html` e do `horizontal-nav.html`): o
formulário virou um **SweetAlert** dentro de `/tickets-list`, com Requester Name e Requester SID
`readonly` vindos da sessão e Status travado em `New`. Saíram as 11 linhas de exemplo.

- **Assigned Agent** = logo do OTC Tracker + "OTC Tracker Team". O logo troca por **`[data-bs-theme]`**,
  **não** pelas classes `.logo-light`/`.logo-dark` do layout — aquelas reagem também a
  `data-menu-color` e apareceriam invertidas em algumas combinações de menu (é a armadilha nº 2 do §8).
- **Due date nasce em branco** (só o master preenche). Os cards do topo contam de verdade.
- O card de **chat saiu** do `ticket-details`, que virou largura cheia.

**A lista largou o `custom-table.js`.** Ele fotografa `this.rows` na construção e auto-inicializa no
`DOMContentLoaded`, então **nunca enxergaria uma tabela vinda de `fetch`**; e a lixeira dele apaga só
do DOM, o que conflitaria com a regra de quem pode excluir. Busca, filtros, ordenação e paginação são
próprios da página.

### Verificação

`scratchpad/check_tickets.py` — 93 asserções: CRUD, as seis regras de permissão, forja de
requester/status/ID pelo corpo, sequência após exclusão, transição do e-mail (envia · não reenvia ·
reenvia após reabrir), render das páginas e JSON corrompido.
`scratchpad/check_notif_sid.py` — o `ALTER` numa tabela criada **sem** a coluna e o isolamento do sino
nos três alvos (SID · papel · broadcast).

---

## §162 — Foto do solicitante no Support Center (`94862cd`)

A coluna *Requested By* mostrava só nome e SID em texto, enquanto a coluna ao lado (*Assigned Agent*)
já trazia o logo — a linha ficava torta.

**Convenção que o app já tinha, reaproveitada em vez de inventar outra:**
`/static/images/users/<sid minúsculo>.jpg`, exatamente o que o sino de notificações usa em
`partials/topbar.html`. Hoje **só o SID do master tem arquivo na pasta** (`e930179.jpg`; os `user-N.jpg`
eram sobra do template e foram embora com as linhas de exemplo), então o caminho que roda na maioria
das linhas é o **fallback** — sem o `onerror` a célula ficaria com o ícone de imagem quebrada em quase
todo ticket. O substituto é um círculo com as iniciais (primeiro e último nome), no mesmo estilo do sino.

**No `ticket-details` o `onerror` é rearmado a cada `paint()`.** Ele se auto-anula ao disparar
(`this.onerror = null`), então sem rearmar, um ticket sem foto seguido de um com foto deixaria o
handler morto e o `<img>` quebrado voltaria a aparecer.

O nome vem do **phonebook** e o SID entra **dentro de um atributo `src`**, então os dois passam por
escape/encode. Verificado com 17 asserções rodando a lógica real no `jsc`, incluindo
`<img onerror=bad>` no nome e `A1"><script>` no SID, além do caso de SID vazio (não pode imprimir um
`<small>` órfão).

---

## §163 — `scripts/tests/` — as verificações saíram do scratchpad para o repo

Os harnesses das últimas sessões viviam no scratchpad, fora do versionamento — ou seja, a próxima
pessoa a mexer nesses arquivos não teria como saber que existiam. Foram para **`scripts/tests/`**, com
`README.md` mapeando cada script ao que ele protege e a **quando rodá-lo**.

São scripts autocontidos, sem framework: imprimem `ok`/`FAIL` por asserção e saem com 0 ou 1. A raiz do
repo é resolvida a partir do próprio arquivo (`scripts/tests/` → `..` → `..`), então rodam de qualquer
diretório e em qualquer máquina — o caminho absoluto do Mac saiu.

| script | protege | rodar ao mexer em |
|---|---|---|
| `check_boxparse.py` | paridade **JS ↔ Python** do parser de booking recap (executa o JS no `jsc`) | `otc_boxparse.py` **ou** `otc-fileupload.js` (§157) |
| `check_boxsched.py` | varredura agendada do box (dedup, amend, arquivamento) | box scan em `routes.py` (§157) |
| `check_cancel_remove.py` | `_nd_cancel_in_file` (apaga vs. mantém como `Canceled`) | os pulls da API (§156) |
| `check_spb_status.py` | Recon Pay/Rec: só `Sucesso` entra, nas duas trilhas | `_cli_spb` (§160) |
| `check_tickets.py` | Support Center ponta a ponta — 93 asserções | `otc_tickets.py`, `/api/tickets*`, templates (§161) |
| `check_notif_sid.py` | migração e isolamento do `target_sid` | `_create_notification`, `_push_notify`, feed (§161) |

Nenhum encosta em dado real: tickets vão para `tempfile`, o DuckDB é recriado num tmp, Outlook e SMTP
são stubados. **`check_boxparse.py` depende do `jsc`** (nativo do macOS; não roda no Windows da
equipe — os outros cinco rodam).

---

## §164 — Cadastro dos arquivos CETIP + notação de padrão no B3 Code (`03bbab3`)

Duas coisas presas no código-fonte viraram cadastro. E uma divergência real apareceu no caminho.

### A lista de arquivos do Save CETIP Files saiu do código

As 15 regras viviam em `_CETIP_RULES`, cada uma com um `match` (substring no nome) e um `date_start`
(offset do YYMMDD). Agora a **lista** é cadastrada em **/mapping › CETIP Files**, no padrão
`CETIP21_YYMMDD_DPOSICAO-SWAP` — o `YYMMDD` marca **onde a data está**.

Isso funde dois campos que podiam se desencontrar: o token identificava o arquivo, o `date_start` dizia
onde ficava a data, e nada garantia que os dois falassem do mesmo nome. Um padrão só dá as duas coisas.
De quebra, as exclusões `_15H00`/`_18H30` do DMOVIMENTO **deixaram de ser necessárias**: o padrão casa
o nome inteiro (sem extensão), então a variante de horário já não bate sozinha.

**O que NÃO foi para a tela é comportamento, não de-para.** Como o arquivo vira JSON, os filtros de
coluna, o `vcp_update` e os anexos de e-mail continuam em **`_CETIP_BEHAVIOUR`**, ligados à linha pela
coluna **`TYPE`**. ⚠️ **Renomear o `TYPE` na tela desliga esse comportamento** e o arquivo passa a ser
só copiado e renomeado — sem erro, sem aviso na tela.

**O prefixo literal (`CETIP21_`, `TER_`) NÃO é comparado, só o seu tamanho.** Os nomes de origem nunca
foram confirmados com a B3 (pendência aberta desde a §27), e o `TER_` do DPOSICAO-TER é inferência a
partir do `date_start` 4. Exigir o prefixo poderia parar de salvar um arquivo que hoje funciona; quando
ele diverge do cadastro fica um **aviso no log**, o que dá o diagnóstico sem o risco. Se alguém
confirmar os nomes reais, apertar isso é uma linha em `_cetip_make_matcher`.

A data do card do Control Panel **já escolhe a pasta do dia** (origem e destino são
`…\YYYY\mm. Month\dd`); o `YYMMDD` casa qualquer 6 dígitos, como antes. Travar no dia do card faria a
rotina ignorar um arquivo carimbado com D-1, que é o caso comum.

### Notação de padrão na coluna B3 Code

A coluna passa a guardar o **código inteiro**, não só o prefixo:

```
"MY"   onde entram a letra do mês e o último dígito do ano do contrato.
       Entre ASPAS porque um código pode ter M e Y como texto fixo — sem a
       marca não daria para saber qual é qual.
_      um ESPAÇO no código emitido. O milho na B3 é 'C ' COM o espaço, e
       espaço no fim de um campo é invisível na tela e some num trim distraído.

XB"MY" → XBZ7        C_"MY" → 'C Z7'        KO"MY"BNMK → KOZ7BNMK
```

Padrão **sem aspas** é lido como formato antigo (só o prefixo, mês/ano no fim), o que mantém uma linha
não migrada funcionando. `_commodities_b3_upgrade` migra **na leitura**, então instância com o arquivo
editado localmente não precisa de script.

Permitir texto **antes E depois** do mês/ano é o que faltava para o FCPO sair de SPECIAL. Sobrou só o
**BRT_IPE** como SPECIAL, porque o código dele depende de vanilla × asian — isso é lógica, não de-para.

### ⚠️ As três cópias discordavam sobre o FCPO

| arquivo | emitia |
|---|---|
| `otc-fileupload.js` | `KOZ7BNMK` |
| `deals-processing-table.js` | `.KOZ7BNMK F` |
| `otc_boxparse.py` | `KOZ7BNMK` |

O **mesmo deal** ganhava um código B3 diferente conforme tivesse entrado pelo upload, pela tabela de
processamento ou pela varredura do box. Com o cadastro passa a existir **um valor só**: `KO"MY"BNMK`
(confirmado pelo usuário), que é o que duas das três cópias já emitiam. **Vale conferir se algum FCPO
foi registrado na B3 com `.KOZ7BNMK F`.**

> Lição repetida: `calculateB3Id` existe em **três** lugares (`otc-fileupload.js`,
> `deals-processing-table.js`, `otc_boxparse.py`). É a armadilha da §121/§157 outra vez. O
> `check_b3_pattern.py` agora roda as **duas** cópias JS no `jsc` e compara com a Python.

### Destaque do trecho variável na tabela

`"MY"` (B3 Code) e `YYMMDD` (arquivos CETIP) saem em **âmbar** com fundo levíssimo. Âmbar é a única
família que não colide com o que a tabela já usa (azul = ação, verde = ok, vermelho = excluir);
`#a05a00` no claro e `#ffb545` no escuro passam de 4.5:1, e o **fundo** delimita o trecho mesmo para
quem não distingue a cor — que é o ponto: bater o olho e ver o que muda.

Só aparece em linha **PREFIX**: em `FIXED` o código é literal e um `MY` ali seria texto mesmo.

**Armadilha do escape:** o destaque escapa **por pedaço**, não o valor inteiro. `esc()` no valor todo
transformaria as aspas em `&quot;` e aí a regex do token não acharia mais nada.

---

## §165 — Accrual/CEM: as abas passam a ser lidas por POSIÇÃO, não por nome

**O sintoma:** a importação por arquivo CEM morria na instância da equipe com
`ValueError: CEM file is missing the 'Kapital CETIP' sheet (Kapital → LE).`

**A causa:** `_acc_parse_cem_factors` procurava a aba cujo **nome** contivesse `kapital` (normalizado
sem espaços). O arquivo real chega com essa aba nomeada de outro jeito, então `kap_rows` ficava `None`
e o `raise` derrubava a importação inteira — não só aquela aba.

**A correção:** as abas são lidas por posição — **1ª = summary** (os fatores), **2ª = Kapital CETIP**
(col B Kapital → col E LE). A ordem das abas é estável no arquivo que a área gera; o nome não é.

**Sem fallback por nome, de propósito.** Um fallback reintroduziria em silêncio a fragilidade que a
mudança remove: com as abas reordenadas E uma delas chamada "kapital", o fallback venceria e o
comportamento ficaria inconsistente entre arquivos.

**Duas coisas que vieram junto:**

- A mensagem de erro agora diz o que o arquivo precisa ter **e o que ele tem**:
  `CEM file needs at least 2 sheets (1st = summary, 2nd = Kapital CETIP); found 1: 'Resumo'`. A antiga
  mandava procurar uma aba com um nome que talvez nem devesse existir.
- Um `log.info` registra **quais** abas foram usadas. Como a escolha agora é posicional, é o log que
  permite descobrir uma planilha fora de ordem sem abrir o arquivo.

**Modo de falhar:** com as abas invertidas o parser devolve **vazio**, não fator errado — o CETIP da
aba de Kapital não casa com nada e as linhas aparecem como *Missing Accrual*. É a falha desejada:
pede correção em vez de gravar um número inventado.

> ⚠️ **Risco conhecido:** o `openpyxl` enxerga **abas ocultas** em `sheetnames`. Uma aba oculta na
> posição 2 seria lida como a Kapital. O `log.info` novo denuncia isso na primeira importação; se
> acontecer, filtrar por `ws.sheet_state == 'visible'` em `_acc_read_sheets`.

`_acc_parse_direct_factors` (EDG/HYB) **já** era posicional (`next(iter(sheets.values()))` = 1ª aba),
então os três parsers de fator agora seguem a mesma regra.

Verificado com `scripts/tests/check_cem_sheets.py` — monta workbooks de verdade com openpyxl e cobre
os nomes que o código antigo não reconhecia, os nomes antigos ainda funcionando, abas extras depois da
2ª, a inversão 228/199 preservada, os dois casos de erro (uma aba só e CSV) e a ordem trocada.

---

## §166 — Vanilla × Other Publisher sai do cadastro, não do literal `'PTAX'` (`0c94d3c`)

**O sintoma:** o usuário cadastrou a linha `PTAX|BRR|PTAX` em /mapping › Publisher × B3 (NDF) e as
operações desse feeder continuavam caindo em **Other Publisher** em vez de **Vanilla**.

**A causa:** o roteamento do import da API nem olhava o cadastro — era um literal:

```python
elif publisher and publisher.upper() != 'PTAX':
    target = 'other-publishers'
```

Qualquer coisa diferente da string exata `PTAX` ia para Other Publisher, **inclusive as variantes que
também são PTAX do BACEN**. Não havia como corrigir pela tela.

**A correção:** quem decide agora é a coluna **NOTES**.

| NOTES | destino |
|---|---|
| `BACEN` | **Vanilla** |
| qualquer outro valor | Other Publisher |
| publisher sem linha no cadastro | Other Publisher |
| publisher vazio | **Vanilla** (default histórico do import: sem feeder = PTAX puro) |

A comparação é sobre o texto limpo e sem caixa (`bacen`, `  BACEN  ` valem), mas **não por trecho** —
`BACEN/PTAX` não conta. É a mesma regra de "sem variações" que vale para o match de publisher.

### O match exato de uma linha sem Match Tokens

`_ndf_publisher_row` faz **duas passadas, nesta ordem**:

1. **nome exato** — `PUBLISHER` igual ao publisher inteiro;
2. **token** — só para linhas **com** `TOKENS`, porque a Athena manda o publisher composto
   (`PTAX|USB|WMR|4` → REUTERS - WMR).

Uma linha **sem** Match Tokens só casa na passada 1 (o `split` de string vazia não produz token). É o
que permite `PTAX` e `PTAX|BRR|PTAX` coexistirem como cadastros **independentes** — nenhum rouba o
outro. A regra sempre valeu, mas estava implícita; virou docstring e teste.

Os rótulos das colunas passam a anunciar a semântica, para quem abre a tela não achar que `NOTES` é só
comentário: **"Notes (BACEN → Vanilla)"** e **"Match Tokens (blank = exact match only)"**.

> ⚠️ **O que sustenta a compatibilidade** é a linha `PTAX` estar com `NOTES = BACEN`. Se alguém apagar
> esse campo, PTAX puro passa a ir para Other Publisher — é a única forma de isso quebrar. Os 10
> publishers do seed foram comparados contra a fórmula antiga e dão idêntico.

`_ndf_deal_from_api` é o **único** ponto onde um deal é classificado Vanilla × Other Publisher; não há
segunda cópia dessa decisão no front (o `_pubRow` do JS serve só à Fonte de Informação do TER).

Verificado com `scripts/tests/check_publisher_ndf.py` — 40 asserções, com o cadastro da tela
reproduzido incluindo a linha nova.

---

## §167 — Verificação: o mapping da Intrag **não** dispara notificação no topbar (sem alteração de código)

**A pergunta:** "verifique se tem notificação no topbar para quando é concluído o mapping nas páginas
de Intrag NDF e Intrag Option". **A resposta: não tem.** Fica registrado aqui para ninguém refazer a
busca — e porque a ausência é fácil de confundir com "a notificação existe mas não chegou".

**O que foi medido.** Os três endpoints de mapping da Intrag —
`/api/intrag/ndf/mapping-intrag-id`, `/api/intrag/option/mapping-intrag-id` e
`/api/intrag/swap/mapping-intrag-id` — chamam `_intrag_run_mapping`, que persiste o `intrag_id`,
promove a linha para `Success` e devolve os resultados. **Nenhum deles chama `_create_notification`.**
Com o finder stubado para forçar um mapping bem-sucedido, o sino continuou em zero nos três; o
controle foi o `B3 Mapped` do New Deals, que nas mesmas condições gerou uma notificação.

Não é esquecimento isolado: a Intrag só notifica nas ações de linha (add/edit/delete/confirm) e no
envio, nunca no mapping. As páginas dão o retorno pelo próprio SweetAlert de resultado.

**Se um dia for implementar**, o desenho combinado (não executado, aguardando a palavra do usuário) é
notificar nos três endpoints e **só quando `mapped > 0`** — um mapping que não casou nada não é evento,
e o CSV da Intrag é reprocessado várias vezes ao dia; notificar em toda tentativa transformaria o sino
em ruído. Página `Intrag NDF` / `Intrag Option` / `Intrag Swap`, ação `Intrag ID Mapped`, detalhe com a
contagem, no mesmo formato do `Sent to B3`.

> ⚠️ Ao mexer nesses endpoints, lembre que `_intrag_run_mapping` recebe a lista de deals **do cliente** —
> é a mesma armadilha do `table.rows({search:'none', page:'all'})` descrita no CLAUDE.md: cobre só o que
> está carregado na tela, não o dia inteiro. Uma contagem de notificação tirada daí conta a tela, não o
> arquivo.

---

## §168 — E-mail saindo metade gradiente, metade cor sólida (`20e258e`)

**O sintoma:** o "CETIP Files Saved" de 03/08/2026 chegou com a faixa azul do topo pintada só até
~93% da largura; o resto era um bloco chapado de `#4f8ae2`. Nos outros dias saiu certo, e os **outros
dois e-mails do mesmo lote** (Sales Support e CEM Latam) — que passam pelo **mesmo** `_send_cetip_email`
e pelo mesmo template — saíram certos no mesmo dia. HTML idêntico rendendo diferente é o que aponta
para fora do template.

**As duas causas.** As duas produzem o mesmo desenho, e as duas variam de um envio para o outro:

1. **A imagem vinha por URL remota quando o e-mail sai de uma requisição.** `_inject_email_grad_url`
   devolvia `url_for(..., _external=True)` sempre que havia contexto de requisição, e só caía no `cid:`
   quando não havia (envio agendado). O Save CETIP Files é botão do Control Panel, ou seja, **sempre**
   pegava a URL remota. URL remota é download: o Outlook pode bloquear, atrasar ou concluir pela
   metade — e meia imagem é meia faixa. O `cid:` já era anexado por `_attach_email_gradient()` em todos
   os senders, então bastou passar a usá-lo sempre. Mesmo ajuste no draft do Daily Metric, o outro
   ponto que montava a URL na mão.
2. **O `v:rect` do VML podia ser pintado mais estreito que a célula.** O que sobra à direita fica com o
   `color` sólido do `v:fill`, que é exatamente o `#4f8ae2` observado. Só o `width` em px não garante
   alinhamento com a tabela HTML; **`mso-width-percent:1000`** amarra a pintura à largura real da
   célula.

> ⚠️ A correção está no **partial compartilhado** `partials/email-gradient-header.html`, então vale para
> os 15 templates de e-mail — não só o do CETIP. Ao mexer nele, lembre que `grad_url` **nunca** pode
> voltar a ser URL http: o anexo `cid:` é o que não falha pela metade.

---

## §169 — Dois cadastros novos: Legal Entity × SPN e o PDF do aviso de NDF (`049794d`, `6d2402f`)

Dois mappings novos na tela `/mapping`, pela regra de sempre: nada mapeável fica no código.

### Legal Entity × SPN (`le-spn`)

Colunas **Legal Entity** (dropdown), **SPN** e **Notes**. É o SPN da **nossa** ponta — coisa diferente
do SPN da contraparte, que continua vindo do Reference Data pelo accronym (§147/§148). Nasce **vazio**:
não havia de-para hardcoded para semear, e SPN inventado no seed sairia em arquivo para a B3 com cara
de cadastro real. Mesmo critério do `swap-curves`.

A lista de LEs virou `_MAP_LE_OPTIONS`, compartilhada com o `le-accronym` para as duas não divergirem.
A **ATACAMA** entrou depois em `_MAP_LE_SPN_OPTIONS` (`_MAP_LE_OPTIONS + ['ATACAMA']`), só no `le-spn`:
o `le-accronym` segue com as três entidades que de fato têm accronym e settlement location. Se a
ATACAMA passar a ter accronym, mova o valor para `_MAP_LE_OPTIONS` e apague a lista extra.

> A lista de LEs é **código, não cadastro**: cada entidade nova custa commit + restart, que é justo o
> atrito que a tela existe para evitar. Se aparecerem mais, o certo é o LE virar texto livre ou puxar as
> opções das linhas já registradas.

Ninguém consome o `le-spn` ainda — por ora é só o cadastro.

### Settlement PDF (NDF Advice) (`ndf-pdf-cpty`)

O aviso de liquidação de NDF de Moeda leva a Ficha de Liquidação **também em PDF anexo** para algumas
contrapartes. A lista era a tupla `_NDF_PDF_COUNTERPARTIES` em `otc_emails.py`, herdada da macro
CommodiXchange — cliente novo exigia mexer no código. Virou cadastro, com o seed carregando **exatamente**
as 6 contrapartes de antes.

**O consumidor lê o arquivo direto**, não via `_mapping_rows`: `otc_emails.py` não importa `routes.py`
(seria import circular), então `_ndf_pdf_set()` faz `open` + `json.load` no
`static/data/mappings/ndf-pdf-cpty.json`, no estilo do `_load_json` que o módulo já usa. Lê a cada aviso
gerado, então **edição na tela vale na próxima geração, sem restart**.

Duas semânticas que precisavam ficar separadas — e é aqui que se erra:

| estado do cadastro | resultado |
|---|---|
| linhas registradas | manda o cadastro |
| **vazio** (`[]`) | **ninguém leva PDF** — é resposta legítima, e é o que permite desligar o anexo pela tela |
| arquivo **ausente** ou ilegível | volta à lista histórica |

> ⚠️ Se o vazio caísse na lista histórica, não haveria como tirar o anexo de ninguém pela tela. Se o
> arquivo ausente caísse em conjunto vazio, o primeiro aviso gerado depois do pull — antes de alguém
> abrir a tela de mappings, que é o que semeia o arquivo — tiraria o PDF de quem sempre recebeu.

O nome casa pelo **normalizado** (`_ndf_pdf_norm`: sem acento, caixa alta, espaços colapsados, travessão
vira hífen), então grafia diferente entre a tela e o Reference Data não quebra o match. O que precisa
bater é a **razão social**, não o accronym.

Verificado com `scripts/tests/check_ndf_pdf_cpty.py` — 24 asserções, incluindo a **paridade entre o seed
em `routes.py` e a tupla de fallback em `otc_emails.py`**: editar um e esquecer o outro faz a instância
sem o arquivo anexar PDF para um conjunto diferente do que a tela mostra.

---

## §170 — `HO"MY"U6` no Underlying Asset: JS velho em cache lendo o cadastro novo

**O sintoma:** um deal de NDF Commodities entrou com **Underlying Asset `HO"MY"U6`** e o badge
*Missing Index B3*, embora o market `HO_NYMEX` estivesse mapeado como `HO"MY"` em Commodities × B3 e o
`HOU6` cadastrado no Subjacente. Cadastro certo, tela errada.

**A causa: o token de cache do `<script>`.** O `otc-fileupload.js` era servido com
`?v=20260728b`, escrito à mão. O §164 (`03bbab3`, 31/07) mudou esse arquivo para a notação `"MY"` e
**ninguém trocou o token** — nem o `2b168a9`, antes dele. Com a URL igual, o navegador seguiu executando
o JS **anterior ao §164**:

```js
function buildDynamicCode(prefix, contract) {   // versão antiga
    return prefix + p.monthCode + p.yearLast;   // o padrão inteiro vira prefixo literal
}
```

`HO"MY"` + `U` + `6` = `HO"MY"U6`. O servidor já servia o cadastro no formato novo; o cliente é que
tinha ficado para trás. Nada no cadastro estava errado — e é por isso que a conferência campo a campo
não achava nada.

> ⚠️ **Um `?v=` escrito à mão é uma promessa que alguém vai esquecer.** E quando esquece, o que quebra
> não é o layout: é o dado, porque a regra de negócio mora nesse JS. `asset_v()` (`routes.py`) devolve o
> **mtime** do estático, então publicar o arquivo já invalida o cache — não sobra string para bumpar. Os
> 6 templates que carregam o `otc-fileupload.js` passaram a usá-lo.

**A rede de segurança.** `_nd_fix_underlying_marker` limpa um `"MY"` que tenha sobrado no
`UnderlyingAsset` nos POSTs de `/api/new-deals/{ndf,opt}-commodities/cache`, e loga um WARNING com o
deal — é o que identifica a máquina com o JS velho. Como o marcador nunca faz parte de um código B3 de
verdade, apagá-lo devolve exatamente `HOU6`.

A guarda fica na **gravação**, não na exibição: corrigir só na tela deixaria o arquivo do dia — que é o
que alimenta o Conecta e o registro na B3 — com o código torto, e aí a tela mentiria sobre o que vai
para o regulador. Ela também cobre a aba que já estava aberta com o JS velho, que continua postando até
alguém dar reload.

**O que a correção NÃO faz:** deal já gravado continua errado no arquivo do dia. Reenviar o recap ou
editar a linha faz o save passar pela guarda e o código sai certo.

Verificado com `scripts/tests/check_b3_pattern.py` (seção 2b) — inclui o caso exato `HO"MY"U6 → HOU6`,
o marcador em minúsculas e com espaço, e a prova de que um código bom não é tocado.

> Sobrou um caso irmão à espera: `live-position-swap-characteristics.js` está com **dois tokens
> diferentes** em templates diferentes (`20260705` em 4 páginas, `20260721a` em 3), ou seja, quatro
> páginas servem uma cópia mais velha do mesmo arquivo. Os outros 22 `?v=` do repo continuam escritos à
> mão; passar o `asset_v` em todos resolve a classe inteira.

---

## §171 — Confirmação de Opção de Commodities com strike em BRL (família `brl`)

O `OPÇÃO COMMODITY - BRL.doc` chegou como export bruto do Word e virou template. O achado que
define a implementação inteira veio antes de escrever qualquer código: **os dois documentos, USD e
BRL, têm exatamente o mesmo texto legal.** Comparação palavra a palavra, sem acento nem pontuação,
descontando o painel e os valores preenchidos do exemplo — sobraram **4 diferenças**, todas no
cabeçalho do Anexo I:

| Coluna | USD | BRL |
|---|---|---|
| Tipo da Opção | `Tipo da Opção`ᵢ | `Tipo da Opção` |
| Quantidade | `Quantidade` | `Quantidade`ᵢ |
| Preço de Exercício | `Preço de Exercício`ᵢ | `Preço de Exercício`ᵢ **(em R$)** |
| Data de Exercício | `Data de Exercício`ᵢ | `Data de Exercício` |

> A cláusula da **USD PTAX continua no documento em BRL** — ela trata do preço da *Mercadoria*
> cotada em dólar, não do strike. Por isso a coluna Data de Verificação da PTAX segue **única** aqui,
> ao contrário do Termo em BRL (§ do `ndf-comm-strike-brl`), que troca a data única pela janela
> inicial/final. Quem for portar a próxima família não deve assumir que "BRL ⇒ janela de PTAX".

Por isso o template BRL foi **gerado do irmão USD por script**, aplicando só essas quatro trocas (o
script aborta se qualquer trecho aparecer um número de vezes diferente do esperado — nada de edição no
escuro). Ele herda painel, `doc_only`, salvamento e validação, e manda `family: 'brl'` no save.

**O que estava só esperando ser ligado:** `_conf_deal_family` já classificava strike BRL/BRR como
`brl`, e `opcao_pdf` já recebia um parâmetro `variant` que ninguém usava. Faltava a entrada em
`_CONF_OPT_FAMILY_TEMPLATES`, a rota, e o save passar a variante — os grupos em BRL apareciam na
lista de confirmações como *indisponíveis*.

> ⚠️ **O cabeçalho tem duas cópias**: o `<th>` do template e a lista da réplica em reportlab. O PDF é
> o que vai assinado para a contraparte e o HTML é o que a pessoa revisa na tela — divergir aqui não
> quebra nada, só faz o documento mentir. A lista saiu para `opcao_anexo_heads(variant)` justamente
> para o teste poder comparar as duas.

Verificado com `scripts/tests/check_conf_optcomm_brl.py` — 21 asserções: as **4 diferenças de palavra
e nada mais** entre os dois documentos (mexer numa cláusula e esquecer o irmão cai aqui), o cabeçalho
célula a célula contra o Word, PDF × template, e a família ligada de ponta a ponta.

**Duas decisões em aberto, à espera da palavra do usuário:**

- O Word do BRL escreve `conseqüentemente` (com trema) na cláusula de call e `consequentemente` na de
  put; o documento em USD não usa trema em nenhuma das duas. Tratado como typo do legado — os dois
  templates ficaram com a grafia moderna. Se o jurídico exigir a reprodução letra por letra, é uma
  troca de string.
- O Preço de Exercício continua saindo como `Strike × Fator de Conversão`, que é o que o Termo em BRL
  já faz. Se para opção com strike em reais o valor tiver de sair cru, é uma linha em
  `_conf_opt_generation_page`.

---

## §172 — Quoted in Cents deixa de olhar a moeda do strike

**A regra é do ATIVO, não do par de moedas.** `Quoted in Cents` é derivado do **Fator Conversão
0,01** do Subjacente (`_is_cents_factor`): diz que aquele ativo é *cotado em centavos*, o que é
propriedade da commodity e não do deal. Excetuar o BRL fazia o mesmo ativo sair com strike **100×
diferente** conforme a moeda da operação.

**O que se achou na varredura.** A divisão por 100 estava reescrita em **cinco lugares, com três
regras diferentes**, e os pares estavam **cruzados** — cada produto excetuava o BRL num destino e não
no outro:

| caminho | antes | agora |
|---|---|---|
| NDF Comm → **Conecta** (servidor + navegador) | `qic` **e não BRL** | `qic` |
| NDF Comm → Intrag | `qic` | `qic` |
| Opt Comm → Conecta (strike e prêmio/unidade) | `qic` | `qic` |
| Opt Comm → **Intrag** | `qic` **e não BRL** | `qic` |
| Confirmações (`_conf_strike_adj`) | Fator do Subjacente; `/100` de fallback | inalterado |

Ou seja, **o mesmo deal saía com strike diferente em dois arquivos da mesma página**. As duas exceções
foram removidas por decisão do usuário: *"retire a verificação se o strike é em BRL, e considere sempre
strike × quoted in cents, independente se for USD ou BRL"*.

No Intrag da Opção isso deixou `strike_ccy` e `is_brl` órfãos — apagados. Nas outras duas funções a
flag de BRL **continua viva**, porque decide outros campos (Data de Fixing da Moeda, o `'S'` do
arquivo); ela só saiu da conta do strike.

> ⚠️ Deals já gravados não mudam sozinhos, mas os arquivos são **gerados na hora** a partir do day-file:
> um NDF Comm com strike em BRL sobre ativo cotado em cents, se reenviado ao Conecta, sai **diferente do
> que saiu antes**. Operação já registrada na B3 pela regra antiga tem de ser conferida antes do reenvio.

Verificado com `scripts/tests/check_quoted_in_cents.py` — 33 asserções. Além dos casos de
`_is_cents_factor` e do YES/NO/MISSING do parser, ele **varre o código-fonte dos quatro caminhos e das
duas cópias no navegador atrás de qualquer termo de moeda dentro da regra**: executar os builders
exigiria escrever arquivo do dia e disparar rota, então a varredura é o que dá para fazer de forma
honesta. Para não virar vácuo se alguém renomear as variáveis, o teste também exige encontrar no mínimo
6 aplicações. Ele foi testado ao contrário — com a exceção do BRL reintroduzida de propósito, apontou a
linha e o caminho.

**Continua em aberto:** `MISSING` (ativo sem cadastro no Subjacente) se comporta como `NO` em todos os
consumidores, que comparam `== 'YES'`. Um subjacente não cadastrado segue para o Conecta sem divisão e
sem aviso — pergunta feita ao usuário, ainda sem resposta.

## §173 — Link da API vira cadastro (`api-links`) e `isDead` volta a ser importado

Duas mudanças no mesmo pull da Athena, pedidas na mesma conversa.

### 1. O endereço da API sai do código

`BASE_URL + TRADES_ENDPOINT` eram **constantes** em `athena_api.py`: trocar o endpoint (versão nova,
migração de host, apontar para UAT) exigia mexer no código e **reiniciar o servidor** — que é
justamente o que a equipe não consegue fazer sozinha na instância. Agora é cadastro em **/mapping ›
API Links** (`api-links`), uma linha por **USO × PRODUTO**:

| USE | PRODUCT | seed |
|---|---|---|
| `New Deals` | `NDF` | `…/getTrades?product=NDF&date=YYYYMMDD` — exatamente a URL que estava no código |
| `New Deals` | `FXO` | idem com `product=FXO` |
| `New Deals` | `Commodities` · `Swaps` | idem, ainda sem consumidor |
| `Unwinds` | *(em branco)* | **vazia**, de propósito |

**Produto é o do `product` da API, não a página.** NDF é **um** produto que alimenta **três** páginas —
Vanilla, Other Publisher e FWD Start —, separadas pelo roteamento do publisher e do Instrument Type
(§166) e não pelo endereço. Cadastrar uma linha "FWD Start" não faria a operação vir de outro lugar.

**`PRODUCT` em branco é curinga** daquele uso: só entra quando o produto pedido não tem linha própria.

**`YYYYMMDD` marca onde entra a Data de Referência**, e é destacado na tabela como o `YYMMDD` dos
arquivos CETIP (§164). Ele existe para a data que fica no *caminho* (`…/trades/20260728`), onde
parâmetro nenhum alcança; o parâmetro `date` é reescrito de todo jeito. Já o **`product` só é reescrito
na linha curinga** — na linha de um produto o endereço vale como está, porque foi ela que o produto
escolheu; reescrever seria contrariar o cadastro.

A linha de Unwinds nasce **sem URL** porque não existe rotina de unwind ainda: semear um endereço não
conferido faria a primeira rotina a nascer chamar um endpoint inventado. Sem cadastro, `fetch_unwinds`
**falha dizendo que falta registro**; o New Deals, esse sim, cai no endereço histórico (arquivo
ausente, ilegível ou linha com URL em branco). `fetch_unwinds()` já existe e não tem consumidor — está
lá para a rotina de unwinds nascer lendo o cadastro em vez de uma constante nova.

`athena_api.py` lê o JSON **direto** (mesmo padrão de `_ndf_pdf_set`, §169): importar `routes` dali
seria circular.

### 2. `isDead` deixa de bloquear a importação

`_api_rec_is_dead` tratava **`isCancelled` e `isDead` como a mesma coisa** — os dois faziam o registro
não ser importado (e, se já importado, virar `Canceled`/sair do arquivo). Só que `isDead` é **estado
interno da Athena** (aquele registro deixou de ser a versão viva do trade), e não "a operação não
existe". A função virou **`_api_rec_is_cancelled`** e olha **só o `isCancelled`**; quem tem `isDead =
true` é puxado normalmente.

Efeito colateral esperado: **operações que antes sumiam do import agora aparecem** nas páginas de New
Deals — se alguém estranhar um volume maior depois do deploy, é isto.

A chave `dead` do JSON de retorno dos dois pulls **foi mantida** (é o que as 4 telas leem no resumo do
import); só o conteúdo mudou. O rótulo que o usuário vê deixou de dizer "cancelados/mortos na API" e
passou a "cancelados na API", nos três idiomas.

A coluna `PRODUCT` nasceu logo depois, no mesmo dia: com uma linha só, o **FXO ficava sem endereço
cadastrado** — foi o que a mesa notou. Um `upgrade` converte o arquivo gravado antes dela (a linha
antiga vira a do NDF e os outros produtos entram do seed).

Verificado com `scripts/tests/check_api_links.py` (32 asserções — inclui a prova de que o seed
reproduz a URL histórica byte a byte, que a linha do produto ganha do curinga e que sem cadastro o
Unwinds falha em vez de bater no endpoint do New Deals) e com a seção nova de `check_cancel_remove.py` (11 asserções sobre `isCancelled` × `isDead`).
O primeiro foi testado ao contrário: com o `product` deixando de ser reescrito, oito asserções caem.

## §174 — Perna interna com SPN, Client e Tax ID vazios (e como procurar "Missing Counterparty")

**O sintoma.** Nas páginas de New Deals, as linhas cujo End Counterparty é **nome de book** (o caso
levantado foi `LM-FWDECOMBRR FXC`) vinham com **SPN, Client e Tax ID em branco — e sem badge nenhum**.
Pior que o Missing Counterparty: a linha parecia normal.

**Por que.** A busca da contraparte tentava, nesta ordem, o accronym no Reference Data e depois os
accronyms cadastrados para a Legal Entity no mapping `le-accronym`. Só que **book não tem accronym no
Reference Data** — a entidade tem (`JPMORGANBM`), o book não. Nenhum dos dois passos casava. E o badge
não aparecia porque o `missing-counterparty.js` isentava do aviso qualquer accronym cadastrado no
`le-accronym`: "é perna interna, está tudo bem" — sem checar se a resolução tinha voltado com alguma
coisa.

**A ordem agora** (`_ndf_ref_by_accronym`), ditada pela mesa:

1. accronym exato do End Counterparty no Reference Data, e o accronym sem o sufixo de entidade;
2. **sendo perna interna** — o accronym está no `le-accronym` —, a *identidade da entidade*
   (`_ndf_le_refdata`): **razão social** cadastrada em `le-spn` procurada no Reference Data pelo nome
   normalizado → accronyms da LE → **SPN** cadastrado em `le-spn` (a linha inteira do Reference Data se
   o SPN existir lá; só o SPN, se não);
3. **não sendo**, o **SPN que veio da API** — que passou a trazer o SPN da contraparte, e não mais o da
   Legal Entity (era a correção pendente citada em §147/§148);
4. nada casando, os três campos ficam vazios e a tela marca **Missing Counterparty**.

O passo 2 é o que faltava, e ele mora num cadastro novo: o mapping `le-spn` ganhou a coluna **`NAME`
(Reference Data Name)**, semeada com as razões sociais ditadas pela mesa (JPM = BANCO J.P MORGAN S.A,
MGT = JPMORGAN CHASE BANK, N.A. - SAO PAULO BRANCH, LAWTON = LAWTON MULTIMERCADO EXCLUSIVO) mais a
entidade **ATACAMA**, que entra na lista sem nome. O match é normalizado (`_pc_norm`), então
`BANCO J.P MORGAN S/A` ≡ `BANCO J.P MORGAN S.A` — a grafia da tela não precisa bater com a do arquivo.

> ⚠️ **MGT e ATACAMA ainda não existem no Reference Data.** Enquanto não existirem, a perna interna
> delas resolve só pelo SPN cadastrado em `le-spn` e, sem ele, cai em Missing Counterparty. Isso é o
> comportamento pedido — "vá cadastrar" —, não um bug.

Como o arquivo `le-spn.json` já existe nas instâncias que abriram a tela, o seed sozinho não chegaria
lá: um `upgrade` (`_le_spn_upgrade`) cria a linha que falta e preenche o nome **só quando a coluna nem
existe**. Nome apagado pela tela continua apagado — senão o cadastro brigaria com o usuário a cada
leitura.

**O accronym da API é preservado.** Resolvendo pela identidade da entidade, a coluna Accronym continua
mostrando `LM-FWDECOMBRR FXC` e não `JPMORGANBM`: trocar apagaria da tela o book que a operação
realmente tem. Vale nos três lugares — builder do NDF, builder do FXO e o re-enriquecimento dos deals
já gravados (`_generic_nd_reenrich`, que é o que conserta as linhas que já estão no arquivo do dia, sem
novo pull).

**O badge deixou de ser complacente.** Perna interna só escapa do "Missing Counterparty" quando a linha
**tem SPN**. Cadastro no `le-accronym` não é, por si, contraparte resolvida.

**Procurar por Missing Counterparty na barra de filtros.** O badge é DOM — não é dado de célula —, então
o `column().search()` do DataTables nunca o achava. O `missing-counterparty.js` ganhou um filtro próprio
(`columnSearch` + um hook em `ext.search`) que decide pela **mesma** função do badge (`isMissing`), e as
6 páginas passaram a desviar o texto para ele. Detalhe deliberado: o termo só é reconhecido a partir de
**9 caracteres** (`missing c`) — com menos, `missing` continua caindo na busca normal e achando
**Missing Index B3**, que *é* dado da célula de Status. O botão Clear Filters zera o filtro.

Verificado com `scripts/tests/check_counterparty_lookup.py` (34 asserções: a ordem inteira, as duas
armadilhas históricas — Settlement Location não vira LE e perna interna não usa o SPN da API —, o
upgrade do `le-spn` e a ligação com a tela). A parte de navegador foi exercitada no JavaScriptCore.

## §175 — Expurgo do tema: 265 arquivos que não faziam nada

O repositório carregava a demonstração inteira do template Bootstrap comprado. Saíram **265 arquivos,
89,5 mil linhas**, sem uma única mudança de comportamento.

| o quê | quantos |
|---|---|
| páginas de demo em `templates/pages/` | 170 |
| JS de página órfão em `static/js/` (incl. `js/maps/`) | 75 |
| `partials/horizontal-nav.html` + `layouts/horizontal.html` | 2 |
| site de documentação do tema em `Docs/` (10 HTML + assets) | 18 |

Famílias apagadas: `ui-*` (28) · `charts-*`/`chartjs-*` (26) · `tables-*` (17) · `ecommerce-*` (11) ·
`sidebar-*` (11) · `crm-*` (10) · `form-*` (9) · `auth-*` (8) · `email-*` (8) · `misc-*` (8) ·
`pages-*` (8) · `layouts-*` (5) · `icons-*` (3) · `topbar-*` (3) · `users-*` (3) · `invoice*` (3) ·
`maps-*` (2) · `api-keys` · `maintenance` · `social-feed`. Mais as **quatro confirmações antigas**
(`ndf-comm_strike_usd`, `ndf-comm_strike_brl`, `ndf-comm_platts_strike_usd`, `opt-comm_strike_usd`),
substituídas pelas de `templates/confirmations/`.

**Por que ninguém tinha percebido.** `@blueprint.route('/<template>')` renderiza **qualquer** arquivo em
`pages/`, então "não tem rota no código" não provava nada — `new_deals-ndf-vanilla.html` também não tem.
O critério que funcionou foi **alcançabilidade**: raiz = o que é citado por código (`.py`, `.js`,
`layouts/`, `partials/`), mais o fecho pelos links entre páginas vivas. Duas exclusões deliberadas na
lista de raízes, e são elas que explicam o resultado:

- **`partials/horizontal-nav.html`** — é o menu de demonstração do tema, com ~170 links, e era
  carregado por **uma** página: `layouts-horizontal.html`, a demo do próprio layout. Contá-lo como raiz
  fazia todo o tema parecer vivo. Ele e o `layouts/horizontal.html` foram junto; o menu da aplicação é
  só o `partials/sidenav.html`.
- **`static/data/translations/*.json`** — têm chaves herdadas daquele menu (`ui-buttons`, `crm-leads`…).
  Chave de tradução não é uso. As chaves órfãs ficaram: são inertes e mexer nelas é outro assunto.

**O que ficou de propósito:** os quatro `error-4xx.html` (superfície de erro da aplicação, mesmo os que
nenhum handler usa hoje), `Docs/SQL_Injection_Prevention_Cheat_Sheet.md` e os dois `.pptx`, e todo o
SCSS — o CSS compilado é um bundle só, e podar o SCSS por página é outro trabalho.

**Como foi conferido.** Os **72 links do `sidenav.html`** foram batidos um a um, com sessão autenticada,
antes e depois: **exatamente os mesmos 24 não-200** (as páginas de Unwinds, DCE, Regulatory e `/cgd`,
que ainda não existem — este é o retrato de hoje, e serve de linha de base para o próximo expurgo).
`/dashboard`, `/mapping`, `/users-profile`, `/page-access`, `/reference-data` e
`/pending-confirmation` seguem 200; `/ui-buttons` e `/layouts-horizontal` agora caem no
`error-404.html`, que renderiza (404, não 500). A suíte de `scripts/tests/` inteira passa. Também
varri o repositório inteiro atrás de referência remanescente a arquivo apagado — a única era o
`Docs/layouts.html`, que foi apagado junto.

## §176 — O amend da API passa a acompanhar a contraparte (pelo Deal ID)

A contraparte de um deal congelava na **primeira** importação. Duas travas independentes, e as duas
tinham de sair:

**1. `SPN`, `Client` e `Tax ID` estavam em `_ND_AMEND_SKIP`.** O amend simplesmente não os comparava.
A justificativa original era boa — esses três são **enriquecimento nosso** (Reference Data), não campo
que a API mande — mas o efeito não era: operação rebookada para outra contraparte ficava para sempre
com o nome antigo na tela, e a linha importada sem contraparte nunca ganhava a que a resolução passou
a achar.

**2. A chave do arquivo do dia é `(Deal, Client)`.** Se o Client muda, a chave não casa e o deal entra
como **linha nova**: a operação passa a aparecer **duas vezes** — a velha com a contraparte antiga, a
nova com a atual —, nenhuma das duas marcada como Amend. Isso é pior que o congelamento, porque
duplica o que vai para registro.

Agora, sem match pela chave, procura-se **pelo Deal ID** (`_nd_amend_find`) — e **só quando ele é único
no arquivo**. O mesmo Deal pode ter **duas pernas** gravadas (é o que o cancelamento por Deal já
trata); nesse caso não há como saber qual delas a API está amendando, e o deal entra como novo, que é
o comportamento antigo. Adivinhar aqui escreveria a contraparte de uma perna na outra.

### O contrapeso: quem já está Success não volta para a fila à toa

Comparar os três campos, sozinho, teria um efeito colateral feio: no primeiro pull depois de §174 —
quando a perna interna passou a resolver SPN/Client/Tax ID que vinham vazios — **todo deal interno já
registrado cairia de Success para Amend**, de uma vez.

A régua é o **accronym**, que é quem identifica a contraparte (nunca o SPN nem a settlement location,
§147/§148). Em `_nd_amend_is_economic`:

| mudou | accronym | resultado |
|---|---|---|
| SPN / Client / Tax ID | **igual** | célula destacada, **Status preservado** — mudou a nossa resolução, não o negócio |
| SPN / Client / Tax ID | mudou, mesma entidade | idem (mesma régua do `Acronym`) |
| SPN / Client / Tax ID | mudou de entidade | **Amend** — a ponta do negócio é outra |

### Na tela

`AMEND_FIELD_COLS` não tinha `SPN`, `Client` nem `TaxID` — as três colunas da contraparte não podiam
sequer ser destacadas. Foram acrescentadas nas quatro páginas alimentadas pela API (Vanilla, Other
Publisher, FWD Start e Opt FXO), com os índices de cada uma (9/11/12 nos NDFs, 8/10/11 no FXO).

Verificado com `scripts/tests/check_amend_counterparty.py` (34 asserções). Duas valem menção:

- a seção **7 roda o caminho real** — `_generic_nd_persist_new_deals` lendo e gravando um day file, com
  o diretório do produto desviado para um `tempfile`: importa a linha sem contraparte, reimporta com a
  contraparte resolvida e prova que o arquivo fica com **uma** linha, com os campos gravados, as três
  colunas em `AmendChanged` e o `Success` intacto;
- a seção **6 confere `AMEND_FIELD_COLS` contra `COL_TO_JSON_FIELD` campo a campo, nas quatro páginas**
  — índice trocado pinta a coluna errada, e é exatamente a classe de erro que já corrompeu dado nesta
  tela duas vezes (§132). Os índices que já existiam estavam todos certos.

O script foi testado ao contrário: devolvendo os três campos ao `_ND_AMEND_SKIP`, 11 asserções caem.

## §177 — Tipo de Cotação e Fonte de Informação viram cadastro

Três literais decidiam campos que vão para a B3:

| arquivo | campo | era |
|---|---|---|
| Termo (NDF Comm) | Tipo de Cotação | `'F' if is_fixed else 'A'` |
| Termo (NDF Comm) | Fonte de Informação | `'340' if is_fixed else '358'` |
| Opção (Opt Comm) | Tipo de Cotação | `'5'`, fixo |

`is_fixed` era só o flag **Fixed Quote** do mapping Commodities × B3 — ou seja, a commodity escolhia
entre **dois** valores, e qualquer terceiro (uma cotação de fechamento, um ajuste diferente) exigia
alterar código e **reiniciar o servidor**, que é o que a equipe não faz sozinha na instância.

Agora são três colunas do mesmo mapping: **`QUOTE TYPE NDF`**, **`QUOTE TYPE OPT`** e
**`INFO SOURCE`**.

**São duas colunas de tipo de cotação porque os dois layouts têm domínios diferentes** — o de Termo usa
letra (`A`/`F`), o de Opção usa número (`5`) — e a mesma commodity é negociada nos dois. Uma coluna só
mandaria `A` para o arquivo de Opção. A coluna guarda o **código do layout**, o que literalmente vai no
arquivo; o nome (AJUSTE, FECHAMENTO…) fica em Notes. Foi decisão da mesa, e é o que evita eu ter de
adivinhar a tabela nome → código de cada layout.

**Coluna vazia — ou subjacente sem linha nenhuma — devolve exatamente o valor histórico.** É o que
`_b3_quote_cfg` faz, e é o que o **seed escreve linha a linha**: cadastro e código dizem a mesma coisa
hoje. O `upgrade` preenche as três colunas nos arquivos já gravados (com `setdefault`, então coluna que
a tela gravou vazia continua vazia).

### Achar a linha do subjacente não é comparação de igualdade

O deal traz o Ativo Subjacente já montado (`HOZ6`), e a coluna B3 CODE guarda um **padrão** nas linhas
PREFIX (`HO"MY"`, `C_"MY"`, `KO"MY"BNMK` — §164). `_b3_code_matches` compara literal nas FIXED e
prefixo + sufixo nas PREFIX, exigindo ao menos um caractere de mês/ano no meio — senão `HO` casaria
com `HO` pelado. Isso é novo: o `FIXED_UNDERLYINGS` antigo era um `set` de igualdade, e por isso só
funcionava para as linhas FIXED (todos os fixed-quote são FIXED, então nunca deu problema).

### A regra tem duas cópias, e isso é deliberado

O arquivo Conecta é montado **nos dois lados** — no navegador (o preview do duplo clique e o download)
e no servidor (o envio) —, então a regra existe em Python e em JS. Para não virar **cinco** cópias (uma
por página), o lado do navegador é um arquivo compartilhado: **`static/js/b3-quote-config.js`**
(`B3Quote.load()` / `B3Quote.cfg(underlying)`). Foi exatamente a cópia-por-página que fez as duas
versões do código B3 divergirem em §164.

Junto saiu a lista literal `_FIXED_UND` que cada uma das quatro páginas de NDF carregava como fallback
— o helper e o cadastro cobrem o caso.

Verificado com `scripts/tests/check_quote_type.py` (48 asserções): o casamento padrão × código, o
default histórico em toda combinação (coluna vazia, linha sem cadastro, subjacente inexistente), o seed
e o upgrade, a ausência dos literais nos seis consumidores e — na seção 5, no JavaScriptCore — a
**paridade das duas cópias**. Como `check_boxparse.py`, essa seção não roda no Windows da equipe; as
outras quatro rodam.

> ⚠️ O `commodities-b3.json` versionado **não foi regenerado**: ele tem 31 linhas contra as 30 do seed,
> ou seja, já carrega edição da equipe. Quem preenche as colunas nele é o `upgrade`, na primeira
> leitura.

## §178 — CO1-2: quantas Datas de Verificação são do segundo futuro

O ticker `CO1-2` (Brent rolling) não sai como código fixo na confirmação: sai como uma **frase** que
diz, das Datas de Verificação, quais valem o **primeiro** futuro e quais valem o **segundo**. A regra é
do calendário do Brent:

| última Data de Verificação em | datas do 2º futuro |
|---|---|
| **dezembro** | as **duas** últimas (última e penúltima) |
| qualquer outro mês | só a **última** |

`_conf_co12_text` aplicava a regra de dezembro **o ano inteiro**. Em qualquer outro mês a penúltima
data saía apontada para o segundo futuro — **um dia a mais de rolagem do que a operação tem**, num
documento que a contraparte assina.

Quem decide o mês é a **última** Data de Verificação (a Data Final de Verificação de Mercadoria), que é
o dia em que a rolagem acontece. Uma janela que atravessa a virada do ano — verificações em dezembro
terminando em janeiro — cai na regra de janeiro, que é o mês do dia que rola. Fica registrado porque é
a única leitura em que "as datas de verificação são de dezembro" fica ambíguo.

O texto de dezembro **não mudou uma vírgula** (o teste fixa a frase inteira). Fora de dezembro a frase
passa ao singular: *"…e para a Data de Verificação em 31/08/2026, significa COV6"*.

Os meses dos dois contratos continuam saindo do **settlement** (+1 e +2, com virada de ano), e o corte
continua andando em **dias úteis ANBIMA** — feriado no dia anterior empurra as duas pontas.

**A confirmação de Opção passou a usar a mesma função.** A regra é do ativo, não do produto, e antes só
o Termo a tinha; a Opção imprimia o literal `CO1-2`. O documento próprio do CO1-2 em opção (família
`co1-2`) continua **pendente de template**, então na prática a frase só aparece quando ele existir — mas
já nasce certa, em vez de a regra ganhar uma terceira cópia.

Verificado com `scripts/tests/check_co12_roll.py` (20 asserções, calendário de feriados stub): a frase
de dezembro byte a byte, o singular dos demais meses, o recuo por fim de semana e por feriado, os
futuros vindos do settlement com virada de ano, e o `CO1-2` cru quando falta data. Testado ao
contrário — voltando a regra para dois dias sempre, 8 asserções caem.

## §179 — Tema claro/escuro: o toggle trocava 1 dos 3 atributos

Sintoma: com o menu **fixado (pin)**, trocar de escuro para claro deixava a **sidebar no escuro** e o
**logo do topbar** no logo do tema anterior — e a troca "travava" por um instante. Reportado como
acontecendo em páginas que são **subitem de um ramo** (`Live Position > NDF`) e não nas diretas.

O tema não é um atributo, são **três**, e cada um pinta uma parte:

| atributo | pinta | onde a regra mora |
|---|---|---|
| `data-bs-theme` | o corpo da página (e o fundo da sidebar) | `visual-refresh.css` |
| `data-menu-color` | o tema da **sidebar** e qual logo dela aparece | `scss/config/_theme-*.scss`, `structure/_layout.scss` |
| `data-topbar-color` | o tema do **topbar** e qual logo dele aparece | `structure/_topbar.scss` |

`initThemeToggle` (`visual-refresh.js`) escrevia **só `data-bs-theme`**. Quem realinha os três é o
`config.js` (`config.topbar.color = config.menu.color = config.theme`), e ele **só roda no load da
página**. Daí a assimetria que parecia de página: clicar num item **folha** do menu navega e conserta
sozinho; clicar num item **com ramificação** só abre o submenu — o drill-down (§ sidenav-drilldown)
não recarrega nada —, então o estado quebrado fica à vista. O `pin` entra só porque mantém a sidebar
visível o tempo todo.

Três correções:

1. **o toggle troca os três**, delegando ao `LayoutCustomizer.changeTheme` do `app.js` (que já fazia
   certo) — `window.layoutCustomizer` passou a ser exposto no `DOMContentLoaded` justamente para isso.
   O caminho de fallback (instância ainda não pronta) escreve os três atributos e persiste
   `theme`/`menu.color`/`topbar.color`.
2. **o resize não regrava mais o config inteiro.** `_adjustLayout` chamava `changeLeftbarSize(size)`
   com `save = true`, e `setSwitchFromConfig()` persiste a cópia de config que a instância tirou **no
   load**. Trocar o tema por fora dessa instância e depois redimensionar a janela gravava o tema
   **antigo** de volta — ele "voltava sozinho" na página seguinte. O ramo em questão só restaura o
   tamanho **já guardado**, então persistir ali não acrescentava nada.
3. **as travadas**: claro↔escuro reavalia fundo/borda/texto de quase todo elemento, e boa parte tem
   `transition` de cor — a troca disparava centenas de animações simultâneas. O toggle agora põe
   `html.vr-theme-switching` por ~60 ms, e a regra em `visual-refresh.css` zera `transition` enquanto
   ela existe.

Verificado com `scripts/tests/check_theme_toggle.py` (22 asserções): os três atributos nos dois
caminhos do toggle, a delegação ao `LayoutCustomizer`, nenhum ramo do resize persistindo, a classe de
supressão conferida **dos dois lados** (JS e CSS) e a prova de que o CSS compilado realmente depende de
`data-menu-color`/`data-topbar-color` — se um dia não depender, o teste avisa em vez de deixar zelo
morto no código. Testado ao contrário: voltando o toggle a escrever um atributo só, 3 asserções caem.

**Cache do navegador**: os três arquivos são estáticos e entram com `?v=` em `head-css.html` /
`footer-scripts.html`. A versão dos três foi subida para `20260804a` no mesmo commit — sem isso o
navegador serviria a cópia antiga e a correção só apareceria depois de um Ctrl+F5. **Quem mexer nesses
arquivos tem de subir o `?v=` junto**, senão a equipe testa a versão velha e reporta que não funcionou.

## §180 — Pay/Rec: um botão de ação só, a dropzone decide a fonte

A toolbar tinha **dois** botões de execução — `Import from folder` e `Run` — e o operador escolhia a
fonte pelo botão. Sobrou o **Run**, e quem decide agora é a dropzone:

| dropzone | o que o Run faz | `mode` no POST |
|---|---|---|
| com arquivo(s) anexado(s) | roda com **esses** arquivos | `manual` |
| vazia | varre a pasta de insumos (o antigo Import) | `auto` |

A regra **já existia no servidor** e não mudou: `_gather_sources` (`recon_payrec.py`) usa os anexos só
com `mode == 'manual' and files`, e qualquer outro caso cai em `_INPUT_BASE`. Ou seja, são **duas
cópias** da mesma decisão — o navegador escolhendo o `mode` e o servidor escolhendo a fonte. Mandar o
`mode` certo daqui não é redundância: é o que mantém as duas dizendo a mesma coisa, e é o que decide se
o `clearDzFiles()` pós-run faz sentido (limpar a dropzone depois de uma rodada que nem usou os anexos
apagaria o trabalho do operador).

Com dois botões dava para ver qual caminho seria tomado; com um só, não — então o `title` do Run é
reescrito a cada mudança da dropzone (*"Rodar com os arquivos da pasta Pay/Rec"* × *"Rodar com o(s)
arquivo(s) anexado(s)"*), e o texto do estado vazio passou a dizer as duas coisas. A chave i18n
`pr-import` foi removida dos três arquivos de tradução junto com o botão, em vez de virar chave órfã.

Verificado com `scripts/tests/check_payrec_run.py` (22 asserções). A seção 1 é funcional de verdade —
chama `_gather_sources` com `_INPUT_BASE` apontando para um tempfile e prova que `manual` sem anexo, e
com `files=None`, lê a pasta; as demais fixam que sobrou um botão de ação, que nenhum call site passa
modo fixo e que a chave i18n não ficou órfã. O `?v=` do JS da página subiu para `20260805a` (§179).

## §181 — NDF Summary: os cards de reconciliação ganham a luz de fundo do Monitor

Os quatro cards do topo (Vanilla · Other Publisher · T+0 · Total) já diziam `OK`/`Check` num badge, mas
o card em si era neutro: só o discrepante levava um anel âmbar fino por dentro. Agora o **card inteiro
flutua sobre uma luz colorida** — verde quando B3 e Interno batem, âmbar quando não batem — que é a
mesma receita do `ndm-card--prog` do New Deals Monitor: sombra em **camadas** (contato + média +
halo largo), não um contorno chapado. É isso que faz o card parecer iluminado por baixo em vez de
contornado.

A cor sai de `--ops-glow` (`"r, g, b"`), escrita pelas classes de estado, e a receita do `box-shadow`
existe **uma vez só** servindo aos dois casos:

| estado | classe no card | `--ops-glow` |
|---|---|---|
| B3 = Interno | `is-ok` | `22, 163, 74` (#16a34a) |
| divergente | `is-check` (+ `is-unmatched`) | `245, 158, 11` (#f59e0b) |

Três armadilhas, todas silenciosas (nenhuma dá erro no console):

- **`box-shadow` não se soma entre regras** — a última declaração vence a lista inteira. O anel âmbar
  do card divergente, que antes era um `box-shadow` próprio, teria apagado o halo; virou a variável
  `--ops-ring` (default: um `0 0 0 0` transparente) e entra como **primeiro item** da mesma lista, o
  que também o mantém desenhado por cima. O card Total tem seu anel mais grosso pela mesma variável.
- **A ordem do `:hover`.** `.ops-widget:hover` troca o `box-shadow` por um cinza genérico; a regra
  colorida de hover **tem de vir depois** dela no arquivo, senão o halo some justamente ao passar o
  mouse — o jeito mais fácil de não perceber.
- **O claro pesa mais que o escuro**, ao contrário do resto da página. Luz colorida sobre fundo branco
  se dissolve; sobre fundo escuro ela já contrasta sozinha e passar do ponto vira néon. Por isso as
  três camadas do tema claro (`.20 / .34 / .22`) são maiores que as do `[data-bs-theme=dark]`
  (`.15 / .25 / .16`) — e o verde é o **#16a34a do badge**, não o #1a8a4a do gradiente da marca, que no
  branco lê como cinza-esverdeado.

As classes vêm do JS no **mesmo ponto** que escreve o badge, do mesmo `ok`: qualquer outra fonte
deixaria halo e texto contando histórias diferentes na primeira vez que a regra de conciliação mudasse.
Sem classe nenhuma (antes do `/api/ndf-summary/data` responder) o card fica neutro de propósito — luz
verde em card ainda sem número é mentira.

Verificado com `scripts/tests/check_summary_glow.py` (21 asserções), que prende exatamente as três
armadilhas: o nome das classes nos dois lados, a ordem do `:hover` contra `.ops-widget:hover` e a
comparação camada a camada claro > escuro. CSS e JS moram no template, então **não há `?v=` para subir**
— mas a instância da equipe roda com o reloader desligado e cacheia templates: precisa de **restart**.

## §182 — Other Products Summary › Trade Level: a linha de SWAP

O Trade Level nascia vazio (`'trade': []` no `api_ops_data`). Agora ele monta uma linha por **swap
liquidando na data**, e a ordem das colunas passou a ser a pedida, com **LOB** nova:

`Status · LOB · Counterparty · Internal ID · B3 ID · Product · Type · Settlement · Settlement B3 ·
Tax Income · Difference`

### O join

A linha nasce de **cinco arquivos que não se conhecem**; tudo é join por código, e cada seta é um lugar
onde o número sai errado sem ninguém perceber (ele aparece, só não é o certo):

| campo | de onde vem | chave |
|---|---|---|
| **B3 ID** | Operations B3 › `Título` | — |
| **LOB** | Operations B3 › coluna derivada `Type` (= Código Identificador da posição) | Título |
| **Settlement B3** | Σ `Valor` do Operations B3 | Título |
| **Internal ID** | Swap Athena › `Kapital ID` | Título = `CETIP ID` |
| **Counterparty** | Swap Athena › `CounterParty` | Título = `CETIP ID` |
| **Settlement** | Σ `Amount` do OTM Settlements | Internal ID = `Trade Id` |
| **Type** | Swap Events › `PARTE / Indexador` e `CONTRAPARTE / Indexador` | Título = `Código do Contrato` |
| **Tax Income** | calculado (ver abaixo) | — |

**Quais linhas são swap liquidando**: `Tipo Título = SWAP` **e** `Tipo Operação` registrado em
`swap-b3-events` (as três variações de PAGAMENTO DE DIF./PRÊMIO). `RESGATE` e `RESGATE ANTECIPADO`
ficam de fora de propósito — são vencimento, não pagamento de diferencial.

**Dedup**: o mesmo swap chega ao Operations B3 **uma vez por Tipo Operação** (amortização, juros,
prêmio). A linha é UMA por Título — mas o **Settlement B3 soma todas as linhas daquele Título**,
inclusive as que o filtro descartou: o que se concilia é o caixa do dia, não o evento.

**Type**: `VCP` quando **qualquer uma** das duas pontas do evento indexa em VCP; senão `Calculado`.

**Counterparty**: o nome vem do **Athena**, não do Operations B3. O `Nome Simplificado` do B3
(`INTRAGMGTFDO`) é apelido de conta e nunca casaria com "BANCO …" nem com as entidades JPM no cadastro
de IR — ele fica só como último recurso, para a linha não sair anônima.

### O IR

Porte da fórmula da planilha de avisos, na mesma ordem: exceção por cliente → só há IR quando **quem
recebe é a contraparte** → tabela regressiva por prazo. Dois pontos que não são transcrição:

- **O prazo é do TRADE.** `Data operação termo` da posição DPOSICAO-SWAP e, só quando ela vem vazia,
  `Data início` — que é exatamente o `XLOOKUP` em Z:Z com fallback para L:L. Num forward start, usar a
  data de início encurtaria o prazo e **subiria** a alíquota.
- **A planilha tem um vão em 721.** `IF(E12>721;15%)` deixa o prazo 721 exato sem resposta (devolve
  FALSE). A tabela por faixas fecha isso: acima da última faixa registrada vale a linha sem limite.

Célula **vazia ≠ 0,00**: sem prazo, sem cliente ou sem direção o IR sai em branco, que é pedido de
conferência. Imprimir 0% ali seria afirmar isenção que ninguém verificou.

**`_ops_cpty_receives` é a única inferência do conjunto** e está marcada como tal: preferimos o texto da
coluna `Direction` do Athena (é o que a planilha lê em `O12="Counterparty receives"`); sem texto
conhecido, sobra o **sinal** do settlement — negativo é o banco pagando, logo a contraparte recebendo,
que é a convenção do Resultado Bruto entre parênteses no aviso. Quando o arquivo real do Athena estiver
disponível, **conferir o vocabulário de `Direction`** e, se for outro, é aqui que se ajusta.

### Cadastros novos (nada de de-para no código)

Três abas novas no `/mapping`, seeds reproduzindo exatamente o que estava na fórmula:
`swap-b3-events` (os Tipo Operação que contam), `swap-ir-client` (as exceções — `Starts with` existe por
causa do `LEFT(A12;5)="BANCO"`) e `swap-ir-term` (as faixas).

### A ordem das colunas vive em TRÊS listas posicionais

Os `<th>` do template, o `rowMaker` do JS e `_OPS_TRADE_COLS` no backend. Mexer numa só desloca a tabela
inteira **sem erro nenhum no console** — é o mesmo tipo de armadilha do §132 (New Deals NDF). A seção 4
do `check_ops_trade_swap.py` compara as três.

Linha derivada renderiza como **texto**, não `<input>`: ela é recalculada a cada troca de data, então um
valor digitado sumiria sem aviso no próximo load. As linhas do Add row seguem editáveis.

### Verificação e limites

`scripts/tests/check_ops_trade_swap.py` (53 asserções). A seção 1 monta **as cinco fontes** num tempfile
e chama `_ops_swap_trade_rows` de verdade, conferindo campo a campo — inclui o swap que chega duas vezes,
o RESGATE que não pode entrar, o TER com o mesmo Tipo Operação, o swap sem contraparte no Athena e o
registro de posição no formato **posicional real de 146 campos**. Os cadastros são lidos **do seed**, não
do arquivo: quem editar a tabela de IR pela tela não faz o teste falhar, e o seed fica fixado contra a
fórmula. Validado reintroduzindo o dedup removido, o vão do 721 e uma troca de colunas no cabeçalho.

**Limite honesto**: nesta máquina só existe o JSON do Operations B3; Athena, Events e OTM não têm arquivo
local. O join está provado pelo teste sintético e pela chamada real do endpoint (que devolve as duas
linhas de swap do dia 27/07 com LOB e Type corretos), **não** por um dia de produção completo. O primeiro
dia com as cinco fontes deve ser conferido contra a planilha.

Falta ainda (partes seguintes): Option, NDF Commodities e COE no Trade Level, o Settlement Summary
(continua `[]`) e a página **Settlement Advice**, que segue como link morto no sidenav.

> O Settlement Summary saiu do `[]` no §183. A coluna LOB do Trade Level também mudou lá: passou a
> mostrar o **token** (`CEM`), não o Código Identificador inteiro (`CEM-2026-3184`).

---

## §183 — Other Products Summary › Settlement Summary: o porte do NDF

A tabela de cima da página existia com cabeçalho e `dtSummary`, mas o endpoint devolvia `'summary': []`
literal — nada nunca a alimentou. Agora ela é o **porte do Settlement Summary do NDF**.

### O que foi portado, e por que não foi copiado

Receive, Pay, Settlement Net, Direction, Account e Observation saem das **mesmas funções** que a página de
NDF usa — `_ndfsum_net_type`, `_ndfsum_account_fmt`, `_ndfsum_obs_auto`, `_ndfsum_refdata_spn`. Recopiar
a regra aqui criaria a segunda cópia de um cálculo de dinheiro, e duas cópias divergem em silêncio: o
número continua aparecendo na tela, só deixa de ser o mesmo número das duas páginas. A seção 9 do teste
prende isso lendo o corpo de `_opssum_rows`.

As regras, na ordem em que rodam:

1. **Net type** vem do Reference Data: nome da contraparte → SPN (`RefData.json`) → registro do
   CounterpartyDetails → `NET.value` aprovado. Sem cadastro, **Total Net** — o mesmo default seguro da
   recon, não "sem netting".
2. **Caixa por trade líquido de IR**: `settlement − tax` quando positivo, `settlement + tax` quando
   negativo. O imposto retido sempre **encolhe** o que se movimenta, seja qual for o sinal.
3. `receive` = Σ positivos, `pay` = Σ negativos. **Total Net** colapsa os dois na ponta do resultado
   final; **Pay/Rec** mantém as duas.
4. **Direction** é a visão do BANCO (`RECEIVE` se o total ≥ 0).
5. **Account** cruza: os defaults do Reference Data são a visão da CONTRAPARTE, então banco `PAY` →
   `DEFAULT_RECEIVE` do cliente e banco `RECEIVE` → `DEFAULT_PAY`. Inverter isso imprime a conta errada
   num aviso de pagamento — e o formato `BCO: 341 | AG: 0910 | CC: 967` continua parecendo certo.
6. **Observation**: a digitada vence; sem ela, a classificação automática Internal/External (banco 376 /
   JPMorgan = interno) das contas default.

### A única diferença deliberada: a linha não é a contraparte

No NDF a linha é a **contraparte**. Aqui é **contraparte × LOB × produto**, porque a página cobre vários
produtos e as colunas Product e LOB existem justamente para separá-los. Consequência a entender antes de
estranhar o número: um cliente **Total Net** com swap e opção sai em **duas linhas** — o net é por
produto, não por cliente, que é o recorte do aviso de liquidação.

Ordem das colunas: `Status · Counterparty · LOB · Product · Receive · Pay · Settlement Net · Direction ·
Account · Observation`. O `<th>` chama a coluna de "Settlement Net", o payload chama o campo de
`net_type` — é o **tipo** de net, não um valor; nomes diferentes de propósito.

### A fonte é o Trade Level, não uma segunda leitura

`_opssum_rows` soma as linhas **já montadas** por `_ops_swap_trade_rows`, pelos campos privados
`_settle_n`/`_tax_n` (números crus, removidos do payload antes do `jsonify`). Reler os arquivos deixaria
as duas tabelas da mesma página livres para se contradizerem; e reconverter o texto formatado para float
seria pior — perde o branco de "não deu para calcular", que viraria zero na soma. Linha sem contraparte
ou sem settlement **não entra**: não há o que liquidar, e entrar com zero inventaria um aviso.

Enquanto só o SWAP alimenta o Trade Level, só o SWAP aparece aqui. Option, NDF Commodities e COE entram
sozinhas assim que as respectivas linhas do Trade Level existirem — não há nada a mexer nesta tabela.

### LOB passou a ser o token

`'lob': _fcst_lob(_opb3_tipo_for(rec, tipo_maps)) or ''`. A coluna Type do Operations B3 carrega o Código
Identificador inteiro (`CEM-2026-3184`); a LOB é o **token** dentro dele (`EDG` · `CEM` · `CEMHYB`), que é
o vocabulário do Accrual e do Forecast. Duas colunas chamadas LOB na mesma página falando línguas
diferentes seria o defeito. Identificador sem token reconhecido deixa a célula **vazia** (regra do
`_fcst_lob`): pede cadastro em vez de rotular a linha com uma LOB inventada.

`COMM` ainda não sai daqui — swap não tem LOB de commodities. Ela virá com os produtos de commodities.
E `CEMHYB` fica como valor próprio, não colapsa em `CEM`: os híbridos são LOB separada no resto do
sistema, e juntá-los aqui os esconderia.

### O que a tabela persiste

Só a observação digitada, num overlay do dia ao lado dos JSONs do batch
(`other-products-summary_YYYYMMDD.json`), chaveado por contraparte × LOB × produto **normalizado** (caixa,
acento e espaço duplo) — sem isso a observação se perderia no dia em que o nome viesse grafado diferente.
Endpoint `POST /api/other-products-summary/observation`; texto vazio limpa e a linha volta à observação
automática. O resto da linha é derivado e renderiza como **texto**, não `<input>`: seria recalculado no
próximo load e o valor digitado sumiria sem aviso.

### Verificação

`scripts/tests/check_ops_summary.py` (38 asserções, 9 seções). RefData e CounterpartyDetails são stubs em
memória — o teste não depende do cadastro real nem o suja. Validado reintroduzindo três defeitos: o sinal
do IR trocado (`s + t` quando positivo), o cruzamento da conta invertido e a LOB voltando a ser o
identificador — os três falham. Além do teste, o endpoint foi chamado de verdade pelo `test_client` com
um OTM sintético e devolveu a linha netada (`SUZANO SA · CEM · SWAP · PAY · -1.000,00`).

**Limite honesto**: `Account` e `Observation` saem vazias enquanto a contraparte não estiver no
`RefData.json` **com** registro no CounterpartyDetails — foi o caso nesta máquina. A cadeia
nome → SPN → net type → conta ainda não foi exercida contra o cadastro de produção.

---

## §184 — Other Products › Swap › Settlement Advice: a página existe

O link estava no sidenav desde sempre apontando para `#other-products-swap-settlement-advice` — uma
**âncora morta**: sem rota, sem template, sem endpoint. Clicar não fazia nada. Agora é uma página de
verdade, e a âncora saiu do menu.

### É o visualizador genérico, não uma página nova

Mesma máquina das irmãs de Swap (Athena · Events · VCP): `live-position-swap-characteristics.js`, escolhido
pelo atributo `data-api` do template. Vêm de graça o date picker, o smart filter por coluna, o show/hide de
colunas, o export (Copy/CSV/Excel/Print) e a linha de filtros. O backend só devolve
`{columns, rows, widgets, ref_date_fmt}`.

**Armadilha do reuso**: o JS procura por `id="swapchar-page"` e `id="swapchar-table"`. Renomear qualquer um
dos dois deixa a página **em branco sem erro no console** — o teste prende os três nomes.

### As colunas e de onde saem

`Cliente · LOB · Número de Contrato · Data Operação · Vencimento · Prazo · Valor Base Original ·
Ativo Banco · Curva Banco · Ativo Cliente · Curva Cliente · Resultado Bruto · Alíquota IR · Valor IR ·
Valor Líquido` — a lista da planilha, com LOB na posição 2.

| coluna | fonte |
|---|---|
| Cliente | Athena (`CounterParty`); sem casamento, o Nome Simplificado do B3 |
| LOB | token do Código Identificador da posição (§183) |
| Número de Contrato | `Título` do Operations B3 |
| Data Operação | posição: **Data operação termo**, e só se vazia a Data início |
| Vencimento · Prazo | posição (Data vencimento) e a diferença em dias |
| Valor Base Original · Ativo Banco · Ativo Cliente | Eventos (`Valor Base`, `PARTE / Indexador`, `CONTRAPARTE / Indexador`) |
| Curva Banco · Curva Cliente · Resultado Bruto | Athena (`Owner curve`, `Counterparty curve`, `BRL Net Amount`) |
| Alíquota IR · Valor IR | `_ops_swap_ir_rate` — a **mesma** tabela do Trade Level |
| Valor Líquido | bruto menos o IR, que sempre **encolhe** o caixa |

Os três valores em dinheiro saem do **mesmo registro do Athena** (o arquivo é literalmente o
`BrazilOnshoreSettlementsWarningFile`, o aviso de liquidação), então a linha fecha sozinha: as duas curvas e
o resultado vêm da mesma fonte. Ativo e Valor Base vêm dos eventos porque o Athena não os traz.

### O universo agora tem UMA implementação

"Quais swaps liquidam hoje" (Tipo Título = SWAP, Tipo Operação registrado em `swap-b3-events`, dedup por
Título) saiu de dentro de `_ops_swap_trade_rows` e virou **`_ops_swap_settling(opb3)`**, usada pelas duas
telas. Duplicar a regra deixaria o Trade Level mostrando um swap que o aviso não mostra — e ninguém veria
erro nenhum. O teste confere que existe **uma** `def _ops_swap_settling` e que as duas funções a chamam.

### A data que mais importa

**Data Operação é a do trade, não a do início.** Um forward start tem `Data operação termo` preenchida e
`Data início` bem depois; usar a de início encurta o prazo e **sobe** a alíquota — retém IR a mais do
cliente, num documento que ele recebe. O teste fixa isso com um forward start de 926 dias (15%) e um swap
sem termo de 35 dias (22,5%).

**Branco não é zero.** Sem prazo na posição não dá para escolher a faixa; a alíquota, o Valor IR e o Valor
Líquido saem vazios — pedido de conferência, não afirmação de isenção.

### Verificação

`scripts/tests/check_swap_advice.py` (39 asserções, 6 seções): as quatro fontes num tempfile, incluindo o
registro de posição no formato **posicional real de 146 campos**, e `_swadv_rows` chamada de verdade. Além
do teste, a rota (200) e o endpoint foram exercidos pelo `test_client`.

**Limites honestos**, os dois que precisam de conferência contra a planilha real no primeiro dia:

1. `Resultado Bruto` é o `BRL Net Amount` do Athena. Se a planilha calcula Curva Cliente − Curva Banco e as
   duas contas divergirem, é aqui que aparece.
2. Quando a coluna `Direction` do Athena vem **vazia**, a direção cai no **sinal** do Resultado Bruto
   (negativo = o banco paga), assumindo a mesma convenção do settlement. O vocabulário real de `Direction`
   ainda não foi visto.

Falta ainda: o botão que **gera** o aviso (a página hoje só mostra), e a Settlement Advice de **Option**,
que segue como âncora morta no sidenav.

---

## §185 — Other Products Summary: o vazio agora se explica

Relato: "não aponta nada nem no Trade Level nem no Settlement Summary". Reproduzido em um minuto — e a
causa não era nenhuma das duas tabelas.

### O que estava acontecendo

A página abre em **hoje**. As duas tabelas leem o batch de liquidação **daquela data**
(`operations-b3_YYYYMMDD.json` e companhia), **sem walk-back**: a data de liquidação é uma data real, e
mostrar o movimento de outro dia sob o rótulo de hoje seria pior do que mostrar nada.

Os **widgets do topo, não**: eles leem a posição *mais recente disponível* (`_forecast_latest_ref`, com
walk-back de pregões). Então num dia sem batch importado a tela se contradizia em silêncio — o card dizia
"2 swaps liquidando", as duas tabelas ficavam vazias, e nada na página explicava a diferença. Parecia
código quebrado; era arquivo ausente.

Não é bug de leitura: nas datas com batch, as tabelas sempre funcionaram (o 27/07 devolve as linhas de
swap desde o §182).

### A correção é uma frase, não um walk-back

Fazer as tabelas recuarem para o último dia com arquivo "resolveria" o vazio mentindo sobre a data. O que
entrou foi diagnóstico: `_ops_batch_status(ref)` confere as quatro fontes do dia mais a posição SWAP e
devolve `{missing, blocking, last_batch}`, publicado no payload como `sources`.

A faixa na tela distingue **dois casos**, porque a ação de quem lê é diferente:

- **Bloqueante** (`alert-warning`) — falta o **Operations B3**. Sem ele não há universo: zero linhas,
  sempre. A faixa nomeia o que falta e oferece **ir para o último dia com batch** (busca 60 dias para
  trás), porque sem essa dica a pessoa fica trocando data às cegas.
- **Informativo** (`alert-info`) — falta uma fonte auxiliar (OTM, Athena, Events, Posição). As linhas
  aparecem; algumas **colunas** é que ficam em branco. Nada de sugerir troca de data.

Usar a mesma cor nos dois faria "faltou tudo" parecer "faltou um detalhe" — o teste prende as duas classes.

### Verificação

Seção 10 do `scripts/tests/check_ops_summary.py` (64 asserções no total): o diretório vazio (bloqueante,
sem dia a sugerir), o batch presente com auxiliares faltando (informativo) e a busca do último dia com
batch. Mais o cabeamento: o endpoint publica `sources`, o JS chama `setSources`, e os três ganchos da faixa
existem no HTML.

**Vale para as outras telas do batch.** Toda página que lê o batch por data tem o mesmo silêncio possível.
Aqui ele foi fechado; nas irmãs, não.

---

## §186 — Other Products Summary: arquivo presente, tabela vazia

Sequência do §185. Com o batch **todo importado** para o dia (as quatro fontes na pasta, a faixa de
diagnóstico sem nada a reclamar, Swap Athena e Swap Events mostrando as duas operações do dia), o Trade
Level e o Settlement Summary continuavam vazios. A faixa do §185 não ajudava: ela só sabia responder
"qual arquivo falta", e não faltava nenhum.

### O funil tem duas peneiras, e nenhuma delas aparecia

`_ops_swap_settling` descarta uma linha do Operations B3 por **dois** motivos: `Tipo Título` sem `SWAP`, ou
`Tipo Operação` fora do cadastro `swap-b3-events`. As duas descartam **em silêncio** — a linha some, a
tabela fica vazia e nada distingue "não tem swap hoje" de "tem swap, mas o texto do evento não está
cadastrado".

Agora `_ops_batch_status` responde isso quando o arquivo existe e nenhuma linha passou:

```
{'rows': 26, 'swap_rows': 2, 'found': ['RESGATE', 'RESGATE ANTECIPADO']}
```

e a faixa vira uma frase acionável: *"O Operations B3 tem 2 linha(s) de SWAP, nenhuma com Tipo Operação
cadastrado. No arquivo: `RESGATE` · `RESGATE ANTECIPADO`. Cadastre a variação em Mapping › Swap B3
Events."* Quando não há linha de SWAP nenhuma, o texto é outro — são problemas diferentes.

Esse aviso é **âmbar**, como a ausência de batch: arquivo presente com tabela vazia deixa a tela tão vazia
quanto arquivo ausente, e pintá-lo de azul (o tom de "batch parcial") diria que é um detalhe.

**Por que não sair cadastrando as variações**: o cadastro é o desenho (`_MAPPING_DEFS`, regra de ouro do
CLAUDE.md). Chutar `RESGATE` como evento de liquidação de swap misturaria vencimento com diferencial nas
contas. A tela agora mostra o texto exato do arquivo; quem conhece o significado registra.

### O espaço duplo, que já estava armado

`_ops_norm_event` substituiu o `_fcst_norm(...).strip()` da comparação: `_fcst_norm` cuida de caixa e
acento mas **não colapsa espaço**, e arquivos da B3 vêm com padding. `PAGAMENTO DE  DIF. DE JUROS` (dois
espaços) não casava com a linha cadastrada — o swap sumia sem nenhum sinal. Aplica-se aos **dois** lados
(arquivo e cadastro), então o seed segue casando igual.

Não sabemos se era essa a causa no dia do relato — o arquivo não estava disponível aqui. É uma armadilha
real fechada de qualquer forma, e barata.

### Verificação

Seções 10 e 11 do `check_ops_summary.py` (64 asserções no total). A 11 monta o cenário do relato —
Operations B3 com linhas de SWAP em `RESGATE`/`RESGATE ANTECIPADO` e as auxiliares presentes — e confere
que zero linhas saem, que o diagnóstico conta as linhas de SWAP e lista os valores **do arquivo**, que um
TER com o mesmo Tipo Operação não entra na conta, que com o evento cadastrado a linha sai e o diagnóstico
se cala, e que o espaço duplo passa a casar.

---

## §187 — Settlement Advice de Swap: indexadores, Print Advice, e o Prazo que mudou

Quatro pedidos numa tacada. O que exige atenção depois não são os três primeiros — é o quarto, que mexeu
numa conta de imposto.

### 1. Indexador Banco / Indexador Cliente (era "Ativo")

Fonte trocada: saía do arquivo de **eventos** (`PARTE / Indexador`), passa a sair da **posição**
DPOSICAO-SWAP, com uma regra:

- `Código índice` da perna ≠ **VCP** → o próprio código é o indexador (`CDI`, `PRE`, `IPCA`).
- `Código índice` = **VCP** → VCP é "variação cambial" e não diz **qual moeda**. O indexador de verdade
  está no `Nome Tipo/Classe` da mesma perna, e vai em **CAIXA ALTA**. Imprimir "VCP" no aviso do cliente
  não informa nada.

Os índices posicionais: `Código índice` em **40** (banco) e **50** (cliente); `Nome Tipo/Classe` em **69**
e **74**. São a 1ª e a 2ª de cada uma **na tela** do Live Position › Swap — e é essa a leitura certa,
porque **no arquivo cru existe um `Nome Tipo/Classe` antes, no índice 30**, que pertence ao bloco do Termo
e a perna nenhuma. Pegá-lo "porque é o primeiro" daria a classe errada sem erro em lugar nenhum. O teste
preenche o índice 30 com `CLASSE DO TERMO` justamente para prender isso.

`_ops_swap_pos_terms` passou a devolver um **dict** (`op`, `venc`, `idx_banco`, `idx_cliente`) em vez da
tupla — os dois consumidores foram junto. Fora do caminho posicional (mock esparso) os indexadores saem
vazios: com nomes repetidos não há como dizer qual é a 1ª e qual é a 2ª.

### 2. Vencimento = a data da liquidação  ⚠️ e o Prazo mudou junto

A coluna Vencimento passa a ser a **data de liquidação** (a referência da tela), não o vencimento do swap.
E o **Prazo é a diferença entre as duas datas impressas** — senão o cliente confere a conta do aviso e ela
não fecha.

**Consequência que precisa ser conferida**: o Prazo alimenta a faixa de IR. Antes era `vencimento − trade`;
agora é `liquidação − trade`. Para um diferencial no meio da vida do swap isso **encurta** o prazo e pode
**subir** a alíquota. É a leitura que faz sentido — o imposto incide sobre o pagamento que sai hoje, e o
período que conta é o decorrido até ele —, mas é uma mudança de conta de imposto e vale bater contra a
planilha no primeiro dia.

A mudança foi aplicada **também no Trade Level** (`_ops_swap_trade_rows`), de propósito: as duas telas têm
de imprimir a mesma alíquota para o mesmo swap no mesmo dia.

### 3. Print Advice

Botão na toolbar da página → `POST /api/other-products-swap-settlement-advice/emails` →
`otc_emails.build_swap_settlement_emails`. **Mesmo documento do aviso de NDF** (mesma casca, mesma tabela,
mesmo painel de totais, mesma regra de instrução/dados bancários pelo sinal do resultado, reaproveitada
verbatim para os dois não divergirem em instrução de pagamento). O que muda é a tabela e o assunto.

- **Colunas**: as da tela **a partir de `Número de Contrato`**. Cliente e LOB ficam de fora — são o
  destinatário e o agrupamento, não conteúdo do documento.
- **Valores em BR**: `R$ 1.234,56`, negativo com o símbolo **dentro** dos parênteses (`(R$ 48.273,88)`) —
  é o `_brl` que o aviso de NDF já usa. Prazo em `#.##0`. **A tela segue em US**: as duas formatações
  convivem de propósito, e o aviso formata a partir do **número**, não do texto da tela — reformatar de
  uma para a outra erraria no primeiro valor com separador ambíguo.
- **Agrupamento**: um aviso por contraparte × entidade legal × prêmio.
- **Entrega**: até 2 avisos vão como `.eml` em base64 (abrem direto no Outlook); 3+ num `.zip`. Igual ao
  NDF.

`otc_emails` **não conhece a ordem das colunas** — ela chega pronta de `_swadv_email_rows`. Reconstruí-la
lá criaria a segunda cópia da ordem das colunas, que é o defeito que o §182 já tinha custado caro.

### 4. Prêmio: assunto e nome de coluna

Quando o evento é **Pagamento de Prêmio**:

- assunto: `(Pagamento de Prêmio) Liquidação de Operação de Derivativo (Swap) - dd/mm/yyyy - Contraparte`;
- a coluna `Vencimento` vira **`Pagamento de Prêmio`** — não é vencimento de nada, é a parcela do dia.

**Regra do "é prêmio"**: quando **todos** os eventos registrados daquele Título são prêmio. Um swap que
paga prêmio *e* diferencial no mesmo dia é liquidação comum — chamar o conjunto de "Pagamento de Prêmio"
no assunto esconderia o diferencial que também está na tabela.

### 5. Actions e Status iguais aos do NDF Summary

Trade Level e Settlement Summary do Other Products passaram a usar os mesmos botões e badges: `.ops-row-act`
(quadrado arredondado de tamanho **travado** por min/max — sem isso uma regra do tema deixa Confirm e
Delete de tamanhos diferentes), pill `OK`/`Check` no Trade Level e `New`/`Generated`/`Sent` no Settlement
Summary, nas mesmas cores. O `<select>` continua, mas só na **linha manual** do Add row, onde o estado é de
quem digitou e não do cálculo.

O **Confirm** ficou funcional: `POST /api/other-products-summary/mark-sent` grava `Sent` no mesmo overlay
do dia que já guardava a observação. Ele salta direto de New para Sent porque `Generated` só existirá
quando esta página ganhar geração de aviso. Botão que não confirma nada seria só um botão bonito.

### Verificação

`check_swap_advice.py` (seção 7 nova) e `check_ops_summary.py` (seção 12 nova) — suíte inteira verde.
Além dos testes: as duas páginas respondem 200 e os dois endpoints foram exercidos pelo `test_client`.

**Limite honesto**: o Print Advice gera para **todas** as linhas da data. O endpoint aceita uma lista
`contracts` para gerar só algumas, mas o botão ainda não a envia — o visualizador genérico não expõe a
DataTable, e ler os checkboxes do DOM só enxergaria a página corrente da paginação (a armadilha do §152).

---

## §188 — As traduções de código do Swap saem do cadastro (e dois bugs do aviso)

### Os dois bugs primeiro

**Valor Base Original saía vazia no aviso.** Ela vinha do arquivo de **eventos**
(`eventos-swap-jpm`), por um join a mais que podia falhar sem sinal. Passou a sair da **posição**
(`Valor base`, índice 14) — o mesmo arquivo que já é lido para as datas e os indexadores. Uma fonte a
menos é um join a menos para falhar em silêncio, e o arquivo de eventos deixou de ser lido no aviso.

**Indexador Banco/Cliente não resolvia o VCP.** `_swadv_indexador` comparava o `Código índice` **cru** com
`'VCP'` — e o VCP é `C00`. Nunca casava. Agora o código passa **primeiro** pela tradução do Swap Index (a
mesma que a tela do Live Position › Swap usa) e só então se testa se deu VCP.

### As traduções viraram cadastro

Regra de ouro do CLAUDE.md: de-para não mora no código. As tabelas do Swap eram dicts em `routes.py`.
Agora:

| cadastro | traduz | vinha de |
|---|---|---|
| `swap-index` | Código de Referência Externa → Nome da Curva (`C00` → `VCP`) | `SwapIndex.json` |
| `swap-funcionalidade` | Funcionalidade (0–9) | `_SWAPCHAR_FUNC_MAP` |
| `swap-amortizacao` | Tipo de Amortização (0/1/3/4) | `_SWAPCHAR_AMORT_MAP` |
| `swap-code-labels` | Sinal Taxa (+/−) e Sim/Não | literais em duas funções |

**O `swap-index` aponta para o PRÓPRIO `SwapIndex.json`**, via a chave `file` do `_MAPPING_DEFS` — não
para uma cópia. As duas telas (a aba Swap Index do B3 Index Results e o /mapping) editam **o mesmo
arquivo**, então não existe a versão de uma e a versão da outra. As colunas são as chaves do próprio
arquivo, **inclusive STATUS/MAKER/CHECKER**, declaradas de propósito: o POST do /mapping reescreve o
arquivo inteiro e as apagaria.

Os seeds reproduzem exatamente o que estava hardcoded — a migração não pode mudar a tela sem ninguém
pedir. `_swapchar_code_map` normaliza o código para o inteiro sem zeros à esquerda, que é como os arquivos
da B3 variam (`0`, `00`, `000`): registrar as três formas seria pedir erro.

**Live Position Termo e Opção**: auditadas, **não têm de-para**. O que elas fazem é formatação — data
para dd/mm/yyyy, número para `#,##0.00`, taxa, 8 casas, máscara de CPF/CNPJ. Não há o que registrar lá, e
inventar um cadastro para formatação de número seria cadastro morto. Toda a tradução de código do módulo
está no Swap, e agora está no /mapping.

### Difference com ✓/✗

A coluna Difference do Trade Level ganhou o ícone ao lado do número, igual ao do NDF. O ícone sai do
**mesmo `status`** que pinta o badge da linha — duas fontes contariam histórias diferentes na primeira vez
que a tolerância mudasse. Diferença **vazia** ("não deu para calcular") ainda mostra ✗: é pedido de
conferência.

Isso mexeu na última coluna do `rowMaker`, que é uma das três listas posicionais do §182 — a seção 4 do
`check_ops_trade_swap.py` foi ajustada para reconhecer `diffCell(r)` como a célula de `difference`.

### Verificação

Seções 8 e 9 novas em `check_swap_advice.py`: os quatro cadastros registrados e com aba, **nenhum
dicionário de tradução sobrando no código**, o `swap-index` apontando para o arquivo original, e cada
tradução conferida valor a valor contra o que estava hardcoded. Suíte inteira verde; as quatro páginas
afetadas respondem 200 e `/api/mappings/swap-index` devolve as 77 linhas.

---

## §189 — Cards de reconciliação no Other Products Summary (e três acertos)

### Os cards viram reconciliação B3 × Interno

Porte dos cards do NDF Summary: cada família (Swap · Option · NDF Commodities · COE) passa a mostrar
**Ops e Valor dos dois lados**, com o badge e a **luz de fundo** por estado, mais um **card de Total**
somando as quatro. `Flow` virou `Cashflow` no card de Swap.

**De onde saem os dois lados — e por que isso importa.** Os números vêm das linhas **já montadas do Trade
Level** (`_b3_n` e `_settle_n`), não de uma segunda varredura do Operations B3. Um card de reconciliação
só vale alguma coisa se contar exatamente o que a tabela logo abaixo mostra; relendo os arquivos, ele
traria linhas que a tabela não mostra e os dois se contradiriam na mesma tela.

Consequência a entender: **o lado B3 do card de Swap cobre só os Tipos Operação registrados em
`swap-b3-events`** — é o universo do Trade Level. Registrar mais um evento lá faz o card e a tabela
crescerem **juntos**, que é o ponto. Se hoje falta o RESGATE (vencimento) no card, é porque ele não está
cadastrado como evento de liquidação.

**Três estados, não dois.** `OK` (contagem *e* valor batem), `Check` (divergência, luz âmbar) e **`n/a`**
— traço cinza, sem luz — para as famílias que ainda não têm lado interno (Option, NDF Commodities, COE).
Não há divergência ali; há conta que ainda não é feita, e pintar de âmbar leria como erro de dado. As três
acendem sozinhas quando as suas linhas do Trade Level existirem.

Bater exige **contagem e valor**: só o valor deixaria passar duas operações que se anulam.

Os sub-contadores antigos (Cashflow/Maturity/Premium) continuam, vindos dos arquivos de **posição** — eles
respondem outra pergunta ("o que vence hoje") e por isso **não** devem ser somados com a reconciliação.

### Os três acertos

**Ícone do FXO Conversion Rate.** Era a única aba do /mapping sem ícone porque `ti-currency-exchange`
**não existe** no Tabler empacotado (`vendors.min.css`) — nome de ícone inexistente não dá erro nenhum,
só deixa o espaço em branco. Trocado por `ti-transfer`. A seção 14 do `check_ops_summary.py` agora confere
**todos** os 19 ícones de aba contra o CSS, para isso não voltar em silêncio.

**JSONs dos cadastros novos.** `swap-funcionalidade`, `swap-amortizacao` e `swap-code-labels` são semeados
na primeira leitura em `apps/static/data/mappings/` e foram versionados. O `swap-index` **não tem arquivo
próprio**: ele aponta para `apps/static/data/SwapIndex.json` (§188), que já era versionado.

**Toolbar do Settlement Advice.** O Columns e o Export são injetados pelo JS depois do render e vêm com
margem zerada, então a fila de botões encostava no cabeçalho da tabela e nos cantos do card. Padding na
barra + `row-gap` para a quebra em tela estreita.

### Verificação

Seções 13 e 14 novas no `check_ops_summary.py`: a regra de bater (contagem *e* valor, com o caso "valor
igual, contagem diferente" explicitamente reprovado), o `n/a` por família, a soma do Total, os cinco cards
com os seus ganchos, `Flow` → `Cashflow`, a luz com o anel como variável (§181), e a auditoria dos ícones.
Suíte inteira verde; as quatro páginas afetadas respondem 200.

---

## §190 — O status do aviso de Swap é um só, nas duas telas

Antes: o Settlement Advice mostrava um badge **fixo** (herdado do visualizador genérico, que o usa para
"custódia") e o Settlement Summary tinha o seu próprio New/Sent. Dois estados para o mesmo aviso.

Agora o ciclo é **New → Generated → Sent**, guardado uma vez só no overlay do dia
(`other-products-summary_YYYYMMDD.json`) e lido pelas duas telas pela **mesma chave**: contraparte × LOB ×
produto (`_opssum_key`).

- **New** — nasce assim, sem entrada no overlay.
- **Generated** — o **Print Advice** grava, para cada linha que de fato virou rascunho. Contraparte
  pulada pelo `build_swap_settlement_emails` (Lawton, JPMorgan) **não** é marcada: o estado tem de refletir
  o que saiu, não o que se tentou.
- **Sent** — o botão **Confirm** (✓) do Settlement Summary.

O Settlement Advice é por contrato e o Summary é por linha de aviso; o contrato **herda** o estado da
linha a que pertence, e é por isso que a chave inclui a LOB — que a linha do aviso já carrega. Duas LOBs
da mesma contraparte são dois avisos e caminham separadas.

Escrita centralizada em `_opssum_set_status` / leitura em `_opssum_status`: os três pontos que mexem em
estado (Print Advice, Confirm, montagem das linhas) passam pelos mesmos dois helpers.

**O Confirm fica só no Settlement Summary.** O Settlement Advice não tem coluna de ações — é a tela de
conferência do documento, e o controle do fluxo vive no Summary, como no NDF. O que a tela de advice ganha
é a **visibilidade**: dá para ver por contrato o que já foi gerado.

### O visualizador genérico ganhou status por linha — de forma aditiva

`live-position-swap-characteristics.js` serve **cinco** páginas. O payload agora pode trazer `statuses`,
um array paralelo a `rows`; quem não manda (Athena, Events, VCP, Characteristics) continua com o badge
fixo de antes. Também expõe `window.scLoad` — só isso — para a página recarregar a tabela depois do Print
Advice, senão a tela seguiria mostrando `New` até o próximo F5.

### Toolbar

Segunda passada no respiro: além do padding embaixo (que separa dos `<th>`), os botões ganharam **altura
própria**. Show/entries, Columns, Export, Clear filters e Print Advice vêm de três origens diferentes
(template, DataTables Buttons e JS), cada uma com o seu default — sem padronizar a altura e a margem, a
fila fica com a cara de "comida".

### Verificação

Seções 10 e 11 novas no `check_swap_advice.py`: o ciclo inteiro nas duas telas, a chave normalizada, a
outra LOB que **não** é arrastada junto, o viewer caindo no badge de sempre quando não há `statuses`, e as
três cores idênticas às do NDF. Além do teste, o ciclo foi percorrido ponta a ponta pelo `test_client`
(New → Print Advice → Generated nas duas → Confirm → Sent nas duas), e as cinco páginas do visualizador
compartilhado respondem 200.

---

## §191 — Botão TEDs no Other Products Summary

Porte do TED do NDF Summary: **mesma regra de quem entra, mesmo template de e-mail, mesmos destinatários**
(`_TED_EMAIL_TO` — OTC Ops + Settlements), mesmo anexo de SSI por contraparte (arquivo mais novo do
Electronic Inventory). O que muda é **só o assunto**:

```
Liberar TED's - Swap/Opção/Commodities - dd/mm/yyyy
```

### Quem entra — as três regras que separam "pedido correto" de "TED para quem não devia"

1. **Pay preenchido** — há o que transferir. Settlement positivo é o banco *recebendo*: não é TED.
2. **Conta fora do BCO 376** — 376 é o próprio Banco J.P. Morgan; ali é transferência interna, não TED.
   A conta é a mesma da coluna **Account** da tela (default de recebimento do cliente).
3. **Contraparte que não seja Lawton nem JPMorgan** — perna interna não recebe TED.

Dois blocos no e-mail por entidade legal (BANCO / MGT), como no NDF. Para isso a linha do Settlement
Summary passou a carregar a **entidade legal** (primeira não vazia do grupo), que vem do Athena pela linha
do Trade Level.

### O ponto de projeto

O endpoint **reusa `_opssum_rows`** — as mesmas linhas que a tela mostra. Recalcular o net aqui criaria a
segunda cópia da regra de netting, e o pedido de TED poderia sair com um valor diferente do que está na
tela. Como é dinheiro saindo do banco, essa é a divergência que não pode existir.

O SSI que falta **não impede o envio**, mas aparece no retorno: é a contraparte cujo anexo o time vai ter
de buscar na mão.

A página passou a carregar o SweetAlert (CSS + JS) — o retorno do botão usa `Swal.fire`, e sem o plugin o
clique falharia em silêncio.

### Verificação

Seção 15 do `check_ops_summary.py`: as três regras conferidas uma a uma chamando o **endpoint de verdade**
com SMTP stubado (nada sai da máquina), o assunto comparado byte a byte, os destinatários iguais aos do
NDF, e a prova de que o TED reusa `_opssum_rows` em vez de recalcular. Suíte inteira verde.

---

## §192 — O rótulo do produto no e-mail de TED era fixo em "NDF"

O assunto do TED de Swap saiu certo no §191, mas o **corpo do e-mail não**: o template
`email-template-ted-release.html` tinha `NDF` **escrito direto** em dois lugares — o título ao lado do
logo (`Liberação de TED — NDF`) e a frase da abertura (`…referentes às liquidações de NDF de …`). O aviso
de Swap chegava com o assunto de Swap e o corpo dizendo NDF.

Agora o rótulo é um parâmetro (`product_label`), com **default `'NDF'`** — sem passar nada o template
renderiza byte a byte o que renderizava antes, então o aviso de NDF não muda. Os dois endpoints passam o
seu: o de NDF passa `'NDF'` explicitamente, e o de Other Products passa `_OPS_TED_LABEL`.

`_OPS_TED_LABEL = 'Swap/Opção/Commodities'` é **uma constante para os três lugares** — assunto, cabeçalho
e corpo. Era exatamente aí que estava o defeito: três textos independentes, e nada obrigando os três a
concordarem.

### Verificação

Seção 11 nova no `check_swap_advice.py` (o default do template preservado, e nenhum `NDF` fixo sobrando
no cabeçalho ou no corpo) e três asserções novas na seção 15 do `check_ops_summary.py`, que **abre o HTML
do e-mail montado de verdade** e confere o cabeçalho, a frase do corpo e que a palavra `NDF` não aparece
em lugar nenhum do aviso de Swap. Suíte inteira verde.

---

## §193 — Card de Option: Câmbio × Commodities

O card de Option somava opção de **taxa de câmbio** com opção de **commodities**. São mesas e
conferências diferentes, e o número somado não dizia de quem era. Agora o card traz as duas quebras
(`FX` e `Commodities`) ao lado de Maturity e Premium.

**A armadilha, que já estava pronta para me pegar**: o arquivo de posição de **opção** escreve
`TAXA DE CAMBIO` (**singular**); o de NDF escreve `TAXAS DE CAMBIO`. A primeira versão comparava por
igualdade contra a grafia do NDF e deixaria o balde de FX **permanentemente em zero** — e zero ali não
parece defeito, parece "não teve opção de câmbio hoje". A comparação passou a ser por **token**
(`'cambio' in`, `'commodit' in`), e o teste fixa as duas grafias.

A classe que não é nenhuma das duas (`ACOES`) continua no **total** do card: a quebra não pode fazer o
card perder operação.

A quebra vale para as **duas datas** da opção (vencimento e prêmio) — a classe é do contrato, não do
evento.

Verificação: seção 16 do `check_ops_summary.py`.

---

## §194 — Other Products › NDF › Settlement Advice (Termo de Mercadoria)

Página nova, no mesmo visualizador genérico das irmãs (`data-api` + `swapchar-page`/`swapchar-table`).
Menu: **Daily Settlement › Other Products › NDF › Settlement Advice**.

### O universo: três peneiras

Operations B3 com **Tipo Operação = RESGATE**, **Tipo Título = TER** e a coluna derivada
**Type = COMMODITIES** (que para TER é a *Classe do Ativo Subjacente* da posição). Errar qualquer uma das
três traz para o aviso do cliente operação que não é dele — uma opção, um termo de câmbio. O teste passa
uma linha de cada tipo errado e prova que nenhuma entra.

### As colunas

`Contraparte · B3 ID · Nº da Confirmação · Data de Início da Operação · Ativo Subjacente · Ptax ·
Cotação Mercadoria · Quantidade da Operação · Resultado Apurado (R$) · IR 0,005% (R$) ·
Resultado Líquido (R$) · Settlement Net`

Duas decisões sobre a lista pedida: **Contraparte entrou no início e não se repete no fim** (a mesma
informação duas vezes na mesma linha), e **Athena ID saiu** porque é o mesmo valor do Nº da Confirmação.

Três regras que valem registrar:

- **Ativo Subjacente** — o código do subjacente da posição NDF passa pelo `Subjacente.json` (a aba
  Subjacente do B3 Index Results) e vira `COMMODITY(CÓDIGO)`, ex.: `ALUMINIO(OAHDY)`. O arquivo tem ~7.800
  linhas e **repete o mesmo código** uma vez por Tipo IF (OPC, COE, TER…): a primeira com Commodity
  preenchida vence, e uma linha sem Commodity não pode apagar a que tem. Código sem commodity registrada
  volta só o código — melhor mostrar o que veio do arquivo do que inventar um nome.
- **Cotação Mercadoria** — a Data de Fixing do Ativo Subjacente. Vazia (o caso da **asiática**), vira o
  mês/ano da 1ª data de verificação escrito por extenso: `Média Fev/2027`. As datas de verificação são um
  bloco **posicional** no arquivo da B3 (a 1ª é o índice 100), e é por isso que a página lê a posição
  através de `_lpndf_collect` — que já resolve esse bloco — em vez de abrir o arquivo direto.
- **Ptax** — a Data de Fixing da **Moeda** (não a do ativo).

### O join que não é óbvio: OTM pelo sufixo

O **Resultado Apurado é o valor INTERNO**, do OTM Settlements. O `Trade Id` do OTM e o Nº da Confirmação
carregam o **mesmo identificador depois do hífen** e prefixos diferentes antes (`OTM-1NR000` ×
`DBH-1NR000`). Comparar a string inteira não casa nada e a coluna sai vazia — o join é pelo **sufixo**, e
soma, porque um trade aparece em várias linhas de fluxo.

### O IR

Porte da fórmula da planilha: **0,005% sobre o valor, e só quando o banco PAGA** (apurado < 0);
**LAWTON é isenta**; arredondado a 2 casas. E o IR **encolhe** o líquido — mesma regra sinal-consciente do
aviso de FX: `-2.028.144,04` com `101,41` de IR fecha em `-2.028.042,63`.

### Ainda não

O **Print Advice** desta página não existe (botão removido do template copiado — botão que dá 404 é pior
que botão ausente), e as linhas de NDF Commodities ainda não aparecem no Trade Level. São os dois próximos
passos.

### Junto

Toolbar do **OTM Settlements** ganhou o mesmo respiro do §190 (padding + altura igual para os botões das
três origens: template, DataTables Buttons e JS).

Verificação: `scripts/tests/check_ndf_advice.py` (6 seções) — as quatro fontes num tempfile, incluindo o
registro de posição com o bloco asiático no índice posicional certo.

---

## §195 — NDF Commodities no Trade Level (e o IR que virou cadastro)

As linhas de **Termo de Mercadoria** entraram no Trade Level do Other Products Summary, e com elas o card
de **NDF Commodities** saiu do `n/a` e passou a reconciliar.

### Saem do MESMO lugar do aviso

`_ops_ndfc_trade_rows` parte de `_ndfadv_collect` — as mesmas linhas do Settlement Advice de NDF. A tabela
e o documento que o cliente recebe não podem mostrar valores diferentes para o mesmo contrato; o que muda
entre as duas é só o recorte das colunas.

| coluna | valor |
|---|---|
| Product | `TERMO` |
| LOB | `COMMODITIES` |
| Type | a **commodity** do subjacente (`ALUMINIO(OAHDY)`) |
| Internal ID | o identificador do **Athena** (o Nº da Confirmação) |
| B3 ID | o **Título** do Operations B3 |
| Settlement | o **interno** (soma do OTM pelo sufixo) |
| Settlement B3 | o `Valor` do Operations B3 daquele Título |
| Tax Income | o IR de 0,005% |

Trocar Internal ID por B3 ID deixa a linha "preenchida" e impossível de casar com qualquer sistema — o
teste fixa os dois.

O card: o Trade Level chama de `TERMO` e o card se chama `NDF Commodities`. **A mesma família precisa ser
reconhecida pelos dois nomes**, senão a linha aparece na tabela e o card continua zerado.

Cada família é montada em `try` próprio: uma fonte malformada de NDF não pode apagar as linhas de swap
que já foram montadas.

### O IR de 0,005% virou cadastro — e é UM só para as duas telas

Novo mapping **`ndfc-ir-exempt`** (`CLIENT` · `MATCH` Exact/Starts with · `NOTES`): quem **não** paga o IR
do Termo de Mercadoria. `_ndfc_ir(apurado, cliente)` é chamada tanto pelo Settlement Advice quanto pelo
Trade Level — são o mesmo imposto sobre a mesma operação, e duas listas divergiriam sem erro nenhum, uma
tela retendo e a outra não.

**Mudança em relação à fórmula da planilha, de propósito**: a fórmula isentava só `LAWTON`. O seed traz
`LAWTON`, `ATACAMA`, `BANCO` e as duas grafias de `JPMORGAN`/`J.P. MORGAN`, porque foram pedidas por nome
("instituição financeira, como lawton, atacama, bancos e etc"). Isso **muda o IR impresso** para essas
contrapartes em relação à planilha antiga — vale conferir no primeiro dia. Qualquer outra se registra pela
tela, sem tocar em código.

Verificação: seções 7 e 8 do `check_ndf_advice.py`, incluindo a linha que **não** bate (Check + a diferença
à mostra) e a prova de que o IR do aviso e o do Trade Level são o mesmo número.

---

## §196 — Print Advice do Termo de Mercadoria (e a quebra dos avisos)

O botão entrou na página de NDF Settlement Advice. O documento é o **mesmo** do aviso de NDF de moeda —
mesma casca, mesma tabela, mesmo painel de totais, mesma regra de instrução/dados bancários pelo sinal do
resultado — e o **mesmo anexo em PDF** (`_ndf_settlement_pdf`), com o **mesmo cadastro de quem recebe**
(`ndf-pdf-cpty`). Reaproveitado, não recopiado: duas fichas de liquidação com layouts que derivam é o
tipo de divergência que só aparece na mesa do cliente.

Colunas do aviso: da tela, **de `B3 ID` em diante, sem `Settlement Net`**. Contraparte é o destinatário e
Settlement Net é o critério de quebra — nenhum dos dois é conteúdo do documento. Valores em BR
(`(R$ 2.028.144,04)`), formatados a partir do **número**, não do texto da tela (que segue em US).

Assunto: `Liquidação de Operação de Derivativo (Termo de Mercadoria) - dd/mm/yyyy - Contraparte`, com a
**commodity no fim quando o aviso tem uma só** — três assuntos idênticos no mesmo dia seriam três anexos
que ninguém sabe separar.

### A quebra, que é o ponto delicado

Na ordem em que roda:

1. **contraparte × entidade legal** — entidades diferentes nunca netam juntas;
2. **net type**: `Total Net` → um aviso; `Pay/Rec` → um por **sentido** do resultado líquido; `No Net` →
   um por trade;
3. **commodity**, e só para quem está no cadastro **`ndfc-advice-split`** (semeado com `MONDELEZ`,
   *Starts with*).

A ordem importa: a quebra por commodity é a **última**, então um `Pay/Rec` do Mondelez sai por sentido
**e** por commodity — quatro avisos, não dois. O teste fixa exatamente esse caso.

`MONDELEZ` com *Starts with* cobre as duas entidades (Brasil e Brasil Norte Nordeste), que já são
contrapartes distintas no Reference Data — **a quebra entre elas acontece sozinha**, sem regra especial.
Fora do cadastro, um aviso pode trazer alumínio e café na mesma tabela.

### Verificação

Seções 9 a 11 do `check_ndf_advice.py`: as colunas do aviso, os valores em BR, os quatro cenários de
quebra (Total Net · Pay/Rec · No Net · Mondelez com sentido × commodity), o assunto, e a prova de que o
PDF sai do mesmo gerador e do mesmo cadastro do aviso de moeda. Além do teste, um aviso completo foi
montado de verdade: PDF de 9 KB anexado e o logo no corpo.

---

## §197 — Conta omnibus: quem é o cliente sai do CNPJ

Numa linha do Operations B3 cuja **Conta Contraparte é a conta guarda-chuva** (`73760.10-2`), o nome que
vem da B3 é o do **titular do omnibus**, não o do cliente. Usar esse nome manda o aviso de liquidação para
o cliente errado — e a linha *parece certa*: nome preenchido, valores preenchidos, nada de errado na tela.

A regra agora é: conta omnibus → pega o **CPF/CNPJ da Contraparte** da posição NDF e procura o nome no
`RefData.json` **pelo CNPJ**. Fora do omnibus, o nome da posição continua valendo; e sem CNPJ ou sem
cadastro, cai na cascata de antes (nome da posição → Nome Simplificado do B3).

Vale para as **duas telas**: o Settlement Advice e o Trade Level, que herda a contraparte já resolvida —
as duas não podem discordar de quem é a contraparte da mesma operação.

### Duas comparações por dígitos, e por quê

- **O CNPJ**: o RefData guarda mascarado (`45.985.371/0001-08`) e a posição da B3 guarda só números.
  Comparar as strings não casaria nada, e a coluna sairia com o nome do omnibus — sem erro.
- **A conta**: aparece ora `73760.10-2`, ora com outra pontuação. Mesma razão.

O índice do RefData é `{CNPJ → COUNTERPARTY}`, primeiro registro vence (há mais linhas do que CNPJs
distintos), cacheado por mtime.

### A conta virou cadastro

`b3-omnibus-account` (`ACCOUNT` · `NOTES`), semeado com `73760.10-2`. Uma conta a mais amanhã se registra
pela tela — nenhuma conta da B3 devia estar escrita em código.

> **Superado pelo §287.** O cadastro virou `b3-accounts` e passou a listar TODAS as contas B3 das
> nossas entidades, própria inclusive — então quem responde "é guarda-chuva?" deixou de ser a
> presença na tabela e passou a ser a coluna `ACCOUNT TYPE` (`CLIENT 1` / `CLIENT 2`).

### Junto

Toolbar do **Live Position NDF** ganhou o mesmo respiro do §190/§194.

Verificação: seção 12 do `check_ndf_advice.py` — a linha que vem pelo omnibus resolvendo pelo CNPJ, a que
**não** vem mantendo o nome da posição, o Trade Level herdando o mesmo nome, e a comparação por dígitos
nos dois lados. Conferido também contra o `RefData.json` real (438 CNPJs indexados).

---

## §198 — Assunto do aviso de NDF Commodities

`(Termo de Mercadoria)` → **`(Termo de Commodities)`** no assunto do aviso:

```
Liquidação de Operação de Derivativo (Termo de Commodities) - dd/mm/yyyy - Contraparte
```

Os dois sufixos continuam: a **commodity** quando o aviso tem uma só, e ` x JPMORGAN CHASE` quando a
entidade legal é a MGT.

Só o assunto mudou — o corpo, o PDF e a quebra seguem iguais. A prosa do §194/§196 continua chamando o
produto de "Termo de Mercadoria" porque é o nome do instrumento; o que o cliente lê no assunto é o texto
acima.

---

## §199 — O e-mail de TED pedia só o swap (e ganhou a coluna Product)

Bug de verdade, e do tipo que não acusa: quando o **NDF Commodities** entrou no Trade Level (§195), o
e-mail de TED continuou pedindo **só as TEDs de swap**. A causa é a de sempre — o endpoint **reconstruía a
lista de trades por conta própria** (`_opssum_rows(_ops_swap_trade_rows(...))`) em vez de usar a mesma que
a tela usa. A TED da contraparte de commodities simplesmente não era pedida: sem erro, sem linha a menos
visível, só um pagamento que não sai.

A correção não foi acrescentar a chamada que faltava — foi tirar a decisão do endpoint.
**`_ops_trade_rows(settle_ref)`** é agora o único lugar que sabe quais famílias existem (hoje SWAP e NDF
Commodities), e a tela, os cards de reconciliação e o e-mail de TED chamam essa função. Uma família nova
entra ali e aparece nos três de uma vez. Cada família segue em `try` próprio: uma fonte malformada não
apaga as linhas que as outras já montaram.

### A coluna Product

Entrou na tabela do e-mail, **depois de Counterparty**, porque agora um mesmo pedido de TED mistura swap e
termo de commodities e o time precisa saber de qual é cada linha.

Ela é **condicional**: só aparece se alguma linha do bloco trouxer produto. O e-mail de TED do NDF (a
página de NDF Summary) não manda produto — é tudo NDF — e não podia ganhar uma coluna vazia. O mesmo
template serve os dois.

### Verificação

Seção 15 do `check_ops_summary.py`: a prova de que o TED e a tela chamam a **mesma** função, que
`_ops_trade_rows` inclui as duas famílias, e que a coluna Product é condicional e vem depois de
Counterparty. Além do teste, um dia com um swap e um termo foi montado e o e-mail saiu com as **duas**
contrapartes e os produtos `SWAP` e `TERMO` na tabela.

---

## §200 — O Settlement B3 do swap somava eventos que a tabela não mostra

O card de Swap do Other Products Summary fechava num valor que **nenhuma linha da tela explicava**, e o
Trade Level trazia o mesmo número errado na coluna Settlement B3 — os dois porque leem a mesma célula
(`_b3_n`), que é justamente o que se quis ao montar os cards a partir das linhas já prontas (§182).

A causa está em `_ops_swap_settling`. O `by_titulo` — {Título → linhas} — era preenchido **antes** dos dois
filtros:

```python
by_titulo.setdefault(titulo.upper(), []).append(rec)   # ← antes de tudo
if 'swap' not in _fcst_norm(rec.get('Tipo Título', '')):
    continue
if _ops_norm_event(rec.get('Tipo Operação', '')) not in wanted:
    continue
```

Então o Settlement B3 somava **toda** linha com aquele Título: os eventos fora do cadastro `swap-b3-events`
(um RESGATE, por exemplo) e até linhas de outro Tipo Título que compartilhem o número. O universo da tela
era um; o do valor, outro.

O `append` passou para **depois** dos dois filtros. O comentário do módulo dos cards já afirmava que "o lado
B3 do card de Swap cobre só os Tipos Operação registrados em `swap-b3-events`" — agora é verdade. E vale a
consequência boa: registrar mais um evento na tabela do `/mapping` faz a tabela **e** o card crescerem
juntos.

Um efeito colateral limpou uma redundância: o `_swadv_collect` refiltrava `by_titulo` por `wanted` para
decidir o assunto "Pagamento de Prêmio". Não precisa mais — e refiltrar deixaria parecendo que a coleção
ainda traz eventos de fora.

### Verificação

`check_ops_trade_swap.py`: o fixture ganhou, **no mesmo Título A1** que já liquida, um `RESGATE` de 999 e
uma linha `TER` de 888. Settlement B3 do A1 continua `150.00`, e o card (`_ops_recon`) fecha em `227.00`
com contagem 2 — exatamente a soma das duas linhas visíveis.

---

## §201 — Tolerância de conciliação do Other Products: 20 BRL

A diferença B3 × Interno passa a ser considerada conciliada **até 20,00 BRL** (limite fechado). Abaixo
disso é arredondamento de curva entre os dois lados, não divergência a investigar — o pedido é do time.

O que importa aqui não é o número, é que ele é **um só**. A mesma diferença é lida em dois lugares: o
status **OK/Check** de cada linha do Trade Level e o **`matched`** (a luz âmbar/verde) dos cards de
reconciliação. Eles estavam separados — os cards já liam `_OPS_RECON_TOL`, mas as duas famílias do Trade
Level (swap e NDF commodities) comparavam com o literal `abs(diff) < 0.01` cada uma. Com duas tolerâncias
diferentes, uma linha sairia verde embaixo de um card âmbar e não haveria em qual acreditar.

`_OPS_RECON_TOL = 20.0` subiu para antes de `_ops_swap_trade_rows` (quem lê a linha precisa achar o
número) e as três comparações passaram a usá-lo, todas com `<=`. O `diffCell` do navegador — o X e o
check da coluna Difference — deriva do `status` que o servidor mandou, então não há cópia da regra no
front-end para divergir.

### Verificação

Seção 13 do `check_ops_summary.py`: o valor da constante, o limite fechado (20,00 exatos batem, 20,01
não), e a prova estrutural de que **não sobrou nenhum literal** — `abs(diff) < 0.01` não existe mais em
`routes.py` e as duas famílias usam a constante.

---

## §202 — Mensageria: "Vencimento Swap", os diferenciais num e-mail só, e o "Favor considerar" que faltava

Três pedidos que são o mesmo pedido, e por isso saíram juntos.

### O assunto e o agrupamento são a MESMA decisão

O assunto de swap passa a ser **`Vencimento Swap - Liquidação Banco x <Contraparte> - dd/mm/aaaa`** (o
resto do padrão intacto), e **amortização e juros contra a mesma contraparte saem num e-mail só**, com o
total somado.

Esses dois não podem se separar: se o assunto dissesse "vencimento" e o agrupamento continuasse quebrando
por `Tipo Operação`, a contraparte receberia **dois e-mails com o mesmo assunto** e valores parciais — pior
que o estado anterior, em que ao menos os assuntos os distinguiam. Por isso existe **uma** função,
`otc_emails.opb3_msg_is_swap_venc(tipo_titulo, tipo_operacao)`, e o `routes` a importa em vez de ter a sua
cópia.

A regra dela é **"é SWAP e não é prêmio"**, não uma lista dos dois eventos de hoje: um diferencial novo que
a B3 mande amanhã entra sozinho, e o prêmio (que já tinha assunto e fonte próprios) segue de fora.

Nada se perde ao juntar: **a tabela do e-mail continua mostrando cada linha com o seu `Tipo Operação`**. O
que se ganha é o total a acatar — e o batimento abaixo.

### O "Favor considerar" para swap e para termo de commodities

A frase já existia (`>= R$ 0,01` de divergência entre o lado interno e o da B3), mas só tinha fonte interna
para **TER de moeda** (Cockpit) e **prêmio de swap** (DAGENDAPREMIOS). Vencimento de swap e termo de
**commodity** saíam sempre sem ela — o que é indistinguível de "bateu".

As duas fontes novas saem do **Trade Level do Other Products Summary**, que é a mesma tela que mostra o
Settlement: `_opb3_internal_swap_map` (linhas de swap) e `_opb3_internal_ndfc_map` (NDF commodities), ambas
sobre `_opb3_internal_trade_map(rows)` = `{B3 ID → Σ _settle_n}`. Se o "Favor considerar" do e-mail e o
Settlement da tela discordassem, não haveria como saber qual dos dois seguir.

No TER a escolha é por contrato, não por configuração: **moeda primeiro, e o que ela não conhece é
commodity**. O contrato está numa das duas fontes, nunca nas duas — somar as duas duplicaria.

**Por que o agrupamento é pré-requisito do batimento:** os mapas trazem o total do **contrato**. Se o
e-mail não juntasse amortização e juros antes de comparar, cada metade (100 e 50) seria confrontada com o
total (150) e as **duas** acusariam uma divergência que é só a outra metade.

Contrato que não casa em mapa nenhum continua sem a frase, de propósito: um valor inventado é pior que a
ausência dele.

### Verificação

`scripts/tests/check_opb3_mensageria.py` (novo, 7 seções). Além dos assuntos e da frase, ele chama o
**endpoint de verdade** com um dia sintético — A1 chegando por amortização e por juros, A2 de prêmio, C1 de
termo — e prova que saem três e-mails, que o de vencimento tem as duas linhas e total 150, e que os dois
lados internos chegam. A seção 7 fura o `except` dos mapas (que devolve `{}` em falha e faria um erro de
wiring passar por "dia sem dados") e confirma que eles recebem um `date`, não o `datetime` cru — o
`settle_ref - op_dt` do Trade Level levanta `TypeError` com datetime.

---

## §203 — Confirmação de NDF FWD Start

Porte do fluxo de confirmação do FXO para o **Termo de Moeda com início a termo**: segregação por
grupo, documento pré-preenchido com painel de edição, `.doc` + `.pdf` + `.xml` no Electronic Inventory,
ciclo `New → Generated → Success` com checklist. O que é novo — e o que quebra em silêncio:

### As três colunas do forward start

| Coluna do Anexo I | Campo do cadastro |
|---|---|
| **Pontos de Termo** | `Strike Set Offset` |
| **Data de Verificação da Taxa Forward** | `Strike Set Date` |
| **Data Efetiva** | `Trade Date` |

As duas primeiras são o par que faz a cláusula **4.2.l.2** funcionar: a Taxa Forward não existe na
contratação e é calculada como *câmbio apurado na Data de Verificação + Pontos de Termo*. Trocar as
duas de lugar não levanta erro — as duas células saem preenchidas e o cliente calcula outra taxa.

### A Taxa Forward é "Não Aplicável" de propósito

O import já zera o `Rate` do FWD Start (a taxa só é fixada na Strike Set Date). O documento declara
**"Não Aplicável"**, e é exatamente esse texto que a cláusula 4.2.l.2 procura para calcular a taxa.
Imprimir `0,00` desligaria a cláusula. Quando o `Rate` existir, é ele que sai.

### O Nº é o B3 ID

O `Nº` do Anexo I é o **B3 ID** — o número que a B3 devolve **depois** do registro —, não o Deal
interno. Sem registro a coluna sai **vazia** e o painel avisa: é o pedido de "mapeia o retorno da B3
primeiro" em vez de um código que a contraparte não reconhece. O `Nº` do cabeçalho segue a mesma regra
e só é preenchido quando o grupo tem **uma** operação; com várias não há número que represente o
documento, e o da primeira seria o de uma das operações contidas.

### A janela de verificação

`First Fixing` vazio ou igual ao `Last Fixing` é uma janela de **um dia**: a Data Inicial sai "Não
Aplicável" (cláusula 4.2.j) e só a Final é impressa. Diferentes, imprime as duas. Repetir a mesma data
nas duas colunas diria que há uma média a apurar onde há uma cotação só.

### O eixo da segregação

O termo de moeda não tem mercadoria, então o eixo do meio é a **Moeda Base** — a moeda **estrangeira**
do par, já que a Moeda Cotada é fixa em BRL (cláusula 3.d). Ler sempre a `Quantity Currency` faria um
deal cotado em BRL sair com BRL nas duas pontas e o Valor Base deixaria de ser o montante que a
cláusula 4.2.m define.

Isso entrou como um parâmetro **`merc_fn`** no `_conf_segregate` **e** no `_conf_pick_eligible`, não
como uma segunda função de segregação: o eixo tem de ser o mesmo nos dois, senão a tela lista um grupo
cujo link abre 404. A Taxa de Conversão e o Tipo saem do cadastro **`fxo-conv-rate`**, o mesmo do FXO —
não há uma segunda tabela de moedas para manter.

### O PDF

`confirmation_pdfs.word_html_pdf(doc_html)` é o gerador genérico: recebe o HTML do documento **já
renderizado** (o mesmo string que vira o `.doc`) e não sabe de que produto é a confirmação. O
`opcao_fx_pdf` passou a delegar para ele — a implementação que existia sempre foi genérica, só tinha
nome de FXO. É o padrão do §139: o texto do Word sai **uma** vez, do template.

### Limitação conhecida

O XML sai com um aviso: sem `Rate` não há `notional × strike` para somar, então `valor` fica zerado. É
consequência do produto (a taxa só existe na Strike Set Date), não um defeito de leitura — o aviso
aparece no painel ao salvar.

### Verificação

`scripts/tests/check_fwdstart_conf.py` (8 seções), renderizando o documento de verdade pelo endpoint e
lendo as células do Anexo I pelo `data-k`.

---

## §204 — Coluna Strike no NDF FWD Start, e o XML convertendo pelo strike

### A coluna

`Strike` entrou **entre Strike Set Offset e Instrument** (índice 17), vinda da API. É a inserção que a
CLAUDE.md marca como perigosa (§132): tudo com índice ≥ 17 subiu um, e as listas **posicionais** têm de
subir juntas, senão a tela grava o valor de uma coluna no campo de outra sem erro nenhum.

Os lugares tocados: CSS `nth-child`, `<th>` do cabeçalho, `<th>` da linha de filtros, `COL_TO_JSON_FIELD`,
`AMEND_FIELD_COLS`, `dealJsonToRow`, `ND_COL_KEYS`, `columnDefs` (os `targets` do Is BRR Fixed e do par
Rate+Maker), `columnLabels` (mais a guarda `index + 2 === 26` do Rate), as opções da edição em massa,
`SF_COLS`, `SF_LABEL_TO_FIELD`, `extractRowDeal`, `rowDataToNdfDeal`, o preenchimento e o
`arBuildDeal` do modal de nova linha (com o campo `#ar-strike`), e o `rowMaker`, que foi de `d[30]` para
`d[31]`.

O `Strike` da API é gravado na **mesma convenção do Rate** — já invertido para moeda fraca. Divergir do
Rate faria a coluna da tela e o valor do arquivo contarem histórias diferentes.

### O XML: a fórmula da mercadoria não serve para moeda

O `_conf_ndf_xml` calculava `valorEstrangeiro = Σ notional × strike`. Isso vale para o termo de
**mercadoria**, onde o notional é uma QUANTIDADE e o strike um PREÇO. No termo de **moeda** não: o
notional já é um VALOR — em uma das duas moedas — e o strike é a taxa entre elas. A fórmula antiga
multiplicaria dólares pela taxa e chamaria o resultado, que está em reais, de "valor estrangeiro". O
arquivo sairia, e sairia errado.

Entrou um `legs_fn` opcional no builder, e o **`_conf_fx_legs`** para o NDF de moeda:

| Notional cotado em | valorEstrangeiro | valor (BRL) |
|---|---|---|
| moeda base | o próprio notional | notional × strike |
| BRL | notional ÷ strike | o próprio notional |

Sem strike a perna fica de fora **com aviso** — que era o caso do forward start antes desta coluna
existir (§203 registrava isso como limitação; deixa de ser).

A moeda do XML passa a ser a **Moeda Base do grupo** (parâmetro `ccy` explícito), não a Quantity
Currency, que pode ser o próprio BRL.

### Verificação

Seção 9 do `check_fwdstart_conf.py`: as três listas posicionais com 32 colunas e o `Strike` no índice 17
nas três, o Maker em 31, o `dtCol` do smart filter, a conversão nos **dois** sentidos de cotação, e a
prova de que a fórmula da mercadoria continua intacta para quem não passa `legs_fn`.

---

## §205 — Pay/Rec: o SWAP conciliava bruto contra líquido

A linha de SWAP ficava **pendente todo dia** por uma diferença que era imposto. O lado interno
(`cashflows`) traz o valor **bruto**; o histórico de mensagens traz o que de fato saiu da conta, que é o
**líquido**. O caso reportado: `-55.462,81` interno contra `-47.143,38` do cliente — exatamente **15%**.

Agora, quando o net do trade é um **pagamento** (negativo), o valor interno é descontado do IR antes de
conciliar. Quatro decisões que valem registrar:

**A alíquota vem do `_ops_swap_ir_rate`, do `routes`.** É a MESMA tabela regressiva (`swap-ir-term`) e a
MESMA lista de isenções (`swap-ir-client`) que o Trade Level e o Settlement Advice de Swap usam. Uma
segunda cópia aqui faria o Pay/Rec conciliar contra uma alíquota e as outras telas imprimirem outra, para
o mesmo swap no mesmo dia. O import é **tardio** de propósito — o `routes` importa este módulo, e
importá-lo no topo fecharia o ciclo.

**"É banco?" quem responde é o cadastro.** Os bancos e as entidades JPM estão registrados em
`swap-ir-client` com 0%, então banco novo entra pela tela `/mapping` em vez de por um `if` no código.

**O IR incide sobre o NET do trade, não perna a perna** — mesmo tratamento que o COMM TER já tinha, e
pela mesma razão: tributar perna a perna cobraria imposto de valores que se anulam dentro do próprio
trade.

**O prazo conta até a data da CONCILIAÇÃO**, não até `hoje`. Reexecutar um dia antigo tem de devolver o
mesmo número que já foi conferido; com `hoje` o trade mudaria de faixa e o valor mudaria sozinho.

O **Trade Date é a coluna K** do arquivo, lida por `_rec_col` — nome do cabeçalho quando ele existe,
posição quando não. **Sem data a linha fica bruta**, de propósito: sem prazo não há faixa, e descontar
por chute é pior que deixar a linha acusar a diferença.

### Verificação

Seção 6 do `check_payrec_run.py`: o caso reportado ao centavo, a regressividade (uma alíquota fixa
passaria no primeiro teste e erraria em todo trade novo), o banco isento, o recebimento intacto, o net do
trade, a data da conciliação mandando, o COMM TER inalterado, e a prova estrutural de que **não há tabela
de faixas recopiada** neste módulo.

**Adendo ao §205** — a linha "sumindo" do Pay/Rec é o conserto funcionando: antes havia **duas órfãs**
(o interno bruto sem par e o TED líquido do cliente sem par); agora as duas pontas falam o mesmo valor e
viram **uma linha em Settled**. Nenhuma linha JPM desaparece do resultado — o `_reconcile` sempre emite
uma entrada por linha JPM, casada ou não —, então "sumiu do Pending Payment" só pode significar
conciliou. A coluna K chega em **`yyyy-mm-dd`** (confirmado); o parser cobre ISO, `dd/mm/aaaa`,
`dd/mm/aa`, `mm/dd/aaaa`, `aaaammdd` e o datetime cru do Excel, e os dois primeiros estão travados no
teste — um formato não reconhecido vira "sem data" e a linha fica bruta, sem erro nenhum.

---

## §206 — About atualizada, e um teste para ela não envelhecer de novo

A About descrevia o sistema de meses atrás. Ela não quebra quando fica velha — só passa a **mentir**, e é
a única descrição do produto que alguém de fora lê.

### O que entrou

**12 cartas novas**, cada uma no seu grupo do menu:

* *New Deals* — NDF Vanilla, Deals Monitor e **Confirmações de Cliente** (o documento por contraparte ×
  ativo, Word + PDF + XML no Inventory, com painel, ciclo e checklist — cobrindo NDF Commodities, Opções
  de Commodities, FXO e o Termo de Moeda a termo);
* *Daily Settlement* — **Settlement Advice de Swap**, **Settlement Advice de Termo de Commodities** e
  **Mensageria B3**;
* *Live Position* — Swap Cashflow e Swap Premium;
* *Apps* — Electronic Inventory, Support Center e Metrics;
* *Data Base* — **Mapping**, com o ponto que importa: 22 cadastros, e editar vale na próxima requisição,
  sem restart e sem tocar em código.

**Três descrições que tinham ficado para trás** foram reescritas: NDF Forward Start (colunas Strike e
Strike Set Offset, geração de confirmação), Other Products Summary (cards de conciliação, Trade Level,
TED) e Pay/Rec (o IR regressivo do swap).

O **fluxo "Como funciona" parava no mapeamento** — que era o fim do ciclo quando foi escrito. Ganhou dois
passos, Confirmação e Liquidação, e a linha passou a `flex-wrap` para os seis caberem.

Tudo com `data-lang` e tradução nos **três** idiomas. No caminho apareceu um órfão antigo: a chave
`page-access` do menu nunca teve tradução — o item aparecia em inglês no ES e no BR.

### Verificação

`scripts/tests/check_about_page.py` (novo, 6 seções), que **renderiza a página pelo endpoint** e prende as
quatro formas de ela apodrecer em silêncio: carta apontando para 404, ícone que não existe no pacote
Tabler (já aconteceu — `ti-currency-exchange`), chave `data-lang` sem tradução (o texto do HTML sobrevive
em pt-BR, então o EN e o ES saem em português e ninguém reclama) e **feature sem carta**.

Esta última é a única que exige manutenção: a lista `MUST` enumera as páginas que a About tem de citar.
Página nova no menu que for para valer entra lá também — ou o teste falha e lembra.

---

## §207 — O aviso das 19h queimava o horário quando o envio falhava

Relato: "os e-mails de Pending Action do Deals Monitor não estão funcionando nos horários estipulados".

O agendamento em si estava certo — simulando um dia inteiro com relógio controlado, os disparos das 19h00
e 19h30 saem na hora e o catch-up recupera os slots quando a instância sobe depois do horário. **O defeito
estava no caminho do envio.**

### A causa

A reserva do slot é feita **antes** do envio — é o que impede dois processos de mandarem o mesmo aviso. Só
que, se o envio falhasse, o slot ficava reservado assim mesmo. E como o catch-up consulta a **mesma**
lista, o aviso daquele horário estava perdido para sempre: nem o restart o trazia de volta. **Uma queda de
SMTP de um minuto custava o aviso do dia inteiro**, sem nada em lugar nenhum para explicar.

O mesmo valia para o caso de destinatário em branco: o horário passava, o slot era queimado, e cadastrar o
destinatário depois não trazia o aviso daquele dia.

### O conserto

`_ndm_pending_release_slot` **devolve** o slot quando o aviso não saiu, e o `_ndm_pending_catch_up` passou
a rodar **a cada volta do laço**, não só no start — ele só dispara slots de hoje que já passaram e que
ninguém reivindicou, então num dia normal não faz nada, e é ele que retenta o horário devolvido.

`empty` (nada pendente) **mantém** a reserva: é desfecho legítimo, e retentar seria perseguir o dia inteiro
um e-mail que não tem o que dizer.

### E o que faltava para saber

A única evidência de que a rotina rodou era uma linha de log no servidor, que ninguém lê — por isso "não
está funcionando" não tinha resposta. Agora cada disparo grava o desfecho (`enviado`, `empty`, ou a
mensagem do erro) e o card **Deals Monitor** do Control Panel mostra, ao lado dos destinatários que já são
editados ali: **último disparo com o resultado** (verde saiu · azul rodou sem pendência · vermelho falhou)
e **o próximo horário**, com a hora atual em Brasília ao lado — que é o que responde a outra metade da
pergunta, se o relógio do servidor está onde se pensa.

### Verificação

`scripts/tests/check_ndm_pending_sched.py` (novo, 7 seções), com relógio, SMTP e destinatários stubados: o
dia normal sem repetição, o restart às 20h recuperando os dois slots, o SMTP caindo e o horário sendo
retentado **sem duplicar**, o destinatário cadastrado depois ainda recebendo o aviso do dia, o `empty`
mantendo a reserva, e o status publicado pelo endpoint que a tela consome.

---

## §208 — Coluna de Actions no Settlement Advice de Swap

Edit (modal), Confirm e Delete por linha, no padrão das páginas de New Deals.

### A parte perigosa: o visualizador é compartilhado

`live-position-swap-characteristics.js` serve **cinco páginas**. Ele tinha duas colunas fixas à esquerda
(checkbox e Status) e esse `2` aparecia como **literal em seis lugares**: o filtro por coluna
(`data-col`), o `columns` do DataTables, o `slice` do menu de colunas, o `data-column` do mesmo menu, os
chips do smart filter e o `exportFromData`. Acrescentar uma coluna e esquecer um deles faz o filtro
passar a filtrar a **coluna vizinha** — sem erro nenhum na tela.

Os seis viraram **`LEAD`**, calculado uma vez a partir de `data-actions` no `#swapchar-page`. A coluna é
**opt-in**: as outras quatro páginas não têm o atributo e não mudaram — e o teste prende isso, arquivo
por arquivo.

O compartilhado **desenha** os botões e entrega o clique (`window.scRowAction`); o que cada um **faz** é
da página, porque só ela tem endpoint para gravar. Mesma regra do Print Advice (§184).

### As edições valem no aviso IMPRESSO, não só na tela

Aqui está o ponto. A linha é derivada de cinco arquivos; a correção vai para um **overlay do dia**, ao
lado do overlay do Settlement Summary — reimportar o batch não a apaga, e nada do que veio da B3/Athena
é sobrescrito. A chave é o **Número de Contrato**, não a posição na tela (a tabela ordena por cliente).

O overlay sincroniza as **células e os números crus** (`_SWADV_NUM_FIELDS`): o aviso impresso lê os
crus, então corrigir só a célula deixaria a tela certa e o documento do cliente errado — a divergência
que este módulo inteiro existe para evitar. Tela e aviso passaram a ler o mesmo `_swadv_items`.

**O parser tem de aceitar os dois formatos.** A tabela mostra em US (`12,345.67`) e o aviso imprime em BR
(`R$ 12.345,67`), então o operador digita ora um, ora outro. `_mtm_parse_num` lê só US e transforma
`12.345,67` em **12,345** — o aviso sairia com um valor mil vezes menor, sem nada na tela acusando. Por
isso o overlay usa `_conf_to_float`, que entende os dois. (Verificado nos dois sentidos.)

Só as células **alteradas** vão no payload: gravar as 15 congelaria a linha nos valores de hoje e amanhã
ela deixaria de acompanhar os arquivos.

### Confirm e Delete

**Confirm** marca `Sent` — e o status vive no overlay do Settlement Summary, por **contraparte × LOB ×
produto**, porque é assim que o aviso é emitido: um documento por destinatário. Confirmar uma linha
confirma o aviso a que ela pertence, e a tela **diz quantas linhas mudaram junto** em vez de deixar a
surpresa acontecer.

**Delete** marca a linha como apagada no overlay — o contrato continua existindo na B3 e no Athena; o que
saiu foi a linha *deste aviso*. O endpoint aceita `undo`.

### Verificação

Seções 13 e 14 do `check_swap_advice.py`: a coluna opt-in, os seis literais que não podem ter sobrado, as
sete páginas irmãs seguindo sem Actions, a chave travada no modal, e a edição chegando ao aviso impresso
com o parser tolerante.

**Adendo ao §208** — os botões de ação saíam **ovais**. `rounded-circle` arredonda em 50% da **caixa**, e
a caixa do `.btn-sm` é mais larga que alta por causa do padding lateral — o círculo vira elipse. A classe
`.sc-row-act` trava **32×32** (com `min/max` junto de `width/height`, senão um `min-width` de tema volta a
esticar um dos três e a fileira sai desalinhada) e aplica `border-radius: 10px` — o **mesmo** raio do
`.ops-row-act` do Other Products Summary, que mostra a mesma linha de liquidação: formatos diferentes nas
duas telas leem como sistemas diferentes. Travado no teste, inclusive a paridade do raio entre as duas
páginas.

---

## §209 — Valor Base saía cem vezes maior no aviso

`280,000,000.00` na tela, `R$ 28.000.000.000,00` no aviso impresso. Duas leituras do MESMO dado, que é o
defeito que este módulo mais repete.

O arquivo de **posição** escreve a vírgula como separador **decimal** (`280000000,00`), sem separador de
milhar. A célula da tela passava por `_swapchar_fmt_value`, que sabe disso; o número cru — o que o aviso
imprime — passava por `_mtm_parse_num`, que trata a vírgula como **milhar** e devolve 28 bilhões para o
mesmo texto. Cem vezes.

A leitura virou uma só: **`_swapchar_value_num`**, usada pelo formatador da célula **e** pelo
`_swadv_collect`. Texto não numérico continua passando inteiro na célula e devolvendo `None` no cru —
`None` e não `0`, senão um campo ilegível viraria um valor base zerado no contrato do cliente.

Os campos vizinhos ficaram como estavam, e por um motivo: `curva_banco`, `curva_cliente` e `bruto` vêm do
**Athena**, em formato US, e a célula deles é o texto cru sem reformatação — a leitura bate. O descompasso
só existia onde a célula era **reformatada** por uma regra e o cru lido por outra.

### Verificação

Seção 15 do `check_swap_advice.py`: o número reportado, a célula e o cru batendo para quatro formatos, o
vazio que não vira zero, e a prova estrutural de que o `valor_base` não pode voltar ao parser de uso geral.

---

## §210 — Forward Rate mostrava 6 casas; o arquivo tem mais

No Trade Level do NDF Summary a taxa forward saía com **seis casas fixas**
(`_ndfc_fmt_fwd` → `'{:.6f}'`), enquanto o SETTLEMENT.xlsx traz todas as que o sistema de origem
calculou. O Fixing Rate, que é `forward ± settlement/notional`, **já era calculado com o valor cheio** e
também impresso com seis — então a taxa na tela não explicava o fixing ao lado dela, e a diferença que a
mesa precisa conferir ficava dentro do arredondamento.

O valor **cru nunca foi truncado**: o importador guarda o texto do openpyxl e `_ndfc_valnum` lê a
precisão inteira. O que mudou é só a **exibição**.

* **Forward Rate** — mostra as casas que o texto do arquivo traz, com **piso de 6**
  (`_ndfc_text_decimals`). Piso e não valor fixo: uma taxa curta virando `5.4` faria a coluna deixar de
  ler como taxa.
* **Fixing Rate** — a **mesma** precisão do forward que o gerou. Menos casas esconderia a diferença que a
  conta produziu; mais inventaria dígitos que nenhuma das entradas tem.

O `round(..., 6)` do `_ndfc_opb3_rescue` **não** mudou: aquilo é tolerância de casamento contra a Live
Position, não exibição.

E a coluna precisou de largura: com `scrollX` ligado mas sem `min-width`, a tabela se acomoda em 100% do
card e a taxa longa **quebra em duas linhas** — uma taxa partida ao meio parece um valor diferente, o que
é pior que a arredondada que se acabou de corrigir. `min-width: 165px` + `nowrap` nas colunas 12 e 15.

### Verificação

`scripts/tests/check_ndfsum_fwd_rate.py` (novo, 4 seções), incluindo a conferência **posicional** de que
o CSS aponta para as colunas certas (contando os `<th>` do cabeçalho) e a prova de que o cálculo continua
lendo o campo cru.

**Adendo ao §210** — o piso subiu de 6 para **8 casas** (`_NDFC_FWD_MIN_DEC`), a pedido da mesa, e o
Fixing Rate acompanha. Vale registrar o que o piso significa: acima dele valem as casas que o **arquivo**
tiver; quando ele traz só seis, as duas últimas saem **zero** — e esse zero é informação, porque diz que
a precisão que falta está na **origem**, não na formatação da tela. Se a coluna continuar em `...00`
depois do restart, o `SETTLEMENT.xlsx` está mesmo gravando seis casas, e aí a precisão tem de vir do
arquivo (ou de outra coluna dele), não daqui.

---

## §211 — Notificação do Other Publisher levava à tela errada

Gerar o arquivo pelo Send em **Daily Settlement › NDF › Other Publisher** e clicar no aviso abria o
**New Deals › NDF › Other Publisher**.

O rótulo `page` da notificação é a chave de **duas** coisas: para onde o clique leva e **quem enxerga o
aviso** (`api_get_notifications` filtra pelo acesso à página que o rótulo aponta). A tela de liquidação
usava `'NDF Other Publisher'`, que é o rótulo do New Deals (vem do `_GENERIC_ND_PRODUCTS`) — então, além
do destino errado, o aviso **sumia** para quem tem a tela de liquidação liberada e a de New Deals não.

Rótulo próprio: **`_NOTIF_DS_OTHERPUB = 'NDF Other Publisher (Settlement)'`**, usado nos quatro pontos da
tela (confirm, edit, delete e Send) e apontando para `/ndf-other-publisher`.

### O mapa existe TRÊS vezes

`_NOTIF_PAGE_URL` (routes, para o filtro de acesso), `PAGE_URL` em `partials/topbar.html` (clique no
sino) e `PAGE_URL` em `static/js/sw-push.js` (clique no push do sistema). Eles **já estavam divergindo**:
o `sw-push.js` não tinha `NDF Vanilla` nem `Intrag Swap`, então um clique no push desses dois não ia a
lugar nenhum enquanto o mesmo clique no sino funcionava. Os três foram sincronizados.

### Verificação

`scripts/tests/check_notif_page_url.py` (novo): os três mapas com as mesmas chaves e destinos, todo
destino sendo página do menu, nenhum destino repetido (rótulo duplicado sem querer), e as quatro
notificações da tela de liquidação usando a constante.

---

## §212 — BRT_IPE asiático: o código depende da distância até a liquidação

Toda asiática de `BRT_IPE` saía **`CO1-2`**, fixo. A regra é outra: o que decide é quantos **meses de
calendário** o contrato está à frente da **data de liquidação**.

- contrato no **mês seguinte** → o código do mês (`CO"MY"` → `COH7`);
- **dois meses ou mais** → `CO1-2`.

Os exemplos que definiram a regra: liquidação `05/01/2027` com contrato `Mar27` (+2) → `CO1-2`;
liquidação `02/02/2027` com o mesmo `Mar27` (+1) → `COH7`. **Vanilla não mudou** — é sempre o código do
mês.

O dia não entra na conta: `28/02/2027` continua sendo +1 para `Mar27`. Sem data de liquidação legível a
resposta é `CO1-2`, que é exatamente o comportamento anterior.

### Os dois códigos viraram cadastro

A linha `SPECIAL` do **Commodities × B3** vinha com o `B3 CODE` vazio e os dois códigos moravam no
código-fonte, em três lugares. Agora:

| coluna | conteúdo | quando sai |
| --- | --- | --- |
| `B3 CODE` | `CO"MY"` | vanilla, e asiática com contrato no mês seguinte |
| `B3 CODE FAR` (nova) | `CO1-2` | asiática com contrato dois meses ou mais à frente |

`SPECIAL` continua sendo SPECIAL porque **qual dos dois sai é lógica**, não de-para. O `upgrade` do
mapping preenche as duas colunas quando estão vazias, então a instância que já tem o arquivo em disco
passa a valer sem script de migração.

**Consequência a saber:** apagar a linha `SPECIAL` do cadastro faz o `BRT_IPE` cair na regra genérica de
prefixo e emitir `BRT` + mês/ano (`BRTZ6`) — um código errado que *se parece* com um código certo. Está
preso no `check_b3_pattern.py` para não virar surpresa.

### A regra vive em TRÊS lugares

`otc_boxparse.calculate_b3_id` (servidor) e as duas cópias JS (`otc-fileupload.js` e
`deals-processing-table.js`). A data de liquidação passou a ser lida **antes** do `b3Id` nas três, e os
formulários de Add/Edit das duas páginas de commodities recalculam o Underlying Asset quando o
`#ar-settledate` muda — sem isso o código ficaria velho na tela.

### Verificação

`check_boxparse.py` compara o Python com o `otc-fileupload.js` em todos os combos × 8 datas de
liquidação; `check_b3_pattern.py` ganhou a seção **5b**, que roda as **duas** cópias JS contra o Python
nos casos do BRT_IPE — é ela que pega a divergência entre os dois arquivos JS (já aconteceu no §164).

---

## §213 — Operations B3: o que entra na liquidação, e por qual das duas visões

Duas correções na mesma cadeia, as duas erravam **número** sem erro nenhum na tela.

### 1. A operação cancelada era somada

Uma linha com **Status B3 = `CANCELADA: COMANDADA`** continua no arquivo da B3 com o valor cheio. Ela
entrava no Settlement B3 do NDF Summary e nos cards de conciliação — um caixa que não vai acontecer,
num total que ninguém conseguia explicar linha a linha.

O cadastro **`swap-b3-events` virou `opb3-events` ("Operations B3 Events")** e deixou de ser uma lista de
Tipo Operação para ser uma **regra** sobre as três colunas que decidem isso:

| coluna | |
| --- | --- |
| `TIPO TITULO` | TER · OPC · SWAP · COE — **em branco = qualquer** |
| `TIPO OPERACAO` | domínio aberto (sugestões, não trava) |
| `STATUS B3` | domínio aberto |
| `USE` | **Consider** / **Disregard** (em branco = Consider) |

Precedência em `_opb3_settle_ok`: **Disregard vence sempre**; depois, um Tipo Título que tenha ao menos
um Consider próprio vira **lista branca** (é o caso do SWAP: só amortização, juros e prêmio); Tipo Título
sem nenhum Consider **não é filtrado** (é como TER e OPC se comportam). O casamento ignora caixa, acento
e **pontuação** — `CANCELADA: COMANDADA` e `CANCELADA:COMANDADA` são a mesma coisa, e comparar o texto
cru fazia a regra simplesmente não valer.

O seed reproduz o comportamento anterior (as três linhas de SWAP) e acrescenta a linha do cancelamento,
sem Tipo Título, que vale para os quatro produtos de uma vez.

**Mudança de semântica a saber:** antes, esvaziar a tabela significava "nenhum swap entra". Hoje isso se
**diz**: uma linha `SWAP` / resto em branco / `Disregard`. Tabela vazia agora não filtra nada — o que
distingue "não quero nenhum" de "ainda não cadastrei".

A regra é aplicada em **cinco** consumidores (`_ops_swap_settling`, `_ndfsum_collect`, `_ndfadv_collect`,
`_ndfc_opb3_resgates` e a mensageria) via `_opb3_settle_rows`/`_opb3_settle_ok`. A **página** Operations
B3 segue mostrando o arquivo inteiro: ela é a fonte, e esconder a linha cancelada lá deixaria o time sem
onde vê-la.

### 2. O intragrupo vinha com o sinal invertido

Um negócio JPM × MGT chega pelos **dois** arquivos de casa que alimentam o Operations B3, espelhado:
`Conta 73760.00-9 / Conta Contraparte 04880.00-6` com o valor de uma ponta, e as contas invertidas com o
sinal trocado. Procurando só pelo Título, quem decidia o sinal era a **ordem de chegada no arquivo** —
metade dos intragrupo saía com o Settlement B3 invertido contra a coluna SETTLEMENT, e a diferença dava o
**dobro** do valor.

`_ndfsum_b3_legs` indexa por **três** chaves, da mais específica para a mais frouxa:
`(Título, Conta, Conta Contraparte)` → `(Título, Conta)` → `Título`. A conta de casa sai do `LEGAL` da
linha e a da contraparte sai do **nome dela** (`_opb3_legal_side`), que no intragrupo é a outra entidade
JPM. Resgate continua vencendo qualquer outro Tipo Operação do mesmo Título.

### 3. O nome da contraparte passou a sair do Cpty SPN

No swap o nome vinha do `CounterParty` do Athena; no termo de commodities, do `Nome da Contraparte` da
posição. Dois **textos livres**, escritos por sistemas diferentes, que divergem em pontuação e sufixo —
o mesmo cliente virava duas linhas no Settlement Summary, e não parecia defeito, parecia cliente
repetido.

A coluna **`Cpty SPN`** do OTM Settlements é um identificador e existe igual dos dois lados.
`_otm_cpty_name` resolve nesta ordem: cadastro **`le-spn`** (entidade nossa não está no Reference Data
como contraparte) → **Reference Data por SPN**. Não achou = string vazia, e quem chama mantém o nome que
já tinha. O SPN da linha do aviso também passa a sair do OTM, sem o caminho de volta nome → SPN, que
errava em toda diferença de pontuação. O omnibus por CNPJ (§197) segue como segunda tentativa.

O nome resolvido é o **mesmo** que vai para o cadastro de IR (`swap-ir-client`) — mostrar um nome e casar
a alíquota por outro deixaria quem edita o cadastro registrando o texto que vê, sem efeito nenhum.

### 4. O card de Swap contava Cashflow como Maturity

Um swap bullet vencendo hoje aparece **também** como evento na DFLUXO — é o mesmo pagamento, e conta como
Maturity. A dedupe existe para isso, e a chave era o **"Código Identificador"** — que no arquivo real é o
**LOB** (`CEM`) e se repete em todas as linhas do dia. Um bullet de CEM vencendo apagava **todo** cashflow
de CEM da contagem: o card mostrava `Cashflow 0 · Maturity 1` com um evento de fluxo liquidando na mesma
data, e o zero passava por "não teve fluxo hoje".

A junção passou a ser pelo **CÓDIGO DO CONTRATO** (`_OPS_SWAP_JOIN_TOKENS`), que tem nomes diferentes nos
dois arquivos: `Contrato` na DPOSICAO-SWAP e `Código do contrato` na DFLUXO. Sem a coluna, a dedupe não
roda e a rotina **conta a mais** (com um `warning`) — um Cashflow sobrando aparece na tela e alguém
pergunta; um Cashflow faltando passa por normal.

### Verificação

`scripts/tests/check_opb3_events.py` (novo) cobre 1 e 2; a seção **6** do `check_ops_trade_swap.py` cobre
3; a seção **17** do `check_ops_summary.py` cobre 4.

---

## §214 — Pending Confirmation: atualização em massa por coluna

A barra de ações só sabia aplicar **uma** coisa em massa — o Pending Status. Qualquer outra coluna exigia
abrir o modal linha a linha.

Agora é o modelo das páginas de New Deals: escolhe-se a **coluna** e o campo de valor à esquerda se
adapta ao tipo dela.

| tipo | colunas | como aparece |
| --- | --- | --- |
| `date` | Trade Date · Maturity Date · EA · Send Date · Return Date | máscara `dd/mm/yyyy` (flatpickr `d/m/Y`, a mesma do modal) — não se digitam as barras |
| `select` | LOB · Product Type · Pending Status · Signature Type | lista fechada; a de Signature Type sai do **próprio Reference Data**, então uma assinatura nova aparece sozinha |
| `refdata` | SPN · Client | autocomplete do Reference Data, o mesmo do modal de edição |
| `text` | Break Reason · Comments · FepWeb ID · Pendência | texto livre |

### O que fica de FORA da lista, e por quê

- **Status, Aging, Owner, Economic Group** — são **derivadas**. Digitar por cima cria um valor que a
  próxima gravação desfaz, sem avisar.
- **Trade Number** — é a **chave** da linha no banco (`_pc_upsert_row` grava por ela). Aplicar o mesmo
  número em várias linhas as fundiria numa só, e isso não tem desfazer.

### O recálculo é do SERVIDOR

`PC_CASCADE` diz qual coluna dispara o quê:

- **SPN / Client** → identidade da contraparte: o par SPN↔Client, Owner, Economic Group e Signature Type,
  todos do Reference Data;
- **Trade Date / Maturity Date** → prazo e idade: Aging, Status e o **Pending Status**, que depende de
  `Maturity − Trade ≤ 60` (prazo curto → `Exception Digital Fep Web` + Status `Ok`, e a linha migra para
  o banco `ok`).

O recálculo roda no endpoint novo **`/api/pending-confirmation/derive`** (`_pc_derive_row`), que reusa
`_pc_refdata_lookup`, `_pc_aging_band_label` e `_pc_signature_status` — as **mesmas** funções da
importação do Pending Update. Uma cópia em JavaScript faria a mesma operação sair com um Pending Status
pelo arquivo e outro por uma edição na tela, e as duas telas mostrariam números diferentes do mesmo dia.
Uma chamada por lote, não por linha.

Uma derivada só é sobrescrita quando o servidor tem resposta: sem contraparte no Reference Data, apagar o
Owner que já estava lá seria perder informação por causa de um cadastro faltando. Se o `/derive` falhar, o
valor escolhido é aplicado mesmo assim e a tela **diz** que as derivadas não foram recalculadas — melhor
do que ficar com metade da mudança e ar de sucesso.

### Verificação

`scripts/tests/check_pc_mass_update.py` (novo).

---

## §215 — Pending Confirmation: o card de Total, e os cards deixando de depender da posição

A linha de widgets tinha seis cards, um por faixa de aging. Faltava o número que mais se procura: o
total. Quem precisava dele somava os seis na mão, e a soma de dez linhas × seis cards erra.

Entrou um **sétimo card, Total**, no fim da linha. Ele não é uma faixa a mais: é a soma das seis, em
azul (`#0066cc`) para sair da rampa verde→vermelha das faixas, com moldura e fundo próprios. Uma sétima
cor dentro da rampa faria dele mais um nível de severidade aos olhos de quem só bate o olho.

Duas decisões que valem estar escritas:

**O Total soma o que os cards somam, e nada além.** Ele conta *dentro* do mesmo teste de faixa: uma linha
sem Aging não entra em faixa nenhuma e também não entra no total. Contar essas linhas só no total deixaria
o card fora da soma dos outros seis — e a primeira leitura de quem olha a tela é somar os cards. Um total
que não fecha com os vizinhos parece defeito mesmo quando está certo. (As linhas sem Aging já não
apareciam em card nenhum antes disso; o Total não piora nem melhora esse ponto, apenas não o contradiz.)

**Os cards passaram a se identificar pelo `data-pc-band`.** O `updateWidgets()` casava o resultado com o
card pelo **índice** do `querySelectorAll` contra o `RANGE_ORDER`. Inserir um card no meio — ou mover um —
deslocava em silêncio os números de todos os seguintes: nenhum erro no console, todos os cards
preenchidos, cada um com o número do vizinho. Acrescentar o sétimo card no fim teria funcionado por sorte;
o próximo, não. Agora cada `.card-body` declara a sua faixa e o JS lê o atributo.

### Layout

O Bootstrap não tem `row-cols-7` (o grid dele para em 6), então a largura de 1/7 em telas ≥1400px vem do
CSS da própria página e o `row-cols-xxl-6` **saiu** do markup — deixá-lo lá poria os dois disputando
especificidade, que é o tipo de coisa que funciona hoje e quebra num upgrade de tema. Abaixo disso o
`row-cols-md-3` continua valendo e o Total cai sozinho na última linha, o que lê bem: ele é o fecho.

### Verificação

`scripts/tests/check_pc_widgets.py` (novo). A seção 4 roda a contagem **real** do arquivo no `jsc`, com
linhas sintéticas no lugar da DataTable — reescrevê-la em Python seria uma terceira cópia da regra, que é
exatamente o que o teste deveria pegar.

---

## §216 — Reconciliação de FXO: o script da mesa virou página

A mesa rodava um `recon_fxo.py` na mão: pedia a data no terminal, baixava o relatório EOD da Athena e
lia a DPOSICAO da rede para dois `.xlsx` numa pasta `test\`, reconciliava e cuspia um terceiro `.xlsx`
com o NOK pintado. Agora é a página **Reconciliations › FXO** (`/reconciliation-fxo`), com o motor em
`apps/pages/recon_fxo.py` e a regra de comparação intacta, campo a campo.

### O que ela compara

A base âncora é a **nossa** conta (`73760009`) e só **TAXAS DE CAMBIO** dentro da DPOSICAO. A chave do
match é a `Combinação de operações` contra o `DealID` da Athena e, para as chaves que não existem em
DealID nenhum, contra o `MatchingDealID` — nessa ordem, porque sem a prioridade a mesma operação casa
duas vezes e o desempate vira sorte. Onze campos saem com OK/NOK: direção, Put/Call, contraparte,
quantidade, prêmio (tolerância de 0,67), strike, trade date, vencimento, o último e o primeiro fixing, e
Asian/European.

O **Status da linha** é derivado dos onze, com uma regra que vale registrar: **'Sem match' vence 'NOK'**.
Sem a outra ponta os onze status dão NOK de uma vez, e contar isso como divergência de campo esconde o
que de fato houve — a operação não existe do outro lado.

### O que saiu do script, e por quê

**O Excel.** O resultado é a página: quatro cards contam Total / OK / NOK / Sem match e filtram a tabela
ao clique, uma faixa de chips diz **qual campo** está quebrando (numa tabela de 38 colunas, "40 linhas com
NOK" não indica por onde começar), e a célula NOK vem pintada. O arquivo era um passo a mais entre rodar
e olhar, e cada rodada deixava um arquivo diferente na pasta de alguém.

**Os dois XLSX intermediários.** A Parte A gravava e a Parte B relia. Isso também matou a aba
`OPC_260702_DPOSICAO` cravada no código — o nome da aba de UM dia específico, que só funcionava porque
havia um resolvedor por semelhança atrás dele.

**Os caminhos do Desktop de quem escreveu.** A DPOSICAO vem da MESMA raiz da rotina Save CETIP Files
(`CETIP_DEST_ROOT`), e o endereço da Athena entrou no cadastro `api-links` com o uso novo **Recon FXO** —
é outro Athena, o relatório EOD do `bob-reports`, não o `getTrades`. A data dele fica no **caminho**
(`AAAA-MM-DD`), que é exatamente o caso para o qual o placeholder existe: parâmetro de query nenhum
alcança ali.

**Os dois de-para que estavam no código**, que é o que mais importa aqui:

- **Counterparty → CNPJ: sai do Reference Data, e NÃO virou cadastro.** No código era uma planilha do
  OneDrive de uma pessoa, que o servidor não alcança. A primeira versão criou um `fxo-cpty-cnpj` vazio em
  `/mapping`; ele foi **removido no mesmo ciclo**, a pedido da mesa e com razão: seria uma segunda lista
  dos mesmos clientes, mantida à mão, envelhecendo em paralelo ao Reference Data — e nascendo vazia, a
  recon compararia nome com nome sem ninguém perceber. Agora `lookup_cnpj()` monta o de-para lendo o
  **Reference Data**: para cada linha com `TAX ID`, indexa **COUNTERPARTY**, **FX CASH ACCRONYM** e
  **SPN** apontando para o mesmo CNPJ (só dígitos dos dois lados, porque CETIP e Athena pontuam
  diferente). Cliente cadastrado uma vez serve as duas telas; cliente novo entra no Reference Data como
  sempre entrou. Se aparecer uma grafia que o Reference Data não conhece, o conserto é registrar o
  accronym lá — não abrir uma tabela nova.
- **`fxo-internal-cpty`** — a perna interna, que chega à Athena com o nome da mesa (o book) enquanto a
  CETIP registra o código do fundo. A coluna **`INVERT DIRECTION`** separa dois casos que não podem ser
  tratados juntos: `No` só troca o nome, e vale **sempre**; `Yes` é a perna **espelhada** (o Buy/Sell
  também veio invertido) e vale **só quando Ctpty e JPM Dir estão os dois NOK**, que é a assinatura da
  perna espelhada. Aplicar a segunda sempre inverteria a direção de operações que estavam certas — e um
  Buy virado em Sell numa recon é pior do que a divergência que ela ia mostrar.

### A tela, depois do primeiro uso

Ajustes que a mesa pediu vendo a página rodar, e que valem para qualquer tela desta família:

- **A data de referência abre em D-1 pelo calendário ANBIMA** (`_prev_anbima_bizday`), não em "ontem". A
  DPOSICAO é gerada no fechamento; abrir a página numa segunda-feira pedindo o domingo devolve um erro de
  arquivo inexistente que parece falha do sistema. Feriado e fim de semana entram na mesma conta.
- **50 linhas por página**, com 100 / 150 / 200 / All. A tabela tem 38 colunas: `All` num dia cheio
  trava o navegador, e é escolha de quem está olhando, não default.
- **Formato por natureza da coluna**: AMT e PREMIUM em `#,##0.00`, Strike em `#0.00000000` — oito casas
  porque é onde mora a divergência que a recon existe para achar. A formatação é **ortogonal**: a
  ordenação e o filtro usam o número cru, o `display` leva o texto formatado. Ordenar por texto colocaria
  `1.000,00` antes de `900,00`.
- **Status / OK / NOK como badge pill com gradiente** (success e error), e **sem o campo de busca global**
  no canto — a linha de filtro por coluna é mais precisa e o campo solto convidava a procurar um DealID
  na coluna errada.

### Um ponto em aberto para a mesa

Na europeia o de-para de estilo só traduz `SIMPLES_DATAS`. Se a DPOSICAO escrever **`NAO`** em vez de
deixar a Média Asiática em branco, a coluna Asian/European acusa NOK em toda opção europeia. O
classificador que absorveria `NAO`/`N`/`NONE` existe no script original e foi deixado **desligado** de
propósito — respeitei isso. Se o arquivo real vier assim, é uma linha a acrescentar no cadastro, não um
conserto de código. Está preso em teste para não virar surpresa.

### Verificação

`scripts/tests/check_recon_fxo.py` (novo). As duas bases são construídas no teste — inclusive a linha de
dados com **mais colunas que o cabeçalho**, que é o cronograma de fixing seguindo à direita sem título, e
o 'Texto para Colunas' que parte o **cabeçalho** junto com o dado.

---

## §217 — Manual Confirmations: a esteira de validação virou tela

Uma confirmação gerada precisa passar por mesas antes de ir ao cliente, e isso vivia numa planilha
(`MANUAIS.xlsx`). Agora são duas telas sob **Manual Confirmation**, e dois DuckDB
(`manual_confirmations_pending` e `manual_confirmations_ok`), com a mesma divisão do Pending Confirmation
e pela mesma razão: a tela abre lendo só o que ainda pede ação.

### A esteira

    (mapeada no New Deals) → Pending OTC → Pending MO e/ou Pending FO → Ok

Quem valida cada etapa sai do cadastro novo **`manual-conf-validation`**, por **Produto × LOB**, com
`REQUESTED` / `EXEMPT`. Termo e opção de commodities, FXO e NDF FWD Start passam por OTC e MO; swap e
opção de EDG passam também pelo FO. **LOB em branco é coringa** do produto — a maioria valida igual em
toda LOB, e exigir uma linha por LOB faria a tela pedir cadastro a cada LOB nova.

Três decisões que vale ter escritas:

**MO e FO correm em paralelo, não em fila.** As duas validam a mesma confirmação depois do OTC, e a
linha só fecha quando as duas pedidas responderem. Encadeá-las atrasaria a segunda por nada — e uma
confirmação parada nas duas aparece nos **dois** cards, porque mostrá-la só num esconderia trabalho da
outra mesa.

**O `Pending` e o `Aging Confirmação` são DERIVADOS**, recalculados na leitura a partir das colunas de
validação. Estão no banco porque vieram no arquivo, mas quem manda é o cálculo: uma coluna `Pending`
digitada discordaria das datas ao lado dela no primeiro reject, e a tela mostraria uma etapa que já
passou. O aging conta da **data de envio para o OTC**, não da data da operação — uma operação de três
meses atrás cuja confirmação saiu ontem não está atrasada.

**O reject de MO/FO limpa o que já foi validado.** A confirmação volta para Pending OTC, e o
`Conferido OTC` **e** as validações já dadas são apagadas: o documento vai ser refeito, e um
"VALIDADO p/ MO" carimbado sobre a versão anterior seria um aval que ninguém deu à versão nova. O
carimbo do reject fica na coluna da mesa que devolveu, com o SPN de quem devolveu. O aviso vai para
`brazil.otc.ops@jpmorgan.com` com o comentário — que é **obrigatório**, porque sem ele o e-mail chega
dizendo "refaça" e nada mais. A gravação vem **antes** do e-mail: a confirmação precisa voltar para o
OTC mesmo que o relay não responda, e a tela diz quando o aviso não saiu.

### De onde as linhas vêm

Do **mesmo** gancho que alimenta o Pending Confirmation: `_mc_save_from_deal` é chamado de dentro de
`_pc_save_from_deal`. Quem decide se um deal vira confirmação de cliente (perna interna? intragrupo?) é
aquela função, e repetir o teste criaria uma segunda resposta para a mesma pergunta — que é como as duas
telas passariam a discordar de quem tem confirmação pendente.

Só entram os **quatro** produtos que geram documento (`_MC_CONFIRMATION_SOURCES`). O recorte é pelo
`source` e **não** pelo Product Type: as três páginas genéricas de NDF gravam o mesmo `'NDF'`, e olhar o
Product Type traria Vanilla e Other Publisher junto com o FWD Start. O FWD Start é chaveado pelo **B3
ID**, como no Pending Confirmation — usar o Deal para todos deixaria justamente essas linhas sem carimbo,
sem erro nenhum.

### Os carimbos

- **Confirmação salva** (`/api/confirmation/*/save`) → `Data envio validação OTC`, e o endereço da tela
  de validação fica guardado na linha (coluna técnica `Confirmation Link`, fora da tabela). A data só é
  carimbada se estiver em branco: regerar o documento não pode reiniciar a idade de uma pendência de duas
  semanas. O link, ao contrário, é sempre reescrito. **Corrigido em §218:** o botão *Abrir* do Monitor
  não usa mais esse link — ele deriva a pasta da linha e abre o **PDF do Electronic Inventory**, senão as
  confirmações anteriores ao carimbo (justamente as que alguém precisa procurar) ficariam sem botão.
- **Confirmação validada no checklist** (`/api/confirmation/*/validate`) → `Conferido OTC` + `Time Stamp`
  com hora e **SPN da sessão**. A validação do OTC acontece na MESMA tela de checklist que já existia:
  uma segunda tela de validação do mesmo documento acabaria divergindo sobre o que foi conferido.

O SPN vem sempre da sessão, nunca do corpo do POST — aceitá-lo do cliente deixaria qualquer sessão
assinar por outra pessoa.

### As colunas

As três colunas de carimbo do arquivo se chamavam **todas** `Time Stamp`; no banco viraram
`Time Stamp OTC` / `MO` / `FO`, e a tela mostra as três com o rótulo curto, encostadas em quem validou.
O `Trade ID` aparecia **duas vezes** na lista original (cópia colada) — ficou uma, e é a chave da linha.

### Importação

`scripts/import_manual_confirmations.py` cria os dois bancos e carrega o `MANUAIS.xlsx`. O cabeçalho é
casado por semelhança (sem acento, caixa ou pontuação), e as três `Time Stamp` são resolvidas **pela
posição** — a que vem depois de `Conferido OTC` é a do OTC, e assim por diante: é a única informação que
as distingue no arquivo. O script **reescreve** os dois bancos, então rodar duas vezes não duplica. Sem
a planilha ele cria os bancos vazios e diz onde procurou.

**Isto é um passo obrigatório na instância do time**, e não um extra: `apps/static/data/db/` está no
`.gitignore`, então os dois bancos **não vêm no pull**. Sem rodar o script as duas telas abrem vazias e
não há nada errado com o código — o mesmo tipo de "não está funcionando" que os scripts de migração do
Pending Confirmation já produziram (§128).

### Verificação

`scripts/tests/check_manual_conf.py` (novo).

---

## §218 — A linha de filtro por coluna sumia com `scrollX`, e o card ficava branco

Duas armadilhas de tela que apareceram juntas nas páginas novas (Recon FXO e Manual Confirmations) e
valem para **qualquer** página futura, porque nenhuma das duas dá erro no console.

### 1. `scrollX` clona o cabeçalho

Com `scrollX: true` o DataTables desenha o cabeçalho **duas vezes**: o `<thead>` do `<table>` real fica
no corpo rolável (escondido) e uma **cópia** é montada dentro de `.dt-scroll-headInner`, que é a que o
usuário enxerga. Acrescentar a linha de filtro só no `<thead>` da tabela faz ela existir no DOM e **não
aparecer** — foi o que aconteceu nas duas páginas.

O jeito certo — e o mais simples — é **montar a linha ANTES do `.DataTable()`**. Com ela já no `<thead>`,
o DataTables leva as duas linhas juntas para onde o cabeçalho for, e não há cópia a sincronizar. É o que
o Pending Confirmation faz há tempo (lá a linha vem no HTML estático, `#column-search-inputs`).

Duas coisas acompanham:

- **`orderCellsTop: true`** — sem ele a ordenação passa a ser a da 2ª linha, e clicar no campo de filtro
  reordena a tabela;
- o CSS tem de mirar os três seletores (`#tabela thead`, `.dt-scroll-headInner thead`,
  `.dataTables_scrollHeadInner thead`), porque o nome do container mudou entre versões do DataTables.

Tentar acrescentar a linha **depois** do init foi o que falhou duas vezes: no `initComplete` o container
de scroll ainda não existe, e `api.table().node()` devolve a tabela do CORPO — cuja thead é justamente a
cópia oculta.

### 2. O `<style>` da página é carregado ANTES do CSS do tema

`layouts/base.html` põe o bloco `extra_css` **antes** do `head-css.html`. O `.card` do tema declara
`background-color`, `border`, `border-radius` **e** `color`; como ele vem depois, qualquer uma dessas
propriedades escrita sem `!important` numa regra da página é revertida.

O sintoma é traiçoeiro: no card de Total do Pending Confirmation as regras de **texto** tinham
`!important` e a do **fundo** não, então o cartão ficou branco com letra branca — em branco, sem título,
sem número, sem erro nenhum. Na Recon FXO os cards saíram brancos com moldura cinza pelo mesmo motivo.

**Regra prática, na ordem de preferência:**

1. **Não use `.card` para um widget seu.** O New Deals Monitor não usa: `.ndm-card` é um `<div>` com
   classe própria, e por isso nunca disputa nada. Foi para lá que a Recon FXO e as duas telas de Manual
   Confirmations migraram, e o problema sumiu junto com os `!important`.
2. Se o `.card` for inevitável (é o caso dos widgets do Pending Confirmation, que herdam padding e
   sombra dele), marque `background-color`, `background-image`, `border`, `border-radius` e `color`, e
   declare uma **cor sólida antes do gradiente** para o cartão nunca depender só da imagem de fundo.

Os testes `check_pc_widgets.py` e `check_recon_fxo.py` prendem cada um o seu caminho.

E uma regra que já estava no CLAUDE.md e eu tinha furado: a camada visual usa **`--ins-*` e `--vr-*`,
nunca `--bs-*`**. O chip de ícone de um card é `--vr-grad`, o mesmo gradiente da marca em toda a
aplicação — um gradiente próprio por tela faz cada página parecer de um sistema diferente.

### Enquanto isso, na tela do Monitor

O botão *Abrir* passou a apontar para o **PDF gravado no Electronic Inventory**
(`/api/electronic-inventory/file?client=…&rel=Confirmations/AAAA/mm. Mês/dd/<produto>/…`), não para a
tela que reconstrói o documento: quem valida precisa ver o papel que vai ao cliente, e a tela de geração
pode montar outra coisa se o day-file mudou desde então. O `rel` é relativo à pasta do cliente porque é
assim que aquele endpoint recebe — ele resolve a pasta pelo nome e barra qualquer caminho que escape
dela.

### O item do Monitor é a CONFIRMAÇÃO, não o trade

Um documento é emitido por **contraparte × produto × data de negociação** (com a LOB junto) e cobre
todas as operações do grupo. O Monitor mostrava um item por trade: a mesma folha aparecia dez vezes na
fila, e validar significava clicar dez vezes no mesmo papel — bastava esquecer um para o grupo travar.

Agora o card agrupa por `GROUP_FIELDS` (LOB · Cliente · Produto · Data Operação), o item traz `keys` com
todos os Trade IDs, e **validar ou rejeitar age no grupo inteiro**. O número grande do card conta
**confirmações**; o subtítulo conta as operações que elas cobrem — contar trades no número grande faria a
fila parecer três vezes maior do que o trabalho que ela é. A idade do grupo é a da operação que espera há
mais tempo.

O botão *Abrir* deixou de depender do link carimbado: a pasta é **derivada da linha**
(`confirmation_folder`), e o Monitor lista os **PDFs** que estiverem lá. É isso que faz o botão funcionar
para as confirmações que já existiam antes de o carimbo passar a existir — e são justamente essas que
alguém precisa procurar. Só PDF: é o que abre em preview; o `.doc` baixaria e o `.xml` é do FepWeb.

A tela **Track Confirmations** ganhou a coluna de **Actions** (abrir · editar · excluir), o **Export**
(CSV e copiar) — que leva o que está **na tela**, com filtro e ordenação aplicados, porque quem filtrou
e clicou em exportar quer o que está vendo — e os cards viraram filtro: clicar filtra a tabela pelo
estágio, clicar de novo desliga. O card de MO e o de FO contam também as linhas em `Pending MO/FO`, que
estão paradas nas duas mesas de verdade.

## §219 — "No PDF in the folder": quatro causas empilhadas, cada uma escondendo a seguinte

O Confirmations Monitor abria com os cards certos e **nenhum documento** — todos os itens diziam *no PDF
in the confirmation folder*, com os arquivos intactos no share. Levou um dia porque eram quatro
problemas em série, e cada um só apareceu depois de o anterior sair da frente.

### 1. Código velho no disco

A instância do time rodava uma versão anterior ao `caa2426`, em que os documentos vinham embutidos no
payload do Monitor. O endpoint `POST /api/manual-confirmation/docs` **não existia ali** — o console
mostrava o Monitor respondendo e mais nada, porque a chamada em lote nunca chegava. Antes de caçar bug,
confira sempre as **três defasagens**: código velho no disco (pull não feito), processo velho na memória
(waitress não reiniciado) e página velha no navegador (aba aberta desde antes do restart). As três
produziram um "não funciona" diferente no mesmo dia.

### 2. As pastas gêmeas de pontuação

Antes de o casamento cego a pontuação existir (`_ei_match_key`), o app não achava `REFINARIA … S.A`
partindo de uma linha que diz `… SA` — e **criava a gêmea sanitizada ao lado**. O share ficou com as
duas, cada uma com uma parte dos documentos.

O casamento cego resolveu a busca, mas o cache da raiz (`_EI_ROOT_CACHE['dirs']`) guarda **uma pasta por
chave**: a última gêmea enumerada sombreava a outra, e se os PDFs estivessem na sombreada, sumiam. O
cache passou a ter também `multi` (todas as pastas de cada chave) e `_ei_client_dir_names(client)`
devolve a lista inteira. **Escrita continua tendo um destino único** (`_ei_actual_dir_name`) — duas
pastas de escrita recriariam o problema pela outra ponta —, mas **leitura olha todas**: o
`_mc_confirmation_docs` varre as gêmeas × as pastas de nome legado e deduplica por nome de arquivo, e o
`api_ei_file` tenta cada base até achar o arquivo, com a trava de traversal aplicada **por base**.

### 3. O diagnóstico saía num nível que o console descarta

As três saídas silenciosas do `_mc_confirmation_docs` ganharam log — em `log.info`. O console do waitress
imprime `INFO` **só do logger de requests**; log de módulo aparece a partir de `WARNING`. Foi por isso
que os avisos de CSP apareciam e os meus não. Diagnóstico que precisa ser visto na instância do time vai
em `log.warning`, e a mensagem diz o que foi tentado: a(s) pasta(s) do cliente com *existe / NÃO EXISTE*
e a lista de caminhos relativos procurados.

### 4. O ajuste de velocidade tinha trocado "demora" por "não aparece"

O diagnóstico do usuário estava certo: *"antes demorava mas carregava, agora não aparece nada"*. Duas
coisas somadas:

- o cache da varredura da raiz era aquecido **só pela página do Electronic Inventory**. Com o cache
  frio, cada item do lote re-listava a raiz do share inteira — 50 cards, 50 varreduras de rede. O
  endpoint em lote passou a chamar `_ei_scan_root(grace=10.0)` **uma vez por lote**, antes de resolver
  qualquer item;
- a página abortava o `fetch` em **30 s** e pintava "no PDF" enquanto o servidor ainda procurava. O
  código anterior não tinha prazo nenhum — daí "demorava, mas carregava". O timeout foi para **90 s**.

A primeira carga depois de um restart ainda pode levar 1–2 minutos com o share frio; as seguintes são
rápidas (cache de 60 s por pasta).

### A réplica local

Para provar tudo isso sem acesso à rede JPM: `ELECTRONIC_INVENTORY_ROOT` é uma variável de ambiente, e
apontá-la para uma árvore falsa no scratchpad reproduz o share — inclusive as gêmeas. Foi assim que o
bug da pasta sombreada foi confirmado.


## §220 — A esteira ganha dono, prazo cadastrável e a Legal Entity que era um book

### Cada etapa é assinada pela mesa dela

Qualquer pessoa autenticada validava qualquer etapa. Agora vale o papel do usuário
(`_MC_STAGE_ROLE`): **Pending OTC → `BO`** (a mesa de OTC Ops é o Back Office do cadastro de papéis),
**Pending MO → `MO`**, **Pending FO → `FO`**. É o que separa as funções, e é a razão de a esteira ter
três etapas: quem monta o documento não pode assiná-lo pela mesa seguinte logo em seguida.

**Master passa; `ADMIN` não.** Master é o único que escapa de toda restrição no app (§5 do CLAUDE.md);
administrar acessos, porém, não é sentar na mesa, e um admin assinando pelo MO desfaz a segregação que a
regra existe para garantir. Quem é de mesa precisa do papel da mesa — vale conferir Users & Roles antes
de subir isto, porque quem estiver sem papel de mesa perde o botão.

**Rejeitar segue a mesma regra**: é a outra resposta à MESMA pergunta que o validar responde — o
documento está certo?

Três camadas, e a que vale é a última: no Monitor o botão verde *Validate* vira um *View* de contorno
(o payload diz, por etapa, o que a sessão pode), na tela de validação somem os dois botões e entra uma
faixa âmbar dizendo de quem é a etapa, e os dois endpoints devolvem **403 com `stage_forbidden`**. Sem a
trava no endpoint, um POST direto assinaria pela mesa de qualquer um.

**Abrir a tela continua livre de propósito.** O que some são os botões, não o documento: escondendo a
confirmação, o OTC deixaria de ver o que o MO está conferindo. E o botão de validar **continua no DOM**
quando está escondido — o script o usa para acompanhar o checklist, e um `null` ali derrubaria o resto
da página (a troca de PDF vem depois dele).

### O prazo virou cadastro

Os SLAs estavam fixos no código. Viraram o mapping **`manual-conf-sla`** (uma linha por mesa), com o
`SLA_BIZDAYS` rebaixado a **fallback** com os valores históricos — o comportamento é idêntico até alguém
editar a tabela. O seed e o `upgrade` moram no `manual_conf`, e não no `routes`, pelo mesmo motivo do
cadastro de validação: quem lê a regra a cada linha do Monitor é aquele módulo, e ele não importa o
`routes`.

Duas decisões: `sla_days()` é **cacheado por mtime** porque o Monitor pergunta o prazo três vezes por
linha e edição na tela precisa valer no request seguinte; e **prazo em branco devolve o valor
histórico**, não "sem prazo" — uma célula limpa pela tela apagaria o vermelho de toda confirmação
atrasada em silêncio.

### Legal Entity: era o nome do BOOK

A coluna trazia `ALUM-BRAZIL-BANCO`, `BANCO_Crude_Brazil_NA`, `AGS-BRAZIL-BANCO`. Só as páginas
genéricas de NDF trazem a entidade no deal (campo `LE`, resolvido do Settlement Location pelo
`le-accronym`); mercadoria e FXO **não têm o campo**, e o `first('LE', 'TradingBook')` caía no book, que
não é entidade nenhuma.

`_mc_legal_entity` resolve pelo produto: **mercadoria é sempre JPM** (a mesa booka termo e opção de
commodity no Banco J.P. Morgan, é uma entidade só) e **FXO fica em branco** quando o deal não diz — em
branco pede cadastro, enquanto o nome do book afirmava uma entidade errada. A razão social sai do
cadastro **`le-spn`** (LE → NAME), nunca de um literal: é de lá que o resto do app lê a identidade da
entidade, e é a grafia que as linhas vindas da planilha já usam. Vale para o que for mapeado daqui para
a frente; as linhas já gravadas se corrigem pela edição em massa do Track.

### O Track abre pelo aging

A tabela abria pela coluna *Pending*, que é a primeira. Passa a abrir por **Aging Confirmação
crescente**, e o índice sai do **nome** da coluna, não de um número — as colunas vêm do servidor e um
índice fixo passaria a apontar para a vizinha assim que alguma fosse inserida antes. Junto foi a
ordenação **numérica**: o servidor manda o aging como TEXTO e a linha sem data de operação manda vazio;
basta uma dessas para o DataTables tipar a coluna como string, e aí `104` vem antes de `9`.


## §221 — O que a tela diz sobre a confirmação: três números que não fechavam

### Daily Metric: 177 no cartão, 167 na barra

O cartão mostrava a leitura **ao vivo** e a última barra do gráfico o **último snapshot em disco**, com o
badge de variação calculado sobre a barra. Quem lia não tinha como saber se o `+9%` ia de 153 para 167
ou para 177.

Mês e dia **em curso não estão fechados**: o valor deles é o de agora, que é o que este e-mail reporta e
o que a tabela por grupo econômico logo abaixo soma. `_pc_metrics_stamp_now` carimba a leitura viva no
ponto corrente e **refaz o `pct`** — sem recalcular, a barra subiria e a variação continuaria a do
snapshot, trocando uma incoerência por outra. Sem ponto para o período em curso ele cria um: no dia 1º
de um mês novo a última barra era a do mês anterior.

A página `/metrics-pending-confirmation` não muda: lá tudo vem da mesma série de snapshots, e portanto
já é coerente consigo mesma.

### O aviso da esteira não levava a lugar nenhum

A página da notificação é `'Confirmation'`, que **não estava no `_NOTIF_PAGE_URL`** — e sem destino o
clique no sino não faz nada. Entrou nas **três** cópias do mapa (`routes.py`, `partials/topbar.html` e
`static/js/sw-push.js`), apontando para o Confirmations Monitor. O rótulo continua `'Confirmation'`, e
não vira `'Manual Confirmation'`, porque é o que as notificações **já gravadas** carregam: renomear
deixaria o histórico do sino sem destino.

O texto ia em português com a tela em inglês. O detalhe é **gravado no banco** e o feed o mostra cru,
então ele nasce em INGLÊS como todo o resto do sino (`Validated by OTC · …`). As notificações antigas
continuam em português — o texto está no banco.

De quebra, o aviso de reject usava uma variável `key` que **nunca existiu** naquela função; só não
estourava porque o `or` à esquerda quase sempre tem o Cliente preenchido.

### O card de Confirmations do New Deals Monitor parava em "Generated"

Ele mostra agora **um ciclo só**, do documento até a assinatura: `New → Generated → … → Success` é a
geração e `Pending OTC → Pending MO/FO → Ok` é a esteira. Quando o grupo já tem linha na esteira, a
etapa dela **vence** o status do documento (mostrar `Generated` numa confirmação já em Pending MO é
parar o relógio na metade), e o anel de progresso só fecha em verde no `Ok`. As cores dos chips são as
**mesmas** do Confirmations Monitor: as duas telas mostram a mesma fila.

O join é pelos **Trade IDs** (`_conf_segregate` passou a coletar `Deal` e `B3_ID` de cada grupo), nunca
por contraparte × mercadoria — os dois lados normalizam nome e mercadoria de jeitos diferentes, e um
de-para por texto casaria errado em silêncio. Os dois identificadores vão juntos porque a chave da
esteira é o Deal para quase todo produto e o **B3 ID** para o FWD Start.

O grupo vale pela operação **menos avançada** (`_CONF_STAGE_ORDER`) — dizer `Ok` porque uma das dez foi
validada esconderia as nove restantes —, e operação que **ainda não entrou** na esteira não conta, senão
um documento recém-gerado nasceria vermelho. O índice é lido **uma vez por request** e passado aos
quatro cards: dentro do `_conf_stage_counts` ele abriria os dois DuckDB oito vezes na mesma tela.


## §222 — Thread de scheduler não tem application context

O aviso de pendências das 19:00/19:30 do Deals Monitor falhava com **`RuntimeError: Working outside of
application context`** e o e-mail não saía.

O scheduler roda numa **thread própria**, e lá não existe application context. `render_template` (o
corpo do aviso) exige um — e o `_get_logo_path` também, porque lê `current_app.root_path`.

**O sintoma engana**: o botão *Run* do Control Panel funciona, porque roda dentro de um request e ganha
o contexto de graça. Só o automático falha, e o único lugar onde isso aparece é a linha vermelha do
card.

`_app_context()` resolve — no-op dentro de um request, e fora dele entra no contexto do app capturado no
**`record_once` do blueprint**, que é o único momento em que o app existe e este módulo é alcançável (a
fábrica `create_app` importa as rotas, então guardar a referência ao contrário seria circular).

Dois detalhes:

- o `with` envolve a **montagem inteira** da mensagem, não só o `render_template`. Envolvendo só ele, o
  erro reaparece três linhas abaixo, no logo. O **SMTP fica de fora**: rede não precisa de contexto e não
  é para segurá-lo durante o envio;
- uma varredura pelas cinco threads de scheduler mostrou que esta é a **única** que renderiza template ou
  toca `current_app`. Pending Confirmation, as duas da Athena e o box scan não precisam de contexto.

O horário que falha é **devolvido** pela própria rotina (o slot só fica reservado quando o envio dá
certo, §207), então o catch-up retenta na volta seguinte: depois do pull e do restart o aviso do dia sai
sozinho, sem apertar o Run. O `check_ndm_pending_sched.py` passa a disparar o envio de dentro de uma
thread, sem request — que é exatamente o caminho que quebrou e que nenhuma asserção cobria.


## §223 — A Weekly Escalation vira rascunho, não envio direto

A escalação CEM/EDG saía pelo SMTP no clique do *Run*: quem apertava o botão só descobria o que tinha
ido depois de ir. É uma cobrança **nominal a banqueiros**, com nome de cliente e contagem por empresa —
quem assina quer ler antes.

Passa a seguir o caminho do **Daily Metric**, que é o outro card de e-mail do painel:
`_build_weekly_escalation_eml` devolve os bytes do `.eml` com `X-Unsent: 1`, a página salva o arquivo e o
Outlook o abre como rascunho editável. Sem SMTP nenhum na rotina.

O TO/CC salvo continua o mesmo cadastro, com uma diferença de sentido: ele agora **pré-preenche** o
rascunho em vez de endereçar um envio — e por isso vai nos **cabeçalhos** da mensagem, não num envelope.

A notificação mudou junto (`Weekly Escalation Draft`, *draft generated*): ela dizia *e-mailed*, e
continuar dizendo isso descreveria um envio que não acontece mais.

### E na Recon FXO, no mesmo dia

A coluna de comentário ficou **centralizada** (o `text-align:left` veio de carona com o recorte por
largura; o limite e o ellipsis continuam, senão uma justificativa longa empurra as ~38 colunas para
fora). E o **Export** ganhou Excel, Print e PDF: a matriz é montada à mão — é isso que garante o "exporta
o que está na tela" —, mas xlsx e PDF ninguém escreve à mão, então entraram pelo **Buttons** do
DataTables, já vendorizado no repo.

Duas armadilhas: o Buttons precisa ser criado **sob demanda e re-vinculado**, porque o `buildTable`
destrói e recria a DataTable quando as colunas chegam do servidor — um Buttons preso à instância
anterior morre junto, **sem erro no console**, deixando um menu que não faz nada. E o PDF sai em **A3
paisagem, fonte 6 e larguras proporcionais**: em retrato as colunas estouram a folha em silêncio.


## §224 — Recon FXO: a perna interna que só produzia quebra

A conta interna **GEM** (`BCO J.P. MORGAN S.A. 2768 - GEM BR - EXPENSES & CASH MGMT`) chega ao relatório
da Athena com dezenas de linhas por dia e **não tem par na CETIP**. Ela entrava no batimento e saía como
`Unmatched Athena` — quebra que não é quebra, todo dia, empurrando para baixo o que precisa de atenção.

O cadastro `fxo-internal-cpty` ganhou a coluna **`USE`** (`Consider` / `Disregard`). `Disregard` tira do
batimento as linhas da Athena cujo `CounterpartyName` casa com o nome cadastrado.

Quatro decisões, e nenhuma é cosmética:

- **O corte é ANTES do merge.** Depois não adiantaria: o `DealID` dessas linhas já teria ocupado a chave
  em `base_athena_para_match` e poderia ter roubado o par de uma operação de verdade.
- **Compara só o `CounterpartyName`**, nunca o `MatchingCounterpartyName`. Quem é a perna interna é o
  dono da linha; o Matching é a contraparte do outro lado da MESMA operação, e cortar por ele derrubaria
  a operação do cliente.
- **A comparação é cega a pontuação** (`_nome_cru`). O cadastro escreve `S.A.` e o arquivo pode vir
  `S.A` — comparar o texto literal casa silenciosamente nada, o mesmo tropeço das pastas gêmeas do
  Electronic Inventory (§219).
- **O corte é avisado no painel**, com a contagem. Linha que some sem dizer nada vira "sumiu uma operação
  da recon" no dia em que alguém marcar o nome errado.

Uma linha `Disregard` **deixa de valer como renomeação ou perna espelhada** — uma linha, uma decisão. Na
prática a GEM saiu do `INVERT DIRECTION = Yes`: a regra continua existindo e testada, mas hoje não há
linha usando-a.

### O upgrade mora no motor, não na tela

O `upgrade` que traz a coluna `USE` para os arquivos antigos fica no **`recon_fxo`**, e o `routes` só
aponta para ele. É o mesmo tropeço que o cadastro da esteira já custou uma vez (§217): esse arquivo tem
**dois leitores**, e o motor da recon lê o JSON cru a cada run. Com o upgrade só na tela de /mapping, a
instância que nunca abriu aquela tela rodaria sem a coluna — e a regra nova simplesmente não valeria.

Ele só preenche o que **não existe**: linha sem a chave é anterior à coluna, então ninguém teve como
opinar sobre ela, e ela recebe o padrão do produto (`Consider` para todas, `Disregard` para a GEM). Com a
chave presente, nada é tocado — o cadastro é de quem edita.


## §225 — O nome da contraparte vinha do arquivo; passa a vir do Reference Data

O `br-onshore-settlements` do Athena traz o `CounterParty` como **texto livre da mesa** — `S T E S A L`
para a SASCAR, `LAWTON MULTIMERCADO EXCLUSIVO 2786 - GEM BR - RATES` para a nossa própria perna. Era
esse texto que a página **Swap Athena** mostrava, que o **Settlement Advice** imprimia e que ia no aviso
ao cliente. No **OTM Settlements** valia o mesmo: o `Cpty Name` era o do arquivo.

Ao lado do nome, os dois arquivos trazem o **SPN**, que é identificador e não apelido. `_otm_cpty_name`
já sabia resolvê-lo — cadastro `le-spn` quando é entidade nossa (entidade própria não está no Reference
Data como contraparte, então procurá-la lá devolveria vazio) e Reference Data quando é cliente, com
`_spn_key` ignorando zeros à esquerda e o rabo `.0` das planilhas. O que faltava era usá-lo.

`_athena_settlements(ref)` passa a ser **a** coleta do arquivo do Athena, com o `CounterParty` já
trocado. As três telas que o leem chamam ela:

| Tela | O que muda |
|---|---|
| Swap Athena | a coluna `COUNTERPARTY` |
| Settlement Advice de Swap | o nome do cliente na tela **e no aviso impresso/enviado** |
| Trade Level / Settlement Summary | o último recurso do nome (o `Cpty SPN` do OTM continua vindo antes) |

Uma coleta, e não uma resolução por tela, porque é exatamente assim que elas passariam a mostrar
clientes diferentes para a mesma operação. E porque o nome não é só rótulo: é por ele que a alíquota é
procurada no `swap-ir-client` — mostrar um nome e casar o IR por outro deixaria quem edita o cadastro
digitando o texto que vê, sem efeito nenhum.

No OTM a resolução é feita **na leitura** (`_otm_collect`), não na importação: corrigir o Reference Data
passa a valer na hora, sem reimportar o dia. E a ordenação alfabética da Swap Athena vem **depois** da
troca — ordenar pelo texto do arquivo deixaria a lista fora de ordem assim que o nome mudasse na tela.

Sem SPN, ou com SPN que não está em cadastro nenhum, o nome do arquivo fica: a linha não pode sair
anônima porque o cadastro está incompleto.


## §226 — Track Confirmations: o Athena ID saiu

A coluna existia para mostrar o **Deal** das linhas de FWD Start, que são chaveadas pelo B3 ID e por
isso não têm o Deal no `Trade ID` (§217). Na prática ela nunca cumpriu isso: nos produtos chaveados pelo
Deal ela **repetia** o Trade ID, e nas linhas de FWD Start vinha **vazia** — no banco da instância local,
33 linhas iguais ao Trade ID, 10 vazias, e nenhuma acrescentando informação (as 10 diferentes eram as
linhas de demonstração criadas para as capturas do SOP).

Ela saiu de `COLUMNS` e o `_mc_save_from_deal` deixou de gravá-la — `blank_row` descarta chave
desconhecida em silêncio, e campo que se escreve para nada é dívida esperando alguém procurá-lo.

**O dado não foi perdido**: `ensure_db` só ACRESCENTA coluna, então a coluna física continua no DuckDB
com o que já estava lá. Voltar atrás é devolver o nome à lista.

## §227 — Equities: o lado que o Swap Athena não tem

A B3 registra as operações de equity como **SWAP**, então elas já entravam no Trade Level e no
Settlement Advice pelo Operations B3 (`_ops_swap_settling`). O que faltava nelas era o outro lado: o
**Swap Athena é só de CEM** e não tem linha nenhuma para equity. Sem ele a linha saía com o nome curto
da B3 (`SAFRABM`, `INTRAGATACAMAFDO`), sem Internal ID, sem Settlement e com as três colunas de valor
em branco — e, sem Settlement, ficava **fora do Settlement Summary**, que é a fonte do aviso.

A primeira tentativa montou uma **família própria** a partir do OTM Settlements. Estava errada, e o
erro é instrutivo: ela criava uma SEGUNDA linha para o mesmo trade, ao lado da que o Operations B3 já
produzia — uma com o identificador da B3 e o valor da B3, a outra com o Trade Id e o valor interno, e
nenhuma das duas completa.

A rota certa parte do **Título** e tem três paradas:

```
Operations B3 --Título--> Latam Desk Position --Deal_Ref--> OTM Settlements
                          CLEARING_TRD_ID_INT               270WI<Deal_Ref>
                          CLEARING_TRD_ID_CLNT              270WC<Deal_Ref>
```

O mesmo `Deal_Ref` cobre DUAS operações — a de contra o cliente externo e a de contra a nossa entidade
(Safra × Atacama) —, e é por isso que o relatório traz os dois identificadores na mesma linha. **Qual
das pernas é a do Título em mãos sai de QUAL COLUNA casou**: `CLEARING_TRD_ID_INT` é a perna interna e
leva ao Trade Id `270WI…`; `CLEARING_TRD_ID_CLNT` é a do cliente e leva ao `270WC…`.

`_ops_equity_link(ref)` devolve `{Título → …}` com exatamente os campos que a linha do Athena daria, e
as DUAS telas o consomem — o documento que vai ao cliente não pode discordar da tela.

O que entra por essa rota:

| Coluna | De onde |
|---|---|
| Internal ID | o Trade Id do OTM (`270WI…`/`270WC…`) |
| Counterparty | Reference Data pelo **Cpty SPN** do OTM (`_otm_cpty_name`) |
| Settlement | soma dos fluxos do OTM daquele Trade Id |
| **Curva Banco** | os fluxos **positivos** do OTM |
| **Curva Cliente** | os fluxos **negativos** |
| **Resultado Bruto** | a soma dos dois |
| Type | o **ativo subjacente** (`Underlying_Name`/`UNDERLYING_RIC` do Latam) |
| Data Operação (prazo do IR) | o **`Trade_Date` do Latam** |
| Settlement B3 | continua vindo do próprio Operations B3 |

Quatro coisas que não dão erro se forem feitas de outro jeito:

- **O de-para lê o ÚLTIMO Latam Desk Position**, não o da data de liquidação. O relatório não é diário
  e a própria página abre no último JSON que existe (`_latam_latest_ref`).
- **A chave é só-dígitos, sem zeros à esquerda dos dois lados** (`_ops_eq_ref_key`): um sistema zera à
  esquerda conforme a largura do campo e o outro não. Trade Id **sem** um dos prefixos conhecidos não
  vira chave — o identificador de outra família não pode casar por acidente.
- **O Type tem de ser trocado, não completado.** VCP/Calculado sai do arquivo de eventos, que não tem
  essas operações: sem a troca, toda linha de equity apareceria como `Calculado`, que é uma afirmação
  errada em vez de uma célula vazia.
- **O prazo do IR sai do Latam.** A posição de swap não tem essas operações, e sem data de operação não
  há prazo — logo não há alíquota, e a coluna de IR sairia vazia numa liquidação que paga IR. O IR
  segue a MESMA tabela do swap (`swap-ir-client` + `swap-ir-term`), inclusive a isenção de bancos.

**O produto continua `SWAP`**, e não `EQUITY`: é como a B3 registra, e é dessa linha que sai o
Settlement B3. Trocar o rótulo tiraria essas operações do card de Swap sem colocá-las em card nenhum.
Quem rotula a linha é a **LOB**, que cai em `EQUITIES` quando o Código Identificador não traz token
(o cadastro continua vencendo quando responde).

**Perna interna não gera aviso** (`_no_advice`): ela FICA no Trade Level — é uma operação de verdade, e
tirá-la esconderia metade do par — e SAI do Settlement Summary e do Settlement Advice. Só para equity,
de propósito: a regra é geral, mas o swap de CEM roda assim há tempo e ligar o corte para ele apagaria
da tela linhas que a mesa usa hoje. É decisão de negócio, não efeito colateral.

## §228 — O corte da GEM na Recon FXO pegava só metade do par

O cadastro `fxo-internal-cpty` com `USE = Disregard` (§224) tirava as linhas da Athena cujo
**`CounterpartyName`** casava com o nome cadastrado. A conta continuou aparecendo na tela.

A operação intragrupo chega ao relatório **pelos dois lados**: numa linha a conta interna é a dona
(`CounterpartyName`), na outra ela é a contraparte (`MatchingCounterpartyName`). E é justamente esta
segunda que a coluna **ATH Cntpy** mostra, porque é dela que `deriv_cntpy_ath` parte — SPN primeiro,
`MatchingCounterpartyName` depois, `CounterpartyName` só como último recurso. Cortando por uma coluna
só, metade do par ficava na recon como `Unmatched Athena` **exibindo o nome que o cadastro mandou
tirar**.

O corte passa a olhar as duas colunas (`COLS_AT_CPTY_DISREGARD`). A ressalva antiga do comentário — "o
Matching é a contraparte do outro lado e cortar por ele derrubaria a operação do cliente" — não se
aplica: a conta marcada é **interna**, e a linha em que ela aparece como contraparte é a perna de
dentro da mesma operação. O cliente está do outro lado do **seu próprio** par, numa linha cujas duas
contrapartes são ele e a mesa.

## §229 — "Começa em BANCO" derrubaria o Banco Safra

A regra de perna interna foi enunciada como *entidade legal ou nome começando em BANCO*. Escrita
literalmente, ela é um bug: **BANCO SAFRA, BANCO BRADESCO e BANCO SANTANDER** são clientes de verdade, e
ficariam sem aviso de liquidação **em silêncio** — a linha some do Settlement Summary sem nada dizer.

O que se quer dizer com "banco" é o banco DO GRUPO. `_ops_is_internal_cpty` responde por duas fontes,
nenhuma delas um prefixo:

1. cadastro **`le-spn`** — por SPN, por nome, e pelo **token da LE** como palavra dentro do nome;
2. **`_pc_is_internal_counterparty`** — o Reference Data (`ECONOMIC GROUP = INTERNAL`, por SPN e depois
   por nome) com `_pc_is_intragroup` como último recurso (`banco` **e** `morgan` no nome). É a resposta
   que o Pending Confirmation já dá para decidir o que é operação de cliente; uma segunda definição aqui
   divergiria da primeira no primeiro cadastro novo.

O **token** existe porque o `Reference Data Name` nasce VAZIO em algumas entidades (a ATACAMA é assim no
seed) e o nome que chega dos arquivos é o da conta por extenso — `ATACAMA FUNDO DE INVESTIMENTO`. Sem
ele, a perna interna só seria reconhecida depois de alguém preencher a razão social na tela, e até lá
geraria aviso. Só tokens de **4+ caracteres** entram: `JPM` e `MGT` são curtos demais e apareceriam no
meio de um nome de cliente por acaso.

## §230 — O sino da Recon FXO levava para a recon do Pay/Rec

`_create_notification(actor_sid, actor_name, **action**, **page**, detail)` — e a chamada da Recon FXO
passava `('Recon FXO', 'Reconciliation')`. O rótulo `Reconciliation` é o do **Pay/Rec**
(`/reconciliation-payrec`) no `_NOTIF_PAGE_URL`, então o clique abria a recon errada. O `page` é o
**destino**, não o assunto: quem escreveu a linha copiou a do Pay/Rec e trocou só o texto da esquerda.

O par certo é o mesmo da Recon Comitente: ação **`Recon Generated`** (que já tem ícone no sino —
shield-check verde; `Recon FXO` não tinha nenhum e caía no genérico) e página **`Recon FXO`**.

**As notificações já gravadas continuam com o par antigo**, e o que está no banco não se reescreve.
`_notif_page_url(page, action)` traduz `('Reconciliation', 'Recon FXO')` → `/reconciliation-fxo`; sem
isso o histórico do sino abriria o Pay/Rec para sempre. É a mesma razão pela qual o rótulo da esteira
continua sendo `Confirmation` e não `Manual Confirmation`.

A tradução vive em **três lugares**, e os três têm de dizer a mesma coisa — `routes._notif_page_url`
(o filtro de acesso por página), `partials/topbar.html` (o clique do sino) e `static/js/sw-push.js` (o
clique da notificação do celular). Com um deles fora, a mesma notificação abre uma recon pelo sino e
outra pelo push. `check_notif_page_url.py` prende os três.

## §231 — O aviso da esteira ia para o time inteiro

Toda validação da esteira gravava a notificação **sem destinatário**, então o sino do time inteiro
tocava por uma confirmação que só uma mesa podia assinar. Agora o aviso é endereçado à etapa em que a
confirmação **caiu**:

| Etapa depois do carimbo | Quem recebe |
|---|---|
| `Pending OTC` | BO · MASTER |
| `Pending MO` | MO · BO · MASTER |
| `Pending FO` | FO · BO · MASTER |
| `Pending MO/FO` | MO · FO · BO · MASTER |
| `Ok` | todos (sem restrição) |

Quatro decisões:

- **O destino sai do ESTADO, não da etapa assinada.** `_mc_notify_roles` chama `pending_stage(row)`
  DEPOIS do carimbo. "O OTC validou" não diz a quem interessa; "isto agora está em Pending MO" diz. E é
  o que faz o cadastro `manual-conf-validation` valer de graça: produto isento de FO nunca avisa o FO.
- **O Back Office entra em todas.** Assinar e receber são perguntas diferentes: assinar é um ato e é de
  uma mesa só (`_MC_STAGE_ROLE`); receber é acompanhar, e o documento é do BO — é ele que o montou e é
  para ele que o reject volta. Os dois mapas existem lado a lado de propósito.
- **`MASTER` em todas, `ADMIN` em nenhuma.** `MASTER` é o valor que `_set_session` grava para os SIDs de
  `_MASTER_SIDS`; sem ele na lista o superusuário perderia a esteira de vista, e em silêncio. `ADMIN`
  ficou de fora pelo mesmo raciocínio que o tirou da validação — administrar acessos não é sentar na
  mesa. Se a mesa quiser o admin vendo tudo, é acrescentar `'ADMIN'` ao mapa: uma linha.
- **A confirmação que fechou (`Ok`) volta a avisar todos.** Não há mesa esperando, e restringir o fim da
  esteira esconderia justamente a notícia boa.

**A coluna `target_role` passou a aceitar VÁRIOS papéis**, separados por vírgula na mesma coluna
(`'MO,BO,MASTER'`). `_notif_roles` normaliza (aceita string ou lista, tira repetido e caixa), o filtro
do feed casa por membro (`list_contains(string_split(target_role, ','), ?)`) e o `_push_notify` monta um
`IN` com os papéis **bindados** — placeholders pela contagem, valores por parâmetro, que é o único caso
que o cheat sheet permite montar string. **O valor antigo continua válido de graça**: `'ADMIN'` parte
numa lista de um elemento. Uma tabela de destinatários seria um join novo em toda consulta do sino, e a
topbar consulta a cada 8 s por aba aberta.

Do outro lado da mesma regra, a matriz de quem **assina** foi completada em `check_manual_conf.py`: os
três positivos (BO→OTC, MO→MO, FO→FO) e todos os cruzamentos negativos, ADMIN inclusive. Só provar os
403 deixaria passar uma regra que nega tudo; só provar os 200, uma que libera tudo.

## §232 — Validar pela GRADE não era validar

A tela de validação passa pelo `mark_validated`: ele carimba **quem** assinou (`Time Stamp <mesa>` =
data, hora e SPN), cobra a justificativa quando o prazo passou (`SlaCommentRequired` → 409) e o endpoint
exige a mesa certa (`_mc_can_validate` → 403).

O Track Confirmations escrevia a **MESMA coluna** por outro caminho. `api_mc_upsert` copiava toda coluna
de `COLUMNS` como texto livre, então preencher `VALIDADO p/ MO` na grade gravava a data e mais nada:

- **sem carimbo** — a validação entrava sem dono, e "quem conferiu isto?" ficava sem resposta;
- **sem o teste de prazo** — uma validação atrasada passava sem justificativa nenhuma;
- **sem o teste de mesa** — qualquer papel assinava por qualquer mesa, e a segregação valia só no
  caminho de cima.

Agora **preencher a coluna de validação pela grade É validar**, e passa pelas três regras. O que
distingue uma validação nova de um ajuste de cadastro é a TRANSIÇÃO: a coluna estava vazia e passou a
ter data. Editar o Cliente de uma linha já validada não recarimba (apagaria o dono da conferência
anterior) nem cobra motivo.

Quatro detalhes que não são óbvios:

- **O prazo é medido no estado ANTERIOR.** Depois de escrever a data, a própria `sla_state` responde
  `done` e o atraso desapareceria da conta — a pergunta tem de ser feita antes de aplicar a edição.
- **A data digitada é preservada.** A grade também serve para registrar validação antiga; forçar `hoje`
  (como o `mark_validated` faz, e ali está certo) reescreveria o que o usuário veio corrigir. O carimbo
  é acrescentado, não a data.
- **Apagar a data apaga o carimbo.** Um `Time Stamp` sobrevivente afirmaria que alguém assinou uma etapa
  que voltou a ficar pendente.
- **O lote é tudo-ou-nada.** As linhas são montadas e conferidas antes de qualquer `upsert_row`: uma
  edição em massa que falha na quinta linha não pode deixar as quatro primeiras gravadas com o usuário
  sem saber quais.

Fica um buraco conhecido, e ele é anterior a isto: `sla_state` devolve `ok` quando a linha **não tem
`Data Operação`** — sem data de operação não há prazo a calcular, e chamar isso de `late` seria afirmar
um atraso que ninguém mediu. Essas linhas validam sem justificativa. O conserto é preencher a data de
operação, não afrouxar a régua.

## §233 — A toolbar encostava no cabeçalho da tabela, e o `mb-2` media zero

Nas páginas **Operations B3** e **Latam Desk Position** a fila de botões (Show · Add row · Columns ·
Export · Clear filters) ficava colada na primeira linha do `<thead>`. O wrapper já tinha `mb-2`, e é
por isso que o problema não saltava ao ler o markup: medido na tela, o espaço era **0 px**. O
DataTables desenha a própria caixa (o `.dt-container` / `.dataTables_wrapper`) encostada no elemento
anterior e come a margem do irmão de cima. `mb-3` devolve 12 px — medidos nas duas páginas, não
supostos.

O comentário fica no template, ao lado da classe: sem ele, a próxima pessoa lê `mb-3` como um número
escolhido a esmo e o "arruma" de volta para o `mb-2` que o resto do arquivo usa.

**O mesmo `mb-2` está em outras dez telas** com o wrapper idêntico
(`d-flex justify-content-between align-items-center flex-wrap gap-2 mb-2`): `cognos`, `ndf-cockpit`,
`ndf-other-publisher`, `otm-settlements`, `other-products-swap-athena`, `-events`, `-vcp`,
`-kapital-hybrids`, `-settlement-advice` e `other-products-ndf-settlement-advice`. Foram deixadas
como estavam **de propósito** — o pedido nomeou duas páginas, e trocar espaçamento em dez telas de uma
vez é uma varredura própria, que se faz olhando cada uma. Fica registrado aqui para a varredura não
depender de alguém reparar de novo.

## §234 — Equity: o Type em branco e a perna interna que sumiu da tela

Duas sobras do §227/§229, as duas com o mesmo formato — a linha existia, mas a tela não contava tudo
sobre ela.

### O Type em branco nas operações de EDG

O Type de equity é o **ativo subjacente** (§227), e ele saía de `Underlying_Name` → `UNDERLYING_RIC` do
Latam → `Underlying` do OTM. As três vêm **vazias no swap de equity**: são colunas de derivativo
*sobre* um ativo (opção, barreira, rebate), e no swap o próprio **instrumento é a ação**. Resultado: a
linha aparecia com Internal ID, contraparte, Settlement e IR — tudo certo — e a coluna Type em branco,
sem nada na tela dizendo por quê.

A cadeia ganhou três degraus, do mais específico para o mais genérico:

```
Underlying_Name → UNDERLYING_RIC → OTM.Underlying → Instrument_Name → RIC → Instrument_ID
```

O `Instrument_ID` fica por último porque é **código, não nome**, e o nome é o que distingue uma
operação da outra na tela. Tudo vazio continua deixando a célula vazia: pede o arquivo, não inventa um
subjacente.

### A perna interna sumia do Settlement Summary

O §229 tirou a perna interna do Settlement Summary junto com o aviso, no raciocínio de que "cada linha
do Summary é um aviso". A premissa estava errada: **o Settlement Summary é a visão de LIQUIDAÇÃO do
dia**, e a perna interna liquida — o dinheiro se move, e o total do Summary tem de fechar com o Trade
Level. Cortá-la de lá fazia a operação da entidade nossa (a ATACAMA, do par com o cliente externo)
desaparecer da tela sem uma palavra, que é exatamente o defeito que o `Unmatched Athena` da Recon FXO
já tinha ensinado: quebra que ninguém vê.

Agora a marca `_no_advice` tira só o que é **documento**:

| Onde | Perna interna |
|---|---|
| Trade Level | entra (visão de trade) |
| Settlement Summary | **entra**, como qualquer outra linha |
| Settlement Advice | fica de fora — é o documento endereçado ao cliente |
| E-mail de TED | fica de fora — não se transfere dinheiro para si mesmo |

**A marca é de servidor e não aparece na tela.** A primeira versão punha um selo `Internal` ao lado do
nome, no argumento de que a linha precisava explicar por que nunca sai do `New` — e a mesa recusou:
quem lê o Settlement Summary sabe o que é a ATACAMA, e o selo só polui a coluna. `internal` continua
no payload porque é ele que corta a TED; o que caiu foi a exibição.

Uma coisa que o corte do TED exige e não é óbvia: **`_is_jpmorgan` não responde por ela**. O TED já
pulava Lawton e J.P. Morgan pelo nome, mas a perna interna pode ser um **fundo nosso**
(`ATACAMA FUNDO DE INVESTIMENTO`) — sem "J.P. Morgan" no nome, passaria batido e o e-mail pediria uma
TED para dentro de casa.

### Verificação

`check_ops_trade_equity.py` ganhou o caso do Latam sem colunas de subjacente (Type caindo no
`Instrument_Name`) e trocou a asserção do §229: a perna interna **entra** no Summary, marcada como
`internal` no payload, e o cliente **não** vem marcado — só provar que ela entra deixaria passar uma
regra que marca tudo. `check_ops_summary.py` continua verde, inclusive a checagem posicional das
colunas, que é lida do `row.add` do template.

## §235 — File Interface: os layouts da B3 viraram cadastro, não código

A seção Apps ganhou o **File Interface** (`/file-interface`): o "lego" dos arquivos enviados à B3
via Batch Conecta. Cada layout do manual "Transferência de Arquivos – Enviar Arquivos" é um JSON em
`apps/static/data/file-interface/` (versionado, um por template) com os blocos como o manual
apresenta — Header, Registro(s), Footer — e, por campo: Seq, Campo, Formato, Posição, Obrigatório,
Conteúdo, Descrição, mais **Origem** e **Detalhe da Origem** (de onde o OTC Tracker puxa o valor:
coluna da página, mapping, literal, calculado). São **14 seeds** transcritos da versão 10/08/2026
do manual (1.002 campos): 5 **ativos** já vinculados às páginas que os usam (Termo Multiclasses →
as 4 de NDF do New Deals; TAXACAMBIOTER → NDF Other Publisher; Opções Flexíveis VCP → Opt FXO e
Opt Commodities; Atualização PU/Fator → Accrual; MID → MtM) e 9 de **biblioteca** (antecipações e
os seis layouts de registro de Swap), sem página ainda — prontos para vincular quando existir.

Decisões e armadilhas:

- **Nada de layout no código.** A API é `/api/file-interface/templates[/<key>]` (GET/POST/DELETE),
  no molde dos mappings: POST substitui o arquivo inteiro, valores não são trimados, escrita
  atômica sob o `_cache_lock`. A chave é o nome do arquivo em disco e o regex `_FI_KEY_RE` é o que
  barra path traversal pela URL. Template novo/atualizado da B3 entra pelo **Create New Template**
  (builder de blocos e campos na tela), e o **Add Template** vincula um template da biblioteca às
  páginas — a lista de páginas é colhida do DOM vivo do sidenav, como no Page Access.
- **A versão 10/08/2026 do manual renumerou as seções**: o Termo Multiclasses virou *4.10.1
  Registro de Contrato a Termo Sem CCP* (págs. 637–647) e o 4.11.x virou 4.10.x. Os
  `manual_section`/`manual_pages` dos seeds seguem essa versão — referências antigas (637–646 etc.)
  não batem mais com o PDF novo.
- **A transcrição achou três divergências código × manual**, anotadas no `notes` dos templates:
  o TAXACAMBIOTER escreve o Contrato com `ljust(10)` onde o manual pede `X(11)` (linha de 86 vs 87
  chars); o docstring do send-conecta de FXO diz Tipo de Cotação `'2'` mas o código escreve `'1'`;
  e no Accrual o Papel/Curva `01` vai para a conta *maior* enquanto o manual manda a *menor*.
  Nenhuma foi "corrigida" — o comportamento em produção é o que está descrito em Origem, e mudar
  qualquer um dos três é decisão de negócio, não de transcrição.
- **Opções Flexíveis é por separador** (`;`, com token vazio no fim — 62 campos, 63 tokens), os
  demais são posicionais; o chip da página mostra qual é qual, e `9(12)V9(8)` ganha a leitura
  humana ("12 inteiros + 8 decimais") na própria coluna de formato.

## §236 — File Interface por página, e a origem virou seleção

Dois ajustes de desenho no File Interface (§235), pedidos na primeira revisão de tela:

- **O rail esquerdo abre pelas PÁGINAS, não pelos templates.** Uma entrada por página que
  gera arquivo; clicar mostra o template linkado com as colunas de Origem dizendo só o que
  AQUELA página faz. O template com 4 páginas (TER) tinha três comportamentos numa célula
  só. O mecanismo é o `source_by_page` por campo: o texto comum fica no
  `source`/`source_detail` plano e cada página só ganha entrada própria onde diverge —
  editar na visão de página grava o override daquela página (e igualar ao comum remove o
  override). A Template Library continua abaixo, para os 9 sem página e para editar o
  template "puro".
- **`source_detail` deixou de ser prosa.** Fixed = o valor em si (sem "Literal");
  Page/Calculated = o NOME EXATO de uma coluna da página, escolhido em dropdown; Mapping =
  a chave do registro, em dropdown com os 25 mappings (endpoint
  `/api/file-interface/options`). Condição/transformação foi para a **`source_note`**
  opcional (subtexto). As opções do dropdown de coluna vêm de **`linked_pages[].columns`**
  do próprio template — cadastráveis, semeadas dos cabeçalhos reais das 9 páginas
  (inclusive as montadas por JS: Other Publisher = `_NDFOP_COLUMNS`, Accrual =
  `_ACC_FIXED_HEADERS`, MtM = `_MTM_FIXED_HEADERS`). Asserção que protege o formato: toda
  origem `Page` bate com uma coluna da lista, e nenhum `source_detail` contém frase de
  lógica.

Armadilhas encontradas ao separar por página: **o NDF Vanilla não gera o TER de fato** (o
endpoint genérico devolve 404 para `vanilla`; o registro é feito por outra ferramenta — o
vínculo ficou, com a realidade anotada) e, no Other Publisher, o gerador lê
`StrikeSetDate`/`StrikeSetOffset`, colunas que só existem na página de FWD Start — esses
campos são `Calculated` com nota, não `Page`, senão apontariam para coluna que a tela não
tem. Os rótulos de coluna diferem por página para o mesmo dado (`FixingStartDate` na de
commodities, `First Fixing Date` nas genéricas; `Total Notional` × `Notional`): o dropdown
usa o rótulo DAQUELA página, é isso que o usuário vê na tela dele.

## §237 — File Interface: independência real por página, colunas cadastráveis e o padrão da casa

Terceira rodada de revisão de tela do File Interface (§235/§236), em dois commits
(`329e537`, `f4b83ed`):

- **As tabelas de bloco entraram no padrão da casa**: linha de filtro por coluna (uma POR
  tabela — filtrar o Header não esconde linhas do Registro; handler delegado no
  `#fiBlocks`, então sobrevive ao re-render e ao modo de edição) e conteúdo todo centrado.
  Os inputs do filtro usam as classes padrão (`form-control form-control-sm
  bg-light-subtle border-light`) — a primeira versão usou classe própria e saiu sem os
  cantos arredondados das demais páginas. A centralização do texto vem da regra
  estrutural do `visual-refresh.css` (input dentro de `th` do `thead`), de graça.
- **Nomes dos templates padronizados como "Nome (SIGLA)"** — TER/OPC/SWAP/MID — sem os
  prefixos "Swap –"/"Opções Flexíveis –" (a categoria já agrupa). O TAXACAMBIOTER perdeu
  o bloco "Registro – Dados Variáveis": o Tracker nunca gera a linha tipo 2 (manda sempre
  `000` datas de verificação), e o bloco documentava um trecho de arquivo que não existe.
- **O VCP entrou vinculado ao template de Atualização de PU/Fator** — o caso concreto de
  "mesmo template, duas páginas": Accrual e VCP geram o mesmo arquivo, mas cada página
  tem as próprias colunas, e o mesmo campo puxa de coluna com nome diferente em cada uma
  (`Código IF` × `Código do Contrato`; `Fator Parte` × `PARTE / Fator`). O mecanismo já
  era o `source_by_page` do §236; o que faltava era o dado do VCP (9 colunas de
  `_VCP_COLUMNS` + os dois overrides). A geração automática continua saindo só do Accrual
  — o vínculo documenta o formato, e a nota do template diz isso.
- **Bug que apagava as colunas em silêncio**: o Save do modal Link Pages remontava
  `linked_pages` só com `{label, url}` — salvar qualquer vínculo descartava as `columns`
  de TODAS as páginas já vinculadas, e os dropdowns de origem daquele template abriam
  vazios. Agora o save preserva a entrada existente da página que continua marcada.
- **Page Columns**: botão na visão de página que abre as colunas daquela página num modal
  (uma por linha, editáveis). É o que permite a uma página recém-vinculada ganhar as
  opções do dropdown sem tocar em código — as colunas são cadastro do par
  template × página, não lista fixa no JS.
- **SweetAlerts no padrão**: o guard de navegação com edição pendente saiu do `confirm()`
  nativo para o Swal de warning com botões traduzidos — e como Swal é assíncrono,
  `guardSrcEdit` virou continuação (`guardSrcEdit(proceed, onCancel)`); o `onCancel` do
  switcher de template devolve o `select` ao valor anterior em vez de re-renderizar (o
  re-render matava os inputs da edição em curso). Delete com "Yes, delete"/"Cancel"
  traduzidos e `#dc3545`; erros com título "File Interface" (não "Error"); sucesso no
  formato do Mapping (ícone, 1,3 s, sem botão) em vez de toast de canto.

## §238 — File Interface v3: o cadastro passou a COMANDAR a geração e os previews

Até aqui o File Interface (§235–§237) era documentação viva: os layouts existiam em três
cópias independentes — o gerador no servidor (o que vale), o preview de duplo clique de
cada página (espelho em JS) e o cadastro. Agora as três são uma: **o template é a
autoridade da ESTRUTURA da linha** (ordem dos campos, larguras do `format`, literais dos
campos Fixed — com override por página), e **o código continua dono dos VALORES
calculados**. Editar um Fixed, reordenar ou acrescentar campo pela tela muda o arquivo
real e o preview no request seguinte, sem restart.

O desenho, e por que ele é assim:

- **Motor** (`routes.py`, seção FILE INTERFACE): `_fi_tpl_cached` (cache por mtime, como
  os mappings), `_fi_width` (`X(n)`/`9(n)` → n; `9(a)V9(b)` → a+b, o V não ocupa
  posição), `_fi_field_src` (override `source_by_page` vence) e **`_fi_build_line(key,
  block_id, values, page_url)`** — `values` é `{seq do template: string JÁ formatada}`
  dos campos não-Fixed, usada **verbatim** (só ljust-espaços se vier curta; nunca trunca
  nem reformata). Fixed sai do cadastro padded pela largura (X → espaços à direita, 9 →
  zeros à esquerda; Fixed vazio = campo em branco). Posicional concatena; delimitado
  junta com o `separator` e fecha com token vazio (padrão OPC). Template/bloco ausente →
  `ValueError`, e os endpoints devolvem 500 com "check /file-interface" — **sem fallback
  para a montagem antiga**: arquivo para a B3 não sai meio montado em silêncio.
- **Por que o valor não vem do cadastro**: as excentricidades históricas (Contrato em 10
  chars onde o manual pede 11, número com vírgula, alinhamento à direita em campo X)
  vivem no gerador, e reformatar no motor mudaria bytes enviados à B3. A troca foi
  provada **byte a byte**: cinco checks novos (`check_fi_{ter,opc,taxacambioter,accrual,
  mid}.py`) carregam cópias `_legacy_` da montagem antiga e comparam linha a linha em
  todos os ramos (pernas Lawton/Atacama, asiáticos, campos vazios, espelhos do MID,
  views do Accrual), mais um e2e de arquivo inteiro no OPC.
- **Onde o cadastro foi corrigido para a PRODUÇÃO** (manual citado no
  `source_note`/`notes`): TAXACAMBIOTER com Contrato `X(10)` 38-47 e linha de **86**
  chars (o manual pede 87 — divergência histórica preservada); Classe do Ativo do TER
  como Fixed com o alinhamento à direita embutido (19 espaços + código, porque o motor
  faz ljust em X); campo 6 do bloco tipo 2 em `X(18)` 35-52 (produção escreve a data à
  esquerda + filler); formatos `v` minúsculo → `V` nos templates de Swap/MID (o `_fi_width`
  não media, e os Fixed em branco colapsariam para largura zero). O COE (0475) do MtM
  **não tem cadastro** e continua montado à mão, anotado no código.
- **Sete geradores** passam pelo motor: TER genérico (`_generic_ndf_ter_line`, com
  `page_url` por produto — os overrides por página valem), TER do NDF Commodities
  (`_ndf_comm_ter_lines`), OPC do FXO e do Opt Commodities, TAXACAMBIOTER
  (`_ndfop_conecta_fields`, que também fatia a linha pronta para o preview — o preview
  mostra exatamente os bytes do arquivo), Accrual e MID. Os headers de arquivo também
  saem do bloco `header` do cadastro.
- **Previews**: API `GET /api/file-interface/page-spec?url=<página>` devolve os blocos
  com Fixed resolvido por página. As 6 páginas de New Deals + o Accrual fazem prefetch
  no load (`FI_SPEC`) e montam a lista do template — Fixed padded como o motor,
  não-Fixed mapeado por seq (`'04' ≡ '4'`); **fetch que falha degrada para a lista fixa
  antiga**, o padrão dos mappings. Cabeçalhos da tabela tipo 2 idem. MtM e o Daily
  Settlement Other Publisher já eram servidos e saem com os rótulos do template.
- **Dois previews mentiam e agora dizem o byte**: o Vanilla mostrava Classe do Ativo
  `'4'` (resquício da cópia do NDF Commodities — errado para termo de moeda; hoje sai em
  branco, e se quiserem `'2'` como no FWD Start é um override de página cadastrável pela
  tela), e o Other Publisher mostrava uma Data de Fixing da Moeda que o arquivo nunca
  levou (o gerador escreve em branco).
- **Duas varreduras de fonte foram atualizadas**, não enfraquecidas: `check_quoted_in_cents`
  e `check_quote_type` procuravam o desenho antigo (`f[13] = …`); a regra agora vive como
  values por seq (`'14': …`) e os padrões acompanharam.

Armadilha aprendida no processo: rodar 7 subagentes pesados em paralelo estourou o limite
de sessão no meio do trabalho — as retomadas preservaram o contexto, mas o certo é
escalonar em ondas.

## §239 — A Parte A do FWD Start pedia para riscar uma entidade à mão

O documento Word do FWD Start imprimia as duas entidades lado a lado — "<BANCO J.P. MORGAN S.A.> OR
<J.P. Morgan Chase Bank, N.A. – Filial Brasileira>" — em nome, CNPJ e assinatura, esperando que alguém
riscasse o lado errado à caneta. Agora `_conf_fwdstart_partea(picked, warnings)` resolve pela **LE dos
deals do grupo** (JPM → Banco / MGT → Filial Brasileira) e o texto sai decidido nos três lugares.

- **LE ausente, mista no grupo ou fora de JPM/MGT deixa a Parte A EM BRANCO com aviso** — o padrão da
  casa: em branco pede preenchimento; um default afirmaria uma entidade errada num documento assinado.
- O painel ganhou os campos de Parte A (nome + CNPJ, espelhados no documento como os da Parte B), e o
  Save recusa Parte A vazia **nas duas pontas**: foco no campo no navegador, `400 missing_partea` no
  servidor.
- **Os textos vivem ao lado do template no `routes.py`, não num mapping — de propósito.** A grafia é a
  do documento assinado, diferente da grafia do Reference Data que o `le-spn` guarda; cadastrá-la seria
  uma segunda lista das mesmas entidades, envelhecendo sozinha. É uma exceção consciente à regra do §6.

## §240 — A planilha de Pending que a mesa mantinha à mão virou card do Control Panel

O card **Pending Confirmations Spreadsheet Metrics** grava a "PENDING - Outstanding Confirmation
OTC.xlsx" em `I:\Confirmation\Derivativos\Movimento\Pending Confirmation`, sobrescrevendo a anterior.
As linhas são as do chip **Status = Pending** da página (a categoria é recomputada na leitura, não o DB
em que a linha mora), e as colunas seguem o **layout histórico da planilha** — inclusive as que a página
não tem (procuração, Vias, Devolvido Por, Controle Envio Draft), que saem em branco com o cabeçalho
preservado, para quem consome a planilha continuar achando as colunas no lugar.

- **Datas saem como DATA** (`number_format dd/mm/yyyy`) — texto seria General e o Excel do consumidor
  não ordenaria; texto livre numa coluna de data (`N/A`) é preservado.
- **Disparo todo dia útil ANBIMA às 10:45 de Brasília** (o pedido foi 7:15 PM IST = 13:45 UTC), com a
  mecânica do Deals Monitor: claim em disco, catch-up no restart e **slot devolvido quando a gravação
  falha** (share fora, arquivo aberto no Excel) — a volta seguinte retenta em vez de perder o dia. A
  escrita é temp + `os.replace`: ninguém abre um xlsx pela metade. O Run do card grava na hora (feriado
  incluído — quem clicou decidiu) sem consumir o claim do automático, e a linha de status do card
  responde "a planilha de hoje saiu?" sem abrir o log. (`_pcx_rows` → `_pcx_build_xlsx` →
  `_pcx_save_spreadsheet`; scheduler `_pcx_scheduler_loop` + `_pcx_claim_slot`.)
- **O primeiro arquivo gerado voltou da mesa com dois de-paras errados**, e é a lição: de-para de
  planilha legada se prova contra o CONSUMIDOR, não contra o nome parecido. "Document type" saía do
  Signature Type da página — não é a mesma coisa, e passou a ir em branco como as demais sem
  contraparte; e **EA é a DATA da economic affirmation**, não texto — saía General, agora sai
  `dd/mm/yyyy` como as outras colunas de data.

## §241 — O recap interno abre no Monitor, e o Validate sai do New Deals

Duas mudanças da mesma conversa — o Confirmations Monitor vira o lugar único de conferir e assinar:

1. **O card ganha um chip para o e-mail de recap interno** que a mesa guarda na MESMA pasta do PDF,
   identificado pelo nome (`_MC_MAIL_TOKENS = ('internal', 'recap')` cobre Internal Recap / Recap /
   Internal, `.msg` ou `.eml`). O chip abre um **preview em tela** — um `.msg` como link baixaria o
   arquivo e mandaria a pessoa ao Outlook, que é o passeio que o preview evita. O corpo do e-mail **não
   entra no DOM da página**: o endpoint devolve o HTML com `Content-Security-Policy: sandbox` e o
   Monitor o carrega num iframe sandboxado — script de e-mail não roda nem aberto numa aba. O cache de
   pasta passou a guardar a **listagem inteira** (PDF e e-mail saem da mesma ida ao share), e o e-mail
   passa pelo mesmo afunilamento por Trade ID/Ativo dos PDFs, **caindo para a lista completa quando nada
   casa** — o recap costuma ser nomeado por contraparte/data, sem Trade ID, e o filtro não pode sumir
   com ele. A resolução de arquivo do Electronic Inventory virou helper (`_ei_locate_file`) para o
   preview usar a mesma guarda de path-traversal do `/file`.
2. **Os diálogos de Confirmations das quatro páginas de New Deals** (FWD Start, NDF Comm, Opt Comm,
   Opt FXO) **perdem o botão Validate**: toda validação é feita no Monitor, onde a esteira OTC → MO/FO
   mora — dois lugares validando era ter duas respostas para a mesma pergunta. O checklist pós-geração
   do editor fica: ele fecha o ciclo do DOCUMENTO, não a etapa da esteira.

## §242 — O Maturity Month/Year da Intrag era o mês de pricing

O campo da Intrag NDF (linhas espelhadas dos deals de NDF Commodities) saía do `Month` do deal — que é o
mês de **pricing** e nem sempre coincide com o mês do contrato embutido no código do ativo subjacente
(`AULF27` = jan/2027). Agora ele vem do cadastro da **Index B3**: Mes/Ano Vencimento do Código do Ativo
Subjacente no `Subjacente.json`.

- **Vencimento fora de faixa sã** (o cadastro tem ano digitado errado: `AGD1` → 2202) **ou código sem
  linha caem no comportamento anterior** — `Month`, depois Settlement — em vez de imprimir um ano
  impossível num arquivo de registro.
- **O lookup do Subjacente virou cache por mtime** (`_subjacente_by_code`; era um dict carregado na
  subida do processo): com o campo dependendo do cadastro, uma correção feita na tela Index B3 tem de
  valer no request seguinte, sem restart — a mesma regra dos mappings. De quebra passou a valer também
  para a Bolsa e a Unidade de Negociação, que já saíam de lá.
- A Intrag **Option** não tem coluna de Maturity Month/Year — nada a mudar lá.

## §243 — O registro do Other Publisher não quebrava em visão banco × visão Lawton

O send-conecta genérico (`4478d38`) foi desenhado esperando que a API entregasse a perna espelho do
Lawton como **deal próprio** (a convenção do ndf-commodities: perna com LE LAWTON e cliente = Banco).
Ela **nunca chega** — o Athena manda só a visão banco —, então o balde LAWTON ficava vazio e o arquivo
visão Lawton simplesmente não saía.

O conserto é a convenção da TAXA do próprio Other Publisher (fixings): **UMA linha Lawton → DUAS
visões**. No envio, todo deal do balde BANCO cujo Client contém LAWTON ganha um espelho sintetizado —
`_nd_lawton_mirror` (LE = LAWTON, Client = Banco, direção invertida) passado pelo MESMO
`_generic_ndf_ter_line`, então participante/papel/contraparte trocam e o resto da linha sai byte a byte
igual. Três decisões:

- **O par é por termos econômicos, não por Deal ID.** Cada perna de um trade intragrupo tem o SEU Deal
  ID; a correlação possível é `_nd_lawton_sig` = (trade date, settlement, notional). Quando a perna
  Lawton explícita vier no lote, ela **consome uma assinatura** (`explicit.remove`) e o espelho daquele
  trade não é sintetizado — e é `remove` de UMA ocorrência de propósito: dois trades idênticos no mesmo
  dia não podem dividir uma perna explícita só.
- **`count` conta DEALS, não linhas** — a notificação e a resposta dizem quantas operações foram
  registradas, não quantas linhas os arquivos têm.
- **O preview de duplo clique mostra as duas visões** (Banco × Lawton e Lawton × Banco, 28vh cada) pelo
  mesmo desvio no `buildConectaFields` — o que se vê é o que os dois arquivos levam.

O **FWD Start herda a regra de graça**: o builder é compartilhado, e a mesma lacuna estava latente lá.

## §244 — O ciclo do card de Confirmations termina no OTC

Pedido da mesa: o e-mail de **Deals Monitor Pending Action** e o New Deals Monitor só cobram o que está
**Pending OTC**. Confirmação que já passou para MO/FO é assunto do Confirmations Monitor — para a mesa
de OTC ela está 100% concluída, e mantê-la aberta no card cobraria trabalho de outra mesa.

- **Um ponto único de tradução**: `_conf_esteira_stages()` passa a devolver a etapa crua só quando ela é
  `Pending OTC`; todo o resto (Pending MO, FO, MO/FO, vazio) vira `Ok`. Card, seção e e-mail leem o
  mesmo snapshot (`_ndm_monitor_snapshot`), então mudam juntos — não há três lugares para esquecer.
- No e-mail, `_ndm_pending_blocks` conta `('success', 'ok')` como concluído e o breakdown exclui os
  dois — o que de quebra conserta um bug anterior: grupo em `Ok` contava como pendente do e-mail **para
  sempre**, porque só `success` fechava a conta.
- **A regra da menos avançada fica**: grupo com um trade ainda em Pending OTC continua aberto — dizer
  `Ok` porque nove de dez passaram esconderia a décima.
- `_CONF_STAGE_ORDER` mantém as etapas MO/FO defensivamente (se um dia a tradução mudar, a ordenação já
  sabe o que fazer com elas). O CLAUDE.md §7 foi reescrito para a nova regra.

## §245 — Ticket aberto agora avisa por e-mail

O Support Center só avisava no **encerramento**. Agora `api_tickets_create` chama
`_tk_send_opened_email(ticket)` — mesmo desenho do closed: template próprio
(`email-template-ticket-opened.html`, clone do de encerramento com badge azul "Current Status" e as
linhas Ticket ID / Subject / Opened By / Priority / Opened On / Tags), assunto
`OTC Tracker — Ticket #NNNN opened by <nome>`, **From e Cc `SHARED_MAILBOX`**
(otc.tracker@jpmorgan.com), **To `_TICKET_NEW_TO`** — env `TICKET_NEW_EMAIL_TO`, default
giulliano.luccia@jpmorgan.com.

**Best-effort de propósito**: o ticket já está persistido quando o e-mail sai; falha de SMTP só é logada
e devolvida em `email_error` no JSON do create — abrir ticket nunca falha por causa do relay. O envio
real só é testável na rede JPM (o SMTP é o relay interno).

## §246 — Toda notificação nova precisa de destino no mapa (o clique morto do TED Release)

"A notificação de TED Release do Other Products Summary não faz nada quando clico." O rótulo `page` de
uma notificação é a chave que decide o destino do clique (sino, toast e push do sistema) e quem a
enxerga no feed — e **nove páginas** gravavam notificação com rótulo que não existia em mapa nenhum:
Other Products Summary, NDF Summary, Operations B3, OTM Settlements, Latam Desk Position, NDF Cockpit,
Cognos, File Interface e Mapping. O aviso aparecia normal; o item só nascia como `<div>` em vez de
`<a>`, sem erro em lugar nenhum.

- As nove entraram nos **três mapas de uma vez** — `_NOTIF_PAGE_URL` (routes.py), `PAGE_URL` do
  `partials/topbar.html` e `PAGE_URL` do `static/js/sw-push.js` —, com a URL do próprio menu
  (Latam é `/other-products-swap-latamdeskposition`).
- **A regra agora é presa por teste, não por lembrança**: `check_notif_page_url.py` ganhou o check 7,
  que varre o `routes.py` por AST e exige que todo rótulo `page` LITERAL passado a
  `_create_notification` resolva via `_notif_page_url`. Os checks 1–6 provavam que os três mapas
  concordam ENTRE SI — era exatamente por fora deles que o rótulo órfão passava. Notificação nova em
  página nova sem cadastrar o mapa = teste vermelho.
- O padrão de sempre: **rode `check_notif_page_url.py` depois de mexer em notificação** (criar
  `_create_notification` novo, renomear rótulo, adicionar página). O CLAUDE.md §7 ganhou o resumo.
- De carona: a ação `TED Release Sent` ganhou ícone próprio no `ACTION_META` (send/verde) em vez do
  sino genérico.

## §247 — O Export completo (Copy · CSV · Excel · Print · PDF) virou padrão obrigatório

O Export do Track Confirmations só oferecia CSV e Copy — export feito à mão sobre a matriz visível,
enquanto o padrão das páginas de New Deals sempre foi o conjunto completo via DataTables Buttons.

- **Track Confirmations**: o export manual (`visibleMatrix`/`toCsv`) saiu; entraram os plugins do
  DataTables Buttons (buttons + bootstrap5 + jszip + pdfmake + vfs_fonts + html5 + print, com o snippet
  síncrono de registro do JSZip copiado do New Deals — sem ele o Excel não sai) e uma instância
  `new $.fn.dataTable.Buttons(table, …)` criada DEPOIS do init (a tabela não usa `buttons:` no init nem
  é destruída/recriada, então a instância vive a página inteira). Os cinco itens do dropdown da toolbar
  disparam por nome (`table.button('excel:name').trigger()`), preservando o visual da barra.
- **Paridade com o export antigo mantida de propósito**: CSV com `fieldSeparator: ';'` e `bom: true`
  (é o que faz o Excel pt-BR abrir com colunas separadas e acentos vivos, e era por isso que o export
  manual usava `;` e BOM), nome de arquivo `track-confirmations`, e `exportOptions` com
  `columns: idx >= OFFSET && visível` (checkbox e Actions fora) +
  `modifier {search/order: 'applied', page: 'all'}` — exporta o que está NA TELA, como sempre.
- **O padrão agora está escrito**: o bullet da Toolbar no CLAUDE.md §3 deixou de dizer "ao menos CSV e
  Copy" e passou a exigir o conjunto completo **Copy · CSV · Excel · Print · PDF**, com a receita
  (Buttons pós-init + trigger por nome) para páginas que montam a toolbar à mão. Página nova com botão
  Export nasce com os cinco; página velha com menos é bug de consistência.

## §248 — No Monitor, só o recap é clicável, e o Validate sem contrato fica riscado

Pedido da mesa, em cima do §246/§241: nos cards do Confirmations Monitor o chip de PDF deixou de ser
link — a confirmação se abre pelo **Validate** (tela de validação), e dois caminhos para o mesmo
documento convidavam a "validar" sem passar pelo checklist. O chip continua na tela como INFORMAÇÃO
(nome + ícone, cursor default); só o **e-mail de recap** (roxo) permanece clicável, abrindo em nova aba.

- **Validate sem contrato na pasta**: quando o `/docs` responde e o grupo não tem PDF, o botão verde
  vira neutro (`btn-secondary`), ganha um **risco transversal** (`.mc-val-off::after`, rotate(-10deg))
  e o tooltip `noContractTip` ("no contract to validate yet", no `_TRANS` en/br/es — texto dinâmico não
  passa pelo I18nManager). O clique é bloqueado por handler delegado E o `href`/`target` são removidos:
  `preventDefault` não cobre o clique do meio, e `<a>` sem destino sai da navegação por teclado
  (`aria-disabled` junto).
- **Só quando o servidor OLHOU a pasta**: o `pinta(el, docs, checou)` só risca com `checou=true` (o
  caminho de sucesso do fetch). No catch — servidor reiniciando, timeout — não se afirma nada: riscar
  ali diria "não há contrato" para a fila inteira num soluço de rede.
- O botão de SÓ LEITURA (View, de quem não é da mesa) não é tocado: ele já é a resposta a outra
  pergunta (acompanhar, não assinar).

## §249 — "Blank" no File Interface é Source FIXED com valor vazio (a Data de Fixing do FWD Start)

"Ajustei o campo Data de Fixing do Ativo Subjacente do FWD Start para Blank e o preview/arquivo
continuam mostrando a data." A edição não surtiu efeito porque **Source = Page significa "o GERADOR
manda o valor"** — a coluna escolhida no dropdown é documentação de onde o valor vem, não o valor: o
motor injeta o que o gerador calculou pelo `seq`, com o detalhe vazio ou não. Limpar o dropdown, ou
trocar a origem para "—", não esvazia o campo; **o único jeito de cadastrar um campo em branco é
Source = `Fixed` com o valor vazio** (é como o Other Publisher sempre esteve: Fixed, valor vazio, nota
"Blank" — o motor preenche as 8 posições com espaço).

- O override do `/new_deals-ndf-fwdstart` no campo 19 do `termo-multiclasses.json` (versionado) foi
  trocado para `Fixed`/vazio/"Blank", igual ao do Other Publisher. Preview de duplo clique e geração
  leem o mesmo cadastro (page-spec e `_fi_build_line` resolvem o override por página), então os dois
  mudam juntos.
- **O gerador continua calculando `fix_single`** e entregando ao motor: com o override Fixed ele é
  ignorado, e re-apontar o cadastro para Page volta a mandar a data do fixing único sem tocar em
  código — é a reversibilidade que o desenho promete.
- Atenção no deploy: o JSON é VERSIONADO. Se a instância do time salvou uma edição local no mesmo
  arquivo pela tela, o `git pull` vai parar em conflito — descarte a edição local
  (`git checkout -- apps/static/data/file-interface/termo-multiclasses.json`) antes do pull, que a
  versão do repo já traz o Blank.

## §250 — A aba da planilha de Pending é CONFIRMATIONS (o nome da aba também é contrato)

O time global de métricas quebrou lendo a "PENDING - Outstanding Confirmation OTC.xlsx":
`"CONFIRMATIONS$ is not a valid name…"`. É o erro do driver OLEDB/Jet quando a QUERY pede uma aba que
não existe no arquivo — o job deles faz `SELECT … FROM [CONFIRMATIONS$]`, a planilha legada tinha a
aba `CONFIRMATIONS`, e a nossa nascia como `PENDING`.

Mesma lição do §240 pela terceira via: o de-para com planilha legada se prova contra o CONSUMIDOR, e o
contrato não é só o cabeçalho — **o nome da aba faz parte do layout**. `_pcx_build_xlsx` agora grava
`ws.title = 'CONFIRMATIONS'`; colunas, datas e o resto ficam como estavam (os headers foram
verificados byte a byte na mesma conversa — 100% ASCII, sem caractere invisível; o erro nunca foi de
caractere, era a aba).

## §251 — Commodities × B3 ganha TRADE TYPE, e o BRT_IPE vira duas linhas

Alguns códigos de ativo subjacente mudam conforme o trade é vanilla ou asiático, e o cadastro não
tinha onde dizer isso — a distinção do BRT_IPE morava no ramo SPECIAL do código. O mapping
`commodities-b3` ganhou a coluna **TRADE TYPE** (`VANILLA` / `ASIAN` / `BOTH`; em branco = BOTH): a
linha só responde pelo tipo que ela declara.

- **BRT_IPE agora são DUAS linhas**: a `SPECIAL` ficou **só da asiática** (near `CO"MY"` quando o
  contrato é o mês seguinte à liquidação, far `CO1-2` a partir de dois meses — §212) e a vanilla ganhou
  linha `PREFIX` própria com `CO"MY"` padrão. O código emitido é o MESMO de antes (vanilla COH7,
  asiática COH7/CO1-2 pela distância) — o que mudou é que cada tipo tem a sua linha cadastrável.
- **Os mapas dos consumidores viraram por tipo** (`{mkt: {'V': …, 'A': …}}`) nas TRÊS cópias da regra:
  `_box_commodity_maps`/`calculate_b3_id` (otc_boxparse.py), `otc-fileupload.js` (que serve os New
  Deals de NDF Comm e Opt Comm via `OTCFileUpload.calculateB3Id` — as páginas já passavam o
  `isVanilla`) e `deals-processing-table.js`. `b3MapEntry`/`_b3_map_entry` resolvem a entrada pelo
  tipo, e **valor plano (formato antigo) segue valendo para os dois** — fixtures e fallback literal
  não quebram. Linha VANILLA não responde pela asiática: sem outra linha, o market cai na regra
  genérica de prefixo, como qualquer market sem cadastro.
- **Upgrade na leitura**: linha antiga sem a coluna vira `BOTH`; a `SPECIAL` do BRT_IPE vira `ASIAN` e,
  quando essa migração acontece (arquivo anterior à coluna), a linha `PREFIX`/`VANILLA` do BRT_IPE é
  criada — num arquivo já migrado a ausência dela é decisão de quem editou, e não volta.
- **A tela corrigiu o destaque do `MY`**: o `PATTERN_COLS` só destacava linha PREFIX, então o
  `CO"MY"` da SPECIAL do BRT_IPE aparecia com as aspas literais. Agora PREFIX e SPECIAL destacam, e a
  coluna B3 CODE FAR entrou por simetria.
- Testes: `check_b3_pattern.py` cobre o filtro por tipo, o upgrade (inclusive "vanilla apagada não
  volta") e a paridade das duas cópias JS (o recorte ganhou o `b3MapEntry`); `check_boxparse.py`,
  `check_quote_type.py` e `check_co12_roll.py` seguem verdes.

## §252 — FIXED QUOTE aposentado, WTI por trade type, ordenação no /mapping e o copy das tabelas

Quatro pedidos da mesma conversa sobre o Commodities × B3 e a tela de Mapping:

- **FIXED QUOTE saiu do cadastro.** Desde o §177 ele só escolhia F/340 vs A/358 quando as colunas de
  cotação estavam vazias — os valores de verdade já moram em `QUOTE TYPE NDF` / `INFO SOURCE`. O
  `_commodities_b3_quote_defaults` ainda LÊ o flag de arquivo antigo (materializa o F/340 das linhas
  YES nas colunas) e então o remove da linha; `_b3_quote_cfg` e o `b3-quote-config.js` passaram a ter
  um default único (A / 5 / 358). **Os PTS**** saíram junto: eram linhas sem MARKET que só existiam
  para carregar o flag. Atenção: coluna de cotação LIMPA pela tela agora cai em A/358 — o "histórico
  por flag" não existe mais.
- **WTI_NYMEX virou duas linhas**, no desenho do BRT_IPE (§251): `PREFIX`/VANILLA `WTI"MY"` e
  `FIXED`/ASIAN **`CL1`** (o contínuo, literal — pedido da mesa). A migração no upgrade restringe o
  PREFIX antigo à vanilla e cria a linha FIXED; fallbacks dos dois JS acompanham (`{V: …}`/`{A: …}`).
- **O JSON versionado (`mappings/commodities-b3.json`) foi regravado no formato novo** — 29 linhas,
  sem FIXED QUOTE, sem PTS, WTI e BRT divididos por tipo — para o pull entregar o formato pronto; o
  upgrade continua cobrindo a instância cujo arquivo divergiu.
- **A tabela do /mapping ordena por coluna**: clique no header alterna asc/desc (seta ▲/▼), e o
  Commodities × B3 abre SEMPRE por MARKET A→Z (`defaultSort`; trocar de aba volta ao padrão). Só a
  EXIBIÇÃO ordena — o arquivo mantém a ordem de cadastro, e o `data-idx` das ações continua apontando
  para a linha certa porque o `filteredRows` carrega o índice original. O header não é remontado no
  clique (os filtros digitados vivem nele); só o indicador e o corpo mudam.
- **Auditoria do copy de célula** (Ctrl+C padrão): as 40 páginas com `<table>` foram varridas. Duas
  páginas REAIS estavam sem o mecanismo e ganharam `table-std.js` + `otcCellCopy`: **Users**
  (`users-roles`, skip checkbox+Actions) e **Ticket List** (`tickets-list`, que também ganhou o id
  `tk-table`; skip Actions). O resto ou já tinha (inclusive via JS compartilhado do swapchar, que
  cobre cinco páginas) ou é tabela DEMO do template comprado com dado fake hardcoded
  (`file-interpreter`, `email`, `users-profile`, `dashboard-2`) — ali não há o que copiar.
- Testes: `check_quote_type.py` reescrito para a semântica sem flag (inclui "PTS saem na migração" e
  "o flag sai da linha"); `check_b3_pattern.py` ganhou os casos do WTI (vanilla WTIZ6 / asiática CL1,
  upgrade em duas linhas). `check_boxparse.py` e `check_co12_roll.py` seguem verdes.

## §253 — A planilha de Pending precisa do TÍTULO MESCLADO da legada (o segundo erro do time global)

Depois da aba CONFIRMATIONS (§250), o job global quebrou de novo: `"No value given for one or more
required parameters"` — o erro do OLEDB quando a query referencia colunas que ele não encontrou. A
causa era a linha 1: a planilha LEGADA tem um título mesclado na linha 1 e os cabeçalhos na linha 2, e
o leitor deles começa na 2 — com os nossos cabeçalhos na 1, ele achava DADOS onde esperava os nomes.
`_pcx_build_xlsx` agora replica o layout legado linha a linha: A1:V1 mesclado com o título "PENDING -
Outstanding Confirmation OTC", cabeçalhos na linha 2, dados da 3 em diante, freeze em A3. Terceira
lição do §240, agora completa: **o CONTRATO com o consumidor é o arquivo INTEIRO** — aba, título,
posição do cabeçalho e nomes de coluna.

## §254 — A esteira ganha Pending Legal e Pending FepWeb, e passa a espelhar no Pending Confirmation

Pedido da mesa, o maior redesenho da esteira desde o §217. O ciclo agora é:

    (Pending Legal, opcional) → Pending OTC → Pending MO e/ou FO → Pending FepWeb → Ok

- **Pending Legal é um HOLD manual** — a confirmação aguarda o jurídico, fora da fila do OTC. É o
  ÚNICO valor de Pending que se escreve à mão (com o Pending OTC que o desfaz): gravado na linha, ele
  VENCE a derivação até alguém soltá-lo. Entra pela edição em massa do Track (a coluna Pending entrou
  no dropdown, com autocomplete dos DOIS valores manuais) ou sai pelo card do Monitor.
- **Pending FepWeb é DERIVADO e não se digita**: todas as validações feitas e o `Enviado p/ cliente
  (desbloqueado no fep)` ainda vazio. **Ok passou a exigir a data do envio** — validar não fecha mais
  a esteira, enviar fecha. O upsert ignora qualquer outro valor manual de Pending (e a tela avisa).
- **Toda gravação da esteira espelha no Pending Confirmation** (`_mc_pc_sync`): a chave é a mesma dos
  dois lados (MC `Trade ID` = PC `Trade Number`, nascem juntos no `_pc_save_from_deal`). O estágio
  entra verbatim no `Pending Status`; o `Ok` vira **Pending Digital Signature** ou **Pending
  Original** pelo `SIGNATURE TYPE` do RefData — documento enviado, o que se espera é a assinatura.
  Falha do espelho só loga: linha importada da planilha antiga não tem irmã no PC.
- **Monitor com CINCO cards**: Pending Legal (início) e Pending FepWeb (fim), no padrão dos demais
  (`_extra_card`: mesmo agrupamento por documento, sem regra de mesa e sem SLA). O botão do Legal
  ("Release to OTC") solta o hold; o do FepWeb ("Mark as sent") carimba o Enviado p/ cliente com a
  data de hoje — os dois com SweetAlert de confirmação, trava da mesa de OTC Ops
  (`/api/manual-confirmation/legal-release` e `/fepweb-sent`, 403 para quem não é da mesa; sem
  permissão o botão nem aparece e o card fica informativo).
- **Track**: card Pending FepWeb (entre FO e Ok, filtro por clique como os demais); a coluna `Nome
  fep` travada em ~1/4 da largura (reticências; o Ctrl+C copia inteiro); a coluna Aging Confirmação
  perdeu o fundo cinza (segue a listra da linha; o itálico fica como marca de derivada); o mass edit
  foi para o padrão do Pending Confirmation — "Select Column to Apply" e o campo de valor SEMPRE
  visível, desabilitado com "Select a column first…" até a coluna ser escolhida.
- Notificações: `_MC_STAGE_NOTIFY_ROLES` ganhou os dois estados (BO+MASTER — os dois são ações do
  OTC Ops). `check_manual_conf.py` e `check_mc_notify.py` reescritos para o ciclo novo (FepWeb antes
  do Ok, hold vence derivação, cinco cards).

## §255 — 'Pending OTC' à mão REABRE a esteira (confirmação regerada), e os cinco cards lado a lado

O §254 deixou o `Pending OTC` manual valendo só como release do hold Legal — em linha com validações
preenchidas ele era silenciosamente ignorado, e a mesa não tinha como devolver à fila uma confirmação
que foi **regerada** depois de validada (o documento novo precisa ser conferido de novo, pelas três
mesas).

- **Semântica nova, uma só**: gravar `Pending OTC` pela grade/edição em massa do Track significa "esta
  confirmação volta para a fila do OTC". O `api_mc_upsert` limpa `Conferido OTC`, `VALIDADO p/ MO`,
  `VALIDADO p/ FO` e o `Enviado p/ cliente` — os carimbos (Time Stamp) caem pelo undo que já existia
  ("desfez a validação: o carimbo não sobrevive a ela") — e grava `Pending = ''` para a derivação
  decidir. Cada mesa revalida e os carimbos novos substituem os antigos; os comentários de atraso
  ficam (são história). O espelho no PC (`_mc_pc_sync`) leva o `Pending OTC` junto.
- **Numa linha só em hold Legal não há o que limpar**, e o mesmo valor age exatamente como o release
  de antes — por isso não são dois comandos.
- **Reabrir é desfazer validação alheia**, então quando há algo a limpar a gravação exige a mesa de
  OTC Ops (`_mc_can_validate(STAGE_OTC)`, 403 `stage_forbidden` — a mesma trava dos dois botões do
  Monitor). Soltar um hold sem nada validado segue livre, como era.
- **Monitor: os cinco cards lado a lado** — a coluna virou `col-12 col-md-6 col-xl` (o `col-xl` sem
  número divide o flex por igual, porque 12/5 não fecha em coluna inteira) com `min-width: 0` no
  filho do `#mc-cards`: flex item tem `min-width: auto`, e um nome de cliente comprido alargava um
  card às custas dos vizinhos.

## §256 — A planilha de Pending muda de contrato: cabeçalho na linha 1 e as 31 colunas por extenso

O time global refez a leitura (Confirmation_Latam) e passou o layout novo por extenso: **cabeçalhos
na linha 1, dados a partir da 2, SEM o título mesclado** — o §253 (que reintroduziu o título da
planilha legada) deixa de valer — e **31 colunas com nome e ordem fixos**, de `LOB` a `Abono`.

- A lista inteira vive em `_PCX_COLUMNS` (routes.py) e é o contrato: coluna que a página não tem sai
  **vazia mantendo a posição** (tirá-la deslocaria as demais na query do consumidor). As novas com
  dado da página: **Signature Type** (a derivada do RefData que o PC já tinha — e "Document type"
  continua vazia: chegou a ser preenchida com o Signature Type e a mesa confirmou que NÃO é a mesma
  coisa). As demais novas (`Data Devolução 2º Via`, `Controle 2º Via`, `Ano`, `Pending IS`,
  `Trade Number IS FEP WEB`, `Baixa Sem Abono`, `Pendência`, `Abono`) saem em branco.
- A aba segue `CONFIRMATIONS` (§250) e as datas seguem como data de verdade com `DD/MM/YYYY`.
- O nome pedido veio com um espaço antes de `Trade Date` (`…Product Type; Trade Date;…`) — foi
  tratado como typo do separador: cabeçalho com espaço inicial não sobrevive ao OLEDB e nenhum outro
  nome da lista veio com espaço.

## §257 — Confirmations Escalation: a cobrança das validações vira card do Control Panel

Card novo (`confescalation`) que manda por e-mail as confirmações **paradas na esteira**. A base é a
MESMA do Track Confirmations e do Confirmations Monitor — `manual_conf.load_all()` com o `Pending`
derivado —, e não uma segunda leitura montada no card: um relatório que conta de outro jeito cobra
uma fila que a tela não mostra, e a mesa deixa de acreditar nos dois.

**Dois disparos e SETE listas de destinatários** (`confirmations_escalation_recipients.json`, no
`control-panel/` que não é versionado). Uma lista por e-mail, e não uma por mesa: quem recebe a fila
do EDG Corporate Swap não é quem recebe a do EDG Swap, e uma lista compartilhada mandaria a fila de
um produto para quem cuida de outro.

| Lista | Quando | Assunto |
|---|---|---|
| **TO — OTC Ops** | rotina: seg e qui, 17:00 BRT | `Confirmations Pending Validation - OTC` |
| **TO — Sales Support** | rotina: seg e qui, 17:00 BRT | `Confirmations Pending Validation - MO` |
| **Escalation — Sales Support** | todo dia útil, 17:00 BRT | o mesmo assunto do MO |
| **TO — FO · CEM Swap** | rotina | `… - FO - CEM Swap` |
| **TO — FO · EDG Swap** | rotina | `… - FO - EDG Swap` |
| **TO — FO · EDG Corporate Swap** | rotina | `… - FO - EDG Swap` (o mesmo, por pedido da mesa) |
| **TO — FO · EDG Option** | rotina | `… - FO - EDG Option` |

Os assuntos são em **inglês**, como o corpo e como todo e-mail do app — chegaram a ser em português
e a mesa voltou atrás. `otc_to` cobra a primeira parada da esteira (Pending OTC); **Pending Legal
fica de fora**, porque é hold manual e cobrar o OTC por ele seria cobrar o trabalho errado.
`fo_to`, a lista única do Front Office que existiu antes da quebra por produto, ainda é lida como
**padrão** dos grupos sem lista própria — quem já a tinha preenchido não vê a cobrança parar sem
aviso.

- **Segunda e quinta ROLAM.** Caindo em feriado ANBIMA, o relatório sai no próximo dia útil (D+1). A
  pergunta é feita ao contrário — *que segunda/quinta desemboca em hoje?* (`_ce_is_routine_day`) —,
  porque olhar só o dia da semana de hoje perderia a semana inteira quando a quinta é feriado: a
  sexta não é dia de rotina por si mesma, ela está pagando a quinta. Dois feriados seguidos rolam de
  novo, e uma quinta que role até a segunda encontra a própria segunda: sai **um** e-mail, porque o
  relatório é o retrato de agora, não um acumulado.
- **A escalação é o ÚLTIMO DIA ou o vencido**, e depois todo dia enquanto continuar vencido. `warn`
  do SLA acende também na véspera (`left == 1`) e essa fica de fora de propósito — escalar aí chega
  com a mesa ainda dentro do prazo. Lista própria porque é outro público: escalar diariamente para
  quem já recebe a rotina transforma a cobrança em ruído.
- **Os grupos do Front Office** são produto × LOB, um e-mail cada: `SWAP × CEM`, `SWAP × EDG`,
  `SWAP CORPORATE × EDG` e `FXO × EDG`. Os dois de EDG Swap têm o **mesmo assunto** (é o que a mesa
  pediu para o corporate) e são e-mails **separados** porque os destinatários mudam — distingui-los
  no assunto é trocar uma linha em `_CE_FO_GROUPS`. ⚠️ **`OPTION EDG` não é um produto** — é a opção
  de câmbio na LOB EDG, e o tipo dela é `FXO` (é o que o `upgrade` do `manual-conf-validation` faz
  com a linha antiga). Cadastrado como produto, o grupo nunca casaria com linha nenhuma, sem erro
  no log.
- O produto casa pelo **tipo de confirmação** (`confirmation_type`), nunca pelo texto cru da coluna:
  é ele que traduz as nomenclaturas que convivem no banco (o `OPTION` do New Deals, o `NDF` ×
  COMMODITY da planilha legada) para os oito nomes únicos.
- **Pending FO que não casa com nenhum grupo NÃO some calado**: vai para `unmatched`, que o card
  mostra em amarelo e o log registra. Silêncio aqui é confirmação que nunca é cobrada.
- `Pending MO/FO` entra nos **dois** e-mails — é a mesma confirmação devendo duas assinaturas, e
  mostrá-la só num esconde trabalho da outra mesa.
- **Nada pendente, nada enviado** ('empty', como no Deals Monitor). Sem destinatário salvo o
  desfecho é `no_recipient`, distinto do `empty`: o primeiro é a rotina rodando bem, o segundo é
  cobrança que não saiu de casa — o card mostra os dois com cores diferentes.
- **Um Run por e-mail** (`mode` = `otc`, `mo`, `fo-<grupo>`, `escalation`, mais o `routine` do
  rodapé, que manda o pacote): reenviar só o EDG Swap não pode obrigar a mesa a disparar os outros
  cinco. O Run
  roda mesmo fora de segunda/quinta e **não consome o claim** do disparo automático — queimar o
  horário faria a rotina do dia não sair.
- Claim/release/status em disco seguem a mecânica do Deals Monitor (§207/§222): a reserva é anterior
  ao envio, e só o **erro** devolve o slot para a volta seguinte do laço retentar.
- **O prazo é medido no dia do RELATÓRIO, não no relógio.** `_ce_run` passava o `ref` só para o
  cabeçalho e chamava `_ce_snapshot()` sem data: no disparo real os dois coincidem, mas num Run
  remarcado (ou no teste) o e-mail dizia uma data e pintava o vencido de outra — e a escalação, que
  é escolhida pela luz do SLA, levava a fila de outro dia. Um `ref`, uma medida.

**O botão do e-mail precisou de um endereço absoluto**, que o app nunca teve: `url_for` é relativo e
não serve num e-mail, e `request.url_root` não existe na thread do scheduler (num Run local sairia
`http://localhost:5005`, link morto para quem recebe). `_otc_app_url()` lê **`OTC_TRACKER_URL`** do
`.env` e, sem ele, monta `http://<hostname>:8050` — a porta em que o `start-prod.bat` sobe a
waitress. **Defina a variável na instância do time**; o padrão só acerta se o hostname resolver na
rede de quem lê o e-mail.

Corpo **e assunto** em inglês (a assinatura pedida, *Regards — OTC Tracker — Brazil OTC
Operations*, já vem assim): o assunto chegou a ser em português e a mesa voltou atrás — um assunto
acentuado sobre um corpo em inglês era a única coisa bilíngue do e-mail, e é sobre ele que se
escreve regra de caixa de entrada. Template único
(`pages/email-template-confirmations-escalation.html`) com as sete colunas pedidas — Trade Date,
Client, Product, LOB, Trade ID, Asset e Sent for validation. A luz do SLA marca a linha vencida
**dentro da coluna da data de envio** em vez de virar uma oitava coluna.

**O botão ficou magro DUAS vezes, e a causa é a mesma nas duas**: a altura estava vindo da linha de
texto. Pintar a célula e deixar o `<a>` só com o texto não dá altura nenhuma; passar o `padding` para
o próprio link resolve em quase todo cliente, mas **o Word do Outlook ignora padding vertical em
link**. A forma que funciona é `height:52px` + `line-height:52px` no `<a>` (com o padding só na
horizontal): o texto centraliza sozinho e a altura não depende de padding.

Os cantos arredondados exigiram **`v:roundrect`** — o Outlook desktop não conhece `border-radius`, e
é ele o cliente da mesa. Aqui o VML é seguro, ao contrário do banner do cabeçalho: a largura é FIXA
em px (`width:340px`) e não precisa acompanhar a célula, e foi exatamente a largura variável que fez
o `<v:rect>` do gradiente pintar ora estreito demais, ora na janela inteira (ver
`partials/email-gradient-header.html`). `arcsize="50%"` é a pílula do `border-radius:26px` do link,
e o `<a>` normal fica no ramo `[if !mso]` para não sair duplicado. Prazo:
`scripts/tests/check_conf_escalation.py`.

**O Guia do Usuário estava contando a esteira antiga.** O item 3.11 descrevia
`OTC → MO e/ou FO → Ok` com três cards — o desenho anterior ao §254/§255 —, então
quem seguia o guia não sabia que existe hold de Legal, que o `Pending FepWeb` só
fecha com o *Enviado p/ cliente* e que escrever `Pending OTC` à mão **reabre** a
esteira apagando as validações. Foi reescrito junto com o 3.15 (o card novo, as
sete listas, o Run por e-mail, o rolar do feriado e a diferença entre *nada
pendente* e *sem destinatário*), e o `.docx` regerado do `.md`, que é a fonte
única. Documentação de tela que descreve um fluxo que mudou é pior que
documentação faltando: ela é seguida.

---

## §258 — Gerar e validar passam a morar no MESMO lugar (o Confirmations Monitor)

Gerar era um botão da barra de cada página de New Deals e validar era um card do Confirmations
Monitor: as duas metades do mesmo trabalho em telas diferentes. A mesa de OTC precisava saber em
**qual das quatro páginas** o documento nascia para, depois, procurá-lo no Monitor — e o caminho de
volta não existia: o card dizia "sem contrato para validar" e parava ali.

Agora o ciclo inteiro mora no Monitor.

- **O botão `Confirmation` saiu das quatro páginas de New Deals** (FWD Start, NDF Comm, Opt Comm,
  Opt FXO): o contêiner `.confirmationBtn` e o diálogo de grupos foram apagados, ~100 linhas por
  página. Os endpoints `/api/new-deals/*/confirmations` **ficam** — quem os usa agora é o Monitor.
- **No card de Pending OTC, sem PDF na pasta o botão vira `Generate`**; com PDF, continua `Validate`.
  É a **mesma condição** que já riscava o botão (o `checou && !temPdf` do `loadDocs`), agora com um
  destino em vez de um aviso. ⚠️ **Só na etapa do OTC.** Em MO e FO, sem contrato o botão continua
  riscado: elas conferem o papel, não o produzem.
- **`/manual-confirmation/generate?keys=…` é a tradução que faltava.** A esteira conhece a LINHA
  (Trade ID, Produto, data da operação) e o New Deals conhece o GRUPO (contraparte × mercadoria ×
  família), que é a unidade do documento. O casamento é pelos **Trade IDs** — os mesmos que o card de
  Confirmations do New Deals Monitor já usa —, nunca por contraparte × mercadoria: seria um de-para
  por texto entre dois cadastros que normalizam nomes de jeitos diferentes.
- **Sem destino, 404 com a página que diz QUAL dos três motivos foi**
  (`confirmations/manual-generate-error.html`): produto sem tela de geração, linha sem Data da
  Operação, ou arquivo-dia sem a operação. Um 404 seco não distingue os três, e os três pedem ações
  diferentes.

**No editor sobrou UM botão.** O `🖨 Imprimir / Salvar PDF` saiu dos nove templates de confirmação: o
PDF é gravado no Electronic Inventory, e imprimir por fora produzia um documento que a esteira não
vê — um papel que existe para o cliente e não existe para o sistema.

E quando o editor foi aberto pelo Monitor (a rota manda **`mc_keys`** na URL), a tela que abre depois
de gravar é a validação da **ESTEIRA**, não o checklist do documento: é o mesmo ato — quem gerou está
com o papel na frente e assina pela mesa de OTC. Validando, a confirmação segue para MO/FO; fechando
sem validar, ela **continua em Pending OTC**, agora com o PDF na pasta, e o card volta a oferecer
`Validate`. Sem `mc_keys` nada muda (abre o checklist do documento), e é por isso que o único ponto
tocado nos nove arquivos é o `openValidate`.

> **O ciclo do DOCUMENTO continua fechando sozinho.** `New → Generated → Success` é acompanhado no
> card de Confirmations do New Deals Monitor, e lá **a etapa da esteira vence o status do
> documento** quando existe — `_conf_esteira_stages` traduz toda etapa depois do OTC para `Ok`. Ou
> seja: validar no Monitor fecha o card do New Deals sem ninguém marcar nada. Foi o que permitiu
> trocar a tela pós-gravação sem quebrar o outro relógio.

---

## §259 — Track Confirmations: rótulos em inglês, `Notional Amount CCY` e o filtro `blank`

**Os NOMES das colunas são os da planilha legada e não podem mudar** — eles são o esquema dos dois
DuckDB, e renomear um quebraria o banco de quem já o tem em disco. Quem traduz é o `COLUMN_LABELS`,
que por isso passou a ser a lista **COMPLETA** das colunas: coluna sem entrada apareceria na tela com
o nome do banco, e é isso que a completude pega.

`Data de vencimento` → **Settlement Date**, `Data Operação` → **Trade Date**, `Moeda` →
**Underlying Asset**, `Notional` → **Notional/Qty**, `Cliente` → **Counterparty**, `Aging
Confirmação` → **Aging**.

A tradução br/es fica no `COLTR` do template, e **não** em `data-lang`: o cabeçalho é montado em JS
depois do load, e o `I18nManager` traduz os `[data-lang]` UMA vez, no load. Nas LISTAS (edição em
massa, painel de colunas) vale o `labelFull` — os três `Time Stamp` compartilham o rótulo curto de
propósito, e só quando há empate o nome do banco entra, porque ele já diz a mesa. Antes o nome vinha
sempre entre parênteses, o que agora encheria a lista de `Trade Date (Data Operação)`.

**`Notional Amount CCY`** entra à direita de Notional/Qty: o código de 3 letras mais o notional, num
texto só (`USD 1500000`). ⚠️ **A coluna `Moeda` ao lado NÃO serve para isso** — ela é o ATIVO da
confirmação e em mercadoria guarda a commodity (`OLEO`, `PLATTS`), que não é moeda nenhuma. Era ela
que a planilha do BACC vinha mandando na coluna de moeda.

A moeda vem do campo que a carrega em CADA produto (`_MC_NOTIONAL_CCY_FIELD`), e não de uma cadeia de
fallback — um `first(...)` genérico pegaria o primeiro campo preenchido, que nem sempre é o que a
mesa chama de moeda do notional:

| Produto | Campo |
|---|---|
| NDF Comm · Opt Comm · **FXO** | `StrikeCurrency` |
| NDF Vanilla · Other Publisher · **FWD Start** | `QuantityCurrency` |

O número vai **CRU** na célula (a máscara é ortogonal e mora na tela): gravar `1,500,000.00` obrigaria
o relatório do BACC a desfazer a máscara para escrever um número no Excel. Quem reparte moeda e valor
é **uma** função — `manual_conf.split_notional_ccy` —, e a moeda só vale como código se tiver 3
letras: um valor solto na célula devolve moeda vazia e o texto inteiro como valor, em vez de comer o
primeiro dígito. A coluna é escrita no **mapeamento**, então vale para as linhas novas; as antigas
ficam em branco porque a moeda de mercadoria não existe em lugar nenhum da linha para ser derivada
depois.

**`blank` no filtro por coluna traz o que está VAZIO.** É o único jeito de procurar a ausência: o
campo casa por conteúdo, e "nada" não se digita. O termo vira a regex `^\s*$` com o **smart search
DESLIGADO** — ligado, o DataTables reescreve a expressão e ela deixa de casar a célula vazia. A
palavra só é reservada quando é a **única** coisa no campo, senão uma contraparte chamada "Blank
Trading" ficaria impossível de procurar; e o `title` do campo é onde ela se anuncia, porque num texto
livre ninguém adivinha que existe.

---

## §260 — A coluna E-mail Subject se escreve sozinha (e o recap que era do vizinho)

A coluna guarda o assunto do **recap interno** que está na pasta da confirmação, e quem sabe a
resposta é o arquivo — não quem digita. Quem varre a pasta é o `_mc_confirmation_docs`, então a
coluna se atualiza nos dois lugares que o chamam: o `/api/manual-confirmation/docs` (os chips de
e-mail dos cards do Monitor) e a **tela de validação**.

`_mc_email_subject` lê o assunto memorizado por **(caminho, mtime, tamanho)** — o caminho sozinho
manteria o assunto do e-mail SUBSTITUÍDO pela vida do processo. `set_email_subjects` grava **só o que
mudou**, num lote por chamada: sem o "só o que mudou", cada abertura do Monitor reescreveria a esteira
inteira (o upsert apaga e reinsere a linha nos dois bancos); sem o lote, cada chave releria os dois
DuckDB, e o Monitor manda até 200 itens de uma vez.

**A primeira versão pegava o PRIMEIRO recap da pasta e o carimbava em todas as operações do grupo.**
Duas coisas quebravam com isso, e nenhuma dava erro:

- pasta com **um recap por operação** (o padrão da mesa: `Internal Recap DBH-1AAA.msg` ao lado do PDF
  de cada trade) — a `DBH-1BBB` ficava com o e-mail da `DBH-1AAA`;
- operação **sem recap próprio** — o `_afunila` cai para a listagem inteira quando nada casa, e a
  pasta é cliente × dia × produto: a operação recebia o assunto do recap de OUTRA confirmação (OLEO e
  PLATTS do mesmo dia dividem a pasta).

O casamento passou a ser em **dois passos, e a ordem separa o certo do plausível**: (1) pelo Trade ID
no NOME do arquivo, que é exato; (2) se nenhum arquivo nomeia operação, o recap **ÚNICO** da pasta,
que é o do booking e vale para o grupo inteiro. Fora disso não se escreve nada e fica um INFO no log
— célula vazia pede o dado, célula errada aponta para um e-mail que não confirma aquele trade.

> Dois limites conhecidos: o arquivo só é reconhecido como recap se o NOME contém `internal` ou
> `recap` (`_MC_MAIL_TOKENS`), e a coluna só se preenche quando alguém OLHA a confirmação. Linha que
> já saiu da esteira (banco `ok`) não passa por nenhum dos dois gatilhos — o que deixou de importar
> para o relatório do BACC quando ele passou a excluir o `Ok` (§261).

---

## §261 — BACC EA Metrics: o card das operações manuais das 16:00

Card novo (`baccea`) que manda, **todo dia útil ANBIMA às 16:00 BRT**, um e-mail com as operações
manuais em anexo `.xlsx`. TO e CC persistidos (`bacc_ea_metrics_recipients.json`, no `control-panel/`
que não é versionado) e um Run manual. Assunto fixo — `Support to OTC Derivatives - EA Metrics` —,
sem data e sem contagem: ele é contrato com quem recebe, que monta regra de caixa de entrada em cima
dele.

Ele fica **empilhado** com o *Pending Confirmations Spreadsheet Metrics*, e os dois juntos preenchem
a altura do *Confirmations Escalation*, que divide a linha e é o card mais alto do painel. Com isso o
`height: 50%` que segurava o card de Pending (§253) deixou de ser necessário: a coluna virou
`flex-column` e os dois `.cp-reveal` (que já são `flex: 1`) repartem a altura sozinhos — o que se
divide é a SOBRA, porque num contêiner em coluna o `min-height: auto` do flex impede que qualquer um
encolha abaixo do próprio conteúdo.

A fonte é a **MESMA** `manual_conf.load_all()` do Track Confirmations, com **dois cortes**:

- **sem Data Callback**, e o teste é a CÉLULA em branco, não um status. O callback é a conferência
  por telefone com o cliente e é ele que fecha a operação manual do ponto de vista da métrica; a
  planilha é a lista do que ainda falta. A coluna vazia é exatamente o que a tela mostra — derivar de
  um Pending criaria uma segunda regra, que discordaria dela no primeiro caso de borda;
- **Pending diferente de `Ok`**, e este é o status, porque `Ok` é justamente o nome do fim da
  esteira. De quebra, isso deixa o anexo restrito ao banco `pending` — o mesmo conjunto que o Monitor
  mostra, e o único cujo E-mail Subject o app preenche sozinho (§260).

Ordem pelo **Aging do maior para o menor**, com chave numérica: o aging é gravado como TEXTO, e por
texto `'10'` viria antes de `'9'`. Vazio vai para o fim — linha sem idade não encabeça um relatório
de atraso.

**As doze colunas, e o notional ocupa três delas:**

| # | Coluna | De onde vem |
|---|---|---|
| 1–6 | Trade ID · Product · Trade Date · Legal Entity · Conterparty Name · Aging | a coluna de mesmo sentido da esteira |
| 7 | **Born Age** | sempre VAZIA (preenchida por quem consolida) |
| 8 | **Notional/Qty** | o número cru da coluna de mesmo nome do Track |
| 9 | **National Currency** | o CÓDIGO, repartido da `Notional Amount CCY` |
| 10 | **Notional Amount** | o VALOR, repartido da mesma coluna |
| 11 | **Comments** | o **E-mail Subject** — é por ele que o time acha a operação na caixa |
| 12 | LOB | — |

⚠️ **A grafia dos cabeçalhos é a que foi pedida, `Conterparty Name` e `National Currency`
inclusive**: quem lê a planilha do outro lado casa pelo nome da coluna, e "corrigir" o typo aqui
quebraria o casamento em silêncio. E `Born Age` fica no arquivo mesmo vazia, porque a **posição** das
colunas é o contrato — tirá-la deslocaria as demais.

- **O TIPO é declarado por coluna** (`text` / `num` / `money` / `date`), não adivinhado do conteúdo. A
  primeira versão escrevia como inteiro tudo que "parecia dígito" e errava dos dois lados: um
  notional com centavos (`250000.50`) não passava no teste e ia para o Excel como **TEXTO** — sem
  somar e sem ordenar —, e um Trade ID todo numérico viraria número, perdendo o zero à esquerda.
  `_bacc_num` aceita as duas escritas que convivem no banco (`1500000` e `1.500.000,00`).
- **`money` leva a máscara de milhar; `num` não** — o Aging em `12,00` dias não quer dizer nada. E o
  código da máscara é escrito na convenção **INVARIANTE** do formato de arquivo (`#,##0.00`, com `,`
  de milhar e `.` de decimal), sempre: quem desenha a célula é o Excel de quem abre, com o separador
  do idioma DELE, e num Excel pt-BR esse mesmo código sai `1.500.000,00`. ⚠️ Escrever `#.##0,00` — a
  máscara como ela se lê em português — produziria um código malformado, com o ponto lido como
  decimal, e o valor sairia errado sem erro nenhum. Valor que não parseia fica texto e **sem**
  máscara: máscara sobre texto não faz nada, mas prometeria um número.
- **A largura mede o que se VÊ.** `1500000` são 7 caracteres e a célula desenha `1.500.000,00`, que
  são 12 — sem isso a coluna nasce estreita e o Excel mostra `####`, que é a forma mais fácil de um
  relatório parecer quebrado sem estar. O auto-fit é contagem de caracteres com piso e teto (o
  assunto em `Comments` tem 120 e sozinho empurraria as outras onze para fora da tela); o openpyxl
  não tem auto-fit de verdade, porque quem mede o texto é o Excel na hora de desenhar.
- **Planilha vazia VAI assim mesmo** — um dia sem operação manual é ele próprio a métrica. O único
  motivo de não enviar é lista de TO em branco (`no_recipient`), que o card mostra em âmbar: é
  relatório que não saiu de casa.
- O corpo do e-mail **não repete a tabela**: ele nomeia o anexo e diz quantas linhas são, que é o que
  distingue "não havia nada hoje" de "o anexo veio truncado". Claim/release/status em disco seguem a
  mecânica do Deals Monitor (§207/§222).

---

## §262 — Support Center: a fila é da MESA, não da pessoa

Cada um via só os próprios chamados e o master via todos. Isso escondia o time de si mesmo: o colega
que abriu o mesmo pedido ontem não tinha como saber, e a mesa abria o chamado duas vezes.

A unidade da visibilidade passou a ser o **papel de quem abriu** — quem é do Back Office vê os
chamados abertos pelo Back Office, quem é do Middle vê os do Middle. O master continua vendo tudo.

**Ver não é poder.** Editar, comentar e apagar continuam sendo do REQUESTER (e do master), então o
chamado do colega abre em leitura — a tela já monta os controles a partir dos flags do servidor, e o
`same_role` novo é o que a separa de "meu". Alargar a escrita seria outra decisão.

- O papel fica **GRAVADO no ticket** (`requester_role`) e é o de quem abriu, não o que a pessoa tem
  hoje: sair do BO para o MO não leva os chamados antigos para a fila nova.
- O ticket **ANTERIOR** a essa coluna tem o papel resolvido no cadastro de usuários
  (`_tk_roles_by_sid`), numa consulta **por LOTE** e com cache: por ticket, a listagem abriria o
  DuckDB de usuários uma vez por linha da tela, e ele é conexão singleton atrás de um lock global
  (CLAUDE.md §4). Sem esse resgate, a fila inteira de antes sumiria da mesa que a abriu — e um chamado
  que some é pior do que um que aparece para gente demais.
- ⚠️ **Papel VAZIO não casa com nada.** Dois usuários sem papel no cadastro não são uma mesa, e
  tratá-los como uma abriria a fila de um para o outro. Ali vale a regra antiga: só o próprio.

> **A asserção do gradiente do e-mail, no `check_tickets.py`, vivia vermelha** e foi alinhada à regra
> que vale. Ela cobrava a imagem `cid:otc_gradient` do banner — abolida quando o cabeçalho virou cor
> sólida + gradiente CSS (o `<v:rect>` que o Outlook pintava fora da célula). Agora ela prende o
> contrário: bgcolor sólido, `linear-gradient` no style, e NENHUMA imagem ou VML. Teste que cobra a
> regra revogada é pior que teste faltando — ele treina o time a ignorar o vermelho.

---

## §263 — Três dados que nasciam errados: a entidade do FXO, o Strike do FWD Start e o distrato

**A confirmação de FXO chegava ao Track Confirmations sem Legal Entity.** Só as páginas genéricas de
NDF trazem o campo `LE` no deal; mercadoria já caía num `JPM` fixo, e o FXO ficava **em branco**
esperando que alguém cadastrasse a entidade linha a linha — só que a resposta é sempre a mesma: a
mesa booka a opção de câmbio no Banco J.P. Morgan. Ele entrou no `_MC_JPM_SOURCES`, e a razão social
sai do `le-spn` (`JPM` → `BANCO J.P MORGAN S.A`), nunca de um literal. ⚠️ A lista é a da **Legal
Entity**, e não a de LOB (`_COMMODITY_SOURCES`): a FXO é CEM e ainda assim é bookada no Banco, então
amarrar as duas perguntas na mesma resposta erraria uma das duas.

**O Strike do NDF FWD Start derrubava para Amend um deal já Success.** O que a B3 registra é o
**Strike Set Offset** — o spread sobre uma taxa que só se conhece no dia do fixing; o Strike da linha
é a projeção dessa taxa no momento do booking, e a Athena a recalcula a cada pull. A operação não
mudou, mudou o mercado, e sem isso **todo FWD Start já registrado voltava sozinho para a fila** e a
mesa reconferia um registro que continuava certo. A célula continua destacada (o campo entra em
`AmendChanged` como qualquer outro); o que não regride é o status. A lista é
`_ND_AMEND_COSMETIC_BY_PRODUCT`, **por produto** — o Strike é econômico em todos os outros —, e por
isso `_nd_api_amend` passou a receber o `product` de quem chama. Produto vazio ("não sei") vale só a
lista geral: o default é econômico, porque um campo esquecido virando Amend custa uma revisão e o
contrário custa uma operação registrada errada.

**`TERMO DE RESILICAO` entrou nos Confirmation Types.** A lista é uma só e tem quatro consumidores
(§217), então o tipo apareceu de uma vez no upload do Electronic Inventory, na pasta em que o
documento é gravado, no cadastro Produto × LOB da esteira e no dropdown do Track. ⚠️ **Sem acento, e
isso não é estilo**: `confirmation_type()` compara `upper_norm(produto)` com a tupla, e o
`upper_norm` normaliza em NFKD e descarta as marcas de combinação — um `TERMO DE RESILIÇÃO` cadastrado
com cedilha chegaria à comparação como `TERMO DE RESILICAO` e **nunca casaria consigo mesmo**: o tipo
não resolveria e a pasta não seria achada (`_product_folder` faz o mesmo lookup), sem erro nenhum. O
lado bom da mesma normalização é que quem digita "Termo de Resilição" com acento resolve para o
código certo. Tipo novo mexe em **três** listas, e as três têm teste: `CONFIRMATION_TYPES`,
`TYPE_FOLDER_LEGACY` (com tupla VAZIA quando o tipo nunca existiu sob outro nome — a entrada existe
para um tipo ausente não se confundir com um histórico esquecido) e `VALIDATION_SEED`, sem a qual ele
cairia no `DEFAULT_RULE` sem ninguém ter decidido nada.

**O Guia do Usuário estava contando o fluxo antigo de geração.** O item 3.8 mandava clicar em
*Confirmation* na barra do New Deals — botão que não existe mais — e o 3.11 descrevia o Monitor só
como tela de validação. Os dois foram reescritos com o ciclo que vale (Generate no card de Pending
OTC, um botão só no editor, a validação da esteira em seguida), junto com o 3.15, que ganhou o card
do BACC. O `.docx` foi regerado do `.md`, que é a fonte única.

---

## §264 — Other Products Summary: o net zero se DIZ, e o Trade Level agrupa por produto

Duas leituras que a mesa pediu, uma em cada tabela da página.

**A linha que NETA ZERO saía com Receive e Pay VAZIOS.** O teste em `_opssum_rows` era `if recv`, e
`0.0` é falso — então a operação cujos valores se anulam chegava à tela sem nenhum número nos dois
lados. ⚠️ **Célula vazia se lê como "não deu para calcular"**, e aqui o zero é o RESULTADO: a
liquidação existe e fecha em zero. A mesa não tinha como distinguir a linha que zerou da linha que
não conseguiu apurar — as duas apareciam iguais.

Passa a sair `0.00` no **Receive**, que é o lado que a `direction` já aponta (`total >= 0` →
`RECEIVE`, a mesma expressão logo acima). O **Pay continua vazio**: preencher os dois diria que a
mesma linha paga e recebe zero ao mesmo tempo, e a Direction ficaria desmentida pela própria linha.
A condição virou `if (recv or zerado)`, com `zerado = not recv and not pay` calculado antes — o
zero só vale quando os DOIS lados são zero, e não numa linha que só não tem o lado oposto.

⚠️ **O gêmeo do NDF Summary (`_ndfsum_collect`) NÃO mudou.** A regra foi pedida para o Other
Products, e as duas telas são lidas por gente diferente; igualá-las é outra decisão, tomada por
quem usa a de NDF. Mexer nas duas "por simetria" teria mudado um relatório que ninguém revisou.

**O Trade Level abria ordenado só por Counterparty**, e isso intercalava swap, termo e opção do
mesmo cliente na mesma vizinhança — a conferência é por produto, e ela ia e voltava na tabela.
Agora abre por **Product → LOB → Counterparty**, nessa precedência: o produto agrupa, a LOB separa
a mesa dentro dele e o cliente ordena a lista final.

Para isso o `initTable(id, dataCols, pageLen, orderCols)` da página passou a aceitar uma **LISTA**
de índices, mantendo o número simples para quem só quer uma coluna e o **omitido** para quem não
quer nenhuma — o Settlement Summary (`initTable('ops-summary-table', 9)`) continua abrindo na ordem
em que o servidor mandou as linhas, que é como sempre foi. A chamada do Trade Level é
`initTable('ops-trade-table', 10, 50, [7, 3, 4])`.

⚠️ **Os índices são posicionais**, então uma coluna inserida no meio do cabeçalho passa a ordenar
pela vizinha, em silêncio — a tabela ordena, só que pela coluna errada. O `check_ops_trade_swap.py`
já fixava a string da chamada; além de atualizá-la, ele agora amarra os três índices ao **cabeçalho
real** (`product` = 7, `lob` = 3, `counterparty` = 4, descontadas as três colunas de controle), o
que transforma o deslocamento em FAIL em vez de numa ordenação plausível.

---

## §265 — Save CETIP Files ganha o TO do BACC, com os arquivos recortados para o intragrupo

O card já mandava para **Sales Support** e **CEM Latam**. O BACC é o terceiro e-mail, e ele não
recebe os arquivos cheios: leva **DFLUXO swap, posição swap, posição OPC e posição TER** filtrados
para as operações **entre contas de casa** — `00041.00-7` (Lawton), `73760.00-9` (Banco) e
`85398.00-5` (Atacama).

⚠️ **O filtro é `and`, não `or`.** A linha só entra quando **PARTE e CONTRAPARTE** são as três
contas. Com um dos lados fora, aquilo é operação com CLIENTE — e ela entraria num anexo que se
chama intragrupo sem que ninguém tivesse como perceber, porque o nome do arquivo é o do original
(é por ele que o consumidor casa). Quem diz que é recorte é o corpo do e-mail e a contagem em cada
linha da tabela (*"— 12 of 480 line(s)"*).

O anexo leva o nome do original **mais `.txt` no fim** (`73760_260817_DPOSICAO-SWAP.CETIP21.txt`).
As extensões da CETIP — `.CETIP21`, `.OPC`, `.TER` — não são associadas a programa nenhum: o anexo
chega sem ícone, não abre com um duplo clique e é o tipo de arquivo que filtro de e-mail costuma
barrar. O `.txt` é **acrescentado, não substituído**: trocar `.OPC` por `.txt` apagaria justamente
a parte do nome que diz qual dos quatro é aquele. O conteúdo não muda — já era texto (latin-1 +
CRLF), byte a byte o original menos as linhas de fora. E o nome que a TABELA do e-mail mostra é o
do anexo, não o do arquivo salvo no share: a tabela e a lista de anexos ficam lado a lado na mesma
mensagem, e dois nomes para o mesmo arquivo fariam procurar um anexo que não existe.

Onde está cada conta em cada arquivo mora no `_CETIP_BEHAVIOUR['<tipo>']['bacc']`, junto do resto
do comportamento do tipo; a LISTA de arquivos continua no cadastro `cetip-files` do /mapping. Cada
tipo tem o seu par de colunas, e é aí que estão as três armadilhas que erram **em silêncio** — as
três presas por `check_cetip_bacc.py`:

- ⚠️ **`'parte (conta)'` é SUBSTRING de `'contraparte (conta)'`.** A resolução da coluna é por
  nome, tentando cada token contra todo o cabeçalho; sem o `avoid`, o lado da parte casa com a
  coluna da contraparte quando ela vem antes no arquivo. O filtro passa a comparar a MESMA coluna
  duas vezes — e aí toda linha satisfaz os dois lados, deixando passar operação de cliente.
- ⚠️ **A conta é comparada só por DÍGITOS, com `zfill(8)`.** O Lawton é `00041.00-7`; um exportador
  que trate a conta como número devolve `41007`, que sem o zfill não casa com nada. O anexo sairia
  **vazio**, parecendo "não teve intragrupo hoje".
- ⚠️ **Par de colunas que não resolve deixa o arquivo FORA do anexo** (marcado como *Not found* no
  e-mail e no log). Mandar o arquivo inteiro com o nome de um recorte é pior do que não mandar.

Os recortes são gravados numa pasta temporária, removida depois do envio: eles **não podem encostar
na pasta de liquidação**, que é o que o KPI lê.

Diferente dos outros dois destinos, o BACC **não tem endereço default** — lista vazia significa
"não envia", e o painel diz isso em vez de sumir com o e-mail sem explicação.

De quebra, o POST de destinatários virou **merge**. Ele substituía as listas pelo payload inteiro,
então, com uma terceira chave, um Run vindo de uma tela que não a conhecesse apagaria aquela lista
em silêncio.

---

## §266 — Quotes: PTAX, Equities e Commodities numa página só (e a saída para a internet é uma FILA)

Porte das três abas de busca do app de desktop `cotaçoes.py` (CustomTkinter) para o OTC Tracker,
em **Apps › Quotes**. Só a busca por período: DI, SOFR, IPCA, EURIBOR e as calculadoras ficaram de
fora. O trabalho de rede está em `apps/pages/quotes.py`; `routes.py` fica com sessão, cadastro e o
formato que a tabela consome.

**Uma página, dois comboboxes em cascata.** O de cima é o tipo (PTAX · Equities · Commodities) e o
de baixo **nasce desabilitado** — o cinza do `:disabled` é o que diz, sem texto, que ainda falta
escolher o tipo. As moedas da PTAX são fixas (`PTAX_CURRENCIES`): ⚠️ **isso não é de-para, é o
domínio do endpoint do BCB** — pedir uma moeda fora da lista devolve vazio, não erro. Equities e
Commodities saem do **Ativo Subjacente do Index B3** (`Subjacente.json`), separados pelo campo
`Classe` e só os `ACTIVE`: ativo cadastrado no Index B3 aparece aqui no mesmo dia, sem release e
sem um segundo cadastro. O combobox é um `<input list=…>` porque são centenas de códigos e um
`<select>` obrigaria a rolar a lista.

**O código do subjacente NÃO é o ticker de mercado**, e é aí que entra o /mapping. `AAPL34` é o BDR
na B3 e o Yahoo quer `AAPL34.SA`; `BRT_IPE` não é símbolo nenhum. Os dois cadastros novos —
**`quotes-equity`** (471 linhas) e **`quotes-commodity`** (70) — são `LABEL → SYMBOL`, e o `seed`
vai **vazio de propósito**: os arquivos são versionados, e repetir centenas de pares no `routes.py`
criaria uma segunda lista para divergir da primeira. Código sem símbolo cadastrado devolve **404
pedindo cadastro**, nunca tenta o código como se fosse ticker — a resposta seria um 404 obscuro da
fonte em vez de "falta cadastrar". A lista da tela mostra `AAPL34 → AAPL34.SA` justamente para
quem escolhe distinguir o que está cadastrado do que vai falhar.

**A autenticação é a mesma da Athena** (`athena_api.build_session`: Kerberos SSO, `trust_env=False`,
o User-Agent que faz o ADFS negociar) — foi o que se pediu, uma forma só de autenticar para todas as
APIs do app.

⚠️ **Mas o proxy volta, explícito, e é uma CADEIA — não um endereço.** O `build_session` desliga o
`trust_env` porque a Athena é host INTERNO e herdar o proxy corporativo dava `WinError 10061`
(CLAUDE.md §8). BCB e Yahoo são o oposto: são internet, e em boa parte da rede JPM a conexão só sai
pelo proxy. Só que o `proxy.jpmchase.net:10443` do app de desktop **não atende em toda máquina** —
na instância do time ele responde *connection refused*, que é o MESMO `WinError 10061` por outro
motivo (ali não há nada escutando). A porta que atende é a **9443**.

Por isso a saída é tentada **em ordem** e a primeira que responder fica memorizada no processo:

`QUOTES_PROXY` (padrão `http://proxy.jpmchase.net:9443`) → **proxy do sistema**
(`getproxies()`, que no Windows lê as Opções de Internet) → `_FALLBACK_PROXIES` (10443) →
**conexão direta**.

Quatro decisões que sustentam isso:

- o `trust_env` continua **desligado**: o proxy do sistema é **copiado** para a sessão, não
  herdado. Herdado, ele voltaria a valer também para a Athena — exatamente o que o `False` protege;
- erro de **rede** (`_RouteError`) tenta a próxima rota; erro **HTTP** vira `QuotesError` e para na
  hora, porque aí a rota funcionou e o problema é a fonte. **407, 502 e 504 são exceção**: vêm DO
  PROXY, contam como rota ruim — parar neles esconderia a saída que funciona;
- o timeout de **conexão** é curto (6 s, contra os 30 s de leitura). Ele é pago uma vez por rota
  morta, e com os 30 s a fila inteira faria a tela esperar um minuto e meio para dizer que não
  conectou;
- quando a rota memorizada morre junto com as outras, a memória é **esquecida** — senão a busca
  seguinte insistiria na que caiu antes de recomeçar pela ordem natural.

**A mensagem de erro cabe numa linha.** O despejo cru do urllib3 tem ~400 caracteres (URL, pool,
endereço do objeto) e era ele que aparecia no SweetAlert. `_short_error` traduz para o motivo
(*the proxy refused the connection*, *timed out*, *host not resolved*, *SSL failure*) e o erro final
nomeia **cada rota tentada**:

```
PTAX (BCB): could not reach the source (proxy http://proxy.jpmchase.net:9443: the proxy refused
the connection; proxy http://proxy.jpmchase.net:10443: the proxy refused the connection; direct
connection: timed out).
```

Quando alguma funciona, o log grava `[quotes] saída em uso: <rota>`. ⚠️ **Se a tela ainda mostrar o
despejo antigo do urllib3, a instância está servindo Python velho** — o reloader é desligado lá, o
template recarrega sozinho e o módulo não (CLAUDE.md §8). É preciso reiniciar o Flask/waitress.

**Sem `yfinance`.** O app de desktop usava `yf.download`, que arrastaria pandas-datareader e afins.
O que ele faz para OHLCV diário é uma chamada ao endpoint `chart` do Yahoo, que devolve JSON — feita
aqui com a MESMA sessão. Uma dependência a menos e um caminho de rede a menos para divergir.

Três detalhes de leitura das fontes, todos com teste em `check_quotes.py`:

- a PTAX traz **só o boletim de Fechamento**: o BCB publica abertura e intermediários, e sem o
  filtro o mesmo dia apareceria quatro vezes com valores diferentes. A data vai no endpoint em
  **`mm-dd-aaaa`**, entre aspas;
- o `period2` do Yahoo leva **um dia a mais**, porque o fim é EXCLUSIVO — sem isso o último dia do
  período pedido some da tabela (é o mesmo `+1` que o `yf.download` fazia);
- `None` da fonte vira célula **vazia**, nunca `0.00`: o Yahoo devolve `null` no dia sem pregão
  daquele papel, e um zero ali afirmaria um preço que não existiu.

A tela segue o padrão de tabela da casa (filtro por coluna montado **antes** do `.DataTable()` com
`orderCellsTop: true`, `autoWidth: true`, toolbar com `mb-3`, Export completo — Copy · CSV · Excel ·
Print · PDF —, `otcCellCopy` do `table-std.js`), o widget é `.qt-card` e **não `.card`** (§7), e os
19 rótulos nasceram em inglês nos três `translations/*.json`. Os campos da busca ficam **alinhados à
esquerda com largura própria**: o grid de 12 colunas esticava cada um até a borda da tela, e um
combobox de 500 px para um código de seis caracteres só afasta os campos uns dos outros.

---

## §267 — Quotes Commodities: uma linha por MERCADORIA, não por vencimento

O de-para de símbolo de commodity nasceu (§266) como código fechado: `BOK6 → ZLK26.CBT`,
uma linha por vencimento. São **70 linhas para 10 mercadorias** — e uma linha nova a cada
vencimento que a B3 abre, para sempre. Pior: o arquivo herdado do app de desktop já mostrava
o que isso vira com o tempo. Vinte e nove das 70 linhas estavam com um valor de enchimento
(`BUSHELS`, que não é ticker de nada) ou com o **mesmo** `ZSK25.CBT` repetido em dezoito
linhas de vencimentos diferentes — quem cadastra uma linha por mês acaba copiando a de cima.

As duas colunas passam a aceitar o padrão **`"MY"`**, que é a notação que o cadastro
`commodities-b3` já usa há muito tempo (§164): `"MY"` é onde entram a letra do mês e o ano,
`_` é um espaço literal. Uma linha vale para a mercadoria inteira:

```
   BO"MY"  →  ZL"MY".CBT          BOK6   →  ZLK26.CBT
   C_"MY"  →  ZC"MY".CBT          C K6   →  ZCK26.CBT
   CO"MY"  →  BZ"MY".NYM          COZ29  →  BZZ29.NYM
```

**17 linhas no lugar de 70, e a cobertura foi de 70 para 221** dos 904 subjacentes ativos da
classe COMMODITIES — porque o vencimento que ninguém tinha cadastrado agora resolve sozinho.

Quem expande é o **`quotes.symbol_lookup`**, e ele existe por duas assimetrias que fariam o
de-para literal viver para sempre:

- **o ANO tem larguras diferentes nos dois lados.** A B3 escreve um dígito (`BOK6`) ou dois
  (`COZ29`); o símbolo de mercado escreve sempre dois (`ZLK26`). O dígito único é resolvido na
  década corrente, virando para a próxima quando o ano cairia mais de um ano no passado —
  contrato futuro aponta para a frente, e `5` em 2026 é 2025 (o vencimento recém-liquidado),
  nunca 2015. A folga de um ano é de propósito: o vencimento que acabou de liquidar ainda é
  consultado;
- **o `"MY"` do símbolo fica no MEIO** (`ZL"MY".CBT`), porque o sufixo de bolsa vem depois do
  vencimento. Por isso o marcador é lido dos dois lados, e não só como prefixo.

Três regras que não dão erro nenhum se caírem:

- **o miolo casado TEM de ser mês+ano de contrato.** Sem essa exigência o prefixo de uma letra
  do milho (`C_"MY"`) casaria com `CCZ6` (cacau), `CLZ6` (WTI) e `CRDZ6`, devolvendo o preço da
  mercadoria errada **em silêncio** — que é o pior desfecho possível numa tela de cotação;
- **prefixo mais longo vence.** `CO"MY"` (Brent) tem de ganhar de `C_"MY"` em `COZ6`; sem a
  ordenação, quem responde pelo código seria a ordem em que as linhas estão no arquivo;
- **linha SEM `"MY"` continua literal, e vence o padrão.** É como se cadastra a exceção de um
  vencimento só, e é o que os sete contratos **contínuos** usam (`C 1` → `ZC=F`). Símbolo sem
  marcador também fica literal: a mercadoria inteira respondendo por um contínuo é cadastro
  válido, e aplicar mês/ano nele produziria um ticker que não existe.

O motor é **um só para os dois cadastros** — equities não têm vencimento e são todas literais,
então não há ramo por tipo. E `symbol_lookup` devolve uma **função**, não um dicionário: a linha
com `"MY"` é regra, não par, e só se resolve contra um código concreto. A tela chama o cadastro
uma vez e resolve os ~900 subjacentes do dia com ele; `symbol_for` é o atalho de uma consulta só.
`has_b3_marker` foi para o `otc_boxparse`, ao lado do `split_b3_pattern`, para o marcador ter um
dono só em vez de uma segunda expressão regular para envelhecer sozinha.

**Dois símbolos estavam errados e apareceram na migração.** `CO"MY".NYB` (Brent) responde 404 no
Yahoo: o contrato é `BZ"MY".NYM` — *Brent Crude Oil Last Day Financial* —, conferido na fonte.
E `DF"MY".NYB` continua **não confirmado**: `DFK26.NYB` e `DFH27.NYB` também são 404, e nenhuma
fonte pública liga o `DF` da B3 a um contrato da ICE. A linha ficou como estava, com a ressalva
escrita na coluna Notes — apagá-la esconderia a pergunta.

O registro do de-para inteiro (sufixos de bolsa do Yahoo conferidos na página oficial, códigos
de mês, as 17 linhas de commodity, as 471 de equity e as cinco pendências conhecidas) está em
`DE_PARA_TICKERS_COTACOES.md`, com o Word gerado pelo `scripts/build_sop_docx.py` como o SOP e o
Guia do Usuário. Testes novos na seção 2b do `check_quotes.py`.

---

## §268 — Save CETIP Files: o quarto destino é o BACC HUB EQT MO, e ele recebe a posição CHEIA

O card já mandava para Sales Support, CEM Latam e BACC (§265). O **BACC HUB EQT MO** é o quarto
e-mail: leva **`SWAP (Strategy)`, posição de NDF/Termo, de Opção, de SWAP e a Agenda de Prêmios**,
os cinco **inteiros** — sem recorte, sem filtro, sem releitura — anexados em `.txt`. É reconciliação
de posição, e é isso que separa este destino do BACC.

**BACC e BACC HUB são duas listas e dois e-mails de propósito.** São times do mesmo lado, mas o que
cada um pede é o oposto: o BACC quer só o intragrupo (`_cetip_bacc_copy`), o HUB quer a posição
completa. Um e-mail só com os dois conjuntos entregaria a cada lado um arquivo que ele não pediu —
e, pior, o recorte e o arquivo cheio saem do MESMO arquivo de origem, então os dois anexos teriam o
mesmo nome na mesma mensagem. **Três dos cinco arquivos do HUB estão também no BACC** (NDF/Termo,
Opção e SWAP), e é aí que isso deixa de ser teoria.

`_cetip_txt_copy` é `shutil.copy2`, e não um `open`/`write` como o recorte do BACC: **byte a byte**,
sem reencodar, sem tocar em fim de linha, sem chance de o latin-1 do arquivo virar outra coisa no
caminho. Um arquivo de reconciliação que difere do original em um byte é um arquivo que não
reconcilia. O `.txt` é acrescentado pela mesma razão do §267 (as extensões da CETIP não abrem com um
duplo clique, e trocá-las apagaria a parte do nome que diz qual arquivo é aquele), e a cópia vai
para um temporário porque o anexo não pode encostar na pasta de liquidação, que é o que o KPI lê.

Quatro coisas que não dão erro nenhum:

- **Arquivo que faltou no dia é DITO, não omitido.** Só o HUB tem `hub_skipped` para o arquivo
  ausente: um e-mail de reconciliação com três dos quatro anexos se parece exatamente com um e-mail
  completo, e a posição que falta é justamente a que ninguém vai conferir. Os outros destinos
  seguem pulando em silêncio, que é o comportamento que eles sempre tiveram.
- **Sem TO, a cópia nem é montada.** O `quer_hub` carrega o teste da lista, como o BACC já fazia —
  copiar quatro arquivos para um e-mail que não vai sair é trabalho para o disco e uma pasta
  temporária a mais. Lista vazia é desfecho legítimo e o painel diz, em cinza.
- **A coluna Type da tabela vai SEM contagem de linhas.** No BACC ela diz `— 12 of 480 line(s)`
  porque houve corte; escrever `480 of 480` aqui sugeriria que também houve um, e é a diferença
  entre os dois e-mails.
- **Comportamento sem cadastro é regra que nunca roda.** `_cetip_rules` une `_CETIP_BEHAVIOUR` ao
  cadastro `cetip-files` pela coluna TYPE: um tipo que existe só no código não vira anexo nenhum, em
  silêncio. Por isso o **`Strategy Position (MID DPOSICAOESTRATEGIA)`** entrou nos três lugares —
  `_CETIP_BEHAVIOUR`, `_CETIP_FILES_SEED` e o `cetip-files.json` versionado —, e o
  `check_cetip_bacc.py` confere que todo tipo com `attach_hub` tem linha nos dois últimos.

O arquivo de estratégia **já estava no cadastro do time**, como **`SWAP (Strategy)`** —
`CETIP21_YYMMDD_DPOSICAOESTRATEGIA_MID` → `CETIP21_YYMMDD_DPOSICAOESTRATEGIA_MID.txt`. A primeira
versão desta seção o inventou como `Strategy Position (MID DPOSICAOESTRATEGIA)`, deduzido do
`MID_DAGENTEACELERADOR`: um TYPE que não existe é uma regra que **nunca casa**, e o e-mail sairia
com três anexos para sempre. O DEST dele já termina em `.txt`, e é por isso que o nome do anexo
passou a sair do **`_cetip_txt_name`** — que acrescenta o sufixo **uma vez só**. `…_MID.txt.txt` é
um nome que ninguém escreveu de propósito, e o casamento do outro lado é pelo nome.

O resto do encanamento já era genérico: `_CETIP_RECIPIENT_KEYS` ganhou `hub_to` e com isso
`_load`/`_save`/`_cetip_merge_recipients` passaram a tratar as quatro listas sem mudança, e o JS do
card itera o mapa `KEYS`. O merge continua sendo merge e não substituição — uma tela antiga, que não
conhece a chave nova, apagaria aquela lista ao rodar.

---

## §269 — O TYPE do cadastro CETIP é DIGITADO, e a junção não pode depender do rótulo inteiro

Sintoma: o `.TER` recortado **sumiu do e-mail do intragrupo (BACC)**. Sem erro, sem linha
*Not found*, sem nada no painel — o arquivo continuava sendo salvo na pasta do dia, normalmente.

Causa: `_cetip_rules` une o cadastro `cetip-files` ao `_CETIP_BEHAVIOUR` pela coluna **TYPE**, e o
rótulo é TEXTO DIGITADO NA TELA. No código a posição de termo é `Term Position (DPOSICAO-TER)`; no
cadastro do time ela foi renomeada para **`NDF Position (DPOSICAO-TER)`** — e a renomeação está
*certa* do ponto de vista de quem opera, porque TER é termo e a mesa chama termo de NDF. Só que
`_CETIP_BEHAVIOUR.get(label)` de uma chave que não existe devolve `{}`, que é **exatamente o que
uma linha sem comportamento nenhum parece**. A linha perdeu de uma vez:

- o recorte do BACC (`attach_bacc`) — o sintoma que apareceu;
- o anexo do Sales Support (`attach_sales_support`);
- e o **JSON de categoria NDF**, que alimenta o Settlement Forecast — este é o que dói de verdade,
  porque não tem e-mail para ninguém notar que faltou.

O prefixo do rótulo é DESCRIÇÃO; o que identifica o arquivo é o que está **entre parênteses** (o
nome da CETIP). `_cetip_behaviour_for` casa pelo TYPE inteiro e, quando ele não bate, pelo
parêntese — e `_cetip_paren_key` é o que extrai. Os parênteses são únicos nas 16 entradas, e
`check_cetip_bacc.py` prova que continuam sendo: com dois iguais, o fallback entregaria o
comportamento de qualquer um dos dois, e **regra errada é pior do que regra nenhuma**.

Os dois desfechos agora **falam**, e em `log.warning` e não `log.info` porque na instância do time
o log de módulo só sai a partir de WARNING — aviso que ninguém lê é o mesmo que não avisar:

- rótulo resolvido pelo parêntese diz qual foi, e sugere renomear (ou não — o efeito é o mesmo);
- rótulo que não casa por nenhum dos dois diz a frase que faltava: *o arquivo é SALVO, mas não vira
  JSON nem é anexado a e-mail nenhum*.

O **`CGD (NET)`** entrou como `{}` — salvo na rotina e nada mais, que é o que ele tem de fazer, e é
o mesmo que dizem as outras entradas vazias do mapa. A entrada existe **por causa do aviso**: sem
ela o CGD o acenderia todo dia por estar certo, e um aviso que sempre aparece deixa de ser lido.
Vale para todo tipo novo: registrar `{}` é a forma de dizer "este é só salvo, de propósito".

A lição vale para todo cadastro que casa por rótulo: **a tela convida a reescrever o texto**, e uma
coluna que é chave de junção precisa ou de um identificador estável, ou de um fallback estrutural
como este, ou de um aviso. Aqui ficaram os dois últimos.

---

## §270 — Os arquivos de termo passam a se chamar NDF, e o nome antigo continua valendo

Fechando o §269: em vez de manter dois vocabulários, os rótulos do cadastro CETIP foram alinhados
com o da mesa. `Term Position (DPOSICAO-TER)` → **`NDF Position (DPOSICAO-TER)`** e
`Term Movement (DMOVIMENTO C21)` → **`NDF Movement (DMOVIMENTO C21)`**, no `_CETIP_BEHAVIOUR`, no
`_CETIP_FILES_SEED` e no `cetip-files.json`. TER é termo, a mesa chama termo de NDF, e o código
falar outra língua era a causa do §269.

Ficam **dois `NDF Position`** na lista — `(DPOSICAO C21)` e `(DPOSICAO-TER)` —, e está certo: o que
distingue os dois é o que está entre parênteses, que é justamente o que a junção passou a usar.

**O fallback do §269 não sai junto.** Ele não existia para aquele caso: existe porque uma coluna de
texto numa tela convida a ser reescrita, e o próximo rename não pode custar outra caçada. Na
prática, ele é o que faz o pull ser seguro — a instância que ainda tem `Term Position` gravado no
`cetip-files.json` continua com o comportamento inteiro, e o log diz que ela pode renomear. O teste
usa o nome HISTÓRICO de propósito: com os dois lados iguais, ele passaria sem testar nada.

**O `.TER` também entrou no BACC HUB EQT MO** (`attach_hub`), e com isso o HUB são cinco arquivos.
O TER é o caso que mostra por que os dois destinos são e-mails separados: ele vai **recortado** para
o BACC e **inteiro** para o HUB, com o mesmo nome de origem — num e-mail só, os dois anexos
brigariam pelo mesmo nome.

---

## §271 — A lista do combobox de Quotes: `datalist` nativo não aceita CSS

A lista de instrumentos saía com a **altura da página inteira**, mais larga que o campo e fora de
posição. Não era CSS errado: era um **`datalist` nativo**, e o popup dele é desenhado pelo
NAVEGADOR — nenhuma regra alcança, nem largura, nem altura, nem posição. Funcionava razoavelmente
com as 10 moedas da PTAX e ruía com os 904 contratos de commodity, que é onde ele foi visto.

A lista passou a ser um `<div>` nosso, dentro de um `.qt-combo` com `position: relative`:
`top: calc(100% + 4px)` e `width: 100%` sobre o wrapper de 190px (largura do campo por construção,
não por número repetido), `max-height: 260px` com `overflow-y: auto` e
`overscroll-behavior: contain` — rolar a lista até o fim não sai rolando a página atrás.

Quatro detalhes que não aparecem no console:

- **Só as 50 primeiras opções entram no DOM**, e o rodapé DIZ quantas ficaram de fora. Desenhar 904
  nós a cada tecla é o que trava a digitação; e uma lista que cala o corte parece a lista inteira —
  quem não achou o código concluiria que ele não existe.
- **`mousedown`, não `click`, no item da lista.** O `click` só chega depois do `blur`, e aí o menu
  já fechou sob o cursor: o item nunca seria escolhido. O `preventDefault` no `mousedown` é o que
  mantém o foco no campo.
- **Enter faz duas coisas.** Com um item destacado pelas setas, escolhe; sem destaque, busca — que é
  o que preserva o gesto do datalist (digitar o código inteiro e apertar Enter).
- **O menu não pode ter ancestral com `overflow: hidden`** — seria cortado. É mais um motivo para o
  widget da página ser um `<div>` próprio e não o `.card` do tema (§7), que recorta.

Vale para toda tela com muitos itens: `datalist` é ótimo para uma dezena de valores e não escala —
e o sintoma não é um erro, é uma tela feia que ninguém liga a uma escolha de elemento.

---

## §272 — Recon Pay/Rec: o Total Net neta DENTRO do produto, e quem diz o produto é o GDT Code

Sintoma: linhas de Lawton e Atacama caindo em *Pending* com a justificativa
*"Netting não tratado pelo OTC Tracker"* — a mesa carimbando à mão todo dia o que a recon não
conseguia casar.

Causa: o lado do CLIENTE da recon é o extrato da conta interna (`rlctahis.csv`), e o único campo
que diz de que produto é o lançamento é o **`nHistorico`**. O `_cli_rlctahis` classificava **tudo
como NDF**, menos três códigos de swap fixos no código. Como `_net_client` agrupa por
**(contraparte, LE, PRODUTO)**, o Total Net da Lawton somava opção de commodity + termo + NDF num
valor só — e do lado do JPM esses produtos estão separados, cada um com o seu registro. O valor
netado não batia com nada porque era a soma de coisas diferentes. Netar continua sendo netar; só
que **dentro do produto**.

O de-para virou cadastro: **`gdt-codes`** ("GDT Codes" no /mapping), com Description × Code ×
Product. Product é `select` de domínio FECHADO — um produto digitado errado não dá erro, cria um
grupo que não existe do outro lado e a linha vira uma pendência que ninguém explica.

**A regra da coluna Product tem duas metades, e as duas importam:**

- **preenchido** = o código liquida aquele produto **e a linha entra na recon**. É o que faz o
  `9396`/`4424` (estorno TSS-FX) passarem a ser contados, e o `9386`/`4414` (TSS-FX) deixarem de
  ser NDF para virarem FXO — eles já entravam, no balde errado;
- **em branco** = documentado e **ignorado**. São as duas transferências entre contas (`5347`,
  `0159`), que a mesa quer ver cadastradas para saber o que são e que não liquidam produto nenhum.

Três coisas que não dão erro nenhum:

- **`_SDCONTA_HIST_ALLOW` continua no código, como PISO.** O `4419` e o `AA` não estão no cadastro
  e seguem entrando pela regra histórica (SWAP se estiver no `_SDCONTA_HIST_SWAP`, senão NDF).
  Cadastro novo não pode apagar comportamento em silêncio;
- **o remap do `5347` na conta `0512026-0` vem ANTES do cadastro.** Aquele lançamento específico
  *é* um NDF e vira `9409`. Sem essa ordem, ele sairia junto com as outras transferências, que o
  cadastro manda ignorar;
- **o endpoint `/reconciliation-payrec/run` toca o cadastro antes de rodar**, só para materializar
  o seed — o motor lê o JSON direto (importar `routes` seria circular) e não tem como semear. Sem
  isso, na instância em que ninguém abriu a tela de /mapping o arquivo não existe, o de-para volta
  vazio e todo lançamento volta a ser NDF, sem erro nenhum. É o mesmo cuidado do §... da Recon FXO.

De quebra, as abas **Quotes — Equities/Commodities** do /mapping estavam sem chave de tradução
desde o §266 (o rótulo caía no inglês do `label` nos três idiomas); entraram junto com a do GDT.

---

## §273 — Manual Deals EA: duas rotinas, duas datas de referência, e o Deal que sai é o do VANILLA

Card novo no Control Panel. Ele manda para o **BACC HUB** (Cc na caixa da mesa) as operações
fechadas à mão, pedindo que o **EA automático não as considere** e que entrem na métrica à parte.
São duas rotinas no mesmo card, e a razão de serem duas é a **data de referência**:

| Rotina | Quando | Sobre o quê |
|---|---|---|
| NDF Other Publisher | todo dia útil às **20:00** BRT | as operações do PRÓPRIO dia (D+0), só **contraparte externa** |
| NDF FWD Start | **16:30** do dia da **Strike Set Date** | o re-booking em vanilla das que fixaram hoje |

Um disparo único teria de escolher uma das duas datas e erraria a outra: o Other Publisher olha o
dia que está acabando, o FWD Start olha operações bookadas semanas atrás que fixam hoje. Dois
horários, dois botões Run, um status por rotina.

⚠️ **O Deal do FWD Start é o do VANILLA, e essa é a armadilha da rotina.** No dia da fixação a mesa
cancela o FWD Start e faz um booking novo, já como vanilla, com **Deal ID novo** — e é esse o número
que o EA automático vê. Mandar o Deal do FWD Start original pediria para excluir uma operação que
já não existe, **deixando dentro do EA justamente a que existe**. O par é calculado no pull
(`_ndf_drop_fwdstart_rebooks`, §…) e agora **gravado** por `_mdea_rebook_record`, no arquivo do dia
da fixação: em nenhum outro momento os dois lados se veem juntos — o vanilla não entra em
arquivo-dia nenhum (é exatamente o que o pull evita) e o FWD Start mora no arquivo do dia em que foi
bookado. Antes o par só ia para o log.

Quatro coisas que não dão erro nenhum:

- **Other Publisher só leva contraparte EXTERNA**, e o teste é o `_pc_is_internal_counterparty` —
  o ECONOMIC GROUP do Reference Data, a mesma resposta que o Pending Confirmation já dá. NÃO é "o
  nome começa em BANCO": isso derrubaria Banco Safra, Bradesco e Santander, que são clientes
  (CLAUDE.md §7);
- **lista vazia NÃO envia**, e aqui é o contrário do BACC EA Metrics: lá a planilha vazia é ela
  própria a métrica, aqui o e-mail PEDE para excluir as operações abaixo — sem operação não há o
  que pedir, e uma tabela vazia faria quem recebe procurar o que não existe. `empty` é desfecho
  legítimo (cinza no card), distinto de `no_recipient` (âmbar: havia o que mandar e não havia para
  quem);
- **a Legal Entity sai do Reference Data** (`le-spn` → NAME), nunca de um literal — seria uma
  segunda grafia das mesmas entidades, para divergir na primeira correção. LE sem cadastro mostra a
  SIGLA, e não vazio: a coluna em branco esconderia de que entidade é a operação;
- **o slot é reservado em disco e DEVOLVIDO quando o envio falha.** A instância reinicia várias
  vezes ao dia; sem o claim o mesmo e-mail sairia a cada subida, e sem a devolução uma queda
  transitória do SMTP custaria o e-mail do dia. `empty` e `no_recipient` consomem o slot — nenhum
  dos dois melhora na retentativa.

O e-mail tem template próprio (`email-template-manual-deals-ea.html`), com a tabela **Deal Id ·
Legal Entity · Counterparty** no CORPO e não em anexo: ela é o conteúdo do pedido, e quem recebe
casa linha a linha pelo Deal Id e responde no próprio e-mail. Assunto
`Manual Deals Closed on dd/mm/yyyy — <rotina>`, com o nome da rotina no fim porque os dois e-mails
podem sair no mesmo dia e sem ele o segundo parece um reenvio do primeiro.

---

## §274 — Print Advice do Settlement Summary, e o BLOCKER do valor não identificado

Duas coisas, e a segunda é a que importa.

**O botão.** O Settlement Summary é a visão de liquidação do dia inteiro, e o aviso é o documento
que sai dela — mas gerar um produto de cada vez obrigava a abrir as TRÊS telas de Settlement Advice
e clicar em três botões na mesma data. Bastava esquecer uma para o cliente ficar sem o aviso daquele
produto, e nada na tela dizia. O **Print Advice** do Summary gera Swap + NDF Commodities + Opção de
uma vez; as telas continuam com o botão delas, para gerar um produto só.

Cada família reusa EXATAMENTE as funções que o botão da própria tela chama (montagem das linhas,
gerador do e-mail, escrita do status): a regra continua morando num lugar só, e o endpoint do
Summary é só o laço. Uma família que falhe não derruba as outras — o dia costuma ter as três, e
perder as duas boas por causa de uma fonte ilegível seria pior do que entregar o que dá.

⚠️ **O blocker.** As colunas de RESULTADO **são** o aviso: é por elas que o cliente paga ou recebe.
Quando a fonte não devolve o valor, a célula sai em branco — e um aviso de liquidação com o valor
em branco é **pior do que aviso nenhum**, porque não diz quanto e ainda assim parece completo, e
vai assinado. Foi visto no aviso de NDF Commodities, com linhas da Mondelez em branco no Resultado
Apurado e no Líquido.

`_opsadv_block_incomplete` tira do lote a contraparte cujo aviso tem valor faltando, nas QUATRO
entradas (as três telas e o Summary). Quatro decisões:

- **o corte é da CONTRAPARTE INTEIRA, e não da linha furada.** O aviso é netado por contraparte (e
  por commodity, para quem está no `ndfc-advice-split`): tirar só a linha mandaria um total que não
  fecha com as operações do cliente — o erro que ninguém percebe, porque o documento continua
  bonito;
- **as colunas exigidas são o resultado BRUTO e o LÍQUIDO** (`Resultado Apurado`/`Resultado
  Líquido` no termo e na opção; `Resultado Bruto`/`Valor Líquido` no swap). O **IR fica de fora de
  propósito**: ele é derivado, e zero é um valor legítimo;
- **coluna que não existe no cabeçalho não corta ninguém**, e avisa no log. Cortar pelo índice
  errado tiraria a contraparte errada, que é pior do que não cortar;
- **o bloqueio APARECE na tela**, no mesmo SweetAlert do resultado, dizendo contraparte, produto e
  quais colunas faltaram. Uma contraparte que some do lote sem dizer por quê é uma contraparte que
  ninguém vai cobrar. Sucesso COM bloqueio vira `warning`, não `success` — o verde faria a falta
  passar batida —, e zero avisos COM bloqueio diz "nenhum aviso foi gerado", não "nada a gerar
  para esta data", que são coisas diferentes.

O disclaimer viaja por dois caminhos porque a resposta tem dois formatos: até 2 rascunhos ela é
JSON (campo `blocked`); 3+ vêm num `.zip` binário, e aí o resumo vai no cabeçalho **`X-Blocked`**,
em **base64** — nome de contraparte tem acento e cabeçalho HTTP é latin-1. A frase mora no
`static/js/ops-advice-blocked.js`, um arquivo só para as quatro telas: quatro cópias divergiriam na
primeira correção de texto.

---

## §275 — OTM Settlements abre pela fila: Pending primeiro, depois a contraparte

A página é uma **fila de trabalho**, e abria ordenada por Cpty Name. Com o `Ok` misturado no meio,
a pendência sumia numa lista de duzentas linhas. Agora a ordem padrão é **Status → Cpty Name →
Trade Id**.

A ordenação do Status é **por rank, não alfabética**: `Pending` (0) → `New` (1) → `Ok` (2). O `New`
fica no meio porque é a linha que ainda não foi tocada; o `Ok` é o único estado que não pede nada e
fica sempre por último. Status desconhecido vai para o fim — ele não é uma pendência conhecida, e
encabeçar a lista com ele empurraria para baixo o que a mesa tem de fazer.

Duas coisas que fariam a ordem sair errada em silêncio:

- **ordenar pelo TEXTO do badge daria uma ordem por idioma** (`Pending`/`OK` em inglês,
  `Pendente`/`OK` em português), e pelo HTML ordenaria pela classe do CSS. Por isso o badge carrega
  o status CRU num **`data-st`**, e é dele que o rank sai;
- **a ordenação é ORTOGONAL ao display**: o `render` devolve o rank só para `type === 'sort'` /
  `'type'` e o badge para o resto. É o mesmo princípio dos números do padrão de tabela (CLAUDE.md
  §3) — o que se vê e o que ordena são perguntas diferentes.

---

## §276 — O assunto do aviso de liquidação leva CONTRAPARTE + CNPJ

Os três avisos (`Termo de Moeda`, `Swap` e o compartilhado `Termo de Commodities` / `Opção`)
terminavam o assunto no NOME da contraparte. O nome sozinho não identifica: o mesmo grupo tem
várias entidades com nomes quase iguais — "Mondelez Brasil Ltda" e "Mondelez Brasil Norte Nordeste
Ltda" chegam no mesmo dia, com avisos diferentes —, e quem arquiva do outro lado casa pelo
cadastro, que é **por CNPJ**.

    Liquidação de Operação de Derivativo (Swap) - 14/08/2026 - SUZANO SA 16.404.287/0001-55

`_subject_cpty(contraparte, taxid)` é o único lugar que monta esse pedaço, e os três assuntos
passam por ele — três formatações separadas divergiriam na primeira correção.

**O CNPJ só entra MASCARADO.** `_fmt_cnpj` devolve o texto CRU quando não são 14 dígitos (é o
comportamento dele em todo o resto do e-mail, onde o campo é rotulado); num ASSUNTO, terminar num
pedaço de número seria pior do que não ter número. A máscara é a prova de que o documento foi
reconhecido: sem ela, o assunto fica exatamente como sempre foi. É o caso do `CLIENTE B3` no teste,
que não tem TAX ID no Reference Data — e é por isso que o `check_swap_advice.py` cobre os dois
lados na mesma asserção.

---

## §277 — Manual Deals EA: o FWD Start que fixa no dia em que foi bookado não entra

Correção do §273. O e-mail de FWD Start sai na Strike Set Date com o Deal do re-booking em vanilla,
mas **o FWD Start cujo trade date É a própria Strike Set Date fica de fora**: ele não ficou
esperando o fixing, é um trade normal do dia — o EA automático o enxerga como qualquer outro, e
pedir para excluí-lo tiraria da métrica uma operação que não tem nada de manual.

⚠️ **A data comparada é a do FWD START ORIGINAL, nunca a do vanilla.** A do vanilla **é** a Strike
Set Date por construção do pareamento (`_ndf_rebook_key` casa "Trade Date do vanilla = Strike Set
Date do FWD Start"), então compará-la excluiria **todas** as linhas — o e-mail sairia sempre vazio,
e "sem operação não envia" faria a rotina parecer que está funcionando.

Para isso o par gravado passou a carregar a Trade Date do FWD Start
(`_ndf_fwdstart_cached_keys` devolve `{'deal', 'trade'}` em vez de só o Deal ID). Sem a data
gravada o lado seguro é **incluir**: uma operação a mais no pedido é revisada por quem recebe; uma
a menos fica no EA sem ninguém ver. A comparação é normalizada (`_mdea_date_key`) porque as duas
datas vêm de arquivos diferentes e já apareceram com zero à esquerda de um jeito e de outro.

**E o store do par saiu do cache do New Deals.** Ele nasceu em `NDF/FwdStartRebooks` e o New Deals
Monitor criou um card sozinho para ele, na seção *Others*, contando 3 "New": o Monitor varre aquela
árvore e trata **todo diretório novo como um produto** — que é justamente o que faz um produto novo
aparecer no painel sem código. O par de re-booking não é um produto, é estado da rotina, e passou a
morar em `cache/manual-deals-ea/fwdstart-rebooks/`. Quem já tiver a pasta antiga em disco pode
apagá-la; o card some junto.

---

## §278 — MT300: o e-mail das 19:30, e quem entra nele é cadastro

Card novo no Control Panel. Todo dia útil ANBIMA às **19:30**, um e-mail com as operações de **NDF
Vanilla do dia** cujas contrapartes estão no cadastro **`mt300`** — a mensagem MT300 é confirmada
por um grupo específico de clientes (Nestlé/Garoto/ABB), e é o cadastro que diz quem. Empresa nova
do grupo entra pela tela, sem release. TO — BACC, Cc na caixa da mesa.

O corpo é o do e-mail que o Confirmation Matching já mandava à mão, com as dez colunas da mensagem:
Instrument Type · Deal Name · End Counterparty Desc · Booking Date · Settlement Date · Other
Quantity · Other Quantity Units · Quantity Currency · Quantity · Rate. Assunto `MT300 - dd/mm/aaaa`.

Quatro coisas que não dão erro nenhum:

- **o casamento tenta TRÊS identificadores** — CNPJ (só dígitos), SPN e o nome por tokens — e basta
  UM casar. O CNPJ vem primeiro porque é o único que não muda de grafia: no e-mail real a Garoto
  chega como `CHOCOLATES GAROTO LTDA` e está cadastrada como `CHOCOLATES GAROTO SA`. Por nome ela
  não casaria, e a operação sumiria da mensagem sem ninguém ver;
- **o SINAL vem da DIREÇÃO**, não do arquivo: o notional é gravado sempre positivo e no MT300 a
  venda é negativa. Sem isso as duas pontas do mesmo trade sairiam idênticas;
- **`Other Quantity` é DERIVADO** (quantity × rate) e sai com **seis casas**. Ele não existe como
  campo, e arredondá-lo faria a conferência do outro lado acusar diferença de centavos — os valores
  do teste são os do e-mail real de 07/08/2026, conferidos dígito a dígito;
- **as datas da TABELA saem em `aaaa-mm-dd`** (o assunto é que leva `dd/mm/aaaa`): é o formato da
  mensagem SWIFT, e é por ele que o outro lado compara.

**Sem operação de ninguém da lista, o e-mail NÃO sai** — ele pede para casar o trade no DVP, e sem
trade não há o que casar. É a mesma regra do Manual Deals EA, e o oposto do BACC EA Metrics. `empty`
e `no_recipient` são desfechos distintos no card: o segundo é o pedido que não saiu de casa.

---

## §279 — Três tipos de confirmação novos, e a ordem do Ticket List

**Aditamento, Aditivo e Reratificação** entraram no Electronic Inventory como `AMENDMENT`,
`ADDENDUM` e `RERATIFICATION` — os documentos que ALTERAM uma confirmação já emitida, em vez de
confirmar uma operação nova. Em inglês, MAIÚSCULO e SEM ACENTO como os demais: o valor é **código**,
comparado por `upper_norm`, e não rótulo de tela.

Tipo novo mexe nas **três** listas (CLAUDE.md §6), e a falta de qualquer uma erra em silêncio:
`CONFIRMATION_TYPES` (a lista única, com quatro consumidores), `TYPE_FOLDER_LEGACY` com tupla
**vazia** — tipo ausente dali não se distingue de um cujo histórico alguém esqueceu de declarar — e
`VALIDATION_SEED`, sem a qual o tipo cairia no `DEFAULT_RULE` sem ninguém ter decidido nada. Os três
entram em OTC + MO, como o distrato; é SEED e não regra fixa, e a mesa corrige em um clique.

A pasta é o próprio código do tipo, então o padrão de gravação (nome do arquivo, não sobrescrever)
vale sem nenhuma mudança — é o que `TYPE_FOLDER` já garante para todos.

**O Ticket List passou a abrir pela FILA**: status primeiro (New → In Progress → Pending → Resolved
→ Closed) e, dentro do status, o **ID do mais antigo para o mais novo**. Abrindo por ID, o resolvido
de ontem ficava no meio do que está aberto hoje. O desempate por `seq` vale em **qualquer**
ordenação e sempre crescente, independente do `dir` da coluna: ele é a fila de atendimento, não uma
segunda ordenação que se inverte junto — e sem ele, chamados do mesmo status saíam na ordem em que o
servidor os devolveu, que muda a cada carga.

---

## §280 — MT300 depois do primeiro run: a coluna que não fechava, Position, Fixing Date e o cadastro que se autocompleta

Quatro ajustes pedidos ao ver o e-mail rodando, mais um defeito de layout que o antecedeu.

**O `<div>` da COLUNA do Manual Deals EA nunca era fechado** — sobra de quando o card foi movido
para uma linha própria. Com a coluna aberta, a coluna do MT300 entrava **aninhada** nela em vez de
ser irmã, e no grid do Bootstrap isso põe um card embaixo do outro: o MT300 aparecia abaixo, não à
direita. É a classe de defeito que não acusa nada — o HTML é válido, o card renderiza, só o lugar
está errado. O saldo de `<div>` da coluna fecha em 0, e os dois cards são irmãos com o Manual Deals
EA à esquerda e o MT300 à direita, embaixo do Confirmations Escalation.

Junto, o **`CP_GROUP` do JS de acesso por card não conhecia nenhum dos dois cards novos**. Ele só é
consultado para decidir se o CABEÇALHO da seção some quando nenhum card do grupo está visível: um
usuário com allowlist configurada que recebesse só o `mt300` veria o card sem o "Reporting" em cima
dele. Card novo entra ali no mesmo commit em que nasce.

**Position** — coluna à esquerda de Other Quantity, com a operação por extenso do lado da NOSSA
entidade: `JPM sells USD / buys BRL`. Quem confere lê a linha inteira sem cruzar o sinal do Quantity
com a direção de cabeça. Os dois verbos são **sempre opostos** (comprar uma moeda do par é vender a
outra, e escrevê-los de forma independente deixaria a linha dizer que a mesa comprou as duas), a
entidade sai da **LE do deal** e não de um literal — a mesma operação é bookada em entidades
diferentes, e a mensagem é confirmada por quem a bookou —, e faltando uma das moedas a célula fica
**vazia**: frase pela metade é pior do que célula em branco.

**Fixing Date** — do campo `Last Fixing Date` do New Deals. Numa média o que interessa é a **última**
fixação, quando a taxa fecha. A coluna vai entre Booking e Settlement, na ordem **cronológica** em
que a operação acontece, que é como quem confere lê a linha.

**Números e datas** seguem a regra da casa: `Quantity` e `Other Quantity` são dinheiro e saem em duas
casas; `Rate` é **taxa** e sai em oito, porque duas fariam dois strikes distintos aparecerem iguais
na mensagem. As datas em `dd/mm/aaaa`, como o resto do app — a mesa lê o e-mail ao lado das telas, e
uma segunda grafia só aqui obrigaria a traduzir de cabeça.

**O cadastro `mt300` se autocompleta do Reference Data.** Escolhido qualquer um dos três — nome, SPN
ou Tax ID — os outros dois se preenchem. É o mesmo cliente escrito de três jeitos, e digitar os três
à mão é criar a chance de o SPN de um cliente conviver com o nome de outro: a linha casaria por um
identificador e apareceria no e-mail com o outro. O tipo de coluna `refdata` do /mapping é genérico
(`/api/reference-data/counterparties`), então o próximo cadastro que precise disso não reescreve
nada.

---

## §281 — A opção de EQUITY acha o valor no OTM, e o Latam passa a ler o relatório mais novo

Dois defeitos que se encontram no mesmo lugar — o elo de equity —, e é por isso que estão na mesma
seção.

### A opção de ação ficava sem o valor interno

O Resultado Apurado da opção sai do OTM Settlements pelo **sufixo da `Combinação de operações`** da
Live Position de Opção. A opção de **ação** não preenche esse campo. Sem sufixo não havia valor, e o
efeito era duplo e silencioso: a linha aparecia no **Trade Level com a célula vazia** e **sumia do
Settlement Summary**, porque `_opssum_rows` descarta quem não tem o que liquidar (`_settle_n is
None`). Uma operação que liquida existindo numa tela e não na outra.

O plano B é o **mesmo elo que o swap de equity já usava** — Operations B3 (Título) → Latam Desk
Position (`CLEARING_TRD_ID_*`) → OTM Settlements (`270WI`/`270WC` + `Deal_Ref`) —, e ele responde por
**duas** coisas: o valor e o **SPN**. O SPN importa tanto quanto o número: é ele que troca o apelido
de conta da B3 (`SAFRABM`) pela razão social do cadastro, que é o nome pelo qual o Settlement Summary
agrupa.

Três detalhes que não dão erro nenhum:

- **o elo vem DEPOIS do sufixo, nunca antes.** Quando o sufixo existe, é um join direto e é o mais
  confiável dos dois; inverter a ordem faria o elo sobrescrever um casamento exato;
- **a chave é o Título em MAIÚSCULA**, a mesma forma que o swap usa (`key = titulo.upper()`). O
  índice é construído assim, e consultá-lo com outra grafia não casaria nada — sem erro;
- **o elo é resolvido UMA vez por linha** e serve o valor e o SPN. Procurá-lo duas vezes abriria
  espaço para os dois virem de trades diferentes.

### O Latam Desk Position ficava preso no relatório da manhã

Sintoma relatado: *"não traz as informações se atualizamos no dia; tive que deletar o JSON"*.

O import lia `sorted(...)[0]` — o **primeiro em ordem alfabética**, que é o mais **antigo**. O
relatório é reemitido no mesmo dia, e quando é, a pasta passa a ter **dois** arquivos: o consumido de
manhã só é apagado quando alguma linha entrou, e o novo chega ao lado. O import então regravava o
JSON do dia com a posição da manhã dizendo *"sucesso, N linhas"* — o pior tipo de falha, a que se
reporta como êxito.

O caminho do **Save Daily Settlement** era pior ainda: processava os dois na ordem crua do
`os.listdir`, então o vencedor dependia do sistema de arquivos e os dois caminhos podiam **discordar
sobre qual é o relatório do dia**.

`_latam_pick_source` é agora o seletor único dos dois: **mtime mais recente, nome só desempata**. Os
preteridos **ficam em disco** — apagar um arquivo que não foi lido destrói a única cópia — e voltam
na resposta em `ignored`, que o SweetAlert do import mostra nos três idiomas. Pasta com dois
relatórios é exatamente o estado que produziu o defeito, e ele não podia continuar invisível.

**Os dois assuntos são um só na prática:** o elo lê o **último** Latam disponível, então um Latam
parado na manhã deixa a opção de equity sem valor mesmo com o plano B no lugar. Quem investigar um
dos dois no futuro vai passar pelo outro.

De quebra, a docstring do `_latam_import` estava mentindo — dizia que a origem NÃO é apagada, e ela é
desde que `kept`.

### Um teste que apodreceu com o calendário

O `check_ops_summary` estava falhando **antes** dessas mudanças (confirmado rodando o HEAD anterior
num worktree). A seção 16 gravava o snapshot de Opção numa data **fixa**, mas
`_ops_src_latest_path` procura o arquivo nos **10 últimos dias úteis contados de hoje**: o fixture
saiu dessa janela sozinho quando o calendário andou, as três contagens viraram 0 e o teste passou a
acusar um defeito que não existia. Fixture de snapshot vai no **último dia útil**; o que precisa ser
fixo é a **data de vencimento** das linhas, que é o que o teste exercita.

## §282 — Moeda fraca: a inversão do strike é do PAR, não da coluna

"Em New Deals › Other Publisher NDF, a moeda está cadastrada como weak currency e o strike não está
sendo invertido." O BRL/CNH de 19/08/2026 saiu com **1,29567245** na coluna Rate, quando o cadastro
manda mostrar **0,77179965** — a API entrega o strike da moeda fraca como *moeda/BRL* (1,2956 CNH por
real) e a aplicação inteira trabalha com **R$/moeda**.

### Duas regras complementares, e o arquivo saía certo por compensação

A inversão existia em DOIS lugares, cada um olhando uma perna diferente:

| Onde | Condição | Efeito |
|---|---|---|
| `_ndf_deal_from_api` (importação) | `Other Quantity Units` é fraca | grava `Rate = 1/strike` |
| `_generic_ndf_ter_line` (arquivo TER) | `Quantity Currency` é fraca | escreve `1/Rate` arredondado |

As duas condições são **mutuamente exclusivas** enquanto uma das pernas for BRL, então o arquivo
Conecta sempre saiu com a Taxa a Termo certa — por compensação, não por acerto. O que ficava errado
era tudo que lê o `Rate` gravado, no arranjo em que o **notional está na moeda fraca**:

- a **coluna Rate da tela**, que é o que o usuário viu;
- o **contravalor do MT300** (`other = qty × rate`): 35.000.000 × 1,2956 dava 45,3 milhões onde a
  própria API declara `Other Quantity = 27.013.000` — que é 35.000.000 × 0,7718;
- a **taxa do arquivo Intrag**, cujo comentário já dizia "taxa (R$/moeda)" e dividia o notional por
  ela;
- o **Strike gravado do FWD Start**, que segue a convenção do Rate por construção.

### A pergunta certa é do par

`_ndf_weak_leg(qty_ccy, other_ccy)` devolve a moeda **fraca do par**, esteja ela em qualquer das duas
colunas — porque qual perna carrega o notional depende de como a mesa bookou, não da moeda. Com ele:

- a **importação** inverte uma vez, e o `Rate` gravado é sempre R$/moeda;
- o **arquivo TER** deixou de inverter: só arredonda pelas casas do cadastro (`INV DECIMALS`), que é
  a precisão com que o 1/taxa vai para a B3;
- o **preview do duplo clique** faz o mesmo, e perdeu o `_INV = { CNH: 4, MXN: 4, … }` fixo no
  template — as casas passam a sair do mesmo `BaseMoeda.json` que a página já busca para os códigos
  de moeda (com os literais antigos de fallback enquanto o fetch não volta).

**Par com as DUAS pernas fracas devolve `None`**: sem BRL não há convenção para apontar, e inverter
seria um chute.

### Duas consequências no deploy

1. **Arredondamento onde não havia.** No arranjo com o notional em BRL, o arquivo TER escrevia a taxa
   já invertida com 8 casas (a condição do `qty_ccy` não casava) e agora escreve com as 4/6 do
   cadastro. É a mesma precisão que o outro arranjo do mesmo par sempre teve — a coluna se chama
   *Inverse Decimals* justamente por isso.
2. **Os deals já gravados se corrigem no pull seguinte.** O `Rate` novo difere do gravado, então
   `_nd_api_amend` aplica o valor e devolve a linha para **Amend**, com a célula realçada. Vale para
   as operações do dia, que é o que a API devolve; operação de dia anterior fica com o valor cru no
   arquivo-dia e, se alguém regerar o Conecta dela, sai sem a inversão — o TER não compensa mais.

`check_weak_ccy_rate.py` cobre a regra nos dois arranjos (perna fraca achada nas duas posições, par
sem moeda fraca, par com as duas fracas, o TER sem a segunda inversão e o contravalor do MT300
fechando com o número da própria API).

### Mais um golden que apodreceu

O `check_fi_ter` falhava **antes** dessa mudança (confirmado no HEAD anterior, num worktree), nas
duas linhas de FWD Start sem janela de fixing: o golden legado ainda mandava a **Data de Fixing do
Ativo Subjacente**, que o §249 passou a Blank pelo cadastro. Golden de montagem de linha acompanha a
mudança de cadastro — quem não acompanha vira ruído vermelho que ninguém lê.

---

## §283 — Os schedulers de importação têm horário de mesa, e o `Sent` entrou na proteção do amend

Dois pedidos da mesa no mesmo dia, e os dois são sobre **trabalho que a aplicação fazia sozinha fora
de hora**.

### A janela 08:00–20:00 BRT

As três rotinas que trazem operação de fora rodavam **24 horas por dia**: a API de NDF a cada 20 min,
a de FXO de hora em hora e a varredura do box de commodities a cada 30 min. De madrugada cada tique
era uma ida à Athena — ou uma abertura do Outlook — para importar **zero** operação, porque a mesa
não booka nesse horário.

O **intervalo de cada uma continua sendo o dela**. O que a janela decide é se aquele tique faz
alguma coisa: `_import_window_open()` é consultada no corpo do `while`, logo depois do `sleep` e
**antes do `try`** — dentro do `try` o poll já teria acontecido, e a janela não teria economizado
nada. É um `continue`, não um `sleep` calculado até a abertura: o laço continua tiquetaqueando no
ritmo dele e a lógica cabe numa linha, sem um segundo relógio para manter sincronizado.

Três detalhes que não dão erro nenhum:

- **é horário de BRASÍLIA** (`_br_now`), como todo agendamento do app. A instância do time não roda
  necessariamente em BRT, e uma janela medida no relógio do servidor abriria e fecharia na hora
  errada, em silêncio — o mesmo defeito que parou o e-mail das 19h (§222);
- **as duas pontas são inclusivas.** "Das 8h às 20h" tem de deixar passar o tique das 20h em ponto;
  os intervalos não são alinhados com a hora cheia, e cortar em 19:59 perderia a última varredura do
  dia sem que ninguém pedisse;
- **cadastro malformado deixa a janela SEMPRE ABERTA**, com aviso no log. `_parse_hhmm_window`
  devolve `None` para o que não entende, e `_import_window_open` responde `True`. O padrão de um
  valor que não se lê é o comportamento anterior (importar): um `IMPORT_POLL_WINDOW` digitado errado
  no `.env` não pode desligar a importação do dia inteiro sem dizer nada.

A janela é `IMPORT_POLL_WINDOW` no `.env` (padrão `08:00-20:00`) e aparece no **log de subida** dos
três schedulers, ao lado do intervalo — é ali que se descobre por que o poll das 6h da manhã não
importou nada. Fim antes do começo (`20:00-08:00`) atravessa a meia-noite, em vez de nunca abrir.

### `Sent` entrou em `_ND_AMEND_KEEP_STATUS`

A regra do amend da API já poupava quem estava **`Success`**: só um dado **econômico** derruba uma
operação registrada de volta para a fila (§176), e trocar o Other Book ou passar a resolver o
accronym de uma perna interna destaca a célula e mantém o status.

O **`Sent` estava de fora**, e era um buraco por onde passava exatamente o que a regra existe para
evitar. `Sent` é o arquivo de registro **já enviado à B3**, e vem **antes** do `Success` — então a
janela desprotegida era justamente a da espera do retorno. Nela, um pull da Athena que trocasse um
book devolvia para `Amend` uma operação que a mesa acabou de mandar registrar: sem Checker, fora da
lista de enviadas, e reconferida à toa.

A lista virou a constante `_ND_AMEND_KEEP_STATUS = {'Success', 'Sent'}` e o resto da regra é o
mesmo, de propósito:

- mudança **econômica** (entidade, notional, strike, vencimento, direção…) derruba os dois do mesmo
  jeito. O default continua sendo econômico — um campo em que ninguém pensou virando `Amend` custa
  uma revisão, e o contrário custa uma operação registrada errada;
- a célula segue **destacada** (`AmendChanged`) em qualquer um dos casos: o que não regride é o
  status, não o aviso;
- os demais status (`New`, `Amend`, `Pending`, `Error`) continuam caindo para `Amend` sempre — quem
  ainda não saiu da mesa não tem o que preservar.

**O que NÃO mudou, e é uma decisão:** a varredura do box de commodities (`_box_persist_deals`) tem a
regra própria dela — qualquer campo diferente vira `Amend` e limpa o Checker. Ela está documentada
como sendo "a MESMA regra do caminho do navegador" (`otc-fileupload.js`), e mexer só no servidor
faria o mesmo recap e-mail amendar de um jeito pelo box scan e de outro pelo upload manual. Quem
quiser a proteção lá tem de mover as duas pontas juntas.

---

## §284 — `new-otc-deploy.bat`: a cópia virou lista branca, e `static\data` não sobe

O script que cria a próxima versão no share (`otc-source\vN` + o `link.txt` apontando para ela)
copiava a origem inteira com um `robocopy /E`. Passou a copiar por **lista branca**: duas variáveis
no topo — `DEPLOY_DIRS` (`pages static templates __pycache__`) e `DEPLOY_FILES` (`__init__.py`
`config.py` `db.sqlite3` `db.sqlite3.lock` `requirements.txt` `run.py`) — e nada fora delas.

**`static\data` fica de fora.** É o dado VIVO da instância: os mappings editados pela tela, o DuckDB
de usuários, os arquivos-dia do New Deals, os caches. Ele pertence à pasta que roda; uma versão
carregando a cópia da máquina de desenvolvimento sobrescreveria o que a mesa cadastrou.

Quatro coisas que não dão erro nenhum:

- **a exclusão é por CAMINHO COMPLETO** (`/XD "%ORIGIN_PATH%\static\data"`). Um `/XD data` casaria
  com QUALQUER pasta chamada `data` em qualquer nível — e há várias dentro de `static\plugins` —, e
  a versão subiria com pedaços de biblioteca faltando;
- **pasta ou arquivo novo na aplicação tem de entrar na lista**, senão a versão sobe sem ele. É o
  preço da lista branca, e é por isso que o script confere os itens contra a origem **antes** de
  copiar e **avisa** o que não achou. O aviso não derruba o deploy: o `db.sqlite3.lock` só existe
  com a aplicação rodando;
- **a cópia agora são várias chamadas de robocopy**, uma por pasta mais uma para os arquivos da
  raiz, e o código de saída é conferido em cada uma (`GEQ 8` = falha). Falhando no meio, a `vN`
  parcial fica no share e o `link.txt` **não** é atualizado — a mensagem de erro imprime o caminho a
  remover, porque a próxima corrida contaria a pasta parcial como versão existente e criaria a
  `vN+1` ao lado;
- o arquivo vai com **CRLF**, ao contrário dos outros dois `.bat` do repo: é um script com blocos
  `for`/`if` aninhados, e o `cmd` é sabidamente sensível a quebra de linha só-LF nesse formato.

---

## §285 — O Control Panel virou cinco seções, e a seção de cada card passou a ser o DOM

"Na página Control Panel já está ficando um pouco bagunçado com muitos cards." Eram **duas**
seções para treze cards — *File-Saving Routines* com dois e *Settlement Reporting* com os outros
**onze**, que na prática era um título só em cima de uma parede de cards sem relação entre si (a
importação de contatos ao lado da escalação de confirmações ao lado do MT300).

### As cinco seções, e o que caiu em cada uma

| Seção | Rótulo | Cards |
|---|---|---|
| **Intraday Routines** | Trading Day | Save CETIP Files · Deals Monitor — Pending Action · Confirmations Escalation |
| **Settlement Reporting** | Forecasts & Reports | Save Daily Settlement Files · Settlement Forecast |
| **Pending Confirmation Routines** | Outstanding Confirmations | Daily Metric · Pending Confirmations Spreadsheet Metrics · Weekly Escalation (CEM/EDG) · Signature Collection |
| **Economic Affirmation Routines** | Manual Confirmations | Manual Deals EA · BACC EA Metrics · MT300 |
| **Reference Data Routines** | Counterparties | Update Contacts |

**Não existe uma seção de salvamento de arquivo**, e isso é decisão da mesa: o que agrupa não é o
que a rotina FAZ (salvar arquivo), é *quando* ela acontece e sobre o que ela responde. O Save CETIP
Files roda ao longo do pregão, com os arquivos chegando, e por isso está na *Intraday* ao lado do
Deals Monitor e do Confirmations Escalation; o Save Daily Settlement Files alimenta a liquidação e
está com o Settlement Forecast. O MT300 saiu de *Settlement Reporting* para *Economic Affirmation*
pela mesma régua: ele reporta as operações do dia para o grupo casar, que é a família da afirmação.

A **coluna empilhada** mudou de seção junto: ela existe para dois cards curtos fecharem na altura do
card mais alto do painel, o Confirmations Escalation — hoje são o Save CETIP Files e o Deals Monitor,
na *Intraday*. A *Economic Affirmation* ficou com três cards de altura parecida e não empilha nada:
empilhar dois ali faria o terceiro esticar até a soma dos dois e virar meia tela de branco.

### O mapa card → grupo saiu do JS

O bloco *Per-user card access* escondia os cabeçalhos consultando um `CP_GROUP` **escrito à mão**
com os treze cards. Ele estava certo enquanto ninguém mexesse no layout — e este commit é
exatamente o que ele não sobreviveria: um card mudando de seção deixaria o cabeçalho antigo
sozinho na tela, ou faria o novo sumir com cards embaixo dele, sem erro nenhum.

Agora a seção sai do **DOM**: do cabeçalho (`data-cp-hdr`) anda-se até a `.row.cp-cards` seguinte, e
os cards dela são os cards da seção. Uma fonte de verdade, e card novo só precisa nascer dentro de
uma seção.

No mesmo bloco, dois defeitos que vinham junto:

- **escondia a COLUNA, não o card.** `card.closest('.col-12')` numa coluna empilhada (dois cards)
  levava junto o card que a pessoa PODE ver — quem tivesse só o BACC EA Metrics perdia os dois. Hoje
  esconde-se o `.cp-reveal` do card, e a coluna sai **depois**, se tiver ficado sem nada visível
  (senão ela reserva meia linha em branco);
- a região tinha um **`</div>` órfão** (o `page_content` fechava em −1). O navegador tolerava; a
  reconstrução da região o levou junto, e o bloco agora fecha em 0.

### Duas coisas que não dão erro nenhum

- **O `id` do card é o token do `Page_Access`** (`/control-panel#<id>`). Reagrupar é livre;
  renomear um `id` revoga o acesso de quem já o tinha, em silêncio. Nada foi renomeado aqui.
- **A ordem de `_CONTROL_PANEL_CARDS` é a da tela**, seção por seção — é ela que monta a checklist
  do `/page-access`, e uma ordem diferente da do painel faz quem concede o acesso procurar o card
  numa lista que não se parece com a página que ele vai liberar.

O `check_control_panel_sections.py` prende tudo isso: registro × template nos dois sentidos, seção
sem card e card sem seção, os três rótulos de cada seção nos **três** idiomas, a ordem do registro e
o JS sem o mapa à mão.

---

## §286 — File Interpreter: a NDF Vanilla estava ligada ao template, mas sem cadastro próprio

"Estou fazendo alterações no item de New Deals NDF Vanilla e não está refletindo na página; ele está
considerando o template de NDF Commodities."

As quatro páginas de NDF dividem o MESMO template do File Interface, o `termo-multiclasses` — o que
separa uma da outra é o **override por página** (`source_by_page`), e `_fi_field_src` cai no texto
COMUM do campo quando a página não tem override. O comum deste template carrega os campos de
mercadoria, e a Vanilla tinha **UM** override em 71 campos:

| seq | Campo | Vanilla resolvia para | Deveria ser |
|---|---|---|---|
| 17 | Código do Ativo Subjacente | `Page: Underlying Asset` | em branco |
| 19 | Data de fixing do Ativo Subjacente | `Page: Last Fixing Date` | em branco |
| 23 | Tipo de Cotação | `Mapping: commodities-b3` | em branco |
| 24 | Data de Fixing da Moeda | `Page: FXConvDate` | em branco |
| 38 | Valor / Percentual Negociado | `Page: Strike Set Offset` (FWD Start) | `Calculated` |
| 30/31 | Cotação Taxa de Câmbio / Paridade | em branco | `1` / `3` |

A página **aparecia** ligada na tela (o `linked_pages` sempre teve a Vanilla, com as 25 colunas
dela), e é por isso que a falha era muda: editar um campo *sem* override não mudava nada visível,
porque o que a tela mostra é o comum — e o comum é de outro produto.

O cadastro da Vanilla passou a ser o do **Other Publisher**, copiado campo a campo: é o mesmo
produto (NDF de moeda), e as duas páginas têm a **mesma lista de 25 colunas**, então todo
`Page: <coluna>` de lá é válido aqui. Hoje o `page-spec` das duas é idêntico, e a Vanilla difere do
cadastro de mercadoria em 25 campos.

**O que este item NÃO resolve:** os botões *Send to Conecta* da página de NDF Vanilla chamam
`/api/new-deals/vanilla/send-conecta`, e o endpoint genérico recusa esse produto
(`send-conecta not available for this product`, HTTP 404) — só `fwd-start` e `other-publishers`
passam. O cadastro da Vanilla alimenta hoje só o **preview de duplo clique**; abrir a geração do
arquivo é outra decisão, porque é registro na B3.

---

## §287 — B3 Omnibus Accounts → **B3 Accounts**: o cadastro que também diz quem é o Participante

O cadastro `b3-omnibus-account` tinha uma coluna (`ACCOUNT`) e uma regra implícita: **estar na
tabela era a resposta**. Ele listava só a conta guarda-chuva `73760.10-2`, e `_b3_is_omnibus`
respondia `True` para qualquer linha cadastrada.

Agora ele é a lista das **contas B3 de cada entidade nossa** — a própria e as de cliente —, com as
sete linhas do documento da B3 e as colunas em inglês:

| LE | SIMPLIFIED NAME | ACCOUNT | ACCOUNT TYPE |
|---|---|---|---|
| MGT | MORGANBC | 04880.00-6 | OWN |
| MGT | MORGANBC | 04880.10-9 | CLIENT 1 |
| JPM | JPMORGANBM | 73760.00-9 | OWN |
| JPM | JPMORGANBM | 73760.10-2 | CLIENT 1 |
| JPM | JPMORGANBM | 73760.20-5 | CLIENT 2 |
| LAWTON | INTRAGLAWTONFDO | 00041.00-7 | OWN |
| ATACAMA | INTRAGATACAMAFDO | 85398.00-5 | OWN |

### O guarda-chuva passou a ser o TIPO, e isso não é detalhe

Com a conta **PRÓPRIA** dentro da mesma tabela, "estar cadastrada" deixou de poder ser a resposta:
a posição da casa passaria a procurar cliente pelo CNPJ onde não há cliente nenhum. `_b3_is_omnibus`
responde pelo `ACCOUNT TYPE` — só **CLIENT 1** e **CLIENT 2**. A comparação da conta continua sendo
**só de dígitos** (§197): ela aparece ora `73760.10-2`, ora `7376010 2`.

O tipo é um **`select`** de propósito. Digitado à mão, um `Cliente1` não casaria com nada e a linha
viraria conta própria em silêncio — o aviso de liquidação sairia endereçado ao titular do omnibus,
com nome e valores preenchidos, parecendo certo. E `_b3_account_type` é **cego a caixa e acento**,
aceitando as grafias em português (`PRÓPRIA`, `CLIENTE 1`): a tabela nasceu assim e é assim que a
mesa a lê no documento da B3.

O `upgrade` traz o formato antigo, e a linha sem colunas novas vira **CLIENT 1** — na tabela antiga
estar nela *era* ser guarda-chuva, e lê-la como PRÓPRIA revogaria a regra do §197 sem erro nenhum.
Já a linha que **tem** as colunas novas e o tipo em branco fica em branco: ali o vazio é escolha.

### O Participante do header do TER saiu do código

O campo 4 do bloco `header` (X(20), "Nome Simplificado do Emissor") vinha de um dicionário fixo,
`_TER_PARTICIPANT_NAME`, e a MESMA resposta estava escrita de novo no `source_note` do File
Interpreter — dois lugares para divergirem. Hoje o campo é **`Source = Mapping` → `b3-accounts`**
nas quatro páginas de NDF, e `_ter_file_header(le, …)` resolve o Nome Simplificado pela **LE da
visão**. A conta PRÓPRIA vence no lookup (é a da entidade), mas qualquer linha da LE serve: o nome
é da entidade, não da conta.

O que sobrou fixo é só a tradução de vocabulário, `_TER_BUCKET_LE`: o gerador fala em **balde**
(`BANCO`, que é como a mesa chama o Banco J.P. Morgan nos arquivos da CETIP) e o cadastro fala em
**LE** (`JPM`, o mesmo token do `le-accronym`).

Três coisas que não dão erro nenhum:

- **o motor completa com espaços até os 20 caracteres** (`_fi_build_line` já fazia isso para todo
  valor de gerador, e nunca trunca nem reformata). Um `MORGANBC` sem preenchimento deslocaria a
  data e a versão de layout, e o arquivo chegaria à B3 com tudo depois da posição 30 fora do lugar;
- **LE sem Nome Simplificado levanta `ValueError` dizendo qual entidade falta** e para onde ir, em
  vez de montar o header com o campo em branco. Os dois endpoints de send-conecta passaram a
  devolver a **mensagem da exceção** no 500 — antes devolviam sempre o `_TER_FI_ERROR` genérico
  ("template missing"), que aqui apontaria para o lugar errado;
- o header continua **byte a byte** o de sempre, e é o golden do `check_fi_ter.py` que prova.

`check_b3_accounts.py` prende o cadastro inteiro: as sete contas, o tipo cego a acento, o
guarda-chuva pelo TIPO, o Participante pela LE, o header de 43 caracteres com o campo nas posições
11-30, o erro da LE ausente e o `upgrade`.

**Fora de escopo, e continua no código:** as CONTAS que o registro TER escreve nos campos Conta
Participante / Conta Contraparte (`04880109`, `73760102`, `00041007`…) seguem calculadas no
`routes.py`, e o `_CETIP_BACC_ACCOUNTS` e os mapas conta → entidade do Save CETIP Files também.
Elas agora existem no cadastro e poderiam sair dele — é a mesma tabela respondendo a mais uma
pergunta —, mas mexer nisso é mexer no arquivo de registro da B3, e isso é decisão da mesa.

---

## §288 — Holidays Calendar: o calendário virou cadastro, e nasce de uma planilha

"Preciso cadastrar mais um calendário no Holidays Calendar."

A lista de calendários estava escrita à mão em **CINCO** lugares: o
`_HOLIDAY_FILE_MAP` do `routes.py`, o `CALENDAR_CONFIG` e o `HC_CAL_COLORS` do
`apps-holidays-calendar.js`, as pills da barra lateral e o `<select>` do modal. Nenhum deles pode
conhecer um calendário criado pela tela — e o que aconteceria sem erro nenhum é o calendário novo
não aparecer em lugar algum, com o `/api/holidays/save` respondendo *"Unknown calendar"* para um
nome que a própria página teria acabado de mostrar.

Agora a lista é **dado**: `apps/static/data/holiday-calendars.json`, semeado com os onze de sempre
(arquivo, classes e cor **idênticos** aos que estavam fixos, para o comportamento ser o mesmo até
alguém cadastrar o décimo segundo) e cacheado por mtime, como os mappings.

- `GET /api/holidays/calendars` devolve o registro, e a página monta **tudo** dele: as pills, as
  opções do `<select>`, o mapa de cores do popup do feriado e o CSS.
- O JS mantém `HC_CAL_FALLBACK` — os mesmos onze — para o fetch que falha. `check_holiday_calendars.py`
  compara seed × fallback **campo a campo**: divergindo, o fallback mostra uma tela que não é a de
  ninguém.
- `POST /api/holidays/calendars` (multipart `name` + `file`) cria o calendário a partir da planilha.

### A planilha

Uma aba, três colunas — **Holiday** (A), **Description** (B) e **Holiday Type** (C) —, e só as duas
primeiras viram feriado. O cabeçalho é descartado por **não ser data**, nunca por posição: pular
`rows[1:]` cegamente jogaria fora o primeiro feriado de uma planilha exportada sem cabeçalho, e o
mesmo teste já descarta a linha em branco do fim e o rodapé de total. A data chega das **duas**
formas que o Excel produz — `datetime` quando a célula é data de verdade e texto `yyyy-mm-dd`
quando a coluna foi salva como texto (com ou sem hora junto); lendo só uma delas, metade das
planilhas voltaria vazia. Linha sem descrição e data repetida saem fora.

Planilha da qual não sai feriado nenhum é **recusada** dizendo o que se esperava ler, em vez de
criar um calendário vazio — que é um calendário que ninguém vê e que ninguém entende por que não
aparece.

### A cor

Sorteada de uma **paleta** (`_HOLIDAY_CAL_PALETTE`), não gerada por acaso: um `hsl` aleatório sai
com saturação e luminosidade fora do padrão da tela e, mais cedo ou mais tarde, ilegível sobre o
fundo `rgba(cor, .15)` que a pill usa. O sorteio evita as cores **já em uso** enquanto houver alguma
livre — duas pills da mesma cor são dois calendários que se leem como um.

**O CSS do calendário novo nasce no navegador** (`hcInjectCalendarCss`), a partir da cor do
registro: as MESMAS cinco regras que os onze têm escritas no `<style>` da página (pill, borda do
evento, ponto e link da list view, e a cor do pill do dayGrid). CSS de calendário criado hoje não
teria como estar escrito no arquivo. A função só gera para as classes `hc-cal-<slug>` — built-in
tem a sua e não é tocado.

### Três coisas que não dão erro nenhum

- **o `slug` vira caminho em disco E classe de CSS**, então só aceita `[a-z0-9_-]`: é ele que entra
  num `os.path.join`, e `../../etc/passwd` como nome de calendário precisa sair `etc_passwd`;
- **a checagem de duplicidade é refeita DENTRO do `_cache_lock`**, junto com a gravação: dois uploads
  simultâneos do mesmo nome passariam os dois pelo teste feito do lado de fora, e o segundo apagaria
  o primeiro. Arquivo que já existe sem linha no registro também é recusado — sobrescrever apagaria
  uma agenda que alguém pode estar consumindo pelo FX holiday schedule;
- **`holiday-calendars.json` entrou no `_SYSTEM_FILES`** do `/api/fx-holiday-schedules`. Ele mora na
  mesma pasta e **não** é uma agenda de feriados; sem a linha, apareceria como opção de schedule.

O registro está no **`.gitignore`**: o app o semeia na primeira leitura, então versioná-lo não
acrescenta nada e traria conflito de merge toda vez que alguém criasse um calendário pela tela — que
é justamente o que reescreve o arquivo.

O aviso do sino ganhou o rótulo `Holidays Calendar` nos **três** mapas de destino (§246).

**Anotado de passagem:** dos onze calendários, só `anbima.json` e `sofr.json` existem no repositório.
Os outros nove (bursa, cby_ags, euribor, iceags, ipe, lme, nymex, platts_asia, platts_europe)
aparecem na barra lateral e não têm arquivo — o JS avisa no console e segue. Eles agora podem ser
preenchidos pelo próprio "Create New Calendar", desde que o nome do arquivo bata (o slug de `LME` é
`lme`, e o endpoint recusa porque a linha do registro já existe); o caminho hoje é cadastrar o
feriado avulso pelo modal, que grava no arquivo certo.

---

## §289 — Operations B3: o topo dos `th` ficava comido

A barra de ferramentas já estava com `mb-3` (§233), e ainda assim o cabeçalho da tabela nascia
colado nos botões. O respiro passou a morar no **container da tabela**
(`#operations-b3-page .table-responsive { padding-top: .6rem }`), e não numa margem do irmão de
cima: o DataTables desenha a própria caixa colada no elemento anterior e come a margem de quem vem
antes, então `mb-*` na barra é uma medida que a tela não tem. Os `th` também ganharam 2 px a mais em
cima (`padding: 10px 12px 8px`).

---

## §290 — Index B3 Results e Reference Data: os botões de ação fora do padrão

"Os formatos dos botões de action na página B3 Index Results não estão no padrão definido."

O CSS das duas páginas **diz** que segue a spec `.ops-row-act` — o comentário está lá, o
`border-radius:10px !important` está lá. O que estava errado é mais fino, e nenhuma das três falhas
aparece no console:

| | Estava | Spec |
|---|---|---|
| Ícone | **13 px** | 1rem (16 px) |
| Tamanho travado | só a largura | os dois eixos |
| Tooltip (Index B3) | `title` nativo do navegador | balão colorido do Bootstrap |

### O ícone de 13 px

O markup trazia `<i class="ti ti-check fs-13">`, e `.fs-13` é uma classe do **tema** declarada com
`font-size: 13px !important`. A regra da página (`.btn-act i { font-size: 1rem }`) tem
especificidade maior, mas `!important` não se resolve por especificidade — ela perdia. Os ícones
saíam com **13 px onde o app inteiro usa 16**, e era essa a diferença que fazia esses botões
parecerem de outra tela: o quadrado tem o tamanho certo e o desenho dentro dele é menor.

A classe saiu do markup; a regra da página virou `.btn-act > i { font-size: 1rem !important }` como
cinto de segurança, porque quem copiar um botão de outra página traz o `fs-13` junto.

### O travamento em um eixo só

`min-width`/`max-width` sem `min-height`/`max-height` — é meia trava. Basta uma regra de tema com
`min-height` em `.btn` para um botão ficar mais alto que o vizinho, e **32×34 não é mais um quadrado
arredondado**. Entrou também o `box-sizing: border-box`: sem ele a borda do `.btn` soma por fora dos
32 px.

### O tooltip que não existia

O Index B3 Results **não inicializava tooltip nenhum**. Os botões traziam `title`, que é o balão
cinza do navegador (com um segundo de atraso), e o `data-bs-toggle="tooltip"` do botão *Add Row*
não fazia absolutamente nada — a página nunca chamou `new bootstrap.Tooltip`.

A criação é **delegada, no primeiro hover**, e não num laço no load: os `<td>` são reescritos a cada
redraw do DataTables, então instanciar uma vez pegaria só as linhas da primeira página — paginar,
ordenar ou filtrar devolveria botões mudos. Delegado, cobre os **quatro** DataTables da tela sem um
hook por tabela. O `.show()` na criação é necessário porque o `mouseenter` que mostraria o balão é
justamente o que acabou de disparar. E há o `hide()` no clique: sem ele, o botão que some da tela
(Delete, ou a linha redesenhada depois do Confirm) deixa o balão preso.

### Junto

- **Reference Data tinha as duas primeiras falhas idênticas** — mesma classe `.btn-act`, mesmo
  `fs-13`, mesma trava pela metade. É a página irmã do Index B3 Results (a varredura de 2026-08-07
  alinhou as duas), e corrigir uma só deixaria as duas telas que se comparam lado a lado ainda
  diferentes. Os tooltips coloridos ela já tinha.
- Os **quatro rodapés de modal** do Index B3 Results estavam com **Cancel em `danger`** — que na
  tabela ao lado quer dizer *Delete*. Foram para o par da spec: Save `ti-device-floppy`/success +
  Cancel `ti-x`/**secondary**, os dois como squircle e com tooltip colorido.
- `.edit-actions-wrap` estava declarada **duas vezes** no mesmo `<style>`; a segunda só acrescentava
  o `justify-content`, e a primeira ficava como ruído contraditório. O wrapper do markup passou a
  ser o padrão da casa (`d-flex justify-content-center gap-1`).
- Os botões ganharam o feedback de hover/active do padrão (`translateY(-1px)` + sombra, `scale(.97)`
  no clique).

`check_row_action_buttons.py` prende a spec nas duas páginas: os seis travamentos de geometria, o
ícone em 1rem **e** a ausência do `fs-13` no markup, a ordem e as cores por função, o tooltip
colorido com o CSS presente na página, a delegação do Index B3 Results e o par Save/Cancel dos
modais.

---

## §291 — Live Position: a coluna de CPF/CNPJ da contraparte mostra o NOME

Nas três Live Position — NDF (`CPF/CNPJ da Contraparte`), Option e Swap Characteristics
(`CPF/CNPJ Cliente Contraparte`) — a coluna passou a resolver o nome da contraparte no
`RefData.json`, em vez de imprimir o número.

Três regras, e as três erram em silêncio se caírem:

- **vazio continua vazio** — célula em branco não vira nome de ninguém nem documento de nada;
- **documento SEM cadastro devolve o número mascarado**, e não branco: o número é o único dado que
  a linha tem sobre a contraparte, e apagá-lo esconderia justamente quem falta cadastrar. A coluna
  misturada é o que denuncia a lacuna;
- **os dois lados normalizam o zero à esquerda** (`_lp_taxid_key`). O RefData guarda mascarado
  (`00.514.820/0001-00`) e a posição da B3 guarda só números, às vezes sem o zero da frente —
  comparar sem normalizar casa silenciosamente nada, a mesma armadilha do §197. **158 dos 553**
  cadastros do RefData começam com zero: seria mais de um quarto da base saindo como número.

A coluna da **PARTE** não foi tocada em nenhuma das telas. Ela é a nossa perna, e trocá-la pelo nome
faria a célula repetir o `Nome da Parte` / `Parte (Nome simplificado)` que já está ao lado.

### O que quase passou batido: essa coluna tem OUTROS leitores

Os dois Settlement Advice — o de **NDF Commodities** (`_ndfadv_collect`) e o de **Opção**
(`_optadv_collect`) — consomem a TELA do Live Position, e tiravam dessa mesma célula o CPF/CNPJ para
resolver o cliente por trás da conta omnibus (§197). Trocar a célula pelo nome zerou esse lookup
**sem erro nenhum**: o `''.join(dígitos)` de um nome não é um CNPJ, o `.get()` no RefData devolvia
vazio, e o aviso sairia endereçado ao **titular do guarda-chuva** — que é exatamente a falha que o
§197 existe para evitar. Foi o `check_ndf_advice.py` que pegou.

A correção não desfaz nada: os dois avisos passaram a **usar a resolução da própria coluna**, que é
a mesma pergunta que eles faziam. O que separa "resolveu" de "não resolveu" é `_lp_is_taxid`, e o
teste dela é a ausência de LETRA — razão social com número (`3M DO BRASIL`) tem letra e nunca casa.
Sem cadastro a célula volta como documento, o omnibus não resolve, e a linha cai para o nome da
posição — **byte a byte o comportamento anterior**. Com cadastro, resolve como antes. E agora há uma
resolução só: a tela e o aviso não têm como discordar de quem é a contraparte da mesma operação.

Há **três** funções, e a divisão importa:

| | O que faz |
|---|---|
| `_lp_taxid_key` | normaliza o documento (dígitos + zero-fill) — dos DOIS lados |
| `_lp_cpty_name_by_taxid` | resolução CRUA: o nome, ou `''` sem cadastro — é a dos consumidores |
| `_lp_cpty_by_taxid` | versão de EXIBIÇÃO: cai para o número mascarado |

O índice (`_lp_taxid_names`) reindexa o `_refdata_by_taxid()` — que chaveia por dígitos crus — pela
chave normalizada, e é um comprehension sobre um mapa **já cacheado por mtime**: o arquivo não é
lido de novo, e o índice é refeito só quando aquele mapa troca de objeto, que é quando o RefData
muda em disco.

**O rótulo da coluna NÃO mudou.** Continua `CPF/CNPJ ...` porque é o nome do campo no arquivo da B3,
e é por ele que o painel de colunas, os filtros e os exports que a mesa já usa se orientam. Se a
mesa preferir "Contraparte (RefData)", é um rename de rótulo — e aí vale conferir os três lugares
que listam colunas em cada tela.

`check_lp_counterparty_name.py` prende as três telas com posição sintética em `tempfile` (nada de
dado real), inclusive o caso do zero à esquerda comido, e a seção 7 prende o acoplamento com os dois
avisos.

---

## §292 — File Interpreter: VARIANTES de template por par de pernas

Um template do registro pode ser **variante** de outro: `base_key` aponta o template-mãe e
`le_pair` diz para qual par de pernas ele vale (`MGT x JPM`). O gerador continua chamando o motor
pela chave BASE — quem escolhe a variante é o motor (`_fi_variant_key`), pelo par do deal. Sem par,
ou sem variante cadastrada, vale o base **byte a byte**: os goldens do TER e do OPC passam com as
19 variantes semeadas ativas, e é essa a prova de que semear não mudou arquivo nenhum.

A variante é **cópia completa** do layout, e é isso que a torna útil: nela mais campos podem virar
`Fixed` (a conta da parte/contraparte, o Nome Simplificado do header — que aí dispensa o
`b3-accounts`) sem tocar em código. Ela pode ainda cadastrar o **`file_name`** do arquivo gerado;
em branco, vale o `{PREFIX}_{BUCKET}.txt` de sempre.

Três coisas que não dão erro nenhum:

- **o par do FWD Start / Other Publisher / Commodities usa a regra do BUCKET** — linha com cliente
  JPM é a perna espelhada, e o par dela é `LAWTON x JPM`, não `MGT x JPM`. Foi o primeiro teste a
  falhar, e falhou dizendo a verdade: eu tinha escrito `MGT x JPM` no golden;
- a cópia da regra vive no navegador (`static/js/fi-ter-pair.js`), porque o preview escolhe a
  variante antes de qualquer ida ao servidor. `check_fi_variants.py` roda a cópia JS no `jsc` e
  compara com a do servidor, caso a caso;
- **o modal de criação ACHATA o `source_by_page`** da página escolhida nos campos planos. A variante
  é de uma página só; um `source_by_page` herdado do base venceria a edição feita nela, em silêncio,
  porque o motor resolve o override primeiro.

### O par não sai de um regex sobre o nome

`MGT x JPM` estava sendo cadastrado e o motor usava o `JPM x CLI`. A causa: `JPMORGAN CHASE BANK,
N.A. - SAO PAULO BRANCH` casa com o regex de JPM, e a entidade era resolvida por texto. Hoje
`_ter_le_side` consulta o cadastro **`le-spn`** primeiro e só cai no regex quando o nome não está
lá — a mesma fonte que o resto do app usa para dizer quem é entidade nossa.

### Segregação por página

Variante não aparece no rail: ela é assunto da PÁGINA dela, e o rail lista só os templates BASE. A
exceção é a variante órfã (base apagado), que entra na lista para não sumir da tela com o arquivo
ainda no registro. Clicar no chip de uma página abre o modal com as variantes **daquela** página —
antes o template criado para o Vanilla aparecia ao clicar em Commodities.

Foram semeadas as 19 variantes que a lógica hardcoded já produzia (Opt Comm, FXO, NDF Commodities,
FWD Start e Other Publisher), para ninguém ter de recriá-las à mão.

---

## §293 — Os sete domínios DCE viram mappings, e os três layouts DCE entram na biblioteca

A planilha `Mapping DCE` virou **sete cadastros** (`dce-country`, `dce-type-of-derivative`,
`dce-type-of-swap`, `dce-type-of-verification`, `dce-functionality`,
`dce-underlying-asset-category`, `dce-underlying-asset`), com os JSONs versionados e o `seed`
vazio — o `dce-underlying-asset` tem ~14 mil linhas, e repeti-las no `routes.py` criaria uma segunda
lista para divergir da primeira.

As colunas carregam `lang` (chave i18n), e o `colLabel` do `mapping.html` traduz **cabeçalho, filtro,
export e modal**. Coluna sem `lang` continua no rótulo inglês — é o que mantém os 33 cadastros
antigos como estavam.

Do manual "Enviar Arquivos" entraram também os três layouts de DCE (Registro pp. 553–557, Alteração
558–562, Atualização 563–564). São **catálogo**: documentam o layout, não comandam gerador nenhum.

---

## §294 — Sugestão de domínio aberto NUNCA usa `<datalist>` nativo

A lista de clientes do MT300 no `/mapping` saía no popup do navegador: ele ignora o tema, não
acompanha a largura do campo e, com as ~560 contrapartes do Reference Data, cobre a tela inteira.

O padrão passou a ser um dropdown próprio **abaixo do campo, com a MESMA largura e `max-height`
(~220px) com rolagem** — `mapAttachDrop`/`.map-ac-drop` no mapping.html, irmão do `.ar-ac-drop` que o
Add/Edit Deal do New Deals já tinha. Dois detalhes que só aparecem quando faltam: o clique do item é
por **`mousedown`** (dispara antes do `blur` do input) e reemite `input`/`change` — é o que deixa o
`wireRefdata` completar os campos irmãos —, e o esconder vem DEPOIS desses eventos, senão o próprio
`input` reabre a lista. O domínio segue aberto: a lista é sugestão, não trava.

---

## §295 — `file-interface` → `file-interpreter`: o nome vale em TUDO

A tela se chama **File Interpreter** e o código dizia `file-interface` — página, APIs, pasta de
dados e identificadores. Renomear só o template deixaria a armadilha de pé: criar amanhã uma página
"File Interface" confundiria o código inteiro.

O legado não quebra, e são cinco proteções:

- a URL antiga `/file-interface` **redireciona**;
- as APIs antigas são **alias** das novas — aba aberta com o HTML de antes do deploy continua
  salvando;
- o valor antigo gravado no `Page_Access` é **normalizado na leitura** (`_get_page_access`);
- o sino aceita os **dois rótulos** nos três mapas de destino;
- a pasta `static/data/file-interface/` é **migrada na subida** para a nova, sem sobrescrever o que
  já existe: template criado pela tela na instância do time não está no git, e renomear diretório
  não pode sumir com cadastro de runtime.

Havia ainda um `file-interpreter.html` **morto** no repo, do Initial commit, com dois links
apontando para ele — era ele que eu estava editando quando o usuário disse "você está alterando o
fileinterface, mas deveria ser o fileinterpreter". Apagado, links corrigidos, e aí sim o rename.

---

## §296 — O campo calculado vira CADASTRO, e o preview BAIXA o arquivo em vez de enviar

Campo com Source `Mapping` ou `Calculated` tinha o cálculo no código. Agora o **Source Field/Value
aceita FÓRMULA**, com builder por dropdowns no Edit Sources e no modal da variante:

| | |
|---|---|
| `FIELD(Campo)` | o valor do campo, como está |
| `DATE(Campo)` | o campo como data AAAAMMDD |
| `BIZDIFF(A; B)` | dias úteis ANBIMA entre A e B, zero-padded pela LARGURA do format (9(01) → `3`, 9(02) → `03`) |
| `ADDBIZ(Campo; N)` | a data do campo + N dias úteis |
| `LOOKUP(mapping; IN; OUT; Campo)` | a linha do mapping cuja coluna IN casa com o campo |
| `CASE(Campo; DE=PARA; …)` | de-para em linha; valor fora da lista devolve VAZIO, que o motor completa com espaços — é assim que se cadastra "e no resto, branco" |

Argumentos por `;`, campo casado com o deal pelo **nome da COLUNA** cego a caixa e espaço. Texto que
NÃO parseia como fórmula continua documentação e o valor do gerador vale — é o que mantém todo
cadastro existente byte a byte. Fórmula vence o gerador; `Fixed` vence tudo.

A cópia do navegador é `FiTer.calc` (com `FiTer.prime` carregando o ANBIMA e os mappings do LOOKUP)
e `check_fi_calc.py` compara as duas, caso a caso, pelo `jsc`.

Duas consequências que valem por si:

- **a Cotação para o Vencimento (campo 15 do TER) EFETIVA desloca as datas das linhas de
  verificação (tipo 2)** N dias úteis para frente, no calendário do deal. Hoje o campo nasce em
  branco, então nada muda sem cadastro;
- **o page-spec é relido a cada abertura do preview** (`fiLoadSpec`), então template editado vale no
  próximo duplo clique, sem refresh da página. Fetch que falha mantém o spec em memória, em vez de
  deixar o preview sem cadastro nenhum.

O botão **Send** do preview virou **download** (só o ícone): o servidor devolve o CONTEÚDO do
arquivo — mesmo gerador, byte a byte, template e variante incluídos — sem gravar no share, sem
notificação e **ignorando o status do deal**. É a conferência que a mesa pedia sem inventar um
segundo gerador.

---

## §297 — Os arquivos da Intrag entram na biblioteca do File Interpreter

Seção **Intrag**, com dois templates base — `intrag-ndf` (30 colunas) e `intrag-option` (38), os
dois `;`-delimitados e **sem linha de header** — e uma versão por página dentro de cada um.

**Nem toda variante é por par de pernas.** As da Intrag se dividem por PRODUTO, e `NDF Commodities`
não é um `le_pair`. Daí o **`variant_label`**: rótulo de tela, só isso — quem o motor consulta para
escolher variante continua sendo o `le_pair`. Sem ele as versões apareciam todas como "Default" e
não havia como distingui-las.

O conteúdo transcreve o que `_save_intrag_ndf_entry`, `_save_intrag_ndf_moeda_entry` e
`_save_intrag_opt_entry` gravam hoje, campo a campo. Duas coisas que o cadastro deixa visíveis pela
primeira vez: na NDF, a versão de moeda diverge de **17 das 30** colunas (é a tabela de mercadoria
com OUTRO significado da coluna Trade Price em diante, e a Participant Position sai **invertida** —
a linha das páginas genéricas é a perna do banco contra o Lawton e a carteira registrada é a do
fundo); na Option, divergem exatamente as **sete** colunas que o `is_fxo` sobrescreve. Cada
divergência vive num `source_by_page` do base.

Os seis nascem `status: library` — o arquivo continua sendo escrito pela tela da Intrag a partir da
grade, e o cadastro documenta e edita o layout sem comandar a geração. Ligar o gerador ao cadastro
(como o TER e o OPC já são) é outra decisão, e pede golden byte a byte.

**O FWD Start não tem versão, e é de propósito**: o `routes.py` restringe a alimentação a
`('vanilla', 'other-publishers')` porque *o strike só existe na strike set date, quando a operação
rebooka como vanilla* — ela chega à Intrag pela versão do Vanilla. Criar a variante documentaria uma
linha que nunca é gerada.

O seletor **Versions** do cartão leva a contagem no rótulo ("Versions 4"): fechado ele mostra só a
versão atual, e a tela dizia "Versions Default" — foi assim que as duas versões da Intrag Option
pareceram não existir. E o subtítulo da página deixou de dizer "B3 file layouts": não vale enumerar
os destinos ali, a lista envelhece calada no próximo arquivo.

---

## §298 — O Reload do Index B3 escrevia só o `<td>`, e a mercadoria sumia da linha

Cadastrado o ativo no Index B3 depois da importação, o **Reload Data** limpava o badge mas o campo
**Commodities** continuava vazio no Edit Deal. A causa é de uma linha: o restore fazia
`td15.text(...)` e parava aí.

Quem lê a mercadoria depois é **`row().data()`** — o modal de edição (`d[15]`), o export e o payload
do save. E texto posto só no DOM ainda **some no primeiro redraw**, porque paginar, ordenar ou
filtrar repinta a célula a partir do dado. O restore passou a gravar `cell().data()` e o `<td>`, e
só quando a célula está vazia: valor que veio da API ou do upload não é atropelado.

Três buracos vieram junto, e a varredura pediu as seis páginas de New Deals:

- o restore só alcançava a página **visível** da grade (era o passe 2, sobre os nós renderizados).
  Foi para o passe 1, que varre a tabela inteira — a operação costuma estar noutra página;
- a **Opt Commodities não resolvia a mercadoria na montagem da linha**. O NDF Commodities já tinha
  `deal.Commodities || _SUBJACENTE_MAP_NDF[ua]`; a de opção tinha só o valor gravado, então nem
  recarregar a página inteira preenchia a célula;
- **Opt Commodities e Opt FXO buscavam o `Subjacente.json` sem cache-busting** (o NDF Commodities já
  usava `?_=`): o navegador podia servir a cópia velha e o botão não recarregava nada. O mesmo valia
  para o `RefData.json` do aviso de contraparte.

Mais duas de higiene na Opt Commodities, que a irmã de NDF já fazia: **zerar o mapa de Fator
Conversão** antes de reconstruir (pela regra de merge o `0,01` cadastrado por engano sobrevivia à
correção para `1,0`, e o Quoted in Cents continuava YES) e **limpar o cache do parser do box**, que
senão segue com o mapa velho no próximo upload da mesma aba.

As três páginas genéricas de NDF têm `reloadSubjacenteAndRefresh` **no-op de propósito** — a máquina
de Index B3 não é carregada nelas, e o stub existe para o SweetAlert compartilhado não quebrar.

O arquivo-dia no servidor continua com Commodities vazio até a linha ser salva: a tela resolve pelo
cadastro em toda leitura e o servidor já faz o mesmo fallback onde importa (a família da confirmação
lê `deal.Commodities or subj.mercadoria`).

---

## §299 — Opção de commodities de PALM OIL ganha o documento dela

O arquivo que existia era o **HTML cru exportado do Word** — 3.118 linhas de `mso-*` e nenhum
Jinja —, então registrar a família e apontar para ele mandaria ao cliente a linha de exemplo do
`.doc` no lugar das operações. Portado a partir do `opt-comm-strike-usd.html`, que é o irmão dele: a
comparação palavra a palavra fecha em **doze** diferenças, e o `check_conf_optcomm_palmoil.py`
prende a décima terceira, que é cláusula mexida por engano.

O Anexo I vai de 16 para **19 colunas** (Código da Bloomberg, Quantidade, Taxa de Conversão da
Mercadoria e a Data de Verificação dela), e cabeçalho, linha do Jinja e painel de edição são
travados na mesma ordem — desalinhar os três é entregar a coluna vizinha ao cliente.

**O `.doc` cita "Anexo II" sete vezes e NÃO traz a seção**, inclusive na fórmula de liquidação. O
anexo foi trazido do Termo de palm oil, que é da mesma mesa e o mesmo anexo: a alternativa era
entregar um documento que manda ler um anexo inexistente. O teste trava que os dois sigam idênticos.

**O PDF sai do HTML JÁ RENDERIZADO** (`word_html_pdf`), e não da réplica em reportlab — o padrão de
documento novo desde a Opção de Câmbio (§139). Aqui não é estilo: o `opcao_pdf` imprime o Anexo I de
16 colunas, e o documento assinado sairia sem a Taxa de Conversão da Mercadoria, que é justamente
como o preço em MYR vira USD. `_CONF_OPT_PDF_FROM_HTML` é o registro de quem usa qual caminho, e o
`doc_html` passou a ser montado ANTES do PDF porque agora ele é a fonte dele.

No gerador, a bolsa sai da constante do documento (`_CONF_PALMOIL_BOLSA`) e a Data de Verificação da
Taxa de Conversão é a Data Final de Verificação da Mercadoria, inclusive no bullet, onde ela é a
própria Data de Exercício. `_conf_opt_family` já resolvia `palm-oil` pela mercadoria, então o card do
New Deals e o Generate do Monitor passaram a oferecer o documento sem mais nada.

---

## §300 — Send Conecta passa a valer para o NDF Vanilla

A página já tinha o fluxo inteiro no navegador — envio em lote e por linha, com a trava de
maker/checker —, e quem recusava era o servidor: `vanilla` só entrava no `send-conecta` com
`download: true`, porque **o registro dele era de outra ferramenta** e o app só montava o arquivo
para conferência. A mesa passou a registrar por aqui; o que muda é o DESTINO e nada mais.

Duas coisas vieram junto porque a mudança as torna obrigatórias:

- **as linhas de verificação (tipo 2) saem nos dois caminhos.** Emitir só no download faria o
  arquivo que a mesa baixa para conferir diferir do que vai para a B3 — divergência que não aparece
  em lugar nenhum até a B3 recusar o registro;
- **o preview escolhe a variante pela regra do BUCKET** (`FiTer.pick`), como as outras três. Ele
  usava `pairSimple` (LE × contraparte, `MGT x JPM`) justamente porque "esta página não gera o
  arquivo", o que deixou de ser verdade: com variante cadastrada para a perna espelhada, a tela
  mostraria um layout e a B3 receberia outro. O `pairSimple` continua no espelho do navegador, sem
  nenhuma página usando.

O ciclo fecha sem mais nada: o **Mapping B3 ID** já é genérico por produto, então o retorno leva o
deal de `Sent` para `Success`, e os gatilhos do Success do vanilla (Pending Confirmation e a Intrag
NDF de moeda contra o Lawton) já existiam.

Conferido no arquivo gerado: `VANILLA_BANCO.txt` com header + tipo 1 + as três linhas tipo 2, e
`VANILLA_LAWTON.txt` quando a linha é a perna espelhada. Download e envio saem iguais byte a byte
**menos os 10 dígitos do Nº de Controle Interno**, que é sorteado a cada geração — isso é de antes.

⚠️ **Ressalva assumida:** se a outra ferramenta continuar registrando em paralelo, o mesmo trade vai
à B3 duas vezes. A decisão de operar só por aqui é da mesa.

---

## §301 — Edição em lote: a coluna vem antes do valor

A barra oferecia o campo de VALOR à esquerda e o dropdown de COLUNA à direita, e a ordem de uso é a
inversa: sem coluna escolhida o campo de valor nasce desabilitado dizendo *"Select a column
first"* — ele pedia a escolha que estava do outro lado. Os dois trocaram de lugar nas **oito**
telas que têm o par (as seis de New Deals, a Pending Confirmation e o Track Confirmations).

O espaçamento não mudou junto, e isso não é detalhe: nas seis páginas de New Deals a barra é
`d-flex` com margens `me-*` em cada elemento, não `gap`. O valor tinha `me-1` e o select `me-2`;
inverter só a ordem apertaria o botão Send de 0.5rem para 0.25rem. As classes acompanharam a
troca — `me-1` entre os dois campos, `me-2` antes dos botões.

A inversão sobrevive ao primeiro clique porque as três implementações reconstroem o campo de valor
com `innerHTML`/`.empty()` **dentro** do wrapper, que permanece onde está. Um reappend à barra
desfaria a ordem em silêncio, no primeiro uso.

---

## §302 — O export do Reference Data leva o CounterpartyDetails junto

O duplo clique na linha já mostrava CGD, contas, defaults e contatos; o export levava só as treze
colunas da grade. Quem precisava dos contatos ou da data do CGD de meia dúzia de clientes abria
contraparte por contraparte e copiava do popup.

Entram **seis colunas** — CGD · Settlement Net Type · Bank Accounts · Default PAY · Default
RECEIVE · Contacts — que nascem **escondidas** (quem quiser vê-las usa o Columns) e vão **sempre**
no arquivo: o `EXPORT_COLS` é uma lista de ÍNDICES, e índice não olha visibilidade.

Elas entram na TABELA, e não só no arquivo, porque é a tabela que o DataTables exporta; montar o
arquivo por fora criaria uma segunda leitura do mesmo JSON, para discordar da tela no primeiro caso
de borda. E são escritas no **array de dados** da linha, nunca no `<td>` — o `<td>` é redesenhado a
cada draw e o arquivo sairia vazio (§298).

O que decide o conteúdo da célula:

- **multivalor numa célula só**: itens separados por `' | '` e os campos de um item por `' · '`, que
  é o separador que o próprio popup usa entre telefone e e-mail — quem comparar a tela com a
  planilha lê a mesma coisa;
- **o que não está aprovado sai marcado `(Pending)`**, em vez de ficar de fora. Escondê-lo faria a
  planilha dizer que a contraparte não tem conta nenhuma justamente quando ela tem uma esperando
  checker, que é a linha que alguém precisa olhar;
- `Active`/`Inactive` entre as REGRAS do contato é lixo de importação antiga (o popup já os
  descarta) e sairia repetindo o status;
- o slot de default aponta para um **id** de conta, e id não diz nada a quem lê a planilha: o que
  sai é o texto da conta.

Os dois JSON são buscados em paralelo e qualquer um chega primeiro, então o `buildRows` preenche o
que já houver e o `decorateAllPending` — que os dois fetches já chamavam — completa o resto. Toda
ação do popup passa pelo mesmo `bankFetch`, então editar um contato atualiza a célula sem recarregar
a tela.

---

## §303 — Gravar no Track Confirmations não apaga mais o filtro

Depois de uma ação em massa a tela voltava ao estado limpo: sem filtro de coluna, sem card ativo,
nada marcado. Quem filtrou chegou até ali para trabalhar naquele recorte e ainda tem o resto da
lista para tratar — limpar obrigava a refiltrar a cada gravação, e numa fila de esteira isso é o
trabalho inteiro.

Agora some a SELEÇÃO, não a VISTA: as marcas e a coluna de aplicação, que dizem respeito à próxima
ação (marca sobrando faz a ação seguinte cair em linha que ninguém escolheu). O preço é conhecido e
é o certo: a linha que deixou de casar com o filtro desaparece da tela — foi exatamente o que a
alteração fez com ela.

**Uma armadilha só apareceu com o filtro preservado:** a coluna de Pending divide o índice com o
filtro dos cards, e o `applyPendingFilter` fazia `search('')` nela sempre que nenhum card estava
ativo. O texto digitado no campo de Pending ficaria na tela sem efeito nenhum — filtro que se vê e a
tabela ignora. Sem card, a coluna volta a ser do campo, pelo mesmo `colSearch` (que subiu para o
escopo de fora por causa disso e continua entendendo `blank`).

A gravação de UMA linha não dizia nada — o modal fechava e a tabela recarregava. Com filtro
aplicado a linha alterada pode nem estar na vista, então não sobrava sinal de que deu certo. Passa a
avisar como as ações em massa, e o mesmo para a exclusão de uma linha (que também engolia a falha do
servidor).

---

## §304 — Advanced Export: o recorte que a tela não está mostrando, e a SÉRIE

O Export da casa (Copy · CSV · Excel · Print · PDF) exporta o que está NA TELA, e é o que se quer
quase sempre. Faltavam duas coisas, e o item **Advanced Export** cobre as duas: um recorte que a
tela não mostra (uma contraparte só, sem as colunas que não interessam) e **vários DIAS** — a tela
mostra um dia, e a única forma de olhar o mês era abrir a página vinte vezes.

O modal tem formato, nome do arquivo, escopo (tudo · página atual · faixa de posições), o intervalo
de dias, até N filtros coluna/condição/valor, a lista de colunas e as opções do formato. O rodapé
conta quantas linhas casam **antes** de exportar.

Decisões que não são óbvias:

- **quem gera o arquivo continua sendo o DataTables Buttons**, por um botão temporário com o mesmo
  `extend` de sempre. Um gerador próprio seria um segundo CSV, com outro separador e outro BOM, e os
  dois divergiriam no primeiro acento;
- o `rows` do export é uma **função** sobre o índice, com o modifier em `search:'none'`: a seleção já
  foi decidida no modal (inclusive se os filtros da tela entram), e deixar o DataTables filtrar de
  novo aplicaria a busca duas vezes — o "ignorar os filtros da tela" nunca chegaria a valer. A ORDEM
  vem do `order:'applied'`;
- **a tabela é resolvida no CLIQUE**, não na ligação: a Recon FXO destrói e recria a DataTable quando
  as colunas chegam do servidor, e o item ficaria preso à instância morta — um menu que abre e não
  exporta nada, sem erro no console;
- **Excel só aparece com o JSZip carregado e PDF só com o pdfmake.** Oferecer o que não tem
  biblioteca produz um clique que não faz nada e nenhuma mensagem.

### O intervalo de dias

Quem responde por um dia é o **endpoint que a própria página consulta** para desenhar aquele dia: o
intervalo o chama uma vez por data, em vez de ler os JSON do cache por fora — um leitor próprio seria
uma segunda regra sobre os mesmos arquivos, para discordar da tela no primeiro caso de borda. O
resultado vai para uma DataTable oculta, e daí em diante o export é o mesmo de sempre. Cada linha
sai com a **Reference Date** na frente; sem ela, um arquivo de vinte dias não diz de que dia é cada
linha.

- **Tela sem arquivo-dia não some com a seção: ela nasce DESABILITADA com o motivo escrito.**
  Reference Data é cadastro — existe o de agora e nada mais —, e um campo que desaparece sem
  explicação lê-se como defeito.
- **Só dia ÚTIL** (calendário ANBIMA, o mesmo `anbima.json` do resto do app). Os arquivos nascem de
  rotinas que rodam em dia útil, então pedir sábado, domingo e feriado é pedir o que não existe — e
  era isso que enchia a lista de "não consegui ler" com dias em que não havia nada a ler. De 05/08 a
  24/08 são 20 dias de calendário e 14 úteis.
- **Os dias são pedidos EM SÉRIE**, com teto de 120 e **60 s por dia**. Em paralelo, um intervalo de
  três meses abriria noventa requisições de uma vez sobre o processo único que serve a mesa (o app
  escala com threads, não com workers); e a leitura em série significa que **um dia que não responde
  segurava os outros dezenove** — daí o timeout, que é o que impedia a exportação de travar no
  último dia.
- **`exact=1` em todo pedido do intervalo.** As telas de Live Position andam para trás até dez dias
  úteis quando não há arquivo do dia — é o que as mantém populadas —, mas para quem monta uma série
  isso é o arquivo de OUTRO dia carimbado com a data pedida: pedir 05/08 devolvia 20 linhas do
  arquivo de 24/07. Num intervalo de catorze dias seria o mesmo dia repetido catorze vezes, o que é
  pior do que travar, porque não parece defeito. A TELA continua sem mandar o parâmetro.
- **O dia substituído é pulado.** O payload passou a dizer `source_date` — a data do arquivo lido de
  verdade —, e quando ela não é a pedida o dia entra como "sem arquivo". Vale mesmo onde o `exact`
  for ignorado, porque a checagem é sobre o que voltou, não sobre o que foi pedido.
- **O arquivo sai com o que veio.** Um dia que falha não derruba a exportação: num intervalo de vinte
  dias basta um para perder os dezenove que estavam lá. O rodapé separa as três coisas — N linhas de
  X dias · Y sem arquivo · Z com erro —, e **a falha leva o MOTIVO** (`HTTP 404`, `resposta não-JSON`,
  o `error` do payload). "Não consegui ler 20 dias" não distingue rota errada, sessão vencida e erro
  do servidor; sem o motivo não há o que investigar. `HTTP 404` em todos os dias, aliás, é o sintoma
  de endpoint novo com o Flask sem reiniciar.
- **A contagem some quando há intervalo** e dá lugar a "N dias úteis a ler": a contagem é a da tela,
  e prometer um número antes de ler os arquivos seria prometer justamente o que essa exportação não é.

O casamento das colunas é pelo **RÓTULO**, não pelo índice: a tabela dos arquivos não tem checkbox
nem Actions e ganha a Reference Date na frente.

Ligadas: Operations B3, OTM Settlements, as duas Live Positions, Cognos, NDF Cockpit, NDF Other
Publisher, Latam Desk Position, as cinco telas do swap-characteristics, a Recon FXO e a Pending
Confirmation — esta pelo **snapshot diário** (`/api/pending-confirmation/snapshot`), porque a tela
mostra a situação de AGORA (Aging e Status são recalculados na leitura) e a série só existe na foto
que a manutenção das 11:30 grava. Sem intervalo ficam as que não têm arquivo-dia (Reference Data,
Mapping) e as que não expõem o dia num endpoint `{columns, rows}`: New Deals (busca por POST),
Accrual/MtM (payload por card) e a Recon Comitente (lê do banco, sem data).

---

## §305 — Data é dd/mm/aaaa em toda tela

O `<input type="date">` desenha no locale do **sistema**. No Windows do JP isso é `mm/dd/yyyy`, e a
mesa lê `03/04` como 3 de abril onde o campo quis dizer 4 de março — um erro de data que não dá erro
nenhum. O padrão já era dd/mm/aaaa (está escrito no `pages/index.html` e nos dois Summaries), mas
quatro telas tinham campo nativo à vista.

O caminho é o **`altInput` do flatpickr**, que dá as duas coisas ao mesmo tempo: ele esconde o input
original — que segue com o `value` em ISO, e por isso NENHUM código em volta muda — e desenha ao lado
o campo em dd/mm/aaaa. Nas duas telas de Intrag e no ticket isso importa porque o ISO é exatamente
como a linha é gravada (`_save_intrag_*` grava `%Y-%m-%d`).

Corrigidos: os dois campos do intervalo do **Advanced Export**, os três do modal do **Intrag NDF**,
os quatro do **Intrag Option** e o Due Date do **ticket**.

Duas coisas que não dão erro nenhum quando se esquece:

- **quem escreve no campo por código tem de avisar o picker.** O `value` do original muda, mas o
  campo que se VÊ é o outro: sem o `setDate`, abrir o modal numa linha e depois noutra mostra a data
  da PRIMEIRA. Daí o `otcDateSync`, que o preenchimento e a limpeza dos modais de Intrag chamam;
- no ticket, o campo **nasce escondido** (só o master edita o prazo), e a classe do campo visível vai
  SEM o `d-none` — copiar a classe inteira o deixaria oculto para sempre, com o `show()` destravando
  um input que o flatpickr esconde de qualquer jeito.

O `type="date"` **invisível** continua legítimo: é o picker atrás de um texto readonly em dd/mm/aaaa
— o `.date-wrap` das duas Recons (`opacity:0` por cima do texto) e o botão de calendário do CGD no
Reference Data. Ali o que se lê é sempre o texto.

`otcDateField`/`otcDateSync` saem do `export-advanced.js`, que 30 telas já carregam, para não haver
um segundo helper de data.

---

## §306 — A mensageria do Operations B3 pergunta ao cadastro de contas

A regra de qual ponta da liquidação intragrupo vira e-mail estava escrita no endpoint: `casa == MGT
e contraparte == Banco`. Ela conhecia esse par e só ele — a visão do **Lawton** e a da **Atacama**
passavam direto, e o mesmo pagamento saía pelas duas pontas, cobrado duas vezes de quem recebe.

O `b3-accounts` ganhou duas colunas:

- **Messaging** (Consider/Disregard): a mensageria sai na visão desta conta? É a pergunta que estava
  no código. Seed: Banco assina; MGT, Lawton e Atacama não.
- **Reference Data Name**: como a entidade está escrita no Reference Data. O Nome Simplificado ao
  lado é o apelido de 20 caracteres da B3 (`INTRAGLAWTONFDO`), que não é razão social nenhuma — e era
  ele que sobrava quando a contraparte era entidade nossa, porque essas não têm linha no RefData pela
  conta B3. A coluna é do tipo `refdata`, então o nome se escolhe da lista.

**Estar no cadastro é ser conta INTERNA** — a tabela lista as contas B3 das nossas entidades e nada
mais —, e é por aí que o BCC de compliance passa a saber que a contraparte é o Lawton ou a Atacama,
em vez de casar o prefixo do Nome Simplificado.

Detalhes que não dão erro nenhum:

- **conta FORA do cadastro gera** (é a conta de terceiro, de que a mensagem sai hoje): travá-la por
  falta de linha calaria a rotina inteira em qualquer instância que não tivesse aberto o /mapping;
- a comparação é por **dígitos** — a mesma conta aparece `73760.10-2` num arquivo e `7376010 2` no
  outro;
- o `upgrade` completa a coluna nova **pelo seed** (por conta e por LE): o arquivo que já está em
  disco vem sem ela, e um default cego `Consider` faria a mensagem sair pelas duas pontas —
  `Disregard` cego a faria não sair de nenhuma, que é pior, porque some sem erro;
- a linha da visão descartada continua indo a `Generated` (a liquidação saiu pela outra ponta), mas
  **só se o `opb3-events` a aprovar**: carimbar a operação cancelada esconderia justamente a linha
  que ninguém tratou.

O inner join com o `opb3-events` continua onde estava, agora dito por escrito: são **quatro**
perguntas que precisam concordar — o evento é liquidação, a modalidade é Bilateral*/Bruta*, a visão
assina, e a linha ainda não virou e-mail.

**No mesmo assunto:** o filtro do arquivo de operações do Daily Settlement passou a considerar a
conta **73760.20-5** (CLIENTE 2) além da própria (73760.00-9). O que não passa por esse filtro não
existe para nada depois dele — a página Operations B3, a mensageria, os avisos e as recons saem
todos desse JSON. A de CLIENTE 1 (73760.10-2) continua fora. E a coluna dos filtros do `_DS_IMPORTS`
é **1-based**, enquanto a do `_CETIP_BEHAVIOUR`, logo acima no mesmo arquivo, é 0-based: trocar uma
pela outra filtra pela coluna vizinha e devolve arquivo vazio, sem exceção nenhuma.

---

## §307 — Todo caminho de banco sai do `Config.DATABASE_DIR` (e a branch de produção)

Mover os bancos para o share exigia achar QUATRO lugares, porque quatro montavam o caminho por conta
própria a partir do diretório do pacote: o `_PC_DB_DIR` dos três DuckDB do Pending Confirmation, o
`_DB_DIR` dos dois da esteira, o `DB_PATH` do de comitentes e os três scripts de migração. Mover só o
`DATABASE_PATH` deixaria o app abrindo o banco de usuários no share e todo o resto local — sem erro
nenhum, e com a migração "dando certo" no banco errado.

Agora existe **`Config.DATABASE_DIR`**, a pasta de TODOS eles, e é dela que saem o `DATABASE_PATH`,
os sete do `DATABASE_ACCESS_PATHS` e os quatro consumidores. Uma variável (`OTC_DATABASE_DIR`) move o
conjunto; `DATABASE_PATH` continua movendo só o banco de usuários. Os scripts têm fallback para o
caminho antigo, para continuarem rodando fora do venv da aplicação.

Duas correções entraram junto: o **`db.sqlite3` estava escrito em dois lugares** com valores
diferentes (o gerenciador de lock guardava um arquivo e o ORM abria outro), e o caminho de rede tinha
**escapes inválidos** (`\l`, `\B`) que o Python ainda tolera — um `\b` num caminho futuro viraria
backspace, sem erro nenhum. Agora é raw string.

### As duas branches

`visual-refresh-prod` é a branch que a **instância do JPM** roda, e ela é a `visual-refresh` MAIS um
commit no `apps/config.py`: bancos e share em `\\Nawest.ad.jpmorganchase.com\lac\BRA\intra` em vez de
dentro da aplicação e `I:\`. A diferença é **um bloco de cinco linhas**, entre os marcadores
`── ENV:DEV ──` e `── /ENV ──`, e nada mais — o resto do código pergunta ao Config e não sabe onde os
bancos estão.

Código só nasce na dev e chega lá por merge: `/commit` publica na dev, `/commitjp` faz o merge, troca
o bloco e volta o working tree para o de dev (com o de prod, o app local não sobe — caminho UNC não é
absoluto fora do Windows, e o `_absolute_path_from_environment` recusa na subida). Corrigir direto na
prod é criar uma divergência que ninguém vê até o merge seguinte conflitar.

> Alternativa que segue aberta: o config já lê `OTC_DATABASE_DIR` e `OTC_SHARED_DRIVE_ROOT` do
> ambiente. Com um `.env` na instância do JPM as duas branches ficam **idênticas** e o `/commitjp`
> deixa de ser necessário.

---

## §308 — O `config.py` é o arquivo que fica para trás na instância, e a falha era ilegível

A instância do time subiu com `AttributeError: type object 'Config' has no attribute 'DATABASE_DIR'`,
vinte frames dentro de um import (`run.py` → `create_app` → `register_blueprints` → `routes` →
`manual_conf`). Não era bug do código: eram **dois arquivos de commits diferentes** no mesmo
checkout — `manual_conf.py` do §307 (que lê `Config.DATABASE_DIR`) ao lado de um `config.py`
anterior a ele, que ainda montava cada caminho de banco na mão.

**Por que justamente esse arquivo.** O `config.py` é o único que se ajusta à mão na instância
(timeouts, caminhos, `SECRET_KEY`), então ele costuma estar **modificado localmente** — e um
`git pull` não sobrescreve arquivo modificado. O resto da árvore atualiza, ele não, e o checkout
passa a ser uma mistura. É a mesma classe de "não está funcionando" do reloader desligado (§CLAUDE §8):
o código no disco não é o código que se pensa estar rodando.

**O que mudou.** `create_app` confere `_REQUIRED_CONFIG_NAMES` **antes** de importar os blueprints e
recusa subir dizendo o nome que falta, o arquivo, a causa provável e o comando:

```
apps/config.py esta desatualizado: faltam DATABASE_DIR. O arquivo costuma ficar
modificado localmente na instancia, e nesse caso o `git pull` nao o sobrescreve.
Confira com `git status apps/config.py` e traga a versao do repositorio
(`git checkout -- apps/config.py`, ou guarde o seu ajuste com `git stash` antes).
Reinicie o Flask depois: o reloader esta desligado na instancia do time.
```

Três decisões:

- **A conferência vem antes do `register_blueprints`**, e não dentro de cada módulo. Cada consumidor
  se defendendo daria quatro mensagens diferentes para a mesma causa — e a primeira a estourar
  dependeria da ordem dos imports.
- **A lista é só o que módulos de FORA leem direto do `Config`** (`DATABASE_DIR`, `DATABASE_PATH`,
  `DATABASE_ACCESS_PATHS`, `SHARED_DRIVE_ROOT`). São justamente as chaves cuja ausência não aparece
  na subida, e sim no import do módulo que a lê. **Nome novo no config que outro módulo leia entra
  aqui junto.**
- **Recusar, nunca cair para um default.** Um fallback `basedir/static/data/db` deixaria o app subir
  lendo o banco LOCAL no dia em que os bancos estivessem no share — sem erro nenhum, que é o defeito
  que o §307 existiu para eliminar.

**Na instância, o conserto é um comando:**

```bash
git status apps/config.py          # confirma que ele está modificado localmente
git stash push apps/config.py      # só se o ajuste local importar
git checkout -- apps/config.py     # traz a versão do repositório
```

E **reiniciar o Flask** — o reloader está desligado.

---

## §309 — A raiz do share também é do `Config`, e três recons não perguntavam

O §307 tirou o caminho de BANCO de dentro dos módulos. Ficaram de fora as raízes de REDE, e três
delas continuavam escritas à mão: `_CETIP_BASE` do `recon_fxo`, `_DCAD_BASE`/`_OUTPUT_BASE`/
`_CETIP_DEST_BASE` do `recon_comitente` e `_INPUT_BASE` do `recon_payrec` — todas
`r"I:\Confirmation\..."`.

O `routes.py` já estava certo (treze destinos, todos `os.getenv(X, os.path.join(
Config.SHARED_DRIVE_ROOT, …))`), e é isso que torna a falha invisível: na instância que aponta para o
UNC, o app inteiro fala com o servidor e SÓ essas três recons continuam pedindo a letra mapeada. Se o
processo subir como serviço, ou com outro usuário, o mapeamento de unidade não existe — e a recon
falha dizendo que não achou o arquivo do dia, que se lê como *"a B3 não mandou"*.

Na dev nada muda: o default do config **é** `I:\`, e `os.path.join('I:\\', 'Confirmation', …)`
devolve o literal de antes byte a byte.

Cinco scripts que espelham um destino do app foram junto (`create_cetip_folders`,
`create_counterparty_folders`, `export_electronic_inventory_excel`,
`backfill_cetip_position_files_vernacci` e o `export_users_excel`, que apontava para o banco de
usuários **local**), com o mesmo `try: Config / except: literal` dos scripts de migração — eles
precisam rodar fora do venv.

O `check_config_names.py` passou a guardar a regra: varre por AST os literais dos módulos versionados
de `apps/` e recusa qualquer coisa que comece por letra de unidade ou `\\servidor`. Comentário e
docstring ficam de fora por construção, então o caminho citado em prosa continua permitido. Ao passar
a importar o `Config`, o `recon_payrec` levou junto o `check_spb_status.py`, que deixou de rodar fora
do Windows sem a variável — os cinco testes afetados ganharam o `os.environ.setdefault` que o
`check_config_names` já usava.

---

## §310 — O IR da opção é do net, e o rodapé do aviso somava a coluna errada

O aviso de pagamento de prêmio da Mondelez (24/08/2026, seis prêmios de TRIGO) saiu assim:

    Resultado Apurado   (28.884,17)
    IR (0,005%)               1,44
    Resultado Final     (28.884,13)

As duas primeiras linhas estão certas. A terceira não é nem o apurado nem o apurado menos o imposto —
é o apurado mexido em **quatro centavos**.

O §-anterior do IR de opção (`7da7fe4`) acertou as três condições — só PRÊMIO paga, a base é o NET por
contraparte × data, e só quando o banco paga — e então **rateou o imposto por todas as linhas de
prêmio**, para que a coluna somasse o imposto do net. O rateio é o certo: toda soma da aplicação (a
coluna do aviso, o Trade Level, o Settlement Summary) é uma soma de LINHAS, e um valor que só existisse
no rodapé sumiria das outras telas.

O que estava errado era o LADO. A regra do líquido encolhe o caixa pelo sinal de cada linha
(`ap - ir` se positivo, `ap + ir` se negativo), então a parte do imposto que caía numa linha de
RECEBIMENTO era subtraída dali enquanto a que caía numa de PAGAMENTO era somada: 0,74 de um lado, 0,70
do outro, e o rodapé — que soma a coluna — imprimia a diferença. Uma retenção não anda para os dois
lados.

Hoje o rateio vai **só para as linhas que pagam**. Nada é decidido por linha: quem diz se há imposto, e
quanto, continua sendo o net; a linha carrega a parte da retenção que sai com ELA, a que recebe sai com
`0,00` e o líquido igual ao apurado. A coluna volta a fechar com o rodapé, e o rodapé com o net —
`28.884,17 − 1,44 = 28.882,73`, a mesma conta do Pay/Rec (§205: net Pay −219.047,36 → −219.036,41).

Por ser um rateio, o Settlement Summary e o Trade Level se corrigem junto, sem tocar em nenhum dos dois:
os dois já netam somando linhas.

`check_optadv_ir.py` prova o caso reportado número a número e as três condições do imposto.

### A tabela do prêmio não leva mais as duas colunas

Corrigido o rodapé, sobrou o que as colunas por linha diziam. `IR 0,005%` e `Resultado Líquido` são
fatos do NET, não da operação: a primeira imprimia um rateio que não é do contrato, e a segunda
repetia o Resultado Apurado com alguns centavos a menos numa operação que não sofreu retenção nenhuma
— a retenção é uma só, sobre o que o banco paga no dia.

No aviso de **Pagamento de Prêmio de Opção** as duas saem da tabela, nas TRÊS classes de subjacente
(mercadoria, taxa de câmbio e EDG), e o imposto aparece uma vez, no quadro de baixo — e só quando há o
que reter: sem retenção não existe linha de `IR (0,005%)` no quadro, porque `R$ 0,00` num aviso que já
não tem a coluna levanta uma pergunta ("por que zero?") que o documento não responde. O Resultado
Final fica sempre: é o valor que o parágrafo de instrução manda transferir.

Quem decide é o par `premium` × `family`, e não o rótulo do produto: o rótulo ('Opção de Commodities')
existe para ser lido por gente e muda com a classe do subjacente. Por isso `_optadv_email_rows` passou
a marcar a linha com `family='option'` — o aviso de **exercício/recompra** de opção e o **termo de
mercadoria** seguem com as duas colunas, byte a byte.

O corte acontece ANTES de montar a tabela, então a **ficha em PDF** (`ndf-pdf-cpty`) sai com o mesmo
cabeçalho e as mesmas linhas do corpo do e-mail — cortar depois deixaria o anexo com uma coluna que o
e-mail não tem. E a TELA de Settlement Advice de Opção continua com as duas colunas: é lá que a mesa
confere e corrige os valores.


---

## §311 — Onboarding (Overview + Tracking Docs) e a recon de CGD saída do Alteryx

O item `CGD` do menu apontava para `/cgd`, uma rota que **não existia** — clicar nele dava 404. Ele virou
a seção **Onboarding**, com duas telas, e a reconciliação ganhou a quarta irmã.

### O banco da lista

A mesa acompanha os CGDs numa lista do SharePoint. `scripts/import_cgd_sharepoint.py` carrega a
exportação (`Sharepoint-CGD.xlsx`, do Downloads) num DuckDB na pasta de sempre
(`Config.DATABASE_DIR/cgd_sharepoint.db`, §307), com as 30 colunas da lista. Ele casa as colunas **por
nome** — cego a caixa, acento e pontuação — e **procura** o cabeçalho em vez de presumir a linha 1: a
exportação vem com título em cima, e uma linha acima importaria a planilha deslocada, com o CNPJ na
coluna do SPN e sem erro nenhum. A importação REESCREVE a tabela: rodar duas vezes dá o mesmo
resultado, e a linha apagada no SharePoint some daqui.

**O `Aging` da planilha é ignorado.** Ele é do dia da exportação; aqui é refeito a cada leitura, em dias
úteis ANBIMA, e PARA no `Conclusion - Stamp`.

### As duas telas

**Overview** é o desenho do Confirmations Monitor: três filas verticais — **Legal**, **Banking OTC** e
**CEM MO** —, e nelas entra todo documento cujo Status não é `Active`. Cada item mostra o status como
está escrito, o aging e onde parou. A etapa vem do cadastro `cgd-stage` e, sem cadastro, é derivada
pelo primeiro carimbo que falta (marcada como derivada na tela).

**Tracking Docs** é a tabela no padrão da casa — checkbox, as 30 colunas, coluna de ações, filtro por
coluna, Columns/Add Row/Export/Clear Filters, `otcCellCopy`, squircles 32×32 — com o Status em badge
pill gradiente e o aging colorido só nos extremos. A tela DIZ de onde leu (o caminho do banco) e, quando
ele não existe, o comando que o cria: "sem documentos" e "ninguém importou ainda" são estados
diferentes.

### A recon (tradução do `Alteryx CGD.yxmd`, 150 nós)

O batimento responde de quem temos CGD assinado × de quem a B3 reconhece. Buckets: `matched`,
`pending_b3` (assinado e falta incluir na B3), `pending_action` (opera e o contrato não fechou),
`justified` (garantidor ou conta encerrada) e `only_b3`.

O que mudou do workflow, e por quê:

- o **calendário** é o ANBIMA do app, não a aba `Feriados` do `Auxiliar.xlsx`;
- as **contas** saem do cadastro `b3-accounts` (`OWN` + LE que assina CGD), não dos dois números
  escritos no filtro;
- as três abas do `Auxiliar.xlsx` viraram cadastro do /mapping (`cgd-b3-participante`,
  `cgd-garantidor`, `cgd-conta-encerrada`): eram planilhas de rede mantidas à mão, e o batimento rodava
  com a lista de ontem sem dizer nada;
- **CNPJ compara por dígito** dos dois lados (§197);
- o `Dummy.xlsx` e o `.xlsx` gravado no share sumiram: o resultado fica no cache do dia e a planilha é o
  Export da própria tela.

Os cortes do FEP continuam literais porque são a regra do processo: fora o aditamento, fora `Cancelado`,
e "assinado" é um dos três status. O aging segue em dias CORRIDOS (é o relógio que a mesa já usa) e o
`DOC TRANSACIONAL` continua se lendo `Docusign`.

Um bug que a integração pegou: o cache gravava em D-1 e a leitura sem data caía em `hoje` — o
batimento rodava e o GET seguinte dizia que ninguém tinha rodado.

`check_cgd_docs.py` e `check_cgd_recon.py` cobrem os dois lados.

---

## §309 — Os SweetAlerts do Holidays Calendar falam o idioma do app (e o mês sai maiúsculo)

A data do popup do feriado estava fixa em `pt-BR` e os títulos/badges dos alertas eram texto inserido
por JS — que o I18nManager nunca alcança, porque ele traduz os `[data-lang]` uma vez, no load. A
página ganhou o padrão da casa: mapa `_TRANS` local (en/br/es) com `t()` lendo
`__OTC_TRACKER_LANG__` — a MESMA chave do I18nManager (o swapchar lê `language`, que é a chave
antiga; não copie dele). A data por extenso sai do `Intl.DateTimeFormat` no locale do idioma
escolhido, com o **mês sempre de inicial maiúscula** via `formatToParts` — em inglês o locale já
capitaliza, em pt/es ele escreve minúsculo, e capitalizar por regex sobre a frase montada quebraria
no primeiro locale com ordem diferente. `segunda-feira, 10 de Agosto de 2026` ·
`Monday, August 10, 2026` · `lunes, 10 de Agosto de 2026`.

## §310 — A campanha de verticalização: 24 features fora do `routes.py`

Entre 26/08 e 27/08 o `routes.py` saiu de **39.696 para 31.012 linhas** (−8.700), com **24 verticais**
em `apps/pages/features/`. O processo de cada fatia foi sempre o mesmo — rede de caracterização ANTES
(quando não havia), extração, a MESMA rede verde depois, guardas atualizados na mesma mudança, suíte
inteira, commit — e a suíte cresceu de 84 para **94 scripts**.

A ordem saiu do acoplamento medido (entradas de fora do grupo), e as fronteiras decididas em cada uma
estão nos docstrings dos `__init__.py`. As que valem regra geral:

- **entrada não é sinal de que a feature não sai — é sinal de plataforma misturada.** O
  `_anbima_holidays` (holidays), o `_otc_app_url` (conf_escalation), o coletor do forecast
  (`_forecast_payload`, que o Other Products Summary lê), o `_pcx_is_bizday`, os leitores
  `_cpd_path/_cpd_load/_cpd_find`, os helpers `_ei_*` e o motor do File Interpreter (`_fi_*`, 36
  entradas: ele é o gerador de layout de TODO arquivo) ficaram no `routes.py` esperando o `platform/`;
- **gancho de volta é import atrasado dentro da função**: o pull do NDF grava os pares de re-booking
  via `_mdea.record_rebooks`, e os saves do New Deals espelham a Intrag via `_intrag_engine()` — os
  entrypoints só são importados no fim do `routes.py`, então import no topo não existe;
- **verrugas são REGISTRADAS, nunca consertadas na extração**: o envelope do e-mail do forecast vai
  fixo para OTC Ops + accrual-cc enquanto os headers levam as listas do card
  (`check_forecast_api.py`); a primeira gravação da Intrag entra sem coluna de ciclo e é o re-save
  que materializa o `New` (`check_intrag_api.py`); o calendário do holidays duplica por caixa
  (`check_holidays_api.py`). Consertar qualquer uma é decisão, com teste mudando junto.

O que resta no `routes.py` é o coração de plataforma (notificações, sessão/authz, banco, ANBIMA, os
helpers compartilhados acima) e as famílias grandes de página (New Deals com 44 rotas, os summaries,
live positions, MtM/Accrual, mapping com 1263 linhas) — candidatas das próximas fatias, na mesma
mecânica.

## §311 — Scheduler mora na feature; o REGISTRO fica no wiring (e o kill-switch dos testes)

Sete features têm laço agendado (bacc, mt300, mdea, conf_escalation, boxscan, pcx, deals_monitor). O
laço vive em `commands.scheduler_loop`/`engine`, mas o `_schedule_on_start('<label>', …)` fica no
bloco de wiring do `routes.py`, ao lado do import do entrypoint: o gancho é de plataforma, e chamá-lo
do corpo do módulo da feature exigiria importar o `routes` ali — o ciclo que a regra das features
proíbe.

Junto veio **`OTC_DISABLE_SCHEDULERS=1`**, honrado pelo `_start_schedulers`: os testes que sobem o
app várias vezes (o guard do config purga e reimporta `apps.*`) corriam com os laços VIVOS ao lado —
uma corrida de import intermitente, e um catch-up de 16h/17h/19h30 num processo de TESTE tentando
reivindicar o slot REAL do dia e mandar o e-mail de verdade. O `check_boxsched`, que prova justamente
a subida, LIMPA a variável no próprio arnês — é o único que precisa dos laços de pé.

## §312 — Extração VERBATIM com religação por AST, e o guarda de bytecode que a prende

Para os emaranhados grandes (deals_monitor, cetip, intrag, counterparty_details) o desenho fino
domain/queries/commands sairia caro demais de uma vez. Eles foram movidos **verbatim** — nomes
internos preservados, inclusive para os testes que os trocam (`N._NDM_…`, `CE._CETIP_…`) — com uma
ferramenta que copia os corpos por AST e reescreve todo `Name(Load)` sem dono para `_R().<nome>`
(busca atrasada no routes). Três armadilhas dela, já pagas:

- o `col_offset` do AST é offset em **BYTES** (utf-8): linha com acento desloca a reescrita em chars;
- num target de assign, só o `ctx=Store` define nome — `spn_by_key[_ei_match_key(name)] = …` tem um
  Load DENTRO do target, e tratá-lo como definido deixou um nome sem religar;
- nome religado só explode quando o CAMINHO roda. Por isso o `check_soc_layers` ganhou a **seção 9**:
  desmonta o bytecode de toda função das features e cobra que cada `LOAD_GLOBAL` exista no módulo —
  no primeiro giro pegou um `traceback` sem import no caminho de ERRO do pcx.

A separação interna desses quatro é trabalho futuro; a fronteira com o `routes.py` — e os guardas —
já valem.

## §313 — Os lotes finais: 43 verticais, e o `routes.py` em 21 mil linhas

A campanha fechou com **43 features** em `apps/pages/features/` e o `routes.py` em **21.322 linhas**
(de 39.696, −46%). O próprio New Deals saiu no último lote — como a maior casca (44 rotas), com os
motores ficando no routes. Os últimos lotes foram MtM e Accrual verbatim (com redes novas escritas antes:
`check_mtm_api`, `check_cognos_api`, `check_intrag_api`, `check_cpd_api`, `check_ei_api`), a família
de liquidação INTEIRA numa vertical só (`other_products`, 29 rotas — o `_ops_trade_rows` é o único
lugar que sabe as famílias, então parti-la seria cruzar features), e as cascas de confirmation,
pending_confirmation, live_positions, file_interpreter, ndf_cockpit e ndf_other_publisher.

O que FICOU no `routes.py` é plataforma de verdade: sessão/authz, notificações, os DuckDB, ANBIMA,
os coletores da liquidação (`_ops_*`, `_otm_*`, `_latam_*`, `_opb3_*`, `_ndfsum_*`), os stores por
dia, o motor `_fi_*` do File Interpreter, os leitores `_cpd_*`/`_ei_*`/`_pc_*` e os motores do New
Deals (caches, lookup de contraparte, roteamento por publisher, espelho Lawton, geradores
TER/Conecta) — o material da fase `apps/pages/platform/`, que é o próximo passo natural: dar casa
própria ao que hoje as features alcançam por `_R()`.

Oito guardas que varriam o TEXTO do `routes.py` ganharam a leitura concatenada (routes + árvore de
features), e os que desmontam AST aceitam a chamada por busca atrasada (`func.attr` além de
`func.id`). A suíte fechou em **96 scripts** verdes, todos com `OTC_DISABLE_SCHEDULERS=1` no arnês
coletivo e as páginas principais respondendo 200 no smoke.

## §314 — A fase platform/ começa: calendário ANBIMA e notificações

As duas primeiras horizontais ganharam casa própria em `apps/pages/platform/`, na ordem do
acoplamento medido: **`anbima.py`** (o calendário de dias úteis — `_br_now`, `_prev_anbima_bizday`,
`_pcx_is_bizday` e as duas cargas históricas do `anbima.json`, movidas as duas de propósito:
unificá-las muda comportamento de borda e é outra decisão) e **`notifications.py`** (o motor do sino
e do Web Push — o mapa `_NOTIF_PAGE_URL`, `get_notif_connection`, o ensure/migração da subida,
`_create_notification` → `_push_notify`; era o nome mais alcançado pelas features, 118 pontos de
chamada). Os ENDPOINTS do sino continuam no `routes.py`: rota é casca.

O padrão da fase, que as próximas fatias repetem:

- **O `routes.py` mantém os nomes como ALIAS** (`_x = _pf_anbima._x`): as features seguem
  alcançando por `routes.<nome>` sem mudar, e os 22 testes que trocam `R._create_notification`
  por espião continuam interceptando todo mundo — o alias é um atributo do `routes`, e todo
  chamador o resolve em tempo de chamada.
- **O ESTADO mora na platform** (`_ANBIMA_HOLIDAYS`, `_notif_db_done`, `_notif_db_retry_at`):
  alias de objeto mutável apontaria para o set velho quando a carga rebinda o global. Teste que
  troca estado troca LÁ — `check_conf_escalation` e `check_notif_db_boot` foram apontados na
  mesma mudança.
- **Platform não importa NOME do routes, e o import do MÓDULO é atrasado** — o que ainda é do
  `routes` (`DB_PATH`, `NOTIF_DB_PATH`, `_B3_DATA_DIR`, `_DuckDBHandle`, `duckdb_*`) é alcançado
  por `routes.<nome>` dentro da função, andaime declarado até a camada de banco ter fatia. É o que
  mantém válidos `R.NOTIF_DB_PATH = tmp` e os contadores de `check_notif_db_boot` sobre
  `R.duckdb_write` — e `R.duckdb_read_unlocked` segue importado no `routes` DE PROPÓSITO (o
  pyflakes o marca como não usado; `check_db_read_path` o troca por espião e a platform o alcança
  por atributo).
- **Guardas na mesma mudança**: `check_soc_layers` ganhou a seção 10 (platform nunca importa
  feature nem nome do routes, LOAD_GLOBAL resolve, e o alias do routes É o objeto da platform —
  extração pela metade é cópia que diverge); a seção 8 cobra os `def` movidos fora do routes;
  `check_notif_page_url` varre `platform/` junto com as features; `check_mc_notify` lê o
  `_push_notify` no arquivo novo (o split por texto estourou na hora — foi assim que a mudança de
  casa apareceu). `check_unlocked_reads` não precisou de nada: ele varre `apps/**` por nome de
  função, e `get_notif_connection` levou o nome junto.

Dois leitores inline do estado no `routes.py` foram reescritos para a função (`_forecast_spine`
usa `_pcx_is_bizday`), porque ler `_ANBIMA_HOLIDAYS` por alias é ler o objeto de antes da carga.
O `routes.py` fechou em **20.752 linhas** (−570). Suíte: 96/96 verdes.

## §315 — Cinco fatias de uma vez: a infraestrutura horizontal inteira na platform/

O lote fechou a camada de INFRA da fase platform/ (§314 tem o padrão; este lote o repete cinco
vezes): **`json_cache.py`** (o armazém JSON — `_cache_lock`, `_atomic_write_json` com o
`bump_cache_gen` no funil, os claims diários cross-process do BACC/MDEA/MT300, o daycache memoizado
`_day_files`/`_day_json` e o `_unique_filepath`), **`mail.py`** (relay, `SHARED_MAILBOX`, logo,
gradiente no-op, `_parse_emails`, `_email_drafts_response`, `_otc_app_url` — os SENDERS ficam com os
donos; quem stuba SMTP troca `R.smtplib.SMTP`, e módulo é um objeto só para todo importador),
**`dates.py`** (`_parse_date_any`, `_parse_deal_date`, `_EN_MONTH_NAMES` — parse é aqui, calendário
é no `anbima.py`), **`db.py`** (`_DuckDBHandle` + `get_db_connection`; primitivas seguem no
`database_access.py`, caminho e `_ensure_db_initialized` seguem no `routes` como superfície de patch)
e **`authz.py`** (master/admin, allowlist do `Page_Access` com o cache por SID, o registro
`_CONTROL_PANEL_CARDS`/`_CP_ENDPOINT_CARD`, `_safe_landing`, `_user_can_access_page` — os dois
`before_request` que APLICAM ficam no `routes`: registro em blueprint é casca).

O que este lote ensinou, além do §314:

- **Objeto de estado mutado IN PLACE aceita alias** (`_cache_lock`, `_daycache_memo`,
  `_page_access_cache`): ninguém os rebinda, então o alias do `routes` continua vivo e os testes
  que os leem por lá não mudam. O critério é o rebind, não o tipo — o set da ANBIMA não aceitava.
- **Caminho relativo a `__file__` muda de valor quando o código muda de casa**: o `_load_nav_urls`
  precisou de `../../templates` no lugar de `../templates` — o único ajuste não-verbatim do lote,
  conferido pelo tamanho do `_NAV_URLS` (77 páginas).
- Dois guardas de TEXTO acompanharam o código na mesma mudança: `check_req_cache` lê o funil do
  `_atomic_write_json` no arquivo novo, e a âncora nova da seção 8 do `check_soc_layers` aprendeu
  que `'_cache_lock = threading'` casa com o `_dash_cache_lock` — âncora de substring pede o
  sufixo (`threading.RLock`).
- `import portalocker` e `import tempfile` saíram do topo do `routes` (só o armazém os usava);
  o `duckdb_read_unlocked` FICA (§314 — superfície de patch e atributo que a platform alcança).

Sete módulos na `platform/` (calendário, notificações, armazém JSON, e-mail, datas, banco,
autorização), `routes.py` em **20.139 linhas** (21.322 no fechamento da campanha, −1.183 na fase).
Suíte: 96/96 verdes. Próximas fatias: os motores compartilhados (liquidação, `_conf_*`, CC/CPD,
quotes/forecast, EI, `_mc_*`, FI/PC/OpB3, New Deals) e as seis separações internas dos verbatim.

## §316 — Os três primeiros MOTORES na platform/: liquidação, `_conf_*` e o Counterparty Details

A fase entrou nos motores compartilhados, na ordem da fila do §315. Três fatias, todas VERBATIM
com religação por bytecode (compila cada def isolado e lê os LOAD_GLOBAL com `co_positions` — a
mesma técnica da seção 9/10 do `check_soc_layers`, que é o que prova depois que nenhum nome ficou
órfão):

- **`settlement.py`** (~1.400 linhas) — a família de liquidação inteira: `_ops_trade_rows` (o único
  lugar que sabe as famílias, §199) e todo o `_ops_*`/`_opssum_*`/`_opsadv_*`, o elo de equity
  (`_ops_equity_link`, `_latam_equity_b3_index`, `_latam_trade_dt`) e o `_swadv_indexador`. Os
  leitores `_opb3_*` + `_ops_norm_event` FICARAM no `routes` de propósito: são da fatia FI/PC/OpB3,
  e a fatia os alcança por `routes.<nome>` como qualquer andaime.
- **`confirmations.py`** (~1.330 linhas) — o motor `_conf_*` das quatro famílias: segregação por
  contraparte × mercadoria, estado New→Generated→Success, `_conf_esteira_stages` (§254), as três
  páginas de geração, o XML da B3 e o `_conf_pc_set_fepweb`. Os três `_mc_*` vizinhos
  (`_mc_conf_trade_keys`, `_mc_ei_link`, `_mc_stamp_generated`) ficaram para a fatia `_mc_*`. O
  estado `_conf_subj_cache` é mutado in place — alias vale (critério do §315).
- **`counterparty.py`** (~390 linhas) — o CounterpartyDetails.json: `_cpd_*`, `_norm_spn`, os
  normalizadores (`_contacts_norm`/`_net_norm`/`_bank_norm`/`_cgd_norm`, `_default_slot`,
  `_CP_NET_TYPES`) e o parser `_cc_*` do Update Contacts — CC e CPD juntos porque operam o mesmo
  arquivo.

O que este lote ensinou, além do §314/§315:

- **Chamada interna do módulo não passa pelo alias.** O §314 prometia que trocar a função no
  `routes` intercepta todo mundo — vale para quem chega DE FORA (o alias resolve em tempo de
  chamada), e deixa de valer quando o chamador mudou de casa JUNTO: `_cpd_load` chama `_cpd_path`
  por global do próprio módulo. Os quatro testes atingidos (`check_cpd_api`, `check_fwdstart_conf`,
  `check_ops_equity_option` ×2) trocam agora nos DOIS lugares — `R.` para quem chega de fora, o
  módulo da platform para a chamada interna.
- **`session` do Flask é superfície de patch.** O `check_swap_advice` faz `R.session = {...}` para
  carimbar o maker fora de request context; um `from flask import session` na platform passaria por
  cima do espião. Na platform ele é `routes.session`, sempre.
- **`__module__` mente sob `functools.wraps`.** O wrapper do `@_req_cached` carrega o nome do módulo
  decorado, mas o CÓDIGO — e os globals que ele resolve — são do `request_cache.py`; a seção 10 do
  guarda estourava com os globals do wrapper. Quem diz onde o código mora é o `co_filename`, e o
  corpo decorado (que é o que a religação precisa provar) segue conferido via `__wrapped__`.
- **O `_fontes_com_rotas_` dos oito testes ancorados em texto varre `platform/` junto** — a mesma
  correção do §314 (`check_notif_page_url`), aplicada de uma vez às oito cópias; as próximas fatias
  não tocam nesses testes. Quatro guardas com leitura direta do `routes.py` foram apontados para o
  arquivo novo (`check_req_cache` ganhou `platform/settlement.py` na lista; `check_co12_roll`,
  `check_conf_optcomm_palmoil` e `check_ops_summary` leem o módulo da fatia).

Dez módulos na `platform/`, `routes.py` em **17.320 linhas** (−2.819 no lote; 21.322 no fechamento
da campanha). Suíte: 96/96 verdes. Próximas fatias: quotes/forecast, EI, `_mc_*`, FI/PC/OpB3,
New Deals — e as seis separações internas dos verbatim.

## §317 — Mais três motores: Forecast, Electronic Inventory e a cola da esteira (`_mc_*`)

O lote repete o §316 (mesma ferramenta de religação por bytecode, mesmo padrão de alias) três
vezes:

- **`forecast.py`** (~530 linhas) — a matriz do Settlement Forecast: `_forecast_collect`/
  `_forecast_payload`/`_forecast_spine`, os `_fcst_*` (parse de data, entidade, produto, LOB,
  normalização) e os mapas de contrato de swap (`_swap_contract_ident_map`/`_swap_contract_cpty_map`).
  É horizontal porque a família de liquidação lê daqui (`_ops_settlement_counts`,
  `_ops_swap_trade_rows`) — pelo alias do routes, então a ordem das fatias não importou.
- **`electronic_inventory.py`** (~420 linhas) — resolução de pasta de cliente no share, o scanner
  do root com cache/TTL (`_EI_ROOT_CACHE`, estado in place — alias vale), versões ordinais e
  listagem. O **`ELECTRONIC_INVENTORY_ROOT` FICOU no routes de propósito**: o `check_ei_api` faz
  `R.ELECTRONIC_INVENTORY_ROOT = tmp`, e o motor o lê por `routes.<nome>` — o teste passou sem
  UMA linha de edição, que era o objetivo. O `_CONFIRMATION_TYPES` vem direto do `manual_conf`
  (mesma tupla que o routes apelida), preservando `_EI_CONFIRMATION_TYPES = _CONFIRMATION_TYPES`
  byte a byte.
- **`manual_confirmation.py`** (~770 linhas) — a cola `_mc_*`: o gancho `_mc_save_from_deal`
  (chamado de DENTRO do `_pc_save_from_deal`, que fica no routes), `_mc_legal_entity`, os
  documentos da pasta (`_mc_confirmation_docs` + E-mail Subject), papéis e avisos
  (`_MC_STAGE_ROLE`, `_MC_STAGE_NOTIFY_ROLES`), o Generate do Monitor e o `_mc_pc_sync`. Os
  seeds de mapping (`_MC_VALIDATION_SEED`…) ficaram no routes: são material do `_MAPPING_DEFS`,
  não da cola.

A lição nova: **constante de módulo que referencia outra fatia da platform importa DIRETO.** O
`_MC_GENERATE_PRODUCTS` referencia os grupos das confirmações (`_conf_ndfcomm_groups`…) no NÍVEL
DO MÓDULO, e o bloco de alias das confirmações vive num ponto do `routes.py` POSTERIOR ao import
deste módulo — `routes.<nome>` não existiria ainda. O import direto de `platform.confirmations`
entrega os mesmos objetos que o alias aponta, e platform→platform não fere fronteira nenhuma.

Nenhum teste precisou de repoint neste lote (os quatro do §316 já tinham sido; o
`_fontes_com_rotas_` corrigido lá cobriu os ancorados em texto daqui de graça). Guardas: seções
8 e 10 do `check_soc_layers` com os três módulos novos.

Treze módulos na `platform/`, `routes.py` em **15.828 linhas** (−1.588 no lote; −4.311 na fase
de motores; 21.322 no fechamento da campanha). Suíte: 96/96 verdes. Próximas fatias: FI/PC/OpB3,
New Deals — e as seis separações internas dos verbatim.

## §318 — platform/: FI, Pending Confirmation e Operations B3 (2026-08-27)

Sétimo, oitavo e nono motores da fase (a fatia "FI/PC/OpB3" da fila do §317), no mesmo padrão
§314/§315 — verbatim por bytecode, alias no routes, guardas na mesma mudança:

- **`file_interpreter.py`** (~420 linhas) — templates, variantes por par de pernas
  (`_fi_variant_key`), fórmulas (`_fi_calc_value`) e a montagem de linha (`_fi_build_line`). O
  **`_FILE_INTERPRETER_DIR` FICOU no routes** (os sete check_fi_* fazem `R._FILE_INTERPRETER_DIR
  = tmp`); calendário e mappings do LOOKUP por busca atrasada. O cache `_fi_tpl_cache` (in
  place) mora na platform com alias vivo.
- **`pending_confirmation.py`** (~840 linhas) — os três DuckDBs, `_pc_derive_row`, as TRÊS
  regras de Pending Status (§7), a manutenção das 11:30, o snapshot, as métricas e o
  `_pc_save_from_deal` (que dispara a esteira via `routes._mc_save_from_deal` — atrasado, então
  os espiões seguem valendo). `_PC_DB_DIR` e `_B3_DATA_DIR` ficaram no routes (superfície de
  patch); o estado `_pc_scheduler_started` (REBINDADO) mora na platform; o REGISTRO do
  scheduler segue no wiring do routes.
- **`operations_b3.py`** (~720 linhas) — o arquivo-dia (`_opb3_load`/`_opb3_import`), as regras
  do cadastro `opb3-events`, o breakdown, os mapas de perna interna (TER/swap/NDFC/swap-prem) e
  a mensageria. Os dois loaders `@_req_cached` vieram junto (o decorador por import direto do
  `request_cache`, como no §316) e o `check_req_cache` passou a ler o arquivo novo. O
  `_OPB3_MSG_RECIPIENTS_FILE` FICOU no routes: é caminho sobre `_DAILY_METRIC_DIR`, que os
  testes patcham.

Um tropeço instrutivo: a whitelist do extrator dizia `json` e o módulo do FI nasceu SEM o
`import json` — e o `except Exception` do `_fi_load` engoliu o NameError, devolvendo None como
se o template não existisse. É a mesma classe de silêncio que a seção 9 do guarda caça; a
whitelist de um slice tem de casar com os imports do header, e o pyflakes nos módulos novos
agora faz parte do fecho de cada fatia.

Repoints: `check_pc_mass_update` (fonte + platform/pending_confirmation.py) e `check_req_cache`
(platform/operations_b3.py na lista). Os `_fontes_com_rotas_` não mudaram.

## §319 — platform/new_deals.py: o motor do New Deals (2026-08-27)

O décimo motor, o maior da fase (~2.450 linhas, 82 nomes): os caches de deal das quatro páginas
(`_find_*`, `_deal_matches`, `_fxo_deal_from_row`, `_ndf_deal_from_api`), os dois pulls da
Athena com schedulers (estado `*_scheduler_started` rebindado mora lá), a regra de Amend
(`_ND_AMEND_*`, `_nd_api_amend`, `_nd_cancel_in_file`), a resolução de contraparte por accronym
(§7), a perna fraca (`_ndf_weak_leg`), o espelho Lawton e a geração TER
(`_generic_ndf_ter_line`, `_ndf_comm_ter_lines`).

Duas decisões de fronteira que valem regra:

- **Função patchada E chamada por dentro da fatia pode simplesmente FICAR no routes.** O
  `_fxo_refdata_by_spn` (3 testes patcham) e o par `_GENERIC_ND_PRODUCTS`/`_generic_nd_cfg`
  (2 testes) são chamados por sete funções movidas — movê-los exigiria dual-patch em cinco
  testes; morando no routes, TODO caminho passa por `routes.<nome>` e os espiões interceptam de
  graça. É o complemento da lição do §316: dual-patch é o remédio, ficar no routes é a vacina.
- **A "única entrada de fora" do mdea virou gancho da casca.** O pull importava
  `features.mdea.entrypoint` de dentro da função; na platform isso feria "platform nunca importa
  feature". O `routes._mdea_record_rebooks` faz a travessia (platform → routes → feature, tudo
  atrasado) — quem conhece as verticais é a casca.

O `_nd_token` NÃO veio: é helper de notificação (Accrual e afins o usam) — nome parecido não é
pertencimento. `_ndfadv_*`/`_ndfc_*`/`_ndfsum_*` também não: são a liquidação de NDF, fatia que
não existe mais como fila (ficam como plataforma miúda no routes).

Repoints (todos ancorados em texto): check_cancel_remove (recorta o corpo do arquivo novo e dá
ao `from apps.pages import routes` um routes FALSO em sys.modules — mantém o "sem subir o app"
com os mesmos stubs), check_counterparty_lookup, check_import_window, check_quote_type,
check_quoted_in_cents, check_manual_deals_ea.

No mesmo dia, fora da fase: o log do sino passou a imprimir o `NOTIF_DB_PATH` (imprimia o banco
de USUÁRIOS — mandava caçar lock no arquivo errado) e a abertura do poll ganhou UMA retentativa
de 250 ms num laço (um ponto de chamada `unlocked=True`, que é o que o check_unlocked_reads
prende): a colisão com uma gravação em curso — o "different configuration than existing
connections" do DuckDB — é de milissegundos, e o ERROR fica reservado à falha que persiste.

**Dezessete módulos na `platform/`, `routes.py` em ~11.870 linhas** (−3.960 nos dois lotes;
−9,4 mil na fase de motores; era 21.322 no fechamento da campanha e 39 mil no início de tudo).
Suíte: 96/96 verdes, app com 377 rotas. A fila de motores ACABOU — o que resta são as seis
separações internas dos verbatim (deals_monitor, cetip, intrag, counterparty_details, mtm,
accrual).

## §320 — a separação interna estreia: deals_monitor e counterparty_details (2026-08-27)

Com a fila de motores da platform/ fechada (§319), começou a última frente do §10: a separação
interna dos seis verbatim. As duas primeiras — a menor (`counterparty_details`, engine de 164
linhas) e a primeira do catálogo (`deals_monitor`, 568) — saíram no mesmo dia, e o `engine.py`
das duas foi APAGADO.

**counterparty_details**: `domain.py` (exibição e payload — `_contact_disp`, `_acc_disp`,
`_bank_detail`, `_contact_payload`), `infra/persistence.py` (`_cpd_get_record`/`_bank_get_record`
— achar/criar o record normalizado de um SPN) e `commands.py` (o import da planilha CONTATO DE
CLIENTES e o `_notify_bank` do maker/checker). O domínio grosso continua na
`platform/counterparty.py` — é horizontal, e a fatia não o duplicou.

**deals_monitor**: `domain.py` (catálogo de cards, `_ndm_deal_le`, taxonomia, parse dos
horários), `queries.py` (o snapshot que a página E o e-mail leem — uma contagem só —, os blocos
de pendência, o status do aviso), `infra/persistence.py` (destinatários, claim de slot
cross-process, desfecho do disparo) e `commands.py` (envio, disparo, catch-up, scheduler — o
registro segue no wiring do routes via `start_scheduler`).

A regra que a estreia fixou, e que os próximos quatro repetem: **toda travessia entre camadas é
pelo ATRIBUTO do módulo** (`queries._ndm_pending_blocks(...)`, `persistence._load_...()`), nunca
`from .queries import nome`. O check_ndm_pending_sched patcha seis nomes e o bench dele exercita
o ciclo inteiro: com o import por nome, o espião patchado no módulo dono não interceptaria a
cópia congelada no importador — o mesmo silêncio da regra nº 1 da seção do §10, agora entre
camadas da MESMA feature. Nome patchado e chamado na mesma camada fica de graça (a chamada
interna resolve pelos globals do módulo).

Repoints: o check_ndm_pending_sched importa as quatro camadas e patcha cada nome no dono
(arquivos em P, envio em C, blocks em Q, horários em D); o texto-âncora do retry lê o
commands.py. O check_cpd_api não precisou de UMA linha: ele fala com as rotas por HTTP e patcha
plataforma no routes.

Suíte: 96/96. Restam quatro verbatim: cetip, intrag, mtm, accrual.

## §321 — o fim dos engines: accrual, cetip, intrag, mtm e cognos (2026-08-27)

As últimas separações internas. Com elas **não existe mais `engine.py` no repositório**: as 43
verticais estão todas em domain/queries/commands/infra.

- **accrual** (548 linhas) → `domain` (layout das colunas, parse/formatação de fator, de-para do
  Código IF, aplicação dos fatores, consultas sobre a tabela), `queries` (o build do dia a partir
  da posição de swap), `infra/persistence` (arquivo-dia + pasta de origem), `infra/mappers`
  (planilha de fatores → mapa, um formato por LOB) e `commands` (Batch Conecta + batimento).
- **cetip** (813) → `domain` (o catálogo de comportamento por arquivo, o reconhecimento nome ×
  data, os nomes de saída), `queries` (o cadastro `cetip-files`, a regra viva), `infra/
  persistence` (destinatários, cópia do dia, JSON de posição), `infra/mappers` (cabeçalho →
  índice de coluna), `infra/mail` e `commands` (recorte do BACC, cópias, distribuição).
- **intrag** (663) → `domain` (o par JPM × Lawton e a chave do retorno), `queries` (achar a linha
  nos arquivos-dia), `infra/persistence` (os arquivos-dia sob o `_cache_lock`), `infra/mappers`
  (CSV do Conecta → `{chave: B3 ID}`) e `commands` (as linhas espelhadas dos três produtos).
- **mtm** (715) → as seis camadas, com `infra/mappers` levando os três `_mtm_apply_*` (um por LOB)
  e o de-para do Hybrids.
- **cognos** (133) → `domain`/`queries`/`commands`. Ele estava no catálogo do §10 como "desenho
  fino" **sem ser** — quem o pegou foi a varredura por `engine.py` no fecho do lote, não a lista.
  Lista escrita à mão envelhece; a varredura não.

Três lições:

1. **`domain` é puro de verdade** — nenhum dos 43 importa `routes`, e o guarda recusa. Função que
   precisa de helper de plataforma (`_cc_cell`, `_acc_digits`, `_fi_build_line`, `_mtm_parse_num`)
   NÃO é domain, por mais que pareça regra: ela desce para queries/commands/infra. Quando a única
   dependência é o LOG, o domain usa `logging.getLogger('otc_tracker')` direto — mesmo objeto que
   o `routes.log`, sem a dependência (cetip).
2. **Montar caminho é infra.** O `_mtm_path_for` foi para o domain no primeiro corte e o pyflakes
   o denunciou: ele monta sobre o `MTM_JSON_ROOT`, que é disco.
3. **`col_offset` do AST é em BYTES UTF-8.** O `split_engine.py` (scratchpad) edita fonte por
   posição, e uma linha com acento ANTES da referência desloca a coluna: o
   `'Data Referência': … _mtm_gen_min_value` do MtM saiu recortado 1 caractere à esquerda. A
   edição passou a ser feita sobre os bytes da linha; quem transformou isso em erro visível (em vez
   de corrupção silenciosa) foi o `assert` de que o recorte é exatamente o nome esperado — o mesmo
   cinto do `extract_platform.py` do §316.

Repoints: check_fi_accrual, check_cem_sheets, check_cetip_bacc, check_b3_pattern, check_intrag_api,
check_quoted_in_cents, check_mtm_api, check_fi_mid — todos pelo mesmo critério do §320 (o patch vai
no módulo DONO; texto-âncora aponta para o arquivo que ficou com o corpo). O
`routes._intrag_engine()` manteve o nome e passou a devolver `commands`.

Suíte: 96/96, app com 377 rotas, zero `engine.py`.

## §322 — a prod "travando para iniciar" não era erro de código (2026-08-27)

Depois do merge do §318–§319 a instância do JPM parecia travar na subida; o Ctrl+C mostrava um
traceback que morria dentro do import de uma feature — `weekly_escalation` numa tentativa,
`forecast` na outra. **Módulo diferente a cada vez é a assinatura do problema**: não é aquele
módulo, é o que estava na vez. O fim do traceback dizia tudo:

```
File "<frozen importlib._bootstrap_external>", line 1214, in _cache_bytecode
File "<frozen importlib._bootstrap_external>", line 1239, in set_data
File "<frozen importlib._bootstrap_external>", line 212, in _write_atomic
KeyboardInterrupt
```

Ele estava GRAVANDO os `.pyc`. O código roda de um share, então o `__pycache__` de cada pasta é
remoto, e o merge trouxe **181 arquivos `.py` novos ou alterados** — 181 compilações com gravação
atômica via rede, uma por módulo, sem nada impresso no console. Um pull normal mexe em 2–5
arquivos e ninguém percebe; este mexeu em 181.

A correção é uma linha no `.bat` de subida: `PYTHONPYCACHEPREFIX` apontando para disco LOCAL. Ela
foi para o `start-prod.bat` (o versionado); o `start-otc-tracker.bat`, que é o que a instância
roda, mora no share e não está no repo — a linha tem de ser colada nele à mão. NÃO use
`PYTHONDONTWRITEBYTECODE`: evita a escrita mas recompila tudo a cada subida, e a instância
reinicia várias vezes por dia.

**Onde os `.pyc` caem, e as três coisas que o `.bat` real ensinou.** O `PYTHONPYCACHEPREFIX` faz o
Python **espelhar a árvore do fonte** dentro do prefixo, em vez de criar um `__pycache__` por pasta;
nenhum `__pycache__` novo nasce ao lado do código, e os que já estão no share viram órfãos
ignorados (`for /d /r %d in (__pycache__) do @if exist "%d" rd /s /q "%d"` limpa, se quiser).

1. **A letra da unidade é DESCARTADA** no espelhamento
   (`importlib/_bootstrap_external.py`: `if head[1] == ':' … head = head[2:]`). Isso importa porque
   o `start-otc-tracker.bat` faz `pushd` sobre o caminho UNC, e `pushd` mapeia o share na primeira
   letra livre — era essa a razão de o traceback aparecer ora com `Y:` ora com `L:`: mesma máquina,
   letra diferente. Com a letra fora, as duas produzem o MESMO cache e não recompilam à toa.
2. **O prefixo leva a VERSÃO no caminho.** Como a raiz que o `pushd` mapeia já é a pasta da versão,
   o caminho espelhado começa em `pages\...` — `v12` e `v13` cairiam no mesmo lugar. O Python
   detectaria pelo mtime/tamanho do fonte e recompilaria (não corrompe), mas cada troca de versão
   invalidaria o cache da outra. Daí `…\pycache\%VERSION_PATH%`.
3. **`%LOCALAPPDATA%`, não `%TEMP%`.** O `.bat` da instância já guarda ali o que precisa sobreviver
   (`APP_STATE_DIR` = `%LOCALAPPDATA%\OTC-Tracker`, com o `secret_key.txt` e o `.snapshot` do
   requirements). `%TEMP%` é alvo de Limpeza de Disco e de GPO: limpo, a subida seguinte recompila
   tudo — não quebra, só volta a demorar. O `start-prod.bat` foi alinhado a essa escolha.

O bloco a colar no `start-otc-tracker.bat`, logo antes do `echo Starting OTC Tracker with
Waitress`:

```bat
set "PYCACHE_DIR=%APP_STATE_DIR%\pycache\%VERSION_PATH%"
if not defined PYTHONPYCACHEPREFIX set "PYTHONPYCACHEPREFIX=%PYCACHE_DIR%"
echo [INFO] Bytecode (.pyc) em: %PYTHONPYCACHEPREFIX%
```

## §323 — o "different configuration" que derrubava a ESCRITA de notificação (2026-08-27)

O ERROR da instância voltou: `_create_notification` FAILED com
`duckdb.ConnectionException: Can't open a connection to same database file with a different
configuration than existing connections`. O §319 tinha dado retentativa ao LEITOR (o poll do
sino, `unlocked=True`), mas o lado que aparecia no log era o outro: com um poll aberto
`read_only` no instante do `duckdb.connect(read_only=False)`, quem estourava era o
**`duckdb_write`** — a notificação se perdia, e o sino de quem devia recebê-la nunca ficava
sabendo.

Três fatos que definem a correção:

1. **O conflito é exclusivamente INTRA-processo.** O DuckDB guarda uma instância por arquivo
   dentro do processo e recusa configurações mistas; entre processos o sintoma é outro (lock de
   arquivo, "being used by another process"). Logo a coordenação pode ser toda em memória —
   nenhuma ida ao share, que é o custo que o `unlocked` existe para evitar.
2. **As leituras COM lock não têm o problema.** O lock de arquivo compartilhado × exclusivo
   (portalocker, no sidecar `.lock`) já exclui leitor de escritor, inclusive entre handles do
   mesmo processo. Só a leitura `unlocked` convive no tempo com uma escrita.
3. **Retentativa é loteria dos dois lados**; com abas suficientes polling a cada 8 s, a janela
   de colisão volta. O determinístico é cada lado saber do outro.

O `_UnlockedReadGate` (`database_access.py`, registrado por caminho normalizado, só para
`engine == 'duckdb'`): o poll se registra ao abrir sem lock; a escrita, depois do lock de
arquivo, espera os polls em voo fecharem (são SELECTs curtos; teto de 10 s com WARNING
`unlocked_gate_wait_timed_out`) e conecta limpa. No sentido inverso o poll espera até 1 s por
uma escrita em curso — na maioria das vezes ela fecha em milissegundos e a leitura que hoje
falharia passa a responder com DADO — e, no teto, SEGUE para o connect e falha como sempre
falhou (o endpoint devolve o sino vazio; nenhum log novo nesse caminho). Melhor esforço nos
dois lados de propósito: esperar sem teto seria devolver ao sino a fila que o `unlocked`
existe para evitar, e um leitor doente não pode calar as notificações do app inteiro.

`check_unlocked_gate.py` prende: a colisão da imagem (escrita durante leitura unlocked
COMPLETA — antes, ConnectionException), o inverso (leitura durante escrita curta espera e traz
dado), os dois tetos, o pareamento enter/exit mesmo com falha, e que sqlite não passa pelo
portão. `check_notif_db_boot`, `check_db_read_path` e `check_unlocked_reads` seguem verdes.

## §324 — JSON → DuckDB: o conversor da migração de fluxos (2026-08-27)

Começou a migração dos fluxos de JSON para DuckDB. O primeiro passo é o
`scripts/convert_json_to_duckdb.py`: materializa os JSONs do `Config.DATA_DIR` (na instância do
JPM, o `...\Application\static\data` do share — o caminho NÃO é fixado no script, CLAUDE.md §8)
como bancos DuckDB em `<DATA_DIR>/duckdb/`, deixando os JSONs como fonte até o app ser religado.
Três bancos, no desenho combinado:

- **`holiday_calendars.db`** — uma tabela POR CALENDÁRIO do registro `holiday-calendars.json`
  (`date DATE`, `title`, `calendar`; `_registry` guarda cores/CSS). Calendário criado pela tela
  ganha a tabela na rodada seguinte; calendário sem arquivo vira tabela VAZIA uma vez (não erro,
  e não "convertido" a cada rodada).
- **`reference_data.db`** — `refdata` e `counterparty_details`, TUDO VARCHAR de propósito: é
  cadastro de IDENTIFICADOR, e 158 dos 553 documentos começam com zero — um BIGINT perderia o
  zero à esquerda e a chave pararia de casar em silêncio (§197). Aninhado (CGD/CONTACTS/BANKING/
  NET) vira texto JSON na coluna, consultável por `json_extract`.
- **`daily_caches.db`** — um banco único para as rotinas de arquivo-dia (`cache/**`): um SCHEMA
  por rotina (o caminho sem os segmentos de data — `new_deals_ndf_commodities`, `b3_files_swap`,
  `pending_confirmation`…) e uma TABELA POR DIA (`d_AAAAMMDD[_tag]`; a tag distingue DFLUXO de
  DPOSICAO no mesmo dia e cai quando só repete a rotina). Lista-de-objetos vira tabela TIPADA
  por inferência; payload-objeto (as recons) vira uma tabela por lista interna + `_meta`.

A inferência otimiza sem trair o dado: número só vira BIGINT/DOUBLE quando TODOS os valores da
coluna parseiam, **número com zero à esquerda é texto** (Trade ID não perde o zero), data
reconhece ISO e o `dd/mm/aaaa` da casa (§3 — nunca mm/dd), texto sai byte a byte (o `'C '` dos
códigos B3), `''` vira NULL só em coluna tipada. E a rodada é INCREMENTAL: cada banco guarda um
`_manifest` (caminho, mtime, tamanho) e só reconverte o que mudou — as tabelas da conversão
anterior de um arquivo são derrubadas antes da nova, para lista interna que saiu do payload não
ficar de fantasma. `_last.json` e arquivos sem data não entram e são AVISADOS (`fora do
padrão-dia`), porque um arquivo que some da conversão sem dizer nada pareceria perda.

`check_json_to_duckdb.py` prende tudo isso em tempfile; o smoke contra a dev converteu os 115
arquivos-dia, os 553 do RefData, os 439 do CounterpartyDetails e os 11 calendários, com a
segunda rodada em zero reconversões.

## §325 — o conversor DuckDB no desenho final: um banco POR ROTINA, na db/ (2026-08-27)

Dois ajustes do §324, pedidos na revisão:

- **Um `daily_<rotina>.db` por rotina de arquivo-dia**, não um `daily_caches.db` único com a
  rotina como schema. A ramificação é a que a pasta `cache/` já tem: `daily_new_deals.db`,
  `daily_pending_confirmation.db`, `daily_b3_files.db`, `daily_payrec.db`,
  `daily_reconciliation.db` — a subárvore da rotina (produto, família B3) vira SCHEMA dentro do
  banco dela, e cada dia segue sendo uma tabela (`d_AAAAMMDD[_tag]`; a tag cai quando só repete
  a rotina). Rotina nova em `cache/` ganha o próprio banco sozinha, sem tocar no script. O
  `daily_caches.db` do desenho anterior é REMOVIDO pelo próprio conversor quando encontrado:
  dois formatos em disco seriam duas respostas para a mesma pergunta, e o arquivo é 100%
  derivado dos JSONs.
- **O destino padrão é o `Config.DATABASE_DIR`** — a `db/` que já guarda todos os bancos do app
  (§4) —, não uma pasta `duckdb/` nova ao lado. O manifest é por banco, então o incremental
  continua igual; quem rodou a versão anterior recebe um aviso apontando a pasta antiga.

`check_json_to_duckdb.py` acompanhou: um banco por rotina com os nomes da ramificação, rotina
sem subárvore no `main`, o legado removido, o incremental atravessando bancos e o default do
destino na `db/`. Smoke na dev: cinco bancos, 114 conversões, segunda rodada em zero.

## §326 — fase 2 da migração DuckDB: o espelho vivo (2026-08-27)

A fase 2 começou — e o desenho dela mudou no mapeamento. O plano era religar as LEITURAS para
os bancos, mas os leitores de JSON estão espalhados demais para um flip seguro de uma vez: 71
`fetch` de navegador leem `/static/data/*.json` por URL estática (a tela de calendário lê o
arquivo do calendário DIRETO), e cada leitor de servidor tem o próprio cache por mtime. Trocar
a leitura antes de os bancos estarem SEMPRE atualizados criaria janelas de divergência que não
dão erro nenhum. A fase 2 virou o pré-requisito do flip: o **espelho vivo** — toda escrita de
JSON coberto atualiza o DuckDB na hora; a fase 3 religa os consumidores um a um.

O motor de conversão saiu do script e virou módulo do app (`apps/pages/json_to_duckdb.py`) —
ele agora tem dois chamadores, e a regra "como este JSON vira tabela" não pode existir em dois
lugares. O `scripts/convert_json_to_duckdb.py` ficou como CLI fina (a carga completa/
reconciliação); ganhou `convert_daily_files(rels)` para converter SÓ o arquivo gravado, sem
varrer a árvore de `cache/` — que no share é uma caminhada cara.

O `apps/pages/duck_mirror.py` é o espelho: fila em memória + thread daemon. Quatro ganchos —
o funil `_atomic_write_json` (74 chamadores; o aviso fica no funil pela MESMA razão do
`bump_cache_gen`: o que ficasse de fora envelheceria o banco em silêncio), o `_b3_save`
(RefData), o `_cpd_save_list` (CounterpartyDetails) e o `write_holidays` da vertical (aviso
explícito: o nome do arquivo de calendário só o registro conhece). Três decisões que não são
detalhe:

- **assíncrono e fora do `_cache_lock`**: o funil roda com o lock global tomado, e DuckDB no
  share ali dentro é o "trabalho lento segurando o lock" que o §4 proíbe. O aviso só
  enfileira; quem converte é a thread;
- **melhor esforço de ponta a ponta**: o aviso nunca levanta para o chamador, e a conversão
  que falha fica no log — o manifest faz a próxima rodada reconverter o que ficou para trás
  (o mtime do JSON não casa mais). Arquivo AUSENTE virou `skipped`, não erro: o par RefData ×
  CounterpartyDetails nem sempre nasce junto;
- **os bancos moram ao lado do dado espelhado**: `Config.DATABASE_DIR` quando a raiz é a do
  app; `<raiz>/db` quando a raiz foi trocada — é o que faz os testes (que apontam
  `_B3_DATA_DIR` para tmp) espelharem no próprio tmp em vez de escrever num banco REAL.

Kill-switches: `OTC_DISABLE_DUCK_MIRROR=1` (só o espelho) e `OTC_DISABLE_SCHEDULERS=1` (o dos
testes que sobem o app — espelho é trabalho de fundo da instância, como os schedulers). O
`write_holidays` também ficou ATÔMICO no caminho: o navegador lê o arquivo por URL estática, e
um fetch no meio de um write não pode ver JSON pela metade.

`check_duck_mirror.py` prende o ciclo (funil → banco, regravação, os dois fora-do-funil,
calendário, o que NÃO dispara, a raiz do espelho, kill-switch e a prova de exceção);
`check_json_to_duckdb`, `check_holidays_api`, `check_holiday_calendars`, `check_cpd_api`,
`check_config_names` e `check_soc_layers` seguem verdes.

## §327 — o Print Advice do NDF Summary gerava só a página visível (2026-08-27)

Select-all + Print Advice no NDF Summary (Daily Settlement › NDF) gerava os avisos SÓ das
linhas da página visível — era preciso paginar e gerar de novo. Duas causas da mesma família
(§7, a armadilha do `rows({page:'all'})`): o select-all marcava os checkboxes NO DOM
(`$('tbody .ops-cb')` — só a página renderizada; o DataTables recria as células ao paginar), e
o coletor descartava linha sem nó (`node ? … : false`).

A regra agora: **select-all marcado = o conjunto FILTRADO inteiro** (`rows({search:'applied'})`,
lido pelos DADOS, não pelo DOM) — no Print Advice e no Delete, que compartilhavam o coletor.
Sem o select-all, valem os checkboxes marcados um a um. E desmarcar UMA linha desfaz o "todos",
senão o select-all seguiria valendo por cima da exclusão manual.

## §328 — fase 3 começou: leitura DB-first com contrato de FRESCOR (2026-08-27)

O flip de leitura, consumidor a consumidor. A peça central é o
`apps/pages/duck_read.py`: o leitor religado só usa o banco quando o `_manifest` dele
(caminho, mtime, tamanho — gravado pelo motor a cada conversão) prova que a tabela reflete o
JSON **como ele está agora** em disco. Qualquer outra situação — banco ausente, manifest
defasado (JSON editado por fora do app), arquivo em uso pelo espelho naquele instante —
devolve `None`: o chamador cai no JSON de sempre e o espelho é avisado para se curar. O flip
nunca pode ser a fonte de um dado velho; no pior caso ele é um caminho a mais que não
funcionou, e o comportamento é o de ontem. (As conexões são as cruas do DuckDB, como as do
espelho — a colisão intra-processo com o espelho escrevendo vira exceção capturada e
fallback, nunca fila.)

Dois pilotos religados:

- **RefData**: os três índices derivados do `routes.py` (`_refdata_triples`,
  `_refdata_by_spn`, `_refdata_by_taxid` — e com eles o `/api/reference-data/counterparties`)
  passaram a ler pelo `_refdata_records()`, que é DB-first. O cache por MTIME DO JSON deles
  ficou como estava de propósito: o mtime é exatamente a chave do contrato de frescor, então
  as duas fontes respondem à mesma pergunta.
- **Feriados**: `calendars()` (a tabela `_registry` — o motor passou a registrá-la no
  manifest, e a pular a reescrita quando o registro não mudou) e `load_holidays` (a tabela do
  calendário, com a data voltando como STRING ISO — a forma que o JSON sempre teve). O
  caminho JSON continua sendo quem SEMEIA: registro vindo do seed nem tem arquivo para o
  manifest provar.

Os leitores que FICARAM no JSON (recon_fxo, recon_payrec, otc_emails, electronic_inventory,
`_cpd_load` e todos os `fetch` de navegador) seguem corretos porque a escrita espelha o JSON
— e o `_cpd_load` tem um motivo para não ser religado tão cedo: o `_contacts_norm` decide
"contato legado" pela AUSÊNCIA de chave (`'appr' not in c`), e a tabela achata as chaves na
união das colunas — um record reconstruído do banco teria a chave com NULL onde o JSON não a
tinha, e todo contato viraria legado em silêncio. Flip ali exige antes tirar a semântica de
chave-ausente do domínio.

`check_duck_read.py` prende: a resposta vindo DO banco (provado adulterando a tabela), o
manifest defasado caindo no JSON com o espelho se curando sozinho, os dois pilotos de
feriados e o banco ausente/ilegível como fallback silencioso. As seis suítes que exercitam os
leitores religados (`check_sigcoll_api`, `check_ndf_advice`, `check_daily_metric_api`,
`check_weekly_escalation_api`, `check_ops_trade_swap`, `check_lp_counterparty_name`) seguem
verdes — nelas o tmp não tem banco, que é o fallback funcionando.

## §329 — o Mapping Intrag ID não alcançava o termo de MOEDAS (2026-08-27)

Na tela de Intrag NDF, o Mapping Intrag ID dizia "N operation(s) mapped" e o termo de moedas
continuava sem Intrag ID — sem erro nenhum. O filtro do CSV de retorno era IGUALDADE EXATA com
`'NDF - TERMO MERCADORIA'`, e a mesma tela envia DOIS contract types (`NDF - TERMO MERCADORIA`
e `NDF - TERMO DE MOEDAS`); o retorno ecoa o texto do instrumento enviado, então a linha de
moedas era descartada ANTES do casamento — o alerta contava só as de mercadoria.

O filtro virou PREFIXO de família (`startswith`, com o NDF passando `'NDF - TERMO'`): ele só
diz de que família a linha é; quem pareia de verdade é o **B3 ID**, exato e único — alargar o
filtro não tem como casar cruzado. OPCAO e SWAP ganham a mesma tolerância de graça (prefixo de
valor exato é o comportamento de antes). `check_intrag_api` §7 prende com um CSV de fixture:
mercadoria E moedas mapeadas e PERSISTIDAS com `Success`.

No mesmo dia: o `convert_json_to_duckdb_standalone.py` (fora do repo, entregue à mão) — a
versão AUTOCONTIDA do conversor para rodar numa máquina sem o código do app: caminhos
absolutos do share fixados, sem Config, sem import de `apps`; requisito único `pip install
duckdb`. O oficial continua sendo o `scripts/convert_json_to_duckdb.py` sobre o motor
`apps/pages/json_to_duckdb.py` — o standalone é uma cópia congelada para uso avulso, e quem
mudar o motor não o atualiza sozinho.

## §330 — a fonte de leitura virou o banco: o flip completo dos cadastros (2026-08-27)

O pedido: mudar a fonte de leitura para os DBs — mantendo as escritas nos JSONs para rollback
fácil. É exatamente o que o contrato de frescor permite: a escrita segue no JSON (com o
espelho realinhando o banco em seguida), a leitura é DB-first, e o rollback é reverter o
commit — nenhuma migração de volta, porque o JSON nunca deixou de ser escrito.

**A coluna `_raw`** (`convert_refdata`): cada registro de RefData/CounterpartyDetails vai
para a tabela também COMO ELE É — o texto JSON original — ao lado das colunas tipadas. É o
canal de fidelidade do flip: reconstruir pelo conjunto de colunas poria chave com NULL onde o
JSON não tinha chave nenhuma, e o `_contacts_norm` decide "contato legado" pela AUSÊNCIA
(§328). Com o `_raw`, o `_cpd_load` pôde ser religado — a migração one-shot dele roda igual
nas duas fontes. O manifest ganhou VERSÃO DE FORMATO na chave (`RefData.json#raw1`): banco no
formato antigo simplesmente não casa, cai no JSON e o espelho reconverte no novo — upgrade
automático, sem script.

**Leitores religados** (todos DB-first com fallback JSON): os que faltavam do RefData —
`_vcp_refdata_maps`, `_b3_load('refdata')` (a tela do Reference Data), `recon_fxo`,
`recon_payrec` (as duas pernas do net type), `otc_emails` (os dois índices),
`_ei_refdata_clients` — e o `_cpd_load` inteiro. E **o NAVEGADOR**: a rota
`static_data_file` serve `RefData.json`, `CounterpartyDetails.json` e os arquivos de
calendário DIRETO DO BANCO quando fresco — os fetch das telas mudaram de fonte sem uma linha
de JS; qualquer dúvida cai no arquivo.

**`expected_path` — o guarda da superfície de patch.** O check_cpd_api pegou na primeira
rodada: ele troca o `_cpd_path()` para um arquivo próprio, e o flip respondia pelo banco do
arquivo CANÔNICO — fonte errada com carimbo de fresca. Todo leitor com caminho próprio passa
ao `duck_read` o caminho DE QUE ELE LERIA (`expected_path`); se não for o canônico coberto
pelo espelho, o banco não responde e vale o arquivo — que é como o patch dos testes (e
qualquer config exótica) continua mandando.

O que segue no JSON: os ARQUIVO-DIA (as tabelas são tipadas e não reproduzem o payload cru;
o flip ali é por consumidor virar SQL — próxima frente) e os JSONs sem banco (mappings,
Subjacente, Dominio…). `check_duck_read` cobre o ciclo (18 asserções, com o CPD provando a
chave-ausente e o estático servindo do banco); a bateria — cpd, payrec, recon_fxo, ei,
ndf_advice, holidays, intrag, soc_layers, config_names — verde.

## §331 — cobertura TOTAL: todos os JSONs viram DuckDB (2026-08-27)

A fase seguinte da migração: o motor ganhou o `convert_datasets` — TODOS os JSONs do DATA_DIR
que ainda não tinham banco, na mesma ramificação por pasta que os arquivo-dia fixaram: a raiz
vira `static_data.db` (Subjacente, Dominio, VCP, SwapIndex, métricas…), `mappings/` →
`mappings.db` (os 43 cadastros, uma tabela cada), `file-interpreter/` → `file_interpreter.db`,
`translations/`, `control-panel/` e `tickets/` idem — pasta nova ganha o próprio banco
sozinha. Fica de fora o que TEM conversor próprio (RefData/CPD, o registro e os arquivos de
calendário — identificados pelo registro, senão seriam duas tabelas para o mesmo arquivo,
`cache/`) e a pasta `db/`.

Toda tabela lista-de-registros dos datasets leva a coluna **`_raw`** (o registro exato, como
no RefData §330) — é o que deixa o flip de leitura desses consumidores pronto para quando
chegar a vez deles; payload-objeto vira as tabelas das listas internas (também com `_raw`)
mais a `_meta`. O **espelho vivo** cobre tudo: o gancho genérico do funil passou a classificar
qualquer outro JSON do DATA_DIR como dataset — arquivo de calendário também cai ali pelo
funil, e é o motor (na thread) que o reconhece pelo registro e devolve como `ignored`.

Uma armadilha de eficiência pega no smoke: `sorted(os.walk(...))` consome o generator INTEIRO
antes de a poda de `dirs[:]` fazer efeito — a árvore de `cache/` era varrida à toa (no share,
uma caminhada cara) e o `ignored` saía com 116 itens em vez de 5. A ordem determinística vem
de ordenar in place, com a poda valendo.

Smoke na dev: 12 bancos, 193 conversões de datasets, segunda rodada em zero. O standalone do
§329 foi REGERADO do motor novo e reentregue (a cópia congelada agora cobre tudo). O que
resta da migração: o flip de leitura dos datasets (consumidor a consumidor, com o `_raw`
pronto) e dos arquivo-dia (por consumidor virar SQL).

## §332 — translations fica em JSON: os únicos fora da migração (2026-08-27)

Decisão da revisão do §331: os TRÊS JSONs de `translations/` ({en,br,es}.json) são os únicos
que permanecem como JSON — são os dicionários de i18n que o navegador consome no load
(`I18nManager`) e vivem versionados como código, não como dado da mesa. A pasta entrou no
`_DATASET_SKIP_DIRS` do motor, o `translations.db` que a primeira rodada da cobertura criou é
REMOVIDO pelo próprio conversor quando encontrado (mesma regra do `daily_caches.db` legado), e
o standalone foi regerado e reentregue. Todo o RESTO do DATA_DIR tem banco.

## §333 — o flip dos DATASETS: /mapping, cadastros B3 e o estático deles (2026-08-27)

A fase seguinte ao §331: a leitura dos datasets também virou DB-first. Três consumidores:

- **`_mapping_rows`** — o caminho de leitura de configuração mais quente do app (os 43
  cadastros, lidos pelos motores o tempo todo). O flip fica DENTRO do cache por mtime (o mtime
  é a chave do contrato de frescor), via `duck_read.dataset_records(path)` — o caminho ABSOLUTO
  de quem lê é o próprio guarda (`_MAPPINGS_DIR` trocado por teste → fora da raiz → JSON), e o
  `_raw` garante que o `upgrade` roda igual nas duas fontes. Os registros com `file` na raiz
  (SwapIndex) resolvem sozinhos para o `static_data.db`.
- **`_b3_load`** — os quatro que faltavam (Subjacente, VCP, Dominio, SwapIndex) pelo
  `static_data.db`; o caminho devolvido segue sendo o do JSON, que é onde o `_b3_save` grava.
- **o NAVEGADOR** — o `_duck_static_json` passou a servir também os JSONs de raiz cobertos
  pelos datasets e os `mappings/<arquivo>.json`; payload que não é lista fica com o arquivo
  (`dataset_records` devolve None), e subpasta fora dos mappings idem.

E a correção que tornou isso possível: **a reconstrução precisava de ORDEM garantida**. O
DuckDB não promete ordem de inserção no SELECT, e as telas exibem na ordem do arquivo — as
tabelas `_raw` ganharam a coluna **`_seq`** (posição no arquivo) e a leitura ordena por
`CAST("_seq" AS BIGINT)` (o CAST cobre o force_varchar dos cadastros, onde '10' < '2' por
texto). A versão de formato no manifest subiu para **`#raw2`** — e passou a valer para os
datasets também (`_dataset_manifest_key`): banco no formato de ontem não casa, cai no JSON e o
espelho reconverte sozinho. O standalone foi regerado no formato novo e reentregue.

`check_duck_read` §3d prende: a lista de 12 linhas voltando NA ORDEM (pega o '10'<'2'), o
`_mapping_rows` provado no banco por adulteração, o `_b3_load` DB-first com o caminho do JSON,
e o estático servindo mapping e cadastro de raiz. O que resta da migração: os ARQUIVO-DIA —
cada consumidor virar consulta SQL, começando pelo intervalo do Advanced Export.

## §334 — a última parte: os arquivo-dia lidos pelo banco (2026-08-27)

O fecho da migração de leitura. O flip é pelo FUNIL: o `_day_json` do
`platform/json_cache` — o daycache por (mtime, tamanho) que serve os leitores de arquivo-dia
do app — passou a tentar o `duck_read.day_payload(path)` no MISS do memo, antes do
`open()`. O memo continua sendo o cache; o banco só é consultado quando o arquivo mudou, e o
contrato de frescor é o mesmo de tudo (manifest × stat, com o espelho avisado no descompasso).

Para isso os arquivo-dia ganharam o que os cadastros já tinham: `raw=True` na conversão —
`_seq` (ordem) e `_raw` (o registro exato) em toda tabela de lista — e o manifest deles passou
para a chave versionada (`#raw2`): os `daily_*.db` de ontem não casam, caem no JSON e o
espelho os reconverte sozinho. O custo é o dobro de armazenamento nos bancos diários — que são
100% derivados e recriáveis; a fidelidade byte a byte do funil vale mais.

O que reconstrói é o payload-LISTA (a forma dos New Deals, Pending Confirmation, arquivos
B3…): o manifest diz que a conversão gerou UMA tabela e ela carrega `_raw`/`_seq`; dia vazio
volta `[]` (a tabela `_empty`). **Payload-objeto (as recons) fica com o JSON de propósito** —
ele vira sub-tabelas + `_meta` normalizadas, e remontar o objeto por elas seria adivinhar
chave e ordem. Os leitores que abrem o arquivo-dia DIRETO (o ramo de data exata de alguns
endpoints) seguem no JSON — mesma resposta, migração gradual.

`check_duck_read` §3e prende: a lista voltando DO BANCO na ordem (por adulteração do `_raw`),
o payload-objeto continuando no JSON (embrulhado em lista, como sempre) e o dia vazio; o
`check_daycache` — que prende o memo — segue verde, e a suíte completa também. O standalone
foi regerado no formato novo e reentregue.

Com isto o mapa fecha: escrita nos JSONs (rollback fácil) → espelho vivo → leitura DB-first
em cadastros, datasets, calendários, navegador E arquivo-dia. O que sobra em JSON por
decisão: `translations/` (§332), os payload-objeto das recons e os leitores de data exata.

## §335 — a varredura da migração: dois achados reais, os dois fechados (2026-08-27)

Auditoria completa da migração JSON → DuckDB (escritas × espelho × leituras × manifest), a
pedido. Dois achados de verdade:

**1. ~30 escritores de DATA_DIR fora do funil.** O censo de `json.dump` em `apps/pages` achou
a classe inteira: os caches das três recons, o histórico do Pay/Rec, os comentários da Recon
FXO, os tickets, o arquivo-dia do Operations B3, o overlay de status do settlement, o snapshot
do Pending Confirmation, o `VCP.json` do CETIP, os recipients do Control Panel (sete features)
e as edições in-place do New Deals — todos gravavam com `open`+`json.dump` direto, sem passar
pelo `_atomic_write_json`. A LEITURA nunca quebrou (o contrato de frescor derruba o banco
defasado para o JSON), mas os bancos ficavam VELHOS em silêncio para quem os consulta por fora
— até a próxima carga completa. Todos migraram para o funil, que é atômico e avisa o espelho
(vários ganharam atomicidade que não tinham; os que já faziam tmp+replace perderam a cópia
local da mesma lógica; o `otc_tickets` mantém o gravador próprio documentado e ganhou o
aviso). O `check_duck_writers.py` PRENDE a regra por varredura: `json.dump` em `apps/pages` só
na allowlist (o funil + os dois stores com aviso próprio) — o próximo write cru nasce
reprovado, com arquivo e linha.

**2. Feriados sem ordem garantida.** As tabelas de calendário e a `_registry` não tinham
`_seq`: a ordem do REGISTRO é a ordem das pills e do sorteio de cores da tela, e dois feriados
no MESMO dia têm de voltar como o JSON os guarda — o SELECT sem ordenação não promete nenhum
dos dois. O registro passou pelo `_com_raw` (o leitor remonta por `_seq`/`_raw`), as tabelas
de calendário ganharam a coluna `_seq` (com `ORDER BY CAST`), e os manifests de feriados
entraram na chave versionada (`#raw2`) — os bancos de ontem reconvertem sozinhos.

O que a varredura CONFIRMOU são (por construção e por teste): todos os leitores religados têm
frescor + fallback + guarda de patch; as chaves de manifest casam entre motor, espelho e
leitores; `.bak`/`.lock`/`_last`/`__pycache__` ficam fora; o estático cai para o empacotado
quando o arquivo não existe; e o seed da subida (`_seed_data_dir`, cópia sem aviso) converge
pelo heal-de-leitura ou pela carga. Suíte completa verde antes e depois; o standalone foi
regerado com o formato dos feriados.

## §336 — um banco por PRODUTO, um banco por JSON (2026-08-28)

A quebra dos bancos era GROSSA demais: um `daily_<rotina>.db` por primeiro nível de `cache/`
(com o produto virando schema lá dentro) e um `<pasta>.db` por pasta de dataset. Na prática o
`daily_new_deals.db` guardava termo, opção, swap e Intrag no mesmo arquivo, e o `mappings.db`
guardava os 42 cadastros. A pedido, a quebra desceu um nível — e nos dois casos ela agora
segue exatamente a ramificação que já existe no disco:

**Arquivo-dia: o caminho INTEIRO de `cache/` nomeia o banco.** `daily_new_deals_ndf_vanilla.db`,
`daily_new_deals_ndf_fwdstart.db`, `daily_new_deals_ndf_otherpublisher.db`,
`daily_new_deals_ndf_commodities.db`, `daily_new_deals_option_commodities.db`,
`daily_new_deals_option_fxo.db`, `daily_new_deals_intrag_ndf.db`,
`daily_new_deals_intrag_option.db`, `daily_b3_files_swap.db`, … Cada dia é uma tabela dentro
dele e o SCHEMA sumiu — o que era subárvore está no nome do banco, e um schema além disso
repetiria a mesma informação.

**Onde a rotina NÃO se ramifica em pastas, o produto sai do NOME do arquivo.** É o Daily
Settlement, que grava os dez arquivos do dia (`otm-settlement`, `ndf-cockpit`, `cognos`,
`br-onshore-settlements`, `latam-desk-position`, os dois `eventos-swap`, …) na MESMA pasta
`AAAA/MM/DD`: sem isso os dez cairiam num banco só, justamente a rotina em que a quebra é mais
útil. Vira `daily_settlement_otm.db`, `daily_settlement_ndf_cockpit.db`, … O corte é pela
CONTAGEM de pastas e nunca por olhar os vizinhos em disco — `_daily_rel_target` tem de ser
PURO sobre o caminho, porque o espelho vivo converte um arquivo por vez e não pode depender de
varrer o diretório.

**Datasets: um banco por ARQUIVO.** `mappings_mt300.db`, `control_panel_mt300_status.db`,
`file_interpreter_termo.db`, e o JSON de raiz com o próprio nome (`subjacente.db`, `vcp.db`).
São 133 bancos onde havia ~10, e isso de quebra tira uma contenção que não precisava existir:
o espelho reconvertendo UM mapping fechava a leitura dos outros 41.

Quatro detalhes que não dão erro nenhum:

- **A tag da TABELA é tudo-ou-nada.** Ela cai quando é pura repetição do nome do banco
  (`pending-confirmation_20260827` no `daily_pending_confirmation.db`; `otm-settlement_20260728`
  no `daily_settlement_otm.db`) e fica INTEIRA caso contrário. A primeira versão podava token a
  token, e aí o `DPOSICAO-SWAP` do `daily_b3_files_swap.db` perdia justamente o `swap` e ficava
  indistinguível de um `DPOSICAO` da mesma pasta — perda de dado sem erro nenhum.
- **A tag entra no nome do banco PODADA** dos tokens que a rotina já diz (`payrec` +
  `payrec_status` → `daily_payrec_status.db`), e o prefixo `daily_` não é acrescentado à rotina
  que já se chama `daily …` — senão o Daily Settlement sairia `daily_daily_settlement_otm.db`.
- **Os bancos dos desenhos anteriores são apagados na carga completa** (`_drop_legacy_dbs`),
  **menos o nome que ainda é alvo**: `daily_pending_confirmation.db` é o mesmo banco antes e
  depois (a rotina nunca se ramificou), com o mesmo manifest, e apagá-lo custaria uma
  reconversão inteira à toa. Quem faz a limpeza é a carga completa e não o espelho: o espelho
  enxerga um arquivo por vez e não tem como saber que um banco ficou órfão.
- **Colisão vira ERRO, não sobrescrita.** `_colisoes` denuncia dois arquivos que reivindiquem a
  mesma tabela — o caso teórico que a poda de nome deixa em aberto. Sem isso a segunda conversão
  sobrescreveria a primeira e o `_drop_targets` da rodada seguinte apagaria o que sobrou.

O `duck_read.day_payload` passou a receber o nome do banco pronto do `_daily_rel_target` (era
ele que recompunha por família), e a leitura DB-first continua intacta — o contrato de frescor
não mudou. Carga completa limpa: 133 bancos, 190 datasets + 114 arquivo-dia convertidos, zero
erro; segunda rodada não reconverte nada. Suíte completa verde.

## §337 — dois ajustes pedidos na mesma sessão (2026-08-28)

**`SWAP CORPORATE` × CEM entra no grupo do CEM Swap** (`conf_escalation/domain.FO_GROUPS`). Na
EDG os dois produtos são grupos SEPARADOS porque quem recebe cada um é diferente; na CEM é a
mesma mesa, então o grupo passou a listar os dois produtos. Antes o `SWAP CORPORATE · CEM` não
casava com grupo nenhum e caía no `unmatched` do card — cobrança que ninguém recebe, com a
linha âmbar na tela como único aviso. O teste que prendia o comportamento antigo foi invertido,
com a EDG continuando separada na mesma asserção.

**O card Update Contacts ganhou DROPZONE** no lugar do `<input type=file>` cru, reusando o
`.cp-dropzone` que o Daily Settlement já tinha na página. O helper novo (`cpWireDropzone`) é de
arquivo ÚNICO e mantém o **input como fonte da verdade** — o drop só o preenche, via
`DataTransfer` —, então o `cpRunUpload` segue lendo `input.files[0]` e nada mais mudou. Duas
coisas que não dão erro nenhum: `input.value = ''` NÃO dispara `change`, então o runner passou a
emitir o evento depois de um upload com sucesso (sem isso o dropzone continuaria mostrando o
arquivo já enviado), e o `DataTransfer` está num `try` — num browser sem ele o clique continua
funcionando. Chave `cp-contacts-dz` nos três idiomas.

## §338 — o SPB interbancário casava com cliente: a guarda de elegibilidade (2026-08-28)

Reportado da tela: um recebimento de **R$7,02 da Saint Gobain** apareceu
`Settled` contra uma linha **`SPB - outros bancos` de R$6,68**. O cliente não
tinha liquidado nada.

**A causa.** A liquidação interbancária capturada do `HistoricoMensagens` não
traz nome de contraparte nenhum — só o LTR, o status `Sucesso` e o valor —,
então ela é casada só por VALOR e com a tolerância larga que a tarifa
interbancária exige (±R$20, `_TOL_BANK`). Para R$7,02 essa janela é 285% do
próprio valor: ela casa com literalmente qualquer perna pequena do dia. O match
aconteceu no terceiro estágio do `_reconcile` e o status virou `Settled` na
linha que aceita a tolerância do próprio registro.

**Por que é pior do que uma linha errada.** A linha SPB nasce
`drop_if_unmatched` — é RUÍDO por construção e seria descartada em silêncio se
não casasse. Então o ruído roubou o par de uma liquidação de verdade e ainda a
carimbou como paga: sumiu justamente o alerta que a mesa precisava ver. Defeito
que se reporta como êxito.

**A correção não é tolerância, é ELEGIBILIDADE.** O outro lado de um
interbancário é um BANCO, e essa pergunta vem ANTES de qualquer tolerância
(`_match_allowed`, aplicado nos TRÊS estágios do match — o bucket exato
incluído, porque ali valores da mesma unidade inteira casam sem passar por
tolerância nenhuma). Quem responde "é banco?" é o cadastro **`bank-name`** do
/mapping, não um `if` no código.

Três coisas que não dão erro nenhum:

- **a comparação é por PALAVRA, nunca por substring.** O `_norm` cola o nome
  inteiro, e a primeira versão da guarda usava o núcleo do cadastro dentro do
  nome colado: o `brasil` do *Banco do Brasil* casou dentro de `SAINT GOBAIN DO
  BRASIL` e a função respondeu que TODA contraparte era banco — o teste pegou na
  hora. Daí o `_name_tokens`, que compara conjuntos de palavras;
- **`banco` é token significativo**, e não stopword: é ele que separa o `BANCO
  JOHN DEERE S/A` da John Deere montadora, que é cliente. O que se descarta são
  sufixos societários e conectivos (`sa`, `ltda`, `bm`, `do`…). Pela mesma razão
  a regra NÃO pode ser "tem a palavra banco no nome": Safra, Bradesco e
  Santander aparecem como clientes, e o `BOFA MERRILL LYNCH BM S/A` é banco sem
  a palavra;
- **a direção entra pela mesma porta.** Com ±R$20, dois valores pequenos de
  sinais OPOSTOS ficam dentro da janela — um Pay de −3,00 fechava com um Receive
  de +9,00. Um pagamento nunca é o par de um recebimento.

Banco fora do cadastro responde NÃO, e é o lado seguro do erro: a perna vira
`Pending` (falso alarme, que se vê) em vez de casar com o SPB errado (falso
`Settled`, que não se vê). **Hoje o `bank-name` tem 8 bancos e o Safra não está
lá**, embora o próprio comentário do `_cli_spb` o cite como contraparte
interbancária típica — cadastrar os que faltam em /mapping › Bank Name é ação de
mesa, vale no run seguinte sem restart.

`check_payrec_run.py` ganhou a seção da guarda (11 asserções): o caso reportado,
o mesmo com valor idêntico (o bucket exato), banco cadastrado continuando a
casar dentro da tarifa, a variante de grafia, o par John Deere banco × cliente,
a direção oposta, o banco não cadastrado e a liquidação normal do cliente, que
não passa pela guarda.

## §339 — o standalone deixa de ser cópia manual: um gerador (2026-08-28)

Perguntado na sessão: *"o standalone que será rodado por alguém que não tem
acesso ao config foi ajustado também com a segregação de bancos?"* — **não
tinha**. Ele estava no formato anterior (`_daily_db_name(familia)`,
`_tabela_dia(redundantes, …)`, um banco por pasta), e rodá-lo depois do §336
teria produzido o desenho VELHO ao lado do novo: dois formatos em disco, sem
erro nenhum, e nada dizendo qual é o de hoje.

O problema não é esta vez, é o padrão: o próprio §329 registrou que "quem mudar
o motor não o atualiza sozinho", e §331, §333 e §334 tiveram, cada um, a linha
"o standalone foi regerado e reentregue" — à mão, três vezes, e na quarta
passou. Uma cópia congelada de 855 linhas mantida por disciplina é uma cópia que
um dia diverge.

**Agora ele é GERADO**: `scripts/build_duckdb_standalone.py` monta o arquivo a
partir do cabeçalho/CLI próprios mais o corpo do `apps/pages/json_to_duckdb.py`
copiado por programa. Três guardas dentro do gerador:

- a **única** adaptação do corpo é o seed do registro de calendários (no app ele
  vem da vertical de feriados; sem `apps` não há de onde tirá-lo), e o gerador
  **falha** se esse trecho não for encontrado — mudou o ramo, alguém revê a
  adaptação em vez de gerar um arquivo silenciosamente errado;
- ele **recusa gerar** se sobrar qualquer outra referência a `apps` no corpo,
  imprimindo arquivo e linha: é assim que uma dependência nova do motor viraria
  `ImportError` na máquina de quem só tem `pip install duckdb`;
- o cabeçalho gerado diz, no próprio arquivo, que ele é gerado e não se edita à
  mão.

Regerado e validado rodando **de fora do repo**, contra o `static/data` da dev:
133 bancos, os MESMOS que o script oficial produz (`diff` das listagens vazio),
190 datasets + 114 arquivo-dia, zero erro, segunda rodada em zero, e a remoção
dos bancos legados funcionando — inclusive preservando o
`daily_pending_confirmation.db`, que continua sendo alvo. O corpo difere do
motor em exatamente 12 linhas, todas do seed adaptado.

O aviso ficou nos dois lugares onde a próxima pessoa olha: no docstring do
`json_to_duckdb.py` (⚠️ mexeu aqui, rode o gerador) e na tabela de scripts do
CLAUDE.md §9. O arquivo entregue continua fora do repo, de propósito —
versioná-lo seria criar a segunda cópia do motor que o gerador existe para
evitar.

## §340 — o standalone entra no repo, com o guarda que o mantém em dia (2026-08-28)

Pedido: versionar o standalone em `scripts/`, para entregá-lo junto com o código
a quem vai rodá-lo, em vez de mandar o arquivo à parte.

Feito — mas **versionar sozinho seria só mudar o lugar do problema do §339**: a
cópia continuaria envelhecendo em silêncio, agora com o agravante de parecer
oficial. Então ela entrou com três coisas:

1. **Gerada, nunca editada.** O `build_duckdb_standalone.py` passou a escrever
   direto em `scripts/convert_json_to_duckdb_standalone.py`, e o cabeçalho do
   arquivo gerado diz isso.
2. **`check_duckdb_standalone.py`**, o guarda. Ele regera em memória e cobra que
   o arquivo do repo seja BYTE A BYTE o que o gerador produz hoje — com o
   comando a rodar na própria mensagem de falha. Provado nos dois sentidos:
   mexendo no motor sem regerar, o teste sai 1 e imprime o diff; restaurado,
   volta a 0.
3. **O guarda prova mais do que a sincronia.** Que ele é mesmo autocontido
   (nenhum `apps`, nenhum `Config`, e a lista de imports é exatamente
   `argparse/datetime/duckdb/json/os/re/sys/traceback`); que o corpo é o do
   motor com a ÚNICA adaptação declarada aplicada — e essa comparação é EXATA
   contra a constante `SEED_APP`/`SEED_STANDALONE` do gerador, não uma
   heurística de palavras-chave, que aceitaria qualquer outra edição que
   "parecesse" do seed; e que ele CONVERTE de verdade, produzindo o mesmo
   desenho do script oficial (um banco por produto com o caminho de `cache/` no
   nome, o Daily Settlement quebrando pelo nome do arquivo, um banco por JSON,
   segunda rodada em zero).

A primeira versão do check 3 foi por palavras-chave e reprovou — o que foi bom:
mostrou que a asserção frágil era a própria asserção. Trocada pela igualdade
exata, ela passou a provar o que promete.

Suíte completa verde, agora com 102 scripts.

## §341 — o standalone repartido: nove scripts para rodar em paralelo (2026-08-28)

Pedido: além de versionar (§340), **repartir** o standalone — um script para os
JSONs únicos e um por bloco com quebra por dia — "para mais pessoas conseguirem
rodar, ou rodar mais de um ao mesmo tempo sem precisar esperar um terminar".

O motor ganhou ESCOPO, e é o motor que ganhou — não os scripts. `convert_daily`
passou a aceitar `familias` (restringe a rotinas de primeiro nível de `cache/`)
e `excluir` (o complemento). Repetir esse filtro em cada script gerado seria a
mesma regra em nove lugares. Junto veio o `cache_families()`, que é o eixo da
repartição e existe para o gerador e os scripts não terem cada um a sua lista.

Três decisões dentro do escopo:

- **a varredura desce só na fatia** (`os.walk` por família, não em `cache/`
  inteiro): no share, onde a caminhada é cara, é a diferença entre ler uma
  rotina e ler tudo;
- **a limpeza de bancos legados se restringe às famílias da fatia.** Sem isso,
  quem rodasse a fatia do New Deals apagaria o `daily_b3_files.db` que a pessoa
  ao lado estava convertendo naquele instante — desfazer a carga alheia no meio
  dela;
- **rotina pedida que não existe em disco vai para `ignored` com o motivo**, não
  é erro nem silêncio: a instância pode não ter aquele cache ainda.

`scripts/standalone/` tem **nove** arquivos: `00_completo` (tudo num comando),
`01_cadastros` (os JSONs únicos — feriados, RefData/CPD e um banco por JSON de
cadastro), seis `02_*` (uma rotina de `cache/` cada) e `99_outros` — a rede de
segurança que pega toda rotina sem arquivo próprio, para uma rotina NOVA nunca
ficar sem conversor enquanto ninguém regera nada.

A repartição é segura porque **os bancos são um por produto**: duas fatias nunca
escrevem no mesmo `.db`. Provado rodando SETE processos ao mesmo tempo contra o
`static/data` da dev — zero erro, 133 bancos, resultado idêntico ao da carga
sequencial e ao do script oficial do repo.

O guarda do §340 cresceu junto: além da sincronia byte a byte de cada um dos
nove com o gerador, ele cobra que a pasta tenha exatamente os arquivos gerados,
que todos sejam autocontidos (imports só da stdlib + duckdb) e — o que motiva a
repartição — que **a soma das fatias seja EXATAMENTE a carga completa**, com uma
rotina inventada caindo no `99_outros`. Duas asserções minhas nasceram erradas e
o teste as pegou: a rotina de UM nível de pasta leva a tag do arquivo no nome do
banco (`daily_rotina_nova_coisa.db`), e o `reference_data.db` faltava na lista
esperada dos cadastros.

`scripts/standalone/README.md` é o que a pessoa que recebe lê: a tabela dos
nove, o `pip install duckdb`, as flags, um exemplo de rodada em paralelo no
Windows, e o aviso de que os arquivos são gerados e não se editam à mão.

**Adendo do mesmo dia — o caminho padrão.** Os nove nasceram com o
`I:\Confirmation\...` fixo, que é como a MESA enxerga o share; a instância do
JPM fala com ele pelo UNC (`\\Nawest.ad.jpmorganchase.com\lac\BRA\intra`, o
bloco ENV:PROD do config). Fixar um só faria o script não achar nada em metade
das máquinas — e o sintoma seria "não converteu nada", não "caminho errado".
Hoje há uma LISTA de candidatos, tentada na ordem (UNC, depois a letra), valendo
o primeiro que existir; `--data-dir` continua mandando em qualquer caso, e a
primeira linha da saída diz qual caminho valeu, que é o que permite conferir
antes de deixar rodando.

## §342 — a pasta db/ espelha a árvore de origem (2026-08-28)

Reportado da instância: *"está sendo salvo tudo dentro da mesma pasta e ficando
mil dbs no mesmo lugar, ficando uma confusão"*. E estava mesmo: os 133 bancos
caíam soltos na raiz do `db/`, com o caminho ACHATADO no nome
(`daily_new_deals_ndf_vanilla.db`, `mappings_mt300.db`). Achar o banco de uma
tela virava caça ao nome, no meio dos bancos do próprio app.

Agora a pasta `db/` **espelha a árvore do `DATA_DIR`**: o caminho vira PASTA e o
último segmento vira o ARQUIVO.

    db/cache/new deals/NDF/Vanilla.db          db/mappings/mt300.db
    db/cache/new deals/Option/FXO.db           db/control-panel/mt300_status.db
    db/cache/b3 files/Swap.db                  db/file-interpreter/termo.db
    db/cache/daily settlement/otm-settlement.db
    db/cache/pending-confirmation.db           db/Subjacente.db  (raiz fica na raiz)

**Ano, mês e dia NÃO viram pasta** — eles já são a tabela `d_AAAAMMDD` dentro do
banco, que era o pedido explícito. E onde a rotina não se ramifica em pastas, a
TAG do arquivo vira o banco dentro da pasta da rotina (o Daily Settlement, dez
arquivos por dia na mesma pasta).

Cinco coisas que não dão erro nenhum e apareceram no caminho:

- **a tag perdia o separador da data.** `otm-settlement_20260728` sem a data
  deixa um `_` no fim, e o arquivo saía `otm-settlement_.db`. O `_sem_data`
  passou a aparar ` _-` das pontas;
- **a remoção de legados NÃO pode ser por varredura de `*.db`.** O
  `DATABASE_DIR` é a casa de TODOS os bancos do app — usuários, notificações,
  os três do Pending Confirmation, os dois da esteira, o do Onboarding —, e
  varrer ali apagaria dado que nada recria. Ela é por LISTA DE NOMES DERIVADOS,
  e o `_legacy_flat_name` reconstrói o nome achatado a partir do caminho novo
  (quem é tag e quem é rotina sai da PROFUNDIDADE, pela mesma regra que gerou o
  caminho);
- **o que decide a remoção é o ARQUIVO, não o nome.** O JSON de raiz passou a
  manter a caixa do original (`Subjacente.db`) e o legado dele era normalizado
  (`subjacente.db`): em macOS e Windows os dois nomes são o MESMO arquivo, e
  remover o "legado" apagaria o banco recém-criado — a leitura seguinte cairia
  no JSON sem ninguém entender por quê. No Linux são dois de verdade, e aí o
  antigo TEM de sair. `os.path.samefile` responde certo nos dois;
- **as conexões criam a subpasta** (`os.makedirs(os.path.dirname(db))`), nos
  dois conversores — antes só a raiz existia;
- **o `duck_read` monta o caminho com `*db_name.split('/')`** nos dois pontos:
  o alvo deixou de ser um nome e passou a ser um caminho relativo.

Migração de quem já tem o formato anterior: a carga completa move tudo sozinha —
125 legados removidos e 133 bancos na árvore nova, com a segunda rodada em zero.
Os nove standalone foram regerados e as fatias seguem somando exatamente a carga
completa, inclusive rodando SETE em paralelo. Suíte completa verde.

---

## §343 — a fatia do standalone não achava a rotina pela GRAFIA da pasta (2026-08-28)

`python 02_2_b3_files.py` na máquina de outra pessoa, apontado para o share do
JPM, terminou assim:

```
escopo : cache/b3 files (arquivo-dia)
== daily -> daily_<produto>.db (um por produto)
   convertidos: 0 | inalterados: 0 | fora deste conversor: 1
```

Nenhum erro, nenhum banco, e uma linha que se lê como "não havia nada a fazer".
Eram **duas** falhas, uma escondendo a outra.

**A causa.** `convert_daily` casava o escopo pedido com a pasta em disco por
string EXATA (`f in set(familias)`). O nome da pasta é escrito por quem criou a
árvore e as instâncias não concordam na grafia: a dev tem `b3 files` e o share
tem `B3 Files`. O `os.listdir` devolve o nome REAL — o Windows ser
case-insensitive para abrir o caminho não ajuda em nada aqui, porque a
comparação é entre strings, não entre arquivos. A rotina caía em "ausente em
disco" e a fatia inteira ficava de fora.

O estrago passava do script que a pessoa rodou. O `99_outros` exclui pela MESMA
lista, com a mesma comparação: sem reconhecer `B3 Files` como coberta, ele a
convertia junto — **dois scripts escrevendo no mesmo banco**, que é exatamente
o que a divisão em fatias promete não acontecer, e que só apareceria como
corrupção se as duas pessoas rodassem ao mesmo tempo.

Hoje o casamento é pelo nome NORMALIZADO (`chave_familia`, sobre o `_tokens`
que já normaliza caixa, acento e separador), nos dois sentidos — o `familias` e
o `excluir`. O banco herda a grafia que está em DISCO
(`db/cache/B3 Files/Swap.db`): a pasta espelha a origem, e é assim que quem sabe
onde está o JSON sabe onde está o banco.

**A segunda falha era o aviso.** A rotina ausente ia para `ignored`, que o
resumo só CONTA — e `ignored` é também onde caem os ponteiros `_last` e as
configs avulsas, coisas normais e numerosas. O `fora deste conversor: 1` era
indistinguível de rotina.

Agora existe `stats['avisos']`, que os dois impressores (o CLI do repo e o molde
do gerador) imprimem sempre, e ele diz o que ACHOU:

```
   ! cache/daily settlement: rotina ausente em disco.
     Rotinas encontradas: b3 files, new deals, payrec
```

Essa lista é o que resolve o caso na hora: se a pasta existe com outro nome, ela
está ali. `ignored` continua sendo contagem, que é o papel dele.

Guardas no `check_duckdb_standalone.py`: a fatia acha `B3 Files` pedindo
`b3 files`, o `99_outros` a reconhece como coberta e não duplica o banco, o
aviso de rotina ausente é impresso, e ele nomeia as rotinas encontradas. Os
nove standalone foram regerados (o `_DOC_ROTINA` ainda descrevia os nomes
achatados do desenho anterior — corrigido para a árvore espelhada). Suíte
completa verde.
