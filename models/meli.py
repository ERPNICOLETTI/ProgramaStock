# models/meli.py
from database import db  # Importamos la db desde database.py
from datetime import datetime

class MeliToken(db.Model):
    __tablename__ = 'meli_token' # Es buena práctica poner nombre de tabla
    
    id = db.Column(db.Integer, primary_key=True)
    access_token = db.Column(db.String(255))
    refresh_token = db.Column(db.String(255))
    user_id = db.Column(db.String(50)) 
    expires_at = db.Column(db.DateTime)