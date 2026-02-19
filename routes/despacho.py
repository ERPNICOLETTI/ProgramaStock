from flask import Blueprint, render_template, jsonify
from database import db
from models.orden import Orden
from models.orden import Item
from datetime import datetime

# Blueprint para administración y despacho
bp = Blueprint('despacho', __name__, url_prefix='/ordenes')

@bp.route('/admin/despacho')
def admin_despacho():
    ordenes_para_despacho = Orden.query.filter(
        Orden.estado.in_(['PENDIENTE_DOCS', 'PENDIENTE_ETIQUETA', 'ESPERANDO_ADMIN']),
        Orden.origen != 'TRANSFERENCIA'
    ).order_by(Orden.fecha_creacion.asc()).all()

    return render_template(
        'admin_despacho.html',
        ordenes=ordenes_para_despacho
    )



# Placeholders de importación (para que no den 404 si el frontend los llama)
@bp.route('/importar-catalogo', methods=['POST'])
def importar_catalogo(): return jsonify({'success': False, 'error': 'Deshabilitado'})
@bp.route('/importar-clientes', methods=['POST'])
def importar_clientes(): return jsonify({'success': False, 'error': 'Deshabilitado'})
@bp.route('/importar-proveedores', methods=['POST'])
def importar_proveedores(): return jsonify({'success': False, 'error': 'Deshabilitado'})
from flask import request, current_app
from werkzeug.utils import secure_filename
import os

@bp.route('/admin/subir-etiqueta-manual', methods=['POST'])
def subir_etiqueta_manual():
    orden_id = request.form.get('orden_id')
    file = request.files.get('etiqueta')

    if not orden_id or not file:
        return jsonify(success=False, error='Datos incompletos')

    orden = Orden.query.get(orden_id)
    if not orden:
        return jsonify(success=False, error='Orden no encontrada')

    if orden.origen != 'MANUAL' or orden.estado != 'ESPERANDO_ADMIN':
        return jsonify(success=False, error='Estado inválido para este flujo')

    if not file.filename.lower().endswith('.pdf'):
        return jsonify(success=False, error='Solo se permite PDF')

    filename = secure_filename(f"manual_{orden.id}.pdf")
    folder = os.path.join(current_app.root_path, 'static', 'etiquetas', 'manual')
    os.makedirs(folder, exist_ok=True)

    file.save(os.path.join(folder, filename))

    orden.etiqueta_url = f"/static/etiquetas/manual/{filename}"
    orden.manual_etapa = 'CIERRE'
    orden.estado = 'EN_PREPARACION'

    db.session.commit()

    return jsonify(success=True)

@bp.route('/admin/importar-full', methods=['POST'])
def importar_envio_full():
    data = request.get_json()
    numero_full = (data or {}).get('numero')

    if not numero_full:
        return jsonify(success=False, error='Número FULL requerido')

    # --- CREAR ORDEN BASE ---
    orden = Orden(
        numero_orden=numero_full,
        origen='FULL',
        estado='EN_PREPARACION',
        cliente_nombre='FULL',
        fecha_creacion=datetime.now()
    )
    db.session.add(orden)
    db.session.flush()

    # --- ITEMS SIMULADOS (PARA TEST) ---
    # Luego esto vendrá de la API FULL
    items_full = [
        {'sku': 'SKU-FULL-1', 'cantidad': 2},
        {'sku': 'SKU-FULL-2', 'cantidad': 1},
    ]

    for it in items_full:
        db.session.add(Item(
            orden_id=orden.id,
            sku=it['sku'],
            descripcion=it['sku'],
            cantidad_pedida=it['cantidad']
        ))

    db.session.commit()

    return jsonify(success=True, orden_id=orden.id)

# --- AGREGAR ESTO AL FINAL DE despacho.py ---

@bp.route('/admin/eliminar-orden', methods=['POST'])
def eliminar_orden_admin():
    orden_id = request.form.get('orden_id')
    
    if not orden_id:
        return jsonify(success=False, error='Falta ID de orden')

    orden = Orden.query.get(orden_id)
    if not orden:
        return jsonify(success=False, error='Orden no encontrada')

    try:
        # 1. Eliminar los items asociados primero (limpieza)
        Item.query.filter_by(orden_id=orden.id).delete()
        
        # 2. Eliminar la orden
        db.session.delete(orden)
        db.session.commit()
        
        return jsonify(success=True)
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e))