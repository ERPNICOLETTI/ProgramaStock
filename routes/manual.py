from flask import Blueprint, render_template, request, jsonify, current_app
from database import db
from models.orden import Orden, Item
from datetime import datetime
import os
import json
from werkzeug.utils import secure_filename

# Importamos el parser de texto que definimos en services
from services.pdf_service import procesar_factura_pdf

bp = Blueprint('manual', __name__, url_prefix='/ordenes')

# --- 1. VISTAS DE CARGA ---
@bp.route('/manual')
def vista_manual():
    # Carga Manual Clásica (Verde)
    return render_template('manual.html', tipo='MANUAL')

@bp.route('/manual_tn')
def vista_manual_tn():
    # Carga TiendaNube (Azul)
    return render_template('manual.html', tipo='TN')

# --- 2. ANÁLISIS DE ARCHIVO (TXT/PRN) ---
@bp.route('/subir-factura-pdf', methods=['POST'])
def subir_factura_pdf():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No se recibió archivo'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'Nombre de archivo vacío'})

        # Usamos TU parser de Clipper/Texto
        datos_extraidos = procesar_factura_pdf(file)
        
        # Si el parser devolvió un error (ej: era un PDF real), lo notificamos
        if "error" in datos_extraidos:
            return jsonify({'success': False, 'error': datos_extraidos['error']})
        
        return jsonify({'success': True, 'data': datos_extraidos})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# --- 3. CREACIÓN DE LA ORDEN (CON ETIQUETA OPCIONAL) ---
@bp.route('/crear-completa', methods=['POST'])
def crear_orden_completa():
    try:
        # Los datos complejos vienen como string JSON dentro del FormData
        json_str = request.form.get('json_data')
        if not json_str:
            return jsonify({'success': False, 'error': 'Faltan datos JSON'})
            
        data = json.loads(json_str)
        
        # Archivo de etiqueta (Solo presente si es TN y el usuario lo subió)
        file_etiqueta = request.files.get('etiqueta_file')

        # --- Datos Generales ---
        origen = data.get('origen', 'MANUAL')
        nro_factura = data.get('factura', '').strip()
        
        # Si no hay factura, generamos un ID temporal basado en la hora
        if not nro_factura:
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            nro_factura = f"S/N-{timestamp}"

        # Prefijo para diferenciar en el sistema
        prefix = "TN" if origen == 'TN' else "MAN"
        numero_orden = f"{prefix}-{nro_factura}"

        # Evitar duplicados exactos agregando sufijo
        if Orden.query.filter_by(numero_orden=numero_orden).first():
             numero_orden = f"{numero_orden}-DUP"

        # --- Crear Objeto Orden ---
        nueva_orden = Orden(
            numero_orden=numero_orden,
            nro_factura=nro_factura,
            cliente_nombre=data.get('cliente', 'Consumidor Final'),
            origen=origen,
            estado='PENDIENTE', # Va al Dashboard para ser preparada
            fecha_creacion=datetime.now(),
            observaciones=data.get('observaciones', '')
        )

        # --- Manejo de Etiqueta (Solo TN) ---
        if origen == 'TN' and file_etiqueta:
            filename = secure_filename(f"ETIQ_{numero_orden}_{file_etiqueta.filename}")
            
            # Carpeta de destino estática
            upload_folder = os.path.join(current_app.root_path, 'static', 'etiquetas')
            os.makedirs(upload_folder, exist_ok=True)
            
            file_path = os.path.join(upload_folder, filename)
            file_etiqueta.save(file_path)
            
            # Guardamos la referencia en la BD
            nueva_orden.etiqueta_url = f"/static/etiquetas/{filename}"
            nueva_orden.tracking_number = "TN-GENERADO"

        db.session.add(nueva_orden)
        db.session.flush() # Obtenemos el ID de la orden

        # --- Guardar Items ---
        items_cargados = data.get('items', [])
        
        # Fallback si la lista está vacía
        if not items_cargados:
             items_cargados.append({'sku': 'REVISAR', 'descripcion': 'Verificar impresión física', 'cantidad': 1})

        for item_data in items_cargados:
            try:
                # Aseguramos conversión numérica
                cant_val = float(item_data.get('cantidad', 1))
            except:
                cant_val = 1.0

            nuevo_item = Item(
                orden_id=nueva_orden.id,
                sku=str(item_data.get('sku', 'GENERICO')).strip().upper(),
                descripcion=item_data.get('descripcion', 'Sin descripción'),
                cantidad_pedida=cant_val, # Usamos float o int según tu modelo
                cantidad_pickeada=0
            )
            db.session.add(nuevo_item)

        db.session.commit()
        return jsonify({'success': True, 'orden_id': numero_orden})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# --- 4. RUTA POSTERIOR (Placeholder) ---
@bp.route('/subir-etiqueta-tn', methods=['POST'])
def subir_etiqueta_tn():
    return jsonify({'success': False, 'error': 'No implementado'})