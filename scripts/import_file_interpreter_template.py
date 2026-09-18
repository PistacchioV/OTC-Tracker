#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Leva ao BANCO um template do File Interpreter corrigido no repositorio.

Por que este script existe: o `.json` versionado e a SEED, e a semeadura da
subida NAO sobrescreve o que o banco ja tem (§434) — o que esta la e o que a
mesa editou na tela. Entao um template corrigido por um commit chega ao
repositorio e o motor continua lendo o antigo, sem erro nenhum: o arquivo
para a B3 sai com o layout velho e nada acusa.

Por seguranca, um template cujo banco ja tem `source` preenchido em algum
campo e considerado EDITADO e fica de fora, a menos que se passe `--force`.
Template de biblioteca (todo `source` em branco) entra sem perguntar.

    python scripts/import_file_interpreter_template.py --dry-run
    python scripts/import_file_interpreter_template.py --key antecipacao-termo-multiclasses
    python scripts/import_file_interpreter_template.py --key <chave> --force

Idempotente: rodar de novo sobre um banco ja atualizado nao muda nada.
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

SUBDIR = 'file-interpreter'


def _origem(key):
    """O JSON versionado no repositorio (a seed), lido do DISCO."""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'apps', 'static', 'data', SUBDIR, key + '.json')


def _tem_source(tpl):
    return any(str(f.get('source') or '').strip()
               for b in (tpl or {}).get('blocks') or []
               for f in b.get('fields') or [])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--key', action='append', default=[],
                    help='chave do template (repetivel). Sem isto, todos os do repositorio.')
    ap.add_argument('--force', action='store_true',
                    help='sobrescreve tambem o template que o banco tem EDITADO')
    ap.add_argument('--dry-run', action='store_true', help='so diz o que faria')
    args = ap.parse_args()

    from run import app                                    # noqa: E402
    from apps.pages import routes as R                     # noqa: E402
    from apps.pages.data_paths import data_write           # noqa: E402

    raiz = os.path.dirname(_origem('x'))
    chaves = args.key or sorted(
        os.path.splitext(n)[0] for n in os.listdir(raiz) if n.endswith('.json'))

    gravados, pulados, ausentes = [], [], []
    with app.app_context():
        for key in chaves:
            src = _origem(key)
            if not os.path.isfile(src):
                ausentes.append(key)
                continue
            novo = json.load(io.open(src, encoding='utf-8'))
            R._fi_tpl_cache.clear()
            atual = R._fi_tpl_cached(key)
            if atual == novo:
                continue                                   # ja igual: nada a fazer
            if atual is not None and _tem_source(atual) and not args.force:
                pulados.append(key)
                continue
            if not args.dry_run:
                R._atomic_write_json(data_write(SUBDIR, key + '.json'), novo)
            gravados.append(key)
        R._fi_tpl_cache.clear()

    prefixo = '[dry-run] ' if args.dry_run else ''
    for k in gravados:
        print('%s%-45s atualizado no banco' % (prefixo, k))
    for k in pulados:
        print('  PULADO  %-43s o banco tem este template EDITADO (use --force)' % k)
    for k in ausentes:
        print('  AUSENTE %-43s nao existe no repositorio' % k)
    if not gravados and not pulados and not ausentes:
        print('nada a fazer: o banco ja esta igual ao repositorio')
    return 1 if ausentes else 0


if __name__ == '__main__':
    sys.exit(main())
