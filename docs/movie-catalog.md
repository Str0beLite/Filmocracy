# Development movie catalog

Status: **200 TMDB movies imported into tandem after explicit user approval on
2026-10-24.** All 200 have TMDB-listed trailer URLs. Repeating the same import
inserted zero additional rows and preserved all 200 existing records. The catalog
was empty before this import. No profiles, votes, sessions, or schema were modified.

Completed import: **200** released, non-adult movies from TMDB discovery, with
metadata-listed YouTube or Vimeo trailers, into existing **tandem** project
`jwrfdwwpndlorrmhmwuw`, public.movies. Allowed count: 100–300. Movie selection
for catalog ingestion is separate from the application's recommendation algorithm.

## Schema mapping

Existing schema is sufficient; no migration is needed. Identity is the unique pair
`(provider, provider_movie_id)`: `tmdb` plus TMDB's movie ID as a string. Database
generates its own bigint id. Other fields map to title, overview, release_date,
positive runtime_minutes, genre-name array, poster_url, trailer_url, trailer_provider.
Optional missing/invalid metadata becomes null. Trailer URL/provider are always
paired. Poster sizes/base URL come from TMDB configuration.

Importer uses discovery, movie details with append_to_response=videos, and image
configuration endpoints. It excludes teasers and movies with no trailer entries,
prefers official trailers, and then prefers English entries. Links are constructed
from provider + video key; no media is downloaded. A TMDB-listed trailer can later
be removed, region-restricted, or embedding-disabled; the frontend needs a fallback.

Sources: [discovery](https://developer.themoviedb.org/reference/discover-movie),
[videos](https://developer.themoviedb.org/reference/movie-videos),
[images](https://developer.themoviedb.org/docs/image-basics),
[authentication](https://developer.themoviedb.org/docs/authentication-application).

## Credentials and preview

Set these in an ignored local environment file or secret manager. Do not commit
or paste credentials into chat:

```dotenv
TMDB_READ_ACCESS_TOKEN=<TMDB API Read Access Token>
CATALOG_SUPABASE_URL=https://jwrfdwwpndlorrmhmwuw.supabase.co
CATALOG_SUPABASE_SECRET_KEY=<server-only Supabase key>
```

The catalog secret may use the same local server key as TEST_SUPABASE_SECRET_KEY.
It is sent only to the approved Supabase host. TMDB credentials are sent only as
an Authorization header to api.themoviedb.org. There is no frontend TMDB key.

After source/destination approval, a no-write preview is:

```bash
backend/.venv/bin/python backend/import_tmdb.py --count 200
```

Dry-run contacts TMDB but never Supabase. It prints only source, count, and write
count, not credentials. It fails before any writes if it cannot collect the target
number within 100 discovery pages. Requests are sequential, throttled, and retry
429/transient server/network failures at most four attempts with bounded backoff.
See [TMDB rate limits](https://developer.themoviedb.org/docs/rate-limiting).

## Approved import command

Only after explicit chat approval of source and destination:

```bash
backend/.venv/bin/python backend/import_tmdb.py --count 200 --write \
  --approved-project-ref jwrfdwwpndlorrmhmwuw
```

Write mode validates the URL hostname against the explicit project ref before
making remote requests. It only POSTs public.movies, in batches of 50, using
`on_conflict=provider,provider_movie_id` and `resolution=ignore-duplicates`.
Existing metadata is preserved, including manual edits. No PATCH, DELETE, or
other application table writes occur. A rerun inserts only absent IDs.

Batches commit separately. If a later batch fails, prior inserts remain; rerun
safely after fixing the issue. The importer does not claim all-or-nothing import.
Post-import verification should count tmdb records with both trailer fields,
confirm no duplicate provider IDs, rerun to verify zero additional inserts for the
same source set, and sample trailer playback in the intended browser/region.
Discovery ordering may change between runs, so separate runs can select new IDs.

## Attribution

TMDB requires attribution in the app's About/Credits area with an approved logo,
and its specified nonendorsement notice. The frontend teammate should follow the
[TMDB FAQ and attribution requirements](https://developer.themoviedb.org/docs/faq).
The importer does not build or modify that interface.
