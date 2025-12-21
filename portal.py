import streamlit as st
import time

# --- ページ設定 ---
st.set_page_config(page_title="AI数学専属コーチ", page_icon="🎓", layout="centered")

# --- CSSでボタンを「大きなカード」に変身させる ---
st.markdown("""
<style>
    /* 全体のボタンのスタイルをリセット */
    div.stButton > button {
        width: 100%;
        border-radius: 15px;
        border: none;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
        padding: 20px 10px; /* 上下左右の余白 */
    }

    /* ボタン内のテキスト設定 */
    div.stButton > button p {
        font-size: 1.1em;       /* 文字サイズ */
        line-height: 1.5;       /* 行間 */
        white-space: pre-wrap;  /* 改行(\n)を有効にする設定 */
    }

    /* マウスを乗せた時の動き */
    div.stButton > button:hover {
        transform: translateY(-3px); /* ぽよんと浮く */
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
        background-color: #e3e8f0;   /* 少し濃い灰色に */
        color: #1f77b4;              /* 青文字に変化 */
    }
    
    /* 戻るボタンなどの小さなボタン用（必要なら調整） */
    div[data-testid="column"] button {
        height: auto;
    }
</style>
""", unsafe_allow_html=True)

# --- セッション状態の初期化 ---
if "page" not in st.session_state:
    st.session_state.page = "login"
if "user_name" not in st.session_state:
    st.session_state.user_name = None

# --- 画面遷移関数 ---
def navigate_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# =========================================================
# 各画面の定義
# =========================================================

def render_login():
    """ログイン画面"""
    st.title("🎓 AI数学専属コーチ")
    st.info("現在は試運転中のため、どなたでもログインできます。")
    
    with st.form("login_form"):
        name = st.text_input("お名前を教えてください", placeholder="例: 数学 太郎")
        submitted = st.form_submit_button("学習を始める")
        
        if submitted and name:
            st.session_state.user_name = name
            st.session_state.page = "portal"
            st.rerun()

def render_portal():
    """ポータル（メニュー）画面"""
    st.title(f"こんにちは、{st.session_state.user_name}さん👋")
    st.caption("今日は何をしますか？")

    # サマリ表示
    st.info("📊 今週の学習時間: **3時間20分** (目標まであと1時間！)")
    st.markdown("---")

    # --- 大きなカード型ボタンの配置 ---
    # ボタンの文字に「\n\n」を入れることで、タイトルと説明文を分けます
    
    col1, col2 = st.columns(2)
    with col1:
        # AIチャット
        if st.button("🤖 AIコーチ\n\n分からない問題を\n質問しよう", use_container_width=True):
            navigate_to("chat")

    with col2:
        # 学習記録
        if st.button("📝 学習記録\n\n今日の勉強時間を\n記録しよう", use_container_width=True):
            navigate_to("record")

    col3, col4 = st.columns(2)
    with col3:
        # ランキング
        if st.button("🏆 ランキング\n\nみんなの頑張りを\nチェック！", use_container_width=True):
            navigate_to("ranking")

    with col4:
        # バディ機能
        if st.button("🤝 バディ\n\n友達と一緒に\n頑張ろう", use_container_width=True):
            navigate_to("buddy")

    st.markdown("---")
    if st.button("ログアウト"):
        st.session_state.page = "login"
        st.session_state.user_name = None
        st.rerun()

# --- その他の画面（中身はシンプルにしてあります） ---

def render_chat():
    col_back, col_title = st.columns([1, 4])
    with col_back:
        if st.button("🏠 戻る"): navigate_to("portal")
    with col_title:
        st.subheader("🤖 AI数学コーチ")
    st.write("チャット画面です...")
    # ここにチャット機能を実装

def render_record():
    col_back, col_title = st.columns([1, 4])
    with col_back:
        if st.button("🏠 戻る"): navigate_to("portal")
    with col_title:
        st.subheader("📝 学習記録")
    st.write("記録画面です...")

def render_ranking():
    col_back, col_title = st.columns([1, 4])
    with col_back:
        if st.button("🏠 戻る"): navigate_to("portal")
    with col_title:
        st.subheader("🏆 ランキング")
    st.write("ランキング画面です...")

def render_buddy():
    col_back, col_title = st.columns([1, 4])
    with col_back:
        if st.button("🏠 戻る"): navigate_to("portal")
    with col_title:
        st.subheader("🤝 バディ機能")
    st.write("バディ画面です...")

# =========================================================
# メイン処理
# =========================================================

if st.session_state.page == "login":
    render_login()
elif st.session_state.page == "portal":
    render_portal()
elif st.session_state.page == "chat":
    render_chat()
elif st.session_state.page == "record":
    render_record()
elif st.session_state.page == "ranking":
    render_ranking()
elif st.session_state.page == "buddy":
    render_buddy()
