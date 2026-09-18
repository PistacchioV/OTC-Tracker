#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_cetip_dominio.py — o cadastro de DOMINIOS da B3 no Save CETIP Files.

O arquivo `CETIP_AAMMDD_CADASTROCURVASMOEDASFEEDERDOMINIOS.txt` (Arquivos
Publicos) passa a ser salvo pela rotina e, depois de salvo, atualiza a base
`Dominio.json` — o mesmo desenho do INDEXADORESSWAP_VCP sobre a `VCP.json`.

O que este teste prende:

  1. o cadastro conhece o arquivo (seed) E o `upgrade` leva a linha para a
     instancia que JA TEM o `cetip-files.json` — sem ele o seed nunca chega la
     (§6) e a rotina simplesmente nao salva o arquivo, sem erro nenhum;
  2. a regra de comportamento casa pelo nome entre PARENTESES, que e como o
     `_cetip_behaviour_for` junta cadastro e catalogo;
  3. a CHAVE do upsert e o QUADRUPLO (grupo, subgrupo, tipo IF, identificador)
     e nao o identificador sozinho: o mesmo id vale para varios `Codigo TipoIF`
     (o IGP-M e o 104 em CCB, CCE, CCI...) e chaveado so pelo id o upsert
     reescreveria a linha de um instrumento com a descricao de outro;
  4. o identificador e comparado com o MESMO tipo dos dois lados: a base guarda
     float (`14056.0`) e o arquivo e texto (`14056`) — comparados como vem,
     NADA casa e a tabela inteira entra de novo a cada rodada;
  5. a `Data Inclusao` NAO entra na base (pedido da mesa);
  6. `Classificação`, `MAKER` e `CHECKER` da linha existente sobrevivem — sao
     da mesa, nao do arquivo — e linha da base ausente do arquivo fica intacta.

Roda em tmp; nao encosta na base real.
"""
import io
import json
import os
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', '/tmp/otc-share')
os.environ['OTC_DISABLE_SCHEDULERS'] = '1'

from apps.pages import routes as R                                      # noqa: E402
from apps.pages.features.cetip import domain as CD                      # noqa: E402
from apps.pages.features.cetip.infra import persistence as CP           # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label
          + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


PAREN = 'CADASTROCURVASMOEDASFEEDERDOMINIOS'

# O arquivo, como a B3 o publica: cabecalho, ';' e a data de inclusao no fim.
ARQUIVO = (
    'Nome do Grupo;Nome do Subgrupo;Codigo TipoIF;Identificador Qualificacao;'
    'Descricao Qualificacao;Data Inclusao;\n'
    'CARTEIRA DE INVESTIMENTO;Espécie do Instrumento Financeiro;ACI;14056;'
    'Ação de Empresa Fechada;20190628\n'
    'CARTEIRA DE INVESTIMENTO;Espécie do Instrumento Financeiro;ACI;14057;'
    'Cota de Empresa Ltda;20190628\n'
    # O MESMO id em dois tipos de instrumento — é o caso que quebra o upsert
    # chaveado só pelo identificador.
    'CURVAS;Tipo do Indicador do Índice (VCP);CCB;104;IGP-M;20190628\n'
    'CURVAS;Tipo do Indicador do Índice (VCP);CCE;104;IGP-M REVISADO;20190628\n'
)


print('== 1. o cadastro conhece o arquivo ==')
seed = {CD._cetip_paren_key(r['TYPE']) for r in R._CETIP_FILES_SEED}
check('o seed tem a linha', PAREN in seed, True)
linha = next(r for r in R._CETIP_FILES_SEED if CD._cetip_paren_key(r['TYPE']) == PAREN)
check('SOURCE com o prefixo CETIP_ (a B3 publica assim, sem o 21)',
      linha['SOURCE'], 'CETIP_YYMMDD_' + PAREN)
check('DEST idem, com .txt', linha['DEST'], 'CETIP_YYMMDD_' + PAREN + '.txt')

print('\n== 2. o upgrade leva a linha para quem JA TEM o cadastro ==')
# Seed só roda com o arquivo AUSENTE (§6): sem upgrade, a instância do time
# nunca veria a linha nova e a rotina não salvaria o arquivo, calada.
antigo = [dict(r) for r in R._CETIP_FILES_SEED
          if CD._cetip_paren_key(r['TYPE']) != PAREN]
check('o cadastro antigo nao tem a linha',
      PAREN in {CD._cetip_paren_key(r['TYPE']) for r in antigo}, False)
subido = R._cetip_files_upgrade(antigo)
check('e o upgrade a acrescenta',
      PAREN in {CD._cetip_paren_key(r['TYPE']) for r in subido}, True)
check('sem duplicar o que ja estava', len(subido), len(R._CETIP_FILES_SEED))
check('rodar de novo nao duplica',
      len(R._cetip_files_upgrade(subido)), len(R._CETIP_FILES_SEED))
# O rótulo é digitado na tela: o upgrade casa pelo nome entre parênteses, que é
# o que identifica o ARQUIVO, e não pelo prefixo descritivo.
renomeado = [dict(r) for r in R._CETIP_FILES_SEED]
for r in renomeado:
    if CD._cetip_paren_key(r['TYPE']) == PAREN:
        r['TYPE'] = 'Base de Dominios (%s)' % PAREN
check('rotulo reescrito na tela nao vira linha duplicada',
      len(R._cetip_files_upgrade(renomeado)), len(R._CETIP_FILES_SEED))

print('\n== 3. a regra de comportamento casa ==')
check('o catalogo tem a entrada',
      CD._cetip_behaviour_for('Domain Registry (%s)' % PAREN).get('dominio_update'), True)
check('e casa mesmo com o prefixo reescrito',
      CD._cetip_behaviour_for('Base de Dominios (%s)' % PAREN).get('dominio_update'), True)

print('\n== 4. a chave e o QUADRUPLO, nao o identificador ==')
k1 = CP._dominio_key('CURVAS', 'Tipo do Indicador do Índice (VCP)', 'CCB', '104')
k2 = CP._dominio_key('CURVAS', 'Tipo do Indicador do Índice (VCP)', 'CCE', '104')
check('mesmo id, tipos de IF diferentes -> chaves diferentes', k1 == k2, False)
check('e cega a caixa e a espaco',
      CP._dominio_key('curvas', ' Tipo do Indicador do Índice (VCP) ', 'ccb', '104'), k1)

print('\n== 5. o identificador vale o mesmo dos dois lados ==')
check('float da base vira o inteiro', CP._dominio_id(14056.0), '14056')
check('texto do arquivo idem', CP._dominio_id('14056'), '14056')
check('e os dois sao a MESMA chave', CP._dominio_id(14056.0), CP._dominio_id('14056'))
check('vazio nao vira chave', CP._dominio_id(None), '')
check('id nao numerico passa como veio', CP._dominio_id('A-12'), 'A-12')

print('\n== 6. o upsert, com a base num tmp ==')
tmp = tempfile.mkdtemp(prefix='cetip-dominio-')
base = os.path.join(tmp, 'Dominio.json')
arq = os.path.join(tmp, 'CETIP_260917_%s.txt' % PAREN)
io.open(arq, 'w', encoding='latin-1').write(ARQUIVO)
# A base ANTES: uma linha que o arquivo traz (com a mesa tendo preenchido
# Classificação/MAKER) e uma que ele NAO traz.
ANTES = [
    {'STATUS': 'ACTIVE', 'Nome do Grupo': 'CARTEIRA DE INVESTIMENTO',
     'Nome do Subgrupo': 'Espécie do Instrumento Financeiro', 'Codigo TipoIF': 'ACI',
     'Identificador Qualificacao': 14056.0, 'Descricao Qualificacao': 'NOME ANTIGO',
     'Classificação': 'RENDA VARIAVEL', 'MAKER': 'A111111', 'CHECKER': 'B222222'},
    {'STATUS': 'ACTIVE', 'Nome do Grupo': 'CADASTRO DA MESA',
     'Nome do Subgrupo': 'Feito a mao', 'Codigo TipoIF': 'XXX',
     'Identificador Qualificacao': 99999.0, 'Descricao Qualificacao': 'SO NA BASE',
     'Classificação': None, 'MAKER': None, 'CHECKER': None},
]
_gravado = {}
R.DOMINIO_JSON = base
_atomic_real = R._atomic_write_json
R._atomic_write_json = lambda caminho, dados: _gravado.update({caminho: dados})
from apps.pages import data_store as _store                              # noqa: E402
_isfile_real, _read_real = _store.isfile, _store.read
_store.isfile = lambda c, *a, **k: True if c == base else _isfile_real(c, *a, **k)
_store.read = lambda c, *a, **k: ANTES if c == base else _read_real(c, *a, **k)
try:
    saida = CP._cetip_update_dominio_json(arq)
    check('devolveu o caminho da base', saida, base)
    rows = _gravado.get(base) or []
    por = {CP._dominio_key(r['Nome do Grupo'], r['Nome do Subgrupo'],
                           r['Codigo TipoIF'], r['Identificador Qualificacao']): r
           for r in rows}
    check('4 linhas do arquivo + a que so existe na base', len(rows), 5)

    k_aci = CP._dominio_key('CARTEIRA DE INVESTIMENTO', 'Espécie do Instrumento Financeiro',
                            'ACI', '14056')
    atualizada = por[k_aci]
    check('a descricao veio do ARQUIVO',
          atualizada['Descricao Qualificacao'], 'Ação de Empresa Fechada')
    check('e a Classificação da mesa sobreviveu',
          atualizada['Classificação'], 'RENDA VARIAVEL')
    check('o MAKER/CHECKER tambem',
          (atualizada['MAKER'], atualizada['CHECKER']), ('A111111', 'B222222'))
    check('o identificador nao virou texto (a base e numerica)',
          isinstance(atualizada['Identificador Qualificacao'], float), True)

    check('linha da base AUSENTE do arquivo ficou intacta',
          por[CP._dominio_key('CADASTRO DA MESA', 'Feito a mao', 'XXX', '99999')]
          ['Descricao Qualificacao'], 'SO NA BASE')

    # O caso que quebra a chave por id: o MESMO 104 em dois tipos de IF.
    ccb = por[CP._dominio_key('CURVAS', 'Tipo do Indicador do Índice (VCP)', 'CCB', '104')]
    cce = por[CP._dominio_key('CURVAS', 'Tipo do Indicador do Índice (VCP)', 'CCE', '104')]
    check('as DUAS linhas do id 104 entraram',
          (ccb['Descricao Qualificacao'], cce['Descricao Qualificacao']),
          ('IGP-M', 'IGP-M REVISADO'))
    check('linha nova nasce ACTIVE', ccb['STATUS'], 'ACTIVE')
    check('e sem Classificação/MAKER/CHECKER inventados',
          (ccb['Classificação'], ccb['MAKER'], ccb['CHECKER']), (None, None, None))

    print('\n== 7. a Data Inclusao NAO entra na base ==')
    colunas = set()
    for r in rows:
        colunas.update(r.keys())
    check('nenhuma coluna de data', sorted(c for c in colunas if 'inclus' in c.lower()), [])
    check('as colunas sao as da base', sorted(colunas),
          sorted(['STATUS', 'Nome do Grupo', 'Nome do Subgrupo', 'Codigo TipoIF',
                  'Identificador Qualificacao', 'Descricao Qualificacao',
                  'Classificação', 'MAKER', 'CHECKER']))
    check('e a data nao vazou para a descricao',
          [r for r in rows if '20190628' in str(r.get('Descricao Qualificacao'))], [])

    print('\n== 8. o texto do arquivo (cp1252) chega inteiro ==')
    # cp1252 e nao latin-1: o travessao e as aspas curvas vivem na faixa
    # 0x80-0x9F, que em latin-1 sao caracteres de CONTROLE invisiveis.
    arq2 = os.path.join(tmp, 'CETIP_260918_%s.txt' % PAREN)
    io.open(arq2, 'w', encoding='cp1252').write(
        'Nome do Grupo;Nome do Subgrupo;Codigo TipoIF;Identificador Qualificacao;'
        'Descricao Qualificacao;Data Inclusao;\n'
        'CURVAS;Ind\u00edce;CCB;777;IGP-M \u2013 REVIS\u00c3O \u201cA\u201d;20260918\n')
    _gravado.clear()
    ANTES[:] = []
    CP._cetip_update_dominio_json(arq2)
    nova = (_gravado.get(base) or [{}])[0]
    check('travessao, acento e aspas curvas intactos',
          nova.get('Descricao Qualificacao'), 'IGP-M \u2013 REVIS\u00c3O \u201cA\u201d')
    check('e o subgrupo acentuado tambem', nova.get('Nome do Subgrupo'), 'Ind\u00edce')

    print('\n== 9. espaco de preenchimento do arquivo nao entra na base ==')
    arq3 = os.path.join(tmp, 'CETIP_260919_%s.txt' % PAREN)
    io.open(arq3, 'w', encoding='cp1252').write(
        'Nome do Grupo;Nome do Subgrupo;Codigo TipoIF;Identificador Qualificacao;'
        'Descricao Qualificacao;Data Inclusao;\n'
        'CURVAS  ;  Indice;CCB;  778 ;   COM E REVENDAS PROD. AGRICOLAS   ;20260919\n')
    _gravado.clear()
    ANTES[:] = []
    CP._cetip_update_dominio_json(arq3)
    n3 = (_gravado.get(base) or [{}])[0]
    check('a descricao vai sem o preenchimento',
          n3.get('Descricao Qualificacao'), 'COM E REVENDAS PROD. AGRICOLAS')
    check('e o identificador tambem', n3.get('Identificador Qualificacao'), 778.0)

    print('\n== 10. rodar de novo nao duplica ==')
    _gravado.clear()
    ANTES[:] = []
    CP._cetip_update_dominio_json(arq)
    primeira = list(_gravado.get(base) or [])
    _gravado.clear()
    ANTES[:] = primeira
    CP._cetip_update_dominio_json(arq)
    check('a base tem o mesmo tamanho', len(_gravado.get(base) or []), len(primeira))
    check('e o arquivo tem 4 linhas de dado', len(primeira), 4)
finally:
    R._atomic_write_json = _atomic_real
    _store.isfile, _store.read = _isfile_real, _read_real

print('\n== 11. o arquivo vai ANEXO no e-mail de stage 1 (OTC Ops) ==')
# O e-mail de stage 1 nunca levou anexo: os anexos desta rotina eram todos do
# stage 2 (Sales Support, CEM Latam, BACC, HUB). Este e o primeiro, a pedido da
# mesa — e o que se prende aqui e que ele sai com o arquivo SALVO, e que a
# tabela do e-mail continua listando tudo que foi salvo.
check('a regra pede o anexo de OTC Ops',
      CD._cetip_behaviour_for('Domain Registry (%s)' % PAREN).get('attach_ops'), True)
# Nenhum outro arquivo da rotina ganha esse anexo sem alguem decidir.
outros = sorted(k for k, v in CD._CETIP_BEHAVIOUR.items() if v.get('attach_ops'))
check('e so ele', outros, ['Domain Registry (%s)' % PAREN])

import datetime as _dt
from datetime import timezone as _tz, timedelta as _td
from run import app                                                     # noqa: E402
from apps.pages.features.cetip.infra import mail as CM                  # noqa: E402

e2e = tempfile.mkdtemp(prefix='cetip-e2e-')
R.CETIP_SOURCE_ROOT = os.path.join(e2e, 'origem')
R.CETIP_DEST_ROOT = os.path.join(e2e, 'destino')
_src = os.path.join(R.CETIP_SOURCE_ROOT, '2026', '09. September', '17')
os.makedirs(_src, exist_ok=True)
_nome = 'CETIP_260917_%s.txt' % PAREN
io.open(os.path.join(_src, _nome), 'w', encoding='cp1252').write(ARQUIVO)

enviados = []
_send_real = CM._send_cetip_email
CM._send_cetip_email = lambda *a, **k: (enviados.append((a, k)) or True)
R.DOMINIO_JSON = os.path.join(e2e, 'Dominio.json')
_gravado.clear()
R._atomic_write_json = lambda caminho, dados: (_gravado.update({caminho: dados})
                                               if caminho == R.DOMINIO_JSON
                                               else _atomic_real(caminho, dados))
_store.isfile = lambda c, *a, **k: False if c == R.DOMINIO_JSON else _isfile_real(c, *a, **k)
_store.read = _read_real
try:
    cl = app.test_client()
    with cl.session_transaction() as ss:
        ss['authenticated'] = True
        ss['user_sid'] = 'T000000'
        ss['user_name'] = 'T'
        ss['session_expires_at'] = (_dt.datetime.now(tz=_tz.utc) + _td(hours=8)).isoformat()
    res = cl.post('/api/control-panel/cetip-settlement',
                  json={'date': '2026-09-17', 'send_email': True}).get_json()
    check('a rotina rodou', res.get('success'), True)
    check('e salvou o arquivo', [x['dest'] for x in (res.get('saved') or [])], [_nome])
    check('a base de dominios saiu atualizada', len(_gravado.get(R.DOMINIO_JSON) or []), 4)
    check('um e-mail de stage 1 foi disparado', len(enviados), 1)
    _args, _kw = enviados[0]
    check('para o Brazil OTC Ops', list(_args[0]), [R.CETIP_OTC_OPS_EMAIL])
    anexos = [os.path.basename(x) for x in (_kw.get('attachments') or [])]
    check('com o arquivo ANEXO', anexos, [_nome])
    check('e o anexo e o SALVO, nao o da origem',
          (_kw.get('attachments') or [''])[0].startswith(R.CETIP_DEST_ROOT), True)
    check('a tabela do e-mail continua listando o que foi salvo',
          [x['dest'] for x in (_args[6] or [])], [_nome])
finally:
    CM._send_cetip_email = _send_real
    R._atomic_write_json = _atomic_real
    _store.isfile, _store.read = _isfile_real, _read_real

print('')
if fails:
    print('FALHAS (%d): %s' % (len(fails), ', '.join(fails)))
    sys.exit(1)
print('TUDO OK')
