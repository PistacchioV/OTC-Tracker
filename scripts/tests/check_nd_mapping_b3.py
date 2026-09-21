#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""O mapeamento do B3 ID DIZ se gravou (`_grava_mapeamento`, 21/09/2026).

Os quatro endpoints de `mapping-b3` (NDF Comm, Opt Comm, Opt FXO e o genérico)
decidiam o `Status` pelo arquivo de retorno da B3 e devolviam esse veredito à
tela **sem olhar se a gravação no arquivo-dia aconteceu**. Havia duas saídas
mudas:

1. **a linha não é achada** — o casamento é por `(Deal, Client)` EXATO, e não
   achando, o código seguia em frente;
2. **a gravação estoura** — no share, `_store.read` e `_atomic_write_json`
   levantam `BancoOcupado`/`BancoIlegivel` quando a instância vizinha está com
   a trava (CLAUDE.md §4). Ali isso é ESPERADO, não excepcional, e um
   `except Exception: pass` engolia.

Nos dois casos o navegador recebia `Success`, pintava Status e B3 ID na grade e
anunciava *"N deal(s) mapped successfully"*; na abertura seguinte a linha
voltava do banco como estava — `Sent`. Foi o relato da mesa: operações
mapeadas no NDF Comm que continuaram em `Sent`. E como o defeito depende da
trava do vizinho, ele pegava ALGUMAS operações e não todas, que é o que mais
atrapalha o diagnóstico.

O que este guarda prende:

  1. gravação que dá certo devolve `saved=True` e o status da B3;
  2. linha NÃO ENCONTRADA devolve `saved=False`, sem B3 ID e sem `Success`;
  3. gravação que ESTOURA devolve `saved=False` — e não é confundida com o
     `Error` da B3, que é veredito do arquivo de retorno, não falha nossa;
  4. o que não gravou não vira espelho: Intrag e Pending Confirmation só são
     alimentados pela linha que FICOU no arquivo-dia;
  5. o contador do sino conta os GRAVADOS;
  6. a tela não pinta o que não gravou (os seis templates contam por `saved`).

Não toca em dado real: o `_grava_mapeamento` é exercitado com dublês.
"""
import io
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages.features.new_deals import entrypoint as E        # noqa: E402
from apps.pages import data_store as _store                      # noqa: E402

falhas = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok   ' if ok else '  FAIL ') + label + ('' if ok else '   got=%r exp=%r' % (got, exp)))
    if not ok:
        falhas.append(label)


# ── Dublês: o `_grava_mapeamento` só fala com o routes e com o armazém ──────

class _Log(object):
    def __init__(self):
        self.linhas = []

    def _anota(self, msg, *a, **k):
        try:
            self.linhas.append(str(msg) % a if a else str(msg))
        except Exception:                                        # noqa: BLE001
            self.linhas.append(str(msg))

    warning = error = info = exception = _anota


class _Lock(object):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Routes(object):
    """O mínimo que `_grava_mapeamento` lê do routes."""

    def __init__(self, arquivo):
        self.log = _Log()
        self._cache_lock = _Lock()
        self.gravado = None
        self._arquivo = arquivo
        self.estoura_na_gravacao = None

    def _atomic_write_json(self, path, dados):
        if self.estoura_na_gravacao:
            raise self.estoura_na_gravacao
        self.gravado = (path, dados)


ARQ = '/tmp/otc-share/20260918_ndfcomm.json'
LINHAS = [{'Deal': 'D5YJ-SMWOF', 'Client': 'LAWTON MULTIMERCADO EXCLUSIVO',
           'Status': 'Sent', 'B3_ID': ''},
          {'Deal': 'D5YJ-SMWOF', 'Client': 'BANCO J.P MORGAN S.A',
           'Status': 'Sent', 'B3_ID': ''}]

_leitura = {'estoura': None}
_read_original = _store.read


def _read_dublê(path, *a, **k):
    if path == ARQ:
        if _leitura['estoura']:
            raise _leitura['estoura']
        return [dict(l) for l in LINHAS]
    return _read_original(path, *a, **k)


_store.read = _read_dublê

_R_original = E._R
_ROTAS = _Routes(ARQ)
E._R = lambda: _ROTAS


def acha(deal, client):
    for i, l in enumerate(LINHAS):
        if l['Deal'] == deal and l['Client'] == client:
            return ARQ, i
    return None, None


def nao_acha(deal, client):
    return None, None


UPD = {'Status': 'Success', 'B3_ID': '26I06068566'}

print('== 1. a gravação que DÁ CERTO diz que gravou ==')
_ROTAS.gravado, _ROTAS.estoura_na_gravacao, _leitura['estoura'] = None, None, None
gravado, linha, motivo = E._grava_mapeamento(acha, 'D5YJ-SMWOF',
                                             'LAWTON MULTIMERCADO EXCLUSIVO', UPD)
check('saved = True', gravado, True)
check('e o motivo vem vazio', motivo, '')
check('a linha devolvida JÁ está atualizada', linha.get('Status'), 'Success')
check('   com o B3 ID', linha.get('B3_ID'), '26I06068566')
check('e o arquivo-dia foi gravado', _ROTAS.gravado[0], ARQ)
check('   com a linha certa alterada', _ROTAS.gravado[1][0]['Status'], 'Success')
check('   e a OUTRA linha do mesmo Deal intacta',
      _ROTAS.gravado[1][1]['Status'], 'Sent')

print('\n== 2. linha NÃO ENCONTRADA: saved=False e nada gravado ==')
_ROTAS.gravado = None
_ROTAS.log.linhas = []
gravado, linha, motivo = E._grava_mapeamento(nao_acha, 'D5YJ-SMWOF',
                                             'CLIENTE QUE NAO CASA', UPD)
check('saved = False', gravado, False)
check('o motivo NOMEIA o caso', motivo, 'row_not_found')
check('não há linha para espelhar (Intrag / Pending Confirmation)', linha, None)
check('e NADA foi gravado', _ROTAS.gravado, None)
# O finder já loga o diagnóstico detalhado; esta linha é o que liga aquele
# aviso ao mapeamento — sem ela o log diz que não achou, sem dizer o que se
# perdeu por causa disso.
check('o log DIZ que o B3 ID não foi gravado, com deal e cliente',
      any('NAO ENCONTRADA' in l and 'D5YJ-SMWOF' in l and 'CLIENTE QUE NAO CASA' in l
          for l in _ROTAS.log.linhas), True)

print('\n== 3. a gravação que ESTOURA: saved=False, e o motivo é o erro ==')
# É o caso do share: a instância vizinha com a trava. `BancoOcupado` é um
# IOError, e o `except Exception: pass` de antes o engolia inteiro.
_ROTAS.gravado = None
_ROTAS.log.linhas = []
_ROTAS.estoura_na_gravacao = _store.BancoOcupado('20260918_ndfcomm.db')
gravado, linha, motivo = E._grava_mapeamento(acha, 'D5YJ-SMWOF',
                                             'LAWTON MULTIMERCADO EXCLUSIVO', UPD)
check('saved = False', gravado, False)
check('o motivo carrega o TIPO da exceção', motivo.startswith('BancoOcupado'), True)
check('não há linha para espelhar', linha, None)
check('e o log guardou a falha com o deal',
      any('falha ao GRAVAR' in l and 'D5YJ-SMWOF' in l for l in _ROTAS.log.linhas), True)
_ROTAS.estoura_na_gravacao = None

print('\n== 4. a LEITURA que estoura conta como não gravado ==')
_ROTAS.gravado = None
_leitura['estoura'] = _store.BancoOcupado('20260918_ndfcomm.db')
gravado, linha, motivo = E._grava_mapeamento(acha, 'D5YJ-SMWOF',
                                             'LAWTON MULTIMERCADO EXCLUSIVO', UPD)
check('saved = False', gravado, False)
check('e NADA foi gravado', _ROTAS.gravado, None)
_leitura['estoura'] = None

E._R = _R_original
_store.read = _read_original

print('\n== 5. os quatro endpoints usam o funil, e nenhum engole a gravação ==')
FONTE = io.open('apps/pages/features/new_deals/entrypoint.py', encoding='utf-8').read()
check('há QUATRO rotas de mapping-b3', FONTE.count("/mapping-b3'"), 4)
check('e QUATRO chamadas ao funil', FONTE.count('_grava_mapeamento('), 5)  # 1 def + 4 usos
# O padrão antigo não pode voltar: gravar o arquivo-dia do mapping dentro de um
# `try` cujo `except` é um `pass` é exatamente o defeito que este guarda existe
# para impedir.
_blocos = re.findall(r'_atomic_write_json\(file_path, deals_list\).*?\n(.*?)\n\s*(?:if|results|return|\Z)',
                     FONTE, re.DOTALL)
check('nenhum `except Exception: pass` sobre a gravação do mapping',
      sum(1 for b in _blocos if re.search(r'except Exception:\s*\n\s*pass', b)), 0)
check('o status de "não gravou" NÃO é o Error da B3',
      E.MAPPING_NAO_GRAVADO not in ('Error', 'Success'), True)
# O sino conta os GRAVADOS: escrito `len(results)`, ele anunciava para a mesa
# inteira um número que inclui o mapeamento que não chegou ao banco.
check('o sino conta pelos gravados',
      FONTE.count("_n_gravados = sum(1 for r in results if r.get('saved'))"), 4)
check('   e nenhuma notificação conta pelo len(results)',
      "str(len(results)) + ' deal'" in FONTE, False)

print('\n== 6. as SEIS telas contam por `saved`, e não pintam o que não gravou ==')
PAGS = ['new_deals-ndf-commodities', 'new_deals-opt-commodities', 'new_deals-opt-fxo',
        'new_deals-ndf-fwdstart', 'new_deals-ndf-otherpublisher', 'new_deals-ndf-vanilla']
for nome in PAGS:
    html = io.open('apps/templates/pages/%s.html' % nome, encoding='utf-8').read()
    # `saved === false` tem de vir ANTES do teste de 'Success': a linha que o
    # servidor não gravou não é sucesso, e contada depois ela cairia no ramo
    # errado no dia em que o servidor mandasse os dois campos.
    i_saved = html.find('result.saved === false')
    i_ok = html.find("result.status === 'Success'")
    check('%-34s conta por saved, antes do Success' % nome,
          i_saved != -1 and i_ok != -1 and i_saved < i_ok, True)
    check('%-34s avisa quantos NÃO gravaram' % nome,
          'swal-mapping-failed-n' in html, True)

print('\n== 7. a frase do aviso existe nas três línguas ==')
import json                                                       # noqa: E402
for lang in ('en', 'br', 'es'):
    with io.open('apps/static/data/translations/%s.json' % lang, encoding='utf-8') as fh:
        d = json.load(fh)
    check('%s: swal-mapping-failed-n' % lang,
          bool(str(d.get('swal-mapping-failed-n') or '').strip()), True)

print()
if falhas:
    for f in falhas:
        print('FAIL ' + f)
    sys.exit(1)
print('TUDO OK')
