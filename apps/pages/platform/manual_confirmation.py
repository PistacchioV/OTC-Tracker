# -*- coding: utf-8 -*-
"""A cola da esteira de confirmação manual (`_mc_*`) — o que liga o New Deals,
o Electronic Inventory, o Pending Confirmation e o Confirmations Monitor à
esteira dos dois DuckDBs (`apps/pages/manual_conf.py`, que segue sendo o dono
do banco e das regras).

Movido VERBATIM do `routes.py` (fase platform/ — CLAUDE.md §10). Daqui saem:
o gancho para a frente `_mc_save_from_deal` (chamado de DENTRO do
`_pc_save_from_deal`, que fica no routes — quem decide se um deal vira
confirmação é ele), a Legal Entity derivada (`_mc_legal_entity`, §7), os
documentos da pasta da confirmação (`_mc_confirmation_docs` + o E-mail Subject
que se escreve sozinho), quem assina cada etapa (`_MC_STAGE_ROLE`,
`_mc_can_validate` — Master é a única exceção), o destino dos avisos do sino
(`_MC_STAGE_NOTIFY_ROLES`), o Generate do Monitor (`_mc_generate_url`) e o
espelho no Pending Confirmation (`_mc_pc_sync`).

Dois imports diretos de propósito: o `manual_conf` (`_mc_mod` — módulo
próprio, sem ciclo) e os oito nomes de `platform.confirmations` que o
`_MC_GENERATE_PRODUCTS` referencia no NÍVEL DO MÓDULO — ali o alias do routes
não serve, porque este módulo é importado num ponto do `routes.py` ANTERIOR ao
bloco de alias das confirmações; são os mesmos objetos.

O resto — `_ei_*`, `_pc_*`, `_notif_roles`, `_session_is_master`, o `session`
do Flask (superfície de patch, §316) — é alcançado por import ATRASADO dentro
da função, andaime declarado.
"""
import logging
import os
import re
import threading
import time
import traceback
from datetime import datetime
from urllib.parse import quote

from apps.pages import manual_conf as _mc_mod
# Os oito nomes que _MC_GENERATE_PRODUCTS referencia no nivel do modulo: o
# alias do routes ainda nao existe quando este modulo e importado (o bloco
# das confirmacoes vem depois no routes.py) — sao os MESMOS objetos.
from apps.pages.platform.confirmations import (
    _conf_ndfcomm_groups, _conf_optcomm_groups, _conf_optfxo_groups,
    _conf_fwdstart_groups, _CONF_FAMILY_TEMPLATES, _CONF_OPT_FAMILY_TEMPLATES,
    _CONF_FXO_FAMILY_TEMPLATES, _CONF_FWDSTART_FAMILY_TEMPLATES,
)

log = logging.getLogger('otc_tracker')

# Produtos cuja operação mapeada gera CONFIRMAÇÃO, e por isso entra também na
# esteira de Manual Confirmations. NDF Vanilla e Other Publisher ficam de fora:
# eles alimentam o Pending Confirmation, mas não geram documento de confirmação.
# A chave é o `source` (ver `_pc_save_from_deal`), não o Product Type — as três
# páginas genéricas de NDF gravam com o mesmo 'NDF', e olhar o Product Type
# traria Vanilla e Other Publisher junto com o FWD Start.
_MC_CONFIRMATION_SOURCES = {'NDF COMM', 'OPTION COMM', 'OPTION', 'NDF FWD START'}


# LOB da linha espelhada. As duas telas gravavam 'CEM' para tudo, e a mesa de
# mercadorias não é a de câmbio: no cadastro Produto × LOB da esteira a LOB é
# metade da chave, e no Reference Data ela separa os produtos. Os quatro tipos de
# mercadoria (termo, opção e os unwinds deles) saem como COMMODITY; o resto segue
# CEM, que é o que sempre foi.
_COMMODITY_SOURCES = {'NDF COMM', 'OPTION COMM', 'UNWIND NDF COMM', 'UNWIND OPTION COMM'}


def _lob_for_source(source):
    return 'COMMODITY' if _mc_mod.upper_norm(source) in _COMMODITY_SOURCES else 'CEM'


# Produtos que a mesa booka SEMPRE no Banco J.P. Morgan — os que não trazem o
# campo `LE` no deal e cuja entidade não depende do Settlement Location. É a
# lista da Legal Entity, e não a de LOB: a FXO é CEM (não é mercadoria) e ainda
# assim é bookada no Banco, então usar `_COMMODITY_SOURCES` para as duas coisas
# amarraria duas perguntas diferentes na mesma resposta.
_MC_JPM_SOURCES = _COMMODITY_SOURCES | {'OPTION'}

# De onde sai a MOEDA do notional, por produto. Não é uma cadeia de fallback:
# cada produto guarda o valor num campo diferente e a resposta certa é a do
# campo daquele produto — um `first(...)` genérico pegaria o primeiro que
# estivesse preenchido, que nem sempre é o que a mesa chama de moeda do notional.
#
#   * termo e opção de MERCADORIA e opção de CÂMBIO → `StrikeCurrency`
#   * os NDF genéricos (Vanilla, Other Publisher, FWD Start) → `QuantityCurrency`
#
# Produto fora da lista cai no `QuantityCurrency`, que é o campo da maioria.
_MC_NOTIONAL_CCY_FIELD = {
    'NDF COMM':      'StrikeCurrency',
    'OPTION COMM':   'StrikeCurrency',
    'OPTION':        'StrikeCurrency',
    'NDF FWD START': 'QuantityCurrency',
}


def _mc_notional_ccy(deal, source, notional):
    """`Notional Amount CCY` da linha: 'USD 1500000'.

    O número vai CRU, como está na coluna Notional ao lado — a formatação é
    ortogonal e mora na tela. Gravar '1,500,000.00' aqui obrigaria o relatório
    do BACC a desfazer a máscara para escrever um número no Excel, e a máscara
    do Excel do consumidor é dele, não nossa.

    Sem moeda cadastrada no deal a célula sai só com o número: em branco ela
    perderia o notional junto, e o valor sem moeda ainda é o valor.
    """
    campo = _MC_NOTIONAL_CCY_FIELD.get(_mc_mod.upper_norm(source), 'QuantityCurrency')
    ccy = str(deal.get(campo, '') or '').strip().upper()
    val = str(notional or '').strip()
    if not val:
        return ''
    return (ccy + ' ' + val).strip() if len(ccy) == 3 and ccy.isalpha() else val


def _mc_legal_entity(deal, source):
    """Legal Entity da linha espelhada na esteira.

    Só as páginas genéricas de NDF trazem a entidade no deal (campo `LE`:
    JPM/MGT/LAWTON, resolvido do Settlement Location pelo mapping le-accronym).
    As de mercadoria e a de FXO **não têm o campo** — e o antigo fallback para
    `TradingBook` escrevia na coluna Legal Entity o nome do BOOK
    (`ALUM-BRAZIL-BANCO`, `BANCO_Crude_Brazil_NA`), que não é entidade nenhuma.

    Mercadoria e **FXO** são sempre **JPM**: a mesa booka termo e opção de
    commodity e a opção de câmbio no Banco J.P. Morgan, e é uma entidade só. A
    FXO ficava em BRANCO aqui, esperando que alguém cadastrasse a entidade linha
    a linha, e as confirmações de FXO que fechavam em Success no New Deals
    chegavam ao Track Confirmations sem Legal Entity nenhuma — uma coluna vazia
    que ninguém tinha como preencher, porque a resposta é sempre a mesma.

    A razão social sai do cadastro `le-spn` (LE → NAME), nunca de um literal
    aqui: é de lá que o resto do app lê a identidade da entidade, e a coluna
    guarda o nome por extenso ('BANCO J.P MORGAN S.A'), como nas linhas vindas
    da planilha. Sem NAME cadastrado sobra a sigla, que ainda é uma entidade.
    """
    from apps.pages import routes
    le = str(deal.get('LE', '') or '').strip().upper()
    if not le and _mc_mod.upper_norm(source) in _MC_JPM_SOURCES:
        le = 'JPM'
    if not le:
        return ''
    return str(routes._ndf_le_row(le).get('NAME', '') or '').strip() or le


def _mc_save_from_deal(deal, source, trade_number=None):
    """Espelha para Manual Confirmations a operação que acabou de ser mapeada.

    Chamado de dentro do `_pc_save_from_deal` de propósito: quem decide se um
    deal vira confirmação de cliente (perna interna? intragrupo?) é aquela
    função, e repetir o teste aqui criaria uma segunda resposta para a mesma
    pergunta — que é como as duas telas passariam a discordar de quem tem
    confirmação pendente.

    Nunca sobrescreve uma linha que já existe: se a esteira já andou, um novo
    mapeamento do mesmo deal (um amend, uma remapeação) não pode apagar o
    'Conferido OTC' que alguém carimbou.
    """
    from apps.pages import routes
    if source not in _MC_CONFIRMATION_SOURCES:
        return
    try:
        from apps.pages import manual_conf as _mc
        key = str(trade_number or deal.get('Deal', '') or '').strip()
        if not key or _mc.find_row(key) is not None:
            return
        td = routes._parse_date_any(deal.get('TradeDate', ''))
        md = routes._parse_date_any(deal.get('SettlementDate', ''))

        def first(*names):
            for n in names:
                v = str(deal.get(n, '') or '').strip()
                if v:
                    return v
            return ''

        _mc.upsert_row(_mc.blank_row(**{
            'Legal Entity': _mc_legal_entity(deal, source),
            'Cliente': str(deal.get('Client', '') or ''),
            'Produto': source,
            'LOB': _lob_for_source(source),
            'Trade ID': key,
            # O `Athena ID` saiu da esteira (repetia o Trade ID em quase todo
            # produto e vinha vazio no FWD Start), e por isso não é mais gravado:
            # o `blank_row` descartaria a chave em silêncio, e um campo que se
            # escreve para nada é dívida esperando alguém procurá-lo.
            'Cetip ID': first('B3_ID'),
            # O campo é o ATIVO da confirmação: nas commodities entra a
            # commodity (é ela que distingue OLEO de PLATTS no mesmo dia e
            # acha o PDF exato); no câmbio, a moeda. A cadeia evita um ramo
            # por página, que envelheceria a cada coluna nova.
            'Moeda': (first('Commodities', 'UnderlyingAsset')
                      if source in ('NDF COMM', 'OPTION COMM')
                      else first('QuantityCurrency', 'StrikeCurrency', 'PremiumCCY', 'Currency')),
            'Notional': first('Notional', 'TotalNotional'),
            'Notional Amount CCY': _mc_notional_ccy(
                deal, source, first('Notional', 'TotalNotional')),
            'Data Operação': td.strftime('%d/%m/%Y') if td else first('TradeDate'),
            'Data de vencimento': md.strftime('%d/%m/%Y') if md else first('SettlementDate'),
        }))
    except Exception:
        log.warning('[manual-conf] save-from-deal falhou:\n%s', traceback.format_exc())

def _mc_conf_trade_keys(picked, product):
    """As chaves de Manual Confirmations das operações que a confirmação cobre.

    O FWD Start é chaveado pelo **B3 ID** — é assim que a linha nasce, tanto no
    Pending Confirmation quanto aqui. Usar o Deal para todos deixaria justamente
    as linhas de FWD Start sem carimbo, e sem erro nenhum: elas simplesmente não
    seriam encontradas.
    """
    field = 'B3_ID' if product == 'ndf-fwdstart' else 'Deal'
    out = []
    for item in (picked or []):
        d = item[0] if isinstance(item, (list, tuple)) else item
        k = str((d or {}).get(field, '') or '').strip()
        if k:
            out.append(k)
    return out


def _mc_ei_link(client_key, client_dir, file_path):
    """Endereço do documento salvo no Electronic Inventory.

    O botão *Abrir* do Monitor tem de levar ao PAPEL — o PDF que foi gravado em
    `<Cliente>/Confirmations/AAAA/mm. Mês/dd/<produto>/` —, não a uma tela que o
    reconstrói. Quem valida precisa ver o que foi (ou vai ser) enviado ao
    cliente, e a tela de geração pode montar outra coisa se o day-file mudou.

    O `rel` é RELATIVO à pasta do cliente porque é assim que
    `/api/electronic-inventory/file` recebe: ele resolve a pasta pelo nome do
    cliente e barra qualquer caminho que escape dela.
    """
    if not (client_key and client_dir and file_path):
        return ''
    try:
        rel = os.path.relpath(file_path, client_dir)
    except ValueError:                       # drives diferentes no Windows
        return ''
    if rel.startswith('..'):
        return ''
    return ('/api/electronic-inventory/file?client=' + quote(str(client_key)) +
            '&rel=' + quote(rel.replace(os.sep, '/')))


def _mc_stamp_generated(picked, product, link=''):
    """Confirmação salva → Data envio validação OTC nas linhas que ela cobre."""
    try:
        from apps.pages import manual_conf as _mc
        for k in _mc_conf_trade_keys(picked, product):
            _mc.mark_generated(k, link=link)
    except Exception:
        log.warning('[manual-conf] carimbo de geração falhou:\n%s', traceback.format_exc())

def _mc_counts(rows):
    from apps.pages import manual_conf as _mc
    return {
        'total': len(rows),
        'legal': sum(1 for r in rows if r.get('Pending') == _mc.PENDING_LEGAL),
        'otc': sum(1 for r in rows if r.get('Pending') == _mc.PENDING_OTC),
        'mo': sum(1 for r in rows if r.get('Pending') in (_mc.PENDING_MO, _mc.PENDING_MOFO)),
        'fo': sum(1 for r in rows if r.get('Pending') in (_mc.PENDING_FO, _mc.PENDING_MOFO)),
        'fepweb': sum(1 for r in rows if r.get('Pending') == _mc.PENDING_FEPWEB),
        'ok': sum(1 for r in rows if r.get('Pending') == _mc.STATUS_OK),
    }


# Listagem de uma pasta do share, memorizada por caminho. O Monitor pede os
# documentos de N confirmações e cada pedido custava um `isdir` + um `listdir`
# sobre o share de rede — e agora são DUAS pastas por linha (a do tipo e a
# antiga). Como várias confirmações do mesmo cliente no mesmo dia caem na MESMA
# pasta, a maior parte dessas idas era repetida.
#
# TTL curto de propósito: a pasta do dia recebe documento enquanto a mesa
# trabalha, e um cache longo esconderia a confirmação que acabou de ser gerada.
# 60 s é mais do que o suficiente para cobrir o carregamento da tela inteira e um
# refresh em seguida, que é onde a espera aparecia.
_MC_DOCS_TTL = 60.0
_MC_DOCS_CACHE = {}
_MC_DOCS_LOCK = threading.Lock()


def _mc_folder_files(folder):
    """TODOS os nomes de arquivo de uma pasta do Electronic Inventory, em ordem.
    [] se não existe. O cache guarda a listagem inteira — PDF e e-mail saem da
    MESMA ida ao share, em vez de duas.

    Pasta inexistente também entra no cache: a pasta de nome antigo não existe
    para a maioria das linhas, e é justamente ela que dobraria o número de idas
    ao share se cada chamada tivesse de descobrir isso de novo.
    """
    from apps.pages import routes
    agora = time.time()
    with _MC_DOCS_LOCK:
        hit = _MC_DOCS_CACHE.get(folder)
        if hit and (agora - hit[0]) < _MC_DOCS_TTL:
            return hit[1]
    try:
        long_folder = routes._ei_long_path(os.path.normpath(os.path.abspath(folder)))
        nomes = (sorted(os.listdir(long_folder))
                 if os.path.isdir(long_folder) else [])
    except Exception:
        # Share fora do ar não pode virar cache: guardar [] aqui faria a tela
        # dizer "sem PDF" pelo minuto seguinte, com os arquivos lá.
        return []
    with _MC_DOCS_LOCK:
        _MC_DOCS_CACHE[folder] = (agora, nomes)
        # Poda simples: a tela toca dezenas de pastas por dia, não milhares.
        if len(_MC_DOCS_CACHE) > 500:
            for k, v in list(_MC_DOCS_CACHE.items()):
                if (agora - v[0]) >= _MC_DOCS_TTL:
                    _MC_DOCS_CACHE.pop(k, None)
    return nomes


def _mc_folder_pdfs(folder):
    """Os PDFs de uma pasta do Electronic Inventory, em ordem. [] se não existe."""
    return [n for n in _mc_folder_files(folder) if n.lower().endswith('.pdf')]


# O e-mail de recap interno que a mesa guarda na MESMA pasta do PDF. A
# identificação é pelo nome do arquivo — 'Internal Recap', 'Recap' ou
# 'Internal' —, e 'internal'/'recap' cobrem as três grafias.
_MC_MAIL_TOKENS = ('internal', 'recap')


def _mc_folder_emails(folder):
    """Os e-mails (.msg/.eml) de recap de uma pasta — nome com Internal/Recap."""
    out = []
    for n in _mc_folder_files(folder):
        nl = n.lower()
        if nl.endswith(('.msg', '.eml')) and any(tok in nl for tok in _MC_MAIL_TOKENS):
            out.append(n)
    return out


# O ASSUNTO de cada e-mail de recap, memorizado por (caminho, mtime, tamanho).
# Ler o assunto custa abrir o arquivo no share — um parser OLE/CFB no .msg —, e
# o Monitor pede a lista inteira a cada carregamento. A chave leva mtime e
# tamanho para o recap SUBSTITUÍDO ser relido: o caminho sozinho manteria o
# assunto do e-mail antigo pela vida do processo.
_MC_SUBJECT_CACHE = {}
_MC_SUBJECT_LOCK = threading.Lock()


def _mc_email_subject(full):
    """O assunto do e-mail de recap em `full`. '' quando não dá para ler.

    Falha é sempre '' e nunca exceção: o assunto é um enfeite da coluna do Track
    Confirmations, e um .msg corrompido não pode derrubar a lista de documentos
    do Monitor inteira.
    """
    from apps.pages import routes
    try:
        st = os.stat(routes._ei_long_path(os.path.normpath(os.path.abspath(full))))
        chave = (full, int(st.st_mtime), st.st_size)
    except Exception:
        return ''
    with _MC_SUBJECT_LOCK:
        if chave in _MC_SUBJECT_CACHE:
            return _MC_SUBJECT_CACHE[chave]
    assunto = ''
    try:
        # Mesmo teto do /api/parse-msg-html: o parser OLE/CFB não pode receber um
        # arquivo sem limite de tamanho.
        if st.st_size <= 25 * 1024 * 1024:
            if full.lower().endswith('.msg'):
                import extract_msg
                assunto = str(getattr(extract_msg.openMsg(full), 'subject', '') or '')
            else:
                import email as _email
                from email import policy as _policy
                with open(full, 'rb') as fh:
                    assunto = str(_email.message_from_binary_file(
                        fh, policy=_policy.default).get('Subject', '') or '')
    except Exception:
        log.warning('[manual-conf] não consegui ler o assunto de %s', full)
        assunto = ''
    assunto = re.sub(r'\s+', ' ', assunto).strip()
    with _MC_SUBJECT_LOCK:
        # Poda simples: o share tem um recap por confirmação, não milhares por dia.
        if len(_MC_SUBJECT_CACHE) > 2000:
            _MC_SUBJECT_CACHE.clear()
        _MC_SUBJECT_CACHE[chave] = assunto
    return assunto


def _mc_confirmation_docs(row, trades=None):
    """Os PDFs da confirmação daquela linha, no Electronic Inventory.

    A pasta é DERIVADA da linha (cliente × produto × data da operação) e não de
    um campo gravado: é isso que faz o botão Abrir funcionar também para as
    confirmações que já existiam antes de o carimbo passar a existir — e essas
    são justamente as que alguém precisa procurar.

    Só PDF: é o que abre em preview no navegador. O .doc baixaria, e o .xml é do
    FepWeb — nenhum dos dois é o que se confere na tela.

    A busca varre TODAS as pastas candidatas da linha: a do nome do tipo (onde o
    app grava hoje) e as de nome antigo, que continuam cheias no share.
    """
    from apps.pages import routes
    try:
        from apps.pages import manual_conf as _mc
        cliente, rels = _mc.confirmation_folders(row)
        if not cliente:
            # Sem log não há como distinguir "linha incompleta" de "pasta não
            # achada" olhando a tela — os dois viram o mesmo "no PDF".
            log.warning('[manual-conf] docs: linha sem pasta derivável — Cliente=%r Produto=%r Data=%r',
                     row.get('Cliente'), row.get('Produto'), row.get('Data Operação'))
            return []
        nomes_disco = routes._ei_client_dir_names(cliente)
        if not nomes_disco:
            log.warning('[manual-conf] docs: cliente %r não resolveu para pasta nenhuma', cliente)
            return []
        # TODAS as gêmeas de pontuação da contraparte ('S.A' e 'SA'), não só a
        # vencedora do scan: os documentos ficaram repartidos entre elas na
        # época em que o app criava a pasta sanitizada por não achar a humana.
        bases = [os.path.join(routes.ELECTRONIC_INVENTORY_ROOT, n) for n in nomes_disco]
        out, mails, vistos = [], [], set()
        for base in bases:
            for rel in rels:
                folder = os.path.join(base, *rel.split('/'))
                for name in _mc_folder_pdfs(folder):
                    # O mesmo documento pode ter sido copiado para as duas
                    # pastas na transição. Mostrar duas vezes o que se abre
                    # igual só faria a pessoa conferir duas vezes o mesmo papel.
                    if name.lower() in vistos:
                        continue
                    vistos.add(name.lower())
                    out.append({'name': os.path.splitext(name)[0],
                                'url': ('/api/electronic-inventory/file?client=' + quote(cliente) +
                                        '&rel=' + quote(rel + '/' + name))})
                # O e-mail de recap interno mora na MESMA pasta do PDF e abre em
                # preview na tela (não em download): a URL é a do endpoint que o
                # converte para HTML.
                for name in _mc_folder_emails(folder):
                    if name.lower() in vistos:
                        continue
                    vistos.add(name.lower())
                    mails.append({'name': os.path.splitext(name)[0], 'email': True,
                                  # O ASSUNTO, não o nome do arquivo: é ele que
                                  # vai para a coluna E-mail Subject do Track
                                  # Confirmations (ver `_mc_sync_email_subjects`).
                                  'subject': _mc_email_subject(os.path.join(folder, name)),
                                  'url': ('/api/manual-confirmation/email-preview?client=' + quote(cliente) +
                                          '&rel=' + quote(rel + '/' + name))})
        if not out and not mails:
            # O diagnóstico que faltava: qual caminho o servidor tentou, e se a
            # pasta do cliente sequer existe — é a diferença entre "o nome da
            # pasta não bate" e "o documento não está lá". WARNING de propósito:
            # a instância do time só imprime INFO do logger de requests; o dos
            # módulos sai a partir de WARNING, e um diagnóstico que o console
            # descarta não diagnostica nada.
            estados = ', '.join(
                '%s (%s)' % (b, 'existe' if os.path.isdir(
                    routes._ei_long_path(os.path.normpath(os.path.abspath(b)))) else 'NAO EXISTE')
                for b in bases)
            log.warning('[manual-conf] docs: nenhum PDF para %r — pasta(s) do cliente: %s; tentadas: %s',
                     cliente, estados, ' | '.join(rels))
            return []
        # A pasta do dia tem UM PDF por confirmação (MATARIPE - OLEO - … nº
        # DBH-1OJ8L5, MATARIPE - PLATTS - … nº DBH-1OJAXM), e o filtro tem de
        # escolher os do grupo.
        #
        # O **Trade ID no nome do arquivo** é o critério exato: o documento traz
        # o número da operação que ele confirma. Ele vem antes do Ativo porque a
        # linha nem sempre sabe o Ativo — as importadas da planilha legada
        # trazem a MOEDA nessa coluna (`USD`), e aí o filtro por Ativo não casa
        # com nada e a tela oferecia a pasta inteira do dia.
        #
        # O e-mail passa pelo MESMO afunilamento, mas cai para a lista inteira
        # quando nada casa: o recap costuma ser nomeado pela contraparte/data,
        # sem Trade ID, e sumir com ele por causa do filtro deixaria o item do
        # Monitor sem o e-mail que está lá.
        ids = [str(k).strip().upper() for k in (trades or []) if str(k or '').strip()]
        ativo = str(row.get('Moeda', '') or '').strip().upper()

        def _afunila(docs):
            if ids:
                proprios = [d for d in docs if any(i in d['name'].upper() for i in ids)]
                if proprios:
                    return proprios
            if ativo and len(ativo) >= 3:
                proprios = [d for d in docs if ativo in d['name'].upper()]
                if proprios:
                    return proprios
            return docs

        return _afunila(out) + _afunila(mails)
    except Exception:
        log.warning('[manual-conf] não consegui listar a pasta da confirmação:\n%s',
                    traceback.format_exc())
        return []


def _mc_sync_email_subjects(docs, trades):
    """Junta {Trade ID: assunto} a partir dos documentos achados de UMA linha.

    A coluna E-mail Subject do Track Confirmations existe para dizer por qual
    e-mail aquela confirmação foi recapitulada, e quem sabe a resposta é o
    arquivo que está na pasta — não quem digita. Aqui é o único ponto do app em
    que o e-mail é aberto, então é daqui que a coluna se atualiza.

    O casamento é em DOIS passos, e a ordem é o que separa o certo do plausível:

      1. **pelo Trade ID no NOME do arquivo**, um recap por operação. É o caso
         da mesa que salva `Internal Recap DBH-1AAA.msg` ao lado do PDF de cada
         trade, e é EXATO — a primeira versão pegava o primeiro recap da pasta e
         carimbava o mesmo assunto em todas as operações do grupo, o que dava a
         DBH-1BBB o e-mail da DBH-1AAA;
      2. **recap ÚNICO** — nenhum arquivo nomeia operação, mas só há um e-mail
         na pasta da confirmação. Aí ele é o recap daquele booking e vale para o
         grupo inteiro; é o caso do recap nomeado por contraparte/data.

    Fora disso não se escreve nada. Vários recaps sem nome de operação é uma
    escolha às cegas: a pasta é cliente × dia × produto e pode guardar duas
    confirmações (OLEO e PLATTS do mesmo dia), e `_mc_confirmation_docs` cai
    para a listagem inteira quando o funil não casa — foi assim que uma operação
    sem recap próprio recebeu o assunto do e-mail de outra. Célula vazia pede o
    dado; célula errada aponta para um e-mail que não confirma aquele trade.
    """
    ids = [str(k).strip() for k in (trades or []) if str(k or '').strip()]
    mails = [d for d in (docs or [])
             if d.get('email') and str(d.get('subject', '') or '').strip()]
    if not ids or not mails:
        return {}
    out = {}
    for k in ids:
        alvo = k.upper()
        for d in mails:
            if alvo in str(d.get('name', '')).upper():
                out[k] = str(d['subject']).strip()
                break
    if out:
        return out
    if len(mails) == 1:
        return {k: str(mails[0]['subject']).strip() for k in ids}
    log.info('[manual-conf] %d recaps na pasta e nenhum nomeia operação (%s) — '
             'E-mail Subject não foi preenchido', len(mails), ', '.join(ids[:5]))
    return {}


def _mc_sync_fepweb_ids(rows):
    """Preenche a coluna 'Nome fep' (rótulo FepWeb ID) a partir do Pending
    Confirmation, quando o Track carrega.

    A FONTE é a coluna FepWeb ID que a geração da confirmação grava nos três
    DBs do Pending Confirmation (`_conf_pc_set_fepweb`) — o elo é o do
    `_mc_pc_sync`: MC `Trade ID` = PC `Trade Number`. Derivar aqui (e não num
    segundo gravador dentro da geração) mantém UMA regra: o que aparece no
    Track é sempre o que está no Pending Confirmation, histórico incluído.

    Três coisas de custo: só consulta os DBs quando HÁ célula vazia com Trade
    ID (o caso comum, tudo preenchido, não abre banco nenhum); é uma consulta
    por DB para o lote inteiro; e grava só o que mudou (`set_fepweb_ids`).
    Melhor esforço por DB: um banco que falha (coluna ausente num arquivo
    antigo, lock) sai no log e não derruba a listagem, que é o serviço pedido.
    Atualiza `rows` em memória para a resposta desta chamada já sair
    preenchida — senão a célula só apareceria no reload seguinte.
    """
    from apps.pages import routes
    vazios = []
    for r in rows or []:
        k = str(r.get(_mc_mod.KEY_COLUMN, '') or '').strip()
        if k and not str(r.get('Nome fep', '') or '').strip():
            vazios.append(k)
    if not vazios:
        return 0
    achados = {}
    ph = ', '.join('?' for _ in vazios)
    for fname in routes._PC_DBS.values():
        path = os.path.join(routes._PC_DB_DIR, fname)
        if not os.path.isfile(path):
            continue
        try:
            with routes.duckdb_read(path) as con:
                for tn, fep in con.execute(
                        'SELECT trim("Trade Number"), trim("FepWeb ID") FROM {} '
                        "WHERE trim(\"Trade Number\") IN ({}) "
                        "AND coalesce(trim(\"FepWeb ID\"), '') <> ''"
                        .format(routes._PC_TABLE, ph), vazios).fetchall():
                    achados.setdefault(str(tn or '').strip(), str(fep or '').strip())
        except Exception:
            log.warning('[manual-conf] FepWeb ID sync falhou em %s:\n%s',
                        fname, traceback.format_exc())
    if not achados:
        return 0
    n = _mc_mod.set_fepweb_ids(achados)
    for r in rows:
        k = str(r.get(_mc_mod.KEY_COLUMN, '') or '').strip()
        if k in achados and not str(r.get('Nome fep', '') or '').strip():
            r['Nome fep'] = achados[k]
    return n


def _mc_flush_email_subjects(pares):
    """Grava os assuntos coletados, sem deixar a falha chegar à tela.

    A gravação é o EFEITO COLATERAL de listar os documentos, não o serviço que a
    página pediu: um banco travado não pode transformar o Monitor inteiro em
    'no PDF'.
    """
    if not pares:
        return
    try:
        from apps.pages import manual_conf as _mc
        n = _mc.set_email_subjects(pares)
        if n:
            log.info('[manual-conf] E-mail Subject atualizado em %d linha(s)', n)
    except Exception:
        log.warning('[manual-conf] não consegui gravar o assunto do recap:\n%s',
                    traceback.format_exc())


# ── Quem assina cada etapa da esteira ────────────────────────────────────────
# A validação é um ato da MESA, não do app: quem carimba o Pending MO está
# dizendo que o Middle Office conferiu, e o que sustenta essa assinatura é o
# papel do usuário. Uma mesa por etapa — é isso que separa as funções, e o OTC,
# que monta o documento, não pode assiná-lo pelo MO logo em seguida.
#
# 'Pending OTC' é do BACK OFFICE (papel `BO`): a etapa se chama OTC porque é a
# mesa de OTC Ops, que no cadastro de papéis é o Back Office.
_MC_STAGE_ROLE = {'OTC': 'BO', 'MO': 'MO', 'FO': 'FO'}

# ADMIN conta como BO (decisão da mesa, 31/08/2026). O `Role` do cadastro é UMA
# coluna, então quem administra acessos não podia também sentar na mesa de OTC
# Ops: a pessoa era admin e o Validate do Pending OTC simplesmente não existia
# para ela. Elevar o SID a master resolveria pela pior porta — o master escapa
# de TODA restrição e passaria a assinar pelo MO e pelo FO também.
#
# O alias é a resposta estreita: ADMIN é lido como BO, e BO assina só o Pending
# OTC. A segregação entre as três mesas continua de pé — o que caiu foi a
# separação entre administrar e ser Back Office, que é a que a mesa não quis.
#
# Ele mora aqui em cima porque decide as DUAS perguntas da esteira: quem assina
# (`_mc_session_desk`) e quem recebe o aviso (`_MC_STAGE_NOTIFY_ROLES`, logo
# abaixo). Deixar o ADMIN validar sem avisá-lo é o meio-caminho que não dá erro
# nenhum: ele poderia carimbar o Pending OTC e nunca saber que havia o que
# carimbar.
_MC_ROLE_ALIAS = {'ADMIN': 'BO'}


def _mc_session_desk():
    """A mesa da sessão, já com os apelidos de `_MC_ROLE_ALIAS` resolvidos."""
    from apps.pages import routes
    papel = (routes.session.get('user_role') or '').strip().upper()
    return _MC_ROLE_ALIAS.get(papel, papel)


def _mc_alias_de(papel):
    """Os papéis que são lidos como `papel` — ('BO',) → ('BO', 'ADMIN')."""
    return (papel,) + tuple(a for a, real in sorted(_MC_ROLE_ALIAS.items())
                            if real == papel)

# Quem RECEBE o aviso quando a confirmação cai em cada etapa. Não é a mesma
# pergunta de quem ASSINA (`_MC_STAGE_ROLE`): assinar é um ato, e é de uma mesa
# só; ver é acompanhar, e o Back Office acompanha a esteira inteira — foi ele que
# montou o documento e é para ele que o reject volta.
#
# `MASTER` entra em todas porque é o papel que `_set_session` grava para os SIDs
# de `_MASTER_SIDS` e o master escapa de toda restrição (§5). Sem ele na lista, o
# superusuário perderia a esteira de vista — e em silêncio, que é o pior jeito.
#
# `ADMIN` entra onde o `BO` entra, pelo apelido de `_MC_ROLE_ALIAS` — e pela
# mesma razão que o deixou assinar: o `Role` do cadastro é uma coluna só.
#
# As chaves são os rótulos de `manual_conf.PENDING_*`. Escritos por extenso
# porque o módulo é importado preguiçosamente (ele puxa os dois DuckDB da
# esteira) e um dict de módulo não pode esperar por isso; `check_mc_notify.py`
# prende os quatro contra as constantes, para o rótulo não poder mudar de um lado
# só — se mudasse, a etapa cairia no `else` e o aviso voltaria a ir para todos.
#
# A tabela é escrita com as MESAS, e o apelido entra por DERIVAÇÃO: escrever
# 'ADMIN' à mão nas quatro linhas que têm 'BO' faria dele um segundo cadastro da
# mesma decisão, e a etapa acrescentada amanhã sairia com a lista pela metade —
# um aviso que não chega não levanta erro nenhum.
_MC_STAGE_NOTIFY_ROLES = {etapa: sum((_mc_alias_de(p) for p in papeis), ())
                          for etapa, papeis in {
    'Pending OTC': ('BO', 'MASTER'),
    'Pending MO': ('MO', 'BO', 'MASTER'),
    'Pending FO': ('FO', 'BO', 'MASTER'),
    # As duas mesas ao mesmo tempo (elas correm em PARALELO, não em fila).
    'Pending MO/FO': ('MO', 'FO', 'BO', 'MASTER'),
    # Os estados fora das mesas (§254) são do OTC Ops: é ele quem solta o hold
    # do jurídico e quem envia o documento pelo FepWeb.
    'Pending Legal': ('BO', 'MASTER'),
    'Pending FepWeb': ('BO', 'MASTER'),
}.items()}


def _mc_notify_roles(rows):
    """Papéis que devem ser avisados por este lote de linhas já validadas.

    A etapa vem de `pending_stage(row)` — o ESTADO depois do carimbo, não a etapa
    que acabou de ser assinada. É a diferença entre "o OTC validou" (que não diz
    a quem interessa) e "isto agora está em Pending MO" (que diz).

    Um documento cobre várias operações e o cadastro de validação é por Produto ×
    LOB, então o lote pode cair em etapas diferentes: a união dos papéis é o
    certo — recortar pela primeira linha deixaria a outra mesa sem aviso.

    Confirmação que fechou (`Ok`) não tem mesa esperando: devolve '' e o aviso
    vai para todo mundo, como sempre foi. Restringir o fim da esteira esconderia
    justamente a notícia boa.
    """
    from apps.pages import routes
    from apps.pages import manual_conf as _mc
    papeis, algum_alvo = [], False
    for row in rows or []:
        try:
            etapa = _mc.pending_stage(row)
        except Exception:
            continue
        alvo = _MC_STAGE_NOTIFY_ROLES.get(etapa)
        if not alvo:
            continue
        algum_alvo = True
        papeis.extend(alvo)
    return routes._notif_roles(papeis) if algum_alvo else ''


def _mc_can_validate(stage):
    """A sessão pode validar/rejeitar esta etapa?

    Master passa (§5: é o único que escapa de toda restrição). O ADMIN passa
    pelo apelido de `_MC_ROLE_ALIAS`, que o lê como BO — e por isso assina o
    Pending OTC e **só** ele: continua sem poder carimbar pelo MO ou pelo FO,
    que é a segregação entre as três mesas.
    """
    from apps.pages import routes
    if routes._session_is_master():
        return True
    return _mc_session_desk() == _MC_STAGE_ROLE.get(str(stage or '').strip().upper())


def _mc_stage_denied(stage):
    """A recusa, na voz de quem lê: qual mesa assina esta etapa."""
    return ('Só o {} valida uma confirmação em Pending {}.'
            .format(_MC_STAGE_ROLE.get(str(stage or '').strip().upper(), '—'), stage))


# ── Gerar a confirmação a partir do Monitor ──────────────────────────────────
# A geração era um botão da barra de cada página de New Deals, e a validação um
# card do Confirmations Monitor: dois lugares para as duas metades do mesmo
# trabalho, e a mesa de OTC tinha de saber em qual das quatro páginas o documento
# nascia para depois procurá-lo no Monitor. Agora o ciclo inteiro mora no
# Monitor — o card de Pending OTC oferece **Generate** enquanto não há documento
# na pasta e **Validate** depois que há.
#
# O que este endpoint faz é a tradução que faltava: a esteira conhece a linha
# (Trade ID, Produto, data da operação) e o New Deals conhece o GRUPO
# (contraparte × mercadoria × família), que é a unidade do documento. O
# casamento é pelos Trade IDs, os mesmos que o card de Confirmations do New Deals
# Monitor já usa — casar por contraparte × mercadoria seria um de-para por texto
# entre dois cadastros que normalizam nomes de jeitos diferentes.
_MC_GENERATE_PRODUCTS = {
    'NDF COMM':      (lambda ref: _conf_ndfcomm_groups(ref),  lambda: _CONF_FAMILY_TEMPLATES),
    'OPTION COMM':   (lambda ref: _conf_optcomm_groups(ref),  lambda: _CONF_OPT_FAMILY_TEMPLATES),
    'FXO':           (lambda ref: _conf_optfxo_groups(ref),   lambda: _CONF_FXO_FAMILY_TEMPLATES),
    'NDF FWD START': (lambda ref: _conf_fwdstart_groups(ref), lambda: _CONF_FWDSTART_FAMILY_TEMPLATES),
}


def _mc_generate_url(row, keys):
    """(url, motivo) do editor da confirmação daquela linha da esteira.

    `url` vazia vem sempre com um motivo em português claro o bastante para
    virar a mensagem da tela: quem clica em Generate e cai num 404 seco não tem
    como saber se o problema é o produto, a data ou o arquivo-dia.
    """
    from apps.pages import routes
    from apps.pages import manual_conf as _mc
    tipo = _mc.confirmation_type(row.get('Produto'), row.get('LOB'))
    alvo = _MC_GENERATE_PRODUCTS.get(tipo)
    if alvo is None:
        return '', ('O produto {} não tem tela de geração no OTC Tracker — a '
                    'confirmação dele é montada fora do app.'.format(tipo or '(em branco)'))
    ref = routes._parse_date_any(row.get('Data Operação', ''))
    if not ref:
        return '', ('A linha está sem Data da Operação, e é ela que diz em que '
                    'arquivo-dia do New Deals a operação está.')
    ref = datetime(ref.year, ref.month, ref.day)
    grupos, _st, _tot = alvo[0](ref)
    templates = alvo[1]()
    # As chaves da esteira: o Trade ID da linha e as das demais operações do
    # grupo do Monitor. O FWD Start é chaveado pelo B3 ID e os demais pelo Deal —
    # o grupo do New Deals guarda os dois, então o cruzamento não precisa saber
    # qual é qual.
    procurados = {str(k).strip().upper() for k in keys if str(k or '').strip()}
    procurados.add(str(row.get('Trade ID', '') or '').strip().upper())
    procurados.discard('')
    for g in grupos:
        if not procurados & {str(t).strip().upper() for t in (g.get('trades') or ())}:
            continue
        if g['family'] not in templates:
            return '', ('A família {} ainda não tem template de documento neste '
                        'produto.'.format(g['family']))
        return (templates[g['family']][1] + '?date=' + ref.strftime('%Y-%m-%d') +
                '&acronym=' + quote(g['acronym']) +
                '&mercadoria=' + quote(g['mercadoria'])), ''
    return '', ('Nenhuma operação dessa confirmação foi encontrada no arquivo-dia '
                'de {} do New Deals. Verifique se a data da operação da linha é a '
                'mesma da importação.'.format(ref.strftime('%d/%m/%Y')))


def _mc_pc_sync(rows):
    """Espelha a etapa da esteira no Pending Status do Pending Confirmation.

    A chave é a MESMA dos dois lados — o MC `Trade ID` e o PC `Trade Number`
    nascem juntos no `_pc_save_from_deal` —, então toda gravação da esteira
    (grade, validação, reject, os botões do Monitor) atualiza a linha irmã.

    O estágio entra verbatim (Pending Legal/OTC/MO/FO/MO-FO/FepWeb). `Ok` — o
    Enviado p/ cliente preenchido — vira **Pending Digital Signature** ou
    **Pending Original** pelo Signature Type da contraparte no Reference Data
    (§254): o documento saiu e o que se espera agora é a assinatura, no meio
    que a contraparte usa.

    Falha aqui só loga: o espelho não pode derrubar a gravação da esteira — e
    linha sem irmã no PC (importada da planilha antiga) simplesmente não tem o
    que espelhar.
    """
    from apps.pages import routes
    from apps.pages import manual_conf as _mc
    alvo = {}
    for row in rows or []:
        tn = str(row.get(_mc.KEY_COLUMN, '') or '').strip()
        if tn:
            alvo[tn] = str(row.get('Pending', '') or '').strip()
    if not alvo:
        return
    try:
        vistos, updates = set(), []
        for cat in ('backlog', 'pending', 'ok'):
            for pc in routes._pc_load_rows(cat):
                tn = str(pc.get('Trade Number', '') or '').strip()
                if tn not in alvo or tn in vistos:
                    continue
                vistos.add(tn)
                pend = alvo[tn]
                if pend == _mc.STATUS_OK:
                    sig = routes._pc_norm(pc.get('Signature Type', ''))
                    if not sig:
                        rec = routes._pc_refdata_lookup({'SPN': pc.get('SPN', ''),
                                                  'Client': pc.get('Client', '')},
                                                 routes._fxo_refdata_by_spn(), routes._pc_refdata_by_name())
                        sig = routes._pc_norm((rec or {}).get('SIGNATURE TYPE', ''))
                    novo = 'Pending Digital Signature' if sig == 'digital' else 'Pending Original'
                else:
                    novo = pend
                if novo and str(pc.get('Pending Status', '') or '').strip() != novo:
                    pc['Pending Status'] = novo
                    updates.append(pc)
        if updates:                 # fora do laço de leitura: o upsert reescreve os DBs
            routes._pc_upsert_rows(updates)   # lote: 3 aberturas, não 4×N
    except Exception:
        log.warning('[manual-conf] espelho no Pending Confirmation falhou:\n%s',
                    traceback.format_exc())
