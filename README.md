# momentum-analysis-ingestion

## Install
curl -LsSf https://astral.sh/uv/install.sh | sh

sudo apt update && sudo apt install docker.io docker-compose-v2 -y
sudo usermod -aG docker $USER && newgrp docker

git clone https://github.com/miraibo-ai/momentum-analysis-ingestion.git
cd momentum-analysis-ingestion

docker compose down
docker compose up -d