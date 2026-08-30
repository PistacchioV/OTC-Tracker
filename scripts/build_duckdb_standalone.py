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
    02_<bloco>      uma fatia por BLOCO de `cache/` — as que têm quebra por DIA.
                    As duas rotinas grandes (New Deals e B3 Files) entram
                    repartidas por dentro, uma fatia por pasta de produto: como
                    bloco único elas eram o gargalo da carga
    99_outros       todo bloco de `cache/` que não tem arquivo próprio, para um
                    bloco NOVO nunca ficar sem conversor — a poda é por CAMINHO,
                    então tanto uma rotina nova quanto uma pasta nova dentro de
                    uma já coberta caem ali

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

def _rotinas_do_motor():
    """A lista de rotinas sai do MOTOR, não daqui.

    Ela é o eixo dos DOIS splits (`scripts/convert/` e `scripts/standalone/`), e
    escrita em cada um envelheceria de um lado só. É carregada do ARQUIVO por
    importlib, e não por `from apps.pages...`, porque importar o pacote traria o
    blueprint do Flask junto — este gerador roda com stdlib e duckdb, e é assim
    que ele continua rodando em qualquer checkout."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('_motor_json_to_duckdb', MOTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return tuple(mod.ROTINAS_CACHE), tuple(mod.PASTAS_DATASET)


ROTINAS, PASTAS = _rotinas_do_motor()

_CAB = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""%(titulo)s

%(resumo)s

Versão AUTOCONTIDA: roda em QUALQUER máquina, sem o código do OTC Tracker por
perto. Requisito único:  pip install duckdb

    Origem : o static\data do share — o UNC
             (\\Nawest.ad.jpmorganchase.com\lac\BRA\intra\...) ou a letra I:,
             o que existir na máquina. `--data-dir` manda em qualquer caso.
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

# O share tem DOIS endereços que apontam para o mesmo lugar: o UNC, que é o que a
# instância do JPM usa (o bloco ENV:PROD do config), e a letra `I:` mapeada, que
# é como a mesa o enxerga. Qual deles existe depende da máquina de quem roda,
# então tenta-se na ordem e vale o primeiro que responder — fixar um só faria o
# script não achar nada na metade das máquinas, e o sintoma seria "não converteu
# nada", não "caminho errado".
DATA_DIR_CANDIDATOS = (
    r'\\Nawest.ad.jpmorganchase.com\lac\BRA\intra\Confirmation\Derivativos\OTC Tracker\Application\static\data',
    r'I:\Confirmation\Derivativos\OTC Tracker\Application\static\data',
)


def _data_dir_padrao():
    for cand in DATA_DIR_CANDIDATOS:
        if os.path.isdir(cand):
            return cand
    return DATA_DIR_CANDIDATOS[0]


def _resumo(nome, stats, houve_erro):
    print('\n== %%s -> %%s' %% (nome, os.path.basename(stats['db'])))
    print('   convertidos: %%d | inalterados: %%d%%s%%s%%s' %% (
        len(stats['converted']), len(stats['skipped']),
        ' | fora da janela: %%d' %% len(stats['antigos'])
        if stats.get('antigos') else '',
        ' | ja cobertos por outro conversor: %%d' %% len(stats['cobertos'])
        if stats.get('cobertos') else '',
        ' | fora deste conversor: %%d' %% len(stats['ignored'])
        if stats.get('ignored') else ''))
    for aviso in stats.get('avisos') or ():
        print('   ! %%s' %% aviso)
    for item in stats['converted']:
        print('   + %%s' %% item)
    for rel, erro in stats['errors']:
        houve_erro[0] = True
        print('   ERRO %%s: %%s' %% (rel, str(erro).strip().splitlines()[-1]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--data-dir', default=None,
                    help='origem dos JSONs (padrão: o static\\data do share — o UNC '
                         'ou a letra I:, o que existir na máquina)')
    ap.add_argument('--out-dir', default=None,
                    help='destino dos .db (padrão: a pasta db dentro da origem)')
%(arg_only)s    ap.add_argument('--force', action='store_true', help='reconverte mesmo sem mudança')
    ap.add_argument('--dry-run', action='store_true', help='só lista o que converteria')
%(arg_meses)s    args = ap.parse_args(argv)

    data_dir = os.path.abspath(args.data_dir or _data_dir_padrao())
    out_dir = os.path.abspath(args.out_dir or os.path.join(data_dir, 'db'))
    print('origem : %%s' %% data_dir)
    print('destino: %%s' %% out_dir)
%(linha_janela)s    print('escopo : %(escopo_label)s')

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
        # A janela so vale para o conversor de arquivo-dia; os cadastros nao
        # tem data nenhuma para recortar.
        extra = {'desde': desde} if nome == 'daily' else {}
        _resumo(nome, conversores[nome](data_dir, out_dir, force=args.force,
                                        dry_run=args.dry_run, **extra), houve_erro)
"""

_MAIN_CADASTROS = """    # Os cadastros SEM pasta propria: calendarios, RefData/CPD e os JSONs da
    # raiz. As pastas com fatia propria sao excluidas — este script e o
    # COMPLEMENTO delas, entao pasta de cadastro NOVA cai aqui sozinha.
    conversores = {'holidays': convert_holidays, 'refdata': convert_refdata,
                   'datasets': convert_datasets}
    escolhidos = [args.only] if args.only else list(conversores)
    for nome in escolhidos:
        extra = {'excluir': %(pastas)r} if nome == 'datasets' else {}
        _resumo(nome, conversores[nome](data_dir, out_dir, force=args.force,
                                        dry_run=args.dry_run, **extra), houve_erro)
"""

_MAIN_PASTA = """    # UMA pasta de cadastro. Os bancos sao um por ARQUIVO, entao esta fatia nao
    # escreve em nada que as outras escrevem.
    _resumo('datasets', convert_datasets(data_dir, out_dir, force=args.force,
                                         dry_run=args.dry_run,
                                         pastas=[%(pasta)r]), houve_erro)
"""

_MAIN_ROTINA = """    # `--bloco` SUBSTITUI o escopo desta fatia; nao soma. Rodar a fatia inteira
    # em paralelo com um bloco dela poria dois processos no mesmo banco.
    fatia = %(fam)r
    if args.bloco:
        fatia = fatia.rstrip('/') + '/' + args.bloco.strip().strip('/')
        print('escopo : cache/%%s (arquivo-dia) [--bloco]' %% fatia)
    _resumo('daily', convert_daily(data_dir, out_dir, force=args.force,
                                   dry_run=args.dry_run, familias=[fatia],
                                   desde=desde),
            houve_erro)
"""

_MAIN_OUTROS = """    # Tudo que os demais scripts NAO cobrem: e o que garante que uma rotina nova
    # em cache/ tenha conversor sem ninguem regerar nada.
    _resumo('daily', convert_daily(data_dir, out_dir, force=args.force,
                                   dry_run=args.dry_run, excluir=%(cobertas)r,
                                   desde=desde),
            houve_erro)
"""

_ARG_ONLY_COMPLETO = ("    ap.add_argument('--only', "
                      "choices=('holidays', 'refdata', 'datasets', 'daily'),\n"
                      "                    default=None)\n")
_ARG_ONLY_CADASTROS = ("    ap.add_argument('--only', "
                       "choices=('holidays', 'refdata', 'datasets'),\n"
                       "                    default=None)\n")

# A janela só existe onde há ARQUIVO-DIA: o 01_cadastros não a recebe, porque
# um `--meses` que não muda nada é pior do que não existir.
_ARG_MESES = (
    "    ap.add_argument('--meses', type=int, default=12,\n"
    "                    help='janela dos arquivo-dia: converte so os dos ultimos '\n"
    "                         'N meses (padrao 12). Use 0 para o historico INTEIRO '\n"
    "                         '— e a segunda passada, e e ela que remove os bancos '\n"
    "                         'de formato antigo.')\n")
# Só as fatias de BLOCO recebem: é o que desce mais um nível numa instância que
# tem mais pasta do que a dev, sem precisar de um arquivo novo.
_ARG_BLOCO = (
    "    ap.add_argument('--bloco', default=None,\n"
    "                    help='restringe a UMA subpasta desta fatia (ex.: --bloco '\n"
    "                         'Vanilla). SUBSTITUI o escopo da fatia — nao rode a '\n"
    "                         'fatia inteira em paralelo com um bloco dela.')\n")
_LINHA_JANELA = (
    "    desde = data_de_corte(args.meses)\n"
    "    # A janela e DECLARADA na tela: o recorte silencioso faria a segunda\n"
    "    # passada (a do historico) parecer desnecessaria.\n"
    "    print('janela : %s' % ('arquivo-dia a partir de %s (%d meses)'\n"
    "                           % (desde.strftime('%d/%m/%Y'), args.meses)\n"
    "                           if desde else 'historico INTEIRO (--meses 0)'))\n")

_DOC_COMPLETO = """O ESCOPO é TUDO: os cadastros (feriados, RefData/CounterpartyDetails, mappings,
control-panel, file-interpreter) e TODAS as rotinas de arquivo-dia de cache\\.
Se preferir repartir entre várias pessoas — para rodarem ao mesmo tempo, sem uma
esperar a outra —, use os arquivos numerados ao lado deste: 01_cadastros e um
02_* por rotina. Os bancos são um por produto, então as fatias nunca escrevem no
mesmo arquivo."""

_DOC_CADASTROS = """O ESCOPO são os cadastros SEM pasta própria ao lado deste script:

  - holiday_calendars.db  uma tabela por calendário do registro (+ _registry);
  - reference_data.db     refdata e counterparty_details, TUDO VARCHAR (o zero à
                          esquerda de SPN/ECI/TAX ID é o que um BIGINT perderia
                          em silêncio) + a coluna _raw com o registro exato;
  - <arquivo>.db          os JSONs da RAIZ do DATA_DIR (Subjacente, Dominio, …).

As pastas com muitos arquivos saíram para fatias próprias — 01_1 em diante:

%(lista)s

Este é o COMPLEMENTO delas, como o 99_outros é o dos blocos de cache\\: pasta de
cadastro NOVA cai aqui sozinha, sem ninguém tocar em nada.

A pasta translations\\ fica FORA de propósito: os 3 JSONs de i18n são os únicos
que permanecem como JSON. Os arquivo-dia de cache\\ são dos outros scripts."""

_DOC_PASTA = """O ESCOPO é UMA pasta de cadastro do DATA_DIR: **%(pasta)s\\**.

%(desc)s

É UM BANCO POR ARQUIVO, na mesma árvore do JSON (db\\%(pasta)s\\<arquivo>.db),
com uma tabela por arquivo e a coluna _raw guardando o registro exato. Juntar a
pasta inteira num banco só criava contenção onde ela não precisa existir — o
espelho reconvertendo UM cadastro fechava a leitura dos outros.

Como os bancos são um por arquivo, este script NÃO escreve em nada que os outros
escrevem: pode rodar ao mesmo tempo que eles."""

_DOC_ROTINA = """O ESCOPO é UM bloco de cache\\: **%(fam)s**.

%(desc)s

Cada produto vira um banco e a pasta db\\ ESPELHA a árvore de cache\\
(db\\cache\\new deals\\NDF\\Vanilla.db, db\\cache\\b3 files\\Swap.db); só
ano/mês/dia não viram pasta — cada dia é uma tabela
(d_AAAAMMDD[_tag]), tipada por inferência: dd/mm/aaaa e ISO viram DATE, número
vira BIGINT/DOUBLE, zero à esquerda continua texto, '' vira NULL só em coluna
tipada, e texto sai byte a byte.

Como os bancos são um por produto, este script NÃO escreve em nada que os outros
escrevem: pode rodar ao mesmo tempo que eles.

Se nesta instância o bloco ainda for grande demais, `--bloco NOME` desce mais um
nível (ex.: `--bloco Vanilla`). Ele SUBSTITUI o escopo desta fatia — não rode a
fatia inteira em paralelo com um bloco dela."""

_DOC_OUTROS = """O ESCOPO é o RESTO de cache\\: todo bloco que não tem arquivo próprio ao lado
deste. Ele existe para um bloco NOVO nunca ficar sem conversor, e a poda é por
CAMINHO — tanto uma rotina nova (cache\\equity) quanto um produto novo dentro de
um bloco já coberto (cache\\new deals\\NDF\\Asian) caem aqui. Hoje os cobertos
são:

%(lista)s

Se não houver nada fora dessa lista, este script não faz nada, e isso é o
resultado esperado."""


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
    """(arquivo, titulo, resumo, escopo_doc, escopo_label, arg_only, corpo_main,
    tem_janela)."""
    _nomes_pastas = [p for p, _ in PASTAS]
    _lista_pastas = '\n'.join('  - %s' % p for p in _nomes_pastas)
    out = [
        ('00_completo.py',
         'convert 00_completo — TUDO de uma vez.',
         'Converte os cadastros E todas as rotinas de arquivo-dia num comando só.',
         _DOC_COMPLETO, 'tudo (cadastros + todas as rotinas de cache/)',
         _ARG_ONLY_COMPLETO, _MAIN_COMPLETO, True),
        ('01_cadastros.py',
         'convert 01_cadastros — os cadastros sem pasta própria.',
         'Feriados, RefData/CounterpartyDetails e os JSONs da raiz.',
         _DOC_CADASTROS % {'lista': _lista_pastas}, 'cadastros: calendarios, '
         'RefData/CPD e os JSONs de raiz',
         _ARG_ONLY_CADASTROS, _MAIN_CADASTROS % {'pastas': _nomes_pastas}, False),
    ]
    for i, (pasta, desc) in enumerate(PASTAS, start=1):
        out.append((
            '01_%d_%s.py' % (i, _slug(pasta)),
            'convert 01_%s — a pasta de cadastro `%s`.' % (_slug(pasta), pasta),
            desc,
            _DOC_PASTA % {'pasta': pasta, 'desc': desc},
            '%s/ (um banco por arquivo)' % pasta,
            '', _MAIN_PASTA % {'pasta': pasta}, False))
    for i, (fam, desc) in enumerate(ROTINAS, start=1):
        out.append((
            '02_%d_%s.py' % (i, _slug(fam)),
            'convert 02_%s — a rotina `%s` de cache/.' % (_slug(fam), fam),
            desc.replace('\n', '\n'),
            _DOC_ROTINA % {'fam': fam, 'desc': desc},
            'cache/%s (arquivo-dia)' % fam,
            _ARG_BLOCO, _MAIN_ROTINA % {'fam': fam}, True))
    cobertas = [f for f, _ in ROTINAS]
    out.append((
        '99_outros.py',
        'convert 99_outros — as rotinas de cache/ que não têm arquivo próprio.',
        'A rede de segurança: rotina nova em cache/ é convertida por aqui.',
        _DOC_OUTROS % {'lista': '\n'.join('  - %s' % f for f in cobertas)},
        'cache/ menos as rotinas com arquivo próprio',
        '', _MAIN_OUTROS % {'cobertas': cobertas}, True))
    return out


def main(argv=None):
    destino = (argv or sys.argv[1:] or [SAIDA_PADRAO])[0]
    corpo = _corpo_do_motor()
    if corpo is None:
        return 1
    if not os.path.isdir(destino):
        os.makedirs(destino)

    gerados = []
    for (arq, titulo, resumo, doc, label, arg_only, main_corpo,
         tem_janela) in _variantes():
        cab = _CAB % {'titulo': titulo, 'resumo': resumo, 'arquivo': arq,
                      'escopo_doc': doc}
        rod = _RODAPE % {'arg_only': arg_only, 'escopo_label': label,
                         'arg_meses': _ARG_MESES if tem_janela else '',
                         'linha_janela': _LINHA_JANELA if tem_janela else '',
                         'corpo_main': main_corpo.rstrip('\n')}
        conteudo = cab + corpo + rod
        io.open(os.path.join(destino, arq), 'w', encoding='utf-8').write(conteudo)
        gerados.append((arq, conteudo.count('\n')))

    # Fatia que saiu do `ROTINAS_CACHE` deixa um arquivo ÓRFÃO, e ele continua
    # rodando — com um escopo que ninguém mais declara e que o `99_outros`
    # agora cobre. Duas pessoas escreveriam no mesmo banco sem que nada na
    # pasta dissesse isso.
    nomes = {a for a, _ in gerados}
    for antigo in sorted(os.listdir(destino)):
        if antigo.endswith('.py') and antigo not in nomes:
            os.remove(os.path.join(destino, antigo))
            print('   - %s (removido: nao esta mais no ROTINAS_CACHE)' % antigo)

    print('gerados em %s:' % destino)
    for arq, n in gerados:
        print('   %-34s %4d linhas' % (arq, n))
    return 0


if __name__ == '__main__':
    sys.exit(main())
