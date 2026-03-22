# Architecture Overview

This document provides a high-level overview of the `momentum-analysis-ingestion` service architecture.

## System Components & Deployment

The service is composed of three main components, all running as Docker containers managed by Docker Compose:

1.  **Prefect Server:** The central hub for orchestrating and monitoring the data ingestion pipelines. It provides a UI for observing flow runs and their states.

2.  **Prefect Worker:** This component is responsible for executing the data ingestion flows. It polls the Prefect server for new flow runs and, upon receiving a work order, it spins up a new Docker container to execute the flow.

3.  **PostgreSQL Database:** A PostgreSQL database is used to store all the financial data ingested by the Prefect flows.

### Deployment Diagram

The following diagram illustrates the interaction between the different runtime components of the system:

```mermaid
graph TD
    subgraph "Docker Host"
        subgraph "Docker Compose Services"
            A[Prefect Server]
            B[Prefect Worker]
            C[PostgreSQL Database]
        end

        subgraph "Flow Execution (Ephemeral)"
            D[Flow Run Container]
        end

        A -- "Schedules Flow Runs" --> B
        B -- "Executes Flows In" --> D
        D -- "Reads/Writes Data" --> C
    end
```

## Code-Level Architecture

This section details the internal structure and responsibilities of the Python modules.

### Module: /common

The `common` module provides foundational, cross-cutting services required by other parts of the application.

#### **Responsibilities & Logic Flow**

*   **Responsibility**: It is responsible for loading, validating, and providing access to all external configurations (e.g., credentials, hostnames, API keys) via a centralized `settings` object.
*   **Responsibility**: It manages the lifecycle of the PostgreSQL database connection pool, offering a simple, thread-safe interface for other modules to acquire and release connections.
*   **Input**: The module's primary input is the external environment (e.g., a `.env` file or shell environment variables) which provides the raw configuration values.
*   **Output**: Its primary outputs are a validated `settings` object from `config.py` and usable database connections from the managed pool in `database.py`.

#### **Component Diagram**

This diagram illustrates how the `common` module interacts with the environment and serves other application modules.

```mermaid
graph TD
    subgraph "External System"
        A[Environment Variables/.env File]
    end

    subgraph "/common Module"
        B(config.py: Settings Object)
        C(database.py: Connection Pool)
    end

    subgraph "Application Modules (Consumers)"
        D[ingestion/flows.py]
        E[ingestion/fetcher.py]
        F[models/models.py]
    end

    A -- "Provides configuration to" --> B
    B -- "Provides DB URL to" --> C
    
    B -- "Provides settings to" --> D
    C -- "Provides DB connection to" --> D

    B -- "Provides API keys to" --> E

    B -- "Provides settings to" --> F
    C -- "Provides DB connection to" --> F
```

### Module: /ingestion

The `/ingestion` module is the system's core orchestration layer, built around Prefect flows. It handles all data fetching, processing, and storage logic.

#### **Responsibilities & Logic Flow**

*   **Responsibility**: Manages scheduled and ad-hoc data acquisition from multiple external financial APIs (`yfinance` for daily data, KIS for real-time Korean market data).
*   **Responsibility**: Orchestrates the persistence of raw and processed data by interfacing with the `common/database` module to write price history, technical indicators, and model predictions to PostgreSQL.
*   **Responsibility**: Triggers analysis and machine learning inference by invoking functions in the `/models` module with the newly fetched historical data.
*   **Input**: The primary inputs are the active ticker symbols queried from the database and API credentials provided by the `common/config` module.
*   **Output**: The module does not return values directly but writes extensively to the PostgreSQL database, populating the `price_daily`, `price_minute_ohlcv_kr`, and `analysis_info` tables.

#### **Workflow Diagram**

This sequence diagram illustrates the primary workflows orchestrated by the `ingestion/flows.py` file.

```mermaid
sequenceDiagram
    participant S as Prefect Scheduler
    participant F as ingestion/flows.py
    participant D as common/database.py
    participant H as ingestion/fetcher.py
    participant M as models/models.py

    S->>+F: Triggers `daily_batch_flow` (End-of-Day)
    F->>D: fetch_active_tickers()
    D-->>F: Returns list of tickers
    loop For each ticker
        F->>H: fetch_yfinance_daily()
        H-->>F: Returns historical DataFrame
        F->>D: upsert_daily_prices()
        F->>M: run_inference_and_persist()
        M->>D: Inserts analysis results (indicators & predictions)
    end
    F-->>-S: Flow completes

    S->>+F: Triggers `krx_realtime_flow` (Market Hours)
    F->>H: (Uses pre-saved KIS Token)
    F->>D: fetch_active_tickers()
    D-->>F: Returns list of Korean tickers
    loop For each Korean ticker
        F->>H: fetcher.fetch_minute_data()
        H-->>F: Returns minute-level DataFrame
        F->>D: Upserts minute data into DB
    end
    F-->>-S: Flow completes
```

### Module: /models

The `/models` module is responsible for running machine learning inference to predict future market direction based on pre-calculated features. It encapsulates feature engineering and model prediction into a unified workflow.

#### **Responsibilities & Logic Flow**

*   **Responsibility**: The module's core responsibility is to transform raw OHLCV (Open, High, Low, Close, Volume) data into a set of engineered features and then use those features to generate predictions from a portfolio of four pre-trained XGBoost models.
*   **Input**: The primary input is a pandas DataFrame containing daily OHLCV data, sorted chronologically. A minimum of ~30 rows is required to compute the feature look-back windows.
*   **Output**: The main output is a tuple containing two dictionaries:
    1.  `probabilities`: A dictionary mapping each of the four model names to its predicted probability of a positive return (e.g., `{"active_1w": 0.82, ...}`).
    2.  `contributions`: A dictionary mapping each model to its top-3 local feature contributions (TreeSHAP values), explaining which features most influenced the prediction.
*   **Dependencies**:
    *   **Internal**: It depends on the `common.config` module to locate the `model_artifacts/` directory.
    *   **External**: It relies on `pandas` for data manipulation, `numpy` for numerical operations, and `xgboost` for loading models and running inference.

#### **Component Diagram**

This diagram illustrates the internal logic of the module and its interaction with the feature engineering sub-module.

```mermaid
graph TD
    subgraph /models Module
        direction TB
        A[Input: OHLCV DataFrame] --> B(FourModelPredictor);

        subgraph Feature Engineering
            direction LR
            C(features.py) -- calculates --> D{RSI};
            C -- calculates --> E{MACD};
            C -- calculates --> F{Bollinger Bands};
            C -- calculates --> G{...and others};
        end

        subgraph Multi-Model Inference
            direction TB
            H(DirectionPredictor 1) -. loads .-> I[model_artifacts/active_1w.json];
            J(DirectionPredictor 2) -. loads .-> K[model_artifacts/conservative_1mo.json];
            L(DirectionPredictor 3) -. loads .-> M[model_artifacts/conservative_6mo.json];
            N(DirectionPredictor 4) -. loads .-> O[model_artifacts/experimental.json];

            P[Feature DataFrame] --> H;
            P --> J;
            P --> L;
            P --> N;

            H --> Q{Prob active_1w};
            J --> R{Prob conservative_1mo};
            L --> S{Prob conservative_6mo};
            N --> T{Prob experimental};
        end

        B -- calls --> C(engineer_features);
        C --> P;
        B -- manages --> H;
        B -- manages --> J;
        B -- manages --> L;
        B -- manages --> N;

        Q & R & S & T --> U[Output: Dict of Probabilities & Contributions];
    end

    style C fill:#f9f,stroke:#333,stroke-width:2px
    style B fill:#ccf,stroke:#333,stroke-width:2px
```
