# -*- coding: utf-8 -*-
"""O catalogo de cards do New Deals Monitor — toda pasta que alguem GRAVA tem
card, e todo card tem lugar na tela (§454).

O Monitor nao recebe uma lista de produtos: ele VARRE o `cache/new deals/`
inteiro e agrupa pelos dois primeiros niveis do caminho. Quem diz que produto
existe e o `_NDM_CARDS`; o que sobra vira o card generico "e etc", que a tela
desenha no grupo *Others* do rodape.

Esse card generico e uma rede de seguranca — nada some do e-mail por falta de
cadastro — e por isso a falta de catalogo nao levanta erro nenhum. Ela apenas:

  * tira o link "Open page" (o card generico nasce com `url: None`);
  * tira o card da zona certa da tela (o *Others* fica no rodape, fora das
    colunas B3 / Confirmations / Intrag);
  * e, no e-mail diario de pendencias, classifica a linha como **Registration**,
    porque a chave `extra-...` nao comeca com `intrag-` — cobranca de Intrag
    misturada com registro na B3.

Foi o que aconteceu com as duas telas de DCE (`Intrag/DCE Option` e
`Intrag/DCE Swap`): elas gravam arquivo-dia no mesmo cache desde sempre, e
sempre apareceram no Monitor — no lugar errado. O `Intrag/Swap` tinha o defeito
irmao: sem card no servidor, o JS INVENTAVA um "Intrag Swap — In development"
zerado na zona Intrag, e o numero real aparecia ao lado, no *Others*: o mesmo
produto duas vezes na mesma tela.

O que este teste prende:

  1. **paridade de pastas**: todo `*_CACHE_DIR` do Intrag que mora sob o
     `NEW_DEALS_CACHE_ROOT` e reivindicado por um card;
  2. **paridade de caminho**: todo `dirs` de card de Intrag aponta para uma
     pasta que a vertical realmente grava (o rotulo de tela nunca vira caminho);
  3. **taxonomia**: todo card tem entrada no `_NDM_TAXONOMY`, senao o e-mail
     quebra o LABEL em duas palavras e chama isso de produto;
  4. **zona**: card de Intrag tem chave com prefixo `intrag-`, que e o unico
     teste que o e-mail faz para separar a zona;
  5. **a tela**: toda chave `intrag-*` do servidor esta num grupo do
     `GROUPS` do template — chave fora dele cai no *Others* de novo, agora por
     esquecimento do front;
  6. **o front nao inventa card**: nenhum placeholder fabricado no JS.
  7. **o link**: card com pagina aponta para uma rota que existe;
  8. **swap se divide pela LOB** (21/09/2026): so existem os cards Swap
     Equities e Swap CEM, e a LINHA cai num ou noutro pela coluna LOB, venha
     da pagina que vier (Bullet, Cashflow, recompra). LOB que nao diz o card
     NAO e chutada: vira o generico `... No LOB` no Others.
"""
import io, os, re, sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages import routes as R                                     # noqa: E402
from apps.pages.features.deals_monitor import domain as D              # noqa: E402
from apps.pages.features.intrag.infra import persistence as IP         # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def pkey(path):
    """A chave de produto que o Monitor deriva de um caminho — os dois
    primeiros niveis nao-numericos abaixo da raiz do cache (`queries.py`)."""
    rel = os.path.relpath(path, R.NEW_DEALS_CACHE_ROOT).replace('\\', '/')
    return '/'.join([p for p in rel.split('/') if not p.isdigit()][:2])


CARD_DIRS = {d for c in D._NDM_CARDS for d in c['dirs']}

print('== 1. toda pasta que o Intrag GRAVA tem card ==')
# As constantes da propria vertical, nao uma lista repetida aqui: pasta nova
# aparece neste teste no mesmo instante em que passa a existir.
gravadas = {}
for nome in sorted(dir(IP)):
    if not nome.endswith('_CACHE_DIR'):
        continue
    caminho = getattr(IP, nome)
    if not str(caminho).startswith(R.NEW_DEALS_CACHE_ROOT):
        continue
    gravadas[nome] = pkey(caminho)
check('as constantes de cache da vertical foram encontradas', bool(gravadas), True)
for nome, k in sorted(gravadas.items()):
    check('%-28s -> %-20s tem card' % (nome, k), k in CARD_DIRS, True)

print('\n== 2. o `dirs` do card e a pasta REAL, nunca o rotulo de tela ==')
# `NDF/FWD Start` (com espaco) ja morou no catalogo como se fosse "a outra
# grafia em producao": nunca foi, e diretorio inexistente casa com nada.
intrag_dirs = {d for d in CARD_DIRS if d.startswith('Intrag/')}
check('nenhuma pasta de Intrag no catalogo fora do que a vertical grava',
      sorted(intrag_dirs - set(gravadas.values())), [])

print('\n== 3. todo card tem taxonomia (o e-mail nao adivinha pelo label) ==')
chaves = [c['key'] for c in D._NDM_CARDS]
check('nenhuma chave duplicada no catalogo', len(chaves), len(set(chaves)))
check('nenhum card sem entrada no _NDM_TAXONOMY',
      sorted(set(chaves) - set(D._NDM_TAXONOMY)), [])
check('nenhuma taxonomia orfa (card que deixou de existir)',
      sorted(set(D._NDM_TAXONOMY) - set(chaves)), [])

print('\n== 4. a zona do e-mail sai do PREFIXO da chave ==')
for c in D._NDM_CARDS:
    if not any(d.startswith('Intrag/') for d in c['dirs']):
        continue
    check('   %-20s cai na zona Intrag' % c['key'], c['key'].startswith('intrag-'), True)

print('\n== 5. a tela desenha todo card de Intrag na zona Intrag ==')
TPL = io.open(os.path.join(ROOT, 'apps', 'templates', 'pages', 'new-deals-monitor.html'),
              encoding='utf-8').read()
no_front = set(re.findall(r"intrag:\s*\[([^\]]*)\]", TPL))
no_front = {k.strip().strip("'\"") for bloco in no_front for k in bloco.split(',') if k.strip()}
check('o GROUPS do template foi lido', bool(no_front), True)
for c in D._NDM_CARDS:
    if c['key'].startswith('intrag-'):
        check('   %-20s esta num grupo do GROUPS' % c['key'], c['key'] in no_front, True)
check('e o front nao lista card que o servidor nao tem',
      sorted(no_front - set(chaves)), [])

print('\n== 6. o front nao INVENTA card ==')
# O `byKey['intrag-swap'] = {...}` fabricado no JS era o que fazia o mesmo
# produto aparecer duas vezes: zerado na zona Intrag e com o numero no Others.
check('nenhum card fabricado no JS', re.search(r"byKey\[[^\]]+\]\s*=\s*\{", TPL) is None, True)

print('\n== 7. card com pagina aponta para uma ROTA que existe ==')
# Pelo `url_map`, e nao pelo nome do arquivo: o teste antigo montava
# `pages/<url>.html`, que so vale para as paginas do CATCH-ALL. Pagina com
# rota propria — a URL de tres segmentos da recompra, `/unwinds/ndf/fx` —
# reprovava com o template ao lado, e a saida era renomear o arquivo para uma
# convencao que a rota nao segue. A pergunta de verdade e se o link do card
# leva a algum lugar, e quem responde isso e o `url_map`.
from run import app                                                    # noqa: E402
_rotas = {str(r.rule) for r in app.url_map.iter_rules()}
check('o url_map foi lido', len(_rotas) > 50, True)
for c in D._NDM_CARDS:
    if not c.get('url'):
        continue
    alvo = str(c['url'])
    # O catch-all `/<template>` atende qualquer nome de um segmento so, entao
    # nele o que se confere continua sendo o ARQUIVO.
    # Mas a rota ESTATICA de um segmento vence o catch-all (as paginas do
    # catalogo de New Deals, `/new_deals-swap-cashflow`, usam um template so):
    # ali quem responde e o `url_map`, e o arquivo com o nome da URL nao existe.
    if alvo in _rotas:
        check('   %-20s -> rota %s' % (c['key'], alvo), True, True)
    elif alvo.count('/') == 1 and '/<template>' in _rotas:
        existe = os.path.isfile(os.path.join(
            ROOT, 'apps', 'templates', 'pages', alvo.lstrip('/') + '.html'))
        check('   %-20s -> pages%s.html (catch-all)' % (c['key'], alvo), existe, True)
    else:
        check('   %-20s -> rota %s' % (c['key'], alvo), alvo in _rotas, True)

print('\n== 8. swap: dois cards, e a LOB da linha decide ==')
import json, tempfile                                                  # noqa: E402
from datetime import datetime                                          # noqa: E402
from apps.pages.features.deals_monitor import queries as Q             # noqa: E402

check('o card Swap Bullet deixou de existir', 'swap-bullet' in chaves, False)
swap_cards = [c for c in D._NDM_CARDS if c.get('lob')]
check('os cards com LOB sao Swap Equities (EDG) e Swap CEM (CEM)',
      sorted((c['key'], c['lob']) for c in swap_cards),
      [('swap-cem', 'CEM'), ('swap-equities', 'EDG')])
check('os dois leem as MESMAS pastas (quem separa e a LOB)',
      len({c['dirs'] for c in swap_cards}), 1)
for pasta in ('Swap/Bullet', 'Swap/Cashflow',
              D.PREFIXO_UNWIND + 'Swap/EDG', D.PREFIXO_UNWIND + 'Swap/CEM'):
    check('   %-22s esta entre elas' % pasta, pasta in swap_cards[0]['dirs'], True)
check('o GROUPS da tela tem so os dois',
      re.search(r"b3:\s*\['swap-equities',\s*'swap-cem'\]", TPL) is not None, True)
check('a LOB e lida sem caixa nem pontuacao',
      [D._ndm_bucket('Swap/Bullet', {'LOB': v}) for v in ('edg', ' C.E.M ', 'EDG')],
      ['Swap/Bullet#EDG', 'Swap/Bullet#CEM', 'Swap/Bullet#EDG'])
check('LOB vazia ou desconhecida NAO e chutada',
      [D._ndm_bucket('Swap/Bullet', {'LOB': v}) for v in ('', 'RATES')],
      ['Swap/Bullet/No LOB'] * 2)
check('pasta que nao e de swap nao olha a LOB',
      D._ndm_bucket('NDF/Vanilla', {'LOB': 'CEM'}), 'NDF/Vanilla')

# O snapshot de verdade, numa arvore em tmp (caminho fora do DATA_DIR e disco).
tmp = tempfile.mkdtemp(prefix='otc-ndm-')
R.NEW_DEALS_CACHE_ROOT = os.path.join(tmp, 'new deals')
Q.unwinds_cache_root = lambda: os.path.join(tmp, 'unwinds')


def _dia(raiz, pasta, nome, linhas):
    d = os.path.join(raiz, *(pasta.split('/') + ['2026', '09']))
    os.makedirs(d)
    with io.open(os.path.join(d, nome), 'w', encoding='utf-8') as fh:
        json.dump(linhas, fh)


_dia(R.NEW_DEALS_CACHE_ROOT, 'Swap/Bullet', '20260921_swapbullet.json', [
    {'_id': 'a', 'LOB': 'EDG', 'Status': 'New', 'Client': 'Safra'},
    {'_id': 'b', 'LOB': 'EDG', 'Status': 'Success', 'Client': 'Atacama'},
    {'_id': 'c', 'LOB': 'CEM', 'Status': 'New', 'Client': 'Vale'},
    {'_id': 'd', 'LOB': '', 'Status': 'New', 'Client': 'Sem Mesa'},
    {'_id': 'e', 'LOB': 'CEM', 'Status': 'Canceled', 'Client': 'Fora'}])
_dia(R.NEW_DEALS_CACHE_ROOT, 'Swap/Cashflow', '20260921_swapcashflow.json', [
    {'_id': 'f', 'LOB': 'CEM', 'Status': 'Pending', 'Client': 'Petrobras'},
    {'_id': 'g', 'LOB': 'EDG', 'Status': 'New', 'Client': 'Itau'}])
_dia(Q.unwinds_cache_root(), 'Swap/CEM', '20260921_unwindswapcem.json', [
    {'_id': 'h', 'LOB': 'EDG', 'Status': 'Imported', 'Client': 'Trocada'},
    {'_id': 'i', 'LOB': 'CEM', 'Status': 'Imported', 'Client': 'Certa'}])

with app.test_request_context():
    cards, _conf = Q._ndm_monitor_snapshot(datetime(2026, 9, 21))
por = {c['key']: c for c in cards}
check('Swap Equities soma as EDG das TRES paginas', por['swap-equities']['total'], 4)
check('   com os status de cada uma', por['swap-equities']['statuses'],
      {'New': 2, 'Success': 1, 'Imported': 1})
check('   e a perna da Atacama como ATA',
      por['swap-equities']['les'], [{'le': 'JPM', 'count': 3}, {'le': 'ATA', 'count': 1}])
check('Swap CEM soma as CEM (cancelada fora)', por['swap-cem']['total'], 3)
check('   a recompra gravada na pagina CEM com LOB EDG foi para Equities',
      por['swap-cem']['statuses'], {'New': 1, 'Pending': 1, 'Imported': 1})
check('os dois cards abrem uma pagina',
      (por['swap-equities']['url'], por['swap-cem']['url']),
      ('/new_deals-swap-bullet', '/new_deals-swap-cashflow'))
extras = {c['key']: c for c in cards if c['key'].startswith('extra-')}
check('a linha sem LOB aparece no Others, com nome que diz o que falta',
      [(k, c['label'], c['total']) for k, c in extras.items() if 'swap' in k],
      [('extra-swap-bullet-no-lob', 'Swap Bullet No LOB', 1)])
check('nenhuma operacao sumiu: 9 linhas validas = 4 + 3 + 1 + a cancelada',
      por['swap-equities']['total'] + por['swap-cem']['total'] + 1, 8)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
