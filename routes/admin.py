import pandas as pd
from datetime import datetime
import os
# Asegurate de tener los modelos importados:
from models.orden import Orden, Item # Y los demás que ya tenías
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session, flash, current_app
from database import db
from models.orden import Orden, Item, ProductoCodigo, ProductoMaestro
from services.util_service import is_admin_logged_in # Importamos la utilidad de sesión
from werkzeug.utils import secure_filename
import os
from PyPDF2 import PdfMerger
# Creamos el Blueprint con prefijo '/admin'
bp = Blueprint('admin', __name__, url_prefix='/admin') 

# --- NUEVA RUTA: BUSCAR VINCULACIONES ---
@bp.route('/consultar-asociaciones', methods=['POST'])
def consultar_asociaciones():
    """Busca vinculaciones por Código de Barra, SKU o EAN"""
    query = request.form.get('query', '').strip().upper()
    
    if not query:
        return jsonify(success=False, error="El campo está vacío")
    
    resultados = []
    
    try:
        # 1. Intentamos ver si lo que escribieron es un SKU directo
        maestro_por_sku = ProductoMaestro.query.filter_by(sku=query).first()
        sku_objetivo = maestro_por_sku.sku if maestro_por_sku else None
        
        # 2. Si no es SKU, vemos si es un EAN (código original del producto)
        if not sku_objetivo:
            maestro_por_ean = ProductoMaestro.query.filter_by(ean=query).first()
            if maestro_por_ean:
                sku_objetivo = maestro_por_ean.sku

        # 3. Buscamos las asociaciones "aprendidas"
        if sku_objetivo:
            # Si encontramos el SKU, mostramos TODOS los códigos que el sistema aprendió para ese SKU
            asociaciones = ProductoCodigo.query.filter_by(sku=sku_objetivo).all()
            for asc in asociaciones:
                resultados.append({
                    'codigo_barra': asc.codigo_barra,
                    'sku': asc.sku,
                    'tipo': 'Aprendido'
                })
        else:
            # Si no encontramos SKU, quizás escanearon directamente un código "malo" aprendido
            asociacion_directa = ProductoCodigo.query.filter_by(codigo_barra=query).first()
            if asociacion_directa:
                resultados.append({
                    'codigo_barra': asociacion_directa.codigo_barra,
                    'sku': asociacion_directa.sku,
                    'tipo': 'Aprendido'
                })

        return jsonify(success=True, resultados=resultados)

    except Exception as e:
        return jsonify(success=False, error=str(e))

# --- RUTAS DE ADMINISTRACIÓN (LOGIN/LOGOUT) ---

# MODIFICADO: Agregamos methods=['GET', 'POST'] para arreglar el error 405
@bp.route('/', methods=['GET', 'POST'])
def admin_login():
    """Ruta para el formulario de login de administrador."""
    
    # 1. Si ya está logueado, redirigir directo al panel
    if is_admin_logged_in():
        return redirect('/ordenes/admin/despacho')
 

    # 2. Si recibimos datos del formulario (POST)
    if request.method == 'POST':
        password = request.form.get('password')
        ADMIN_PASSWORD = current_app.config.get('ADMIN_PASSWORD') 
        
        if password == ADMIN_PASSWORD: 
            session['admin_logged_in'] = True
            flash('Inicio de sesión exitoso.', 'success')
            return redirect('/ordenes/admin/despacho')
 
        else:
            flash('Contraseña incorrecta.', 'error')
            # No redirigimos, dejamos que se renderice el template de nuevo con el mensaje de error

    # 3. Mostrar el formulario (GET o POST fallido)
    return render_template('admin_login.html') 

# Mantenemos esta ruta por compatibilidad si el HTML apunta explícitamente a ella
@bp.route('/login_submit', methods=['POST'])
def admin_login_submit():
    password = request.form.get('password')
    ADMIN_PASSWORD = current_app.config.get('ADMIN_PASSWORD') 
    
    if password == ADMIN_PASSWORD: 
        session['admin_logged_in'] = True
        flash('Inicio de sesión exitoso.', 'success')
        return redirect('/ordenes/admin/despacho')
 
    else:
        flash('Contraseña incorrecta.', 'error')
        return redirect(url_for('admin.admin_login'))

@bp.route('/logout')
def admin_logout():
    """Cierra la sesión del administrador."""
    session.pop('admin_logged_in', None)
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for('admin.admin_login'))

# --- RUTAS DE CONTROL ADMINISTRATIVO ---

@bp.route('/control')
def admin_control():
    flash('Ruta admin antigua. Redirigiendo...', 'info')
    return redirect('/ordenes/admin/despacho')
 
    
    # Carga órdenes que esperan acción del admin
    ordenes = Orden.query.filter(Orden.estado.in_(['PENDIENTE_DOCS', 'PENDIENTE_ETIQUETA'])).all()
    return render_template('admin_control.html', ordenes=ordenes) 

@bp.route('/despacho')
def admin_despacho():
    """Ruta para el panel de control de documentos y despacho."""
    if not is_admin_logged_in():
        flash('Acceso denegado. Se requiere iniciar sesión como administrador.', 'error')
        return redirect(url_for('admin.admin_login')) 

    # Carga las órdenes que requieren documentos
    ordenes = Orden.query.filter(Orden.estado.in_(['PENDIENTE_DOCS', 'PENDIENTE_ETIQUETA'])).all()
    return render_template('admin_despacho.html', ordenes=ordenes)

@bp.route('/subir-docs', methods=['POST'])
def admin_subir_docs():
    """
    Recibe los archivos cargados por el administrador.
    """
    if not is_admin_logged_in():
        return jsonify(success=False, message="Acceso denegado."), 403

    try:
        orden_id = request.form.get('orden_id')
        etiqueta_pdf = request.files.get('etiqueta_pdf')
        factura_pdf = request.files.get('factura_pdf')
        
        # Lógica de guardado...
        
        return jsonify(success=True, message=f"Documentos para Orden {orden_id} subidos correctamente. Orden liberada.")

    except Exception as e:
        current_app.logger.error(f"Error al subir documentos: {e}")
        return jsonify(success=False, message=f"Error interno: {str(e)}"), 500

@bp.route('/api/check-pendientes-admin')
def check_pendientes_admin():
    """Endpoint API para contar tareas pendientes del admin."""
    count = Orden.query.filter(Orden.estado.in_(['PENDIENTE_DOCS', 'PENDIENTE_ETIQUETA'])).count()
    return jsonify({'pendientes': count})

# ... (El resto del archivo arriba queda igual) ...

@bp.route('/desvincular-sku', methods=['POST'])
def desvincular_sku():
    """Elimina un ítem específico de una orden (Corrección manual)."""
    
    # --- BLOQUEO ELIMINADO: AHORA APRUEBA DIRECTO ---
    # if not is_admin_logged_in():
    #    return jsonify(success=False, error="No autorizado"), 403
        
    orden_id = request.form.get('orden_id')
    sku = request.form.get('sku')

    if not orden_id or not sku:
        return jsonify(success=False, error="Datos incompletos")

    sku = sku.strip().upper()
    
    try:
        # Buscamos el item por orden y SKU
        item = Item.query.filter_by(orden_id=orden_id, sku=sku).first()
        if item:
            db.session.delete(item)
            db.session.commit()
            return jsonify(success=True, message=f"SKU {sku} eliminado de la orden.")
        else:
            return jsonify(success=False, error="Item no encontrado")
            
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e))
    
@bp.route('/borrar-asociacion-codigo', methods=['POST'])
def borrar_asociacion_codigo():
    """Borra la memoria de un código de barras mal aprendido."""
    
    # --- BLOQUEO ELIMINADO: AHORA APRUEBA DIRECTO ---
    # if not is_admin_logged_in():
    #    return jsonify(success=False, error="No autorizado"), 403

    codigo_barra = request.form.get('codigo_barra')

    if not codigo_barra:
        return jsonify(success=False, error="Código vacío")

    codigo_barra = codigo_barra.strip().upper()

    try:
        asociacion = ProductoCodigo.query.filter_by(
            codigo_barra=codigo_barra
        ).first()

        if not asociacion:
            return jsonify(
                success=False,
                error=f"El código {codigo_barra} no está en la memoria del sistema."
            )

        sku_anterior = asociacion.sku

        db.session.delete(asociacion)
        db.session.commit()

        return jsonify(
            success=True,
            message=f"Vínculo borrado: {codigo_barra} ya no es {sku_anterior}."
        )

    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e))
    
@bp.route('/subir-etiqueta-manual', methods=['POST'])
def subir_etiqueta_manual():
    """Recibe uno o varios PDFs, los une y guarda como etiqueta de la orden."""
    try:
        orden_id = request.form.get('orden_id')
        # Usamos getlist para recibir múltiples archivos
        lista_archivos = request.files.getlist('etiquetas') 

        if not orden_id or not lista_archivos:
            return jsonify(success=False, error="Faltan datos o archivos")

        orden = Orden.query.get(orden_id)
        if not orden:
            return jsonify(success=False, error="Orden no encontrada")

        # Configuración de carpeta
        folder = os.path.join(current_app.root_path, 'static', 'etiquetas')
        os.makedirs(folder, exist_ok=True)
        
        # Nombre final del archivo (siempre PDF)
        filename = secure_filename(f"ETI_MANUAL_{orden.numero_orden}.pdf")
        path_final = os.path.join(folder, filename)

        # --- LÓGICA DE UNIFICACIÓN (MERGE) ---
        merger = PdfMerger()
        
        count = 0
        for file in lista_archivos:
            if file.filename == '': continue
            # Agregamos cada PDF a la cola de fusión
            merger.append(file)
            count += 1
            
        if count == 0:
            return jsonify(success=False, error="Archivos vacíos")

        # Escribimos el archivo final unificado
        merger.write(path_final)
        merger.close()

        # Guardamos la ruta en la DB y actualizamos estado
        orden.etiqueta_url = f"/static/etiquetas/{filename}"
        
        # Flujo Manual: Si estaba esperando admin, ahora vuelve al Dashboard para imprimir
        if orden.origen == 'MANUAL':
            orden.estado = 'LISTO_DESPACHO' # O el estado que uses para imprimir
            orden.manual_etapa = 'CIERRE'

        db.session.commit()

        return jsonify(success=True, message=f"Se unieron {count} etiquetas correctamente.")

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error subiendo etiquetas: {e}")
        return jsonify(success=False, error=str(e))
    
@bp.route('/eliminar-orden', methods=['POST'])
def eliminar_orden():
    """Elimina una orden completa y sus items asociados."""
    # if not is_admin_logged_in(): return jsonify(success=False, error="No autorizado"), 403

    orden_id = request.form.get('orden_id')
    if not orden_id:
        return jsonify(success=False, error="Falta ID de orden")

    try:
        orden = Orden.query.get(orden_id)
        if not orden:
            return jsonify(success=False, error="Orden no encontrada")

        # Borrar items primero (aunque el cascade debería hacerlo, aseguramos)
        Item.query.filter_by(orden_id=orden.id).delete()
        
        # Borrar orden
        db.session.delete(orden)
        db.session.commit()

        return jsonify(success=True, message="Orden eliminada correctamente")

    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e))    
    
@bp.route('/subir-etiquetas-desglosadas', methods=['POST'])
def subir_etiquetas_desglosadas():
    import json
    try:
        orden_id = request.form.get('orden_id')
        orden = Orden.query.get(orden_id)
        if not orden: return jsonify(success=False, error="Orden no encontrada")

        # Recuperamos la lista de paquetes desde observaciones
        paquetes = orden.obtener_paquetes()
        if not paquetes:
            return jsonify(success=False, error="La orden no tiene bultos registrados")

        folder = os.path.join(current_app.root_path, 'static', 'etiquetas')
        os.makedirs(folder, exist_ok=True)
        
        archivos_guardados = 0

        # Iteramos los inputs posibles (etiqueta_0, etiqueta_1...)
        for i in range(len(paquetes)):
            key = f"etiqueta_{i}"
            file = request.files.get(key)
            
            if file and file.filename != '':
                # Nombre único: ETI_MAN_Orden_Bulto.pdf
                filename = secure_filename(f"ETI_MAN_{orden.numero_orden}_B{i+1}.pdf")
                path_final = os.path.join(folder, filename)
                file.save(path_final)
                
                # Guardamos la URL en el JSON del paquete
                paquetes[i]['etiqueta_url'] = f"/static/etiquetas/{filename}"
                archivos_guardados += 1

        if archivos_guardados > 0:
            # Actualizamos el JSON en la base de datos
            orden.observaciones = json.dumps(paquetes)
            
            # Liberamos la orden
            if orden.origen == 'MANUAL':
                orden.estado = 'LISTO_DESPACHO'
                orden.manual_etapa = 'CIERRE'
                
            # Fallback: Usamos la primera etiqueta como principal
            if paquetes and 'etiqueta_url' in paquetes[0]:
                orden.etiqueta_url = paquetes[0]['etiqueta_url']

            db.session.commit()
            return jsonify(success=True, message=f"Guardadas {archivos_guardados} etiquetas.")
        else:
            return jsonify(success=False, error="No se recibieron archivos.")

    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e))
    
@bp.route('/cargar-envio-full', methods=['POST'])
def cargar_envio_full():
    """Recibe Excel/CSV, itera TODAS las pestañas, extrae SKU/Cantidad y crea orden FULL."""
    try:
        if 'archivo_full' not in request.files:
            return jsonify(success=False, error="No se envió archivo")
        
        file = request.files['archivo_full']
        if not file or file.filename == '':
            return jsonify(success=False, error="Nombre de archivo vacío")

        # 1. Guardar archivo temporalmente
        filename = secure_filename(file.filename)
        folder = os.path.join(current_app.root_path, 'static', 'uploads_temp')
        os.makedirs(folder, exist_ok=True)
        filepath = os.path.join(folder, filename)
        file.save(filepath)

        # 2. Preparar lista de DataFrames a procesar (Soporte CSV y Excel Multi-Sheet)
        dfs_list = []
        
        if filename.endswith('.csv'):
            df = pd.read_csv(filepath, header=None)
            dfs_list.append(('CSV', df))
        else:
            # sheet_name=None lee un diccionario {nombre_hoja: dataframe} con TODAS las pestañas
            xls_dict = pd.read_excel(filepath, sheet_name=None, header=None)
            for sheet_name, df in xls_dict.items():
                dfs_list.append((sheet_name, df))

        items_a_cargar = []
        pestanas_leidas = 0
        
        # 3. Iterar sobre cada pestaña encontrada
        for sheet_name, df_raw in dfs_list:
            
            # --- Lógica de búsqueda de encabezados por hoja ---
            header_row_index = None
            col_sku_idx = None
            col_envio_idx = None

            # Buscamos en las primeras 20 filas de ESTA hoja
            # Usamos un try/except por si la hoja está vacía o es muy corta
            try:
                for i, row in df_raw.head(20).iterrows():
                    # Convertimos valores a string mayúscula para buscar
                    row_str = [str(val).strip().upper() for val in row.values]
                    
                    if 'SKU' in row_str:
                        if 'ENVÍO' in row_str or 'ENVIO' in row_str:
                            header_row_index = i
                            col_sku_idx = row_str.index('SKU')
                            try:
                                col_envio_idx = row_str.index('ENVÍO')
                            except ValueError:
                                col_envio_idx = row_str.index('ENVIO')
                            break
            except Exception:
                continue # Si falla leer esta hoja, pasamos a la siguiente
            
            # Si esta hoja no tiene las columnas clave, la saltamos (ej: hoja de resumen o instrucciones)
            if header_row_index is None:
                continue 
            
            pestanas_leidas += 1

            # --- Extraer datos de esta hoja ---
            for i in range(header_row_index + 1, len(df_raw)):
                try:
                    row = df_raw.iloc[i]
                    
                    # Verificamos que la fila tenga suficientes columnas
                    if len(row) <= max(col_sku_idx, col_envio_idx):
                        continue

                    sku = str(row[col_sku_idx]).strip().upper()
                    
                    # Limpieza de cantidad
                    cant_raw = row[col_envio_idx]
                    cantidad = 0
                    if pd.notnull(cant_raw):
                        val_str = str(cant_raw).replace('.','')
                        if val_str.isdigit():
                            cantidad = int(float(cant_raw))

                    if sku and sku != 'NAN' and sku != 'NONE' and cantidad > 0:
                        items_a_cargar.append({'sku': sku, 'cantidad': cantidad})
                except Exception:
                    continue # Si falla una fila, seguimos con la otra

        # 4. Validaciones Finales
        if not items_a_cargar:
            return jsonify(success=False, error="No se encontraron items válidos (SKU + Envío > 0) en ninguna pestaña.")

        # 5. CREAR LA ORDEN
        timestamp = datetime.now().strftime('%Y%m%d-%H%M')
        numero_orden_full = f"FULL-{timestamp}"

        nueva_orden = Orden(
            numero_orden=numero_orden_full,
            cliente_nombre="MERCADO LIBRE FULL",
            origen="FULL",
            destino="DEPÓSITO FULL",
            estado="PENDIENTE",
            fecha_creacion=datetime.now(),
            observaciones=f"Carga Masiva ({pestanas_leidas} pestañas leídas) desde {filename}"
        )
        # ... (código anterior de creación de la orden nueva_orden) ...
        db.session.add(nueva_orden)
        db.session.flush()

        # --- MODIFICACIÓN PARA BUSCAR DESCRIPCIÓN REAL ---
        for item in items_a_cargar:
            # 1. Buscamos el producto en la base de datos por SKU
            producto_db = ProductoMaestro.query.filter_by(sku=item['sku']).first()
            
            # 2. Si existe, usamos su descripción. Si no, ponemos un texto genérico con el SKU.
            if producto_db:
                descripcion_real = producto_db.descripcion
            else:
                descripcion_real = f"Producto FULL Desconocido ({item['sku']})"

            nuevo_item = Item(
                orden_id=nueva_orden.id,
                sku=item['sku'],
                cantidad=item['cantidad'],
                descripcion=descripcion_real  # <--- AQUÍ ESTABA EL CAMBIO CLAVE
            )
            db.session.add(nuevo_item)
        # ------------------------------------------------

        db.session.commit()
        # ... (resto del código igual) ...

        # Limpiar archivo
        try: os.remove(filepath) 
        except: pass

        return jsonify(
            success=True, 
            message=f"✅ Orden {numero_orden_full} creada.\nPestañas procesadas: {pestanas_leidas}\nTotal Items: {len(items_a_cargar)}\n(Debieran ser aprox 447 si el archivo está completo)"
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error procesando FULL: {str(e)}")
        return jsonify(success=False, error=f"Error interno: {str(e)}")