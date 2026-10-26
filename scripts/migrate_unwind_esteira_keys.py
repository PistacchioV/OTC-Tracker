"""
migrate_unwind_esteira_keys.py
------------------------------
Leva as recompras do Pending Confirmation e da esteira para a chave PRÓPRIA
delas (§696) e conserta o que a chave antiga quebrou.

Até §696 a recompra era chaveada pelo Athena ID cru (Fase 1, NDF FX) ou pelo
Deal ID (catálogo). O Athena ID é o `DEAL NAME` do trade ORIGINAL — o mesmo
`Deal` com que a Vanilla e a Other Publisher gravam a confirmação do contrato
no Pending —, e o Deal ID do catálogo pode ser o `Deal` do NDF Comm. Com a
mesma chave:

  * no Pending, a recompra REESCREVIA a linha da original (o Product Type virava
    `UNWIND NDF`, as datas viravam as da recompra);
  * na esteira, a recompra nunca entrava quando a original já tinha linha (o
    `_mc_save_from_deal` não sobrescreve), e duas recompras parciais do mesmo
    contrato dividiam uma linha;
  * o Delete da recompra apagava a confirmação original.

A chave nova é `UNW-<Athena ID>-<AAAAMMDD da liquidação>` na Fase 1 e
`UNW-<_id>` no catálogo (`unwinds.domain.chave_esteira`).

O que o script faz, recompra a recompra (as do fundo ficam de fora, §580):

  1. ESTEIRA: a linha da chave antiga que é da recompra (Produto `UNWIND …`)
     passa para a chave nova — destino primeiro, depois apaga a antiga. Duas
     parciais na mesma linha: fica com a do dia da `Data Operação`.
  2. PENDING: idem, a linha `UNWIND …` da chave antiga vai para a nova. Se a
     chave antiga era o `Deal` de uma Vanilla/Other Publisher MAPEADA, a linha
     da original é REFEITA pela porta de sempre (`_generic_nd_pc_trigger`) —
     o que a equipe tinha preenchido nela (EA, comentários, FepWeb ID) foi
     perdido quando a recompra a reescreveu e NÃO volta: a lista sai no fim.
  3. A recompra sem linha na chave nova (a que nunca entrou na esteira, a
     segunda parcial) entra pela mesma porta do import (`esteira_da_recompra`
     / `product.esteira`).

Sem `--gravar` só relata. Idempotente: rodar de novo não muda nada. Rode com
o app de pé ou parado (grava pelo `duckdb_write`), DEPOIS do pull.

Uso
    python scripts/migrate_unwind_esteira_keys.py            # relatório
    python scripts/migrate_unwind_esteira_keys.py --gravar
"""
import argparse
import os
import sys
from datetime import datetime

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
sys.path.insert(0, REPO_ROOT)
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')


def _dias(store, raiz):
    """(dia, [linhas]) de cada arquivo-dia sob `raiz` (AAAAMMDD no começo do nome)."""
    if not store.isdir(raiz):
        return
    for dirpath, _dirs, files in store.walk(raiz):
        for fname in sorted(files):
            if not fname.endswith('.json'):
                continue
            try:
                dia = datetime.strptime(fname[:8], '%Y%m%d')
            except ValueError:
                continue
            fp = os.path.join(dirpath, fname)
            try:
                lst = store.read(fp)
            except Exception as exc:                        # noqa: BLE001
                print('  ! não li {}: {}'.format(fp, exc))
                continue
            if isinstance(lst, list):
                yield dia, [e for e in lst if isinstance(e, dict)]


def _dono(grupo, data, parse):
    """Entre as recompras que dividiam a chave antiga, a do dia `data` (a
    `Data Operação` da esteira, a `Trade Date` do Pending); sem ela, a primeira."""
    d = parse(data)
    d = d.date() if hasattr(d, 'date') else d
    return next((it for it in grupo if d and it[2].date() == d), grupo[0])


def _e_recompra(produto):
    return str(produto or '').strip().upper().startswith('UNWIND')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--gravar', action='store_true', help='grava (sem ele, só relata)')
    args = ap.parse_args(argv)

    from apps.pages import routes as R                            # noqa: E402
    from apps.pages import data_store as S                        # noqa: E402
    from apps.pages import manual_conf as MC                      # noqa: E402
    from apps.pages.platform import pending_confirmation as PCM   # noqa: E402
    from apps.pages.features.unwinds import commands as F1        # noqa: E402
    from apps.pages.features.unwinds import domain as D1          # noqa: E402
    from apps.pages.features.unwinds.infra import persistence     # noqa: E402
    from apps.pages.features.unwinds.infra import product_store   # noqa: E402
    from apps.pages.features.unwinds.product import commands as PR  # noqa: E402

    # Cada recompra: (origem, page, dia, linha, chave antiga, chave nova).
    itens = []
    for dia, linhas in _dias(S, persistence.cache_dir()):
        for l in linhas:
            if F1.e_do_fundo(l):
                continue
            antiga = str(l.get('AthenaID') or '').strip()
            nova = D1.chave_esteira(l)
            if antiga and nova:
                itens.append(('NDF FX', None, dia, l, antiga, nova))
    for page in PR.paginas_com_esteira():
        for dia, linhas in _dias(S, product_store.cache_dir(page)):
            for l in linhas:
                if F1.e_do_fundo(l):
                    continue
                antiga = PR.chave(l)
                nova = PR.chave_esteira(page, l)
                if antiga and nova:
                    itens.append((page['label'], page, dia, l, antiga, nova))
    print('{} recompra(s) contra cliente nos arquivos-dia'.format(len(itens)))

    por_antiga = {}
    for it in itens:
        por_antiga.setdefault(it[4], []).append(it)

    mc_mov, pc_mov, restaurar, perdidos, entrar = [], [], [], [], []
    for antiga, grupo in sorted(por_antiga.items()):
        # 1. ESTEIRA
        row = MC.find_row(antiga)
        if row is not None and _e_recompra(row.get('Produto')):
            dono = _dono(grupo, row.get('Data Operação'), R._parse_date_any)
            if MC.find_row(dono[5]) is None:
                mc_mov.append((antiga, dono[5]))
                if args.gravar:
                    MC.insert_rows([dict(row, **{MC.KEY_COLUMN: dono[5]})])
                    MC.delete_row(antiga)
        # 2. PENDING
        pc = PCM._pc_find_row(antiga)
        if pc is not None and _e_recompra(pc.get('Product Type')):
            dono = _dono(grupo, pc.get('Trade Date'), R._parse_date_any)
            if PCM._pc_find_row(dono[5]) is None:
                pc_mov.append((antiga, dono[5]))
                if args.gravar:
                    PCM._pc_upsert_rows([dict(pc, **{'Trade Number': dono[5]})])
                    PCM._pc_delete_trade_number(antiga)
            # A chave antiga era o `Deal` de uma confirmação ORIGINAL?
            achou = False
            for prod in ('vanilla', 'other-publisher'):
                cfg = R._GENERIC_ND_PRODUCTS.get(prod)
                if not cfg:
                    continue
                fp, i = R._find_generic_nd_deal(cfg, antiga)
                if fp is None:
                    continue
                deal = S.read(fp)[i]
                achou = True
                if str(deal.get('Status') or '').strip() == 'Success':
                    restaurar.append((antiga, prod))
                    if args.gravar:
                        R._generic_nd_pc_trigger(prod, deal)
                else:
                    perdidos.append((antiga, 'original em {} com Status {}'.format(
                        prod, deal.get('Status') or '—')))
                break
            if not achou and grupo[0][0] != 'NDF FX':
                perdidos.append((antiga, 'confira se era o Deal de um NDF Comm/Opt Comm'))

    # 3. A recompra sem linha na chave nova entra pela porta do import.
    for it in itens:
        origem, page, dia, l, antiga, nova = it
        mc_ok = MC.find_row(nova) is not None or (antiga, nova) in mc_mov
        pc_ok = PCM._pc_find_row(nova) is not None or (antiga, nova) in pc_mov
        if not (mc_ok and pc_ok):
            entrar.append(it)
    if args.gravar:
        for origem, page, dia, l, antiga, nova in entrar:
            if page is None:
                F1.esteira_da_recompra([l], dia)
            else:
                PR.esteira(page, [l], dia)

    def _lista(titulo, pares):
        print('\n{} ({})'.format(titulo, len(pares)))
        for p in pares[:200]:
            print('  ' + '  →  '.join(str(x) for x in p))

    _lista('esteira: linha da recompra para a chave nova', mc_mov)
    _lista('pending: linha da recompra para a chave nova', pc_mov)
    _lista('pending: confirmação ORIGINAL refeita (o que a equipe preencheu nela não volta)',
           restaurar)
    _lista('a CONFERIR à mão', perdidos)
    _lista('recompras que entram agora (nunca tiveram linha própria)',
           [(it[0], it[5]) for it in entrar])
    print('\n' + ('gravado.' if args.gravar else 'nada gravado (rode com --gravar).'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
