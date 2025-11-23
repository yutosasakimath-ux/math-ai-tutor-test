import streamlit as st
import google.generativeai as genai
from PIL import Image
import numpy as np # 画像変換用

# ★追加ライブラリ
from streamlit_drawable_canvas import st_canvas

# --- 1. アプリの初期設定 ---
st.set_page_config(page_title="数学AIチューター", page_icon="📐", layout="wide")

st.title("📐 高校数学 AIチューター")
st.caption("Gemini 2.5 Flash 搭載。手書き入力で直感的に質問しよう！")

# --- 2. 会話履歴の保存場所 ---
if "messages" not in st.session_state:
    st.session_state.messages = []

if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0

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

    # --- ■ 1. 学習モード ---
    if mode == "📖 学習モード":
        st.info("💡 ヒントを出しながら、あなたの理解を助けます。")
        
        st.write("### 🔄 類題演習")
        num_questions_learn = st.number_input("類題の数", 1, 5, 1, key="num_learn")
        
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

        st.write("👇 **困ったときは...**")
        col_hint, col_ans, col_exp = st.columns(3)
        
        with col_hint:
            if st.button("💡 ヒント"):
                st.session_state.messages.append({"role": "user", "content": "この問題のヒントをください。まだ答えは教えないでください。"})
                st.rerun()
        with col_ans:
            if st.button("解答のみ"):
                st.session_state.messages.append({"role": "user", "content": "直前の類題の【解答（数値・数式）のみ】を教えてください。解説は不要です。"})
                st.rerun()
        with col_exp:
            if st.button("解説を見る"):
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
        
        st.write("### 🔢 設定")
        num_q_init = st.number_input("出題する問題数", min_value=1, max_value=5, value=1, key="q_init")
        
        st.write("### 🆕 演習スタート")
        
        math_curriculum = {
            "数学I": ["数と式", "集合と命題", "二次関数", "図形と計量", "データの分析"],
            "数学A": ["場合の数と確率", "図形の性質", "整数の性質"],
            "数学II": ["式と証明", "複素数と方程式", "図形と方程式", "三角関数", "指数・対数関数", "微分・積分"],
            "数学B": ["数列", "統計的な推測"],
            "数学III": ["極限", "微分法", "積分法"],
            "数学C": ["ベクトル", "平面上の曲線と複素数平面"],
            "手動入力": [] 
        }
        
        selected_subject = st.selectbox("科目を選択", list(math_curriculum.keys()))
        topic_for_prompt = ""
        
        if selected_subject == "手動入力":
            topic_for_prompt = st.text_input("単元名を入力（例：合同式）")
        else:
            selected_topic = st.selectbox("単元を選択", math_curriculum[selected_subject])
            topic_for_prompt = f"{selected_subject}の{selected_topic}"

        if st.button("問題を作成開始"):
            if not topic_for_prompt:
                st.error("単元を選択してください。")
            else:
                prompt_text = f"【{topic_for_prompt}】に関する練習問題を【{num_q_init}問】出題してください。問1, 問2...と番号を振ってください。まだ答えは言わないでください。"
                st.session_state.messages.append({"role": "user", "content": prompt_text})
                st.rerun()
        
        st.markdown("---")
        
        st.write("### ⏩ 次の問題へ")
        num_q_next = st.number_input("次に出す問題数", 1, 5, 1, key="q_next")
        
        st.caption("難易度を選んで次のセットへ")
        col_easy, col_same, col_hard = st.columns(3)
        
        with col_easy:
            if st.button("↘️ 易しく", key="exam_easy"):
                prompt_text = f"""
                【教師へのリクエスト】
                先ほどの問題よりも**難易度を下げて（基礎的な内容にして）**、新しい類題を【{num_q_next}問】作成してください。
                数値を変え、基本的な理解を確認できるようにしてください。
                まだ答えは言わないでください。
                """
                st.session_state.messages.append({"role": "user", "content": prompt_text})
                st.rerun()

        with col_same:
            if st.button("➡️ 維持", key="exam_same"):
                prompt_text = f"""
                【教師へのリクエスト】
                先ほどの問題と**同じ難易度・同じ解法パターン**の新しい類題を【{num_q_next}問】作成してください。
                数値を変えて、反復練習できるようにしてください。
                まだ答えは言わないでください。
                """
                st.session_state.messages.append({"role": "user", "content": prompt_text})
                st.rerun()

        with col_hard:
            if st.button("↗️ 難しく", key="exam_hard"):
                prompt_text = f"""
                【教師へのリクエスト】
                先ほどの問題よりも**難易度を上げて（応用的な内容にして）**、新しい類題を【{num_q_next}問】作成してください。
                計算を複雑にするか、他の単元との融合問題にするなどして、応用力を試してください。
                まだ答えは言わないでください。
                """
                st.session_state.messages.append({"role": "user", "content": prompt_text})
                st.rerun()

        st.markdown("---")
        st.write("👇 **ヘルプ**")
        
        if st.button("💡 ヒントをもらう"):
             st.session_state.messages.append({"role": "user", "content": "分かりません。ヒントをください（答えは言わないで）。"})
             st.rerun()

        if st.button("🏳️ ギブアップ（解答を見る）"):
            st.session_state.messages.append({"role": "user", "content": "降参です。正解と解説を教えてください。"})
            st.rerun()

    st.markdown("---")
    
    # 共通：手動リセットボタン
    if st.button("🗑️ 会話をリセット", type="primary"):
        st.session_state.messages = []
        st.rerun()

# --- 4. モードごとのプロンプト定義 ---

base_instruction = """
あなたは日本の高校数学教師です。数式は必ずLaTeX形式（$マーク）で書いてください。
画像（手書きの数式や図形含む）が送られた場合、それを読み取り、数学的に解釈して応答してください。
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
    - 画像が送られた場合は、その問題の解答を作成してください。
    """
elif mode == "⚔️ 演習モード":
    system_instruction = base_instruction + """
    【役割：試験監督・コーチ】
    - 生徒から数値や数式が送られてきた場合、それを「直前の問題（複数ある場合はそれぞれ）に対する解答」とみなして採点してください。
    
    【採点のルール】
    1. **正解の場合**: 
       - 「正解です！」と褒めて、詳しい解説を行ってください。
       - 解説が終わったら、そこで出力を終了してください（勝手に次の問題を出さない）。
    2. **不正解の場合**: 
       - 答えは教えず、ヒントを出して再挑戦させてください。
       - 複数問ある場合は、問ごとに合否を判定してください。
    3. **ヒント要求の場合**: 
       - 答えは教えず、考え方のヒントだけを出してください。
    4. **ギブアップの場合**: 
       - 正解と解説を提示して終了してください。
    5. **次の問題（難易度調整）の場合**:
       - 生徒の指示（易しく/維持/難しく）に従って、難易度を調整した新しい類題を、指定された数だけ出題してください。
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
            
            current_msg = st.session_state.messages[-1]["content"]
            content_to_send = []
            
            if isinstance(current_msg, dict):
                if "text" in current_msg: content_to_send.append(current_msg["text"])
                if "image" in current_msg: content_to_send.append(current_msg["image"])
            else:
                content_to_send.append(current_msg)

            response = chat.send_message(content_to_send, stream=True)
            
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    response_placeholder.markdown(full_response)
            
            st.session_state.messages.append({"role": "model", "content": full_response})
            st.rerun()
        except Exception as e:
            st.error(f"エラー: {e}")

# --- 8. 入力エリア（手書き・画像・テキスト） ---
if not (st.session_state.messages and st.session_state.messages[-1]["role"] == "user"):
    
    uploader_key = f"file_uploader_{st.session_state['uploader_key']}"

    # カラム分けで「画像アップロード」と「手書き」を並べる
    col_upload, col_canvas = st.columns(2)
    
    # 1. 画像アップロード
    with col_upload:
        with st.expander("📸 画像をアップロード", expanded=False):
            uploaded_file = st.file_uploader("問題の写真をアップロード", type=["jpg", "png", "jpeg"], key=uploader_key)

    # 2. 手書き入力 (Canvas)
    canvas_result = None
    with col_canvas:
        with st.expander("📝 手書き入力ボード", expanded=False):
            # st_canvasで手書きエリアを作成
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=3,
                stroke_color="#000000",
                background_color="#ffffff",
                height=200,
                width=300,
                drawing_mode="freedraw",
                key="canvas",
            )
            # 手書き送信ボタン
            send_canvas = st.button("手書きを送信")

    # 3. テキスト入力
    placeholder_text = "質問を入力..."
    if mode == "⚡ 解答確認モード":
        placeholder_text = "解答を知りたい問題を入力（または画像を送信）"
    elif mode == "⚔️ 演習モード":
        placeholder_text = "解答を入力（例：(1) 5, (2) 10 ...）"

    chat_input = st.chat_input(placeholder_text)

    # --- 送信処理 ---
    content_to_save = {}
    should_submit = False

    # A. チャット入力で送信された場合
    if chat_input:
        text_part = chat_input
        if mode == "⚔️ 演習モード":
            text_part = f"【生徒の解答】\n{chat_input}\n\n※採点してください。正解なら解説のみを行ってください。"
        
        content_to_save["text"] = text_part
        
        # 画像もあれば追加
        if uploaded_file:
            image_data = Image.open(uploaded_file)
            content_to_save["image"] = image_data
        
        should_submit = True

    # B. 手書きボタンで送信された場合
    elif send_canvas and canvas_result is not None and canvas_result.image_data is not None:
        # キャンバスのデータをPIL画像に変換
        img_data = canvas_result.image_data.astype('uint8')
        # RGBAからRGBへ（背景が透明だと黒くなるので、白背景と合成するのがベストだが、簡易的に変換）
        # 数学AI用途ならRGBAのままでもGeminiは読めることが多いが、念のためRGB変換
        pil_image = Image.fromarray(img_data, "RGBA")
        
        # 背景を白にする処理（透明部分を白に）
        background = Image.new("RGB", pil_image.size, (255, 255, 255))
        background.paste(pil_image, mask=pil_image.split()[3]) # alpha channel as mask
        
        content_to_save["image"] = background
        content_to_save["text"] = "この手書きの数式・図形を読み取ってください。"
        
        if mode == "⚔️ 演習モード":
            content_to_save["text"] = "【生徒の手書き解答】\nこの画像を解答として採点してください。"

        should_submit = True

    # 送信実行
    if should_submit:
        if "image" in content_to_save:
            st.session_state.messages.append({"role": "user", "content": content_to_save})
        else:
            st.session_state.messages.append({"role": "user", "content": content_to_save["text"]})
        
        # アップローダーのリセット
        st.session_state["uploader_key"] += 1
        st.rerun()
