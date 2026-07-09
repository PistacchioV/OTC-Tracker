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

There is **one blueprint** (`pages_blueprint`, defined in `apps/pages/__init__.py`) that owns all routes. All route logic lives in `apps/pages/routes.py`.

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

### Database

Two separate databases are in use:

- **DuckDB** (`Users_OTCTracker.db`): stores `users` and `verification_codes` tables. Connection is managed manually via `get_db_connection()` / `conn.close()` in every function. The path is currently hardcoded as a Windows absolute path in `apps/pages/routes.py:27` — this must be updated when running on a different machine.
- **SQLite** (`apps/db.sqlite3`): managed by Flask-SQLAlchemy. Currently unused by application logic but initialised by `configure_database()` on every request.

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

- `awmpy` is an internal JPMorgan library and is not available on PyPI. The app will fail at login/register if it is not installed in the environment.
- The `DB_PATH` for DuckDB is a hardcoded Windows path — it must be changed to the correct path for the current machine before the auth flow works.
- `flask_login`, `flask_wtf`, and `flask_migrate` are in `requirements.txt` but are not actively used in the current codebase; the app manages sessions and DB directly.
- SMTP delivery uses `mailhost.jpmchase.net` (internal relay, port 25, no auth) — email sending will silently fail outside the JPMorgan network.
