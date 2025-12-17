# app.py
import streamlit as st
import anthropic
import json
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from characters.characters import CHARACTERS

# 環境変数の読み込み
load_dotenv()

# Anthropic クライアント初期化
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# データ保存用ディレクトリ
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

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

# タイトル
st.title("💬 AI Character Chat")

# キャラクター選択
st.sidebar.header("キャラクター選択")

for char_name, char_info in CHARACTERS.items():
    if st.sidebar.button(
        f"{char_info['emoji']} {char_name}",
        key=f"select_{char_name}",
        use_container_width=True
    ):
        # キャラクター切り替え
        if st.session_state.current_character != char_name:
            st.session_state.current_character = char_name
            st.session_state.messages = load_conversations(char_name)
            st.rerun()

# キャラクター情報表示
if st.session_state.current_character:
    char = CHARACTERS[st.session_state.current_character]
    st.sidebar.divider()
    st.sidebar.subheader(f"{char['emoji']} {char['name']}")
    st.sidebar.caption(char['description'])
    
    # 会話リセットボタン
    if st.sidebar.button("🔄 会話をリセット", use_container_width=True):
        st.session_state.messages = []
        save_conversations(st.session_state.current_character, [])
        st.rerun()
else:
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
                recent_messages = get_recent_messages(st.session_state.messages)
                
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=1000,
                    system=char["system_prompt"],
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
                
            except Exception as e:
                st.error(f"エラーが発生しました: {str(e)}")

# フッター
st.sidebar.divider()
st.sidebar.caption(f"💾 会話数: {len(st.session_state.messages)}")