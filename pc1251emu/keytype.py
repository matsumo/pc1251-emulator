"""文字列をPC-1251(とPC-1245)のキー操作に直す(貼り付けと自動入力用)"""

# SHIFTを押してから打つ記号。MAMEのキー名(下段がSHIFTのときの文字)による。
SHIFTED = {
    ">": "-",
    "<": "*",
    "^": "/",
    "(": "DOWN",
    "#": "E",
    "!": "Q",
    "@": "3",
    '"': "W",
    ")": "UP",
    "$": "R",
    ";": "P",
    "%": "T",
    ",": "O",
    "&": "Y",
    "?": "U",
    ":": "I",
    "√": ".",
    "π": "0",
}
# PC-1245は括弧が1と2の上にある(↓↑ではない)
SHIFTED_1245 = {**SHIFTED, "(": "1", ")": "2"}
PLAIN = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ+-*/=.")


def keys_for(text: str, model: str = "1251") -> list[list[str]]:
    """1文字ごとに押すキーの列。[["SHIFT"], ["I"]]のように、1打鍵ずつ並べる。"""
    shifted = SHIFTED_1245 if model == "1245" else SHIFTED
    out: list[list[str]] = []
    for ch in text.upper():
        if ch == "\n":
            out.append(["ENTER"])
        elif ch == " ":
            out.append(["SPC"])
        elif ch in PLAIN:
            out.append([ch])
        elif ch in shifted:
            out.append(["SHIFT"])
            out.append([shifted[ch]])
        # それ以外の文字はPC-1251のキーにないので捨てる
    return out


# 1行に打てるのは79字まで(行番号と空白も数える)。長い行は途中まで打ってENTERし、
# ▶を80回押して行末へ送ってから続きを打つ。直すときの入力欄も80字ぶんで、入った部分は
# 中間コード(命令は1字)で数えるので、2回目からはその長さを見積もって残りに収まるだけ打つ。
LINE_MAX = 79

# BASICの命令と関数の綴り(PC-1251のBASIC ROMの表から)。中間コードでは1字になる
KEYWORDS = sorted(
    """OUTSTAT RESTORE DEGREE INKEY$ INSTAT LPRINT RADIAN RANDOM RETURN RIGHT$ SETCOM
    AREAD CHAIN CLEAR CLOAD CSAVE DEBUG ERROR GOSUB INPUT LEFT$ LLIST MERGE PAUSE
    PRINT TROFF USING BEEP CALL CHR$ COM$ CONT DATA GOTO GRAD LIST MID$ NEXT PASS
    PEEK POKE READ STEP STOP STR$ THEN TRON WAIT ABS ACS AND ASC ASN ATN COS DEG
    DIM DMS END EXP FOR INT KEY LEN LET LOG MEM NEW NOT OFF REM RND ROM RUN SGN SIN
    SQR TAN VAL <= <> >= IF LN ON OR PI TO""".split(),
    key=len,
    reverse=True,
)


def stored_len(text: str) -> int:
    """打った行をROMが中間コードにしたときの長さの見積もり(行番号は数字+1字)"""
    num, _, body = text.strip().partition(" ")
    n = len(num) + 1
    i, quoted = 0, False
    while i < len(body):
        ch = body[i]
        if ch == '"':
            quoted = not quoted
        elif not quoted:
            if ch == " ":
                i += 1
                continue
            kw = next((k for k in KEYWORDS if body.startswith(k, i)), None)
            if kw:
                n += 1
                i += len(kw)
                continue
        n += 1
        i += 1
    return n


def _cuts(line: str) -> tuple[list[int], list[int]]:
    """切ってよい位置。1つ目は文字列の外の「:」のすぐ後ろ、2つ目はそれ以外に
    切ってもよい位置(文字列の外の空白・「;」・「,」のすぐ後ろ)"""
    good, other, quoted = [], [], False
    for i, ch in enumerate(line):
        if ch == '"':
            quoted = not quoted
        elif not quoted and ch == ":":
            good.append(i + 1)
        elif not quoted and ch in " ;,":
            other.append(i + 1)
    return good, other


def split_line(line: str) -> list[str]:
    """79字を超える行を、打てる大きさに切り分ける。なるべく「:」(文字列の外)の
    あとで切る。切れるところがなければ、残りをそのまま最後の1つにする"""
    if len(line) <= LINE_MAX:
        return [line]
    good, other = _cuts(line)
    parts, done = [], 0
    while len(line) - done > 0:
        room = LINE_MAX if done == 0 else LINE_MAX - 1 - stored_len(line[:done])
        if len(line) - done <= room:
            parts.append(line[done:])
            break
        fit = [c for c in good if done < c <= done + room]
        if not fit:  # 「:」で切れなければ、文の途中で切る(ROMは入力のときに文法を見ない)
            fit = [c for c in other if done < c <= done + room]
        if not fit:
            parts.append(line[done:])
            break
        parts.append(line[done : fit[-1]])
        done = fit[-1]
    return parts


def keys_for_program(text: str, model: str = "1251") -> list[list[str]]:
    """BASICのプログラムを打ち込む打鍵。長い行は分けて、2つ目からは打ったばかりの
    行を直す形で後ろに足す"""
    out: list[list[str]] = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        first, *rest = split_line(line)
        out.extend(keys_for(first + "\n", model))
        for part in rest:
            out.extend([["RIGHT"]] * (LINE_MAX + 1))
            out.extend(keys_for(part + "\n", model))
    return out
