"""Facts about this project that are used in more than one place.

If the repository moves, for example to a different GitHub account, change
REPOSITORY_URL here and the Contact and Policy lines in site/.well-known/security.txt.
A test checks that the two agree. The relay's timer and the OCPI handshake Worker copy the
URL too (relay/worker.js, and the User-Agent in ocpi/worker.js); tests check both.
"""

NAME = "OEVM"
VERSION = "0.1"
REPOSITORY_URL = "https://github.com/MCRDavid/OEVM"
