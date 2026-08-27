# -*- coding: utf-8 -*-
"""O cache de leitura dos JSON do dia (`apps/pages/request_cache.py`).

Ele guarda o resultado dos loaders por REQUEST e por um TTL curto entre
requests. Duas coisas nele não dão erro nenhum quando quebram, e são as que
este script protege:

- **quem grava tem de invalidar.** Os savers do OTM e do Latam escrevem DIRETO
  (`json.dump`), sem passar pelo `_atomic_write_json` que é o funil dos outros
  74 pontos de gravação — sem o `bump_cache_gen` neles, a pessoa edita a linha,
  a tela recarrega e mostra o valor de antes;
- **quem carrega para MUTAR não pode receber o objeto do cache.** Os treze
  endpoints de add/edit/delete fazem `data.remove(rec)` / `rec[c] = ...` e só
  então gravam. Com a lista do cache na mão, a mutação vale para todo mundo
  antes do save — e continua valendo se o save FALHAR.
"""

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)

falhas = []


def ok(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond:
        falhas.append(msg)


# ── 1. o módulo em si ───────────────────────────────────────────────────────
from apps.pages import request_cache as rc            # noqa: E402

ok(rc.SHARED_CACHE_TTL_SECONDS > 0, 'TTL do cache compartilhado é positivo')

chamadas = []


@rc.req_cached
def carrega(ref):
    chamadas.append(ref)
    return ['linha']


import datetime                                        # noqa: E402
d = datetime.date(2026, 8, 24)
carrega(d), carrega(d)
ok(len(chamadas) == 1, 'segunda leitura do mesmo dia vem do cache')

rc.bump_cache_gen(os.path.join('x', 'otm-settlements_20260824.json'))
carrega(d)
ok(len(chamadas) == 2, 'gravação do dia invalida a leitura (bump_cache_gen)')

antes = len(chamadas)
rc.bump_cache_gen(os.path.join('x', 'sem-data.json'))
carrega(d)
ok(len(chamadas) == antes, 'arquivo sem AAAAMMDD no nome não invalida nada')

# ── 2. o routes: os sete decorados, e o que cada um exige ───────────────────
import ast                                             # noqa: E402
import io                                              # noqa: E402
import re                                              # noqa: E402

# As telas de OTM e Latam moram em features/ desde a extracao — os entrypoints
# entram na mesma arvore (os endpoints mutantes estao la, chamando o store do
# routes por _R()).
fonte = io.open(os.path.join(RAIZ, 'apps', 'pages', 'routes.py'), encoding='utf-8').read()
# A família de liquidação mora em platform/settlement.py (§316) — dois dos
# sete decorados (`_ops_swap_pos_terms`, `_ops_equity_link`) vivem lá.
for _rel in ('platform/settlement.py',
             'features/otm/entrypoint.py', 'features/latam/entrypoint.py',
             'features/cognos/entrypoint.py', 'features/operations_b3/entrypoint.py',
             'features/ndf_summary/entrypoint.py', 'features/other_products/entrypoint.py'):
    fonte += io.open(os.path.join(RAIZ, 'apps', 'pages', _rel), encoding='utf-8').read()
arvore = ast.parse(fonte)
linhas = fonte.split('\n')

decorados = set()
corpo = {}
for n in ast.walk(arvore):
    if not isinstance(n, ast.FunctionDef):
        continue
    corpo[n.name] = '\n'.join(linhas[n.lineno - 1:n.end_lineno])
    for dec in n.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == '_req_cached':
            decorados.add(n.name)

ESPERADOS = {'_opb3_settle_rows', '_ops_swap_pos_terms', '_ops_equity_link',
             '_otm_load_cached', '_ndfadv_otm_by_suffix', '_latam_load_cached',
             '_opb3_load_cached'}
ok(decorados == ESPERADOS,
   'os sete loaders decorados com @_req_cached (falta=%s sobra=%s)'
   % (sorted(ESPERADOS - decorados) or '-', sorted(decorados - ESPERADOS) or '-'))

# ── 3. todo save que escapa do funil invalida por conta própria ─────────────
# `_atomic_write_json` cobre os 74 pontos que passam por ele. Estes dois não
# passam: escrevem com `json.dump` direto.
for saver in ('_otm_save', '_latam_save'):
    ok('_bump_cache_gen(' in corpo.get(saver, ''),
       '%s invalida o cache (não passa pelo _atomic_write_json)' % saver)

# O funil mora na platform/ desde a fatia `platform/json_cache.py` — a
# asserção acompanha o código (era em `corpo`, do routes.py).
_jcache_src = io.open(os.path.join(RAIZ, 'apps', 'pages', 'platform', 'json_cache.py'),
                      encoding='utf-8').read()
_jcache_fn = _jcache_src.split('def _atomic_write_json', 1)[1].split('\ndef ', 1)[0]
ok('_bump_cache_gen(file_path)' in _jcache_fn,
   '_atomic_write_json invalida o cache — o funil dos demais gravadores')

# E NENHUM outro gravador direto pode aparecer sem invalidar. A varredura é
# por AST sobre quem monta o caminho de um arquivo-dia decorado
# (`_otm_json_path`, `_latam_json_path`, `_opb3_json_path`) e grava com
# `json.dump` — foi assim que as três rotinas de importação (`_ds_write`,
# `_otm_import`, `_opb3_side_write`) apareceram: elas gravam o dia e a tela
# seguia lendo o de antes.
CAMINHO_DIA = re.compile(r'_(otm|latam|opb3)_json_path\(')
faltantes = []
for n in ast.walk(arvore):
    if not isinstance(n, ast.FunctionDef):
        continue
    seg = corpo[n.name]
    if 'json.dump(' not in seg or not CAMINHO_DIA.search(seg):
        continue
    if ('_bump_cache_gen(' in seg or '_atomic_write_json' in seg
            or re.search(r'\b(_otm_save|_latam_save|_ds_write)\(', seg)):
        continue
    faltantes.append(n.name)
ok(not faltantes,
   'todo gravador de arquivo-dia decorado invalida o cache (sem bump: %s)'
   % (', '.join(faltantes) or '-'))

# ── 4. quem carrega para mutar recebe CÓPIA ────────────────────────────────
for pub in ('_otm_load', '_latam_load', '_opb3_load'):
    seg = corpo.get(pub, '')
    ok('[dict(r) for r in data]' in seg and ('%s_cached(' % pub) in seg,
       '%s devolve cópia dos registros, não a lista do cache' % pub)
    ok('@_req_cached' not in seg, '%s (o público) NÃO é o decorado' % pub)

# O ponto que a cópia protege: os endpoints que mutam e depois gravam.
MUTANTES = [n.name for n in ast.walk(arvore)
            if isinstance(n, ast.FunctionDef)
            and re.search(r'\b(_otm_load|_latam_load|_opb3_load)\(', corpo[n.name])
            and re.search(r'\b(_otm_save|_latam_save)\(', corpo[n.name])]
ok(len(MUTANTES) >= 13,
   'os %d endpoints que carregam-mutam-gravam seguem existindo' % len(MUTANTES))
for m in MUTANTES:
    ok(not re.search(r'_(otm|latam|opb3)_load_cached\(', corpo[m]),
       '%s carrega pelo público (cópia), nunca pelo cacheado' % m)

# ── 5. a cópia é de verdade: mutar o resultado não contamina a leitura ──────
disco = [{'Trade Id': 'A', '_ot_status': 'Pending'}]


@rc.req_cached
def _load_cached(ref):
    return 'jp', disco


def _load(ref):
    jp, data = _load_cached(ref)
    return jp, (None if data is None else [dict(r) for r in data])


_, d1 = _load(d)
d1.pop()                                     # o delete que falha antes do save
d1_ = d1
_, d2 = _load(d)
ok(len(d2) == 1, 'remoção não gravada não vaza para a leitura seguinte')
_, d3 = _load(d)
d3[0]['_ot_status'] = 'OK'
_, d4 = _load(d)
ok(d4[0]['_ot_status'] == 'Pending', 'edição não gravada não vaza para a leitura seguinte')

print('')
print('FALHAS: %d' % len(falhas))
sys.exit(1 if falhas else 0)
