#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""convert 01_cadastros — os cadastros sem pasta própria.

Feriados, RefData/CounterpartyDetails e os JSONs da raiz.

Versão AUTOCONTIDA: roda em QUALQUER máquina, sem o código do OTC Tracker por
perto — com o `_motor.py` desta pasta ao lado (copie a pasta inteira).
Requisito único:  pip install duckdb

    Origem : o static\data do share — o UNC
             (\\Nawest.ad.jpmorganchase.com\lac\BRA\intra\...) ou a letra I:,
             o que existir na máquina. `--data-dir` manda em qualquer caso.
    Destino: ...\static\data\db   (a pasta db dentro da origem)

Uso:
    python 01_cadastros.py
    python 01_cadastros.py --dry-run
    python 01_cadastros.py --data-dir "D:\outra\pasta" --out-dir "D:\saida"

O ESCOPO são os cadastros SEM pasta própria ao lado deste script:

  - holiday_calendars.db  uma tabela por calendário do registro (+ _registry);
  - reference_data.db     refdata e counterparty_details, TUDO VARCHAR (o zero à
                          esquerda de SPN/ECI/TAX ID é o que um BIGINT perderia
                          em silêncio) + a coluna _raw com o registro exato;
  - <arquivo>.db          os JSONs da RAIZ do DATA_DIR (Subjacente, Dominio, …).

As pastas com muitos arquivos saíram para fatias próprias — 01_1 em diante:

  - mappings
  - file-interpreter
  - control-panel
  - tickets

Este é o COMPLEMENTO delas, como o 99_outros é o dos blocos de cache\: pasta de
cadastro NOVA cai aqui sozinha, sem ninguém tocar em nada.

A pasta translations\ fica FORA de propósito: os 3 JSONs de i18n são os únicos
que permanecem como JSON. Os arquivo-dia de cache\ são dos outros scripts.

É IDEMPOTENTE e INCREMENTAL: cada banco guarda um `_manifest` com
caminho/mtime/tamanho e só reconverte o arquivo que mudou — rodar de novo com
nada alterado não reescreve nada. `--force` reconverte tudo; `--dry-run` só
lista. Erro num arquivo não para o resto: sai no resumo do fim.

GERADO por scripts/build_duckdb_standalone.py a partir de
apps/pages/json_to_duckdb.py — não edite à mão: mexer no motor e não regerar
estes arquivos é como eles passam a discordar.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _motor import (_data_dir_padrao, _resumo, convert_daily,  # noqa: F401
                        convert_datasets, convert_holidays, convert_refdata,
                        data_de_corte)
except ModuleNotFoundError as e:
    if e.name != '_motor':
        raise
    sys.exit('falta o _motor.py ao lado deste script: copie a pasta '
             'scripts/standalone INTEIRA')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--data-dir', default=None,
                    help='origem dos JSONs (padrão: o static\\data do share — o UNC '
                         'ou a letra I:, o que existir na máquina)')
    ap.add_argument('--out-dir', default=None,
                    help='destino dos .db (padrão: a pasta db dentro da origem)')
    ap.add_argument('--only', choices=('holidays', 'refdata', 'datasets'),
                    default=None)
    ap.add_argument('--force', action='store_true', help='reconverte mesmo sem mudança')
    ap.add_argument('--dry-run', action='store_true', help='só lista o que converteria')
    args = ap.parse_args(argv)

    data_dir = os.path.abspath(args.data_dir or _data_dir_padrao())
    out_dir = os.path.abspath(args.out_dir or os.path.join(data_dir, 'db'))
    print('origem : %s' % data_dir)
    print('destino: %s' % out_dir)
    print('escopo : cadastros: calendarios, RefData/CPD e os JSONs de raiz')

    houve_erro = [False]
    # Os cadastros SEM pasta propria: calendarios, RefData/CPD e os JSONs da
    # raiz. As pastas com fatia propria sao excluidas — este script e o
    # COMPLEMENTO delas, entao pasta de cadastro NOVA cai aqui sozinha.
    conversores = {'holidays': convert_holidays, 'refdata': convert_refdata,
                   'datasets': convert_datasets}
    escolhidos = [args.only] if args.only else list(conversores)
    for nome in escolhidos:
        extra = {'excluir': ['mappings', 'file-interpreter', 'control-panel', 'tickets']} if nome == 'datasets' else {}
        _resumo(nome, conversores[nome](data_dir, out_dir, force=args.force,
                                        dry_run=args.dry_run, **extra), houve_erro)
    return 1 if houve_erro[0] else 0


if __name__ == '__main__':
    sys.exit(main())
