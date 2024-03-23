
from log import logger


def get_swap_symbol(standard_name: str, ex: str) -> str:
    if 'USDT' in standard_name:
        return standard_name
    exchange_name = ex.lower()
    if exchange_name == "binance":
        return f"{standard_name.upper()}USDT"
    elif exchange_name == "okx":
        return f"{standard_name.upper()}-USDT-SWAP"
    elif exchange_name == "bitget":
        return f"{standard_name.upper()}USDT"
    elif exchange_name == "bingx":
        return f"{standard_name.upper()}-USDT"
    elif exchange_name == 'nexo':
        return f"{standard_name.upper()}USDT"
    else:
        logger.error(f"暂不支持{exchange_name}这个交易所的永续合约名")


def get_spot_symbol(standard_name: str, ex: str) -> str:
    if 'USDT' in standard_name:
        return standard_name
    exchange_name = ex.lower()
    if exchange_name == "binance":
        return f"{standard_name.upper()}USDT"
    elif exchange_name == "okx":
        return f"{standard_name.upper()}-USDT"
    elif exchange_name == "bitget":
        return f"{standard_name.upper()}USDT"
    elif exchange_name == "bingx":
        return f"{standard_name.upper()}-USDT"
    elif exchange_name == "nexo":
        return f"{standard_name.upper()}/USDT"
    else:
        logger.error(f"暂不支持{exchange_name}这个交易所的永续合约名")
