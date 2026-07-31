# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Python / Flask

```bash
# Activate the virtual environment (Python 3.11)
source .venv311/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Run in development mode (port 5000)
flask run

# Run on a specific port
flask run --port=8050

# Production (Gunicorn, binds to 0.0.0.0:5005)
gunicorn --config gunicorn-cfg.py run:app
```

Environment setup: copy `env.sample` to `.env` and set at minimum `FLASK_APP=run.py`. Debug mode is controlled by the `DEBUG` flag at the top of `run.py` (not the `.env` file).

### Frontend / Assets

```bash
# Install Node dependencies
npm install   # or: bun install

# Watch SCSS for changes (development)
npm run dev   # runs: gulp

# Compile SCSS to CSS (one-shot)
npm run build # runs: gulp build
```

Gulp compiles `apps/static/scss/**/*.scss` → `apps/static/css/` and copies third-party plugin assets from `node_modules` into `apps/static/plugins/`.

## Architecture

### Request lifecycle

`run.py` reads `DEBUG` → selects `DebugConfig` or `ProductionConfig` from `apps/config.py` → calls `create_app()` in `apps/__init__.py`. That factory registers Flask extensions, then auto-discovers blueprints by iterating the `apps = ('pages',)` tuple and importing `apps.<name>.routes`.

There is **one blueprint** (`pages_blueprint`, defined in `apps/pages/__init__.py`) that owns all routes. All route logic lives in `apps/pages/routes.py` (~24.2k lines). Alongside it, `apps/pages/` holds helper modules imported by the routes — no blueprints of their own:

- `athena_api.py` — client for the Athena `getTrades` API (Kerberos/ADFS SSO; see below)
- `confirmation_pdfs.py` — reportlab replicas of the Word confirmation documents. **FX Options is the exception and the pattern to follow for new documents**: `opcao_fx_pdf()` builds the PDF from the *rendered document HTML* (the same string that becomes the `.doc`) via `_WordHtmlToFlowables`, so the two outputs cannot drift apart — see HANDOFF §139.
- `otc_emails.py`, `webpush.py`, `forecast_charts.py`, `otc_boxscan.py`, `recon_payrec.py`, `recon_comitente.py`

### Authentication flow

Authentication is SID-based (internal JPMorgan employees), not username/password:

1. User submits their SID (format: 1 letter + 6 digits, e.g. `A123456`)
2. `awmpy.get_phonebook_data(sid)` fetches name, email, and job title from the internal phonebook
3. If the SID exists in the DB **and** the client IP matches the stored IP → session is set directly, user enters the app
4. Otherwise → a 6-digit code is generated, stored in `verification_codes` table, emailed via SMTP, and user is sent to the 2FA page
5. `/verify-2fa` validates the code (10-minute expiry) and sets `session['authenticated'] = True`

Session keys set after auth: `authenticated`, `user_sid`, `user_name`, `user_email`, `user_role`.

### Access control (roles + per-page/per-card)

Authorization lives in `apps/pages/routes.py` and is enforced in three layers (before_request, sidebar JS, notification feed):

- **Roles.** `user_role` comes from the DB (`ADMIN`, `BO`, `MO`, `FO`, `INSTITUTIONAL`, `HUB`). **Master** is a superuser pinned by SID (`_MASTER_SIDS`, currently `E930179`) — it is *not* a grantable DB role, so it can't be assigned through user management. `_session_is_master()` is SID-based; `_session_is_admin()` = role `ADMIN` **or** master. Only the master can change an admin's (or another master's) page access; only the master is exempt from every page restriction.
- **Per-page access.** Column `users.Page_Access` holds a JSON array of allowed sidebar URLs. Empty/absent = *unconfigured* = full access. `_load_nav_urls()` parses `partials/sidenav.html` for the set of controllable pages. `enforce_page_access` (before_request) redirects to `/dashboard` when a configured user hits a page not in their allowlist. `_ALWAYS_ALLOWED_PATHS` (dashboard, users-profile, page-access) is never restricted. Admins are enforced too *if the master configured them*; unconfigured users (incl. admins) keep full access.
- **Per-card access (Control Panel).** The Control Panel is card-gated: allowlist tokens `"/control-panel#<id>"` (registry `_CONTROL_PANEL_CARDS`) grant individual routine cards. The page opens if ≥1 card is granted (`_cp_page_allowed`); `enforce_control_panel_cards` (before_request) blocks each routine's API endpoint unless its card is granted (`_CP_ENDPOINT_CARD`). A legacy whole-page `/control-panel` grant implies all cards.
- **Admin UI.** `/page-access` (admin/master only) is the editor; `/api/page-access/<sid>` GET/POST persists the allowlist. The Page Access checklist is built client-side from the live sidebar DOM, grouped by full menu hierarchy, with Control Panel exploded into its own card section.

### Mappings (lookup tables edited in the UI, not in code)

**Never hardcode a new de-para (lookup table) in the code** — the user's standing rule is that anything
mappable must be registrable through the `/mapping` page. Add an entry to `_MAPPING_DEFS` in
`apps/pages/routes.py` instead (`key → {label, columns, seed[, file, upgrade]}`) and an item to the
`TYPES` array in `apps/templates/pages/mapping.html`.

- Files live in `apps/static/data/mappings/` (one JSON per mapping, versioned). `BaseMoeda.json` is there
  too (moved in `f789d02` — the old `apps/static/data/BaseMoeda.json` path is gone).
- `_mapping_rows(key)` seeds the file on first read and caches by mtime: **UI edits apply on the next
  request, no restart** (unlike `routes.py` changes, which do need a restart on the team instance).
- Seeds must carry **exactly** the values that were hardcoded, so behaviour is identical until someone
  edits the table.
- Generic API `/api/mappings/<key>` GET/POST. POST replaces the whole file. Values are **not trimmed** on
  purpose (trailing space in B3 codes like `'C '` is part of the code).
- Front-end consumers `fetch` the endpoint and keep the old literals as a fallback, so a failed fetch
  degrades to the previous behaviour.
- Optional per-mapping `upgrade` callable converts legacy row formats on read; optional per-column
  `autofill` (on a `select`) makes the modal fill another column from the rows already registered.

Current mappings: `currency-base`, `interbook-ndf`, `publisher-ndf`, `le-accronym`, `commodities-b3`,
`bank-name`, `fxo-conv-rate`, `swap-curves`. See HANDOFF §131–§133 for what each one feeds and the
traps (e.g. the PTAX row in `publisher-ndf` must stay without a match token). `fxo-conv-rate` feeds
the two Taxa de Conversão columns of the Asian FXO confirmation (Moeda Base → rate name + Venda /
Compra) and ships seeded only with USD → USD PTAX / Venda — an unregistered currency raises a panel
warning instead of printing blanks (HANDOFF §139).

### Database

Two separate databases are in use:

- **DuckDB** (`Users_OTCTracker.db`): stores `users` and `verification_codes` tables. Connection is managed manually via `get_db_connection()` / `conn.close()` in every function. `DB_PATH` is now a **relative** path (`apps/static/data/db/Users_OTCTracker.db`) resolved from the module dir — no longer a hardcoded Windows path, so it works cross-machine. If DuckDB refuses to open the DB after running under a different duckdb version (`INTERNAL Error … replaying WAL`), rename the stray `Users_OTCTracker.db.wal` aside; the main `.db` is intact.
- **SQLite** (`apps/db.sqlite3`): managed by Flask-SQLAlchemy. Currently unused by application logic; `configure_database()` calls `db.create_all()` **once at app startup** (not per request).

**Concurrency — the app serves several users from a single process, so this matters:**

- The users DuckDB is a **singleton connection behind a global lock** (`_duckdb_conn_lock`). `get_db_connection()` hands out a `_DuckDBHandle` that **holds that lock until `close()`**. Every caller must therefore be `conn = get_db_connection()` immediately followed by `try: … finally: conn.close()` — all 20 current callers are. Miss the `finally` and the lock is never released: the whole app hangs for **everyone**, not just the failing request.
- **Never do slow work while holding it** (network, SMTP, file scans, template rendering). `_push_notify` is the model: it reads the subscriber list, closes, and only then sends the HTTP pushes. The topbar polls notifications every 8 s per open tab, so that lock is taken constantly.
- Per-DB connections (pending-confirmation DuckDBs) are opened ad hoc with a retry/backoff loop and **must close in `finally`** — a leaked connection keeps DuckDB's write lock for the life of the process and takes the page down for all users.
- JSON caches (New Deals day files, mappings, MTM) are read-modify-write, so they need `with _cache_lock:` around the **whole** read → change → `_atomic_write_json` cycle; the atomic write alone only prevents corruption, not lost updates. `_cache_lock` is a plain `Lock` (**not reentrant**): never call a locking helper from inside a locked block.
- **Keep it single-process.** Production is waitress (`start-prod.bat`, default 4 threads) and `gunicorn-cfg.py` pins `workers = 1`. With more than one process the DuckDB singleton lock and `_cache_lock` protect nothing, the users DB fails to open in the second process, and each process starts its own API schedulers (duplicate pulls). Scale with threads, not workers.

### SQL injection

Reference: [`Docs/SQL_Injection_Prevention_Cheat_Sheet.md`](Docs/SQL_Injection_Prevention_Cheat_Sheet.md)
— the OWASP cheat sheet, vendored into the repo (CC BY-SA 3.0, provenance header at the top; re-download
it to update, don't hand-edit).

How it applies here — the codebase already follows the primary defense, and it must stay that way:

- **Every value that comes from a request, a session, a spreadsheet or an e-mail goes in as a `?`
  parameter**, never interpolated: `conn.execute("SELECT Page_Access FROM users WHERE SID = ?", [sid])`.
  DuckDB's `execute` takes the parameter list as its second argument; `executemany` for batches.
- The handful of `'...{}'.format(...)` queries are **DDL over code-owned identifiers** (`_PC_TABLE`,
  columns from `_PC_COLUMNS`) — table and column names can't be bound as parameters, which is the one
  case the cheat sheet allows string building for. Keep those lists as module constants: the moment a
  table or column name can come from a request, it needs allow-list validation against a fixed tuple
  (cheat sheet "Defense Option 3"), not escaping.
- Login is by SID from the internal phonebook, but the SID still reaches the DB as a bound parameter —
  don't "optimize" it into an f-string.

### Template inheritance

```
layouts/base.html          ← base HTML skeleton
  └── layouts/vertical.html or layouts/horizontal.html
        └── pages/*.html   ← individual page templates
```

Partials (sidebar, header, topbar) are included inside the layout files. The `segment` variable passed from routes is used in templates to highlight the active nav item.

### Adding a new page

1. Add a route in `apps/pages/routes.py` returning `render_template('pages/<name>.html', segment='<name>')`
2. Create the template in `apps/templates/pages/<name>.html` extending a layout
3. Optionally add page-specific SCSS in `apps/static/scss/` (Gulp picks up all `*.scss` files automatically)

### Key non-obvious details

- **Working branch is `visual-refresh`** (since 2026-07-26; `apple-design` was merged in and is retired). All commits and pushes go there — never assume `main`. See HANDOFF §109/§114 for the visual-refresh design rules (tokens `--vr-*`/`--ins-*`, never `--bs-*`; i18n with English defaults + `data-lang`).
- `awmpy` is an internal JPMorgan library and is not available on PyPI. The app will fail at login/register (phonebook lookup) if it is not installed. For **local dev off the JPM network**, a tiny `awmpy` stub in the venv lets the server boot — real SID login won't work, so use the `/dev-login` DEV BYPASS route instead (that block is stripped from `routes.py` before every commit; see HANDOFF).
- `DB_PATH` for DuckDB is a **relative** path resolved from the module dir (see Database section above) — no per-machine editing needed.
- **Local dev on macOS**: use `flask run --port=5005` — port 5000 is taken by the AirPlay Receiver (returns a 403 "AirTunes"). The venv here is Python 3.12 (`.venv311`); `duckdb` and `flask-minify` are required (both in `requirements.txt`).
- `flask_login`, `flask_wtf`, and `flask_migrate` are in `requirements.txt` but are not actively used in the current codebase; the app manages sessions and DB directly.
- SMTP delivery uses `mailhost.jpmchase.net` (internal relay, port 25, no auth) — email sending will silently fail outside the JPMorgan network.
- **Athena `getTrades` API** (`apps/pages/athena_api.py`): imports New Deals for NDF/FXO (manual button + in-app schedulers, NDF every 20 min, FXO hourly). Needs the JPM network — off-network the scheduler fails silently (repeated errors demoted to `debug`). `build_session()` sets `trust_env=False` on purpose: inheriting the corporate proxy is what caused `WinError 10061` on the team's Windows box. Kerberos SSO on Windows needs `requests-negotiate-sspi`, which is **commented out** in `requirements.txt` (Windows-only) — install it on the JPM instance.
- **The counterparty comes from the End Counterparty accronym, never from the SPN or the Settlement Location.** Two traps, both of which shipped wrong counterparties to production (HANDOFF §147/§148):
  - the API's **`SPN` carries the Legal Entity's SPN, not the counterparty's** (fix pending on the API team) — so it is not used as a lookup key; the SPN shown on screen comes from Reference Data. When the API is fixed, re-add it as a step between the accronym and the LE (noted in `_ndf_ref_by_accronym`'s docstring);
  - the **Settlement Location is *our* leg**, not the counterparty's. Feeding it into the counterparty lookup made a client resolve to Banco J.P. Morgan. The `le` argument of `_ndf_ref_by_accronym` must be the entity of the *counterparty's own accronym* (`_ndf_le_from_accronym(end_cp)`), which is `None` unless the counterparty is an internal JPM leg.
  Nothing matching = empty row + "Missing Counterparty" badge, which is the desired failure: it asks for registration instead of inventing a counterparty.
- **Scheduled jobs run on Brazil time, not the server's.** `_br_now()` (`zoneinfo` `America/Sao_Paulo`, falling back to a fixed `-03:00` when `tzdata` is missing — the Windows case) backs the 19:00/19:30 pending-action email and the 11:30 Pending Confirmation maintenance. `datetime.now()` is the server's local clock and silently fired them at the wrong hour. Because the instance is restarted several times a day, `_ndm_pending_catch_up()` also fires the day's already-passed slots at startup; the on-disk claim file is what keeps that from becoming a repeated e-mail.
- **reportlab** (confirmation PDFs and the NDF Summary settlement sheet) is imported **lazily**: without the lib the email goes out *without* the attachment instead of failing.
- **`Docs/` and `docs/` both exist in this repo** (21 tracked files under the capitalised one, 33 under the lowercase one — an artefact of a case-insensitive filesystem). Screenshots live under **lowercase `docs/sop-screenshots/`**, which is what `SOP_PROCESSAMENTO_OTC.md` and `GUIA_DO_USUARIO_OTC_TRACKER.md` reference. Since the on-disk directory is `Docs`, a plain `git add docs/...` records the path **capitalised** and the new files land in a different tree — invisible on macOS, broken images on Linux/Windows. Stage with `git -c core.ignorecase=false add docs/sop-screenshots/` and verify the casing in the index. Both documents are generated from their `.md` (the single source) by `scripts/build_sop_docx.py`, which takes the source file as an optional argument; see HANDOFF §155 for the screenshot-capture traps.
- **One-off migration scripts** live in `scripts/` and must be run once on the team instance after a pull — `update_pending_confirmation_dbs.py` and `update_pending_confirmation_bankers.py` (both idempotent). See HANDOFF §128.
- **The team instance runs with the reloader off**: after a `git pull` that touched `routes.py` or a template, Flask must be **restarted** or the old code keeps serving. Several "it's not working" reports traced back to this. Mapping table edits made in the UI are the exception — they apply on the next request.
- **`table.rows({search: 'none', page: 'all'})` is NOT "everything for the day".** It returns every row *loaded*, and the New Deals tables are frequently loaded from a server-side search (`/cache/search`, the filter chips in the top bar). Any action built by scanning the table therefore silently covers only the last search. The B3 return-file mapping was fixed by sending the **Reference Date** and letting the server build the list from the day file (`_generic_nd_mapping_candidates`, HANDOFF §152) — that also means the server persists to deals that are not on screen. The same limitation still applies to Opt FXO / Opt Commodities / NDF Commodities, which have their own mapping endpoints.
- **Inserting a column into the New Deals NDF pages touches 14 places** (header `<th>`, filter-row `<th>`, `COL_TO_JSON_FIELD`, `AMEND_FIELD_COLS`, `dealJsonToRow`, `ND_COL_KEYS`, hidden `columnDefs`, `columnLabels`, mass-edit options, `SF_COLS`, `SF_LABEL_TO_FIELD`, `extractRowDeal`, `rowDataToNdfDeal`, `rowMaker`). Stale indexes here have caused silent data corruption twice — see HANDOFF §132. The Maker column is reached through the `MAKER_COL_INDEX` constant; keep it that way.
