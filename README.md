# CA2-H9CEAI chat scaffold

A static, user-facing chat hosted on GitHub Pages, backed by a Python serverless
function on Vercel. The OpenAI API key exists only in Vercel's environment and
is never sent to the browser.

## Architecture

- `index.html`, `styles.css`, `app.js`: zero-build GitHub Pages frontend
- `config.js`: public backend endpoint configuration
- `api/chat.py`: validated chat endpoint using OpenAI's Responses API
- `api/health.py`: lightweight deployment health check
- `.github/workflows/pages.yml`: GitHub Pages deployment workflow

## Run the frontend locally

The production backend only allows configured browser origins. Local port 8000
is allowed for development:

```powershell
python -m http.server 8000
```

Open `http://localhost:8000`. To chat against a deployed backend, temporarily
set its URL in `config.js`.

## Deploy the backend to Vercel

1. Import this GitHub repository as a new Vercel project.
2. In **Settings > Environment Variables**, add:
   - `OPENAI_API_KEY`: your secret OpenAI API key
   - `OPENAI_MODEL`: optional; defaults to `gpt-5.6-sol`
   - `FRONTEND_ORIGIN`: `https://luansandes.github.io`
3. Deploy. Vercel will expose `/api/chat` and `/api/health`.
4. Confirm `https://YOUR-PROJECT.vercel.app/api/health` returns `{"status":"ok"}`.
5. Replace the placeholder URL in `config.js` with the deployed `/api/chat` URL,
   commit, and push again.

Never commit `.env` or a real API key. `.env.example` contains names only.

## Enable GitHub Pages

1. In the GitHub repository, open **Settings > Pages**.
2. Under **Build and deployment**, choose **GitHub Actions** as the source.
3. Push to `master`. The workflow publishes the frontend at
   `https://luansandes.github.io/CA2-H9CEAI/`.

## API contract

`POST /api/chat`

```json
{
  "messages": [
    { "role": "user", "content": "Hello" }
  ]
}
```

Success response:

```json
{ "message": "Hi! How can I help?" }
```

The backend keeps the most recent 20 validated messages per request. The browser
owns conversation state; this scaffold does not persist chats or identify users.

## Next production steps

- Add abuse protection or authentication before sharing the endpoint broadly.
- Add rate limits and request logging appropriate for your privacy requirements.
- Pin dependencies after validating a deployment.

