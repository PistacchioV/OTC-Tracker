#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""exporta_dados.py — tira do share uma cópia CONSISTENTE dos dados do OTC
Tracker, no formato que o Stratos recebe.

    python OTC-Tracker-Stratos\\stratos\\exporta_dados.py [--origem PASTA] [--destino PASTA_LOCAL]
                                    [--medir] [--com-json-legado] [--zip]
                                    [--sem-emagrecer] [--lock-seconds 30]
                                    [--insistir SEGUNDOS]

Roda na máquina do JPM, que enxerga o share, com o MESMO python do
`start-otc-tracker.bat` (é a versão de duckdb que escreveu os WALs). O
contêiner do Stratos não enxerga o share: os dados só chegam lá como arquivo.

`--origem` é a pasta de DADOS da instância (o `DATA_DIR` da prod, com o `db/`
dentro); o padrão é o do bloco ENV:PROD. O pacote sai em `--destino` (padrão
`%LOCALAPPDATA%\\OTC-Tracker\\exporta-stratos`, fora do Desktop de propósito:
o Desktop da máquina do JPM pode estar no OneDrive, e o pacote tem nome de
cliente, CNPJ e operação):

    otc-dados-<AAAAMMDD-HHMMSS>/
        manifest.json       o que entrou (caminho, bytes, sha256) e o que ficou de fora
        data/db/...         os bancos, um por um, já sem WAL
        data/...            o que não é banco (anexos, imagens dos tickets)

`data/` tem a MESMA forma do `data/` sob o `OTC_STRATOS_ROOT` no contêiner, que
é a pasta `otc-tracker` do Shared Drive (§681): o Stratos roda com os mesmos
bancos DuckDB, e o pacote chega lá como está, pelo `stratos file --save`, numa
pasta própria — nunca por cima dos bancos em uso. Só depois de conferido pelo
sha256 do manifest ele passa a valer como raiz.

Banco a banco:
  1. toma a trava COMPARTILHADA da camada (a mesma das leituras do app): um
     escritor de outra instância espera, e o `.db` não muda no meio da cópia;
  2. copia o `.db` com os WALs ao lado para o disco local;
  3. abre a cópia, `CHECKPOINT` (o DuckDB funde o WAL no `.db`; o limbo do
     §442 sai pela MESMA rotina do `recover_duckdb_wal.py`) e confere que não
     sobrou WAL — o pacote não carrega WAL, porque WAL de uma versão de duckdb
     replayado por outra é justamente o banco ILEGÍVEL do §442;
  4. emagrece (a forma do §437, `--sem-emagrecer` pula) e confere o `_manifest`;
  5. o banco SQLite (comitentes) vai pela API de backup do sqlite.
O share não é alterado: o máximo que ganha é o `.lock` da camada, que já existe
ao lado de todo banco que o app abriu.

O que NÃO entra: `.lock`, WALs, `_recuperado/`, sobras (`.corrupt-*`,
`.incompatible-bak`, `.slim`, `.novo`), o `_seed_stamp.txt` (a semeadura do
Stratos refaz o dela), `translations/` (vem com o código) e o JSON legado em
disco — o que a instância tem há mais de 12 meses só no disco (§434), e que
`--com-json-legado` leva junto. `--medir` diz os tamanhos antes de copiar.

Banco preso por outra instância (a trava não vem em `--lock-seconds`) fica
de fora como EM USO e o pacote sai marcado INCOMPLETO — o importador do Stratos
o recusa. O certo é rodar com as instâncias do time fechadas (fim do dia);
`--insistir 60` fica tentando os presos até a brecha aparecer.
"""
import argparse
import hashlib
import io
import json
import os
import platform
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
import zipfile
from datetime import datetime

WT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, WT)
sys.path.insert(0, os.path.join(WT, 'scripts'))

import recover_duckdb_wal as R                               # noqa: E402  (faz o chdir para a raiz)
import slim_duckdb                                           # noqa: E402
import duckdb                                                # noqa: E402
from apps.pages import data_store as _store                 # noqa: E402

# O `DATA_DIR` do bloco ENV:PROD (`git show StreamFlow-prod:apps/config.py`).
ORIGEM_PROD = (r'\\Nawest.ad.jpmorganchase.com\lac\BRA\intra\Confirmation'
               r'\Derivativos\OTC Tracker\Application\static\data')

FORMATO = 1
FORA_DO_DB = ('.lock', '.lock.w', '.slim', '.novo', '.orig', '.descartado') + _store.WAL_SUFIXOS
LIXO = {'thumbs.db', 'desktop.ini', '.ds_store'}


def _diz(msg):
    print(msg, flush=True)


def _mb(n):
    return '%.1f MB' % (n / 1e6)


def _sha256(caminho):
    h = hashlib.sha256()
    with io.open(caminho, 'rb') as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b''):
            h.update(bloco)
    return h.hexdigest()


def _motor(caminho):
    """'duckdb', 'sqlite' ou None, pelo CABEÇALHO (o nome não diz: os dois são `.db`)."""
    try:
        with io.open(caminho, 'rb') as fh:
            cab = fh.read(16)
    except OSError:
        return None
    if cab.startswith(b'SQLite format 3\x00'):
        return 'sqlite'
    if cab[8:12] == b'DUCK':
        return 'duckdb'
    return None


def _rel(caminho, raiz):
    return os.path.relpath(caminho, raiz).replace(os.sep, '/')


def _pula_nome(nome):
    n = nome.lower()
    return n in LIXO or n.startswith('~$') or n.startswith('_test')


def inventario(origem, com_json=False):
    """O que vai para o pacote: (bancos, arquivos, fora). `bancos` e `arquivos`
    são caminhos absolutos; `fora` é [(rel, motivo)] do que fica de fora e por quê
    — o JSON legado entra como UMA linha com a contagem (são milhares de dias)."""
    db_dir = os.path.join(origem, 'db')
    bancos, arquivos, fora = [], [], []
    json_fora = [0, 0]
    for pasta, dirs, nomes in os.walk(db_dir):
        for d in list(dirs):
            if d.startswith(_store.RECUPERADO_DIR) or _pula_nome(d):
                fora.append((_rel(os.path.join(pasta, d), origem) + '/', 'sobra de recuperação/teste'))
        dirs[:] = sorted(d for d in dirs
                         if not d.startswith(_store.RECUPERADO_DIR) and not _pula_nome(d))
        for nome in sorted(nomes):
            caminho = os.path.join(pasta, nome)
            baixo = nome.lower()
            if baixo.endswith('.db') and not _pula_nome(nome):
                bancos.append(caminho)
            elif not any(baixo.endswith(s) for s in FORA_DO_DB):
                fora.append((_rel(caminho, origem), 'não é banco (o .db vai sem sobras)'))
    for pasta, dirs, nomes in os.walk(origem):
        if os.path.normcase(os.path.abspath(pasta)) == os.path.normcase(os.path.abspath(origem)):
            dirs[:] = [d for d in dirs if d.lower() not in ('db', 'translations')]
        dirs[:] = sorted(d for d in dirs if not _pula_nome(d))
        for nome in sorted(nomes):
            caminho = os.path.join(pasta, nome)
            baixo = nome.lower()
            if _pula_nome(nome) or baixo.endswith('.lock') or baixo.endswith('.lock.w'):
                continue
            if baixo.endswith('.json') and not com_json:
                json_fora[0] += 1
                json_fora[1] += _tamanho(caminho)
                continue
            arquivos.append(caminho)
    if json_fora[0]:
        fora.append(('*.json (%d arquivo(s), %s)' % (json_fora[0], _mb(json_fora[1])),
                     'json legado em disco: --com-json-legado leva'))
    return bancos, arquivos, fora


def _tamanho(caminho):
    try:
        return os.path.getsize(caminho)
    except OSError:
        return 0


def medir(origem, com_json):
    bancos, arquivos, fora = inventario(origem, com_json=True)
    por_area = {}
    for db in bancos:
        partes = _rel(db, os.path.join(origem, 'db')).split('/')
        area = partes[0] if len(partes) > 1 else '(raiz do db)'
        n, b, w = por_area.get(area, (0, 0, 0))
        wal = sum(_store.wal_irmaos(db).values())
        por_area[area] = (n + 1, b + _tamanho(db), w + wal)
    _diz('bancos em %s:' % os.path.join(origem, 'db'))
    tot_b = tot_w = 0
    for area in sorted(por_area):
        n, b, w = por_area[area]
        tot_b += b
        tot_w += w
        _diz('  %-34s %5d banco(s)  %12s  + WAL %s' % (area, n, _mb(b), _mb(w)))
    _diz('  %-34s %5d banco(s)  %12s  + WAL %s' % ('TOTAL', len(bancos), _mb(tot_b), _mb(tot_w)))
    js = [a for a in arquivos if a.lower().endswith('.json')]
    outros = [a for a in arquivos if not a.lower().endswith('.json')]
    _diz('fora do db: %d arquivo(s), %s' % (len(outros), _mb(sum(_tamanho(a) for a in outros))))
    _diz('json legado em disco: %d arquivo(s), %s %s'
         % (len(js), _mb(sum(_tamanho(a) for a in js)),
            '(entra: --com-json-legado)' if com_json else '(fica de fora; --com-json-legado leva)'))
    _diz('sobras que não vão: %d' % len(fora))
    return 0


def _copia_duckdb(db, local, emagrecer):
    """Cópia local consistente, SEM WAL. Devolve o resumo; levanta se não fechar."""
    irm = _store.wal_irmaos(db)
    for s in ('',) + _store.WAL_SUFIXOS + ('.slim',):
        if os.path.isfile(local + s):
            R._liberar(local + s)
            os.remove(local + s)
    shutil.copy2(db, local)
    R._liberar(local)
    for s in R._a_copiar(irm):
        shutil.copy2(db + s, local + s)
        R._liberar(local + s)
    wal = sum(irm.values())
    R._recupera_local(local, origem=db, descartar=False)
    sobras = R._resolve_sobra_recovery(local, irm.get('.wal', 0) + irm.get('.wal.checkpoint', 0))
    if sobras:
        raise RuntimeError('depois do CHECKPOINT ainda há WAL na cópia (%s)' % ', '.join(sorted(sobras)))
    linhas = R._manifest_linhas(local)
    resumo = {'wal_fundido': wal, 'manifest': linhas}
    if emagrecer and linhas >= 0:
        r = slim_duckdb.emagrecer(local)
        if r and not r.get('pulado'):
            if R._manifest_linhas(local) != linhas:
                raise RuntimeError('o _manifest mudou no emagrecimento')
            resumo['emagrecido'] = [r['bytes_antes'], r['bytes_depois']]
    con = duckdb.connect(local, read_only=True)
    try:
        resumo['tabelas'] = con.execute('SELECT count(*) FROM duckdb_tables()').fetchone()[0]
    finally:
        con.close()
    if _store.wal_irmaos(local):
        raise RuntimeError('a conferência deixou WAL na cópia')
    return resumo


def _copia_sqlite(db, local):
    if os.path.isfile(local):
        os.remove(local)
    src = sqlite3.connect(db, timeout=30)
    try:
        dst = sqlite3.connect(local)
        try:
            src.backup(dst)
            ok = dst.execute('PRAGMA integrity_check').fetchone()[0]
            tabelas = dst.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        finally:
            dst.close()
    finally:
        src.close()
    if ok != 'ok':
        raise RuntimeError('integrity_check da cópia: %s' % ok)
    for s in ('-wal', '-shm', '-journal'):
        if os.path.isfile(local + s):
            os.remove(local + s)
    return {'tabelas': tabelas}


def _trava(db, segundos, motor):
    try:
        from apps.pages import database_access as DA
    except ImportError:
        return None
    return DA.hold_file_lock(db, write=False, timeout_seconds=segundos,
                             engine='sqlite' if motor == 'sqlite' else 'duckdb')


def exportar(origem, destino, com_json=False, emagrecer=True, lock_seconds=30,
             insistir=0, compactar=False, carimbo=None):
    """Monta o pacote. Devolve (pasta do pacote, manifest)."""
    carimbo = carimbo or datetime.now().strftime('%Y%m%d-%H%M%S')
    pacote = os.path.join(destino, 'otc-dados-%s' % carimbo)
    data = os.path.join(pacote, 'data')
    bancos, arquivos, fora = inventario(origem, com_json=com_json)
    previsto = sum(_tamanho(b) + sum(_store.wal_irmaos(b).values()) for b in bancos) \
        + sum(_tamanho(a) for a in arquivos)
    os.makedirs(pacote, exist_ok=True)
    livre = shutil.disk_usage(pacote).free
    if livre < previsto * (2.2 if compactar else 1.2):
        raise RuntimeError('espaço livre em %s: %s; o pacote pede uns %s%s'
                           % (destino, _mb(livre), _mb(previsto), ' (x2 com --zip)' if compactar else ''))
    try:
        R._prova_de_renome(pacote)
    except RuntimeError as exc:
        raise RuntimeError(str(exc).replace('--work-dir C:\\Temp\\otc-recover',
                                            '--destino C:\\Temp\\otc-exporta'))
    _diz('%d banco(s) e %d arquivo(s) de %s (%s) -> %s'
         % (len(bancos), len(arquivos), origem, _mb(previsto), pacote))

    entradas, pulados, erros = [], [], []

    def _um_banco(db):
        rel = _rel(db, origem)
        local = os.path.join(data, *rel.split('/'))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        motor = _motor(db)
        if motor is None:
            pulados.append({'caminho': rel, 'motivo': 'vazio ou formato desconhecido'})
            _diz('  pulei %s: não é DuckDB nem SQLite' % rel)
            return 'ok'
        t0 = time.time()
        try:
            trava = _trava(db, lock_seconds, motor)
        except Exception as exc:                             # noqa: BLE001
            if not R._em_uso(exc):
                raise
            return 'preso'
        try:
            resumo = _copia_duckdb(db, local, emagrecer) if motor == 'duckdb' else _copia_sqlite(db, local)
        finally:
            if trava is not None:
                trava.release()
        entradas.append(dict(caminho='data/' + rel, tipo=motor, bytes=os.path.getsize(local),
                             sha256=_sha256(local), **resumo))
        _diz('  ok   %s (%s, %s) em %.0fs' % (rel, motor, _mb(os.path.getsize(local)), time.time() - t0))
        return 'ok'

    def _rodada(lista):
        presos = []
        for db in lista:
            try:
                if _um_banco(db) == 'preso':
                    presos.append(db)
                    _diz('  EM USO %s — outra instância segura a trava' % _rel(db, origem))
            except Exception:                                # noqa: BLE001
                erros.append({'caminho': _rel(db, origem), 'motivo': traceback.format_exc()})
                _diz('  ERRO %s\n%s' % (_rel(db, origem), traceback.format_exc()))
        return presos

    presos = _rodada(bancos)
    while presos and insistir:
        _diz('%d banco(s) EM USO; nova tentativa em %ds (Ctrl+C para parar)' % (len(presos), insistir))
        try:
            time.sleep(insistir)
        except KeyboardInterrupt:
            break
        presos = _rodada(presos)
    for db in presos:
        pulados.append({'caminho': _rel(db, origem), 'motivo': 'EM USO: outra instância segurava a trava'})

    for a in arquivos:
        rel = _rel(a, origem)
        local = os.path.join(data, *rel.split('/'))
        os.makedirs(os.path.dirname(local), exist_ok=True)
        try:
            shutil.copy2(a, local)
            R._liberar(local)
        except OSError as exc:
            erros.append({'caminho': rel, 'motivo': str(exc)})
            continue
        entradas.append({'caminho': 'data/' + rel, 'tipo': 'arquivo',
                         'bytes': os.path.getsize(local), 'sha256': _sha256(local)})

    manifest = {
        'formato': FORMATO,
        'criado_em': datetime.now().isoformat(timespec='seconds'),
        'origem': origem,
        'maquina': platform.node(),
        'duckdb': duckdb.__version__,
        'python': platform.python_version(),
        'completo': not erros and not any(p['motivo'].startswith('EM USO') for p in pulados),
        'arquivos': entradas,
        'pulados': pulados,
        'erros': erros,
        'fora': [{'caminho': r, 'motivo': m} for r, m in fora],
    }
    with io.open(os.path.join(pacote, 'manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    if compactar:
        _zipa(pacote)
    return pacote, manifest


def _zipa(pacote):
    alvo = pacote + '.zip'
    t0 = time.time()
    with zipfile.ZipFile(alvo + '.parcial', 'w', zipfile.ZIP_DEFLATED, allowZip64=True,
                         compresslevel=6) as z:
        for pasta, _dirs, nomes in os.walk(pacote):
            for nome in sorted(nomes):
                caminho = os.path.join(pasta, nome)
                z.write(caminho, _rel(caminho, pacote))
    os.replace(alvo + '.parcial', alvo)
    _diz('zip: %s (%s) em %.0fs' % (alvo, _mb(os.path.getsize(alvo)), time.time() - t0))
    return alvo


def _destino_padrao():
    base = os.environ.get('LOCALAPPDATA') or tempfile.gettempdir()
    return os.path.join(base, 'OTC-Tracker', 'exporta-stratos')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--origem', default=None,
                    help='a pasta de dados da instância, com o db/ dentro (padrão: a da prod)')
    ap.add_argument('--destino', default=None,
                    help='pasta LOCAL do pacote (padrão: %%LOCALAPPDATA%%\\OTC-Tracker\\exporta-stratos)')
    ap.add_argument('--medir', action='store_true', help='só diz quantos bancos e quantos MB')
    ap.add_argument('--com-json-legado', action='store_true',
                    help='leva também o JSON que só existe em disco (o histórico fora dos bancos)')
    ap.add_argument('--zip', action='store_true', help='compacta o pacote num .zip ao lado')
    ap.add_argument('--sem-emagrecer', action='store_true', help='não leva os bancos à forma do §437')
    ap.add_argument('--lock-seconds', type=int, default=30,
                    help='quanto esperar pela trava de cada banco (padrão: 30)')
    ap.add_argument('--insistir', type=int, default=0, metavar='SEGUNDOS',
                    help='fica tentando os bancos EM USO a cada N segundos')
    args = ap.parse_args(argv)
    origem = os.path.normpath(args.origem or os.environ.get('OTC_EXPORTA_ORIGEM') or ORIGEM_PROD)
    if not os.path.isdir(os.path.join(origem, 'db')):
        _diz('ERRO: %s não tem a pasta db/ — é a pasta de DADOS da instância? (--origem)' % origem)
        return 1
    if args.medir:
        return medir(origem, args.com_json_legado)
    try:
        pacote, man = exportar(origem, os.path.normpath(args.destino or _destino_padrao()),
                               com_json=args.com_json_legado, emagrecer=not args.sem_emagrecer,
                               lock_seconds=args.lock_seconds, insistir=args.insistir,
                               compactar=args.zip)
    except RuntimeError as exc:
        _diz('ERRO %s' % exc)
        return 1
    total = sum(e['bytes'] for e in man['arquivos'])
    _diz('%d item(ns), %s, duckdb %s' % (len(man['arquivos']), _mb(total), man['duckdb']))
    for p in man['pulados']:
        _diz('  fora: %s — %s' % (p['caminho'], p['motivo']))
    if not man['completo']:
        _diz('INCOMPLETO: %d erro(s), %d banco(s) em uso. O Stratos recusa este pacote;\n'
             '     feche as instâncias do time e rode de novo (ou --insistir 60).'
             % (len(man['erros']), sum(1 for p in man['pulados'] if p['motivo'].startswith('EM USO'))))
        return 1
    _diz('pronto: %s' % pacote)
    return 0


if __name__ == '__main__':
    sys.exit(main())
