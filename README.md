# ai-cloud-functions

## What This Repo Does
Google Cloud Functions v2 monorepo with deploy automation for AI assistant message ingestion and user info lookup.

## Stack
Python Cloud Functions, Functions Framework, Firebase Emulator, GitHub Actions

## Entrypoint
functions/ai_insert_text_assistant_message/main.py and functions/user_info_lookup/main.py

## Key Files
- functions/*/function.json: deploy metadata
- functions/ai_insert_text_assistant_message/main.py: chat message ingestion + optional file uploads
- functions/user_info_lookup/main.py: phone-to-user lookup
- .github/workflows/deploy.yml: changed-functions deployment pipeline

## Run Locally
```bash
make emu-firestore PROJECT=dingdoor-development
make run-fn FN=ai_insert_text_assistant_message TARGET=ai_insert_text_assistant_message PORT=8081 PROJECT=dingdoor-development
make run-fn FN=user_info_lookup TARGET=http_lookup PORT=8082 PROJECT=dingdoor-development
```

## Run With Docker (If Available)
```bash
Not configured in this repo.
```

## Verification / Checks
```bash
python -m py_compile functions/ai_insert_text_assistant_message/main.py functions/user_info_lookup/main.py
# smoke test locally
curl -X POST http://localhost:8082 -H "Content-Type: application/json" -d '{"phoneNumber":"+13055550123"}' || true
```

## Interfaces
Function HTTP endpoints are created from each function name/entrypoint at deploy time.

## Notes
Makefile has a truncated dev target in current state; prefer emu-firestore + run-fn.

## Credentials (.env.example)

```dotenv
# Function config (from env.dev.yaml / env.prod.yaml)
FILES_BUCKET=
SIGNED_URL_SA_EMAIL=
SIGNED_URL_EXPIRES_HOURS=72
AI_ASSISTANT_MESSAGES_COLLECTION=aiAssistantMessages
ENV=DEV
GOOGLE_CLOUD_PROJECT=
```
