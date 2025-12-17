# supabase_manager.py
from supabase import create_client, Client
import json
from datetime import datetime
import os

class SupabaseManager:
    def __init__(self, url: str, key: str, user_id: str):
        """
        Supabaseマネージャー初期化
        
        Args:
            url: Supabase Project URL
            key: Supabase anon public key
            user_id: ユーザーID（パスワードから生成したハッシュなど）
        """
        self.client: Client = create_client(url, key)
        self.user_id = user_id
    
    # ==================== プロフィール管理 ====================
    
    def load_profile(self):
        """ユーザープロフィールを読み込む"""
        try:
            response = self.client.table('user_profiles').select('*').eq('user_id', self.user_id).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]['profile_data']
            else:
                # プロフィールが存在しない場合は初期化
                default_profile = {
                    "basic_info": {},
                    "preferences": {
                        "likes": [],
                        "dislikes": []
                    },
                    "important_events": [],
                    "notes": [],
                    "last_updated": None
                }
                self.save_profile(default_profile)
                return default_profile
        except Exception as e:
            print(f"プロフィール読み込みエラー: {e}")
            return {
                "basic_info": {},
                "preferences": {"likes": [], "dislikes": []},
                "important_events": [],
                "notes": [],
                "last_updated": None
            }
    
    def save_profile(self, profile_data):
        """プロフィールを保存"""
        try:
            profile_data['last_updated'] = datetime.now().isoformat()
            
            # upsert（存在すれば更新、なければ挿入）
            self.client.table('user_profiles').upsert(
                {
                    'user_id': self.user_id,
                    'profile_data': profile_data,
                    'updated_at': datetime.now().isoformat()
                },
                on_conflict='user_id'
            ).execute()
            
            return True
        except Exception as e:
            print(f"プロフィール保存エラー: {e}")
            return False
    
    # ==================== 会話履歴管理 ====================
    
    def load_conversations(self, character_name: str):
        """特定キャラクターの会話履歴を読み込む"""
        try:
            response = self.client.table('conversations').select('*').eq('user_id', self.user_id).eq('character_name', character_name).execute()
            
            if response.data and len(response.data) > 0:
                return response.data[0]['messages']
            else:
                return []
        except Exception as e:
            print(f"会話履歴読み込みエラー: {e}")
            return []
    
    def save_conversations(self, character_name: str, messages: list):
        """会話履歴を保存"""
        try:
            # upsert（存在すれば更新、なければ挿入）
            self.client.table('conversations').upsert(
                {
                    'user_id': self.user_id,
                    'character_name': character_name,
                    'messages': messages,
                    'updated_at': datetime.now().isoformat()
                },
                on_conflict='user_id,character_name'
            ).execute()
            
            return True
        except Exception as e:
            print(f"会話履歴保存エラー: {e}")
            return False
    
    def delete_conversations(self, character_name: str):
        """会話履歴を削除"""
        try:
            self.client.table('conversations').delete().eq('user_id', self.user_id).eq('character_name', character_name).execute()
            return True
        except Exception as e:
            print(f"会話履歴削除エラー: {e}")
            return False
    
    def get_all_conversations_count(self):
        """全キャラクターの総会話数を取得"""
        try:
            response = self.client.table('conversations').select('messages').eq('user_id', self.user_id).execute()
            
            total = 0
            if response.data:
                for conv in response.data:
                    total += len(conv.get('messages', []))
            
            return total
        except Exception as e:
            print(f"会話数取得エラー: {e}")
            return 0