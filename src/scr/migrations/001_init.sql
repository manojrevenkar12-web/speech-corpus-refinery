-- PostgreSQL is the record: every URL, fetch, decision, segment, release and takedown.

CREATE TABLE sources (
  id serial PRIMARY KEY,
  name text UNIQUE NOT NULL,
  kind text NOT NULL,                -- librivox | internet_archive | rss | html_index
  seed_url text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE hosts (
  host text PRIMARY KEY,
  robots_status int,
  robots_txt text,
  robots_fetched_at timestamptz,
  tdmrep jsonb,
  tdmrep_fetched_at timestamptz,
  crawl_delay real,
  next_allowed_at timestamptz NOT NULL DEFAULT now(),
  lease_until timestamptz,
  lease_owner text
);

CREATE TABLE urls (
  id bigserial PRIMARY KEY,
  url text UNIQUE NOT NULL,
  host text NOT NULL REFERENCES hosts(host),
  source_id int REFERENCES sources(id),
  kind text NOT NULL CHECK (kind IN ('api', 'feed', 'page', 'audio', 'text')),
  state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'done', 'skipped', 'failed')),
  reason text,
  attempts int NOT NULL DEFAULT 0,
  next_try_at timestamptz NOT NULL DEFAULT now(),
  discovered_from bigint REFERENCES urls(id),
  depth int NOT NULL DEFAULT 0,
  meta jsonb NOT NULL DEFAULT '{}',
  etag text,
  last_modified text,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX urls_due ON urls (host, next_try_at) WHERE state = 'queued';

CREATE TABLE fetches (
  id bigserial PRIMARY KEY,
  url_id bigint NOT NULL REFERENCES urls(id),
  at timestamptz NOT NULL DEFAULT now(),
  status int,
  bytes bigint,
  sha256 text,
  content_type text,
  headers jsonb,
  error text,
  seconds real
);

CREATE TABLE blobs (
  sha256 text PRIMARY KEY,
  bytes bigint NOT NULL,
  content_type text,
  first_seen timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,
  deleted_reason text
);

-- one downloaded audio file and everything decided about it
CREATE TABLE items (
  id bigserial PRIMARY KEY,
  url_id bigint UNIQUE NOT NULL REFERENCES urls(id),
  source_id int REFERENCES sources(id),
  sha256 text REFERENCES blobs(sha256),
  licence text NOT NULL,
  licence_evidence text NOT NULL DEFAULT '',
  attribution text NOT NULL DEFAULT '',
  synthetic_declared boolean NOT NULL DEFAULT false,
  title text NOT NULL DEFAULT '',
  text_url text,
  meta jsonb NOT NULL DEFAULT '{}',
  state text NOT NULL DEFAULT 'new' CHECK (state IN ('new', 'kept', 'held', 'rejected', 'withdrawn')),
  reason text,
  detail jsonb NOT NULL DEFAULT '{}',
  decided_config text,
  created_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz
);

CREATE TABLE analyses (
  item_id bigint PRIMARY KEY REFERENCES items(id),
  config_hash text NOT NULL,
  codec text, native_rate int, channels int,
  seconds real, bandwidth_hz real, snr_db real, snr_method text, clipped_ratio real, dbfs real,
  speech_ratio real, tags jsonb, language text,
  pcm_sha256 text,
  canonical_of bigint REFERENCES items(id),   -- set when this item repeats another
  match jsonb
);

-- fingerprints of downloaded items and of the protected evaluation recordings
CREATE TABLE fp_items (
  id bigserial PRIMARY KEY,
  item_id bigint UNIQUE REFERENCES items(id),
  protected boolean NOT NULL DEFAULT false,
  blocked_by int,                  -- a takedown: copies of this recording are never ingested again
  label text NOT NULL DEFAULT '',
  n int NOT NULL
);
CREATE TABLE fp_hashes (h int NOT NULL, fp_id bigint NOT NULL REFERENCES fp_items(id) ON DELETE CASCADE, t int NOT NULL);
CREATE INDEX fp_hashes_h ON fp_hashes (h);

CREATE TABLE segments (
  id bigserial PRIMARY KEY,
  item_id bigint NOT NULL REFERENCES items(id),
  idx int NOT NULL,
  start_s real NOT NULL, end_s real NOT NULL,
  asr text, text text, cer real,
  snr_db real, clipped_ratio real, bandwidth_hz real, tier text,
  speaker text,
  embedding real[],
  state text NOT NULL CHECK (state IN ('kept', 'rejected', 'withdrawn')),
  reason text,
  UNIQUE (item_id, idx)
);

-- the work queue: leases, retries, dead letters
CREATE TABLE jobs (
  id bigserial PRIMARY KEY,
  kind text NOT NULL,
  ref bigint NOT NULL,
  state text NOT NULL DEFAULT 'queued' CHECK (state IN ('queued', 'running', 'done', 'dead')),
  attempts int NOT NULL DEFAULT 0,
  not_before timestamptz NOT NULL DEFAULT now(),
  lease_until timestamptz,
  lease_owner text,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  UNIQUE (kind, ref)
);
CREATE INDEX jobs_due ON jobs (kind, not_before) WHERE state = 'queued';

CREATE TABLE costs (
  id bigserial PRIMARY KEY,
  stage text NOT NULL,
  item_id bigint,
  source_id int,
  cpu_seconds real NOT NULL,
  wall_seconds real NOT NULL,
  audio_seconds real NOT NULL DEFAULT 0,
  bytes bigint NOT NULL DEFAULT 0,
  at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE releases (
  id serial PRIMARY KEY,
  name text UNIQUE NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  config_hash text NOT NULL,
  manifest_sha256 text NOT NULL,
  stats jsonb NOT NULL,
  parent text
);
CREATE TABLE release_segments (release_id int NOT NULL REFERENCES releases(id), segment_id bigint NOT NULL REFERENCES segments(id), split text NOT NULL, PRIMARY KEY (release_id, segment_id));

CREATE TABLE takedowns (
  id serial PRIMARY KEY,
  kind text NOT NULL CHECK (kind IN ('url', 'domain', 'speaker', 'item')),
  value text NOT NULL,
  reason text NOT NULL,
  requested_by text NOT NULL,
  requested_at timestamptz NOT NULL DEFAULT now(),
  executed_at timestamptz,
  affected jsonb
);

-- what takedowns keep out of future crawls and processing
CREATE TABLE do_not_crawl (pattern text PRIMARY KEY, kind text NOT NULL CHECK (kind IN ('url', 'domain')), takedown_id int REFERENCES takedowns(id));
CREATE TABLE blocked_speakers (id serial PRIMARY KEY, centroid real[] NOT NULL, takedown_id int REFERENCES takedowns(id));

CREATE TABLE reviews (
  id bigserial PRIMARY KEY,
  segment_id bigint REFERENCES segments(id),
  item_id bigint REFERENCES items(id),
  reviewer text NOT NULL,
  verdict text NOT NULL CHECK (verdict IN ('agree', 'disagree')),
  note text NOT NULL DEFAULT '',
  at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit (
  seq bigserial PRIMARY KEY,
  at timestamptz NOT NULL DEFAULT now(),
  actor text NOT NULL,
  event text NOT NULL,
  data jsonb NOT NULL,
  prev text NOT NULL,
  hash text NOT NULL
);
-- the audit trail is append-only
CREATE FUNCTION audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'audit is append-only'; END $$;
CREATE TRIGGER audit_no_update BEFORE UPDATE OR DELETE ON audit FOR EACH ROW EXECUTE FUNCTION audit_immutable();

CREATE TABLE schema_version (version int PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
