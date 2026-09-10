# -*- coding: utf-8 -*-
"""O armazém das bases locais das ferramentas — `DATA_DIR/tools/`.

Três séries ficam guardadas porque a fonte não as entrega inteiras: o SOFR (o
NY Fed responde por janela), a EURIBOR (o Banco da Finlândia mostra seis meses
por vez e o histórico some com facilidade) e o Term SOFR (licenciado pela CME —
entra pelo arquivo que o usuário importa, e não desce de fonte nenhuma).

Cada base é um JSON com uma LISTA DE REGISTROS, um por data
(`{"date": "2026-09-08", "1 week": 0.0192, …}`), e não um dicionário por data:
é a forma que vira TABELA no banco. A gravação passa pelo funil
(`_atomic_write_json`), que grava no banco (DB-only, §434), e o motor cria
`db/tools/euribor_historico.db`, `db/tools/term_sofr_b3.db` e
`db/tools/sofr_historico.db` — as cotações extraídas ficam num banco, como a
mesa pediu, e a leitura é DB-FIRST (`duck_read.dataset_rows`): banco frio ou
defasado cura na hora, e a emergência é o JSON.

Quatro regras da casa moram aqui:

* **caminho pelo `data_paths`**, nunca montado à mão (CLAUDE.md §4);
* **gravação pelo funil** — `json.dump` fora dele é reprovado pelo
  `check_duck_writers`;
* **o seed vem versionado** em `apps/static/data/tools/seed/`, e na PRIMEIRA
  leitura ele vira a base viva (gravada pelo funil, portanto espelhada) — a
  instância nova nasce com os vinte anos de EURIBOR e os oito de SOFR. A base
  viva é gitignorada: na dev as duas pastas são a mesma, e o JSON reescrito a
  cada sincronização não pode virar ruído de commit;
* **o read-modify-write roda sob o `_cache_lock`** do armazém JSON.
"""
import os

from apps.pages.data_paths import data_path, data_write
from apps.pages.platform import json_cache as _jc

PASTA = 'tools'
SEED = 'seed'


def caminho(nome):
    """Onde a base VIVA mora (e onde se grava)."""
    return data_write(PASTA, nome)


def caminho_do_seed(nome):
    return data_path(PASTA, SEED, nome)


def _ler_json(fp):
    """O payload do caminho, pelo armazém; `None` só quando NÃO HÁ. Banco
    ocupado sobe (é um `IOError` que os leitores tratam) — lido como "não
    há", a base viva seria re-semeada por cima."""
    try:
        from apps.pages import data_store
        return data_store.read(fp)
    except (FileNotFoundError, ValueError):
        return None


def _semear(nome):
    """Copia o seed para a base viva, pelo funil — uma vez, na primeira leitura."""
    registros = _ler_json(caminho_do_seed(nome))
    if not isinstance(registros, list):
        return None
    try:
        salvar(nome, registros)
    except Exception:                                       # noqa: BLE001
        pass                                                # sem disco, vale o seed em memória
    return registros


def carregar(nome):
    """Os registros da base: do armazém (o banco, §434); sem base viva, o
    seed (que vira a base viva). ``[]`` quando não há nada.

    A pergunta "há base viva?" é ao ARMAZÉM, nunca `os.path.isfile`: desde
    o §434 a base gravada pelo funil só existe no banco, e o `isfile` do disco
    respondia "não" para sempre — cada leitura re-semeava e REGRAVAVA a base
    (uma trava exclusiva no share por leitura), apagando o que a sincronização
    do NY Fed/Finlândia tinha trazido e o Term SOFR que o usuário importou
    (varredura de 10/09/2026, §440)."""
    registros = _ler_json(caminho(nome))
    if registros is None:
        return _semear(nome) or []
    return registros if isinstance(registros, list) else []


def salvar(nome, registros):
    """Grava a base viva pelo funil (no banco, §434)."""
    fp = caminho(nome)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    _jc._atomic_write_json(fp, list(registros))


def trava():
    """O lock do read-modify-write — o do armazém JSON, reentrante."""
    return _jc._cache_lock


def para_dict(registros, chave='date'):
    """Lista de registros → ``{data: {campo: valor}}`` (a forma de trabalho)."""
    saida = {}
    for r in registros or []:
        if not isinstance(r, dict):
            continue
        d = str(r.get(chave, '') or '').strip()
        if not d:
            continue
        saida[d] = {k: v for k, v in r.items() if k != chave and v is not None}
    return saida


def para_lista(taxas, campos=None, chave='date'):
    """``{data: {campo: valor}}`` → lista ordenada por data, a data primeiro.
    ``campos`` fixa a ORDEM das colunas (o que o banco não promete sozinho)."""
    saida = []
    for d in sorted(taxas):
        linha = taxas[d] or {}
        rec = {chave: d}
        for c in (campos or sorted(linha)):
            if c in linha and linha[c] is not None:
                rec[c] = linha[c]
        if campos:
            for c in sorted(set(linha) - set(campos)):
                if linha[c] is not None:
                    rec[c] = linha[c]
        saida.append(rec)
    return saida
