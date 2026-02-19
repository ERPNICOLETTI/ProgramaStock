import os
import shutil
from datetime import datetime

                         
from dbfread import DBF             # LEER DBF

from database import db
from config import Config
from models.orden import (
    Movimiento,
    ProductoMaestro,
    Orden,
    Cliente,
    Proveedor
)

# ==========================================================
# CONFIG
# ==========================================================

RUTA_VENTAS = r"C:\VENTAS\MOVSTK"
RUTA_MAESTRO = r"C:\VENTAS\MOVSTK\NOVEDADES.DBF"


# ==========================================================
# NUMERADOR GLOBAL DE ORDEN (SIN BLOQUEOS)
# ==========================================================

ORDEN_FILE = r"C:\VENTAS\MOVSTK\orden_actual.txt"

def obtener_siguiente_orden():
    raise RuntimeError(
        "Numerador de clipper_service deshabilitado. "
        "Usar el numerador del sincronizador."
    )



# ==========================================================
# UTILIDADES
# ==========================================================

def limpiar_basura(texto):
    if texto is None:
        return ""
    if isinstance(texto, bytes):
        try:
            return texto.decode("cp850").strip()
        except Exception:
            return str(texto).strip()
    s = str(texto).strip()
    if s.startswith("b'") and s.endswith("'"):
        return s[2:-1]
    return s


# ==========================================================
# RESOLUCIÓN DE CÓDIGOS (BLINDAJE ML)
# ==========================================================

def obtener_codigo_cliente(nombre_cliente):
    """
    REGLA ABSOLUTA:
    - Si es ML / MELI / MERCADOLIBRE → devuelve 'ML'
    - JAMÁS devuelve FULL para ML
    """
    if not nombre_cliente:
        return "9999"

    nombre = limpiar_basura(nombre_cliente).upper()

    if nombre in ("ML", "MELI", "MERCADOLIBRE"):
        return "ML"

    cliente = Cliente.query.filter_by(nombre=nombre).first()
    if cliente:
        return cliente.codigo

    cliente_aprox = Cliente.query.filter(
        Cliente.nombre.contains(nombre)
    ).first()
    if cliente_aprox:
        return cliente_aprox.codigo

    if nombre.isdigit():
        return nombre

    return nombre[:20]


def obtener_codigo_proveedor(nombre_prov):
    if not nombre_prov:
        return "0000"

    nombre = limpiar_basura(nombre_prov)

    prov = Proveedor.query.filter_by(nombre=nombre).first()
    if prov:
        return prov.codigo

    prov_aprox = Proveedor.query.filter(
        Proveedor.nombre.contains(nombre)
    ).first()
    if prov_aprox:
        return prov_aprox.codigo

    if nombre.isdigit():
        return nombre

    return nombre[:20]


def generar_id_unico(orden):
    if not orden:
        return "000000"
    return str(orden.id).zfill(8)


def replicar_en_ventas(ruta_original, nombre_archivo):
    try:
        os.makedirs(RUTA_VENTAS, exist_ok=True)
        shutil.copy(
            ruta_original,
            os.path.join(RUTA_VENTAS, nombre_archivo)
        )
    except Exception:
        pass


# ==========================================================
# EXPORTADORES DBF INDIVIDUALES
# ==========================================================

# ==========================================================
# EXPORTADORES DESHABILITADOS (MODO SINCRONIZADOR)
# ==========================================================

def exportar_movimiento_dbf(*args, **kwargs):
    raise RuntimeError(
        "exportar_movimiento_dbf() DESHABILITADO. "
        "Todos los movimientos deben pasar por sincronizador_blindado.py"
    )

def agregar_al_maestro(*args, **kwargs):
    raise RuntimeError(
        "agregar_al_maestro() DESHABILITADO. "
        "Todos los movimientos deben pasar por sincronizador_blindado.py"
    )



# ==========================================================
# IMPORTADORES DBF CON ESTADÍSTICAS DETALLADAS
# ==========================================================

def importar_catalogo_dbf():
    ruta = os.path.join(Config.DBF_IMPORT_PATH, "SETART.DBF")
    if not os.path.exists(ruta):
        return {"success": False, "error": "Falta SETART.DBF"}

    table = DBF(ruta, encoding="cp850")
    vivos = set()
    
    # Contadores
    c_nuevos = 0
    c_actualizados = 0
    c_iguales = 0
    c_eliminados = 0

    for r in table:
        sku = limpiar_basura(r.get("INVCOD"))
        desc = limpiar_basura(r.get("INVNOM"))
        
        # --- AGREGADO: LEER STOCK ---
        # Usamos 'or 0' por si el campo viene vacío o None del DBF
        invact = int(r.get("INVACT") or 0)  # Stock Salón
        invpen = int(r.get("INVPEN") or 0)  # Stock Depósito

        if not sku:
            continue

        vivos.add(sku)
        prod = ProductoMaestro.query.get(sku)
        
        if not prod:
            # NUEVO PRODUCTO (Incluimos stock inicial)
            prod = ProductoMaestro(
                sku=sku, 
                descripcion=desc, 
                INVACT=invact, 
                INVPEN=invpen
            )
            db.session.add(prod)
            c_nuevos += 1
        else:
            # EXISTENTE: CHEQUEAR CAMBIOS EN DESCRIPCIÓN O STOCK
            cambios = False
            
            if prod.descripcion != desc:
                prod.descripcion = desc
                cambios = True
            
            # Chequear si cambió el stock físico (INVACT)
            if prod.INVACT != invact:
                prod.INVACT = invact
                cambios = True
                
            # Chequear si cambió el stock depósito (INVPEN)
            if prod.INVPEN != invpen:
                prod.INVPEN = invpen
                cambios = True

            if cambios:
                c_actualizados += 1
            else:
                c_iguales += 1

    # Limpieza de obsoletos
    for p in ProductoMaestro.query.all():
        if p.sku not in vivos:
            db.session.delete(p)
            c_eliminados += 1

    db.session.commit()
    
    msg = (f"✅ Catálogo Procesado:\n"
           f"🆕 Nuevos: {c_nuevos}\n"
           f"🔄 Actualizados: {c_actualizados}\n"
           f"💤 Sin Cambios: {c_iguales}\n"
           f"🗑 Eliminados: {c_eliminados}")
           
    return {"success": True, "mensaje": msg}


def importar_clientes_dbf():
    ruta = os.path.join(Config.DBF_IMPORT_PATH, "SETCLI.DBF")
    if not os.path.exists(ruta):
        return {"success": False, "error": "Falta SETCLI.DBF"}

    table = DBF(ruta, encoding="cp850")
    vivos = set()
    
    c_nuevos = 0
    c_actualizados = 0
    c_iguales = 0
    c_eliminados = 0

    for r in table:
        codigo = limpiar_basura(r.get("CLICOD"))
        nombre = limpiar_basura(r.get("CLINOM"))
        if not codigo:
            continue

        vivos.add(codigo)
        cli = Cliente.query.get(codigo)
        
        if not cli:
            cli = Cliente(codigo=codigo, nombre=nombre)
            db.session.add(cli)
            c_nuevos += 1
        else:
            if cli.nombre != nombre:
                cli.nombre = nombre
                c_actualizados += 1
            else:
                c_iguales += 1

    for c in Cliente.query.all():
        if c.codigo not in vivos:
            db.session.delete(c)
            c_eliminados += 1

    db.session.commit()
    
    msg = (f"✅ Clientes Procesados:\n"
           f"🆕 Nuevos: {c_nuevos}\n"
           f"🔄 Actualizados: {c_actualizados}\n"
           f"💤 Sin Cambios: {c_iguales}\n"
           f"🗑 Eliminados: {c_eliminados}")
           
    return {"success": True, "mensaje": msg}


def importar_proveedores_dbf():
    ruta = os.path.join(Config.DBF_IMPORT_PATH, "SETPRO.DBF")
    if not os.path.exists(ruta):
        return {"success": False, "error": "Falta SETPRO.DBF"}

    table = DBF(ruta, encoding="cp850")
    vivos = set()
    
    c_nuevos = 0
    c_actualizados = 0
    c_iguales = 0
    c_eliminados = 0

    for r in table:
        codigo = limpiar_basura(r.get("PROCOD") or r.get("CODIGO"))
        nombre = limpiar_basura(r.get("PRONOM") or r.get("NOMBRE"))
        if not codigo:
            continue

        vivos.add(codigo)
        prov = Proveedor.query.get(codigo)
        
        if not prov:
            prov = Proveedor(codigo=codigo, nombre=nombre)
            db.session.add(prov)
            c_nuevos += 1
        else:
            if prov.nombre != nombre:
                prov.nombre = nombre
                c_actualizados += 1
            else:
                c_iguales += 1

    for p in Proveedor.query.all():
        if p.codigo not in vivos:
            db.session.delete(p)
            c_eliminados += 1

    db.session.commit()
    
    msg = (f"✅ Proveedores Procesados:\n"
           f"🆕 Nuevos: {c_nuevos}\n"
           f"🔄 Actualizados: {c_actualizados}\n"
           f"💤 Sin Cambios: {c_iguales}\n"
           f"🗑 Eliminados: {c_eliminados}")
           
    return {"success": True, "mensaje": msg}
