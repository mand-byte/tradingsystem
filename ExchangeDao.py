#from sqlalchemy import Boolean, Column, Integer, String, and_
# from Database import pool,create_pool
from log import logger


class ExchangeDb:
    def __init__(self, **kwargs):
        self.id =kwargs.get('id',0)
        self.ex = kwargs.get('ex','')
        self.account = kwargs.get('account','')
        self.apikey = kwargs.get('apikey','')
        self.api_secret = kwargs.get('api_secret','')
        self.api_password = kwargs.get('api_password','')
        self.deleted = kwargs.get('deleted',False)
    def to_json(self):
        return {
            "id": self.id,
            "ex": self.ex,
            "account": self.account,
            'deleted':self.deleted
        }
async def insert(db:ExchangeDb):
    from DataStore import db_pool
    insert_query = (
        "INSERT INTO exchange_info (ex, account, apikey, api_secret, api_password, deleted) "
        "VALUES (%s, %s, %s, %s, %s, %s)"
    )
    parameters = (
        db.ex, db.account, db.apikey, db.api_secret, db.api_password, db.deleted
    )
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(insert_query, parameters)
                db.id = cursor.lastrowid
                if cursor.rowcount > 0:
                    return db
    except Exception as e:
        logger.error(f"exchange_info 表 Insert 更新错误 : {e} info={db.to_json()}")        

async def del_physical(id:int):
    from DataStore import db_pool
    delete_query = "DELETE FROM exchange_info WHERE id = %s"
    parameters = (id,)
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(delete_query, parameters)
                if cursor.rowcount > 0:
                    return True
    except Exception as e:
        logger.error(f"exchange_info 表物理删除错误: {e} id={id}")
        return False

async def delete_soft(id: int):
    from DataStore import db_pool
    update_query = "UPDATE exchange_info SET deleted = 1 WHERE id = %s"
    parameters = (id,)
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(update_query, parameters)
                if cursor.rowcount > 0:
                    return True
    except Exception as e:
        logger.error(f"exchange_info 表软删除错误: {e} id={id}")
        return False

async def restore(id: int):
    from DataStore import db_pool
    update_query = "UPDATE exchange_info SET deleted = 0 WHERE id = %s"
    parameters = (id,)
    
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(update_query, parameters)
                if cursor.rowcount > 0:
                    return True
    except Exception as e:
        logger.error(f"exchange_info 表软删除错误: {e} id={id}")
        return False    

async def exchange_db_query(all:bool=False):
    from DataStore import db_pool
    async with db_pool.acquire() as conn:
        try:
            async with conn.cursor() as cursor:
                # 异步查询
                if all:
                    await cursor.execute("SELECT * FROM exchange_info")
                    result = await cursor.fetchall()
                    columns = [column[0] for column in cursor.description]
                    return [ExchangeDb(**dict(zip(columns, row))) for row in result]
                else:   
                    await cursor.execute("SELECT * FROM exchange_info WHERE deleted = 0")
                    result = await cursor.fetchall()
                    columns = [column[0] for column in cursor.description]
                    return [ExchangeDb(**dict(zip(columns, row))) for row in result]
        except Exception as e:
            # 处理异常
            logger.error(f"ExchangeDb 表 Query 查询错误 : {e}")