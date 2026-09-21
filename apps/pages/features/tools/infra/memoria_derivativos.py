# -*- coding: utf-8 -*-
"""A memória de cálculo em Excel do NDF Calculator, do Unwind NDF Calculator e
do Option Calculator — a MESMA lógica da memória do swap (`memoria_xlsx`, §455).

As regras que vêm de lá, e que valem aqui sem exceção:

- **a memória é FÓRMULA, não valor**: toda célula derivada é fórmula de Excel
  encadeada até as entradas, e mexer numa entrada refaz a conta;
- **fórmula vai com o VALOR gravado junto** (`_cache_das_formulas` + `_selar`):
  o openpyxl escreve o cache vazio, e o Modo de Exibição Protegido, o preview do
  anexo e o Excel Online mostrariam a memória inteira em branco;
- **o documento é do BANCO**: timbre em A1, nada do sistema que o gerou, valores
  à esquerda, texto executivo — com a parte devedora NOMEADA.

Nada de conta escrita duas vezes: o que o motor (`precificador/derivativos.py`)
calcula, a planilha recalcula por fórmula, e o `check_tools_calculators.py`
cobra que o valor em cache da planilha seja o do motor.

As funções de planilha usadas são só as que o avaliador do `memoria_xlsx`
conhece (as quatro operações, `^`, IF/AND/MAX/ABS/ROUND) — por isso a média da
asiática é a soma explícita das células dividida pela contagem, e não AVERAGE.
"""
import io
from datetime import date

from apps.pages.features.tools.infra import memoria_xlsx as _mx
from apps.pages.precificador import derivativos

BANCO = 'Banco J.P. Morgan'
TAXA_FMT = '0.00000000'
QTD_FMT = '#,##0.00######'


def _abrir(subtitulo):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = _mx.ABA
    ws.sheet_view.showGridLines = False
    for letra, w in (('A', 42), ('B', 22), ('C', 24), ('D', 72)):
        ws.column_dimensions[letra].width = w
    _mx._timbre(ws, 'Memória de Cálculo', subtitulo)
    f = _mx._Folha(ws)
    f.linha = 4
    return wb, ws, f


def _fechar(wb, ws, f, emitido_em=None):
    f.pular()
    f.nota('As células em fórmula trazem o valor apurado e recalculam quando uma entrada muda.')
    f.nota('Emitido em {:%d/%m/%Y}.'.format(emitido_em or date.today()))
    ws.freeze_panes = 'A4'
    wb.properties.creator = 'J.P. Morgan'
    wb.properties.lastModifiedBy = 'J.P. Morgan'
    wb.properties.title = 'Memória de Cálculo'
    wb.properties.description = None
    cache = _mx._cache_das_formulas(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return _mx._selar(buf.getvalue(), cache)


def _identificacao(f, cetip_id, contraparte, classe='', emissao=None):
    f.secao('Identificação')
    f.campo('CETIP ID', cetip_id or '—')
    f.campo('Contraparte', contraparte or '—')
    if classe:
        f.campo('Classe do ativo subjacente', classe)
    if emissao:
        f.campo('Data de emissão', _mx._data(emissao), _mx.DATA_FMT)


def _devedora(f, resultado_ref, direcao, contraparte):
    """A parte devedora NOMEADA — texto, porque o avaliador não concatena; o
    sinal que a decide está na célula do resultado, logo acima."""
    nome = contraparte or 'Contraparte'
    quem = BANCO if direcao == 'PAY' else (nome if direcao == 'RECEIVE' else '—')
    f.campo('Parte devedora', quem, nota='parte com resultado negativo: resultado do banco em {} '
                                         '(positivo, o banco recebe)'.format(resultado_ref.replace('$', '')))


# ── NDF no vencimento ────────────────────────────────────────────────────────

def ndf(r, moeda, vencimento, cetip_id='', contraparte='', classe='', emissao=None,
        nocional_informado=None, fixo_em_reais=False, fixing_nota='', paridade_nota='',
        ativo='', emitido_em=None):
    mercadoria = r.paridade != 1.0 or 'commodit' in (classe or '').lower()
    wb, ws, f = _abrir('Liquidação de termo{} em {:%d/%m/%Y}'.format(
        ' de mercadoria' if mercadoria else ' de moeda', vencimento))
    _identificacao(f, cetip_id, contraparte, classe, emissao)
    f.campo('Vencimento', _mx._data(vencimento), _mx.DATA_FMT)
    if ativo:
        f.campo('Ativo subjacente', ativo)

    f.secao('Entradas')
    f.campo('Posição do banco', 'Comprado' if r.sinal > 0 else 'Vendido',
            nota='na moeda estrangeira' if not mercadoria else 'na mercadoria')
    sinal = f.campo('Sinal da posição', int(r.sinal), _mx.INT_FMT,
                    nota='+1 com o banco comprado, −1 com o banco vendido')
    f.campo('Moeda', moeda)
    informado = nocional_informado if nocional_informado is not None else r.nocional_me
    noc = f.campo('Quantidade' if mercadoria else 'Nocional informado', informado, _mx.MOEDA_FMT)
    fixo = f.campo('Nocional fixo em reais', bool(fixo_em_reais),
                   nota='na B3 o contrato é em moeda estrangeira: o valor em reais divide pela taxa a termo')
    termo = f.campo('Preço a termo' if mercadoria else 'Taxa a termo', r.taxa_termo, TAXA_FMT)
    me = f.campo('Quantidade apurada' if mercadoria else 'Nocional em moeda estrangeira',
                 '=IF({x},{n}/{t},{n})'.format(x=fixo, n=noc, t=termo), _mx.MOEDA_FMT)
    fixing = f.campo('Preço de fixing' if mercadoria else 'Fixing', r.fixing, TAXA_FMT,
                     nota=fixing_nota or ('preço do ativo no fixing' if mercadoria else 'taxa informada'))
    par = None
    if mercadoria:
        par = f.campo('Paridade para reais', r.paridade, TAXA_FMT,
                      nota=paridade_nota or 'taxa informada')

    f.secao('Apuração')
    dif = f.campo('Fixing − termo', '={}-{}'.format(fixing, termo), TAXA_FMT)
    expr = '{m}*{d}*{s}'.format(m=me, d=dif, s=sinal) + ('*{}'.format(par) if par else '')
    liq = f.campo('Liquidação (resultado do banco)', '=ROUND({},2)'.format(expr), _mx.MOEDA_FMT,
                  nota='positivo, o banco recebe; negativo, o banco paga', destaque=True)
    _devedora(f, liq, r.direcao, contraparte)

    f.secao('Imposto de renda')
    retem = f.campo('Retém IR na fonte', not r.isento,
                    nota='contraparte isenta pelo cadastro NDF IR Exempt' if r.isento
                    else 'retenção pela fonte pagadora')
    aliq = f.campo('Alíquota', derivativos.ALIQUOTA_IR_TERMO, '0.0000%',
                   nota='0,005% sobre a liquidação em que o banco paga')
    ir = f.campo('IR da operação', '=IF(AND({r},{l}<0),ROUND(ABS({l})*{a},2),0)'.format(
        r=retem, l=liq, a=aliq), _mx.MOEDA_FMT)
    f.campo('Líquido ao cliente', '=IF({l}<0,ABS({l})-{i},0)'.format(l=liq, i=ir),
            _mx.MOEDA_FMT, destaque=True)
    f.pular()
    f.nota('Imposto inferior a R$ 1,00 não é retido e fica acumulado contra a contraparte no mês; '
           'o piso é apurado sobre o acumulado mensal, não sobre a operação.')
    return _fechar(wb, ws, f, emitido_em)


# ── recompra de NDF ──────────────────────────────────────────────────────────

def unwind_ndf(r, moeda, liquidacao, vencimento, cetip_id='', contraparte='', classe='',
               emissao=None, nocional_informado=None, fixo_em_reais=False, du_contado=False,
               original_informado=None, ja_recomprado=0.0, emitido_em=None):
    wb, ws, f = _abrir('Recompra de termo de moeda em {:%d/%m/%Y}'.format(liquidacao))
    _identificacao(f, cetip_id, contraparte, classe, emissao)
    f.campo('Liquidação da recompra', _mx._data(liquidacao), _mx.DATA_FMT)
    f.campo('Vencimento do contrato', _mx._data(vencimento), _mx.DATA_FMT)

    f.secao('Entradas')
    f.campo('Posição do banco no contrato original', 'Comprado' if r.sinal > 0 else 'Vendido',
            nota='na moeda estrangeira')
    sinal = f.campo('Sinal da posição', int(r.sinal), _mx.INT_FMT,
                    nota='+1 com o banco comprado, −1 com o banco vendido')
    f.campo('Moeda', moeda)
    informado = nocional_informado if nocional_informado is not None else r.nocional_me
    noc = f.campo('Nocional recomprado informado', informado, _mx.MOEDA_FMT)
    fixo = f.campo('Nocional fixo em reais', bool(fixo_em_reais),
                   nota='os valores em reais dividem pelo strike')
    strike = f.campo('Strike (taxa a termo original)', r.strike, TAXA_FMT)
    me = f.campo('Nocional recomprado em moeda estrangeira',
                 '=IF({x},{n}/{k},{n})'.format(x=fixo, n=noc, k=strike), _mx.MOEDA_FMT)
    term = f.campo('Taxa da recompra', r.taxa_recompra, TAXA_FMT)
    pre = f.campo('Taxa pré (a.a.)', r.taxa_pre, _mx.PCT_FMT)
    du = f.campo('Dias úteis até o vencimento', int(r.du), _mx.INT_FMT,
                 nota='contados no calendário ANBIMA, da liquidação da recompra ao vencimento'
                 if du_contado else 'informados')

    f.secao('Apuração')
    dif = f.campo('Recompra − strike', '={}-{}'.format(term, strike), TAXA_FMT)
    f.campo('Valor futuro', '=ROUND({m}*{d}*{s},2)'.format(m=me, d=dif, s=sinal), _mx.MOEDA_FMT)
    fator = f.campo('Fator de desconto', '=(1+{p})^({d}/252)'.format(p=pre, d=du), _mx.FATOR_FMT,
                    nota='(1 + pré) ^ (DU / 252)')
    res = f.campo('Resultado da recompra (valor presente, do banco)',
                  '=ROUND({m}*{d}*{s}/{f},2)'.format(m=me, d=dif, s=sinal, f=fator), _mx.MOEDA_FMT,
                  nota='valor futuro trazido a valor presente; positivo, o banco recebe',
                  destaque=True)
    _devedora(f, res, r.direcao, contraparte)

    if r.saldo is not None and original_informado:
        f.secao('Saldo do contrato')
        orig = f.campo('Nocional original informado', original_informado, _mx.MOEDA_FMT)
        antes = f.campo('Já recomprado informado', float(ja_recomprado or 0.0), _mx.MOEDA_FMT)
        orig_me = f.campo('Nocional original em moeda estrangeira',
                          '=IF({x},{o}/{k},{o})'.format(x=fixo, o=orig, k=strike), _mx.MOEDA_FMT)
        antes_me = f.campo('Já recomprado em moeda estrangeira',
                           '=IF({x},{a}/{k},{a})'.format(x=fixo, a=antes, k=strike), _mx.MOEDA_FMT)
        f.campo('Novo valor base', '=MAX({o}-{a}-{m},0)'.format(o=orig_me, a=antes_me, m=me),
                _mx.MOEDA_FMT, nota='original − já recomprado − recomprado nesta operação',
                destaque=True)
        f.campo('Recompra', 'Total' if r.total else 'Parcial')
    return _fechar(wb, ws, f, emitido_em)


# ── opção no exercício ───────────────────────────────────────────────────────

def opcao(r, moeda, exercicio, cetip_id='', contraparte='', classe='', emissao=None,
          paridade_nota='', premio_unitario=0.0, paridade_premio=None, emitido_em=None):
    wb, ws, f = _abrir('Exercício de opção em {:%d/%m/%Y}'.format(exercicio))
    _identificacao(f, cetip_id, contraparte, classe, emissao)
    f.campo('Data de exercício', _mx._data(exercicio), _mx.DATA_FMT)

    f.secao('Entradas')
    f.campo('Tipo', 'Call' if r.tipo == derivativos.CALL else 'Put')
    titular = r.lado == derivativos.TITULAR
    f.campo('Lado do banco', 'Titular' if titular else 'Lançador')
    dono = f.campo('Sinal do lado', 1 if titular else -1, _mx.INT_FMT,
                   nota='+1 com o banco titular (recebe o exercício, paga o prêmio); −1 lançador')
    f.campo('Moeda do preço', moeda)
    strike = f.campo('Strike', r.strike, TAXA_FMT)
    qtd = f.campo('Quantidade', r.quantidade, QTD_FMT)
    refs = []
    for i, p in enumerate(r.fixings, 1):
        refs.append(f.campo('Preço de verificação {}'.format(i) if len(r.fixings) > 1
                            else 'Preço de verificação', p, TAXA_FMT))
    par = f.campo('Paridade para reais', r.paridade, TAXA_FMT,
                  nota=paridade_nota or ('preço já em reais' if r.paridade == 1.0 else 'taxa informada'))
    pu = f.campo('Prêmio unitário', float(premio_unitario or 0.0), TAXA_FMT)
    parp = f.campo('Paridade do prêmio', float(paridade_premio or r.paridade), TAXA_FMT,
                   nota='a do dia do prêmio' if paridade_premio else 'a do exercício')

    f.secao('Apuração')
    media = f.campo('Preço de exercício apurado', '=({})/{}'.format('+'.join(refs), len(refs)),
                    TAXA_FMT, nota='média aritmética dos preços de verificação'
                    if len(refs) > 1 else 'o preço de verificação')
    intr = f.campo('Valor intrínseco (por unidade)',
                   '=MAX(0,{a}-{b})'.format(a=media if r.tipo == derivativos.CALL else strike,
                                            b=strike if r.tipo == derivativos.CALL else media),
                   TAXA_FMT, nota='call: preço − strike; put: strike − preço; nunca negativo')
    payoff = f.campo('Liquidação do exercício', '=ROUND({i}*{q}*{p},2)'.format(i=intr, q=qtd, p=par),
                     _mx.MOEDA_FMT, nota='devida ao titular', destaque=True)
    premio = f.campo('Prêmio', '=ROUND({u}*{q}*{p},2)'.format(u=pu, q=qtd, p=parp),
                     _mx.MOEDA_FMT, nota='pago pelo titular ao lançador')
    ex_b = f.campo('Exercício — resultado do banco', '={}*{}'.format(payoff, dono), _mx.MOEDA_FMT)
    pr_b = f.campo('Prêmio — resultado do banco', '=0-{}*{}'.format(premio, dono), _mx.MOEDA_FMT)
    res = f.campo('Resultado do banco', '=ROUND({}+{},2)'.format(ex_b, pr_b), _mx.MOEDA_FMT,
                  nota='exercício e prêmio liquidam em datas diferentes; a soma é só o resultado',
                  destaque=True)
    f.campo('Exercício', 'Exercida — dentro do dinheiro' if r.exercida else 'Não exercida — fora do dinheiro')
    _devedora(f, res, derivativos._quem(r.resultado), contraparte)
    f.pular()
    f.nota('Barreiras e rebates não são apurados nesta memória.')
    return _fechar(wb, ws, f, emitido_em)
