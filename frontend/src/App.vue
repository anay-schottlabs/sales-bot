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

function sendMessage() {
    if (messageInput.value != "") {
        messages.value.push(
            new Message(
                messageInput.value,
                Sender.USER
            )
        );
        messageInput.value = "";

        // placeholder until actual message response from bot
        messages.value.push(
            new Message(
                "This is a placeholder response from the bot",
                Sender.BOT
            )
        );
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
        <div class="flex justify-center mt-8">
            <input
                type="text"
                class="input"
                placeholder="Type your question here..."
                v-model="messageInput"
                @keydown.enter="sendMessage"       
            >
        </div>
    </div>
</template>
