# Knowledge Workspace frontend

Next.js frontend with reusable login and registration forms, a shared header and navigation, conversation sidebar and chat composer, and a paper/document dashboard. Zustand manages the session, conversations, messages, papers, and selected paper. Only the session is persisted; logout clears the workspace state. Passwords are never stored.

## Run locally

```sh
bun install
bun dev
```

Open http://localhost:3000. Run the FastAPI backend on http://localhost:8000. To use another backend, set `NEXT_PUBLIC_API_URL` in `.env.local` to its complete API prefix (for example, `http://localhost:8000/api/v1`). The backend must allow the frontend origin through CORS.

## Routes

- `/auth` and `/login`: email/password login.
- `/register`: username/email/password registration, followed by login.
- `/`: authenticated conversation workspace; starts with an empty conversation.
- `/dashboard`: create/select papers and upload documents with document type and assessment metadata.

The UI uses the existing `/auth`, `/threads`, `/chat`, `/papers`, and `/documents` backend endpoints. It reports backend failures rather than generating placeholder responses. A new conversation is created when its first message is sent. Chat history and paper data are loaded from the server.

## Validation

```sh
bun run lint
bunx tsc --noEmit
bun run build
```
