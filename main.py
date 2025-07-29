from flask import Flask, render_template, request
import sqlite3
from datetime import date

app = Flask(__name__)


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
