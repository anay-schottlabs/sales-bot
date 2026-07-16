<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue';

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
        "Hey there! What can I help you with today?",
        Sender.BOT
    )
]);

const messageInput = ref("");
const isWaitingForResponse = ref(false);

const messagesContainer = ref(null);

const isAuthenticated = ref(false);
const isAuthenticating = ref(false);
const isCheckingSession = ref(true);
const otpCode = ref("");
const authError = ref("");
const shifts = ref([]);

const AUTHENTICATE_URL = "http://127.0.0.1:5050/authenticate";

onMounted(async () => {
    try {
        const response = await fetch(AUTHENTICATE_URL);
        const result = await response.json();
        isAuthenticated.value = response.ok && result.authenticated;

        if (isAuthenticated.value) {
            shifts.value = result.shifts ?? [];
        }
    } catch {
        isAuthenticated.value = false;
    } finally {
        isCheckingSession.value = false;
    }
});

function handleOtpInput(event) {
    const digitsOnly = event.target.value.replace(/\D/g, "").slice(0, 6);
    otpCode.value = digitsOnly;
    event.target.value = digitsOnly;
}

watch(otpCode, async (code) => {
    if (code.length === 6 && !isAuthenticating.value) {
        isAuthenticating.value = true;
        authError.value = "";

        try {
            const response = await fetch(AUTHENTICATE_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ code })
            });

            const result = await response.json();

            if (response.ok && result.authenticated) {
                isAuthenticated.value = true;
                shifts.value = result.shifts ?? [];
                otpCode.value = "";
            } else {
                authError.value = "Incorrect code. Try again.";
                otpCode.value = "";
            }
        } catch {
            authError.value = "Couldn't reach the server. Try again.";
            otpCode.value = "";
        } finally {
            isAuthenticating.value = false;
        }
    }
});

watch(
    () => [messages.value.length, isWaitingForResponse.value],
    async () => {
        await nextTick();
        if (messagesContainer.value) {
            messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
        }
    }
);

const timeOfDay = computed(() => {
    const hour = new Date().getHours();
    if (hour < 12) return "morning";
    if (hour < 18) return "afternoon";
    return "evening";
});

const greeting = computed(() => {
    if (timeOfDay.value === "morning") return "Good morning.";
    if (timeOfDay.value === "afternoon") return "Good afternoon.";
    return "Good evening.";
});

// mirrors get_current_shift() in main.py: matches today's day name and
// time-of-day against the shift schedule fetched from /authenticate
const currentDayAndShift = computed(() => {
    const now = new Date();
    const dayName = now.toLocaleDateString("en-US", { weekday: "long" });
    const currentMinutes = now.getHours() * 60 + now.getMinutes();

    const toMinutes = (hhmm) => {
        const [hours, minutes] = hhmm.split(":").map(Number);
        return hours * 60 + minutes;
    };

    const matchingShift = shifts.value.find((shift) => (
        shift.days.includes(dayName) &&
        currentMinutes >= toMinutes(shift.start) &&
        currentMinutes <= toMinutes(shift.end)
    ));

    return matchingShift
        ? `It's ${dayName}, and the ${matchingShift.label} is underway.`
        : `It's ${dayName} — no shift right now.`;
});

const REQUEST_URL = "http://127.0.0.1:5050/ask?question=";

async function sendMessage() {
    if (messageInput.value != "" && !isWaitingForResponse.value) {
        const question = messageInput.value;
        messages.value.push(
            new Message(
                question,
                Sender.USER
            )
        );
        messageInput.value = "";
        isWaitingForResponse.value = true;

        try {
            const response = await fetch(
                REQUEST_URL + encodeURIComponent(question)
            );
       

            if (response.status === 401) {
                isAuthenticated.value = false;
                authError.value = "Your session expired. Verify again to continue.";
                return;
            }

            const answerText = await response.text();
            messages.value.push(
                new Message(
                    answerText,
                    Sender.BOT
                )
            );
        } finally {
            isWaitingForResponse.value = false;
        }
    }
}
</script>

<template>
    <!-- checking for an already-authenticated session before deciding what to show -->
    <div v-if="isCheckingSession" class="flex h-screen items-center justify-center">
        <div class="flex items-center gap-1.5 rounded-2xl bg-base-200/70 backdrop-blur-md px-4 py-3">
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:0ms]"></span>
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:150ms]"></span>
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:300ms]"></span>
        </div>
    </div>

    <!-- OTP gate: shown until the six-digit code is verified -->
    <div v-else-if="!isAuthenticated" class="flex flex-col h-screen max-w-2xl mx-auto px-4 items-center justify-center gap-6 text-center">
        <div>
            <p class="text-4xl font-bold tracking-tight text-base-content">Verify it's you.</p>
            <p class="mt-2 text-base text-base-content/60">Enter the 6-digit code to continue.</p>
        </div>

        <label class="otp otp-lg" :class="authError ? 'otp-error' : ''">
            <span></span>
            <span></span>
            <span></span>
            <span></span>
            <span></span>
            <span></span>
            <input
                type="text"
                autocomplete="one-time-code"
                inputmode="numeric"
                maxlength="6"
                pattern="[0-9]{6}"
                :value="otpCode"
                :disabled="isAuthenticating"
                autofocus
                required
                @input="handleOtpInput"
            >
        </label>

        <div v-if="isAuthenticating" class="flex items-center gap-1.5 rounded-2xl bg-base-200/70 backdrop-blur-md px-4 py-3">
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:0ms]"></span>
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:150ms]"></span>
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:300ms]"></span>
        </div>
        <p v-else-if="authError" class="text-sm text-error">{{ authError }}</p>
    </div>

    <div v-else class="relative h-screen">
        <!-- single scroll region: header and messages scroll together, so history passes beneath the glass header -->
        <div ref="messagesContainer" class="absolute inset-0 overflow-y-auto">
            <!-- page hero, glassy and pinned to the top of the scroll region — the glass spans the full screen width -->
            <div class="glass-fade-b sticky top-0 z-10 bg-gradient-to-b from-base-100 via-base-100/85 to-transparent">
                <div class="max-w-2xl mx-auto px-4 pt-16 pb-8 text-center">
                    <div class="inline-block rounded-3xl border border-base-content/10 bg-base-200/50 backdrop-blur-xl px-8 py-5 shadow-lg shadow-black/20">
                        <!-- TEMP: all three side by side with no cycling logic, just to compare them -->
                        <div class="flex items-center justify-center gap-4">
                            <!-- sunrise: same full circle as the afternoon sun, but with dots instead of capsule rays -->
                            <svg viewBox="0 0 24 24" fill="currentColor" class="h-11 w-11 shrink-0 text-base-content">
                                <circle cx="12" cy="12" r="5" />
                                <circle cx="12" cy="2.1" r="1" />
                                <circle cx="12" cy="2.1" r="1" transform="rotate(45 12 12)" />
                                <circle cx="12" cy="2.1" r="1" transform="rotate(90 12 12)" />
                                <circle cx="12" cy="2.1" r="1" transform="rotate(135 12 12)" />
                                <circle cx="12" cy="2.1" r="1" transform="rotate(180 12 12)" />
                                <circle cx="12" cy="2.1" r="1" transform="rotate(225 12 12)" />
                                <circle cx="12" cy="2.1" r="1" transform="rotate(270 12 12)" />
                                <circle cx="12" cy="2.1" r="1" transform="rotate(315 12 12)" />
                            </svg>

                            <!-- full sun: filled circle + the same capsule rays, rotated around the sun center -->
                            <svg viewBox="0 0 24 24" fill="currentColor" class="h-11 w-11 shrink-0 text-base-content">
                                <circle cx="12" cy="12" r="5" />
                                <rect x="11" y="0.5" width="2" height="4.5" rx="1" />
                                <rect x="11" y="0.5" width="2" height="4.5" rx="1" transform="rotate(45 12 12)" />
                                <rect x="11" y="0.5" width="2" height="4.5" rx="1" transform="rotate(90 12 12)" />
                                <rect x="11" y="0.5" width="2" height="4.5" rx="1" transform="rotate(135 12 12)" />
                                <rect x="11" y="0.5" width="2" height="4.5" rx="1" transform="rotate(180 12 12)" />
                                <rect x="11" y="0.5" width="2" height="4.5" rx="1" transform="rotate(225 12 12)" />
                                <rect x="11" y="0.5" width="2" height="4.5" rx="1" transform="rotate(270 12 12)" />
                                <rect x="11" y="0.5" width="2" height="4.5" rx="1" transform="rotate(315 12 12)" />
                            </svg>

                            <!-- crescent moon -->
                            <svg viewBox="0 0 24 24" class="h-11 w-11 shrink-0 text-base-content">
                                <mask id="moon-mask">
                                    <rect x="0" y="0" width="24" height="24" fill="white" />
                                    <circle cx="15" cy="9" r="7" fill="black" />
                                </mask>
                                <circle cx="12" cy="12" r="9" fill="currentColor" mask="url(#moon-mask)" />
                            </svg>
                        </div>

                        <p class="mt-3 text-5xl font-bold tracking-tight text-base-content">{{ greeting }}</p>
                        <p class="mt-2 text-sm text-base-content/60">{{ currentDayAndShift }}</p>
                    </div>
                </div>
            </div>

            <!-- message history -->
            <div class="max-w-2xl mx-auto flex flex-col gap-3 px-5 pb-32">
                <div
                    v-for="message in messages"
                    class="flex"
                    :class="message.sender == Sender.BOT ? 'justify-start' : 'justify-end'"
                >
                    <div
                        class="max-w-[75%] rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed backdrop-blur-md"
                        :class="message.sender == Sender.BOT ? 'bg-base-200/70 text-base-content' : 'bg-neutral/85 text-neutral-content'"
                    >
                        {{ message.text }}
                    </div>
                </div>

                <div v-if="isWaitingForResponse" class="flex justify-start">
                    <div class="flex items-center gap-1.5 rounded-2xl bg-base-200/70 backdrop-blur-md px-4 py-3">
                        <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:0ms]"></span>
                        <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:150ms]"></span>
                        <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:300ms]"></span>
                    </div>
                </div>
            </div>
        </div>

        <!-- input to type messages, glassy and pinned to the bottom so history blurs beneath it too — full screen width -->
        <div class="glass-fade-t absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-base-100 via-base-100/85 to-transparent">
            <div class="max-w-2xl mx-auto flex justify-center px-4 pt-10 pb-12">
                <div class="relative w-full">
                    <input
                        type="text"
                        class="input input-lg w-full rounded-full border border-base-content/10 bg-base-200/60 backdrop-blur-md pr-14 text-base shadow-sm focus:outline-none"
                        placeholder="Message..."
                        v-model="messageInput"
                        @keydown.enter="sendMessage"
                    >
                    <button
                        type="button"
                        class="absolute right-1 top-1/2 flex h-10 w-10 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full bg-neutral/90 backdrop-blur-sm text-neutral-content transition-colors disabled:cursor-default disabled:bg-base-300/70 disabled:text-[oklch(58%_0.012_250)]"
                        :disabled="messageInput === '' || isWaitingForResponse"
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
    </div>
</template>
