# CLAUDE.md

## Deployment

The app runs on the Docker host at `192.168.68.10` as a plain `docker run`
container — **not** compose. `~/docker-compose.yml` on that host does not
mention this project; don't go looking for it there.

| | |
|---|---|
| Host | `spierce@192.168.68.10` |
| Container / image | `college-data-2023` |
| Ports | `8001` on the host → `8080` in the container |
| URL | http://192.168.68.10:8001 |
| Restart policy | `always` |
| Source checkout | `~/code/college-data-2023` |
| Mounts | none — **code is baked into the image** |

Check what's running:

```sh
ssh spierce@192.168.68.10 docker ps | grep college
```

### Deploying an update

Because there are no volume mounts, changing files on the host does nothing
until the image is rebuilt and the container recreated.

```sh
# 1. ship the working tree (see note on git below)
printf '%s\n' map.py refresh.py fetch_utr.py fetch_ipeds.sh fetch_zips.sh \
    requirements.in requirements.txt README.md utr_crosswalk.csv \
    dist/utr_costs_df.pkl dist/zip_centroids.csv.gz \
  | rsync -av --files-from=- . spierce@192.168.68.10:code/college-data-2023/

# 2. rebuild
ssh spierce@192.168.68.10 'cd ~/code/college-data-2023 && docker build -t college-data-2023 .'

# 3. recreate (flags must be repeated -- they live nowhere but here)
ssh spierce@192.168.68.10 'docker rm -f college-data-2023 && \
  docker run -d --name college-data-2023 --restart always -p 8001:8080 college-data-2023'

# 4. verify
ssh spierce@192.168.68.10 'curl -s -o /dev/null -w "%{http_code}\n" localhost:8001/_stcore/health'
```

`rsync --files-from=-` takes exactly one source dir; listing multiple paths as
plain args fails with *"Only one src dir allowed with --files-from"*.

`docker rm -f` leaves the previous image dangling. That is deliberate — it is
the rollback. `docker image prune` once the new one is known good.

### Gotchas

- **`.dockerignore` excludes `data/`.** Anything the app needs at runtime must
  live in `dist/`, which is why `fetch_zips.sh` writes
  `dist/zip_centroids.csv.gz`. A runtime asset dropped in `data/` builds
  cleanly and then fails on first use inside the container.
- **`origin` is a public GitHub repo** (`ddrscott/college-data-2023`). Deploying
  by pushing publishes the work. Prefer rsync unless publishing is intended.
- rsync deploys leave the host checkout dirty and diverged from its last
  commit, so the running container's code may exist in no commit anywhere.
  Verify with `git -C ~/code/college-data-2023 status` on the host.
- The `Dockerfile` installs from `requirements.txt`, not `requirements.in` or
  the PEP-723 header in `map.py`. Adding a dependency means recompiling:
  `uv pip compile requirements.in -o requirements.txt`.
- `start.sh` binds `--server.address=0.0.0.0` and honours `$PORT` (8080 in the
  image). Don't hardcode the port in the app.
