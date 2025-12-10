import streamlit as st

# ==========================================
# 🔐 認証設定（毎月ここを書き換えます）
# ==========================================
CURRENT_PASSWORD = "nagoya2025dec"  # ここを月ごとに変える

# セッション状態の初期化（ログイン状態を管理する箱を作る）
if 'is_logged_in' not in st.session_state:
    st.session_state['is_logged_in'] = False

# ==========================================
# 🚪 ログイン画面の表示
# ==========================================
def login_screen():
    st.title("🔒 名大数学AIチューター")
    st.write("noteで購入した「今月のパスワード」を入力してください。")
    
    password_input = st.text_input("パスワード", type="password")
    
    if st.button("ログイン"):
        if password_input == CURRENT_PASSWORD:
            st.session_state['is_logged_in'] = True
            st.rerun()  # 画面をリロードしてメイン機能へ
        else:
            st.error("パスワードが違います。noteを確認してください。")
            # ここにnoteの販売ページへのリンクを貼ると親切です
            st.markdown("[👉 パスワードの購入はこちら (note)](https://note.com/your_account/...)")

# ==========================================
# 🚀 メイン処理
# ==========================================
if not st.session_state['is_logged_in']:
    # ログインしていない場合、ログイン画面だけ出して終了
    login_screen()
    st.stop()  # これより下のコードは実行されない

# 👇👇👇 ここから下に、いつものAIアプリのコードを書く 👇👇👇

st.title("🤖 AI数学チューター (ログイン済み)")
st.success("ようこそ！")

user_question = st.text_area("質問を入力してください")
# ... (あなたのAIロジック)
