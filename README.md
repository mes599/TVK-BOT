# Discord AI Agent

The current bot provides ticket, order, payment-confirmation, welcome, and
showcase flows. The AI agent is being introduced incrementally so existing
flows stay operational.

## Step 1: configuration foundation

The AI feature is disabled by default (`AI_ENABLED=false`). No OpenAI request
is made in this step.

For local development, copy `.env.example` to `.env`, fill in the values, and
keep `.env` out of version control. Railway will provide the same values via
its Variables tab.

Install the declared dependencies before starting locally:

```powershell
pip install -r requirements.txt
```

Required now: `DISCORD_BOT_TOKEN`.

Required only once the future AI feature is enabled: `OPENAI_API_KEY`.

The planned limits are `AI_MAX_INPUT_CHARACTERS`, `AI_MAX_OUTPUT_TOKENS`,
`AI_USER_COOLDOWN_SECONDS`, `AI_DAILY_USER_LIMIT`, and `AI_DAILY_GUILD_LIMIT`.
They are validated now and will be enforced once the AI command is added.

## Step 2: Railway Postgres and persistent deployment

The repository contains a versioned SQL migration in `migrations/` and a
secret-free `railway.toml`. Railway runs `python -m database migrate` before
starting the persistent bot process with `python bot.py`.

In Railway, create a **PostgreSQL** database service, then add this reference
variable to the bot service (replace `Postgres` with the actual service name if
you choose another one):

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

Keep the database private; the bot reaches it through Railway's private
network. Add `DISCORD_BOT_TOKEN` and, only when AI is enabled in a later step,
`OPENAI_API_KEY` via Railway's Variables tab. Seal both secret variables after
setting them. Do not put any production value in `.env.example`.

The migration creates separate tables for conversation sessions, expiring
messages, opt-in memories, daily usage totals, background jobs, and audit
events. It does not run during the current ticket/showcase bot process yet.

## Step 3: minimal AI assistant

With `AI_ENABLED=true`, the bot adds two opt-in entry points in servers:

- `/ai <question>` sends a private response to the requesting user.
- Mentioning the bot followed by a question replies in that channel.

The implementation uses the OpenAI Responses API with no tools, `store=False`,
a hashed Discord identifier, a request timeout, and the configured character,
output-token, concurrency, cooldown, user-daily, and guild-daily limits.
Postgres records only daily request and token totals in this step; conversation
history and long-term memory remain disabled until the next step.

## Step 4: context and opt-in memory

The AI keeps at most `AI_CONTEXT_MESSAGE_LIMIT` recent messages for the same
user and channel. They expire automatically after `AI_MESSAGE_RETENTION_DAYS`
(30 by default), and are only included in later AI requests for that same
channel and user.

Long-term memory is opt-in only:

- `/ai_remember <text>` saves a user-selected preference or fact.
- `/ai_memory` privately displays the user's saved memories.
- `/ai_forget` deletes all of that user's saved memories in the server.
- `/ai_reset` deletes that user's current-channel conversation context.

Saved memories expire after `AI_MEMORY_RETENTION_DAYS` (180 by default), are
limited by `AI_MEMORY_MAX_ITEMS`, and are not shared with other users. A daily
cleanup task removes expired context and memories.
