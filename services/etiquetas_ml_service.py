import os
import tempfile
import win32print
import win32ui
from PIL import Image, ImageEnhance, ImageWin
from pdf2image import convert_from_path
from config import Config

# --- RUTA EXACTA DE POPPLER ---
POPPLER_PATH = r"C:\poppler-25.11.0\Library\bin"

def _imprimir_imagen_nativa(png_path: str, printer_name: str) -> None:
    """
    Simula un Ctrl+P inteligente.
    Ajusta la imagen al ANCHO del papel y calcula el ALTO proporcionalmente.
    Evita que la etiqueta se estire verticalmente si el driver tiene un largo incorrecto.
    """
    try:
        # 1. Abrir la imagen generada
        bmp = Image.open(png_path)
        img_w, img_h = bmp.size
        
        # 2. Conectar con la impresora
        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(printer_name)
        
        # 3. Obtener el tamaño REAL del papel (en píxeles)
        ancho_papel = hDC.GetDeviceCaps(110) # HORZRES (Ancho imprimible)
        alto_papel = hDC.GetDeviceCaps(111)  # VERTRES (Alto imprimible)
        
        # --- LOGICA DE PROPORCION (SMART FIT) ---
        # Calculamos la relación de aspecto de la imagen original
        ratio = img_h / img_w
        
        # Definimos el tamaño de destino:
        # Usamos todo el ANCHO disponible
        dest_w = ancho_papel
        
        # El ALTO lo calculamos matemáticamente para no deformar la imagen
        dest_h = int(dest_w * ratio)
        
        # (Opcional) Si el alto calculado es mayor que el papel, ajustamos al alto
        # pero en etiquetas térmicas lo vital suele ser el ancho.
        if dest_h > alto_papel:
             # Solo si se pasa del largo físico, re-escalamos para que entre en el alto
             # (Esto evita cortar si la hoja fuera muy corta, aunque no es tu caso)
             scale = alto_papel / dest_h
             dest_h = alto_papel
             dest_w = int(dest_w * scale)

        # 4. Iniciar trabajo
        hDC.StartDoc("Etiqueta WMS Smart")
        hDC.StartPage()
        
        dib = ImageWin.Dib(bmp)
        
        # Dibujamos desde la esquina (0,0) hasta el tamaño calculado (dest_w, dest_h)
        # Esto deja espacio blanco abajo si sobra papel, en lugar de estirar la imagen.
        dib.draw(hDC.GetHandleOutput(), (0, 0, dest_w, dest_h))
        
        hDC.EndPage()
        hDC.EndDoc()
        hDC.DeleteDC()
        
    except Exception as e:
        raise RuntimeError(f"Error nativo Windows: {str(e)}")

def imprimir_etiqueta_ml(pdf_path_relativo: str):
    """
    Convierte el PDF (vector) a Imagen (PNG) y la imprime estirada
    al tamaño del papel (10x15) usando el driver nativo.
    """
    try:
        # 1) Validar rutas
        if not pdf_path_relativo:
            return {"success": False, "error": "Ruta de etiqueta vacía"}
        
        # Limpieza de ruta (quita / iniciales)
        clean_path = pdf_path_relativo.lstrip('/').lstrip('\\')
        pdf_path = os.path.join(Config.BASE_DIR, clean_path)

        if not os.path.exists(pdf_path):
            return {"success": False, "error": f"Archivo PDF no encontrado: {pdf_path}"}

        # 2) Convertir PDF a Imagen 203 DPI (Estándar Térmicas)
        dpi_setting = 203
        images = convert_from_path(
            pdf_path,
            dpi=dpi_setting,
            poppler_path=POPPLER_PATH,
            first_page=1,
            last_page=1
        )

        if not images:
            return {"success": False, "error": "No se pudo convertir el PDF (sin páginas)"}

        img = images[0]

        # 3) Mejorar contraste para térmica (Negros puros)
        img = img.convert("L")
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.5)
        img = img.point(lambda x: 0 if x < 140 else 255, "1")

        # 4) Guardar PNG temporal
        tmp_dir = tempfile.gettempdir()
        tmp_png = os.path.join(tmp_dir, f"ml_label_{os.getpid()}_{int(__import__('time').time())}.png")
        img.save(tmp_png, format="PNG")

        # 5) Imprimir usando el driver nativo (Estirar a pagina)
        printer_name = getattr(Config, "PRINTER_ENVIOS", "").strip()
        if not printer_name:
            return {"success": False, "error": "Config.PRINTER_ENVIOS vacío (nombre de impresora requerido)"}

        # Llamada a la nueva función que reemplaza a MSPaint
        _imprimir_imagen_nativa(tmp_png, printer_name)
        
        # Limpieza (opcional, aunque Windows limpia temp eventualmente)
        try:
            os.remove(tmp_png)
        except:
            pass
            
        return {"success": True, "msg": "Etiqueta impresa (Nativo Windows)"}

    except Exception as e:
        return {"success": False, "error": str(e)}