"""
OuttoTeam - Outlook予定をTeamsに週次サマリーとして投稿

使い方:
    python main.py           # 週次サマリーを生成してTeamsに投稿
    python main.py --chats   # チャット一覧を表示（TEAMS_CHAT_ID確認用）
"""
import sys
import json
import msal
from datetime import datetime

from config import CLIENT_ID, TENANT_ID, SCOPES, TOKEN_CACHE_FILE
from outlook_client import get_calendar_events, format_event, get_week_range
from teams_client import send_message_to_chat, get_my_chats


def load_token_cache():
    """トークンキャッシュをファイルから読み込む"""
    cache = msal.SerializableTokenCache()
    try:
        with open(TOKEN_CACHE_FILE, "r") as f:
            cache.deserialize(f.read())
    except FileNotFoundError:
        pass
    return cache


def save_token_cache(cache):
    """トークンキャッシュをファイルに保存"""
    if cache.has_state_changed:
        with open(TOKEN_CACHE_FILE, "w") as f:
            f.write(cache.serialize())


def get_access_token():
    """
    Microsoft Graph APIのアクセストークンを取得
    初回はデバイスコードフローで認証、2回目以降はキャッシュを使用
    """
    if not CLIENT_ID or not TENANT_ID:
        print("エラー: CLIENT_IDとTENANT_IDを.envファイルに設定してください")
        print("詳しくはREADME.mdを参照してください")
        sys.exit(1)

    cache = load_token_cache()

    # MSALアプリを作成
    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        token_cache=cache
    )

    # キャッシュからアカウントを取得
    accounts = app.get_accounts()

    if accounts:
        # キャッシュされたトークンで認証を試みる
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            save_token_cache(cache)
            return result["access_token"]

    # デバイスコードフローで認証
    print("\n=== 初回認証が必要です ===")
    flow = app.initiate_device_flow(scopes=SCOPES)

    if "user_code" not in flow:
        print("エラー: デバイスコードフローの開始に失敗しました")
        print(flow.get("error_description", "不明なエラー"))
        sys.exit(1)

    print(flow["message"])
    print("\n上記のURLにアクセスし、コードを入力してください...")

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        print("エラー: 認証に失敗しました")
        print(result.get("error_description", "不明なエラー"))
        sys.exit(1)

    save_token_cache(cache)
    print("認証成功！\n")
    return result["access_token"]


def create_weekly_summary(events):
    """
    予定リストから週次サマリーHTML形式を生成

    Args:
        events: 予定のリスト

    Returns:
        str: HTML形式のサマリー
    """
    start_date, end_date = get_week_range()
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)

    # HTMLヘッダー
    html = f"""<h2>📅 週次予定サマリー</h2>
<p><strong>{start.strftime('%Y年%m月%d日')} 〜 {end.strftime('%m月%d日')}</strong></p>
"""

    if not events:
        html += "<p>今週の予定はありません</p>"
        return html

    # 日付ごとにグループ化
    events_by_date = {}
    for event in events:
        formatted = format_event(event)
        date = formatted["date"]
        if date not in events_by_date:
            events_by_date[date] = []
        events_by_date[date].append(formatted)

    # 日付順にサマリーを生成
    html += "<ul>"
    for date in sorted(events_by_date.keys()):
        html += f"<li><strong>{date}</strong><ul>"
        for event in events_by_date[date]:
            location = f" @ {event['location']}" if event["location"] else ""
            html += f"<li>{event['time']} - {event['subject']}{location}</li>"
        html += "</ul></li>"
    html += "</ul>"

    # 統計情報
    html += f"<p><em>合計: {len(events)}件の予定</em></p>"

    return html


def show_chats(access_token):
    """チャット一覧を表示（TEAMS_CHAT_ID確認用）"""
    print("\n=== 参加中のチャット一覧 ===\n")
    chats = get_my_chats(access_token)

    if not chats:
        print("チャットが見つかりませんでした")
        return

    for chat in chats:
        chat_id = chat.get("id", "")
        chat_type = chat.get("chatType", "")
        topic = chat.get("topic", "")

        # メンバー情報
        members = chat.get("members", [])
        member_names = [m.get("displayName", "不明") for m in members]

        print(f"ID: {chat_id}")
        print(f"  種類: {chat_type}")
        if topic:
            print(f"  トピック: {topic}")
        print(f"  メンバー: {', '.join(member_names)}")
        print()


def main():
    """メイン処理"""
    # コマンドライン引数の確認
    if len(sys.argv) > 1 and sys.argv[1] == "--chats":
        access_token = get_access_token()
        show_chats(access_token)
        return

    print("=" * 50)
    print("OuttoTeam - 週次予定サマリー投稿ツール")
    print("=" * 50)

    # アクセストークン取得
    print("\n1. 認証中...")
    access_token = get_access_token()

    # カレンダー予定取得
    print("2. Outlookカレンダーから予定を取得中...")
    events = get_calendar_events(access_token)
    print(f"   → {len(events)}件の予定を取得しました")

    # サマリー生成
    print("3. 週次サマリーを生成中...")
    summary = create_weekly_summary(events)

    # プレビュー表示
    print("\n--- サマリープレビュー ---")
    # HTMLタグを除去した簡易表示
    preview = summary.replace("<h2>", "\n").replace("</h2>", "\n")
    preview = preview.replace("<p>", "").replace("</p>", "\n")
    preview = preview.replace("<ul>", "").replace("</ul>", "")
    preview = preview.replace("<li>", "  • ").replace("</li>", "\n")
    preview = preview.replace("<strong>", "").replace("</strong>", "")
    preview = preview.replace("<em>", "").replace("</em>", "")
    print(preview)
    print("-" * 30)

    # Teamsに投稿
    print("\n4. Teamsに投稿中...")
    success = send_message_to_chat(access_token, summary)

    if success:
        print("\n✅ 完了！週次サマリーをTeamsに投稿しました")
    else:
        print("\n❌ 投稿に失敗しました。設定を確認してください")


if __name__ == "__main__":
    main()
