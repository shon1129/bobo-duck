"""
波波鴨選股主程式
GitHub Actions 每天自動執行
同時推播 Telegram + LINE，並產生 HTML 報告
"""
import os, sys, time, requests, json
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta

# ══════════════════════════════════════════════
# 設定（從 GitHub Secrets 讀取）
# ══════════════════════════════════════════════
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
LINE_TOKEN       = os.environ.get("LINE_TOKEN", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept-Language": "zh-TW,zh;q=0.9",
}
DELAY = 0.8

# ══════════════════════════════════════════════
# 股票池（可自行新增）
# ══════════════════════════════════════════════
STOCK_POOL = {
    # 半導體
    "2330":"台積電","2454":"聯發科","2379":"瑞昱","2303":"聯電",
    "2449":"京元電","3711":"日月光投控",
    # 記憶體
    "2408":"南亞科","2344":"華邦電","2337":"旺宏","6770":"力積電","3006":"晶豪科",
    # AI伺服器
    "2382":"廣達","2317":"鴻海","2356":"英業達","3231":"緯創",
    # 被動元件
    "2327":"國巨","2492":"華新科","5222":"信昌電",
    # 散熱
    "6515":"奇鋐","8996":"高力",
    # 面板
    "3481":"群創","2409":"友達","6116":"彩晶",
    # PCB
    "2313":"華通","2383":"台光電","3037":"欣興","8046":"南電","3044":"健鼎",
    # 儲存
    "5289":"宜鼎","8299":"群聯",
    # 網通
    "2345":"智邦",
    # 傳產
    "1605":"華新","2609":"陽明","2603":"長榮",
    # 金融
    "2882":"國泰金","2886":"兆豐金",
    # 喜好股
    "2069":"大學光","6182":"合晶","2338":"超豐","8101":"尖點",
    "8271":"宇瞻","6150":"光聖","4549":"和桐","6282":"康舒",
    "2476":"鉅祥","6515":"奇鋐","8996":"高力",
    # 觀察名單
    "3006":"晶豪科","3481":"群創","2409":"友達","2382":"廣達",
}

# ══════════════════════════════════════════════
# 資料抓取
# ══════════════════════════════════════════════
def safe_float(s):
    try: return float(str(s).replace(",","").strip())
    except: return None

def fetch_twse_month(code, y, m):
    try:
        r = requests.get(
            "https://www.twse.com.tw/exchangeReport/STOCK_DAY",
            params={"response":"json","date":f"{y}{m:02d}01","stockNo":code},
            headers=HEADERS, timeout=15
        )
        j = r.json()
        if j.get("stat") != "OK" or not j.get("data"): return []
        rows = []
        for d in j["data"]:
            o,h,l,c,v = safe_float(d[3]),safe_float(d[4]),safe_float(d[5]),safe_float(d[6]),safe_float(d[1])
            if c: rows.append({"date":d[0],"open":o,"high":h,"low":l,"close":c,"volume":v or 0})
        return rows
    except: return []

def fetch_tpex_month(code, y, m):
    try:
        roc = y - 1911
        r = requests.get(
            "https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_download.php",
            params={"l":"zh-tw","d":f"{roc}/{m:02d}","stkno":code,"s":"0,asc,0"},
            headers=HEADERS, timeout=15
        )
        j = r.json()
        rows = []
        for d in j.get("aaData",[]):
            o,h,l,c,v = safe_float(d[3]),safe_float(d[4]),safe_float(d[5]),safe_float(d[6]),safe_float(d[1])
            if c: rows.append({"date":d[0],"open":o,"high":h,"low":l,"close":c,"volume":v or 0})
        return rows
    except: return []

def fetch_kline(code, months=14):
    rows = []
    today = date.today()
    for i in range(months-1, -1, -1):
        m = today.month - i
        y = today.year
        while m <= 0: m += 12; y -= 1
        data = fetch_twse_month(code, y, m)
        if not data: data = fetch_tpex_month(code, y, m)
        rows.extend(data)
        time.sleep(DELAY)
    seen, result = set(), []
    for r in rows:
        if r["date"] not in seen:
            seen.add(r["date"]); result.append(r)
    return sorted(result, key=lambda x: x["date"]) if result else None

def fetch_institutional(code):
    try:
        r = requests.get("https://www.twse.com.tw/fund/T86",
            params={"response":"json","date":date.today().strftime("%Y%m%d"),"selectType":"ALLBUT0999"},
            headers=HEADERS, timeout=15)
        j = r.json()
        for row in j.get("data",[]):
            if row[0] == code:
                return {"foreign":safe_float(row[4]),"invest":safe_float(row[10]),
                        "dealer":safe_float(row[13]),"net":safe_float(row[18])}
    except: pass
    return {"foreign":None,"invest":None,"dealer":None,"net":None}

def fetch_margin(code):
    try:
        r = requests.get("https://www.twse.com.tw/exchangeReport/MI_MARGN",
            params={"response":"json","date":date.today().strftime("%Y%m%d"),"selectType":"ALL"},
            headers=HEADERS, timeout=15)
        j = r.json()
        for row in j.get("data",[]):
            if row[0] == code:
                return {"margin_bal":safe_float(row[6]),"margin_ratio":safe_float(row[7]),"short_bal":safe_float(row[12])}
    except: pass
    return {"margin_bal":None,"margin_ratio":None,"short_bal":None}

# ══════════════════════════════════════════════
# 技術分析
# ══════════════════════════════════════════════
def ma(s, n): return s.rolling(n).mean()
def turning_up(s, n, lb=5):
    m = ma(s,n); v = m.dropna()
    return len(v)>lb and float(m.iloc[-1])>float(m.iloc[-lb-1])

def analyze(rows):
    df = pd.DataFrame(rows)
    c = df["close"].astype(float)
    v = df["volume"].astype(float)
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    price = float(c.iloc[-1])
    last_date = df["date"].iloc[-1]

    mas = {}
    for n,k in [(5,"MA5"),(10,"MA10"),(20,"MA20"),(60,"MA60"),(120,"MA120"),(200,"MA200")]:
        val = ma(c,n).iloc[-1]
        if not pd.isna(val): mas[k] = round(float(val),2)

    above = {k:v2 for k,v2 in mas.items() if price>v2}
    above_pct = len(above)/len(mas) if mas else 0
    above_score = round(above_pct*100)
    above_all = above_pct == 1.0
    ma20up = turning_up(c,20); ma60up = turning_up(c,60)
    ma_up_score = (50 if ma20up else 0)+(50 if ma60up else 0)

    vol5 = float(v.iloc[-5:].mean()); vol20 = float(v.iloc[-20:].mean())
    vol_r = vol5/vol20 if vol20>0 else 1.0
    vol_score = min(100, round(vol_r*80))

    h20 = float(c.iloc[-20:].max()); rh = float(c.iloc[-5:].max())
    mh = rh>=h20*0.98
    high_score = round((rh/h20)*(90 if mh else 60))

    vmin,vmax = float(v.iloc[-20:].min()),float(v.iloc[-20:].max())
    base_score = 80 if (vmax>0 and (vmax-vmin)/vmax>0.5) else 50

    chg = c.pct_change().iloc[-10:].abs().dropna()
    chip_score = max(0, round(100-float(chg.mean())*2000))

    wave = round(above_score*0.25+vol_score*0.20+ma_up_score*0.20
                +high_score*0.15+base_score*0.10+chip_score*0.10)

    lv=float(v.iloc[-1]); lo=float(df["open"].iloc[-1]) if df["open"].iloc[-1] else price
    lh=float(h.iloc[-1])
    d20=((price-mas.get("MA20",price))/mas.get("MA20",price)*100) if "MA20" in mas else 0
    d5 =((price-mas.get("MA5", price))/mas.get("MA5", price)*100) if "MA5"  in mas else 0
    us =(lh-max(price,lo))/lh if lh>0 else 0
    low20=float(l.iloc[-20:].min())

    risks={
        "高檔爆量":   lv>vol20*2.5 and price<float(c.iloc[-3]),
        "爆量長上影": us>0.03 and lv>vol20*2,
        "乖離過大":   abs(d20)>25,
        "出現三破":   ("MA5" in mas and price<mas["MA5"]) and
                     ("MA20" in mas and price<mas["MA20"]) and
                     float(c.iloc[-5:].min())<float(c.iloc[-20:-5].min()),
        "短線過熱":   d5>8,
        "均線下彎":   not ma20up and not ma60up and above_score<40,
    }
    risk_n = sum(risks.values())

    if   risks["出現三破"]:                                    stage="下山"
    elif risks["高檔爆量"] or risks["乖離過大"]:               stage="稜線段"
    elif above_all and vol_r>=1.2 and mh and wave>=80:         stage="主升段"
    elif above_all and vol_r>=1.2 and wave>=70:                stage="行進段"
    elif above_all and wave>=60:                               stage="夢想起飛"
    elif above_score>=60:                                      stage="量縮整理"
    else:                                                      stage="打地基"

    bull=len(c)>=80 and float(c.iloc[-20:].max())>float(c.iloc[-80:-60].max())
    av60=float(v.iloc[-60:].mean()) if len(v)>=60 else vol20
    atk =bool((v.iloc[-60:]>av60*2.0).any()) if len(v)>=60 else False
    pull_flag=vol_r<0.85
    nm20="MA20" in mas and abs(price-mas["MA20"])/mas["MA20"]<0.05
    nm60="MA60" in mas and abs(price-mas["MA60"])/mas["MA60"]<0.05
    l60 =float(l.iloc[-60:-20].min()) if len(l)>=60 else float(l.iloc[-20:].min())

    ds=0
    if bull:         ds+=25
    if atk:          ds+=20
    if pull_flag:    ds+=20
    if nm20 or nm60: ds+=20
    if price>l60*0.97: ds+=10
    if (mas.get("MA5",0)>mas.get("MA20",0)*0.98) or ma20up: ds+=5

    if   not bull or not atk:                   dream="不符合"
    elif ds>=75 and not risks["短線過熱"]:       dream="捕夢網✨"
    elif ds>=55 and pull_flag:                  dream="觀察中"
    elif bull and atk:                          dream="等拉回"
    else:                                       dream="不符合"

    if   risk_n>=2 or risks["出現三破"]:                        gpt="型態轉弱"
    elif risks["短線過熱"] or risks["高檔爆量"]:                gpt="強勢但過熱"
    elif dream=="捕夢網✨":                                      gpt="捕夢網買點"
    elif above_all and ma20up and vol_r>=1.2 and wave>=75:      gpt="積極觀察"
    elif above_all and ma20up:                                  gpt="可觀察"
    else:                                                       gpt="等確認"

    ma20v=mas.get("MA20",price)
    return {
        "price":price,"date":last_date,"stage":stage,"gpt":gpt,
        "wave":wave,"risk_n":risk_n,"dream":dream,"dream_score":ds,
        "vol_r":round(vol_r,2),"div20":round(d20,1),
        "above_all":above_all,"mas":mas,"above":above,"risks":risks,
        "pull":round(max(ma20v,low20*1.01),1),
        "breakout":round(h20*1.005,1),
        "weak":round(min(ma20v*0.99,low20),1),
        "scores":{"站上均線":above_score,"量增輪迴":vol_score,
                  "均線上彎":ma_up_score,"不斷創高":high_score,
                  "量縮打地基":base_score,"籌碼穩定":chip_score},
    }

def analyze_stock(code, name):
    print(f"  {name}({code})…", end=" ", flush=True)
    rows = fetch_kline(code)
    if not rows or len(rows)<10:
        print("❌"); return None
    t = analyze(rows)
    inst   = fetch_institutional(code); time.sleep(DELAY)
    margin = fetch_margin(code);        time.sleep(DELAY)
    r = {"code":code,"name":name,**t}
    r.update(inst); r.update(margin)
    bar = "█"*(t["wave"]//10)+"░"*(10-t["wave"]//10)
    print(f"${t['price']:.1f} [{bar}]{t['wave']} {t['stage']}"
          +(f" 🕸️" if t["dream"]=="捕夢網✨" else ""))
    return r

# ══════════════════════════════════════════════
# Telegram 推播
# ══════════════════════════════════════════════
def tg(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID: return
    for chunk in [text[i:i+4000] for i in range(0,len(text),4000)]:
        try:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id":TELEGRAM_CHAT_ID,"text":chunk,
                      "parse_mode":"HTML","disable_web_page_preview":True}, timeout=15)
            time.sleep(0.3)
        except Exception as e: print(f"TG error:{e}")

# ══════════════════════════════════════════════
# LINE 推播
# ══════════════════════════════════════════════
def line(text):
    if not LINE_TOKEN: return
    for chunk in [text[i:i+950] for i in range(0,len(text),950)]:
        try:
            requests.post("https://notify-api.line.me/api/notify",
                headers={"Authorization":f"Bearer {LINE_TOKEN}"},
                data={"message":chunk}, timeout=15)
            time.sleep(0.5)
        except Exception as e: print(f"LINE error:{e}")

def notify(text, tg_fmt=None):
    """同時推播 TG（HTML格式）和 LINE（純文字）"""
    tg(tg_fmt or text)
    # LINE 移除 HTML 標籤
    import re
    plain = re.sub(r'<[^>]+>', '', tg_fmt or text)
    line(plain)

# ══════════════════════════════════════════════
# HTML 報告產生
# ══════════════════════════════════════════════
STAGE_CFG={
    "主升段":  ("#3a2a00","#fbbf24","🔥"),"行進段":  ("#1a2e1a","#86efac","📈"),
    "夢想起飛":("#1a3a1a","#4ade80","🚀"),"量縮整理":("#2a1a3a","#c084fc","⏸️"),
    "打地基":  ("#1a2a3a","#60a5fa","🧱"),"稜線段":  ("#3a1500","#fb923c","⚠️"),
    "下山":    ("#3a1a1a","#f87171","📉"),
}
GPT_CFG={
    "捕夢網買點":("#3a2800","#fde68a"),"積極觀察":("#1a3a1a","#4ade80"),
    "可觀察":("#1a2e1a","#86efac"),"等確認":("#2a1a3a","#c084fc"),
    "強勢但過熱":("#3a1500","#fb923c"),"型態轉弱":("#3a1a1a","#f87171"),
}

def sc(s): return "#4ade80" if s>=80 else "#fbbf24" if s>=65 else "#94a3b8"
def badge(t,bg,c,bd="transparent"):
    return f'<span style="background:{bg};color:{c};border:1px solid {bd};padding:2px 8px;border-radius:6px;font-size:11px;font-weight:700">{t}</span>'

def card_html(r):
    stg=STAGE_CFG.get(r["stage"],("#1e293b","#94a3b8","❓"))
    gpc=GPT_CFG.get(r["gpt"],("#1e293b","#94a3b8"))
    risks=[k for k,v in r.get("risks",{}).items() if v]
    risk_html="".join(f'<span style="background:#3a0a0a;color:#fca5a5;padding:2px 7px;border-radius:5px;font-size:10px;margin:2px">⚠️{k}</span>' for k in risks)
    dream_badge=badge("🕸️ 捕夢網✨","#3a2800","#fde68a","#fbbf2455") if r.get("dream")=="捕夢網✨" else ""
    bars="".join(f'''<div style="margin-bottom:3px"><div style="display:flex;justify-content:space-between;font-size:9px;color:#94a3b8"><span>{k}</span><span>{v}</span></div>
      <div style="background:#0f172a;border-radius:2px;height:4px"><div style="width:{min(v,100)}%;height:4px;background:{'#4ade80' if v>=75 else '#fbbf24' if v>=50 else '#ef4444'};border-radius:2px"></div></div></div>'''
      for k,v in r.get("scores",{}).items())
    ma_html="".join(f'<span style="background:{"#1a3a1a" if r["price"]>v else "#3a1a1a"};color:{"#4ade80" if r["price"]>v else "#f87171"};padding:2px 6px;border-radius:4px;font-size:9px;font-family:monospace;margin:2px">{k} {v:.1f}{"✓" if r["price"]>v else "✗"}</span>' for k,v in r.get("mas",{}).items())
    inst=""
    if r.get("foreign") is not None:
        c2="#4ade80" if (r["foreign"] or 0)>0 else "#f87171"
        inst+=f' <span style="color:{c2};font-size:10px">外資{("+" if (r["foreign"] or 0)>0 else "")}{int(r["foreign"] or 0):,}張</span>'
    if r.get("margin_ratio"):
        inst+=f' <span style="color:#94a3b8;font-size:10px">融資率{r["margin_ratio"]:.1f}%</span>'
    return f'''<div style="background:{"linear-gradient(135deg,#071507,#080f1f)" if r["wave"]>=80 else "#0b1120"};border:1px solid {"#22c55e22" if r["wave"]>=80 else "#1e293b"};border-radius:14px;padding:14px;margin-bottom:10px;position:relative">
  <div style="position:absolute;top:10px;right:12px;text-align:center"><div style="font-size:22px;font-weight:900;color:{sc(r["wave"])};font-family:monospace;line-height:1">{r["wave"]}</div><div style="font-size:8px;color:#475569">大波評分</div></div>
  <div style="padding-right:48px">
    <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:4px">
      <span style="font-size:15px;font-weight:800">{r["name"]}</span>
      <span style="font-size:10px;color:#64748b;font-family:monospace">{r["code"]}</span>
      {badge(f"{stg[2]} {r['stage']}",stg[0],stg[1])}
      {badge(f"● {r['gpt']}",gpc[0],gpc[1])}
      {dream_badge}
    </div>
    <div style="font-size:10px;color:#64748b;margin-bottom:8px">
      收盤 <b style="color:#f1f5f9;font-family:monospace">{r["price"]:.1f}</b>
      &nbsp;乖離<b style="color:{"#f87171" if abs(r["div20"])>20 else "#94a3b8"}">{r["div20"]:+.1f}%</b>
      &nbsp;量比<b style="color:{"#4ade80" if r["vol_r"]>=1.2 else "#94a3b8"}">{r["vol_r"]}×</b>
      &nbsp;<span style="color:#334155">{r["date"]}</span>{inst}
    </div>
    <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px">
      <div style="text-align:center;padding:3px 10px;background:#0a0f1a;border-radius:7px;border:1px solid #60a5fa33"><div style="font-size:8px;color:#475569">拉回觀察</div><div style="font-size:11px;font-weight:700;color:#60a5fa;font-family:monospace">{r["pull"]}</div></div>
      <div style="text-align:center;padding:3px 10px;background:#0a0f1a;border-radius:7px;border:1px solid #4ade8033"><div style="font-size:8px;color:#475569">突破確認</div><div style="font-size:11px;font-weight:700;color:#4ade80;font-family:monospace">{r["breakout"]}</div></div>
      <div style="text-align:center;padding:3px 10px;background:#0a0f1a;border-radius:7px;border:1px solid #f8717133"><div style="font-size:8px;color:#475569">轉弱失效</div><div style="font-size:11px;font-weight:700;color:#f87171;font-family:monospace">{r["weak"]}</div></div>
    </div>
    {risk_html}
  </div>
  <details style="margin-top:8px"><summary style="font-size:9px;color:#334155;cursor:pointer">▼ 展開詳細分析</summary>
    <div style="margin-top:8px;border-top:1px solid #1e293b;padding-top:8px">{bars}<div style="display:flex;flex-wrap:wrap;gap:3px;margin-top:6px">{ma_html}</div></div>
  </details>
</div>'''

def make_html(df, today):
    top   =df[(df["wave"]>=65)&(df["risk_n"]==0)].sort_values("wave",ascending=False)
    dream =df[df["dream"]=="捕夢網✨"].sort_values("dream_score",ascending=False)
    flying=df[df["stage"]=="夢想起飛"].sort_values("wave",ascending=False)
    wait  =df[df["stage"]=="量縮整理"].sort_values("wave",ascending=False)
    risky =df[df["risk_n"]>0]
    def sec(title,sub,limit=20):
        if sub.empty: return ""
        return f'<div style="margin-bottom:24px"><h2 style="font-size:14px;font-weight:800;color:#f1f5f9;margin:0 0 10px;padding:8px 12px;background:#0a1628;border-radius:10px;border-left:3px solid #3b82f6">{title}</h2>'+"".join(card_html(r) for _,r in sub.head(limit).iterrows())+"</div>"
    body=(sec(f"⭐ 今日精選（≥65分，共{len(top)}檔）",top)
         +sec(f"🕸️ 捕夢網買點（{len(dream)}檔）",dream)
         +sec(f"🚀 夢想起飛（{len(flying)}檔）",flying)
         +sec(f"⏸️ 量縮整理等突破（{len(wait)}檔）",wait)
         +sec(f"⚠️ 風險警示（{len(risky)}檔）",risky))
    return f'''<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>波波鴨選股 {today}</title>
<style>*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#020817;color:#f1f5f9;font-family:"Noto Sans TC",system-ui,sans-serif;padding:0}}details summary::-webkit-details-marker{{display:none}}</style>
</head><body>
<div style="background:linear-gradient(135deg,#030a18,#0a1628);padding:14px;border-bottom:1px solid #1e293b;position:sticky;top:0;z-index:100">
  <div style="max-width:800px;margin:0 auto;display:flex;align-items:center;gap:10px">
    <span style="font-size:24px">🦆</span>
    <div style="flex:1"><div style="font-size:16px;font-weight:900;letter-spacing:2px">波波鴨選股報告</div>
    <div style="font-size:10px;color:#475569">{today} · TWSE公開資料 · 大波經×捕夢網</div></div>
    <div style="display:flex;gap:10px">
      <div style="text-align:center"><div style="font-size:18px;font-weight:900;color:#4ade80">{len(top)}</div><div style="font-size:8px;color:#475569">精選</div></div>
      <div style="text-align:center"><div style="font-size:18px;font-weight:900;color:#fde68a">{len(dream)}</div><div style="font-size:8px;color:#475569">捕夢網</div></div>
      <div style="text-align:center"><div style="font-size:18px;font-weight:900;color:#94a3b8">{len(df)}</div><div style="font-size:8px;color:#475569">分析</div></div>
    </div>
  </div>
  <div style="max-width:800px;margin:8px auto 0;display:flex;gap:5px;overflow-x:auto">
    <a href="#s1" style="color:#60a5fa;font-size:11px;padding:3px 10px;background:#1e3a5f;border-radius:6px;text-decoration:none;white-space:nowrap">⭐精選</a>
    <a href="#s2" style="color:#fde68a;font-size:11px;padding:3px 10px;background:#3a2800;border-radius:6px;text-decoration:none;white-space:nowrap">🕸️捕夢網</a>
    <a href="#s3" style="color:#4ade80;font-size:11px;padding:3px 10px;background:#1a3a1a;border-radius:6px;text-decoration:none;white-space:nowrap">🚀夢想起飛</a>
    <a href="#s4" style="color:#c084fc;font-size:11px;padding:3px 10px;background:#2a1a3a;border-radius:6px;text-decoration:none;white-space:nowrap">⏸️量縮整理</a>
  </div>
</div>
<div style="max-width:800px;margin:0 auto;padding:12px">
  <div id="s1"></div>{body}
  <div style="padding:10px;background:#080f1f;border-radius:10px;border:1px solid #1e293b;font-size:10px;color:#334155;line-height:1.8">
    ⚠️ 資料來源：台灣證券交易所公開資料。僅供學習參考，不構成投資建議。
  </div>
</div></body></html>'''

# ══════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════
def main():
    today = date.today().strftime("%Y/%m/%d")
    print(f"\n{'═'*60}")
    print(f"  🦆 波波鴨選股系統 | {today}")
    print(f"{'═'*60}\n")

    results = []
    for code,name in STOCK_POOL.items():
        r = analyze_stock(code, name)
        if r: results.append(r)

    if not results:
        notify("\n🦆 波波鴨：今日無法取得資料")
        return

    df = pd.DataFrame(results)
    top   = df[(df["wave"]>=65)&(df["risk_n"]==0)].sort_values("wave",ascending=False)
    dream = df[df["dream"]=="捕夢網✨"].sort_values("dream_score",ascending=False)
    flying= df[df["stage"]=="夢想起飛"].sort_values("wave",ascending=False)
    wait  = df[df["stage"]=="量縮整理"].sort_values("wave",ascending=False)

    # ── Telegram + LINE 推播 ──
    notify(
        f"\n🦆 波波鴨選股報告\n📅 {today}\n"
        f"分析{len(df)}檔 | ⭐精選{len(top)} | 🕸️捕夢網{len(dream)}",
        f"🦆 <b>波波鴨選股報告</b>\n📅 {today}\n"
        f"分析{len(df)}檔 | ⭐精選<b>{len(top)}</b> | 🕸️捕夢網<b>{len(dream)}</b>"
    )

    def fmt(r, rank=None):
        stg={"主升段":"🔥","行進段":"📈","夢想起飛":"🚀","量縮整理":"⏸️","打地基":"🧱","稜線段":"⚠️","下山":"📉"}.get(r["stage"],"")
        dr=" 🕸️" if r.get("dream")=="捕夢網✨" else ""
        rk=f"{rank}." if rank else "→"
        inst=f" 外資{('+' if (r.get('foreign') or 0)>0 else '')}{int(r.get('foreign') or 0):,}張" if r.get("foreign") is not None else ""
        risks=[k for k,v in r.get("risks",{}).items() if v]
        rstr=f" ⚠️{','.join(risks)}" if risks else ""
        plain=(f"\n{rk} {r['name']}({r['code']}){dr}"
               f"\n   ${r['price']:.1f} 評分{r['wave']} {stg}{r['stage']} {r['gpt']}"
               f"\n   拉回:{r['pull']} 突破:{r['breakout']} 轉弱:{r['weak']}{inst}{rstr}")
        html =(f"\n{rk} <b>{r['name']}({r['code']})</b>{dr}"
               f"\n   <code>{r['price']:.1f}</code> 評分<b>{r['wave']}</b> {stg}{r['stage']} {r['gpt']}"
               f"\n   拉回:{r['pull']} 突破:{r['breakout']} 轉弱:{r['weak']}{inst}{rstr}")
        return plain, html

    if not top.empty:
        plains,htmls=["⭐ 今日精選"],["⭐ <b>今日精選</b>"]
        for i,(_,r) in enumerate(top.head(10).iterrows(),1):
            p,h=fmt(r,i); plains.append(p); htmls.append(h)
        notify("\n".join(plains), "\n".join(htmls))

    if not dream.empty:
        plains,htmls=["🕸️ 捕夢網買點"],["🕸️ <b>捕夢網買點</b>"]
        for _,r in dream.head(8).iterrows():
            p,h=fmt(r); plains.append(p); htmls.append(h)
        notify("\n".join(plains), "\n".join(htmls))

    if not flying.empty:
        plains,htmls=["🚀 夢想起飛"],["🚀 <b>夢想起飛</b>"]
        for _,r in flying.head(6).iterrows():
            p,h=fmt(r); plains.append(p); htmls.append(h)
        notify("\n".join(plains), "\n".join(htmls))

    if not wait.empty:
        plains,htmls=["⏸️ 量縮整理等突破"],["⏸️ <b>量縮整理等突破</b>"]
        for _,r in wait.head(6).iterrows():
            p,h=fmt(r); plains.append(p); htmls.append(h)
        notify("\n".join(plains), "\n".join(htmls))

    notify("\n⚠️ 僅供學習參考，非投資建議。")

    # ── 產生 HTML 報告 ──
    html = make_html(df, today)
    with open("report.html","w",encoding="utf-8") as f: f.write(html)
    print("\n✅ HTML 報告已產生：report.html")
    print("✅ 推播完成！")

if __name__ == "__main__":
    main()
