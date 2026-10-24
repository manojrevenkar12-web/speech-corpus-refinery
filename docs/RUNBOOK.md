# Runbook

## Deploy

```bash
# once: a bucket for Terraform state
gsutil mb -l europe-west3 gs://$PROJECT-tfstate

docker build -t europe-west3-docker.pkg.dev/$PROJECT/scr-images/scr:$(git rev-parse --short HEAD) .
docker push europe-west3-docker.pkg.dev/$PROJECT/scr-images/scr:$(git rev-parse --short HEAD)
# pin the pushed digest in terraform.tfvars (image = ".../scr@sha256:...")

cd infra/terraform
terraform init -backend-config="bucket=$PROJECT-tfstate"
terraform apply
gcloud secrets versions add scr-api-keys --data-file=keys.txt   # key:role pairs, comma-separated
gcloud run jobs execute scr-setup --region europe-west3 --wait  # migrations and the protected set
```

Then publish the `crawler_egress_ip` output in docs/CRAWLER.md.

## Add a source

1. Score it first: `scr discover <name> <kind> <seed-url> --sample 10`. This runs the full
   pipeline on a sample, in its own source prefix, and gives a verdict (ingest, review first or
   skip), the yield and the cost per usable hour.
2. Seed it if the verdict is ingest: `scr seed <name> <kind> <seed-url>`. The nightly crawl picks
   it up.

## A job failed

The alert links here.

- **`scr-crawl` failed.** Read the job's logs.
  - A host that keeps failing is retried with back-off and then marked failed. One bad host
    does not stop the crawl.
  - A crash is usually Cloud SQL being unreachable. Check the instance, then run the job again;
    URL leases expire and nothing is fetched twice.
- **`scr-work` failed, or the console shows `analyse:dead` jobs.** A dead job failed three
  times. `SELECT ref, last_error FROM jobs WHERE state = 'dead'` shows why.
  - A corrupt file is rejected as `corrupt`; it does not go dead.
  - A dead job is a bug or a resource limit. Fix it, then
    `UPDATE jobs SET state = 'queued', attempts = 0 WHERE state = 'dead'`.

## Takedown

In the console (admin key), or from the CLI:

```bash
scr takedown request domain example.org --reason "Rights holder request #123" --by "you@team"
scr takedown preview domain example.org   # what it would remove, and which releases contained it
scr takedown execute <id> --by "you@team"
```

Tell everyone who trained on the listed releases. The audit chain records who did what:
`scr verify-audit`.

## Release

```bash
gcloud run jobs execute scr-release --region europe-west3 --args=release,v7 --wait
```

Releases are immutable. Publishing an existing name fails rather than overwriting it. To compare
two releases, run `scr diff v6 v7`.

## Held-out sets

- A new set is written blind, from heldout/WRITING_SETS.md only, by someone who has not seen
  the code.
- Run it once: `python -c "from scr import heldout; heldout.run('setN', '<db url>')"`. Commit
  `reports/heldout/setN/first_run.json`, and never edit it.
