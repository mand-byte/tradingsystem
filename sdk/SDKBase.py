from hashlib import sha256
import base64
import hmac
import math


class SDKBase:
    def __init__(self, api_key: str, api_secret: str, api_password: str = None) -> None:
        self._cb = {}
        self.swap_copytrader = False
        self.spot_copytrader = False
        self.keyconf = {}
        self.keyconf['apiKey'] = api_key
        self.keyconf['secret'] = api_secret
        self.keyconf['password'] = api_password
        pass

    async def init(self):
        pass
    
    # 返回base64

    def get_sign(self, api_secret: str, payload: str):
        signature = hmac.new(api_secret.encode(
            "utf-8"), payload.encode("utf-8"), digestmod=sha256).digest()
        signature = base64.b64encode(signature).decode('utf-8')
        return signature
    # 返回十六进制字符串

    def get_sign2(self, api_secret: str, payload: str):
        signature = hmac.new(api_secret.encode(
            "utf-8"), payload.encode("utf-8"), digestmod=sha256).hexdigest()
        return signature

    def praseParam(self, paramsMap: dict):
        sortedKeys = sorted(paramsMap)
        paramsStr = "&".join(["{}={}".format(x, paramsMap[x])
                             for x in sortedKeys])
        return paramsStr

    def _custom_round(self, A, B):
        # 确保A和B都是浮点数
        A = float(A)
        B = float(B)

        if A >= 1:
            # 整数情况，将B四舍五入到A的最接近整数倍
            if B < A:
                return A
            tempA = A
            count = 0
            while tempA >= 10:
                tempA = tempA/10
                count = count+1
            c = math.pow(10, count)
            result = int(B/c)*c
            return result
        else:
            decimal_places_a = len(str(A).split('.')[-1])
            # 小数情况，根据A的小数位数，将B的小数部分截断到相同位数，然后返回
            rounded_b = round(B, decimal_places_a)

            return max(rounded_b, A)  # 使用max确保B不小于A

    def count_pos_by_price(self, minQty, money, price, lever=10):
        sz = money/price*lever
        sz = self._custom_round(minQty, sz)
        return sz

    def is_spot_copytrader(self):
        return self.spot_copytrader

    def is_swap_copytrader(self):
        return self.swap_copytrader
    # async def set_lever(self, lever: int, symbol: str):
    #     pass

    # def reg_event(self, event_name: str, callback):
    #     self._cb[event_name] = callback
    #     pass
    # # 现货下单   orderType =0 market, =1 limit

    # async def make_spot_order(self, symbol: str, size: float, orderType: int = 0, price: float = 0, sl: float = 0, tp: float = 0):
    #     pass
    # # 现货市价平仓

    # async def close_spot_order_by_market(self, symbol: str, size: float):
    #     pass
    # # 带单现货平仓
    # async def close_spot_order_by_copytrader(self,symbol:str,subPosId:str):
    #     pass

    # # 现货订单查询

    # async def query_spot_order_info(self, symbol: str, orderId: str):
    #     pass
    # # 现货订单取消

    # async def cancel_spot_order(self, symbol: str, orderId: str):
    #     pass
    # async def request_swap_price(self,symbol):
    #     pass
    # async def request_spot_price(self,symbol):
    #     pass
    # # 合约下单
    # async def make_swap_order(self, symbol: str, size: float,posSide: str, orderType: int = 0, price: float = 0, sl: float = 0, tp: float = 0):
    #     pass
    # # 合约市价平仓

    # async def close_swap_order_by_market(self, symbol: str, size: str, posSide: str):
    #     pass
    #  # 带单合约平仓
    # async def close_swap_order_by_copytrader(self,subPosId:str):
    #     pass

    # #去掉订单
    # async def cancel_swap_order(self, symbol: str, orderId: str):
    #     pass
    # # 合约止盈止损

    # async def set_swap_sl_tp(self, symbol: str, size: float, posSide: str, sl: float = 0, tp: float = 0):
    #     pass

    # # 合约订单查询

    # async def query_swap_order_info(self, symbol: str, orderId: str):
    #     pass

    # #现货持仓总览
    # async def request_spot_positions(self):
    #     pass
    # #合约账户总览
    # async def request_swap_account(self):
    #     pass
    # #合约持仓总览
    # async def request_swap_positions(self):
    #     pass
    # #请求现货当前带单信息
    # async def request_spot_subpositions(self,symbol:str):
    #     pass
    # #请求合约当前带单信息
    # async def request_swap_subpositions(self,symbol:str):
    #     pass
