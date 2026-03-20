"""
deploy_market_flows.py
Unified deployment for KIS/KRX market data pipelines.
"""
from prefect.schedules import CronSchedule

from ingestion.flows import daily_batch_flow, kis_token_renewal_flow, krx_realtime_flow


def deploy_market_ops():
    """
    Builds and applies all market data pipeline deployments.
    """
    # 1. KIS Token Renewal (Run daily at 08:30 KST)
    kis_token_renewal_flow.deploy(
        name="kis-token-daily-refresh",
        work_pool_name="vm-pool",
        schedule=CronSchedule(cron="30 8 * * 1-5", timezone="Asia/Seoul"),
    )

    # 2. KRX Realtime (5-min intervals during market hours)
    # Schedule 1: 09:00 to 14:55 KST
    krx_realtime_flow.deploy(
        name="krx-5min-ingestion-morning",
        work_pool_name="vm-pool",
        schedule=CronSchedule(cron="*/5 9-14 * * 1-5", timezone="Asia/Seoul"),
    )

    # Schedule 2: 15:00 to 15:30 KST
    krx_realtime_flow.deploy(
        name="krx-5min-ingestion-closing",
        work_pool_name="vm-pool",
        schedule=CronSchedule(cron="0,5,10,15,20,25,30 15 * * 1-5", timezone="Asia/Seoul"),
    )

    # 3. Daily Batch (Post-market inference at 18:00 KST)
    daily_batch_flow.deploy(
        name="daily-ml-inference",
        work_pool_name="vm-pool",
        schedule=CronSchedule(cron="0 18 * * 1-5", timezone="Asia/Seoul"),
    )

    print("Successfully applied all market flow deployments.")


if __name__ == "__main__":
    deploy_market_ops()