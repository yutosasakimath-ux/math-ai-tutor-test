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
import re
import uuid
import pandas as pd

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm

# --- 0. 設定と定数 ---
st.set_page_config(page_title="AI数学専属コーチ", page_icon="🎓", layout="centered", initial_sidebar_state="expanded")
JST = datetime.timezone(datetime.timedelta(hours=9))

# --- CSS定義 ---
def apply_chat_css():
    hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    
    /* チャット入力フォームのスタイル調整 */
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

    /* ファイルアップローダーをカメラアイコンにするスタイル */
    [data-testid="stFileUploader"] {
        width: 50px;
        margin-top: 0px;
        padding-top: 0;
    }
    [data-testid="stFileUploader"] section {
        padding: 0;
        min-height: 44px;
        background-color: transparent;
        border: 1px solid #ccc; /* 枠線 */
        border-radius: 5px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: transparent; 
    }
    [data-testid="stFileUploader"] section > * {
        display: none !important; /* デフォルトの文字を消す */
    }
    [data-testid="stFileUploader"] section::after {
        content: "📷";  /* カメラアイコン */
        font-size: 24px;
        color: #555;
        display: block;
        cursor: pointer;
    }
    /* ファイル選択後のスタイル */
    [data-testid="stFileUploader"]:has(input[type="file"]:valid) section {
        background-color: #e0f7fa;
        border-color: #00bcd4;
    }
    [data-testid="stFileUploader"]:has(input[type="file"]:valid) section::after {
        content: "✅"; /* 選択済み */
    }
    
    .stTextArea textarea {
        font-size: 16px;
        padding: 10px;
    }
    </style>
    """
    st.markdown(hide_streamlit_style, unsafe_allow_html=True)

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

# --- フォント管理 ---
FONT_URL = "https://moji.or.jp/wp-content/ipafont/IPAexfont/ipaexg00401.zip"
FONT_FILE_NAME = "ipaexg.ttf"

def ensure_japanese_font():
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

def create_pdf(text_content, student_name):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    # 簡易実装
    p.drawString(100, 800, "Report")
    p.save()
    buffer.seek(0)
    return buffer

# --- Secrets ---
if "ADMIN_EMAIL" in st.secrets:
    ADMIN_EMAIL = st.secrets["ADMIN_EMAIL"]
else:
    ADMIN_EMAIL = None 

if "ADMIN_KEY" in st.secrets:
    ADMIN_KEY = st.secrets["ADMIN_KEY"]
else:
    ADMIN_KEY = None

if "FIREBASE_WEB_API_KEY" in st.secrets:
    FIREBASE_WEB_API_KEY = st.secrets["FIREBASE_WEB_API_KEY"]
else:
    FIREBASE_WEB_API_KEY = ""

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
if "user_role" not in st.session_state:
    st.session_state.user_role = "student" 
if "managed_team_id" not in st.session_state:
    st.session_state.managed_team_id = None 
if "last_used_model" not in st.session_state:
    st.session_state.last_used_model = "まだ回答していません"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "messages_loaded" not in st.session_state:
    st.session_state.messages_loaded = False
if "debug_logs" not in st.session_state:
    st.session_state.debug_logs = []
if "current_page" not in st.session_state:
    st.session_state.current_page = "portal" # 初期値

def navigate_to(page_name):
    st.session_state.current_page = page_name
    st.rerun()

# --- 4. UI: ログイン画面 ---
if st.session_state.user_info is None:
    st.title("🎓 AI数学コーチ：ログイン")
    
    if not FIREBASE_WEB_API_KEY:
        st.error("⚠️ Web APIキーが設定されていません。Streamlit Secretsを確認してください。")
        st.stop()

    tab_student, tab_admin = st.tabs(["🧑‍🎓 生徒ログイン", "👨‍🏫 先生・管理者ログイン"])

    # --- タブ1: 生徒用ログイン ---
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

    # --- タブ2: 先生・管理者用ログイン ---
    with tab_admin:
        st.caption("先生または管理者はこちら。")
        st.warning("※管理者権限を持つアカウントでのみログイン可能です。")
        
        with st.form("admin_login_form"):
            a_email = st.text_input("メールアドレス", key="a_email")
            a_password = st.text_input("パスワード", type="password", key="a_pass")
            
            st.markdown("---")
            st.write("▼ 以下のいずれかを入力してください")
            auth_code = st.text_input("管理者パスワード または チーム招待コード", type="password", help="開発者は管理者キー、先生は担当クラスのチームコードを入力してください。")
            
            submit_admin = st.form_submit_button("管理者/先生としてログイン")
            
            if submit_admin:
                # 1. Firebase認証
                resp = sign_in_with_email(a_email, a_password)
                if "error" in resp:
                    st.error(f"認証失敗: {resp['error']['message']}")
                else:
                    uid = resp["localId"]
                    user_email_val = resp["email"]
                    
                    # 2. 権限チェック
                    # A. 全体管理者（開発者）
                    if ADMIN_KEY and auth_code == ADMIN_KEY:
                        if ADMIN_EMAIL and user_email_val == ADMIN_EMAIL:
                            st.session_state.user_info = {"uid": uid, "email": user_email_val}
                            st.session_state.user_role = "global_admin"
                            st.success("全体管理者としてログインしました")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("⛔️ 認証に失敗しました。（管理者権限がありません）")
                        
                    # B. チーム管理者（先生）
                    else:
                        user_doc = db.collection("users").document(uid).get()
                        is_teacher_auth = False
                        managed_team_id = None
                        
                        if user_doc.exists:
                            u_data = user_doc.to_dict()
                            if u_data.get("role") == "teacher":
                                managed_team_id = u_data.get("managedTeamId")
                                if managed_team_id:
                                    t_doc = db.collection("teams").document(managed_team_id).get()
                                    if t_doc.exists:
                                        t_data = t_doc.to_dict()
                                        if t_data.get("teamCode") == auth_code.strip().upper():
                                            is_teacher_auth = True
                                            st.session_state.managed_team_name = t_data.get("name")
                        
                        if is_teacher_auth:
                            st.session_state.user_info = {"uid": uid, "email": user_email_val}
                            st.session_state.user_role = "team_teacher"
                            st.session_state.managed_team_id = managed_team_id
                            st.success(f"チーム「{st.session_state.managed_team_name}」の先生としてログインしました")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("⛔️ 先生としての権限がありません、またはチームコードが間違っています。")
    st.stop()

# =========================================================
# ログイン済みユーザーの世界
# =========================================================

user_id = st.session_state.user_info["uid"]
user_email = st.session_state.user_info["email"]
user_role = st.session_state.user_role 

user_ref = db.collection("users").document(user_id)
if "user_name" not in st.session_state:
    try:
        user_doc = user_ref.get()
        if user_doc.exists:
            st.session_state.user_name = user_doc.to_dict().get("name", "ゲスト")
        else:
            st.session_state.user_name = "管理者/先生"
    except Exception as e:
        st.session_state.user_name = "ゲスト"

student_name = st.session_state.user_name

# --- 5. サイドバー (権限別表示) ---
with st.sidebar:
    if user_role == "student":
        st.header(f"ようこそ、{student_name}さん")
        st.caption("ナビゲーション")
        if st.button("🏠 ホーム (ポータル)", use_container_width=True): navigate_to("portal")
        
        col_nav1, col_nav2 = st.columns(2)
        with col_nav1:
            if st.button("🤖 AIコーチ", use_container_width=True): navigate_to("chat")
            if st.button("🏆 ランキング", use_container_width=True): navigate_to("ranking")
        with col_nav2:
            if st.button("📝 学習記録", use_container_width=True): navigate_to("study_log")
            if st.button("👥 チーム", use_container_width=True): navigate_to("team")
        
        if st.button("💬 掲示板", use_container_width=True): navigate_to("board")
        if st.button("📮 先生へ連絡", use_container_width=True): navigate_to("contact")
        
        st.markdown("---")
        if st.session_state.current_page == "chat":
            if st.button("🗑️ 会話履歴を全削除"):
                st.success("履歴をリセットしました")
                time.sleep(1)
                st.rerun()

    else:
        # 管理者・先生用サイドバー
        st.header("管理者メニュー")
        role_label = "開発者" if user_role == "global_admin" else "先生"
        st.caption(f"権限: {role_label}")
        
        if st.button("🏠 ホーム", use_container_width=True): navigate_to("admin_home")
        if st.button("📊 学習状況", use_container_width=True): navigate_to("admin_learning")
        
        # (2) 管理者(global_admin)には連絡ボタンを表示しない
        if user_role == "team_teacher":
            if st.button("📮 生徒連絡", use_container_width=True): navigate_to("admin_contact")
        
        if user_role == "global_admin":
            st.markdown("---")
            if st.button("👥 チーム作成", use_container_width=True): navigate_to("admin_create_team") 
            if st.button("🔑 権限管理", use_container_width=True): navigate_to("admin_roles")
            if st.button("👤 アカウント作成", use_container_width=True): navigate_to("admin_signup")
        
        st.markdown("---")

    if st.button("ログアウト", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# =========================================================
# ヘルパー関数: 未読チェック
# =========================================================
def get_unread_senders(target_team_id=None):
    try:
        # 未読メッセージを検索 (Collection Group Query)
        # ※インデックス作成が必要になる場合があります: sender ASC, read ASC
        query = db.collection_group("messages").where("sender", "==", "student").where("read", "==", False)
        docs = query.stream()
        
        unread_uids = set()
        for d in docs:
            # メッセージの親ドキュメントのIDがユーザーID
            parent_doc = d.reference.parent.parent
            if parent_doc:
                unread_uids.add(parent_doc.id)
        
        if target_team_id:
            team_doc = db.collection("teams").document(target_team_id).get()
            if team_doc.exists:
                team_members = set(team_doc.to_dict().get("members", []))
                unread_uids = unread_uids.intersection(team_members)
            else:
                return []
        
        return list(unread_uids)
    except Exception as e:
        # インデックス未作成エラーなどを想定
        print(f"Unread check error: {e}")
        return []

# =========================================================
# 管理者用 画面描画関数
# =========================================================

def render_admin_home():
    """管理者用ホーム"""
    role = st.session_state.user_role
    st.title("👨‍🏫 管理者ホーム")
    
    if role == "global_admin":
        st.info(f"全体管理者としてログイン中\nID: {user_email}")
        st.warning("※プライバシー保護のため、管理者は生徒との直接連絡機能を使用できません。")
    else:
        t_name = st.session_state.get("managed_team_name", "担当チーム")
        st.info(f"チーム「{t_name}」の先生としてログイン中")

        # (2) 未読チェック: 教員(team_teacher)のみ実行
        target_team = st.session_state.managed_team_id
        unread_uids = get_unread_senders(target_team)
        unread_count = len(unread_uids)
        
        if unread_count > 0:
            st.error(f"🔔 **{unread_count}名** の生徒から未読メッセージが届いています！")
        else:
            st.success("現在、未読のメッセージはありません。")

    st.markdown("### 📌 メニュー")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📊 学習状況を確認する\n(チーム・生徒検索)", use_container_width=True):
            navigate_to("admin_learning")
        
        if role == "global_admin":
            if st.button("🔑 教員権限の管理\n(全体管理者のみ)", use_container_width=True):
                navigate_to("admin_roles")
            if st.button("👥 チーム作成\n(全体管理者のみ)", use_container_width=True):
                navigate_to("admin_create_team")
            
    with col2:
        # (2) 管理者には連絡ボタンを表示しない
        if role == "team_teacher":
            btn_label = f"📮 生徒と連絡をとる"
            if unread_count > 0:
                btn_label += f" (未読: {unread_count}件)"
            if st.button(btn_label, use_container_width=True):
                navigate_to("admin_contact")
        
        if role == "global_admin":
            if st.button("👤 新規アカウント作成\n(全体管理者のみ)", use_container_width=True):
                navigate_to("admin_signup")

def render_admin_learning():
    """(1) 学習状況確認（検索機能拡張: タブ分け）"""
    st.title("📊 学習状況の確認")
    role = st.session_state.user_role
    
    # 検索方法タブ
    tab_team, tab_student = st.tabs(["👥 チームコードで検索", "🧑‍🎓 生徒名で検索"])
    
    users_list = []
    
    # --- タブ1: チームコード検索 ---
    with tab_team:
        if role == "team_teacher":
            st.info(f"担当チーム: {st.session_state.get('managed_team_name', '不明')}")
            team_id = st.session_state.managed_team_id
            t_doc = db.collection("teams").document(team_id).get()
            if t_doc.exists:
                member_ids = t_doc.to_dict().get("members", [])
                for uid in member_ids:
                    u = db.collection("users").document(uid).get()
                    if u.exists:
                        users_list.append(u.to_dict() | {"id": u.id})
        else:
            search_team = st.text_input("チームコードを入力", placeholder="例: A1B2C3")
            if search_team:
                t_query = db.collection("teams").where("teamCode", "==", search_team.strip().upper()).stream()
                target_team_doc = next(t_query, None)
                if target_team_doc:
                    st.success(f"チーム「{target_team_doc.to_dict().get('name')}」が見つかりました")
                    member_ids = target_team_doc.to_dict().get("members", [])
                    for uid in member_ids:
                        u = db.collection("users").document(uid).get()
                        if u.exists:
                            users_list.append(u.to_dict() | {"id": u.id})
                else:
                    st.warning("チームが見つかりません")

    # --- タブ2: 生徒名検索 ---
    with tab_student:
        search_name = st.text_input("生徒名を入力", placeholder="例: 山田")
        if search_name:
            if role == "team_teacher":
                team_id = st.session_state.managed_team_id
                t_doc = db.collection("teams").document(team_id).get()
                if t_doc.exists:
                    member_ids = t_doc.to_dict().get("members", [])
                    for uid in member_ids:
                        u = db.collection("users").document(uid).get()
                        if u.exists:
                            u_data = u.to_dict()
                            if search_name in u_data.get("name", ""):
                                users_list.append(u_data | {"id": u.id})
            else:
                q = db.collection("users").where("name", ">=", search_name).where("name", "<=", search_name + "\uf8ff").limit(20)
                docs = q.stream()
                for d in docs:
                    users_list.append(d.to_dict() | {"id": d.id})
    
    if not users_list:
        st.caption("検索条件を入力してください、または該当者がいません。")
        return

    users_list = {u['id']: u for u in users_list}.values()
    users_list = list(users_list)
    users_list.sort(key=lambda x: x.get("totalStudyMinutes", 0), reverse=True)
    
    st.divider()
    user_options = {u["id"]: f"{u.get('name', '名無し')} ({u.get('totalStudyMinutes', 0)}分)" for u in users_list}
    selected_uid = st.selectbox("詳細を見る生徒を選択", options=list(user_options.keys()), format_func=lambda x: user_options[x], key="learning_select")
    
    target = next((u for u in users_list if u["id"] == selected_uid), None)
    if target:
        st.markdown(f"#### 👤 {target.get('name')} さんの学習状況")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("累計学習時間", f"{target.get('totalStudyMinutes', 0)} 分")
        with col2:
            st.caption(f"Email: {target.get('email')}")
            st.caption(f"登録日: {target.get('created_at')}")

def render_admin_contact():
    """(2) 連絡機能（未読/検索タブ分け） ※管理者はアクセス不可"""
    st.title("📮 生徒との連絡")
    role = st.session_state.user_role
    
    # 管理者ブロック
    if role == "global_admin":
        st.error("管理者権限では生徒のメッセージを閲覧できません。")
        if st.button("ホームに戻る"):
            navigate_to("admin_home")
        return

    target_team = st.session_state.managed_team_id
    tab_unread, tab_search = st.tabs(["🔔 未読メッセージ", "🔍 生徒を検索して連絡"])

    target_uid_for_chat = None

    with tab_unread:
        unread_uids = get_unread_senders(target_team)
        if unread_uids:
            st.error(f"以下の生徒からメッセージが届いています ({len(unread_uids)}件)")
            for uid in unread_uids:
                u_doc = db.collection("users").document(uid).get()
                u_name = u_doc.to_dict().get("name", "不明") if u_doc.exists else "不明"
                if st.button(f"🔴 {u_name} さんからのメッセージを見る", key=f"unread_btn_{uid}"):
                    st.session_state.admin_chat_target = uid
                    st.rerun()
        else:
            st.success("現在、未読のメッセージはありません。")

    with tab_search:
        st.markdown("チームコードまたは生徒名で検索")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            s_team_code = st.text_input("チームコード", key="contact_search_team")
        with col_s2:
            s_student_name = st.text_input("生徒名", key="contact_search_name")
            
        candidates = []
        if s_team_code:
            t_query = db.collection("teams").where("teamCode", "==", s_team_code.strip().upper()).stream()
            t_doc = next(t_query, None)
            if t_doc:
                m_ids = t_doc.to_dict().get("members", [])
                for mid in m_ids:
                    u = db.collection("users").document(mid).get()
                    if u.exists:
                         if role == "team_teacher" and target_team != t_doc.id:
                             continue 
                         candidates.append(u.to_dict() | {"id": u.id})
        
        if s_student_name:
            if role == "team_teacher":
                t_doc = db.collection("teams").document(target_team).get()
                if t_doc.exists:
                    m_ids = t_doc.to_dict().get("members", [])
                    for mid in m_ids:
                        u = db.collection("users").document(mid).get()
                        if u.exists:
                            u_dat = u.to_dict()
                            if s_student_name in u_dat.get("name", ""):
                                candidates.append(u_dat | {"id": u.id})
            # 管理者の検索機能は削除済 (到達しないはずだが念のため)

        unique_candidates = {c['id']: c for c in candidates}.values()
        
        if unique_candidates:
            opts = {c["id"]: f"{c.get('name')} ({c.get('email')})" for c in unique_candidates}
            selected = st.selectbox("連絡先を選択", options=list(opts.keys()), format_func=lambda x: opts[x], key="contact_select")
            if st.button("チャットを開く", key="open_chat_search"):
                st.session_state.admin_chat_target = selected
                st.rerun()
        elif s_team_code or s_student_name:
            st.caption("該当者が見つかりません")

    target_uid_for_chat = st.session_state.get("admin_chat_target")

    if target_uid_for_chat:
        st.divider()
        u_doc = db.collection("users").document(target_uid_for_chat).get()
        if not u_doc.exists:
            st.error("ユーザーが見つかりません")
            return
        
        u_name = u_doc.to_dict().get("name")
        st.markdown(f"### 💬 {u_name} さんとのチャット")
        
        msgs_ref = db.collection("admin_messages").document(target_uid_for_chat).collection("messages")
        
        # 既読処理
        unread_msgs = msgs_ref.where("sender", "==", "student").where("read", "==", False).stream()
        batch = db.batch()
        has_unread = False
        for m in unread_msgs:
            batch.update(m.reference, {"read": True})
            has_unread = True
        if has_unread:
            batch.commit()

        all_msgs = msgs_ref.order_by("timestamp").stream()
        with st.container(height=400):
            for m in all_msgs:
                d = m.to_dict()
                sender = d.get("sender")
                content = d.get("content")
                ts = d.get("timestamp")
                t_str = ts.astimezone(JST).strftime('%m/%d %H:%M') if ts else ""
                
                if sender == "student":
                    with st.chat_message("user", avatar="🧑‍🎓"):
                        st.write(content)
                        st.caption(t_str)
                else:
                    with st.chat_message("assistant", avatar="👨‍🏫"):
                        st.write(content)
                        st.caption(f"先生 - {t_str}")

        with st.form("admin_send_msg_v2", clear_on_submit=True):
            txt = st.text_input("返信を入力")
            if st.form_submit_button("送信"):
                if txt:
                    msgs_ref.add({
                        "sender": "teacher",
                        "content": txt,
                        "timestamp": firestore.SERVER_TIMESTAMP,
                        "read": False
                    })
                    st.success("送信しました")
                    time.sleep(0.5)
                    st.rerun()

def render_admin_create_team():
    """(1) 管理者専用チーム作成機能（教員権限付与機能付き）"""
    st.title("👥 チーム作成")
    st.caption("新しいクラス（チーム）を作成し、担当教員と初期メンバーを設定できます。")
    
    if st.session_state.user_role != "global_admin":
        st.error("この機能は全体管理者のみ利用可能です。")
        return

    with st.form("create_team_admin_form"):
        t_name = st.text_input("チーム名（例: 3年B組）")
        
        # 全ユーザー取得（本来はもっと効率的な検索UIが必要）
        all_users_stream = db.collection("users").limit(100).stream()
        all_users = [u.to_dict() | {"id": u.id} for u in all_users_stream]
        user_opts = {u['id']: f"{u.get('name')} ({u.get('email')})" for u in all_users}
        
        # 担当教員の選択
        st.markdown("### 👨‍🏫 担当教員の選択")
        st.caption("選択したアカウントに、このチームの教員権限(Teacher role)が付与されます。")
        selected_teacher_uid = st.selectbox(
            "教員アカウントを選択", 
            options=[""] + list(user_opts.keys()), 
            format_func=lambda x: user_opts[x] if x else "選択してください"
        )

        # メンバー選択
        st.markdown("### 🧑‍🎓 生徒の選択")
        selected_members = st.multiselect(
            "初期メンバーを選択（後からでも追加可能）", 
            options=list(user_opts.keys()), 
            format_func=lambda x: user_opts[x]
        )
        
        submit = st.form_submit_button("チームを作成 & 権限付与")
        
        if submit:
            if not t_name:
                st.error("チーム名を入力してください")
            elif not selected_teacher_uid:
                st.error("担当教員を必ず選択してください")
            else:
                t_code = str(uuid.uuid4())[:6].upper()
                
                # 教員もメンバーリストに含めるか？ -> 含めておくとリスト表示などで便利
                final_members = list(set(selected_members + [selected_teacher_uid]))

                new_ref = db.collection("teams").add({
                    "name": t_name,
                    "teamCode": t_code,
                    "members": final_members, 
                    "creatorId": user_id,
                    "createdAt": firestore.SERVER_TIMESTAMP,
                    "isOfficial": True 
                })
                new_team_id = new_ref[1].id
                
                # 生徒の所属チーム更新
                batch = db.batch()
                for mid in final_members:
                    ref = db.collection("users").document(mid)
                    batch.update(ref, {"teamId": new_team_id})
                
                # 教員権限の付与 (role=teacher, managedTeamId=...)
                teacher_ref = db.collection("users").document(selected_teacher_uid)
                batch.update(teacher_ref, {
                    "role": "teacher",
                    "managedTeamId": new_team_id
                })
                
                batch.commit()
                st.success(f"チーム「{t_name}」を作成しました！\n担当教員を設定しました。")

def render_admin_roles():
    """権限管理 (全体管理者のみ)"""
    st.title("🔑 教員権限の管理")
    if st.session_state.user_role != "global_admin":
        st.error("権限がありません")
        return

    st.markdown("特定のユーザーに、指定したチームの管理権限(先生権限)を付与します。")
    with st.form("grant_teacher_role_form"):
        target_email = st.text_input("権限を与えたいユーザーのメールアドレス")
        target_team_code_input = st.text_input("担当させるチームコード")
        
        if st.form_submit_button("権限を付与"):
            if not target_email or not target_team_code_input:
                st.error("メールアドレスとチームコードを入力してください")
            else:
                u_query = db.collection("users").where("email", "==", target_email).stream()
                target_user = next(u_query, None)
                
                t_query = db.collection("teams").where("teamCode", "==", target_team_code_input.strip().upper()).stream()
                target_team_doc = next(t_query, None)
                
                if target_user and target_team_doc:
                    db.collection("users").document(target_user.id).update({
                        "role": "teacher",
                        "managedTeamId": target_team_doc.id
                    })
                    t_name = target_team_doc.to_dict().get("name")
                    st.success(f"成功: {target_email} さんを「{t_name}」の先生に設定しました。")
                else:
                    st.error("ユーザーまたはチームが見つかりません。")

def render_admin_signup():
    """新規アカウント作成"""
    st.title("👤 新規アカウント作成")
    if st.session_state.user_role != "global_admin":
        st.error("権限がありません")
        return
    
    with st.form("admin_signup_form_internal"):
        new_name_input = st.text_input("お名前") 
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
                            "role": "student"
                        })
                        st.success(f"作成成功！\n名前: {new_name_input}\nEmail: {new_email}")
                    except Exception as e:
                        st.error(f"DB登録エラー: {e}")

# =========================================================
# 生徒用: チーム画面
# =========================================================
def render_team_page():
    st.title("👥 チーム機能")
    my_doc = user_ref.get().to_dict()
    my_team_id = my_doc.get("teamId")
    
    if my_team_id:
        # 所属済みの場合
        team_ref = db.collection("teams").document(my_team_id)
        team_doc = team_ref.get()
        if not team_doc.exists:
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
            for m_uid in members:
                m_doc = db.collection("users").document(m_uid).get()
                if m_doc.exists:
                    m_data = m_doc.to_dict()
                    m_name = m_data.get("name", "名無し")
                    me_mark = " (あなた)" if m_uid == user_id else ""
                    st.write(f"- **{m_name}**{me_mark}")
        
        st.markdown("---")
        if st.button("🚪 チームから脱退する"):
            team_ref.update({"members": firestore.ArrayRemove([user_id])})
            user_ref.update({"teamId": firestore.DELETE_FIELD})
            st.success("脱退しました。")
            st.rerun()
    else:
        # 未所属時: 参加または作成
        st.write("チームに参加して、みんなで学習時間を競い合おう！")
        tab_new, tab_join = st.tabs(["✨ 新規チーム作成", "📩 チームに参加"])
        
        with tab_new:
            with st.form("create_team_form"):
                t_name = st.text_input("チーム名を決めてください")
                submit_create = st.form_submit_button("作成して参加")
                if submit_create and t_name:
                    t_code = str(uuid.uuid4())[:6].upper()
                    new_team_ref = db.collection("teams").add({
                        "name": t_name,
                        "teamCode": t_code,
                        "members": [user_id],
                        "creatorId": user_id, 
                        "createdAt": firestore.SERVER_TIMESTAMP,
                        "isOfficial": False 
                    })
                    new_team_id = new_team_ref[1].id
                    user_ref.update({"teamId": new_team_id})
                    st.success(f"チーム「{t_name}」を作成しました！")
                    st.rerun()
        
        with tab_join:
            with st.form("join_team_form"):
                input_code = st.text_input("招待コードを入力")
                submit_join = st.form_submit_button("参加する")
                if submit_join and input_code:
                    input_code = input_code.strip().upper()
                    teams = db.collection("teams").where("teamCode", "==", input_code).stream()
                    target_team = next(teams, None)
                    if target_team:
                        t_id = target_team.id
                        members = target_team.to_dict().get("members", [])
                        if user_id in members:
                             st.warning("既に参加しています")
                        else:
                            db.collection("teams").document(t_id).update({
                                "members": firestore.ArrayUnion([user_id])
                            })
                            user_ref.update({"teamId": t_id})
                            st.success(f"チーム「{target_team.to_dict().get('name')}」に参加しました！")
                            st.rerun()
                    else:
                        st.error("チームが見つかりませんでした。")

# ... (生徒用その他ページ) ...
def render_contact_page():
    st.title("📮 先生へ連絡")
    st.caption("学習の相談や連絡事項があれば、ここにメッセージを書いてください。")
    msgs_ref = db.collection("admin_messages").document(user_id).collection("messages")
    query = msgs_ref.order_by("timestamp")
    docs = query.stream()
    with st.container(height=500):
        for doc in docs:
            data = doc.to_dict()
            sender = data.get("sender")
            content = data.get("content")
            ts = data.get("timestamp")
            if ts:
                time_str = ts.astimezone(JST).strftime('%m/%d %H:%M')
            else:
                time_str = ""
            if sender == "student":
                with st.chat_message("user", avatar="🧑‍🎓"):
                    st.write(content)
                    st.caption(f"{time_str}")
            else:
                with st.chat_message("assistant", avatar="👨‍🏫"):
                    st.write(content)
                    st.caption(f"先生 - {time_str}")
    with st.form("contact_admin_form", clear_on_submit=True):
        user_input = st.text_area("メッセージを入力", height=100)
        submit = st.form_submit_button("送信")
        if submit and user_input:
            try:
                msgs_ref.add({
                    "sender": "student",
                    "content": user_input,
                    "timestamp": firestore.SERVER_TIMESTAMP,
                    "read": False
                })
                st.success("送信しました")
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"送信エラー: {e}")

def render_portal_page():
    apply_portal_css()
    st.title(f"こんにちは、{student_name}さん！👋")
    user_doc = user_ref.get().to_dict()
    total_minutes = user_doc.get("totalStudyMinutes", 0)
    total_hours = total_minutes // 60
    st.info(f"📚 **累計学習時間**: {total_hours}時間 {total_minutes % 60}分")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🤖 AIコーチ\n(チャット)", use_container_width=True): navigate_to("chat")
        if st.button("🏆 ランキング\n(みんなと競う)", use_container_width=True): navigate_to("ranking")
        if st.button("💬 掲示板\n(Q&A)", use_container_width=True): navigate_to("board")
    with col2:
        if st.button("📝 学習記録\n(時間を記録)", use_container_width=True): navigate_to("study_log")
        if st.button("👥 チーム\n(みんなで頑張る)", use_container_width=True): navigate_to("team")
        if st.button("📮 先生へ連絡\n(相談する)", use_container_width=True): navigate_to("contact")
    st.markdown("---")
    with st.expander("⚙️ 設定・サポート"):
        st.markdown("### 👤 プロフィール設定")
        new_name = st.text_input("表示名", value=student_name, key="setting_name")
        if new_name != student_name:
            if st.button("名前を更新"):
                user_ref.update({"name": new_name})
                st.session_state.user_name = new_name
                st.success("名前を更新しました")
                time.sleep(1)
                st.rerun()
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
            feedback_content = st.text_area("感想、バグ、要望など")
            feedback_submit = st.form_submit_button("送信")
            if feedback_submit and feedback_content:
                db.collection("feedback").add({
                    "user_id": user_id,
                    "email": user_email,
                    "content": feedback_content,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                st.success("送信しました。")

def render_study_log_page():
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
                            user_ref.update({
                                "totalStudyMinutes": firestore.Increment(-m_val)
                            })
                            st.success("削除しました")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"削除エラー: {e}")

def render_ranking_page():
    st.title("🏆 学習時間ランキング")
    tabs = st.tabs(["👤 個人(今日)", "👤 個人(今週)", "👤 個人(今月)", "👥 チーム(今日)", "👥 チーム(今週)", "👥 チーム(今月)"])
    top_users_stream = db.collection("users").order_by("totalStudyMinutes", direction=firestore.Query.DESCENDING).limit(50).stream()
    all_users = list(top_users_stream)
    user_map = {}
    for u in all_users:
        user_map[u.id] = u.to_dict()
    all_teams = list(db.collection("teams").limit(20).stream())
    team_list = [{"id": t.id, **t.to_dict()} for t in all_teams]
    def get_anonymous_name(uid, original_name, is_anon_flag):
        if is_anon_flag:
            if uid == user_id: return "匿名ユーザー (あなた)"
            return "匿名ユーザー"
        return original_name
    def get_aggregated_stats(period_type):
        now_jst = datetime.datetime.now(JST)
        start_dt = None
        if period_type == 'day':
            start_dt = now_jst.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period_type == 'week':
            start_dt = (now_jst - datetime.timedelta(days=now_jst.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        elif period_type == 'month':
            start_dt = now_jst.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if not start_dt: return {}
        try:
            query = db.collection_group("study_logs").where("timestamp", ">=", start_dt).select(["minutes"]).limit(2000)
            docs = query.stream()
            stats = {}
            for d in docs:
                parent_ref = d.reference.parent.parent
                if parent_ref:
                    uid = parent_ref.id
                    if uid in user_map or uid == user_id:
                        minutes = d.to_dict().get("minutes", 0)
                        stats[uid] = stats.get(uid, 0) + minutes
            return stats
        except Exception as e:
            if "indexes?create_composite=" in str(e):
                st.error("⚠️ 管理者設定が必要です：Firestoreインデックスを作成してください。")
            else:
                st.error(f"集計エラー: {e}")
            return {}
    def display_ranking_table(data_list, value_key="minutes"):
        if not data_list:
            st.info("データがありません")
            return
        sorted_data = sorted(data_list, key=lambda x: x[value_key], reverse=True)
        display_rows = []
        for i, item in enumerate(sorted_data):
            row = {"順位": f"{i + 1}位", "名前": item["name"], "時間(分)": item[value_key]}
            if "count" in item: row["人数"] = item["count"]
            display_rows.append(row)
        df = pd.DataFrame(display_rows)
        if not df.empty: st.table(df.set_index("順位"))
    stats_day = get_aggregated_stats('day')
    stats_week = get_aggregated_stats('week')
    stats_month = get_aggregated_stats('month')
    def make_personal_list(stats):
        result = []
        for uid, mins in stats.items():
            if uid in user_map:
                info = user_map[uid]
                disp_name = get_anonymous_name(uid, info.get("name", "名無し"), info.get("isAnonymousRanking", False))
                result.append({"name": disp_name, "minutes": mins})
            elif uid == user_id:
                 disp_name = get_anonymous_name(uid, student_name, False)
                 result.append({"name": disp_name + " (あなた)", "minutes": mins})
        return result
    def make_team_list(stats):
        result = []
        for t in team_list:
            members = t.get("members", [])
            team_total = 0
            for m_uid in members: team_total += stats.get(m_uid, 0)
            result.append({"name": t.get("name", "No Name"), "minutes": team_total, "count": len(members)})
        result = [r for r in result if r["minutes"] > 0]
        return result
    with tabs[0]:
        st.caption(f"集計期間: {datetime.datetime.now(JST).strftime('%Y/%m/%d')} (今日)")
        display_ranking_table(make_personal_list(stats_day))
    with tabs[1]:
        start_week = (datetime.datetime.now(JST) - datetime.timedelta(days=datetime.datetime.now(JST).weekday()))
        st.caption(f"集計期間: {start_week.strftime('%m/%d')} 〜")
        display_ranking_table(make_personal_list(stats_week))
    with tabs[2]:
        start_month = datetime.datetime.now(JST).replace(day=1)
        st.caption(f"集計期間: {start_month.strftime('%m/%d')} 〜")
        display_ranking_table(make_personal_list(stats_month))
    with tabs[3]:
        st.caption("チームメンバーの今日の合計時間")
        display_ranking_table(make_team_list(stats_day))
    with tabs[4]:
        st.caption("チームメンバーの今週の合計時間")
        display_ranking_table(make_team_list(stats_week))
    with tabs[5]:
        st.caption("チームメンバーの今月の合計時間")
        display_ranking_table(make_team_list(stats_month))

def render_board_page():
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
                        image_url = blob.generate_signed_url(version="v4", expiration=datetime.timedelta(days=7), method="GET")
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
            if p.get("isAnonymous", False): p_name = "匿名ユーザー"
            ts = p.get("createdAt")
            date_str = ts.astimezone(JST).strftime('%Y/%m/%d %H:%M') if ts else ""
            st.markdown(f"#### {p.get('title')}")
            st.caption(f"by {p_name} | {date_str}")
            st.write(p.get("body"))
            if p.get("imageUrl"): st.image(p.get("imageUrl"), use_column_width=True)
            show_comments = st.checkbox(f"💬 コメントを表示 / 返信", key=f"check_{post_id}")
            if show_comments:
                comments_ref = db.collection("posts").document(post_id).collection("comments")
                comments = comments_ref.order_by("timestamp").limit(50).stream()
                for c in comments:
                    c_data = c.to_dict()
                    c_name = c_data.get("authorName", "名無し")
                    if c_data.get("isAnonymous", False): c_name = "匿名ユーザー"
                    c_ts = c_data.get("timestamp")
                    c_date = c_ts.astimezone(JST).strftime('%m/%d %H:%M') if c_ts else ""
                    st.markdown(f"""
                    <div style="background-color:#f9f9f9; padding:8px; border-radius:5px; margin-bottom:5px;">
                        <small><b>{c_name}</b> ({c_date})</small><br>
                        {c_data.get("body", "")}
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

def render_chat_page():
    """(3) AIコーチ画面 (写真選択アイコンのUI改善版)"""
    apply_chat_css()
    st.title("🤖 AI数学コーチ")
    st.caption("教科書の内容を「完璧」に理解しよう。答えは教えません、一緒に解きます。")
    if not st.session_state.messages_loaded:
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
                    if "text" in content: st.markdown(content["text"])
                else: st.markdown(content)
    system_instruction = f"""
    あなたは世界一の「ソクラテス式数学コーチ」です。
    生徒の名前は「{student_name}」さんです。
    【指導ガイドライン】
    1. **回答の禁止**: どんなに求められても、最終的な答えや数式を直接提示してはいけません。
    2. **現状分析**: まず、生徒が質問を見て、「どこまで分かっていて、どこで詰まっているか」を特定してください。
    3. **問いかけ**: 生徒が次に進むための「小さなヒント」や「問いかけ」を投げかけてください。
    4. **アウトプットの要求**: 一方的に解説せず、必ず生徒に考えさせ、返答させてください。
    5. **数式**: 必要であればLaTeX形式（$マーク）を使ってきれいに表示してください。
    """
    
    # フォーム定義: ファイル選択とテキスト入力
    with st.form(key="chat_form", clear_on_submit=True):
        col1, col2, col3 = st.columns([0.8, 5, 1], gap="small")
        with col1:
            # CSSでカメラアイコン化されたアップローダー
            # label_visibility="collapsed" でデフォルトのラベルを隠す
            uploaded_file = st.file_uploader("写真を選択", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed", key="chat_uploader")
        with col2: 
            user_prompt = st.text_area("質問", placeholder="質問を入力...", height=68, label_visibility="collapsed")
        with col3:
            st.write("") 
            submitted = st.form_submit_button("送信")
        
        if submitted:
            # 入力チェック: 画像のみ、テキストのみ、両方OK
            if not user_prompt and not uploaded_file:
                st.warning("質問または画像を入力してください")
            elif not GEMINI_API_KEY:
                st.warning("Gemini APIキーが設定されていません。")
            else:
                upload_img_obj = None
                user_msg_content = user_prompt
                if uploaded_file:
                    try:
                        upload_img_obj = Image.open(uploaded_file)
                        user_msg_content += "\n\n(※画像を送信しました)"
                    except Exception: st.error("画像エラー")
                
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
                        if upload_img_obj: st.image(upload_img_obj, width=200)
                    with st.spinner("AIコーチが思考中..."):
                        genai.configure(api_key=GEMINI_API_KEY)
                        history_for_ai = []
                        MAX_HISTORY_MESSAGES = 20
                        limited_messages = st.session_state.messages[:-1][-MAX_HISTORY_MESSAGES:]
                        for m in limited_messages: 
                            content_str = ""
                            if isinstance(m["content"], dict): content_str = m["content"].get("text", str(m["content"]))
                            else: content_str = str(m["content"])
                            history_for_ai.append({"role": m["role"], "parts": [content_str]})
                        PRIORITY_MODELS = ["gemini-1.5-flash", "gemini-1.5-pro"]
                        ai_text = ""
                        success_model = None
                        error_details = []
                        for model_name in PRIORITY_MODELS:
                            retry_count = 0
                            max_retries = 3
                            while retry_count < max_retries:
                                try:
                                    model = genai.GenerativeModel(model_name, system_instruction=system_instruction)
                                    chat = model.start_chat(history=history_for_ai)
                                    inputs = [user_prompt]
                                    if upload_img_obj: inputs.append(upload_img_obj)
                                    response = chat.send_message(inputs)
                                    ai_text = response.text
                                    success_model = model_name
                                    break 
                                except Exception as e:
                                    retry_count += 1
                                    wait_time = 2 ** retry_count
                                    log_message = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] ⚠️ {model_name} エラー(Try {retry_count}): {e}"
                                    error_details.append(log_message)
                                    st.session_state.debug_logs.append(log_message)
                                    if retry_count < max_retries: time.sleep(wait_time)
                            if success_model: break
                    if success_model:
                        st.session_state.last_used_model = success_model
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
                    else: st.error(f"❌ エラーが発生しました。\n詳細: {error_details}")

# =========================================================
# 8. メイン画面ルーティング
# =========================================================

if "current_page" not in st.session_state:
    if st.session_state.user_role == "student":
        st.session_state.current_page = "portal"
    else:
        st.session_state.current_page = "admin_home" # ★管理者初期ページ

current_page = st.session_state.current_page
user_role = st.session_state.user_role

if user_role == "student":
    if current_page == "portal": render_portal_page()
    elif current_page == "chat": render_chat_page()
    elif current_page == "study_log": render_study_log_page()
    elif current_page == "ranking": render_ranking_page()
    elif current_page == "board": render_board_page()
    elif current_page == "team": render_team_page()
    elif current_page == "contact": render_contact_page()
    else: render_portal_page()

elif user_role in ["global_admin", "team_teacher"]:
    # ★管理者ルーティング拡張
    if current_page == "admin_home": render_admin_home()
    elif current_page == "admin_learning": render_admin_learning()
    elif current_page == "admin_contact": render_admin_contact()
    elif current_page == "admin_roles": render_admin_roles()
    elif current_page == "admin_create_team": render_admin_create_team() 
    elif current_page == "admin_signup": render_admin_signup()
    else: render_admin_home()
else:
    st.error("不正な状態です。")
    if st.button("リセット"):
        st.session_state.clear()
        st.rerun()
