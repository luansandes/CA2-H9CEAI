const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const messagesElement = document.querySelector("#messages");
const sendButton = document.querySelector("#send-button");
const clearButton = document.querySelector("#clear-button");
const statusElement = document.querySelector("#status");

const conversation = [];
const defaultApiUrl = "https://ca-2-h9-ceai-teal.vercel.app/api/chat";
const configuredApiUrl = window.APP_CONFIG?.apiUrl;
const apiUrl =
  configuredApiUrl && !configuredApiUrl.includes("YOUR-VERCEL-PROJECT")
    ? configuredApiUrl
    : defaultApiUrl;

function addMessage(role, content) {
  const article = document.createElement("article");
  article.className = `message ${role}-message`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = role === "user" ? "You" : "AI";

  const body = document.createElement("div");
  body.className = "message-body";

  const author = document.createElement("span");
  author.className = "message-author";
  author.textContent = role === "user" ? "You" : "Assistant";

  const text = document.createElement("p");
  text.textContent = content;

  body.append(author, text);
  article.append(avatar, body);
  messagesElement.append(article);
  messagesElement.scrollTop = messagesElement.scrollHeight;
}

function setLoading(isLoading) {
  input.disabled = isLoading;
  sendButton.disabled = isLoading;
  clearButton.disabled = isLoading;
  sendButton.querySelector("span:first-child").textContent = isLoading
    ? "Thinking…"
    : "Send";
}

function resetChat() {
  conversation.length = 0;
  messagesElement.replaceChildren();
  addMessage("assistant", "Hi! What would you like to explore today?");
  statusElement.textContent = "";
  input.focus();
}

async function sendMessage(content) {
  conversation.push({ role: "user", content });
  addMessage("user", content);
  setLoading(true);
  statusElement.textContent = "";

  try {
    const response = await fetch(apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: conversation }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || `Request failed (${response.status}).`);
    }

    if (typeof data.message !== "string" || !data.message.trim()) {
      throw new Error("The backend returned an invalid response.");
    }

    conversation.push({ role: "assistant", content: data.message });
    addMessage("assistant", data.message);
  } catch (error) {
    conversation.pop();
    throw error;
  } finally {
    setLoading(false);
    input.focus();
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const content = input.value.trim();
  if (!content) return;

  input.value = "";
  input.style.height = "auto";

  try {
    await sendMessage(content);
  } catch (error) {
    statusElement.textContent = error.message || "Unable to reach the assistant.";
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

clearButton.addEventListener("click", resetChat);
