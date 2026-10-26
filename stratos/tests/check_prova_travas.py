"""Confere a prova das travas do Shared Drive (stratos/src/prova_travas.py, HANDOFF §681).

Num disco local as travas valem, e o que se confere é que a prova DIZ isso e
que ela ACUSA o caso que o NFS costuma trazer:

  1. modo local: as onze conferências passam e a pasta da rodada some;
  2. com `OTC_PROVA_LOCKER=lockf` (as travas POSIX que o Linux usa por baixo
     do flock num NFS) as três `mesmo_processo_*` falham, as outras passam, e
     o veredito diz que a trava é do processo;
  3. segurar → conferir → soltar: o segundo request acha as travas presas, o
     mesmo host é "inconclusivo", e o soltar as libera.

    python stratos/tests/check_prova_travas.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
PROVA = os.path.join(os.path.dirname(AQUI), 'src', 'prova_travas.py')

FALHAS = []


def ok(cond, msg):
    print(('ok    ' if cond else 'FAIL  ') + msg)
    if not cond:
        FALHAS.append(msg)


def roda(pasta, *args, **env):
    e = dict(os.environ, **env)
    r = subprocess.run([sys.executable, PROVA, '--pasta', pasta] + list(args),
                       capture_output=True, text=True, env=e, timeout=180)
    try:
        return r.returncode, json.loads(r.stdout)
    except ValueError:
        return r.returncode, {'stderr': r.stderr[-800:]}


def main():
    tmp = tempfile.mkdtemp(prefix='otc-prova-')
    try:
        base = os.path.join(tmp, 'prova-travas')
        db_dir = os.path.join(tmp, 'db')
        os.makedirs(os.path.join(db_dir, 'mappings'))
        os.makedirs(os.path.join(db_dir, 'cache'))
        import duckdb
        for rel in ('mappings/x.db', 'cache/y.db'):
            con = duckdb.connect(os.path.join(db_dir, rel))
            con.execute('CREATE TABLE _manifest AS SELECT 1 AS a')
            con.close()

        # 1. Disco local
        rc, d = roda(base, '--db-dir', db_dir)
        casos = {c['teste']: c for c in d.get('casos', ())}
        ok(rc == 0 and d.get('veredito') == 'as travas valem' and len(casos) == 11,
           'local: as onze conferencias passam (%s %s)' % (d.get('veredito'), d.get('falhas')
                                                            or d.get('stderr')))
        ok(not [n for n in os.listdir(base) if n.startswith('rodada-')],
           'local: a pasta da rodada e apagada no fim')
        t = d.get('tempos') or {}
        ok(t.get('banco_de_dia', {}).get('banco') == os.path.join('cache', 'y.db')
           and t.get('banco_de_cadastro', {}).get('manifest') == 1,
           'local: mede um banco de dia e um de cadastro (%s)' % t)
        ok([h['host'] for h in d.get('hosts_vistos', ())] == [d.get('host')],
           'local: o host da rodada entra nos hosts vistos')

        # 2. Trava POSIX (o NFS)
        rc, d = roda(base, OTC_PROVA_LOCKER='lockf')
        falhas = sorted(d.get('falhas') or ())
        ok(rc == 1 and falhas == ['mesmo_processo_exclusiva_segue',
                                   'mesmo_processo_fechar_outro_descritor',
                                   'mesmo_processo_segundo_descritor'],
           'lockf: acusa as tres do mesmo processo e so elas (%s)' % falhas)
        ok('do PROCESSO' in (d.get('veredito') or ''), 'lockf: o veredito diz que a trava e do processo')

        # 3. Entre requests
        rc, d = roda(base, '--modo', 'conferir')
        ok('segurar primeiro' in (d.get('veredito') or ''), 'conferir sem segurar: diz o que fazer')
        rc, d = roda(base, '--modo', 'segurar', '--segundos', '60')
        seg = d.get('segurando') or {}
        ok(rc == 0 and seg.get('pid') and seg.get('ate', 0) > time.time(),
           'segurar: volta com o processo segurando (%s)' % (seg or d.get('stderr')))
        rc, d2 = roda(base, '--modo', 'segurar', '--segundos', '60')
        ok((d2.get('segurando') or {}).get('pid') == seg.get('pid') and d2.get('aviso'),
           'segurar de novo: nao abre um segundo processo')
        rc, d = roda(base, '--modo', 'conferir', '--soltar')
        ok(rc == 0 and len(d.get('casos') or ()) == 4 and all(c['ok'] for c in d['casos']),
           'conferir: as travas do outro request estao presas (%s)' % d.get('falhas'))
        ok(d.get('mesmo_conteiner') is True and d.get('veredito', '').startswith('inconclusivo'),
           'conferir no mesmo host: inconclusivo')
        ate = time.time() + 15
        while time.time() < ate and os.path.exists(os.path.join(base, 'cruzada', 'segurando.json')):
            time.sleep(0.1)
        rc, d = roda(base, '--modo', 'conferir')
        ok('segurar primeiro' in (d.get('veredito') or ''), 'soltar: o processo solta e sai')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('\n%d falha(s)' % len(FALHAS))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
