import streamlit as st
import google.generativeai as genai

# --- 1. アプリの初期設定 ---
st.set_page_config(page_title="数学AIチューター", page_icon="📐", layout="wide")

st.title("📐 高校数学 AIチューター")
st.caption("Gemini 2.5 Flash 搭載。難易度を自在に操ろう！")

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

    # --- ■ 1. 学習モード（ここを修正しました！） ---
    if mode == "📖 学習モード":
        st.info("💡 ヒントを出しながら、あなたの理解を助けます。")
        
        st.write("### 🔄 類題演習")
        num_questions_learn = st.number_input("類題の数", 1, 5, 1, key="num_learn")
        
        # ★難易度調整ボタンを追加
        st.caption("難易度を選んで出題")
        l_col1, l_col2, l_col3 = st.columns(3)
        
        with l_col1:
            if st.button("↘️ 易しく", key="learn_easy"):
                prompt_text = f"""
                【教師へのリクエスト】
                直前の内容よりも**難易度を下げて（基礎的な内容にして）**、新しい類題を【{num_questions_learn}問】作成してください。
                まだ答えや解説は一切書かず、**問題文のみ**を提示してください。
                """
                st.session_state.messages.append({"role": "user", "content": prompt_text})
                st.rerun()
        
        with l_col2:
            if st.button("➡️ 維持", key="learn_same"):
                prompt_text = f"""
                【教師へのリクエスト】
                直前の内容と**同じ難易度**の新しい類題を【{num_questions_learn}問】作成してください。
                まだ答えや解説は一切書かず、**問題文のみ**を提示してください。
                """
                st.session_state.messages.append({"role": "user", "content": prompt_text})
                st.rerun()

        with l_col3:
            if st.button("↗️ 難しく", key="learn_hard"):
                prompt_text = f"""
                【教師へのリクエスト】
                直前の内容よりも**難易度を上げて（応用的な内容にして）**、新しい類題を【{num_questions_learn}問】作成してください。
                まだ答えや解説は一切書かず、**問題文のみ**を提示してください。
                """
                st.session_state.messages.append({"role": "user", "content": prompt_text})
                st.rerun()

        st.write("👇 **答え合わせ**")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("解答のみ確認"):
                st.session_state.messages.append({"role": "user", "content": "直前の類題の【解答（数値・数式）のみ】を教えてください。"})
                st.rerun()
        with col2:
            if st.button("解説を含めて確認"):
                st.session_state.messages.append({"role": "user", "content": "直前の類題の【詳しい解説と解答】を教えてください。"})
                st.rerun()

        st.markdown("---")
        if st.button("今日の学びを整理"):
            st.session_state.messages.append({"role": "user", "content": "ここまでの学習内容の要点をまとめてください。"})
            st.rerun()

    # --- ■ 2. 解答確認モード ---
    elif mode == "⚡ 解答確認モード":
        st.warning("📸 解答が知りたい問題を入力（または画像をアップ）してください。即座に答えを提示します。")
    
    # --- ■ 3. 演習モード ---
    elif mode == "⚔️ 演習モード":
        st.success("📝 問題を出題し、採点します。")
        
        st.write("### 🆕 演習スタート")
        topic = st.text_input("演習したい単元（例：二次関数）")
        
        if st.button("問題を作成開始"):
            prompt_text = f"【{topic}】に関する練習問題を**1問**出題してください。まだ答えは言わないでください。"
            st.session_state.messages.append({"role": "user", "content": prompt_text})
            st.rerun()
        
        st.markdown("---")
        
        # 難易度調整ボタン
        st.write("### ⏩ 次の問題へ")
        
        col_easy, col_same, col_hard = st.columns(3)
        
        with col_easy:
            if st.button("↘️ 易しく", key="exam_easy"):
                prompt_text = """
                【教師へのリクエスト】
                先ほどの問題よりも**難易度を下げて（基礎的な内容にして）**、新しい類題を1問作成してください。
                数値を変え、基本的な理解を確認できるようにしてください。
                まだ答えは言わないでください。
                """
                st.session_state.messages.append({"role": "user", "content": prompt_text})
                st.rerun()

        with col_same:
            if st.button("➡️ 維持", key="exam_same"):
                prompt_text = """
                【教師へのリクエスト】
                先ほどの問題と**同じ難易度・同じ解法パターン**の新しい類題を1問作成してください。
                数値を変えて、反復練習できるようにしてください。
                まだ答えは言わないでください。
                """
                st.session_state.messages.append({"role": "user", "content": prompt_text})
                st.rerun()

        with col_hard:
            if st.button("↗️ 難しく", key="exam_hard"):
                prompt_text = """
                【教師へのリクエスト】
                先ほどの問題よりも**難易度を上げて（応用的な内容にして）**、新しい類題を1問作成してください。
                計算を複雑にするか、他の単元との融合問題にするなどして、応用力を試してください。
                まだ答えは言わないでください。
                """
                st.session_state.messages.append({"role": "user", "content": prompt_text})
                st.rerun()

        # ギブアップ
        if st.button("🏳️ ギブアップ（解答を見る）"):
            st.session_state.messages.append({"role": "user", "content": "降参です。正解と解説を教えてください。"})
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
    - 絶対にすぐに答えを教えないでください（「解答のみ確認」と指示された場合を除く）。
    - 生徒が自力で気づけるよう、問いかけやヒントで導いてください。
    """
elif mode == "⚡ 解答確認モード":
    system_instruction = base_instruction + """
    【役割：解答チェッカー】
    - 結論（答え）を最優先で提示してください。
    """
elif mode == "⚔️ 演習モード":
    system_instruction = base_instruction + """
    【役割：試験監督・コーチ】
    - 生徒から数値や数式が送られてきた場合、それを「直前の問題に対する解答」とみなして採点してください。
    
    【採点のルール】
    1. **正解の場合**: 
       - 「正解です！」と褒めて、詳しい解説を行ってください。
       - 解説が終わったら、そこで出力を終了してください（勝手に次の問題を出さない）。
    2. **不正解の場合**: 
       - 答えは教えず、ヒントを出して再挑戦させてください。
    3. **ギブアップの場合**: 
       - 正解と解説を提示して終了してください。
    4. **次の問題（難易度調整）の場合**:
       - 生徒の指示（易しく/維持/難しく）に従って、難易度を調整した新しい類題を1問出題してください。
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

# --- 8. 入力エリア ---
if not (st.session_state.messages and st.session_state.messages[-1]["role"] == "user"):
    placeholder_text = "質問を入力..."
    if mode == "⚡ 解答確認モード":
        placeholder_text = "解答を知りたい問題を入力"
    elif mode == "⚔️ 演習モード":
        placeholder_text = "解答を入力（例：x = 2）"

    if prompt := st.chat_input(placeholder_text):
        content_to_save = prompt
        if mode == "⚔️ 演習モード":
            content_to_save = f"【生徒の解答】\n{prompt}\n\n※採点してください。正解なら解説のみを行ってください（次の問題は出さないでください）。"
        
        st.session_state.messages.append({"role": "user", "content": content_to_save})
        st.rerun()
