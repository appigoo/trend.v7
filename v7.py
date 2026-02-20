import streamlit as st
import yfinance as yf
import pandas as pd
import time
import datetime
import requests

# --- 1. 安全配置 (從 Secrets 讀取) ---
try:
    # Telegram 配置
    TG_TOKEN = st.secrets["telegram"]["bot_token"]
    TG_CHAT_ID = st.secrets["telegram"]["chat_id"]
    # Gemini 配置
    GEMINI_API_KEY = st.secrets["gemini"]["api_key"]
except Exception as e:
    st.error(f"❌ 配置錯誤: 請檢查 Streamlit Secrets 設定。錯誤訊息: {e}")
    st.stop()

# 初始化 Session State (用於防止重複發送與冷卻)
if 'last_alert_time' not in st.session_state:
    st.session_state.last_alert_time = {}

# --- 2. 核心功能函數 ---

def send_telegram_msg(message):
    """發送訊息到 Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        payload = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"TG 發送失敗: {e}")

def get_ai_advice_auto(sym, info1, info15, vix):
    """使用 REST API 直接呼叫 Gemini (免 SDK 安裝版)"""
    # 使用 1.5 Flash 速度快且適合短評，也可改用 2.0-flash
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = (
        f"你是專業交易員。分析標的:{sym}。當前市場VIX指數:{vix:.2f}。\n"
        f"15分鐘趨勢:{info15['trend']}，1分鐘趨勢:{info1['trend']}。\n"
        f"剛發生{info1['signal']}，請在40字內給出具體操作建議。"
    )
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 100}
    }
    
    try:
        response = requests.post(api_url, json=payload, timeout=10)
        res_json = response.json()
        # 提取 AI 文字回傳
        advice = res_json['candidates'][0]['content']['parts'][0]['text']
        return advice.strip()
    except Exception as e:
        return "AI 分析暫時不可用，請檢查網路或 API Key。"

def fetch_data(symbol, interval, period):
    """抓取數據並計算 EMA"""
    try:
        # auto_adjust=True 處理除權息數據
        df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=True)
        if df.empty or len(df) < 21: return None
        
        # 處理 yfinance 的 MultiIndex 欄位
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 計算 EMA 指標
        df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        trend = "多頭" if last['EMA9'] > last['EMA21'] else "空頭"
        
        # 偵測交叉訊號
        signal = None
        if prev['EMA9'] <= prev['EMA21'] and last['EMA9'] > last['EMA21']:
            signal = "🚀 黃金交叉"
        elif prev['EMA9'] >= prev['EMA21'] and last['EMA9'] < last['EMA21']:
            signal = "💀 死亡交叉"
            
        return {"trend": trend, "signal": signal, "price": float(last['Close'])}
    except Exception as e:
        return None

# --- 3. Streamlit UI 介面 ---
st.set_page_config(page_title="AI 交易助手 (REST版)", layout="wide")
st.title("🤖 全自動 AI 監控 & Telegram 推送")

# 側邊欄配置
with st.sidebar:
    st.header("設定")
    input_symbols = st.text_input("監控列表 (逗號分隔)", "NVDA, TSLA, BTC-USD")
    symbols = [s.strip().upper() for s in input_symbols.split(",")]
    refresh_rate = st.slider("掃描頻率 (秒)", 30, 300, 60)

st.info(f"系統運行中... 監控週期: 1m (訊號) & 15m (大趨勢)。當前監控: {', '.join(symbols)}")

# 建立顯示區塊
status_table = st.empty()

# --- 4. 無限監控迴圈 ---
while True:
    with status_table.container():
        # 抓取市場恐慌指數 VIX
        try:
            v_df = yf.download("^VIX", period="1d", interval="1m", progress=False)
            curr_vix = float(v_df['Close'].iloc[-1]) if not v_df.empty else 20.0
        except:
            curr_vix = 20.0
            
        st.metric("當前市場 VIX 指數", f"{curr_vix:.2f}")

        for sym in symbols:
            info1 = fetch_data(sym, "1m", "1d")
            info15 = fetch_data(sym, "15m", "5d")
            
            if info1 and info15:
                now = datetime.datetime.now()
                last_time = st.session_state.last_alert_time.get(sym)
                
                # 偵測到 EMA 交叉訊號
                if info1['signal']:
                    # 冷卻檢查：10分鐘內不針對同一標的重複發送
                    if not last_time or (now - last_time).total_seconds() > 600:
                        
                        with st.spinner(f"正在為 {sym} 生成 AI 策略建議..."):
                            advice = get_ai_advice_auto(sym, info1, info15, curr_vix)
                        
                        # 發送到 Telegram
                        tg_msg = (
                            f"{info1['signal']}！\n"
                            f"📌 標的: {sym}\n"
                            f"💰 價格: {info1['price']:.2f}\n"
                            f"📊 趨勢: 15m {info15['trend']} / 1m {info1['trend']}\n"
                            f"🤖 AI 建議: {advice}"
                        )
                        send_telegram_msg(tg_msg)
                        
                        st.session_state.last_alert_time[sym] = now
                        st.success(f"✅ {sym} 訊號已推送到 Telegram")
                
                # 介面即時顯示
                st.write(f"⏱️ {now.strftime('%H:%M:%S')} - **{sym}**: {info1['trend']} (價格: {info1['price']:.2f})")

        time.sleep(refresh_rate)
        st.rerun()
