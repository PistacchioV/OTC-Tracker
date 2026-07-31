"""Publisher x B3 (NDF): match do publisher e roteamento Vanilla x Other Publisher.

Duas regras:
  1. Linha SEM Match Tokens casa so pelo texto COMPLETO, sem variacao. E o que
     permite 'PTAX' e 'PTAX|BRR|PTAX' serem cadastros independentes.
  2. NOTES = BACEN manda a operacao para a pagina Vanilla; qualquer outro valor
     (e publisher sem linha) vai para Other Publisher. Antes o roteamento era o
     literal `publisher.upper() != 'PTAX'`, entao a variante caia em Other
     Publisher e nao havia como corrigir sem mexer no codigo.

Usa um arquivo de mapping em tmp; nao encosta no cadastro real.
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import routes as R                       # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# --- cadastro de teste (o da tela do usuario + casos de borda) --------------
TMP = tempfile.mkdtemp()
R._MAPPINGS_DIR = TMP
ROWS = [
    {'PUBLISHER': 'PTAX', 'TOKENS': '', 'FONTE INFO': '0',
     'FONTE CONSULTA': '', 'TELA CONSULTA': '', 'NOTES': 'BACEN'},
    {'PUBLISHER': 'BFIX 4PM LONDON', 'TOKENS': 'BFIX', 'FONTE INFO': '1',
     'FONTE CONSULTA': '2', 'TELA CONSULTA': '14399', 'NOTES': 'BLOOMBERG'},
    {'PUBLISHER': 'REUTERS - WMR', 'TOKENS': 'WMR', 'FONTE INFO': '1',
     'FONTE CONSULTA': '0', 'TELA CONSULTA': '247', 'NOTES': 'REUTERS'},
    {'PUBLISHER': 'TRM COP', 'TOKENS': 'TRM', 'FONTE INFO': '1',
     'FONTE CONSULTA': '5', 'TELA CONSULTA': '11682', 'NOTES': 'OUTROS'},
    # a linha nova do usuario: sem tokens, NOTES BACEN
    {'PUBLISHER': 'PTAX|BRR|PTAX', 'TOKENS': '', 'FONTE INFO': '0',
     'FONTE CONSULTA': '', 'TELA CONSULTA': '', 'NOTES': 'BACEN'},
    # bordas de NOTES
    {'PUBLISHER': 'MINUSCULO', 'TOKENS': '', 'FONTE INFO': '0',
     'FONTE CONSULTA': '', 'TELA CONSULTA': '', 'NOTES': 'bacen'},
    {'PUBLISHER': 'COM ESPACO', 'TOKENS': '', 'FONTE INFO': '0',
     'FONTE CONSULTA': '', 'TELA CONSULTA': '', 'NOTES': '  BACEN  '},
    {'PUBLISHER': 'QUASE', 'TOKENS': '', 'FONTE INFO': '1',
     'FONTE CONSULTA': '', 'TELA CONSULTA': '', 'NOTES': 'BACEN/PTAX'},
    {'PUBLISHER': 'SEM NOTES', 'TOKENS': '', 'FONTE INFO': '1',
     'FONTE CONSULTA': '', 'TELA CONSULTA': '', 'NOTES': ''},
]
R._atomic_write_json(os.path.join(TMP, 'publisher-ndf.json'), ROWS)
R._mapping_cache.pop('publisher-ndf', None)


def pub(p):
    return str(R._ndf_publisher_row(p).get('PUBLISHER', '') or '')


print('\n== 1. linha SEM tokens casa so pelo texto completo ==')
check('PTAX exato',            pub('PTAX'), 'PTAX')
check('PTAX|BRR|PTAX exato',   pub('PTAX|BRR|PTAX'), 'PTAX|BRR|PTAX')
check('a variante NAO cai na linha PTAX',
      pub('PTAX|BRR|PTAX') != 'PTAX', True)
check('PTAX nao cai na variante', pub('PTAX') != 'PTAX|BRR|PTAX', True)
check('PTAXX nao casa nada',   pub('PTAXX'), '')
check('PTAX|BRR nao casa (texto incompleto)', pub('PTAX|BRR'), '')
check('PTAX|BRR|PTAX|X nao casa (texto a mais)', pub('PTAX|BRR|PTAX|X'), '')
check('caixa e espaco nao importam', pub('  ptax|brr|ptax  '), 'PTAX|BRR|PTAX')

print('\n== 2. linha COM tokens continua casando por trecho ==')
check('PTAX|USB|WMR|4 -> REUTERS', pub('PTAX|USB|WMR|4'), 'REUTERS - WMR')
check('XXBFIXYY -> BFIX',          pub('XXBFIXYY'), 'BFIX 4PM LONDON')
check('nome exato vence o token',  pub('TRM COP'), 'TRM COP')

print('\n== 3. NOTES = BACEN decide Vanilla ==')
for p, exp in (('PTAX', True), ('PTAX|BRR|PTAX', True), ('MINUSCULO', True),
               ('COM ESPACO', True), ('QUASE', False), ('SEM NOTES', False),
               ('REUTERS - WMR', False), ('TRM COP', False),
               ('PTAX|USB|WMR|4', False), ('NAO CADASTRADO', False),
               ('', True)):
    check('is_bacen(%r)' % p, R._ndf_publisher_is_bacen(p), exp)

print('\n== 4. roteamento ponta a ponta (_ndf_deal_from_api) ==')


def route(publisher, instrument='FXNDF'):
    rec = {
        'DEAL NAME': 'D-1', 'END COUNTERPARTY': 'ACME', 'PUBLISHER': publisher,
        'INSTRUMENT TYPE': instrument, 'TRADE DATE': '2026-07-31',
        'SETTLEMENT DATE': '2026-08-31', 'INSTRUMENT': 'USB/BRR',
        'TYPE': 'BUY', 'STRIKE SET DATE': '',
    }
    target, deal = R._ndf_deal_from_api(rec, 'E930179', {}, '31/07/2026')
    return target


check('PTAX -> vanilla',                route('PTAX'), 'vanilla')
check('PTAX|BRR|PTAX -> vanilla',       route('PTAX|BRR|PTAX'), 'vanilla')
check('REUTERS - WMR -> other',         route('REUTERS - WMR'), 'other-publishers')
check('PTAX|USB|WMR|4 -> other',        route('PTAX|USB|WMR|4'), 'other-publishers')
check('nao cadastrado -> other',        route('FEEDER NOVO'), 'other-publishers')
check('publisher vazio -> vanilla',     route(''), 'vanilla')
check('FWD Start vence o publisher',
      route('PTAX', 'FXForwardStartNDF'), 'fwd-start')

print('\n== 5. regressao: o comportamento antigo e preservado ==')
# Antes: publisher vazio ou exatamente 'PTAX' -> vanilla; todo o resto -> other.
# Com o cadastro semeado (so PTAX tem BACEN), o resultado tem de ser o mesmo.
R._atomic_write_json(os.path.join(TMP, 'publisher-ndf.json'),
                     R._MAPPING_DEFS['publisher-ndf']['seed'])
R._mapping_cache.pop('publisher-ndf', None)
for p in ('PTAX', '', 'REUTERS - WMR', 'BFIX 4PM LONDON', 'TRM COP',
          'PTAX|USB|WMR|4', 'OBSERVADO/BCENTRAL CL', 'PEN SBSP/BCRP',
          'QUALQUER COISA', 'ptax'):
    antigo = 'other-publishers' if (p and p.upper() != 'PTAX') else 'vanilla'
    check('seed padrao: %-22r -> %s' % (p, antigo), route(p), antigo)

print('\n== 6. Fonte de Informacao segue a mesma linha ==')
check('PTAX -> 0',          R._ndf_publisher_fonte_info('PTAX').strip(), '0')
check('REUTERS - WMR -> 1', R._ndf_publisher_fonte_info('REUTERS - WMR').strip(), '1')
check('desconhecido -> 1',  R._ndf_publisher_fonte_info('XPTO').strip(), '1')
check('4 chars a direita',  R._ndf_publisher_fonte_info('PTAX'), '   0')

shutil.rmtree(TMP, ignore_errors=True)
print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
