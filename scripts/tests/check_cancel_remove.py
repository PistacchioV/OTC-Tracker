"""Testa _nd_cancel_in_file recortada de routes.py (sem subir o app).

Regra: cancelamento na API apaga a linha, EXCETO Success com B3 ID preenchido,
que vira Canceled e continua visivel.
"""
import io, json, os, re, sys, tempfile, threading

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))   # scripts/tests/ -> raiz do repo
SRC = os.path.join(ROOT, 'apps', 'pages', 'routes.py')
src = io.open(SRC, encoding='utf-8').read()

m = re.search(r'^def _nd_cancel_in_file\(.*?(?=\n\ndef )', src, re.S | re.M)
assert m, 'nao achei _nd_cancel_in_file'
ns = {'os': os, 'json': json, '_cache_lock': threading.RLock()}
def _atomic_write_json(p, data):
    with io.open(p, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
ns['_atomic_write_json'] = _atomic_write_json
exec(compile(m.group(0), 'cut', 'exec'), ns)
fn = ns['_nd_cancel_in_file']

tmp = tempfile.mkdtemp()
fails = []
def case(name, rows, deal, exp_removed, exp_marked, exp_left_status):
    p = os.path.join(tmp, re.sub(r'\W+', '_', name) + '.json')
    with io.open(p, 'w', encoding='utf-8') as fh:
        json.dump(rows, fh)
    got = fn(p, deal)
    left = json.load(io.open(p, encoding='utf-8'))
    left_st = [(d.get('Deal'), d.get('Status')) for d in left]
    ok = got == (exp_removed, exp_marked) and left_st == exp_left_status
    print(('  ok  ' if ok else ' FAIL ') + name)
    if not ok:
        print('        retorno  esperado=%r  obtido=%r' % ((exp_removed, exp_marked), got))
        print('        restante esperado=%r  obtido=%r' % (exp_left_status, left_st))
        fails.append(name)

D = lambda deal, st, b3='': {'Deal': deal, 'Client': 'ACME', 'Status': st, 'B3_ID': b3}

print('\n-- linhas que devem SAIR da tabela --')
case('New sai',            [D('D1', 'New')],                  'D1', 1, 0, [])
case('Amend sai',          [D('D1', 'Amend')],                'D1', 1, 0, [])
case('Pending sai',        [D('D1', 'Pending')],              'D1', 1, 0, [])
case('Approved sai',       [D('D1', 'Approved')],             'D1', 1, 0, [])
case('Sent sai',           [D('D1', 'Sent')],                 'D1', 1, 0, [])
case('Error sai',          [D('D1', 'Error')],                'D1', 1, 0, [])
case('Success SEM B3 sai', [D('D1', 'Success')],              'D1', 1, 0, [])
case('Success B3 vazio',   [D('D1', 'Success', '   ')],       'D1', 1, 0, [])

print('\n-- a unica excecao: ja registrado na B3 --')
case('Success COM B3 fica Canceled', [D('D1', 'Success', 'B3-77')], 'D1', 0, 1,
     [('D1', 'Canceled')])

print('\n-- idempotencia e escopo --')
case('ja Canceled nao mexe',  [D('D1', 'Canceled')],           'D1', 0, 0, [('D1', 'Canceled')])
case('outro deal intocado',   [D('D1', 'New'), D('D2', 'New')],'D1', 1, 0, [('D2', 'New')])
case('deal inexistente',      [D('D2', 'New')],                'D9', 0, 0, [('D2', 'New')])
case('duas pernas do mesmo deal', [D('D1', 'New'), D('D1', 'Sent')], 'D1', 2, 0, [])
case('perna registrada + perna nao',
     [D('D1', 'Success', 'B3-1'), D('D1', 'New')], 'D1', 1, 1, [('D1', 'Canceled')])

print('\n-- arquivo ausente --')
r = fn(os.path.join(tmp, 'nao_existe.json'), 'D1')
print(('  ok  ' if r == (0, 0) else ' FAIL ') + 'arquivo ausente devolve (0,0) -> %r' % (r,))
if r != (0, 0):
    fails.append('arquivo ausente')

r = fn(os.path.join(tmp, 'x.json'), '')
print(('  ok  ' if r == (0, 0) else ' FAIL ') + 'deal vazio devolve (0,0) -> %r' % (r,))
if r != (0, 0):
    fails.append('deal vazio')

print('\n%s' % ('TODOS OS CASOS PASSARAM' if not fails else 'FALHAS: %r' % fails))
sys.exit(1 if fails else 0)
