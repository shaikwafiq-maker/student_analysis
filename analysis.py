import base64
import json
import os
import re
from io import BytesIO

import matplotlib

matplotlib.use("Agg")  # draw charts into files, without opening a window
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
from flask import Blueprint, jsonify, request, send_from_directory

from db import get_connection

analysis_bp = Blueprint("analysis", __name__, url_prefix="/analysis")

REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
SUPPORT_BELOW_PERCENT = 50  # students under this percentage need academic support


# ---------- Loading data ----------

def load_marks(assessment=None):
    """Read all marks from MySQL into a Pandas DataFrame (one row per mark)."""
    sql = """
        SELECT m.mark_id, s.student_id, s.roll_no, s.name, s.section,
               sub.subject_name, sub.max_marks, sub.pass_marks,
               m.assessment, m.marks_obtained
        FROM marks m
        JOIN students s ON s.student_id = m.student_id
        JOIN subjects sub ON sub.subject_id = m.subject_id
    """
    params = ()
    if assessment:
        sql += " WHERE m.assessment = %s"
        params = (assessment,)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    for column in ("marks_obtained", "max_marks", "pass_marks"):
        df[column] = df[column].astype(float)
    df["passed"] = df["marks_obtained"] >= df["pass_marks"]
    df["failed"] = ~df["passed"]
    return df


def records(df):
    """DataFrame -> list of plain dictionaries that Flask can turn into JSON."""
    return json.loads(df.to_json(orient="records"))


# ---------- Calculations ----------

def student_summary(df):
    """Total, percentage, result, grade and rank for every student."""
    summary = df.groupby(["student_id", "roll_no", "name", "section"], as_index=False).agg(
        subjects=("subject_name", "count"),
        total=("marks_obtained", "sum"),
        max_total=("max_marks", "sum"),
        failed_subjects=("failed", "sum"),
    )
    summary["percentage"] = (summary["total"] / summary["max_total"] * 100).round(2)
    summary["result"] = np.where(summary["failed_subjects"] == 0, "Pass", "Fail")

    percent = summary["percentage"]
    grade = np.select(
        [percent >= 90, percent >= 80, percent >= 70, percent >= 60, percent >= 50],
        ["A+", "A", "B", "C", "D"],
        default="E",
    )
    summary["grade"] = np.where(summary["result"] == "Fail", "F", grade)
    summary["rank"] = percent.rank(method="min", ascending=False).astype(int)
    return summary.sort_values(["rank", "roll_no"]).reset_index(drop=True)


def subject_stats(df):
    """Average, highest, lowest, median, standard deviation and pass rate per subject."""
    grouped = df.groupby("subject_name")
    stats = grouped.agg(
        students=("marks_obtained", "count"),
        average=("marks_obtained", "mean"),
        highest=("marks_obtained", "max"),
        lowest=("marks_obtained", "min"),
        passed_count=("passed", "sum"),
    )
    stats["median"] = grouped["marks_obtained"].apply(lambda s: float(np.median(s.to_numpy())))
    stats["std_dev"] = grouped["marks_obtained"].apply(lambda s: float(np.std(s.to_numpy())))
    stats["pass_percentage"] = stats["passed_count"] / stats["students"] * 100
    return stats.round(2).reset_index()



def class_overview(summary):
    """Class-level numbers (uses NumPy for the statistics)."""
    percentages = summary["percentage"].to_numpy()
    total = int(len(summary))
    passed = int((summary["result"] == "Pass").sum())
    return {
        "students": total,
        "passed": passed,
        "failed": total - passed,
        "pass_percentage": round(passed / total * 100, 2),
        "class_average_percentage": round(float(np.mean(percentages)), 2),
        "highest_percentage": round(float(np.max(percentages)), 2),
        "lowest_percentage": round(float(np.min(percentages)), 2),
        "std_dev_percentage": round(float(np.std(percentages)), 2),
    }


def top_students(summary, limit=3):
    passed = summary[summary["result"] == "Pass"].head(limit)
    return passed[["rank", "roll_no", "name", "section", "total", "percentage", "grade"]]


def support_list(df, summary):
    failed_in = (
        df[df["failed"]].groupby("student_id")["subject_name"]
        .apply(lambda s: ", ".join(s))
        .rename("failed_in")
    )
    needs = summary[(summary["result"] == "Fail") | (summary["percentage"] < SUPPORT_BELOW_PERCENT)]
    needs = needs.merge(failed_in, on="student_id", how="left")
    needs["failed_in"] = needs["failed_in"].fillna("-")
    return needs[["roll_no", "name", "section", "percentage", "result", "failed_in"]]


def assessment_order(df):
    """Order assessments by the number in their name (Sem 1, Sem 2...), else by the order they were entered."""
    names = list(dict.fromkeys(df.sort_values("mark_id")["assessment"]))
    if all(re.search(r"\d+", n) for n in names):
        names.sort(key=lambda n: int(re.search(r"\d+", n).group()))
    return names


def trend_report(df, drop_points=10.0):
    """Compare each student's latest assessment with the one before it."""
    order = assessment_order(df)
    rows = []
    for (roll_no, name, section), g in df.groupby(["roll_no", "name", "section"]):
        pct = (g.groupby("assessment")["marks_obtained"].sum() / g.groupby("assessment")["max_marks"].sum() * 100).round(2)
        seq = [x for x in order if x in pct.index]
        if len(seq) < 2:
            continue
        before, latest = seq[-2], seq[-1]
        change = round(float(pct[latest] - pct[before]), 2)
        status = "Dropped" if change <= -drop_points else "Improved" if change >= drop_points else "Stable"
        per_subject = g.assign(p=g["marks_obtained"] / g["max_marks"] * 100).pivot_table(
            index="subject_name", columns="assessment", values="p")
        diff = (per_subject[latest] - per_subject[before]).dropna().sort_values()
        fell = ", ".join(f"{s} {d:+.0f}" for s, d in diff.items() if d <= -drop_points)
        rows.append({
            "roll_no": roll_no, "name": name, "section": section,
            "from_assessment": before, "to_assessment": latest,
            "previous_percentage": float(pct[before]), "latest_percentage": float(pct[latest]),
            "change": change, "status": status, "fell_in": fell or "-",
            "history": " > ".join(f"{x}: {pct[x]:g}%" for x in seq),
        })
    rows.sort(key=lambda r: (r["status"] != "Dropped", r["change"]))
    return rows


# ---------- One student's profile (marks table + charts) ----------

def figure_uri(fig):
    """Turn a Matplotlib figure into an image that can be placed directly in a web page."""
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def subject_chart(matrix, order, class_avg):
    """Grouped bars: every subject on the x axis, one bar per assessment, plus the class average."""
    fig = Figure(figsize=(max(7.5, 1.7 * len(matrix) + 3), 4.6))
    ax = fig.subplots()
    palette = ["#0e7c86", "#f4a261", "#2a9d8f", "#e76f51", "#264653", "#8ab17d"]
    x = np.arange(len(matrix))
    n = len(order) + 1
    w = 0.8 / n
    for i, name in enumerate(order):
        vals = [np.nan if row["cells"][i]["marks"] is None else row["cells"][i]["marks"] for row in matrix]
        bars = ax.bar(x + (i - n / 2 + 0.5) * w, vals, w, color=palette[i % len(palette)], label=name)
        for bar, row in zip(bars, matrix):
            cell = row["cells"][i]
            if cell["marks"] is not None and not cell["passed"]:
                bar.set_hatch("//")
                bar.set_edgecolor("#c0392b")
        ax.bar_label(bars, labels=["" if np.isnan(v) else f"{v:.0f}" for v in vals], fontsize=8)
    avg_bars = ax.bar(x + (n - 1 - n / 2 + 0.5) * w, [class_avg[r["subject"]] for r in matrix], w, color="#c9d3da")
    ax.bar_label(avg_bars, fmt="%.0f", fontsize=8, color="#4a5866")
    ax.set_xticks(x)
    ax.set_xticklabels([r["subject"] for r in matrix])
    ax.set_ylim(0, max(r["max_marks"] for r in matrix) * 1.12)
    ax.set_ylabel("Marks")
    ax.set_title("Marks in every subject (hatched red edge = failed)")
    handles = [Patch(color=palette[i % len(palette)], label=name) for i, name in enumerate(order)]
    handles.append(Patch(color="#c9d3da", label="Class average"))
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=min(n, 4), fontsize=8, frameon=False)
    fig.tight_layout()
    return figure_uri(fig)


def trend_chart(names, student, class_avg):
    fig = Figure(figsize=(7.5, 3.6))
    ax = fig.subplots()
    ax.plot(names, student, marker="o", color="#0e7c86", linewidth=2.2, label="Student")
    ax.plot(names, class_avg, marker="s", color="#9db4c0", linestyle="--", label="Class average")
    for n, v in zip(names, student):
        ax.annotate(f"{v:.0f}%", (n, v), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=9)
    ax.set_ylim(0, 105)
    ax.set_ylabel("Percentage")
    ax.set_title("Overall percentage in each assessment")
    ax.legend(fontsize=8)
    fig.tight_layout()
    return figure_uri(fig)


def student_profile(df, student_id):
    """All of one student's marks: a subject x assessment table, totals, overall result and charts."""
    mine = df[df["student_id"] == student_id]
    if mine.empty:
        return None
    order = [x for x in assessment_order(df) if x in set(mine["assessment"])]
    lookup = {(r.subject_name, r.assessment): r for r in mine.itertuples()}

    matrix = []
    for subject in sorted(mine["subject_name"].unique()):
        cells, seen = [], []
        for name in order:
            r = lookup.get((subject, name))
            cells.append({"assessment": name, "marks": None if r is None else float(r.marks_obtained),
                          "passed": None if r is None else bool(r.passed)})
            if r is not None:
                seen.append(float(r.marks_obtained))
        info = mine[mine["subject_name"] == subject].iloc[0]
        matrix.append({"subject": subject, "max_marks": float(info["max_marks"]), "pass_marks": float(info["pass_marks"]),
                       "cells": cells, "average": round(sum(seen) / len(seen), 1)})

    totals = []
    class_pct = df.groupby(["assessment", "student_id"]).agg(t=("marks_obtained", "sum"), m=("max_marks", "sum"))
    class_pct = (class_pct["t"] / class_pct["m"] * 100).groupby(level="assessment").mean()
    for name in order:
        g = mine[mine["assessment"] == name]
        total, max_total = float(g["marks_obtained"].sum()), float(g["max_marks"].sum())
        totals.append({"assessment": name, "total": total, "max_total": max_total,
                       "percentage": round(total / max_total * 100, 1), "class_avg": round(float(class_pct[name]), 1),
                       "result": "Pass" if g["passed"].all() else "Fail"})

    summary = student_summary(df)
    me = summary[summary["student_id"] == student_id].iloc[0]
    class_avg = df.groupby("subject_name")["marks_obtained"].mean()

    return {
        "assessments": order, "matrix": matrix, "totals": totals,
        "percentage": float(me["percentage"]), "grade": me["grade"], "result": me["result"],
        "rank": int(me["rank"]), "class_size": int(len(summary)),
        "total": float(me["total"]), "max_total": float(me["max_total"]),
        "subject_chart": subject_chart(matrix, order, class_avg),
        "trend_chart": trend_chart(order, [t["percentage"] for t in totals], [t["class_avg"] for t in totals])
        if len(order) > 1 else None,
    }


def chart_payload(summary, subjects):
    """Plain numbers and labels that the browser charts need."""
    grades = ["A+", "A", "B", "C", "D", "E", "F"]
    counts = summary["grade"].value_counts()
    ranked = summary.head(30)
    return {
        "subjects": {"labels": [str(s) for s in subjects["subject_name"]],
                     "average": [float(v) for v in subjects["average"]],
                     "pass": [float(v) for v in subjects["pass_percentage"]]},
        "grades": {"labels": grades, "counts": [int(counts.get(g, 0)) for g in grades]},
        "students": {"labels": [f"{r.name} ({r.roll_no})" for r in ranked.itertuples()],
                     "percentage": [float(v) for v in ranked["percentage"]],
                     "failed": [bool(v == "Fail") for v in ranked["result"]]},
    }


def no_data():
    return jsonify(error="No marks found. Add some marks first."), 404


# ---------- Routes (JSON reports) ----------
# Every route accepts an optional ?assessment=Final to analyze one assessment only.

@analysis_bp.route("/overview")
def overview():
    df = load_marks(request.args.get("assessment"))
    if df.empty:
        return no_data()
    return jsonify(class_overview(student_summary(df)))


@analysis_bp.route("/summary")
def summary_report():
    df = load_marks(request.args.get("assessment"))
    if df.empty:
        return no_data()
    return jsonify(records(student_summary(df)))


@analysis_bp.route("/subjects")
def subjects_report():
    df = load_marks(request.args.get("assessment"))
    if df.empty:
        return no_data()
    return jsonify(records(subject_stats(df)))


@analysis_bp.route("/toppers")
def toppers_report():
    df = load_marks(request.args.get("assessment"))
    if df.empty:
        return no_data()
    try:
        limit = max(1, int(request.args.get("limit", 3)))
    except ValueError:
        return jsonify(error="limit must be a whole number"), 400
    return jsonify(records(top_students(student_summary(df), limit)))


@analysis_bp.route("/trends")
def trends_report():
    df = load_marks()
    if df.empty:
        return no_data()
    try:
        drop = float(request.args.get("drop", 10))
    except ValueError:
        return jsonify(error="drop must be a number"), 400
    return jsonify(trend_report(df, drop))


@analysis_bp.route("/needs-support")
def needs_support_report():
    df = load_marks(request.args.get("assessment"))
    if df.empty:
        return no_data()
    return jsonify(records(support_list(df, student_summary(df))))


# ---------- Matplotlib charts ----------

def save_bar_chart(labels, values, title, xlabel, ylabel, filename, fmt="%.1f", ylim=None):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(labels, values, color="#2f6fb3")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if ylim:
        ax.set_ylim(*ylim)
    ax.bar_label(bars, fmt=fmt)
    fig.tight_layout()
    os.makedirs(REPORTS_DIR, exist_ok=True)
    fig.savefig(os.path.join(REPORTS_DIR, filename), dpi=150)
    plt.close(fig)


def build_charts(df):
    """Draw the three charts into the reports folder. Returns the file names."""
    subjects = subject_stats(df)
    summary = student_summary(df)

    save_bar_chart(
        subjects["subject_name"], subjects["average"],
        "Average Marks by Subject", "Subject", "Average marks",
        "subject_average.png", ylim=(0, 100),
    )
    save_bar_chart(
        subjects["subject_name"], subjects["pass_percentage"],
        "Pass Percentage by Subject", "Subject", "Students passed (%)",
        "pass_percentage.png", ylim=(0, 100),
    )

    grade_order = ["A+", "A", "B", "C", "D", "E", "F"]
    counts = summary["grade"].value_counts().reindex(grade_order, fill_value=0)
    save_bar_chart(
        counts.index, counts.values,
        "Grade Distribution", "Grade", "Number of students",
        "grade_distribution.png", fmt="%d",
    )
    return ["subject_average.png", "pass_percentage.png", "grade_distribution.png"]


@analysis_bp.route("/charts")
def make_charts():
    df = load_marks(request.args.get("assessment"))
    if df.empty:
        return no_data()

    names = build_charts(df)
    base = request.host_url.rstrip("/") + "/analysis/charts/"
    return jsonify(
        message="Charts created in the 'reports' folder",
        charts=[base + name for name in names],
    )


@analysis_bp.route("/charts/<path:filename>")
def show_chart(filename):
    return send_from_directory(REPORTS_DIR, filename)
