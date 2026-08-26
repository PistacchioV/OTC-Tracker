# -*- coding: utf-8 -*-
"""As regras do aviso — puras: o texto do link.txt chega por parâmetro."""
import re

# O .bat que a mesa executa na pasta Application. Constante porque ele aparece em
# dois lugares (o corpo do e-mail e o texto do card) e um nome errado manda a
# pessoa procurar um arquivo que não existe.
STARTER = 'start-otc-tracker.bat'

# `v8`, `v10`, `v8.2` — como TOKEN INTEIRO. Sem as âncoras, o `v` de qualquer
# palavra seguida de dígito casaria, e o caminho de rede que costuma estar no
# arquivo é cheio de candidatos.
VERSION_RE = re.compile(r'(?<![A-Za-z0-9])[vV](\d+(?:\.\d+)*)(?![A-Za-z0-9])')


def subject(versao):
    return 'OTC Tracker - New version {} released, please restart'.format(versao)


def parse_link(texto):
    """(versao, erro) do CONTEÚDO do link.txt.

    Erro em vez de exceção porque o card precisa DIZER o que houve — e um
    arquivo vazio e uma versão que não se reconhece são problemas diferentes.
    """
    texto = str(texto or '').strip()
    if not texto:
        return ('', 'link.txt está vazio')
    # A ÚLTIMA ocorrência, não a primeira: o arquivo costuma guardar um caminho
    # terminado na pasta da versão (`...\otc-source\v8`), e é o fim dele que
    # responde "qual versão".
    achados = VERSION_RE.findall(texto)
    if achados:
        return ('v' + achados[-1], '')
    # Sem `vN`, vale o último pedaço do que estiver escrito — um nome de pasta,
    # uma data, o que a pessoa que publicou tiver posto. Só se for curto: um
    # parágrafo inteiro no lugar da versão é ilegível no e-mail.
    ultima = [ln.strip() for ln in texto.splitlines() if ln.strip()][-1]
    pedaco = re.split(r'[\\/]', ultima)[-1].strip()
    if pedaco and len(pedaco) <= 40:
        return (pedaco, '')
    return ('', 'não reconheci a versão no conteúdo do link.txt')


def href(endereco):
    """O endereço com esquema, para virar `href`.

    O atalho se ESCREVE `go/otctracker` — é assim que a mesa o digita e é assim
    que ele tem de aparecer no texto —, mas como `href` ele é um caminho
    RELATIVO: clicado no Outlook, o cliente o resolve contra nada e o link morre.
    O texto continua sendo o atalho; o destino ganha o `http://`.
    """
    e = str(endereco or '').strip()
    return e if '://' in e else 'http://' + e.lstrip('/')
