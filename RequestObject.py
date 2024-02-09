from typing import List, Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str

class CancelOrderRequest(BaseModel):
    orderID:int
class ClosePosRequest(BaseModel):
    exId:int
    symbol:str
    isswap:bool
    posSide:str
class MakeOrderRequest(BaseModel):
    exid: int
    symbol: str
    money: float #投入金额
    isswap: bool  # true 为swap false为spot
    posSide: bool  # true 为long false为short
    orderType: bool  # true为limit false为market
    price: float #标的价格
    sl: float
    tp: float
    sltp_type:int #0为仓位止盈止损 1 为订单止盈止损

class ModifySlTp(BaseModel):
    exid: Optional[int] = None
    id:Optional[int] = None
    symbol:Optional[str] = None
    posSide:Optional[bool] = None  # true 为long false为short
    isswap:Optional[bool] = None
    sl: float
    tp: float

class StrategyOrderRequest(BaseModel):
    symbol:str
    condition1:float
    condition2:float
    exids:List[int]
    endtime:int
    posSide:bool# true 为long false为short
    money:float
    isswap:bool# true 为swap false为spot
    sl:float
    tp:float
class CloseStrategyOrder(BaseModel):
    id:int

class TvNotificationRequest(BaseModel):
    ticker:str
    ex:str
    close:Optional[str] = None
    open:Optional[str] = None
    high:Optional[str] = None
    low:Optional[str] = None
    time:Optional[str] = None
    volume:Optional[str] = None
    timenow:Optional[str] = None
    interval:str
    position_size:str
    action:str
    contracts: Optional[str] = None
    price:str
    id:str
    market_position: Optional[str] = None
    market_position_size:Optional[str] = None
    prev_market_position:Optional[str] = None
    prev_market_position_size:Optional[str] = None
    comment:str
    tv_type:str

class AddExRequest(BaseModel):
    ex:str
    account:str
    apikey:str
    api_secret:str
    api_password:str

class SetExStatusRequest(BaseModel):
    id:int
    #false为禁用 true为物理删除 
    status:int

class SetExSingalRequest(BaseModel):
    id:int
    
    no_open:int
    no_close:int

class SetMartinRequest(BaseModel):
    use_ratio:bool
    ratio:Optional[float]
    fixed:Optional[List[float]]
    max_count:int
    except_num:int 

class SetTrendRequest(BaseModel):
    use_ratio:bool
    num:float
    tp:float

class SetTGRequest(BaseModel):
    TG_report_err:bool
    TG_report_open:bool
    TG_report_close:bool

class SetLeverageRequest(BaseModel):
    leverage: int