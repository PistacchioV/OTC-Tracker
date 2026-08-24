#!/usr/bin/env python3
"""check_export_advanced.py — protege o `apps/static/js/export-advanced.js`.

O Advanced Export decide QUE LINHAS vão para o arquivo, e as duas decisões que
erram em silêncio são:

  · o INTERVALO DE DIAS — quais datas ele vai buscar, e o que faz com o dia que
    não tem arquivo (que é a maioria dos dias num intervalo qualquer: fim de
    semana, feriado, ou anterior à primeira gravação);
  · o TEXTO DA CÉLULA como o export a vê — um badge de status comparado contra o
    HTML cru nunca casaria com o que está escrito nele.

Nenhuma das duas levanta exceção quando erra: devolvem o recorte errado, e quem
recebe a planilha não tem como saber.

Como o `check_boxparse.py`, este script roda a cópia real do JavaScript no `jsc`
do macOS (JavaScriptCore) em vez de reimplementar a regra em Python — uma
reimplementação seria uma segunda regra, e as duas divergiriam.

Precisa do `jsc`, então NÃO roda na máquina Windows do time (§163).
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JS = os.path.join(ROOT, 'apps', 'static', 'js', 'export-advanced.js')
JSC = ('/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/'
       'Helpers/jsc')

FAILURES = []


def check(label, got, want):
    ok = str(got) == str(want)
    print(('ok   ' if ok else 'FAIL ') + label + '  ->  ' + repr(got))
    if not ok:
        FAILURES.append('%s: esperado %r, veio %r' % (label, want, got))


def extract(src, name):
    """A função `name` do arquivo, por contagem de chaves."""
    i = src.index('function %s(' % name)
    j = src.index('{', i)
    depth = 0
    while True:
        ch = src[j]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1


def main():
    if not os.path.exists(JSC):
        print('jsc não encontrado — este check só roda no macOS (§163). Pulando.')
        return 0

    src = open(JS, encoding='utf-8').read()

    # O MAX_DAYS é a trava do intervalo e é lido pelo dayList.
    m = re.search(r'var MAX_DAYS = (\d+)', src)
    if not m:
        print('FAIL MAX_DAYS não encontrado no arquivo')
        return 1
    max_days = int(m.group(1))

    # `plain` usa um <textarea> para decodificar entidades; fora do navegador o
    # stub faz o mesmo com os casos que interessam. `t` devolve a chave, que é o
    # bastante para o rótulo da Reference Date.
    harness = ("var MAX_DAYS = %d;\n" % max_days
               + "var DAY_TIMEOUT_MS = 60000;\n"
               + "function setTimeout(f, ms) { return 0; }\n"
               + "function clearTimeout(id) {}\n"
               + "var _decoder = null;\n"
               # Um feriado no meio do intervalo do relato (05/08–24/08).
               + "var _holidays = {'2026-08-06': 1};\n"
               + "function t(k) { return k; }\n"
               + "var document = { createElement: function () {\n"
               + "  return { set innerHTML(v) { this.value = String(v)\n"
               + "      .replace(/&amp;/g, '&').replace(/&lt;/g, '<')\n"
               + "      .replace(/&gt;/g, '>').replace(/&quot;/g, '\"'); }, value: '' };\n"
               + "},\n"
               # O `defaultName` lê o <h4> do cabeçalho da página; aqui ele é
               # trocado por caso de teste.
               + "  querySelector: function () {\n"
               + "    return _PAGE_H4 === null ? null : { textContent: _PAGE_H4 };\n"
               + "  } };\n"
               + "var _PAGE_H4 = null, baseName = '', daily = null;\n")
    for name in ('plain', 'normDaily', 'pad2', 'ymd', 'isBizDay', 'dayList',
                 'fetchDays', 'defaultName', 'flatDay', 'todayIso', 'finalName'):
        harness += extract(src, name) + '\n'

    harness += r"""
    function out(k, v) { print(k + '\t' + v); }

    out('plain-tag',   plain('<span class="badge bg-success">Matched</span>'));
    out('plain-ent',   plain('ACME &amp; CO'));
    out('plain-nl',    plain('linha1\n   linha2'));

    // `daily` aceita a URL crua; os padrões são os da maioria das telas.
    var d1 = normDaily('/api/operations-b3/data');
    out('daily-url',   d1.url);
    out('daily-param', d1.param);
    out('daily-rows',  d1.rows);
    // As recons fogem dos dois padrões: `recon_date` e `data`.
    var d2 = normDaily({ url: '/reconciliation-fxo/data', param: 'recon_date', rows: 'data' });
    out('daily-param2', d2.param);
    out('daily-rows2',  d2.rows);
    out('daily-none',   normDaily('') === null);
    out('daily-nourl',  normDaily({ param: 'date' }) === null);

    out('biz-sab',     isBizDay('2026-08-22'));
    out('biz-dom',     isBizDay('2026-08-23'));
    out('biz-seg',     isBizDay('2026-08-24'));
    out('biz-feriado', isBizDay('2026-08-06'));
    // O intervalo do relato: 05/08 a 24/08 tem 20 dias de calendário e 13 dias
    // úteis — 6 de fim de semana e o feriado do stub ficam de fora. Eram 7 dias
    // pedidos à toa, e cada um deles entrava na conta de "não consegui ler".
    out('dias-cal',    dayList('2026-08-05', '2026-08-24').length);
    out('dias-uteis',  dayList('2026-08-05', '2026-08-24', true).length);
    out('dias-sem-fds', dayList('2026-08-22', '2026-08-23', true).length);
    out('dias-1',      dayList('2026-08-24', '2026-08-24').join(','));
    out('dias-3',      dayList('2026-08-24', '2026-08-26').join(','));
    // Vira o mês e o ano sem pular nem repetir dia.
    out('dias-mes',    dayList('2026-07-30', '2026-08-02').join(','));
    out('dias-ano',    dayList('2026-12-30', '2027-01-02').join(','));
    // Ano bissexto: 2028 tem 29/02.
    out('dias-bissex', dayList('2028-02-27', '2028-03-01').join(','));
    out('dias-invert', dayList('2026-08-26', '2026-08-24').length);
    out('dias-lixo',   dayList('nao-e-data', '2026-08-24').length);

    // ── o NOME do arquivo ──────────────────────────────────────────────
    // O padrão do app é "Nome Legível - AAAAMMDD" (o mesmo do anexo do BACC),
    // e não o slug do id da tabela.
    _PAGE_H4 = 'Live Position NDF';
    out('nome-titulo',  defaultName({ id: 'lnndf-table' }));
    _PAGE_H4 = '  Manual Confirmations / Track  ';
    out('nome-limpo',   defaultName({ id: 'x' }));
    _PAGE_H4 = null;                       // página sem cabeçalho: sobra o id
    out('nome-id',      defaultName({ id: 'lnndf-table' }));
    out('nome-vazio',   defaultName({ id: '' }));

    // O carimbo da data. `todayIso` é substituído para o teste não depender do
    // dia em que ele roda.
    todayIso = function () { return '2026-08-24'; };
    baseName = 'Live Position NDF';
    daily = normDaily('/api/x');
    out('carimbo-dia',  finalName({ name: baseName, dayFrom: '', dayTo: '' }));
    out('carimbo-int',  finalName({ name: baseName, dayFrom: '2026-08-11',
                                    dayTo: '2026-08-24' }));
    // Intervalo de um dia só não repete a data.
    out('carimbo-1dia', finalName({ name: baseName, dayFrom: '2026-08-24',
                                    dayTo: '2026-08-24' }));
    // Uma ponta só vale pelas duas.
    out('carimbo-meia', finalName({ name: baseName, dayFrom: '', dayTo: '2026-08-24' }));
    // Renomeado à mão: vale o que foi digitado, sem data nenhuma.
    out('carimbo-mao',  finalName({ name: 'Posicao para o Ze', dayFrom: '2026-08-11',
                                    dayTo: '2026-08-24' }));
    // Tela sem arquivo-dia: as datas nem chegam a existir, e sobra o dia.
    daily = null;
    out('carimbo-sem-daily', finalName({ name: baseName, dayFrom: '2026-08-11',
                                         dayTo: '2026-08-24' }));

    // fetchDays com um fetch de mentira: um dia com linhas, um vazio, um que
    // falha. O dia sem arquivo NÃO é erro — é dia sem movimento.
    var CHAMADAS = [];
    fetch = function (url) {
        CHAMADAS.push(url);
        var d = /date=([^&]+)/.exec(url)[1];
        if (d === '2026-08-25') { return Promise.resolve({ ok: false, status: 404 }); }
        if (d === '2026-08-26') {
            return Promise.resolve({ ok: true, json: function () {
                return Promise.resolve({ columns: ['A', 'B'], rows: [] }); } });
        }
        // O dia SUBSTITUÍDO: a tela andou para trás e devolveu o arquivo de
        // outro dia. Tem linhas, mas não são deste dia.
        if (d === '2026-08-27') {
            return Promise.resolve({ ok: true, json: function () {
                return Promise.resolve({ columns: ['A', 'B'], source_date: '2026-08-24',
                                         rows: [['x1', 'x2']] }); } });
        }
        return Promise.resolve({ ok: true, json: function () {
            return Promise.resolve({ columns: ['A', 'B'],
                                     rows: [['a1', 'b1', 'cauda'], ['a2', 'b2']] }); } });
    };
    var passos = [];
    fetchDays(normDaily('/api/x'), ['2026-08-24', '2026-08-25', '2026-08-26', '2026-08-27'],
              function (i, d) { passos.push(i + ':' + d); })
        .then(function (res) {
            out('fd-cols',     res.columns.join(','));
            out('fd-rows',     JSON.stringify(res.rows));
            out('fd-failed',   res.failed.join(','));
            out('fd-empty',    res.empty.join(','));
            out('fd-passos',   passos.join(' '));
            out('fd-why',      res.why);
            out('fd-serie',    CHAMADAS.join(' '));
        });
    """

    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                     encoding='utf-8') as fh:
        fh.write(harness)
        path = fh.name
    try:
        res = subprocess.run([JSC, path], capture_output=True, text=True)
    finally:
        os.unlink(path)

    if res.returncode != 0:
        print('FAIL o jsc não rodou o harness:\n' + (res.stderr or res.stdout))
        return 1

    got = {}
    for line in res.stdout.splitlines():
        if '\t' in line:
            k, v = line.split('\t', 1)
            got[k] = v

    print('\n== o texto da célula, como o export a vê ==')
    # É assim que um critério "Status é exatamente Matched" casa a linha que a
    # tela pinta de verde.
    check('badge vira texto', got.get('plain-tag'), 'Matched')
    check('entidade decodificada', got.get('plain-ent'), 'ACME & CO')
    check('quebra de linha vira espaço', got.get('plain-nl'), 'linha1 linha2')

    print('\n== o endpoint do dia ==')
    check('a URL crua vira objeto', got.get('daily-url'), '/api/operations-b3/data')
    check('o parâmetro padrão é date', got.get('daily-param'), 'date')
    check('e as linhas vêm em rows', got.get('daily-rows'), 'rows')
    # A Recon FXO usa `recon_date` e devolve `data`: fixar os dois padrões faria
    # o intervalo pedir sempre o mesmo dia e ler uma lista vazia.
    check('a recon usa recon_date', got.get('daily-param2'), 'recon_date')
    check('e devolve em data', got.get('daily-rows2'), 'data')
    # Tela sem arquivo-dia (Reference Data): o `daily` não resolve, e é isso que
    # deixa a seção do intervalo desabilitada em vez de pedir um dia que não há.
    check('sem daily não há intervalo', got.get('daily-none'), 'true')
    check('daily sem url também não', got.get('daily-nourl'), 'true')

    print('\n== só dias úteis: o arquivo nasce em dia útil ==')
    # Pedir sábado, domingo e feriado é pedir o que não existe — e era isso que
    # enchia a lista de "não consegui ler" com dias em que não havia nada a ler.
    check('sábado não', got.get('biz-sab'), 'false')
    check('domingo não', got.get('biz-dom'), 'false')
    check('segunda sim', got.get('biz-seg'), 'true')
    check('feriado ANBIMA não', got.get('biz-feriado'), 'false')
    # O intervalo do relato: 05/08 a 24/08.
    check('20 dias de calendário', got.get('dias-cal'), '20')
    check('e 13 dias úteis', got.get('dias-uteis'), '13')
    check('fim de semana inteiro não devolve dia', got.get('dias-sem-fds'), '0')

    print('\n== o nome do arquivo ==')
    # Nome LEGÍVEL, como a mesa chama a tela — o slug minúsculo era o nome do
    # arquivo de código, não o do documento que se manda por e-mail.
    check('o título da página vira o nome', got.get('nome-titulo'), 'Live Position NDF')
    # A limpeza é a MESMA que o DataTables aplica ao baixar; sem colapsar de
    # novo, a barra removida deixaria dois espaços no meio.
    check('a barra sai e o espaço não dobra', got.get('nome-limpo'),
          'Manual Confirmations Track')
    check('sem cabeçalho sobra o id', got.get('nome-id'), 'lnndf-table')
    check('sem nada nenhum sobra export', got.get('nome-vazio'), 'export')
    # A data é o que distingue a extração de hoje da de ontem na mesma pasta.
    check('sem intervalo carimba o dia', got.get('carimbo-dia'),
          'Live Position NDF - 20260824')
    check('com intervalo vão as duas pontas', got.get('carimbo-int'),
          'Live Position NDF - 20260811 a 20260824')
    check('intervalo de um dia não repete', got.get('carimbo-1dia'),
          'Live Position NDF - 20260824')
    check('uma ponta só vale pelas duas', got.get('carimbo-meia'),
          'Live Position NDF - 20260824')
    # Quem renomeou quis AQUELE nome, e não aquele nome mais uma data.
    check('renomeado à mão sai como foi digitado', got.get('carimbo-mao'),
          'Posicao para o Ze')
    check('tela sem arquivo-dia carimba o dia', got.get('carimbo-sem-daily'),
          'Live Position NDF - 20260824')

    print('\n== os dias do intervalo ==')
    check('um dia só', got.get('dias-1'), '2026-08-24')
    # As duas pontas são inclusivas: pedir 24 a 26 e receber 24 e 25 perderia o
    # último dia sem dizer nada.
    check('as duas pontas entram', got.get('dias-3'),
          '2026-08-24,2026-08-25,2026-08-26')
    check('vira o mês', got.get('dias-mes'),
          '2026-07-30,2026-07-31,2026-08-01,2026-08-02')
    check('vira o ano', got.get('dias-ano'),
          '2026-12-30,2026-12-31,2027-01-01,2027-01-02')
    check('ano bissexto', got.get('dias-bissex'),
          '2028-02-27,2028-02-28,2028-02-29,2028-03-01')
    check('intervalo invertido não devolve dia', got.get('dias-invert'), '0')
    check('data inválida não devolve dia', got.get('dias-lixo'), '0')

    print('\n== a leitura dos dias ==')
    # A Reference Date entra na FRENTE e é a razão de ser deste export: sem ela o
    # arquivo de vinte dias não diz de que dia é cada linha.
    check('a Reference Date encabeça', got.get('fd-cols'), 'refDate,A,B')
    # A linha pode trazer uma cauda que a página usa (status, maker, id): o que
    # entra é o tamanho do cabeçalho, senão as colunas saem deslocadas.
    check('a cauda da linha não entra',
          got.get('fd-rows'), '[["2026-08-24","a1","b1"],["2026-08-24","a2","b2"]]')
    check('o dia que falhou é reportado', got.get('fd-failed'), '2026-08-25')
    # Dia sem linha não é falha: é dia sem movimento.
    check('o dia vazio e o substituído entram como sem arquivo',
          got.get('fd-empty'), '2026-08-26,2026-08-27')
    check('o progresso conta os dias', got.get('fd-passos'),
          '1:2026-08-24 2:2026-08-25 3:2026-08-26 4:2026-08-27')
    # O dia que a tela SUBSTITUIU pelo arquivo de outro é pulado como se não
    # houvesse arquivo — que é o que de fato não há. Aceitá-lo poria o mesmo dia
    # duas vezes na planilha, com duas datas diferentes.
    check('o dia substituído não entra',
          got.get('fd-rows').find('x1'), -1)
    # EM SÉRIE, um pedido por vez: em paralelo, um intervalo de três meses
    # abriria noventa requisições sobre o processo único que serve a mesa.
    # `exact=1` desliga a busca para trás do servidor — sem ele, o dia sem arquivo
    # volta com o do dia anterior.
    check('os dias são pedidos em série, com exact', got.get('fd-serie'),
          '/api/x?date=2026-08-24&exact=1 /api/x?date=2026-08-25&exact=1 '
          '/api/x?date=2026-08-26&exact=1 /api/x?date=2026-08-27&exact=1')
    # A falha vem com o MOTIVO: "não consegui ler 20 dias" não diz se foi rota
    # errada, sessão vencida ou erro do servidor — e sem isso não há o que
    # investigar. (Foi um 404 de endpoint novo sem restart do Flask.)
    check('a falha diz o motivo', got.get('fd-why'), 'HTTP 404')

    print('\n== o relógio do carimbo ==')
    # `todayIso` tem de ler o relógio LOCAL. Com `getUTC*` — que é o que o
    # `ymd()` das datas do intervalo usa, e por bom motivo — toda exportação
    # feita depois das 21h no Brasil sairia carimbada com o dia seguinte.
    fonte_hoje = extract(src, 'todayIso')
    check('todayIso lê o relógio local', 'getUTC' not in fonte_hoje, True)
    check('e o ymd do intervalo continua em UTC',
          'getUTC' in extract(src, 'ymd'), True)

    print('\n== o spinner da exportação ==')
    # O popup do spinner NÃO pode entrar animado. A `swal2-show` vai de
    # `opacity:0` a 1 em 0,3 s e o trabalho síncrono começa no quadro seguinte:
    # a caixa congela com ~5% de opacidade e a espera inteira se lê como "o
    # SweetAlert apareceu e sumiu".
    i = src.find("t('exporting')")
    bloco = src[i:i + 1200] if i != -1 else ''
    check('o popup do spinner abre sem animação',
          "showClass: { popup: ''" in bloco, True)
    # O `showClass` SUBSTITUI o padrão do SweetAlert, não se soma a ele: sem
    # repetir a classe do backdrop, o desfundo perde o escurecido e o blur.
    check('e o backdrop mantém a classe do tema',
          "backdrop: 'swal2-backdrop-show'" in bloco, True)
    # A roda promovida a camada continua girando pelo compositor enquanto a
    # thread principal está presa montando o arquivo.
    check('a roda é promovida a camada própria',
          '.xa-busy .swal2-loader{will-change:transform}' in src, True)
    check('e o popup carrega a classe que a alcança',
          "customClass: { container: 'xa-busy' }" in bloco, True)

    print('\n== a trava do intervalo ==')
    check('o teto é o MAX_DAYS do arquivo', max_days >= 30, True)

    print()
    if FAILURES:
        for f in FAILURES:
            print('FAIL ' + f)
        return 1
    print('todas as asserções passaram')
    return 0


if __name__ == '__main__':
    sys.exit(main())
