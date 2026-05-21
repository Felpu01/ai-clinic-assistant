from flask import Flask, request, jsonify
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
# SUPABASE INIT
# -----------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# SYSTEM PROMPT
# -----------------------------
SYSTEM_PROMPT = """
Eres recepcionista virtual de una clínica estética, dermatológica u odontológica.
Tu objetivo es convertir consultas en turnos.
Responde breve, humana y siempre intenta agendar.
"""

# -----------------------------
# CLASSIFIER
# -----------------------------
def classify(msg):
    msg = (msg or "").lower()

    if any(x in msg for x in ["turno", "agendar", "reservar"]):
        return "CALIENTE"
    if any(x in msg for x in ["precio", "info", "consulta"]):
        return "TIBIO"
    return "FRIO"


def score(lead_type):
    return {"CALIENTE": 90, "TIBIO": 60, "FRIO": 20}[lead_type]


def stage(score):
    if score >= 80:
        return "BOOKED_READY"
    if score >= 50:
        return "INTERESTED"
    return "NEW"


# -----------------------------
# FALLBACK
# -----------------------------
def fallback(msg_type):
    if msg_type == "CALIENTE":
        return "Perfecto 👌 te agendo un turno. ¿Qué día te queda cómodo?"
    if msg_type == "TIBIO":
        return "Te explico 👌 ¿querés que te recomiende el mejor tratamiento?"
    return "Hola 👋 ¿qué te gustaría mejorar?"


# -----------------------------
# OPENAI
# -----------------------------
def ask_ai(message):
    if not client:
        return None

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message}
            ]
        )
        return res.choices[0].message.content
    except:
        return None


# -----------------------------
# CHAT ENDPOINT (SAAS READY)
# -----------------------------
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()

    msg = data.get("message", "")
    user_id = data.get("user_id", str(uuid.uuid4()))
    clinic_id = data.get("clinic_id", "default")

    lead_type = classify(msg)
    lead_score = score(lead_type)
    lead_stage = stage(lead_score)

    ai_response = ask_ai(msg)
    if not ai_response:
        ai_response = fallback(lead_type)

    # -----------------------------
    # SAVE TO SUPABASE
    # -----------------------------
    supabase.table("leads").insert({
        "id": str(uuid.uuid4()),
        "clinic_id": clinic_id,
        "user_id": user_id,
        "message": msg,
        "lead_type": lead_type,
        "score": lead_score,
        "stage": lead_stage,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }).execute()

    return jsonify({
        "user_id": user_id,
        "response": ai_response,
        "lead_type": lead_type,
        "score": lead_score,
        "stage": lead_stage,
        "next_action": "BOOK_APPOINTMENT" if lead_type == "CALIENTE" else "FOLLOW_UP"
    })


# -----------------------------
# LEADS (FROM SUPABASE)
# -----------------------------
@app.route("/leads/<clinic_id>", methods=["GET"])
def get_leads(clinic_id):
    data = supabase.table("leads").select("*").eq("clinic_id", clinic_id).execute()
    return jsonify(data.data)


# -----------------------------
@app.route("/")
def home():
    return "AI Clinic SaaS V2.1 + Supabase 🚀"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
