import logging
from logging.handlers import TimedRotatingFileHandler
logger = logging.getLogger('log')
logger.setLevel(logging.INFO)
__handler = TimedRotatingFileHandler(
    'tradingsystem.log', when='midnight', interval=1, backupCount=7)
__handler.setLevel(logging.INFO)

# 创建一个格式化器
__formatter = logging.Formatter(
    '%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s')
__handler.setFormatter(__formatter)
__console_handler = logging.StreamHandler()
__console_handler.setLevel(logging.INFO)
# 将handler添加到logger中
logger.addHandler(__handler)
logger.addHandler(__console_handler)
