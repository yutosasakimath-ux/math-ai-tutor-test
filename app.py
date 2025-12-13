import streamlit as st
import google.generativeai as genai
from PIL import Image
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import json
import datetime

# --- 0. 設定と定数 ---
st.set_page_config(page_title="AI数学専属コーチ", page_icon="🎓", layout="centered")

# ★ SecretsからAPIキーを取得（安全化）
if "FIREBASE_WEB_API_KEY" in st.secrets:
    FIREBASE_WEB_API_KEY = st.secrets["FIREBASE_WEB_API_KEY"]
else:
    FIREBASE_WEB_API_KEY = "ここにウェブAPIキーを貼り付ける" # Secrets設定後は空でOK

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

# --- 3. セッション管理 & リミッター初期化 ---
if "user_info" not in st.session_state:
    st.session_state.user_info = None

# ★ 赤字防止カウンター & デバッグ情報 ★
if "pro_usage_count" not in st.session_state:
    st.session_state.pro_usage_count = 0
if "last_reset_date" not in st.session_state:
    st.session_state.last_reset_date = datetime.date.today()
if "last_used_model" not in st.session_state:
    st.session_state.last_used_model = "まだ回答していません"

# 日付変更でリセット
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

    with tab2:
        with st.form("signup_form"):
            st.write("初めての方はこちら")
            new_email = st.text_input("メールアドレス")
            new_password = st.text_input("パスワード", type="password")
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

if not user_doc.exists:
    user_data = {"email": user_email, "plan": "free", "created_at": firestore.SERVER_TIMESTAMP}
    user_ref.set(user_data)
else:
    user_data = user_doc.to_dict()

current_plan = user_data.get("plan", "free")
student_name = user_data.get("name", "ゲスト") # 名前がなければゲスト

# --- 6. サイドバー設定 ---
with st.sidebar:
    st.header(f"ようこそ")
    # 名前変更機能
    new_name = st.text_input("お名前", value=student_name)
    if new_name != student_name:
        user_ref.update({"name": new_name})
        st.rerun()
    
    if current_plan == "premium":
        st.success("👑 プレミアムプラン")
    else:
        st.info("🥚 無料プラン")
    
    if st.button("ログアウト"):
        st.session_state.user_info = None
        st.rerun()
    
    st.markdown("---")
    
    with st.expander("💰 【開発用】課金テスト"):
        if current_plan == "free":
            if st.button("👉 プレミアムに変更"):
                user_ref.update({"plan": "premium"})
                st.success("課金成功！")
                st.rerun()
        else:
            if st.button("リセット（無料に戻す）"):
                user_ref.update({"plan": "free"})
                st.success("リセット完了")
                st.rerun()

    # ★ デバッグ情報表示 ★
    st.markdown("---")
    st.caption("🛠️ 開発者用デバッグ情報")
    if "pro" in st.session_state.last_used_model:
        st.error(f"Last Model: {st.session_state.last_used_model}")
    else:
        st.success(f"Last Model: {st.session_state.last_used_model}")
    st.write(f"Pro Count: {st.session_state.pro_usage_count} / 15")

    # APIキー取得
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

for msg in messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- 9. プロンプト定義（統合済み） ---
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

# --- 10. AI応答ロジック（リミッター付き統合版） ---
if prompt := st.chat_input("質問を入力してください..."):
    if not api_key:
        st.warning("サイドバーでGemini APIキーを設定してください。")
        st.stop()

    # 1. ユーザー入力保存
    with st.chat_message("user"):
        st.markdown(prompt)
    user_ref.collection("history").add({
        "role": "user",
        "content": prompt,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    genai.configure(api_key=api_key)
    
    # 履歴変換
    history_for_ai = [{"role": m["role"], "parts": [m["content"]]} for m in messages]
    
    # AI生成開始
    response_text = ""
    with st.chat_message("assistant"):
        placeholder = st.empty()
        
        # ★ 戦略的モデル優先順位 ★
        PRIORITY_MODELS = [
            "gemini-2.5-flash",       # メイン
            "gemini-1.5-pro",         # バックアップ
            "gemini-2.0-flash"        # 予備
        ]
        
        PRO_LIMIT_PER_DAY = 15 # 赤字防止リミッター
        
        success = False
        active_model = None
        
        # 試行関数
        def try_generate(model_name):
            retry_model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
            chat = retry_model.start_chat(history=history_for_ai)
            return chat.send_message(prompt, stream=True)

        for model_name in PRIORITY_MODELS:
            # Pro制限チェック
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
        
        # 全滅時のフォールバック（安いモデルで再トライ）
        if not success:
            if st.session_state.pro_usage_count >= PRO_LIMIT_PER_DAY:
                st.warning("⚠️ 本日の「Proモード」上限に達しました。")
                # ここで終わりではなく、安いモデルでもう一度粘る処理を入れても良いですが
                # 今回はシンプルに警告を出して終了、または安いモデルリスト取得ロジックへ
            
            # 最後のあがき（安いモデル探索）
            try:
                fetched_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                for model_name in fetched_models:
                    if "pro" not in model_name: # Pro以外で試す
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
                        except:
                            continue
            except:
                pass

        if not success:
            st.error("❌ 現在アクセスが集中しており応答できません。")
            st.stop()

    # 2. AI応答保存
    st.session_state.last_used_model = active_model # デバッグ情報保存
    user_ref.collection("history").add({
        "role": "model",
        "content": response_text,
        "timestamp": firestore.SERVER_TIMESTAMP
    })
    
    st.rerun()
