# Sandstorm Help Desk — 0.1.0

A small server-rendered Python/Flask ticket system with SQLite persistence.
This archive is source code, not an already-built or signed Sandstorm `.spk`.

## Features

- Four Sandstorm sharing roles: Requester, Supervisor, Technician, Administrator.
- Requesters see their own tickets, create tickets, and comment/upload images on their own open tickets.
- Supervisors have those same ownership-based abilities and can read everyone else's tickets, comments, and images.
- Technicians can respond to any open ticket, close/reopen any ticket, and update categories/priorities.
- Administrators also manage categories, priorities, and the requester-reopening policy.
- Configurable owner reopening, disabled by default, with no time limit when enabled.
- Markdown descriptions/comments, formatting toolbar, and server-rendered sanitized preview.
- Multiple authorized image attachments on original descriptions and individual comments.
- Filter/search ticket lists with pagination, ticket activity history, and settings audit history.
- Responsive HTML/CSS interface without external assets, JavaScript frameworks, or CDN dependencies.

## Quick start (local development)

Requires Python 3.10+ and an internet connection to install dependencies (or a local wheelhouse).
From the extracted project directory, on Linux/macOS:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
export HELPDESK_DEV_MODE=1
python run.py
```

Open http://127.0.0.1:8000. The fixed local identity is an administrator.
The development mode is deliberately opt-in. `run.py` listens only on loopback and uses Waitress, not Flask's debugger.

PowerShell equivalents:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:HELPDESK_DEV_MODE="1"
python run.py
```

To manually try another local role, stop the server, set these variables, then restart:

```sh
export HELPDESK_DEV_ROLE=requester
export HELPDESK_DEV_USER_ID=alice
export HELPDESK_DEV_USER_NAME=Alice
python run.py
```

Role values: `requester`, `supervisor`, `technician`, `administrator`.
Keep a user's ID unchanged when trying different roles if you want to retain ownership.
Development mode ignores incoming identity headers; it does not offer a browser role switcher.
Never expose development mode on a shared/public interface.

## First use

1. Open the app as an administrator (the grain owner in Sandstorm).
2. Visit Settings to review the starter categories and priorities.
3. Optionally enable "Allow ticket owners to reopen their own closed tickets".
4. In Sandstorm, use Share access to grant each colleague the appropriate named role.
5. Requesters use My tickets and New ticket; staff use All tickets.

Starter categories: General, Hardware, Software, Network.
Starter priorities, lowest to highest: Low, Normal, High, Urgent.
These are database seed values, not hardcoded restrictions; administrators can rename/add/deactivate them.
Lower priority sort-order numbers appear first in selection lists.

## Workflow details

- All roles may create tickets.
- Supervisors' access to other people's tickets is strictly read-only.
- Closed tickets remain readable but accept no new comments/images from any role until explicitly reopened.
- Only technicians/administrators close tickets.
- Technicians/administrators may always reopen any closed ticket.
- When the policy is enabled, requesters/supervisors may reopen only their own closed tickets.
- Policy changes apply immediately to both existing and future tickets.
- Reopening clears the current closure fields but never removes historical closure/reopening events.
- No ticket deletion, assignment, comment editing, notifications, or per-ticket custom role grants are included.
- Deactivated category/priority selections remain visible on existing tickets; at least one option of each kind must stay active.
- Taxonomy renames are reflected on associated tickets. The settings audit records the previous values.
- Settings history shows the latest 50 changes; all events remain in the database.
- Display names are cached on writes; they are not security identifiers.

## Formatting and images

Markdown supports bold, italics, lists, links, code, headings, and blockquotes.
Raw HTML is disabled and the rendered result is sanitized.
Remote embedded Markdown images are disabled to avoid bypassing attachment access and loading trackers.
External ordinary links are allowed.

Image inputs: PNG, JPEG, GIF, WebP. Each submission accepts at most 10 images,
10 MiB per input image, and 20 million pixels per image. The total HTTP request limit is 105 MiB.
Images are decoded and re-encoded to PNG, stripping metadata and trailing payloads;
GIF/WebP animations use the first frame. The resulting PNG must also be at most 10 MiB.
This may increase storage size compared with the original compressed image.

Implementation simplification: normalized image bytes are stored as SQLite BLOBs,
not in a public upload directory. Metadata includes a generated storage key and the original display filename.
Ticket/comment/image writes are transactional; a database snapshot includes all images.
The attachment endpoint verifies parent-ticket access on every request, including downloads.
There are no public image URLs. Gallery thumbnails use browser-sized versions of the authorized full image,
not separately generated thumbnails; this is suitable for a simple help desk but not optimized for massive image libraries.

## Persistence and configuration

- Local data directory: `./instance`, relative to the process working directory.
- Sandstorm data directory: `/var/helpdesk`.
- Files: `helpdesk.sqlite3`, its live WAL/shared-memory companions, and `session-secret`.
- The secret is generated once and persisted. Preserve it to keep existing sessions valid.
- No passwords, external services, SMTP server, or database server are needed.
- Initialization is idempotent and seeds only a new database. Schema version 1 is recorded;
  a newer database version is rejected. Future releases must add explicit versioned migrations.

Environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `HELPDESK_DATA_DIR` | `./instance` | Persistent data directory |
| `HELPDESK_DEV_MODE` | disabled | Exactly `1` enables a fixed local test identity |
| `HELPDESK_DEV_ROLE` | `administrator` | Fixed development role |
| `HELPDESK_DEV_USER_ID` | `local-admin` | Fixed development identity ID |
| `HELPDESK_DEV_USER_NAME` | `Local administrator` | Fixed development display name |
| `PORT` | `8000` | Loopback HTTP listening port |

Production cookies are Secure/HttpOnly/SameSite=Lax. Secure cookies are disabled only in explicit local development mode.
Sandstorm production must be served over HTTPS.

## Sandstorm security boundary

Production identity comes exclusively from `X-Sandstorm-User-Id`, the percent-decoded
`X-Sandstorm-Username`, and the comma-separated `X-Sandstorm-Permissions` header.
Anonymous visitors are rejected; no implicit administrator fallback exists.

These headers are only trustworthy behind Sandstorm's HTTP bridge. Do not publish the raw
Waitress port or place the app behind a proxy that forwards user-supplied Sandstorm headers.
If deploying outside Sandstorm, you must add a real authenticated identity gateway first.

Sandstorm authenticates users and grants sharing roles. Flask performs per-ticket ownership
and permission checks, so sharing a grain as Requester does not reveal other users' tickets.
The package role definitions are in `sandstorm/sandstorm-pkgdef.capnp.in`.
Never reorder/remove existing permission or role entries in a released package; append instead.

Official integration reference: https://docs.sandstorm.io/en/latest/developing/auth/
Package format example used for the scaffold:
https://github.com/sandstorm-io/hello-sandstorm-oauth/blob/master/sandstorm-pkgdef.capnp

## Build a Sandstorm package

The included package definition is a scaffold for a Linux Sandstorm SDK/build environment.
It has not been compiled or smoke-tested on a Sandstorm server in the generation environment.
You need `spk`, the Sandstorm Cap'n Proto schemas, and the bridge executable available
as `/sandstorm-http-bridge` in your build filesystem/source map. A configured vagrant-spk
build VM is another suitable place to do this; its surrounding VM setup is not included.
Do not run the following commands inside a grain: dependency installation happens at build time.

From the extracted source tree inside your build environment:

```sh
# Provision a build-time Python environment at the path used by the package.
python3 -m venv /opt/helpdesk-env
/opt/helpdesk-env/bin/python -m pip install -r requirements.txt
/opt/helpdesk-env/bin/python -m unittest discover -v

# Create your own signing identity; save the private key/keyring securely.
spk keygen
# Copy the app ID printed by spk keygen into this command:
python3 tools/configure_sandstorm.py YOUR_APP_ID

# Start development packaging. Use the grain from your Sandstorm host.
spk dev
```

The package's source map mounts this project at `/opt/helpdesk`, and maps dependencies from
the build filesystem. The launcher uses `/opt/helpdesk-env/bin/python`, stores all mutable
state under `/var/helpdesk`, and forcibly disables local development identities.
If your SDK places its bridge elsewhere, adjust the command/source map before running `spk dev`.

During `spk dev`, exercise every screen and every role to populate `sandstorm-files.list`,
including initial image decoding and preview. Review the captured file list for missing
runtime libraries or accidentally included host secrets. The app source and the virtualenv
are also explicitly included. Keep this list alongside your package definition for future builds.
After stopping development mode, build the signed artifact:

```sh
spk pack helpdesk.spk
```

Install that artifact on a test Sandstorm host and run the acceptance checklist below before
production use. No signed `.spk` or app signing key is included in this archive.
For public app-market publication, supply your own author/contact/license information,
icons, and other required market metadata in the generated package definition.

## Automated tests

```sh
python -m unittest discover -v
```

Tests use temporary SQLite databases, not your real help desk.
The core suite checks role permissions, ownership, status transitions, policy changes,
classification settings, image decoding, Markdown sanitization, transaction rollback,
SQL parameterization, and audit records. The web suite checks routes, session/CSRF handling,
attachment access, form rendering, preview, upload submission, and production cookie settings.

See TEST_REPORT.md for the exact checks executed while this archive was generated.
A successful run that reports skipped web tests is not a full application validation.
For a strict CI check that first requires Flask:

```sh
python -c "import flask, waitress, markdown_it, bleach; from PIL import Image"
python -m unittest discover -v
```

## Backup and restore

Preferred in Sandstorm: use the grain's built-in backup/restore capability.
For a local consistent database snapshot, including images and audit history:

```sh
python tools/backup.py instance/helpdesk.sqlite3 backups/helpdesk-backup.sqlite3
```

The helper uses SQLite's backup API, checks integrity, and refuses to overwrite a destination.
Do not copy only a live `.sqlite3` file while ignoring its WAL. Preserve `session-secret`
separately if you want browser sessions to survive restore. To restore locally, stop the app,
move the old data directory aside (including WAL/SHM files), create a clean data directory,
place the snapshot there as `helpdesk.sqlite3`, restore the secret if desired, and restart.
Treat backups as sensitive: they include every ticket, comment, and image.

## Deployment acceptance checklist

- Install requirements and run all 61 automated tests without skips.
- Validate the Sandstorm package definition with your SDK and build an `.spk`.
- Create an HTTPS grain and verify all four Sandstorm sharing roles using distinct users.
- As requester B, try direct URLs for requester A's ticket and attachment; both must fail.
- Verify a supervisor cannot submit a forged comment, classification, or close request on another user's ticket.
- Verify requester/supervisor owners can comment/upload images on their own open tickets.
- Close a ticket, test reopening with the policy off/on, then disable it again immediately.
- Verify technicians/administrators can reopen regardless of that policy.
- Verify persistence after stopping/restarting the grain and after backup/restore.
- Try invalid, oversized, and unsupported images, and inspect browser console/CSP errors.
- Ensure development mode is off, raw HTTP is not exposed, and package contents exclude host secrets.

## Project map

- `helpdesk/core.py`: database schema, transactions, authorization policies, ticket operations, formatting, images.
- `helpdesk/web.py`: Flask factory, Sandstorm identity, CSRF, routes, security headers.
- `helpdesk/templates/`, `helpdesk/static/`: responsive server-rendered interface and formatting toolbar.
- `run.py`: loopback Waitress entry point; `wsgi.py`: WSGI factory entry point.
- `tests/`: core and Flask integration tests.
- `sandstorm/`: launcher and package-definition template.
- `tools/`: package configuration and consistent database backup helpers.

Dependencies are bounded major-version ranges, not a reproducible transitive lockfile.
For a production release, resolve and audit dependencies in your target build environment,
record the exact versions, run the complete suite, and retain the lockfile/build artifacts.


# Help Desk 0.1.1

## Behavior changes

- Technicians/administrators default to All tickets filtered to Open when opening the app, visiting `/tickets`, or clicking the header brand.
- My tickets remains available to every role; its link explicitly selects `scope=mine`.
- Explicit filters override defaults. All statuses submits `status=` to include open and closed tickets; Closed selects closed tickets. Filters remain effective during pagination.
- Requesters/supervisors still default to My tickets. Supervisors' All tickets access remains read-only.
- Administrators can change Header title in Settings → Appearance. It defaults to Sandstorm Help Desk, applies grain-wide, is trimmed, required, single-line, limited to 80 characters, and HTML-escaped when displayed. Changes are audited.
- The title changes the top-left brand and browser page-title suffix, not the Sandstorm shell's grain title or installed application name.
- CSS follows the OS/browser light/dark preference automatically, including panels, form controls, tables, previews, messages, badges, and code blocks. Light is the fallback. No JavaScript theme store or per-grain theme override is introduced.

## Compatibility

No schema change or database reset is needed. The title uses the existing app_settings table, with a fallback until saved. Existing ticket data and reopening policy are preserved. The updater itself touches source only.

Back up data and stop the app before applying. Source backups are saved under `.helpdesk-update-backups/`. The updater validates anchors and Python syntax before writing, refuses duplicate application, and rolls back source writes on handled errors. A forced termination or machine failure during writing can still require restoring the backups manually. The backup's CREATED_FILES.txt lists files that did not exist before the update.

## Tests

The update adds 6 core tests and 7 Flask integration tests in tests/test_update_011.py. Combined with the original suite, expected discovery is 74 tests. Inherited tests are not counted twice. Run the complete suite in your installed application environment without skips:

```sh
python -m unittest discover -v
```

See the update bundle's VALIDATION.md for checks actually executed while preparing this update. New test inclusion does not mean the full application has been runtime-tested here.

## Sandstorm packaging

The package template is updated to numeric appVersion 2 and marketing version 0.1.1. If you already generated sandstorm-pkgdef.capnp, manually increment its numeric appVersion beyond your last installed version, and set marketing version 0.1.1. Preserve your app ID/private key and permission/role ordering. Rebuild, install, and test the SPK using the original README instructions. Updating a source tree does not change an already installed grain.
