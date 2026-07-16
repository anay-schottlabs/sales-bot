<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue';

const Sender = Object.freeze({
    USER: "user",
    BOT: "bot"
});

// incrementing id rather than array index, so TransitionGroup's :key stays
// stable even if the list is ever manipulated beyond simple appends
let nextMessageId = 0;

class Message {
    constructor(text, sender) {
        this.id = nextMessageId++;
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

// the scrollable message-list element; watched below to auto-scroll on new messages
const messagesContainer = ref(null);

// drives the hero card condensing down to just its icon once the user has
// scrolled past it, and expanding back out on hover so it's still glanceable
const isScrolled = ref(false);
const isHeroHovered = ref(false);
const isHeroCondensed = computed(() => isScrolled.value && !isHeroHovered.value);

// hysteresis band, not a single threshold — condense only once scrolled past
// the higher value, but don't expand back out until scrolled back above the
// lower one. with a single threshold, slow scrolling that lingers right
// around it flips isScrolled on every scroll event, replaying the condense
// animation over and over instead of settling
const HERO_CONDENSE_SCROLL_THRESHOLD = 48;
const HERO_EXPAND_SCROLL_THRESHOLD = 16;

// timestamp of the last genuine @mousemove over the hero — not reactive on
// purpose, this is only ever read inside handleMessagesScroll
let lastHeroMouseMoveAt = -Infinity;
const HERO_HOVER_STALE_AFTER_MS = 80;

function handleHeroMouseMove() {
    lastHeroMouseMoveAt = performance.now();
    isHeroHovered.value = true;
}

function handleHeroMouseLeave() {
    isHeroHovered.value = false;
}

function handleMessagesScroll() {
    if (!messagesContainer.value) return;

    // the expanded card's hitbox is large (most of the top of the screen),
    // so it's common for the cursor to already be resting inside it from
    // unrelated earlier activity, well before the user starts scrolling. If
    // that stale hover were left alone, isHeroCondensed could never become
    // true — the card can't shrink out from under a hover that's blocking
    // it, so the mouseleave that would normally clear that hover never
    // fires either, deadlocking it open regardless of how far the user
    // scrolls. Scrolling should win over a hover the user isn't actively
    // maintaining, so treat any hover more than HERO_HOVER_STALE_AFTER_MS
    // old as stale and drop it on every scroll event.
    if (performance.now() - lastHeroMouseMoveAt > HERO_HOVER_STALE_AFTER_MS) {
        isHeroHovered.value = false;
    }

    const scrollTop = messagesContainer.value.scrollTop;

    if (scrollTop > HERO_CONDENSE_SCROLL_THRESHOLD) {
        isScrolled.value = true;
    } else if (scrollTop < HERO_EXPAND_SCROLL_THRESHOLD) {
        isScrolled.value = false;
    }
    // else: within the band between the two thresholds, leave isScrolled as-is
}

// auth/session state
const isAuthenticated = ref(false);
const isAuthenticating = ref(false);
const isCheckingSession = ref(true); // true only during the initial onMounted check below
const otpCode = ref("");
const authError = ref("");
const shifts = ref([]); // the shift schedule, sent by the backend once authenticated

const AUTHENTICATE_URL = "http://127.0.0.1:5050/authenticate";

// on load, ask the backend whether this IP is still within an authenticated
// window (see is_authenticated() in main.py) so a page reload doesn't force
// the user through the OTP gate again if their session hasn't expired
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

// the OTP <input> is bound via :value/@input (not v-model) specifically so
// every keystroke can be sanitized here — strips anything non-numeric and
// caps the length, so otpCode can never end up holding a bad value
function handleOtpInput(event) {
    const digitsOnly = event.target.value.replace(/\D/g, "").slice(0, 6);
    otpCode.value = digitsOnly;
    event.target.value = digitsOnly;
}

// auto-submits as soon as all 6 digits are entered, no separate "verify" button
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

// keeps the view pinned to the latest message — fires on a new message AND
// on the loading indicator toggling, since that also shifts scroll height.
// nextTick is needed because the DOM hasn't re-rendered yet when this runs
watch(
    () => [messages.value.length, isWaitingForResponse.value],
    async () => {
        await nextTick();
        if (messagesContainer.value) {
            messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
        }
    }
);

// single source of truth for the hour thresholds, so the greeting text and
// the icon shown in the template (v-if on timeOfDay) can never disagree
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

            // the backend's auth window (AUTH_DURATION_SECONDS in main.py) can
            // lapse mid-conversation; bounce back to the OTP gate instead of
            // showing the denial text as if it were a real answer
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
    <!-- crossfades between the checking/OTP-gate/chat screens instead of popping straight across -->
    <Transition name="screen" mode="out-in">
    <!-- checking for an already-authenticated session before deciding what to show -->
    <div v-if="isCheckingSession" key="checking" class="flex h-screen items-center justify-center">
        <div class="flex items-center gap-1.5 rounded-2xl bg-base-200/70 backdrop-blur-md px-4 py-3">
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:0ms]"></span>
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:150ms]"></span>
            <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:300ms]"></span>
        </div>
    </div>

    <!-- OTP gate: shown until the six-digit code is verified -->
    <div v-else-if="!isAuthenticated" key="otp-gate" class="flex flex-col h-screen max-w-2xl mx-auto px-4 items-center justify-center gap-6 text-center">
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
                type="password"
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

    <div v-else key="chat" class="relative h-screen">
        <!-- single scroll region: header and messages scroll together, so history passes beneath the glass header.
             overflow-anchor:none disables the browser's scroll anchoring for this scroller: without it, the
             browser "helpfully" adjusts scrollTop to compensate whenever the sticky header above resizes (as it
             does when the hero card condenses/expands), to keep visible content from jumping. That compensation
             itself crosses the condense/expand thresholds, re-triggering the resize, triggering another
             compensation, forever — this is what the reported glitchy/rapid toggling on a slow scroll actually
             was, not simple threshold jitter -->
        <div
            ref="messagesContainer"
            class="absolute inset-0 overflow-y-auto [overflow-anchor:none]"
            @scroll="handleMessagesScroll"
        >
            <!-- page hero, glassy and pinned to the top of the scroll region — the glass spans the full screen width.
                 condenses down to just the icon once scrolled past, expands back on hover or scrolling back to top -->
            <div class="glass-fade-b sticky top-0 z-10 bg-gradient-to-b from-base-100 via-base-100/85 to-transparent">
                <!-- hover is bound here rather than on the pill itself — this div's top edge is pinned by the
                     sticky ancestor and only its bottom edge moves as padding grows, so a stationary pointer near
                     the top of the condensed icon never ends up outside the region as it expands. binding hover to
                     the pill instead caused a feedback loop: the pill shifts down as its ancestor's padding-top
                     grows, pushing it out from under a fixed pointer, which un-hovers it, which shrinks it back
                     under the pointer, which re-hovers it — an infinite expand/contract flicker.

                     setting hover true uses @mousemove, not @mouseenter: mouseenter (like :hover) is a hit-test
                     result that gets recomputed — and re-fires — on ANY layout change, including this element's own
                     geometry shifting under a pointer that never actually moved. since the user's cursor commonly
                     rests somewhere near the top of the screen, scrolling alone (which resizes this element as the
                     card condenses) could spuriously fire mouseenter and force a re-expand mid-scroll, which grows
                     the header and shoves the message content back down — exactly the "scrolling down drags me
                     back up" report. mousemove only ever fires on genuine pointer movement, never from layout
                     changes, so it can't be triggered by the resize itself. mouseleave stays as-is: losing hover
                     when the shrinking card moves out from under a stationary pointer is the correct direction.

                     that alone still leaves a deadlock though: the expanded card's hitbox covers most of the top
                     of the screen, so the cursor is often already resting inside it from unrelated earlier
                     activity before the user starts scrolling at all — a real mousemove that legitimately set
                     isHeroHovered=true. Since the card can't shrink while hovered, it never gets the chance to
                     move out from under that stationary cursor, so mouseleave never fires either — stuck expanded
                     no matter how far you scroll. handleMessagesScroll breaks this by treating any hover older
                     than HERO_HOVER_STALE_AFTER_MS as stale and dropping it on every scroll event, so scrolling
                     always wins over a hover the user isn't actively maintaining. -->
                <div
                    class="max-w-2xl mx-auto px-4 text-center transition-[padding] duration-300 ease-out"
                    :class="isHeroCondensed ? 'pt-4 pb-3' : 'pt-16 pb-8'"
                    @mousemove="handleHeroMouseMove"
                    @mouseleave="handleHeroMouseLeave"
                >
                    <div
                        class="inline-block rounded-3xl border border-base-content/10 bg-base-200/50 backdrop-blur-xl shadow-lg shadow-black/20 transition-[padding] duration-300 ease-out"
                        :class="isHeroCondensed ? 'px-3 py-2.5' : 'px-8 py-5'"
                    >
                        <div class="flex items-center justify-center">
                            <!-- sunrise: full circle with dots instead of capsule rays -->
                            <svg
                                v-if="timeOfDay === 'morning'"
                                viewBox="0 0 24 24" fill="currentColor"
                                class="shrink-0 text-base-content transition-[height,width] duration-300 ease-out"
                                :class="isHeroCondensed ? 'h-6 w-6' : 'h-11 w-11'"
                            >
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

                            <!-- full sun: filled circle + capsule rays, rotated around the sun center -->
                            <svg
                                v-else-if="timeOfDay === 'afternoon'"
                                viewBox="0 0 24 24" fill="currentColor"
                                class="shrink-0 text-base-content transition-[height,width] duration-300 ease-out"
                                :class="isHeroCondensed ? 'h-6 w-6' : 'h-11 w-11'"
                            >
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

                            <!-- crescent moon: cusp tips rounded via blur+alpha-threshold (masks don't have "corners" to round directly) -->
                            <svg
                                v-else viewBox="0 0 24 24"
                                class="shrink-0 text-base-content transition-[height,width] duration-300 ease-out"
                                :class="isHeroCondensed ? 'h-6 w-6' : 'h-11 w-11'"
                            >
                                <filter id="moon-round" x="-30%" y="-30%" width="160%" height="160%">
                                    <feGaussianBlur in="SourceGraphic" stdDeviation="0.47" result="blur" />
                                    <feColorMatrix in="blur" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 22 -10" />
                                </filter>
                                <g filter="url(#moon-round)">
                                    <mask id="moon-mask">
                                        <rect x="0" y="0" width="24" height="24" fill="white" />
                                        <circle cx="15" cy="9" r="7" fill="black" />
                                    </mask>
                                    <circle cx="12" cy="12" r="9" fill="currentColor" mask="url(#moon-mask)" />
                                </g>
                            </svg>
                        </div>

                        <!-- collapses via max-height + max-width + opacity rather than v-if, so it animates smoothly
                             instead of popping. max-width has to collapse too, not just max-height — otherwise this
                             div still reserves its full intrinsic text width (just invisible), which keeps the
                             inline-block card pill-wide instead of shrinking down to the icon. the expanded cap is a
                             fixed px value (comfortably wider than the longest greeting) rather than max-w-full —
                             percentage max-width inside a shrink-to-fit inline-block is circular and silently
                             resolves too small, clipping the text -->
                        <div
                            class="overflow-hidden whitespace-nowrap transition-[max-height,max-width,opacity,margin-top] duration-300 ease-out"
                            :class="isHeroCondensed ? 'mt-0 max-h-0 max-w-0 opacity-0' : 'mt-3 max-h-40 max-w-[32rem] opacity-100'"
                        >
                            <p class="text-5xl font-bold tracking-tight text-base-content">{{ greeting }}</p>
                            <p class="mt-2 text-sm text-base-content/60">{{ currentDayAndShift }}</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- message history -->
            <TransitionGroup
                tag="div"
                name="message"
                class="max-w-2xl mx-auto flex flex-col gap-3 px-5 pb-32"
            >
                <div
                    v-for="message in messages"
                    :key="message.id"
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

                <div v-if="isWaitingForResponse" key="loading-indicator" class="flex justify-start">
                    <div class="flex items-center gap-1.5 rounded-2xl bg-base-200/70 backdrop-blur-md px-4 py-3">
                        <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:0ms]"></span>
                        <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:150ms]"></span>
                        <span class="h-1.5 w-1.5 animate-bounce rounded-full bg-base-content/50 [animation-delay:300ms]"></span>
                    </div>
                </div>
            </TransitionGroup>
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
    </Transition>
</template>

<style scoped>
/* new messages/loading-indicator fade + slide in */
.message-enter-active {
    transition: opacity 0.35s ease-out, transform 0.35s ease-out;
}

.message-enter-from {
    opacity: 0;
    transform: translateY(14px) scale(0.97);
}

/* Vue's FLIP transition: smoothly animates the *other* bubbles sliding into
   their new position when the list changes (e.g. the loading indicator
   above the input appearing/disappearing) */
.message-move {
    transition: transform 0.35s ease-out;
}

.message-leave-active {
    transition: opacity 0.2s ease-in;
    /* takes the leaving element out of flow so it doesn't block/offset the
       .message-move animation of the elements around it while it fades out */
    position: absolute;
}

.message-leave-to {
    opacity: 0;
}

/* crossfade between the checking/OTP-gate/chat screens — mode="out-in" on the
   Transition means only one of these is ever in the DOM at once, so a plain
   fade + subtle scale is enough, no position juggling needed */
.screen-enter-active,
.screen-leave-active {
    transition: opacity 0.25s ease-out, transform 0.25s ease-out;
}

.screen-enter-from {
    opacity: 0;
    transform: scale(0.98);
}

.screen-leave-to {
    opacity: 0;
    transform: scale(1.02);
}
</style>
