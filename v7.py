import streamlit as st
import yfinance as yf
import pandas as pd
import time
import datetime
import requests
from google import genai

# --- 1. 安全配置 (從 Secrets 讀取) ---
try:
    # Telegram 配置
    TG_TOKEN = st.secrets["telegram"]["bot_token"]
    TG_CHAT_ID = st.secrets["telegram"]["chat_id"]
    # Gemini 配置
    client = genai.Client(api_key=st.secrets["gemini"]["api_key"])
except Exception as e:
    st.error(f"❌ 配置錯誤: {e}")
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
    """自動調用 Gemini 1.5 Flash 生成建議"""
    prompt = f"你是操盤手，分析{sym}。VIX:{vix:.2f}, 短線:{info1['trend']}, 長線:{info15['trend']}。請給出40字內操作建議。"
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash", 
            contents=prompt
        )
        return response.text
    except:
        return "AI 分析暫時不可用。"

def fetch_data(symbol, interval, period):
    """抓取數據並計算 EMA"""
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
        
        last, prev = df.iloc[-1], df.iloc[-2]
        trend = "多頭" if last['EMA9'] > last['EMA21'] else "空頭"
        
        # 偵測交叉訊號
        signal = None
        if prev['EMA9'] <= prev['EMA21'] and last['EMA9'] > last['EMA21']:
            signal = "🚀 黃金交叉"
        elif prev['EMA9'] >= prev['EMA21'] and last['EMA9'] < last['EMA21']:
            signal = "💀 死亡交叉"
            
        return {"df": df, "trend": trend, "signal": signal, "price": float(last['Close'])}
    except:
        return None

# --- 3. Streamlit UI 介面 ---
st.set_page_config(page_title="AI 自動交易助手", layout="wide")
st.title("🤖 全自動 AI 監控 & Telegram 推送")

symbols = [s.strip().upper() for s in st.sidebar.text_input("監控列表", "NVDA, TSLA, BTC-USD").split(",")]
st.info(f"系統運行中... 監控週期: 1m & 15m。當前監控: {', '.join(symbols)}")

placeholder = st.empty()

# --- 4. 無限監控迴圈 ---
while True:
    with placeholder.container():
        # 抓取 VIX
        v_df = yf.download("^VIX", period="1d", interval="2m", progress=False)
        curr_vix = float(v_df['Close'].iloc[-1]) if not v_df.empty else 20.0
        st.metric("當前市場 VIX", f"{curr_vix:.2f}")

        for sym in symbols:
            info1 = fetch_data(sym, "1m", "1d")
            info15 = fetch_data(sym, "15m", "5d")
            
            if info1 and info15:
                # 檢查是否有訊號且不在冷卻期 (10分鐘)
                now = datetime.datetime.now()
                last_time = st.session_state.last_alert_time.get(sym)
                
                # 如果偵測到訊號 (金叉或死叉)
                if info1['signal']:
                    # 冷卻檢查：避免同一個訊號在短時間內重複發送
                    if not last_time or (now - last_time).total_seconds() > 600:
                        
                        # --- 觸發 AI 分析 ---
                        with st.spinner(f"偵測到 {sym} 訊號，正在生成 AI 建議..."):
                            advice = get_ai_advice_auto(sym, info1, info15, curr_vix)
                        
                        # --- 組合訊息並發送到 Telegram ---
                        tg_msg = (
                            f"{info1['signal']}！\n"
                            f"📌 標的: {sym}\n"
                            f"💰 價格: {info1['price']:.2f}\n"
                            f"📊 趨勢: 長線{info15['trend']} / 短線{info1['trend']}\n"
                            f"🤖 AI 建議: {advice}"
                        )
                        send_telegram_msg(tg_msg)
                        
                        # 更新最後發送時間
                        st.session_state.last_alert_time[sym] = now
                        st.success(f"✅ {sym} 訊號已推送到 Telegram")
                
                # 在網頁端也顯示當前狀態
                st.write(f"⏱️ {now.strftime('%H:%M:%S')} - {sym}: {info1['trend']} (無新訊號)")

        time.sleep(60) # 每分鐘掃描一次
        st.rerun()
