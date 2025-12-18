import streamlit as st
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import json
import datetime
import time
from PIL import Image # 画像処理用に追加

# --- 0. 設定と定数 ---
# initial_sidebar_state="expanded" を追加し、PCでは最初からサイドバーを開くように設定
st.set_page_config(page_title="AI数学専属コーチ", page_icon="🎓", layout="centered", initial_sidebar_state="expanded")

# ★★★ UI設定：スマホ対応・修正版 ★★★
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
.stDeployButton {display:none;}
/* 画像アップローダーの見た目を少し調整 */
.stFileUploader {padding-bottom: 10px;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- 1. Firebase初期化 ---
# 管理者用パスワード
if "ADMIN_KEY" in st.secrets:
    ADMIN_KEY = st.secrets["ADMIN_KEY"]
else:
    ADMIN_KEY = None

if "FIREBASE_WEB_API_KEY" in st.secrets:
    FIREBASE_WEB_API_KEY = st.secrets["FIREBASE_WEB_API_KEY"]
else:
    # 開発用ダミー（動作しません）
    FIREBASE_WEB_API_KEY = "API_KEY_NOT_SET"

if not firebase_admin._apps:
    try:
        if "firebase" in st.secrets:
            key_dict = dict(st.secrets["firebase"])
            # private_keyの改行コード対応
            if "\\n" in key_dict["private_key"]:
                key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(key_dict)
            firebase_admin.initialize_app(cred)
        else:
            # ローカル開発用
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

# --- 5. Firestoreからユーザーデータ取得 ---
user_ref = db.collection("users").document(user_id)
user_doc = user_ref.get()

if not user_doc.exists:
    user_data = {"email": user_email, "created_at": firestore.SERVER_TIMESTAMP} 
    user_ref.set(user_data)
    student_name = "ゲスト"
else:
    user_data = user_doc.to_dict()
    student_name = user_data.get("name", "ゲスト")

api_key = ""
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]

# --- 6. サイドバー ---
with st.sidebar:
    st.header(f"ようこそ")
    new_name = st.text_input("お名前", value=student_name)
    if new_name != student_name:
        user_ref.update({"name": new_name})
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
        st.success("履歴をリセットしました")
        time.sleep(1)
        st.rerun()

    if st.button("ログアウト"):
        st.session_state.user_info = None
        st.session_state.messages = []
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
            
            history_ref = user_ref.collection("history").order_by("timestamp")
            docs = history_ref.stream()
            messages_for_report = []
            for doc in docs:
                messages_for_report.append(doc.to_dict())

            if st.button("📝 今日のレポートを作成"):
                if not messages_for_report:
                    st.warning("学習履歴がありません。")
                elif not api_key:
                    st.error("APIキー設定エラー")
                else:
                    with st.spinner("会話ログを分析中..."):
                        try:
                            # レポート用プロンプト（省略せず記述）
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
                            for m in messages_for_report[-20:]: 
                                role_name = "先生" if m["role"] == "model" else "生徒"
                                content_text = m["content"].get("text", "") if isinstance(m["content"], dict) else str(m["content"])
                                conversation_text += f"{role_name}: {content_text}\n"

                            genai.configure(api_key=api_key)
                            # レポートは高速なFlashモデルを優先
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

# チャット履歴の表示
history_ref = user_ref.collection("history").order_by("timestamp")
docs = history_ref.stream()
messages = []
for doc in docs:
    messages.append(doc.to_dict())

for msg in messages:
    with st.chat_message(msg["role"]):
        content = msg["content"]
        # Firestoreには画像パスを保存していないためテキストのみ表示
        if isinstance(content, dict):
            if "text" in content:
                st.markdown(content["text"])
        else:
            st.markdown(content)

# --- ★★★ 画像アップロード機能（位置変更：会話ログの下へ） ★★★ ---
st.write("") # 履歴との間に少し余白を入れる
with st.expander("📸 数式の写真をアップロード（ここをタップ）", expanded=False):
    st.caption("ノートや教科書の写真を撮ってアップロードしてください。")
    uploaded_file = st.file_uploader("画像を選択", type=["jpg", "jpeg", "png", "webp"])
    
    uploaded_image = None
    if uploaded_file is not None:
        try:
            uploaded_image = Image.open(uploaded_file)
            st.image(uploaded_image, caption="送信する画像", width=250)
        except Exception as e:
            st.error("画像の読み込みに失敗しました。別の画像を試してください。")

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
1. **回答の禁止**: どんなに求められても、最終的な答えや数式を直接提示してはいけません。
2. **現状分析**: 生徒がどこまで分かっているかを特定してください。
3. **問いかけ**: 次に進むための「小さなヒント」を出してください。
4. **アウトプットの要求**: 「ここまでで、どう思いますか？」と最後に聞いてください。
5. **数式**: LaTeX形式（$マーク）を使ってきれいに表示してください。
"""

# --- 10. AI応答ロジック ---
# チャット入力
if prompt := st.chat_input("質問を入力してください...（画像がある場合は先にアップロード）"):
    if not api_key:
        st.warning("サイドバーでGemini APIキーを設定してください。")
        st.stop()

    # ユーザーの入力を表示
    with st.chat_message("user"):
        st.markdown(prompt)
        # 今回のターンだけ画像を表示
        if uploaded_image:
            st.image(uploaded_image, width=200)

    # Firestoreへ保存（画像データは容量削減のため保存せず、テキストで代替）
    user_msg_content = prompt
    if uploaded_image:
        user_msg_content += "\n\n(※画像を送信しました)"
    
    user_ref.collection("history").add({
        "role": "user",
        "content": user_msg_content,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    genai.configure(api_key=api_key)
    
    # 過去の履歴をテキストのみで構築（画像は今回のターンのみ使用）
    history_for_ai = []
    for m in messages:
        content_str = ""
        if isinstance(m["content"], dict):
            content_str = m["content"].get("text", "")
        else:
            content_str = str(m["content"])
        history_for_ai.append({"role": m["role"], "parts": [content_str]})

    response_text = ""
    with st.chat_message("assistant"):
        placeholder = st.empty()
        
        # モデルリスト（マルチモーダル対応のモデルを優先）
        PRIORITY_MODELS = [
            "gemini-2.0-flash",        # 高速・高性能
            "gemini-1.5-flash",        # 安定・安価
            "gemini-1.5-pro",          # 高精度
            "gemini-2.0-flash-exp"     # 実験的
        ]
        
        success = False
        active_model = None
        
        def try_generate(model_name):
            full_model_name = f"models/{model_name}" if not model_name.startswith("models/") else model_name
            retry_model = genai.GenerativeModel(full_model_name, system_instruction=system_instruction)
            
            # チャットセッションを開始
            chat = retry_model.start_chat(history=history_for_ai)
            
            # 入力データを作成（テキスト + 画像があれば画像も）
            inputs = [prompt]
            if uploaded_image:
                inputs.append(uploaded_image)
            
            # ストリーミング送信
            return chat.send_message(inputs, stream=True)

        # モデルローテーション実行
        for model_name in PRIORITY_MODELS:
            try:
                response = try_generate(model_name)
                full_res = ""
                for chunk in response:
                    if chunk.text:
                        full_res += chunk.text
                        placeholder.markdown(full_res)
                
                response_text = full_res
                success = True
                active_model = model_name
                break
            except Exception as e:
                # エラー時は次のモデルへ
                # print(f"Model {model_name} failed: {e}") # デバッグ用
                continue
        
        if not success:
            st.error("❌ 申し訳ありません。現在アクセスが集中しているか、画像が処理できませんでした。もう一度お試しください。")
            st.stop()

    st.session_state.last_used_model = active_model
    
    # AIの返答をFirestoreに保存
    user_ref.collection("history").add({
        "role": "model",
        "content": response_text,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    
    # 画像をアップロードしたままリランすると次回も送信されてしまうため、
    # 本来はuploaderをクリアしたいが、Streamlitの仕様上難しいため、
    # そのままリランする（ユーザーには手動で×を押してもらう運用）
    st.rerun()
