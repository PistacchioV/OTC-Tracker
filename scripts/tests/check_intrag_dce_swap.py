# -*- coding: utf-8 -*-
"""Regressão da página Intrag › DCE › Swap.

O que este script prende:

1. o PARSER da planilha acha as DUAS tabelas pelo cabeçalho (características
   por perna e fluxos por cupom), na mesma aba ou em abas distintas, casa
   coluna por NOME normalizado (embaralhar não desloca; desconhecida sai em
   `unknown`) e agrupa por Deal Name;
2. a LINHA da Intrag é byte a byte a do script da mesa
   (`translate_athena_intrag_swap.py`): a saída esperada abaixo foi gerada
   rodando `montar_operacao` daquele script sobre o mesmo par Pay + Rec;
   deal sem uma das pernas levanta dizendo qual;
3. os literais `Fixed` do template do File Interpreter vencem o gerador;
4. o IMPORT materializa os deals no arquivo-dia da Trade Date escolhida e o
   RE-IMPORT preserva a esteira (status/maker/checker/intrag_id);
5. o leitor de upload: .xlsx (openpyxl) e texto `;` viram a mesma grade —
   data como ISO, inteiro sem `.0`, booleano TRUE/FALSE;
6. o template `intrag-dce-swap` está na biblioteca com 48 campos ligados à
   página, e a família `dce-swap` existe no Delete.

Roda em tmp: o cache da página aponta para um diretório temporário — nada de
rede, nada de dado real.
"""
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, cond):
    print(('  ok  ' if cond else '  FAIL ') + nome)
    if not cond:
        FALHAS.append(nome)


LEG_HDR = ('Deal Name;Leg Name;Counterparty;SPN;Trading Entity;Inst Leg Name;Direction;Quantity;'
           'Rates/Spread;Currency;Start Date;End Date;Pay Freq;Initial Exchange;Final Exchange;DCC;'
           'Acc Adj;Pay Adj;Pay Rel To;Notional Exch Date Adj;Comp Freq;Comp Meth;Compounding Formula;'
           'Index Name;Index Tenor;Reset Adj;Leverage;Index Start Value;Index Start Date;Index End Date;'
           'Notional Pay Date;Roll Convention;Roll Day;Initial Stub Method;Initial Interp Tenor;'
           'Final Stub Method;Final Interp Tenor;Custom Rt(%);Settlement Ccy;FX Reset Anchor;'
           'FX Fix Date Adj;FX Fix Pub')
PAY = ('D8DV-2CEZBY;leg0;XXX XTRUCTURED BRAZIL;7512716;LAWTON;StdFixedXccyLegND;Pay;-25000000;0.0;BRL;'
       '2026-09-02;2026-10-02;Zero;FALSE;TRUE;30/360;ModifiedFollowing(GBLO,USNY);'
       'ModifiedFollowing(GBLO,USNY);PeriodEnd;ModifiedFollowing(GBLO,USNY);;StdFixedXccyLegND;;;;N/A;'
       ';;;;;Calendar;;DefaultRate;;DefaultRate;;;USD;PaymentDate;-2D(BRSP,USNY);PTAX')
REC = ('D8DV-2CEZBY;leg1;XXX XTRUCTURED BRAZIL;7512716;LAWTON;StdFloatXccyLegND;Rec;4500000;1.25;USD;'
       '2026-09-02;2026-10-02;Zero;FALSE;TRUE;act/360;ModifiedFollowing(GBLO,USNY);'
       'ModifiedFollowing(GBLO,USNY);PeriodEnd;ModifiedFollowing(GBLO,USNY);;StdFloatXccyLegND;;USD SOFR;'
       '1D;N/A;;;;;;Calendar;;DefaultRate;;ShortFront;3M;2.5;USD;PaymentDate;-2D(BRSP,USNY);PTAX')
FLOW_HDR = ('Deal Name;Leg Name;Inst Leg Name;Coupon;Settlement Date;Accrual Start Date;'
            'Accrual End Date;(Adj)RateValue(%);Spread(%);DCF Fraction;Adj Start;Adj End;'
            'Notional(Absolute);Notional(%)')
FLOW = 'D8DV-2CEZBY;leg0;StdFixedXccyLegND;Coupon 1;2026-10-02;2026-09-02;2026-10-02;0;;30/360;46267;46297;25000000;100'

# A saída do `montar_operacao` do script da mesa para PAY + REC acima com
# TRADE_DATE = 20260911 (gerada em 11/09/2026 — é o oráculo deste teste).
ESPERADO = ('13;0;GCCN;JPM;D8DV-2CEZBY;20260911;20260902;20261002;-25000000,00;USD SOFR;100;'
            '-0,180000;1.25;360;E;E;C;Zero;ModifiedFollowing(GBLO,USNY);ModifiedFollowing(GBLO,USNY);'
            '2.5;;;ShortFront;3M;;BRL FIXED;100;;0.0;360;E;E;C;Zero;ModifiedFollowing(GBLO,USNY);'
            'ModifiedFollowing(GBLO,USNY);0;;;;;;20261002;USD;PaymentDate;-2D(BRSP,USNY);PTAX')


def _grid(*blocos):
    """Blocos de texto `;` → grade (linha em branco entre blocos)."""
    out = []
    for b in blocos:
        for ln in b.splitlines():
            out.append(ln.split(';'))
        out.append([])
    return out


def main():
    from run import app  # noqa: F401 — sobe o registro (blueprint, config)
    from apps.pages import routes as R
    from apps.pages.features.intrag import commands, domain, queries
    from apps.pages.features.intrag.infra import persistence, xlsx_grid
    from datetime import datetime

    print('== 1. parser: duas tabelas pelo cabeçalho, por nome ==')
    deals, unknown = domain._dce_swap_parse_grid(_grid(LEG_HDR + '\n' + PAY + '\n' + REC,
                                                       FLOW_HDR + '\n' + FLOW))
    check('um deal, nenhum cabeçalho desconhecido', list(deals) == ['D8DV-2CEZBY'] and not unknown)
    d = deals['D8DV-2CEZBY']
    check('duas pernas e um fluxo', len(d['legs']) == 2 and len(d['flows']) == 1)
    check('42 campos por perna, 14 por fluxo',
          len(domain._DCE_SWAP_LEG_FIELDS) == 42 and len(domain._DCE_SWAP_FLOW_FIELDS) == 14
          and set(d['legs'][0]) == set(domain._DCE_SWAP_LEG_FIELDS)
          and set(d['flows'][0]) == set(domain._DCE_SWAP_FLOW_FIELDS))
    check('Custom Rt(%) casa pelo nome normalizado', d['legs'][1]['custom_rt'] == '2.5')
    check('(Adj)RateValue(%) e Notional(%) casam', d['flows'][0]['adj_rate_value'] == '0'
          and d['flows'][0]['notional_pct'] == '100')
    # Tabelas COLADAS (sem linha em branco) e embaralhadas + coluna estranha.
    emb = _grid('Direction;COLUNA NOVA;Deal Name;Quantity\nPay;x;ABC;10\nRec;y;ABC;20\n'
                'Coupon;Deal Name;Notional(Absolute)\nCoupon 1;ABC;10')
    deals2, unknown2 = domain._dce_swap_parse_grid(emb)
    check('coladas e embaralhadas: 2 pernas + 1 fluxo do ABC',
          len(deals2.get('ABC', {}).get('legs', [])) == 2
          and len(deals2['ABC']['flows']) == 1 and deals2['ABC']['flows'][0]['notional_absolute'] == '10')
    check('coluna desconhecida sai em unknown', unknown2 == ['COLUNA NOVA'])
    check('linha sem Deal Name é ignorada',
          not domain._dce_swap_parse_grid(_grid(LEG_HDR + '\n;leg0;X'))[0])

    print('== 2. a linha da Intrag: byte a byte com o script da mesa ==')
    entry = {'_deal': 'D8DV-2CEZBY', 'trade_date': '2026-09-11', 'legs': d['legs'], 'flows': d['flows']}
    campos = domain._dce_swap_intrag_fields(entry)
    check('48 campos', len(campos) == 48 and len(domain._DCE_SWAP_FILE_FIELDS) == 48)
    linha = ';'.join(campos)
    check('linha igual à do script', linha == ESPERADO)
    if linha != ESPERADO:
        for i, (a, b) in enumerate(zip(campos, ESPERADO.split(';')), 1):
            if a != b:
                print('      campo %d: %r != %r' % (i, a, b))
    # Ordem invertida das pernas na planilha não muda nada; Rec chamado 'Receive' vale.
    inv = dict(entry, legs=[dict(d['legs'][1], direction='Receive'), d['legs'][0]])
    check('pernas em qualquer ordem, Rec = Receive', ';'.join(domain._dce_swap_intrag_fields(inv)) == ESPERADO)
    try:
        domain._dce_swap_intrag_fields(dict(entry, legs=[d['legs'][0]]))
        check('sem Rec levanta', False)
    except ValueError as exc:
        check('sem Rec levanta dizendo qual', 'Rec' in str(exc))
    check('FX rate vazio com Pay zero',
          domain._dce_swap_intrag_fields(dict(entry, legs=[dict(d['legs'][0], quantity='0'), d['legs'][1]]))[11] == '')
    check('data dd/mm/aaaa vira AAAAMMDD', domain._dces_fmt_data('02/09/2026') == '20260902')

    print('== 3. os Fixed do template vencem o gerador ==')
    sub = domain._dce_swap_apply_fixed(campos, [{'seq': '3', 'source': 'Fixed', 'source_detail': 'XPTO'},
                                                {'seq': '5', 'source': 'Page', 'source_detail': 'Deal Name'},
                                                {'seq': '99', 'source': 'Fixed', 'source_detail': 'x'}])
    check('Fixed troca o campo 3; Page não toca; seq fora ignora',
          sub[2] == 'XPTO' and sub[4] == 'D8DV-2CEZBY' and len(sub) == 48)
    tpl = R._fi_tpl_cached('intrag-dce-swap')
    check('template na biblioteca, 48 campos, ligado à página',
          bool(tpl) and tpl.get('status') == 'library'
          and len(tpl['blocks'][0]['fields']) == 48
          and any(p.get('url') == '/intrag-dce-swap' for p in tpl.get('linked_pages', [])))
    check('os Fixed do template gravado reproduzem o script',
          ';'.join(commands._dce_swap_line_fields(entry)) == ESPERADO)
    check('nome do arquivo segue as irmãs da Intrag', commands._dce_swap_file_name(datetime(2026, 9, 11)) == 'Intrag-DCE-Swap-20260911.txt')

    print('== 4. import no arquivo-dia da Trade Date; re-import preserva a esteira ==')
    tmp = tempfile.mkdtemp(prefix='otc-dces-')
    persistence.INTRAG_DCE_SWAP_CACHE_DIR = tmp
    grid = _grid(LEG_HDR + '\n' + PAY + '\n' + REC + '\nOUTRO;leg0;C;1;LAWTON;X;Pay;1;;BRL;2026-09-02;2026-10-02',
                 FLOW_HDR + '\n' + FLOW)
    res = commands._dce_swap_import_grid(grid, datetime(2026, 9, 11))
    check('dois deals importados', res.get('imported') == 2 and res.get('legs') == 3 and res.get('flows') == 1)
    check('o deal sem Rec é avisado, não descartado',
          res.get('missing_leg') and res['missing_leg'][0].startswith('OUTRO'))
    fp = os.path.join(tmp, '2026', '09', '20260911_intrag_dce_swap.json')
    check('arquivo-dia da TRADE DATE', os.path.isfile(fp) or persistence._store.isfile(fp))
    fp2, entries, idx = queries._find_intrag_dce_swap_entry('D8DV-2CEZBY', '2026-09-11')
    check('finder acha o deal', idx is not None and os.path.normpath(fp2) == os.path.normpath(fp))
    check('nasce New, com pernas e fluxos', entries[idx]['status'] == 'New' and entries[idx]['maker'] == ''
          and len(entries[idx]['legs']) == 2 and len(entries[idx]['flows']) == 1
          and entries[idx]['_client'] == 'XXX XTRUCTURED BRAZIL')
    entries[idx].update(status='Approved', maker='A111111', checker='B222222', intrag_id='INT-7')
    R._atomic_write_json(fp2, entries)
    commands._dce_swap_import_grid(grid, datetime(2026, 9, 11))
    _fp3, e3, i3 = queries._find_intrag_dce_swap_entry('D8DV-2CEZBY', '2026-09-11')
    check('re-import preserva status/maker/checker/intrag_id',
          e3[i3]['status'] == 'Approved' and e3[i3]['maker'] == 'A111111'
          and e3[i3]['checker'] == 'B222222' and e3[i3]['intrag_id'] == 'INT-7')
    check('sem deal duplicado', sum(1 for e in e3 if e.get('_deal') == 'D8DV-2CEZBY') == 1)
    apagadas, nao = commands._intrag_delete_entries('dce-swap', [{'deal_id': 'OUTRO', 'trade_date': '2026-09-11'}])
    check('família dce-swap apaga do arquivo', apagadas == 1 and not nao
          and queries._find_intrag_dce_swap_entry('OUTRO', '2026-09-11')[2] is None)

    print('== 5. o leitor de upload: xlsx e texto viram a mesma grade ==')
    from openpyxl import Workbook
    import datetime as _dt
    wb = Workbook()
    ws = wb.active; ws.title = 'Deals'
    ws.append(['Deal Name', 'Direction', 'Quantity', 'Start Date', 'Initial Exchange', 'Rates/Spread'])
    ws.append(['ABC', 'Pay', -25000000, _dt.datetime(2026, 9, 2), False, 1.25])
    ws2 = wb.create_sheet('Cashflows')
    ws2.append(['Deal Name', 'Coupon', 'Notional(%)'])
    ws2.append(['ABC', 'Coupon 1', 100.0])
    buf = io.BytesIO(); wb.save(buf)
    g, sheets = xlsx_grid.grid_from_upload('x.xlsx', buf.getvalue())
    check('duas abas lidas', sheets == ['Deals', 'Cashflows'])
    dx, _ = domain._dce_swap_parse_grid(g)
    leg = dx['ABC']['legs'][0]
    check('inteiro sem .0, data ISO, booleano FALSE, float como veio',
          leg['quantity'] == '-25000000' and leg['start_date'] == '2026-09-02'
          and leg['initial_exchange'] == 'FALSE' and leg['rates_spread'] == '1.25')
    check('100.0 vira 100', dx['ABC']['flows'][0]['notional_pct'] == '100')
    gt, _ = xlsx_grid.grid_from_upload('x.txt', (LEG_HDR + '\n' + PAY).encode('utf-8'))
    check('texto `;` vira grade', gt[0][0] == 'Deal Name' and gt[1][6] == 'Pay')
    try:
        xlsx_grid.grid_from_upload('x.txt', b'so uma palavra')
        check('texto sem delimitador levanta', False)
    except ValueError:
        check('texto sem delimitador levanta', True)

    print()
    if FALHAS:
        print('FALHOU: ' + '; '.join(FALHAS))
        return 1
    print('TUDO OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
