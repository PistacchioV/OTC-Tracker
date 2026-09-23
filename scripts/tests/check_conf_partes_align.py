#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_conf_partes_align.py — o CNPJ sob o nome das Partes, na TELA das
confirmações do Word.

Na tela de MGT × Cliente o CNPJ da Parte A saía 172px à DIREITA do nome e o da
Parte B 21px à ESQUERDA (23/09/2026): o bloco é export do Word, com o nome
posicionado por tab (`mso-tab-count`, que o navegador desenha como &nbsp;) e o
CNPJ por margem MAIS um recuo de &nbsp; que só o PDF deveria ler. O mesmo nos
outros quatro documentos com esse bloco. Quem alinha é o
`static/js/conf-partes-align.js`, que roda só na tela.

O que este script prende, no Chromium:
  1. nos cinco documentos, com o script, o "CNPJ" começa EXATAMENTE onde o
     nome começa (Parte A e Parte B); sem ele, o desalinhamento é o da imagem;
  2. o script entra na tela e NÃO no modo `doc_only` — o `.doc` e o PDF são
     renderizados dele, e o Word não roda script (é por isso que o conserto é
     JS, e não uma regra de <style>, que valeria também no Word).
"""
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ.setdefault('OTC_DISABLE_SCHEDULERS', '1')

DOCS = ('ndf-mgt-strike-me', 'ndf-fwdstart-strike-me', 'option-fx-vanilla-strike-me',
        'option-fx-asian-strike-me', 'swap-edg-opcao-arrependimento')
fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


JS = r"""()=>{
 const ps=[...document.querySelectorAll('p')];
 const txt=p=>p.textContent.replace(/\s+/g,' ');
 const posAfter=(p,label)=>{const nos=[];let todo='';const w=document.createTreeWalker(p,NodeFilter.SHOW_TEXT);let n;
   while(n=w.nextNode()){nos.push([n,todo.length]);todo+=n.textContent}
   const m=new RegExp(label.replace(/ /g,'[\\s\\u00a0]+')).exec(todo); if(!m) return null;
   const k=todo.slice(m.index+m[0].length).search(/[^\s :]/); if(k<0) return null;
   const pos=m.index+m[0].length+k;
   for(let q=nos.length-1;q>=0;q--){if(nos[q][1]<=pos){const rg=document.createRange();rg.setStart(nos[q][0],pos-nos[q][1]);rg.setEnd(nos[q][0],pos-nos[q][1]+1);const r=rg.getClientRects()[0];return r?r.left:null}} return null};
 const out=[];
 for(const lab of ['Parte A','Parte B']){const i=ps.findIndex(p=>txt(p).includes(lab+':')); if(i<0){out.push(null,null);continue}
   let c=null; for(let k=i+1;k<Math.min(i+4,ps.length);k++){if(txt(ps[k]).includes('CNPJ')){c=posAfter(ps[k],'');c=null;const w=document.createTreeWalker(ps[k],NodeFilter.SHOW_TEXT);let n;while(n=w.nextNode()){const j=n.textContent.indexOf('CNPJ');if(j>=0){const rg=document.createRange();rg.setStart(n,j);rg.setEnd(n,j+4);c=rg.getClientRects()[0].left;break}}break}}
   out.push(posAfter(ps[i],lab), c)}
 return out}"""
def trecho(src):
    k=src.find('das Partes'); i=src.rfind('<p',0,k); j=src.find('individualmente',k); j=src.find('</p>',j)+4
    t=re.sub(r'\{\{[^}]*\}\}','EMPRESA EXEMPLO LTDA',src[i:j]); return re.sub(r'\{%.*?%\}','',t,flags=re.S)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('playwright ausente — o teste mede no Chromium'); sys.exit(1)

JS_ALINHA = open(os.path.join(ROOT, 'apps/static/js/conf-partes-align.js'), encoding='utf-8').read()

print('== 1. no Chromium: CNPJ sob o nome ==')
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 1000, 'height': 400})
    for nome in DOCS:
        t = trecho(open('apps/templates/confirmations/%s.html' % nome, encoding='utf-8').read())
        for com in (False, True):
            pg.set_content('<html><body style="font-family:Times New Roman;font-size:11pt;'
                           'width:900px"><div class="WordSection1">' + t + '</div>' +
                           ('<script>' + JS_ALINHA + '</script>' if com else '') + '</body></html>')
            pg.wait_for_timeout(120)
            a_nome, a_cnpj, b_nome, b_cnpj = pg.evaluate(JS)
            if None in (a_nome, a_cnpj, b_nome, b_cnpj):
                check('%s: o bloco das Partes é encontrado' % nome, False)
                continue
            if com:
                check('%s: CNPJ da Parte A sob o nome' % nome, round(a_cnpj - a_nome), 0)
                check('%s: CNPJ da Parte B sob o nome' % nome, round(b_cnpj - b_nome), 0)
            else:
                check('%s: sem o script o defeito aparece (prova de que o teste mede)' % nome,
                      abs(a_cnpj - a_nome) > 5 or abs(b_cnpj - b_nome) > 5)
    b.close()

print('\n== 2. só na tela, nunca no .doc/PDF ==')
from apps import create_app                                   # noqa: E402
from apps.config import DebugConfig                           # noqa: E402
from flask import render_template                             # noqa: E402
app = create_app(DebugConfig)
with app.test_request_context('/'):
    for nome in DOCS:
        tela = render_template('confirmations/%s.html' % nome, conf={}, doc_only=False)
        doc = render_template('confirmations/%s.html' % nome, conf={}, doc_only=True)
        check('%s: o script está na tela' % nome, 'conf-partes-align.js' in tela)
        check('%s: e fora do doc_only' % nome, 'conf-partes-align.js' in doc, False)

print()
if fails:
    print('FAILED: %d check(s)' % len(fails))
    sys.exit(1)
print('TUDO OK')
sys.exit(0)
