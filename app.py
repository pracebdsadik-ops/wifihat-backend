import os
import random
import string
import sqlite3
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import routeros_api

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
# It is highly recommended to set these as Environment Variables in production
ROUTER_IP = os.getenv("ROUTER_IP", "10.120.0.1")
ROUTER_USER = os.getenv("ROUTER_USER", "voucherbot")
ROUTER_PASS = os.getenv("ROUTER_PASS", "vsadikv+-72345")
BOHUDUR_API_KEY = os.getenv("BOHUDUR_API_KEY", "jHfeNZCQJ0zqAROgD4WdstxFiSIcGrbB")

DB_FILE = "payments.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments(
        paymentkey TEXT PRIMARY KEY,
        voucher TEXT,
        profile TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()

# Note: Global variables are not thread-safe in production (like Gunicorn). 
# Consider moving this to your database if scaling.
last_voucher = {
    "voucher": "000000000000",
    "profile": "7_day"
}

PACKAGE_MAP = {
    "2_hour": 10,
    "1_day": 15,
    "2_day": 25,
    "5_day": 50,
    "7_day": 65,
    "15_day": 85,
    "month_1": 100,
    "month_2": 150,
    "month_3": 220,
    "month_5": 350
}

def mikrotik_connect():
    return routeros_api.RouterOsApiPool(
        host=ROUTER_IP,
        username=ROUTER_USER,
        password=ROUTER_PASS,
        port=8728,
        plaintext_login=True
    )

def random_voucher():
    return ''.join(random.choices(string.digits, k=12))

def verify_payment(paymentkey):
    r = requests.post(
        "https://request.bohudur.one/execute/v2/",
        headers={
            "AH-BOHUDUR-API-KEY": BOHUDUR_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "paymentkey": paymentkey
        }
    )
    return r.json()

@app.route("/")
def home():
    return "WiFi Hat OK"

@app.route("/profiles")
def profiles():
    con = mikrotik_connect()
    try:
        api = con.get_api()
        p = api.get_resource("/ip/hotspot/user/profile")
        rows = p.get()
        out = [r.get("name", "") for r in rows if r.get("name", "")]
        return jsonify(out)
    finally:
        con.disconnect()

@app.route("/voucher", methods=["POST"])
def voucher():
    global last_voucher
    data = request.json
    profile = data.get("profile")

    con = mikrotik_connect()
    try:
        api = con.get_api()
        hotspot = api.get_resource("/ip/hotspot/user")

        while True:
            code = random_voucher()
            chk = hotspot.get(name=code)
            if not chk:
                break

        hotspot.add(
            name=code,
            password="",
            profile=profile
        )

        last_voucher = {
            "voucher": code,
            "profile": profile
        }

        return jsonify({
            "voucher": code,
            "profile": profile
        })
    finally:
        con.disconnect()

@app.route("/status")
def status():
    con = mikrotik_connect()
    try:
        api = con.get_api()
        hotspot = api.get_resource("/ip/hotspot/user")
        active = api.get_resource("/ip/hotspot/active")
        
        users = hotspot.get()
        act = active.get()
        
        amap = {a.get("user", ""): a for a in act}

        result = []
        for u in users:
            name = u.get("name", "")
            if name in ["admin", "default-trial"]:
                continue

            st = "Unused"
            mac = "-"
            remain = "-"
            expire = "-"

            if name in amap:
                st = "Used"
                mac = amap[name].get("mac-address", "-")
                remain = amap[name].get("uptime", "-")
                expire = "Running"

            result.append({
                "voucher": name,
                "profile": u.get("profile", ""),
                "status": st,
                "mac": mac,
                "remain": remain,
                "expire": expire
            })

        return jsonify(result)
    finally:
        con.disconnect()

@app.route("/stats")
def stats():
    con = mikrotik_connect()
    try:
        api = con.get_api()
        hotspot = api.get_resource("/ip/hotspot/user")
        active = api.get_resource("/ip/hotspot/active")
        
        users = hotspot.get()
        online = active.get()
        
        total = sum(1 for u in users if u.get("name", "") not in ["admin", "default-trial"])
        used = len(online)
        unused = max(total - used, 0)
        
        return jsonify({
            "total": total,
            "used": used,
            "unused": unused,
            "online": used
        })
    finally:
        con.disconnect()

@app.route("/delete/<voucher>", methods=["DELETE"])
def delete(voucher):
    try:
        con = mikrotik_connect()
        try:
            api = con.get_api()
            hotspot = api.get_resource("/ip/hotspot/user")
            
            users = hotspot.get(name=voucher)
            if not users:
                return jsonify({
                    "ok": False,
                    "msg": "Voucher not found"
                })

            uid = users[0].get("id") or users[0].get(".id")
            
            if not uid:
                return jsonify({
                    "ok": False,
                    "msg": "User ID not found"
                })

            hotspot.remove(id=uid)
            return jsonify({"ok": True})
        finally:
            con.disconnect()
            
    except Exception as e:
        print("DELETE ERROR:", str(e))
        return jsonify({
            "ok": False,
            "msg": str(e)
        })

@app.route("/export/csv")
def csv_export():
    con = mikrotik_connect()
    try:
        api = con.get_api()
        hotspot = api.get_resource("/ip/hotspot/user")
        users = hotspot.get()
        
        txt = "voucher,profile\n"
        for u in users:
            txt += u.get("name", "") + "," + u.get("profile", "") + "\n"
            
        return txt
    finally:
        con.disconnect()

@app.route("/export/txt")
def txt_export():
    con = mikrotik_connect()
    try:
        api = con.get_api()
        hotspot = api.get_resource("/ip/hotspot/user")
        users = hotspot.get()
        
        txt = ""
        for u in users:
            txt += u.get("name", "") + "\n"
            
        return txt
    finally:
        con.disconnect()

@app.route("/admin")
def admin():
    return render_template("admin.html")

@app.route("/print/v1")
def print_v1():
    return render_template(
        "print_v1.html",
        voucher=last_voucher["voucher"],
        package=last_voucher["profile"],
        device="1 Device",
        price="150"
    )

@app.route("/print/v2")
def print_v2():
    return render_template(
        "print_v2.html",
        voucher=last_voucher["voucher"],
        package=last_voucher["profile"],
        device="1 Device",
        price="250"
    )

@app.route("/list")
def list_voucher():
    con = mikrotik_connect()
    try:
        api = con.get_api()
        hotspot = api.get_resource("/ip/hotspot/user")
        rows = hotspot.get()

        out = [{"voucher": r.get("name", ""), "profile": r.get("profile", "")} for r in rows]
        return jsonify(out)
    finally:
        con.disconnect()

@app.route("/create-payment", methods=["POST"])
def create_payment():
    print("PAYMENT REQUEST RECEIVED")
    data = request.json
    print(data)
    
    profile = data.get("profile")
    amount = PACKAGE_MAP.get(profile)

    if not amount:
        return jsonify({
            "ok": False,
            "msg": "Invalid package"
        })

    mac = data.get("mac", "")
    ip = data.get("ip", "")
    link_login = data.get("link_login", "")
    link_orig = data.get("link_orig", "")

    payload = {
        "full_name": "WiFi Hat User",
        "email": "user@wifihat.net",
        "amount": amount,
        "return_type": "GET",
        "redirect_url": "https://web-production-51370.up.railway.app/payment-success",
        "cancel_url": "https://web-production-51370.up.railway.app/payment-cancel",
        "metadata": {
            "profile": profile,
            "mac": mac,
            "ip": ip,
            "link_login": link_login,
            "link_orig": link_orig
        }
    }

    r = requests.post(
        "https://request.bohudur.one/create/v2/",
        headers={
            "Content-Type": "application/json",
            "AH-BOHUDUR-API-KEY": BOHUDUR_API_KEY
        },
        json=payload
    )

    print("STATUS:", r.status_code)
    print("BODY:", r.text)
    
    return jsonify(r.json())

@app.route("/payment-success", strict_slashes=False)
def payment_success():
    paymentkey = request.args.get("paymentkey")

    if not paymentkey:
        return "Missing paymentkey", 400

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute(
        "SELECT voucher, profile FROM payments WHERE paymentkey=?",
        (paymentkey,)
    )

    existing = cur.fetchone()

    # IF PAYMENT ALREADY PROCESSED
    if existing:
        voucher = existing[0]
        profile = existing[1]
        conn.close()

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
        <title>Payment Success</title>
        <style>
        body{{ font-family:Arial; background:#f5f7fa; display:flex; justify-content:center; align-items:center; height:100vh; }}
        .card{{ background:white; padding:30px; border-radius:15px; text-align:center; box-shadow:0 0 20px rgba(0,0,0,.1); max-width:400px; width:100%; }}
        .voucher{{ font-size:32px; font-weight:bold; color:#4B0082; margin:15px 0; }}
        .btn{{ background:#4B0082; color:white; border:none; padding:12px 20px; border-radius:8px; cursor:pointer; }}
        </style>
        </head>
        <body>
        <div class="card">
        <h1>✅ Payment Successful</h1>
        <p>Package: {profile}</p>
        <div class="voucher" id="voucher">{voucher}</div>
        <button class="btn" onclick="copyVoucher()">Copy Voucher</button>
        <p style="margin-top:15px;">আপনার ভাউচার সংরক্ষণ করুন</p>
        <div id="countdown" style="margin-top:15px;color:red;font-weight:bold;">
        Auto Login in 3 seconds...
        </div>
        <p>যদি Auto Login কাজ না করে, Voucher Copy করে Manual Login করুন।</p>
        <p>Support: 01733243216</p>
        </div>
        <script>
        function copyVoucher(){{
            navigator.clipboard.writeText(document.getElementById('voucher').innerText);
            alert('Voucher Copied');
        }}
        let sec = 3;
        const timer = setInterval(function() {{
            sec--;
            document.getElementById("countdown").innerText = "Auto Login in " + sec + " seconds...";
            if(sec <= 0){{ clearInterval(timer); }}
        }}, 1000);
        </script>
        </body>
        </html>
        """

    # NEW PAYMENT PROCESSING
    verify = verify_payment(paymentkey)
    print("VERIFY =", verify)
    
    metadata = verify.get("metadata", {})
    print("METADATA =", metadata)
    profile = metadata.get("profile")
    
    link_login = metadata.get("link_login", "")
    link_orig = metadata.get("link_orig", "")
    
    print("AUTO LOGIN URL =", link_login)

    if not profile:
        return f"Profile not found. Response = {verify}", 400

    con = mikrotik_connect()
    try:
        api = con.get_api()
        hotspot = api.get_resource("/ip/hotspot/user")

        while True:
            code = random_voucher()
            chk = hotspot.get(name=code)
            if not chk:
                break

        hotspot.add(
            name=code,
            password="",
            profile=profile
        )
    finally:
        con.disconnect()

    cur.execute(
        """
        INSERT INTO payments
        (paymentkey,voucher,profile)
        VALUES (?,?,?)
        """,
        (paymentkey, code, profile)
    )

    conn.commit()
    conn.close()

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
    <title>Payment Success</title>
    <style>
    body{{ font-family:Arial; background:#f5f7fa; display:flex; justify-content:center; align-items:center; height:100vh; }}
    .card{{ background:white; padding:30px; border-radius:15px; text-align:center; box-shadow:0 0 20px rgba(0,0,0,.1); max-width:400px; width:100%; }}
    .voucher{{ font-size:32px; font-weight:bold; color:#4B0082; margin:15px 0; }}
    .btn{{ background:#4B0082; color:white; border:none; padding:12px 20px; border-radius:8px; cursor:pointer; }}
    </style>
    </head>
    <body>
    <div class="card">
    <h1>✅ Payment Successful</h1>
    <p>Package: {profile}</p>
    <div class="voucher" id="voucher">{code}</div>
    <button class="btn" onclick="copyVoucher()">Copy Voucher</button>
    <p style="margin-top:15px;">আপনার ভাউচার সংরক্ষণ করুন</p>
    </div>
    <form id="autologin" action="{link_login}" method="post" style="display:none;">
        <input type="hidden" name="username" value="{code}">
        <input type="hidden" name="password" value="">
        <input type="hidden" name="dst" value="{link_orig}">
        <input type="hidden" name="popup" value="true">
    </form>
    <script>
    function copyVoucher() {{
        navigator.clipboard.writeText(document.getElementById('voucher').innerText);
        alert('Voucher Copied');
    }}
    setTimeout(function() {{
        const form = document.getElementById("autologin");
        if (form && form.action) {{ form.submit(); }}
    }}, 3000);
    </script>
    </body>
    </html>
    """

@app.route("/payment-cancel")
def payment_cancel():
    return "<h1>Payment Cancelled</h1>"

# Initialize DB on start
init_db()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
