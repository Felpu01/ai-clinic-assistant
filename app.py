from flask import Flask, request, jsonify, render_template, session, redirect
import os
import uuid
import time
from openai import OpenAI
from supabase import create_client

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
# SAAS PLANS (NUEVO PASO 7.1)
# =========================================================
PLANS = {
    "FREE": {
        "limit": 50
    },
    "BASIC": {
        "limit": 300
    },
    "PRO": {
        "limit": 2000
    }
}


def get_clinic(clinic_id):
    if not supabase:
        return None

    res = supabase.table("clinics") \
        .select("*") \
        .eq("id", clinic_id) \
        .execute()

    return res.data[0] if res.data else None


def check_access(clinic_id):
    """
    Control central SaaS:
    - plan activo
    - límites
    - existencia de clínica
    """

    clinic = get_clinic(clinic_id)

    if not clinic:
        return False, "NO_CLINIC"

    plan = clinic.get("plan", "FREE")
    used = clinic.get("leads_used", 0)

    limit = PLANS.get(plan, PLANS["FREE"])["limit"]

    # bloqueo por límite
    if used >= limit:
        return False, "LIMIT_REACHED"

    # bloqueo si está inactivo (futuro billing)
    if clinic.get("status", "active") != "active":
        return False, "INACTIVE"

    return True, clinic


def increment_usage(clinic_id):
    if not supabase:
        return

    try:
        clinic = supabase.table("clinics") \
            .select("leads_used") \
            .eq("id", clinic_id) \
            .execute()

        if clinic.data:
            used = clinic.data[0].get("leads_used", 0)

            supabase.table("clinics") \
                .update({"leads_used": used + 1}) \
                .eq("id", clinic_id) \
                .execute()

    except Exception as e:
        print("USAGE ERROR:", str(e))


# =========================================================
# AI CORE ENGINE
# =========================================================

SYSTEM_PROMPT = """
Eres una recepcionista experta en ventas de clínicas estéticas y odontológicas.

OBJETIVO:
Convertir conversaciones en TURNOS CONFIRMADOS.

Reglas:
- siempre empujar a agendar
- respuestas cortas
- siempre cerrar con pregunta
"""


def classify(msg):
    msg = (msg or "").lower()

    if any(x in msg for x in ["turno", "agendar", "reservar", "disponibilidad"]):
        return "CALIENTE"

    if any(x in msg for x in ["precio", "cuánto", "valor", "consulta", "tratamiento"]):
        return "TIBIO"

    return "FRIO"


def score(lead_type):
    return {"CALIENTE": 90, "TIBIO": 60, "FRIO": 20}.get(lead_type, 20)


def stage(score_value):
    if score_value >= 80:
        return "BOOKED_READY"
    if score_value >= 50:
        return "INTERESTED"
    return "NEW"


def fallback(lead_type):
    return {
        "CALIENTE": "Perfecto 👌 ¿Te agendo un turno esta semana?",
        "TIBIO": "Te explico 👌 ¿querés que te recomiende tratamiento o agendamos?",
        "FRIO": "Hola 👋 ¿en qué te puedo ayudar?"
    }.get(lead_type, "Hola 👋 ¿en qué te puedo ayudar?")


def ask_ai(message, user_id, lead_type):

    if not client:
        return None, "fallback"

    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"TIPO_DE_LEAD: {lead_type}"},
            {"role": "user", "content": message}
        ]

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7
        )

        return res.choices[0].message.content, "openai"

    except Exception as e:
        print("OPENAI ERROR:", str(e))
        return None, "fallback"


# =========================================================
# AUTH
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        if not supabase:
            return "DB not configured", 500

        user = supabase.table("users") \
            .select("*") \
            .eq("username", username) \
            .eq("password", password) \
            .execute()

        if user.data:
            session["user"] = user.data[0]["username"]
            session["clinic_id"] = user.data[0]["clinic_id"]
            return redirect("/dashboard")

        return "Login incorrecto", 401

    return """
    <form method="post">
        <input name="username" placeholder="user"/>
        <input name="password" type="password" placeholder="pass"/>
        <button type="submit">Login</button>
    </form>
    """


# =========================================================
# CHAT ENGINE (PROTECTED BY SAAS PLAN)
# =========================================================

@app.route("/chat", methods=["POST"])
def chat():

    try:

        if "user" not in session:
            return jsonify({"error": "unauthorized"}), 403

        data = request.get_json(force=True)

        msg = data.get("message", "")
        user_id = data.get("user_id") or str(uuid.uuid4())
        clinic_id = session.get("clinic_id")

        if not msg:
            return jsonify({"error": "missing message"}), 400

        # 🔒 SAAS ACCESS CHECK (NUEVO)
        ok, clinic_or_reason = check_access(clinic_id)

        if not ok:
            return jsonify({
                "error": "access_denied",
                "reason": clinic_or_reason
            }), 403

        clinic = clinic_or_reason

        # AI FLOW
        lead_type = classify(msg)
        lead_score = score(lead_type)
        lead_stage = stage(lead_score)

        ai_response, mode = ask_ai(msg, user_id, lead_type)

        if not ai_response:
            ai_response = fallback(lead_type)
            mode = "fallback"

        # SAVE LEAD
        if supabase:
            try:
                supabase.table("leads").insert({
                    "id": str(uuid.uuid4()),
                    "clinic_id": clinic_id,
                    "user_id": user_id,
                    "message": msg,
                    "ai_response": ai_response,
                    "lead_type": lead_type,
                    "score": lead_score,
                    "stage": lead_stage,
                    "mode": mode,
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }).execute()

                increment_usage(clinic_id)

            except Exception as e:
                print("SUPABASE WRITE ERROR:", str(e))

        return jsonify({
            "user_id": user_id,
            "response": ai_response,
            "lead_type": lead_type,
            "score": lead_score,
            "stage": lead_stage,
            "plan": clinic.get("plan", "FREE"),
            "next_action": "BOOK_APPOINTMENT" if lead_type == "CALIENTE" else "FOLLOW_UP"
        })

    except Exception as e:
        print("CHAT ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


# =========================================================
# DATA
# =========================================================

@app.route("/leads")
def get_leads():

    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 403

    if not supabase:
        return jsonify([])

    data = supabase.table("leads") \
        .select("*") \
        .eq("clinic_id", session.get("clinic_id")) \
        .order("created_at", desc=True) \
        .execute()

    return jsonify(data.data or [])


@app.route("/metrics")
def metrics():

    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 403

    if not supabase:
        return jsonify({
            "total_leads": 0,
            "hot_leads": 0,
            "warm_leads": 0,
            "cold_leads": 0,
            "conversion_rate": 0,
            "used": 0,
            "limit": 0,
            "plan": "FREE"
        })

    data = supabase.table("leads") \
        .select("*") \
        .eq("clinic_id", session.get("clinic_id")) \
        .execute()

    leads = data.data or []

    total = len(leads)
    hot = len([x for x in leads if x["score"] >= 80])
    warm = len([x for x in leads if 50 <= x["score"] < 80])
    cold = len([x for x in leads if x["score"] < 50])

    clinic = get_clinic(session.get("clinic_id"))

    return jsonify({
        "total_leads": total,
        "hot_leads": hot,
        "warm_leads": warm,
        "cold_leads": cold,
        "conversion_rate": round((hot / total) * 100, 2) if total else 0,
        "used": clinic.get("leads_used", 0) if clinic else 0,
        "limit": PLANS.get(clinic.get("plan", "FREE"), PLANS["FREE"])["limit"] if clinic else 0,
        "plan": clinic.get("plan", "FREE") if clinic else "FREE"
    })


# =========================================================
# UI
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/login")

    return render_template("dashboard.html")


@app.route("/")
def home():
    return "AI Clinic SaaS PRO 🚀"


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
