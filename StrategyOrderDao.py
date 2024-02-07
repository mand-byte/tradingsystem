from typing import List
from log import logger

class StrategyOrder():    
    def __init__(self, **kwargs):
        self.id = kwargs.get('id',0)
        self.symbol=kwargs.get('symbol','')
        self.condition1=kwargs.get('condition1',0)
        self.condition1status=kwargs.get('condition1status',0)
        self.condition2=kwargs.get('condition2',0)
        self.exids = kwargs.get('exids','')
        self.opentime = kwargs.get('opentime','')
        self.deleted=kwargs.get('deleted',0)
        self.endtime=kwargs.get('endtime',0)
        self.posSide = kwargs.get('posSide','long')
        self.money = kwargs.get('money',0)
        self.isswap = kwargs.get('isswap',0)
        self.sl=kwargs.get('sl',0)
        self.tp=kwargs.get('tp',0)
async def query_all_strategy_orders() -> List[StrategyOrder]:
    from DataStore import db_pool
    async with db_pool.acquire() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    f"SELECT * FROM strategy_order WHERE deleted=0"
                )
                result = await cursor.fetchall()
                columns = [column[0] for column in cursor.description]
                if result:
                    return [StrategyOrder(**dict(zip(columns, row))) for row in result]
        except Exception as e:
            logger.error(
                f"strategy_order表 query_all_strategy_orders 查询错误 : {e}")
            
async def update_strategy_order(order:StrategyOrder):
        from DataStore import db_pool
        async with db_pool.acquire() as conn:
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        f"UPDATE strategy_order SET symbol=%s, condition1=%s, condition1status=%s, condition2=%s, "
                        "exids=%s, opentime=%s, deleted=%s, endtime=%s, posSide=%s, money=%s, isswap=%s, sl=%s, tp=%s WHERE id=%s",
                        (order.symbol, order.condition1, order.condition1status, order.condition2, order.exids, order.opentime,
                         order.deleted, order.endtime, order.posSide, order.money, order.isswap,order.sl,order.tp, order.id)
                    )
                    await conn.commit()
            except Exception as e:
                logger.error(
                    f"strategy_order表 update_strategy_order 更新错误: {e}")

async def insert_strategy_order(order:StrategyOrder):
        from DataStore import db_pool
        async with db_pool.acquire() as conn:
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        f"INSERT INTO strategy_order (symbol, condition1, condition1status, condition2, exids, "
                        "opentime, deleted, endtime, posSide, money, isswap,sl,tp) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s,%s)",
                        (order.symbol, order.condition1, order.condition1status, order.condition2, order.exids, order.opentime,
                         order.deleted, order.endtime, order.posSide, order.money, order.isswap,order.sl,order.tp)
                    )
                    await conn.commit()
                    order.id= cursor.lastrowid
                    return True
            except Exception as e:
                logger.error(
                    f"strategy_order表 insert_strategy_order 插入错误: {e}")
                return False          