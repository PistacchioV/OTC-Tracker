#!/usr/bin/env python3
"""check_fi_variants.py — variantes por par de pernas do File Interpreter.

Prova as três garantias do motor de variantes (`base_key`/`le_pair`):
  1. SEM variante cadastrada, tudo é byte a byte o comportamento do base —
     inclusive par sem cadastro e chamadas sem par;
  2. COM variante, o deal cujo par casa usa o layout dela (Fixed da conta,
     Participante do header, `file_name`), e os demais deals seguem no base;
  3. a resolução é cega a caixa/espaço/× no par, respeita a PÁGINA da
     variante e cai no bloco do base quando a variante não tem o bloco.

Também compara a cópia da regra do par que vive no navegador
(`static/js/fi-ter-pair.js`) com a do servidor, campo a campo, via `jsc`
(macOS; sem o binário o bloco é pulado, como no check_boxparse).

Usa um registro em tempfile — o JSON versionado não é tocado.
"""
import copy
import json
import os
import random
import re
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


DEAL_MGT_JPM = dict(
    Deal='FWDS-MGT-9', Client='BANCO J.P. MORGAN S.A.', LE='MGT',
    Status='Success', Direction='SELL', TaxID='',
    TradeDate='2026-08-04', SettlementDate='2026-11-16',
    FirstFixingDate='', LastFixingDate='2026-11-12',
    StrikeSetDate='2026-08-28', StrikeSetOffset='1.25',
    Publisher='PTAX', QuantityCurrency='USD', OtherQuantityCurrency='BRL',
    Notional='750000', IsBRRFixed='NO')

DEAL_JPM_CLI = dict(
    Deal='FWDS-CLI-1', Client='ACME EXPORTADORA S.A.', LE='JPM',
    Status='Success', Direction='BUY', TaxID='12.345.678/0001-90',
    TradeDate='2026-08-03', SettlementDate='2026-09-15',
    FirstFixingDate='', LastFixingDate='2026-09-10',
    StrikeSetDate='2026-08-20', StrikeSetOffset='0.05',
    Publisher='PTAX', QuantityCurrency='USD', OtherQuantityCurrency='BRL',
    Notional='1000000', IsBRRFixed='NO')


def _line(deal):
    random.seed(1234)
    return R._generic_ndf_ter_line(dict(deal), True)


def main():
    # ── Lado do par e par do deal ─────────────────────────────────────────
    check("side: 'BANCO J.P. MORGAN S.A.' → JPM", R._ter_le_side('BANCO J.P. MORGAN S.A.') == 'JPM')
    check("side: 'BANCO SAFRA S.A.' → None (cliente)", R._ter_le_side('BANCO SAFRA S.A.') is None)
    check("side: 'INTRAG LAWTON FDO' → LAWTON", R._ter_le_side('INTRAG LAWTON FDO') == 'LAWTON')
    check("side: 'ATACAMA COMERCIO' → ATACAMA", R._ter_le_side('ATACAMA COMERCIO LTDA') == 'ATACAMA')
    check("side: vazio → None", R._ter_le_side('  ') is None)
    # O CADASTRO le-spn vence a heurística: a razão social da MGT contém
    # 'JPMORGAN', que o regex do JPM casaria primeiro.
    check("side: razão social da MGT (le-spn) → MGT",
          R._ter_le_side('JPMORGAN CHASE BANK, N.A. - SAO PAULO BRANCH') == 'MGT')
    check("side: razão social da MGT com pontuação diferente → MGT",
          R._ter_le_side('JPMORGAN CHASE BANK NA SAO PAULO BRANCH') == 'MGT')
    check("pair simples: JPM × razão social MGT",
          R._ter_le_pair('JPM', 'JPMORGAN CHASE BANK, N.A. - SAO PAULO BRANCH') == 'JPM x MGT')
    check("pair: MGT × JPM", R._ter_le_pair('MGT', 'BANCO J.P. MORGAN S.A.') == 'MGT x JPM')
    check("pair: JPM × cliente → CLI", R._ter_le_pair('JPM', 'ACME EXPORTADORA S.A.') == 'JPM x CLI')
    check("norm: 'mgt  ×  jpm' ≡ 'MGT x JPM'",
          R._fi_le_pair_norm(' mgt  ×  jpm ') == R._fi_le_pair_norm('MGT x JPM'))

    # ── Registro em tempfile: base real + variante MGT x JPM (FWD Start) ──
    src_path = os.path.join(ROOT, 'apps', 'static', 'data', 'file-interpreter',
                            'termo-multiclasses.json')
    with open(src_path, encoding='utf-8') as fh:
        base = json.load(fh)

    variant = copy.deepcopy(base)
    # O par LAWTON x JPM é o que o gerador de fato produz para a linha
    # LE MGT × cliente JPM (a perna espelhada do Lawton) — 'MGT x JPM' só
    # existe nas páginas sem geração de arquivo (Vanilla, via pairSimple).
    variant['key'] = 'termo-multiclasses--lawton-x-jpm'
    variant['name'] = base['name'] + ' — LAWTON x JPM'
    variant['base_key'] = 'termo-multiclasses'
    variant['le_pair'] = 'LAWTON x JPM'
    variant['file_name'] = 'FWDSTART_CUSTOM.txt'
    variant['linked_pages'] = [p for p in base.get('linked_pages', [])
                               if p.get('url') == '/new_deals-ndf-fwdstart']
    for b in variant['blocks']:
        if b['id'] == 'registro-dados-fixos':
            for f in b['fields']:
                if R._fi_seq_key(f['seq']) == '5':      # Lançamento do Participante
                    f['source'] = 'Fixed'
                    f['source_detail'] = '99999999'
                    f.pop('source_by_page', None)
        if b['id'] == 'header':
            for f in b['fields']:
                if R._fi_seq_key(f['seq']) == '4':      # Participante
                    f['source'] = 'Fixed'
                    f['source_detail'] = 'CUSTOMNAME'
                    f.pop('source_by_page', None)
    # variante sem o bloco de Dados Variáveis: o motor cai no bloco do base
    variant['blocks'] = [b for b in variant['blocks']
                         if b['id'] != 'registro-dados-variaveis']

    tmp = tempfile.mkdtemp(prefix='fi-var-')
    try:
        shutil.copy(src_path, os.path.join(tmp, 'termo-multiclasses.json'))
        with open(os.path.join(tmp, variant['key'] + '.json'), 'w', encoding='utf-8') as fh:
            json.dump(variant, fh, ensure_ascii=False, indent=2)

        base_mgt = _line(DEAL_MGT_JPM)[1]
        base_cli = _line(DEAL_JPM_CLI)[1]

        old_dir = R._FILE_INTERPRETER_DIR
        R._FILE_INTERPRETER_DIR = tmp
        R._fi_tpl_cache.clear()
        try:
            # resolução da chave
            check('variant_key: par + página casam → variante',
                  R._fi_variant_key('termo-multiclasses', '/new_deals-ndf-fwdstart',
                                    'LAWTON x JPM') == variant['key'])
            check('variant_key: par cego a caixa/×',
                  R._fi_variant_key('termo-multiclasses', '/new_deals-ndf-fwdstart',
                                    'lawton × jpm') == variant['key'])
            check('variant_key: outra página → base',
                  R._fi_variant_key('termo-multiclasses', '/new_deals-ndf-otherpublisher',
                                    'LAWTON x JPM') == 'termo-multiclasses')
            check('variant_key: par sem cadastro → base',
                  R._fi_variant_key('termo-multiclasses', '/new_deals-ndf-fwdstart',
                                    'JPM x CLI') == 'termo-multiclasses')
            check('variant_key: sem par → base',
                  R._fi_variant_key('termo-multiclasses', '/new_deals-ndf-fwdstart',
                                    None) == 'termo-multiclasses')
            check('file_name: da variante para o par',
                  R._fi_variant_file_name('termo-multiclasses', '/new_deals-ndf-fwdstart',
                                          'LAWTON x JPM') == 'FWDSTART_CUSTOM.txt')
            check('file_name: sem variante → vazio',
                  R._fi_variant_file_name('termo-multiclasses', '/new_deals-ndf-fwdstart',
                                          'JPM x CLI') == '')

            # linha do deal LE MGT × cliente JPM (par efetivo LAWTON x JPM):
            # só o participante muda — o campo 5 vem depois de
            # TER(5)+tipo(1)+op(4)+controle X(10): posições 21-28
            var_mgt = _line(DEAL_MGT_JPM)[1]
            check('deal LAWTON x JPM: participante vem do Fixed da variante',
                  var_mgt[20:28] == '99999999', repr(var_mgt[20:28]))
            check('deal LAWTON x JPM: resto da linha idêntico ao base',
                  var_mgt[:20] == base_mgt[:20] and var_mgt[28:] == base_mgt[28:])
            check('linha da variante mantém 648 chars', len(var_mgt) == 648, str(len(var_mgt)))

            # deal de par SEM variante: byte a byte o base
            check('deal JPM x CLI: intocado pela variante',
                  _line(DEAL_JPM_CLI)[1] == base_cli)

            # header: Participante Fixed da variante, sem exigir b3-accounts
            hdr = R._ter_file_header('LAWTON', '20260810', '/new_deals-ndf-fwdstart',
                                     le_pair='LAWTON x JPM')
            check('header da variante: Participante do Fixed',
                  hdr[10:30] == 'CUSTOMNAME'.ljust(20), repr(hdr[10:30]))
            hdr_base = R._ter_file_header('LAWTON', '20260810', '/new_deals-ndf-fwdstart')
            check('header sem par: o de sempre (b3-accounts)',
                  hdr_base[10:30] == 'INTRAGLAWTONFDO'.ljust(20), repr(hdr_base[10:30]))

            # bloco ausente na variante cai no bloco do base
            line2 = R._fi_build_line('termo-multiclasses', 'registro-dados-variaveis',
                                     {'4': '20260901'.ljust(8),
                                      '6': ''.ljust(18)},
                                     page_url='/new_deals-ndf-fwdstart',
                                     le_pair='LAWTON x JPM')
            line2_base = R._fi_build_line('termo-multiclasses', 'registro-dados-variaveis',
                                          {'4': '20260901'.ljust(8),
                                           '6': ''.ljust(18)},
                                          page_url='/new_deals-ndf-fwdstart')
            check('bloco ausente na variante → bloco do base', line2 == line2_base)
        finally:
            R._FILE_INTERPRETER_DIR = old_dir
            R._fi_tpl_cache.clear()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ── A cópia do navegador concorda com a do servidor (jsc, macOS) ──────
    import shutil as _sh2
    jsc = _sh2.which('jsc') or \
        '/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc'
    cases = [
        ('MGT',    'BANCO J.P. MORGAN S.A.'),
        ('JPM',    'JPMORGAN CHASE BANK, N.A. - SAO PAULO BRANCH'),
        ('JPM',    'ACME EXPORTADORA S.A.'),
        ('JPM',    'MGT BANK LTDA'),
        ('JPM',    'INTRAG LAWTON FDO'),
        ('JPM',    'ATACAMA COMERCIO LTDA'),
        ('LAWTON', 'BANCO J.P. MORGAN S.A.'),
        ('',       'BANCO J.P. MORGAN S.A.'),
        ('',       'USINA BOA VISTA S.A.'),
        ('MGT',    ''),
    ]

    def py_pair(le, client):
        """A perna nossa como o gerador decide o bucket (LE Lawton, cliente
        JPM = perna espelhada, LE MGT), depois o par pelo helper real."""
        le_u = (le or '').upper()
        if 'LAWTON' in le_u:
            ours = 'LAWTON'
        elif R._ter_le_side(client) == 'JPM':
            ours = 'LAWTON'
        else:
            ours = 'MGT' if le_u.strip() == 'MGT' else 'JPM'
        return R._ter_le_pair(ours, client)

    if os.path.exists(jsc):
        js = open(os.path.join(ROOT, 'apps', 'static', 'js', 'fi-ter-pair.js'),
                  encoding='utf-8').read()
        # As MESMAS entidades que o servidor lê (o navegador as busca em
        # /api/mappings/le-spn; no jsc não há fetch, então o teste injeta).
        entities = json.dumps(R._mapping_rows('le-spn'))
        harness = (js + '\nFiTer.setEntities(' + entities + ');'
                   '\nvar CASES = ' + json.dumps(cases) +
                   ';\nprint(JSON.stringify(CASES.map(function (c) '
                   '{ return [FiTer.pair(c[0], c[1]), FiTer.pairSimple(c[0], c[1])]; })));')
        out = subprocess.run([jsc, '-e', 'var window = this;\n' + harness],
                             capture_output=True, text=True)
        got = json.loads(out.stdout.strip() or '[]')
        want = [[py_pair(le, cl),
                 (R._ter_le_side(le) or 'JPM') + ' x ' + (R._ter_le_side(cl) or 'CLI')]
                for le, cl in cases]
        check('fi-ter-pair.js concorda com o servidor ({} casos)'.format(len(cases)),
              got == want, '{} != {}'.format(got, want))
    else:
        print('  skip  fi-ter-pair.js (jsc indisponível nesta máquina)')

    print()
    if FAILS:
        print('{} FAIL'.format(len(FAILS)))
        sys.exit(1)
    print('all ok')
    sys.exit(0)


if __name__ == '__main__':
    main()
