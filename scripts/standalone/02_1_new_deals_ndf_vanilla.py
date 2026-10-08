#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""convert 02_new_deals_ndf_vanilla — a rotina `new deals/NDF/Vanilla` de cache/.

O termo de moeda vanilla — costuma ser o maior
arquivo-dia do app inteiro.

Versão AUTOCONTIDA: roda em QUALQUER máquina, sem o código do OTC Tracker por
perto — com o `_motor.py` desta pasta ao lado (copie a pasta inteira).
Requisito único:  pip install duckdb

    Origem : o static\data do share — o UNC
             (\\Nawest.ad.jpmorganchase.com\lac\BRA\intra\...) ou a letra I:,
             o que existir na máquina. `--data-dir` manda em qualquer caso.
    Destino: ...\static\data\db   (a pasta db dentro da origem)

Uso:
    python 02_1_new_deals_ndf_vanilla.py
    python 02_1_new_deals_ndf_vanilla.py --dry-run
    python 02_1_new_deals_ndf_vanilla.py --data-dir "D:\outra\pasta" --out-dir "D:\saida"

O ESCOPO é UM bloco de cache\: **new deals/NDF/Vanilla**.

O termo de moeda vanilla — costuma ser o maior
arquivo-dia do app inteiro.

Cada produto vira um banco e a pasta db\ ESPELHA a árvore de cache\
(db\cache\new deals\NDF\Vanilla.db, db\cache\b3 files\Swap.db); só
ano/mês/dia não viram pasta — cada dia é uma tabela
(d_AAAAMMDD[_tag]), tipada por inferência: dd/mm/aaaa e ISO viram DATE, número
vira BIGINT/DOUBLE, zero à esquerda continua texto, '' vira NULL só em coluna
tipada, e texto sai byte a byte.

Como os bancos são um por produto, este script NÃO escreve em nada que os outros
escrevem: pode rodar ao mesmo tempo que eles.

Se nesta instância o bloco ainda for grande demais, `--bloco NOME` desce mais um
nível (ex.: `--bloco Vanilla`). Ele SUBSTITUI o escopo desta fatia — não rode a
fatia inteira em paralelo com um bloco dela.

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
    ap.add_argument('--bloco', default=None,
                    help='restringe a UMA subpasta desta fatia (ex.: --bloco '
                         'Vanilla). SUBSTITUI o escopo da fatia — nao rode a '
                         'fatia inteira em paralelo com um bloco dela.')
    ap.add_argument('--force', action='store_true', help='reconverte mesmo sem mudança')
    ap.add_argument('--dry-run', action='store_true', help='só lista o que converteria')
    ap.add_argument('--meses', type=int, default=12,
                    help='janela dos arquivo-dia: converte so os dos ultimos '
                         'N meses (padrao 12). Use 0 para o historico INTEIRO '
                         '— e a segunda passada, e e ela que remove os bancos '
                         'de formato antigo.')
    args = ap.parse_args(argv)

    data_dir = os.path.abspath(args.data_dir or _data_dir_padrao())
    out_dir = os.path.abspath(args.out_dir or os.path.join(data_dir, 'db'))
    print('origem : %s' % data_dir)
    print('destino: %s' % out_dir)
    desde = data_de_corte(args.meses)
    # A janela e DECLARADA na tela: o recorte silencioso faria a segunda
    # passada (a do historico) parecer desnecessaria.
    print('janela : %s' % ('arquivo-dia a partir de %s (%d meses)'
                           % (desde.strftime('%d/%m/%Y'), args.meses)
                           if desde else 'historico INTEIRO (--meses 0)'))
    print('escopo : cache/new deals/NDF/Vanilla (arquivo-dia)')

    houve_erro = [False]
    # `--bloco` SUBSTITUI o escopo desta fatia; nao soma. Rodar a fatia inteira
    # em paralelo com um bloco dela poria dois processos no mesmo banco.
    fatia = 'new deals/NDF/Vanilla'
    if args.bloco:
        fatia = fatia.rstrip('/') + '/' + args.bloco.strip().strip('/')
        print('escopo : cache/%s (arquivo-dia) [--bloco]' % fatia)
    _resumo('daily', convert_daily(data_dir, out_dir, force=args.force,
                                   dry_run=args.dry_run, familias=[fatia],
                                   desde=desde),
            houve_erro)
    return 1 if houve_erro[0] else 0


if __name__ == '__main__':
    sys.exit(main())
