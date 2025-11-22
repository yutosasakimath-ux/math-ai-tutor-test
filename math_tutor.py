import streamlit as st
import google.generativeai as genai

# --- 1. アプリの初期設定 ---
st.set_page_config(page_title="数学AIチューター", page_icon="📐", layout="wide")

st.title("📐 高校数学 AIチューター")
st.caption("モードを選んで学習を始めよう！")

# --- 2. 会話履歴の保存場所 ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- 3. サイドバー（設定＆モード選択） ---
with st.sidebar:
    st.header("⚙️ 設定・モード切替")
    
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

    # ★★★ モード選択 ★★★
    mode = st.radio(
        "学習モードを選択",
        ["📖 学習モード", "⚡ 解答確認モード", "⚔️ 演習モード"],
        index=0
    )

    st.markdown("---")

    # --- ■ 1. 学習モードの機能 ---
    if mode == "📖 学習モード":
        st.info("💡 ヒントを出しながら、あなたの理解を助けます。")
        
        st.write("### 🔄 類題演習")
        num_questions = st.number_input("類題の数", 1, 5, 1)
        
        # 1-1. 問題だけ出すボタン
        if st.button("類題を出題（問題のみ）"):
            prompt_text = f"""
            【教師へのリクエスト】
            直前のやり取りで扱った問題と「同じ単元」「同じ難易度」の類題を【{num_questions}問】作成してください。
            まだ答えや解説は一切書かず、**問題文のみ**を提示してください。
            """
            st.session_state.messages.append({"role": "user", "content": prompt_text})
            st.rerun()

        st.write("👇 **答え合わせ**")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("解答のみ確認"):
                prompt_text = "直前の類題の【解答（数値・数式）のみ】を教えてください。解説は不要です。"
                st.session_state.messages.append({"role": "user", "content": prompt_text})
                st.rerun()
        
        with col2:
            if st.button("解説を含めて確認"):
                prompt_text = "直前の類題の【詳しい解説と解答】を教えてください。"
                st.session_state.messages.append({"role": "user", "content": prompt_text})
                st.rerun()

        st.markdown("---")
        if st.button("今日の学びを整理"):
            st.session_state.messages.append({"role": "user", "content": "ここまでの学習内容の要点をまとめてください。"})
            st.rerun()

    # --- ■ 2. 解答確認モードの機能 ---
    elif mode == "⚡ 解答確認モード":
        st.warning("📸 解答が知りたい問題を入力（または画像をアップ）してください。即座に答えを提示します。")
    
    # --- ■ 3. 演習モードの機能 ---
    elif mode == "⚔️ 演習モード":
        st.success("📝 指定した単元の問題を出題し、採点します。")
        
        feedback_style = st.radio(
            "採点・解説のスタイル",
            ["解答のみ（シンプル）", "解説付き（詳細）"]
        )
        st.session_state['feedback_style'] = feedback_style

        topic = st.text_input("演習したい単元（例：二次関数、確率）")
        if st.button("問題を作成開始"):
            prompt_text = f"【{topic}】に関する練習問題を1問出題してください。まだ答えは言わないでください。"
            st.session_state.messages.append({"role": "user", "content": prompt_text})
            st.rerun()

    st.markdown("---")
    
    # 共通：リセットボタン
    if st.button("🗑️ 会話をリセット", type="primary"):
        st.session_state.messages = []
        st.rerun()

# --- 4. モードごとのプロンプト定義 ---

base_instruction = """
あなたは日本の高校数学教師です。数式は必ずLaTeX形式（$マーク）で書いてください。
"""

if mode == "📖 学習モード":
    system_instruction = base_instruction + """
    【役割：ファシリテーター】
    - **絶対にすぐに答えを教えないでください**（「解答のみ確認」と指示された場合を除く）。
    - 生徒が自力で気づけるよう、問いかけやヒントで導いてください。
    - 類題作成時は、指示がない限り「問題文のみ」を出してください。
    """
elif mode == "⚡ 解答確認モード":
    system_instruction = base_instruction + """
    【役割：解答チェッカー】
    - **結論（答え）を最優先で提示してください**。
    - 解説は聞かれない限り、最低限で構いません。
    - 途中式は示しても良いですが、まずは「答えは〜です」と明記してください。
    """
elif mode == "⚔️ 演習モード":
    # スタイルに応じた採点指示
    style_instruction = ""
    current_style = st.session_state.get('feedback_style', "解説付き（詳細）")
    
    if current_style == "解答のみ（シンプル）":
        style_instruction = "採点時は、正誤判定（合格/不合格）と正答のみを簡潔に伝えてください。"
    else:
        style_instruction = "採点時は、正誤判定に加え、どこが良かったか、どこで間違えたかを詳しく解説してください。"

    system_instruction = base_instruction + f"""
    【役割：試験監督・コーチ】
    - 生徒の要望に合わせて問題を出題してください。
    - 問題を出した後は、生徒の回答を待ってください。
    - 生徒から数値や数式が送られてきた場合、それを**「直前の問題に対する解答」**とみなして採点してください。
    - 多少の表記ゆれ（例: x=2 と 2）は許容し、数学的に合っていれば「合格」としてください。
    - {style_instruction}
    """

# --- 5. モデルのセットアップ ---
if api_key:
    genai.configure(api_key=api_key)
    try:
        target_model_name = "gemini-2.5-flash"
        model = genai.GenerativeModel(target_model_name, system_instruction=system_instruction)
        st.sidebar.caption(f"Active Model: `{target_model_name}`")
    except Exception as e:
        st.error(f"モデル設定エラー: {e}")
        st.stop()

# --- 6. チャット表示 ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 7. AI応答ロジック ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    if not api_key: st.stop()
    
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        try:
            history = [{"role": m["role"], "parts": [str(m["content"])]} for m in st.session_state.messages if m["role"] != "system"]
            chat = model.start_chat(history=history)
            response = chat.send_message(st.session_state.messages[-1]["content"], stream=True)
            
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    response_placeholder.markdown(full_response)
            
            st.session_state.messages.append({"role": "model", "content": full_response})
            st.rerun()
        except Exception as e:
            st.error(f"エラー: {e}")

# --- 8. 入力エリア（採点精度向上のための修正） ---
if not (st.session_state.messages and st.session_state.messages[-1]["role"] == "user"):
    placeholder_text = "質問を入力..."
    if mode == "⚡ 解答確認モード":
        placeholder_text = "解答を知りたい問題を入力"
    elif mode == "⚔️ 演習モード":
        placeholder_text = "解答を入力（例：x = 2）"

    if prompt := st.chat_input(placeholder_text):
        # ★ここが重要！演習モードの時だけ、裏側で「これは解答です」と注釈をつけて保存する
        content_to_save = prompt
        
        if mode == "⚔️ 演習モード":
            # ユーザーには入力した数字だけ見えるが、AIには「解答」だと伝える
            content_to_save = f"【生徒の解答】\n{prompt}\n\n※この解答を採点してください。"
        
        # チャット履歴に追加（AIには注釈付きが渡る）
        st.session_state.messages.append({"role": "user", "content": content_to_save})
        st.rerun()
