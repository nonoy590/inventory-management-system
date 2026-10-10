import os

# MySQL settings (XAMPP/WAMP defaults: user "root", empty password)
DB_HOST = os.environ.get("MYSQL_HOST", "localhost")
DB_PORT = int(os.environ.get("MYSQL_PORT", 3306))
DB_USER = os.environ.get("MYSQL_USER", "root")
DB_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
DB_NAME = os.environ.get("MYSQL_DB", "inventory_db")  # must match database/schema.sql

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

DEFAULT_ADMIN = ("admin", "admin123", "admin")
DEFAULT_STAFF = ("staff", "staff123", "user")

# Shown at the top of printed / downloaded receipts
STORE_NAME = os.environ.get("STORE_NAME", "StockWise")
STORE_ADDRESS = os.environ.get("STORE_ADDRESS", "")
STORE_PHONE = os.environ.get("STORE_PHONE", "")
