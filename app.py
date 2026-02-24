from flask import Flask, redirect, send_from_directory, request, jsonify, render_template
from config import Config
from database import db
import os
import sqlite3
import shutil
import time
import dbf
from datetime import datetime

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
    presupuestos,
    cambios
)

# --- REGISTRO DE BLUEPRINTS ---
# Aquí conectamos cada módulo con la aplicación principal

# 1. Gestión de Pedidos y Ventas
app.register_blueprint(ordenes.bp)          # /ordenes/ (Dashboard)
app.register_blueprint(picklist.bp)         # /ordenes/picklist
app.register_blueprint(despacho.bp)         # /ordenes/admin/despacho
app.register_blueprint(manual.bp)           # /ordenes/manual y /ordenes/manual_tn
app.register_blueprint(cambios.bp)          # /cambios/ (Gestión de Devoluciones y Cambios)

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

# --- FUNCIONES DE SOPORTE ---
_SETART_CACHE = None

def _get_nombres_dict():
    """Trae nombres de DBF similar a ORCHESTRATOR.PY, usando copia viva como consulta_live.py"""
    global _SETART_CACHE
    if _SETART_CACHE is not None:
        return _SETART_CACHE
        
    _SETART_CACHE = {}
    ruta_original = r"\\servidor\sistema\VENTAS\SETART.DBF"
    ruta_temp = rf"C:\Users\Usuario\Desktop\ERP-PINO\temp_visor_{int(time.time() * 1000)}.dbf"
    
    try:
        # 1. Copia segura como en consulta_live.py
        shutil.copy2(ruta_original, ruta_temp)
        
        # 2. Lectura como en ORCHESTRATOR.py
        t = dbf.Table(ruta_temp, codepage='cp1252')
        t.open(mode=dbf.READ_ONLY)
        fields = [f.upper() for f in t.field_names]
        
        campo_nombre = None
        for c in ["INVNOM", "NOMBRE", "DESCRIP", "DESCRI", "DESCRIPCIO", "ARTNOM"]:
            if c in fields:
                campo_nombre = c
                break
                
        if campo_nombre:
            for r in t:
                cod = str(r.INVCOD).strip().upper()
                nom = str(getattr(r, campo_nombre)).strip()
                if cod:
                    _SETART_CACHE[cod] = nom
        t.close()
    except Exception as e:
        print(f"Error cargando Nombres de SETART: {e}")
    finally:
        if os.path.exists(ruta_temp):
            try: os.remove(ruta_temp)
            except: pass
            
    return _SETART_CACHE

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
    
    nombres_dict = _get_nombres_dict()
    
    try:
        # Abrimos la conexión
        con = sqlite3.connect(db_path)
        con.row_factory = sqlite3.Row 
        cur = con.cursor()
        
        # Le pedimos todos los registros ordenados desde el más reciente (ID más grande) al más viejo
        cur.execute("SELECT * FROM stock_movimientos_his ORDER BY id DESC LIMIT 2000")
        rows = cur.fetchall()
        
        for row in rows:
            mov = dict(row) # Convertimos a dict mutable
            codigo = str(mov.get('invcod', '')).strip().upper()
            mov['nombre'] = nombres_dict.get(codigo, "")
            
            # Acortar fecha (ej: "2026-02-23 17:16:03" a "23/02 17:16")
            fecha_str = mov.get('fecha', '')
            if fecha_str:
                try:
                    if ' ' in fecha_str:
                        dt = datetime.strptime(fecha_str, '%Y-%m-%d %H:%M:%S')
                        mov['fecha_corta'] = dt.strftime('%d/%m/%y %H:%M')
                    else:
                        dt = datetime.strptime(fecha_str, '%Y-%m-%d')
                        mov['fecha_corta'] = dt.strftime('%d/%m/%y')
                except Exception:
                    mov['fecha_corta'] = fecha_str
            else:
                mov['fecha_corta'] = ""

            movimientos.append(mov)
            
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

