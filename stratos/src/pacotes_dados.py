# -*- coding: utf-8 -*-
"""pacotes_dados.py — a CHEGADA dos bancos do share no Stratos (HANDOFF §681,
passo C; §708).

O `exporta_dados.py` monta, na máquina do JPM, a cópia consistente dos bancos
(o pacote `otc-dados-<carimbo>/`, com o `manifest.json`), e o `envia_dados.py`
a leva para o Shared Drive em `<raiz>/pacotes/<nome>/`, com os arquivos grandes
em PARTES e o `envio.json` por último. Este módulo é a metade do contêiner:

  lista(raiz)           os pacotes e o estado de cada um;
  confere(raiz, nome)   junta as partes, confere cada arquivo pelo sha256 do
                        manifest e grava `conferencia.json` (ok ou os erros);
  ativa(raiz, nome)     grava o ponteiro `<raiz>/dados-ativos.txt` — só pacote
                        conferido e COMPLETO;
  desativa(raiz)        apaga o ponteiro (volta para `<raiz>/data`);
  dados_ativos(raiz)    na SUBIDA: a pasta `data/` do pacote do ponteiro, ou None.

O ponteiro troca só os DADOS (`OTC_DATA_DIR`/`OTC_DATABASE_DIR`): o `share/`
da ponte, o manifesto dela e a chave da sessão continuam na raiz. E ele só vale
no restart seguinte — trocar a pasta com o app de pé seria trocar os bancos por
baixo de quem os tem abertos. A pasta anterior fica como estava (a volta atrás
é o `desativa`, ou ativar o pacote anterior).

Depois de ativado, o pacote É o banco em uso: o sha256 do manifest deixa de
valer no primeiro Save. Por isso conferir pacote ativo é recusado.
"""
import hashlib
import io
import json
import os
import re
import shutil
import time

PASTA = 'pacotes'
PONTEIRO = 'dados-ativos.txt'
ENVIO = 'envio.json'
MANIFESTO = 'manifest.json'
CONFERENCIA = 'conferencia.json'
FORMATOS = (1,)                     # o `FORMATO` do exporta_dados.py que este lado lê
_NOME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$')


def _bytes(item):
    """O tamanho que o manifest declara; -1 sem ele. Nunca `or -1`: o arquivo
    VAZIO (o `.gitkeep` das pastas) declara 0, e o 0 virava -1."""
    v = item.get('bytes')
    return -1 if v is None else int(v)


class PacoteInvalido(ValueError):
    """O pedido não se aplica a este pacote (`code` diz por quê, para a tela)."""

    def __init__(self, code, text, **params):
        ValueError.__init__(self, text)
        self.code, self.text, self.params = code, text, params


def _pasta(raiz, nome):
    if not _NOME.match(str(nome or '')):
        raise PacoteInvalido('bad_name', 'Invalid package name.', nome=nome)
    return os.path.join(raiz, PASTA, nome)


def _le_json(caminho):
    try:
        with io.open(caminho, encoding='utf-8') as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None


def _grava_json(caminho, doc):
    tmp = caminho + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def _sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, 'rb') as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b''):
            h.update(bloco)
    return h.hexdigest()


def _versao(v):
    """'1.1.3' → (1, 1, 3); o que não for número fica de fora."""
    return tuple(int(x) for x in re.findall(r'\d+', str(v or ''))[:3])


def _dentro(pacote, rel):
    """O caminho de um arquivo do manifest, recusando o que sai do pacote."""
    alvo = os.path.normpath(os.path.join(pacote, *str(rel).split('/')))
    if not alvo.startswith(os.path.normpath(pacote) + os.sep):
        raise PacoteInvalido('bad_path', 'A path leaves the package.', caminho=rel)
    return alvo


def ativo(raiz):
    """O nome do pacote do ponteiro, ou ''."""
    try:
        with io.open(os.path.join(raiz, PONTEIRO), encoding='utf-8') as fh:
            return fh.read().strip()
    except FileNotFoundError:
        return ''


def estado(raiz, nome):
    """{nome, estado, ...}: `enviando` (sem o envio.json: a cópia não acabou),
    `recebido`, `conferido`, `recusado`; `ativo` diz se é o do ponteiro."""
    pacote = _pasta(raiz, nome)
    man = _le_json(os.path.join(pacote, MANIFESTO)) or {}
    env = _le_json(os.path.join(pacote, ENVIO))
    conf = _le_json(os.path.join(pacote, CONFERENCIA))
    if env is None:
        est = 'enviando'
    elif conf is None:
        est = 'recebido'
    else:
        est = 'conferido' if conf.get('ok') else 'recusado'
    return {'nome': nome, 'estado': est, 'ativo': ativo(raiz) == nome,
            'criado_em': man.get('criado_em'), 'completo': man.get('completo'),
            'duckdb': man.get('duckdb'), 'arquivos': len(man.get('arquivos') or ()),
            'bytes': sum(int(a.get('bytes') or 0) for a in man.get('arquivos') or ()),
            'enviado_em': (env or {}).get('enviado_em'),
            'conferido_em': (conf or {}).get('em'), 'erros': (conf or {}).get('erros') or [],
            'avisos': (conf or {}).get('avisos') or []}


def lista(raiz):
    base = os.path.join(raiz, PASTA)
    try:
        nomes = sorted((n for n in os.listdir(base)
                        if _NOME.match(n) and os.path.isdir(os.path.join(base, n))), reverse=True)
    except FileNotFoundError:
        nomes = []
    return [estado(raiz, n) for n in nomes]


def _junta(pacote, item):
    """Junta as partes de um arquivo (o `envio.json` diz quais, na ordem) no
    caminho final, por um `.parcial` + rename, e apaga as partes. Arquivo sem
    partes já chegou inteiro."""
    partes = item.get('partes') or []
    if not partes:
        return
    alvo = _dentro(pacote, item['caminho'])
    faltam = [p for p in partes if not os.path.isfile(_dentro(pacote, p))]
    if faltam:
        if os.path.isfile(alvo) and os.path.getsize(alvo) == _bytes(item):
            return                       # já juntado numa conferência anterior
        raise PacoteInvalido('missing_part', 'A part of %s did not arrive.' % item['caminho'],
                             caminho=item['caminho'], parte=faltam[0])
    os.makedirs(os.path.dirname(alvo), exist_ok=True)
    with open(alvo + '.parcial', 'wb') as out:
        for p in partes:
            with open(_dentro(pacote, p), 'rb') as fh:
                shutil.copyfileobj(fh, out, 1 << 20)
    os.replace(alvo + '.parcial', alvo)
    for p in partes:
        os.remove(_dentro(pacote, p))


def confere(raiz, nome, duckdb_aqui=None, progresso=None):
    """Junta as partes e confere o pacote inteiro contra o manifest; grava e
    devolve o `conferencia.json`. Recusa (PacoteInvalido) o que nem dá para
    conferir: envio pela metade e pacote ativo."""
    pacote = _pasta(raiz, nome)
    if ativo(raiz) == nome:
        raise PacoteInvalido('package_active', 'The active package is the live database: '
                             'it cannot be checked again.', nome=nome)
    env = _le_json(os.path.join(pacote, ENVIO))
    if env is None:
        raise PacoteInvalido('upload_unfinished', 'The upload has not finished (no envio.json).',
                             nome=nome)
    man = _le_json(os.path.join(pacote, MANIFESTO))
    if man is None:
        raise PacoteInvalido('no_manifest', 'The package has no manifest.json.', nome=nome)
    t0 = time.time()
    erros, avisos = [], []
    if man.get('formato') not in FORMATOS:
        erros.append('formato %r do manifest (este lado lê %r)' % (man.get('formato'), FORMATOS))
    if not man.get('completo'):
        erros.append('pacote INCOMPLETO: %d banco(s) ficaram de fora ou com erro'
                     % (len(man.get('pulados') or []) + len(man.get('erros') or [])))
    # §651: banco criado por um duckdb mais NOVO não abre no mais velho.
    if duckdb_aqui and man.get('duckdb') and _versao(man['duckdb']) > _versao(duckdb_aqui):
        erros.append('duckdb do pacote %s é mais novo que o do contêiner %s: os bancos não abririam'
                     % (man['duckdb'], duckdb_aqui))
    elif duckdb_aqui and man.get('duckdb') and _versao(man['duckdb'])[:2] != _versao(duckdb_aqui)[:2]:
        avisos.append('duckdb do pacote %s, do contêiner %s' % (man['duckdb'], duckdb_aqui))
    for item in env.get('arquivos') or []:
        try:
            _junta(pacote, item)
        except PacoteInvalido as e:
            erros.append(e.text)
    arquivos = man.get('arquivos') or []
    for i, a in enumerate(arquivos):
        if progresso:
            progresso(i, len(arquivos), a.get('caminho'))
        try:
            caminho = _dentro(pacote, a['caminho'])
        except PacoteInvalido as e:
            erros.append(e.text)
            continue
        if not str(a['caminho']).startswith('data/'):
            erros.append('%s fora de data/' % a['caminho'])
        elif not os.path.isfile(caminho):
            erros.append('%s não chegou' % a['caminho'])
        elif os.path.getsize(caminho) != _bytes(a):
            erros.append('%s com %d bytes (o manifest diz %s)'
                         % (a['caminho'], os.path.getsize(caminho), a.get('bytes')))
        elif _sha256(caminho) != a.get('sha256'):
            erros.append('%s com o sha256 diferente do manifest' % a['caminho'])
    if not os.path.isdir(os.path.join(pacote, 'data', 'db')):
        erros.append('o pacote não tem data/db')
    conf = {'ok': not erros, 'em': time.strftime('%Y-%m-%dT%H:%M:%S'), 'segundos': round(time.time() - t0, 1),
            'arquivos': len(arquivos), 'erros': erros, 'avisos': avisos,
            'duckdb_pacote': man.get('duckdb'), 'duckdb_aqui': duckdb_aqui}
    _grava_json(os.path.join(pacote, CONFERENCIA), conf)
    return conf


def ativa(raiz, nome):
    """O ponteiro passa a apontar o pacote (vale no próximo restart)."""
    st = estado(raiz, nome)
    if st['estado'] != 'conferido':
        raise PacoteInvalido('not_checked', 'Only a checked package can be activated '
                             '(this one is %s).' % st['estado'], nome=nome, estado=st['estado'])
    with io.open(os.path.join(raiz, PONTEIRO + '.tmp'), 'w', encoding='utf-8') as fh:
        fh.write(nome + '\n')
    os.replace(os.path.join(raiz, PONTEIRO + '.tmp'), os.path.join(raiz, PONTEIRO))
    return estado(raiz, nome)


def desativa(raiz):
    try:
        os.remove(os.path.join(raiz, PONTEIRO))
        return True
    except FileNotFoundError:
        return False


def dados_ativos(raiz):
    """(pasta data/ do pacote do ponteiro, motivo). Sem ponteiro: (None, '').
    Ponteiro para pacote que não está conferido ou sem data/db: (None, motivo) —
    a subida fica em `<raiz>/data` avisando, em vez de abrir bancos que ninguém
    conferiu."""
    nome = ativo(raiz)
    if not nome:
        return None, ''
    try:
        st = estado(raiz, nome)
    except PacoteInvalido:
        return None, 'ponteiro com nome inválido: %r' % nome
    if st['estado'] != 'conferido':
        return None, 'o pacote %s do ponteiro está %s' % (nome, st['estado'])
    data = os.path.join(raiz, PASTA, nome, 'data')
    if not os.path.isdir(os.path.join(data, 'db')):
        return None, 'o pacote %s do ponteiro não tem data/db' % nome
    return data, ''
