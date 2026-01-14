"""
OuttoTeam - 設定管理
"""
import os
from dotenv import load_dotenv

# .envファイルを読み込む
load_dotenv()

# Azure AD設定
CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = os.getenv("TENANT_ID")

# Microsoft Graph APIのスコープ（必要な権限）
SCOPES = [
    "Calendars.Read",      # Outlookカレンダー読み取り
    "Chat.ReadWrite",      # Teamsチャット読み書き
]

# Teams設定
TEAMS_CHAT_ID = os.getenv("TEAMS_CHAT_ID")

# Microsoft Graph API エンドポイント
GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"

# トークンキャッシュファイル
TOKEN_CACHE_FILE = "token_cache.json"
