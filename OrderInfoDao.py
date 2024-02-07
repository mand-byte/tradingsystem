import json
from typing import Iterable
from sdk.OrderClass import OrderInfo
# from sqlalchemy.future import select
# from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, and_
from log import logger
# from Datebase import OrmBase, AsyncSession, engine
# OrmBase.metadata.create_all(engine)
# from Database import pool

class OrderInfoDB(OrderInfo):
    # __tablename__ = "order_info"

    # id = Column(Integer, primary_key=True,
    #             nullable=False, autoincrement='auto')
    # symbol = Column('symbol', String(255), nullable=False, comment='交易对名')
    # exId = Column('ex', Integer(), nullable=False, comment='交易所Id')
    # orderId = Column('orderId', String(255), nullable=False, comment='订单id')
    # posSide = Column('posSide', String(255), nullable=False, comment='方向')
    # size = Column('size', Float(), nullable=True, comment='头寸大小')
    # size_exec = Column('size_exec', Float(), nullable=True, comment='已成交的头寸')
    # priceAvg = Column('priceAvg', Float(), nullable=True, comment='均价')
    # tp = Column('tp', Float(), nullable=True, comment='止盈位')
    # tp_id = Column('tp_id', String(255), nullable=True, comment='止盈Id')
    # sl = Column('sl', Float(), nullable=True, comment='止损位')
    # sl_id = Column('sl_id', String(255), nullable=True, comment='止损Id')
    # leverage = Column('leverage', Integer(), nullable=True, comment='杠杆')
    # isswap = Column('isswap', Boolean(), nullable=False, comment='是否是合约')
    # marginMode = Column('marginMode', String(
    #     255), nullable=True, comment='保证金模式')
    # openTime = Column('openTime', DateTime, nullable=True, comment='下单时间')
    # subPosId = Column('subPosId', String(255), nullable=True, comment='带单id')
    # delete = Column('delete', Boolean(), nullable=True, comment='删除')
    # # 0 为全部成交或部分成交 0为 新建订单 -1为无效,1为完全 2为部分
    # status = Column('status', Integer(), nullable=True, comment='状态')
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.isswap=kwargs.get('isswap',True)
        self.size_exec=kwargs.get('size_exec',0)
        self.exId=kwargs.get('ex',0)
        self.id=kwargs.get('id',0)
        self.orderFrom=kwargs.get('orderFrom','')
        self.orderType=kwargs.get('orderType',0)
        #0未设止盈止损1未生效2已生效
        self.sltp_status=kwargs.get('sltp_status',0)
    def to_json(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "ex": self.exId,
            "posSide": self.posSide,
            "size": self.size,
            "size_exec": self.size_exec,
            "priceAvg": self.priceAvg,
            'isswap': self.isswap,
            "tp": self.tp,
            "sl": self.sl,
            "leverage": self.leverage,
            "marginMode": self.marginMode,
            "openTime": self.openTime.strftime("%Y-%m-%d %H:%M:%S"),
            "status": self.status,
            'orderFrom':self.orderFrom,
            'orderType':self.orderType,
            'sltp_status':self.sltp_status
        }

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return isinstance(other,OrderInfoDB) and self.id == other.id

async def OrderInfoDB_Insert(info: OrderInfoDB):
    from DataStore import db_pool
    insert_query = (
        "INSERT INTO order_info (symbol, ex, orderId, posSide, size, size_exec, priceAvg, tp, sl, "
        "leverage, isswap, marginMode, openTime, subPosId, `delete`, status, sl_id, tp_id,orderFrom,orderType,sltp_status) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s,%s,%s,%s,%s)"
    )

    parameters = (
        info.symbol, info.exId, info.orderId, info.posSide, info.size, info.size_exec, info.priceAvg,
        info.tp, info.sl, info.leverage, info.isswap, info.marginMode, info.openTime,
        info.subPosId, info.delete, info.status,info.sl_id,info.tp_id,info.orderFrom,info.orderType,info.sltp_status
    )
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(insert_query, parameters)
                info.id = cursor.lastrowid
                if cursor.rowcount > 0:
                    return info
    except Exception as e:
        logger.error(f"order_info 表 Insert 更新错误 : {e} info={info.to_json()}")            
# async def OrderInfoDB_Insert(info: OrderInfoDB):
#     async with AsyncSession() as session:
#         try:
#             # 开始数据库事务
#             if isinstance(info, Iterable):
#                 [session.add(o) for o in info]
#             elif isinstance(info, OrderInfoDB):
#                 session.add(info)
#             await session.commit()
#         except Exception as e:
#             # 处理异常
#             logger.error(f"order_info 表 Insert 更新错误 : {e}")
#         # finally:
#         #     session.expunge_all()      
        


# async def OrderInfoDB_Query_All():
#     async with AsyncSession() as session:
#         try:
#         # 开始数据库事务
#             stmt = select(OrderInfoDB).filter(and_(
#                 OrderInfoDB.delete == False))
#             result=await session.execute(stmt)
#             return result.scalars().all()
#         except Exception as e:
#             # 处理异常
#             logger.error(f"order_info 表 Query 查询错误 : {e}")
#         # finally:
#         #     session.expunge_all()      
        
async def OrderInfoDB_Query_All():
    from DataStore import db_pool
    query = "SELECT * FROM order_info WHERE order_info.delete = 0"
    async with db_pool.acquire() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(query)
                result = await cursor.fetchall()
                columns = [column[0] for column in cursor.description]
                objects = [OrderInfoDB(**dict(zip(columns, row))) for row in result]
                return objects
        except Exception as e:
            logger.error(f"order_info 表 Query 查询错误 : {e}")

# async def OrderInfoDB_Update(ori):
#     async with AsyncSession() as session:
#         try:
#             # 开始数据库事务
#             if isinstance(ori, Iterable):
#                 [session.add(o) for o in ori]
#             elif isinstance(ori, OrderInfoDB):
#                 session.add(ori)
#             await session.commit()
#         except Exception as e:
#             # 处理异常
#             logger.error(f"order_info 表 update 更新错误 : {e}")
#         # finally:
#         #     session.expunge_all()      
        
async def OrderInfoDB_Update(info: OrderInfoDB):
    from DataStore import db_pool
    query = (
        "UPDATE order_info SET symbol=%s, ex=%s, orderId=%s, posSide=%s, size=%s, size_exec=%s, "
        "priceAvg=%s, tp=%s, sl=%s, leverage=%s, isswap=%s, marginMode=%s, openTime=%s, "
        "subPosId=%s, `delete`=%s, status=%s ,sl_id=%s,tp_id=%s,orderFrom=%s,orderType=%s,sltp_status=%s WHERE id=%s"
    )

    parameters = (
        info.symbol, info.exId, info.orderId, info.posSide, info.size, info.size_exec, info.priceAvg,
        info.tp, info.sl, info.leverage, info.isswap, info.marginMode, info.openTime,
        info.subPosId, info.delete, info.status,info.sl_id,info.tp_id,info.orderFrom,info.orderType,info.sltp_status, info.id
    )

    await execute_query(db_pool, query, parameters)

async def execute_query(pool, query, parameters=None):
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, parameters)
                if query.lower().startswith('select'):
                    return await cursor.fetchall() 
    except Exception as e:
        logger.error(f"order_info 表 update 更新错误 : {e}")            