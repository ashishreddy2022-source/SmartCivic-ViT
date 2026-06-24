import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import shutil
import cv2
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
import random
import numpy as np

app = Flask(__name__, static_folder='assets')
app.secret_key = 'your_super_secret_key'

# --- EMAIL CONFIGURATION ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USERNAME'] = 'npritam312@gmail.com'  
app.config['MAIL_PASSWORD'] = 'wnna myws syee doca'   
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True

mail = Mail(app)

# --- CONFIGURATION ---
UPLOAD_FOLDER = 'assets/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- SIMPLIFIED AI SYSTEM (FOR DEPLOYMENT) ---
print("\n--- INITIALIZING AI SYSTEMS ---")
print("⚠️ Running in DEMO MODE (No heavy ML models loaded)")
print("-------------------------------\n")

# --- DUMMY AI FUNCTION ---
def analyze_image_with_ai(image_path):
    detected_category = "Pothole"
    priority = "Medium"
    is_spam = 0
    return detected_category, priority, is_spam

# --- ROUTES ---

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        hashed_password = generate_password_hash(password)

        try:
            conn = sqlite3.connect('fixify.db')
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, hashed_password))
            conn.commit()
        except sqlite3.IntegrityError:
            flash("Email already registered.", "danger")
            return redirect(url_for('register'))
        finally:
            conn.close()

        flash("Registration successful!", "success")
        return redirect(url_for('login'))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = sqlite3.connect('fixify.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid login", "danger")

    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('fixify.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM issues ORDER BY id DESC")
    issues = cursor.fetchall()
    conn.close()

    return render_template("dashboard.html", issues=issues)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

# --- REPORT ISSUE ---
@app.route('/report_issue', methods=['GET', 'POST'])
def report_issue():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        description = request.form.get('description')
        location = request.form.get('location')
        photo = request.files.get('photo')
        user_id = session['user_id']

        db_filename = None

        if photo and photo.filename != '':
            filename = secure_filename(photo.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            photo.save(filepath)

            detected_category, priority, is_spam = analyze_image_with_ai(filepath)

            conn = sqlite3.connect('fixify.db')
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO issues (title, description, location, photo_filename, user_id) VALUES (?, ?, ?, ?, ?)",
                (detected_category, description, location, filename, user_id)
            )
            conn.commit()
            conn.close()

            flash(f"Detected: {detected_category} (Priority: {priority})", "success")

        return redirect(url_for('dashboard'))

    return render_template('report_issue.html')

# --- ADMIN ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == 'admin123':
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Wrong password", "danger")

    return render_template("admin_login.html")

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin'))

    conn = sqlite3.connect('fixify.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM issues")
    issues = cursor.fetchall()
    conn.close()

    return render_template("admin.html", issues=issues)

# --- RUN ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
