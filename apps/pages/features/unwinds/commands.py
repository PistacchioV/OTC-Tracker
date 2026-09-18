# -*- coding: utf-8 -*-
"""Escritas da recompra de NDF de moeda: importar o e-mail do Athena, montar a
linha da tela com a posicao e gerar o arquivo da B3 (TER 0014)."""
import os
import random
import threading
import time
import traceback
from datetime import datetime

from apps.pages import data_store as _store
from apps.pages.features.unwinds import domain, queries
from apps.pages.features.unwinds.infra import email_file, notification_html, persistence


def _R():
    from apps.pages import routes
    return routes


TER_FI_KEY = 'antecipacao-termo-multiclasses'
PAGE_URL = '/unwinds/ndf/fx'
PAGE = 'Unwind NDF FX'            # o rotulo `page` das notificacoes (§8)

# Quem aparece no sino quando foi a MAQUINA que importou — o mesmo 'BOX' do
# scan de New Deals, escrito aqui porque feature nao importa feature. Nao vai
# para o `Maker` da linha: ali se registra quem ENVIOU para a B3, e enviar
# continua sendo da mesa.
BOX_MAKER_SID = 'BOX'

# O nome do arquivo por VISAO (a entidade que lanca). A visao sai da conta da
# parte pelo cadastro `b3-accounts` — nao ha par de pernas a adivinhar, porque
# a recompra e de operacao ja registrada e a conta veio da posicao.
FILE_NAMES = {'JPM': 'UNWIND_BANCO.txt', 'LAWTON': 'UNWIND_LAWTON.txt',
              'ATACAMA': 'UNWIND_ATACAMA.txt', 'MGT': 'UNWIND_MGT.txt'}
FILE_NAME_DEFAULT = 'UNWIND_BANCO.txt'

# Como os demais arquivos TER desta casa (o TAXA_ do Other Publisher e o
# FWDSTART_/VANILLA_ do New Deals): utf-8 e `\n`. O layout e ASCII puro —
# digitos, letras e espacos —, entao nao ha o byte duplo que obrigou o Swap
# Bullet ao cp1252 (§480).
FILE_ENCODING = 'utf-8'


def _rand10():
    return str(random.randint(1000000000, 9999999999))


def _hoje():
    return _R()._br_now().date()


# ── Import ───────────────────────────────────────────────────────────────────

def import_email(html, subject='', ref_dt=None, dry_run=False):
    """O corpo HTML de UM `BRL NDF Unwind Notification` -> a linha da recompra.

    Devolve `{'rows': [...], 'warnings': [...], 'source_date': iso}`. A
    posicao e lida UMA vez por import, e e dela que saem contrato, contas,
    moeda, lado e contraparte — a recompra e de operacao ja registrada.

    `dry_run` so parseia: e o primeiro passo do Import das paginas desta casa
    (a tela confere as duplicatas e pergunta se substitui)."""
    ref = ref_dt or _hoje()
    tabelas = notification_html.tables(html or '')
    if not tabelas:
        raise ValueError('No table found in the e-mail body')
    rec = domain.parse_notification(tabelas, subject or '')
    if not rec.get('athena_id'):
        raise ValueError('The e-mail carries no Athena ID')
    linhas, src = queries.position_rows(ref)
    contrato, posicao = domain.contrato_por_identificador(linhas, rec['athena_id'])
    linha, avisos = domain.linha_da_recompra(rec, posicao, ref, contrato)
    linha['MyNumber'] = _rand10()
    linha['ImportedAt'] = _R()._br_now().strftime('%Y-%m-%d %H:%M')
    linha['PositionDate'] = src
    if not dry_run:
        persistence.upsert(datetime(ref.year, ref.month, ref.day), [linha])
    return {'rows': [linha], 'warnings': avisos, 'source_date': src}


def import_email_upload(filename, data, ref_dt=None, dry_run=False):
    """O arquivo do dropzone: `.msg`, `.eml` ou o corpo salvo como `.htm`.

    Quem decide o formato e o CONTEUDO (`infra.email_file`), nao a extensao —
    o mesmo que as paginas de New Deals fazem, e por isso elas nunca pediram
    que se salvasse o e-mail antes.

    O assunto sai do proprio arquivo quando ele o carrega (`.msg` e `.eml`);
    so o corpo solto cai para o NOME do arquivo, que e onde o Outlook poe o
    assunto ao salvar — e e de la que saem os dois identificadores."""
    nome = str(filename or '')
    texto, assunto = email_file.ler(nome, data)
    if not assunto:
        assunto = os.path.splitext(os.path.basename(nome))[0]
    return import_email(texto, assunto, ref_dt=ref_dt, dry_run=dry_run)


def scan_box(ref_dt=None):
    """Roda a varredura do box AGORA (o automatico e de 30 em 30 minutos) e
    importa o que achar, arquivando cada e-mail na pasta Unwind depois de
    gravar a linha. So no Windows, onde ha Outlook.

    O arquivamento vem DEPOIS da gravacao de proposito: e-mail movido com a
    linha nao gravada e uma recompra que ninguem mais acha."""
    from apps.pages import otc_boxscan
    ref = ref_dt or _hoje()
    resultado = otc_boxscan.scan_unwind_box('ndf') or {}
    achados = resultado.get('emails') or []
    rows, avisos, falhas = [], [], []
    for item in achados:
        try:
            out = import_email(item.get('html') or '', item.get('subject') or '', ref_dt=ref)
        except ValueError as exc:
            falhas.append({'subject': item.get('subject') or '', 'reason': str(exc)})
            continue
        rows.extend(out['rows'])
        avisos.extend(out['warnings'])
        try:
            otc_boxscan.archive_unwind_email(item.get('entry_id') or '')
        except Exception as exc:                            # noqa: BLE001
            avisos.append({'code': 'unwind_archive_failed',
                           'params': {'subject': item.get('subject') or ''},
                           'text': 'Imported, but the e-mail could not be archived: %s' % exc})
    return {'rows': rows, 'warnings': avisos, 'failed': falhas,
            'scanned': len(achados)}


# ── O laco dos 30 minutos ────────────────────────────────────────────────────
# A varredura tambem roda sozinha, como a do booking recap de NDF Comm e Opt
# Comm — a tela sempre prometeu isso ("also runs on its own every 30 minutes")
# e nao havia laco nenhum registrado: a recompra so entrava no clique do
# Import. Nada quebrava; ela simplesmente ficava no Outlook ate alguem abrir a
# pagina.
#
# E laco PROPRIO, e nao uma parada dentro do `features/boxscan`: nesta casa
# feature nao importa feature (nenhuma das 49 importa, e o `check_soc_layers` e
# quem segura). O que as duas compartilham de verdade e o INTERVALO — a mesma
# `BOX_SCAN_POLL_MIN` —, para a mesa ter um botao so para "a varredura do box".
POLL_MIN = int(os.getenv('BOX_SCAN_POLL_MIN', '30') or 30)

_scheduler_started = False
_scheduler_lock = threading.Lock()


def scheduler_loop():
    """Uma varredura a cada `POLL_MIN` minutos, dentro da janela da mesa.

    O `_app_context` e obrigatorio: a thread do scheduler nao tem um, e o
    caminho do import passa pelo Live Position e pelo armazem (§8). O erro
    REPETIDO sai uma vez so — sem Outlook (a dev e macOS) seriam 48 linhas por
    dia dizendo a mesma coisa, e e ai que o log para de ser lido.
    """
    from apps.pages import data_store
    ultimo = ''
    while True:
        time.sleep(max(60, POLL_MIN * 60))
        R = _R()
        if not R._import_window_open():
            continue                    # fora do horario da mesa
        try:
            with R._app_context():
                out = scan_box()
            ultimo = ''
            _avisar_varredura(out)
        except data_store.BancoOcupado as exc:
            # E um IOError, e cairia no EnvironmentError abaixo como "sem
            # Outlook", em INFO: e a instancia vizinha gravando (§434).
            R.log.warning('[unwind-boxscan] banco ocupado, fica para a proxima '
                          'volta (%s)', exc)
        except EnvironmentError as exc:
            # Sem Outlook (host nao-Windows): estado esperado, nao e falha.
            if ultimo != str(exc):
                R.log.info('[unwind-boxscan] indisponivel: %s', exc)
            ultimo = str(exc)
        except Exception as exc:                            # noqa: BLE001
            if ultimo != str(exc):
                R.log.warning('[unwind-boxscan] varredura falhou: %s\n%s',
                              exc, traceback.format_exc())
            else:
                R.log.debug('[unwind-boxscan] varredura falhou de novo: %s', exc)
            ultimo = str(exc)


def _avisar_varredura(out):
    """O sino e o log do que a varredura automatica trouxe.

    So avisa quando ENTROU alguma coisa: o laco roda o dia inteiro e a caixa
    esta vazia quase sempre. E-mail que o parser recusou vai para o log em
    WARNING mesmo sem linha nenhuma — ele ficou no box, e alguem precisa saber
    por que.
    """
    R = _R()
    rows = (out or {}).get('rows') or []
    falhas = (out or {}).get('failed') or []
    for f in falhas:
        R.log.warning('[unwind-boxscan] %r nao entrou (e-mail mantido no box): %s',
                      f.get('subject') or '', f.get('reason') or '')
    if not rows:
        return
    R.log.info('[unwind-boxscan] %d e-mail(s) · %d recompra(s) importada(s) · '
               '%d recusada(s)', (out or {}).get('scanned') or 0, len(rows), len(falhas))
    R._create_notification(BOX_MAKER_SID, 'Box Scan', 'Imported', PAGE,
                           'Outlook box: %d unwind%s' % (len(rows),
                                                         '' if len(rows) == 1 else 's'))


def start_scheduler():
    """Sobe o laco UMA vez por processo. Quem o chama e o wiring do
    `routes.py` (`_schedule_on_start`), que respeita o `OTC_DISABLE_SCHEDULERS`
    dos testes — a feature nunca sobe thread no proprio import."""
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    threading.Thread(target=scheduler_loop,
                     name='unwind-box-scan-scheduler', daemon=True).start()
    R = _R()
    R.log.info('[unwind-boxscan] scheduler do box iniciado (a cada %d min · '
               'janela %s BRT · NDF FX)', POLL_MIN, R._import_window_label())


# ── O arquivo da B3 ──────────────────────────────────────────────────────────

def _visao(linha):
    """A Legal Entity que LANCA a recompra, pela conta do campo 5.

    Quem responde e o cadastro `b3-accounts` (`_b3_account_le`), nunca um
    de-para aqui: e o mesmo cadastro que ja diz a quem pertence cada conta
    na mensageria, e conta nova da mesa passa a valer sem tocar em codigo.
    Conta fora do cadastro devolve '' — e a falha desejada, porque uma conta
    que nao e nossa no campo 5 e um arquivo que a B3 recusa."""
    return _R()._b3_account_le(str((linha or {}).get('PartyAccount') or ''))


def _campos(linha):
    """Os valores nomeados do TER 0014 a partir da LINHA da tela.

    Os valores do e-mail entram CRUS (`UnwoundAmount`, `NotionalCCY`,
    `Strike`), nao o nocional ja convertido: quem divide pelo strike no fixo
    em reais e o `notional_me`, e e a MESMA conta que o import fez. Duas
    versoes da mesma divisao em lugares diferentes e como a recompra sairia
    certa na tela e errada no arquivo."""
    antes = {'Notional CCY': linha.get('NotionalCCY'),
             'Strike': linha.get('Strike')}
    depois = {'Unwound Amount': linha.get('UnwoundAmount'),
              'Termination Rate': linha.get('TerminationRate'),
              'Pre FWD Rate': linha.get('PreFWDRate')}
    # A posicao ja foi lida no import: o que ela respondeu esta na linha, e
    # reler o Live Position aqui seria outra ida ao share para chegar ao
    # mesmo lugar — e a outro, se a posicao do dia tiver mudado.
    posicao = {'Contrato': linha.get('Contract'),
               'Simbolo da Moeda': linha.get('Currency'),
               # O lado veio da POSICAO no import e esta na linha. Deriva-lo
               # da `Direction` inverteria o campo 6 sempre que o banco
               # estivesse vendido e recebendo — que e o caso da amostra.
               'Descricao da posicao do Participante':
                   '' if linha.get('Comprado') is None
                   else ('COMPRADOR' if linha.get('Comprado') else 'VENDEDOR'),
               'Valor Base no registro': linha.get('OriginalNotional'),
               'Valor Antecipado': '',
               'Codigo da Parte': linha.get('PartyAccount'),
               'Codigo da Contraparte': linha.get('CptyAccount')}
    campos, avisos = domain.campos_ter_0014(
        antes, depois, posicao, _hoje(),
        controle_interno=str(linha.get('MyNumber') or '') or _rand10())
    # Campo 11: a B3 aceita ate D+1 da antecipacao. O padrao e HOJE (a
    # decisao da mesa), e a data da linha vence quando a mesa a edita.
    liq = _R()._parse_date_any(str(linha.get('SettlementDate') or ''))
    if liq is not None:
        campos['Data Liquidação'] = liq.strftime('%Y%m%d')
    return campos, avisos


def ter_file(linha, hoje_ymd=None):
    """O arquivo da B3 de UMA recompra: `{file_name, header, records, fields}`.
    Lacuna levanta ValueError dizendo quais — e o que o Send recusaria."""
    campos, avisos = _campos(linha)
    valores, av_val = domain.valores_ter_0014(campos)
    faltas = [a['params'].get('campo') or a['code'] for a in avisos + av_val]
    if faltas:
        raise ValueError('missing: ' + '; '.join(sorted(set(str(f) for f in faltas))))
    visao = _visao(linha)
    if not visao:
        raise ValueError('B3 Accounts: account %r is not registered — the party of an '
                         'unwind has to be one of ours; register it at /mapping > B3 Accounts'
                         % str(linha.get('PartyAccount') or ''))
    participante = queries.participant_name(visao)
    if not participante:
        raise ValueError('B3 Accounts: no Simplified Name registered for %s — '
                         'register it at /mapping > B3 Accounts' % visao)
    hoje = hoje_ymd or _hoje().strftime('%Y%m%d')
    hdr = {'4': participante, '5': hoje}
    header = _R()._fi_build_line(TER_FI_KEY, 'header', hdr, page_url=PAGE_URL)
    record = _R()._fi_build_line(TER_FI_KEY, 'registro-dados-fixos', valores,
                                 page_url=PAGE_URL)
    if len(record) != domain.TER_RECORD_LENGTH:
        raise ValueError('the TER 0014 record has %d characters, the layout wants %d '
                         '(check the file-interpreter template %s)'
                         % (len(record), domain.TER_RECORD_LENGTH, TER_FI_KEY))
    return {'kind': 'ter', 'key': TER_FI_KEY, 'view': visao,
            'file_name': FILE_NAMES.get(visao, FILE_NAME_DEFAULT),
            'header': header, 'records': [record],
            'fields': _campos_do_preview({'header': hdr}, valores)}


def _campos_do_preview(por_bloco, valores):
    """[{seq, block, field, format, position, source, value}] na ordem do
    template — rotulo e origem do CADASTRO, valor do gerador."""
    rows = []
    for b in queries.template_blocks(TER_FI_KEY):
        if b.get('id') == 'registro-dados-variaveis':
            continue                    # so existe em contrato com media
        src = por_bloco.get(b.get('id'))
        if src is None:
            src = valores or {}
        for f in b.get('fields') or []:
            seq = str(f.get('seq', '')).strip()
            fixo = str(f.get('source', '')) == 'Fixed'
            rows.append({'seq': seq, 'block': b.get('title', ''),
                         'field': f.get('field', ''), 'format': f.get('format', ''),
                         'position': f.get('position', ''), 'source': f.get('source', ''),
                         'value': f.get('source_detail', '') if fixo else src.get(seq, '')})
    return rows


def preview(linha):
    return [ter_file(linha)]


def send(items, sid='', download=False, ref_date=''):
    """Gera o arquivo das recompras selecionadas no `CONECTA_NEW_PATH` (ou
    devolve o conteudo com `download`) e vira Imported -> Sent.

    Uma linha com lacuna recusa o LOTE inteiro: nada vai pela metade."""
    problemas, alvos, grupos = [], [], {}
    hoje = _hoje().strftime('%Y%m%d')
    for it in items or []:
        aid = str((it or {}).get('athena_id') or '').strip()
        if not aid:
            continue
        fp, lst, idx = queries.find(aid, str((it or {}).get('ref_date') or ref_date))
        if idx is None:
            problemas.append(aid + ': not found')
            continue
        linha = lst[idx]
        if (linha.get('Status') or domain.STATUS_NOVO) not in domain.STATUS_ENVIAVEL:
            problemas.append(aid + ': status ' + str(linha.get('Status') or domain.STATUS_NOVO))
            continue
        try:
            f = ter_file(linha, hoje)
        except ValueError as exc:
            problemas.append(aid + ': ' + str(exc))
            continue
        g = grupos.setdefault(f['file_name'], {'header': f['header'], 'records': [], 'count': 0})
        g['records'].extend(f['records'])
        g['count'] += 1
        alvos.append((aid, fp, idx))
    if problemas:
        raise ValueError('Nothing sent — ' + '; '.join(problemas))
    if not grupos:
        raise ValueError('No valid rows provided')
    gerados = []
    if download:
        for nome, g in grupos.items():
            gerados.append({'filename': nome, 'count': g['count'],
                            'content': '\n'.join([g['header']] + g['records'])})
        return {'files': gerados, 'count': sum(g['count'] for g in grupos.values())}
    out_dir = _R().CONECTA_NEW_PATH
    os.makedirs(out_dir, exist_ok=True)
    for nome, g in grupos.items():
        destino = _R()._unique_filepath(out_dir, nome)
        with open(destino, 'w', encoding=FILE_ENCODING) as fh:
            fh.write('\n'.join([g['header']] + g['records']))
        gerados.append({'filename': os.path.basename(destino), 'count': g['count']})
        _R().log.info('[UNWIND NDF FX] Wrote %s (%d record(s))', destino, len(g['records']))
    enviadas = marcar_enviadas(alvos, sid, [g['filename'] for g in gerados])
    # A recompra foi para a B3: o Termo de Resilição passa a ser devido, e é a
    # esteira que cobra. As linhas vão CARIMBADAS (`Sent`) — é esse status que a
    # segregação das confirmações lê como elegível.
    esteira_from_send(enviadas)
    # E a ponta do FUNDO, quando ele está no contrato: a Intrag é quem lança
    # por ele, e a instrução sai na planilha de onze colunas da página
    # Intrag › Unwind.
    intrag_from_send(enviadas)
    return {'files': gerados, 'count': sum(g['count'] for g in grupos.values())}


def marcar_enviadas(alvos, sid='', nomes=()):
    """Vira as linhas para `Sent`, agrupando por arquivo-dia — um
    read-modify-write por arquivo, o ciclo inteiro sob o `_cache_lock`.

    Devolve as linhas JÁ CARIMBADAS: é delas que a esteira monta o deal, e
    remontá-lo do que estava em memória antes da gravação o mandaria com o
    status velho."""
    por_arquivo = {}
    for _aid, fp, idx in alvos:
        por_arquivo.setdefault(fp, []).append(idx)
    quando = _R()._br_now().strftime('%Y-%m-%d %H:%M')
    enviadas = []
    with _R()._cache_lock:
        for fp, idxs in por_arquivo.items():
            try:
                lst = _store.read(fp)
            except Exception:                               # noqa: BLE001
                continue
            if not isinstance(lst, list):
                continue
            for i in idxs:
                if 0 <= i < len(lst) and isinstance(lst[i], dict):
                    lst[i]['Status'] = domain.STATUS_ENVIADO
                    lst[i]['SentFiles'] = list(nomes)
                    lst[i]['SentAt'] = quando
                    lst[i]['Maker'] = sid or lst[i].get('Maker') or ''
                    enviadas.append(dict(lst[i]))
            persistence.save(fp, lst)
    return enviadas


def editar(athena_id, ref_date='', fields=None, sid=''):
    """Edicao de linha -> `Pending`, com o editor como MAKER (4 olhos).

    O mesmo desenho das paginas de Intrag: mexer na linha nao a manda para a
    B3 sozinha — ela sai da fila de envio ate outro usuario conferir
    (`aprovar`). Devolve a linha gravada, ou None se ela nao existe.

    O ciclo inteiro (achar -> alterar -> gravar) roda sob o `_cache_lock`,
    porque e read-modify-write: `queries.find` nao trava nada, e ler fora da
    trava e gravar dentro reescreveria por cima do que entrou no meio.
    """
    alvo = str(athena_id or '').strip().upper()
    with _R()._cache_lock:
        fp, lst, idx = queries.find(alvo, ref_date)
        if idx is None:
            return None
        if (lst[idx].get('Status') or '') == domain.STATUS_ENVIADO:
            raise ValueError('This unwind was already sent to B3')
        for k, v in (fields or {}).items():
            # `k in lst[idx]` de proposito: a tela manda as colunas da grade, e
            # campo que a linha nao tem nao se INVENTA aqui.
            if k in lst[idx] and k not in domain.UNW_NAO_EDITAVEL:
                lst[idx][k] = v
        lst[idx]['Status'] = domain.STATUS_PENDENTE
        lst[idx]['Maker'] = sid or ''
        lst[idx]['Checker'] = ''
        linha = dict(lst[idx])
        persistence.save(fp, lst)
    return linha


def aprovar(athena_id, ref_date='', sid=''):
    """`Pending` -> `Approved`, com maker != checker.

    Levanta `ValueError` quando a linha nao esta `Pending` (nao ha o que
    conferir) e `PermissionError` quando quem aprova e quem editou — e a trava
    de quatro olhos, e sem ela a aprovacao nao afirma nada.
    """
    alvo = str(athena_id or '').strip().upper()
    with _R()._cache_lock:
        fp, lst, idx = queries.find(alvo, ref_date)
        if idx is None:
            return None
        if (lst[idx].get('Status') or '') != domain.STATUS_PENDENTE:
            raise ValueError('Only Pending unwinds can be approved')
        if lst[idx].get('Maker') and lst[idx]['Maker'] == (sid or ''):
            raise PermissionError('Maker cannot approve their own change — '
                                  'a different user must check it')
        lst[idx]['Status'] = domain.STATUS_APROVADO
        lst[idx]['Checker'] = sid or ''
        linha = dict(lst[idx])
        persistence.save(fp, lst)
    return linha


def delete(athena_id, ref_date=''):
    """Remove a linha do arquivo-dia. Linha ja enviada NAO se apaga: o arquivo
    ja foi para a B3 e sumir com o rastro esconde o que precisa ser corrigido
    por cancelamento."""
    fp, lst, idx = queries.find(athena_id, ref_date)
    if idx is None:
        return False
    if (lst[idx].get('Status') or '') == domain.STATUS_ENVIADO:
        raise ValueError('This unwind was already sent to B3')
    with _R()._cache_lock:
        try:
            atual = _store.read(fp)
        except Exception:                                   # noqa: BLE001
            atual = lst
        if not isinstance(atual, list):
            atual = lst
        atual = [e for e in atual if persistence.key_of(e) != str(athena_id or '').strip().upper()]
        persistence.save(fp, atual)
    return True


# ── O Termo de Resilição ─────────────────────────────────────────────────────
# O distrato da operação recomprada, no documento que a mesa redigiu
# (`confirmations/termo-resilicao-unwind.html`). Mesmo desenho dos outros
# editores de confirmação (§453): a rota pré-preenche, o painel edita, o Save
# grava Word + PDF no Electronic Inventory na pasta do TIPO.
#
# O que este documento NÃO tem, e não é esquecimento:
#   * **não há XML** — o XML das confirmações é o registro da operação no
#     FepWeb, e um distrato não é operação nova. Gerar um com `tipoOperacao`
#     inventado mandaria para o FepWeb uma operação que não existe;
#   * **não há família** — o termo é um só, para toda recompra de termo de
#     moeda. O eixo do grupo é contraparte × moeda, como em todo o resto (§457).
TERMO_TIPO = 'TERMO DE RESILICAO'          # um dos `manual_conf.CONFIRMATION_TYPES`
TERMO_TEMPLATE = 'confirmations/termo-resilicao-unwind.html'
TERMO_URL = '/confirmation/unwind/termo-resilicao'


def _termo_partea(linhas, avisos):
    """(nome, cnpj) da Parte A pela CONTA da recompra.

    A entidade que lança sai do `b3-accounts` (`_visao`), que é a mesma porta
    do arquivo da B3 — e não de um campo LE, que a recompra não tem. Entidade
    sem Parte A cadastrada (o Lawton e a Atacama não têm) sai em BRANCO e
    avisa: um default afirmaria uma entidade errada num documento que vai
    assinado para a contraparte."""
    les = {_visao(l) for l in linhas or []}
    les.discard('')
    if len(les) == 1:
        nome, cnpj = _R()._CONF_FWDSTART_PARTEA.get(next(iter(les)), ('', ''))
        if nome:
            return nome, cnpj
    if len(les) > 1:
        avisos.append('Recompras de entidades diferentes no mesmo grupo ({}) — preencha '
                      'a Parte A no painel.'.format(', '.join(sorted(les))))
    elif les:
        avisos.append('Entidade {} sem Parte A definida — preencha o nome e o CNPJ da '
                      'Parte A no painel.'.format(next(iter(les))))
    else:
        avisos.append('Conta da parte fora do cadastro B3 Accounts — preencha o nome e o '
                      'CNPJ da Parte A no painel.')
    return '', ''


def termo_conf(ref, acr, moeda, linhas, sid=''):
    """O payload do documento a partir das recompras do grupo. -> (conf, linhas).

    `ref` é um `date`/`datetime`; `linhas` são as recompras já filtradas."""
    avisos = []
    rows, av = domain.termo_rows(linhas)
    for a in av:
        avisos.append(a.get('text') or a.get('code'))
    first = linhas[0] if linhas else {}
    partea_nome, partea_cnpj = _termo_partea(linhas, avisos)

    spn = queries.spn_por_taxid(first.get('TaxID'))
    cgd_txt = _R()._conf_cgd_lookup({'SPN': spn}) if spn else ''
    if not cgd_txt:
        avisos.append('CGD não cadastrado no Reference Data — preencha a data do Contrato '
                      'no painel.')
    hoje = _hoje()
    conf = {
        'ref_date':     ref.strftime('%Y-%m-%d'),
        'acronym':      acr or queries._acr_da_linha(first),
        'mercadoria':   (moeda or str(first.get('Currency') or '')).upper(),
        'athena_ids':   [str(l.get('AthenaID') or '') for l in linhas],
        'cgd_date':     cgd_txt,
        'partea_nome':  partea_nome,
        'partea_cnpj':  partea_cnpj,
        'parteb_nome':  str(first.get('Counterparty') or '').strip(),
        'parteb_cnpj':  _R()._conf_fmt_cnpj(first.get('TaxID')),
        'data_neg':     _R()._conf_fmt_date(ref),
        # A data do Termo é a da ASSINATURA, que é hoje — a recompra se resolve
        # no dia. A data da operação original está no Anexo I, pelo contrato.
        'data_extenso': _R()._conf_date_extenso(hoje),
        'rows':         rows,
        'warnings':     avisos,
    }
    return conf, linhas


def termo_salvar(payload, sid=''):
    """Word + PDF do Termo na pasta da CONTRAPARTE do Electronic Inventory, e o
    carimbo do documento nas linhas da recompra.

    O caminho é o MESMO das confirmações de New Deals, e de propósito:
    `<Cliente>\Confirmations\AAAA\mm. Month\dd\<pasta do TIPO>`, com o
    cliente resolvido pelo `_ei_resolve_client_dir` e a pasta do produto saindo
    do `TYPE_FOLDER` (a pasta É o código do tipo). Escrito à mão aqui, ele
    voltaria a divergir do upload manual da tela no primeiro ajuste.

    O documento sai PRIMEIRO e o PDF sai DELE (§139): uma segunda transcrição
    do texto é a forma conhecida de os dois divergirem sem ninguém notar."""
    from flask import render_template

    fields = payload.get('fields') or {}
    rows = [r for r in (payload.get('rows') or []) if isinstance(r, dict)]
    if not rows:
        raise ValueError('No operations to save.')
    if not str(fields.get('partea_nome') or '').strip():
        raise ValueError('Parte A em branco — a conta da recompra não a define. Preencha o '
                         'nome (e o CNPJ) da Parte A no painel antes de salvar.')
    if not str(fields.get('cgd_date') or '').strip():
        raise ValueError('Data do CGD não cadastrada para esta contraparte. Cadastre o CGD '
                         'no Reference Data (ou preencha o campo no painel) antes de salvar.')

    acr = str(payload.get('acronym') or '').strip()
    moeda = str(payload.get('mercadoria') or '').strip().upper()
    conf = {
        'ref_date':     str(payload.get('date') or '').strip(),
        'acronym':      acr,
        'mercadoria':   moeda,
        'athena_ids':   [str(a) for a in (payload.get('athena_ids') or [])],
        'cgd_date':     str(fields.get('cgd_date') or '').strip(),
        'partea_nome':  str(fields.get('partea_nome') or '').strip(),
        'partea_cnpj':  str(fields.get('partea_cnpj') or '').strip(),
        'parteb_nome':  str(fields.get('parteb_nome') or '').strip(),
        'parteb_cnpj':  str(fields.get('parteb_cnpj') or '').strip(),
        'data_neg':     '',
        'data_extenso': str(fields.get('data_extenso') or '').strip(),
        'rows':         rows,
        'warnings':     [],
    }
    doc_html = render_template(TERMO_TEMPLATE, conf=conf, doc_only=True)
    from apps.pages.confirmation_pdfs import word_html_pdf
    pdf_bytes = word_html_pdf(doc_html)

    ref = _R()._parse_date_any(payload.get('date')) or _hoje()
    # A pasta é a da CONTRAPARTE, e sem contraparte não há pasta. O `acr` caía
    # num literal 'UNWIND' quando a posição não resolvia o cliente (é o mesmo
    # dia em que o B3 ID e a moeda saem em branco), e o `create=True` fazia
    # nascer no Electronic Inventory uma pasta chamada UNWIND, ao lado das
    # contrapartes — o documento ficava salvo, ninguém errava nada na tela, e
    # ele não estava onde a mesa procura. Recusar aqui é a falha desejada.
    cliente = conf['parteb_nome'] or acr
    if not cliente:
        raise ValueError('Counterparty unknown — the Termo is filed in the counterparty '
                         'folder of the Electronic Inventory, and this unwind has none. '
                         'Fill in Parte B in the panel (or fix the Live Position row) '
                         'before saving.')
    client_dir = _R()._ei_resolve_client_dir(cliente, create=True)
    dir_path = os.path.join(client_dir, 'Confirmations',
                            ref.strftime('%Y'), _R()._ei_month_folder(ref.strftime('%m')),
                            ref.strftime('%d'), _R()._mc_mod.TYPE_FOLDER[TERMO_TIPO])
    # O prefixo do nome é o do padrão legado (contraparte × mercadoria); sem
    # acrônimo, quem o abre é o nome da Parte B — nunca um segmento vazio, que
    # deixaria o arquivo começando por ' - '.
    prefixo = acr or cliente
    if len(rows) == 1 and str(rows[0].get('registroCetip') or '').strip():
        base = '{} - {} - TERMO DE RESILIÇÃO - {}'.format(
            prefixo, moeda, str(rows[0]['registroCetip']).strip())
    else:
        base = '{} - {} - TERMO DE RESILIÇÃO - {}'.format(prefixo, moeda, ref.strftime('%Y%m%d'))
    base = _R()._ei_sanitize(base)

    os.makedirs(_R()._ei_long_path(dir_path), exist_ok=True)
    candidate, n = base, 0
    while _store.exists(_R()._ei_long_path(os.path.join(dir_path, candidate + '.doc'))) or \
            _store.exists(_R()._ei_long_path(os.path.join(dir_path, candidate + '.pdf'))):
        n += 1
        candidate = '{} ({})'.format(base, n)
    doc_path = os.path.join(dir_path, candidate + '.doc')
    pdf_path = os.path.join(dir_path, candidate + '.pdf')
    with open(_R()._ei_long_path(doc_path), 'w', encoding='utf-8') as fh:
        fh.write(doc_html)
    with open(_R()._ei_long_path(pdf_path), 'wb') as fh:
        fh.write(pdf_bytes)
    _R().log.info('[UNWIND NDF FX] Termo de Resilição -> %s', pdf_path)

    link = _R()._mc_ei_link(cliente, client_dir, pdf_path)
    termo_carimbar(conf['athena_ids'], conf['ref_date'], doc_path, pdf_path, link, sid)
    # A confirmação saiu: carimba a Data envio validação OTC na esteira e guarda
    # o endereço do PDF — é para lá que o botão Abrir do Monitor manda. O grupo
    # é o das recompras JÁ ENVIADAS (o `pick` só considera as `Sent`): termo
    # gerado antes do Send não tem linha na esteira para carimbar, e é assim
    # mesmo — a confirmação só é devida depois de a recompra ir para a B3.
    picked = _R()._conf_pick_unwind(ref, acr, moeda, 'termo-resilicao')
    _R()._mc_stamp_generated(picked, 'unwind-termo', link=link)
    return {'files': [doc_path, pdf_path], 'pdf': pdf_path, 'link': link,
            'esteira': len(picked)}


def termo_carimbar(athena_ids, ref_date, doc_path, pdf_path, link='', sid=''):
    """Grava na linha da recompra o documento que acabou de sair — agrupando
    por arquivo-dia, um read-modify-write por arquivo sob o `_cache_lock`."""
    quando = _R()._br_now().strftime('%Y-%m-%d %H:%M')
    por_arquivo = {}
    for aid in athena_ids or []:
        fp, _lst, idx = queries.find(aid, ref_date)
        if idx is not None:
            por_arquivo.setdefault(fp, []).append(idx)
    with _R()._cache_lock:
        for fp, idxs in por_arquivo.items():
            try:
                lst = _store.read(fp)
            except Exception:                               # noqa: BLE001
                continue
            if not isinstance(lst, list):
                continue
            for i in idxs:
                if 0 <= i < len(lst) and isinstance(lst[i], dict):
                    lst[i]['TermoDoc'] = doc_path
                    lst[i]['TermoPdf'] = pdf_path
                    lst[i]['TermoLink'] = link
                    lst[i]['TermoAt'] = quando
                    lst[i]['TermoBy'] = sid or lst[i].get('TermoBy') or ''
            persistence.save(fp, lst)


# ── A recompra na esteira (Pending Confirmation + Manual Confirmations) ──────
# A recompra registrada na B3 deve ao cliente um documento — o Termo de
# Resilição —, e é a esteira que cobra isso: Pending OTC → MO → FO pelo
# cadastro `manual-conf-validation`, onde o TIPO é `TERMO DE RESILICAO`.
#
# A porta é a de sempre (`_pc_save_from_deal`, que chama o
# `_mc_save_from_deal`): quem decide se uma operação vira confirmação de
# cliente — perna interna, intragrupo — é aquela função, e responder isso aqui
# criaria uma segunda resposta para a mesma pergunta.
#
# O gatilho é o **Send**, não o import: o documento só é devido depois de a
# recompra ir para a B3. Antes disso ela ainda pode ser corrigida ou apagada, e
# uma linha na esteira por uma recompra que não aconteceu é cobrança de
# trabalho que não existe.
# O Produto da esteira é o mesmo valor que o Pending Confirmation mostra no
# Product Type — `UNWIND NDF` para a recompra de termo de moeda (decisão da
# mesa: a tela classifica por PRODUTO RECOMPRADO). O TIPO do documento é um só
# para todas as recompras, e quem traduz é o `manual_conf.confirmation_type`:
# `UNWIND …` → `TERMO DE RESILICAO`.
MC_SOURCE = 'UNWIND NDF'


def confirmation_deal(linha, ref=None):
    """A recompra no formato de DEAL que a esteira e as confirmações leem.

    `ref` é a data do ARQUIVO-DIA: é ela que vai na `Data Operação` da esteira,
    e é por ela que o Generate do Monitor encontra a recompra de volta. Pôr a
    data do contrato original ali mandaria o Monitor procurar num dia em que
    não há recompra nenhuma."""
    ref = ref or _R()._parse_date_any(linha.get('SettlementDate')) or _hoje()
    return {
        'Deal':           str(linha.get('AthenaID') or ''),
        'B3_ID':          str(linha.get('Contract') or ''),
        'Client':         str(linha.get('Counterparty') or ''),
        'Acronym':        queries._acr_da_linha(linha),
        'TaxID':          str(linha.get('TaxID') or ''),
        'SPN':            queries.spn_por_taxid(linha.get('TaxID')),
        'LE':             _visao(linha),
        # A recompra é um termo de MOEDA: o ativo da confirmação é a moeda
        # estrangeira do contrato, que é o mesmo eixo do documento (§457).
        'Currency':       str(linha.get('Currency') or ''),
        'QuantityCurrency': str(linha.get('Currency') or ''),
        'Notional':       linha.get('UnwoundNotional'),
        'TradeDate':      ref.strftime('%Y-%m-%d'),
        'SettlementDate': str(linha.get('SettlementDate') or ''),
        # `Success` é o que a segregação das confirmações chama de elegível; na
        # recompra isso é ter ido para a B3 (`Sent`). Enquanto ela está
        # `Imported` o grupo existe no Monitor e não gera documento — o mesmo
        # que acontece com um deal ainda não mapeado.
        'Status':         'Success' if str(linha.get('Status') or '') == domain.STATUS_ENVIADO else 'New',
        '_unwind':        True,
    }


def confirmation_deals(ref_dt):
    """As recompras do dia no formato das confirmações — o que a segregação
    (`platform/confirmations`) lê pelo gancho `routes._unwind_engine()`."""
    ref = _R()._parse_date_any(ref_dt) or _hoje()
    return [confirmation_deal(l, ref)
            for l in queries.entries(date_str=ref.strftime('%Y-%m-%d'))]


def esteira_from_send(linhas, ref=None):
    """Manda para o Pending Confirmation (e daí para a esteira) as recompras
    que acabaram de ir para a B3.

    Falha aqui NÃO derruba o envio: o arquivo já foi gerado, e uma exceção no
    espelho faria a tela dizer que o Send falhou depois de ele ter acontecido.
    O que se perde é recuperável pelo `backfill_manual_confirmations.py`."""
    for l in linhas or []:
        try:
            deal = confirmation_deal(l, ref)
            _R()._pc_save_from_deal(deal, MC_SOURCE, source=MC_SOURCE,
                                    trade_number=deal['Deal'])
        except Exception:                                   # noqa: BLE001
            _R().log.warning('[UNWIND NDF FX] esteira: %s ficou de fora — %s',
                             l.get('AthenaID'), traceback.format_exc())


# ── A recompra na Intrag (a visão do fundo) ──────────────────────────────────
# Quando o Lawton ou a Atacama está numa das pontas do contrato recomprado, a
# antecipação também tem de chegar à Intrag, que é quem lança pelo fundo. O
# LAYOUT é da Intrag (`intrag.domain.intrag_unwind_entry`, onze colunas iguais
# para todos os produtos); o que sai daqui são os VALORES, que é o que esta
# vertical conhece.
#
# O gatilho é o mesmo do espelho da esteira — o **Send** —, e pela mesma razão:
# antes de ir para a B3 a recompra ainda pode ser corrigida, e uma linha na
# Intrag por uma antecipação que não aconteceu é instrução errada no
# custodiante.
FUNDOS = ('LAWTON', 'ATACAMA')


def _fundo_da_recompra(linha):
    """(fundo, o fundo é a PARTE?) quando um dos dois está no contrato.

    A entidade de cada ponta sai da CONTA, pelo `b3-accounts` — o mesmo
    cadastro que decide a visão do arquivo da B3. Contrato sem fundo nenhum
    devolve (None, None), e aí não há linha da Intrag."""
    parte = _R()._b3_account_le(str((linha or {}).get('PartyAccount') or ''))
    if parte in FUNDOS:
        return parte, True
    cpty = _R()._b3_account_le(str((linha or {}).get('CptyAccount') or ''))
    if cpty in FUNDOS:
        return cpty, False
    return None, None


def intrag_from_send(linhas, ref=None):
    """Grava na Intrag as recompras que têm o fundo numa das pontas.
    -> [(entry, avisos)] das que entraram.

    Falha aqui NÃO derruba o envio: o arquivo da B3 já foi gerado."""
    ref = _R()._parse_date_any(ref) or _hoje()
    out = []
    for l in linhas or []:
        fundo, fundo_e_parte = _fundo_da_recompra(l)
        if not fundo:
            continue
        try:
            direcao = str(l.get('Direction') or '').strip().upper()
            # O Sentido é na VISÃO DO FUNDO. A `Direction` da linha é a da
            # PARTE (é o lado dela na posição que apura o sinal): com o fundo
            # na contraparte, o sentido é o INVERSO — recebemos quer dizer que
            # ele paga.
            if direcao == 'RECEIVE':
                credor = bool(fundo_e_parte)
            elif direcao == 'PAY':
                credor = not fundo_e_parte
            else:
                credor = None
            entry, avisos = _R()._intrag_engine()._save_intrag_unwind_entry(
                fundo=fundo,
                b3_id=l.get('Contract'),
                data_inicio=_R()._parse_date_any(l.get('TradeDate')),
                data_vencimento=_R()._parse_date_any(l.get('MaturityDate')),
                data_recompra=ref,
                valor_base_original=domain.numero_flex(l.get('OriginalNotional')),
                valor_base_recomprado=domain.numero_flex(l.get('UnwoundNotional')),
                total=domain.recompra_total(l),
                data_liquidacao=_R()._parse_date_any(l.get('SettlementDate')) or ref,
                # O valor que liquida é o resultado apurado, em módulo: o lado
                # de quem paga está no Sentido, e um valor negativo ali leria
                # como o contrário do que a coluna ao lado diz.
                credor=credor,
                valor_liquidacao=abs(domain.numero_flex(l.get('Result')))
                                 if domain.numero_flex(l.get('Result')) is not None else None,
                deal=str(l.get('AthenaID') or ''),
                client=str(l.get('Counterparty') or ''))
            out.append((entry, avisos))
            if avisos:
                _R().log.warning('[UNWIND NDF FX] Intrag %s: %s', l.get('AthenaID'),
                                 '; '.join(a['text'] for a in avisos))
        except Exception:                                   # noqa: BLE001
            _R().log.warning('[UNWIND NDF FX] Intrag: %s ficou de fora — %s',
                             l.get('AthenaID'), traceback.format_exc())
    return out


# ── A recompra no Settlement Summary de NDF ──────────────────────────────────
# A recompra liquida caixa como qualquer termo do dia, e a mesa vê o dia inteiro
# numa tela só. Por isso ela entra no Summary de NDF — mas **fora do e-mail em
# lote**: o aviso de liquidação sai de manhã, em lote, e a recompra chega
# durante o dia; juntar as duas mandaria ao cliente um aviso incompleto de
# manhã e um repetido à tarde. No Summary as duas aparecem juntas (é a visão do
# dia) e o IR se acerta sozinho, porque o ledger é MENSAL: a recompra da tarde
# já enxerga o que a liquidação da manhã reteve.
#
# A janela de busca não é só o dia: a B3 aceita a liquidação da antecipação até
# D+1, e a recompra fica gravada no arquivo-dia em que ENTROU. Quem manda é a
# `SettlementDate` da linha.
SETTLEMENT_LOOKBACK_DIAS = 4


def settlement_rows(ref):
    """As recompras que LIQUIDAM em `ref`, no formato das linhas do Summary.

    Só as que foram para a B3 (`Sent`): enquanto a recompra está `Imported` ela
    ainda pode mudar, e caixa previsto não é caixa.

    O SINAL segue a convenção do Summary — negativo é o banco PAGANDO —, e quem
    o diz é a `Direction` apurada (o sinal do resultado), nunca o campo do
    e-mail (§488). Recompra sem direção apurada fica de fora e vai para o log:
    somá-la com o sinal errado inverteria o caixa da contraparte."""
    from datetime import timedelta
    alvo = _R()._parse_date_any(ref) or _hoje()
    try:
        alvo = alvo.date()
    except AttributeError:
        pass
    inicio = alvo - timedelta(days=SETTLEMENT_LOOKBACK_DIAS)
    linhas = queries.entries(date_from=inicio.strftime('%Y-%m-%d'),
                             date_to=alvo.strftime('%Y-%m-%d'))
    out = []
    for l in linhas:
        if str(l.get('Status') or '') != domain.STATUS_ENVIADO:
            continue
        liq = _R()._parse_date_any(l.get('SettlementDate'))
        try:
            liq = liq.date()
        except AttributeError:
            pass
        if liq != alvo:
            continue
        resultado = domain.numero_flex(l.get('Result'))
        direcao = str(l.get('Direction') or '').strip().upper()
        if resultado is None or direcao not in ('RECEIVE', 'PAY'):
            _R().log.warning('[UNWIND NDF FX] %s fora do Summary de %s: sem resultado ou '
                             'sem direção apurada', l.get('AthenaID'), alvo)
            continue
        valor = abs(resultado) if direcao == 'RECEIVE' else -abs(resultado)
        le = _visao(l)
        out.append({
            'counterparty': str(l.get('Counterparty') or '').strip(),
            'legal': str(_R()._ndf_le_row(le).get('NAME', '') or '').strip() or le,
            'athena': str(l.get('AthenaID') or ''),
            'b3': str(l.get('Contract') or ''),
            'trade_date': _R()._conf_fmt_date(l.get('TradeDate')),
            'settle_date': _R()._conf_fmt_date(l.get('SettlementDate')),
            'notional_fc': abs(domain.numero_flex(l.get('UnwoundNotional')) or 0.0),
            'ccy': str(l.get('Currency') or ''),
            'settlement': valor,
            'tax': 0.0,
            'fixing': str(l.get('TerminationRate') or ''),
            # A marca que tira a recompra do aviso em lote — e que a tela usa
            # para dizer que esta linha não tem conferência contra a B3.
            'unwind': True,
        })
    return out
