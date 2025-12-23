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
import pandas as pd # ★追加: ランキング表示の整形用

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

# 【追加】23日verのログインロジックで必要なため追加
if "ADMIN_EMAIL" in st.secrets:
    ADMIN_EMAIL = st.secrets["ADMIN_EMAIL"]
else:
    ADMIN_EMAIL = None 

# 【修正】ハードコードされたデフォルトキーを削除
if "FIREBASE_WEB_API_KEY" in st.secrets:
    FIREBASE_WEB_API_KEY = st.secrets["FIREBASE_WEB_API_KEY"]
else:
    FIREBASE_WEB_API_KEY = "" # 空文字に変更してリスク回避

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

# 【追加】23日verのログインロジックとの互換性のため追加
if "user_role" not in st.session_state:
    st.session_state.user_role = "student" 
if "managed_team_id" not in st.session_state:
    st.session_state.managed_team_id = None 
if "managed_team_name" not in st.session_state:
    st.session_state.managed_team_name = None

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

# --- 4. UI: ログイン画面 (23日verより移植・調整) ---
if st.session_state.user_info is None:
    st.title("🎓 AI数学コーチ：ログイン")
    
    if not FIREBASE_WEB_API_KEY:
        st.error("⚠️ Web APIキーが設定されていません。Streamlit Secretsを確認してください。")
        st.stop()

    # ★修正: タブ名を変更し、先生ログインを排除
    tab_student, tab_admin = st.tabs(["🧑‍🎓 生徒ログイン", "🛡️ 管理者ログイン"])

    with tab_student:
        st.caption("生徒のみなさんはこちらからログインしてください。")
        with st.form("student_login_form"):
            email = st.text_input("メールアドレス", key="s_email")
            password = st.text_input("パスワード", type="password", key="s_pass")
            submit = st.form_submit_button("ログイン")
            
            if submit:
                resp = sign_in_with_email(email, password)
                if "error" in resp:
                    st.error(f"ログイン失敗: {resp['error']['message']}")
                else:
                    st.session_state.user_info = {"uid": resp["localId"], "email": resp["email"]}
                    st.session_state.user_role = "student"
                    st.success("ログインしました！")
                    time.sleep(0.5)
                    st.rerun()

    with tab_admin:
        # ★修正: 管理者専用の表記に変更
        st.caption("システム管理者専用です。")
        with st.form("admin_login_form"):
            a_email = st.text_input("メールアドレス", key="a_email")
            a_password = st.text_input("パスワード", type="password", key="a_pass")
            
            st.markdown("---")
            # ★修正: 教師用チームコードの入力を示唆する文言を削除
            auth_code = st.text_input("管理者パスワード", type="password", help="管理者キーを入力してください。")
            
            submit_admin = st.form_submit_button("管理者としてログイン")
            
            if submit_admin:
                resp = sign_in_with_email(a_email, a_password)
                if "error" in resp:
                    st.error(f"認証失敗: {resp['error']['message']}")
                else:
                    uid = resp["localId"]
                    user_email_val = resp["email"]
                    
                    login_success = False
                    
                    # ★修正: 教師ログイン(チームコード判定)を全削除し、管理者判定のみ残す
                    if ADMIN_KEY and auth_code == ADMIN_KEY:
                        if ADMIN_EMAIL and user_email_val == ADMIN_EMAIL:
                            st.session_state.user_info = {"uid": uid, "email": user_email_val}
                            st.session_state.user_role = "global_admin"
                            login_success = True
                            st.success("全体管理者として認証しました")
                        else:
                            st.error("⛔️ 認証に失敗しました。（管理者メールアドレスと一致しません）")
                    else:
                        st.error("⛔️ 認証に失敗しました。（管理者パスワードが違います）")
                    
                    if login_success:
                        # 22日verには管理者専用画面がないため、通常のアプリ画面へ遷移させる
                        st.info("※22日verの画面へ移動します")
                        time.sleep(0.5)
                        st.rerun()
        
        # ★削除: ログイン画面での新規登録機能は削除し、ログイン後の管理者メニューへ移動

    st.stop()

# =========================================================
# ログイン済みユーザーの世界
# =========================================================

user_id = st.session_state.user_info["uid"]
user_email = st.session_state.user_info["email"]
user_role = st.session_state.get("user_role", "student") # ロール取得

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
        # ★変更: バディ -> チーム
        if st.button("👥 チーム", use_container_width=True):
            navigate_to("team")
    
    if st.button("💬 掲示板", use_container_width=True):
            navigate_to("board")

    # ★追加: 管理者の場合のみ表示する専用メニューボタン
    if user_role == "global_admin":
        st.markdown("---")
        st.caption("管理者機能")
        if st.button("🛠 管理者メニュー", use_container_width=True, type="primary"):
            navigate_to("admin_menu")
    
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
        keys_to_remove = ["user_name", "current_page", "is_anon_ranking", "user_role"]
        for k in keys_to_remove:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

# =========================================================
# 各画面の描画関数定義
# =========================================================

# ★新規追加: 管理者専用メニュー画面
def render_admin_menu_page():
    """管理者専用の機能集約画面"""
    # セキュリティチェック: 管理者権限がない場合はポータルへ強制送還
    if st.session_state.get("user_role") != "global_admin":
        st.error("権限がありません。")
        time.sleep(1)
        navigate_to("portal")
        return

    st.title("🛠 システム管理者メニュー")
    st.info(f"ログイン中: {st.session_state.user_info.get('email')}")

    # 機能ごとにタブで整理
    tab1, tab2, tab3 = st.tabs(["📊 ダッシュボード", "👤 ユーザー管理", "⚙️ システム設定"])

    # --- タブ1: ダッシュボード (コスト・ログ) ---
    with tab1:
        st.subheader("💰 コスト分析 & ログ")
        
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### モデル稼働状況")
            st.info(f"**最後に使用したモデル:** `{st.session_state.last_used_model}`")
        
        with col2:
            st.markdown("#### コスト試算")
            if st.button("📊 直近1000件から試算", key="admin_cost_calc_tab"):
                with st.spinner("集計中..."):
                    try:
                        INPUT_PRICE_PER_M = 0.50 
                        OUTPUT_PRICE_PER_M = 3.00
                        USD_JPY = 155.5
                        SYSTEM_PROMPT_EST_LEN = 700 
                        
                        logs_ref = user_ref.collection("full_conversation_logs").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(1000)
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

        st.markdown("---")
        st.markdown("#### 🛠 デバッグログ")
        if st.session_state.debug_logs:
            with st.expander("ログを表示", expanded=True):
                for i, log in enumerate(reversed(st.session_state.debug_logs)):
                    st.code(log, language="text")
                if st.button("ログ消去", key="admin_clear_log_tab"):
                    st.session_state.debug_logs = []
                    st.rerun()
        else:
            st.caption("現在エラーログはありません")

    # --- タブ2: ユーザー管理 (新規作成) ---
    with tab2:
        st.subheader("👤 新規アカウント作成")
        st.caption("管理者として新規ユーザーを作成します。作成後、生徒にメールアドレスとパスワードを伝えてください。")
        
        with st.form("admin_signup_form_tab"):
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                new_name_input = st.text_input("生徒のお名前")
                new_email = st.text_input("新規メールアドレス")
            with col_u2:
                new_password = st.text_input("新規パスワード")
                # 必要であればここでロール選択などを追加可能
            
            submit_new = st.form_submit_button("アカウントを作成する")
            
            if submit_new:
                if not new_name_input or not new_email or not new_password:
                    st.error("全ての項目を入力してください")
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
                                "isAnonymousRanking": False,
                                "role": "student"
                            })
                            st.success(f"アカウント作成成功！\n名前: {new_name_input}\nEmail: {new_email}")
                        except Exception as e:
                            st.error(f"データベース登録エラー: {e}")

    # --- タブ3: システム設定 (モデル一覧など) ---
    with tab3:
        st.subheader("⚙️ システム設定 & ツール")
        
        if st.button("📡 利用可能なGeminiモデル一覧を取得", key="admin_model_list_tab"):
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
        
        st.markdown("#### 📝 学習まとめレポート作成 (デバッグ用)")
        if st.button("📝 レポートを作成してPDFを開く", key="admin_report_gen_tab"):
            st.info("※チャット画面のデバッグメニューと同じロジックがここに実装されます（今回は省略）")

    st.markdown("---")
    if st.button("← ポータルへ戻る"):
        navigate_to("portal")

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
        # ★変更: バディ -> チーム
        if st.button("👥 チーム\n(みんなで頑張る)", use_container_width=True):
            navigate_to("team")
        
        # ★追加: 管理者の場合、ここにボタンを追加
        if st.session_state.get("user_role") == "global_admin":
            if st.button("🛠 管理者メニュー\n(設定・管理)", use_container_width=True, type="primary"):
                navigate_to("admin_menu")
    
    st.markdown("---")
    
    # 設定・サポート
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
        
        # ★変更: パスワード入力式の「管理者メニュー」は削除しました。
        # 代わりに上部のボタンまたはサイドバーからアクセスします。

        # ★追加: 22日verにあった新規アカウント作成機能を復活
        st.markdown("---")
        with st.expander("管理者用：新規アカウント作成"):
            # 競合を避けるため key を変更
            admin_reg_pass = st.text_input("管理者パスワード", type="password", key="admin_reg_pass_tab")
            
            if ADMIN_KEY and admin_reg_pass == ADMIN_KEY:
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
                                        "isAnonymousRanking": False,
                                        "role": "student" # 23日verのロール管理に対応させるため明示的に追加
                                    })
                                    st.success(f"アカウント作成成功！\n名前: {new_name_input}\nEmail: {new_email}\nPass: {new_password}")
                                except Exception as e:
                                    st.error(f"データベース登録エラー: {e}")
            elif admin_reg_pass:
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
        # ★変更: バディ -> チーム
        if st.button("👥 チーム", use_container_width=True):
            navigate_to("team")
    
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
        # ★変更: バディ -> チーム
        if st.button("👥 チーム\n(みんなで頑張る)", use_container_width=True):
            navigate_to("team")
    
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
        
        # ★修正: 管理者メニューの表示制御を追加
        # 一般生徒には管理者メニューを表示せず、誤ってアクセスできないようにする
        is_admin = False
        # ロールによる判定（前回追加した仕組み）または Emailによる判定
        if st.session_state.get("user_role") == "global_admin":
            is_admin = True
        elif ADMIN_EMAIL and st.session_state.user_info.get("email") == ADMIN_EMAIL:
            is_admin = True
            
        if is_admin:
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
                            
                            # 【修正】limitを追加して、全件取得によるコスト爆発を防止
                            logs_ref = user_ref.collection("full_conversation_logs").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(1000)
                            docs = logs_ref.stream()
                            logs = [d.to_dict() for d in docs]
                            
                            if logs:
                                total_input_chars = 0
                                total_output_chars = 0
                                history_buffer_len = 0
                                # ログは降順で取得しているため、コスト計算用に逆順（古い順）にするのが正確だが、
                                # 簡易計算としてそのまま処理
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
                                st.metric("推定総コスト (直近1000件分)", f"¥ {total_jpy:.2f}")
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
                    
                    # 【修正】アトミックなインクリメント処理に変更（競合状態の防止）
                    user_ref.update({
                        "totalStudyMinutes": firestore.Increment(total_min)
                    })
                    
                    st.success(f"{hours}時間{minutes}分の学習を記録しました！")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"記録エラー: {e}")

    st.markdown("### 📜 直近の履歴（編集・削除）")
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
                            
                            user_ref.collection("study_logs").document(doc_id).update({
                                "minutes": new_total_min,
                                "note": new_note
                            })
                            # 【修正】アトミックな更新（差分を加算）
                            user_ref.update({
                                "totalStudyMinutes": firestore.Increment(diff)
                            })
                            
                            st.success("更新しました！")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"更新エラー: {e}")

                with col_del:
                    if st.form_submit_button("削除する", type="primary"):
                        try:
                            user_ref.collection("study_logs").document(doc_id).delete()
                            # 【修正】アトミックな更新（値を減算）
                            user_ref.update({
                                "totalStudyMinutes": firestore.Increment(-m_val)
                            })
                            
                            st.success("削除しました")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"削除エラー: {e}")

def render_ranking_page():
    """ランキング画面 (修正版: 個人/チーム × 日/週/月 の計6パターン + 1位始まり)"""
    st.title("🏆 学習時間ランキング")
    
    # タブを6つに分割
    tabs = st.tabs([
        "👤 個人(今日)", "👤 個人(今週)", "👤 個人(今月)",
        "👥 チーム(今日)", "👥 チーム(今週)", "👥 チーム(今月)"
    ])
    
    # 【修正】全ユーザー取得の廃止
    # 代わりに上位50名のみを取得するよう制限。
    # ※期間別集計に必要なuser_mapは、ランキング上位者のみに限定されるが、
    # パフォーマンスとのトレードオフとして許容する。
    top_users_stream = db.collection("users").order_by("totalStudyMinutes", direction=firestore.Query.DESCENDING).limit(50).stream()
    all_users = list(top_users_stream)
    
    user_map = {}
    for u in all_users:
        user_map[u.id] = u.to_dict()

    # チーム情報もlimitをかけるか検討すべきだが、チーム数はまだ少ないと仮定
    all_teams = list(db.collection("teams").limit(20).stream())
    team_list = [{"id": t.id, **t.to_dict()} for t in all_teams]

    def get_anonymous_name(uid, original_name, is_anon_flag):
        if is_anon_flag:
            if uid == user_id:
                return "匿名ユーザー (あなた)"
            return "匿名ユーザー"
        return original_name

    # --- 集計ロジック (期間指定でユーザーごとの学習時間を集計) ---
    def get_aggregated_stats(period_type):
        """
        指定期間のログを集計し、{uid: total_minutes} の辞書を返す
        period_type: 'day', 'week', 'month'
        """
        now_jst = datetime.datetime.now(JST)
        start_dt = None

        if period_type == 'day':
            start_dt = now_jst.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period_type == 'week':
            start_dt = (now_jst - datetime.timedelta(days=now_jst.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        elif period_type == 'month':
            start_dt = now_jst.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        if not start_dt:
            return {}

        try:
            # 【修正】データ量削減とパフォーマンス最適化
            # 1. select(['minutes']) で必要なフィールドのみ取得（転送量削減）
            # 2. limit(2000) で万が一の大量読み込みを防ぐ（上限設定）
            query = db.collection_group("study_logs")\
                      .where("timestamp", ">=", start_dt)\
                      .select(["minutes"])\
                      .limit(2000)
            
            docs = query.stream()
            
            stats = {}
            for d in docs:
                parent_ref = d.reference.parent.parent
                if parent_ref:
                    uid = parent_ref.id
                    # ユーザーマップにあるユーザー（＝上位ユーザー）のみ集計対象とする
                    # ※全件取得していないため、ランキング圏外のユーザーが集計されない可能性があるが、
                    # コスト削減のためにこの仕様とする。
                    if uid in user_map or uid == user_id: # 自分は必ず含める
                        minutes = d.to_dict().get("minutes", 0)
                        stats[uid] = stats.get(uid, 0) + minutes
            return stats

        except Exception as e:
            if "indexes?create_composite=" in str(e):
                st.error("⚠️ 管理者設定が必要です：Firestoreインデックスを作成してください。")
            else:
                st.error(f"集計エラー: {e}")
            return {}

    # --- ランキング表示用関数 ---
    def display_ranking_table(data_list, value_key="minutes"):
        """リストデータを受け取り、1位から順にテーブル表示"""
        if not data_list:
            st.info("データがありません")
            return

        # 時間の多い順にソート
        sorted_data = sorted(data_list, key=lambda x: x[value_key], reverse=True)
        
        # 表示用データ作成 (1位から開始)
        display_rows = []
        for i, item in enumerate(sorted_data):
            row = {
                "順位": f"{i + 1}位", 
                "名前": item["name"],
                "時間(分)": item[value_key]
            }
            if "count" in item:
                row["人数"] = item["count"]
            display_rows.append(row)
        
        # ★修正: Pandas DataFrameにしてインデックスを制御
        df = pd.DataFrame(display_rows)
        if not df.empty:
            # "順位"列をインデックスに設定することで、左端の0始まりの番号を"1位", "2位"...に置き換える
            st.table(df.set_index("順位"))

    # --- データの準備 ---
    stats_day = get_aggregated_stats('day')
    stats_week = get_aggregated_stats('week')
    stats_month = get_aggregated_stats('month')

    # --- 個人ランキング生成 ---
    def make_personal_list(stats):
        result = []
        for uid, mins in stats.items():
            # 自分がuser_mapにない場合（圏外）でも表示するために再取得の工夫が必要だが
            # ここではuser_mapにある場合のみ処理（簡易化）
            if uid in user_map:
                info = user_map[uid]
                disp_name = get_anonymous_name(uid, info.get("name", "名無し"), info.get("isAnonymousRanking", False))
                result.append({"name": disp_name, "minutes": mins})
            elif uid == user_id:
                 # 自分だけは特別に追加
                 disp_name = get_anonymous_name(uid, student_name, False) # 自分の画面では自分とわかるように
                 result.append({"name": disp_name + " (あなた)", "minutes": mins})

        return result

    # --- チームランキング生成 ---
    def make_team_list(stats):
        result = []
        for t in team_list:
            team_id = t["id"]
            members_in_team_doc = t.get("members", [])
            valid_members_count = 0
            team_total = 0
            for m_uid in members_in_team_doc:
                if m_uid in user_map:
                    user_info = user_map[m_uid]
                    # ★修正: ユーザー情報の所属チームIDと、現在のチームIDが一致するか確認
                    if user_info.get("teamId") == team_id:
                        team_total += stats.get(m_uid, 0)
                        valid_members_count += 1
            
            if team_total > 0 or valid_members_count > 0:
                result.append({"name": t.get("name", "No Name"), "minutes": team_total, "count": valid_members_count})
        result = [r for r in result if r["minutes"] > 0]
        return result

    # --- タブへの描画 ---
    
    # 1. 個人 (今日)
    with tabs[0]:
        st.caption(f"集計期間: {datetime.datetime.now(JST).strftime('%Y/%m/%d')} (今日)")
        display_ranking_table(make_personal_list(stats_day))

    # 2. 個人 (今週)
    with tabs[1]:
        start_week = (datetime.datetime.now(JST) - datetime.timedelta(days=datetime.datetime.now(JST).weekday()))
        st.caption(f"集計期間: {start_week.strftime('%m/%d')} 〜")
        display_ranking_table(make_personal_list(stats_week))

    # 3. 個人 (今月)
    with tabs[2]:
        start_month = datetime.datetime.now(JST).replace(day=1)
        st.caption(f"集計期間: {start_month.strftime('%m/%d')} 〜")
        display_ranking_table(make_personal_list(stats_month))

    # 4. チーム (今日)
    with tabs[3]:
        st.caption("チームメンバーの今日の合計時間")
        display_ranking_table(make_team_list(stats_day))

    # 5. チーム (今週)
    with tabs[4]:
        st.caption("チームメンバーの今週の合計時間")
        display_ranking_table(make_team_list(stats_week))

    # 6. チーム (今月)
    with tabs[5]:
        st.caption("チームメンバーの今月の合計時間")
        display_ranking_table(make_team_list(stats_month))

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
                        # ファイルパスを一意にする
                        blob_name = f"posts/{user_id}/{uuid.uuid4()}_{img_file.name}"
                        blob = bucket.blob(blob_name)
                        blob.upload_from_file(img_file, content_type=img_file.type)
                        
                        # 【修正】make_public()を廃止し、署名付きURLを使用（セキュリティ強化）
                        # ※ここでは永続的な公開ではなく、1時間有効なURLを発行する例
                        # ただし、掲示板のような静的コンテンツの場合、本来は公開バケットポリシーの設定が推奨されるが、
                        # コードベースでの修正としては generate_signed_url が安全。
                        # 長期間表示させるために有効期限を長め（例えば7日）に設定するか、
                        # 今回は簡易的に V4 署名を使用。
                        image_url = blob.generate_signed_url(
                            version="v4",
                            expiration=datetime.timedelta(days=7),
                            method="GET"
                        )

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
            
            # 【修正】N+1問題対策：コメントをデフォルトで読み込まないように変更
            # チェックボックスがONになったときだけ読み込み処理を実行する
            show_comments = st.checkbox(f"💬 コメントを表示 / 返信", key=f"check_{post_id}")
            
            if show_comments:
                comments_ref = db.collection("posts").document(post_id).collection("comments")
                # limitを追加して安全策
                comments = comments_ref.order_by("timestamp").limit(50).stream()
                
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

def render_team_page():
    """チーム機能（旧バディ機能から刷新）"""
    st.title("👥 チーム機能")
    
    # ユーザーのチーム所属状況を確認
    my_doc = user_ref.get().to_dict()
    my_team_id = my_doc.get("teamId")
    
    if my_team_id:
        # --- 所属している場合 ---
        team_ref = db.collection("teams").document(my_team_id)
        team_doc = team_ref.get()
        
        if not team_doc.exists:
            # チームが消滅している場合などの整合性処理
            user_ref.update({"teamId": firestore.DELETE_FIELD})
            st.error("所属していたチームが見つかりません。")
            st.rerun()
            return

        team_data = team_doc.to_dict()
        st.subheader(f"チーム名: {team_data.get('name')}")
        st.info(f"🔑 **チーム招待コード:** `{team_data.get('teamCode')}`")
        st.caption("友達にこのコードを教えて、チームに招待しよう！")
        
        st.markdown("### 📋 メンバーリスト")
        members = team_data.get("members", [])
        
        if members:
            # メンバー詳細取得
            for m_uid in members:
                m_doc = db.collection("users").document(m_uid).get()
                if m_doc.exists:
                    m_data = m_doc.to_dict()
                    m_name = m_data.get("name", "名無し")
                    m_total = m_data.get("totalStudyMinutes", 0)
                    
                    # 自分かどうか
                    me_mark = " (あなた)" if m_uid == user_id else ""
                    st.write(f"- **{m_name}**{me_mark} : 累計 {m_total}分")
        
        st.markdown("---")
        if st.button("🚪 チームから脱退する"):
            # 【修正】Atomic Operation: ArrayRemoveを使用
            # 配列から自分を安全に削除
            team_ref.update({"members": firestore.ArrayRemove([user_id])})
            # 自分のteamId削除
            user_ref.update({"teamId": firestore.DELETE_FIELD})
            st.success("脱退しました。")
            st.rerun()

    else:
        # --- 所属していない場合 ---
        st.write("チームに参加して、みんなで学習時間を競い合おう！")
        
        tab_new, tab_join = st.tabs(["✨ 新規チーム作成", "📩 チームに参加"])
        
        with tab_new:
            with st.form("create_team_form"):
                t_name = st.text_input("チーム名を決めてください")
                submit_create = st.form_submit_button("作成して参加")
                
                if submit_create and t_name:
                    # コード生成
                    t_code = str(uuid.uuid4())[:6].upper() # 簡易的
                    
                    # チーム作成
                    new_team_ref = db.collection("teams").add({
                        "name": t_name,
                        "teamCode": t_code,
                        "members": [user_id],
                        "createdAt": firestore.SERVER_TIMESTAMP
                    })
                    new_team_id = new_team_ref[1].id
                    
                    # ユーザー更新
                    user_ref.update({"teamId": new_team_id})
                    
                    st.success(f"チーム「{t_name}」を作成しました！")
                    st.rerun()
        
        with tab_join:
            with st.form("join_team_form"):
                input_code = st.text_input("招待コードを入力")
                submit_join = st.form_submit_button("参加する")
                
                if submit_join and input_code:
                    input_code = input_code.strip().upper()
                    # コード検索
                    teams = db.collection("teams").where("teamCode", "==", input_code).stream()
                    target_team = next(teams, None)
                    
                    if target_team:
                        t_id = target_team.id
                        t_data = target_team.to_dict()
                        members = t_data.get("members", [])
                        
                        if user_id in members:
                             st.warning("既に参加しています")
                        else:
                            # 【修正】Atomic Operation: ArrayUnionを使用
                            # 競合を防ぎつつメンバーを追加
                            db.collection("teams").document(t_id).update({
                                "members": firestore.ArrayUnion([user_id])
                            })
                            user_ref.update({"teamId": t_id})
                            st.success(f"チーム「{t_data.get('name')}」に参加しました！")
                            st.rerun()
                    else:
                        st.error("チームが見つかりませんでした。コードを確認してください。")

def render_chat_page():
    """AIコーチ画面（既存ロジック）"""
    apply_chat_css() # CSS適用
    
    st.title("🤖 AI数学コーチ")
    st.caption("教科書の内容を「完璧」に理解しよう。答えは教えません、一緒に解きます。")

    if not st.session_state.messages_loaded:
        # limitを追加
        history_ref = user_ref.collection("history").order_by("timestamp").limit(50)
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
                        
                        # 【修正】リトライロジック (Exponential Backoff)
                        # 一時的なエラー（503など）に対して再試行を行う
                        
                        for model_name in PRIORITY_MODELS:
                            # モデルごとに最大3回リトライ
                            retry_count = 0
                            max_retries = 3
                            
                            while retry_count < max_retries:
                                try:
                                    model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
                                    chat = model.start_chat(history=history_for_ai)
                                    inputs = [user_prompt]
                                    if upload_img_obj:
                                        inputs.append(upload_img_obj)
                                    
                                    response = chat.send_message(inputs)
                                    ai_text = response.text
                                    success_model = model_name
                                    break # 成功したらループを抜ける
                                except Exception as e:
                                    retry_count += 1
                                    wait_time = 2 ** retry_count # 2, 4, 8秒待機
                                    log_message = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ⚠️ {model_name} エラー(Try {retry_count}): {e}"
                                    error_details.append(log_message)
                                    st.session_state.debug_logs.append(log_message)
                                    if retry_count < max_retries:
                                        time.sleep(wait_time)
                                    else:
                                        pass # 次のモデルへ

                            if success_model:
                                break # モデルが見つかったら外側のループも抜ける
                    
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
elif current_page == "team":
    render_team_page()
elif current_page == "admin_menu": # ★追加: 管理者メニューへのルーティング
    render_admin_menu_page()
else:
    render_portal_page()
