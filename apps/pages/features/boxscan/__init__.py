# -*- coding: utf-8 -*-
"""Box Scan — a varredura do box de booking recap (NDF Comm e Opt Comm).

O caminho MANUAL (botão Import + dropzone) continua no navegador, parseando com
o `otc-fileupload.js`; esta vertical é o mesmo trabalho feito sozinho, com o
porte Python da mesma regra (`otc_boxparse`) — e o `check_boxparse.py` prova que
as duas cópias concordam. O Maker gravado é `BOX`, diferente do `API` dos pulls:
é o que mantém a trava de quatro olhos válida para o deal que a máquina trouxe.
"""
