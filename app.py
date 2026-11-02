import os
import secrets

from dotenv import load_dotenv
from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from mysql.connector import Error, IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

from analysis import analysis_bp  # noqa: E402
from db import run_query, to_json  # noqa: E402
from web import web_bp  # noqa: E402

app = Flask(__name__)

# ---------- Security settings ----------

if not os.getenv("SECRET_KEY"):
    print("WARNING: SECRET_KEY is missing in your .env file. "
          "You will be logged out every time the app restarts.")
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,  # uploads can be at most 1 MB
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

app.register_blueprint(analysis_bp)
app.register_blueprint(web_bp)

# Used so that a wrong username takes as long to check as a wrong password
DUMMY_HASH = generate_password_hash("not-a-real-password")


def csrf_token():
    """A secret value stored in the session and added to every form."""
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def check_csrf():
    """Reject form posts that did not come from our own pages."""
    if request.method == "POST" and (request.path.startswith("/web") or request.path in ("/login", "/logout")):
        sent = request.form.get("csrf_token", "")
        if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
            abort(400, "Invalid form token. Go back, reload the page and try again.")


@app.before_request
def require_login():
    """Everything except the login page needs a logged-in teacher."""
    if request.endpoint in (None, "login", "static"):
        return None
    if "teacher" in session:
        return None
    if request.path == "/" or request.path.startswith("/web"):
        return redirect(url_for("login"))
    return jsonify(error="Login required. Log in at /login first."), 401


# ---------- Error handlers ----------

@app.errorhandler(IntegrityError)
def handle_integrity_error(error):
    return bad("Duplicate value or invalid reference. Check roll_no, subject name or IDs.", 409)


@app.errorhandler(Error)
def handle_database_error(error):
    app.logger.error("Database error: %s", error)
    if request.path.startswith("/web"):
        return error_page(500, "Database problem", "The app could not reach MySQL. Check that MySQL is running and your .env values are correct.")
    return bad("Database error. Check that MySQL is running and your .env values are correct.", 500)


@app.errorhandler(413)
def file_too_large(error):
    return "File too large. The maximum size is 1 MB.", 413


def error_page(status, title, message):
    return render_template("error.html", status=status, title=title, message=message), status


@app.errorhandler(404)
def not_found(error):
    if request.path.startswith(("/students", "/subjects", "/marks", "/analysis")) and "text/html" not in request.headers.get("Accept", ""):
        return jsonify(error="Not found"), 404
    return error_page(404, "Page not found", "The page you are looking for does not exist.")


@app.errorhandler(400)
def bad_request(error):
    if request.path.startswith("/web") or request.path in ("/login", "/logout"):
        return error_page(400, "Request not accepted", getattr(error, "description", "Please go back and try again."))
    return jsonify(error=getattr(error, "description", "Bad request")), 400


@app.errorhandler(500)
def server_error(error):
    if request.path.startswith("/web"):
        return error_page(500, "Something went wrong", "The server could not finish that request. Please try again.")
    return jsonify(error="Server error"), 500


# ---------- Login and logout ----------

@app.route("/")
def home():
    return redirect(url_for("web.dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        try:
            user = run_query(
                "SELECT username, password_hash FROM users WHERE username = %s",
                (username,), fetch=True, one=True,
            )
        except Error:
            flash("Teacher accounts are not set up yet. Run create_teacher.py first.", "error")
            return render_template("login.html")

        password_ok = check_password_hash(user["password_hash"] if user else DUMMY_HASH, password)
        if user and password_ok:
            session.clear()
            session["teacher"] = user["username"]
            return redirect(url_for("web.dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ---------- JSON API: small validation helpers ----------

def bad(message, code=400):
    return jsonify(error=message), code


def body():
    return request.get_json(silent=True) or {}


def text(data, key):
    return str(data.get(key, "")).strip()


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------- Students ----------

@app.route("/students", methods=["GET"])
def list_students():
    rows = run_query(
        "SELECT student_id, roll_no, name, section FROM students ORDER BY roll_no",
        fetch=True,
    )
    return jsonify(rows)


@app.route("/students/<int:student_id>", methods=["GET"])
def get_student(student_id):
    row = run_query(
        "SELECT student_id, roll_no, name, section FROM students WHERE student_id = %s",
        (student_id,), fetch=True, one=True,
    )
    if not row:
        return bad("Student not found", 404)
    return jsonify(row)


@app.route("/students", methods=["POST"])
def add_student():
    data = body()
    roll_no, name, section = text(data, "roll_no"), text(data, "name"), text(data, "section")
    if not roll_no or not name or not section:
        return bad("roll_no, name and section are required")
    if len(roll_no) > 20 or len(name) > 100 or len(section) > 10:
        return bad("roll_no max 20, name max 100, section max 10 characters")

    _, new_id = run_query(
        "INSERT INTO students (roll_no, name, section) VALUES (%s, %s, %s)",
        (roll_no, name, section),
    )
    return jsonify(message="Student added", student_id=new_id), 201


@app.route("/students/<int:student_id>", methods=["PUT"])
def update_student(student_id):
    exists = run_query("SELECT 1 AS found FROM students WHERE student_id = %s",
                       (student_id,), fetch=True, one=True)
    if not exists:
        return bad("Student not found", 404)

    data = body()
    roll_no, name, section = text(data, "roll_no"), text(data, "name"), text(data, "section")
    if not roll_no or not name or not section:
        return bad("roll_no, name and section are required")

    run_query(
        "UPDATE students SET roll_no = %s, name = %s, section = %s WHERE student_id = %s",
        (roll_no, name, section, student_id),
    )
    return jsonify(message="Student updated")


@app.route("/students/<int:student_id>", methods=["DELETE"])
def delete_student(student_id):
    affected, _ = run_query("DELETE FROM students WHERE student_id = %s", (student_id,))
    if affected == 0:
        return bad("Student not found", 404)
    return jsonify(message="Student deleted (their marks were deleted too)")


# ---------- Subjects ----------

@app.route("/subjects", methods=["GET"])
def list_subjects():
    rows = run_query(
        "SELECT subject_id, subject_name, max_marks, pass_marks FROM subjects ORDER BY subject_name",
        fetch=True,
    )
    return jsonify(rows)


@app.route("/subjects", methods=["POST"])
def add_subject():
    data = body()
    subject_name = text(data, "subject_name")
    max_marks = number(data.get("max_marks", 100))
    pass_marks = number(data.get("pass_marks", 35))

    if not subject_name or len(subject_name) > 100:
        return bad("subject_name is required (max 100 characters)")
    if max_marks is None or pass_marks is None or max_marks <= 0 or pass_marks < 0:
        return bad("max_marks and pass_marks must be valid numbers")
    if max_marks > 999:
        return bad("max_marks cannot be more than 999")
    if pass_marks > max_marks:
        return bad("pass_marks cannot be more than max_marks")

    _, new_id = run_query(
        "INSERT INTO subjects (subject_name, max_marks, pass_marks) VALUES (%s, %s, %s)",
        (subject_name, int(max_marks), int(pass_marks)),
    )
    return jsonify(message="Subject added", subject_id=new_id), 201


# ---------- Marks ----------

MARKS_SELECT = """
    SELECT m.mark_id, s.student_id, s.roll_no, s.name, sub.subject_id,
           sub.subject_name, m.assessment, m.marks_obtained, sub.max_marks
    FROM marks m
    JOIN students s ON s.student_id = m.student_id
    JOIN subjects sub ON sub.subject_id = m.subject_id
"""


@app.route("/marks", methods=["GET"])
def list_marks():
    rows = run_query(MARKS_SELECT + " ORDER BY s.roll_no, sub.subject_name", fetch=True)
    return jsonify(to_json(rows))


@app.route("/marks/<int:mark_id>", methods=["GET"])
def get_mark(mark_id):
    row = run_query(MARKS_SELECT + " WHERE m.mark_id = %s", (mark_id,), fetch=True, one=True)
    if not row:
        return bad("Mark record not found", 404)
    return jsonify(to_json(row))


@app.route("/marks", methods=["POST"])
def add_mark():
    data = body()
    student_id = number(data.get("student_id"))
    subject_id = number(data.get("subject_id"))
    assessment = text(data, "assessment")
    obtained = number(data.get("marks_obtained"))

    if student_id is None or subject_id is None or not assessment or obtained is None:
        return bad("student_id, subject_id, assessment and marks_obtained are required")
    if len(assessment) > 50:
        return bad("assessment can be at most 50 characters")

    student = run_query("SELECT 1 AS found FROM students WHERE student_id = %s",
                        (int(student_id),), fetch=True, one=True)
    if not student:
        return bad("Student not found", 404)

    subject = run_query("SELECT max_marks FROM subjects WHERE subject_id = %s",
                        (int(subject_id),), fetch=True, one=True)
    if not subject:
        return bad("Subject not found", 404)

    if obtained < 0 or obtained > subject["max_marks"]:
        return bad(f"marks_obtained must be between 0 and {subject['max_marks']}")

    _, new_id = run_query(
        "INSERT INTO marks (student_id, subject_id, assessment, marks_obtained) "
        "VALUES (%s, %s, %s, %s)",
        (int(student_id), int(subject_id), assessment, obtained),
    )
    return jsonify(message="Marks added", mark_id=new_id), 201


@app.route("/marks/<int:mark_id>", methods=["PUT"])
def update_mark(mark_id):
    record = run_query(
        "SELECT sub.max_marks FROM marks m JOIN subjects sub ON sub.subject_id = m.subject_id "
        "WHERE m.mark_id = %s",
        (mark_id,), fetch=True, one=True,
    )
    if not record:
        return bad("Mark record not found", 404)

    obtained = number(body().get("marks_obtained"))
    if obtained is None:
        return bad("marks_obtained is required and must be a number")
    if obtained < 0 or obtained > record["max_marks"]:
        return bad(f"marks_obtained must be between 0 and {record['max_marks']}")

    run_query("UPDATE marks SET marks_obtained = %s WHERE mark_id = %s", (obtained, mark_id))
    return jsonify(message="Marks updated")


@app.route("/marks/<int:mark_id>", methods=["DELETE"])
def delete_mark(mark_id):
    affected, _ = run_query("DELETE FROM marks WHERE mark_id = %s", (mark_id,))
    if affected == 0:
        return bad("Mark record not found", 404)
    return jsonify(message="Marks deleted")


if __name__ == "__main__":
    app.run(debug=True)
