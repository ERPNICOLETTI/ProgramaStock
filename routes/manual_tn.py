from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from database import db
from models.orden import Orden, Item
from datetime import datetime
import os

bp = Blueprint('manual', __name__, url_prefix='/ordenes')

# --- 1. VISTA PRINCIPAL (Selector o Redirección) ---
@bp.route('/manual')
def vista_manual():
    # Esta es la vista para carga MANUAL pura (Factura + Datos a mano)
    return render_template('manual.html', tipo='MANUAL')

@bp.route('/manual_tn')
def vista_manual_tn():
    # Esta es la vista para TIENDANUBE (Solo Factura Inicial)
    # Reutilizamos el mismo template pero le pasamos tipo='TN' para que cambie el color a azul y los textos.
    return render_template('manual.html', tipo='TN')

# --- 2. ANÁLISIS DE PDF (Simulado) ---
@bp.route('/subir-factura-pdf', methods=['POST'])
def subir_factura_pdf():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No se recibió archivo'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'Nombre de archivo vacío'})

        # Lógica simulada de lectura de PDF
        nombre_clean = file.filename.replace('.pdf', '')
        
        # En un caso real, aquí usarías pdfplumber para leer el texto del PDF
        datos_extraidos = {
            'cliente': f"Cliente {nombre_clean}", # Simulado
            'factura': f"FC-{nombre_clean}",      # Simulado
            'items': [
                {'sku': 'SKU-EJEMPLO-1', 'descripcion': 'Producto Ejemplo TN', 'cantidad': 1},
            ]
        }
        
        return jsonify({'success': True, 'data': datos_extraidos})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# --- 3. CREACIÓN DE ORDEN COMPLETA ---
@bp.route('/crear-completa', methods=['POST'])
def crear_orden_completa():
    try:
        data = request.json
        
        # Validaciones básicas
        if not data.get('cliente') or not data.get('items'):
            return jsonify({'success': False, 'error': 'Faltan datos obligatorios'})

        # Definir Origen
        origen = data.get('origen', 'MANUAL') # Puede ser 'MANUAL' o 'TN'
        
        nro_factura = data.get('factura', '').strip()
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:18]
        
        # Generación de ID según origen
        if origen == 'TN':
            numero_orden = f"TN-{nro_factura}" if nro_factura else f"TN-{timestamp}"
        else:
            numero_orden = f"MAN-{nro_factura}" if nro_factura else f"MAN-{timestamp}"

        # Evitar duplicados
        if Orden.query.filter_by(numero_orden=numero_orden).first():
             numero_orden = f"{numero_orden}-DUP"

        # Crear la Orden
        # NOTA: Para TN, no cargamos etiqueta ni medidas aún. Eso se hace en el Pickeo.
        nueva_orden = Orden(
            numero_orden=numero_orden,
            nro_factura=nro_factura,
            cliente_nombre=data.get('cliente'),
            origen=origen,
            estado='PENDIENTE', # Pasa directo a pendiente para que el depósito la tome
            fecha_creacion=datetime.now(),
            observaciones=data.get('observaciones', '')
        )
        
        db.session.add(nueva_orden)
        db.session.flush()

        # Crear Items
        for item_data in data['items']:
            cant = int(item_data.get('cantidad', 1))
            nuevo_item = Item(
                orden_id=nueva_orden.id,
                sku=str(item_data.get('sku', 'GENERICO')).strip().upper(),
                descripcion=item_data.get('descripcion', 'Sin descripción'),
                cantidad_pedida=cant,
                cantidad_pickeada=0
            )
            db.session.add(nuevo_item)

        db.session.commit()
        
        return jsonify({'success': True, 'orden_id': numero_orden})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# --- 4. CARGA DE ETIQUETA (Solo para TN - Post Pickeo) ---
# Esta ruta se usará más adelante desde el panel de Admin o Pickeo para subir la etiqueta
@bp.route('/subir-etiqueta-tn', methods=['POST'])
def subir_etiqueta_tn():
    try:
        orden_id = request.form.get('orden_id')
        file = request.files.get('etiqueta')
        
        if not orden_id or not file:
             return jsonify({'success': False, 'error': 'Faltan datos'})

        orden = Orden.query.get(orden_id)
        if not orden:
            return jsonify({'success': False, 'error': 'Orden no encontrada'})

        # Guardar archivo (Simulado)
        # nombre_archivo = secure_filename(file.filename)
        # file.save(os.path.join(app.config['UPLOAD_FOLDER'], nombre_archivo))
        
        # orden.etiqueta_url = nombre_archivo
        orden.tracking_number = "TN-TRACK-12345" # Simulado
        orden.estado = 'LISTO_DESPACHO' # Si ya tiene etiqueta y está pickeada, está lista
        
        db.session.commit()
        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})