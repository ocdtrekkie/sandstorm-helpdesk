import os
from waitress import serve
from helpdesk.web import create_app

if __name__ == '__main__':
    serve(create_app(), host='127.0.0.1', port=int(os.environ.get('PORT','8000')),
          threads=4, max_request_body_size=105*1024*1024)
