import json
from typing import List

import datetime
from log import logger
from dateutil.relativedelta import relativedelta

class TradingStatistics():    
    def __init__(self, **kwargs):
        self.id = kwargs.get('id',0)
        self.datetime = kwargs.get('datetime','')
        self.money = kwargs.get('money',0)
        self.exId = kwargs.get('exId',0)
    def to_json(self):
        return {
            'datetime': self.datetime,
            'money': self.money,
            'exId':self.exId
        }

async def query_total_by_range(exid:List[int],start: datetime.datetime, end: datetime.datetime):
    from DataStore import db_pool
    async with db_pool.acquire() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    f"SELECT * FROM TradingStatistics WHERE datetime >= %s AND datetime <= %s AND exId IN %s ORDER BY datetime",
                    (start, end,tuple(exid))
                )
                result = await cursor.fetchall()
                columns = [column[0] for column in cursor.description]
                return [TradingStatistics(**dict(zip(columns, row))) for row in result]
        except Exception as e:
            logger.error(
                f"TradingStatistics表 query_total_by_range 查询错误 : {e}")

    
async def insert(d):
    from DataStore import db_pool
    async with db_pool.acquire() as conn:
        try:
            # 开始数据库事务
            async with conn.cursor() as cursor:
                # 插入数据
                if isinstance(d, list):
                    for item in d:
                        await cursor.execute(
                            "INSERT INTO TradingStatistics (datetime, money, exId) VALUES (%s, %s, %s)",
                            (item.datetime, item.money, item.exId)
                        )
                elif isinstance(d, TradingStatistics):
                    await cursor.execute(
                        "INSERT INTO TradingStatistics (datetime, money, exId) VALUES (%s, %s, %s)",
                        (d.datetime, d.money, d.exId)
                    )
        except Exception as e:
            # 处理异常
            logger.error(f"TradingStatistics表 insert 插入错误 : {e}")