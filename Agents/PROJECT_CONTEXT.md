# Project Context for Agents

## Mission
Google Cloud Functions v2 monorepo with deploy automation for AI assistant message ingestion and user info lookup.

## Key Architecture Anchors
- functions/*/function.json: deploy metadata
- functions/ai_insert_text_assistant_message/main.py: chat message ingestion + optional file uploads
- functions/user_info_lookup/main.py: phone-to-user lookup
- .github/workflows/deploy.yml: changed-functions deployment pipeline

## Runtime Entry
functions/ai_insert_text_assistant_message/main.py and functions/user_info_lookup/main.py

## External Interfaces
Function HTTP endpoints are created from each function name/entrypoint at deploy time.

## Constraints
- Preserve public request/response contracts unless explicitly asked to change them.
- Prefer minimal, targeted edits; avoid broad refactors unless required.
- Keep secrets in env files or secret managers, never hardcoded in source.
- Read this repo's README before implementing any non-trivial change.
