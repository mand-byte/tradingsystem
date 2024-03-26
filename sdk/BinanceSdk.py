import asyncio
import math
from .SDKBase import SDKBase
import datetime
import aiohttp
import json
from . import OrderClass


class BinanceSdk(SDKBase):
    name = 'binance'
    _rest = "https://fapi.binance.com"
    spot_baseinfo = {}
    swap_baseinfo = {}

    def __init__(self, api_key: str, api_secret: str, api_password: str = None) -> None:
        super().__init__(api_key, api_secret, api_password)

    @staticmethod
    def register_spot_kline(symbol: str, cb):
        if symbol in BinanceSdk.spot_baseinfo:
            return True
        return False
    swap_reg = set()
    spot_reg = set()

    @staticmethod
    def caculate_swap_url():
        pass

    @staticmethod
    def unregister_spot_kline(symbol: str):
        pass

    @staticmethod
    def register_swap_kline(symbol: str):
        if symbol in BinanceSdk.swap_baseinfo:
            if symbol not in BinanceSdk.swap_reg:
                BinanceSdk.swap_reg.add(symbol)
            return True
        return False

    @staticmethod
    def unregister_swap_kline(symbol: str):
        if symbol in BinanceSdk.swap_reg:
            BinanceSdk.swap_reg.remove(symbol)
        pass

    @staticmethod
    def run_kline_ws():
        pass

    @staticmethod
    def stop_kline_ws():
        pass

    async def send_request(self, api):
        headers = {
            "X-MBX-APIKEY": self.keyconf['apiKey'],
            "Accept": "application/json"
        }
        current_time = str(int(datetime.datetime.now().timestamp()*1000))

        method = api["method"]
        params = f"{self.praseParam(api['payload'])}&timestamp={current_time}"

        sign_str = self.get_sign2(
            self.keyconf['secret'], params)
        url = f"{BinanceSdk._rest if 'rest' not in api else api['rest']}{api['url']}?{params}&signature={sign_str}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url=url, headers=headers) as response:
                    return await response.text()
        except Exception as e:
            return f'{{"e": "{e}"}}'

    @staticmethod
    async def request_baseinfo():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request("GET", url=f"{BinanceSdk._rest}/fapi/v1/exchangeInfo") as response:
                    result = await response.text()
                    result = json.loads(result)
                    if 'symbols' in result:
                        data = result['symbols']
                        BinanceSdk.swap_baseinfo.clear()
                        for d in data:
                            if d['status'] == 'TRADING' and d['contractType'] == 'PERPETUAL':
                                for f in d['filters']:
                                    if f['filterType'] == 'MARKET_LOT_SIZE':
                                        BinanceSdk.swap_baseinfo[d['symbol']] = float(
                                            f['minQty'])
                                        break
        except Exception as e:
            print(f'binance request_baseinfo swap err={e}')
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request("GET", url=f"https://api4.binance.com/api/v3/exchangeInfo") as response:
                    result = await response.text()
                    result = json.loads(result)
                    if 'symbols' in result:
                        data = result['symbols']
                        BinanceSdk.spot_baseinfo.clear()
                        for d in data:
                            if d['status'] == 'TRADING':
                                for f in d['filters']:
                                    if f['filterType'] == 'LOT_SIZE':
                                        BinanceSdk.spot_baseinfo[d['symbol']] = float(
                                            f['minQty'])
                                        break
        except Exception as e:
            print(f'binance request_baseinfo spot err={e}')

    async def request_swap_positions(self, symbol=None):
        api = {
            "method": "GET",
            "url": "/fapi/v2/positionRisk",
            "payload": {
            }
        }
        if isinstance(symbol, str):
            api['payload']['symbol'] = symbol
        response = await self.send_request(api)
        result = json.loads(response)
        if isinstance(result, list):
            _result = []
            for i in result:
                if float(i['positionAmt']) != 0:
                    sp = OrderClass.SwapPostion()
                    sp.leverage = int(i['leverage'])
                    sp.symbol = i['symbol']
                    sp.posSide = i['positionSide'].lower()
                    sp.size = math.fabs(float(i['positionAmt']))
                    sp.priceAvg = float(i['entryPrice'])
                    sp.upl = float(i['unRealizedProfit'])
                    sp.marginMode = i['marginType']
                    if sp.marginMode == 'cross':
                        sp.margin = math.fabs(
                            float(i['notional'])/int(i['leverage']))
                    else:
                        sp.margin = math.fabs(float(i['isolatedMargin']))
                    _result.append(sp)
            return _result
        else:
            return result

    @staticmethod
    async def request_swap_price(symbol):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request("GET", url=f"https://fapi.binance.com/fapi/v2/ticker/price?symbol={symbol}") as response:
                    result = await response.text()
                    result = json.loads(result)
                    if "price" in result:
                        return float(result['price'])
                    return response
        except Exception as e:
            return f'{{"e": "{e}"}}'

    @staticmethod
    async def request_spot_price(symbol):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request("GET", url=f"https://api4.binance.com/api/v3/ticker/price?symbol={symbol}") as response:
                    result = await response.text()
                    result = json.loads(result)
                    if "price" in result:
                        return float(result['price'])
                    return response
        except Exception as e:
            return f'{{"e": "{e}"}}'

    async def request_swap_account(self):
        api = {

            "method": "GET",
            "url": "/fapi/v2/account",
            "payload": {
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'feeTier' in result:
            ai = OrderClass.AccountInfo()
            ai.total = float(result['totalMarginBalance'])
            ai.unrealizedPL = float(result['totalUnrealizedProfit'])
            ai.available = float(result['availableBalance'])

            return ai
        else:
            return response

    # 查询合约订单信息 status:FILLED NEW

    async def query_swap_order_info(self, symbol: str, orderId: str):
        api = {
            "method": "GET",
            "url": "/fapi/v1/order",
            "payload": {
                'symbol': symbol,
                'orderId': int(orderId)
            }
        }
        response = await self.send_request(api)
        json_data = json.loads(response)
        if 'orderId' in json_data:
            soi = OrderClass.OrderInfo()
            soi.openTime = datetime.datetime.fromtimestamp(
                float(json_data['time']) / 1000.0)
            soi.symbol = symbol
            soi.orderId = str(json_data['orderId'])
            soi.posSide = json_data['positionSide'].lower()

            if json_data['status'] == 'FILLED':
                soi.status = 1
                soi.size = float(json_data['executedQty'])
                soi.priceAvg = float(json_data['avgPrice'])
            elif json_data['status'] == 'PARTIALLY_FILLED':
                soi.status = 2
                soi.size = float(json_data['executedQty'])
                soi.priceAvg = float(json_data['avgPrice'])
            elif json_data['status'] == 'NEW':
                soi.status = 0
                soi.priceAvg = 0
            else:
                soi.status = -1
            return soi
        else:
            return response

 # 合约下单 合约的止盈止损跟合约下单一样，因此修改合约的止盈止损就是删除再重设
    async def make_swap_order(self, symbol: str, size: float, posSide: str, orderType: int = 0, price: float = 0):

        api = {
            "method": "POST",
            "url": "/fapi/v1/order",
            "payload": {
                'symbol': symbol,
                'side': 'BUY' if posSide == 'long' else 'SELL',
                'positionSide': posSide.upper(),
                'type': 'MARKET' if orderType == 0 else 'LIMIT',
                'quantity': size
            }
        }
        if orderType == 1:
            api['payload']['timeInForce'] = 'GTC'
            api['payload']['price'] = price
        response = await self.send_request(api)
        json_data = json.loads(response)
        if 'orderId' in json_data:
            return (str(json_data['orderId']),)
        return response

    async def set_swap_sl(self, symbol: str, size: float, posSide: str, sl: float, ispos: bool):
        api = {
            "method": "POST",
            "url": "/fapi/v1/order",
            "payload": {
                'symbol': symbol,
                'side': 'SELL' if posSide == 'long' else 'BUY',
                'positionSide': posSide.upper(),
                'stopPrice': sl,
                'timeInForce': 'GTC'
            }
        }
        if ispos:
            api['payload']['type'] = 'STOP_MARKET'
        else:
            api['payload']['type'] = 'STOP'
            api['payload']['quantity'] = size
            api['payload']['price'] = sl
        response = await self.send_request(api)
        json_data = json.loads(response)
        if 'orderId' in json_data:
            return (str(json_data['orderId']),)
        return response

    async def set_swap_tp(self, symbol: str, size: float, posSide: str, tp: float, ispos: bool):
        api = {
            "method": "POST",
            "url": "/fapi/v1/order",
            "payload": {
                'symbol': symbol,
                'side': 'SELL' if posSide == 'long' else 'BUY',
                'positionSide': posSide.upper(),
                'quantity': size,
                'stopPrice': tp,
                'price': tp,
                'timeInForce': 'GTC'
            }
        }
        if ispos:
            api['payload']['type'] = 'TAKE_PROFIT_MARKET'
        else:
            api['payload']['type'] = 'TAKE_PROFIT'
            api['payload']['quantity'] = size
            api['payload']['price'] = tp

        response = await self.send_request(api)
        json_data = json.loads(response)
        if 'orderId' in json_data:
            return (str(json_data['orderId']),)
        return response

    # 取消合约订单

    async def cancel_swap_order(self, symbol: str, orderId: str):
        api = {
            "method": "DELETE",
            "url": "/fapi/v1/order",
            "payload": {
                'symbol': symbol,
                'orderId': int(orderId),
            }
        }
        response = await self.send_request(api)
        json_data = json.loads(response)
        if 'status' in json_data and json_data['status'] == 'CANCELED':
            return True
        return response
    # 市价平合约

    async def close_swap_order_by_market(self, symbol: str, size: float, posSide: str):
        api = {
            "method": "POST",
            "url": "/fapi/v1/order",
            "payload": {
                'symbol': symbol,
                'side': 'BUY' if posSide == 'short' else 'SELL',
                'positionSide': posSide.upper(),
                'type': 'MARKET',
                'quantity': size
            }
        }
        response = await self.send_request(api)
        json_data = json.loads(response)
        if 'orderId' in json_data:
            return (json_data['orderId'],)
        else:
            return response

    # 取消现货订单
    async def cancel_spot_order(self, symbol: str, orderId: str):
        api = {
            'rest': "https://api.binance.com",
            "method": "DELETE",
            "url": "/api/v3/order",
            "payload": {
                'symbol': symbol,
                'orderId': int(orderId),
            }
        }
        response = await self.send_request(api)
        json_data = json.loads(response)
        if 'orderId' in json_data:
            return True
        else:
            return response
    # 创建现货订单

    async def make_spot_order(self, symbol: str, size: float, orderType: int = 0, price: float = 0, sl: float = 0, tp: float = 0):
        api = {
            'rest': "https://api.binance.com",
            "method": "POST",
            "url": "/api/v3/order",
            "payload": {
                'symbol': symbol,
                'side': 'BUY',
                'type': 'MARKET' if orderType == 0 else 'LIMIT',
                # //usdt 数量
                'quantity': size
            }
        }
        if orderType == 1:
            api['payload']['timeInForce'] = 'GTC'
            api['payload']['price'] = price
        response = await self.send_request(api)
        json_data = json.loads(response)
        if 'orderId' in json_data:
            orderId = json_data['orderId']

            return orderId
        else:
            return response
    # 现货设置止盈止损

    async def set_spot_sl(self, symbol: str, size: float, sl: float):
        api = {
            'rest': "https://api.binance.com",
            "method": "POST",
            "url": "/api/v3/order",
            "payload": {
                    'symbol': symbol,
                    'side': 'SELL',
                    'type': 'STOP_LOSS',
                    'quantity': size,
                    'stopPrice': sl,
                    'timeInForce': 'GTC'
            }
        }

        response = await self.send_request(api)
        json_data = json.loads(response)
        if 'orderId' in json_data:
            return (str(json_data['orderId']),)
        return response

    async def set_spot_tp(self, symbol: str, size: float, tp: float):
        api = {
            'rest': "https://api.binance.com",
            "method": "POST",
            "url": "/api/v3/order",
            "payload": {
                    'symbol': symbol,
                    'side': 'SELL',
                    'type': 'TAKE_PROFIT',
                    'quantity': size,
                    'stopPrice': tp,
                    'timeInForce': 'GTC'
            }
        }
        response = await self.send_request(api)
        json_data = json.loads(response)
        if 'orderId' in json_data:
            return (str(json_data['orderId']),)
        return response

    # 现货市价平仓
    async def close_spot_order_by_market(self, symbol: str, size: float):
        api = {
            'rest': "https://api.binance.com",
            "method": "POST",
            "url": "/api/v3/order",
            "payload": {
                'symbol': symbol,
                'side': 'SELL',
                'type': 'MARKET',
                'quantity': size
            }
        }
        response = await self.send_request(api)
        json_data = json.loads(response)
        if 'orderId' in json_data:
            return True
        else:
            return response

    # 现货订单查询

    async def query_spot_order_info(self, symbol: str, orderId: str):
        api = {
            'rest': "https://api.binance.com",
            "method": "GET",
            "url": "/api/v3/order",
            "payload": {
                'symbol': symbol,
                'orderId': int(orderId)
            }
        }
        response = await self.send_request(api)
        json_data = json.loads(response)
        if 'orderId' in json_data:
            soi = OrderClass.OrderInfo()
            soi.openTime = datetime.datetime.fromtimestamp(
                float(json_data['time']) / 1000.0)
            soi.symbol = symbol
            soi.orderId = str(json_data['orderId'])
            soi.priceAvg = float(json_data['price'])
            soi.size = float(json_data['executedQty'])
            if json_data['status'] == 'FILLED':
                soi.status = 1
            elif json_data['status'] == 'PARTIALLY_FILLED':
                soi.status = 2
            elif json_data['status'] == 'NEW':
                soi.status = 0
            else:
                soi.status = -1
            return soi
        else:
            return response

    # 查询现货总仓位
    async def request_spot_positions(self, symbol=None):
        api = {
            'rest': "https://api.binance.com",
            "method": "POST",
            "url": "/sapi/v3/asset/getUserAsset",
            "payload": {
            }
        }
        if isinstance(symbol, str):
            api['payload']['asset'] = symbol
        response = await self.send_request(api)
        result = json.loads(response)
        if isinstance(result, list):
            _result = []
            for i in result:
                if float(i['free']) > 0:
                    ai = OrderClass.AccountInfo()
                    ai.symbol = i['asset']
                    ai.available = float(i['free'])
                    ai.total = ai.available+float(i['locked'])
                    if ai.symbol != 'USDT':
                        ai.unrealizedPL = float(i['btcValuation'])
                    _result.append(ai)
            return _result
        else:
            return response

    async def transfer(self, fromType: int, toType: int, usdt: float):
        api = {
            'rest': "https://api.binance.com",
            "method": "POST",
            "url": "/sapi/v1/asset/transfer",
            "payload": {
                'type': 'MAIN_UMFUTURE' if fromType == 0 else 'UMFUTURE_MAIN',
                'asset': 'USDT',
                'amount': usdt
            }

        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'tranId' in result:
            return (result['tranId'],)
        else:
            return response

    async def setlever(self, symbol: str, lever: int):
        api = {
            "method": "POST",
            "url": "/fapi/v1/leverage",
            "payload": {
                'symbol': symbol,
                'leverage': lever
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'leverage' in result:
            return True
        else:
            return response

    async def get_swap_pnl_history(self, symbol: str, orderId: str):
        api = {
            "method": "GET",
            "url": "/fapi/v1/userTrades",
            "payload": {
                'symbol': symbol,
                'orderId': int(orderId)
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if isinstance(result, list):
            pnl=0
            for i in result:
                if i['realizedPnl'] != '0':
                    pnl+=float(i['realizedPnl'])
            return pnl
        else:
            return response

    async def get_saving_funding(self):
        api = {
            "method": "GET",
            'rest': "https://api.binance.com",
            "url": "/sapi/v1/simple-earn/account",
            "payload": {
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'totalAmountInUSDT' in result :
            return float(result['totalAmountInUSDT'])
        else:
            return response
        
    #获取活期产品持仓(USER_DATA)
    async def get_simple_earn_id(self):
        api = {
            "method": "GET",
            'rest': "https://api.binance.com",
            "url": "/sapi/v1/simple-earn/flexible/position",
            "payload": {
                'asset':"USDT"
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'rows' in result :
            if len(result['rows'])>0:
                return (result['rows'][0]['productId'],)
            return ''
        else:
            return response

    async def move_to_simple_earn(self,productId:str,usdt:float):
        api = {
            "method": "POST",
            'rest': "https://api.binance.com",
            "url": "/sapi/v1/simple-earn/flexible/subscribe",
            "payload": {
                'productId':productId,
                'amount':usdt
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'success' in result and result['success']==True:
            return result['purchaseId']
        else:
            return response

    async def fedeem_simple_earn(self,productId:str,usdt:float):
        api = {
            "method": "POST",
            'rest': "https://api.binance.com",
            "url": "/sapi/v1/simple-earn/flexible/redeem",
            "payload": {
                'productId':productId,
                'amount':usdt
            }
        }
        response = await self.send_request(api)
        result = json.loads(response)
        if 'success' in result and result['success']==True:
            return result['redeemId']
        else:
            return response    
        

