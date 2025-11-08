import serial
import os


'''
UART6TXM2      <---->
UART6RXM2      <---->
433Gpio1(SET)  <---->    GPIO4_B5 141
433gpio2(CS)   <---->    GPIO4_B4 140

'''



def parse_frame(message,total_length):
    '''

    解析数据帧
    :param message:       bytes
    :param total_length:  int   数据长度
    :return
    '''
    #将 bytes 类型的 message 转为十六进制字符串（例如 b'\x01' -> '01'）。
    # 函数没有返回值也没有后续代码，表示该函数尚未实现（stub）。
    message = message.hex()



class SerialInterface:
    def __init__(self, port='/dev/ttyS6', baudrate=9600, timeout=0.1, setgpio=141,csgpio=140):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.setstate = None   #0指令模式 1数据收发模式
        self.setgpio = setgpio
        self.csgpio = csgpio
        self.setctl = None
        self.csctl = None

    def open(self):
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            self.setctl = GPIO(self.setgpio)
            self.setctl.set_direction('out')
            self.csctl = GPIO(self.csgpio)
            self.csctl.set_direction('out')
            self.csctl.set_value(0)
            # print(f"串口 {self.port} 已打开")
        except Exception as e:
            print(f"打开串口 {self.port} 失败： {e}")

    def close(self):
        if self.ser:
            self.ser.close()
            print(f"串口 {self.port} 已关闭")


    def write(self, data):
        if not self.ser:
            print(f"串口 {self.port} 未打开")
            return

        try:
            # self.ser.write(data.encode())
            self.ser.write(data)
            # print(f"Send frame data: {list(map(hex, data))}")
        except Exception as e:
            print(f"发送数据失败： {e}")


    def read(self, length=1024):
        if not self.ser:
            print(f"串口 {self.port} 未打开")
            return

        try:
            # data = self.ser.read(length).decode()
            data = self.ser.read(length)
            # print(f"已接收数据： {data}\n")
            return data
        except Exception as e:
            print(f"接收数据失败： {e}")

    def setMode(self,value):
        '''
        配置433模块参数使能配置
        :param value: 0使能参数配置，1关闭
        '''
        self.setctl.set_value(value)
        self.setstate=self.setctl.get_value()
        return self.setstate


class GPIO:
    def __init__(self, gpio_index):
        self.gpio_index = gpio_index
        self.sysfs_path = f"/sys/class/gpio/gpio{gpio_index}"
        self.direction = None
        self.value = None

        self.export_gpio()
        self.refresh_direction()

    def is_exported(self):
        return os.path.exists(self.sysfs_path)

    def export_gpio(self):
        if not self.is_exported():
            with open("/sys/class/gpio/export", "w") as export_file:
                export_file.write(str(self.gpio_index))

    def unexport_gpio(self):
        if self.is_exported():
            with open("/sys/class/gpio/unexport", "w") as unexport_file:
                unexport_file.write(str(self.gpio_index))
            self.direction = None
            self.value = None

    def set_direction(self, direction):
        if not self.is_exported():
            raise ValueError("GPIO pin has not been exported")

        if direction not in ["in", "out"]:
            raise ValueError("Invalid direction. Must be 'in' or 'out'")

        if direction != self.direction:
            with open(f"{self.sysfs_path}/direction", "w") as direction_file:
                direction_file.write(direction)
            self.direction = direction

    def get_value(self):
        if not self.is_exported():
            raise ValueError("GPIO pin has not been exported")

        if self.direction == "in":
            self.refresh_value()

        return self.value

    def set_value(self, value):
        if not self.is_exported():
            raise ValueError("GPIO pin has not been exported")

        if self.direction != "out":
            raise ValueError("Cannot set value in input mode")

        if value not in [0, 1]:
            raise ValueError("Invalid value. Must be 0 or 1")

        if value != self.value:
            with open(f"{self.sysfs_path}/value", "w") as value_file:
                value_file.write(str(value))
            self.value = value

    def get_direction(self):
        if not self.is_exported():
            raise ValueError("GPIO pin has not been exported")

        if self.direction is None:
            self.refresh_direction()

        return self.direction

    def refresh_direction(self):
        with open(f"{self.sysfs_path}/direction", "r") as direction_file:
            self.direction = direction_file.read().strip()

    def refresh_value(self):
        with open(f"{self.sysfs_path}/value", "r") as value_file:
            value = value_file.read().strip()
        self.value = int(value)



if __name__  == '__main__':
    print('please use me as a module')


