import asyncio
import hashlib
import math

import urllib.parse
from .SDKBase import SDKBase
import datetime
import aiohttp
import json
from . import OrderClass
import time
import hmac
import base64
class KrakenSdk(SDKBase):
    name ='kraken'
    _future_rest="https://futures.kraken.com"
    _spot_rest='https://api.kraken.com'
    spot_baseinfo={}
    swap_baseinfo={}
    def __init__(self, api_key: str, api_secret: str, api_password: str = None) -> None:
        self.nonce=0
        self.useNonce=True
        api_key=json.loads(api_key)
        api_secret=json.loads(api_secret)
        super().__init__(api_key, api_secret, api_password)

    def get_spot_sign(self,urlpath:str, data:dict):
        postdata = urllib.parse.urlencode(data)
        encoded = (str(data['nonce']) + postdata).encode()
        message = urlpath.encode() + hashlib.sha256(encoded).digest()

        mac = hmac.new(base64.b64decode(self.keyconf['secret'][0]), message, hashlib.sha512)
        sigdigest = base64.b64encode(mac.digest())
        return sigdigest.decode()

    async def send_spot_request(self, api):
        api['payload']['nonce'] = str(int(time.time()*1000))
        headers = {
            "API-Key": self.keyconf['apiKey'][0],
            'API-Sign':self.get_spot_sign(api['url'],api['payload'])
        }
        method = api["method"]
        data=urllib.parse.urlencode(api['payload'])
        try:
            if method == "GET":
                url = f"{KrakenSdk._spot_rest}{api['url']}?{data}"
                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url=url, headers=headers) as response:
                        return await response.text()
            elif method == "POST":
                url = f"{KrakenSdk._spot_rest}{api['url']}"
                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url=url, data=api['payload'], headers=headers) as response:
                        return await response.text()
        except Exception as e:
            return f'{{"e": "{e}"}}' 

    def get_swap_sign(self,endpoint:str, postData:str,nonce:str):
        if endpoint.startswith('/derivatives'):
            endpoint = endpoint[len('/derivatives'):]

        # step 1: concatenate postData, nonce + endpoint
        message = postData+ nonce + endpoint

        # step 2: hash the result of step 1 with SHA256
        sha256_hash = hashlib.sha256()
        sha256_hash.update(message.encode('utf8'))
        hash_digest = sha256_hash.digest()

        # step 3: base64 decode apiPrivateKey
        secretDecoded = base64.b64decode(self.keyconf['secret'][1])

        # step 4: use result of step 3 to has the result of step 2 with HMAC-SHA512
        hmac_digest = hmac.new(secretDecoded, hash_digest,
                               hashlib.sha512).digest()

        # step 5: base64 encode the result of step 4 and return
        return base64.b64encode(hmac_digest).decode('utf-8')
    
    def get_nonce(self):
        return str(int(time.time() * 1000))
  

    async def send_swap_request(self, api):
        Nonce = self.get_nonce()
        postData = urllib.parse.urlencode(api['payload'])
        headers = {
            "APIKey": self.keyconf['apiKey'][1],
            "Authent":self.get_swap_sign(api['url'],postData,Nonce),
            'Nonce':Nonce
        }
        method = api["method"]
        try:
            if method == "GET":
                url = f"{KrakenSdk._future_rest}{api['url']}" if len(postData)==0 else f"{KrakenSdk._future_rest}{api['url']}?{postData}"
                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url=url, headers=headers) as response:
                        return await response.text()
            elif method == "POST":
                url = f"{KrakenSdk._future_rest}{api['url']}"
                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url=url, json=api['payload'], headers=headers) as response:
                        return await response.text()
        except Exception as e:
            return f'{{"e": "{e}"}}'
        
    @staticmethod
    async def request_baseinfo():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request("GET", url=f"{KrakenSdk._spot_rest}/0/public/AssetPairs") as response:
                    result = await response.text()
                    print(result)
                    result = json.loads(result)
                    if 'error' in result and len(result['error'])==0:
                        data = result['result']
                        KrakenSdk.spot_baseinfo.clear()
                        for i in data:
                            if i.endswith('USD'):
                                KrakenSdk.spot_baseinfo[i]=data[i]
                                pass

        except Exception as e:
            print(f'kraken request_baseinfo spot err={e}')

    async def request_spot_positions(self):
        api = {
            "method": "POST",
            "url": "/0/private/BalanceEx",
            "payload": {
            }
        }
        
        response = await self.send_spot_request(api)
        result = json.loads(response)
        if 'error' in result and len(result['error'])==0:
            _result = []
            for v,i in result['result']:
                if v!='USDT':
                    hold_trade=float(i['hold_trade'])
                    if hold_trade>0:
                        account = OrderClass.AccountInfo()
                        account.total=hold_trade
                        account.available=float(i['balance'])
                        account.symbol=v
                        _result.append(account)
                else:
                    account = OrderClass.AccountInfo()
                    account.total=float(i['hold_trade'])
                    account.available=float(i['balance'])
                    account.symbol=v        
                    _result.append(account)
            return _result
        else:
            return response
        

    async def make_spot_order(self, symbol: str, size: float, orderType: int = 0, price: float = 0):
        api = {
            "method": "POST",
            "url": "/0/private/AddOrder",
            "payload": {
                'ordertype': 'market' if orderType == 0 else 'limit',
                'type': 'buy',
                'volume': str(size),
                'pair': symbol,
                'timeinforce': 'GTC',
            }
        }
        if orderType == 1:
            api['payload']['price'] = str(price)
        response = await self.send_spot_request(api)
        result = json.loads(response)    
        if 'error' in result and len(result['error'])==0:
            return (result['result']['txid'][0],)
        else:
            return response




    async def request_swap_account(self):
        api = {
            "method": "GET",
            "url": "/derivatives/api/v3/accounts",
            "payload": {
            }
        }
        
        response=await self.send_swap_request(api)
        print(response)    
   