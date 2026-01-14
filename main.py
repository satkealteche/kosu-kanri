from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import date

app = Flask(__name__)


# --- Outlook/Teams週次レポート機能 ---
try:
    from outlook_teams_weekly import run_weekly_report
    OUTLOOK_TEAMS_ENABLED = True
except ImportError:
    OUTLOOK_TEAMS_ENABLED = False


# DB初期化（初回のみ）
def init_db():
    conn = sqlite3.connect('kousu.db')
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        employee TEXT,
        category TEXT,
        subcategory TEXT,
        hours REAL,
        note TEXT
    )
    ''')
    conn.commit()
    conn.close()


init_db()


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        employee = request.form["employee"]
        category = request.form["category"]
        subcategory = request.form["subcategory"]
        hours = request.form["hours"]
        note = request.form["note"]
        today = date.today().isoformat()

        conn = sqlite3.connect('kousu.db')
        c = conn.cursor()
        c.execute(
            "INSERT INTO records(date, employee, category, subcategory, hours, note) VALUES (?,?,?,?,?,?)",
            (today, employee, category, subcategory, hours, note))
        conn.commit()
        conn.close()

    # データ取得（一覧表示用）
    conn = sqlite3.connect('kousu.db')
    c = conn.cursor()
    c.execute(
        "SELECT date, employee, category, subcategory, hours, note FROM records ORDER BY id DESC"
    )
    rows = c.fetchall()
    conn.close()

    return render_template("index.html", rows=rows)


# --- Outlook/Teams週次レポートAPIエンドポイント ---
@app.route("/api/weekly-report", methods=["POST"])
def trigger_weekly_report():
    """
    週次レポートを手動でトリガーするAPIエンドポイント

    POSTパラメータ:
        week_offset: 週のオフセット（0=今週、-1=先週）
        user_id: ユーザーID（オプション、環境変数から取得可能）
    """
    if not OUTLOOK_TEAMS_ENABLED:
        return jsonify({
            "success": False,
            "error": "Outlook/Teams連携機能が利用できません"
        }), 500

    try:
        data = request.get_json() or {}
        week_offset = data.get("week_offset", 0)
        user_id = data.get("user_id")

        result = run_weekly_report(user_id=user_id, week_offset=week_offset)

        return jsonify({
            "success": True,
            "data": result
        })
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/weekly-report/status", methods=["GET"])
def weekly_report_status():
    """週次レポート機能のステータスを確認"""
    import os

    config_status = {
        "enabled": OUTLOOK_TEAMS_ENABLED,
        "client_id_set": bool(os.environ.get("MS_CLIENT_ID")),
        "client_secret_set": bool(os.environ.get("MS_CLIENT_SECRET")),
        "tenant_id_set": bool(os.environ.get("MS_TENANT_ID")),
        "user_id_set": bool(os.environ.get("MS_USER_ID"))
    }

    all_configured = all([
        config_status["enabled"],
        config_status["client_id_set"],
        config_status["client_secret_set"],
        config_status["tenant_id_set"],
        config_status["user_id_set"]
    ])

    return jsonify({
        "ready": all_configured,
        "config": config_status
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
