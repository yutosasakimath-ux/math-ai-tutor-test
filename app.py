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

# ★★★ UI設定：スマホ対応・入力フォームの最適化（修正版） ★★★
# 修正点：.main [data-testid="stForm"] とすることで、サイドバーのフォームへの影響を除外
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
    position: fixed; /* 簡易的な下部固定 */
    bottom: 0;
    left: 0;
    right: 0;
    background-color: white;
    z-index: 999;
    margin: 0 auto;
    max-width: 700px; /* layout="centered"に合わせる */
}

/* メインコンテンツがフォームに隠れないように余白を開ける */
.main .block-container {
    padding-bottom: 150px; 
}

/* 画像アップローダーをコンパクトにする */
[data-testid="stFileUploader"] {
    padding-top: 0px;
}
[data-testid="stFileUploader"] section {
    padding: 0px;
    min-height: 0px;
}
[data-testid="stFileUploader"] img {
    display: none; /* デフォルトのアイコンを消すなど */
}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- 1. Firebase初期化 ---
if "ADMIN_KEY" in st.secrets:
    ADMIN_KEY = st.secrets["ADMIN_KEY"]
else:
    ADMIN_KEY = None

if "FIREBASE_WEB_API_KEY" in st.secrets:
    FIREBASE_WEB_API_KEY = st.secrets["FIREBASE_WEB_API_KEY"]
else:
    FIREBASE_WEB_API_KEY = "API_KEY_NOT_SET"

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

# ★重要修正：Firestore読み込みコスト削減のためのキャッシュ★
if "messages" not in st.session_state:
    st.session_state.messages = []
if "messages_loaded" not in st.session_state:
    st.session_state.messages_loaded = False

# --- 4. UI: ログイン画面（未ログイン時） ---
if st.session_state.user_info is None:
    st.title("🎓 AI数学コーチ：ログイン")
    
    if "FIREBASE_WEB_API_KEY" not in st.secrets and FIREBASE_WEB_API_KEY == "API_KEY_NOT_SET":
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
                        st.success(f"アカウント作成成功！\nEmail: {new_email}\nPass: {new_password}")
        elif admin_pass_input:
            st.error("パスワードが違います")
            
    st.stop()

# =========================================================
# ログイン済みユーザーの世界
# =========================================================

user_id = st.session_state.user_info["uid"]
user_email = st.session_state.user_info["email"]

# --- 5. Firestoreからユーザーデータ取得（基本情報） ---
user_ref = db.collection("users").document(user_id)
# ユーザー名の取得もキャッシュする（Read削減）
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
        st.session_state.messages = [] # キャッシュもクリア
        st.session_state.messages_loaded = True # ロード済み状態にする（空なので）
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
        feedback_content = st.text_area("感想、バグなど", placeholder="例：画像の読み込みが遅いです")
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
    
    # 管理者用レポート機能
    with st.expander("管理者用：レポート作成"):
        report_admin_pass = st.text_input("管理者パスワード", type="password", key="report_admin_pass")
        if ADMIN_KEY and report_admin_pass == ADMIN_KEY:
            st.info("🔓 レポート作成モード")
            
            if st.button("📝 今日のレポートを作成"):
                if not st.session_state.messages:
                    st.warning("学習履歴がありません。")
                elif not api_key:
                    st.error("APIキー設定エラー")
                else:
                    with st.spinner("会話ログを分析中..."):
                        try:
                            report_system_instruction = f"""
                            あなたは学習塾の「保護者への報告担当者」です。
                            生徒名は「{new_name}」さんです。
                            【絶対遵守する出力フォーマット】
                            --------------------------------------------------
                            【📅 本日の学習レポート】
                            生徒名：{new_name}
                            ■ 学習トピック
                            （単元名やテーマ）
                            ■ 理解度スコア
                            （1〜5）/ 5
                            （評価理由1行）
                            ■ 先生からのコメント
                            （3行程度）
                            ■ 保護者様へのアドバイス
                            （具体的なセリフ案を1つ）
                            --------------------------------------------------
                            """
                            
                            conversation_text = ""
                            # セッションステートから履歴を取得（最新20件）
                            for m in st.session_state.messages[-20:]: 
                                role_name = "先生" if m["role"] == "model" else "生徒"
                                content_text = m["content"].get("text", "") if isinstance(m["content"], dict) else str(m["content"])
                                conversation_text += f"{role_name}: {content_text}\n"

                            genai.configure(api_key=api_key)
                            report_model_name = "gemini-1.5-flash" 
                            report_model = genai.GenerativeModel(report_model_name, system_instruction=report_system_instruction)
                            response = report_model.generate_content(f"【会話ログ】\n{conversation_text}")
                            
                            st.session_state.last_report = response.text
                            st.success("作成完了！")
                        except Exception as e:
                            st.error(f"エラー: {e}")

            if st.session_state.last_report:
                st.text_area("コピー用", st.session_state.last_report, height=300)

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

# --- チャット履歴の表示（セッションステートから） ---
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

【指導ガイドライン】
1. **回答の禁止**: どんなに求められても、最終的な答えや数式を直接提示してはいけません。
2. **問いかけ重視**: いきなり解説せず、「まずはどこまで分かった？」「この式変形はどうなると思う？」と問いかけてください。
3. **数式**: LaTeX形式（$マーク）を使ってきれいに表示してください。
"""

# --- 10. AI応答ロジック ---
# ★★★ UI変更：チャットログの下に「画像＋テキスト＋送信」のフォームを配置 ★★★

st.write("---") # 区切り線

# 画面下部に固定風に見せるための余白調整などはCSSで行っているが、
# ここでは物理的にフォームを配置する。
with st.form(key="chat_form", clear_on_submit=True):
    # レイアウト：[カメラ(画像)] [テキスト入力] [送信ボタン]
    # width比率を調整してそれっぽく見せる
    col1, col2, col3 = st.columns([1, 4, 1], gap="small")
    
    with col1:
        # 画像アップローダー（ラベルを消してコンパクトに）
        uploaded_file = st.file_uploader("📸", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed")
    
    with col2:
        # テキストエリア（高さを抑える）
        user_prompt = st.text_area("質問", placeholder="質問を入力...", height=68, label_visibility="collapsed")
        
    with col3:
        # 送信ボタン（テキストエリアの高さに合うように少しCSSハックが必要だが、まずは配置）
        st.write("") # 空行で位置調整
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
                    user_msg_content += "\n\n(※画像を送信しました)"
                except Exception as e:
                    st.error("画像エラー")

            # 1. ユーザーのメッセージをセッションステートに追加（即時表示用）
            st.session_state.messages.append({
                "role": "user",
                "content": user_msg_content
            })
            
            # 2. Firestoreへ保存（非同期っぽく振る舞うため、表示後に保存してもよいが安全のためここで）
            user_ref.collection("history").add({
                "role": "user",
                "content": user_msg_content,
                "timestamp": firestore.SERVER_TIMESTAMP
            })

            # リランしてユーザーのメッセージを表示（フォーム送信後はリランされるが、念のため）
            # ここではリランせず、そのままAI生成に進むことでUXを向上させる
            
            # 3. AI生成準備
            genai.configure(api_key=api_key)
            
            # 履歴の構築（画像は今回のターンのみ）
            history_for_ai = []
            # 最新のユーザーメッセージ以外の過去ログを入れる
            for m in st.session_state.messages[:-1]:
                content_str = ""
                if isinstance(m["content"], dict):
                    content_str = m["content"].get("text", "")
                else:
                    content_str = str(m["content"])
                history_for_ai.append({"role": m["role"], "parts": [content_str]})

            # 4. AI生成実行
            try:
                # ユーザーメッセージの直下にAIの思考中を表示したいが、
                # フォーム送信後は一度リロードされる仕様のため、st.spinnerを使う
                with st.spinner("AIコーチが思考中..."):
                    model = genai.GenerativeModel("models/gemini-1.5-flash", system_instruction=system_instruction)
                    chat = model.start_chat(history=history_for_ai)
                    
                    inputs = [user_prompt]
                    if upload_img_obj:
                        inputs.append(upload_img_obj)
                    
                    response = chat.send_message(inputs)
                    ai_text = response.text

                # 5. 結果の保存と表示
                st.session_state.messages.append({
                    "role": "model",
                    "content": ai_text
                })
                
                user_ref.collection("history").add({
                    "role": "model",
                    "content": ai_text,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                
                # 画面更新（これで新しいメッセージが表示される）
                st.rerun()

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
