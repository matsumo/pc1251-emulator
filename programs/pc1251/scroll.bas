# title: 文字を1ドットずつ流す(マシン語)
# 同じ名前のscroll.hexを先に書き込み、CALL &C000で動かす。BRKで止める
# 「POCKET COMPUTER PC-1251」を液晶の全幅で右から左へ1列ずつ流す。
10 CALL &C000
