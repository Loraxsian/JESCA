import unittest
import app as jesca_app
from extensions import db
from models import Asset, Vendor, Site, PurchaseOrder, ActivityLog, SystemFeedback


class TestJescaV3FullFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = jesca_app.app
        cls.app.config['WTF_CSRF_ENABLED'] = False

    def _login_admin_with_sudo(self):
        c = self.app.test_client()
        r = c.post('/login', data={'username': 'Admin', 'password': 'Admin123'}, follow_redirects=False)
        self.assertIn(r.status_code, (200, 302))
        s = c.post('/confirm-sudo', data={'password': 'Admin123'}, follow_redirects=False)
        self.assertIn(s.status_code, (200, 302))
        return c

    def test_01_version_blueprints_and_public_routes(self):
        self.assertEqual(jesca_app.APP_VERSION, '3.0.0')
        expected_bps = {'auth', 'main', 'assets', 'maintenance', 'po', 'admin', 'api'}
        self.assertTrue(expected_bps.issubset(set(self.app.blueprints.keys())))

        c = self.app.test_client()
        for route in ('/health', '/robots.txt', '/login'):
            resp = c.get(route)
            self.assertEqual(resp.status_code, 200, f'{route} returned {resp.status_code}')

        r404 = c.get('/nonexistent-v3-route-test')
        self.assertEqual(r404.status_code, 404)
        self.assertIn('Ke Beranda', r404.get_data(as_text=True))

    def test_02_all_get_routes_and_labels(self):
        c = self._login_admin_with_sudo()
        routes = [
            '/dashboard', '/assets', '/assets/import-csv', '/assets/export/csv',
            '/assets/export/excel', '/assets/export/pdf',
            '/maintenance', '/purchase-orders', '/purchase-orders/create',
            '/purchase-orders/export/csv', '/purchase-orders/export/pdf',
            '/vendors', '/sites', '/history', '/reports/audit', '/reports/audit?format=csv',
            '/feedbacks', '/accounts', '/admin/backups', '/settings',
            '/api/vendors', '/api/sites', '/api/assets/warranty-alerts',
            '/api/assets/cache-summary', '/api/generate-code?category=Tech'
        ]
        for route in routes:
            resp = c.get(route)
            self.assertEqual(resp.status_code, 200, f'Route {route} returned {resp.status_code}')

        self.assertIn('Pengadaan Barang (PO)', c.get('/purchase-orders').get_data(as_text=True))
        settings_html = c.get('/settings').get_data(as_text=True)
        self.assertIn('Mode Jurnal WAL', settings_html)
        self.assertIn('Mode Akses Khusus (Sudo)', settings_html)

    def test_03_api_v1_requires_api_key(self):
        c = self.app.test_client()
        resp = c.get('/api/v1/assets')
        self.assertEqual(resp.status_code, 401)

    def test_04_asset_crud_qr_scan_circulation_maintenance_and_cleanup(self):
        c = self._login_admin_with_sudo()
        test_name = '__TEST_V3_ASSET__'
        resp = c.post('/assets/create', data={
            'name': test_name,
            'category': 'Tech',
            'location': 'Ruang Uji v3',
            'purchase_date': '2026-01-15',
            'purchase_price': '5000000',
            'status': 'Aktif',
            'description': 'Aset uji v3.0',
            'needs_maintenance': '1',
            'maintenance_interval_days': '90'
        }, follow_redirects=False)
        self.assertIn(resp.status_code, (200, 302))

        with self.app.app_context():
            asset = Asset.query.filter_by(name=test_name).first()
            self.assertIsNotNone(asset)
            asset_id = asset.id
            asset_code = asset.asset_code

        try:
            # QR & Public Scan
            qr_resp = c.get(f'/api/assets/{asset_id}/qrcode')
            self.assertEqual(qr_resp.status_code, 200)
            scan_resp = self.app.test_client().get(f'/scan/{asset_code}')
            self.assertEqual(scan_resp.status_code, 200)
            self.assertIn(test_name, scan_resp.get_data(as_text=True))

            # Checkout & Checkin
            co = c.post(f'/assets/{asset_id}/checkout', data={'borrower': 'Tester v3', 'borrow_notes': 'Uji'}, follow_redirects=False)
            self.assertIn(co.status_code, (200, 302))
            circ = c.get(f'/api/assets/{asset_id}/circulation')
            self.assertEqual(circ.status_code, 200)
            ci = c.post(f'/assets/{asset_id}/checkin', data={'return_condition': 'Baik'}, follow_redirects=False)
            self.assertIn(ci.status_code, (200, 302))

            # Maintenance start & complete
            ms = c.post(f'/assets/{asset_id}/maintenance/start', follow_redirects=False)
            self.assertIn(ms.status_code, (200, 302))
            mc = c.post(f'/assets/{asset_id}/maintenance/complete', data={
                'action_taken': 'Pembersihan sistem',
                'cost': '100000',
                'maintenance_date': '2026-11-13'
            }, follow_redirects=False)
            self.assertIn(mc.status_code, (200, 302))
        finally:
            # Cleanup test asset
            c.post(f'/assets/{asset_id}/delete', follow_redirects=False)
            with self.app.app_context():
                ActivityLog.query.filter(ActivityLog.asset_name == test_name).delete()
                db.session.commit()

    def test_05_vendor_site_and_po_crud_cleanup(self):
        c = self._login_admin_with_sudo()
        v_resp = c.post('/vendors/create', data={'name': '__TEST_VENDOR_V3__', 'phone': '081234'}, follow_redirects=False)
        self.assertIn(v_resp.status_code, (200, 302))
        s_resp = c.post('/sites/create', data={'name': '__TEST_SITE_V3__', 'description': 'Uji'}, follow_redirects=False)
        self.assertIn(s_resp.status_code, (200, 302))

        po_resp = c.post('/purchase-orders/create', data={
            'title': '__TEST_PO_V3__',
            'notes': '__TEST_PO_V3__',
            'item_name[]': ['Laptop Uji v3'],
            'category[]': ['Tech'],
            'quantity[]': ['1'],
            'unit_price[]': ['10000000'],
            'specification[]': ['Unit uji']
        }, follow_redirects=False)
        self.assertIn(po_resp.status_code, (200, 302))

        with self.app.app_context():
            po = PurchaseOrder.query.filter_by(notes='__TEST_PO_V3__').first()
            self.assertIsNotNone(po)
            po_id = po.id
            vendor = Vendor.query.filter_by(name='__TEST_VENDOR_V3__').first()
            site = Site.query.filter_by(name='__TEST_SITE_V3__').first()

        try:
            self.assertEqual(c.get(f'/purchase-orders/{po_id}').status_code, 200)
            self.assertEqual(c.get(f'/purchase-orders/{po_id}/edit').status_code, 200)
            self.assertEqual(c.get(f'/purchase-orders/{po_id}/print').status_code, 200)
        finally:
            with self.app.app_context():
                po_obj = db.session.get(PurchaseOrder, po_id)
                if po_obj:
                    db.session.delete(po_obj)
                if vendor:
                    v_obj = db.session.get(Vendor, vendor.id)
                    if v_obj:
                        db.session.delete(v_obj)
                if site:
                    s_obj = db.session.get(Site, site.id)
                    if s_obj:
                        db.session.delete(s_obj)
                db.session.commit()


if __name__ == '__main__':
    unittest.main()
