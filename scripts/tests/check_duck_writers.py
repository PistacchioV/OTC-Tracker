# -*- coding: utf-8 -*-
"""check_duck_writers.py — TODA gravação de dado passa pelo funil, e o funil grava no BANCO.

A auditoria da migração (HANDOFF §335) achou a classe inteira: ~30 escritores
gravavam JSON do DATA_DIR com `json.dump` direto, fora do funil
`_atomic_write_json` — a leitura não quebrava (o contrato de frescor cai no
JSON), mas os BANCOS ficavam defasados em silêncio para quem os consulta por
fora, até a próxima carga completa. Todos foram migrados para o funil (que é
atômico e avisa o espelho); este script impede o próximo de nascer.

A regra (§434, DB-only): `json.dump(` só pode existir em apps/pages dentro
da ALLOWLIST — o armazém (`data_store`), que é quem grava o que NÃO vive no
banco. Qualquer outro site é reprovado apontando arquivo e linha: o caminho
certo é `_atomic_write_json` (routes/`_R()`/`_routes()`), que grava no banco.
"""
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

# Quem PODE conter json.dump — e o que o arquivo tem de conter junto.
ALLOW = {
    # O escritor atômico do que NÃO vive no banco mora no armazém (§434).
    os.path.join('apps', 'pages', 'data_store.py'): 'def write(',
}

fails = []


def check(label, ok, detalhe=''):
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        ' + detalhe))
    if not ok:
        fails.append(label)


achados = []
raiz = os.path.join(ROOT, 'apps', 'pages')
for dirpath, dirs, files in os.walk(raiz):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for fname in files:
        if not fname.endswith('.py') or fname == 'routes 2.py':
            continue
        full = os.path.join(dirpath, fname)
        rel = os.path.relpath(full, ROOT)
        with open(full, encoding='utf-8') as fh:
            texto = fh.read()
        hits = [i + 1 for i, ln in enumerate(texto.splitlines())
                if re.search(r'\bjson\.dump\(', ln)]
        if not hits:
            continue
        chave = os.path.relpath(full, ROOT)
        if chave in ALLOW:
            exigido = ALLOW[chave]
            if exigido and exigido not in texto:
                achados.append('%s: permitido gravar, mas SEM o aviso ao espelho (%s)'
                               % (rel, exigido))
        else:
            achados.append('%s:%s: json.dump fora do funil — use _atomic_write_json'
                           % (rel, ','.join(map(str, hits))))

check('nenhum json.dump fora do funil em apps/pages', not achados,
      '\n        '.join(achados))

# E o funil de fato grava no ARMAZÉM (DB-only, §434): nenhum JSON é escrito.
funil = open(os.path.join(ROOT, 'apps', 'pages', 'platform', 'json_cache.py'),
             encoding='utf-8').read()
check('o funil delega ao armazém (data_store.write) e não grava JSON',
      'data_store.write(file_path, data)' in funil and 'json.dump(' not in funil)

print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
