from app import create_app
import logging

app = create_app()

if __name__ == '__main__':
    # Suppress routine Flask request logs, only show warnings and errors
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.WARNING)

    app.run(host='0.0.0.0', port=5000)
