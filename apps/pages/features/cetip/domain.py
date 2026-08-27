# -*- coding: utf-8 -*-
"""As regras puras do Save CETIP Files — o catálogo de comportamento por
arquivo (o que vai por e-mail, o que vira JSON, o que o BACC recorta), o
reconhecimento do nome do arquivo (padrão × data) e os nomes de saída.

Puro: nada aqui importa `routes`, Flask ou disco. O logger vem do `logging`
direto — é o MESMO objeto que o `routes.log` (mesmo nome), sem a dependência.
A regra VIVA de quais arquivos existem é o cadastro `cetip-files`, lido em
`queries._cetip_rules`; este catálogo diz o que fazer com cada um deles.
"""
import logging
import os
import re

log = logging.getLogger('otc_tracker')


_CETIP_RECIPIENT_KEYS = ('ss_to', 'cem_to', 'bacc_to', 'hub_to')


_CETIP_BEHAVIOUR = {
    'NDF Position (DPOSICAO C21)': {},
    'SWAP Position (DPOSICAO-SWAP)': {
        'attach_sales_support': True,      # SWAP position also e-mailed to Sales Support
        'attach_hub': True,                # BACC HUB EQT MO — arquivo INTEIRO, só renomeado
        # BACC: Participante (coluna D) × Contraparte (coluna H) — os nomes vêm do
        # `_B3_SWAP_HEADERS['swap_position']`, que é o cabeçalho padrão deste
        # arquivo (ele chega SEM cabeçalho).
        'attach_bacc': True,
        'bacc': {'has_header': False,
                 'parte':       {'column': ['participante'], 'index': 3},
                 'contraparte': {'column': ['contraparte'],  'index': 7}},
        'json': {'category': 'Swap', 'has_header': False, 'header_key': 'swap_position',
                 # de-dup: Conta Parte (coluna D = "Participante")
                 'filter': {'column': ['participante'], 'index': 3,
                            'allowed': ['73760009', '04880006']}}},
    'Option Position (OPC DPOSICAO)': {
        'attach_cem_latam': True,          # this .OPC file is e-mailed to CEM Latam BA
        'attach_sales_support': True,      # .OPC position also e-mailed to Sales Support
        'attach_bacc': True,
        'attach_hub': True,                # BACC HUB EQT MO — arquivo INTEIRO, só renomeado
        # 'parte (conta)' é SUBSTRING de 'contraparte (conta)': o `avoid` é o que
        # impede o lado da parte de casar com a coluna da contraparte quando ela
        # vem antes no cabeçalho — sem ele o filtro compararia a mesma coluna duas
        # vezes e deixaria passar linha de conta externa.
        'bacc': {'has_header': True,
                 'parte':       {'column': ['parte (conta)', 'parte(conta)', 'parte'],
                                 'index': 4, 'avoid': 'contraparte'},
                 'contraparte': {'column': ['contraparte (conta)', 'contraparte(conta)',
                                            'contraparte'], 'index': 7}},
        'json': {'category': 'Option', 'has_header': True,
                 # de-dup: keep only our side (Parte/conta = coluna E)
                 'filter': {'column': ['parte (conta)', 'parte(conta)', 'parte'], 'index': 4,
                            'allowed': ['73760009']}}},
    'Option Movement (OPC DMOVIMENTO)': {},
    'NDF Movement (DMOVIMENTO C21)': {},
    'SWAP Movement (DMOVIMENTO-SWAP)': {},
    'SWAP Flow (DFLUXO_SWAP)': {
        # Este é o único dos quatro do BACC que não vai para mais ninguém: ele não
        # tem `attach_sales_support`, então o BACC é a razão de ele ser anexado.
        'attach_bacc': True,
        'bacc': {'has_header': False,
                 'parte':       {'column': ['código conta cetip parte',
                                            'codigo conta cetip parte',
                                            'conta cetip parte'],
                                 'index': 2, 'avoid': 'contraparte'},
                 'contraparte': {'column': ['código conta cetip contraparte',
                                            'codigo conta cetip contraparte',
                                            'conta cetip contraparte'], 'index': 5}},
        'json': {'category': 'Swap', 'has_header': False, 'header_key': 'swap_fluxo',
                 # de-dup: Conta Parte (coluna C = "Código Conta Cetip Parte")
                 'filter': {'column': ['código conta cetip parte', 'codigo conta cetip parte',
                                       'conta cetip parte'], 'index': 2,
                            'allowed': ['73760009', '04880006']}}},
    'SWAP Premium Agenda (DAGENDAPREMIOS)': {
        'attach_hub': True,                # BACC HUB EQT MO — arquivo INTEIRO, só renomeado
        'json': {'category': 'Swap', 'has_header': False, 'header_key': 'swap_premio',
                 # de-dup: Conta da Parte (coluna D = "Parte")
                 'filter': {'column': ['parte'], 'index': 3,
                            'allowed': ['73760009', '04880006']}}},
    'SWAP Indexers (INDEXADORESSWAP_VCP)': {
        # Not a position file: after saving, its rows refresh the VCP indexer
        # reference JSON (see _cetip_update_vcp_json), used by the Swap
        # Characteristics page. A=Qualification ID, B=Description, C=Additional
        # Description, D=Level 1 Classification, E=Status
        # (Habilitado→Active / Bloqueado→Inactive).
        'vcp_update': True},
    'Operations (DOPERACOES)': {
        # DOPERACOES ships WITH a header row (first line); data from the 2nd line —
        # like the Save-Settlements "operações" file. Keep only our accounts
        # (Conta = col B) and the derivative title types (Tipo Titulo = col J).
        'json': {'category': 'Operations', 'has_header': True,
                 'filters': [
                     {'column': ['conta'], 'index': 1,
                      'allowed': ['73760009', '04880006']},
                     {'column': ['tipo titulo', 'tipo título'], 'index': 9,
                      'allowed': ['TER', 'SWAP', 'OPC'], 'match': 'text'},
                 ]}},
    'COE (DRESUMOEMISSOR-COE)': {},
    'Accelerator Agent (MID DAGENTEACELERADOR)': {},
    # Posição de estratégia (MID). Existe para o BACC HUB EQT MO: ele não vira
    # JSON e não alimenta rotina nenhuma — é salvo na pasta do dia como os outros
    # e anexado inteiro. Sem a linha aqui e no cadastro, a rotina não conheceria o
    # arquivo e o e-mail sairia com três anexos em vez de quatro.
    #
    # O nome do TIPO é o que está no cadastro do time — `SWAP (Strategy)`, e não
    # um nome descritivo inventado aqui: `_cetip_rules` une os dois pela coluna
    # TYPE, e um rótulo que não bate deixa a regra sem cadastro, ou seja, sem
    # efeito nenhum, em silêncio.
    'SWAP (Strategy)': {
        'attach_hub': True},               # BACC HUB EQT MO — arquivo INTEIRO, só renomeado
    'NDF Position (DPOSICAO-TER)': {
        'attach_sales_support': True,      # .TER position also e-mailed to Sales Support
        'attach_bacc': True,
        'attach_hub': True,                # BACC HUB EQT MO — arquivo INTEIRO, só renomeado
        'bacc': {'has_header': True,
                 'parte':       {'column': ['código da parte', 'codigo da parte'],
                                 'index': 1, 'avoid': 'contraparte'},
                 'contraparte': {'column': ['código da contraparte',
                                            'codigo da contraparte'], 'index': 3}},
        'json': {'category': 'NDF', 'has_header': True,
                 # de-dup: keep only our side (Código da Parte = coluna B)
                 'filter': {'column': ['código da parte', 'codigo da parte'], 'index': 1,
                            'allowed': ['73760009', '04880006']}}},
    'SIC Contract Position (DPOSCONTRATOSIC)': {
        'attach_sales_support': True},   # this file is e-mailed to Sales Support
    'Comitente Registry (DCADCOMITENTES)': {},
    # Salvo e mais nada, DE PROPÓSITO — como os outros `{}` daqui. A entrada
    # vazia não é decoração: `_cetip_behaviour_for` avisa em WARNING quando um
    # TYPE do cadastro não casa com nada, justamente para um `attach_*` perdido
    # não passar calado (§269). Sem a linha, o CGD acenderia esse aviso todo dia
    # por estar certo, e um aviso que sempre aparece deixa de ser lido.
    'CGD (NET)': {},
}


_CETIP_DATE_TOKEN = 'YYMMDD'


def _cetip_split_pattern(pattern):
    """`'CETIP21_YYMMDD_DPOSICAO-SWAP'` → `(8, '_dposicao-swap')`.

    Devolve (offset da data, final do nome em minúsculas) ou None se o padrão
    não tiver o `YYMMDD`. A extensão é descartada: o cadastro guarda o nome sem
    `.TXT` (é o formato que o usuário digita) e a comparação é feita contra o
    nome do arquivo sem extensão, o que faz `.TXT` e `.txt` casarem sozinhos.
    """
    s = os.path.splitext(str(pattern or '').strip())[0]
    i = s.upper().find(_CETIP_DATE_TOKEN)
    if i < 0:
        return None
    return i, s[i + len(_CETIP_DATE_TOKEN):].lower()


def _cetip_apply_date(pattern, yymmdd):
    """Troca o `YYMMDD` do padrão pela data (case-insensitive, todas as ocorrências)."""
    return re.sub(_CETIP_DATE_TOKEN, yymmdd, str(pattern or ''), flags=re.I)


def _cetip_make_matcher(pattern, label):
    """Predicado de match do padrão, ou None se o padrão for inválido.

    Casa pelo FINAL do nome (sem extensão) mais 6 dígitos na posição que o
    padrão indica. O prefixo literal ('CETIP21_', 'TER_') NÃO é comparado, só
    o seu tamanho: os nomes de origem nunca foram confirmados com a B3 (era uma
    pendência aberta desde a §27) e exigir o prefixo poderia parar de salvar um
    arquivo que hoje funciona. Quando o prefixo do arquivo não bate com o do
    cadastro fica um aviso no log — dá o diagnóstico sem o risco.
    """
    parts = _cetip_split_pattern(pattern)
    if not parts:
        return None
    idx, tail = parts
    head = os.path.splitext(str(pattern or '').strip())[0][:idx].lower()

    def _match(name_lower):
        stem = os.path.splitext(name_lower)[0]
        if tail and not stem.endswith(tail):
            return False
        date = stem[idx:idx + 6]
        if len(date) != 6 or not date.isdigit():
            return False
        if head and stem[:idx] != head:
            log.warning('[cetip] %s: prefixo do arquivo (%r) difere do cadastro (%r) — '
                        'salvando mesmo assim', label, stem[:idx], head)
        return True

    return _match


def _cetip_paren_key(label):
    """`'NDF Position (DPOSICAO-TER)'` → `'DPOSICAO-TER'`; sem parênteses, o
    rótulo inteiro. É o NOME DO ARQUIVO da CETIP dentro do rótulo — a parte que
    identifica de que arquivo a linha fala, ao contrário do prefixo descritivo,
    que é como o time escolheu chamá-lo."""
    m = re.search(r'\(([^)]*)\)\s*$', str(label or ''))
    return (m.group(1) if m else str(label or '')).strip().upper()


_CETIP_BEHAVIOUR_BY_PAREN = {_cetip_paren_key(k): v for k, v in _CETIP_BEHAVIOUR.items()}


def _cetip_behaviour_for(label):
    """Comportamento da linha do cadastro, pelo TYPE — e, se ele não bater, pelo
    NOME DO ARQUIVO entre parênteses.

    O rótulo é digitado na tela, e o prefixo dele é DESCRIÇÃO. A posição de termo
    já se chamou `Term Position (DPOSICAO-TER)` aqui e `NDF Position
    (DPOSICAO-TER)` no cadastro do time — TER é termo, e a mesa chama termo de
    NDF, então quem renomeou tinha razão. Com a junção só pelo rótulo inteiro,
    essa linha perdia o comportamento por completo: o arquivo continuava sendo
    salvo (SOURCE e DEST vêm do cadastro), mas não virava JSON, não ia para o
    Sales Support e não entrava no recorte do BACC — **sem erro nenhum**, porque
    `dict.get` de uma chave que não existe devolve um dicionário vazio, que é
    exatamente o que uma linha sem comportamento parece. Foi assim que o `.TER`
    sumiu do e-mail do intragrupo.

    Os rótulos daqui já foram alinhados com os da mesa (`Term …` virou `NDF …`
    nos dois arquivos de termo), mas o fallback FICA: ele não existe para aquele
    caso, existe porque uma coluna de texto numa tela convida a ser reescrita, e
    o próximo rename não pode custar outra caçada.

    O que identifica o arquivo é o que está ENTRE PARÊNTESES, e ele é único nas
    17 entradas (`check_cetip_bacc.py` prova). O prefixo pode mudar à vontade.

    Rótulo que não casa por nenhum dos dois é **avisado no log**: a linha existe
    de propósito (há tipos sem comportamento nenhum, que só são salvos), mas um
    `attach_*` que deixa de valer por causa de um parêntese perdido não pode
    passar calado uma segunda vez.
    """
    label = str(label or '').strip()
    if label in _CETIP_BEHAVIOUR:
        return _CETIP_BEHAVIOUR[label]
    achado = _CETIP_BEHAVIOUR_BY_PAREN.get(_cetip_paren_key(label))
    # WARNING, e não INFO: na instância do time o log de módulo só sai a partir de
    # WARNING, e um aviso que ninguém lê é o mesmo que não avisar.
    if achado is not None:
        log.warning('[cetip] %r não é um TYPE conhecido; o comportamento foi resolvido '
                    'pelo nome do arquivo entre parênteses (%r). Renomeie a linha no '
                    '/mapping para o TYPE do código, ou ignore — o efeito é o mesmo.',
                    label, _cetip_paren_key(label))
        return achado
    log.warning('[cetip] %r não tem comportamento registrado: o arquivo é SALVO, mas '
                'não vira JSON nem é anexado a e-mail nenhum. Se ele deveria ir para '
                'alguma área, o TYPE não está batendo com o código.', label)
    return {}


_CETIP_BACC_ACCOUNTS = frozenset(('00041007',      # Lawton   00041.00-7
                                  '73760009',      # Banco    73760.00-9
                                  '85398005'))     # Atacama  85398.00-5


def _cetip_acct_key(v):
    """Conta comparável: só dígitos, completada com zeros à esquerda até 8.

    O Lawton é `00041.00-7`; um exportador que trate a conta como NÚMERO devolve
    `41007`, que sem o zfill não casaria com nada — e o recorte sairia vazio sem
    erro nenhum."""
    d = re.sub(r'\D', '', str(v or ''))
    return d.zfill(8) if 0 < len(d) <= 8 else d


def _cetip_txt_name(src_path):
    """Nome do anexo: o do arquivo salvo, com `.txt` no fim — e um só.

    O `.txt` é ACRESCENTADO, não substituído: as extensões da CETIP (`.CETIP21`,
    `.OPC`, `.TER`) não são associadas a programa nenhum e o anexo não abre com um
    duplo clique, mas é pelo nome inteiro que o outro lado reconhece QUAL arquivo
    é aquele — trocar `.OPC` por `.txt` apagaria justamente essa parte.

    Quando o DEST cadastrado já termina em `.txt` (o `SWAP (Strategy)` é assim),
    não ganha um segundo: `…_MID.txt.txt` é um nome que ninguém escreveu de
    propósito, e o casamento do outro lado é pelo nome."""
    nome = os.path.basename(src_path)
    return nome if nome.lower().endswith('.txt') else nome + '.txt'
