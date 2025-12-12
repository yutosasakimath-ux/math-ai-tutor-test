import streamlit as st
import google.generativeai as genai
from PIL import Image

# --- 1. アプリの初期設定 ---
st.set_page_config(page_title="AI数学専属コーチ", page_icon="🎓", layout="centered")

# --- ビジネスモデルBの肝: 「誰が」勉強しているか ---
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

# --- 3. サイドバー（設定・診断） ---
with st.sidebar:
    st.header("⚙️ 設定")
    
    # 生徒情報の入力
    st.session_state.student_name = st.text_input("あなたのお名前", value=st.session_state.student_name)
    
    # APIキー設定
    api_key = ""
    try:
        if "GEMINI_API_KEY" in st.secrets:
            api_key = st.secrets["GEMINI_API_KEY"]
            st.success("✅ 認証済み (Secrets)")
    except:
        pass
    
    if not api_key:
        input_key = st.text_input("Gemini APIキー", type="password")
        if input_key: api_key = input_key.strip()
    
    st.markdown("---")
    
    # ★★★ 接続診断ボタン ★★★
    with st.expander("🛠️ トラブルシューティング"):
        if st.button("🔑 接続テスト・利用可能モデル確認"):
            if not api_key:
                st.error("まずはAPIキーを入力してください。")
            else:
                try:
                    genai.configure(api_key=api_key)
                    st.write("Googleへの接続を試みています...")
                    
                    # 利用可能なモデル一覧を取得
                    available_models = []
                    for m in genai.list_models():
                        if 'generateContent' in m.supported_generation_methods:
                            available_models.append(m.name)
                    
                    if available_models:
                        st.success(f"✅ 接続成功！利用可能なモデルが見つかりました ({len(available_models)}個)")
                        st.code("\n".join(available_models))
                        st.info("このリストにあるモデルを自動的に使用します。")
                    else:
                        st.warning("⚠️ 接続できましたが、チャットに使用できるモデルが見つかりませんでした。APIキーの種類（Vertex AI用など）を確認してください。")
                        
                except Exception as e:
                    st.error(f"❌ 接続失敗: {e}")
                    st.caption("APIキーが間違っているか、Google AI StudioでAPIが無効になっている可能性があります。")

    st.markdown("---")
    
    st.info(f"ようこそ、{st.session_state.student_name}さん。\n今日も一緒に頑張りましょう！")

    st.markdown("---")
    
    # 手動リセットボタン
    if st.button("🗑️ 会話をリセット", type="primary"):
        st.session_state.messages = []
        st.rerun()

# --- 4. プロンプト定義（ソクラテス式・教育特化） ---
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

# --- 6. AI応答ロジック（自己修復機能付き） ---
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

        # ★★★ 戦略的モデル優先順位 ★★★
        # あなたのアカウントで使えるモデルの中から、
        # 「賢さ」と「コスト」のバランスが良い順に並べています。
        PRIORITY_MODELS = [
            "gemini-2.5-flash",       # 第1候補: 最新・高速・高コスパ（本命）
            "gemini-2.0-flash",       # 第2候補: 安定のバックアップ
            "gemini-2.5-pro",         # 第3候補: 超高性能だがコスト高め（切り札）
            "gemini-2.0-flash-lite"   # 第4候補: 超低コスト（緊急用）
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
                # ユーザーの発言に対してレスポンス生成を試みる
                # (モデル初期化だけでなく、実際にsend_messageしてエラーが出ないか確認)
                response = try_generate(model_name)
                
                # 成功したらストリーミング開始
                for chunk in response:
                    if chunk.text:
                        full_response += chunk.text
                        response_placeholder.markdown(full_response)
                
                success = True
                active_model = model_name
                break
            except Exception:
                # このモデルがダメなら次へ
                continue
        
        # B. 優先リストが全滅した場合、サーバーから「本当に使えるリスト」を取得して再トライ（自己修復）
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
            # デバッグ用に実際に使われたモデルをログ出力（本番では消してもOK）
            print(f"Used Model: {active_model}")
            st.rerun()
        else:
            st.error("❌ エラー: AIシステムに接続できませんでした。")
            st.warning("サイドバーの「🛠️ トラブルシューティング」ボタンを押して、APIキーが正しいか確認してください。")
            with st.expander("詳細エラーログ"):
                st.write(f"Last Error: {last_error}")

# --- 7. 入力エリア ---
if not (st.session_state.messages and st.session_state.messages[-1]["role"] == "user"):
    
    current_key = st.session_state["form_key_index"]
    uploader_key = f"uploader_{current_key}"

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
