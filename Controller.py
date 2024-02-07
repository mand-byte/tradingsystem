from ExchangeDao import ExchangeDb
from OrderInfoDao import OrderInfoDB
#from SLTPMarketDao import SLTPMarketDB


class Controller:
    def __init__(self, db: ExchangeDb) -> None:
        pass

    async def init(self):
        pass
    def cancel_job(self):
        pass
    #账户转移
    async def transfer(self, fromType: int, toType: int, usdt: float):
        pass
    async def setlever(self,symbol:str,lever:int):
        pass
    #合约开单
    #sltp_type:int 0为仓位止盈止损 1为订单止盈止损 orderType 0 为市价 1 为限价
    async def make_swap_order(self, symbol: str, money: float, posSide: str, price: float, orderType: int,sl:float,tp:float,sltp_type:int,orderFrom:str)->OrderInfoDB:
        pass
    #通过订单手动平仓或关闭订单
    async def close_swap_by_order(self, id:int)->bool:
        pass
    #通过仓位手动全部平仓
    async def close_swap_by_pos(self, symbol:str, posSide:str)->bool:
        pass
    # #设置仓位的止盈止损
    async def set_swap_sltp_by_pos(self,symbol:str,posSide:str,sl: float,tp: float)->bool:#SLTPMarketDB:
        pass
    #设置订单的止盈止损
    async def set_swap_sltp_by_order(self,id:int,sl: float,tp: float)->OrderInfoDB:
        pass

    async def make_spot_order(self, symbol: str, money: float, price: float, orderType: int,sl:float,tp:float,sltp_type:int,orderFrom:str)->OrderInfoDB:
        pass 
    async def close_spot_by_order(self, id:int)->bool:
        pass
    async def close_spot_by_pos(self, symbol:str)->bool:
        pass 
    async def set_spot_sltp_by_pos(self,symbol:str,sl: float,tp: float)->bool:#SLTPMarketDB:
        pass
    async def set_spot_sltp_by_order(self,id:int,sl: float,tp: float)->OrderInfoDB:
        pass
    def get_tv_huoxing_swap_count(self)->int:
        pass