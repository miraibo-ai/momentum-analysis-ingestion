"""
deploy_market_flows.py
Unified deployment for KIS/KRX market data pipelines.
"""
from prefect.deployments.runner import Deployment
from prefect.infrastructure import DockerContainer
from ingestion.flows import daily_batch_flow, kis_token_renewal_flow, krx_realtime_flow


def deploy_market_ops():
    """
    Builds and applies all market data pipeline deployments using an explicit
    infrastructure block to prevent Prefect from trying to build the image.
    """
    # Define the infrastructure for all deployments.
    # This points to our pre-built image and tells Prefect to never try to build or pull it.
    docker_infra = DockerContainer(
        image="momentum-worker",
        image_pull_policy="NEVER",
    )

    common_args = {
        "work_pool_name": "vm-pool",
        "infrastructure": docker_infra,
    }

    # 1. KIS Token Renewal (Run daily at 08:30 KST)
    Deployment.build_from_flow(
        flow=kis_token_renewal_flow,
        name="kis-token-daily-refresh",
        schedule={"cron": "30 8 * * 1-5", "timezone": "Asia/Seoul"},
        **common_args,
    ).apply()

    # 2. KRX Realtime (5-min intervals during market hours)
    # Schedule 1: 09:00 to 14:55 KST
    Deployment.build_from_flow(
        flow=krx_realtime_flow,
        name="krx-5min-ingestion-morning",
        schedule={"cron": "*/5 9-14 * * 1-5", "timezone": "Asia/Seoul"},
        **common_args,
    ).apply()

    # Schedule 2: 15:00 to 15:30 KST
    Deployment.build_from_flow(
        flow=krx_realtime_flow,
        name="krx-5min-ingestion-closing",
        schedule={"cron": "0,5,10,15,20,25,30 15 * * 1-5", "timezone": "Asia/Seoul"},
        **common_args,
    ).apply()

    # 3. Daily Batch (Post-market inference at 18:00 KST)
    Deployment.build_from_flow(
        flow=daily_batch_flow,
        name="daily-ml-inference",
        schedule={"cron": "0 18 * * 1-5", "timezone": "Asia/Seoul"},
        **common_args,
    ).apply()

    print("Successfully applied all market flow deployments.")


if __name__ == "__main__":
    deploy_market_ops()