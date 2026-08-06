"""Links da API viraram cadastro (/mapping › API Links).

O endereco do getTrades era constante em athena_api.py. Agora e uma linha por
USO ('New Deals', 'Unwinds') e PRODUTO (NDF, FXO, Commodities, Swaps), com
`YYYYMMDD` marcando a data de referencia. Tres armadilhas moram aqui:

  * o seed do NDF TEM que reproduzir a URL historica byte a byte, senao o dia em
    que a tela for aberta pela primeira vez o pull passa a bater noutro endereco;
  * a linha do PRODUTO tem de ganhar da linha curinga (PRODUCT em branco), senao
    um curinga cadastrado por engano sequestraria todos os produtos;
  * na linha curinga o `product` e do CODIGO (a rotina sabe o que esta puxando);
    na linha do produto, nao — ela foi escolhida PELO produto, e reescrever
    contrariaria o cadastro.

O que este script protege:

  1. Seed == URL historica, e existe linha para CADA produto (o FXO faltando foi
     o que a mesa notou).
  2. `build_url`: placeholder da data (inclusive no caminho), date sempre
     reescrito, product so no curinga, query alheia preservada.
  3. Sem arquivo / linha vazia, o New Deals cai no fallback e o Unwinds FALHA
     dizendo que falta cadastro — nunca chama o endpoint do New Deals.
  4. O upgrade converte o arquivo gravado antes da coluna PRODUCT.
  5. O mapping esta ligado na tela: `_MAPPING_DEFS`, o rail e as tres traducoes.

Nao encosta em dado real: o arquivo de cadastro vai para um tempfile e a sessao
HTTP e stub (nada sai da maquina).
"""
import io
import json
import os
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from apps.pages import athena_api as A                        # noqa: E402
from apps.pages import routes as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


SEED = {(r['USE'], r['PRODUCT']): r for r in R._MAPPING_DEFS['api-links']['seed']}
LEGACY = A.BASE_URL + A.TRADES_ENDPOINT + '?product=NDF&date=20260728'

print('\n== 1. o seed cobre uso x produto ==')
check('uma linha por produto do New Deals',
      sorted(p for u, p in SEED if u == 'New Deals'),
      ['Commodities', 'FXO', 'NDF', 'Swaps'])
check('seed NDF -> URL historica',
      A.build_url(SEED[('New Deals', 'NDF')]['URL'], date='20260728', force_product=False),
      LEGACY)
check('a constante de fallback bate com o seed',
      A.build_url(A.DEFAULT_NEW_DEALS_URL, product='NDF', date='20260728'), LEGACY)
check('o FXO tem endereco proprio',
      A.build_url(SEED[('New Deals', 'FXO')]['URL'], date='20260728', force_product=False),
      A.BASE_URL + A.TRADES_ENDPOINT + '?product=FXO&date=20260728')
check('o seed do Unwinds nasce SEM URL', SEED[('Unwinds', '')]['URL'], '')

print('\n== 2. build_url resolve o que o codigo manda ==')
BASE = A.BASE_URL + A.TRADES_ENDPOINT
check('linha do produto: o endereco vale como esta',
      A.build_url(BASE + '?product=FXO&date=YYYYMMDD', product='FXO', date='20260101',
                  force_product=False),
      BASE + '?product=FXO&date=20260101')
check('linha curinga: product do cadastro e sobrescrito',
      A.build_url(BASE + '?product=NDF&date=YYYYMMDD', product='FXO', date='20260101'),
      BASE + '?product=FXO&date=20260101')
check('date fora do query string (caminho)',
      A.build_url(BASE + '/YYYYMMDD?product=NDF', product='FXO', date='20260101'),
      BASE + '/20260101?product=FXO&date=20260101')
check('placeholder com separador',
      A.build_url(BASE + '?date=yyyy-mm-dd', product='NDF', date='20260101'),
      BASE + '?date=20260101&product=NDF')
check('parametros ausentes sao acrescentados',
      A.build_url(BASE, product='NDF', date='20260101'),
      BASE + '?product=NDF&date=20260101')
check('query alheia e preservada',
      A.build_url(BASE + '?env=uat&product=NDF&date=YYYYMMDD', product='Swaps', date='20260101'),
      BASE + '?env=uat&product=Swaps&date=20260101')
check('URL vazia -> None', A.build_url('', product='NDF', date='20260101'), None)
check('URL None -> None', A.build_url(None, product='NDF', date='20260101'), None)

print('\n== 3. leitura do cadastro e fallback ==')
tmp = tempfile.mkdtemp(prefix='otc-api-links-')
orig_file = A.API_LINKS_FILE
A.API_LINKS_FILE = os.path.join(tmp, 'api-links.json')


class _Resp(object):
    headers = {'Content-Type': 'application/json'}

    def __init__(self, url, params):
        self.seen = (url, params)

    def raise_for_status(self):
        pass

    def json(self):
        return {'url': self.seen[0], 'params': self.seen[1]}


class _Session(object):
    """Sessao stub: guarda a URL chamada em vez de sair na rede."""

    def get(self, url, params=None, timeout=None):
        return _Resp(url, params)


def called(usage, product='NDF', date='20260728'):
    """URL final que o fetch bateria, ja com os params do requests aplicados."""
    payload = A.fetch_trades(_Session(), product, date, usage=usage)
    url, params = payload['url'], payload['params'] or {}
    if params:
        url += ('&' if '?' in url else '?') + '&'.join('%s=%s' % kv for kv in params.items())
    return url


def write_rows(rows):
    with io.open(A.API_LINKS_FILE, 'w', encoding='utf-8') as fh:
        fh.write(json.dumps(rows))


try:
    check('sem arquivo, New Deals usa o endereco historico', called('New Deals'), LEGACY)
    try:
        called('Unwinds')
        check('sem arquivo, Unwinds falha', 'nao levantou', 'RuntimeError')
    except RuntimeError as exc:
        check('sem arquivo, Unwinds falha pedindo cadastro',
              'API Links' in str(exc), True)

    write_rows([{'USE': 'New Deals', 'PRODUCT': 'NDF', 'URL': ''},
                {'USE': 'Unwinds', 'PRODUCT': '', 'URL': ''}])
    check('linha sem URL == sem linha (New Deals)', called('New Deals'), LEGACY)

    # Curinga (PRODUCT em branco) + linha propria do FXO.
    write_rows([{'USE': 'new_deals', 'PRODUCT': '',
                 'URL': 'https://uat.example/api/v2/getTrades?date=YYYYMMDD'},
                {'USE': 'New Deals', 'PRODUCT': 'FXO',
                 'URL': 'https://uat.example/api/v3/getFxo?date=YYYYMMDD&product=FXO'},
                {'USE': 'Unwinds', 'PRODUCT': '',
                 'URL': 'https://uat.example/api/v2/getUnwinds?date=YYYYMMDD'}])
    check('produto sem linha propria cai no curinga', called('New Deals', 'NDF', '20260102'),
          'https://uat.example/api/v2/getTrades?date=20260102&product=NDF')
    check('a linha do produto ganha do curinga', called('New Deals', 'FXO', '20260102'),
          'https://uat.example/api/v3/getFxo?date=20260102&product=FXO')
    check('o USE casa sem caixa/underscore', called('new deals', 'NDF', '20260102'),
          'https://uat.example/api/v2/getTrades?date=20260102&product=NDF')
    check('o Unwinds tem endereco proprio', called('Unwinds', 'NDF', '20260102'),
          'https://uat.example/api/v2/getUnwinds?date=20260102&product=NDF')

    write_rows({'nao': 'e uma lista'})
    check('JSON invalido -> fallback', called('New Deals'), LEGACY)
finally:
    A.API_LINKS_FILE = orig_file
    for name in os.listdir(tmp):
        os.remove(os.path.join(tmp, name))
    os.rmdir(tmp)

print('\n== 4. upgrade do arquivo sem a coluna PRODUCT ==')
antigo = [{'USE': 'New Deals', 'URL': LEGACY.replace('20260728', 'YYYYMMDD'), 'NOTES': ''},
          {'USE': 'Unwinds', 'URL': '', 'NOTES': ''}]
up = R._api_links_upgrade([dict(r) for r in antigo])
check('a linha antiga vira a do NDF',
      [(r['USE'], r['PRODUCT']) for r in up[:2]], [('New Deals', 'NDF'), ('Unwinds', '')])
check('os produtos que faltavam entram',
      sorted(r['PRODUCT'] for r in up if r['USE'] == 'New Deals'),
      ['Commodities', 'FXO', 'NDF', 'Swaps'])
check('idempotente', len(R._api_links_upgrade(up)), len(up))

print('\n== 5. o mapping esta ligado na tela ==')
cols = [c['key'] for c in R._MAPPING_DEFS['api-links']['columns']]
check('colunas', cols, ['USE', 'PRODUCT', 'URL', 'NOTES'])
check('USE e um select com os usos cadastrados',
      R._MAPPING_DEFS['api-links']['columns'][0].get('options'),
      ['New Deals', 'Unwinds', 'Recon FXO'])
# Todo uso que aparece no seed tem de estar na lista do select — senao a linha
# existe no arquivo e nao ha como reeditá-la pela tela.
check('   e cobre todos os usos do seed',
      sorted({r['USE'] for r in R._API_LINKS_SEED}
             - set(R._MAPPING_DEFS['api-links']['columns'][0]['options'])), [])
check('PRODUCT lista os produtos da API',
      R._MAPPING_DEFS['api-links']['columns'][1].get('options'),
      ['', 'NDF', 'FXO', 'Commodities', 'Swaps'])
check('os produtos batem com os do cliente',
      sorted(p for p in R._MAP_API_PRODUCTS if p), sorted(A.PRODUCTS.values()))
check('os usos batem com as constantes do cliente',
      [A.USE_NEW_DEALS, A.USE_UNWINDS], ['New Deals', 'Unwinds'])
tpl = io.open('apps/templates/pages/mapping.html', encoding='utf-8').read()
check('no rail da tela', "key: 'api-links'" in tpl, True)
check('YYYYMMDD destacado como padrao', "'api-links':      { cols: ['URL']" in tpl, True)
for lang in ('en', 'br', 'es'):
    tr = json.load(io.open('apps/static/data/translations/%s.json' % lang, encoding='utf-8'))
    check('traducao %s' % lang, bool(tr.get('map-tab-api-links')), True)

print('\n%s' % ('TUDO OK' if not fails else 'FALHAS (%d): %r' % (len(fails), fails)))
sys.exit(1 if fails else 0)
