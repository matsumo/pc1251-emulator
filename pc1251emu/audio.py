"""圧電ブザーの音

Cポートの上位4ビット(ビット6〜4)で出力が決まる(POPCOMの講座の表7、
PockEmulのcompute_xout)。

    0, 4  LOW        1, 5  HIGH
    2     2kHzの発振  3     4kHzの発振
    6, 7  カセット入力をそのまま出す(ここでは無音)

BASICのBEEP文は3(4kHz)を使い、PC-インタープリタのBEEPは5と4を交互に
書いて振動板を直接動かす。CPUのサイクル数で時刻を持っているので、
書き込みの間隔がそのまま音の高さになる。
"""

import math
from array import array

from .machine import CLOCK

RATE = 44100  # 22050Hzでは方形波の高調波の折り返しが耳につくので、この速さで作る
AMP = 9000
# 圧電素子は低音を返さない。50Hzあたりから下を切る一次のハイパス
HPF = 1.0 - 2 * math.pi * 50 / RATE
# 1.5kHzより上を約6dB下げる一次のシェルフ。方形波のままだと、実機の録音より
# 倍音が強く軽い音になる。600Hzの2次ローパスまで削るとこもるので、この程度にした
SHELF_A = math.exp(-2 * math.pi * 1500 / RATE)
SHELF_G = 0.5
SPC = CLOCK / RATE  # 1サンプルあたりのCPUサイクル(約4.4)
OSC_HALF = {2: CLOCK / 2000 / 2, 3: CLOCK / 4000 / 2}  # 内蔵発振の半周期(サイクル)


class Buzzer:
    def __init__(self):
        self.mode = 0  # 次の標本の始まりの時刻での出力
        self.t = 0.0  # 次の標本の始まりのサイクル
        self.pending: list[tuple[int, int]] = []  # 標本にまだ入れていない書き込み
        self.x_prev = 0.0
        self.y = 0.0
        self.lp = 0.0  # シェルフの低域側

    @staticmethod
    def _mean(mode: int, t0: float, t1: float) -> float:
        """サイクルt0〜t1の出力の平均(-1〜1)。内蔵発振は正確に積分する"""
        if mode in (1, 5):
            return 1.0
        half = OSC_HALF.get(mode)
        if half is None or t1 <= t0:
            return -1.0

        def tri(t: float) -> float:  # 発振の方形波(最初の半周期が+1)を0からtまで積分した値
            k, r = divmod(t, half)
            return r if int(k) % 2 == 0 else half - r

        return (tri(t1) - tri(t0)) / (t1 - t0)

    def render(self, events: list[tuple[int, int]], c0: int, c1: int) -> bytes:
        """サイクルc0〜c1ぶんのPCMを作る。eventsは(サイクル, モード)の列。

        PC-インタープリタは1〜3kHzの音を、Cポートを書き換える間隔で作る。1周期が
        10サンプル前後しかないので、書き換えの時刻をサンプルの点で拾うと、半周期の
        長さが1サンプルずつ揺れて濁った音になる。そこで各サンプルの区間で、出力が
        HIGHだった時間の割合を平均して値にする。

        標本の時刻はフレームをまたいでつなげる。1フレームのサイクル数は標本の間隔で
        割り切れないので、端数を捨てると毎フレーム音が少しずつ欠けて濁る。
        """
        if abs(self.t - c0) > 2 * SPC:  # 早送りのあとなど、時刻が飛んだ
            self.t = float(c0)
            self.pending = []
        ev = self.pending + [e for e in events if c0 <= e[0] < c1]
        n = max(0, int((c1 - self.t) / SPC))
        out = array("h", bytes(2 * n))
        idx = 0
        mode = self.mode
        silent = True
        x_prev, y, lp = self.x_prev, self.y, self.lp
        t0 = self.t
        for i in range(n):
            t1 = self.t + (i + 1) * SPC
            if idx < len(ev) and ev[idx][0] < t1:
                acc = 0.0
                t = t0
                while idx < len(ev) and ev[idx][0] < t1:
                    tc = max(t, ev[idx][0])
                    if tc > t:
                        acc += self._mean(mode, t, tc) * (tc - t)
                    t = tc
                    mode = ev[idx][1]
                    idx += 1
                acc += self._mean(mode, t, t1) * (t1 - t)
                x = acc / (t1 - t0)
            else:
                x = self._mean(mode, t0, t1)
            y = HPF * (y + x - x_prev)
            x_prev = x
            lp = SHELF_A * lp + (1 - SHELF_A) * y
            z = lp + SHELF_G * (y - lp)
            if abs(z) > 1e-3:
                silent = False
            out[i] = int(max(-1.0, min(1.0, z)) * AMP)
            t0 = t1
        self.t = t0
        self.pending = ev[idx:]
        self.mode = mode
        self.x_prev, self.y, self.lp = x_prev, y, lp
        return b"" if silent else out.tobytes()
