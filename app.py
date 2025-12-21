import streamlit as st
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, firestore, storage
import requests
import json
import datetime
import time
from PIL import Image
import os
import io
import base64
import re  # 正規表現用
import uuid # UUID生成用

# --- ★数式画像化機能（matplotlib）を削除 ---
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
# from reportlab.lib.utils import ImageReader # 削除

# --- 0. 設定と定数 ---
st.set_page_config(page_title="AI数学専属コーチ", page_icon="🎓", layout="centered", initial_sidebar_state="expanded")

# ★★★ UI設定：チャット画面専用CSS（関数内で適用するように変更） ★★★
def apply_chat_css():
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
        max-width: 700px;
        box-shadow: 0px -2px 10px rgba(0,0,0,0.1);
    }

    .main .block-container {
        padding-bottom: 150px; 
    }

    /* カメラアイコン化 */
    [data-testid="stFileUploader"] {
        width: 44px;
        margin-top: -2px;
        padding-top: 0;
    }
    [data-testid="stFileUploader"] section {
        padding: 0;
        min-height: 44px;
        background-color: #f0f2f6;
        border: 1px solid #ccc;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: transparent; 
    }
    [data-testid="stFileUploader"] section > * {
        display: none !important;
    }
    [data-testid="stFileUploader"] section::after {
        content: "📷"; 
        font-size: 22px;
        color: black;
        display: block;
        cursor: pointer;
    }
    [data-testid="stFileUploader"] ul {
        display: none;
    }
    [data-testid="stFileUploader"]:has(input[type="file"]:valid) section {
        background-color: #e0f7fa;
        border-color: #00bcd4;
    }
    .stTextArea textarea {
        font-size: 16px;
        padding: 10px;
    }
    </style>
    """
    st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ポータル画面用CSS
def apply_portal_css():
    portal_style = """
    <style>
    div[data-testid="stHorizontalBlock"] button {
        height: 120px;
        white-space: pre-wrap;
    }
    </style>
    """
    st.markdown(portal_style, unsafe_allow_html=True)


# --- ★追加機能：フォント管理 ---
FONT_URL = "https://moji.or.jp/wp-content/ipafont/IPAexfont/ipaexg00401.zip"
FONT_FILE_NAME = "ipaexg.ttf"

def ensure_japanese_font():
    """PDF用の日本語フォントが存在するか確認し、なければダウンロードする"""
    if os.path.exists(FONT_FILE_NAME):
        return FONT_FILE_NAME
    
    try:
        import zipfile
        r = requests.get(FONT_URL)
        if r.status_code == 200:
            z = zipfile.ZipFile(io.BytesIO(r.content))
            for info in z.infolist():
                if info.filename.endswith(FONT_FILE_NAME):
                    info.filename = FONT_FILE_NAME
                    z.extract(info, path=".")
                    return FONT_FILE_NAME
    except Exception as e:
        print(f"Font download error: {e}")
    return None

# --- ★数式画像生成関数（render_math_to_image）を削除 ---

def create_pdf(text_content, student_name):
    """テキストレポートからPDFを作成しバイナリデータとして返す（シンプルテキスト版）"""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # フォント設定
    font_path = ensure_japanese_font()
    font_name = "Helvetica" # デフォルト
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont('IPAexGothic', font_path))
            font_name = 'IPAexGothic'
        except Exception:
            pass

    # タイトル
    p.setFont(font_name, 18)
    p.drawString(20 * mm, height - 20 * mm, f"学習まとめレポート - {student_name}さん")
    p.setFont(font_name, 10)
    p.drawString(20 * mm, height - 30 * mm, f"作成日: {datetime.date.today().strftime('%Y/%m/%d')}")
    
    # 本文設定
    p.setFont(font_name, 11)
    
    lines = text_content.split('\n')
    # 文字数設定（余裕を持って35文字）
    max_char_per_line = 35 
    line_height = 6 * mm
    y_position = height - 50 * mm
    
    for line in lines:
        # シンプルなテキスト描画のみを行う（数式画像処理を削除）
        while True:
            chunk = line[:max_char_per_line]
            line = line[max_char_per_line:]
            
            p.drawString(20 * mm, y_position, chunk)
            y_position -= line_height
            
            # 改ページ処理
            if y_position < 20 * mm:
                p.showPage()
                p.setFont(font_name, 11)
                y_position = height - 30 * mm
            
            if not line:
                break

    p.save()
    buffer.seek(0)
    return buffer

# --- Secretsの取得 ---
if "ADMIN_KEY" in st.secrets:
    ADMIN_KEY = st.secrets["ADMIN_KEY"]
else:
    ADMIN_KEY = None

if "FIREBASE_WEB_API_KEY" in st.secrets:
    FIREBASE_WEB_API_KEY = st.secrets["FIREBASE_WEB_API_KEY"]
else:
    FIREBASE_WEB_API_KEY = "ここにウェブAPIキーを貼り付ける" 

if "GEMINI_API_KEY" in st.secrets:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
else:
    GEMINI_API_KEY = None

# --- 1. Firebase初期化 ---
# ★Storage対応のため、初期化オプションにstorageBucketを追加するロジックへ変更
if not firebase_admin._apps:
    try:
        # Storageバケット名の取得 (st.secrets["firebase"]["storage_bucket"] または デフォルト)
        # ※ バケット名が不明な場合は一時的にNoneとなりますが、Storage機能利用時にエラーとなります
        storage_bucket = None
        if "firebase" in st.secrets and "storage_bucket" in st.secrets["firebase"]:
            storage_bucket = st.secrets["firebase"]["storage_bucket"]
        
        # 既存のロジック
        if "firebase" in st.secrets:
            key_dict = dict(st.secrets["firebase"])
            if "\\n" in key_dict["private_key"]:
                key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(key_dict)
            
            # Options辞書の作成
            options = {}
            if storage_bucket:
                options['storageBucket'] = storage_bucket
            
            firebase_admin.initialize_app(cred, options)
        else:
            if os.path.exists("service_account.json"):
                cred = credentials.Certificate("service_account.json")
                # service_account利用時のStorage対応は任意（今回はCloudメイン）
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

if "messages" not in st.session_state:
    st.session_state.messages = []
if "messages_loaded" not in st.session_state:
    st.session_state.messages_loaded = False
    
if "debug_logs" not in st.session_state:
    st.session_state.debug_logs = []

# ★新規追加: 画面遷移管理
if "current_page" not in st.session_state:
    st.session_state.current_page = "portal"

def navigate_to(page_name):
    st.session_state.current_page = page_name
    st.rerun()

# --- 4. UI: ログイン画面 ---
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
                if "user_name" in st.session_state:
                    del st.session_state["user_name"]
                st.success("ログインしました！")
                st.rerun()

    st.markdown("---")
    
    with st.expander("管理者用：新規アカウント作成"):
        admin_pass_input = st.text_input("管理者パスワード", type="password", key="admin_reg_pass")
        if ADMIN_KEY and admin_pass_input == ADMIN_KEY:
            st.info("🔓 管理者モード：新規モニターユーザーを作成します")
            with st.form("admin_signup_form"):
                new_name_input = st.text_input("生徒のお名前") 
                new_email = st.text_input("新規メールアドレス")
                new_password = st.text_input("新規パスワード")
                submit_new = st.form_submit_button("アカウントを作成する")
                
                if submit_new:
                    if not new_name_input:
                        st.error("お名前を入力してください")
                    else:
                        resp = sign_up_with_email(new_email, new_password)
                        if "error" in resp:
                            st.error(f"作成失敗: {resp['error']['message']}")
                        else:
                            new_uid = resp["localId"]
                            try:
                                db.collection("users").document(new_uid).set({
                                    "name": new_name_input,
                                    "email": new_email,
                                    "created_at": firestore.SERVER_TIMESTAMP,
                                    "totalStudyMinutes": 0, # 初期値追加
                                    "isAnonymousRanking": False # 初期値追加
                                })
                                st.success(f"アカウント作成成功！\n名前: {new_name_input}\nEmail: {new_email}\nPass: {new_password}")
                            except Exception as e:
                                st.error(f"データベース登録エラー: {e}")
        elif admin_pass_input:
            st.error("パスワードが違います")
    st.stop()

# =========================================================
# ログイン済みユーザーの世界
# =========================================================

user_id = st.session_state.user_info["uid"]
user_email = st.session_state.user_info["email"]

user_ref = db.collection("users").document(user_id)
if "user_name" not in st.session_state:
    try:
        user_doc = user_ref.get()
        if not user_doc.exists:
            user_data = {"email": user_email, "created_at": firestore.SERVER_TIMESTAMP} 
            user_ref.set(user_data)
            st.session_state.user_name = "ゲスト"
        else:
            user_data = user_doc.to_dict()
            st.session_state.user_name = user_data.get("name", "ゲスト")
    except Exception as e:
        st.session_state.user_name = "ゲスト"

student_name = st.session_state.user_name

# --- 6. サイドバー (共通) ---
with st.sidebar:
    st.header(f"ようこそ、{student_name}さん")
    
    # ★追加: ナビゲーションボタン
    if st.button("🏠 ホームに戻る", use_container_width=True):
        navigate_to("portal")
    
    st.markdown("---")

    new_name = st.text_input("お名前（AIが呼びかける名前）", value=student_name)
    if new_name != student_name:
        user_ref.update({"name": new_name})
        st.session_state.user_name = new_name
        st.rerun()

    # ★追加: ランキング匿名設定
    try:
        # 現在の設定を取得（キャッシュ考慮）
        if "is_anon_ranking" not in st.session_state:
            u_doc = user_ref.get()
            if u_doc.exists:
                st.session_state.is_anon_ranking = u_doc.to_dict().get("isAnonymousRanking", False)
            else:
                st.session_state.is_anon_ranking = False
        
        is_anon = st.checkbox("ランキングで匿名にする", value=st.session_state.is_anon_ranking)
        if is_anon != st.session_state.is_anon_ranking:
            user_ref.update({"isAnonymousRanking": is_anon})
            st.session_state.is_anon_ranking = is_anon
            st.success("設定を更新しました")
    except Exception:
        pass
    
    st.markdown("---")

    if st.button("🗑️ 会話履歴を全削除"):
        with st.spinner("履歴を保存して削除中..."):
            try:
                history_stream = user_ref.collection("history").order_by("timestamp").stream()
                session_logs = []
                batch = db.batch()
                doc_count = 0
                
                for doc in history_stream:
                    data = doc.to_dict()
                    session_logs.append(data)
                    batch.delete(doc.reference)
                    doc_count += 1
                    
                    if doc_count >= 400:
                        batch.commit()
                        batch = db.batch()
                        doc_count = 0
                
                if doc_count > 0:
                    batch.commit()

                if session_logs:
                    user_ref.collection("archived_sessions").add({
                        "archived_at": firestore.SERVER_TIMESTAMP,
                        "messages": session_logs,
                        "note": "ユーザーによる全削除時のバックアップ"
                    })
            except Exception as e:
                st.error(f"ログ保存エラー: {e}")

            st.session_state.last_report = "" 
            st.session_state.messages = [] 
            st.session_state.messages_loaded = True 
            st.session_state.debug_logs = [] 
            st.success("履歴をリセットしました")
            time.sleep(1)
            st.rerun()

    if st.button("ログアウト"):
        st.session_state.user_info = None
        st.session_state.messages = []
        st.session_state.messages_loaded = False
        st.session_state.debug_logs = []
        # セッションステートのクリーンアップ
        keys_to_remove = ["user_name", "current_page", "is_anon_ranking"]
        for k in keys_to_remove:
            if k in st.session_state:
                del st.session_state[k]
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

    # --- 管理者メニュー ---
    with st.expander("管理者用：管理メニュー"): 
        report_admin_pass = st.text_input("管理者パスワード", type="password", key="report_admin_pass")
        
        if ADMIN_KEY and report_admin_pass == ADMIN_KEY:
            st.info("🔓 管理者モード")

            st.markdown("### 🤖 モデル稼働状況")
            st.info(f"**最後に使用したモデル:** `{st.session_state.last_used_model}`")

            st.markdown("---")
            
            # --- 利用可能なモデル一覧を取得 ---
            if st.button("📡 利用可能なモデル一覧を取得"):
                if not GEMINI_API_KEY:
                    st.error("APIキーが設定されていません")
                else:
                    try:
                        genai.configure(api_key=GEMINI_API_KEY)
                        models = genai.list_models()
                        available_models = []
                        for m in models:
                            if "generateContent" in m.supported_generation_methods:
                                available_models.append(m.name.replace("models/", ""))
                        
                        st.success("取得成功！")
                        st.code("\n".join(available_models))
                        st.session_state.debug_logs.append(f"Available Models:\n{', '.join(available_models)}")
                    except Exception as e:
                        st.error(f"取得エラー: {e}")

            # --- デバッグログ ---
            st.markdown("### 🛠 デバッグログ")
            if st.session_state.debug_logs:
                for i, log in enumerate(reversed(st.session_state.debug_logs)):
                    st.code(log, language="text")
                
                if st.button("ログ消去"):
                    st.session_state.debug_logs = []
                    st.rerun()
            else:
                st.caption("現在エラーログはありません")
            
            st.markdown("---")
            
            # --- コスト分析機能 ---
            st.markdown("### 💰 コスト分析")
            if st.button("📊 ログからコストを試算"):
                with st.spinner("Firestoreのログを集計中..."):
                    try:
                        INPUT_PRICE_PER_M = 0.50 
                        OUTPUT_PRICE_PER_M = 3.00
                        USD_JPY = 155.5
                        SYSTEM_PROMPT_EST_LEN = 700 
                        
                        logs_ref = user_ref.collection("full_conversation_logs").order_by("timestamp")
                        docs = logs_ref.stream()
                        logs = [d.to_dict() for d in docs]
                        data_source = "全保存ログ"
                        
                        if not logs:
                            logs_ref = user_ref.collection("history").order_by("timestamp")
                            docs = logs_ref.stream()
                            logs = [d.to_dict() for d in docs]
                            data_source = "現在の履歴"

                        if not logs:
                            st.warning("ログデータが見つかりませんでした。")
                        else:
                            total_input_chars = 0
                            total_output_chars = 0
                            history_buffer_len = 0
                            
                            for log in logs:
                                content = log.get("content", "")
                                content_len = len(content)
                                img_cost = 0
                                if "(※画像を送信しました)" in content:
                                    img_cost = 300
                                
                                if log.get("role") == "user":
                                    current_input = SYSTEM_PROMPT_EST_LEN + history_buffer_len + content_len + img_cost
                                    total_input_chars += current_input
                                    history_buffer_len += content_len
                                elif log.get("role") == "model":
                                    total_output_chars += content_len
                                    history_buffer_len += content_len

                            input_cost_usd = (total_input_chars / 1_000_000) * INPUT_PRICE_PER_M
                            output_cost_usd = (total_output_chars / 1_000_000) * OUTPUT_PRICE_PER_M
                            total_usd = input_cost_usd + output_cost_usd
                            total_jpy = total_usd * USD_JPY

                            st.success(f"試算完了 (ソース: {data_source})")
                            col_c1, col_c2, col_c3 = st.columns(3)
                            with col_c1:
                                st.metric("推定総コスト", f"¥ {total_jpy:.2f}")
                            with col_c2:
                                st.metric("総入力", f"{total_input_chars:,}")
                            with col_c3:
                                st.metric("総出力", f"{total_output_chars:,}")
                            
                            st.caption("※ 概算値です。")

                    except Exception as e:
                        st.error(f"計算エラー: {e}")

            st.markdown("---")
            # --- レポート作成機能 (★機能変更：PDF自動生成・自動オープン・テキスト数式対応) ---
            st.markdown("### 📝 学習まとめレポート作成")
            st.caption("生徒用の復習レポート（公式・解法まとめ）を生成し、別タブで開きます。")
            
            if st.button("📝 レポートを作成してPDFを開く"):
                if not GEMINI_API_KEY:
                    st.error("Gemini APIキーを設定してください。")
                else:
                    with st.spinner("AIがレポートを執筆し、PDFを生成中..."):
                        try:
                            # 1. ログ収集 (JST)
                            jst_tz = datetime.timezone(datetime.timedelta(hours=9))
                            now_jst = datetime.datetime.now(jst_tz)
                            start_of_day_jst = now_jst.replace(hour=0, minute=0, second=0, microsecond=0)
                            end_of_day_jst = start_of_day_jst + datetime.timedelta(days=1)

                            all_messages = []
                            # (A) archived
                            archived_docs = user_ref.collection("archived_sessions").stream()
                            for doc in archived_docs:
                                data = doc.to_dict()
                                msg_list = data.get("messages", [])
                                for m in msg_list:
                                    ts = m.get("timestamp")
                                    if ts:
                                        ts_jst = ts.astimezone(jst_tz)
                                        if start_of_day_jst <= ts_jst < end_of_day_jst:
                                            all_messages.append(m)
                            # (B) history
                            history_docs = user_ref.collection("history").order_by("timestamp").stream()
                            for doc in history_docs:
                                m = doc.to_dict()
                                ts = m.get("timestamp")
                                if ts:
                                    ts_jst = ts.astimezone(jst_tz)
                                    if start_of_day_jst <= ts_jst < end_of_day_jst:
                                        all_messages.append(m)

                            if not all_messages:
                                st.warning("今日の学習履歴が見つかりませんでした。")
                            else:
                                all_messages.sort(key=lambda x: x.get("timestamp") if x.get("timestamp") else datetime.datetime.min.replace(tzinfo=datetime.timezone.utc))

                                conversation_text = ""
                                for m in all_messages:
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

                                # 2. レポートプロンプト (★変更：高校生でも理解できるテキスト数式)
                                report_system_instruction = f"""
                                あなたは数学の「学習まとめ作成AI」です。
                                生徒の「{new_name}」さんが今日学習した内容を復習できるように、簡潔かつ明確なレポートを作成してください。

                                【重要：数式の出力ルール】
                                厳密なLaTeX表記は使わず、高校生がテキストだけでも理解しやすい記法を使用してください。
                                - 分数: a/b (または言葉で「b分のa」と補足)
                                - 2乗: x^2 
                                - 下付き文字: a_n または a[n]
                                - ギリシャ文字: α, β (Unicode文字を使用)
                                - ルート: √ (ルート)
                                - 例: 解の公式 x = (-b ± √(b^2 - 4ac)) / 2a

                                【出力フォーマット（厳守）】
                                --------------------------------------------------
                                【📅 {now_jst.strftime('%Y/%m/%d')} 学習まとめレポート】
                                
                                ■ 今日学んだ単元
                                （箇条書きで簡潔に）

                                ■ 重要公式・ポイント
                                （わかりやすいテキスト形式で公式を列挙。例: α + β = -b/a）

                                ■ 今日の解法メモ
                                （具体的にどのような問題に取り組み、どう解決したかを要約）

                                ■ 次回へのアドバイス
                                （励ましのメッセージと、次に復習すべき点）
                                --------------------------------------------------
                                ※ マークダウンは使わず、プレーンテキストで見やすく整形してください。
                                """
                                
                                genai.configure(api_key=GEMINI_API_KEY)
                                REPORT_MODELS = [
                                    "gemini-3-flash-preview", 
                                    "gemini-2.0-flash-exp", 
                                    "gemini-1.5-flash", 
                                    "gemini-1.5-pro"
                                ]
                                report_text = ""
                                success_report = False
                                used_model = None
                                
                                for model_name in REPORT_MODELS:
                                    try:
                                        report_model = genai.GenerativeModel(model_name, system_instruction=report_system_instruction)
                                        response = report_model.generate_content(f"【会話ログ】\n{conversation_text}")
                                        if response.text:
                                            report_text = response.text
                                            success_report = True
                                            used_model = model_name
                                            st.session_state.debug_logs.append(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ✅ Report generated: {model_name}")
                                            break
                                    except Exception as e:
                                        st.session_state.debug_logs.append(f"⚠️ Report failed ({model_name}): {e}")
                                        continue
                                
                                if success_report and report_text:
                                    st.session_state.last_report = report_text
                                    
                                    # ★重要：ここで直ちにPDFを生成（シンプルテキスト版）★
                                    pdf_buffer = create_pdf(report_text, new_name)
                                    pdf_b64 = base64.b64encode(pdf_buffer.getvalue()).decode('utf-8')
                                    
                                    # Blob URLを生成して開くJSスクリプト
                                    js_code = f"""
                                    <script>
                                    (function() {{
                                        var b64 = "{pdf_b64}";
                                        var byteCharacters = atob(b64);
                                        var byteNumbers = new Array(byteCharacters.length);
                                        for (var i = 0; i < byteCharacters.length; i++) {{
                                            byteNumbers[i] = byteCharacters.charCodeAt(i);
                                        }}
                                        var byteArray = new Uint8Array(byteNumbers);
                                        var blob = new Blob([byteArray], {{type: "application/pdf"}});
                                        var blobUrl = URL.createObjectURL(blob);
                                        window.open(blobUrl, '_blank');
                                    }})();
                                    </script>
                                    """
                                    st.components.v1.html(js_code, height=0)
                                    
                                    st.success(f"レポートを作成し、PDFを別タブで開きました！ (Model: {used_model})")
                                    # ポップアップブロックされた時のためにリンクも表示
                                    href = f'<a href="data:application/pdf;base64,{pdf_b64}" download="report_{datetime.date.today()}.pdf" target="_blank">PDFが開かない場合はここをクリックしてダウンロード</a>'
                                    st.markdown(href, unsafe_allow_html=True)
                                else:
                                    st.error("レポート生成に失敗しました。")

                        except Exception as e:
                            st.error(f"予期せぬエラー: {e}")

            # 過去の結果表示（リロード時用）
            if st.session_state.last_report:
                st.text_area("レポート内容", st.session_state.last_report, height=300)

        elif report_admin_pass:
            st.error("パスワードが違います")
    
    st.markdown("---")
    # キーが未設定の場合の入力フォーム
    if not GEMINI_API_KEY:
        GEMINI_API_KEY = st.text_input("Gemini APIキー", type="password")

# =========================================================
# 各画面の描画関数定義 (New)
# =========================================================

def render_portal_page():
    """ポータル画面（ホーム）"""
    apply_portal_css()
    st.title(f"こんにちは、{student_name}さん！👋")
    
    # 簡易サマリ（DBから取得）
    # ※totalStudyMinutesはユーザー作成時/学習記録時に更新される想定
    user_doc = user_ref.get().to_dict()
    total_minutes = user_doc.get("totalStudyMinutes", 0)
    total_hours = total_minutes // 60
    
    st.info(f"📚 **累計学習時間**: {total_hours}時間 {total_minutes % 60}分")

    # ナビゲーションカード
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🤖 AIコーチ\n(チャット)", use_container_width=True):
            navigate_to("chat")
        if st.button("🏆 ランキング\n(みんなと競う)", use_container_width=True):
            navigate_to("ranking")
        if st.button("💬 掲示板\n(Q&A)", use_container_width=True):
            navigate_to("board")
            
    with col2:
        if st.button("📝 学習記録\n(時間を記録)", use_container_width=True):
            navigate_to("study_log")
        if st.button("🤝 バディ\n(友達と連携)", use_container_width=True):
            navigate_to("buddy")

def render_study_log_page():
    """学習記録画面"""
    st.title("📝 学習記録")
    st.write("今日の頑張りを記録しよう！")
    
    with st.form("study_log_form"):
        col1, col2 = st.columns(2)
        with col1:
            hours = st.selectbox("時間", list(range(0, 13)), index=0)
        with col2:
            minutes = st.selectbox("分", [0, 15, 30, 45], index=0)
            
        note = st.text_area("メモ (学習内容や感想)", placeholder="例: 三角関数の加法定理を覚えた！")
        submit = st.form_submit_button("記録する")
        
        if submit:
            if hours == 0 and minutes == 0:
                st.error("学習時間を入力してください")
            else:
                total_min = hours * 60 + minutes
                now = datetime.datetime.now()
                date_str = now.strftime('%Y-%m-%d')
                
                try:
                    # 1. サブコレクションに記録
                    user_ref.collection("study_logs").add({
                        "minutes": total_min,
                        "date": date_str,
                        "timestamp": firestore.SERVER_TIMESTAMP,
                        "note": note
                    })
                    
                    # 2. 累計時間を更新 (Atomic increment推奨だがここでは簡易的にget->update)
                    user_snap = user_ref.get()
                    current_total = user_snap.to_dict().get("totalStudyMinutes", 0)
                    user_ref.update({"totalStudyMinutes": current_total + total_min})
                    
                    st.success(f"{hours}時間{minutes}分の学習を記録しました！")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"記録エラー: {e}")

    st.markdown("### 📜 直近の履歴")
    logs_stream = user_ref.collection("study_logs").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(5).stream()
    for log in logs_stream:
        data = log.to_dict()
        ts = data.get("timestamp")
        date_display = ts.strftime('%Y/%m/%d %H:%M') if ts else data.get("date")
        m_val = data.get("minutes", 0)
        h = m_val // 60
        m = m_val % 60
        st.markdown(f"**{date_display}** - {h}時間{m}分 : {data.get('note', '')}")

def render_ranking_page():
    """ランキング画面"""
    st.title("🏆 学習時間ランキング")
    
    # タブ切り替え
    tab1, tab2, tab3 = st.tabs(["今日", "今週", "今月"])
    
    # ※Firestoreでの複雑な集計・ソートはインデックスが必要なため、
    # Phase 1では「全ユーザー取得 -> Python側でフィルタリング」で実装（テスター50名規模なら許容）
    
    try:
        all_users = db.collection("users").stream()
        ranking_data = []
        
        # ユーザー情報を先にマッピング
        user_map = {} # uid -> {name, isAnonymousRanking, ...}
        for u in all_users:
            d = u.to_dict()
            user_map[u.id] = d
            
        # 今日の日付
        now = datetime.datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        
        # NOTE: ログごとの集計をするには全ログなめる必要がありコスト高。
        # Phase 1 の要件定義書の「累計時間」ベースと「期間別」の兼ね合いが難しいが、
        # ここでは要件定義書の usersコレクションの totalStudyMinutes（累計） を表示する形と、
        # 期間別は本来 study_logs 集計が必要だが、今回は実装の簡易化のため
        # 「累計ランキング」のみを正しく表示し、期間別はダミー（または将来実装）とするか、
        # 正直に「現在は累計のみ対応」とする。
        # -> 要件定義に従い、タブは出すが、実装は累計（Total）をベースにする暫定対応とします。
        
        st.info("※ 現在は「累計学習時間」でのランキングを表示しています。")

        # 累計ランキング作成
        ranking_list = []
        for uid, info in user_map.items():
            t_min = info.get("totalStudyMinutes", 0)
            if t_min > 0:
                # 匿名処理
                disp_name = info.get("name", "名無し")
                if info.get("isAnonymousRanking", False):
                    # 自分自身ならわかるようにする、などの配慮も可だが、要件通り置換
                    disp_name = "匿名ユーザー"
                    if uid == user_id:
                        disp_name = "匿名ユーザー (あなた)"
                
                ranking_list.append({"name": disp_name, "minutes": t_min})
        
        # ソート
        ranking_list.sort(key=lambda x: x["minutes"], reverse=True)
        
        with tab1: # 今日（今回は累計を表示）
            st.table(ranking_list[:20]) # Top 20
        with tab2: # 今週
            st.write("（集計中...）")
        with tab3: # 今月
            st.write("（集計中...）")
            
    except Exception as e:
        st.error(f"ランキング取得エラー: {e}")

def render_board_page():
    """掲示板画面"""
    st.title("💬 コミュニティ掲示板")
    
    with st.expander("📝 新規投稿を作成"):
        with st.form("new_post_form"):
            title = st.text_input("タイトル")
            body = st.text_area("本文")
            is_anon = st.checkbox("匿名で投稿する")
            img_file = st.file_uploader("画像 (任意)", type=["png", "jpg", "jpeg"], key="board_upload")
            
            submit_post = st.form_submit_button("投稿する")
            
            if submit_post and title and body:
                try:
                    image_url = None
                    if img_file:
                        # Firebase Storageへのアップロード
                        # バケット取得 (Init時に設定済みと仮定)
                        bucket = storage.bucket()
                        blob_name = f"posts/{user_id}/{uuid.uuid4()}_{img_file.name}"
                        blob = bucket.blob(blob_name)
                        
                        # Content-Type設定
                        blob.upload_from_file(img_file, content_type=img_file.type)
                        
                        # 公開URL取得 (make_public()が必要だが権限エラーの可能性あり。signed URL推奨だが簡略化)
                        # Phase 1のStreamlit Cloud環境では権限周りが複雑なため、
                        # 今回は要件を満たすコードを書くが、実動作にはFirebase側のルール設定が必要
                        blob.make_public() 
                        image_url = blob.public_url

                    db.collection("posts").add({
                        "authorId": user_id,
                        "authorName": student_name,
                        "isAnonymous": is_anon,
                        "title": title,
                        "body": body,
                        "imageUrl": image_url,
                        "createdAt": firestore.SERVER_TIMESTAMP
                    })
                    st.success("投稿しました！")
                    st.rerun()
                except Exception as e:
                    st.error(f"投稿エラー: {e}")
                    st.caption("※Cloud Storageの設定を確認してください")

    st.markdown("---")
    # 投稿一覧表示
    posts_stream = db.collection("posts").order_by("createdAt", direction=firestore.Query.DESCENDING).limit(20).stream()
    
    for doc in posts_stream:
        p = doc.to_dict()
        with st.container():
            # ヘッダー
            p_name = p.get("authorName", "名無し")
            if p.get("isAnonymous", False):
                p_name = "匿名ユーザー"
            
            ts = p.get("createdAt")
            date_str = ts.strftime('%Y/%m/%d %H:%M') if ts else ""
            
            st.markdown(f"**{p.get('title')}**")
            st.caption(f"by {p_name} | {date_str}")
            st.write(p.get("body"))
            
            if p.get("imageUrl"):
                st.image(p.get("imageUrl"), use_column_width=True)
            
            st.markdown("---")

def render_buddy_page():
    st.title("🤝 バディ機能")
    st.info("開発中：招待コードを使って友達とリンクしよう！")
    st.text_input("招待コードを入力")
    st.button("連携する")

def render_chat_page():
    """既存のチャット画面ロジック"""
    apply_chat_css() # CSS適用
    
    st.title("🤖 AI数学コーチ")
    st.caption("教科書の内容を「完璧」に理解しよう。答えは教えません、一緒に解きます。")

    if not st.session_state.messages_loaded:
        history_ref = user_ref.collection("history").order_by("timestamp")
        docs = history_ref.stream()
        loaded_msgs = []
        for doc in docs:
            loaded_msgs.append(doc.to_dict())
        st.session_state.messages = loaded_msgs
        st.session_state.messages_loaded = True

    chat_log_container = st.container()

    with chat_log_container:
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
    生徒の名前は「{student_name}」さんです。

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
    2. **現状分析**: まず、生徒が質問を見て、「どこまで分かっていて、どこで詰まっているか」を特定してください。
    3. **問いかけ**: 生徒が次に進むための「小さなヒント」や「問いかけ」を投げかけてください。
    4. **アウトプットの要求**: 一方的に解説せず、必ず生徒に考えさせ、返答させてください。
    5. **数式**: 必要であればLaTeX形式（$マーク）を使ってきれいに表示してください。
    """

    # --- 10. AI応答ロジック ---
    with st.form(key="chat_form", clear_on_submit=True):
        col1, col2, col3 = st.columns([0.8, 5, 1], gap="small")
        with col1:
            # keyを追加して他画面との競合回避
            uploaded_file = st.file_uploader(" ", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed", key="chat_uploader")
        with col2:
            user_prompt = st.text_area("質問", placeholder="質問を入力...", height=68, label_visibility="collapsed")
        with col3:
            st.write("") 
            submitted = st.form_submit_button("送信")

        if submitted:
            if not user_prompt and not uploaded_file:
                st.warning("質問か画像を入力してください")
            elif not GEMINI_API_KEY:
                st.warning("Gemini APIキーが設定されていません。")
            else:
                upload_img_obj = None
                user_msg_content = user_prompt
                if uploaded_file:
                    try:
                        upload_img_obj = Image.open(uploaded_file)
                        user_msg_content += "\n\n(※画像を送信しました)"
                    except Exception:
                        st.error("画像エラー")

                st.session_state.messages.append({"role": "user", "content": user_msg_content})
                
                user_ref.collection("history").add({
                    "role": "user",
                    "content": user_msg_content,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                user_ref.collection("full_conversation_logs").add({
                    "role": "user",
                    "content": user_msg_content,
                    "timestamp": firestore.SERVER_TIMESTAMP,
                    "log_type": "sequential"
                })

                with chat_log_container:
                    with st.chat_message("user"):
                        st.markdown(user_msg_content)
                        if upload_img_obj:
                            st.image(upload_img_obj, width=200)

                    with st.spinner("AIコーチが思考中..."):
                        genai.configure(api_key=GEMINI_API_KEY)
                        history_for_ai = []
                        MAX_HISTORY_MESSAGES = 20
                        limited_messages = st.session_state.messages[:-1][-MAX_HISTORY_MESSAGES:]
                        
                        for m in limited_messages: 
                            content_str = ""
                            if isinstance(m["content"], dict):
                                content_str = m["content"].get("text", str(m["content"]))
                            else:
                                content_str = str(m["content"])
                            history_for_ai.append({"role": m["role"], "parts": [content_str]})

                        # モデルリスト（最新優先）
                        PRIORITY_MODELS = [
                            "gemini-3-flash-preview",
                            "gemini-2.0-flash-exp",
                            "gemini-1.5-flash",
                            "gemini-3-pro-preview",
                            "gemini-1.5-pro",
                        ]
                        
                        ai_text = ""
                        success_model = None
                        error_details = []
                        
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
                                log_message = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ⚠️ {model_name} エラー: {e}"
                                error_details.append(log_message)
                                st.session_state.debug_logs.append(log_message)
                                continue
                    
                    if success_model:
                        st.session_state.last_used_model = success_model

                        if success_model != PRIORITY_MODELS[0]:
                            with st.chat_message("assistant"):
                                    st.warning(f"Note: 最新モデル ({PRIORITY_MODELS[0]}) が利用できなかったため、{success_model} を使用しました。")

                        st.session_state.messages.append({"role": "model", "content": ai_text})
                        
                        user_ref.collection("history").add({
                            "role": "model",
                            "content": ai_text,
                            "timestamp": firestore.SERVER_TIMESTAMP
                        })
                        user_ref.collection("full_conversation_logs").add({
                            "role": "model",
                            "content": ai_text,
                            "timestamp": firestore.SERVER_TIMESTAMP,
                            "log_type": "sequential",
                            "model": success_model
                        })
                        
                        with st.chat_message("model"):
                            st.markdown(ai_text)
                        time.sleep(0.1) 
                        st.rerun()
                    else:
                        st.error(f"❌ エラーが発生しました。\n詳細: {error_details}")

# =========================================================
# 8. メイン画面ルーティング (Main Entry Point)
# =========================================================

# ページの状態によって表示する関数を切り替え
current_page = st.session_state.current_page

if current_page == "portal":
    render_portal_page()
elif current_page == "chat":
    render_chat_page()
elif current_page == "study_log":
    render_study_log_page()
elif current_page == "ranking":
    render_ranking_page()
elif current_page == "board":
    render_board_page()
elif current_page == "buddy":
    render_buddy_page()
else:
    # フォールバック
    render_portal_page()
