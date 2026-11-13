"""
JESCA v3 - Full system audit suite.

Covers:
  1. RBAC matrix auto-derived from route decorators (Admin/Staff/Teknisi/Auditor x every GET route).
  2. Mode Akses Khusus (Sudo) guard on sudo-protected routes.
  3. Cross-role end-to-end workflows (PO lifecycle -> asset, maintenance, feedback,
     accounts + API key, transfer, bulk, attachments, CSV import, profile, backup).

All records created here use the '__AUDIT' prefix and are removed in tearDownClass.
"""
import ast
import glob
import io
import os
import re
import unittest
from datetime import datetime

import app as jesca_app
from config import BACKUP_FOLDER, PO_ATTACHMENT_FOLDER
from extensions import db
from models import (
    ActivityLog, Asset, AssetAttachment, PurchaseOrder, SystemFeedback, User, Vendor
)

PWD = 'Audit12345'
ROLES = ['Admin', 'Staff', 'Teknisi', 'Auditor']
TEST_USERS = {'Staff': '__audit_staff', 'Teknisi': '__audit_teknisi', 'Auditor': '__audit_auditor'}
# GET routes that legitimately answer with a redirect for allowed users
REDIRECT_OK = {
    '/', '/users',
    '/login',                     # logged-in users are sent to Beranda
    '/change-password-required',  # only shown when force_password_change is set
    '/confirm-sudo',              # already in sudo -> forwards to /settings
    '/admin/import-report/csv',   # no import report in session -> back to Backup & DB
}
# logout ends session, check-update needs internet, /api/v1 uses X-API-Key (tested separately)
SKIP_GET = {'/logout', '/api/system/check-update', '/api/v1/assets'}


def _derive_access_rules():
    """Map endpoint name -> (allowed_roles or None for any logged-in user, needs_sudo, needs_login)."""
    bp_names = {}
    rules = {}
    for path in glob.glob(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'routes', '*.py')):
        src = open(path, encoding='utf-8').read()
        tree = ast.parse(src)
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                    and getattr(node.value.func, 'id', '') == 'Blueprint':
                bp_names[node.targets[0].id] = node.value.args[0].value
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            allowed, sudo, login, bp = None, False, False, None
            for d in node.decorator_list:
                txt = ast.unparse(d)
                m = re.match(r'(\w+)\.route\(', txt)
                if m:
                    bp = bp_names.get(m.group(1))
                if txt == 'login_required':
                    login = True
                if txt == 'admin_required':
                    allowed = {'Admin', 'Administrator'}
                if txt == 'sudo_required':
                    sudo = True
                if txt.startswith('role_required('):
                    allowed = {a.value for a in d.args}
            if bp:
                rules[f'{bp}.{node.name}'] = (allowed, sudo, login)
    return rules


class TestJescaFullAudit(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = jesca_app.app
        cls.app.config['WTF_CSRF_ENABLED'] = False
        cls.started = datetime.utcnow()
        cls.backups_before = set(os.listdir(BACKUP_FOLDER))
        with cls.app.app_context():
            for role, uname in TEST_USERS.items():
                u = User.query.filter_by(username=uname).first()
                if not u:
                    u = User(username=uname, full_name=f'Audit {role}', role=role)
                    db.session.add(u)
                u.role = role
                u.is_active = True
                u.force_password_change = False
                u.failed_login_count = 0
                u.locked_until = None
                u.set_password(PWD)
            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            for po in PurchaseOrder.query.filter(PurchaseOrder.title.like('__AUDIT%')).all():
                for fn in (po.order_proof, po.receipt_proof):
                    if fn:
                        fp = os.path.join(PO_ATTACHMENT_FOLDER, fn)
                        if os.path.exists(fp):
                            os.remove(fp)
                Asset.query.filter_by(po_id=po.id).delete()
                db.session.delete(po)
            for a in Asset.query.filter(Asset.name.like('__AUDIT%')).all():
                db.session.delete(a)
            Vendor.query.filter(Vendor.name.like('__AUDIT%')).delete(synchronize_session=False)
            SystemFeedback.query.filter(SystemFeedback.message.like('__AUDIT%')).delete(synchronize_session=False)
            User.query.filter(User.username.like('__audit%')).delete(synchronize_session=False)
            ActivityLog.query.filter(ActivityLog.created_at >= cls.started).delete(synchronize_session=False)
            db.session.commit()
        for f in set(os.listdir(BACKUP_FOLDER)) - cls.backups_before:
            try:
                os.remove(os.path.join(BACKUP_FOLDER, f))
            except OSError:
                pass

    # ---------- helpers ----------
    def login(self, role, sudo=False):
        c = self.app.test_client()
        uname, pwd = ('Admin', 'Admin123') if role == 'Admin' else (TEST_USERS[role], PWD)
        r = c.post('/login', data={'username': uname, 'password': pwd})
        self.assertEqual(r.status_code, 302, f'login {role} failed')
        self.assertNotIn('/login', r.headers.get('Location', ''), f'login {role} rejected')
        if sudo:
            s = c.post('/confirm-sudo', data={'password': 'Admin123'})
            self.assertIn(s.status_code, (200, 302))
        return c

    def assertNo500(self, resp, label):
        self.assertLess(resp.status_code, 500, f'{label} -> HTTP {resp.status_code}')

    # ---------- 1. RBAC matrix ----------
    def test_01_rbac_matrix_all_get_routes(self):
        rules = _derive_access_rules()
        get_routes = []
        for rule in self.app.url_map.iter_rules():
            if 'GET' in rule.methods and not rule.arguments and rule.endpoint != 'static' \
                    and rule.rule not in SKIP_GET:
                get_routes.append((rule.rule, rule.endpoint))
        self.assertGreater(len(get_routes), 30)

        failures = []
        for role in ROLES:
            c = self.login(role, sudo=(role == 'Admin'))
            for path, ep in sorted(get_routes):
                allowed, _sudo, login_req = rules.get(ep, (None, False, False))
                may = allowed is None or role in allowed
                r = c.get(path)
                if r.status_code >= 500:
                    failures.append(f'[{role}] {path} -> 500')
                    continue
                if may:
                    ok = r.status_code == 200 or (r.status_code == 302 and path in REDIRECT_OK)
                    if not ok:
                        failures.append(f'[{role}] {path} expected ALLOWED got {r.status_code} -> {r.headers.get("Location")}')
                else:
                    if r.status_code == 200:
                        failures.append(f'[{role}] {path} expected DENIED but got 200')
        self.assertEqual(failures, [], '\n' + '\n'.join(failures))

    def test_02_anonymous_and_sudo_guards(self):
        rules = _derive_access_rules()
        anon = self.app.test_client()
        failures = []
        admin_nosudo = self.login('Admin', sudo=False)
        for rule in self.app.url_map.iter_rules():
            if 'GET' not in rule.methods or rule.arguments or rule.endpoint == 'static' or rule.rule in SKIP_GET:
                continue
            allowed, sudo, login_req = rules.get(rule.endpoint, (None, False, False))
            if login_req:
                r = anon.get(rule.rule)
                if r.status_code not in (302, 401):
                    failures.append(f'[anon] {rule.rule} should require login, got {r.status_code}')
            if sudo:
                r = admin_nosudo.get(rule.rule)
                if r.status_code != 302 or 'confirm-sudo' not in r.headers.get('Location', ''):
                    failures.append(f'[admin no-sudo] {rule.rule} should redirect to confirm-sudo, got {r.status_code}')
        # lock sudo works
        c = self.login('Admin', sudo=True)
        self.assertEqual(c.get('/settings').status_code, 200)
        c.post('/settings/lock-sudo')
        r = c.get('/settings')
        if r.status_code != 302:
            failures.append(f'lock-sudo did not re-lock /settings (got {r.status_code})')
        self.assertEqual(failures, [], '\n' + '\n'.join(failures))

    # ---------- 2. PO lifecycle across roles ----------
    def test_03_po_full_lifecycle_staff_admin_to_asset(self):
        staff = self.login('Staff')
        admin = self.login('Admin')
        r = staff.post('/purchase-orders/create', data={
            'title': '__AUDIT_PO_FLOW', 'notes': 'audit',
            'item_name[]': ['__AUDIT Monitor'], 'category[]': ['Tech'],
            'quantity[]': ['2'], 'unit_price[]': ['1.500.000'], 'specification[]': ['24 inch'],
        })
        self.assertNo500(r, 'staff create PO')
        with self.app.app_context():
            po = PurchaseOrder.query.filter_by(title='__AUDIT_PO_FLOW').first()
            self.assertIsNotNone(po, 'Staff could not create PO')
            po_id, item_id = po.id, po.items[0].id
            self.assertEqual(po.status, 'DRAFT')
            self.assertAlmostEqual(po.items[0].unit_price, 1500000.0)

        self.assertNo500(staff.get(f'/purchase-orders/{po_id}/edit'), 'staff edit PO page')
        self.assertNo500(staff.post(f'/purchase-orders/{po_id}/submit'), 'submit')
        # Staff must NOT approve
        staff.post(f'/purchase-orders/{po_id}/approve')
        with self.app.app_context():
            self.assertEqual(db.session.get(PurchaseOrder, po_id).status, 'SUBMITTED')
        self.assertNo500(admin.post(f'/purchase-orders/{po_id}/approve'), 'approve')
        self.assertNo500(staff.post(f'/purchase-orders/{po_id}/order', data={
            'order_notes': 'dipesan', 'order_proof': (io.BytesIO(b'%PDF-1.4 dp'), 'dp.pdf')},
            content_type='multipart/form-data'), 'order')
        # receive without proof must be blocked
        staff.post(f'/purchase-orders/{po_id}/receive', data={'receipt_notes': 'x'})
        with self.app.app_context():
            self.assertEqual(db.session.get(PurchaseOrder, po_id).status, 'ORDERED')
        self.assertNo500(staff.post(f'/purchase-orders/{po_id}/receive', data={
            'receipt_notes': 'tiba', 'receipt_proof': (io.BytesIO(b'%PDF-1.4 bast'), 'bast.pdf')},
            content_type='multipart/form-data'), 'receive')
        self.assertNo500(staff.post(f'/purchase-orders/{po_id}/items/{item_id}/convert', data={
            'name': '__AUDIT Monitor Unit 1', 'location': 'Gudang Audit'}), 'convert')

        with self.app.app_context():
            po = db.session.get(PurchaseOrder, po_id)
            self.assertEqual(po.status, 'RECEIVED')
            self.assertIsNotNone(po.receipt_proof)
            self.assertEqual(Asset.query.filter_by(po_id=po_id).count(), 1, 'PO item was not converted to asset')
            self.assertEqual(len(po.history_entries) >= 4, True)

        for path in (f'/purchase-orders/{po_id}', f'/purchase-orders/{po_id}/print',
                     '/purchase-orders/export/csv', '/purchase-orders/export/pdf'):
            self.assertEqual(admin.get(path).status_code, 200, path)
        # attachment download through blueprint
        with self.app.app_context():
            proof = db.session.get(PurchaseOrder, po_id).receipt_proof
        self.assertEqual(admin.get(f'/attachments/po/{proof}').status_code, 200)

    def test_04_po_reject_resubmit_cancel(self):
        staff = self.login('Staff')
        admin = self.login('Admin')
        staff.post('/purchase-orders/create', data={
            'title': '__AUDIT_PO_REJECT', 'item_name[]': ['Kursi'], 'category[]': ['Furniture'],
            'quantity[]': ['1'], 'unit_price[]': ['500000'], 'specification[]': [''],
        })
        with self.app.app_context():
            po_id = PurchaseOrder.query.filter_by(title='__AUDIT_PO_REJECT').first().id
        staff.post(f'/purchase-orders/{po_id}/submit')
        self.assertNo500(admin.post(f'/purchase-orders/{po_id}/reject', data={'rejection_reason': 'mahal'}), 'reject')
        with self.app.app_context():
            self.assertEqual(db.session.get(PurchaseOrder, po_id).status, 'REJECTED')
        staff.post(f'/purchase-orders/{po_id}/submit')
        with self.app.app_context():
            self.assertEqual(db.session.get(PurchaseOrder, po_id).status, 'SUBMITTED')
        # staff may not cancel a non-draft PO
        staff.post(f'/purchase-orders/{po_id}/cancel')
        with self.app.app_context():
            self.assertEqual(db.session.get(PurchaseOrder, po_id).status, 'SUBMITTED')
        self.assertNo500(admin.post(f'/purchase-orders/{po_id}/cancel'), 'admin cancel')
        with self.app.app_context():
            self.assertEqual(db.session.get(PurchaseOrder, po_id).status, 'CANCELLED')

    # ---------- 3. Assets, maintenance, feedback ----------
    def _create_asset(self, client, name):
        r = client.post('/assets/create', data={
            'name': name, 'category': 'Tech', 'location': 'Ruang Audit',
            'purchase_date': '2026-01-10', 'purchase_price': '2500000', 'status': 'Aktif',
            'needs_maintenance': '1', 'maintenance_interval_days': '30'})
        self.assertNo500(r, 'create asset')
        with self.app.app_context():
            a = Asset.query.filter_by(name=name).first()
            return a.id if a else None

    def test_05_asset_rbac_and_operations(self):
        admin = self.login('Admin', sudo=True)
        staff = self.login('Staff')
        auditor = self.login('Auditor')
        tek = self.login('Teknisi')

        # Auditor & Teknisi must not create assets
        self.assertIsNone(self._create_asset(auditor, '__AUDIT_BY_AUDITOR'))
        self.assertIsNone(self._create_asset(tek, '__AUDIT_BY_TEKNISI'))
        aid = self._create_asset(staff, '__AUDIT_ASSET_OPS')
        self.assertIsNotNone(aid, 'Staff could not create asset')

        # edit
        self.assertNo500(staff.post(f'/assets/{aid}/edit', data={
            'name': '__AUDIT_ASSET_OPS', 'category': 'Tech', 'location': 'Ruang Audit 2',
            'purchase_date': '2026-01-10', 'purchase_price': '2600000', 'status': 'Aktif'}), 'edit')
        # transfer
        self.assertNo500(staff.post(f'/assets/{aid}/transfer', data={
            'to_location': 'Gudang Audit', 'reason': 'pindah'}), 'transfer')
        with self.app.app_context():
            self.assertEqual(db.session.get(Asset, aid).location, 'Gudang Audit')
        # attachments
        self.assertNo500(staff.post(f'/assets/{aid}/attachments/upload', data={
            'file_type': 'invoice', 'attachment_file': (io.BytesIO(b'%PDF-1.4 inv'), 'inv.pdf')},
            content_type='multipart/form-data'), 'upload attachment')
        with self.app.app_context():
            att = AssetAttachment.query.filter_by(asset_id=aid).first()
            self.assertIsNotNone(att, 'attachment not saved')
            att_id = att.id
        self.assertEqual(staff.get(f'/api/assets/{aid}/attachments').status_code, 200)
        self.assertEqual(staff.get(f'/assets/{aid}/attachments/{att_id}/download').status_code, 200)
        self.assertNo500(staff.post(f'/assets/{aid}/attachments/{att_id}/delete'), 'delete attachment')
        # bulk status + export
        self.assertNo500(staff.post('/assets/bulk-action', data={
            'action': 'change_status', 'asset_ids': str(aid), 'bulk_status': 'Rusak'}), 'bulk status')
        with self.app.app_context():
            self.assertEqual(db.session.get(Asset, aid).status, 'Rusak')
        r = staff.post('/assets/bulk-action', data={'action': 'export', 'asset_ids': str(aid)})
        self.assertEqual(r.status_code, 200)
        self.assertIn('text/csv', r.headers.get('Content-Type', ''))
        # Rusak asset cannot be checked out
        staff.post(f'/assets/{aid}/checkout', data={'borrower': 'X'})
        with self.app.app_context():
            self.assertNotEqual(db.session.get(Asset, aid).status, 'Dipinjam')
        staff.post('/assets/bulk-action', data={'action': 'change_status', 'asset_ids': str(aid), 'bulk_status': 'Aktif'})

        # maintenance: staff cannot start/complete, teknisi can
        staff.post(f'/assets/{aid}/maintenance/start')
        with self.app.app_context():
            self.assertNotEqual(db.session.get(Asset, aid).status, 'Dalam Perbaikan')
        self.assertNo500(tek.post(f'/assets/{aid}/maintenance/start'), 'teknisi start')
        with self.app.app_context():
            self.assertEqual(db.session.get(Asset, aid).status, 'Dalam Perbaikan')
        self.assertNo500(tek.post(f'/assets/{aid}/maintenance/complete', data={
            'action_taken': 'Ganti thermal paste', 'cost': '150000', 'service_type': 'Rutin',
            'proof_file': (io.BytesIO(b'%PDF-1.4 nota'), 'nota.pdf')},
            content_type='multipart/form-data'), 'teknisi complete')
        with self.app.app_context():
            a = db.session.get(Asset, aid)
            self.assertEqual(a.status, 'Aktif')
            self.assertGreaterEqual(len(a.maintenance_records), 1)

        # staff report issue -> feedback, teknisi resolves, admin deletes
        self.assertNo500(staff.post(f'/assets/{aid}/report-issue', data={
            'issue_description': '__AUDIT layar berkedip'}), 'report issue')
        with self.app.app_context():
            fb = SystemFeedback.query.filter(SystemFeedback.message.like('%__AUDIT layar%')).first()
            self.assertIsNotNone(fb, 'report issue did not create feedback')
            fb.message = '__AUDIT ' + fb.message
            db.session.commit()
            fb_id = fb.id
        self.assertNo500(tek.post(f'/feedback/{fb_id}/resolve', data={'notes': 'beres'}), 'resolve')
        tek.post(f'/feedback/{fb_id}/delete')  # Teknisi not allowed
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(SystemFeedback, fb_id))
        self.assertNo500(admin.post(f'/feedback/{fb_id}/delete'), 'admin delete feedback')

        # circulation
        self.assertNo500(staff.post(f'/assets/{aid}/checkout', data={'borrower': 'Budi', 'notes': 'rapat'}), 'checkout')
        with self.app.app_context():
            self.assertEqual(db.session.get(Asset, aid).status, 'Dipinjam')
        self.assertNo500(staff.post(f'/assets/{aid}/checkin', data={'status': 'Aktif'}), 'checkin')
        self.assertEqual(staff.get(f'/api/assets/{aid}/circulation').status_code, 200)

        # public scan & qr
        with self.app.app_context():
            code = db.session.get(Asset, aid).asset_code
        anon = self.app.test_client()
        self.assertEqual(anon.get(f'/scan/{code}').status_code, 200)
        self.assertEqual(anon.get(f'/api/assets/{aid}/qrcode').status_code, 200)

        # staff cannot delete; admin can
        staff.post(f'/assets/{aid}/delete')
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Asset, aid))
        self.assertNo500(admin.post(f'/assets/{aid}/delete'), 'admin delete asset')
        with self.app.app_context():
            self.assertIsNone(db.session.get(Asset, aid))

    def test_06_csv_import_and_public_feedback(self):
        staff = self.login('Staff')
        csv_body = ('\ufeffNama Aset;Kategori;Lokasi;Tanggal Perolehan (YYYY-MM-DD);Nilai Perolehan;Status;'
                    'Deskripsi;Perlu Maintenance (0/1);Interval Maintenance (hari)\n'
                    '__AUDIT CSV Printer;Office;Ruang Audit;2026-02-01;3000000;Aktif;uji;1;60\n')
        r = staff.post('/assets/import-csv', data={'csv_file': (io.BytesIO(csv_body.encode('utf-8')), 'a.csv')},
                       content_type='multipart/form-data')
        self.assertNo500(r, 'csv import')
        with self.app.app_context():
            self.assertIsNotNone(Asset.query.filter_by(name='__AUDIT CSV Printer').first(), 'CSV import failed')

        anon = self.app.test_client()
        r = anon.post('/submit-feedback', data={'name': 'Tamu', 'contact': 'tamu@x.id',
                                                'category': 'Laporan Bug / Eror', 'message': '__AUDIT public bug'})
        self.assertNo500(r, 'public feedback')
        with self.app.app_context():
            self.assertIsNotNone(SystemFeedback.query.filter_by(message='__AUDIT public bug').first())

    # ---------- 4. Accounts, API key, profile ----------
    def test_07_accounts_api_key_profile(self):
        admin = self.login('Admin', sudo=True)
        staff = self.login('Staff')
        # staff cannot create accounts
        staff.post('/accounts/create', data={'username': '__audit_hack', 'full_name': 'x', 'password': 'Hack12345', 'role': 'Admin'})
        with self.app.app_context():
            self.assertIsNone(User.query.filter_by(username='__audit_hack').first())

        self.assertNo500(admin.post('/accounts/create', data={
            'username': '__audit_new', 'full_name': 'Audit New', 'password': 'NewUser123', 'role': 'Staff'}), 'create account')
        with self.app.app_context():
            u = User.query.filter_by(username='__audit_new').first()
            self.assertIsNotNone(u, 'account not created')
            uid = u.id
        self.assertNo500(admin.post(f'/accounts/{uid}/edit', data={
            'full_name': 'Audit New Edited', 'role': 'Auditor', 'is_active': '1'}), 'edit account')
        self.assertNo500(admin.post(f'/accounts/{uid}/change-password', data={
            'new_password': 'Changed123', 'confirm_password': 'Changed123'}), 'admin change pw')
        self.assertNo500(admin.post(f'/accounts/{uid}/generate-api-key'), 'api key')
        with self.app.app_context():
            u = db.session.get(User, uid)
            self.assertEqual(u.role, 'Auditor')
            key = u.api_key
            self.assertTrue(key)
        anon = self.app.test_client()
        r = anon.get('/api/v1/assets', headers={'X-API-Key': key})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(anon.get('/api/v1/assets', headers={'X-API-Key': 'invalid'}).status_code, 403)
        self.assertEqual(anon.get('/api/v1/assets/TIDAK-ADA', headers={'X-API-Key': key}).status_code, 404)

        # new user logs in with changed password; must change on first login?
        c = self.app.test_client()
        r = c.post('/login', data={'username': '__audit_new', 'password': 'Changed123'})
        self.assertEqual(r.status_code, 302)
        self.assertNo500(c.post('/change-password-required', data={
            'new_password': 'Final12345', 'confirm_password': 'Final12345'}), 'forced pw change')
        self.assertNo500(c.post('/profile/update', data={'full_name': 'Audit Profil'}), 'profile update')
        self.assertNo500(c.post('/change-password', data={
            'old_password': 'Final12345', 'new_password': 'Final67890', 'confirm_password': 'Final67890'}), 'change pw')
        with self.app.app_context():
            u = db.session.get(User, uid)
            self.assertTrue(u.check_password('Final67890'), 'self password change failed')
            self.assertEqual(u.full_name, 'Audit Profil')

        self.assertNo500(admin.post(f'/accounts/{uid}/delete'), 'delete account')
        with self.app.app_context():
            self.assertIsNone(db.session.get(User, uid))

    def test_08_login_lockout_and_logout(self):
        c = self.app.test_client()
        for _ in range(5):
            c.post('/login', data={'username': TEST_USERS['Auditor'], 'password': 'salah'})
        with self.app.app_context():
            u = User.query.filter_by(username=TEST_USERS['Auditor']).first()
            self.assertIsNotNone(u.locked_until, 'account not locked after 5 failures')
            u.locked_until = None
            u.failed_login_count = 0
            db.session.commit()
        c = self.login('Auditor')
        self.assertEqual(c.get('/logout').status_code, 302)
        self.assertEqual(c.get('/dashboard').status_code, 302)

    # ---------- 5. Admin system tools ----------
    def test_09_admin_system_tools(self):
        admin = self.login('Admin', sudo=True)
        self.assertNo500(admin.post('/admin/backup'), 'manual backup')
        self.assertTrue(set(os.listdir(BACKUP_FOLDER)) - self.backups_before, 'backup file not created')
        self.assertNo500(admin.post('/admin/optimize-db'), 'optimize db')
        r = admin.get('/api/system/quick-tunnel/status')
        self.assertEqual(r.status_code, 200)
        self.assertIn('active', r.get_json())
        self.assertNo500(admin.post('/settings/test-smtp', data={'test_email': 'audit@example.com'}), 'test smtp')
        self.assertEqual(admin.get('/reports/audit?format=csv').status_code, 200)
        self.assertEqual(admin.get('/set-lang/en').status_code, 302)
        self.assertEqual(admin.get('/set-lang/id').status_code, 302)


if __name__ == '__main__':
    unittest.main(verbosity=2)
