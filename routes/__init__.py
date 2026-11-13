from routes.auth import auth_bp
from routes.main import main_bp
from routes.assets import assets_bp
from routes.maintenance import maintenance_bp
from routes.purchase_orders import po_bp
from routes.admin import admin_bp
from routes.api import api_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(assets_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(po_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
