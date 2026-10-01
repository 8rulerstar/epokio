# README용 GIF 조립: Epokio --export-info-toggle 프레임(PNG) -> 600px GIF
# 사용: python tools/make_info_toggle_gif.py <프레임폴더> <out.gif>
import glob
import sys

from PIL import Image

fs = sorted(glob.glob(sys.argv[1] + "/f_*.png"))
ims = []
for f in fs:
    im = Image.open(f).convert("RGB")
    ims.append(im.resize((600, round(im.height * 600 / im.width)), Image.LANCZOS))
pal = ims[len(ims) // 4].quantize(colors=128, method=Image.MEDIANCUT)    # 칩이 켜진 장면에서 팔레트를 뽑는다
q = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in ims]
q[0].save(sys.argv[2], save_all=True, append_images=q[1:], duration=50, loop=0, optimize=True, disposal=1)
print(sys.argv[2], q[0].size, len(q))
