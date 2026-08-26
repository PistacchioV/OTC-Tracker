"""O mesmo aviso nao pode sair DUAS vezes.

O evento chega ao usuario por dois caminhos: o `push` do service worker
(`sw-push.js`) e o `maybeNativeNotify` do `topbar.html`. Com a aba ABERTA e sem
foco, os dois disparavam — duas notificacoes para a mesma coisa —, e como as
`tag` eram diferentes (`otc-activity` no worker, `otc-<id>` na pagina) o
navegador nem as sobrepunha: apareciam uma embaixo da outra. O relato veio com
as duas visiveis, uma no formato novo e outra no antigo, porque a pagina ja
estava atualizada e o worker registrado ainda era o velho.

A regra: com uma janela do app aberta, quem avisa e a PAGINA — ela tem o
`notification` inteiro, sabe o id, marca como lida no clique e navega sem
recarregar. O push existe para quando NAO ha janela.

Roda o `sw-push.js` DE VERDADE no JavaScriptCore, com um `self` falso. Como o
`check_boxparse.py`, ele depende do `jsc` do macOS e nao roda na maquina Windows
do time.
"""
import io
import os
import subprocess
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
os.chdir(ROOT)

JSC = '/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc'

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


if not os.path.exists(JSC):
    print('  --  jsc ausente (so no macOS): nada a rodar')
    sys.exit(0)

HARNESS = r'''
var mostradas = [], JANELAS = [], RESPOSTA = null, FETCH_FALHA = false;
var self = {
  _ev: {},
  addEventListener: function (n, f) { this._ev[n] = f; },
  clients: { matchAll: function () { return Promise.resolve(JANELAS); } },
  registration: { showNotification: function (t, o) {
      mostradas.push({ title: t, tag: o.tag, icon: o.icon }); return Promise.resolve(); } },
  skipWaiting: function () {}
};
function fetch() {
  if (FETCH_FALHA) { return Promise.reject(new Error('rede')); }
  return Promise.resolve({ ok: true, json: function () { return Promise.resolve(RESPOSTA); } });
}
var pendente = [];
load('apps/static/js/sw-push.js');
var saida = [];
function cenario(rot, janelas, resp, falha) {
  mostradas = []; JANELAS = janelas; RESPOSTA = resp; FETCH_FALHA = !!falha; pendente = [];
  self._ev['push']({ waitUntil: function (p) { pendente.push(p); } });
  return Promise.all(pendente).then(function () {
    saida.push(rot + '|' + mostradas.length + '|' +
               mostradas.map(function (m) { return m.tag; }).join(','));
  });
}
var N = { success: true, notifications: [{ id: 42, actor_name: 'Fulano',
          action: 'Manual Confirmation', page: 'Confirmation', detail: 'Validated by OTC' }] };
cenario('sem_janela', [], N)
  .then(function () { return cenario('com_janela', [{ id: 1 }], N); })
  .then(function () { return cenario('com_janela_fetch_falha', [{ id: 1 }], null, true); })
  .then(function () { return cenario('sem_janela_fetch_falha', [], null, true); })
  .then(function () { print(saida.join('\n')); });
'''

f = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8')
f.write(HARNESS)
f.close()
r = subprocess.run([JSC, f.name], capture_output=True, text=True, cwd=ROOT)
os.unlink(f.name)
if r.returncode != 0:
    print(' FAIL o sw-push.js nao rodou:\n' + (r.stderr or r.stdout)[:500])
    sys.exit(1)

res = {}
for linha in r.stdout.strip().split('\n'):
    if '|' not in linha:
        continue
    rot, n, tags = linha.split('|')
    res[rot] = (int(n), tags)

print('== quem avisa, e quantas vezes ==')
# O push existe para quando NAO ha janela. Zero aqui e o aviso sumindo.
check('sem janela: o push avisa', res.get('sem_janela', (None,))[0], 1)
# Com janela, a pagina cuida. Um aqui e a notificacao DUPLICADA do relato.
check('com janela: o push se cala', res.get('com_janela', (None,))[0], 0)
# O `.catch` tambem tem de respeitar a janela: sem isso a duplicata volta
# justamente no caminho de erro, que e o que ninguem testa.
check('com janela e fetch falhando: continua calado',
      res.get('com_janela_fetch_falha', (None,))[0], 0)
check('sem janela e fetch falhando: avisa o generico',
      res.get('sem_janela_fetch_falha', (None,))[0], 1)

print('\n== a tag e a mesma dos dois lados ==')
# Cinto de seguranca: se a janela fechar entre a checagem e o showNotification,
# a tag igual faz o navegador SOBREPOR em vez de empilhar.
check('o push usa otc-<id>', res.get('sem_janela', (0, ''))[1], 'otc-42')
_topbar = io.open(os.path.join(ROOT, 'apps', 'templates', 'partials', 'topbar.html'),
                  encoding='utf-8').read()
check('e o topbar tambem', "tag: 'otc-' + (Number(n.id) || 0)" in _topbar, True)
# O worker registrado pode ficar horas atras da pagina — foi o que fez o balao
# sair no formato novo por um caminho e no antigo pelo outro.
check('o topbar pede a checagem de versao do worker', 'reg.update()' in _topbar, True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
