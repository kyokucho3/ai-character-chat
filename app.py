# app.py
import streamlit as st
import anthropic
import os
import hashlib
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from characters.characters import CHARACTERS
from supabase_manager import SupabaseManager
from profile_manager import ProfileManager
import uuid


def chat_message_styled(name, avatar=None):
    """スタイル付きチャットメッセージ用のヘルパー関数"""
    return st.container(key=f"{name}-{uuid.uuid4()}").chat_message(name=name, avatar=avatar)


# 日本時間用のタイムゾーン
JST = timezone(timedelta(hours=9))

WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]

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
        
        if st.button("ログイン", use_container_width=True):
            if password:
                # 環境変数から正しいパスワードを取得
                correct_password = os.getenv("MY_PASSWORD")
                
                if not correct_password:
                    st.error("⚠️ パスワードが設定されていません。管理者に連絡してください。")
                elif password == correct_password:
                    # パスワードが一致
                    st.session_state.user_id = hash_password(password)
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    # パスワードが不一致
                    st.error("❌ パスワードが間違っています")
            else:
                st.error("パスワードを入力してください")
        
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
if "horoscope_sent_today" not in st.session_state:
    st.session_state.horoscope_sent_today = None
if "last_log_extract_count" not in st.session_state:
    st.session_state.last_log_extract_count = 0

# ==================== 関数定義 ====================

def get_recent_messages(messages, limit=20):
    """最新N件のメッセージを取得"""
    return messages[-limit:] if len(messages) > limit else messages

def build_system_prompt(character):
    """プロフィール情報を含むシステムプロンプトを構築"""
    # 現在の日本時間を取得
    now = datetime.now(JST)
    current_time = now.strftime("%Y年%m月%d日 %H:%M")
    day_of_week = WEEKDAYS[now.weekday()]
    
    base_prompt = character["system_prompt"]
    context = profile_manager.get_full_context_for_character(character["name"])
    
    # 時刻情報を追加
    time_info = f"""
現在の日時：{current_time}（{day_of_week}曜日）
※会話の中で必要に応じて時間を参照してください。
"""
    
    # タクミ用のToDo情報
    todo_info = ""
    if character["name"] == "タクミ":
        todo_summary = profile_manager.get_todo_summary()
        if todo_summary:
            todo_info = f"""

【ToDoリスト】
{todo_summary}

※これらのタスクについて質問されたら、優先順位や進め方をアドバイスしてください。
※無理はさせず、小さく始めることを提案してください。
"""
    
    # ヤナギ用のデイリーログ情報
    log_info = ""
    if character["name"] == "ヤナギ":
        log_text = profile_manager.get_recent_logs_summary(3)
        if log_text:
            log_info = f"""

【最近のログ】
{log_text}

※「今週の振り返り」を求められたら、詳しく週次サマリーを話してください。
※自然な会話の中で、今日の出来事や健康面を聞き出してください。
"""
    
    if context or todo_info or log_info:
        enhanced_prompt = f"""{base_prompt}

{time_info}{todo_info}{log_info}

【ユーザーについての情報】
以下は、これまでの会話で得た情報です。自然に会話の中で活用してください。

{context if context else "（まだ情報がありません）"}

注意：この情報を唐突に全部話したり、確認したりしないでください。会話の流れの中で自然に思い出したように使ってください。"""
        return enhanced_prompt
    
    return f"{base_prompt}\n\n{time_info}"

# ==================== UI ====================

st.title("💬 AI Character Chat")

# サイドバー
with st.sidebar:
    # ログアウトボタン（タブの外、常に表示）
    if st.button("🚪 ログアウト", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.clear()
        st.rerun()
    
    st.divider()
    
    # タブを作成
    tab1, tab2 = st.tabs(["💬 チャット", "👤 プロフィール"])
    
    # ==================== タブ1: チャット設定 ====================
    with tab1:
        # ToDoリスト（折りたたみ式）
        with st.expander("✅ ToDoリスト", expanded=False):
            st.caption("タクミと共有できるタスクリスト")
            
            # タスク追加
            with st.form("add_todo_form", clear_on_submit=True):
                col1, col2 = st.columns([4, 1])
                with col1:
                    new_task = st.text_input("新しいタスク", label_visibility="collapsed", placeholder="タスクを入力...")
                with col2:
                    add_button = st.form_submit_button("追加", use_container_width=True)
                
                if add_button and new_task:
                    profile_manager.add_todo(new_task)
                    st.rerun()
            
            # タスク一覧
            todos = profile_manager.get_todos()
            
            if todos:
                # 未完了タスク
                incomplete = [t for t in todos if not t["completed"]]
                if incomplete:
                    st.write("**未完了**")
                    for todo in incomplete:
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            checkbox_key = f"todo_{todo['id']}_incomplete"
                            if st.checkbox(todo["task"], key=checkbox_key, value=False):
                                profile_manager.toggle_todo(todo["id"])
                                st.rerun()
                        with col2:
                            if st.button("🗑️", key=f"del_{todo['id']}", use_container_width=True):
                                profile_manager.delete_todo(todo["id"])
                                st.rerun()
                
                # 完了タスク
                completed = [t for t in todos if t["completed"]]
                if completed:
                    st.write("**完了済み**")
                    for todo in completed:
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            checkbox_key = f"todo_{todo['id']}_completed"
                            if st.checkbox(f"~~{todo['task']}~~", key=checkbox_key, value=True):
                                pass
                            if checkbox_key in st.session_state and not st.session_state[checkbox_key]:
                                profile_manager.toggle_todo(todo["id"])
                                st.rerun()
                        with col2:
                            if st.button("🗑️", key=f"del_{todo['id']}", use_container_width=True):
                                profile_manager.delete_todo(todo["id"])
                                st.rerun()
            else:
                st.caption("タスクがありません")
        
        st.divider()
        
        # モデル設定
        st.subheader("🎯 モデル設定")
        
        model_options = {
            "Haiku (高速・安価)": "claude-haiku-4-5-20251001",
            "Sonnet (推奨)": "claude-sonnet-4-6",
            "Opus (最高品質)": "claude-opus-4-6"
        }
        
        model_descriptions = {
            "Haiku (高速・安価)": "💬 雑談や簡単な会話に最適\n入力: $0.25/M · 出力: $1.25/M",
            "Sonnet (推奨)": "⭐ 通常の会話におすすめ\n入力: $3/M · 出力: $15/M",
            "Opus (最高品質)": "🎓 複雑な相談や深い議論向け\n入力: $15/M · 出力: $75/M"
        }
        
        selected_model_name = st.radio(
            "モデルを選択",
            list(model_options.keys()),
            index=0,
            help="会話の内容に応じてモデルを選択してください"
        )
        
        st.session_state.selected_model = model_options[selected_model_name]
        st.caption(model_descriptions[selected_model_name])
        
        st.divider()
        
        # キャラクター選択
        st.subheader("キャラクター選択")
        
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
            st.metric("会話数", len(st.session_state.messages))
    
    # ==================== タブ2: プロフィール管理 ====================
    with tab2:
        # 共通プロフィール
        st.subheader("🐈 共通プロフィール")
        st.caption("全キャラクターが知っている情報")
        
        try:
            common_summary = profile_manager.get_common_profile_summary()
            st.text(common_summary)
        except Exception as e:
            st.error(f"エラー: {str(e)}")
            st.text("(プロフィール読み込みエラー)")
        
        # 手動追加
        with st.expander("情報を追加"):
            info_type = st.selectbox(
                "種類",
                ["基本情報", "好きなもの", "苦手なもの"],
                key="add_info_type"
            )
            
            if info_type == "基本情報":
                with st.form("add_basic_info"):
                    key = st.text_input("項目名(例:名前、職業)")
                    value = st.text_input("内容")
                    if st.form_submit_button("追加"):
                        if key and value:
                            profile_manager.update_common_info(key, value)
                            st.success("追加しました!")
                            st.rerun()
            
            elif info_type == "好きなもの":
                with st.form("add_like"):
                    item = st.text_input("好きなもの")
                    if st.form_submit_button("追加"):
                        if item:
                            if profile_manager.add_common_preference(item, "likes"):
                                st.success("追加しました!")
                                st.rerun()
                            else:
                                st.warning("すでに登録されています")
            
            else:
                with st.form("add_dislike"):
                    item = st.text_input("苦手なもの")
                    if st.form_submit_button("追加"):
                        if item:
                            if profile_manager.add_common_preference(item, "dislikes"):
                                st.success("追加しました!")
                                st.rerun()
                            else:
                                st.warning("すでに登録されています")
        
        # 削除機能
        with st.expander("情報を削除"):
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
                            st.success("削除しました!")
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
                            st.success("削除しました!")
                            st.rerun()
                else:
                    st.caption("削除する項目がありません")
            
            else:
                if profile["preferences"]["dislikes"]:
                    with st.form("delete_dislike"):
                        item_to_delete = st.selectbox(
                            "削除する項目",
                            profile["preferences"]["dislikes"]
                        )
                        if st.form_submit_button("削除", type="secondary"):
                            profile_manager.delete_common_preference(item_to_delete, "dislikes")
                            st.success("削除しました!")
                            st.rerun()
                else:
                    st.caption("削除する項目がありません")
        
        st.divider()
        
        # キャラクター別記憶
        if st.session_state.current_character:
            char = CHARACTERS[st.session_state.current_character]
            
            st.subheader(f"💭 {char['name']}との記憶")
            
            if "optimization_done" in st.session_state and st.session_state.optimization_done:
                stats = st.session_state.optimization_stats
                st.success(f"🧹 整理完了!(重複削除: {stats['deleted']}件、要約: {stats['summarized']}件)")
                st.session_state.optimization_done = False
            
            st.caption("このキャラクターだけが知っている情報")
            
            char_summary = profile_manager.get_character_memory_summary(char['name'])
            st.text(char_summary)
            
            # 手動追加
            with st.expander("記憶を追加"):
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
                                st.success("追加しました!")
                                st.rerun()
                            else:
                                st.warning("類似の内容がすでに登録されています")
            
            # 削除機能
            with st.expander("記憶を削除"):
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
                                st.success("削除しました!")
                                st.rerun()
                    else:
                        st.caption("削除する項目がありません")
                else:
                    st.caption("まだ記憶がありません")
            
            # 全削除と整理ボタン
            col1, col2 = st.columns(2)
            with col1:
                if st.button(f"🗑️ 全削除", type="secondary", use_container_width=True):
                    if profile_manager.delete_all_character_memories(char['name']):
                        st.success("全ての記憶を削除しました")
                        st.rerun()
            
            with col2:
                if st.button(f"🧹 整理", use_container_width=True):
                    with st.spinner("整理中..."):
                        stats = profile_manager.optimize_memories(char['name'])
                        st.session_state.optimization_done = True
                        st.session_state.optimization_stats = stats
                        st.rerun()
            
            st.divider()
            
            # 会話リセットボタン
            if st.button("🔄 会話をリセット", use_container_width=True):
                db.delete_conversations(st.session_state.current_character)
                st.session_state.messages = []
                st.session_state.message_count = 0
                st.rerun()
            st.divider()
            
    # バックアップ機能
    st.subheader("💾 データバックアップ")

    col1, col2 = st.columns(2)

    with col1:
        # エクスポート
        if st.button("📥 エクスポート", use_container_width=True):
            import json
            backup_data = profile_manager.export_all_data()
            backup_json = json.dumps(backup_data, ensure_ascii=False, indent=2)
            
            # ダウンロードボタン用にセッションステートに保存
            st.session_state.backup_data = backup_json
            st.success("エクスポート準備完了！")

    with col2:
        # インポート
        uploaded_file = st.file_uploader(
            "📤 インポート",
            type=['json'],
            key="import_backup",
            label_visibility="collapsed"
        )
        
        if uploaded_file is not None:
            try:
                import json
                backup_data = json.load(uploaded_file)
                
                if profile_manager.import_data(backup_data):
                    st.success("データを復元しました！")
                    st.rerun()
                else:
                    st.error("データ形式が正しくありません")
            except Exception as e:
                st.error(f"復元エラー: {str(e)}")

    # ダウンロードボタン（エクスポート後に表示）
    if "backup_data" in st.session_state:
        timestamp = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
        filename = f"ai_chat_backup_{timestamp}.json"
        
        st.download_button(
            label="⬇️ ダウンロード",
            data=st.session_state.backup_data,
            file_name=filename,
            mime="application/json",
            use_container_width=True
        )
        
        if st.button("✓ 完了", use_container_width=True):
            del st.session_state.backup_data
            st.rerun()



# メイン画面
if not st.session_state.current_character:
    st.info("👈 サイドバーからキャラクターを選んでください")
    st.stop()



st.html("""
<style>
    /* ユーザーメッセージ（青系） */
    div[class*="st-key-user"] {
        display: flex !important;
        justify-content: flex-end !important;
        margin-bottom: 12px !important;
    }
    
    div[class*="st-key-user"] [data-testid="stChatMessageContent"] {
        background-color: rgba(59, 130, 246, 0.15) !important;
        border-right: 3px solid rgba(59, 130, 246, 0.6) !important;
        border-left: none !important;
        border-radius: 12px !important;
        padding: 8px !important;
        max-width: 80% !important;
    }
    
    /* AIメッセージ（グレー系） */
    div[class*="st-key-assistant"] {
        display: flex !important;
        justify-content: flex-start !important;
        margin-bottom: 12px !important;
    }
    
    div[class*="st-key-assistant"] [data-testid="stChatMessageContent"] {
        background-color: rgba(100, 100, 100, 0.15) !important;
        border-left: 3px solid rgba(150, 150, 150, 0.4) !important;
        border-right: none !important;
        border-radius: 12px !important;
        padding: 8px !important;
        max-width: 80% !important;
    }
    
    /* タイムスタンプ */
    .timestamp {
        font-size: 0.7rem !important;
        color: rgba(150, 150, 150, 0.8) !important;
        margin-top: 4px !important;
        font-style: italic !important;
    }
    
    /* チャット入力欄のフォーカス時の色を変更 */
    textarea[data-testid="stChatInputTextArea"]:focus {
        border-color: rgba(59, 130, 246, 0.6) !important;
        box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.3) !important;
        outline: none !important;
    }
    
    textarea[data-testid="stChatInputTextArea"]:focus-visible {
        outline: none !important;
        border-color: rgba(59, 130, 246, 0.6) !important;
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
    
    # API呼び出し
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
            
            # ヤナギとの会話の場合、デイリーログを抽出（夜19時以降、5メッセージごと）
            if st.session_state.current_character == "ヤナギ":
                current_hour = datetime.now(JST).hour
                msg_since_last = st.session_state.message_count - st.session_state.last_log_extract_count
                if current_hour >= 19 and len(st.session_state.messages) >= 4 and msg_since_last >= 5:
                    profile_manager.extract_log_from_conversation(st.session_state.messages)
                    st.session_state.last_log_extract_count = st.session_state.message_count

            # 50メッセージごとに記憶を整理
            if st.session_state.message_count % 50 == 0:
                profile_manager.optimize_memories(st.session_state.current_character)

            st.rerun()
            
        except Exception as e:
            st.error(f"エラーが発生しました: {str(e)}")