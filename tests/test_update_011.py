import unittest
from helpdesk import core
from tests.test_core import CoreTests, actor
from tests.test_web import WebTests


class UpdateCoreTests(CoreTests):
    # Base class supplies isolated databases. Limit discovery of inherited tests below.
    def test_011_default_scope_and_status(self):
        for role in core.ROLES:
            a = actor(role)
            expected = 'all' if role in ('technician', 'administrator') else 'mine'
            self.assertEqual(core.default_ticket_scope(a), expected)
            self.assertEqual(core.default_ticket_status(a, 'all'), 'open' if expected == 'all' else '')
            self.assertEqual(core.default_ticket_status(a, 'mine'), '')

    def test_011_default_header_and_persistence(self):
        self.assertEqual(core.header_title(self.db), 'Sandstorm Help Desk')
        core.set_header_title(self.db, self.admin, 'Acme Support')
        self.assertEqual(core.header_title(self.db), 'Acme Support')
        another = core.connect(self.path)
        try:
            self.assertEqual(core.header_title(another), 'Acme Support')
        finally:
            another.close()

    def test_011_only_admin_changes_title(self):
        for a in (self.owner, self.supervisor, self.tech):
            self.assert_problem(403, core.set_header_title, self.db, a, 'Forbidden')

    def test_011_title_validation(self):
        for value in ('', '  ', 'X' * 81, 'Two\nlines'.replace('\\n','\n'), 'A\tB'.replace('\\t','\t')):
            self.assert_problem(400, core.set_header_title, self.db, self.admin, value)

    def test_011_title_change_audited(self):
        core.set_header_title(self.db, self.admin, 'Support')
        row = self.db.execute("SELECT * FROM ticket_events WHERE action='header_title_changed'").fetchone()
        self.assertEqual(row['actor_id'], self.admin.id)
        self.assertIsNone(row['ticket_id'])
        self.assertIn('Support', row['details'])

    def test_011_title_does_not_change_reopen_policy(self):
        core.set_reopen(self.db, self.admin, True)
        core.set_header_title(self.db, self.admin, 'Support')
        self.assertTrue(core.reopen_allowed(self.db))


class UpdateWebTests(WebTests):
    def test_011_staff_default_all_open(self):
        db = core.connect(self.app.config['DATABASE'])
        staff = core.Actor('tech', 'Tech', core.ROLES['technician'])
        closed = core.create_ticket(db, staff, 'Closed staff ticket', 'Body', 1, 2)
        core.change_status(db, staff, closed, 'closed')
        db.close()
        for headers in (self.tech, self.admin):
            page = self.client.get('/tickets', headers=headers)
            self.assertEqual(page.status_code, 200)
            self.assertIn(b'All tickets', page.data)
            self.assertIn(b'Web ticket', page.data)
            self.assertNotIn(b'Closed staff ticket', page.data)
        # Explicit empty status means All statuses, not the role default.
        page = self.client.get('/tickets?scope=all&status=', headers=self.tech)
        self.assertIn(b'Closed staff ticket', page.data)

    def test_011_explicit_mine_still_available(self):
        page = self.client.get('/tickets?scope=mine', headers=self.tech)
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'Web ticket', page.data)
        self.assertIn(b'My tickets', page.data)

    def test_011_supervisor_still_defaults_to_own(self):
        h = self.headers('supervisor', 'boss')
        page = self.client.get('/tickets', headers=h)
        self.assertNotIn(b'Web ticket', page.data)
        page = self.client.get('/tickets?scope=all', headers=h)
        self.assertIn(b'Web ticket', page.data)

    def test_011_title_setting_and_escaping(self):
        response = self.post('/admin/branding', self.admin, {'header_title': '<b>Support</b>'})
        self.assertEqual(response.status_code, 303)
        page = self.client.get('/tickets', headers=self.owner)
        self.assertIn(b'&lt;b&gt;Support&lt;/b&gt;', page.data)
        self.assertNotIn(b'<b>Support</b>', page.data)

    def test_011_nonadmin_cannot_change_title(self):
        self.assertEqual(self.post('/admin/branding', self.tech, {'header_title':'No'}).status_code, 403)

    def test_011_branding_csrf_required(self):
        self.csrf(self.admin)
        response = self.client.post('/admin/branding', headers=self.admin, data={'header_title':'No'})
        self.assertEqual(response.status_code, 400)

    def test_011_branding_form_and_theme(self):
        page = self.client.get('/admin', headers=self.admin)
        self.assertIn(b'name="header_title"', page.data)
        css = self.client.get('/static/app.css', headers=self.owner)
        self.assertIn(b'prefers-color-scheme: dark', css.data)
        self.assertIn(b'color-scheme: light dark', css.data)


def load_tests(loader, tests, pattern):
    # Avoid running the inherited 0.1.0 tests a second time.
    suite = unittest.TestSuite()
    for cls in (UpdateCoreTests, UpdateWebTests):
        for name in sorted(cls.__dict__):
            if name.startswith('test_011_'):
                suite.addTest(cls(name))
    return suite
