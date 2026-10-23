"""Confere a ponte do share (stratos/ponte_share.py + src/ponte_comum.py, HANDOFF §683).

O share e o Shared Drive viram duas pastas temporárias; o drive é o
`DriveLocal` (o mesmo contrato do `DriveHttp`), e o manifesto do lado do
Stratos é escrito pela MESMA função que a thread do contêiner chama. O relógio
é do teste: cada passada anda um minuto.

  1. a regra das datas e da chave (caixa e acento);
  2. ESPELHO: sobe, adota o que o manifesto mostrou, sobe o que mudou, manda à
     lixeira do drive o que saiu do share, ignora o que o app fez no drive, e
     NUNCA toca o share; lock do Office e Thumbs.db de fora; janela de dias;
  3. as travas: remoção em massa recusada, drive trocado (id do manifesto)
     recusado, virada sem --alinhar recusada;
  4. ALINHAR e VIRADA: o que o app grava desce, o que o Conecta tira do share
     sai do drive, o que o app tira do drive sai do share (para a lixeira
     local), conflito pelo sentido da pasta;
  5. a thread do contêiner escreve os manifestos.

    python stratos/tests/check_ponte.py
"""
import os
import shutil
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
STRATOS = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(STRATOS, 'src'))
sys.path.insert(0, STRATOS)
import ponte_comum as P  # noqa: E402
import ponte_share as PS  # noqa: E402

FALHAS = []


def ok(cond, msg):
    print(('ok    ' if cond else 'FAIL  ') + msg)
    if not cond:
        FALHAS.append(msg)


class Mundo(object):
    """Um share, um drive, a pasta local da ponte e o relógio."""

    def __init__(self, tmp, modo=P.ESPELHO):
        self.share = os.path.join(tmp, 'share')
        self.drive_raiz = os.path.join(tmp, 'drive')
        self.local = os.path.join(tmp, 'local')
        self.no_drive = os.path.join(self.drive_raiz, 'otc-tracker', 'share')
        self.ponte_drive = os.path.join(self.drive_raiz, 'otc-tracker', 'ponte')
        for p in (self.share, self.no_drive, self.local):
            os.makedirs(p, exist_ok=True)
        self.t = time.time() + 60
        self.drive = PS.DriveLocal(self.drive_raiz)
        self.ponte = PS.Ponte(self.share, self.drive, 'otc-tracker', self.local, modo=modo,
                              agora=lambda: self.t)
        self.instancia = P.instancia_do_drive(self.ponte_drive)

    def manifestos(self):
        for p in P.PASTAS:
            P.escreve_manifesto(self.no_drive, self.ponte_drive, p, self.t, self.instancia)

    def passa(self, slug, alinhar=False):
        """Um minuto, o manifesto do contêiner, uma passada."""
        self.t += 60
        self.manifestos()
        return self.ponte.passada(P.POR_SLUG[slug], alinhar=alinhar)


def escreve(raiz, rel, texto, mtime=None):
    p = os.path.join(raiz, *rel.split('/'))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as fh:
        fh.write(texto)
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def le(raiz, rel):
    p = os.path.join(raiz, *rel.split('/'))
    if not os.path.isfile(p):
        return None
    with open(p, encoding='utf-8') as fh:
        return fh.read()


def foto(raiz):
    """Tudo o que há numa árvore: caminho → (tamanho, mtime, conteúdo)."""
    out = {}
    for d, _sub, arqs in os.walk(raiz):
        for a in arqs:
            p = os.path.join(d, a)
            with open(p, 'rb') as fh:
                out[os.path.relpath(p, raiz)] = (os.path.getsize(p), os.path.getmtime(p), fh.read())
    return out


RET = 'Confirmation/Derivativos/OTC Tracker/Batch Conecta/Return/'
NEW = 'Confirmation/Derivativos/OTC Tracker/Batch Conecta/New/'
EI = 'Confirmation/Derivativos/OTC Tracker/Electronic Inventory/'
POS = 'Confirmation/Derivativos/OTC Tracker/CETIP Files/Position Files/'


def confere_regras():
    agora = time.mktime((2026, 10, 23, 12, 0, 0, 0, 0, -1))
    ok(P.data_do_caminho(EI + 'ACME/Confirmations/2026/10. October/22/NDF/x.pdf') ==
       time.mktime((2026, 10, 22, 0, 0, 0, 0, 0, -1)), 'data: AAAA/mm. Mes/dd')
    ok(P.data_do_caminho(POS + '2026/10/22/a.txt') is not None, 'data: AAAA/MM/DD')
    ok(P.data_do_caminho('x/20261022/a.txt') is not None, 'data: AAAAMMDD')
    ok(P.data_do_caminho(EI + 'ACME/SSI/ssi.pdf') is None, 'data: caminho sem data')
    ok(P.na_janela(POS + '2026/10/20/a.txt', 31, agora), 'janela: 3 dias atras, dentro')
    ok(not P.na_janela(POS + '2020/01/02/a.txt', 31, agora), 'janela: 2020, fora')
    ok(P.na_janela(POS + '2020/01/02/a.txt', None, agora), 'janela: sem janela, tudo dentro')
    ok(P.chave('Alteryx/Posição B3/x') == P.chave('Alteryx/Posição B3/x'),
       'chave: o acento composto e o decomposto sao o mesmo arquivo')
    ok(P.chave('B3 Files/A.txt') == P.chave('b3 files/a.txt'), 'chave: caixa nao importa')
    ok(P.ignora('~$Termo.docx') and P.ignora('Thumbs.db') and P.ignora('x.pdf.ponte-tmp')
       and not P.ignora('Termo.docx'), 'ignora: lock do Office, Thumbs.db e temporario')
    ok(P.limite_de_remocao(5) == 10 and P.limite_de_remocao(1000) == 200,
       'limite de remocao: 10, ou 20% da pasta')
    ok((PS.AMBIENTES['dev'], PS.AMBIENTES['prod']) == ('TEST', 'PRODUCTION'),
       'ambiente: dev/prod do stratos file viram TEST/PRODUCTION do stratosblocks')
    try:
        PS.main(['--solution-id', '1'])
        ok(False, 'ambiente: sem --env a ponte recusa')
    except SystemExit as e:
        ok(e.code == 2, 'ambiente: sem --env a ponte recusa (cada ambiente tem o seu drive)')


def confere_espelho(tmp):
    m = Mundo(os.path.join(tmp, 'espelho'))
    velho = m.t - 3600
    escreve(m.share, RET + 'retorno1.txt', 'ret 1', velho)
    escreve(m.share, RET + 'retorno2.txt', 'ret 2', velho)
    escreve(m.share, EI + 'ACME SA/SSI/ssi.pdf', 'ssi acme', velho)
    escreve(m.share, EI + 'ACME SA/Confirmations/~$termo.docx', 'lock', velho)
    escreve(m.share, EI + 'ACME SA/Thumbs.db', 'thumbs', velho)
    hoje = time.localtime(m.t)
    dia = '%04d/%02d. X/%02d' % (hoje.tm_year, hoje.tm_mon, hoje.tm_mday)
    escreve(m.share, POS + dia + '/DPOSICAO.txt', 'posicao de hoje', velho)
    escreve(m.share, POS + '2020/01. January/02/DPOSICAO.txt', 'posicao de 2020', velho)
    antes = foto(m.share)

    r = m.passa('conecta-return')
    ok(le(m.no_drive, RET + 'retorno1.txt') == 'ret 1' and
       le(m.no_drive, RET + 'retorno2.txt') == 'ret 2', 'espelho: o que esta no share sobe')
    ok(r['feitas'] == 2 and not r['recusa'], 'espelho: duas subidas, sem recusa %s' % r)
    r = m.passa('conecta-return')
    ok(r['acoes'] == 0, 'espelho: na passada seguinte o manifesto mostra e nada se repete')

    m.passa('electronic-inventory')
    ok(le(m.no_drive, EI + 'ACME SA/SSI/ssi.pdf') == 'ssi acme', 'espelho: a SSI sobe')
    ok(le(m.no_drive, EI + 'ACME SA/Confirmations/~$termo.docx') is None and
       le(m.no_drive, EI + 'ACME SA/Thumbs.db') is None, 'espelho: lock do Office e Thumbs.db ficam')
    m.passa('cetip-destino')
    ok(le(m.no_drive, POS + dia + '/DPOSICAO.txt') == 'posicao de hoje',
       'janela: a posicao de hoje sobe')
    ok(le(m.no_drive, POS + '2020/01. January/02/DPOSICAO.txt') is None,
       'janela: a de 2020 nao')

    # Mudou no share → sobe; saiu do share → lixeira do drive.
    escreve(m.share, RET + 'retorno1.txt', 'ret 1 corrigido', velho + 10)
    os.remove(os.path.join(m.share, *(RET + 'retorno2.txt').split('/')))
    antes = foto(m.share)
    m.passa('conecta-return')
    ok(le(m.no_drive, RET + 'retorno1.txt') == 'ret 1 corrigido', 'espelho: o que mudou sobe')
    ok(le(m.no_drive, RET + 'retorno2.txt') is None, 'espelho: o que saiu do share sai do drive')
    lixo = [p for p in foto(os.path.join(m.ponte_drive, 'lixeira')) if p.endswith('retorno2.txt')]
    ok(len(lixo) == 1, '   e vai para a lixeira do drive, nao some')

    # O app mexe no drive: nada disso vai ao share, e o que ele apagou não volta.
    escreve(m.no_drive, NEW + '73760009.TCO_BANCO.txt', 'registro do stratos', velho)
    os.remove(os.path.join(m.no_drive, *(RET + 'retorno1.txt').split('/')))
    r1 = m.passa('conecta-new')
    r2 = m.passa('conecta-return')
    ok(foto(m.share) == antes, 'espelho: o share fica INTOCADO (nem o arquivo da B3 do Stratos)')
    ok(le(m.no_drive, RET + 'retorno1.txt') is None and r2['acoes'] == 0,
       'espelho: o retorno que o app consumiu nao e subido de novo')
    ok(r1['acoes'] == 0, 'espelho: o arquivo gerado no Stratos nao vira acao')
    return m


def confere_travas(tmp):
    m = Mundo(os.path.join(tmp, 'travas'))
    velho = m.t - 3600
    for i in range(60):
        escreve(m.share, EI + 'CLIENTE %02d/SSI/ssi.pdf' % i, 'ssi %d' % i, velho)
    m.passa('electronic-inventory')
    ok(len([p for p in foto(m.no_drive) if p.endswith('ssi.pdf')]) == 60,
       'travas: 60 SSIs no drive')
    # O share "vazio" (fora do ar no meio da listagem, pasta renomeada): 60 > 12.
    shutil.rmtree(os.path.join(m.share, *EI.strip('/').split('/')))
    r = m.passa('electronic-inventory')
    ok('remo' in r['recusa'] and len([p for p in foto(m.no_drive) if p.endswith('ssi.pdf')]) == 60,
       'travas: remocao em massa RECUSADA, o drive fica (%s)' % r['recusa'])
    m.ponte.permitir_apagar = True
    m.passa('electronic-inventory')
    ok(len([p for p in foto(m.no_drive) if p.endswith('ssi.pdf')]) == 0,
       '   com --permitir-apagar ela vai (para a lixeira)')
    m.ponte.permitir_apagar = False

    # O drive foi trocado: outro id no manifesto.
    with open(os.path.join(m.ponte_drive, 'instancia'), 'w') as fh:
        fh.write('outro-drive')
    m.instancia = 'outro-drive'
    r = m.passa('electronic-inventory')
    ok('mudou' in r['recusa'], 'travas: drive trocado, a pasta para (%s)' % r['recusa'])

    # Uma subpasta que não abre: o resto segue, e nada se apaga dentro dela.
    u = Mundo(os.path.join(tmp, 'pulada'))
    velho = u.t - 3600
    escreve(u.share, EI + 'ABERTA/SSI/a.pdf', 'a', velho)
    escreve(u.share, EI + 'FECHADA/SSI/f.pdf', 'f', velho)
    u.passa('electronic-inventory')
    escreve(u.share, EI + 'ABERTA/SSI/b.pdf', 'b', velho)
    fechada = os.path.join(u.share, *(EI + 'FECHADA').split('/'))
    real = os.scandir

    def scandir_que_recusa(p):
        if os.path.normpath(p) == os.path.normpath(fechada):
            raise PermissionError(13, 'Access is denied', p)
        return real(p)

    orig = P.os.scandir
    P.lista.__defaults__ = (scandir_que_recusa, None)
    try:
        u.passa('electronic-inventory')
    finally:
        P.lista.__defaults__ = (orig, None)
    ok(le(u.no_drive, EI + 'ABERTA/SSI/b.pdf') == 'b', 'pulada: o resto da pasta segue')
    ok(le(u.no_drive, EI + 'FECHADA/SSI/f.pdf') == 'f',
       '   e o que esta na subpasta que nao abriu NAO sai do drive')

    v = Mundo(os.path.join(tmp, 'virada-sem'), modo=P.VIRADA)
    r = v.passa('conecta-new')
    ok('alinhar' in r['recusa'], 'travas: virada sem --alinhar e recusada')

    s = Mundo(os.path.join(tmp, 'sem-manifesto'))
    r = s.ponte.passada(P.POR_SLUG['conecta-new'])
    ok('manifesto' in r['recusa'], 'travas: sem manifesto do Stratos, nada acontece')


def confere_virada(tmp):
    m = Mundo(os.path.join(tmp, 'virada'))
    velho = m.t - 3600
    escreve(m.share, RET + 'retorno1.txt', 'ret 1', velho)
    escreve(m.share, NEW + 'ja_enviado.txt', 'do share', velho)
    escreve(m.share, EI + 'ACME SA/SSI/ssi.pdf', 'ssi', velho)
    escreve(m.share, 'Confirmation/Derivativos/OTC Tracker/Reconciliations/payrec/cashflows.xlsx',
            'cash v1', velho)
    for slug in ('conecta-return', 'conecta-new', 'electronic-inventory', 'payrec'):
        m.passa(slug)
    # Gerado no Stratos durante a validação: o --alinhar o tira antes da virada.
    escreve(m.no_drive, NEW + '73760009.VALIDACAO.txt', 'teste do stratos', velho)

    m.ponte.modo = P.VIRADA
    for slug in ('conecta-return', 'conecta-new', 'electronic-inventory', 'payrec'):
        m.passa(slug, alinhar=True)
    ok(le(m.no_drive, NEW + '73760009.VALIDACAO.txt') is None and
       le(m.share, NEW + '73760009.VALIDACAO.txt') is None,
       'alinhar: o que o Stratos gerou na validacao NAO vai ao share (vai a lixeira do drive)')
    for slug in ('conecta-return', 'conecta-new', 'electronic-inventory', 'payrec'):
        m.passa(slug)     # o manifesto mostra o que o alinhar subiu

    # O app grava na New: desce para o share.
    escreve(m.no_drive, NEW + '73760009.TCO_BANCO.txt', 'registro', velho)
    m.passa('conecta-new')
    ok(le(m.share, NEW + '73760009.TCO_BANCO.txt') == 'registro',
       'virada: o arquivo da B3 que o app gravou chega a New do share')
    # O Conecta pega e tira da New: sai do drive também.
    os.remove(os.path.join(m.share, *(NEW + '73760009.TCO_BANCO.txt').split('/')))
    m.passa('conecta-new')
    ok(le(m.no_drive, NEW + '73760009.TCO_BANCO.txt') is None,
       'virada: o que o Conecta tirou da New sai do drive')
    # O app lê e apaga o retorno: sai do share, para a lixeira LOCAL.
    os.remove(os.path.join(m.no_drive, *(RET + 'retorno1.txt').split('/')))
    m.passa('conecta-return')
    ok(le(m.share, RET + 'retorno1.txt') is None, 'virada: o retorno que o app consumiu sai do share')
    ok(any(p.endswith('retorno1.txt') for p in foto(os.path.join(m.local, 'lixeira'))),
       '   e fica na lixeira local da ponte')
    # Alguém põe um documento no Electronic Inventory pelo Explorer: sobe.
    escreve(m.share, EI + 'ACME SA/Transactional/contrato.pdf', 'contrato', velho)
    m.passa('electronic-inventory')
    ok(le(m.no_drive, EI + 'ACME SA/Transactional/contrato.pdf') == 'contrato',
       'virada: o documento salvo pelo Explorer chega ao Stratos')
    # O app gera uma confirmação: desce.
    escreve(m.no_drive, EI + 'ACME SA/Confirmations/2026/10. October/23/NDF/conf.pdf', 'conf', velho)
    m.passa('electronic-inventory')
    ok(le(m.share, EI + 'ACME SA/Confirmations/2026/10. October/23/NDF/conf.pdf') == 'conf',
       'virada: a confirmacao gerada no Stratos chega ao share')

    # Conflito: mudou dos dois lados. Pasta de SAIDA → vence o Stratos.
    m.passa('conecta-new')
    escreve(m.share, NEW + 'ja_enviado.txt', 'share mexeu', velho + 50)
    escreve(m.no_drive, NEW + 'ja_enviado.txt', 'stratos mexeu!', velho + 50)
    m.passa('conecta-new')
    ok(le(m.share, NEW + 'ja_enviado.txt') == 'stratos mexeu!',
       'conflito na pasta de saida: vence o Stratos')
    # Pasta AMBOS → vence o share.
    escreve(m.share, 'Confirmation/Derivativos/OTC Tracker/Reconciliations/payrec/cashflows.xlsx',
            'cash do share', velho + 50)
    escreve(m.no_drive, 'Confirmation/Derivativos/OTC Tracker/Reconciliations/payrec/cashflows.xlsx',
            'cash do stratos!!', velho + 50)
    m.passa('payrec')
    ok(le(m.no_drive, 'Confirmation/Derivativos/OTC Tracker/Reconciliations/payrec/cashflows.xlsx')
       == 'cash do share', 'conflito na pasta dos dois sentidos: vence o share')

    # O mesmo arquivo com outra caixa nos dois lados: um só.
    escreve(m.share, EI + 'BETA/SSI/SSI.PDF', 'beta', velho)
    escreve(m.no_drive, EI + 'beta/ssi/ssi.pdf', 'beta', velho)
    r = m.passa('electronic-inventory')
    ok(r['acoes'] == 0, 'caixa: BETA/SSI/SSI.PDF e beta/ssi/ssi.pdf sao o mesmo, nada se copia')

    # Mexido agora (está sendo escrito): espera a próxima passada.
    p = escreve(m.share, EI + 'ACME SA/SSI/nova.pdf', 'nova', m.t + 60 - 2)
    r = m.ponte.passada(P.POR_SLUG['electronic-inventory'])
    ok(le(m.no_drive, EI + 'ACME SA/SSI/nova.pdf') is None, 'assentar: arquivo de 2s atras espera')
    os.utime(p, (velho, velho))
    m.passa('electronic-inventory')
    ok(le(m.no_drive, EI + 'ACME SA/SSI/nova.pdf') == 'nova', '   e sobe na passada seguinte')


def confere_thread(tmp):
    raiz = os.path.join(tmp, 'thread')
    share = os.path.join(raiz, 'share')
    escreve(share, RET + 'r.txt', 'x', time.time() - 100)
    guardado = {k: os.environ.get(k) for k in ('OTC_STRATOS_ROOT', 'OTC_DISABLE_SCHEDULERS',
                                               'OTC_PONTE')}
    try:
        os.environ['OTC_STRATOS_ROOT'] = raiz
        os.environ.pop('OTC_DISABLE_SCHEDULERS', None)
        os.environ.pop('OTC_PONTE', None)
        import otc_stratos

        class App(object):
            config = {'SHARED_DRIVE_ROOT': share}

        t = otc_stratos._ponte_manifestos(App())
        alvo = P.caminho_manifesto(os.path.join(raiz, 'ponte'), 'conecta-return')
        limite = time.time() + 10
        while not os.path.isfile(alvo) and time.time() < limite:
            time.sleep(0.1)
        ok(t is not None and os.path.isfile(alvo), 'thread: o manifesto sai do contêiner')
        with open(alvo, encoding='utf-8') as fh:
            _i, _em, arqs = P.le_manifesto(fh.read())
        ok(P.chave(RET + 'r.txt') in arqs, '   e lista o arquivo do share do Stratos')
        os.environ['OTC_DISABLE_SCHEDULERS'] = '1'
        ok(otc_stratos._ponte_manifestos(App()) is None, 'thread: desligada nos testes')
    finally:
        for k, v in guardado.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main():
    tmp = tempfile.mkdtemp(prefix='otc-ponte-')
    try:
        confere_regras()
        confere_espelho(tmp)
        confere_travas(tmp)
        confere_virada(tmp)
        confere_thread(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print('\n%d falha(s)' % len(FALHAS))
    return 1 if FALHAS else 0


if __name__ == '__main__':
    sys.exit(main())
