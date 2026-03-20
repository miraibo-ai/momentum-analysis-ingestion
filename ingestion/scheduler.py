"""
Prefect deployment definitions for momentum-ops.

This file programmatically deploys the KR market high-frequency ingestion flow.
Legacy APScheduler logic has been fully migrated to ingestion/flows.py.
"""
 
from prefect.deployments.base import Deployment
from prefect.server.schemas.schedules import CronSchedule

from ingestion.flows import kr_minute_ingestion_flow


def deploy_kr_ingestion():
    """
    Builds and applies Prefect deployments for Korean market minute-data ingestion.
    Utilizes two separate cron schedules to strictly halt polling at exactly 15:30 KST.
    """

    # Schedule 1: 09:00 to 14:55 KST (Standard trading hours)
    morning_schedule = CronSchedule(cron="*/5 9-14 * * 1-5", timezone="Asia/Seoul")

    # Schedule 2: 15:00 to 15:30 KST (Captures the exact closing cross)
    closing_schedule = CronSchedule(
        cron="0,5,10,15,20,25,30 15 * * 1-5", timezone="Asia/Seoul"
    )

    # Create two separate deployments, as each can only have one schedule.
    morning_deployment = Deployment.build_from_flow(
        flow=kr_minute_ingestion_flow,
        name="kr-swing-morning-ingestion",
        schedule=morning_schedule,
        work_queue_name="default",
        description="5-minute KIS data ingestion for KR swing trades (morning session).",
    )

    closing_deployment = Deployment.build_from_flow(
        flow=kr_minute_ingestion_flow,
        name="kr-swing-closing-ingestion",
        schedule=closing_schedule,
        work_queue_name="default",
        description="5-minute KIS data ingestion for KR swing trades (closing session).",
    )

    morning_deployment.apply()
    closing_deployment.apply()
    print("Successfully applied KR ingestion deployments.")


if __name__ == "__main__":
    deploy_kr_ingestion()