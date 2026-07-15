<script setup>
import { ref, computed } from 'vue';

const Sender = Object.freeze({
    USER: "user",
    BOT: "bot"
});

class Message {
    constructor(text, sender) {
        this.text = text;
        this.sender = sender;
    }
}

const messages = ref([
    new Message(
        "How can I help?",
        Sender.BOT
    )
]);

const messageInput = ref("");
const questionType = ref("SALES");

const greeting = computed(() => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good morning.";
    if (hour < 18) return "Good afternoon.";
    return "Good evening.";
});

const REQUEST_URL = "http://127.0.0.1:5000/ask?";
const QUESTION_PARAM = "question=";
const QUESTION_TYPE_PARAM = "question_type=";

async function sendMessage() {
    if (messageInput.value != "") {
        messages.value.push(
            new Message(
                messageInput.value,
                Sender.USER
            )
        );

        const response = await fetch(
            REQUEST_URL +
            QUESTION_PARAM + encodeURIComponent(messageInput.value) +
            "&" + QUESTION_TYPE_PARAM + encodeURIComponent(questionType.value)
        );
        const answerText = await response.text();
        messages.value.push(
            new Message(
                answerText,
                Sender.BOT
            )
        );

        messageInput.value = "";
    }
}
</script>

<template>
    <div class="flex flex-col h-screen max-w-3xl mx-auto px-4">
        <!-- page hero -->
        <p class="text-4xl font-semibold text-center py-6 shrink-0">{{ greeting }}</p>

        <!-- show message history -->
        <div class="flex-1 overflow-y-auto flex flex-col gap-3 px-1">
            <div v-for="message in messages">
                <div v-if="message.sender == Sender.BOT" class="chat chat-start">
                    <div class="chat-bubble">{{ message.text }}</div>
                </div>
                <div v-if="message.sender == Sender.USER" class="chat chat-end">
                    <div class="chat-bubble">{{ message.text }}</div>
                </div>
            </div>
        </div>

        <!-- selector for question type -->
        <div class="flex justify-center shrink-0">
            <div class="join">
                <button
                    type="button"
                    class="btn join-item"
                    :class="questionType === 'SALES' ? 'btn-primary' : 'btn-outline'"
                    @click="questionType = 'SALES'"
                >
                    Sales
                </button>
                <button
                    type="button"
                    class="btn join-item"
                    :class="questionType === 'SHIFT' ? 'btn-primary' : 'btn-outline'"
                    @click="questionType = 'SHIFT'"
                >
                    Shift
                </button>
            </div>
        </div>

        <!-- input to type messages -->
        <div class="flex justify-center pt-3 pb-12 shrink-0">
            <input
                type="text"
                class="input input-lg w-full max-w-xl text-lg shadow-sm"
                placeholder="Type your question here..."
                v-model="messageInput"
                @keydown.enter="sendMessage"
            >
        </div>
    </div>
</template>
