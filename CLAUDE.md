# CLAUDE.md

## Deployment

The app is deployed to a Docker host as a plain `docker run` container —
**not** compose — with no volume mounts, so the code is baked into the image.
Changing files on the host does nothing until the image is rebuilt and the
container recreated.

**Host address, ssh account and the exact commands are in `CLAUDE.local.md`,
which is gitignored** — this repo is public, so internal topology stays out of
it. Read that file before deploying; the deploy is not reproducible from this
one alone.

The deploy shape, in general terms:

1. Get the code onto the host (push + pull; rsync only for uncommitted work).
2. `docker build -t college-data-2023 .`
3. `docker rm -f` the old container, `docker run -d` a new one — the port
   mapping and restart policy exist nowhere but `CLAUDE.local.md`, so they must
   be repeated verbatim.
4. Verify `/_stcore/health` and that the analytics tag is in the served HTML.

`docker rm -f` leaves the previous image dangling. That is deliberate — it is
the rollback. `docker image prune` once the new one is known good.

### Gotchas

- **`.dockerignore` excludes `data/`.** Anything the app needs at runtime must
  live in `dist/`, which is why `fetch_zips.sh` writes
  `dist/zip_centroids.csv.gz`. A runtime asset dropped in `data/` builds
  cleanly and then fails on first use inside the container.
- **`origin` is a public GitHub repo** (`ddrscott/college-data-2023`). Anything
  written here is published. Host addresses and accounts belong in
  `CLAUDE.local.md`.
- rsync deploys leave the host checkout dirty and diverged from its last
  commit, so the running container's code may exist in no commit anywhere.
  Prefer push-then-pull, and check `git status` on the host afterwards.
- The `Dockerfile` installs from `requirements.txt`, not `requirements.in` or
  the PEP-723 header in `map.py`. Adding a dependency means recompiling:
  `uv pip compile requirements.in -o requirements.txt`.
- **The Plausible tag is injected by the `Dockerfile`**, not by `map.py` --
  Streamlit has no `<head>` hook. Editing the app will never add or remove it;
  edit the `sed` in the `Dockerfile`. The `grep` after it is load-bearing: it
  fails the build if a Streamlit upgrade changes the template.
- `start.sh` binds `--server.address=0.0.0.0` and honours `$PORT` (8080 in the
  image). Don't hardcode the port in the app.
