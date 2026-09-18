#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_unwind_ter_file.py — o ARQUIVO da B3 da recompra de NDF de moeda.

O TER 0014 (Antecipacao de Contrato a Termo Sem CCP, secao 4.9.3 do manual
`Enviar Arquivos` v.14/09/2026, pag. 730-732) e posicional de 133 caracteres.
Num arquivo posicional o defeito nao acusa: um campo um caractere mais curto
desloca TODOS os seguintes e a linha continua com o tamanho certo. A B3 aceita
e a mesa descobre pelo extrato.

Este teste prende as tres coisas que podem divergir em silencio:

  1. o CADASTRO consigo mesmo — a `position` de cada campo tem de ser a
     largura do `format`, os campos tem de ser contiguos e o bloco tem de
     fechar nos 133 do `record_length`;
  2. o DOMINIO com o cadastro — a largura que o `TER_0014_LAYOUT` usa para
     formatar cada valor tem de ser a mesma que o cadastro declara na
     `position`. E esta a juncao que desliza: o dominio formata, o motor so
     concatena, e ninguem confere;
  3. a LINHA montada pelo motor de verdade (`_fi_build_line`), campo a campo,
     na fatia que o cadastro declara — com os valores da operacao REAL de
     10/09/2026 que a fixture do `check_unwind_notification` carrega.

Nao encosta em dado real: copia o template do repositorio para um tmp e aponta
o motor para la, como fazem os demais check_fi_*.
"""
import datetime as _dt
import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.gettempdir())

from apps.pages import routes as R                                      # noqa: E402
from apps.pages.features.unwinds import domain                          # noqa: E402

CHAVE = 'antecipacao-termo-multiclasses'
ORIGEM = os.path.join(ROOT, 'apps', 'static', 'data', 'file-interpreter',
                      CHAVE + '.json')
TPL = json.load(io.open(ORIGEM, encoding='utf-8'))

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label
          + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def bloco(bid):
    for b in TPL['blocks']:
        if b['id'] == bid:
            return b
    raise AssertionError('bloco ausente: ' + bid)


def posicao(campo):
    ini, fim = str(campo['position']).replace(' ', '').split('-')
    return int(ini), int(fim)


# ─────────────────────────────────────────────────────────────────────────────
print('\n== 1. o cadastro e coerente consigo mesmo ==')
check('identificacao do layout', (TPL['system_id'], TPL['file_type'],
                                  TPL['record_length']), ('TER', 'positional', 133))
check('secao e paginas do manual em vigor',
      (TPL['manual_section'], TPL['manual_pages'], TPL['manual_version']),
      ('4.9.3 Antecipação de Contrato a Termo Sem CCP', '730-732', '14/09/2026'))

for b in TPL['blocks']:
    esperado = 1
    larguras_ok, contiguo_ok = True, True
    for f in b['fields']:
        ini, fim = posicao(f)
        if fim - ini + 1 != domain.largura(f['format']):
            larguras_ok = False
            print('        %s seq %s: position %s nao e a largura de %s'
                  % (b['id'], f['seq'], f['position'], f['format']))
        if ini != esperado:
            contiguo_ok = False
            print('        %s seq %s: comeca em %d, o campo anterior fechou em %d'
                  % (b['id'], f['seq'], ini, esperado - 1))
        esperado = fim + 1
    check('%s: position = largura do format' % b['id'], larguras_ok, True)
    check('%s: campos contiguos desde a posicao 1' % b['id'], contiguo_ok, True)

check('o registro fecha nos 133 do record_length',
      posicao(bloco('registro-dados-fixos')['fields'][-1])[1], 133)
check('o header tem os 43 de sempre',
      posicao(bloco('header')['fields'][-1])[1], 43)

print('\n== 2. todo campo tem origem declarada ==')
sem_origem = ['%s/%s %s' % (b['id'], f['seq'], f['field'])
              for b in TPL['blocks'] for f in b['fields'] if not f.get('source')]
check('nenhum Source em branco', sem_origem, [])
check('o Fixed do header carrega a versao de layout do 0014',
      [f['source_detail'] for f in bloco('header')['fields'] if f['seq'] == '6'],
      [domain.TER_VERSAO_LAYOUT])
check('e o codigo de operacao e o 0014 nos tres blocos',
      sorted({f['source_detail'] for b in TPL['blocks'] for f in b['fields']
              if f['seq'] == '3'}), [domain.TER_CODIGO_OPERACAO])

print('\n== 3. o dominio formata na largura que o CADASTRO declara ==')
pos_por_seq = {f['seq']: posicao(f) for f in bloco('registro-dados-fixos')['fields']}
divergentes = []
for seq, nome, formato in domain.TER_0014_LAYOUT:
    ini, fim = pos_por_seq[seq]
    if domain.largura(formato) != fim - ini + 1:
        divergentes.append((seq, nome, formato, '%d-%d' % (ini, fim)))
check('largura do TER_0014_LAYOUT = largura do cadastro', divergentes, [])
check('o LAYOUT cobre todo campo nao-Fixed do registro',
      sorted((s for s, _, _ in domain.TER_0014_LAYOUT), key=int),
      sorted((f['seq'] for f in bloco('registro-dados-fixos')['fields']
              if f['seq'] not in ('1', '2', '3')), key=int))
nomes_cadastro = {f['seq']: f['field'] for f in bloco('registro-dados-fixos')['fields']}
check('e chama cada campo pelo nome do cadastro',
      [(s, n) for s, n, _ in domain.TER_0014_LAYOUT if nomes_cadastro[s] != n], [])

print('\n== 4. formatar_b3: a convencao de cada formato ==')
check('9(08) zero a esquerda', domain.formatar_b3('41007', '9(08)'), '00041007')
check('9(08) tira a mascara da conta', domain.formatar_b3('73760.00-9', '9(08)'), '73760009')
check('X(11) alinha a esquerda', domain.formatar_b3('26C03202688', 'X(11)'), '26C03202688')
check('9(14)V9(02) separa inteiros e centavos',
      domain.formatar_b3(144122.68, '9(14)V9(02)'), '0000000014412268')
check('9(12)V9(08) com as oito casas',
      domain.formatar_b3('5.2067', '9(12)V9(08)'), '00000000000520670000')
check('9(02)V9(08) da taxa de juros',
      domain.formatar_b3(13.81, '9(02)V9(08)'), '1381000000')
check('9(04)V9(08): o 1 do layout e "000100000000"',
      domain.formatar_b3(1.0, '9(04)V9(08)'), '000100000000')
check('arredonda para a ultima casa, nao trunca',
      domain.formatar_b3('10.005', '9(14)V9(02)'), '0000000000001001')
check('vazio e BRANCO na largura, nao zeros',
      domain.formatar_b3('', '9(08)'), '        ')
check('None tambem', domain.formatar_b3(None, '9(08)'), '        ')
check('mas zero e ZERO (nao se aplica != vale zero)',
      domain.formatar_b3(0, '9(08)'), '00000000')
check('valor que estoura a largura devolve None, nao um numero cortado',
      domain.formatar_b3('123456789012345678', '9(14)V9(02)'), None)
check('texto que nao e numero devolve None',
      domain.formatar_b3('n/a', '9(14)V9(02)'), None)

print('\n== 5. valores_ter_0014: falta = aviso + branco, jamais zero ==')
vals, avisos = domain.valores_ter_0014({'Contrato': None, 'Liquidante': ''})
check('campo sem valor sai em branco', vals['8'], ' ' * 11)
check('e avisa qual', [a['params']['campo'] for a in avisos
                       if a['code'] == 'unwind_ter_campo_vazio' and a['params']['seq'] == '8'],
      ['Contrato'])
check('o Liquidante em branco NAO vira aviso (e a decisao da mesa)',
      [a for a in avisos if a['params']['campo'] == 'Liquidante'], [])
check('valor que nao cabe avisa como invalido, nao como ausente',
      [a['code'] for a in domain.valores_ter_0014(
          {'Valor Base a Antecipar': '999999999999999999'})[1]
       if a['params']['seq'] == '9'], ['unwind_ter_campo_invalido'])

# ─────────────────────────────────────────────────────────────────────────────
print('\n== 6. a linha do motor, campo a campo, na operacao REAL ==')
# E-mail `BRL NDF Unwind Notification` de 10/09/2026 (a fixture do
# check_unwind_notification) contra a linha do Live Position do contrato.
ANTES  = {'Notional': '226,997.40', 'Notional CCY': 'USB', 'Strike': '5.3748'}
DEPOIS = {'Unwound Amount': '42,227.42', 'Termination Rate': '5.109',
          'Pre FWD Rate': '13.75', 'DU': '14',
          'Input Termination Fee': '11,144.00', 'Direction': 'RECEIVE'}
POS = {'Contrato': '26C03202688', 'Simbolo da Moeda': 'USD',
       'Descricao da posicao do Participante': 'COMPRADOR',
       'Valor Base no registro': '587,224.31', 'Valor Antecipado': '155,652.49',
       'Codigo da Parte': '73760.00-9', 'Codigo da Contraparte': '41007'}

campos, av_campos = domain.campos_ter_0014(
    ANTES, DEPOIS, POS, _dt.date(2026, 9, 10), controle_interno='1001000100')
valores, av_vals = domain.valores_ter_0014(campos)
check('nada ficou sem resposta', [a['code'] for a in av_campos + av_vals], [])

tmp = tempfile.mkdtemp(prefix='unwind-ter-')
old_dir = R._FILE_INTERPRETER_DIR
try:
    shutil.copy(ORIGEM, os.path.join(tmp, CHAVE + '.json'))
    R._FILE_INTERPRETER_DIR = tmp
    R._fi_tpl_cache.clear()

    linha = R._fi_build_line(CHAVE, 'registro-dados-fixos', valores)
    check('a linha tem os 133 caracteres do layout', len(linha), 133)

    ESPERADO = {
        '1':  'TER  ',                  # Fixed do cadastro
        '2':  '1',
        '3':  '0014',
        '4':  '1001000100',             # Nº Controle Interno
        '5':  '73760009',               # conta propria, da posicao
        '6':  '0',                      # comprado
        '7':  '00041007',               # contraparte, da posicao (zeros a esquerda)
        '8':  '26C03202688',            # contrato achado pelo identificador
        '9':  '0000000004222742',       # 42.227,42 em moeda estrangeira
        '10': '20260910',
        '11': '20260910',
        '12': '00000000000510900000',   # Termination Rate 5,109
        '13': '1375000000',             # Pre FWD Rate 13,75% a.a.
        '14': '000100000000',           # taxa termo em BRL -> 1
        '15': '        ',               # liquidante em branco
        '16': '000',                    # sem media
    }
    erradas = []
    for f in bloco('registro-dados-fixos')['fields']:
        ini, fim = posicao(f)
        fatia = linha[ini - 1:fim]
        if fatia != ESPERADO[f['seq']]:
            erradas.append('seq %s (%s) pos %s: %r != %r'
                           % (f['seq'], f['field'], f['position'], fatia,
                              ESPERADO[f['seq']]))
    check('cada campo na fatia que o cadastro declara', erradas, [])
    check('a linha inteira', linha, ''.join(ESPERADO[f['seq']] for f in
                                            bloco('registro-dados-fixos')['fields']))

    print('\n== 7. o header sai do cadastro, so a data e do gerador ==')
    hdr = R._fi_build_line(CHAVE, 'header',
                           {'4': 'JPMORGANBM', '5': '20260910'})
    check('43 caracteres', len(hdr), 43)
    check('tipo de linha 0 e operacao 0014', hdr[:10], 'TER  00014')
    check('participante em X(20)', hdr[10:30], 'JPMORGANBM'.ljust(20))
    check('data e versao de layout', hdr[30:43], '20260910' + '00002')

    print('\n== 8. fixo em reais: o valor base vai em MOEDA ESTRANGEIRA ==')
    # Mesmo contrato do §23 do check_unwind_notification: Notional CCY = BRR,
    # Unwound Amount em BRL. Na B3 o contrato e em USD, e o campo 9 tem de
    # levar 750.000,01 / 5,2039 = 144.122,68 — nao os 750 mil.
    cb, _ = domain.campos_ter_0014(
        {'Notional': '3,055,856.61', 'Notional CCY': 'BRR', 'Strike': '5.2039'},
        {'Unwound Amount': '750,000.01', 'Termination Rate': '5.2067',
         'Pre FWD Rate': '13.81'},
        POS, _dt.date(2026, 9, 10), controle_interno='1001000100')
    vb, _ = domain.valores_ter_0014(cb)
    lb = R._fi_build_line(CHAVE, 'registro-dados-fixos', vb)
    check('campo 9 em USD, nao em BRL', lb[48:64], '0000000014412268')
    check('e a linha continua com 133', len(lb), 133)
finally:
    R._FILE_INTERPRETER_DIR = old_dir
    R._fi_tpl_cache.clear()
    shutil.rmtree(tmp, ignore_errors=True)

print('')
if fails:
    print('FALHAS (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('tudo ok')
