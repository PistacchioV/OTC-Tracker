#!/usr/bin/env python3
"""check_fi_calc.py — fórmulas CADASTRÁVEIS do File Interpreter.

Prende o contrato do _fi_calc_value e do hook no motor:
  1. as cinco funções (FIELD/DATE/BIZDIFF/ADDBIZ/LOOKUP), com o campo casado
     pelo nome da COLUNA da página (cego a caixa/espaço) e o BIZDIFF
     zero-padded pela largura do format;
  2. texto que NÃO parseia como fórmula devolve None — vale o gerador, e é o
     que mantém todo cadastro existente byte a byte;
  3. no _fi_build_line, a fórmula VENCE o valor do gerador (e Fixed vence
     tudo), só quando o deal é passado;
  4. o valor EFETIVO (_fi_effective_seq_value): Fixed > fórmula > gerador;
  5. a cópia do navegador (FiTer.calc do fi-ter-pair.js) concorda com o
     servidor, via jsc (pulado sem o binário).
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault('OTC_SHARED_DRIVE_ROOT', tempfile.gettempdir())

from apps.pages import routes as R  # noqa: E402

FAILS = []


def check(name, cond, extra=''):
    if cond:
        print('  ok    ' + name)
    else:
        print(' FAIL   ' + name + (' — ' + extra if extra else ''))
        FAILS.append(name)


DEAL = {
    'LastFixingDate': '2026-08-21',      # sexta
    'SettlementDate': '2026-08-25',      # terça — 2 dias úteis depois
    'QuantityCurrency': 'USD',
    'Deal': 'D5VL-1',
}


def main():
    calc = R._fi_calc_value

    check("FIELD pelo nome da coluna ('Last Fixing Date')",
          calc('FIELD(Last Fixing Date)', DEAL) == '2026-08-21')
    check('DATE em AAAAMMDD', calc('DATE(Settlement Date)', DEAL) == '20260825')
    check('BIZDIFF 9(01)', calc('BIZDIFF(Last Fixing Date; Settlement Date)', DEAL, '9(01)') == '2')
    check('BIZDIFF 9(02) zero-padded',
          calc('BIZDIFF(Last Fixing Date; Settlement Date)', DEAL, '9(02)') == '02')
    check('ADDBIZ +2 dias úteis', calc('ADDBIZ(Last Fixing Date; 2)', DEAL) == '20260825')
    check('LOOKUP currency-base USD → 220',
          calc('LOOKUP(currency-base; SIMBOLO; CODIGO DE CADASTRO; Quantity Currency)', DEAL) == '220')
    check('texto livre → None (vale o gerador)', calc('Direction', DEAL) is None)
    check('sem deal → None', calc('DATE(Settlement Date)', None) is None)
    check('argumento inválido degrada para None', calc('ADDBIZ(Last Fixing Date; xx)', DEAL) is None)

    # ── fórmula vence o gerador no motor (template em tempfile) ────────────
    tpl = {'key': 'calc-t', 'name': 'Calc T', 'file_type': 'positional',
           'blocks': [{'id': 'reg', 'title': 'Reg', 'note': '', 'fields': [
               {'seq': '1', 'field': 'A', 'format': 'X(02)', 'position': '1-2',
                'required': '', 'content': '', 'description': '',
                'source': 'Calculated',
                'source_detail': 'BIZDIFF(Last Fixing Date; Settlement Date)',
                'source_note': ''},
               {'seq': '2', 'field': 'B', 'format': 'X(04)', 'position': '3-6',
                'required': '', 'content': '', 'description': '',
                'source': 'Calculated', 'source_detail': 'nota livre',
                'source_note': ''},
           ]}]}
    tmp = tempfile.mkdtemp(prefix='fi-calc-')
    old_dir = R._FILE_INTERPRETER_DIR
    try:
        with open(os.path.join(tmp, 'calc-t.json'), 'w', encoding='utf-8') as fh:
            json.dump(tpl, fh)
        R._FILE_INTERPRETER_DIR = tmp
        R._fi_tpl_cache.clear()
        line = R._fi_build_line('calc-t', 'reg', {'1': 'XX', '2': 'GEN '}, deal=DEAL)
        check('fórmula vence o gerador', line[:2] == '02', repr(line[:2]))
        check('nota livre mantém o gerador', line[2:6] == 'GEN ', repr(line[2:6]))
        line2 = R._fi_build_line('calc-t', 'reg', {'1': 'XX', '2': 'GEN '})
        check('sem deal, tudo é do gerador', line2[:2] == 'XX')
        check('efetivo: fórmula',
              R._fi_effective_seq_value('calc-t', 'reg', '1', {'1': 'XX'}, deal=DEAL) == '02')
        check('efetivo: gerador no texto livre',
              R._fi_effective_seq_value('calc-t', 'reg', '2', {'2': 'GEN '}, deal=DEAL) == 'GEN ')
    finally:
        R._FILE_INTERPRETER_DIR = old_dir
        R._fi_tpl_cache.clear()
        shutil.rmtree(tmp, ignore_errors=True)

    # ── a cópia do navegador concorda (jsc) ────────────────────────────────
    jsc = shutil.which('jsc') or \
        '/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc'
    if os.path.exists(jsc):
        js = open(os.path.join(ROOT, 'apps', 'static', 'js', 'fi-ter-pair.js'),
                  encoding='utf-8').read()
        hols = json.dumps(sorted(R._anbima_holidays()))
        rows = json.dumps(R._mapping_rows('currency-base'))
        cases = [
            ['FIELD(Last Fixing Date)', ''],
            ['DATE(Settlement Date)', ''],
            ['BIZDIFF(Last Fixing Date; Settlement Date)', '9(02)'],
            ['ADDBIZ(Last Fixing Date; 2)', ''],
            ['LOOKUP(currency-base; SIMBOLO; CODIGO DE CADASTRO; Quantity Currency)', ''],
            ['Direction', ''],
        ]
        harness = (js +
                   '\nFiTer.setHolidays(' + hols + ');' +
                   "\nFiTer.setMappingRows('currency-base', " + rows + ');' +
                   '\nvar DEAL = ' + json.dumps(DEAL) + ';' +
                   '\nvar CASES = ' + json.dumps(cases) + ';' +
                   '\nprint(JSON.stringify(CASES.map(function (c) '
                   '{ return FiTer.calc(c[0], DEAL, c[1]); })));')
        out = subprocess.run([jsc, '-e', 'var window = this;\n' + harness],
                             capture_output=True, text=True)
        got = json.loads(out.stdout.strip() or '[]')
        want = [R._fi_calc_value(c[0], DEAL, c[1]) for c in cases]
        check('FiTer.calc concorda com o servidor ({} casos)'.format(len(cases)),
              got == want, '{} != {}'.format(got, want))
    else:
        print('  skip  FiTer.calc (jsc indisponível nesta máquina)')

    print()
    if FAILS:
        print('{} FAIL'.format(len(FAILS)))
        sys.exit(1)
    print('all ok')
    sys.exit(0)


if __name__ == '__main__':
    main()
