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

# テスト期間中は全員プレミアムなのでStripe IDは使いませんが、コード互換性のため残します
STRIPE_PRICE_ID = "price_1SdhxlQpLmU93uYCGce6dPni"
# ★管理者用パスワード（新規登録やデータ閲覧に使用）
ADMIN_KEY = "admin1234" 

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

# --- 4. UI: ログイン画面（未ログイン時） ---
if st.session_state.user_info is None:
    st.title("🎓 AI数学コーチ：ログイン")
    
    if "FIREBASE_WEB_API_KEY" not in st.secrets and FIREBASE_WEB_API_KEY == "ここにウェブAPIキーを貼り付ける":
        st.warning("⚠️ Web APIキーが設定されていません。Streamlit Secretsを設定してください。")
    
    # ログインフォーム
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
    
    # 管理者だけが開ける「新規登録」メニュー
    with st.expander("管理者用：新規アカウント作成"):
        admin_pass_input = st.text_input("管理者パスワード", type="password", key="admin_reg_pass")
        if admin_pass_input == ADMIN_KEY:
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
user_doc = user_ref.get()

if not user_doc.exists:
    user_data = {"email": user_email, "created_at": firestore.SERVER_TIMESTAMP} 
    user_ref.set(user_data)
    student_name = "ゲスト"
else:
    user_data = user_doc.to_dict()
    student_name = user_data.get("name", "ゲスト")

# 全員強制的にプレミアムプラン扱い
current_plan = "premium"

api_key = ""
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
if not api_key:
    pass

# --- 6. サイドバー ---
with st.sidebar:
    # 1. ようこそ（最上段）
    st.header(f"ようこそ")
    new_name = st.text_input("お名前", value=student_name)
    if new_name != student_name:
        user_ref.update({"name": new_name})
        st.rerun()
    
    st.markdown("---")

    # 2. 会話履歴削除（生徒がよく使う）
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

    # 3. ログアウト（生徒がよく使う）
    if st.button("ログアウト"):
        st.session_state.user_info = None
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")

    # 4. フィードバック（気軽に使ってほしい）
    st.caption("📢 ご意見・不具合報告")
    with st.form("feedback_form", clear_on_submit=True):
        feedback_content = st.text_area("感想、バグ、要望など", placeholder="例：〇〇の計算でエラーが出ました / 〇〇な機能が欲しいです")
        feedback_submit = st.form_submit_button("開発者に送信")
        if feedback_submit and feedback_content:
            db.collection("feedback").add({
                "user_id": user_id,
                "email": user_email,
                "content": feedback_content,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            st.success("ありがとうございます！送信しました。")

    st.markdown("---")

    # 5. プラン状況
    st.success("👑 モニター会員 (Pro機能有効)")
    st.caption("現在、テスト期間につき全機能を開放しています。")

    st.markdown("---")

    # 6. 管理者用：保護者レポート作成（一番下へ）
    with st.expander("管理者用：保護者レポート作成"):
        report_admin_pass = st.text_input("管理者パスワード", type="password", key="report_admin_pass")
        
        if report_admin_pass == ADMIN_KEY:
            st.info("🔓 レポート作成モード")
            
            # チャット履歴読み込み（レポート用）
            history_ref = user_ref.collection("history").order_by("timestamp")
            docs = history_ref.stream()
            messages_for_report = []
            for doc in docs:
                messages_for_report.append(doc.to_dict())

            if st.button("📝 今日のレポートを作成"):
                if not messages_for_report:
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
                            # 直近20件を使用
                            for m in messages_for_report[-20:]: 
                                role_name = "先生" if m["role"] == "model" else "生徒"
                                content_text = m["content"].get("text", "") if isinstance(m["content"], dict) else str(m["content"])
                                conversation_text += f"{role_name}: {content_text}\n"

                            genai.configure(api_key=api_key)
                            REPORT_MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
                            
                            report_text = ""
                            success_report = False
                            
                            for model_name in REPORT_MODELS:
                                try:
                                    full_model_name = f"models/{model_name}" if not model_name.startswith("models/") else model_name
                                    report_model = genai.GenerativeModel(full_model_name, system_instruction=report_system_instruction)
                                    response = report_model.generate_content(f"【会話ログ】\n{conversation_text}")
                                    report_text = response.text
                                    success_report = True
                                    break
                                except Exception as e:
                                    continue
                            
                            if success_report and report_text:
                                st.session_state.last_report = report_text
                                st.success("レポートを作成しました！")
                            else:
                                st.error("レポート生成に失敗しました。")

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

# メイン表示用の履歴読み込み（全員に表示するため再取得）
history_ref = user_ref.collection("history").order_by("timestamp")
docs = history_ref.stream()
messages = []
for doc in docs:
    messages.append(doc.to_dict())

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
あなたは世界一の「ソクラテス式数学コーチ」です。
生徒の名前は「{new_name}」さんです。
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
        
        PRIORITY_MODELS = [
            "gemini-3-flash-preview", 
            "gemini-2.0-flash",       
            "gemini-2.0-flash-exp",   
            "gemini-2.5-flash",       
            "gemini-3-pro-preview",   
            "gemini-1.5-pro"          
        ]
        
        success = False
        active_model = None
        
        def try_generate(model_name):
            full_model_name = f"models/{model_name}" if not model_name.startswith("models/") else model_name
            retry_model = genai.GenerativeModel(full_model_name, system_instruction=system_instruction)
            chat = retry_model.start_chat(history=history_for_ai)
            return chat.send_message(prompt, stream=True)

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
