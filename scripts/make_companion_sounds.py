"""Original procedural mono WAV cues; no downloaded or copyrighted recordings."""
import math,random,struct,wave,json,hashlib
from project_layout import DEV,DOCS
from mediaforge.sound_catalog import CUES

rate=22050;root=DEV/'assets/sounds';root.mkdir(exist_ok=True);records=[]
for index,(name,cue) in enumerate(CUES.items()):
    if name in {'receive','start','complete','failed'}:continue
    rng=random.Random(index);samples=[];duration=cue.duration
    for i in range(round(rate*duration)):
        t=i/rate;phase=t/duration;envelope=math.sin(math.pi*phase)**1.5
        if name=='meow':
            # Gentle cartoon vocal harmonics with a falling, vowel-like glide.
            f=540+380*math.sin(math.pi*phase)-190*phase
            signal=sum(math.sin(2*math.pi*f*t*k)/(k*k) for k in range(1,7))*.18
        elif name=='purr':signal=(math.sin(2*math.pi*100*t)+.4*math.sin(2*math.pi*205*t))*(.4+.6*math.sin(2*math.pi*24*t)**2)*.12
        elif name in {'wand','rub','snack'}:
            signal=rng.uniform(-1,1)*(.07 if name=='wand' else .1)*(math.sin(2*math.pi*(22 if name=='snack' else 5)*t)**2)
        else:
            base={'pet_touch':880,'joy':660,'throw':440,'bounce':340,'catch':980,'miss':300,'game_finish':720}.get(name,660)
            glide=(1+phase*.5) if name in {'joy','catch','game_finish'} else (1-phase*.45)
            signal=(math.sin(2*math.pi*base*glide*t)+.2*math.sin(2*math.pi*base*2*t))*.16
        samples.append(round(max(-.9,min(.9,signal*envelope))*32767))
    path=root/(name+'.wav')
    with wave.open(str(path),'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(rate);out.writeframes(struct.pack('<'+'h'*len(samples),*samples))
    records.append({'name':name,'group':cue.group,'seconds':duration,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
report={'original_procedural_synthesis':True,'sample_rate':rate,'channels':1,'bits':16,'cues':records}
(root/'companion-sounds.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(DOCS/'3.8_音效素材检查.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Created {len(records)} original offline cues')
