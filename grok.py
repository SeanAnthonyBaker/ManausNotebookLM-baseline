from flask import Blueprint, request, jsonify
import requests
import logging

grok_bp = Blueprint('grok', __name__)

@grok_bp.route('/grok', methods=['POST', 'OPTIONS'])
def proxy_grok():
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200

    try:
        data = request.json
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({"error": "Missing Authorization header"}), 401

        response = requests.post(
            'https://api.x.ai/v1/chat/completions',
            json=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': auth_header
            }
        )
        
        # Filter out CORS headers from the upstream response to avoid conflicts
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection', 'access-control-allow-origin', 'access-control-allow-methods', 'access-control-allow-headers']
        headers = [(k, v) for k, v in response.headers.items() if k.lower() not in excluded_headers]

        return (response.content, response.status_code, headers)
    except Exception as e:
        logging.error(f"Grok proxy error: {e}")
        return jsonify({"error": str(e)}), 500
