# -*- coding: utf-8 -*-
"""check_duck_read.py — o flip de leitura DB-first com contrato de frescor (fase 3).

O `apps/pages/duck_read.py` só responde pelo banco quando o `_manifest` prova
que a tabela reflete o JSON COMO ELE ESTÁ em disco; senão devolve `None`, o
chamador cai no JSON de sempre e o espelho é avisado para se curar. O que este
script prova, nos dois pilotos religados:

  1. **RefData** (`_refdata_records` + os três índices derivados): com o banco
     FRESCO, a resposta vem DO BANCO — provado adulterando a tabela e vendo a
     adulteração na resposta (o JSON diz outra coisa);
  2. **frescor**: editado o JSON por FORA do app (sem aviso), o manifest não
     casa mais, a leitura cai no JSON — dado velho do banco nunca vence — e o
     espelho se cura sozinho (a leitura seguinte volta a ser do banco);
  3. **feriados**: `calendars()` e `load_holidays` DB-first com a data
     voltando como STRING ISO (a forma que o JSON sempre teve), e o fallback
     JSON + seed intactos quando não há banco nenhum;
  4. banco ausente/ilegível nunca é erro: é `None` e o comportamento de ontem.

Tudo em tempfile; não toca em dado real.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', ROOT)
os.environ.pop('OTC_DISABLE_SCHEDULERS', None)
os.environ.pop('OTC_DISABLE_DUCK_MIRROR', None)

import duckdb                                               # noqa: E402

from apps.pages import routes as R                          # noqa: E402
from apps.pages import duck_mirror as M                     # noqa: E402
from apps.pages import duck_read as DR                      # noqa: E402
from apps.pages.features.holidays.infra import persistence as HP   # noqa: E402

TMP = tempfile.mkdtemp(prefix='otc-dread-')
R._B3_DATA_DIR = TMP
DBDIR = os.path.join(TMP, 'db')

fails = []


def check(label, got, exp=True):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label +
          ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


def _tamper(db, sql):
    con = duckdb.connect(os.path.join(DBDIR, db))
    try:
        con.execute(sql)
    finally:
        con.close()


# ── 1. RefData: com o banco fresco, a resposta vem DO banco ─────────────────
R._b3_save(os.path.join(TMP, 'RefData.json'),
           [{'COUNTERPARTY': 'ACME LTDA', 'SPN': '007135',
             'TAX ID': '45.985.371/0001-08'}])
check('1. espelho alcancou o banco', M.flush(20))
check('1. sem banco adulterado, DB e JSON dizem o mesmo',
      DR.refdata_rows()[0]['SPN'], '007135')
# A prova de que a fonte é o BANCO: adultera a coluna `_raw` — o canal que o
# flip consome (as tipadas ficam para o SQL) — enquanto o JSON continua 007135.
_tamper('reference_data.db',
        'UPDATE refdata SET "_raw" = '
        '\'{"COUNTERPARTY": "ACME LTDA", "SPN": "999999"}\'')
check('1. a leitura veio do banco (a adulteracao aparece)',
      R._refdata_records()[0]['SPN'], '999999')
R._REFDATA_TRIPLE_CACHE['mtime'] = None
check('1. e o indice derivado a herdou',
      R._refdata_triples()[0]['spn'], '999999')

# ── 2. frescor: JSON editado POR FORA cai no JSON e o espelho se cura ───────
with open(os.path.join(TMP, 'RefData.json'), 'w', encoding='utf-8') as fh:
    json.dump([{'COUNTERPARTY': 'BETA SA', 'SPN': '135742'}], fh)
check('2. manifest defasado: a resposta e o JSON (dado velho nunca vence)',
      R._refdata_records()[0]['SPN'], '135742')
check('2. e o espelho se curou sozinho', M.flush(20))
check('2. leitura seguinte volta a ser do banco (agora fresco)',
      DR.refdata_rows()[0]['COUNTERPARTY'], 'BETA SA')

# ── 3. feriados: calendars() e load_holidays DB-first ───────────────────────
regs = HP.calendars()                    # sem banco: semeia o JSON (fallback)
check('3. seed intacto no fallback', len(regs) >= 11)
M.flush(20)
check('3. depois do espelho, o registro vem do banco',
      HP._calendars_db() is not None)
erro = HP.write_holidays('anbima.json',
                         [{'date': '2026-01-01', 'title': 'Confraternização',
                           'calendar': 'ANBIMA'}])
check('3. write ok', erro, None)
M.flush(20)
_tamper('holiday_calendars.db', "UPDATE anbima SET \"title\" = 'DO BANCO'")
lidas = HP.load_holidays('anbima.json')
check('3. load_holidays veio do banco, data como STRING ISO',
      lidas, [{'date': '2026-01-01', 'title': 'DO BANCO', 'calendar': 'ANBIMA'}])

# ── 3b. CounterpartyDetails: fidelidade total via _raw ──────────────────────
from apps.pages.platform import counterparty as CP          # noqa: E402
CP._cpd_save_list([{'SPN': '007135', 'COUNTERPARTY': 'ACME LTDA', 'CGD': [],
                    'CONTACTS': [{'name': 'Bob', 'email': 'b@x'}],
                    'BANKING': {'ACCOUNTS': []},
                    'NET': {'value': 'Total Net', 'status': 'Active'}}])
M.flush(20)
# O contato veio SEM 'appr'/'maker' — a semântica de chave-AUSENTE que o
# _contacts_norm lê. O flip só é correto se as duas fontes respondem IGUAL.
via_db = CP._cpd_load()
_orig_cpd = None
try:
    import apps.pages.duck_read as _dr
    _orig_cpd = _dr.cpd_records
    _dr.cpd_records = lambda: None
    M.flush(20)                       # a migração one-shot pode ter regravado
    via_json = CP._cpd_load()
finally:
    _dr.cpd_records = _orig_cpd
check('3b. DB-first e JSON respondem IGUAL (chave-ausente preservada)',
      via_db, via_json)
check('3b. contato legado importado como ja aprovado (a chave AUSENTE foi vista)',
      bool(via_db and via_db[0]['CONTACTS']
           and via_db[0]['CONTACTS'][0].get('appr')))

# ── 3c. o navegador: /static/data servido do banco quando fresco ────────────
M.flush(20)
resp = R._duck_static_json('RefData.json')
check('3c. RefData.json servido do banco',
      resp is not None and json.loads(resp.get_data(as_text=True))[0]['SPN'],
      '135742')
resp = R._duck_static_json('anbima.json')
check('3c. arquivo de calendario servido do banco (via registro)',
      resp is not None and json.loads(resp.get_data(as_text=True))[0]['calendar'],
      'ANBIMA')
check('3c. subpasta fora dos mappings e nao-coberto caem no arquivo (None)',
      (R._duck_static_json('translations/en.json'),
       R._duck_static_json('datatables.json')), (None, None))

# ── 3d. datasets: _mapping_rows, _b3_load e o estático dos mappings ─────────
R._MAPPINGS_DIR = os.path.join(TMP, 'mappings')
os.makedirs(R._MAPPINGS_DIR, exist_ok=True)
# 12 linhas: com o _seq gravado como TEXTO, '10' < '2' — a ordem so sai certa
# porque a leitura ordena por CAST.
linhas_map = [{'BANK': 'B%02d' % i, 'CODE': str(300 + i)} for i in range(12)]
R._atomic_write_json(os.path.join(R._MAPPINGS_DIR, 'bank-name.json'), linhas_map)
M.flush(20)
lidas = DR.dataset_records(os.path.join(R._MAPPINGS_DIR, 'bank-name.json'))
check('3d. dataset_records devolve a LISTA NA ORDEM do arquivo (12 linhas)',
      lidas, linhas_map)
import duckdb as _dd
_con = _dd.connect(os.path.join(DBDIR, 'mappings', 'bank-name.db'))
_con.execute('UPDATE bank_name SET "_raw" = \'{"BANK": "DO BANCO"}\' '
             'WHERE "BANK" = \'B00\'')
_con.close()
check('3d. _mapping_rows veio do banco (a adulteracao aparece)',
      R._mapping_rows('bank-name')[0], {'BANK': 'DO BANCO'})
R._b3_save(os.path.join(TMP, 'Subjacente.json'),
           [{'Codigo': 'AAPL34', 'Classe': 'EQUITY'}])
M.flush(20)
resp = R._duck_static_json('Subjacente.json')
check('3d. cadastro B3 de raiz servido do banco',
      resp is not None and json.loads(resp.get_data(as_text=True))[0]['Codigo'],
      'AAPL34')
check('3d. _b3_load DB-first devolve as linhas e o caminho do JSON',
      (R._b3_load('subj')[0][0]['Classe'],
       R._b3_load('subj')[1].endswith('Subjacente.json')), ('EQUITY', True))
resp = R._duck_static_json('mappings/bank-name.json')
check('3d. mapping servido do banco pelo /static/data',
      resp is not None and json.loads(resp.get_data(as_text=True))[0],
      {'BANK': 'DO BANCO'})

# ── 3e. arquivo-dia: o funil _day_json DB-first ─────────────────────────────
dia = os.path.join(TMP, 'cache', 'new deals', 'NDF', 'Commodities', '2026', '06',
                   '20260618_ndfcomm.json')
os.makedirs(os.path.dirname(dia), exist_ok=True)
R._atomic_write_json(dia, [{'Deal': 'DBH-9AAA'}, {'Deal': 'DBH-9BBB'}])
M.flush(20)
_tamper(os.path.join('cache', 'new deals', 'NDF', 'Commodities.db'),
        'UPDATE main.d_20260618_ndfcomm SET "_raw" = '
        '\'{"Deal": "DO BANCO"}\' WHERE "Deal" = \'DBH-9AAA\'')
lidas = R._day_json(dia, os.path.getmtime(dia), os.path.getsize(dia))
check('3e. _day_json veio do banco, NA ORDEM do arquivo',
      lidas, [{'Deal': 'DO BANCO'}, {'Deal': 'DBH-9BBB'}])
obj = os.path.join(TMP, 'cache', 'reconciliation', 'payrec', '2026-07-08.json')
os.makedirs(os.path.dirname(obj), exist_ok=True)
R._atomic_write_json(obj, {'success': True, 'summary': [{'a': 1}]})
M.flush(20)
lidas = R._day_json(obj, os.path.getmtime(obj), os.path.getsize(obj))
check('3e. payload-objeto continua vindo do JSON (embrulhado em lista)',
      lidas, [{'success': True, 'summary': [{'a': 1}]}])
vazio = os.path.join(TMP, 'cache', 'new deals', 'NDF', 'Commodities', '2026', '06',
                     '20260619_ndfcomm.json')
R._atomic_write_json(vazio, [])
M.flush(20)
check('3e. dia vazio reconstrói como lista vazia',
      R._day_json(vazio, os.path.getmtime(vazio), os.path.getsize(vazio)), [])

# ── 4. banco ausente/ilegível nunca é erro ──────────────────────────────────
os.rename(os.path.join(DBDIR, 'reference_data.db'),
          os.path.join(DBDIR, 'reference_data.db.fora'))
check('4. banco ausente: fallback JSON, sem erro',
      R._refdata_records()[0]['SPN'], '135742')
with open(os.path.join(DBDIR, 'reference_data.db'), 'w') as fh:
    fh.write('nao sou um banco')
check('4. banco ilegivel: fallback JSON, sem erro',
      R._refdata_records()[0]['SPN'], '135742')

# ── 5. o cronômetro do share (era o freio): só TELEMETRIA na leitura DB-only ─
# (HANDOFF §389; endurecido em 2026-09-02) A leitura lenta continua armando a
# janela — mas ela agora é só o silenciador do AVISO no log: com a leitura
# DB-only não existe mais modo só-JSON, e o banco CONTINUA respondendo com o
# cronômetro armado. É a diferença entre "trocar de fonte em silêncio" (o
# comportamento antigo, que servia o JSON) e "avisar que está lento".
import time as _t
from apps.pages import duck_read as DR
os.rename(os.path.join(DBDIR, 'reference_data.db'),
          os.path.join(DBDIR, 'reference_data.db.quebrado'))
os.rename(os.path.join(DBDIR, 'reference_data.db.fora'),
          os.path.join(DBDIR, 'reference_data.db'))
check('5. antes do cronometro, o banco responde',
      DR.refdata_rows() is not None)
DR._freio_mede(DR._FREIO_LIMIAR + 1.0, 'x.db')          # leitura "lenta"
check('5. leitura lenta ARMA a janela do aviso', DR._freio_armado())
check('5. janela armada: table_rows SEGUE respondendo pelo banco',
      DR.refdata_rows() is not None)
check('5. janela armada: o leitor de cima segue servindo pelo BANCO',
      R._refdata_records()[0]['SPN'], '135742')
DR._freio['ate'] = _t.monotonic() - 1                    # expira
check('5. janela expirada: o banco segue respondendo',
      DR.refdata_rows() is not None)
check('5. leitura rapida NAO arma',
      (DR._freio_mede(0.0, 'x.db'), DR._freio_armado())[1], False)

# ── 6. a cura que NAO cura entra em QUARENTENA ──────────────────────────────
# No share do JPM a conversao falha com `IO Error: Could not move file: Access
# is denied` e NAO passa numa segunda tentativa. Sem quarentena, toda leitura
# do dia pagava a fila do espelho + a conversao inteira + o segundo `_ler` e
# caia no JSON do mesmo jeito — e ainda enfileirava uma retentativa que
# atravancava a cura da leitura seguinte. Uma tela que abre oito arquivos-dia
# pagava isso oito vezes: era o Summary que nao terminava de carregar.
DIA = os.path.join(TMP, 'cache', 'new deals', 'NDF', 'Commodities', '2026', '06',
                   '20260618_ndfcomm.json')
R._atomic_write_json(DIA, [{'Deal': 'Q1'}])
M.flush(20)
check('6. antes de quebrar, o dia vem do BANCO', DR.day_payload(DIA), [{'Deal': 'Q1'}])

tentativas = []
_sync_real, _notify_real = M.convert_sync, M.notify_write
# A conversao "roda" e nao converte. O aviso ASSINCRONO tambem e calado: a
# thread do espelho converteria o arquivo por tras, e o que se testa aqui e a
# leitura que continua batendo num banco que nao cura.
M.convert_sync = lambda *a, **k: (tentativas.append(a[0] if a else None), True)[1]
M.notify_write = lambda *a, **k: None
# Escrita CRUA de proposito: o funil `_atomic_write_json` avisa o espelho, e a
# thread dele converteria o arquivo por fora — o que se quer aqui e justamente
# o banco ficando DEFASADO com a cura falhando.
with open(DIA, 'w', encoding='utf-8') as fh:
    fh.write(json.dumps([{'Deal': 'Q2'}], ensure_ascii=False))
DR._cura_falhou.clear()
check('6. a primeira leitura tenta curar e cai no JSON',
      (DR.day_payload(DIA), len(tentativas)), (None, 1))
check('6. a segunda NAO tenta de novo — quarentena',
      (DR.day_payload(DIA), len(tentativas)), (None, 1))
check('6. e o arquivo esta marcado', DR._cura_em_quarentena(DIA), True)
check('6. quem cai aqui ainda LE, pelo JSON',
      DR.day_records(DIA), [{'Deal': 'Q2'}])

DR._cura_falhou[DIA] = _t.monotonic() - 1     # a janela expira
check('6. janela expirada: tenta curar de novo',
      (DR.day_payload(DIA), len(tentativas)), (None, 2))

# O DISJUNTOR: a marca por arquivo nao basta quando o share recusa a escrita,
# porque ai TODA conversao falha e uma tela que abre dez arquivos-dia pagaria
# dez curas — cada uma ate o timeout do `convert_sync`. Passadas
# `_CURA_FALHAS_SEGUIDAS` falhas, a quarentena vale para qualquer arquivo.
OUTRO = os.path.join(TMP, 'cache', 'new deals', 'NDF', 'Commodities', '2026', '06',
                     '20260617_ndfcomm.json')
R._atomic_write_json(OUTRO, [{'Deal': 'R1'}])
M.flush(20)
DR._cura_falhou.clear()
DR._cura_geral.update({'ate': 0.0, 'seguidas': 0})
with open(OUTRO, 'w', encoding='utf-8') as fh:
    fh.write(json.dumps([{'Deal': 'R2'}], ensure_ascii=False))
tentativas[:] = []
check('6. a primeira falha ainda tenta o arquivo dela',
      (DR.day_payload(OUTRO), len(tentativas)), (None, 1))
check('6. o disjuntor NAO abriu com uma falha so', DR._cura_geral['ate'] > _t.monotonic(), False)
with open(DIA, 'w', encoding='utf-8') as fh:
    fh.write(json.dumps([{'Deal': 'Q3'}], ensure_ascii=False))
DR._cura_falhou.pop(DIA, None)
check('6. a segunda falha, em OUTRO arquivo, abre o disjuntor',
      (DR.day_payload(DIA), len(tentativas), DR._cura_geral['ate'] > _t.monotonic()),
      (None, 2, True))
# Um TERCEIRO arquivo, nunca tentado, ja nasce em quarentena — e e isso que
# tira o timeout de 30s de cada um dos dez arquivos da tela.
TERCEIRO = os.path.join(TMP, 'cache', 'new deals', 'NDF', 'Commodities', '2026', '06',
                        '20260616_ndfcomm.json')
with open(TERCEIRO, 'w', encoding='utf-8') as fh:
    fh.write(json.dumps([{'Deal': 'S1'}], ensure_ascii=False))
check('6. com o disjuntor aberto, arquivo NOVO nem tenta',
      (DR.day_payload(TERCEIRO), len(tentativas)), (None, 2))
check('6. e ele ainda LE, pelo JSON', DR.day_records(TERCEIRO), [{'Deal': 'S1'}])

M.convert_sync, M.notify_write = _sync_real, _notify_real
DR._cura_falhou.clear()
DR._cura_geral.update({'ate': 0.0, 'seguidas': 0})
M.notify_write(DIA)
M.flush(20)
check('6. curado de verdade, o banco volta a responder', DR.day_payload(DIA), [{'Deal': 'Q3'}])
check('6. e o sucesso LIMPA a marca', DR._cura_em_quarentena(DIA), False)
check('6. o sucesso tambem zera a contagem do disjuntor', DR._cura_geral['seguidas'], 0)

# ── 6b. OCUPADO nao e DEFASADO: disputa nao cura nem poe em quarentena ───────
# O teto do permit/da trava e o "used by another process" da instancia vizinha
# sao banco INTEGRO com outro dono neste instante. Tratados como defasados,
# custavam 30 s de `convert_sync` reconvertendo o que estava certo — e a marca
# de quarentena por cima. Agora: uma retentativa curta e o JSON desta vez.
from apps.pages import database_access as _DAx             # noqa: E402
OCUP = os.path.join(TMP, 'cache', 'new deals', 'NDF', 'Commodities', '2026', '06',
                    '20260612_ndfcomm.json')
R._atomic_write_json(OCUP, [{'Deal': 'OC-1'}])
M.flush(20)
check('6b. antes, o banco responde', DR.day_payload(OCUP), [{'Deal': 'OC-1'}])
DR.day_memo_forget()
tentativas = []
_sync_real = M.convert_sync
M.convert_sync = lambda *a, **k: (tentativas.append(a[0] if a else None), True)[1]
_dr_real = DR.duckdb_read
_chamadas = []


def _ocupado(path, **kw):
    _chamadas.append(os.path.basename(str(path)))
    raise _DAx.DatabaseLockTimeout(str(path), 'read', 0.1)


DR.duckdb_read = _ocupado
DR._ocupado_aviso['ate'] = 0.0
DR._cura_falhou.clear()
DR._cura_geral.update({'ate': 0.0, 'seguidas': 0})
check('6b. banco ocupado: cai no JSON SEM curar',
      (DR.day_payload(OCUP), len(tentativas)), (None, 0))
check('6b. com UMA retentativa antes de desistir', _chamadas.count('Commodities.db'), 2)
# Disputa perdida marca o banco: dentro da janela o banco NEM e tentado (era
# 5 s + 0,3 s + 5 s por ARQUIVO enquanto a vizinha convertia por minutos).
_chamadas[:] = []
check('6b. dentro da janela de OCUPADO o banco nem e tentado',
      (DR.day_payload(OCUP), len(_chamadas)), (None, 0))
check('6b. a janela e configuravel e curta', 0 < DR._OCUPADO_JANELA <= 300)
check('6b. e sem marcar quarentena', DR._cura_em_quarentena(OCUP), False)
check('6b. quem cai aqui ainda LE, pelo JSON', DR.day_records(OCUP), [{'Deal': 'OC-1'}])
_chamadas[:] = []
check('6b. o cadastro (table_rows) segue a mesma regra',
      (DR.refdata_rows() if os.path.isfile(os.path.join(TMP, 'RefData.json')) else None) is None
      and len(tentativas) == 0)
DR.duckdb_read = _dr_real
M.convert_sync = _sync_real
DR.ocupado_forget()                    # a janela passou
check('6b. passada a disputa, o banco volta a responder', DR.day_payload(OCUP), [{'Deal': 'OC-1'}])
check('6b. e a leitura que deu certo limpa a marca', DR._ocupado_marcado('cache/new deals/NDF/Commodities.db'), False)
# O teto de espera das leituras do espelho e CURTO e vale so para LEITURA.
check('6b. o teto curto e configuravel e cobre so a leitura',
      DR._LEITURA_TETO is not None and DR._LEITURA_TETO <= 15)

# ── 7. JSON AUSENTE: o banco responde sozinho ───────────────────────────────
# A leitura e DB-only e o JSON e o meio de ESCRITA (§4). Exigir o arquivo para
# LER era exigir o meio de escrita: com o dia no banco e o JSON fora do disco a
# tela vinha vazia ("No data available"), e o log nao dizia nada. Sem o JSON nao
# ha manifest a conferir — nem cura possivel, porque o conversor le o JSON —,
# entao serve-se o que o banco tem, que e a unica fonte que restou.
SEMJ = os.path.join(TMP, 'cache', 'new deals', 'NDF', 'Commodities', '2026', '06',
                    '20260614_ndfcomm.json')
R._atomic_write_json(SEMJ, [{'Deal': 'SJ-1'}, {'Deal': 'SJ-2'}])
M.flush(20)
check('7. com o JSON, o banco ja respondia', DR.day_payload(SEMJ), [{'Deal': 'SJ-1'}, {'Deal': 'SJ-2'}])
DR._sem_json_avisado.clear()
os.remove(SEMJ)
check('7. SEM o JSON, o banco responde igual',
      DR.day_payload(SEMJ), [{'Deal': 'SJ-1'}, {'Deal': 'SJ-2'}])
check('7. e o funil do daycache tambem (mtime/size = 0)',
      R._day_json(SEMJ, 0, 0), [{'Deal': 'SJ-1'}, {'Deal': 'SJ-2'}])
check('7. o aviso sai UMA vez por arquivo', SEMJ in DR._sem_json_avisado)
# Sem JSON e sem tabela no banco nao ha dado nenhum — e isso e a verdade, nao
# um erro: `None`, como qualquer outro caminho que nao pode responder.
NADA = os.path.join(TMP, 'cache', 'new deals', 'NDF', 'Commodities', '2026', '06',
                    '20260613_ndfcomm.json')
check('7. sem JSON e sem tabela, None', DR.day_payload(NADA), None)

# ── 8. a VARREDURA: nenhum leitor de fonte volta a abrir o JSON como caminho ─
#  A fase 3 diz que a LEITURA e servida so pelos bancos e que o JSON e o meio de
#  ESCRITA. Ainda assim, trinta leitores tinham ficado para tras — cada um com o
#  seu `with open(...) as fh: json.load(fh)` — e o defeito nao aparece na dev,
#  onde `DATA_DIR` e a pasta do codigo e os dois lados batem sempre. Na instancia
#  eles liam o SHARE por fora do banco: sem o farol do `database_access`, sem a
#  cura, sem o memo — e uma tela lenta sem nada no log dizendo por que.
#
#  A assercao e por FUNCAO: cada uma tem de citar o `duck_read`. `open`/`json.load`
#  CONTINUAM permitidos dentro delas, porque a emergencia (espelho desligado nos
#  testes, conversao que falhou, payload-objeto) e parte do contrato — o que nao
#  pode e o JSON ser o PRIMEIRO caminho.
#
#  O que NAO entra nesta lista, e por que: o read-modify-write da escrita (os 26
#  do New Deals, os persist, os claims), os payloads-OBJETO que o banco nao
#  reconstroi (as tres recons, o MtM, o Accrual, os templates do File
#  Interpreter) e os `meta`/`status`/`recipients`, que sao dicts — para todos
#  eles o `dataset_records` devolve `None` de proposito.
import ast as _ast
import io as _io

_MIGRADOS = [
    # (arquivo, funcao)                                          o que ele le
    ('apps/pages/athena_api.py', '_api_link_rows'),              # api-links
    ('apps/pages/cgd_docs.py', '_stage_map'),                    # cgd-stage
    ('apps/pages/manual_conf.py', '_mapping_rows'),              # os da esteira
    ('apps/pages/manual_conf.py', '_anbima_holidays'),           # calendario
    ('apps/pages/recon_cgd.py', '_mapping_rows'),
    ('apps/pages/recon_cgd.py', '_feriados'),
    ('apps/pages/recon_fxo.py', '_mapping_rows'),
    ('apps/pages/recon_payrec.py', '_mapping_rows'),
    ('apps/pages/recon_payrec.py', '_gdt_map'),
    ('apps/pages/otc_emails.py', '_ndf_pdf_set'),
    ('apps/pages/otc_emails.py', '_cpdetails'),                  # CounterpartyDetails
    ('apps/pages/precificador/calendario.py', '_arquivo_do_calendario'),
    ('apps/pages/precificador/calendario.py', '_feriados_do_arquivo'),
    ('apps/pages/features/boxscan/queries.py', 'refdata_by_accronym'),
    ('apps/pages/features/boxscan/queries.py', 'subjacente_index'),
    ('apps/pages/features/quotes/infra/persistence.py', 'active_by_class'),
    ('apps/pages/features/mtm/infra/mappers.py', '_mtm_load_hyb_mapping'),
    ('apps/pages/features/cognos/queries.py', '_cog_collect'),
    ('apps/pages/features/deals_monitor/queries.py', '_ndm_monitor_snapshot'),
    ('apps/pages/features/mdea/infra/persistence.py', 'rebook_rows'),
    ('apps/pages/features/mdea/infra/persistence.py', 'day_deals'),
    ('apps/pages/features/mt300/infra/persistence.py', 'load_day'),
    ('apps/pages/features/pcx/queries.py', 'rows_at'),
    ('apps/pages/features/pending_confirmation/entrypoint.py',
     'api_pending_confirmation_snapshot'),
    ('apps/pages/features/ndf_summary/entrypoint.py', 'api_ndf_summary_cards'),
    ('apps/pages/features/intrag/queries.py', '_find_intrag_ndf_entry'),
    ('apps/pages/features/intrag/queries.py', '_find_intrag_opt_entry'),
    ('apps/pages/features/intrag/queries.py', '_find_intrag_dce_opt_entry'),
    ('apps/pages/features/intrag/queries.py', '_find_intrag_swap_entry'),
    ('apps/pages/features/intrag/entrypoint.py', 'api_intrag_ndf'),
    ('apps/pages/features/intrag/entrypoint.py', 'api_intrag_option'),
    ('apps/pages/features/intrag/entrypoint.py', 'api_intrag_swap'),
    ('apps/pages/routes.py', '_vanilla_verification_lines'),
    ('apps/pages/platform/new_deals.py', '_ndf_comm_ter_lines'),
]
# Os dois finders do New Deals varrem a arvore inteira, entao vao pelo FUNIL
# `_day_json` (DB-only E memoizado por (mtime, tamanho)) — um `day_records` por
# arquivo seria uma abertura de banco por dia, que e a armadilha do §428.
_PELO_FUNIL = [
    ('apps/pages/platform/new_deals.py', '_find_ndf_deal_in_cache'),
    ('apps/pages/platform/new_deals.py', '_find_generic_nd_deal'),
]


def _corpo(rel, nome):
    caminho = os.path.join(ROOT, rel)
    if not os.path.isfile(caminho):
        return None
    origem = _io.open(caminho, encoding='utf-8').read()
    linhas = origem.splitlines()
    for no in _ast.walk(_ast.parse(origem)):
        if isinstance(no, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and no.name == nome:
            return '\n'.join(linhas[no.lineno - 1:(no.end_lineno or no.lineno)])
    return None


_sem_db = []
for rel, nome in _MIGRADOS:
    corpo = _corpo(rel, nome)
    if corpo is None or 'duck_read' not in corpo:
        _sem_db.append('%s:%s' % (rel.split('/')[-1], nome))
check('8. os %d leitores migrados citam o duck_read' % len(_MIGRADOS), _sem_db, [])

_sem_funil = []
for rel, nome in _PELO_FUNIL:
    corpo = _corpo(rel, nome)
    if corpo is None or '_day_json' not in corpo:
        _sem_funil.append('%s:%s' % (rel.split('/')[-1], nome))
check('8. os finders do New Deals vao pelo funil _day_json', _sem_funil, [])

# O `duck_read` e a UNICA porta de leitura de calendario: sem `calendar_rows`,
# cada um dos seis leitores de feriado voltaria a montar a sua.
check('8. o duck_read expoe a leitura de calendario',
      all(hasattr(DR, n) for n in ('calendar_rows', 'calendar_dates', 'calendar_registry')))
# E a tela de Holidays DELEGA a ela, em vez de ter a segunda copia.
_hol = _corpo('apps/pages/features/holidays/infra/persistence.py', '_load_holidays_db')
check('8. a tela de Holidays delega ao duck_read.calendar_rows',
      bool(_hol) and 'duck_read.calendar_rows' in _hol)


print()
if fails:
    print('FAILED: %d check(s)' % len(fails))
    sys.exit(1)
print('all ok')
sys.exit(0)
