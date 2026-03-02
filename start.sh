#!/bin/sh
# Start Gunicorn workers in the background, bound to localhost
gunicorn --workers 3 --bind 127.0.0.1:5000 app:app &

# Start Nginx in the foreground so the container stays alive
nginx -g "daemon off;"