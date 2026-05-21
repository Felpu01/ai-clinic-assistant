from flask import Flask, request, jsonify, render_template
import os
import uuid
import time
from openai import OpenAI
from supabase import create_client

app = Flask(__name__)

# -----------------------------
# OPENAI
# -----------------------------
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key) if api_key else None

# -----------------------------
# SUPABASE
# -----------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# SYSTEM PROMPT
# -----------------------------
SYSTEM_PROMPT = """
Eres recepcionista virtual de una clínica estética, dermatológica u odontológica.
OBJETIVO: convertir consultas en turnos.

Responde breve, profesional y orientado a cerrar turnos.
"""

# -----------------------------
# CLASSIFIER
# -----------------------------
def classify(msg):
    msg = (msg or "").lower()

    if any(x in msg for x in ["turno", "agendar", "reservar", "disponibilidad", "cuando puedo"]):
        return "CALIENTE"

    if any(x in msg for x in ["precio", "cuánto", "valor", "info", "consulta", "tratamiento"]):
        return "TIBIO"

    return "FRIO"


def score(lead_type):
    return {
        "CALIENTE": 90,
        "TIBIO": 60,
        "FRIO": 20
    }[lead_type]


def stage(score_value):
    if score_value >= 80:
        return "BOOKED_READY"
    if score_value >= 50:
        return "INTERESTED"
    return "NEW"


# -----------------------------
# FALLBACK
# -----------------------------
def fallback(lead_type):
    if lead_type == "CALIENTE":
        return "Perfecto 👌 te puedo agendar un turno. ¿Qué día te queda cómodo?"
    if lead_type == "TIBIO":
        return "Te explico 👌 ¿querés que te recomiende el mejor tratamiento?"
    return "Hola 👋 ¿qué te gustaría consultar?"


# -----------------------------
# OPENAI SAFE MEMORY
# -----------------------------
def ask_ai(message, user_id):

    if not client:
        return None, "fallback"

    try:

        memory = (
            supabase
            .table("leads")
            .select("message")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if memory.data:
            for m in reversed(memory.data):
                messages.append({
                    "role": "user",
                    "content": m["message"]
                })

        messages.append({"role": "user", "content": message})

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
# CHAT
# -----------------------------
@app.route("/chat", methods=["POST"])
def chat():

    try:

        data = request.get_json(force=True)

        msg = data.get("message", "")
        user_id = data.get("user_id", str(uuid.uuid4()))
        clinic_id = data.get("clinic_id", "default")

        if not msg:
            return jsonify({"error": "missing message"}), 400

        lead_type = classify(msg)
        lead_score = score(lead_type)
        lead_stage = stage(lead_score)

        ai_response, mode = ask_ai(msg, user_id)

        if not ai_response:
            ai_response = fallback(lead_type)
            mode = "fallback"

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

        return jsonify({
            "user_id": user_id,
            "response": ai_response,
            "lead_type": lead_type,
            "score": lead_score,
            "stage": lead_stage,
            "mode": mode,
            "next_action": "BOOK_APPOINTMENT" if lead_type == "CALIENTE" else "FOLLOW_UP"
        })

    except Exception as e:
        print("CHAT ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


# -----------------------------
# LEADS
# -----------------------------
@app.route("/leads/<clinic_id>")
def get_leads(clinic_id):

    data = (
        supabase
        .table("leads")
        .select("*")
        .eq("clinic_id", clinic_id)
        .order("created_at", desc=True)
        .execute()
    )

    return jsonify(data.data)


# -----------------------------
# METRICS
# -----------------------------
@app.route("/metrics/<clinic_id>")
def metrics(clinic_id):

    data = (
        supabase
        .table("leads")
        .select("*")
        .eq("clinic_id", clinic_id)
        .execute()
    )

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
    return render_template("dashboard.html")


@app.route("/")
def home():
    return "AI Clinic SaaS PRO 🚀"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
