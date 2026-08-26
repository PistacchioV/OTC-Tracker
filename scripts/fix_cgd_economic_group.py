#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_cgd_economic_group.py — completa o Grupo Econômico dos CGDs pelo RefData.

A coluna `Grupo Economico` do `cgd_sharepoint.db` chega da lista do SharePoint
e vem furada: uma parte está em BRANCO e outra traz `0` — o zero que a planilha
escreve quando a fórmula não achou o cliente. Os dois se leem como "não tem
grupo", e não é isso: o grupo existe, está no Reference Data, e a chave para
achá-lo é o CNPJ que as duas bases já guardam.

    python scripts/fix_cgd_economic_group.py
    python scripts/fix_cgd_economic_group.py --dry-run       # só relata
    python scripts/fix_cgd_economic_group.py --db  <caminho> # outro banco
    python scripts/fix_cgd_economic_group.py --refdata <arquivo>
    python scripts/fix_cgd_economic_group.py --force         # reescreve o que já tem grupo

É idempetente: rodar de novo não muda mais nada, porque a segunda passada não
acha o que corrigir.

Quatro coisas que não são óbvias:

- **O CNPJ compara por DÍGITO.** Os dois lados guardam pontuação diferente
  (`17.803.411/0001-18` × `17803411000118`) e o CGD ainda vem com zero à
  esquerda perdido no caminho da planilha. Comparar string casa nada, em
  silêncio — é a mesma armadilha do §197.
- **O `0` é tratado como VAZIO.** Ele não é um grupo chamado zero: é o
  `#N/D` que virou zero na exportação. Fica na mesma lista de "a preencher"
  que a célula em branco, senão metade das linhas continuaria como está.
- **Sem CNPJ, o nome é o segundo caminho.** Algumas linhas do CGD não têm CNPJ
  nenhum; nelas a Razão Social é comparada com o COUNTERPARTY do RefData,
  normalizada (sem acento, sem pontuação, sem sufixo societário). É o caminho
  mais fraco e por isso é o SEGUNDO: um nome parecido casaria dois clientes
  diferentes, então ele só vale quando o CNPJ não respondeu, e só quando o nome
  bate por INTEIRO.
- **Grupo já preenchido não é tocado** (a menos de `--force`): a mesa corrige o
  campo à mão quando o RefData está errado, e sobrescrever apagaria a correção.

O banco é o `Config.DATABASE_DIR` — o mesmo caminho que a aplicação lê, e ele
muda entre a dev e a instância do JPM junto com o resto (o bloco de ENV do
`config.py`). Rodando na dev, corrige o banco da dev; rodando na instância,
o do share. Nenhum caminho é montado aqui.
"""

import argparse
import io
import json
import os
import re
import sys
import unicodedata

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Fora do Windows o `Config` exige o share absoluto (§8), e este script não
# encosta no share — o default deixa o import do config passar em qualquer
# máquina, sem mudar nada para quem já tem a variável definida.
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', os.path.join(REPO_ROOT, '.import-share'))

from apps.pages import cgd_docs as CGD                              # noqa: E402
from apps.pages.data_paths import data_path                         # noqa: E402

GROUP_COLUMN = 'Grupo Economico'
CNPJ_COLUMN = 'CNPJ'
NAME_COLUMN = 'Razão Social'

# O que se lê como "não preenchido". O `0` é o `#N/D` que virou zero na
# exportação; `n/a`, `-` e `#n/d` aparecem escritos à mão na mesma coluna.
VAZIOS = {'', '0', '0.0', '-', '--', 'n/a', 'na', 'nao', 'não', 'none',
          'null', '#n/d', '#n/a', 'nd'}

# Sufixos societários: `CARGILL AGRICOLA S.A.` e `CARGILL AGRICOLA` são o mesmo
# cliente para o casamento por nome, que já é o caminho fraco.
SUFIXOS = ('sa', 'sas', 'ltda', 'ltd', 'eireli', 'me', 'epp', 'scltda',
           'sociedadeanonima', 'inc', 'llc', 'corp', 'plc', 'nv', 'bv', 'gmbh')


def so_digitos(v):
    return re.sub(r'\D', '', str(v or ''))


def cnpj_chave(v):
    """CNPJ comparável: só dígitos, sem zeros à esquerda.

    Os zeros caem dos DOIS lados. O CGD perde o zero inicial quando a planilha
    trata a coluna como número, e o RefData o mantém — comparar com eles faria
    o cliente casar com ninguém, sem erro nenhum (§197).
    """
    d = so_digitos(v).lstrip('0')
    return d or ''


def nome_chave(v):
    """Nome comparável: sem acento, sem pontuação, sem caixa, sem sufixo."""
    s = unicodedata.normalize('NFKD', str(v or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r'[^a-z0-9]', '', s.lower())
    for suf in SUFIXOS:
        if s.endswith(suf) and len(s) > len(suf) + 3:
            s = s[:-len(suf)]
            break
    return s


def vazio(v):
    return str(v or '').strip().lower() in VAZIOS


def carrega_refdata(caminho=None):
    """(por CNPJ, por nome) → grupo econômico, do RefData.json.

    A leitura passa pelo `data_path`, que é quem sabe se o arquivo está no
    `DATA_DIR` (o share, na instância) ou na cópia empacotada. Montar o caminho
    aqui faria o script corrigir o banco do share com o RefData do checkout.
    """
    caminho = caminho or data_path('RefData.json')
    with io.open(caminho, encoding='utf-8') as fh:
        dados = json.load(fh) or []
    por_cnpj, por_nome, ambiguos = {}, {}, set()
    for rec in (dados if isinstance(dados, list) else []):
        grupo = str(rec.get('ECONOMIC GROUP', '') or '').strip()
        if vazio(grupo):
            continue
        ck = cnpj_chave(rec.get('TAX ID'))
        if ck:
            # Mesmo CNPJ com grupos diferentes: não dá para escolher, e escolher
            # errado é pior do que deixar em branco. Vale para os dois índices.
            if ck in por_cnpj and por_cnpj[ck] != grupo:
                ambiguos.add(ck)
            por_cnpj[ck] = grupo
        nk = nome_chave(rec.get('COUNTERPARTY'))
        if nk:
            if nk in por_nome and por_nome[nk] != grupo:
                por_nome[nk] = None          # ambíguo: some do índice
            elif nk not in por_nome:
                por_nome[nk] = grupo
    for ck in ambiguos:
        por_cnpj.pop(ck, None)
    por_nome = {k: v for k, v in por_nome.items() if v}
    return por_cnpj, por_nome, caminho


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', help='caminho do cgd_sharepoint.db (padrão: o do Config)')
    ap.add_argument('--refdata', help='caminho do RefData.json')
    ap.add_argument('--dry-run', action='store_true', help='só relata, não grava')
    ap.add_argument('--force', action='store_true',
                    help='reescreve TAMBÉM o que já tem grupo preenchido')
    args = ap.parse_args()

    db = args.db or CGD.DB_PATH
    print('banco   : %s' % db)
    if not os.path.isfile(db):
        print('ERRO: banco não encontrado. Rode antes o import_cgd_sharepoint.py.')
        return 1

    por_cnpj, por_nome, rd = carrega_refdata(args.refdata)
    print('refdata : %s  (%d CNPJ, %d nomes)' % (rd, len(por_cnpj), len(por_nome)))

    linhas = CGD.load_all(db)
    print('linhas  : %d' % len(linhas))

    por_cnpj_n = por_nome_n = ja_tinha = sem_chave = nao_achou = 0
    mudancas = []
    for r in linhas:
        atual = str(r.get(GROUP_COLUMN, '') or '').strip()
        if not vazio(atual) and not args.force:
            ja_tinha += 1
            continue
        ck = cnpj_chave(r.get(CNPJ_COLUMN))
        grupo = por_cnpj.get(ck) if ck else None
        via = 'CNPJ'
        if not grupo:
            nk = nome_chave(r.get(NAME_COLUMN))
            grupo = por_nome.get(nk) if nk else None
            via = 'nome'
        if not grupo:
            if not ck and not nome_chave(r.get(NAME_COLUMN)):
                sem_chave += 1
            else:
                nao_achou += 1
            continue
        if grupo == atual:
            continue
        if via == 'CNPJ':
            por_cnpj_n += 1
        else:
            por_nome_n += 1
        mudancas.append((r[CGD.ID_COLUMN], grupo, via,
                         str(r.get(NAME_COLUMN, ''))[:40], atual))

    print('')
    print('a preencher    : %d  (%d por CNPJ, %d por nome)'
          % (len(mudancas), por_cnpj_n, por_nome_n))
    print('já tinha grupo : %d%s' % (ja_tinha, ' (use --force para reescrever)' if ja_tinha else ''))
    print('sem CNPJ e sem nome : %d' % sem_chave)
    print('sem correspondência no RefData : %d' % nao_achou)

    for rid, grupo, via, nome, antes in mudancas[:15]:
        print('   #%-5s %-40s %-6s %r -> %r' % (rid, nome, via, antes, grupo))
    if len(mudancas) > 15:
        print('   … e mais %d' % (len(mudancas) - 15))

    if args.dry_run:
        print('\n--dry-run: nada foi gravado.')
        return 0
    if not mudancas:
        print('\nNada a fazer.')
        return 0

    for rid, grupo, _via, _nome, _antes in mudancas:
        CGD.update_row(rid, {GROUP_COLUMN: grupo}, db)
    print('\n%d linha(s) atualizada(s).' % len(mudancas))
    return 0


if __name__ == '__main__':
    sys.exit(main())
