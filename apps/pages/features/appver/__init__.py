# -*- coding: utf-8 -*-
"""New Version Released — o aviso de reinício para a mesa.

A instância do time roda com o reloader DESLIGADO: depois de um deploy, o
processo que está de pé continua servindo o código velho até alguém derrubá-lo
e subir de novo. Quem usa a ferramenta não tem como saber que isso aconteceu —
a tela abre, tudo responde, e o que ela mostra é a versão anterior. Este card é
o aviso: um e-mail para TODO usuário ativo dizendo qual versão foi liberada e
como reiniciar.

A versão NÃO se digita. Ela sai do `link.txt` que fica ao lado do
`start-otc-tracker.bat`, na pasta Application — o mesmo arquivo que aponta para
o código em uso. Digitada, ela seria o número que alguém lembrou de trocar; lida
do arquivo, é a que a instância vai de fato subir.

Sem scheduler: o envio é sempre o botão do card.
"""
