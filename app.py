from flask import Flask, request, jsonify
import os
from openai import OpenAI

app = Flask(__name__)

# -----------------------------
# OPENAI CLIENT (SAFE INIT)
# -----------------------------
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("WARNING: OPENAI_API_KEY is missing")

client = OpenAI(api_key=api_key)


# -----------------------------
# SYSTEM PROMPT (CLINIC SALES)
# -----------------------------
SYSTEM_PROMPT = """
Eres recepcionista virtual de una clínica estética, dermatológica u odontológica.

OBJETIVO:
Convertir consultas en turnos.

REGLAS:
- Responde amable, humana y profesional
- Nunca técnico
- Siempre intenta cerrar turno
- Lleva a: "¿Querés que te agende un turno?"
"""


# -----------------------------
# LEAD CLASSIFICATION
# -----------------------------
def classify(msg):
    if not msg:
        return "FRIO"

    msg = msg.lower()

    if any(x in msg for x in ["turno", "agendar", "reservar", "quiero hacerlo"]):
        return "CALIENTE"
    elif any(x in msg for x in ["precio", "info", "consulta", "tratamiento"]):
        return "TIBIO"
    else:
        return "FRIO"


# -----------------------------
# OPENAI CALL (SAFE)
# -----------------------------
def ask_ai(message):
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message}
            ],
            temperature=0.7
        )

        return response.choices[0].message.content

    except Exception as e:
        print("OPENAI ERROR:", str(e))
        return "Lo siento, hubo un error procesando la consulta."


# -----------------------------
# CHAT ENDPOINT
# -----------------------------
@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(force=True)

        msg = data.get("message")

        print("INCOMING MESSAGE:", msg)

        if not msg:
            return jsonify({"error": "missing message"}), 400

        reply = ask_ai(msg)
        lead = classify(msg)

        return jsonify({
            "response": reply,
            "lead_type": lead,
            "next_action": "BOOK_APPOINTMENT" if lead == "CALIENTE" else "FOLLOW_UP"
        })

    except Exception as e:
        print("CHAT ERROR:", str(e))
        return jsonify({
            "error": str(e)
        }), 500


# -----------------------------
# HEALTH CHECK
# -----------------------------
@app.route("/")
def home():
    return "AI Clinic Assistant running"


# -----------------------------
# RUN APP
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
