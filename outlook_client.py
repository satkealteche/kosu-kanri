"""
OuttoTeam - Outlookカレンダー取得クライアント
"""
import requests
from datetime import datetime, timedelta
from config import GRAPH_API_ENDPOINT


def get_week_range():
    """
    今週の月曜日から日曜日までの日付範囲を取得

    Returns:
        tuple: (開始日時, 終了日時) ISO形式の文字列
    """
    today = datetime.now()
    # 今週の月曜日を計算（0=月曜日）
    monday = today - timedelta(days=today.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    # 日曜日
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

    return monday.isoformat(), sunday.isoformat()


def get_calendar_events(access_token):
    """
    Outlookカレンダーから今週の予定を取得

    Args:
        access_token: Microsoft Graph APIアクセストークン

    Returns:
        list: 予定のリスト
    """
    start_date, end_date = get_week_range()

    # カレンダービューAPIを使用（繰り返し予定も展開される）
    url = f"{GRAPH_API_ENDPOINT}/me/calendarview"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Prefer": 'outlook.timezone="Asia/Tokyo"'
    }

    params = {
        "startDateTime": start_date,
        "endDateTime": end_date,
        "$orderby": "start/dateTime",
        "$select": "subject,start,end,location,isAllDay,bodyPreview"
    }

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        print(f"エラー: カレンダー取得に失敗しました (ステータス: {response.status_code})")
        print(response.text)
        return []

    data = response.json()
    return data.get("value", [])


def format_event(event):
    """
    予定を読みやすい形式にフォーマット

    Args:
        event: 予定データ

    Returns:
        dict: フォーマット済みの予定情報
    """
    start = datetime.fromisoformat(event["start"]["dateTime"].replace("Z", ""))
    end = datetime.fromisoformat(event["end"]["dateTime"].replace("Z", ""))

    if event.get("isAllDay"):
        time_str = "終日"
    else:
        time_str = f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"

    return {
        "subject": event.get("subject", "（件名なし）"),
        "date": start.strftime("%m/%d (%a)"),
        "time": time_str,
        "location": event.get("location", {}).get("displayName", ""),
    }
