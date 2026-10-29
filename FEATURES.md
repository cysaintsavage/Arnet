# Feature status

"Tested" means covered by the automated tests in `tests/` against a fake AI vendor. **No real AI provider key was available when this was built, so no feature has been tried against a live Anthropic, OpenAI, image or search service.** Set your keys, then try each feature once before announcing it.

## Finished and tested

| Area | What works |
|---|---|
| Accounts | Register, sign in, sign out, profile, change password (other sessions are signed out), delete account (removes the user's data), server-side sessions in an HTTP-only cookie |
| Password reset | Token emailed by SMTP, single use, expires. Only offered when SMTP is configured; otherwise the page says so |
| Chat | Streaming replies, saved history per user, new / rename / delete, search, copy, regenerate, Markdown and code blocks, spoken replies (browser speech synthesis) |
| Tools directory | Chat, Code Generator, Code Explainer, Debugger, Refactor, Website Builder, Writing, Translator, Summarizer, Study, Business, Brainstorming, Data Analysis, Productivity. Each is a purpose-built instruction set over the same chat engine. Searchable page, grouped by category |
| Website Builder | HTML/CSS/JS output with an editor and a sandboxed preview served with its own strict policy. Frameworks come back as file trees and code blocks, not a running preview |
| Document analysis | Upload PDF, DOCX, TXT, MD, CSV, JSON (size limit, content checks, not just file name). Ask questions or summarize in chat |
| Image generation | Prompt to image through an OpenAI-compatible images API. Per-user daily limit, private image files |
| Web research | Search results shown as a separate source list, apart from the AI's own explanation |
| Voice | Speech input and spoken output through browser features. Support depends on the browser (Chrome and Safari work best; Firefox lacks speech input) |
| Usage limits | Free and Pro daily message and image limits, editable in the dashboard, enforced on the server |
| Admin dashboard | Users (plan, disable, role), usage statistics, AI request log, error log, settings (limits, provider and model, registration open/closed), service health, branding, contact details, owner information |
| Branding and contact | Footer, About and Contact text exactly as specified. Email is a `mailto:` link, WhatsApp is a `wa.me` link. Editable in the dashboard |
| Security | Scrypt password hashing, server-side authorization on every route, per-user data isolation, CSRF defence, rate limits, input validation, security headers and a strict content policy, safe Markdown rendering (no raw HTML), no keys in the browser, generic error messages |
| Look and feel | Dark and light themes, original logo, responsive layouts checked at desktop and phone widths |

## Needs something from you before it works

| Feature | What to set |
|---|---|
| Any AI answer | `AI_API_KEY` (and `AI_PROVIDER`, `AI_MODEL` if you do not want the defaults) |
| Image generation | `IMAGE_API_KEY` |
| Web research | `SEARCH_API_KEY` (Tavily-compatible API) |
| Password-reset email | `SMTP_HOST`, `SMTP_FROM`, and usually `SMTP_USER` / `SMTP_PASSWORD` |
| WhatsApp link | The number `0746940886` is turned into `https://wa.me/254746940886` using country code 254 (Kenya). If that is wrong, change the country code in Admin, Settings, or enter the number with a leading `+` |

## Not built, and said plainly in the app

- **Online payments.** Plans (Free, Pro) and limits work. The owner sets a user's plan by hand in the dashboard. There is no payment provider, checkout or webhook, so the app does not claim to take payments.
- **PostgreSQL.** The database is SQLite (one file, WAL mode, backed up with SQLite's backup command). That suits a single server and a modest number of users. Moving to PostgreSQL means replacing `app/db.py` and the SQL in the route files.
- **Running code.** Data Analysis reads data and writes formulas or snippets for you. It does not execute code.
- **Multiple server processes.** Rate-limit counters live in memory, so run one worker (the supplied service file does). Scaling out needs a shared store such as Redis.
- **Email verification** of new accounts, two-factor sign-in, and OAuth login.
- **Object storage.** Images are files in `data/images`; documents are stored as extracted text in the database.
