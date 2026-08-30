#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_convert_split.py — gera as fatias de `scripts/convert/`.

A carga JSON → DuckDB é repartida para várias pessoas rodarem ao mesmo tempo, e
os dois splits saem do MESMO eixo (`ROTINAS_CACHE`, no motor):

  - `scripts/convert/`     usa o `Config` do app (roda DENTRO do checkout);
  - `scripts/standalone/`  não usa nada do app (`build_duckdb_standalone.py`).

Ao contrário do standalone — que precisa carregar o motor inteiro porque a
máquina de destino não tem o código do app —, cada arquivo daqui é uma CHAMADA
de três linhas para `convert_json_to_duckdb.run`. São gerados mesmo assim
porque são um por bloco de `cache/`, e escritos à mão eles envelheceriam no dia
em que um bloco entrasse no `ROTINAS_CACHE` — que é justamente a mudança que
ninguém lembra de propagar.

    python scripts/build_convert_split.py [destino]

`scripts/tests/check_convert_split.py` reprova quem esquecer de rodar.
"""
import importlib.util
import io
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
MOTOR = os.path.join(ROOT, 'apps', 'pages', 'json_to_duckdb.py')
SAIDA_PADRAO = os.path.join(ROOT, 'scripts', 'convert')


def _motor():
    """O motor, carregado do ARQUIVO por importlib: um `from apps.pages...`
    traria o blueprint do Flask junto, e este gerador roda com stdlib +
    duckdb."""
    spec = importlib.util.spec_from_file_location('_motor_json_to_duckdb', MOTOR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pastas():
    """As pastas de cadastro com fatia própria — do MOTOR, como as rotinas."""
    return tuple(_motor().PASTAS_DATASET)


def _rotinas():
    """Os blocos de `cache/` — a mesma lista que o `scripts/standalone/` usa."""
    return tuple(_motor().ROTINAS_CACHE)


_MODELO = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""%(titulo)s

%(escopo_doc)s

GERADO por scripts/build_convert_split.py — não edite à mão.

Usa o `Config` do app para achar a origem e o destino: é a versão para rodar
DENTRO do checkout. Para uma máquina sem o código do OTC Tracker existe o
`scripts/standalone/`, com o mesmo corte em fatias.

As fatias são independentes: os bancos são um por produto, então duas nunca
escrevem no mesmo arquivo e podem rodar AO MESMO TEMPO, em máquinas diferentes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from convert_json_to_duckdb import run    # noqa: E402


if __name__ == '__main__':
    sys.exit(run(%(chamada)s
                 doc=__doc__))
'''

_DOC_COMPLETO = """O ESCOPO é TUDO: os cadastros (feriados, RefData/CounterpartyDetails, mappings,
control-panel, file-interpreter) e TODAS as rotinas de arquivo-dia de cache/.

Se preferir repartir entre várias pessoas — para rodarem ao mesmo tempo, sem uma
esperar a outra —, use os arquivos numerados ao lado deste: 01_cadastros e um
02_* por bloco de cache/.

Esta é a única fatia SEM escopo, e por isso a única que remove os bancos dos
desenhos anteriores e a única que enxerga colisão de tabela entre blocos
diferentes."""

_DOC_CADASTROS = """O ESCOPO são os cadastros que NÃO têm pasta própria ao lado deste script:

  - holiday_calendars.db  uma tabela por calendário do registro (+ _registry);
  - reference_data.db     refdata e counterparty_details, TUDO VARCHAR;
  - <arquivo>.db          os JSONs da RAIZ do DATA_DIR (Subjacente, Dominio, …).

As pastas com muitos arquivos saíram para fatias próprias — 01_1 em diante:

%(lista)s

Este é o COMPLEMENTO delas, como o 99_outros é o dos blocos de cache/: pasta de
cadastro NOVA cai aqui sozinha, sem ninguém tocar em nada.

A pasta translations/ fica FORA de propósito: os 3 JSONs de i18n são os únicos
que permanecem como JSON. Os arquivo-dia de cache/ são dos outros scripts, e por
isso esta fatia não recebe `--meses`: nenhum destes JSONs tem data para cortar."""

_DOC_PASTA = """O ESCOPO é UMA pasta de cadastro do DATA_DIR: **%(pasta)s/**.

%(desc)s

É UM BANCO POR ARQUIVO, na mesma árvore do JSON: db/%(pasta)s/<arquivo>.db, com
uma tabela por arquivo. Juntar a pasta inteira num banco só criava contenção
onde ela não precisa existir — o espelho reconvertendo UM cadastro fechava a
leitura dos outros.

Não recebe `--meses`: nenhum destes JSONs tem data para cortar."""

_DOC_BLOCO = """O ESCOPO é UM bloco de cache/: **%(fam)s**.

%(desc)s

Cada produto vira um banco e a pasta db/ espelha a árvore de cache/; só
ano/mês/dia não viram pasta — cada dia é uma tabela dentro do banco.

A janela padrão é de 12 meses (`--meses`); `--meses 0` traz o histórico inteiro,
e é essa passada que remove os bancos de formato antigo.

Se nesta instância o bloco ainda for grande demais, `--bloco NOME` desce mais um
nível (ex.: `--bloco Vanilla`). Ele SUBSTITUI o escopo desta fatia — não rode a
fatia inteira em paralelo com um bloco dela."""

_DOC_OUTROS = """O ESCOPO é o RESTO de cache/: todo bloco que não tem arquivo próprio ao lado
deste. Ele existe para um bloco NOVO nunca ficar sem conversor, e a poda é por
CAMINHO — tanto uma rotina nova (`cache/equity`) quanto uma pasta nova dentro de
uma já coberta (`cache/new deals/Equity`) caem aqui. Hoje os cobertos são:

%(lista)s

Se não houver nada fora dessa lista, este script não faz nada, e isso é o
resultado esperado."""


def _slug(nome):
    return ''.join(c if c.isalnum() else '_' for c in nome.lower()).strip('_')


def _variantes():
    rotinas = _rotinas()
    pastas = _pastas()
    _lista_pastas = '\n'.join('  - %s' % p for p, _ in pastas)
    out = [
        ('00_completo.py', 'convert 00_completo — TUDO de uma vez.', _DOC_COMPLETO,
         "escopo='tudo (cadastros + todos os blocos de cache/)',"),
        ('01_cadastros.py',
         'convert 01_cadastros — os cadastros sem pasta própria (calendários, '
         'RefData/CPD, raiz).',
         _DOC_CADASTROS % {'lista': _lista_pastas},
         "escopo='cadastros: calendarios, RefData/CPD e os JSONs de raiz',\n"
         "                 conversores=('holidays', 'refdata', 'datasets'),\n"
         "                 excluir_pastas=%r," % ([p for p, _ in pastas],)),
    ]
    for i, (pasta, desc) in enumerate(pastas, start=1):
        out.append((
            '01_%d_%s.py' % (i, _slug(pasta)),
            'convert 01_%s — a pasta de cadastro `%s/`.' % (_slug(pasta), pasta),
            _DOC_PASTA % {'pasta': pasta, 'desc': desc},
            "escopo='%s/ (um banco por arquivo)',\n"
            "                 conversores=('datasets',), pastas=[%r]," % (pasta, pasta)))
    for i, (fam, desc) in enumerate(rotinas, start=1):
        out.append((
            '02_%d_%s.py' % (i, _slug(fam)),
            'convert 02_%s — o bloco `%s` de cache/.' % (_slug(fam), fam),
            _DOC_BLOCO % {'fam': fam, 'desc': desc},
            "escopo='cache/%s (arquivo-dia)',\n"
            "                 conversores=('daily',), familias=[%r]," % (fam, fam)))
    cobertos = [f for f, _ in rotinas]
    out.append((
        '99_outros.py',
        'convert 99_outros — os blocos de cache/ que não têm arquivo próprio.',
        _DOC_OUTROS % {'lista': '\n'.join('  - %s' % f for f in cobertos)},
        "escopo='cache/ menos os blocos com arquivo próprio',\n"
        "                 conversores=('daily',), excluir=%r," % (cobertos,)))
    return out


def main(argv=None):
    destino = (argv or sys.argv[1:] or [SAIDA_PADRAO])[0]
    if not os.path.isdir(destino):
        os.makedirs(destino)
    gerados = []
    for arq, titulo, doc, chamada in _variantes():
        conteudo = _MODELO % {'titulo': titulo, 'escopo_doc': doc, 'chamada': chamada}
        io.open(os.path.join(destino, arq), 'w', encoding='utf-8').write(conteudo)
        gerados.append(arq)
    # Fatia que saiu do ROTINAS_CACHE deixa um arquivo órfão, e ele continuaria
    # rodando com um escopo que ninguém mais declara — some da lista e não do
    # disco é o pior dos dois mundos.
    for antigo in sorted(os.listdir(destino)):
        if antigo.endswith('.py') and antigo not in gerados:
            os.remove(os.path.join(destino, antigo))
            print('   - %s (removido: nao esta mais no ROTINAS_CACHE)' % antigo)
    print('gerados em %s:' % destino)
    for arq in gerados:
        print('   %s' % arq)
    return 0


if __name__ == '__main__':
    sys.exit(main())
