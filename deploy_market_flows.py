"""
deploy_market_flows.py
Unified deployment for KIS/KRX market data pipelines.
"""
from prefect.deployments import Deployment

from ingestion.flows import daily_batch_flow, kis_token_renewal_flow, krx_realtime_flow


def deploy_market_ops():
    """
    Builds and applies all market data pipeline deployments.
    """
    # 1. KIS Token Renewal (Run daily at 08:30 KST)
    Deployment.build_from_flow(
        flow=kis_token_renewal_flow,
        name="kis-token-daily-refresh",
        work_pool_name="vm-pool",
        schedule={"cron": "30 8 * * 1-5", "timezone": "Asia/Seoul"},
    ).apply()

    # 2. KRX Realtime (5-min intervals during market hours)
    # Schedule 1: 09:00 to 14:55 KST
    Deployment.build_from_flow(
        flow=krx_realtime_flow,
        name="krx-5min-ingestion-morning",
        work_pool_name="vm-pool",
        schedule={"cron": "*/5 9-14 * * 1-5", "timezone": "Asia/Seoul"},
    ).apply()

    # Schedule 2: 15:00 to 15:30 KST
    Deployment.build_from_flow(
        flow=krx_realtime_flow,
        name="krx-5min-ingestion-closing",
        work_pool_name="vm-pool",
        schedule={"cron": "0,5,10,15,20,25,30 15 * * 1-5", "timezone": "Asia/Seoul"},
    ).apply()

    # 3. Daily Batch (Post-market inference at 18:00 KST)
    Deployment.build_from_flow(
        flow=daily_batch_flow,
        name="daily-ml-inference",
        work_pool_name="vm-pool",
        schedule={"cron": "0 18 * * 1-5", "timezone": "Asia/Seoul"},
    ).apply()

    print("Successfully applied all market flow deployments.")


if __name__ == "__main__":
    deploy_market_ops()