-- Student Performance Analysis System: database setup
-- Run this once in MySQL Workbench.

CREATE DATABASE IF NOT EXISTS student_analysis;
USE student_analysis;

CREATE TABLE IF NOT EXISTS students (
    student_id INT AUTO_INCREMENT PRIMARY KEY,
    roll_no VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    section VARCHAR(10) NOT NULL
);

CREATE TABLE IF NOT EXISTS subjects (
    subject_id INT AUTO_INCREMENT PRIMARY KEY,
    subject_name VARCHAR(100) NOT NULL UNIQUE,
    max_marks INT NOT NULL DEFAULT 100,
    pass_marks INT NOT NULL DEFAULT 35
);

CREATE TABLE IF NOT EXISTS marks (
    mark_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    subject_id INT NOT NULL,
    assessment VARCHAR(50) NOT NULL,
    marks_obtained DECIMAL(5,2) NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(subject_id) ON DELETE CASCADE,
    UNIQUE (student_id, subject_id, assessment)
);

CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Sample data for testing (INSERT IGNORE skips rows that already exist)
INSERT IGNORE INTO students (roll_no, name, section) VALUES
('R001', 'Asha', 'A'),
('R002', 'Ravi', 'A'),
('R003', 'Meena', 'B');

INSERT IGNORE INTO subjects (subject_name, max_marks, pass_marks) VALUES
('Maths', 100, 35),
('Science', 100, 35),
('English', 100, 35);

INSERT IGNORE INTO marks (student_id, subject_id, assessment, marks_obtained) VALUES
(1, 1, 'Final', 88), (1, 2, 'Final', 76), (1, 3, 'Final', 91),
(2, 1, 'Final', 45), (2, 2, 'Final', 32), (2, 3, 'Final', 58),
(3, 1, 'Final', 67), (3, 2, 'Final', 72), (3, 3, 'Final', 80);

SELECT * FROM student_analysis.marks;
