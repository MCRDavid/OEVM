# Privacy and cookies

General information, not legal advice. Checked against the legislation on 7 October 2026.
There is no website yet (blueprint task 9). These are the rules it must be built to, and
a draft of the notice it must show.

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
   Prefer self-hosted files.
3. **Prefer the address bar.** Settings carried in the page address (for example
   `?free=1&connector=ccs`) store nothing on the device.
4. **Saving settings is opt-in.** Filters, favourites and a home location are saved to the
   device only after the visitor turns on "Remember my settings on this device", which is
   off by default. A short explanation sits beside the switch, and "Forget my settings"
   deletes everything saved. This gives consent under paragraph 2 and also meets
   paragraph 6.
5. **Nothing leaves the device.** Saved settings stay in the browser. The site never sends
   them anywhere.
6. **No cookie banner is needed while rules 1 to 5 hold**, because nothing optional is
   stored until the visitor asks for it. Check what the hosting service itself stores when
   the site is deployed, and update this page if it stores anything.
7. **Any new storage needs review first.** Check it against Schedule A1 and update this
   page before it ships. Paragraph 4 must not be stretched to cover storage the visitor
   did not ask for.
8. **Every page links to the privacy and cookies notice**, the disclaimer and the data
   sources.

## Draft notice for the site

Finish the parts in square brackets when the site is built.

> **Privacy and cookies**
>
> This site has no accounts, no analytics and no advertising. It does not collect your
> personal data.
>
> **What is saved on your device.** Nothing, unless you turn on "Remember my settings on
> this device". If you do, your filters, favourites and home location are saved in your
> browser's local storage so the map opens the same way next time. They never leave your
> device. Turn the switch off or press "Forget my settings" at any time to delete them.
>
> **Links you share.** Your current filters can appear in the page address so you can
> bookmark or share them. Anyone you send that link to can see those settings.
>
> **Who else sees your visit.** This site is hosted by [hosting provider]. Map images come
> from [map provider]. Like any web server, they receive your IP address and basic
> browser details when your browser asks them for files. Their privacy notices: [links].
>
> **Contact.** [Contact route to be decided, for example a GitHub issue.]
>
> Last updated: [date].
