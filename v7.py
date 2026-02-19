import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import time
from google import genai # 使用新版 SDK v2

# --- 1. 初始化 AI Client ---
try:
    # 確保在 secrets.toml 中有 [gemini] 區塊
    client = genai.Client(api_key=st.secrets["gemini"]["api_key"])
except Exception as e:
    st.error(f"❌ API Key 配置錯誤: {e}")
    st.stop()

# 初始化 AI 建議快取
if 'ai_cache' not in st.session_state:
    st.session_state.ai_cache = {}

# --- 2. 數據與分析函數 ---
def fetch_stock_data(symbol, interval, period):
    try:
        df = yf.download(symbol, period=period, interval=interval, progress=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        # 簡單趨勢判斷 (EMA)
        df['EMA9'] = df['Close'].ewm(span=9).mean()
        df['EMA21'] = df['Close'].ewm(span=21).mean()
        last = df.iloc[-1]
        trend = "多頭" if last['EMA9'] > last['EMA21'] else "空頭"
        
        return {"df": df, "trend": trend, "price": last['Close'], "ema9": last['EMA9'], "ema21": last['EMA21']}
    except:
        return None

# --- 3. UI 主體 ---
st.set_page_config(page_title="專業 AI 監控", layout="wide")
st.sidebar.header("監控配置")
symbols = [s.strip().upper() for s in st.sidebar.text_input("輸入股票代碼", "NVDA, TSLA, 2330.TW").split(",")]

placeholder = st.empty()

while True:
    with placeholder.container():
        # VIX 狀態
        vix_df = yf.download("^VIX", period="1d", interval="2m", progress=False)
        curr_vix = float(vix_df['Close'].iloc[-1]) if not vix_df.empty else 20.0
        st.metric("VIX 恐慌指數", f"{curr_vix:.2f}", help="VIX 越高，操作越需謹慎")
        
        # --- 迴圈開始 (sym 在這裡定義) ---
        for sym in symbols:
            info1 = fetch_stock_data(sym, "1m", "1d")
            info15 = fetch_stock_data(sym, "15m", "5d")
            
            if info1 and info15:
                with st.expander(f"📊 {sym} 分析詳情 (1m:{info1['trend']} | 15m:{info15['trend']})", expanded=True):
                    col_info, col_ai = st.columns([1, 2])
                    
                    with col_info:
                        st.metric("當前價格", f"{info1['price']:.2f}")
                        st.write(f"短線 EMA9: {info1['ema9']:.2f}")
                        st.write(f"長線趨勢: **{info15['trend']}**")
                    
                    with col_ai:
                        # 關鍵修正：st.button 必須在 sym 作用域內，且 key 需唯一
                        btn_key = f"diag_{sym}"
                        if st.button(f"🔍 AI 深度診斷 {sym}", key=btn_key):
                            with st.spinner(f"正在分析 {sym}..."):
                                # 調用新版 SDK v2
                                prompt = f"你是操盤手，分析{sym}。VIX:{curr_vix:.2f}, 1m趨勢:{info1['trend']}, 15m趨勢:{info15['trend']}。給出40字內操作建議。"
                                try:
                                    response = client.models.generate_content(
                                        model="gemini-2.0-flash", 
                                        contents=prompt
                                    )
                                    st.session_state.ai_cache[sym] = response.text
                                except Exception as e:
                                    st.session_state.ai_cache[sym] = f"分析失敗: {e}"
                        
                        # 顯示診斷內容
                        advice = st.session_state.ai_cache.get(sym, "尚未進行診斷，請點擊按鈕。")
                        st.info(f"**AI 建議：**\n{advice}")

                    # 雙週期圖表展示
                    chart_col1, chart_col2 = st.columns(2)
                    with chart_col1:
                        st.caption("1m 週期 (短線進場)")
                        st.line_chart(info1['df'][['Close', 'EMA9', 'EMA21']].tail(50))
                    with chart_col2:
                        st.caption("15m 週期 (長線趨勢)")
                        st.line_chart(info15['df'][['Close', 'EMA9', 'EMA21']].tail(50))

        time.sleep(60)
        st.rerun()
