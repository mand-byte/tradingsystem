import asyncio
import math
from .SDKBase import SDKBase
import datetime
import aiohttp
import json
from . import OrderClass
import time

class NexoSdk(SDKBase):
    name ='nexo'
    _rest="https://pro-api.nexo.io"
    spot_baseinfo={}
    swap_baseinfo={}
    def __init__(self, api_key: str, api_secret: str, api_password: str = None) -> None:
        super().__init__(api_key, api_secret, api_password)

    async def send_request(self, api):
        headers = {
            "X-API-KEY": self.keyconf['apiKey'],
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        current_time = str(int(time.time() * 1000))
        
        headers['X-NONCE'] = current_time
        headers['X-SIGNATURE']=self.get_sign(self.keyconf['secret'],current_time)
        method = api["method"]
        try:
            if method == "GET":
                params = self.praseParam(api['payload'])
                url = f"{NexoSdk._rest}{api['url']}?{params}" if len(params)>0 else f"{NexoSdk._rest}{api['url']}"
                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url=url, headers=headers) as response:
                        return await response.text()
            elif method == "POST":
                url = f"{NexoSdk._rest}{api['url']}"
                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url=url, json=api['payload'], headers=headers) as response:
                        return await response.text()
        except Exception as e:
            return f'{{"e": "{e}"}}' 

    async def request_baseinfo(self):
        api = {
            "method": "GET",
            "url": "/api/v1/futures/instruments",
            "payload": {
            }
        }
        #现货和合约的api没有最小下单数量的数据，合约只有单位精度和价格精度。
        response = await self.send_request(api)
        result = json.loads(response)
        if isinstance(result, dict) and 'instruments' in result:
            NexoSdk.swap_baseinfo.clear()
            for i in result['instruments']:
                #pricePrecision,amountPrecision
                NexoSdk.swap_baseinfo[i['name']]=i      
        

        api = {
            "method": "GET",
            "url": "/api/v1/pairs",
            "payload": {
            }
        }
        #现货和合约的api没有最小下单数量的数据，合约只有单位精度和价格精度。
        response = await self.send_request(api)
        result = json.loads(response)
        if isinstance(result, dict) and 'min_limits' in result:
            NexoSdk.spot_baseinfo.clear()
            for i in result['min_limits']:
                #pricePrecision,amountPrecision
                NexoSdk.spot_baseinfo[i]=result['min_limits'][i]      
            
    
        
    async def request_spot_price(self,symbol:str,size:float,side:str):
        api = {
            "method": "GET",
            "url": "/api/v1/quote",
            "payload": {
                "pair":symbol,
                'amount':str(size),
                'side':side
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'price' in result:
            return (float(result['price']),)
        else:
            return response
        
    async def request_spot_positions(self):
        api = {
            "method": "GET",
            "url": "/api/v2/accountSummary",
            "payload": {
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if isinstance(result, dict) and 'balances' in result:
            _result = []
            for i in result['balances']:
                total=float(i['total'])
                if total>0:
                    account = OrderClass.AccountInfo()
                    account.available=float(i['available'])
                    account.total=account.available+float(i['lockedFuturePositions'])+float(i['unrealizedPnl'])+float(i['lockedLimits'])
                    account.unrealizedPL=float(i['unrealizedPnl'])
                    account.symbol=i['assetName']
                    _result.append(account)       
            return _result        
        else:
            return response
        
    async def make_spot_order(self, symbol: str, size: float, orderType: int = 0, price: float = 0):
        api = {
            "method": "POST",
            "url": "/api/v1/orders",
            "payload": {
                'pair': symbol,
                'side': 'buy',
                'type': 'market' if orderType == 0 else 'limit',
                'force': 'gtc',
                'quantity': str(size),
            }
        }
        if orderType == 1:
            api['payload']['price'] = str(price)
        response = await self.send_request(api)
        result = json.loads(response)
        if isinstance(result, dict) and 'dealId' in result:
            return (result['dealId'],)
        else:
            return result

    async def cancel_spot_order(self,  orderId: str):
        api = {
            "method": "POST",
            "url": "/api/v1/orders/cancel",
            "payload": {
                'orderID': orderId
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if isinstance(result, dict) and 'errorMessage' in result:
            return response
        else:
            return True

    async def close_spot_order_by_market(self, symbol: str, size: float):
        api = {
            "method": "POST",
            "url": "/api/v1/orders",
            "payload": {
                'pair': symbol,
                'side': 'sell',
                'type': 'market',
                'quantity': str(size),
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if isinstance(result, dict) and 'dealId' in result:
            return (result['dealId'],)
        else:
            return response

    async def set_spot_sltp(self, symbol: str, size: float, sl:float,tp: float):
        api = {
            "method": "POST",
            "url": "/api/v1/orders/advanced",
            "payload": {
                'pair': symbol,
                'side': 'sell',
                'amount': str(size),
                'stopLossPrice': str(sl),
                'takeProfitPrice': str(tp)
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if isinstance(result, dict) and 'dealId' in result:
            return (result['dealId'],)
        else:
            return response

    async def query_spot_order_info(self, orderId: str):
        api = {
            "method": "GET",
            "url": "/api/v3/orderDetails",
            "payload": {
                'orderId': orderId
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)    
        if isinstance(result, dict) and 'orderId' in result:
            oi = OrderClass.OrderInfo()
            oi.status=0 if result['status']=='active' else 1 if result['status']=='completed' else 2 if result['status']=='partially_filled' else -1
            oi.symbol=result['pair']
            oi.size=float(result['quantity'])
            oi.priceAvg = float(result['price']) if len(
                result['price']) > 0 else 0.0
            return oi
        else:
            return response

    async def make_swap_order(self, symbol: str, size: float, posSide: str, orderType: int = 0, price: float = 0):
        api = {
            "method": "POST",
            "url": "/api/v1/futures/order",
            "payload": {
                'instrument': symbol,
                'positionAction':'open',
                'positionSide':posSide,
                'type':'market',
                "quantity":str(size)
            }
        }
        #nexo 暂不支持限价订单
        if 'orderType'==1:
            return 'f"Bad Request: Tried to place future position with type = {type}, must be "market"'
        
        response = await self.send_request(api)
        result = json.loads(response)
        if isinstance(result, dict) and 'dealId' in result:      
            return (result['dealId'],)
        else:
            return response

    async def close_swap_order_by_market(self, symbol: str, size: float, posSide: str):
        api = {
            "method": "POST",
            "url": "/api/v1/futures/order",
            "payload": {
                'instrument': symbol,
                'positionAction':'close',
                'positionSide':posSide,
                'type':'market',
                "quantity":str(size)
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if isinstance(result, dict) and 'dealId' in result:      
            return (result['dealId'],)
        else:
            return response

    async def request_swap_positions(self):
        api = {
            "method": "GET",
            "url": "/api/v1/futures/positions",
            "payload": {
                'status':'active'
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'positions' in result:
            _result = []
            for i in result['positions']:
                sp = OrderClass.SwapPostion()
                sp.leverage = i['leverage']
                sp.symbol = i['instrument']
                sp.posSide = i['side'].lower()
                sp.size = i['amount']
                sp.priceAvg = i['entryPrice']
                sp.upl = float(i['unrealizedPnl'])
                sp.margin=math.fabs(float(i['lockedCollateral']))     
                _result.append(sp)
            return _result
        else:
            return response         

    async def setlever(self,symbol:str,lever:int):
        pass

    @staticmethod
    async def request_swap_price(symbol:str):
        from .BinanceSdk import BinanceSdk
        return await BinanceSdk.request_swap_price(symbol)