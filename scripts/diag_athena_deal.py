# -*- coding: utf-8 -*-
"""Diagnóstico de UMA operação no pull da Athena: o que a API devolve e o que o
app faz com isso.

    python scripts/diag_athena_deal.py FXO 2026-10-27 D5WM-PLNXR [--json saida.json]
    python scripts/diag_athena_deal.py NDF 20261027 <DEAL>

Busca na Athena EXATAMENTE o que o pull do New Deals busca (o endereço do
cadastro /mapping › API Links, a mesma sessão Kerberos) e imprime:

  1. o endereço chamado e quantos registros vieram;
  2. CADA registro com esse DEAL NAME (a operação pode vir mais de uma vez:
     versões, pernas) — End Counterparty, SPN, descrição, Entry Time,
     isDead/isCancelled e os books;
  3. o que sobra depois do filtro de versões (`_api_live_records`);
  4. só no FXO: como cada registro é resolvido no Reference Data (o acronym, o
     SPN, o cliente e o Tax ID que iriam para a tela, e por qual caminho);
  5. as linhas que o arquivo-dia já tem para esse Deal.

`--json` grava os registros crus da operação num arquivo, para mandar adiante.

Roda na instância (máquina da rede do JPM), no Python do app, com o app de pé
ou parado: só LÊ — não grava nada na tela nem no banco.
"""
import json
import os
import re
import sys
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps import create_app                                # noqa: E402
from apps.config import DebugConfig                        # noqa: E402

CAMPOS = ('Deal Name', 'End Counterparty', 'End Counterparty SPN', 'SPN',
          'End Counterparty Description', 'Orig Entry Time', 'Entry Time', 'Trade Date',
          'isDead', 'isCancelled', 'Trading Book', 'Other Book', 'Counterparty Type')


def _norm(rec):
    return {re.sub(r'[\s_]+', ' ', str(k or '').strip().upper()): v for k, v in rec.items()}


def _nome(rec):
    return str(_norm(rec).get('DEAL NAME') or '').strip().replace('_', '-').upper()


def _data(txt):
    txt = txt.strip()
    for fmt in ('%Y-%m-%d', '%Y%m%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(txt, fmt)
        except ValueError:
            pass
    raise SystemExit('data inválida: %r (use AAAA-MM-DD)' % txt)


def _mostra(rec):
    n = _norm(rec)
    for c in CAMPOS:
        k = re.sub(r'[\s_]+', ' ', c.upper())
        print('      %-30s %r' % (c, n.get(k)))


def main():
    args = [a for a in sys.argv[1:]]
    saida = None
    if '--json' in args:
        i = args.index('--json')
        saida = args[i + 1] if i + 1 < len(args) else 'diag_athena_deal.json'
        del args[i:i + 2]
    if len(args) != 3:
        raise SystemExit(__doc__)
    produto, data, deal = args[0].upper(), _data(args[1]), args[2].strip().replace('_', '-').upper()
    if produto not in ('FXO', 'NDF'):
        raise SystemExit('produto: FXO ou NDF')
    ymd = data.strftime('%Y%m%d')

    app = create_app(DebugConfig)
    with app.test_request_context('/'):
        from apps.pages import athena_api as A
        from apps.pages import routes as R
        from apps.pages import data_store as S
        from apps.pages.platform import new_deals as ND

        print('== 1. a chamada ==')
        url = A.registered_url(A.USE_NEW_DEALS, product=produto, date=ymd)
        print('  endereço do cadastro: %s' % (url or '(sem cadastro: o endereço histórico)'))
        payload = A.fetch_product_trades(produto, ymd)
        registros = A.extract_records(payload)
        print('  registros devolvidos: %d' % len(registros))

        print('\n== 2. os registros de %s ==' % deal)
        meus = [r for r in registros if isinstance(r, dict) and _nome(r) == deal]
        if not meus:
            print('  NENHUM registro com esse DEAL NAME nesta data. Parecidos:')
            for r in registros:
                if isinstance(r, dict) and deal[:4] in _nome(r):
                    print('    %s' % _nome(r))
        for i, r in enumerate(meus, 1):
            print('  [%d de %d]' % (i, len(meus)))
            _mostra(r)
        if saida:
            with open(saida, 'w', encoding='utf-8') as fh:
                json.dump(meus, fh, ensure_ascii=False, indent=2, default=str)
            print('  registros crus gravados em %s' % os.path.abspath(saida))

        print('\n== 3. depois do filtro de versões (_api_live_records) ==')
        vivos = ND._api_live_records(meus)
        print('  ficam %d de %d' % (len(vivos), len(meus)))
        if len(vivos) > 1:
            print('  ATENÇÃO: mais de um registro VIVO com o mesmo Deal — o último da lista')
            print('  é o que fica gravado na tela a cada pull.')

        if produto == 'FXO':
            print('\n== 4. como o app resolve cada registro (Reference Data) ==')
            refmap = R._fxo_refdata_by_spn()
            acr = ND._fxo_refdata_by_accronym(refmap)
            for i, r in enumerate(vivos, 1):
                n = _norm(r)
                end_cp = str(n.get('END COUNTERPARTY') or '').strip()
                print('  [%d] End Counterparty %r' % (i, end_cp))
                for v in ND._ndf_accronym_variants(end_cp):
                    rec = acr.get(v)
                    print('      acronym %-20r → %s' % (v, ('%s / SPN %s' % (rec.get('COUNTERPARTY'), rec.get('SPN')))
                                                      if rec else 'não está no Reference Data'))
                print('      LE pelo le-accronym: %r' % ND._ndf_le_from_accronym(end_cp))
                spn = R._norm_spn(n.get('SPN'))
                rec = refmap.get(spn)
                print('      SPN da API %r → %s' % (n.get('SPN'), ('%s / acronym %s' % (
                    rec.get('COUNTERPARTY'), rec.get('FX CASH ACCRONYM'))) if rec else 'não está no Reference Data'))
                deals, _c = ND._fxo_deals_from_api_records([r], 'DIAG')
                for d in deals:
                    print('      → a tela recebe: Acronym %r · SPN %r · Client %r · Tax ID %r'
                          % (d.get('Acronym'), d.get('SPN'), d.get('Client'), d.get('TaxID')))
                if not deals:
                    print('      → descartado na leitura (End Counterparty, descrição ou SPN vazio)')

            print('\n== 5. o que o arquivo-dia tem ==')
            for r in meus or [{}]:
                td = str(_norm(r).get('TRADE DATE') or data.strftime('%Y-%m-%d'))[:10]
                try:
                    dia = datetime.strptime(td, '%Y-%m-%d')
                except ValueError:
                    dia = data
                fpath = os.path.join(R.OPT_FXO_CACHE_DIR, dia.strftime('%Y'), dia.strftime('%m'),
                                     dia.strftime('%Y%m%d') + '_optfxo.json')
                try:
                    linhas = S.read(fpath)
                except FileNotFoundError:
                    linhas = []
                for l in linhas if isinstance(linhas, list) else [linhas]:
                    if str(l.get('Deal') or '').strip().upper() == deal:
                        print('  %s: Status %r · Acronym %r · SPN %r · Client %r · AmendChanged %r'
                              % (os.path.basename(fpath), l.get('Status'), l.get('Acronym'), l.get('SPN'),
                                 l.get('Client'), l.get('AmendChanged')))
                break


if __name__ == '__main__':
    main()
