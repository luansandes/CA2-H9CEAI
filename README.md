# Atlantic Coast Tours AI assistant

A pilot, user-facing travel chat for Atlantic Coast Tours. The static frontend is
hosted on GitHub Pages and calls a Python serverless API on Vercel. The backend
uses OpenAI's Responses API, reads the tour catalogue live from Google Sheets,
and retrieves date-specific weather from Open-Meteo.

## Architecture

- `index.html`, `styles.css`, `app.js`: zero-build, single-page chat interface
- `config.js`: public Vercel endpoint configuration
- `api/chat.py`: validation, Responses API tool loop, live sheet reads, and weather
- `api/system_prompt.txt`: inspectable assistant instructions, cached at cold start
- `api/health.py`: lightweight deployment health check
- `.github/workflows/pages.yml`: GitHub Pages deployment workflow
- [`docs/atlantic-coast-tours-architecture.drawio`](docs/atlantic-coast-tours-architecture.drawio): editable diagrams.net solution architecture

The browser retains the current conversation in memory. Chats are not persisted,
and selecting an offer card continues the conversation rather than making a
booking.

## Data behavior

Tour data is read-only and comes from this public Google Sheet tab:

`https://docs.google.com/spreadsheets/d/1balBGf8QhZ5dc-RCCAPt2kcrcf6m_YRh0HL_r8bBtJw/edit?gid=120683740`

Every catalogue tool call issues a new GET request to the CSV export with
no-cache headers and a unique query parameter. The application does not store,
copy, mirror, update, or hardcode sheet rows. Relevant cell values are sent to
the model as curated business data and cards are hydrated only from rows read
during the current request.

When a concrete date and tour location are known, the backend geocodes the
location and requests a live forecast from Open-Meteo. Forecasts outside the
supported window are reported as unavailable.

## Run locally

Install the backend dependency and expose the required environment variables:

```powershell
python -m pip install -r requirements.txt
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_MODEL = "gpt-5.6-luna"
$env:FRONTEND_ORIGIN = "http://localhost:8000"
python -m http.server 8000
```

Open `http://localhost:8000`. The static site will call the deployed Vercel API
configured in `config.js`.

Run the local automated checks with:

```powershell
python -m unittest discover -s tests -v
```

The tests mock external services and never modify the Google Sheet.

## Deploy the backend to Vercel

When importing the GitHub repository in Vercel, use:

- Framework preset: **Other**
- Root directory: `.` (the repository root)
- Build command: leave empty
- Output directory: leave empty
- Install command: leave at the Vercel default

Add these variables in **Project Settings > Environment Variables**:

- `OPENAI_API_KEY`: the secret OpenAI API key
- `OPENAI_MODEL`: `gpt-5.6-luna`
- `FRONTEND_ORIGIN`: `https://luansandes.github.io`

Deploy and verify:

- Health: `https://ca-2-h9-ceai-teal.vercel.app/api/health`
- Chat: `https://ca-2-h9-ceai-teal.vercel.app/api/chat`

The system prompt is loaded once per warm serverless instance. Update
`api/system_prompt.txt` and redeploy to apply prompt changes consistently.

Never commit `.env`, `.env.local`, `.vercel`, or a real API key.

## Enable GitHub Pages

1. Open **Settings > Pages** in the GitHub repository.
2. Select **GitHub Actions** as the build and deployment source.
3. Push to `master`.

The workflow publishes only the four static frontend files at
`https://luansandes.github.io/CA2-H9CEAI/`.

## API contract

`POST /api/chat`

```json
{
  "messages": [
    { "role": "user", "content": "Show me kayak trips near Galway" }
  ]
}
```

Success response:

```json
{
  "message": "Here are two live options near Galway.",
  "offers": [
    {
      "tour_id": "ACT020",
      "tour_name": "Kinvara Kayak & Castle Tour",
      "category": "Kayak Trip",
      "location": "Kinvara, Co. Galway",
      "meeting_point": "Kinvara Quay",
      "price_eur": "62",
      "duration_hours": "3",
      "capacity": "10",
      "availability": "Apr-Oct",
      "slots_this_week": "6",
      "special_offer": "Early-bird 15% off before 9am",
      "description": "Paddle across Galway Bay..."
    }
  ]
}
```

The backend validates and retains at most the 20 most recent messages per
request. Upstream failures return a controlled JSON error.

## Pilot limitations

- No bookings, payments, accounts, authentication, or persistent conversations
- No production-grade rate limiting or abuse protection
- No streaming responses
- Weather forecasts are informational and can change
