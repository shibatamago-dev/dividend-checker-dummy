"""
Personal dividend-streak quality checker (personal use only).

Data source: yfinance (Yahoo Finance, unofficial).
  - Personal use only under Yahoo's terms. Do NOT redistribute the
    fetched data in a public tool. For a public tool, use EDINET DB
    or the official EDINET API instead, and check their terms.
  - No API key needed. `pip install yfinance pandas`
  - Ticker.dividends is split-adjusted retroactively, so sums are on
    the current post-split basis. Verify this per stock.

Fiscal-year aggregation (the main pitfall):
  - yfinance dividends are per ex-date, usually 2 payments/year.
  - Dec year-end (e.g. ハルカ食品 DUM-A): annual DPS = sum of that calendar year.
  - Mar year-end (most Japanese stocks): FY ending Mar YYYY =
    Sep (YYYY-1) interim + Mar (YYYY) final.
  - FY_END below must be set per stock. Most are 3; check IR / Yahoo.

Judgement (proposed, not investment advice):
  - Show 10y / 5y / 3y CAGR side by side; primary judgement is recent 3y.
    >=3% solid, 1-3% slow, <1% effectively flat.
  - Deceleration flag: 10y CAGR >=3% but 3y CAGR <2%.
  - Token-year count: in last 5y, how many years the increase was <=1 yen
    (split-adjusted), always shown together with %.
  - Past data only. Forecasts excluded. Not investment advice.

Usage:
  python dividend_quality.py
  python dividend_quality.py --csv dividends_snapshot.csv
  # --csv writes annual DPS (code,name,fy,dps,fetched_at) for the
  # last 11 fiscal years per stock. That CSV is the input for the
  # public browser-only UI: the UI reads the file you upload, it
  # never fetches data itself. Edit STOCKS to add codes, and FY_END
  # for Dec-end stocks.
"""

import argparse
import csv
from collections import defaultdict
from datetime import date

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


def annual_dps(code: str, fy_end_month: int) -> dict[int, float]:
    div = yf.Ticker(code).dividends
    yearly: dict[int, float] = defaultdict(float)
    counts: dict[int, int] = defaultdict(int)
    for date, val in div.items():
        y, m = date.year, date.month
        if fy_end_month == 12:
            fy = y
        else:  # Mar end: Apr-Dec -> next FY, Jan-Mar -> same FY
            fy = y + 1 if m >= 4 else y
        yearly[fy] += float(val)
        counts[fy] += 1
    # Drop incomplete FYs: these 5 stocks pay twice a year, and the
    # latest FY only has the interim payment so far (Nov 2026).
    # A 1-payment-a-year stock would need a different rule.
    return {fy: v for fy, v in sorted(yearly.items()) if counts[fy] >= 2}


def cagr(start: float, end: float, years: int) -> float:
    return (end / start) ** (1 / years) - 1


def analyse(code: str, name: str, fy_end: int) -> dict:
    series = annual_dps(code, fy_end)
    last = max(series)
    out = {"code": code, "name": name, "fy_end": fy_end, "last_fy": last, "series": series}
    for n in (10, 5, 3):
        s = last - n
        if s in series:
            out[f"cagr_{n}y"] = cagr(series[s], series[last], n)
    # token years in last 5y: increase <= 1 yen (adjusted)
    token = 0
    for fy in range(last - 4, last + 1):
        if fy - 1 in series and fy in series:
            if series[fy] - series[fy - 1] <= 1.0 + 1e-9:
                token += 1
    out["token_years_5y"] = token
    c10 = out.get("cagr_10y", 0)
    c3 = out.get("cagr_3y", 0)
    out["deceleration_flag"] = bool(c10 >= 0.03 and c3 < 0.02)
    if c3 >= 0.03:
        out["judgement"] = "しっかり増配"
    elif c3 >= 0.01:
        out["judgement"] = "ゆるやか"
    else:
        out["judgement"] = "実質横ばい"
    return out


def export_csv(results: list[dict], path: str) -> None:
    fetched = date.today().isoformat()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["code", "name", "fy", "dps", "fetched_at"])
        for r in results:
            last = r["last_fy"]
            for fy, dps in sorted(r["series"].items()):
                if fy >= last - 10:
                    w.writerow([r["code"], r["name"], fy, round(dps, 2), fetched])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", dest="csv_path", default=None,
                    help="also write annual-DPS snapshot CSV for the browser UI")
    args = ap.parse_args()
    results = []
    for code, name, fy_end in STOCKS:
        try:
            r = analyse(code, name, fy_end)
        except ValueError:
            print(f"{name} {code}: データが取れませんでした（yfinanceのタイムアウト等）。時間を置いて再実行してください。")
            continue
        results.append(r)
        print(f"{r['name']} {code}  FY{r['last_fy']}決算まで")
        print(f"  DPS: { {k: round(v, 2) for k, v in r['series'].items() if k >= r['last_fy'] - 9} }")
        print(
            "  CAGR 10y {:.2%} / 5y {:.2%} / 3y {:.2%}  "
            "トークン年(直近5年) {}  減速注意 {}  -> {}".format(
                r.get("cagr_10y", float("nan")),
                r.get("cagr_5y", float("nan")),
                r.get("cagr_3y", float("nan")),
                r["token_years_5y"],
                "あり" if r["deceleration_flag"] else "なし",
                r["judgement"],
            )
        )
    if args.csv_path and results:
        export_csv(results, args.csv_path)
        print(f"CSVを書き出しました: {args.csv_path}（{len(results)}銘柄）")


if __name__ == "__main__":
    main()
