# -*- coding: utf-8 -*-
"""As regras do card — constantes e o parse do horário, puros."""

# Segunda (0) e quinta (3). Feriado rola para o próximo dia útil — ver
# `queries.is_routine_day`.
WEEKDAYS = (0, 3)
MONITOR_PATH = '/manual-confirmation/monitor'
# Assunto em INGLÊS, como o corpo e como todo e-mail do app. A mesa pediu os
# quatro em português e voltou atrás: é por eles que ela filtra a caixa de
# entrada, e uma regra de Outlook com acento é a que quebra quando o cliente
# reescreve o cabeçalho codificado.
SUBJECT_MO = 'Confirmations Pending Validation - MO'
# A primeira parada da esteira também é cobrada, e com lista própria: quem
# confere pelo OTC é a mesa de OTC Ops, não o Sales Support.
SUBJECT_OTC = 'Confirmations Pending Validation - OTC'

# Os grupos do Front Office: cada um é um e-mail, com o assunto que a mesa
# pediu e a LISTA DE DESTINATÁRIOS PRÓPRIA (`rec`). `SWAP` e `SWAP CORPORATE`
# da EDG chegaram a ser um grupo só, por terem o mesmo assunto; são grupos
# separados porque quem recebe cada um é diferente, e uma lista compartilhada
# mandaria a fila do corporate para quem só cuida do swap comum.
#
# Na CEM é o contrário, e por isso o grupo lista os DOIS produtos: lá quem
# cuida do swap corporate é a mesma mesa do swap comum, então a fila é uma só.
# Sem isso o `SWAP CORPORATE · CEM` não casava com grupo nenhum e caía no
# `unmatched` do card — cobrança que ninguém recebe, com a linha visível na
# tela em âmbar como único aviso.
#
# ⚠️ 'OPTION EDG' não é um produto: é a opção de CÂMBIO na LOB EDG, e o tipo de
# confirmação dela é `FXO` (o `upgrade` do cadastro `manual-conf-validation`
# converte a linha antiga exatamente assim). Cadastrar 'OPTION EDG' aqui como
# produto faria o grupo nunca casar com linha nenhuma, em silêncio.
FO_GROUPS = (
    {'id': 'cem-swap', 'label': 'CEM Swap', 'lob': 'CEM',
     'products': ('SWAP', 'SWAP CORPORATE'), 'rec': 'fo_cem_swap',
     'subject': 'Confirmations Pending Validation - FO - CEM Swap'},
    {'id': 'edg-swap', 'label': 'EDG Swap', 'lob': 'EDG',
     'products': ('SWAP',), 'rec': 'fo_edg_swap',
     'subject': 'Confirmations Pending Validation - FO - EDG Swap'},
    {'id': 'edg-corp-swap', 'label': 'EDG Corporate Swap', 'lob': 'EDG',
     'products': ('SWAP CORPORATE',), 'rec': 'fo_edg_corp_swap',
     # O assunto é o que a mesa pediu para o SWAP CORPORATE EDG, e ele é o
     # mesmo do EDG Swap: são dois e-mails com o mesmo título, para públicos
     # diferentes. Distingui-los é trocar esta linha.
     'subject': 'Confirmations Pending Validation - FO - EDG Swap'},
    {'id': 'edg-option', 'label': 'EDG Option', 'lob': 'EDG',
     'products': ('FXO',), 'rec': 'fo_edg_option',
     'subject': 'Confirmations Pending Validation - FO - EDG Option'},
)

# As listas do card, na ordem em que a tela as mostra: a do OTC Ops, as duas do
# Sales Support e UMA POR GRUPO do Front Office — quem recebe a fila do EDG
# Option não é quem recebe a do CEM Swap.
REC_KEYS = (('otc_to', 'sales_to', 'sales_escalation')
            + tuple(g['rec'] for g in FO_GROUPS))

# Os modos do disparo. 'routine' e 'both' são os do AGENDAMENTO; os demais
# existem para o botão Run de cada item do card mandar o seu e-mail sozinho —
# reenviar só o EDG Swap não pode obrigar a mesa a disparar os outros cinco.
MODES = (('routine', 'escalation', 'both', 'otc', 'mo')
         + tuple('fo-' + g['id'] for g in FO_GROUPS))


def time_of(raw):
    """(hh, mm) do disparo em BRT. Entrada inválida cai no padrão — um typo na
    variável de ambiente não pode matar a rotina."""
    try:
        hh, mm = (int(x) for x in str(raw).split(':')[:2])
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except (ValueError, TypeError):
        pass
    return 17, 0
