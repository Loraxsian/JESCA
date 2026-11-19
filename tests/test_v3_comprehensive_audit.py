import unittest
import os
import json
from datetime import datetime, date, timedelta
from app import app, db
from models import User, Asset, MaintenanceRecord, ActivityLog, Vendor, Site, SystemSetting, PurchaseOrder
from services.backup_service import backup_sqlite_db

class ComprehensiveSystemVerification(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def login_admin(self):
        self.client.post('/login', data={'username': 'Admin', 'password': 'Admin123'}, follow_redirects=True)
        # Aktifkan session Sudo Mode untuk Admin
        with self.client.session_transaction() as sess:
            sess['sudo_mode_until'] = (datetime.utcnow() + timedelta(minutes=15)).isoformat()

    def test_01_all_navigation_routes_and_views(self):
        """Verifikasi semua menu navigasi utama menghasilkan status HTTP 200 (atau 302 untuk root redirect)"""
        self.login_admin()
        
        # 1. Root redirect ke dashboard
        res_root = self.client.get('/')
        self.assertEqual(res_root.status_code, 302)
        
        routes = [
            '/dashboard',
            '/assets',
            '/history',
            '/vendors',
            '/sites',
            '/maintenance',
            '/purchase-orders',
            '/reports/audit',
            '/admin/backups',
            '/accounts',
            '/settings',
            '/health',
            '/api/system/check-update'
        ]
        
        for route in routes:
            with self.subTest(route=route):
                res = self.client.get(route)
                self.assertEqual(res.status_code, 200, f"Route {route} gagal dengan status {res.status_code}")

    def test_02_export_features(self):
        """Verifikasi fitur ekspor PDF dan CSV inventaris serta laporan audit"""
        self.login_admin()
        
        # 1. Export PDF Asset
        res_pdf = self.client.get('/assets/export/pdf')
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf.content_type, 'application/pdf')
        
        # 2. Export CSV Asset
        res_csv = self.client.get('/assets/export/csv')
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn('text/csv', res_csv.content_type)
        
        # 3. Export CSV Template Import
        res_tpl = self.client.get('/assets/import-csv')
        self.assertEqual(res_tpl.status_code, 200)
        self.assertIn('text/csv', res_tpl.content_type)

        # 4. Export CSV Audit Report
        res_audit_csv = self.client.get('/reports/audit?format=csv')
        self.assertEqual(res_audit_csv.status_code, 200)
        self.assertIn('text/csv', res_audit_csv.content_type)

    def test_03_smtp_settings_and_autodetect(self):
        """Verifikasi fungsionalitas smart SMTP auto-detect dan penyusunan konfigurasi"""
        from services.email_service import resolve_smtp_settings
        
        host, port, ssl_mode = resolve_smtp_settings('perusahaan@gmail.com')
        self.assertEqual(host, 'smtp.gmail.com')
        self.assertEqual(port, 587)
        self.assertEqual(ssl_mode, 'tls')
        
        host_y, port_y, ssl_mode_y = resolve_smtp_settings('support@yahoo.com')
        self.assertEqual(host_y, 'smtp.mail.yahoo.com')
        self.assertEqual(port_y, 465)
        self.assertEqual(ssl_mode_y, 'ssl')

        host_c, port_c, ssl_mode_c = resolve_smtp_settings('admin@pt-abadi.co.id')
        self.assertEqual(host_c, 'smtp.pt-abadi.co.id')

    def test_04_asset_lifecycle_workflow(self):
        """Verifikasi siklus hidup aset lengkap: create, checkout, checkin, transfer, edit"""
        self.login_admin()
        
        # 1. Create Asset
        res = self.client.post('/assets/create', data={
            'name': 'Laptop Audit Test QA',
            'category': 'Tech',
            'location': 'Ruang IT',
            'purchase_date': str(date.today()),
            'purchase_price': '15000000',
            'status': 'Aktif',
            'description': 'Aset uji verifikasi alur kerja',
            'needs_maintenance': '1',
            'maintenance_interval_days': '60'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        
        asset = Asset.query.filter_by(name='Laptop Audit Test QA').first()
        self.assertIsNotNone(asset)
        asset_id = asset.id
        
        # 2. Checkout (Peminjaman)
        res_co = self.client.post(f'/assets/{asset_id}/checkout', data={
            'borrower': 'Auditor Internal',
            'notes': 'Keperluan audit lapangan'
        }, follow_redirects=True)
        self.assertEqual(res_co.status_code, 200)
        db.session.refresh(asset)
        self.assertEqual(asset.status, 'Dipinjam')
        self.assertEqual(asset.borrower, 'Auditor Internal')
        
        # 3. Checkin (Pengembalian)
        res_ci = self.client.post(f'/assets/{asset_id}/checkin', follow_redirects=True)
        self.assertEqual(res_ci.status_code, 200)
        db.session.refresh(asset)
        self.assertEqual(asset.status, 'Aktif')
        self.assertIsNone(asset.borrower)
        
        # 4. Asset Transfer
        res_tf = self.client.post(f'/assets/{asset_id}/transfer', data={
            'to_location': 'Gudang B',
            'reason': 'Relokasi aset proyek'
        }, follow_redirects=True)
        self.assertEqual(res_tf.status_code, 200)
        db.session.refresh(asset)
        self.assertEqual(asset.location, 'Gudang B')

        # Cleanup test asset
        db.session.delete(asset)
        db.session.commit()

    def test_05_database_backup_service(self):
        """Verifikasi pembuatan backup database SQLite secara konsisten dengan backup_sqlite_db"""
        from config import DATA_DIR, BACKUP_FOLDER
        db_path = os.path.join(DATA_DIR, 'jesca.db')
        test_backup_path = os.path.join(BACKUP_FOLDER, 'test_verification.db')
        
        backup_sqlite_db(db_path, test_backup_path)
        self.assertTrue(os.path.exists(test_backup_path), "File backup fisik tidak ditemukan")
        if os.path.exists(test_backup_path):
            os.remove(test_backup_path)

    def test_06_offline_maintenance_sync_api(self):
        """Verifikasi endpoint /api/maintenance/sync (auth 401, RBAC, dan simpan lampiran base64)"""
        import base64
        from config import MAINT_ATTACHMENT_FOLDER

        # 1. Unauthenticated harus return 401 JSON (bukan 200)
        res_unauth = self.client.post('/api/maintenance/sync', json={'items': [{'asset_id': 1}]})
        self.assertEqual(res_unauth.status_code, 401)

        # 2. Login Admin & buat aset uji Dalam Perbaikan
        self.login_admin()
        asset = Asset(
            asset_code='TECH-OFF-001',
            name='Server Rack Offline Test',
            category='Tech',
            location='Basement',
            purchase_date=date.today(),
            purchase_price=10000000,
            status='Dalam Perbaikan',
            needs_maintenance=True,
            maintenance_interval_days=60
        )
        db.session.add(asset)
        db.session.commit()

        # 1x1 JPEG base64 minimal valid
        tiny_jpg = base64.b64encode(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9').decode()
        data_url = f'data:image/jpeg;base64,{tiny_jpg}'

        res_sync = self.client.post('/api/maintenance/sync', json={
            'items': [{
                'id': 99,
                'asset_id': asset.id,
                'asset_code': asset.asset_code,
                'service_date': str(date.today()),
                'service_type': 'Perbaikan Kerusakan',
                'action_taken': 'Ganti kipas PSU di basement',
                'cost': '250000',
                'interval_days': '45',
                'proof_data_url': data_url,
                'proof_filename': 'kamera_hp.jpg',
                'is_offline': True
            }]
        })
        self.assertEqual(res_sync.status_code, 200)
        body = res_sync.get_json()
        self.assertEqual(body['status'], 'success')
        self.assertEqual(body['synced_count'], 1)
        self.assertEqual(body['synced_ids'], [99])

        db.session.refresh(asset)
        self.assertEqual(asset.status, 'Aktif')
        self.assertEqual(asset.maintenance_interval_days, 45)

        rec = MaintenanceRecord.query.filter_by(asset_id=asset.id).first()
        self.assertIsNotNone(rec)
        self.assertIsNotNone(rec.proof_file)
        proof_path = os.path.join(MAINT_ATTACHMENT_FOLDER, rec.proof_file)
        self.assertTrue(os.path.exists(proof_path))

        # Cleanup
        if os.path.exists(proof_path):
            os.remove(proof_path)
        db.session.delete(rec)
        db.session.delete(asset)
        db.session.commit()

    def test_07_teknisi_mobile_workspace_redirect_and_tab(self):
        """Verifikasi redirect login Teknisi (force_password_change prioritas) & custom tab Riwayat"""
        # 1. Buat akun Teknisi dengan force_password_change=True
        tech_force = User(
            username='tech_qa_force',
            full_name='Teknisi Force PW',
            role='Teknisi',
            force_password_change=True
        )
        tech_force.set_password('TechPass123')
        db.session.add(tech_force)

        tech_ready = User(
            username='tech_qa_ready',
            full_name='Teknisi Siap',
            role='Teknisi',
            force_password_change=False
        )
        tech_ready.set_password('TechPass123')
        db.session.add(tech_ready)
        db.session.commit()

        try:
            # Cek prioritas force_password_change
            res_force = self.client.post('/login', data={'username': 'tech_qa_force', 'password': 'TechPass123'}, follow_redirects=False)
            self.assertEqual(res_force.status_code, 302)
            self.assertIn('/change-password-required', res_force.location)
            self.client.get('/logout')

            # Cek redirect normal Teknisi ke /maintenance
            res_ready = self.client.post('/login', data={'username': 'tech_qa_ready', 'password': 'TechPass123'}, follow_redirects=False)
            self.assertEqual(res_ready.status_code, 302)
            self.assertIn('/maintenance', res_ready.location)

            # Cek bottom nav khusus Teknisi & tab ?tab=riwayat
            res_page = self.client.get('/maintenance?tab=riwayat')
            self.assertEqual(res_page.status_code, 200)
            html = res_page.get_data(as_text=True)
            self.assertIn('id="mobileNavHistory"', html)
            self.assertNotIn('id="mobileNavAssets"', html)
            self.assertIn('id="history-maint"', html)
        finally:
            self.client.get('/logout')
            db.session.delete(tech_force)
            db.session.delete(tech_ready)
            db.session.commit()

if __name__ == '__main__':
    unittest.main()
