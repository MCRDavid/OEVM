# Security policy

OEVM is a personal, experimental, non-commercial project run by one hobbyist (see
[DISCLAIMER.md](DISCLAIMER.md)). Security reports are welcome and are handled on a
best-effort basis.

## Reporting a vulnerability

Please report security problems **privately**, not in a public issue:

1. Open the repository's **Security** tab.
2. Choose **Report a vulnerability**.
3. Describe the problem, how to reproduce it and what it could affect.

This uses GitHub's private vulnerability reporting, so only you and the maintainer can see
the report.

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

- this repository's code, GitHub Actions workflows and configuration;
- the published website and its data files, once they exist;
- anything that exposes a secret, a key or personal data.

Out of scope:

- charge point operators' own systems and feeds (please report those to the operator);
- GitHub, Cloudflare and other services the project uses (please report those to them);
- reports from automated scanners that do not show a real impact;
- denial of service, spam and social engineering.

## Good-faith research

Please act in good faith: avoid harming people's privacy, do not disrupt any service, only
look at the data you need to show the problem, and allow reasonable time for a fix before
telling anyone else. Never test against operators' feeds. If you follow these guidelines,
the maintainer will not complain about your research to anyone.

## How the project protects itself

- No keys, tokens or passwords are stored in the repository. Operator keys live in GitHub
  Actions secrets and are referred to by name only.
- A secret scanner runs before every commit and in CI on every file.
- Tests never call live operator feeds.
- The website has no accounts, no cookies, no tracking and no scripts from third parties.
