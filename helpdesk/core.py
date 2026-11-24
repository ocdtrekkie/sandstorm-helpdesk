import io
import json
import sqlite3
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import bleach
from markdown_it import MarkdownIt
from PIL import Image, ImageOps, UnidentifiedImageError

PERMISSIONS = ('createTickets', 'viewAllTickets', 'respondToTickets', 'manageTickets', 'manageSettings')
ROLES = {
    'requester': frozenset(PERMISSIONS[:1]),
    'supervisor': frozenset(PERMISSIONS[:2]),
    'technician': frozenset(PERMISSIONS[:4]),
    'administrator': frozenset(PERMISSIONS),
}
MAX_IMAGE = 10 * 1024 * 1024
MAX_IMAGES = 10
MAX_PIXELS = 20_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status

@dataclass(frozen=True)
class Actor:
    id: str
    name: str
    permissions: frozenset

    def has(self, permission):
        return permission in self.permissions

    def owns(self, ticket):
        return self.id == ticket['requester_id']

    def can_view(self, ticket):
        return self.has('viewAllTickets') or (self.has('createTickets') and self.owns(ticket))

    def can_comment(self, ticket):
        return ticket['status'] == 'open' and self.can_view(ticket) and (
            self.has('respondToTickets') or (self.has('createTickets') and self.owns(ticket)))

    def can_reopen(self, ticket, allowed):
        return ticket['status'] == 'closed' and self.can_view(ticket) and (
            self.has('manageTickets') or (allowed and self.has('createTickets') and self.owns(ticket)))

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS categories(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)));
CREATE TABLE IF NOT EXISTS priorities(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
 sort_order INTEGER NOT NULL DEFAULT 0,
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)));
CREATE TABLE IF NOT EXISTS app_settings(
 key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tickets(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 requester_id TEXT NOT NULL REFERENCES users(id),
 subject TEXT NOT NULL CHECK(length(subject) BETWEEN 1 AND 200),
 body TEXT NOT NULL,
 category_id INTEGER NOT NULL REFERENCES categories(id),
 priority_id INTEGER NOT NULL REFERENCES priorities(id),
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed')),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 closed_at TEXT, closed_by TEXT REFERENCES users(id));
CREATE INDEX IF NOT EXISTS tickets_owner ON tickets(requester_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS tickets_status ON tickets(status, updated_at DESC);
CREATE TABLE IF NOT EXISTS comments(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 ticket_id INTEGER NOT NULL REFERENCES tickets(id),
 author_id TEXT NOT NULL REFERENCES users(id),
 body TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(id,ticket_id));
CREATE TABLE IF NOT EXISTS attachments(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 ticket_id INTEGER NOT NULL REFERENCES tickets(id),
 comment_id INTEGER,
 author_id TEXT NOT NULL REFERENCES users(id),
 storage_key TEXT NOT NULL UNIQUE,
 original_name TEXT NOT NULL, mime TEXT NOT NULL,
 data BLOB NOT NULL, created_at TEXT NOT NULL,
 FOREIGN KEY(comment_id,ticket_id) REFERENCES comments(id,ticket_id));
CREATE INDEX IF NOT EXISTS attachments_ticket ON attachments(ticket_id);
CREATE TABLE IF NOT EXISTS ticket_events(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 ticket_id INTEGER REFERENCES tickets(id),
 actor_id TEXT NOT NULL REFERENCES users(id),
 action TEXT NOT NULL, details TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS events_ticket ON ticket_events(ticket_id,id);
"""

def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')

def connect(path):
    db = sqlite3.connect(str(path), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=15000')
    return db

def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = connect(path)
    try:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript(SCHEMA)
        with db:
            db.execute('BEGIN IMMEDIATE')
            version = db.execute('SELECT MAX(version) FROM schema_migrations').fetchone()[0]
            if version is not None and version > 1:
                raise RuntimeError('Database is newer than this application; refusing downgrade.')
            if version is None:
                db.execute('INSERT INTO schema_migrations VALUES(1,?)', (now(),))
                for name in ('General', 'Hardware', 'Software', 'Network'):
                    db.execute('INSERT INTO categories(name) VALUES(?)', (name,))
                for rank, name in enumerate(('Low', 'Normal', 'High', 'Urgent')):
                    db.execute('INSERT INTO priorities(name,sort_order) VALUES(?,?)', (name, rank))
            db.execute("INSERT OR IGNORE INTO app_settings VALUES('allow_requester_reopen','0')")
    finally:
        db.close()

@contextmanager
def transaction(db):
    try:
        db.execute('BEGIN IMMEDIATE')
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise

def remember(db, actor):
    db.execute('INSERT INTO users VALUES(?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name',
               (actor.id, actor.name))

def event(db, actor, action, ticket_id=None, **details):
    db.execute('INSERT INTO ticket_events(ticket_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',
               (ticket_id, actor.id, action, json.dumps(details), now()))

def text(value, label, limit, required=True):
    if not isinstance(value, str):
        raise Problem(f'{label} must be text.')
    value = value.strip()
    if required and not value:
        raise Problem(f'{label} is required.')
    if len(value) > limit:
        raise Problem(f'{label} must be at most {limit:,} characters.')
    return value

def integer(value, label):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        raise Problem(f'{label} must be a number.')

def require(actor, permission):
    if not actor.has(permission):
        raise Problem('You do not have permission to do that.', 403)

def ticket(db, actor, ticket_id):
    row = db.execute("""
      SELECT t.*,u.name requester_name,c.name category,p.name priority
      FROM tickets t JOIN users u ON u.id=t.requester_id
      JOIN categories c ON c.id=t.category_id JOIN priorities p ON p.id=t.priority_id
      WHERE t.id=?""", (ticket_id,)).fetchone()
    if row is None or not actor.can_view(row):
        raise Problem('Ticket not found.', 404)
    return row

def reopen_allowed(db):
    return db.execute("SELECT value FROM app_settings WHERE key='allow_requester_reopen'").fetchone()[0] == '1'

def active_choice(db, table, value):
    if table not in ('categories','priorities'):
        raise ValueError('Invalid taxonomy')
    value = integer(value, 'Category or priority')
    row = db.execute(f'SELECT id FROM {table} WHERE id=? AND active=1', (value,)).fetchone()
    if row is None:
        raise Problem('Select an active category and priority.')
    return value

@dataclass(frozen=True)
class Upload:
    name: str
    mime: str
    data: bytes
    storage_key: str

def prepare_uploads(files):
    files = [(name, data) for name, data in files if name]
    if len(files) > MAX_IMAGES:
        raise Problem(f'At most {MAX_IMAGES} images are allowed per submission.')
    result = []
    for name, data in files:
        if not data or len(data) > MAX_IMAGE:
            raise Problem('Images must be nonempty and no larger than 10 MB each.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    fmt = image.format
                    if fmt not in ('PNG','JPEG','GIF','WEBP'):
                        raise Problem('Only PNG, JPEG, GIF, and WebP images are supported.')
                    if image.width * image.height > MAX_PIXELS:
                        raise Problem('Image exceeds the 20 megapixel limit.')
                    image.seek(0)
                    image.load()
                    cleaned = ImageOps.exif_transpose(image).convert('RGBA')
                    out = io.BytesIO()
                    cleaned.save(out, format='PNG')
                    encoded = out.getvalue()
                    if len(encoded) > MAX_IMAGE:
                        raise Problem('Image exceeds 10 MB after safe conversion. Use a smaller image.')
        except Problem:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
                Image.DecompressionBombWarning):
            raise Problem('An uploaded file is not a valid supported image.')
        safe_name = str(name).replace('\\','/').split('/')[-1]
        safe_name = ''.join(c for c in safe_name if c.isprintable())[:200] or 'image'
        result.append(Upload(safe_name, 'image/png', encoded, uuid4().hex + '.png'))
    return result

def save_uploads(db, actor, ticket_id, comment_id, uploads):
    for u in uploads:
        db.execute("""
          INSERT INTO attachments(ticket_id,comment_id,author_id,storage_key,original_name,mime,data,created_at)
          VALUES(?,?,?,?,?,?,?,?)""",
          (ticket_id,comment_id,actor.id,u.storage_key,u.name,u.mime,u.data,now()))

def create_ticket(db, actor, subject, body, category, priority, files=()):
    require(actor,'createTickets')
    subject = text(subject,'Subject',200)
    body = text(body,'Description',50000)
    uploads = prepare_uploads(files)
    with transaction(db):
        remember(db,actor)
        category = active_choice(db,'categories',category)
        priority = active_choice(db,'priorities',priority)
        stamp = now()
        cur = db.execute("""
          INSERT INTO tickets(requester_id,subject,body,category_id,priority_id,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?)""",(actor.id,subject,body,category,priority,stamp,stamp))
        tid = cur.lastrowid
        save_uploads(db,actor,tid,None,uploads)
        event(db,actor,'created',tid)
    return tid

def add_comment(db, actor, tid, body, files=()):
    body = text(body,'Comment',50000,required=False)
    uploads = prepare_uploads(files)
    if not body and not uploads:
        raise Problem('Add a comment or at least one image.')
    with transaction(db):
        t = ticket(db,actor,tid)
        if not actor.can_comment(t):
            raise Problem('You cannot comment on this ticket. Closed tickets must be reopened first.',403)
        remember(db,actor)
        stamp = now()
        cur = db.execute('INSERT INTO comments(ticket_id,author_id,body,created_at) VALUES(?,?,?,?)',
                         (tid,actor.id,body,stamp))
        save_uploads(db,actor,tid,cur.lastrowid,uploads)
        db.execute('UPDATE tickets SET updated_at=? WHERE id=?',(stamp,tid))
        event(db,actor,'commented',tid,comment_id=cur.lastrowid)

def change_status(db, actor, tid, target):
    if target not in ('open','closed'):
        raise Problem('Invalid status.')
    with transaction(db):
        t = ticket(db,actor,tid)
        if target == 'closed':
            require(actor,'manageTickets')
        elif not actor.can_reopen(t,reopen_allowed(db)):
            raise Problem('You cannot reopen this ticket.',403)
        if t['status'] == target:
            raise Problem('Ticket already has that status.',409)
        remember(db,actor)
        stamp = now()
        db.execute('UPDATE tickets SET status=?,updated_at=?,closed_at=?,closed_by=? WHERE id=?',
                   (target,stamp,stamp if target=='closed' else None,
                    actor.id if target=='closed' else None,tid))
        event(db,actor,'closed' if target=='closed' else 'reopened',tid)

def change_metadata(db, actor, tid, category, priority):
    require(actor,'manageTickets')
    with transaction(db):
        t = ticket(db,actor,tid)
        cid, pid = integer(category,'Category'), integer(priority,'Priority')
        # An inactive historical selection may be retained, but not newly selected.
        if cid != t['category_id']:
            active_choice(db,'categories',cid)
        if pid != t['priority_id']:
            active_choice(db,'priorities',pid)
        if cid == t['category_id'] and pid == t['priority_id']:
            return
        remember(db,actor)
        db.execute('UPDATE tickets SET category_id=?,priority_id=?,updated_at=? WHERE id=?',
                   (cid,pid,now(),tid))
        event(db,actor,'metadata_changed',tid,
              old_category=t['category_id'],category=cid,old_priority=t['priority_id'],priority=pid)

def set_reopen(db, actor, enabled):
    require(actor,'manageSettings')
    with transaction(db):
        remember(db,actor)
        old = reopen_allowed(db)
        db.execute("UPDATE app_settings SET value=? WHERE key='allow_requester_reopen'",('1' if enabled else '0',))
        if old != bool(enabled):
            event(db,actor,'requester_reopen_policy_changed',enabled=bool(enabled),previous=old)

def save_taxonomy(db, actor, kind, item_id, name, active=True, sort_order=0):
    require(actor,'manageSettings')
    if kind not in ('categories','priorities'):
        raise Problem('Unknown setting.',404)
    name = text(name,'Name',80)
    rank = integer(sort_order,'Sort order')
    if not -1000000 <= rank <= 1000000:
        raise Problem('Sort order is out of range.')
    try:
        with transaction(db):
            remember(db,actor)
            if item_id is not None:
                item_id = integer(item_id,'Item ID')
                old = db.execute(f'SELECT * FROM {kind} WHERE id=?',(item_id,)).fetchone()
                if old is None:
                    raise Problem('Setting not found.',404)
                count = db.execute(f'SELECT count(*) FROM {kind} WHERE active=1').fetchone()[0]
                if old['active'] and not active and count <= 1:
                    raise Problem('Keep at least one active option.')
                if kind == 'priorities':
                    db.execute('UPDATE priorities SET name=?,active=?,sort_order=? WHERE id=?',(name,int(active),rank,item_id))
                else:
                    db.execute('UPDATE categories SET name=?,active=? WHERE id=?',(name,int(active),item_id))
            else:
                old = None
                if kind == 'priorities':
                    cur = db.execute('INSERT INTO priorities(name,active,sort_order) VALUES(?,?,?)',(name,int(active),rank))
                else:
                    cur = db.execute('INSERT INTO categories(name,active) VALUES(?,?)',(name,int(active)))
                item_id = cur.lastrowid
            event(db,actor,'taxonomy_changed',kind=kind,item_id=item_id,name=name,
                  active=bool(active),sort_order=rank,previous=dict(old) if old else None)
    except sqlite3.IntegrityError:
        raise Problem('An option with that name already exists.')

_md = MarkdownIt('commonmark', {'html': False, 'linkify': False})
# Disable remote images: all embedded images must be authorized attachments.
_md.disable('image')
def render_markdown(value):
    rendered = _md.render(value or '')
    return bleach.clean(rendered,
        tags={'p','br','strong','em','ul','ol','li','blockquote','pre','code','a','hr','h1','h2','h3','h4','h5','h6'},
        attributes={'a':['href','title'],'ol':['start']},
        protocols={'http','https','mailto'},strip=True)

# Help desk 0.1.1: branding and role-aware initial ticket view.
DEFAULT_HEADER_TITLE = 'Sandstorm Help Desk'


def default_ticket_scope(actor):
    return 'all' if actor.has('manageTickets') else 'mine'


def default_ticket_status(actor, scope):
    return 'open' if actor.has('manageTickets') and scope == 'all' else ''


def header_title(db):
    row = db.execute("SELECT value FROM app_settings WHERE key='header_title'").fetchone()
    return row[0] if row and row[0] else DEFAULT_HEADER_TITLE


def set_header_title(db, actor, value):
    require(actor, 'manageSettings')
    value = text(value, 'Header title', 80)
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise Problem('Header title must be a single line without control characters.')
    with transaction(db):
        remember(db, actor)
        previous = header_title(db)
        db.execute("INSERT INTO app_settings(key,value) VALUES('header_title',?) "
                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (value,))
        if previous != value:
            event(db, actor, 'header_title_changed', previous=previous, title=value)
