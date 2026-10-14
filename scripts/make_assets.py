"""Recreate proportional, padded Windows icons from the generated Xiaobai face."""
from pathlib import Path
from PIL import Image
folder=Path(__file__).resolve().parents[1]/'assets'
image=Image.open(folder/'xiaobai-logo.png').convert('RGBA')
bounds=image.getchannel('A').point(lambda value:255 if value>=32 else 0).getbbox()
image=image.crop(bounds);image.thumbnail((224,224),Image.Resampling.NEAREST)
canvas=Image.new('RGBA',(256,256));canvas.alpha_composite(image,((256-image.width)//2,(256-image.height)//2))
canvas.save(folder/'mediaforge.png');canvas.save(folder/'mediaforge.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
