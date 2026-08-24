#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reconciliação de CGD — a tradução do workflow Alteryx `Batimento CGD`.

O que este teste protege é o que a tradução tinha de acertar, e que erra em
SILÊNCIO quando quebra:

1. **O D-1** é o último dia útil ANBIMA, e é dele que sai o nome do arquivo da
   B3. Errando o dia, a recon lê o arquivo de outro pregão e reporta quebras que
   não existem.
2. **As contas próprias** saem do cadastro `b3-accounts` (`OWN` + LE que assina
   CGD). Sem filtro, o arquivo inteiro da B3 entraria no batimento; com as
   contas dos fundos, o `Only B3` enche de contraparte que não é cliente.
3. **CNPJ compara por DÍGITO.** A B3 manda `12.345.678/0001-99` e a planilha
   manda `12345678000199` — comparar texto casa NADA, sem erro nenhum (§197).
4. **Os cortes do FEP**: fora `Cancelado`, fora o aditamento, e o CNPJ com várias
   solicitações vale pela MAIS RECENTE.
5. **Os buckets**, que são o relatório inteiro: o que falta incluir na B3, o que
   falta assinar, o que está justificado (garantidor / conta encerrada) e o que
   só a B3 conhece.
6. **O cache lê no MESMO dia em que grava.** A leitura sem data caía em `hoje` e
   a gravação em D-1: o batimento rodava e o GET seguinte dizia que ninguém
   tinha rodado.

Não toca em rede nem em dado real: o arquivo da B3, a lista do FEP e os
cadastros são sintéticos, num diretório temporário.
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

TMP = tempfile.mkdtemp(prefix='cgd-recon-')
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(TMP, 'share'))
os.environ['CETIP_SOURCE_ROOT'] = os.path.join(TMP, 'b3')
os.environ['CGD_INPUT_ROOT'] = os.path.join(TMP, 'fep')

from apps.pages import recon_cgd as R                            # noqa: E402

# Cadastros e cache vão para o tmp: o teste não escreve no repositório.
R._MAPPINGS_DIR = os.path.join(TMP, 'mappings')
R._CACHE_DIR = os.path.join(TMP, 'cache')
os.makedirs(R._MAPPINGS_DIR, exist_ok=True)

falhas = []


def check(label, got, exp):
    ok = got == exp
    print(('ok   ' if ok else 'FAIL ') + label + '  ->  ' + repr(got))
    if not ok:
        falhas.append('%s: %r != %r' % (label, got, exp))


def cadastro(nome, linhas):
    with open(os.path.join(R._MAPPINGS_DIR, nome + '.json'), 'w', encoding='utf-8') as fh:
        json.dump(linhas, fh, ensure_ascii=False)
    R._MAP_CACHE.pop(nome, None)


# ── 1. O D-1 ────────────────────────────────────────────────────────────────

print('== o dia da posição ==')
# Sábado 22/08/2026 → o último dia útil antes dele é sexta 21.
check('sábado volta para a sexta', R.dia_util_anterior(date(2026, 8, 22)), date(2026, 8, 21))
check('segunda volta para a sexta', R.dia_util_anterior(date(2026, 8, 24)), date(2026, 8, 21))

# Feriado: 07/09 (Independência). O dia útil antes de 08/09/2026 (terça) é 04/09
# (sexta), porque 07/09 é feriado e 05-06 é fim de semana.
antes = R.dia_util_anterior(date(2026, 9, 8))
check('feriado ANBIMA é pulado', antes, date(2026, 9, 4))

p = R.caminho_b3(date(2026, 8, 21))
check('o caminho tem ano/mês em inglês/dia',
      p.replace(os.sep, '/').endswith('2026/08. August/21/CETIP21_260821_DPOSICAO-NET'), True)


# ── 2. As contas próprias ───────────────────────────────────────────────────

print('\n== as contas do batimento ==')
cadastro('b3-accounts', [
    {'LE': 'JPM', 'ACCOUNT': '73760.00-9', 'ACCOUNT TYPE': 'OWN'},
    {'LE': 'MGT', 'ACCOUNT': '04880.00-6', 'ACCOUNT TYPE': 'OWN'},
    {'LE': 'JPM', 'ACCOUNT': '73760.10-2', 'ACCOUNT TYPE': 'CLIENT 1'},   # omnibus, fora
    {'LE': 'LAWTON', 'ACCOUNT': '00041.00-7', 'ACCOUNT TYPE': 'OWN'},     # fundo, fora
])
check('só OWN das entidades que assinam CGD',
      sorted(R.contas_proprias()), ['04880.00-6', '73760.00-9'])


# ── 3. O arquivo da B3 ──────────────────────────────────────────────────────

print('\n== o lado da B3 ==')
DIA = date(2026, 8, 21)
p = R.caminho_b3(DIA)
os.makedirs(os.path.dirname(p), exist_ok=True)
with open(p, 'w', encoding='latin-1') as fh:
    fh.write('\n'.join([
        '1,CTR1,73760.00-9,JPMORGANBM,9,MONDELEZ,10.144.076/0001-44,MONDELEZ BRASIL,CGD,',
        '2,CTR2,73760.00-9,JPMORGANBM,8,SEM CGD,55.555.555/0001-55,SEM CGD LTDA,CGD,',
        '3,CTR3,04880.00-6,MORGANBC,7,PARTICIPANTE X,,,CGD,',      # sem CNPJ → cadastro
        '4,CTR4,04880.00-6,MORGANBC,6,PARTICIPANTE Y,,,CGD,',      # sem CNPJ e sem cadastro
        '5,CTR5,99999.99-9,OUTRO,5,NAO NOSSO,11.222.333/0001-44,NAO NOSSO,CGD,',
    ]) + '\n')

cadastro('cgd-b3-participante', [
    {'NOME CONTRAPARTE': 'participante  x', 'CNPJ': '77.777.777/0001-77',
     'RAZAO SOCIAL': 'RESOLVIDO PELO CADASTRO'},
])

avisos = []
b3, path = R.ler_b3(DIA, avisos)
check('a conta que não é nossa fica de fora', '11222333000144' in b3, False)
check('as contrapartes com CNPJ entram',
      sorted(b3.keys()), sorted(['10144076000144', '55555555000155', '77777777000177']))
check('o participante sem CNPJ é resolvido pelo cadastro',
      b3.get('77777777000177', {}).get('nome'), 'RESOLVIDO PELO CADASTRO')
check('   e o nome do cadastro casa cego a caixa e espaço duplo',
      '77777777000177' in b3, True)
check('o que ficou sem CNPJ sai, e a recon AVISA', bool(avisos), True)

# Sem cadastro de conta não há como saber o que é nosso — e isso é aviso, não
# um filtro que deixa passar tudo.
cadastro('b3-accounts', [])
av2 = []
b3_vazio, _ = R.ler_b3(DIA, av2)
check('sem conta cadastrada o batimento não lê a B3', (b3_vazio, len(av2)), ({}, 1))
cadastro('b3-accounts', [
    {'LE': 'JPM', 'ACCOUNT': '73760.00-9', 'ACCOUNT TYPE': 'OWN'},
    {'LE': 'MGT', 'ACCOUNT': '04880.00-6', 'ACCOUNT TYPE': 'OWN'},
])


# ── 4. A lista do FEP ───────────────────────────────────────────────────────

print('\n== o lado do FEP ==')
from openpyxl import Workbook                                     # noqa: E402
os.makedirs(os.path.join(TMP, 'fep'), exist_ok=True)
wb = Workbook(); ws = wb.active
ws.append(['ID da Operação', 'CPF/CNPJ Cliente CMS', 'Nome Cliente CMS', 'STATUS CMS',
           'TIPO OPERAÇÃO', 'Criação'])
LIN = [
    ('1', '10.144.076/0001-44', 'MONDELEZ BRASIL', 'Assinatura Concluida', 'CGD', '01/07/2026'),
    ('2', '22.222.222/0001-22', 'PENDENTE B3', 'DOC TRANSACIONAL', 'CGD', '01/08/2026'),
    ('3', '33.333.333/0001-33', 'GARANTIDOR', 'Assinatura Manualmente', 'CGD', '10/08/2026'),
    ('4', '44444444000144', 'ENCERRADO', 'Assinatura Concluida', 'CGD', '12/08/2026'),
    ('5', '10.144.076/0001-44', 'MONDELEZ BRASIL', 'Cancelado', 'CGD', '20/08/2026'),
    ('6', '66.666.666/0001-66', 'ADITAMENTO', 'Assinatura Concluida',
     'ADITAMENTO AO CONTRATO GLOBAL DE DERIVATIVOS', '20/08/2026'),
    ('7', '77.777.777/0001-77', 'NAO ASSINADO', 'Em elaboracao', 'CGD', '18/08/2026'),
    # O mesmo CNPJ com duas solicitações: vale a mais RECENTE.
    ('8', '88.888.888/0001-88', 'DOIS PEDIDOS', 'Em elaboracao', 'CGD', '01/06/2026'),
    ('9', '88.888.888/0001-88', 'DOIS PEDIDOS', 'Assinatura Concluida', 'CGD', '15/08/2026'),
]
for l in LIN:
    ws.append(list(l))
wb.save(os.path.join(TMP, 'fep', 'LISTA_CONTRATOS_CGD.xlsx'))

av = []
fep, fep_path = R.ler_fep(av)
check('o Cancelado não entra (e o CNPJ dele fica pela linha boa)',
      fep.get('10144076000144', {}).get('status'), 'Assinatura Concluida')
check('o ADITAMENTO fica de fora', '66666666000166' in fep, False)
check('o CNPJ com dois pedidos vale pelo mais recente',
      (fep['88888888000188']['status'], R._fmt_date(fep['88888888000188']['criacao'])),
      ('Assinatura Concluida', '15/08/2026'))
check('   e a contagem lembra que eram dois', fep['88888888000188']['qtd'], 2)
check('CNPJ entra por DÍGITO, com ou sem pontuação', '44444444000144' in fep, True)


# ── 5. Os buckets ───────────────────────────────────────────────────────────

print('\n== o batimento ==')
cadastro('cgd-garantidor', [{'CNPJ / CPF': '33.333.333/0001-33', 'NOME': 'GARANTIDOR'}])
cadastro('cgd-conta-encerrada', [{'CNPJ / CPF': '44444444000144', 'NOME': 'ENCERRADO'}])

res = R.executar(DIA)
por_cliente = {r['client']: r for r in res['rows']}

check('nos dois lados e assinado → matched',
      (por_cliente['MONDELEZ BRASIL']['check'], por_cliente['MONDELEZ BRASIL']['bucket']),
      ('No breaks', 'matched'))
check('nos dois lados e NÃO assinado → pending_action',
      (por_cliente['NAO ASSINADO']['check'], por_cliente['NAO ASSINADO']['bucket']),
      ('No breaks', 'pending_action'))
check('só no FEP, assinado e sem justificativa → pending_b3',
      (por_cliente['PENDENTE B3']['check'], por_cliente['PENDENTE B3']['bucket']),
      ('Only FEP', 'pending_b3'))
check('   e o DOC TRANSACIONAL se lê Docusign',
      por_cliente['PENDENTE B3']['status'], 'Docusign')
check('garantidor sai da fila com a justificativa',
      (por_cliente['GARANTIDOR']['bucket'], por_cliente['GARANTIDOR']['obs']),
      ('justified', 'Guarantee'))
check('conta encerrada idem (casada por dígito)',
      (por_cliente['ENCERRADO']['bucket'], por_cliente['ENCERRADO']['obs']),
      ('justified', 'Closed Account'))
check('só na B3 → only_b3',
      (por_cliente['SEM CGD LTDA']['check'], por_cliente['SEM CGD LTDA']['bucket']),
      ('Only B3', 'only_b3'))
# O bucket sai do status da linha MAIS RECENTE: o pedido de junho estava em
# elaboração e o de agosto fechou, então o CNPJ conta como assinado e o que
# falta é a inclusão na B3. Pelo status antigo ele cairia na fila errada.
check('o bucket segue o status mais recente do CNPJ',
      por_cliente['DOIS PEDIDOS']['bucket'], 'pending_b3')

check('as contagens somam as linhas',
      sum(res['counts'].values()), len(res['rows']))
check('o aging é em dias CORRIDOS desde a criação',
      por_cliente['PENDENTE B3']['aging'], (date.today() - date(2026, 8, 1)).days)
check('linha sem data de criação não inventa aging',
      por_cliente['SEM CGD LTDA']['aging'], '')


# ── 6. O cache ──────────────────────────────────────────────────────────────

print('\n== o cache do dia ==')
R.salvar(res)
volta = R.carregar(res['ref'])
check('o dia gravado volta pela data', len(volta['rows']), len(res['rows']))
# O caso que quebrou na integração: gravar em D-1 e ler sem data.
hoje_util = R.dia_util_anterior()
res2 = R.executar(hoje_util)
R.salvar(res2)
check('e volta TAMBÉM sem data (o default é o mesmo dos dois lados)',
      bool(R.carregar()), True)
check('dia que ninguém rodou volta vazio', R.carregar('1999-01-04'), None)


# ── 7. O e-mail ─────────────────────────────────────────────────────────────

print('\n== o relatório ==')
from apps import create_app                                       # noqa: E402
from apps.config import DebugConfig                               # noqa: E402
app = create_app(DebugConfig)
with app.app_context():
    assunto, html = R.montar_email(res)
check('o assunto é o do workflow', assunto.startswith('CGD Matching - '), True)
for trecho in ('Hi Team', 'pending inclusion in B3', 'pending action',
               'guarantors', 'Best regards'):
    check('   a seção "%s" está no corpo' % trecho, trecho in html, True)
# O cabeçalho é cor sólida + gradiente CSS: VML/imagem é proibido (CLAUDE.md §2).
check('o cabeçalho não usa VML nem imagem',
      ('v:rect' in html or '<img' in html), False)
# Sem destinatário o envio é um DESFECHO, não um erro engolido.
ok, motivo = R.enviar_email(res, [])
check('sem destinatário o envio diz por quê', (ok, motivo), (False, 'no_recipient'))

shutil.rmtree(TMP, ignore_errors=True)

print()
if falhas:
    for f in falhas:
        print('FAIL ' + f)
    sys.exit(1)
print('TUDO OK')
