import json
from pathlib import Path

from flask import Flask, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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
K = 3

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

    prompt = (
        "You are a helpful sales assistant for a fitness company.\n"
        "Answer the user's question using ONLY the information provided below.\n"
        "If the answer is not in the information provided, say: \"I don't have that information.\"\n\n"
        f"Information:\n{context_text}\n\n"
        f"Question:\n{question}\n\n"
        "Answer:"
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

# a function to generate a response with the model
def generate_response(prompt):
    # Convert the text prompt into tokens (numbers) that the model understands.
    # return_tensors="pt" means return PyTorch tensors instead of normal Python lists.
    inputs = tokenizer(
        prompt,
        return_tensors="pt"
    )

    # Move the input tensors to the same device as the model.
    # If the model is on GPU, the inputs must also be on GPU.
    inputs = inputs.to(llm.device)

    # Generate a response from the model.
    #
    # **inputs is dictionary unpacking.
    # It takes:
    # {
    #     "input_ids": ...,
    #     "attention_mask": ...
    # }
    #
    # and converts it into:
    # generate(
    #     input_ids=...,
    #     attention_mask=...
    # )
    #
    # max_new_tokens controls how long the answer can be.
    output = llm.generate(
        **inputs,
        max_new_tokens=200
    )

    # output is a tensor containing token IDs.
    #
    # Example:
    # output = [
    #     [15496, 995, 318, 1234, 5678]
    # ]
    #
    # The first [] represents the batch.
    # Since we only asked one question, we take the first result:
    # output[0]
    #
    # Then decode converts token IDs back into readable text.
    answer = tokenizer.decode(
        output[0],
        skip_special_tokens=True
    )

    # clean up the response
    # without cleanup, the response would include the entire prompt with the answer
    # this removes the prompt so that only the answer is included
    prompt_len = len(prompt) + 1
    return answer[prompt_len:]

@app.route("/ask")
@limiter.limit("5 per minute")
def answer_question():
    question = request.args.get("question")

    # have FAISS collect the top k matching data chunks to the question
    distances, indices = retrieve_info(question, K)

    # remove the outermost dimension
    # so that distances and indices become a 1d array
    distances = np.squeeze(distances)
    indices = np.squeeze(indices)

    # compare indices with database to get actual text
    context = indices_to_context(indices)

    # use the context to collect a prompt
    prompt = build_prompt(question, context)

    # use the prompt to generate a response
    response = generate_response(prompt)

    return response
