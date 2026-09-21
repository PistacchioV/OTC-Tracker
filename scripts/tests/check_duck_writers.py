# -*- coding: utf-8 -*-
"""check_duck_writers.py — dado ENTRA e SAI pelo funil, e o funil fala com o BANCO.

A auditoria da migração (HANDOFF §335) achou a classe inteira: ~30 escritores
gravavam JSON do DATA_DIR com `json.dump` direto, fora do funil
`_atomic_write_json` — a leitura não quebrava (o contrato de frescor cai no
JSON), mas os BANCOS ficavam defasados em silêncio para quem os consulta por
fora, até a próxima carga completa. Todos foram migrados para o funil (que é
atômico e avisa o espelho); este script impede o próximo de nascer.

A regra (§434, DB-only): escrita e leitura de dado são só nos DuckDB.

  · **ESCRITA** — `json.dump(` só existe em `apps/pages` dentro da allowlist:
    o armazém (`data_store`), que grava o que NÃO vive no banco. Qualquer outro
    site é reprovado apontando arquivo e linha; o caminho certo é o
    `_atomic_write_json`.
  · **LEITURA** — `json.load(` segue a mesma disciplina, e até 21/09/2026 NÃO
    tinha guarda nenhuma. A varredura mecânica do §434 trocou os ~110 leitores
    por `data_store.read`, mas nada impedia o próximo de nascer — e a leitura
    crua é a MAIS traiçoeira das duas: `json.load(data_path('X.json'))` devolve
    a SEED DO REPOSITÓRIO e ignora o que a mesa editou pela tela. A página
    abre, a API responde 200, e o cadastro mostra o valor de fábrica. Nada
    nisso parece defeito, e foi o que o §488 documenta no File Interpreter.

As duas varreduras usam o MESMO percorredor de propósito: escritas com uma
regra e leituras com outra divergiriam no primeiro arquivo que uma pula e a
outra não.
"""
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

# Sobras não versionadas que o CLAUDE.md §11 manda nunca commitar. Elas existem
# na árvore de quem desenvolve e não são código do app — `routes 2.py` sozinho
# tem 75 `json.load` de antes da migração.
IGNORADOS = {'routes 2.py', 'cotaçoes.py'}

# ── ESCRITA: quem PODE conter json.dump, e o que o arquivo tem de conter junto.
ALLOW = {
    # O escritor atômico do que NÃO vive no banco mora no armazém (§434).
    os.path.join('apps', 'pages', 'data_store.py'): 'def write(',
}

# ── LEITURA: quem PODE conter json.load.
#
# As quatro entradas têm a MESMA natureza — elas leem a origem empacotada ou
# legada para COLOCAR o dado no banco, ou são o próprio armazém. Nenhuma delas
# serve dado à tela a partir do disco, que é o que a regra proíbe.
ALLOW_LEITURA = {
    # A queda para o JSON legado em disco é o armazém em pessoa (§442).
    os.path.join('apps', 'pages', 'data_store.py'): 'def _read_fs(',
    # O motor de conversão JSON → DuckDB: ler JSON é o trabalho dele.
    os.path.join('apps', 'pages', 'json_to_duckdb.py'): 'def _load_json(',
    # A semeadura da subida lê a cópia DO REPOSITÓRIO para importar (§434).
    os.path.join('apps', '__init__.py'): 'def _seed_data_dir(',
    # Leva ao banco o template corrigido no repositório (§488) — sem ele o
    # motor segue lendo o layout velho e o arquivo vai errado para a B3. O
    # marcador é o `_origem()`: é ele que aponta para a cópia DO REPOSITÓRIO,
    # e é isso que torna a leitura crua legítima aqui. O que o script grava vai
    # pelo funil (`_atomic_write_json`), como todo o resto.
    os.path.join('scripts', 'import_file_interpreter_template.py'): 'def _origem(',
}

fails = []


def check(label, ok, detalhe=''):
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        ' + detalhe))
    if not ok:
        fails.append(label)


def varre(alvos, padrao, allow, remedio):
    """Acha `padrao` fora da `allow`. Devolve a lista de reprovações.

    `alvos` são pares (raiz, recursivo?) — `apps/pages` desce a árvore inteira,
    `scripts/` fica no primeiro nível de propósito: `scripts/tests/` são os
    guardas (leem JSON à vontade, é o trabalho deles) e `scripts/standalone/` e
    `scripts/convert/` são GERADOS pelo `build_duckdb_standalone.py`, cópias do
    motor de conversão para máquina sem o código.
    """
    achados = []
    for raiz, recursivo in alvos:
        base = os.path.join(ROOT, raiz)
        if os.path.isfile(base):
            arquivos = [base]
        else:
            arquivos = []
            for dirpath, dirs, files in os.walk(base):
                dirs[:] = [] if not recursivo else [d for d in dirs if d != '__pycache__']
                arquivos += [os.path.join(dirpath, f) for f in files]
        for full in arquivos:
            fname = os.path.basename(full)
            if not fname.endswith('.py') or fname in IGNORADOS:
                continue
            rel = os.path.relpath(full, ROOT)
            with open(full, encoding='utf-8') as fh:
                texto = fh.read()
            hits = [i + 1 for i, ln in enumerate(texto.splitlines())
                    if re.search(padrao, ln)]
            if not hits:
                continue
            if rel in allow:
                exigido = allow[rel]
                # O marcador não é burocracia: ele prende a permissão à FUNÇÃO
                # que a justifica. Movida ela para outro lugar, a permissão
                # deixa de valer aqui em vez de virar uma licença permanente
                # para o arquivo inteiro.
                if exigido and exigido not in texto:
                    achados.append('%s: permitido, mas sem %r — a permissão era '
                                   'para essa função' % (rel, exigido))
            else:
                achados.append('%s:%s: %s' % (rel, ','.join(map(str, hits)), remedio))
    return achados


print('== ESCRITA: json.dump só dentro do funil ==')
achados = varre([(os.path.join('apps', 'pages'), True)],
                r'\bjson\.dump\(', ALLOW,
                'json.dump fora do funil — use _atomic_write_json')
check('nenhum json.dump fora do funil em apps/pages', not achados,
      '\n        '.join(achados))

# E o funil de fato grava no ARMAZÉM (DB-only, §434): nenhum JSON é escrito.
funil = open(os.path.join(ROOT, 'apps', 'pages', 'platform', 'json_cache.py'),
             encoding='utf-8').read()
check('o funil delega ao armazém (data_store.write) e não grava JSON',
      'data_store.write(file_path, data)' in funil and 'json.dump(' not in funil)

print('\n== LEITURA: json.load só no armazém e em quem ALIMENTA o banco ==')
# `json.loads(` fica de FORA da varredura: ele opera sobre TEXTO já em mãos
# (o corpo de uma resposta HTTP, uma coluna do banco), e não abre arquivo
# nenhum. Proibi-lo pegaria dezenas de usos legítimos e ensinaria a contornar
# o guarda, que é pior do que não ter guarda. Quem lê ARQUIVO é o `json.load(`.
achados_r = varre([(os.path.join('apps', 'pages'), True),
                   (os.path.join('apps', '__init__.py'), False),
                   ('scripts', False)],
                  r'\bjson\.load\(', ALLOW_LEITURA,
                  'json.load fora do armazém — dado se lê por data_store.read '
                  '(um json.load num caminho do DATA_DIR devolve a SEED do '
                  'repositório e ignora o que a mesa editou)')
check('nenhum json.load de dado fora do armazém', not achados_r,
      '\n        '.join(achados_r))

# A allowlist não pode virar gaveta: cada entrada tem de existir de verdade.
# Arquivo renomeado deixaria uma permissão pendurada num caminho que não existe
# — e a próxima leitura crua nascida ali passaria batida.
mortas = [rel for rel in list(ALLOW) + list(ALLOW_LEITURA)
          if not os.path.exists(os.path.join(ROOT, rel))]
check('nenhuma entrada da allowlist aponta para arquivo que não existe',
      not mortas, ', '.join(mortas))

print()
print(('FAIL: %d' % len(fails)) if fails else 'TUDO OK')
sys.exit(1 if fails else 0)
