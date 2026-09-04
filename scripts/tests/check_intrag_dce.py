# -*- coding: utf-8 -*-
"""Regressão da página Intrag › DCE › Option.

O que este script prende:

1. o PARSER do extrato casa coluna por NOME normalizado, nunca por posição —
   coluna embaralhada não desloca nada, coluna desconhecida sai em `unknown`;
2. o IMPORT materializa o extrato nos arquivos-dia do PRÓPRIO Trade Date e o
   RE-IMPORT preserva a esteira (status/maker/checker/intrag_id) — importar de
   novo não desfaz validação nem mapeamento;
3. a URL do dia sai do cadastro `api-links` (uso `Intrag DCE`) com a data no
   CAMINHO, e sem cadastro cai no fallback — nunca em erro;
4. a lista de campos tem 28 entradas, o contrato com o template da página.

Roda em tmp: o cache da página é apontado para um diretório temporário e o
download é stubado — nada de rede, nada de dado real.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
os.environ.setdefault('OTC_DISABLE_DUCK_MIRROR', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, cond):
    print(('  ok  ' if cond else '  FAIL ') + nome)
    if not cond:
        FALHAS.append(nome)


HEADER = ('OPTION TYPE;TRADE ID;PORTFOLIO CODE;TRADE DATE;OPERATION TYPE;'
          'HOLDER OR WRITER PARTY;HOLDER OR WRITER COUNTERPARTY;COUNTERPARTY;'
          'BASE CURRENCY - STOCKS/INDEX;COMMODITY;QUOTED CURRENCY;MATURITY DATE;'
          'STRIKE PRICE;STRIKE PRICE IN BRL;UNIT PRICE;PREMIUM;'
          'PREMIUM SETTLEMENT DATE;BASE VALUE/QUANTITY;EXERCISE TYPE;'
          'ASIAN OPTION AVERAGE;INITIAL VERIFICATION DATE;FINAL VERIFICATION DATE;'
          'INFORMATION SOURCE;QUOTE FOR MATURITY;QUOTE FOR CURRENCY;FIXING DATE;'
          'BONUS;PREMIUM HOLDER')
LINHA = ('PARIDADE;CETIP_SDP-Y63Y1;GCCN;2026-08-03;CALL;TITULAR;LANCADOR;JPM;'
         'USD;NÃO SE APLICA;BRL;2026-08-11;5.5;0;0.5;0;2026-08-11;1000000;'
         'EUROPEIA;NÃO SE APLICA;2026-08-05;2026-08-10;PTAX;5-2;2;2026-08-10;;PARTE')


def main():
    from run import app  # noqa: F401 — sobe o registro (blueprint, config)
    from apps.pages.features.intrag import commands, domain, queries
    from apps.pages.features.intrag.infra import persistence

    print('== 1. parser: por nome, nunca por posição ==')
    rows, unknown = domain._dce_parse_report(HEADER + '\n' + LINHA)
    check('uma linha, nenhum cabeçalho desconhecido', len(rows) == 1 and not unknown)
    r = rows[0]
    check('trade_id certo', r['trade_id'] == 'CETIP_SDP-Y63Y1')
    check('premium_holder na última coluna', r['premium_holder'] == 'PARTE')
    check('28 campos no contrato', len(domain._DCE_OPT_FIELDS) == 28)
    check('toda chave do parse é do contrato',
          set(r) == set(domain._DCE_OPT_FIELDS))

    # Colunas EMBARALHADAS + uma desconhecida: nada desloca, a estranha avisa.
    emb = ('TRADE ID;COLUNA NOVA;TRADE DATE;COUNTERPARTY\n'
           'CETIP_SDP-Y63Y1;X;2026-08-03;JPM')
    rows2, unknown2 = domain._dce_parse_report(emb)
    check('embaralhado casa pelo nome',
          rows2 and rows2[0]['trade_id'] == 'CETIP_SDP-Y63Y1'
          and rows2[0]['counterparty'] == 'JPM')
    check('coluna desconhecida sai em unknown', unknown2 == ['COLUNA NOVA'])
    check('campo sem coluna fica vazio', rows2[0]['premium'] == '')

    print('== 2. import: arquivo-dia do Trade Date, re-import preserva a esteira ==')
    tmp = tempfile.mkdtemp(prefix='otc-dce-')
    persistence.INTRAG_DCE_OPT_CACHE_DIR = tmp

    class _Resp:
        status_code = 200
        content = (HEADER + '\n' + LINHA).encode('utf-8')
        def raise_for_status(self):
            return None

    class _Sess:
        trust_env = False
        def get(self, url, timeout=None):
            return _Resp()

    from apps.pages import athena_api
    _orig = athena_api.build_session
    athena_api.build_session = lambda: _Sess()
    try:
        res = commands._dce_opt_import(ref_date='2026-09-02')
        check('import devolve sucesso', res.get('success') is True)
        check('uma linha importada', res.get('imported') == 1)
        fp = os.path.join(tmp, '2026', '08', '20260803_intrag_dce_opt.json')
        check('arquivo-dia do TRADE DATE (não do ref date)', os.path.isfile(fp))

        fp2, entries, idx = queries._find_intrag_dce_opt_entry('CETIP_SDP-Y63Y1', '2026-08-03')
        check('finder acha a linha', idx is not None and fp2 == fp)
        check('linha nasce New sem maker', entries[idx]['status'] == 'New'
              and entries[idx]['maker'] == '')

        # Simula a esteira andando e re-importa: nada volta atrás.
        entries[idx]['status'] = 'Approved'
        entries[idx]['maker'] = 'A111111'
        entries[idx]['checker'] = 'B222222'
        entries[idx]['intrag_id'] = 'INT-42'
        import json as _json
        with open(fp, 'w', encoding='utf-8') as fh:
            _json.dump(entries, fh)
        res2 = commands._dce_opt_import(ref_date='2026-09-03')
        check('re-import devolve sucesso', res2.get('success') is True)
        _fp3, entries3, idx3 = queries._find_intrag_dce_opt_entry('CETIP_SDP-Y63Y1', '2026-08-03')
        check('status preservado', entries3[idx3]['status'] == 'Approved')
        check('maker/checker preservados', entries3[idx3]['maker'] == 'A111111'
              and entries3[idx3]['checker'] == 'B222222')
        check('intrag_id preservado', entries3[idx3]['intrag_id'] == 'INT-42')
        check('sem linha duplicada', sum(1 for e in entries3
                                         if e.get('_deal') == 'CETIP_SDP-Y63Y1') == 1)
    finally:
        athena_api.build_session = _orig

    print('== 3. a URL do dia: cadastro com a data no caminho, fallback sem erro ==')
    from datetime import datetime
    url = commands._dce_opt_url(datetime(2026, 9, 2))
    check('data no caminho (AAAA-MM-DD)', '/2026-09-02/' in url)
    check('endereço do extrato de FX Option', 'ITAUDataExtract' in url)

    print()
    if FALHAS:
        print('FALHOU: ' + '; '.join(FALHAS))
        return 1
    print('TUDO OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
