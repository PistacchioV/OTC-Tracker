#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera os conversores STANDALONE a partir do motor do app.

O standalone é a versão do conversor para quem vai rodá-lo numa máquina SEM o
código do OTC Tracker (e sem acesso ao `apps/config.py`): é o MESMO motor
(`apps/pages/json_to_duckdb.py`) com outra casca — sem Config, sem import de
`apps`, com os caminhos do share fixos e `pip install duckdb` como requisito
único.

São VÁRIOS arquivos, todos em `scripts/standalone/`, e a razão é operacional: a
carga completa no share é longa, e repartida ela pode ser **rodada em paralelo
por várias pessoas**, cada uma com o seu arquivo, sem ninguém esperar o outro
terminar. A repartição é segura porque os bancos são um por produto — duas
fatias nunca escrevem no mesmo `.db`:

    00_completo     tudo de uma vez (para quem prefere um comando só)
    01_cadastros    os JSONs ÚNICOS, sem quebra por dia (feriados, RefData/CPD,
                    mappings, control-panel, file-interpreter, cadastros B3)
    02_<rotina>     uma fatia por rotina de `cache/` — as que têm quebra por DIA
    99_outros       toda rotina de `cache/` que não tem arquivo próprio, para
                    uma rotina NOVA nunca ficar sem conversor

Eles são VERSIONADOS em `scripts/standalone/` para serem entregues junto com o
código, e são gerados — nunca editados à mão — porque são cópias de um motor
que vive noutro lugar: por três vezes (HANDOFF §331, §333, §334) o motor mudou e
o standalone teve de ser "regerado e reentregue" à mão, e na quarta passou
batido. Uma mudança esquecida faz os dois produzirem bancos DIFERENTES do mesmo
dado — sem erro nenhum, só duas verdades em disco.

A ÚNICA adaptação do corpo é o seed do registro de calendários: no app ele vem
da vertical de feriados (um import de `apps`), e aqui não há app — sem registro
em disco não há o que converter. O gerador RECUSA gerar se sobrar qualquer outra
referência a `apps` no corpo, que é como uma dependência nova do motor viraria
um `ImportError` na máquina de quem só tem o duckdb instalado.

Uso:
    python scripts/build_duckdb_standalone.py [pasta/de/saida]

Depois de mexer em `apps/pages/json_to_duckdb.py`, RODE ISTO e commite o
resultado. O `check_duckdb_standalone.py` reprova o commit que esquecer.
"""
import io
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
MOTOR = os.path.join(ROOT, 'apps', 'pages', 'json_to_duckdb.py')
SAIDA_PADRAO = os.path.join(ROOT, 'scripts', 'standalone')

# As rotinas de `cache/` que ganham arquivo PRÓPRIO. É uma lista de conveniência
# — quem não estiver aqui cai no `99_outros`, que existe justamente para rotina
# nova não ficar sem conversor enquanto ninguém regera nada.
ROTINAS = (
    ('new deals', 'Os arquivo-dia do New Deals — NDF (Vanilla, FWD Start, Other\n'
                  'Publisher, Commodities), Opção (Commodities, FXO), Swap e Intrag.\n'
                  'É a maior fatia: um banco por produto, uma tabela por dia.'),
    ('b3 files', 'As posições e fluxos que a rotina Save CETIP Files grava —\n'
                 'NDF, Option, Swap e Operations (DPOSICAO, DFLUXO).'),
    ('daily settlement', 'Os arquivos do Daily Settlement — OTM Settlements, NDF Cockpit,\n'
                         'Operações JPM/MGT, Eventos Swap, Cognos, BR Onshore, Latam Desk.\n'
                         'Esta rotina NÃO se ramifica em pastas: os dez arquivos do dia\n'
                         'convivem em AAAA/MM/DD, e é o NOME de cada um que dá o banco.'),
    ('pending-confirmation', 'Os snapshots diários do Pending Confirmation.'),
    ('payrec', 'O histórico diário da reconciliação de Pay/Rec.'),
    ('reconciliation', 'Os caches por data das reconciliações (Pay/Rec e afins).'),
)

_CAB = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""%(titulo)s

%(resumo)s

Versão AUTOCONTIDA: roda em QUALQUER máquina, sem o código do OTC Tracker por
perto. Requisito único:  pip install duckdb

    Origem : I:\Confirmation\Derivativos\OTC Tracker\Application\static\data
    Destino: ...\static\data\db   (a pasta db dentro da origem)

Uso:
    python %(arquivo)s
    python %(arquivo)s --dry-run
    python %(arquivo)s --data-dir "D:\outra\pasta" --out-dir "D:\saida"

%(escopo_doc)s

É IDEMPOTENTE e INCREMENTAL: cada banco guarda um `_manifest` com
caminho/mtime/tamanho e só reconverte o arquivo que mudou — rodar de novo com
nada alterado não reescreve nada. `--force` reconverte tudo; `--dry-run` só
lista. Erro num arquivo não para o resto: sai no resumo do fim.

GERADO por scripts/build_duckdb_standalone.py a partir de
apps/pages/json_to_duckdb.py — não edite à mão: mexer no motor e não regerar
estes arquivos é como eles passam a discordar.
"""
import datetime
import json
import os
import re
import traceback

import duckdb

'''

_RODAPE = r'''

# ── CLI (caminhos fixos do share — versão standalone) ───────────────────────
import argparse
import sys

DATA_DIR_PADRAO = r'I:\Confirmation\Derivativos\OTC Tracker\Application\static\data'


def _resumo(nome, stats, houve_erro):
    print('\n== %%s -> %%s' %% (nome, os.path.basename(stats['db'])))
    print('   convertidos: %%d | inalterados: %%d%%s' %% (
        len(stats['converted']), len(stats['skipped']),
        ' | fora deste conversor: %%d' %% len(stats['ignored'])
        if stats.get('ignored') else ''))
    for item in stats['converted']:
        print('   + %%s' %% item)
    for rel, erro in stats['errors']:
        houve_erro[0] = True
        print('   ERRO %%s: %%s' %% (rel, str(erro).strip().splitlines()[-1]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--data-dir', default=DATA_DIR_PADRAO,
                    help='origem dos JSONs (padrão: o static\\data do share)')
    ap.add_argument('--out-dir', default=None,
                    help='destino dos .db (padrão: a pasta db dentro da origem)')
%(arg_only)s    ap.add_argument('--force', action='store_true', help='reconverte mesmo sem mudança')
    ap.add_argument('--dry-run', action='store_true', help='só lista o que converteria')
    args = ap.parse_args(argv)

    data_dir = os.path.abspath(args.data_dir)
    out_dir = os.path.abspath(args.out_dir or os.path.join(data_dir, 'db'))
    print('origem : %%s' %% data_dir)
    print('destino: %%s' %% out_dir)
    print('escopo : %(escopo_label)s')

    houve_erro = [False]
%(corpo_main)s
    return 1 if houve_erro[0] else 0


if __name__ == '__main__':
    sys.exit(main())
'''

# ── o miolo do main de cada variante ────────────────────────────────────────
_MAIN_COMPLETO = """    conversores = {'holidays': convert_holidays, 'refdata': convert_refdata,
                   'datasets': convert_datasets, 'daily': convert_daily}
    escolhidos = [args.only] if args.only else list(conversores)
    for nome in escolhidos:
        _resumo(nome, conversores[nome](data_dir, out_dir, force=args.force,
                                        dry_run=args.dry_run), houve_erro)
"""

_MAIN_CADASTROS = """    # Os JSONs UNICOS — nenhum deles tem quebra por dia, entao esta fatia nao
    # toca em nada que os scripts de rotina convertem.
    conversores = {'holidays': convert_holidays, 'refdata': convert_refdata,
                   'datasets': convert_datasets}
    escolhidos = [args.only] if args.only else list(conversores)
    for nome in escolhidos:
        _resumo(nome, conversores[nome](data_dir, out_dir, force=args.force,
                                        dry_run=args.dry_run), houve_erro)
"""

_MAIN_ROTINA = """    _resumo('daily', convert_daily(data_dir, out_dir, force=args.force,
                                   dry_run=args.dry_run, familias=[%(fam)r]),
            houve_erro)
"""

_MAIN_OUTROS = """    # Tudo que os demais scripts NAO cobrem: e o que garante que uma rotina nova
    # em cache/ tenha conversor sem ninguem regerar nada.
    _resumo('daily', convert_daily(data_dir, out_dir, force=args.force,
                                   dry_run=args.dry_run, excluir=%(cobertas)r),
            houve_erro)
"""

_ARG_ONLY_COMPLETO = ("    ap.add_argument('--only', "
                      "choices=('holidays', 'refdata', 'datasets', 'daily'),\n"
                      "                    default=None)\n")
_ARG_ONLY_CADASTROS = ("    ap.add_argument('--only', "
                       "choices=('holidays', 'refdata', 'datasets'),\n"
                       "                    default=None)\n")

_DOC_COMPLETO = """O ESCOPO é TUDO: os cadastros (feriados, RefData/CounterpartyDetails, mappings,
control-panel, file-interpreter) e TODAS as rotinas de arquivo-dia de cache\\.
Se preferir repartir entre várias pessoas — para rodarem ao mesmo tempo, sem uma
esperar a outra —, use os arquivos numerados ao lado deste: 01_cadastros e um
02_* por rotina. Os bancos são um por produto, então as fatias nunca escrevem no
mesmo arquivo."""

_DOC_CADASTROS = """O ESCOPO são os JSONs ÚNICOS — os que NÃO têm quebra por dia:

  - holiday_calendars.db  uma tabela por calendário do registro (+ _registry);
  - reference_data.db     refdata e counterparty_details, TUDO VARCHAR (o zero à
                          esquerda de SPN/ECI/TAX ID é o que um BIGINT perderia
                          em silêncio) + a coluna _raw com o registro exato;
  - <pasta>_<arquivo>.db  UM BANCO POR JSON para o resto — mappings_mt300.db,
                          control_panel_mt300_status.db,
                          file_interpreter_termo.db, e o JSON da raiz com o
                          próprio nome (subjacente.db).

A pasta translations\\ fica FORA de propósito: os 3 JSONs de i18n são os únicos
que permanecem como JSON. Os arquivo-dia de cache\\ são dos outros scripts."""

_DOC_ROTINA = """O ESCOPO é UMA rotina de cache\\: **%(fam)s**.

%(desc)s

Cada produto vira um banco (o caminho inteiro de cache\\ no nome —
daily_new_deals_ndf_vanilla.db, daily_b3_files_swap.db) e cada dia é uma tabela
(d_AAAAMMDD[_tag]), tipada por inferência: dd/mm/aaaa e ISO viram DATE, número
vira BIGINT/DOUBLE, zero à esquerda continua texto, '' vira NULL só em coluna
tipada, e texto sai byte a byte.

Como os bancos são um por produto, este script NÃO escreve em nada que os outros
escrevem: pode rodar ao mesmo tempo que eles."""

_DOC_OUTROS = """O ESCOPO é o RESTO de cache\\: toda rotina que não tem arquivo próprio ao lado
deste. Ele existe para uma rotina NOVA nunca ficar sem conversor — hoje as
cobertas são:

%(lista)s

Se não houver nenhuma rotina fora dessa lista, este script não faz nada, e isso
é o resultado esperado."""


def _slug(nome):
    return ''.join(c if c.isalnum() else '_' for c in nome.lower()).strip('_')


def _corpo_do_motor():
    """O corpo do motor com a ÚNICA adaptação prevista — ou `None` com o motivo
    impresso, que é como uma mudança no motor para de gerar em silêncio."""
    motor = io.open(MOTOR, encoding='utf-8').read()
    corpo = motor[motor.index('REGISTRY_FILE = '):].rstrip('\n')
    if SEED_APP not in corpo:
        print('ERRO: o ramo do seed de calendarios mudou — reveja a adaptacao')
        return None
    corpo = corpo.replace(SEED_APP, SEED_STANDALONE)
    if 'apps.' in corpo or 'from apps' in corpo:
        print('ERRO: sobrou referencia a `apps` no corpo:')
        for i, l in enumerate(corpo.splitlines(), 1):
            if 'apps' in l:
                print('   %d: %s' % (i, l))
        return None
    return corpo


SEED_APP = """    # Instância que nunca abriu a tela: o registro ainda não foi semeado.
    # O seed do app é a mesma lista que a tela usaria — importado só aqui,
    # e só neste caso.
    try:
        from apps.pages.features.holidays import domain
        return [dict(r) for r in domain.CAL_SEED]
    except Exception:                                          # noqa: BLE001
        return []
"""
SEED_STANDALONE = """    # Sem registro não há o que converter — o arquivo nasce quando alguém
    # abre a tela de calendários no app. (No app este ramo cai no seed da
    # vertical de feriados; aqui não há `apps` para importar.)
    return []
"""


def _variantes():
    """(arquivo, titulo, resumo, escopo_doc, escopo_label, arg_only, corpo_main)."""
    out = [
        ('00_completo.py',
         'convert 00_completo — TUDO de uma vez.',
         'Converte os cadastros E todas as rotinas de arquivo-dia num comando só.',
         _DOC_COMPLETO, 'tudo (cadastros + todas as rotinas de cache/)',
         _ARG_ONLY_COMPLETO, _MAIN_COMPLETO),
        ('01_cadastros.py',
         'convert 01_cadastros — os JSONs ÚNICOS (sem quebra por dia).',
         'Feriados, RefData/CounterpartyDetails e um banco por JSON de cadastro.',
         _DOC_CADASTROS, 'cadastros (sem quebra por dia)',
         _ARG_ONLY_CADASTROS, _MAIN_CADASTROS),
    ]
    for i, (fam, desc) in enumerate(ROTINAS, start=1):
        out.append((
            '02_%d_%s.py' % (i, _slug(fam)),
            'convert 02_%s — a rotina `%s` de cache/.' % (_slug(fam), fam),
            desc.replace('\n', '\n'),
            _DOC_ROTINA % {'fam': fam, 'desc': desc},
            'cache/%s (arquivo-dia)' % fam,
            '', _MAIN_ROTINA % {'fam': fam}))
    cobertas = [f for f, _ in ROTINAS]
    out.append((
        '99_outros.py',
        'convert 99_outros — as rotinas de cache/ que não têm arquivo próprio.',
        'A rede de segurança: rotina nova em cache/ é convertida por aqui.',
        _DOC_OUTROS % {'lista': '\n'.join('  - %s' % f for f in cobertas)},
        'cache/ menos as rotinas com arquivo próprio',
        '', _MAIN_OUTROS % {'cobertas': cobertas}))
    return out


def main(argv=None):
    destino = (argv or sys.argv[1:] or [SAIDA_PADRAO])[0]
    corpo = _corpo_do_motor()
    if corpo is None:
        return 1
    if not os.path.isdir(destino):
        os.makedirs(destino)

    gerados = []
    for (arq, titulo, resumo, doc, label, arg_only, main_corpo) in _variantes():
        cab = _CAB % {'titulo': titulo, 'resumo': resumo, 'arquivo': arq,
                      'escopo_doc': doc}
        rod = _RODAPE % {'arg_only': arg_only, 'escopo_label': label,
                         'corpo_main': main_corpo.rstrip('\n')}
        conteudo = cab + corpo + rod
        io.open(os.path.join(destino, arq), 'w', encoding='utf-8').write(conteudo)
        gerados.append((arq, conteudo.count('\n')))

    print('gerados em %s:' % destino)
    for arq, n in gerados:
        print('   %-34s %4d linhas' % (arq, n))
    return 0


if __name__ == '__main__':
    sys.exit(main())
