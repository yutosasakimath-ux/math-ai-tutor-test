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
if "last_used_model" not in st.session_state:
    st.session_state.last_used_model = "未実行"

if st.session_state.last_reset_date != datetime.date.today():
    st.session_state.pro_usage_count = 0
    st.session_state.last_reset_date = datetime.date.today()

# --- 4. ログイン画面 ---
if st.session_state.user_info is None:
    st.title("🎓 AI数学コーチ：ログイン")
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

# --- 5. サイドバー (診断機能統合) ---
with st.sidebar:
    st.header(f"こんにちは、{student_name}さん")
    
    # 決済リンク
    if current_plan != "premium":
        if st.button("👑 プレミアムにアップグレード"):
            doc_ref = user_ref.collection("checkout_sessions").add({
                "price": STRIPE_PRICE_ID,
                "success_url": st.secrets.get("BASE_URL", "http://localhost:8501"),
                "cancel_url": st.secrets.get("BASE_URL", "http://localhost:8501"),
            })
            st.info("決済URLを生成中... 数秒待ってから下に出るリンクをクリックしてください。")
            time.sleep(2)
            res = user_ref.collection("checkout_sessions").document(doc_ref[1].id).get()
            if res.exists and "url" in res.to_dict():
                st.link_button("💳 お支払い画面へ進む", res.to_dict()["url"])

    st.markdown("---")
    
    # リセットボタン
    if st.button("🗑️ 会話履歴をリセット"):
        all_history = user_ref.collection("history").get()
        for doc in all_history:
            doc.reference.delete()
        st.success("リセット完了")
        st.rerun()

    # ★ システム診断セクション ★
    with st.expander("🛠️ システム診断 (開発者向け)"):
        st.write(f"現在のプラン: **{current_plan.upper()}**")
        st.write(f"前回の使用モデル: `{st.session_state.last_used_model}`")
        
        # APIキー取得
        api_key = st.secrets.get("GEMINI_API_KEY", "")
        if not api_key:
            api_key = st.text_input("API Keyを入力", type="password")

        if st.button("🔎 利用可能モデルをスキャン"):
            if api_key:
                try:
                    genai.configure(api_key=api_key)
                    models = genai.list_models()
                    available = [m.name for m in models if 'generateContent' in m.supported_generation_methods]
                    st.code("\n".join(available))
                    
                    # 3.0やThinkingの有無を確認
                    has_3_0 = any("3.0" in m for m in available)
                    has_thinking = any("thinking" in m.lower() or "2.0-flash-exp" in m for m in available)
                    
                    if has_3_0: st.success("✅ Gemini 3.0 利用可能！")
                    if has_thinking: st.success("✅ Thinking(思考)モデル利用可能！")
                    if not has_3_0 and not has_thinking: st.warning("⚠️ 2.5系列のみ利用可能です。")
                except Exception as e:
                    st.error(f"スキャンエラー: {e}")

    if st.button("ログアウト"):
        st.session_state.user_info = None
        st.rerun()

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

    # ユーザーメッセージ保存
    user_ref.collection("history").add({"role": "user", "content": prompt, "timestamp": firestore.SERVER_TIMESTAMP})
    with st.chat_message("user"):
        st.markdown(prompt)

    # モデル選定
    # Gemini 3.0 Thinking や 2.0 Flash Exp を優先的にトライします
    PRIORITY_MODELS = [
        "gemini-3.0-flash-exp",
        "gemini-3.0-flash",
        "gemini-2.0-flash-thinking-exp", # 思考モード
        "gemini-2.0-flash-exp",          # 2.0 実験版
        "gemini-2.5-flash",              # 安定版
        "gemini-1.5-pro"                 # バックアップ
    ]

    genai.configure(api_key=api_key)
    
    # 履歴取得
    chat_history = []
    past_msgs = user_ref.collection("history").order_by("timestamp").get()
    for m in past_msgs:
        d = m.to_dict()
        chat_history.append({"role": d["role"], "parts": [d["content"]]})

    instruction = f"あなたは数学の個別指導講師です。生徒名:{student_name}。答えは出さず、ヒントを与えて思考を促してください。"

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        success = False
        
        for model_id in PRIORITY_MODELS:
            try:
                model = genai.GenerativeModel(model_id, system_instruction=instruction)
                chat = model.start_chat(history=chat_history[:-1]) # 今回のメッセージはまだ含めない
                
                # 思考モード（Thinking）の場合、特別な設定が必要な場合があるため
                # ここでは標準的なストリーミング送信を行います
                response = chat.send_message(prompt, stream=True)
                
                for chunk in response:
                    if chunk.text:
                        full_response += chunk.text
                        response_placeholder.markdown(full_response)
                
                st.session_state.last_used_model = model_id
                success = True
                break
            except Exception as e:
                continue # 次のモデルを試す

        if not success:
            st.error("現在、AIモデルにアクセスできません。")
        else:
            user_ref.collection("history").add({"role": "model", "content": full_response, "timestamp": firestore.SERVER_TIMESTAMP})
