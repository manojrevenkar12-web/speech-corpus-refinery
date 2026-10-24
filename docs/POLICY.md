# Data policy

What the refinery may collect, and what it may put into text-to-speech training data. This is
the policy in plain words; `config/rights.yaml` and `config/settings.yaml` hold the same rules
as data.

## What we never fetch

- **Blocked domains.** Domains on the blocklist are never contacted, not even for robots.txt.
  The blocklist holds piracy-focused domains, as the GPAI Code of Practice requires.
- **What robots.txt disallows** for our crawler (product token `ScrBot`, RFC 9309 rules:
  longest matching path wins, `Allow` wins ties, our group replaces `*`).
- **What a site reserves under TDMRep:**
  - rules in `/.well-known/tdmrep.json` stop the request before it is made;
  - a `tdm-reservation: 1` response header means the body is not read or kept;
  - a `<meta name="tdm-reservation" content="1">` tag means the page is not used, so audio
    linked only from that page is never discovered.
- **What a takedown covers:** the URL or domain is never crawled again.

## What may train a model

- **Licence.** Public domain, CC0, the Public Domain Mark, CC BY and CC BY-SA (3.0 and 4.0).
  Attribution is recorded and published with each release.
  - Not usable: non-commercial (NC), no-derivatives (ND), all rights reserved, or no licence
    stated.
  - The licence is what the source states for that file: a schema.org `license` on the audio,
    a `<podcast:license>` in the feed, the Internet Archive item's `licenseurl`, LibriVox's
    public-domain dedication, or the page's `rel="license"` link.
- **No synthetic speech.**
  - Audio the source declares AI-generated is rejected. The declaration is the IPTC digital
    source type `trainedAlgorithmicMedia` in schema.org.
  - Audio that merely sounds synthetic is *held* for a person to review; it is not released
    until cleared.
- **Not our evaluation recordings.** Our TTS evaluation set (LJSpeech LJ001-0017 to
  LJ001-0024) must never enter training data, in any copy, re-encoding or excerpt.
- **No duplicates.** One recording is kept once. When the same recording appears twice (another
  bitrate, another loudness, extra silence, another site, up to 10% faster or slower), the
  better usable copy is kept: the higher bandwidth tier first (`full`, then `wide`), then the
  higher signal-to-noise ratio, then the higher bitrate. An excerpt (a copy with less than 80%
  of the other's speech) never replaces the fuller recording. A copy we may not use (wrong
  licence, say) does not count.
- **Speech.** At least half of the file must be speech, and the audio must sound like speech
  rather than animals, weather, machines, laughter or music.
- **Language.** English.
- **Bandwidth.** The recording's content must reach at least 7 kHz, whatever sample rate the file
  says. A 44.1 kHz file made from an 8 kHz phone recording fails.
  - Recordings reaching 9.5 kHz are labelled `full` (usable at 22.05 kHz).
  - Recordings reaching 7 kHz but not 9.5 kHz are labelled `wide` (usable at 16 kHz).
- **No music** under or around the speech: theme tunes, beds and jingles fail the file.
- **Segments.** Files are cut into segments of 1.5 to 20 seconds at pauses. A segment fails if:
  - its signal-to-noise ratio is below 25 dB;
  - more than 0.05% of it is clipped (flat-topped at full scale);
  - its transcript has fewer than two words;
  - the source publishes its text and the speech does not match that text closely (character
    error rate above 25%).
  A file whose segments all fail is rejected for the most common reason.

## Takedowns

Rights holders and speakers can ask for removal by URL, domain, recording or voice. The
recordings are withdrawn and their stored audio is deleted. The releases that contained them are
listed so that anyone who trained on them can be told. Future copies are rejected by
fingerprint, and future segments in a removed voice are rejected by speaker embedding.

## Releases

Releases are immutable. Each one carries:

- a manifest with every segment's source, licence and attribution;
- speaker-disjoint train, dev and test splits;
- a dataset card;
- the public summary of training content (EU AI Act Article 53(1)(d), AI Office template).
