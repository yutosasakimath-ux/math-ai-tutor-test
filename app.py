import streamlit as st
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, firestore
import requests
import json
import datetime
import time
from PIL import Image
import os
import io
import base64
import re  # 正規表現用

# --- ★追加：数式描画用ライブラリ ---
import matplotlib
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

# Streamlit CloudなどのGUIがない環境でのエラーを防ぐ設定
matplotlib.use('Agg')

# --- 0. 設定と定数 ---
st.set_page_config(page_title="AI数学専属コーチ", page_icon="🎓", layout="centered", initial_sidebar_state="expanded")

# ★★★ UI設定：スマホ対応・入力フォームの最適化・カメラアイコン化 ★★★
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

# --- ★追加機能：数式を画像に変換する関数 ---
def render_math_to_image(latex_str, fontsize=12):
    """
    LaTeX文字列をMatplotlibを使って画像(ImageReader)に変換する。
    """
    # Matplotlibで数式を描画
    fig = plt.figure(figsize=(0.1, 0.1)) # 初期サイズはダミー
    text = fig.text(0, 0, f"${latex_str}$", fontsize=fontsize, usetex=False)
    
    # 描画サイズを取得してリサイズ
    bbox = text.get_window_extent(fig.canvas.get_renderer())
    bbox_inches = bbox.transformed(fig.dpi_scale_trans.inverted())
    
    # 少し余白を持たせる
    fig.set_size_inches(bbox_inches.width + 0.1, bbox_inches.height + 0.1)
    text.set_position((0.05, 0.05))
    
    # 画像バッファに出力
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=300, transparent=True)
    plt.close(fig)
    buf.seek(0)
    
    # 高さ(mm換算)を返す
    height_mm = bbox_inches.height * 25.4
    return ImageReader(buf), height_mm

def create_pdf(text_content, student_name):
    """テキストレポートからPDFを作成しバイナリデータとして返す（数式画像対応版）"""
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
    max_char_per_line = 40 
    line_height = 6 * mm
    y_position = height - 50 * mm
    
    for line in lines:
        line = line.strip()
        if not line:
            y_position -= line_height
            continue

        # --- 数式判定 ($$ ... $$) ---
        # 行全体が $$...$$ で囲まれているかを判定
        math_match = re.match(r'^\$\$(.+)\$\$$', line)
        
        if math_match:
            # 数式の場合：画像として描画
            latex_str = math_match.group(1)
            try:
                img_reader, img_height_mm = render_math_to_image(latex_str, fontsize=14)
                
                # 改ページ判定
                if y_position - img_height_mm < 20 * mm:
                    p.showPage()
                    p.setFont(font_name, 11)
                    y_position = height - 30 * mm
                
                # 画像を描画 (X座標は少しインデント)
                p.drawImage(img_reader, 25 * mm, y_position - img_height_mm + 2*mm, height=img_height_mm * mm, preserveAspectRatio=True, mask='auto')
                y_position -= (img_height_mm + 4) * mm # 次の行へ移動
                
            except Exception as e:
                # 失敗時はそのままテキスト描画
                p.drawString(20 * mm, y_position, line)
                y_position -= line_height
        else:
            # 通常テキストの場合：折り返し描画
            while True:
                chunk = line[:max_char_per_line]
                line = line[max_char_per_line:]
                
                if y_position < 20 * mm:
                    p.showPage()
                    p.setFont(font_name, 11)
                    y_position = height - 30 * mm
                
                p.drawString(20 * mm, y_position, chunk)
                y_position -= line_height
                
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
        if "firebase" in st.secrets:
            key_dict = dict(st.secrets["firebase"])
            if "\\n" in key_dict["private_key"]:
                key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(key_dict)
            firebase_admin.initialize_app(cred)
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
                                    "created_at": firestore.SERVER_TIMESTAMP
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

# --- 6. サイドバー ---
with st.sidebar:
    st.header(f"ようこそ、{student_name}さん")
    
    new_name = st.text_input("お名前（AIが呼びかける名前）", value=student_name)
    if new_name != student_name:
        user_ref.update({"name": new_name})
        st.session_state.user_name = new_name
        st.rerun()
    
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
        if "user_name" in st.session_state:
            del st.session_state["user_name"]
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
            # --- レポート作成機能 (★機能変更：PDF自動生成・自動オープン・数式対応) ---
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

                                # 2. レポートプロンプト (数式形式を指定)
                                report_system_instruction = f"""
                                あなたは数学の「学習まとめ作成AI」です。
                                生徒の「{new_name}」さんが今日学習した内容を復習できるように、簡潔かつ明確なレポートを作成してください。

                                【重要：数式の出力ルール】
                                PDFで綺麗に数式を表示するため、以下のルールを厳守してください。
                                1. 文中の簡単な数式（例: x, y, a=1）はそのまま書いてOKです。
                                2. **複雑な数式（分数、ルート、2乗など）は、必ず独立した行にし、LaTeX形式で `$$` (ドルマーク2つ) で囲んでください。**
                                   良い例:
                                   $$ x = \\frac{{-b \\pm \\sqrt{{b^2-4ac}}}}{{2a}} $$
                                   
                                   悪い例:
                                   x = (-b ± √(b^2-4ac)) / 2a  (読みづらい)

                                【出力フォーマット（厳守）】
                                --------------------------------------------------
                                【📅 {now_jst.strftime('%Y/%m/%d')} 学習まとめレポート】
                                
                                ■ 今日学んだ単元
                                （箇条書きで簡潔に）

                                ■ 重要公式・ポイント
                                （重要な数式は必ず $$...$$ で囲んで出力してください）

                                ■ 今日の解法メモ
                                （具体的にどのような問題に取り組み、どう解決したかを要約）

                                ■ 次回へのアドバイス
                                （励ましのメッセージと、次に復習すべき点）
                                --------------------------------------------------
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
                                    
                                    # ★重要：ここで直ちにPDFを生成（数式対応版）★
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

# --- 8. メイン画面 ---
st.title("🎓 高校数学 AI専属コーチ")
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
2. **現状分析**: まず、生徒が質問を見て、「どこまで分かっていて、どこで詰まっているか」を特定してください。
3. **問いかけ**: 生徒が次に進むための「小さなヒント」や「問いかけ」を投げかけてください。
4. **アウトプットの要求**: 一方的に解説せず、必ず生徒に考えさせ、返答させてください。
5. **数式**: 必要であればLaTeX形式（$マーク）を使ってきれいに表示してください。
"""

# --- 10. AI応答ロジック ---
with st.form(key="chat_form", clear_on_submit=True):
    col1, col2, col3 = st.columns([0.8, 5, 1], gap="small")
    with col1:
        uploaded_file = st.file_uploader(" ", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed")
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
