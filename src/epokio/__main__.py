"""`python -m epokio setup` 처럼 쓴다. ★pip의 Scripts 폴더가 PATH에 없는 윈도우에서는 `epokio`가 '인식되지 않는 명령'이었다"""
from .cli import main

main()
