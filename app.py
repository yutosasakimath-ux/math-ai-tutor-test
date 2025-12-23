# ...（前略：render_portal_page関数の途中）

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

    # ここにあった重複コードブロック（古いサイドバー定義やrender_portal_pageの再定義など）を全て削除し、
    # 直後の render_study_log_page へ繋げます。

def render_study_log_page():
    """学習記録画面（修正・削除機能付き）"""
    st.title("📝 学習記録")
# ...（後略）
