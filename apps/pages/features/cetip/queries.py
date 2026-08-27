# -*- coding: utf-8 -*-
"""A leitura do cadastro `cetip-files` — as regras vivas de quais arquivos a
rotina reconhece, com o padrão de nome e o comportamento de cada um.
"""
from apps.pages.features.cetip import domain


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


def _cetip_rules():
    """Regras da rotina = cadastro (/mapping) + comportamento (código), unidos
    pela coluna TYPE — ou, quando ela não bate, pelo nome do arquivo entre
    parênteses (ver `_cetip_behaviour_for`). Uma linha com padrão inválido é
    ignorada com aviso no log, para um erro de digitação na tela não derrubar a
    rotina inteira."""
    rules = []
    for row in _R()._mapping_rows('cetip-files'):
        label = str(row.get('TYPE') or '').strip()
        source = str(row.get('SOURCE') or '').strip()
        dest = str(row.get('DEST') or '').strip()
        if not label or not source or not dest:
            continue
        matcher = domain._cetip_make_matcher(source, label)
        parts = domain._cetip_split_pattern(source)
        if matcher is None or parts is None:
            _R().log.warning('[cetip] %r ignorado: SOURCE %r não tem %s',
                        label, source, domain._CETIP_DATE_TOKEN)
            continue
        if domain._CETIP_DATE_TOKEN not in dest.upper():
            _R().log.warning('[cetip] %r: DEST %r não tem %s — o nome salvo não terá data',
                        label, dest, domain._CETIP_DATE_TOKEN)
        rule = dict(domain._cetip_behaviour_for(label))
        rule.update({
            'label': label,
            'match': matcher,
            'date_start': parts[0],
            'dest_name': (lambda d: (lambda r: domain._cetip_apply_date(d, r)))(dest),
        })
        extra = str(row.get('EXTRA DEST') or '').strip()
        if extra:
            rule['extra_dest'] = extra
        rules.append(rule)
    return rules
