from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, flash
from flask_cors import CORS
import os, base64, sqlite3
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from plant_api import identify_crop_disease
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PIL import Image
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

# ------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------
print("✅ Loaded API Key:", os.getenv("PLANT_ID_API_KEY"))
PLANT_ID_API_KEY = os.getenv("PLANT_ID_API_KEY")

app = Flask(__name__, template_folder='frontend')
CORS(app)

# 🔑 Jinja filter for pretty timestamps
@app.template_filter('datetimeformat')
def datetimeformat(value, fmt='%d-%m-%Y %H:%M'):
    try:
        dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        return dt.strftime(fmt)
    except Exception:
        return value

app.secret_key = 'your_secret_key_here'  # TODO: set strong key
UPLOAD_FOLDER        = os.path.join(os.getcwd(), 'uploads')
STATIC_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ------------------------------------------------------------------
# ROUTES
# ------------------------------------------------------------------
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

@app.route('/contact', methods=['GET', 'POST'])
def contact_page():
    if request.method == 'POST':
        name, email, message = request.form['name'], request.form['email'], request.form['message']
        msg_body = f"Hi {name},\n\nThanks for reaching out!\n\nWe received your message:\n\"{message}\"\n\nWe'll get back to you shortly.\n\nBest regards,\nAgriScan AI Team"
        mail.send(Message(subject="Thanks for contacting AgriScan AI!", recipients=[email], body=msg_body))
        flash("Your message has been sent! Please check your email.", "success")
        return redirect(url_for('contact_page'))
    return render_template('contact.html')

@app.route('/result')
def result_page():
    return render_template('result.html')

# ---------- AUTHENTICATION ----------------------------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username, email, password = request.form['username'], request.form['email'], request.form['password']
        hashed = generate_password_hash(password)
        conn = sqlite3.connect('analysis.db'); cur = conn.cursor()
        try:
            cur.execute("INSERT INTO users (username,email,password_hash) VALUES (?,?,?)", (username, email, hashed))
            conn.commit(); flash('Signup successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists.', 'danger')
        finally:
            conn.close()
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email, password = request.form['email'], request.form['password']
        conn = sqlite3.connect('analysis.db'); cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email,)); user = cur.fetchone(); conn.close()
        if user and check_password_hash(user[3], password):
            session.update(user_id=user[0], username=user[1], role=user[4])
            flash('Login successful!', 'success'); return redirect(url_for('home'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear(); flash('Logged out successfully.', 'info'); return redirect(url_for('login'))

# ---------- PREDICT -----------------------------------------------
@app.route('/predict', methods=['POST'])
def predict():
    if 'username' not in session:
        return redirect(url_for('login'))

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'No file provided'}), 400

    fname       = secure_filename(file.filename)
    temp_path   = os.path.join(app.config['UPLOAD_FOLDER'], fname)
    static_path = os.path.join(STATIC_UPLOAD_FOLDER, fname)
    file.save(temp_path)
    with open(temp_path,'rb') as fi, open(static_path,'wb') as fo: fo.write(fi.read())

    result = identify_crop_disease(temp_path, PLANT_ID_API_KEY)
    if "error" in result:
        msg = "🚫 Too many requests. Please wait 10–15 s and try again." if "429" in result["error"] else result["error"]
        return render_template("result.html", result={"error": msg}, image_name=fname)

    disease, confidence = result.get("prediction","Unknown Disease"), result.get("confidence",0)
    status = 'Infected' if confidence >= 0.5 else 'Healthy'

    conn = sqlite3.connect('analysis.db'); cur = conn.cursor()
    cur.execute("""INSERT INTO analysis_history (image_name,disease,confidence,status,timestamp)
                   VALUES (?,?,?,?,?)""",
                (fname, disease, confidence, status, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit(); conn.close()

    return render_template("result.html", result={"disease":disease,"confidence":confidence,"status":status},
                           image_name=fname)

# ---------- HISTORY -----------------------------------------------
@app.route('/history')
def history_page():
    if 'username' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('analysis.db'); cur = conn.cursor()
    cur.execute("SELECT * FROM analysis_history ORDER BY id DESC"); rows = cur.fetchall(); conn.close()
    processed = [list(r[:3])+[float(r[3])]+list(r[4:]) for r in rows]  # ensure confidence float
    return render_template('history.html', records=processed)

@app.route('/clear_history', methods=['POST'])
def clear_history():
    if 'username' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('analysis.db'); cur = conn.cursor()
    cur.execute("DELETE FROM analysis_history"); conn.commit(); conn.close()
    return render_template('history.html', records=[])

# ---------- DOWNLOAD PDF ------------------------------------------
@app.route('/download_pdf')
def download_pdf():
    if 'username' not in session:
        return redirect(url_for('login'))
    from reportlab.platypus import SimpleDocTemplate, Image as RLImage, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet; from reportlab.lib import colors; from reportlab.lib.units import inch
    disease  = request.args.get('disease','Unknown')
    confidence = float(request.args.get('confidence',0))*100
    status   = request.args.get('status','Unknown')
    image_name = request.args.get('image',None)

    buf = BytesIO(); doc = SimpleDocTemplate(buf,pagesize=A4,rightMargin=50,leftMargin=50,topMargin=50,bottomMargin=50)
    styles = getSampleStyleSheet(); story=[]
    title_style=styles['Heading1']; title_style.textColor=colors.green
    story.append(Paragraph("🌿 Plant Disease Detection Report", title_style)); story.append(Spacer(1,12))

    image_path = os.path.join('static','uploads',image_name) if image_name else None
    img = RLImage(image_path) if image_path and os.path.exists(image_path) else None
    if img: img.drawHeight, img.drawWidth = 3*inch, 3*inch

    data=[['🧬 Disease:',disease],['🔎 Confidence:',f"{confidence:.2f}%"],['📊 Status:',status]]
    table=Table(data,colWidths=[130,320]); table.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),'Helvetica'),('FONTSIZE',(0,0),(-1,-1),12)]))
    story.append(Table([[img,table]],colWidths=[3.2*inch,3.7*inch]) if img else table)
    doc.build(story); buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="plant_report.pdf", mimetype='application/pdf')

# ---------- ANALYTICS ---------------------------------------------
@app.route('/analytics')
def analytics():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('analysis.db')
    cur = conn.cursor()
    cur.execute("SELECT status FROM analysis_history")
    statuses = [r[0] for r in cur.fetchall()]
    conn.close()

    total = len(statuses)

    healthy = statuses.count('Healthy')
    infected = statuses.count('Infected')

    chart_data = {
        "labels": ["Healthy", "Infected"],
        "counts": [healthy, infected]
    }

    def pct(n):
        return round((n / total) * 100, 2) if total > 0 else 0

    return render_template("analytics.html",
                           total=total,
                           healthy_pct=pct(healthy),
                           infected_pct=pct(infected),
                           chart_data=chart_data)

# ---------- CAMERA PREDICT ----------------------------------------
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
        return jsonify({'error':'No image data'}),400
    try:
        b64 = data['image'].split(",")[1]; image_data = base64.b64decode(b64)
        fname = f"captured_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], fname)
        static_path = os.path.join(STATIC_UPLOAD_FOLDER, fname)
        with open(temp_path,"wb") as f: f.write(image_data)
        with open(static_path,"wb") as f: f.write(image_data)

        result = identify_crop_disease(temp_path, PLANT_ID_API_KEY)
        if "error" in result:
            msg="🚫 Too many requests. Please wait 10–15 s and try again." if "429" in result["error"] else result["error"]
            return jsonify({"error":msg})
        disease, confidence = result.get("prediction","Unknown Disease"), result.get("confidence",0)
        status = 'Infected' if confidence >= 0.5 else 'Healthy'
        conn = sqlite3.connect('analysis.db'); cur = conn.cursor()
        cur.execute("""INSERT INTO analysis_history (image_name,disease,confidence,status,timestamp)
                       VALUES (?,?,?,?,?)""",
                    (fname,disease,confidence,status,datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit(); conn.close()
        return jsonify({"disease":disease,"confidence":confidence,"status":status})
    except Exception as e:
        return jsonify({"error":f"Failed to process image: {str(e)}"})

# ---------- ADMIN USERS -------------------------------------------
@app.route('/admin/users')
def view_users():
    if 'username' not in session or session.get('role')!='admin':
        flash("Access denied: Admins only", "danger"); return redirect(url_for('home'))
    conn = sqlite3.connect('analysis.db'); cur = conn.cursor()
    cur.execute("SELECT id,username,email,role FROM users"); users=cur.fetchall(); conn.close()
    return render_template('admin_users.html', users=users)

# ---------- INIT DB & MAIL ----------------------------------------
def init_db():
    conn = sqlite3.connect('analysis.db'); cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS analysis_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_name TEXT, disease TEXT, confidence REAL,
            status TEXT, timestamp TEXT)
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE, email TEXT UNIQUE,
            password_hash TEXT, role TEXT DEFAULT 'user')
    ''')
    cur.execute("SELECT 1 FROM users WHERE email='admin@example.com'")
    if not cur.fetchone():
        cur.execute("INSERT INTO users (username,email,password_hash,role) VALUES (?,?,?,?)",
                    ('admin','admin@example.com',generate_password_hash('admin123'),'admin'))
    conn.commit(); conn.close()
init_db()

from flask_mail import Mail, Message
app.config.update(
    MAIL_SERVER='smtp.gmail.com', MAIL_PORT=587, MAIL_USE_TLS=True,
    MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER='your_admin_email@gmail.com'
)
mail = Mail(app)

# ------------------------------------------------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
