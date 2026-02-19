import os

class Config:
    # Directorio base del proyecto
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Base de datos SQLite local
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(BASE_DIR, "pickeo.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Carpetas de intercambio
    DBF_EXPORT_PATH = os.path.join(BASE_DIR, 'exports')
    DBF_IMPORT_PATH = os.path.join(BASE_DIR, 'imports')
    
    # Clave secreta
    SECRET_KEY = 'erp-pino-wms-secret'
    
    # --- CONFIGURACIÓN DE IMPRESORAS ---
    # Usamos r'' (raw string) para que Python acepte las barras mezcladas (\ y /)
    
    # 1. ETIQUETAS DE ENVÍO (Andreani/Correo/MeLi) -> Xprinter XP-410B
    PRINTER_ENVIOS = r"\\http://192.168.1.121:631\Xprinter_410B"
    
    # 2. ETIQUETAS DE PRODUCTO (Ingresos/Transferencias) -> Argox OS-2140 PPLA
    PRINTER_PRODUCTOS = r'\\http://192.168.1.121:631\Argox_PPLA'
    
    # 3. DOCUMENTOS A4 (Facturas/Remitos) -> HP P1102w
    PRINTER_A4 = 'HP LaserJet Professional P 1102w'

    # --- CREDENCIALES MERCADOLIBRE (Extraídas de tu tokens.json) ---
    MELI_APP_ID = '6824976465100476' 
    MELI_SECRET_KEY = 'xeEJtTCqz0Jc4Om4hpqoJQHLyEsMMQGl'
    MELI_REDIRECT_URI = 'http://localhost:5000/meli/callback'

    # --- CONFIGURACIÓN DE ACCESO ---
    ADMIN_PASSWORD = 'pino1403' # <-- AÑADIDO: Contraseña de admin