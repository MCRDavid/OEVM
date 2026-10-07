# GitHub settings to switch on

These settings live in the repository's settings on GitHub, not in its files, so they must
be switched on by hand. Menu names are as GitHub's documentation gave them on 7 October
2026. GitHub renamed several in 2026, so your screen may differ slightly:

- the repository's **Security** tab is now called **Security and quality**;
- in **Settings**, the security page is called **Advanced Security** (older pages call it
  **Code security** or **Code security and analysis**).

All of these are free for public repositories.

## 1. Private vulnerability reporting

Lets people report security problems privately, as `SECURITY.md` asks.

1. Open the repository on GitHub and click **Settings**.
2. In the sidebar's **Security and quality** section, click **Advanced Security**.
3. Next to **Private vulnerability reporting**, click **Enable**.
4. Check it works: open
   https://github.com/MCRDavid/OEVM/security/advisories/new. You should see a "Report a
   vulnerability" form. If you do not, tell Claude, because that address is used in
   `site/.well-known/security.txt` and the issue forms and could not be checked from the
   cloud session.
5. To get an email when someone reports something: click **Watch** at the top of the
   repository, then **Custom**, tick **Security alerts**, and click **Apply**.

Source: https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository

## 2. Dependabot alerts and security updates

Warns about known security problems in the packages the project uses and opens pull
requests to fix them. Weekly version updates are already set up in
`.github/dependabot.yml`.

1. **Settings > Advanced Security**.
2. Next to **Dependabot alerts**, click **Enable**.
3. Next to **Dependabot security updates**, click **Enable**.
4. After a day, check **Insights > Dependency graph** lists the Python packages from
   `uv.lock`. GitHub's documentation is unclear on whether security alerts cover
   `uv.lock` yet.

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
5. Tick **Require status checks to pass before merging**, and add the check
   **Lint, test and scan**.
6. Keep **Block force pushes** and **Restrict deletions** ticked, then click **Create**.

The older way also works: **Settings > Branches > Add classic branch protection rule**,
branch name pattern `main`, with the same two options ticked.

Source: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository

## 7. Your account

- Turn on two-factor authentication for your GitHub account if it is not on already
  (**Settings > Password and authentication**, from your profile picture).
- In **Settings > Emails**, keep **Keep my email addresses private** ticked, so commits
  you make on GitHub show a private noreply address. Your commits already do.

## Later: security.txt on the website

`site/.well-known/security.txt` only counts as a security contact when it is served from
the top of a domain, at `https://<domain>/.well-known/security.txt` (RFC 9116). A GitHub
Pages project site lives at `https://<user>.github.io/OEVM/`, so the file would not be at
the top. When the site is set up (blueprint task 10):

- use a custom domain for the site, or put a copy in a separate `<user>.github.io`
  repository; and
- if the site is published with GitHub Actions, use `actions/upload-pages-artifact@v5`
  with `include-hidden-files: true`. Earlier versions leave out folders that start with a
  dot, such as `.well-known`.
