from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

try:
    import qrcode
    HAVE_QRCODE = True
except ImportError:
    qrcode = None
    HAVE_QRCODE = False

try:
    from reportlab.lib import colors as rl_colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    HAVE_REPORTLAB = True
except ImportError:
    rl_colors = None
    A4 = landscape = SimpleDocTemplate = Table = TableStyle = Paragraph = Spacer = getSampleStyleSheet = None
    HAVE_REPORTLAB = False

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    HAVE_SCHEDULER = True
except ImportError:
    BackgroundScheduler = None
    HAVE_SCHEDULER = False

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Silakan login terlebih dahulu untuk mengakses sistem JESCA.'
login_manager.login_message_category = 'warning'
