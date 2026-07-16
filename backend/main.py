import json
import os
import time
from datetime import datetime
from pathlib import Path
from threading import Lock

# faiss, torch, and scikit-learn (a sentence-transformers dependency) each
# bundle their own separate copy of the OpenMP runtime (libomp.dylib) in
# their macOS pip wheels. With more than one loaded in the same process,
# OpenMP's thread-pool setup segfaults (SIGSEGV inside libomp) while the
# model's checkpoint shards are loading — confirmed by forcing a single
# OpenMP thread, which reliably avoids it. KMP_DUPLICATE_LIB_OK is kept too
# since the underlying multiple-libomp situation is real, but
# OMP_NUM_THREADS=1 is the one that actually stops the crash. Both must be
# set before any of those libraries are imported, so this comes before the
# imports below rather than living next to load_dotenv().
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import faiss
import numpy as np
import torch
from dotenv import load_dotenv
from flask import Flask, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForCausalLM

# reads .env into the process environment (e.g. AUTH_CODE below) — must run
# before anything that touches os.environ
load_dotenv()

# app setup

app = Flask(__name__)
CORS(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["20 per minute"]
)

# authentication

AUTH_CODE = os.environ["AUTH_CODE"]
AUTH_DURATION_SECONDS = 1 * 60 * 60 # 1 hour long

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

# conversation history
#
# how many past messages (the user's questions and the bot's answers,
# combined) are kept per IP and threaded into every prompt, so a follow-up
# question ("what about that one?") can refer back to what was just discussed
MAX_HISTORY_MESSAGES = 4

# maps IP address -> list of {"role": "user"/"assistant", "content": ...}
# messages for that IP, oldest first, capped at MAX_HISTORY_MESSAGES entries
conversation_history = {}
conversation_history_lock = Lock()

# appends a message to an IP's history, trimming down to the most recent
# MAX_HISTORY_MESSAGES entries
def add_to_history(ip, role, content):
    with conversation_history_lock:
        history = conversation_history.setdefault(ip, [])
        history.append({"role": role, "content": content})
        del history[:-MAX_HISTORY_MESSAGES]

# returns a snapshot of an IP's current history (empty if it has none yet)
def get_history(ip):
    with conversation_history_lock:
        return list(conversation_history.get(ip, []))

# shift schedule

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

NO_SHIFT_LABEL = "No Shift"

# each entry is the days it applies to, its start/end time ("HH:MM", 24h), and its label
SHIFTS = [
    {"label": "Morning Shift", "days": WEEKDAYS, "start": "05:30", "end": "07:30"},
    {"label": "Noon Shift", "days": WEEKDAYS, "start": "11:00", "end": "13:00"},
    {"label": "Evening Shift", "days": ["Monday", "Wednesday"], "start": "15:45", "end": "20:15"},
    {"label": "Evening Shift", "days": ["Tuesday", "Thursday"], "start": "17:00", "end": "20:15"},
    {"label": "Evening Shift", "days": ["Friday"], "start": "17:00", "end": "19:15"},
    {"label": "All Day Shift", "days": ["Saturday"], "start": "07:45", "end": "12:45"},
    {"label": "All Day Shift", "days": ["Sunday"], "start": "07:45", "end": "12:45"},
]

# figures out which shift (if any) covers the given moment, by day and time-of-day
def get_current_shift(now=None):
    # If no time is provided, use the current datetime
    now = now or datetime.now()

    # Get the day of the week as a string, e.g. "Monday"
    day_name = now.strftime("%A")
    # Get the current time as a time object (hour, minute, second)
    current_time = now.time()

    # Loop through each shift defined in SHIFTS
    for shift in SHIFTS:
        # Only consider shifts that are scheduled for today (match day name)
        if day_name not in shift["days"]:
            continue

        # Parse the start and end times from strings ("HH:MM") to time objects
        # Example: "05:30" -> datetime.strptime("05:30", "%H:%M").time()
        start = datetime.strptime(shift["start"], "%H:%M").time()
        end = datetime.strptime(shift["end"], "%H:%M").time()

        # Check if the current_time falls within the shift's start and end time, inclusive
        if start <= current_time <= end:
            # Return the label (name) of the current shift if we're within this shift's time window
            return shift["label"]

    # If no shifts cover the current time, return the NO_SHIFT_LABEL
    return NO_SHIFT_LABEL

# day of week, shift, month, and year as of `now` — computed once per request
# (in answer_question) and threaded into both retrieval and prompt
# construction, so they always agree on what "today" is
def current_time_context(now=None):
    now = now or datetime.now()
    return {
        "day_of_week": now.strftime("%A"),
        "shift": get_current_shift(now),
        "month": now.strftime("%B"),
        "year": now.strftime("%Y"),
    }

# knowledge base retrieval
#
# the database is a flat list of {category, text} entries. we embed each one
# ahead of time, then at question-time embed the question the same way and
# use FAISS to find the entries whose meaning is closest to it — this is
# what lets the bot match "when do you open" against "gym hours" without
# needing the exact same wording.

DATABASE_PATH = Path(__file__).parent / "database.json"

with open(DATABASE_PATH) as f:
    database = json.load(f)

# folding the category into the embedded text (rather than embedding database
# directly) gives the model more context to match against — e.g. a question
# about "pricing" can match on the category even if the word never appears in
# the text itself. this list only exists to be embedded; database stays the
# source of truth for what's actually returned to the caller.
embedding_texts = [
    f"Category: {item['category']}. Information: {item['text']}"
    for item in database
]

encoding_model = SentenceTransformer("all-MiniLM-L6-v2")

embeddings = encoding_model.encode(
    embedding_texts,
    normalize_embeddings=True   # we want to compare direction, not magnitude
)

# dimension of previously created embeddings
# shape is [X, Y]
# X = number of chunks
# Y = embedding dimension
# embeddings[1] gives Y, the embedding dimension
embedding_dimension = embeddings.shape[1]

# IndexFlatIP does an exact nearest-neighbor search using inner product,
# which is equivalent to cosine similarity here since every embedding
# above is normalized
index = faiss.IndexFlatIP(embedding_dimension)

# add embeddings
index.add(embeddings.astype("float32"))

# how many candidate chunks FAISS returns per question
K = 10

# how similar (cosine similarity, 0-1) a chunk must be to the question to
# be trusted as real context, rather than a coincidental near-match
SCORE_THRESHOLD = 0.5

# index retrieval function
def retrieve_info(question, k, time_context):

    # fold the current day/shift/month/year into the embedded query so
    # retrieval can surface time-relevant entries (e.g. a specific month's
    # promotion) even when the question itself doesn't mention them
    augmented_question = (
        f"{question} "
        f"(Today is {time_context['day_of_week']}, the current shift is {time_context['shift']}, "
        f"and the current month is {time_context['month']} {time_context['year']}.)"
    )

    # convert question into embeddings
    query_embedding = encoding_model.encode(
        [augmented_question],
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

# converts FAISS result indices (row numbers into `database`, which stays
# aligned with embedding_texts since both are built from the same list) back
# into the original {category, text} entries, not the embedding strings
def indices_to_context(indices):
    context = []

    for i in indices:
        context.append(database[i])

    return context

# prompt construction

# assembles the final prompt sent to the model: the retrieved knowledge-base
# context, plus today's day of week, current shift, and current month/year
# (so day/shift/promotion-relative questions can be answered), plus recent
# conversation history (so follow-up questions can refer back to what was
# just discussed), plus the rules for how to answer
def build_prompt(question, context, time_context, history):
    context_text = "\n".join(item["text"] for item in context)

    history_text = "\n".join(
        f"{'Them' if message['role'] == 'user' else 'You'}: {message['content']}"
        for message in history
    )

    history_section = (
        f"Recent conversation, oldest first — refer back to it only if the current "
        f"question depends on it (e.g. it says \"that\", \"it\", or otherwise follows "
        f"up on something just discussed); otherwise ignore it and don't mention it:\n"
        f"{history_text}\n\n"
        if history else ""
    )

    prompt = (
        "Answer the question using ONLY the information below, in a warm, friendly, "
        "conversational tone — like a helpful teammate chatting with someone, not a formal manual. "
        "Give one clear, complete answer rather than just 'yes' or 'no', but keep it tight — a sentence "
        "or two of explanation is plenty; don't pad the answer with extra analysis, restate the question, "
        "or over-elaborate beyond what's needed to actually answer it.\n"
        "End the answer once it's answered. Do not ask a follow-up question, do not offer to help further "
        "(e.g. \"let me know if you need anything else\"), and do not add extra questions, extra answers, "
        "or any other text beyond your one direct answer.\n"
        "If none of the information below answers the question, only respond with the exact phrase "
        "\"I don't have that one handy, sorry! Is there something else I can help with?\" If the information "
        "below does answer the question, answer it directly and do not say that phrase.\n"
        "Whenever possible and reasonable, answer the question to the best of your ability.\n"
        f"For context only — today is {time_context['day_of_week']}, {time_context['month']} "
        f"{time_context['year']}, and the shift currently underway is: {time_context['shift']}. Only bring "
        "up the day, shift, or month/year if the question specifically depends on one of them (for example, "
        "a shift-specific task or a time-limited monthly promotion). Do not mention today's date, the "
        "month/year, or the current shift in your answer for questions that have nothing to do with "
        "timing.\n\n"
        f"Information:\n{context_text}\n\n"
        f"{history_section}"
        f"Question:\n{question}"
    )

    return prompt

# language model

model_name = "Qwen/Qwen2.5-3B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
llm = AutoModelForCausalLM.from_pretrained(
    model_name,
    dtype=torch.float16,
    device_map="auto"
)

SYSTEM_PROMPT = (
    "You are a friendly, approachable assistant for a fitness company, chatting with staff and "
    "customers about sales, memberships, and shift/operational procedures. Sound warm and human, "
    "like a helpful teammate — not stiff or robotic."
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

# routes

# lets the frontend check, on page load/reload, whether this IP is still
# within an authenticated window — without needing to resubmit a code
@app.route("/authenticate", methods=["GET"])
def authentication_status():
    authenticated = is_authenticated(request.remote_addr)

    if not authenticated:
        return {"authenticated": False}

    return {"authenticated": True, "shifts": SHIFTS}

# verifies a submitted 6-digit code and, if correct, marks this IP
# authenticated for AUTH_DURATION_SECONDS
@app.route("/authenticate", methods=["POST"])
@limiter.limit("10 per minute")
def authenticate():
    data = request.get_json(silent=True) or {}
    code = str(data.get("code", ""))

    if not (code.isdigit() and len(code) == 6) or code != AUTH_CODE:
        return {"authenticated": False}, 401

    with authenticated_ips_lock:
        authenticated_ips[request.remote_addr] = time.time() + AUTH_DURATION_SECONDS

    return {"authenticated": True, "shifts": SHIFTS}

# answers a question: retrieves relevant knowledge-base context, filters out
# anything too dissimilar to be trustworthy, then asks the LLM to answer
# using only that context
@app.route("/ask")
@limiter.limit("5 per minute")
def answer_question():
    ip = request.remote_addr

    if not is_authenticated(ip):
        return "Looks like your session's expired. Type in your code again and I'll be right here.", 401

    question = request.args.get("question")

    # computed once so retrieval and the prompt agree on what "today" is
    time_context = current_time_context()

    # this IP's recent back-and-forth, threaded into the prompt below
    history = get_history(ip)

    # have FAISS collect the top k matching data chunks to the question
    distances, indices = retrieve_info(question, K, time_context)

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
        return "Hmm, I'm not confident I've got a good answer for that one. Could you rephrase, or ask me something else?"

    # compare indices with database to get actual text
    context = indices_to_context(filtered_indices)

    # use the context to collect a prompt
    prompt = build_prompt(question, context, time_context, history)

    # use the prompt to generate a response
    response = generate_response(prompt)

    # remember this turn so follow-up questions from the same IP can refer
    # back to it
    add_to_history(ip, "user", question)
    add_to_history(ip, "assistant", response)

    return response

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, threaded=True)
