"""O modal padrao da casa, e quem ainda destoa dele.

Sao 52 modais no app. O padrao e o do /mapping, e ele existe para o mesmo editor
nao ter duas caras dependendo da tela em que a pessoa esta:

    <div class="modal-content liquid-glass">
      <div class="modal-header py-2">
        <h5 class="modal-title fs-6"> … </h5>
      <div class="modal-body">  <div class="row g-3">
        <label class="form-label fs-xs text-muted mb-1">
      <div class="modal-footer py-2">
        botao de ICONE vermelho (descartar) + verde (gravar)

O Track Confirmations tinha cabecalho sem altura, titulo de outro tamanho, grade
mais apertada, rotulo com CSS proprio e botoes de TEXTO — e ainda redesenhava a
moldura do `modal-content` na propria pagina, o que faz o mesmo modal ter dois
contornos no tema escuro.

Este script NAO exige que os 52 estejam no padrao: oito arquivos ainda estao
fora, e alguns sao telas de demonstracao do tema comprado. Ele PRENDE A LISTA:
um modal novo fora do padrao falha, e um dos oito que for corrigido tambem falha
— pedindo que saia da lista. E assim que a divida para de crescer sem obrigar a
pagar tudo de uma vez.
"""
import io
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
TPL = os.path.join(ROOT, 'apps', 'templates')

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# Os que ainda nao seguem o padrao, com QUANTAS instancias cada um. Corrigiu um?
# Tire-o daqui. Nasceu um novo fora do padrao? Ele aparece e o teste falha.
FORA_DO_PADRAO = {
    'pages/calendar.html': 1,                 # tela de demonstracao do tema
    'pages/chat.html': 3,                     # idem
    'pages/other-products-option-settlement-advice.html': 1,
    'pages/other-products-swap-settlement-advice.html': 1,
    'pages/reconciliation-comitente.html': 1,
    'pages/reconciliation-fxo.html': 1,
    'pages/users-roles.html': 1,
    'partials/topbar.html': 1,
}

atual = {}
for raiz, _dirs, arqs in os.walk(TPL):
    for a in arqs:
        if not a.endswith('.html'):
            continue
        caminho = os.path.join(raiz, a)
        rel = os.path.relpath(caminho, TPL).replace(os.sep, '/')
        texto = io.open(caminho, encoding='utf-8').read()
        n = sum(1 for m in re.finditer(r'<div class="modal-content([^"]*)"', texto)
                if 'liquid-glass' not in m.group(1))
        if n:
            atual[rel] = n

print('== a divida nao cresce ==')
novos = sorted(k for k in atual if k not in FORA_DO_PADRAO)
check('nenhum modal NOVO fora do padrao', novos, [])
corrigidos = sorted(k for k in FORA_DO_PADRAO if k not in atual)
check('e a lista nao guarda quem ja foi corrigido', corrigidos, [])
piorou = sorted(k for k in atual if k in FORA_DO_PADRAO and atual[k] > FORA_DO_PADRAO[k])
check('nenhum arquivo da lista ganhou modal a mais', piorou, [])

print('\n== o Track Confirmations segue o padrao ==')
# Ele acabou de ser alinhado; sem isto, a proxima edicao da pagina o desalinha
# de novo e ninguem nota ate alguem abrir o modal.
trk = io.open(os.path.join(TPL, 'pages', 'manual-confirmation-track.html'),
              encoding='utf-8').read()
for trecho, rotulo in [
        ('modal-content liquid-glass', 'a moldura e a da casa'),
        ('modal-header py-2', 'o cabecalho tem altura'),
        ('modal-title fs-6', 'o titulo e fs-6'),
        ('row g-3" id="mcEditGrid"', 'a grade e g-3'),
        ('form-label fs-xs text-muted mb-1', 'o rotulo e o padrao'),
        ('modal-footer py-2', 'o rodape tem altura'),
        ('btn btn-sm btn-danger', 'o descartar e o icone vermelho'),
        ('btn btn-sm btn-success', 'o gravar e o icone verde')]:
    check('  ' + rotulo, trecho in trk, True)
# E a pagina nao pode voltar a redesenhar a moldura por conta propria.
check('  e a pagina nao redesenha o modal-content',
      re.search(r'#mcEditModal\s+\.modal-content\s*\{', trk) is None, True)

print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
