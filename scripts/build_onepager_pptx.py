# -*- coding: utf-8 -*-
"""Gera OTC_Tracker_One_Pager.pptx — um slide 16:9 sobre o que o sistema faz.

Uso:

    pip install python-pptx           # uma vez (não é dependência do app)
    python scripts/build_onepager_pptx.py
    python scripts/build_onepager_pptx.py /tmp/previa.html   # + prévia HTML

Paleta e geometria são as da própria aplicação (`visual-refresh.css`): gradiente
#0066cc → #5e5ce6 → #8b5cf6 → #d946ef, cartão branco com borda leve e canto
arredondado — o slide tem de parecer o sistema.

O conteúdo é CAPACIDADE e FLUXO, mais os benefícios já entregues (a pedido:
consolidação das Intelligent Solutions e a redução de 0,5 FTE, no rodapé).
Para editar o texto, mexa em `PILARES` e `COLUNAS` e rode de novo — o arquivo é
gerado, não editado à mão, senão a próxima rodada apaga a edição.
"""
import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
OUT = os.path.join(ROOT, 'OTC_Tracker_One_Pager.pptx')

# ── Paleta (visual-refresh.css) ──────────────────────────────────────────────
A1, A2, A3, A4 = '0066CC', '5E5CE6', '8B5CF6', 'D946EF'
INK = RGBColor(0x0E, 0x11, 0x2A)
INK_SOFT = RGBColor(0x54, 0x5A, 0x72)
INK_FAINT = RGBColor(0x7B, 0x82, 0x99)
CARD_BG = RGBColor(0xFF, 0xFF, 0xFF)
CARD_BD = RGBColor(0xE3, 0xE6, 0xEF)
PAGE_BG = RGBColor(0xF6, 0xF7, 0xFB)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = 'Segoe UI'

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
slide = prs.slides.add_slide(prs.slide_layouts[6])          # em branco


def _no_line(shape):
    shape.line.fill.background()


def rect(x, y, w, h, fill=None, radius=None, line=None, line_w=Pt(1)):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius is not None else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h))
    shp.shadow.inherit = False
    if radius is not None:
        # adj = raio / menor lado
        shp.adjustments[0] = radius / min(w, h)
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line is None:
        _no_line(shp)
    else:
        shp.line.color.rgb = line
        shp.line.width = line_w
    shp.text_frame.word_wrap = True
    return shp


def gradient(shape, stops, angle_deg=100):
    """Gradiente linear multi-parada — python-pptx só expõe duas, então o
    preenchimento é escrito direto no XML da forma."""
    spPr = shape._element.spPr
    for tag in ('a:solidFill', 'a:noFill', 'a:gradFill', 'a:blipFill', 'a:pattFill'):
        for el in spPr.findall(qn(tag)):
            spPr.remove(el)
    from pptx.oxml import parse_xml
    from pptx.oxml.ns import nsdecls
    gs = ''.join(
        '<a:gs pos="%d"><a:srgbClr val="%s"/></a:gs>' % (int(pos * 1000), color)
        for pos, color in stops)
    xml = ('<a:gradFill %s rotWithShape="1"><a:gsLst>%s</a:gsLst>'
           '<a:lin ang="%d" scaled="0"/></a:gradFill>'
           % (nsdecls('a'), gs, int(angle_deg * 60000)))
    frag = parse_xml(xml)
    # o preenchimento vem logo depois da geometria
    ref = spPr.find(qn('a:prstGeom'))
    ref.addnext(frag)


def text(shape, blocks, margins=(0.14, 0.10, 0.14, 0.10), anchor=MSO_ANCHOR.TOP):
    """blocks: [(texto, tamanho, negrito, cor, espaço_antes, alinhamento, espaçamento)]"""
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    l, t, r, b = margins
    tf.margin_left, tf.margin_top = Inches(l), Inches(t)
    tf.margin_right, tf.margin_bottom = Inches(r), Inches(b)
    for i, blk in enumerate(blocks):
        txt, size, bold, color, space, align, spacing = (list(blk) + [None] * 7)[:7]
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align or PP_ALIGN.LEFT
        if space:
            p.space_before = Pt(space)
        p.line_spacing = spacing or 1.0
        run = p.add_run()
        run.text = txt
        f = run.font
        f.name, f.size, f.bold = FONT, Pt(size), bool(bold)
        f.color.rgb = color
    return shape


def textbox(x, y, w, h, blocks, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    return text(box, blocks, margins=(0, 0, 0, 0), anchor=anchor)


# ── Fundo ────────────────────────────────────────────────────────────────────
rect(0, 0, 13.333, 7.5, fill=PAGE_BG)

# ── Faixa do cabeçalho ───────────────────────────────────────────────────────
band = rect(0, 0, 13.333, 1.42)
gradient(band, [(0, A1), (0.5, A2), (0.8, A3), (1, A4)])

textbox(0.62, 0.24, 8.6, 0.95, [
    ('OTC Tracker', 30, True, WHITE, None, None, 1.0),
    ('One platform for the full OTC derivatives lifecycle — Brazil OTC Operations',
     14, False, RGBColor(0xE4, 0xEC, 0xFF), 3, None, 1.0),
])
textbox(7.25, 0.56, 5.45, 0.4, [
    ('Trade capture  ›  B3 / CETIP registration  ›  Client confirmation  ›  Settlement',
     9.5, True, RGBColor(0xEB, 0xF1, 0xFF), None, PP_ALIGN.RIGHT, 1.0),
])

# ── Quatro pilares ───────────────────────────────────────────────────────────
PILARES = [
    (A1, 'One solution, end to end',
     'Registration, confirmation, settlement and regulatory reporting live in the '
     'same place — every user reads and writes the same data.',
     ['100+ screens covering NDF, FX and commodity options, swaps, unwinds and intragroup legs',
      'The step that follows always knows what the previous one did — no re-keying between tools',
      'No side spreadsheet as the source of truth — nothing left to reconcile between tools']),
    (A2, 'The routine runs itself',
     'What used to be typed, copied or remembered is now imported, generated or '
     'scheduled — people are left with the decisions.',
     ['Trades pulled from Athena automatically — NDF every 20 minutes, FX options hourly',
      'Client confirmations, settlement advices and B3 / CETIP files produced by the solution',
      'Daily routines e-mail each user exactly what is still open, without anyone asking']),
    (A3, 'Controls built into the flow',
     'The check is part of the screen, not a separate review — so nothing depends '
     'on someone remembering to do it.',
     ['Confirmation trail OTC › MO / FO, with each stage signed only by its own users',
      'Deadlines in business days; signing off late requires a written justification',
      'Every action stamped with date, time and employee ID, plus maker / checker on the data']),
    (A4, 'Changes without a release',
     'The rules the users own are edited on screen and take effect on the next '
     'click — no code change, no deployment window.',
     ['25 on-screen registries hold the mappings that used to be hard-coded',
      'Access granted page by page — and routine by routine inside the Control Panel',
      'One code base serving users in English, Portuguese and Spanish']),
]

CARD_Y, CARD_H, CARD_W, GAP, X0 = 1.62, 3.50, 2.98, 0.24, 0.62
for i, (accent, titulo, lead, bullets) in enumerate(PILARES):
    x = X0 + i * (CARD_W + GAP)
    card = rect(x, CARD_Y, CARD_W, CARD_H, fill=CARD_BG, radius=0.17, line=CARD_BD, line_w=Pt(0.75))
    # faixa de acento no topo do cartão
    tab = rect(x + 0.22, CARD_Y + 0.28, 0.52, 0.075, fill=RGBColor.from_string(accent), radius=0.037)
    textbox(x + 0.22, CARD_Y + 0.48, CARD_W - 0.44, 0.62, [
        (titulo, 15, True, INK, None, None, 1.02),
    ])
    textbox(x + 0.22, CARD_Y + 1.00, CARD_W - 0.44, 0.85, [
        (lead, 10, False, INK_SOFT, None, None, 1.24),
    ])
    y = CARD_Y + 1.88
    for b in bullets:
        dot = rect(x + 0.24, y + 0.075, 0.062, 0.062, fill=RGBColor.from_string(accent), radius=0.031)
        textbox(x + 0.40, y - 0.015, CARD_W - 0.62, 0.72, [
            (b, 9.5, False, INK, None, None, 1.2),
        ])
        y += 0.50

# ── Cobertura dos processos de OTC Derivatives ───────────────────────────────
# Comparação pedida pela mesa: quanto do processo cada ferramenta cobre — o
# OTC Tracker (completo e o já entregue) contra o que a tech já desenvolveu
# (Cockpit + AEVO + Registration). Tracker nas cores da marca, stack da tech em
# cinza — a barra é a comparação, não decoração.
GRAY_BAR = '9AA3B8'
COBERTURA = [
    ('OTC Tracker — Full',            62.14, A1),
    ('OTC Tracker — Today',           33.01, A2),
    ('Cockpit + AEVO + Registration', 14.56, GRAY_BAR),
    ('Cockpit',                        9.71, GRAY_BAR),
]
COV_Y, COV_H = 5.24, 0.62
COV_LBL_W = 1.95                     # bloco do rótulo à esquerda
COV_IW = (12.09 - COV_LBL_W - 0.30) / len(COBERTURA)
rect(0.62, COV_Y, 12.09, COV_H, fill=CARD_BG, radius=0.17, line=CARD_BD, line_w=Pt(0.75))
textbox(0.92, COV_Y + 0.12, COV_LBL_W - 0.35, 0.42, [
    ('PROCESS COVERAGE', 9, True, INK, None, None, 1.0),
    ('OTC Derivatives', 8, False, INK_SOFT, 2, None, 1.0),
])
for i, (nome, pct, accent) in enumerate(COBERTURA):
    ix = 0.62 + COV_LBL_W + i * COV_IW
    textbox(ix, COV_Y + 0.10, COV_IW - 0.25, 0.25, [
        (nome, 8, False, INK, None, None, 1.0),
    ])
    track_w = COV_IW - 0.78
    rect(ix, COV_Y + 0.385, track_w, 0.085, fill=RGBColor(0xEC, 0xEE, 0xF5), radius=0.042)
    rect(ix, COV_Y + 0.385, max(track_w * pct / 100.0, 0.06), 0.085,
         fill=RGBColor.from_string(accent), radius=0.042)
    textbox(ix + track_w + 0.08, COV_Y + 0.315, 0.62, 0.25, [
        ('%.2f%%' % pct, 9, True, RGBColor.from_string(accent), None, None, 1.0),
    ])

# ── Rodapé: o que a solução conversa e o que ela vigia ───────────────────────
FOOT_Y, FOOT_H = 6.02, 1.06
foot = rect(0.62, FOOT_Y, 12.09, FOOT_H, fill=CARD_BG, radius=0.17, line=CARD_BD, line_w=Pt(0.75))

# Com QUATRO colunas o texto de cada uma tem de ser mais curto que o das três
# antigas — a largura cai de 4,03" para 3,02" e o corpo não pode passar de
# ~3 linhas, senão vaza do cartão do rodapé.
COLUNAS = [
    ('Connected to', A1,
     'Athena  ·  B3 / CETIP  ·  Reference Data  ·  Electronic Inventory  ·  '
     'SSO + 2FA  ·  E-mail and push'),
    ('Reconciles', A2,
     'FX options: CETIP × Athena end-of-day  ·  Pay / Rec  ·  Comitente  ·  '
     'B3 return files'),
    ('Keeps in sight', A3,
     'New Deals and Confirmations Monitors  ·  KPI and daily metrics  ·  '
     'Alerts when something is late'),
    ('Benefits delivered', A4,
     'Several Intelligent Solutions consolidated in one place  ·  '
     '0.5 FTE reduction already delivered'),
]
CW = 12.09 / len(COLUNAS)
for i, (rotulo, accent, corpo) in enumerate(COLUNAS):
    cx = 0.62 + i * CW
    if i:
        rect(cx, FOOT_Y + 0.22, 0.008, FOOT_H - 0.44, fill=RGBColor(0xEC, 0xEE, 0xF5))
    textbox(cx + 0.30, FOOT_Y + 0.22, CW - 0.55, 0.3, [
        (rotulo.upper(), 9, True, RGBColor.from_string(accent), None, None, 1.0),
    ])
    textbox(cx + 0.30, FOOT_Y + 0.52, CW - 0.55, 0.62, [
        (corpo, 9.5, False, INK_SOFT, None, None, 1.22),
    ])

# ── Assinatura ───────────────────────────────────────────────────────────────
textbox(0.62, 7.18, 12.09, 0.3, [
    ('Internal use — Brazil OTC Operations, J.P. Morgan', 8.5, False, INK_FAINT, None, None, 1.0),
])

prs.save(OUT)
print('OK ->', OUT)

# ── Prévia HTML (opcional) ───────────────────────────────────────────────────
# Só roda com um caminho no argv: `python scripts/build_onepager_pptx.py /tmp/p.html`.
# Serve para CONFERIR composição e transbordo de texto sem abrir o PowerPoint —
# a mesma geometria (as mesmas polegadas × 96 px) desenhada em HTML, a partir do
# mesmo `PILARES`/`COLUNAS`, então as duas não divergem. Fica de fora por padrão
# para não largar um .html na raiz do repo.
import sys

if len(sys.argv) < 2:
    raise SystemExit(0)
PREVIEW = sys.argv[1]
PX = 96


def px(v):
    return '%.1fpx' % (v * PX)


bl = []
for i, (accent, titulo, lead, bullets) in enumerate(PILARES):
    x = X0 + i * (CARD_W + GAP)
    itens = ''.join(
        '<div style="position:absolute;left:%s;top:%s;width:%s">'
        '<span style="position:absolute;left:-%s;top:6px;width:6px;height:6px;'
        'border-radius:3px;background:#%s"></span>'
        '<div style="font-size:9.5pt;line-height:1.2;color:#0E112A">%s</div></div>'
        % (px(0.40), px(1.88 - 0.015 + j * 0.50), px(CARD_W - 0.62), px(0.16), accent, b)
        for j, b in enumerate(bullets))
    bl.append(
        '<div style="position:absolute;left:%s;top:%s;width:%s;height:%s;background:#fff;'
        'border:1px solid #E3E6EF;border-radius:%s;box-sizing:border-box">'
        '<div style="position:absolute;left:%s;top:%s;width:%s;height:%s;border-radius:3px;background:#%s"></div>'
        '<div style="position:absolute;left:%s;top:%s;width:%s;font:700 15pt %s;color:#0E112A;line-height:1.02">%s</div>'
        '<div style="position:absolute;left:%s;top:%s;width:%s;font-size:10pt;color:#545A72;line-height:1.24">%s</div>'
        '%s</div>'
        % (px(x), px(CARD_Y), px(CARD_W), px(CARD_H), px(0.17),
           px(0.22), px(0.28), px(0.52), px(0.075), accent,
           px(0.22), px(0.48), px(CARD_W - 0.44), FONT, titulo,
           px(0.22), px(1.00), px(CARD_W - 0.44), lead, itens))

# faixa de cobertura — mesma geometria e mesmo `COBERTURA` do slide
cov_items = []
for i, (nome, pct, accent) in enumerate(COBERTURA):
    ix = COV_LBL_W + i * COV_IW
    track_w = COV_IW - 0.78
    cov_items.append(
        '<div style="position:absolute;left:%s;top:0;width:%s">'
        '<div style="position:absolute;left:0;top:%s;width:%s;font-size:8pt;color:#0E112A;white-space:nowrap">%s</div>'
        '<div style="position:absolute;left:0;top:%s;width:%s;height:%s;border-radius:4px;background:#ECEEF5"></div>'
        '<div style="position:absolute;left:0;top:%s;width:%s;height:%s;border-radius:4px;background:#%s"></div>'
        '<div style="position:absolute;left:%s;top:%s;font:700 9pt %s;color:#%s">%s</div>'
        '</div>'
        % (px(ix), px(COV_IW),
           px(0.10), px(COV_IW - 0.25), nome,
           px(0.385), px(track_w), px(0.085),
           px(0.385), px(max(track_w * pct / 100.0, 0.06)), px(0.085), accent,
           px(track_w + 0.08), px(0.315), FONT, accent, '%.2f%%' % pct))
cov = (
    '<div style="position:absolute;left:%s;top:%s;width:%s;height:%s;background:#fff;'
    'border:1px solid #E3E6EF;border-radius:%s;box-sizing:border-box">'
    '<div style="position:absolute;left:%s;top:%s;font:700 9pt %s;color:#0E112A;letter-spacing:.04em">PROCESS COVERAGE</div>'
    '<div style="position:absolute;left:%s;top:%s;font-size:8pt;color:#545A72">OTC Derivatives</div>'
    '%s</div>'
    % (px(0.62), px(COV_Y), px(12.09), px(COV_H), px(0.17),
       px(0.30), px(0.12), FONT,
       px(0.30), px(0.32),
       ''.join(cov_items)))

cols = []
for i, (rotulo, accent, corpo) in enumerate(COLUNAS):
    cx = i * CW
    cols.append(
        '<div style="position:absolute;left:%s;top:%s;width:%s">'
        '%s'
        '<div style="position:absolute;left:%s;top:%s;font:700 9pt %s;color:#%s;letter-spacing:.04em">%s</div>'
        '<div style="position:absolute;left:%s;top:%s;width:%s;font-size:9.5pt;color:#545A72;line-height:1.22">%s</div>'
        '</div>'
        % (px(cx), '0px', px(CW),
           ('' if not i else '<div style="position:absolute;left:0;top:%s;width:1px;height:%s;background:#ECEEF5"></div>'
            % (px(0.22), px(FOOT_H - 0.44))),
           px(0.30), px(0.22), FONT, accent, rotulo.upper(),
           px(0.30), px(0.52), px(CW - 0.55), corpo))

html = (
    '<div style="position:relative;width:%s;height:%s;background:#F6F7FB;'
    'font-family:%s,Helvetica,Arial,sans-serif;overflow:hidden">'
    '<div style="position:absolute;inset:0 0 auto 0;height:%s;'
    'background:linear-gradient(100deg,#0066CC,#5E5CE6 50%%,#8B5CF6 80%%,#D946EF)"></div>'
    '<div style="position:absolute;left:%s;top:%s;width:%s;font:700 30pt %s;color:#fff;line-height:1">OTC Tracker</div>'
    '<div style="position:absolute;left:%s;top:%s;width:%s;font-size:14pt;color:#E4ECFF">'
    'One platform for the full OTC derivatives lifecycle — Brazil OTC Operations</div>'
    '<div style="position:absolute;left:%s;top:%s;width:%s;text-align:right;font:700 9.5pt %s;'
    'color:#EBF1FF;line-height:1.18">Trade capture &nbsp;›&nbsp; B3 / CETIP registration &nbsp;›&nbsp; '
    'Client confirmation &nbsp;›&nbsp; Settlement</div>'
    '%s'
    '%s'
    '<div style="position:absolute;left:%s;top:%s;width:%s;height:%s;background:#fff;border:1px solid #E3E6EF;'
    'border-radius:%s;box-sizing:border-box">%s</div>'
    '<div style="position:absolute;left:%s;top:%s;font-size:8.5pt;color:#7B8299">'
    'Internal use — Brazil OTC Operations, J.P. Morgan</div>'
    '</div>'
    % (px(13.333), px(7.5), FONT, px(1.42),
       px(0.62), px(0.24), px(8.6), FONT,
       px(0.62), px(0.80), px(8.6),
       px(7.25), px(0.56), px(5.45), FONT,
       ''.join(bl), cov,
       px(0.62), px(FOOT_Y), px(12.09), px(FOOT_H), px(0.17), ''.join(cols),
       px(0.62), px(7.18)))

with open(PREVIEW, 'w', encoding='utf-8') as fh:
    fh.write('<!doctype html><meta charset="utf-8"><body style="margin:0">' + html)
print('prévia ->', PREVIEW)
