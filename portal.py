import streamlit as st
import time

# --- ページ設定 ---
st.set_page_config(page_title="AI数学専属コーチ", page_icon="🎓", layout="centered")

# --- CSSでボタンをカード風におしゃれにする ---
st.markdown("""
<style>
    .stButton button {
        width: 100%;
        border-radius: 10px;
        height: 3em;
        font-weight: bold;
    }
    .portal-card {
        padding: 20px;
        background-color: #f0f2f6;
        border-radius: 15px;
        margin-bottom: 20px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .portal-title {
        font-size: 1.2em;
        font-weight: bold;
        margin-bottom: 10px;
        color: #1f77b4;
    }
    .portal-desc {
        font-size: 0.9em;
        color: #666;
        margin-bottom: 15px;
    }
</style>
""", unsafe_allow_html=True)

# --- セッション状態の初期化 ---
if "page" not in st.session_state:
    st.session_state.page = "login"  # 初期ページはログイン
if "user_name" not in st.session_state:
    st.session_state.user_name = None

# --- 画面遷移のための関数 ---
def navigate_to(page_name):
    st.session_state.page = page_name
    st.rerun()

# =========================================================
# 各画面（ページ）の定義
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
            st.session_state.page = "portal" # ポータルへ遷移
            st.rerun()

def render_portal():
    """ポータル（メニュー）画面"""
    st.title(f"こんにちは、{st.session_state.user_name}さん👋")
    st.caption("今日は何をしますか？")

    # --- ダッシュボード的なサマリ表示 ---
    # ここに「今週の学習時間」などをチラ見せするとモチベが上がります
    st.info("📊 今週の学習時間: **3時間20分** (目標まであと1時間！)")

    st.markdown("---")

    # --- メニューボタン配置 (2列レイアウト) ---
    col1, col2 = st.columns(2)

    with col1:
        # AIチャットへのリンクカード
        st.markdown("""
        <div class="portal-card">
            <div class="portal-title">🤖 AIコーチ</div>
            <div class="portal-desc">分からない問題を<br>質問しよう</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("チャットを始める", key="btn_chat"):
            navigate_to("chat")

    with col2:
        # 学習記録へのリンクカード
        st.markdown("""
        <div class="portal-card">
            <div class="portal-title">📝 学習記録</div>
            <div class="portal-desc">今日の勉強時間を<br>記録しよう</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("記録をつける", key="btn_record"):
            navigate_to("record")

    col3, col4 = st.columns(2)

    with col3:
        # ランキングへのリンクカード
        st.markdown("""
        <div class="portal-card">
            <div class="portal-title">🏆 ランキング</div>
            <div class="portal-desc">みんなの頑張りを<br>チェック！</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("ランキングを見る", key="btn_rank"):
            navigate_to("ranking")

    with col4:
        # バディ機能へのリンクカード
        st.markdown("""
        <div class="portal-card">
            <div class="portal-title">🤝 バディ</div>
            <div class="portal-desc">友達と一緒に<br>頑張ろう</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("バディを探す", key="btn_buddy"):
            navigate_to("buddy")

    st.markdown("---")
    if st.button("ログアウト", type="secondary"):
        st.session_state.page = "login"
        st.session_state.user_name = None
        st.rerun()

def render_chat():
    """AIチャット画面"""
    # 共通ヘッダー（戻るボタン）
    col_back, col_title = st.columns([1, 4])
    with col_back:
        if st.button("🏠 戻る"):
            navigate_to("portal")
    with col_title:
        st.subheader("🤖 AI数学コーチ")

    st.markdown("ここにチャット機能が入ります...")
    # (ここに以前のチャットコードを移植します)
    st.chat_message("assistant").write("こんにちは！どの問題が分かりませんか？")

def render_record():
    """学習記録画面"""
    col_back, col_title = st.columns([1, 4])
    with col_back:
        if st.button("🏠 戻る"):
            navigate_to("portal")
    with col_title:
        st.subheader("📝 学習記録")
    
    with st.form("record_form"):
        st.number_input("学習時間（分）", min_value=0, step=10)
        st.text_area("一言メモ", placeholder="例: ベクトルの内積が少し分かった")
        st.form_submit_button("記録する")

def render_ranking():
    """ランキング画面"""
    col_back, col_title = st.columns([1, 4])
    with col_back:
        if st.button("🏠 戻る"):
            navigate_to("portal")
    with col_title:
        st.subheader("🏆 今週のランキング")
    
    st.write("1位: ユーザーA (10時間)")
    st.write("2位: ユーザーB (8時間)")
    st.write(f"3位: {st.session_state.user_name} (3時間20分)")

def render_buddy():
    """バディ画面"""
    col_back, col_title = st.columns([1, 4])
    with col_back:
        if st.button("🏠 戻る"):
            navigate_to("portal")
    with col_title:
        st.subheader("🤝 バディ機能")
    
    st.info("招待コード: **12345**")
    st.text_input("友達のコードを入力")
    st.button("連携する")

# =========================================================
# メイン処理：現在のページ状態に応じて表示関数を切り替える
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
