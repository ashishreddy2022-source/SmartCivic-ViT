import os
os.environ["TF_USE_LEGACY_KERAS"] = "1"  # <--- THIS IS THE MAGIC FIX

from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os
import shutil
import cv2  
from werkzeug.utils import secure_filename
from ultralytics import YOLO
from flask_mail import Mail, Message
import random
import math
import numpy as np
import tensorflow as tf
import tensorflow_hub as hub

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

# --- LOAD AI MODELS (TWO-STAGE PIPELINE) ---
print("\n--- INITIALIZING AI SYSTEMS ---")
try:
    # 1. Loading the YOLO Finder
    master_model = YOLO('fixify_master.pt')
    print("✅ YOLOv8 Object Detection Model Loaded Successfully!")
    
    # 2. Loading the ViT Verifier
    IMG_SIZE = 224
    CLASS_LABELS = ['Damaged Pole', 'Dead Animal', 'Fallen Tree', 'Garbage', 'Pothole', 'Spam'] 
    
    vit_url = "https://tfhub.dev/sayakpaul/vit_b16_fe/1"
    vit_model = tf.keras.Sequential([
        hub.KerasLayer(vit_url, trainable=False, input_shape=(IMG_SIZE, IMG_SIZE, 3)),
        tf.keras.layers.BatchNormalization(),
        tf.keras.layers.Dense(512, activation='gelu'),
        tf.keras.layers.Dropout(0.5),
        tf.keras.layers.Dense(len(CLASS_LABELS), activation='softmax')
    ])
    vit_model.load_weights('vit_native_checkpoint') 
    print("✅ ViT-B16 Vision Transformer Loaded Successfully!")
    
except Exception as e:
    print(f"❌ ERROR LOADING MODELS: {e}")
    master_model = None
    vit_model = None
print("-------------------------------\n")


# --- HELPER: CALCULATE PRIORITY BASED ON SIZE ---
def get_severity(box, orig_shape):
    x1, y1, x2, y2 = box.xyxy[0].tolist()
    box_area = (x2 - x1) * (y2 - y1)
    img_height, img_width = orig_shape
    coverage_percentage = (box_area / (img_width * img_height)) * 100
    
    if coverage_percentage > 30: return "High"
    elif coverage_percentage > 10: return "Medium"
    else: return "Low"


# --- MAIN AI FUNCTION (TWO-STAGE PIPELINE) ---
def analyze_image_with_ai(image_path):
    detected_category = "Nothing Detected/Spam"
    priority = "None"
    is_spam = 1

    if not master_model or not vit_model:
        return detected_category, priority, is_spam

    # STAGE 1: Run YOLO to find bounding boxes
    results = master_model.predict(source=image_path, save=False, conf=0.50)

    # If YOLO found at least one issue
    if len(results[0].boxes) > 0:
        # Read the original image with OpenCV
        img = cv2.imread(image_path)
        
        # Grab the most confident detection box from YOLO
        box = results[0].boxes[0]
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        
        # Prevent boundary errors
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
        
        # STAGE 2: Crop the issue for the Vision Transformer
        issue_crop = img[y1:y2, x1:x2]
        
        if issue_crop.size > 0:
            # Prepare crop for ViT (Scale and Resize)
            crop_resized = cv2.resize(issue_crop, (224, 224))
            crop_rgb = cv2.cvtColor(crop_resized, cv2.COLOR_BGR2RGB)
            crop_scaled = (crop_rgb / 127.5) - 1.0
            crop_expanded = np.expand_dims(crop_scaled, axis=0)
            
            # Get ViT's highly accurate classification
            vit_prediction = vit_model.predict(crop_expanded)
            predicted_index = int(np.argmax(vit_prediction))
            
            # Get the label from your CLASS_LABELS array
            detected_category = CLASS_LABELS[predicted_index]
            confidence = np.max(vit_prediction)
            
            # --- THE BULLETPROOF SPAM CHECK ---
            # .lower() forces the string to lowercase so it always catches spam
            if 'spam' in detected_category.lower() or 'nothing' in detected_category.lower():
                is_spam = 1
                priority = "None"
                detected_category = "Spam / Invalid" # Cleans up the database entry
            else:
                is_spam = 0
                priority = get_severity(box, results[0].orig_shape)
            # ----------------------------------
            
            # DRAW CUSTOM RED BOX WITH ViT LABEL
            label_text = f"{detected_category} {confidence:.2f}"
            
            # Draw the Bounding Box
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 3)
            
            # Draw Label Background (Dynamically size width based on text length)
            (text_width, text_height), _ = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
            cv2.rectangle(img, (x1, y1 - 30), (x1 + text_width + 10, y1), (0, 0, 255), -1)
            
            # Put Label Text
            cv2.putText(img, label_text, (x1 + 5, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            
            # Save the final modified image over the original
            cv2.imwrite(image_path, img)

    return detected_category, priority, is_spam


# --- ROUTES ---

@app.route("/")
def home(): return render_template("index.html")

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
            flash("Email address already registered.", "danger")
            return redirect(url_for('register'))
        finally:
            conn.close()
        flash("Registration successful! Please log in.", "success")
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
            flash("Invalid email or password. Please try again.", "danger")
            return redirect(url_for('login'))
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    user_id = session.get('user_id')
    conn = sqlite3.connect('fixify.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM issues WHERE user_id = ? ORDER BY id DESC", (user_id,))
    issues = cursor.fetchall()
    conn.close()
    return render_template("dashboard.html", name=session.get('user_name'), issues=issues)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('home'))

# --- REPORT ISSUE ROUTE ---
@app.route('/report_issue', methods=['GET', 'POST'])
def report_issue():
    if 'user_id' not in session: return redirect(url_for('login'))

    if request.method == 'POST':
        description = request.form.get('description')
        location = request.form.get('location')
        photo = request.files.get('photo')
        user_id = session['user_id']

        db_filename = None 
        detected_category = "No Image"
        priority = "Low"
        is_spam = 1
        final_title = "Issue Report"
        final_status = "Pending"

        if photo and photo.filename != '':
            filename = secure_filename(photo.filename)
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            photo.save(temp_path)

            # AI Analysis (YOLO + ViT Two-Stage Pipeline)
            detected_category, priority, is_spam = analyze_image_with_ai(temp_path)
            
            # Dynamically sort into folders based on the detected category
            if is_spam:
                subfolder = "spam"
                final_title = "Spam / Nothing Detected"
                final_status = "Blocked"
            else:
                # Formats "Fallen Tree" into "fallen_tree" for clean folder names
                subfolder = detected_category.lower().replace(" ", "_")
                final_title = f"{priority} Priority {detected_category}"
                final_status = "Pending"

            target_dir = os.path.join(app.config['UPLOAD_FOLDER'], subfolder)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)

            new_path = os.path.join(target_dir, filename)
            
            if os.path.exists(new_path):
                import time
                base, ext = os.path.splitext(filename)
                filename = f"{base}_{int(time.time())}{ext}"
                new_path = os.path.join(target_dir, filename)

            shutil.move(temp_path, new_path)
            db_filename = f"{subfolder}/{filename}"

        else:
            final_title = "Invalid Report"
            final_status = "Blocked"

        conn = sqlite3.connect('fixify.db')
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO issues 
               (title, description, location, photo_filename, status, user_id, detected_category, priority, is_spam) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (final_title, description, location, db_filename, final_status, user_id, detected_category, priority, is_spam)
        )
        conn.commit()
        conn.close()

        if is_spam:
            flash(f'Report rejected. AI could not detect a valid civic issue.', 'danger')
        else:
            flash(f'Issue reported successfully! Detected: {detected_category} (Severity: {priority})', 'success')
            
        return redirect(url_for('dashboard'))

    return render_template('report_issue.html')

# --- ADMIN ROUTES ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == 'admin123':
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Incorrect password!', 'danger')
    return '''<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <div class="container mt-5" style="max-width: 400px;"><div class="card shadow p-4"><h3 class="text-center mb-3">Admin Login</h3>
        <form method="POST"><div class="mb-3"><label class="form-label">Password</label><input type="password" name="password" class="form-control" required>
        </div><button type="submit" class="btn btn-danger w-100">Login</button></form></div></div>'''

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    conn = sqlite3.connect('fixify.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM issues ORDER BY id DESC")
    issues = cursor.fetchall()
    conn.close()
    return render_template('admin.html', issues=issues)

@app.route('/admin/update_status/<int:issue_id>', methods=['POST'])
def update_status(issue_id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin_login'))
    conn = sqlite3.connect('fixify.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE issues SET status = ? WHERE id = ?", (request.form.get('status'), issue_id))
    conn.commit()
    conn.close()
    flash(f'Status for issue #{issue_id} has been updated!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        step = request.form.get("step")
        
        # STEP 1: SEND OTP
        if step == "send_otp":
            email = request.form.get("email")
            
            conn = sqlite3.connect('fixify.db')
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            user = cursor.fetchone()
            conn.close()

            if user:
                otp = random.randint(100000, 999999)
                session['reset_otp'] = otp
                session['reset_email'] = email
                
                try:
                    msg = Message('Fixify Password Reset OTP', sender='noreply@fixify.com', recipients=[email])
                    msg.body = f"Your OTP for Password Reset is: {otp}"
                    mail.send(msg)
                    flash("OTP sent to your email!", "success")
                    return render_template("forgot_password.html", step=2)
                except Exception as e:
                    flash(f"Error sending email: {e}", "danger")
                    return redirect(url_for('forgot_password'))
            else:
                flash("Email not registered.", "danger")
                return redirect(url_for('forgot_password'))

        # STEP 2: VERIFY OTP
        elif step == "verify_otp":
            user_otp = request.form.get("otp")
            stored_otp = session.get('reset_otp')
            
            if stored_otp and str(stored_otp) == user_otp:
                flash("OTP Verified!", "success")
                return render_template("forgot_password.html", step=3)
            else:
                flash("Invalid OTP. Please try again.", "danger")
                return render_template("forgot_password.html", step=2)

        # STEP 3: RESET PASSWORD
        elif step == "reset_password":
            new_pass = request.form.get("new_password")
            email = session.get('reset_email')
            
            if email:
                hashed_pw = generate_password_hash(new_pass)
                conn = sqlite3.connect('fixify.db')
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET password = ? WHERE email = ?", (hashed_pw, email))
                conn.commit()
                conn.close()
                
                session.pop('reset_otp', None)
                session.pop('reset_email', None)
                
                flash("Password reset successfully! Login now.", "success")
                return redirect(url_for('login'))
            else:
                flash("Session expired. Start over.", "danger")
                return redirect(url_for('forgot_password'))

    return render_template("forgot_password.html", step=1)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
