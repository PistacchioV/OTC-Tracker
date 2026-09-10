# -*- coding: utf-8 -*-
"""O armazém de dados do app: o `DATA_DIR` como um sistema de arquivos VIRTUAL
sobre os DuckDB — leitura e escrita SÓ nos bancos (09/09/2026, HANDOFF §434).

Até aqui a escrita ia para o JSON e um espelho (`duck_mirror`) reconvertia
para o banco numa thread de fundo; a leitura era DB-only com o JSON como
emergência. O pedido foi tirar o espelho: **escrita e leitura apenas nos
bancos**. Este módulo é onde isso mora, e a forma dele é a de um sistema de
arquivos porque é assim que o resto do app fala — em CAMINHOS de JSON sob o
`DATA_DIR` (`jp`, `fpath`, `fp`). Trocar `open(fp) + json.load` por
`read_json(fp)`, `os.path.isfile(jp)` por `isfile(jp)`, `os.walk(raiz)` por
`walk(raiz)` é uma troca de vocabulário, não de desenho, e os cento e tantos
pontos que leem dado ficam mecânicos.

Três regras que sustentam isso:

- **o banco continua o de sempre.** Mesma quebra por produto (`db/` espelha a
  árvore de origem), mesmas tabelas com `_seq`/`_raw`, mesmo `_manifest`. Quem
  diz que banco e tabela um caminho ocupa é o `target_of` do motor — o mesmo
  que a importação de JSON legado usa, então banco importado e banco gravado
  pela tela têm uma forma só. Nada do que a instância já tem precisa migrar;
  o que falta nela (o payload-objeto sem `__raw`, o histórico anterior à
  janela de doze meses) entra pela importação (`scripts/convert_json_to_duckdb.py
  --meses 0`) ou, para o arquivo que ainda estiver no disco, pela importação
  PREGUIÇOSA: a primeira leitura de um caminho que o banco não tem e o disco
  tem grava o arquivo no banco e responde por ele. Enumerar (`listdir`/`walk`/
  `day_files`) é só pelo banco.
- **caminho fora do `DATA_DIR` é disco de verdade.** O share dos documentos,
  os uploads e os anexos não passam por aqui: as funções abaixo caem em `os.*`
  para o que não é `.json` sob a raiz de dados (e para `translations/`, que
  é código versionado, e `db/`, que são os próprios bancos). É o que torna a
  troca segura mesmo onde o chamador não sabe de onde o caminho veio.
- **a cópia empacotada continua sendo do `data_path()`.** O JSON versionado
  no repositório (`anbima.json`, `Subjacente.json`, as seeds dos cadastros)
  é importado para o banco na subida (`_seed_data_dir`); antes disso, quem
  pede por `data_path()` recebe o caminho do repositório e o lê do disco,
  como sempre. O armazém em si nunca cai para o pacote: um leitor com
  caminho explícito lê o que pediu, ou nada — é o que deixa um teste com a
  raiz num tmp ler só o que ele mesmo gravou.

O que se paga por isso, e onde: a gravação passa a reconstruir a tabela
DENTRO do request, sob a trava exclusiva do arquivo — no share são os
segundos que o espelho pagava em background. A leitura tem o memo de
PROCESSO por (caminho, mtime, tamanho) de sempre, validado pelo `stat` do
PRÓPRIO `.db` (o DuckDB reescreve o arquivo no checkpoint, então o mtime dele
é o "mudou?" que o mtime do JSON era antes); banco OCUPADO por outra
instância serve a última cópia boa em memória, e sem cópia levanta
`BancoOcupado` — não há mais JSON para cair.
"""
import json
import logging
import os
import tempfile
import threading
import time
import traceback

from apps.pages import database_access as _DA
from apps.pages import json_to_duckdb as core
from apps.pages.database_access import db_gate, duckdb_read, duckdb_write

log = logging.getLogger('otc_tracker')

AUSENTE = core.AUSENTE
_SKIP_TOP = ('db', 'duckdb', 'translations')


class BancoOcupado(IOError):
    """O banco está com outra instância (trava exclusiva) e não há cópia boa em
    memória. É `IOError` de propósito: os `except (IOError, ...)` dos leitores
    tratam como arquivo que não deu para ler, que é o que é."""


# ── raízes ───────────────────────────────────────────────────────────────────

def data_root():
    """A raiz de dados — `routes._B3_DATA_DIR`, que é a superfície que os
    testes trocam; antes de o routes existir, o `Config.DATA_DIR`."""
    try:
        from apps.pages import routes
        return os.path.normpath(str(routes._B3_DATA_DIR))
    except Exception:                                       # noqa: BLE001
        from apps.config import Config
        return os.path.normpath(Config.DATA_DIR)


def db_root(raiz=None):
    """Onde os bancos moram: `Config.DATABASE_DIR` para a raiz do app, e
    `<raiz>/db` para uma raiz trocada (os testes apontam a raiz para um tmp e
    os bancos têm de nascer dentro dele)."""
    from apps.config import Config
    raiz = os.path.normpath(raiz or data_root())
    if raiz == os.path.normpath(Config.DATA_DIR):
        return Config.DATABASE_DIR
    return os.path.join(raiz, 'db')


def rel_of(path, raiz=None):
    """O caminho relativo à raiz de dados, com `/`, ou `None` fora dela."""
    raiz = raiz or data_root()
    try:
        rel = os.path.relpath(os.path.normpath(os.path.abspath(str(path))), raiz)
    except ValueError:                                      # outra unidade (Windows)
        return None
    if rel == '.' or rel.startswith('..'):
        return None
    return rel.replace(os.sep, '/')


def managed(path):
    """Este caminho vive no banco? `.json` sob a raiz de dados, fora de `db/`
    e `translations/`."""
    rel = rel_of(path)
    return bool(rel) and rel.endswith('.json') and rel.split('/', 1)[0] not in _SKIP_TOP


def _managed_dir(path):
    """Um DIRETÓRIO sob a raiz (ou a própria raiz), fora de `db/`/`translations/`."""
    raiz = data_root()
    alvo = os.path.normpath(os.path.abspath(str(path)))
    # `normcase`: no Windows da instância a raiz chega em qualquer caixa
    # (`I:\OTC` × `i:\otc`), e o `relpath` já compara sem caixa.
    if os.path.normcase(alvo) == os.path.normcase(raiz):
        return ''
    rel = rel_of(alvo, raiz)
    if rel is None or rel.split('/', 1)[0] in _SKIP_TOP:
        return None
    return rel


# ── o registro de calendários (quem diz o que é arquivo de calendário) ───────
_cal_lock = threading.Lock()
_cal_memo = {'at': 0.0, 'map': None}
_CAL_TTL = 60.0


def _cal_files():
    """`{arquivo.lower(): nome}` do registro de calendários — do banco; sem
    banco, do seed da vertical de feriados (o registro é gitignorado e nasce
    do seed na instância que nunca abriu a tela)."""
    with _cal_lock:
        m = _cal_memo
        if m['map'] is not None and time.monotonic() - m['at'] < _CAL_TTL:
            return m['map']
    rows = None
    try:
        rows = _read_target(core.REGISTRY_FILE,
                            ('holiday_calendars.db', 'main', '_registry', core.KIND_REGISTRY),
                            default=None)
    except Exception:                                       # noqa: BLE001
        rows = None
    if rows is None:
        try:
            from apps.pages.features.holidays import domain
            rows = [dict(r) for r in domain.CAL_SEED]
        except Exception:                                   # noqa: BLE001
            rows = []
    mapa = {}
    for r in rows or []:
        if isinstance(r, dict):
            arq = str(r.get('file', '') or '').strip().lower()
            if arq:
                mapa[arq] = str(r.get('name', '') or '').strip()
    with _cal_lock:
        _cal_memo['at'] = time.monotonic()
        _cal_memo['map'] = mapa
    return mapa


def _cal_forget():
    with _cal_lock:
        _cal_memo['map'] = None


def target(rel):
    return core.target_of(rel, _cal_files())


def _alvos(rel):
    """O alvo do caminho e, para um `.json` de RAIZ, o alvo ALTERNATIVO: o
    arquivo de calendário é classificado pelo registro, e o registro pode ter
    ganhado a linha DEPOIS de o arquivo ser gravado (a tela cria o calendário
    gravando os dois) — ou perdido. Quem lê tenta o principal e, sem entrada,
    o outro; quem grava apaga o outro."""
    principal = target(rel)
    if principal is None or '/' in rel:
        return [principal] if principal else []
    if principal[3] == core.KIND_CALENDAR:
        alt = core.target_of(rel, {})
    else:
        cal = _cal_files()
        alt = core.target_of(rel, cal) if rel.lower() in cal else None
        if alt is not None and alt[3] != core.KIND_CALENDAR:
            alt = None
    return [principal] + ([alt] if alt and alt != principal else [])


def _db_abs(db_rel, raiz=None):
    return os.path.join(db_root(raiz), *db_rel.split('/'))


# ── os memos ─────────────────────────────────────────────────────────────────
# `_mcache`: o manifest de cada banco, validado pelo stat do `.db`.
# `_pmemo`: o canal cru de cada caminho por (rel, mtime, fsize), com teto em
# bytes e LRU — o gêmeo do `_day_memo` que o `duck_read` tinha.
_mlock = threading.Lock()
_mcache = {}
try:
    _PMEMO_MAX = int(float(os.getenv('OTC_DUCK_DAY_MEMO_MB', '256') or 0) * 1024 * 1024)
except ValueError:
    _PMEMO_MAX = 256 * 1024 * 1024
_plock = threading.Lock()
_pmemo = {}
_pbytes = {'n': 0}
_MISS = object()


def _tamanho(crus):
    forma, dados = crus
    if forma == 'list':
        return sum(len(c) for c in dados)
    if forma == 'obj':
        return len(dados or '')
    return 64 * len(dados)


def _pmemo_get(chave):
    if not _PMEMO_MAX:
        return _MISS
    with _plock:
        if chave not in _pmemo:
            return _MISS
        crus = _pmemo.pop(chave)
        _pmemo[chave] = crus
        return crus


def _pmemo_last(rel):
    """A última cópia boa de um caminho, QUALQUER versão — para o banco ocupado."""
    with _plock:
        for k in reversed(list(_pmemo)):
            if k[0] == rel:
                return _pmemo[k]
    return _MISS


def _pmemo_last_key(rel):
    """A chave `(rel, mtime, fsize)` da última cópia boa — o `stat` do ocupado."""
    with _plock:
        for k in reversed(list(_pmemo)):
            if k[0] == rel:
                return k
    return _MISS


def _pmemo_put(chave, crus):
    if not _PMEMO_MAX:
        return
    tam = _tamanho(crus)
    if tam > _PMEMO_MAX:
        return
    with _plock:
        antigo = _pmemo.pop(chave, None)
        if antigo is not None:
            _pbytes['n'] -= _tamanho(antigo)
        while _pmemo and _pbytes['n'] + tam > _PMEMO_MAX:
            k, velho = next(iter(_pmemo.items()))
            del _pmemo[k]
            _pbytes['n'] -= _tamanho(velho)
        _pmemo[chave] = crus
        _pbytes['n'] += tam


def memo_forget(path=None):
    """Esquece o canal de um caminho (todas as versões) ou de tudo."""
    with _plock:
        if path is None:
            _pmemo.clear()
            _pbytes['n'] = 0
            return
        rel = rel_of(path)
        for k in [k for k in _pmemo if k[0] == rel]:
            _pbytes['n'] -= _tamanho(_pmemo.pop(k))


def _req_store(nome):
    try:
        from flask import g, has_app_context
        if has_app_context():
            return g.setdefault(nome, {})
    except Exception:                                       # noqa: BLE001
        pass
    return None


def _db_stat(db):
    """`os.stat` do `.db`, memoizado por REQUEST — é o "mudou?" de cada banco."""
    store = _req_store('_store_dbstat')
    if store is not None and db in store:
        return store[db]
    try:
        st = os.stat(db)
        val = (st.st_mtime, st.st_size)
    except OSError:
        val = None
    if store is not None:
        store[db] = val
    return val


def _forget_db(db):
    with _mlock:
        _mcache.pop(db, None)
    store = _req_store('_store_dbstat')
    if store is not None:
        store.pop(db, None)


# ── OCUPADO: a disputa entre instâncias ─────────────────────────────────────
# Os tetos são do SHARE, não da dev: lá uma gravação legítima da instância
# vizinha (a semeadura da subida, um dia grande, a importação em lote) segura
# a trava exclusiva por dezenas de segundos, e um leitor que desiste em 5 s
# lia isso como OCUPADO — na subida, era a semeadura inteira falhando com
# traceback (10/09/2026). Vinte segundos por tentativa, uma de intervalo.
try:
    _LEITURA_TETO = float(os.getenv('OTC_DUCK_READ_LOCK_SECONDS', '20') or 0) or None
except ValueError:
    _LEITURA_TETO = 20.0
try:
    _OCUPADO_JANELA = float(os.getenv('OTC_DUCK_BUSY_SKIP_SECONDS', '60') or 0)
except ValueError:
    _OCUPADO_JANELA = 60.0
_OCUPADO_ESPERA = 1.0
_AVISO_JANELA = 600.0
_GATE_READ_WAIT_SECONDS = 20.0            # o mesmo fôlego do teto: a gravação deste processo no share
_olock = threading.Lock()
_ocupado_ate = {}
_ocupado_aviso = {'ate': 0.0}


def _ocupado_marcado(db):
    if not _OCUPADO_JANELA:
        return False
    with _olock:
        return time.monotonic() < _ocupado_ate.get(db, 0.0)


def _ocupado_marca(db):
    if _OCUPADO_JANELA:
        with _olock:
            _ocupado_ate[db] = time.monotonic() + _OCUPADO_JANELA


def _ocupado_limpa(db):
    with _olock:
        _ocupado_ate.pop(db, None)


def ocupado_forget(db=None):
    with _olock:
        if db is None:
            _ocupado_ate.clear()
        else:
            _ocupado_ate.pop(db, None)


def _ocupado_avisa(db):
    with _olock:
        agora = time.monotonic()
        if agora < _ocupado_aviso['ate']:
            return
        _ocupado_aviso['ate'] = agora + _AVISO_JANELA
    log.warning('[data-store] %s está OCUPADO (outro processo com a trava exclusiva) — '
                'servindo a última cópia em memória quando há; sem ela a leitura '
                'falha (teto da espera em OTC_DUCK_READ_LOCK_SECONDS)',
                os.path.basename(str(db)))


def _le_ocupado(fn, db):
    """`fn()` com UMA retentativa curta na disputa; marca/limpa o memo de
    OCUPADO. Levanta a exceção da disputa quando ela persiste."""
    if _ocupado_marcado(db):
        raise BancoOcupado(db)
    try:
        return fn()
    except Exception as exc:                                # noqa: BLE001
        if not _DA.is_file_in_use(exc):
            raise
    time.sleep(_OCUPADO_ESPERA)
    try:
        out = fn()
    except Exception as exc:                                # noqa: BLE001
        if _DA.is_file_in_use(exc):
            _ocupado_marca(db)
            _ocupado_avisa(db)
            _DA.trace_note('ocupado', os.path.basename(db))
            raise BancoOcupado(db) from exc
        raise
    _ocupado_limpa(db)
    return out


def _com_leitura(db, fn):
    """Abre `db` em LEITURA pela camada (portão em memória + permit + trava
    COMPARTILHADA de arquivo) com o teto curto, e roda `fn(con)`.

    O portão (`db_gate`) é o que dá PREFERÊNCIA ao escritor dentro do
    processo: um `duckdb_write` DECLARA a escrita antes de pedir a trava de
    arquivo, os leitores novos param aqui (teto `_GATE_READ_WAIT_SECONDS`),
    os em voo terminam, e a trava exclusiva vem sem disputa. Sem isso, oito
    leitores em laço (o aquecimento dos Summaries lendo um produto) seguram
    a trava compartilhada quase o tempo todo e a exclusiva, pedida por
    tentativa, não entra: uma gravação levava 9-12 s. A ordem importa e é
    a mesma nos dois lados — portão, depois trava de arquivo: o escritor
    que pegava a trava ANTES de esperar o portão fechava um ciclo com o
    leitor que entrava no portão antes de pedir a trava, e só o timeout
    desfazia. Medido no estresse de 10/09/2026."""
    def _uma():
        gate = db_gate(db)
        gate.enter_read(_GATE_READ_WAIT_SECONDS)
        try:
            with _DA.read_timeout(_LEITURA_TETO), duckdb_read(db) as con:
                return fn(con)
        finally:
            gate.exit_read()
    return _le_ocupado(_uma, db)


# ── manifest por banco ───────────────────────────────────────────────────────

def _manifest_rows_ro(con):
    try:
        return core.manifest_rows(con)
    except Exception as exc:                                # noqa: BLE001
        if 'manifest' in str(exc).lower():
            return {}                                       # banco sem manifest ainda
        raise


def _manifest(db, strict=False):
    """`{rel: (mtime, fsize, targets)}` do banco — em cache enquanto o `.db`
    não muda. Banco ausente → `{}`. Banco OCUPADO → o último manifest
    conhecido; sem nenhum, `{}` para quem só pergunta (existe? lista?) e
    `BancoOcupado` para quem vai LER (`strict`): ocupado não pode parecer
    "não há dado"."""
    st = _db_stat(db)
    if st is None:
        return {}
    with _mlock:
        ent = _mcache.get(db)
        if ent and ent[0] == st:
            return ent[1]
    try:
        rows = _com_leitura(db, _manifest_rows_ro)
    except BancoOcupado:
        if ent:
            return ent[1]
        if strict:
            raise
        return {}
    except Exception:                                       # noqa: BLE001
        log.debug('[data-store] manifest ilegível em %s:\n%s', db, traceback.format_exc())
        return ent[1] if ent else {}
    with _mlock:
        _mcache[db] = (st, rows)
    return rows


def _dbs_under(rel_dir):
    """Os bancos que podem ter caminhos sob `rel_dir` (`''` = a raiz): a pasta
    `db/` espelha a árvore, então é a pasta correspondente, recursiva — e, na
    raiz, também os bancos de primeiro nível (RefData, calendários, datasets
    de raiz)."""
    base = db_root()
    pasta = os.path.join(base, *rel_dir.split('/')) if rel_dir else base
    out = []
    # o banco de um ANCESTRAL guarda os caminhos das subpastas (o `.db` do
    # produto tem os dias de `AAAA/MM`), então cada prefixo do caminho conta
    partes = rel_dir.split('/') if rel_dir else []
    for i in range(1, len(partes) + 1):
        cand = os.path.join(base, *partes[:i]) + '.db'
        if os.path.isfile(cand):
            out.append(cand)
    if os.path.isdir(pasta):
        pilha = [pasta]
        while pilha:
            atual = pilha.pop()
            try:
                with os.scandir(atual) as it:
                    for e in it:
                        if e.is_dir():
                            pilha.append(e.path)
                        elif e.name.endswith('.db'):
                            out.append(e.path)
            except OSError:
                continue
    return sorted(set(out))


def _entries_under(rel_dir):
    """`{rel: (mtime, fsize)}` de todos os caminhos sob `rel_dir`."""
    prefixo = (rel_dir + '/') if rel_dir else ''
    out = {}
    for db in _dbs_under(rel_dir):
        for rel, (mt, fs, _tg) in _manifest(db).items():
            if rel.startswith(prefixo):
                out[rel] = (mt, fs)
    return out


# ── leitura ──────────────────────────────────────────────────────────────────

def _read_fs(path, default=AUSENTE):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except FileNotFoundError:
        if default is AUSENTE:
            raise
        return default


def _read_fs_text(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


# ── a importação do legado, FORA do request ─────────────────────────────────
# A primeira leitura de um caminho que o banco não tem e o disco tem serve o
# ARQUIVO na hora e manda a importação para uma thread. Antes ela rodava no
# próprio request, sob a trava exclusiva: um DPOSICAO-TER de milhares de
# linhas no share são dezenas de segundos — quem clicou esperava tudo isso, e
# quem lia o mesmo banco enquanto isso (o aquecimento do Summary, a instância
# vizinha) estourava o teto e caía em OCUPADO (10/09/2026). A thread recebe o
# TEXTO do arquivo (o chamador pode alterar o objeto que recebeu), uma por
# caminho (`_import_em_voo`), e grava só se o banco continua sem o caminho
# (`so_se_ausente`): uma gravação da tela que entrou antes dela vence.
_import_lock = threading.Lock()
_import_em_voo = set()
_import_threads = []


def _importar_legado(path, rel, texto, st):
    try:
        if write(path, json.loads(texto), stamp=(st.st_mtime, st.st_size), so_se_ausente=True):
            log.info('[data-store] %s importado do disco para o banco', rel)
    except Exception:                                       # noqa: BLE001
        log.warning('[data-store] não consegui importar %s:\n%s', rel, traceback.format_exc())
    finally:
        with _import_lock:
            _import_em_voo.discard(rel)
            _import_threads[:] = [t for t in _import_threads
                                  if t is not threading.current_thread() and t.is_alive()]


def _importar_legado_async(path, rel, texto):
    with _import_lock:
        if rel in _import_em_voo:
            return
        _import_em_voo.add(rel)
    try:
        st = os.stat(path)
    except OSError:
        with _import_lock:
            _import_em_voo.discard(rel)
        return
    t = threading.Thread(target=_importar_legado, args=(path, rel, texto, st),
                         name='store-import', daemon=True)
    with _import_lock:
        _import_threads.append(t)
    t.start()


def import_wait(timeout=120.0):
    """Espera as importações de legado em voo (testes, scripts). True se
    todas terminaram dentro do teto."""
    fim = time.monotonic() + timeout
    while True:
        with _import_lock:
            vivos = [t for t in _import_threads if t.is_alive()]
        if not vivos:
            return True
        for t in vivos:
            t.join(max(0.0, fim - time.monotonic()))
        if time.monotonic() >= fim:
            return False


def _read_target(rel, alvo, default=AUSENTE):
    """O payload de `rel` no alvo dado — sem a importação preguiçosa nem a
    cópia empacotada (é o miolo do `read`, e o que o registro de calendários
    usa para não entrar em recursão)."""
    db_rel, schema, tabela, kind = alvo
    db = _db_abs(db_rel)
    try:
        ent = _manifest(db, strict=True).get(rel)
    except BancoOcupado:
        ultimo = _pmemo_last(rel)
        if ultimo is _MISS:
            raise
        return core.parsear_crus(ultimo)
    if ent is None:
        if default is AUSENTE:
            raise FileNotFoundError(rel)
        return default
    mtime, fsize, _targets = ent
    chave = (rel, mtime, fsize)
    crus = _pmemo_get(chave)
    if crus is _MISS:
        try:
            crus = _com_leitura(db, lambda con: core.ler_crus(con, rel, kind, tabela, schema))
        except BancoOcupado:
            ultimo = _pmemo_last(rel)
            if ultimo is _MISS:
                raise
            return core.parsear_crus(ultimo)
        if crus is AUSENTE:
            _forget_db(db)                    # o manifest em cache estava velho
            if default is AUSENTE:
                raise FileNotFoundError(rel)
            return default
        if crus is None:
            raise IOError('%s: o banco tem o caminho mas não o canal de reconstrução '
                          '(formato anterior ao __raw) — reimporte com '
                          'scripts/convert_json_to_duckdb.py' % rel)
        _pmemo_put(chave, crus)
    return core.parsear_crus(crus)


def read(path, default=AUSENTE):
    """O payload de um caminho. Levanta `FileNotFoundError` quando não há —
    ou devolve `default`, se dado — para os `except (IOError, ...)` de sempre
    continuarem valendo."""
    if not managed(path):
        return _read_fs(path, default)
    rel = rel_of(path)
    alvos = _alvos(rel)
    if not alvos:
        return _read_fs(path, default)
    for alvo in alvos:
        try:
            return _read_target(rel, alvo)
        except FileNotFoundError:
            continue
    # O banco não tem: o arquivo legado no disco é IMPORTADO (uma vez). A
    # cópia EMPACOTADA não entra aqui — quem cai para ela é o `data_path()`,
    # que devolve o caminho do repositório (fora da raiz de dados, lido do
    # disco): um leitor com caminho explícito lê o que pediu, ou nada.
    if os.path.isfile(path):
        texto = _read_fs_text(path)
        payload = json.loads(texto)
        _importar_legado_async(path, rel, texto)
        return payload
    if default is AUSENTE:
        raise FileNotFoundError(path)
    return default


def read_json(path):
    return read(path)


# ── escrita ──────────────────────────────────────────────────────────────────

def _write_fs_atomic(path, payload):
    """O escritor atômico de sempre, para o que NÃO vive no banco."""
    dir_name = os.path.dirname(path) or '.'
    os.makedirs(dir_name, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            pass
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        try:
            os.unlink(tmp)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _after_write_fs(path):
    """Os mesmos esquecimentos, para o que foi gravado no disco."""
    try:
        from apps.pages.request_cache import bump_cache_gen
        bump_cache_gen(path)
        from apps.pages.platform import json_cache
        json_cache._map_req_forget(path)
        json_cache._daycache_forget(path)
    except Exception:                                       # noqa: BLE001
        pass


def _after_write(db, path, rel):
    _forget_db(db)
    memo_forget(path)
    if rel == core.REGISTRY_FILE:
        _cal_forget()
    try:
        from apps.pages.request_cache import bump_cache_gen
        bump_cache_gen(path)
    except Exception:                                       # noqa: BLE001
        pass
    try:
        from apps.pages.platform import json_cache
        json_cache._map_req_forget(path)
        json_cache._daycache_forget(path)
    except Exception:                                       # noqa: BLE001
        pass


def write(path, payload, stamp=None, so_se_ausente=False):
    """Grava `payload` no banco do caminho — a tabela é RECONSTRUÍDA, sob a
    trava exclusiva do arquivo (camada `database_access`: permit, trava,
    portão, retentativa). `stamp` = `(mtime, fsize)` para a importação de um
    arquivo legado; sem ele, o relógio e o tamanho do texto. `so_se_ausente`
    (a importação do legado) desiste, já sob a trava, se o banco ganhou o
    caminho nesse meio-tempo. Devolve True quando gravou."""
    if not managed(path):
        _write_fs_atomic(path, payload)
        _after_write_fs(path)
        return True
    rel = rel_of(path)
    alvo = target(rel)
    if alvo is None:
        _write_fs_atomic(path, payload)
        _after_write_fs(path)
        return True
    db_rel, schema, tabela, kind = alvo
    db = _db_abs(db_rel)
    os.makedirs(os.path.dirname(db), exist_ok=True)
    nome_cal = _cal_files().get(rel.lower()) if kind == core.KIND_CALENDAR else None
    mtime, fsize = (stamp if stamp else (None, None))
    with duckdb_write(db) as con:
        if so_se_ausente:
            core.ensure_manifest(con)
            if core.manifest_targets(con, core.manifest_key_of(rel, kind)):
                return False
        core.escrever_payload(con, rel, payload, kind, tabela, schema,
                              nome_cal=nome_cal, mtime=mtime, fsize=fsize)
    _after_write(db, path, rel)
    # O mesmo caminho gravado sob o OUTRO alvo (calendário × dataset de raiz)
    # sai de lá: duas cópias responderiam por versões diferentes.
    for outro in _alvos(rel)[1:]:
        odb = _db_abs(outro[0])
        if rel in _manifest(odb):
            try:
                with duckdb_write(odb) as con:
                    core.apagar_payload(con, rel, outro[3])
                _after_write(odb, path, rel)
            except Exception:                               # noqa: BLE001
                log.debug('[data-store] não apaguei %s do alvo alternativo', rel, exc_info=True)
    return True


def remove(path):
    """Apaga um caminho: as tabelas dele e a linha do manifest. Levanta
    `FileNotFoundError` quando não há, como `os.remove`."""
    if not managed(path):
        os.remove(path)
        return
    rel = rel_of(path)
    alvo = target(rel)
    if alvo is None:
        os.remove(path)
        return
    achou = False
    for db_rel, _schema, _tabela, kind in _alvos(rel):
        db = _db_abs(db_rel)
        if rel not in _manifest(db):
            continue
        with duckdb_write(db) as con:
            core.apagar_payload(con, rel, kind)
        _after_write(db, path, rel)
        achou = True
    if not achou:
        if os.path.isfile(path):
            os.remove(path)
            return
        raise FileNotFoundError(path)
    if os.path.isfile(path):                  # o legado no disco não pode ressuscitar o dado
        try:
            os.remove(path)
        except OSError:
            pass


# ── existência, stat, enumeração ────────────────────────────────────────────

class _Stat:
    __slots__ = ('st_mtime', 'st_size')

    def __init__(self, mtime, size):
        self.st_mtime = float(mtime)
        self.st_size = int(size)


def stat(path):
    """`(st_mtime, st_size)` de um caminho — do manifest; do disco para o
    legado ainda não importado e para a cópia empacotada.

    Banco OCUPADO sem manifest conhecido levanta `BancoOcupado` (`strict`),
    nunca `FileNotFoundError`: "não existe" é o que um read-modify-write
    (`if exists: ler; alterar; gravar`) lê como "dia vazio" — e gravaria só o
    registro novo por cima do dia inteiro assim que a instância vizinha
    soltasse a trava. Ocupado tem de PARAR o chamador (o `except IOError` dos
    leitores, ou o 503 do tratador global), não responder por ele."""
    if not managed(path):
        return os.stat(path)
    rel = rel_of(path)
    for alvo in _alvos(rel):
        try:
            ent = _manifest(_db_abs(alvo[0]), strict=True).get(rel)
        except BancoOcupado:
            # A mesma resposta do `read`: a última cópia boa em memória diz
            # que o caminho existe, com o carimbo dela (a chave do memo).
            chave = _pmemo_last_key(rel)
            if chave is not _MISS:
                return _Stat(chave[1], chave[2])
            raise
        if ent is not None:
            return _Stat(ent[0], ent[1])
    if os.path.isfile(path):
        return os.stat(path)
    raise FileNotFoundError(path)


def getmtime(path):
    return stat(path).st_mtime


def getsize(path):
    return stat(path).st_size


def isfile(path):
    """Existe no banco (ou no disco, legado)? `BancoOcupado` sobe — ver
    `stat`: só `FileNotFoundError` é "não"."""
    if not managed(path):
        return os.path.isfile(path)
    try:
        stat(path)
        return True
    except BancoOcupado:
        raise
    except OSError:
        return False


def exists(path):
    if managed(path):
        return isfile(path)
    if os.path.exists(path):
        return True
    return isdir(path)


def isdir(path):
    """Um diretório de dados EXISTE quando há caminho sob ele no banco — ou no
    disco. A pasta física deixou de ser criada pela escrita."""
    if os.path.isdir(path):
        return True
    rel = _managed_dir(path)
    if rel is None:
        return False
    return bool(_entries_under(rel))


def listdir(path):
    """Os nomes sob um diretório: os `.json` do banco, os subdiretórios que
    o banco implica, e o que estiver no disco (anexos, planilhas)."""
    rel = _managed_dir(path)
    if rel is None:
        return os.listdir(path)
    nomes = set()
    try:
        nomes.update(os.listdir(path))
    except OSError:
        pass
    prefixo = (rel + '/') if rel else ''
    for r in _entries_under(rel):
        resto = r[len(prefixo):]
        nomes.add(resto.split('/', 1)[0])
    if not nomes and not os.path.isdir(path):
        raise FileNotFoundError(path)
    return sorted(nomes)


def walk(root):
    """`(dirpath, dirnames, filenames)` como `os.walk`, top-down e ordenado,
    a partir do banco — só os `.json`. Fora da raiz de dados é `os.walk`."""
    rel_root = _managed_dir(root)
    if rel_root is None:
        yield from os.walk(root)
        return
    raiz = data_root()
    arquivos, pastas = {}, set()
    for r in _entries_under(rel_root):
        pasta, _sep, nome = r.rpartition('/')
        arquivos.setdefault(pasta, []).append(nome)
        partes = pasta.split('/') if pasta else []
        for i in range(len(partes) + 1):
            pastas.add('/'.join(partes[:i]))
    if rel_root not in pastas:
        if os.path.isdir(root):
            yield root, [], []
        return
    filhos = {}
    for pasta in pastas:
        if pasta:
            pai, _sep, nome = pasta.rpartition('/')
            filhos.setdefault(pai, set()).add(nome)
    fila = [rel_root]
    while fila:
        atual = fila.pop(0)
        dirpath = os.path.join(raiz, *atual.split('/')) if atual else raiz
        subs = sorted(filhos.get(atual, ()))
        yield dirpath, subs, sorted(arquivos.get(atual, ()))
        fila[0:0] = [(atual + '/' + f) if atual else f for f in subs]


def day_files(raiz, sufixo='', desde=None, ate=None):
    """`(caminho, nome, mtime, tamanho)` dos arquivos-dia de uma árvore, pelo
    banco, na ordem do caminho — o contrato do `_day_files` do daycache.
    `desde`/`ate` podam pela DATA do caminho (`dia_do_rel`); caminho sem
    data fica de fora quando há poda."""
    rel_root = _managed_dir(raiz)
    if rel_root is None:
        yield from _day_files_disk(raiz, sufixo, desde, ate)
        return
    base = data_root()
    entradas = _entries_under(rel_root)
    for r in sorted(entradas):
        nome = r.rsplit('/', 1)[-1]
        if sufixo and not nome.endswith(sufixo):
            continue
        if desde is not None or ate is not None:
            dia = core.dia_do_rel(r)
            if dia is None:
                continue
            if desde is not None and dia < (desde.date() if hasattr(desde, 'date') else desde):
                continue
            if ate is not None and dia > (ate.date() if hasattr(ate, 'date') else ate):
                continue
        mt, fs = entradas[r]
        yield (os.path.normpath(os.path.join(base, *r.split('/'))), nome, mt, fs)


def _day_files_disk(raiz, sufixo='', desde=None, ate=None):
    """A varredura de DISCO de sempre (scandir com poda por ano/mês) — para
    uma árvore FORA da raiz de dados, que o banco não conhece (os testes que
    apontam a pasta de um módulo para um tmp)."""
    from apps.pages.platform.json_cache import _daycache_dir_ok
    if not os.path.isdir(raiz):
        return
    pilha = [(raiz, '')]
    while pilha:
        atual, pai = pilha.pop()
        subdirs, arquivos = [], []
        try:
            with os.scandir(atual) as entradas:
                for e in entradas:
                    try:
                        if e.is_dir():
                            if _daycache_dir_ok(e.name, pai, desde, ate):
                                subdirs.append((e.name, e.path))
                            continue
                        if sufixo and not e.name.endswith(sufixo):
                            continue
                        st = e.stat()
                        arquivos.append((e.name, e.path, st.st_mtime, st.st_size))
                    except OSError:
                        continue
        except OSError:
            log.warning('[data-store] não consegui listar %s', atual)
            continue
        for nome, caminho in sorted(subdirs, reverse=True):
            pilha.append((caminho, nome))
        for nome, caminho, mtime, size in sorted(arquivos):
            yield (caminho, nome, mtime, size)


def prefetch(paths):
    """Aquece o memo para vários caminhos com UMA abertura por banco. Devolve
    `{caminho: payload}` do que ficou pronto; o resto sai da leitura de sempre."""
    grupos = {}
    for p in paths or []:
        if not managed(p):
            continue
        rel = rel_of(p)
        alvo = target(rel)
        if alvo is None:
            continue
        grupos.setdefault(_db_abs(alvo[0]), []).append((p, rel, alvo))
    prontos = {}
    for db, itens in grupos.items():
        man = _manifest(db)
        pend = []
        for p, rel, alvo in itens:
            ent = man.get(rel)
            if ent is None:
                continue
            chave = (rel, ent[0], ent[1])
            crus = _pmemo_get(chave)
            if crus is not _MISS:
                prontos[p] = core.parsear_crus(crus)
            else:
                pend.append((p, rel, alvo, chave))
        if not pend:
            continue

        def _lote(con, pend=pend):
            out = {}
            for p, rel, alvo, chave in pend:
                try:
                    crus = core.ler_crus(con, rel, alvo[3], alvo[2], alvo[1])
                except Exception:                           # noqa: BLE001
                    continue
                if crus is AUSENTE or crus is None:
                    continue
                out[p] = (chave, crus)
            return out
        try:
            lidos = _com_leitura(db, _lote)
        except Exception:                                   # noqa: BLE001
            continue
        for p, (chave, crus) in lidos.items():
            _pmemo_put(chave, crus)
            prontos[p] = core.parsear_crus(crus)
    return prontos
