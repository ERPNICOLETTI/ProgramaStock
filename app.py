from flask import Flask, redirect, send_from_directory, request, jsonify, render_template
from config import Config
from database import db
import os
import sqlite3

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

# Asegurar directorios de exportación
os.makedirs(app.config.get('DBF_EXPORT_PATH', 'exports'), exist_ok=True)
os.makedirs(app.config.get('DBF_IMPORT_PATH', 'imports'), exist_ok=True)

# --- IMPORTACIÓN DE MÓDULOS (BLUEPRINTS) ---
# Importamos TODOS los módulos del sistema, incluyendo el NUEVO 'manual'
from routes import (
    ordenes,        # Dashboard General
    picklist,       # Generación de Lotes
    despacho,       # Control de Salida
    manual,         # Carga Manual y TiendaNube (NUEVO)
    pickeo,         # Escáner Operativo
    transferencias, # Movimientos Internos
    ingresos,       # Stock Entrante
    egresos,        # Gastos
    meli_routes,    # Integración MercadoLibre
    admin,          # Panel Admin Global
    reposicion,      # <--- AGREGAR ESTO
    stock,
    presupuestos
)

# --- REGISTRO DE BLUEPRINTS ---
# Aquí conectamos cada módulo con la aplicación principal

# 1. Gestión de Pedidos y Ventas
app.register_blueprint(ordenes.bp)          # /ordenes/ (Dashboard)
app.register_blueprint(picklist.bp)         # /ordenes/picklist
app.register_blueprint(despacho.bp)         # /ordenes/admin/despacho
app.register_blueprint(manual.bp)           # /ordenes/manual y /ordenes/manual_tn

# 2. Operativa de Depósito
app.register_blueprint(pickeo.bp)           # /pickeo/
app.register_blueprint(transferencias.bp)   # /transferencias/
app.register_blueprint(reposicion.bp)
app.register_blueprint(stock.bp)
app.register_blueprint(presupuestos.bp)
# 3. Stock y Maestros
app.register_blueprint(ingresos.bp)
app.register_blueprint(egresos.bp)

# 4. Integraciones y Admin
app.register_blueprint(meli_routes.meli_bp, url_prefix='/meli')
app.register_blueprint(admin.bp)

# --- RUTAS GLOBALES ---

@app.route('/')
def index():
    # Redirige siempre al dashboard principal al entrar a la raíz
    return redirect('/ordenes/')

@app.route('/visor-remitos')
def visor_remitos():
    movimientos = []
    # Nos conectamos a la base de datos de Clipper/Movimientos
    db_path = r'Z:\VENTAS\MOVSTK\stock_movimientos.db'
    
    try:
        # Abrimos la conexión
        con = sqlite3.connect(db_path)
        # Queremos que los resultados se comporten como diccionarios (para llamarlos como mov.remito en el HTML)
        con.row_factory = sqlite3.Row 
        cur = con.cursor()
        
        # Le pedimos todos los registros ordenados desde el más reciente (ID más grande) al más viejo
        cur.execute("SELECT * FROM stock_movimientos_his ORDER BY id DESC")
        movimientos = cur.fetchall()
        
        con.close()
    except Exception as e:
        print(f"Error al leer la base de datos de remitos: {e}")
        # Si falla (ej: no se encuentra la red Z:), movimientos quedará vacío "[]"
        
    # Le pasamos la lista de movimientos al HTML que creamos antes
    return render_template('visor_remitos.html', movimientos=movimientos)

# Ruta para descargar PDFs y DBFs generados
@app.route('/descargar-archivo/<filename>')
def descargar_archivo(filename):
    return send_from_directory(app.config['DBF_EXPORT_PATH'], filename)

if __name__ == '__main__':
    with app.app_context():
        print(">>> PUERTO: 5000 (VERSION ESTABLE)")
        print("=" * 60 + "\n")

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        use_reloader=False
    )

