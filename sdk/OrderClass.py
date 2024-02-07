import datetime
class OrderInfo:
    def __init__(self, **kwargs) -> None:
        self.symbol = kwargs.get('symbol','')
        self.orderId = kwargs.get('orderId','')
        self.posSide = kwargs.get('posSide','')
        self.size = kwargs.get('size',0)
        self.priceAvg = kwargs.get('priceAvg',0)
        self.tp = kwargs.get('tp',0)
        self.sl = kwargs.get('sl',0)
        self.tp_id = kwargs.get('tp_id','')
        self.sl_id = kwargs.get('sl_id','')
        self.leverage = kwargs.get('leverage',0)
        self.marginMode = kwargs.get('marginMode','')
        self.openTime = kwargs.get('openTime',datetime.datetime.now())
        self.subPosId = kwargs.get('subPosId','')
        self.delete = kwargs.get('delete',False)
        # 0 为全部成交或部分成交 1为 新建订单 -1为无效
        self.status = kwargs.get('status',0)
        self.orderSource = kwargs.get('orderSource','')
        self.tradeSide = kwargs.get('tradeSide','')


class SwapPostion:
    def __init__(self) -> None:
        self.symbol = None
        self.posSide = None
        self.size = 0
        self.margin = None
        self.leverage = 0
        self.upl = 0
        self.priceAvg = 0
        self.marginMode = None
    # def to_json(self):
    #     return {
    #         'symbol':self.symbol,
    #         'posSide':self.posSide,
    #         'size':self.size,
    #         'margin':self.margin,
    #         'leverage':self.leverage,
    #         'upl':self.upl,
    #         'priceAvg':self.priceAvg,
    #         'marginMode':self.marginMode,
    #     } 

class AccountInfo:
    def __init__(self) -> None:
        self.total = 0
        self.available = 0
        self.unrealizedPL = 0
        self.symbol = None
    # def to_json(self):
    #     return {
    #         'symbol':self.symbol,
    #         'unrealizedPL':self.unrealizedPL,
    #         'total':self.total,
    #         'available':self.available
    #     }    
