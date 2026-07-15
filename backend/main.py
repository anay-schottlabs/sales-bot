from flask import Flask, request
from flask_cors import CORS
from enum import Enum

app = Flask(__name__)
CORS(app)

class QuestionType(Enum):
    SALES = "SALES"
    SHIFT = "SHIFT"

@app.route("/ask")
def answer_question():
    question = request.args.get("question")
    question_type = request.args.get("question_type")
    return f"Answer to '{question}' is PLACEHOLDER"
