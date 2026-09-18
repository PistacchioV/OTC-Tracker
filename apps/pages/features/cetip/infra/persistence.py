# -*- coding: utf-8 -*-
"""Disco: os destinatários do card, as raízes de origem/destino no share, a
cópia do arquivo do dia e o JSON de posição (VCP) que a rotina alimenta.

As RAÍZES (`CETIP_SOURCE_ROOT`/`CETIP_DEST_ROOT`) ficam no `routes`: recon_fxo
e recon_cgd leem a mesma raiz de destino — são plataforma (§8: nenhum módulo
escreve a raiz à mão).
"""
import os
import traceback

from apps.pages.features.cetip import domain
from apps.pages import data_store as _store  # noqa: E402


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


_CETIP_RECIPIENTS_FILE = os.path.normpath(os.path.join(
    _R().data_dir(), 'control-panel',
    'cetip_distribution_recipients.json'))


def _load_cetip_recipients():
    try:
        d = _store.read(_CETIP_RECIPIENTS_FILE)
        if isinstance(d, dict):
            return {k: d.get(k, '') or '' for k in domain._CETIP_RECIPIENT_KEYS}
    except Exception:
        pass
    return {k: '' for k in domain._CETIP_RECIPIENT_KEYS}


def _save_cetip_recipients(rec):
    """Grava as três listas. Recebe o DICIONÁRIO inteiro, não um argumento por
    lista: com três chaves, uma assinatura posicional deixaria uma chamada de dois
    argumentos apagar a terceira em silêncio — que é justamente o que o POST
    fazia quando o payload vinha sem uma delas (ver `_cetip_merge_recipients`)."""
    os.makedirs(os.path.dirname(_CETIP_RECIPIENTS_FILE), exist_ok=True)
    _R()._atomic_write_json(
        _CETIP_RECIPIENTS_FILE,
        {k: str((rec or {}).get(k, '') or '') for k in domain._CETIP_RECIPIENT_KEYS})


def _cetip_merge_recipients(payload):
    """As listas salvas com as do payload por cima — só as chaves que VIERAM.

    Sobrescrever as três com o que o payload traz apagaria a lista de quem não
    está no corpo: o botão Run manda o que está na tela, e uma tela antiga (ou um
    POST de fora) não conhece a chave nova. Devolve (rec, mudou)."""
    rec = _load_cetip_recipients()
    mudou = False
    for k in domain._CETIP_RECIPIENT_KEYS:
        if k in (payload or {}):
            rec[k] = str(payload.get(k) or '').strip()
            mudou = True
    return rec, mudou


def _ensure_cetip_roots():
    """At server start, make sure the CETIP source/destination ROOT folders exist;
    create them if missing. Windows-only (the I:\\ paths are JPM network paths) —
    skipped elsewhere so dev machines don't create junk dirs from backslash paths."""
    if os.name != 'nt':
        return
    for root in (_R().CETIP_SOURCE_ROOT, _R().CETIP_DEST_ROOT):
        try:
            if not _store.isdir(root):
                os.makedirs(root, exist_ok=True)
                _R().log.info("[cetip] created root folder: %s", root)
        except Exception:
            _R().log.warning("[cetip] could not create root %s:\n%s", root, traceback.format_exc())


def _cetip_save_file(src_path, dest_path):
    """Replicate the Alteryx DynamicInput→DbFileOutput pass: read the raw file as
    Latin-1 (CodePage 28591) and rewrite it with CRLF line endings to the new
    location. Latin-1 is a byte-for-byte mapping, so content is preserved; only
    line endings are normalised to CRLF — matching what the KPI process expects."""
    with open(src_path, 'r', encoding='latin-1', newline='') as f:
        lines = f.read().splitlines()
    out = '\r\n'.join(lines)
    if lines:
        out += '\r\n'
    with open(dest_path, 'w', encoding='latin-1', newline='') as f:
        f.write(out)


def _cetip_update_vcp_json(src_path):
    """Refresh the existing VCP.json IN PLACE from the saved INDEXADORESSWAP_VCP
    file (';'-delimited, Latin-1). File columns: A=Qualification ID, B=Description,
    C=Additional Description, D=Level 1 Classification, E=Status (Habilitado →
    ACTIVE / Bloqueado → INACTIVE).

    Upsert by "ID da Qualificação": existing rows have their STATUS/descriptions/
    classification updated (MAKER/CHECKER preserved); new IDs are appended with
    Produto=SWAP. Rows not present in the file (e.g. the OPC entries) are left
    untouched. Best-effort — returns the path or None."""
    try:
        with open(src_path, 'r', encoding='latin-1', newline='') as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        if not lines:
            return None
        # Skip a header row if the file ships with one.
        first = [c.strip().lower() for c in lines[0].split(';')]
        if any('qualif' in c or c == 'status' or 'classif' in c or 'descri' in c for c in first):
            lines = lines[1:]

        # Load the existing table + index by Qualification ID (as string).
        current = []
        if _store.isfile(_R().VCP_JSON):
            try:
                current = _store.read(_R().VCP_JSON) or []
            except Exception:
                current = []
        by_id = {str(r.get('ID da Qualificação')): r for r in current}

        added = updated = 0
        for ln in lines:
            f = ln.split(';')
            def g(i):
                return f[i].strip() if i < len(f) else ''
            qid_raw = g(0)
            if not qid_raw:
                continue
            try:
                qid = int(''.join(ch for ch in qid_raw if ch.isdigit() or ch == '-'))
            except ValueError:
                qid = qid_raw
            st = _R()._fcst_norm(g(4))
            status = 'ACTIVE' if 'habilitad' in st else ('INACTIVE' if 'bloquead' in st else g(4))
            row = by_id.get(str(qid))
            if row is None:
                current.append({
                    'STATUS':                              status,
                    'ID da Qualificação':                  qid,
                    'Descrição da Qualificação':           g(1),
                    'Descrição Adicional da Qualificação': g(2),
                    'Classificação Nível 1':               g(3),
                    'Produto':                             'SWAP',
                    'MAKER':                               None,
                    'CHECKER':                             None,
                })
                by_id[str(qid)] = current[-1]
                added += 1
            else:
                row['STATUS'] = status
                row['Descrição da Qualificação'] = g(1)
                row['Descrição Adicional da Qualificação'] = g(2)
                row['Classificação Nível 1'] = g(3)
                updated += 1

        _R()._atomic_write_json(_R().VCP_JSON, current)
        _R().log.info("[cetip] VCP.json refreshed: %d updated, %d added (%d total)",
                 updated, added, len(current))
        return _R().VCP_JSON
    except Exception:
        _R().log.warning("[cetip] VCP.json update failed:\n%s", traceback.format_exc())
        return None


def _dominio_id(valor):
    """O `Identificador Qualificacao` como CHAVE, igual dos dois lados.

    A base veio de uma planilha e guarda o identificador como FLOAT (`14056.0`);
    o arquivo da B3 e texto (`14056`). Comparados como vieram, `'14056.0'` nunca
    e `'14056'`: NADA casaria, e cada rodada acrescentaria a tabela inteira de
    novo — 4 mil linhas duplicadas por dia, sem erro nenhum.
    """
    txt = str(valor if valor is not None else '').strip()
    if not txt:
        return ''
    try:
        f = float(txt.replace(',', '.'))
    except ValueError:
        return txt.upper()
    return str(int(f)) if f == int(f) else str(f)


def _dominio_key(grupo, subgrupo, tipoif, ident):
    """A chave de uma linha de dominio.

    E o QUADRUPLO, nao o identificador sozinho: o mesmo id vale para varios
    `Codigo TipoIF` (o indice IGP-M e o 104 em CCB, CCE, CCI, CRH...), e na base
    ele repete 202 vezes. Chaveado so pelo id, o upsert reescreveria a linha de
    um tipo de instrumento com a descricao de outro.
    """
    def _n(v):
        return ' '.join(str(v or '').split()).strip().upper()
    return (_n(grupo), _n(subgrupo), _n(tipoif), _dominio_id(ident))


def _cetip_update_dominio_json(src_path):
    """Atualiza a base `Dominio.json` NO LUGAR a partir do arquivo
    CADASTROCURVASMOEDASFEEDERDOMINIOS salvo (';', Latin-1).

    Colunas do arquivo: A=Nome do Grupo, B=Nome do Subgrupo, C=Codigo TipoIF,
    D=Identificador Qualificacao, E=Descricao Qualificacao, F=Data Inclusao.
    **A data de inclusao NAO entra na base** (pedido da mesa): ela e do arquivo,
    nao do dominio, e a base nao tem coluna para ela.

    Upsert pelo quadruplo (grupo, subgrupo, tipo IF, identificador), que e a
    chave de verdade. Linha que ja existe tem a DESCRICAO atualizada e conserva
    `Classificação`, `MAKER` e `CHECKER` — as tres sao da mesa, nao do arquivo.
    Linha nova entra com `STATUS: ACTIVE` (a unica forma que a base conhece) e
    as tres em branco.

    Linha da base que NAO esta no arquivo fica INTACTA, como no gemeo do VCP: a
    base tambem guarda o que a mesa cadastrou a mao, e apagar por ausencia
    silenciaria isso. Se um dia a mesa quiser que o sumico do arquivo signifique
    baixa, isso e uma decisao dela e vira `STATUS: INACTIVE`, nunca um delete.

    Melhor esforco: devolve o caminho ou None.
    """
    try:
        # cp1252, o ANSI do Windows, e nao latin-1: os dois so diferem na faixa
        # 0x80-0x9F, que e justamente onde moram o travessao e as aspas curvas
        # que aparecem em descricao de dominio. Em latin-1 eles viram caracteres
        # de controle invisiveis — o texto "parece" certo e leva sujeira que so
        # aparece no arquivo que sair depois (§480).
        with open(src_path, 'r', encoding='cp1252', errors='replace', newline='') as fh:
            linhas = [ln for ln in fh.read().splitlines() if ln.strip()]
        if not linhas:
            _R().log.warning('[cetip] Dominio.json: %s esta vazio', src_path)
            return None
        # O arquivo vem COM cabecalho; o teste e pelo conteudo, para um dia sem
        # ele nao perder a primeira linha de dado.
        primeira = [c.strip().lower() for c in linhas[0].split(';')]
        if any('nome do grupo' in c or 'identificador' in c or 'tipoif' in c
               for c in primeira):
            linhas = linhas[1:]

        atual = []
        if _store.isfile(_R().DOMINIO_JSON):
            try:
                atual = _store.read(_R().DOMINIO_JSON) or []
            except Exception:                               # noqa: BLE001
                atual = []
        if not isinstance(atual, list):
            atual = []
        # A chave aponta para uma LISTA: a base traz linhas exatamente iguais
        # repetidas (seis copias de FEIJO DE CORDA, de um import antigo), e
        # atualizar so a primeira deixaria as outras velhas ao lado dela.
        por_chave = {}
        for r in atual:
            if isinstance(r, dict):
                por_chave.setdefault(_dominio_key(
                    r.get('Nome do Grupo'), r.get('Nome do Subgrupo'),
                    r.get('Codigo TipoIF'), r.get('Identificador Qualificacao')), []).append(r)

        novas = atualizadas = 0
        for ln in linhas:
            f = ln.split(';')

            def g(i):
                return f[i].strip() if i < len(f) else ''

            grupo, subgrupo, tipoif, ident, descricao = g(0), g(1), g(2), g(3), g(4)
            if not ident and not descricao:
                continue
            chave = _dominio_key(grupo, subgrupo, tipoif, ident)
            existentes = por_chave.get(chave)
            if existentes:
                for r in existentes:
                    r['Descricao Qualificacao'] = descricao
                atualizadas += 1
                continue
            linha = {
                'STATUS': 'ACTIVE',
                'Nome do Grupo': grupo,
                'Nome do Subgrupo': subgrupo,
                'Codigo TipoIF': tipoif,
                # Numerico como o resto da base, para a coluna nao ficar com
                # dois tipos e a tela ordenar por texto sem avisar.
                'Identificador Qualificacao': (float(_dominio_id(ident))
                                               if _dominio_id(ident).replace('.', '').isdigit()
                                               else ident),
                'Descricao Qualificacao': descricao,
                'Classificação': None,
                'MAKER': None,
                'CHECKER': None,
            }
            atual.append(linha)
            por_chave.setdefault(chave, []).append(linha)
            novas += 1

        _R()._atomic_write_json(_R().DOMINIO_JSON, atual)
        _R().log.info('[cetip] Dominio.json atualizado: %d atualizada(s), %d nova(s) '
                      '(%d no total)', atualizadas, novas, len(atual))
        return _R().DOMINIO_JSON
    except Exception:
        _R().log.warning('[cetip] Dominio.json update failed:\n%s', traceback.format_exc())
        return None
