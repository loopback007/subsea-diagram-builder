from flask import Flask, request, send_file, jsonify
import io
from subsea_engine import generate_from_config

app = Flask(__name__, static_folder='static', static_url_path='')

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/generate', methods=['POST'])
def generate_topology():
    try:
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "Missing or invalid JSON body."}), 400

        # FIX: Generate entirely in-memory — no temp files, no concurrent-request collisions.
        xml_bytes = generate_from_config(payload)

        system_name = payload.get('system_name', 'topology_output')
        filename = f"{system_name}.drawio"

        return send_file(
            io.BytesIO(xml_bytes),
            mimetype='application/xml',
            as_attachment=True,
            download_name=filename
        )

    except ValueError as e:
        # Structured validation errors from the engine come back as 422 with detail
        return jsonify({"error": str(e)}), 422

    except Exception as e:
        return jsonify({"error": f"Unexpected server error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)