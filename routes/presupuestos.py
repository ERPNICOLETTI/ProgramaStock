import os
import time
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, send_file
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

bp = Blueprint('presupuestos', __name__, url_prefix='/presupuestos')

# Ensure directories for budgets
PRESUPUESTOS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'presupuestos')
os.makedirs(PRESUPUESTOS_DIR, exist_ok=True)

@bp.route('/')
def vista_presupuestos():
    return render_template('presupuestos.html')

@bp.route('/api/historial', methods=['GET'])
def historial():
    try:
        files = []
        for f in os.listdir(PRESUPUESTOS_DIR):
            if f.endswith('.pdf'):
                path = os.path.join(PRESUPUESTOS_DIR, f)
                mtime = os.path.getmtime(path)
                files.append({
                    'name': f,
                    'date': datetime.fromtimestamp(mtime).strftime('%d/%m/%Y %H:%M:%S'),
                    'timestamp': mtime,
                    'url': f'/static/presupuestos/{f}'
                })
        # Sort by newest first
        files.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify({'success': True, 'archivos': files[:50]}) # Ultimos 50
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@bp.route('/api/generar-pdf', methods=['POST'])
def generar_pdf():
    data = request.json
    if not data:
        return jsonify({'success': False, 'error': 'No data sent'})
    
    cliente = data.get('cliente', '')
    localidad = data.get('localidad', '')
    cuit = data.get('cuit', '')
    condicion = data.get('condicion', '')
    items = data.get('items', [])
    
    if not items:
        return jsonify({'success': False, 'error': 'Cart is empty'})
    
    # Generate Unique Filename
    timestamp = int(time.time())
    filename = f"presupuesto_{timestamp}.pdf"
    filepath = os.path.join(PRESUPUESTOS_DIR, filename)
    
    # Create PDF with ReportLab
    try:
        c = canvas.Canvas(filepath, pagesize=A4)
        width, height = A4
        c.setFont("Courier", 10) # Using Courier to mimic Clipper monospaced look
        
        # --- HEADER ---
        c.drawString(40, height - 50, "PINO SUB S.C.A.")
        c.drawString(40, height - 65, "Av.Hipolito Yrigoyen 200")
        c.drawString(40, height - 80, "Puerto Madryn")
        
        fecha_actual = datetime.now().strftime("%d/%m/%Y")
        c.drawString(width - 200, height - 65, f"Fecha : {fecha_actual}")
        c.drawString(width - 200, height - 80, "PRESUPUESTO")
        
        # --- CLIENT INFO ---
        y = height - 120
        c.drawString(40, y, f"Sr.: *         {cliente.ljust(30)}")
        c.drawString(40, y - 15, f"{localidad}")
        c.drawString(40, y - 30, "__________________")
        c.drawString(40, y - 45, f"C.U.I.T.: {cuit.ljust(15)}")
        c.drawString(180, y - 45, f"Cuenta Corriente   Pago en   {condicion}")
        
        # --- TABLE HEADER ---
        y = y - 75
        c.drawString(30, y, "—" * 75)
        y -= 15
        c.drawString(35, y, "Codigo")
        c.drawString(110, y, "Cant")
        c.drawString(150, y, "Descripcion")
        c.drawString(400, y, "Precio")
        c.drawString(460, y, "Ajus.")
        c.drawString(510, y, "Total")
        y -= 15
        c.drawString(30, y, "—" * 75)
        
        # --- ITEMS ---
        y -= 20
        subtotal = 0.0
        for item in items:
            codigo = str(item.get('codigo', ''))[:10]
            cant = float(item.get('cant', 1))
            desc = str(item.get('desc', ''))[:35]
            precio = float(item.get('precio', 0))
            ajus = float(item.get('ajus', 0))
            
            total_item = (precio + ajus) * cant
            subtotal += total_item
            
            c.drawString(35, y, f"{codigo:<10}")
            c.drawString(110, y, f"{cant:.2f}")
            c.drawString(150, y, f"{desc:<35}")
            c.drawString(400, y, f"{precio:8.2f}")
            if ajus != 0:
                c.drawString(460, y, f"{ajus:8.2f}")
            c.drawRightString(550, y, f"{total_item:8.2f}")
            
            y -= 15
            if y < 150:
                c.showPage()
                y = height - 50
                c.setFont("Courier", 10)
        
        # --- FOOTER ---
        # Fuerza que el footer siempre inicie fijo desde abajo
        y = 120
        c.drawString(110, y, "En caso de abonar con cheques se imputara el pago")
        c.drawString(110, y - 15, "al tipo de cambio de la fecha de acreditacion.///")
        
        c.drawString(420, y, "Subtotal")
        c.drawRightString(550, y, f"{subtotal:8.2f}")
        
        y -= 45
        c.drawString(110, y, "Documento no valido como factura")
        c.drawString(420, y, "Total")
        c.drawRightString(550, y, f"{subtotal:8.2f}")
        
        c.save()
        
        return jsonify({'success': True, 'url': f'/static/presupuestos/{filename}'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

