#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""convert 99_outros — as rotinas de cache/ que não têm arquivo próprio.

A rede de segurança: rotina nova em cache/ é convertida por aqui.

Versão AUTOCONTIDA: roda em QUALQUER máquina, sem o código do OTC Tracker por
perto — com o `_motor.py` desta pasta ao lado (copie a pasta inteira).
Requisito único:  pip install duckdb

    Origem : o static\data do share — o UNC
             (\\Nawest.ad.jpmorganchase.com\lac\BRA\intra\...) ou a letra I:,
             o que existir na máquina. `--data-dir` manda em qualquer caso.
    Destino: ...\static\data\db   (a pasta db dentro da origem)

Uso:
    python 99_outros.py
    python 99_outros.py --dry-run
    python 99_outros.py --data-dir "D:\outra\pasta" --out-dir "D:\saida"

O ESCOPO é o RESTO de cache\: todo bloco que não tem arquivo próprio ao lado
deste. Ele existe para um bloco NOVO nunca ficar sem conversor, e a poda é por
CAMINHO — tanto uma rotina nova (cache\equity) quanto um produto novo dentro de
um bloco já coberto (cache\new deals\NDF\Asian) caem aqui. Hoje os cobertos
são:

  - new deals/NDF/Vanilla
  - new deals/NDF/FwdStart
  - new deals/NDF/OtherPublisher
  - new deals/NDF/Commodities
  - new deals/Option/FXO
  - new deals/Option/Commodities
  - new deals/Swap/Rates
  - new deals/Swap/Commodities
  - new deals/Intrag/NDF
  - new deals/Intrag/Option
  - new deals/Intrag/Swap
  - b3 files/NDF
  - b3 files/Option
  - b3 files/Swap
  - b3 files/Operations
  - daily settlement/otm-settlement
  - daily settlement/ndf-cockpit
  - daily settlement/operations-b3
  - daily settlement/operacoes-jpm
  - daily settlement/operacoes-mgt
  - daily settlement/eventos-swap-jpm
  - daily settlement/eventos-swap-mgt
  - daily settlement/latam-desk-position
  - daily settlement/swap-kapital-hybrids
  - daily settlement/cognos
  - daily settlement/br-onshore-settlements
  - daily settlement/other-products-summary
  - pending-confirmation
  - payrec
  - reconciliation/fxo
  - reconciliation/cgd
  - reconciliation/payrec
  - new deals/Intrag/DCE Option

Se não houver nada fora dessa lista, este script não faz nada, e isso é o
resultado esperado.

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
    print('escopo : cache/ menos as rotinas com arquivo próprio')

    houve_erro = [False]
    # Tudo que os demais scripts NAO cobrem: e o que garante que uma rotina nova
    # em cache/ tenha conversor sem ninguem regerar nada.
    _resumo('daily', convert_daily(data_dir, out_dir, force=args.force,
                                   dry_run=args.dry_run, excluir=['new deals/NDF/Vanilla', 'new deals/NDF/FwdStart', 'new deals/NDF/OtherPublisher', 'new deals/NDF/Commodities', 'new deals/Option/FXO', 'new deals/Option/Commodities', 'new deals/Swap/Rates', 'new deals/Swap/Commodities', 'new deals/Intrag/NDF', 'new deals/Intrag/Option', 'new deals/Intrag/Swap', 'b3 files/NDF', 'b3 files/Option', 'b3 files/Swap', 'b3 files/Operations', 'daily settlement/otm-settlement', 'daily settlement/ndf-cockpit', 'daily settlement/operations-b3', 'daily settlement/operacoes-jpm', 'daily settlement/operacoes-mgt', 'daily settlement/eventos-swap-jpm', 'daily settlement/eventos-swap-mgt', 'daily settlement/latam-desk-position', 'daily settlement/swap-kapital-hybrids', 'daily settlement/cognos', 'daily settlement/br-onshore-settlements', 'daily settlement/other-products-summary', 'pending-confirmation', 'payrec', 'reconciliation/fxo', 'reconciliation/cgd', 'reconciliation/payrec', 'new deals/Intrag/DCE Option'],
                                   desde=desde),
            houve_erro)
    return 1 if houve_erro[0] else 0


if __name__ == '__main__':
    sys.exit(main())
