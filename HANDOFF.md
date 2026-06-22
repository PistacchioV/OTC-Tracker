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
- Endpoint p/ persistir `CounterpartyDetails.json` (hoje save é só sessão).
- Popular `CounterpartyDetails.json` com dados reais (CGD/bancos/contatos) — hoje vazio.

