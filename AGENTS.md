# Project workflow

User requirement: all future changes go to the testing site first. After testing is complete, ask the user whether to promote that specific change to production. Production may be updated only after explicit user approval.

- Implement, test, commit and push new features on `staging` by default.
- Do not push or merge changes to `main`, or change production Secrets, credentials, data, or deployment settings without explicit approval for that release.
- Approval for a previous production release does not authorize later releases.
- Present the tested result and limitations before asking to promote. Do not claim live OAuth or deployment readiness when required external configuration is missing.
- Production entry: `app.py`; testing entry: `staging_app.py`; Google authorization management entry: `approval_app.py`.
- Keep account/data isolation between production and staging. Never commit credentials or original financial reports; use synthetic test data.
- Authentication/authorization configuration and database failures must deny access. Never add a development login bypass to a deployed entry point.
