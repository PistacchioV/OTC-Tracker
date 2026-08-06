"""Reconciliação de FXO: DPOSICAO (posição B3/CETIP) × Athena (EOD FXO).

Porte do script que a mesa rodava na mão. O que este teste prende é o que se
perde num porte e não dá erro nenhum — sai um número errado, ou uma linha some:

  1. **a base âncora**. Só a nossa conta e só câmbio. A conta chega ora como
     texto ora como número conforme quem gravou o arquivo, e testar só um dos
     dois faz a linha sumir da recon inteira sem aviso.

  2. **a chave do match**. `CETIP-` e `CETIP_` são o mesmo identificador escrito
     de dois jeitos; sem normalizar, a operação sai órfã. E o `DealID` tem
     PRIORIDADE sobre o `MatchingDealID` — sem ela a mesma operação casa duas
     vezes e o desempate vira sorte.

  3. **a perna interna**. `INVERT DIRECTION = No` renomeia sempre; `= Yes` só
     entra quando Ctpty E JPM Dir estão os dois NOK, que é a assinatura da perna
     espelhada. Aplicar a segunda sempre inverteria a direção de operações
     certas — e um Buy virado em Sell numa recon é pior do que a divergência.

  4. **os tipos de comparação**. Número em formato BR (1.234,56), tolerância de
     0,67 no prêmio, data AAAAMMDD de um lado e ISO do outro. Cada um desses,
     lido errado, produz NOK em campo que estava certo.

  5. **'Sem match' vencendo 'NOK'**. Sem a outra ponta, os onze status dão NOK de
     uma vez; contar isso como divergência de campo esconde o que houve.

  6. **o contrato com a página**: as colunas vêm do servidor, e o `nok_por_campo`
     é o que diz QUAL campo quebrou numa tabela de 38 colunas.

Não encosta em dado real: as duas bases são construídas aqui, os cadastros vão
para um diretório temporário e nada de rede é chamado.
"""
import io
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import pandas as pd                                              # noqa: E402
from apps.pages import recon_fxo as R                            # noqa: E402

fails = []


def check(label, got, exp):
    ok = got == exp
    print(('  ok  ' if ok else ' FAIL ') + label + ('' if ok else '\n        got=%r\n        exp=%r' % (got, exp)))
    if not ok:
        fails.append(label)


# ── Cadastros de teste, num diretório próprio ────────────────────────────────
TMP = tempfile.mkdtemp(prefix='fxo-map-')
R._MAPPINGS_DIR = TMP

LAWTON = 'LAWTON MULTIMERCADO EXCLUSIVO FUNDO DE INVESTIMENTO - LABAY LAWTON'
GEM = 'BCO J.P. MORGAN S.A. 2768 - GEM BR - EXPENSES & CASH MGMT'


def write_map(key, rows):
    with io.open(os.path.join(TMP, '%s.json' % key), 'w', encoding='utf-8') as fh:
        json.dump(rows, fh, ensure_ascii=False)


# O Counterparty → CNPJ sai do REFERENCE DATA, não de um cadastro próprio: ele já
# é a fonte de quem é cada contraparte, e uma segunda lista dos mesmos clientes
# envelheceria sozinha. Aqui ele é substituído por linhas sintéticas.
R._refdata_rows = lambda: [
    {'COUNTERPARTY': 'Açúcar   Brasil  S.A.', 'TAX ID': '01.234.567/0001-89',
     'FX CASH ACCRONYM': 'ACUBRA', 'SPN': '9001'},
]
write_map('fxo-internal-cpty', [
    {'ATHENA NAME': LAWTON, 'CETIP CODE': 'INTRAGLAWTONFDO', 'INVERT DIRECTION': 'No'},
    {'ATHENA NAME': GEM, 'CETIP CODE': 'INTRAGLAWTONFDO', 'INVERT DIRECTION': 'Yes'},
])

# ── A DPOSICAO sintética ─────────────────────────────────────────────────────
# O bloco de fixing é POSICIONAL (colunas 80..148), então o arquivo precisa ser
# largo de verdade: as nomeadas primeiro e enchimento até passar do índice 148.
DP_COLS = [
    'Parte (Conta)', 'Classe do ativo subjacente', 'Combinação de operações',
    'Código IF', 'Posição da Parte', 'Tipo de Opção',
    'CPF/CNPJ Cliente Contraparte', 'Contraparte (Nome simplificado)',
    'Quantidade', 'Valor financeiro total do prêmio', 'Strike (valor)',
    'Data Registro', 'Data Vencimento', 'Média Asiática',
    'Data de fixing do ativo subjacente',
]
DP_COLS += ['filler_%d' % i for i in range(len(DP_COLS), 160)]
FIX1, FIX2 = 80, 81          # dentro do bloco 80..148


def dp_row(**kw):
    row = dict.fromkeys(DP_COLS, '')
    row.update({'Parte (Conta)': '73760009', 'Classe do ativo subjacente': 'TAXAS DE CAMBIO'})
    row.update(kw)
    return row


def make_dposicao(rows):
    """Escreve o `.OPC` como a B3 entrega: separado por TAB, latin-1."""
    out = ['\t'.join(DP_COLS)]
    for r in rows:
        out.append('\t'.join(str(r.get(c, '')) for c in DP_COLS))
    return io.BytesIO(('\n'.join(out) + '\n').encode('latin-1'))


AT_COLS = ['DealID', 'MatchingDealID', 'OptionStyle', 'TransactionType', 'OptionType',
           'MatchingCounterpartyName', 'CounterpartyName', 'Quantity', 'Premium',
           'Strike', 'TradeDate', 'SettlementDate', 'FixingDate', 'FirstFixingDate']


def at_row(**kw):
    row = dict.fromkeys(AT_COLS, '')
    row.update(kw)
    return row


def make_athena(rows):
    out = ['|'.join(AT_COLS)]
    for r in rows:
        out.append('|'.join(str(r.get(c, '')) for c in AT_COLS))
    return io.BytesIO(('\n'.join(out) + '\n').encode('utf-8'))


def run(dp_rows, at_rows):
    df_dp = R.read_dposicao(make_dposicao(dp_rows))
    df_at = R.read_athena(make_athena(at_rows))
    return R.reconcile(df_dp, df_at)


print('== 1. a base âncora: a nossa conta, só câmbio ==')
rows, counts, _w = run(
    [dp_row(**{'Combinação de operações': 'CETIP_1'}),
     dp_row(**{'Combinação de operações': 'CETIP_2', 'Parte (Conta)': '73760009.0'}),
     dp_row(**{'Combinação de operações': 'CETIP_3', 'Parte (Conta)': '99999999'}),
     dp_row(**{'Combinação de operações': 'CETIP_4', 'Classe do ativo subjacente': 'TAXAS DE JUROS'})],
    [at_row(DealID='CETIP_%d' % i) for i in range(1, 5)])
check('a conta como texto entra', 'CETIP_1' in [r['Combinação de operações'] for r in rows], True)
check('a conta como número entra', 'CETIP_2' in [r['Combinação de operações'] for r in rows], True)
check('outra conta fica de fora', 'CETIP_3' in [r['Combinação de operações'] for r in rows], False)
check('outra classe de ativo fica de fora',
      'CETIP_4' in [r['Combinação de operações'] for r in rows], False)
check('   sobram duas', counts['total'], 2)

print('\n== 2. a chave: CETIP- ≡ CETIP_, e o DealID na frente ==')
rows, counts, _w = run(
    [dp_row(**{'Combinação de operações': 'CETIP-77'})],
    [at_row(DealID='CETIP_77')])
check('o traço casa com o underline', counts['no_match'], 0)
check('   e a chave sai normalizada', rows[0]['Combinação de operações'], 'CETIP_77')

# A MESMA chave existe como DealID de uma operação e como MatchingDealID de
# outra. A linha do DealID é que vale.
rows, counts, _w = run(
    [dp_row(**{'Combinação de operações': 'K1', 'Quantidade': '100'})],
    [at_row(DealID='K1', Quantity='100'), at_row(DealID='Z9', MatchingDealID='K1', Quantity='777')])
check('o DealID ganha do MatchingDealID', rows[0]['Match'], 'DealID')
check('   e o valor vem da linha certa', rows[0]['ATH Amt'], '100')
check('   sem duplicar a operação', counts['total'], 1)

# Quando a chave NÃO existe em DealID nenhum, o MatchingDealID é usado.
rows, counts, _w = run(
    [dp_row(**{'Combinação de operações': 'K2'})],
    [at_row(DealID='Z1', MatchingDealID='K2')])
check('sem DealID, o MatchingDealID atende', rows[0]['Match'], 'MatchingDealID')

print('\n== 3. a perna interna ==')
# (a) INVERT = No: renomeia sempre.
rows, _c, _w = run(
    [dp_row(**{'Combinação de operações': 'L1', 'Contraparte (Nome simplificado)': 'INTRAGLAWTONFDO',
               'Posição da Parte': 'TITULAR'})],
    [at_row(DealID='L1', CounterpartyName=LAWTON, TransactionType='Buy')])
check('LAWTON vira o código da CETIP', rows[0]['ATH Client Ext'], 'INTRAGLAWTONFDO')
check('   e o status fecha', rows[0]['Status Ctpty'], 'OK')

# (b) INVERT = Yes com os DOIS status NOK: espelha e renomeia.
rows, _c, _w = run(
    [dp_row(**{'Combinação de operações': 'G1', 'Contraparte (Nome simplificado)': 'INTRAGLAWTONFDO',
               'Posição da Parte': 'TITULAR'})],
    [at_row(DealID='G1', CounterpartyName=GEM, TransactionType='Sell')])
check('a perna GEM inverte a direção', rows[0]['ATH JPM Dir'], 'Buy')
check('   e o status de direção fecha', rows[0]['Status JPM Dir'], 'OK')
check('   e a contraparte também', rows[0]['Status Ctpty'], 'OK')
check('   a linha inteira fica OK', rows[0]['Status'], 'OK')

# (c) INVERT = Yes com a direção JÁ certa: NÃO pode inverter.
rows, _c, _w = run(
    [dp_row(**{'Combinação de operações': 'G2', 'Contraparte (Nome simplificado)': 'INTRAGLAWTONFDO',
               'Posição da Parte': 'TITULAR'})],
    [at_row(DealID='G2', CounterpartyName=GEM, TransactionType='Buy')])
check('direção certa NÃO é espelhada', rows[0]['ATH JPM Dir'], 'Buy')
check('   e a contraparte segue divergente (é o que se quer ver)',
      rows[0]['Status Ctpty'], 'NOK')

# (d) Cadastro vazio: nada é renomeado, e a tela avisa.
write_map('fxo-internal-cpty', [])
rows, _c, avisos = run(
    [dp_row(**{'Combinação de operações': 'G3', 'Contraparte (Nome simplificado)': 'INTRAGLAWTONFDO'})],
    [at_row(DealID='G3', CounterpartyName=GEM)])
check('sem cadastro, o nome da Athena fica como veio', rows[0]['ATH Client Ext'], GEM)
write_map('fxo-internal-cpty', [
    {'ATHENA NAME': LAWTON, 'CETIP CODE': 'INTRAGLAWTONFDO', 'INVERT DIRECTION': 'No'},
    {'ATHENA NAME': GEM, 'CETIP CODE': 'INTRAGLAWTONFDO', 'INVERT DIRECTION': 'Yes'},
])

print('\n== 4. os tipos de comparação ==')
# Direção, Put/Call e o de-para de CNPJ (com acento e espaço duplo no nome).
rows, _c, _w = run(
    [dp_row(**{'Combinação de operações': 'T1', 'Posição da Parte': 'LANCADOR',
               'Tipo de Opção': 'PUT', 'CPF/CNPJ Cliente Contraparte': '01234567000189',
               'Quantidade': '1.500.000,00', 'Valor financeiro total do prêmio': '7.415,50',
               'Strike (valor)': '5,4321', 'Data Registro': '20260701',
               'Data Vencimento': '20260901', 'Média Asiática': '',
               'Data de fixing do ativo subjacente': '20260828'})],
    [at_row(DealID='T1', TransactionType='Sell', OptionType='Put on USD',
            MatchingCounterpartyName='ACUCAR BRASIL S.A.', Quantity='-1500000',
            Premium='-7416.10', Strike='5.4321', TradeDate='2026-07-01',
            SettlementDate='2026-09-01', FixingDate='2026-08-28',
            OptionStyle='Vanilla Option')])
r = rows[0]
check('LANCADOR = Sell', (r['CET JPM Dir'], r['Status JPM Dir']), ('Sell', 'OK'))
check('Put on USD = PUT', (r['Ath_P/C'], r['Status P/C']), ('PUT', 'OK'))
check('o CNPJ vem do cadastro, com acento e espaço duplo no nome',
      (r['ATH Client Ext'], r['Status Ctpty']), ('1234567000189', 'OK'))
check('quantidade em formato BR, em valor absoluto', r['Status Amt'], 'OK')
check('prêmio dentro da tolerância de 0,67', r['Status Premium'], 'OK')
check('strike com vírgula ≡ strike com ponto', r['Status Strike'], 'OK')
check('AAAAMMDD ≡ ISO na data de registro', (r['CET TD'], r['Status TD']),
      ('01/07/2026', 'OK'))
check('   e no vencimento', r['Status VD'], 'OK')
check('europeia: o fixing é o do ativo subjacente', r['Status Fix Date'], 'OK')
check('   e não tem primeiro fixing', (r['CET 1º Fix'], r['Status 1º Fix']), ('', 'OK'))
check('Vanilla Option ≡ vazio no estilo', r['Status Asian/European'], 'OK')
check('a linha inteira fecha', r['Status'], 'OK')
# CONSEQUÊNCIA CONHECIDA: na europeia o de-para só traduz 'SIMPLES_DATAS'. Se a
# DPOSICAO escrever 'NAO' em vez de deixar em branco, a coluna acusa NOK — o
# classificador que absorveria 'NAO'/'N'/'NONE' existe no script original e foi
# deixado DESLIGADO de propósito. Se o arquivo real vier assim, é uma linha a
# acrescentar no de-para, não um conserto de código.
rows, _c, _w = run(
    [dp_row(**{'Combinação de operações': 'T3', 'Média Asiática': 'NAO'})],
    [at_row(DealID='T3', OptionStyle='Vanilla Option')])
check("um 'NAO' literal no arquivo acusaria", rows[0]['Status Asian/European'], 'NOK')

# O prêmio FORA da tolerância tem de acusar.
rows, _c, _w = run(
    [dp_row(**{'Combinação de operações': 'T2', 'Valor financeiro total do prêmio': '7.415,50'})],
    [at_row(DealID='T2', Premium='-7416.90')])
check('prêmio fora da tolerância acusa', rows[0]['Status Premium'], 'NOK')

print('\n== 5. a opção asiática: o fixing sai do cronograma ==')
rows, _c, _w = run(
    [dp_row(**{'Combinação de operações': 'A1', 'Média Asiática': 'SIMPLES_DATAS',
               'Data de fixing do ativo subjacente': '20260101',
               DP_COLS[FIX1]: '20260810', DP_COLS[FIX2]: '20260828'})],
    [at_row(DealID='A1', OptionStyle='Avg Rate Option',
            FixingDate='2026-08-28', FirstFixingDate='2026-08-10')])
r = rows[0]
check('o último fixing é a última data do cronograma',
      (r['CET Fix Date'], r['Status Fix Date']), ('28/08/2026', 'OK'))
check('o primeiro fixing é a primeira', (r['CET 1º Fix'], r['Status 1º Fix']),
      ('10/08/2026', 'OK'))
check('   e a data do ativo subjacente é ignorada na asiática',
      r['CET Fix Date'] != '01/01/2026', True)
check('Avg Rate Option = Asian dos dois lados', r['Status Asian/European'], 'OK')

print('\n== 6. sem match vence NOK ==')
rows, counts, _w = run(
    [dp_row(**{'Combinação de operações': 'X1', 'Quantidade': '10'}),
     dp_row(**{'Combinação de operações': 'X2', 'Quantidade': '10'}),
     dp_row(**{'Combinação de operações': 'X2', 'Quantidade': '10'})],
    [at_row(DealID='X2', Quantity='99')])
por_chave = {r['Combinação de operações']: r for r in rows}
check('a órfã sai como Sem match', por_chave['X1']['Status'], 'Sem match')
check('   e não como NOK, mesmo com os onze status NOK',
      por_chave['X1']['Status Amt'], 'NOK')
check('a que casou e diverge sai como NOK', por_chave['X2']['Status'], 'NOK')
check('a chave repetida é sinalizada', por_chave['X2']['Chave Duplicada'], 'Sim')
check('as contagens fecham',
      (counts['total'], counts['ok'], counts['nok'], counts['no_match'],
       counts['dup_key'], counts['match_dealid']),
      (3, 0, 2, 1, 2, 2))
check('nok_por_campo diz qual campo quebrou', counts['nok_por_campo']['Status Amt'], 3)

print('\n== 7. o contrato com a página ==')
check('a primeira coluna é o Status', R.COLUMNS[0], 'Status')
check('as três colunas por campo estão todas na lista',
      [c for m in R.CAMPOS for c in (m['rot_dp'], m['rot_at'], m['rot_st'])
       if c not in R.COLUMNS], [])
check('as colunas de status batem com os campos',
      R.STATUS_COLS, [m['rot_st'] for m in R.CAMPOS])
check('nenhum rótulo repetido', len(set(R.COLUMNS)), len(R.COLUMNS))
check('o payload vazio já traz as colunas', R.load_last('')['columns'], R.COLUMNS)
check('   e uma data inválida não estoura', R.load_last('lixo')['counts']['total'], 0)
# A página monta a tabela com o que o servidor manda: se o motor ganhar um campo
# e a lista não crescer, a coluna nova aparece vazia e sem erro.
HTML = io.open(os.path.join(ROOT, 'apps/templates/pages/reconciliation-fxo.html'),
               encoding='utf-8', errors='ignore').read()
check('a tela usa as colunas do servidor', 'payload.columns' in HTML, True)
check('   e não tem uma lista própria', 'CET JPM Dir' in HTML, False)
check('a linha de filtro entra nas duas theads',
      HTML.count('.append($row.clone())'), 2)
check('   e a clonada e a que recebe o evento',
      "closest('.dt-scroll-head, .dataTables_scrollHead')" in HTML, True)
# O `.card` do tema declara fundo, borda e raio e e carregado DEPOIS do <style>
# da pagina: sem !important o cartao volta a branco com moldura cinza.
import re as _re
bloco = _re.search(r'#fxo-page \.fxo-widget \{([^}]*)\}', HTML, _re.S).group(1)
for decl in ('border-radius', 'border', 'padding'):
    check('%s do card leva !important' % decl,
          _re.search(_re.escape(decl) + r':[^;]*!important', bloco) is not None, True)

check('o card de Total usa o mesmo gradiente das outras telas',
      'linear-gradient(135deg, #0066cc 0%, #34369b 100%)' in HTML, True)

print('\n== 8. leituras do arquivo ==')
# 'Texto para Colunas' quebra o CABEÇALHO junto com o dado. Quebrar só o dado
# deixaria N colunas novas com um nome só, e a segunda em diante viraria KeyError.
df = pd.DataFrame({'A;B;C': ['1;2;3', '4;5;6'], 'D': ['x', 'y']})
out = R._text_to_columns(df, 'A;B;C', ';')
check('o cabeçalho é partido junto com o dado', list(out.columns), ['A', 'B', 'C', 'D'])
check('   e os valores vão para as colunas certas', out.iloc[0].tolist(), ['1', '2', '3', 'x'])

# Linha de dados com MAIS colunas que o cabeçalho: é o cronograma de fixing, que
# segue à direita sem título. Truncar ali perderia as datas da asiática.
raw = io.BytesIO(('a\tb\n1\t2\t3\t4\n').encode('latin-1'))
df = R.read_dposicao(raw)
check('as colunas sem cabeçalho ganham nome genérico',
      list(df.columns), ['a', 'b', 'extra_1', 'extra_2'])
check('   e o dado excedente é preservado', df.iloc[0].tolist(), ['1', '2', '3', '4'])

print('\n== 9. o caminho e o endereço do dia ==')
check('a pasta do dia segue o padrão da B3',
      R.dposicao_path('2026-08-04').replace('\\', '/').endswith(
          '2026/08. August/04/73760_260804_DPOSICAO.OPC'), True)
check('a data entra no CAMINHO do relatório da Athena',
      '/2026-08-04/' in R.athena_url('2026-08-04'), True)
check('   e não vira parâmetro de query', '?' in R.athena_url('2026-08-04'), False)
try:
    R._parse_date('nao e data')
    check('data inválida falha cedo', 'passou', 'ValueError')
except ValueError as e:
    check('data inválida falha cedo', 'Data inválida' in str(e), True)

shutil.rmtree(TMP, ignore_errors=True)
print('\n' + ('FALHOU: ' + ', '.join(fails) if fails else 'TUDO OK'))
sys.exit(1 if fails else 0)
