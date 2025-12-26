# profile_manager.py
import json
from datetime import datetime
from anthropic import Anthropic
import os
from datetime import datetime, timezone, timedelta

# 日本時間用のタイムゾーン
JST = timezone(timedelta(hours=9))

class ProfileManager:
    def __init__(self, supabase_manager, anthropic_api_key):
        """
        プロフィール管理（共通 + キャラクター別記憶対応版）
        
        Args:
            supabase_manager: SupabaseManagerインスタンス
            anthropic_api_key: Anthropic APIキー
        """
        self.db = supabase_manager
        self.profile = self.db.load_profile()
        self.client = Anthropic(api_key=anthropic_api_key)
        
        # 新しいデータ構造に移行
        self._migrate_to_new_structure()
    
    def _migrate_to_new_structure(self):
        """旧データ構造から新データ構造への移行"""
        # すでに新しい構造なら何もしない
        if "common_profile" in self.profile and "character_memories" in self.profile:
            return
        
        # 旧データ構造の場合は移行
        try:
            old_basic_info = self.profile.get("basic_info", {})
            old_preferences = self.profile.get("preferences", {"likes": [], "dislikes": []})
            
            # 新しい構造を作成
            self.profile = {
                "common_profile": {
                    "basic_info": old_basic_info if isinstance(old_basic_info, dict) else {},
                    "preferences": {
                        "likes": old_preferences.get("likes", []) if isinstance(old_preferences, dict) else [],
                        "dislikes": old_preferences.get("dislikes", []) if isinstance(old_preferences, dict) else []
                    }
                },
                "character_memories": {},
                "last_updated": self.profile.get("last_updated")
            }
            
            # 保存
            self.db.save_profile(self.profile)
            print("データ構造を新しい形式に移行しました")
            
        except Exception as e:
            # エラーが起きたら完全に新規作成
            print(f"移行エラー、新規作成します: {e}")
            self.profile = {
                "common_profile": {
                    "basic_info": {},
                    "preferences": {
                        "likes": [],
                        "dislikes": []
                    }
                },
                "character_memories": {},
                "last_updated": None
            }
            self.db.save_profile(self.profile)
    
    # ==================== 共通プロフィール ====================
    
    def update_common_info(self, key, value):
        """共通の基本情報を更新"""
        self.profile["common_profile"]["basic_info"][key] = value
        self.db.save_profile(self.profile)
    
    def delete_common_info(self, key):
        """共通の基本情報を削除"""
        if key in self.profile["common_profile"]["basic_info"]:
            del self.profile["common_profile"]["basic_info"][key]
            self.db.save_profile(self.profile)
            return True
        return False
    
    def add_common_preference(self, item, preference_type="likes"):
        """共通の好き・嫌いを追加（重複チェック付き）"""
        items = self.profile["common_profile"]["preferences"][preference_type]
        
        # 完全一致チェック
        if item in items:
            return False
        
        # 小文字で比較（大文字小文字の違いを無視）
        item_lower = item.lower()
        for existing_item in items:
            if existing_item.lower() == item_lower:
                return False
        
        # 重複なしなら追加
        items.append(item)
        self.db.save_profile(self.profile)
        return True
    
    def delete_common_preference(self, item, preference_type="likes"):
        """共通の好き・嫌いを削除"""
        if item in self.profile["common_profile"]["preferences"][preference_type]:
            self.profile["common_profile"]["preferences"][preference_type].remove(item)
            self.db.save_profile(self.profile)
            return True
        return False
    
    def get_common_profile_summary(self):
        """共通プロフィールの要約を取得"""
        common = self.profile["common_profile"]
        summary = []
        
        if common["basic_info"]:
            summary.append("【基本情報】")
            for key, value in common["basic_info"].items():
                summary.append(f"- {key}: {value}")
        
        if common["preferences"]["likes"]:
            summary.append(f"\n【好きなもの】\n- " + "、".join(common["preferences"]["likes"]))
        
        if common["preferences"]["dislikes"]:
            summary.append(f"\n【苦手なもの】\n- " + "、".join(common["preferences"]["dislikes"]))
        
        return "\n".join(summary) if summary else "（まだ情報がありません）"
    
    # ==================== キャラクター別記憶 ====================
    
    def add_character_memory(self, character_name, memory_type, content):
        """キャラクター別の記憶を追加（重複チェック付き）
        
        Args:
            character_name: キャラクター名
            memory_type: "topics", "events", "notes"
            content: 記憶内容
        """
        if character_name not in self.profile["character_memories"]:
            self.profile["character_memories"][character_name] = {
                "topics": [],
                "events": [],
                "notes": []
            }
        
        memories = self.profile["character_memories"][character_name][memory_type]
        
        # イベントにはタイムスタンプを付ける（日本時間）
        if memory_type == "events":
            timestamp = datetime.now(JST).strftime("%Y/%m/%d")
            content_with_timestamp = f"{timestamp}: {content}"
            
            # 完全一致チェック
            if content_with_timestamp in memories:
                return False
        
        # 類似チェック（小文字比較 + 部分一致）
        content_lower = content.lower()
        for existing_memory in memories:
            # タイムスタンプを除外して比較（イベントの場合）
            if memory_type == "events" and ": " in existing_memory:
                existing_content = existing_memory.split(": ", 1)[1].lower()
            else:
                existing_content = existing_memory.lower()
            
            # 完全一致または80%以上の類似
            if existing_content == content_lower:
                return False
            
            # 短い方が長い方に含まれている場合も重複とみなす
            if len(content_lower) < len(existing_content):
                if content_lower in existing_content:
                    return False
            else:
                if existing_content in content_lower:
                    return False
        
        # 重複なしなら追加
        memories.append(content_with_timestamp)
        self.db.save_profile(self.profile)
        return True
    
    def delete_character_memory(self, character_name, memory_type, index):
        """キャラクター別の記憶を削除
        
        Args:
            character_name: キャラクター名
            memory_type: "topics", "events", "notes"
            index: 削除するインデックス
        """
        if character_name in self.profile["character_memories"]:
            memories = self.profile["character_memories"][character_name][memory_type]
            if 0 <= index < len(memories):
                memories.pop(index)
                self.db.save_profile(self.profile)
                return True
        return False
    
    def delete_all_character_memories(self, character_name):
        """特定キャラクターの記憶を全削除"""
        if character_name in self.profile["character_memories"]:
            del self.profile["character_memories"][character_name]
            self.db.save_profile(self.profile)
            return True
        return False
    
    def get_character_memory_summary(self, character_name):
        """キャラクター別記憶の要約を取得"""
        if character_name not in self.profile["character_memories"]:
            return "（まだ記憶がありません）"
        
        memories = self.profile["character_memories"][character_name]
        summary = []
        
        if memories["topics"]:
            summary.append("【話したトピック】")
            for topic in memories["topics"]:
                summary.append(f"- {topic}")
        
        if memories["events"]:
            summary.append("\n【重要な出来事】")
            for event in memories["events"][-5:]:  # 最新5件
                summary.append(f"- {event}")
        
        if memories["notes"]:
            summary.append("\n【メモ】")
            for note in memories["notes"]:
                summary.append(f"- {note}")
        
        return "\n".join(summary) if summary else "（まだ記憶がありません）"
    
    # ==================== システムプロンプト用 ====================
    
    def get_full_context_for_character(self, character_name):
        """特定キャラクター用の完全なコンテキストを取得"""
        context = []
        
        # 共通プロフィール
        common_summary = self.get_common_profile_summary()
        if common_summary != "（まだ情報がありません）":
            context.append("【ユーザーの基本情報（全キャラクター共通）】")
            context.append(common_summary)
        
        # キャラクター別記憶
        char_summary = self.get_character_memory_summary(character_name)
        if char_summary != "（まだ記憶がありません）":
            context.append(f"\n【{character_name}との記憶】")
            context.append(char_summary)
        
        return "\n".join(context) if context else None
    
    # ==================== 自動抽出 ====================
    
    def extract_info_from_conversation(self, character_name, messages):
        """会話から情報を自動抽出（共通 + キャラクター別）"""
        if len(messages) < 4:
            return
        
        recent_messages = messages[-4:]
        conversation_text = "\n".join([
            f"{msg['role']}: {msg['content']}" for msg in recent_messages
        ])
        
        extraction_prompt = f"""以下の会話から、ユーザーに関する重要な情報を抽出してください。

会話:
{conversation_text}

以下のカテゴリに該当する情報があれば、JSON形式で返してください。該当するものがない場合は空のオブジェクトを返してください。

{{
  "common": {{
    "basic_info": {{"キー": "値"}},
    "likes": ["好きなもの1"],
    "dislikes": ["苦手なもの1"]
  }},
  "character_specific": {{
    "topics": ["このキャラクターと話したトピック"],
    "events": ["このキャラクターとの重要な出来事"],
    "notes": ["このキャラクターとの関係性についてのメモ"]
  }}
}}

注意：
- common: 全キャラクターが知っておくべき基本情報（名前、趣味など）
- character_specific: このキャラクターだけが知っている内容
- 明確に言及されている情報のみ抽出
- 推測や憶測は含めない
- JSONのみを返し、他の説明は不要"""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": extraction_prompt}]
            )
            
            result_text = response.content[0].text.strip()
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            extracted = json.loads(result_text)
            
            # 共通情報を追加
            if extracted.get("common"):
                common = extracted["common"]
                
                if common.get("basic_info"):
                    for key, value in common["basic_info"].items():
                        self.update_common_info(key, value)
                
                if common.get("likes"):
                    for item in common["likes"]:
                        self.add_common_preference(item, "likes")
                
                if common.get("dislikes"):
                    for item in common["dislikes"]:
                        self.add_common_preference(item, "dislikes")
            
            # キャラクター別情報を追加
            if extracted.get("character_specific"):
                char_data = extracted["character_specific"]
                
                if char_data.get("topics"):
                    for topic in char_data["topics"]:
                        self.add_character_memory(character_name, "topics", topic)
                
                if char_data.get("events"):
                    for event in char_data["events"]:
                        self.add_character_memory(character_name, "events", event)
                
                if char_data.get("notes"):
                    for note in char_data["notes"]:
                        self.add_character_memory(character_name, "notes", note)
                    
        except Exception as e:
            pass  # エラーは無視

    def optimize_memories(self, character_name):
        """記憶を精査・整理する
        
        Args:
            character_name: キャラクター名
        
        Returns:
            dict: 精査結果の統計
        """
        if character_name not in self.profile["character_memories"]:
            return {"deleted": 0, "summarized": 0}
        
        memories = self.profile["character_memories"][character_name]
        stats = {"deleted": 0, "summarized": 0}
        
        # 各タイプの記憶を精査
        for memory_type in ["topics", "events", "notes"]:
            items = memories[memory_type]
            if len(items) <= 10:  # 10件以下なら精査不要
                continue
            
            # 重複削除（既に実装済みだが念のため）
            original_count = len(items)
            unique_items = []
            seen_lower = set()
            
            for item in items:
                # イベントの場合はタイムスタンプを除外して比較
                if memory_type == "events" and ": " in item:
                    content = item.split(": ", 1)[1].lower()
                else:
                    content = item.lower()
                
                if content not in seen_lower:
                    unique_items.append(item)
                    seen_lower.add(content)
            
            deleted = original_count - len(unique_items)
            stats["deleted"] += deleted
            
            # 50件を超える場合は古いものを要約
            if len(unique_items) > 50:
                # 古い30件を要約、新しい20件は残す
                old_items = unique_items[:-20]
                new_items = unique_items[-20:]
                
                # 要約を作成
                summary = self._summarize_memories(character_name, memory_type, old_items)
                
                # 要約を追加（"summary:" プレフィックス）
                memories[memory_type] = [f"[要約] {summary}"] + new_items
                stats["summarized"] += len(old_items)
            else:
                memories[memory_type] = unique_items
        
        # 保存
        self.db.save_profile(self.profile)
        return stats

    def _summarize_memories(self, character_name, memory_type, items):
        """記憶を要約する（AI使用）
        
        Args:
            character_name: キャラクター名
            memory_type: 記憶のタイプ
            items: 要約する項目リスト
        
        Returns:
            str: 要約テキスト
        """
        type_names = {
            "topics": "話題",
            "events": "出来事",
            "notes": "メモ"
        }
        
        prompt = f"""以下は{character_name}との会話で記録された{type_names[memory_type]}です。
    これらを簡潔に要約してください（3-5行程度）。

    {chr(10).join(f"- {item}" for item in items)}

    要約:"""
        
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return response.content[0].text.strip()
        except Exception as e:
            # エラー時は簡易要約
            return f"{len(items)}件の{type_names[memory_type]}（詳細は省略）"