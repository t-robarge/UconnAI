from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
import requests
import os

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Load your API key from an environment variable
API_KEY = os.environ.get("DIFY_API_KEY")
# Dify API endpoint for sending chat messages
API_URL = "https://api.dify.ai/v1/chat-messages"

@app.route('/')
def index():
    return app.send_static_file('index.html')

from flask import Flask, request, redirect, session, url_for
import requests
import xml.etree.ElementTree as ET

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with your own secret key

CAS_LOGIN_URL = "https://login.uconn.edu/cas/login"
CAS_VALIDATE_URL = "https://login.uconn.edu/cas/serviceValidate"

@app.route('/login')
def login():
    ticket = request.args.get('ticket')
    # The service URL is this endpoint's URL.
    service_url = url_for('login', _external=True)

    if not ticket:
        # Redirect the user to the CAS login page.
        return redirect(f"{CAS_LOGIN_URL}?service={service_url}")
    else:
        # Validate the ticket by contacting the CAS service.
        validate_url = f"{CAS_VALIDATE_URL}?ticket={ticket}&service={service_url}"
        try:
            response = requests.get(validate_url)
            response.raise_for_status()
        except requests.RequestException as e:
            return f"Error contacting CAS: {e}", 500

        # Parse the XML response from CAS.
        # (The XML namespace may need to be adjusted based on the CAS server's response.)
        root = ET.fromstring(response.text)
        ns = {'cas': 'https://login.uconn.edu/cas/login'}  # Adjust namespace if needed
        auth_success = root.find('cas:authenticationSuccess', ns)

        if auth_success is not None:
            user = auth_success.find('cas:user', ns).text
            # Store the authenticated user in the session.
            session['user'] = user
            # Redirect to your main page.
            return redirect(url_for('index'))
        else:
            return "Authentication failed", 401

@app.route('/proxy/chat-messages', methods=['POST'])
def chat_messages():
    if request.method == 'OPTIONS':
        response = make_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'POST,OPTIONS'
        return response
    try:
        data = request.get_json()
        app.logger.info("Received data: %s", data)
        
        # Check if API_KEY is set
        if not API_KEY:
            app.logger.error("API_KEY is not set!")
            return "API key not set", 500

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        app.logger.info("Sending request to Dify API with headers: %s", headers)
        
        api_response = requests.post(API_URL, json=data, headers=headers)
        app.logger.info("Upstream API responded with status %s and content: %s", 
                        api_response.status_code, api_response.text)
        
        response = make_response(api_response.content, api_response.status_code)
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    except Exception as e:
        app.logger.exception("Exception occurred in /proxy/chat-messages")
        return str(e), 500

if __name__ == '__main__':
    # Run the Flask app on port 5000 (or any other desired port)
    app.run(port=5000, debug=True)
