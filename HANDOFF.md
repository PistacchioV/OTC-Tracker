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
