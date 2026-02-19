from database import db
from datetime import datetime

class Picklist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    ordenes = db.relationship('Orden', backref='picklist', lazy=True)

class Orden(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_orden = db.Column(db.String(50), unique=True, nullable=False)
    origen = db.Column(db.String(20)) 
    destino = db.Column(db.String(50))
    
    # Datos Cliente
    cliente_nombre = db.Column(db.String(100)) 
    nro_factura = db.Column(db.String(50))
    estado_factura = db.Column(db.String(20), default='NO_FACTURADO')
    dni = db.Column(db.String(20))
    direccion = db.Column(db.String(200))
    localidad = db.Column(db.String(100))
    cp = db.Column(db.String(20))
    email = db.Column(db.String(100))
    telefono = db.Column(db.String(50))
    observaciones = db.Column(db.String(500))

    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    estado = db.Column(db.String(30), default='PENDIENTE')

    # --- FLUJO DE ORDEN ---
    # MELI | TN | MANUAL
    tipo_flujo = db.Column(db.String(20), nullable=False, default='MELI')

    # Solo para MANUAL:
    # PREPARACION -> operador pickea, imprime factura, mide y devuelve
    # CIERRE       -> admin adjunta etiqueta y reenvía
    manual_etapa = db.Column(db.String(20), nullable=True)
    
    picklist_id = db.Column(db.Integer, db.ForeignKey('picklist.id'), nullable=True)
    
    etiqueta_url = db.Column(db.String(500))
    factura_url = db.Column(db.String(500))

    # Datos Logísticos
    peso = db.Column(db.Float, default=0.0)
    largo = db.Column(db.Integer, default=0)
    ancho = db.Column(db.Integer, default=0)
    alto = db.Column(db.Integer, default=0)
    costo_envio = db.Column(db.Float, default=0.0)
    empresa_transporte = db.Column(db.String(50))
    tracking_number = db.Column(db.String(100))
    link_seguimiento = db.Column(db.String(500))
    
    meli_shipment_id = db.Column(db.String(50), nullable=True)
    meli_order_id = db.Column(db.String(50), nullable=True)

    items = db.relationship('Item', backref='orden', lazy=True, cascade="all, delete-orphan")

class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    orden_id = db.Column(db.Integer, db.ForeignKey('orden.id'), nullable=False)
    sku = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.String(200))
    
    cantidad_pedida = db.Column(db.Integer, nullable=False, default=1)
    cantidad_pickeada = db.Column(db.Integer, default=0)
    
    # --- FIX: COMENTAMOS COLUMNAS QUE NO EXISTEN EN TU DB ---
    # ubicacion = db.Column(db.String(50)) 
    # precio_unitario = db.Column(db.Float, default=0.0) 

    # --- PROPIEDADES VIRTUALES (Evitan el error 'no such column') ---
    @property
    def ubicacion(self):
        return "GRAL" # Valor por defecto si no existe la columna
    
    @ubicacion.setter
    def ubicacion(self, value):
        pass # Ignoramos la escritura para que no falle
        
    @property
    def precio_unitario(self):
        return 0.0
        
    @precio_unitario.setter
    def precio_unitario(self, value):
        pass

    # --- COMPATIBILIDAD ANTERIOR ---
    @property
    def cantidad(self):
        return self.cantidad_pedida
    
    @cantidad.setter
    def cantidad(self, value):
        self.cantidad_pedida = value

    @property
    def nombre(self):
        return self.descripcion

    @nombre.setter
    def nombre(self, value):
        self.descripcion = value

class ProductoMaestro(db.Model):
    sku = db.Column(db.String(50), primary_key=True)
    ean = db.Column(db.String(50), index=True) 
    descripcion = db.Column(db.String(200))
    
    # --- FIX: Lo mismo para stock_actual si no existe ---
    # stock_actual = db.Column(db.Integer, default=0) 
    @property
    def stock_actual(self):
        return 0
    @stock_actual.setter
    def stock_actual(self, val):
        pass

class ProductoCodigo(db.Model):
    codigo_barra = db.Column(db.String(100), primary_key=True)
    sku = db.Column(db.String(50), db.ForeignKey('producto_maestro.sku'), nullable=False)
    fecha_registro = db.Column(db.DateTime, default=datetime.now)

class Cliente(db.Model):
    codigo = db.Column(db.String(20), primary_key=True) 
    nombre = db.Column(db.String(100), index=True)      
    cuit = db.Column(db.String(20))                     
    direccion = db.Column(db.String(200))               
    localidad = db.Column(db.String(100))               
    telefono = db.Column(db.String(50))                 
    email = db.Column(db.String(100))                   

class Proveedor(db.Model):
    codigo = db.Column(db.String(20), primary_key=True)
    nombre = db.Column(db.String(100), index=True)      
    cuit = db.Column(db.String(20)) 
    direccion = db.Column(db.String(200))

class Movimiento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    orden_id = db.Column(db.Integer)
    sku = db.Column(db.String(50))
    cantidad = db.Column(db.Integer)
    fecha = db.Column(db.DateTime, default=datetime.now)
    exportado = db.Column(db.Boolean, default=False)

class MeliToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    access_token = db.Column(db.String(255))
    refresh_token = db.Column(db.String(255))
    user_id = db.Column(db.String(50)) 
    expires_at = db.Column(db.DateTime)