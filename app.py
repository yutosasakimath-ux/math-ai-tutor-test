import streamlit as st
import google.generativeai as genai
from PIL import Image
import datetime

# --- 1. アプリの初期設定 ---
st.set_page_config(page_title="AI数学専属コーチ", page_icon="🎓", layout="centered")

# --- ビジネスモデルBの肝: 「誰が」勉強しているか ---
if "student_name" not in st.session_state:
    st.session_state.student_name = "ゲスト"

st.title("🎓 高校数学 AI専属コーチ")
st.caption("教科書の内容を「完璧」に理解しよう。答えは教えません、一緒に解きます。")

# --- 2. 会話履歴と利用カウントの保存場所 ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# ★ デバッグ用: 最後に使われたモデル名を保存する変数 ★
if "last_used_model" not in st.session_state:
    st.session_state.last_used_model = "まだ回答していません"

# 赤字防止カウンター
if "pro_usage_count" not in st.session_state:
    st.session_state.pro_usage_count = 0
if "last_reset_date" not in st.session_state:
    st.session_state.last_reset_date = datetime.date.today()

if st.session_state.last_reset_date != datetime.date.today():
    st.session_state.pro_usage_count = 0
    st.session_state.last_reset_date = datetime.date.today()

# リセット用キー管理
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0
if "form_key_index" not in st.session_state:
    st.session_state.form_key_index = 0

# --- 3. サイドバー（設定） ---
with st.sidebar:
    st.header("⚙️ 設定")
    
    st.session_state.student_name = st.text_input("あなたのお名前", value=st.session_state.student_name)
    
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
    
    if st.button("🗑️ 会話をリセット", type="primary"):
        st.session_state.messages = []
        st.session_state.last_used_model = "リセット済み" # デバッグ表示もリセット
        st.rerun()

    # ★★★ デバッグ用表示エリア（完成版ではここを消すだけ！） ★★★
    st.markdown("---")
    st.caption("🛠️ 開発者用デバッグ情報")
    if "pro" in st.session_state.last_used_model:
        st.error(f"Last Model: {st.session_state.last_used_model}") # Proなら赤色で警告っぽく表示
    else:
        st.success(f"Last Model: {st.session_state.last_used_model}") # Flashなら緑色で表示
    
    st.write(f"Pro Count: {st.session_state.pro_usage_count} / 15")

# --- 4. プロンプト定義 ---
system_instruction = f"""
あなたは日本の進学校で教える、非常に優秀で忍耐強い数学教師です。
相手は高校生の「{st.session_state.student_name}」さんです。

【指導の絶対ルール】
1. **ソクラテス式指導:** 答えを教えず、問いかけで導くこと。
2. **教科書準拠:** 高校数学の範囲内で解説すること。
3. **優しさと承認:** 否定せず、褒めて伸ばすこと。
4. **形式:** 数式はLaTeX形式（$マーク）を使用すること。

【画像について】
問題を読み取り、方針のヒントを出してください。
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

# --- 6. AI応答ロジック（デバッグ情報保存機能付き） ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    if not api_key:
        st.warning("左のサイドバーでAPIキーを設定してください。")
        st.stop()
    
    genai.configure(api_key=api_key)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        
        # 履歴構築
        history_for_ai = []
        for m in st.session_state.messages[:-1]:
            if m["role"] != "system":
                text_content = ""
                if isinstance(m["content"], dict):
                    text_content = m["content"].get("text", "")
                else:
                    text_content = str(m["content"])
                history_for_ai.append({"role": m["role"], "parts": [text_content]})

        current_msg = st.session_state.messages[-1]["content"]
        content_to_send = []
        if isinstance(current_msg, dict):
            if "text" in current_msg: content_to_send.append(current_msg["text"])
            if "image" in current_msg: content_to_send.append(current_msg["image"])
        else:
            content_to_send.append(current_msg)

        # ★★★ 戦略的モデル優先順位 ★★★
        PRIORITY_MODELS = [
            "gemini-2.5-flash",       # メイン
            "gemini-1.5-pro",         # バックアップ
            "gemini-2.0-flash"        # 予備
        ]
        
        PRO_LIMIT_PER_DAY = 15

        success = False
        active_model = None
        last_error = None
        
        # 試行関数
        def try_generate(model_name):
            retry_model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
            chat = retry_model.start_chat(history=history_for_ai)
            return chat.send_message(content_to_send, stream=True)

        for model_name in PRIORITY_MODELS:
            if "pro" in model_name and st.session_state.pro_usage_count >= PRO_LIMIT_PER_DAY:
                continue

            try:
                response = try_generate(model_name)
                for chunk in response:
                    if chunk.text:
                        full_response += chunk.text
                        response_placeholder.markdown(full_response)
                
                success = True
                active_model = model_name
                
                if "pro" in model_name:
                    st.session_state.pro_usage_count += 1
                
                break
            except Exception:
                continue
        
        if not success:
            if st.session_state.pro_usage_count >= PRO_LIMIT_PER_DAY:
                st.warning("⚠️ 本日の「高度な学習モード（Pro）」の利用上限に達しました。現在は回線が混み合っており、明日またご利用いただけます。")
            else:
                try:
                    fetched_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                    for model_name in fetched_models:
                        if "pro" not in model_name:
                            try:
                                response = try_generate(model_name)
                                for chunk in response:
                                    if chunk.text:
                                        full_response += chunk.text
                                        response_placeholder.markdown(full_response)
                                success = True
                                active_model = model_name
                                break
                            except:
                                continue
                except:
                    pass
                
                if success:
                    st.session_state.messages.append({"role": "model", "content": full_response})
                    # ★ デバッグ情報保存 ★
                    st.session_state.last_used_model = active_model
                    st.rerun()
                else:
                    st.error("❌ 現在アクセスが集中しており応答できません。")

        if success:
            st.session_state.messages.append({"role": "model", "content": full_response})
            # ★ デバッグ情報保存 ★
            st.session_state.last_used_model = active_model
            print(f"Used Model: {active_model}, Pro Count Today: {st.session_state.pro_usage_count}")
            st.rerun()

# --- 7. 入力エリア ---
if not (st.session_state.messages and st.session_state.messages[-1]["role"] == "user"):
    
    current_key = st.session_state.form_key_index
    uploader_key = f"uploader_{current_key}"

    input_type = st.radio("入力モード", ["⌨️ テキストで質問", "📸 画像で質問"], horizontal=True, label_visibility="collapsed")

    if input_type == "⌨️ テキストで質問":
        with st.form(key=f'text_form_{current_key}'):
            user_text = st.text_area("ここに入力...", height=100, placeholder="例：教科書のこの定義がよく分かりません...")
            submit_btn = st.form_submit_button("送信", type="primary")
            
            if submit_btn and user_text:
                st.session_state.messages.append({"role": "user", "content": user_text})
                st.session_state.form_key_index += 1
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
                st.session_state.form_key_index += 1
                st.rerun()
            else:
                st.warning("画像を選択してください。")
