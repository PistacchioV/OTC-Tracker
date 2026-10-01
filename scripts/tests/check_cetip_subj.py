#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_cetip_subj.py — o cadastro de ATIVOS SUBJACENTES no Save CETIP Files.

O arquivo `CETIP_AAMMDD_COE` (apesar do nome, não é posição de COE) é salvo
pela rotina, vai anexo no e-mail do OTC Ops e atualiza a base
`Subjacente.json` (aba Underlying Assets do Index B3).

O que este teste prende:

  1. o comportamento casa pelo nome entre PARÊNTESES `(COE)` e não colide com
     o `COE (DRESUMOEMISSOR-COE)`; o padrão `CETIP_YYMMDD_COE` não casa o
     arquivo do DRESUMOEMISSOR, nem o contrário;
  2. as colunas casam pelo NOME do cabeçalho — a ordem do arquivo não é a da
     tela —, e sem cabeçalho valem na ordem publicada pela B3;
  3. a chave é (código, índice de valorização, tipo IF): o mesmo código em OPC
     e COE são linhas diferentes;
  4. STATUS/MAKER/CHECKER da linha existente sobrevivem; linha fora do arquivo
     fica intacta; numéricos entram como float.

Roda em tmp; não encosta na base real.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages import routes as R                                      # noqa: E402
from apps.pages import data_store as S                                  # noqa: E402
from apps.pages.features.cetip import domain as CD                      # noqa: E402
from apps.pages.features.cetip.infra import persistence as CP           # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label
          + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('== 1. comportamento e padrão ==')
b = CD._cetip_behaviour_for('Underlying Assets (COE)')
check('subj_update', b.get('subj_update'), True)
check('attach_ops (e-mail do OTC Ops)', b.get('attach_ops'), True)
check('TYPE reescrito na tela casa pelo parêntese',
      CD._cetip_behaviour_for('Ativos Subjacentes B3 (COE)').get('subj_update'), True)
check('o DRESUMOEMISSOR-COE segue sem subj_update',
      CD._cetip_behaviour_for('COE (DRESUMOEMISSOR-COE)').get('subj_update'), None)
novo = CD._cetip_make_matcher('CETIP_YYMMDD_COE', 'x')
velho = CD._cetip_make_matcher('CETIP21_YYMMDD_DRESUMOEMISSOR-COE', 'y')
check('padrão novo casa o arquivo', novo('cetip_260930_coe.txt'), True)
check('padrão novo NÃO casa o DRESUMOEMISSOR',
      novo('cetip21_260930_dresumoemissor-coe.txt'), False)
check('padrão velho NÃO casa o novo', velho('cetip_260930_coe.txt'), False)

print('== 2-4. atualização da base ==')
tmp = tempfile.mkdtemp()
base = os.path.join(R.data_dir(), '_test_subj', 'Subjacente.json')
R.SUBJ_JSON = base
existente_opc = {'STATUS': 'PENDING', 'Classe': 'AÇÕES', 'Codigo do Ativo Subjacente': 'AAPL34',
                 'Bolsa de Negociacao': 'X', 'Indice Valorizacao': 'AAPL34', 'Mes Vencimento': None,
                 'Ano Vencimento': None, 'Tipo': '-', 'Unidade de Negociacao': None, 'Moeda': 'REAL',
                 'Data Limite': None, 'Calculado': 'SIM', 'Commodity': None, 'Fator Conversao': None,
                 'Tipo Cotacao': None, 'Ticker': None, 'Tipo IF': 'OPC', 'MAKER': 'A1', 'CHECKER': None}
fora = dict(existente_opc, **{'Codigo do Ativo Subjacente': 'ZZZ9', 'Indice Valorizacao': 'ZZZ9',
                              'STATUS': 'ACTIVE', 'MAKER': None})
R._atomic_write_json(base, [existente_opc, fora])

# Ordem do ARQUIVO (a da B3), diferente da tela.
cab = ('Classe;Codigo do Ativo Subjacente;Bolsa de Negociacao;Indice Valorizacao;Mes Vencimento;'
       'Ano Vencimento;Tipo;Unidade de Negociacao;Moeda;Data Limite;Calculado;Commodity;'
       'Fator Conversao;Tipo Cotacao;Ticker;Tipo IF')
dados = ('AÇÕES;AAPL34;REUTERS;AAPL34;;;-;;REAL;;SIM;;;;;OPC\n'
         'AÇÕES;AAPL34;REUTERS;AAPL34;;;-;;REAL;;SIM;;;;;COE\n'
         'COMMODITIES;KWZ6;CBOT;KWZ6;12;2026;-;BUSHEL;DOLAR DOS EUA;20261214;SIM;TRIGO;0,01;AJUSTE;KWZ6;OPC\n')
arq = os.path.join(tmp, 'CETIP_260930_COE.txt')
with open(arq, 'w', encoding='cp1252') as fh:
    fh.write(cab + '\n' + dados)
check('devolve o caminho', CP._cetip_update_subj_json(arq), base)
out = S.read(base)
por = {(r['Codigo do Ativo Subjacente'], r['Tipo IF']): r for r in out}
check('3 linhas do arquivo + 1 fora = 4 (OPC atualizada, COE e KWZ6 novas)', len(out), 4)
check('Bolsa atualizada pelo NOME da coluna', por[('AAPL34', 'OPC')]['Bolsa de Negociacao'], 'REUTERS')
check('STATUS da mesa preservado', por[('AAPL34', 'OPC')]['STATUS'], 'PENDING')
check('MAKER preservado', por[('AAPL34', 'OPC')]['MAKER'], 'A1')
check('COE é linha própria', por[('AAPL34', 'COE')]['STATUS'], 'ACTIVE')
k = por[('KWZ6', 'OPC')]
check('Fator 0,01 → float', k['Fator Conversao'], 0.01)
check('Mês/Ano/Data Limite → float', (k['Mes Vencimento'], k['Ano Vencimento'], k['Data Limite']),
      (12.0, 2026.0, 20261214.0))
check('vazio → None', k['Ticker'] is not None and por[('AAPL34', 'COE')]['Ticker'], None)
check('linha fora do arquivo intacta', por[('ZZZ9', 'OPC')], fora)

# Cabeçalho em OUTRA ordem: casa pelo nome.
with open(arq, 'w', encoding='cp1252') as fh:
    fh.write('Tipo IF;Codigo do Ativo Subjacente;Indice Valorizacao;Bolsa de Negociacao\n'
             'OPC;AAPL34;AAPL34;BLOOMBERG\n')
CP._cetip_update_subj_json(arq)
por = {(r['Codigo do Ativo Subjacente'], r['Tipo IF']): r for r in S.read(base)}
check('cabeçalho reordenado casa pelo nome', por[('AAPL34', 'OPC')]['Bolsa de Negociacao'], 'BLOOMBERG')
check('rodar de novo não duplica', len(S.read(base)), 4)

# Sem cabeçalho: ordem da B3.
with open(arq, 'w', encoding='cp1252') as fh:
    fh.write('AÇÕES;PETR4;B3;PETR4;;;-;;REAL;;SIM;;;;;OPC\n')
CP._cetip_update_subj_json(arq)
check('sem cabeçalho entra pela ordem da B3', len(S.read(base)), 5)

try:
    S.remove(base)
except Exception:
    pass

print('\nTUDO OK' if not fails else '\n%d FALHA(S)' % len(fails))
sys.exit(1 if fails else 0)
