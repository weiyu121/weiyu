from typing import Callable
from pathlib import Path
from threading import Thread, Event
from time import perf_counter, sleep

from config import config
from base.logger import get_logger


class LedTipper:

    def __init__(self):
        self._led_driver = Path('/sys/class/leds/work1/brightness')
        if not self._led_driver.exists():
            self._led_driver = None
        self._on = False
        self._twinkling = Event()
        self._twinkling.set()  # 默认不用等待闪烁退出

    def bright(self):
        self._turnon()
        self._turn(True)

    def twinkle(self):
        self._turnon()
        # 开个线程让他一直闪，直到给闪烁关了
        def twinkle_daemon():
            twinkle_on = False
            self._twinkling.clear()
            while self._on:
                twinkle_on = not twinkle_on
                self._turn(twinkle_on)
                sleep(0.2)
            self._turn(False)
            self._twinkling.set()
        Thread(target=twinkle_daemon).start()

    def turnoff(self):
        self._on = False
        self._twinkling.wait()  # 等待闪烁线程退出
        self._turn(False)  # 关闭bright打开的灯

    def _turnon(self) -> bool:
        if self._on:
            self.turnoff()
        self._on = True

    def _turn(self, on: bool):
        if self._led_driver:
            self._led_driver.write_text('0' if on else '1')

class ResetButtonListener:
    def __init__(self, on_reset: Callable[[None], None]):
        base_gpio_path = Path('/sys/class/gpio')
        gpio_path = base_gpio_path / f'gpio{config._RESET_BUTTON_GPIO_INDEX}'
        self._value_path = gpio_path / 'value'
        self._on_reset = on_reset
        self._logger = get_logger('network.hotspot')
        self._available = True
        try:
            # 如果没有被注册过，就注册
            if not gpio_path.exists():
                # 注册GPIO重置按钮
                (base_gpio_path / 'export').write_text(str(config._RESET_BUTTON_GPIO_INDEX))
                # 写入derection
                (gpio_path / 'direction').write_text('in')
        except Exception as e:
            self._logger.info(f'重置按钮监听不可用：{e}')
            self._available = False
        
        if self._available:
            # 开线程监测文件内容是否变化
            Thread(target=self._daemon, daemon=True).start()

    @property
    def _pressed(self) -> bool:
        return not bool(int(self._value_path.read_text().strip()))

    def _daemon(self):
        self._logger.debug('重置按钮监测线程已启动')
        led_tipper = LedTipper()
        while True:
            if self._pressed:
                led_tipper.bright()
                # 轮询监测连续n秒是否都是按下
                # 本来想sleep5s后对比文件修改时间的，但是这个文件特殊，三个时间都不变，就轮询吧
                begin_time = perf_counter()
                while True:
                    if not self._pressed:
                        break
                    elif perf_counter() - begin_time >= config._RESET_BUTTON_PRESSING_SECONDS:
                        led_tipper.twinkle()
                        self._on_reset()
                        led_tipper.turnoff()
                        break
                    sleep(0.1)  # 轮询间隔设小，对于按钮敏感点
            else:
                led_tipper.turnoff()
            sleep(0.3)