#!/bin/bash

# 1. Update System
echo "Updating System..."
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git

# 2. Install Docker (Official Script)
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=\"$(dpkg --print-architecture)\" signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      \"$(. /etc/os-release && echo "$VERSION_CODENAME")\" stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
    echo "Docker already installed."
fi

# 3. Setup Permissions (Run docker without sudo)
sudo usermod -aG docker $USER
echo "Docker installed. You might need to logout and login again."

# 4. Clone/Pull Repo
REPO_URL="https://github.com/vivekpabari1894/PrintAgent.git"
DIR_NAME="PrintAgent"

if [ -d "$DIR_NAME" ]; then
    echo "Pulling latest code..."
    cd $DIR_NAME
    git pull origin main
else
    echo "Cloning repository..."
    git clone $REPO_URL
    cd $DIR_NAME
fi

# 5. Run Docker Compose
echo "Starting Odoo..."
cd odoo18_docker
# Note: Ensure you are logged in to existing shell session or newgrp for docker permission
sudo docker compose up -d --build

echo "Deployment Complete! Odoo should be available on Port 80."
