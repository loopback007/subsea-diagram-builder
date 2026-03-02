from flask import Flask, request, send_file, jsonify
import os
import json
# Assuming your generation script is saved as 'subsea_engine.py'
from subsea_engine import generate_from_json 

app = Flask(__name__, static_folder='static', static_url_path='')

@app.route('/')
def index():
    # Serve the frontend HTML form
    return app.send_static_file('index.html')

@app.route('/api/generate', methods=['POST'])
def generate_topology():
    try:
        payload = request.get_json()
        
        # Temporary file handling (in production, use tempfile or memory buffers)
        input_filepath = 'temp_payload.json'
        output_filepath = f"{payload.get('system_name', 'topology_output')}.drawio"
        
        with open(input_filepath, 'w') as f:
            json.dump(payload, f)
            
        # Trigger the math engine
        generate_from_json(input_filepath, output_filepath)
        
        # Send the file back to the browser
        return send_file(output_filepath, as_attachment=True)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Binds to 0.0.0.0 making it ready for a Docker container
    app.run(host='0.0.0.0', port=5000, debug=True)