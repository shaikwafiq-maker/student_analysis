# Student Performance Analysis System

A Flask web application with a teacher login. Teachers manage students, subjects and marks through web forms (or by uploading a CSV file). The data is stored in MySQL and analyzed with Pandas, NumPy and Matplotlib to show grades, ranks, toppers, subject statistics and charts.

## Features

- **Teacher login** with hashed passwords and sessions
- **Web pages with forms** to add, edit and delete students, subjects and marks
- **CSV upload** to add marks for many students at once (the whole file is checked first)
- Marks validation (must be between 0 and the subject's maximum marks)
- Total, percentage, grade, pass/fail result and rank for every student
- Subject-wise average, highest, lowest, median, standard deviation and pass percentage
- **Find student:** search by name or roll number to see all of one student's marks in every subject and semester in one table, with a graph of every subject, rank, grade and progress across semesters (printable)
- Topper list and a list of students who need academic support
- **Trends:** compares each student's latest semester with the one before (name assessments Sem 1, Sem 2, Sem 3) and flags big drops, with the subjects that fell
- Interactive charts (hover for exact values) on the Dashboard and Reports pages, plus saved Matplotlib chart images
- Dark mode and light mode (remembered in the browser, follows the computer's setting at first)
- A vertical sidebar menu that highlights the current page (it moves to the top on small screens)
- Friendly error pages and a printable layout
- A JSON API for the same data (available after logging in)

## Technologies

Python, Flask, MySQL, Pandas, NumPy, Matplotlib, HTML and CSS

## Project structure

```
student_analysis/
├── app.py              # Flask app: login, security and the JSON API
├── web.py              # Web pages: forms, CSV upload, reports
├── analysis.py         # Pandas/NumPy analysis and Matplotlib charts
├── db.py               # MySQL connection and query helper
├── create_teacher.py   # Creates a teacher login account
├── schema.sql          # MySQL tables and sample data
├── requirements.txt    # Python libraries
├── .env                # Private settings (never share this file)
├── templates/          # HTML pages
├── static/             # style.css and sample_marks.csv
└── reports/            # Generated chart images
```

## Setup

1. **Install** Python 3 and MySQL Server (with MySQL Workbench).
2. **Create the database:** open `schema.sql` in MySQL Workbench and run it.
3. **Create a virtual environment and install the libraries:**
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. **Create a `.env` file** in the project folder:
   ```
   DB_HOST=127.0.0.1
   DB_USER=root
   DB_PASSWORD=your_mysql_password
   DB_NAME=student_analysis
   SECRET_KEY=a-long-random-text-that-only-you-know
   ```
5. **Create a teacher account:**
   ```
   python create_teacher.py
   ```
   Enter a username and a password (at least 8 characters).
6. **Run the app:**
   ```
   python app.py
   ```
7. Open http://127.0.0.1:5000 and log in.

## Using the web pages

| Page | What you can do |
|---|---|
| Dashboard | Counts, class pass rate and average, top students, students who need support |
| Students | Add, edit and delete students |
| Subjects | Add and delete subjects (with maximum and pass marks) |
| Marks | Add, edit and delete marks using drop-down lists |
| Trends | Students whose marks fell (or rose) between the last two semesters |
| Upload CSV | Add or update marks for many students from one file |
| Reports | Results table, subject statistics and charts |

### CSV format

The first line must contain these column names:

```
roll_no,name,section,subject_name,assessment,marks_obtained
```

- The subject must already exist.
- Students that do not exist yet are created from `roll_no`, `name` and `section`.
- Marks that already exist for the same student, subject and assessment are updated.
- If any row has a problem, nothing is saved and every problem is listed.
- A sample file is available on the Upload CSV page.

## Grading scale

| Percentage | Grade |
|---|---|
| 90 and above | A+ |
| 80 to 89 | A |
| 70 to 79 | B |
| 60 to 69 | C |
| 50 to 59 | D |
| Below 50 | E |
| Failed any subject | F |

A student passes only if they reach the pass marks in every subject.

## JSON API (after logging in)

These addresses work in the browser while you are logged in. Without a login they return `401`.

| Method | URL | Purpose |
|---|---|---|
| GET, POST | `/students` | List or add students |
| GET, PUT, DELETE | `/students/<id>` | View, update or delete a student |
| GET, POST | `/subjects` | List or add subjects |
| GET, POST | `/marks` | List or add marks |
| GET, PUT, DELETE | `/marks/<id>` | View, update or delete marks |
| GET | `/analysis/overview` | Class pass percentage, average, highest and lowest |
| GET | `/analysis/summary` | Total, percentage, grade, result and rank per student |
| GET | `/analysis/subjects` | Statistics and pass percentage per subject |
| GET | `/analysis/toppers?limit=3` | Top students who passed every subject |
| GET | `/analysis/needs-support` | Students who failed a subject or scored below 50% |
| GET | `/analysis/trends?drop=10` | Change between each student's last two assessments |
| GET | `/analysis/charts` | Creates the chart images and returns their links |

All analysis URLs accept an optional `?assessment=Final` to analyze one assessment only.

## Security notes

- Teacher passwords are stored as salted hashes, never as plain text.
- Every page and API address needs a login, except the login page.
- Every form carries a secret token (CSRF protection).
- All SQL uses parameterized queries to prevent SQL injection.
- Page output is escaped to prevent cross-site scripting.
- Database credentials and the secret key are kept in `.env`, not in the code.
- CSV uploads are limited to 1 MB and 5000 rows, and the whole file is validated before saving.
- The app runs in debug mode for development. Do not run it that way on a public server.

## Future improvements

- Teacher accounts with different roles (admin and teacher)
- Download reports as PDF or Excel
- Student progress over time across several assessments
- Sending result emails to students
