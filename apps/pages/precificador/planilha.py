# -*- coding: utf-8 -*-
"""Leitura de planilha — ``.xlsx``, ``.csv`` e ``.tsv`` — sem dependência.

Um ``.xlsx`` é um zip de XML; ler os pedaços que importam cabe em cem linhas e
poupa uma dependência num caminho que roda na estação da mesa. Onde um leitor
ingênuo erra:

**A célula guarda posição, não ordem.** O XML pula célula vazia — uma linha
com ``A1`` e ``D1`` vem com dois elementos. Lendo em sequência a coluna P vira
a N a partir da primeira lacuna, e os números continuam parecendo números.
Aqui a referência (``L12``) vira índice e a linha sai do comprimento certo.

**Texto mora em outro arquivo** (``sharedStrings.xml``); sem resolvê-lo a
coluna de ticker viria ``0``, ``1``, ``2``.

**Data é número** (dias desde 30/12/1899). Quem chama sabe qual coluna é a
data, então ``como_data`` faz as duas leituras, o serial e o texto.
"""
import csv
import io
import re
import zipfile
from datetime import date, datetime, timedelta
from xml.etree import ElementTree

from apps.pages.precificador.erros import ErroFerramenta

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
_ORIGEM_EXCEL = date(1899, 12, 30)


class ErroPlanilha(ErroFerramenta, ValueError):
    """Arquivo que não dá para ler, com o motivo por extenso."""


def _indice_da_coluna(referencia):
    letras = re.match(r'([A-Z]+)', referencia or '')
    if not letras:
        return 0
    indice = 0
    for letra in letras.group(1):
        indice = indice * 26 + (ord(letra) - ord('A') + 1)
    return indice - 1


def letra_da_coluna(indice):
    nome, indice = '', indice + 1
    while indice:
        indice, resto = divmod(indice - 1, 26)
        nome = chr(ord('A') + resto) + nome
    return nome


def _textos_compartilhados(arquivo):
    try:
        bruto = arquivo.read('xl/sharedStrings.xml')
    except KeyError:
        return []
    raiz = ElementTree.fromstring(bruto)
    return [''.join(t.text or '' for t in item.iter(NS + 't'))
            for item in raiz.findall(NS + 'si')]


def _primeira_planilha(arquivo):
    nomes = [n for n in arquivo.namelist()
             if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')]
    if not nomes:
        raise ErroPlanilha('the .xlsx file has no worksheet inside')
    return sorted(nomes)[0]


def ler_xlsx(dados):
    try:
        arquivo = zipfile.ZipFile(io.BytesIO(dados))
    except zipfile.BadZipFile:
        raise ErroPlanilha('this file is not an .xlsx. An old .xls must be saved '
                           'again as .xlsx or CSV.') from None
    with arquivo:
        compartilhados = _textos_compartilhados(arquivo)
        raiz = ElementTree.fromstring(arquivo.read(_primeira_planilha(arquivo)))
        linhas = []
        for linha in raiz.iter(NS + 'row'):
            celulas = []
            for celula in linha.findall(NS + 'c'):
                posicao = _indice_da_coluna(celula.get('r') or '')
                while len(celulas) < posicao:
                    celulas.append('')
                tipo = celula.get('t')
                if tipo == 'inlineStr':
                    valor = ''.join(t.text or '' for t in celula.iter(NS + 't'))
                else:
                    no = celula.find(NS + 'v')
                    valor = (no.text or '') if no is not None else ''
                    if tipo == 's':
                        try:
                            valor = compartilhados[int(valor)]
                        except (ValueError, IndexError):
                            valor = ''
                celulas.append(valor)
            linhas.append(celulas)
    return linhas


def ler_separado(dados):
    """Separador por CONTAGEM (um .csv salvo do Excel em português vem com ;)
    e codificação por tentativa."""
    texto = None
    for codificacao in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            texto = dados.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise ErroPlanilha('could not decode the text file')
    amostra = texto[:8192]
    separador = max(('\t', ';', ','), key=amostra.count)
    if amostra.count(separador) == 0:
        separador = '\t'
    return [linha for linha in csv.reader(io.StringIO(texto), delimiter=separador)]


def ler(nome, dados):
    if (nome or '').lower().endswith('.xlsx'):
        return ler_xlsx(dados)
    if (nome or '').lower().endswith(('.csv', '.tsv', '.txt', '.tab')):
        return ler_separado(dados)
    raise ErroPlanilha('cannot read {arquivo}. Use .xlsx, .csv or .tsv — an old '
                       '.xls must be saved again as one of them.', arquivo=repr(nome))


def celula(linha, indice):
    return (linha[indice] or '').strip() if indice < len(linha) else ''


def como_data(valor):
    """Serial do Excel ou texto. A faixa aceita começa em 1954: uma taxa como
    ``3,74231`` é um serial válido e viraria 02/01/1900 sem reclamar."""
    texto = (valor or '').strip()
    if not texto:
        return None
    try:
        numero = float(texto.replace(',', '.'))
    except ValueError:
        numero = None
    if numero is not None and 20000 <= numero <= 73050:
        return _ORIGEM_EXCEL + timedelta(days=int(numero))
    for formato in ('%d/%m/%Y', '%Y-%m-%d', '%d/%m/%y', '%d-%m-%Y', '%Y/%m/%d', '%m/%d/%Y'):
        try:
            return datetime.strptime(texto[:10], formato).date()
        except ValueError:
            continue
    return None


def como_numero(valor):
    """``'3,74231'`` e ``'3.74231'`` são o mesmo número."""
    texto = (valor or '').strip()
    if not texto:
        return None
    if ',' in texto:
        texto = texto.replace('.', '').replace(',', '.')
    try:
        return float(texto)
    except ValueError:
        return None
