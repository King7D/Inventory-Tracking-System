# app.py
import os
import csv
import json
from io import StringIO, BytesIO
from datetime import datetime, timezone
from decimal import Decimal
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from sqlalchemy import asc, desc
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf.csrf import generate_csrf

from tzlocal import get_localzone  # <-- detect computer's timezone

from extensions import db, migrate, login_manager, csrf
from models import User, Item, Warehouse, Location, InventoryBalance
from users_config import DEFAULT_USERS
from forms import LoginForm, ItemForm, ImportForm
from services.audit import audit
from services.import_service import parse_csv


# Display formats (minute precision)
DT_DISPLAY = "%Y-%m-%d %H:%M"
DT_EXPORT = "%Y/%m/%d %H:%M"

# Computer's local timezone (IANA), e.g. "America/Vancouver"
LOCAL_TZ = get_localzone()


def to_local(dt):
    """Convert stored naive-UTC datetime to local timezone-aware datetime for display/export."""
    if not dt:
        return None
    # We store UTC as naive; make it aware in UTC, then convert
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ)


def local_naive_to_utc_naive(dt):
    """Assume a naive datetime is in local time, convert to naive UTC for storage."""
    if not dt:
        return None
    aware_local = dt.replace(tzinfo=LOCAL_TZ)
    aware_utc = aware_local.astimezone(timezone.utc)
    return aware_utc.replace(tzinfo=None)


def create_app():
    app = Flask(__name__)

    # --- Secrets / DB ---
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "supersecretkey")
    os.makedirs(app.instance_path, exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(app.instance_path, "inventory.db"),
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # --- Init extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "login"

    # Make csrf token + format helper available to Jinja
    app.jinja_env.globals["csrf_token"] = generate_csrf

    @app.template_filter("fmt_local")
    def fmt_local(dt):
        """Jinja filter: format datetime in local timezone."""
        if not dt:
            return ""
        return to_local(dt).strftime(DT_DISPLAY)

    # --------- Login manager ---------
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # --------- Role guard ---------
    def role_required(*roles):
        def decorator(fn):
            @wraps(fn)
            def inner(*args, **kwargs):
                if not current_user.is_authenticated:
                    return login_manager.unauthorized()
                if current_user.role not in roles and current_user.role != "admin":
                    flash("Permission denied", "error")
                    return redirect(url_for("index"))
                return fn(*args, **kwargs)
            return inner
        return decorator

    # --------- Helpers ---------
    def get_or_create_default_location():
        """Ensure MAIN / A-01-01 exists; return (warehouse, location)."""
        wh = Warehouse.query.filter_by(code="MAIN").first()
        if not wh:
            wh = Warehouse(name="Main Warehouse", code="MAIN")
            db.session.add(wh)
            db.session.flush()
        loc = Location.query.filter_by(warehouse_id=wh.id, code="A-01-01").first()
        if not loc:
            loc = Location(warehouse_id=wh.id, code="A-01-01", type="pick")
            db.session.add(loc)
            db.session.flush()
        return wh, loc

    def set_item_on_hand(item: Item, new_qty: int):
        """Single-location quick mode: set on-hand in default location."""
        _, loc = get_or_create_default_location()
        bal = InventoryBalance.query.filter_by(item_id=item.id, location_id=loc.id).first()
        if not bal:
            bal = InventoryBalance(item_id=item.id, location_id=loc.id, on_hand=0, allocated=0)
            db.session.add(bal)
        bal.on_hand = int(new_qty or 0)

    # --------- Auth ---------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        # Seed default users if DB empty
        if User.query.count() == 0:
            from werkzeug.security import generate_password_hash
            for u in DEFAULT_USERS:
                user = User(email=u["email"], role=u.get("role", "viewer"))
                user.password_hash = generate_password_hash(u["password"])
                db.session.add(user)
            db.session.commit()

        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(email=form.email.data).first()
            if user and user.check_password(form.password.data):
                login_user(user)
                return redirect(url_for("index"))
            flash("Invalid credentials", "error")
        return render_template("login.html", form=form)

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    # --------- Dashboard ---------
    @app.route("/")
    @login_required
    def index():
        q = request.args.get("q", "").strip()
        sort_by = request.args.get("sort_by", "date_added")
        order = request.args.get("order", "desc")
        page = max(int(request.args.get("page", 1)), 1)
        per_page = int(request.args.get("per_page", 20))

        base_q = Item.query
        if q:
            like = f"%{q}%"
            base_q = base_q.filter((Item.name.ilike(like)) | (Item.sku.ilike(like)))

        # helpers per spec
        def available(i):      # On-hand − Allocated
            return i.available_qty()

        def total_qty(i):      # Total = Available + On-transit
            return available(i) + (i.on_transit or 0)

        def needs_reorder(i):  # when Total <= Reorder Point
            return total_qty(i) <= (i.reorder_point or 0)

        SORT_MAP = {
            "date_added": Item.date_added,
            "name": Item.name,
            "sku": Item.sku,
            "price": Item.price,
        }

        if sort_by in ("available", "needs_reorder"):
            items_all = base_q.all()
            if sort_by == "available":
                items_all.sort(key=lambda i: available(i), reverse=(order == "desc"))
            else:
                # put items that need reorder (True) first
                items_all.sort(key=lambda i: (not needs_reorder(i), i.name.lower()))
            total_count = len(items_all)
            start = (page - 1) * per_page
            page_items = items_all[start:start + per_page]
        else:
            col = SORT_MAP.get(sort_by, Item.date_added)
            page_obj = base_q.order_by(desc(col) if order == "desc" else asc(col)) \
                             .paginate(page=page, per_page=per_page, error_out=False)
            page_items, total_count = page_obj.items, page_obj.total
            items_all = base_q.all()

        # Orange banner (warning category)
        low_count = sum(1 for i in page_items if needs_reorder(i))
        if low_count:
            flash(f"{low_count} item(s) at or below reorder point on this page.", "warning")

        # Inventory totals (values)
        inv_total_all = sum(Decimal(total_qty(i)) * (i.price or Decimal("0")) for i in items_all)
        inv_total_page = sum(Decimal(total_qty(i)) * (i.price or Decimal("0")) for i in page_items)

        return render_template(
            "index.html",
            items=page_items, total=total_count, page=page, per_page=per_page,
            q=q, sort_by=sort_by, order=order,
            inv_total_all=inv_total_all, inv_total_page=inv_total_page,
        )

    # --------- Create / Edit / Delete ---------
    @app.route("/items/new", methods=["GET", "POST"])
    @login_required
    @role_required("ops", "buyer")
    def create_item():
        form = ItemForm()
        if form.validate_on_submit():
            if Item.query.filter_by(sku=form.sku.data).first():
                flash("SKU already exists", "error")
                return render_template("items/edit.html", form=form, mode="create")

            item = Item(
                sku=form.sku.data,
                name=form.name.data,
                price=Decimal(form.price.data or 0),
                reorder_point=int(form.reorder_point.data or 0),
                on_transit=int(form.on_transit.data or 0),
            )
            db.session.add(item)
            db.session.flush()
            set_item_on_hand(item, int(form.on_hand.data or 0))
            audit("create", "Item", after={"sku": item.sku, "name": item.name})
            db.session.commit()
            flash("Item created", "success")
            return redirect(url_for("index"))
        elif request.method == "POST":
            flash(str(form.errors), "error")
        return render_template("items/edit.html", form=form, mode="create")

    @app.route("/items/<int:item_id>/edit", methods=["GET", "POST"])
    @login_required
    @role_required("ops", "buyer")
    def edit_item(item_id):
        item = db.session.get(Item, item_id)
        if not item:
            flash("Item not found", "error")
            return redirect(url_for("index"))

        form = ItemForm(request.form if request.method == "POST" else None, obj=item)
        current_on_hand = item.on_hand_total()
        if request.method == "GET":
            form.on_hand.data = current_on_hand

        if form.validate_on_submit():
            before = {
                "sku": item.sku, "name": item.name, "price": str(item.price),
                "reorder_point": item.reorder_point, "on_transit": item.on_transit,
                "on_hand": current_on_hand
            }
            item.sku = form.sku.data
            item.name = form.name.data
            item.price = Decimal(form.price.data or 0)
            item.reorder_point = int(form.reorder_point.data or 0)
            item.on_transit = int(form.on_transit.data or 0)

            db.session.flush()
            set_item_on_hand(item, int(form.on_hand.data if form.on_hand.data is not None else current_on_hand))

            # store UTC naive
            item.last_changed = datetime.utcnow()
            audit("update", "Item", entity_id=item.id, before=before, after={
                "sku": item.sku, "name": item.name, "price": str(item.price),
                "reorder_point": item.reorder_point, "on_transit": item.on_transit,
                "on_hand": int(form.on_hand.data or 0)
            })
            db.session.commit()
            flash("Item updated", "success")
            return redirect(url_for("index"))
        elif request.method == "POST":
            flash(str(form.errors), "error")

        return render_template("items/edit.html", form=form, mode="edit", item=item)

    @app.route("/items/<int:item_id>/delete", methods=["POST"])
    @login_required
    @role_required("ops", "buyer")
    def delete_item(item_id):
        item = db.session.get(Item, item_id)
        if not item:
            flash("Item not found", "error")
            return redirect(url_for("index"))
        audit("delete", "Item", entity_id=item.id, before={"sku": item.sku, "name": item.name})
        db.session.delete(item)
        db.session.commit()
        flash("Item deleted", "success")
        return redirect(url_for("index"))

    # --------- Export CSV (includes Reorder Point; times in local tz) ---------
    @app.route("/export")
    @login_required
    def export_csv():
        items = Item.query.order_by(desc(Item.date_added)).all()
        si = StringIO()
        writer = csv.writer(si)
        # Added "Reorder Point" column (after Total)
        writer.writerow([
            "Date Added", "Item Name", "SKU", "Available", "On-Transit", "Total",
            "Reorder Point", "Price", "Total Value", "Last Changed"
        ])
        for it in items:
            avail = it.available_qty()
            total = avail + (it.on_transit or 0)
            total_val = Decimal(total) * (it.price or Decimal("0"))
            # Format times using local tz
            date_added_str = to_local(it.date_added).strftime(DT_EXPORT) if it.date_added else ""
            last_changed_str = to_local(it.last_changed).strftime(DT_EXPORT) if it.last_changed else ""
            writer.writerow([
                date_added_str,
                it.name,
                it.sku,
                avail,
                it.on_transit or 0,
                total,
                it.reorder_point or 0,
                f"{Decimal(it.price):.2f}",
                f"{total_val:.2f}",
                last_changed_str,
            ])
        output = si.getvalue().encode("utf-8")
        return send_file(BytesIO(output), mimetype="text/csv", as_attachment=True, download_name="inventory.csv")

    # --------- Import Wizard (two-step: preview -> commit) ---------
    @app.route("/import", methods=["GET", "POST"])
    @login_required
    @role_required("ops", "buyer")
    def import_wizard():
        form = ImportForm()

        # Step 2: Commit (Upsert or Replace) from preview
        if request.method == "POST" and request.form.get("action") in {"commit_upsert", "commit_replace"}:
            rows_json = session.get("import_rows_json")
            if not rows_json:
                flash("No parsed rows found. Please upload the file again.", "error")
                return redirect(url_for("import_wizard"))
            rows = json.loads(rows_json)
            do_replace = (request.form.get("action") == "commit_replace")

            if do_replace:
                for item in Item.query.all():
                    db.session.delete(item)
                db.session.flush()
                audit("truncate", "Item")

            inserted, updated = 0, 0
            for r in rows:
                item = Item.query.filter_by(sku=r["sku"]).first()
                # Convert local naive -> UTC naive for storage if present
                date_added = datetime.fromisoformat(r["date_added"]) if r.get("date_added") else None
                last_changed = datetime.fromisoformat(r["last_changed"]) if r.get("last_changed") else None
                if date_added:
                    date_added = local_naive_to_utc_naive(date_added)
                if last_changed:
                    last_changed = local_naive_to_utc_naive(last_changed)

                if not item:
                    item = Item(
                        sku=r["sku"],
                        name=r["name"],
                        price=Decimal(str(r["price"])),
                        reorder_point=int(r.get("reorder_point") or 0),
                    )
                    if date_added:
                        item.date_added = date_added
                    if last_changed:
                        item.last_changed = last_changed
                    db.session.add(item)
                    db.session.flush()
                    # on-hand := available (allocations assumed 0)
                    set_item_on_hand(item, r["available"])
                    item.on_transit = r["on_transit"]
                    inserted += 1
                else:
                    item.name = r["name"] or item.name
                    item.price = Decimal(str(r["price"])) if r["price"] is not None else item.price
                    item.reorder_point = int(r.get("reorder_point") or item.reorder_point or 0)
                    if date_added and not item.date_added:
                        item.date_added = date_added
                    if last_changed:
                        item.last_changed = last_changed
                    db.session.flush()
                    set_item_on_hand(item, r["available"])
                    item.on_transit = r["on_transit"]
                    updated += 1
            db.session.commit()
            # clear session payload after commit
            session.pop("import_rows_json", None)
            flash(f"Import complete. Inserted {inserted}, Updated {updated}.", "success")
            return redirect(url_for("index"))

        # Step 1: Upload -> always do dry-run preview
        if request.method == "POST" and form.validate_on_submit() and request.form.get("action") == "preview":
            parsed = parse_csv(form.file.data)  # now also parses Reorder Point
            # Show parse errors (warnings for total mismatch)
            if parsed["errors"]:
                for e in parsed["errors"]:
                    flash(e, "warning" if "Total !=" in e else "error")

            # Store compact rows in session (ISO; still local-naive; convert at commit time)
            compact_rows = []
            for r in parsed["rows"]:
                compact_rows.append({
                    "name": r["name"],
                    "sku": r["sku"],
                    "available": int(r["available"]),
                    "on_transit": int(r["on_transit"]),
                    "reorder_point": int(r.get("reorder_point") or 0),
                    "price": str(r["price"]),
                    "date_added": r["date_added"].isoformat() if r["date_added"] else None,
                    "last_changed": r["last_changed"].isoformat() if r["last_changed"] else None,
                })
            session["import_rows_json"] = json.dumps(compact_rows)

            return render_template("import_wizard.html", form=form, preview=True, rows=parsed["rows"])
        # GET (or non-matching POST) -> initial screen
        return render_template("import_wizard.html", form=form, preview=False)

    # --------- First-run seed for WH/Location ---------
    with app.app_context():
        db.create_all()
        if Warehouse.query.count() == 0:
            wh = Warehouse(name="Main Warehouse", code="MAIN")
            db.session.add(wh)
            db.session.flush()
            loc = Location(warehouse_id=wh.id, code="A-01-01", type="pick")
            db.session.add(loc)
            db.session.commit()

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
