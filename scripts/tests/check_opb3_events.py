"""Operations B3: o que entra numa liquidacao, e por qual das duas visoes.

Duas regras que decidem NUMERO, e que erram em silencio.

1. **Quais linhas contam** (cadastro `opb3-events`). Uma operacao CANCELADA:
   COMANDADA continua no arquivo da B3 com o valor cheio. Somada, ela vira um
   caixa que nao vai acontecer — e nao ha erro nenhum: a tela mostra um total
   plausivel que ninguem consegue explicar linha a linha. O cadastro substituiu
   o `swap-b3-events`, que so sabia dizer quais Tipo Operacao eram swap; agora a
   linha e uma REGRA sobre Tipo Titulo x Tipo Operacao x Status B3.

2. **Qual das duas visoes e a nossa** (direcao do valor). Um negocio JPM x MGT
   chega pelos DOIS arquivos de casa, espelhado: Conta 73760.00-9 / Conta
   Contraparte 04880.00-6 com o valor de uma ponta, e as contas invertidas com o
   sinal trocado. Procurando so pelo Titulo, quem decidia o sinal era a ordem de
   chegada no arquivo — metade dos intragrupo saia com o Settlement B3 invertido
   contra a coluna SETTLEMENT, e a diferenca dava o DOBRO do valor.

Nao encosta em dado real: o cadastro e lido do seed e as linhas sao sinteticas.
"""
import io
import os
import sys

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

from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8', errors='ignore').read()


# O cadastro sai do SEED, nao do arquivo: quem editar a tabela pela tela nao pode
# fazer este teste falhar, e o seed e justamente o que precisa estar certo numa
# instalacao nova.
_real_rows = R._mapping_rows
R._mapping_rows = lambda key: ([dict(r) for r in R._MAPPING_DEFS[key]['seed']]
                               if key == 'opb3-events' else _real_rows(key))


def rec(tit, op, status='PENDENTE DE LIQUIDACAO FINANCEIRA', **extra):
    d = {'Tipo Título': tit, 'Tipo Operação': op, 'Status': status}
    d.update(extra)
    return d


print('== 1. o cadastro existe e reproduz o comportamento antigo ==')
SRC = _fontes_com_rotas_(ROOT)
check("'opb3-events' registrado", "'opb3-events': {" in SRC, True)
check('e na aba do /mapping', "key: 'opb3-events'" in read('apps/templates/pages/mapping.html'), True)
check('o antigo swap-b3-events saiu', "'swap-b3-events': {" in SRC, False)
check('e o arquivo dele tambem',
      os.path.isfile(os.path.join(ROOT, 'apps/static/data/mappings/swap-b3-events.json')), False)
seed = R._MAPPING_DEFS['opb3-events']['seed']
check('sete linhas de seed', len(seed), 7)
check('as tres do swap continuam la',
      sorted(r['TIPO OPERACAO'] for r in seed if r['TIPO TITULO'] == 'SWAP'),
      ['PAGAMENTO DE DIF. AMORTIZACAO', 'PAGAMENTO DE DIF. DE JUROS', 'PAGAMENTO DE PREMIO'])
# TER e OPC ganharam a linha de RESGATE: a selecao do evento de termo estava FIXA
# no `_ndfadv_collect` e virou cadastro, e a opcao nasce com a mesma regra. Sem
# elas, "Tipo Titulo sem Consider nao e filtrado" deixaria TODO evento de termo
# entrar no aviso no dia em que o codigo parou de testar 'resgate'.
check('TER nasce com o RESGATE cadastrado',
      [r['TIPO OPERACAO'] for r in seed if r['TIPO TITULO'] == 'TER'], ['RESGATE'])
check('OPC nasce com RESGATE e o premio',
      sorted(r['TIPO OPERACAO'] for r in seed if r['TIPO TITULO'] == 'OPC'),
      ['PAGAMENTO DE PREMIO', 'RESGATE'])
check('e a regra do cancelamento nasce sem Tipo Titulo (vale para todos)',
      [(r['TIPO TITULO'], r['USE']) for r in seed if r['STATUS B3']],
      [('', 'Disregard')])
# O `upgrade` completa o arquivo JA em disco — sem ele a instancia que tem o
# opb3-events.json de antes ficaria sem regra de TER/OPC.
up = R._MAPPING_DEFS['opb3-events']['upgrade']
antigo = [r for r in seed if r['TIPO TITULO'] in ('SWAP', '')]
check('upgrade acrescenta TER e OPC ao arquivo antigo',
      sorted((r['TIPO TITULO'], r['TIPO OPERACAO']) for r in up(antigo)
             if r['TIPO TITULO'] in ('TER', 'OPC')),
      [('OPC', 'PAGAMENTO DE PREMIO'), ('OPC', 'RESGATE'), ('TER', 'RESGATE')])
check('e NAO sobrescreve quem ja configurou o TER',
      [r['TIPO OPERACAO'] for r in up(antigo + [dict(seed[0], **{
          'TIPO TITULO': 'TER', 'TIPO OPERACAO': 'PAGAMENTO DE EVENTO'})])
       if r['TIPO TITULO'] == 'TER'],
      ['PAGAMENTO DE EVENTO'])

print('\n== 2. lista branca por Tipo Titulo ==')
# SWAP tem Consider proprio -> so o registrado entra.
check('SWAP amortizacao entra', R._opb3_settle_ok(rec('SWAP', 'PAGAMENTO DE DIF. AMORTIZACAO')), True)
check('SWAP juros entra', R._opb3_settle_ok(rec('SWAP', 'PAGAMENTO DE DIF. DE JUROS')), True)
check('SWAP premio entra', R._opb3_settle_ok(rec('SWAP', 'PAGAMENTO DE PREMIO')), True)
check('SWAP resgate NAO entra', R._opb3_settle_ok(rec('SWAP', 'RESGATE')), False)
check('SWAP resgate antecipado NAO entra',
      R._opb3_settle_ok(rec('SWAP', 'RESGATE ANTECIPADO')), False)
# TER e OPC ganharam Consider proprio -> viraram lista branca tambem. Era aqui
# que o `_ndfadv_collect` testava 'resgate' por conta propria; a resposta passou
# a ser uma so, do cadastro, para os tres Settlement Advice de Other Products.
check('TER resgate entra', R._opb3_settle_ok(rec('TER', 'RESGATE')), True)
check('TER pagamento de evento NAO entra (nao cadastrado)',
      R._opb3_settle_ok(rec('TER', 'PAGAMENTO DE EVENTO')), False)
check('OPC resgate entra', R._opb3_settle_ok(rec('OPC', 'RESGATE')), True)
check('OPC premio entra (o aviso o distingue no assunto)',
      R._opb3_settle_ok(rec('OPC', 'PAGAMENTO DE PREMIO')), True)
check('OPC registro NAO entra', R._opb3_settle_ok(rec('OPC', 'REGISTRO')), False)
# COE nao tem Consider nenhum -> nao e filtrado, que e como a tela se comporta.
check('COE qualquer coisa entra', R._opb3_settle_ok(rec('COE', 'QUALQUER EVENTO')), True)

print('\n== 3. Disregard vence, e o coringa vale para todo Tipo Titulo ==')
for tit, op in (('TER', 'RESGATE'), ('SWAP', 'PAGAMENTO DE DIF. DE JUROS'),
                ('OPC', 'PAGAMENTO DE PREMIO'), ('COE', 'RESGATE')):
    check('%s %s cancelada sai' % (tit, op),
          R._opb3_settle_ok(rec(tit, op, 'CANCELADA: COMANDADA')), False)
check('FINALIZADA continua entrando',
      R._opb3_settle_ok(rec('TER', 'RESGATE', 'FINALIZADA')), True)

print('\n== 4. o casamento ignora caixa, acento e PONTUACAO ==')
# A B3 escreve o mesmo status com e sem espaco depois dos dois pontos; comparar
# o texto cru fazia a regra simplesmente nao valer, sem erro nenhum.
for status in ('CANCELADA: COMANDADA', 'CANCELADA:COMANDADA', 'cancelada  comandada',
               'Cancelada : Comandada'):
    check('status %r casa' % status, R._opb3_settle_ok(rec('TER', 'RESGATE', status)), False)
check('AMORTIZACAO com cedilha casa',
      R._opb3_settle_ok(rec('SWAP', 'PAGAMENTO DE DIF. AMORTIZAÇÃO')), True)
check('espaco duplo no meio casa',
      R._opb3_settle_ok(rec('SWAP', 'PAGAMENTO DE  DIF.  DE JUROS')), True)
check('padding nas pontas casa',
      R._opb3_settle_ok(rec('  SWAP  ', '  PAGAMENTO DE PREMIO  ')), True)

print('\n== 5. "nenhum swap entra" continua possivel, mas agora se DIZ ==')
# Antes isso se fazia esvaziando a tabela, o que nao distinguia "nao quero
# nenhum" de "ainda nao cadastrei". Hoje e uma linha explicita.
R._mapping_rows = lambda key: ([{'TIPO TITULO': 'SWAP', 'TIPO OPERACAO': '',
                                 'STATUS B3': '', 'USE': 'Disregard'}]
                               if key == 'opb3-events' else _real_rows(key))
check('linha SWAP/Disregard tira todo swap',
      R._opb3_settle_ok(rec('SWAP', 'PAGAMENTO DE DIF. DE JUROS')), False)
check('e nao encosta no TER', R._opb3_settle_ok(rec('TER', 'RESGATE')), True)
# USE em branco vale como Consider — e o que as linhas do cadastro antigo queriam
# dizer, e a leitura inofensiva das duas.
R._mapping_rows = lambda key: ([{'TIPO TITULO': 'SWAP', 'TIPO OPERACAO': 'RESGATE',
                                 'STATUS B3': '', 'USE': ''}]
                               if key == 'opb3-events' else _real_rows(key))
check('USE em branco e Consider', R._opb3_settle_ok(rec('SWAP', 'RESGATE')), True)
check('   e vira lista branca do SWAP',
      R._opb3_settle_ok(rec('SWAP', 'PAGAMENTO DE PREMIO')), False)
# Cadastro sem linha nenhuma nao filtra nada.
R._mapping_rows = lambda key: ([] if key == 'opb3-events' else _real_rows(key))
check('cadastro vazio nao filtra', R._opb3_settle_ok(rec('SWAP', 'RESGATE')), True)
R._mapping_rows = lambda key: ([dict(r) for r in R._MAPPING_DEFS[key]['seed']]
                               if key == 'opb3-events' else _real_rows(key))

print('\n== 6. a regra e a MESMA em todas as telas de liquidacao ==')
# Nao adianta filtrar numa e nao na outra: o mesmo negocio contaria num lugar e
# sumiria no outro. Aqui se confere que cada consumidor passa pelo cadastro.
for label, marker, needle in (
        ('swap (Trade Level / Advice)', 'def _ops_swap_settling', '_opb3_settle_ok(rec, rules)'),
        ('NDF Summary', 'def _ndfsum_collect', '_opb3_settle_rows(ref)'),
        ('aviso de commodities', 'def _ndfadv_collect', '_opb3_settle_rows(ref)'),
        ('contratos CETIP do Cockpit', 'def _ndfc_opb3_resgates', '_opb3_settle_rows(ref)'),
        ('mensageria', 'def api_opb3_mensageria', '_opb3_settle_ok(rec, ev_rules)')):
    blk = SRC.split(marker, 1)[1].split('\n@blueprint', 1)[0].split('\ndef ', 1)[0]
    check('%s passa pelo cadastro' % label, needle in blk, True)
# A PAGINA Operations B3 continua mostrando o arquivo inteiro: ela e a fonte, e
# esconder a linha cancelada la deixaria o time sem onde ve-la.
blk = SRC.split('def _opb3_collect', 1)[1].split('\ndef ', 1)[0]
check('a pagina Operations B3 NAO filtra', '_opb3_settle_ok' in blk, False)

print('\n== 7. direcao do valor: qual das duas visoes e a nossa ==')
BANCO, MGT = '73760.00-9', '04880.00-6'
CLIENTE = '85398.00-5'
ops = [
    # Intragrupo: o MESMO Titulo pelas duas oticas, com o sinal trocado.
    {'Título': 'X1', 'Tipo Operação': 'RESGATE', 'Conta': BANCO,
     'Conta Contraparte': MGT, 'Valor': '1.000,00'},
    {'Título': 'X1', 'Tipo Operação': 'RESGATE', 'Conta': MGT,
     'Conta Contraparte': BANCO, 'Valor': '-1.000,00'},
    # Cliente externo: uma visao so.
    {'Título': 'X2', 'Tipo Operação': 'RESGATE', 'Conta': BANCO,
     'Conta Contraparte': CLIENTE, 'Valor': '500,00'},
    # Titulo com resgate E outro evento: o resgate vence.
    {'Título': 'X3', 'Tipo Operação': 'PAGAMENTO DE EVENTO', 'Conta': BANCO,
     'Conta Contraparte': CLIENTE, 'Valor': '9,99'},
    {'Título': 'X3', 'Tipo Operação': 'RESGATE', 'Conta': BANCO,
     'Conta Contraparte': CLIENTE, 'Valor': '77,00'},
]
legs = R._ndfsum_b3_legs(ops)
ACC_BANCO, ACC_MGT = R._OPB3_ACCT_BANCO, R._OPB3_ACCT_MGT
check('a conta de casa sai do LEGAL', R._opb3_legal_side('BANCO J.P. MORGAN S.A.'), ACC_BANCO)
check('   e a da outra entidade tambem',
      R._opb3_legal_side('J.P. MORGAN CHASE BANK, N.A.'), ACC_MGT)
check('LEGAL que nao classifica devolve vazio', R._opb3_legal_side('ACME LTDA'), '')
# O caso que motivou a mudanca.
check('pela otica do Banco, o intragrupo e +1.000',
      R._ndfsum_b3_val(legs, 'X1', ACC_BANCO, ACC_MGT), '1.000,00')
check('pela otica da MGT, e -1.000',
      R._ndfsum_b3_val(legs, 'X1', ACC_MGT, ACC_BANCO), '-1.000,00')
# Sem saber a contraparte, a conta de casa ja resolve.
check('so com a conta de casa (Banco)', R._ndfsum_b3_val(legs, 'X1', ACC_BANCO, ''), '1.000,00')
check('so com a conta de casa (MGT)', R._ndfsum_b3_val(legs, 'X1', ACC_MGT, ''), '-1.000,00')
# Cliente externo: a chave especifica nao existe, e a frouxa resolve.
check('cliente externo', R._ndfsum_b3_val(legs, 'X2', ACC_BANCO, ''), '500,00')
check('   mesmo sem conta de casa', R._ndfsum_b3_val(legs, 'X2', '', ''), '500,00')
check('resgate vence o outro evento do mesmo Titulo',
      R._ndfsum_b3_val(legs, 'X3', ACC_BANCO, ''), '77,00')
check('Titulo que nao existe devolve vazio', R._ndfsum_b3_val(legs, 'X9', ACC_BANCO, ''), '')
# E a tela usa isso de verdade.
blk = SRC.split('def _ndfsum_collect', 1)[1].split('\n@blueprint', 1)[0]
check('o Trade Level pega a conta de casa pelo LEGAL',
      "_opb3_legal_side(row[ci['LEGAL']])" in blk, True)
check('   e a da contraparte pelo nome dela',
      "_opb3_legal_side(row[ci['NM_COUNTERPARTY']])" in blk, True)
check('   e busca pelas tres chaves', '_ndfsum_b3_val(legs, b3.upper(), casa, cpty_acc)' in blk, True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
