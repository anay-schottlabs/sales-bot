<script setup>
import { ref } from 'vue';

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

const messages = ref([]);

const messageInput = ref("");
const questionType = ref("SALES");

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
    <div class="py-10 px-50">
        <!-- page hero -->
        <p class="text-7xl text-center">How can I help?</p>
    
        <!-- show message history -->
        <div v-for="message in messages">
            <div v-if="message.sender == Sender.BOT" class="chat chat-start">
                <div class="chat-bubble">{{ message.text }}</div>
            </div>
            <div v-if="message.sender == Sender.USER" class="chat chat-end">
                <div class="chat-bubble">{{ message.text }}</div>
            </div>
        </div>
    
        <!-- input to type messages -->
        <div class="flex justify-center mt-8 gap-2">
            <input
                type="text"
                class="input"
                placeholder="Type your question here..."
                v-model="messageInput"
                @keydown.enter="sendMessage"
            >
            <select class="select" v-model="questionType">
                <option value="SALES">Sales</option>
                <option value="SHIFT">Shift</option>
            </select>
        </div>
    </div>
</template>
