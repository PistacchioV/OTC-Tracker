#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""split_notifications_db.py — separa as notificações do banco de usuários.

    python scripts/split_notifications_db.py --dry-run   # só relata
    python scripts/split_notifications_db.py             # executa

**Você provavelmente não precisa rodar isto.** A separação acontece SOZINHA na
primeira subida do app depois do pull: o `_ensure_notif_db` cria o
`Notifications_OTCTracker.db` ao lado do de usuários e copia `notifications` e
`push_subscriptions` do arquivo antigo. Foi feito assim de propósito — "rode
este script depois do pull" é a forma mais confiável de a mesa ficar sem o sino,
e já aconteceu com as migrações do Pending Confirmation.

Este script existe para o **--dry-run**: ele mostra o que vai ser copiado ANTES
de você reiniciar a instância, sem tocar em nada. É a resposta para "quantas
notificações eu tenho, e elas vão sobreviver?".

Ele roda na MÁQUINA EM QUE OS BANCOS ESTÃO, e lê os caminhos do `Config` — na
dev, os bancos da dev; na instância do JPM, os do share. Nenhum dado sai de uma
máquina para outra, e nenhum caminho é montado aqui.

Por que separar:

    O lock da camada de acesso é por ARQUIVO. Com as quatro tabelas num só
    DuckDB, cada gravação de notificação — e elas acontecem a cada ação de
    qualquer pessoa da mesa — segurava o arquivo inteiro em modo EXCLUSIVO, e
    com ele o login, a allowlist do Page_Access e a gestão de usuários. Some o
    sino, que consulta por aba aberta: o banco vivia travado, e o que travava
    não era o dado que importa, era o aviso.

O que ele NÃO faz: apagar as tabelas do banco antigo. Elas ficam lá como backup
— o custo são algumas dezenas de KB num arquivo que ninguém mais lê, e o ganho
é poder voltar atrás. A cópia é idempotente (pula o que já está no destino),
então rodar de novo não duplica nada.
"""

import argparse
import os
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Fora do Windows o `Config` exige o share absoluto (§8), e este script não
# encosta no share — só nos bancos.
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.gettempdir())

from apps.config import Config                                      # noqa: E402

TABELAS = (('notifications', 'id'), ('push_subscriptions', 'endpoint'))


def conta(caminho, tabela):
    """(linhas, erro) de uma tabela, sem criar nada."""
    if not os.path.isfile(caminho):
        return None, 'arquivo não existe'
    try:
        import duckdb
    except ImportError:
        return None, 'duckdb não instalado'
    try:
        con = duckdb.connect(caminho, read_only=True)
    except Exception as e:                                          # noqa: BLE001
        return None, '{}: {}'.format(type(e).__name__, str(e)[:60])
    try:
        return con.execute('SELECT COUNT(*) FROM {}'.format(tabela)).fetchone()[0], ''
    except Exception:                                               # noqa: BLE001
        return None, 'tabela não existe'
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true',
                    help='só relata o que seria copiado')
    args = ap.parse_args()

    antigo = Config.DATABASE_PATH
    novo = Config.NOTIFICATIONS_DATABASE_PATH
    print('banco de usuários    : %s' % antigo)
    print('banco de notificações: %s' % novo)
    print('')

    for tabela, _chave in TABELAS:
        a, erro_a = conta(antigo, tabela)
        n, erro_n = conta(novo, tabela)
        print('%-20s antigo: %-8s %-22s destino: %-8s %s' % (
            tabela,
            '—' if a is None else a, '(%s)' % erro_a if erro_a else '',
            '—' if n is None else n, '(%s)' % erro_n if erro_n else ''))

    if args.dry_run:
        print('\n--dry-run: nada foi tocado. A cópia acontece sozinha na próxima')
        print('subida do app; rode sem --dry-run para fazê-la agora.')
        return 0

    # Executar é chamar a MESMA função que a subida chama. Um segundo caminho de
    # cópia aqui divergiria do da aplicação no primeiro ajuste que um dos dois
    # recebesse — e a divergência apareceria como dado faltando no sino.
    from apps.pages import routes as R                              # noqa: E402
    R._notif_db_done = False
    R._ensure_notif_db()

    print('')
    for tabela, _chave in TABELAS:
        n, erro = conta(novo, tabela)
        print('%-20s destino agora: %-8s %s' % (tabela, '—' if n is None else n,
                                                '(%s)' % erro if erro else ''))
    print('\nPronto. O banco antigo continua com as linhas, como backup.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
