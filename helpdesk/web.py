import hmac
import io
import os
import secrets
from pathlib import Path
from urllib.parse import unquote

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from markupsafe import Markup
from werkzeug.exceptions import HTTPException

from . import core


def secret_for(directory):
    path = Path(directory) / 'session-secret'
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        value = path.read_bytes()
    else:
        value = secrets.token_bytes(48)
        with os.fdopen(fd,'wb') as f:
            f.write(value)
    if len(value) < 32:
        raise RuntimeError('Invalid persistent session secret.')
    return value


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATA_DIR=os.environ.get('HELPDESK_DATA_DIR','./instance'),
        DEV_MODE=os.environ.get('HELPDESK_DEV_MODE') == '1',
        DEV_USER_ID=os.environ.get('HELPDESK_DEV_USER_ID','local-admin'),
        DEV_USER_NAME=os.environ.get('HELPDESK_DEV_USER_NAME','Local administrator'),
        DEV_ROLE=os.environ.get('HELPDESK_DEV_ROLE','administrator'),
        MAX_CONTENT_LENGTH=105 * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=1024 * 1024,
        MAX_FORM_PARTS=40,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_NAME='helpdesk_session',
    )
    if config:
        app.config.update(config)
    data_dir = Path(app.config['DATA_DIR'])
    data_dir.mkdir(mode=0o700,parents=True,exist_ok=True)
    app.config.setdefault('DATABASE',str(data_dir/'helpdesk.sqlite3'))
    if not config or 'SESSION_COOKIE_SECURE' not in config:
        app.config['SESSION_COOKIE_SECURE'] = not app.config['DEV_MODE']
    app.secret_key = app.config.get('SECRET_KEY') or secret_for(data_dir)
    if app.config['DEV_MODE'] and app.config['DEV_ROLE'] not in core.ROLES:
        raise RuntimeError('Unknown development role.')
    core.initialize(app.config['DATABASE'])

    def db():
        if 'db' not in g:
            g.db = core.connect(app.config['DATABASE'])
        return g.db

    @app.teardown_appcontext
    def close_db(error=None):
        conn = g.pop('db',None)
        if conn is not None:
            conn.close()

    @app.before_request
    def authenticate():
        if app.config['DEV_MODE']:
            actor = core.Actor(app.config['DEV_USER_ID'],app.config['DEV_USER_NAME'],
                               core.ROLES[app.config['DEV_ROLE']])
        else:
            uid = request.headers.get('X-Sandstorm-User-Id','').strip()
            if not uid or len(uid) > 256:
                abort(403,description='Open this help desk as an identified Sandstorm user.')
            name = unquote(request.headers.get('X-Sandstorm-Username','User'))[:200]
            perms = frozenset(p.strip() for p in request.headers.get('X-Sandstorm-Permissions','').split(',')
                              if p.strip() in core.PERMISSIONS)
            actor = core.Actor(uid,name,perms)
        g.actor = actor
        if session.get('actor_id') != actor.id:
            session.clear()
            session['actor_id'] = actor.id
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        if request.method not in ('GET','HEAD','OPTIONS'):
            supplied = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token','')
            if not supplied or not hmac.compare_digest(supplied.encode('utf-8'),session['csrf'].encode('utf-8')):
                abort(400,description='The form expired or failed its security check. Reload and try again.')

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store, private'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'")
        # Sandstorm embeds grains; deliberately do not set X-Frame-Options DENY/SAMEORIGIN.
        return response

    @app.context_processor
    def context():
        return dict(actor=getattr(g,'actor',None),csrf_token=session.get('csrf',''),
                    dev_mode=app.config['DEV_MODE'],header_title=core.header_title(db()))

    app.jinja_env.filters['markdown'] = lambda value: Markup(core.render_markdown(value))

    @app.errorhandler(core.Problem)
    def problem(error):
        return render_template('error.html',message=str(error),code=error.status),error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        return render_template('error.html',message=error.description,code=error.code),error.code

    def options(include_inactive=False):
        where = '' if include_inactive else ' WHERE active=1'
        categories = db().execute('SELECT * FROM categories'+where+' ORDER BY name').fetchall()
        priorities = db().execute('SELECT * FROM priorities'+where+' ORDER BY sort_order,id').fetchall()
        return categories,priorities

    def uploads():
        result = []
        for upload in request.files.getlist('images'):
            if upload.filename:
                result.append((upload.filename,upload.stream.read(core.MAX_IMAGE+1)))
                if len(result) > core.MAX_IMAGES:
                    raise core.Problem('At most 10 images are allowed per submission.')
        return result

    @app.get('/')
    def index():
        return redirect(url_for('ticket_list'))

    @app.get('/tickets')
    def ticket_list():
        core.require(g.actor,'createTickets')
        scope = request.args.get('scope',core.default_ticket_scope(g.actor))
        if scope not in ('mine','all'):
            raise core.Problem('Unknown ticket view.')
        if scope == 'all':
            core.require(g.actor,'viewAllTickets')
        conditions,params = [],[]
        if scope == 'mine':
            conditions.append('t.requester_id=?')
            params.append(g.actor.id)
        status = request.args.get('status',core.default_ticket_status(g.actor,scope))
        if status:
            if status not in ('open','closed'):
                raise core.Problem('Unknown status filter.')
            conditions.append('t.status=?')
            params.append(status)
        for key,column in [('category','t.category_id'),('priority','t.priority_id')]:
            if request.args.get(key):
                conditions.append(column+'=?')
                params.append(core.integer(request.args[key],key))
        query = core.text(request.args.get('q',''),'Search',200,False)
        if query:
            escaped = query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            conditions.append("(t.subject LIKE ? ESCAPE '\\' OR CAST(t.id AS TEXT)=?)")
            params.extend(['%'+escaped+'%',query.lstrip('#')])
        where = ' WHERE '+' AND '.join(conditions) if conditions else ''
        page = max(1,min(core.integer(request.args.get('page',1),'Page'),1000000))
        total = db().execute('SELECT count(*) FROM tickets t'+where,params).fetchone()[0]
        rows = db().execute("""
          SELECT t.*,u.name requester_name,c.name category,p.name priority
          FROM tickets t JOIN users u ON u.id=t.requester_id
          JOIN categories c ON c.id=t.category_id JOIN priorities p ON p.id=t.priority_id
          """+where+' ORDER BY t.updated_at DESC,t.id DESC LIMIT 30 OFFSET ?',params+[(page-1)*30]).fetchall()
        categories,priorities = options(True)
        def page_link(n):
            args = request.args.to_dict()
            args['page'] = n
            return url_for('ticket_list',**args)
        return render_template('list.html',tickets=rows,categories=categories,priorities=priorities,
                               total=total,page=page,page_link=page_link,scope=scope,current_status=status)

    @app.route('/tickets/new',methods=['GET','POST'])
    def new_ticket():
        core.require(g.actor,'createTickets')
        categories,priorities = options()
        error = None
        if request.method == 'POST':
            try:
                tid = core.create_ticket(db(),g.actor,request.form.get('subject',''),request.form.get('body',''),
                                         request.form.get('category'),request.form.get('priority'),uploads())
                flash('Ticket created.')
                return redirect(url_for('ticket_detail',tid=tid),code=303)
            except core.Problem as exc:
                if exc.status != 400:
                    raise
                error = str(exc)
        return render_template('new.html',categories=categories,priorities=priorities,error=error),400 if error else 200

    @app.get('/tickets/<int:tid>')
    def ticket_detail(tid):
        t = core.ticket(db(),g.actor,tid)
        comments = db().execute("""
          SELECT c.*,u.name author_name FROM comments c JOIN users u ON u.id=c.author_id
          WHERE c.ticket_id=? ORDER BY c.id""",(tid,)).fetchall()
        images = db().execute('SELECT id,comment_id,original_name FROM attachments WHERE ticket_id=? ORDER BY id',(tid,)).fetchall()
        events = db().execute("""
          SELECT e.*,u.name actor_name FROM ticket_events e JOIN users u ON u.id=e.actor_id
          WHERE e.ticket_id=? ORDER BY e.id""",(tid,)).fetchall()
        categories,priorities = options(True)
        return render_template('ticket.html',ticket=t,comments=comments,images=images,events=events,
                               can_comment=g.actor.can_comment(t),
                               can_reopen=g.actor.can_reopen(t,core.reopen_allowed(db())),
                               categories=categories,priorities=priorities)

    @app.post('/tickets/<int:tid>/comments')
    def comment(tid):
        # Check visibility before processing uploaded image bytes.
        t = core.ticket(db(),g.actor,tid)
        if not g.actor.can_comment(t):
            raise core.Problem('You cannot comment on this ticket.',403)
        core.add_comment(db(),g.actor,tid,request.form.get('body',''),uploads())
        flash('Comment added.')
        return redirect(url_for('ticket_detail',tid=tid),code=303)

    @app.post('/tickets/<int:tid>/status')
    def status(tid):
        core.change_status(db(),g.actor,tid,request.form.get('status'))
        flash('Ticket status updated.')
        return redirect(url_for('ticket_detail',tid=tid),code=303)

    @app.post('/tickets/<int:tid>/metadata')
    def metadata(tid):
        core.change_metadata(db(),g.actor,tid,request.form.get('category'),request.form.get('priority'))
        flash('Category and priority updated.')
        return redirect(url_for('ticket_detail',tid=tid),code=303)

    @app.get('/attachments/<int:aid>')
    def attachment(aid):
        row = db().execute('SELECT ticket_id FROM attachments WHERE id=?',(aid,)).fetchone()
        if row is None:
            abort(404)
        core.ticket(db(),g.actor,row['ticket_id'])
        row = db().execute('SELECT data,mime,storage_key FROM attachments WHERE id=?',(aid,)).fetchone()
        return send_file(io.BytesIO(row['data']),mimetype=row['mime'],download_name=row['storage_key'],
                         as_attachment=request.args.get('download')=='1',conditional=False,max_age=0)

    @app.post('/preview')
    def preview():
        core.require(g.actor,'createTickets')
        value = core.text(request.form.get('body',''),'Preview',50000,False)
        return jsonify(html=core.render_markdown(value))

    @app.get('/admin')
    def admin():
        core.require(g.actor,'manageSettings')
        categories,priorities = options(True)
        events = db().execute("""
          SELECT e.*,u.name actor_name FROM ticket_events e JOIN users u ON u.id=e.actor_id
          WHERE ticket_id IS NULL ORDER BY e.id DESC LIMIT 50""").fetchall()
        return render_template('admin.html',categories=categories,priorities=priorities,
                               allowed=core.reopen_allowed(db()),events=events)

    @app.post('/admin/branding')
    def branding():
        core.set_header_title(db(),g.actor,request.form.get('header_title',''))
        flash('Header title saved.')
        return redirect(url_for('admin'),code=303)

    @app.post('/admin/policy')
    def policy():
        core.set_reopen(db(),g.actor,request.form.get('allow_requester_reopen')=='1')
        flash('Reopening policy saved.')
        return redirect(url_for('admin'),code=303)

    @app.post('/admin/<kind>')
    def taxonomy(kind):
        item_id = request.form.get('id') or None
        core.save_taxonomy(db(),g.actor,kind,item_id,request.form.get('name',''),
                           request.form.get('active')=='1',request.form.get('sort_order','0'))
        flash('Option saved.')
        return redirect(url_for('admin'),code=303)

    return app
