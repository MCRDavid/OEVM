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
   From then on it runs every day: the relay Worker's timer starts it at 04:17 UTC once
   section 10's steps 12 to 16 are done, and GitHub's own schedule is a backup.

If an operator fails, the site is still updated with the others, and the map keeps
showing the failed operator's last good copy (up to 7 days old) with its own fetch date
(ADR 0018). The run then stays green with a warning. It shows red only when an operator
failed and had no last good copy to show, so it is missing from the map. Either way, the
feed health page on the site says which one.

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
secrets. The free plan allows up to 100 Workers, but one is enough for every relayed operator.
(Section 11's Worker is separate on purpose, because it holds an operator's token.) ADR 0010
explains the decision.

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

### The timer that starts Fetch daily

GitHub's own schedule started Fetch daily six to seven hours late in October 2026, or not
at all, so the relay Worker also has a timer (ADR 0024). At 04:17 UTC, and again at 06:17
UTC, it asks GitHub to start Fetch daily. Only the first run each day fetches; later ones
stop within a minute. The timer needs a GitHub token of its own:

12. On GitHub, select your profile picture, then **Settings > Developer settings >
    Personal access tokens > Fine-grained tokens > Generate new token**. Fill in:
    - **Token name**: `oevm-relay-timer`;
    - **Resource owner**: your account;
    - **Expiration**: a date up to a year ahead. Put a reminder in your calendar a week
      before it (step 16);
    - **Repository access**: **Only select repositories**, and pick this repository only;
    - **Permissions**: under **Repository permissions**, set **Actions** to **Read and
      write**. GitHub adds **Metadata: Read-only** by itself. Leave everything else at
      **No access**.
    Select **Generate token** and copy it. Do not paste it anywhere but step 13.
13. In the Cloudflare dashboard, open the `oevm-relay` Worker, then **Settings > Variables
    and Secrets > Add**. Set **Type** to **Secret**, **Variable name** to
    `GITHUB_DISPATCH_TOKEN`, paste the token as the **Value**, and select **Deploy**.
14. Merge the pull request that adds the timer. Cloudflare deploys `relay/` with its two
    Cron Triggers, which can take up to 15 minutes to take effect. The Worker's
    **Settings** then list them under **Trigger events** (or the nearest match) as
    `17 4 * * *` and `17 6 * * *`.
15. The next morning, the **Actions** tab shows a run named **Fetch daily (Cloudflare
    timer)** that started at about 04:17 UTC. Runs named **Fetch daily (GitHub schedule
    ...)** later that day finish within a minute without fetching. The feed health page's
    "How the daily fetch started" section shows the same. If no timer run appears, the
    Worker's Cron Events say why: HTTP 401 means the token is wrong or has expired; 403 or
    404 means it lacks **Actions: Read and write** on this repository.
16. Before the token expires, open it on GitHub (step 12's page), select **Regenerate
    token**, and replace the secret's value in Cloudflare (step 13). Until you do, GitHub's
    schedule still starts the fetch, only later in the day.

To stop the timer, delete the `GITHUB_DISPATCH_TOKEN` secret in Cloudflare and the token on
GitHub; GitHub's schedule carries on.

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
For the timer: https://developers.cloudflare.com/workers/configuration/cron-triggers/,
https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
and https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event,
read 12 October 2026.

## 11. The OCPI handshake Worker (Cloudflare Workers)

Tesla offers its data through an OCPI 2.2.1 connection that Tesla's servers start by calling
this project: they read the project's OCPI versions, send Tesla's own token and wait for an
answer (see `operators/tesla.yaml`). A second small Cloudflare Worker that you own answers
those calls. It is separate from the relay, with its own folder (`ocpi/`), name, build
settings and secrets, and it only does the handshake: the daily run will fetch Tesla's data
itself, and Tesla stays switched off until its terms have been read. ADR 0025 explains the
decision.

**Do this only after** ADR 0025 is accepted and the pull request that adds `ocpi/` is merged.
Tesla's form asks for the Worker's address, so the Worker must be working before you fill the
form in.

**Make two tokens first.** Use your password manager's generator to make two different random
passwords of 40 to 64 letters and digits, with no spaces (OCPI tokens may be at most 64
characters, and the Worker ignores a token shorter than 32). Save both in your password
manager:

- the **connection token**, which goes in step 7 and in Tesla's form in step 10;
- the **pull token**, which goes in step 8, and later in a GitHub secret when the daily run
  learns to read the Worker (that pull request adds its steps here).

Do not reuse the relay's token. Do not put either token anywhere else, such as an issue, a
commit or a chat.

Cloudflare builds this Worker from the repository's `ocpi/` folder, so each change to `ocpi/`
merged into `main` is deployed without copying code by hand.

1. Check that two-factor authentication is on for your Cloudflare account: open **My
   Profile**, then **Authentication**. Anyone who can sign in to the account, or merge a change
   to `ocpi/` into `main`, could read the token Tesla sends.
2. In the Cloudflare dashboard, open **Workers & Pages**, select **Create application**, then
   **Get started** next to **Import a repository**, and choose this repository. The
   **Cloudflare Workers and Pages** app already has access to it from section 10, step 3; if
   GitHub asks again, keep **Only select repositories** with only this repository.
3. On **Set up your application**, check that it shows this repository, then fill in:
   - **Project name**: `oevm-ocpi` (it must match `name` in `ocpi/wrangler.toml`, or the build
     fails). Never put an operator's name in it;
   - **Build command**: leave empty;
   - **Deploy command**: `npx wrangler deploy` (the default);
   - **Preview command**: leave as it is (it only runs for preview builds);
   - **Enable Preview builds**: switch off, so only `main` is ever deployed;
   - **Protect with Cloudflare Access**: leave off (Tesla's servers could not get past a
     sign-in page);
   - under **Advanced settings**, **Path**: `/ocpi` (the folder the Worker is in);
   - **API token**: leave as **Create new token**. Cloudflare makes this token itself so its
     builds can deploy; it is neither of your tokens. Leave **API token name** empty unless
     Cloudflare asks for one, then use `oevm-ocpi-build`;
   - **Variable name** and **Variable value**: leave empty. These are build variables, and
     neither token goes here.
   If it asks for a branch, choose `main`. Then select **Deploy**. Note the Worker's address,
   something like `https://oevm-ocpi.<your-subdomain>.workers.dev`. Keep the address out of
   issues and commits too: anyone's requests to it count against the free plan's daily
   allowance, which the relay shares.
4. Open the Worker's **Settings > Build**. Under **Build watch paths**, set the include paths
   to `ocpi/*`, so other changes to the repository do not start a build. Under **Branch
   control**, check that preview builds are still off. Open the first build's log and check
   that it created the `OcpiConnection` class and shows no warning about
   `enable_request_signal`.
5. Still in **Settings**, check that **Domains & Routes** lists only the `workers.dev` address
   (no custom domain or route), that no Cron Trigger is listed, and that logs are off.
   `ocpi/wrangler.toml` sets all three; if the dashboard shows logs on, find the nearest match
   to **Observability** and turn them off.
6. Still in **Settings**, open **Variables and Secrets**.
7. Select **Add**, set **Type** to **Secret** and **Variable name** to `OCPI_TOKEN_A`, paste the
   connection token as the **Value** and select **Deploy**.
8. Select **Add** again, set **Type** to **Secret** and **Variable name** to `OCPI_PULL_TOKEN`,
   paste the pull token as the **Value** and select **Deploy**. Until each secret is set, the
   Worker refuses every request that would need it.
9. Check the Worker from a terminal, with your subdomain in place of `<your-subdomain>`. First,
   without a token:

   ```bash
   curl -sS -o /dev/null -w "%{http_code}\n" https://oevm-ocpi.<your-subdomain>.workers.dev/ocpi/versions
   ```

   It should print `401`. The same command for `/oevm/connection` should print `403`, and for
   `/` it should print `404`. Then with the connection token. The command waits for you to
   paste the token and press Enter; nothing shows, and the token goes to curl on its standard
   input, not on the command line:

   ```bash
   read -rs T && printf 'Authorization: Token %s\n' "$T" | curl -sS -H @- https://oevm-ocpi.<your-subdomain>.workers.dev/ocpi/versions; unset T; echo
   ```

   It should print a reply containing `"version":"2.2.1"` and `"status_code":1000`. Then with
   the pull token. This command never prints Tesla's token, even after Tesla has connected:

   ```bash
   read -rs T && printf 'X-Pull-Token: %s\n' "$T" | curl -sS -H @- https://oevm-ocpi.<your-subdomain>.workers.dev/oevm/connection | python3 -c 'import json, sys; d = json.load(sys.stdin); d.pop("token", None); print(json.dumps(d, indent=2))'; unset T
   ```

   It should show `"state": "unregistered"`. If any check shows something else, or `"Not
   allowed."`, stop: set the secret again as typed, and do not fill in Tesla's form until every
   check passes. Use **Disconnect** in the Worker's build settings if anything else is wrong.
10. Only now, sign in to Tesla's developer portal and open its **Charging OCPI Connection** form
    (https://developer.tesla.com/en_GB/dashboard/charging/roaming/connection). Fill in:
    - **Connection Scope**: **UK**;
    - **Token**: the connection token, pasted from your password manager;
    - **Role**: **NSP**;
    - **URL**: `https://oevm-ocpi.<your-subdomain>.workers.dev/ocpi/versions`, with no slash at
      the end, so it matches the address in every reply the Worker sends;
    - **Party ID**: exactly the `party_id` in `PARTY` in `ocpi/worker.js` (three capital
      letters from the project's name). Not `TES`, the form's own example, and never your
      initials.
    Then select **Submit**. Tesla reviews each request and its portal is open by invitation
    only, so it may refuse or not answer; that is a reply to record, not a fault. The form is
    sent from your own Tesla Account, so Tesla will know who asked; nothing about the account
    goes in the repository.
11. The same day, record the request in `operators/tesla.yaml`, in a pull request like any
    change: add this step at the end of `engagement.log`, set `access_requested` to the same
    date and `engagement.status` to `requested_no_reply`, then run
    `uv run python -m pipeline.registry --validate` and `uv run python -m pipeline.transparency`.
    Never write the Worker's address or either token in the file.

    ```yaml
        - date: <YYYY-MM-DD>
          action: request_sent
          channel: web_form
          summary: >-
            The repository owner submitted Tesla's Charging OCPI Connection form with a UK
            scope, the NSP role, a three-letter party ID and the address of the project's OCPI
            versions endpoint, for Tesla to review.
          evidence_url: https://developer.tesla.com/en_GB/dashboard/charging/roaming/connection
    ```

    Record Tesla's answer the same way when it comes (see `operators/_template.yaml`).
12. To see whether Tesla has called, run the last command from step 9 again, with the pull
    token. It shows:
    - `"state"`: `"registered"` once Tesla has connected, `"handshake_in_progress"` while Tesla
      is connecting, or `"ended"` if Tesla ended the connection;
    - `"last_contact"`: when Tesla last called each address, with which kind of token
      (`"setup"` is the connection token, `"retired"` a connection token already used and
      `"peer"` the token the Worker gave Tesla), in which form, and whether it sent request
      IDs. Your
      own check in step 9 with the connection token shows here too, as `"GET /ocpi/versions"`
      with `"who": "setup"`, `"form": "plain"` and `"request_ids": false`, at the time you ran
      it (times are in UTC), until Tesla calls that address. So only entries dated after you
      submitted Tesla's form can be Tesla's. If it shows Tesla reading `/ocpi/2.2.1` but never
      a `POST`, Tesla did not like the Worker's answer; see "Needs testing" in ADR 0025;
    - `"last_handshake"`: the result of Tesla's last attempt. `1000` is success, `2001` means
      Tesla's request was not usable, `3001` that the Worker could not use Tesla's addresses
      or ran out of time (the message says why), `3002` that Tesla offers no version 2.2.1,
      `3003` that it offers no locations, and `3000` an unexpected error in the Worker;
    - `"handouts"`: how many times the Worker has handed Tesla's token to anyone with the pull
      token (once Tesla has connected, your own checks count too).

    As soon as it says `"registered"`, delete `OCPI_TOKEN_A` in **Settings > Variables and
    Secrets**. For 10 minutes after Tesla first registers with it, and until Tesla uses the new
    token the Worker gave it, the connection token can still register again, even after you
    delete the secret, so that Tesla can retry if it lost the answer (D7 in ADR 0025); a retry
    does not add time. After that the Worker refuses it, but only while its stored record
    survives, so deleting the secret still matters. Then, in a pull request, record the host
    of Tesla's `locations_url` (the host only, never the address or a token) in
    `operators/tesla.yaml` with the date and the source "the operator's credentials POST"; the
    daily run will use only addresses on that host (D8 in ADR 0025). If Tesla asks that its
    host not be published, stop and decide before recording anything.

If Tesla says it never received an answer to its registration, it can simply try again within
10 minutes of its first registration (D7 in ADR 0025). After that, set a new connection token
as `OCPI_TOKEN_A` (step 7) and fill in Tesla's form again with it; the Worker replaces the old
connection when Tesla registers (D6). If Tesla ever ends the connection, connecting again also
needs a new connection token and the form again.

Do not change the Worker's secrets while the command shows `"handshake_in_progress"`: each
change is a new deployment and restarts the Worker.

To stop answering Tesla, use **Disconnect** in the Worker's build settings, then delete the
Worker. Whether deleting the Worker also deletes the token Tesla sent at once, or Cloudflare
keeps it for its 30-day recovery window, needs checking; ask Tesla to end the connection too.
Menu names in Cloudflare's dashboard change from time to time; if a label differs, look for the
nearest match.

Sources: the relay's sources above (Cloudflare's builds and secrets pages, read 8 October 2026,
and the **Set up your application** form as it appeared that day);
https://developers.cloudflare.com/workers/platform/limits/ and
https://developers.cloudflare.com/durable-objects/platform/pricing/, read 15, 16 and 17 October
2026; https://developers.cloudflare.com/fundamentals/user-profiles/2fa/, read 16 October 2026;
curl's `--header` option (`@-` reads headers from standard input, curl 7.55.0 or later); and
Tesla's connection form as the repository owner read it on 13 October 2026.

## Later: security.txt on the website

`site/.well-known/security.txt` only counts as a security contact when it is served from
the top of a domain, at `https://<domain>/.well-known/security.txt` (RFC 9116). A GitHub
Pages project site lives at `https://<user>.github.io/OEVM/`, so the file would not be at
the top. Now that the site is published by a workflow (blueprint task 10):

- use a custom domain for the site, or put a copy in a separate `<user>.github.io`
  repository; and
- the deploy workflow already uses `actions/upload-pages-artifact@v5` with
  `include-hidden-files: true`, so `.well-known` is published.
