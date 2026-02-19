from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from datetime import datetime
import os
from config import Config

def generar_remito_a4(items, numero_orden, deposito_origen):
    """
    Genera un PDF A4 (Tipo Remito) para Egresos.
    No imprime directo, devuelve la ruta para abrir en el navegador.
    """
    timestamp = datetime.now().strftime('%H%M%S')
    filename = f'remito_{numero_orden}_{timestamp}.pdf'
    pdf_path = os.path.join(Config.DBF_EXPORT_PATH, filename)
    
    os.makedirs(Config.DBF_EXPORT_PATH, exist_ok=True)
    
    c = canvas.Canvas(pdf_path, pagesize=A4)
    ancho, alto = A4
    
    # --- ENCABEZADO ---
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20*mm, alto - 20*mm, f"REMITO DE EGRESO - {numero_orden}")
    
    c.setFont("Helvetica", 10)
    c.drawString(20*mm, alto - 30*mm, f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    c.drawString(20*mm, alto - 35*mm, f"Depósito de Origen: {deposito_origen}")
    
    # Logo (si existe)
    ruta_logo = os.path.join(Config.BASE_DIR, 'static', 'logo.png')
    if os.path.exists(ruta_logo):
        try: c.drawImage(ruta_logo, ancho - 60*mm, alto - 30*mm, width=40*mm, height=10*mm, preserveAspectRatio=True, mask='auto')
        except: pass

    # --- TABLA DE ITEMS ---
    y = alto - 50*mm
    
    # Cabecera Tabla
    c.setFillColorRGB(0.9, 0.9, 0.9)
    c.rect(15*mm, y, ancho - 30*mm, 8*mm, fill=1, stroke=0)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 10)
    
    c.drawString(20*mm, y + 2.5*mm, "CANT")
    c.drawString(40*mm, y + 2.5*mm, "SKU")
    c.drawString(90*mm, y + 2.5*mm, "DESCRIPCIÓN")
    
    y -= 10*mm # Espacio para el primer item
    
    # Cuerpo Tabla
    c.setFont("Helvetica", 10)
    total_bultos = 0
    
    for item in items:
        # Verificar fin de página
        if y < 30*mm:
            c.showPage()
            y = alto - 20*mm
            c.setFont("Helvetica", 10)
        
        c.drawString(20*mm, y, str(item.cantidad_pickeada))
        c.drawString(40*mm, y, item.sku)
        c.drawString(90*mm, y, item.descripcion[:60]) # Truncar si es muy largo
        
        total_bultos += item.cantidad_pickeada
        y -= 6*mm
        
    # --- PIE DE PAGINA ---
    y_footer = 40*mm
    c.line(15*mm, y_footer, ancho - 15*mm, y_footer)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20*mm, y_footer - 5*mm, f"Total Bultos: {total_bultos}")
    
    c.setFont("Helvetica", 8)
    c.drawString(20*mm, 15*mm, "Documento generado internamente por Sistema WMS.")
    
    # Espacio firma
    c.line(130*mm, 25*mm, 190*mm, 25*mm)
    c.drawCentredString(160*mm, 20*mm, "Firma / Responsable")

    c.save()
    
    # Devolvemos la URL relativa para que el navegador lo pueda descargar/abrir
    return f"/descargar-archivo/{filename}"