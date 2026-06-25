"""
Settlement Forecast — professional chart generation (Matplotlib + Seaborn).

Renders high-resolution PNGs to embed (cid) in the Settlement Forecast e-mail.
Server-safe: forces the non-interactive 'Agg' backend BEFORE importing pyplot, so
it runs head-less inside Flask/Gunicorn with no display.

Design language (clean, professional data-viz — Senior DS / data-viz guidelines):
  * seaborn ``whitegrid`` theme, top/right spines removed (despine)
  * cohesive, accessible categorical palette (fixed colour per product / entity)
  * bold left-aligned titles + muted subtitle, clear axis labels, readable fonts
  * figure size tuned for e-mail width; high DPI for crisp rendering
  * data labels (totals) on top of stacked bars for instant reading

The public entry-point is :func:`generate_forecast_charts`, which writes the PNGs
and returns their paths. The module can also be run directly (``python -m
apps.pages.forecast_charts`` or via ``scripts/forecast_charts_demo.py``) with
synthetic data to preview the look locally.
"""
from __future__ import annotations

import os
import matplotlib
matplotlib.use('Agg')                       # head-less / server rendering — MUST precede pyplot
import matplotlib.pyplot as plt             # noqa: E402
import matplotlib.ticker as mticker         # noqa: E402
import seaborn as sns                       # noqa: E402

# ── Output resolution ─────────────────────────────────────────────────────────
# 200 dpi keeps the embedded PNGs crisp while keeping the e-mail light. Bump to
# 300 for print-grade exports (heavier attachments).
DPI = 200

# ── Cohesive, accessible palettes (fixed so colours never shift run-to-run) ────
PRODUCT_COLORS = {
    'NDF Moeda':         '#0066cc',   # action blue (app accent)
    'OPÇÃO Moeda':       '#1ba0d4',
    'OPÇÃO Commodities': '#17b39a',
    'OPÇÃO Equities':    '#7c5cd6',
    'SWAP CEM':          '#f5a524',
    'SWAP EDG':          '#e5484d',
    'SWAP CEMHYB':       '#8a929e',
}
ENTITY_COLORS = {
    'LAWTON':  '#0066cc',
    'MGT':     '#17b39a',
    'ATACAMA': '#f5a524',
}
_FALLBACK = '#b0b7c3'

# Brand-ish neutrals reused across charts
_INK   = '#1d1d1f'
_MUTED = '#6e6e73'
_FAINT = '#54545a'


def _apply_theme() -> None:
    """Apply the shared seaborn/matplotlib theme (idempotent)."""
    sns.set_theme(style='whitegrid', context='notebook')
    plt.rcParams.update({
        'font.family':      'DejaVu Sans',     # bundled with matplotlib → predictable everywhere
        'axes.titleweight': 'bold',
        'axes.titlecolor':  _INK,
        'axes.labelcolor':  _INK,
        'axes.edgecolor':   '#d6d9e0',
        'text.color':       _INK,
        'xtick.color':      _FAINT,
        'ytick.color':      _FAINT,
        'figure.facecolor': 'white',
        'axes.facecolor':   'white',
        'grid.color':       '#eceef2',
        'grid.linewidth':   0.9,
        'axes.axisbelow':   True,
    })


def _color_for(label: str, palette: dict) -> str:
    return palette.get(label, _FALLBACK)


def _stacked_bar(date_labels, series, palette, title, subtitle, ylabel, path):
    """Render one stacked bar chart (x = business days, stacks = categories).

    ``series`` is an ordered list of ``(label, [values per day])`` tuples.
    """
    _apply_theme()
    fig, ax = plt.subplots(figsize=(12, 6), dpi=DPI)

    x = list(range(len(date_labels)))
    bottoms = [0.0] * len(date_labels)
    for label, values in series:
        ax.bar(x, values, bottom=bottoms, width=0.66,
               color=_color_for(label, palette), label=label,
               edgecolor='white', linewidth=0.7, zorder=3)
        bottoms = [b + v for b, v in zip(bottoms, values)]

    # Per-day totals on top of each stack
    ymax = max(bottoms) if bottoms else 0
    for xi, tot in zip(x, bottoms):
        if tot > 0:
            ax.text(xi, tot + ymax * 0.012, str(int(round(tot))),
                    ha='center', va='bottom', fontsize=9.5,
                    fontweight='bold', color=_INK, zorder=4)

    ax.set_xticks(x)
    ax.set_xticklabels(date_labels, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True, nbins=6))
    if ymax > 0:
        ax.set_ylim(0, ymax * 1.16)

    ax.set_title(title, fontsize=17, pad=26, loc='left')
    ax.text(0.0, 1.015, subtitle, transform=ax.transAxes, fontsize=11,
            color=_MUTED, ha='left', va='bottom')

    sns.despine(ax=ax, top=True, right=True)
    ax.grid(axis='x', visible=False)
    ax.margins(x=0.015)
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.13),
              ncol=min(len(series), 4), frameon=False, fontsize=10,
              handlelength=1.1, columnspacing=1.6, handletextpad=0.5)

    fig.savefig(path, bbox_inches='tight', dpi=DPI, facecolor='white')
    plt.close(fig)
    return path


def _donut(totals, palette, title, subtitle, path):
    """Render a product-mix donut from ``totals`` = ordered ``(label, value)``."""
    _apply_theme()
    totals = [(l, v) for l, v in totals if v > 0]
    fig, ax = plt.subplots(figsize=(7.6, 6), dpi=DPI)
    if not totals:
        ax.text(0.5, 0.5, 'No upcoming settlements', ha='center', va='center',
                fontsize=13, color=_MUTED, transform=ax.transAxes)
        ax.axis('off')
        fig.savefig(path, bbox_inches='tight', dpi=DPI, facecolor='white')
        plt.close(fig)
        return path

    labels  = [l for l, _ in totals]
    values  = [v for _, v in totals]
    colors  = [_color_for(l, palette) for l in labels]
    grand   = sum(values)

    wedges, _ = ax.pie(
        values, colors=colors, startangle=90, counterclock=False,
        wedgeprops=dict(width=0.42, edgecolor='white', linewidth=2))
    ax.set(aspect='equal')

    # Center total
    ax.text(0, 0.08, str(int(round(grand))), ha='center', va='center',
            fontsize=26, fontweight='bold', color=_INK)
    ax.text(0, -0.16, 'settlements', ha='center', va='center',
            fontsize=11, color=_MUTED)

    ax.set_title(title, fontsize=17, pad=22, loc='center')
    ax.text(0.5, 1.015, subtitle, transform=ax.transAxes, fontsize=11,
            color=_MUTED, ha='center', va='bottom')

    legend_labels = ['{}  ·  {} ({:.0%})'.format(l, int(v), v / grand)
                     for l, v in totals]
    ax.legend(wedges, legend_labels, loc='center left',
              bbox_to_anchor=(1.0, 0.5), frameon=False, fontsize=10.5)

    fig.savefig(path, bbox_inches='tight', dpi=DPI, facecolor='white')
    plt.close(fig)
    return path


def _order_series(mapping, color_keys):
    """Order a {label: [values]} mapping by the palette order (known first), then
    drop all-zero series so empty products/entities never clutter the chart."""
    ordered = [k for k in color_keys if k in mapping]
    ordered += [k for k in mapping if k not in ordered]
    return [(k, mapping[k]) for k in ordered if sum(mapping[k]) > 0]


def generate_forecast_charts(date_labels, by_product, by_entity, out_dir,
                             prefix='forecast'):
    """Generate the Settlement Forecast chart set and return a dict of file paths.

    Parameters
    ----------
    date_labels : list[str]      x-axis labels (upcoming business days, e.g. '25/06')
    by_product  : dict[str, list[int]]   product -> count per business day
    by_entity   : dict[str, list[int]]   entity  -> count per business day
    out_dir     : str            directory to write the PNGs into
    prefix      : str            filename prefix

    Returns
    -------
    dict with keys 'by_product', 'by_entity', 'mix' -> absolute PNG paths.
    """
    os.makedirs(out_dir, exist_ok=True)
    prod_series = _order_series(by_product, PRODUCT_COLORS)
    ent_series  = _order_series(by_entity, ENTITY_COLORS)

    p_product = os.path.join(out_dir, '{}_by_product.png'.format(prefix))
    p_entity  = os.path.join(out_dir, '{}_by_entity.png'.format(prefix))
    p_mix     = os.path.join(out_dir, '{}_mix.png'.format(prefix))

    _stacked_bar(
        date_labels, prod_series, PRODUCT_COLORS,
        'Settlements by Product', 'Upcoming settlements per business day, stacked by product',
        'Number of settlements', p_product)

    _stacked_bar(
        date_labels, ent_series, ENTITY_COLORS,
        'Settlements by Entity', 'Upcoming settlements per business day, stacked by entity',
        'Number of settlements', p_entity)

    mix_totals = [(l, sum(v)) for l, v in prod_series]
    _donut(mix_totals, PRODUCT_COLORS,
           'Product Mix', 'Share of upcoming settlements by product', p_mix)

    return {'by_product': p_product, 'by_entity': p_entity, 'mix': p_mix}


# ── Local preview with synthetic data ─────────────────────────────────────────
def _demo(out_dir=None):
    """Generate the chart set with realistic synthetic data for a local preview."""
    out_dir = out_dir or os.path.join(os.path.dirname(__file__), '..', '..', '_chart_preview')
    out_dir = os.path.abspath(out_dir)

    date_labels = ['25/06', '26/06', '27/06', '30/06', '01/07',
                   '02/07', '03/07', '04/07', '07/07', '08/07']
    n = len(date_labels)
    # Synthetic counts per product across the business-day spine
    by_product = {
        'NDF Moeda':         [12, 8, 15, 6, 9, 11, 7, 4, 10, 5],
        'OPÇÃO Moeda':       [4, 6, 3, 5, 2, 7, 4, 3, 6, 2],
        'OPÇÃO Commodities': [1, 2, 0, 3, 1, 0, 2, 1, 0, 1],
        'OPÇÃO Equities':    [0, 1, 2, 0, 1, 1, 0, 2, 1, 0],
        'SWAP CEM':          [5, 3, 7, 4, 6, 2, 5, 3, 4, 6],
        'SWAP EDG':          [2, 4, 1, 3, 2, 5, 1, 2, 3, 1],
        'SWAP CEMHYB':       [1, 0, 2, 1, 0, 1, 2, 0, 1, 0],
    }
    by_entity = {
        'LAWTON':  [14, 11, 18, 9, 12, 16, 10, 8, 15, 9],
        'MGT':     [7, 9, 6, 8, 5, 7, 6, 4, 7, 3],
        'ATACAMA': [4, 4, 6, 5, 4, 4, 5, 3, 3, 3],
    }
    paths = generate_forecast_charts(date_labels, by_product, by_entity, out_dir)
    print('Charts written to:', out_dir)
    for k, p in paths.items():
        print('  {:<11} {}'.format(k, p))
    return paths


if __name__ == '__main__':
    _demo()
