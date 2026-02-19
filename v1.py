from google import genai
import streamlit as st

# 從 Streamlit Secrets 取得 Key 並建立 Client
client = genai.Client(api_key=st.secrets["gemini"]["api_key"])

def get_ai_advice_v2(sym, info_1m, info_15m):
    # 使用新版 SDK 的語法
    prompt = f"你是操盤手，分析 {sym}: 短線 {info_1m['trend']}, 長線 {info_15m['trend']}。請給建議。"
    
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash", # 使用最新的 2.0 模型，反應極快
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"AI 診斷失敗: {str(e)}"

# --- 在 UI 中的應用 ---
if st.button(f"🔍 AI 深度診斷 {sym}"):
    with st.spinner("思考中..."):
        advice = get_ai_advice_v2(sym, info1, info15)
        st.session_state.ai_cache[sym] = advice
        st.write(advice)
