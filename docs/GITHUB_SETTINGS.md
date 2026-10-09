# GitHub settings to switch on

These settings live in the repository's settings on GitHub, not in its files, so they must
be switched on by hand. Menu names are as GitHub's documentation gave them on 7 October
2026. GitHub renamed several in 2026, so your screen may differ slightly:

- the repository's **Security** tab is now called **Security and quality**;
- in **Settings**, the security page is called **Advanced Security** (older pages call it
  **Code security** or **Code security and analysis**).

All of these are free for public repositories.

## 1. Private vulnerability reporting

Lets people report security problems privately, as `SECURITY.md` asks. **Do this before
merging the pull request that adds `SECURITY.md`**: until it is on, the policy, the issue
forms and `security.txt` point to a form that does not exist.

1. Open the repository on GitHub and click **Settings**.
2. In the sidebar's **Security and quality** section, click **Advanced Security**.
3. Next to **Private vulnerability reporting**, click **Enable**.
4. Check it works. Open
   `https://api.github.com/repos/<owner>/<repository>/private-vulnerability-reporting`
   in a browser, where `<owner>/<repository>` is the part of the repository's address
   after `github.com/` (see `REPOSITORY_URL` in `pipeline/project.py`). No sign-in is
   needed. It should show `"enabled": true`. Your own view of the report form is not a
   good check, because as the owner you can open it either way.
5. To get an email when someone reports something: click **Watch** at the top of the
   repository, then **Custom**, tick **Security alerts**, and click **Apply**. Then open
   https://github.com/settings/notifications and, under **Subscriptions**, then
   **Watching**, make sure **Email** is selected.

Source: https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository

## 2. Dependabot alerts and security updates

Warns about known security problems and opens pull requests to fix them. Weekly version
updates for Python packages, GitHub Actions and pre-commit hooks are already set up in
`.github/dependabot.yml`.

GitHub's list of ecosystems its dependency graph reads (checked 8 October 2026) has no
entry for uv, so alerts will probably cover the GitHub Actions but not the Python
packages in `uv.lock`. CI covers that gap: every run checks the locked packages against
known vulnerabilities with pip-audit, and fails if one is found.

1. **Settings > Advanced Security**.
2. Next to **Dependabot alerts**, click **Enable**.
3. Next to **Dependabot security updates**, click **Enable**.
4. After a day, look at **Insights > Dependency graph**. If it lists the Python
   packages from `uv.lock`, alerts cover them too.

Source: https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configure-security-updates

## 3. Secret scanning and push protection

GitHub's own check for keys and passwords, on top of the project's pre-commit scanner.
Push protection blocks a push that contains a known kind of key.

1. **Settings > Advanced Security**.
2. Next to **Secret Protection**, click **Enable**, then **Enable Secret Protection**.
3. In the **Secret Protection** section, next to **Push protection**, click **Enable**.

Source: https://docs.github.com/en/code-security/how-tos/secure-your-secrets/prevent-future-leaks/enable-push-protection

## 4. Code scanning with CodeQL

Looks for security mistakes in the Python code and the GitHub Actions workflows.

1. **Settings > Advanced Security**.
2. Under **Code Security**, next to **CodeQL analysis**, choose **Set up**, then
   **Default**.
3. Click **Enable CodeQL**.

It runs on pull requests, on changes to `main` and once a week.

Source: https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configure-code-scanning

## 5. Read-only workflow permissions

Limits what automated workflows can change. The project's workflow already asks for
read-only access, and new personal repositories usually have this set already.

1. **Settings**, then in the sidebar **Actions > General**.
2. Under **Workflow permissions**, choose the read-only option (read access to contents
   and packages), and click **Save**.
3. Leave **Allow GitHub Actions to create and approve pull requests** unticked.

Source: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository

## 6. Protect the main branch

Makes every change go through a pull request with passing checks, as `CLAUDE.md` asks.

1. **Settings**, then in the sidebar under **Code, planning, and automation**, click
   **Rulesets** (it may show as **Rules**, then **Rulesets**).
2. Click **New ruleset**, then **New branch ruleset**. Give it a name, such as
   "Protect main", and set **Enforcement status** to **Active**.
3. Under **Target branches**, click **Add a target** and choose the default branch
   (`main`).
4. Under **Branch protections**, tick **Require a pull request before merging**. Set the
   number of required approvals to **0**: GitHub does not let you approve your own pull
   request, so any higher number would stop you merging.
5. Tick **Require status checks to pass before merging**, and add the checks
   **Lint, test and scan** and **Map page (build, browser tests, accessibility)**. If you
   set this up before the second check existed, edit the ruleset and add it. (GitHub
   only offers checks it has seen run in the last week, so open a pull request first if
   it is not listed.)
6. Keep **Block force pushes** and **Restrict deletions** ticked, then click **Create**.

The older way also works: **Settings > Branches > Add classic branch protection rule**,
branch name pattern `main`, with the same two options ticked. Also tick **Do not allow
bypassing the above settings**: without it, classic rules do not apply to the repository's
owner, so pushes straight to `main` would still be allowed.

Source: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository

## 7. Labels for the issue forms

The issue forms add the labels `privacy` and `correction`. GitHub leaves out labels that
do not exist yet, so create them once:

1. Open the labels page directly: add `/labels` to the end of the repository's address,
   for example `https://github.com/<owner>/<repository>/labels`. (It can also be reached
   from the **Issues** tab, where the **Labels** button sits next to the search box,
   although newer layouts sometimes hide it.)
2. Click **New label**, name it `privacy`, and click **Create label**.
3. Do the same for `correction`.

## 8. Your account

- Turn on two-factor authentication for your GitHub account if it is not on already
  (**Settings > Password and authentication**, from your profile picture).
- In **Settings > Emails**, keep **Keep my email addresses private** ticked, so commits
  you make on GitHub show a private noreply address. Your commits already do.

## 9. GitHub Pages and the Jolt key

Needed before the first run of the **Fetch daily** workflow (`.github/workflows/`).

1. **Settings > Pages**. Under **Build and deployment**, set **Source** to **GitHub
   Actions**.
2. **Settings > Environments > github-pages** (it appears after step 1). Under
   **Deployment branches and tags**, keep it to `main` only.
3. **Settings > Secrets and variables > Actions > New repository secret**. Name it
   `JOLT_API_KEY` and paste the key from Jolt's own open data page (its address is in
   `operators/jolt.yaml`). Jolt publishes this key, but it is still kept out of the
   repository, as `CLAUDE.md` asks.
4. Open the **Actions** tab, choose **Fetch daily**, and click **Run workflow** on
   `main`. When it finishes, the site's address is shown on the run's summary page.
   From then on it runs every day at 04:17 UTC.

A run shows red if any operator failed, even though the site was still updated with the
others; the feed health page on the site says which one.

To watch a run while it fetches, open it, then the **Fetch operator feeds** job, then the
**Fetch every enabled operator, never two on one host at once** step. Operators on
different hosts are fetched at the same time, so their lines are interleaved; each line
starts with the operator's id. It prints a line as each operator starts and finishes, and every ten pages in between, with the page reached, the
percentage done and an estimate of the time left where the feed gives its total.

Source: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site

## 10. The relay (Cloudflare Workers)

Some operators' servers refuse requests from GitHub's servers; GeniePoint is the first
(see `operators/geniepoint.yaml`). The daily run fetches their files through one small
Cloudflare Worker that you own. The Worker only fetches the files listed in it, only for
requests carrying a secret token, and passes on the project's User-Agent unchanged. Each
operator has its own path on it (for example `/geniepoint/...`), so a later operator only
needs a new path in `relay/worker.js` and a decision in its file, not a new Worker or new
secrets. The free plan allows up to 100 Workers, but one is enough. ADR 0010 explains the
decision.

**Make a token first.** Use your password manager's generator to make a random password of
at least 40 letters and digits, with no spaces. You will paste the same value in two places
(steps 8 and 10). Do not put it anywhere else, such as an issue, a commit or a chat.

Cloudflare builds the Worker from this repository's `relay/` folder (its Git integration),
so each change to `relay/` merged into `main` is deployed without copying code by hand.

1. Sign up for a free Cloudflare account at https://dash.cloudflare.com/sign-up (no card is
   needed for the free Workers plan), and confirm your email address. If Cloudflare asks you
   to choose a workers.dev subdomain, pick a neutral one with no name, place or other
   personal detail in it.
2. In the Cloudflare dashboard, open **Workers & Pages**, select **Create application**,
   then **Get started** next to **Import a repository**.
3. Connect your GitHub account when asked. On GitHub's page for the **Cloudflare Workers
   and Pages** app, choose **Only select repositories** and pick only this repository.
4. Back in Cloudflare, choose this repository. On **Set up your application**, check that
   it shows this repository, then fill in:
   - **Project name**: `oevm-relay` (it must match `name` in `relay/wrangler.toml`, or the
     build fails);
   - **Build command**: leave empty;
   - **Deploy command**: `npx wrangler deploy` (the default);
   - **Preview command**: leave as it is (it only runs for preview builds);
   - **Enable Preview builds**: switch off, so only `main` is ever deployed;
   - **Protect with Cloudflare Access**: leave off (it would put a sign-in page in front of
     the Worker, and the daily run could not get through);
   - under **Advanced settings**, **Path**: `/relay` (the folder the Worker is in);
   - **API token**: leave as **Create new token**. Cloudflare makes this token itself so
     its builds can deploy; it is not the relay token. Leave **API token name** empty
     unless Cloudflare asks for one, then use `oevm-relay-build`;
   - **Variable name** and **Variable value**: leave empty. These are build variables,
     which Cloudflare says "will not be accessible at runtime", so the relay token does
     not go here (it goes in step 7).
   If it asks for a branch, choose `main`. Then select **Deploy**. Note the Worker's
   address, something like `https://oevm-relay.<your-subdomain>.workers.dev`.
5. Open the Worker's **Settings > Build**. Under **Build watch paths**, set the include
   paths to `relay/*`, so other changes to the repository do not start a build. Under
   **Branch control**, check that preview builds are still off.
6. Still in **Settings**, open **Variables and Secrets**.
7. Select **Add**, set **Type** to **Secret** and **Variable name** to `RELAY_TOKEN`.
8. Paste the token as the **Value** and select **Deploy**. Until this is set, the Worker
   refuses every request.
9. In GitHub, open **Settings > Secrets and variables > Actions**. On the **Secrets** tab,
   select **New repository secret**: name `OEVM_RELAY_URL`, value the Worker's address
   from step 4 (starting `https://`, with nothing after `.dev`). It is a secret, not a
   variable, so GitHub hides it in the public run logs.
10. Select **New repository secret** again: name `OEVM_RELAY_TOKEN`, value the same token
    as in step 8.
11. Open the **Actions** tab, choose **Fetch daily** and select **Run workflow** on `main`.
    The run's log shows whether GeniePoint came through.

Cloudflare's app posts a build result on commits and pull requests that change `relay/`.
Menu names in Cloudflare's dashboard change from time to time; if a label differs, look
for the nearest match. To stop using the relay, delete **both** GitHub secrets,
`OEVM_RELAY_URL` and `OEVM_RELAY_TOKEN`: the daily run then asks GeniePoint directly again.
Deleting only one stops GeniePoint's fetch with a message saying which is missing, on
purpose, so a half-finished setup is noticed. To stop Cloudflare deploying from the
repository, use **Disconnect** in the Worker's build settings.

Sources: https://developers.cloudflare.com/workers/ci-cd/builds/ (with its configuration,
build branches, build watch paths and GitHub integration pages) and
https://developers.cloudflare.com/workers/configuration/secrets/, read 8 October 2026,
and the **Set up your application** form as it appeared on the same day.

## Later: security.txt on the website

`site/.well-known/security.txt` only counts as a security contact when it is served from
the top of a domain, at `https://<domain>/.well-known/security.txt` (RFC 9116). A GitHub
Pages project site lives at `https://<user>.github.io/OEVM/`, so the file would not be at
the top. Now that the site is published by a workflow (blueprint task 10):

- use a custom domain for the site, or put a copy in a separate `<user>.github.io`
  repository; and
- the deploy workflow already uses `actions/upload-pages-artifact@v5` with
  `include-hidden-files: true`, so `.well-known` is published.
