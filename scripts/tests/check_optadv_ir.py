#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""O IR de 0,005% do aviso de OPÇÃO: quem decide é o NET, e o rodapé tem de fechar.

O imposto da opção não é da linha. Ele nasce de três condições (`_optadv_apply_ir`):
só pagamento de PRÊMIO paga, a base é o NET por contraparte × data, e só quando o
banco PAGA (net < 0). Isso o código já fazia — o que quebrava era o passo seguinte.

O imposto do net é rateado pelas linhas para que toda soma da aplicação continue
sendo uma soma de linhas (a coluna do aviso, o Trade Level, o Settlement Summary).
O rateio ia para TODAS as linhas de prêmio, e a regra do líquido encolhe pelo
sinal de cada uma: a parte que caía numa linha de RECEBIMENTO era subtraída ali,
enquanto a que caía numa de PAGAMENTO era somada. As duas metades quase se
anulavam, e o rodapé — que soma a coluna — imprimia um número que não era nem o
apurado nem o apurado menos o imposto.

O caso reportado (Mondelez, 24/08/2026, seis prêmios de TRIGO):

    Resultado Apurado   (28.884,17)
    IR (0,005%)               1,44
    Resultado Final     (28.884,13)   ← errado; o certo é (28.882,73)

`(28.884,13)` é `(28.884,17)` mexido em quatro centavos — a diferença entre os
0,74 rateados nas linhas que pagam e os 0,70 nas que recebem. O imposto retido
sempre ENCOLHE o caixa, e o caixa é o net: `28.884,17 − 1,44` (a mesma conta do
Pay/Rec, HANDOFF §205 — net Pay −219.047,36 → −219.036,41).

Hoje o rateio vai só para as linhas do lado que paga. Nada é decidido por linha;
a linha carrega a parte da retenção que sai com ela, e por isso a coluna volta a
fechar com o rodapé — em qualquer tela que some linhas.

Não toca em rede nem em dado real: as linhas são sintéticas.
"""
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# Fora do Windows o share tem de ser absoluto para o `Config` importar (§8).
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(ROOT, '.check-share'))

from apps.pages import routes as R                            # noqa: E402

falhas = []


def check(label, got, exp):
    ok = got == exp
    print(('ok   ' if ok else 'FAIL ') + label + '  ->  ' + repr(got))
    if not ok:
        falhas.append('%s: %r != %r' % (label, got, exp))


def linhas(cliente, valores, premium=True):
    return [{'counterparty': cliente, 'premium': premium, 'apurado': v,
             'ir': None, 'cells': [''] * 12} for v in valores]


def totais(items):
    """O que o rodapé do aviso imprime — `_ndfc_settlement_email` soma as LINHAS."""
    ap = round(sum(r['apurado'] for r in items), 2)
    ir = round(sum(r['ir'] or 0.0 for r in items), 2)
    final = round(sum(r['liquido'] for r in items), 2)
    return ap, ir, final


# ── 1. o caso reportado ─────────────────────────────────────────────────────

print('== Mondelez 24/08/2026 — seis prêmios de TRIGO ==')
MOND = [-124942.50, -108283.50, -297893.27, 399816.00, 21946.95, 80472.15]
it = linhas('MONDELEZ BRASIL NORTE NORDESTE LTDA', MOND)
R._optadv_apply_ir(it)
ap, ir, final = totais(it)

check('Resultado Apurado é o net dos seis', ap, -28884.17)
check('IR é 0,005% do net', ir, 1.44)
check('Resultado Final é o net ENCOLHIDO pelo imposto', final, -28882.73)
check('   e não o (28.884,13) de antes', final == -28884.13, False)

# A conta que o cliente faz somando a coluna tem de dar o rodapé.
check('a coluna Líquido fecha com o rodapé', round(sum(r['liquido'] for r in it), 2), final)
check('e a coluna IR fecha com o rodapé', round(sum(r['ir'] for r in it), 2), ir)

check('só as linhas que PAGAM carregam retenção',
      [r['ir'] for r in it], [0.34, 0.29, 0.81, 0.0, 0.0, 0.0])
check('a linha que RECEBE sai com o líquido igual ao apurado',
      [r['liquido'] for r in it[3:]], MOND[3:])


# ── 2. a regra do net ───────────────────────────────────────────────────────

print('\n== quem decide é o net, não a linha ==')

# Uma linha negativa dentro de um net POSITIVO não paga nada: pela regra antiga
# do termo ela pagaria o seu próprio 0,005%.
it = linhas('CLIENTE NET POSITIVO', [-100000.0, 900000.0])
R._optadv_apply_ir(it)
check('net a favor do banco não retém nada', [r['ir'] for r in it], [0.0, 0.0])
check('   e o líquido é o apurado', [r['liquido'] for r in it], [-100000.0, 900000.0])

# E o inverso: o imposto é do net, não da perna.
it = linhas('CLIENTE NET NEGATIVO', [-1000000.0, 900000.0])
R._optadv_apply_ir(it)
ap, ir, final = totais(it)
check('o imposto é 0,005% do NET, não da perna', ir, 5.0)
check('   (por linha seriam R$ 50,00 sobre um caixa que não existe)', ir == 50.0, False)
check('   e o rodapé fecha', (ap, final), (-100000.0, -99995.0))

# Recompra e exercício não pagam, e não entram na base.
it = linhas('CLIENTE COM EXERCICIO', [-200000.0]) + \
     linhas('CLIENTE COM EXERCICIO', [-800000.0], premium=False)
R._optadv_apply_ir(it)
ap, ir, final = totais(it)
check('só o prêmio entra na base', ir, 10.0)
check('   e o exercício sai sem imposto', it[1]['ir'], 0.0)
check('   o rodapé soma os dois assim mesmo', (ap, final), (-1000000.0, -999990.0))


# ── 3. o rateio ─────────────────────────────────────────────────────────────

print('\n== o rateio nas linhas que pagam ==')

# A sobra do arredondamento fecha na última: a soma da coluna é EXATAMENTE o
# imposto do net, e não a soma de seis arredondamentos.
it = linhas('CLIENTE TRES PERNAS', [-33333.33, -33333.33, -33333.34])
R._optadv_apply_ir(it)
ap, ir, final = totais(it)
check('a soma das partes é o imposto do net', ir, round(abs(ap) * 0.00005, 2))
check('   e o rodapé continua fechando', final, round(ap + ir, 2))

# Duas contrapartes no mesmo lote não se misturam.
it = linhas('CLIENTE A', [-400000.0]) + linhas('CLIENTE B', [-600000.0])
R._optadv_apply_ir(it)
check('cada contraparte tem o seu net', [r['ir'] for r in it], [20.0, 30.0])


# ── 4. a isenção ────────────────────────────────────────────────────────────

print('\n== a isenção sai do mesmo cadastro do termo ==')
isentos = [str(row.get('CLIENT', '') or '').strip()
           for row in R._mapping_rows('ndfc-ir-exempt')]
isentos = [n for n in isentos if n]
if isentos:
    it = linhas(isentos[0], [-1000000.0])
    R._optadv_apply_ir(it)
    check('contraparte isenta não retém (%s)' % isentos[0][:22],
          (it[0]['ir'], it[0]['liquido']), (0.0, -1000000.0))
else:
    print('ok   cadastro `ndf-ir-exempt` vazio — nada a conferir')


# ── 5. o rodapé do e-mail continua sendo a soma das linhas ──────────────────

print('\n== o rodapé do aviso ==')
SRC = open(os.path.join(ROOT, 'apps', 'pages', 'otc_emails.py'), encoding='utf-8').read()
bloco = SRC.split('def _ndfc_settlement_email', 1)[1].split('\ndef ', 1)[0]
check('o Resultado Final do aviso soma a coluna Líquido',
      "final = sum(float(t.get('liquido') or 0.0) for t in items)" in bloco, True)
check('   e o IR soma a coluna IR',
      "ir = sum(float(t.get('ir') or 0.0) for t in items)" in bloco, True)
# É essa soma que torna o rateio de um lado só obrigatório: com o rateio dos dois
# lados, este mesmo rodapé imprimia (28.884,13).

print()
if falhas:
    for f in falhas:
        print('FAIL ' + f)
    sys.exit(1)
print('TUDO OK')
