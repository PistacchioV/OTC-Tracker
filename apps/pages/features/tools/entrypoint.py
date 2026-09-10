# -*- coding: utf-8 -*-
"""As rotas das Tools — cinco páginas e as APIs que as sustentam.

As páginas são renderizadas no servidor (POST do formulário → a mesma página
com o resultado). Os filtros Jinja `tl_*` formatam número em `#,##0.00` (o
padrão da casa, CLAUDE.md §3) e data em dd/mm/aaaa; são registrados no
blueprint com prefixo para não colidir com nada do tema.
"""
import csv
import io
from datetime import date, datetime, timedelta

from flask import (Response, jsonify, redirect, render_template, request, session,
                   url_for)

from apps.pages import blueprint
from apps.pages.features.tools import commands, domain, queries
from apps.pages.precificador import contagem, liquidacao, renda_fixa, sofr, term_sofr
from apps.pages.precificador.calendario import CALENDARIOS_DISPONIVEIS, para_data
from apps.pages.precificador.erros import ErroDeDado, ErroDeFonte, ErroFerramenta


def _R():
    from apps.pages import routes
    return routes


# ── filtros de formatação (en-US, como o resto do app) ──────────────────────

def tl_money(valor, casas=2):
    if valor is None:
        return '—'
    return '{:,.{c}f}'.format(float(valor), c=casas)


def tl_pct(valor, casas=4):
    if valor is None:
        return '—'
    return tl_money(float(valor) * 100.0, casas) + '%'


def tl_num(valor, casas=0):
    return '—' if valor is None else tl_money(valor, casas)


def tl_date(valor):
    if not valor:
        return '—'
    if isinstance(valor, str):
        d = _R()._fcst_parse_date(valor)
        return d.strftime('%d/%m/%Y') if d else valor
    return valor.strftime('%d/%m/%Y')


def tl_fixed(valor, casas=10):
    return '—' if valor is None else '{:.{c}f}'.format(float(valor), c=casas)


def tl_fx(valor):
    """Fixing de moeda: 4 a 8 casas, as que o valor tem (`domain.fx8`)."""
    return '—' if valor is None else domain.fx8(valor)


for _f in (tl_money, tl_pct, tl_num, tl_date, tl_fixed, tl_fx):
    blueprint.add_app_template_filter(_f, _f.__name__)
blueprint.add_app_template_global(lambda c: liquidacao.INDEXADOR_POR_CODIGO.get(c, c), 'tl_idx_name')
blueprint.add_app_template_global(contagem.nome_curto, 'tl_dc_name')


def _auth_page():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return None


def _auth_api():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return None


_ERROS_DE_TELA = (domain.ErroFormulario, ErroFerramenta, ErroDeFonte, ErroDeDado, ValueError)


def _ref_e_meses():
    hoje = date.today()
    try:
        referencia = para_data(request.args.get('referencia') or hoje.isoformat())
    except ErroDeDado:
        referencia = hoje
    try:
        meses = int(request.args.get('meses') or 6)
    except ValueError:
        meses = 6
    return referencia, meses, hoje


# ── Fixed Income ────────────────────────────────────────────────────────────

@blueprint.route('/tools/fixed-income', methods=['GET', 'POST'])
def tools_fixed_income():
    r = _auth_page()
    if r:
        return r
    hoje = date.today()
    ctx = {
        'form': {'valor': '1,000.00', 'inicio': date(hoje.year, 1, 1).isoformat(),
                 'vencimento': hoje.isoformat(), 'produto': 'cdb',
                 'indexador': renda_fixa.CDI_REALIZADO, 'taxa': '100', 'cdi': '14',
                 'ipca': '4.5', 'arredondar_di': ''},
        'indexadores': renda_fixa.INDEXADORES, 'produtos_rf': renda_fixa.PRODUTOS_RF,
        'retroativos': sorted(renda_fixa.RETROATIVOS), 'hoje': hoje.isoformat(),
        'resultado': None, 'erro': None,
    }
    if request.method == 'POST':
        ctx['form'] = {k: v for k, v in request.form.items()}
        try:
            ctx['resultado'] = queries.calcular_renda_fixa(request.form)
        except _ERROS_DE_TELA as exc:
            ctx['erro'] = str(exc)
    return render_template('pages/tools-fixed-income.html', segment='tools-fixed-income', **ctx)


# ── Swap Calculator ─────────────────────────────────────────────────────────

def _form_padrao_swap(hoje):
    ano_passado = date(hoje.year - 1, hoje.month, 1)
    form = {
        'b3_id': '', 'counterparty': '',
        'data_operacao': ano_passado.isoformat(), 'inicio': ano_passado.isoformat(),
        'fim': hoje.isoformat(), 'vencimento': '', 'base_ajuste': liquidacao.BASE_AUTOMATICA,
        'nocional': '10,000,000.00', 'nocional_original': '10,000,000.00',
        'amortizacao': '0', 'base_amortizacao': liquidacao.SOBRE_ORIGINAL,
        'calendario': 'ANBIMA', 'arredondar_di': '', 'reter_ir': '1',
    }
    padrao = {'ativa': (liquidacao.PRE, '14'), 'passiva': (liquidacao.CDI, '')}
    for lado, (idx, taxa) in padrao.items():
        conv, reg = liquidacao.convencao_padrao(idx)
        form.update({
            lado + '_indexador': idx, lado + '_taxa': taxa, lado + '_convencao': conv,
            lado + '_percentual': '100' if idx == liquidacao.CDI else '',
            lado + '_regime': reg, lado + '_moeda': liquidacao.SEM_CONVERSAO,
            lado + '_ptax_inicial': '', lado + '_ptax_final': '', lado + '_ptax_offset': '',
            lado + '_ni_inicial': '',
            lado + '_ni_final': '', lado + '_fator': '', lado + '_tenor': '3 month',
            lado + '_data_fixing': '', lado + '_taxa_indice': '', lado + '_lookback': '0',
            lado + '_shift': '0', lado + '_ativo': '', lado + '_preco_inicial': '',
            lado + '_preco_final': '',
        })
    return form


@blueprint.route('/tools/swap-calculator', methods=['GET', 'POST'])
def tools_swap_calculator():
    r = _auth_page()
    if r:
        return r
    hoje = date.today()
    ctx = {
        'form': _form_padrao_swap(hoje),
        'indexadores': liquidacao.INDEXADORES, 'convencoes': contagem.CONVENCOES,
        'regimes': contagem.REGIMES, 'moedas': liquidacao.MOEDAS,
        'bases_amortizacao': liquidacao.BASES_AMORTIZACAO,
        'bases_ajuste': liquidacao.BASES_DE_AJUSTE,
        'convencao_padrao': {c: list(liquidacao.convencao_padrao(c)) for c, _ in liquidacao.INDEXADORES},
        'tenores': liquidacao.TENORES_EURIBOR,
        'calendarios': [(nome, desc) for nome, _f, desc in CALENDARIOS_DISPONIVEIS],
        'hoje': hoje.isoformat(), 'resultado': None, 'erro': None,
    }
    if request.method == 'POST':
        ctx['form'] = {k: v for k, v in request.form.items()}
        try:
            ctx['resultado'] = queries.liquidar(request.form)
        except _ERROS_DE_TELA as exc:
            ctx['erro'] = str(exc)
    return render_template('pages/tools-swap-calculator.html', segment='tools-swap-calculator', **ctx)


@blueprint.route('/api/tools/swap-calculator/prefill')
def api_tools_swap_prefill():
    """O que a posição de swap sabe sobre um B3 ID — para a tela preencher.

    404 quando o contrato não está na posição do último dia útil: a tela diz
    isso em vez de preencher com nada."""
    r = _auth_api()
    if r:
        return r
    b3_id = str(request.args.get('id') or '').strip()
    if not b3_id:
        return jsonify({'success': False, 'error': 'Type a B3 ID.'}), 400
    try:
        dados = queries.swap_prefill(b3_id)
    except Exception as exc:                                # noqa: BLE001
        _R().log.error('[tools] prefill %s falhou: %s', b3_id, exc)
        return jsonify({'success': False, 'error': 'Could not read the swap position.'}), 500
    if not dados.get('found'):
        return jsonify({'success': False,
                        'error': '{} is not in the swap position of the last business day '
                                 '(Live Position › Swap Characteristics).'.format(b3_id)}), 404
    dados['success'] = True
    return jsonify(dados)


# ── SOFR Index ──────────────────────────────────────────────────────────────

@blueprint.route('/tools/sofr-index', methods=['GET', 'POST'])
def tools_sofr_index():
    r = _auth_page()
    if r:
        return r
    hoje = date.today()
    ctx = {'form': {'inicio': (hoje - timedelta(days=90)).isoformat(), 'fim': hoje.isoformat(),
                    'lookback': '0', 'shift': '0'},
           'resultado': None, 'erro': None}
    # O que o NY Fed publica ABERTO (overnight, médias de 30/90/180 dias e o
    # índice) mora aqui, ao lado da composição que o acumula — é a taxa
    # REALIZADA. A tela de Term SOFR é a curva a termo da CME, cotada de
    # antemão: as duas na mesma página davam dois quadros de "valores
    # publicados" respondendo a perguntas diferentes.
    ctx['publicados'] = queries.sofr_publicados(hoje, 6)
    if request.method == 'POST':
        ctx['form'] = {k: v for k, v in request.form.items()}
        try:
            ctx['resultado'] = queries.compor_sofr(request.form)
        except _ERROS_DE_TELA as exc:
            ctx['erro'] = str(exc)
    return render_template('pages/tools-sofr-index.html', segment='tools-sofr-index', **ctx)


# ── Term SOFR ───────────────────────────────────────────────────────────────

@blueprint.route('/tools/term-sofr')
def tools_term_sofr():
    r = _auth_page()
    if r:
        return r
    referencia, meses, hoje = _ref_e_meses()
    ctx = queries.term_sofr_context(referencia, meses)
    ctx['hoje'] = hoje.isoformat()
    return render_template('pages/tools-term-sofr.html', segment='tools-term-sofr', **ctx)


@blueprint.route('/api/tools/term-sofr/import', methods=['POST'])
def api_tools_term_sofr_import():
    r = _auth_api()
    if r:
        return r
    arquivo = request.files.get('file') or request.files.get('arquivo')
    if arquivo is None or not (arquivo.filename or '').strip():
        return jsonify({'success': False, 'error': 'No file sent.'}), 400
    try:
        res = commands.importar_term_sofr(arquivo.filename, arquivo.read())
    except (term_sofr.ErroTermSOFR, ValueError) as exc:
        return jsonify({'success': False, 'error': str(exc)}), 422
    res['success'] = True
    return jsonify(res)


@blueprint.route('/api/tools/term-sofr/rate')
def api_tools_term_sofr_rate():
    """A taxa importada de um prazo numa data — tira o Term SOFR da digitação."""
    r = _auth_api()
    if r:
        return r
    try:
        meses = int(request.args.get('months') or request.args.get('meses') or 3)
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid tenor.'}), 400
    quando = request.args.get('date') or date.today().isoformat()
    try:
        taxa, vigente = queries.term_sofr_taxa(meses, quando)
    except ErroDeDado as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    if taxa is None:
        return jsonify({'success': False,
                        'error': 'No {}-month Term SOFR imported up to {}.'.format(
                            meses, tl_date(quando))}), 404
    return jsonify({'success': True, 'rate': taxa, 'percent': taxa * 100.0,
                    'date': vigente.isoformat() if vigente else None, 'months': meses})


@blueprint.route('/api/tools/fixing-rate')
def api_tools_fixing_rate():
    """A taxa a termo de um prazo numa data, da BASE local — Term SOFR (o que o
    dropzone importou) e EURIBOR (a base do Banco da Finlândia).

    UM endpoint para os dois porque é a MESMA pergunta: que taxa o contrato
    fixou naquele prazo, naquele dia. Dois seriam duas respostas para divergir
    no primeiro caso de borda — e o `/api/tools/term-sofr/rate` acima segue de
    pé pela mesma implementação, para a aba já aberta não quebrar."""
    r = _auth_api()
    if r:
        return r
    idx = (request.args.get('index') or liquidacao.TERM_SOFR).strip()
    if idx not in liquidacao.COM_FIXING:
        return jsonify({'success': False,
                        'error': '{} has no forward fixing.'.format(idx)}), 404
    tenor = (request.args.get('tenor') or '3 month').strip()
    quando = request.args.get('date') or date.today().isoformat()
    try:
        alvo = para_data(quando)
    except ErroDeDado:
        return jsonify({'success': False, 'error': 'Invalid date.'}), 400
    taxa, vigente, motivo = queries.taxa_do_fixing(idx, tenor, alvo)
    if taxa is None:
        return jsonify({'success': False, 'error': motivo}), 404
    return jsonify({'success': True, 'rate': taxa, 'percent': taxa * 100.0,
                    'date': vigente.isoformat() if vigente else None,
                    'index': idx, 'tenor': tenor})


@blueprint.route('/tools/term-sofr/csv')
def tools_term_sofr_csv():
    """A curva IMPORTADA em CSV — o que a tela mostra. Exportar a base do Fed
    de uma página que não a exibe entregaria um arquivo que não bate com nada
    na frente de quem clicou."""
    r = _auth_page()
    if r:
        return r
    base = term_sofr.carregar()
    if base.vazio:
        return Response('empty base', status=404, mimetype='text/plain; charset=utf-8')
    campos = base.campos
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['Date'] + [rot for c, rot, _m in term_sofr.CAMPOS if c in campos])
    tabela = base.por_data()
    for d in base.datas:
        linha = tabela[d]
        w.writerow([d.strftime('%d/%m/%Y')]
                   + ['{:.5f}'.format(linha[c] * 100) if c in linha else '' for c in campos])
    nome = 'term_sofr_{:%Y%m%d}_{:%Y%m%d}.csv'.format(base.inicio, base.fim)
    return Response('\ufeff' + buf.getvalue(), content_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="{}"'.format(nome)})


@blueprint.route('/tools/sofr-index/csv')
def tools_sofr_index_csv():
    """A base realizada do NY Fed em CSV — o quadro que agora vive nesta tela."""
    r = _auth_page()
    if r:
        return r
    historico = sofr.HistoricoSOFR.da_base()
    if not historico.datas:
        return Response('empty base', status=404, mimetype='text/plain; charset=utf-8')
    campos = historico.campos
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['Date'] + [rot for c, rot in sofr.CAMPOS if c in campos] + ['SOFR Index'])
    tabela = historico.por_data()
    for d in historico.datas:
        linha = tabela[d]
        w.writerow([d.strftime('%d/%m/%Y')]
                   + ['{:.5f}'.format(linha[c] * 100) if c in linha else '' for c in campos]
                   + ['{:.8f}'.format(linha['indice']) if 'indice' in linha else ''])
    nome = 'sofr_{:%Y%m%d}_{:%Y%m%d}.csv'.format(historico.inicio, historico.fim)
    return Response('\ufeff' + buf.getvalue(), content_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="{}"'.format(nome)})


@blueprint.route('/api/tools/term-sofr/sync', methods=['POST'])
def api_tools_term_sofr_sync():
    r = _auth_api()
    if r:
        return r
    try:
        rel = commands.sincronizar_sofr()
    except ErroDeFonte as exc:
        return jsonify({'success': False, 'error': str(exc)}), 502
    rel['success'] = True
    return jsonify(rel)


# ── EURIBOR ─────────────────────────────────────────────────────────────────

@blueprint.route('/tools/euribor')
def tools_euribor():
    r = _auth_page()
    if r:
        return r
    referencia, meses, hoje = _ref_e_meses()
    ctx = queries.euribor_context(referencia, meses)
    ctx['hoje'] = hoje.isoformat()
    return render_template('pages/tools-euribor.html', segment='tools-euribor', **ctx)


@blueprint.route('/tools/euribor/csv')
def tools_euribor_csv():
    r = _auth_page()
    if r:
        return r
    from apps.pages.precificador import euribor
    curva = euribor.CurvaEuribor.da_base()
    if not curva.datas:
        return Response('empty base', status=404, mimetype='text/plain; charset=utf-8')
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(['Date'] + curva.tenores)
    tabela = curva.por_data()
    for d in curva.datas:
        w.writerow([d.strftime('%d/%m/%Y')]
                   + ['{:.3f}'.format(tabela[d][t] * 100) if t in tabela[d] else ''
                      for t in curva.tenores])
    nome = 'euribor_{:%Y%m%d}_{:%Y%m%d}.csv'.format(curva.inicio, curva.fim)
    return Response('\ufeff' + buf.getvalue(), content_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="{}"'.format(nome)})


@blueprint.route('/api/tools/euribor')
def api_tools_euribor():
    r = _auth_api()
    if r:
        return r
    from apps.pages.precificador import euribor
    curva = euribor.CurvaEuribor.da_base()
    tabela = curva.por_data()
    return jsonify({'success': True, 'source': euribor.PAGINA,
                    'start': curva.inicio.isoformat() if curva.inicio else None,
                    'end': curva.fim.isoformat() if curva.fim else None,
                    'tenors': curva.tenores,
                    'observations': [{'date': d.isoformat(),
                                      'rates': {t: tabela[d][t] for t in curva.tenores if t in tabela[d]}}
                                     for d in curva.datas]})


@blueprint.route('/api/tools/euribor/sync', methods=['POST'])
def api_tools_euribor_sync():
    r = _auth_api()
    if r:
        return r
    try:
        rel = commands.sincronizar_euribor()
    except ErroDeFonte as exc:
        return jsonify({'success': False, 'error': str(exc)}), 502
    rel['success'] = True
    return jsonify(rel)


# `datetime` fica importado para o `tl_date` aceitar datetime além de date.
_ = datetime
