# -*- coding: utf-8 -*-
"""O badge "Missing Counterparty" na lista do funil de Excel das telas de New Deals.

O funil (`excel-filter.js`) lista o que o DataTables DESENHA na célula
(`render('display')`), e o badge do `missing-counterparty.js` é só DOM — o dado
da célula fica intacto (§685). Resultado: nas seis telas de NDF/Opção o
"Missing Counterparty" não aparecia na lista de valores de coluna nenhuma, e não
havia como filtrar as linhas sem contraparte.

O que se prende:

  1. o `cellKey` do funil passa o texto pelo gancho `otcCellText` publicado no
     nó da tabela, lido na hora (a página liga o helper antes ou depois);
  2. o `missing-counterparty.js`, executado no node com uma tabela falsa: publica
     o gancho; no Status o texto é o badge SOZINHO (ele substitui a célula), nas
     colunas de contraparte o texto + o badge (ou só o badge na vazia); coluna
     fora do badge e linha com contraparte cadastrada ficam como o render.

    OTC_SHARED_DRIVE_ROOT=/tmp/otc-share python scripts/tests/check_missing_cp_filter.py
"""
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
EXCEL = os.path.join(ROOT, 'apps', 'static', 'js', 'excel-filter.js')
CP = os.path.join(ROOT, 'apps', 'static', 'js', 'missing-counterparty.js')
fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


print('== 1. o funil consulta o gancho da tabela ==')
src = open(EXCEL, encoding='utf-8').read()
i = src.find('function cellKey(')
corpo = src[i:src.find('\n    }\n', i)]
check('cellKey lê o otcCellText do nó da tabela', 'nTable.otcCellText' in corpo)
check('cellKey devolve o texto do gancho', 'txt = hook(rowIdx, col, txt)' in corpo)

print('\n== 2. o gancho do missing-counterparty.js no node ==')
node = shutil.which('node')
if not node:
    print('  skip: sem node')
else:
    js = r"""
var window = { console: console };
global.window = window;
global.fetch = function () { return new Promise(function () {}); };   // le-accronym nunca chega
%s
// colunas: 0 Actions, 1 Deal, 2 Status, 3 SPN, 4 Acronym, 5 Client, 6 Tax ID
var ROWS = [
  ['', 'D1', 'New', '999', 'CPTY1', '', ''],            // SPN fora do RefData -> missing
  ['', 'D2', 'New', '123', 'CPTY2', 'CLIENTE SA', '11'], // cadastrada
  ['', 'D3', 'Approved', '888', '', 'PARCIAL', '']      // missing, Client com texto
];
var NODE = {};
var table = {
  table: function () { return { node: function () { return NODE; } }; },
  row: function (i) { return { data: function () { return ROWS[i]; } }; }
};
var inst = window.MissingCounterparty.init({
  table: table,
  getRefData: function () { return [{ SPN: '00123', COUNTERPARTY: 'CLIENTE SA' }]; },
  cols: { status: 2, spn: 3, acr: 4, client: 5, taxid: 6, info: [3, 5, 6] }
});
var h = NODE.otcCellText;
console.log(JSON.stringify({
  publicado: typeof h,
  status: h(0, 2, 'New'),
  spn: h(0, 3, '999'),
  client_vazio: h(0, 5, ''),
  client_texto: h(2, 5, 'PARCIAL'),
  fora: h(0, 1, 'D1'),
  cadastrada_status: h(1, 2, 'New'),
  cadastrada_client: h(1, 5, 'CLIENTE SA')
}));
""" % open(CP, encoding='utf-8').read()
    r = subprocess.run([node, '-e', js], capture_output=True, text=True)
    if r.returncode:
        check('o script roda no node', r.stderr.strip(), '')
    else:
        got = json.loads(r.stdout.strip().splitlines()[-1])
        M = 'Missing Counterparty'
        check('publica o gancho no nó da tabela', got['publicado'], 'function')
        check('Status sem contraparte: o badge sozinho', got['status'], M)
        check('SPN sem contraparte: o texto + o badge', got['spn'], '999 ' + M)
        check('coluna de contraparte vazia: só o badge', got['client_vazio'], M)
        check('coluna com texto: o texto + o badge', got['client_texto'], 'PARCIAL ' + M)
        check('coluna fora do badge: o render', got['fora'], 'D1')
        check('contraparte cadastrada: Status como o render', got['cadastrada_status'], 'New')
        check('contraparte cadastrada: Client como o render', got['cadastrada_client'], 'CLIENTE SA')

print(('\nFALHAS (%d): %s' % (len(fails), fails)) if fails else '\nTUDO OK')
sys.exit(1 if fails else 0)
