# 2. Rights are checked before bytes are fetched, and again before audio is decoded

## Decision

The checks run in this order, and each stops everything after it:

1. Blocked domain: never contacted, not even for robots.txt.
2. Takedowns: never crawled again.
3. robots.txt for `ScrBot`, under RFC 9309.
4. TDMRep `tdmrep.json`, before any request.
5. The TDMRep header: the body is not read.
6. The TDMRep meta tag: the page is not used.
7. The licence the source states for the file, and any declaration that it is AI-generated.
   Both are decided before the audio is decoded.

## Why

- An opt-out that is honoured after the download is not honoured. The evaluation does not trust
  the crawler's own account of this: it checks the test server's request log, and requires zero
  requests to blocked, disallowed or `tdmrep.json`-reserved paths.
- The EU AI Act's Article 53(1)(c) requires a copyright policy that identifies and respects
  reservations of rights. The GPAI Code of Practice names robots.txt, and machine-readable
  protocols such as TDMRep, as the ways to do that.
- Deciding the licence before decoding means an unusable file costs no CPU. The cost report
  shows the policy stage at zero CPU seconds.

## Consequences

- A licence stated in an unusual way, such as `PDM-1.0` instead of the Public Domain Mark's URL
  or `CC-PDM-1.0`, is rejected as unusable rather than guessed at. Held-out set3 has one such
  file (heldout/set3/NOTES.md).
