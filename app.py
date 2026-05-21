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

OBJETIVO:
Convertir consultas en turnos.

REGLAS:
- Responde breve
- Profesional
- Humana
- Siempre intenta cerrar turno
"""

# -----------------------------
# CLASSIFIER (MEJORADO)
# -----------------------------
def classify(msg):
    msg = (msg or "").lower()

    # 🔥 LEAD CALIENTE
    if any(x in msg for x in [
        "turno",
        "agendar",
        "reservar",
        "quiero hacerlo",
        "cuando puedo",
        "disponibilidad"
    ]):
        return "CALIENTE"

    # 🟡 LEAD TIBIO
    if any(x in msg for x in [
        "precio",
        "cuánto",
        "cuesta",
        "valor",
        "sale",
        "info",
        "consulta",
        "tratamiento",
        "limpieza",
        "facial"
    ]):
        return "TIBIO"

    # 🔵 LEAD FRÍO
    return "FRIO"


# -----------------------------
# SCORE SYSTEM
# -----------------------------
def score(lead_type):
    return {
        "CALIENTE": 90,
        "TIBIO": 60,
        "FRIO": 20
    }[lead_type]


# -----------------------------
# PIPELINE STAGE
# -----------------------------
def stage(score):
    if score >= 80:
        return "BOOKED_READY"

    if score >= 50:
        return "INTERESTED"

    return "NEW"


# -----------------------------
# FALLBACK AI
# -----------------------------
def fallback(msg_type):
    if msg_type == "CALIENTE":
        return "Perfecto 👌 te puedo agendar un turno. ¿Qué día te queda cómodo?"

    if msg_type == "TIBIO":
        return "Te explico 👌 ¿querés que te recomiende el mejor tratamiento para vos?"

    return "Hola 👋 ¿qué te gustaría mejorar o consultar?"


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
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": message
                }
            ],
            temperature=0.7
        )

        return res.choices[0].message.content

    except Exception as e:
        print("OPENAI ERROR:", str(e))
        return None


# -----------------------------
# CHAT ENDPOINT
# -----------------------------
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(force=True)

        msg = data.get("message", "")
        user_id = data.get("user_id", str(uuid.uuid4()))
        clinic_id = data.get("clinic_id", "default")

        if not msg:
            return jsonify({
                "error": "missing message"
            }), 400

        print("INCOMING MESSAGE:", msg)

        # -----------------------------
        # LEAD ANALYSIS
        # -----------------------------
        lead_type = classify(msg)
        lead_score = score(lead_type)
        lead_stage = stage(lead_score)

        # -----------------------------
        # AI RESPONSE
        # -----------------------------
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

        # -----------------------------
        # RESPONSE
        # -----------------------------
        return jsonify({
            "user_id": user_id,
            "response": ai_response,
            "lead_type": lead_type,
            "score": lead_score,
            "stage": lead_stage,
            "next_action": (
                "BOOK_APPOINTMENT"
                if lead_type == "CALIENTE"
                else "FOLLOW_UP"
            )
        })

    except Exception as e:
        print("CHAT ERROR:", str(e))

        return jsonify({
            "error": str(e)
        }), 500


# -----------------------------
# GET LEADS
# -----------------------------
@app.route("/leads/<clinic_id>", methods=["GET"])
def get_leads(clinic_id):
    try:
        data = (
            supabase
            .table("leads")
            .select("*")
            .eq("clinic_id", clinic_id)
            .execute()
        )

        return jsonify(data.data)

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


# -----------------------------
# METRICS
# -----------------------------
@app.route("/metrics/<clinic_id>", methods=["GET"])
def metrics(clinic_id):
    try:
        data = (
            supabase
            .table("leads")
            .select("*")
            .eq("clinic_id", clinic_id)
            .execute()
        )

        leads = data.data

        total = len(leads)
        hot = len([x for x in leads if x["score"] >= 80])
        warm = len([x for x in leads if 50 <= x["score"] < 80])
        cold = len([x for x in leads if x["score"] < 50])

        return jsonify({
            "total_leads": total,
            "hot_leads": hot,
            "warm_leads": warm,
            "cold_leads": cold
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


# -----------------------------
# HEALTH CHECK
# -----------------------------
@app.route("/")
def home():
    return "AI Clinic SaaS V2.1 + Supabase 🚀"


# -----------------------------
# RUN APP
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
