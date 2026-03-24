"""
Prefect deployment definitions for momentum-ops.

This file programmatically deploys the KR market high-frequency ingestion flow.
Legacy APScheduler logic has been fully migrated to ingestion/flows.py.
"""
 


from ingestion.flows import kr_minute_ingestion_flow


def deploy_kr_ingestion():
    """
    Builds and applies Prefect deployments for Korean market minute-data ingestion.
    Utilizes two separate cron schedules to strictly halt polling at exactly 15:30 KST.
    """

    # 1. Morning session: 09:00 to 14:55 KST (Standard trading hours)
    kr_minute_ingestion_flow.deploy(
        name="kr-swing-morning-ingestion",
        schedule={"cron": "*/5 9-14 * * 1-5", "timezone": "Asia/Seoul"},
        work_pool_name="vm-pool",  # Update as needed
        description="5-minute KIS data ingestion for KR swing trades (morning session).",
    )

    # 2. Closing session: 15:00 to 15:30 KST (Captures the exact closing cross)
    kr_minute_ingestion_flow.deploy(
        name="kr-swing-closing-ingestion",
        schedule={"cron": "0,5,10,15,20,25,30 15 * * 1-5", "timezone": "Asia/Seoul"},
        work_pool_name="vm-pool",  # Update as needed
        description="5-minute KIS data ingestion for KR swing trades (closing session).",
    )

    print("Successfully applied KR ingestion deployments.")


if __name__ == "__main__":
    deploy_kr_ingestion()