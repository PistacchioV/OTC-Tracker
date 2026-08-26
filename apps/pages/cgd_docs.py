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

from apps.pages.data_paths import data_dir, data_path, data_write, mapping_file, mapping_write
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
    """
    path = path or DB_PATH
    if duckdb is None or not os.path.isfile(path):
        return []
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
# O Overview mostra TRÊS filas — Legal, Banking OTC e CEM MO —, e nelas entra
# todo documento cujo Status não é `Active`. "Não está ativo" é o que define
# pendência; o que a fila responde é ONDE ele parou.
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
    {'label': 'CGD - Solicitação', 'column': 'Data Solicitação', 'type': 'date',
     'required': True, 'hint': 'Preenchida com a data de hoje', 'col': 'col-md-3'},
    {'label': 'Grupo', 'column': 'Grupo Economico', 'type': 'text',
     'required': False, 'hint': 'Informar o nome de referência para a Razão Social',
     'col': 'col-md-9'},
    {'label': 'Razão Social', 'column': 'Razão Social', 'type': 'textarea',
     'required': True, 'hint': 'Inserir todas as entidades do grupo', 'col': 'col-12'},
    {'label': 'CNPJ', 'column': 'CNPJ', 'type': 'textarea',
     'required': True, 'hint': 'Inserir todas as entidades do grupo', 'col': 'col-12'},
    {'label': 'CGD - Tipo de Assinatura', 'column': SIGNATURE_COLUMN, 'type': 'select',
     'required': True, 'hint': 'Selecionar a forma que o cliente assinará o CGD',
     'col': 'col-md-6'},
    {'label': 'CGD - Domínio cliente', 'column': 'Dominio', 'type': 'textarea',
     'required': False, 'hint': 'Caso o cliente não tenha domínio preencher com NA',
     'col': 'col-md-6'},
    {'label': 'Contatos', 'column': 'Contacts', 'type': 'textarea',
     'required': True, 'hint': 'Adicionar emails que devem ser considerados para solicitação de SSI',
     'col': 'col-md-6'},
    {'label': 'Garantidor', 'column': 'Garantidor', 'type': 'select',
     'required': True, 'hint': 'Yes = cliente possui garantidor | No = cliente não possui garantidor',
     'col': 'col-md-4', 'options': GUARANTOR_OPTIONS, 'default': 'No'},
    # O formulário pede Razão Social E CNPJ do garantidor NUM campo só, e é
    # assim que a lista guarda. O banco tem duas colunas (`Nome Garantidor` e
    # `CNPJ Garantidor`) porque a exportação as separa; o texto digitado aqui vai
    # para a primeira. Partir em dois campos seria inventar um formulário que
    # ninguém preenche assim.
    {'label': 'Informações do garantidor', 'column': 'Nome Garantidor', 'type': 'textarea',
     'required': False, 'hint': 'Preencher com Razão Social e CNPJ do garantidor',
     'col': 'col-md-8', 'default': 'N/A'},
    # O Apêndice é ARQUIVO, e por isso não tem `column`: ele não vai para o
    # banco da lista, vai para o Electronic Inventory da contraparte, como
    # documento `Transactional` — que é onde os documentos por cliente já vivem
    # e onde a mesa os procura. Guardá-lo numa pasta nova, só do Onboarding,
    # criaria um segundo lugar para o mesmo tipo de papel.
    {'label': 'Apêndice', 'column': '', 'type': 'file',
     'required': True, 'hint': 'Adicionar o Template para emissão do CGD',
     'col': 'col-12'},
)

# A pasta do Electronic Inventory em que o Apêndice é gravado, e o prefixo do
# nome do arquivo. `Transactional` é uma das três pastas do inventário
# (`routes.EI_SUBFOLDERS`); o prefixo é o que aparece no começo do nome e é por
# ele que a mesa reconhece o documento na listagem.
APPENDIX_EI_TYPE = 'Transactional'
APPENDIX_EI_SUBTYPE = 'CGD TEMPLATE'

# Os obrigatórios do formulário QUE VIRAM COLUNA, na ordem dele. Derivado do
# `REQUEST_FORM` e não escrito à mão: duas listas divergiriam no dia em que um
# campo deixasse de ser obrigatório, e a fila do Banking continuaria cobrando o
# que ninguém mais pede.
#
# O `and f['column']` não é defensivo: o Apêndice é obrigatório no formulário e
# NÃO tem coluna (é arquivo, vai para o Electronic Inventory). Sem o teste, a
# coluna `''` entraria na lista, nunca estaria preenchida em linha nenhuma e
# TODO documento ficaria preso no Banking para sempre — sem erro em lugar nenhum.
REQUEST_FIELDS = tuple(f['column'] for f in REQUEST_FORM
                       if f['required'] and f['column'])

# As mesas da esteira, NA ORDEM em que o documento passa por elas. `Banking` é a
# primeira: é quem abre a solicitação do CGD. Era um cartão só, `Banking OTC`, e
# ele juntava duas mesas que trabalham em momentos diferentes — a que pede o
# contrato e a que o confere depois de assinado.
STAGES = ('Banking', 'Legal', 'OTC', 'CEM MO')

# O carimbo que cada etapa deixa quando termina. A ORDEM é a da esteira: quem
# procura onde o documento parou pega a primeira que ainda não carimbou.
#
# Vem DEPOIS do `REQUEST_FIELDS`, que ele consome na leitura do módulo: definido
# antes, o Banking nasceria com a lista vazia e nunca casaria com nada — a fila
# ficaria permanentemente zerada, sem erro nenhum.
STAGE_STAMP = (
    ('Banking', REQUEST_FIELDS),
    ('Legal',   ('Emissão', 'Signature Date')),
    ('OTC',     ('OTC - STAMP',)),
    ('CEM MO',  ('MO - STAMP',)),
)

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


def pending_stage(row):
    """`(etapa, derivada?)` de um documento pendente, ou `(None, False)`.

    Documento encerrado não tem etapa — concluído (`Active`) ou morto
    (`Inactive`, `Cancelado`): ninguém está trabalhando nele. Para os demais, o
    cadastro vence a derivação — é ele que sabe que um status novo pertence à
    Legal, e a derivação só olha carimbo.
    """
    if is_closed(row):
        return None, False
    cad = _stage_map().get(_norm(row.get('Status')))
    if cad:
        return cad, False
    for etapa, campos in STAGE_STAMP:
        if any(not str(row.get(c) or '').strip() for c in campos):
            return etapa, True
    # Todos os carimbos dados e o status ainda não é Active: o documento está com
    # a ÚLTIMA mesa que o tocou, esperando o registro fechar. Devolvê-lo sem
    # etapa o faria sumir das três filas — e um pendente que some é pior do que
    # um pendente na fila errada, que alguém corrige cadastrando o status.
    return STAGES[-1], True


def overview(rows=None):
    """As três filas do Overview, na ordem da esteira.

    Cada item leva o que a fila precisa mostrar: cliente, status COMO ESTÁ
    ESCRITO (é ele que a mesa reconhece), aging e se a etapa foi derivada.
    A fila vem ordenada pelo aging decrescente — quem espera há mais tempo
    encabeça, como no Confirmations Monitor.
    """
    rows = load_all() if rows is None else rows
    filas = {e: [] for e in STAGES}
    ativos = 0
    encerrados = 0
    for r in rows:
        if is_active(r):
            ativos += 1
            continue
        # Encerrado sem ter concluído (Inactive, Cancelado) sai das filas mas
        # NÃO conta como ativo: são coisas diferentes, e somá-las esconderia
        # quantos CGDs realmente estão de pé.
        if is_closed(r):
            encerrados += 1
            continue
        etapa, derivada = pending_stage(r)
        filas.setdefault(etapa, []).append({
            'id': r.get(ID_COLUMN, ''),
            'client': (r.get('Razão Social') or r.get('Grupo Economico') or '').strip(),
            'cnpj': (r.get('CNPJ') or '').strip(),
            'doc_type': (r.get('Doc Type') or '').strip(),
            'legal_entity': (r.get('Legal Entity') or '').strip(),
            'status': (r.get('Status') or '').strip(),
            'aging': r.get('Aging', ''),
            'derived': derivada,
            'requested': (r.get(AGING_FROM) or '').strip(),
        })
    def _idade(it):
        return it['aging'] if isinstance(it['aging'], int) else -1
    cards = []
    for e in STAGES:
        itens = sorted(filas.get(e, []), key=_idade, reverse=True)
        cards.append({'stage': e, 'count': len(itens), 'items': itens})
    pendentes = sum(c['count'] for c in cards)
    # Os quatro números fecham: total = pendentes + ativos + encerrados. Sem o
    # `closed` explícito o Overview mostrava três que não somavam o total, e a
    # diferença era justamente o que tinha sumido das filas.
    return {'cards': cards, 'active': ativos, 'closed': encerrados,
            'pending': pendentes, 'total': len(rows)}

