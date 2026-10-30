"""A ponte entre o share da rede e o Shared Drive do Stratos: a parte COMUM.

O contêiner do Stratos não enxerga o share (`\\\\Nawest...\\lac\\BRA\\intra`), e as
pastas do share são usadas fora do app — o Batch Conecta da B3, quem abre o
Electronic Inventory pelo Explorer, a equipe global que lê a planilha do
Pending Confirmation. No Stratos o `SHARED_DRIVE_ROOT` do OTC é
`<raiz>/share`, dentro do Shared Drive (EFS) da solução. A ponte mantém as
pastas abaixo iguais nos dois lados (HANDOFF §683).

Ela tem duas metades, e este módulo é o que as duas usam:

  · no contêiner (`otc_stratos`), uma thread escreve, por pasta, o MANIFESTO do
    lado do Stratos (`<raiz>/ponte/manifesto/<pasta>.json`: caminho, mtime e
    tamanho de cada arquivo) — listar o drive pela API HTTP seria uma chamada
    por subpasta, e o Electronic Inventory tem milhares;
  · numa máquina da rede do JPM (`stratos/ponte_share.py`), um laço lê o share
    e o manifesto, decide o que copiar (`plano`) e copia pelo cliente
    `SharedDrive` do stratosblocks.

Dois modos:

  · ESPELHO (o padrão, enquanto a equipe segue na instância de hoje): só do
    share para o Stratos. A ponte não escreve NADA no share — um arquivo do
    Stratos em validação na `Batch Conecta\\New` seria registro de verdade na
    B3.
  · VIRADA (o Stratos é a produção): os dois sentidos, com a remoção
    propagada — o app esvazia a `Return` depois de ler, e o Conecta esvazia a
    `New` depois de enviar. Conflito (mudou dos dois lados desde a última
    passada) se resolve pelo SENTIDO da pasta: na de entrada vence o share, na
    de saída vence o Stratos, e o perdedor vai para a lixeira.

As pastas que o app só GRAVA e nunca lê (`DESCE`: as cópias extras da posição
e a planilha do Pending Confirmation) não sobem nunca: no espelho elas são
puladas, e no `--alinhar` e na virada o que está no share é só REGISTRADO na
base, sem cópia — é o que mantém o histórico de outras pessoas no share sem
levá-lo ao Stratos (§690), e o que o app gravar desce como numa pasta de saída.

Nada é apagado de verdade: o que sai vai para a LIXEIRA (no drive,
`<raiz>/ponte/lixeira/<dia>/`; no share, uma pasta local da máquina da ponte),
e uma passada que apagaria muito de uma vez é RECUSADA (`limite_de_remocao`).

Este arquivo é puro (só `os`, `json`, `re`, `time`): roda no contêiner, na
máquina do JPM e no teste, sem Flask e sem stratosblocks.
"""
import json
import os
import re
import time
import unicodedata
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor

ESPELHO = 'espelho'
VIRADA = 'virada'

ENTRADA = 'entrada'   # alguém (B3, pessoas, relatórios) põe; o app lê e às vezes apaga
SAIDA = 'saida'       # o app grava para alguém (B3, pessoas, outra equipe) pegar
AMBOS = 'ambos'       # os dois: pessoas e o app gravam
# O app grava e NÃO lê (§690): como SAIDA, mas o que está no share nunca sobe.
# Sem isto o espelho levaria ao Stratos 18 GB de histórico que nenhuma tela
# abre (o `--medir` de 26/10/2026): o CETIP_NDF, o CETIP_OPTIONS e a pasta
# `Movimento\Pending Confirmation`, onde o app escreve UM arquivo e o resto é
# de outras pessoas.
DESCE = 'desce'

Pasta = namedtuple('Pasta', 'slug rel sentido intervalo janela_dias')

# As pastas do share que o app usa, relativas ao SHARED_DRIVE_ROOT (o
# inventário do §683). `janela_dias` limita as pastas por dia (`AAAA\\mm. Mês\\dd`)
# aos últimos N dias corridos: o histórico de anos não serve ao app e custaria
# horas de cópia. None = a pasta inteira.
_OTC = 'Confirmation/Derivativos/OTC Tracker/'
PASTAS = (
    Pasta('conecta-new', _OTC + 'Batch Conecta/New', SAIDA, 20, None),
    Pasta('conecta-return', _OTC + 'Batch Conecta/Return', ENTRADA, 20, None),
    Pasta('settlements', _OTC + 'Settlements', ENTRADA, 30, None),
    Pasta('otm', _OTC + 'Settlement/OTM', ENTRADA, 30, None),
    Pasta('payrec', _OTC + 'Reconciliations/payrec', AMBOS, 30, None),
    Pasta('intrag', _OTC + 'Intrag', SAIDA, 30, 31),
    Pasta('cetip-origem', _OTC + 'Alteryx/Posição B3/ARQUIVOS CETIP', AMBOS, 60, 31),
    Pasta('cetip-destino', _OTC + 'CETIP Files/Position Files', SAIDA, 60, 31),
    Pasta('mtm', _OTC + 'Regulatory/MTM', AMBOS, 60, 31),
    Pasta('accrual', _OTC + 'Regulatory/Accrual', AMBOS, 60, 31),
    # o arquivo mensal da E-Financeira (§736): o app grava e nunca lê; a pasta
    # é por MÊS (`AAAA\MM. Month`), sem dia — a janela por dia não se aplica
    Pasta('efinanceira', _OTC + 'Regulatory/E-Financeira', DESCE, 120, None),
    Pasta('comitente', _OTC + 'Reconciliations/Comitente', SAIDA, 120, 31),
    Pasta('cgd-input', 'Confirmation/Derivativos/Alteryx/Batimento CGD/Input', ENTRADA, 120, None),
    Pasta('pending-confirmation', 'Confirmation/Derivativos/Movimento/Pending Confirmation',
          DESCE, 120, None),
    Pasta('cetip-options', 'CETIP_OPTIONS', DESCE, 120, 31),
    Pasta('cetip-ndf', 'CETIP_NDF', DESCE, 120, 31),
    Pasta('electronic-inventory', _OTC + 'Electronic Inventory', AMBOS, 600, None),
)
POR_SLUG = {p.slug: p for p in PASTAS}

# Arquivos que não são dado: o lock do Office (`~$x.docx`), o que o Windows
# solta nas pastas e os temporários da própria ponte.
_IGNORA = re.compile(r'^(~\$|\.ponte|\._)|^(thumbs\.db|desktop\.ini|\.ds_store)$|\.ponte-tmp$',
                     re.IGNORECASE)

ASSENTAR = 10          # s: arquivo mexido há menos que isto está sendo escrito
PENDENTE_MAX = 900     # s: quanto se espera o manifesto mostrar o que a ponte subiu

_ANO = re.compile(r'^(19|20)\d{2}$')
_MES = re.compile(r'^(\d{1,2})(\.\s*\S.*)?$')
_DIA = re.compile(r'^(\d{1,2})$')
_AAAAMMDD = re.compile(r'^(20\d{2})(\d{2})(\d{2})$')


def ignora(nome):
    return bool(_IGNORA.search(nome))


def chave(rel):
    """O mesmo arquivo nos dois lados: o share é Windows (caixa não importa) e o
    EFS é Linux (importa). Comparado pelo nome cru, `B3 Files` e `b3 files`
    seriam dois arquivos num lado e um no outro, e iriam e voltariam a cada
    passada. E o acento tem duas grafias em Unicode (o `ç` de `Posição` pode
    chegar composto ou como `c` + cedilha): a chave é a forma composta."""
    return unicodedata.normalize('NFC', rel.replace('\\', '/')).casefold()


def data_do_caminho(rel):
    """A data de uma pasta por dia no caminho (`2026/06. June/22`, `2026/06/22`
    ou `20260622`), ou None."""
    partes = [p for p in rel.replace('\\', '/').split('/') if p]
    for i, p in enumerate(partes):
        m = _AAAAMMDD.match(p)
        if m:
            try:
                return time.mktime((int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                    0, 0, 0, 0, 0, -1))
            except (OverflowError, ValueError):
                return None
        if _ANO.match(p) and i + 2 < len(partes):
            mm, dd = _MES.match(partes[i + 1]), _DIA.match(partes[i + 2])
            if mm and dd and 1 <= int(mm.group(1)) <= 12 and 1 <= int(dd.group(1)) <= 31:
                try:
                    return time.mktime((int(p), int(mm.group(1)), int(dd.group(1)),
                                        0, 0, 0, 0, 0, -1))
                except (OverflowError, ValueError):
                    return None
    return None


def na_janela(rel, janela_dias, agora):
    """Fora da janela o arquivo não existe para a ponte: nem se copia, nem se
    apaga. Caminho sem data está sempre dentro."""
    if not janela_dias:
        return True
    dia = data_do_caminho(rel)
    return dia is None or dia >= agora - (janela_dias + 1) * 86400


def longo(p, nome_so=None):
    """O caminho na forma ESTENDIDA do Windows (`\\\\?\\UNC\\…`), que não tem o
    limite de 260 caracteres — 248 para uma PASTA. O Electronic Inventory passa
    disso: `<contraparte>\\Confirmations\\AAAA\\mm. Mês\\dd\\<tipo>\\<documento>
    _files` chega a ~260 já na pasta, e o `scandir` dela respondia "The system
    cannot find the path specified" (WinError 3). Fora do Windows não muda nada.
    Só caminho ABSOLUTO: a forma estendida não resolve `.`/`..` nem relativo."""
    if (nome_so or os.name) != 'nt' or p.startswith('\\\\?\\'):
        return p
    if p.startswith('\\\\'):
        return '\\\\?\\UNC\\' + p[2:]
    if len(p) > 2 and p[1] == ':':
        return '\\\\?\\' + p
    return p


def _le_pasta(scandir, absoluto, rel, pasta, agora):
    """Uma pasta do share: ([(abs, rel)] das subpastas a abrir, {chave: item}
    dos arquivos). Roda numa thread do `lista`; o `stat` vem da própria
    listagem (no Windows o `DirEntry` já o traz, sem outra ida ao SMB)."""
    subs, arqs = [], {}
    with scandir(absoluto) as it:
        for e in it:
            if ignora(e.name):
                continue
            filho = rel + '/' + e.name
            if e.is_dir(follow_symlinks=False):
                # A pasta do DIA fora da janela nem é aberta; ano e mês
                # (ainda sem data inteira) são.
                if data_do_caminho(filho) is None or \
                        na_janela(filho, pasta.janela_dias, agora):
                    subs.append((e.path, filho))
                continue
            if not e.is_file(follow_symlinks=False):
                continue
            if not na_janela(filho, pasta.janela_dias, agora):
                continue
            st = e.stat(follow_symlinks=False)
            arqs[chave(filho)] = (filho, round(st.st_mtime, 3), st.st_size)
    return subs, arqs


def lista(raiz, pasta, agora, scandir=os.scandir, pulados=None, workers=1, progresso=None):
    """{chave: (rel, mtime, tamanho)} dos arquivos de `pasta` sob `raiz`, com
    `rel` relativo à RAIZ e com `/`.

    Uma listagem pela metade, comparada com a passada anterior, pareceria uma
    remoção em massa. Sem `pulados`, qualquer pasta que não abre LEVANTA. Com
    ele (uma lista), a subpasta que não abre (sem permissão, nome que o SMB
    recusa) entra na lista e a listagem segue: quem a chama não decide nada
    debaixo dela — uma contraparte bloqueada não pode parar o Electronic
    Inventory inteiro. A raiz da pasta que não abre levanta sempre.

    `workers` abre várias pastas AO MESMO TEMPO (nível a nível da árvore): no
    share o custo é a ida e volta de cada pasta aberta, não o arquivo, e o
    Electronic Inventory tem milhares de subpastas de contraparte — uma de cada
    vez eram ~40 minutos por passada. `progresso(pastas, arquivos)` é chamado a
    cada nível, para a passada longa dizer que está viva."""
    # Forma estendida já na base: os `e.path` dos filhos a herdam.
    base = longo(os.path.join(raiz, *pasta.rel.split('/')))
    out = {}
    if not os.path.isdir(base):
        return out
    nivel, abertas = [(base, pasta.rel)], 0
    pool = ThreadPoolExecutor(max_workers=workers) if workers and workers > 1 else None
    try:
        while nivel:
            def uma(item):
                try:
                    return item, _le_pasta(scandir, item[0], item[1], pasta, agora), None
                except OSError as exc:
                    return item, None, exc
            res = list(pool.map(uma, nivel)) if pool else [uma(i) for i in nivel]
            proximo = []
            for (_abs, rel), lido, erro in res:
                if erro is not None:
                    if pulados is None or rel == pasta.rel:
                        raise erro
                    pulados.append(rel)
                    continue
                subs, arqs = lido
                proximo.extend(subs)
                out.update(arqs)
            abertas += len(nivel)
            nivel = proximo
            if progresso:
                progresso(abertas, len(out))
    finally:
        if pool:
            pool.shutdown(wait=True)
    return out


# ── O manifesto do lado do Stratos ──────────────────────────────────────────

def caminho_manifesto(raiz_ponte, slug):
    return os.path.join(raiz_ponte, 'manifesto', slug + '.json')


def escreve_manifesto(raiz_share, raiz_ponte, pasta, agora=None, instancia=''):
    """No contêiner: grava o manifesto de `pasta` (troca atômica — a ponte nunca
    lê um pela metade). `instancia` identifica ESTE drive: se o drive for
    trocado ou zerado, a ponte vê o id mudar e não apaga nada do share."""
    agora = time.time() if agora is None else agora
    arquivos = lista(raiz_share, pasta, agora)
    doc = {'gerado_em': agora, 'instancia': instancia, 'pasta': pasta.slug,
           'arquivos': {rel: [m, t] for rel, m, t in arquivos.values()}}
    destino = caminho_manifesto(raiz_ponte, pasta.slug)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    tmp = destino + '.ponte-tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False)
    os.replace(tmp, destino)
    return len(arquivos)


def le_manifesto(texto):
    """(instancia, gerado_em, {chave: (rel, mtime, tamanho)}) do manifesto."""
    doc = json.loads(texto)
    arquivos = {chave(rel): (rel, round(float(v[0]), 3), int(v[1]))
                for rel, v in (doc.get('arquivos') or {}).items()}
    return str(doc.get('instancia') or ''), float(doc.get('gerado_em') or 0), arquivos


def instancia_do_drive(raiz_ponte):
    """O id deste drive, criado uma vez (`<raiz>/ponte/instancia`)."""
    p = os.path.join(raiz_ponte, 'instancia')
    try:
        with open(p, encoding='utf-8') as fh:
            atual = fh.read().strip()
        if atual:
            return atual
    except OSError:
        pass
    novo = '%x-%x' % (int(time.time()), os.getpid()) + os.urandom(4).hex()
    os.makedirs(raiz_ponte, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as fh:
        fh.write(novo)
    return novo


# ── A decisão ───────────────────────────────────────────────────────────────

Acao = namedtuple('Acao', 'tipo chave rel motivo')
# tipo: 'subir' (share → drive), 'baixar' (drive → share), 'lixo_drive',
#       'lixo_share', 'adota' (os dois lados já estão iguais: só registra),
#       'esquece' (sumiu dos dois lados), 'solta' (o manifesto não mostrou o
#       que a ponte subiu no prazo: deixa de esperar), 'registra' (pasta
#       DESCE: o que o share tem entra na base sem subir).
SO_BASE = ('adota', 'esquece', 'solta', 'registra')   # não copiam nada


def _sig(x):
    return None if x is None else [x[1], x[2]]


def plano(share, drive, base, modo, sentido, agora, drive_em, assentar=ASSENTAR,
          pendente_max=PENDENTE_MAX):
    """A lista de ações de UMA pasta, comparando cada lado com a BASE (o que os
    dois lados tinham na última passada que deu certo) — nunca um lado com o
    outro: os relógios do share e do contêiner não são o mesmo.

    `share`/`drive` são as listagens ({chave: (rel, mtime, tamanho)}), `base` é
    {chave: {'r', 's', 'd', 'p', 'pt'}} (`s`/`d` = [mtime, tamanho] de cada lado;
    `p` = o tamanho que a ponte SUBIU e o manifesto ainda não mostrou, desde
    `pt`). `drive_em` é o `gerado_em` do manifesto.

    Pasta `DESCE`: no espelho, nada; na virada, a regra da SAIDA com toda
    subida trocada por `registra`.
    """
    if sentido == DESCE and modo == ESPELHO:
        return []
    acoes = []
    for k in sorted(set(share) | set(drive) | set(base)):
        s, d, b = share.get(k), drive.get(k), base.get(k)
        # Mexido agora: está sendo escrito. Fica para a próxima passada.
        if s and s[1] > agora - assentar:
            continue
        if d and d[1] > drive_em - assentar:
            continue

        # O que a ponte subiu e o manifesto ainda não mostra: espera.
        d_base = b.get('d') if b else None
        if b and b.get('p') is not None:
            if d and d[2] == b['p']:
                acoes.append(Acao('adota', k, d[0], 'o manifesto mostrou o que subiu'))
                d_base = _sig(d)
            elif agora - float(b.get('pt') or 0) < pendente_max:
                continue
            else:
                acoes.append(Acao('solta', k, b.get('r') or k, 'o manifesto não mostrou '
                                  'o que subiu em %ds' % pendente_max))

        if modo == ESPELHO:
            if s:
                if b is None or b.get('s') is None:
                    if d and d[2] == s[2]:
                        acoes.append(Acao('adota', k, s[0], 'já igual nos dois lados'))
                    else:
                        acoes.append(Acao('subir', k, s[0], 'novo no share'))
                elif _sig(s) != b['s']:
                    acoes.append(Acao('subir', k, s[0], 'mudou no share'))
            elif b and b.get('s') is not None:
                if d:
                    acoes.append(Acao('lixo_drive', k, d[0], 'saiu do share'))
                else:
                    acoes.append(Acao('esquece', k, b.get('r') or k, 'saiu do share'))
            continue

        # VIRADA
        if b is None:
            if s and d:
                if s[2] == d[2]:
                    acoes.append(Acao('adota', k, s[0], 'já igual nos dois lados'))
                elif sentido in (SAIDA, DESCE):
                    acoes.append(Acao('baixar', k, d[0], 'diferente dos dois lados; '
                                      'na pasta de saída vence o Stratos'))
                else:
                    acoes.append(Acao('subir', k, s[0], 'diferente dos dois lados; '
                                      'vence o share'))
            elif s:
                acoes.append(Acao('subir', k, s[0], 'novo no share'))
            elif d:
                acoes.append(Acao('baixar', k, d[0], 'novo no Stratos'))
            continue

        mudou_s = _sig(s) != b.get('s')
        mudou_d = _sig(d) != d_base
        if not mudou_s and not mudou_d:
            continue
        if mudou_s and not mudou_d:
            if s:
                acoes.append(Acao('subir', k, s[0], 'mudou no share'))
            elif d:
                acoes.append(Acao('lixo_drive', k, d[0], 'saiu do share'))
            else:
                acoes.append(Acao('esquece', k, b.get('r') or k, 'saiu dos dois lados'))
        elif mudou_d and not mudou_s:
            if d:
                acoes.append(Acao('baixar', k, d[0], 'mudou no Stratos'))
            elif s:
                acoes.append(Acao('lixo_share', k, s[0], 'saiu do Stratos'))
            else:
                acoes.append(Acao('esquece', k, b.get('r') or k, 'saiu dos dois lados'))
        else:
            # Mudou dos DOIS lados desde a última passada.
            if not s and not d:
                acoes.append(Acao('esquece', k, b.get('r') or k, 'saiu dos dois lados'))
            elif s and not d:
                acoes.append(Acao('subir', k, s[0], 'saiu do Stratos mas mudou no share'))
            elif d and not s:
                acoes.append(Acao('baixar', k, d[0], 'saiu do share mas mudou no Stratos'))
            elif s[2] == d[2]:
                acoes.append(Acao('adota', k, s[0], 'mudou dos dois lados, igual'))
            elif sentido in (SAIDA, DESCE):
                acoes.append(Acao('baixar', k, d[0], 'conflito; na pasta de saída vence '
                                  'o Stratos'))
            else:
                acoes.append(Acao('subir', k, s[0], 'conflito; vence o share'))
    return _so_desce(acoes) if sentido == DESCE else acoes


def _so_desce(acoes):
    """Pasta DESCE: o que subiria só entra na base (o share segue com o
    histórico dele, o Stratos não o recebe)."""
    return [Acao('registra', a.chave, a.rel, a.motivo + '; pasta que só desce')
            if a.tipo == 'subir' else a for a in acoes]


def plano_alinhar(share, drive, agora, drive_em, assentar=ASSENTAR, sentido=None):
    """A passada que COMEÇA a virada: o drive fica igual ao share, e o que só
    existe no drive vai para a lixeira dele. Sem isto, o primeiro minuto da
    virada levaria ao share o que o Stratos gerou durante a validação — numa
    `Batch Conecta\\New`, registro de verdade na B3. Não usa base: é dela que a
    virada parte. Pasta DESCE: o share é só registrado, sem subir."""
    acoes = []
    for k in sorted(set(share) | set(drive)):
        s, d = share.get(k), drive.get(k)
        if (s and s[1] > agora - assentar) or (d and d[1] > drive_em - assentar):
            continue
        if s and d and s[2] == d[2]:
            acoes.append(Acao('adota', k, s[0], 'já igual nos dois lados'))
        elif s:
            acoes.append(Acao('subir', k, s[0], 'alinhar: o share vale'))
        else:
            acoes.append(Acao('lixo_drive', k, d[0], 'alinhar: só no Stratos'))
    return _so_desce(acoes) if sentido == DESCE else acoes


def sob(rel, prefixos):
    """`rel` está dentro de algum dos `prefixos` (comparado pela chave)?"""
    k = chave(rel)
    return any(k == chave(p) or k.startswith(chave(p) + '/') for p in prefixos)


def limite_de_remocao(n_base):
    """Quantas remoções uma passada pode fazer numa pasta. Acima disto é mais
    provável um lado vazio por engano (drive trocado, share fora do ar no meio
    da listagem) do que a rotina do dia: a passada RECUSA as remoções."""
    return max(10, n_base // 5)
