"""Prova das travas de arquivo no Shared Drive do Stratos (HANDOFF §681, passo B).

O DuckDB no Shared Drive (o EFS da solução, NFS v4.1) só é seguro se as duas
travas de que o app depende valem ali, entre PROCESSOS:

  · a do `portalocker` — o `.lock` ao lado de cada banco, que a camada
    `database_access` pede compartilhada na leitura e exclusiva na escrita
    (`fcntl.flock` no Linux, `LOCK_* | NON_BLOCKING`, a mesma chamada daqui);
  · a do próprio DuckDB — quem abre em escrita segura o arquivo, e o outro
    processo recebe "Could not set lock on file".

E uma terceira pergunta, a que o NFS costuma responder diferente do disco
local: o Linux EMULA o `flock` em NFS com travas POSIX (`fcntl`), e trava
POSIX é do PROCESSO, não do descritor. Se for o caso aqui, duas threads do
mesmo processo não se excluem pelo `.lock`, e fechar QUALQUER descritor do
arquivo solta a trava inteira — a da thread que está escrevendo inclusive. O
app abre o mesmo `.lock` em várias threads ao mesmo tempo (cada operação
abre o seu), então isso tiraria a proteção contra a instância VIZINHA (outro
contêiner, ou o velho durante o deploy) sem erro nenhum. Os testes
`mesmo_processo_*` medem exatamente isso.

Dois modos:

  · `local` — tudo num contêiner: processos filhos seguram as travas e o
    processo que pergunta é outro. Prova a trava entre processos DO MESMO
    cliente NFS, mede abrir um banco de dia e um de cadastro e gravar.
  · `segurar` / `conferir` — a prova ENTRE contêineres: um request deixa um
    processo segurando as travas por N segundos, e outro request (de
    preferência noutro contêiner — o `host` da resposta diz) tenta pegá-las.
    Num contêiner só, o resultado é "inconclusivo" e diz por quê.

Cada chamada também anota o host que a atendeu em `<pasta>/hosts/`, e a
resposta lista os hosts vistos na última hora: é como se descobre quantos
contêineres servem a solução.

Nada aqui importa o `apps` nem o `stratosblocks`; o processo filho é este
mesmo arquivo (`python prova_travas.py <modo> ...`). Linha de comando, para
rodar num terminal do contêiner ou numa pasta qualquer:

    python prova_travas.py --pasta /caminho/no/drive [--db-dir ...]
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time

AQUI = os.path.abspath(__file__)
ESPERA_PRONTO = 30          # s até o filho dizer que segura a trava
SEGURA_MAX = 90             # s que o filho segura no modo local, no máximo
CRUZADA_MAX = 900           # s que o filho segura no modo segurar, no máximo
HOSTS_JANELA = 3600         # s: hosts vistos nesta janela entram na resposta
_FILHOS = []                # os filhos do modo segurar, para colher quando saem


# ── As travas, como o app as pede ───────────────────────────────────────────

def _portalocker():
    """O `portalocker` como o app o usa. `OTC_PROVA_LOCKER=lockf` troca o
    `flock` pelas travas POSIX (`fcntl.lockf`) — é o que o Linux faz por baixo
    do `flock` num NFS, e é como o `check_prova_travas.py` prova que o teste
    acusa o caso num disco local."""
    import portalocker
    if os.getenv('OTC_PROVA_LOCKER', '').strip().lower() == 'lockf':
        import fcntl
        import portalocker.portalocker as impl
        impl.LOCKER = fcntl.lockf
    return portalocker


def _flags(modo):
    portalocker = _portalocker()
    base = portalocker.LockFlags.EXCLUSIVE if modo == 'EX' else portalocker.LockFlags.SHARED
    return base | portalocker.LockFlags.NON_BLOCKING


def trava(fh, modo):
    portalocker = _portalocker()
    portalocker.lock(fh, _flags(modo))


def tenta_trava(caminho, modo):
    """-> (pegou, erro). Abre, tenta sem esperar e solta: a pergunta de outro
    processo. `a+b`, o modo do `database_access`."""
    portalocker = _portalocker()
    fh = open(caminho, 'a+b')
    try:
        portalocker.lock(fh, _flags(modo))
    except portalocker.exceptions.LockException as e:
        fh.close()
        return False, '%s: %s' % (type(e).__name__, e)
    try:
        portalocker.unlock(fh)
    finally:
        fh.close()
    return True, ''


def tenta_duckdb(caminho, read_only):
    """-> (abriu, erro)."""
    import duckdb
    try:
        con = duckdb.connect(caminho, read_only=read_only)
    except Exception as e:                                  # noqa: BLE001
        return False, '%s: %s' % (type(e).__name__, str(e)[:300])
    con.close()
    return True, ''


# ── O processo filho ────────────────────────────────────────────────────────

def _grava_json(caminho, doc):
    tmp = caminho + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh)
    os.replace(tmp, caminho)


def _espera_solta(solta, ate):
    while time.time() < ate and not os.path.exists(solta):
        time.sleep(0.05)


def filho(modo, alvo, pronto, solta, segundos):
    """Segura uma trava até `solta` existir (ou o prazo), e avisa em `pronto`."""
    ate = time.time() + segundos
    doc = {'pid': os.getpid(), 'host': socket.gethostname(), 'ate': ate}
    if modo in ('arquivo-EX', 'arquivo-SH'):
        fh = open(alvo, 'a+b')
        trava(fh, modo[-2:])
        _grava_json(pronto, doc)
        _espera_solta(solta, ate)
        fh.close()
    elif modo == 'mesmo-processo-tenta':
        # A trava exclusiva num descritor; outro descritor do MESMO arquivo, no
        # MESMO processo, pede a compartilhada. No disco local (flock por
        # descritor) ele é recusado; com flock emulado por fcntl ele passa — e
        # CONVERTE a exclusiva em compartilhada.
        fh1 = open(alvo, 'a+b')
        trava(fh1, 'EX')
        fh2 = open(alvo, 'a+b')
        try:
            trava(fh2, 'SH')
            doc['segundo_descritor_pegou'] = True
        except Exception as e:                              # noqa: BLE001
            doc['segundo_descritor_pegou'] = False
            doc['erro'] = '%s: %s' % (type(e).__name__, e)
        fh2.close()
        _grava_json(pronto, doc)
        _espera_solta(solta, ate)
        fh1.close()
    elif modo == 'mesmo-processo-fecha':
        # O caso do app: uma thread segura a exclusiva e OUTRA abre e fecha o
        # mesmo `.lock` (a leitura que terminou). Trava POSIX solta no close.
        fh1 = open(alvo, 'a+b')
        trava(fh1, 'EX')
        open(alvo, 'a+b').close()
        _grava_json(pronto, doc)
        _espera_solta(solta, ate)
        fh1.close()
    elif modo == 'duckdb-escreve':
        import duckdb
        con = duckdb.connect(alvo)
        con.execute('CREATE OR REPLACE TABLE t AS SELECT range AS i FROM range(1000)')
        _grava_json(pronto, doc)
        _espera_solta(solta, ate)
        con.close()
    elif modo == 'cruzada':
        import duckdb
        fh = open(alvo + '.lock', 'a+b')
        trava(fh, 'EX')
        con = duckdb.connect(alvo)
        con.execute('CREATE OR REPLACE TABLE t AS SELECT range AS i FROM range(1000)')
        _grava_json(pronto, doc)
        _espera_solta(solta, ate)
        con.close()
        fh.close()
        try:
            os.remove(pronto)
        except OSError:
            pass
    else:
        raise SystemExit('modo desconhecido: %s' % modo)


class _Filho(object):
    """Um filho segurando uma trava; `with` solta e colhe."""

    def __init__(self, pasta, modo, alvo, segundos=SEGURA_MAX):
        self.pronto = os.path.join(pasta, '%s-%d.pronto' % (modo, time.time() * 1000))
        self.solta = self.pronto + '.solta'
        self.proc = subprocess.Popen(
            [sys.executable, AQUI, '--filho', modo, alvo, self.pronto, self.solta, str(segundos)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.doc = None

    def __enter__(self):
        ate = time.time() + ESPERA_PRONTO
        while time.time() < ate:
            if os.path.exists(self.pronto):
                with open(self.pronto, encoding='utf-8') as fh:
                    self.doc = json.load(fh)
                return self
            if self.proc.poll() is not None:
                break
            time.sleep(0.05)
        erro = (self.proc.stderr.read() or b'').decode('utf-8', 'replace')[-800:] \
            if self.proc.poll() is not None else 'sem resposta em %ds' % ESPERA_PRONTO
        self.solta_e_colhe()
        raise RuntimeError('o processo filho (%s) nao segurou a trava: %s'
                           % (self.proc.args[3], erro.strip()))

    def solta_e_colhe(self):
        try:
            open(self.solta, 'w').close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()

    def __exit__(self, *exc):
        self.solta_e_colhe()
        return False


# ── Os testes ───────────────────────────────────────────────────────────────

def _caso(nome, esperado, obtido, detalhe='', nota=''):
    return {'teste': nome, 'esperado': esperado, 'obtido': obtido,
            'ok': esperado == obtido, 'detalhe': detalhe, 'nota': nota}


def _travas_entre_processos(pasta):
    casos = []
    lock = os.path.join(pasta, 'a.lock')
    with _Filho(pasta, 'arquivo-EX', lock):
        pegou, erro = tenta_trava(lock, 'EX')
        casos.append(_caso('exclusiva_barra_exclusiva', False, pegou, erro,
                           'outro processo segura a exclusiva: a exclusiva daqui não vem'))
        pegou, erro = tenta_trava(lock, 'SH')
        casos.append(_caso('exclusiva_barra_compartilhada', False, pegou, erro,
                           'nem a compartilhada (o leitor espera o escritor)'))
    pegou, erro = tenta_trava(lock, 'EX')
    casos.append(_caso('solta_ao_sair', True, pegou, erro,
                       'o processo saiu: a trava volta a estar livre'))
    with _Filho(pasta, 'arquivo-SH', lock):
        pegou, erro = tenta_trava(lock, 'SH')
        casos.append(_caso('compartilhada_aceita_compartilhada', True, pegou, erro,
                           'dois leitores ao mesmo tempo'))
        pegou, erro = tenta_trava(lock, 'EX')
        casos.append(_caso('compartilhada_barra_exclusiva', False, pegou, erro,
                           'o escritor espera os leitores'))
    return casos


def _travas_no_mesmo_processo(pasta):
    casos = []
    lock = os.path.join(pasta, 'b.lock')
    with _Filho(pasta, 'mesmo-processo-tenta', lock) as f:
        casos.append(_caso('mesmo_processo_segundo_descritor', False,
                           bool(f.doc.get('segundo_descritor_pegou')), f.doc.get('erro', ''),
                           'outro descritor do mesmo processo pede a compartilhada sobre a '
                           'exclusiva. True = flock emulado por fcntl (trava por processo): '
                           'as threads do app não se excluem pelo .lock'))
        pegou, erro = tenta_trava(lock, 'EX')
        casos.append(_caso('mesmo_processo_exclusiva_segue', False, pegou, erro,
                           'depois disso, outro processo ainda não pega a exclusiva'))
    lock = os.path.join(pasta, 'c.lock')
    with _Filho(pasta, 'mesmo-processo-fecha', lock):
        pegou, erro = tenta_trava(lock, 'EX')
        casos.append(_caso('mesmo_processo_fechar_outro_descritor', False, pegou, erro,
                           'uma thread segura a exclusiva e outra abre e fecha o mesmo .lock. '
                           'True = o close soltou a trava inteira: a instância vizinha entra '
                           'no meio da gravação'))
    return casos


def _travas_do_duckdb(pasta):
    casos = []
    db = os.path.join(pasta, 'd.duckdb')
    with _Filho(pasta, 'duckdb-escreve', db):
        abriu, erro = tenta_duckdb(db, read_only=False)
        casos.append(_caso('duckdb_escrita_barra_escrita', False, abriu, erro,
                           'outro processo tem o banco aberto em escrita'))
        abriu, erro = tenta_duckdb(db, read_only=True)
        casos.append(_caso('duckdb_escrita_barra_leitura', False, abriu, erro,
                           'nem só leitura'))
    import duckdb
    try:
        con = duckdb.connect(db, read_only=True)
        try:
            n = con.execute('SELECT count(*) FROM t').fetchone()[0]
        finally:
            con.close()
        casos.append(_caso('duckdb_dado_do_outro_processo', 1000, n, '',
                           'o que o outro processo gravou e fechou chega inteiro aqui'))
    except Exception as e:                                  # noqa: BLE001
        casos.append(_caso('duckdb_dado_do_outro_processo', 1000, None,
                           '%s: %s' % (type(e).__name__, e)))
    return casos


# ── Tempos ──────────────────────────────────────────────────────────────────

def _bancos(db_dir):
    """O maior banco de dia (`cache`) e o maior de cadastro (`mappings`)."""
    dia = cadastro = None
    for raiz, pastas, arquivos in os.walk(db_dir):
        pastas[:] = [p for p in pastas if not p.startswith('_')]
        partes = set(os.path.relpath(raiz, db_dir).replace('\\', '/').lower().split('/'))
        for nome in arquivos:
            if not nome.endswith('.db'):
                continue
            p = os.path.join(raiz, nome)
            try:
                t = os.path.getsize(p)
            except OSError:
                continue
            if 'cache' in partes and (dia is None or t > dia[1]):
                dia = (p, t)
            elif 'mappings' in partes and (cadastro is None or t > cadastro[1]):
                cadastro = (p, t)
    return dia, cadastro


def _abre_bruto(caminho):
    import contextlib
    import duckdb

    @contextlib.contextmanager
    def cm():
        con = duckdb.connect(caminho, read_only=True)
        try:
            yield con
        finally:
            con.close()
    return cm()


def _mede_abertura(caminho, abre):
    voltas = []
    for _ in range(2):
        t0 = time.monotonic()
        try:
            with abre(caminho) as con:
                tem = con.execute("SELECT count(*) FROM information_schema.tables "
                                  "WHERE table_name = '_manifest'").fetchone()[0]
                n = con.execute('SELECT count(*) FROM _manifest').fetchone()[0] if tem else None
        except Exception as e:                              # noqa: BLE001
            return {'erro': '%s: %s' % (type(e).__name__, str(e)[:300])}
        voltas.append(round(time.monotonic() - t0, 3))
    return {'segundos': voltas, 'manifest': n}


def _tempos(pasta, db_dir, abre):
    out = {}
    if db_dir and os.path.isdir(db_dir):
        dia, cadastro = _bancos(db_dir)
        for rotulo, achado in (('banco_de_dia', dia), ('banco_de_cadastro', cadastro)):
            if achado is None:
                out[rotulo] = {'erro': 'nenhum .db em %s' % db_dir}
                continue
            r = _mede_abertura(achado[0], abre or _abre_bruto)
            r.update(banco=os.path.relpath(achado[0], db_dir), mb=round(achado[1] / 1e6, 1))
            out[rotulo] = r
    import duckdb
    db = os.path.join(pasta, 'escrita.duckdb')
    t0 = time.monotonic()
    con = duckdb.connect(db)
    try:
        con.execute('CREATE TABLE t AS SELECT range AS i, md5(range::VARCHAR) AS s '
                    'FROM range(200000)')
        con.execute('CHECKPOINT')
    finally:
        con.close()
    out['gravar_200_mil_linhas'] = round(time.monotonic() - t0, 3)
    arq = os.path.join(pasta, 'fsync.bin')
    t0 = time.monotonic()
    with open(arq, 'wb') as fh:
        fh.write(os.urandom(1 << 20))
        fh.flush()
        os.fsync(fh.fileno())
    out['gravar_1_mb_com_fsync'] = round(time.monotonic() - t0, 3)
    t0 = time.monotonic()
    for _ in range(100):
        os.stat(arq)
    out['stat_ms'] = round((time.monotonic() - t0) * 10, 3)
    return out


# ── Hosts e veredito ────────────────────────────────────────────────────────

def _anota_host(base):
    pasta = os.path.join(base, 'hosts')
    os.makedirs(pasta, exist_ok=True)
    host, agora = socket.gethostname(), time.time()
    try:
        _grava_json(os.path.join(pasta, host + '.json'), {'host': host, 'pid': os.getpid(),
                                                          'em': agora})
    except OSError:
        pass
    vistos = []
    for nome in sorted(os.listdir(pasta)):
        if not nome.endswith('.json'):
            continue
        try:
            with open(os.path.join(pasta, nome), encoding='utf-8') as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        if agora - doc.get('em', 0) <= HOSTS_JANELA:
            vistos.append({'host': doc.get('host'), 'pid': doc.get('pid'),
                           'ha_segundos': int(agora - doc.get('em', 0))})
    return vistos


def _veredito(casos):
    falhas = [c['teste'] for c in casos if not c['ok']]
    if not falhas:
        return 'as travas valem', falhas
    if all(f.startswith('mesmo_processo') for f in falhas):
        return ('as travas valem entre processos, mas no mesmo processo são do PROCESSO '
                '(flock emulado por fcntl): com mais de um contêiner, a instância vizinha '
                'pode entrar no meio de uma gravação'), falhas
    return 'as travas NÃO valem aqui', falhas


def _cabecalho(pasta):
    import duckdb
    import portalocker
    return {'host': socket.gethostname(), 'pid': os.getpid(), 'pasta': pasta,
            'python': sys.version.split()[0], 'duckdb': duckdb.__version__,
            'portalocker': portalocker.__version__, 'quando': time.strftime('%Y-%m-%d %H:%M:%S')}


def prova_local(base, db_dir=None, abre=None):
    """Os testes num contêiner. `base` é a pasta da prova no drive; cada rodada
    trabalha numa subpasta própria e a apaga no fim. `abre` é o `duckdb_read`
    do app quando roda dentro dele (respeita as travas dos bancos em uso)."""
    pasta = os.path.join(base, 'rodada-%d-%d' % (time.time(), os.getpid()))
    os.makedirs(pasta)
    out = _cabecalho(pasta)
    out['hosts_vistos'] = _anota_host(base)
    casos = []
    try:
        for grupo in (_travas_entre_processos, _travas_no_mesmo_processo, _travas_do_duckdb):
            try:
                casos.extend(grupo(pasta))
            except Exception as e:                          # noqa: BLE001
                casos.append(_caso(grupo.__name__.strip('_'), 'rodar', 'quebrou',
                                   '%s: %s' % (type(e).__name__, e)))
        try:
            out['tempos'] = _tempos(pasta, db_dir, abre)
        except Exception as e:                              # noqa: BLE001
            out['tempos'] = {'erro': '%s: %s' % (type(e).__name__, e)}
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    out['casos'] = casos
    out['veredito'], out['falhas'] = _veredito(casos)
    return out


def _colhe_filhos():
    for p in list(_FILHOS):
        if p.poll() is not None:
            _FILHOS.remove(p)


def segurar(base, segundos):
    """Deixa um processo segurando o `.lock` (exclusiva) e o DuckDB (escrita) da
    prova cruzada por `segundos`, e volta na hora."""
    _colhe_filhos()
    segundos = max(10, min(int(segundos), CRUZADA_MAX))
    pasta = os.path.join(base, 'cruzada')
    os.makedirs(pasta, exist_ok=True)
    pronto = os.path.join(pasta, 'segurando.json')
    if os.path.exists(pronto):
        with open(pronto, encoding='utf-8') as fh:
            doc = json.load(fh)
        if doc.get('ate', 0) > time.time():
            return dict(_cabecalho(pasta), hosts_vistos=_anota_host(base), segurando=doc,
                        aviso='ja havia um processo segurando; nada novo foi aberto')
        os.remove(pronto)
    solta = os.path.join(pasta, 'solta')
    if os.path.exists(solta):
        os.remove(solta)
    p = subprocess.Popen([sys.executable, AQUI, '--filho', 'cruzada',
                          os.path.join(pasta, 'x.duckdb'), pronto, solta, str(segundos)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    _FILHOS.append(p)
    ate = time.time() + ESPERA_PRONTO
    while time.time() < ate and not os.path.exists(pronto) and p.poll() is None:
        time.sleep(0.05)
    if not os.path.exists(pronto):
        raise RuntimeError('o processo filho nao segurou as travas (saida %s)' % p.poll())
    with open(pronto, encoding='utf-8') as fh:
        doc = json.load(fh)
    return dict(_cabecalho(pasta), hosts_vistos=_anota_host(base), segurando=doc)


def conferir(base, soltar=False):
    """Tenta pegar o que o `segurar` deixou preso. Só prova alguma coisa se o
    host daqui for OUTRO."""
    _colhe_filhos()
    pasta = os.path.join(base, 'cruzada')
    pronto = os.path.join(pasta, 'segurando.json')
    out = dict(_cabecalho(pasta), hosts_vistos=_anota_host(base))
    doc = None
    if os.path.exists(pronto):
        with open(pronto, encoding='utf-8') as fh:
            doc = json.load(fh)
    if not doc or doc.get('ate', 0) <= time.time():
        out.update(veredito='nada sendo segurado: chame ?modo=segurar primeiro', casos=[])
        return out
    out['segurando'] = doc
    db = os.path.join(pasta, 'x.duckdb')
    casos = []
    pegou, erro = tenta_trava(db + '.lock', 'EX')
    casos.append(_caso('cruzada_exclusiva_barra_exclusiva', False, pegou, erro))
    pegou, erro = tenta_trava(db + '.lock', 'SH')
    casos.append(_caso('cruzada_exclusiva_barra_compartilhada', False, pegou, erro))
    abriu, erro = tenta_duckdb(db, read_only=False)
    casos.append(_caso('cruzada_duckdb_escrita_barra_escrita', False, abriu, erro))
    abriu, erro = tenta_duckdb(db, read_only=True)
    casos.append(_caso('cruzada_duckdb_escrita_barra_leitura', False, abriu, erro))
    out['casos'] = casos
    mesmo = doc.get('host') == out['host']
    veredito, out['falhas'] = _veredito(casos)
    out['mesmo_conteiner'] = mesmo
    out['veredito'] = (('inconclusivo: o mesmo contêiner (%s) segura e pergunta — repita o '
                        'conferir até cair noutro host, ou faça um deploy com o processo '
                        'segurando. Resultado aqui: %s') % (out['host'], veredito)) if mesmo \
        else veredito
    if soltar:
        open(os.path.join(pasta, 'solta'), 'w').close()
        out['soltou'] = True
    return out


def roda(modo, base, db_dir=None, abre=None, segundos=300, soltar=False):
    os.makedirs(base, exist_ok=True)
    if modo == 'segurar':
        return segurar(base, segundos)
    if modo == 'conferir':
        return conferir(base, soltar=soltar)
    return prova_local(base, db_dir=db_dir, abre=abre)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ['--filho']:
        modo, alvo, pronto, solta, segundos = argv[1:6]
        filho(modo, alvo, pronto, solta, float(segundos))
        return 0
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--pasta', required=True, help='a pasta da prova (no Shared Drive)')
    ap.add_argument('--db-dir', default='', help='o DATABASE_DIR, para medir a abertura')
    ap.add_argument('--modo', default='local', choices=('local', 'segurar', 'conferir'))
    ap.add_argument('--segundos', type=int, default=300)
    ap.add_argument('--soltar', action='store_true')
    a = ap.parse_args(argv)
    out = roda(a.modo, a.pasta, db_dir=a.db_dir or None, segundos=a.segundos, soltar=a.soltar)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if not out.get('falhas') else 1


if __name__ == '__main__':
    sys.exit(main())
