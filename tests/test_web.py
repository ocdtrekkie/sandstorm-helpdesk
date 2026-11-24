import io
import re
import tempfile
import unittest
import importlib.util
from helpdesk import core
from tests.test_core import png

HAS_FLASK = importlib.util.find_spec('flask') is not None
if HAS_FLASK:
    from helpdesk.web import create_app

@unittest.skipUnless(HAS_FLASK,'Flask is not installed in this environment')
class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING':True,'DATA_DIR':self.tmp.name,'SECRET_KEY':'test-only-secret',
                               'DEV_MODE':False,'SESSION_COOKIE_SECURE':False})
        self.client = self.app.test_client()
        self.owner = self.headers('requester','owner')
        self.other = self.headers('requester','other')
        self.tech = self.headers('technician','tech')
        self.admin = self.headers('administrator','admin')
        db = core.connect(self.app.config['DATABASE'])
        self.tid = core.create_ticket(db,core.Actor('owner','Owner',core.ROLES['requester']),
                                     'Web ticket','Body',1,2,[('a.png',png())])
        self.aid = db.execute('SELECT id FROM attachments').fetchone()[0]
        db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def headers(self,role,uid):
        return {'X-Sandstorm-User-Id':uid,'X-Sandstorm-Username':'Test%20User',
                'X-Sandstorm-Permissions':','.join(core.ROLES[role])}

    def csrf(self,headers):
        response = self.client.get('/tickets',headers=headers)
        self.assertEqual(response.status_code,200)
        with self.client.session_transaction() as s:
            return s['csrf']

    def post(self,path,headers,data):
        return self.client.post(path,headers=headers,data={**data,'csrf_token':self.csrf(headers)})

    def test_identity_required(self):
        self.assertEqual(self.client.get('/tickets').status_code,403)

    def test_requester_direct_ticket_access(self):
        self.assertEqual(self.client.get(f'/tickets/{self.tid}',headers=self.owner).status_code,200)
        self.assertEqual(self.client.get(f'/tickets/{self.tid}',headers=self.other).status_code,404)

    def test_attachment_enforces_parent_visibility(self):
        self.assertEqual(self.client.get(f'/attachments/{self.aid}',headers=self.owner).status_code,200)
        self.assertEqual(self.client.get(f'/attachments/{self.aid}',headers=self.other).status_code,404)

    def test_supervisor_reads_but_cannot_write_other_ticket(self):
        h = self.headers('supervisor','boss')
        self.assertEqual(self.client.get(f'/tickets/{self.tid}',headers=h).status_code,200)
        self.assertEqual(self.post(f'/tickets/{self.tid}/comments',h,{'body':'No'}).status_code,403)
        self.assertEqual(self.post(f'/tickets/{self.tid}/status',h,{'status':'closed'}).status_code,403)

    def test_csrf_required(self):
        self.csrf(self.tech)
        self.assertEqual(self.client.post(f'/tickets/{self.tid}/status',headers=self.tech,
                                         data={'status':'closed'}).status_code,400)

    def test_owner_status_workflow(self):
        path = f'/tickets/{self.tid}/status'
        self.assertEqual(self.post(path,self.tech,{'status':'closed'}).status_code,303)
        self.assertEqual(self.post(path,self.owner,{'status':'open'}).status_code,403)
        self.assertEqual(self.post('/admin/policy',self.admin,{'allow_requester_reopen':'1'}).status_code,303)
        self.assertEqual(self.post(path,self.owner,{'status':'open'}).status_code,303)

    def test_admin_and_form_pages_render(self):
        for path in ('/tickets','/tickets?scope=all','/tickets/new','/admin',f'/tickets/{self.tid}'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path,headers=self.admin).status_code,200)

    def test_nonadmin_settings_blocked(self):
        self.assertEqual(self.client.get('/admin',headers=self.tech).status_code,403)
        self.assertEqual(self.post('/admin/policy',self.tech,{'allow_requester_reopen':'1'}).status_code,403)

    def test_requester_all_view_blocked(self):
        self.assertEqual(self.client.get('/tickets?scope=all',headers=self.owner).status_code,403)

    def test_create_ticket_through_form(self):
        response = self.post('/tickets/new',self.owner,{'subject':'New ticket','body':'**Hello**',
                                                       'category':'1','priority':'2'})
        self.assertEqual(response.status_code,303)
        page = self.client.get(response.location,headers=self.owner)
        self.assertIn(b'<strong>Hello</strong>',page.data)

    def test_comment_image_through_form(self):
        response = self.post(f'/tickets/{self.tid}/comments',self.owner,
                             {'body':'Picture','images':(io.BytesIO(png()),'pic.png')})
        self.assertEqual(response.status_code,303)

    def test_search_special_characters_and_filters(self):
        for path in ('/tickets?q=%25','/tickets?q=%5C','/tickets?q=%23'+str(self.tid),
                     '/tickets?status=open&priority=2&category=1','/tickets?page=2'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path,headers=self.owner).status_code,200)

    def test_preview_is_sanitized(self):
        response = self.post('/preview',self.owner,{'body':'**OK** <script>bad</script>'})
        self.assertEqual(response.status_code,200)
        self.assertIn('<strong>OK</strong>',response.json['html'])
        self.assertNotIn('<script>',response.json['html'])

    def test_security_headers(self):
        response = self.client.get('/tickets',headers=self.owner)
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertIn("object-src 'none'",response.headers['Content-Security-Policy'])

    def test_development_identity_ignores_spoofed_headers(self):
        self.app.config.update(DEV_MODE=True,DEV_ROLE='requester',DEV_USER_ID='owner',DEV_USER_NAME='Owner')
        self.assertEqual(self.client.get('/admin',headers=self.admin).status_code,403)

    def test_secure_cookies_default_in_production(self):
        app = create_app({'DATA_DIR':self.tmp.name,'SECRET_KEY':'test','DEV_MODE':False})
        self.assertTrue(app.config['SESSION_COOKIE_SECURE'])

    def test_new_ticket_validation_retains_text(self):
        response = self.post('/tickets/new',self.owner,{'subject':'Keep me','body':'Body','category':'999','priority':'2'})
        self.assertEqual(response.status_code,400)
        self.assertIn(b'Keep me',response.data)

if __name__ == '__main__':
    unittest.main()
