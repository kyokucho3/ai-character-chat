# app.py
import streamlit as st
import anthropic
import os
import hashlib
from dotenv import load_dotenv
from characters.characters import CHARACTERS
from supabase_manager import SupabaseManager
from profile_manager import ProfileManager

# 環境変数の読み込み
load_dotenv()

# ページ設定
st.set_page_config(
    page_title="AI Character Chat",
    page_icon="💬",
    layout="centered"
)

# ==================== 認証機能 ====================

def hash_password(password: str) -> str:
    """パスワードをハッシュ化してユーザーIDとして使用"""
    return hashlib.sha256(password.encode()).hexdigest()

def check_authentication():
    """認証チェック"""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if not st.session_state.authenticated:
        st.title("🔐 ログイン")
        st.write("あなた専用のAIキャラクターチャットです")
        
        password = st.text_input("パスワードを入力", type="password", key="login_password")
        
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("ログイン", use_container_width=True):
                if password:
                    # パスワードをハッシュ化してユーザーIDとして保存
                    st.session_state.user_id = hash_password(password)
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("パスワードを入力してください")
        
        with col2:
            st.caption("💡 任意のパスワードを設定できます。初回入力時に自動で作成されます。")
        
        st.stop()

# 認証チェック
check_authentication()

# ==================== 初期化 ====================

# Supabase接続
@st.cache_resource
def get_supabase_manager(user_id):
    """Supabaseマネージャーを取得（キャッシュ）"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        st.error("Supabase接続情報が設定されていません")
        st.stop()
    
    return SupabaseManager(supabase_url, supabase_key, user_id)

# Anthropic クライアント
@st.cache_resource
def get_anthropic_client():
    """Anthropicクライアントを取得（キャッシュ）"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("Anthropic APIキーが設定されていません")
        st.stop()
    return anthropic.Anthropic(api_key=api_key)

# マネージャー初期化
db = get_supabase_manager(st.session_state.user_id)
client = get_anthropic_client()
profile_manager = ProfileManager(db, os.getenv("ANTHROPIC_API_KEY"))

# セッション状態の初期化
if "current_character" not in st.session_state:
    st.session_state.current_character = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "message_count" not in st.session_state:
    st.session_state.message_count = 0

# ==================== 関数定義 ====================

def get_recent_messages(messages, limit=20):
    """最新N件のメッセージを取得"""
    return messages[-limit:] if len(messages) > limit else messages

def build_system_prompt(character):
    """プロフィール情報を含むシステムプロンプトを構築"""
    base_prompt = character["system_prompt"]
    profile_summary = profile_manager.get_profile_summary()
    
    if profile_summary != "（まだプロフィール情報がありません）":
        enhanced_prompt = f"""{base_prompt}

【ユーザーについての情報】
以下は、これまでの会話で得たユーザーについての情報です。自然に会話の中で活用してください。

{profile_summary}

注意：この情報を唐突に全部話したり、確認したりしないでください。会話の流れの中で自然に思い出したように使ってください。"""
        return enhanced_prompt
    
    return base_prompt

# ==================== UI ====================

# タイトル
st.title("💬 AI Character Chat")

# サイドバー
with st.sidebar:
    # ログアウトボタン
    if st.button("🚪 ログアウト", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.clear()
        st.rerun()
    
    st.divider()
    st.header("キャラクター選択")
    
    # キャラクター選択ボタン
    for char_name, char_info in CHARACTERS.items():
        if st.button(
            f"{char_info['emoji']} {char_name}",
            key=f"select_{char_name}",
            use_container_width=True
        ):
            if st.session_state.current_character != char_name:
                st.session_state.current_character = char_name
                st.session_state.messages = db.load_conversations(char_name)
                st.session_state.message_count = len(st.session_state.messages)
                st.rerun()
    
    # キャラクター情報表示
    if st.session_state.current_character:
        char = CHARACTERS[st.session_state.current_character]
        st.divider()
        st.subheader(f"{char['emoji']} {char['name']}")
        st.caption(char['description'])
        
        # 統計情報
        st.metric("会話数", len(st.session_state.messages))
        
        st.divider()
        
        # プロフィール管理
        with st.expander("📝 あなたのプロフィール"):
            profile_summary = profile_manager.get_profile_summary()
            st.text(profile_summary)
            
            st.caption("プロフィールは会話から自動で更新されます")
            
            # 手動追加フォーム
            with st.form("manual_profile"):
                st.subheader("手動で情報を追加")
                
                info_type = st.selectbox(
                    "種類",
                    ["基本情報", "好きなもの", "苦手なもの", "重要な出来事", "メモ"]
                )
                
                if info_type == "基本情報":
                    key = st.text_input("項目名（例：名前、職業）")
                    value = st.text_input("内容")
                    if st.form_submit_button("追加"):
                        if key and value:
                            profile_manager.update_basic_info(key, value)
                            st.success("追加しました！")
                            st.rerun()
                
                elif info_type == "好きなもの":
                    item = st.text_input("好きなもの")
                    if st.form_submit_button("追加"):
                        if item:
                            profile_manager.add_preference(item, "likes")
                            st.success("追加しました！")
                            st.rerun()
                
                elif info_type == "苦手なもの":
                    item = st.text_input("苦手なもの")
                    if st.form_submit_button("追加"):
                        if item:
                            profile_manager.add_preference(item, "dislikes")
                            st.success("追加しました！")
                            st.rerun()
                
                elif info_type == "重要な出来事":
                    event = st.text_area("出来事")
                    if st.form_submit_button("追加"):
                        if event:
                            profile_manager.add_event(event)
                            st.success("追加しました！")
                            st.rerun()
                
                else:  # メモ
                    note = st.text_area("メモ")
                    if st.form_submit_button("追加"):
                        if note:
                            profile_manager.add_note(note)
                            st.success("追加しました！")
                            st.rerun()
        
        st.divider()
        
        # 会話リセットボタン
        if st.button("🔄 会話をリセット", use_container_width=True):
            db.delete_conversations(st.session_state.current_character)
            st.session_state.messages = []
            st.session_state.message_count = 0
            st.rerun()

# メイン画面
if not st.session_state.current_character:
    st.info("👈 サイドバーからキャラクターを選んでください")
    st.stop()

# メッセージ表示
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# ユーザー入力
if prompt := st.chat_input("メッセージを入力..."):
    # ユーザーメッセージを追加
    st.session_state.messages.append({
        "role": "user",
        "content": prompt
    })
    
    with st.chat_message("user"):
        st.write(prompt)
    
    # Claude APIを呼び出し
    with st.chat_message("assistant"):
        with st.spinner("考え中..."):
            try:
                char = CHARACTERS[st.session_state.current_character]
                system_prompt = build_system_prompt(char)
                recent_messages = get_recent_messages(st.session_state.messages)
                
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=1000,
                    system=system_prompt,
                    messages=recent_messages
                )
                
                assistant_message = response.content[0].text
                st.write(assistant_message)
                
                # アシスタントメッセージを追加
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": assistant_message
                })
                
                # 会話を保存（Supabase）
                db.save_conversations(
                    st.session_state.current_character,
                    st.session_state.messages
                )
                
                # メッセージカウント更新
                st.session_state.message_count = len(st.session_state.messages)
                
                # 5メッセージごとに自動情報抽出
                if st.session_state.message_count % 5 == 0:
                    profile_manager.extract_info_from_conversation(
                        st.session_state.messages
                    )
                
            except Exception as e:
                st.error(f"エラーが発生しました: {str(e)}")