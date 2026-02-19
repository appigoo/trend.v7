import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
from google import genai  # 使用新版 SDK

# --- 1. 初始化與安全配置 ---
try:
    # 確保 secrets 裡有 gemini 區塊與 api_key
    client = genai.Client(api_key=st.secrets["gemini"]["api_key"])
except Exception as e:
    st.error(f"❌ 密鑰配置錯誤: {e}")
    st.stop()

if 'ai_cache' not in st.session_state:
    st.session_state.ai_cache = {}

# --- 2. AI 診斷函數 (Gemini 2.0 Flash) ---
def get_ai_advice_v2(sym, info1, info15, vix):
    prompt = f"""
    你是專業分析師。
    標的: {sym} | VIX: {vix:.2f}
    15m長線趨勢: {info15['trend']}
    1m短線訊號: {info1['msg']} | RSI: {info1['rsi']:.1f}
    請在40字內給出操作核心建議（包含支撐/壓力觀察點）。
    """
    try:
        # 使用最新的 2.0 Flash 模型
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"AI 診斷暫時不可用: {str(e)}"

# --- 3. 數據處理函數 ---
def fetch_and_analyze(symbol, interval, period):
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 指標計算
        df['EMA9'] = df['Close'].ewm(span=9).mean()
        df['EMA21'] = df['Close'].ewm(span=21).mean()
        
        last, prev = df.iloc[-1], df.iloc[-2]
        trend = "多頭" if last['EMA9'] > last['EMA21'] else "空頭"
        msg = "穩定"
        if prev['EMA9'] <= prev['EMA21'] and last['EMA9'] > last['EMA21']: msg = "🚀金叉"
        elif prev['EMA9'] >= prev['EMA21'] and last['EMA9'] < last['EMA21']: msg = "💀死叉"
        
        return {"df": df, "trend": trend, "msg": msg, "price": last['Close'], "rsi": 50.0} # RSI 簡化
    except: return None

# --- 4. UI 介面 ---
st.set_page_config(page_title="專業級監控 v2", layout="wide")
symbols = [s.strip().upper() for s in st.sidebar.text_input("監控代碼", "NVDA, TSLA, 2330.TW").split(",")]

placeholder = st.empty()

while True:
    with placeholder.container():
        # VIX 取得
        vix_df = yf.download("^VIX", period="1d", interval="2m", progress=False)
        curr_vix = float(vix_df['Close'].iloc[-1]) if not vix_df.empty else 20.0
        st.metric("VIX 指數", f"{curr_vix:.2f}")

        # 遍歷股票清單
        for sym in symbols:
            info1 = fetch_and_analyze(sym, "1m", "1d")
            info15 = fetch_and_analyze(sym, "15m", "5d")
            
            if info1 and info15:
                # 建立 Expander，將 sym 傳入
                with st.expander(f"📈 {sym} 分析區 (短:{info1['trend']} | 長:{info15['trend']})", expanded=True):
                    col_ai, col_info = st.columns([2, 1])
                    
                    with col_ai:
                        # 修正後的按鈕邏輯：按鈕必須在 sym 被定義的迴圈內
                        # 使用 key=f"btn_{sym}" 確保每個按鈕唯一
                        if st.button(f"🔍 啟動 AI 深度診斷 ({sym})", key=f"btn_{sym}"):
                            with st.spinner("AI 正在解析盤勢..."):
                                advice = get_ai_advice_v2(sym, info1, info15, curr_vix)
                                st.session_state.ai_cache[sym] = advice
                        
                        # 顯示快取或初始文字
                        display_text = st.session_state.ai_cache.get(sym, "尚未進行 AI 診斷，點擊上方按鈕開始。")
                        st.info(f"**AI 建議：**\n{display_text}")

                    with col_info:
                        st.metric("現價", f"{info1['price']:.2f}")
                        if info1['msg'] != "穩定":
                            st.warning(f"訊號觸發: {info1['msg']}")
        
        time.sleep(60)
        st.rerun()
