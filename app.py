from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
import pdfplumber
import re
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime
from flask import send_file
import io
from flask import session

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ---------------- DATABASE ----------------
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY,
        username TEXT,
        password TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS history(
    id INTEGER PRIMARY KEY,
    username TEXT,
    filename TEXT,
    score INTEGER,
    date TEXT
    )""")

    conn.commit()
    conn.close()

init_db()


# ---------------- TEXT EXTRACTION ----------------
def extract_text(path):
    text = ""

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""

    text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
    return text.lower()


# ---------------- ANALYZER ----------------
def analyze(text):
    text = text.lower()

    programming = ["python", "java", "c++"]
    web = ["html", "css", "javascript"]
    database = ["mysql", "mongodb"]
    tools = ["git", "docker"]
    cs = ["data structures", "os", "dbms"]

    result = {
        "programming": [],
        "web": [],
        "database": [],
        "tools": [],
        "cs_core": []
    }
    session["result"] = result

    # Detect skills
    for skill in programming:
        if skill in text:
            result["programming"].append(skill)

    for skill in web:
        if skill in text:
            result["web"].append(skill)

    for skill in database:
        if skill in text:
            result["database"].append(skill)

    for skill in tools:
        if skill in text:
            result["tools"].append(skill)

    for skill in cs:
        if skill in text:
            result["cs_core"].append(skill)

    #  FIXED BREAKDOWN (MAX 20 PER CATEGORY)
    breakdown = {
        "Programming": min(len(result["programming"]) * 10, 20),
        "Web": min(len(result["web"]) * 7, 20),
        "Database": min(len(result["database"]) * 10, 20),
        "Tools": min(len(result["tools"]) * 10, 20),
        "CS Core": min(len(result["cs_core"]) * 10, 20)
    }

    # TOTAL SCORE (MAX 100)
    score = min(sum(breakdown.values()), 100)

    # Suggestions
    suggestions = []
    if breakdown["Programming"] < 20:
        suggestions.append("Improve Programming skills")
    if breakdown["Web"] < 20:
        suggestions.append("Improve Web skills")
    if breakdown["Database"] < 20:
        suggestions.append("Add Database skills")
    if breakdown["Tools"] < 20:
        suggestions.append("Use tools like Git, Docker")
    if breakdown["CS Core"] < 20:
        suggestions.append("Strengthen CS fundamentals")

    return {
        "score": score,
        "breakdown": breakdown,
        "suggestions": suggestions,
        **result
    }
# ---------------- ROUTES ----------------
@app.route("/", methods=["GET", "POST"])
def index():
    if "user" not in session:
        return redirect("/login")

    result = None

    if request.method == "POST":
        file = request.files["resume"]
        path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(path)

        text = extract_text(path)
        result = analyze(text)

        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("INSERT INTO history(username, filename, score, date) VALUES(?,?,?,?)",
                  (session["user"], file.filename, result["score"], now))
        conn.commit()
        conn.close()

    return render_template("index.html", result=result)


@app.route("/compare", methods=["GET", "POST"])
def compare():
    result = None

    if request.method == "POST":
        f1 = request.files["resume1"]
        f2 = request.files["resume2"]

        p1 = os.path.join(UPLOAD_FOLDER, f1.filename)
        p2 = os.path.join(UPLOAD_FOLDER, f2.filename)

        f1.save(p1)
        f2.save(p2)

        r1 = analyze(extract_text(p1))
        r2 = analyze(extract_text(p2))

        all_skills = ["python","java","c++","html","css","javascript",
                      "mysql","mongodb","git","docker","data structures","os","dbms"]

        def missing(skills):
            return [s for s in all_skills if s not in skills]

        skills1 = r1["programming"] + r1["web"] + r1["database"] + r1["tools"] + r1["cs_core"]
        skills2 = r2["programming"] + r2["web"] + r2["database"] + r2["tools"] + r2["cs_core"]

        result = {
            "r1": r1,
            "r2": r2,
            "better": "Resume 1" if r1["score"] > r2["score"] else "Resume 2",
            "skills1": skills1,
            "skills2": skills2,
            "missing1": missing(skills1),
            "missing2": missing(skills2)
        }

    return render_template("compare.html", result=result)


@app.route("/history")
def history():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT filename, score, date FROM history WHERE username=? ORDER BY id DESC",
              (session["user"],))
    data = c.fetchall()
    conn.close()

    return render_template("history.html", data=data)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (u, p))
        user = c.fetchone()
        conn.close()

        if user:
            session["user"] = u
            return redirect("/")
        else:
            error = "Invalid credentials"

    return render_template("login.html", error=error)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("INSERT INTO users(username,password) VALUES(?,?)", (u, p))
        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("signup.html")


@app.route("/download")
def download_pdf():
    result = session.get("result")

    if not result:
        return "No data found"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer)
    styles = getSampleStyleSheet()

    content = []

    # Title
    content.append(Paragraph("Resume Analysis Report", styles["Title"]))
    content.append(Spacer(1, 10))

    # Score
    content.append(Paragraph(f"Score: {result['score']}%", styles["Heading2"]))
    content.append(Spacer(1, 10))

    # Breakdown
    content.append(Paragraph("Score Breakdown:", styles["Heading3"]))
    for k, v in result["breakdown"].items():
        content.append(Paragraph(f"{k}: {v}%", styles["Normal"]))

    content.append(Spacer(1, 10))

    # Skills
    content.append(Paragraph("Skills Detected:", styles["Heading3"]))

    for key in ["programming", "web", "database", "tools", "cs_core"]:
        if result.get(key):
            content.append(Paragraph(f"{key.title()}: {', '.join(result[key])}", styles["Normal"]))

    content.append(Spacer(1, 10))

    # Suggestions
    content.append(Paragraph("Suggestions:", styles["Heading3"]))
    for s in result["suggestions"]:
        content.append(Paragraph(f"- {s}", styles["Normal"]))

    content.append(Spacer(1, 20))

    # Date
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    content.append(Paragraph(f"Generated on: {now}", styles["Italic"]))

    doc.build(content)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name="Resume_Report.pdf", mimetype="application/pdf")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


if __name__ == "__main__":
    app.run(debug=True)