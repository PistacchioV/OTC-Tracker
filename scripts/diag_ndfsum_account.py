# -*- coding: utf-8 -*-
"""Diagnóstico da coluna Account do Settlement Summary (NDF Summary).

    python scripts/diag_ndfsum_account.py [AAAA-MM-DD]

Para cada contraparte do arquivo-dia do Cockpit imprime cada elo da cadeia
que enche a coluna: o NOME da linha → o SPN que esse nome resolve no
Reference Data → o registro do Counterparty Details → as contas e os
defaults (current = aprovado, pending = à espera do checker) → o texto
que a tela mostraria nas duas direções. Onde a cadeia quebra, diz por quê,
e no nome sem cadastro lista os nomes mais parecidos do Reference Data.

Roda na instância, no venv do app, com o app de pé ou parado (só lê). Não
grava nada. Sem argumento usa hoje.
"""
import difflib
import os
import sys
import traceback
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps import create_app                                # noqa: E402
from apps.config import DebugConfig                        # noqa: E402


def _slot(s):
    s = s or {}
    return 'current=%s pending=%s' % (s.get('current') or '-', s.get('pending') or '-')


def main():
    ref = datetime.strptime(sys.argv[1], '%Y-%m-%d') if len(sys.argv) > 1 else datetime.now()
    app = create_app(DebugConfig)
    with app.test_request_context('/'):
        from apps.pages import routes as R
        from apps.pages import data_store as S

        print('== Counterparty Details ==')
        try:
            cpd = R._cpd_load()
            print('  registros: %d (%s)' % (len(cpd), R._cpd_path()))
            com_def = [r for r in cpd if any(
                ((R._bank_norm(r.get('BANKING')) or {}).get(k) or {}).get('current')
                for k in ('DEFAULT_PAY', 'DEFAULT_RECEIVE'))]
            print('  com default aprovado: %d' % len(com_def))
            for r in com_def[:10]:
                b = R._bank_norm(r.get('BANKING'))
                print('    SPN %-10s %-40s PAY[%s] RECEIVE[%s]' % (
                    r.get('SPN'), str(r.get('COUNTERPARTY') or '')[:40],
                    _slot(b['DEFAULT_PAY']), _slot(b['DEFAULT_RECEIVE'])))
        except Exception:
            print('  FALHOU a leitura do cadastro — é isto que deixa a coluna vazia:')
            print(traceback.format_exc())
            cpd = []

        print('\n== Reference Data ==')
        spn_by_name = R._ndfsum_refdata_spn()
        print('  nomes com SPN: %d' % len(spn_by_name))

        print('\n== Cockpit %s ==' % ref.strftime('%Y-%m-%d'))
        jp = R._ndfc_json_path(ref)
        print('  arquivo-dia: %s' % jp)
        try:
            existe = S.isfile(jp)
        except Exception as exc:                            # noqa: BLE001
            print('  isfile FALHOU: %r' % exc)
            return 1
        if not existe:
            print('  não há arquivo-dia para esta data (o banco não o tem). Nada a diagnosticar.')
            return 1
        data = R._db_day_records(jp) or []
        print('  linhas: %d' % len(data))
        nomes = {}
        for rec in data:
            nm = str(rec.get('NM_COUNTERPARTY', '') or '').strip()
            if nm:
                nomes.setdefault(nm, []).append(str(rec.get('LEGAL', '') or '').strip())

        print('\n== A cadeia, contraparte a contraparte ==')
        candidatos = list(spn_by_name)
        for nm in sorted(nomes, key=R._fcst_norm):
            key = R._fcst_norm(nm)
            ref_rec = spn_by_name.get(key)
            print('\n- %s  (LEGAL: %s)' % (nm, ', '.join(sorted(set(nomes[nm])))))
            if not ref_rec:
                print('    QUEBRA no Reference Data: nenhum cadastro com este NOME (a busca é pelo nome, normalizado).')
                for alt in difflib.get_close_matches(key, candidatos, n=3, cutoff=0.6):
                    print('      parecido: %s (SPN %s)' % (alt, spn_by_name[alt]['spn']))
                continue
            spn = ref_rec['spn']
            print('    Reference Data: SPN %s' % spn)
            rec_cpd = R._cpd_find(cpd, spn) if spn else None
            if rec_cpd is None:
                print('    QUEBRA no Counterparty Details: nenhum registro com o SPN %s.' % spn)
                continue
            b = R._bank_norm(rec_cpd.get('BANKING'))
            print('    Counterparty Details: %d conta(s); DEFAULT_PAY %s; DEFAULT_RECEIVE %s' % (
                len(b['ACCOUNTS']), _slot(b['DEFAULT_PAY']), _slot(b['DEFAULT_RECEIVE'])))
            for a in b['ACCOUNTS']:
                print('      conta id=%s bco=%s ag=%s cc=%s status=%s' % (
                    a.get('id'), a.get('bank'), a.get('agency'), a.get('account'), a.get('status')))
            for d in ('RECEIVE', 'PAY'):
                txt = R._ndfsum_account_fmt(b, d)
                print('    Direction %-7s → Account: %s' % (d, txt or '(vazio: o slot %s não tem default aprovado)'
                                                             % ('DEFAULT_PAY' if d == 'RECEIVE' else 'DEFAULT_RECEIVE')))
        print('\nLegenda: Direction é a visão do BANCO. Banco RECEIVE = cliente paga → usa DEFAULT_PAY do '
              'cliente; banco PAY → DEFAULT_RECEIVE. Só `current` (aprovado pelo checker) enche a coluna.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
