import tzlocal
import logging
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler(timezone=tzlocal.get_localzone_name())
logging.getLogger('apscheduler').setLevel(logging.ERROR)  # 给这玩意的警告禁用掉，输出一大堆很烦人