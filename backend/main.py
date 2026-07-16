import json
import os
import time
from datetime import datetime
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
from flask import Flask, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()

from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

app = Flask(__name__)
CORS(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["20 per minute"]
)

DATABASE_PATH = Path(__file__).parent / "database.json"

with open(DATABASE_PATH) as f:
    database = json.load(f)

# authentication

AUTH_CODE = os.environ["AUTH_CODE"]
AUTH_DURATION_SECONDS = 5 * 60

# maps IP address -> time (epoch seconds) the authentication expires
authenticated_ips = {}
authenticated_ips_lock = Lock()

# checks whether an IP is currently authenticated, evicting it from the
# authenticated list if its window has expired
def is_authenticated(ip):
    with authenticated_ips_lock:
        expires_at = authenticated_ips.get(ip)

        if expires_at is None:
            return False

        if time.time() > expires_at:
            del authenticated_ips[ip]
            return False

        return True

# answering questions

encoding_model = SentenceTransformer("all-MiniLM-L6-v2")

embeddings = encoding_model.encode(
    database,
    normalize_embeddings=True   # we want to compare direction, not magnitude
)

# dimension of previously created embeddings
# shape is [X, Y]
# X = number of chunks
# Y = embedding dimension
# embeddings[1] gives Y, the embedding dimension
embedding_dimension = embeddings.shape[1]

# create an empty FAISS database with the embedding dimension
index = faiss.IndexFlatIP(embedding_dimension)

# add embeddings
index.add(embeddings.astype("float32"))

# define the K chunks of data that FAISS will collect
K = 10

# Minimum score to consider a database chunk relevant
SCORE_THRESHOLD = 0.5

# index retrieval function
def retrieve_info(question, k):

    # convert question into embeddings
    query_embedding = encoding_model.encode(
        [question],
        normalize_embeddings=True
    )

    # get the top k matches to the question from the database
    # distances represent how similar the chunks are
    # indices represent the which items in the database were found
    distances, indices = index.search(
        query_embedding.astype("float32"),
        k=k
    )

    return distances, indices

# a function to convert indices into context
def indices_to_context(indices):
    context = []

    for i in indices:
        context.append(database[i])

    return context

# a function to compile everything into a single prompt
def build_prompt(question, context):
    context_text = "\n".join(context)
    day_of_week = datetime.now().strftime("%A")

    prompt = (
        "Answer the question using ONLY the information below. Provide exactly one "
        "complete, elaborated answer that explains your reasoning rather than simply responding 'yes' or 'no'. "
        "Do not add extra questions, extra answers, or unrelated text beyond your one thorough answer.\n"
        "If none of the information below answers the question, only respond with the exact phrase "
        "\"I don't have that information.\" If the information below does "
        "answer the question, answer it directly and do not say that phrase.\n"
        "Whenever possible and reasonable, answer the question to the best of your ability.\n"
        "If the answer depends on the day of the week, use the fact that today is {day_of_week} in your answer, "
        "and explain any details that change based on the day.\n\n"
        f"Information:\n{context_text}\n\n"
        f"Question:\n{question}"
    )

    return prompt

# define the model
model_name = "Qwen/Qwen2.5-3B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
llm = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.float16,
    device_map="auto"
)

SYSTEM_PROMPT = (
    "You are a helpful assistant for a fitness company, answering staff and "
    "customer questions about sales, memberships, and shift/operational procedures."
)

# a function to generate a response with the model
def generate_response(prompt):
    # Qwen2.5-Instruct is trained on chat-formatted conversations, not raw text
    # completion. apply_chat_template wraps the prompt with the special tokens
    # the model was trained to recognize as "the assistant's turn" — this is
    # what lets the model know when to stop, instead of rambling on past the
    # actual answer.
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt"
    ).to(llm.device)

    # max_new_tokens controls how long the answer can be.
    output = llm.generate(
        **inputs,
        max_new_tokens=200
    )

    # output includes the input prompt tokens followed by the newly generated
    # ones. Slice those off so we only decode the model's actual answer.
    new_tokens = output[0][inputs["input_ids"].shape[-1]:]

    return tokenizer.decode(
        new_tokens,
        skip_special_tokens=True
    ).strip()

@app.route("/authenticate", methods=["GET"])
def authentication_status():
    return {"authenticated": is_authenticated(request.remote_addr)}

@app.route("/authenticate", methods=["POST"])
@limiter.limit("10 per minute")
def authenticate():
    data = request.get_json(silent=True) or {}
    code = str(data.get("code", ""))

    if not (code.isdigit() and len(code) == 6) or code != AUTH_CODE:
        return {"authenticated": False}, 401

    with authenticated_ips_lock:
        authenticated_ips[request.remote_addr] = time.time() + AUTH_DURATION_SECONDS

    return {"authenticated": True}

@app.route("/ask")
@limiter.limit("5 per minute")
def answer_question():
    if not is_authenticated(request.remote_addr):
        return "The password was bypassed, you can't send messages without authenticating first.", 401

    question = request.args.get("question")

    # have FAISS collect the top k matching data chunks to the question
    distances, indices = retrieve_info(question, K)

    # remove the outermost dimension
    # so that distances and indices become a 1d array
    distances = np.squeeze(distances)
    indices = np.squeeze(indices)

    # filter out indices based on threshold
    filtered_indices = []
    for i in range(len(distances)):
        if distances[i] >= SCORE_THRESHOLD:
            filtered_indices.append(indices[i])
    
    # if no indices met the threshold
    # the request doesn't match what is known in the database
    if len(filtered_indices) == 0:
        return "NO CONTEXT MEETS THRESHOLD"

    # compare indices with database to get actual text
    context = indices_to_context(filtered_indices)

    # use the context to collect a prompt
    prompt = build_prompt(question, context)

    # use the prompt to generate a response
    response = generate_response(prompt)

    return response

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, threaded=True)
