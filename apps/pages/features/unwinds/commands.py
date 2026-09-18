# -*- coding: utf-8 -*-
"""Escritas da recompra de NDF de moeda: importar o e-mail do Athena, montar a
linha da tela com a posicao e gerar o arquivo da B3 (TER 0014)."""
import os
import random
import re
from datetime import datetime

from apps.pages import data_store as _store
from apps.pages.features.unwinds import domain, queries
from apps.pages.features.unwinds.infra import notification_html, persistence


def _R():
    from apps.pages import routes
    return routes


TER_FI_KEY = 'antecipacao-termo-multiclasses'
PAGE_URL = '/unwinds/ndf/fx'
PAGE = 'Unwind NDF FX'            # o rotulo `page` das notificacoes (§8)

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
    """O arquivo do dropzone (.htm/.html/.txt do corpo do e-mail). O assunto,
    quando o arquivo nao o carrega, vem do NOME do arquivo — e onde o Outlook
    o poe ao salvar, e e de la que saem os dois identificadores."""
    nome = str(filename or '')
    if not re.search(r'\.(html?|txt)$', nome, re.I):
        raise ValueError('Drop the e-mail body as .htm, .html or .txt')
    texto = data.decode('utf-8', 'replace') if isinstance(data, bytes) else str(data or '')
    return import_email(texto, os.path.splitext(os.path.basename(nome))[0],
                        ref_dt=ref_dt, dry_run=dry_run)


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
    marcar_enviadas(alvos, sid, [g['filename'] for g in gerados])
    return {'files': gerados, 'count': sum(g['count'] for g in grupos.values())}


def marcar_enviadas(alvos, sid='', nomes=()):
    """Vira as linhas para `Sent`, agrupando por arquivo-dia — um
    read-modify-write por arquivo, o ciclo inteiro sob o `_cache_lock`."""
    por_arquivo = {}
    for _aid, fp, idx in alvos:
        por_arquivo.setdefault(fp, []).append(idx)
    quando = _R()._br_now().strftime('%Y-%m-%d %H:%M')
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
            persistence.save(fp, lst)


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
