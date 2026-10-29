# -*- coding: utf-8 -*-
"""RED Clients: a rodada do card (§730).

Lê a aba da planilha, aplica a lista ao Reference Data num ciclo só de
ler → alterar → gravar sob o `_cache_lock` (a gravação reconstrói a tabela do
cadastro inteiro — sem a trava, uma edição na tela no mesmo instante seria
apagada), e registra a rodada no Intraday Monitor (tarefa diária `red-clients`).
"""
from apps.pages.features.red_clients import domain
from apps.pages.features.red_clients.infra import persistence


def _R():
    from apps.pages import routes
    return routes


def run(nome_arquivo, raw, sid='', nome=''):
    """Devolve o resumo da rodada. `PlanilhaInvalida` sobe (a tela diz o
    motivo) e NADA é gravado — uma planilha errada não tira o RED de ninguém."""
    linhas = persistence.linhas_da_aba(raw)
    ecis = domain.ecis_da_aba(linhas)
    if not ecis:
        # aba sem nenhum ECI na coluna K: é a planilha ou a coluna errada, e
        # aplicada ela tiraria TODOS do RED de uma vez
        raise persistence.PlanilhaInvalida('red_no_eci', sheet=domain.SHEET)

    R = _R()
    with R._cache_lock:
        registros, caminho = R._b3_load('refdata')
        resumo = domain.aplicar(registros, ecis)
        if resumo['changed']:
            R._b3_save(caminho, registros)

    agora = R._br_now()
    resumo.update({'file': nome_arquivo, 'by': nome or sid,
                   'at': agora.strftime('%d/%m/%Y %H:%M:%S')})
    persistence.write_status(resumo)

    from apps.pages.platform import task_runs
    task_runs.record('red-clients', sid, nome,
                     summary={'red': len(resumo['red']), 'entered': len(resumo['entered']),
                              'left': len(resumo['left'])})
    try:
        R._create_notification(
            sid, nome, 'RED Clients Updated', 'Control Panel',
            '{} RED · {} in · {} out'.format(len(resumo['red']), len(resumo['entered']),
                                            len(resumo['left'])))
    except Exception:                        # noqa: BLE001 — o sino é melhor esforço
        R.log.warning('[red-clients] sino não tocou', exc_info=True)
    R.log.warning('[red-clients] %s: %d ECIs, %d RED, +%d -%d, %d sem cadastro',
                  nome_arquivo, resumo['eci_total'], len(resumo['red']),
                  len(resumo['entered']), len(resumo['left']), resumo['eci_unmatched'])
    return resumo
