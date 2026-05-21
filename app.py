from flask import Flask, request, jsonify
import os
from openai import OpenAI

app = Flask(__name__)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


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


def classify(msg):
    msg = msg.lower()

    if any(x in msg for x in ["turno", "agendar", "reservar", "quiero hacerlo"]):
        return "CALIENTE"
    elif any(x in msg for x in ["precio", "info", "consulta", "tratamiento"]):
        return "TIBIO"
    else:
        return "FRIO"


def ask_ai(message):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message}
        ],
        temperature=0.7
    )

    return response.choices[0].message.content


@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    msg = data.get("message")

    if not msg:
        return jsonify({"error": "missing message"}), 400

    reply = ask_ai(msg)
    lead = classify(msg)

    return jsonify({
        "response": reply,
        "lead_type": lead,
        "next_action": "BOOK_APPOINTMENT" if lead == "CALIENTE" else "FOLLOW_UP"
    })


@app.route("/")
def home():
    return "AI Clinic Assistant running"


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
