"""配当の持続性をyfinanceだけで足せるか確かめるための1回きりのチェック（単体版）。
dividend_quality.py に依存しないので、このファイル1つで動きます。

  pip install yfinance pandas
  python sustainability_check_standalone.py

5銘柄について年度ごとに表示します:
  DPS（年度集計）/ 希薄化EPS → 配当性向
  FCF/株（(営業CF + 設備投資) / 株数）→ DPSのFCFカバー倍率

結果の読み方:
  - 全5銘柄でEPS・FCFが数年分取れる → 持続性はyfinance単独で足せる（EDINETキー不要）
  - financials/cashflow が空、または1〜2年だけ → 日本株には短すぎるのでEDINETが本命
  - 配当性向が上がりながらDPSの伸びが鈍る、またはカバー1倍割れが、持続性ビューで見たいシグナル
投資助言ではありません。過去データのみ。
"""
from collections import defaultdict

import yfinance as yf

# 架空コード, name, fiscal-year-end month
# ※架空のサンプルコードです。実際に使うときは調べたい銘柄のコードに置き換えてください。
STOCKS = [
    ("DUM-A", "ハルカ食品", 12),
    ("DUM-C", "カケルキャピタル", 3),
    ("DUM-B", "ノゾミ通信", 3),
    ("DUM-D", "ソラ部品", 3),
    ("DUM-E", "ユメ流通", 3),
]


def annual_dps(code: str, fy_end_month: int) -> dict:
    div = yf.Ticker(code).dividends
    yearly = defaultdict(float)
    counts = defaultdict(int)
    for d, val in div.items():
        y, m = d.year, d.month
        if fy_end_month == 12:
            fy = y
        else:  # 3月決算: 4〜12月は翌年度、1〜3月は同年度
            fy = y + 1 if m >= 4 else y
        yearly[fy] += float(val)
        counts[fy] += 1
    # 年2回払い前提で、支払いが1回しかない未確定の年度は落とす
    return {fy: v for fy, v in sorted(yearly.items()) if counts[fy] >= 2}


for code, name, fy_end in STOCKS:
    print(f"=== {name} {code} ===", flush=True)
    try:
        t = yf.Ticker(code)
        fin, cf, bs = t.financials, t.cashflow, t.balance_sheet
        dps = annual_dps(code, fy_end)
        recent = {k: round(v, 2) for k, v in dps.items() if k >= max(dps) - 5}
        print(" DPS FYs:", recent, flush=True)
        if fin is None or fin.empty:
            print(" financials EMPTY", flush=True)
            continue
        eps = {}
        if "Diluted EPS" in fin.index:
            for c in fin.columns:
                eps[c.year] = float(fin.loc["Diluted EPS", c])
        print(" EPS by year:", {k: round(v, 2) for k, v in sorted(eps.items())}, flush=True)
        ocf, capex = {}, {}
        if cf is not None and not cf.empty:
            if "Operating Cash Flow" in cf.index:
                for c in cf.columns:
                    ocf[c.year] = float(cf.loc["Operating Cash Flow", c])
            if "Capital Expenditure" in cf.index:
                for c in cf.columns:
                    capex[c.year] = float(cf.loc["Capital Expenditure", c])
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
                    fcf_ps = (ocf[fy] + capex[fy]) / sh  # capexは負の値
            cov = (fcf_ps / dps[fy]) if fcf_ps and dps[fy] else None
            line = f"  FY{fy}: DPS {dps[fy]:.2f} / EPS {eps[fy]:.2f}"
            if payout is not None:
                line += f" -> 配当性向 {payout:.1%}"
            if cov is not None:
                line += f" | FCF/株 {fcf_ps:.2f} -> カバー {cov:.2f}倍"
            else:
                line += " | FCF n/a"
            print(line, flush=True)
    except Exception as e:
        print(" ERROR:", type(e).__name__, str(e)[:200], flush=True)
print("DONE", flush=True)
