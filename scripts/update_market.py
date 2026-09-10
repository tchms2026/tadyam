import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
text = (ROOT / "app.js").read_text(encoding="utf-8")
pairs = dict(re.findall(r"\['(\d{4})','([^']+)'\]", text))
for code, name in re.findall(r"code:'(\d{4})',name:'([^']+)'", text):
    pairs[code] = name

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))

def clamp(value, low=0, high=100):
    return max(low, min(high, value))

def analyze(code, name):
    ticker = f"{code}.T"
    df = yf.download(ticker, period="1y", interval="1d", auto_adjust=True, progress=False, threads=False)
    if df.empty or len(df) < 30:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    close = df["Close"].dropna()
    volume = df["Volume"].reindex(close.index).fillna(0)
    if len(close) < 30:
        return None
    price = float(close.iloc[-1])
    sma25 = float(close.tail(25).mean())
    sma75 = float(close.tail(min(75, len(close))).mean())
    rsi14 = float(rsi(close).iloc[-1]) if pd.notna(rsi(close).iloc[-1]) else 50.0
    vol20 = float(volume.tail(20).mean()) or 1.0
    volume_ratio = float(volume.iloc[-1] / vol20)
    high52 = float(close.max())
    low52 = float(close.min())
    position = (price - low52) / max(high52 - low52, 1)
    trend_score = 50 + (15 if price > sma25 else -10) + (15 if sma25 > sma75 else -10)
    rsi_score = 80 if 45 <= rsi14 <= 65 else 62 if 35 <= rsi14 < 75 else 38
    position_score = 45 + position * 35
    technical = round(clamp(trend_score * .5 + rsi_score * .3 + position_score * .2))
    flow = round(clamp(50 + (volume_ratio - 1) * 25 + (10 if price >= sma25 else -5)))
    score = round(technical * .75 + flow * .25)
    if rsi14 >= 75:
        action = "過熱注意"
    elif price >= sma25 >= sma75 and rsi14 < 70:
        action = "上昇トレンド"
    elif price >= sma75 and rsi14 < 55:
        action = "押し目候補"
    else:
        action = "監視"
    buy_low, buy_high = sorted((sma25 * .97, sma25 * 1.01))
    take = max(price * 1.2, high52 * 1.05)
    stop = min(sma75 * .95, price * .9)
    return {
        "code": code, "name": name, "price": round(price, 1),
        "sma25": round(sma25, 1), "sma75": round(sma75, 1),
        "rsi14": round(rsi14, 1), "volume_ratio": round(volume_ratio, 2),
        "technical": technical, "flow": flow, "score": score, "action": action,
        "buy_zone": [round(buy_low, 1), round(buy_high, 1)],
        "take": round(take, 1), "stop": round(stop, 1),
        "upside": round((take / price - 1) * 100)
    }

results = []
for index, (code, name) in enumerate(sorted(pairs.items()), 1):
    try:
        row = analyze(code, name)
        if row:
            results.append(row)
        print(f"{index}/{len(pairs)} {code} {'ok' if row else 'no data'}", flush=True)
    except Exception as exc:
        print(f"{index}/{len(pairs)} {code} error: {exc}", flush=True)

out = {"updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "stocks": results}
(ROOT / "data").mkdir(exist_ok=True)
(ROOT / "data" / "market.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
