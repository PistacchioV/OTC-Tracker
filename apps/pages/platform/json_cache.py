# -*- coding: utf-8 -*-
"""O armazém JSON do app: escrita atômica, o lock de cache, os claims diários
e o leitor memoizado dos arquivos-dia.

Movido VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10). O `routes.py`
mantém os nomes como ALIAS, e aqui os objetos de ESTADO (`_cache_lock`,
`_daycache_memo`, `_daycache_lock`) são mutados **in place** e nunca
rebindados — por isso o alias deles no `routes` continua vivo, ao contrário do
set da ANBIMA, que a carga rebinda.

O `_bump_cache_gen` vem do `request_cache` (que já é um módulo próprio — a
mesma camada que esta); nada aqui alcança o `routes`.
"""
import json
import logging
import os
import tempfile
import threading
import traceback

import portalocker

from apps.pages.request_cache import bump_cache_gen as _bump_cache_gen

log = logging.getLogger('otc_tracker')

# A escrita atômica garante que um arquivo do cache nunca fica pela metade; só
# ela NÃO evita lost update: dois requests que leem a mesma versão e gravam em
# seguida fazem o segundo apagar a alteração do primeiro. Por isso o ciclo
# inteiro (ler → alterar → gravar) anda dentro do `_cache_lock`.
# RLock e não Lock: helper que tranca sozinho pode ser chamado de um bloco que já
# tranca (é o caso do _conf_state_save), e com Lock isso seria deadlock.
_cache_lock = threading.RLock()


# _cache_lock only serializes threads INSIDE this process — quando duas
# instâncias do app rodam (dois processos, dois hosts), cada uma tem seu
# próprio RLock, e as duas podem ler o claim file antes de qualquer uma
# escrever: ambas veem o slot livre e o e-mail agendado (BACC, MDEA, MT300)
# sai em dobro. O portalocker.Lock abaixo é um lock de ARQUIVO — visto
# por todo processo que abrir o mesmo caminho, inclusive noutro host no share —
# e envolve o ciclo ler → checar → gravar inteiro, então só uma instância
# consegue reservar o slot.
def _claim_daily_slot(claim_file, claim_dir, slot, keep_last, log_prefix):
    """Reserva `slot` em `claim_file`; False se outra instância (ou volta
    anterior deste processo) já reservou. Cross-process via lock de arquivo."""
    os.makedirs(claim_dir, exist_ok=True)
    try:
        with portalocker.Lock(claim_file + '.lock', mode='a+b', timeout=15,
                              flags=portalocker.LockFlags.EXCLUSIVE):
            with _cache_lock:
                try:
                    with open(claim_file, encoding='utf-8') as fh:
                        sent = json.load(fh)
                    if not isinstance(sent, list):
                        sent = []
                except (IOError, OSError, json.JSONDecodeError):
                    sent = []
                if slot in sent:
                    return False
                sent.append(slot)
                _atomic_write_json(claim_file, sorted(sent)[-keep_last:])
                return True
    except portalocker.exceptions.LockException:
        # Outra instância está com o lock — trata como "já reservado" para não
        # arriscar dois envios; a próxima volta do catch-up tenta de novo.
        log.warning('[%s] claim lock busy — assuming another instance is handling %s',
                    log_prefix, slot)
        return False
    except Exception:                                       # noqa: BLE001
        log.warning('[%s] não consegui gravar o claim:\n%s', log_prefix, traceback.format_exc())
        return True


def _release_daily_slot(claim_file, slot, log_prefix):
    """Devolve `slot` (envio falhou) sob o mesmo lock cross-process do claim."""
    try:
        with portalocker.Lock(claim_file + '.lock', mode='a+b', timeout=15,
                              flags=portalocker.LockFlags.EXCLUSIVE):
            with _cache_lock:
                try:
                    with open(claim_file, encoding='utf-8') as fh:
                        sent = json.load(fh)
                    if not isinstance(sent, list):
                        return
                except (IOError, OSError, json.JSONDecodeError):
                    return
                if slot not in sent:
                    return
                _atomic_write_json(claim_file, [s for s in sent if s != slot])
    except Exception:                                       # noqa: BLE001
        log.warning('[%s] não consegui devolver o slot %s:\n%s',
                    log_prefix, slot, traceback.format_exc())


def _atomic_write_json(file_path, data):
    """Write JSON safely: atomic rename on POSIX; direct write fallback on Windows.

    On Windows, os.replace() raises PermissionError if a concurrent reader holds
    the file open without FILE_SHARE_DELETE (e.g. _find_deal_in_cache). In that
    case we fall back to a direct write — safe because _cache_lock already
    serialises all concurrent writes to the same file.

    **O `bump_cache_gen` fica AQUI, e não em cada `*_save`.** O
    `request_cache` pede que quem grava invalide o cache curto do dia, senão a
    edição de quem salvou fica escondida atrás do TTL de 5 s — a pessoa salva,
    a tela recarrega e mostra o valor anterior, sem erro nenhum. São 74
    chamadores deste funil: pedir a chamada em cada um é criar 74 chances de
    esquecer, e a que faltasse só apareceria como "salvei e não mudou" num
    caso de borda. No funil, é impossível esquecer.

    Invalidar demais não custa correção, só um relê a mais: o
    `bump_cache_gen` ignora nome de arquivo sem `YYYYMMDD`, e um arquivo-dia
    que nenhum loader decorado lê apenas incrementa uma geração que ninguém
    consulta. O commit é DEPOIS da gravação bem-sucedida — antes, um erro no
    `os.replace` invalidaria o cache de um dado que continua igual em disco.
    """
    dir_name = os.path.dirname(file_path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        try:
            os.replace(tmp_path, file_path)
            _bump_cache_gen(file_path)
            return
        except PermissionError:
            pass  # Windows: target held open by a reader — fall through
        # Fallback: copy content then remove temp
        with open(file_path, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        _bump_cache_gen(file_path)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _unique_filepath(output_dir, filename):
    """Return a path inside output_dir that does not collide with an existing
    file. If 'filename' is free it is used as-is; otherwise a copy suffix is
    inserted before the extension based on how many same-named files exist:
    'TCO_BANCO.txt' -> 'TCO_BANCO (1).txt' -> 'TCO_BANCO (2).txt' ...
    """
    base, ext = os.path.splitext(filename)
    candidate = filename
    n = 0
    while os.path.exists(os.path.join(output_dir, candidate)):
        n += 1
        candidate = base + ' (' + str(n) + ')' + ext
    return os.path.join(output_dir, candidate)


# ── Os arquivos-dia do cache: um leitor só, com poda e memo ──────────────────
# Sete endpoints varriam a árvore do cache com `os.walk` e abriam todo JSON que
# casasse com o sufixo — as buscas das cinco telas de New Deals e as três de
# Intrag. Na dev é um SSD com dezenas de arquivos e ninguém nota; na instância do
# JPM a árvore está num share, cada listagem e cada abertura é ida e volta de
# rede, e dois anos de histórico são milhares de arquivos.
#
# As três correções são as mesmas do painel (`_dash_scan_files`), e valem pelo
# mesmo motivo:
#
#   • `os.scandir` no lugar de `os.walk`. A listagem de um diretório no SMB já
#     devolve nome, tamanho e mtime de cada entrada, e o `DirEntry` os guarda —
#     no Windows, `entry.stat()` não custa chamada nenhuma. Com `os.walk` essa
#     informação é jogada fora e a checagem do memo custaria um `os.stat` por
#     arquivo, que é MAIS caro do que não ter memo nenhum na primeira leitura.
#   • PODAR por data. A árvore termina em `{...}/{AAAA}/{MM}/arquivo.json`, e um
#     intervalo de datas descarta ano e mês inteiros antes de entrar neles. A
#     poda é grossa de propósito: quem decide continua sendo a data no NOME do
#     arquivo, como sempre foi.
#   • LEMBRAR. Arquivo-dia já lido não é reaberto se não mudou. A chave é
#     (mtime, tamanho) e não o caminho: o arquivo-dia de hoje é reescrito a cada
#     importação, e um amend entra no arquivo do dia da OPERAÇÃO, que pode ser
#     antigo — pelo caminho sozinho a tela congelaria o dia na primeira leitura
#     do processo.
#
# A ORDEM é a de sempre (nome, dentro de cada pasta): a busca devolve os deals na
# ordem em que a árvore é lida, e a ordem crua do `scandir` é a do sistema de
# arquivos — a mesma base renderia listas diferentes no share e na dev.
_daycache_memo = {}                     # caminho → (mtime, tamanho, dados)
_daycache_lock = threading.Lock()
# Teto do memo. Estourado, ele é ESVAZIADO inteiro em vez de despejar por idade:
# o custo é uma varredura completa a mais, uma vez, e a alternativa (LRU) é
# estado a mais para manter no caminho mais quente das telas.
_DAYCACHE_MAX = 20000


def _daycache_dir_ok(nome, pai, desde, ate):
    """Este diretório pode conter arquivo-dia do intervalo?

    Nome de 4 dígitos é ano; de 2 dígitos, mês — e o mês só é avaliado dentro de
    um ano, porque fora dele não há como saber a que ano ele pertence. Nome que
    não é número é pasta de produto e nunca é descartado: quem decide o que é
    ano ou mês é o FORMATO do nome, não a profundidade — a árvore tem produto
    com um nível de subpasta e produto com dois.
    """
    if desde is None and ate is None:
        return True
    if len(nome) == 4 and nome.isdigit():
        ano = int(nome)
        if desde is not None and ano < desde.year:
            return False
        if ate is not None and ano > ate.year:
            return False
        return True
    if len(nome) == 2 and nome.isdigit() and len(pai) == 4 and pai.isdigit():
        ano, mes = int(pai), int(nome)
        if desde is not None and (ano, mes) < (desde.year, desde.month):
            return False
        if ate is not None and (ano, mes) > (ate.year, ate.month):
            return False
    return True


def _day_files(raiz, sufixo='', desde=None, ate=None):
    """Gera `(caminho, nome, mtime, tamanho)` dos arquivos-dia da árvore.

    `desde`/`ate` são `date`/`datetime` e servem só para PODAR: o chamador
    continua filtrando pela data do nome, que é a que vale.

    Diretório que não abre é PULADO com aviso, não derruba a varredura: o share
    fica indisponível de vez em quando, e meia lista é melhor do que um 500.
    """
    if not os.path.isdir(raiz):
        return
    pilha = [(raiz, '')]
    while pilha:
        atual, pai = pilha.pop()
        subdirs, arquivos = [], []
        try:
            with os.scandir(atual) as entradas:
                for e in entradas:
                    try:
                        if e.is_dir():
                            if _daycache_dir_ok(e.name, pai, desde, ate):
                                subdirs.append((e.name, e.path))
                            continue
                        if sufixo and not e.name.endswith(sufixo):
                            continue
                        st = e.stat()
                        arquivos.append((e.name, e.path, st.st_mtime, st.st_size))
                    except OSError:
                        continue
        except OSError:
            log.warning('[daycache] não consegui listar %s', atual)
            continue
        # A pilha é LIFO, então os subdiretórios entram ao contrário para sair
        # em ordem; os arquivos saem por nome, como o `sorted(files)` de antes.
        for nome, caminho in sorted(subdirs, reverse=True):
            pilha.append((caminho, nome))
        for nome, caminho, mtime, size in sorted(arquivos):
            yield (caminho, nome, mtime, size)


def _day_json(fp, mtime, size, mutavel=False):
    """O conteúdo de um arquivo-dia como LISTA, memoizado por (mtime, tamanho).

    `mutavel=True` devolve uma cópia rasa dos registros. É para quem ALTERA os
    dicionários depois de ler — sem ela, a alteração ficaria gravada no memo e
    o próximo leitor veria o dado de outro request. A cópia custa microssegundos
    contra a dezena de milissegundos de uma leitura no share, então ela é barata
    exatamente onde importa.

    Arquivo ilegível devolve lista vazia e NÃO entra no memo: um JSON quebrado
    costuma ser um arquivo sendo escrito naquele instante, e memoizar o vazio
    esconderia o dia até o processo reiniciar.
    """
    with _daycache_lock:
        item = _daycache_memo.get(fp)
    if item and item[0] == mtime and item[1] == size:
        dados = item[2]
    else:
        try:
            with open(fp, 'r', encoding='utf-8') as fh:
                dados = json.load(fh)
        except Exception:                                   # noqa: BLE001
            return []
        if not isinstance(dados, list):
            dados = [dados] if isinstance(dados, dict) else []
        with _daycache_lock:
            if len(_daycache_memo) >= _DAYCACHE_MAX:
                _daycache_memo.clear()
            _daycache_memo[fp] = (mtime, size, dados)
    if mutavel:
        return [dict(d) if isinstance(d, dict) else d for d in dados]
    return dados


def _daycache_forget(fp=None):
    """Esquece um arquivo (ou tudo). Quem REESCREVE um arquivo-dia chama isto —
    o mtime novo já invalidaria a entrada, mas contar com isso é contar com a
    resolução do relógio do sistema de arquivos, que num share não é garantida."""
    with _daycache_lock:
        if fp is None:
            _daycache_memo.clear()
        else:
            _daycache_memo.pop(fp, None)
