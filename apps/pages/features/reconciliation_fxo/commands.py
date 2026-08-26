# -*- coding: utf-8 -*-
"""As escritas da Recon de FXO: rodar o batimento e gravar a justificativa."""
from apps.pages import recon_fxo
from apps.pages.features.reconciliation_fxo.infra import persistence

# O par (ação, página) do aviso do sino. `page` é o DESTINO do clique, não o
# assunto: 'Reconciliation' é a página do Pay/Rec, e era para lá que o sino
# levava. O par certo é o mesmo da Recon de Comitentes — e o rótulo precisa
# existir nos TRÊS mapas de destino (`_NOTIF_PAGE_URL`, o `PAGE_URL` da topbar e
# o do `sw-push.js`), senão o item nasce `<div>` em vez de `<a>` e o clique não
# vai a lugar nenhum, sem erro no console.
NOTIF_ACTION = 'Recon Generated'
NOTIF_PAGE = 'Recon FXO'


def run(recon_date, files, mode):
    """Roda o batimento. Devolve o resultado do motor, verbatim.

    O seed dos cadastros vem ANTES da execução — ver
    `infra/persistence.seed_registries`, que é onde está o porquê.
    """
    persistence.seed_registries()
    return recon_fxo.run_fxo(recon_date, files=files, mode=mode)


def save_comment(key, comment, status, status_raw):
    """Grava (ou apaga) a justificativa e devolve o Status já recalculado.

    A justificativa pertence ao TRADE e não à execução do dia: ela volta em toda
    recon daquela operação até alguém alterá-la. Por isso não há data nenhuma
    aqui — e por isso o Status volta junto, para a tela trocar o badge sem
    recarregar a tabela inteira.

    O recálculo sai do MESMO `aplicar_comentarios` que a tabela usa. Reproduzir
    aqui a regra "com comentário vira Justified" criaria uma segunda resposta
    para a mesma pergunta, e é o `_status` cru que permite apagar o comentário e
    a linha voltar a dizer `Partial - Cntpy` em vez de ficar `Justified` para
    sempre.
    """
    recon_fxo.save_comment(key, comment)
    linha = {'Combinação de operações': key,
             'Status': status,
             recon_fxo.STATUS_RAW_KEY: status_raw or status}
    recon_fxo.aplicar_comentarios([linha])
    return {'comment': comment,
            'status': linha['Status'],
            'status_raw': linha[recon_fxo.STATUS_RAW_KEY]}
