import struct
import serial
import time
import threading

# ---------- 校验和 ----------
def calc_checksum(data: bytes) -> int:
    return sum(data) & 0xFF

# ---------- 下行帧打包 ----------
def downlink_switch(action: int) -> bytes:
    assert action in (0x00, 0x01, 0x02)
    payload = struct.pack('<BB', 0x01, action)
    packet = b'\x5A\xA5' + payload
    return packet + bytes([calc_checksum(packet)])

def downlink_brightness(brightness: float) -> bytes:
    if not 0.0 <= brightness <= 1.0:
        raise ValueError("亮度范围 0.0~1.0")
    payload = struct.pack('<Bf', 0x02, brightness)
    packet = b'\x5A\xA5' + payload
    return packet + bytes([calc_checksum(packet)])

# ---------- 上行帧解析器（滑动窗口 + 三级过滤） ----------
class UplinkParser:
    def __init__(self, on_frame):
        """
        on_frame: 回调函数，参数为 (gpio_state: int)
        """
        self.buf = b''
        self.lock = threading.Lock()
        self.on_frame = on_frame

    def feed(self, data: bytes):
        with self.lock:
            self.buf += data
            self._parse()

    def _parse(self):
        """内部解析，调用时会持有锁"""
        HEADER = b'\x5A\xA5'
        while True:
            idx = self.buf.find(HEADER)
            if idx == -1:
                if len(self.buf) > 1:
                    self.buf = self.buf[-1:]   # 保留最后一个可能为 0x5A 的字节
                return

            if len(self.buf) - idx < 4:
                return                          # 数据不足，等待更多字节

            frame = self.buf[idx:idx+4]
            data_part = frame[:3]
            received_cs = frame[3]
            if calc_checksum(data_part) == received_cs:
                # 校验通过，调用回调
                gpio_state = frame[2]
                self.on_frame(gpio_state)
                self.buf = self.buf[idx+4:]     # 移除已处理的帧
                continue                        # 继续检查后续帧
            else:
                # 脏帧，跳过一个 0x5A 继续滑动
                self.buf = self.buf[idx+1:]

# ---------- 主程序 ----------
def main():
    ser = serial.Serial('COM8', 115200, timeout=0.1)

    # 上行帧回调（在接收线程中调用）
    def handle_uplink(gpio):
        #print(f">>> GPIO 状态 = {'高电平' if gpio else '低电平'}")
        return

    parser = UplinkParser(on_frame=handle_uplink)

    # 接收线程
    def reader():
        while True:
            try:
                data = ser.read(256)
                if data:
                    parser.feed(data)
            except Exception as e:
                print(f"串口读取异常: {e}")
                break

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    print("指令: on / off / toggle / b <0~1> / q")
    while True:
        try:
            cmd_input = input().strip().split()
        except EOFError:
            break

        if not cmd_input:
            continue
        cmd = cmd_input[0].lower()
        if cmd == 'q':
            break
        elif cmd == 'on':
            ser.write(downlink_switch(0x01))
        elif cmd == 'off':
            ser.write(downlink_switch(0x00))
        elif cmd == 'toggle':
            ser.write(downlink_switch(0x02))
        elif cmd == 'b' and len(cmd_input) == 2:
            try:
                val = float(cmd_input[1])
                ser.write(downlink_brightness(val))
            except ValueError:
                print("请输入 0~1 之间的数字")
        else:
            print("未知指令")

        # 稍微等一下串口发送完成
        time.sleep(0.2)

    ser.close()
    print("程序结束")

if __name__ == '__main__':
    main()