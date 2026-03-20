"""
deploy_market_flows.py
Unified deployment for KIS/KRX market data pipelines using Prefect 2.
"""
from prefect.deployments import Deployment
from prefect.schedules.schedules import CronSchedule

from ingestion.flows import daily_batch_flow, kis_token_renewal_flow, krx_realtime_flow


def deploy_market_ops():
    """
    Builds and applies all market data pipeline deployments.
    """
    # 1. KIS Token Renewal (Run daily at 08:30 KST)
    kis_token_deployment = Deployment.build_from_flow(
        flow=kis_token_renewal_flow,
        name="kis-token-daily-refresh",
        work_queue_name="vm-pool",  # Must match the worker's pool
        schedule=CronSchedule(cron="30 8 * * 1-5", timezone="Asia/Seoul"),
    )
    kis_token_deployment.apply()

    # 2. KRX Realtime (5-min intervals during market hours)
    # Schedule 1: 09:00 to 14:55 KST
    krx_morning_deployment = Deployment.build_from_flow(
        flow=krx_realtime_flow,
        name="krx-5min-ingestion-morning",
        work_pool_name="vm-pool",
        schedule=CronSchedule(cron="*/5 9-14 * * 1-5", timezone="Asia/Seoul"),
    )
    krx_morning_deployment.apply()

    # Schedule 2: 15:00 to 15:30 KST
    krx_closing_deployment = Deployment.build_from_flow(
        flow=krx_realtime_flow,
        name="krx-5min-ingestion-closing",
        work_pool_name="vm-pool",
        schedule=CronSchedule(cron="0,5,10,15,20,25,30 15 * * 1-5", timezone="Asia/Seoul"),
    )
    krx_closing_deployment.apply()

    # 3. Daily Batch (Post-market inference at 18:00 KST)
    daily_batch_deployment = Deployment.build_from_flow(
        flow=daily_batch_flow,
        name="daily-ml-inference",
        work_pool_name="vm-pool",
        schedule=CronSchedule(cron="0 18 * * 1-5", timezone="Asia/Seoul"),
    )
    daily_batch_deployment.apply()

    print("Successfully applied all market flow deployments.")


if __name__ == "__main__":
    deploy_market_ops()