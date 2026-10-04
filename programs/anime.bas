# title: 文字のアニメーション(WAITの例)
# 電光掲示板のように、文字を右から左へ流す。
# WAIT 2にしておくと、PRINTは止まらずに少しだけ見せて次へ進む。
# 最後のWAITだけの行で、PRINTがENTERを待つ動作に戻る。
10 DIM T$(0)*40
20 T$(0)="                        POCKET COMPUTER"
30 WAIT 2
40 FOR I=1 TO 24
50 PRINT MID$ (T$(0),I,24)
60 NEXT I
70 WAIT:PRINT "POCKET COMPUTER"
80 END
