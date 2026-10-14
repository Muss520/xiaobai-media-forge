"""Isolate generated action bodies; normalize pixels and anchor, never slice blindly."""
from pathlib import Path
from collections import deque
import json,hashlib,math
from PIL import Image
from project_layout import DEV,DOCS

assets=DEV/'assets';path=assets/'xiaobai-states.json'
manifest=json.loads(path.read_text(encoding='utf-8'))
with Image.open(assets/manifest['image']) as existing:
    classic=[existing.crop((f['rect'][0],f['rect'][1],f['rect'][0]+f['rect'][2],f['rect'][1]+f['rect'][3])).convert('RGBA') for f in manifest['frames'][:36]]
image=Image.open(assets/'xiaobai-actions-38-source.png').convert('RGBA');w,h=image.size
alpha=image.getchannel('A');pending=bytearray(a>128 for a in alpha.get_flattened_data());bodies=[]
for index in range(w*h):
    if not pending[index]:continue
    pending[index]=0;queue=deque([index]);points=[];left=right=index%w;top=bottom=index//w
    while queue:
        point=queue.popleft();points.append(point);x,y=point%w,point//w
        left=min(left,x);right=max(right,x);top=min(top,y);bottom=max(bottom,y)
        for neighbor in (point-1 if x else -1,point+1 if x<w-1 else -1,point-w,point+w):
            if 0<=neighbor<w*h and pending[neighbor]:pending[neighbor]=0;queue.append(neighbor)
    if len(points)>1800:bodies.append({'box':(left,top,right+1,bottom+1),'points':points})
assert len(bodies)==56,'Unexpected atlas topology; explicit frame review required'
bodies.sort(key=lambda b:b['box'][1]);ordered=[]
for row in range(7):ordered.extend(sorted(bodies[row*8:row*8+8],key=lambda b:b['box'][0]))
factor=27/max(max(b['box'][2]-b['box'][0],b['box'][3]-b['box'][1]) for b in ordered)
names=('wash','lick','scratch','sniff','ears','yawn','lie','hug','rub','snack','joy','shy','pounce','catch')
actions={key:value for key,value in manifest['actions'].items() if key not in names}
frames=classic[:];records=[]
for action_index,name in enumerate(names):
    row=action_index//2;start=row*8+(action_index%2)*4;actions[name]=[]
    ground=max(b['box'][3] for b in ordered[start:start+4])
    for body in ordered[start:start+4]:
        l,t,r,b=body['box'];crop=image.crop((l,t,r,b));mask=Image.new('L',crop.size);data=mask.load()
        for p in body['points']:data[p%w-l,p//w-t]=alpha.getpixel((p%w,p//w))
        crop.putalpha(mask);crop=crop.resize((max(1,round(crop.width*factor)),max(1,round(crop.height*factor))),Image.Resampling.NEAREST)
        # Stable, crisp native pixels; remove antialiasing halo from the generated source.
        crop.putdata([(0,0,0,0) if a<128 else ((0,0,0,255) if (r+g+b)<450 else (255,255,255,255)) for r,g,b,a in crop.get_flattened_data()])
        canvas=Image.new('RGBA',(32,32));jump=round((ground-b)*factor) if name=='joy' else 0
        canvas.alpha_composite(crop,((32-crop.width)//2,30-crop.height-jump))
        assert canvas.getbbox() and canvas.getbbox()[0]>0 and canvas.getbbox()[1]>0 and canvas.getbbox()[2]<32 and canvas.getbbox()[3]<32
        actions[name].append(len(frames));frames.append(canvas);records.append({'action':name,'source_box':list(body['box']),'jump_offset':jump})
columns=10;rows=math.ceil(len(frames)/columns);sheet=Image.new('RGBA',(columns*32,rows*32));descriptors=[]
for index,frame in enumerate(frames):
    x,y=index%columns*32,index//columns*32;sheet.alpha_composite(frame,(x,y))
    descriptors.append({'rect':[x,y,32,32],'anchor':[16,30]})
sheet.save(assets/'xiaobai-frames.png')
manifest.update(schema_version=2,image='xiaobai-frames.png',columns=columns,rows=rows,frames=descriptors,actions=actions)
manifest['action_specs']={name:{'frame_ms':360 if name in {'lie','hug','yawn'} else 220,'loops':1} for name in names}
manifest['new_frame_sources']=records
path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
report={'passed':True,'classic_frames_preserved':len(classic),'new_frames':56,'total_frames':len(frames),'actions':list(actions),
        'source_sha256':hashlib.sha256((assets/'xiaobai-actions-38-source.png').read_bytes()).hexdigest(),'explicit_connected_bounds':True}
(DOCS/'3.8_动作素材检查.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
