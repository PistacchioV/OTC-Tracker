# -*- coding: utf-8 -*-
"""Reemite a ÚLTIMA posição B3 local numa data recente — dado de DEMONSTRAÇÃO
para a máquina de desenvolvimento.

Por quê: os arquivos de posição (DPOSICAO*/DFLUXO/DAGENDAPREMIOS) da dev são
um mock esparso parado em 24/07/2026. O dashboard anda no máximo 10 dias
úteis para trás procurando posição (`_forecast_latest_ref`,
`api_dashboard_live_position`) e o Settlement Forecast olha os PRÓXIMOS 15
dias úteis a partir dela — passado um mês, a Live Position mostra 0, o
"By product" diz "No position files for this date" e o Forecast "No deals
found for the period", sem nada errado no código.

O que faz: copia cada JSON do último dia com posição para a data alvo
(padrão: D-1 ANBIMA de hoje), deslocando TODA data dos registros pelo MESMO
número de dias úteis que separa as duas referências — um vencimento que
estava 8 dias úteis à frente da posição continua 8 dias úteis à frente. O
formato de cada campo é preservado (`20260724` fica AAAAMMDD, `07/08/2026`
fica DD/MM/AAAA), e o `Data do Arquivo` vira a data alvo.

O espelho DuckDB não precisa de nada: o leitor DB-only cura sozinho (o
manifest não casa com o arquivo novo e o `duck_read` converte na hora).

Só para a DEV: recusa rodar quando o `DATA_DIR` está fora do repositório
(o share do JPM), a menos que `--allow-external` seja passado.

    python scripts/dev_seed_positions.py                 # último dia → D-1
    python scripts/dev_seed_positions.py --to 2026-09-04
    python scripts/dev_seed_positions.py --from 2026-07-24 --to 2026-09-04 --force
"""
import argparse
import os
import re
import sys
from datetime import datetime

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.config import Config                           # noqa: E402
from apps.pages import routes as R                       # noqa: E402
from apps.pages import data_store as S                   # noqa: E402

CATEGORIES = ('NDF', 'Option', 'Swap', 'Operations')
_RE_YMD = re.compile(r'^(\d{4})(\d{2})(\d{2})$')
_RE_DMY = re.compile(r'^(\d{2})/(\d{2})/(\d{4})$')


_DATE_KEY_HINTS = ('data', 'date', 'venc', 'evento', 'liquid')


def _parse_any(s, key=''):
    """(datetime, fmt) para os dois formatos que o mock usa; (None, None) senão.
    O AAAAMMDD só vale em coluna cujo NOME diga que é data: um código de conta
    de oito dígitos (`00041007`) é uma data válida para o regex — ano 4, dia 7 —
    e saía deslocado junto, trocando a contraparte da linha em silêncio."""
    s = str(s or '').strip()
    m = _RE_YMD.match(s)
    if m and any(h in str(key).lower() for h in _DATE_KEY_HINTS):
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))), '%Y%m%d'
        except ValueError:
            return None, None
    m = _RE_DMY.match(s)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))), '%d/%m/%Y'
        except ValueError:
            return None, None
    return None, None


def _shift(value, src_ref, dst_ref, key=''):
    """Desloca UMA data pelo offset em dias úteis que ela tinha da referência
    de origem. Datas ANTES da referência (histórico) andam pelo mesmo número
    de dias úteis para trás. Valor que não é data volta intacto."""
    d, fmt = _parse_any(value, key)
    if d is None:
        return value
    if d >= src_ref:
        nd = R._anbima_add_biz(dst_ref, R._anbima_biz_diff(src_ref, d))
    else:
        back = R._anbima_biz_diff(d, src_ref)
        nd = dst_ref
        for _ in range(back):
            nd = R._prev_anbima_bizday(nd)
    return nd.strftime(fmt)


def _day_dir(cat, ref):
    return os.path.join(R.B3_JSON_ROOT, cat, R._b3_date_subpath(ref.strftime('%y%m%d')))


def _latest_source_day(max_back_days=400):
    """Anda o calendário para trás a partir de hoje até achar um dia com
    posição em alguma categoria."""
    from datetime import timedelta
    cur = datetime.now()
    for _ in range(max_back_days):
        for cat in CATEGORIES:
            d = _day_dir(cat, cur)
            if S.isdir(d) and any(f.endswith('.json') and not f.endswith('.meta.json')
                                  for f in S.listdir(d)):
                return cur.replace(hour=0, minute=0, second=0, microsecond=0)
        cur -= timedelta(days=1)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--from', dest='src', help='dia de origem (YYYY-MM-DD); padrão: o último com posição')
    ap.add_argument('--to', dest='dst', help='dia alvo (YYYY-MM-DD); padrão: D-1 ANBIMA de hoje')
    ap.add_argument('--force', action='store_true', help='sobrescreve arquivo já existente no alvo')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--allow-external', action='store_true',
                    help='permite rodar com o DATA_DIR fora do repositório (NÃO faça isso no share do JPM)')
    a = ap.parse_args()

    data_dir = os.path.normpath(Config.DATA_DIR)
    if not data_dir.startswith(ROOT) and not a.allow_external:
        print('RECUSADO: DATA_DIR fora do repositório ({}). Isto é dado de DEMONSTRAÇÃO; '
              'no share do JPM ele se misturaria à posição real. --allow-external força.'.format(data_dir))
        return 2

    src_ref = datetime.strptime(a.src, '%Y-%m-%d') if a.src else _latest_source_day()
    if src_ref is None:
        print('nenhum dia com posição encontrado em', R.B3_JSON_ROOT)
        return 1
    dst_ref = datetime.strptime(a.dst, '%Y-%m-%d') if a.dst else R._prev_anbima_bizday(datetime.now())
    dst_ref = dst_ref.replace(hour=0, minute=0, second=0, microsecond=0)
    if dst_ref == src_ref:
        print('origem e alvo são o mesmo dia ({}); nada a fazer'.format(src_ref.date()))
        return 0
    print('origem: {}   alvo: {}   ({} dias úteis)'.format(
        src_ref.strftime('%d/%m/%Y'), dst_ref.strftime('%d/%m/%Y'),
        R._anbima_biz_diff(src_ref, dst_ref) if dst_ref > src_ref else -R._anbima_biz_diff(dst_ref, src_ref)))
    print('raiz  :', R.B3_JSON_ROOT)

    src_tag, dst_tag = src_ref.strftime('%y%m%d'), dst_ref.strftime('%y%m%d')
    written, skipped = 0, 0
    for cat in CATEGORIES:
        sdir = _day_dir(cat, src_ref)
        if not S.isdir(sdir):
            continue
        for fname in sorted(S.listdir(sdir)):
            if not fname.endswith('.json') or fname.endswith('.meta.json'):
                continue
            if src_tag not in fname:
                print('  pulo {} (nome sem a data {})'.format(fname, src_tag))
                continue
            payload = S.read(os.path.join(sdir, fname))
            if not isinstance(payload, list):
                print('  pulo {} (payload não é lista)'.format(fname))
                continue
            out = []
            for row in payload:
                if not isinstance(row, dict):
                    out.append(row)
                    continue
                nr = {}
                for k, v in row.items():
                    nr[k] = dst_ref.strftime('%Y%m%d') if k.strip().lower() == 'data do arquivo' \
                        else _shift(v, src_ref, dst_ref, k)
                out.append(nr)
            ddir = _day_dir(cat, dst_ref)
            dpath = os.path.join(ddir, fname.replace(src_tag, dst_tag))
            rel = os.path.relpath(dpath, R.B3_JSON_ROOT)
            if S.exists(dpath) and not a.force:
                print('  existe {} (use --force)'.format(rel))
                skipped += 1
                continue
            print('  {} {}  ({} registros)'.format('[dry] ' if a.dry_run else 'grava', rel, len(out)))
            if a.dry_run:
                continue
            S.write(dpath, out)                          # no banco (§434)
            written += 1
    print('gravados: {}   pulados: {}'.format(written, skipped))
    return 0


if __name__ == '__main__':
    sys.exit(main())
