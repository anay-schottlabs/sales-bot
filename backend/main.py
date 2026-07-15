import json
from pathlib import Path

from flask import Flask, request
from flask_cors import CORS
from enum import Enum

app = Flask(__name__)
CORS(app)

DATABASE_PATH = Path(__file__).parent / "database.json"

with open(DATABASE_PATH) as f:
    database = json.load(f)

class QuestionType(Enum):
    SALES = "SALES"
    SHIFT = "SHIFT"

@app.route("/ask")
def answer_question():
    question = request.args.get("question")
    question_type = request.args.get("question_type")

    # confirm that question type is valid
    if question_type not in [qt.value for qt in QuestionType]:
        return ""

    return f"Answer to '{question}' is PLACEHOLDER"
