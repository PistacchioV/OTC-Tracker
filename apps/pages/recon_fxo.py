# -*- coding: utf-8 -*-
"""FXO Reconciliation — DPOSICAO (posição B3/CETIP) × Athena (sistema interno).

Porte do script `recon_fxo.py` que a mesa rodava na mão. A regra de comparação é
a mesma, campo a campo; o que mudou é como as bases entram e como o resultado
sai.

O que saiu do script, e por quê:

  * **O Excel.** O resultado agora é a própria página: os cards contam os status
    e a tabela mostra as linhas, com o NOK pintado na célula. O arquivo era um
    passo a mais entre rodar e olhar, e cada rodada deixava um arquivo diferente
    na pasta de alguém.

  * **Os dois XLSX intermediários.** A Parte A baixava a Athena e importava a
    DPOSICAO para dois `.xlsx` em `test\\`, que a Parte B relia. Aqui as bases
    entram direto em memória. Isso também matou a aba `OPC_260702_DPOSICAO`
    cravada no código — um nome de aba de UM dia específico, que só funcionava
    porque havia um resolvedor por semelhança atrás dele.

  * **Os caminhos do Desktop de quem escreveu.** A DPOSICAO vem da MESMA raiz da
    rotina Save CETIP Files (`CETIP_DEST_ROOT`), e o endereço da Athena está
    cadastrado em `api-links` (uso **Recon FXO**) como todo endpoint do sistema.

  * **Os dois de-para que estavam no código.** O Counterparty → CNPJ vinha de uma
    planilha no OneDrive de uma pessoa: agora sai do **Reference Data**
    (`lookup_cnpj`, indexando COUNTERPARTY / FX CASH ACCRONYM / SPN pelo TAX ID),
    e não de um cadastro próprio — um de-para paralelo seria uma segunda lista
    dos mesmos clientes, mantida à mão. As contrapartes internas (GEM, LAWTON)
    eram constantes e viraram cadastro (`fxo-internal-cpty`), editável em
    /mapping e válido no próximo run, sem restart.

Chave do match: `Combinação de operações` (DPOSICAO) × `DealID` (Athena), com
`MatchingDealID` como segunda tentativa e SÓ para as chaves que não existem em
DealID — a prioridade é do DealID, senão uma mesma operação casaria duas vezes —
e SÓ quando aquele MatchingDealID existe do lado da B3. O MatchingDealID é o
identificador da perna do outro lado, e o que não tem registro da CETIP
correspondente é descartado antes do merge: entrando, viraria um `Unmatched
Athena` fantasma, a mesma operação repetida pela chave da perna oposta.

Os `warnings` do payload são ESTRUTURADOS — `{'code': ..., parâmetros}` —, e não
a frase pronta. A frase é montada na tela, no idioma da aplicação; um texto já
escrito aqui apareceria em português para quem está com o app em inglês, que foi
exatamente o que aconteceu. Resultados em cache guardam o que era frase, então a
tela aceita os dois formatos e imprime a string legada como veio.
"""

import io
import json
import logging
import os
import re
import threading
import unicodedata
from datetime import datetime

import pandas as pd

# A raiz do share sai do Config, como todo destino de rede do app: na branch de
# produção ela é o UNC, e um literal `I:\` aqui manteria ESTA recon presa à
# letra mapeada enquanto o resto do app já fala com o servidor.
from apps.pages.data_paths import data_dir, data_path, data_write, mapping_file, mapping_write
from apps.config import Config

_LOG = logging.getLogger(__name__)

_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = data_dir()
_MAPPINGS_DIR = data_write('mappings')
_CACHE_DIR = data_write('cache', 'reconciliation', 'fxo')

# Raiz das posições CETIP — a MESMA da rotina Save CETIP Files e da recon de
# Comitente, pelo mesmo env var. Duas raízes seriam duas verdades sobre onde o
# arquivo do dia está.
_CETIP_BASE = os.getenv(
    'CETIP_DEST_ROOT',
    os.path.join(Config.SHARED_DRIVE_ROOT, 'Confirmation', 'Derivativos',
                 'OTC Tracker', 'CETIP Files', 'Position Files'))

# Nome do arquivo de posição de opções, com a data no padrão da B3 (AAMMDD).
_DPOSICAO_NAME = '73760_{yymmdd}_DPOSICAO.OPC'

# Endereço do relatório EOD de FXO — usado só quando o cadastro `api-links` não
# tem a linha do Recon FXO. É o mesmo que estava no script.
_ATHENA_FXO_FALLBACK = ('http://athena-reports.jpmchase.net:8080/bob-reports/'
                        'YYYY-MM-DD/EOD/GEM_OFFICIAL_TRD/FXOEODReport/'
                        'brazil_fxo_trades.csv')
_API_USE = 'Recon FXO'
_API_PRODUCT = 'FXO'

_MONTH_EN = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May',
             6: 'June', 7: 'July', 8: 'August', 9: 'September', 10: 'October',
             11: 'November', 12: 'December'}

# ── Filtros da base âncora ───────────────────────────────────────────────────
FILTRO_PARTE_CONTA = '73760009'
FILTRO_CLASSE = 'TAXAS DE CAMBIO'

# ── Colunas ──────────────────────────────────────────────────────────────────
COL_DP_PARTE_CONTA = 'Parte (Conta)'
COL_DP_CLASSE = 'Classe do ativo subjacente'
COL_DP_CHAVE = 'Combinação de operações'
COL_DP_CODIGO_IF = 'Código IF'
COL_DP_MEDIA_ASIAT = 'Média Asiática'
COL_DP_FIX_ADATIVO = 'Data de fixing do ativo subjacente'

COL_AT_CHAVE = 'DealID'
COL_AT_MATCHING = 'MatchingDealID'
COL_AT_OPTIONSTYLE = 'OptionStyle'
COL_AT_CPTY_NAME = 'CounterpartyName'
# As colunas que dizem QUEM É A CONTRAPARTE da linha da Athena. As duas entram no
# corte por `USE = Disregard` (ver `ignored_cpty_names`): a perna interna chega ao
# relatório ora como dona da linha (`CounterpartyName`), ora como contraparte da
# linha do outro lado da MESMA operação intragrupo (`MatchingCounterpartyName`) —
# e é esta segunda que a coluna ATH Cntpy da tela mostra, porque é dela que
# `deriv_cntpy_ath` parte.
COLS_AT_CPTY_DISREGARD = ('MatchingCounterpartyName', COL_AT_CPTY_NAME)
COL_AT_MATCH_SPN = 'MatchingCounterpartySPN'

# Bloco de datas de fixing (colunas CC..ES da DPOSICAO, por POSIÇÃO). É onde a
# opção asiática lista as datas de verificação; ele não tem cabeçalho próprio,
# por isso o recorte é posicional.
IDX_BLOCO_FIXING_INI = 80
IDX_BLOCO_FIXING_FIM = 148
VALOR_MEDIA_ASIATICA_DATAS = 'SIMPLES_DATAS'


# =============================================================================
# Leitura das bases
# =============================================================================

def _text_to_columns(df, coluna, sep=';'):
    """Divide `coluna` pelo separador, QUEBRANDO TAMBÉM o nome do cabeçalho.

    É o 'Texto para Colunas' do Excel: ele parte a linha inteira, header
    incluído. Quebrar só os dados deixaria N colunas novas com um nome só.
    """
    idx = df.columns.get_loc(coluna)
    partes = df[coluna].astype('string').str.split(sep, expand=True)
    n = partes.shape[1]

    nomes = str(coluna).split(sep)
    if len(nomes) < n:
        nomes = nomes + ['%s_%d' % (coluna, i + 1) for i in range(len(nomes), n)]
    else:
        nomes = nomes[:n]
    partes.columns = nomes
    return pd.concat([df.iloc[:, :idx], partes, df.iloc[:, idx + 1:]], axis=1)


def read_dposicao(src):
    """Lê o `.OPC` (separado por TAB) como a Parte A do script fazia.

    Duas coisas que o arquivo faz e um `read_csv` ingênuo não sobrevive:

      1. **as linhas de dados podem ter MAIS colunas que o cabeçalho** — o
         cronograma de verificação de barreiras / média asiática continua para a
         direita sem título. Por isso o número de colunas sai do arquivo inteiro
         e as excedentes ganham nome genérico;
      2. **algumas colunas trazem vários campos separados por `;`**, no dado e no
         próprio cabeçalho.

    Tudo entra como texto (`dtype=str`): zeros à esquerda de conta e CNPJ são
    parte do valor, e a conversão vem depois, por campo.
    """
    if hasattr(src, 'read'):
        raw = src.read()
        if isinstance(raw, bytes):
            raw = raw.decode('latin-1', errors='replace')
        linhas = raw.splitlines(True)
        buf = io.StringIO(''.join(linhas))
    else:
        with open(src, 'r', encoding='latin-1') as fh:
            linhas = fh.readlines()
        buf = io.StringIO(''.join(linhas))

    if not linhas:
        raise ValueError('Arquivo de DPOSICAO vazio.')

    ncols = max(l.count('\t') for l in linhas) + 1
    header = [c for c in linhas[0].rstrip('\n').split('\t') if c.strip() != '']
    extra = max(ncols - len(header), 0)
    names = header + ['extra_%d' % (i + 1) for i in range(extra)]

    df = pd.read_csv(buf, sep='\t', dtype=str, header=0, names=names,
                     engine='python', index_col=False)

    com_pv = [c for c in df.columns
              if (';' in str(c)
                  or df[c].astype('string').str.contains(';', na=False).any())]
    for col in com_pv:
        df = _text_to_columns(df, col, sep=';')
    _LOG.info('[recon_fxo] DPOSICAO: %d linhas, %d colunas (%d expandidas por ";")',
              len(df), len(df.columns), len(com_pv))
    return df


def read_athena(src):
    """Lê o relatório EOD de FXO (CSV separado por `|`)."""
    if isinstance(src, bytes):
        src = io.BytesIO(src)
    return pd.read_csv(src, sep='|', encoding='utf-8-sig')


def dposicao_path(ref_date):
    """`<raiz>/AAAA/MM. Month/DD/73760_AAMMDD_DPOSICAO.OPC`."""
    d = _parse_date(ref_date)
    return os.path.join(_CETIP_BASE, d.strftime('%Y'),
                        '%02d. %s' % (d.month, _MONTH_EN[d.month]),
                        d.strftime('%d'),
                        _DPOSICAO_NAME.format(yymmdd=d.strftime('%y%m%d')))


def athena_url(ref_date):
    """Endereço do relatório do dia, do cadastro `api-links`.

    Sem linha cadastrada cai no endereço histórico — a rotina existia antes do
    cadastro e deixá-la sem URL nenhuma a quebraria na primeira instância que
    ainda não abriu a tela de mappings.
    """
    d = _parse_date(ref_date)
    template = None
    try:
        from apps.pages import athena_api
        template, _ = athena_api.registered_link(_API_USE, _API_PRODUCT)
    except Exception as exc:                       # pragma: no cover - defensivo
        _LOG.debug('[recon_fxo] cadastro api-links indisponível: %s', exc)
    if not template:
        template = _ATHENA_FXO_FALLBACK
    return re.sub(r'yyyy[-/. ]?mm[-/. ]?dd', d.strftime('%Y-%m-%d'),
                  template, flags=re.I)


def _parse_date(ref_date):
    s = str(ref_date or '').strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%Y%m%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError('Data inválida: %r. Use AAAA-MM-DD.' % ref_date)


# =============================================================================
# Os dois cadastros
# =============================================================================

def _mapping_rows(key):
    """Linhas de um cadastro de /mapping, lidas do disco a cada chamada.

    Importar `routes` daqui seria circular; ler o JSON direto é o mesmo padrão de
    `athena_api._api_link_rows` e `otc_emails._ndf_pdf_set`. Ler a cada chamada é
    de propósito: edição na tela vale no próximo run, sem restart.
    """
    try:
        with open(mapping_file(key, _MAPPINGS_DIR), encoding='utf-8') as fh:
            rows = json.load(fh)
    except Exception:
        return []
    rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    # O `upgrade` é aplicado AQUI, e não só na tela de /mapping. Eram dois
    # leitores do mesmo arquivo, e este via o JSON CRU: numa instância que nunca
    # abriu o /mapping (ou abriu e não salvou), a coluna nova simplesmente não
    # existiria e a regra dela nunca valeria. É o mesmo tropeço que o cadastro da
    # esteira já custou uma vez.
    if key == 'fxo-internal-cpty':
        return internal_cpty_upgrade(rows)
    if key == 'fxo-book-disregard':
        return book_disregard_upgrade(rows)
    return rows


# A conta interna que a mesa pediu para tirar do batimento. Fica aqui, ao lado da
# regra que a usa, e é o **default do seed** — não um literal no meio do motor:
# quem manda é o cadastro, e esta constante só decide o valor inicial da coluna.
GEM_ACCOUNT = 'BCO J.P. MORGAN S.A. 2768 - GEM BR - EXPENSES & CASH MGMT'


def internal_cpty_upgrade(rows):
    """Traz a coluna `USE` para os arquivos gravados antes de ela existir.

    Roda na LEITURA — a instância que já tem o arquivo em disco nunca receberia o
    seed de outro jeito — e só preenche o que **não existe**: linha sem a chave é
    anterior à coluna, então ninguém teve como opinar sobre ela. Ela recebe
    `Consider` (o comportamento de sempre) e, no caso da conta GEM, `Disregard`,
    que é a perna interna sem par na CETIP e enchia a recon de `Unmatched
    Athena`. Com a chave presente, nada é tocado: o cadastro é de quem edita.
    """
    alvo = _nome_cru(GEM_ACCOUNT)
    for r in rows:
        if isinstance(r, dict) and 'USE' not in r:
            r['USE'] = ('Disregard' if _nome_cru(r.get('ATHENA NAME')) == alvo
                        else 'Consider')
    return rows


def lookup_cnpj():
    """Counterparty (como a Athena escreve) → CNPJ, do **Reference Data**.

    Não existe cadastro próprio para isto: o Reference Data já é a fonte de quem
    é cada contraparte, com nome, SPN e Tax ID na mesma linha. Um de-para
    paralelo seria uma segunda lista dos mesmos clientes, e envelheceria sozinho
    — todo cliente novo entraria no Reference Data e a recon continuaria sem
    casar, sem ninguém saber por quê.

    O índice aceita três chaves para a mesma linha, porque a Athena escreve a
    contraparte de três jeitos conforme o campo: a razão social, o accronym de FX
    Cash e o SPN. As três levam ao mesmo Tax ID.
    """
    mapa = {}
    for r in _refdata_rows():
        cnpj = so_digitos(r.get('TAX ID'))
        if not cnpj:
            continue
        for campo in ('COUNTERPARTY', 'FX CASH ACCRONYM', 'SPN'):
            chave = _chave_lookup(r.get(campo))
            if chave:
                mapa.setdefault(chave, cnpj)
    return mapa


def refdata_indexes():
    """(SPN → nome, CNPJ → nome), os dois só-dígitos, do Reference Data.

    É a identidade da contraparte para a recon: a Athena aponta o cliente pelo
    **MatchingCounterpartySPN** e a CETIP pelo **CNPJ**, e os dois campos levam à
    MESMA linha do Reference Data — comparar o NOME registrado dos dois lados é
    o que faz um par correto fechar mesmo com grafias diferentes nos arquivos.
    """
    por_spn, por_cnpj = {}, {}
    for r in _refdata_rows():
        nome = texto_simples(r.get('COUNTERPARTY'))
        if not nome:
            continue
        spn = so_digitos(r.get('SPN'))
        cnpj = so_digitos(r.get('TAX ID'))
        if spn:
            por_spn.setdefault(spn, nome)
        if cnpj:
            por_cnpj.setdefault(cnpj, nome)
    return por_spn, por_cnpj


_REFDATA_CACHE = {'mtime': None, 'rows': []}


def _refdata_rows():
    """As linhas do RefData.json, relidas quando o arquivo muda.

    Cache por mtime, não por processo: o Reference Data é editado dentro da
    própria aplicação, e um cache eterno faria a recon do dia seguinte continuar
    sem o cliente que alguém acabou de cadastrar.
    """
    path = data_path('RefData.json')
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return []
    if _REFDATA_CACHE['mtime'] == mtime:
        return _REFDATA_CACHE['rows']
    # DB-first (fase 3): o reference_data.db quando fresco; senão o JSON. O
    # cache por mtime fica — o mtime é a própria chave do contrato de frescor.
    try:
        from apps.pages import duck_read
        db_rows = duck_read.refdata_rows(expected_path=path)
    except Exception:                                       # noqa: BLE001
        db_rows = None
    if db_rows is not None:
        _REFDATA_CACHE['mtime'] = mtime
        _REFDATA_CACHE['rows'] = db_rows
        return db_rows
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        rows = [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
    except Exception:
        _LOG.warning('[recon_fxo] não consegui ler o Reference Data')
        rows = []
    _REFDATA_CACHE.update({'mtime': mtime, 'rows': rows})
    return rows


def internal_cpty_rules():
    """Contrapartes internas: (renomeações diretas, regras de perna espelhada).

    Uma perna interna chega à Athena com o nome da MESA (o book), não o do
    cliente, e a CETIP registra o código do fundo. Duas formas:

      * `INVERT DIRECTION = No` — só o nome muda; a renomeação vale sempre;
      * `INVERT DIRECTION = Yes` — a perna vem ESPELHADA: além do nome, o Buy/Sell
        está invertido. Essa vale só quando Ctpty **e** JPM Dir estão os dois
        NOK, que é a assinatura da perna espelhada — aplicá-la sempre inverteria
        a direção de operações que estavam certas.
    """
    diretas, espelhadas = {}, []
    for r in _mapping_rows('fxo-internal-cpty'):
        nome = str(r.get('ATHENA NAME') or '').strip()
        codigo = str(r.get('CETIP CODE') or '').strip()
        if not nome or not codigo or _linha_disregard(r):
            # `USE = Disregard` tira a linha do batimento (ver
            # `ignored_cpty_names`): renomear ou espelhar um nome que não vai
            # chegar ao match seriam duas leituras do mesmo cadastro.
            continue
        if str(r.get('INVERT DIRECTION') or '').strip().lower().startswith(('y', 's')):
            espelhadas.append((nome.upper(), codigo))
        else:
            diretas[nome.upper()] = codigo
    return diretas, espelhadas


def _linha_disregard(r):
    return str(r.get('USE') or '').strip().lower().startswith('d')


def ignored_cpty_names():
    """As contrapartes da Athena que saem ANTES do batimento.

    Coluna `USE = Disregard` no cadastro `fxo-internal-cpty` — em branco vale
    `Consider`, que é o comportamento de sempre. São pernas internas que não têm
    par na CETIP: mantidas, elas caem em `Unmatched Athena` e enchem a tela de
    quebra que não é quebra.

    O corte é ANTES do merge de propósito. Depois dele não adiantaria: o DealID
    dessas linhas já teria ocupado a chave em `base_athena_para_match` e poderia
    ter roubado o par de uma operação de verdade.

    O nome é procurado nas DUAS colunas de contraparte
    (`COLS_AT_CPTY_DISREGARD`), e não só no `CounterpartyName`. Uma operação
    intragrupo chega ao relatório pelos dois lados: numa linha a conta interna é a
    dona (`CounterpartyName`), na outra ela é a contraparte
    (`MatchingCounterpartyName`) — e é ESTA que a tela mostra na coluna
    ATH Cntpy, porque é dela que `deriv_cntpy_ath` parte. Cortando só pela
    primeira, metade do par continuava na recon como `Unmatched Athena`, com o
    nome cadastrado à vista na tela: exatamente o que o cadastro dizia para tirar.

    Não é a mesma coisa que derrubar a operação do cliente. A conta marcada
    `Disregard` é interna e a linha em que ela aparece como contraparte é a perna
    de dentro da mesma operação — o cliente está do outro lado do SEU próprio par,
    numa linha cujas duas contrapartes são ele e a mesa.
    """
    out = set()
    for r in _mapping_rows('fxo-internal-cpty'):
        if _linha_disregard(r):
            chave = _nome_cru(r.get('ATHENA NAME'))
            if chave:
                out.add(chave)
    return out


# O cadastro de exclusão é uma lista de CRITÉRIOS: até três pares
# `COLUMN n` (uma coluna do relatório, escolhida num dropdown) × `VALUE n`.
# Nada aqui fixa QUAIS colunas podem ser usadas — a lista do dropdown é uma
# conveniência da tela (`_ATHENA_FXO_COLUMNS`, no routes) e o motor aceita o
# nome que estiver cadastrado. Foi assim que o desenho anterior errou: ele
# supunha `TRADING BOOK` / `OTHER BOOK`, nomes que o relatório não tem.
_BOOK_SLOTS = (('COLUMN 1', 'VALUE 1'), ('COLUMN 2', 'VALUE 2'), ('COLUMN 3', 'VALUE 3'))
# O formato antigo, para o `upgrade` traduzir uma vez. O valor era o mesmo; o que
# estava errado era o nome da coluna, e é justamente ele que agora se escolhe.
_BOOK_LEGACY = ('TRADING BOOK', 'OTHER BOOK', 'INT/EXT')


def book_disregard_upgrade(rows):
    """Traz o cadastro de três colunas FIXAS para os pares coluna × valor.

    Roda na LEITURA, como o `internal_cpty_upgrade`: a instância que já tem o
    arquivo em disco nunca receberia o formato novo de outro jeito, e o motor lê
    esse JSON a cada run. Os VALORES são preservados; o nome da coluna vai como
    estava, porque quem sabe qual é a coluna certa do relatório é quem opera —
    e é por isso que ela virou um dropdown. Linha que já está no formato novo
    (tem `COLUMN 1`) não é tocada.
    """
    for r in rows:
        if not isinstance(r, dict) or 'COLUMN 1' in r:
            continue
        antigos = [(c, r.pop(c)) for c in _BOOK_LEGACY
                   if str(r.get(c) or '').strip()]
        for c in _BOOK_LEGACY:
            r.pop(c, None)
        for (col_k, val_k), (col, val) in zip(_BOOK_SLOTS, antigos):
            r[col_k], r[val_k] = col, val
        for col_k, val_k in _BOOK_SLOTS:
            r.setdefault(col_k, '')
            r.setdefault(val_k, '')
    return rows


def disregarded_book_rules():
    """As linhas da Athena que saem do batimento por cadastro, `fxo-book-disregard`.

    Cada linha do cadastro é uma REGRA, e a regra é uma **conjunção** de até três
    critérios `coluna = valor`: com um critério preenchido sai tudo que tem
    aquele valor naquela coluna; com dois, só o que tem os dois; com três, só o
    que tem os três. Par com coluna ou valor em branco simplesmente **não conta**
    — é o que permite escrever a regra de um critério só sem inventar coringa.

    A linha sem critério nenhum é DESCARTADA de propósito: sem nada a exigir ela
    casaria com o relatório inteiro, e a linha vazia criada por engano na tela
    apagaria o lado da Athena da recon sem dizer nada.

    Os VALORES são comparados por `_nome_cru` (cego a caixa, espaço e
    pontuação): `BRL_FXO LAWTON` e `BRL FXO LAWTON` são a mesma coisa escrita de
    dois jeitos.
    """
    regras = []
    for r in _mapping_rows('fxo-book-disregard'):
        regra = []
        for col_k, val_k in _BOOK_SLOTS:
            col = str(r.get(col_k) or '').strip()
            val = _nome_cru(r.get(val_k))
            if col and val:
                regra.append((col, val))
        if regra:
            regras.append(regra)
    return regras


def _book_disregard_mask(df_at):
    """Máscara das linhas da Athena que o cadastro manda tirar.

    Devolve `(mask_or_None, avisos)`. A coluna cadastrada é procurada no
    relatório pela forma NORMALIZADA do nome (`INT_EXT` ≡ `Int Ext` ≡
    `int-ext`), porque a grafia depende de quem gerou o arquivo. Regra que cite
    coluna inexistente é PULADA com aviso, nunca ignorada em silêncio: ignorar o
    critério faria a regra passar a exigir menos e derrubar mais linhas do que o
    cadastro pediu.
    """
    regras = disregarded_book_rules()
    if not regras:
        return None, []

    por_norm = {}
    for c in df_at.columns:
        n = _nome_cru(c)
        if n:
            por_norm.setdefault(n, c)

    avisos, fora, cache = [], pd.Series(False, index=df_at.index), {}
    for regra in regras:
        ausentes = [col for col, _v in regra if _nome_cru(col) not in por_norm]
        if ausentes:
            avisos.append({'code': 'rule_missing_cols',
                           'cols': ' / '.join(ausentes),
                           'rule': ' + '.join('%s = %s' % (c, v) for c, v in regra)})
            continue
        casa = pd.Series(True, index=df_at.index)
        for col, alvo in regra:
            real = por_norm[_nome_cru(col)]
            if real not in cache:
                cache[real] = df_at[real].apply(_nome_cru)
            casa = casa & (cache[real] == alvo)
        fora = fora | casa
    return fora, avisos


# =============================================================================
# Normalizações e comparação
# =============================================================================

def norm_txt(v):
    if pd.isna(v):
        return None
    return str(v).strip()


def ajustar_prefixo_cetip(v):
    """`CETIP-` → `CETIP_` na chave de operação.

    Os dois lados escrevem o mesmo identificador com traço e com underline; sem
    normalizar, a operação simplesmente não casa e sai como órfã.
    """
    if pd.isna(v):
        return v
    s = str(v).lstrip()
    if s.startswith('CETIP-'):
        return 'CETIP_' + s[len('CETIP-'):]
    return str(v)


def so_digitos(v):
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        if float(v).is_integer():
            v = int(v)
        s = str(v)
    else:
        s = str(v).strip()
        if re.fullmatch(r'\d+\.0+', s):
            s = s.split('.')[0]
    s = re.sub(r'\D', '', s).lstrip('0')
    return s or None


def num_br(v):
    """Número em formato BR (1.234,56) ou simples ('7415') → float.

    Só trata o ponto como separador de milhar QUANDO há vírgula: '1234.56' sem
    vírgula é decimal americano, e apagar o ponto dele daria 123456.
    """
    if pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s == '':
        return None
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    return pd.to_numeric(s, errors='coerce')


def texto_simples(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    return s or None


def _chave_lookup(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    s = str(v).strip()
    if s == '':
        return None
    s = ''.join(c for c in unicodedata.normalize('NFKD', s)
                if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', s).upper()


def _nome_cru(v):
    """Chave de comparação de NOME cega a pontuação e a espaço.

    Os dois lados escrevem o mesmo nome com pontuação diferente
    ('BCO J.P. MORGAN S.A. 2768' × 'BCO J.P MORGAN S.A 2768'), e comparar o texto
    literal casa silenciosamente NADA — o mesmo tropeço das pastas gêmeas do
    Electronic Inventory.
    """
    s = _chave_lookup(v)
    return re.sub(r'[^A-Z0-9]+', '', s) or None if s else None


def _texto_vazio_para_na(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    if s == '' or s.upper() in {'NAN', 'NONE'}:
        return None
    return s.upper()


def comparar(a, b, tolerancia=None, tipo=None):
    """OK/NOK de um par de valores já normalizados.

    Vazio dos dois lados é OK: a operação não tem o campo, e os dois sistemas
    concordam nisso. Vazio de um lado só é NOK — é justamente o que a recon
    procura.
    """
    if tipo == 'texto':
        a, b = _texto_vazio_para_na(a), _texto_vazio_para_na(b)
    a_na, b_na = pd.isna(a), pd.isna(b)
    if a_na and b_na:
        return 'OK'
    if a_na or b_na:
        return 'NOK'
    if tipo == 'valor' or tolerancia is not None:
        a_num = pd.to_numeric(a, errors='coerce')
        b_num = pd.to_numeric(b, errors='coerce')
        if pd.isna(a_num) or pd.isna(b_num):
            return 'NOK'
        return 'OK' if abs(a_num - b_num) <= (tolerancia or 0) else 'NOK'
    return 'OK' if a == b else 'NOK'


def aplicar_substituicao(serie, mapa):
    if not mapa:
        return serie
    norm = {str(k).strip().upper(): v for k, v in mapa.items()}

    def _tr(v):
        if pd.isna(v):
            return v
        return norm.get(str(v).strip().upper(), v)
    return serie.apply(_tr)


def aplicar_lookup(serie, mapa):
    return serie.apply(lambda v: None if pd.isna(v) else mapa.get(_chave_lookup(v)))


def normalizar_data(serie):
    """Texto/serial/AAAAMMDD → data, sem ambiguidade de dia × mês.

    A ordem importa: AAAA-MM-DD é lido como ISO e o resto como BR (dia primeiro).
    Deixar o pandas adivinhar fazia 03/04 virar 4 de março num arquivo e 3 de
    abril no outro, e a recon acusava NOK numa data que era a mesma.
    """
    def _to_date(v):
        if pd.isna(v):
            return pd.NaT
        if isinstance(v, pd.Timestamp):
            return v.normalize()
        num = pd.to_numeric(v, errors='coerce')
        if pd.notna(num) and str(v).strip().replace('.', '').isdigit():
            n = int(num)
            if 19000101 <= n <= 29991231:
                d = pd.to_datetime(str(n), format='%Y%m%d', errors='coerce')
                if pd.notna(d):
                    return d.normalize()
            d = pd.to_datetime(num, unit='D', origin='1899-12-30', errors='coerce')
            if pd.notna(d):
                return d.normalize()
        s = str(v).strip()
        if re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}', s):
            d = pd.to_datetime(s, errors='coerce', dayfirst=False)
            if pd.notna(d):
                return d.normalize()
        d = pd.to_datetime(s, errors='coerce', dayfirst=True)
        return d.normalize() if pd.notna(d) else pd.NaT
    return serie.apply(_to_date)


# =============================================================================
# Derivações — o fixing da opção asiática
# =============================================================================

def _datas_do_bloco(row, cols_bloco):
    datas = []
    for c in cols_bloco:
        v = row.get(c)
        if pd.isna(v):
            continue
        num = pd.to_numeric(v, errors='coerce')
        if pd.isna(num) or num == 0:
            continue
        d = pd.to_datetime(str(int(num)), format='%Y%m%d', errors='coerce')
        if pd.notna(d):
            datas.append(d)
    return sorted(set(datas))


def deriv_fix_date(row, ctx):
    """Último fixing. Na asiática ele é a última data do cronograma; na europeia
    é a própria data de fixing do ativo subjacente."""
    if str(row.get(ctx['col_media'])).strip().upper() == ctx['valor_datas'].upper():
        datas = _datas_do_bloco(row, ctx['cols_bloco'])
        return datas[-1] if datas else pd.NaT
    return row.get(ctx['col_fix_ad'])


def deriv_primeiro_fix(row, ctx):
    """Primeiro fixing — só existe na asiática; a europeia fixa uma vez só."""
    if str(row.get(ctx['col_media'])).strip().upper() == ctx['valor_datas'].upper():
        datas = _datas_do_bloco(row, ctx['cols_bloco'])
        return datas[0] if datas else pd.NaT
    return pd.NaT


# =============================================================================
# Os campos comparados
# =============================================================================

def deriv_cntpy_b3(row, ctx):
    """Quem é o cliente no arquivo da CETIP/B3.

    1º o CNPJ (só dígitos — a B3 grava sem pontuação, o RefData com), traduzido
    para o NOME do Reference Data; sem CNPJ ou sem cadastro, cai no Nome
    simplificado do próprio arquivo — a regra que já valia.
    """
    cnpj = so_digitos(row.get(ctx['col_cnpj_dp']))
    if cnpj:
        nome = ctx['por_cnpj'].get(cnpj)
        if nome:
            return nome
    return texto_simples(row.get(ctx['col_nome_dp']))


def deriv_cntpy_ath(row, ctx):
    """Quem é a contraparte no arquivo da Athena.

    1º o MatchingCounterpartySPN (a coluna Z do CSV) → nome do Reference Data.
    SPN vazio ou sem cadastro → regra anterior: o MatchingCounterpartyName,
    traduzido para o nome canônico quando o cadastro o conhece, senão como veio;
    por último o CounterpartyName.
    """
    if ctx.get('col_spn_at'):
        spn = so_digitos(row.get(ctx['col_spn_at']))
        if spn:
            nome = ctx['por_spn'].get(spn)
            if nome:
                return nome
    v = texto_simples(row.get(ctx['col_nome_at']))
    if v is not None:
        cnpj = ctx['mapa_cnpj'].get(_chave_lookup(v))
        if cnpj:
            canonico = ctx['por_cnpj'].get(cnpj)
            if canonico:
                return canonico
        return v
    return texto_simples(row.get(ctx['col_nome_at2']))


# Cada campo tem um NOME COMUM (`campo`) e os três rótulos saem dele:
# `B3 <campo>` / `ATH <campo>` / `Status <campo>`. É o nome comum que a coluna
# Status usa na lista do Partial.
def _rots(campo):
    return {'rot_dp': 'B3 ' + campo, 'rot_at': 'ATH ' + campo,
            'rot_st': 'Status ' + campo, 'campo': campo}


CAMPOS = [
    dict({'nome': 'JPM_Dir', 'dp': 'Posição da Parte', 'at': 'TransactionType',
          'subst_dp': {'TITULAR': 'Buy', 'LANCADOR': 'Sell'}}, **_rots('Dir')),

    dict({'nome': 'P_C', 'dp': 'Tipo de Opção', 'at': 'OptionType',
          'subst_at': {'Put on USD': 'PUT', 'Call on USD': 'CALL'}}, **_rots('P/C')),

    # A identidade da contraparte sai do Reference Data pelos DOIS lados:
    # SPN (Athena, coluna Z) e CNPJ (CETIP) apontam a mesma linha, e o que se
    # compara é o NOME registrado — ver deriv_cntpy_b3 / deriv_cntpy_ath.
    dict({'nome': 'Ctpty', 'dp': None, 'at': None,
          'derivacao': deriv_cntpy_b3, 'derivacao_at': deriv_cntpy_ath,
          'tipo': 'texto'}, **_rots('Cntpy')),

    dict({'nome': 'Amt', 'dp': 'Quantidade', 'at': 'Quantity',
          'abs_at': True, 'tipo': 'valor'}, **_rots('Amt')),

    dict({'nome': 'Premium', 'dp': 'Valor financeiro total do prêmio', 'at': 'Premium',
          # Tolerância de 0,67: o prêmio da CETIP é arredondado no registro, e a
          # diferença de centavos não é quebra de recon.
          'abs_at': True, 'arred': 2, 'tolerancia': 0.67, 'tipo': 'valor'}, **_rots('Premium')),

    dict({'nome': 'Strike', 'dp': 'Strike (valor)', 'at': 'Strike',
          'tipo': 'valor'}, **_rots('Strike')),

    dict({'nome': 'TD', 'dp': 'Data Registro', 'at': 'TradeDate',
          'tipo': 'data', 'fmt': '%d/%m/%Y'}, **_rots('Trade Date')),

    dict({'nome': 'VD', 'dp': 'Data Vencimento', 'at': 'SettlementDate',
          'tipo': 'data', 'fmt': '%d/%m/%Y'}, **_rots('Settlement Date')),

    dict({'nome': 'Fix_Date', 'dp': None, 'at': 'FixingDate',
          'tipo': 'data', 'derivacao': deriv_fix_date, 'fmt': '%d/%m/%Y'}, **_rots('Fix Date')),

    dict({'nome': 'Primeiro_Fix', 'dp': None, 'at': 'FirstFixingDate',
          'tipo': 'data', 'derivacao': deriv_primeiro_fix, 'fmt': '%d/%m/%Y'}, **_rots('1st Fix')),

    dict({'nome': 'Asian_European', 'dp': 'Média Asiática', 'at': 'OptionStyle',
          'subst_dp': {'SIMPLES_DATAS': 'Asian'},
          'subst_at': {'Vanilla Option': '', 'Avg Rate Option': 'Asian', 'European': ''},
          'tipo': 'texto'}, **_rots('Style')),
]

STATUS_COLS = [c['rot_st'] for c in CAMPOS]

# Os quatro estados da 1ª coluna, na ordem da gravidade.
#   Unmatched B3     — a operação está na CETIP/B3 e não achou par na Athena
#   Unmatched Athena — está na Athena e não achou par na B3
#   Partial - campos — casou, mas algum campo diverge
#   Matched          — fechou
# `Justified` é ortogonal: é o que qualquer um dos três primeiros vira quando
# alguém escreve um comentário explicando a divergência (ver `COMMENT_COLUMN`).
ST_UNMATCHED_B3 = 'Unmatched B3'
ST_UNMATCHED_ATH = 'Unmatched Athena'
ST_MATCHED = 'Matched'
ST_JUSTIFIED = 'Justified'

# A coluna do comentário vem logo depois do Status porque é ela que o explica.
COMMENT_COLUMN = 'Comentário'

# O status ANTES da justificativa, guardado na linha e fora de `COLUMNS` (a tela
# não o mostra). É ele que permite apagar um comentário e a linha voltar a dizer
# 'Partial - Cntpy' em vez de ficar 'Justified' para sempre.
STATUS_RAW_KEY = '_status'

# Colunas da tabela, na ordem em que aparecem na página. O checkbox e o Actions
# são da TELA (o padrão de tabela do app), não do motor — por isso não estão aqui.
COLUMNS = (['Status', COMMENT_COLUMN, 'Código IF', 'Combinação de operações']
           + [x for c in CAMPOS for x in (c['rot_dp'], c['rot_at'], c['rot_st'])]
           + ['Match', 'Chave Duplicada'])


# =============================================================================
# Match
# =============================================================================

def base_athena_para_match(df_at, chaves_b3):
    """Athena expandida para o match, com PRIORIDADE do DealID.

    A chave da CETIP pode bater com o `DealID` ou com o `MatchingDealID`. As duas
    entram, mas a linha de MatchingDealID só é considerada quando aquela chave
    NÃO existe em DealID nenhum — senão a mesma operação apareceria duas vezes e
    o `drop_duplicates` escolheria qualquer uma das duas.

    E ela só entra quando o valor do `MatchingDealID` **existe do lado da B3**
    (`chaves_b3` são as `Combinação de operações` da base âncora). O
    MatchingDealID é o identificador da perna do OUTRO lado, e a maioria desses
    valores não corresponde a registro nenhum da CETIP: sem esse filtro cada um
    deles entra no merge `outer` como uma linha a mais da Athena sem par, isto é,
    um `Unmatched Athena` fantasma — a MESMA operação da Athena aparecendo de
    novo, agora pela chave da perna oposta. Só o MatchingDealID que tem B3
    correlacionado pode fechar alguma coisa; o resto é descartado.
    """
    chave_deal = df_at[COL_AT_CHAVE].apply(norm_txt)
    chave_match = df_at[COL_AT_MATCHING].apply(norm_txt)
    set_deal = set(chave_deal.dropna().unique())
    set_b3 = set(chaves_b3)

    base_deal = df_at.copy()
    base_deal['_chave_norm'] = chave_deal.values
    base_deal['match_athena_por'] = 'DealID'
    base_deal['_prio'] = 1
    base_deal = base_deal[base_deal['_chave_norm'].notna()].copy()

    base_match = df_at.copy()
    base_match['_chave_norm'] = chave_match.values
    base_match['match_athena_por'] = 'MatchingDealID'
    base_match['_prio'] = 2
    base_match = base_match[base_match['_chave_norm'].notna()
                            & ~base_match['_chave_norm'].isin(set_deal)
                            & base_match['_chave_norm'].isin(set_b3)].copy()

    out = pd.concat([base_deal, base_match], ignore_index=True)
    out = out.sort_values('_prio').drop_duplicates(subset=['_chave_norm'], keep='first')
    return out


# =============================================================================
# Reconciliação
# =============================================================================

def reconcile(df_dp, df_at):
    """DPOSICAO × Athena → (linhas, contagens, avisos)."""
    avisos = []

    for c in (COL_DP_PARTE_CONTA, COL_DP_CLASSE, COL_DP_CHAVE, COL_DP_CODIGO_IF,
              COL_DP_MEDIA_ASIAT, COL_DP_FIX_ADATIVO):
        if c not in df_dp.columns:
            raise KeyError('Coluna %r não existe na DPOSICAO.' % c)
    for c in (COL_AT_CHAVE, COL_AT_MATCHING, COL_AT_OPTIONSTYLE):
        if c not in df_at.columns:
            raise KeyError('Coluna %r não existe no relatório da Athena.' % c)

    df_dp = df_dp.copy()
    df_dp[COL_DP_CHAVE] = df_dp[COL_DP_CHAVE].apply(ajustar_prefixo_cetip)

    mapa_cnpj = lookup_cnpj()
    if not mapa_cnpj:
        avisos.append({'code': 'no_taxid'})
    diretas, espelhadas = internal_cpty_rules()

    cols_bloco = list(df_dp.columns[IDX_BLOCO_FIXING_INI:IDX_BLOCO_FIXING_FIM + 1])

    # ── Base âncora: a nossa conta, só câmbio ────────────────────────────────
    conta_txt = df_dp[COL_DP_PARTE_CONTA].apply(norm_txt)
    conta_num = pd.to_numeric(df_dp[COL_DP_PARTE_CONTA], errors='coerce')
    try:
        alvo_num = float(FILTRO_PARTE_CONTA)
    except ValueError:
        alvo_num = None
    # A conta chega ora como texto ora como número, conforme quem gravou o
    # arquivo — os dois testes existem para a linha não sumir por causa disso.
    cond_conta = (conta_txt == FILTRO_PARTE_CONTA)
    if alvo_num is not None:
        cond_conta = cond_conta | (conta_num == alvo_num)
    cond_classe = (df_dp[COL_DP_CLASSE].apply(norm_txt).fillna('').str.upper()
                   == FILTRO_CLASSE.upper())
    df_anc = df_dp[cond_conta & cond_classe].copy()

    if df_anc.empty:
        avisos.append({'code': 'empty_anchor', 'account': FILTRO_PARTE_CONTA})

    chave_dp = df_anc[COL_DP_CHAVE].apply(norm_txt)
    df_anc['_chave_norm'] = chave_dp.values
    df_anc['alerta_chave_duplicada'] = (chave_dp.duplicated(keep=False)
                                        & chave_dp.notna()).values
    # Marca de que a linha veio da B3. Depois do join ela é o que distingue a
    # operação que a Athena não tem da operação que a B3 não tem — as duas saem
    # do merge com metade das colunas vazias, e sem a marca seriam a mesma coisa.
    df_anc['_veio_da_b3'] = True

    df_at = df_at.copy()

    # As pernas internas cadastradas como `Disregard` saem AQUI, antes do match.
    # O aviso não é decoração: linha que some sem dizer nada vira "sumiu uma
    # operação da recon" no dia em que alguém marcar o nome errado.
    ignorados = ignored_cpty_names()
    if ignorados:
        cols_cpty = [c for c in COLS_AT_CPTY_DISREGARD if c in df_at.columns]
        if not cols_cpty:
            avisos.append({'code': 'cpty_missing_cols',
                           'cols': ' / '.join(COLS_AT_CPTY_DISREGARD)})
        else:
            fora = pd.Series(False, index=df_at.index)
            for c in cols_cpty:
                fora = fora | df_at[c].apply(_nome_cru).isin(ignorados)
            n_fora = int(fora.sum())
            if n_fora:
                df_at = df_at[~fora].copy()
                avisos.append({'code': 'cut_cpty', 'n': n_fora})

    # E as pernas cadastradas por BOOK (`fxo-book-disregard`) saem no mesmo
    # ponto, e pela mesma razão: é a perna interbook que não tem registro na
    # CETIP e viraria `Unmatched Athena` todo dia. O corte tem de ser ANTES do
    # merge — depois dele o DealID dessa linha já teria ocupado a chave e poderia
    # ter roubado o par de uma operação de verdade.
    fora_book, avisos_book = _book_disregard_mask(df_at)
    avisos.extend(avisos_book)
    if fora_book is not None:
        n_fora = int(fora_book.sum())
        if n_fora:
            df_at = df_at[~fora_book].copy()
            avisos.append({'code': 'cut_rows', 'n': n_fora})

    # OUTER, e não LEFT: o left só enxergava a B3 sem par na Athena. A operação
    # que existe SÓ na Athena simplesmente não aparecia na tela — e é uma quebra
    # de recon do mesmo tamanho, com a diferença de que ninguém a via.
    # As chaves da B3 vão junto: é com elas que o MatchingDealID sem par
    # correlacionado é descartado antes do merge (ver `base_athena_para_match`).
    df_final = df_anc.merge(base_athena_para_match(df_at, chave_dp.dropna().unique()),
                            on='_chave_norm', how='outer', suffixes=('_dp', '_at'))
    df_final['_veio_da_b3'] = df_final['_veio_da_b3'].fillna(False).astype(bool)
    df_final['sem_correspondencia_athena'] = (df_final['match_athena_por'].isna()
                                              & df_final['_veio_da_b3'])
    df_final['sem_correspondencia_b3'] = ~df_final['_veio_da_b3']

    def col_dp(nome):
        if nome in df_final.columns:
            return nome
        if '%s_dp' % nome in df_final.columns:
            return '%s_dp' % nome
        raise KeyError('Não encontrei %r na base final.' % nome)

    def col_at(nome):
        if nome in df_final.columns:
            return nome
        if '%s_at' % nome in df_final.columns:
            return '%s_at' % nome
        raise KeyError('Não encontrei a coluna Athena %r na base final.' % nome)

    por_spn, por_cnpj = refdata_indexes()
    ctx = {'col_media': col_dp(COL_DP_MEDIA_ASIAT),
           'col_fix_ad': col_dp(COL_DP_FIX_ADATIVO),
           'cols_bloco': [col_dp(c) for c in cols_bloco],
           'valor_datas': VALOR_MEDIA_ASIATICA_DATAS,
           # Identidade da contraparte (ver deriv_cntpy_*)
           'por_spn': por_spn, 'por_cnpj': por_cnpj, 'mapa_cnpj': mapa_cnpj,
           'col_cnpj_dp': col_dp('CPF/CNPJ Cliente Contraparte'),
           'col_nome_dp': col_dp('Contraparte (Nome simplificado)'),
           'col_nome_at': col_at('MatchingCounterpartyName'),
           'col_nome_at2': col_at('CounterpartyName'),
           'col_spn_at': None}
    try:
        ctx['col_spn_at'] = col_at('MatchingCounterpartySPN')
    except KeyError:
        avisos.append({'code': 'no_match_spn'})

    saida = pd.DataFrame()
    saida['Código IF'] = df_final[col_dp(COL_DP_CODIGO_IF)].values
    # A linha que só existe na Athena não tem chave da CETIP: a coluna recebe a
    # chave do JOIN (o DealID). É a mesma coisa que a coluna sempre guardou — o
    # identificador pelo qual os dois lados se procuram —, e deixá-la vazia daria
    # uma linha sem nenhum jeito de dizer de que operação se está falando.
    chave_saida = df_final[col_dp(COL_DP_CHAVE)].where(
        df_final['_veio_da_b3'], df_final['_chave_norm'])
    saida['Combinação de operações'] = chave_saida.values

    for m in CAMPOS:
        if m.get('derivacao') is not None:
            v_dp = df_final.apply(lambda row, f=m['derivacao']: f(row, ctx), axis=1)
        else:
            v_dp = df_final[col_dp(m['dp'])]
        if m.get('derivacao_at') is not None:
            v_at = df_final.apply(lambda row, f=m['derivacao_at']: f(row, ctx), axis=1)
        else:
            v_at = df_final[col_at(m['at'])]

        if m.get('lookup_at'):
            v_at = aplicar_lookup(v_at, mapa_cnpj)

        v_dp = aplicar_substituicao(v_dp, m.get('subst_dp'))
        v_at = aplicar_substituicao(v_at, m.get('subst_at'))

        if m.get('abs_dp'):
            v_dp = pd.to_numeric(v_dp, errors='coerce').abs()
        if m.get('abs_at'):
            v_at = pd.to_numeric(v_at, errors='coerce').abs()

        if m.get('tipo') == 'data':
            v_dp, v_at = normalizar_data(v_dp), normalizar_data(v_at)
        elif m.get('tipo') == 'digitos':
            v_dp = pd.Series(v_dp).apply(so_digitos)
            v_at = pd.Series(v_at).apply(so_digitos)
        elif m.get('tipo') == 'valor':
            # A CETIP vem como texto e em formato BR; a Athena já é numérica.
            v_dp = pd.Series(v_dp).apply(num_br)
            v_at = pd.to_numeric(pd.Series(v_at), errors='coerce')

        if m.get('arred') is not None:
            v_dp = pd.to_numeric(v_dp, errors='coerce').round(m['arred'])
            v_at = pd.to_numeric(v_at, errors='coerce').round(m['arred'])

        v_dp, v_at = pd.Series(list(v_dp)), pd.Series(list(v_at))

        # Sem tradução dos dois lados, cai no nome — ver o comentário do campo.
        if m.get('fallback_dp'):
            nomes = df_final[col_dp(m['fallback_dp'])].apply(texto_simples).values
            v_dp = pd.Series([n if pd.isna(v) else v for v, n in zip(v_dp, nomes)])
        if m.get('fallback_at'):
            nomes = df_final[col_at(m['fallback_at'])].apply(texto_simples).values
            v_at = pd.Series([n if pd.isna(v) else v for v, n in zip(v_at, nomes)])

        if diretas and m['nome'] == 'Ctpty':
            v_at = aplicar_substituicao(v_at, diretas)

        if m.get('tipo') == 'data':
            fmt = m.get('fmt', '%d/%m/%Y')
            saida[m['rot_dp']] = pd.Series(v_dp).dt.strftime(fmt).values
            saida[m['rot_at']] = pd.Series(v_at).dt.strftime(fmt).values
        else:
            saida[m['rot_dp']] = pd.Series(v_dp).values
            saida[m['rot_at']] = pd.Series(v_at).values

        saida[m['rot_st']] = [comparar(a, b, m.get('tolerancia'), m.get('tipo'))
                              for a, b in zip(v_dp, v_at)]

    # A perna espelhada é uma correção da comparação entre os DOIS lados; numa
    # linha que só tem um lado não há o que espelhar, e a assinatura que ela
    # procura (Ctpty e Dir os dois NOK) acontece ali por falta de par.
    _aplicar_perna_espelhada(saida, espelhadas, df_final['_veio_da_b3'].values
                             & ~df_final['sem_correspondencia_athena'].values)

    # `Match` diz POR ONDE a operação casou. Na linha que só existe na Athena ela
    # sai vazia: aquela linha veio da base da Athena e por isso carrega o
    # 'DealID' herdado do lado direito do join, mas não casou com nada — deixá-lo
    # inflaria o chip de diagnóstico com operações que não tiveram match nenhum.
    saida['Match'] = df_final['match_athena_por'].where(
        df_final['_veio_da_b3'], '').fillna('').values
    # `alerta_chave_duplicada` vem NaN nas linhas só-Athena (elas não estavam no
    # df_anc), e `if nan` é VERDADEIRO — sem o teste explícito, toda operação
    # órfã da Athena sairia marcada como chave duplicada. `pd.notna(x) and
    # bool(x)`, e não `x is True`: depois do merge o valor é um `numpy.bool_`, e
    # `numpy.True_ is True` é FALSO — o teste de identidade apagava a marca de
    # TODAS as linhas, inclusive as duplicadas de verdade.
    saida['Chave Duplicada'] = ['Sim' if (pd.notna(x) and bool(x)) else ''
                               for x in df_final['alerta_chave_duplicada'].values]

    sem_ath = df_final['sem_correspondencia_athena'].values
    sem_b3 = df_final['sem_correspondencia_b3'].values
    # O Status da linha DIZ o que não bateu: 'Matched' quando todos os campos
    # fecharam, 'Partial - Cntpy | Settlement Date' listando os campos NOK pelo
    # nome comum. Faltar um dos lados vence tudo: sem a outra ponta, os onze NOK
    # são consequência de um só problema.
    nok_por_linha = [
        [c['campo'] for c in CAMPOS if saida[c['rot_st']].iat[i] == 'NOK']
        for i in range(len(saida))
    ]
    saida.insert(0, 'Status', [
        ST_UNMATCHED_B3 if a else (ST_UNMATCHED_ATH if b else
                                   ('Partial - ' + ' | '.join(f) if f else ST_MATCHED))
        for a, b, f in zip(sem_ath, sem_b3, nok_por_linha)])
    # A coluna do comentário nasce vazia aqui e é preenchida por
    # `aplicar_comentarios`, que é quem sabe o que já foi justificado antes.
    saida.insert(1, COMMENT_COLUMN, '')

    rows = [{k: _cell(v) for k, v in rec.items()}
            for rec in saida.to_dict('records')]
    aplicar_comentarios(rows)
    return rows, _contar(rows), avisos


def _aplicar_perna_espelhada(saida, espelhadas, elegivel=None):
    """A perna interna que chega invertida: espelha a direção e renomeia.

    Só entra onde Ctpty E JPM Dir estão os DOIS NOK — a assinatura de que a linha
    é a perna espelhada da mesa, e não uma divergência de verdade. `elegivel` é a
    máscara das linhas que têm os DOIS lados; sem ela, uma linha órfã (que tem
    todos os campos NOK por falta de par) seria "corrigida" para um par que não
    existe.
    """
    if not espelhadas or saida.empty:
        return
    precisa = {'Status Cntpy', 'Status Dir', 'ATH Cntpy', 'ATH Dir',
               'B3 Dir', 'B3 Cntpy'}
    if not precisa.issubset(saida.columns):
        return
    base = (pd.Series(list(elegivel), index=saida.index)
            if elegivel is not None else pd.Series(True, index=saida.index))

    def _flip(v):
        if pd.isna(v):
            return v
        s = str(v).strip().upper()
        return 'Buy' if s == 'SELL' else ('Sell' if s == 'BUY' else v)

    for nome_at, codigo in espelhadas:
        mask = (
            base &
            (saida['Status Cntpy'] == 'NOK') & (saida['Status Dir'] == 'NOK') &
            saida['ATH Cntpy'].apply(
                lambda x, n=nome_at: pd.notna(x) and str(x).strip().upper() == n)
        )
        if not mask.any():
            continue
        saida.loc[mask, 'ATH Dir'] = saida.loc[mask, 'ATH Dir'].apply(_flip)
        saida.loc[mask, 'Status Dir'] = [
            comparar(a, b) for a, b in zip(saida.loc[mask, 'B3 Dir'],
                                           saida.loc[mask, 'ATH Dir'])]
        saida.loc[mask, 'ATH Cntpy'] = codigo
        saida.loc[mask, 'Status Cntpy'] = [
            comparar(a, b) for a, b in zip(saida.loc[mask, 'B3 Cntpy'],
                                           saida.loc[mask, 'ATH Cntpy'])]
        _LOG.info('[recon_fxo] perna espelhada %s: %d linha(s) ajustada(s)',
                  nome_at, int(mask.sum()))


def _cell(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ''
    if isinstance(v, float) and float(v).is_integer():
        return str(int(v))
    if isinstance(v, (int, float)):
        return str(v)
    return str(v).strip()


def _contar(rows):
    """As contagens dos cards. `nok_por_campo` diz QUAL campo está quebrando —
    sem ela, '40 linhas com NOK' não indica por onde começar."""
    counts = {
        'total': len(rows),
        'ok': sum(1 for r in rows if r.get('Status') == ST_MATCHED),
        'nok': sum(1 for r in rows if str(r.get('Status', '')).startswith('Partial')),
        'no_match': sum(1 for r in rows if r.get('Status') == ST_UNMATCHED_B3),
        'no_match_ath': sum(1 for r in rows if r.get('Status') == ST_UNMATCHED_ATH),
        'justified': sum(1 for r in rows if r.get('Status') == ST_JUSTIFIED),
        'match_dealid': sum(1 for r in rows if r.get('Match') == 'DealID'),
        'match_matching': sum(1 for r in rows if r.get('Match') == 'MatchingDealID'),
        'dup_key': sum(1 for r in rows if r.get('Chave Duplicada') == 'Sim'),
    }
    counts['nok_por_campo'] = {c: sum(1 for r in rows if r.get(c) == 'NOK')
                               for c in STATUS_COLS}
    return counts


# =============================================================================
# Comentários — a justificativa que atravessa as recons
# =============================================================================
#
# O comentário pertence ao TRADE, não à execução do dia: quem explicou por que
# aquela operação não casa não vai reescrever a explicação toda manhã. Por isso
# ele mora fora do cache por data, e é reaplicado em toda leitura — inclusive nos
# resultados que já estavam gravados antes de o comentário existir.
#
# A chave é a `Combinação de operações`, que é o identificador pelo qual os dois
# lados se procuram (a chave da CETIP, ou o DealID nas linhas só-Athena). Chavear
# por Código IF perderia as linhas da Athena, que não têm um.
_COMMENTS_PATH = data_write('recon-fxo-comments.json')
_COMMENTS_LOCK = threading.Lock()

# Os estados que uma justificativa cobre. `Matched` fica de fora de propósito:
# comentar uma linha que fechou é uma anotação, não uma justificativa, e trocar o
# status dela esconderia o único estado que não precisa de atenção nenhuma.
_JUSTIFICAVEL = (ST_UNMATCHED_B3, ST_UNMATCHED_ATH)


def _comment_key(row):
    return str(row.get('Combinação de operações', '') or '').strip()


# Status que já foram gravados em cache com outro nome. A recon é persistida por
# data, e o arquivo de ontem continua sendo lido depois de o nome mudar — sem
# esta tradução na leitura, a linha antiga fica com o rótulo velho, o badge cai
# no cinza de "desconhecido", a ordenação por gravidade a joga para o fim e o
# card correspondente conta ZERO com as linhas ali na tela.
_STATUS_ANTIGOS = {
    'Sem match': ST_UNMATCHED_B3,
}


def _status_atual(s):
    return _STATUS_ANTIGOS.get(str(s or '').strip(), str(s or ''))


def load_comments():
    """{chave: comentário} do disco. Arquivo ausente ou ilegível = {}."""
    try:
        with open(_COMMENTS_PATH, encoding='utf-8') as fh:
            data = json.load(fh)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if str(v or '').strip()}


def save_comment(key, comment):
    """Grava (ou apaga, com comentário vazio) a justificativa de um trade.

    Ler-alterar-gravar sob lock: dois usuários comentando linhas diferentes ao
    mesmo tempo gravariam o arquivo inteiro por cima um do outro, e o segundo
    apagaria o comentário do primeiro.
    """
    k = str(key or '').strip()
    if not k:
        raise ValueError('Sem a chave da operação não há o que comentar.')
    txt = str(comment or '').strip()
    with _COMMENTS_LOCK:
        data = load_comments()
        if txt:
            data[k] = txt
        else:
            data.pop(k, None)
        try:
            os.makedirs(os.path.dirname(_COMMENTS_PATH), exist_ok=True)
            # Pelo FUNIL (auditoria §335): atômico E avisando o espelho — o
            # tmp+replace local fazia o mesmo sem o banco ficar sabendo.
            from apps.pages import routes
            routes._atomic_write_json(_COMMENTS_PATH, data)
        except Exception as exc:
            _LOG.warning('[recon_fxo] não consegui gravar o comentário: %s', exc)
            raise
    return txt


def aplicar_comentarios(rows, comments=None):
    """Escreve o comentário em cada linha e promove o Status a `Justified`.

    Roda na gravação E na leitura, e é idempotente: um comentário escrito hoje
    aparece na recon de ontem que já está em cache, e apagá-lo devolve a linha ao
    status que ela tinha.

    Essa volta atrás só é possível porque o status original fica guardado em
    `_status`, fora de `COLUMNS` (a tela não o mostra). Sobrescrever o `Status`
    direto gravaria 'Justified' no cache, e a linha nunca mais saberia dizer o
    que ela era antes de alguém justificá-la.
    """
    if comments is None:
        comments = load_comments()
    for r in rows:
        # A linha vinda de um cache antigo não tem `_status`; o Status dela ainda
        # é o cru, porque ela foi gravada antes de existir justificativa. E o
        # nome pode ser o de antes ('Sem match'), daí o `_status_atual`.
        raw = _status_atual(r.get(STATUS_RAW_KEY) or r.get('Status', ''))
        r[STATUS_RAW_KEY] = raw
        txt = comments.get(_comment_key(r), '')
        r[COMMENT_COLUMN] = txt
        justificavel = raw in _JUSTIFICAVEL or raw.startswith('Partial')
        r['Status'] = ST_JUSTIFIED if (txt and justificavel) else raw
    return rows


# =============================================================================
# Cache por data
# =============================================================================

def _cache_path(recon_date):
    d = _parse_date(recon_date)
    return os.path.join(_CACHE_DIR, 'fxo_%s.json' % d.strftime('%Y%m%d'))


def _persist(recon_date, payload):
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        # Pelo FUNIL (auditoria §335): atômico e com o espelho avisado.
        from apps.pages import routes
        routes._atomic_write_json(_cache_path(recon_date), payload)
    except Exception as exc:                       # pragma: no cover - defensivo
        _LOG.warning('[recon_fxo] não consegui gravar o cache: %s', exc)


def load_last(recon_date=''):
    """Último resultado gravado para a data — a página abre com ele, sem rodar.

    Data ausente/inválida devolve o vazio em vez de estourar: a tela pede o
    resultado assim que carrega, antes de o usuário escolher qualquer coisa.
    """
    vazio = {'columns': COLUMNS, 'data': [], 'counts': _contar([]), 'warnings': []}
    try:
        path = _cache_path(recon_date)
    except ValueError:
        return vazio
    if not os.path.exists(path):
        return vazio
    try:
        with open(path, encoding='utf-8') as fh:
            payload = json.load(fh)
    except Exception:
        return vazio
    # As colunas são SEMPRE as de agora: um cache gravado antes da coluna de
    # comentário existir traria a lista antiga, e a tela montaria a tabela sem
    # ela — com os dados novos por baixo, e sem erro nenhum.
    payload['columns'] = COLUMNS
    payload.setdefault('warnings', [])
    # A justificativa é reaplicada na LEITURA: ela vale para o trade, não para a
    # execução, então um comentário escrito hoje tem de aparecer na recon de
    # ontem que já está gravada. As contagens saem daí, e não do que foi
    # persistido, senão o card diria um número e a tabela mostraria outro.
    linhas = payload.get('data') or []
    aplicar_comentarios(linhas)
    payload['counts'] = _contar(linhas)
    return payload


# =============================================================================
# Execução
# =============================================================================

def _classificar_upload(nome, blob):
    """Qual dos dois arquivos é este — pelo CONTEÚDO, não pelo nome.

    O nome depende de quem baixou (`brazil_fxo_trades (2).csv`), e trocar as duas
    bases de lugar faria a recon rodar inteira e devolver tudo órfão.
    """
    head = blob[:4096].decode('latin-1', errors='replace')
    if COL_AT_CHAVE in head and '|' in head:
        return 'athena'
    if COL_DP_PARTE_CONTA in head or 'DPOSICAO' in nome.upper():
        return 'dposicao'
    if nome.upper().endswith('.OPC'):
        return 'dposicao'
    return 'athena' if nome.lower().endswith('.csv') else None


def run_fxo(recon_date, files=None, mode='auto'):
    """Roda a reconciliação e devolve o que a página mostra.

    `mode='auto'` busca as duas bases (rede + Athena); `mode='manual'` usa os
    arquivos enviados na tela, para o dia em que a rede ou o relatório não
    respondem.
    """
    _parse_date(recon_date)                    # falha cedo, com a data na mão
    origem = {}

    if mode == 'manual':
        for f in (files or []):
            blob = f.read()
            qual = _classificar_upload(getattr(f, 'filename', '') or '', blob)
            if qual == 'athena':
                origem['athena'] = read_athena(blob)
            elif qual == 'dposicao':
                origem['dposicao'] = read_dposicao(io.BytesIO(blob))
        faltando = [n for n in ('dposicao', 'athena') if n not in origem]
        if faltando:
            raise ValueError('Faltou o arquivo de %s.' % ' e de '.join(
                {'dposicao': 'posição (DPOSICAO .OPC)',
                 'athena': 'trades da Athena (CSV)'}[n] for n in faltando))
    else:
        caminho = dposicao_path(recon_date)
        if not os.path.exists(caminho):
            raise FileNotFoundError(caminho)
        origem['dposicao'] = read_dposicao(caminho)
        origem['athena'] = read_athena(_baixar_athena(recon_date))

    rows, counts, avisos = reconcile(origem['dposicao'], origem['athena'])
    payload = {
        'columns': COLUMNS,
        'data': rows,
        'counts': counts,
        'warnings': avisos,
        'recon_date': _parse_date(recon_date).strftime('%Y-%m-%d'),
        'ran_at': datetime.now().strftime('%d/%m/%Y %H:%M'),
        'mode': mode,
    }
    _persist(recon_date, payload)
    payload['success'] = True
    payload['meta'] = ('%d operações · %d Matched · %d Partial · '
                       '%d Unmatched B3 · %d Unmatched Athena' % (
                           counts['total'], counts['ok'], counts['nok'],
                           counts['no_match'], counts['no_match_ath']))
    return payload


def _baixar_athena(recon_date):
    """Bytes do relatório EOD do dia."""
    url = athena_url(recon_date)
    try:
        from apps.pages import athena_api
        session = athena_api.build_session()
    except Exception:
        import requests
        session = requests.Session()
        # Mesma razão do athena_api: o proxy corporativo recusa o host interno
        # que o navegador alcança direto.
        session.trust_env = False
    resp = session.get(url, timeout=180)
    resp.raise_for_status()
    return resp.content
