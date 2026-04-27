from flask import Flask, render_template, request, jsonify, make_response
import os, sqlite3, json, calendar
from datetime import datetime
from weasyprint import HTML

app = Flask(__name__, static_folder='static', static_url_path='/static')

DB_PATH = os.path.join(app.root_path, 'data', 'shifts.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- ユーティリティ関数 ---
def type_to_class(type_str):
    mapping = {
        "特休": "sp-leave",
        "法休": "le-holi",
        "年休": "an-leave",
        "午前半休": "HalfDayOffInTheMorning",
        "午後半休": "AfternoonHalfOff",
        "所内": "office",
        "外勤": "outside",
        "夜勤": "night",
        "所内+現場": "office-site",
        "現場": "site",
        "日勤+夜勤": "double",
        "特休夜勤": "sp-holiday-night",
        "非番": "off-duty",
        "重要": "important"
    }
    return mapping.get(type_str, "")

def group_by_user(rows, days):
    result = {}
    for row in rows:
        name = row["name"]
        day = int(row["date"].split("-")[2])
        if name not in result:
            result[name] = [{} for _ in range(days)]
        result[name][day-1] = {
            "type": row["type"],
            "work": row["work"],
            "project": row["project"] or "",
            "cls": type_to_class(row["type"])
        }
    people = [{"name": name, "shifts": shifts} for name, shifts in result.items()]
    return people

# --- ルート定義 ---
@app.route("/")
def index():
    return render_template('index.html')

@app.route("/API")
def api():
    return "Hello, World"

@app.route("/shifts/print")
def print_pdf():
    month = request.args.get("month")
    if not month:
        return "month is required", 400

    year, m = map(int, month.split("-"))
    days = calendar.monthrange(year, m)[1]
    weekdays = ["日","月","火","水","木","金","土"]
    weekday_list = [weekdays[calendar.weekday(year, m, d)] for d in range(1, days+1)]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.name, s.date, s.type, s.work, s.project
        FROM shifts s
        JOIN users u ON s.user_id = u.id
        WHERE strftime('%Y-%m', s.date)=?
        ORDER BY u.id, s.date
    """, (month,))
    rows = cur.fetchall()
    people = group_by_user(rows, days)

    html_str = render_template("shifts/print.html",
                               month=month,
                               people=people,
                               days=days,
                               weekdays=weekday_list)

    pdf = HTML(string=html_str).write_pdf()
    response = make_response(pdf)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"inline; filename=shift_{month}.pdf"
    return response


@app.route("/shifts/dashboard")
def dashboard():
    return render_template('shifts/dashboard.html')

@app.route("/shifts")
def shifts():
    return render_template('shifts/shifts.html')




# 保存先（Flask アプリの app.root_path を基準）
SAVE_DIR = os.path.join(app.root_path, 'static', 'json')
SAVE_PATH = os.path.join(SAVE_DIR, 'shifts.json')

def get_or_create_user(cur, name):
    """既存ユーザーがいればその id を返し、なければ新規追加"""
    cur.execute("SELECT id FROM users WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO users (name) VALUES (?)", (name,))
    return cur.lastrowid

# 初期 shifts.json を作成
os.makedirs(SAVE_DIR, exist_ok=True)
if not os.path.exists(SAVE_PATH) or os.path.getsize(SAVE_PATH) == 0:
    try:
        with open(SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump({"savedAt": None}, f, ensure_ascii=False, indent=2)
    except Exception:
        app.logger.exception("failed to create initial shifts.json")

@app.route('/save-shifts', methods=['POST'])
def save_shifts():
    try:
        data = request.get_json(force=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Invalid JSON format"}), 400

        conn = get_db()
        cur = conn.cursor()
        user_ids = {}

        for month_key, people in data.items():
            year, month = map(int, month_key.split("-"))

            # その月の既存シフトを削除
            cur.execute("DELETE FROM shifts WHERE date LIKE ?", (f"{year:04d}-{month:02d}-%",))

            for person in people:
                name = person.get("name")
                if not name:
                    continue

                # 既存ユーザーを再利用 or 新規追加
                if name not in user_ids:
                    user_ids[name] = get_or_create_user(cur, name)
                user_id = user_ids[name]

                # シフトを保存
                for i, shift in enumerate(person.get("shifts", [])):
                    if not shift:
                        continue
                    day = i + 1
                    date_str = f"{year:04d}-{month:02d}-{day:02d}"
                    project_val = shift.get("project") or ""
                    cur.execute(
                        "INSERT INTO shifts (user_id, date, type, work, project) VALUES (?, ?, ?, ?, ?)",
                        (user_id, date_str, shift.get("type"), shift.get("work"), project_val)
                    )

        conn.commit()
        saved_at = datetime.now().isoformat()

        # メタ情報保存
        try:
            os.makedirs(SAVE_DIR, exist_ok=True)
            meta = {"savedAt": saved_at}
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
        except Exception as meta_err:
            app.logger.warning("failed to write shifts meta file: %s", meta_err)

        return jsonify({"message": "保存成功", "savedAt": saved_at}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/load-months')
def load_months():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT substr(date, 1, 7) AS month FROM shifts ORDER BY month")
    months = [row["month"] for row in cur.fetchall()]
    return jsonify(months)

@app.route('/load-shifts')
def load_shifts():
    month = request.args.get("month")
    if not month:
        return jsonify({"error":"month is required"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.name, s.date, s.type, s.work, s.project
        FROM shifts s
        JOIN users u ON s.user_id = u.id
        WHERE s.date LIKE ?
        ORDER BY u.id, s.date
    """, (f"{month}-%",))

    rows = cur.fetchall()
    result = {}
    for row in rows:
        name = row["name"]
        day = int(row["date"].split("-")[2])
        if name not in result:
            result[name] = {}
        result[name][day] = {"type": row["type"], "work": row["work"], "project": row["project"] or ""}
    final = []
    # total days should be daysInMonth — but keeping original behavior: use max_day from data
    for name, shifts in result.items():
        max_day = max(shifts.keys())
        shift_list = [shifts.get(d, {"type":"休","work":"","project":""}) for d in range(1, max_day + 1)]
        final.append({"name": name, "shifts": shift_list})
    return jsonify(final)


@app.route('/load-shifts-all')
def load_shifts_all():
    year = request.args.get("year")
    if not year:
        return jsonify({"error": "year is required"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.name, s.date, s.type, s.work
        FROM shifts s
        JOIN users u ON s.user_id = u.id
        WHERE s.date LIKE ?
        ORDER BY s.date, u.id
    """, (f"{year}-%",))

    rows = cur.fetchall()
    result = {}

    for row in rows:
        date = row["date"]
        month_key = date[:7]  # YYYY-MM
        day = int(date[8:10])
        name = row["name"]
        if month_key not in result:
            result[month_key] = []
        person_list = result[month_key]

        # 既存の person を探す
        person = next((p for p in person_list if p["name"] == name), None)
        if not person:
            person = {"name": name, "shifts": []}
            person_list.append(person)

        # シフトを day-1 の位置に入れる
        while len(person["shifts"]) < day:
            person["shifts"].append({})
        person["shifts"][day - 1] = {
            "type": row["type"],
            "work": row["work"]
        }

    return jsonify(result)

@app.route('/shifts-meta')
def shifts_meta():
    try:
        app.logger.info("shifts_meta: SAVE_DIR=%s SAVE_PATH=%s", SAVE_DIR, SAVE_PATH)
        if not os.path.exists(SAVE_PATH):
            app.logger.info("shifts_meta: file not found")
            return jsonify({"savedAt": None, "ok": False, "error": "no file"}), 200

        with open(SAVE_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        if not content.strip():
            app.logger.warning("shifts_meta: file is empty")
            return jsonify({"savedAt": None, "ok": False, "error": "empty file"}), 200

        j = json.loads(content)
        app.logger.info("shifts_meta: loaded json keys=%s", list(j.keys()))
        return jsonify({"savedAt": j.get("savedAt"), "ok": True}), 200

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        app.logger.error("shifts_meta error: %s\n%s", str(e), tb)
        return jsonify({"savedAt": None, "ok": False, "error": str(e)}), 500

@app.route("/projects")
def projects_view():
    return render_template("shifts/projects.html")

@app.route("/api/projects", methods=["GET"])
def get_projects():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, project_no, contract_no, contract_name, start_date, end_date, change_count, progress, manager, partner, color FROM projects ORDER BY id")
    rows = cur.fetchall()
    return jsonify([dict(row) for row in rows])

@app.route("/api/projects", methods=["POST"])
def add_project():
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO projects (project_no, contract_no, contract_name, start_date, end_date, change_count, progress, manager, partner, color)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("project_no"),
        data.get("contract_no"),
        data.get("contract_name"),
        data.get("start_date"),
        data.get("end_date"),
        int(data.get("change_count", 0)),
        float(data.get("progress", 0)),
        data.get("manager"),
        data.get("partner"),
        data.get("color", "#999999")
    ))
    conn.commit()
    return jsonify({"message": "project added"})

@app.route("/api/projects/<int:pid>", methods=["DELETE"])
def delete_project(pid):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM projects WHERE id = ?", (pid,))
    conn.commit()
    return jsonify({"message": "project deleted"})

@app.route("/api/projects/<int:pid>", methods=["PUT"])
def update_project(pid):
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE projects
        SET project_no=?, contract_no=?, contract_name=?, start_date=?, end_date=?, change_count=?, progress=?, manager=?, partner=?, color=?
        WHERE id=?
    """, (
        data.get("project_no"),
        data.get("contract_no"),
        data.get("contract_name"),
        data.get("start_date"),
        data.get("end_date"),
        int(data.get("change_count")),
        float(data.get("progress")),
        data.get("manager"),
        data.get("partner"),
        data.get("color"),
        pid
    ))
    conn.commit()
    return jsonify({"message": "project updated"})

# --- ユーザー検索 ---
@app.route("/search_user")
def search_user():
    q = request.args.get("q", "").strip()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM users WHERE name LIKE ?", (f"%{q}%",))
    rows = cur.fetchall()
    return jsonify([{"id": r["id"], "name": r["name"]} for r in rows])

# --- ユーザー追加 ---
@app.route("/add_user", methods=["POST"])
def add_user():
    data = request.get_json()
    name = data.get("name")
    conn = get_db()
    cur = conn.cursor()

    # 既存チェック
    cur.execute("SELECT id, name FROM users WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        return jsonify({"id": row[0], "name": row[1]})

    # 新規追加
    cur.execute("INSERT INTO users (name) VALUES (?)", (name,))
    conn.commit()
    return jsonify({"id": cur.lastrowid, "name": name})


if __name__ == '__main__':
    app.run()