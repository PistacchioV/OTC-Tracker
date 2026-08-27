"""Recon Comitente: os quatro desfechos de banco, e o que cada um responde.

Sao caminhos de ERRO — nunca rodam num dia normal, e por isso apodrecem calados.
O que cada um decide:

1. **`DatabaseLockTimeout` → 503 + `retryable`.** O banco esta OCUPADO, nao
   quebrado: a tela pode tentar de novo sozinha. Com 500 ela desiste, e o
   operador reexecuta a rotina inteira por causa de uma espera de segundos.

2. **`TransactionOutcomeUnknown` → 500 + `outcome_unknown` + `operation_id`.** O
   pior desfecho: a gravacao PODE ter acontecido. Reexecutar as cegas duplicaria
   a reconciliacao do dia; nao reexecutar pode deixa-la pela metade. A resposta
   NAO escolhe por quem opera — ela diz que o resultado e desconhecido e devolve
   o identificador para a conferencia.

   E a verificacao de integridade que falha nao pode derrubar a resposta: aqui a
   maquina pode nem ter o arquivo do banco. `integrity_ok=False` diz "nao deu
   para confirmar", que e justamente o que o operador precisa saber.

3. **`DatabaseCleanupError` → 500 dizendo que a reconciliacao CONCLUIU.** O que
   falhou foi soltar o recurso depois. Sem essa distincao o operador refaz um
   trabalho que ja esta feito.

4. Qualquer outra → 500 generico, com o traceback no log e uma frase na tela.

Nao encosta em rede nem em banco real: as funcoes do modulo sao stubadas.
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# Fora do Windows o share tem de ser absoluto para o `Config` importar (§8), e
# desde que as recons perguntam a raiz ao Config isto vale para elas também.
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))

from apps import create_app                                  # noqa: E402
from apps.config import DebugConfig                          # noqa: E402
from apps.pages import routes as R
# As rotas moram em features/recon_comitente desde a extracao.
from apps.pages.features.recon_comitente import entrypoint as CE  # noqa: E402                           # noqa: E402
from apps.pages import recon_comitente as RC                 # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label
          + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


app = create_app(DebugConfig)

CASOS = [
    ('DatabaseLockTimeout',       R.DatabaseLockTimeout(RC.DB_PATH, 'write', 30.0)),
    ('TransactionOutcomeUnknown', R.TransactionOutcomeUnknown(RC.DB_PATH, 'op-abc123')),
    ('DatabaseCleanupError',      R.DatabaseCleanupError('cleanup')),
    ('Exception',                 RuntimeError('qualquer outra')),
]


def chamar(endpoint, exc, stub):
    def boom(*a, **k):
        raise exc
    setattr(RC, stub, boom)
    url = '/reconciliation-comitente/' + ('data' if endpoint == 'data' else 'run')
    kw = {} if endpoint == 'data' else {
        'method': 'POST', 'data': {'mode': 'auto', 'recon_date': '2026-08-18'}}
    with app.test_request_context(url, **kw):
        from flask import session
        session['authenticated'] = True
        fn = CE.reconciliation_comitente_data if endpoint == 'data' else CE.reconciliation_comitente_run
        r = fn()
    body, status = (r if isinstance(r, tuple) else (r, 200))
    return status, body.get_json()


_orig = {'load': RC.load_from_db, 'run': RC.run_auto}
try:
    print('== 1. /data — o status separa ocupado de quebrado ==')
    for nome, exc in CASOS:
        st, j = chamar('data', exc, 'load_from_db')
        esperado = 503 if nome == 'DatabaseLockTimeout' else 500
        check('%-28s responde %s' % (nome, esperado), st, esperado)
        if nome == 'DatabaseLockTimeout':
            # `retryable` e o que autoriza a tela a tentar de novo sozinha.
            check('   e marca retryable', j.get('retryable'), True)
        else:
            check('   e NAO marca retryable', j.get('retryable'), None)
    # A mensagem da tela nao repete o `str(e)`: excecao de banco carrega caminho
    # de arquivo e hostname, e isso nao vai para a tela do usuario.
    _st, j = chamar('data', RuntimeError('/caminho/secreto/db.sqlite3'), 'load_from_db')
    check('a mensagem generica nao vaza o texto da excecao',
          '/caminho/secreto' in str(j.get('error', '')), False)

    print('\n== 2. /run — o desfecho DESCONHECIDO e o mais importante ==')
    for nome, exc in CASOS:
        st, j = chamar('run', exc, 'run_auto')
        esperado = 503 if nome == 'DatabaseLockTimeout' else 500
        check('%-28s responde %s' % (nome, esperado), st, esperado)
    st, j = chamar('run', R.TransactionOutcomeUnknown(RC.DB_PATH, 'op-abc123'), 'run_auto')
    # Sem o `operation_id` a conferencia operacional nao tem por onde comecar.
    check('o outcome desconhecido se declara', j.get('outcome_unknown'), True)
    check('   e devolve o operation_id', j.get('operation_id'), 'op-abc123')
    # A verificacao de integridade pode falhar (a maquina pode nem ter o arquivo
    # do banco): `False` e uma resposta, nao um erro — a rota nao pode cair nela.
    check('   e o integrity_ok vem preenchido, mesmo sem o banco em disco',
          isinstance(j.get('integrity_ok'), bool), True)
    check('   a frase manda NAO reexecutar antes de conferir',
          'Não execute novamente' in j.get('error', ''), True)
    # Cleanup e o unico 500 que diz que o trabalho FOI feito.
    _st, j = chamar('run', R.DatabaseCleanupError('cleanup'), 'run_auto')
    check('o cleanup diz que a reconciliacao CONCLUIU',
          'foi concluída' in j.get('error', ''), True)

    print('\n== 3. FileNotFoundError continua sendo o caminho de sempre ==')
    # Ele vem ANTES dos de banco e nao e erro: e a rotina dizendo que o insumo do
    # dia ainda nao chegou, e a tela mostra isso de outro jeito.
    st, j = chamar('run', FileNotFoundError('falta o arquivo'), 'run_auto')
    check('arquivo ausente nao vira 500', st, 200)
    check('   e se anuncia com not_found', j.get('not_found'), True)
finally:
    RC.load_from_db, RC.run_auto = _orig['load'], _orig['run']

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
