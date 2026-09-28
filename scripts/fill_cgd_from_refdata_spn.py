#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fill_cgd_from_refdata_spn.py — completa o Tracking Docs pelo SPN.

Para cada CGD do `cgd_sharepoint.db`, procura o SPN no Reference Data e
preenche as quatro colunas que o cadastro já sabe: Economic Group, ECI, CASID
e UCN.

    python scripts/fill_cgd_from_refdata_spn.py --dry-run   # só relata
    python scripts/fill_cgd_from_refdata_spn.py             # grava
    python scripts/fill_cgd_from_refdata_spn.py --force     # reescreve o que já tem valor
    python scripts/fill_cgd_from_refdata_spn.py --db <caminho> --refdata <arquivo>

É idempotente: a segunda passada não acha o que preencher.

O que não é óbvio:

- **O SPN compara pelos DÍGITOS, sem zero à esquerda e sem o `.0`** — a mesma
  chave do `routes._spn_key`. O Reference Data veio de planilha e guarda
  `1234567.0` em parte das linhas; comparar a string casaria nada, calado.
- **Uma célula pode trazer VÁRIOS SPNs** (o grupo inteiro, separados por `;`,
  `,`, `/` ou quebra de linha — o contrato da Razão Social e do CNPJ). Cada um
  é procurado, e os valores achados vão juntos, sem repetir, separados por
  `; `. SPN que o cadastro não tem é relatado e não impede os outros.
- **SPN AMBÍGUO não preenche.** O mesmo SPN com dois ECI diferentes no
  Reference Data é cadastro a corrigir, não escolha a fazer aqui: um ECI
  errado leva o documento para outro cliente, e nada na tela acusa. A coluna
  fica como está e o SPN vai para o relatório.
- **Só preenche o VAZIO** (`''`, `0`, `N/A`, `#N/D`…), a menos de `--force`: a
  mesa corrige o campo à mão quando o cadastro está errado, e sobrescrever
  apagaria a correção.
- **A gravação é UMA abertura do banco** (`cgd_docs.update_rows`), pelo mesmo
  funil da tela. Linha a linha, no share, seriam centenas de travas
  exclusivas sobre a lista da mesa inteira.

O banco é o `Config.DATABASE_DIR` e o Reference Data sai do armazém pelo
`data_path` — os mesmos lugares que o app lê, na dev e na instância.
"""

import argparse
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Fora do Windows o `Config` exige o share absoluto (§9), e este script não
# encosta no share.
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(REPO_ROOT, '.import-share'))

from apps.pages import cgd_docs as CGD                              # noqa: E402
from apps.pages.data_paths import data_path                         # noqa: E402

SPN_COLUMN = 'SPN'
NAME_COLUMN = 'Razão Social'

# coluna do Tracking Docs → campo do Reference Data
CAMPOS = (
    ('Grupo Economico', 'ECONOMIC GROUP'),
    ('ECI', 'ECI'),
    ('CASID', 'CASID'),
    ('UCN', 'UCN'),
)

VAZIOS = {'', '0', '0.0', '-', '--', 'n/a', 'na', 'nao', 'não', 'none',
          'null', '#n/d', '#n/a', 'nd'}

_SEP = re.compile(r'[;,/\n]+')


def spn_chave(v):
    """A mesma regra do `routes._spn_key`: o `.0` sai ANTES da pontuação (senão
    o zero dele viraria mais um dígito), e os zeros da frente caem."""
    s = str(v or '').strip()
    if s.endswith('.0'):
        s = s[:-2]
    return re.sub(r'\D', '', s).lstrip('0')


def spns_da_celula(v):
    """As chaves de SPN de uma célula, na ordem em que aparecem, sem repetir."""
    out = []
    for pedaco in _SEP.split(str(v or '')):
        k = spn_chave(pedaco)
        if k and k not in out:
            out.append(k)
    return out


def limpo(v):
    """O valor do cadastro como texto: sem espaço nas pontas e sem o `.0` que o
    número ganhou na planilha (`221690142.0` é o ECI `221690142`)."""
    s = str(v if v is not None else '').strip()
    if re.fullmatch(r'\d+\.0', s):
        s = s[:-2]
    return s


def vazio(v):
    return str(v or '').strip().lower() in VAZIOS


def carrega_refdata(caminho=None):
    """{spn → {campo → valor}} e {spn → {campos ambíguos}}.

    A leitura passa pelo armazém (§440): o `data_path` sabe se o RefData está
    no banco do `DATA_DIR` ou só na cópia empacotada.
    """
    caminho = caminho or data_path('RefData.json')
    from apps.pages import data_store
    dados = data_store.read(caminho) or []
    por_spn, ambiguos = {}, {}
    for rec in (dados if isinstance(dados, list) else []):
        k = spn_chave(rec.get('SPN'))
        if not k:
            continue
        atual = por_spn.setdefault(k, {})
        for _col, campo in CAMPOS:
            v = limpo(rec.get(campo))
            if vazio(v):
                continue
            if campo in atual and atual[campo] != v:
                ambiguos.setdefault(k, set()).add(campo)
            atual.setdefault(campo, v)
    for k, campos in ambiguos.items():
        for campo in campos:
            por_spn[k].pop(campo, None)
    return por_spn, ambiguos, caminho


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', help='caminho do cgd_sharepoint.db (padrão: o do Config)')
    ap.add_argument('--refdata', help='caminho do RefData.json')
    ap.add_argument('--dry-run', action='store_true', help='só relata, não grava')
    ap.add_argument('--force', action='store_true',
                    help='reescreve TAMBÉM o que já está preenchido')
    args = ap.parse_args()

    db = args.db or CGD.DB_PATH
    print('banco   : %s' % db)
    from apps.pages import data_store
    if not data_store.isfile(db) and not os.path.isfile(db):
        print('ERRO: banco não encontrado. Rode antes o import_cgd_sharepoint.py.')
        return 1

    por_spn, ambiguos, rd = carrega_refdata(args.refdata)
    print('refdata : %s  (%d SPNs)' % (rd, len(por_spn)))

    linhas = CGD.load_all(db)
    print('linhas  : %d' % len(linhas))

    mudancas = {}                 # _id → {coluna: valor}
    exemplos = []
    sem_spn = 0
    spn_fora = {}                 # spn → quantas linhas
    spn_ambiguo = set()
    ja_tinha = {c: 0 for c, _f in CAMPOS}
    for r in linhas:
        chaves = spns_da_celula(r.get(SPN_COLUMN))
        if not chaves:
            sem_spn += 1
            continue
        achados = []
        for k in chaves:
            if k in por_spn:
                achados.append(por_spn[k])
            else:
                spn_fora[k] = spn_fora.get(k, 0) + 1
            if k in ambiguos:
                spn_ambiguo.add(k)
        if not achados:
            continue
        novos = {}
        for col, campo in CAMPOS:
            atual = str(r.get(col, '') or '').strip()
            if not vazio(atual) and not args.force:
                ja_tinha[col] += 1
                continue
            # SPN do grupo com a coluna AMBÍGUA: melhor não preencher do que
            # preencher com os valores só dos outros SPNs, como se fossem todos.
            if any(campo in ambiguos.get(k, ()) for k in chaves):
                continue
            valores = []
            for a in achados:
                v = a.get(campo)
                if v and v not in valores:
                    valores.append(v)
            valor = '; '.join(valores)
            if valor and valor != atual:
                novos[col] = valor
        if novos:
            mudancas[r[CGD.ID_COLUMN]] = novos
            if len(exemplos) < 15:
                exemplos.append((r[CGD.ID_COLUMN], str(r.get(NAME_COLUMN, ''))[:34],
                                 ', '.join('%s=%s' % kv for kv in novos.items())))

    print('')
    print('linhas a preencher : %d' % len(mudancas))
    for col, _f in CAMPOS:
        n = sum(1 for v in mudancas.values() if col in v)
        print('   %-16s %d%s' % (col, n,
                                  ('  (%d já tinham — use --force)' % ja_tinha[col])
                                  if ja_tinha[col] else ''))
    print('sem SPN            : %d' % sem_spn)
    print('SPN fora do RefData: %d' % len(spn_fora))
    for k in sorted(spn_fora)[:15]:
        print('   %s  (%d linha(s))' % (k, spn_fora[k]))
    if spn_ambiguo:
        print('SPN AMBÍGUO no RefData (coluna não preenchida — corrija o cadastro):')
        for k in sorted(spn_ambiguo):
            print('   %s  %s' % (k, ', '.join(sorted(ambiguos[k]))))

    for rid, nome, o_que in exemplos:
        print('   #%-5s %-34s %s' % (rid, nome, o_que))
    if len(mudancas) > len(exemplos):
        print('   … e mais %d' % (len(mudancas) - len(exemplos)))

    if args.dry_run:
        print('\n--dry-run: nada foi gravado.')
        return 0
    if not mudancas:
        print('\nNada a fazer.')
        return 0

    n = CGD.update_rows(mudancas, db)
    print('\n%d linha(s) atualizada(s).' % n)
    return 0


if __name__ == '__main__':
    sys.exit(main())
