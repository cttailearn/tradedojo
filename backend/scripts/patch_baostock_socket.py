# -*- coding: utf-8 -*-
"""
baostock 库忙循环缺陷补丁(2026-08-12)

背景:
  baostock 库 util/socketutil.py 的 send_msg 在 recv 循环里:
    while True:
        recv = default_socket.recv(8192)
        receive += recv
        if receive[-13:] == b"<![CDATA[]]>\\n": break
  - 对端断开时 recv 返回空字节, receive += b"" 永远不匹配结束符 -> 忙循环吃满一个 CPU 核
  - 对端保持连接但不回包时 recv 永久阻塞

  2026-08-12 线上故障: baostock 服务器不可达, 该死循环持续 6 天占满 100% CPU,
  且 _reset_login 调 bs.logout() 也走 send_msg 同样卡死。

修复:
  给 send_msg 加 recv 超时(5s) + 空字节检测, 让网络故障时快速失败返回 None,
  由上层 fetcher 统一重试 / failover。

用法(在 backend 目录执行):
  python scripts/patch_baostock_socket.py

注意:
  补丁写入 .venv/lib/python3.12/site-packages/baostock/util/socketutil.py
  重装依赖(uv sync / pip install)后会丢失, 需要重新执行本脚本。
"""
import io
import sys
from pathlib import Path

# 定位 venv 里的 baostock 库(支持 Windows/Linux 路径)
CANDIDATES = [
    Path(__file__).resolve().parent.parent / ".venv" / "lib",
    Path.home() / "tradedojo" / "backend" / ".venv" / "lib",
]
BAOSTOCK_SOCKET = None
for lib in CANDIDATES:
    if lib.exists():
        hits = list(lib.rglob("baostock/util/socketutil.py"))
        if hits:
            BAOSTOCK_SOCKET = hits[0]
            break
if BAOSTOCK_SOCKET is None:
    print("[FAIL] 未找到 baostock/util/socketutil.py,请确认在 backend 目录下执行")
    sys.exit(1)
print(f"[OK] 定位到: {BAOSTOCK_SOCKET}")

src = io.open(BAOSTOCK_SOCKET, encoding="utf-8").read()

# 幂等: 已打过补丁则跳过
if "_BS_RECV_TIMEOUT" in src:
    print("[SKIP] 补丁已存在,无需重复执行")
    sys.exit(0)

old = '''def send_msg(msg):
    """发送消息，并接受消息 """
    try:
        # default_socket = get_default_socket()
        if hasattr(context, "default_socket"):
            default_socket = getattr(context, "default_socket")
            if default_socket is not None:
                # str 类型 -> bytes 类型
                # msg = msg + "<![CDATA[]]>"  # 在消息结尾追加“消息之间的分隔符”，压缩时的分隔符
                msg = msg + "\\n"  # 在消息结尾追加“消息之间的分隔符”，不压缩时的分隔符
                default_socket.send(bytes(msg, encoding='utf-8'))
                receive = b""
                while True:
                    recv = default_socket.recv(8192)
                    receive += recv
                    # 判断是否读取完
                    if receive[-13:] == b"<![CDATA[]]>\\n":  # 压缩时的结尾分隔符长度
                    # if receive[-1:] == b"\\n":  # 不压缩时的结尾分隔符长度
                        break
                # return bytes.decode(zlib.decompress(receive))  # 进行解压
                head_bytes = receive[0:cons.MESSAGE_HEADER_LENGTH]
                head_str = bytes.decode(head_bytes)
                head_arr = head_str.split(cons.MESSAGE_SPLIT)
                if head_arr[1] in cons.COMPRESSED_MESSAGE_TYPE_TUPLE:
                    # 消息体需要解压
                    head_inner_length = int(head_arr[2])
                    body_str = bytes.decode(zlib.decompress(receive[cons.MESSAGE_HEADER_LENGTH:cons.MESSAGE_HEADER_LENGTH + head_inner_length]))
                    return head_str + body_str
                else:
                    return bytes.decode(receive)  # 不进行解压
            else:
                return None
        else:
            print("you don't login.")
'''

new = '''# 单次 recv 等待上限(秒)。baostock 服务器不可达时 recv 会永久挂起或忙循环,
# 此超时让 send_msg 快速失败,由上层(fetcher)统一重试/切换数据源。
_BS_RECV_TIMEOUT = 5.0


def send_msg(msg):
    """发送消息，并接受消息

    2026-08-12 修复: recv 加超时 + 空字节检测,避免对端断开时忙循环/永久阻塞。
    """
    try:
        # default_socket = get_default_socket()
        if hasattr(context, "default_socket"):
            default_socket = getattr(context, "default_socket")
            if default_socket is not None:
                # str 类型 -> bytes 类型
                # msg = msg + "<![CDATA[]]>"  # 在消息结尾追加“消息之间的分隔符”，压缩时的分隔符
                msg = msg + "\\n"  # 在消息结尾追加“消息之间的分隔符”，不压缩时的分隔符
                try:
                    default_socket.settimeout(_BS_RECV_TIMEOUT)
                    default_socket.send(bytes(msg, encoding='utf-8'))
                except Exception:
                    # send 失败(对端已断开) -> 快速失败,不进入 recv 循环
                    return None
                receive = b""
                while True:
                    try:
                        recv = default_socket.recv(8192)
                    except Exception:
                        # recv 超时/异常: 返回已收到的内容(可能不完整),由上层处理
                        if not receive:
                            return None
                        break
                    if not recv:
                        # 对端关闭连接: 返回已收到的内容(可能不完整)
                        break
                    receive += recv
                    # 判断是否读取完
                    if receive[-13:] == b"<![CDATA[]]>\\n":  # 压缩时的结尾分隔符长度
                    # if receive[-1:] == b"\\n":  # 不压缩时的结尾分隔符长度
                        break
                if not receive:
                    return None
                # return bytes.decode(zlib.decompress(receive))  # 进行解压
                head_bytes = receive[0:cons.MESSAGE_HEADER_LENGTH]
                head_str = bytes.decode(head_bytes)
                head_arr = head_str.split(cons.MESSAGE_SPLIT)
                if head_arr[1] in cons.COMPRESSED_MESSAGE_TYPE_TUPLE:
                    # 消息体需要解压
                    head_inner_length = int(head_arr[2])
                    body_str = bytes.decode(zlib.decompress(receive[cons.MESSAGE_HEADER_LENGTH:cons.MESSAGE_HEADER_LENGTH + head_inner_length]))
                    return head_str + body_str
                else:
                    return bytes.decode(receive)  # 不进行解压
            else:
                return None
        else:
            print("you don't login.")
'''

if old not in src:
    print("[WARN] 未匹配到原始 send_msg 源码,可能库版本已变化,请人工核对")
    sys.exit(2)

src = src.replace(old, new)
io.open(BAOSTOCK_SOCKET, "w", encoding="utf-8").write(src)
print("[OK] baostock send_msg 补丁已应用(recv 超时 + 空字节检测)")
