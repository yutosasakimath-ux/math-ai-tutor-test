import streamlit as st
import google.generativeai as genai
from PIL import Image
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

# ★★★ 【重要】ここにWeb APIキーを貼り付けてください ★★★
FIREBASE_WEB_API_KEY = "ここにWebAPIキーを貼り付けてください" 

# Secretsに設定がある場合はそちらを優先
if "FIREBASE_WEB_API_KEY" in st.secrets:
    FIREBASE_WEB_API_KEY = st.secrets["FIREBASE_WEB_API_KEY"]

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

# --- 2. 認証機能ヘルパー ---
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
if "pro_usage_count" not in st.session_state:
    st.session_state.pro_usage_count = 0
if "last_reset_date" not in st.session_state:
    st.session_state.last_reset_date = datetime.date.today()

if st.session_state.last_reset_date != datetime.date.today():
    st.session_state.pro_usage_count = 0
    st.session_state.last_reset_date = datetime.date.today()

# --- 4. ログイン画面 ---
if st.session_state.user_info is None:
    st.title("🎓 AI数学コーチ：ログイン")
    
    if "ここに" in FIREBASE_WEB_API_KEY:
        st.warning("⚠️ Web APIキーが設定されていません。コード内の `FIREBASE_WEB_API_KEY` を確認してください。")

    tab1, tab2 = st.tabs(["ログイン", "新規登録"])
    with tab1:
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
                    st.rerun()
    with tab2:
        with st.form("signup_form"):
            new_email = st.text_input("メールアドレス")
            new_password = st.text_input("パスワード", type="password")
            submit_new = st.form_submit_button("アカウント作成")
            if submit_new:
                resp = sign_up_with_email(new_email, new_password)
                if "error" in resp:
                    st.error(f"登録失敗: {resp['error']['message']}")
                else:
                    st.success("作成成功！ログインしてください。")
    st.stop()

# =========================================================
# アプリメイン
# =========================================================

user_id = st.session_state.user_info["uid"]
user_email = st.session_state.user_info["email"]
user_ref = db.collection("users").document(user_id)
user_doc = user_ref.get()

if not user_doc.exists:
    # 救済措置：customersも探す
    fallback_ref = db.collection("customers").document(user_id)
    if fallback_ref.get().exists:
        user_ref = fallback_ref
        user_doc = user_ref.get()

if not user_doc.exists:
    user_data = {"email": user_email, "created_at": firestore.SERVER_TIMESTAMP, "name": "ゲスト"}
    user_ref.set(user_data)
else:
    user_data = user_doc.to_dict()

student_name = user_data.get("name", "ゲスト")

# 課金判定
current_plan = "free"
active_subs = user_ref.collection("subscriptions").where("status", "in", ["active", "trialing"]).get()
if len(active_subs) > 0:
    current_plan = "premium"

# --- 5. サイドバー ---
with st.sidebar:
    st.header(f"こんにちは、{student_name}さん")
    
    # 決済リンク
    if current_plan != "premium":
        st.info("🥚 無料プラン")
        if st.button("👑 プレミアムにアップグレード"):
            doc_ref = user_ref.collection("checkout_sessions").add({
                "price": STRIPE_PRICE_ID,
                "success_url": "https://math-ai-tutor-test-n8dyekhp6yjmcpa2qei7sg.streamlit.app/",
                "cancel_url": "https://math-ai-tutor-test-n8dyekhp6yjmcpa2qei7sg.streamlit.app/",
            })
            st.info("決済URLを生成中...")
            time.sleep(2)
            # 待機ループ
            checkout_url = None
            for _ in range(60):
                time.sleep(1)
                res = user_ref.collection("checkout_sessions").document(doc_ref[1].id).get()
                if res.exists:
                    data = res.to_dict()
                    if "url" in data:
                        checkout_url = data["url"]
                        break
                    if "error" in data:
                        st.error(f"エラー: {data['error']['message']}")
                        break
            
            if checkout_url:
                st.link_button("💳 お支払い画面へ進む", checkout_url)
            elif not checkout_url:
                st.error("タイムアウトしました。")
    else:
        st.success("👑 プレミアムプラン (有効)")

    st.markdown("---")
    
    # ★★★ 会話履歴リセットボタン（機能維持） ★★★
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

    # APIキー取得
    api_key = ""
    if "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    if not api_key:
        api_key = st.text_input("Gemini APIキー", type="password")

# --- 6. チャット表示 ---
st.title("🎓 AI数学コーチ")

history = user_ref.collection("history").order_by("timestamp").stream()
for msg in history:
    m = msg.to_dict()
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# --- 7. AI応答ロジック ---
if prompt := st.chat_input("数学の悩みを教えてください"):
    if not api_key:
        st.error("APIキーが必要です")
        st.stop()

    # メッセージ保存
    user_ref.collection("history").add({"role": "user", "content": prompt, "timestamp": firestore.SERVER_TIMESTAMP})
    with st.chat_message("user"):
        st.markdown(prompt)

    # ★★★ 最新の優先順位（Gemini 3.0 Flash 優先） ★★★
    PRIORITY_MODELS = [
        "gemini-3.0-flash-preview", # 最新エース
        "gemini-3.0-flash",         # 表記ゆれ対応
        "gemini-2.0-flash-exp",     # 安定の実験版
        "gemini-2.5-flash",         # 従来の安定版
        "gemini-1.5-pro"            # バックアップ
    ]
    PRO_LIMIT_PER_DAY = 15

    genai.configure(api_key=api_key)
    
    # 履歴取得
    chat_history = []
    past_msgs = user_ref.collection("history").order_by("timestamp").get()
    for m in past_msgs:
        d = m.to_dict()
        chat_history.append({"role": d["role"], "parts": [d["content"]]})

    instruction = f"あなたは数学の個別指導講師です。生徒名:{student_name}。答えは出さず、ヒントを与えて思考を促してください。数式は必ず$を用いたLaTeX形式で書いてください。"

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        success = False
        
        for model_id in PRIORITY_MODELS:
            # Proモデル制限チェック
            if "pro" in model_id and st.session_state.pro_usage_count >= PRO_LIMIT_PER_DAY:
                continue

            try:
                full_model_id = f"models/{model_id}" if not model_id.startswith("models/") else model_id
                model = genai.GenerativeModel(full_model_id, system_instruction=instruction)
                chat = model.start_chat(history=chat_history[:-1])
                
                response = chat.send_message(prompt, stream=True)
                
                for chunk in response:
                    if chunk.text:
                        full_response += chunk.text
                        response_placeholder.markdown(full_response)
                
                # Proカウントアップ
                if "pro" in model_id:
                    st.session_state.pro_usage_count += 1
                
                success = True
                break
            except Exception as e:
                continue

        if not success:
            st.error("現在、AIモデルにアクセスできません。")
        else:
            user_ref.collection("history").add({"role": "model", "content": full_response, "timestamp": firestore.SERVER_TIMESTAMP})
