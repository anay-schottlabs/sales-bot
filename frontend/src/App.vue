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
    <div class="flex flex-col h-screen max-w-2xl mx-auto px-4">
        <!-- page hero -->
        <div class="shrink-0 pt-16 pb-8 text-center">
            <p class="text-5xl font-bold tracking-tight text-gray-900">{{ greeting }}</p>
        </div>

        <!-- show message history -->
        <div class="flex-1 overflow-y-auto flex flex-col gap-3 px-1">
            <div
                v-for="message in messages"
                class="flex"
                :class="message.sender == Sender.BOT ? 'justify-start' : 'justify-end'"
            >
                <div
                    class="max-w-[75%] rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed"
                    :class="message.sender == Sender.BOT ? 'bg-gray-100 text-gray-900' : 'bg-gray-900 text-white'"
                >
                    {{ message.text }}
                </div>
            </div>
        </div>

        <!-- selector for question type -->
        <div class="flex justify-center shrink-0 pt-4">
            <div class="inline-flex rounded-full border border-gray-300 overflow-hidden">
                <button
                    type="button"
                    class="px-5 py-1.5 text-sm font-medium transition-colors"
                    :class="questionType === 'SALES' ? 'bg-gray-900 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'"
                    @click="questionType = 'SALES'"
                >
                    Sales
                </button>
                <button
                    type="button"
                    class="border-l border-gray-300 px-5 py-1.5 text-sm font-medium transition-colors"
                    :class="questionType === 'SHIFT' ? 'bg-gray-900 text-white' : 'bg-white text-gray-600 hover:bg-gray-50'"
                    @click="questionType = 'SHIFT'"
                >
                    Shift
                </button>
            </div>
        </div>

        <!-- input to type messages -->
        <div class="flex justify-center pt-3 pb-12 shrink-0">
            <div class="relative w-full max-w-xl">
                <input
                    type="text"
                    class="input input-lg w-full rounded-full pr-14 text-base shadow-sm"
                    placeholder="Message..."
                    v-model="messageInput"
                    @keydown.enter="sendMessage"
                >
                <button
                    type="button"
                    class="absolute right-1.5 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-gray-900 text-white transition-colors disabled:bg-gray-200 disabled:text-gray-400"
                    :disabled="messageInput === ''"
                    @click="sendMessage"
                    aria-label="Send message"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="h-5 w-5">
                        <path d="M12 19V5" />
                        <path d="M5 12l7-7 7 7" />
                    </svg>
                </button>
            </div>
        </div>
    </div>
</template>
