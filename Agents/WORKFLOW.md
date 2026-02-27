# Agent Workflow

## 1) Understand Before Editing
- Read README.md first.
- Inspect entrypoint and directly related modules before changing logic.
- Confirm whether the change is API-facing, infra-facing, or internal.

## 2) Implement Safely
- Make the smallest viable change.
- Keep existing env-var names and deployment assumptions stable.
- If behavior changes, update docs and examples in the same PR.

## 3) Validate
Run these commands after edits:
```bash
python -m py_compile functions/ai_insert_text_assistant_message/main.py functions/user_info_lookup/main.py
# smoke test locally
curl -X POST http://localhost:8082 -H "Content-Type: application/json" -d '{"phoneNumber":"+13055550123"}' || true
```

## 4) Handoff Expectations
- Summarize changed files and behavioral impact.
- List any required env vars, migrations, or manual rollout steps.
- Flag anything not tested locally.
