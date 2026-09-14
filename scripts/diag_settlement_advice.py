#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diag_settlement_advice.py — por que o NDF/Option Settlement Advice está vazio.

As duas telas não têm fonte própria: elas PENEIRAM o arquivo-dia do Operations
B3 e desistem em silêncio em cada degrau. `_ndfadv_collect` e `_optadv_collect`
devolvem `[]` — não um erro — quando

  1. não há arquivo-dia de Operations B3 na data (é o mesmo `ref` das duas
     telas, sem walk-back: o dia é o que está no campo, e a Reference date do
     card Save Daily Settlement é quem decide em que dia o arquivo foi gravado);
  2. o cadastro `opb3-events` derrubou todas as linhas — e a armadilha aqui é
     que CADASTRAR um Consider é o que LIGA a lista branca: um Tipo Título com
     ao menos um Consider próprio passa a aceitar SÓ as combinações cadastradas,
     enquanto um Tipo Título sem nenhum Consider não é filtrado. Registrar o
     evento errado deixa a tela mais vazia do que não registrar nada;
  3. nenhuma linha tem o Tipo Título do produto (`ter` no aviso de termo, `opc`
     no de opção);
  4. (só o aviso de termo) nenhuma sobrevivente resolve para uma classe de
     subjacente com `commodit` — e essa classe NÃO está no arquivo do Operations
     B3: ela vem do snapshot de posição da B3 (`DPOSICAO-TER`), procurado de D-1
     ANBIMA para trás por até 10 dias úteis. Sem o arquivo no BANCO, o mapa
     nasce vazio e o aviso fica vazio sem uma linha de log. O sintoma gêmeo, na
     tela Operations B3, é a coluna **Type** em branco.

Este script percorre os quatro degraus com os números de cada um.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share \
        python scripts/diag_settlement_advice.py [AAAA-MM-DD]
"""
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

from apps.pages import routes as R                              # noqa: E402
from apps.pages import data_store as _store                     # noqa: E402
from apps.pages.platform import operations_b3 as OB             # noqa: E402


def main():
    ds = sys.argv[1] if len(sys.argv) > 1 else None
    ref = R._parse_date_any(ds) if ds else R._br_now().date()
    if ref is None:
        print('data inválida: %r' % ds)
        return 2
    ref = R.datetime(ref.year, ref.month, ref.day)
    print('\nreference date: %s' % ref.strftime('%d/%m/%Y'))

    # ── 1. o arquivo-dia do Operations B3 ────────────────────────────────────
    jp = OB._opb3_json_path(ref)
    print('\n== 1. arquivo-dia do Operations B3 ==')
    print('  %s' % jp)
    existe = _store.isfile(jp)
    print('  existe no armazém: %s' % ('SIM' if existe else 'NÃO'))
    _p, data = OB._opb3_load(ref)
    data = data or []
    print('  linhas: %d' % len(data))
    if not data:
        print('\n>> as duas telas ficam VAZIAS aqui, e nenhuma outra causa importa.')
        print('   O dia do arquivo é a Reference date usada no card Save Daily')
        print('   Settlement Files — processar o arquivo com a data de hoje grava')
        print('   no dia de hoje, e o aviso aberto noutro dia não o procura.')
        return 1

    # ── 2. o cadastro `opb3-events` ──────────────────────────────────────────
    cons, dis = OB._opb3_event_rules()
    print('\n== 2. cadastro opb3-events ==')
    print('  Consider : %d regra(s)' % len(cons))
    for r in cons:
        print('     título=%-18r operação=%-28r status=%r' % r)
    print('  Disregard: %d regra(s)' % len(dis))
    for r in dis:
        print('     título=%-18r operação=%-28r status=%r' % r)
    brancos = sorted({r[0] for r in cons if r[0]})
    if brancos:
        print('  >> LISTA BRANCA ligada para: %s' % ', '.join(brancos))
        print('     (esses Tipos Título passam a aceitar SÓ as combinações acima;')
        print('      os demais não são filtrados por Consider nenhum)')

    # O funil linha a linha, agregado pela tripla que a regra compara.
    triplas = Counter()
    passou = Counter()
    for rec in data:
        t = (OB._opb3_ev_key(rec.get('Tipo Título', '')),
             OB._opb3_ev_key(rec.get('Tipo Operação', '')),
             OB._opb3_ev_key(rec.get('Status', '')))
        triplas[t] += 1
        if OB._opb3_settle_ok(rec, (cons, dis)):
            passou[t] += 1
    print('\n  o que o arquivo TEM, e o que o cadastro deixa passar:')
    print('     %-14s %-30s %-24s %6s %6s' % ('TIPO TÍTULO', 'TIPO OPERAÇÃO', 'STATUS', 'linhas', 'passam'))
    for t, n in triplas.most_common():
        print('     %-14s %-30s %-24s %6d %6d%s'
              % (t[0] or '(vazio)', t[1] or '(vazio)', t[2] or '(vazio)', n, passou[t],
                 '   <<< TODAS derrubadas' if n and not passou[t] else ''))
    sobrou = OB._opb3_settle_rows(ref)
    print('\n  sobraram %d de %d linha(s)' % (len(sobrou), len(data)))
    if not sobrou:
        print('\n>> as duas telas ficam VAZIAS aqui. Compare as triplas acima com o')
        print('   que está cadastrado: uma linha de Consider com o Tipo Operação ou o')
        print('   Status escritos de outro jeito liga a lista branca e não casa nada.')
        return 1

    # ── 3. o recorte de PRODUTO de cada tela ─────────────────────────────────
    print('\n== 3. o recorte de produto de cada aviso ==')
    com_ter = [r for r in sobrou if 'ter' in R._fcst_norm(r.get('Tipo Título', ''))]
    com_opc = [r for r in sobrou if 'opc' in R._fcst_norm(r.get('Tipo Título', ''))]
    print('  Tipo Título com "ter" (aviso de termo) : %d' % len(com_ter))
    print('  Tipo Título com "opc" (aviso de opção) : %d' % len(com_opc))

    # ── 4. a classe do subjacente (só o aviso de termo) ──────────────────────
    print('\n== 4. a classe do subjacente — DPOSICAO da B3 (só o aviso de termo) ==')
    maps = OB._opb3_tipo_maps(ref)
    for k in ('TER', 'OPC', 'SWAP'):
        print('  mapa %-5s: %d contrato(s)%s'
              % (k, len(maps.get(k) or {}),
                 '   <<< VAZIO: o DPOSICAO não foi achado no banco' if not maps.get(k) else ''))
    classes = Counter(OB._opb3_tipo_for(r, maps) or '(não resolveu)' for r in com_ter)
    if com_ter:
        print('  classes das linhas de termo:')
        for c, n in classes.most_common():
            print('     %-40s %4d%s' % (c, n, '   <<< entra no aviso' if 'commodit' in R._fcst_norm(c) else ''))

    # ── o resultado de verdade ───────────────────────────────────────────────
    print('\n== resultado ==')
    for rot, fn in (('NDF Settlement Advice', R._ndfadv_collect),
                    ('Option Settlement Advice', R._optadv_items)):
        try:
            itens = fn(ref)
            print('  %-26s %d linha(s)' % (rot, len(itens)))
        except Exception as exc:                                # noqa: BLE001
            print('  %-26s ERRO: %s: %s' % (rot, type(exc).__name__, exc))
    return 0


if __name__ == '__main__':
    sys.exit(main())
