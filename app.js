const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const messagesElement = document.querySelector("#messages");
const sendButton = document.querySelector("#send-button");
const clearButton = document.querySelector("#clear-button");
const statusElement = document.querySelector("#status");
const startersElement = document.querySelector("#starters");

const conversation = [];
const defaultApiUrl = "https://ca-2-h9-ceai-teal.vercel.app/api/chat";
const configuredApiUrl = window.APP_CONFIG?.apiUrl;
const apiUrl =
  configuredApiUrl && !configuredApiUrl.includes("YOUR-VERCEL-PROJECT")
    ? configuredApiUrl
    : defaultApiUrl;

const welcomeMessage = [
  "Hi, I’m Atlantic Coast Tours’ AI travel assistant. I can search our live tour catalogue, recommend experiences, and explain current offers and availability.",
  "My guidance is informational, and I can’t confirm bookings or payments.",
];

function createOfferCard(offer) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "offer-card";
  card.dataset.tourId = offer.tour_id;
  card.dataset.tourName = offer.tour_name;
  card.setAttribute("aria-label", `Ask about ${offer.tour_name}`);

  const top = document.createElement("div");
  top.className = "offer-card-top";

  const category = document.createElement("span");
  category.className = "offer-category";
  category.textContent = offer.category;

  const price = document.createElement("span");
  price.className = "offer-price";
  price.textContent = `€${offer.price_eur}`;
  top.append(category, price);

  const title = document.createElement("h3");
  title.textContent = offer.tour_name;

  const location = document.createElement("p");
  location.className = "offer-location";
  location.textContent = `⌖ ${offer.location}`;

  const description = document.createElement("p");
  description.className = "offer-description";
  description.textContent = offer.description;

  const facts = document.createElement("div");
  facts.className = "offer-facts";
  facts.append(
    createFact("Duration", `${offer.duration_hours} hrs`),
    createFact("Availability", offer.availability),
    createFact("This week", `${offer.slots_this_week} slots`),
  );

  card.append(top, title, location, description, facts);

  if (offer.special_offer) {
    const special = document.createElement("span");
    special.className = "offer-special";
    special.textContent = offer.special_offer;
    card.append(special);
  }

  const action = document.createElement("span");
  action.className = "offer-action";
  action.innerHTML = "Ask about this tour <span aria-hidden=\"true\">→</span>";
  card.append(action);
  return card;
}

function createFact(label, value) {
  const fact = document.createElement("span");
  const small = document.createElement("small");
  small.textContent = label;
  const strong = document.createElement("strong");
  strong.textContent = value;
  fact.append(small, strong);
  return fact;
}

function addMessage(role, content, offers = []) {
  const article = document.createElement("article");
  article.className = `message ${role}-message`;

  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.setAttribute("aria-hidden", "true");
  avatar.textContent = role === "user" ? "You" : "AC";

  const contentWrap = document.createElement("div");
  contentWrap.className = "message-content";

  const author = document.createElement("span");
  author.className = "message-author";
  author.textContent = role === "user" ? "You" : "Atlantic AI";

  const body = document.createElement("div");
  body.className = "message-body";
  const paragraphs = String(content).split(/\n{2,}/).filter(Boolean);
  for (const paragraph of paragraphs) {
    const text = document.createElement("p");
    text.textContent = paragraph;
    body.append(text);
  }

  contentWrap.append(author, body);
  if (role === "assistant" && offers.length) {
    const cards = document.createElement("div");
    cards.className = "offer-grid";
    cards.setAttribute("aria-label", "Recommended tours");
    offers.forEach((offer) => cards.append(createOfferCard(offer)));
    contentWrap.append(cards);
  }

  article.append(avatar, contentWrap);
  messagesElement.append(article);
  messagesElement.scrollTop = messagesElement.scrollHeight;
}

function setLoading(isLoading) {
  input.disabled = isLoading;
  sendButton.disabled = isLoading;
  clearButton.disabled = isLoading;
  document.querySelectorAll(".offer-card, .starters button").forEach((button) => {
    button.disabled = isLoading;
  });
  sendButton.querySelector("span").textContent = isLoading ? "Searching…" : "Send";
}

function resetChat() {
  conversation.length = 0;
  messagesElement.replaceChildren();
  addMessage("assistant", welcomeMessage.join("\n\n"));
  startersElement.hidden = false;
  statusElement.textContent = "";
  input.focus();
}

async function sendMessage(content) {
  conversation.push({ role: "user", content });
  addMessage("user", content);
  startersElement.hidden = true;
  setLoading(true);
  statusElement.textContent = "Thinking…";

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

    const offers = Array.isArray(data.offers) ? data.offers : [];
    conversation.push({ role: "assistant", content: data.message });
    addMessage("assistant", data.message, offers);
    statusElement.textContent = "";
  } catch (error) {
    conversation.pop();
    throw error;
  } finally {
    setLoading(false);
    input.focus();
  }
}

async function submitContent(content) {
  if (!content || input.disabled) return;
  input.value = "";
  input.style.height = "auto";
  try {
    await sendMessage(content);
  } catch (error) {
    statusElement.textContent = error.message || "Unable to reach the travel assistant.";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  submitContent(input.value.trim());
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

messagesElement.addEventListener("click", (event) => {
  const card = event.target.closest(".offer-card");
  if (!card || card.disabled) return;
  submitContent(
    `Tell me more about ${card.dataset.tourId} — ${card.dataset.tourName}. Please check the live details and help me decide if it suits me.`,
  );
});

startersElement.addEventListener("click", (event) => {
  const starter = event.target.closest("button[data-prompt]");
  if (starter) submitContent(starter.dataset.prompt);
});

clearButton.addEventListener("click", resetChat);
