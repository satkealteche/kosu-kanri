"""
Outlook週次レポート・Teams投稿モジュール

このモジュールは以下の機能を提供します:
- Outlookカレンダーから1週間のイベントを取得
- イベントの優先度とトレンドを分析
- Teamsの自分のチャットにレポートを投稿
"""

import os
import json
import requests
from datetime import datetime, timedelta
from dateutil import parser as date_parser
from collections import defaultdict
import msal


class MicrosoftGraphClient:
    """Microsoft Graph APIクライアント"""

    GRAPH_API_ENDPOINT = "https://graph.microsoft.com/v1.0"

    def __init__(self):
        self.client_id = os.environ.get("MS_CLIENT_ID")
        self.client_secret = os.environ.get("MS_CLIENT_SECRET")
        self.tenant_id = os.environ.get("MS_TENANT_ID")
        self.scopes = ["https://graph.microsoft.com/.default"]
        self._access_token = None
        self._token_expires = None

    def _get_access_token(self):
        """アクセストークンを取得（キャッシュ対応）"""
        if self._access_token and self._token_expires and datetime.now() < self._token_expires:
            return self._access_token

        if not all([self.client_id, self.client_secret, self.tenant_id]):
            raise ValueError(
                "環境変数が設定されていません: MS_CLIENT_ID, MS_CLIENT_SECRET, MS_TENANT_ID"
            )

        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=authority,
            client_credential=self.client_secret
        )

        result = app.acquire_token_for_client(scopes=self.scopes)

        if "access_token" in result:
            self._access_token = result["access_token"]
            # トークンは通常1時間有効、5分前に更新
            self._token_expires = datetime.now() + timedelta(minutes=55)
            return self._access_token
        else:
            error_msg = result.get("error_description", "不明なエラー")
            raise Exception(f"トークン取得失敗: {error_msg}")

    def _get_headers(self):
        """API呼び出し用ヘッダーを取得"""
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json"
        }

    def get_calendar_events(self, user_id: str, start_date: datetime, end_date: datetime) -> list:
        """
        指定期間のカレンダーイベントを取得

        Args:
            user_id: ユーザーID（メールアドレスまたはオブジェクトID）
            start_date: 開始日時
            end_date: 終了日時

        Returns:
            イベントのリスト
        """
        start_iso = start_date.strftime("%Y-%m-%dT%H:%M:%S")
        end_iso = end_date.strftime("%Y-%m-%dT%H:%M:%S")

        url = (
            f"{self.GRAPH_API_ENDPOINT}/users/{user_id}/calendarView"
            f"?startDateTime={start_iso}&endDateTime={end_iso}"
            f"&$select=subject,start,end,importance,categories,isAllDay,organizer,attendees,location"
            f"&$orderby=start/dateTime"
            f"&$top=100"
        )

        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()

        data = response.json()
        return data.get("value", [])

    def send_chat_message(self, user_id: str, message: str) -> dict:
        """
        自分のチャット（自分自身とのチャット）にメッセージを送信

        Args:
            user_id: ユーザーID
            message: 送信するメッセージ（HTML形式対応）

        Returns:
            送信結果
        """
        # まず自分自身とのチャットを取得または作成
        chat_id = self._get_or_create_self_chat(user_id)

        url = f"{self.GRAPH_API_ENDPOINT}/chats/{chat_id}/messages"

        payload = {
            "body": {
                "contentType": "html",
                "content": message
            }
        }

        response = requests.post(url, headers=self._get_headers(), json=payload)
        response.raise_for_status()

        return response.json()

    def _get_or_create_self_chat(self, user_id: str) -> str:
        """
        自分自身とのチャット（メモ用チャット）を取得

        Args:
            user_id: ユーザーID

        Returns:
            チャットID
        """
        # 既存のチャットを検索
        url = f"{self.GRAPH_API_ENDPOINT}/users/{user_id}/chats?$filter=chatType eq 'oneOnOne'"

        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()

        chats = response.json().get("value", [])

        # 自分自身とのチャットを探す（メンバーが自分だけ）
        for chat in chats:
            chat_id = chat["id"]
            members_url = f"{self.GRAPH_API_ENDPOINT}/chats/{chat_id}/members"
            members_response = requests.get(members_url, headers=self._get_headers())

            if members_response.status_code == 200:
                members = members_response.json().get("value", [])
                # 自分だけのチャットを探す
                if len(members) == 1:
                    return chat_id

        # 見つからない場合は新規作成
        create_url = f"{self.GRAPH_API_ENDPOINT}/chats"
        payload = {
            "chatType": "oneOnOne",
            "members": [
                {
                    "@odata.type": "#microsoft.graph.aadUserConversationMember",
                    "roles": ["owner"],
                    "user@odata.bind": f"https://graph.microsoft.com/v1.0/users/{user_id}"
                }
            ]
        }

        create_response = requests.post(create_url, headers=self._get_headers(), json=payload)
        create_response.raise_for_status()

        return create_response.json()["id"]


class WeeklyScheduleAnalyzer:
    """週次スケジュール分析クラス"""

    # 重要度マッピング
    IMPORTANCE_SCORES = {
        "high": 3,
        "normal": 2,
        "low": 1
    }

    # カテゴリの日本語マッピング
    CATEGORY_TRANSLATIONS = {
        "meeting": "会議",
        "project": "プロジェクト",
        "training": "研修",
        "review": "レビュー",
        "planning": "計画",
        "client": "顧客対応",
        "internal": "社内業務",
        "other": "その他"
    }

    def __init__(self, events: list):
        """
        Args:
            events: Outlookイベントのリスト
        """
        self.events = events
        self.analysis_result = None

    def analyze(self) -> dict:
        """
        週次スケジュールを分析

        Returns:
            分析結果の辞書
        """
        if not self.events:
            return {
                "total_events": 0,
                "total_hours": 0,
                "priority_events": [],
                "category_breakdown": {},
                "daily_load": {},
                "trends": [],
                "recommendations": []
            }

        # 基本統計
        total_events = len(self.events)
        total_hours = 0
        priority_events = []
        category_counts = defaultdict(int)
        daily_events = defaultdict(list)
        organizer_counts = defaultdict(int)

        for event in self.events:
            # 時間計算
            start = date_parser.parse(event["start"]["dateTime"])
            end = date_parser.parse(event["end"]["dateTime"])
            duration_hours = (end - start).total_seconds() / 3600

            if not event.get("isAllDay"):
                total_hours += duration_hours

            # 重要度の高いイベントを抽出
            importance = event.get("importance", "normal")
            if importance == "high":
                priority_events.append({
                    "subject": event["subject"],
                    "start": start.strftime("%Y-%m-%d %H:%M"),
                    "duration_hours": round(duration_hours, 1),
                    "importance": importance
                })

            # カテゴリ集計
            categories = event.get("categories", [])
            if categories:
                for cat in categories:
                    category_counts[cat] += 1
            else:
                category_counts["未分類"] += 1

            # 日別集計
            day_key = start.strftime("%Y-%m-%d (%a)")
            daily_events[day_key].append({
                "subject": event["subject"],
                "duration": duration_hours
            })

            # 主催者集計
            organizer = event.get("organizer", {}).get("emailAddress", {}).get("name", "不明")
            organizer_counts[organizer] += 1

        # 日別負荷計算
        daily_load = {}
        for day, events_list in sorted(daily_events.items()):
            day_hours = sum(e["duration"] for e in events_list)
            daily_load[day] = {
                "event_count": len(events_list),
                "total_hours": round(day_hours, 1)
            }

        # トレンド分析
        trends = self._analyze_trends(daily_load, category_counts, organizer_counts)

        # 推奨事項生成
        recommendations = self._generate_recommendations(
            total_hours, daily_load, category_counts
        )

        self.analysis_result = {
            "total_events": total_events,
            "total_hours": round(total_hours, 1),
            "priority_events": priority_events,
            "category_breakdown": dict(category_counts),
            "daily_load": daily_load,
            "top_organizers": dict(sorted(
                organizer_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]),
            "trends": trends,
            "recommendations": recommendations
        }

        return self.analysis_result

    def _analyze_trends(self, daily_load: dict, category_counts: dict,
                        organizer_counts: dict) -> list:
        """トレンドを分析"""
        trends = []

        # 忙しい日の特定
        if daily_load:
            max_day = max(daily_load.items(), key=lambda x: x[1]["total_hours"])
            if max_day[1]["total_hours"] > 6:
                trends.append(f"最も忙しい日: {max_day[0]} ({max_day[1]['total_hours']}時間)")

        # 主要カテゴリ
        if category_counts:
            top_category = max(category_counts.items(), key=lambda x: x[1])
            trends.append(f"最多カテゴリ: {top_category[0]} ({top_category[1]}件)")

        # 会議主催者の傾向
        if organizer_counts:
            top_organizer = max(organizer_counts.items(), key=lambda x: x[1])
            if top_organizer[1] >= 3:
                trends.append(f"主な主催者: {top_organizer[0]} ({top_organizer[1]}件)")

        return trends

    def _generate_recommendations(self, total_hours: float, daily_load: dict,
                                   category_counts: dict) -> list:
        """推奨事項を生成"""
        recommendations = []

        # 週の総時間が多い場合
        if total_hours > 30:
            recommendations.append("会議時間が多めです。一部の会議を非同期コミュニケーションに置き換えることを検討してください。")

        # 日によって負荷が偏っている場合
        if daily_load:
            hours_list = [d["total_hours"] for d in daily_load.values()]
            if hours_list and max(hours_list) > 2 * min(hours_list) and min(hours_list) > 0:
                recommendations.append("日によって予定の偏りがあります。予定の分散を検討してください。")

        # 未分類が多い場合
        if category_counts.get("未分類", 0) > 5:
            recommendations.append("未分類の予定が多いです。カテゴリを設定すると管理しやすくなります。")

        if not recommendations:
            recommendations.append("バランスの取れたスケジュールです。")

        return recommendations


class WeeklyTeamsReporter:
    """週次レポートをTeamsに投稿するクラス"""

    def __init__(self, graph_client: MicrosoftGraphClient):
        self.graph_client = graph_client

    def generate_report_html(self, analysis: dict, week_start: datetime,
                             week_end: datetime) -> str:
        """
        分析結果からHTMLレポートを生成

        Args:
            analysis: 分析結果
            week_start: 週の開始日
            week_end: 週の終了日

        Returns:
            HTML形式のレポート
        """
        week_range = f"{week_start.strftime('%Y/%m/%d')} - {week_end.strftime('%Y/%m/%d')}"

        html = f"""
<h2>📅 週次スケジュールレポート</h2>
<p><strong>対象期間:</strong> {week_range}</p>

<h3>📊 サマリー</h3>
<ul>
    <li>総予定数: <strong>{analysis['total_events']}件</strong></li>
    <li>総時間: <strong>{analysis['total_hours']}時間</strong></li>
</ul>
"""

        # 優先度の高い予定
        if analysis['priority_events']:
            html += "<h3>🔴 優先度の高い予定</h3><ul>"
            for event in analysis['priority_events']:
                html += f"<li><strong>{event['subject']}</strong> - {event['start']} ({event['duration_hours']}時間)</li>"
            html += "</ul>"

        # 日別負荷
        if analysis['daily_load']:
            html += "<h3>📆 日別予定</h3><ul>"
            for day, load in analysis['daily_load'].items():
                bar = "█" * min(int(load['total_hours']), 10)
                html += f"<li>{day}: {load['event_count']}件 / {load['total_hours']}時間 {bar}</li>"
            html += "</ul>"

        # カテゴリ内訳
        if analysis['category_breakdown']:
            html += "<h3>🏷️ カテゴリ別</h3><ul>"
            for cat, count in sorted(analysis['category_breakdown'].items(),
                                     key=lambda x: x[1], reverse=True):
                html += f"<li>{cat}: {count}件</li>"
            html += "</ul>"

        # トレンド
        if analysis['trends']:
            html += "<h3>📈 トレンド</h3><ul>"
            for trend in analysis['trends']:
                html += f"<li>{trend}</li>"
            html += "</ul>"

        # 推奨事項
        if analysis['recommendations']:
            html += "<h3>💡 推奨事項</h3><ul>"
            for rec in analysis['recommendations']:
                html += f"<li>{rec}</li>"
            html += "</ul>"

        html += f"<hr><p><em>自動生成: {datetime.now().strftime('%Y/%m/%d %H:%M')}</em></p>"

        return html

    def send_weekly_report(self, user_id: str, week_offset: int = 0) -> dict:
        """
        週次レポートを生成してTeamsに送信

        Args:
            user_id: ユーザーID（メールアドレス）
            week_offset: 週のオフセット（0=今週、-1=先週）

        Returns:
            送信結果
        """
        # 週の開始・終了を計算（月曜始まり）
        today = datetime.now()
        week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)

        # カレンダーイベント取得
        events = self.graph_client.get_calendar_events(user_id, week_start, week_end)

        # 分析
        analyzer = WeeklyScheduleAnalyzer(events)
        analysis = analyzer.analyze()

        # レポート生成
        report_html = self.generate_report_html(analysis, week_start, week_end)

        # Teams送信
        result = self.graph_client.send_chat_message(user_id, report_html)

        return {
            "success": True,
            "week_range": f"{week_start.strftime('%Y/%m/%d')} - {week_end.strftime('%Y/%m/%d')}",
            "events_count": len(events),
            "message_id": result.get("id")
        }


def run_weekly_report(user_id: str = None, week_offset: int = 0) -> dict:
    """
    週次レポートを実行するメイン関数

    Args:
        user_id: ユーザーID（環境変数 MS_USER_ID から取得可能）
        week_offset: 週のオフセット（0=今週、-1=先週）

    Returns:
        実行結果
    """
    if not user_id:
        user_id = os.environ.get("MS_USER_ID")

    if not user_id:
        raise ValueError("ユーザーIDが指定されていません（MS_USER_ID環境変数を設定してください）")

    client = MicrosoftGraphClient()
    reporter = WeeklyTeamsReporter(client)

    return reporter.send_weekly_report(user_id, week_offset)


if __name__ == "__main__":
    import sys

    # コマンドライン引数から週オフセットを取得
    week_offset = 0
    if len(sys.argv) > 1:
        try:
            week_offset = int(sys.argv[1])
        except ValueError:
            print("使用方法: python outlook_teams_weekly.py [週オフセット]")
            print("  例: python outlook_teams_weekly.py 0  # 今週")
            print("  例: python outlook_teams_weekly.py -1 # 先週")
            sys.exit(1)

    try:
        result = run_weekly_report(week_offset=week_offset)
        print(f"✅ レポート送信成功")
        print(f"   対象期間: {result['week_range']}")
        print(f"   イベント数: {result['events_count']}")
    except Exception as e:
        print(f"❌ エラー: {e}")
        sys.exit(1)
