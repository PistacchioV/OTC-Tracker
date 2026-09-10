#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recover_duckdb_wal.py — tira um banco do LIMBO DE CHECKPOINT do DuckDB,
recuperando-o FORA do share, e o devolve magro.

    python scripts/recover_duckdb_wal.py [--db-dir PASTA] [--only SUBCAMINHO]
                                         [--work-dir PASTA_LOCAL] [--dry-run]
                                         [--no-slim] [--all]

O estado (HANDOFF §442): ao lado do `.db` há um `.wal.checkpoint` — um
checkpoint do DuckDB COMEÇOU (o `.wal` bateu o `checkpoint_threshold` de
16 MB), as gravações seguintes foram para esse segundo WAL e o processo
morreu antes de terminar (restart) — e/ou um `.wal.recovery`, a fusão dos
dois WALs que TODA abertura em escrita refaz antes de repetir o replay. Na
instância eram 75 MB a 1,1 GB por banco, com o `.db` parado em 31/08: cada
abertura, mesmo só leitura, relia tudo isso pelo share (minutos), o
`store-import` ficava meia hora dentro do `duckdb.connect` segurando a trava
exclusiva, e o `slim_duckdb.py` travava no `ATTACH` deixando `.db.slim` de
12 KB. O DuckDB sai do limbo sozinho num disco local em segundos; pelo share
nunca chega ao fim antes do restart seguinte.

O que este script faz, banco a banco (só nos que estão em limbo — ver
`data_store.wal_em_limbo`; `--all` pega qualquer `.wal`):
  1. copia `.db` + WALs para `--work-dir` (local; padrão
     `%LOCALAPPDATA%\\OTC-Tracker\\recover`);
  2. abre a cópia em escrita (o DuckDB funde e refaz o replay), `CHECKPOINT`,
     fecha — e confere que não sobrou WAL nenhum. A cópia perde o
     SOMENTE-LEITURA herdado do share, e se o rename da fusão for NEGADO
     (`Could not move file: Access is denied`: no Windows o `MoveFileW` com que
     o DuckDB grava o `.wal.recovery` recusou mesmo com o destino fora do
     caminho) os dois WALs são fundidos À MÃO — a mesma operação, por cópia em
     vez de rename — e a abertura é refeita;
  3. emagrece a cópia (`slim_duckdb.emagrecer`, a forma do §437; `--no-slim`
     pula) e lê o `_manifest` dela;
  4. copia de volta como `<db>.novo`, MOVE o `.db` velho e os WALs para
     `db/_recuperado/<AAAAMMDD-HHMMSS>/<caminho>` (renome: instantâneo no
     share; apague a pasta quando o app estiver de pé e conferido), troca o
     `.novo` pelo `.db` e relê o `_manifest` no share.

Rode com TODAS as instâncias PARADAS, na MESMA versão de duckdb da instância
(o WAL é da versão que o escreveu), a partir do python do `.bat`. Cada banco é
tomado na trava EXCLUSIVA da camada antes de qualquer coisa; com alguém de pé
ela não vem (uma instância lê esses bancos em laço no `summary-warm`, e um
`store-import` preso no limbo fica meia hora dentro do `duckdb.connect`
segurando a exclusiva), e o banco é PULADO dizendo `EM USO`. `--dry-run` só
lista os bancos e os MB.
"""
import argparse
import io
import os
import shutil
import stat
import sys
import tempfile
import time
import traceback
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

import duckdb                                                # noqa: E402
from apps.pages import data_store as _store                 # noqa: E402
import slim_duckdb                                          # noqa: E402


def _mb(n):
    return '%.0f MB' % (n / 1e6)


def _diz(msg):
    print(msg, flush=True)


def _em_uso(exc):
    """O erro é "o arquivo está preso por alguém" (a trava exclusiva não veio)?"""
    try:
        from apps.pages import database_access as DA
        return DA.is_file_in_use(exc)
    except ImportError:
        return False


def _liberar(caminho):
    """Tira o SOMENTE-LEITURA da cópia local. O `copy2` herda os atributos do
    arquivo do share, e o `MoveFileEx` que o DuckDB usa para fundir os WALs
    (`.wal.checkpoint` + `.wal` → `.wal.recovery` → `.wal`) recusa SOBRESCREVER
    um destino com o atributo posto: a recuperação morre num
    `IO Error: Could not move file: Access is denied` — na CÓPIA, com a trava
    do share na mão (§442)."""
    try:
        os.chmod(caminho, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _acesso_negado(exc):
    """O erro é o Windows recusando mexer no arquivo (atributo, antivírus lendo
    o que acabou de ser escrito, indexador)? Vale uma nova tentativa."""
    m = str(exc)
    return 'Could not move file' in m or 'denied' in m.lower()


def _prova_de_renome(work_dir):
    """O DuckDB não RECUPERA nada sem renomear arquivo (é assim que ele funde
    `.wal.checkpoint` + `.wal`). Se a pasta de trabalho não deixa renomear —
    política corporativa, `%LOCALAPPDATA%` redirecionado para a rede, antivírus
    de tempo real —, é melhor descobrir AGORA do que depois de copiar 1,2 GB
    pelo share e morrer com a trava do banco na mão. Levanta com o remédio."""
    os.makedirs(work_dir, exist_ok=True)
    a = os.path.join(work_dir, '_prova_renome.tmp')
    b = a + '.2'
    for x in (a, b):
        if os.path.isfile(x):
            os.remove(x)
    try:
        with io.open(a, 'wb') as fh:
            fh.write(b'x')
        os.replace(a, b)
        os.remove(b)
    except OSError as exc:
        raise RuntimeError(
            'a pasta de trabalho %s NÃO deixa renomear arquivo (%s).\n'
            '     O DuckDB precisa disso para fundir os WALs, e é o que devolve\n'
            '     `IO Error: Could not move file: Access is denied` DEPOIS da cópia.\n'
            '     Rode com outra pasta LOCAL, por exemplo:\n'
            '       --work-dir C:\\Temp\\otc-recover' % (work_dir, exc))
    finally:
        for x in (a, b):
            if os.path.isfile(x):
                try:
                    os.remove(x)
                except OSError:
                    pass


def _a_copiar(irmaos):
    """Quais WALs vão para a cópia local. O `.wal.recovery` é o produto da FUSÃO
    do `.wal` com o `.wal.checkpoint` — na instância os tamanhos batem na soma
    exata (17 + 1104 = 1121 MB), e nos parciais dão menos —, e ele é REFEITO a
    partir dos dois. Levá-lo junto não acrescenta dado nenhum e ainda custa de
    92 MB a 1,1 GB de share por banco. Só vai quando um dos dois FALTA: aí pode
    ser a única cópia do que não foi checkpointado. O original nunca é apagado:
    vai inteiro para `db/_recuperado/`."""
    fusao_completa = '.wal' in irmaos and '.wal.checkpoint' in irmaos
    return [s for s in _store.WAL_SUFIXOS
            if s in irmaos and not (s == '.wal.recovery' and fusao_completa)]


def _abre_e_checkpoint(local, tentativas, espera):
    """Abre a cópia LOCAL em escrita — é aqui que o DuckDB refaz o replay — e
    força o `CHECKPOINT`. Retenta o acesso negado passageiro (o antivírus lendo
    os megabytes recém-escritos quando o DuckDB pede o rename)."""
    for n in range(1, tentativas + 1):
        # A fusão pela metade que a tentativa anterior deixou é o destino que o
        # `MoveFileW` da próxima vai recusar: some com ela (o `.wal` e o
        # `.wal.checkpoint` que a geram continuam aqui).
        if n > 1 and os.path.isfile(local + '.wal.recovery'):
            _liberar(local + '.wal.recovery')
            os.remove(local + '.wal.recovery')
        for s in ('',) + _store.WAL_SUFIXOS:
            if os.path.isfile(local + s):
                _liberar(local + s)
        try:
            con = duckdb.connect(local)
            try:
                con.execute('CHECKPOINT')
            finally:
                con.close()
            return
        except Exception as exc:                             # noqa: BLE001
            if n >= tentativas or not _acesso_negado(exc):
                raise
            _diz('     acesso negado na cópia local (%s); tentando de novo em %ds [%d/%d]'
                 % (exc, espera, n, tentativas))
            time.sleep(espera)


def _funde_wal(local, ordem):
    """Faz À MÃO o que o DuckDB faz para sair do limbo: um `.wal` só, com o
    conteúdo dos dois. É a MESMA operação — os tamanhos da instância mostram o
    `.wal.recovery` sendo a soma exata do `.wal` com o `.wal.checkpoint` —, mas
    por CÓPIA em vez de rename, e é o rename que o Windows nega. Guarda os dois
    originais ao lado (`.orig`, renome: instantâneo) para poder desfazer.
    Devolve o mapa da guarda, ou None se algum dos dois não estiver aqui."""
    guarda = {}
    for s in ('.wal', '.wal.checkpoint'):
        if not os.path.isfile(local + s):
            for g in guarda.values():
                os.replace(g, g[:-len('.orig')])
            return None
        g = local + s + '.orig'
        if os.path.isfile(g):
            _liberar(g)
            os.remove(g)
        _liberar(local + s)
        os.replace(local + s, g)
        guarda[s] = g
    with io.open(local + '.wal', 'wb') as saida:
        for s in ordem:
            with io.open(guarda[s], 'rb') as fh:
                shutil.copyfileobj(fh, saida, 1 << 20)
    return guarda


def _desfaz_fusao(local, guarda):
    """Volta os dois WALs para o lugar (a tentativa seguinte precisa deles)."""
    for s, g in guarda.items():
        if os.path.isfile(local + s):
            _liberar(local + s)
            os.remove(local + s)
        os.replace(g, local + s)


def _recupera_local(local, origem=None, tentativas=5, espera=15):
    """Tira a cópia local do limbo. Primeiro deixa o DuckDB fazer o que ele
    faria sozinho; se o rename da fusão for NEGADO — no Windows o `MoveFileW`
    com que ele grava o `.wal.recovery` recusa destino existente, e negou
    também com o destino fora do caminho —, funde os dois WALs à mão e abre de
    novo. A ordem natural é `.wal` (o antigo) seguido do `.wal.checkpoint` (o
    que commitou durante o checkpoint); se o replay recusar, tenta a inversa,
    sempre sobre uma cópia NOVA do `.db` — uma abertura que falhou no meio do
    replay pode ter mexido nele."""
    try:
        _abre_e_checkpoint(local, 2, espera)
        return
    except Exception as exc:                                 # noqa: BLE001
        if not _acesso_negado(exc):
            raise
        primeiro = exc
    _diz('     o DuckDB não conseguiu fundir os WALs sozinho (%s)' % primeiro)
    _diz('     fundindo À MÃO — o `.wal.recovery` que ele tenta escrever É o `.wal` '
         'seguido do `.wal.checkpoint`')
    for ordem in (('.wal', '.wal.checkpoint'), ('.wal.checkpoint', '.wal')):
        guarda = _funde_wal(local, ordem)
        if guarda is None:
            raise primeiro
        try:
            _abre_e_checkpoint(local, tentativas, espera)
            _diz('     fundido à mão na ordem %s: recuperado' % ' + '.join(ordem))
            for g in guarda.values():
                if os.path.isfile(g):
                    os.remove(g)
            return
        except Exception as exc:                             # noqa: BLE001
            _diz('     a fusão %s não serviu (%s)' % (' + '.join(ordem), exc))
            if os.path.isfile(local + '.wal'):
                _liberar(local + '.wal')
                os.remove(local + '.wal')
            _desfaz_fusao(local, guarda)
            if origem is None:
                raise
            _liberar(local)
            os.remove(local)
            shutil.copy2(origem, local)
            _liberar(local)
    raise primeiro


def _manifest_linhas(db):
    """Linhas do `_manifest` (ou -1 quando o banco não é do armazém), abrindo só leitura."""
    con = duckdb.connect(db, read_only=True)
    try:
        if not con.execute("SELECT count(*) FROM information_schema.tables "
                           "WHERE table_schema='main' AND table_name='_manifest'").fetchone()[0]:
            return -1
        return con.execute('SELECT count(*) FROM main._manifest').fetchone()[0]
    finally:
        con.close()


def _work_dir_padrao():
    base = os.environ.get('LOCALAPPDATA') or tempfile.gettempdir()
    return os.path.join(base, 'OTC-Tracker', 'recover')


def recuperar(db, work_dir, db_dir, slim=True, carimbo=None):
    """Um banco. Devolve o resumo (dict). Levanta se qualquer conferência falhar
    — e aí o share fica como estava (a troca é o ÚLTIMO passo)."""
    irm = _store.wal_irmaos(db)
    nome = os.path.basename(db)
    local = os.path.join(work_dir, nome)
    resumo = {'db': db, 'wal_mb': sum(irm.values()) / 1e6, 'irmaos': irm}
    os.makedirs(work_dir, exist_ok=True)
    for s in ('',) + _store.WAL_SUFIXOS + ('.slim', '.novo'):
        if os.path.isfile(local + s):
            os.remove(local + s)
    # 1. para o disco local
    t0 = time.time()
    shutil.copy2(db, local)
    _liberar(local)
    copiar = _a_copiar(irm)
    if '.wal.recovery' in irm and '.wal.recovery' not in copiar:
        _diz('     descartei o .wal.recovery (%s): ele É a fusão do .wal com o '
             '.wal.checkpoint, que vão inteiros' % _mb(irm['.wal.recovery']))
    for s in copiar:
        shutil.copy2(db + s, local + s)
        _liberar(local + s)
    resumo['t_copia'] = time.time() - t0
    _diz('     copiado %s + %s de WAL em %.0fs' % (_mb(os.path.getsize(db)), _mb(sum(irm.values())),
                                                  resumo['t_copia']))
    # 2. o DuckDB recupera no local
    t0 = time.time()
    _recupera_local(local, origem=db)
    sobras = _store.wal_irmaos(local)
    if sobras:
        raise RuntimeError('%s: depois do CHECKPOINT ainda há WAL na cópia local (%s)'
                           % (db, ', '.join(sobras)))
    resumo['t_recupera'] = time.time() - t0
    resumo['manifest'] = _manifest_linhas(local)
    _diz('     recuperado em %.0fs; manifest com %s linha(s)'
         % (resumo['t_recupera'], resumo['manifest'] if resumo['manifest'] >= 0 else 'n/a'))
    # 3. magro
    resumo['slim'] = None
    if slim and resumo['manifest'] >= 0:
        r = slim_duckdb.emagrecer(local)
        if r and not r.get('pulado'):
            resumo['slim'] = r
            _diz('     emagrecido: %d tabela(s), %d apagada(s), %s → %s'
                 % (r['magras'], r['apagadas'], _mb(r['bytes_antes']), _mb(r['bytes_depois'])))
            if _manifest_linhas(local) != resumo['manifest']:
                raise RuntimeError('%s: o manifest mudou no slim — não troquei' % db)
    # 4. de volta ao share — a troca é o último passo
    t0 = time.time()
    novo = db + '.novo'
    shutil.copy2(local, novo)
    carimbo = carimbo or datetime.now().strftime('%Y%m%d-%H%M%S')
    rel = os.path.relpath(db, db_dir)
    guarda = os.path.join(db_dir, _store.RECUPERADO_DIR, carimbo, os.path.dirname(rel))
    os.makedirs(guarda, exist_ok=True)
    for s in ('',) + _store.WAL_SUFIXOS + ('.slim',):
        if os.path.isfile(db + s):
            os.replace(db + s, os.path.join(guarda, nome + s))
    os.replace(novo, db)
    resumo['guardado_em'] = guarda
    no_share = _manifest_linhas(db)
    if no_share != resumo['manifest']:
        raise RuntimeError('%s: o manifest no share tem %s linha(s) e o recuperado %s'
                           % (db, no_share, resumo['manifest']))
    resumo['t_volta'] = time.time() - t0
    resumo['bytes_depois'] = os.path.getsize(db)
    _diz('     no lugar (%s) em %.0fs; o antigo está em %s' % (_mb(resumo['bytes_depois']),
                                                              resumo['t_volta'], guarda))
    return resumo


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--db-dir', default=None, help='a pasta db/ (padrão: Config.DATABASE_DIR)')
    ap.add_argument('--only', default='', help='subcaminho dentro de db/ (padrão: tudo)')
    ap.add_argument('--work-dir', default=None,
                    help='pasta LOCAL de trabalho (padrão: %%LOCALAPPDATA%%\\OTC-Tracker\\recover)')
    ap.add_argument('--dry-run', action='store_true', help='só lista os bancos em limbo e os MB')
    ap.add_argument('--no-slim', action='store_true', help='não emagrece de caminho')
    ap.add_argument('--lock-seconds', type=int, default=30,
                    help='quanto esperar pela trava exclusiva de cada banco (padrão: 30)')
    ap.add_argument('--all', action='store_true',
                    help='recupera qualquer banco com WAL ao lado, não só os em limbo')
    args = ap.parse_args(argv)
    db_dir = args.db_dir
    if not db_dir:
        from apps.config import Config
        db_dir = Config.DATABASE_DIR
    raiz = (os.path.join(db_dir, *args.only.replace('\\', '/').strip('/').split('/'))
            if args.only else db_dir)
    work_dir = args.work_dir or _work_dir_padrao()
    alvos = []
    for pasta, dirs, arquivos in os.walk(raiz):
        dirs[:] = sorted(d for d in dirs if not d.startswith(_store.RECUPERADO_DIR))
        for a in sorted(arquivos):
            if not a.lower().endswith('.db'):
                continue
            db = os.path.join(pasta, a)
            irm = _store.wal_irmaos(db)
            if irm and (args.all or _store.wal_em_limbo(irm)):
                alvos.append((db, irm))
    _diz('%d banco(s) %s em %s%s' % (len(alvos), 'com WAL' if args.all else 'em limbo de checkpoint',
                                     raiz, ' (dry-run)' if args.dry_run else ''))
    for db, irm in alvos:
        _diz('  %s: %s' % (os.path.relpath(db, db_dir),
                           ', '.join('%s %s' % (s, _mb(b)) for s, b in sorted(irm.items()))))
    if args.dry_run or not alvos:
        return 0
    _diz('trabalho local em %s' % work_dir)
    try:
        _prova_de_renome(work_dir)
    except RuntimeError as exc:                              # noqa: BLE001
        _diz('  ERRO %s' % exc)
        return 1
    carimbo = datetime.now().strftime('%Y%m%d-%H%M%S')
    erros = []
    presos = []
    for db, _irm in alvos:
        rel = os.path.relpath(db, db_dir)
        _diz('  -> %s' % rel)
        trava = None
        t0 = time.time()
        try:
            try:
                trava = slim_duckdb._trava(db, args.lock_seconds)
            except Exception as exc:                         # noqa: BLE001
                if not _em_uso(exc):
                    raise
                presos.append(db)
                _diz('  EM USO %s — um processo VIVO ainda segura o arquivo; não toquei nele' % rel)
                continue
            recuperar(db, work_dir, db_dir, slim=not args.no_slim, carimbo=carimbo)
            _diz('  ok   %s em %.0fs' % (rel, time.time() - t0))
        except Exception:                                    # noqa: BLE001
            erros.append(db)
            _diz('  ERRO %s\n%s' % (db, traceback.format_exc()))
        finally:
            if trava is not None:
                trava.release()
    if presos:
        _diz('%d banco(s) EM USO: pare TODAS as instâncias do time (a sua inclusive) e rode de novo.\n'
             '     A trava não cai sozinha: uma instância de pé lê esses bancos em laço (summary-warm) e um\n'
             '     `store-import` preso no limbo fica MEIA HORA dentro do duckdb.connect com a trava\n'
             '     EXCLUSIVA — só o fim do processo a solta. Confira que não sobrou python.exe/waitress.'
             % len(presos))
    if erros or presos:
        _diz('%d banco(s) sem recuperar — o share ficou como estava neles' % (len(erros) + len(presos)))
        return 1
    _diz('pronto: o que foi substituído está em %s (apague depois de conferir o app)'
         % os.path.join(db_dir, _store.RECUPERADO_DIR, carimbo))
    return 0


if __name__ == '__main__':
    sys.exit(main())
