from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, Response, send_file
import psycopg2
from psycopg2.extras import RealDictCursor
import csv
import io
import os
import re
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = 'integrated_health_pro_render_final_v3'

# --- [ตั้งค่าการเชื่อมต่อ] ---
DB_URL = "postgresql://postgres.dwykmsiqyhujvltslbwi:aniwatza11.@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres"

USER_LOGIN = "23256"
USER_PASS = "23256"

# ข้อมูลระบบ
VACCINES_ALL = [
    "OPV1 + DTP-HB-hip1 + Rota1", 
    "IPV1 (ใช้แทน OPV1)",
    "OPV2 + DTP-HB-hip2 + Rota2 + IPV", 
    "IPV2 (ใช้แทน OPV2)",
    "OPV3 + DTP-HB-hip3", 
    "MMR1", 
    "LA-JE1", 
    "OPV4 + DTP4 + MMR2", 
    "LA-JE2", 
    "OPV5 + DTP5"
]

CORE_VACCINES = VACCINES_ALL
VACCINE_SCHEDULE = {
    2: ["OPV1 + DTP-HB-hip1 + Rota1", "IPV1 (ใช้แทน OPV1)"], 
    4: ["OPV2 + DTP-HB-hip2 + Rota2 + IPV", "IPV2 (ใช้แทน OPV2)"], 
    6: ["OPV3 + DTP-HB-hip3"], 
    9: ["MMR1"], 
    12: ["LA-JE1"], 
    18: ["OPV4 + DTP4 + MMR2"], 
    30: ["LA-JE2"], 
    48: ["OPV5 + DTP5"]
}

STOCK_VACCINES = ["OPV", "DTP-HB-Hib", "Rota", "IPV", "MMR", "LA-JE1", "HPV", "dT", "DTP", "BCG", "HB1"]
STOCK_SOURCES = ["รพ.สต.บางตะเคียน", "โรงพยาบาลสมเด็จพระสังฆราชองค์ที่ 17", "คลังนอก", "อื่นๆ"]
STOCK_NOTES = ["นัดฉีดคลินิกเด็กดี (WCC)", "รับเข้าประจำเดือน", "วัคซีนเสื่อมสภาพ/เสีย", "อื่นๆ"]

# --- [UI Styles & Templates] ---
STYLE_ASSETS = '''
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<link href="https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
    body { font-family: 'Prompt', sans-serif; background-color: #f8fafc; color: #334155; }
    .header-bg-stock { background: linear-gradient(135deg, #0284c7 0%, #38bdf8 100%); color: white; padding-top: 2.5rem; padding-bottom: 2rem; border-radius: 0 0 25px 25px; box-shadow: 0 4px 20px rgba(2, 132, 199, 0.15); }
    .header-pink { background: linear-gradient(135deg, #fbc2eb 0%, #a6c1ee 100%); color: #1e293b; padding: 2rem 1.5rem; border-radius: 0 0 25px 25px; box-shadow: 0 4px 15px rgba(251, 194, 235, 0.4); }
    .stock-card { background: white; color: #334155; border-radius: 12px; padding: 15px 20px; min-width: 140px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); border-left: 4px solid #0ea5e9; transition: all 0.2s ease; }
    .stock-card:hover { transform: translateY(-3px); box-shadow: 0 6px 12px rgba(14, 165, 233, 0.15); }
    .card { border-radius: 16px !important; border: 1px solid #e2e8f0 !important; box-shadow: 0 2px 8px rgba(0,0,0,0.02) !important; transition: all 0.2s ease; }
    .card:hover { border-color: #cbd5e1 !important; box-shadow: 0 6px 15px rgba(0,0,0,0.06) !important; }
    .btn-float { position: fixed; bottom: 30px; right: 30px; border-radius: 50px; padding: 14px 28px; font-size: 1.1rem; background: #0284c7; color: white; border: none; box-shadow: 0 4px 15px rgba(2, 132, 199, 0.3); transition: all 0.2s ease; z-index: 1000;}
    .btn-float:hover { background: #0369a1; transform: scale(1.05); color: white; box-shadow: 0 6px 20px rgba(2, 132, 199, 0.4); }
    .modal-content { border-radius: 20px; border: none; box-shadow: 0 15px 35px rgba(0,0,0,0.15); }
    .form-select, .form-control { border-radius: 10px; border: 1px solid #cbd5e1; padding: 0.6rem 1rem; }
    .form-select:focus, .form-control:focus { border-color: #38bdf8; box-shadow: 0 0 0 0.25rem rgba(56, 189, 248, 0.25); }
    .info-card { background: white; border-radius: 16px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 10px rgba(0,0,0,0.03); }
    .text-success { color: #10b981 !important; }
    .text-danger { color: #ef4444 !important; }
    .animate-pulse { animation: pulse 2s infinite; }
    @keyframes pulse { 0% { transform: scale(1); } 50% { transform: scale(1.05); } 100% { transform: scale(1); } }
</style>
'''

NAV_BAR = '''
<nav class="navbar navbar-dark bg-success sticky-top shadow-sm py-3">
    <div class="container-fluid px-3">
        <button class="navbar-toggler border-0 shadow-none" type="button" data-bs-toggle="offcanvas" data-bs-target="#sidebar">
            <span class="navbar-toggler-icon"></span>
        </button>
        <span class="navbar-brand fw-bold mb-0 h1">รพ.สต.บางตะเคียน</span>
        <div class="offcanvas offcanvas-start bg-success text-white" id="sidebar" style="width:280px">
            <div class="offcanvas-header border-bottom border-white border-opacity-25"><h5 class="offcanvas-title fw-bold">เมนูหลัก</h5><button type="button" class="btn-close btn-close-white shadow-none" data-bs-dismiss="offcanvas"></button></div>
            <div class="offcanvas-body p-0"><div class="list-group list-group-flush mt-3"><a href="/" class="list-group-item list-group-item-action bg-transparent text-white border-0 py-3 fs-5"><i class="fas fa-child me-3"></i>ทะเบียนเด็ก</a><a href="/stock" class="list-group-item list-group-item-action bg-transparent text-white border-0 py-3 fs-5"><i class="fas fa-box-open me-3"></i>คลังวัคซีน (Stock)</a><hr class="mx-3 opacity-25"><a href="/logout" class="list-group-item list-group-item-action bg-transparent text-white-50 border-0 py-3">ออกจากระบบ</a></div></div>
        </div>
    </div>
</nav>
'''

LOGIN_HTML = '''<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1">''' + STYLE_ASSETS + '''</head><body><div style="height:100vh; display:flex; align-items:center; justify-content:center; background:#f0fdf4;"><div style="background:white; padding:40px; border-radius:40px; box-shadow:0 20px 50px rgba(0,0,0,0.1); width:100%; max-width:400px; text-align:center;"><h2 class="fw-bold text-success mb-4"><i class="fas fa-clinic-medical me-2"></i>เข้าสู่ระบบ</h2><form method="POST"><input type="text" name="username" class="form-control mb-3 py-3 rounded-pill text-center border-0 bg-light" placeholder="รหัสผู้ใช้งาน" required><input type="password" name="password" class="form-control mb-4 py-3 rounded-pill text-center border-0 bg-light" placeholder="รหัสผ่าน" required><button class="btn btn-success w-100 py-3 rounded-pill fw-bold">เข้าใช้งานระบบ</button></form></div></div></body></html>'''

MAIN_HTML = '''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">''' + STYLE_ASSETS + '''</head><body>''' + NAV_BAR + '''
<div class="container mt-4 pb-5">
    <form class="mb-4"><input type="text" name="search" class="form-control rounded-pill mb-3 border-0 shadow-sm py-3 px-4" placeholder="🔍 ค้นหาชื่อ หรือ เลขบัตรประชาชน..." value="{{search}}"><div class="d-flex justify-content-center gap-2"><button name="filter" value="all" class="btn btn-sm rounded-pill px-4 py-2 fw-bold {{'btn-dark' if current_filter=='all' else 'btn-outline-dark'}}">ทั้งหมด</button><button name="filter" value="this_month" class="btn btn-sm rounded-pill px-4 py-2 fw-bold {{'btn-warning text-dark' if current_filter=='this_month' else 'btn-outline-warning text-dark'}}">ต้องรับเดือนนี้</button><button name="filter" value="overdue" class="btn btn-sm rounded-pill px-4 py-2 fw-bold {{'btn-danger' if current_filter=='overdue' else 'btn-outline-danger'}}">ขาดนัด</button></div></form>
    
    {% for c in children %}
    <div class="card p-3 mb-3">
        <div class="row align-items-center">
            <div class="col-8">
                <div class="mb-1">
                    <span class="badge {{ 'bg-success' if c.in_zone else 'bg-secondary' }} px-2 py-1">{{ 'ในเขต' if c.in_zone else 'นอกเขต' }}</span>
                    {% if c.status=='overdue' %}<span class="badge bg-danger ms-1 animate-pulse px-2 py-1"><i class="fas fa-exclamation-triangle"></i> ขาดนัด!</span>
                    {% elif c.status=='this_month' %}<span class="badge bg-warning text-dark ms-1 px-2 py-1">นัดเดือนนี้</span>{% endif %}
                </div>
                <h5 class="fw-bold m-0 text-dark">{{c.name}}</h5>
                <small class="text-muted"><i class="fas fa-birthday-cake me-1"></i> {{c.birth_date}} ({{c.age_str}})</small>
                <div class="mt-2">
                    <small class="fw-bold text-success" style="font-size:0.75rem">รับวัคซีนแล้ว {{c.coverage_pct}}%</small>
                    <div class="progress mt-1" style="height: 6px; border-radius: 10px;">
                        <div class="progress-bar bg-success progress-bar-striped progress-bar-animated" style="width:{{c.coverage_pct}}%"></div>
                    </div>
                </div>
                <div class="mt-3 d-flex flex-wrap gap-2">
                    <button class="btn btn-sm btn-success rounded-pill px-3 shadow-sm fw-bold" data-bs-toggle="modal" data-bs-target="#service{{c.id}}"><i class="fas fa-syringe me-1"></i>ให้บริการ</button>
                    <button class="btn btn-sm btn-outline-secondary rounded-pill px-3 fw-bold" data-bs-toggle="modal" data-bs-target="#editModal{{c.id}}"><i class="fas fa-edit me-1"></i>แก้ไข</button>
                    <a href="/profile/{{c.id}}" class="btn btn-sm btn-outline-primary rounded-pill px-3 fw-bold"><i class="fas fa-book-medical me-1"></i>สมุด</a>
                    <form action="/delete_child_full/{{c.id}}" method="POST" class="m-0 ms-auto" onsubmit="return confirm('ลบข้อมูลเด็กคนนี้?')">
                        <button class="btn btn-sm text-danger border-0 bg-transparent p-1"><i class="fas fa-trash-alt"></i></button>
                    </form>
                </div>
            </div>
            <div class="col-4 text-end border-start ps-2">
                <small class="text-muted d-block">นัดครั้งต่อไป</small>
                <div class="fw-bold text-primary fs-6 mt-1">{{c.appoint_date or '-'}}</div>
                <div class="text-danger fw-bold small mt-1" style="line-height:1.2; font-size:0.7rem;">{{c.next_vaccine or ''}}</div>
            </div>
        </div>
    </div>

    <div class="modal fade" id="editModal{{c.id}}" tabindex="-1">
        <div class="modal-dialog modal-dialog-centered text-black">
            <div class="modal-content p-4">
                <h5 class="fw-bold text-primary mb-3"><i class="fas fa-user-edit me-2"></i>แก้ไขข้อมูล: {{c.name}}</h5>
                <form action="/edit_child/{{c.id}}" method="POST" class="row g-3">
                    <div class="col-12"><label class="small fw-bold">ชื่อ-นามสกุล</label><input type="text" name="name" class="form-control" value="{{c.name}}" required></div>
                    <div class="col-12"><label class="small fw-bold text-danger">วันเกิด (วว/ดด/พศ)</label><input type="text" name="birth_date" class="form-control border-danger" value="{{c.birth_date}}" required></div>
                    <div class="col-12"><label class="small fw-bold">เลขบัตรประชาชน</label><input type="text" name="id_card" class="form-control" value="{{c.id_card}}"></div>
                    <div class="col-12"><label class="small fw-bold">ที่อยู่ (ใส่เลขหมู่ เช่น ม.2)</label><input type="text" name="address" class="form-control" value="{{c.address}}"></div>
                    <button class="btn btn-primary w-100 rounded-pill py-3 mt-4 fw-bold shadow-sm">บันทึกการแก้ไข</button>
                </form>
            </div>
        </div>
    </div>

    <div class="modal fade" id="service{{c.id}}" tabindex="-1"><div class="modal-dialog modal-dialog-centered text-black"><div class="modal-content p-4"><h5 class="fw-bold text-success mb-3"><i class="fas fa-syringe me-2"></i>ให้บริการ: {{c.name}}</h5><form action="/provide_service/{{c.id}}" method="POST" class="row g-3">
    <div class="col-12 border-bottom pb-3"><label class="small fw-bold text-primary mb-1">วันที่รับบริการ</label><input type="text" name="visit_date" class="form-control bg-light" value="{{today_be}}"></div><div class="col-12"><label class="small fw-bold text-primary mb-1">สถานที่ฉีด</label><select name="location" class="form-select"><option value="รพ.สต.บางตะเคียน" selected>รพ.สต.บางตะเคียน</option><option value="รพ.สมเด็จพระสังฆราชองค์ที่ 17">รพ.สมเด็จพระสังฆราชองค์ที่ 17</option></select></div>
    <div class="col-4"><label class="small text-muted">หนัก(kg)</label><input type="number" step="0.1" name="weight" class="form-control" required></div><div class="col-4"><label class="small text-muted">สูง(cm)</label><input type="number" step="0.1" name="height" class="form-control" required></div><div class="col-4"><label class="small text-muted">รอบศีรษะ</label><input type="number" step="0.1" name="head_circ" class="form-control" required></div>
    <div class="col-12 bg-light p-3 rounded-4 mt-3"><label class="fw-bold mb-2 text-dark"><i class="fas fa-check-square me-2 text-success"></i>วัคซีนที่ฉีดวันนี้</label><div class="row">{% for v in vaccines %}<div class="col-12 mb-2"><div class="form-check"><input class="form-check-input" type="checkbox" name="vaccines_today" value="{{v}}" id="chk_{{c.id}}_{{loop.index}}" {% if c.vaccines_today and v in c.vaccines_today %}checked{% endif %}><label class="form-check-label small" for="chk_{{c.id}}_{{loop.index}}">{{v}}</label></div></div>{% endfor %}</div></div><button class="btn btn-success w-100 rounded-pill py-3 mt-3 fw-bold shadow-sm">บันทึกประวัติ (ไม่ตัดสต็อก)</button></form></div></div></div>
    {% endfor %}

    <button class="btn btn-float fw-bold" data-bs-toggle="modal" data-bs-target="#addModal"><i class="fas fa-plus me-2"></i>ลงทะเบียนเด็กใหม่</button>
</div>

<div class="modal fade" id="addModal" tabindex="-1"><div class="modal-dialog modal-dialog-centered text-black"><div class="modal-content p-4">
<h4 class="fw-bold text-success text-center mb-4"><i class="fas fa-user-plus me-2"></i>ลงทะเบียนเด็ก</h4><form action="/add_child" method="POST" class="row g-3">
<div class="col-12"><label class="small fw-bold">ชื่อ-นามสกุล</label><input type="text" name="name" class="form-control" required></div><div class="col-12"><label class="small fw-bold text-danger">วันเกิด (วว/ดด/พศ)</label><input type="text" name="birth_date" class="form-control border-danger" placeholder="เช่น 1/1/2568" required></div><div class="col-12"><label class="small fw-bold">เลขบัตรประชาชน (ถ้ามี)</label><input type="text" name="id_card" class="form-control"></div><div class="col-12"><label class="small fw-bold">ที่อยู่ (หมู่)</label><input type="text" name="address" class="form-control" placeholder="เช่น หมู่ 2"></div><button class="btn btn-success w-100 rounded-pill py-3 mt-4 fw-bold shadow-sm">บันทึกข้อมูล</button></form></div></div></div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script></body></html>'''

STOCK_HTML = '''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">''' + STYLE_ASSETS + '''</head><body>''' + NAV_BAR + '''
<div class="header-bg-stock mb-4 px-4">
    <div class="container d-flex justify-content-between align-items-center px-0"><div><h3 class="fw-bold m-0"><i class="fas fa-box-open me-2"></i>คลังวัคซีน</h3><small class="opacity-75">จัดการสต็อกแบบ Real-time</small></div><a href="/export_stock" class="btn btn-light text-success rounded-pill fw-bold shadow-sm px-4"><i class="fas fa-file-excel me-2"></i>ส่งออก Excel</a></div>
    <div class="d-flex overflow-auto gap-3 mt-4 pb-3" style="scrollbar-width:none">{% for name in vaccine_names %}<div class="stock-card text-center"><small class="text-muted fw-bold">{{name}}</small><div class="h3 fw-bold mt-1 text-primary">{{stock_map.get(name, 0)}} <small class="fs-6 text-muted">โดส</small></div></div>{% endfor %}</div>
</div>
<div class="container px-4 text-black pb-5">
    <div class="d-flex flex-column gap-3 mb-4">
        <h5 class="fw-bold m-0 text-secondary"><i class="fas fa-history me-2"></i>{{ 'ถังขยะ' if view_deleted else 'ประวัติรับ-จ่าย' }}</h5>
        <form method="GET" class="row g-2 bg-white p-3 rounded-4 shadow-sm border">
            <input type="hidden" name="view_deleted" value="{{ view_deleted }}">
            <div class="col-4"><select name="filter_vaccine" class="form-select border-0 bg-light" onchange="this.form.submit()"><option value="ทั้งหมด">🧪 วัคซีน</option>{% for n in vaccine_names %}<option value="{{n}}" {% if current_vaccine == n %}selected{% endif %}>{{n}}</option>{% endfor %}</select></div>
            <div class="col-4"><select name="filter_source" class="form-select border-0 bg-light" onchange="this.form.submit()"><option value="ทั้งหมด">📍 หน่วยงาน</option>{% for s in sources %}<option value="{{s}}" {% if current_filter == s %}selected{% endif %}>{{s}}</option>{% endfor %}</select></div>
            <div class="col-4"><select name="filter_type" class="form-select border-0 bg-light" onchange="this.form.submit()"><option value="ทั้งหมด">📦 ประเภท</option><option value="รับเข้า" {% if current_type == 'รับเข้า' %}selected{% endif %}>รับเข้า</option><option value="จ่ายออก" {% if current_type == 'จ่ายออก' %}selected{% endif %}>จ่ายออก</option></select></div>
        </form>
    </div>
    
    {% for log in logs %}
    <div class="card p-3 mb-3">
        <div class="d-flex justify-content-between align-items-center">
            <div>
                <b class="text-dark fs-5">{{log.vaccine_name}}</b>
                {% if log.lot or log.exp %}
                <span class="badge text-dark rounded-pill ms-2" style="background-color: #38bdf8; font-weight: 500;">Lot: {{log.lot or '-'}} | Exp: {{log.exp or '-'}}</span>
                {% endif %}
                <br>
                <small class="text-muted"><i class="far fa-calendar-alt me-1"></i>{{log.date}} | <i class="fas fa-map-marker-alt me-1"></i>{{log.source_destination}}</small><br>
                <span class="badge bg-light text-secondary border mt-1">{{log.note}}</span>
            </div>
            <div class="text-end">
                <div class="fw-bold {% if log.receive %}text-success{% else %}text-danger{% endif %} h3 m-0">
                    {% if log.receive %}+{{ log.receive }}{% else %}-{{ log.pay }}{% endif %}
                </div>
                {% if view_deleted %}
                    <a href="/restore_log/{{log.id}}" class="btn btn-sm btn-success rounded-pill px-3 mt-2"><i class="fas fa-undo me-1"></i>กู้คืน</a>
                {% else %}
                    <div class="mt-2">
                        <a href="#" data-bs-toggle="modal" data-bs-target="#editStockModal{{log.id}}" class="text-primary me-3 fs-5"><i class="fas fa-edit"></i></a>
                        <a href="/delete_log/{{log.id}}" class="text-danger opacity-50 fs-5" onclick="return confirm('ลบรายการ?')"><i class="fas fa-trash-alt"></i></a>
                    </div>
                {% endif %}
            </div>
        </div>
    </div>
    
    <div class="modal fade" id="editStockModal{{log.id}}" tabindex="-1">
        <div class="modal-dialog modal-dialog-centered text-black">
            <div class="modal-content p-4">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h5 class="fw-bold text-primary m-0"><i class="fas fa-edit me-2"></i>แก้ไขข้อมูล ({{log.vaccine_name}})</h5>
                    <button type="button" class="btn-close shadow-none" data-bs-dismiss="modal"></button>
                </div>
                <form action="/edit_stock/{{log.id}}" method="POST" class="row g-3">
                    <div class="col-12"><label class="small fw-bold text-muted mb-1">วันที่</label><input type="date" name="log_date" class="form-control bg-light" value="{{log.date}}" required></div>
                    <div class="col-6"><label class="small fw-bold text-muted mb-1">ประเภท</label><select name="action" class="form-select"><option value="receive" {% if log.receive > 0 %}selected{% endif %}>รับเข้า</option><option value="pay" {% if log.pay > 0 %}selected{% endif %}>จ่ายออก</option></select></div>
                    <div class="col-6"><label class="small fw-bold text-muted mb-1">จำนวนโดส</label><input type="number" name="amount" class="form-control" value="{{log.receive if log.receive > 0 else log.pay}}" required></div>
                    <div class="col-12"><label class="small fw-bold text-muted mb-1">หน่วยงาน/แหล่งที่มา</label><select name="source_destination" class="form-select">{% for s in sources %}<option value="{{s}}" {% if log.source_destination == s %}selected{% endif %}>{{s}}</option>{% endfor %}</select></div>
                    <div class="col-6"><label class="small fw-bold text-muted mb-1">Lot No.</label><input type="text" name="lot" class="form-control" value="{{log.lot or ''}}"></div>
                    <div class="col-6"><label class="small fw-bold text-muted mb-1">วันหมดอายุ (Exp)</label><input type="date" name="exp_date" class="form-control" value="{{log.exp or ''}}"></div>
                    <div class="col-12"><label class="small fw-bold text-muted mb-1">หมายเหตุ</label><input type="text" name="note" class="form-control" value="{{log.note or ''}}"></div>
                    <div class="col-12 mt-4"><button class="btn btn-primary w-100 rounded-pill py-3 fw-bold shadow-sm">บันทึกการแก้ไข</button></div>
                </form>
            </div>
        </div>
    </div>
    {% endfor %}

    <button class="btn btn-float fw-bold" data-bs-toggle="modal" data-bs-target="#stockModal"><i class="fas fa-exchange-alt me-2"></i>บันทึก รับ/จ่าย</button>
</div>
<div class="modal fade" id="stockModal" tabindex="-1"><div class="modal-dialog modal-dialog-centered text-black"><div class="modal-content p-4"><h4 class="fw-bold text-primary text-center mb-4"><i class="fas fa-boxes me-2"></i>บันทึกสต็อก</h4><form action="/add_stock" method="POST" class="row g-3">
<div class="col-12"><label class="small fw-bold text-muted">วันที่</label><input type="date" name="log_date" class="form-control bg-light" value="{{today_date}}" required></div>
<div class="col-12"><label class="small fw-bold text-muted">ชื่อวัคซีน</label><select name="vaccine_name" class="form-select">{% for n in vaccine_names %}<option>{{n}}</option>{% endfor %}</select></div>
<div class="col-6"><label class="small fw-bold text-muted">ประเภท</label><select name="action" class="form-select"><option value="receive">รับเข้า</option><option value="pay">จ่ายออก</option></select></div><div class="col-6"><label class="small fw-bold text-muted">จำนวนโดส</label><input type="number" name="amount" class="form-control" required></div>
<div class="col-12"><label class="small fw-bold text-muted">หน่วยงาน</label><select name="source_destination" class="form-select">{% for s in sources %}<option>{{s}}</option>{% endfor %}</select></div>
<div class="col-6"><label class="small fw-bold text-muted">Lot No.</label><input type="text" name="lot" class="form-control"></div><div class="col-6"><label class="small fw-bold text-muted">วันหมดอายุ (Exp)</label><input type="date" name="exp_date" class="form-control"></div>
<div class="col-12"><label class="small fw-bold text-muted">เหตุผล</label><select name="note_choice" class="form-select" onchange="const c=document.getElementById('n_custom'); if(this.value==='อื่นๆ') c.classList.remove('d-none'); else c.classList.add('d-none');">{% for ch in note_choices %}<option value="{{ch}}">{{ch}}</option>{% endfor %}</select><input type="text" id="n_custom" name="note_custom" class="form-control d-none mt-2" placeholder="ระบุเหตุผลเพิ่มเติม..."></div>
<button class="btn btn-primary w-100 rounded-pill py-3 mt-4 fw-bold shadow-sm">ยืนยันการบันทึก</button></form></div></div></div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script></body></html>'''

PROFILE_HTML = '''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">''' + STYLE_ASSETS + '''</head>
<body style="background-color: #fdf2f8;"><div class="header-pink d-flex justify-content-between align-items-center mb-4"><a href="/" class="text-dark text-decoration-none px-2 fw-bold bg-white rounded-pill py-1"><i class="fas fa-chevron-left me-2"></i>กลับ</a><h4 class="fw-bold m-0 pe-2 text-dark"><i class="fas fa-book-medical text-danger me-2"></i>สมุดสีชมพู</h4></div>
<div class="container px-3 pb-5">
<div class="info-card border-top border-5 border-danger shadow-sm"><div class="d-flex justify-content-between align-items-start"><div><h3 class="fw-bold text-dark m-0">{{child.name}}</h3><small class="text-muted"><i class="far fa-calendar-check me-1"></i>เกิด: {{child.birth_date}}</small></div><span class="badge {{ 'bg-success' if child.in_zone else 'bg-secondary' }} px-3 py-2 rounded-pill shadow-sm">{{ 'ในเขต' if child.in_zone else 'นอกเขต' }}</span></div><div class="mt-4 bg-danger bg-opacity-10 p-3 rounded-4 text-center text-danger fw-bold fs-5"><i class="fas fa-birthday-cake me-2"></i>อายุ: {{age_str}}</div></div>
<div class="info-card border-top border-5 border-warning shadow-sm"><h5 class="fw-bold text-warning-emphasis mb-3"><i class="fas fa-history me-2"></i>นำเข้าประวัติ (จากสมุดเล่มจริง)</h5><form action="/add_external_vaccine/{{child.id}}" method="POST" class="row g-2 align-items-end"><div class="col-12"><label class="small text-muted">วัคซีน</label><select name="vaccine_name" class="form-select form-select-sm bg-light">{% for v in vaccines %}<option value="{{v}}">{{v}}</option>{% endfor %}</select></div><div class="col-6"><label class="small text-muted">สถานที่</label><select name="location" class="form-select form-select-sm bg-light"><option value="รพ.สต.บางตะเคียน">รพ.สต.บางตะเคียน</option><option value="รพ.สมเด็จพระสังฆราชองค์ที่ 17" selected>รพ.สมเด็จฯ</option><option value="อื่นๆ">อื่นๆ</option></select></div><div class="col-6"><label class="small text-muted">วันที่</label><input type="text" name="receive_date" class="form-control form-control-sm bg-light" value="{{today_be}}"></div><div class="col-12 mt-3"><button class="btn btn-warning w-100 fw-bold text-dark rounded-pill shadow-sm">บันทึกประวัติย้อนหลัง</button></div></form></div>
<div class="info-card border-top border-5 border-primary shadow-sm"><h5 class="fw-bold text-primary mb-3"><i class="fas fa-chart-line me-2"></i>บันทึกเจริญเติบโต</h5><div class="table-responsive"><table class="table table-hover table-sm text-center align-middle"><thead class="table-light text-muted small"><tr><th>วันที่</th><th>อายุ</th><th>หนัก</th><th>สูง</th><th>ศีรษะ</th><th>ลบ</th></tr></thead><tbody>{% for h in history %}<tr><td><small>{{h.visit_date}}</small></td><td><small>{{h.age_at_visit}}</small></td><td class="fw-bold text-primary">{{h.weight}}</td><td class="fw-bold text-success">{{h.height}}</td><td>{{h.head_circ}}</td><td><form action="/delete_growth/{{h.id}}/{{child.id}}" method="POST" class="m-0"><button class="btn btn-sm text-danger border-0 bg-transparent p-0"><i class="fas fa-times-circle fs-5"></i></button></form></td></tr>{% endfor %}</tbody></table></div></div>
<div class="info-card border-top border-5 border-success shadow-sm"><h5 class="fw-bold text-success mb-3"><i class="fas fa-shield-alt me-2"></i>ความครอบคลุมวัคซีน ({{pct}}%)</h5><div class="progress mb-4" style="height: 10px; border-radius: 5px;"><div class="progress-bar bg-success progress-bar-striped progress-bar-animated" style="width:{{pct}}%"></div></div>{% for v in vaccines %}<div class="d-flex justify-content-between align-items-center border-bottom py-3"><span class="fw-bold text-secondary" style="font-size: 0.9rem;">{{v}}</span>{% if v in v_dict %}<div class="text-end text-success"><b class="fs-6"><i class="fas fa-check-circle me-1"></i>{{v_dict[v].receive_date}}</b><br><small class="text-muted"><i class="fas fa-hospital me-1"></i>{{v_dict[v].location}}</small></div>{% else %}<span class="badge bg-light text-muted border px-3 py-2 rounded-pill"><i class="fas fa-hourglass-half me-1"></i>ยังไม่ได้รับ</span>{% endif %}</div>{% endfor %}</div></div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script></body></html>'''

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
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        b_dt = datetime(y-543, m, d)
        today = datetime.now()
        months = (today.year - b_dt.year) * 12 + today.month - b_dt.month
        if today.day < b_dt.day: months -= 1
        return f"{months // 12} ปี {months % 12} เดือน" if months >= 12 else f"{months} เดือน"
    except: return "-"

def get_auto_schedule_be(birth_be, vaccines_done_str=""):
    try:
        parts = birth_be.split('/')
        d, m, y_be = int(parts[0]), int(parts[1]), int(parts[2])
        b_dt = datetime(y_be-543, m, d)
        done_list = [v.strip() for v in (vaccines_done_str or "").split(',') if v.strip()]
        
        next_vaccine, next_date_str = "ครบเกณฑ์", "-"

        # เช็ควัคซีนทีละกลุ่มเดือน ถ้ากลุ่มไหนยังไม่ฉีดตัวใดตัวหนึ่งเลย ให้นัดตัวแรกของกลุ่มนั้น
        for months in sorted(VACCINE_SCHEDULE.keys()):
            v_options = VACCINE_SCHEDULE[months]
            is_done = any(opt in done_list for opt in v_options)
            
            if not is_done:
                target_month = b_dt.month + months
                target_year = b_dt.year + (target_month - 1) // 12
                target_month = (target_month - 1) % 12 + 1
                
                if b_dt.day > 10:
                    target_month += 1
                    if target_month > 12:
                        target_month = 1
                        target_year += 1

                app_dt = datetime(target_year, target_month, 10)
                if app_dt.weekday() == 5: app_dt += timedelta(days=2)
                elif app_dt.weekday() == 6: app_dt += timedelta(days=1)

                next_vaccine = v_options[0] # โชว์ชื่อตัวแรกของกลุ่มนั้นเป็นตัวนัดถัดไป
                next_date_str = f"{app_dt.day}/{app_dt.month}/{app_dt.year + 543}"
                break
        return next_vaccine, next_date_str
    except Exception as e: return "", ""

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
    in_zone_keys = ["ม.2", "หมู่ 2", "ม.5", "หมู่ 5", "ม.7", "หมู่ 7", "02", "05", "07"]
    
    for r in rows:
        d = dict(r)
        d['age_str'] = calculate_age_be(d['birth_date'])
        addr_clean = (d['address'] or "").replace(" ", "")
        d['in_zone'] = any(k.replace(" ", "") in addr_clean for k in in_zone_keys)
        
        # คำนวณความครอบคลุมใหม่ ให้นับกลุ่มวัคซีน (8 กลุ่ม) ไม่ใช่นับชื่อ
        done_v_list = [v.strip() for v in (d['vaccines_today'] or "").split(',') if v.strip()]
        groups_done = 0
        for m in VACCINE_SCHEDULE:
            if any(opt in done_v_list for opt in VACCINE_SCHEDULE[m]):
                groups_done += 1
        d['coverage_pct'] = int((groups_done / 8) * 100)
        
        d['status'] = 'normal'
        try:
            if d.get('appoint_date') and d.get('appoint_date') != '-':
                p = d['appoint_date'].split('/')
                # แก้มัดบัคแปลงค่า (Strip ก่อนเพื่อตัดช่องว่างทิ้ง)
                app_dt = datetime(int(p[2].strip())-543, int(p[1].strip()), int(p[0].strip()))
                if d['next_vaccine'] != "ครบเกณฑ์":
                    if app_dt.date() < today.date(): d['status'] = 'overdue'
                    elif app_dt.year == today.year and app_dt.month == today.month: d['status'] = 'this_month'
        except: pass
        if filt == 'overdue' and d['status'] != 'overdue': continue
        if filt == 'this_month' and d['status'] != 'this_month': continue
        res.append(d)
    conn.close()
    return render_template_string(MAIN_HTML, children=res, vaccines=VACCINES_ALL, search=search, today_be=f"{today.day}/{today.month}/{today.year+543}", current_filter=filt)

@app.route('/edit_child/<int:id>', methods=['POST'])
@login_required
def edit_child(id):
    d = request.form
    conn = get_db()
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT vaccines_today FROM children WHERE id=%s", (id,))
            child = cur.fetchone()
            nv, nd = get_auto_schedule_be(d.get('birth_date'), child['vaccines_today'])
            cur.execute('''UPDATE children SET name=%s, id_card=%s, birth_date=%s, address=%s, 
                           next_vaccine=%s, appoint_date=%s WHERE id=%s''', 
                        (d.get('name'), d.get('id_card'), d.get('birth_date'), d.get('address'), nv, nd, id))
    conn.close()
    return redirect(url_for('index'))

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

@app.route('/edit_stock/<int:id>', methods=['POST'])
@login_required
def edit_stock(id):
    d = request.form
    amt = int(d['amount'])
    rcv = amt if d['action'] == 'receive' else 0
    py = amt if d['action'] == 'pay' else 0
    
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute('''
                UPDATE logs 
                SET date=%s, receive=%s, pay=%s, lot=%s, exp=%s, source_destination=%s, note=%s
                WHERE id=%s
            ''', (d['log_date'], rcv, py, d.get('lot', ''), d.get('exp_date', ''), d.get('source_destination', ''), d.get('note', ''), id))
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
    nv, nd = get_auto_schedule_be(d.get('birth_date'), "")
    conn = get_db()
    with conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO children (name, id_card, birth_date, address, visit_date, next_vaccine, appoint_date) VALUES (%s,%s,%s,%s,%s,%s,%s)', (d.get('name'), d.get('id_card',''), d.get('birth_date'), d.get('address',''), datetime.now().strftime('%d/%m/%Y'), nv, nd))
    conn.close()
    return redirect(url_for('index'))

@app.route('/provide_service/<int:id>', methods=['POST'])
@login_required
def provide_service(id):
    d = request.form
    v_list_today = d.getlist('vaccines_today')
    loc = d.get('location', 'รพ.สต.บางตะเคียน')
    visit_date = d.get('visit_date')
    conn = get_db()
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT vaccines_today, birth_date FROM children WHERE id=%s', (id,))
            child = cur.fetchone()
            
            old_v = [v.strip() for v in (child['vaccines_today'] or "").split(',') if v.strip()]
            newly_added = [v for v in v_list_today if v not in old_v]
            updated_v_list = list(set(old_v + v_list_today))
            updated_v_str = ", ".join(updated_v_list)
            
            nv, nd = get_auto_schedule_be(child['birth_date'], updated_v_str)
            
            cur.execute('UPDATE children SET weight=%s, height=%s, head_circ=%s, vaccines_today=%s, next_vaccine=%s, appoint_date=%s, visit_date=%s WHERE id=%s', 
                        (d.get('weight',0), d.get('height',0), d.get('head_circ',0), updated_v_str, nv, nd, visit_date, id))
            cur.execute('INSERT INTO growth_history (child_id, visit_date, age_at_visit, weight, height, head_circ) VALUES (%s,%s,%s,%s,%s,%s)', 
                        (id, visit_date, calculate_age_be(child['birth_date']), d.get('weight',0), d.get('height',0), d.get('head_circ',0)))
            for v in newly_added:
                cur.execute('INSERT INTO vaccine_records (child_id, vaccine_name, receive_date, location) VALUES (%s,%s,%s,%s)', (id, v, visit_date, loc))
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
    
    done_v_list = [v.strip() for v in (child['vaccines_today'] or "").split(',') if v.strip()]
    groups_done = 0
    for m in VACCINE_SCHEDULE:
        if any(opt in done_v_list for opt in VACCINE_SCHEDULE[m]):
            groups_done += 1
    pct = int((groups_done / 8) * 100)
    
    today_dt = datetime.now()
    return render_template_string(PROFILE_HTML, child=child, history=hist, vaccines=VACCINES_ALL, v_dict=v_dict, today_be=f"{today_dt.day}/{today_dt.month}/{today_dt.year + 543}", age_str=calculate_age_be(child['birth_date']), pct=pct)

@app.route('/add_external_vaccine/<int:id>', methods=['POST'])
@login_required
def add_external_vaccine(id):
    d = request.form
    v_name, v_date, v_loc = d.get('vaccine_name'), d.get('receive_date'), d.get('location')
    conn = get_db()
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('INSERT INTO vaccine_records (child_id, vaccine_name, receive_date, location) VALUES (%s,%s,%s,%s)', (id, v_name, v_date, v_loc))
            cur.execute('SELECT vaccines_today, birth_date FROM children WHERE id=%s', (id,))
            child = cur.fetchone()
            old_v = [v.strip() for v in (child['vaccines_today'] or "").split(',') if v.strip()]
            if v_name not in old_v:
                old_v.append(v_name)
                v_final = ", ".join(old_v)
                nv, nd = get_auto_schedule_be(child['birth_date'], v_final)
                cur.execute('UPDATE children SET vaccines_today=%s, next_vaccine=%s, appoint_date=%s WHERE id=%s', (v_final, nv, nd, id))
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
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT date, vaccine_name, source_destination, receive, pay, lot, exp, note FROM logs WHERE is_deleted = 0 ORDER BY date DESC, id DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()

        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow(['วันที่', 'ชื่อวัคซีน', 'หน่วยงาน/แหล่งที่มา', 'รับเข้า', 'จ่ายออก', 'Lot', 'วันหมดอายุ', 'หมายเหตุ'])
        for row in rows: writer.writerow(["" if item is None else item for item in row])
        
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=vaccine_stock_report.csv"})
    except Exception as e: return f"<h1>❌ เกิดข้อผิดพลาดในการส่งออกไฟล์</h1><p>Error: {e}</p>"

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
