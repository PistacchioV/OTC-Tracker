# -*- coding: utf-8 -*-
"""As contas de TERMO e de OPÇÃO das Tools — NDF Calculator, Unwind NDF
Calculator e Option Calculator.

Puro: sem Flask, sem rede, sem arquivo (só o calendário, para contar dia útil).
Quem busca PTAX e lê formulário é a vertical (`features/tools`); aqui entra
número e sai número, com cada PARCELA da conta no resultado — a tela mostra
como o valor se formou, não só o valor.

As três contas, como a mesa as faz:

  NDF (vencimento)     Liquidação = Nocional ME × (Fixing − Taxa a Termo) × sinal
                       `sinal` = +1 quando o BANCO está comprado na moeda
                       estrangeira. O resultado é o do BANCO: positivo, o banco
                       recebe; negativo, o banco paga.

  Recompra de NDF      Valor Futuro = Nocional ME × (Taxa da Recompra − Strike) × sinal
                       Resultado    = Valor Futuro ÷ (1 + Pré)^(DU/252)
                       É a MESMA fórmula que a página de Unwinds confere contra
                       o aviso do Athena (`unwinds.domain.conferir_apuracao`,
                       verificada contra três operações reais — §488). DU são
                       os dias úteis ANBIMA da liquidação da recompra até o
                       vencimento do contrato.

  Opção (exercício)    Call: max(0, Fixing − Strike) × Quantidade
                       Put:  max(0, Strike − Fixing) × Quantidade
                       × Paridade, quando o preço é em moeda estrangeira. O
                       payoff é de quem é TITULAR; o prêmio é pago pelo titular
                       ao lançador. O resultado é o do BANCO.

**Nocional fixo em reais**: o contrato é em moeda estrangeira na B3, então o
valor em reais se divide pela taxa a termo (o mesmo tratamento do §488).

**IR**: o termo de moeda retém 0,005% sobre a liquidação em que o BANCO PAGA
(§423). O piso de R$ 1,00 é do balde MENSAL da contraparte e não se decide
olhando uma operação — a calculadora mostra o imposto da operação e diz isso.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from apps.pages.precificador.calendario import calendario_anbima, para_data
from apps.pages.precificador.erros import ErroFerramenta

BASE_DU = 252.0
ALIQUOTA_IR_TERMO = 0.00005          # 0,005% (§423)

COMPRADO, VENDIDO = 'comprado', 'vendido'
POSICOES = ((COMPRADO, 'Bank is long the foreign currency (buys)'),
            (VENDIDO, 'Bank is short the foreign currency (sells)'))

CALL, PUT = 'call', 'put'
TIPOS_OPCAO = ((CALL, 'Call'), (PUT, 'Put'))
TITULAR, LANCADOR = 'titular', 'lancador'
LADOS_OPCAO = ((TITULAR, 'Bank is the holder (bought the option)'),
               (LANCADOR, 'Bank is the writer (sold the option)'))


class ErroDerivativo(ErroFerramenta, ValueError):
    """Entrada que não fecha conta nenhuma — a tela mostra a frase."""


def _sinal(posicao):
    if posicao == COMPRADO:
        return 1.0
    if posicao == VENDIDO:
        return -1.0
    raise ErroDerivativo('pick the bank position: long or short the foreign currency')


def _quem(valor):
    """De quem é o caixa, pelo SINAL do resultado do banco — nunca por um campo
    de direção digitado (§488: o aviso do Athena erra o Direction)."""
    if valor > 0:
        return 'RECEIVE'
    if valor < 0:
        return 'PAY'
    return ''


def nocional_me(nocional, taxa_termo, fixo_em_reais=False):
    """O nocional em MOEDA ESTRANGEIRA. No contrato fixo em reais o valor vem
    em BRL e se divide pela taxa a termo — na B3 o contrato é em ME."""
    if nocional is None or nocional <= 0:
        raise ErroDerivativo('the notional must be greater than zero')
    if not fixo_em_reais:
        return float(nocional)
    if not taxa_termo:
        raise ErroDerivativo('a BRL-fixed notional needs the forward rate to convert')
    return float(nocional) / float(taxa_termo)


# ── NDF no vencimento ────────────────────────────────────────────────────────

@dataclass
class LiquidacaoNDF:
    nocional_me: float
    taxa_termo: float
    fixing: float
    diferenca: float                 # fixing − taxa a termo
    sinal: float
    liquidacao: float                # resultado do BANCO, em reais
    direcao: str                     # RECEIVE / PAY (do banco)
    ir: float                        # 0,005% quando o banco paga
    liquido_cliente: Optional[float]  # o que o cliente recebe, líquido de IR
    isento: bool = False


def liquidar_ndf(nocional, taxa_termo, fixing, posicao, fixo_em_reais=False, isento_ir=False):
    if not taxa_termo or taxa_termo <= 0:
        raise ErroDerivativo('the forward rate must be greater than zero')
    if not fixing or fixing <= 0:
        raise ErroDerivativo('the fixing must be greater than zero')
    me = nocional_me(nocional, taxa_termo, fixo_em_reais)
    s = _sinal(posicao)
    dif = float(fixing) - float(taxa_termo)
    liq = round(me * dif * s, 2)
    # O imposto é sobre o ganho do CLIENTE: só quando o banco paga.
    ir = 0.0 if (isento_ir or liq >= 0) else round(abs(liq) * ALIQUOTA_IR_TERMO, 2)
    return LiquidacaoNDF(
        nocional_me=me, taxa_termo=float(taxa_termo), fixing=float(fixing), diferenca=dif,
        sinal=s, liquidacao=liq, direcao=_quem(liq), ir=ir,
        liquido_cliente=(round(abs(liq) - ir, 2) if liq < 0 else None), isento=bool(isento_ir))


# ── Recompra (unwind) de NDF ─────────────────────────────────────────────────

@dataclass
class RecompraNDF:
    nocional_me: float
    strike: float
    taxa_recompra: float
    diferenca: float
    sinal: float
    valor_futuro: float
    taxa_pre: float                  # a.a., fração
    du: int
    fator_desconto: float            # (1 + pré)^(DU/252)
    resultado: float                 # valor presente, do BANCO
    direcao: str
    saldo: Optional[float] = None    # nocional ME que sobra no contrato
    total: Optional[bool] = None     # a recompra zera o contrato?


def dias_uteis_ate(liquidacao, vencimento, calendario=None):
    """DU ANBIMA da liquidação da recompra até o vencimento do contrato."""
    cal = calendario or calendario_anbima()
    d0, d1 = para_data(liquidacao), para_data(vencimento)
    if d1 < d0:
        raise ErroDerivativo('the contract maturity is before the unwind settlement date')
    return cal.dias_uteis(d0, d1)


def recomprar_ndf(nocional, strike, taxa_recompra, taxa_pre, du, posicao,
                  fixo_em_reais=False, nocional_original=None, ja_recomprado=0.0):
    if not strike or strike <= 0:
        raise ErroDerivativo('the strike must be greater than zero')
    if not taxa_recompra or taxa_recompra <= 0:
        raise ErroDerivativo('the termination rate must be greater than zero')
    if du is None or du < 0:
        raise ErroDerivativo('the business days to maturity cannot be negative')
    me = nocional_me(nocional, strike, fixo_em_reais)
    s = _sinal(posicao)
    dif = float(taxa_recompra) - float(strike)
    fv = me * dif * s
    fator = (1.0 + float(taxa_pre or 0.0)) ** (float(du) / BASE_DU)
    res = round(fv / fator, 2)
    saldo = total = None
    if nocional_original:
        # As TRÊS parcelas do Novo Valor Base do Termo (mesa, 18/09/2026):
        # original − já recomprado − recomprado agora.
        original = nocional_me(nocional_original, strike, fixo_em_reais)
        antes = (float(ja_recomprado or 0.0) / float(strike)) if fixo_em_reais else float(ja_recomprado or 0.0)
        saldo = original - antes - me
        if saldo < -0.01:
            raise ErroDerivativo('the unwound notional is larger than what is left in the contract')
        saldo = max(saldo, 0.0)
        total = saldo <= 0.01        # a posição imprime duas casas
    return RecompraNDF(
        nocional_me=me, strike=float(strike), taxa_recompra=float(taxa_recompra), diferenca=dif,
        sinal=s, valor_futuro=round(fv, 2), taxa_pre=float(taxa_pre or 0.0), du=int(du),
        fator_desconto=fator, resultado=res, direcao=_quem(res), saldo=saldo, total=total)


# ── Opção no exercício ───────────────────────────────────────────────────────

@dataclass
class LiquidacaoOpcao:
    tipo: str
    lado: str
    strike: float
    fixing: float                    # o preço de exercício apurado (média, na asiática)
    fixings: List[float] = field(default_factory=list)
    intrinseco: float = 0.0          # por unidade, na moeda do preço
    exercida: bool = False
    quantidade: float = 0.0
    paridade: float = 1.0
    payoff: float = 0.0              # em reais, de quem é TITULAR (sempre ≥ 0)
    premio: float = 0.0              # em reais, pago pelo titular (sempre ≥ 0)
    exercicio_banco: float = 0.0     # o exercício, do BANCO
    premio_banco: float = 0.0        # o prêmio, do BANCO
    resultado: float = 0.0           # exercício + prêmio, do BANCO
    direcao_exercicio: str = ''
    direcao_premio: str = ''


def liquidar_opcao(tipo, lado, strike, quantidade, fixings, paridade=1.0,
                   premio_unitario=0.0, paridade_premio=None):
    """Exercício de uma opção flexível. `fixings` é a lista de preços de
    verificação: um, na vanilla; vários, na asiática — o preço de exercício é a
    MÉDIA aritmética deles. `premio_unitario` é por unidade, na moeda do preço;
    `paridade_premio` é a cotação do dia do prêmio (em branco, a do exercício)."""
    if tipo not in (CALL, PUT):
        raise ErroDerivativo('pick Call or Put')
    if lado not in (TITULAR, LANCADOR):
        raise ErroDerivativo('pick the bank side: holder or writer')
    if not strike or strike <= 0:
        raise ErroDerivativo('the strike must be greater than zero')
    if quantidade is None or quantidade <= 0:
        raise ErroDerivativo('the quantity must be greater than zero')
    precos = [float(x) for x in (fixings or []) if x is not None]
    if not precos:
        raise ErroDerivativo('enter at least one fixing price')
    if any(p <= 0 for p in precos):
        raise ErroDerivativo('a fixing price must be greater than zero')
    par = float(paridade or 1.0)
    if par <= 0:
        raise ErroDerivativo('the FX rate must be greater than zero')
    media = sum(precos) / len(precos)
    intr = max(0.0, media - float(strike)) if tipo == CALL else max(0.0, float(strike) - media)
    payoff = round(intr * float(quantidade) * par, 2)
    premio = round(float(premio_unitario or 0.0) * float(quantidade)
                   * float(paridade_premio or par), 2)
    dono = 1.0 if lado == TITULAR else -1.0
    ex_banco, pr_banco = payoff * dono, -premio * dono
    return LiquidacaoOpcao(
        tipo=tipo, lado=lado, strike=float(strike), fixing=media, fixings=precos,
        intrinseco=intr, exercida=intr > 0, quantidade=float(quantidade), paridade=par,
        payoff=payoff, premio=premio, exercicio_banco=ex_banco, premio_banco=pr_banco,
        resultado=round(ex_banco + pr_banco, 2),
        direcao_exercicio=_quem(ex_banco), direcao_premio=_quem(pr_banco))
