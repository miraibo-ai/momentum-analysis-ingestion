"""
deploy_market_flows.py
Unified deployment for KIS/KRX market data pipelines.
"""
from prefect import flow
from prefect.schedules import CronSchedule

from ingestion.flows import daily_batch_flow, kis_token_renewal_flow, krx_realtime_flow


def deploy_market_ops():
    # 1. KIS Token Renewal (Run daily at 08:30 KST)
    kis_token_renewal_flow.deploy(
        name="kis-token-daily-refresh",
        work_pool_name="vm-pool",
        schedule=CronSchedule(cron="30 8 * * 1-5", timezone="Asia/Seoul"),
        build=False # Assuming we use a pre-built Docker image
    )

    # 2. KRX Realtime (5-min intervals during market hours)
    krx_realtime_flow.deploy(
        name="krx-5min-ingestion",
        work_pool_name="vm-pool",
        schedules=[
            CronSchedule(cron="*/5 9-14 * * 1-5", timezone="Asia/Seoul"),
            CronSchedule(cron="0,5,10,15,20,25,30 15 * * 1-5", timezone="Asia/Seoul")
        ],
        build=False
    )

    # 3. Daily Batch (Post-market inference at 18:00 KST)
    daily_batch_flow.deploy(
        name="daily-ml-inference",
        work_pool_name="vm-pool",
        schedule=CronSchedule(cron="0 18 * * 1-5", timezone="Asia/Seoul"),
        build=False
    )

if __name__ == "__main__":
    deploy_market_ops()