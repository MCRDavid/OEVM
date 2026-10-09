# 0011: Engagement log for access requests

Date: 2026-10-09. Status: accepted.

Blueprint Phase 2: access requests and an engagement log, done when every known operator
has a dated status. Until now each operator file held one engagement status with
evidence links, and two summary dates (`access_requested`, `access_granted`) that nothing
filled in.

## Decisions

- **The log lives in the operator file** as `engagement.log`: a list of dated steps,
  oldest first. Each step has an action (`page_checked`, `feed_searched`, `request_sent`,
  `follow_up_sent`, `reply_received`, `agreement_offered`, `key_granted`,
  `request_declined`), a channel where something was sent or received, one neutral
  sentence, and optionally the operator's own words and a link or saved copy. Recording a
  step is a pull request editing YAML, as the blueprint's "no login" section describes.
- **A status is dated by its latest evidence or log entry.** The transparency page shows
  it "as of" that date, or says there is no dated check yet. Builds stay reproducible:
  nothing depends on the day the page is built.
- **Dates, never day counts.** The page shows when access was first requested, the
  latest request or follow-up, and the operator's latest response with its date (or
  "None recorded"), rather than "no reply after N days". The owner chose plain dates on
  9 October 2026, so the page states only what happened and when. A new status,
  `requested_awaiting_decision`, covers a reply that does not yet grant or refuse access.
- **The registry enforces consistency:** the status must match the log (no "no reply"
  after a recorded reply; a decline needs a recorded decline with the operator's words);
  sent steps need a channel; replies, agreements, keys and declines need evidence; and
  `access_requested` and `access_granted` must equal the first request and first key in
  the log. Text is checked for neutral wording and rejected if it holds an email address.
- **Saved copies go in `evidence/<operator id>/`** with names and contact details removed
  (`evidence/README.md`). The loader checks every referenced file exists.
- **The validator prompts follow-ups:** `pipeline.registry --validate` warns about
  operators with no dated status and about requests with no reply after 14 days.
- **Right of reply:** the page invites operators to correct or reply to an entry through
  an issue, and replies are added to the log (blueprint section 3, defamation basics).

## Dated on 2026-10-09

InstaVolt and ubitricity pages were read and logged. ubitricity's page offers a request
form but names no key, licence or agreement, so its status stays "Not yet established"
until a request shows what is issued. Web searches for Pod and Go Zero open data pages found
none, recorded as `feed_searched` with the method stated. bp pulse's page answered an
automated fetch with HTTP 403, and Shell Recharge's pages showed no readable text, so
bp pulse, Shell Recharge and Community by Shell Recharge still need a check in a browser.

## Needs testing

- Whether ubitricity's form also covers Community by Shell Recharge or Shell Recharge.
