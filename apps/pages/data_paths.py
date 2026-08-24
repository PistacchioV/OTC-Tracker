# -*- coding: utf-8 -*-
"""O caminho dos dados em JSON do app — um lugar só, e não `__file__` em cada módulo.

Tudo que o app guarda em JSON mora sob uma pasta: os arquivos-dia do cache (New
Deals, liquidação, MTM, accrual, as recons), os cadastros do /mapping, os
templates do File Interpreter, os tickets, o `RefData.json`, o calendário de
feriados. Cada módulo montava esse caminho a partir do PRÓPRIO arquivo
(`os.path.dirname(__file__) + '/../static/data/...'`), o que amarra os dados ao
diretório do CÓDIGO.

Isso funciona na máquina de desenvolvimento, em que as duas coisas são a mesma
pasta, e quebra na instância do JPM, em que não são: o cache é **gitignorado**,
então um checkout novo não traz arquivo-dia nenhum. O app subia, as APIs
respondiam 200 e os gráficos vinham vazios — o sintoma que mais engana, porque
nada nele parece defeito.

Agora o caminho sai do `Config.DATA_DIR`, que muda de lugar entre as duas
branches junto com o `DATABASE_DIR` e o `SHARED_DRIVE_ROOT`.

**A leitura tem uma segunda chance, a escrita não.** `data_path()` devolve o
arquivo em `DATA_DIR` quando ele existe e, quando não, a cópia EMPACOTADA (a que
vem no repositório, ao lado do código). É isso que mantém de pé o que é
versionado — `anbima.json`, `Subjacente.json`, as seeds dos cadastros — sem
exigir que alguém as copie para o share antes de o app subir. `data_write()`
nunca cai para o pacote: gravar dentro do checkout é gravar num lugar que o
próximo `git pull` conflita e que a outra instância não enxerga.

A consequência combina com o que se espera: o arquivo versionado é lido do
código até alguém EDITÁ-LO pela tela; a partir da primeira gravação, a cópia do
share é a que vale. O dado de runtime vence o empacotado — que é a regra que já
valia quando os dois eram a mesma pasta.
"""

import os

from apps.config import Config

# A cópia que vem no repositório, ao lado do código. É o fallback de leitura, e
# é o valor de `DATA_DIR` na dev — onde as duas são a mesma pasta e nada disto
# tem efeito.
PACKAGED_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static', 'data'))


def data_dir():
    """A raiz dos dados. Configurável (`OTC_DATA_DIR` / o bloco de ENV)."""
    return Config.DATA_DIR


def data_write(*parts):
    """O caminho para GRAVAR. Sempre em `DATA_DIR`, sem cair para o pacote."""
    return os.path.normpath(os.path.join(Config.DATA_DIR, *parts))


def data_path(*parts):
    """O caminho para LER: `DATA_DIR` quando existe, senão a cópia empacotada.

    Existindo em nenhum dos dois, devolve o de `DATA_DIR` — é lá que o arquivo
    deveria estar, e é o caminho que a mensagem de erro precisa citar para
    alguém saber onde procurar.
    """
    alvo = data_write(*parts)
    if os.path.exists(alvo) or Config.DATA_DIR == PACKAGED_DIR:
        return alvo
    empacotado = os.path.normpath(os.path.join(PACKAGED_DIR, *parts))
    return empacotado if os.path.exists(empacotado) else alvo


# ── Os cadastros do /mapping ────────────────────────────────────────────────
# Eles são o caso que exige o fallback POR ARQUIVO, e não por pasta: a instância
# do JPM começa com a pasta de mappings vazia no share, e são 43 cadastros — 42
# deles versionados no repositório, um com quatorze mil linhas. Uma queda por
# PASTA (a pasta existe? então é ela) esconderia os 42 no instante em que o
# primeiro fosse editado pela tela, e cada um voltaria à seed vazia sem erro
# nenhum.
#
# Por arquivo, cada cadastro migra sozinho: lê-se o do repositório até alguém
# editá-lo, e daí em diante o do share.

def with_fallback(caminho):
    """Um caminho já montado, com a queda para a cópia empacotada.

    Só cai quando o caminho está DENTRO do `DATA_DIR`: os testes apontam as
    constantes de pasta dos módulos (`_MAPPINGS_DIR`, `_CACHE_DIR`) para um
    diretório temporário, e cair para o repositório ali faria o teste ler o dado
    de verdade em vez do que ele mesmo escreveu.
    """
    if not os.path.exists(caminho) and Config.DATA_DIR != PACKAGED_DIR:
        try:
            rel = os.path.relpath(caminho, Config.DATA_DIR)
        except ValueError:                      # unidades diferentes, no Windows
            return caminho
        if not rel.startswith(os.pardir):
            empacotado = os.path.join(PACKAGED_DIR, rel)
            if os.path.exists(empacotado):
                return empacotado
    return caminho


def mapping_file(key, base=None):
    """O JSON de um cadastro, para LER (com queda para a cópia do repositório).

    `base` é a pasta de mappings do módulo que chama — os módulos guardam a sua
    própria constante e os testes a apontam para um temporário.
    """
    if base:
        return with_fallback(os.path.join(base, '{}.json'.format(key)))
    return data_path('mappings', '{}.json'.format(key))


def mapping_write(key):
    """O JSON de um cadastro, para GRAVAR. Sempre em `DATA_DIR`."""
    return data_write('mappings', '{}.json'.format(key))
