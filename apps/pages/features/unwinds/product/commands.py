# -*- coding: utf-8 -*-
"""Escritas das recompras do catalogo: importar a planilha, editar/aprovar
(4-olhos), apagar, e gerar/enviar o arquivo da B3.

O mesmo desenho da Fase 1 (`unwinds/commands.py`), dirigido pelo catalogo: a
pagina e um PARAMETRO, nunca um ramo por produto. Todo read-modify-write do
arquivo-dia roda INTEIRO sob o `_cache_lock`.
"""
import os
import random
import uuid

from apps.pages.features.unwinds import catalog
from apps.pages.features.unwinds.infra import email_file, product_store
from apps.pages.features.unwinds.product import domain, queries


def _R():
    from apps.pages import routes
    return routes


FILE_ENCODING = 'utf-8'      # os tres layouts sao ASCII puro (digitos e ids)


def _hoje():
    return _R()._br_now().date()


def _agora():
    return _R()._br_now().strftime('%Y-%m-%d %H:%M')


def _rand10():
    return str(random.randint(1000000000, 9999999999))


# ── O que chegou no dropzone ─────────────────────────────────────────────────

_OLE2 = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'


def _e_email(dados):
    """O arquivo e um E-MAIL (e nao uma planilha)? Pelo CONTEUDO, nunca pela
    extensao: `.msg` e `.xls` sao os dois Compound File (mesmo magic) e so se
    separam pelos fluxos de dentro — o `.msg` tem os `__substg1.0_`, o `.xls` o
    `Workbook`/`Book`. O `.eml` e o cabecalho MIME no topo."""
    if dados[:8] == _OLE2:
        return '__substg1.0_'.encode('utf-16-le') in dados
    return bool(email_file._MIME_RE.search(email_file._texto(dados[:4096])))


def _linhas_do_arquivo(page, filename, dados):
    """(linhas da planilha, avisos, formato) — ou Recusa com o motivo."""
    if not dados:
        raise domain.Recusa('unwind_file_empty', 'The file is empty')
    if len(dados) > email_file.MAX_BYTES:
        raise domain.Recusa('unwind_file_too_large', 'File too large')
    if _e_email(dados):
        raise domain.Recusa(
            'unwind_email_format_pending',
            'The unwind e-mail of %s has no known format yet (there is no sample): import the '
            'spreadsheet with the grid columns instead' % page['label'], produto=page['label'])
    try:
        rows, fmt = _R()._latam_read_rows(dados)
    except RuntimeError as exc:                         # .xls sem o xlrd: diz o que instalar
        raise domain.Recusa('unwind_sheet_unreadable', str(exc), motivo=str(exc))
    except Exception as exc:                            # noqa: BLE001
        raise domain.Recusa('unwind_sheet_unreadable', 'Could not read %s: %s: %s'
                            % (filename, type(exc).__name__, exc),
                            motivo='%s: %s' % (type(exc).__name__, exc))
    try:
        linhas, avisos = domain.linhas_da_planilha(rows, page)
    except domain.Recusa:
        if fmt == 'html':
            # Um corpo de e-mail salvo como .htm cai aqui (tabela sem as colunas
            # da pagina): e o e-mail, e o formato dele ainda nao existe.
            raise domain.Recusa('unwind_email_format_pending',
                                'The unwind e-mail of %s has no known format yet'
                                % page['label'], produto=page['label'])
        raise
    return linhas, avisos, fmt


# ── Import ───────────────────────────────────────────────────────────────────

def _completar_linha(page, linha, posicoes, ref_iso):
    """A linha da planilha -> a linha da tela: datas padrao, posicao, DU,
    direcao e o veredito. Devolve os avisos DESTA linha."""
    avisos = []
    campos = catalog.fields(page)
    if 'UnwindDate' in campos and not linha.get('UnwindDate'):
        linha['UnwindDate'] = ref_iso
    if 'SettlementDate' in campos and not linha.get('SettlementDate'):
        linha['SettlementDate'] = linha.get('UnwindDate') or ref_iso
    if page.get('position'):
        pos = None
        if linha.get('Contract'):
            pos = domain.posicao_pelo_contrato(linha['Contract'], posicoes)
            if pos is None:
                avisos.append(domain.aviso('unwind_position_not_found',
                                           'B3 ID %s is not in the Live Position'
                                           % linha['Contract'], contrato=str(linha['Contract'])))
        else:
            pos, av = domain.casar_por_caracteristicas(linha, posicoes)
            avisos.append(av)
        if pos is not None:
            linha['PositionFound'] = True
            avisos.extend(domain.completar(linha, pos, page))
            if page['dir'].startswith('Swap/') and pos.get('lob') and \
                    domain.norm(pos['lob']) != domain.norm(page['product']):
                avisos.append(domain.aviso(
                    'unwind_lob_differs_from_page',
                    'The Live Position says LOB %s, this is the %s page' % (pos['lob'], page['label']),
                    lob=pos['lob'], pagina=page['label']))
    if 'DU' in campos and linha.get('DU') in (None, '') and linha.get('MaturityDate'):
        du = queries.dias_uteis(linha.get('SettlementDate') or linha.get('UnwindDate'),
                                linha['MaturityDate'])
        if du is not None:
            linha['DU'] = du
    if 'Direction' in campos and not linha.get('Direction'):
        linha['Direction'] = domain.direcao_do_resultado(linha)
    veredito, av_ck = domain.conferir(linha, page)
    linha['Check'] = veredito
    avisos.extend(av_ck)
    linha['Warnings'] = domain.codigos(avisos)
    return avisos


def importar(page, filename, dados, ref, dry_run=False):
    """A planilha do dropzone -> as linhas do dia `ref` (um `date`).

    `dry_run` so le e responde as DUPLICATAS (a chave natural ja no dia): e a
    pergunta do primeiro passo do Import, e nada e gravado. Sem ele, o upsert
    pela chave natural: a linha que ja estava mantem o `_id` e o Nº de controle
    (reemitir um numero para uma antecipacao ja enviada faria a B3 ver duas), e
    volta a `Imported` — dado novo da planilha e maquina, nao conferencia.
    Linha ja ENVIADA nao se sobrescreve: fica como esta, avisando."""
    linhas, avisos, _fmt = _linhas_do_arquivo(page, filename, dados)
    if not linhas:
        raise domain.Recusa('unwind_sheet_empty', 'The spreadsheet has no data rows')
    ref_iso = ref.strftime('%Y-%m-%d')
    posicoes, fonte = ([], '')
    if page.get('position'):
        posicoes, fonte = queries.posicoes(page, ref)
    for linha in linhas:
        n = linha.pop('_sheet_row', None)
        for a in _completar_linha(page, linha, posicoes, ref_iso):
            if n is not None:
                a.setdefault('params', {}).setdefault('linha', n)
            avisos.append(a)
        linha.update({catalog.KEY_FIELD: uuid.uuid4().hex[:12], 'Status': domain.STATUS_NOVO,
                      'MyNumber': _rand10(), 'ImportedAt': _agora(), 'PositionDate': fonte,
                      'SourceFile': os.path.basename(str(filename or ''))})
    fp = product_store.day_path(page, ref)
    if dry_run:
        existentes = {domain.chave_natural(e) for e in product_store.read_day(fp)}
        existentes.discard(None)
        dup = [l for l in linhas if domain.chave_natural(l) in existentes]
        return {'rows': linhas, 'warnings': avisos,
                'duplicates': [{'Contract': l.get('Contract') or '', 'DealID': l.get('DealID') or '',
                                'UnwindDate': l.get('UnwindDate') or ''} for l in dup],
                'source_date': fonte}
    gravadas, puladas = [], []
    with _R()._cache_lock:
        dia = product_store.read_day(fp)
        for linha in linhas:
            chave = domain.chave_natural(linha)
            idx = next((i for i, e in enumerate(dia)
                        if chave is not None and domain.chave_natural(e) == chave), None)
            if idx is not None and dia[idx].get('Status') == domain.STATUS_ENVIADO:
                puladas.append(linha)
                avisos.append(domain.aviso('unwind_already_sent',
                                           'Row %s was already sent to B3 and was kept'
                                           % (linha.get('Contract') or linha.get('DealID') or ''),
                                           contrato=str(linha.get('Contract') or '')))
                continue
            if idx is not None:
                for k in (catalog.KEY_FIELD, 'MyNumber'):
                    if dia[idx].get(k):
                        linha[k] = dia[idx][k]
                dia[idx] = linha
            else:
                dia.append(linha)
            gravadas.append(linha)
        if gravadas:
            product_store.save(fp, dia)
    _R().log.info('[UNWIND %s] %d linha(s) importada(s), %d ja enviada(s) mantida(s) -> %s',
                  page['label'], len(gravadas), len(puladas), fp)
    return {'rows': gravadas, 'warnings': avisos, 'skipped': len(puladas),
            'source_date': fonte}


# ── Edicao, 4-olhos, delete ──────────────────────────────────────────────────

def editar(page, row_id, date_str, fields, sid=''):
    """Edicao -> `Pending`, com o editor como MAKER (o 4-olhos da Fase 1). O
    veredito e REFEITO com os valores novos: um Check `OK` que sobrevivesse a
    uma edicao afirmaria uma conferencia que ninguem fez. None se a linha nao
    existe; Recusa se ja foi enviada ou se um valor nao se le no tipo da coluna."""
    kinds = catalog.column_kinds(page)
    with _R()._cache_lock:
        fp, lst, idx = queries.find(page, row_id, date_str)
        if idx is None:
            return None
        linha = lst[idx]
        if linha.get('Status') == domain.STATUS_ENVIADO:
            raise domain.Recusa('unwind_already_sent', 'This unwind was already sent to B3', 409)
        for k, v in (fields or {}).items():
            if k not in kinds or k in domain.NAO_EDITAVEL:
                continue
            val, erro = domain.valor_da_celula(v, kinds[k])
            if erro:
                raise domain.Recusa('unwind_bad_value', '%s: %r is not a valid %s'
                                    % (k, v, kinds[k]), campo=k, valor=str(v))
            linha[k] = val
        veredito, avisos = domain.conferir(linha, page)
        linha['Check'] = veredito
        linha['Warnings'] = domain.codigos(avisos)
        linha['Status'] = domain.STATUS_PENDENTE
        linha['Maker'] = sid or ''
        linha['Checker'] = ''
        product_store.save(fp, lst)
        return dict(linha)


def aprovar(page, row_id, date_str, sid=''):
    """`Pending` -> `Approved`, com maker != checker (o proprio e 403)."""
    with _R()._cache_lock:
        fp, lst, idx = queries.find(page, row_id, date_str)
        if idx is None:
            return None
        linha = lst[idx]
        if linha.get('Status') != domain.STATUS_PENDENTE:
            raise domain.Recusa('unwind_only_pending', 'Only Pending unwinds can be approved')
        if linha.get('Maker') and linha['Maker'] == (sid or ''):
            raise domain.Recusa('unwind_maker_is_checker',
                                'Maker cannot approve their own change', 403)
        linha['Status'] = domain.STATUS_APROVADO
        linha['Checker'] = sid or ''
        product_store.save(fp, lst)
        return dict(linha)


def apagar(page, row_id, date_str):
    """Tira a linha do arquivo-dia. Linha ja ENVIADA nao se apaga (o arquivo ja
    foi a B3; sumir com o rastro esconde o que precisa de cancelamento)."""
    with _R()._cache_lock:
        fp, lst, idx = queries.find(page, row_id, date_str)
        if idx is None:
            return None
        if lst[idx].get('Status') == domain.STATUS_ENVIADO:
            raise domain.Recusa('unwind_already_sent', 'This unwind was already sent to B3', 409)
        apagada = lst.pop(idx)
        product_store.save(fp, lst)
    return apagada


# ── O arquivo da B3 ──────────────────────────────────────────────────────────

def _layout(page):
    if not page.get('b3'):
        raise domain.Recusa('unwind_no_b3_file',
                            '%s has no B3 file: the product is not anticipated through a B3 '
                            'layout' % page['label'], 422, produto=page['label'])
    return page['b3']['layout']


def _largura_do_bloco(key, bloco):
    for b in queries.template_blocks(key):
        if b.get('id') == bloco:
            return sum(domain.fase1.largura(str(f.get('format') or '').upper()) or 0
                       for f in b.get('fields') or [])
    return None


def _campos_do_preview(key, por_bloco):
    """[{seq, block, field, format, position, source, value}] na ordem do
    template, so dos blocos que o arquivo leva — rotulo e origem do CADASTRO,
    valor do gerador (ou o `Fixed` do cadastro, que vence)."""
    rows = []
    for b in queries.template_blocks(key):
        vals = por_bloco.get(b.get('id'))
        if vals is None:
            continue
        for f in b.get('fields') or []:
            seq = str(f.get('seq', '')).strip()
            fixo = str(f.get('source', '')) == 'Fixed'
            rows.append({'seq': seq, 'block': b.get('title', ''),
                         'field': f.get('field', ''), 'format': f.get('format', ''),
                         'position': f.get('position', ''), 'source': f.get('source', ''),
                         'value': f.get('source_detail', '') if fixo else vals.get(seq, '')})
    return rows


def arquivo(page, linha, hoje_ymd=None):
    """O arquivo da B3 de UMA recompra: {kind, key, view, file_name, header,
    records, fields}. Lacuna levanta Recusa DIZENDO quais — e o que o Send
    recusaria."""
    key = _layout(page)
    gerar, bloco_reg = domain.GERADORES[key]
    R = _R()
    conta = str(linha.get('PartyAccount') or '').strip()
    # A visao (quem lanca) sai da CONTA pelo `b3-accounts`, nunca de um de-para
    # aqui. Sem conta nenhuma (a linha nao achou a posicao) a recusa e a LISTA
    # do que falta; conta que existe e nao e nossa recusa sozinha — o arquivo
    # iria para a B3 na visao de ninguem.
    visao = R._b3_account_le(conta) if conta else ''
    if conta and not visao:
        raise domain.Recusa('unwind_account_not_registered',
                            'B3 Accounts: account %r is not registered — the party of an unwind '
                            'has to be one of ours; register it at /mapping > B3 Accounts'
                            % conta, 422, conta=conta)
    participante = R._b3_participant_name(visao) if visao else ''
    if visao and not participante:
        raise domain.Recusa('unwind_no_participant_name',
                            'B3 Accounts: no Simplified Name registered for %s' % visao, 422,
                            visao=visao)
    hoje = hoje_ymd or _hoje().strftime('%Y%m%d')
    blocos, faltas = gerar(linha, participante, hoje)
    if not conta:
        faltas.insert(0, 'our account (the row has no Live Position contract)')
    if faltas:
        raise domain.Recusa('unwind_b3_missing', 'missing: ' + '; '.join(faltas), 422,
                            campos='; '.join(faltas))
    header = R._fi_build_line(key, 'header', blocos['header'], page_url=page['path'])
    record = R._fi_build_line(key, bloco_reg, blocos[bloco_reg], page_url=page['path'])
    # Posicional: a linha tem de ter a largura que o TEMPLATE soma — largura que
    # discorde desloca todos os campos seguintes sem mudar nada que se veja.
    if page['b3']['layout'] != 'antecipacao-opcao':
        largura = _largura_do_bloco(key, bloco_reg)
        if largura and len(record) != largura:
            raise domain.Recusa('unwind_b3_length',
                                'the %s record has %d characters, the template wants %d'
                                % (page['b3']['label'], len(record), largura), 500,
                                tem=len(record), quer=largura)
    return {'kind': key, 'key': key, 'view': visao,
            'file_name': domain.nome_do_arquivo(page, visao),
            'header': header, 'records': [record],
            'fields': _campos_do_preview(key, blocos)}


def preview(page, row_id, date_str):
    fp, lst, idx = queries.find(page, row_id, date_str)
    if idx is None:
        raise domain.Recusa('unwind_not_found', 'Entry not found', 404)
    return [arquivo(page, lst[idx])]


def enviar(page, items, sid='', download=False, date_str=''):
    """Gera o arquivo das recompras selecionadas no `CONECTA_NEW_PATH` (ou
    devolve o conteudo com `download`) e vira `Sent`. Uma linha com lacuna, ou
    fora de `Imported`/`Approved`, recusa o LOTE inteiro: nada vai pela metade."""
    _layout(page)
    problemas, alvos, grupos = [], [], {}
    hoje = _hoje().strftime('%Y%m%d')
    for it in items or []:
        rid = str((it or {}).get('id') or '').strip()
        if not rid:
            continue
        fp, lst, idx = queries.find(page, rid, str((it or {}).get('date') or date_str))
        if idx is None:
            problemas.append(rid + ': not found')
            continue
        linha = lst[idx]
        st = linha.get('Status') or domain.STATUS_NOVO
        if st not in domain.STATUS_ENVIAVEL:
            problemas.append('%s: status %s' % (linha.get('Contract') or rid, st))
            continue
        try:
            f = arquivo(page, linha, hoje)
        except domain.Recusa as exc:
            problemas.append('%s: %s' % (linha.get('Contract') or rid, exc.text))
            continue
        g = grupos.setdefault(f['file_name'], {'header': f['header'], 'records': [], 'count': 0})
        g['records'].extend(f['records'])
        g['count'] += 1
        alvos.append((fp, rid))
    if problemas:
        raise domain.Recusa('unwind_nothing_sent', 'Nothing sent — ' + '; '.join(problemas),
                            motivos='; '.join(problemas))
    if not grupos:
        raise domain.Recusa('unwind_no_rows', 'No valid rows provided')
    total = sum(g['count'] for g in grupos.values())
    if download:
        return {'files': [{'filename': n, 'count': g['count'],
                           'content': '\n'.join([g['header']] + g['records'])}
                          for n, g in grupos.items()], 'count': total}
    out_dir = _R().CONECTA_NEW_PATH
    os.makedirs(out_dir, exist_ok=True)
    gerados = []
    for nome, g in grupos.items():
        destino = _R()._unique_filepath(out_dir, nome)
        with open(destino, 'w', encoding=FILE_ENCODING) as fh:
            fh.write('\n'.join([g['header']] + g['records']))
        gerados.append({'filename': os.path.basename(destino), 'count': g['count']})
        _R().log.info('[UNWIND %s] Wrote %s (%d record(s))', page['label'], destino,
                      len(g['records']))
    _marcar_enviadas(page, alvos, sid, [g['filename'] for g in gerados])
    return {'files': gerados, 'count': total}


def _marcar_enviadas(page, alvos, sid, nomes):
    por_arquivo = {}
    for fp, rid in alvos:
        por_arquivo.setdefault(fp, set()).add(rid)
    quando = _agora()
    with _R()._cache_lock:
        for fp, ids in por_arquivo.items():
            lst = product_store.read_day(fp)
            for e in lst:
                if isinstance(e, dict) and str(e.get(catalog.KEY_FIELD) or '') in ids:
                    e['Status'] = domain.STATUS_ENVIADO
                    e['SentFiles'] = list(nomes)
                    e['SentAt'] = quando
                    e['Maker'] = sid or e.get('Maker') or ''
            product_store.save(fp, lst)
