import os
import logging
from flask import Flask, send_from_directory
from flask_cors import CORS
from models import db
from user import user_bp
from notebooklm import notebooklm_bp

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# Configuration
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'a-default-insecure-secret-key-for-dev')
app.config['SECRET_KEY'] = SECRET_KEY
db_path = os.path.join(os.path.dirname(__file__), 'database')
os.makedirs(db_path, exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(db_path, 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Extensions
CORS(app)
db.init_app(app)

# Blueprints
app.register_blueprint(user_bp, url_prefix='/api')
app.register_blueprint(notebooklm_bp, url_prefix='/api')

# Create database tables if they don't exist
with app.app_context():
    db.create_all()

# Static file serving
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    app.run(host='0.0.0.0', port=port, debug=debug)
