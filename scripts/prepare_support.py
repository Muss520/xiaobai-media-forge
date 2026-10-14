"""Deterministic pixel-preserving crops of the author's supplied payment codes."""
import hashlib,json
from PIL import Image,ImageOps
import zxingcpp
from project_layout import DEV,PROJECT,DOCS

destination=DEV/'assets/support';destination.mkdir(parents=True,exist_ok=True)
codes=[]
# Keep the entire code, embedded portrait/mark and existing white pixels.
# Additional white canvas guarantees a quiet border without resampling any pixels.
for original,asset,box,padding in (
    ('微信.jpg','wechat.png',(360,400,900,940),60),
    ('支付宝.jpg','alipay.png',(228,690,1030,1492),80),
):
    source=PROJECT/'收款码'/original
    with Image.open(source) as opened: image=opened.convert('RGB')
    before=zxingcpp.read_barcodes(image)
    assert len(before)==1,f'Cannot read original {original}'
    cropped=ImageOps.expand(image.crop(box),border=padding,fill='white')
    after=zxingcpp.read_barcodes(cropped)
    assert len(after)==1 and after[0].bytes==before[0].bytes,f'Changed QR content {original}'
    path=destination/asset;cropped.save(path,format='PNG')
    codes.append({'original':original,'asset':asset,'box':list(box),'padding':padding,'size':list(cropped.size),
                  'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                  'asset_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                  'payload_sha256':hashlib.sha256(before[0].bytes).hexdigest(),'decoded_equal':True})
manifest={'codes':codes,'method':'original pixel crop plus white canvas; no resize or redraw'}
(destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(DOCS/'3.7_二维码资源校验.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('Both original codes and lossless crops decode identically; source pixels preserved.')
