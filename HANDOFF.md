# Handoff: About Page + Correções de Navegação e UI — OTC Tracker

**Data:** 2026-06-11  
**Status:** Em andamento

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
