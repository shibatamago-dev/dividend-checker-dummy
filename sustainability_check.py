"""配当の持続性をyfinanceだけで足せるか確かめるための1回きりのチェック。
Run on your own PC (the Muse VM currently cannot reach Yahoo Finance:
even `dividends`, verified working in an earlier check, returns 0 rows there,
so a failure from the VM proves nothing about the data itself).

  pip install yfinance pandas
  python sustainability_check.py

For each of the 5 dividend stocks it prints, per fiscal year:
  DPS (from dividend_quality.py's FY aggregation) / Diluted EPS -> payout ratio
  FCF per share ((Operating CF + CapEx) / shares) -> FCF coverage of DPS (x)

How to read the result:
  - EPS and FCF present for all 5, several years back -> sustainability can be
    added to the tool with yfinance alone (no EDINET key needed).
  - Financials/cashflow empty or only 1-2 years -> yfinance is too short for
    Japanese stocks; EDINET (decisions data) becomes the fallback, as flagged
    in an earlier check.
  - Payout rising while DPS growth slows, or coverage < 1x, is the signal the
    sustainability view is meant to catch (e.g. ハルカ食品の recent +1 yen years).
Not investment advice; past data only.
"""
from dividend_quality import STOCKS, annual_dps  # 同じフォルダの dividend_quality.py を使う
import yfinance as yf

for code, name, fy_end in STOCKS:
    print(f"=== {name} {code} ===", flush=True)
    try:
        t = yf.Ticker(code)
        fin, cf, bs = t.financials, t.cashflow, t.balance_sheet
        dps = annual_dps(code, fy_end)
        print(" DPS FYs:", {k: round(v, 2) for k, v in dps.items() if k >= max(dps) - 5}, flush=True)
        if fin is None or fin.empty:
            print(" financials EMPTY", flush=True); continue
        # columns are year-end dates; map to FY by year (Mar-end: col year = FY year; Dec-end same)
        eps = {}
        if "Diluted EPS" in fin.index:
            for c in fin.columns:
                eps[c.year] = float(fin.loc["Diluted EPS", c])
        print(" EPS by year:", {k: round(v, 2) for k, v in sorted(eps.items())}, flush=True)
        ocf, capex = {}, {}
        if cf is not None and not cf.empty:
            if "Operating Cash Flow" in cf.index:
                for c in cf.columns: ocf[c.year] = float(cf.loc["Operating Cash Flow", c])
            if "Capital Expenditure" in cf.index:
                for c in cf.columns: capex[c.year] = float(cf.loc["Capital Expenditure", c])
        shares = None
        if bs is not None and not bs.empty and "Ordinary Shares Number" in bs.index:
            shares = {c.year: float(bs.loc["Ordinary Shares Number", c]) for c in bs.columns}
        else:
            try:
                shares = {"info": float(t.info.get("sharesOutstanding"))} if t.info.get("sharesOutstanding") else None
            except Exception:
                shares = None
        print(" shares:", shares, flush=True)
        for fy in sorted(dps):
            if fy not in eps:
                continue
            payout = dps[fy] / eps[fy] if eps[fy] else None
            fcf_ps = None
            if fy in ocf and fy in capex and shares:
                sh = shares.get(fy) or shares.get("info")
                if sh:
                    fcf_ps = (ocf[fy] + capex[fy]) / sh  # capex negative
            cov = (fcf_ps / dps[fy]) if fcf_ps and dps[fy] else None
            print(f"  FY{fy}: DPS {dps[fy]:.2f} / EPS {eps[fy]:.2f} -> payout "
                  f"{payout:.1%}" if payout is not None else f"  FY{fy}: DPS {dps[fy]:.2f} / EPS n/a",
                  (f" | FCF/株 {fcf_ps:.2f} -> カバー {cov:.2f}倍" if cov is not None else " | FCF n/a"), flush=True)
    except Exception as e:
        print(" ERROR:", type(e).__name__, str(e)[:200], flush=True)
print("DONE", flush=True)
