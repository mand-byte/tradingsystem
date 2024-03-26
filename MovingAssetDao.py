from log import logger
class MovingAssetDB():    
    def __init__(self, **kwargs):
        self.id = kwargs.get('id',0)
        self.exid=kwargs.get('exid',0)
        self.datetime = kwargs.get('datetime','')
        self.money = kwargs.get('money',0)
        self.transid = kwargs.get('transid','')
        self.isdelete = kwargs.get('isdelete',False)
    def  to_json(self):
        return {
            "id": self.id,
            "exid": self.exid,
            "datetime": self.datetime,
            "money": self.money,
            'transid':self.transid,
        }
    
async def MovingAssetDB_query(exid):
    from DataStore import db_pool
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                query = "SELECT * FROM moving_asset_info WHERE exid = %s AND isdelete = 0 ORDER BY datetime DESC LIMIT 1"
                await cursor.execute(query, (exid,))
                row = await cursor.fetchone()
                if row:
                    columns = [column[0] for column in cursor.description]
                    return MovingAssetDB(**dict(zip(columns, row)))
                else:
                    return None
    except Exception as e:
        logger.error(f"moving_asset_info 表 query 查询错误 : {e}")          
            
async def MovingAssetDB_Insert(info: MovingAssetDB):
    from DataStore import db_pool
    insert_query = (
        "INSERT INTO moving_asset_info (exid, datetime, money, isdelete,transid)"
        "VALUES (%s, %s, %s, %s, %s)"
    )

    parameters = (
        info.exid, info.datetime, info.money,  info.isdelete,info.transid
    )
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(insert_query, parameters)
                info.id = cursor.lastrowid
                if cursor.rowcount > 0:
                    return info
    except Exception as e:
        logger.error(f"moving_asset_info 表 Insert 更新错误 : {e} info={info.to_json()}")

async def MovingAssetDB_Update(info: MovingAssetDB):
    from DataStore import db_pool
    query = (
        "UPDATE moving_asset_info SET exid=%s, datetime=%s, money=%s, isdelete=%s, transid=%s WHERE id=%s"
    )

    parameters = (
        info.exid, info.datetime, info.money, info.isdelete,info.transid, info.id
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
        logger.error(f"moving_asset_info 表 update 更新错误 : {e}")  