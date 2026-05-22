from flask import Flask, request, jsonify, render_template, session, redirect
import os
import uuid
import time
from openai import OpenAI
from supabase import create_client

app = Flask(__name__)

# -----------------------------
# CONFIG
# -----------------------------
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-this")

# -----------------------------
# OPENAI SAFE INIT
# -----------------------------
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key) if api_key else None

# -----------------------------
# SUPABASE SAFE INIT
# -----------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# SYSTEM PROMPT (AI SALES)
# -----------------------------
SYSTEM_PROMPT = """
Eres recepcionista virtual de una clínica estética, dermatológica u odontológica.

OBJETIVO PRINCIPAL:
- Convertir consultas en turnos reales

ESTILO:
- breve
- profesional
- persuasivo
- orientado a agendar

SIEMPRE intenta cerrar con una pregunta.
"""


# -----------------------------
# CLASSIFIER (MVP LOGIC)
# -----------------------------
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


# -----------------------------
# FALLBACK SAFE
# -----------------------------
def fallback(lead_type):
    if lead_type == "CALIENTE":
        return "Perfecto 👌 ¿Querés que te agende un turno esta semana?"
    if lead_type == "TIBIO":
        return "Te explico 👌 ¿qué te gustaría saber primero?"
    return "Hola 👋 ¿en qué te puedo ayudar hoy?"


# -----------------------------
# AI FUNCTION SAFE
# -----------------------------
def ask_ai(message, user_id):

    if not client:
        return None, "fallback"

    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
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


# -----------------------------
# SAFE CHECK (NO CRASH IF SUPABASE OFF)
# -----------------------------
def check_plan_limit(clinic_id):

    if not supabase:
        return True, None

    try:
        clinic = supabase.table("clinics") \
            .select("*") \
            .eq("id", clinic_id) \
            .execute()

        if not clinic.data:
            return False, None

        clinic = clinic.data[0]

        used = clinic.get("leads_used", 0)
        limit = clinic.get("leads_limit", 100)

        if used >= limit:
            return False, clinic

        return True, clinic

    except Exception as e:
        print("SUPABASE ERROR:", str(e))
        return True, None


# -----------------------------
# LOGIN (SAME MVP)
# -----------------------------
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


# -----------------------------
# CHAT (SAFE CORE)
# -----------------------------
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

        ok, _ = check_plan_limit(clinic_id)

        if not ok:
            return jsonify({
                "error": "limit_reached",
                "message": "Plan limit reached"
            }), 403

        lead_type = classify(msg)
        lead_score = score(lead_type)
        lead_stage = stage(lead_score)

        ai_response, mode = ask_ai(msg, user_id)

        if not ai_response:
            ai_response = fallback(lead_type)
            mode = "fallback"

        # SAVE SAFE
        if supabase:
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

            supabase.table("clinics") \
                .update({"leads_used": 1}) \
                .eq("id", clinic_id) \
                .execute()

        return jsonify({
            "user_id": user_id,
            "response": ai_response,
            "lead_type": lead_type,
            "score": lead_score,
            "stage": lead_stage,
            "next_action": "BOOK_APPOINTMENT" if lead_type == "CALIENTE" else "FOLLOW_UP"
        })

    except Exception as e:
        print("CHAT ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


# -----------------------------
# LEADS
# -----------------------------
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


# -----------------------------
# METRICS
# -----------------------------
@app.route("/metrics")
def metrics():

    if "user" not in session:
        return jsonify({"error": "unauthorized"}), 403

    if not supabase:
        return jsonify({
            "total_leads": 0,
            "hot_leads": 0,
            "warm_leads": 0,
            "cold_leads": 0
        })

    data = supabase.table("leads") \
        .select("*") \
        .eq("clinic_id", session.get("clinic_id")) \
        .execute()

    leads = data.data or []

    return jsonify({
        "total_leads": len(leads),
        "hot_leads": len([x for x in leads if x["score"] >= 80]),
        "warm_leads": len([x for x in leads if 50 <= x["score"] < 80]),
        "cold_leads": len([x for x in leads if x["score"] < 50])
    })


# -----------------------------
# DASHBOARD
# -----------------------------
@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/login")

    return render_template("dashboard.html")


# -----------------------------
# HOME
# -----------------------------
@app.route("/")
def home():
    return "AI Clinic SaaS PRO 🚀"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
