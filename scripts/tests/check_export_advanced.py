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
               # O nome do padrão lê o <title> (a página) e o
               # `data-export-name` da tabela; aqui os dois são trocados por
               # caso de teste.
               + "  title: '',\n"
               + "  querySelector: function (sel) { return _NODES[sel] || null; } };\n"
               + "var _NODES = {}, daily = null;\n"
               + "function node(lbl) { return { getAttribute: function () { return lbl; } }; }\n"
               + "var EXPORT_SUFFIX = ' - OTC Tracker - OTC Processing System';\n")
    for name in ('plain', 'normDaily', 'pad2', 'ymd', 'isBizDay', 'dayList',
                 'fetchDays', 'pageName', 'exportLabel', 'exportTitle', 'exportFile',
                 'finalName'):
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

    // ── o NOME do arquivo (mesa, 21/10/2026) ───────────────────────────
    // `<Página ou tabela> - OTC Tracker - OTC Processing System`. A página é
    // o <title> antes do " | " (o nome em inglês; o <h4> é traduzido).
    document.title = 'Live Position NDF | OTC Tracker - Sistema de Gestão OTC';
    out('nome-pagina',  exportFile(null));
    out('titulo-pagina', exportTitle(null));
    document.title = 'Intrag — DCE NDF | OTC Tracker - Sistema de Gestão OTC';
    out('nome-travessao', exportFile(null));
    // A TABELA vence a página; a barra sai do nome e fica no título.
    out('nome-tabela',  exportFile(node('API/Bob Reports Links')));
    out('titulo-tabela', exportTitle(node('API/Bob Reports Links')));
    out('nome-rotulo',  exportFile('Reference Data'));
    _NODES['#t'] = node('NDF Summary - Trade Level');
    out('nome-seletor', exportFile('#t'));
    out('nome-sem-rotulo', exportFile(node('')));
    document.title = '';
    out('nome-vazio',   exportFile(null));

    // O Advanced Export: o nome é o do CAMPO, sem data.
    document.title = 'Live Position NDF | OTC Tracker';
    var baseName = exportFile(null);
    daily = normDaily('/api/x');
    out('final-dia',  finalName({ name: baseName, dayFrom: '', dayTo: '' }));
    out('final-int',  finalName({ name: baseName, dayFrom: '2026-08-11', dayTo: '2026-08-24' }));
    out('final-mao',  finalName({ name: 'Posicao para o Ze', dayFrom: '2026-08-11', dayTo: '2026-08-24' }));
    out('final-barra', finalName({ name: 'Recorte A/B', dayFrom: '', dayTo: '' }));
    out('final-vazio', finalName({ name: '', dayFrom: '', dayTo: '' }));

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
    SUF = ' - OTC Tracker - OTC Processing System'
    # Um padrão só (mesa, 21/10/2026): a página, ou a tabela, mais o sistema.
    check('a página vira o nome', got.get('nome-pagina'), 'Live Position NDF' + SUF)
    check('o título dentro do arquivo é o mesmo texto', got.get('titulo-pagina'),
          'Live Position NDF' + SUF)
    # O travessão de "Intrag — DCE NDF" vira espaço: o separador do padrão é o
    # hífen, e os dois juntos não se leem.
    check('o travessão do título vira espaço', got.get('nome-travessao'), 'Intrag DCE NDF' + SUF)
    check('o rótulo da tabela vence a página; a barra vira hífen no nome',
          got.get('nome-tabela'), 'API-Bob Reports Links' + SUF)
    check('...e fica no título', got.get('titulo-tabela'), 'API/Bob Reports Links' + SUF)
    check('rótulo em texto (o /mapping)', got.get('nome-rotulo'), 'Reference Data' + SUF)
    check('seletor lê o data-export-name', got.get('nome-seletor'), 'NDF Summary - Trade Level' + SUF)
    check('tabela sem rótulo é a página', got.get('nome-sem-rotulo'), 'Intrag DCE NDF' + SUF)
    check('sem página nem rótulo sobra Export', got.get('nome-vazio'), 'Export' + SUF)
    # Sem data: o padrão não leva, e o intervalo está nas linhas.
    check('Advanced: sem intervalo, o nome do padrão', got.get('final-dia'), 'Live Position NDF' + SUF)
    check('Advanced: com intervalo, o MESMO nome (sem data)', got.get('final-int'),
          'Live Position NDF' + SUF)
    # Quem renomeou quis AQUELE nome.
    check('Advanced: renomeado à mão sai como foi digitado', got.get('final-mao'), 'Posicao para o Ze')
    check('Advanced: a barra digitada vira hífen', got.get('final-barra'), 'Recorte A-B')
    check('Advanced: campo apagado volta ao padrão', got.get('final-vazio'), 'Live Position NDF' + SUF)

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

    print('\n== o relógio do intervalo ==')
    # O nome não leva mais data (o carimbo `todayIso` saiu, 21/10/2026); o que
    # fica é o `ymd()` das datas do intervalo, em UTC de propósito (lê ISO).
    check('o ymd do intervalo continua em UTC',
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
