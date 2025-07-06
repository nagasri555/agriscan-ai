from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, flash
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from plant_api import identify_crop_disease
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PIL import Image
import sqlite3
from datetime import datetime
import base64
from dotenv import load_dotenv
load_dotenv()

PLANT_ID_API_KEY = os.getenv("PLANT_ID_API_KEY")

app = Flask(__name__, template_folder='frontend')
CORS(app)

app.secret_key = 'your_secret_key_here'  # Replace with a strong secret key
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
STATIC_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Home page redirects to login if not authenticated
@app.route('/')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/upload')
def upload_page():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('upload.html')

@app.route('/about')
def about_page():
    return render_template('about.html')

@app.route("/contact", methods=["GET", "POST"])
def contact_page():
    if request.method == "POST":
        name = request.form['name']
        email = request.form['email']
        message = request.form['message']

        # Send an email to the user
        msg = Message(
            subject="Thanks for contacting AgriScan AI!",
            recipients=[email],  # Send to the user
            body=f"""Hi {name},

Thanks for reaching out! We received your message:

"{message}"

We’ll get back to you shortly.

Best regards,
AgriScan AI Team
"""
        )
        mail.send(msg)

        flash("Your message has been sent! Please check your email.", "success")
        return redirect(url_for("contact_page"))

    return render_template("contact.html")


@app.route('/result')
def result_page():
    return render_template('result.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)

        conn = sqlite3.connect('analysis.db')
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                           (username, email, hashed_pw))
            conn.commit()
            flash('Signup successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists.', 'danger')
        finally:
            conn.close()
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = sqlite3.connect('analysis.db')
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[4]  # <--- Add this line
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid credentials', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

@app.route('/predict', methods=['POST'])
def predict():
    if 'username' not in session:
        return redirect(url_for('login'))

    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({'error': 'No file provided'}), 400

    filename = secure_filename(file.filename)
    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    static_path = os.path.join(STATIC_UPLOAD_FOLDER, filename)
    file.save(temp_path)

    with open(temp_path, 'rb') as f_in, open(static_path, 'wb') as f_out:
        f_out.write(f_in.read())

    result = identify_crop_disease(temp_path, PLANT_ID_API_KEY)

    if "error" in result:
        error_msg = result["error"]
        if "429" in error_msg:
            error_msg = "🚫 Too many requests. Please wait 10–15 seconds and try again."
        return render_template("result.html", result={"error": error_msg}, image_name=filename)

    disease = result.get("prediction", "Unknown Disease")
    confidence = result.get("confidence", 0)

    status = 'Infected' if confidence >= 0.7 else ('Likely Healthy' if confidence >= 0.3 else 'Healthy')

    conn = sqlite3.connect('analysis.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO analysis_history (image_name, disease, confidence, status, timestamp)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        filename, disease, confidence, status,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    conn.close()

    return render_template("result.html", result={
        "disease": disease,
        "confidence": confidence,
        "status": status
    }, image_name=filename)

@app.route('/history')
def history_page():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('analysis.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM analysis_history ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    processed_rows = []
    for row in rows:
        row = list(row)
        try:
            row[3] = float(row[3])
        except:
            row[3] = 0.0
        processed_rows.append(row)

    return render_template("history.html", records=processed_rows)

@app.route('/clear_history', methods=['POST'])
def clear_history():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('analysis.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM analysis_history")
    conn.commit()
    conn.close()
    return render_template("history.html", records=[])

@app.route('/download_pdf')
def download_pdf():
    if 'username' not in session:
        return redirect(url_for('login'))

    from reportlab.platypus import SimpleDocTemplate, Image as RLImage, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    disease = request.args.get('disease', 'Unknown')
    confidence = float(request.args.get('confidence', 0)) * 100
    status = request.args.get('status', 'Unknown')
    image_name = request.args.get('image', None)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    story = []

    title_style = styles['Heading1']
    title_style.textColor = colors.green
    story.append(Paragraph("🌿 Plant Disease Detection Report", title_style))
    story.append(Spacer(1, 12))

    image_path = os.path.join('static', 'uploads', image_name) if image_name else None
    img = None
    if image_path and os.path.exists(image_path):
        try:
            img = RLImage(image_path)
            img.drawHeight = 3 * inch
            img.drawWidth = 3 * inch
        except:
            img = None

    info_data = [
        ['🧬 Disease:', disease],
        ['🔎 Confidence:', f"{confidence:.2f}%"],
        ['📊 Status:', status]
    ]
    table_style = TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ])
    info_table = Table(info_data, colWidths=[130, 320])
    info_table.setStyle(table_style)

    if img:
        table = Table([[img, info_table]], colWidths=[3.2 * inch, 3.7 * inch])
    else:
        table = info_table
    story.append(table)

    doc.build(story)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="plant_report.pdf", mimetype='application/pdf')

@app.route('/analytics')
def analytics():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('analysis.db')
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM analysis_history")
    statuses = [row[0] for row in cursor.fetchall()]
    conn.close()

    total = len(statuses)
    infected = statuses.count('Infected')
    likely_healthy = statuses.count('Likely Healthy')
    healthy = statuses.count('Healthy')

    healthy_pct = round((healthy / total) * 100, 2) if total else 0
    likely_healthy_pct = round((likely_healthy / total) * 100, 2) if total else 0
    infected_pct = round((infected / total) * 100, 2) if total else 0

    chart_data = {
        "labels": ["Healthy", "Likely Healthy", "Infected"],
        "counts": [healthy, likely_healthy, infected]
    }

    return render_template("analytics.html", total=total,
                           healthy_pct=healthy_pct,
                           likely_healthy_pct=likely_healthy_pct,
                           infected_pct=infected_pct,
                           chart_data=chart_data)

@app.route('/camera')
def camera_page():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template("camera.html")

@app.route('/camera_predict', methods=['POST'])
def camera_predict():
    if 'username' not in session:
        return redirect(url_for('login'))

    data = request.get_json()
    if not data or "image" not in data:
        return jsonify({'error': 'No image data'}), 400

    try:
        base64_str = data['image'].split(",")[1]
        image_data = base64.b64decode(base64_str)

        filename = f"captured_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        static_path = os.path.join(STATIC_UPLOAD_FOLDER, filename)

        with open(temp_path, "wb") as f:
            f.write(image_data)
        with open(static_path, "wb") as f_out:
            f_out.write(image_data)

        result = identify_crop_disease(temp_path, PLANT_ID_API_KEY)

        if "error" in result:
            error_msg = result["error"]
            if "429" in error_msg:
                error_msg = "🚫 Too many requests. Please wait 10–15 seconds and try again."
            return jsonify({"error": error_msg})

        disease = result.get("prediction", "Unknown Disease")
        confidence = result.get("confidence", 0)
        status = 'Infected' if confidence >= 0.7 else ('Likely Healthy' if confidence >= 0.3 else 'Healthy')

        conn = sqlite3.connect('analysis.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO analysis_history (image_name, disease, confidence, status, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            filename, disease, confidence, status,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        conn.close()

        return jsonify({
            "disease": disease,
            "confidence": confidence,
            "status": status
        })

    except Exception as e:
        return jsonify({"error": f"Failed to process image: {str(e)}"})
    
@app.route('/admin/users')
def view_users():
    if 'username' not in session or session.get('role') != 'admin':
        flash("Access denied: Admins only", "danger")
        return redirect(url_for('home'))

    conn = sqlite3.connect('analysis.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, role FROM users")
    users = cursor.fetchall()
    conn.close()

    return render_template('admin_users.html', users=users)


def init_db():
    conn = sqlite3.connect('analysis.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analysis_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_name TEXT,
            disease TEXT,
            confidence REAL,
            status TEXT,
            timestamp TEXT
        )
    ''')

    # Add role column to users table (admin/user), default to 'user'
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        )
    ''')

    # Optional: Insert default admin user (developer access)
    cursor.execute('SELECT * FROM users WHERE email = ?', ('admin@example.com',))
    if not cursor.fetchone():
        from werkzeug.security import generate_password_hash
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, role)
            VALUES (?, ?, ?, ?)
        ''', ('admin', 'admin@example.com', generate_password_hash('admin123'), 'admin'))

    conn.commit()
    conn.close()


init_db()

from flask_mail import Mail, Message

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')             # App password
app.config['MAIL_DEFAULT_SENDER'] = 'your_admin_email@gmail.com'

mail = Mail(app)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
