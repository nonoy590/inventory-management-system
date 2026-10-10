import os
import uuid
from decimal import Decimal
from datetime import date, datetime
from functools import wraps

import config
import pymysql
import pymysql.cursors
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

DB_CONFIG = {
    "host": config.DB_HOST,
    "port": config.DB_PORT,
    "user": config.DB_USER,
    "password": config.DB_PASSWORD,
}
DB_NAME = config.DB_NAME
DEFAULT_ADMIN = config.DEFAULT_ADMIN
DEFAULT_STAFF = config.DEFAULT_STAFF
UNITS = ["pcs", "kg", "g", "L", "mL", "pack", "box", "tray", "bottle", "can", "sack", "dozen"]
SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "schema.sql")


class DB:
    """Thin wrapper so queries read like conn.execute(sql, params).fetchone()."""

    def __init__(self, database=DB_NAME):
        self.conn = pymysql.connect(
            **DB_CONFIG,
            database=database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(sql.replace("?", "%s"), params)
        return cur

    def executemany(self, sql, seq):
        cur = self.conn.cursor()
        cur.executemany(sql.replace("?", "%s"), seq)
        return cur

    def scalar(self, sql, params=()):
        row = self.execute(sql, params).fetchone()
        return list(row.values())[0] if row else None

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()


def get_db():
    return DB()


def ensure_column(conn, table, column, ddl):
    """Add a column to an existing table if an older database doesn't have it yet."""
    exists = conn.scalar(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s AND column_name = %s",
        (DB_NAME, table, column),
    )
    if not exists:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.commit()


def init_db():
    # Build the database and tables from database/inventory.sql
    boot = pymysql.connect(**DB_CONFIG, charset="utf8mb4")
    with open(SCHEMA_FILE, encoding="utf-8") as f:
        lines = [l for l in f.read().splitlines() if not l.strip().startswith("--")]
    with boot.cursor() as cur:
        for stmt in "\n".join(lines).split(";"):
            if stmt.strip():
                cur.execute(stmt)
    boot.commit()
    boot.close()

    conn = get_db()
    # Upgrade older databases that are missing newer columns
    ensure_column(conn, "items", "unit", "VARCHAR(20) NOT NULL DEFAULT 'pcs'")
    ensure_column(conn, "sales", "buyer_name", "VARCHAR(100)")
    ensure_column(conn, "sales", "buyer_phone", "VARCHAR(30)")
    ensure_column(conn, "sales", "created_at", "DATETIME NULL")
    ensure_column(conn, "stock_in", "unit_cost", "DECIMAL(10,2) NOT NULL DEFAULT 0")
    ensure_column(conn, "stock_in", "total", "DECIMAL(10,2) NOT NULL DEFAULT 0")
    ensure_column(conn, "stock_in", "created_at", "DATETIME NULL")

    item_count = conn.scalar("SELECT COUNT(*) FROM items")
    if item_count == 0:
        sample_items = [
            ("Rice (5kg)", "Groceries", 25, 150.0, 5, "sack"),
            ("Coca-Cola (1L)", "Beverages", 8, 50.0, 10, "bottle"),
            ("Chips (Individual)", "Snacks", 15, 20.0, 5, "pack"),
            ("Bread", "Bakery", 4, 50.0, 5, "pack"),
            ("Eggs (1 tray)", "Eggs", 0, 110.0, 3, "tray"),
        ]
        conn.executemany(
            "INSERT INTO items (name, category, quantity, price, low_stock_threshold, unit) VALUES (?, ?, ?, ?, ?, ?)",
            sample_items,
        )
        t1, t2, t3 = uuid.uuid4().hex[:8], uuid.uuid4().hex[:8], uuid.uuid4().hex[:8]
        sample_sales = [
            ("Rice (5kg)", 2, 300.0, "2026-09-19", t1, "Maria Santos", "0917-111-2222"),
            ("Coca-Cola (1L)", 5, 250.0, "2026-09-19", t1, "Maria Santos", "0917-111-2222"),
            ("Chips (Individual)", 10, 200.0, "2026-09-18", t2, "Juan Dela Cruz", "0918-333-4444"),
            ("Bread", 3, 150.0, "2026-09-18", t2, "Juan Dela Cruz", "0918-333-4444"),
            ("Eggs (1 tray)", 2, 220.0, "2026-09-17", t3, "Ana Lopez", "0919-555-6666"),
        ]
        conn.executemany(
            "INSERT INTO sales (product_name, quantity, total, sale_date, transaction_id, buyer_name, buyer_phone) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            sample_sales,
        )
        conn.commit()

    if conn.scalar("SELECT COUNT(*) FROM stock_in") == 0 and conn.scalar("SELECT COUNT(*) FROM items") > 0:
        b1 = uuid.uuid4().hex[:8]
        conn.executemany(
            "INSERT INTO stock_in (batch_id, item_id, product_name, quantity, supplier, note, received_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (b1, 1, "Rice (5kg)", 20, "San Miguel Wholesale", "Opening stock", "2026-09-15"),
                (b1, 4, "Bread", 10, "Golden Bakery Supply", "Opening stock", "2026-09-15"),
            ],
        )
        conn.commit()

    cat_count = conn.scalar("SELECT COUNT(*) FROM categories")
    if cat_count == 0:
        sample_categories = [
            ("Groceries", "Rice, canned goods, and pantry staples"),
            ("Beverages", "Soft drinks, juices, and bottled water"),
            ("Snacks", "Chips, crackers, and individually packed treats"),
            ("Bakery", "Bread, pastries, and baked goods"),
            ("Eggs", "Fresh eggs by the tray or piece"),
        ]
        conn.executemany(
            "INSERT INTO categories (name, description) VALUES (?, ?)", sample_categories
        )
        conn.commit()

    supplier_count = conn.scalar("SELECT COUNT(*) FROM suppliers")
    if supplier_count == 0:
        sample_suppliers = [
            ("San Miguel Wholesale", "Ana Reyes", "0917-000-1111", "ana@smwholesale.ph", "Iloilo City"),
            ("Golden Bakery Supply", "Mark Tan", "0917-000-2222", "mark@goldenbakery.ph", "San Miguel, Iloilo"),
        ]
        conn.executemany(
            "INSERT INTO suppliers (name, contact_person, phone, email, address) VALUES (?, ?, ?, ?, ?)",
            sample_suppliers,
        )
        conn.commit()

    user_count = conn.scalar("SELECT COUNT(*) FROM users")
    if user_count == 0:
        for username, password, role in (DEFAULT_ADMIN, DEFAULT_STAFF):
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (username, generate_password_hash(password), role, date.today().isoformat()),
            )
        conn.commit()
        print("=" * 60)
        print("Default accounts created:")
        print(f"  admin / {DEFAULT_ADMIN[1]}  (role: admin)")
        print(f"  staff / {DEFAULT_STAFF[1]}  (role: user)")
        print("Change these passwords from Settings after logging in.")
        print("=" * 60)

    conn.close()


def picker_products(items):
    """Plain dicts for the product picker (rendered as JSON in the templates)."""
    return [
        {
            "id": i["id"],
            "name": i["name"],
            "category": i["category"] or "",
            "unit": i["unit"] or "pcs",
            "price": float(i["price"]),
            "stock": i["quantity"],
            "low": i["low_stock_threshold"],
        }
        for i in items
    ]


def stock_status(item):
    if item["quantity"] == 0:
        return "out"
    if item["quantity"] <= item["low_stock_threshold"]:
        return "low"
    return "in"


@app.context_processor
def inject_user():
    user = None
    if session.get("user_id"):
        user = {"id": session["user_id"], "username": session["username"], "role": session["role"]}
    return dict(current_user=user)


@app.before_request
def require_login():
    open_endpoints = {"login", "static"}
    if request.endpoint not in open_endpoints and not session.get("user_id"):
        return redirect(url_for("login", next=request.path))


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("That page is restricted to admins.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            flash(f'Welcome back, {user["username"]}!', "success")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("login.html", title="Login")


@app.route("/logout")
def logout():
    session.clear()
    flash("You've been logged out.", "success")
    return redirect(url_for("login"))


@app.route("/")
def dashboard():
    conn = get_db()
    items = conn.execute("SELECT * FROM items ORDER BY id DESC").fetchall()
    recent_sales = conn.execute(
        "SELECT * FROM sales ORDER BY COALESCE(created_at, sale_date) DESC, id DESC LIMIT 5"
    ).fetchall()
    total_sales_value = conn.scalar("SELECT COALESCE(SUM(total), 0) FROM sales")
    conn.close()

    total_products = len(items)
    in_stock = [i for i in items if stock_status(i) == "in"]
    low_stock = [i for i in items if stock_status(i) == "low"]
    out_stock = [i for i in items if stock_status(i) == "out"]

    def pct(n):
        return round((n / total_products) * 100) if total_products else 0

    in_pct = pct(len(in_stock))
    low_pct = pct(len(low_stock))
    out_pct = pct(len(out_stock))
    in_stop = in_pct
    low_stop = in_pct + low_pct

    return render_template(
        "dashboard.html",
        title="Dashboard",
        active="dashboard",
        today=date.today().strftime("%B %d, %Y"),
        weekday=date.today().strftime("%A"),
        total_products=total_products,
        in_stock_count=len(in_stock),
        low_stock_count=len(low_stock),
        out_stock_count=len(out_stock),
        in_pct=in_pct,
        low_pct=low_pct,
        out_pct=out_pct,
        in_stop=in_stop,
        low_stop=low_stop,
        total_sales_value=total_sales_value,
        recent_sales=recent_sales,
        recent_items=items[:5],
    )


@app.route("/products")
def products():
    query = request.args.get("q", "").strip()
    conn = get_db()
    if query:
        items = conn.execute(
            "SELECT * FROM items WHERE name LIKE ? OR category LIKE ? ORDER BY name",
            (f"%{query}%", f"%{query}%"),
        ).fetchall()
    else:
        items = conn.execute("SELECT * FROM items ORDER BY name").fetchall()
    conn.close()
    return render_template(
        "products.html", title="Products", active="products", items=items, query=query
    )


@app.route("/add", methods=["GET", "POST"])
@admin_required
def add_item():
    conn = get_db()
    categories_list = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        quantity = request.form.get("quantity", 0)
        price = request.form.get("price", 0)
        threshold = request.form.get("low_stock_threshold", 5)
        unit = request.form.get("unit", "pcs")
        if unit not in UNITS:
            unit = "pcs"

        if not name:
            flash("Item name is required.", "error")
            conn.close()
            return render_template(
                "add_item.html",
                title="Add Item",
                active="products",
                form=request.form,
                categories=categories_list, units=UNITS,
            )

        conn.execute(
            "INSERT INTO items (name, category, quantity, price, low_stock_threshold, unit) VALUES (?, ?, ?, ?, ?, ?)",
            (name, category, int(quantity or 0), float(price or 0), int(threshold or 5), unit),
        )
        conn.commit()
        conn.close()
        flash(f'"{name}" added to inventory.', "success")
        return redirect(url_for("products"))

    conn.close()
    return render_template(
        "add_item.html", title="Add Item", active="products", form={}, categories=categories_list, units=UNITS
    )


@app.route("/edit/<int:item_id>", methods=["GET", "POST"])
@admin_required
def edit_item(item_id):
    conn = get_db()
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    categories_list = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()

    if item is None:
        conn.close()
        flash("Item not found.", "error")
        return redirect(url_for("products"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        quantity = request.form.get("quantity", 0)
        price = request.form.get("price", 0)
        threshold = request.form.get("low_stock_threshold", 5)
        unit = request.form.get("unit", "pcs")
        if unit not in UNITS:
            unit = "pcs"

        if not name:
            flash("Item name is required.", "error")
            conn.close()
            return render_template(
                "edit_item.html",
                title="Edit Item",
                active="products",
                item=item,
                categories=categories_list, units=UNITS,
            )

        conn.execute(
            "UPDATE items SET name=?, category=?, quantity=?, price=?, low_stock_threshold=?, unit=? WHERE id=?",
            (name, category, int(quantity or 0), float(price or 0), int(threshold or 5), unit, item_id),
        )
        conn.commit()
        conn.close()
        flash(f'"{name}" updated.', "success")
        return redirect(url_for("products"))

    conn.close()
    return render_template(
        "edit_item.html", title="Edit Item", active="products", item=item, categories=categories_list, units=UNITS
    )


@app.route("/delete/<int:item_id>", methods=["POST"])
@admin_required
def delete_item(item_id):
    conn = get_db()
    item = conn.execute("SELECT name FROM items WHERE id = ?", (item_id,)).fetchone()
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    if item:
        flash(f'"{item["name"]}" removed from inventory.', "success")
    return redirect(request.referrer or url_for("products"))


@app.route("/sales")
def sales():
    """Transactions page: every stock in and stock out."""
    kind = request.args.get("type", "all")
    if kind not in ("all", "in", "out"):
        kind = "all"

    stock_in_sql = (
        "SELECT si.received_date AS tx_date, COALESCE(si.created_at, CAST(si.received_date AS DATETIME)) AS tx_time, "
        "(si.created_at IS NOT NULL) AS has_time, 'in' AS type, si.batch_id AS ref, "
        "si.product_name AS product_name, si.quantity AS quantity, i.unit AS unit, "
        "si.total AS amount, si.supplier AS supplier, si.note AS note, "
        "CAST(NULL AS CHAR) AS buyer_name, CAST(NULL AS CHAR) AS buyer_phone, si.id AS row_id "
        "FROM stock_in si LEFT JOIN items i ON i.id = si.item_id"
    )
    stock_out_sql = (
        "SELECT s.sale_date AS tx_date, COALESCE(s.created_at, CAST(s.sale_date AS DATETIME)) AS tx_time, "
        "(s.created_at IS NOT NULL) AS has_time, 'out' AS type, s.transaction_id AS ref, "
        "s.product_name AS product_name, s.quantity AS quantity, "
        "(SELECT i.unit FROM items i WHERE i.name = s.product_name LIMIT 1) AS unit, "
        "s.total AS amount, CAST(NULL AS CHAR) AS supplier, CAST(NULL AS CHAR) AS note, "
        "s.buyer_name AS buyer_name, s.buyer_phone AS buyer_phone, s.id AS row_id "
        "FROM sales s"
    )
    parts = {"in": stock_in_sql, "out": stock_out_sql}
    selected = [parts[kind]] if kind in parts else [stock_in_sql, stock_out_sql]

    conn = get_db()
    rows = conn.execute(
        " UNION ALL ".join(f"({q})" for q in selected) + " ORDER BY tx_time DESC, row_id DESC"
    ).fetchall()

    # Group lines into one transaction per buyer (sale) / per delivery (stock in)
    transactions, index = [], {}
    for r in rows:
        key = (r["type"], r["ref"] or f"row{r['row_id']}")
        g = index.get(key)
        if g is None:
            g = {
                "type": r["type"],
                "ref": r["ref"],
                "date": r["tx_date"],
                "time": r["tx_time"] if r["has_time"] else None,
                "name": (r["buyer_name"] or "Walk-in customer") if r["type"] == "out"
                        else (r["supplier"] or "No supplier"),
                "phone": r["buyer_phone"],
                "note": r["note"],
                "lines": [],
                "amount": None,
            }
            index[key] = g
            transactions.append(g)
        g["lines"].append(r)
        if r["amount"] is not None:
            g["amount"] = (g["amount"] or Decimal("0")) + r["amount"]

    in_count = conn.scalar("SELECT COUNT(DISTINCT COALESCE(batch_id, CONCAT('r', id))) FROM stock_in")
    out_count = conn.scalar("SELECT COUNT(DISTINCT COALESCE(transaction_id, CONCAT('r', id))) FROM sales")
    total_value = conn.scalar("SELECT COALESCE(SUM(total), 0) FROM sales")
    conn.close()
    return render_template(
        "transactions.html",
        title="Transactions",
        active="transactions",
        transactions=transactions,
        kind=kind,
        in_count=in_count,
        out_count=out_count,
        total_value=total_value,
    )


def _when(created_at, day):
    """Human-readable date and time for receipts (falls back to the date for old records)."""
    if created_at:
        return created_at.strftime("%b %d, %Y  %I:%M %p")
    return str(day)


@app.route("/sales/receipt/<transaction_id>")
def receipt(transaction_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM sales WHERE transaction_id = ? ORDER BY id", (transaction_id,)
    ).fetchall()
    conn.close()
    if not rows:
        flash("Receipt not found.", "error")
        return redirect(url_for("sales"))

    lines = []
    grand_total = Decimal("0")
    for r in rows:
        qty = r["quantity"]
        grand_total += r["total"]
        lines.append({
            "name": r["product_name"],
            "qty": qty,
            "unit_price": float(r["total"] / qty) if qty else 0.0,
            "total": float(r["total"]),
        })
    first = rows[0]
    meta = [["Receipt no.", transaction_id], ["Date", _when(first.get("created_at"), first["sale_date"])],
            ["Customer", first["buyer_name"] or "Walk-in customer"]]
    if first["buyer_phone"]:
        meta.append(["Contact", first["buyer_phone"]])
    if session.get("username"):
        meta.append(["Served by", session["username"]])
    data = {
        "store": config.STORE_NAME, "address": config.STORE_ADDRESS, "phone": config.STORE_PHONE,
        "ref": transaction_id, "heading": "SALES RECEIPT", "price_label": "Price",
        "subtitle": "Sale recorded.", "meta": meta, "lines": lines, "total": float(grand_total),
        "again_url": url_for("new_sale"), "again_label": "New sale",
    }
    return render_template("receipt.html", title="Receipt", active="transactions", r=data)


@app.route("/stock-in/receipt/<batch_id>")
def stock_in_receipt(batch_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM stock_in WHERE batch_id = ? ORDER BY id", (batch_id,)
    ).fetchall()
    conn.close()
    if not rows:
        flash("Receipt not found.", "error")
        return redirect(url_for("sales"))

    lines = []
    grand_total = Decimal("0")
    for r in rows:
        grand_total += r["total"]
        lines.append({
            "name": r["product_name"],
            "qty": r["quantity"],
            "unit_price": float(r["unit_cost"]),
            "total": float(r["total"]),
        })
    first = rows[0]
    meta = [["Receipt no.", batch_id], ["Date", _when(first.get("created_at"), first["received_date"])],
            ["Supplier", first["supplier"] or "No supplier"]]
    if first["note"]:
        meta.append(["Note", first["note"]])
    if session.get("username"):
        meta.append(["Received by", session["username"]])
    data = {
        "store": config.STORE_NAME, "address": config.STORE_ADDRESS, "phone": config.STORE_PHONE,
        "ref": batch_id, "heading": "STOCK IN RECEIPT", "price_label": "Price",
        "subtitle": "Stock in recorded.", "meta": meta, "lines": lines, "total": float(grand_total),
        "again_url": url_for("stock_in"), "again_label": "New stock in",
    }
    return render_template("receipt.html", title="Receipt", active="transactions", r=data)


@app.route("/stock-in", methods=["GET", "POST"])
def stock_in():
    conn = get_db()

    if request.method == "POST":
        item_ids = request.form.getlist("item_id")
        quantities = request.form.getlist("quantity")
        note = request.form.get("note", "").strip()
        supplier_id = request.form.get("supplier_id", "")

        aggregated = {}   # item_id -> qty
        for raw_id, raw_qty in zip(item_ids, quantities):
            try:
                item_id, qty = int(raw_id), int(raw_qty)
            except ValueError:
                continue
            if qty > 0:
                aggregated[item_id] = aggregated.get(item_id, 0) + qty

        supplier_name = None
        if supplier_id:
            row = conn.execute("SELECT name FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
            supplier_name = row["name"] if row else None

        if not aggregated:
            flash("Add at least one product with a quantity.", "error")
        else:
            batch_id = uuid.uuid4().hex[:8]
            now = datetime.now()
            today = now.date().isoformat()
            created_at = now.strftime("%Y-%m-%d %H:%M:%S")
            recorded = 0
            grand_total = Decimal("0")
            for item_id, qty in aggregated.items():
                item = conn.execute("SELECT id, name, price FROM items WHERE id = ?", (item_id,)).fetchone()
                if item is None:
                    continue
                cost = item["price"]          # the product's price is used for the amount
                line_total = cost * qty
                grand_total += line_total
                conn.execute(
                    "INSERT INTO stock_in (batch_id, item_id, product_name, quantity, supplier, note, received_date, "
                    "unit_cost, total, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (batch_id, item_id, item["name"], qty, supplier_name, note or None, today, cost, line_total, created_at),
                )
                conn.execute("UPDATE items SET quantity = quantity + ? WHERE id = ?", (qty, item_id))
                recorded += 1
            conn.commit()
            conn.close()
            flash(f"Stock in recorded: {recorded} product(s) added, ₱{grand_total:.2f} total.", "success")
            return redirect(url_for("stock_in_receipt", batch_id=batch_id))

    items = conn.execute("SELECT * FROM items ORDER BY name").fetchall()
    suppliers_list = conn.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    history = conn.execute(
        "SELECT * FROM stock_in ORDER BY COALESCE(created_at, received_date) DESC, id DESC LIMIT 20"
    ).fetchall()
    low_items = conn.execute(
        "SELECT * FROM items WHERE quantity <= low_stock_threshold ORDER BY quantity ASC, name ASC"
    ).fetchall()
    conn.close()
    return render_template(
        "stock_in.html",
        title="Stock In",
        active="stock_in",
        items=items,
        products=picker_products(items),
        suppliers=suppliers_list,
        history=history,
        low_items=low_items,
    )


@app.route("/sales/new", methods=["GET", "POST"])
def new_sale():
    conn = get_db()

    if request.method == "POST":
        item_ids = request.form.getlist("item_id")
        quantities = request.form.getlist("quantity")
        buyer_name = request.form.get("buyer_name", "").strip()[:100]
        buyer_phone = request.form.get("buyer_phone", "").strip()[:30]

        rows = []
        for raw_id, raw_qty in zip(item_ids, quantities):
            if not raw_id:
                continue
            try:
                qty = int(raw_qty)
            except ValueError:
                qty = 0
            if qty > 0:
                rows.append((int(raw_id), qty))

        if not buyer_name:
            flash("Buyer name is required.", "error")
        elif not rows:
            flash("Add at least one product with a quantity.", "error")
        else:
            aggregated = {}
            for item_id, qty in rows:
                aggregated[item_id] = aggregated.get(item_id, 0) + qty

            errors = []
            item_cache = {}
            for item_id, qty in aggregated.items():
                item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
                if item is None:
                    errors.append("One of the selected products no longer exists.")
                    continue
                item_cache[item_id] = item
                if qty > item["quantity"]:
                    errors.append(f'Only {item["quantity"]} unit(s) of "{item["name"]}" in stock.')

            if errors:
                for e in errors:
                    flash(e, "error")
            else:
                transaction_id = uuid.uuid4().hex[:8]
                now = datetime.now()
                sale_date = now.date().isoformat()
                created_at = now.strftime("%Y-%m-%d %H:%M:%S")
                grand_total = Decimal("0")
                for item_id, qty in aggregated.items():
                    item = item_cache[item_id]
                    line_total = qty * item["price"]
                    grand_total += line_total
                    conn.execute(
                        "INSERT INTO sales (product_name, quantity, total, sale_date, transaction_id, buyer_name, buyer_phone, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (item["name"], qty, line_total, sale_date, transaction_id, buyer_name, buyer_phone or None, created_at),
                    )
                    conn.execute(
                        "UPDATE items SET quantity = quantity - ? WHERE id = ?", (qty, item_id)
                    )
                conn.commit()
                conn.close()
                flash(
                    f"Sale recorded for {buyer_name}: {len(aggregated)} product(s), ₱{grand_total:.2f} total.",
                    "success",
                )
                return redirect(url_for("receipt", transaction_id=transaction_id))

    items = conn.execute("SELECT * FROM items WHERE quantity > 0 ORDER BY name").fetchall()
    conn.close()
    return render_template(
        "new_sale.html",
        title="Stock Out",
        active="stock_out",
        items=items,
        products=picker_products(items),
        form=request.form if request.method == "POST" else {},
    )


@app.route("/categories")
def categories():
    conn = get_db()
    cats = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    counts = {
        row["category"]: row["n"]
        for row in conn.execute(
            "SELECT category, COUNT(*) as n FROM items GROUP BY category"
        ).fetchall()
    }
    conn.close()
    return render_template(
        "categories.html", title="Categories", active="categories", categories=cats, counts=counts
    )


@app.route("/categories/add", methods=["GET", "POST"])
@admin_required
def add_category():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()

        if not name:
            flash("Category name is required.", "error")
            return render_template(
                "add_category.html", title="Add Category", active="categories", form=request.form
            )

        conn = get_db()
        existing = conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
        if existing:
            conn.close()
            flash(f'Category "{name}" already exists.', "error")
            return render_template(
                "add_category.html", title="Add Category", active="categories", form=request.form
            )

        conn.execute("INSERT INTO categories (name, description) VALUES (?, ?)", (name, description))
        conn.commit()
        conn.close()
        flash(f'Category "{name}" added.', "success")
        return redirect(url_for("categories"))

    return render_template("add_category.html", title="Add Category", active="categories", form={})


@app.route("/categories/edit/<int:cat_id>", methods=["GET", "POST"])
@admin_required
def edit_category(cat_id):
    conn = get_db()
    category = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()

    if category is None:
        conn.close()
        flash("Category not found.", "error")
        return redirect(url_for("categories"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()

        if not name:
            flash("Category name is required.", "error")
            conn.close()
            return render_template(
                "edit_category.html", title="Edit Category", active="categories", category=category
            )

        conn.execute(
            "UPDATE categories SET name=?, description=? WHERE id=?", (name, description, cat_id)
        )
        conn.commit()
        conn.close()
        flash(f'Category "{name}" updated.', "success")
        return redirect(url_for("categories"))

    conn.close()
    return render_template(
        "edit_category.html", title="Edit Category", active="categories", category=category
    )


@app.route("/categories/delete/<int:cat_id>", methods=["POST"])
@admin_required
def delete_category(cat_id):
    conn = get_db()
    category = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()
    if category:
        flash(f'Category "{category["name"]}" removed.', "success")
    return redirect(url_for("categories"))


@app.route("/suppliers")
def suppliers():
    conn = get_db()
    all_suppliers = conn.execute("SELECT * FROM suppliers ORDER BY name").fetchall()
    conn.close()
    return render_template(
        "suppliers.html", title="Suppliers", active="suppliers", suppliers=all_suppliers
    )


@app.route("/suppliers/add", methods=["GET", "POST"])
@admin_required
def add_supplier():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        contact_person = request.form.get("contact_person", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()

        if not name:
            flash("Supplier name is required.", "error")
            return render_template(
                "add_supplier.html", title="Add Supplier", active="suppliers", form=request.form
            )

        conn = get_db()
        conn.execute(
            "INSERT INTO suppliers (name, contact_person, phone, email, address) VALUES (?, ?, ?, ?, ?)",
            (name, contact_person, phone, email, address),
        )
        conn.commit()
        conn.close()
        flash(f'Supplier "{name}" added.', "success")
        return redirect(url_for("suppliers"))

    return render_template("add_supplier.html", title="Add Supplier", active="suppliers", form={})


@app.route("/suppliers/edit/<int:supplier_id>", methods=["GET", "POST"])
@admin_required
def edit_supplier(supplier_id):
    conn = get_db()
    supplier = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()

    if supplier is None:
        conn.close()
        flash("Supplier not found.", "error")
        return redirect(url_for("suppliers"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        contact_person = request.form.get("contact_person", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        address = request.form.get("address", "").strip()

        if not name:
            flash("Supplier name is required.", "error")
            conn.close()
            return render_template(
                "edit_supplier.html", title="Edit Supplier", active="suppliers", supplier=supplier
            )

        conn.execute(
            "UPDATE suppliers SET name=?, contact_person=?, phone=?, email=?, address=? WHERE id=?",
            (name, contact_person, phone, email, address, supplier_id),
        )
        conn.commit()
        conn.close()
        flash(f'Supplier "{name}" updated.', "success")
        return redirect(url_for("suppliers"))

    conn.close()
    return render_template(
        "edit_supplier.html", title="Edit Supplier", active="suppliers", supplier=supplier
    )


@app.route("/suppliers/delete/<int:supplier_id>", methods=["POST"])
@admin_required
def delete_supplier(supplier_id):
    conn = get_db()
    supplier = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
    conn.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
    conn.commit()
    conn.close()
    if supplier:
        flash(f'Supplier "{supplier["name"]}" removed.', "success")
    return redirect(url_for("suppliers"))


@app.route("/reports")
def reports():
    conn = get_db()
    total_value = conn.scalar("SELECT COALESCE(SUM(quantity * price), 0) FROM items")
    total_sales_value = conn.scalar("SELECT COALESCE(SUM(total), 0) FROM sales")
    low_items = conn.execute(
        "SELECT * FROM items WHERE quantity <= low_stock_threshold ORDER BY quantity ASC"
    ).fetchall()
    top_products = conn.execute("""
        SELECT product_name, SUM(quantity) as total_qty, SUM(total) as total_revenue
        FROM sales GROUP BY product_name ORDER BY total_qty DESC LIMIT 5
    """).fetchall()
    category_breakdown = conn.execute("""
        SELECT COALESCE(category, 'Uncategorized') as category, COUNT(*) as n,
               COALESCE(SUM(quantity * price), 0) as value
        FROM items GROUP BY category ORDER BY value DESC
    """).fetchall()
    conn.close()

    max_qty = max([p["total_qty"] for p in top_products], default=0) or 1

    return render_template(
        "reports.html",
        title="Reports",
        active="reports",
        total_value=total_value,
        total_sales_value=total_sales_value,
        low_items=low_items,
        top_products=top_products,
        max_qty=max_qty,
        category_breakdown=category_breakdown,
    )


@app.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    conn = get_db()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add_user":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            role = request.form.get("role", "user")

            if not username or not password:
                flash("Username and password are required.", "error")
            elif role not in ("admin", "user"):
                flash("Invalid role.", "error")
            elif conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
                flash(f'Username "{username}" is already taken.', "error")
            else:
                conn.execute(
                    "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                    (username, generate_password_hash(password), role, date.today().isoformat()),
                )
                conn.commit()
                flash(f'User "{username}" created.', "success")

        elif action == "change_password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            me = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()

            if not me or not check_password_hash(me["password_hash"], current_password):
                flash("Current password is incorrect.", "error")
            elif len(new_password) < 4:
                flash("New password must be at least 4 characters.", "error")
            else:
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(new_password), session["user_id"]),
                )
                conn.commit()
                flash("Password updated.", "success")

        conn.close()
        return redirect(url_for("settings"))

    users = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return render_template("settings.html", title="Settings", active="users", users=users)


@app.route("/settings/users/delete/<int:user_id>", methods=["POST"])
@admin_required
def delete_user(user_id):
    if user_id == session.get("user_id"):
        flash("You can't delete your own account while logged in.", "error")
        return redirect(url_for("settings"))

    conn = get_db()
    admin_count = conn.scalar("SELECT COUNT(*) FROM users WHERE role = 'admin'")
    target = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    if target and target["role"] == "admin" and admin_count <= 1:
        flash("Can't delete the last remaining admin.", "error")
    elif target:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        flash(f'User "{target["username"]}" removed.', "success")

    conn.close()
    return redirect(url_for("settings"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)