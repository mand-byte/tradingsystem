from log import logger
class SLTPMarketDB:
    def __init__(self, **kwargs) -> None:
        self.id=kwargs.get('id',0)
        self.exId=kwargs.get('exId',0)
        self.isdelete=kwargs.get('isdelete',False)
        self.isswap=kwargs.get('isswap',True)
        self.symbol=kwargs.get('symbol','')
        self.sl=kwargs.get('sl',0)
        self.tp=kwargs.get('tp',0)
        self.sl_id=kwargs.get('sl_id','')
        self.tp_id=kwargs.get('tp_id','')
        self.posSide=kwargs.get('posSide','')
    def to_json(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "exId": self.exId,
            "posSide": self.posSide,
            "tp": self.tp,
            "sl": self.sl,
            "isswap": self.isswap,
            "isdelete": self.isdelete,
            "sl_id": self.sl_id,
            "tp_id": self.tp_id
        }     
async def SLTPMarketDB_Insert(info: SLTPMarketDB):
    from DataStore import db_pool
    insert_query = (
        "INSERT INTO sltp_market (exId, isdelete, isswap, symbol, sl, tp, sl_id, sl_id, posSide)"
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )

    parameters = (
        info.exId, info.isdelete, info.isswap, info.symbol, info.sl, info.tp, info.sl_id,
        info.tp_id, info.posSide
    )
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(insert_query, parameters)
                info.id = cursor.lastrowid
                if cursor.rowcount > 0:
                    return info
    except Exception as e:
        logger.error(f"sltp_market 表 Insert 更新错误 : {e} info={info.to_json()}")

async def SLTPMarketDB_update(info: SLTPMarketDB):
    from Database import pool
    query = (
        "UPDATE sltp_market SET exId=%s, isdelete=%s, isswap=%s, symbol=%s, sl=%s, tp=%s, "
        "sl_id=%s, tp_id=%s, posSide=%s WHERE id=%s"
    )

    parameters = (
        info.exId, info.isdelete, info.isswap, info.symbol, info.sl, info.tp, info.sl_id,
        info.tp_id, info.posSide, info.id
    )
    await execute_query(pool, query, parameters)

async def SLTPMarketDB_Query_All():
    from Database import pool
    query = "SELECT * FROM sltp_market WHERE sltp_market.delete = 0"
    async with pool.acquire() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(query)
                result = await cursor.fetchall()
                columns = [column[0] for column in cursor.description]
                objects = [SLTPMarketDB(**dict(zip(columns, row))) for row in result]
                return objects
        except Exception as e:
            logger.error(f"sltp_market 表 Query 查询错误 : {e}")    
async def execute_query(pool, query, parameters=None):
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, parameters)
                if query.lower().startswith('select'):
                    return await cursor.fetchall() 
    except Exception as e:
        logger.error(f"sltp_market 表 update 更新错误 : {e}")       