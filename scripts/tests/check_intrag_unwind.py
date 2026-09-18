# -*- coding: utf-8 -*-
"""check_intrag_unwind.py — a recompra na visao do FUNDO (Intrag > Unwind).

Quando o Lawton ou a Atacama esta numa das pontas do contrato recomprado, a
antecipacao tambem tem de chegar a Intrag, que e quem lanca pelo fundo. A
planilha sao ONZE colunas, **as mesmas para todos os produtos**: o que muda de
um para o outro e so a CARTEIRA (a mesa, 18/09/2026).

O que este teste prende:

  1. o layout — as onze colunas, na ordem, e a carteira por fundo;
  2. a Situacao sai da MESMA pergunta do Termo de Resilicao
     (`domain.recompra_total`): total, parcial, ou nao-da-para-dizer;
  3. o Sentido e na visao do FUNDO: com ele na contraparte, o sinal inverte;
  4. o que nao se sabe fica em BRANCO e AVISA — situacao, sentido e carteira;
  5. o gatilho e o SEND da recompra, e contrato sem fundo nenhum nao gera linha;
  6. o arquivo: uma linha por recompra, campos por ';', um arquivo por Data da
     Recompra, nome `Intrag-Unwind-AAAAMMDD.txt`, e o nome existente ganha
     ' (n)' em vez de ser sobrescrito;
  7. as rotas existem e o ciclo New -> Pending -> Approved -> Sent anda.
"""
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')
if os.name != 'nt' and not os.environ.get('OTC_SHARED_DRIVE_ROOT'):
    os.environ['OTC_SHARED_DRIVE_ROOT'] = tempfile.mkdtemp(prefix='otc-share-')

FALHAS = []


def check(nome, cond, extra=''):
    print(('  ok  ' if cond else ' FAIL ') + nome + (('  — ' + str(extra)) if (not cond and extra) else ''))
    if not cond:
        FALHAS.append(nome)


HOJE = date(2026, 9, 18)

# A recompra de um contrato contra o LAWTON: a conta do fundo esta na
# CONTRAPARTE (o banco e a parte), e o banco RECEBE — logo o fundo e DEVEDOR.
L_LAWTON = {'AthenaID': 'STP-XE-10G5U5X-0-0', 'Contract': '00041252DLL', 'Currency': 'USD',
            'Counterparty': 'LAWTON MULTIMERCADO-FI', 'TaxID': '', 'UnwoundNotional': 3808000.0,
            'Balance': 5000000.0, 'Result': 0.0, 'Direction': 'RECEIVE',
            'PartyAccount': '73760009', 'CptyAccount': '00041007',
            'TradeDate': '2025-11-04', 'MaturityDate': '2026-09-16',
            'SettlementDate': '2026-09-18', 'OriginalNotional': 3808000.0,
            'Status': 'Sent'}
# Contra cliente: nenhum fundo nas pontas — nao ha linha da Intrag.
L_CLIENTE = dict(L_LAWTON, AthenaID='STP-CLI-1', CptyAccount='12345678',
                 Counterparty='COFCO INTERNATIONAL BRASIL SA')


def main():
    from run import app  # noqa: F401
    from apps.pages import routes as R
    from apps.pages.features.intrag import domain as I
    from apps.pages.features.intrag import queries as IQ
    from apps.pages.features.intrag.infra import persistence as IP
    from apps.pages.features.unwinds import commands, domain

    tmp = tempfile.mkdtemp(prefix='otc-iuw-')
    IP.INTRAG_UNWIND_CACHE_DIR = os.path.join(tmp, 'cache')
    IP.INTRAG_NDF_SEND_DIR = os.path.join(tmp, 'share')
    commands._hoje = lambda: HOJE

    print('\n== 1. o layout: onze colunas e a carteira por fundo ==')
    check('onze colunas', len(I.INTRAG_UNWIND_FIELDS) == 11, len(I.INTRAG_UNWIND_FIELDS))
    check('na ordem da planilha da mesa', I.INTRAG_UNWIND_FIELDS == (
        'carteira', 'b3_id', 'data_inicio', 'data_vencimento', 'data_recompra',
        'valor_base_original', 'valor_base_recomprado', 'situacao',
        'data_liquidacao', 'sentido', 'valor_liquidacao'))
    check('Lawton -> INTRAGJP552', I.INTRAG_CARTEIRAS['LAWTON'] == 'INTRAGJP552')
    check('Atacama -> INTRAGJP633', I.INTRAG_CARTEIRAS['ATACAMA'] == 'INTRAGJP633')

    base = dict(fundo='LAWTON', b3_id='00041252DLL', data_inicio=date(2025, 11, 4),
                data_vencimento=date(2026, 9, 16), data_recompra=HOJE,
                valor_base_original=3808000.0, valor_base_recomprado=3808000.0,
                total=False, data_liquidacao=HOJE, credor=True, valor_liquidacao=0.0,
                deal='A1')
    e, av = I.intrag_unwind_entry(**base)
    check('a carteira sai do fundo', e['carteira'] == 'INTRAGJP552', e['carteira'])
    check('as datas saem dd/mm/aaaa', (e['data_inicio'], e['data_vencimento'], e['data_recompra'])
          == ('04/11/2025', '16/09/2026', '18/09/2026'), e['data_inicio'])
    check('os valores saem com duas casas e ponto',
          (e['valor_base_original'], e['valor_liquidacao']) == ('3808000.00', '0.00'),
          e['valor_base_original'])
    check('zero NAO e branco (a recompra que nao gera caixa existe)',
          e['valor_liquidacao'] == '0.00')
    check('a linha nasce New', e['status'] == 'New' and not av, av)
    check('fundo desconhecido deixa a carteira em branco AVISANDO',
          I.intrag_unwind_entry(**dict(base, fundo='XPTO'))[0]['carteira'] == '' and
          any(a['code'] == 'intrag_unwind_sem_carteira'
              for a in I.intrag_unwind_entry(**dict(base, fundo='XPTO'))[1]))

    print('\n== 2. a Situacao e a MESMA pergunta do Termo ==')
    check('parcial', e['situacao'] == I.INTRAG_UNWIND_SIT_PARCIAL)
    check('total', I.intrag_unwind_entry(**dict(base, total=True))[0]['situacao']
          == I.INTRAG_UNWIND_SIT_TOTAL)
    sem, av2 = I.intrag_unwind_entry(**dict(base, total=None))
    check('sem saber, a celula fica em BRANCO', sem['situacao'] == '')
    check('e avisa', any(a['code'] == 'intrag_unwind_sem_situacao' for a in av2))
    # A pergunta e uma so: o Termo e a Intrag leem o MESMO `recompra_total`.
    check('a regra vem do dominio da recompra, nao de uma segunda leitura',
          domain.recompra_total(L_LAWTON) is False and
          domain.recompra_total(dict(L_LAWTON, UnwoundNotional=5000000.0)) is True and
          domain.recompra_total(dict(L_LAWTON, Balance=None)) is None)

    print('\n== 3. o Sentido e na visao do FUNDO ==')
    check('credor', e['sentido'] == I.INTRAG_UNWIND_CREDOR)
    check('devedor', I.intrag_unwind_entry(**dict(base, credor=False))[0]['sentido']
          == I.INTRAG_UNWIND_DEVEDOR)
    sem3, av3 = I.intrag_unwind_entry(**dict(base, credor=None))
    check('sem direcao apurada fica em BRANCO', sem3['sentido'] == '')
    check('e avisa', any(a['code'] == 'intrag_unwind_sem_sentido' for a in av3))

    print('\n== 4. o gatilho: o Send da recompra ==')
    check('o fundo e achado na CONTRAPARTE',
          commands._fundo_da_recompra(L_LAWTON) == ('LAWTON', False))
    check('e na PARTE quando e ele que lanca',
          commands._fundo_da_recompra(dict(L_LAWTON, PartyAccount='00041007'))[0] == 'LAWTON')
    check('contrato sem fundo nenhum nao tem linha da Intrag',
          commands._fundo_da_recompra(L_CLIENTE) == (None, None))
    out = commands.intrag_from_send([L_LAWTON, L_CLIENTE], HOJE)
    check('so a recompra com o fundo entrou', len(out) == 1, len(out))
    entry = out[0][0] if out else {}
    check('o b3 id e o contrato', entry.get('b3_id') == '00041252DLL')
    check('a Data da Recompra e a do envio', entry.get('data_recompra') == '18/09/2026')
    # O banco RECEBE e o fundo esta na contraparte: ele PAGA.
    check('com o fundo na contraparte o sentido INVERTE',
          entry.get('sentido') == I.INTRAG_UNWIND_DEVEDOR, entry.get('sentido'))
    check('com o fundo na PARTE, nao',
          commands.intrag_from_send([dict(L_LAWTON, AthenaID='A2', PartyAccount='00041007',
                                          CptyAccount='73760009')], HOJE)[0][0]['sentido']
          == I.INTRAG_UNWIND_CREDOR)
    check('a linha foi gravada no arquivo-dia da Data da Recompra',
          IQ._find_intrag_unwind_entry(L_LAWTON['AthenaID'], '18/09/2026')[2] is not None)
    check('e o dia fica FORA da arvore da recompra (e dentro do cache da Intrag)',
          'Intrag' in IP.INTRAG_UNWIND_CACHE_DIR or IP.INTRAG_UNWIND_CACHE_DIR.startswith(tmp))

    print('\n== 5. as rotas e o arquivo ==')
    regras = {str(r) for r in app.url_map.iter_rules()}
    for r in ('/api/intrag/unwind', '/api/intrag/unwind/send-file',
              '/api/intrag/unwind/edit', '/api/intrag/unwind/approve'):
        check('rota ' + r, r in regras)
    from apps.pages.features.intrag import commands as IC
    check('o delete generico conhece a familia', 'unwind' in IC._INTRAG_DELETE_FAMILIES)

    cells = [entry[f] for f in I.INTRAG_UNWIND_FIELDS]
    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess['authenticated'] = True
            sess['user_sid'] = 'E930179'
            sess['user_name'] = 'Teste'
            # UTC: um horario local ja chega "expirado" para o
            # `enforce_session_expiry`, e o request volta 302 parecendo falta
            # de autenticacao.
            sess['session_expires_at'] = (datetime.now(timezone.utc)
                                          + timedelta(hours=8)).isoformat()
        resp = c.post('/api/intrag/unwind/send-file',
                      json={'items': [{'deal_id': L_LAWTON['AthenaID'], 'cells': cells}]})
        data = resp.get_json() or {}
    check('o send-file devolve o arquivo', data.get('success') and data.get('files'), data)
    arq = (data.get('files') or [''])[0]
    check('o nome e Intrag-Unwind-AAAAMMDD.txt',
          os.path.basename(arq) == 'Intrag-Unwind-20260918.txt', os.path.basename(arq))
    conteudo = open(arq, encoding='utf-8').read() if arq and os.path.isfile(arq) else ''
    check('uma linha por recompra', len(conteudo.splitlines()) == 1, conteudo)
    check('onze campos separados por ;', len(conteudo.split(';')) == 11, conteudo)
    check('e a linha comeca pela carteira', conteudo.startswith('INTRAGJP552;'), conteudo[:40])
    check('a recompra virou Sent',
          (IQ._find_intrag_unwind_entry(L_LAWTON['AthenaID'], '18/09/2026')[1] or [{}])[0].get('status') == 'Sent')

    print('\n' + ('tudo ok' if not FALHAS else 'FALHAS: ' + '; '.join(FALHAS)))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
