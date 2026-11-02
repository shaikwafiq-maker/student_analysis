import math
import time

import pandas as pd
from flask import Blueprint, flash, redirect, render_template, request, url_for
from mysql.connector import IntegrityError

from analysis import (build_charts, chart_payload, class_overview, load_marks, records,
                      student_profile, student_summary, subject_stats, support_list, top_students,
                      trend_report)
from db import get_connection, run_query

web_bp = Blueprint("web", __name__, url_prefix="/web")

MARKS_SELECT = """
    SELECT m.mark_id, s.roll_no, s.name, sub.subject_name, m.assessment,
           m.marks_obtained, sub.max_marks
    FROM marks m
    JOIN students s ON s.student_id = m.student_id
    JOIN subjects sub ON sub.subject_id = m.subject_id
"""

CSV_COLUMNS = ["roll_no", "name", "section", "subject_name", "assessment", "marks_obtained"]
MAX_CSV_ROWS = 5000


# ---------- Small helpers ----------

def clean(field):
    return request.form.get(field, "").strip()


def to_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def student_error(roll_no, name, section):
    if not roll_no or not name or not section:
        return "Roll number, name and section are all required."
    if len(roll_no) > 20 or len(name) > 100 or len(section) > 10:
        return "Roll number can be 20 characters, name 100 and section 10 at most."
    return None


def marks_error(obtained, max_marks):
    if obtained is None:
        return "Marks must be a number."
    if obtained < 0 or obtained > max_marks:
        return f"Marks must be between 0 and {int(max_marks)} for this subject."
    return None


# ---------- Dashboard ----------

@web_bp.route("/dashboard")
def dashboard():
    counts = run_query(
        "SELECT (SELECT COUNT(*) FROM students) AS students, "
        "(SELECT COUNT(*) FROM subjects) AS subjects, "
        "(SELECT COUNT(*) FROM marks) AS marks",
        fetch=True, one=True,
    )
    overview, toppers, needs, drops, chart_data = None, [], [], [], None
    df = load_marks()
    if not df.empty:
        summary = student_summary(df)
        overview = class_overview(summary)
        chart_data = chart_payload(summary, subject_stats(df))
        toppers = records(top_students(summary, 3))
        needs = records(support_list(df, summary))
        drops = [r for r in trend_report(df) if r["status"] == "Dropped"]
    return render_template("dashboard.html", counts=counts, overview=overview,
                           toppers=toppers, needs=needs, drops=drops, chart_data=chart_data)


# ---------- Students ----------

@web_bp.route("/students")
def students():
    rows = run_query(
        "SELECT student_id, roll_no, name, section FROM students ORDER BY roll_no",
        fetch=True,
    )
    return render_template("students.html", students=rows)


@web_bp.route("/students/add", methods=["POST"])
def add_student():
    roll_no, name, section = clean("roll_no"), clean("name"), clean("section")
    problem = student_error(roll_no, name, section)
    if problem:
        flash(problem, "error")
    else:
        try:
            run_query("INSERT INTO students (roll_no, name, section) VALUES (%s, %s, %s)",
                      (roll_no, name, section))
            flash(f"Student {name} added.", "success")
        except IntegrityError:
            flash("A student with that roll number already exists.", "error")
    return redirect(url_for("web.students"))


@web_bp.route("/students/<int:student_id>/edit", methods=["GET", "POST"])
def edit_student(student_id):
    student = run_query(
        "SELECT student_id, roll_no, name, section FROM students WHERE student_id = %s",
        (student_id,), fetch=True, one=True,
    )
    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("web.students"))

    if request.method == "POST":
        roll_no, name, section = clean("roll_no"), clean("name"), clean("section")
        problem = student_error(roll_no, name, section)
        if problem:
            flash(problem, "error")
            student.update(roll_no=roll_no, name=name, section=section)
        else:
            try:
                run_query(
                    "UPDATE students SET roll_no = %s, name = %s, section = %s WHERE student_id = %s",
                    (roll_no, name, section, student_id),
                )
                flash("Student updated.", "success")
                return redirect(url_for("web.students"))
            except IntegrityError:
                flash("Another student already has that roll number.", "error")
                student.update(roll_no=roll_no, name=name, section=section)
    return render_template("student_edit.html", student=student)


@web_bp.route("/students/<int:student_id>/delete", methods=["POST"])
def delete_student(student_id):
    affected, _ = run_query("DELETE FROM students WHERE student_id = %s", (student_id,))
    flash("Student and their marks deleted." if affected else "Student not found.",
          "success" if affected else "error")
    return redirect(url_for("web.students"))


# ---------- Subjects ----------

@web_bp.route("/subjects")
def subjects():
    rows = run_query(
        "SELECT subject_id, subject_name, max_marks, pass_marks FROM subjects ORDER BY subject_name",
        fetch=True,
    )
    return render_template("subjects.html", subjects=rows)


@web_bp.route("/subjects/add", methods=["POST"])
def add_subject():
    name = clean("subject_name")
    max_marks = to_number(clean("max_marks") or "100")
    pass_marks = to_number(clean("pass_marks") or "35")

    if not name or len(name) > 100:
        flash("Subject name is required (100 characters at most).", "error")
    elif max_marks is None or pass_marks is None or max_marks <= 0 or pass_marks < 0:
        flash("Maximum marks and pass marks must be valid numbers.", "error")
    elif max_marks > 999:
        flash("Maximum marks cannot be more than 999.", "error")
    elif pass_marks > max_marks:
        flash("Pass marks cannot be more than maximum marks.", "error")
    else:
        try:
            run_query(
                "INSERT INTO subjects (subject_name, max_marks, pass_marks) VALUES (%s, %s, %s)",
                (name, int(max_marks), int(pass_marks)),
            )
            flash(f"Subject {name} added.", "success")
        except IntegrityError:
            flash("That subject already exists.", "error")
    return redirect(url_for("web.subjects"))


@web_bp.route("/subjects/<int:subject_id>/delete", methods=["POST"])
def delete_subject(subject_id):
    affected, _ = run_query("DELETE FROM subjects WHERE subject_id = %s", (subject_id,))
    flash("Subject and its marks deleted." if affected else "Subject not found.",
          "success" if affected else "error")
    return redirect(url_for("web.subjects"))


# ---------- Marks ----------

@web_bp.route("/marks")
def marks():
    rows = run_query(MARKS_SELECT + " ORDER BY s.roll_no, sub.subject_name, m.assessment", fetch=True)
    student_list = run_query("SELECT student_id, roll_no, name FROM students ORDER BY roll_no", fetch=True)
    subject_list = run_query("SELECT subject_id, subject_name, max_marks FROM subjects ORDER BY subject_name", fetch=True)
    return render_template("marks.html", marks=rows, students=student_list, subjects=subject_list)


@web_bp.route("/marks/add", methods=["POST"])
def add_mark():
    student_id = to_number(request.form.get("student_id"))
    subject_id = to_number(request.form.get("subject_id"))
    assessment = clean("assessment")
    obtained = to_number(clean("marks_obtained"))

    if student_id is None or subject_id is None or not assessment or obtained is None:
        flash("Please choose a student and subject, and fill in assessment and marks.", "error")
        return redirect(url_for("web.marks"))
    if len(assessment) > 50:
        flash("Assessment name can be 50 characters at most.", "error")
        return redirect(url_for("web.marks"))

    student = run_query("SELECT 1 AS found FROM students WHERE student_id = %s",
                        (int(student_id),), fetch=True, one=True)
    subject = run_query("SELECT max_marks FROM subjects WHERE subject_id = %s",
                        (int(subject_id),), fetch=True, one=True)
    if not student or not subject:
        flash("Student or subject not found.", "error")
        return redirect(url_for("web.marks"))

    problem = marks_error(obtained, subject["max_marks"])
    if problem:
        flash(problem, "error")
        return redirect(url_for("web.marks"))

    try:
        run_query(
            "INSERT INTO marks (student_id, subject_id, assessment, marks_obtained) VALUES (%s, %s, %s, %s)",
            (int(student_id), int(subject_id), assessment, obtained),
        )
        flash("Marks added.", "success")
    except IntegrityError:
        flash("Marks already exist for this student, subject and assessment. Edit them instead.", "error")
    return redirect(url_for("web.marks"))


@web_bp.route("/marks/<int:mark_id>/edit", methods=["GET", "POST"])
def edit_mark(mark_id):
    record = run_query(MARKS_SELECT + " WHERE m.mark_id = %s", (mark_id,), fetch=True, one=True)
    if not record:
        flash("Mark record not found.", "error")
        return redirect(url_for("web.marks"))

    if request.method == "POST":
        obtained = to_number(clean("marks_obtained"))
        problem = marks_error(obtained, record["max_marks"])
        if problem:
            flash(problem, "error")
        else:
            run_query("UPDATE marks SET marks_obtained = %s WHERE mark_id = %s", (obtained, mark_id))
            flash("Marks updated.", "success")
            return redirect(url_for("web.marks"))
    return render_template("mark_edit.html", record=record)


@web_bp.route("/marks/<int:mark_id>/delete", methods=["POST"])
def delete_mark(mark_id):
    affected, _ = run_query("DELETE FROM marks WHERE mark_id = %s", (mark_id,))
    flash("Marks deleted." if affected else "Mark record not found.",
          "success" if affected else "error")
    return redirect(url_for("web.marks"))


# ---------- CSV upload ----------

def process_csv(file):
    """Check every row first. Save everything only if the whole file is valid."""
    try:
        df = pd.read_csv(file, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except ValueError:
        return {"errors": ["Could not read the file. Save it as a plain CSV (comma separated) and try again."]}

    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = [c for c in CSV_COLUMNS if c not in df.columns]
    if missing:
        return {"errors": ["Missing column(s): " + ", ".join(missing) +
                           ". The first line must be: " + ",".join(CSV_COLUMNS)]}
    if df.empty:
        return {"errors": ["The file has no data rows."]}
    if len(df) > MAX_CSV_ROWS:
        return {"errors": [f"Too many rows. The limit is {MAX_CSV_ROWS} rows per upload."]}

    subjects = {
        row["subject_name"].lower(): row
        for row in run_query("SELECT subject_id, subject_name, max_marks FROM subjects", fetch=True)
    }
    students = {
        row["roll_no"].lower(): row["student_id"]
        for row in run_query("SELECT student_id, roll_no FROM students", fetch=True)
    }
    existing_marks = {
        (row["roll_no"].lower(), row["subject_id"], row["assessment"].lower()): float(row["marks_obtained"])
        for row in run_query(
            "SELECT s.roll_no, m.subject_id, m.assessment, m.marks_obtained "
            "FROM marks m JOIN students s ON s.student_id = m.student_id",
            fetch=True,
        )
    }

    errors, rows, new_students, seen = [], [], {}, set()
    for line, record in enumerate(df.to_dict("records"), start=2):  # line 1 is the header
        roll_no = record["roll_no"].strip()
        name = record["name"].strip()
        section = record["section"].strip()
        subject_name = record["subject_name"].strip()
        assessment = record["assessment"].strip()
        obtained = to_number(record["marks_obtained"].strip())

        problems = []
        if not roll_no or len(roll_no) > 20:
            problems.append("roll_no is required (20 characters at most)")
        roll_key = roll_no.lower()
        if roll_key not in students and roll_key not in new_students:
            if not name or not section or len(name) > 100 or len(section) > 10:
                problems.append("new student needs a name (100 characters) and section (10 characters)")
        subject = subjects.get(subject_name.lower())
        if not subject:
            problems.append(f"unknown subject '{subject_name}' (add the subject first)")
        if not assessment or len(assessment) > 50:
            problems.append("assessment is required (50 characters at most)")
        if subject:
            problem = marks_error(obtained, subject["max_marks"])
            if problem:
                problems.append(problem.lower())
        key = (roll_no.lower(), subject_name.lower(), assessment.lower())
        if key in seen:
            problems.append("this student, subject and assessment appear twice in the file")
        seen.add(key)

        if problems:
            errors.append(f"Line {line}: " + "; ".join(problems))
            continue
        if roll_key not in students and roll_key not in new_students:
            new_students[roll_key] = (roll_no, name, section)
        rows.append((roll_key, subject["subject_id"], assessment, obtained))

    if errors:
        return {"errors": errors[:20], "error_count": len(errors)}

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    added = updated = unchanged = 0
    try:
        student_ids = dict(students)
        for roll_key, (roll_no, name, section) in new_students.items():
            cursor.execute("INSERT INTO students (roll_no, name, section) VALUES (%s, %s, %s)",
                           (roll_no, name, section))
            student_ids[roll_key] = cursor.lastrowid
        for roll_key, subject_id, assessment, obtained in rows:
            before = existing_marks.get((roll_key, subject_id, assessment.lower()))
            if before is None:
                added += 1
            elif before == obtained:
                unchanged += 1
                continue
            else:
                updated += 1
            cursor.execute(
                "INSERT INTO marks (student_id, subject_id, assessment, marks_obtained) "
                "VALUES (%s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE marks_obtained = VALUES(marks_obtained)",
                (student_ids[roll_key], subject_id, assessment, obtained),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

    return {"rows": len(rows), "students_created": len(new_students),
            "added": added, "updated": updated, "unchanged": unchanged}


@web_bp.route("/upload", methods=["GET", "POST"])
def upload():
    result = None
    if request.method == "POST":
        file = request.files.get("file")
        if not file or not file.filename:
            flash("Please choose a CSV file first.", "error")
        elif not file.filename.lower().endswith(".csv"):
            flash("Only .csv files can be uploaded.", "error")
        else:
            try:
                result = process_csv(file)
            except IntegrityError:
                flash("Could not save the file because of a duplicate value. Nothing was saved.", "error")
    return render_template("upload.html", result=result, columns=CSV_COLUMNS)


# ---------- Reports ----------

@web_bp.route("/reports")
def reports():
    df = load_marks()
    if df.empty:
        return render_template("reports.html", empty=True)
    summary = student_summary(df)
    subjects = subject_stats(df)
    charts = build_charts(df)
    return render_template("reports.html", empty=False, summary=records(summary),
                           subjects=records(subjects), charts=charts, stamp=int(time.time()),
                           chart_data=chart_payload(summary, subjects))


# ---------- Trends (did a student's performance fall?) ----------

@web_bp.route("/trends")
def trends():
    try:
        drop = max(1.0, min(100.0, float(request.args.get("drop", 10))))
    except ValueError:
        drop = 10.0
    df = load_marks()
    rows = trend_report(df, drop) if not df.empty else []
    return render_template("trends.html", rows=rows, drop=drop,
                           dropped=[r for r in rows if r["status"] == "Dropped"])


# ---------- Find a student and see everything about them ----------

@web_bp.route("/find")
def find_student():
    chosen = to_number(request.args.get("student_id"))
    if chosen:
        return redirect(url_for("web.student_profile_page", student_id=int(chosen)))
    q = request.args.get("q", "").strip()
    matches = []
    if q:
        like = f"%{q}%"
        matches = run_query(
            "SELECT student_id, roll_no, name, section FROM students "
            "WHERE roll_no LIKE %s OR name LIKE %s ORDER BY roll_no LIMIT 20", (like, like), fetch=True)
        if len(matches) == 1:
            return redirect(url_for("web.student_profile_page", student_id=matches[0]["student_id"]))
    everyone = run_query("SELECT student_id, roll_no, name FROM students ORDER BY roll_no", fetch=True)
    return render_template("find_student.html", q=q, matches=matches, students=everyone)


@web_bp.route("/students/<int:student_id>/profile")
def student_profile_page(student_id):
    student = run_query("SELECT student_id, roll_no, name, section FROM students WHERE student_id = %s",
                        (student_id,), fetch=True, one=True)
    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("web.find_student"))
    df = load_marks()
    profile = None if df.empty else student_profile(df, student_id)
    return render_template("student_profile.html", student=student, profile=profile)
