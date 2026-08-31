# -*- coding: utf-8 -*-
"""As regras de separacao das VERTICAIS (`apps/pages/features/`).

O `routes.py` tem 39 mil linhas porque toda funcionalidade nasceu nele. A saida
e levar uma feature de cada vez para `features/<nome>/`, e este script e o que
impede a arvore nova de virar a mesma bola de barro com pastas.

Ele prende as regras da skill `separation-of-concerns` (SoC-002/003/004) mais
uma que e especifica deste repositorio e e a que causa perda SILENCIOSA:

  **Modulo de feature nunca importa NOME do `routes`, so o MODULO.**

  Sessenta e um dos setenta e nove scripts de `scripts/tests/` trocam atributos
  no `routes` para nao encostar em dado real: `R.DB_PATH = tmp`,
  `R._create_notification = espiao`, `R.OTM_JSON_ROOT = tmp`. Um
  `from apps.pages.routes import get_db_connection` no topo de um modulo de
  feature CONGELA o valor no import: o teste troca o atributo, o modulo continua
  com o original, e o teste passa a ler o banco de VERDADE — passando. E a
  producao herda o mesmo problema pelo outro lado, porque o `routes` reatribui
  varias dessas constantes na subida.

  O jeito certo e a busca ATRASADA: `from apps.pages import routes` DENTRO da
  funcao, e `routes.X` no ponto de uso. De quebra isso resolve a circularidade,
  ja que o `routes` importa os entrypoints no fim do proprio arquivo.

E a regra que nao esta na skill mas mata a feature em silencio: **entrypoint que
o `routes.py` nao importa e rota que nao existe.** Em Flask o decorador so roda
quando o modulo e importado; sem o import, a pagina responde 404 e a subida nao
diz nada.
"""
import ast
import io
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
FEAT = os.path.join(ROOT, 'apps', 'pages', 'features')

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def modulos():
    for raiz, dirs, arqs in os.walk(FEAT):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for a in arqs:
            if a.endswith('.py'):
                yield os.path.join(raiz, a)


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, '/')


def camada(p):
    return os.path.splitext(os.path.basename(p))[0]


def feature_de(p):
    r = rel(p).split('/')
    return r[3] if len(r) > 3 else ''


ARQS = sorted(modulos())
check('a pasta das verticais existe e tem modulo', bool(ARQS), True)
if not ARQS:
    sys.exit(1)

arvores = {p: ast.parse(io.open(p, encoding='utf-8').read()) for p in ARQS}


def imports_de(arv):
    """(modulo, [nomes]) de cada import, com o nivel de `from .` resolvido."""
    out = []
    for n in ast.walk(arv):
        if isinstance(n, ast.ImportFrom):
            out.append((n.module or '', [a.name for a in n.names], n))
        elif isinstance(n, ast.Import):
            for a in n.names:
                out.append((a.name, [], n))
    return out


print('\n== 1. modulo de feature nunca importa NOME do routes ==')
maus = []
for p in ARQS:
    for mod, nomes, no in imports_de(arvores[p]):
        if mod == 'apps.pages.routes' and nomes:
            maus.append('%s:%d importa %s' % (rel(p), no.lineno, ', '.join(nomes)))
check('nenhum `from apps.pages.routes import <nome>`', maus, [])

print('\n== 2. e o import do routes e ATRASADO (dentro da funcao) ==')
# No topo do modulo ele fecharia o ciclo: o routes importa os entrypoints no fim
# do proprio arquivo, entao neste ponto ele ainda esta a meio de executar.
topo = []
for p in ARQS:
    for n in arvores[p].body:                       # so o corpo do modulo
        for mod, _nomes, no in imports_de(ast.Module(body=[n], type_ignores=[])):
            if mod in ('apps.pages.routes',) or mod.endswith('.routes'):
                topo.append('%s:%d' % (rel(p), no.lineno))
check('nenhum import de routes no corpo do modulo', topo, [])

print('\n== 3. o dominio nao faz I/O (SoC-004) ==')
# Dominio e regra pura: o que ele precisa saber do mundo chega por parametro.
PROIBIDO_NO_DOMINIO = ('flask', 'duckdb', 'smtplib', 'requests', 'sqlite3',
                       'shutil', 'apps.pages.routes', 'apps.config')
sujos = []
for p in ARQS:
    if camada(p) != 'domain':
        continue
    for mod, _n, no in imports_de(arvores[p]):
        if any(mod == x or mod.startswith(x + '.') for x in PROIBIDO_NO_DOMINIO):
            sujos.append('%s:%d importa %s' % (rel(p), no.lineno, mod))
check('nenhum dominio importa I/O', sujos, [])

print('\n== 4. as dependencias apontam para dentro (SoC-002) ==')
# domain nao conhece quem o usa; queries nao conhecem commands.
PROIBIDO_POR_CAMADA = {
    'domain':  ('entrypoint', 'commands', 'queries', 'infra'),
    'queries': ('entrypoint', 'commands'),
    'commands': ('entrypoint',),
}
invertidas = []
for p in ARQS:
    proib = PROIBIDO_POR_CAMADA.get(camada(p))
    if not proib:
        continue
    for mod, nomes, no in imports_de(arvores[p]):
        alvo = set(mod.split('.')) | set(nomes)
        for x in proib:
            if x in alvo:
                invertidas.append('%s:%d -> %s' % (rel(p), no.lineno, x))
check('nenhuma dependencia para cima', sorted(set(invertidas)), [])

print('\n== 5. features nao se importam entre si (SoC-003) ==')
cruzados = []
for p in ARQS:
    minha = feature_de(p)
    for mod, _n, no in imports_de(arvores[p]):
        if not mod.startswith('apps.pages.features.'):
            continue
        outra = mod.split('.')[3] if len(mod.split('.')) > 3 else ''
        if outra and minha and outra != minha:
            cruzados.append('%s:%d -> %s' % (rel(p), no.lineno, outra))
check('nenhuma feature importa outra', cruzados, [])

print('\n== 6. todo entrypoint e importado pelo routes.py ==')
# Em Flask, rota que ninguem importa e rota que nao existe: o decorador so roda
# no import. Sem esta linha, a pagina responde 404 e a subida nao diz nada.
rotas_py = io.open(os.path.join(ROOT, 'apps', 'pages', 'routes.py'), encoding='utf-8').read()
faltando = []
for p in ARQS:
    if camada(p) != 'entrypoint':
        continue
    mod = rel(p)[:-3].replace('/', '.')             # apps/pages/... -> apps.pages...
    pacote, _sep, _nome = mod.rpartition('.')
    if ('import %s' % mod) not in rotas_py and \
       ('from %s import entrypoint' % pacote) not in rotas_py:
        faltando.append(mod)
check('nenhum entrypoint orfao', faltando, [])

print('\n== 7. as rotas realmente existem no app ==')
# O teste acima le o texto; este SOBE o app e pergunta ao Flask. Um import
# escrito e um import que executou sao coisas diferentes.
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from apps import create_app                                  # noqa: E402
from apps.config import DebugConfig                          # noqa: E402
app = create_app(DebugConfig)
regras = {str(r) for r in app.url_map.iter_rules()}
check('/api/tickets registrada', '/api/tickets' in regras, True)
check('/api/tickets/<ticket_id> registrada',
      '/api/tickets/<ticket_id>' in regras, True)
check('/api/tickets/<ticket_id>/comment registrada',
      '/api/tickets/<ticket_id>/comment' in regras, True)
for r in ('/holidays-calendar', '/api/holidays/calendars', '/api/holidays/save',
          '/api/fx-holiday-schedules',
          '/quotes', '/api/quotes/ptax', '/api/quotes/<kind>',
          '/reconciliation-fxo', '/reconciliation-fxo/data',
          '/reconciliation-fxo/run', '/reconciliation-fxo/comment',
          '/onboarding', '/onboarding/tracking-docs', '/cgd',
          '/api/onboarding/overview', '/api/onboarding/docs',
          '/api/onboarding/docs/save', '/api/onboarding/docs/delete',
          '/api/control-panel/bacc-ea-metrics/recipients',
          '/api/control-panel/bacc-ea-metrics/run',
          '/api/control-panel/mt300/recipients', '/api/control-panel/mt300/run',
          '/api/control-panel/app-version/recipients',
          '/api/control-panel/app-version/run',
          '/api/control-panel/manual-deals-ea/recipients',
          '/api/control-panel/manual-deals-ea/run',
          '/api/control-panel/confirmations-escalation/recipients',
          '/api/control-panel/confirmations-escalation/run',
          '/api/control-panel/daily-metric/recipients', '/api/control-panel/daily-metric/run',
          '/api/control-panel/weekly-escalation/recipients',
          '/api/control-panel/weekly-escalation/run',
          '/reconciliation-comitente', '/reconciliation-comitente/run',
          '/reconciliation-payrec', '/reconciliation-payrec/run',
          '/reconciliation-payrec/justify', '/reconciliation-payrec/end-process',
          '/reconciliation-cgd', '/api/reconciliation-cgd/data',
          '/reconciliation-cgd/run', '/reconciliation-cgd/email',
          '/api/new-deals/box-scan', '/api/new-deals/box-scan/run',
          '/api/new-deals/box-archive',
          '/api/control-panel/signature-collection/preview',
          '/api/control-panel/signature-collection/generate',
          '/api/control-panel/pending-spreadsheet/run',
          '/api/control-panel/pending-spreadsheet/status',
          '/api/control-panel/settlement-forecast/data',
          '/api/control-panel/settlement-forecast/email',
          '/api/new-deals/monitor', '/api/control-panel/deals-monitor/run',
          '/api/control-panel/cetip-settlement',
          '/api/control-panel/cetip-settlement/recipients',
          '/api/intrag/ndf', '/api/intrag/option', '/api/intrag/swap',
          '/api/intrag/ndf/approve', '/api/intrag/swap/approve',
          '/api/counterparty-details/save',
          '/api/counterparty-details/contact/add',
          '/api/counterparty-details/contact/approve',
          '/api/electronic-inventory/clients',
          '/api/electronic-inventory/documents',
          '/api/electronic-inventory/upload',
          '/manual-confirmation/monitor', '/manual-confirmation/track',
          '/api/manual-confirmation/data', '/api/manual-confirmation/validate',
          '/mtm-swap', '/api/mtm-swap/data', '/api/mtm-swap/row/edit',
          '/cognos', '/api/cognos/data', '/api/cognos/row/confirm',
          '/otm-settlements', '/api/otm-settlements/data',
          '/other-products-swap-latamdeskposition',
          '/api/other-products-swap-latamdeskposition/data',
          '/accrual-swap', '/api/accrual-swap/data',
          '/ndf-summary', '/api/ndf-summary/data', '/api/ndf-summary/ted-email',
          '/operations-b3', '/api/operations-b3/data', '/api/operations-b3/mensageria',
          '/other-products-summary', '/api/other-products-summary/data',
          '/other-products-ndf-settlement-advice', '/other-products-swap-vcp',
          '/file-interpreter', '/api/file-interpreter/templates',
          '/confirmation/ndf-comm/validate', '/api/confirmation/opt-fxo/save',
          '/ndf-cockpit', '/api/ndf-cockpit/data',
          '/ndf-other-publisher', '/api/ndf-other-publisher/data',
          '/api/pending-confirmation/derive', '/metrics-pending-confirmation',
          '/live-position-swap-characteristics', '/live-position-ndf',
          '/mapping', '/api/mappings/<key>', '/api/reference-data/counterparties',
          '/api/b3/add', '/api/b3/update', '/api/b3/delete',
          '/api/control-panel/daily-settlement-save', '/new-deals-monitor',
          '/api/parse-msg-html',
          '/api/new-deals/<product>/cache', '/api/new-deals/<product>/cache/search',
          '/api/new-deals/<product>/mapping-b3', '/api/new-deals/<product>/send-conecta'):
    check('%s registrada' % r, r in regras, True)

print('\n== 8. o que saiu do routes.py nao ficou nele ==')
# Codigo duplicado nos dois lugares e a falha classica de uma extracao pela
# metade: os dois divergem, e a que vale e a que o decorador registrou.
for morto in ('_tk_roles_by_sid', '_tk_can_view', '_tk_public',
              '_tk_send_closed_email', 'def api_tickets_list',
              '_cgd_form_ctx', '_cgd_db_ready', 'def api_onboarding_docs',
              'def reconciliation_fxo_run', 'def reconciliation_fxo_comment',
              '_quotes_underlyings', '_QUOTES_KINDS', 'def api_quotes_ptax',
              '_HOLIDAY_CAL_SEED', '_holiday_cal_slug', 'def api_holidays_save',
              '_BACC_COLUMNS', '_bacc_rows', '_bacc_build_xlsx', '_bacc_send_email',
              '_bacc_disparar', 'def api_cp_bacc_run',
              '_MT300_TIME', '_mt300_rows', '_mt300_is_target', '_mt300_send_email',
              '_mt300_disparar', 'def api_cp_mt300_run',
              '_APPVER_LINK_FILE', '_appver_read_link', '_appver_active_users',
              '_appver_run', 'def api_cp_app_version_run',
              '_MDEA_KINDS', '_mdea_rows', '_mdea_rebook_record', '_mdea_send_email',
              '_mdea_disparar', 'def api_cp_mdea_run',
              '_CE_FO_GROUPS', '_ce_snapshot', '_ce_run', '_ce_send_email',
              '_ce_is_routine_day', 'def api_cp_conf_escalation_run',
              '_pc_metrics_pivot', '_build_daily_metric_eml', '_pc_weekly_escalation',
              '_build_weekly_escalation_eml', 'def reconciliation_comitente_run',
              'def reconciliation_payrec_run', 'def api_cgd_recon_run',
              '_cgd_recon_recipients', '_BOX_PRODUCTS', '_box_scan_pull',
              '_box_persist_deals', 'def api_new_deals_box_scan_run',
              '_sigcoll_groups', '_sigcoll_build_drafts', '_pcx_build_xlsx',
              '_pcx_save_spreadsheet', '_send_forecast_email', '_ndm_monitor_snapshot',
              '_send_ndm_pending_email', '_cetip_distribute_emails', '_cetip_bacc_copy',
              'def api_cp_cetip_settlement',
              '_intrag_ndf_persist', '_save_intrag_opt_entry', 'def api_intrag_swap_approve',
              '_cpd_get_record', '_bank_get_record', 'def api_cp_contact_approve',
              'def api_ei_clients', 'def api_ei_upload',
              'def api_mc_validate', 'def manual_confirmation_generate',
              '_mtm_build_from_folder', '_mtm_generate_book', 'def api_mtm_process',
              '_cog_import', '_cog_collect', 'def api_cog_row_confirm',
              'def api_otm_row_confirm', 'def api_latam_row_confirm',
              '_acc_apply_factors', '_acc_write_batch_files', 'def api_accrual_recon',
              'def api_ndf_summary_ted_email', 'def api_opb3_mensageria',
              'def api_ops_data', 'def api_optadv_row_confirm',
              'def api_file_interpreter_template',
              # fase platform/ — o calendário foi para platform/anbima.py; os
              # nomes seguem no routes como ALIAS (`_x = _pf_anbima._x`), e é
              # por isso que a busca aqui é por `def X`: o alias não tem `def`.
              'def _br_now', 'def _load_anbima', 'def _prev_anbima_bizday',
              'def _anbima_bizdays_between', 'def _weekday_bizdays_between',
              'def _last_anbima_bizday_of_month', 'def _pcx_is_bizday',
              'def _anbima_holidays', 'def _anbima_biz_diff',
              'def _anbima_add_biz',
              # ... e as notificacoes para platform/notifications.py.
              'def get_notif_connection', 'def _ensure_notif_db',
              'def _notif_init_schema', 'def _notif_schema_pronto',
              'def _notif_migrar_do_antigo', 'def _notif_maior_id_antigo',
              'def _notif_avanca_sequencia', 'def _notif_roles',
              'def _create_notification', 'def _push_notify',
              'def _notif_page_url', '_NOTIF_PAGE_URL = {',
              # ... o armazém JSON para platform/json_cache.py ...
              'def _claim_daily_slot', 'def _release_daily_slot',
              'def _atomic_write_json', 'def _unique_filepath',
              'def _day_files', 'def _day_json', 'def _daycache_forget',
              'def _daycache_dir_ok', '_cache_lock = threading.RLock',
              '_daycache_memo = {}',
              # ... o e-mail para platform/mail.py ...
              'def _get_logo_path', 'def _get_email_asset',
              'def _attach_email_gradient', 'def _parse_emails',
              'def _email_drafts_response', 'def _otc_app_url',
              # ... as datas para platform/dates.py ...
              'def _parse_date_any', 'def _parse_deal_date',
              # ... o banco de usuários para platform/db.py ...
              'class _DuckDBHandle', 'def get_db_connection',
              # ... e a autorização para platform/authz.py (os dois
              # before_request FICAM no routes: registro em blueprint é casca).
              'def _load_nav_urls', 'def _get_page_access',
              'def _read_page_access', 'def _set_page_access',
              'def _get_user_authz', 'def _read_user_authz',
              'def _get_user_role',
              'def _session_is_master', 'def _session_is_admin',
              'def _safe_landing', 'def _user_can_access_page',
              'def _cp_page_allowed', 'def _cp_card_allowed',
              'def _page_access_forget', '_CONTROL_PANEL_CARDS = [',
              # ... e a familia de liquidacao para platform/settlement.py (§316).
              'def _ops_trade_rows', 'def _ops_swap_trade_rows',
              'def _ops_ndfc_trade_rows', 'def _ops_opt_trade_rows',
              'def _ops_equity_link', 'def _ops_is_internal_cpty',
              'def _opssum_rows', 'def _opssum_set_status',
              'def _ops_recon', 'def _ops_batch_status',
              'def _opsadv_family_drafts', '_OPS_SRC_MAP = {',
              # ... o motor de confirmacoes para platform/confirmations.py ...
              'def _conf_segregate', 'def _conf_esteira_stages',
              'def _conf_stage_counts', 'def _conf_generation_page',
              'def _conf_opt_generation_page', 'def _conf_fxo_generation_page',
              'def _conf_fwdstart_rows', 'def _conf_ndf_xml',
              'def _conf_state_load', 'def _conf_state_save',
              'def _conf_cgd_lookup', '_CONF_STAGE_ORDER = (',
              # ... e o Counterparty Details para platform/counterparty.py.
              'def _cpd_path', 'def _cpd_load', 'def _cpd_find',
              'def _cpd_save_list', 'def _norm_spn', 'def _cc_read_rows',
              'def _contacts_norm', '_CONTACT_RULE_MAP = {',
              # ... §317: o Forecast para platform/forecast.py ...
              'def _forecast_collect', 'def _forecast_payload',
              'def _forecast_spine', 'def _fcst_lob', 'def _fcst_norm',
              '_FORECAST_SOURCES = [',
              # ... o Electronic Inventory para platform/electronic_inventory.py
              # (o ELECTRONIC_INVENTORY_ROOT fica no routes: superficie de patch) ...
              'def _ei_scan_root', 'def _ei_actual_dir_name',
              'def _ei_client_dir_names', 'def _ei_iter_files',
              'def _ei_locate_file', 'def _ei_resolve_client_dir',
              # ... e a cola da esteira para platform/manual_confirmation.py.
              'def _mc_save_from_deal', 'def _mc_legal_entity',
              'def _mc_confirmation_docs', 'def _mc_pc_sync',
              'def _mc_notify_roles', 'def _mc_can_validate',
              'def _mc_generate_url', '_MC_STAGE_NOTIFY_ROLES = {',
              # ... §318: o File Interpreter para platform/file_interpreter.py
              # (o _FILE_INTERPRETER_DIR fica no routes: superficie de patch) ...
              'def _fi_load', 'def _fi_clean_template', 'def _fi_variant_key',
              'def _fi_calc_value', 'def _fi_build_line',
              'def _fi_effective_seq_value', '_FI_CALC_RE = re.compile',
              # ... o Pending Confirmation para platform/pending_confirmation.py
              # (_PC_DB_DIR e _B3_DATA_DIR ficam no routes: superficie de patch) ...
              'def _pc_load_rows', 'def _pc_derive_row',
              'def _pc_signature_pending_status', 'def _pc_import_update',
              'def _pc_is_internal_counterparty', 'def _pc_apply_auto_rules',
              'def _pc_save_from_deal', 'def _pc_run_daily_maintenance',
              'def _pc_snapshot_pending', '_PC_ESTEIRA_STATUSES = {',
              # ... e o Operations B3 para platform/operations_b3.py
              # (o _OPB3_MSG_RECIPIENTS_FILE fica no routes: caminho sobre
              # _DAILY_METRIC_DIR, que os testes patcham).
              'def _opb3_load', 'def _opb3_import', 'def _opb3_event_rules',
              'def _opb3_settle_rows', 'def _opb3_collect',
              'def _opb3_breakdown', 'def _opb3_tipo_maps',
              'def _opb3_msg_load_recipients', 'def _ops_norm_event',
              '_OPB3_COLUMNS = [',
              # ... §319: o motor do New Deals para platform/new_deals.py
              # (os caminhos de cache, o _fxo_refdata_by_spn e o
              # _generic_nd_cfg ficam no routes: superficie de patch e
              # chamada interna).
              'def _find_deal_in_cache', 'def _find_ndf_deal_in_cache',
              'def _find_fxo', 'def _deal_matches', 'def _fxo_deal_from_row',
              'def _ndf_deal_from_api', 'def _nd_api_amend',
              'def _nd_amend_is_economic', 'def _nd_cancel_in_file',
              'def _fxo_api_pull', 'def _ndf_api_pull',
              'def _ndf_ref_by_accronym', 'def _ndf_weak_leg',
              'def _generic_ndf_ter_line', 'def _ndf_comm_ter_lines',
              'def _nd_lawton_mirror', 'def _generic_nd_mapping_candidates',
              '_ND_AMEND_COSMETIC_BY_PRODUCT = {'):
    check('%s saiu do routes.py' % morto, morto in rotas_py, False)

print('\n== 9. nenhum global orfao nos modulos de feature ==')
# As extracoes VERBATIM religam nome a nome; um nome que escapou vira NameError
# so quando aquele caminho roda — este passo desmonta o bytecode de TODAS as
# funcoes das features e cobra que cada LOAD_GLOBAL exista no modulo.
import builtins as _bt
import dis as _dis
import importlib as _il
import inspect as _isp
import types as _tp
_orfaos = []
for p in ARQS:
    mod_nome = rel(p)[:-3].replace('/', '.')
    if mod_nome.endswith('__init__'):
        mod_nome = mod_nome[:-9].rstrip('.')
    try:
        _m = _il.import_module(mod_nome)
    except Exception as e:                                  # noqa: BLE001
        _orfaos.append('%s: import falhou (%s)' % (mod_nome, e))
        continue
    _g = set(vars(_m))
    for _nome, _fn in list(vars(_m).items()):
        if not _isp.isfunction(_fn) or _fn.__module__ != _m.__name__:
            continue
        _cods = [_fn.__code__] + [c2 for c2 in _fn.__code__.co_consts
                                  if isinstance(c2, _tp.CodeType)]
        for _cod in _cods:
            for _ins in _dis.get_instructions(_cod):
                if _ins.opname == 'LOAD_GLOBAL' and _ins.argval not in _g \
                        and _ins.argval not in dir(_bt):
                    _orfaos.append('%s.%s -> %s' % (mod_nome, _nome, _ins.argval))
check('todo LOAD_GLOBAL das features resolve', sorted(set(_orfaos)), [])

print('\n== 10. as HORIZONTAIS (apps/pages/platform/) ==')
# As mesmas regras das features, com os sentidos invertidos: platform nunca
# importa feature (a seta aponta para dentro), nunca importa NOME do routes
# (congela o valor que os testes trocam), e o import do routes que ainda
# restar — andaime declarado, enquanto banco/paths não têm fatia própria —
# e ATRASADO, dentro da funcao.
PLAT = os.path.join(ROOT, 'apps', 'pages', 'platform')
plat_arqs = []
for raiz, dirs, arqs in os.walk(PLAT):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    plat_arqs += [os.path.join(raiz, a) for a in arqs if a.endswith('.py')]
plat_arqs = sorted(plat_arqs)
check('a pasta das horizontais existe e tem modulo', bool(plat_arqs), True)
plat_arvores = {p: ast.parse(io.open(p, encoding='utf-8').read()) for p in plat_arqs}
_p_maus, _p_topo, _p_feat = [], [], []
for p in plat_arqs:
    for mod, nomes, no in imports_de(plat_arvores[p]):
        if mod == 'apps.pages.routes' and nomes:
            _p_maus.append('%s:%d importa %s' % (rel(p), no.lineno, ', '.join(nomes)))
        if mod.startswith('apps.pages.features'):
            _p_feat.append('%s:%d' % (rel(p), no.lineno))
    for n in plat_arvores[p].body:                  # so o corpo do modulo
        for mod, _nomes, no in imports_de(ast.Module(body=[n], type_ignores=[])):
            if mod in ('apps.pages.routes',) or mod.endswith('.routes'):
                _p_topo.append('%s:%d' % (rel(p), no.lineno))
check('platform nunca importa NOME do routes', _p_maus, [])
check('e o import do routes e atrasado (andaime declarado)', _p_topo, [])
check('platform nunca importa feature', _p_feat, [])
_p_orfaos = []
for p in plat_arqs:
    mod_nome = rel(p)[:-3].replace('/', '.')
    if mod_nome.endswith('__init__'):
        mod_nome = mod_nome[:-9].rstrip('.')
    try:
        _m = _il.import_module(mod_nome)
    except Exception as e:                                  # noqa: BLE001
        _p_orfaos.append('%s: import falhou (%s)' % (mod_nome, e))
        continue
    _g = set(vars(_m))
    for _nome, _fn in list(vars(_m).items()):
        if not _isp.isfunction(_fn) or _fn.__module__ != _m.__name__:
            continue
        # `__module__` mente sob functools.wraps: o wrapper do `@_req_cached`
        # (settlement) carrega o nome do modulo decorado, mas o CODIGO — e os
        # globals que ele resolve — sao do request_cache.py. Quem diz onde o
        # codigo mora e o co_filename; o CORPO decorado (que e o que a extracao
        # religou e precisa provar) segue conferido via __wrapped__.
        if os.path.abspath(_fn.__code__.co_filename) != os.path.abspath(_m.__file__):
            _fn = getattr(_fn, '__wrapped__', None)
            if _fn is None or os.path.abspath(_fn.__code__.co_filename) \
                    != os.path.abspath(_m.__file__):
                continue
        _cods = [_fn.__code__] + [c2 for c2 in _fn.__code__.co_consts
                                  if isinstance(c2, _tp.CodeType)]
        for _cod in _cods:
            for _ins in _dis.get_instructions(_cod):
                if _ins.opname == 'LOAD_GLOBAL' and _ins.argval not in _g \
                        and _ins.argval not in dir(_bt):
                    _p_orfaos.append('%s.%s -> %s' % (mod_nome, _nome, _ins.argval))
check('todo LOAD_GLOBAL da platform resolve', sorted(set(_p_orfaos)), [])
# E o alias do routes aponta mesmo para ca — extracao pela metade e a falha
# classica: as duas copias divergem e a que vale e a que ninguem olha.
from apps.pages.platform import anbima as _anb          # noqa: E402
from apps.pages.platform import notifications as _ntf   # noqa: E402
from apps.pages.platform import json_cache as _jch      # noqa: E402
from apps.pages.platform import mail as _pml            # noqa: E402
from apps.pages.platform import dates as _dts           # noqa: E402
from apps.pages.platform import db as _pdb              # noqa: E402
from apps.pages.platform import authz as _atz           # noqa: E402
from apps.pages.platform import settlement as _stl     # noqa: E402
from apps.pages.platform import confirmations as _cnf  # noqa: E402
from apps.pages.platform import counterparty as _cpd   # noqa: E402
from apps.pages.platform import forecast as _fct       # noqa: E402
from apps.pages.platform import electronic_inventory as _eli  # noqa: E402
from apps.pages.platform import manual_confirmation as _mcf   # noqa: E402
from apps.pages.platform import file_interpreter as _pfi      # noqa: E402
from apps.pages.platform import pending_confirmation as _ppc  # noqa: E402
from apps.pages.platform import operations_b3 as _ob3         # noqa: E402
from apps.pages.platform import new_deals as _pnd             # noqa: E402
from apps.pages import routes as R                      # noqa: E402
for _mod, _nomes in (
        (_anb, ('_br_now', '_load_anbima', '_prev_anbima_bizday',
                '_anbima_bizdays_between', '_weekday_bizdays_between',
                '_last_anbima_bizday_of_month', '_pcx_is_bizday',
                '_anbima_holidays', '_anbima_biz_diff', '_anbima_add_biz')),
        (_ntf, ('get_notif_connection', '_ensure_notif_db', '_notif_schema_pronto',
                '_notif_roles', '_create_notification', '_push_notify',
                '_notif_page_url', '_NOTIF_PAGE_URL')),
        (_jch, ('_cache_lock', '_claim_daily_slot', '_release_daily_slot',
                '_atomic_write_json', '_unique_filepath', '_daycache_memo',
                '_day_files', '_day_json', '_daycache_forget')),
        (_pml, ('_get_logo_path', '_get_email_asset', '_attach_email_gradient',
                '_parse_emails', '_email_drafts_response', '_otc_app_url')),
        (_dts, ('_parse_date_any', '_parse_deal_date', '_EN_MONTH_NAMES')),
        (_pdb, ('_DuckDBHandle', 'get_db_connection')),
        (_atz, ('_ALWAYS_ALLOWED_PATHS', '_NAV_URLS', '_CONTROL_PANEL_CARDS',
                '_CP_ENDPOINT_CARD', '_get_page_access', '_read_page_access',
                '_set_page_access', '_page_access_forget', '_session_is_master',
                '_session_is_admin', '_safe_landing', '_user_can_access_page',
                '_get_user_authz', '_read_user_authz', '_get_user_role',
                '_MASTER_SIDS')),
        (_stl, ('_ops_trade_rows', '_ops_swap_trade_rows', '_ops_ndfc_trade_rows',
                '_ops_opt_trade_rows', '_ops_equity_link', '_ops_is_internal_cpty',
                '_opssum_rows', '_opssum_set_status', '_ops_recon',
                '_ops_batch_status', '_opsadv_family_drafts', '_OPS_RECON_TOL',
                '_OPS_SRC_MAP', '_OPSADV_FAMILIES')),
        (_cnf, ('_conf_segregate', '_conf_esteira_stages', '_conf_stage_counts',
                '_conf_generation_page', '_conf_opt_generation_page',
                '_conf_fxo_generation_page', '_conf_fwdstart_rows',
                '_conf_ndf_xml', '_conf_state_load', '_conf_state_save',
                '_conf_cgd_lookup', '_conf_subj_cache', '_CONF_STAGE_ORDER',
                'CONF_STATE_DIR')),
        (_cpd, ('_cpd_path', '_cpd_load', '_cpd_find', '_cpd_save_list',
                '_norm_spn', '_cc_read_rows', '_contacts_norm', '_net_norm',
                '_bank_norm', '_cgd_norm', '_CONTACT_RULE_MAP',
                '_CP_NET_TYPES')),
        (_fct, ('_forecast_collect', '_forecast_payload', '_forecast_spine',
                '_forecast_matrix', '_forecast_latest_ref', '_fcst_lob',
                '_fcst_norm', '_fcst_parse_date', '_fcst_resolve_key',
                '_FORECAST_SOURCES', '_FCST_ENTITY_MAP')),
        (_eli, ('_ei_scan_root', '_ei_actual_dir_name', '_ei_client_dir_names',
                '_ei_iter_files', '_ei_locate_file', '_ei_resolve_client_dir',
                '_ei_sanitize', '_ei_match_key', '_ei_refdata_clients',
                '_EI_ROOT_CACHE', 'EI_SUBFOLDERS', '_EI_TRANSACTIONAL_TYPES')),
        (_mcf, ('_mc_save_from_deal', '_mc_legal_entity', '_mc_confirmation_docs',
                '_mc_pc_sync', '_mc_notify_roles', '_mc_can_validate',
                '_mc_generate_url', '_mc_ei_link', '_mc_stamp_generated',
                '_MC_STAGE_ROLE', '_MC_STAGE_NOTIFY_ROLES',
                '_MC_GENERATE_PRODUCTS', '_COMMODITY_SOURCES')),
        (_pfi, ('_fi_path', '_fi_load', '_fi_clean_template', '_fi_tpl_cache',
                '_fi_tpl_cached', '_fi_variant_key', '_fi_calc_value',
                '_fi_build_line', '_fi_effective_seq_value', '_FI_LE_PAIRS',
                '_FI_CALC_RE')),
        (_ppc, ('_pc_load_rows', '_pc_derive_row', '_pc_signature_pending_status',
                '_pc_signature_status', '_pc_import_update',
                '_pc_is_internal_counterparty', '_pc_apply_auto_rules',
                '_pc_save_from_deal', '_pc_run_daily_maintenance',
                '_pc_snapshot_pending', '_pc_refdata_by_name',
                '_pc_latest_snapshot_rows', '_pc_metrics_history',
                '_PC_ESTEIRA_STATUSES', '_PC_COLUMNS', '_PC_DBS')),
        (_ob3, ('_opb3_load', '_opb3_load_cached', '_opb3_import',
                '_opb3_event_rules', '_opb3_settle_rows', '_opb3_collect',
                '_opb3_breakdown', '_opb3_tipo_maps', '_opb3_msg_load_recipients',
                '_opb3_refdata_by_account', '_opb3_internal_ter_map',
                '_ops_norm_event', '_OPB3_COLUMNS')),
        (_pnd, ('_find_deal_in_cache', '_find_ndf_deal_in_cache', '_find_fxo',
                '_deal_matches', '_fxo_deal_from_row', '_ndf_deal_from_api',
                '_nd_api_amend', '_nd_amend_is_economic', '_nd_cancel_in_file',
                '_fxo_api_pull', '_ndf_api_pull', '_ndf_ref_by_accronym',
                '_ndf_weak_leg', '_generic_ndf_ter_line', '_ndf_comm_ter_lines',
                '_nd_lawton_mirror', '_generic_nd_mapping_candidates',
                '_generic_nd_persist_new_deals', '_fxo_persist_new_deals',
                '_ND_AMEND_COSMETIC_BY_PRODUCT', '_ND_AMEND_KEEP_STATUS'))):
    for _nm in _nomes:
        check('routes.%s e o da platform' % _nm,
              getattr(R, _nm) is getattr(_mod, _nm), True)

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
