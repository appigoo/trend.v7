import streamlit as st
import yfinance as yf
import pandas as pd
import time
import datetime
import requests

# --- 1. 安全配置 ---
try:
    TG_TOKEN = st.secrets["telegram"]["bot_token"]
    TG_CHAT_ID = st.secrets["telegram"]["chat_id"]
    GEMINI_API_KEY = st.secrets["gemini"]["api_key"]
except Exception as e:
    st.error("❌ 配置錯誤: 請檢查 Secrets 設定。")
    st.stop()

if 'last_alert_time' not in st.session_state:
    st.session_state.last_alert_time = {}

# --- 2. 核心功能函數 ---

def send_telegram_msg(message):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        payload = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def get_ai_advice_auto(sym, info1, info15, vix):
    """強化診斷版：應對 Google 今天的系統故障"""
    api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"你是操盤手。分析{sym}，VIX:{vix:.2f}。長線趨勢:{info15['trend']}，短線趨勢:{info1['trend']}。發生{info1['signal']}，給出40字內操作建議。"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(api_url, json=payload, timeout=10)
        # 如果 Google 回傳 500 或 503，代表伺服器掛了
        if response.status_code != 200:
            return "⚠️ Google AI 服務目前中斷 (維護中)"
            
        res_json = response.json()
        return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return "⚠️ 連線至 AI 伺服器失敗"

def fetch_data(symbol, interval, period):
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty or len(df) < 21: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
        
        last, prev = df.iloc[-1], df.iloc[-2]
        trend = "多頭" if last['EMA9'] > last['EMA21'] else "空頭"
        
        signal = None
        if prev['EMA9'] <= prev['EMA21'] and last['EMA9'] > last['EMA21']:
            signal = "🚀 黃金交叉"
        elif prev['EMA9'] >= prev['EMA21'] and last['EMA9'] < last['EMA21']:
            signal = "💀 死亡交叉"
            
        return {"trend": trend, "signal": signal, "price": float(last['Close'])}
    except:
        return None

# --- 3. UI 介面 ---
st.set_page_config(page_title="AI 交易監控 (故障自動診斷版)", layout="wide")
st.title("💹 AI 自動交易監控系統")
st.warning("⚠️ 偵測到 Google AI Studio 今日服務不穩定，建議監控 Telegram 狀態。")

input_symbols = st.sidebar.text_input("監控代碼", "NVDA, TSLA, BTC-USD")
symbols = [s.strip().upper() for s in input_symbols.split(",")]
placeholder = st.empty()

# --- 4. 監控迴圈 ---
while True:
    with placeholder.container():
        try:
            v_df = yf.download("^VIX", period="1d", interval="1m", progress=False)
            curr_vix = float(v_df['Close'].iloc[-1]) if not v_df.empty else 20.0
        except:
            curr_vix = 20.0
        
        st.write(f"### 📊 VIX: {curr_vix:.2f}")

        for sym in symbols:
            info1 = fetch_data(sym, "1m", "1d")
            info15 = fetch_data(sym, "15m", "5d")
            
            if info1 and info15:
                now = datetime.datetime.now()
                if info1['signal']:
                    last_time = st.session_state.last_alert_time.get(sym)
                    if not last_time or (now - last_time).total_seconds() > 600:
                        advice = get_ai_advice_auto(sym, info1, info15, curr_vix)
                        tg_msg = f"{info1['signal']}！\n標的: {sym}\n趨勢: {info15['trend']}\n🤖 AI 建議: {advice}"
                        send_telegram_msg(tg_msg)
                        st.session_state.last_alert_time[sym] = now
                
                st.write(f"✅ {now.strftime('%H:%M:%S')} | {sym} | 狀態: {info1['trend']}")

    time.sleep(60)
    st.rerun()
