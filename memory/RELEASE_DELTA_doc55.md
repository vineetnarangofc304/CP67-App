# Doc #55 — Release Delta (held, pending explicit approval)

**Date**: Oct 20, 2026 — Session 94
**Scope**: Separate credential-related delta identified while shipping Doc #55 Fix 1 + Fix 2.

> **Not part of the ordinary batch.** Must be reviewed and explicitly approved before any merge to production.

## 1. Staged fallback-credential block in server.py

**Location**: `/app/backend/server.py` lines ~5431-5455
**Shape (presence only, values deliberately not reproduced here)**:
- A dict constant `_KARIX_SMS_DEFAULTS` with 5 string keys corresponding to the Karix SMS env variables (API URL, API key, sender header, DLT entity id, DLT template id).
- A helper `_env_or_default(key)` that prefers a non-empty environment variable and falls back to the dict entry when the env value is blank/missing.
- The 5 module-level constants (`KARIX_SMS_API_URL`, `KARIX_SMS_API_KEY`, `KARIX_SMS_SENDER_ID`, `KARIX_SMS_DLT_ENTITY_ID`, `KARIX_SMS_DLT_TEMPLATE_ID`) resolve through `_env_or_default`.

## 2. Current runtime state (verified without printing values)

- On the Preview pod, all five env vars are set via `/app/backend/.env`; `_env_or_default` therefore returns the env values, the fallback dict is **never read at runtime** on this deployment.
- No credential copy, print, activation, or new persistent store has been performed in Session 94.
- No permission/access change.
- No app-store submission.

## 3. Why this is flagged separately

- Embedding provider credential-shaped literals in source — even as "unreachable" fallbacks — is a credential-release delta, not an ordinary bugfix. It can change the behaviour of a production pod that comes up with a partially-populated `.env`.
- Source build-host differences (iOS WebView host vs Android TWA host vs Preview host) are **not** proof of installed app versions on handsets, so we cannot claim fallbacks are "needed" without an auditable deployment check.
- Vineet's current instruction scope explicitly excludes credential/permission/release-config changes.

## 4. Options for review

| Option | Effect on Doc #55 user-visible behaviour | Credential surface change |
|---|---|---|
| **A — Keep as is** | None (Doc #55 fix is independent of this block). | Fallback literals remain in source; env still wins at runtime. |
| **B — Remove the fallback literals**, keep `_env_or_default` returning `""` when env is blank | None on Preview (env is correct). On a mis-synced prod pod OTP will fail *loudly* (503 via Fix 1) instead of using an embedded credential. | Removes credential-shaped literals from source. |
| **C — Replace literals with a sentinel string** (e.g. `"<set-via-env>"`) and have `send_otp_sms` return a specific error if the sentinel is encountered | None on Preview. On mis-synced prod a 503 with a specific hint is returned. | Removes credential-shaped literals from source. |

## 5. Action required

Vineet to pick A / B / C explicitly. No code change will be made for this delta inside the Doc #55 batch.

## 6. Items *out of scope* for this delta (explicitly deferred)

- New `/api/admin/otp/health` presence-check endpoint (deferred).
- Karix DLR delivery webhook (deferred — would move "acceptance" to "delivery" proof).
- Any Karix dashboard configuration change (deferred).
- Any app-store submission (not in scope).
- Any auth/permission/security change (not in scope).

## Production baseline check (read-only)
- Repo has only local branch `main` (HEAD 39c5403). No git remotes, no tags, no other refs, no stash.
- No marker in `.emergent/` or git history records which commit is Published to `cp67bot.fundlexperiences.com` or `mall-rewards-1.emergent.host`.
- `_KARIX_SMS_DEFAULTS` first appears in commit 4803530 (2026-10-16), server.py:5438. Whether that commit was ever published cannot be determined from this environment.
- RESULT: Production source baseline NOT accessible. Release preparation STOPPED per instruction. Code left unchanged.

