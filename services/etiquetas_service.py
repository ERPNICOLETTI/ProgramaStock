from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.graphics import renderPDF
from reportlab.lib.utils import ImageReader, simpleSplit
import os
import win32print
import win32ui
from PIL import Image, ImageWin, ImageEnhance
from pdf2image import convert_from_path
from config import Config
from datetime import datetime

# --- RUTA EXACTA DE POPPLER ---
POPPLER_PATH = r"C:\poppler-25.11.0\Library\bin"

# --- FUNCIONES DE DIBUJO ---
def dibujar_una_etiqueta(c, item, x_offset, logo_img, ancho, contador):
    """
    Dibuja una etiqueta con AUTO-AJUSTE de Código de Barras.
    MODIFICADO:
    - Desplazamiento TOTAL de 3mm a la derecha.
    - AJUSTE_X ahora es 0.0 (Antes -3.0).
    - Margen contador ahora es -1mm (Antes -4mm).
    """
    
    # 1. AJUSTE DE CENTRADO (Movido 3mm a la derecha)
    # Antes era -3.0mm. Al sumar 3mm, queda en 0.0mm.
    AJUSTE_X = 0.0 * mm 
    
    centro_x = x_offset + (ancho/2) + AJUSTE_X

    # 2. DESCRIPCIÓN (Arriba del todo)
    y_nombre = 20.0 * mm 
    c.setFont("Helvetica-Bold", 8)
    # Permitimos hasta 2 líneas de descripción
    lineas = simpleSplit(item.descripcion, "Helvetica-Bold", 8, 44 * mm)
    for linea in lineas[:2]:
        c.drawCentredString(centro_x, y_nombre, linea)
        y_nombre -= 3.0 * mm 

    # 3. CÓDIGO DE BARRAS INTELIGENTE
    try:
        # A) Definimos el ancho máximo disponible (Ancho etiqueta - 4mm de margen seguro)
        ancho_maximo_disponible = ancho - (4 * mm)
        
        # B) Intentamos crear el código con grosor IDEAL (Bien ancho y legible)
        grosor_ideal = 1.5 
        bc = createBarcodeDrawing('Code128', value=item.sku, barHeight=10*mm, barWidth=grosor_ideal, humanReadable=False)
        
        # C) Verificamos si se pasa del ancho
        ancho_real = bc.width
        
        if ancho_real > ancho_maximo_disponible:
            # D) SI SE PASA: Calculamos cuánto debemos achicarlo
            factor_reduccion = ancho_maximo_disponible / ancho_real
            nuevo_grosor = grosor_ideal * factor_reduccion
            
            # Re-generamos el código con el grosor ajustado para que quepa exacto
            bc = createBarcodeDrawing('Code128', value=item.sku, barHeight=10*mm, barWidth=nuevo_grosor, humanReadable=False)

        # E) Dibujamos (La matemática asegura que quede centrado sea ancho o fino)
        renderPDF.draw(bc, c, centro_x - (bc.width / 2), 6*mm)
        
    except Exception as e:
        print(f"Error dibujando barcode: {e}")
        pass

    # 4. SKU y CONTADOR (Pie de etiqueta)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(centro_x, 1.8*mm, item.sku)
    
    c.setFont("Helvetica", 7) 
    
    # El contador también se mueve 3mm a la derecha
    # Original: x_offset + ancho - 4*mm
    # Nuevo:    x_offset + ancho - 1*mm  (-4 + 3 = -1)
    c.drawRightString(x_offset + ancho - 1*mm, 1.8*mm, contador)


def imprimir_como_imagen_raw(pdf_path, printer_name, job_name="Trabajo WMS"):
    """
    *** SOLUCIÓN FINAL PIXEL PERFECT ***
    Rotar la imagen para corregir el eje del driver y dibujar con las dimensiones 
    resultantes, sin forzar reescalado.
    """
    
    if not os.path.exists(pdf_path):
        return {"success": False, "error": "Archivo no encontrado"}

    try:
        dpi_setting = 203
        images = convert_from_path(
            pdf_path,
            dpi=dpi_setting,
            poppler_path=POPPLER_PATH
        )
        if not images:
            return {"success": False, "msg": "No se pudo procesar el PDF"}

        hprinter = win32print.OpenPrinter(printer_name)
        try:
            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(printer_name)
            hdc.StartDoc(job_name)

            for idx, img in enumerate(images):
                # Rotación solo para etiquetas de producto
                if printer_name == Config.PRINTER_PRODUCTOS:
                    img = img.rotate(-90, expand=True)

                # Negro intenso
                img = img.convert("L")
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(2.5)
                img = img.point(lambda x: 0 if x < 140 else 255, '1')

                hdc.StartPage()
                dib = ImageWin.Dib(img)
                dib.draw(
                    hdc.GetHandleOutput(),
                    (0, 0, img.width, img.height)
                )
                hdc.EndPage()

            hdc.EndDoc()
            hdc.DeleteDC()
            return {
                "success": True,
                "msg": f"Impresas {len(images)} páginas en {printer_name}"
            }

        finally:
            win32print.ClosePrinter(hprinter)

    except Exception as e:
        print(f"Error impresión RAW: {e}")
        return {"success": False, "msg": f"Error de Impresora: {str(e)}"}


def generar_etiquetas_termicas(items, orden_nombre):
    """
    Genera el PDF y LLAMA DIRECTAMENTE a la impresión automática.
    """
    timestamp = datetime.now().strftime('%H%M%S')
    filename = f'etq_{orden_nombre}_{timestamp}.pdf'
    pdf_path = os.path.join(Config.DBF_EXPORT_PATH, filename)
    
    os.makedirs(Config.DBF_EXPORT_PATH, exist_ok=True)

    # --- 1. GENERAR PDF ---
    ANCHO_PAGINA = 104.0 * mm 
    ALTO_PAGINA = 25.0 * mm
    ANCHO_ETIQUETA = 50.0 * mm
    
    X_IZQUIERDA = 0.5 * mm 
    X_DERECHA = 53.5 * mm
    
    try:
        c = canvas.Canvas(pdf_path, pagesize=(ANCHO_PAGINA, ALTO_PAGINA))
        
        # Ya no cargamos el logo porque lo sacamos del diseño
        logo_img = None 

        lista_impresion = []
        for item in items:
            cantidad_sku = item.cantidad_pickeada
            for i in range(1, cantidad_sku + 1):
                texto_contador = f"{i}/{cantidad_sku}"
                lista_impresion.append((item, texto_contador))

        for i in range(0, len(lista_impresion), 2):
            item_izq, contador_izq = lista_impresion[i]
            dibujar_una_etiqueta(c, item_izq, X_IZQUIERDA, logo_img, ANCHO_ETIQUETA, contador_izq)
            
            if i + 1 < len(lista_impresion):
                item_der, contador_der = lista_impresion[i+1]
                dibujar_una_etiqueta(c, item_der, X_DERECHA, logo_img, ANCHO_ETIQUETA, contador_der)
                
            c.showPage()
        
        c.save()
        
        # --- 2. LLAMADA DIRECTA A LA IMPRESIÓN CORREGIDA ---
        printer_name = getattr(Config, 'PRINTER_PRODUCTOS', win32print.GetDefaultPrinter())
        return imprimir_como_imagen_raw(pdf_path, printer_name, filename)

    except Exception as e:
        return {"success": False, "msg": f"Error al generar el PDF: {str(e)}"}


# ==============================================================================
# 3. FUNCIONES PÚBLICAS (WRAPPERS)
# ==============================================================================

def imprimir_etiqueta_envio(pdf_path_relativo):
    """Llama a la impresión automática de etiquetas de envío."""
    clean_path = pdf_path_relativo.lstrip('/').lstrip('\\')
    full_path = os.path.join(Config.BASE_DIR, clean_path)
    
    printer = getattr(Config, 'PRINTER_ENVIOS', win32print.GetDefaultPrinter())
    return imprimir_como_imagen_raw(full_path, printer, "Etiqueta Envio")

def imprimir_factura_remito(pdf_path_relativo):
    """Llama a la impresión automática de facturas/remitos (A4)."""
    clean_path = pdf_path_relativo.lstrip('/').lstrip('\\')
    full_path = os.path.join(Config.BASE_DIR, clean_path)
    
    printer = getattr(Config, 'PRINTER_A4', win32print.GetDefaultPrinter())
    return imprimir_como_imagen_raw(full_path, printer, "Factura A4")