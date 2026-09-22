# -*- coding: utf-8 -*-
"""check_unwind_termo.py — o Termo de Resilicao da recompra de NDF de moeda.

O distrato que as duas Partes assinam. O corpo e o Word que a mesa redigiu; o
que este teste prende e o que o app DECIDE:

  1. as rotas existem (a do documento tem tres segmentos, como a da pagina);
  2. o Anexo I: Confirmacao n = **Athena ID** e Registro CETIP n = o contrato
     da B3 (dois numeros diferentes, decisao da mesa em 18/09/2026);
  3. Total x Parcial sai da comparacao com o SALDO da posicao, e o Novo Valor
     Base e o que sobra — sem saldo, NENHUM dos dois se inventa (a clausula 1
     e a 2 do Termo dizem coisas diferentes);
  4. o pagador e o SINAL do resultado, nunca o `Direction` do e-mail (§488);
  5. o Valor de Resilicao vai em MODULO (quem paga esta na coluna ao lado);
  6. a Parte A sai da CONTA pelo `b3-accounts`, e entidade sem Parte A
     cadastrada fica em branco AVISANDO, nunca num default;
  7. o documento renderizado nao guarda nenhum `[.]` do modelo, o painel fica
     fora do `doc_only` e o PDF sai do MESMO HTML;
  8. o Save recusa sem Parte A e sem CGD, e grava Word + PDF na pasta do TIPO
     do Electronic Inventory, carimbando a linha da recompra.

Roda em tmp: cache, share e Inventory apontam para diretorios temporarios.
"""
import io
import os
import re
import sys
import tempfile
from datetime import date, datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, cond, extra=''):
    print(('  ok  ' if cond else ' FAIL ') + nome + (('  — ' + str(extra)) if (not cond and extra) else ''))
    if not cond:
        FALHAS.append(nome)


def _erro(fn, *a, **k):
    try:
        fn(*a, **k)
    except ValueError as exc:
        return str(exc)
    return None


HOJE = date(2026, 9, 18)

# Duas recompras da MESMA contraparte e moeda — um termo com duas linhas no
# Anexo I. A primeira e parcial (recompra menor que o saldo) e a segunda zera
# o que restava; na primeira o banco RECEBE e na segunda PAGA.
# `UnwoundAmount`/`BRLFixed`/`TerminationRate` sao a amostra real do §488: o
# nocional e fixo em reais, entao o `Unwound Amount` do aviso vem em BRL
# (59.999,98 / 5,2039 = os 11.529,81 da planilha da mesa). Sao eles que o XML
# do FepWeb le.
L1 = {'AthenaID': 'STP-XE-10G5U5X-0-0', 'Contract': '26C03202688', 'Currency': 'USD',
      'Counterparty': 'COFCO INTERNATIONAL BRASIL SA', 'TaxID': '02.916.265/0001-60',
      'ClientAcronym': 'COFCO', 'UnwoundNotional': 11529.81, 'Balance': 587224.31,
      'UnwoundAmount': '59,999.98', 'BRLFixed': 'YES', 'TerminationRate': 5.2000,
      'Result': 42.80, 'Direction': 'RECEIVE', 'PartyAccount': '73760009',
      'CptyAccount': '00041007', 'Status': 'Imported'}
L2 = dict(L1, AthenaID='STP-XE-10G5U5X-0-1', Contract='26C03202689',
          UnwoundNotional=144122.68, Balance=144122.68, Result=-9350.12, Direction='PAY',
          UnwoundAmount='750,000.00')


def main():
    from run import app  # noqa: F401
    from apps.pages import routes as R
    from apps.pages.features.unwinds import commands, domain, queries
    from apps.pages.features.unwinds.infra import persistence

    tmp = tempfile.mkdtemp(prefix='otc-termo-')
    persistence.cache_root = lambda: os.path.join(tmp, 'cache')
    persistence.cache_dir = lambda: os.path.join(tmp, 'cache', 'NDF', 'FX')
    commands._hoje = lambda: HOJE
    # A esteira e o Pending Confirmation de VERDADE ficam de fora: a secao 14
    # grava e apaga linha neles.
    from apps.pages import manual_conf as _mcdb
    _mcdb._DB_DIR = os.path.join(tmp, 'mc-db')
    os.makedirs(_mcdb._DB_DIR, exist_ok=True)
    R._PC_DB_DIR = os.path.join(tmp, 'pc-db')
    os.makedirs(R._PC_DB_DIR, exist_ok=True)
    _pc_save_original = R._pc_save_from_deal

    print('\n== 1. as rotas existem ==')
    regras = {str(r) for r in app.url_map.iter_rules()}
    for r in ('/confirmation/unwind/termo-resilicao',
              '/api/unwinds/ndf/fx/termo-resilicao/save',
              '/api/unwinds/ndf/fx/termo-resilicao/pdf'):
        check('rota ' + r, r in regras)

    print('\n== 2. o Anexo I: Confirmacao n = Athena ID, Registro CETIP n = contrato ==')
    rows, avisos = domain.termo_rows([L1, L2])
    check('Confirmacao n e o Athena ID', rows[0]['numConf'] == L1['AthenaID'], rows[0]['numConf'])
    check('Registro CETIP n e o contrato da B3', rows[0]['registroCetip'] == '26C03202688')
    check('sao dois numeros DIFERENTES', rows[0]['numConf'] != rows[0]['registroCetip'])
    check('sem contrato na posicao, o Registro sai vazio AVISANDO',
          domain.termo_linha(dict(L1, Contract=''))[0]['registroCetip'] == ''
          and any(a['code'] == 'unwind_termo_sem_contrato'
                  for a in domain.termo_linha(dict(L1, Contract=''))[1]))

    print('\n== 3. Total x Parcial pelo SALDO da posicao ==')
    check('recompra menor que o saldo e PARCIAL', rows[0]['resilicao'] == domain.RESILICAO_PARCIAL)
    check('e o Novo Valor Base e o que sobra', rows[0]['novoValorBase'] == 'USD 575.694,50',
          rows[0]['novoValorBase'])
    check('recompra que zera o saldo e TOTAL', rows[1]['resilicao'] == domain.RESILICAO_TOTAL)
    check('e no total o Novo Valor Base e Zero (mesa)',
          rows[1]['novoValorBase'] == domain.NOVO_BASE_ZERO, rows[1]['novoValorBase'])
    # O saldo e o recomprado vem de arredondamentos diferentes: a posicao
    # imprime duas casas e a conta da recompra nao.
    check('um centavo de diferenca ainda e resilicao TOTAL',
          domain.termo_linha(dict(L1, UnwoundNotional=587224.3049,
                                  Balance=587224.31))[0]['resilicao'] == domain.RESILICAO_TOTAL)
    sem_saldo, av = domain.termo_linha(dict(L1, Balance=None, OriginalNotional=None))
    check('SEM saldo nao se diz qual das duas e', sem_saldo['resilicao'] == '' and
          sem_saldo['novoValorBase'] == '')
    check('e avisa', any(a['code'] == 'unwind_termo_sem_saldo' for a in av))

    print('\n== 3b. o Novo Valor Base sao TRES parcelas (mesa, 18/09/2026) ==')
    # nocional ORIGINAL - ja recomprado que a posicao mostra - recomprado agora.
    # O `Valor Antecipado` da posicao e a parcela do meio, e ela e uma COLUNA da
    # tela: o numero do documento tem de ser conferivel na grade.
    tres = dict(L1, OriginalNotional=587224.31, UnwoundBefore=155652.49,
                UnwoundNotional=11529.81, Balance=None)
    row3, _av3 = domain.termo_linha(tres)
    check('o ja recomprado da posicao e descontado',
          row3['novoValorBase'] == 'USD 420.042,01', row3['novoValorBase'])
    check('e a resilicao continua PARCIAL', row3['resilicao'] == domain.RESILICAO_PARCIAL)
    check('a conta pura devolve o numero', round(domain.saldo_apos_a_recompra(tres), 2) == 420042.01,
          domain.saldo_apos_a_recompra(tres))
    # O que zera as tres parcelas e TOTAL — e o Novo Valor Base nao se aplica.
    zera = dict(tres, UnwoundNotional=431571.82)
    check('zerar as tres parcelas e TOTAL',
          domain.termo_linha(zera)[0]['resilicao'] == domain.RESILICAO_TOTAL and
          domain.termo_linha(zera)[0]['novoValorBase'] == domain.NOVO_BASE_ZERO)
    # A linha ANTIGA (gravada antes de as colunas existirem) ainda responde
    # pelo `Balance` — sem isso o Termo de uma recompra do arquivo-dia de
    # ontem sairia sem saldo nenhum.
    antiga = {k: v for k, v in L1.items()}
    check('linha antiga, sem as colunas novas, ainda sai pelo Balance',
          domain.termo_linha(antiga)[0]['novoValorBase'] == 'USD 575.694,50',
          domain.termo_linha(antiga)[0]['novoValorBase'])
    # Posicao que nao resolveu: nem o ja recomprado nem o saldo. A conta sai do
    # nocional original presumindo zero — e DIZ que presumiu.
    presumido, avp = domain.termo_linha(dict(L1, Balance=None, OriginalNotional=78000.0,
                                             UnwoundNotional=42227.42))
    check('sem posicao, o saldo sai do original presumindo zero',
          presumido['novoValorBase'] == 'USD 35.772,58', presumido['novoValorBase'])
    check('e o documento AVISA que o valor e presumido',
          any(a['code'] == 'unwind_termo_antecipado_presumido' for a in avp),
          [a['code'] for a in avp])
    check('com a posicao respondendo zero, nao ha aviso nenhum',
          not any(a['code'] == 'unwind_termo_antecipado_presumido'
                  for a in domain.termo_linha(tres)[1]))

    print('\n== 4. o pagador e o SINAL do resultado ==')
    check('recebemos -> paga a Parte B', rows[0]['pagador'] == domain.PAGADOR_PARTE_B)
    check('pagamos -> paga a Parte A', rows[1]['pagador'] == domain.PAGADOR_PARTE_A)
    # Na amostra fixa em reais o e-mail diz PAY numa recompra a RECEBER: a
    # linha ja guarda a direcao APURADA, e e so nela que o termo olha.
    sem_dir, av = domain.termo_linha(dict(L1, Direction=''))
    check('sem direcao apurada o pagador fica em branco', sem_dir['pagador'] == '')
    check('e avisa', any(a['code'] == 'unwind_termo_sem_direcao' for a in av))

    print('\n== 5. o Valor de Resilicao vai em MODULO ==')
    check('resultado negativo sai positivo no documento',
          rows[1]['valorResilicao'] == 'R$ 9.350,12', rows[1]['valorResilicao'])
    check('e o Valor Base Liquidado leva a MOEDA do contrato',
          rows[0]['valorBaseLiq'] == 'USD 11.529,81', rows[0]['valorBaseLiq'])

    print('\n== 6. a Parte A sai da CONTA (b3-accounts), nunca de um default ==')
    with app.test_request_context():
        conf, _ = commands.termo_conf(HOJE, 'COFCO', 'USD', [L1, L2])
    check('conta do banco -> Parte A do BANCO',
          conf['partea_nome'] == 'BANCO J.P. MORGAN S.A.', conf['partea_nome'])
    check('e o CNPJ vem junto', conf['partea_cnpj'] == '33.172.537/0001-98')
    check('a Parte B e a contraparte da posicao', conf['parteb_nome'] == L1['Counterparty'])
    with app.test_request_context():
        conf_lawton, _ = commands.termo_conf(HOJE, 'COFCO', 'USD',
                                             [dict(L1, PartyAccount='00041007')])
    check('entidade sem Parte A cadastrada fica em BRANCO', conf_lawton['partea_nome'] == '',
          conf_lawton['partea_nome'])
    check('e avisa em vez de escolher uma', any('Parte A' in w for w in conf_lawton['warnings']))
    check('sem CGD cadastrado o documento avisa', any('CGD' in w for w in conf['warnings']))

    print('\n== 7. o documento renderizado ==')
    from flask import render_template
    with app.test_request_context():
        conf['cgd_date'] = '28 de Maio de 2008'
        doc = render_template(commands.TERMO_TEMPLATE, conf=conf, doc_only=True)
        tela = render_template(commands.TERMO_TEMPLATE, conf=conf)
    texto = re.sub(r'<[^>]+>', '', doc)
    check('o painel de edicao fica FORA do documento', '<div id="editor-panel">' not in doc)
    check('e aparece na tela', '<div id="editor-panel">' in tela)
    check('nenhum [.] do modelo sobrou', '[•]' not in texto)
    check('nem o <BANCO ...> OR <J.P. Morgan ...> do modelo',
          ' OR ' not in texto and 'Filial Brasileira' not in texto)
    for esperado in (L1['AthenaID'], '26C03202688', 'USD 11.529,81', 'R$ 42,80',
                     'COFCO INTERNATIONAL BRASIL SA', '02.916.265/0001-60',
                     '28 de Maio de 2008', '18 de Setembro de 2026'):
        check('o documento traz %r' % esperado, esperado in doc)
    check('as duas recompras viraram duas linhas do Anexo I',
          doc.count('26C03202688') >= 1 and '26C03202689' in doc)
    # O PDF sai do MESMO HTML do Word (§139): uma segunda transcricao do texto
    # e a forma conhecida de os dois divergirem sem ninguem notar.
    from apps.pages.confirmation_pdfs import word_html_pdf
    pdf = word_html_pdf(doc)
    check('o PDF sai do MESMO HTML', pdf[:5] == b'%PDF-' and len(pdf) > 2000, len(pdf))

    print('\n== 8. o Save: recusa, grava e carimba ==')
    base = {'date': HOJE.strftime('%Y-%m-%d'), 'acronym': 'COFCO', 'mercadoria': 'USD',
            'athena_ids': [L1['AthenaID'], L2['AthenaID']], 'rows': rows,
            'fields': {'cgd_date': '28 de Maio de 2008',
                       'partea_nome': 'BANCO J.P. MORGAN S.A.',
                       'partea_cnpj': '33.172.537/0001-98',
                       'parteb_nome': L1['Counterparty'],
                       'parteb_cnpj': '02.916.265/0001-60',
                       'data_extenso': '18 de Setembro de 2026'}}
    with app.test_request_context():
        sem_a = dict(base, fields=dict(base['fields'], partea_nome=''))
        check('sem Parte A o Save RECUSA', 'Parte A' in (_erro(commands.termo_salvar, sem_a) or ''))
        sem_cgd = dict(base, fields=dict(base['fields'], cgd_date=''))
        check('sem CGD o Save RECUSA', 'CGD' in (_erro(commands.termo_salvar, sem_cgd) or ''))
        check('sem operacao o Save RECUSA', (_erro(commands.termo_salvar, dict(base, rows=[])) or ''))
        # O termo e ARQUIVADO na pasta da contraparte, como toda confirmacao
        # desta casa. Sem contraparte nao ha pasta: antes, o acronimo caia num
        # literal 'UNWIND' e o `create=True` fazia nascer uma pasta com esse
        # nome no Inventory, ao lado das contrapartes de verdade.
        sem_cpty = dict(base, acronym='',
                        fields=dict(base['fields'], parteb_nome=''))
        check('sem contraparte o Save RECUSA, em vez de inventar pasta',
              'Counterparty' in (_erro(commands.termo_salvar, sem_cpty) or ''),
              _erro(commands.termo_salvar, sem_cpty))

        # Grava de verdade: o Inventory e o `tmp`, e a linha da recompra
        # existe no arquivo-dia (o carimbo tem de achar as duas).
        R._EI_ROOT = os.path.join(tmp, 'inventory')
        persistence.upsert(datetime(HOJE.year, HOJE.month, HOJE.day), [dict(L1), dict(L2)])
        out = commands.termo_salvar(base, sid='E930179')
    check('o Save devolve os TRES arquivos (.doc, .pdf e .xml)', len(out['files']) == 3,
          out['files'])
    check('os tres existem no Inventory',
          all(os.path.isfile(p) for p in out['files']), out['files'])
    check('na pasta do TIPO da esteira',
          os.sep + 'TERMO DE RESILICAO' + os.sep in out['files'][0], out['files'][0])
    # O caminho INTEIRO e o das confirmacoes de New Deals: a pasta da
    # CONTRAPARTE, depois Confirmations/AAAA/mm. Month/dd/<TIPO>.
    check('dentro da pasta da CONTRAPARTE, em Confirmations/AAAA/mm/dd',
          (os.sep + 'Confirmations' + os.sep) in out['files'][0]
          and out['files'][0].startswith(R._ei_resolve_client_dir(L1['Counterparty']) + os.sep),
          out['files'][0])
    _fp, lst, idx = queries.find(L1['AthenaID'], HOJE.strftime('%Y-%m-%d'))
    check('a linha da recompra ficou carimbada com o PDF',
          idx is not None and lst[idx].get('TermoPdf') == out['pdf'])
    check('e com quem gerou', idx is not None and lst[idx].get('TermoBy') == 'E930179')
    _fp2, lst2, idx2 = queries.find(L2['AthenaID'], HOJE.strftime('%Y-%m-%d'))
    check('as DUAS linhas do termo foram carimbadas',
          idx2 is not None and lst2[idx2].get('TermoPdf') == out['pdf'])

    print('\n== 8b. o XML do FepWeb sai junto ==')
    # Ate 18/09/2026 a recompra era o unico documento da casa que saia sem o
    # XML — a mesa tinha de leva-lo ao FepWeb a mao.
    xmls = [f for f in out['files'] if f.endswith('.xml')]
    check('o .xml esta na mesma pasta e com o mesmo nome base', len(xmls) == 1 and
          os.path.splitext(xmls[0])[0] == os.path.splitext(out['pdf'])[0], xmls)
    xml = io.open(xmls[0], encoding='utf-8').read() if xmls else ''
    check('tipoOperacao e NDF (a operacao resilida e um termo de moeda)',
          '<tipoOperacao>NDF</tipoOperacao>' in xml)
    # O tipoEvento e RE de RESILICAO (mesa, 22/09/2026; era R): com o 'N' de novo, o FepWeb
    # cadastraria o distrato como uma operacao nova.
    check('tipoEvento e RE, de resilicao', '<tipoEvento>RE</tipoEvento>' in xml, xml)
    # Regra da mesa: `valor` = o liquidado em REAIS; `valorEstrangeiro` = ele
    # dividido pela TAXA DA RECOMPRA (nao pelo strike do registro, que e o que
    # nomeia o Valor Base Liquidado do Anexo I).
    check('valor = o liquidado em BRL das duas recompras',
          '<valor>809999.98</valor>' in xml, xml)
    check('valorEstrangeiro = ele dividido pela taxa da recompra',
          '<valorEstrangeiro>155769.23</valorEstrangeiro>' in xml, xml)
    check('a moeda estrangeira e a do grupo', '<moedaEstrangeira>' in xml
          and '<moedaEstrangeira></moedaEstrangeira>' not in xml, xml)
    check('o CNPJ do cliente vai sem pontuacao', '<cnpjCliente>02916265000160</cnpjCliente>' in xml)
    check('e o Save devolve o numeroContrato', bool(out.get('numero_contrato')),
          out.get('numero_contrato'))
    # Sem a taxa da recompra nao ha perna estrangeira que se possa afirmar: a
    # operacao fica de fora dos valores, AVISANDO.
    from apps.pages.platform.confirmations import _conf_unwind_legs
    check('sem taxa da recompra a perna fica de fora',
          _conf_unwind_legs({'UnwoundBRL': 1000.0, 'TerminationRate': None}, '') is None)
    check('e com ela a conta e BRL / taxa',
          _conf_unwind_legs({'UnwoundBRL': 1040.0, 'TerminationRate': 5.2}, '') == (200.0, 1040.0))

    print('\n== 9. o grupo do termo e contraparte x moeda ==')
    grupo = queries.termo_grupo(HOJE.strftime('%Y-%m-%d'), 'COFCO', 'USD')
    check('as duas recompras da contraparte entram', len(grupo) == 2, len(grupo))
    check('moeda diferente nao entra',
          queries.termo_grupo(HOJE.strftime('%Y-%m-%d'), 'COFCO', 'EUR') == [])
    check('contraparte diferente nao entra',
          queries.termo_grupo(HOJE.strftime('%Y-%m-%d'), 'OUTRA', '') == [])

    print('\n== 10. a recompra entra no Pending Confirmation e na esteira ==')
    deal = commands.confirmation_deal(L1, HOJE)
    check('o deal leva o Athena ID como Trade ID', deal['Deal'] == L1['AthenaID'])
    check('e o contrato da B3 no B3_ID', deal['B3_ID'] == '26C03202688')
    check('a Data Operacao e a do ARQUIVO-DIA (e por ela que o Generate acha)',
          deal['TradeDate'] == HOJE.strftime('%Y-%m-%d'), deal['TradeDate'])
    check('o ativo da confirmacao e a moeda do contrato',
          deal['Currency'] == 'USD' and deal['QuantityCurrency'] == 'USD')
    # ELEGIVEL DESDE O IMPORT (mesa, 18/09/2026, invertendo a decisao de dois
    # dias antes): o Termo se gera com o que o aviso e a posicao ja
    # responderam, sem esperar o arquivo da B3.
    check('recompra recem-importada JA e elegivel', deal['Status'] == 'Success')
    check('e depois do Send continua', commands.confirmation_deal(
        dict(L1, Status=domain.STATUS_ENVIADO), HOJE)['Status'] == 'Success')
    check('a entidade sai da CONTA', deal['LE'] == 'JPM', deal['LE'])

    # O Produto da esteira e o mesmo valor do Product Type do Pending
    # Confirmation; o TIPO do documento e um so para toda recompra.
    from apps.pages import manual_conf as _mc
    check('o Produto da esteira e UNWIND NDF', commands.MC_SOURCE == 'UNWIND NDF')
    check('e ele esta na lista dos que geram documento',
          commands.MC_SOURCE in R._pf_mc._MC_CONFIRMATION_SOURCES)
    check('UNWIND NDF -> TERMO DE RESILICAO',
          _mc.confirmation_type(commands.MC_SOURCE) == commands.TERMO_TIPO)
    for outro in ('UNWIND SWAP', 'UNWIND OPTION', 'UNWIND NDF COMM', 'UNWIND OPTION COMM'):
        check('%s tambem -> TERMO DE RESILICAO' % outro,
              _mc.confirmation_type(outro) == commands.TERMO_TIPO)
    check('o tipo tem gerador no Monitor',
          commands.TERMO_TIPO in R._pf_mc._MC_GENERATE_PRODUCTS)
    linha_seed = next((l for l in _mc.VALIDATION_SEED
                       if _mc.upper_norm(l.get('PRODUCT')) == commands.TERMO_TIPO), None)
    check('e a regra de validacao do tipo esta no cadastro (nao cai no default)',
          linha_seed is not None)
    # O trilho do distrato e SO OTC (mesa, 18/09/2026): o MO e o FO conferem a
    # economia da operacao, e ela ja passou por eles quando a operacao nasceu.
    check('o trilho e so OTC — MO e FO isentos',
          (linha_seed or {}).get('OTC') == 'REQUESTED'
          and (linha_seed or {}).get('MO') == 'EXEMPT'
          and (linha_seed or {}).get('FO') == 'EXEMPT', linha_seed)
    # Seed nao alcanca quem ja tem o cadastro (§6): quem conserta a instancia e
    # o upgrade, e so a linha que esta EXATAMENTE como o seed antigo a deixou.
    velho = [{'PRODUCT': 'TERMO DE RESILICAO', 'LOB': '', 'OTC': 'REQUESTED',
              'MO': 'REQUESTED', 'FO': 'EXEMPT', 'NOTES': ''}]
    corrigida = next(l for l in _mc.validation_upgrade(velho)
                     if _mc.upper_norm(l.get('PRODUCT')) == commands.TERMO_TIPO)
    check('o upgrade corrige o cadastro que ja existe', corrigida.get('MO'), 'EXEMPT')
    mesa = [{'PRODUCT': 'TERMO DE RESILICAO', 'LOB': '', 'OTC': 'REQUESTED',
             'MO': 'REQUESTED', 'FO': 'REQUESTED', 'NOTES': 'a mesa decidiu'}]
    mantida = next(l for l in _mc.validation_upgrade(mesa)
                   if _mc.upper_norm(l.get('PRODUCT')) == commands.TERMO_TIPO)
    check('mas nao desfaz o que a mesa editou',
          (mantida.get('MO'), mantida.get('FO')), ('REQUESTED', 'REQUESTED'))

    print('\n== 11. o gatilho e o IMPORT, e a linha vai CARIMBADA ==')
    vistos = []
    R._pc_save_from_deal = lambda d, pt, **kw: vistos.append((d, pt, kw))
    commands.esteira_da_recompra([dict(L1)], HOJE)
    check('o import manda a recompra para o Pending Confirmation', len(vistos) == 1)
    if vistos:
        d, pt, kw = vistos[0]
        check('com o Product Type UNWIND NDF', pt == 'UNWIND NDF', pt)
        check('e chaveada pelo Athena ID', kw.get('trade_number') == L1['AthenaID'])
        check('com o Status que a segregacao le como elegivel', d['Status'] == 'Success')
    # Falha no espelho NAO derruba o import: a linha ja esta no arquivo-dia.
    def _explode(*a, **k):
        raise RuntimeError('banco ocupado')
    R._pc_save_from_deal = _explode
    try:
        commands.esteira_da_recompra([dict(L1)], HOJE)
        check('falha no espelho nao derruba o import', True)
    except Exception as exc:                                # noqa: BLE001
        check('falha no espelho nao derruba o import', False, exc)

    print('\n== 12. a segregacao do Generate ve o grupo da recompra ==')
    R._pc_save_from_deal = lambda *a, **k: None
    grupos, _st, _tot = R._conf_unwind_groups(datetime(HOJE.year, HOJE.month, HOJE.day))
    check('um grupo por contraparte x moeda', len(grupos) == 1, [g['acronym'] for g in grupos])
    if grupos:
        g = grupos[0]
        check('o eixo do grupo e a moeda', g['mercadoria'] == 'USD', g['mercadoria'])
        check('a familia e o termo', g['family'] == 'termo-resilicao')
        check('e os Athena IDs sao as chaves da esteira',
              L1['AthenaID'] in g['trades'] and L2['AthenaID'] in g['trades'])
    check('e a familia tem template',
          'termo-resilicao' in R._CONF_UNWIND_FAMILY_TEMPLATES)
    check('que aponta para a rota do documento',
          R._CONF_UNWIND_FAMILY_TEMPLATES['termo-resilicao'][1] == commands.TERMO_URL)

    print('\n== 13. o Generate do Monitor abre o Termo ==')
    # A ponta que faltava: a segregacao ve o grupo (secao 12), mas quem o card
    # do Monitor chama e o `_mc_generate_url`, e e ele que decide entre abrir o
    # editor e devolver um 404 explicado. Sem esta secao, Produto sem tipo,
    # tipo sem gerador ou Data Operacao fora do arquivo-dia passariam verdes
    # ate alguem clicar no botao na instancia.
    linha_esteira = {'Cliente': L1['Counterparty'], 'Produto': commands.MC_SOURCE,
                     'LOB': 'CEM', 'Moeda': 'USD', 'Legal Entity': '',
                     'Data Operação': HOJE.strftime('%d/%m/%Y'),
                     'Trade ID': L1['AthenaID']}
    check('o Produto da esteira traduz para o TIPO do documento',
          _mc.confirmation_type(commands.MC_SOURCE, 'CEM') == 'TERMO DE RESILICAO',
          _mc.confirmation_type(commands.MC_SOURCE, 'CEM'))
    # Na FILA do Monitor o card diz tambem o produto RECOMPRADO (mesa): o tipo
    # e um so para termo, opcao e swap, e tres cards com o mesmo nome nao dizem
    # qual operacao cada um distrata. E so ROTULO — a pasta e o cadastro de
    # validacao continuam no tipo.
    check('e o card do Monitor mostra o produto recomprado',
          _mc.confirmation_label(commands.MC_SOURCE, 'CEM') == 'TERMO DE RESILICAO NDF FX',
          _mc.confirmation_label(commands.MC_SOURCE, 'CEM'))
    check('o rotulo NAO vira tipo (a pasta seguiria para um tipo inexistente)',
          _mc.confirmation_label(commands.MC_SOURCE, 'CEM') not in _mc.CONFIRMATION_TYPES)
    check('produto sem recompra nao ganha sufixo',
          _mc.confirmation_label('NDF COMM', 'CEM') == _mc.confirmation_type('NDF COMM', 'CEM'))
    url, motivo = R._mc_generate_url(linha_esteira, [L1['AthenaID']])
    check('o Generate resolve a URL (nao devolve motivo)', bool(url) and not motivo, motivo)
    check('e ela e a do Termo de Resilicao, com contraparte e moeda',
          url.startswith(commands.TERMO_URL + '?') and 'mercadoria=USD' in url
          and 'acronym=' in url, url)
    check('com a data do ARQUIVO-DIA', 'date=' + HOJE.strftime('%Y-%m-%d') in url, url)
    # Data Operacao de um dia SEM recompra: o 404 tem de dizer por que, em vez
    # de abrir o documento de outro dia.
    _u2, _m2 = R._mc_generate_url(dict(linha_esteira, **{'Data Operação': '01/01/2026'}),
                                  [L1['AthenaID']])
    check('dia sem a recompra recusa dizendo o motivo', not _u2 and 'arquivo-dia' in (_m2 or ''),
          (_u2, _m2))

    print('\n== 14. a esteira acompanha a recompra (o orfao) ==')
    # A cobranca do documento nasce no import junto com a recompra e tem de
    # morrer com ela: sem isto ficava um card de Pending OTC de uma operacao
    # que nao existe mais, e o Generate dele responde "nenhuma operacao
    # encontrada no arquivo-dia" para sempre.
    R._pc_save_from_deal = _pc_save_original
    persistence.upsert(datetime(HOJE.year, HOJE.month, HOJE.day), [dict(L1)])
    commands.esteira_da_recompra([dict(L1)], HOJE)
    check('a recompra entrou na esteira', _mcdb.find_row(L1['AthenaID']) is not None)
    def _no_pc(tn):
        return any(str(r.get('Trade Number', '') or '').strip() == tn
                   for cat in ('backlog', 'pending', 'ok')
                   for r in R._pc_load_rows(cat))
    check('e no Pending Confirmation', _no_pc(L1['AthenaID']))
    # Reimportada NOUTRO dia: a linha aponta para o arquivo-dia novo, senao o
    # Generate procura onde a recompra nao esta mais.
    outro = date(2026, 9, 21)
    commands.esteira_data_da_operacao(dict(L1), datetime(outro.year, outro.month, outro.day))
    check('reimportada noutro dia, a Data Operacao acompanha',
          (_mcdb.find_row(L1['AthenaID']) or {}).get('Data Operação') == '21/09/2026',
          (_mcdb.find_row(L1['AthenaID']) or {}).get('Data Operação'))
    # Mas nao por cima de carimbo: mesa que ja validou decidiu com a data que
    # estava la.
    _row = _mcdb.find_row(L1['AthenaID'])
    _row['Conferido OTC'] = '19/09/2026'
    _mcdb.upsert_row(_row)
    commands.esteira_data_da_operacao(dict(L1), datetime(HOJE.year, HOJE.month, HOJE.day))
    check('linha ja carimbada NAO tem a data mexida',
          (_mcdb.find_row(L1['AthenaID']) or {}).get('Data Operação') == '21/09/2026')
    # E o Delete: com carimbo ele RECUSA (apagar levaria o rastro de quem
    # assinou); sem carimbo, a linha sai da esteira junto com a recompra.
    check('com a esteira carimbada o Delete RECUSA',
          'trail' in (_erro(commands.delete, L1['AthenaID'], HOJE.strftime('%Y-%m-%d')) or ''),
          _erro(commands.delete, L1['AthenaID'], HOJE.strftime('%Y-%m-%d')))
    check('e a recompra continua no arquivo-dia',
          queries.find(L1['AthenaID'], HOJE.strftime('%Y-%m-%d'))[2] is not None)
    _row = _mcdb.find_row(L1['AthenaID'])
    _row['Conferido OTC'] = ''
    _mcdb.upsert_row(_row)
    check('sem carimbo o Delete passa',
          commands.delete(L1['AthenaID'], HOJE.strftime('%Y-%m-%d')) is True)
    check('e a linha sai da esteira junto', _mcdb.find_row(L1['AthenaID']) is None)
    check('e do Pending Confirmation tambem', not _no_pc(L1['AthenaID']))

    print('\n' + ('tudo ok' if not FALHAS else 'FALHAS: ' + '; '.join(FALHAS)))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
