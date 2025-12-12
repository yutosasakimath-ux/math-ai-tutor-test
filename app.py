import streamlit as st
import google.generativeai as genai
from PIL import Image

# --- 1. アプリの初期設定 ---
st.set_page_config(page_title="AI数学専属コーチ", page_icon="🎓", layout="centered")

# --- ビジネスモデルBの肝: 「誰が」勉強しているか ---
if "student_name" not in st.session_state:
    st.session_state.student_name = "ゲスト"

st.title("🎓 高校数学 AI専属コーチ")
st.caption("教科書の内容を「完璧」に理解しよう。答えは教えません、一緒に解きます。")

# --- 2. 会話履歴の保存場所 ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# リセット用キー管理
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0
if "form_key_index" not in st.session_state:
    st.session_state["form_key_index"] = 0

# --- 3. サイドバー（設定） ---
with st.sidebar:
    st.header("⚙️ 設定")
    
    # 生徒情報の入力
    st.session_state.student_name = st.text_input("あなたのお名前", value=st.session_state.student_name)
    
    # APIキー設定
    api_key = ""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["GEMINI_API_KEY"]
    except:
        pass
    
    if not api_key:
        input_key = st.text_input("Gemini APIキー", type="password")
        if input_key: api_key = input_key.strip()
    
    st.markdown("---")
    
    st.info(f"ようこそ、{st.session_state.student_name}さん。\n焦らず基礎から固めていきましょう。")

    st.markdown("---")
    
    # 手動リセットボタン
    if st.button("🗑️ 会話をリセット", type="primary"):
        st.session_state.messages = []
        st.rerun()

# --- 4. プロンプト定義（教科書完全準拠・品質重視） ---
system_instruction = f"""
あなたは日本の進学校で教える、非常に優秀で忍耐強い数学教師です。
相手は高校生の「{st.session_state.student_name}」さんです。
数学が苦手、または赤点回避を目指している生徒に対して、**教科書の定義に基づいた正確かつ分かりやすい指導**を行ってください。

【指導の絶対ルール】
1. **ソクラテス式指導:** - 答えをすぐに教えないでください。
   - 「この公式は覚えている？」「図を描いてみた？」など、スモールステップで問いかけてください。
2. **教科書準拠:** - 突飛な解法（ロピタルの定理などの大学範囲）は避け、高校数学の教科書範囲内の解法で導いてください。
   - 定義や定理の使用条件（例：真数条件、判別式の条件）には厳密であってください。
3. **優しさと承認:**
   - 生徒が間違えても絶対に否定せず、「惜しい！」「その考え方は面白いね」と承認してから修正してください。
4. **形式:**
   - 数式は必ずLaTeX形式（$マーク）を使って綺麗に表示してください。
   - 長文で畳み掛けず、会話のキャッチボールを重視してください。

【画像が送られた場合】
- 画像内の問題を読み取り、「どの方針で迷ってる？」とヒントを出してください。
"""

# --- 5. チャット表示エリア ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        content = message["content"]
        if isinstance(content, dict):
            if "image" in content:
                st.image(content["image"], width=300)
            if "text" in content:
                st.markdown(content["text"])
        else:
            st.markdown(content)

# --- 6. AI応答ロジック（品質重視のモデル選定） ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    if not api_key:
        st.warning("左のサイドバーでAPIキーを設定してください。")
        st.stop()
    
    # 設定
    genai.configure(api_key=api_key)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        
        # 履歴の構築
        history_for_ai = []
        for m in st.session_state.messages[:-1]:
            if m["role"] != "system":
                text_content = ""
                if isinstance(m["content"], dict):
                    text_content = m["content"].get("text", "")
                else:
                    text_content = str(m["content"])
                history_for_ai.append({"role": m["role"], "parts": [text_content]})

        # 最新メッセージ
        current_msg = st.session_state.messages[-1]["content"]
        content_to_send = []
        if isinstance(current_msg, dict):
            if "text" in current_msg: content_to_send.append(current_msg["text"])
            if "image" in current_msg: content_to_send.append(current_msg["image"])
        else:
            content_to_send.append(current_msg)

        # ★★★ 品質最優先のモデル設定 ★★★
        # 教科書レベルを「完璧」に説明するため、賢いモデルだけを使います。
        PRIORITY_MODELS = [
            "gemini-2.5-flash",       # 第1候補: 最新鋭。賢さと速度のバランスが最高。
            "gemini-1.5-pro",         # 第2候補: 実績ある賢いモデル（Flashがダメな時の保険）
            "gemini-2.0-flash"        # 第3候補: 予備
            # "gemini-1.5-flash" は除外しました（解説の質にブレがあるため）
        ]
        
        success = False
        last_error = None
        
        # 試行関数
        def try_generate(model_name):
            retry_model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
            chat = retry_model.start_chat(history=history_for_ai)
            return chat.send_message(content_to_send, stream=True)

        # A. 優先リストでトライ
        active_model = None
        for model_name in PRIORITY_MODELS:
            try:
                response = try_generate(model_name)
                for chunk in response:
                    if chunk.text:
                        full_response += chunk.text
                        response_placeholder.markdown(full_response)
                success = True
                active_model = model_name
                break
            except Exception:
                continue
        
        # B. 優先リストが全滅した場合、サーバーから「使えるモデル」を取得して再トライ
        if not success:
            try:
                fetched_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                for model_name in fetched_models:
                    try:
                        response = try_generate(model_name)
                        for chunk in response:
                            if chunk.text:
                                full_response += chunk.text
                                response_placeholder.markdown(full_response)
                        success = True
                        active_model = model_name
                        break
                    except Exception as e:
                        last_error = e
                        continue
            except Exception as e:
                last_error = e

        if success:
            st.session_state.messages.append({"role": "model", "content": full_response})
            # 管理用ログ
            print(f"Used Model: {active_model}")
            st.rerun()
        else:
            st.error("❌ 接続エラー: 現在AIが応答できません。")
            print(f"Connection Failed. Last Error: {last_error}")

# --- 7. 入力エリア ---
if not (st.session_state.messages and st.session_state.messages[-1]["role"] == "user"):
    
    current_key = st.session_state["form_key_index"]
    uploader_key = f"uploader_{current_key}"

    input_type = st.radio("入力モード", ["⌨️ テキストで質問", "📸 画像で質問"], horizontal=True, label_visibility="collapsed")

    if input_type == "⌨️ テキストで質問":
        with st.form(key=f'text_form_{current_key}'):
            user_text = st.text_area("ここに入力...", height=100, placeholder="例：教科書のこの定義がよく分かりません...")
            submit_btn = st.form_submit_button("送信", type="primary")
            
            if submit_btn and user_text:
                st.session_state.messages.append({"role": "user", "content": user_text})
                st.session_state["form_key_index"] += 1
                st.rerun()

    elif input_type == "📸 画像で質問":
        st.info("教科書や問題集の写真をアップロードしてください。")
        img_file = st.file_uploader("画像をアップロード", type=["jpg", "png", "jpeg"], key=uploader_key)
        img_comment = st.text_input("補足（任意）", placeholder="例：(2)の解説をお願いします", key=f"comment_{current_key}")
        
        if st.button("画像で質問する", type="primary"):
            if img_file:
                image_data = Image.open(img_file)
                text_part = img_comment if img_comment else "この問題について教えてください。"
                content_to_save = {"image": image_data, "text": text_part}
                
                st.session_state.messages.append({"role": "user", "content": content_to_save})
                st.session_state["form_key_index"] += 1
                st.rerun()
            else:
                st.warning("画像を選択してください。")
