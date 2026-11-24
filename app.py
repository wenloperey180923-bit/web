from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import basedatos


ROOT = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("DATABASE_PATH", ROOT / "instance" / "awos.sqlite3"))
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)
ADMIN_P9_PASSWORD_HASH = os.environ.get(
    "ADMIN_P9_PASSWORD_HASH", generate_password_hash("admin")
)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = basedatos.connect(DATABASE)
    return g.db


@app.teardown_appcontext
def close_db(_error: BaseException | None = None) -> None:
    database = g.pop("db", None)
    if database is not None:
        database.close()


def init_db() -> None:
    db = get_db()
    if basedatos.MYSQL:
        db.executescript(basedatos.SCHEMA)
        db.commit()
        return
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            precio REAL NOT NULL,
            existencia INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS estudiantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matricula TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            apellido TEXT NOT NULL,
            carrera TEXT NOT NULL,
            correo TEXT NOT NULL,
            promedio REAL NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS respuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            carrera TEXT NOT NULL,
            factor TEXT NOT NULL,
            instalaciones TEXT NOT NULL,
            mejora TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visitante_id TEXT NOT NULL,
            sesion_id TEXT NOT NULL,
            usuario_id INTEGER REFERENCES estudiantes(id) ON DELETE SET NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('vista', 'clic', 'tiempo')),
            pagina TEXT NOT NULL,
            elemento TEXT,
            segundos INTEGER,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_eventos_visitante ON eventos(visitante_id);
        CREATE INDEX IF NOT EXISTS idx_eventos_sesion ON eventos(sesion_id);
        CREATE TABLE IF NOT EXISTS productos_tienda (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            marca TEXT NOT NULL,
            categoria TEXT NOT NULL,
            precio REAL NOT NULL,
            existencia INTEGER NOT NULL,
            codigo_barras TEXT NOT NULL UNIQUE,
            promocion TEXT
        );
        CREATE TABLE IF NOT EXISTS chat_mensajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            autor_matricula TEXT NOT NULL,
            autor_nombre TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            creado_en TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    db.commit()


@app.before_request
def ensure_database() -> None:
    if not app.config.get("_database_initialized"):
        init_db()
        app.config["_database_initialized"] = True


@app.context_processor
def template_helpers() -> dict[str, Any]:
    return {
        "current_user": session.get("usuario"),
        "admin_active": bool(session.get("admin_p9")),
        "asset": lambda filename: url_for("assets", filename=filename),
    }


@app.route("/assets/<path:filename>")
def assets(filename: str):
    return send_from_directory(ROOT / "assets", filename)


@app.get("/")
def home():
    cards = [
        ("Práctica 3", "CRUD completo de productos.", "practice3"),
        ("Práctica 4", "Sitio personal con mapas.", "practice4"),
        ("Práctica 5", "Login, sesiones y CRUD de estudiantes.", "practice5"),
        ("Práctica 6", "Encuesta de satisfacción.", "practice6"),
        ("Práctica 7", "Video incrustado.", "practice7"),
        ("Práctica 8", "Métricas de uso del sitio.", "practice8"),
        ("Práctica 9", "Tienda de ropa, inventario y chat.", "practice9"),
    ]
    return render_template("home.html", title="Inicio", cards=cards)


def product_form_data() -> dict[str, Any]:
    return {
        "nombre": request.form.get("nombre", "").strip(),
        "descripcion": request.form.get("descripcion", "").strip(),
        "precio": request.form.get("precio", ""),
        "existencia": request.form.get("existencia", ""),
    }


def simple_product_error(data: dict[str, Any]) -> str | None:
    try:
        price = float(data["precio"])
        stock = int(data["existencia"])
        if price < 0 or stock < 0:
            raise ValueError
    except (ValueError, TypeError):
        return "El precio y la existencia deben ser números válidos no negativos."
    if not data["nombre"] or not data["descripcion"]:
        return "Completa el nombre y la descripción."
    return None


@app.route("/p3", defaults={"action": ""}, methods=["GET", "POST"])
@app.route("/p3/<action>", defaults={"product_id": None}, methods=["GET", "POST"])
@app.route("/p3/<action>/<int:product_id>", methods=["GET", "POST"])
def practice3(action: str, product_id: int | None = None):
    db = get_db()
    if action == "eliminar" and product_id is not None:
        if request.method == "POST":
            db.execute("DELETE FROM productos WHERE id = ?", (product_id,))
            db.commit()
            flash("Producto eliminado correctamente.", "info")
        return redirect(url_for("practice3"))
    if action in ("crear", "editar"):
        product = None
        if action == "editar":
            product = db.execute(
                "SELECT * FROM productos WHERE id = ?", (product_id,)
            ).fetchone()
            if product is None:
                abort(404)
        if request.method == "POST":
            data = product_form_data()
            error = simple_product_error(data)
            if error:
                flash(error, "error")
            else:
                if action == "crear":
                    db.execute(
                        "INSERT INTO productos(nombre, descripcion, precio, existencia) "
                        "VALUES (?, ?, ?, ?)",
                        (data["nombre"], data["descripcion"], float(data["precio"]),
                         int(data["existencia"])),
                    )
                    flash("Producto agregado correctamente.", "exito")
                else:
                    db.execute(
                        "UPDATE productos SET nombre=?, descripcion=?, precio=?, existencia=? "
                        "WHERE id=?",
                        (data["nombre"], data["descripcion"], float(data["precio"]),
                         int(data["existencia"]), product_id),
                    )
                    flash("Producto modificado correctamente.", "exito")
                db.commit()
                return redirect(url_for("practice3"))
        return render_template(
            "form.html",
            title=("Agregar" if action == "crear" else "Editar") + " producto",
            kind="product",
            item=product,
            action=action,
        )
    products = db.execute("SELECT * FROM productos ORDER BY nombre").fetchall()
    return render_template("p3.html", title="Práctica 3 · CRUD de productos", products=products)


@app.get("/p4")
def practice4():
    return render_template("p4.html", title="Práctica 4 · Sitio personal")


def login_required():
    if not session.get("usuario"):
        flash("Inicia sesión para continuar.", "info")
        return redirect(url_for("practice5", action="login"))
    return None


@app.route("/p5", defaults={"action": ""}, methods=["GET", "POST"])
@app.route("/p5/<action>", methods=["GET", "POST"])
@app.route("/p5/estudiantes/<action>", defaults={"student_id": None}, methods=["GET", "POST"])
@app.route("/p5/estudiantes/<action>/<int:student_id>", methods=["GET", "POST"])
def practice5(action: str, student_id: int | None = None):
    db = get_db()
    if action == "login":
        if request.method == "POST":
            student = db.execute(
                "SELECT * FROM estudiantes WHERE matricula = ?",
                (request.form.get("usuario", "").strip(),),
            ).fetchone()
            if student and check_password_hash(
                student["password_hash"], request.form.get("contrasena", "")
            ):
                session.clear()
                session["usuario"] = student["matricula"]
                flash(f"¡Hola {student['nombre']}! Iniciaste sesión.", "exito")
                return redirect(url_for("practice5"))
            flash("Matrícula o contraseña incorrectos.", "error")
        return render_template("form.html", title="Iniciar sesión", kind="login")
    if action == "registro":
        if request.method == "POST":
            data = student_form_data()
            password = request.form.get("contrasena", "")
            if len(password) < 8 or password != request.form.get("repetir_contrasena", ""):
                flash("La contraseña debe tener 8 caracteres y coincidir.", "error")
            elif not valid_student(data):
                flash("Revisa los datos del estudiante.", "error")
            else:
                try:
                    insert_student(db, data, password)
                    db.commit()
                except basedatos.INTEGRITY_ERRORS:
                    flash("Ya existe un estudiante con esa matrícula.", "error")
                else:
                    flash("¡Cuenta creada! Ya puedes iniciar sesión.", "exito")
                    return redirect(url_for("practice5", action="login"))
        return render_template("form.html", title="Registrar estudiante", kind="student_register")
    if action == "logout":
        if not session.get("usuario"):
            return redirect(url_for("practice5", action="login"))
        session.pop("usuario", None)
        flash("Cerraste sesión correctamente.", "info")
        return redirect(url_for("practice5", action="login"))

    guard = login_required()
    if guard:
        return guard
    if action in ("crear", "editar"):
        student = None
        if action == "editar":
            student = db.execute(
                "SELECT id, matricula, nombre, apellido, carrera, correo, promedio "
                "FROM estudiantes WHERE id = ?", (student_id,),
            ).fetchone()
            if student is None:
                abort(404)
        if request.method == "POST":
            data = student_form_data()
            password = request.form.get("contrasena", "")
            if not valid_student(data):
                flash("Completa correctamente los datos del estudiante.", "error")
            elif action == "crear" and not password:
                flash("La contraseña no puede quedar vacía.", "error")
            else:
                try:
                    if action == "crear":
                        insert_student(db, data, password)
                    else:
                        db.execute(
                            "UPDATE estudiantes SET matricula=?, nombre=?, apellido=?, carrera=?, "
                            "correo=?, promedio=? WHERE id=?",
                            (*student_values(data), student_id),
                        )
                    db.commit()
                except basedatos.INTEGRITY_ERRORS:
                    flash("Ya existe un estudiante con esa matrícula.", "error")
                else:
                    flash("Estudiante guardado correctamente.", "exito")
                    return redirect(url_for("practice5", action="estudiantes"))
        return render_template(
            "form.html", title="Estudiante", kind="student", item=student, action=action
        )
    if action == "eliminar" and student_id is not None:
        if request.method == "POST":
            db.execute("DELETE FROM estudiantes WHERE id=?", (student_id,))
            db.commit()
            flash("Estudiante eliminado correctamente.", "info")
        return redirect(url_for("practice5", action="estudiantes"))
    if action == "estudiantes":
        students = db.execute(
            "SELECT id, matricula, nombre, apellido, carrera, correo, promedio "
            "FROM estudiantes ORDER BY apellido"
        ).fetchall()
        return render_template("p5_students.html", title="Lista de estudiantes", students=students)
    return render_template("p5.html", title="Práctica 5 · Gestión de estudiantes")


def student_form_data() -> dict[str, str]:
    return {
        key: request.form.get(key, "").strip()
        for key in ("matricula", "nombre", "apellido", "carrera", "correo", "promedio")
    }


def valid_student(data: dict[str, str]) -> bool:
    if not all(data[key] for key in ("matricula", "nombre", "apellido", "carrera", "correo")):
        return False
    try:
        return 0 <= float(data["promedio"]) <= 10
    except ValueError:
        return False


def student_values(data: dict[str, str]) -> tuple[Any, ...]:
    return (
        data["matricula"], data["nombre"], data["apellido"], data["carrera"],
        data["correo"], float(data["promedio"]),
    )


def insert_student(db: sqlite3.Connection, data: dict[str, str], password: str) -> None:
    db.execute(
        "INSERT INTO estudiantes(matricula,nombre,apellido,carrera,correo,promedio,password_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (*student_values(data), generate_password_hash(password)),
    )


@app.route("/p6", defaults={"action": ""}, methods=["GET", "POST"])
@app.route("/p6/<action>", methods=["GET", "POST"])
def practice6(action: str):
    db = get_db()
    if action == "encuesta":
        if request.method == "POST":
            fields = ("nombre", "carrera", "factor", "instalaciones", "mejora")
            values = [request.form.get(field, "").strip() for field in fields]
            if not all(values):
                flash("Completa todas las respuestas.", "error")
            else:
                db.execute(
                    "INSERT INTO respuestas(nombre,carrera,factor,instalaciones,mejora) "
                    "VALUES (?, ?, ?, ?, ?)", values,
                )
                db.commit()
                return redirect(url_for("practice6", action="regalo"))
        total = db.execute("SELECT COUNT(*) FROM respuestas").fetchone()[0]
        return render_template("p6_survey.html", title="Formulario de encuesta", total=total)
    if action == "regalo":
        return render_template("p6_thanks.html", title="Gracias por tu respuesta")
    return render_template("p6.html", title="Práctica 6 · Encuesta UPVM")


@app.route("/p7", defaults={"action": ""})
@app.route("/p7/<action>")
def practice7(action: str):
    return render_template(
        "p7.html", title="Práctica 7 · Video", show_video=action == "video"
    )


UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@app.route("/p8")
def practice8():
    return render_template("p8.html", title="Práctica 8 · Métricas", panel=False)


@app.get("/p8/panel")
def metrics_panel():
    return render_template("p8.html", title="Práctica 8 · Métricas", panel=True)


@app.route("/p8/eventos", methods=["POST"])
def track_event():
    try:
        data = json.loads(request.get_data(as_text=True))
    except (json.JSONDecodeError, UnicodeDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    kind, visitor, browsing_session = (
        data.get("tipo"), data.get("visitante_id"), data.get("sesion_id")
    )
    if kind not in {"vista", "clic", "tiempo"} or not all(
        isinstance(value, str) and UUID_PATTERN.fullmatch(value)
        for value in (visitor, browsing_session)
    ):
        return jsonify(error="Evento inválido."), 400
    page = str(data.get("pagina", ""))[:200]
    if not page:
        return jsonify(error="Falta la página del evento."), 400
    element = str(data.get("elemento", ""))[:100] if kind == "clic" else None
    seconds = min(3600, max(0, int(data.get("segundos", 0) or 0))) if kind == "tiempo" else None
    db = get_db()
    user = db.execute(
        "SELECT id FROM estudiantes WHERE matricula=?", (session.get("usuario"),)
    ).fetchone()
    user_id = user["id"] if user else None
    db.execute(
        "INSERT INTO eventos(visitante_id,sesion_id,usuario_id,tipo,pagina,elemento,segundos) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (visitor, browsing_session, user_id, kind, page, element, seconds),
    )
    if user_id and request.cookies.get("awos_visitante_id"):
        db.execute(
            "UPDATE eventos SET usuario_id=? WHERE visitante_id=? AND usuario_id IS NULL",
            (user_id, request.cookies["awos_visitante_id"]),
        )
    db.commit()
    return "", 204


@app.get("/p8/metricas")
def metrics():
    db = get_db()
    summary = dict(db.execute(
        """
        SELECT COUNT(DISTINCT visitante_id) visitantes,
               COUNT(DISTINCT sesion_id) sesiones,
               COUNT(DISTINCT usuario_id) usuarios,
               COALESCE(SUM(CASE WHEN tipo='vista' THEN 1 ELSE 0 END),0) vistas,
               COALESCE(SUM(CASE WHEN tipo='clic' THEN 1 ELSE 0 END),0) clics
        FROM eventos
        """
    ).fetchone())
    average = db.execute(
        "SELECT COALESCE(ROUND(AVG(total)),0) FROM "
        "(SELECT SUM(segundos) total FROM eventos WHERE tipo='tiempo' GROUP BY sesion_id)"
    ).fetchone()[0]
    summary["tiempo_promedio"] = average
    pages = rows(db, """
        SELECT pagina, SUM(CASE WHEN tipo='vista' THEN 1 ELSE 0 END) vistas, SUM(CASE WHEN tipo='clic' THEN 1 ELSE 0 END) clics,
               COALESCE(SUM(segundos),0) segundos FROM eventos
        GROUP BY pagina ORDER BY vistas DESC LIMIT 10
    """)
    clicks = rows(db, """
        SELECT elemento, pagina, COUNT(*) total FROM eventos WHERE tipo='clic'
        GROUP BY elemento, pagina ORDER BY total DESC LIMIT 10
    """)
    users = rows(db, """
        SELECT COALESCE(u.nombre,'(anónimos)') nombre, COALESCE(u.carrera,'—') carrera,
               COUNT(DISTINCT e.sesion_id) sesiones, SUM(CASE WHEN e.tipo='vista' THEN 1 ELSE 0 END) vistas,
               SUM(CASE WHEN e.tipo='clic' THEN 1 ELSE 0 END) clics, COALESCE(SUM(e.segundos),0) segundos,
               MAX(e.creado_en) ultima
        FROM eventos e LEFT JOIN estudiantes u ON u.id=e.usuario_id
        GROUP BY e.usuario_id,u.nombre,u.carrera ORDER BY ultima DESC
    """)
    careers = rows(db, """
        SELECT u.carrera, COUNT(DISTINCT u.id) usuarios, SUM(CASE WHEN e.tipo='clic' THEN 1 ELSE 0 END) clics,
               COALESCE(SUM(e.segundos),0) segundos
        FROM eventos e JOIN estudiantes u ON u.id=e.usuario_id
        GROUP BY u.carrera ORDER BY segundos DESC
    """)
    recent = rows(db, """
        SELECT strftime('%H:%M:%S',e.creado_en) hora, COALESCE(u.nombre,'Anónimo') nombre,
               e.tipo,e.pagina,e.elemento,e.segundos
        FROM eventos e LEFT JOIN estudiantes u ON u.id=e.usuario_id
        ORDER BY e.id DESC LIMIT 15
    """)
    return jsonify(resumen=summary, paginas=pages, clics=clicks, usuarios=users,
                   carreras=careers, recientes=recent)


def rows(db: sqlite3.Connection, query: str) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(query).fetchall()]


SAMPLE_PRODUCTS = [
    ("Playera básica", "Cuidado con el Perro", "Playeras", 199, 24, "7500010000001", "2 por $349"),
    ("Playera estampada", "Cuidado con el Perro", "Playeras", 249, 18, "7500010000002", None),
    ("Jeans rectos", "Cuidado con el Perro", "Pantalones", 499, 12, "7500010000003", None),
    ("Pantalón cargo", "Cuidado con el Perro", "Pantalones", 549, 10, "7500010000004", None),
    ("Sudadera con capucha", "Cuidado con el Perro", "Sudaderas", 599, 9, "7500010000005", None),
    ("Chamarra ligera", "Cuidado con el Perro", "Chamarras", 699, 6, "7500010000006", None),
    ("Gorra bordada", "Cuidado con el Perro", "Accesorios", 229, 20, "7500010000007", None),
    ("Bolsa casual", "Cuidado con el Perro", "Accesorios", 299, 8, "7500010000008", None),
]


def shop_product_data() -> dict[str, str]:
    return {key: request.form.get(key, "").strip() for key in (
        "nombre", "marca", "categoria", "precio", "existencia", "codigo_barras", "promocion"
    )}


def shop_product_error(data: dict[str, str]) -> str | None:
    limits = {"nombre": 120, "marca": 80, "categoria": 60, "codigo_barras": 20, "promocion": 120}
    for field in ("nombre", "marca", "categoria", "codigo_barras"):
        if not data[field]:
            return "Completa los campos obligatorios."
    if any(len(data[key]) > limit for key, limit in limits.items()):
        return "Uno de los campos supera la longitud permitida."
    try:
        price = float(data["precio"])
        stock = int(data["existencia"])
        if not 0 <= price <= 99999999.99 or stock < 0:
            raise ValueError
    except (ValueError, TypeError):
        return "El precio y la existencia deben ser números válidos no negativos."
    return None


def shop_return():
    return redirect(url_for("practice9", action="admin" if session.get("admin_p9") else ""))


@app.route("/p9", defaults={"action": ""}, methods=["GET", "POST"])
@app.route("/p9/<action>", methods=["GET", "POST"])
@app.route("/p9/editar/<int:product_id>", defaults={"action": "editar"}, methods=["GET", "POST"])
@app.route("/p9/eliminar/<int:product_id>", defaults={"action": "eliminar"}, methods=["GET", "POST"])
def practice9(action: str, product_id: int | None = None):
    db = get_db()
    if action == "ejemplo":
        if request.method == "POST":
            db.executemany(
                "INSERT OR IGNORE INTO productos_tienda"
                "(nombre,marca,categoria,precio,existencia,codigo_barras,promocion) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", SAMPLE_PRODUCTS,
            )
            db.commit()
            flash("Se cargó el catálogo de ejemplo.", "exito")
        return shop_return()
    if action == "admin":
        if request.args.get("salir") is not None:
            session.pop("admin_p9", None)
            flash("Cerraste la sesión de administrador.", "info")
            return redirect(url_for("practice9", action="admin"))
        if request.method == "POST":
            if (
                secrets.compare_digest(request.form.get("matricula", ""), "777")
                and check_password_hash(
                    ADMIN_P9_PASSWORD_HASH, request.form.get("contrasena", "")
                )
            ):
                session["admin_p9"] = True
                return redirect(url_for("practice9", action="admin"))
            flash("Matrícula o contraseña de administrador incorrectas.", "error")
        if not session.get("admin_p9"):
            return render_template("p9_admin_login.html", title="Administración")
    if action == "crear" or action == "editar":
        product = None
        if action == "editar":
            product = db.execute("SELECT * FROM productos_tienda WHERE id=?", (product_id,)).fetchone()
            if product is None:
                abort(404)
        if request.method == "POST":
            data = shop_product_data()
            error = shop_product_error(data)
            if error:
                flash(error, "error")
            else:
                values = (
                    data["nombre"], data["marca"], data["categoria"], float(data["precio"]),
                    int(data["existencia"]), data["codigo_barras"], data["promocion"] or None,
                )
                try:
                    if action == "crear":
                        db.execute(
                            "INSERT INTO productos_tienda"
                            "(nombre,marca,categoria,precio,existencia,codigo_barras,promocion) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)", values,
                        )
                    else:
                        db.execute(
                            "UPDATE productos_tienda SET nombre=?,marca=?,categoria=?,precio=?,"
                            "existencia=?,codigo_barras=?,promocion=? WHERE id=?",
                            (*values, product_id),
                        )
                    db.commit()
                except basedatos.INTEGRITY_ERRORS:
                    flash("Ya existe un producto con ese código de barras.", "error")
                else:
                    flash("Producto guardado correctamente.", "exito")
                    return shop_return()
        return render_template("form.html", title="Producto de tienda", kind="shop",
                               item=product, action=action)
    if action == "eliminar" and product_id is not None:
        if request.method == "POST":
            db.execute("DELETE FROM productos_tienda WHERE id=?", (product_id,))
            db.commit()
            flash("Producto eliminado correctamente.", "info")
        return shop_return()
    if action == "chat":
        return shop_chat(db)
    if action == "":
        query = request.args.get("q", "").strip()
        category = request.args.get("categoria", "").strip()
        clauses, params = [], []
        if query:
            clauses.append("(nombre LIKE ? OR marca LIKE ? OR categoria LIKE ? OR codigo_barras LIKE ?)")
            params.extend([f"%{query}%"] * 4)
        if category:
            clauses.append("categoria=?")
            params.append(category)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        products = db.execute(
            "SELECT * FROM productos_tienda" + where + " ORDER BY categoria,nombre", params
        ).fetchall()
        categories = [row[0] for row in db.execute(
            "SELECT DISTINCT categoria FROM productos_tienda ORDER BY categoria"
        ).fetchall()]
        stats = shop_stats(db)
        branches = make_branches()
        return render_template("p9.html", title="Práctica 9 · Cuidado con el Perro", products=products,
                               categories=categories, query=query, category=category,
                               stats=stats, branches=branches)
    if action == "admin":
        query = request.args.get("q", "").strip()
        category = request.args.get("categoria", "").strip()
        clauses, params = [], []
        if query:
            clauses.append("(nombre LIKE ? OR marca LIKE ? OR categoria LIKE ? OR codigo_barras LIKE ?)")
            params.extend([f"%{query}%"] * 4)
        if category:
            clauses.append("categoria=?")
            params.append(category)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        products = db.execute(
            "SELECT * FROM productos_tienda" + where + " ORDER BY categoria,nombre", params
        ).fetchall()
        categories = [row[0] for row in db.execute(
            "SELECT DISTINCT categoria FROM productos_tienda ORDER BY categoria"
        ).fetchall()]
        return render_template("p9.html", title="Administración · Cuidado con el Perro", products=products,
                               categories=categories, query=query, category=category,
                               stats=shop_stats(db), branches=[], admin_view=True)
    abort(404)


@app.get("/p9/admin/salir")
def shop_admin_logout():
    session.pop("admin_p9", None)
    flash("Cerraste la sesión de administrador.", "info")
    return redirect(url_for("practice9", action="admin"))


def shop_stats(db: sqlite3.Connection) -> dict[str, Any]:
    return dict(zip(
        ("productos", "piezas", "valor", "bajos", "agotados", "promociones"),
        db.execute(
            "SELECT COUNT(*),COALESCE(SUM(existencia),0),COALESCE(SUM(precio*existencia),0),"
            "SUM(CASE WHEN existencia>0 AND existencia<10 THEN 1 ELSE 0 END),SUM(CASE WHEN existencia=0 THEN 1 ELSE 0 END),"
            "SUM(CASE WHEN promocion IS NOT NULL AND promocion<>'' THEN 1 ELSE 0 END) FROM productos_tienda"
        ).fetchone(),
    ))


def make_branches() -> list[dict[str, Any]]:
    return [
        {"nombre": "Cuidado con el Perro – Las Américas Ecatepec",
         "direccion": "Av. Central, Manzana 4, Lotes 1 y 2, locales SB-09 y LA-22, Fraccionamiento Las Américas, Ecatepec, Estado de México.",
         "horario": "Lunes a domingo de 11:00 a. m. a 9:00 p. m."},
        {"nombre": "Cuidado con el Perro – Gran Patio Ecatepec",
         "direccion": "Carretera Texcoco-Lechería No. 8, local L08E, Santa Cruz Venta de Carpio, Ecatepec, Estado de México.",
         "horario": "Lunes a domingo de 11:00 a. m. a 9:00 p. m."},
        {"nombre": "Cuidado con el Perro – Multiplaza Aragón",
         "direccion": "Av. Carlos Hank González No. 120, Ciudad Azteca, Ecatepec, Estado de México.",
         "horario": "Lunes a domingo de 11:00 a. m. a 9:00 p. m."},
        {"nombre": "Cuidado con el Perro – Cosmopol",
         "direccion": "Avenida José López Portillo No. 1, Plaza Cosmopol, Coacalco, Estado de México.",
         "horario": "Lunes a domingo de 11:00 a. m. a 9:00 p. m."},
        {"nombre": "Cuidado con el Perro – Puerta Texcoco",
         "direccion": "Kilómetro 30.5, Carretera México-Texcoco, local 136, Santiago Cuautlalpan, Texcoco, Estado de México.",
         "horario": "Lunes a domingo de 11:00 a. m. a 9:00 p. m."},
        {"nombre": "Cuidado con el Perro – Texcoco Centro",
         "direccion": "Calle Colón No. 124 y 126, Centro, Texcoco, Estado de México.",
         "horario": "Lunes a domingo de 10:00 a. m. a 9:00 p. m."},
        {"nombre": "Cuidado con el Perro – Patio Texcoco",
         "direccion": "Camino de las Flores S/N, locales S13, S14 y J07, Santa Cruz de Arriba, Texcoco, Estado de México.",
         "horario": "Lunes a domingo de 11:00 a. m. a 9:00 p. m."},
        {"nombre": "Cuidado con el Perro – Tecámac",
         "direccion": "Carretera México-Pachuca No. 3855, Centro, Tecámac, Estado de México.",
         "horario": "Lunes a domingo de 9:30 a. m. a 8:30 p. m."},
        {"nombre": "Cuidado con el Perro – Fórum Buenavista",
         "direccion": "Eje 1 Norte Mosqueta No. 259, locales N1-50 y N1-51, Buenavista, Cuauhtémoc, Ciudad de México.",
         "horario": "Lunes a domingo de 11:00 a. m. a 9:00 p. m."},
    ]


def current_chat_author(db: sqlite3.Connection):
    if not session.get("usuario"):
        return None
    return db.execute(
        "SELECT matricula,nombre,apellido FROM estudiantes WHERE matricula=?",
        (session["usuario"],),
    ).fetchone()


def chat_message(row: sqlite3.Row, own_matricula: str | None = None) -> dict[str, Any]:
    return {
        "id": row["id"],
        "autor_matricula": row["autor_matricula"],
        "autor_nombre": row["autor_nombre"],
        "mensaje": row["mensaje"],
        "hora": row["creado_en"],
        "es_mio": row["autor_matricula"] == own_matricula,
    }


def shop_chat(db: sqlite3.Connection):
    author = current_chat_author(db)
    if author is None:
        if request.path.endswith("/mensajes") or request.path.endswith("/enviar"):
            return jsonify(error="Inicia sesión para usar el chat."), 401
        flash("Inicia sesión para entrar al chat.", "info")
        return redirect(url_for("practice5", action="login"))
    if not session.get("chat_token"):
        session["chat_token"] = secrets.token_urlsafe(24)
    if request.path.endswith("/mensajes"):
        try:
            since = max(0, int(request.args.get("desde", 0)))
        except ValueError:
            return jsonify(error="Identificador inválido."), 400
        records = db.execute(
            "SELECT * FROM chat_mensajes WHERE id>? ORDER BY id ASC LIMIT 100", (since,)
        ).fetchall()
        messages = [chat_message(row, author["matricula"]) for row in records]
        latest = messages[-1]["id"] if messages else since
        return jsonify(mensajes=messages, ultimo=latest)
    if request.path.endswith("/enviar"):
        text = request.form.get("mensaje", "").strip()
        if not secrets.compare_digest(request.form.get("token", ""), session["chat_token"]):
            return jsonify(error="Token de seguridad inválido."), 400
        if not text or len(text) > 500:
            return jsonify(error="El mensaje debe tener entre 1 y 500 caracteres."), 400
        cursor = db.execute(
            "INSERT INTO chat_mensajes(autor_matricula,autor_nombre,mensaje) VALUES (?, ?, ?)",
            (author["matricula"], f"{author['nombre']} {author['apellido']}", text),
        )
        db.commit()
        row = db.execute("SELECT * FROM chat_mensajes WHERE id=?", (cursor.lastrowid,)).fetchone()
        result = chat_message(row, author["matricula"])
        result["es_mio"] = True
        return jsonify(mensaje=result, ultimo=result["id"])
    records = db.execute("SELECT * FROM chat_mensajes ORDER BY id DESC LIMIT 100").fetchall()
    messages = [chat_message(row, author["matricula"]) for row in reversed(records)]
    return render_template("chat.html", title="Chat de la tienda", messages=messages,
                           latest=messages[-1]["id"] if messages else 0,
                           chat_token=session["chat_token"])


@app.get("/p9/chat/mensajes")
def chat_messages():
    return shop_chat(get_db())


@app.post("/p9/chat/enviar")
def chat_send():
    return shop_chat(get_db())


@app.errorhandler(404)
def not_found(_error):
    return render_template("message.html", title="No encontrado",
                           message="No encontramos la página solicitada."), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 8000)), debug=False)
