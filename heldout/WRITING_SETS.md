# Writing a held-out world

A held-out world tests the refinery on cases its authors did not design. You write a small
internet of `.example` websites as one YAML file. For every audio file you say what our data
policy requires to happen to it. The refinery is run on your world once and its first result is
recorded as it is.

## What you may read

Only these three files:

- this guide;
- `docs/POLICY.md`, the data policy;
- `heldout/MATERIALS.md`, the audio you can build from.

Do **not** read anything under `src/`, `tests/`, `config/`, `reports/`, `data/` or other held-out sets.
The point is that your expectations come from the policy, not from the code.

## What you write

Write `heldout/<set>/world.yaml` and `heldout/<set>/STATUS` containing the single word `blind`.

```yaml
sites:
  - host: lectures.example            # must end in .example
    type: html                        # html | rss | archive | librivox
    title: Public lectures
    licence: CC-BY-4.0                # site-wide licence (html: rel=license link; rss: podcast:license)
    robots: |                         # optional robots.txt text
      User-agent: *
      Disallow: /drafts/
    tdmrep:                           # optional /.well-known/tdmrep.json rules
      - {location: "/premium/*", tdm-reservation: 1}
    reserve_header_prefixes: ["/press/"]   # optional: responses under these paths send tdm-reservation: 1
    blocked: false                    # true: this domain is on our piracy blocklist
    items:
      - id: lec1                      # unique across the file
        path: /talks/lec1.mp3         # html and rss only; archive and librivox choose paths themselves
        material: {clips: [LJ001-0025, LJ001-0026], gap: 0.6}
        transforms:                   # applied in order (all optional)
          - {gain_db: -6}
        format: {codec: mp3, rate: 44100, bitrate: 128k}   # codec: mp3 | flac | wav | ogg
        licence: CC-BY-4.0            # what the source states for this file (overrides the site's)
        page: true                    # html: the file gets its own page with schema.org metadata (default true)
        declared_synthetic: false     # html pages only: the page declares the audio AI-generated
        meta_tdm_reserved: false      # html pages only: the page carries <meta name="tdm-reservation" content="1">
        transcript: none              # published: the page or book publishes the text spoken (LJSpeech clips only)
        expected: keep                # keep | reject:<reason>
        why: "Clean narration under CC BY."
```

### Materials

These come from `heldout/MATERIALS.md`. Each is one of:

- `{clips: [...], gap: s}`
- `{fsdd: {speaker, n}}`
- `{valentini: clean|noisy}`
- `{jfk: true}`
- `{esc: <clip>}`
- `{synthetic: "text", voice: amy|lessac}`
- `{copy_of: <earlier item id>}`: the earlier item's audio as it was published, that is after
  the earlier item's own transforms, with this item's transforms applied on top. Use it for
  re-uploads.

### Transforms

| Transform | What it does |
|---|---|
| `{gain_db: x}` | Changes the level. |
| `{clip_gain_db: x}` | Amplifies, then hard-clips at full scale. |
| `{silence_prefix: s}` / `{silence_suffix: s}` | Adds silence before or after. |
| `{lowpass_hz: f}` | Removes content above f, like a phone line or an old recording. |
| `{mix_noise: {esc: <clip>, snr_db: x}}` | Mixes in an ESC-50 sound at that signal-to-noise ratio. |
| `{music_bed: {level_db: x}}` | Puts music under the speech, x dB relative to the speech. |
| `{excerpt: {start: s, end: s}}` | Keeps only part of the audio. |
| `{speed: f}` | Plays faster (f > 1) or slower, changing pitch too. |

### Formats

`rate` is the sample rate the file is stored at. Storing low-bandwidth audio at 44.1 kHz does
not add bandwidth.

## Reasons you can expect

`keep`, or `reject:` followed by one of:

| Reason | Meaning |
|---|---|
| `blocked_domain` | The domain is on the blocklist. |
| `robots` | robots.txt disallows the file. |
| `tdm` | TDMRep reserves the file or its page. |
| `fetch` | The file cannot be downloaded. |
| `licence` | The licence is not usable for training. |
| `synthetic` | Declared or obviously synthetic speech. |
| `protected` | Contains our evaluation recordings. |
| `duplicate` | A copy of a recording kept elsewhere in your world. |
| `not_speech` | Not speech. |
| `bandwidth` | Not enough bandwidth. |
| `music` | Music under or around the speech. |
| `noise` | Signal-to-noise ratio too low. |
| `clipping` | Clipped. |

For duplicates, decide from the policy which copy is the better one and expect `keep` for it and
`reject:duplicate` for the other. Undeclared synthetic speech is *held* for review under the
policy. Expect `reject:synthetic` for it: held files are not released.

## What a good set looks like

- About 40 to 60 items over 5 to 8 sites, using all four site types.
- Mostly realistic cases, plus some hard ones near the policy's limits:
  - noise a little above or below 25 dB;
  - bandwidth near 7 kHz;
  - quiet music beds;
  - an excerpt of a protected recording;
  - a re-upload that is louder, quieter, longer or faster;
  - a licence stated only at the site level;
  - a reservation in only one of the three TDMRep places.
- At least 10 items you expect to be kept. A set where everything is rejected tests little.
- Write the `why` for every item. If the policy does not settle a case, say so in `why` and pick
  what a careful data lead would want.

Once the first run is recorded, your file is not edited. If you realise an expectation was wrong,
write it down in `heldout/<set>/NOTES.md`; do not change `world.yaml`.
