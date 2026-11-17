"""三條件策略回測（一般版 vs 買得到版 vs 同期 0050）。

用法:  python -I backtest.py <daily.parquet> <codes.txt> <out.json>
  daily.parquet : 欄位 date,ticker(如 2330.TW),open,high,low,close,volume(股)；價格為還原價
  codes.txt     : 每行一個代號，依「市值」由大到小（前 N 取前 N 行）
出場（三策略共用）：連續 3 日收盤 < 20MA。
一般版：訊號日收盤進、第 3 個破線日收盤出（較樂觀、實務買不到）。
買得到版：訊號隔日開盤進、出場訊號隔日開盤出。
成本：往返 0.585%（手續費 0.1425%x2 + 證交稅 0.3%），進出各負擔一半。
"""
import sys, json
import numpy as np, pandas as pd

COST = 0.00585; SLOTS = 10; CAP0 = 150_000; START = 130; MINVOL = 500_000


def ema(a, n): return pd.Series(a).ewm(span=n, adjust=False).mean().values
def rmax(a, n, shift=1): return pd.Series(a).shift(shift).rolling(n).max().values
def rmean(a, n, shift=0): return pd.Series(a).shift(shift).rolling(n).mean().values
def prev(a, k=1):
    out = np.full(len(a), np.nan)
    if len(a) > k: out[k:] = a[:-k]
    return out


def sig_macd_bb(o, h, l, c, v, ref):
    """脆友原策略：MACD柱翻正 + 布林開口放大 + 站上上揚20MA"""
    w = (h + l + 2 * c) / 4
    dif = ema(w, 12) - ema(w, 26); osc = dif - ema(dif, 9)
    s = pd.Series(c); ma = s.rolling(20).mean().values; sd = s.rolling(20).std(ddof=0).values
    up, dn = ma + 2 * sd, ma - 2 * sd; bw = (up - dn) / ma
    return ((osc > 0) & (prev(osc) <= 0) & (bw > prev(bw)) & (up > prev(up)) & (dn < prev(dn))
            & (c > ma) & (ma > prev(ma)))


def sig_donchian(o, h, l, c, v, ref):
    """網路版（Donchian 海龜式）：收盤創20日新高 + 量>=20日均量1.5倍 + ADX(14)>25 且 +DI>-DI"""
    pc = prev(c)
    tr = np.nanmax(np.vstack([h - l, abs(h - pc), abs(l - pc)]), axis=0)
    up_m = np.r_[0, h[1:] - h[:-1]]; dn_m = np.r_[0, l[:-1] - l[1:]]
    pdm = np.where((up_m > dn_m) & (up_m > 0), up_m, 0.0)
    mdm = np.where((dn_m > up_m) & (dn_m > 0), dn_m, 0.0)
    wl = lambda a: pd.Series(a).ewm(alpha=1 / 14, adjust=False).mean().values
    atr = wl(tr); pdi = 100 * wl(pdm) / atr; mdi = 100 * wl(mdm) / atr
    adx = wl(100 * abs(pdi - mdi) / (pdi + mdi + 1e-9))
    return (c > rmax(h, 20)) & (v >= 1.5 * rmean(v, 20, 1)) & (adx > 25) & (pdi > mdi)


def sig_rs_trend(o, h, l, c, v, ref):
    """通用版（取自我們的選股原則，僅用公開指標）：相對強度勝0050 + 均線多頭 + 10日新高帶量"""
    ma20 = rmean(c, 20); ma60 = rmean(c, 60)
    r120 = c / prev(c, 120) - 1; b120 = ref / prev(ref, 120) - 1
    return ((r120 > b120) & (ma20 > ma60) & (ma60 > prev(ma60, 5)) & (c > ma20)
            & (c > rmax(c, 10)) & (v > rmean(v, 20, 1)))


STRATS = {
    "S1": ("脆友原策略：MACD柱翻正＋布林開口＋站上上揚20MA", sig_macd_bb),
    "S2": ("網路版：Donchian 20日新高＋爆量1.5倍＋ADX>25", sig_donchian),
    "S3": ("通用版：相對強度勝0050＋均線多頭＋10日新高帶量", sig_rs_trend),
}


def gen_trades(g, fn, ref, buyable):
    t = g.ticker.iloc[0]
    o, h, l, c, v = (g[k].values.astype(float) for k in ("open", "high", "low", "close", "volume"))
    n = len(c); dates = g.date.values
    with np.errstate(all="ignore"):
        sig = np.nan_to_num(fn(o, h, l, c, v, ref), nan=False).astype(bool) & (v >= MINVOL)
        ma = pd.Series(c).rolling(20).mean().values
        below = c < ma
    sig[:START] = False
    out = []; i = START
    while i < n - 1:
        if not sig[i]:
            i += 1; continue
        ei = i + 1 if buyable else i
        ep = o[ei] if buyable else c[i]
        xi = next((j for j in range(ei + 2, n) if below[j] and below[j - 1] and below[j - 2]), None)
        if xi is None:
            out.append((t, dates[ei], None, ep, None)); break
        xj = xi + 1 if buyable else xi
        if xj >= n:
            out.append((t, dates[ei], None, ep, None)); break
        out.append((t, dates[ei], dates[xj], ep, o[xj] if buyable else c[xj]))
        i = xj + (0 if buyable else 1)
    return out


def simulate(trades, px, days, cap0=CAP0):
    """逐日盯市：SLOTS 檔等權；同日多訊號依代號排序；滿檔跳過。回傳 (權益序列, 成交筆數)"""
    ev = {}
    for tr in trades: ev.setdefault(tr["entry"], []).append(tr)
    free = cap0; held = []; eq = []; taken = 0; half = COST / 2
    for d in days:
        for p in [p for p in held if p["exit"] <= d]:
            free += p["amt"] * (p["xp"] / p["ep"]) * (1 - half); held.remove(p)
        for tr in sorted(ev.get(d, []), key=lambda x: x["ticker"]):
            if len(held) >= SLOTS: break
            tot = free + sum(p["amt"] * (px.at[d, p["ticker"]] / p["ep"]) for p in held)
            amt = min(tot / SLOTS, free)
            if amt < 1000: break
            free -= amt; held.append(dict(tr, amt=amt * (1 - half))); taken += 1
        eq.append(free + sum(p["amt"] * (px.at[d, p["ticker"]] / p["ep"]) for p in held))
    return np.array(eq), taken


def mdd(e): return float((e / np.maximum.accumulate(e) - 1).min())


def main(daily, codes_f, out_f):
    d = pd.read_parquet(daily); d["ticker"] = d.ticker.astype(str)
    codes = [x.strip() for x in open(codes_f) if x.strip()]
    code_of = d.ticker.str.split(".").str[0]
    px_all = d.pivot_table(index="date", columns="ticker", values="close")
    days = list(px_all.index[START:]); ref0 = px_all["0050.TW"].ffill()
    b = ref0.loc[days]; b_eq = (b / b.iloc[0] * CAP0).values
    years = sorted(set(x.year for x in days))
    span = (days[-1] - days[0]).days / 365.25
    bench_year = {str(y): float(b[b.index.year == y].iloc[-1] / b[b.index.year == y].iloc[0] - 1) for y in years}
    res = {"meta": dict(start=str(days[0].date()), end=str(days[-1].date()), cost=COST, slots=SLOTS, cap0=CAP0,
                        bench_total=float(b.iloc[-1] / b.iloc[0] - 1),
                        bench_cagr=float((b.iloc[-1] / b.iloc[0]) ** (1 / span) - 1),
                        bench_mdd=mdd(b_eq), bench_year=bench_year),
           "strats": {k: v[0] for k, v in STRATS.items()}, "runs": []}
    for topn in (100, 500):
        pool = set(codes[:topn]); sub = d[code_of.isin(pool)]
        px = px_all[[t for t in px_all.columns if t.split(".")[0] in pool]].ffill()
        groups = {t: g.sort_values("date").reset_index(drop=True) for t, g in sub.groupby("ticker", sort=False)}
        for sk, (_, fn) in STRATS.items():
            for buyable in (False, True):
                raw = []
                for t, g in groups.items():
                    r = ref0.reindex(g.date).ffill().values.astype(float)
                    raw += gen_trades(g, fn, r, buyable)
                last = days[-1]; tl = []
                for (t, e, x, ep, xp) in raw:
                    if x is None: x = last; xp = px.at[last, t]
                    tl.append(dict(ticker=t, entry=pd.Timestamp(e), exit=pd.Timestamp(x), ep=float(ep), xp=float(xp)))
                rets = np.array([tr["xp"] / tr["ep"] - 1 - COST for tr in tl])
                hold = np.array([(tr["exit"] - tr["entry"]).days for tr in tl])
                w = rets[rets > 0]; lo = rets[rets <= 0]
                eq, taken = simulate(tl, px, days)
                yearly = []
                for y in years:
                    yd = [x for x in days if x.year == y]; ye = yd[-1]; ty = []
                    for tr in tl:
                        if yd[0] <= tr["entry"] <= ye:
                            tr2 = dict(tr)
                            if tr["exit"] > ye:
                                tr2["exit"] = ye + pd.Timedelta(days=1); tr2["xp"] = float(px.at[ye, tr["ticker"]])
                            ty.append(tr2)
                    e2, _ = simulate(ty, px, yd)
                    yearly.append(dict(year=y, ret=float(e2[-1] / CAP0 - 1), bench=bench_year[str(y)], n=len(ty)))
                run = dict(strat=sk, topn=topn, buyable=buyable, n=len(tl), win=float(len(w) / len(rets)),
                           avg=float(rets.mean()), med=float(np.median(rets)), odds=float(w.mean() / -lo.mean()),
                           hold=float(hold.mean()), avg_ex5=float(np.sort(rets)[:-5].mean()), taken=taken,
                           final=float(eq[-1]), cagr=float((eq[-1] / CAP0) ** (1 / span) - 1), mdd=mdd(eq),
                           yearly=yearly, yr_avg=float(np.mean([y["ret"] for y in yearly])),
                           yr_loss=int(sum(y["ret"] < 0 for y in yearly)),
                           yr_beat=int(sum(y["ret"] > y["bench"] for y in yearly)),
                           curve=[[str(days[i].date()), round(float(eq[i]))] for i in range(0, len(days), 5)]
                                 + [[str(days[-1].date()), round(float(eq[-1]))]])
                res["runs"].append(run)
                print(sk, topn, "買得到" if buyable else "一般", len(tl), f"CAGR {run['cagr']:.1%} MDD {run['mdd']:.1%}", flush=True)
    res["bench_curve"] = ([[str(days[i].date()), round(float(b_eq[i]))] for i in range(0, len(days), 5)]
                          + [[str(days[-1].date()), round(float(b_eq[-1]))]])
    json.dump(res, open(out_f, "w", encoding="utf-8"), ensure_ascii=False)


if __name__ == "__main__":
    main(*sys.argv[1:4])
