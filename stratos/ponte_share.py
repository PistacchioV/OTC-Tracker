#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ponte_share.py — mantém as pastas do share iguais no Shared Drive do Stratos.

    python stratos\\ponte_share.py --env dev|prod [--solution-id 76521]
                                  [--modo espelho|virada] [--alinhar]
                                  [--loop 20] [--so slug,slug] [--dry-run]
                                  [--permitir-apagar] [--medir]

Roda numa máquina da REDE do JPM, que enxerga o share, com o Python do
DevShell (é o que tem o `stratosblocks`: o cliente `SharedDrive` fala com o
Shared Drive por HTTP). O contêiner não enxerga o share, e a tarefa agendada
do Stratos também roda na nuvem: a ponte só pode morar aqui.

O que ela faz, pasta a pasta (a lista e a regra estão no `src/ponte_comum.py`,
HANDOFF §683): lista o share, lê o MANIFESTO que o contêiner escreve do lado
dele, compara cada lado com a BASE (o estado da última passada, guardado nesta
máquina) e copia o que mudou.

  --modo espelho  (o padrão) só do share para o Stratos. A ponte não escreve
                  nada no share: enquanto a equipe segue na instância de hoje,
                  um arquivo do Stratos em validação na `Batch Conecta\\New`
                  seria registro de verdade na B3.
  --alinhar       uma vez, antes da virada: o Stratos fica igual ao share, e o
                  que só existe no Stratos (o que ele gerou na validação) vai
                  para a lixeira dele.
  --modo virada   os dois sentidos, com as remoções. Recusa rodar sem um
                  --alinhar antes.
  --medir         só diz quantos arquivos e MB cada pasta tem no share.
  --dry-run       mostra o que faria.

Nada é apagado: o que sai do Stratos vai para `<raiz>/ponte/lixeira/<dia>/`
no drive, e o que sai do share vai para `%LOCALAPPDATA%\\OTC-Tracker\\ponte\\
lixeira\\<dia>\\` nesta máquina. Uma passada que tiraria muitos arquivos de
uma pasta é recusada (`--permitir-apagar` insiste), e se o drive do Stratos
for trocado ou zerado (o id do manifesto muda) a pasta para até alguém olhar.

`--env` é OBRIGATÓRIO e é o ambiente em que a solução está publicada (`dev`
ou `prod`, os mesmos nomes do `stratos file`; `TEST`/`PRODUCTION` também
valem). Cada ambiente tem o SEU Shared Drive: com a solução no dev, uma ponte
em `prod` gravaria num drive que o app não lê, sem erro nenhum.

Uma ponte por vez: ela grava um aviso no drive (`<raiz>/ponte/ponte.json`) a
cada passada, e uma segunda que encontre o de outra máquina com menos de 3
minutos espera.
"""
import argparse
import io
import json
import logging
import os
import shutil
import socket
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, 'src'))
import ponte_comum as P  # noqa: E402

log = logging.getLogger('ponte')

SHARE_PADRAO = r'\\Nawest.ad.jpmorganchase.com\lac\BRA\intra'
# O nome do `stratos file` (dev/prod) → a constante do `stratosblocks.env`.
AMBIENTES = {'dev': 'TEST', 'test': 'TEST', 'prod': 'PRODUCTION', 'production': 'PRODUCTION'}
DRIVE_RAIZ = 'otc-tracker'          # a pasta do OTC no Shared Drive (otc_stratos._PASTA_NO_DRIVE)
# O solution id do OTC no Stratos: o mesmo do CONTEXT_ROOT (`/76521/...`) e do
# `StratosAuth(app, 76521)` do solution.py.
SOLUCAO = '76521'
AVISO_VALIDO = 180                  # s: o aviso de outra ponte vale por isto


def _local():
    base = os.getenv('LOCALAPPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'OTC-Tracker', 'ponte')


def _longo(p):
    """Caminho do share acima de 260 caracteres no Windows (o Electronic
    Inventory tem nomes de contraparte longos)."""
    if os.name != 'nt' or len(p) < 240 or p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\UNC\\' + p[2:] if p.startswith('\\\\') else '\\\\?\\' + p


# ── O lado do Stratos ───────────────────────────────────────────────────────

class DriveHttp(object):
    """O Shared Drive pelo cliente `SharedDrive` do stratosblocks (HTTP,
    auditado). Caminhos com `/`, relativos à raiz da solução."""

    def __init__(self, solution_id, env):
        from stratosblocks.file_storage import SharedDrive
        import stratosblocks.env as E
        self._d = SharedDrive()
        self._sid = str(solution_id)
        self._env = getattr(E, env)
        self._pastas = set()

    def load(self, caminho):
        try:
            dado = self._d.load(solution_id=self._sid, server_path=caminho, env=self._env)
        except Exception as e:                              # noqa: BLE001
            texto = str(e).lower()
            if any(m in texto for m in ('404', 'not found', 'does not exist', 'no such')):
                return None
            raise
        return dado.read() if hasattr(dado, 'read') else dado

    def mkdir(self, caminho):
        partes = caminho.strip('/').split('/')
        for i in range(1, len(partes) + 1):
            atual = '/'.join(partes[:i])
            if atual in self._pastas:
                continue
            try:
                self._d.create_folder(solution_id=self._sid, server_path=atual, env=self._env)
            except Exception:                               # noqa: BLE001
                pass    # já existe (o cliente não diz de outro jeito); o save acusa o resto
            self._pastas.add(atual)

    def save(self, caminho, fh):
        self.mkdir(caminho.rsplit('/', 1)[0])
        self._d.save(solution_id=self._sid, server_path=caminho, file_obj=fh, env=self._env)

    def move(self, origem, destino):
        self.mkdir(destino.rsplit('/', 1)[0])
        self._d.rename(solution_id=self._sid, source_path=origem, dest_path=destino,
                       env=self._env)


class DriveLocal(object):
    """O mesmo contrato sobre uma pasta local: o teste, e um ensaio sem o
    Stratos (`--drive-local PASTA`)."""

    def __init__(self, raiz):
        self.raiz = raiz

    def _p(self, caminho):
        return os.path.join(self.raiz, *caminho.strip('/').split('/'))

    def load(self, caminho):
        try:
            with open(self._p(caminho), 'rb') as fh:
                return fh.read()
        except FileNotFoundError:
            return None

    def mkdir(self, caminho):
        os.makedirs(self._p(caminho), exist_ok=True)

    def save(self, caminho, fh):
        self.mkdir(caminho.rsplit('/', 1)[0])
        with open(self._p(caminho), 'wb') as out:
            shutil.copyfileobj(fh, out)

    def move(self, origem, destino):
        self.mkdir(destino.rsplit('/', 1)[0])
        os.replace(self._p(origem), self._p(destino))


# ── A base: o que os dois lados tinham na última passada ────────────────────

def _base_path(pasta_local, slug):
    return os.path.join(pasta_local, 'base', slug + '.json')


def carrega_base(pasta_local, slug):
    try:
        with open(_base_path(pasta_local, slug), encoding='utf-8') as fh:
            doc = json.load(fh)
        return doc.get('meta') or {}, doc.get('itens') or {}
    except (OSError, ValueError):
        return {}, {}


def grava_base(pasta_local, slug, meta, itens):
    p = _base_path(pasta_local, slug)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.ponte-tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump({'meta': meta, 'itens': itens}, fh, ensure_ascii=False)
    os.replace(tmp, p)


# ── Uma passada numa pasta ──────────────────────────────────────────────────

class Ponte(object):
    def __init__(self, share, drive, drive_raiz=DRIVE_RAIZ, pasta_local=None,
                 modo=P.ESPELHO, permitir_apagar=False, dry_run=False, agora=time.time):
        self.share = share
        self.drive = drive
        self.raiz = drive_raiz.strip('/')
        self.local = pasta_local or _local()
        self.modo = modo
        self.permitir_apagar = permitir_apagar
        self.dry_run = dry_run
        self.agora = agora

    def _d(self, rel):
        return '%s/share/%s' % (self.raiz, rel)

    def _s(self, rel):
        return _longo(os.path.join(self.share, *rel.split('/')))

    def manifesto(self, pasta):
        txt = self.drive.load('%s/ponte/manifesto/%s.json' % (self.raiz, pasta.slug))
        return None if txt is None else P.le_manifesto(txt)

    def passada(self, pasta, alinhar=False):
        """-> {'acoes': n, 'feitas': n, 'erros': n, 'recusa': motivo ou ''}."""
        agora = self.agora()
        res = {'pasta': pasta.slug, 'acoes': 0, 'feitas': 0, 'erros': 0, 'recusa': ''}
        man = self.manifesto(pasta)
        if man is None:
            res['recusa'] = 'sem manifesto do Stratos (o contêiner ainda não o escreveu)'
            return res
        instancia, drive_em, drive = man
        meta, base = carrega_base(self.local, pasta.slug)
        if meta.get('instancia') and instancia and meta['instancia'] != instancia and not alinhar:
            res['recusa'] = ('o drive do Stratos mudou (id %s, era %s): nada se copia até um '
                             '--alinhar' % (instancia, meta['instancia']))
            return res
        if self.modo == P.VIRADA and not meta.get('alinhado_em') and not alinhar:
            res['recusa'] = 'virada sem --alinhar antes'
            return res
        pulados = []
        share = P.lista(self.share, pasta, agora, pulados=pulados)
        if pulados:
            log.warning('[ponte] %s: %d subpasta(s) do share não abriram (%s%s); nada se '
                        'decide dentro delas nesta passada', pasta.slug, len(pulados),
                        ', '.join(pulados[:3]), '…' if len(pulados) > 3 else '')

        if alinhar:
            acoes = P.plano_alinhar(share, drive, agora, drive_em)
        else:
            acoes = P.plano(share, drive, base, self.modo, pasta.sentido, agora, drive_em)
            remocoes = [a for a in acoes if a.tipo in ('lixo_drive', 'lixo_share')]
            limite = P.limite_de_remocao(len(base))
            if len(remocoes) > limite and not self.permitir_apagar:
                log.error('[ponte] %s: %d remoções numa passada (limite %d) — RECUSADAS. '
                          'Confira os dois lados; --permitir-apagar insiste.',
                          pasta.slug, len(remocoes), limite)
                acoes = [a for a in acoes if a.tipo not in ('lixo_drive', 'lixo_share')]
                res['recusa'] = 'remoções demais (%d > %d)' % (len(remocoes), limite)
        if pulados:
            acoes = [a for a in acoes if not P.sob(a.rel, pulados)]
        if self.modo == P.ESPELHO:
            # Defesa: no espelho nada toca o share, saia do plano o que sair.
            acoes = [a for a in acoes if a.tipo not in ('baixar', 'lixo_share')]
        res['acoes'] = len([a for a in acoes if a.tipo not in ('adota', 'esquece', 'solta')])

        if self.dry_run:
            for a in acoes:
                if a.tipo not in ('adota', 'esquece', 'solta'):
                    print('  %-10s %s  (%s)' % (a.tipo, a.rel, a.motivo))
            return res

        dia = time.strftime('%Y%m%d', time.localtime(agora))
        for i, a in enumerate(acoes):
            try:
                if self._executa(a, share, drive, base, agora, dia):
                    res['feitas'] += 1
            except Exception as e:                           # noqa: BLE001
                res['erros'] += 1
                log.warning('[ponte] %s: %s %s falhou: %s: %s', pasta.slug, a.tipo, a.rel,
                            type(e).__name__, e)
            if i % 50 == 49:
                grava_base(self.local, pasta.slug, meta, base)
        meta['instancia'] = instancia or meta.get('instancia', '')
        if alinhar:
            meta['alinhado_em'] = agora
        grava_base(self.local, pasta.slug, meta, base)
        return res

    def _executa(self, a, share, drive, base, agora, dia):
        k = a.chave
        s, d, b = share.get(k), drive.get(k), base.get(k) or {}
        if a.tipo == 'adota':
            novo = dict(b, r=(s or d)[0], p=None)
            if s:
                novo['s'] = [s[1], s[2]]
            if d:
                novo['d'] = [d[1], d[2]]
            base[k] = novo
            return False
        if a.tipo == 'solta':
            base[k] = dict(b, p=None)
            return False
        if a.tipo == 'esquece':
            base.pop(k, None)
            return False
        if a.tipo == 'subir':
            caminho = self._s(s[0])
            st = os.stat(caminho)
            if st.st_mtime > agora - P.ASSENTAR:
                return False                                 # mexeram nele agora
            with open(caminho, 'rb') as fh:
                self.drive.save(self._d(d[0] if d else s[0]), fh)
            base[k] = {'r': s[0], 's': [round(st.st_mtime, 3), st.st_size], 'd': b.get('d'),
                       'p': st.st_size, 'pt': agora}
            log.info('[ponte] ↑ %s', s[0])
            return True
        if a.tipo == 'baixar':
            if self.modo == P.ESPELHO:
                raise RuntimeError('espelho não escreve no share')
            dado = self.drive.load(self._d(d[0]))
            if dado is None or len(dado) != d[2]:
                return False                                 # sumiu ou mudou no meio
            alvo = self._s(s[0] if s else d[0])
            os.makedirs(os.path.dirname(alvo), exist_ok=True)
            tmp = alvo + '.ponte-tmp'
            with open(tmp, 'wb') as fh:
                fh.write(dado)
            os.replace(tmp, alvo)
            st = os.stat(alvo)
            base[k] = {'r': s[0] if s else d[0], 's': [round(st.st_mtime, 3), st.st_size],
                       'd': [d[1], d[2]], 'p': None}
            log.info('[ponte] ↓ %s', d[0])
            return True
        if a.tipo == 'lixo_drive':
            self.drive.move(self._d(d[0]), '%s/ponte/lixeira/%s/%s' % (self.raiz, dia, d[0]))
            base.pop(k, None)
            log.info('[ponte] lixeira do Stratos: %s (%s)', d[0], a.motivo)
            return True
        if a.tipo == 'lixo_share':
            if self.modo == P.ESPELHO:
                raise RuntimeError('espelho não escreve no share')
            destino = os.path.join(self.local, 'lixeira', dia, *s[0].split('/'))
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.move(self._s(s[0]), destino)
            base.pop(k, None)
            log.info('[ponte] lixeira local: %s (%s)', s[0], a.motivo)
            return True
        raise ValueError('ação desconhecida: %s' % a.tipo)


# ── Uma ponte por vez ───────────────────────────────────────────────────────

def _quem():
    return '%s/%s/%d' % (socket.gethostname(), os.getenv('USERNAME') or os.getenv('USER') or '?',
                         os.getpid())


def toma_aviso(drive, raiz, agora):
    """True se esta máquina pode trabalhar agora (e renova o aviso)."""
    caminho = '%s/ponte/ponte.json' % raiz
    eu = _quem()
    try:
        atual = json.loads(drive.load(caminho) or b'{}')
    except ValueError:
        atual = {}
    if atual.get('quem') and atual['quem'] != eu and agora - float(atual.get('em') or 0) < AVISO_VALIDO:
        log.warning('[ponte] outra ponte está rodando (%s, há %.0fs): esperando',
                    atual['quem'], agora - float(atual['em']))
        return False
    drive.save(caminho, io.BytesIO(json.dumps({'quem': eu, 'em': agora}).encode('utf-8')))
    return True


# ── Linha de comando ────────────────────────────────────────────────────────

def medir(share, pastas, agora):
    total_n = total_b = 0
    for p in pastas:
        try:
            itens = P.lista(share, p, agora)
        except OSError as e:
            print('%-22s ERRO: %s' % (p.slug, e))
            continue
        n, b = len(itens), sum(v[2] for v in itens.values())
        total_n += n
        total_b += b
        janela = ('%d dias' % p.janela_dias) if p.janela_dias else 'tudo'
        print('%-22s %8d arquivos %10.1f MB  (%s, %s)' % (p.slug, n, b / 1e6, p.sentido, janela))
    print('%-22s %8d arquivos %10.1f MB' % ('TOTAL', total_n, total_b / 1e6))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--solution-id', default=os.getenv('OTC_PONTE_SOLUTION_ID', SOLUCAO))
    ap.add_argument('--env', default=os.getenv('OTC_PONTE_ENV', ''),
                    type=lambda v: v.strip().lower(),
                    help='dev ou prod: o ambiente em que a solução está publicada')
    ap.add_argument('--share', default=os.getenv('OTC_PONTE_SHARE', SHARE_PADRAO))
    ap.add_argument('--drive-raiz', default=DRIVE_RAIZ)
    ap.add_argument('--drive-local', default='', help='ensaio: uma pasta local no lugar do drive')
    ap.add_argument('--modo', default=P.ESPELHO, choices=(P.ESPELHO, P.VIRADA))
    ap.add_argument('--alinhar', action='store_true')
    ap.add_argument('--loop', type=int, default=0, help='segundos entre passadas (0 = uma só)')
    ap.add_argument('--so', default='', help='só estas pastas (slugs, por vírgula)')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--permitir-apagar', action='store_true')
    ap.add_argument('--medir', action='store_true')
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

    pastas = list(P.PASTAS)
    if a.so:
        pedidas = [x.strip() for x in a.so.split(',') if x.strip()]
        faltam = [x for x in pedidas if x not in P.POR_SLUG]
        if faltam:
            ap.error('pasta desconhecida: %s (há: %s)' % (', '.join(faltam),
                                                           ', '.join(P.POR_SLUG)))
        pastas = [P.POR_SLUG[x] for x in pedidas]

    if a.medir:
        medir(a.share, pastas, time.time())
        return 0
    if a.drive_local:
        drive = DriveLocal(a.drive_local)
    else:
        if not a.solution_id:
            ap.error('--solution-id (ou OTC_PONTE_SOLUTION_ID) é obrigatório')
        if a.env not in AMBIENTES:
            ap.error('--env dev ou --env prod (ou OTC_PONTE_ENV) é obrigatório: o ambiente '
                     'em que a solução está publicada. Cada um tem o seu Shared Drive.')
        drive = DriveHttp(a.solution_id, AMBIENTES[a.env])
    ponte = Ponte(a.share, drive, a.drive_raiz, modo=a.modo,
                  permitir_apagar=a.permitir_apagar, dry_run=a.dry_run)
    log.info('[ponte] %s, %s -> %s/share (%s), %d pasta(s)%s', a.modo, a.share, a.drive_raiz,
             a.env or 'drive local', len(pastas), ' (alinhar)' if a.alinhar else '')

    proximo = {}
    while True:
        agora = time.time()
        if a.dry_run or toma_aviso(drive, ponte.raiz, agora):
            for p in pastas:
                if a.loop and proximo.get(p.slug, 0) > agora:
                    continue
                try:
                    r = ponte.passada(p, alinhar=a.alinhar)
                except OSError as e:
                    log.warning('[ponte] %s: o share não respondeu (%s); fica para a próxima',
                                p.slug, e)
                    continue
                except Exception:                           # noqa: BLE001
                    log.exception('[ponte] %s: a passada quebrou', p.slug)
                    continue
                finally:
                    proximo[p.slug] = agora + p.intervalo
                if r['recusa'] or r['acoes'] or r['erros']:
                    log.info('[ponte] %s: %d ação(ões), %d feita(s), %d erro(s)%s', p.slug,
                             r['acoes'], r['feitas'], r['erros'],
                             (' — ' + r['recusa']) if r['recusa'] else '')
        if not a.loop or a.alinhar:
            return 0
        time.sleep(a.loop)


if __name__ == '__main__':
    sys.exit(main())
