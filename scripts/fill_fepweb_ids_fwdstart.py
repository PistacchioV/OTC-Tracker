"""
fill_fepweb_ids_fwdstart.py
---------------------------
Preenche o FepWeb ID do Pending Confirmation das confirmações de NDF FWD Start
JÁ geradas (§703).

Até §703 o Save da confirmação gravava o `numeroContrato` do XML na coluna
FepWeb ID procurando a linha do Pending pelo `Deal` (Athena ID) — e a linha do
FWD Start (do Banco e de MGT) é chaveada pelo B3 ID. A busca não achava nada,
sem erro, e o FepWeb ID ficava vazio no Pending e, por cópia, na coluna "Nome
fep" da esteira (`_mc_sync_fepweb_ids`). O Vanilla de MGT, pelo Deal, saía
certo.

O que o script faz, linha a linha da esteira com Produto `NDF FWD START` e
`Confirmation Link` (o PDF que a geração gravou):

  1. a linha irmã do Pending (Trade Number = o Trade ID, o B3 ID) com o
     FepWeb ID VAZIO — preenchido não é tocado;
  2. o XML ao lado do PDF (mesmo nome, `.xml`) no Electronic Inventory, e
     dele o `numeroContrato`;
  3. grava pelo mesmo `_conf_pc_set_fepweb` da geração.

A "Nome fep" da esteira se preenche sozinha na próxima carga do Track. Sem
`--gravar` só relata. Idempotente. Rode com o app de pé ou parado (grava pelo
`duckdb_write`), DEPOIS do pull.

Uso
    python scripts/fill_fepweb_ids_fwdstart.py            # relatório
    python scripts/fill_fepweb_ids_fwdstart.py --gravar
"""
import argparse
import os
import re
import sys
from urllib.parse import parse_qs, urlparse

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, REPO_ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

_NUMERO = re.compile(r'<numeroContrato>\s*([^<]*?)\s*</numeroContrato>')


def _xml_do_link(R, link):
    """(caminho do XML, motivo) a partir do `Confirmation Link` da esteira."""
    q = parse_qs(urlparse(link).query)
    cliente = (q.get('client') or [''])[0]
    rel = (q.get('rel') or [''])[0]
    if not (cliente and rel):
        return None, 'link sem cliente/caminho'
    raiz = R._ei_resolve_client_dir(cliente, create=False)
    if not raiz:
        return None, 'pasta do cliente %r não achada no Electronic Inventory' % cliente
    pdf = os.path.join(raiz, *rel.split('/'))
    return os.path.splitext(pdf)[0] + '.xml', ''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--gravar', action='store_true', help='grava (sem ele, só relata)')
    args = ap.parse_args()

    from apps import create_app
    from apps.config import DebugConfig
    app = create_app(DebugConfig)
    from apps.pages import manual_conf as MC
    from apps.pages import routes as R
    from apps.pages.platform import pending_confirmation as PC

    with app.app_context():
        linhas = [r for r in MC.load_all(strict=True)
                  if str(r.get('Produto', '') or '').strip().upper() == 'NDF FWD START'
                  and str(r.get('Trade ID', '') or '').strip()
                  and str(r.get('Confirmation Link', '') or '').strip()]
        print('esteira: %d linha(s) de NDF FWD START com documento gerado' % len(linhas))
        pcs = PC._pc_find_rows([str(r['Trade ID']).strip() for r in linhas])
        feitos, ja, sem_pc, falhas = [], 0, [], []
        for r in linhas:
            tn = str(r['Trade ID']).strip()
            pc = pcs.get(tn)
            if pc is None:
                sem_pc.append(tn)
                continue
            if str(pc.get('FepWeb ID', '') or '').strip():
                ja += 1
                continue
            xml, motivo = _xml_do_link(R, str(r['Confirmation Link']).strip())
            if not xml:
                falhas.append((tn, motivo))
                continue
            try:
                with open(R._ei_long_path(xml), encoding='utf-8') as fh:
                    m = _NUMERO.search(fh.read())
            except OSError as exc:
                falhas.append((tn, 'XML não lido (%s): %s' % (exc.__class__.__name__, xml)))
                continue
            if not m or not m.group(1):
                falhas.append((tn, 'XML sem numeroContrato: %s' % xml))
                continue
            feitos.append((tn, m.group(1)))
            if args.gravar:
                R._conf_pc_set_fepweb([tn], m.group(1))

        print('%s: %d' % ('preenchidos' if args.gravar else 'a preencher', len(feitos)))
        for tn, num in feitos:
            print('   %s -> %s' % (tn, num))
        print('já tinham FepWeb ID: %d' % ja)
        if sem_pc:
            print('sem linha no Pending: %d (%s)' % (len(sem_pc), ', '.join(sem_pc[:20])))
        if falhas:
            print('não resolvidos: %d' % len(falhas))
            for tn, motivo in falhas:
                print('   %s: %s' % (tn, motivo))
        if feitos and not args.gravar:
            print('\nnada gravado — rode com --gravar')


if __name__ == '__main__':
    main()
