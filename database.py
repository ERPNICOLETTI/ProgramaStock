from flask_sqlalchemy import SQLAlchemy

# Inicializamos la DB aquí para evitar conflictos circulares
db = SQLAlchemy()