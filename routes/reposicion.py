from flask import Blueprint, render_template, request, jsonify
from database import db
from models.orden import Orden, Item, ProductoMaestro, ReglaReposicion
from datetime import datetime
from sqlalchemy import or_, func
import os
import shutil
import dbf
import time

# ==========================================
# CONFIG DBF LIVE (Stock en vivo)
# ==========================================
RUTA_ORIGINAL = r"\\servidor\sistema\VENTAS\SETART.DBF"
RUTA_TEMP_BASE = r"C:\Users\Usuario\Desktop\ERP-PINO\temp_repo_live_"

def _cargar_stock_live_dict():
    """
    Copia SETART.DBF a un temp local y arma un dict:
    { SKU: (INVACT_salon, INVPEN_depo) }
    """
    timestamp = int(time.time() * 1000)
    ruta_temp = f"{RUTA_TEMP_BASE}{timestamp}.dbf"

    copiado_ok = False
    for _ in range(3):
        try:
            shutil.copy2(RUTA_ORIGINAL, ruta_temp)
            copiado_ok = True
            break
        except PermissionError:
            time.sleep(0.2)
    if not copiado_ok:
        raise Exception("Servidor ocupado o inaccesible (no se pudo copiar SETART.DBF).")

    stock = {}
    try:
        table = dbf.Table(ruta_temp, codepage="cp850")
        table.open(mode=dbf.READ_ONLY)

        for record in table:
            sku = str(record.invcod).strip().upper()
            invact = record.invact or 0
            invpen = record.invpen or 0
            stock[sku] = (invact, invpen)

        table.close()
        return stock

    finally:
        if os.path.exists(ruta_temp):
            try:
                os.remove(ruta_temp)
            except:
                pass


bp = Blueprint('reposicion', __name__, url_prefix='/reposicion')



# ==========================================
# 1. PANTALLA PRINCIPAL (REPO INTERNA)
# ==========================================
@bp.route('/')
def index():
    # Filtro de umbral dinámico (Por defecto 1)
    umbral_param = request.args.get('umbral', 1, type=int)

    # LÓGICA MAESTRA (REPO INTERNA):
    # Stock Salón <= Regla Mínima (o Umbral)
    # NO está oculto de REPOSICIÓN
    
    # 1) Stock en vivo desde DBF (snapshot)
    stock_live = _cargar_stock_live_dict()

    # 2) Traemos catálogo + reglas (pero SIN filtrar por stock en SQL)
    query = db.session.query(ProductoMaestro, ReglaReposicion).outerjoin(
        ReglaReposicion, ProductoMaestro.sku == ReglaReposicion.sku
    ).filter(
        ProductoMaestro.oculto_reposicion == False
    ).order_by(ProductoMaestro.sku.asc())

    resultados = query.all()


    sugeridos_procesados = []
    
    for prod, regla in resultados:
        sku_key = (prod.sku or "").strip().upper()
        invact_live, invpen_live = stock_live.get(sku_key, (0, 0))

        cant_sugerida = regla.cantidad_a_reponer if regla else 1
        stock_min = regla.stock_minimo if regla else umbral_param
    # Solo sugerimos si HAY depósito y el salón está bajo mínimo
        if invpen_live <= 0:
            continue
        if invact_live >= stock_min:
            continue


        
        sugeridos_procesados.append({
            'sku': prod.sku,
            'descripcion': prod.descripcion,
            'INVACT': invact_live,
            'INVPEN': invpen_live,

            'cantidad_sugerida': cant_sugerida,
            'stock_minimo': stock_min,
            'tiene_regla': True if regla else False
        })

    # Ocultos de REPO INTERNA
    productos_ocultos = ProductoMaestro.query.filter(
        ProductoMaestro.oculto_reposicion == True
    ).order_by(ProductoMaestro.sku.asc()).all()

    return render_template(
        'reposicion.html',
        sugeridos=sugeridos_procesados,
        ocultos=productos_ocultos,
        umbral_actual=umbral_param
    )

# ==========================================
# 2. PANTALLA NUEVA: PEDIDO A BS AS
# ==========================================
@bp.route('/pedido_bsas')
def view_pedido_bsas():
    # Busca productos sin stock en NINGÚN lado (0 Salón y 0 Depósito)
    # y que NO estén ocultos de la lista de BsAs (oculto_bsas)
    
    sugeridos = ProductoMaestro.query.filter(
        ProductoMaestro.INVACT <= 0,
        ProductoMaestro.INVPEN <= 0,
        ProductoMaestro.oculto_bsas == False
    ).order_by(ProductoMaestro.sku.asc()).all()

    ocultos = ProductoMaestro.query.filter(
        ProductoMaestro.INVACT <= 0,
        ProductoMaestro.INVPEN <= 0,
        ProductoMaestro.oculto_bsas == True
    ).order_by(ProductoMaestro.sku.asc()).all()

    return render_template('reposicion_bsas.html', sugeridos=sugeridos, ocultos=ocultos)

# ==========================================
# 3. ACCIONES (OCULTAR/MOSTRAR/GENERAR)
# ==========================================

# --- REPO INTERNA ---
@bp.route('/ocultar/<path:sku>', methods=['POST'])
def ocultar_producto(sku):
    prod = ProductoMaestro.query.get_or_404(sku)
    prod.oculto_reposicion = True
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/mostrar/<path:sku>', methods=['POST'])
def mostrar_producto(sku):
    prod = ProductoMaestro.query.get_or_404(sku)
    prod.oculto_reposicion = False
    db.session.commit()
    return jsonify({'success': True})

# --- REPO BS AS ---
@bp.route('/ocultar_bsas/<path:sku>', methods=['POST'])
def ocultar_bsas(sku):
    prod = ProductoMaestro.query.get_or_404(sku)
    prod.oculto_bsas = True
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/mostrar_bsas/<path:sku>', methods=['POST'])
def mostrar_bsas(sku):
    prod = ProductoMaestro.query.get_or_404(sku)
    prod.oculto_bsas = False
    db.session.commit()
    return jsonify({'success': True})

# --- CONFIGURACIÓN ---
@bp.route('/configuracion')
def vista_configuracion():
    return render_template('reposicion_config.html')

@bp.route('/guardar_regla', methods=['POST'])
def guardar_regla():
    data = request.json
    sku = data.get('sku')
    cantidad = int(data.get('cantidad', 1))
    minimo = int(data.get('minimo', 0))

    try:
        regla = ReglaReposicion.query.filter_by(sku=sku).first()
        if regla:
            regla.cantidad_a_reponer = cantidad
            regla.stock_minimo = minimo
        else:
            nueva_regla = ReglaReposicion(
                sku=sku, 
                cantidad_a_reponer=cantidad,
                stock_minimo=minimo
            )
            db.session.add(nueva_regla)

        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'mensaje': str(e)})

@bp.route('/eliminar_regla/<path:sku>', methods=['POST'])
def eliminar_regla(sku):
    regla = ReglaReposicion.query.filter_by(sku=sku).first()
    if regla:
        db.session.delete(regla)
        db.session.commit()
    return jsonify({'success': True})

@bp.route('/buscar_producto_config')
def buscar_producto_config():
    q = request.args.get('q', '')
    if len(q) < 3: return jsonify([])
    
    productos = db.session.query(ProductoMaestro, ReglaReposicion).outerjoin(
        ReglaReposicion
    ).filter(
        or_(
            ProductoMaestro.sku.ilike(f'%{q}%'),
            ProductoMaestro.descripcion.ilike(f'%{q}%')
        )
    ).limit(20).all()
    
    resultado = []
    for prod, regla in productos:
        resultado.append({
            'sku': prod.sku,
            'descripcion': prod.descripcion,
            'stock_minimo': regla.stock_minimo if regla else 0,
            'cantidad_a_reponer': regla.cantidad_a_reponer if regla else 1,
            'tiene_regla': True if regla else False
        })
        
    return jsonify(resultado)

# --- GENERADOR DE ORDEN (SOLO INTERNA) ---
@bp.route('/generar_orden', methods=['POST'])
def generar_orden():
    try:
        data = request.json
        items_seleccionados = data.get('items', [])
        
        if not items_seleccionados: return jsonify({'success': False, 'mensaje': 'Sin items.'})
        
        timestamp = datetime.now().strftime('%Y%m%d-%H%M')
        numero_ref = f"REP-{timestamp}"

        nueva_orden = Orden(
            numero_orden=numero_ref,
            origen='REPOSICION',
            destino='SALON',
            estado='PENDIENTE'
        )
        db.session.add(nueva_orden)
        db.session.flush()

        count = 0
        for item_data in items_seleccionados:
            sku = item_data.get('sku')
            cant = int(item_data.get('cantidad', 1))
            
            prod = ProductoMaestro.query.get(sku)
            desc = prod.descripcion if prod else "Producto"
            
            item = Item(
                orden_id=nueva_orden.id,
                sku=sku,
                descripcion=desc,
                cantidad_pedida=cant,
                cantidad_pickeada=0
            )
            db.session.add(item)
            count += 1

        db.session.commit()
        return jsonify({'success': True, 'mensaje': f"Orden {numero_ref} generada."})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'mensaje': str(e)})