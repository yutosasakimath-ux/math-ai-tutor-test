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

# ★JST（日本時間）の定義
JST = datetime.timezone(datetime.timedelta(hours=9))

# ★★★ UI設定：チャット画面専用CSS ★★★
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
    # 日付もJST対応
    today_str = datetime.datetime.now(JST).strftime('%Y/%m/%d')
    p.drawString(20 * mm, height - 30 * mm, f"作成日: {today_str}")
    
    # 本文設定
    p.setFont(font_name, 11)
    
    lines = text_content.split('\n')
    # 文字数設定（余裕を持って35文字）
    max_char_per_line = 35 
    line_height = 6 * mm
    y_position = height - 50 * mm
    
    for line in lines:
        while True:
            chunk = line[:max_char_per_line]
            line = line[max_char_per_line:]
            
            p.drawString(20 * mm, y_position, chunk)
            y_position -= line_height
            
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
if not firebase_admin._apps:
    try:
        storage_bucket = None
        if "firebase" in st.secrets and "storage_bucket" in st.secrets["firebase"]:
            storage_bucket = st.secrets["firebase"]["storage_bucket"]
        
        if "firebase" in st.secrets:
            key_dict = dict(st.secrets["firebase"])
            if "\\n" in key_dict["private_key"]:
                key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(key_dict)
            
            options = {}
            if storage_bucket:
                options['storageBucket'] = storage_bucket
            
            firebase_admin.initialize_app(cred, options)
        else:
            if os.path.exists("service_account.json"):
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

if "messages" not in st.session_state:
    st.session_state.messages = []
if "messages_loaded" not in st.session_state:
    st.session_state.messages_loaded = False
    
if "debug_logs" not in st.session_state:
    st.session_state.debug_logs = []

# 画面遷移管理
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
                                    "totalStudyMinutes": 0,
                                    "isAnonymousRanking": False
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

# --- 6. サイドバー (機能改修版) ---
with st.sidebar:
    st.header(f"ようこそ、{student_name}さん")
    
    # ナビゲーションメニュー
    st.caption("ナビゲーション")
    if st.button("🏠 ホーム (ポータル)", use_container_width=True):
        navigate_to("portal")
    
    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        if st.button("🤖 AIコーチ", use_container_width=True):
            navigate_to("chat")
        if st.button("🏆 ランキング", use_container_width=True):
            navigate_to("ranking")
    with col_nav2:
        if st.button("📝 学習記録", use_container_width=True):
            navigate_to("study_log")
        if st.button("💬 掲示板", use_container_width=True):
            navigate_to("board")
    
    st.markdown("---")

    # AIコーチ画面の場合のみ「会話履歴削除」を表示
    if st.session_state.current_page == "chat":
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
        st.markdown("---")

    if st.button("ログアウト", use_container_width=True):
        st.session_state.user_info = None
        st.session_state.messages = []
        st.session_state.messages_loaded = False
        st.session_state.debug_logs = []
        keys_to_remove = ["user_name", "current_page", "is_anon_ranking"]
        for k in keys_to_remove:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

# =========================================================
# 各画面の描画関数定義
# =========================================================

def render_portal_page():
    """ポータル画面（ホーム）"""
    apply_portal_css()
    st.title(f"こんにちは、{student_name}さん！👋")
    
    # 簡易サマリ
    user_doc = user_ref.get().to_dict()
    total_minutes = user_doc.get("totalStudyMinutes", 0)
    total_hours = total_minutes // 60
    
    st.info(f"📚 **累計学習時間**: {total_hours}時間 {total_minutes % 60}分")

    # メインナビゲーション
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
    
    st.markdown("---")
    
    # 設定・サポート・管理者メニューを集約
    with st.expander("⚙️ 設定・サポート"):
        st.markdown("### 👤 プロフィール設定")
        
        # 名前変更
        new_name = st.text_input("表示名（AIが呼びかける名前）", value=student_name, key="setting_name")
        if new_name != student_name:
            if st.button("名前を更新"):
                user_ref.update({"name": new_name})
                st.session_state.user_name = new_name
                st.success("名前を更新しました")
                time.sleep(1)
                st.rerun()
        
        # ランキング匿名設定
        if "is_anon_ranking" not in st.session_state:
            st.session_state.is_anon_ranking = user_doc.get("isAnonymousRanking", False)
        
        is_anon = st.checkbox("ランキングで匿名にする", value=st.session_state.is_anon_ranking, key="setting_anon")
        if is_anon != st.session_state.is_anon_ranking:
            user_ref.update({"isAnonymousRanking": is_anon})
            st.session_state.is_anon_ranking = is_anon
            st.success("匿名設定を更新しました")
            
        st.markdown("---")
        st.markdown("### 📢 ご意見・不具合報告")
        with st.form("feedback_form_portal", clear_on_submit=True):
            feedback_content = st.text_area("感想、バグ、要望など", placeholder="例：〇〇の機能が欲しいです")
            feedback_submit = st.form_submit_button("送信")
            if feedback_submit and feedback_content:
                db.collection("feedback").add({
                    "user_id": user_id,
                    "email": user_email,
                    "content": feedback_content,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                st.success("送信しました。ありがとうございます！")
        
        st.markdown("---")
        st.markdown("### 🛡️ 管理者メニュー")
        report_admin_pass = st.text_input("管理者パスワード", type="password", key="portal_admin_pass")
        
        if ADMIN_KEY and report_admin_pass == ADMIN_KEY:
            st.info("🔓 管理者モード")

            st.markdown("#### 🤖 モデル稼働状況")
            st.info(f"**最後に使用したモデル:** `{st.session_state.last_used_model}`")
            
            # --- 利用可能なモデル一覧 ---
            if st.button("📡 利用可能なモデル一覧を取得", key="admin_model_list"):
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
                        st.code("\n".join(available_models))
                    except Exception as e:
                        st.error(f"取得エラー: {e}")

            # --- デバッグログ ---
            st.markdown("#### 🛠 デバッグログ")
            if st.session_state.debug_logs:
                for i, log in enumerate(reversed(st.session_state.debug_logs)):
                    st.code(log, language="text")
                if st.button("ログ消去", key="admin_clear_log"):
                    st.session_state.debug_logs = []
                    st.rerun()
            else:
                st.caption("現在エラーログはありません")
            
            # --- コスト分析 ---
            st.markdown("#### 💰 コスト分析")
            if st.button("📊 ログからコストを試算", key="admin_cost_calc"):
                with st.spinner("集計中..."):
                    try:
                        INPUT_PRICE_PER_M = 0.50 
                        OUTPUT_PRICE_PER_M = 3.00
                        USD_JPY = 155.5
                        SYSTEM_PROMPT_EST_LEN = 700 
                        
                        logs_ref = user_ref.collection("full_conversation_logs").order_by("timestamp")
                        docs = logs_ref.stream()
                        logs = [d.to_dict() for d in docs]
                        
                        if logs:
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
                            total_jpy = (input_cost_usd + output_cost_usd) * USD_JPY
                            st.metric("推定総コスト", f"¥ {total_jpy:.2f}")
                        else:
                            st.warning("ログなし")
                    except Exception as e:
                        st.error(f"計算エラー: {e}")

            # --- レポート作成 ---
            st.markdown("#### 📝 学習まとめレポート作成")
            if st.button("📝 レポートを作成してPDFを開く", key="admin_report_gen"):
                st.info("※チャット画面のデバッグメニューと同じロジックがここに実装されます（今回は省略）")

def render_study_log_page():
    """学習記録画面（修正・削除機能付き）"""
    st.title("📝 学習記録")
    st.write("今日の頑張りを記録しよう！")
    
    # ★変更: ドロップダウンから整数入力へ
    with st.form("study_log_form"):
        col1, col2 = st.columns(2)
        with col1:
            hours = st.number_input("時間 (0-24)", min_value=0, max_value=24, value=0, step=1)
        with col2:
            minutes = st.number_input("分 (0-59)", min_value=0, max_value=59, value=0, step=1)
            
        note = st.text_area("メモ (学習内容や感想)", placeholder="例: 三角関数の加法定理を覚えた！")
        submit = st.form_submit_button("記録する")
        
        if submit:
            if hours == 0 and minutes == 0:
                st.error("学習時間を入力してください")
            else:
                total_min = hours * 60 + minutes
                now_jst = datetime.datetime.now(JST)
                date_str = now_jst.strftime('%Y-%m-%d')
                
                try:
                    user_ref.collection("study_logs").add({
                        "minutes": total_min,
                        "date": date_str,
                        "timestamp": firestore.SERVER_TIMESTAMP,
                        "note": note
                    })
                    
                    user_snap = user_ref.get()
                    current_total = user_snap.to_dict().get("totalStudyMinutes", 0)
                    user_ref.update({"totalStudyMinutes": current_total + total_min})
                    
                    st.success(f"{hours}時間{minutes}分の学習を記録しました！")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"記録エラー: {e}")

    st.markdown("### 📜 直近の履歴（編集・削除）")
    # 履歴を取得（IDが必要なのでstreamで取得し、IDも保持）
    logs_stream = user_ref.collection("study_logs").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(10).stream()
    
    for log in logs_stream:
        doc_id = log.id
        data = log.to_dict()
        ts = data.get("timestamp")
        
        if ts:
            ts_jst = ts.astimezone(JST)
            date_display = ts_jst.strftime('%Y/%m/%d %H:%M')
        else:
            date_display = data.get("date")
            
        m_val = data.get("minutes", 0)
        h = m_val // 60
        m = m_val % 60
        
        # ★追加: Expanderによる修正・削除UI
        with st.expander(f"{date_display} - {h}時間{m}分 : {data.get('note', '')[:10]}..."):
            with st.form(f"edit_log_{doc_id}"):
                st.caption("内容を修正")
                new_h = st.number_input("時間", min_value=0, max_value=24, value=h, key=f"h_{doc_id}")
                new_m = st.number_input("分", min_value=0, max_value=59, value=m, key=f"m_{doc_id}")
                new_note = st.text_area("メモ", value=data.get('note', ''), key=f"n_{doc_id}")
                
                col_upd, col_del = st.columns(2)
                with col_upd:
                    if st.form_submit_button("更新する"):
                        try:
                            new_total_min = new_h * 60 + new_m
                            diff = new_total_min - m_val
                            
                            # ログ更新
                            user_ref.collection("study_logs").document(doc_id).update({
                                "minutes": new_total_min,
                                "note": new_note
                            })
                            # 累計時間更新
                            u_snap = user_ref.get()
                            curr_tot = u_snap.to_dict().get("totalStudyMinutes", 0)
                            user_ref.update({"totalStudyMinutes": max(0, curr_tot + diff)})
                            
                            st.success("更新しました！")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"更新エラー: {e}")

                with col_del:
                    if st.form_submit_button("削除する", type="primary"):
                        try:
                            # ログ削除
                            user_ref.collection("study_logs").document(doc_id).delete()
                            # 累計時間減算
                            u_snap = user_ref.get()
                            curr_tot = u_snap.to_dict().get("totalStudyMinutes", 0)
                            user_ref.update({"totalStudyMinutes": max(0, curr_tot - m_val)})
                            
                            st.success("削除しました")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"削除エラー: {e}")

def render_ranking_page():
    """ランキング画面 (期間集計対応)"""
    st.title("🏆 学習時間ランキング")
    
    tab1, tab2, tab3 = st.tabs(["累計", "今週", "今月"])
    
    all_users = list(db.collection("users").stream())
    user_map = {}
    for u in all_users:
        user_map[u.id] = u.to_dict()

    def get_anonymous_name(uid, original_name, is_anon_flag):
        if is_anon_flag:
            if uid == user_id:
                return "匿名ユーザー (あなた)"
            return "匿名ユーザー"
        return original_name

    with tab1:
        ranking_list = []
        for uid, info in user_map.items():
            t_min = info.get("totalStudyMinutes", 0)
            if t_min > 0:
                disp_name = get_anonymous_name(uid, info.get("name", "名無し"), info.get("isAnonymousRanking", False))
                ranking_list.append({"name": disp_name, "minutes": t_min})
        
        ranking_list.sort(key=lambda x: x["minutes"], reverse=True)
        st.write("#### 👑 累計学習時間")
        st.table(ranking_list[:20])

    def aggregate_ranking(start_dt):
        try:
            query = db.collection_group("study_logs").where("timestamp", ">=", start_dt)
            docs = query.stream()
            user_stats = {} 
            for d in docs:
                parent_ref = d.reference.parent.parent
                if parent_ref:
                    uid = parent_ref.id
                    minutes = d.to_dict().get("minutes", 0)
                    user_stats[uid] = user_stats.get(uid, 0) + minutes
            
            ranking_period = []
            for uid, mins in user_stats.items():
                if uid in user_map:
                    info = user_map[uid]
                    disp_name = get_anonymous_name(uid, info.get("name", "名無し"), info.get("isAnonymousRanking", False))
                    ranking_period.append({"name": disp_name, "minutes": mins})
            
            ranking_period.sort(key=lambda x: x["minutes"], reverse=True)
            return ranking_period

        except Exception as e:
            if "indexes?create_composite=" in str(e):
                st.error("⚠️ 管理者設定が必要です：Firestoreインデックスを作成してください。")
            else:
                st.error(f"集計エラー: {e}")
            return []

    with tab2:
        now_jst = datetime.datetime.now(JST)
        start_of_week = now_jst - datetime.timedelta(days=now_jst.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        st.write(f"集計期間: {start_of_week.strftime('%m/%d')} 〜")
        ranking_weekly = aggregate_ranking(start_of_week)
        if ranking_weekly:
            st.table(ranking_weekly[:20])
        elif not ranking_weekly:
             st.info("データがありません")

    with tab3:
        now_jst = datetime.datetime.now(JST)
        start_of_month = now_jst.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        st.write(f"集計期間: {start_of_month.strftime('%m/%d')} 〜")
        ranking_monthly = aggregate_ranking(start_of_month)
        if ranking_monthly:
            st.table(ranking_monthly[:20])
        elif not ranking_monthly:
            st.info("データがありません")

def render_board_page():
    """掲示板画面 (返信機能付き)"""
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
                        bucket = storage.bucket()
                        blob_name = f"posts/{user_id}/{uuid.uuid4()}_{img_file.name}"
                        blob = bucket.blob(blob_name)
                        blob.upload_from_file(img_file, content_type=img_file.type)
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

    st.markdown("---")
    
    posts_stream = db.collection("posts").order_by("createdAt", direction=firestore.Query.DESCENDING).limit(20).stream()
    
    for doc in posts_stream:
        p = doc.to_dict()
        post_id = doc.id
        
        with st.container():
            p_name = p.get("authorName", "名無し")
            if p.get("isAnonymous", False):
                p_name = "匿名ユーザー"
            
            ts = p.get("createdAt")
            if ts:
                ts_jst = ts.astimezone(JST)
                date_str = ts_jst.strftime('%Y/%m/%d %H:%M')
            else:
                date_str = ""
            
            st.markdown(f"#### {p.get('title')}")
            st.caption(f"by {p_name} | {date_str}")
            st.write(p.get("body"))
            
            if p.get("imageUrl"):
                st.image(p.get("imageUrl"), use_column_width=True)
            
            with st.expander("💬 返信を見る / 書く"):
                comments_ref = db.collection("posts").document(post_id).collection("comments")
                comments = comments_ref.order_by("timestamp").stream()
                
                for c in comments:
                    c_data = c.to_dict()
                    c_name = c_data.get("authorName", "名無し")
                    if c_data.get("isAnonymous", False):
                        c_name = "匿名ユーザー"
                    c_body = c_data.get("body", "")
                    c_ts = c_data.get("timestamp")
                    c_date = c_ts.astimezone(JST).strftime('%m/%d %H:%M') if c_ts else ""
                    
                    st.markdown(f"""
                    <div style="background-color:#f9f9f9; padding:8px; border-radius:5px; margin-bottom:5px;">
                        <small><b>{c_name}</b> ({c_date})</small><br>
                        {c_body}
                    </div>
                    """, unsafe_allow_html=True)
                
                # ★修正: clear_on_submit=Trueを追加
                with st.form(f"comment_form_{post_id}", clear_on_submit=True):
                    c_text = st.text_input("返信コメント", key=f"input_{post_id}")
                    c_anon = st.checkbox("匿名", key=f"anon_{post_id}")
                    c_submit = st.form_submit_button("送信")
                    
                    if c_submit and c_text:
                        comments_ref.add({
                            "authorId": user_id,
                            "authorName": student_name,
                            "isAnonymous": c_anon,
                            "body": c_text,
                            "timestamp": firestore.SERVER_TIMESTAMP
                        })
                        st.success("返信しました")
                        time.sleep(0.5)
                        st.rerun()

            st.markdown("---")

def render_buddy_page():
    """バディ機能（バディコード＆相互リンク実装）"""
    st.title("🤝 バディ機能")
    st.write("友達とバディコードを交換して、チームを結成しよう！")

    # 1. 自分のバディコード生成・取得
    my_doc = user_ref.get().to_dict()
    my_buddy_code = my_doc.get("buddy_code")
    
    if not my_buddy_code:
        # コード生成 (UUIDの先頭6文字を大文字で)
        generated_code = str(uuid.uuid4())[:6].upper()
        user_ref.update({"buddy_code": generated_code})
        my_buddy_code = generated_code
        st.rerun() # リロードして表示
    
    st.info(f"🔑 **あなたのバディコード:** `{my_buddy_code}`")
    st.caption("このコードを友達に教えてあげてください。")

    st.markdown("---")

    # 2. 相手のコード入力
    with st.form("buddy_add_form", clear_on_submit=True):
        input_code = st.text_input("友達のバディコードを入力")
        submit_code = st.form_submit_button("連携する")
        
        if submit_code and input_code:
            input_code = input_code.strip().upper()
            if input_code == my_buddy_code:
                st.warning("自分自身のコードは登録できません。")
            else:
                # コードからユーザーを検索
                target_users = db.collection("users").where("buddy_code", "==", input_code).stream()
                target_user = next(target_users, None)
                
                if target_user:
                    target_uid = target_user.id
                    target_data = target_user.to_dict()
                    target_name = target_data.get("name", "名無し")
                    
                    # 自分のbuddyIdsに追加
                    current_buddies = my_doc.get("buddyIds", [])
                    if target_uid not in current_buddies:
                        current_buddies.append(target_uid)
                        user_ref.update({"buddyIds": current_buddies})
                        st.success(f"「{target_name}」さんをバディリストに追加しました！")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.info(f"「{target_name}」さんは既にリストにいます。")
                else:
                    st.error("そのコードのユーザーは見つかりませんでした。")

    st.markdown("### 👥 バディリスト")
    
    my_buddy_ids = my_doc.get("buddyIds", [])
    
    if not my_buddy_ids:
        st.write("まだバディはいません。")
    else:
        for b_uid in my_buddy_ids:
            # 相手の情報を取得
            b_doc_ref = db.collection("users").document(b_uid)
            b_doc = b_doc_ref.get()
            if b_doc.exists:
                b_data = b_doc.to_dict()
                b_name = b_data.get("name", "名無し")
                
                # 相互フォロー確認
                b_buddy_ids = b_data.get("buddyIds", [])
                is_mutual = user_id in b_buddy_ids
                
                with st.container():
                    col_icon, col_info = st.columns([1, 6])
                    with col_icon:
                        if is_mutual:
                            st.markdown("🤝") # チーム結成
                        else:
                            st.markdown("➡️") # 片思い
                    with col_info:
                        if is_mutual:
                            st.write(f"**{b_name}** (チーム結成済！🎉)")
                        else:
                            st.write(f"**{b_name}** (相手の承認待ち)")
            else:
                st.write("退会したユーザー")

def render_chat_page():
    """AIコーチ画面（既存ロジック）"""
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

    with st.form(key="chat_form", clear_on_submit=True):
        col1, col2, col3 = st.columns([0.8, 5, 1], gap="small")
        with col1:
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
# 8. メイン画面ルーティング
# =========================================================

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
    render_portal_page()
