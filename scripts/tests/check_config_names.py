#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Protege o `_REQUIRED_CONFIG_NAMES` do `apps/__init__.py` (HANDOFF §308).

O `config.py` é o arquivo que fica para trás numa instância: é o único que se
ajusta à mão, e `git pull` não sobrescreve arquivo modificado. O checkout passa a
ter dois commits misturados, e uma chave que o código novo lê some do config
velho — a falha aparece como `AttributeError` vinte frames dentro de um import.

`create_app` confere a lista ANTES de importar os blueprints e recusa subir
dizendo o que falta. O que este teste guarda é a lista **não envelhecer**:

  1. todo `Config.<NOME>` do código existe mesmo no `Config`;
  2. todo `Config.<NOME>` lido no TOPO de um módulo de `apps/` (isto é, no
     import — que é o que derruba a subida) está em `_REQUIRED_CONFIG_NAMES`;
  3. a conferência aceita o config atual e recusa cada nome que falte, com a
     mensagem que diz o comando.

O item 2 é o que teria pego o `DATABASE_DIR`: ele nasceu lido no topo do
`manual_conf.py`, do `recon_comitente.py` e do `routes.py`.

Não toca em dado real: nada é aberto, nada é gravado.
"""

import ast
import io
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, REPO)

# O share tem de ser absoluto para o config importar fora do Windows (§8).
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(REPO, '.check-config-share'))

falhas = []


def check(cond, msg):
    print(('ok  ' if cond else 'FAIL ') + msg)
    if not cond:
        falhas.append(msg)


# ── as fontes ────────────────────────────────────────────────────────────────

from apps import _REQUIRED_CONFIG_NAMES, _require_config_names   # noqa: E402
from apps.config import Config                                    # noqa: E402


def arquivos_py(raiz):
    for base, dirs, nomes in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'node_modules', '.git')]
        for nome in nomes:
            if nome.endswith('.py'):
                yield os.path.join(base, nome)


def refs_config(caminho):
    """(nome, no_topo) para cada `Config.<NOME>` do arquivo.

    `no_topo` = lido no import do módulo (fora de def/class), que é o caso em que
    a ausência derruba a subida em vez de aparecer no primeiro request.
    """
    with open(caminho, encoding='utf-8') as fh:
        try:
            arvore = ast.parse(fh.read(), filename=caminho)
        except SyntaxError:
            return []

    dentro = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for filho in ast.walk(no):
                dentro.add(id(filho))

    saida = []
    for no in ast.walk(arvore):
        if (isinstance(no, ast.Attribute)
                and isinstance(no.value, ast.Name)
                and no.value.id == 'Config'):
            saida.append((no.attr, id(no) not in dentro))
    return saida


CONFIG_PY = os.path.join(REPO, 'apps', 'config.py')

# ── 1. todo Config.<NOME> do código existe no Config ─────────────────────────

desconhecidos = []
for caminho in list(arquivos_py(os.path.join(REPO, 'apps'))) + \
               list(arquivos_py(os.path.join(REPO, 'scripts'))):
    if os.path.abspath(caminho) == CONFIG_PY:
        continue
    for nome, _topo in refs_config(caminho):
        if not hasattr(Config, nome):
            desconhecidos.append('{}: Config.{}'.format(
                os.path.relpath(caminho, REPO), nome))

check(not desconhecidos,
      'todo Config.<NOME> do codigo existe no Config' +
      ('' if not desconhecidos else ' — ausentes: ' + '; '.join(desconhecidos)))

# ── 2. o que é lido no TOPO de um módulo de apps/ está na lista ──────────────

no_topo = {}
for caminho in arquivos_py(os.path.join(REPO, 'apps')):
    if os.path.abspath(caminho) == CONFIG_PY:
        continue
    for nome, topo in refs_config(caminho):
        if topo:
            no_topo.setdefault(nome, set()).add(os.path.relpath(caminho, REPO))

check(bool(no_topo), 'o teste achou leitura de Config no topo de algum modulo')

fora_da_lista = sorted(n for n in no_topo if n not in _REQUIRED_CONFIG_NAMES)
check(not fora_da_lista,
      'todo Config.<NOME> lido no import esta em _REQUIRED_CONFIG_NAMES' +
      ('' if not fora_da_lista else
       ' — falta(m): ' + '; '.join('{} ({})'.format(n, ', '.join(sorted(no_topo[n])))
                                   for n in fora_da_lista)))

# O DATABASE_DIR é o caso que originou a §308 — se ele deixar de ser lido no
# topo, o teste acima passaria por vacuidade e ninguém saberia.
check('DATABASE_DIR' in no_topo,
      'DATABASE_DIR continua sendo lido no import (o caso da §308)')

# ── 3. a conferência aceita o config atual e recusa o que falta ─────────────

atual = dict((n, getattr(Config, n)) for n in _REQUIRED_CONFIG_NAMES)
try:
    _require_config_names(atual)
    check(True, 'o config atual passa pela conferencia')
except RuntimeError as exc:
    check(False, 'o config atual passa pela conferencia — recusou: {}'.format(exc))

for nome in _REQUIRED_CONFIG_NAMES:
    velho = dict(atual)
    velho.pop(nome)
    try:
        _require_config_names(velho)
        check(False, 'config sem {} e recusado'.format(nome))
    except RuntimeError as exc:
        msg = str(exc)
        check(nome in msg and 'apps/config.py' in msg,
              'config sem {} e recusado e a mensagem nomeia o arquivo'.format(nome))

# A mensagem tem de dizer o que FAZER — sem isso ela é só um AttributeError com
# outro texto, e foi a ilegibilidade que custou a rodada de depuração.
try:
    _require_config_names({})
    check(False, 'config vazio e recusado')
except RuntimeError as exc:
    msg = str(exc)
    check('git checkout -- apps/config.py' in msg,
          'a mensagem traz o comando que conserta')
    check('Reinicie o Flask' in msg,
          'a mensagem lembra do restart (o reloader esta desligado)')
    check(all(n in msg for n in _REQUIRED_CONFIG_NAMES),
          'a mensagem lista TODOS os nomes que faltam de uma vez')

# ── 4. a lista não pode ter nome que o config não tem ───────────────────────

sem_config = [n for n in _REQUIRED_CONFIG_NAMES if not hasattr(Config, n)]
check(not sem_config,
      'todo nome de _REQUIRED_CONFIG_NAMES existe no config atual' +
      ('' if not sem_config else ' — ausentes: ' + ', '.join(sem_config)))

# ── 5. nenhuma raiz de rede escrita à mão em apps/ ──────────────────────────
#
# O `Config.SHARED_DRIVE_ROOT` só vale para quem pergunta a ele. Um
# `r"I:\Confirmation\..."` num módulo mantém AQUELE caminho na letra mapeada
# depois de a instância do JPM passar a falar com o UNC — e a falha aparece como
# "o arquivo do dia não chegou", não como erro de configuração. Foi o caso das
# três recons (FXO, Comitente e Pay/Rec).
#
# A varredura é sobre os literais do AST, então comentário e docstring ficam de
# fora por construção — o caminho citado em prosa continua permitido.

import re                                                          # noqa: E402
import subprocess                                                  # noqa: E402

RAIZ_RE = re.compile(r'^(?:[A-Za-z]:[\\/]|\\\\[A-Za-z0-9._-]+[\\/])')


def _docstrings(arvore):
    """Os nós de docstring — módulo, classe e função."""
    fora = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            corpo = getattr(no, 'body', None)
            if corpo and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant) \
               and isinstance(corpo[0].value.value, str):
                fora.add(id(corpo[0].value))
    return fora


def _versionados():
    """Só o que está no git: a árvore de trabalho tem cópias soltas (`routes 2.py`,
    `cotaçoes.py`) que não vão para instância nenhuma."""
    saida = subprocess.check_output(['git', 'ls-files', 'apps'], cwd=REPO)
    nomes = saida.decode('utf-8', 'replace').splitlines()
    return [os.path.join(REPO, n) for n in nomes if n.endswith('.py')]


try:
    alvos = _versionados()
except Exception as exc:                                            # pragma: no cover
    check(False, 'git ls-files respondeu (a varredura de raiz precisa dele): %s' % exc)
    alvos = []

# O config é o dono do literal: é lá que o bloco de ambiente mora.
alvos = [a for a in alvos if os.path.basename(a) != 'config.py']

achados = []
for caminho in alvos:
    try:
        arvore = ast.parse(io.open(caminho, encoding='utf-8').read())
    except Exception:
        continue
    fora = _docstrings(arvore)
    for no in ast.walk(arvore):
        if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in fora:
            if RAIZ_RE.match(no.value):
                achados.append('%s:%d  %r' % (os.path.relpath(caminho, REPO),
                                              no.lineno, no.value[:60]))

check(not achados,
      'nenhum modulo de apps/ escreve raiz de rede a mao' +
      ('' if not achados else ' — ' + '; '.join(achados[:6])))

print()
if falhas:
    print('{} falha(s)'.format(len(falhas)))
    sys.exit(1)
print('tudo ok')
