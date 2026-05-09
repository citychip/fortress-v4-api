"""
Master Orchestrator for Portfolio Strategy v3.2
Uses APScheduler to run all 10 workflow scripts at their precise scheduled times.
Designed to run continuously as a background process.
"""

import os
import sys
import time
import subprocess
from datetime import datetime
import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Setup dynamic paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Set up logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "orchestrator.log")),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("orchestrator")

# All scripts to run
SCRIPTS = {
    "premarket": os.path.join(BASE_DIR, "workflow_01_premarket_scanner.py"),
    "quantdata": os.path.join(BASE_DIR, "quantdata_daily.py"),
    "iv_crush": os.path.join(BASE_DIR, "workflow_05_iv_crush_report.py"),
    "whale_flow": os.path.join(BASE_DIR, "workflow_07_whale_flow_report.py"),
    "position_monitor": os.path.join(BASE_DIR, "workflow_03_position_monitor.py"),
    "dp_alert": os.path.join(BASE_DIR, "workflow_06_dark_pool_alert.py"),
    "eod_review": os.path.join(BASE_DIR, "workflow_04_eod_review.py"),
    "max_pain": os.path.join(BASE_DIR, "workflow_08_max_pain_report.py"),
}

def run_script(name, path):
    logger.info(f"Starting {name} ({path})...")
    try:
        result = subprocess.run(
            ["python3", path], 
            capture_output=True, 
            text=True, 
            timeout=300
        )
        if result.returncode == 0:
            logger.info(f"✅ {name} completed successfully.")
        else:
            logger.error(f"❌ {name} failed with return code {result.returncode}.")
            logger.error(f"Error output: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.error(f"❌ {name} timed out after 5 minutes.")
    except Exception as e:
        logger.error(f"❌ {name} execution failed: {str(e)}")

def schedule_jobs():
    # We use US/Eastern time for all trading schedules
    et_tz = pytz.timezone("US/Eastern")
    scheduler = BackgroundScheduler(timezone=et_tz)
    
    # 09:00 AM ET - Pre-Market
    scheduler.add_job(
        run_script, 
        CronTrigger(day_of_week='mon-fri', hour=9, minute=0, timezone=et_tz), 
        args=["Pre-Market Scanner", SCRIPTS["premarket"]],
        id="premarket"
    )
    
    # 09:35 AM ET - Market Open / Morning Briefing
    scheduler.add_job(
        run_script, 
        CronTrigger(day_of_week='mon-fri', hour=9, minute=35, timezone=et_tz), 
        args=["Daily QuantData Summary", SCRIPTS["quantdata"]],
        id="quantdata"
    )
    scheduler.add_job(
        run_script, 
        CronTrigger(day_of_week='mon-fri', hour=9, minute=35, timezone=et_tz), 
        args=["IV Crush Opportunity", SCRIPTS["iv_crush"]],
        id="iv_crush"
    )
    scheduler.add_job(
        run_script, 
        CronTrigger(day_of_week='mon-fri', hour=9, minute=35, timezone=et_tz), 
        args=["Whale Flow Report", SCRIPTS["whale_flow"]],
        id="whale_flow"
    )
    
    # 12:00 PM ET - Mid-Day Monitoring
    scheduler.add_job(
        run_script, 
        CronTrigger(day_of_week='mon-fri', hour=12, minute=0, timezone=et_tz), 
        args=["Position Monitor (Mid-Day)", SCRIPTS["position_monitor"]],
        id="position_monitor_mid"
    )
    scheduler.add_job(
        run_script, 
        CronTrigger(day_of_week='mon-fri', hour=12, minute=0, timezone=et_tz), 
        args=["Dark Pool Alert (Mid-Day)", SCRIPTS["dp_alert"]],
        id="dp_alert_mid"
    )
    
    # 3:45 PM ET - Pre-Close Monitoring
    scheduler.add_job(
        run_script, 
        CronTrigger(day_of_week='mon-fri', hour=15, minute=45, timezone=et_tz), 
        args=["Position Monitor (Pre-Close)", SCRIPTS["position_monitor"]],
        id="position_monitor_close"
    )
    scheduler.add_job(
        run_script, 
        CronTrigger(day_of_week='mon-fri', hour=15, minute=45, timezone=et_tz), 
        args=["Dark Pool Alert (Pre-Close)", SCRIPTS["dp_alert"]],
        id="dp_alert_close"
    )
    
    # 4:15 PM ET - End of Day Review
    scheduler.add_job(
        run_script, 
        CronTrigger(day_of_week='mon-fri', hour=16, minute=15, timezone=et_tz), 
        args=["End of Day Review", SCRIPTS["eod_review"]],
        id="eod_review"
    )
    
    # Fridays 4:30 PM ET - Max Pain Report
    scheduler.add_job(
        run_script, 
        CronTrigger(day_of_week='fri', hour=16, minute=30, timezone=et_tz), 
        args=["Max Pain Report (Weekly)", SCRIPTS["max_pain"]],
        id="max_pain_weekly"
    )
    
    return scheduler

if __name__ == "__main__":
    logger.info("Starting Master Orchestrator for Portfolio Strategy v3.2...")
    logger.info("All times are in US/Eastern timezone.")
    
    scheduler = schedule_jobs()
    scheduler.start()
    
    # Print schedule
    logger.info("--- Scheduled Jobs ---")
    for job in scheduler.get_jobs():
        logger.info(f"[{job.id}] Next run: {job.next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info("----------------------")
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down orchestrator...")
        scheduler.shutdown()
        logger.info("Orchestrator stopped.")
