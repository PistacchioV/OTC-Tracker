# -*- coding: utf-8 -*-
"""Onboarding · Tracking Docs — o banco dos CGDs que vem da lista do SharePoint.

A mesa acompanha a emissão dos Contratos Globais de Derivativos numa lista do
SharePoint, exportada como `Sharepoint-CGD.xlsx`. Este módulo é o banco dessa
lista dentro do app: um DuckDB na MESMA pasta dos demais (`Config.DATABASE_DIR`,
§307 — montar o caminho por conta própria deixaria este banco local no dia em
que os outros forem para o share, sem erro nenhum), uma tabela, e as regras que
a tela e o script de importação dividem.

Três coisas que não são óbvias:

- **O `Aging` NÃO é lido da planilha.** A coluna existe lá e envelhece sozinha:
  quem exportou ontem exportou o aging de ontem. Aqui ele é DERIVADO a cada
  leitura (`aging_of`), em dias ÚTEIS do calendário ANBIMA — o mesmo do resto do
  app —, contados da **Data Solicitação**. E ele PARA quando o CGD conclui
  (`Conclusion - Stamp` preenchido): o prazo de quem terminou deixou de correr,
  e mantê-lo subindo cobraria um trabalho que já foi feito.
- **A importação REESCREVE a tabela.** A lista do SharePoint é a fonte, não o
  app: um upsert por chave exigiria inventar uma chave que a lista não tem (não
  há ID; o mesmo CNPJ tem vários documentos) e deixaria no banco linhas que
  alguém apagou de lá. Rodar duas vezes dá o mesmo resultado.
- **`_id` é interno e não é dado.** É o número da linha na importação, e serve
  para a tela endereçar a linha que está editando ou apagando. Ele NÃO é
  estável entre importações — depois de reimportar, a lista é outra.
"""

import logging
import os
from datetime import date, datetime

try:
    import duckdb
except Exception:                                          # pragma: no cover
    duckdb = None

from apps.pages.data_paths import data_write, mapping_file
from apps.pages.database_access import duckdb_read, duckdb_write
# Só o Config: importar o `routes` daqui seria circular (é ele quem importa este
# módulo). O que se repete é a LEITURA da configuração, não o dado.
from apps.config import Config

_LOG = logging.getLogger(__name__)

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
# Os cadastros do /mapping. Constante de módulo (e não caminho montado dentro
# da função) para o teste poder apontá-la para um diretório temporário sem
# escrever no repositório.
_MAPPINGS_DIR = data_write('mappings')

DB_NAME = 'cgd_sharepoint.db'
DB_PATH = os.path.normpath(os.path.join(Config.DATABASE_DIR, DB_NAME))
TABLE = 'cgd_docs'

# As colunas da lista do SharePoint, na ordem em que a tela as mostra. São o
# contrato com a planilha: quem exporta de lá reconhece esta ordem, e o script
# casa as colunas do arquivo POR NOME (normalizado), não por posição.
COLUMNS = [
    'Status',
    'Doc Type',
    'Legal Entity',
    'Razão Social',
    'Grupo Economico',
    'CNPJ',
    'SPN',
    'ECI',
    'CASID',
    'UCN',
    'Dominio',
    'OTC - STAMP',
    'MO - STAMP',
    'Data Solicitação',
    'Garantidor',
    'Nome Garantidor',
    'CNPJ Garantidor',
    'Emissão',
    'Signature Type',
    'Signature Date',
    'B3 ID - JPM',
    'B3 ID - MGT',
    'B3 Register',
    # O carimbo do Taxonomy anexado pela Legal (data · SID de quem anexou). Fica
    # à ESQUERDA do Captis de propósito — é a ordem em que a tela mostra — e NÃO
    # entra em DATE_COLUMNS: o valor carrega o SID junto da data, e o fmt_date
    # jogaria o SID fora ao reformatar.
    'Taxonomy',
    'Captis',
    # Derivada na leitura — ver o cabeçalho do módulo. A coluna fica no banco
    # porque a planilha tem a dela, e guardá-la permite ver o que veio do
    # SharePoint; o que a tela mostra é sempre a conta refeita hoje.
    'Conclusion - Stamp',
    'Aging',
    'Contacts',
    'CSA?',
    'Instituição Financeira',
    'B3 Account',
]

# `_id` é coluna do banco, não da lista: é por ele que a tela endereça a linha.
ID_COLUMN = '_id'
DB_COLUMNS = [ID_COLUMN] + COLUMNS

# A data de onde o aging conta, e a que faz ele parar.
AGING_FROM = 'Data Solicitação'
AGING_STOP = 'Conclusion - Stamp'

# As colunas que a tela desenha como DATA (dd/mm/aaaa) e o filtro entende como
# tal. Ficam aqui e não no template porque o script também as normaliza.
#
# A lista tem de ser COMPLETA. O que não está nela sai como o SharePoint gravou,
# e o SharePoint grava data com hora: `B3 Register` e `Captis` apareciam na
# grade como `2022-08-02 00:00:00` na coluna ao lado de um `02/08/2022` — o
# mesmo dado em duas grafias, na mesma linha, e a de fora ainda ordenava e
# filtrava por outro texto. Data é SEMPRE dd/mm/aaaa na tela (CLAUDE.md §3), e
# `check_cgd_docs.py` recusa coluna de data que fique de fora.
DATE_COLUMNS = ('OTC - STAMP', 'MO - STAMP', 'Data Solicitação', 'Emissão',
                'Signature Date', 'B3 Register', 'Captis', 'Conclusion - Stamp')


# ── Datas ────────────────────────────────────────────────────────────────────

def parse_date(value):
    """Uma data de qualquer das grafias que chegam da planilha, ou `None`.

    O openpyxl devolve `datetime` quando a célula é data de verdade e TEXTO
    quando alguém digitou por cima — e a mesma coluna tem os dois. O serial do
    Excel entra pelo mesmo caminho: número puro dentro da janela de datas é
    contagem desde 30/12/1899 (a origem que o Excel usa por causa do 1900
    bissexto que não existiu).
    """
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    if s.replace('.', '', 1).isdigit() and '.' not in s[:1]:
        try:
            n = float(s)
            # 20000 ≈ 1954 e 80000 ≈ 2119: fora disso é código, não data.
            if 20000 <= n <= 80000:
                from datetime import timedelta
                return (datetime(1899, 12, 30) + timedelta(days=int(n))).date()
        except (TypeError, ValueError):
            pass
    s = s.split(' ')[0].split('T')[0]
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y', '%m/%d/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def fmt_date(value):
    """`dd/mm/aaaa` — o formato da tela em toda a aplicação. Texto que não é data
    volta como veio: apagá-lo esconderia o que está errado na planilha."""
    d = parse_date(value)
    return d.strftime('%d/%m/%Y') if d else (str(value).strip() if value else '')


def _bizdays_between(inicio, fim):
    """Dias úteis de `inicio` (exclusive) a `fim` (inclusive), calendário ANBIMA.

    A função é a MESMA da esteira de confirmação (`manual_conf`), importada em
    vez de recopiada: duas contagens de dia útil no mesmo app divergiriam no
    primeiro feriado que só uma das duas conhecesse. O import é tardio porque o
    `manual_conf` é pesado e nem toda tela que abre este módulo conta aging.
    """
    from apps.pages.manual_conf import _bizdays_between as _mc_bizdays
    return _mc_bizdays(inicio, fim)


def aging_of(row, hoje=None):
    """O aging da linha, em dias ÚTEIS, ou `''` quando não há de onde contar.

    Conta da `Data Solicitação` até hoje — ou até o `Conclusion - Stamp`, quando
    ele existe: o CGD que concluiu parou de envelhecer, e deixá-lo subindo
    colocaria em vermelho um trabalho que já terminou.

    Sem `Data Solicitação` devolve vazio, nunca zero: zero se lê como "entrou
    hoje", e o que aconteceu foi a planilha não dizer quando entrou.
    """
    inicio = parse_date(row.get(AGING_FROM))
    if not inicio:
        return ''
    fim = parse_date(row.get(AGING_STOP)) or (hoje or date.today())
    return _bizdays_between(inicio, fim)


# ── Banco ────────────────────────────────────────────────────────────────────

def ensure_db(path=None):
    """Cria o banco vazio e ACRESCENTA as colunas que faltarem.

    É o que dispensa script de migração (CLAUDE.md §7): o banco está no
    `.gitignore`, então a instância do time tem o dela desde antes da coluna
    nova, e o `INSERT` — que lista as colunas — falharia com *column not found*
    derrubando a tela inteira depois de um pull.
    """
    path = path or DB_PATH
    if duckdb is None:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with duckdb_write(path) as con:
        cols = ', '.join('"{}" VARCHAR'.format(c) for c in DB_COLUMNS)
        con.execute('CREATE TABLE IF NOT EXISTS {} ({})'.format(TABLE, cols))
        existentes = {r[1] for r in con.execute(
            "PRAGMA table_info('{}')".format(TABLE)).fetchall()}
        for c in DB_COLUMNS:
            if c not in existentes:
                # DDL sobre IDENTIFICADOR do próprio código (DB_COLUMNS é
                # constante de módulo): nome de coluna não se binda, e é o único
                # caso em que o cheat sheet da OWASP permite montar a string.
                con.execute('ALTER TABLE {} ADD COLUMN IF NOT EXISTS "{}" VARCHAR'
                            .format(TABLE, c))
    return path


def replace_all(rows, path=None):
    """Reescreve a tabela inteira a partir das linhas da planilha.

    Tudo-ou-nada: a transação do `duckdb_write` só fecha no fim, então uma falha
    no meio deixa a tabela como estava. Meia lista é pior que lista velha — a
    tela não teria como dizer que está incompleta.
    """
    path = ensure_db(path)
    if duckdb is None:
        return 0
    cols = ', '.join('"{}"'.format(c) for c in DB_COLUMNS)
    ph = ', '.join('?' for _ in DB_COLUMNS)
    dados = []
    for i, r in enumerate(rows, start=1):
        linha = [str(i)]
        for c in COLUMNS:
            v = r.get(c, '')
            linha.append('' if v is None else str(v))
        dados.append(linha)
    with duckdb_write(path) as con:
        con.execute('DELETE FROM {}'.format(TABLE))
        if dados:
            con.executemany('INSERT INTO {} ({}) VALUES ({})'.format(TABLE, cols, ph),
                            dados)
    return len(dados)


def load_all(path=None):
    """Todas as linhas, com as datas em dd/mm/aaaa e o **Aging refeito**.

    O aging gravado nunca chega à tela: ele é do dia da exportação, e a lista
    fica semanas no banco entre uma importação e outra.

    Chama `ensure_db` como toda escrita do módulo — é o que dispensa script de
    migração (CLAUDE.md §7): sem isso, um banco em disco anterior a uma coluna
    nova (`Taxonomy` foi o primeiro caso) derruba a leitura com *column not
    found* em vez de se autocompletar. As outras funções já chamam; só a
    leitura tinha ficado de fora.
    """
    path = path or DB_PATH
    if duckdb is None or not os.path.isfile(path):
        return []
    path = ensure_db(path)
    cols = ', '.join('"{}"'.format(c) for c in DB_COLUMNS)
    # `duckdb_read`: lock COMPARTILHADO — duas telas abertas não se excluem.
    with duckdb_read(path) as con:
        linhas = con.execute('SELECT {} FROM {} ORDER BY CAST("{}" AS INTEGER)'
                             .format(cols, TABLE, ID_COLUMN)).fetchall()
    hoje = date.today()
    out = []
    for l in linhas:
        r = {c: ('' if v is None else str(v)) for c, v in zip(DB_COLUMNS, l)}
        for c in DATE_COLUMNS:
            r[c] = fmt_date(r.get(c))
        r['Aging'] = aging_of(r, hoje)
        out.append(r)
    return out


def update_row(row_id, values, path=None):
    """Grava as colunas de UMA linha. Só as colunas conhecidas entram — o resto
    do payload é descartado, que é a "Defense Option 3" do cheat sheet: o nome
    da coluna não pode ser bindado, então ele é validado contra a lista fixa."""
    path = ensure_db(path)
    if duckdb is None:
        return 0
    campos = [(c, values[c]) for c in COLUMNS if c in values]
    if not campos:
        return 0
    sets = ', '.join('"{}" = ?'.format(c) for c, _v in campos)
    args = ['' if v is None else str(v) for _c, v in campos] + [str(row_id)]
    with duckdb_write(path) as con:
        con.execute('UPDATE {} SET {} WHERE "{}" = ?'.format(TABLE, sets, ID_COLUMN),
                    args)
    return 1


def delete_row(row_id, path=None):
    path = ensure_db(path)
    if duckdb is None:
        return 0
    with duckdb_write(path) as con:
        con.execute('DELETE FROM {} WHERE "{}" = ?'.format(TABLE, ID_COLUMN),
                    [str(row_id)])
    return 1


def add_row(values, path=None):
    """Acrescenta uma linha no fim, com o próximo `_id` livre."""
    path = ensure_db(path)
    if duckdb is None:
        return 0
    with duckdb_write(path) as con:
        prox = con.execute('SELECT COALESCE(MAX(CAST("{}" AS INTEGER)), 0) + 1 FROM {}'
                           .format(ID_COLUMN, TABLE)).fetchone()[0]
        cols = ', '.join('"{}"'.format(c) for c in DB_COLUMNS)
        ph = ', '.join('?' for _ in DB_COLUMNS)
        linha = [str(prox)] + ['' if values.get(c) is None else str(values.get(c, ''))
                               for c in COLUMNS]
        con.execute('INSERT INTO {} ({}) VALUES ({})'.format(TABLE, cols, ph), linha)
    return prox


def counts(rows=None):
    """O resumo que os cards do Overview mostram: por status, mais o que está
    atrasado. `late` é uma CONTAGEM de aging alto, não um estado do documento —
    o SLA do CGD não é cadastrado em lugar nenhum, então o número é descritivo."""
    rows = load_all() if rows is None else rows
    por_status = {}
    for r in rows:
        s = (r.get('Status') or '').strip() or '—'
        por_status[s] = por_status.get(s, 0) + 1
    agings = [r['Aging'] for r in rows if isinstance(r.get('Aging'), int)]
    return {
        'total': len(rows),
        'by_status': por_status,
        'aging_max': max(agings) if agings else 0,
        'aging_avg': round(sum(agings) / len(agings), 1) if agings else 0,
        'open': sum(1 for r in rows if not (r.get(AGING_STOP) or '').strip()),
        'done': sum(1 for r in rows if (r.get(AGING_STOP) or '').strip()),
    }


# ── A esteira ────────────────────────────────────────────────────────────────
#
# O Overview mostra TRÊS filas — Legal, OTC e CEM MO —, e nelas entra todo
# documento cujo Status não é `Active` nem encerrado. Legal e OTC trabalham em
# PARALELO desde a criação da solicitação; o que a fila responde é o que ainda
# falta, e um documento pode dever a duas mesas ao mesmo tempo.
#
# A resposta vem de duas fontes, nesta ordem:
#
# 1. o cadastro **`cgd-stage`** do /mapping (STATUS → STAGE). Os status da lista
#    do SharePoint são texto livre de quem opera e mudam sem aviso; fixá-los aqui
#    seria o de-para no código que a casa não aceita (CLAUDE.md §6). O JSON é
#    lido DIRETO (importar o `routes` daqui seria circular), como faz o
#    `recon_fxo` com os cadastros dele;
# 2. sem linha cadastrada, a etapa é DERIVADA pelos carimbos que a própria linha
#    tem — a primeira etapa cujo carimbo falta é onde o documento está. É o que
#    faz a tela nascer respondendo antes de alguém cadastrar coisa nenhuma, e a
#    resposta vem marcada como derivada para ninguém confundir com cadastro.

# O domínio do `CGD - Tipo de Assinatura` — como o cliente vai assinar o contrato.
# São três, e o valor gravado é o código em inglês: `Manual` aparece como
# *Física* na tela em português, mas é o MESMO valor (dois valores para a mesma
# coisa fariam metade da lista deixar de casar com a outra metade).
#
# É o domínio de UM campo, não um de-para: não há nada a traduzir de um sistema
# para outro, e por isso ele é constante de módulo — como o
# `manual_conf.CONFIRMATION_TYPES` — e não um cadastro do /mapping.
SIGNATURE_TYPES = ('FepWeb', 'DocuSign', 'Manual')

# A coluna que guarda esse domínio. Constante porque a tela precisa saber QUAL
# das trinta colunas vira um `select`, e casar pelo texto no navegador seria o
# nome da coluna escrito em dois lugares.
SIGNATURE_COLUMN = 'Signature Type'

# O domínio do `Garantidor` — o formulário pergunta se o cliente TEM garantidor,
# e as duas respostas são as do SharePoint. `Yes`/`No` em inglês porque é o que
# a lista grava: traduzir aqui criaria um terceiro valor para a mesma resposta e
# metade das linhas deixaria de casar com a outra metade no filtro.
GUARANTOR_OPTIONS = ('Yes', 'No')

# O domínio do `Doc Type` — o TIPO de documento transacional que a solicitação
# gera. É o mesmo domínio do Transactional Type do Electronic Inventory, e por
# isso os valores são os de lá, em inglês: o documento sai daqui e vai parar na
# pasta do cliente com esse nome, e uma segunda grafia faria a mesma coisa
# aparecer como dois tipos na listagem.
#
# Domínio de UM campo, como o `SIGNATURE_TYPES` — não é cadastro do /mapping,
# porque não há nada a traduzir de um sistema para outro.
DOC_TYPES = ('CGD', 'Appendix', 'CSA', 'CGD Amendment', 'Appendix Amendment')

# A coluna que guarda esse domínio, pela mesma razão do `SIGNATURE_COLUMN`: a
# tela precisa saber QUAL coluna vira um `select`.
DOC_TYPE_COLUMN = 'Doc Type'

# O domínio da Legal Entity que assina o CGD — as DUAS entidades que têm conta
# de registro na B3 (`CGD_LES` da recon: JPM e MGT). O Banco é o default porque
# é onde a mesa booka a quase totalidade dos contratos. A grafia é a do
# documento, e é POR ELA que se decide qual coluna de B3 ID a solicitação usa.
LEGAL_ENTITIES = ('BANCO J.P MORGAN S.A',
                  'JPMORGAN CHASE BANK, N.A. - SAO PAULO BRANCH')
LEGAL_ENTITY_COLUMN = 'Legal Entity'

# LE → a coluna de B3 ID daquela entidade. O modal do OTC pede UM B3 ID, e qual
# das duas colunas o recebe depende da LE em que a solicitação foi aberta.
_B3_ID_BY_LE = {
    'BANCO J.P MORGAN S.A': 'B3 ID - JPM',
    'JPMORGAN CHASE BANK, N.A. - SAO PAULO BRANCH': 'B3 ID - MGT',
}


def b3_id_column(legal_entity):
    """A coluna de B3 ID da LE da linha. Cega a caixa/acento; `CHASE` no nome é
    o que separa a branch do Banco — LE vazia ou desconhecida cai no JPM, que é
    o default do formulário."""
    v = _norm(legal_entity)
    for le, col in _B3_ID_BY_LE.items():
        if v == _norm(le):
            return col
    return 'B3 ID - MGT' if 'CHASE' in v else 'B3 ID - JPM'

# O formulário de abertura da solicitação, na ORDEM em que ele é preenchido.
# Cada campo diz o rótulo (o do formulário do SharePoint, que nem sempre é o
# nome da coluna), a COLUNA do banco em que ele grava, o tipo do campo, se é
# obrigatório e a dica que aparece embaixo do rótulo.
#
# É uma lista só, no servidor, porque ela tem dois consumidores — o modal de New
# Request e a regra do Banking (`REQUEST_FIELDS` sai daqui) — e escrever os
# campos no template deixaria a fila cobrando um campo que o formulário não pede
# mais, sem erro nenhum.
# `col` é a largura da coluna no grid do modal (as classes do Bootstrap que o
# resto do app usa). A data é estreita de propósito — são dez caracteres, e um
# campo de meia largura ao lado de um texto livre desequilibra a linha.
REQUEST_FORM = (
    {'label': 'CGD - Request Date', 'lang': 'ob-req-f-date', 'column': 'Data Solicitação',
     'type': 'date', 'required': True, 'col': 'col-md-3',
     'hint': 'Filled in with today\'s date', 'hint_lang': 'ob-req-h-date'},
    # O Doc Type é o Transactional Type do Electronic Inventory (DOC_TYPES): o
    # documento que a solicitação gera vai parar na pasta do cliente com esse
    # nome, e uma grafia própria do formulário criaria um segundo tipo na
    # listagem.
    {'label': 'Document Type', 'lang': 'ob-req-f-doctype', 'column': DOC_TYPE_COLUMN,
     'type': 'select', 'required': True, 'col': 'col-md-4',
     'hint': 'Transactional document type of the Electronic Inventory',
     'hint_lang': 'ob-req-h-doctype',
     'options': DOC_TYPES, 'default': 'CGD'},
    # Qual das nossas entidades assina — e é POR ELA que o modal do OTC decide
    # se o B3 ID digitado vai para `B3 ID - JPM` ou `B3 ID - MGT`.
    {'label': 'Legal Entity', 'lang': 'ob-req-f-le', 'column': LEGAL_ENTITY_COLUMN,
     'type': 'select', 'required': True, 'col': 'col-md-5',
     'hint': 'Entity issuing the CGD', 'hint_lang': 'ob-req-h-le',
     'options': LEGAL_ENTITIES, 'default': LEGAL_ENTITIES[0]},
    {'label': 'Economic Group', 'lang': 'ob-req-f-group', 'column': 'Grupo Economico',
     'type': 'text', 'required': False, 'col': 'col-md-8',
     'hint': 'Reference name for the legal names below', 'hint_lang': 'ob-req-h-group'},
    # Checkbox: o valor gravado é Yes/No, como o Garantidor — dois valores para
    # a mesma resposta fariam metade da lista não casar com a outra no filtro.
    {'label': 'Financial Institution', 'lang': 'ob-req-f-fininst',
     'column': 'Instituição Financeira', 'type': 'checkbox', 'required': False,
     'col': 'col-md-4', 'default': '',
     'hint': 'Tick when the client is a financial institution',
     'hint_lang': 'ob-req-h-fininst'},
    # Razão Social e CNPJ pedem TODAS as entidades do grupo, e o separador é o
    # PONTO E VÍRGULA — não a quebra de linha. Ele é o que a mesa já usa na
    # lista do SharePoint, e é o que o `contraparte()` do modal corta para achar
    # a primeira entidade (a pasta do Electronic Inventory é de UM cliente).
    # Trocar o separador aqui sem trocar lá faria o anexo ir para uma pasta com
    # o grupo inteiro no nome.
    {'label': 'Legal Name', 'lang': 'ob-req-f-name', 'column': 'Razão Social',
     'type': 'textarea', 'required': True, 'col': 'col-12',
     'hint': 'Enter every entity of the group, separated by ;',
     'hint_lang': 'ob-req-h-name'},
    {'label': 'Tax ID', 'lang': 'ob-req-f-cnpj', 'column': 'CNPJ',
     'type': 'textarea', 'required': True, 'col': 'col-12',
     'hint': 'Enter every entity of the group, separated by ;',
     'hint_lang': 'ob-req-h-cnpj'},
    # Os quatro identificadores do cliente nos sistemas internos. Opcionais: a
    # solicitação não pode ficar presa esperando um código que outra área emite.
    {'label': 'ECI', 'lang': 'ob-req-f-eci', 'column': 'ECI',
     'type': 'text', 'required': False, 'col': 'col-md-3'},
    {'label': 'SPN', 'lang': 'ob-req-f-spn', 'column': 'SPN',
     'type': 'text', 'required': False, 'col': 'col-md-3'},
    {'label': 'CASID', 'lang': 'ob-req-f-casid', 'column': 'CASID',
     'type': 'text', 'required': False, 'col': 'col-md-3'},
    {'label': 'UCN', 'lang': 'ob-req-f-ucn', 'column': 'UCN',
     'type': 'text', 'required': False, 'col': 'col-md-3'},
    {'label': 'CGD - Signature Type', 'lang': 'ob-req-f-sig', 'column': SIGNATURE_COLUMN,
     'type': 'select', 'required': True, 'col': 'col-md-6',
     'hint': 'How the client will sign the CGD', 'hint_lang': 'ob-req-h-sig'},
    # O domínio do cliente costuma já estar escrito no Apêndice anexado, e é o
    # caso comum — por isso o checkbox nasce MARCADO. A coluna começa com `_` e
    # NÃO é persistida (o update_row descarta chave desconhecida): o que fica
    # gravado é o efeito dela no campo Dominio abaixo, via `enabled_by`.
    {'label': 'Client Domain in the Appendix', 'lang': 'ob-req-f-domappx',
     'column': '_domain_in_appendix', 'type': 'checkbox', 'required': False,
     'col': 'col-md-6', 'default': 'Yes',
     'hint': 'Untick when the domain is NOT in the attached Appendix',
     'hint_lang': 'ob-req-h-domappx'},
    # Desmarcado o checkbox acima, o domínio passa a ser DIGITADO e obrigatório;
    # marcado, o campo trava e a coluna grava que ele está no Apêndice.
    {'label': 'CGD - Client Domain', 'lang': 'ob-req-f-dom', 'column': 'Dominio',
     'type': 'textarea', 'required': False, 'col': 'col-md-6',
     'hint': 'Fill in with NA when the client has no domain',
     'hint_lang': 'ob-req-h-dom',
     'enabled_by': {'column': '_domain_in_appendix', 'value': 'No',
                    'required_when_on': True,
                    'value_when_off': 'Included in the Appendix'}},
    {'label': 'Contacts', 'lang': 'ob-req-f-contacts', 'column': 'Contacts',
     'type': 'textarea', 'required': True, 'col': 'col-md-6',
     'hint': 'E-mails to be considered for the SSI request',
     'hint_lang': 'ob-req-h-contacts'},
    {'label': 'Guarantor', 'lang': 'ob-req-f-guar', 'column': 'Garantidor',
     'type': 'select', 'required': True, 'col': 'col-md-4',
     'hint': 'Yes = the client has a guarantor | No = it does not',
     'hint_lang': 'ob-req-h-guar',
     'options': GUARANTOR_OPTIONS, 'default': 'No'},
    # O formulário pede Razão Social E CNPJ do garantidor NUM campo só, e é
    # assim que a lista guarda. O banco tem duas colunas (`Nome Garantidor` e
    # `CNPJ Garantidor`) porque a exportação as separa; o texto digitado aqui vai
    # para a primeira. Partir em dois campos seria inventar um formulário que
    # ninguém preenche assim.
    #
    # `enabled_by` diz que este campo só vale quando OUTRO tem certo valor, e é
    # o formulário que declara isso — não o JS. Com a regra escrita no
    # navegador, o dia em que o domínio do Garantidor mudasse (ou o campo
    # mudasse de nome) ela continuaria olhando para o valor antigo, e o campo
    # ficaria travado para sempre sem erro nenhum. Ligado, ele passa a ser
    # OBRIGATÓRIO: sem garantidor não há o que preencher, e com garantidor a
    # informação dele é o motivo do campo existir.
    {'label': 'Guarantor Details', 'lang': 'ob-req-f-guarinfo', 'column': 'Nome Garantidor',
     'type': 'textarea', 'required': False, 'col': 'col-md-8', 'default': 'N/A',
     'hint': 'Legal name and Tax ID of the guarantor',
     'hint_lang': 'ob-req-h-guarinfo',
     'enabled_by': {'column': 'Garantidor', 'value': 'Yes', 'required_when_on': True,
                    'value_when_off': 'N/A'}},
    # O Apêndice é ARQUIVO, e por isso não tem `column`: ele não vai para o
    # banco da lista, vai para o Electronic Inventory da contraparte, como
    # documento `Transactional` — que é onde os documentos por cliente já vivem
    # e onde a mesa os procura. Guardá-lo numa pasta nova, só do Onboarding,
    # criaria um segundo lugar para o mesmo tipo de papel.
    {'label': 'Appendix', 'lang': 'ob-req-f-appx', 'column': '', 'type': 'file',
     'required': True, 'col': 'col-12',
     'hint': 'Attach the template used to issue the CGD',
     'hint_lang': 'ob-req-h-appx'},
)

# A pasta do Electronic Inventory em que o Apêndice é gravado, e o prefixo do
# nome do arquivo. `Transactional` é uma das três pastas do inventário
# (`routes.EI_SUBFOLDERS`); o prefixo é o que aparece no começo do nome e é por
# ele que a mesa reconhece o documento na listagem.
APPENDIX_EI_TYPE = 'Transactional'
APPENDIX_EI_SUBTYPE = 'CGD TEMPLATE'

# Os obrigatórios do formulário QUE VIRAM COLUNA, na ordem dele. Derivado do
# `REQUEST_FORM` e não escrito à mão: duas listas divergiriam no dia em que um
# campo deixasse de ser obrigatório, e a validação do Save continuaria cobrando
# o que ninguém mais pede.
#
# O `and f['column']` não é defensivo: o Apêndice é obrigatório no formulário e
# NÃO tem coluna (é arquivo, vai para o Electronic Inventory), e o checkbox do
# domínio tem uma coluna PSEUDO (`_domain_in_appendix`) que não é persistida.
# Sem os testes, uma coluna que nunca se preenche entraria na lista e a
# validação do formulário cobraria o impossível — sem erro em lugar nenhum.
REQUEST_FIELDS = tuple(f['column'] for f in REQUEST_FORM
                       if f['required'] and f['column']
                       and not f['column'].startswith('_'))

# As mesas da esteira. `Banking` SAIU: a ação dele é abrir a solicitação, e ela
# acontece inteira no New Request — solicitação criada já nasce pendente em
# **Legal e OTC ao mesmo tempo** (as duas trabalham em paralelo), e o CEM MO
# recebe quando o Taxonomy é anexado pela Legal.
STAGES = ('Legal', 'OTC', 'CEM MO')

# O carimbo que ENCERRA cada mesa. Legal termina anexando o Taxonomy (a coluna
# guarda data · SID de quem anexou); OTC termina no modal do abonado (Emissão,
# Signature Date, B3 ID → `OTC - STAMP`); CEM MO termina no Complete
# (`MO - STAMP` + Conclusion). Não é mais uma FILA: Legal e OTC correm juntas,
# e por isso quem responde é `pending_stages` (plural), não a primeira que
# falta.
LEGAL_STAMP = 'Taxonomy'
OTC_STAMP = 'OTC - STAMP'
MO_STAMP = 'MO - STAMP'

ACTIVE_STATUS = 'ACTIVE'

# Status que tiram o documento das filas SEM ele ter concluído. `Inactive` é o
# CGD que deixou de valer e `Cancelado` o que não vai adiante — nos dois casos
# não há mesa trabalhando neles, e derivar uma etapa por carimbo faltante os
# jogava na fila do Legal (que é a primeira que falta carimbo em quem nunca
# começou). Um encerrado na fila é pior do que parece: ele envelhece para
# sempre no topo da lista, empurrando para baixo o que alguém tem de fazer.
#
# A comparação é por PEDAÇO porque a grafia vem do SharePoint e é livre
# (`Inactive`, `Inativo`, `CANCELADO`, `Cancelled`). E `INACTIVE` contém
# `ACTIVE`: o teste do encerrado vem antes do de ativo em todo lugar que os
# dois convivem.
CLOSED_MARKS = ('INACTIV', 'INATIV', 'CANCEL')

_STAGE_MAP = {'mtime': None, 'rows': None}

def _norm(s):
    """Caixa, espaço e acento fora — a comparação de status é cega às três.
    `Assinatura Concluída` e `ASSINATURA CONCLUIDA` são o mesmo status escrito
    por duas pessoas."""
    import unicodedata
    s = unicodedata.normalize('NFKD', str(s or ''))
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return ' '.join(s.upper().split())


def _stage_map():
    """`{STATUS normalizado: STAGE}` do cadastro `cgd-stage`, cacheado por mtime.

    Arquivo ausente devolve mapa vazio, e aí vale a derivação: a instância em que
    ninguém abriu o /mapping continua com a tela respondendo.
    """
    path = mapping_file('cgd-stage', _MAPPINGS_DIR)
    try:
        mt = os.path.getmtime(path)
    except OSError:
        _STAGE_MAP['mtime'], _STAGE_MAP['rows'] = None, {}
        return {}
    if _STAGE_MAP['mtime'] == mt and _STAGE_MAP['rows'] is not None:
        return _STAGE_MAP['rows']
    import json
    try:
        with open(path, encoding='utf-8') as fh:
            linhas = json.load(fh) or []
    except Exception:
        linhas = []
    mapa = {}
    for r in linhas if isinstance(linhas, list) else []:
        st = _norm(r.get('STATUS'))
        et = str(r.get('STAGE') or '').strip()
        if st and et:
            mapa[st] = et
    _STAGE_MAP['mtime'], _STAGE_MAP['rows'] = mt, mapa
    return mapa


def is_active(row):
    """`Status` = Active — o documento está de pé e não é pendência de ninguém.

    Comparação EXATA de propósito: `Inactive` normaliza para `INACTIVE`, que
    contém `ACTIVE`, e um teste por pedaço contaria o encerrado como ativo.
    """
    return _norm(row.get('Status')) == ACTIVE_STATUS


def is_closed(row):
    """O documento saiu das filas — concluído (`Active`) ou encerrado.

    É o teste que o Overview usa para decidir se alguém ainda trabalha nele.
    `is_active` continua respondendo só pelo concluído, que é o número que a
    tela mostra.
    """
    v = _norm(row.get('Status'))
    if v == ACTIVE_STATUS:
        return True
    return any(m in v for m in CLOSED_MARKS)


def pending_stages(row):
    """`(etapas, derivadas?)` de um documento pendente — LISTA, porque Legal e
    OTC correm em paralelo: a solicitação recém-criada está nas duas filas ao
    mesmo tempo, e dizer uma só esconderia a outra mesa do próprio trabalho.

    Documento encerrado não tem etapa. O cadastro `cgd-stage` vence a derivação
    (uma etapa só — quem cadastrou foi explícito); um STAGE cadastrado que não
    existe mais (o antigo `Banking`) cai na derivação, senão o item sumiria das
    filas sem erro nenhum.
    """
    if is_closed(row):
        return [], False
    cad = _stage_map().get(_norm(row.get('Status')))
    if cad and cad in STAGES:
        return [cad], False
    etapas = []
    tax = str(row.get(LEGAL_STAMP) or '').strip()
    if not tax:
        etapas.append('Legal')
    elif not str(row.get(MO_STAMP) or '').strip():
        # Taxonomy anexado → a pendência da Legal PASSA para o CEM MO.
        etapas.append('CEM MO')
    if not str(row.get(OTC_STAMP) or '').strip():
        etapas.append('OTC')
    if etapas:
        # Na ordem da esteira, que é a ordem dos cards na tela.
        return [e for e in STAGES if e in etapas], True
    # Todos os carimbos dados e o status ainda não é Active: o documento está
    # com a ÚLTIMA mesa, esperando o registro fechar. Devolvê-lo sem etapa o
    # faria sumir das filas — e um pendente que some é pior do que um pendente
    # na fila errada, que alguém corrige cadastrando o status.
    return [STAGES[-1]], True


def pending_stage(row):
    """`(etapa, derivada?)` — a PRIMEIRA das etapas pendentes, ou `(None,
    False)`. Mantida para quem precisa de uma resposta singular (a coluna da
    grade mostra todas via `pending_stages`)."""
    etapas, derivada = pending_stages(row)
    return (etapas[0] if etapas else None), (derivada if etapas else False)


def overview(rows=None):
    """As três filas do Overview, na ordem da esteira.

    O MESMO documento pode estar em mais de uma fila (Legal e OTC correm em
    paralelo), então `pending` conta DOCUMENTOS distintos, não itens de card.
    Cada item leva o que a fila precisa mostrar: cliente, status COMO ESTÁ
    ESCRITO, aging, a LE (é ela que diz qual B3 ID o modal do OTC pede) e se a
    etapa foi derivada. A fila vem ordenada pelo aging decrescente.
    """
    rows = load_all() if rows is None else rows
    filas = {e: [] for e in STAGES}
    ativos = 0
    inativos = 0
    cancelados = 0
    pendentes = 0
    for r in rows:
        if is_active(r):
            ativos += 1
            continue
        # Encerrado sem ter concluído sai das filas e NÃO conta como ativo. O
        # Inactive (valeu e deixou de valer) e o Cancelado (nunca chegou a
        # valer) saem SEPARADOS: são desfechos diferentes, e o card de cada um
        # existe para a diferença aparecer.
        if is_closed(r):
            if 'INACTIV' in _norm(r.get('Status')) or 'INATIV' in _norm(r.get('Status')):
                inativos += 1
            else:
                cancelados += 1
            continue
        etapas, derivada = pending_stages(r)
        pendentes += 1
        item = {
            'id': r.get(ID_COLUMN, ''),
            'client': (r.get('Razão Social') or r.get('Grupo Economico') or '').strip(),
            'cnpj': (r.get('CNPJ') or '').strip(),
            'doc_type': (r.get('Doc Type') or '').strip(),
            'legal_entity': (r.get(LEGAL_ENTITY_COLUMN) or '').strip(),
            'status': (r.get('Status') or '').strip(),
            'aging': r.get('Aging', ''),
            'derived': derivada,
            'requested': (r.get(AGING_FROM) or '').strip(),
            'taxonomy': (r.get(LEGAL_STAMP) or '').strip(),
        }
        for etapa in etapas:
            filas.setdefault(etapa, []).append(dict(item))
    def _idade(it):
        return it['aging'] if isinstance(it['aging'], int) else -1
    cards = []
    for e in STAGES:
        itens = sorted(filas.get(e, []), key=_idade, reverse=True)
        cards.append({'stage': e, 'count': len(itens), 'items': itens})
    # Os números FECHAM: total = pendentes + ativos + inativos + cancelados.
    # `closed` continua no payload (inativos + cancelados) para quem soma os
    # quatro de antes.
    return {'cards': cards, 'active': ativos, 'inactive': inativos,
            'cancelled': cancelados, 'closed': inativos + cancelados,
            'pending': pendentes, 'total': len(rows)}

