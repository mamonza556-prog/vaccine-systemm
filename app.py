from flask import Flask, render_template_string, request, redirect, url_for, session, send_file
import sqlite3
import pandas as pd
import io
import os
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = 'vaccine_bangtakean_pro_system'

USER_LOGIN = "23256"
USER_PASS = "23256"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_db():
    conn = sqlite3.connect('vaccine.db')
    conn.row_factory = sqlite3.Row
    return conn

SOURCES = ["โรงพยาบาลสมเด็จพระสังฆราชองค์ที่ 17", "คลังนอก"]
VACCINE_NAMES = ["OPV", "DTP-HB-Hib", "Rota", "IPV", "MMR", "LA-JE1", "HPV", "dT", "DTP"]
NOTE_CHOICES = ["นัดฉีดคลินิกเด็กดี (WCC)", "สนับสนุน รพ.สต. ข้างเคียง", "วัคซีนเสื่อมสภาพ/เสีย", "รับเข้าประจำเดือน", "อื่นๆ (ระบุในหมายเหตุเพิ่ม)"]

def init_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      date TEXT, warehouse TEXT, vaccine_name TEXT, 
                      source_destination TEXT, receive INTEGER, pay INTEGER, 
                      lot TEXT, exp TEXT, note TEXT, is_deleted INTEGER DEFAULT 0)''')
        cursor = conn.execute("PRAGMA table_info(logs)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'note' not in columns:
            conn.execute("ALTER TABLE logs ADD COLUMN note TEXT")
        if 'is_deleted' not in columns:
            conn.execute("ALTER TABLE logs ADD COLUMN is_deleted INTEGER DEFAULT 0")

init_db()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == USER_LOGIN and request.form['password'] == USER_PASS:
            session['logged_in'] = True
            return redirect(url_for('index'))
        return "<script>alert('รหัสไม่ถูกต้อง'); window.location='/login';</script>"
    return render_template_string(LOGIN_STYLE)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    filter_source = request.args.get('filter_source', 'ทั้งหมด')
    filter_type = request.args.get('filter_type', 'ทั้งหมด')
    view_deleted = request.args.get('view_deleted', '0')
    conn = get_db()
    today_str = datetime.now().strftime('%Y-%m-%d')
    stats = conn.execute('SELECT SUM(receive) as rcv, SUM(pay) as py FROM logs WHERE date = ? AND is_deleted = 0', (today_str,)).fetchone()
    
    query = f'SELECT * FROM logs WHERE is_deleted = {view_deleted}'
    params = []
    if filter_source != 'ทั้งหมด':
        query += ' AND source_destination = ?'; params.append(filter_source)
    if filter_type == 'รับเข้า':
        query += ' AND receive > 0'
    elif filter_type == 'จ่ายออก':
        query += ' AND pay > 0'
    query += ' ORDER BY date DESC, id DESC LIMIT 100'
    
    logs_raw = conn.execute(query, params).fetchall()
    summary = conn.execute('SELECT vaccine_name, (SUM(receive) - SUM(pay)) as balance FROM logs WHERE is_deleted = 0 GROUP BY vaccine_name').fetchall()
    stock_map = {s['vaccine_name']: s['balance'] for s in summary}
    
    logs = []
    warning_date = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')
    for row in logs_raw:
        item = dict(row)
        item['is_near_exp'] = item['exp'] <= warning_date if item['exp'] else False
        logs.append(item)
    conn.close()
    return render_template_string(APP_STYLE, logs=logs, stock_map=stock_map, names=VACCINE_NAMES, 
                                  sources=SOURCES, current_filter=filter_source, 
                                  current_type=filter_type, stats=stats, today_date=today_str, 
                                  note_choices=NOTE_CHOICES, view_deleted=int(view_deleted))

@app.route('/add', methods=['POST'])
@login_required
def add():
    vaccine_name = request.form['vaccine_name']
    action = request.form['action']
    amount = int(request.form['amount'])
    source = request.form['source_destination']
    note_choice = request.form.get('note_choice', '')
    note_custom = request.form.get('note_custom', '')
    
    final_note = note_choice if note_choice != "อื่นๆ (ระบุในหมายเหตุเพิ่ม)" else note_custom
    if note_choice == "อื่นๆ (ระบุในหมายเหตุเพิ่ม)" and note_custom:
        final_note = f"อื่นๆ: {note_custom}"

    conn = get_db()
    if action == 'pay':
        res = conn.execute('SELECT (SUM(receive) - SUM(pay)) as bal FROM logs WHERE vaccine_name = ? AND is_deleted = 0', (vaccine_name,)).fetchone()
        current_bal = res['bal'] if res and res['bal'] else 0
        if current_bal < amount:
            conn.close()
            return f"<script>alert('❌ ยอดคงเหลือ {vaccine_name} ไม่พอ'); window.history.back();</script>"
    
    receive = amount if action == 'receive' else 0
    pay = amount if action == 'pay' else 0
    conn.execute('INSERT INTO logs (date, warehouse, vaccine_name, source_destination, receive, pay, lot, exp, note, is_deleted) VALUES (?, "คลังใน", ?, ?, ?, ?, ?, ?, ?, 0)',
                 (request.form['log_date'], vaccine_name, source, receive, pay, request.form['lot'], request.form['exp_date'], final_note))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/delete/<int:log_id>')
@login_required
def delete(log_id):
    conn = get_db()
    conn.execute('UPDATE logs SET is_deleted = 1 WHERE id = ?', (log_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/restore/<int:log_id>')
@login_required
def restore(log_id):
    conn = get_db()
    conn.execute('UPDATE logs SET is_deleted = 0 WHERE id = ?', (log_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index', view_deleted=1))

@app.route('/export')
@login_required
def export():
    conn = get_db()
    df = pd.read_sql_query("SELECT date, vaccine_name, source_destination, receive, pay, lot, exp, note FROM logs WHERE is_deleted = 0", conn)
    conn.close()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name=f'Report_Vaccine_{datetime.now().strftime("%Y%m%d")}.xlsx')

APP_STYLE = '''
<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600&display=swap');
        body { font-family: 'Sarabun', sans-serif; background-color: #f8fafc; color: #1e293b; padding-bottom: 120px; }
        .header-bg { background: linear-gradient(135deg, #064e3b, #059669); color: white; padding: 40px 20px; border-radius: 0 0 50px 50px; box-shadow: 0 10px 30px rgba(5, 150, 105, 0.1); }
        .stock-slider { display: flex; overflow-x: auto; gap: 15px; padding: 15px 0; scrollbar-width: none; }
        .stock-slider::-webkit-scrollbar { display: none; }
        .stock-item { min-width: 110px; background: rgba(255, 255, 255, 0.15); backdrop-filter: blur(12px); padding: 18px; border-radius: 25px; text-align: center; color: white; border: 1px solid rgba(255, 255, 255, 0.2); transition: 0.3s; }
        .log-item { background: white; border-radius: 25px; padding: 22px; margin-bottom: 20px; border-left: 10px solid #10b981; transition: 0.3s; box-shadow: 0 5px 15px rgba(0,0,0,0.02); }
        .log-item.pay { border-left-color: #ef4444; }
        .log-item.deleted { border-left-color: #64748b; opacity: 0.8; }
        .floating-btn { position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%); width: 220px; height: 65px; border-radius: 35px; background: #064e3b; color: white; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 1.1rem; box-shadow: 0 15px 35px rgba(6, 78, 59, 0.3); text-decoration: none; z-index: 1000; transition: 0.3s; }
        .alert-exp { background: #fee2e2; color: #b91c1c; font-weight: bold; padding: 4px 10px; border-radius: 10px; font-size: 0.85rem; border: 1px solid #fecaca; }
        .filter-select { border-radius: 20px; border: none; padding: 10px 20px; font-weight: 600; color: #064e3b; box-shadow: 0 5px 15px rgba(0,0,0,0.05); }
    </style>
</head>
<body>
<div class="header-bg">
    <div class="container d-flex justify-content-between align-items-start mb-4 px-0 px-md-3">
        <div><h3 class="fw-bold m-0 text-white">รพ.สต.บางตะเคียน</h3><p class="small opacity-80 m-0 text-white text-wrap">คลังวัคซีนโรงพยาบาลส่งเสริมสุขภาพตำบลบางตะเคียน</p></div>
        <div class="text-end text-white">
            <a href="/export" class="btn btn-sm btn-light rounded-pill px-3 py-1 fw-bold text-success shadow-sm mb-2">📊 Excel</a><br>
            <a href="/logout" class="text-white small opacity-70 text-decoration-none">ออกจากระบบ</a>
        </div>
    </div>
    <div class="container px-0 px-md-3">
        <div class="row g-3 mb-4 text-center text-white">
            <div class="col-6"><div class="bg-white bg-opacity-10 rounded-4 p-3 border border-white border-opacity-10"><small class="d-block opacity-70">วันนี้รับเข้า</small><span class="h4 fw-bold">{{ stats.rcv or 0 }}</span></div></div>
            <div class="col-6"><div class="bg-white bg-opacity-10 rounded-4 p-3 border border-white border-opacity-10"><small class="d-block opacity-70">วันนี้จ่ายออก</small><span class="h4 fw-bold">{{ stats.py or 0 }}</span></div></div>
        </div>
        <div class="stock-slider">
            {% for name in names %}<div class="stock-item"><div class="small opacity-80 text-white">{{ name }}</div><div class="h5 m-0 fw-bold text-white">{{ stock_map.get(name, 0) }}</div></div>{% endfor %}
        </div>
    </div>
</div>
<div class="container mt-5 px-4">
    <div class="d-flex flex-wrap gap-3 justify-content-between align-items-center mb-4 text-black">
        <div class="d-flex align-items-center gap-2">
            <h5 class="fw-bold m-0 text-secondary">{{ '🗑️ ถังขยะ' if view_deleted else '📑 ประวัติรายการ' }}</h5>
            <a href="/?view_deleted={{ 0 if view_deleted else 1 }}" class="btn btn-sm {{ 'btn-outline-primary' if view_deleted else 'btn-outline-secondary' }} rounded-pill">
                {{ 'หน้าหลัก' if view_deleted else 'ดูถังขยะ' }}
            </a>
        </div>
        <form method="GET" class="d-flex gap-2">
            <input type="hidden" name="view_deleted" value="{{ view_deleted }}">
            <select name="filter_source" class="form-select form-select-sm filter-select shadow-sm" onchange="this.form.submit()"><option value="ทั้งหมด">📍 แหล่ง: ทั้งหมด</option>{% for s in sources %}<option value="{{s}}" {% if current_filter == s %}selected{% endif %}>📍 {{s}}</option>{% endfor %}</select>
            <select name="filter_type" class="form-select form-select-sm filter-select shadow-sm" onchange="this.form.submit()"><option value="ทั้งหมด" {% if current_type == 'ทั้งหมด' %}selected{% endif %}>📦 ประเภท: ทั้งหมด</option><option value="รับเข้า" {% if current_type == 'รับเข้า' %}selected{% endif %}>🟢 รับเข้า</option><option value="จ่ายออก" {% if current_type == 'จ่ายออก' %}selected{% endif %}>🔴 จ่ายออก</option></select>
        </form>
    </div>
    <div class="row g-4">
        {% for log in logs %}
        <div class="col-12 col-xl-6">
            <div class="log-item {{ 'deleted' if view_deleted else ('pay' if log.pay > 0 else '') }}">
                <div class="d-flex justify-content-between align-items-start text-black">
                    <div><h4 class="fw-bold mb-1" style="color: #064e3b;">{{ log.vaccine_name }}</h4><p class="text-muted small mb-1">📍 {{ log.source_destination }}</p>
                    {% if log.note %}<p class="small m-0 text-secondary fw-bold">📝 เหตุผล: {{ log.note }}</p>{% endif %}</div>
                    <div class="text-end">
                        <h3 class="fw-bold {{ 'text-success' if log.receive > 0 else 'text-danger' }} m-0 text-black">{{ "+" ~ log.receive if log.receive > 0 else "-" ~ log.pay }}</h3>
                        <small class="text-muted fw-bold">{{ log.date }}</small>
                    </div>
                </div>
                <div class="d-flex flex-wrap gap-2 align-items-center mt-3 text-black">
                    <span class="badge bg-light text-dark px-4 py-2 rounded-pill border shadow-sm">Lot: {{ log.lot }}</span>
                    <span class="{{ 'alert-exp' if log.is_near_exp else 'small text-muted fw-bold' }}">📅 หมดอายุ: {{ log.exp }}</span>
                    {% if view_deleted %}
                    <a href="/restore/{{log.id}}" class="ms-auto btn btn-success btn-sm rounded-pill px-3">🔄 กู้คืน</a>
                    {% else %}
                    <a href="/delete/{{log.id}}" class="ms-auto btn btn-outline-danger btn-sm border-0 rounded-circle p-2" onclick="return confirm('ย้ายรายการนี้ไปถังขยะ?')">🗑️</a>
                    {% endif %}
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
<a href="#" class="floating-add floating-btn" data-bs-toggle="modal" data-bs-target="#addModal"><span>➕</span> เพิ่มรายการวัคซีน</a>
<div class="modal fade" id="addModal" tabindex="-1 text-black"><div class="modal-dialog modal-dialog-centered px-3 text-black"><div class="modal-content border-0 shadow-lg text-black" style="border-radius: 40px;"><div class="modal-body p-5 text-start text-black">
    <h4 class="fw-bold mb-4 text-center" style="color: #064e3b;">บันทึกข้อมูลวัคซีน</h4>
    <form action="/add" method="POST" class="row g-4 text-black">
        <div class="col-12"><label class="small fw-bold mb-1">📅 วันที่ดำเนินการ</label><input type="date" name="log_date" class="form-control rounded-4 py-3 shadow-sm" required value="{{ today_date }}"></div>
        <div class="col-12"><label class="small fw-bold mb-1">🧪 ชื่อวัคซีน</label><select name="vaccine_name" class="form-select rounded-4 py-3 shadow-sm">{% for n in names %}<option>{{n}}</option>{% endfor %}</select></div>
        <div class="col-12"><label class="small fw-bold mb-1">🏢 หน่วยงาน</label><select name="source_destination" class="form-select rounded-4 py-3 shadow-sm">{% for s in sources %}<option>{{s}}</option>{% endfor %}</select></div>
        <div class="col-6"><label class="small fw-bold mb-1">🔄 ประเภท</label><select name="action" class="form-select rounded-4 py-3 shadow-sm fw-bold"><option value="receive">🟢 รับเข้า</option><option value="pay">🔴 จ่ายออก</option></select></div>
        <div class="col-6"><label class="small fw-bold mb-1">🔢 จำนวน</label><input type="number" name="amount" class="form-control rounded-4 py-3 shadow-sm" placeholder="จำนวน" required min="1"></div>
        <div class="col-6"><label class="small fw-bold mb-1">🏷️ Lot No.</label><input type="text" name="lot" class="form-control rounded-4 py-3 shadow-sm" placeholder="Lot" required></div>
        <div class="col-6"><label class="small fw-bold mb-1">⌛ วันหมดอายุ</label><input type="date" name="exp_date" class="form-control rounded-4 py-3 shadow-sm" required></div>
        <div class="col-12">
            <label class="small fw-bold mb-1">📝 เหตุผลการเบิกจ่าย</label>
            <select name="note_choice" class="form-select rounded-4 py-3 shadow-sm mb-2" onchange="toggleCustomNote(this)">
                {% for choice in note_choices %}
                <option value="{{choice}}">{{choice}}</option>
                {% endfor %}
            </select>
            <input type="text" id="note_custom" name="note_custom" class="form-control rounded-4 py-3 shadow-sm d-none" placeholder="ระบุเหตุผลอื่นๆ...">
        </div>
        <div class="col-12 mt-4 text-center"><button type="submit" class="btn btn-success w-100 py-3 fw-bold rounded-pill shadow">บันทึกข้อมูล</button></div>
    </form>
</div></div></div></div>
<script>
    function toggleCustomNote(select) {
        const customInput = document.getElementById('note_custom');
        if (select.value === "อื่นๆ (ระบุในหมายเหตุเพิ่ม)") {
            customInput.classList.remove('d-none');
        } else {
            customInput.classList.add('d-none');
        }
    }
</script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

LOGIN_STYLE = '''
<!DOCTYPE html>
<html lang="th">
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>body { background-color: #f0fdf4; height: 100vh; display: flex; align-items: center; justify-content: center; font-family: 'Sarabun', sans-serif; }.card-login { border: none; border-radius: 45px; box-shadow: 0 20px 60px rgba(0,0,0,0.1); width: 90%; max-width: 420px; padding: 60px 40px; background: white; text-align: center; }.btn-green { background: linear-gradient(135deg, #064e3b, #059669); color: white; border-radius: 25px; font-weight: 600; padding: 18px; width: 100%; border: none; box-shadow: 0 10px 25px rgba(6, 78, 59, 0.2); transition: 0.3s; }</style>
</head>
<body>
    <div class="card-login">
        <h2 class="fw-bold mb-1" style="color: #064e3b;">🧪 คลังวัคซีน</h2>
        <p class="text-muted mb-5">รพ.สต.บางตะเคียน<br><small>ระบบจัดการคลังวัคซีนออนไลน์</small></p>
        <form method="post"><input type="text" name="username" class="form-control mb-3 py-3 rounded-4 border-0 bg-light text-center" placeholder="Username" required><input type="password" name="password" class="form-control mb-4 py-3 rounded-4 border-0 bg-light text-center" placeholder="Password" required><button type="submit" class="btn btn-green shadow">เข้าสู่ระบบ</button></form>
    </div>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))