# profile_manager.py
import json
from datetime import datetime
from anthropic import Anthropic
import os

class ProfileManager:
    def __init__(self, supabase_manager, anthropic_api_key):
        """
        プロフィール管理（Supabase版）
        
        Args:
            supabase_manager: SupabaseManagerインスタンス
            anthropic_api_key: Anthropic APIキー
        """
        self.db = supabase_manager
        self.profile = self.db.load_profile()
        self.client = Anthropic(api_key=anthropic_api_key)
    
    def update_basic_info(self, key, value):
        """基本情報を更新"""
        self.profile["basic_info"][key] = value
        self.db.save_profile(self.profile)
    
    def add_preference(self, item, preference_type="likes"):
        """好き・嫌いを追加"""
        if item not in self.profile["preferences"][preference_type]:
            self.profile["preferences"][preference_type].append(item)
            self.db.save_profile(self.profile)
    
    def add_event(self, event):
        """重要な出来事を追加"""
        event_data = {
            "content": event,
            "timestamp": datetime.now().isoformat()
        }
        self.profile["important_events"].append(event_data)
        self.db.save_profile(self.profile)
    
    def add_note(self, note):
        """メモを追加"""
        note_data = {
            "content": note,
            "timestamp": datetime.now().isoformat()
        }
        self.profile["notes"].append(note_data)
        self.db.save_profile(self.profile)
    
    def get_profile_summary(self):
        """プロフィールの要約を取得"""
        summary = []
        
        if self.profile["basic_info"]:
            summary.append("【基本情報】")
            for key, value in self.profile["basic_info"].items():
                summary.append(f"- {key}: {value}")
        
        if self.profile["preferences"]["likes"]:
            summary.append(f"\n【好きなもの】\n- " + "、".join(self.profile["preferences"]["likes"]))
        
        if self.profile["preferences"]["dislikes"]:
            summary.append(f"\n【苦手なもの】\n- " + "、".join(self.profile["preferences"]["dislikes"]))
        
        if self.profile["important_events"]:
            summary.append("\n【重要な出来事】")
            for event in self.profile["important_events"][-5:]:  # 最新5件
                summary.append(f"- {event['content']}")
        
        return "\n".join(summary) if summary else "（まだプロフィール情報がありません）"
    
    def extract_info_from_conversation(self, messages):
        """会話から情報を自動抽出"""
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
  "basic_info": {{"キー": "値"}},
  "likes": ["好きなもの1", "好きなもの2"],
  "dislikes": ["苦手なもの1"],
  "events": ["重要な出来事1"],
  "notes": ["その他のメモ1"]
}}

注意：
- 明確に言及されている情報のみ抽出する
- 推測や憶測は含めない
- 重要でない日常会話は無視する
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
            
            # 抽出された情報をプロフィールに追加
            if extracted.get("basic_info"):
                for key, value in extracted["basic_info"].items():
                    self.update_basic_info(key, value)
            
            if extracted.get("likes"):
                for item in extracted["likes"]:
                    self.add_preference(item, "likes")
            
            if extracted.get("dislikes"):
                for item in extracted["dislikes"]:
                    self.add_preference(item, "dislikes")
            
            if extracted.get("events"):
                for event in extracted["events"]:
                    self.add_event(event)
            
            if extracted.get("notes"):
                for note in extracted["notes"]:
                    self.add_note(note)
                    
        except Exception as e:
            pass  # エラーは無視