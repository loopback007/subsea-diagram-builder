FROM python:3.11-slim

# Install Nginx
RUN apt-get update && apt-get install -y nginx && rm -rf /var/lib/apt/lists/*

# Set up the working directory
WORKDIR /app

# Install Python dependencies first (caches this layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your Python application and frontend
COPY app.py subsea_engine.py ./
COPY static/ ./static/

# Remove default Nginx config and copy ours
RUN rm /etc/nginx/sites-enabled/default
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy entrypoint script and make it executable
COPY start.sh .
RUN chmod +x start.sh

# Expose standard HTTP port
EXPOSE 80

# Run the startup script
CMD ["./start.sh"]