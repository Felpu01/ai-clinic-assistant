from flask import Flask, request, jsonify, render_template, session, redirect
import os
import uuid
import time
from openai import OpenAI
from supabase import create_client
import stripe

app = Flask(__name__)

# =========================================================
# CONFIG
# =========================================================
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-this")

# =========================================================
# AI INIT
# =========================================================
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key) if api_key else None

# =========================================================
# SUPABASE INIT
# =========================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# =========================================================
# STRIPE INIT
# =========================================================
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# PRICE IDS
STRIPE_PLANS = {
    "BASIC": "price_1TZlu9PQZfThJzm9pWHoDCom",
    "PRO": "price_1TZlwxPQZfThJzm933I4BxPp"
}

# =========================================================
# SAAS PLANS
# =========================================================
PLANS = {
    "FREE": {"limit": 50},
    "BASIC": {"limit": 300},
    "PRO": {"limit": 2000}
}

# =========================================================
# CLINIC
# =========================================================
def get_clinic(clinic_id):
    if not supabase:
        return None

    res = supabase.table("clinics").select("*").eq("id", clinic_id).execute()
    return res.data[0] if res.data else None


def check_access(clinic_id):
    clinic = get_clinic(clinic_id)

    if not clinic:
        return False, "NO_CLINIC"

    plan = clinic.get("plan", "FREE")
    used = clinic.get("leads_used", 0)
    limit = PLANS.get(plan, PLANS["FREE"])["limit"]

    if used >= limit:
        return False, "LIMIT_REACHED"

    if clinic.get("status", "active") != "active":
        return False, "INACTIVE"

    return True, clinic


def increment_usage(clinic_id):
    if not supabase:
        return

    clinic = supabase.table("clinics").select("leads_used").eq("id", clinic_id).execute()

    if clinic.data:
        used = clinic.data[0].get("leads_used", 0)

        supabase.table("clinics").update({
            "leads_used": used + 1
        }).eq("id", clinic_id).execute()

# =========================================================
# AI CORE
# =========================================================
SYSTEM_PROMPT = "Eres recepcionista de clínica estética. Convertís chats en turnos."


def classify(msg):
    msg = (msg or "").lower()

    if any(x in msg for x in ["turno", "agendar", "reservar"]):
        return "CALIENTE"
    if any(x in msg for x in ["precio", "cuánto", "valor"]):
        return "TIBIO"
    return "FRIO"


def ask_ai(message):
    if not client:
        return "Hola 👋 ¿en qué te ayudo?", "fallback"

    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message}
        ]
    )

    return res.choices[0].message.content, "openai"


# =========================================================
# LOGIN (REAL - SIN DUPLICADOS)
# =========================================================
@app.route("/login")
def login():
    session["user"] = "test"
    session["clinic_id"] = "test_clinic"
    return "logged"


# =========================================================
# STRIPE CHECKOUT
# =========================================================
@app.route("/create-checkout-session", methods=["POST"])
def create_checkout():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 403

    data = request.get_json()
    plan = data.get("plan")

    if plan not in STRIPE_PLANS:
        return jsonify({"error": "invalid plan"}), 400

    try:
        checkout = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{
                "price": STRIPE_PLANS[plan],
                "quantity": 1
            }],
            success_url="https://TU-DOMINIO/dashboard",
            cancel_url="https://TU-DOMINIO/dashboard",
            metadata={
                "clinic_id": session.get("clinic_id"),
                "plan": plan
            }
        )

        return jsonify({"url": checkout.url})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================================
# STRIPE WEBHOOK
# =========================================================
@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    payload = request.data
    sig = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig,
            STRIPE_WEBHOOK_SECRET
        )
    except:
        return jsonify({"error": "invalid webhook"}), 400

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]

        clinic_id = session_obj["metadata"]["clinic_id"]
        plan = session_obj["metadata"]["plan"]

        if supabase:
            supabase.table("clinics").update({
                "plan": plan,
                "status": "active"
            }).eq("id", clinic_id).execute()

    return jsonify({"ok": True})


# =========================================================
# CHAT
# =========================================================
@app.route("/chat", methods=["POST"])
def chat():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 403

    data = request.get_json()
    msg = data.get("message", "")

    ok, clinic = check_access(session.get("clinic_id"))

    if not ok:
        return jsonify({"error": "blocked", "reason": clinic}), 403

    lead_type = classify(msg)
    ai_response, _ = ask_ai(msg)

    increment_usage(session.get("clinic_id"))

    return jsonify({
        "response": ai_response,
        "lead_type": lead_type,
        "plan": clinic.get("plan", "FREE")
    })


# =========================================================
# METRICS
# =========================================================
@app.route("/metrics")
def metrics():
    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 403

    clinic = get_clinic(session.get("clinic_id"))

    return jsonify({
        "plan": clinic.get("plan", "FREE"),
        "used": clinic.get("leads_used", 0),
        "limit": PLANS.get(clinic.get("plan", "FREE"), PLANS["FREE"])["limit"]
    })


# =========================================================
# DASHBOARD
# =========================================================
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    return render_template("dashboard.html")


# =========================================================
# HOME
# =========================================================
@app.route("/")
def home():
    return "AI SaaS PRO 🚀"


# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
