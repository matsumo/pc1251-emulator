"""PC-1251本体: メモリ、キーボード、タイマ、液晶、ブザー

配置はMAMEとPockEmulのPC-1251の実装、ポートのビットはPOPCOM 1984年
9〜11月号の講座の表7と照らし合わせて決めた。

    0000-1FFF  内部ROM(CPUに内蔵、8KB)
    4000-7FFF  BASIC ROM(16KB)
    B800-C7FF  RAM(4KB)。B000-B7FFはB800-BFFFの鏡(PockEmulによる)。
               BASICはプログラムの先頭をB030(=B830)に置く
    F800-F87F  液晶RAM

PC-1245も同じつくりで、違いはMODELSの表にまとめた。RAMはC000-C7FFの2KB、
液晶は16桁で、モードスイッチにRSVの段がない。ROMはPC-1251とは別のもの。
"""

import os
from dataclasses import dataclass

from .sc61860 import SC61860, Bus

CLOCK = 192_000  # 命令サイクルの周波数(水晶576kHzの1/3)
TICK_2MS = CLOCK // 500  # 2msごとに反転するタイマ
LCD_LO, LCD_HI = 0xF800, 0xF900

# キーの配置。(ストローブ, 読み取りビット)。ストローブは("B", n)がポートIBの
# ビットn、("A", n)がポートIAのビットn。MAMEとPockEmulで一致している。
KEYS = {
    "-": ("B", 0, 0x01),
    "CL": ("B", 0, 0x02),
    "*": ("B", 0, 0x04),
    "/": ("B", 0, 0x08),
    "DOWN": ("B", 0, 0x10),
    "E": ("B", 0, 0x20),
    "D": ("B", 0, 0x40),
    "C": ("B", 0, 0x80),
    "+": ("B", 1, 0x01),
    "9": ("B", 1, 0x02),
    "3": ("B", 1, 0x04),
    "6": ("B", 1, 0x08),
    "SHIFT": ("B", 1, 0x10),
    "W": ("B", 1, 0x20),
    "S": ("B", 1, 0x40),
    "X": ("B", 1, 0x80),
    ".": ("B", 2, 0x01),
    "8": ("B", 2, 0x02),
    "2": ("B", 2, 0x04),
    "5": ("B", 2, 0x08),
    "DEF": ("B", 2, 0x10),
    "Q": ("B", 2, 0x20),
    "A": ("B", 2, 0x40),
    "Z": ("B", 2, 0x80),
    "7": ("A", 0, 0x02),
    "1": ("A", 0, 0x04),
    "4": ("A", 0, 0x08),
    "UP": ("A", 0, 0x10),
    "R": ("A", 0, 0x20),
    "F": ("A", 0, 0x40),
    "V": ("A", 0, 0x80),
    "=": ("A", 1, 0x04),
    "P": ("A", 1, 0x08),
    "LEFT": ("A", 1, 0x10),
    "T": ("A", 1, 0x20),
    "G": ("A", 1, 0x40),
    "B": ("A", 1, 0x80),
    "O": ("A", 2, 0x08),
    "RIGHT": ("A", 2, 0x10),
    "Y": ("A", 2, 0x20),
    "H": ("A", 2, 0x40),
    "N": ("A", 2, 0x80),
    "U": ("A", 3, 0x20),
    "J": ("A", 3, 0x40),
    "M": ("A", 3, 0x80),
    "I": ("A", 4, 0x20),
    "K": ("A", 4, 0x40),
    "SPC": ("A", 4, 0x80),
    "L": ("A", 5, 0x40),
    "ENTER": ("A", 5, 0x80),
    "0": ("A", 6, 0x80),
}

# モードスイッチ
MODES = ("OFF", "RUN", "PRO", "RSV")

# 液晶の表示記号: (番地, ビット)。PockEmulの配置による。
SYMBOLS = {
    "BUSY": (0xF83D, 0x01),
    "P": (0xF83C, 0x02),
    "DEF": (0xF83C, 0x01),
    "SHIFT": (0xF83D, 0x02),
    "PRO": (0xF83E, 0x01),
    "RUN": (0xF83E, 0x02),
    "RESERVE": (0xF83E, 0x04),
    "DE": (0xF83C, 0x08),
    "G": (0xF83C, 0x04),
    "RAD": (0xF83D, 0x04),
    "E": (0xF83D, 0x08),
}


# PC-1245の表示記号はF83CとF83Dの8つ(ビットはPC-1251と同じ。ht-deko.comによる)。
# モードは液晶に出ない(ROMはF83EにPRO・RUNのビットを書くが、表示はない)
SYMBOLS_1245 = {
    name: SYMBOLS[name] for name in ("DEF", "P", "G", "DE", "BUSY", "SHIFT", "RAD", "E")
}


@dataclass(frozen=True)
class Model:
    """機種ごとの違い"""

    name: str  # "1251"。--modelで選ぶ名前
    title: str  # "PC-1251"
    ram: tuple[int, int]  # RAMの範囲(終わりは含まない)
    mirror: tuple[int, int] | None  # RAMの鏡の範囲。+0x800した番地と同じもの
    cells: int  # 液晶の桁数
    modes: tuple[str, ...]  # モードスイッチの段(上から)
    symbols: dict[str, tuple[int, int]]
    prog_start: int  # BASICのプログラムの先頭(FFの番地)

    @property
    def roms(self) -> tuple[str, str]:
        """(内部ROM, BASIC ROM)のファイル名"""
        return (f"cpu-{self.name}.rom", f"bas-{self.name}.rom")


MODELS = {
    "1251": Model(
        name="1251",
        title="PC-1251",
        ram=(0xB800, 0xC800),
        mirror=(0xB000, 0xB800),
        cells=24,
        modes=("RSV", "PRO", "RUN", "OFF"),
        symbols=SYMBOLS,
        prog_start=0xB830,
    ),
    "1245": Model(
        name="1245",
        title="PC-1245",
        ram=(0xC000, 0xC800),
        mirror=None,
        cells=16,
        modes=("PRO", "RUN", "OFF"),
        symbols=SYMBOLS_1245,
        prog_start=0xC000,
    ),
}


class RomNotFound(FileNotFoundError):
    pass


def find_rom(name: str) -> str:
    """ROMファイルを探す。PC1251_ROM、./rom、~/.pc1251の順。"""
    dirs = [
        os.environ.get("PC1251_ROM", ""),
        "rom",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rom"),
        os.path.expanduser("~/.pc1251"),
    ]
    for d in dirs:
        if d and os.path.exists(os.path.join(d, name)):
            return os.path.join(d, name)
    model = name[4:-4]  # "cpu-1251.rom"の"1251"
    raise RomNotFound(
        f"ROMのファイル{name}が見つかりません。実機から読み出した内部ROM(cpu-{model}.rom、"
        f"8KB)とBASIC ROM(bas-{model}.rom、16KB)をrom/に置くか、環境変数PC1251_ROMに"
        "置き場所を指定してください(READMEの「ROMの用意」)。"
    )


def rom_size(name: str) -> int:
    """内部ROMは8KB、BASIC ROMは16KB"""
    return 0x2000 if name.startswith("cpu-") else 0x4000


def read_rom(name: str) -> bytes:
    """ROMのファイルを読み、大きさが足りているか確かめる。版の違いがあるので中身は見ない"""
    path = find_rom(name)
    data = open(path, "rb").read()
    size = rom_size(name)
    if len(data) < size:
        raise RomNotFound(
            f"{path}は{len(data)}バイトしかありません。"
            f"{name}は{size}バイト({size // 1024}KB)必要です。"
        )
    return data


class PC1251(Bus):
    """本体。model="1245"でPC-1245になる"""

    def __init__(
        self, cpu_rom: bytes | None = None, bas_rom: bytes | None = None, model: str = "1251"
    ):
        self.model = MODELS[model]
        self.mem = bytearray(0x10000)
        cpu_name, bas_name = self.model.roms
        if cpu_rom is None:
            cpu_rom = read_rom(cpu_name)
        if bas_rom is None:
            bas_rom = read_rom(bas_name)
        self.mem[0:0x2000] = cpu_rom[:0x2000]
        self.mem[0x4000:0x8000] = bas_rom[:0x4000]
        self.wmask = bytearray(0x10000)
        ram_lo, ram_hi = self.model.ram
        for a in range(ram_lo, ram_hi):
            self.wmask[a] = 1
        mirror = self.model.mirror
        self._mirror_lo, self._mirror_hi = mirror if mirror else (0, 0)
        for a in range(LCD_LO, LCD_HI):
            self.wmask[a] = 1
        self.cpu = SC61860(self)
        self.held: set[str] = set()  # 押されているキー
        self.brk = False  # BRK(ON)キー
        self.reset_key = False  # 裏のRESETボタン
        self.mode = "RUN"
        self.pa = self.pb = self.pc_out = self.pf = 0
        self.lcd_dirty = True
        self.power = True  # Cポートのビット3で切れる
        self.halted = False  # Cポートのビット2で止まっている
        self.cold_start()

    # ---- 電源とリセット ----
    def cold_start(self) -> None:
        self.cpu.reset()
        self.cpu.ram[:] = bytes(len(self.cpu.ram))
        self.t2 = 0
        self.t2ms = self.t512 = 0
        self.t512cnt = 0
        self.tape = None  # 再生中のテープ(tape.TapeIn)。Xinに出る
        self.power = True
        self.sound_events: list[tuple[int, int]] = []  # (サイクル, Cポートの上位4ビット)

    def wake(self) -> None:
        """ONキーで電源を入れ直す。RAMの中身は残る。"""
        self.cpu.reset()
        self.power = True
        self.halted = False

    # ---- バス ----
    def read(self, a: int) -> int:
        if self._mirror_lo <= a < self._mirror_hi:
            a += 0x800
        return self.mem[a]

    def write(self, a: int, v: int) -> None:
        if self._mirror_lo <= a < self._mirror_hi:
            a += 0x800
        if self.wmask[a]:
            self.mem[a] = v
            if a >= LCD_LO:
                self.lcd_dirty = True

    def _scan(self, port: str, strobe: int) -> int:
        v = 0
        for k in self.held:
            key = KEYS.get(k)
            if key and key[0] == port and strobe & (1 << key[1]):
                v |= key[2]
        return v

    def in_a(self) -> int:
        return self._scan("B", self.pb & 0x07) | self._scan("A", self.pa & 0x7F)

    def in_b(self) -> int:
        # IBの下位4ビット: 出力したストローブにモードスイッチが返る(PockEmulに合わせた)。
        # OFFはビット2。ROMの1D36でINBの下位3ビットを見ており、ビット0がRSV、
        # ビット1がPRO、どれも0ならRUN、ビット2だけのときはROMが自分で電源を切る
        # (内部RAMの30h〜37hに印を書いてからCポートのビット3を立てる)。
        data = self.pb & 0x0F
        ret = 0
        if self.pb & 0x08:
            ret |= {"PRO": 2, "RSV": 1, "OFF": 4}.get(self.mode, 0)
        if (self.pb & 0x02) and self.mode == "PRO":
            ret |= 0x08
        if (self.pb & 0x01) and self.mode == "RSV":
            ret |= 0x08
        return (ret & ~data) | (self.pb & 0xF0)

    def out_a(self, v: int) -> None:
        self.pa = v

    def out_b(self, v: int) -> None:
        self.pb = v

    def out_f(self, v: int) -> None:
        self.pf = v

    def out_c(self, v: int) -> None:
        old = self.pc_out
        self.pc_out = v
        if v & 0x02:  # カウンタのリセット
            self.t2 = 0
            self.t512cnt = 0
        if (v ^ old) & 0xF0:
            self.sound_events.append((self.cpu.cycles, v >> 4))
        if v & 0x08:  # 電源オフ
            self.power = False
        if v & 0x04:  # 止まって待つ(キーか512msのタイマで起きる)
            self.halted = True
        self.lcd_dirty = True

    def xin(self, cycle: int) -> int:
        """カセットの入力(Xin)。テープがなければ0"""
        tape = self.tape
        return tape.level(cycle) if tape is not None else 0

    def test(self, n: int) -> int:
        """TEST命令。タイマの印(ビット0が512ms、ビット1が2ms)は、その間隔ごとに立ち、
        読むと消える。ROMはテープの1ビットや待ち時間を、印が立つのを続けて何回も待つ
        ことで数えるので、立っているあいだずっと見える信号では数えられない"""
        t = self.test_bits() & n
        if t & 0x01:
            self.t512 = 0
        if t & 0x02:
            self.t2ms = 0
        if n & 0x80 and self.xin(self.cpu.cycles):  # テープは読むときだけ見る
            t |= 0x80
        return t

    def test_bits(self) -> int:
        t = 0
        if self.t512:
            t |= 0x01
        if self.t2ms:
            t |= 0x02
        if self.brk:
            t |= 0x08
        if self.reset_key:  # 裏のRESETボタン。電源を入れただけでは見えない
            t |= 0x40
        return t

    # ---- 実行 ----
    def run(self, cycles: int) -> None:
        """指定サイクルぶん動かす。2msごとにタイマを進める。"""
        cpu = self.cpu
        while cycles > 0:
            if not self.power:
                if self.brk:
                    self.wake()
                else:
                    return
            chunk = min(cycles, TICK_2MS - self.t2)
            if self.halted and (self.held or self.brk or self.reset_key):
                self.halted = False
            if self.halted:  # 止まっているあいだは時間だけ進める
                used = chunk
                cpu.cycles += used
            else:
                used = cpu.run(chunk)
            self.t2 += used
            cycles -= used
            if self.t2 >= TICK_2MS:
                self.t2 -= TICK_2MS
                self.t2ms = 1  # TESTで読むと消える(下のtest)
                self.t512cnt += 1
                if self.t512cnt >= 256:
                    self.t512cnt = 0
                    self.t512 = 1  # 2msと同じく、読むと消える
                    self.halted = False

    # ---- 液晶 ----
    def display_on(self) -> bool:
        return self.power and bool(self.pc_out & 0x01)

    def columns(self) -> list[int]:
        """左から桁数×5列ぶん(PC-1251は120列)の液晶RAM。左の12桁がF800から順に、
        残りはF87Bから逆順に並ぶ。PC-1245の16桁は右側の4桁ぶんF87B〜F868まで"""
        m = self.mem
        n = self.model.cells * 5
        left = min(n, 60)
        return list(m[0xF800 : 0xF800 + left]) + [m[0xF87B - i] for i in range(n - left)]

    def symbols(self) -> set[str]:
        m = self.mem
        return {name for name, (a, bit) in self.model.symbols.items() if m[a] & bit}

    def power_off(self, limit: float = 3.0) -> bool:
        """スイッチをOFFにして、ROMが電源を切るまで動かす。切れたらTrue。

        BASICは内部RAMの30h〜37hの印でメモリが生きているかを確かめるので、
        ROMに切らせないと次に電源を入れたときにプログラムが消える。
        """
        self.mode = "OFF"
        spent = 0
        while self.power and spent < limit * CLOCK:
            if spent == CLOCK:  # 1秒たっても切れなければBRKで止めてみる
                self.brk = True
            if spent == CLOCK + CLOCK // 10:
                self.brk = False
            self.run(CLOCK // 50)
            spent += CLOCK // 50
        self.brk = False
        return not self.power

    # ---- RAMの保存 ----
    # 外部RAM(PC-1251は4KB)のあとに、電池で保たれるCPUの内部RAM(96バイト)を続けて書く
    def save_ram(self, path: str) -> None:
        ram_lo, ram_hi = self.model.ram
        with open(path, "wb") as f:
            f.write(self.mem[ram_lo:ram_hi])
            f.write(self.cpu.ram)

    def load_ram(self, path: str) -> bool:
        try:
            data = open(path, "rb").read()
        except OSError:
            return False
        ram_lo, ram_hi = self.model.ram
        n = ram_hi - ram_lo
        if len(data) not in (n, n + len(self.cpu.ram)):
            return False
        self.mem[ram_lo:ram_hi] = data[:n]
        if len(data) > n:
            self.cpu.ram[:] = data[n:]
        return True
