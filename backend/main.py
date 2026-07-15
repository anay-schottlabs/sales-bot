from flask import Flask, request

app = Flask(__name__)

@app.route("/ask")
def answer_question():
    question = request.args.get("question")
    return f"Answer to '{question}' is PLACEHOLDER"
