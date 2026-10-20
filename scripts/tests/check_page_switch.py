"""O custo de TROCAR DE PÁGINA na instância (mesa, 20/10/2026: "no ambiente do
JP está muito lenta a troca de páginas").

Na dev nada disto aparece: o código está no disco local e o Mac tem GPU. Na
instância o código roda do share e as máquinas do JPM desenham por software, e
cada troca de página pagava as duas coisas.

  1. SERVIDOR — a instância sobe pelo waitress COM o DebugConfig (o
     ProductionConfig exige cookie seguro e ela é HTTP). Por DEBUG, cada render
     conferia no disco a data de cada template (`TEMPLATES_AUTO_RELOAD`) e de
     cada asset (`asset_v`): ~17 `stat` por página, ~1 s a 50 ms cada pelo SMB.
     Agora isso é só do `flask run` da dev (`OTC_LIVE_RELOAD`), e este script
     MEDE: render quente na instância = zero idas ao disco de código;
  2. NAVEGADOR (cache) — estático com o token ATUAL (`?v=` = carimbo do arquivo)
     fica no cache sem revalidar; token escrito à mão segue revalidando (§170);
  3. NAVEGADOR (desenho) — no modo opaco (sem GPU) não há View Transition, a
     entrada é um esmaecer curto e o título não entra letra a letra; a refração
     do vidro só existe com GPU e é calculada no tempo ocioso; as traduções são
     baixadas uma vez por página (eram três). Medido com a CPU 6× mais lenta e
     sem GPU: quatro trocas no modo opaco de 6,6 s para 3,4 s;
  4. INITIATIVES — os modais esperam as listas da página (o Lead e o Icon
     abriam vazios no JP, onde a resposta leva segundos), e o calendário dentro
     de modal: grade inteira, meses legíveis, ano que se digita.
"""
import io
import os
import subprocess
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.mkdtemp(prefix='share-root-'))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
os.environ.pop('FLASK_RUN_FROM_CLI', None)          # como o waitress da instância

TMP = tempfile.mkdtemp(prefix='pageswitch-')
DB = os.path.join(TMP, 'Users_OTCTracker.db')
import duckdb                                              # noqa: E402
_c = duckdb.connect(DB)
_c.execute("""CREATE TABLE users (
        SID VARCHAR PRIMARY KEY, Name VARCHAR, Email VARCHAR,
        Role_Description VARCHAR, Position VARCHAR, Role VARCHAR,
        Status VARCHAR, IP_Address VARCHAR, Page_Access VARCHAR DEFAULT '')""")
_c.execute("INSERT INTO users (SID, Name, Email, Position, Role, Status) VALUES "
           "('A111111', 'Ana Lima', 'ana@jpmorgan.com', 'VP', 'BO', 'Active')")
_c.close()

import run                                                 # noqa: E402
from apps.pages import routes as R                         # noqa: E402
R.DB_PATH = DB

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '  (got %r, expected %r)' % (got, exp)))
    if not ok:
        fails.append(label)


def ler(*parts):
    return io.open(os.path.join(ROOT, *parts), encoding='utf-8').read()


app = run.app
c = app.test_client()
with c.session_transaction() as s:
    s.update(authenticated=True, user_sid='A111111', user_name='Ana Lima', user_email='ana@jpmorgan.com',
             user_role='BO', user_position='VP', session_ip='127.0.0.1')
ENV = {'REMOTE_ADDR': '127.0.0.1'}

# ── 1. Servidor ─────────────────────────────────────────────────────────────
print('=== 1. Render na instancia: zero idas ao disco de codigo ===')
check('  DEBUG como na instancia', bool(app.config.get('DEBUG')), True)
check('  sem recarga de template fora do flask run', app.config.get('TEMPLATES_AUTO_RELOAD'), False)
check('  OTC_LIVE_RELOAD desligado no waitress', app.config.get('OTC_LIVE_RELOAD'), False)

CODIGO = (os.path.join(ROOT, 'apps', 'templates'), os.path.join(ROOT, 'apps', 'static'))
_stat = os.stat
idas = []


def stat_contado(p, *a, **k):
    if not isinstance(p, int):
        s = os.fsdecode(os.fspath(p))
        if s.startswith(CODIGO):
            idas.append(s)
    return _stat(p, *a, **k)


for pagina in ('/initiatives', '/intraday-monitor'):
    r = c.get(pagina, environ_base=ENV)                    # aquece (memo do processo)
    check('  %s responde' % pagina, r.status_code, 200)
    del idas[:]
    os.stat = stat_contado
    try:
        r = c.get(pagina, environ_base=ENV)
    finally:
        os.stat = _stat
    check('  %s quente: idas ao disco de codigo' % pagina, idas, [])

# A dev continua vendo o template novo sem reiniciar: o `flask run` marca
# FLASK_RUN_FROM_CLI antes de importar o app.
saida = subprocess.run(
    [sys.executable, '-c', "import run; print(run.app.config['OTC_LIVE_RELOAD'], "
                           "run.app.config['TEMPLATES_AUTO_RELOAD'])"],
    cwd=ROOT, capture_output=True, text=True,
    env=dict(os.environ, FLASK_RUN_FROM_CLI='true')).stdout.strip().splitlines()
check('  flask run da dev: recarga ligada', saida[-1] if saida else '', 'True True')

# ── 2. Estático com token ───────────────────────────────────────────────────
print('=== 2. Estatico com o token atual fica no cache ===')
html = c.get('/initiatives', environ_base=ENV).get_data(as_text=True)
for rel in ('css/otc.css', 'js/otc.js', 'css/vendors.min.css', 'js/vendors.min.js'):
    tok = R._asset_v(rel)
    check('  %s sai com o token do arquivo' % rel, ('/static/%s?v=%s' % (rel, tok)) in html, True)
    cc = c.get('/static/%s?v=%s' % (rel, tok)).headers.get('Cache-Control', '')
    check('  %s com token atual: imutavel' % rel, 'immutable' in cc and 'max-age=31536000' in cc, True)
cc = c.get('/static/js/otc.js?v=20260101a').headers.get('Cache-Control', '')
check('  token escrito a mao segue revalidando', 'no-cache' in cc and 'immutable' not in cc, True)
cc = c.get('/static/js/otc.js').headers.get('Cache-Control', '')
check('  sem token segue revalidando', 'immutable' not in cc, True)

# ── 3. Desenho no navegador ─────────────────────────────────────────────────
print('=== 3. Modo opaco leve; refracao so com GPU; traducoes uma vez ===')
HEAD = ler('apps', 'templates', 'partials', 'head-css.html')
check('  View Transition pulada no modo opaco (saida e entrada)',
      HEAD.count("if (r.classList.contains('is-solid')) { e.viewTransition.skipTransition(); return; }"), 2)
SCSS = ler('apps', 'static', 'scss', 'otc.scss')
CSS = ler('apps', 'static', 'css', 'otc.css')
check('  entrada do modo opaco e um esmaecer sem cascata (scss)', ':root.is-solid .otc-enter {' in SCSS, True)
check('  ... e o otc.css compilado tem a regra', ':root.is-solid .otc-enter' in CSS, True)
JS = ler('apps', 'static', 'js', 'otc.js')
check('  refracao exige GPU', "!/Firefox\\//.test(ua) && !weakGpu();" in JS, True)
check('  refracao no tempo ocioso, em fatias', 'lgIdle(lgScan);' in JS and 'function lgRun(dl)' in JS, True)
check('  titulo parado no modo opaco', "if (REDUCED_MOTION || root.classList.contains('is-solid')) return;" in JS, True)
check('  cascata das placas em ate 6 degraus', "Math.min(i++, 6)" in JS, True)
check('  traducoes: a PROMESSA fica no cache', "this._cache[l] = fetch(this.langPath + l + '.json')" in JS, True)

# ── 4. Initiatives ──────────────────────────────────────────────────────────
print('=== 4. Initiatives: modais esperam as listas; calendario no modal ===')
PC = ler('apps', 'static', 'js', 'pages', 'projects-common.js')
for chave, fn in (('project', 'openProjectModal'), ('task', 'openTaskModal'), ('drawer', 'openTaskDrawer')):
    check('  %s espera as listas' % fn,
          "if (afterMeta('%s', function () { %s(opts); })) return;" % (chave, fn) in PC, True)
for pagina in ('projects.js', 'project-detail.js', 'tasks.js', 'user-home.js'):
    check('  %s libera os modais quando a carga falha' % pagina,
          'P.metaFailed()' in ler('apps', 'static', 'js', 'pages', pagina), True)
check('  calendario com o respiro POR FORA da grade', 'box-sizing: content-box;' in SCSS.split('// flatpickr', 1)[1][:900], True)
check('  meses da lista nativa com fundo solido',
      '.flatpickr-monthDropdown-months option { background-color: var(--otc-menu-bg) !important;' in SCSS, True)
check('  foco no calendario nao volta ao modal',
      "t.closest('.flatpickr-calendar, .daterangepicker') && doc.querySelector('.modal.show')) e.stopImmediatePropagation();" in JS, True)
check('  Escape fecha so o menu do select', "e.preventDefault(); e.stopPropagation(); } return; }" in JS, True)

print()
if fails:
    print('FALHOU (%d):' % len(fails))
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('TUDO OK')
