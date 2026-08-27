# -*- coding: utf-8 -*-
"""As regras do relatório — puras: o que entra chega por parâmetro."""
import re

# O assunto é contrato com quem recebe (a caixa do time tem regra por assunto):
# ele não leva data nem contagem, e é igual todo dia.
SUBJECT = 'Support to OTC Derivatives - EA Metrics'

# A máscara dos valores. O código é escrito na convenção INVARIANTE do formato
# de arquivo (`,` = milhar, `.` = decimal), sempre — não é o que se vê. Quem
# desenha a célula é o Excel de quem abre, com o separador do idioma DELE: num
# Excel pt-BR este mesmo código sai `1.500.000,00`, que é a máscara pedida.
#
# Escrever `#.##0,00` aqui (a máscara como ela se LÊ em português) produziria um
# código malformado — o Excel leria o ponto como decimal —, e o valor sairia
# errado sem erro nenhum.
MONEY_FMT = '#,##0.00'


def ccy(row):
    """O CÓDIGO da moeda, repartido da coluna `Notional Amount CCY`.

    A moeda não sai da coluna `Moeda`: aquela é o ATIVO da confirmação e em
    mercadoria guarda a commodity (OLEO, PLATTS), que não é moeda nenhuma.

    O `split_notional_ccy` é regra que já mora no `manual_conf` — a esteira é o
    módulo horizontal deste relatório, e a função é pura; o import é atrasado
    só para este módulo continuar importável sem o resto do app.
    """
    from apps.pages import manual_conf
    return manual_conf.split_notional_ccy(row.get('Notional Amount CCY'))[0]


def amount(row):
    """O VALOR do notional — a outra metade da mesma coluna (ver `ccy`)."""
    from apps.pages import manual_conf
    return manual_conf.split_notional_ccy(row.get('Notional Amount CCY'))[1]


# As colunas do anexo, na ordem pedida: (cabeçalho, origem, tipo).
#
# A ORIGEM de cada coluna é o nome de uma coluna da esteira, uma FUNÇÃO da linha
# ou `''` — que é a coluna que sai sempre em branco. Só `Born Age` é assim, e foi
# pedida assim: ela é preenchida do outro lado, por quem consolida. Ela fica no
# arquivo porque a POSIÇÃO das colunas é o contrato — tirá-la deslocaria as
# demais.
#
# O TIPO é declarado por coluna, e não adivinhado do conteúdo (`num` é contagem,
# sem máscara; `money` é valor, com a máscara de milhar).
#
# A grafia dos cabeçalhos é a que foi pedida, `Conterparty Name` e
# `National Currency` inclusive: quem lê a planilha do outro lado casa pelo nome
# da coluna, e "corrigir" o typo aqui quebraria o casamento em silêncio.
COLUMNS = (
    ('Trade ID',          'Trade ID',           'text'),
    ('Product',           'Produto',            'text'),
    ('Trade Date',        'Data Operação',      'date'),
    ('Legal Entity',      'Legal Entity',       'text'),
    ('Conterparty Name',  'Cliente',            'text'),
    ('Aging',             'Aging Confirmação',  'num'),
    ('Born Age',          '',                   'text'),
    ('Notional/Qty',      'Notional',           'money'),
    ('National Currency', ccy,                  'text'),
    ('Notional Amount',   amount,               'money'),
    ('Comments',          'E-mail Subject',     'text'),
    ('LOB',               'LOB',                'text'),
)


def num(raw):
    """O número de uma célula, ou None quando não é número.

    Aceita as DUAS escritas que convivem no banco: a do New Deals ('1500000',
    '250000.50') e a que veio da planilha legada ('1.500.000,00'). O desempate é
    o mesmo do `num()` da tela — vírgula com uma ou duas casas no fim é decimal,
    e aí o ponto é separador de milhar.
    """
    t = str(raw or '').strip()
    if not t:
        return None
    t = (t.replace('.', '').replace(',', '.')
         if re.search(r',\d{1,2}$', t) else t.replace(',', ''))
    try:
        n = float(t)
    except ValueError:
        return None
    return int(n) if n.is_integer() else n


def value(row, src):
    """O valor de uma coluna do anexo. `src` é o nome de uma coluna da esteira,
    uma função da linha, ou '' para a coluna que sai sempre em branco."""
    if not src:
        return ''
    return src(row) if callable(src) else row.get(src, '')


def attach_name(ref):
    return 'EA Metrics - {}.xlsx'.format(ref.strftime('%Y%m%d'))


def time_of(raw):
    """(hh, mm) do disparo em BRT. Entrada inválida cai no padrão — um typo na
    variável de ambiente não pode matar a rotina."""
    try:
        hh, mm = (int(x) for x in str(raw).split(':')[:2])
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
    except (ValueError, TypeError):
        pass
    return 16, 0


def pending(all_rows, status_ok):
    """As linhas do anexo, na ordem em que o relatório é lido.

    DOIS cortes, e eles respondem perguntas diferentes:

      * **sem Data Callback** — o callback é a conferência por telefone com o
        cliente, e é ele que fecha a operação manual do ponto de vista da
        métrica. O teste é a CÉLULA em branco e não um status: o callback é uma
        data, e o Track Confirmations mostra exatamente essa coluna vazia;
      * **Pending diferente de `status_ok`** — a confirmação que terminou a
        esteira saiu da fila, e o relatório é do que ainda pede ação. Este teste
        é o status porque `Ok` é justamente o nome do fim da esteira; ele também
        deixa o anexo restrito ao banco `pending`, que é o mesmo conjunto que o
        Monitor mostra — e, de quebra, o único cujo E-mail Subject o app
        preenche sozinho.

    A ordem é o **Aging do maior para o menor**: quem espera há mais tempo vem
    primeiro, como na fila do Monitor. O aging é gravado como TEXTO (e vem
    vazio na linha sem data de operação), então a chave é numérica — por texto,
    '10' viria antes de '9'. Vazio vai para o fim: linha sem idade não pode
    encabeçar um relatório de atraso.
    """
    def idade(r):
        try:
            return int(float(str(r.get('Aging Confirmação', '') or '').strip()))
        except (TypeError, ValueError):
            return -10 ** 9

    return sorted(
        (r for r in all_rows
         if not str(r.get('Data Callback', '') or '').strip()
         and str(r.get('Pending', '') or '').strip() != status_ok),
        key=idade, reverse=True)
