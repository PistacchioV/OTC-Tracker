"""
backfill_manual_confirmations.py
--------------------------------
Traz para a esteira de Manual Confirmations as operações que JÁ estavam mapeadas
quando a esteira passou a existir.

Por que é preciso: o espelho `_mc_save_from_deal` nasceu no commit 994e742, junto
com as duas telas, e ele é um gancho PARA FRENTE — roda no instante em que a
operação é mapeada (`Status` → `Success`). Tudo que foi mapeado antes disso
alimentou o Pending Confirmation e parou ali: a operação existe, a confirmação é
devida, e a esteira nunca soube dela. Não é um bug do mapeamento, é o histórico
que não foi varrido — e é isso que este script faz, uma vez.

A regra NÃO é reescrita aqui. O script varre o cache de New Deals e chama as
mesmas duas funções que o mapeamento chama (`_pc_is_internal_counterparty` para
descartar perna interna/intragrupo, `_mc_save_from_deal` para gravar). Repetir o
critério aqui criaria uma segunda resposta para "esta operação gera confirmação?"
— que é exatamente como as duas telas passariam a discordar.

Quais famílias entram: só as que GERAM DOCUMENTO de confirmação
(`_MC_CONFIRMATION_SOURCES`). O NDF Vanilla entra PELA METADE — só o de MGT
contra cliente gera documento (§453), e quem decide deal a deal é a mesma
função do mapeamento. Other Publisher fica de fora de propósito: alimenta o
Pending Confirmation e para aí. Swap e Intrag também.

Uso
    python scripts/backfill_manual_confirmations.py --dry-run   # só relata
    python scripts/backfill_manual_confirmations.py             # grava
    python scripts/backfill_manual_confirmations.py --source "NDF COMM"

É idempotente: `_mc_save_from_deal` nunca sobrescreve uma linha existente, então
rodar duas vezes não duplica nada nem apaga um 'Conferido OTC' já carimbado.
Rodar de novo depois de novos mapeamentos também é inofensivo.
"""
import argparse
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, REPO_ROOT)

# ── o dado vem do ARMAZÉM, não da cópia do repositório ──────────────────────
# `apps/static/data/*.json` no checkout é a SEED; na instância o dado vive no
# DATA_DIR (o share) e, desde o §434, dentro dos bancos. Ler o JSON do
# repositório aqui era ler o Reference Data de meses atrás (§440).
def _caminho_de_dado(*parts):
    try:
        if REPO_ROOT not in sys.path:
            sys.path.insert(0, REPO_ROOT)
        os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', REPO_ROOT)
        from apps.pages.data_paths import data_path
        return data_path(*parts)
    except Exception:                                       # noqa: BLE001
        return os.path.join(REPO_ROOT, 'apps', 'static', 'data', *parts)


def _armazem():
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', REPO_ROOT)
    from apps.pages import data_store
    return data_store


def _ler_json_do_armazem(path):
    return _armazem().read(path)


CACHE_ROOT = _caminho_de_dado('cache', 'new deals')

# Pasta do cache → o `source` que o mapeamento daquela página passa. É a mesma
# string de `_MC_CONFIRMATION_SOURCES`; uma pasta fora deste mapa não é varrida.
# 'NDF/FWD Start' é a única das três páginas genéricas de NDF que gera
# confirmação, e é a única cuja linha é chaveada pelo B3 ID (ver
# `_generic_nd_pc_trigger`) — sem isso o backfill criaria a linha com o nome do
# deal, e o mapeamento seguinte criaria uma SEGUNDA linha com o B3 ID.
#
# `generic` é a chave da página no `_GENERIC_ND_PRODUCTS`, e ela responde as
# DUAS perguntas de uma vez:
#
#   * a PASTA sai de `cfg['dir']` do próprio gerador, nunca de um literal aqui.
#     As três páginas genéricas gravam em `NDF/Vanilla`, `NDF/FwdStart` e
#     `NDF/OtherPublisher` — SEM espaço (`check_nd_cache_dirs.py`). Este script
#     escrevia `NDF/FWD Start`, que é o RÓTULO de tela e não existe em disco:
#     uma pasta inexistente não dá erro, casa com nada, e o backfill do FWD
#     Start varria zero arquivo em silêncio desde que a pasta ganhou o nome
#     atual.
#   * o SOURCE sai do `_generic_nd_mc_source`, por DEAL. É o que faz o Vanilla
#     entrar pela metade: só o de MGT contra cliente gera documento (§453), e o
#     do BANCO responde None. Um `source` fixo traria a página inteira — a de
#     maior volume — para a esteira. E perguntar à função do mapeamento, em vez
#     de repetir o teste de `LE` aqui, é o que impede backfill e mapeamento de
#     discordarem de quem tem documento.
#
# As famílias que não são página genérica declaram a pasta em `dir`, relativa ao
# cache do New Deals.
FAMILIES = {
    'NDF Commodities':    {'dir': ('NDF', 'Commodities'),    'source': 'NDF COMM',      'key': 'deal'},
    'Option Commodities': {'dir': ('Option', 'Commodities'), 'source': 'OPTION COMM',   'key': 'deal'},
    'Option FXO':         {'dir': ('Option', 'FXO'),         'source': 'OPTION',        'key': 'deal'},
    'NDF FWD Start':      {'generic': 'fwd-start',           'source': 'NDF FWD START', 'key': 'b3id'},
    'NDF Vanilla':        {'generic': 'vanilla',             'source': 'NDF VANILLA',   'key': 'deal'},
}


def family_root(cfg, R):
    """A pasta da família: a do próprio gerador quando é página genérica."""
    if cfg.get('generic'):
        return R._GENERIC_ND_PRODUCTS[cfg['generic']]['dir']
    return os.path.join(CACHE_ROOT, *cfg['dir'])


def iter_deals(root):
    """Todos os deals dos arquivos-dia da família, na ordem das datas."""
    if not _armazem().isdir(root):
        return
    for dirpath, _dirs, files in _armazem().walk(root):
        for fname in sorted(files):
            if not fname.endswith('.json'):
                continue
            path = os.path.join(dirpath, fname)
            try:
                deals = _ler_json_do_armazem(path)
            except (OSError, ValueError):
                print('  ! não consegui ler {}'.format(os.path.relpath(path, REPO_ROOT)))
                continue
            if isinstance(deals, list):
                for deal in deals:
                    if isinstance(deal, dict):
                        yield deal


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true',
                    help='conta o que entraria, sem gravar')
    ap.add_argument('--source', action='append', metavar='SOURCE',
                    help='limita a um source (ex.: "NDF COMM"); pode repetir')
    args = ap.parse_args()

    # O import de routes sobe os schedulers do app — barulho no log, inofensivo
    # num processo que termina. É o preço de reusar a regra em vez de copiá-la.
    from apps.pages import routes as R                            # noqa: E402
    from apps.pages import manual_conf as MC                      # noqa: E402

    wanted = set(args.source) if args.source else None
    totals = {'varridos': 0, 'success': 0, 'internos': 0, 'fora_regra': 0,
              'sem_chave': 0, 'ja_existiam': 0, 'criados': 0}

    for family, cfg in sorted(FAMILIES.items()):
        source = cfg['source']
        if wanted and source not in wanted:
            continue
        if source not in R._MC_CONFIRMATION_SOURCES:
            # Rede de segurança: se alguém tirar um produto da lista lá, o
            # backfill para de trazê-lo aqui em vez de contrariar a decisão.
            print('· {:22s} fora de _MC_CONFIRMATION_SOURCES — pulando'.format(source))
            continue

        criados = existiam = internos = sem_chave = success = varridos = 0
        fora_regra = 0
        # O MESMO Deal aparece em mais de um arquivo-dia (amend, remapeação, e no
        # mock simplesmente repetido). Sem este conjunto o --dry-run conta cada
        # repetição como uma linha nova — ele não enxerga a própria gravação que
        # não fez, e prometia 73 onde o run real criava 39.
        vistos = set()
        root = family_root(cfg, R)
        if not _armazem().isdir(root):
            # Pasta que não existe casa com NADA e não levanta: é assim que o
            # FWD Start varria zero em silêncio. Dizer o caminho é o que separa
            # "não há o que trazer" de "estou olhando no lugar errado".
            print('· {:20s} {:22s} pasta inexistente: {}'.format(
                family, source, root))
            continue
        for deal in iter_deals(root):
            varridos += 1
            if str(deal.get('Status', '') or '').strip() != 'Success':
                continue
            success += 1

            client = str(deal.get('Client', '') or '')
            if R._pc_is_internal_counterparty(client, deal.get('SPN', '')):
                internos += 1
                continue

            # Família de source condicional: pergunta a regra do mapeamento por
            # DEAL. O Vanilla do BANCO responde None e fica de fora — é a
            # maioria da página, e por isso o contador existe: sem ele a linha
            # do resumo diria `varridos=5000 criados=12` e pareceria defeito.
            # Página genérica: a regra do MAPEAMENTO responde por deal. O
            # FWD Start responde sempre o mesmo; o Vanilla do BANCO responde
            # None e fica de fora — é a maioria da página, e por isso o contador
            # existe: sem ele a linha do resumo diria `varridos=5000 criados=12`
            # e pareceria defeito.
            deal_source = cfg['source']
            if cfg.get('generic'):
                deal_source = R._generic_nd_mc_source(cfg['generic'], deal)
                if deal_source is None:
                    fora_regra += 1
                    continue

            if cfg['key'] == 'b3id':
                key = str(deal.get('B3_ID', '') or '').strip()
            else:
                key = str(deal.get('Deal', '') or '').strip()
            if not key:
                sem_chave += 1
                continue

            if key in vistos or MC.find_row(key) is not None:
                existiam += 1
                continue
            vistos.add(key)

            if not args.dry_run:
                R._mc_save_from_deal(deal, deal_source, trade_number=key)
                if MC.find_row(key) is None:
                    print('  ! {} não gravou (ver log [manual-conf])'.format(key))
                    continue
            criados += 1

        print('· {:20s} {:22s} varridos={:4d} success={:3d} internos={:3d} '
              'fora-da-regra={:4d} sem-chave={:2d} já-existiam={:3d} {}={:3d}'.format(
                  family, source, varridos, success, internos, fora_regra,
                  sem_chave, existiam,
                  'entrariam' if args.dry_run else 'criados', criados))

        totals['varridos'] += varridos
        totals['success'] += success
        totals['internos'] += internos
        totals['fora_regra'] += fora_regra
        totals['sem_chave'] += sem_chave
        totals['ja_existiam'] += existiam
        totals['criados'] += criados

    verbo = 'entrariam na esteira' if args.dry_run else 'entraram na esteira'
    print()
    print('{} deals varridos · {} mapeados (Success) · {} pernas internas · '
          '{} fora da regra do produto · {} já na esteira'.format(
              totals['varridos'], totals['success'], totals['internos'],
              totals['fora_regra'], totals['ja_existiam']))
    print('{} {}{}'.format(totals['criados'], verbo,
                           ' (--dry-run: nada foi gravado)' if args.dry_run else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
