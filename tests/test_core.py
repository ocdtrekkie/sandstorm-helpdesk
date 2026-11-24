import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from helpdesk import core as c


def actor(role, uid=None):
    return c.Actor(uid or role, role.title(), c.ROLES[role])


def png():
    buf = io.BytesIO()
    Image.new('RGB',(6,6),'blue').save(buf,'PNG')
    return buf.getvalue()


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'test.sqlite3'
        c.initialize(self.path)
        self.db = c.connect(self.path)
        self.owner = actor('requester','owner')
        self.other = actor('requester','other')
        self.supervisor = actor('supervisor')
        self.tech = actor('technician')
        self.admin = actor('administrator')
        self.tid = c.create_ticket(self.db,self.owner,'A test ticket','**Description**',1,2)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def closed(self):
        c.change_status(self.db,self.tech,self.tid,'closed')

    def assert_problem(self, status, func, *args):
        with self.assertRaises(c.Problem) as got:
            func(*args)
        self.assertEqual(got.exception.status,status)

    def test_all_roles_create_owned_tickets(self):
        for role in c.ROLES:
            with self.subTest(role=role):
                a = actor(role)
                tid = c.create_ticket(self.db,a,'Ticket','Description',1,2)
                self.assertEqual(c.ticket(self.db,a,tid)['requester_id'],a.id)

    def test_anonymous_or_permissionless_cannot_create(self):
        self.assert_problem(403,c.create_ticket,self.db,c.Actor('x','X',frozenset()),'X','Y',1,2)

    def test_requester_own_only(self):
        self.assertEqual(c.ticket(self.db,self.owner,self.tid)['id'],self.tid)
        self.assert_problem(404,c.ticket,self.db,self.other,self.tid)

    def test_staff_visibility(self):
        for a in (self.supervisor,self.tech,self.admin):
            with self.subTest(actor=a.id):
                self.assertEqual(c.ticket(self.db,a,self.tid)['id'],self.tid)

    def test_missing_ticket(self):
        self.assert_problem(404,c.ticket,self.db,self.admin,9999)

    def test_owner_can_comment_with_image(self):
        c.add_comment(self.db,self.owner,self.tid,'A reply',[('photo.png',png())])
        self.assertEqual(self.db.execute('SELECT count(*) FROM comments').fetchone()[0],1)
        image = self.db.execute('SELECT * FROM attachments').fetchone()
        self.assertIsNotNone(image['comment_id'])
        self.assertEqual(image['mime'],'image/png')

    def test_owner_can_add_image_without_text(self):
        c.add_comment(self.db,self.owner,self.tid,'',[('photo.png',png())])
        self.assertEqual(self.db.execute('SELECT count(*) FROM comments').fetchone()[0],1)

    def test_supervisor_comments_on_own_only(self):
        own = c.create_ticket(self.db,self.supervisor,'Own','Body',1,2)
        c.add_comment(self.db,self.supervisor,own,'Reply')
        self.assert_problem(403,c.add_comment,self.db,self.supervisor,self.tid,'Reply')

    def test_other_requester_cannot_comment(self):
        self.assert_problem(404,c.add_comment,self.db,self.other,self.tid,'Intrusion')

    def test_technician_and_admin_can_comment_on_any_open(self):
        for a in (self.tech,self.admin):
            c.add_comment(self.db,a,self.tid,'Staff response')
        self.assertEqual(self.db.execute('SELECT count(*) FROM comments').fetchone()[0],2)

    def test_empty_comment_rejected(self):
        self.assert_problem(400,c.add_comment,self.db,self.owner,self.tid,'  ')

    def test_closed_ticket_blocks_comments_for_every_role(self):
        self.closed()
        for a in (self.owner,self.supervisor,self.tech,self.admin):
            with self.subTest(actor=a.id):
                self.assert_problem(403,c.add_comment,self.db,a,self.tid,'No')

    def test_only_staff_close(self):
        for a in (self.owner,self.supervisor):
            self.assert_problem(403,c.change_status,self.db,a,self.tid,'closed')
        self.closed()
        t = c.ticket(self.db,self.tech,self.tid)
        self.assertEqual(t['status'],'closed')
        self.assertEqual(t['closed_by'],self.tech.id)
        self.assertIsNotNone(t['closed_at'])

    def test_admin_can_close(self):
        c.change_status(self.db,self.admin,self.tid,'closed')
        self.assertEqual(c.ticket(self.db,self.admin,self.tid)['status'],'closed')

    def test_default_reopen_disabled(self):
        self.assertFalse(c.reopen_allowed(self.db))
        self.closed()
        self.assert_problem(403,c.change_status,self.db,self.owner,self.tid,'open')

    def test_owner_reopen_enabled_and_closure_cleared(self):
        self.closed()
        c.set_reopen(self.db,self.admin,True)
        c.change_status(self.db,self.owner,self.tid,'open')
        t = c.ticket(self.db,self.owner,self.tid)
        self.assertEqual(t['status'],'open')
        self.assertIsNone(t['closed_at'])
        self.assertIsNone(t['closed_by'])
        c.add_comment(self.db,self.owner,self.tid,'Thanks!')

    def test_supervisor_reopens_own_only_when_enabled(self):
        own = c.create_ticket(self.db,self.supervisor,'Own','Body',1,2)
        c.change_status(self.db,self.tech,own,'closed')
        self.assert_problem(403,c.change_status,self.db,self.supervisor,own,'open')
        c.set_reopen(self.db,self.admin,True)
        c.change_status(self.db,self.supervisor,own,'open')
        self.closed()
        self.assert_problem(403,c.change_status,self.db,self.supervisor,self.tid,'open')

    def test_other_requester_cannot_reopen_even_when_enabled(self):
        self.closed()
        c.set_reopen(self.db,self.admin,True)
        self.assert_problem(404,c.change_status,self.db,self.other,self.tid,'open')

    def test_staff_always_reopen(self):
        for enabled in (False,True):
            c.set_reopen(self.db,self.admin,enabled)
            for a in (self.tech,self.admin):
                with self.subTest(enabled=enabled,actor=a.id):
                    self.closed()
                    c.change_status(self.db,a,self.tid,'open')

    def test_policy_revocation_immediate(self):
        c.set_reopen(self.db,self.admin,True)
        self.closed()
        c.set_reopen(self.db,self.admin,False)
        self.assert_problem(403,c.change_status,self.db,self.owner,self.tid,'open')

    def test_nonadmins_cannot_change_policy(self):
        for a in (self.owner,self.supervisor,self.tech):
            self.assert_problem(403,c.set_reopen,self.db,a,True)
        self.assertFalse(c.reopen_allowed(self.db))

    def test_repeated_status_cycles_record_history(self):
        for _ in range(3):
            self.closed()
            c.change_status(self.db,self.tech,self.tid,'open')
        actions = [r[0] for r in self.db.execute('SELECT action FROM ticket_events WHERE ticket_id=?',(self.tid,))]
        self.assertEqual(actions.count('closed'),3)
        self.assertEqual(actions.count('reopened'),3)

    def test_close_already_closed_conflict(self):
        self.closed()
        self.assert_problem(409,c.change_status,self.db,self.tech,self.tid,'closed')

    def test_invalid_status_rejected(self):
        self.assert_problem(400,c.change_status,self.db,self.tech,self.tid,'deleted')

    def test_only_staff_change_classification(self):
        for a in (self.owner,self.supervisor):
            self.assert_problem(403,c.change_metadata,self.db,a,self.tid,2,3)
        c.change_metadata(self.db,self.tech,self.tid,2,3)
        t = c.ticket(self.db,self.owner,self.tid)
        self.assertEqual((t['category_id'],t['priority_id']),(2,3))

    def test_inactive_historical_option_retained(self):
        c.save_taxonomy(self.db,self.admin,'categories',1,'General',False)
        t = c.ticket(self.db,self.owner,self.tid)
        self.assertEqual(t['category'],'General')
        c.change_metadata(self.db,self.tech,self.tid,1,3)
        self.assert_problem(400,c.create_ticket,self.db,self.owner,'New','Body',1,2)

    def test_inactive_option_cannot_be_newly_selected(self):
        c.save_taxonomy(self.db,self.admin,'categories',2,'Hardware',False)
        self.assert_problem(400,c.change_metadata,self.db,self.tech,self.tid,2,2)

    def test_admin_can_create_taxonomy(self):
        c.save_taxonomy(self.db,self.admin,'categories',None,'Billing')
        c.save_taxonomy(self.db,self.admin,'priorities',None,'Emergency',True,-10)
        row = self.db.execute('SELECT name FROM priorities ORDER BY sort_order LIMIT 1').fetchone()
        self.assertEqual(row[0],'Emergency')

    def test_nonadmins_cannot_manage_taxonomy(self):
        for a in (self.owner,self.supervisor,self.tech):
            self.assert_problem(403,c.save_taxonomy,self.db,a,'categories',None,'No')

    def test_case_insensitive_unique_names(self):
        self.assert_problem(400,c.save_taxonomy,self.db,self.admin,'categories',None,'GENERAL')

    def test_last_active_option_cannot_be_disabled(self):
        for row in self.db.execute('SELECT * FROM categories WHERE id!=1').fetchall():
            c.save_taxonomy(self.db,self.admin,'categories',row['id'],row['name'],False)
        self.assert_problem(400,c.save_taxonomy,self.db,self.admin,'categories',1,'General',False)

    def test_ticket_validation(self):
        for subject,body,category,priority in [('', 'Body',1,2),('X'*201,'Body',1,2),('X','',1,2),('X','Y',999,2),('X','Y',1,'oops')]:
            with self.subTest(subject=subject[:10],category=category,priority=priority):
                self.assert_problem(400,c.create_ticket,self.db,self.owner,subject,body,category,priority)

    def test_sql_text_not_executable(self):
        value = "'); DROP TABLE tickets; --"
        tid = c.create_ticket(self.db,self.owner,value,value,1,2)
        self.assertEqual(c.ticket(self.db,self.owner,tid)['subject'],value)
        self.assertEqual(self.db.execute('SELECT count(*) FROM tickets').fetchone()[0],2)

    def test_image_validation_and_limits(self):
        for files in [[('script.svg',b'<svg/>')],[('fake.jpg',b'<script>alert(1)</script>')],
                      [('empty.png',b'')],[('huge.png',b'x'*(c.MAX_IMAGE+1))],
                      [('photo.png',png())]*11]:
            with self.subTest(count=len(files),size=len(files[0][1])):
                self.assert_problem(400,c.prepare_uploads,files)

    def test_image_name_and_content_are_safely_normalized(self):
        image = c.prepare_uploads([('../../evil.html',png()+b'<script>bad</script>')])[0]
        self.assertEqual(image.name,'evil.html')
        self.assertTrue(image.storage_key.endswith('.png'))
        self.assertNotIn(b'<script>',image.data)
        with Image.open(io.BytesIO(image.data)) as im:
            self.assertEqual(im.format,'PNG')

    def test_original_ticket_images(self):
        tid = c.create_ticket(self.db,self.owner,'Image ticket','Body',1,2,[('a.png',png())])
        row = self.db.execute('SELECT * FROM attachments WHERE ticket_id=?',(tid,)).fetchone()
        self.assertIsNone(row['comment_id'])
        self.assertTrue(len(row['data']) > 0)

    def test_invalid_image_leaves_no_ticket(self):
        count = self.db.execute('SELECT count(*) FROM tickets').fetchone()[0]
        self.assert_problem(400,c.create_ticket,self.db,self.owner,'Broken','Body',1,2,[('bad.png',b'bad')])
        self.assertEqual(self.db.execute('SELECT count(*) FROM tickets').fetchone()[0],count)

    def test_transaction_failure_rolls_back(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with c.transaction(self.db):
                self.db.execute("INSERT INTO categories(name) VALUES('temporary')")
                self.db.execute("INSERT INTO categories(name) VALUES('General')")
        self.assertIsNone(self.db.execute("SELECT id FROM categories WHERE name='temporary'").fetchone())

    def test_attachment_cannot_reference_another_tickets_comment(self):
        c.add_comment(self.db,self.owner,self.tid,'Comment')
        cid = self.db.execute('SELECT id FROM comments').fetchone()[0]
        other = c.create_ticket(self.db,self.other,'Other','Body',1,2)
        with self.assertRaises(sqlite3.IntegrityError):
            with c.transaction(self.db):
                c.save_uploads(self.db,self.owner,other,cid,c.prepare_uploads([('a.png',png())]))

    def test_markdown_formatting(self):
        html = c.render_markdown('**bold** and *italic*\n\n- one\n- two\n\n`code`')
        for tag in ('<strong>','<em>','<ul>','<code>'):
            self.assertIn(tag,html)

    def test_markdown_rejects_xss_and_remote_images(self):
        html = c.render_markdown('<script>alert(1)</script>\n\n[x](javascript:alert(1))\n\n![tracker](https://evil.example/a.png)')
        self.assertNotIn('<script>',html)
        self.assertNotIn('href="javascript:',html)
        self.assertNotIn('<img',html)

    def test_initialization_is_idempotent(self):
        c.initialize(self.path)
        self.assertEqual(self.db.execute('SELECT count(*) FROM categories').fetchone()[0],4)
        self.assertEqual(self.db.execute('SELECT count(*) FROM schema_migrations').fetchone()[0],1)

    def test_display_name_does_not_grant_ownership(self):
        impostor = c.Actor('impostor',self.owner.name,c.ROLES['requester'])
        self.assert_problem(404,c.ticket,self.db,impostor,self.tid)

    def test_policy_changes_are_audited(self):
        c.set_reopen(self.db,self.admin,True)
        row = self.db.execute("SELECT * FROM ticket_events WHERE action='requester_reopen_policy_changed'").fetchone()
        self.assertEqual(row['actor_id'],self.admin.id)
        self.assertIsNone(row['ticket_id'])


if __name__ == '__main__':
    unittest.main()
