import streamlit as st
import yfinance as yf
import pandas as pd
import time
import datetime
import requests

# --- 1. 安全配置 (從 Secrets 讀取) ---
try:
    TG_TOKEN = st.secrets["telegram"]["bot_token"]
    TG_CHAT_ID = st.secrets["telegram"]["chat_id"]
    GEMINI_API_KEY = st.secrets["gemini"]["api_key"]
except Exception as e:
    st.error(f"❌ 配置錯誤: 請檢查 Streamlit Secrets 設定。")
    st.stop()

if 'last_alert_time' not in st.session_state:
    st.session_state.last_alert_time = {}

# --- 2. 核心功能函數 ---

def send_telegram_msg(message):
    """發送訊息到 Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        payload = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def get_ai_advice_auto(sym, info1, info15, vix):
    """使用 v1 穩定版 REST API，避開地區限制與 SDK 衝突"""
    # 切換為 v1 穩定版
    api_url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = (
        f"你是專業操盤手。分析{sym}，目前VIX:{vix:.2f}。\n"
        f"長線(15m)趨勢:{info15['trend']}，短線(1m)趨勢:{info1['trend']}。\n"
        f"剛發生{info1['signal']}，請在40字內給出具體操作建議。"
    )
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(api_url, json=payload, timeout=10)
        res_json = response.json()
        
        # 診斷：若 API 回傳錯誤訊息，直接顯示出來
        if 'error' in res_json:
            return f"AI 服務拒絕 ({res_json['error'].get('message', '未知錯誤')[:20]})"
            
        return res_json['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        return f"連線異常: {str(e)[:15]}"

def fetch_data(symbol, interval, period):
    """獲取技術指標數據"""
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

# --- 3. Streamlit UI 介面 ---
st.set_page_config(page_title="AI 監控終極版", layout="wide")
st.title("💹 AI 自動交易監控系統")

with st.sidebar:
    st.header("監控參數")
    input_symbols = st.text_input("輸入代碼 (逗號隔開)", "NVDA, TSLA, GOOGL, BTC-USD")
    symbols = [s.strip().upper() for s in input_symbols.split(",")]
    refresh_rate = st.slider("掃描頻率 (秒)", 30, 120, 60)

status_display = st.empty()

# --- 4. 監控迴圈 ---
while True:
    with status_display.container():
        # 更新 VIX
        try:
            v_df = yf.download("^VIX", period="1d", interval="1m", progress=False)
            curr_vix = float(v_df['Close'].iloc[-1]) if not v_df.empty else 20.0
        except:
            curr_vix = 20.0
        
        st.subheader(f"📊 市場恐慌指數 VIX: {curr_vix:.2f}")

        for sym in symbols:
            info1 = fetch_data(sym, "1m", "1d")
            info15 = fetch_data(sym, "15m", "5d")
            
            if info1 and info15:
                now = datetime.datetime.now()
                # 偵測交叉訊號
                if info1['signal']:
                    last_time = st.session_state.last_alert_time.get(sym)
                    # 10分鐘冷卻期，避免洗版
                    if not last_time or (now - last_time).total_seconds() > 600:
                        advice = get_ai_advice_auto(sym, info1, info15, curr_vix)
                        
                        tg_msg = (
                            f"{info1['signal']}！\n標的: {sym}\n"
                            f"價格: {info1['price']:.2f}\n"
                            f"趨勢: 長線{info15['trend']} / 短線{info1['trend']}\n"
                            f"🤖 AI 建議: {advice}"
                        )
                        send_telegram_msg(tg_msg)
                        st.session_state.last_alert_time[sym] = now
                        st.success(f"已推送 {sym} 訊號至 Telegram")
                
                st.write(f"✅ {now.strftime('%H:%M:%S')} | {sym} | 價格: {info1['price']:.2f} | 狀態: {info1['trend']}")

    time.sleep(refresh_rate)
    st.rerun()
