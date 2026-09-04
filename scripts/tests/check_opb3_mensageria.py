"""Operations B3 > Mensageria: o assunto, o agrupamento e o "Favor considerar".

O e-mail de mensageria pede que a contraparte ACATE um valor. Tudo que este
teste prende erra em silencio — o e-mail continua saindo, bonito, com o numero
errado ou partido em dois:

  1. o assunto do SWAP. Vencimento (diferencial de amortizacao e de juros) sai
     como "Vencimento Swap"; premio continua "Premio Swap". Nomear o assunto
     pelo Tipo Operacao da primeira linha descreveria metade do e-mail.

  2. o AGRUPAMENTO. Amortizacao e juros contra a mesma contraparte sao o mesmo
     pagamento partido em dois eventos pela B3 e saem num e-mail so, com o total
     somado. Dois e-mails com o mesmo assunto e valores parciais e o defeito.

  3. o assunto e o agrupamento lendo a MESMA funcao. Se um lado disser
     "vencimento" e o outro continuar quebrando por Tipo Operacao, volta-se ao
     item 2 sem que nada acuse.

  4. o "Favor considerar". Aparece quando o lado interno diverge do lado B3 em
     >= R$ 0,01 — e agora existe lado interno para o VENCIMENTO DE SWAP e para o
     TERMO DE COMMODITIES, que ficavam sempre sem ele (indistinguivel de
     "bateu"). O valor interno sai do MESMO Trade Level que a tela mostra.

  5. o batimento comparando o total do grupo. O mapa interno traz o total do
     CONTRATO; se o e-mail nao juntasse amortizacao e juros antes de comparar,
     cada metade acusaria uma divergencia que e so a outra metade.

Nao encosta em dado real: as fontes vao para um tempfile, os destinatarios e o
RefData sao stubs e as raizes do modulo voltam no finally.
"""
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))


def _fontes_com_rotas_(base):
    """routes.py + a arvore de features — as rotas moram nos entrypoints desde
    a verticalizacao, e um scan so do routes viraria assercao vazia."""
    import io as _io, os as _os
    partes = [_io.open(_os.path.join(base, 'apps', 'pages', 'routes.py'), encoding='utf-8').read()]
    # ... e a arvore da platform/ — a fase §316 move os motores compartilhados
    # para la, e um scan que parasse nas features perderia o que acabou de sair
    # do routes (foi a familia de liquidacao a primeira).
    for raiz in (_os.path.join(base, 'apps', 'pages', 'features'),
                 _os.path.join(base, 'apps', 'pages', 'platform')):
        for r, dirs, arqs in _os.walk(raiz):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for a in sorted(arqs):
                if a.endswith('.py'):
                    partes.append(_io.open(_os.path.join(r, a), encoding='utf-8').read())
    return '\n'.join(partes)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                        # noqa: E402
from apps.pages import otc_emails                         # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
print('== 1. quem e vencimento de swap ==')
V = otc_emails.opb3_msg_is_swap_venc
check('dif. amortizacao e vencimento', V('SWAP', 'PAGAMENTO DE DIF. AMORTIZACAO'), True)
check('dif. de juros e vencimento', V('SWAP', 'PAGAMENTO DE DIF. DE JUROS'), True)
check('premio NAO e vencimento', V('SWAP', 'PAGAMENTO DE PREMIO'), False)
# O acento e a caixa do arquivo da B3 variam; a normalizacao tem de absorver.
check('premio com acento tambem nao', V('Swap', 'Pagamento de Prêmio'), False)
check('TER nao e swap', V('TER', 'RESGATE'), False)
check('OPC nao e swap', V('OPC', 'EXERCICIO OPCAO'), False)
# Um diferencial novo da B3 entra sozinho — a regra e "swap e nao premio", nao
# uma lista de dois eventos para manter.
check('diferencial novo entra sem manutencao', V('SWAP', 'PAGAMENTO DE DIF. DE ALGO'), True)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 2. o assunto ==')


def subj(tipo_titulo, tipo_op, cpty='SUZANO SA'):
    return otc_emails.build_opb3_mensageria_email({
        'tipo': 'CEM', 'tipo_titulo': tipo_titulo, 'tipo_operacao': tipo_op,
        'cpty': cpty, 'ref_date': '05/08/2026', 'rows': [], 'total': 100.0,
        'internal': None, 'to': 'a@b', 'cc': '',
    })['subject']


check('vencimento de swap', subj('SWAP', 'PAGAMENTO DE DIF. DE JUROS'),
      'Vencimento Swap - Liquidação Banco x SUZANO SA - 05/08/2026')
check('amortizacao tem o MESMO assunto', subj('SWAP', 'PAGAMENTO DE DIF. AMORTIZACAO'),
      'Vencimento Swap - Liquidação Banco x SUZANO SA - 05/08/2026')
# O resto do assunto e o padrao de sempre — so a base mudou.
check('premio de swap intacto', subj('SWAP', 'PAGAMENTO DE PREMIO'),
      'Prêmio Swap - Liquidação Banco x SUZANO SA - 05/08/2026')
check('resgate de TER intacto', subj('TER', 'RESGATE'),
      'Vencimento de Termo - Liquidação Banco x SUZANO SA - 05/08/2026')
check('exercicio de opcao intacto', subj('OPC', 'EXERCICIO OPCAO'),
      'Exercício Opção - Liquidação Banco x SUZANO SA - 05/08/2026')

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 3. o "Favor considerar" ==')


def favor(total, internal):
    html = otc_emails.build_opb3_mensageria_email({
        'tipo': 'CEM', 'tipo_titulo': 'SWAP', 'tipo_operacao': 'PAGAMENTO DE DIF. DE JUROS',
        'cpty': 'SUZANO SA', 'ref_date': '05/08/2026', 'rows': [], 'total': total,
        'internal': internal, 'to': 'a@b', 'cc': '',
    })['html']
    return 'Favor considerar' in html


check('sem lado interno, nao aparece', favor(100.0, None), False)
check('valores iguais, nao aparece', favor(100.0, 100.0), False)
check('1 centavo de diferenca ja aparece', favor(100.0, 100.01), True)
# Abaixo de um centavo e ruido de float, nao divergencia.
check('meio centavo nao aparece', favor(100.0, 100.004), False)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 4. o agrupamento, pelo endpoint de verdade ==')
# Um dia com: A1 chegando por amortizacao E juros contra a mesma contraparte,
# A2 de premio (contraparte igual, e outro e-mail), e C1 de termo de commodity.


def run_day(recs, internal_swap=None, internal_ndfc=None, participants=None, ids=None):
    """Chama /api/operations-b3/mensageria e devolve os `group` de cada draft."""
    from apps import create_app
    from apps.config import DebugConfig
    seen = []
    real_build = otc_emails.build_opb3_mensageria_email
    real = (R._opb3_msg_load_recipients, R._opb3_refdata_by_account,
            R._opb3_participant_name_by_account,
            R._opb3_tipo_maps, R._opb3_internal_ter_map, R._opb3_internal_swapprem_map,
            R._opb3_internal_swap_map, R._opb3_internal_ndfc_map, R.OTM_JSON_ROOT)

    def spy(group):
        out = real_build(group)
        seen.append(dict(group, _subject=out['subject'], _html=out['html']))
        return out

    otc_emails.build_opb3_mensageria_email = spy
    R._opb3_msg_load_recipients = lambda: {'cem': {'to': 'cem@x', 'cc': ''},
                                           'equities': {'to': 'eq@x', 'cc': ''}}
    R._opb3_refdata_by_account = lambda: {}
    R._opb3_participant_name_by_account = lambda: dict(participants or {})
    R._opb3_tipo_maps = lambda ref: {}
    R._opb3_internal_ter_map = lambda ref: {}
    R._opb3_internal_swapprem_map = lambda ref: {}
    R._opb3_internal_swap_map = lambda ref: dict(internal_swap or {})
    R._opb3_internal_ndfc_map = lambda ref: dict(internal_ndfc or {})
    tmp = tempfile.mkdtemp(prefix='opb3-msg-')
    try:
        R.OTM_JSON_ROOT = tmp
        write_json(os.path.join(tmp, '2026', '08', '05', 'operations-b3_20260805.json'), recs)
        app = create_app(DebugConfig)
        c = app.test_client()
        with c.session_transaction() as s:
            s['authenticated'] = True
            s['user_sid'] = 'T000000'
            s['user_name'] = 'T'
            s['user_email'] = 't@x'
            s['session_expires_at'] = (datetime.now(tz=timezone.utc) + timedelta(hours=8)).isoformat()
        body = {'date': '2026-08-05'}
        if ids is not None:
            body['ids'] = ids
        r = c.post('/api/operations-b3/mensageria', json=body)
        return r, seen
    finally:
        otc_emails.build_opb3_mensageria_email = real_build
        (R._opb3_msg_load_recipients, R._opb3_refdata_by_account,
         R._opb3_participant_name_by_account,
         R._opb3_tipo_maps, R._opb3_internal_ter_map, R._opb3_internal_swapprem_map,
         R._opb3_internal_swap_map, R._opb3_internal_ndfc_map, R.OTM_JSON_ROOT) = real
        shutil.rmtree(tmp, ignore_errors=True)


def rec(titulo, tipo_op, valor, tit='SWAP', cp='11111.11-1', cpn='SUZANO SA'):
    return {'Conta': '73760.00-9', 'Tipo Operação': tipo_op, 'C/V': 'CREDOR',
            'Título': titulo, 'Tipo Título': tit, 'Valor': valor,
            'Modalidade Liquidação': 'Bilateral', 'Status': 'PENDENTE',
            'Contraparte (Nome Simpl.)': cpn, 'Conta Contraparte': cp,
            'Data Liquidação': '05/08/2026'}


resp, drafts = run_day([
    rec('A1', 'PAGAMENTO DE DIF. AMORTIZACAO', '100,00'),
    rec('A1', 'PAGAMENTO DE DIF. DE JUROS', '50,00'),
    rec('A2', 'PAGAMENTO DE PREMIO', '7,00'),
    rec('C1', 'RESGATE', '900,00', tit='TER'),
], internal_swap={'A1': 150.0}, internal_ndfc={'C1': 900.0})

check('o endpoint respondeu', resp.status_code, 200)
by_subj = {d['_subject'].split(' - ')[0]: d for d in drafts}
check('tres e-mails: vencimento, premio e termo', sorted(by_subj),
      ['Prêmio Swap', 'Vencimento Swap', 'Vencimento de Termo'])

venc = by_subj.get('Vencimento Swap', {})
check('amortizacao e juros num e-mail SO', len(venc.get('rows') or []), 2)
check('e o total e a soma dos dois eventos', venc.get('total'), 150.0)
# O detalhe nao se perde ao juntar: cada linha da tabela mantem o seu evento.
evs = sorted(r[2] for r in (venc.get('rows') or []))
check('a tabela mantem os dois Tipos Operacao', evs,
      ['PAGAMENTO DE DIF. AMORTIZACAO', 'PAGAMENTO DE DIF. DE JUROS'])
# 150 interno x 150 na B3 -> bateu. E o ponto do item 5: comparado por metade
# (100 ou 50 contra 150) teria acusado divergencia nas duas.
check('vencimento de swap TEM lado interno', venc.get('internal'), 150.0)
check('e sem divergencia nao pede nada', 'Favor considerar' in venc.get('_html', ''), False)

termo = by_subj.get('Vencimento de Termo', {})
check('o termo de commodities TEM lado interno', termo.get('internal'), 900.0)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 5. a divergencia chegando ao e-mail ==')
resp, drafts = run_day([
    rec('A1', 'PAGAMENTO DE DIF. AMORTIZACAO', '100,00'),
    rec('A1', 'PAGAMENTO DE DIF. DE JUROS', '50,00'),
    rec('C1', 'RESGATE', '900,00', tit='TER'),
], internal_swap={'A1': 149.0}, internal_ndfc={'C1': 880.0})
by_subj = {d['_subject'].split(' - ')[0]: d for d in drafts}
check('swap: divergencia pede "Favor considerar"',
      'Favor considerar' in by_subj['Vencimento Swap']['_html'], True)
check('termo: divergencia pede "Favor considerar"',
      'Favor considerar' in by_subj['Vencimento de Termo']['_html'], True)
# Sem contrato no mapa interno nao ha o que comparar — e o e-mail sai SEM a
# frase, que e melhor que sair com um valor inventado.
resp, drafts = run_day([rec('A1', 'PAGAMENTO DE DIF. DE JUROS', '50,00')], internal_swap={})
check('sem fonte interna, nada de "Favor considerar"',
      'Favor considerar' in drafts[0]['_html'], False)
check('e o internal fica None, nao zero', drafts[0].get('internal'), None)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 6. uma definicao so para as duas decisoes ==')
src = _fontes_com_rotas_(ROOT)
check('o agrupamento chama a funcao do otc_emails',
      'otc_emails.opb3_msg_is_swap_venc' in src, True)
check('e nao reimplementa o teste de premio no agrupamento',
      "== 'pagamento de premio'" in src.split('def api_opb3_mensageria')[1].split('gkey')[0], False)
esrc = io.open(os.path.join(ROOT, 'apps', 'pages', 'otc_emails.py'), encoding='utf-8').read()
check('a funcao existe uma vez so', esrc.count('def opb3_msg_is_swap_venc'), 1)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 7. os mapas internos leem o Trade Level ==')
# As secoes 4 e 5 stubam os dois mapas — sozinhas, provam o e-mail, nao a fonte.
# Aqui e o contrario: a fonte. E preciso furar o `except` das duas funcoes, que
# devolve {} em falha e faria um erro de wiring passar por "dia sem dados".
check('id_b3 -> _settle_n', R._opb3_internal_trade_map([
    {'id_b3': 'a1', '_settle_n': 100.0},
    {'id_b3': 'A1', '_settle_n': 50.0},        # mesmo contrato, duas linhas
    {'id_b3': 'B2', '_settle_n': None},        # sem valor interno nao entra
    {'id_b3': '', '_settle_n': 9.0},           # sem B3 ID nao entra
]), {'A1': 150.0})


def spy_map(fn_name, map_fn):
    """Chama o mapa com um datetime e devolve (argumento recebido, resultado)."""
    seen = {}
    real = getattr(R, fn_name)

    def spy(arg):
        seen['arg'] = arg
        return [{'id_b3': 'X1', '_settle_n': 42.0}]

    setattr(R, fn_name, spy)
    try:
        out = map_fn(datetime(2026, 8, 5))
        return seen.get('arg'), out
    finally:
        setattr(R, fn_name, real)


arg, got = spy_map('_ops_swap_trade_rows', R._opb3_internal_swap_map)
check('swap: veio do Trade Level de swap', got, {'X1': 42.0})
# `_ops_swap_trade_rows` faz `settle_ref - op_dt` com um date; passar o datetime
# cru levanta TypeError, que o except transformaria num {} silencioso.
check('swap: recebe date, nao datetime', type(arg), datetime(2026, 8, 5).date().__class__)

arg, got = spy_map('_ops_ndfc_trade_rows', R._opb3_internal_ndfc_map)
check('commodities: veio do Trade Level de NDF commodities', got, {'X1': 42.0})
check('commodities: recebe date, nao datetime', type(arg), datetime(2026, 8, 5).date().__class__)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 8. o nome da contraparte: RefData -> B3 Participants -> apelido ==')
# A conta que nao tem linha no Reference Data cai no cadastro de participantes
# da B3 (/mapping > B3 Participants, RAZAO SOCIAL pela CONTA, comparada por
# DIGITOS — os dois lados guardam pontuacao diferente). So sem os dois o
# e-mail sai com o apelido de 20 caracteres do arquivo.
resp, drafts = run_day([rec('A9', 'PAGAMENTO DE PREMIO', '7,00',
                            cp='22222.22-2', cpn='APELIDOB3')],
                       participants={'22222222': 'BANCO EXEMPLO LEGAL S.A.'})
check('sem RefData, o nome vem do cadastro de participantes',
      drafts[0].get('cpty'), 'BANCO EXEMPLO LEGAL S.A.')
resp, drafts = run_day([rec('A9', 'PAGAMENTO DE PREMIO', '7,00',
                            cp='22222.22-2', cpn='APELIDOB3')])
check('sem RefData E sem participante, fica o apelido do arquivo',
      drafts[0].get('cpty'), 'APELIDOB3')
# E o mapa REAL le a RAZAO SOCIAL pela CONTA em digitos — a assinatura do
# cadastro (`cgd-b3-participante`) que a recon de CGD tambem consome.
_real_rows = R._mapping_rows
R._mapping_rows = lambda k: ([{'RAZAO SOCIAL': 'FULANO S.A.', 'NOME CONTRAPARTE': 'FULANO',
                               'CNPJ': '1', 'CONTA': '33333.33-3'}]
                             if k == 'cgd-b3-participante' else _real_rows(k))
try:
    check('o mapa real: conta em digitos -> razao social',
          R._opb3_participant_name_by_account(), {'33333333': 'FULANO S.A.'})
finally:
    R._mapping_rows = _real_rows

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 9. o agrupamento e por NOME resolvido, nao por conta ==')
# A mesma contraparte pode liquidar por DUAS contas no mesmo dia (o COE de
# 04/09/2026): um e-mail por conta cobra o mesmo pagamento em dois avisos. As
# duas contas resolvem para a mesma Razao Social no cadastro de participantes
# -> UM e-mail, com as duas linhas e o total somado. Contraparte de nome
# DIFERENTE continua num e-mail proprio.
resp, drafts = run_day([
    rec('K1', 'RESGATE', '100,00', tit='COE', cp='44444.44-4', cpn='APELIDO1'),
    rec('K2', 'RESGATE', '200,00', tit='COE', cp='55555.55-5', cpn='APELIDO2'),
    rec('K3', 'RESGATE', '900,00', tit='COE', cp='66666.66-6', cpn='OUTRA'),
], participants={'44444444': 'MESMA CONTRAPARTE S.A.',
                 '55555555': 'MESMA CONTRAPARTE S.A.',
                 '66666666': 'OUTRA CONTRAPARTE LTDA'})
check('o endpoint respondeu', resp.status_code, 200)
check('duas contas, mesmo nome -> DOIS drafts no dia (um por contraparte)',
      len(drafts), 2)
mesma = next((d for d in drafts if d.get('cpty') == 'MESMA CONTRAPARTE S.A.'), {})
check('o e-mail unido tem as DUAS linhas', len(mesma.get('rows') or []), 2)
check('e o total soma as duas contas', mesma.get('total'), 300.0)
contas = sorted(r[11] for r in (mesma.get('rows') or []))
check('cada linha mantem a SUA conta na tabela', contas,
      ['44444.44-4', '55555.55-5'])
outra = next((d for d in drafts if d.get('cpty') == 'OUTRA CONTRAPARTE LTDA'), {})
check('a outra contraparte fica no e-mail dela', len(outra.get('rows') or []), 1)

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 10. selecao orfa = pagina desatualizada, e o erro DIZ isso ==')
# O `_ob_id` e reatribuido quando a reimportacao nao consegue carregar o meta
# adiante (linha sem Num Ctrl Operacao): a aba aberta manda ids que nao casam
# com NADA, as Generated marcadas ficam de fora, e o "No pending" generico lia
# como botao quebrado. Ids sem NENHUM correspondente no dia -> 409 nomeando o
# remedio (recarregar). Id que casa continua destravando a regeracao.
gen = dict(rec('G1', 'RESGATE', '10,00', tit='COE'),
           _ob_id='K-GEN', _ob_status='Generated', _ob_maker='', _ob_checker='')
resp, drafts = run_day([gen], ids=['id-que-nao-existe'])
check('ids orfaos -> 409', resp.status_code, 409)
check('e o erro manda recarregar', 'Refresh the page' in (resp.get_json() or {}).get('error', ''), True)
check('nenhum draft foi gerado', len(drafts), 0)
resp, drafts = run_day([gen], ids=['K-GEN'])
check('id valido -> regenera a Generated marcada', resp.status_code, 200)
check('com o draft dela', len(drafts), 1)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
