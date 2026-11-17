"""頸線策略三種（出場與 backtest.py 相同：連 3 日收盤 < 20MA）。
用法: python -I neckline.py <daily.parquet> <codes.txt> <out.json>
轉折點（pivot）用左右各 K 根確認，確認要等 K 根之後，所以訊號只用「當時已知」的轉折，沒有偷看未來。
股票池：市值前100、前500（10 檔等權）＋ 0050 單一標的（全倉、一次一筆）。
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import backtest as bt

K = 5


def pivots(a, low=True):
    """回傳轉折點索引陣列（low=True 找波谷）。i 為轉折要求 a[i] 是 [i-K, i+K] 的極值。"""
    n = len(a); s = pd.Series(a)
    ext = s.rolling(2 * K + 1, center=True).min() if low else s.rolling(2 * K + 1, center=True).max()
    ok = (s == ext).values.copy()
    ok[:K] = False; ok[n - K:] = False
    return np.flatnonzero(ok)


def _common(o, h, l, c, v):
    n = len(c)
    pc = np.r_[np.nan, c[:-1]]
    vavg = pd.Series(v).shift(1).rolling(20).mean().values
    return n, pc, vavg


def sig_double_bottom(o, h, l, c, v, ref):
    """N1 W底：近兩個波谷相距 15~60 根、高低差 ≤5%，頸線=兩谷之間最高價（且高於谷底 8% 以上）；
    收盤首次突破頸線，量 ≥ 20日均量 1.5 倍；右谷之後沒有跌破谷底 2%。"""
    n, pc, vavg = _common(o, h, l, c, v); sig = np.zeros(n, bool); pl = pivots(l, True)
    for t in range(60, n):
        m = np.searchsorted(pl, t - K, side="right")
        if m < 2: continue
        ia, ib = pl[m - 2], pl[m - 1]
        if not (15 <= ib - ia <= 60) or t - ib > 40: continue
        if abs(l[ib] / l[ia] - 1) > 0.05: continue
        neck = h[ia:ib + 1].max()
        if neck / min(l[ia], l[ib]) - 1 < 0.08: continue
        if min(l[ib:t + 1]) < min(l[ia], l[ib]) * 0.98: continue
        if c[t] > neck and pc[t] <= neck and v[t] >= 1.5 * vavg[t]: sig[t] = True
    return sig


def sig_head_shoulder_bottom(o, h, l, c, v, ref):
    """N2 頭肩底：三個連續波谷，中間（頭）比兩肩低至少 3%，兩肩高低差 ≤10%，總寬 ≤120 根、每段 ≥8 根；
    頸線=左右兩段反彈高點中較高者；收盤首次突破頸線，量 ≥ 20日均量 1.5 倍；頭之後沒有再破頭部低點。"""
    n, pc, vavg = _common(o, h, l, c, v); sig = np.zeros(n, bool); pl = pivots(l, True)
    for t in range(80, n):
        m = np.searchsorted(pl, t - K, side="right")
        if m < 3: continue
        i1, i2, i3 = pl[m - 3], pl[m - 2], pl[m - 1]
        if i2 - i1 < 8 or i3 - i2 < 8 or i3 - i1 > 120 or t - i3 > 40: continue
        if l[i2] > min(l[i1], l[i3]) * 0.97: continue
        if abs(l[i1] / l[i3] - 1) > 0.10: continue
        neck = max(h[i1:i2 + 1].max(), h[i2:i3 + 1].max())
        if min(l[i3:t + 1]) < l[i2]: continue
        if c[t] > neck and pc[t] <= neck and v[t] >= 1.5 * vavg[t]: sig[t] = True
    return sig


def sig_higher_low_breakout(o, h, l, c, v, ref):
    """N3 底底高＋突破前波高：近兩個波谷抬高 ≥2%、相距 ≥10 根；頸線=第一個谷起算的最高價；
    收盤首次突破頸線，量 ≥ 20日均量 1.2 倍；第一個谷起算不超過 80 根。"""
    n, pc, vavg = _common(o, h, l, c, v); sig = np.zeros(n, bool); pl = pivots(l, True)
    for t in range(60, n):
        m = np.searchsorted(pl, t - K, side="right")
        if m < 2: continue
        ia, ib = pl[m - 2], pl[m - 1]
        if ib - ia < 10 or t - ia > 80 or l[ib] < l[ia] * 1.02: continue
        neck = h[ia:t].max()
        if min(l[ib:t + 1]) < l[ib] * 0.99: continue
        if c[t] > neck and pc[t] <= neck and v[t] >= 1.2 * vavg[t]: sig[t] = True
    return sig


STRATS = {
    "N1": ("W底（雙重底）突破頸線＋放量", sig_double_bottom),
    "N2": ("頭肩底突破頸線＋放量", sig_head_shoulder_bottom),
    "N3": ("底底高＋突破前波高（頸線）", sig_higher_low_breakout),
}

if __name__ == "__main__":
    daily, codes_f, out_f = sys.argv[1:4]
    codes = [x.strip() for x in open(codes_f) if x.strip()]
    pools = [("etf0050", ["0050"], 1), ("top100", codes[:100], bt.SLOTS), ("top500", codes[:500], bt.SLOTS)]
    bt.main(daily, codes_f, out_f, strats=STRATS, pools=pools)
