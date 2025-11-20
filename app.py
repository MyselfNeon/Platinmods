from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Platinmods Tracker Bot is Alive!"

def run_web_server(port):
    """Runs the Flask app in a separate thread."""
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def start_web_server(port):
    """Helper to start the server thread."""
    t = threading.Thread(target=run_web_server, args=(port,))
    t.daemon = True
    t.start()