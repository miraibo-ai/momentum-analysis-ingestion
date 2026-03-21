# Momentum Analysis Ingestion

This repository contains the data ingestion component of the Momentum Ops project. It is responsible for fetching financial data from various sources and storing it in a PostgreSQL database. The data ingestion pipelines are orchestrated using Prefect.

## Architecture

The ingestion service is designed to be a standalone component that can be deployed independently of the other Momentum Ops services. It consists of the following components:

-   **Prefect Flows**: A set of Prefect flows that define the data ingestion pipelines.
-   **Docker**: The entire service is containerized using Docker for easy deployment and scalability.
-   **uv**: A fast Python package installer and resolver, used for managing dependencies.
-   **PostgreSQL**: A PostgreSQL database is used to store the ingested data.

## Architecture

For a detailed explanation of the architecture, please see the [Architecture Overview](Docs/architecture.md) document.

## Getting Started

### Prerequisites

-   Docker & Docker Compose
-   Python 3.12+ with `uv`
-   Git

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/miraibo-ai/momentum-analysis-ingestion.git
    cd momentum-analysis-ingestion
    ```

2.  **Set up the environment:**
    ```bash
    # Install uv (if not already installed)
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Install system dependencies (for Debian/Ubuntu)
    sudo apt update && sudo apt install docker.io docker-compose-v2 docker-buildx-plugin -y

    # Add your user to the docker group
    sudo usermod -aG docker $USER && newgrp docker
    ```

3.  **Build and run the services:**
    ```bash
    docker compose up -d --build
    ```

## Usage

### Deploying the Flows

To deploy the Prefect flows, run the following command:

```bash
docker compose exec worker uv run python deploy_market_flows.py
```

### Starting the Prefect Worker

To start the Prefect worker, run the following command:

```bash
prefect worker start --pool "vm-pool" --work-queue "market-data-ops"
```

### Accessing the Prefect UI

The Prefect UI is available at [http://localhost:4200](http://localhost:4200).

## Prefect Deployments

| Deployment                  | Schedule                             | Description                                            |
| :-------------------------- | :----------------------------------- | :----------------------------------------------------- |
| `kis-token-daily-refresh`   | `30 8 * * 1-5` (Asia/Seoul)          | Daily KIS Open API access-token renewal                |
| `krx-5min-ingestion-morning`| `*/5 9-14 * * 1-5` (Asia/Seoul)      | Realtime KRX data ingestion during morning trading hours |
| `krx-5min-ingestion-closing`| `0,5,10,15,20,25,30 15 * * 1-5` (Asia/Seoul) | Realtime KRX data ingestion during closing trading hours |
| `daily-ml-inference`        | `0 18 * * 1-5` (Asia/Seoul)          | Daily batch inference after market close               |

## Technical Stack

| Component       | Technology                                  |
| :-------------- | :------------------------------------------ |
| Language        | Python 3.13                                 |
| Package Manager | uv (Astral) with PEP 621 `pyproject.toml` |
| Database        | PostgreSQL 18 (psycopg 3)                   |
| Configuration   | Pydantic Settings v2                        |
| Orchestration   | Prefect 3                                   |
| Data            | yfinance, pandas                            |
| Deployment      | Docker Compose                              |

## Configuration

All settings are managed via environment variables and validated by Pydantic. The main configuration file for the Docker environment is `docker-compose.yml`.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
