from flask import Blueprint, render_template, request, jsonify
from services.consulta_live import buscar_stock_live

bp = Blueprint('stock', __name__, url_prefix='/stock')

@bp.route('/')
def vista_consulta():
    return render_template('stock_live.html')

@bp.route('/api/buscar')
def api_buscar():
    q = request.args.get('q', '')
    if len(q) < 2:
        return jsonify({'success': False, 'error': 'Escribe al menos 2 letras'})
    
    resp = buscar_stock_live(q)
    return jsonify(resp)