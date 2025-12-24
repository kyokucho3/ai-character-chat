# app.py
import streamlit as st
import anthropic
import os
import hashlib
from dotenv import load_dotenv
from characters.characters import CHARACTERS
from supabase_manager import SupabaseManager
from profile_manager import ProfileManager
import uuid
from datetime import datetime, timezone, timedelta

def chat_message_styled(name, avatar=None):
    """スタイル付きチャットメッセージ用のヘルパー関数"""
    return st.container(key=f"{name}-{uuid.uuid4()}").chat_message(name=name, avatar=avatar)


# 日本時間用のタイムゾーン
JST = timezone(timedelta(hours=9))

def get_jst_time():
    """日本時間の現在時刻を取得"""
    return datetime.now(JST).strftime("%H:%M")


# 環境変数の読み込み
load_dotenv()

# ページ設定
st.set_page_config(
    page_title="AI Character Chat",
    page_icon="💬",
    layout="centered"
)

# PWA用のメタタグを追加
st.markdown("""
<head>
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#ff4b4b">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="AI Chat">
    <link rel="apple-touch-icon" href="/app/static/icon-192.png">
</head>
""", unsafe_allow_html=True)

# PWA設定を追加
def add_pwa_support():
    """PWAサポートを追加"""
    pwa_script = """
    <head>
        <link rel="manifest" href="/manifest.json">
        <meta name="theme-color" content="#FF4B4B">
        <meta name="mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <meta name="apple-mobile-web-app-title" content="AI Chat">
        <link rel="apple-touch-icon" href="/icon-192.png">
        <script>
            if ('serviceWorker' in navigator) {
                window.addEventListener('load', function() {
                    navigator.serviceWorker.register('/service-worker.js')
                        .then(function(registration) {
                            console.log('ServiceWorker registration successful');
                        })
                        .catch(function(err) {
                            console.log('ServiceWorker registration failed: ', err);
                        });
                });
            }
        </script>
    </head>
    """
    st.markdown(pwa_script, unsafe_allow_html=True)

# PWAサポートを追加
add_pwa_support()

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

@st.cache_resource
def get_supabase_manager(user_id):
    """Supabaseマネージャーを取得"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        st.error("Supabase接続情報が設定されていません")
        st.stop()
    
    return SupabaseManager(supabase_url, supabase_key, user_id)

@st.cache_resource
def get_anthropic_client():
    """Anthropicクライアントを取得"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        st.error("Anthropic APIキーが設定されていません")
        st.stop()
    return anthropic.Anthropic(api_key=api_key)

# マネージャー初期化
db = get_supabase_manager(st.session_state.user_id)
client = get_anthropic_client()

# ProfileManagerをセッション状態で管理（キャッシュ問題を回避）
if "profile_manager" not in st.session_state:
    try:
        st.session_state.profile_manager = ProfileManager(db, os.getenv("ANTHROPIC_API_KEY"))
    except Exception as e:
        st.error(f"ProfileManager初期化エラー: {str(e)}")
        import traceback
        st.text(traceback.format_exc())
        st.stop()

profile_manager = st.session_state.profile_manager

# セッション状態の初期化
if "current_character" not in st.session_state:
    st.session_state.current_character = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "message_count" not in st.session_state:
    st.session_state.message_count = 0
if "selected_model" not in st.session_state:
    st.session_state.selected_model = "claude-sonnet-4-20250514"

# ==================== 関数定義 ====================

def get_recent_messages(messages, limit=20):
    """最新N件のメッセージを取得"""
    return messages[-limit:] if len(messages) > limit else messages

def build_system_prompt(character):
    """プロフィール情報を含むシステムプロンプトを構築"""
    base_prompt = character["system_prompt"]
    context = profile_manager.get_full_context_for_character(character["name"])
    
    if context:
        enhanced_prompt = f"""{base_prompt}

【ユーザーについての情報】
以下は、これまでの会話で得た情報です。自然に会話の中で活用してください。

{context}

注意：この情報を唐突に全部話したり、確認したりしないでください。会話の流れの中で自然に思い出したように使ってください。"""
        return enhanced_prompt
    
    return base_prompt

# ==================== UI ====================

st.title("💬 AI Character Chat")

# サイドバー
with st.sidebar:
    # ログアウトボタン
    if st.button("🚪 ログアウト", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.clear()
        st.rerun()
    
    st.divider()
# モデル選択
    st.subheader("🎯 モデル設定")
    
    model_options = {
        "Haiku (高速・安価)": "claude-haiku-4-5-20251001",
        "Sonnet (推奨)": "claude-sonnet-4-5-20250929",
        "Opus (最高品質)": "claude-opus-4-1-20250805"
    }
    
    model_descriptions = {
        "Haiku (高速・安価)": "💬 雑談や簡単な会話に最適\n入力: $0.25/M · 出力: $1.25/M",
        "Sonnet (推奨)": "⭐ 通常の会話におすすめ\n入力: $3/M · 出力: $15/M",
        "Opus (最高品質)": "🎓 複雑な相談や深い議論向け\n入力: $15/M · 出力: $75/M"
    }
    
    selected_model_name = st.radio(
        "モデルを選択",
        list(model_options.keys()),
        index=1,  # Sonnetをデフォルト
        help="会話の内容に応じてモデルを選択してください"
    )
# 共通プロフィール（常に表示）
    with st.expander("🐈 共通プロフィール"):
        st.caption("全キャラクターが知っている情報")
        
        try:
            common_summary = profile_manager.get_common_profile_summary()
            st.text(common_summary)
        except Exception as e:
            st.error(f"エラー: {str(e)}")
            st.text("（プロフィール読み込みエラー）")
        
        # 手動追加
        st.subheader("情報を追加")
        
        info_type = st.selectbox(
            "種類",
            ["基本情報", "好きなもの", "苦手なもの"],
            key="add_info_type"
        )
        
        
        if info_type == "基本情報":
            with st.form("add_basic_info"):
                key = st.text_input("項目名（例：名前、職業）")
                value = st.text_input("内容")
                if st.form_submit_button("追加"):
                    if key and value:
                        profile_manager.update_common_info(key, value)
                        st.success("追加しました！")
                        st.rerun()
        
        elif info_type == "好きなもの":
            with st.form("add_like"):
                item = st.text_input("好きなもの")
                if st.form_submit_button("追加"):
                    if item:
                        if profile_manager.add_common_preference(item, "likes"):
                            st.success("追加しました！")
                            st.rerun()
                        else:
                            st.warning("すでに登録されています")
    
        else:  # 苦手なもの
            with st.form("add_dislike"):
                item = st.text_input("苦手なもの")
                if st.form_submit_button("追加"):
                    if item:
                        if profile_manager.add_common_preference(item, "dislikes"):
                            st.success("追加しました！")
                            st.rerun()
                        else:
                            st.warning("すでに登録されています")
        
        # 削除機能
        st.subheader("情報を削除")
        
        delete_type = st.selectbox(
            "削除する種類",
            ["基本情報", "好きなもの", "苦手なもの"],
            key="delete_common_type"
        )
        
        profile = profile_manager.profile["common_profile"]
        
        if delete_type == "基本情報":
            if profile["basic_info"]:
                with st.form("delete_basic_info"):
                    item_to_delete = st.selectbox(
                        "削除する項目",
                        list(profile["basic_info"].keys())
                    )
                    if st.form_submit_button("削除", type="secondary"):
                        profile_manager.delete_common_info(item_to_delete)
                        st.success("削除しました！")
                        st.rerun()
            else:
                st.caption("削除する項目がありません")
        
        elif delete_type == "好きなもの":
            if profile["preferences"]["likes"]:
                with st.form("delete_like"):
                    item_to_delete = st.selectbox(
                        "削除する項目",
                        profile["preferences"]["likes"]
                    )
                    if st.form_submit_button("削除", type="secondary"):
                        profile_manager.delete_common_preference(item_to_delete, "likes")
                        st.success("削除しました！")
                        st.rerun()
            else:
                st.caption("削除する項目がありません")
        
        else:  # 苦手なもの
            if profile["preferences"]["dislikes"]:
                with st.form("delete_dislike"):
                    item_to_delete = st.selectbox(
                        "削除する項目",
                        profile["preferences"]["dislikes"]
                    )
                    if st.form_submit_button("削除", type="secondary"):
                        profile_manager.delete_common_preference(item_to_delete, "dislikes")
                        st.success("削除しました！")
                        st.rerun()
            else:
                st.caption("削除する項目がありません")
            
            profile = profile_manager.profile["common_profile"]
            
            if delete_type == "基本情報":
                if profile["basic_info"]:
                    item_to_delete = st.selectbox(
                        "削除する項目",
                        list(profile["basic_info"].keys())
                    )
                    if st.form_submit_button("削除", type="secondary"):
                        profile_manager.delete_common_info(item_to_delete)
                        st.success("削除しました！")
                        st.rerun()
                else:
                    st.caption("削除する項目がありません")
                    st.form_submit_button("削除", disabled=True)
            
            elif delete_type == "好きなもの":
                if profile["preferences"]["likes"]:
                    item_to_delete = st.selectbox(
                        "削除する項目",
                        profile["preferences"]["likes"]
                    )
                    if st.form_submit_button("削除", type="secondary"):
                        profile_manager.delete_common_preference(item_to_delete, "likes")
                        st.success("削除しました！")
                        st.rerun()
                else:
                    st.caption("削除する項目がありません")
                    st.form_submit_button("削除", disabled=True)
            
            else:  # 苦手なもの
                if profile["preferences"]["dislikes"]:
                    item_to_delete = st.selectbox(
                        "削除する項目",
                        profile["preferences"]["dislikes"]
                    )
                    if st.form_submit_button("削除", type="secondary"):
                        profile_manager.delete_common_preference(item_to_delete, "dislikes")
                        st.success("削除しました！")
                        st.rerun()
                else:
                    st.caption("削除する項目がありません")
                    st.form_submit_button("削除", disabled=True)
    
    st.divider()
    st.session_state.selected_model = model_options[selected_model_name]
    st.caption(model_descriptions[selected_model_name])
    

    st.divider()
    st.header("キャラクター選択")
    
    # キャラクター選択ボタン
    for char_i, (char_name, char_info) in enumerate(CHARACTERS.items()):
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
        
        # ==================== キャラクター別記憶管理 ====================
        with st.expander(f"💭 {char['name']}との記憶"):
            st.caption("このキャラクターだけが知っている情報")
            
            char_summary = profile_manager.get_character_memory_summary(char['name'])
            st.text(char_summary)
            
            # 手動追加
            st.subheader("記憶を追加")
            
            memory_type = st.selectbox(
                "種類",
                ["トピック", "出来事", "メモ"],
                key=f"add_memory_type_{char['name']}"
            )
            
            memory_map = {
                "トピック": "topics",
                "出来事": "events",
                "メモ": "notes"
            }
            
            with st.form(f"add_character_memory_{char['name']}_{memory_type}"):
                content = st.text_area("内容", key=f"add_memory_content_{char['name']}_{memory_type}")
                if st.form_submit_button("追加"):
                    if content:
                        if profile_manager.add_character_memory(
                            char['name'],
                            memory_map[memory_type],
                            content
                        ):
                            st.success("追加しました！")
                            st.rerun()
                        else:
                            st.warning("類似の内容がすでに登録されています")
            
            # 削除機能
            st.subheader("記憶を削除")
            
            delete_memory_type = st.selectbox(
                "削除する種類",
                ["トピック", "出来事", "メモ"],
                key=f"delete_char_type_{char['name']}"
            )
            
            memory_type_key = memory_map[delete_memory_type]
            
            if char['name'] in profile_manager.profile["character_memories"]:
                memories = profile_manager.profile["character_memories"][char['name']][memory_type_key]
                
                if memories:
                    with st.form(f"delete_character_memory_{char['name']}_{delete_memory_type}"):
                        # インデックスと内容を表示
                        options = [f"{i}: {mem[:50]}..." if len(mem) > 50 else f"{i}: {mem}" 
                                for i, mem in enumerate(memories)]
                        selected = st.selectbox("削除する項目", options)
                        
                        if st.form_submit_button("削除", type="secondary"):
                            index = int(selected.split(":")[0])
                            profile_manager.delete_character_memory(
                                char['name'],
                                memory_type_key,
                                index
                            )
                            st.success("削除しました！")
                            st.rerun()
                else:
                    st.caption("削除する項目がありません")
            else:
                st.caption("まだ記憶がありません")
            
            # 全削除
            if st.button(f"🗑️ {char['name']}の記憶を全削除", type="secondary", use_container_width=True):
                if profile_manager.delete_all_character_memories(char['name']):
                    st.success("全ての記憶を削除しました")
                    st.rerun()
            
            # 記憶の整理（手動）
            if st.button(f"🧹 {char['name']}の記憶を整理", use_container_width=True):
                with st.spinner("整理中..."):
                    stats = profile_manager.optimize_memories(char['name'])
                    st.success(f"整理完了！（重複削除: {stats['deleted']}件、要約: {stats['summarized']}件）")
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


st.html("""
<style>
    /* ユーザーメッセージ（右寄せ・青系） */
    [class*="st-key-user"] {
        display: flex;
        justify-content: flex-end;
        margin-bottom: 12px;
    }
    
    [class*="st-key-user"] > div {
        background-color: rgba(59, 130, 246, 0.15) !important;
        border-right: 3px solid rgba(59, 130, 246, 0.6);
        border-radius: 12px;
        padding: 8px;
        max-width: 70%;
    }
    
    /* AIメッセージ（左寄せ・グレー系） */
    [class*="st-key-assistant"] {
        display: flex;
        justify-content: flex-start;
        margin-bottom: 12px;
    }
    
    [class*="st-key-assistant"] > div {
        background-color: rgba(100, 100, 100, 0.15) !important;
        border-left: 3px solid rgba(150, 150, 150, 0.4);
        border-radius: 12px;
        padding: 8px;
        max-width: 70%;
    }


    /* チャット入力欄のフォーカス時の色を変更 */
    .stChatInput textarea:focus,
    .stChatInput input:focus {
        border-color: rgba(59, 130, 246, 0.6) !important;
        box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.3) !important;
    }
    
    /* フォーカス時の赤い枠を無効化 */
    .stChatInput textarea:focus-visible,
    .stChatInput input:focus-visible {
        outline: none !important;
    }

    
    /* タイムスタンプ */
    .timestamp {
        font-size: 0.7rem;
        color: rgba(150, 150, 150, 0.8);
        margin-top: 4px;
        font-style: italic;
    }
</style>
""")


# 精査完了の通知
if "optimization_done" in st.session_state and st.session_state.optimization_done:
    stats = st.session_state.optimization_stats
    st.success(f"🧹 記憶を整理しました（重複削除: {stats['deleted']}件、要約: {stats['summarized']}件）")
    st.session_state.optimization_done = False


# メッセージ表示
for message in st.session_state.messages:
    # アバターを設定
    if message["role"] == "user":
        avatar = "🐈"
        role = "user"
    else:
        # キャラクターが選択されているか確認
        if st.session_state.current_character:
            char = CHARACTERS[st.session_state.current_character]
            avatar = char["emoji"]
        else:
            avatar = "🤖"  # デフォルトアバター
        role = "assistant"
    
    with chat_message_styled(name=role, avatar=avatar):
        st.write(message["content"])
        if "timestamp" in message:
            st.markdown(f'<div class="timestamp">{message["timestamp"]}</div>', unsafe_allow_html=True)
    


# ユーザー入力
if prompt := st.chat_input("メッセージを入力..."):
    # ユーザーメッセージを追加
    timestamp = get_jst_time()
    
    st.session_state.messages.append({
        "role": "user",
        "content": prompt,
        "timestamp": timestamp
    })
    
    # API呼び出し（表示はしない、追加だけ）
    with st.spinner("考え中..."):
        try:
            char = CHARACTERS[st.session_state.current_character]
            system_prompt = build_system_prompt(char)
            recent_messages = get_recent_messages(st.session_state.messages)
            
            # timestampフィールドを除外
            cleaned_messages = [
                {"role": msg["role"], "content": msg["content"]}
                for msg in recent_messages
            ]
            
            response = client.messages.create(
                model=st.session_state.selected_model,
                max_tokens=1000,
                system=system_prompt,
                messages=cleaned_messages
            )
            
            assistant_message = response.content[0].text
            timestamp = get_jst_time()
            
            # アシスタントメッセージを追加
            st.session_state.messages.append({
                "role": "assistant",
                "content": assistant_message,
                "timestamp": timestamp
            })
            
            # 会話を保存
            db.save_conversations(
                st.session_state.current_character,
                st.session_state.messages
            )
            
            # メッセージカウント更新
            st.session_state.message_count = len(st.session_state.messages)
            
            # 5メッセージごとに自動情報抽出
            if st.session_state.message_count % 5 == 0:
                profile_manager.extract_info_from_conversation(
                    st.session_state.current_character,
                    st.session_state.messages
                )
            
            # 50メッセージごとに記憶を整理
            if st.session_state.message_count % 50 == 0:
                stats = profile_manager.optimize_memories(st.session_state.current_character)
                if stats["deleted"] > 0 or stats["summarized"] > 0:
                    # 次回の表示時に通知するためフラグを設定
                    st.session_state.optimization_done = True
                    st.session_state.optimization_stats = stats
            # 再読み込みして履歴を表示
            st.rerun()
            
        except Exception as e:
            st.error(f"エラーが発生しました: {str(e)}")