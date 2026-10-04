"""Original geometric artwork. Optional rebuild: pip install Pillow, then run this file.
Runtime does not require Pillow. No downloaded photos, logos or embedded metadata.
"""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / 'miniprogram/assets'
OUT.mkdir(parents=True, exist_ok=True)
SCALE = 3


def canvas(size):
    image = Image.new('RGBA', (size[0]*SCALE, size[1]*SCALE))
    return image, ImageDraw.Draw(image)


def save(image, name, size):
    image.resize(size, Image.Resampling.LANCZOS).save(OUT / name)


# Neutral white sedan silhouette, unrelated to a vehicle brand or photograph.
size = (360, 140)
im, d = canvas(size)
def poly(points, color):
    d.polygon([(int(x*SCALE), int(y*SCALE)) for x, y in points], fill=color)
def oval(box, color):
    d.ellipse(tuple(int(v*SCALE) for v in box), fill=color)
oval((30, 113, 330, 125), '#11151b')
poly([(30,95),(48,78),(96,69),(129,40),(211,40),(256,72),(310,86),(330,102),(326,114),(30,114)], '#e3e7ee')
poly([(110,69),(137,47),(173,47),(173,71)], '#222936')
poly([(183,47),(205,47),(241,72),(183,71)], '#222936')
for x in (93,272):
    oval((x-22,94,x+22,138), '#12161d')
    oval((x-13,103,x+13,129), '#758294')
save(im, 'car.png', size)
for kind in ('car','trips','footprints'):
    for active in (False,True):
        size=(64,64);im,d=canvas(size);c='#7798ff' if active else '#999da8'
        def line(points):d.line([(x*SCALE,y*SCALE) for x,y in points],fill=c,width=4*SCALE,joint='curve')
        if kind=='car':
            line([(12,43),(12,31),(20,20),(44,20),(52,31),(52,43),(12,43)])
            line([(12,31),(52,31)])
            for x in (16,48):d.ellipse(((x-4)*SCALE,39*SCALE,(x+4)*SCALE,49*SCALE),fill=c)
        elif kind=='trips':
            line([(20,12),(46,12),(46,52),(20,52),(20,12)])
            for y in (23,33,43):line([(27,y),(39,y)])
        else:
            line([(15,48),(24,30),(41,35),(50,14)])
            for x,y in ((15,48),(24,30),(41,35),(50,14)):
                d.ellipse(((x-4)*SCALE,(y-4)*SCALE,(x+4)*SCALE,(y+4)*SCALE),fill=c)
        save(im,f'tab-{kind}'+('-active' if active else '')+'.png',size)
for name,color,radius in [('start','#68d7a0',9),('end','#f27a86',9),('point','#6b97ff',7),('footprint-dot-fine','#6b97ff',2),('footprint-dot','#6b97ff',6),('footprint-dot-small','#6b97ff',3)]:
    size=(24,24);im,d=canvas(size)
    d.ellipse(((12-radius)*SCALE,(12-radius)*SCALE,(12+radius)*SCALE,(12+radius)*SCALE),fill=color)
    save(im,name+'.png',size)
print('Generated original geometric assets.')
