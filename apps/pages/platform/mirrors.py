# -*- coding: utf-8 -*-
"""O espelho que FALHOU tem de ser dito na tela (§696).

Gravar uma operação na origem dispara cópias para outras telas — o Pending
Confirmation, a esteira das confirmações, a Intrag. Cada cópia é melhor
esforço de propósito (a origem já gravou; derrubar a resposta faria a tela
dizer que não gravou), e por isso cada uma engolia a exceção e só registrava
no log: a tela respondia "Success … sent to Intrag", a cópia não existia, e
nada tentava de novo (o Mapping B3 ID ignora a linha que já é Success).

Aqui a falha é REGISTRADA no request (`falhou`), além do WARNING no log. O
`after_request` do routes devolve o registro no cabeçalho `X-OTC-Mirror-Failed`
de toda resposta de `/api/*`, e o `session-guard.js` — que já embrulha o fetch
de toda página com sessão — mostra o aviso traduzido. Nenhuma página precisa
saber disso: espelho novo só chama `falhou`.

Fora de request (rotina agendada, script) só loga.
"""
import json
import logging

from flask import g, has_request_context

log = logging.getLogger('otc_tracker')

# O que cada alvo é na tela (o `session-guard.js` traduz pela chave).
ALVOS = ('pc', 'mc', 'intrag')
_TETO = 20          # refs por resposta: o cabeçalho tem de caber


def falhou(alvo, ref, exc=None, remocao=False):
    """Registra que a cópia para `alvo` ('pc', 'mc' ou 'intrag') da operação
    `ref` não foi gravada — ou, com `remocao`, que a operação apagada na origem
    NÃO saiu de lá. Devolve False, para quem chama devolver o veredito."""
    ref = str(ref or '').strip() or '?'
    log.warning('[mirror] %s %s de %s NAO foi feita: %s',
                'a remocao' if remocao else 'a copia para', alvo, ref,
                '%s: %s' % (type(exc).__name__, exc) if exc is not None else 'sem motivo')
    if has_request_context():
        lst = g.setdefault('_otc_mirror_failed', [])
        item = {'target': alvo, 'ref': ref}
        if remocao:
            item['op'] = 'remove'
        if item not in lst and len(lst) < _TETO:
            lst.append(item)
    return False


def registradas():
    """As falhas deste request (lista vazia fora dele)."""
    if not has_request_context():
        return []
    return list(g.get('_otc_mirror_failed') or [])


def cabecalho():
    """O valor do `X-OTC-Mirror-Failed`, ou '' sem falha. ASCII puro (o
    cabeçalho HTTP é latin-1): o JSON escapa o que não for."""
    lst = registradas()
    return json.dumps(lst, ensure_ascii=True, separators=(',', ':')) if lst else ''
