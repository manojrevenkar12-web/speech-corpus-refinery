# ScrBot

ScrBot is the crawler of [speech-corpus-refinery](../README.md). It looks for recordings of read
speech that their publishers have released under open licences, so they can become
text-to-speech training data. This page is what its user agent links to.

```
ScrBot/0.1 (+https://github.com/manojrevenkar12-web/speech-corpus-refinery/blob/main/docs/CRAWLER.md)
```

## To keep ScrBot out

Any of these works, and each is checked before anything is downloaded:

- **robots.txt**, product token `ScrBot` ([RFC 9309](https://www.rfc-editor.org/rfc/rfc9309)).
  A group for `ScrBot` replaces the `*` group. The longest matching rule wins, and `Allow` wins a
  tie. `Crawl-delay` is honoured when it is longer than our own minimum. If robots.txt answers
  with a server error, ScrBot stays out of the whole site until it can read it.
  ```
  User-agent: ScrBot
  Disallow: /
  ```
- **TDMRep** ([W3C TDM Reservation Protocol](https://www.w3.org/community/reports/tdmrep/CG-FINAL-tdmrep-20220216/)),
  in any of its three places:
  - `/.well-known/tdmrep.json` rules: matching paths are never requested;
  - a `tdm-reservation: 1` response header: the body is not read or kept;
  - `<meta name="tdm-reservation" content="1">`: the page is not used, so audio linked only from
    it is never found.
- **A takedown request** (below): the URL or domain is never crawled again.

## How it behaves

- One request at a time per host, at least 1 second apart.
- robots.txt is re-read at least every 24 hours.
- `429` and `503` responses are retried after the `Retry-After` the server gives, otherwise
  after 5, 30 and 120 seconds, and at most 4 times. Redirects count against the same per-host
  pacing, at most 5 per URL.
- Files over 200 MiB are not downloaded. JavaScript is not run, forms are not submitted and
  logins are not attempted.
- Domains on our piracy blocklist are never contacted, not even for robots.txt, as the
  [GPAI Code of Practice](https://digital-strategy.ec.europa.eu/en/policies/gpai-code-practice)
  copyright chapter asks.
- Each request is logged with the URL, status, size and content hash. The audio is kept only if
  its licence allows training: public domain, CC0, the Public Domain Mark, CC BY or CC BY-SA.
- In production every request leaves from one static address, the Cloud NAT address in
  `infra/terraform` (`crawler_egress_ip`), so you can recognise or block it.

The full rules are in the [data policy](POLICY.md).

## Removal requests

Rights holders and speakers can ask for removal by URL, domain, recording or voice. Open an issue
on the repository, marked "takedown". A removal:

- withdraws the recordings and deletes their stored audio;
- lists the dataset releases that contained them, so anyone who trained on those can be told;
- stops future crawling of the URL or domain;
- rejects future copies by audio fingerprint, and new recordings in a removed voice by speaker
  embedding.
