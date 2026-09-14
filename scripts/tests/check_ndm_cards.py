# -*- coding: utf-8 -*-
"""O catalogo de cards do New Deals Monitor — toda pasta que alguem GRAVA tem
card, e todo card tem lugar na tela.

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

print('\n== 7. card com pagina aponta para um template que existe ==')
paginas = os.path.join(ROOT, 'apps', 'templates', 'pages')
for c in D._NDM_CARDS:
    if not c.get('url'):
        continue
    alvo = c['url'].lstrip('/')
    check('   %-20s -> %s.html' % (c['key'], alvo),
          os.path.isfile(os.path.join(paginas, alvo + '.html')), True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
