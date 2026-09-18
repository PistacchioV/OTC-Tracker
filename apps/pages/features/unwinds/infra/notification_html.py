# -*- coding: utf-8 -*-
"""O corpo HTML de um e-mail do Athena -> as tabelas, como texto de celula.

Le QUALQUER tabela: devolve `[[linha, ...], ...]` por tabela, cada linha uma
lista de celulas ja em texto limpo. Quem sabe o que cada tabela significa e o
`domain` — aqui nao mora regra de negocio nenhuma.

O e-mail e HTML do Word, e sao os detalhes dele que quebram um leitor ingenuo:

  * **o rotulo vem QUEBRADO em duas linhas** quando e longo ('Calculated\\n
    Termination Fee' na celula, com a indentacao do Word no meio). Sem colapsar
    o branco, ele nunca casa com 'Calculated Termination Fee' — e o campo sai
    vazio sem erro nenhum.
  * **o titulo da tabela tem espaco no FIM** ('Before Unwind ', 'After Unwind ').
  * o Word fecha toda celula com um `<o:p></o:p>` vazio e enche os espacos com
    `&nbsp;` — os dois viram branco comum aqui.
  * `<style>` traz o corpo dentro de `<!-- -->` e o `<head>` tem comentario
    condicional do Office (`<!--[if gte mso 9]>`). O HTMLParser trata os dois
    como comentario, entao nao vazam para as celulas.
  * **o `id` das linhas (`row_0`, `row_1`, ...) REINICIA na segunda tabela**:
    nao e chave de nada, e casar por ele junta as duas.

Tabela dentro de tabela vai para a tabela mais interna (pilha), e nao derrete
com a de fora — o Outlook aninha tabela por qualquer motivo de layout.
"""
import re
from html.parser import HTMLParser

_BRANCO = re.compile(r'\s+')

# Tags cujo texto NAO e conteudo de celula.
_MUDAS = ('style', 'script', 'xml')


def _limpo(txt):
    """O `textContent` de uma celula, com o branco COLAPSADO (o rotulo quebrado
    em duas linhas volta inteiro) e o nbsp do Word virando espaco comum."""
    return _BRANCO.sub(' ', (txt or '').replace('\xa0', ' ')).strip()


class _Tabelas(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self)
        self.tabelas = []          # [] de tabela; tabela = [] de linha; linha = [] de celula
        self._pilha = []           # tabelas abertas (a do topo e a que recebe)
        self._linha = None
        self._celula = None
        self._mudo = 0

    # -- tags ------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        if tag in _MUDAS:
            self._mudo += 1
        elif tag == 'table':
            nova = []
            self.tabelas.append(nova)
            self._pilha.append(nova)
        elif tag == 'tr' and self._pilha:
            self._linha = []
        elif tag in ('td', 'th') and self._linha is not None:
            self._celula = []
        elif tag == 'br' and self._celula is not None:
            self._celula.append(' ')

    def handle_endtag(self, tag):
        if tag in _MUDAS:
            self._mudo = max(0, self._mudo - 1)
        elif tag in ('td', 'th'):
            if self._celula is not None and self._linha is not None:
                self._linha.append(_limpo(''.join(self._celula)))
            self._celula = None
        elif tag == 'tr':
            if self._linha and self._pilha:
                self._pilha[-1].append(self._linha)
            self._linha = None
        elif tag == 'table':
            # Celula/linha em aberto quando a tabela fecha: HTML torto, fecha na mao.
            if self._celula is not None and self._linha is not None:
                self._linha.append(_limpo(''.join(self._celula)))
            self._celula = None
            if self._linha and self._pilha:
                self._pilha[-1].append(self._linha)
            self._linha = None
            if self._pilha:
                self._pilha.pop()

    def handle_data(self, data):
        if not self._mudo and self._celula is not None:
            self._celula.append(data)


def tables(html):
    """[[linha, ...], ...] — uma lista de linhas por tabela, na ordem do
    documento. Tabela sem nenhuma linha nao entra."""
    p = _Tabelas()
    p.feed(html or '')
    p.close()
    return [t for t in p.tabelas if t]
