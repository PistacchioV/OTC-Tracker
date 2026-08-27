# -*- coding: utf-8 -*-
"""As leituras do card: o retrato da fila, o calendário da rotina e as listas."""
from datetime import datetime, timedelta

from apps.pages.features.conf_escalation import domain
from apps.pages.features.conf_escalation.infra import persistence


def _routes():
    """Busca ATRASADA (ver `infra/persistence.py`): calendário útil e relógio
    BRT são plataforma."""
    from apps.pages import routes
    return routes


def sent_date(row):
    """Quando a confirmação CHEGOU na mesa que está devendo a validação.

    É a 'Data envio validação MO/FO', carimbada no instante em que o OTC
    conferiu (`manual_conf.mark_validated`). As duas alternativas existem para
    a linha antiga, que entrou na esteira antes desse carimbo: sem elas a
    coluna sairia vazia justamente nas confirmações mais velhas — as que o
    relatório existe para cobrar.
    """
    for col in ('Data envio validação MO/FO', 'Conferido OTC',
                'Data envio validação OTC'):
        v = str(row.get(col, '') or '').strip()
        if v:
            return v
    return ''


def fo_group_id(row):
    """O grupo de Front Office da linha, ou '' quando ela não casa com nenhum.

    O produto é comparado pelo TIPO DE CONFIRMAÇÃO (`confirmation_type`), nunca
    pelo texto cru da coluna: é ele que traduz as nomenclaturas que convivem no
    banco para os oito nomes únicos, e é assim que o cadastro de validação e a
    pasta do Electronic Inventory também comparam.
    """
    from apps.pages import manual_conf as _mc
    prod = _mc.confirmation_type(row.get('Produto'), row.get('LOB'))
    lob = _mc.upper_norm(row.get('LOB'))
    for g in domain.FO_GROUPS:
        if lob == g['lob'] and prod in g['products']:
            return g['id']
    return ''


def report_rows(rows, stage, hoje=None):
    """As linhas da tabela do e-mail, já na ordem da fila.

    Mais antiga primeiro (pela data de envio para validação): é a fila, e quem
    espera há mais tempo vem antes. Linha sem data de envio vai para o fim — ela
    não tem como ser comparada, e jogá-la no topo empurraria para baixo o que
    realmente está atrasado.

    `level`/`left` são a luz do SLA daquela mesa; o e-mail usa para marcar em
    vermelho o que venceu, e a escalação usa para escolher quem entra.
    """
    from apps.pages import manual_conf as _mc
    out = []
    for r in rows:
        st = _mc.sla_state(r, stage, hoje)
        out.append({
            'trade_date': str(r.get('Data Operação', '') or ''),
            'client': str(r.get('Cliente', '') or ''),
            # O nome que as três telas mostram, e não o produto cru do banco.
            'product': (_mc.confirmation_type(r.get('Produto'), r.get('LOB'))
                        or str(r.get('Produto', '') or '')),
            'lob': str(r.get('LOB', '') or ''),
            'trade_id': str(r.get(_mc.KEY_COLUMN, '') or ''),
            # 'Moeda' é a coluna do banco; o rótulo é ATIVO desde que ela passou
            # a carregar a commodity da confirmação (OLEO, PLATTS…).
            'asset': str(r.get('Moeda', '') or ''),
            'sent': sent_date(r),
            'deadline': _mc.fmt_date(st['deadline']),
            'level': st['level'],
            'left': st['left'],
        })
    out.sort(key=lambda x: (_mc.parse_date(x['sent']) or datetime.max.date(),
                            x['client'].lower()))
    return out


def snapshot(hoje=None):
    """(otc, mo, grupos_fo, escalation, sem_grupo) — UMA leitura da esteira.

    Uma leitura por e-mail abriria os dois DuckDB quatro vezes no mesmo disparo
    e, pior, as listas contariam momentos diferentes: uma confirmação validada
    entre a primeira e a última leitura sairia numa e não na outra.

    `sem_grupo` são os pares Produto × LOB parados no FO que não casam com
    nenhum grupo cadastrado. Eles NÃO somem calados: o card mostra e o log
    registra — uma linha que desaparece sem dizer nada vira "sumiu uma
    confirmação da cobrança".
    """
    from apps.pages import manual_conf as _mc
    rows = _mc.load_all()
    # Pending Legal fica de fora: é hold manual, a confirmação está parada por
    # decisão de alguém e cobrar o OTC por ela seria cobrar o trabalho errado.
    otc_src = [r for r in rows if r.get('Pending') == _mc.PENDING_OTC]
    mo_src = [r for r in rows if r.get('Pending') in (_mc.PENDING_MO, _mc.PENDING_MOFO)]
    fo_src = [r for r in rows if r.get('Pending') in (_mc.PENDING_FO, _mc.PENDING_MOFO)]

    por_grupo, sem_grupo = {g['id']: [] for g in domain.FO_GROUPS}, set()
    for r in fo_src:
        gid = fo_group_id(r)
        if gid:
            por_grupo[gid].append(r)
        else:
            sem_grupo.add('%s · %s' % (
                _mc.confirmation_type(r.get('Produto'), r.get('LOB')) or '—',
                str(r.get('LOB') or '—')))

    # O prazo é o da mesa que está devendo: OTC D+3, MO D+4, FO D+6, todos
    # contados do trade date.
    otc = report_rows(otc_src, _mc.STAGE_OTC, hoje)
    mo = report_rows(mo_src, _mc.STAGE_MO, hoje)
    grupos = [dict(g, rows=report_rows(por_grupo[g['id']], _mc.STAGE_FO, hoje))
              for g in domain.FO_GROUPS]
    # Último dia = o prazo vence HOJE (`left == 0`). A véspera também acende
    # `warn` (left == 1) e fica de fora de propósito: o pedido é escalar no
    # último dia, e antecipar um dia faria a escalação chegar quando a mesa
    # ainda tem prazo.
    esc = [r for r in mo
           if r['level'] == 'late' or (r['level'] == 'warn' and r['left'] == 0)]
    return otc, mo, grupos, esc, sorted(sem_grupo)


def is_routine_day(d):
    """Hoje é dia do relatório agendado?

    Segunda e quinta, ROLANDO para o próximo dia útil quando o dia cai em
    feriado ANBIMA — o pedido é "se não for dia útil, em D+1". A pergunta é
    feita ao contrário (que segunda/quinta desemboca em HOJE?) porque é assim
    que uma sexta-feira sabe que está pagando a quinta que foi feriado; olhar só
    para o dia da semana de hoje perderia o relatório inteiro nessa semana.

    Dois feriados seguidos rolam para o dia seguinte de novo, e uma quinta que
    role até a segunda seguinte se encontra com a própria segunda — e sai UM
    e-mail, porque o relatório é o retrato de agora, não um acumulado.
    """
    R = _routes()
    d = d.date() if isinstance(d, datetime) else d
    if not R._pcx_is_bizday(d):
        return False
    for back in range(8):
        cand = d - timedelta(days=back)
        if cand.weekday() not in domain.WEEKDAYS:
            continue
        roll = cand
        while not R._pcx_is_bizday(roll):
            roll += timedelta(days=1)
        if roll == d:
            return True
    return False


def next_runs(now=None):
    """Os próximos horários de cada modo, para o card responder "quando sai o
    próximo?" sem ninguém reproduzir a regra de cabeça."""
    R = _routes()
    now = now or R._br_now()
    hh, mm = domain.time_of(persistence.TIME_RAW)
    nxt = {'routine': '', 'escalation': ''}
    for i in range(0, 40):
        cand = (now + timedelta(days=i)).replace(hour=hh, minute=mm,
                                                 second=0, microsecond=0)
        if cand <= now:
            continue
        if not nxt['escalation'] and R._pcx_is_bizday(cand):
            nxt['escalation'] = cand.strftime('%d/%m/%Y %H:%M')
        if not nxt['routine'] and is_routine_day(cand):
            nxt['routine'] = cand.strftime('%d/%m/%Y %H:%M')
        if nxt['routine'] and nxt['escalation']:
            break
    return nxt


def recipients():
    return persistence.load_recipients()


def status():
    return persistence.read_status()


def send_time():
    return domain.time_of(persistence.TIME_RAW)
