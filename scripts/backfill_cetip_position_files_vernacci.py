"""
backfill_cetip_position_files_vernacci.py
-----------------------------------------
Same backfill as scripts/backfill_cetip_position_files.py — fill the DESTINATION's
missing CETIP position files (incl. DOPERACOES) date by date, without overwriting
what is already there — but pulling the source files from the **Vernacci / Batch
Conecta** drop instead of the default OTC Tracker source.

Source tree:  I:\\Confirmation\\Derivativos\\Vernacci\\ARQUIVOS CETIP\\Batch Conecta
              \\{YYYY}\\{MM. Month}\\{DD}
Dest tree:    I:\\Confirmation\\Derivativos\\OTC Tracker\\CETIP Files\\Position Files
              \\{YYYY}\\{MM. Month}\\{DD}   (same destination as the daily routine)

Everything else — the rules, the renaming, the ';' parsing, the DOPERACOES
header+filters, the per-day JSON export, and the "fill only what's missing / skip
existing" behaviour — is reused verbatim from backfill_cetip_position_files.py.

Usage (identical flags to the main script)
    python scripts/backfill_cetip_position_files_vernacci.py --year 2026 --dry-run
    python scripts/backfill_cetip_position_files_vernacci.py --year 2026
    python scripts/backfill_cetip_position_files_vernacci.py --year 2026 --rebuild-json
    # override the source if the share path ever changes
    python scripts/backfill_cetip_position_files_vernacci.py --src "D:\\other" ...
"""
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Reuse the entire backfill implementation; only the default source differs.
import backfill_cetip_position_files as bf

# Vernacci / Batch Conecta CETIP drop. Overridable via env or the --src flag.
# ── A raiz do share ───────────────────────────────────────────────────────────
def _shared_root():
    """A MESMA raiz que a aplicação usa (`Config.SHARED_DRIVE_ROOT`).

    Escrita à mão aqui, ela ficaria em `I:\\` no dia em que a instância passasse
    a apontar para o UNC — o script "daria certo" mexendo na árvore errada. O
    fallback existe para o script continuar rodando fora do venv da aplicação."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        from apps.config import Config
        return Config.SHARED_DRIVE_ROOT
    except Exception:
        return 'I:\\'


VERNACCI_SOURCE_ROOT = os.getenv(
    'CETIP_VERNACCI_SOURCE_ROOT',
    os.path.join(_shared_root(), 'Confirmation', 'Derivativos', 'Vernacci',
                 'ARQUIVOS CETIP', 'Batch Conecta'))


if __name__ == '__main__':
    bf.main(default_src=VERNACCI_SOURCE_ROOT,
            description='Backfill CETIP position files (incl. DOPERACOES) from the '
                        'Vernacci / Batch Conecta source into the destination tree, '
                        'filling only the dates/files the destination is missing.')
