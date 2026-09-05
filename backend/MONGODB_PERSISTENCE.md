# MongoDB persistence and deployment checks

## Deployment scope

The verified live authentication release is
`1f2a06b0b7797044857ab8195038e91ce4c9df55`. It contains the focused BSON
login-handoff timestamp fix, enforced trial access, validated account identity,
durable new-account read-back, and the required-code frontend state. The broader
patient-activity persistence work described below remains pending locally.

It was deployed from the clean worktree `D:/repos/rehyn_mongodb_signin_hotfix`
(branch `codex/mongodb-sign-in-hotfix`) by pushing non-force to the existing
Render branch `conflict_290826_1558`. This original dirty worktree retains the
same timestamp fix alongside the user's pending edits and asset deletions.
Reconcile with the advanced remote branch before publishing the remaining work;
do not reset this worktree or restore deleted user assets automatically.

## Source of truth

- `users`: stable account ID, email/name, consent, survey/profile, login timestamp,
  `initial_assessment_completed_at`, and daily check-ins.
- `assessments` and `assessment_task_progress`: results and completed task ledger.
- `exercise_repetitions`: each guided repetition, scoped to user, plan, local day,
  exercise, session, and repetition number. Unique `_id` makes retries idempotent.
- `alira_activities`: completed exercise sessions and final scores; new clients send
  `client_activity_id` so retrying a save cannot duplicate a session or its rewards.
- `journal_entries`: account-scoped personal journal notes.
- Existing Alira check-ins, reviews, functional issues, and chat histories remain
  in their respective MongoDB collections.

MongoDB writes use majority acknowledgement. Render cannot fall back to temporary
JSON files even if a local fallback setting is accidentally enabled. Device caches
are not evidence that a record reached MongoDB. Failed exercise writes remain in
an account-scoped outbox and retry on reconnect/app activation; journal failures
retain the draft and show an error. Pending records must never move to another
account automatically. Do not clear browser/app storage while activity is pending.

Account completion is separate from a particular build, browser session, or latest
assessment package. A database error must return an unavailable state, not a false
incomplete state. Testing-shortcut snapshots remain explicitly marked synthetic.

## Trial sign-in and new accounts

Trial-code validation is enabled by default and cannot be disabled by the testing
override on Render. The secret remains server-side in `REHYN_TRIAL_ACCESS_CODE`.
The Blueprint explicitly sets `REHYN_ENFORCE_TRIAL_CODE=1`.

Login, signup, and the `rehyn.com` login handoff all validate the code before
looking up or creating an account. Names and email addresses are validated;
normalized email identifies the account. New accounts use a stable unique MongoDB
`_id` and are read back before sign-in can succeed. A different email gets a
separate account; returning accounts retain their saved assessment and check-in
state. A database failure must not produce a successful, device-only sign-in.

This is trial access, not verification of email ownership. Before using it for
real patient data, add verified per-user authentication; knowing a shared trial
code and another person's email must not be sufficient to access their records.

## Connection recovery

The backend maintains one pooled Motor client. Read/write retries and bounded
timeouts are enabled. Background probes run every 30 seconds when healthy and
retry after 5 seconds when disconnected. A probe verifies both ping and an
authenticated read of `users`, bypassing the failure cooldown. Concurrent probes
share one task. `/api/health/db` returns sanitized JSON and HTTP 503 on failure.

This recovers transient outages; it cannot repair invalid credentials, a paused
cluster, TLS/network rejection, or a stopped hosting service.

## Before deploying

1. In Render, verify that `MONGO_URL` points to the existing production Atlas
   cluster and `DB_NAME` is the existing production database (`rehyn` in the
   blueprint). Do not create an empty replacement database as a login workaround.
   Hosting environment variables take precedence over local `.env` values.
2. In Atlas, check cluster availability, the database user's access to the intended
   database, and network access for the service's actual Render outbound ranges.
   Keep certificate verification enabled. Do not open Atlas to every IP as a fix.
3. Set `ALLOW_EPHEMERAL_PATIENT_STATE=0` on Render. Check the deployed environment,
   not only the YAML file, for services that are not managed by a Blueprint.
4. Deploy only after the frontend assets/build are intact. Confirm the deployed
   commit and that `/api/health/db` returns JSON with `ok: true`.
5. Using a designated test account, save consent/survey, an assessment, a daily
   check-in, a repetition, and a journal note. Inspect the account-scoped MongoDB
   records. Sign out, clear only that test device's caches after sync completes,
   and sign back in. Confirm initial completion and the current check-in survive.
6. Repeat after a server restart/redeploy and from another test device. An outage
   must show temporary unavailability, not request another initial assessment.
7. Check retry recovery: interrupt a repetition save, reopen the app with the same
   account, restore connectivity, and confirm exactly one stored repetition.

## Verification on 2026-09-05

- 89 focused backend tests passed, including real API route/JSON contracts with
  test database doubles, account isolation, restart/cache-loss state restoration,
  atomic daily check-ins, idempotent retries, and database recovery probes.
  These also cover trial validation, new-account persistence/readback, distinct
  emails, the public-site handoff, and failures during each sign-in database step.
- 7 frontend outbox tests passed (offline/reopen, multiple accounts, concurrent
  tabs, failed local writes, save ordering, and progress refresh).
- Targeted ESLint and Python compilation passed.
- Full TypeScript check still reports pre-existing WebView `onPermissionRequest`
  and `persona-chat.tsx` errors. No new type errors from this change.
- Full web export is blocked by pre-existing deleted assets, beginning with
  `frontend/assets/images/alira-companion.png`. Those deletions were not reverted.
- Two broader care API tests disagree with the current survey-readiness policy.
  Both failures also reproduce with the pre-change server; policy was not changed
  to silence these tests.
- After the user's explicit approval, added only the two actual shared Render
  outbound ranges, `74.220.48.0/24` and `74.220.56.0/24`, to Atlas Project 0.
  Both are Active. The existing single-IP entry was left intact. No allow-all
  entry was added; database credentials and TLS settings were not changed.
- The live database check changed from HTTP 503 to HTTP 200 JSON with `ok: true`.
  After the focused deployment, it returned `state: closed`, `last_error: null`,
  and a 147 ms database probe. This verifies current reachability, not permanent
  availability. Render's free service can still sleep after inactivity.
- A real public-site sign-in exposed a second issue: BSON dates decode as naive
  UTC by default, but the handoff consumer compared them to timezone-aware UTC.
  Render logs confirmed `TypeError: can't compare offset-naive and offset-aware
  datetimes`. Because the token had already been consumed, a retry said expired.
- The focused fix normalizes that timestamp before comparison and rejects absent
  or malformed expiry dates. Regression tests use actual BSON encode/decode with
  both timezone modes, successful completion, single-use tokens, and expiry.
  The first release passed 18 focused tests in the clean hotfix checkout. The
  subsequent registration release passed 40 focused authentication, handoff and
  account-state tests plus targeted frontend lint.
- Render deployed `1f2a06b` successfully in 1m26s. `/api/` reports the full release
  SHA above, `/api/health/db` returns HTTP 200 JSON with `ok: true`, and a wrong
  trial code returns HTTP 403.
- A new production verification account was submitted through `https://rehyn.com`
  with the correct code and reached `https://rehyn.onrender.com/consent`. Atlas
  stores the exact normalized email, submitted name, stable account ID,
  `created_at`, `last_login_at`, and trial grant. The trial code is not stored.
  The document count increased by exactly one; the earlier wrong-code attempt did
  not create an account. Consent was not accepted on the user's behalf.
- Atlas confirms the same account ID remains stored before and after the Render
  deployment and repeat sign-in; no duplicate account was created by the retry.
  At verification, `rehyn` contained `users` and `login_handoffs` only. No previous
  assessments, task-progress records, or initial-completion marker were found
  for this account. Historical results have NOT been recovered or fabricated.
- Trial-code enforcement and verified MongoDB account creation are deployed. The
  larger assessment/activity persistence and outbox changes, plus unrelated local
  frontend work, remain pending and must not be represented as deployed by this
  focused release.

References: [Atlas connection troubleshooting](https://www.mongodb.com/docs/atlas/troubleshoot-connection/),
[MongoDB connection options](https://www.mongodb.com/docs/manual/reference/connection-string-options/).
