#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_b3_accounts.py — o cadastro `b3-accounts` e o Participante do TER.

O que era `b3-omnibus-account` (uma coluna, e estar na tabela era a resposta)
virou a lista das contas B3 de cada entidade nossa: LE, Nome Simplificado,
conta e TIPO. Duas perguntas passam por ele, e as duas erram em SILENCIO:

  1. **quem e o Participante** do header dos arquivos TER. Era um dicionario
     fixo no `routes.py`, com a mesma resposta escrita tambem no `source_note`
     do File Interpreter. O campo e X(20) e o motor completa com espacos - um
     nome mais curto que 20 nao pode sair sem o preenchimento, e o layout
     inteiro desandaria a partir dali;
  2. **a conta identifica o cliente?** So CLIENT 1 e CLIENT 2 sao guarda-chuva.
     Se estar na tabela voltasse a ser a resposta, a conta PROPRIA - que agora
     esta cadastrada - passaria a mandar o app procurar cliente pelo CNPJ onde
     nao ha cliente nenhum.

Le o cadastro versionado, o template do File Interface e o `routes.py`; nao
escreve nada e nao toca em dado real.
"""
import io
import json
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, 'scripts', 'tests'))

from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def read(rel):
    return io.open(os.path.join(ROOT, rel), encoding='utf-8').read()


SRC = read('apps/pages/routes.py')
ROWS = R._mapping_rows('b3-accounts')

print('\n== 1. o cadastro ==')
check('registrado como b3-accounts', "'b3-accounts': {" in SRC, True)
check('o nome antigo saiu do registro', "'b3-omnibus-account': {" in SRC, False)
check('aba no /mapping', "key: 'b3-accounts'" in read('apps/templates/pages/mapping.html'), True)
check('as colunas do cadastro',
      [c['key'] for c in R._MAPPING_DEFS['b3-accounts']['columns']],
      ['LE', 'SIMPLIFIED NAME', 'ACCOUNT', 'ACCOUNT TYPE',
       'REFDATA NAME', 'MESSAGING', 'NOTES'])
# O Nome Simplificado ao lado e o apelido de 20 caracteres da B3
# (INTRAGLAWTONFDO), que nao e razao social nenhuma: quem endereca documento
# precisa do nome do Reference Data, e ele se escolhe da lista de la.
refd_col = [c for c in R._MAPPING_DEFS['b3-accounts']['columns']
            if c['key'] == 'REFDATA NAME'][0]
check('o nome do RefData e ligado ao Reference Data', refd_col.get('refdata'), 'name')
# O TIPO e o que decide a regra: digitado a mao, um "Cliente1" viraria conta
# PROPRIA sem erro nenhum.
tipo_col = [c for c in R._MAPPING_DEFS['b3-accounts']['columns']
            if c['key'] == 'ACCOUNT TYPE'][0]
check('o tipo e um select, nao texto livre', tipo_col.get('type'), 'select')
check('e as opcoes sao os tres tipos', tipo_col.get('options'), list(R._B3_ACCOUNT_TYPES))

print('\n== 2. as sete contas do documento da B3 ==')
esperado = [
    ('MGT', 'MORGANBC', '04880.00-6', 'OWN'),
    ('MGT', 'MORGANBC', '04880.10-9', 'CLIENT 1'),
    ('JPM', 'JPMORGANBM', '73760.00-9', 'OWN'),
    ('JPM', 'JPMORGANBM', '73760.10-2', 'CLIENT 1'),
    ('JPM', 'JPMORGANBM', '73760.20-5', 'CLIENT 2'),
    ('LAWTON', 'INTRAGLAWTONFDO', '00041.00-7', 'OWN'),
    ('ATACAMA', 'INTRAGATACAMAFDO', '85398.00-5', 'OWN'),
]
check('as sete linhas, na ordem cadastrada',
      [(r.get('LE'), r.get('SIMPLIFIED NAME'), r.get('ACCOUNT'), r.get('ACCOUNT TYPE'))
       for r in ROWS], esperado)
check('o arquivo versionado tem o mesmo conteudo do seed',
      json.loads(read('apps/static/data/mappings/b3-accounts.json')),
      list(R._MAPPING_DEFS['b3-accounts']['seed']))

print('\n== 3. o tipo de conta e cego a caixa e acento ==')
# A tabela nasceu em portugues, e e assim que a mesa a le no documento da B3.
check('PROPRIA', R._b3_account_type('PROPRIA'), 'OWN')
check('Propria com acento', R._b3_account_type('Própria'), 'OWN')
check('CLIENTE 1', R._b3_account_type('CLIENTE 1'), 'CLIENT 1')
check('cliente 2 minusculo', R._b3_account_type('cliente 2'), 'CLIENT 2')
check('CLIENT 1 ja canonico', R._b3_account_type('CLIENT 1'), 'CLIENT 1')
check('espaco sobrando', R._b3_account_type('  CLIENT  2 '), 'CLIENT 2')
check('vazio nao e tipo nenhum', R._b3_account_type(''), '')
check('lixo nao vira tipo', R._b3_account_type('QUALQUER'), '')

print('\n== 4. guarda-chuva e o TIPO, nao estar na tabela ==')
for conta, exp in (('73760.10-2', True), ('73760.20-5', True), ('04880.10-9', True),
                   ('73760.00-9', False), ('04880.00-6', False),
                   ('00041.00-7', False), ('85398.00-5', False)):
    check('%s -> omnibus=%s' % (conta, exp), R._b3_is_omnibus(conta), exp)
check('conta fora do cadastro nao e omnibus', R._b3_is_omnibus('11111.11-1'), False)
check('e a comparacao continua por digitos', R._b3_is_omnibus('7376020 5'), True)

print('\n== 5. o Participante sai do cadastro, pela LE da visao ==')
check('JPM', R._b3_participant_name('JPM'), 'JPMORGANBM')
check('LAWTON', R._b3_participant_name('LAWTON'), 'INTRAGLAWTONFDO')
check('MGT', R._b3_participant_name('MGT'), 'MORGANBC')
check('ATACAMA', R._b3_participant_name('ATACAMA'), 'INTRAGATACAMAFDO')
check('LE minuscula resolve igual', R._b3_participant_name('jpm'), 'JPMORGANBM')
check('LE sem cadastro devolve vazio', R._b3_participant_name('XPTO'), '')
check('LE vazia devolve vazio', R._b3_participant_name(''), '')
# O balde e o vocabulario do gerador ('BANCO'), a LE e o do cadastro ('JPM').
check('o balde traduz para a LE', dict(R._TER_BUCKET_LE),
      {'BANCO': 'JPM', 'LAWTON': 'LAWTON', 'MGT': 'MGT'})
check('o dicionario fixo de nomes saiu do codigo',
      '_TER_PARTICIPANT_NAME' in SRC, False)

print('\n== 6. o header do TER, byte a byte ==')
# X(5) + X(1) + X(4) + X(20) + X(8) + 9(05) = 43. O Participante e completado
# com espacos ate 20: um nome curto sem preenchimento desloca tudo o que vem
# depois, e o arquivo chega a B3 com a data no lugar errado.
hdr = R._ter_file_header('JPM', '20260820', '/new_deals-ndf-vanilla')
check('a linha tem 43 caracteres', len(hdr), 43)
check('e o header e o de sempre', hdr, 'TER  00001JPMORGANBM          2026082000003')
check('o Participante ocupa as posicoes 11-30', hdr[10:30], 'JPMORGANBM          ')
check('MORGANBC completado ate 20',
      R._ter_file_header('MGT', '20260820', '/new_deals-ndf-fwdstart')[10:30],
      'MORGANBC            ')
check('INTRAGLAWTONFDO completado ate 20',
      R._ter_file_header('LAWTON', '20260820', '/new_deals-ndf-commodities')[10:30],
      'INTRAGLAWTONFDO     ')

# LE sem Nome Simplificado nao pode virar arquivo com o campo em branco: a B3
# recusa depois de a mesa ja ter mandado.
erro = ''
try:
    R._ter_file_header('XPTO', '20260820', '/new_deals-ndf-vanilla')
except ValueError as exc:
    erro = str(exc)
check('LE sem cadastro levanta ValueError', bool(erro), True)
check('e o erro diz QUAL entidade falta', "'XPTO'" in erro, True)
check('e para onde ir', '/mapping' in erro, True)

print('\n== 7. o File Interpreter aponta para o cadastro ==')
TPL = json.loads(read('apps/static/data/file-interpreter/termo-multiclasses.json'))
blk = [b for b in TPL['blocks'] if b['id'] == 'header'][0]
part = [f for f in blk['fields'] if f['seq'] == '4'][0]
check('o campo 4 e o Participante', part['field'], 'Participante')
check('a largura continua X(20)', part['format'], 'X(20)')
check('a origem e Mapping', part['source'], 'Mapping')
check('e o registro e o b3-accounts', part['source_detail'], 'b3-accounts')
# As quatro paginas de NDF dividem o template; o override por pagina e o que
# separa uma da outra, e aqui as quatro respondem a mesma coisa.
check('as quatro paginas de NDF tem override',
      sorted(part['source_by_page'].keys()),
      ['/new_deals-ndf-commodities', '/new_deals-ndf-fwdstart',
       '/new_deals-ndf-otherpublisher', '/new_deals-ndf-vanilla'])
check('e todas apontam para o mesmo cadastro',
      sorted(set((o['source'], o['source_detail'])
                 for o in part['source_by_page'].values())),
      [('Mapping', 'b3-accounts')])
# `Mapping` so e opcao valida se a tela oferecer o tipo.
check('a tela do File Interpreter tem a origem Mapping',
      "'Mapping'" in read('apps/templates/pages/file-interpreter.html'), True)

print('\n== 8. o upgrade do formato antigo ==')
# A tabela antiga listava SO as contas guarda-chuva: estar nela era a resposta.
# Lida como PROPRIA, a linha antiga deixaria de resolver o cliente pelo CNPJ.
velho = R._b3_accounts_upgrade([{'ACCOUNT': '73760.10-2', 'NOTES': 'omnibus'}])
check('a linha antiga vira CLIENT 1', velho[0]['ACCOUNT TYPE'], 'CLIENT 1')
check('e ganha as colunas novas em branco',
      (velho[0]['LE'], velho[0]['SIMPLIFIED NAME']), ('', ''))
check('a nota e preservada', velho[0]['NOTES'], 'omnibus')
# Ja no formato novo, o tipo em branco e uma ESCOLHA e continua em branco - a
# linha simplesmente nao e guarda-chuva.
novo = R._b3_accounts_upgrade([{'LE': 'JPM', 'SIMPLIFIED NAME': 'JPMORGANBM',
                                'ACCOUNT': '73760.00-9', 'ACCOUNT TYPE': ''}])
check('linha nova sem tipo NAO vira CLIENT 1', novo[0]['ACCOUNT TYPE'], '')
check('a grafia em portugues e normalizada',
      R._b3_accounts_upgrade([{'LE': 'JPM', 'ACCOUNT TYPE': 'Cliente 1'}])[0]['ACCOUNT TYPE'],
      'CLIENT 1')
check('e o upgrade esta ligado no registro',
      R._MAPPING_DEFS['b3-accounts'].get('upgrade') is R._b3_accounts_upgrade, True)

print('\n== 8b. a coluna MESSAGING: de que VISAO a mensageria sai ==')
# A liquidacao intragrupo chega pelos DOIS arquivos, espelhada. As duas pontas
# virando e-mail, o time cobraria duas vezes o mesmo pagamento.
msg_col = [c for c in R._MAPPING_DEFS['b3-accounts']['columns']
           if c['key'] == 'MESSAGING'][0]
check('e um select', msg_col.get('type'), 'select')
check('com Consider e Disregard', msg_col.get('options'), list(R._B3_MSG_USES))
check('o Banco assina', R._b3_msg_view_use('73760.00-9'), True)
check('a MGT nao', R._b3_msg_view_use('04880.00-6'), False)
# Estas duas passavam direto na regra antiga, que so conhecia o par MGT x Banco.
check('o Lawton nao', R._b3_msg_view_use('00041.00-7'), False)
check('a Atacama nao', R._b3_msg_view_use('85398.00-5'), False)
# A conta e comparada por DIGITOS: o mesmo numero aparece com e sem pontuacao.
check('a conta sem pontuacao casa', R._b3_msg_view_use('7376000 9'), True)
check('  e a da MGT tambem', R._b3_msg_view_use('0488000 6'), False)
# Conta de terceiro: e dela que a mensagem sai hoje. Travar por falta de linha
# calaria a rotina inteira onde ninguem abriu o /mapping.
check('conta fora do cadastro gera', R._b3_msg_view_use('11111.11-1'), True)
check('conta em branco gera', R._b3_msg_view_use(''), True)

# Quem e a contraparte sai da CONTA, nao da grafia do Nome Simplificado.
check('a conta diz a LE', R._b3_account_le('85398.00-5'), 'ATACAMA')
check('conta de fora nao diz LE', R._b3_account_le('11111.11-1'), '')

# O arquivo que ja esta em disco vem sem a coluna: o upgrade a completa PELO
# SEED. Um default cego 'Consider' faria a mensagem sair pelas duas pontas.
up = R._b3_accounts_upgrade([
    {'LE': 'JPM', 'ACCOUNT': '73760.00-9', 'ACCOUNT TYPE': 'OWN'},
    {'LE': 'MGT', 'ACCOUNT': '04880.00-6', 'ACCOUNT TYPE': 'OWN'},
    {'LE': 'ATACAMA', 'ACCOUNT': '85398.00-5', 'ACCOUNT TYPE': 'OWN'},
    {'LE': 'CLIENTE', 'ACCOUNT': '99999.00-1', 'ACCOUNT TYPE': 'OWN'},
])
check('upgrade: Banco Consider', up[0]['MESSAGING'], 'Consider')
check('upgrade: MGT Disregard', up[1]['MESSAGING'], 'Disregard')
check('upgrade: Atacama Disregard', up[2]['MESSAGING'], 'Disregard')
check('upgrade: conta desconhecida gera', up[3]['MESSAGING'], 'Consider')
# Escolha feita na tela nao se reescreve pelo seed.
mantido = R._b3_accounts_upgrade([{'LE': 'MGT', 'ACCOUNT': '04880.00-6',
                                   'MESSAGING': 'Consider'}])
check('upgrade nao pisa no que foi escolhido', mantido[0]['MESSAGING'], 'Consider')

print('\n== 8c. a mensageria usa o cadastro, e nao mais o par fixo ==')
# A regra antiga era `casa == MGT and contraparte == Banco`, escrita no
# endpoint: ela conhecia esse par e so ele.
check('o endpoint pergunta ao cadastro', '_b3_msg_view_use(rec.get(' in SRC, True)
check('a regra fixa da visao MGT saiu', '_mgt_view' in SRC, False)
# O inner join com o opb3-events continua: evento que nao e liquidacao nao vira
# mensagem pedindo pagamento.
mens = SRC[SRC.index('def api_opb3_mensageria('):]
mens = mens[:mens.index('\n@blueprint.route', 1) if '\n@blueprint.route' in mens[1:] else len(mens)]
check('e o join com opb3-events tambem', '_opb3_settle_ok(rec, ev_rules)' in mens, True)

print('\n== 9. a traducao da aba ==')
for lang, esperado_txt in (('en', 'B3 Accounts'), ('br', 'Contas B3'), ('es', 'Cuentas B3')):
    tr = json.loads(read('apps/static/data/translations/%s.json' % lang))
    check('%s: map-tab-b3-accounts' % lang, tr.get('map-tab-b3-accounts'), esperado_txt)
    check('%s: a chave antiga saiu' % lang, 'map-tab-b3-omnibus' in tr, False)

print('\nFALHAS: %d' % len(fails))
sys.exit(1 if fails else 0)
