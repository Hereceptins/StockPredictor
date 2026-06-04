"""
定时任务调度 — APScheduler

每日任务：
- 16:00 收盘后更新日K线
- 18:00 更新龙虎榜
- 23:00 AI模型批量预测 + 精选池生成
"""

from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

scheduler = AsyncIOScheduler()


async def init_scheduler():
    """初始化定时任务"""
    # 交易日收盘后更新
    scheduler.add_job(
        update_daily_kline,
        CronTrigger(hour=16, minute=30, day_of_week="mon-fri"),
        id="update_kline",
        replace_existing=True,
    )

    # 盘后更新龙虎榜
    scheduler.add_job(
        update_dragon_tiger,
        CronTrigger(hour=18, minute=0, day_of_week="mon-fri"),
        id="update_dragon_tiger",
        replace_existing=True,
    )

    # 夜间批量预测
    scheduler.add_job(
        generate_predictions,
        CronTrigger(hour=23, minute=0, day_of_week="mon-fri"),
        id="generate_predictions",
        replace_existing=True,
    )

    scheduler.start()


async def update_daily_kline():
    """更新日K线数据"""
    print(f"[{datetime.now()}] 开始更新日K线...")
    # TODO: 调用数据采集管道
    # from app.tasks.data_collection import collect_daily_kline
    # await collect_daily_kline()


async def update_dragon_tiger():
    """更新龙虎榜数据"""
    print(f"[{datetime.now()}] 开始更新龙虎榜...")
    # TODO


async def generate_predictions():
    """生成AI批量预测 + 精选池"""
    print(f"[{datetime.now()}] 开始生成AI预测...")
    # TODO: 加载最新模型 → 批量推理 → 生成精选池
    # from app.tasks.prediction_pipeline import run_prediction_pipeline
    # await run_prediction_pipeline()
