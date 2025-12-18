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
    st.session_state.last_used_model = "まだ回答していません"

if st.session_state.last_reset_date != datetime.date.today():
    st.session_state.pro_usage_count = 0
    st.session_state.last_reset_date = datetime.date.today()

# リセット用キー管理
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0
if "form_key_index" not in st.session_state:
    st.session_state.form_key_index = 0

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
                    st.success("ログイン成功")
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
# ログイン済みユーザーの世界
# =========================================================

user_id = st.session_state.user_info["uid"]
user_email = st.session_state.user_info["email"]

# --- 5. ユーザー情報とプラン確認 ---
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
                doc_ref = user_ref.collection("checkout_sessions").add({
                    "price": STRIPE_PRICE_ID,
                    "success_url": "https://math-ai-tutor-test-n8dyekhp6yjmcpa2qei7sg.streamlit.app/",
                    "cancel_url": "https://math-ai-tutor-test-n8dyekhp6yjmcpa2qei7sg.streamlit.app/",
                })
                session_id = doc_ref[1].id
                
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
    
    # ★★★ ここにリセット機能を追加 ★★★
    st.markdown("---")
    if st.button("🗑️ 会話履歴を全削除"):
        with st.spinner("履歴を削除中..."):
            # Firestoreのサブコレクション内のドキュメントを全て削除
            batch = db.batch()
            all_history = user_ref.collection("history").stream()
            count = 0
            for doc in all_history:
                batch.delete(doc.reference)
                count += 1
                # バッチ処理の上限（500件）を超えないように分割コミット
                if count >= 400:
                    batch.commit()
                    batch = db.batch()
                    count = 0
            
            if count > 0:
                batch.commit()
                
            st.success("履歴をリセットしました！")
            time.sleep(1)
            st.rerun()

    st.markdown("---")
    if st.button("ログアウト"):
        st.session_state.user_info = None
        st.session_state.messages = []
        st.rerun()
    
    st.markdown("---")
    st.caption("🛠️ 開発者用デバッグ情報")
    
    model_display = st.session_state.last_used_model
    if "3.0" in str(model_display):
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

for msg in messages:
    with st.chat_message(msg["role"]):
        content = msg["content"]
        if isinstance(content, dict):
            if "text" in content:
                st.markdown(content["text"])
        else:
            st.markdown(content)

# --- 9. プロンプト定義 ---
system_instruction = f"""
あなたは日本の進学校で教える、非常に優秀で忍耐強い数学教師です。
相手は高校生の「{new_name}」さんです。

【指導の絶対ルール】
1. **ソクラテス式指導:** 答えを教えず、問いかけで導くこと。
2. **教科書準拠:** 高校数学の範囲内で解説すること。
3. **優しさと承認:** 否定せず、褒めて伸ばすこと。
4. **形式:** 数式はLaTeX形式（$マーク）を使用すること。

【画像について】
問題を読み取り、方針のヒントを出してください。
"""

# --- 10. AI応答ロジック（Gemini 3.0 Flash対応） ---
if prompt := st.chat_input("質問を入力してください..."):
    if not api_key:
        st.warning("サイドバーでGemini APIキーを設定してください。")
        st.stop()

    with st.chat_message("user"):
        st.markdown(prompt)
    user_ref.collection("history").add({
        "role": "user",
        "content": prompt,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    genai.configure(api_key=api_key)
    
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
        
        # ★★★ 最強の布陣 ★★★
        PRIORITY_MODELS = [
            "gemini-3.0-flash-exp",
            "gemini-3.0-flash",
            "gemini-2.5-flash",
            "gemini-1.5-pro",
            "gemini-2.0-flash"
        ]
        
        PRO_LIMIT_PER_DAY = 15 
        
        success = False
        active_model = None
        
        def try_generate(model_name):
            retry_model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
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
            except:
                continue
        
        if not success:
            st.error("❌ 現在アクセスが集中しており応答できません。")
            st.stop()

    st.session_state.last_used_model = active_model
    user_ref.collection("history").add({
        "role": "model",
        "content": response_text,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    
    st.rerun()
