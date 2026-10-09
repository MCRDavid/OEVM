# Evidence

Saved copies that back the engagement log on the transparency page, one folder per
operator id: `evidence/<operator id>/`. Name each file by date and what it is, for example
`2026-10-20-reply.md`, and point to it from `evidence_file` in that operator's
`engagement.log` (or `file` in `engagement.evidence`).

Rules:

- No personal names, email addresses, phone numbers or signatures. Remove them before
  saving and write the sender as a role, for example "the operator's open data team".
- Keep only what the log needs: the date, the channel and the operator's own words.
- Never save a key, token or password, even one an operator sends. Store it as a GitHub
  Actions secret and record only its secret name in the operator file.
- Everything here is public. Each file keeps the operator's words as they wrote them;
  this repository's Apache-2.0 licence does not apply to them.
