import streamlit as st
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import json
import datetime
import time

# --- 0. 設定と定数 ---
st.set_page_config(page_title="AI数学専属コーチ", page_icon="🎓", layout="centered")

# ★ Stripeの商品ID
STRIPE_PRICE_ID = "price_1SdhxlQpLmU93uYCGce6dPni"

if "FIREBASE_WEB_API_KEY" in st.secrets:
    FIREBASE_WEB_API_KEY = st.secrets["FIREBASE_WEB_API_KEY"]
else:
    # ローカルテスト用など
    FIREBASE_WEB_API_KEY = "ここにウェブAPIキーを貼り付ける" 

# --- 1. Firebase初期化 ---
if not firebase_admin._apps:
    try:
        if "firebase" in st.secrets:
            key_dict = dict(st.secrets["firebase"])
            # secretsの改行コード対応
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

# --- 3. セッション管理 & リミッター初期化 ---
if "user_info" not in st.session_state:
    st.session_state.user_info = None
if "pro_usage_count" not in st.session_state:
    st.session_state.pro_usage_count = 0
if "last_reset_date" not in st.session_state:
    st.session_state.last_reset_date = datetime.date.today()
if "last_used_model" not in st.session_state:
    st.session_state.last_used_model = "まだ回答していません"

# 日付が変わったらカウントリセット
if st.session_state.last_reset_date != datetime.date.today():
    st.session_state.pro_usage_count = 0
    st.session_state.last_reset_date = datetime.date.today()

# --- 4. UI: ログイン画面（未ログイン時） ---
if st.session_state.user_info is None:
    st.title("🎓 AI数学コーチ：ログイン")
    
    if "FIREBASE_WEB_API_KEY" not in st.secrets and FIREBASE_WEB_API_KEY == "ここにウェブAPIキーを貼り付ける":
        st.warning("⚠️ Web APIキーが設定されていません。Streamlit Secretsを設定してください。")
    
    tab1, tab2 = st.tabs(["ログイン", "新規登録"])
    
    with tab1:
        with st.form("login_form"):
            # keyを追加して重複エラーを回避
            email = st.text_input("メールアドレス", key="login_email")
            password = st.text_input("パスワード", type="password", key="login_password")
            submit = st.form_submit_button("ログイン")
            if submit:
                resp = sign_in_with_email(email, password)
                if "error" in resp:
                    st.error(f"ログイン失敗: {resp['error']['message']}")
                else:
                    st.session_state.user_info = {"uid": resp["localId"], "email": resp["email"]}
                    st.success("ログインしました！")
                    st.rerun()

    with tab2:
        with st.form("signup_form"):
            # keyを追加して重複エラーを回避
            new_email = st.text_input("メールアドレス", key="signup_email")
            new_password = st.text_input("パスワード", type="password", key="signup_password")
            submit_new = st.form_submit_button("アカウント作成")
            if submit_new:
                resp = sign_up_with_email(new_email, new_password)
                if "error" in resp:
                    st.error(f"登録失敗: {resp['error']['message']}")
                else:
                    st.success("アカウント作成成功！ログインしてください。")
    st.stop()

# =========================================================
# ログイン済みユーザーの世界
# =========================================================

user_id = st.session_state.user_info["uid"]
user_email = st.session_state.user_info["email"]

# --- 5. Firestoreからユーザーデータ取得 ---
user_ref = db.collection("users").document(user_id)
user_doc = user_ref.get()

# 救済措置：customersも探す
if not user_doc.exists:
    fallback_ref = db.collection("customers").document(user_id)
    if fallback_ref.get().exists:
        user_ref = fallback_ref
        user_doc = user_ref.get()

if not user_doc.exists:
    user_data = {"email": user_email, "created_at": firestore.SERVER_TIMESTAMP}
    user_ref.set(user_data)
    student_name = "ゲスト"
else:
    user_data = user_doc.to_dict()
    student_name = user_data.get("name", "ゲスト")

# 課金状態の判定
current_plan = "free"
subs_ref = user_ref.collection("subscriptions")
active_subs = subs_ref.where("status", "in", ["active", "trialing"]).get()
if len(active_subs) > 0:
    current_plan = "premium"

# --- 6. サイドバー ---
with st.sidebar:
    st.header(f"ようこそ")
    new_name = st.text_input("お名前", value=student_name)
    if new_name != student_name:
        user_ref.update({"name": new_name})
        st.rerun()
    
    st.markdown("---")
    
    if current_plan == "premium":
        st.success("👑 プレミアムプラン")
        st.caption("全機能が使い放題です！")
    else:
        st.info("🥚 無料プラン")
        st.write("プレミアムにアップグレードして\n学習を加速させよう！")
        
        if st.button("👉 プレミアムに登録 (¥1,980/月)"):
            with st.spinner("決済システムに接続中...（初回は30秒ほどかかります）"):
                # 1. 注文書を作成
                doc_ref = user_ref.collection("checkout_sessions").add({
                    "price": STRIPE_PRICE_ID,
                    "success_url": "https://math-ai-tutor-test-n8dyekhp6yjmcpa2qei7sg.streamlit.app/",
                    "cancel_url": "https://math-ai-tutor-test-n8dyekhp6yjmcpa2qei7sg.streamlit.app/",
                })
                session_id = doc_ref[1].id
                
                # 2. URL生成待ち
                checkout_url = None
                error_msg = None
                
                for i in range(60):
                    time.sleep(1)
                    session_doc = user_ref.collection("checkout_sessions").document(session_id).get()
                    
                    if session_doc.exists:
                        data = session_doc.to_dict()
                        if "url" in data:
                            checkout_url = data["url"]
                            break
                        if "error" in data:
                            error_msg = data["error"]["message"]
                            break
                
                if checkout_url:
                    st.link_button("💳 お支払い画面へ進む", checkout_url)
                elif error_msg:
                    st.error(f"エラー: {error_msg}")
                else:
                    st.error("⚠️ タイムアウトしました。")
    
    st.markdown("---")
    
    # リセット機能
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
        st.success("履歴をリセットしました")
        time.sleep(1)
        st.rerun()

    if st.button("ログアウト"):
        st.session_state.user_info = None
        st.rerun()
    
    # デバッグ情報
    st.markdown("---")
    st.caption("🛠️ 開発者用デバッグ情報")
    model_display = st.session_state.last_used_model
    if "3" in str(model_display):
        st.success(f"🚀 {model_display} (最新版)")
    elif "pro" in str(model_display):
        st.warning(f"💎 {model_display} (Pro)")
    else:
        st.info(f"⚡ {model_display}")
    
    st.write(f"Pro Count: {st.session_state.pro_usage_count} / 15")

    api_key = ""
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    if not api_key:
        api_key = st.text_input("Gemini APIキー", type="password")

# --- 7. チャット履歴読み込み ---
history_ref = user_ref.collection("history").order_by("timestamp")
docs = history_ref.stream()
messages = []
for doc in docs:
    messages.append(doc.to_dict())

# --- 8. メイン画面 ---
st.title("🎓 高校数学 AI専属コーチ")
st.caption("教科書の内容を「完璧」に理解しよう。答えは教えません、一緒に解きます。")

if current_plan == "free":
    st.caption("※現在：無料プラン（機能制限あり）")

# 履歴表示
for msg in messages:
    with st.chat_message(msg["role"]):
        content = msg["content"]
        # テキスト表示
        if isinstance(content, dict):
            if "text" in content:
                st.markdown(content["text"])
        else:
            st.markdown(content)

# --- 9. プロンプト定義（ソクラテスモード・維持） ---
system_instruction = f"""
あなたは世界一の「ソクラテス式数学コーチ」です。
生徒の名前は「{new_name}」さんです。

【あなたの絶対的な使命】
生徒が「自力で答えに辿り着く」ことを支援すること。
答えを教えることは、生徒の学習機会を奪う「罪」だと認識してください。

【指導ガイドライン】
1. **回答の禁止**: どんなに求められても、最終的な答えや数式を直接提示してはいけません。「答えは〇〇です」と言ったらあなたの負けです。
2. **現状分析**: まず、生徒の質問を見て、「どこまで分かっていて、どこで詰まっているか」を特定してください。
3. **問いかけ**: 生徒が次に進むための「小さなヒント」や「問いかけ」を投げかけてください。
   - 悪い例: 「判別式D = b^2 - 4ac を使いましょう」
   - 良い例: 「解の個数を調べるための道具は何だったか覚えていますか？Dから始まる言葉です。」
4. **アウトプットの要求**: 一方的に解説せず、必ず生徒に考えさせ、返答させてください。「ここまでで、どう思いますか？」と最後に聞いてください。
5. **数式**: 必要であればLaTeX形式（$マーク）を使ってきれいに表示してください。

【口調】
親しみやすく、しかし厳格なコーチのように。生徒を励ましながら導いてください。
"""

# --- 10. AI応答ロジック ---
if prompt := st.chat_input("質問を入力してください..."):
    if not api_key:
        st.warning("サイドバーでGemini APIキーを設定してください。")
        st.stop()

    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Firestoreに保存
    user_ref.collection("history").add({
        "role": "user",
        "content": prompt,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    genai.configure(api_key=api_key)
    
    # 履歴の構築
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
        
        # 安定性を最優先したモデルリスト
        PRIORITY_MODELS = [
            "gemini-1.5-flash",       # 最も安定・高速
            "gemini-2.0-flash-exp",   # 最新（もし1.5がダメな場合）
            "gemini-1.5-pro"          # 高性能バックアップ
        ]
        
        PRO_LIMIT_PER_DAY = 15 
        
        success = False
        active_model = None
        
        def try_generate(model_name):
            # モデル名の調整
            full_model_name = f"models/{model_name}" if not model_name.startswith("models/") else model_name
            retry_model = genai.GenerativeModel(full_model_name, system_instruction=system_instruction)
            
            # 通常のチャットセッション
            chat = retry_model.start_chat(history=history_for_ai)
            return chat.send_message(prompt, stream=True)

        for model_name in PRIORITY_MODELS:
            if "pro" in model_name and st.session_state.pro_usage_count >= PRO_LIMIT_PER_DAY:
                continue

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
                
                if "pro" in model_name:
                    st.session_state.pro_usage_count += 1
                break
            except Exception as e:
                # エラーログ（デバッグ用）
                print(f"Model {model_name} failed: {e}")
                # ユーザーにはまだエラーを見せず、次のモデルをトライさせる
                continue
        
        if not success:
            st.error("❌ 現在アクセスが集中しており応答できません。しばらく待ってから再試行してください。")
            st.stop()

    st.session_state.last_used_model = active_model
    user_ref.collection("history").add({
        "role": "model",
        "content": response_text,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    
    st.rerun()
