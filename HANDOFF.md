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
