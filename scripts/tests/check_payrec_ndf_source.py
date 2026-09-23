"""Pay/Rec: o lado JPM de NDF vem da API + recompras, não do `settlement.csv`.

Desde 23/09/2026 a liquidação de NDF da recon é a do Cockpit montada na hora
(`routes._ndfc_liquidacao_do_dia`): o `getTradesBySettle` da Athena mais as
recompras de NDF que a API ainda não traz, com o IR calculado. O que se prova:

  1. o registro do Cockpit vira NDF pela MESMA redução do `settlement.csv`
     (SETTLEMENT + TAX, por cliente e LE; LEGAL fora do JPM fica de fora);
  2. um `settlement.csv` esquecido na pasta NÃO entra de novo (dobraria o NDF);
  3. recompra cujo DEAL já veio da API não entra duas vezes — e a que não veio
     entra;
  4. a liquidação do dia junta API + recompras e calcula o IR, SEM gravar o
     dia do Cockpit; API fora do ar LEVANTA com o motivo.

Sem dado real: API, dia do Cockpit e IR são stubs.
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from datetime import date                                        # noqa: E402

from apps.pages import recon_payrec as RP                        # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


BANCO = 'BANCO J.P. MORGAN S.A.'
MGT = 'JPMORGAN CHASE BANK, N.A. - SAO PAULO BRANCH'


def ck(cpty, settle, tax='', legal=BANCO, deal='D1', **kw):
    r = {'LEGAL': legal, 'NM_COUNTERPARTY': cpty, 'ID_SOURCE_DEAL': deal,
         '[PROD] Cockpit.SETTLEMENT': settle, 'VL_TAX_INCOME': tax}
    r.update(kw)
    return r


print('\n== 1. registro do Cockpit -> NDF, a mesma conta do settlement.csv ==')
out = RP._jpm_cockpit([ck('SUZANO SA', '-1000.00', '0.05')], None)
check('SETTLEMENT + TAX (o IR reduz o pagamento)', [round(r['value'], 2) for r in out], [-999.95])
check('produto NDF', out[0]['product'], 'NDF')
check('LE do banco = JPM', out[0]['le'], 'JPM')
out = RP._jpm_cockpit([ck('SUZANO SA', '500.00', legal=MGT)], None)
check('LE da filial = MGT', out[0]['le'], 'MGT')
out = RP._jpm_cockpit([ck('SUZANO SA', '500.00', legal='LAWTON MULTIMERCADO')], None)
check('LEGAL fora do JPM fica de fora (como no Cockpit)', out, [])
out = RP._jpm_cockpit([ck('SUZANO SA', '-300.00', deal='D1'),
                       ck('SUZANO SA', '100.00', deal='UNW1')], None)
check('recompra netada com o termo do cliente (Total Net)',
      [round(r['value'], 2) for r in out], [-200.0])
check('sem linhas, sem NDF', RP._jpm_cockpit(None, None), [])

print('\n== 2. settlement.csv na pasta é ignorado ==')
_g, _net = RP._gather_sources, RP._load_net_type_map
_persist = RP._persist
RP._gather_sources = lambda files, mode: [
    ('settlement', [{'Client': 'SUZANO SA', 'Amount': '-1000', 'Tax Income': '0',
                     'Legal Entity': BANCO}], ['Client', 'Amount', 'Tax Income', 'Legal Entity'])]
RP._load_net_type_map = lambda: {}
RP._persist = lambda d, p: None
try:
    res = RP.run_payrec('2026-09-23', ndf_rows=[ck('SUZANO SA', '-400.00')])
    jpm_vals = sorted(round(float(r['jpm_value']), 2)
                      for r in res['pending_payment'] + res['pending_receivement'] + res['settled']
                      if r.get('jpm_value') not in ('', None))
    check('só o NDF do Cockpit entra (o CSV não dobra)', jpm_vals, [-400.0])
finally:
    RP._gather_sources, RP._load_net_type_map, RP._persist = _g, _net, _persist

print('\n== 3 e 4. routes: recompras fora da API e a liquidação do dia ==')
from apps.pages import routes as R                               # noqa: E402

REF = date(2026, 9, 23)
dia = [ck('SUZANO SA', '-100.00', deal='TERMO-1', _nc_id='x1'),
       ck('SUZANO SA', '250.00', deal='STP-XE-AAA-0-0', _nc_id='UNW-STP-XE-AAA-0-0', _nc_unwind=True),
       ck('VALE SA', '-50.00', deal='STP_XE_BBB_0_0', _nc_id='UNW-STP_XE_BBB_0_0', _nc_unwind=True)]
api_rows = [ck('SUZANO SA', '-100.00', deal='TERMO-1'),
            ck('VALE SA', '-50.00', deal='STP-XE-BBB-0-0')]     # a API já trouxe a BBB

saved = {k: getattr(R, k) for k in ('_ndfc_load', '_ndfc_fetch_api', '_ndfc_apply_ir', '_ndfc_save')}
gravou = []
R._ndfc_load = lambda ref: ('x.json', [dict(r) for r in dia])
R._ndfc_save = lambda jp, data: gravou.append(jp)
try:
    fora = R._ndfc_unwinds_fora_da_api(REF, api_rows)
    check('a recompra que a API não traz entra, a que traz não (deal com _ ou -)',
          [r['ID_SOURCE_DEAL'] for r in fora], ['STP-XE-AAA-0-0'])
    check('linha que não é recompra nunca é reanexada',
          all(r.get('_nc_unwind') for r in fora), True)

    R._ndfc_fetch_api = lambda ref: {'success': True, 'rows': [dict(r) for r in api_rows],
                                     'skipped': {}, 'url': 'u'}

    def _ir(ref, rows):
        for r in rows:
            if float(r['[PROD] Cockpit.SETTLEMENT']) < 0:
                r['VL_TAX_INCOME'] = '0.01'
    R._ndfc_apply_ir = _ir
    rows = R._ndfc_liquidacao_do_dia(REF)
    check('API + recompra fora dela', [r['ID_SOURCE_DEAL'] for r in rows],
          ['TERMO-1', 'STP-XE-BBB-0-0', 'STP-XE-AAA-0-0'])
    check('o IR é calculado sobre o dia montado',
          [r['VL_TAX_INCOME'] for r in rows], ['0.01', '0.01', ''])
    check('e o dia do Cockpit NÃO é regravado', gravou, [])
    check('a lista da API não é alterada por dentro', api_rows[0]['VL_TAX_INCOME'], '')

    R._ndfc_fetch_api = lambda ref: {'success': False, 'error': 'Athena API: 401', 'url': 'u'}
    try:
        R._ndfc_liquidacao_do_dia(REF)
        check('API fora do ar levanta', 'não levantou', 'RuntimeError')
    except RuntimeError as e:
        check('API fora do ar levanta com o motivo', 'Athena API: 401' in str(e), True)
finally:
    for k, v in saved.items():
        setattr(R, k, v)

print('\n== 5. o import do Cockpit usa a mesma regra de recompra ==')
import inspect                                                    # noqa: E402
check('_ndfc_keep_unwinds pergunta ao _ndfc_unwinds_fora_da_api',
      '_ndfc_unwinds_fora_da_api(' in inspect.getsource(R._ndfc_keep_unwinds), True)
check('o commands da recon busca pela liquidação do dia',
      '_ndfc_liquidacao_do_dia(' in open('apps/pages/features/recon_payrec/commands.py',
                                         encoding='utf-8').read(), True)

print('\n%s' % ('FAIL: %d' % len(fails) if fails else 'all ok'))
sys.exit(1 if fails else 0)
