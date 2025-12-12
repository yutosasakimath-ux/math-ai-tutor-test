import streamlit as st
import google.generativeai as genai
from PIL import Image

# --- 1. アプリの初期設定 ---
st.set_page_config(page_title="AI数学専属コーチ", page_icon="🎓", layout="centered")

# --- ビジネスモデルBの肝: 「誰が」勉強しているか ---
# ここで個人の学習ログを特定します（将来的にDB連携・レポート送信に使います）
if "student_name" not in st.session_state:
    st.session_state.student_name = "ゲスト"

st.title("🎓 高校数学 AI専属コーチ")
st.caption("答えは教えません。「解き方」を一緒に考えましょう。")

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
    
    # 生徒情報の入力（レポート機能への布石）
    st.session_state.student_name = st.text_input("あなたのお名前", value=st.session_state.student_name)
    
    # APIキー設定
    api_key = ""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["GEMINI_API_KEY"]
            st.success("✅ 認証済み")
    except:
        pass
    if not api_key:
        input_key = st.text_input("Gemini APIキー", type="password")
        if input_key: api_key = input_key.strip()
    
    st.markdown("---")
    
    # モードは「学習（ソクラテス）」に一本化し、シンプルに
    st.info(f"ようこそ、{st.session_state.student_name}さん。\n今日も一緒に頑張りましょう！")

    st.markdown("---")
    
    # 手動リセットボタン
    if st.button("🗑️ 会話をリセット", type="primary"):
        st.session_state.messages = []
        st.rerun()

# --- 4. プロンプト定義（ソクラテス式・教育特化） ---
# ここがあなたのビジネスの「商品価値（USP）」です。
system_instruction = f"""
あなたはプロの数学家庭教師です。相手は高校生の「{st.session_state.student_name}」さんです。
以下のルールを厳格に守ってください。

【絶対ルール：ソクラテス式指導】
1. **答えをすぐに教えないこと。** 生徒が自分で気づくように導いてください。
2. 生徒から質問や画像の送信があった場合、「どこまで分かった？」「何が分からない？」と優しく問いかけてください。
3. 決して上から目線にならず、伴走するパートナーとして振る舞ってください。
4. 数式はLaTeX形式（$マーク）を使って綺麗に表示してください。
5. 解説が長くなりすぎないように、会話のキャッチボールを重視してください。

【画像が送られた場合】
- 画像内の問題を読み取り、いきなり解答を書くのではなく、「この問題のどの方針で迷ってる？」とヒントを出してください。
"""

# --- 5. モデルのセットアップ ---
if api_key:
    genai.configure(api_key=api_key)
    try:
        # 無料枠ならflash、精度重視ならproに変更可能
        target_model_name = "gemini-1.5-flash" 
        model = genai.GenerativeModel(target_model_name, system_instruction=system_instruction)
    except Exception as e:
        st.error(f"モデル設定エラー: {e}")
        st.stop()

# --- 6. チャット表示エリア ---
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

# --- 7. AI応答ロジック ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    if not api_key: st.stop()
    
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        try:
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

            chat = model.start_chat(history=history_for_ai)
            
            # 最新メッセージの処理
            current_msg = st.session_state.messages[-1]["content"]
            content_to_send = []
            
            if isinstance(current_msg, dict):
                if "text" in current_msg: content_to_send.append(current_msg["text"])
                if "image" in current_msg: content_to_send.append(current_msg["image"])
            else:
                content_to_send.append(current_msg)

            # ストリーミング応答
            response = chat.send_message(content_to_send, stream=True)
            
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    response_placeholder.markdown(full_response)
            
            st.session_state.messages.append({"role": "model", "content": full_response})
            st.rerun() # 状態更新のためリロード
        except Exception as e:
            st.error(f"エラー: {e}")

# --- 8. 入力エリア（シンプル化） ---
# ユーザーの発言待ち状態のときだけ表示
if not (st.session_state.messages and st.session_state.messages[-1]["role"] == "user"):
    
    # フォームのリセット用キー
    current_key = st.session_state["form_key_index"]
    uploader_key = f"uploader_{current_key}"

    # 入力モード切替（テキスト or 画像 のみ）
    input_type = st.radio("入力モード", ["⌨️ テキストで質問", "📸 画像で質問"], horizontal=True, label_visibility="collapsed")

    if input_type == "⌨️ テキストで質問":
        with st.form(key=f'text_form_{current_key}'):
            user_text = st.text_area("ここに入力...", height=100, placeholder="例：二次関数の頂点の求め方がわかりません。")
            submit_btn = st.form_submit_button("送信", type="primary")
            
            if submit_btn and user_text:
                st.session_state.messages.append({"role": "user", "content": user_text})
                st.session_state["form_key_index"] += 1
                st.rerun()

    elif input_type == "📸 画像で質問":
        st.info("分からない問題の写真をアップロードしてください。")
        img_file = st.file_uploader("画像をアップロード", type=["jpg", "png", "jpeg"], key=uploader_key)
        img_comment = st.text_input("補足（任意）", placeholder="例：(2)がわかりません", key=f"comment_{current_key}")
        
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
