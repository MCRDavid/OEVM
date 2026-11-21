"""Facts about this project that are used in more than one place.

If the repository moves, for example to a different GitHub account, change
REPOSITORY_URL here and the Contact and Policy lines in site/.well-known/security.txt.
A test checks that the two agree. The relay's timer and the OCPI handshake Worker copy the
URL too (relay/worker.js, and the User-Agent in ocpi/worker.js); tests check both.

SITE_URL is where the site is published. Search engines and link previews are given it as
each page's address (pipeline/seo.py). If the site moves, for example to its own domain,
change it here and in the head of site/index.html; a test checks that the two agree. The
OCPI handshake Worker gives operators the same address (website in ocpi/worker.js).
"""

NAME = "OEVM"
VERSION = "0.1"
REPOSITORY_URL = "https://github.com/MCRDavid/OEVM"
SITE_URL = "https://mcrdavid.github.io/OEVM/"
