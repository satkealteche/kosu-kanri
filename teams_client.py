"""
OuttoTeam - Teamsチャット投稿クライアント
"""
import requests
from config import GRAPH_API_ENDPOINT, TEAMS_CHAT_ID


def send_message_to_chat(access_token, message):
    """
    Teamsのチャットにメッセージを送信

    Args:
        access_token: Microsoft Graph APIアクセストークン
        message: 送信するメッセージ（HTML形式可）

    Returns:
        bool: 送信成功したらTrue
    """
    if not TEAMS_CHAT_ID:
        print("エラー: TEAMS_CHAT_IDが設定されていません")
        return False

    url = f"{GRAPH_API_ENDPOINT}/chats/{TEAMS_CHAT_ID}/messages"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    body = {
        "body": {
            "contentType": "html",
            "content": message
        }
    }

    response = requests.post(url, headers=headers, json=body)

    if response.status_code == 201:
        print("メッセージを送信しました！")
        return True
    else:
        print(f"エラー: メッセージ送信に失敗しました (ステータス: {response.status_code})")
        print(response.text)
        return False


def get_my_chats(access_token):
    """
    自分が参加しているチャット一覧を取得
    （TEAMS_CHAT_IDを確認するためのヘルパー関数）

    Args:
        access_token: Microsoft Graph APIアクセストークン

    Returns:
        list: チャット一覧
    """
    url = f"{GRAPH_API_ENDPOINT}/me/chats"

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    params = {
        "$expand": "members",
        "$top": 20
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        print(f"エラー: チャット一覧取得に失敗しました (ステータス: {response.status_code})")
        return []

    data = response.json()
    return data.get("value", [])
