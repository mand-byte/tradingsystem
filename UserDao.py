# from sqlalchemy import Column, Integer, String, and_
# from Datebase import OrmBase, AsyncSession, engine
# from sqlalchemy.future import select
from log import logger




# class UserDB(OrmBase):
#     __tablename__ = "user"
#     id = Column(Integer, primary_key=True,
#                 nullable=False, autoincrement='auto')
#     account = Column('account', String(255), nullable=False, comment='账号')
#     password = Column('password', String(255), nullable=False, comment='密码')
#     privilege = Column('privilege', Integer(),
#                        nullable=False, comment='1为只读,2为可读可写')

class UserDB:
    def __init__(self, id, account, password, privilege):
        self.id = id
        self.account = account
        self.password = password
        self.privilege = privilege
# async def UserDB_query(account: str, password: str):
#     async with AsyncSession() as session:
#         try:
#             # 开始数据库事务
#             stmt = select(UserDB).filter(and_(
#                     UserDB.account == account, UserDB.password == password))
#             result= await session.execute(stmt)
#             return result.scalars().first()
#         except Exception as e:
#             # 处理异常
#             logger.error(f"UserDB 表 Query 查询错误 : {e}")
#         finally:
#             session.expunge_all()    
async def UserDB_query( account: str, password: str):
    from DataStore import db_pool
    async with db_pool.acquire() as conn:
        try:
            async with conn.cursor() as cursor:
                await cursor.execute(
                    "SELECT * FROM user WHERE account = %s AND password = %s",
                    (account, password)
                )
                result = await cursor.fetchone()
                if result:
                    return UserDB(*result)
        except Exception as e:
            logger.error(f"UserDB 表 Query 查询错误 : {e}")