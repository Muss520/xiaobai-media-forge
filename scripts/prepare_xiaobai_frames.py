"""Repack generated Xiaobai artwork into explicit, padded frames (no redraw)."""
from pathlib import Path
from collections import deque
import json
from PIL import Image
root=Path(__file__).resolve().parents[1]; assets=root/'assets'
image=Image.open(assets/'xiaobai-atlas.png').convert('RGBA'); width,height=image.size
alpha=image.getchannel('A'); pending=bytearray(v>32 for v in alpha.get_flattened_data()); components=[]
for index in range(width*height):
    if not pending[index]:continue
    pending[index]=0;queue=deque([index]);pixels=[];left=right=index%width;top=bottom=index//width
    while queue:
        item=queue.popleft();pixels.append(item);x,y=item%width,item//width
        left=min(left,x);right=max(right,x);top=min(top,y);bottom=max(bottom,y)
        for neighbor in ((item-1 if x else -1),(item+1 if x<width-1 else -1),item-width,item+width):
            if 0<=neighbor<width*height and pending[neighbor]:pending[neighbor]=0;queue.append(neighbor)
    components.append({'pixels':pixels,'box':(left,top,right+1,bottom+1)})
bodies=[c for c in components if len(c['pixels'])>800]
assert len(bodies)==36,'Unexpected artwork topology; do not guess the frame order'
bodies.sort(key=lambda c:c['box'][1]);ordered=[]
for row in range(6):ordered.extend(sorted(bodies[row*6:(row+1)*6],key=lambda c:c['box'][0]))
body_ids={id(body) for body in bodies};groups=[[body] for body in ordered]
for component in components:
    if id(component) in body_ids or len(component['pixels'])<4:continue
    left,top,right,bottom=component['box'];x,y=(left+right)/2,(top+bottom)/2
    def distance(body):
        a,b,c,d=body['box'];dx=max(a-x,0,x-c);dy=max(b-y,0,y-d)
        return dx*dx+dy*dy
    nearest=min(range(36),key=lambda i:distance(ordered[i]))
    if distance(ordered[nearest])<65**2:groups[nearest].append(component)
# Common scale and foot anchor; each connected cat is isolated from adjacent rows.
patches=[];extents=[]
factor=27/max(max(body["box"][2]-body["box"][0],body["box"][3]-body["box"][1]) for body in ordered)
for body,group in zip(ordered,groups):
    left,top,right,bottom=body['box'];anchor=((left+right)/2,bottom)
    # Keep every cat pixel. Separate decorative specks are kept only when the whole
    # component fits the padded cell; never leave a clipped fragment at an edge.
    selected=[]
    for part in group:
        a,b,c,d=part['box']
        if part is body or (16+(a-anchor[0])*factor>=1 and 16+(c-anchor[0])*factor<=31 and 30+(b-anchor[1])*factor>=1 and 30+(d-anchor[1])*factor<=31):selected.append(part)
    points=[point for part in selected for point in part['pixels']]
    box=(min(p%width for p in points),min(p//width for p in points),max(p%width for p in points)+1,max(p//width for p in points)+1)
    crop=image.crop(box);mask=Image.new('L',crop.size);data=mask.load()
    for point in points:data[point%width-box[0],point//width-box[1]]=alpha.getpixel((point%width,point//width))
    crop.putalpha(mask);patches.append((crop,box,anchor))
    extents.append(max(2*(anchor[0]-box[0]),2*(box[2]-anchor[0]),anchor[1]-box[1]))
sheet=Image.new('RGBA',(192,192));frames=[]
for index,(crop,box,anchor) in enumerate(patches):
    scaled=crop.resize((max(1,round(crop.width*factor)),max(1,round(crop.height*factor))),Image.Resampling.NEAREST)
    canvas=Image.new('RGBA',(32,32));x=16-round((anchor[0]-box[0])*factor);y=30-round((anchor[1]-box[1])*factor)
    canvas.alpha_composite(scaled,(x,y));col,row=index%6,index//6;sheet.alpha_composite(canvas,(col*32,row*32))
    frames.append({'rect':[col*32,row*32,32,32],'anchor':[16,30],'source_body':list(ordered[index]['box'])})
sheet.save(assets/'xiaobai-frames.png')
manifest=json.loads((assets/'xiaobai-states.json').read_text(encoding='utf-8'));manifest['image']='xiaobai-frames.png';manifest['frames']=frames
(assets/'xiaobai-states.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('36 isolated frames, common scale, anchor (16,30)')
