import streamlit as st
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import json
import datetime
import time
from PIL import Image

# --- 0. 設定と定数 ---
st.set_page_config(page_title="AI数学専属コーチ", page_icon="🎓", layout="centered", initial_sidebar_state="expanded")

# ★★★ UI設定：スマホ対応・入力フォームの最適化・カメラアイコン化 ★★★
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.stDeployButton {display:none;}

/* チャット用フォーム（メインエリアにあるフォームのみ）を下部に固定 */
.main [data-testid="stForm"] {
    border: 1px solid #ddd;
    border-radius: 10px;
    padding: 10px;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background-color: white;
    z-index: 999;
    margin: 0 auto;
    max-width: 700px; /* layout="centered"に合わせる */
    box-shadow: 0px -2px 10px rgba(0,0,0,0.1);
}

/* メインコンテンツがフォームに隠れないように余白を開ける */
.main .block-container {
    padding-bottom: 150px; 
}

/* --- 画像アップローダーをカメラアイコンにするCSSハック --- */
[data-testid="stFileUploader"] {
    width: 44px; /* アイコンの幅 */
    margin-top: -2px;
    padding-top: 0;
}
[data-testid="stFileUploader"] section {
    padding: 0;
    min-height: 44px;
    background-color: #f0f2f6;
    border: 1px solid #ccc;
    border-radius: 8px; /* 角丸 */
    display: flex;
    align-items: center;
    justify-content: center;
    /* 文字を透明にして「Browse files」等を完全に見えなくする */
    color: transparent; 
}

/* 内部のすべての要素（テキストやボタン）を強制的に消す */
[data-testid="stFileUploader"] section > * {
    display: none !important;
}

/* カメラアイコンを表示（透明にした文字色をここで黒に戻す） */
[data-testid="stFileUploader"] section::after {
    content: "📷"; 
    font-size: 22px;
    color: black; /* アイコンの色 */
    display: block;
    cursor: pointer;
}
/* アップロード済みファイル情報のリストを消す（スッキリさせるため） */
[data-testid="stFileUploader"] ul {
    display: none;
}
/* アップロードされた時の状態変化 */
[data-testid="stFileUploader"]:has(input[type="file"]:valid) section {
    background-color: #e0f7fa;
    border-color: #00bcd4;
}

/* テキストエリアの調整 */
.stTextArea textarea {
    font-size: 16px;
    padding: 10px;
}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ★管理者用パスワード
if "ADMIN_KEY" in st.secrets:
    ADMIN_KEY = st.secrets["ADMIN_KEY"]
else:
    ADMIN_KEY = None

if "FIREBASE_WEB_API_KEY" in st.secrets:
    FIREBASE_WEB_API_KEY = st.secrets["FIREBASE_WEB_API_KEY"]
else:
    FIREBASE_WEB_API_KEY = "ここにウェブAPIキーを貼り付ける" 

# --- 1. Firebase初期化 ---
if not firebase_admin._apps:
    try:
        if "firebase" in st.secrets:
            key_dict = dict(st.secrets["firebase"])
            if "\\n" in key_dict["private_key"]:
                key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(key_dict)
            firebase_admin.initialize_app(cred)
        else:
            cred = credentials.Certificate("service_account.json")
            firebase_admin.initialize_app(cred)
    except Exception as e:
        st.error(f"Firebase接続エラー: {e}")
        st.stop()

db = firestore.client()

# --- 2. 認証機能ヘルパー関数 ---
def sign_in_with_email(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(url, json=payload)
    return r.json()

def sign_up_with_email(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_WEB_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(url, json=payload)
    return r.json()

# --- 3. セッション管理 ---
if "user_info" not in st.session_state:
    st.session_state.user_info = None
if "last_used_model" not in st.session_state:
    st.session_state.last_used_model = "まだ回答していません"
if "last_report" not in st.session_state:
    st.session_state.last_report = ""

# Firestore読み込みコスト削減のためのキャッシュ
if "messages" not in st.session_state:
    st.session_state.messages = []
if "messages_loaded" not in st.session_state:
    st.session_state.messages_loaded = False

# --- 4. UI: ログイン画面（未ログイン時） ---
if st.session_state.user_info is None:
    st.title("🎓 AI数学コーチ：ログイン")
    
    if "FIREBASE_WEB_API_KEY" not in st.secrets and FIREBASE_WEB_API_KEY == "ここにウェブAPIキーを貼り付ける":
        st.warning("⚠️ Web APIキーが設定されていません。Streamlit Secretsを設定してください。")
    
    with st.form("login_form"):
        email = st.text_input("メールアドレス")
        password = st.text_input("パスワード", type="password")
        submit = st.form_submit_button("ログイン")
        
        if submit:
            resp = sign_in_with_email(email, password)
            if "error" in resp:
                st.error(f"ログイン失敗: {resp['error']['message']}")
            else:
                st.session_state.user_info = {"uid": resp["localId"], "email": resp["email"]}
                st.success("ログインしました！")
                st.rerun()

    st.markdown("---")
    
    with st.expander("管理者用：新規アカウント作成"):
        admin_pass_input = st.text_input("管理者パスワード", type="password", key="admin_reg_pass")
        if ADMIN_KEY and admin_pass_input == ADMIN_KEY:
            st.info("🔓 管理者モード：新規モニターユーザーを作成します")
            with st.form("admin_signup_form"):
                new_email = st.text_input("新規メールアドレス")
                new_password = st.text_input("新規パスワード")
                submit_new = st.form_submit_button("アカウントを作成する")
                
                if submit_new:
                    resp = sign_up_with_email(new_email, new_password)
                    if "error" in resp:
                        st.error(f"作成失敗: {resp['error']['message']}")
                    else:
                        st.success(f"アカウント作成成功！\nEmail: {new_email}\nPass: {new_password}\n\nこの情報を親御さんに送ってください。")
        elif admin_pass_input:
            st.error("パスワードが違います")
            
    st.stop()

# =========================================================
# ログイン済みユーザーの世界
# =========================================================

user_id = st.session_state.user_info["uid"]
user_email = st.session_state.user_info["email"]

# --- 5. Firestoreからユーザーデータ取得 ---
user_ref = db.collection("users").document(user_id)
if "user_name" not in st.session_state:
    user_doc = user_ref.get()
    if not user_doc.exists:
        user_data = {"email": user_email, "created_at": firestore.SERVER_TIMESTAMP} 
        user_ref.set(user_data)
        st.session_state.user_name = "ゲスト"
    else:
        user_data = user_doc.to_dict()
        st.session_state.user_name = user_data.get("name", "ゲスト")

student_name = st.session_state.user_name

api_key = ""
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
if not api_key:
    pass

# --- 6. サイドバー ---
with st.sidebar:
    st.header(f"ようこそ")
    new_name = st.text_input("お名前", value=student_name)
    if new_name != student_name:
        user_ref.update({"name": new_name})
        st.session_state.user_name = new_name
        st.rerun()
    
    st.markdown("---")

    if st.button("🗑️ 会話履歴を全削除"):
        with st.spinner("履歴を削除中..."):
            batch = db.batch()
            all_history = user_ref.collection("history").stream()
            count = 0
            for doc in all_history:
                batch.delete(doc.reference)
                count += 1
                if count >= 400:
                    batch.commit()
                    batch = db.batch()
                    count = 0
            if count > 0:
                batch.commit()
        st.session_state.last_report = "" 
        st.session_state.messages = [] 
        st.session_state.messages_loaded = True 
        st.success("履歴をリセットしました")
        time.sleep(1)
        st.rerun()

    if st.button("ログアウト"):
        st.session_state.user_info = None
        st.session_state.messages = []
        st.session_state.messages_loaded = False
        st.rerun()

    st.markdown("---")

    st.caption("📢 ご意見・不具合報告")
    with st.form("feedback_form", clear_on_submit=True):
        feedback_content = st.text_area("感想、バグ、要望など", placeholder="例：〇〇の計算でエラーが出ました")
        feedback_submit = st.form_submit_button("送信")
        if feedback_submit and feedback_content:
            db.collection("feedback").add({
                "user_id": user_id,
                "email": user_email,
                "content": feedback_content,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            st.success("送信しました。")

    st.markdown("---")
    st.success("👑 モニター会員 (Pro機能有効)")
    st.caption("現在、テスト期間につき全機能を開放しています。")

    st.markdown("---")

    # 管理者用：保護者レポート作成（修正版）
    with st.expander("管理者用：保護者レポート作成"):
        report_admin_pass = st.text_input("管理者パスワード", type="password", key="report_admin_pass")
        
        if ADMIN_KEY and report_admin_pass == ADMIN_KEY:
            st.info("🔓 レポート作成モード")
            
            if st.button("📝 今日のレポートを作成"):
                if not st.session_state.messages:
                    st.warning("まだ学習履歴がありません。")
                elif not api_key:
                    st.error("Gemini APIキーを設定してください。")
                else:
                    with st.spinner("会話ログを分析中..."):
                        try:
                            report_system_instruction = f"""
                            あなたは学習塾の「保護者への報告担当者」です。
                            以下の「生徒とAI講師の会話ログ」をもとに、保護者に送るための学習レポートを作成してください。
                            生徒名は「{new_name}」さんです。
                            
                            【絶対遵守する出力フォーマット】
                            --------------------------------------------------
                            【📅 本日の学習レポート】
                            生徒名：{new_name}

                            ■ 学習トピック
                            （ここに単元名やテーマを簡潔に書く）

                            ■ 理解度スコア
                            （1〜5の数字）/ 5
                            （評価理由を1行で簡潔に）

                            ■ 先生からのコメント
                            （学習の様子、つまずいた点、克服した点などを「です・ます」調で3行程度）

                            ■ 保護者様へのアドバイス（今日のお声がけ）
                            （家庭でどのような言葉をかければよいか、具体的なセリフ案を「」で1つ提示）
                            --------------------------------------------------
                            """
                            
                            conversation_text = ""
                            for m in st.session_state.messages[-20:]: 
                                role_name = "先生" if m["role"] == "model" else "生徒"
                                raw_content = m["content"]
                                content_text = ""
                                if isinstance(raw_content, str):
                                    content_text = raw_content
                                elif isinstance(raw_content, dict):
                                    content_text = raw_content.get("text", str(raw_content))
                                else:
                                    content_text = str(raw_content)
                                conversation_text += f"{role_name}: {content_text}\n"

                            genai.configure(api_key=api_key)
                            REPORT_MODELS = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash-exp", "gemini-2.5-flash"]
                            report_text = ""
                            success_report = False
                            error_log = []
                            
                            for model_name in REPORT_MODELS:
                                try:
                                    report_model = genai.GenerativeModel(model_name, system_instruction=report_system_instruction)
                                    response = report_model.generate_content(f"【会話ログ】\n{conversation_text}")
                                    if response.text:
                                        report_text = response.text
                                        success_report = True
                                        break
                                except Exception as e:
                                    error_log.append(f"{model_name}: {str(e)}")
                                    continue
                            
                            if success_report and report_text:
                                st.session_state.last_report = report_text
                                st.success("レポートを作成しました！")
                            else:
                                st.error("レポート生成に失敗しました。")
                                with st.expander("エラー詳細"):
                                    st.write(error_log)

                        except Exception as e:
                            st.error(f"予期せぬエラー: {e}")

            if st.session_state.last_report:
                st.text_area("コピーしてLINEで送れます", st.session_state.last_report, height=300)
        
        elif report_admin_pass:
            st.error("パスワードが違います")

    st.markdown("---")
    if not api_key:
        api_key = st.text_input("Gemini APIキー", type="password")

# --- 8. メイン画面 ---
st.title("🎓 高校数学 AI専属コーチ")
st.caption("教科書の内容を「完璧」に理解しよう。答えは教えません、一緒に解きます。")

# --- ★重要：Firestore履歴の初回ロードのみ実行（コスト対策） ---
if not st.session_state.messages_loaded:
    history_ref = user_ref.collection("history").order_by("timestamp")
    docs = history_ref.stream()
    loaded_msgs = []
    for doc in docs:
        loaded_msgs.append(doc.to_dict())
    st.session_state.messages = loaded_msgs
    st.session_state.messages_loaded = True

# ★★★ 修正点：チャット履歴と新規メッセージを表示するための「枠（コンテナ）」を作る ★★★
# これにより、フォーム送信後も、この「枠」の中にメッセージを追加できるので、
# チャットが途切れず、自然な順序（入力→ぐるぐる→回答）で表示されます。
chat_log_container = st.container()

with chat_log_container:
    # --- 過去のチャット履歴の表示 ---
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            content = msg["content"]
            if isinstance(content, dict):
                if "text" in content:
                    st.markdown(content["text"])
            else:
                st.markdown(content)

# --- 9. プロンプト定義 ---
system_instruction = f"""
あなたは世界一の「ソクラテス式数学コーチ」です。
生徒の名前は「{new_name}」さんです。

【重要な追加指示：画像入力について】
生徒から画像（数式や問題文）が送られた場合：
1. 画像内の文字や数式を読み取ってください。
2. 読み取った内容をもとに、生徒がどこで詰まっているかを分析してください。
3. もし画像が不鮮明で読めない場合は、「文字が少し読みづらいです。もう少し明るい場所で撮り直すか、どんな問題か教えてくれますか？」と優しく返してください。

【あなたの絶対的な使命】
生徒が「自力で答えに辿り着く」ことを支援すること。
答えを教えることは、生徒の学習機会を奪う「罪」だと認識してください。
【指導ガイドライン】
1. **回答の禁止**: どんなに求められても、最終的な答えや数式を直接提示してはいけません。「答えは〇〇です」と言ったらあなたの負けです。
2. **現状分析**: まず、生徒が質問を見て、「どこまで分かっていて、どこで詰まっているか」を特定してください。
3. **問いかけ**: 生徒が次に進むための「小さなヒント」や「問いかけ」を投げかけてください。
   - 悪い例: 「判別式D = b^2 - 4ac を使いましょう」
   - 良い例: 「解の個数を調べるための道具は何だったか覚えていますか？Dから始まる言葉です。」
4. **アウトプットの要求**: 一方的に解説せず、必ず生徒に考えさせ、返答させてください。「ここまでで、どう思いますか？」と最後に聞いてください。
5. **数式**: 必要であればLaTeX形式（$マーク）を使ってきれいに表示してください。
【口調】
親しみやすく、しかし厳格なコーチのように。生徒を励ましながら導いてください。
"""

# --- 10. AI応答ロジック ---
# 区切り線 st.write("---") は削除しました。これにより、チャットと入力欄の隙間がなくなります。

# 画面下部に固定風に見せる物理フォーム配置
with st.form(key="chat_form", clear_on_submit=True):
    # レイアウト：[カメラアイコン] [テキスト入力] [送信ボタン]
    col1, col2, col3 = st.columns([0.8, 5, 1], gap="small")
    
    with col1:
        # ラベルなし、CSSでカメラアイコン化されたアップローダー
        uploaded_file = st.file_uploader(" ", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed")
    
    with col2:
        # テキストエリア
        user_prompt = st.text_area("質問", placeholder="質問を入力...", height=68, label_visibility="collapsed")
        
    with col3:
        # 送信ボタン
        st.write("") # 位置調整
        submitted = st.form_submit_button("送信")

    # --- 送信処理 ---
    if submitted:
        if not user_prompt and not uploaded_file:
            st.warning("質問か画像を入力してください")
        elif not api_key:
            st.warning("サイドバーでGemini APIキーを設定してください。")
        else:
            # 画像処理
            upload_img_obj = None
            user_msg_content = user_prompt
            
            if uploaded_file:
                try:
                    upload_img_obj = Image.open(uploaded_file)
                    # 画像がある場合、テキストに注釈を追加
                    user_msg_content += "\n\n(※画像を送信しました)"
                except Exception as e:
                    st.error("画像エラー")

            # ユーザーメッセージをセッションに追加
            st.session_state.messages.append({
                "role": "user",
                "content": user_msg_content
            })
            
            # Firestoreへ保存
            user_ref.collection("history").add({
                "role": "user",
                "content": user_msg_content,
                "timestamp": firestore.SERVER_TIMESTAMP
            })

            # ★★★ 修正点：先ほど作った「チャットの枠（chat_log_container）」の中に表示を入れる ★★★
            with chat_log_container:
                # 1. あなたの入力（赤枠～）を即座に表示
                with st.chat_message("user"):
                    st.markdown(user_msg_content)
                    if upload_img_obj:
                        st.image(upload_img_obj, width=200)

                # 2. そのすぐ下で「ぐるぐる（思考中）」を回す
                # これで、あなたの入力のすぐ下でAIが考えているように見えます
                with st.spinner("AIコーチが思考中..."):
                    genai.configure(api_key=api_key)
                    history_for_ai = []
                    for m in st.session_state.messages[:-1]:
                        content_str = ""
                        if isinstance(m["content"], dict):
                            content_str = m["content"].get("text", str(m["content"]))
                        else:
                            content_str = str(m["content"])
                        history_for_ai.append({"role": m["role"], "parts": [content_str]})

                    # ★★★ 修正点：3.0系モデルを最優先で復活させました ★★★
                    PRIORITY_MODELS = [
                        "gemini-3.0-flash-preview", # 復活
                        "gemini-2.5-flash", 
                        "gemini-2.0-flash-exp",   
                        "gemini-1.5-pro",
                        "gemini-1.5-flash"
                    ]
                    
                    ai_text = ""
                    success_model = None
                    error_log = []

                    for model_name in PRIORITY_MODELS:
                        try:
                            model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
                            chat = model.start_chat(history=history_for_ai)
                            
                            inputs = [user_prompt]
                            if upload_img_obj:
                                inputs.append(upload_img_obj)
                            
                            response = chat.send_message(inputs)
                            ai_text = response.text
                            success_model = model_name
                            break 
                        except Exception as e:
                            error_log.append(f"{model_name}: {str(e)}")
                            continue
                
                # 3. AIの処理が終わったら、その「ぐるぐる」が消えて、同じ場所に「解答」が出る
                if success_model:
                    st.session_state.last_used_model = success_model
                    
                    # 結果の保存
                    st.session_state.messages.append({
                        "role": "model",
                        "content": ai_text
                    })
                    
                    user_ref.collection("history").add({
                        "role": "model",
                        "content": ai_text,
                        "timestamp": firestore.SERVER_TIMESTAMP
                    })
                    
                    # AIの回答を表示（ここも chat_log_container の中）
                    with st.chat_message("model"):
                        st.markdown(ai_text)
                    
                    # 少し待ってからリロードして、正式に履歴として保存・表示
                    # これにより、一瞬表示されて消える現象を防ぎます
                    time.sleep(0.1) 
                    st.rerun()
                else:
                    st.error(f"❌ エラーが発生しました。\n詳細: {error_log}")
