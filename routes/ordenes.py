from flask import Blueprint, render_template, jsonify
from datetime import date
from database import db
from models.orden import Orden
from services.etiquetas_ml_service import imprimir_etiqueta_ml
from services import clipper_service



# Blueprint principal para el tablero
bp = Blueprint('ordenes', __name__, url_prefix='/ordenes')

@bp.route('/')
def dashboard():
    # 1. Órdenes activas (Excluyendo movimientos internos: Transf, Ingresos, Egresos)
    query_bruta = Orden.query.filter(
        Orden.estado.notin_(['DESPACHADO', 'CANCELADO']),
        Orden.origen.notin_(['TRANSFERENCIA', 'INGRESO', 'EGRESO']), # <--- CAMBIO REALIZADO
        Orden.estado != 'ESPERANDO_ADMIN'
    ).order_by(Orden.fecha_creacion.desc()).all()


    # 2. Filtro de seguridad (solo con items)
    ordenes_activas = [o for o in query_bruta if len(o.items) > 0]

    # 3. Estadísticas
    stats = {
        'listos': sum(1 for o in ordenes_activas if o.estado == 'LISTO_DESPACHO'),
        'en_prep': sum(1 for o in ordenes_activas if o.estado == 'EN_PREPARACION'),
        'esperando_admin': sum(1 for o in ordenes_activas if o.estado == 'ESPERANDO_ADMIN'),
        'despachados_hoy': Orden.query.filter(
            Orden.estado == 'DESPACHADO',
            Orden.fecha_creacion >= date.today(),
            Orden.origen != 'TRANSFERENCIA' 
        ).count()
    }

    return render_template('ordenes.html', ordenes=ordenes_activas, stats=stats)

@bp.route('/historial')
def historial_completo():
    ordenes = Orden.query.order_by(Orden.id.desc()).limit(100).all()
    return render_template('historial.html', ordenes=ordenes)

# API para el contador de notificaciones del menú lateral
@bp.route('/api/check-pendientes-admin')
def check_pendientes_admin():
    try:
        cantidad = Orden.query.filter(
            Orden.estado == 'PENDIENTE', 
            Orden.origen != 'TRANSFERENCIA'
        ).count()
        return jsonify({'success': True, 'pendientes': cantidad})
    except:
        return jsonify({'success': False, 'pendientes': 0})
    
# Aceptamos ambas rutas por si algún botón viejo todavía llama a /ml/
@bp.route('/imprimir/ml/<int:orden_id>')
@bp.route('/imprimir/envio/<int:orden_id>') 
def imprimir_etiqueta_envio_route(orden_id):
    orden = Orden.query.get(orden_id)
    if not orden:
        return jsonify(success=False, error="Orden no encontrada")

    # SIN restricción de origen (Funciona para MELI, TN, MANUAL)
    
    if not orden.etiqueta_url:
        return jsonify(success=False, error="La orden no tiene etiqueta asociada (PDF)")

    # Usamos el servicio unificado (MSPaint / Nativo)
    res = imprimir_etiqueta_ml(orden.etiqueta_url)
    return jsonify(res)


@bp.route('/importar-catalogo', methods=['POST'])
def importar_catalogo_route():
    # Corregido: Agregamos _dbf
    return jsonify(clipper_service.importar_catalogo_dbf())

@bp.route('/importar-proveedores', methods=['POST'])
def importar_proveedores_route():
    # Corregido: Agregamos _dbf
    return jsonify(clipper_service.importar_proveedores_dbf())

@bp.route('/importar-clientes', methods=['POST'])
def importar_clientes_route():
    # Corregido: Agregamos _dbf
    return jsonify(clipper_service.importar_clientes_dbf())




