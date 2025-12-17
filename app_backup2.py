# app.py
import streamlit as st
import anthropic
import json
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from characters.characters import CHARACTERS
from profile_manager import ProfileManager

# 環境変数の読み込み
load_dotenv()

# Anthropic クライアント初期化
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# データ保存用ディレクトリ
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# プロフィールマネージャー初期化
profile_manager = ProfileManager()

# ページ設定
st.set_page_config(
    page_title="AI Character Chat",
    page_icon="💬",
    layout="centered"
)

# セッション状態の初期化
if "current_character" not in st.session_state:
    st.session_state.current_character = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "message_count" not in st.session_state:
    st.session_state.message_count = 0

def get_conversation_file(character_name):
    """キャラクターごとの会話ファイルパスを取得"""
    return DATA_DIR / f"{character_name}_conversations.json"

def load_conversations(character_name):
    """会話履歴を読み込む"""
    file_path = get_conversation_file(character_name)
    if file_path.exists():
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_conversations(character_name, messages):
    """会話履歴を保存"""
    file_path = get_conversation_file(character_name)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

def get_recent_messages(messages, limit=20):
    """最新N件のメッセージを取得（Claude APIに送信用）"""
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

# タイトル
st.title("💬 AI Character Chat")

# サイドバー
with st.sidebar:
    st.header("キャラクター選択")
    
    # キャラクター選択ボタン
    for char_name, char_info in CHARACTERS.items():
        if st.button(
            f"{char_info['emoji']} {char_name}",
            key=f"select_{char_name}",
            use_container_width=True
        ):
            # キャラクター切り替え
            if st.session_state.current_character != char_name:
                st.session_state.current_character = char_name
                st.session_state.messages = load_conversations(char_name)
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
            st.session_state.messages = []
            save_conversations(st.session_state.current_character, [])
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
                # システムプロンプトとメッセージを準備
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
                
                # 会話を保存
                save_conversations(
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