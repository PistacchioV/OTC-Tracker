import pandas as pd
from datetime import date
import os

# ------------------------------------------------------------------
# CONFIGURAÇÕES
# ------------------------------------------------------------------
PASTA         = r"caminho do xlsx"
ARQUIVO_EXCEL = os.path.join(PASTA, "NewDealsAndCashflowDetails.xlsx")
ABA           = 0                                   # nome ou índice da aba
DELIMITADOR   = ";"
TRADE_DATE    = date.today().strftime("%Y%m%d")     # =today
ARQUIVO_TXT   = os.path.join(PASTA, f"LAWTON_OFF_SWAP_{TRADE_DATE}.txt")   # ex.: LAWTON_OFF_SWAP_20260821.txt

# Comp Meth -> valor no índice (pernas fixas viram FIXED)
COMP_METH_MAP = {
    "StdFixedXccyLeg":   "FIXED",
    "StdFixedXccyLegND": "FIXED",
    "StdIRSFixedLeg":    "FIXED",
    "IRFixedLeg":        "FIXED",
}

# ------------------------------------------------------------------
# FUNÇÕES AUXILIARES
# ------------------------------------------------------------------
def vazio(v):
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""

def to_num(v):
    if vazio(v):
        return None
    s = str(v).strip()
    if "," in s and "." not in s:          # padrão BR: 1.166.207,02
        s = s.replace(".", "").replace(",", ".")
    return float(s)

def fmt_num_br(v, casas=2):
    if v is None:
        return ""
    return f"{v:.{casas}f}".replace(".", ",")

def fmt_data(v):
    if vazio(v):
        return ""
    return pd.to_datetime(v).strftime("%Y%m%d")

def base_from_dcc(dcc):
    """act/360 -> 360 ; 30/360 -> 360"""
    if vazio(dcc):
        return ""
    return str(dcc).split("/")[-1].strip()

def stub(v):
    """DefaultRate ou vazio -> '' (campo vazio, sem espaço)."""
    if vazio(v) or str(v).strip() == "DefaultRate":
        return ""
    return str(v).strip()

def custom_rate(v):
    """Custom Rt(%) vazio -> '0'."""
    return "0" if vazio(v) else str(v).strip()

def resolve_index(index_name, currency, comp_meth):
    """
    Resolve o índice de uma perna (serve para Rec e Pay).
    Se Index Name estiver vazio -> Currency + ' ' + Comp Meth,
    com as pernas fixas mapeadas para FIXED.
    """
    if vazio(index_name):
        comp = COMP_METH_MAP.get(str(comp_meth).strip(), str(comp_meth).strip())
        return f"{currency} {comp}"
    return str(index_name).strip()

def g(row, col):
    return "" if (col not in row or vazio(row[col])) else str(row[col]).strip()

def pay_ou_rec(pay, rec, col, default=""):
    """Pega da Pay; se vazio, olha na Rec; se ambos vazios, usa default."""
    vp = g(pay, col)
    if not vazio(vp):
        return vp
    vr = g(rec, col)
    if not vazio(vr):
        return vr
    return default

# ------------------------------------------------------------------
# MONTAGEM DE UMA OPERAÇÃO (par Pay + Rec)
# ------------------------------------------------------------------
def montar_operacao(pay, rec):
    qtd_pay = to_num(g(pay, "Quantity"))
    qtd_rec = to_num(g(rec, "Quantity"))
    fx_rate = ""
    if qtd_pay not in (None, 0) and qtd_rec is not None:
        fx_rate = fmt_num_br(qtd_rec / qtd_pay, 6)      # Campo 12: calculado

    campos = [
        "13",                                   # 1  File Code (fixo)
        "0",                                    # 2  Trade Number (fixo)
        "GCCN",                                 # 3  Portfolio Code (fixo)
        "JPM",                                  # 4  Counterparty Code (fixo)
        g(pay, "Deal Name"),                    # 5  Contract Number
        TRADE_DATE,                             # 6  Trade Date (=today)
        fmt_data(g(pay, "Start Date")),         # 7  Start Date (Pay)
        fmt_data(g(pay, "End Date")),           # 8  Maturity Date (Pay)
        fmt_num_br(qtd_pay, 2),                 # 9  Notional Value (Pay)

        # --- Leg 1 (Party) = Rec leg ---
        resolve_index(g(rec, "Index Name"),
                      g(rec, "Currency"),
                      g(rec, "Comp Meth")),     # 10 Index (Rec) -> mesma regra
        "100",                                  # 11 Percentage (fixo)
        fx_rate,                                # 12 FX Rate = Qtd Rec / Qtd Pay
        g(rec, "Rates/Spread"),                 # 13 Rate (Rec)
        base_from_dcc(g(rec, "DCC")),           # 14 Base (Rec)
        "E",                                    # 15 Interest Type (fixo)
        "E",                                    # 16 Accrual (fixo)
        "C",                                    # 17 Days (fixo)
        g(rec, "Pay Freq"),                     # 18 Pay Frequency (Rec)
        g(rec, "Acc Adj"),                      # 19 Accrual Adjust (Rec)
        g(rec, "Pay Adj"),                      # 20 Payment Adjust (Rec)
        custom_rate(g(rec, "Custom Rt(%)")),    # 21 Custom Rate (Rec) vazio->0
        stub(g(rec, "Initial Stub Method")),    # 22 Initial Stub Method (Rec)
        g(rec, "Initial Interp Tenor"),         # 23 Initial Interp Tenor (Rec)
        stub(g(rec, "Final Stub Method")),      # 24 Final Stub Method (Rec)
        g(rec, "Final Interp Tenor"),           # 25 Final Interp Tenor (Rec)
        "",                                     # 26 Observation

        # --- Leg 2 (Counterparty) = Pay leg ---
        resolve_index(g(pay, "Index Name"),
                      g(pay, "Currency"),
                      g(pay, "Comp Meth")),     # 27 Index (Pay) -> mesma regra
        "100",                                  # 28 Percentage (fixo)
        "",                                     # 29 FX Rate (vazio)
        g(pay, "Rates/Spread"),                 # 30 Rate (Pay)
        base_from_dcc(g(rec, "DCC")),           # 31 Base (Rec, conforme template)
        "E",                                    # 32 Interest Type (fixo)
        "E",                                    # 33 Accrual (fixo)
        "C",                                    # 34 Days (fixo)
        g(pay, "Pay Freq"),                     # 35 Pay Frequency (Pay)
        g(pay, "Acc Adj"),                      # 36 Accrual Adjust (Pay)
        g(pay, "Pay Adj"),                      # 37 Payment Adjust (Pay)
        custom_rate(g(pay, "Custom Rt(%)")),    # 38 Custom Rate (Pay) vazio->0
        stub(g(pay, "Initial Stub Method")),    # 39 Initial Stub Method (Pay)
        g(pay, "Initial Interp Tenor"),         # 40 Initial Interp Tenor (Pay)
        stub(g(pay, "Final Stub Method")),      # 41 Final Stub Method (Pay)
        g(pay, "Final Interp Tenor"),           # 42 Final Interp Tenor (Pay)
        "",                                     # 43 Observation

        # --- Settlement ---
        fmt_data(g(pay, "End Date")),                            # 44 Settlement Date (Pay)
        pay_ou_rec(pay, rec, "Settlement Ccy", default="DSW"),   # 45 Settl. Ccy (Pay->Rec->DSW)
        pay_ou_rec(pay, rec, "FX Reset Anchor"),                 # 46 FX Fixing Date  (FX Reset Anchor, Pay->Rec)
        pay_ou_rec(pay, rec, "FX Fix Date Adj"),                 # 47 FX Fixing Adjust (FX Fix Date Adj, Pay->Rec)
        pay_ou_rec(pay, rec, "FX Fix Pub"),                      # 48 FX Fixing Publisher (FX Fix Pub, Pay->Rec)
    ]
    # .strip() em todos os campos -> garante que vazios saiam como '' (sem espaço)
    return [str(c).strip() for c in campos]

# ------------------------------------------------------------------
# PROCESSAMENTO PRINCIPAL
# ------------------------------------------------------------------
def main():
    df = pd.read_excel(ARQUIVO_EXCEL, sheet_name=ABA, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    linhas_saida = []
    for deal, grupo in df.groupby("Deal Name", sort=False):
        pay = grupo[grupo["Direction"].str.strip().str.lower() == "pay"]
        rec = grupo[grupo["Direction"].str.strip().str.lower() == "rec"]

        if pay.empty or rec.empty:
            print(f"[AVISO] Deal {deal}: faltando perna Pay ou Rec — ignorado.")
            continue

        linhas_saida.append(DELIMITADOR.join(montar_operacao(pay.iloc[0], rec.iloc[0])))

    with open(ARQUIVO_TXT, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas_saida))

    print(f"OK: {len(linhas_saida)} operações gravadas em {ARQUIVO_TXT}")

if __name__ == "__main__":
    main()