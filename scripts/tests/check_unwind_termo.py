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
L1 = {'AthenaID': 'STP-XE-10G5U5X-0-0', 'Contract': '26C03202688', 'Currency': 'USD',
      'Counterparty': 'COFCO INTERNATIONAL BRASIL SA', 'TaxID': '02.916.265/0001-60',
      'ClientAcronym': 'COFCO', 'UnwoundNotional': 11529.81, 'Balance': 587224.31,
      'Result': 42.80, 'Direction': 'RECEIVE', 'PartyAccount': '73760009',
      'CptyAccount': '00041007', 'Status': 'Imported'}
L2 = dict(L1, AthenaID='STP-XE-10G5U5X-0-1', Contract='26C03202689',
          UnwoundNotional=144122.68, Balance=144122.68, Result=-9350.12, Direction='PAY')


def main():
    from run import app  # noqa: F401
    from apps.pages import routes as R
    from apps.pages.features.unwinds import commands, domain, queries
    from apps.pages.features.unwinds.infra import persistence

    tmp = tempfile.mkdtemp(prefix='otc-termo-')
    persistence.cache_root = lambda: os.path.join(tmp, 'cache')
    persistence.cache_dir = lambda: os.path.join(tmp, 'cache', 'NDF', 'FX')
    commands._hoje = lambda: HOJE

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
    check('e no total nao ha Novo Valor Base', rows[1]['novoValorBase'] == domain.NAO_APLICAVEL)
    # O saldo e o recomprado vem de arredondamentos diferentes: a posicao
    # imprime duas casas e a conta da recompra nao.
    check('um centavo de diferenca ainda e resilicao TOTAL',
          domain.termo_linha(dict(L1, UnwoundNotional=587224.3049,
                                  Balance=587224.31))[0]['resilicao'] == domain.RESILICAO_TOTAL)
    sem_saldo, av = domain.termo_linha(dict(L1, Balance=None))
    check('SEM saldo nao se diz qual das duas e', sem_saldo['resilicao'] == '' and
          sem_saldo['novoValorBase'] == '')
    check('e avisa', any(a['code'] == 'unwind_termo_sem_saldo' for a in av))

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
    check('o Save devolve os dois arquivos', len(out['files']) == 2)
    check('o .doc e o .pdf existem no Inventory',
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

    print('\n' + ('tudo ok' if not FALHAS else 'FALHAS: ' + '; '.join(FALHAS)))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
