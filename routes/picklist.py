from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from database import db
from models.orden import Orden, Picklist
from datetime import datetime

bp = Blueprint('picklist', __name__, url_prefix='/ordenes')

# --- 1. VISTA PREVIA (Antes de imprimir) ---
@bp.route('/picklist')
def vista_previa_picklist():
    # 1. VERIFICAR SI HAY IDs SELECCIONADOS EN LA URL
    ids_param = request.args.get('ids')
    
    if ids_param:
        lista_ids = ids_param.split(',')
        ordenes_pendientes = Orden.query.filter(Orden.id.in_(lista_ids)).all()
    else:
        # 2. SI NO HAY SELECCIÓN, TRAER TODO LO PENDIENTE (Lógica Original)
        ordenes_pendientes = Orden.query.filter(
    Orden.estado.in_(['PENDIENTE', 'APROBADO']),
    Orden.origen.in_(['ML', 'TN', 'MANUAL', 'REPOSICION'])
).all()
    
    ordenes_validas = [o for o in ordenes_pendientes if len(o.items) > 0]
    
    if not ordenes_validas:
        flash("⚠️ No hay órdenes pendientes para generar Picklist.", "warning")
        return redirect(url_for('ordenes.dashboard'))

    datos = consolidar_items(ordenes_validas)
    
    return render_template('picklist.html', 
                           items=datos['items'], 
                           ordenes_ids=datos['ids'],
                           total_items=datos['total'],
                           picklist=None)

# --- 2. CONFIRMAR Y CREAR LOTE EN BD (MODIFICADO PARA AUTO-PRINT) ---
@bp.route('/picklist/confirmar-batch', methods=['POST'])
def confirmar_batch():
    data = request.json
    ids_a_procesar = data.get('ids', [])
    
    if not ids_a_procesar:
        return jsonify({'success': False, 'error': 'No se recibieron IDs.'})

    try:
        # 1. Creamos el registro del Lote
        nuevo_picklist = Picklist(fecha_creacion=datetime.now())
        db.session.add(nuevo_picklist)
        db.session.flush()

        for id_orden in ids_a_procesar:
            orden = Orden.query.get(id_orden)
            if orden:
                orden.estado = 'EN_PREPARACION'
                orden.picklist_id = nuevo_picklist.id 
        
        db.session.commit()
        
        # --- CAMBIO CLAVE: Devolvemos la URL de impresión directa ---
        # Le agregamos ?auto_print=true para que el HTML sepa que debe imprimirse solo
        print_url = url_for('picklist.reimprimir_picklist', picklist_id=nuevo_picklist.id) + "?auto_print=true"
        
        return jsonify({
            'success': True, 
            'message': f"Lote #{nuevo_picklist.id} generado.",
            'print_url': print_url
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# --- 3. HISTORIAL DE LOTES ---
@bp.route('/picklist/historial')
def historial_picklist():
    lotes_db = Picklist.query.order_by(Picklist.id.desc()).limit(50).all()
    picklists_data = []
    
    for lote in lotes_db:
        total_ordenes = len(lote.ordenes)
        progreso = 0
        if total_ordenes > 0:
            terminadas = sum(1 for o in lote.ordenes if o.estado in ['LISTO_DESPACHO', 'DESPACHADO', 'COMPLETA'])
            progreso = int((terminadas / total_ordenes) * 100)
            
        picklists_data.append({
            'id': lote.id,
            'fecha': lote.fecha_creacion,
            'cant_ordenes': total_ordenes,
            'progreso': progreso
        })

    return render_template('picklist_historial.html', picklists=picklists_data)

# --- 4. VER / REIMPRIMIR LOTE ---
@bp.route('/picklist/ver/<int:picklist_id>')
def reimprimir_picklist(picklist_id):
    lote = Picklist.query.get_or_404(picklist_id)
    ordenes_del_lote = lote.ordenes
    
    if not ordenes_del_lote:
        flash("Este lote está vacío.", "error")
        return redirect(url_for('picklist.historial_picklist'))

    datos = consolidar_items(ordenes_del_lote)
    
    return render_template('picklist.html', 
                           items=datos['items'], 
                           ordenes_ids=datos['ids'],
                           total_items=datos['total'],
                           picklist=lote)

# --- AUXILIAR ---
def consolidar_items(lista_ordenes):
    items_consolidados = {}
    total_unidades = 0
    ids_ordenes = []

    for orden in lista_ordenes:
        ids_ordenes.append(orden.id)
        for item in orden.items:
            sku = getattr(item, 'sku', 'SIN_SKU')
            nombre = getattr(item, 'nombre', getattr(item, 'descripcion', 'Sin descripción'))
            cantidad = getattr(item, 'cantidad', getattr(item, 'quantity', 1))
            
            if sku not in items_consolidados:
                items_consolidados[sku] = {
                    'sku': sku, 
                    'descripcion': nombre, 
                    'cantidad': 0, 
                    'ubicacion': getattr(item, 'ubicacion', '---')
                }
            items_consolidados[sku]['cantidad'] += cantidad
            total_unidades += cantidad
    
    lista_items = list(items_consolidados.values())
    lista_items.sort(key=lambda x: x['sku'])
    
    return {'items': lista_items, 'ids': ids_ordenes, 'total': total_unidades}