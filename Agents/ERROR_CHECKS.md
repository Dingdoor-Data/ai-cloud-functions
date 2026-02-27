# Error Checks and Debugging Guide

## Fast Triage
1. Confirm env vars are loaded and non-empty.
2. Run syntax/compile checks first.
3. Run the smallest reproducible request against the service/notebook task.
4. Inspect logs around external calls (OpenAI, Pinecone, Twilio, Firebase, etc.).

## Repo Validation Commands
```bash
python -m py_compile functions/ai_insert_text_assistant_message/main.py functions/user_info_lookup/main.py
# smoke test locally
curl -X POST http://localhost:8082 -H "Content-Type: application/json" -d '{"phoneNumber":"+13055550123"}' || true
```

## Common Failure Classes
- Auth/config errors: bad API keys, missing project IDs, wrong region/runtime.
- Contract mismatches: payload shape drift between services.
- External service timeouts/rate limits: retries or fallback paths needed.
- Local runtime drift: wrong Python/Node/Bun version vs repo expectation.

## Agent Escalation Rule
If a fix requires changing public API contracts, deployment topology, or credentials model, stop and request human confirmation before applying the change.
