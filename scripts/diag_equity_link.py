#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diag_equity_link.py — por que o elo de equity não resolve um Título da B3.

O Settlement Advice e o Internal ID de EDG do Swap VCP dependem de uma rota de
três paradas, e ela falha CALADA em qualquer uma:

    Operations B3 --Título--> Latam Desk Position --Deal_Ref--> OTM Settlements
                              CLEARING_TRD_ID_CLNT = CETIP ID do cliente
                              CLEARING_TRD_ID_INT  = CETIP ID interno

    perna = o `Cpty SPN` da linha do OTM (entidade nossa? cliente?)

Sem o elo, a linha sai com o nome curto da B3 — que é a NOSSA perna — e as
colunas de valor em branco, sem erro nenhum.

Este script mostra as STRINGS de verdade em cada salto: o Título procurado nas
duas colunas do Latam, o `Deal_Ref` dele, o que cada Trade Id do OTM vira
depois de descartado o prefixo, e a que perna cada grupo pertence pelo SPN.
Serve exatamente para o caso em que os dois lados "parecem" o mesmo número e
não casam.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share \\
        python scripts/diag_equity_link.py <B3 ID> [AAAA-MM-DD]

Sem B3 ID, lista os Títulos que o Latam conhece e os Deal_Ref do OTM do dia —
é assim que se vê de que lado está a diferença.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps.pages import routes as R                               # noqa: E402
from apps.pages.platform import settlement as S                  # noqa: E402


def main():
    titulo = (sys.argv[1] if len(sys.argv) > 1 else '').strip().upper()
    ds = sys.argv[2] if len(sys.argv) > 2 else None
    ref = R._parse_date_any(ds) if ds else R._br_now().date()
    if ref is None:
        print('data inválida: %r' % ds)
        return 2
    ref = R.datetime(ref.year, ref.month, ref.day)
    print('\nreference date: %s' % ref.strftime('%d/%m/%Y'))

    print('\n== prefixos que o cadastro manda DESCARTAR ==')
    print('  %s' % ', '.join(S._ops_eq_prefixos()))
    print('  (o prefixo NÃO diz a perna — quem diz é o Cpty SPN do OTM)')

    # ── 1. Latam Desk Position ───────────────────────────────────────────────
    lt_ref = R._latam_latest_ref()
    print('\n== 1. Latam Desk Position ==')
    if lt_ref is None:
        print('  NENHUM Latam Desk Position encontrado — o elo fica vazio e todas as')
        print('  linhas de equity saem sem cliente e sem valores.')
        return 1
    print('  usando o ÚLTIMO disponível: %s' % lt_ref)
    idx = S._latam_equity_b3_index()
    print('  %d Título(s) da B3 no de-para' % len(idx))

    # ── 2. OTM Settlements ───────────────────────────────────────────────────
    _jp, otm = R._otm_load(ref)
    otm = otm or []
    print('\n== 2. OTM Settlements de %s ==' % ref.strftime('%d/%m/%Y'))
    print('  %d linha(s)' % len(otm))
    if not otm:
        print('  Sem OTM do dia o elo devolve VAZIO, qualquer que seja o Latam.')
        return 1
    grupos = {}
    for rec in otm:
        tid = str(rec.get('Trade Id', '') or '').strip()
        chave = S._ops_eq_trade_key(tid)
        g = grupos.setdefault(tid.upper(), {'tid': tid, 'ref': chave,
                                            'spn': str(rec.get('Cpty SPN', '') or '').strip(),
                                            'nome': str(rec.get('Cpty Name', '') or '').strip(),
                                            'n': 0})
        g['n'] += 1
    sem_chave = [g for g in grupos.values() if not g['ref']]
    if sem_chave:
        print('  !! %d Trade Id(s) com prefixo NÃO cadastrado — as linhas deles são'
              % len(sem_chave))
        print('     DESCARTADAS antes de agrupar. Cadastre o prefixo em /mapping →')
        print('     Equity Legs — Trade Id Prefix:')
        for g in sorted(sem_chave, key=lambda x: x['tid'])[:15]:
            print('       %-18s (%d linha(s))' % (g['tid'], g['n']))

    if not titulo:
        print('\n== os dois lados, para comparar à mão ==')
        print('  Deal_Ref que o LATAM conhece (até 20):')
        for b3, (dref, interna, _r) in sorted(idx.items())[:20]:
            print('     %-18s -> Deal_Ref %-14s (%s)'
                  % (b3, dref, 'INT' if interna else 'CLNT'))
        print('  Deal_Ref que o OTM produz (até 20):')
        for g in sorted(grupos.values(), key=lambda x: x['tid'])[:20]:
            print('     Trade Id %-18s -> %-14s SPN %-10s %s'
                  % (g['tid'], g['ref'] or '(prefixo não cadastrado)', g['spn'], g['nome']))
        print('\n  Passe um B3 ID para o caminho completo de UM Título.')
        return 0

    # ── 3. o Título pedido ───────────────────────────────────────────────────
    print('\n== 3. o Título %s ==' % titulo)
    achado = idx.get(titulo)
    if not achado:
        print('  NÃO está em nenhuma das duas colunas de clearing do Latam.')
        print('  Sem esta parada não há Deal_Ref, e o elo não tem por onde começar.')
        prox = [b3 for b3 in idx if titulo[:6] and b3.startswith(titulo[:6])]
        if prox:
            print('  Títulos parecidos no Latam: %s' % ', '.join(sorted(prox)[:8]))
        return 1
    dref, interna, _rec = achado
    print('  está na coluna %s → a perna procurada é a %s'
          % ('CLEARING_TRD_ID_INT' if interna else 'CLEARING_TRD_ID_CLNT',
             'INTERNA' if interna else 'do CLIENTE'))
    print('  Deal_Ref (normalizado, sem zeros à esquerda): %r' % dref)

    candidatos = [g for g in grupos.values() if g['ref'] == dref]
    print('\n  grupos do OTM com esse Deal_Ref: %d' % len(candidatos))
    if not candidatos:
        print('  !! É AQUI que quebra. Nenhum Trade Id do OTM, depois de descartado o')
        print('     prefixo, dá %r. Compare com a lista abaixo — o mais comum é o' % dref)
        print('     prefixo não cadastrado (o pedaço dele fica no número) ou os dois')
        print('     lados serem números realmente diferentes.')
        for g in sorted(grupos.values(), key=lambda x: x['tid'])[:20]:
            print('       Trade Id %-18s -> %r' % (g['tid'], g['ref']))
        return 1
    for g in candidatos:
        eh_int = R._ops_is_internal_cpty(g['nome'], g['spn'])
        marca = '  <<< é esta' if eh_int == interna else ''
        print('     Trade Id %-18s SPN %-10s %-32s perna=%s%s'
              % (g['tid'], g['spn'], g['nome'][:32],
                 'INTERNA' if eh_int else 'CLIENTE', marca))
    if not any(R._ops_is_internal_cpty(g['nome'], g['spn']) == interna for g in candidatos):
        print('  !! Nenhum grupo do lado procurado. O Deal_Ref casa, mas o `Cpty SPN`')
        print('     classifica todos do outro lado — confira o cadastro `le-spn` e o')
        print('     ECONOMIC GROUP = INTERNAL do Reference Data para esses SPNs.')

    elo = S._ops_equity_link(ref) if not hasattr(S._ops_equity_link, '__wrapped__') \
        else S._ops_equity_link.__wrapped__(ref)
    r = (elo or {}).get(titulo)
    print('\n== resultado ==')
    if not r:
        print('  o elo NÃO resolveu este Título (ver acima).')
        return 1
    for k in ('internal_id', 'counterparty', 'spn', 'settlement',
              'curva_banco', 'curva_cliente', 'underlying'):
        print('  %-14s %s' % (k, r.get(k)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
