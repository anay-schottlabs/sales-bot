from flask import Flask, request
from enum import Enum, auto

app = Flask(__name__)

class QuestionType(Enum):
    SALES = auto()
    SHIFT = auto()

@app.route("/ask")
def answer_question():
    question = request.args.get("question")
    question_type = request.args.get("question_type")
    return f"Answer to '{question}' is PLACEHOLDER"
