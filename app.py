from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, Response, send_file
import psycopg2
from psycopg2.extras import RealDictCursor
import csv
import io
import os
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = 'integrated_health_pro_render_final_v3'

# --- [ตั้งค่าการเชื่อมต่อ] ---
DB_URL = "postgresql://postgres.dwykmsiqyhujvltslbwi:aniwatza11.@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres"

USER_LOGIN = "23256"
USER_PASS = "23256"

# ข้อมูลระบบ
VACCINES_ALL = ["BCG", "HB1", "DPT-HB1 OPV1 Rota1", "DPT-HB2 OPV2 Rota2 IPV", "DPT-HB3 OPV3", "MMR1", "LA-JE1", "DTP4 OPV4 MMR2", "LA-JE2", "DTP5 OPV5"]
CORE_VACCINES = ["BCG", "HB1", "DPT-HB1", "DPT-HB2", "DPT-HB3", "MMR1", "LA-JE1", "DTP4", "LA-JE2", "DTP5"]
VACCINE_SCHEDULE = {2: "DPT-HB1 OPV1 Rota1", 4: "DTP-HB2 OPV2 Rota2 IPV", 6: "DTP-HB3 OPV3", 9: "MMR1", 12: "LA-JE1", 18: "DTP4 OPV4 MMR2", 30: "LA-JE2", 48: "DTP5 OPV5"}

STOCK_VACCINES = ["OPV", "DTP-HB-Hib", "Rota", "IPV", "MMR", "LA-JE1", "HPV", "dT", "DTP", "BCG", "HB1"]
STOCK_SOURCES = ["รพ.สต.บางตะเคียน", "โรงพยาบาลสมเด็จพระสังฆราชองค์ที่ 17", "คลังนอก", "อื่นๆ"]
STOCK_NOTES = ["นัดฉีดคลินิกเด็กดี (WCC)", "รับเข้าประจำเดือน", "วัคซีนเสื่อมสภาพ/เสีย", "อื่นๆ"]

# --- [UI Styles & Templates] ---
# ย้ายมาไว้ข้างบนเพื่อให้ Python รู้จักตัวแปรก่อนเรียกใช้
STYLE_ASSETS = '''
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
<style>
    @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600&display=swap');
    body { background:#f8fafc; font-family:'Sarabun',sans-serif; padding-bottom:100px; }
    .card-child { background:white; border-radius:20px; border:none; margin-bottom:15px; border-left:8px solid #10b981; box-shadow:0 4px 10px rgba(0,0,0,0.03); transition:0.2s; }
    .badge-zone { font-size: 0.65rem; padding: 4px 10px; border-radius: 50px; font-weight: 600; color: white; }
    .bg-in { background-color: #10b981; } .bg-out { background-color: #ef4444; }
    .progress-tiny { height: 6px; background: #e2e8f0; border-radius: 10px; margin-top: 4px; overflow: hidden; }
    .btn-float { position:fixed; bottom:25px; left:50%; transform:translateX(-50%); width:220px; border-radius:30px; z-index:1000; box-shadow:0 8px 15px rgba(16,185,129,0.3); font-size: 1.1rem; }
    .header-bg-stock { background: linear-gradient(135deg, #064e3b, #059669); color: white; padding: 30px 20px; border-radius: 0 0 40px 40px; }
    .stock-card { min-width:110px; background:rgba(255,255,255,0.15); backdrop-filter:blur(10px); padding:15px; border-radius:20px; text-align:center; color:white; border:1px solid rgba(255,255,255,0.2); }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    .animate-pulse { animation: pulse 2s infinite; }
</style>
'''

NAV_BAR = '''
<nav class="navbar navbar-dark bg-success sticky-top shadow-sm">
    <div class="container-fluid">
        <button class="navbar-toggler border-0 shadow-none" type="button" data-bs-toggle="offcanvas" data-bs-target="#sidebar">
            <span class="navbar-toggler-icon"></span>
        </button>
        <span class="navbar-brand fw-bold">รพ.สต.บางตะเคียน Online</span>
        <div class="offcanvas offcanvas-start bg-success text-white" id="sidebar" style="width:280px">
            <div class="offcanvas-header border-bottom border-white border-opacity-25"><h5 class="offcanvas-title fw-bold">เมนูหลัก</h5><button type="button" class="btn-close btn-close-white shadow-none" data-bs-dismiss="offcanvas"></button></div>
            <div class="offcanvas-body p-0"><div class="list-group list-group-flush mt-3"><a href="/" class="list-group-item list-group-item-action bg-transparent text-white border-0 py-3 fs-5"><i class="fas fa-child me-3"></i>ทะเบียนเด็ก</a><a href="/stock" class="list-group-item list-group-item-action bg-transparent text-white border-0 py-3 fs-5"><i class="fas fa-box-open me-3"></i>คลังวัคซีน (Stock)</a><hr class="mx-3 opacity-25"><a href="/logout" class="list-group-item list-group-item-action bg-transparent text-white-50 border-0 py-3">ออกจากระบบ</a></div></div>
        </div>
    </div>
</nav>
'''

LOGIN_HTML = '<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">' + STYLE_ASSETS + '</head><body><div style="height:100vh; display:flex; align-items:center; justify-content:center; background:#f0fdf4;"><div style="background:white; padding:40px; border-radius:40px; box-shadow:0 20px 50px rgba(0,0,0,0.1); width:100%; max-width:400px; text-align:center;"><h2 class="fw-bold text-success mb-4">เข้าสู่ระบบ</h2><form method="POST"><input type="text" name="username" class="form-control mb-3 py-3 rounded-pill text-center border-0 bg-light" placeholder="User" required><input type="password" name="password" class="form-control mb-4 py-3 rounded-pill text-center border-0 bg-light" placeholder="Pass" required><button class="btn btn-success w-100 py-3 rounded-pill fw-bold">ตกลง</button></form></div></div></body></html>'

MAIN_HTML = '''
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">''' + STYLE_ASSETS + '''</head>
<body>''' + NAV_BAR + '''
<div class="container mt-4">
    <form class="mb-4"><input type="text" name="search" class="form-control rounded-pill mb-3 border-0 shadow-sm py-2" placeholder="ค้นชื่อ หรือ เลขบัตร..." value="{{search}}"><div class="d-flex justify-content-center gap-2"><button name="filter" value="all" class="btn btn-sm rounded-pill px-4 {{'btn-dark' if current_filter=='all' else 'btn-outline-dark'}}">ทั้งหมด</button><button name="filter" value="this_month" class="btn btn-sm rounded-pill px-4 {{'btn-warning text-dark' if current_filter=='this_month' else 'btn-outline-warning text-dark'}}">เดือนนี้</button><button name="filter" value="overdue" class="btn btn-sm rounded-pill px-4 {{'btn-danger' if current_filter=='overdue' else 'btn-outline-danger'}}">ขาดนัด</button></div></form>
    {% for c in children %}<div class="card card-child p-3"><div class="row align-items-center"><div class="col-8"><div class="mb-1"><span class="badge badge-zone {{ 'bg-in' if c.in_zone else 'bg-out' }}">{{ 'ในเขต' if c.in_zone else 'นอกเขต' }}</span>{% if c.status=='overdue' %}<span class="badge bg-danger ms-1 animate-pulse">ขาดนัด!</span>{% elif c.status=='this_month' %}<span class="badge bg-warning text-dark ms-1">เดือนนี้</span>{% endif %}</div><h5 class="fw-bold m-0 text-dark">{{c.name}}</h5><small class="text-muted">📅 {{c.birth_date}} ({{c.age_str}})</small><div class="mt-2"><div class="d-flex justify-content-between align-items-center"><small class="fw-bold text-success" style="font-size:0.7rem">{{c.coverage_pct}}%</small></div><div class="progress-tiny"><div class="progress-bar bg-success" style="width:{{c.coverage_pct}}%"></div></div></div><div class="mt-3 d-flex gap-1"><button class="btn btn-sm btn-success rounded-pill px-3 shadow-sm" data-bs-toggle="modal" data-bs-target="#service{{c.id}}"><i class="fas fa-syringe me-1"></i>ให้บริการ</button><a href="/profile/{{c.id}}" class="btn btn-sm btn-outline-primary rounded-pill px-3 ms-1"><i class="fas fa-book-medical me-1"></i>ประวัติ</a><form action="/delete_child_full/{{c.id}}" method="POST" class="m-0" onsubmit="return confirm('ลบข้อมูลเด็กคนนี้?')"><button class="btn btn-sm text-danger border-0 p-1"><i class="fas fa-trash-alt"></i></button></form></div></div><div class="col-4 text-end border-start small text-muted">นัดหน้า<div class="fw-bold text-primary fs-6">{{c.appoint_date or '-'}}</div><div class="text-danger fw-bold small">{{c.next_vaccine or ''}}</div></div></div></div>
    <div class="modal fade" id="service{{c.id}}" tabindex="-1"><div class="modal-dialog modal-dialog-centered text-black"><div class="modal-content p-4 rounded-4 shadow-lg border-0"><h5 class="fw-bold text-success mb-3">ให้บริการ: {{c.name}}</h5><form action="/provide_service/{{c.id}}" method="POST" class="row g-3">
    <div class="col-12 border-bottom pb-2"><label class="small fw-bold text-primary">วันที่รับบริการ</label><input type="text" name="visit_date" class="form-control" value="{{today_be}}"></div><div class="col-12"><label class="small fw-bold text-primary">สถานที่ฉีด</label><select name="location" class="form-select text-black"><option value="รพ.สต.บางตะเคียน" selected>รพ.สต.บางตะเคียน</option><option value="รพ.สมเด็จพระสังฆราชองค์ที่ 17">รพ.สมเด็จพระสังฆราชองค์ที่ 17</option></select></div>
    <div class="col-4">หนัก(kg)<input type="number" step="0.1" name="weight" class="form-control" required></div><div class="col-4">สูง(cm)<input type="number" step="0.1" name="height" class="form-control" required></div><div class="col-4">ศีรษะ<input type="number" step="0.1" name="head_circ" class="form-control" required></div>
    <div class="col-12 bg-light p-3 rounded-3 small"><label class="fw-bold mb-2">วัคซีนวันนี้ (ติ๊กถูก)</label><div class="row">{% for v in vaccines %}<div class="col-6 mb-1"><input type="checkbox" name="vaccines_today" value="{{v}}" {% if c.vaccines_today and v in c.vaccines_today %}checked{% endif %}> {{v}}</div>{% endfor %}</div></div><button class="btn btn-success w-100 rounded-pill py-3 mt-1 fw-bold">บันทึกและตัดสต็อก</button></form></div></div></div>{% endfor %}
    <button class="btn btn-success btn-float fw-bold shadow-lg" data-bs-toggle="modal" data-bs-target="#addModal">+ ลงทะเบียนเด็ก</button>
</div>
<div class="modal fade" id="addModal" tabindex="-1"><div class="modal-dialog modal-dialog-centered text-black"><div class="modal-content p-4 rounded-4 border-0">
<h5 class="fw-bold text-success text-center mb-3">ลงทะเบียนเด็กใหม่</h5><form action="/add_child" method="POST" class="row g-3">
<div class="col-12"><label class="small fw-bold">ชื่อ-สกุล</label><input type="text" name="name" class="form-control" required></div><div class="col-12"><label class="small fw-bold text-danger">วันเกิด (วว/ดด/พศ)</label><input type="text" name="birth_date" class="form-control border-danger" placeholder="1/1/2568" required></div><div class="col-12"><label class="small fw-bold">เลขบัตรประชาชน</label><input type="text" name="id_card" class="form-control"></div><div class="col-12"><label class="small fw-bold">ที่อยู่</label><input type="text" name="address" class="form-control"></div><button class="btn btn-success w-100 rounded-pill py-3 mt-3 fw-bold">บันทึก</button></form></div></div></div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script></body></html>
'''

STOCK_HTML = '''
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">''' + STYLE_ASSETS + '''</head>
<body>''' + NAV_BAR + '''
<div class="header-bg-stock mb-4 px-4">
    <div class="container d-flex justify-content-between align-items-start px-0"><div><h4 class="fw-bold m-0">คลังวัคซีน</h4><small class="opacity-75">รพ.สต.บางตะเคียน Online</small></div><a href="/export_stock" class="btn btn-sm btn-light text-success rounded-pill fw-bold">📊 Excel</a></div>
    <div class="d-flex overflow-auto gap-3 mt-3 pb-2" style="scrollbar-width:none">{% for name in vaccine_names %}<div class="stock-card"><small class="opacity-75">{{name}}</small><div class="h5 fw-bold">{{stock_map.get(name, 0)}}</div></div>{% endfor %}</div>
</div>
<div class="container px-4 text-black">
    <div class="d-flex flex-column gap-3 mb-4">
        <h5 class="fw-bold m-0 text-secondary">{{ '🗑️ ถังขยะ' if view_deleted else '📑 ประวัติรายการ' }}</h5>
        <form method="GET" class="row g-2">
            <input type="hidden" name="view_deleted" value="{{ view_deleted }}">
            <div class="col-4"><select name="filter_vaccine" class="form-select rounded-pill small" onchange="this.form.submit()"><option value="ทั้งหมด">🧪 วัคซีน</option>{% for n in vaccine_names %}<option value="{{n}}" {% if current_vaccine == n %}selected{% endif %}>{{n}}</option>{% endfor %}</select></div>
            <div class="col-4"><select name="filter_source" class="form-select rounded-pill small" onchange="this.form.submit()"><option value="ทั้งหมด">📍 หน่วยงาน</option>{% for s in sources %}<option value="{{s}}" {% if current_filter == s %}selected{% endif %}>{{s}}</option>{% endfor %}</select></div>
            <div class="col-4"><select name="filter_type" class="form-select rounded-pill small" onchange="this.form.submit()"><option value="ทั้งหมด">📦 ประเภท</option><option value="รับเข้า" {% if current_type == 'รับเข้า' %}selected{% endif %}>รับเข้า</option><option value="จ่ายออก" {% if current_type == 'จ่ายออก' %}selected{% endif %}>จ่ายออก</option></select></div>
        </form>
    </div>
    {% for log in logs %}<div class="card border-0 shadow-sm rounded-4 p-3 mb-2">
    <div class="d-flex justify-content-between align-items-start">
        <div><b class="text-success">{{log.vaccine_name}}</b><br><small class="text-muted">{{log.date}} | {{log.source_destination}}</small><br><small class="text-secondary">{{log.note}}</small></div>
        <div class="text-end">
            <div class="fw-bold {{'text-success' if log.receive > 0 else 'text-danger'}} h5">{{'+' ~ log.receive if log.receive > 0 else '-' ~ log.pay}}</div>
            {% if view_deleted %}<a href="/restore_log/{{log.id}}" class="btn btn-sm btn-success rounded-pill p-1 px-2 mt-1 small">🔄 กู้คืน</a>
            {% else %}<a href="/delete_log/{{log.id}}" class="text-danger opacity-50" onclick="return confirm('ลบรายการ?')"><i class="fas fa-trash-alt"></i></a>{% endif %}
        </div>
    </div></div>{% endfor %}
    <button class="btn btn-success btn-float fw-bold shadow-lg" data-bs-toggle="modal" data-bs-target="#stockModal">+ บันทึกรับ/จ่าย</button>
</div>
<div class="modal fade" id="stockModal" tabindex="-1"><div class="modal-dialog modal-dialog-centered text-black"><div class="modal-content p-4 rounded-4 border-0"><h5>บันทึกสต๊อก</h5><form action="/add_stock" method="POST" class="row g-3">
<div class="col-12"><label>วันที่</label><input type="date" name="log_date" class="form-control" value="{{today_date}}" required></div>
<div class="col-12"><label>ชื่อวัคซีน</label><select name="vaccine_name" class="form-select">{% for n in vaccine_names %}<option>{{n}}</option>{% endfor %}</select></div>
<div class="col-6"><label>ประเภท</label><select name="action" class="form-select"><option value="receive">รับเข้า</option><option value="pay">จ่ายออก</option></select></div><div class="col-6"><label>จำนวน</label><input type="number" name="amount" class="form-control" required></div>
<div class="col-12"><label>หน่วยงาน</label><select name="source_destination" class="form-select">{% for s in sources %}<option>{{s}}</option>{% endfor %}</select></div>
<div class="col-6"><label>Lot</label><input type="text" name="lot" class="form-control"></div><div class="col-6"><label>Exp</label><input type="date" name="exp_date" class="form-control"></div>
<div class="col-12"><label>เหตุผล</label><select name="note_choice" class="form-select" onchange="const c=document.getElementById('n_custom'); if(this.value==='อื่นๆ') c.classList.remove('d-none'); else c.classList.add('d-none');">{% for ch in note_choices %}<option value="{{ch}}">{{ch}}</option>{% endfor %}</select><input type="text" id="n_custom" name="note_custom" class="form-control d-none mt-2" placeholder="ระบุเหตุผล..."></div>
<button class="btn btn-success w-100 rounded-pill py-3 mt-3 fw-bold">ยืนยัน</button></form></div></div></div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script></body></html>
'''

PROFILE_HTML = '''
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">''' + STYLE_ASSETS + '''
<style>.header-pink{background: linear-gradient(135deg, #ec4899 0%, #f43f5e 100%); color:white; padding:20px; border-radius:0 0 30px 30px; shadow: 0 4px 15px rgba(236,72,153,0.3);}.info-card{background:white; border-radius:20px; padding:20px; margin-bottom:20px; box-shadow:0 5px 15px rgba(0,0,0,0.03)}</style></head>
<body><div class="header-pink d-flex justify-content-between align-items-center mb-4"><a href="/" class="text-white text-decoration-none px-3 fw-bold"><i class="fas fa-arrow-left me-2"></i>กลับ</a><h5 class="fw-bold m-0 pe-3">สมุดสีชมพู</h5></div>
<div class="container px-3"><div class="info-card border-top border-4 border-danger"><div class="d-flex justify-content-between"><div><h4 class="fw-bold text-dark m-0">{{child.name}}</h4><small class="text-muted">📅 เกิด: {{child.birth_date}}</small></div><span class="badge badge-zone {{ 'bg-in' if child.in_zone else 'bg-out' }}">{{ 'ในเขต' if child.in_zone else 'นอกเขต' }}</span></div><div class="mt-3 bg-light p-2 rounded text-center text-success fw-bold">🎂 อายุ: {{age_str}}</div></div>
<div class="info-card border-top border-4 border-warning bg-warning bg-opacity-10"><h6>🏥 นำเข้าประวัติ (สมุดเล่มจริง)</h6><form action="/add_external_vaccine/{{child.id}}" method="POST" class="row g-2 align-items-end"><div class="col-4">วัคซีน<select name="vaccine_name" class="form-select form-select-sm">{% for v in vaccines %}<option value="{{v}}">{{v}}</option>{% endfor %}</select></div><div class="col-4">สถานที่<select name="location" class="form-select form-select-sm"><option value="รพ.สต.บางตะเคียน">รพ.สต.บางตะเคียน</option><option value="รพ.สมเด็จพระสังฆราชองค์ที่ 17" selected>รพ.สมเด็จฯ</option><option value="อื่นๆ">อื่นๆ</option></select></div><div class="col-3">วันที่<input type="text" name="receive_date" class="form-control form-control-sm" value="{{today_be}}"></div><div class="col-1"><button class="btn btn-warning btn-sm w-100 fw-bold">เซฟ</button></div></form></div>
<div class="info-card border-top border-4 border-primary"><h5>บันทึกเจริญเติบโต</h5><div class="table-responsive"><table class="table table-sm small text-center"><thead><tr><th>วันที่</th><th>อายุ</th><th>หนัก</th><th>สูง</th><th>ศีรษะ</th><th>ลบ</th></tr></thead><tbody>{% for h in history %}<tr><td>{{h.visit_date}}</td><td>{{h.age_at_visit}}</td><td>{{h.weight}}</td><td>{{h.height}}</td><td>{{h.head_circ}}</td><td><form action="/delete_growth/{{h.id}}/{{child.id}}" method="POST" class="m-0"><button class="btn btn-sm text-danger border-0 p-0"><i class="fas fa-trash-alt"></i></button></form></td></tr>{% endfor %}</tbody></table></div></div>
<div class="info-card border-top border-4 border-success"><h5>สถานะวัคซีน ({{pct}}%)</h5>{% for v in vaccines %}<div class="d-flex justify-content-between align-items-center border-bottom py-2 small"><span>{{v}}</span>{% if v in v_dict %}<div class="text-end text-success"><b>✅ {{v_dict[v].receive_date}}</b><br><small class="text-muted"><i class="fas fa-hospital"></i> {{v_dict[v].location}}</small></div>{% else %}<span class="text-muted">⏳ ยังไม่ได้รับ</span>{% endif %}</div>{% endfor %}</div></div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script></body></html>
'''

# --- [Functions & Logic] ---

def get_db():
    return psycopg2.connect(DB_URL)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session: return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def calculate_age_be(birth_be):
    try:
        parts = birth_be.split('/')
        d, m, y = int(parts), int(parts), int(parts)
        b_dt = datetime(y-543, m, d)
        today = datetime.now()
        months = (today.year - b_dt.year) * 12 + today.month - b_dt.month
        if today.day < b_dt.day: months -= 1
        return f"{months // 12} ปี {months % 12} เดือน" if months >= 12 else f"{months} เดือน"
    except: return "-"

def get_auto_schedule_be(birth_be):
    try:
        parts = birth_be.split('/')
        d, m, y_be = int(parts), int(parts), int(parts)
        b_dt = datetime(y_be-543, m, d)
        today = datetime.now()
        age_m = (today.year - b_dt.year) * 12 + today.month - b_dt.month
        if today.day < b_dt.day: age_m -= 1
        next_m = next((k for k in sorted(VACCINE_SCHEDULE.keys()) if k > age_m), 0)
        if not next_m: return "ครบเกณฑ์", ""
        app_month = b_dt.month + next_m
        app_year = b_dt.year
        while app_month > 12: app_month -= 12; app_year += 1
        app_dt = datetime(app_year, app_month, 10)
        if app_dt <= today:
            app_month += 1
            if app_month > 12: app_month = 1; app_year += 1
            app_dt = datetime(app_year, app_month, 10)
        while app_dt.weekday() >= 5: app_dt += timedelta(days=1)
        return VACCINE_SCHEDULE[next_m], f"{app_dt.day}/{app_dt.month}/{app_dt.year+543}"
    except: return "", ""

# --- [Routes] ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == USER_LOGIN and request.form.get('password') == USER_PASS:
            session['logged_in'] = True
            return redirect(url_for('index'))
    return render_template_string(LOGIN_HTML)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    search = request.args.get('search', '')
    filt = request.args.get('filter', 'all')
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM children WHERE name ILIKE %s OR id_card ILIKE %s ORDER BY id DESC", (f'%{search}%', f'%{search}%'))
    rows = cur.fetchall()
    res = []
    today = datetime.now()
    for r in rows:
        d = dict(r)
        d['age_str'] = calculate_age_be(d['birth_date'])
        d['in_zone'] = any(z in (d['address'] or "") for z in ["ม.2", "หมู่ 2", "ม.5", "หมู่ 5", "ม.7", "หมู่ 7"])
        d['coverage_pct'] = int((len([v for v in CORE_VACCINES if (d['vaccines_today'] or "") and v in d['vaccines_today']]) / (len(CORE_VACCINES) or 1)) * 100)
        nv, nd = get_auto_schedule_be(d['birth_date'])
        d.update({'preview_next_v': nv, 'preview_next_d': nd, 'status': 'normal'})
        try:
            if d.get('appoint_date'):
                p = d['appoint_date'].split('/')
                app_dt = datetime(int(p)-543, int(p), int(p))
                if d['next_vaccine'] and d['next_vaccine'] != "ครบเกณฑ์":
                    if app_dt.date() < today.date(): d['status'] = 'overdue'
                    elif app_dt.year == today.year and app_dt.month == today.month: d['status'] = 'this_month'
        except: pass
        if filt == 'overdue' and d['status'] != 'overdue': continue
        if filt == 'this_month' and d['status'] != 'this_month': continue
        res.append(d)
    conn.close()
    return render_template_string(MAIN_HTML, children=res, vaccines=VACCINES_ALL, search=search, today_be=f"{today.day}/{today.month}/{today.year+543}", current_filter=filt)

@app.route('/stock')
@login_required
def stock():
    f_src = request.args.get('filter_source', 'ทั้งหมด')
    f_type = request.args.get('filter_type', 'ทั้งหมด')
    f_vac = request.args.get('filter_vaccine', 'ทั้งหมด')
    v_del = int(request.args.get('view_deleted', '0'))
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT COALESCE(SUM(receive),0) as rcv, COALESCE(SUM(pay),0) as py FROM logs WHERE date = %s AND is_deleted = 0', (datetime.now().strftime('%Y-%m-%d'),))
    stats = cur.fetchone()
    cur.execute('SELECT vaccine_name, (SUM(receive) - SUM(pay)) as bal FROM logs WHERE is_deleted = 0 GROUP BY vaccine_name')
    stock_map = {s['vaccine_name']: s['bal'] for s in cur.fetchall()}
    q = 'SELECT * FROM logs WHERE is_deleted = %s'
    p = [v_del]
    if f_vac != 'ทั้งหมด': q += ' AND vaccine_name = %s'; p.append(f_vac)
    if f_src != 'ทั้งหมด': q += ' AND source_destination = %s'; p.append(f_src)
    if f_type == 'รับเข้า': q += ' AND receive > 0'
    elif f_type == 'จ่ายออก': q += ' AND pay > 0'
    q += ' ORDER BY id DESC LIMIT 100'
    cur.execute(q, tuple(p))
    logs = cur.fetchall()
    conn.close()
    return render_template_string(STOCK_HTML, logs=logs, stock_map=stock_map, vaccine_names=STOCK_VACCINES, sources=STOCK_SOURCES, current_filter=f_src, current_type=f_type, current_vaccine=f_vac, stats=stats, today_date=datetime.now().strftime('%Y-%m-%d'), note_choices=STOCK_NOTES, view_deleted=v_del)

@app.route('/add_stock', methods=['POST'])
@login_required
def add_stock():
    d = request.form
    amt = int(d['amount'])
    rcv = amt if d['action'] == 'receive' else 0
    py = amt if d['action'] == 'pay' else 0
    note = d.get('note_choice', '') if d.get('note_choice') != "อื่นๆ" else d.get('note_custom', '')
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO logs (date, vaccine_name, source_destination, receive, pay, lot, exp, note) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)', (d['log_date'], d['vaccine_name'], d['source_destination'], rcv, py, d.get('lot',''), d.get('exp_date',''), note))
    conn.close()
    return redirect(url_for('stock'))

@app.route('/delete_log/<int:id>')
@login_required
def delete_log(id):
    conn = get_db()
    with conn:
        with conn.cursor() as cur: cur.execute('UPDATE logs SET is_deleted = 1 WHERE id = %s', (id,))
    conn.close()
    return redirect(url_for('stock'))

@app.route('/restore_log/<int:id>')
@login_required
def restore_log(id):
    conn = get_db()
    with conn:
        with conn.cursor() as cur: cur.execute('UPDATE logs SET is_deleted = 0 WHERE id = %s', (id,))
    conn.close()
    return redirect(url_for('stock', view_deleted=1))

@app.route('/add_child', methods=['POST'])
@login_required
def add_child():
    d = request.form
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO children (name, id_card, birth_date, address, visit_date) VALUES (%s,%s,%s,%s,%s)', (d.get('name'), d.get('id_card',''), d.get('birth_date'), d.get('address',''), datetime.now().strftime('%d/%m/%Y')))
    conn.close()
    return redirect(url_for('index'))

@app.route('/provide_service/<int:id>', methods=['POST'])
@login_required
def provide_service(id):
    d = request.form
    v_list = d.getlist('vaccines_today')
    loc = d.get('location', 'รพ.สต.บางตะเคียน')
    visit_date = d.get('visit_date')
    conn = get_db()
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT name, vaccines_today, birth_date FROM children WHERE id=%s', (id,))
            child = cur.fetchone()
            old_v = (child['vaccines_today'] or "").split(', ')
            newly_added = [v for v in v_list if v not in old_v]
            nv, nd = get_auto_schedule_be(child['birth_date'])
            cur.execute('UPDATE children SET weight=%s, height=%s, head_circ=%s, vaccines_today=%s, next_vaccine=%s, appoint_date=%s, visit_date=%s WHERE id=%s', (d.get('weight',0), d.get('height',0), d.get('head_circ',0), ", ".join(v_list), nv, nd, visit_date, id))
            cur.execute('INSERT INTO growth_history (child_id, visit_date, age_at_visit, weight, height, head_circ) VALUES (%s,%s,%s,%s,%s,%s)', (id, visit_date, calculate_age_be(child['birth_date']), d.get('weight',0), d.get('height',0), d.get('head_circ',0)))
            for v in newly_added:
                cur.execute('INSERT INTO vaccine_records (child_id, vaccine_name, receive_date, location) VALUES (%s,%s,%s,%s)', (id, v, visit_date, loc))
                v_short = v.split(' ')
                cur.execute('INSERT INTO logs (date, vaccine_name, source_destination, pay, note) VALUES (%s,%s,%s,%s,%s)', (datetime.now().strftime('%Y-%m-%d'), v_short, "ให้บริการเด็ก", 1, f"ฉีดให้น้อง {child['name']}"))
    conn.close()
    return redirect(url_for('index'))

@app.route('/profile/<int:id>')
@login_required
def profile(id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM children WHERE id=%s', (id,))
    child = cur.fetchone()
    if not child: return redirect(url_for('index'))
    cur.execute('SELECT * FROM growth_history WHERE child_id=%s ORDER BY id DESC', (id,))
    hist = cur.fetchall()
    cur.execute('SELECT * FROM vaccine_records WHERE child_id=%s', (id,))
    v_rec = cur.fetchall()
    v_dict = {r['vaccine_name']: r for r in v_rec}
    conn.close()
    age_str = calculate_age_be(child['birth_date'])
    pct = int((len([v for v in CORE_VACCINES if (child['vaccines_today'] or "") and v in child['vaccines_today']]) / (len(CORE_VACCINES) or 1)) * 100)
    today_dt = datetime.now()
    today_be_str = f"{today_dt.day}/{today_dt.month}/{today_dt.year + 543}"
    return render_template_string(PROFILE_HTML, child=child, history=hist, vaccines=VACCINES_ALL, v_dict=v_dict, today_be=today_be_str, age_str=age_str, pct=pct)

@app.route('/add_external_vaccine/<int:id>', methods=['POST'])
@login_required
def add_external_vaccine(id):
    d = request.form
    v_name, v_date, v_loc = d.get('vaccine_name'), d.get('receive_date'), d.get('location')
    conn = get_db()
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('INSERT INTO vaccine_records (child_id, vaccine_name, receive_date, location) VALUES (%s,%s,%s,%s)', (id, v_name, v_date, v_loc))
            cur.execute('SELECT vaccines_today FROM children WHERE id=%s', (id,))
            child = cur.fetchone()
            cur_v = (child['vaccines_today'] or "").split(', ')
            if v_name not in cur_v:
                cur_v.append(v_name)
                v_final = ", ".join([v for v in VACCINES_ALL if v in cur_v])
                cur.execute('UPDATE children SET vaccines_today=%s WHERE id=%s', (v_final, id))
    conn.close()
    return redirect(url_for('profile', id=id))

@app.route('/delete_child_full/<int:id>', methods=['POST'])
@login_required
def delete_child_full(id):
    conn = get_db()
    with conn:
        with conn.cursor() as cur: cur.execute('DELETE FROM children WHERE id=%s', (id,))
    conn.close()
    return redirect(url_for('index'))

@app.route('/delete_growth/<int:history_id>/<int:child_id>', methods=['POST'])
@login_required
def delete_growth(history_id, child_id):
    conn = get_db()
    with conn:
        with conn.cursor() as cur: cur.execute('DELETE FROM growth_history WHERE id=%s', (history_id,))
    conn.close()
    return redirect(url_for('profile', id=child_id))

@app.route('/export_stock')
@login_required
def export_stock():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT date, vaccine_name, source_destination, receive, pay, note FROM logs WHERE is_deleted = 0")
    rows = cur.fetchall()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['วันที่', 'วัคซีน', 'หน่วยงาน', 'รับ', 'จ่าย', 'หมายเหตุ'])
    for r in rows: cw.writerow(list(r))
    return Response(si.getvalue().encode('utf-8-sig'), mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=stock_report.csv"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
