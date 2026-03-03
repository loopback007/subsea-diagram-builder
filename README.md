# Subsea Diagram Builder

To build subsea cable systems diagrams for Network Engineers.

## 📖 Overview

The **Subsea Diagram Builder** is a specialized tool designed to help Network Engineers visualize, construct, and manage diagrams of subsea cable systems. By providing a streamlined interface and backend processing, this project simplifies the complex task of mapping out international underwater network infrastructure.

## 🛠️ Tech Stack

This project is built using the following technologies:

*   **HTML (58.2%)**: Frontend structure and user interface.
*   **Python (37.4%)**: Backend logic, diagram generation, and data processing.
*   **Dockerfile (3.4%)**: Containerization for consistent and easy deployment.
*   **Shell (1.0%)**: Scripting for automation and setup tasks.

## 🚀 Getting Started

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

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/loopback007/subsea-diagram-builder/issues) if you want to contribute.

## 📝 License

This project is licensed under the [MIT License](LICENSE) - see the LICENSE file for details. (Update this section with your actual license if different).
