# Security policy

OEVM is a personal, experimental, non-commercial project run by one hobbyist (see
[DISCLAIMER.md](DISCLAIMER.md)). Security reports are welcome and are handled on a
best-effort basis.

## Reporting a vulnerability

Please report security problems **privately**, not in a public issue:

1. Open the repository's **Security and quality** tab (called **Security** on older
   pages).
2. Choose **Report a vulnerability**.
3. Describe the problem, how to reproduce it and what it could affect.

This uses GitHub's private vulnerability reporting, so only you and the maintainer can see
the report. It needs a GitHub account.

If you cannot see **Report a vulnerability**, open a public issue titled "Private security
contact needed" with no details of the problem, and the maintainer will set up a private
route.

Please use the same private route if you find a key, token, password or personal data
that has been published in this repository by mistake.

## What to expect

- An acknowledgement, usually within 14 days. This is a hobby project, so response times
  are not guaranteed.
- Updates while the problem is looked into, and credit in the fix if you would like it.
- There is no bug bounty.

## Supported versions

Only the latest version on the `main` branch is supported.

## Scope

In scope:

- this repository's code, GitHub Actions workflows and configuration, and the Cloudflare Workers
  deployed from it;
- the published website and its data files, once they exist;
- anything that exposes a secret, a key or personal data.

Out of scope:

- charge point operators' own systems and feeds (please report those to the operator);
- GitHub and other services the project uses or may use (please report those to them);
- reports from automated scanners that do not show a real impact;
- denial of service, spam and social engineering.

## Good-faith research

Please act in good faith: avoid harming people's privacy, do not disrupt any service, only
look at the data you need to show the problem, and allow reasonable time for a fix before
telling anyone else. Never test against operators' feeds. The project's Cloudflare Workers
share one small daily allowance of requests, so please send them only the few requests needed
to show a problem. If you follow these guidelines, the maintainer will not complain about your
research to anyone.

## How the project protects itself

- No keys, tokens or passwords are stored in the repository. Operator keys live in GitHub
  Actions secrets and are referred to by name only. The exception is a connection that an
  operator sets up by calling the project (the OCPI 2.2.1 credentials handshake): its tokens
  are held by the project's own Cloudflare Worker, as Worker secrets and in the Worker's
  storage, and the token the operator uses to reach the project is kept only as a hash
  ([ADR 0025](docs/adr/0025-ocpi-handshake-worker.md)).
- The Workers have Cloudflare's logs switched off, compare tokens in constant time, and hold no
  GitHub token that can change code or secrets. The handshake Worker stops accepting a setup
  token at the latest 10 minutes after the first registration made with it (a retry does not
  extend this), and sooner once the operator uses the new token it was given.
- A secret scanner runs in CI on every file, and before each commit for anyone who has
  installed the pre-commit hooks.
- Keys are only sent over https, and are removed from anything saved or shown, in case a
  server echoes them back.
- CI checks the locked dependencies against known vulnerabilities.
- Tests never call live operator feeds.
- The website has no accounts, no cookies, no tracking and no scripts from third parties.
