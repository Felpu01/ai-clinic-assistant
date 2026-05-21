from flask import Flask, request, jsonify
import os
import uuid
import time
from openai import OpenAI

app = Flask(__name__)

# -----------------------------
# OPENAI INIT SAFE
# -----------------------------
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key) if api_key else None

# -----------------------------
# CRM MEMORY (MVP DB)
# -----------------------------
LEADS = {}

# -----------------------------
# SYSTEM PROMPT
# -----------------------------
SYSTEM_PROMPT = """
Eres recepcionista virtual de una clínica estética, dermatológica u odontológica.

OBJETIVO:
Convertir consultas en turnos.

REGLAS:
- Responde breve, humana y profesional
- No técnico
- Siempre intenta cerrar con turno
"""


# -----------------------------
# LEAD CLASSIFICATION
# -----------------------------
def classify(msg):
    msg = (msg or "").lower()

    if any(x in msg for x in ["turno", "agendar", "reservar"]):
        return "CALIENTE"
    elif any(x in msg for x in ["precio", "info", "consulta", "tratamiento"]):
        return "TIBIO"
    return "FRIO"


# -----------------------------
# FALLBACK (SIN OPENAI)
# -----------------------------
def fallback_ai(msg, lead_type):
    if lead_type == "CALIENTE":
        return "Perfecto 👌 te puedo agendar un turno. ¿Qué día te queda cómodo?"
    if lead_type == "TIBIO":
        return "Te explico 👌 ¿querés que te recomiende el mejor tratamiento para vos?"
    return "Hola 👋 ¿qué te gustaría mejorar o consultar?"


# -----------------------------
# OPENAI CALL
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

        print("INCOMING MESSAGE:", msg)

        if not msg:
            return jsonify({"error": "missing message"}), 400

        lead_type = classify(msg)

        # -------------------------
        # CRM STORAGE
        # -------------------------
        if user_id not in LEADS:
            LEADS[user_id] = {
                "id": user_id,
                "created_at": time.time(),
                "messages": [],
                "stage": lead_type
            }

        LEADS[user_id]["messages"].append({
            "role": "user",
            "message": msg,
            "time": time.time()
        })

        LEADS[user_id]["stage"] = lead_type

        # -------------------------
        # AI RESPONSE
        # -------------------------
        ai_response = ask_ai(msg)

        if not ai_response:
            ai_response = fallback_ai(msg, lead_type)

        return jsonify({
            "user_id": user_id,
            "response": ai_response,
            "lead_type": lead_type,
            "next_action": "BOOK_APPOINTMENT" if lead_type == "CALIENTE" else "FOLLOW_UP"
        })

    except Exception as e:
        print("CHAT ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


# -----------------------------
# CRM ENDPOINTS
# -----------------------------
@app.route("/leads", methods=["GET"])
def get_leads():
    return jsonify(LEADS)


@app.route("/lead/<user_id>", methods=["GET"])
def get_lead(user_id):
    return jsonify(LEADS.get(user_id, {"error": "not found"}))


# -----------------------------
# HEALTH
# -----------------------------
@app.route("/")
def home():
    return "AI Clinic CRM V2 running 🚀"


# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
