# Subsea Diagram Builder

![Python](https://img.shields.io/badge/Python-3.x-blue.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)
![Flask](https://img.shields.io/badge/Flask-App-black.svg)
![License](https://img.shields.io/badge/License-TBD-lightgrey.svg)

To build subsea cable systems diagrams for Network Engineers.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Quick Start (Docker Compose Prod)](#quick-start-docker-compose-prod)
- [Portainer Deployment Checklist](#portainer-deployment-checklist)
- [Run Without Docker](#run-without-docker)
- [API Usage Examples](#api-usage-examples)
- [Recent Updates](#recent-updates)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## ðŸ“– Overview

The **Subsea Diagram Builder** is a specialized tool designed to help Network Engineers visualize, construct, and manage diagrams of subsea cable systems. By providing a streamlined interface and backend processing, this project simplifies the complex task of mapping out international underwater network infrastructure.The repository includes Docker-first deployment options and production compose support via `docker-compose.prod.yml`.

## Architecture

```text
User Browser
    |
    v
Flask App (app.py)
    |
    v
Topology/Diagram Engine (subsea_engine.py)
    |
    v
Input Payload (topology_payload.json) + Static Assets (static/)
```

For containerized production-style runtime:

```text
Docker Host / Portainer
    |
    v
docker-compose.prod.yml
    |
    v
subsea-topology-api (container, port 80)
    |
    v
Host port 8081
```

---

## ðŸ› ï¸ Tech Stack

This project is built using the following technologies:

*   **HTML (58.2%)**: Frontend structure and user interface.
*   **Python (37.4%)**: Backend logic, diagram generation, and data processing.
*   **Dockerfile (3.4%)**: Containerization for consistent and easy deployment.
*   **Shell (1.0%)**: Scripting for automation and setup tasks.

## Repository Structure

- `app.py` — Flask application entry point
- `subsea_engine.py` — diagram generation/business logic
- `topology_payload.json` — sample topology payload/input
- `static/` — static files for UI
- `requirements.txt` — Python dependencies
- `Dockerfile` — container build recipe
- `docker-compose.yml` — general/local compose config
- `docker-compose.prod.yml` — production-style compose file
- `nginx.conf` — NGINX config
- `start.sh` — startup helper script

## ðŸš€ Getting Started

### Prerequisites

To run this project locally, ensure you have the following installed:

*   [Python 3.x](https://www.python.org/downloads/)
*   [Docker](https://www.docker.com/products/docker-desktop/) (optional, but recommended for containerized deployment)

### Installation & Running Locally

#### Option 1: Using Docker (Recommended)

1. Clone the repository:
   ```bash
   git clone https://github.com/loopback007/subsea-diagram-builder.git
   cd subsea-diagram-builder
   ```

2. Build the Docker image:
   ```bash
   docker build -t subsea-diagram-builder .
   ```

3. Run the container:
   ```bash
   docker run -p 8080:8080 subsea-diagram-builder
   ```
   *(Note: Adjust the port mapping based on your application's specific configuration.)*

#### Option 2: Manual Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/loopback007/subsea-diagram-builder.git
   cd subsea-diagram-builder
   ```

2. Run any setup shell scripts provided:
   ```bash
   # Example:
   # ./setup.sh
   ```

3. Install Python dependencies and run the application (assuming a standard Python setup):
   ```bash
   pip install -r requirements.txt
   python app.py
   ```

## ðŸ¤ Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/loopback007/subsea-diagram-builder/issues) if you want to contribute.

## ðŸ“ License

This project is licensed under the [MIT License](LICENSE) - see the LICENSE file for details. (Update this section with your actual license if different).
