"""One resolution policy for preview, preflight and all media execution paths."""
from dataclasses import replace
from fractions import Fraction
from .models import VideoOptions,ImageOptions,LiveOptions,target_size

RESOLUTIONS=[('原尺寸','original'),('480p · 854 × 480','480p'),('720p · 1280 × 720','720p'),
             ('1080p · 1920 × 1080','1080p'),('1440p · 2560 × 1440','1440p'),('4K · 3840 × 2160','2160p'),('自定义宽高','custom')]
BOUNDS={'480p':(854,480),'720p':(1280,720),'1080p':(1920,1080),'1440p':(2560,1440),'2160p':(3840,2160)}


def resolve_options(info,options):
    if not isinstance(options,(ImageOptions,VideoOptions)):return options
    if isinstance(options,VideoOptions) and options.remux:return options
    if options.resolved_size:return options
    key=options.resolution_preset
    if key not in {'original','custom',*BOUNDS}:raise ValueError('分辨率预设无效')
    width,height=options.width,options.height
    aspect=options.aspect
    if key in BOUNDS:
        width,height=BOUNDS[key]
        sar=float(Fraction(info.sample_aspect_ratio)) if isinstance(options,VideoOptions) else 1
        if info.width*sar<info.height:width,height=height,width
        # The frame box describes display dimensions, while the scaler works in coded pixels.
        width=max(1,int(width/sar))
        aspect=True
    actual=target_size(info.width,info.height,width,height,aspect,options.upscale)
    if isinstance(options,VideoOptions):actual=tuple(max(2,n//2*2) for n in actual)
    return replace(options,width=actual[0],height=actual[1],aspect=aspect,resolution_preset='custom',resolved_size=True)


def resolve_live(options,picture,video):
    return replace(options,image=resolve_options(video if options.mode=='animation' else picture,options.image),
                   video=resolve_options(video,options.video))
