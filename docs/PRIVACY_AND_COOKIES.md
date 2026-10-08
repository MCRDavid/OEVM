# Privacy and cookies

General information, not legal advice. Checked against the legislation on 7 October 2026.
The map page (`site/index.html`, blueprint task 9) is built to these rules but is not
deployed yet. This page sets out the rules, what the page does today and the notice it
will show.

## The law in short

UK cookie law is regulation 6 of the Privacy and Electronic Communications (EC Directive)
Regulations 2003 (PECR). The Data (Use and Access) Act 2025 replaced regulation 6 and
added Schedule A1 from 5 February 2026.

- Regulation 6(1): a person "must not store information, or gain access to information
  stored, in the terminal equipment of a subscriber or user", unless Schedule A1 allows
  it. This covers cookies and also browser storage such as `localStorage`.
- Schedule A1 allows storage or access in these cases relevant to this project:
  - **Consent** (paragraph 2): the visitor is given "clear and comprehensive information"
    about the purpose and gives consent.
  - **Strictly necessary** (paragraph 4): needed to provide a service the visitor asked
    for. Its examples include "maintaining a record of selections made on a website, or
    information put into a website". No consent or notice is required.
  - **Statistics** (paragraph 5): counting how the site is used to improve it, if the
    information is not shared except to help with that, the visitor gets clear
    information, and the visitor has "a simple means of objecting, free of charge".
  - **Appearance and functions** (paragraph 6): adapting how the site looks or works to
    the visitor's preferences, with the same clear information and simple, free way to
    object.
- UK GDPR still applies to any personal data, such as the IP addresses that web hosts
  see.

Sources:
- Regulation 6: https://www.legislation.gov.uk/uksi/2003/2426/regulation/6
- Schedule A1: https://www.legislation.gov.uk/uksi/2003/2426/schedule/A1

The ICO's guidance on the amended rules was not reviewed for this note. Read it before
the site goes live.

## Rules for the site

1. **No tracking.** No analytics, advertising, tracking pixels, social media embeds or
   fingerprinting. (The blueprint already rules out analytics.)
2. **No third-party files that track.** Check every external font, map style, tile
   server or script before adding it, and record whether it sets cookies or uses storage.
   Prefer self-hosted files. Checked so far:
   - **MapLibre GL JS** (the version pinned in `package.json`): served from the site
     itself, not from a script host. No telemetry was found in 6.11.2's source, nor in
     6.12.0's bundles (searched 8 October 2026). Search again after major updates.
   - **OpenFreeMap** (`tiles.openfreemap.org`, Liberty style): the only outside host the
     page contacts. Header checks on 8 October 2026 saw no cookies and no storage. The
     responses carry Cloudflare's Network Error Logging (NEL) headers, which ask some
     browsers to keep a reporting policy and to report failed connections to
     `a.nel.cloudflare.com`. This site does not control that. **Decided by the
     repository owner on 8 October 2026:** acceptable, on condition that the privacy
     notice below and the page footer say so. If that changes, the fallback is a
     self-hosted basemap (ADR 0008).
3. **Prefer the address bar.** Settings carried in the page address (for example
   `?free=1&plug=ccs`) store nothing on the device.
4. **Saving settings is opt-in.** Settings are saved to the device only after the visitor
   turns on "Remember my settings on this device", which is off by default. A short
   explanation sits beside the switch, and "Forget my settings" deletes everything saved.
   This gives consent under paragraph 2 and also meets paragraph 6. Today only the
   filters are saved, under one `localStorage` key (`oevm.settings.v1`). Favourites and a
   home location are not built yet; they must follow this rule when they are.
5. **Saved settings stay on the device.** The site never sends them anywhere. The map
   still fetches map files for the area on screen (see the notice below), so a saved home
   location, if one is added, would be visible to the map host as an area on every visit.
   Do not open the map at a saved location without saying so in the notice.
6. **No cookie banner is needed while rules 1 to 5 hold**, because nothing optional is
   stored until the visitor asks for it. Check what the hosting service itself stores when
   the site is deployed, and update this page if it stores anything.
7. **Any new storage needs review first.** Check it against Schedule A1 and update this
   page before it ships. Paragraph 4 must not be stretched to cover storage the visitor
   did not ask for.
8. **Every page links to the privacy and cookies notice**, the disclaimer, the data
   sources and the security policy.
9. **Privacy questions go through GitHub.** The "Privacy question" issue form warns that
   issues are public. Anything involving personal data that should not be public goes
   through GitHub's private vulnerability reporting instead (see `SECURITY.md`).

## Notice for the site

To be published with the site. Check each statement against the deployed site first,
and fill in the date.

> **Privacy and cookies**
>
> This site has no accounts, no analytics and no advertising. It does not collect your
> personal data.
>
> **What is saved on your device.** Nothing, unless you turn on "Remember my settings on
> this device". If you do, your filters are saved in your browser's local storage so the
> map opens the same way next time. They are not sent anywhere. Turn the switch off or
> press "Forget my settings" at any time to delete them. Your browser may also keep copies
> of the site's files and map files in its normal cache, as it does for any website. When
> the map loads, Cloudflare, which delivers OpenFreeMap's map files, may also ask your
> browser to keep a small instruction to report failed connections to it (Network Error
> Logging). The headers checked on 8 October 2026 asked browsers to keep it for up to 7
> days. This site does not set or control it.
>
> **Links you share.** When you change a filter, your filters appear in the page address,
> and the map's position appears after the # sign, so you can bookmark or share them.
> Filters you saved on this device are not added to the address until you change one. Anyone you send
> that link to can see those settings and the area you were looking at. The page tells
> browsers to send only the site's address, not the full page address, with the requests
> it makes.
>
> **Who else sees your visit.** This site is hosted by GitHub Pages. The background map
> comes from OpenFreeMap (tiles.openfreemap.org), a free service delivered through
> Cloudflare. To draw the map, your browser asks OpenFreeMap for the map files covering
> the area on your screen. Like any web server, it receives your IP address, the address
> of this site (not your filters) and basic browser details, and it can tell roughly which
> area you are looking at. OpenFreeMap says it does not use cookies and does not keep IP
> addresses in its access logs. When we checked on 8 October 2026, none of its map files
> set a cookie. The map service also asks some browsers to report failed connections to
> Cloudflare (a.nel.cloudflare.com). This is a browser feature called Network Error
> Logging, and this site does not control it. Privacy notices: GitHub
> (https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement),
> OpenFreeMap (https://openfreemap.org/privacy/), Cloudflare
> (https://www.cloudflare.com/privacypolicy/).
>
> **Contact.** Open an issue on GitHub using the "Privacy question" form. Issues are
> public, so please do not include personal information. If your question involves
> personal data that should not be public, report it privately with the "Report a
> vulnerability" button on the repository's Security and quality tab (called Security on
> older pages). Both routes need a GitHub account.
>
> Last updated: [date of publishing].

The OpenFreeMap statements come from its privacy page and response headers as read on
8 October 2026 (ADR 0008). Re-check them before publishing and from time to time, because
the service can change without notice.
