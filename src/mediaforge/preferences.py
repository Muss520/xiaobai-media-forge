"""Validated presentation preferences, independent of media parameters."""
UI_DEFAULTS={'density':'comfortable','text_size':'standard','navigation':'standard','splitters':{}}
CHOICES={'density':('comfortable','compact'),'text_size':('small','standard','large'),'navigation':('narrow','standard','wide')}


def normalize_ui(value):
    value=value if isinstance(value,dict) else {}
    result={key:value.get(key) if value.get(key) in options else UI_DEFAULTS[key] for key,options in CHOICES.items()}
    result['splitters']={}
    for key,low,high,default in [('font_points',12,20,12),('spacing',6,24,12),('navigation_width',110,220,150)]:
        raw=value.get(key)
        result[key]=raw if type(raw) is int and low<=raw<=high else default
    result['detailed_columns']=value.get('detailed_columns') if type(value.get('detailed_columns')) is bool else False
    sizes=value.get('splitters',{})
    if isinstance(sizes,dict):
        for kind in ('video','image','live'):
            ratio=sizes.get(kind)
            if type(ratio) in (float,int) and .25<=ratio<=.8:
                result['splitters'][kind]=ratio
    return result


def normalize_desktop(value):
    result=dict(value) if isinstance(value,dict) else {}
    if type(result.get('scale')) is not int or not 2<=result['scale']<=6:
        result['scale']=3
    for name in ('visible','show_progress','sounds','notifications'):
        result[name]=result.get(name) if type(result.get(name)) is bool else True
    if not isinstance(result.get('quick',{}),dict):
        result['quick']={}
    from .formats import VIDEO_FORMATS,IMAGE_FORMATS
    saved=result.get('quick',{}); quick={}
    for kind in ('video','image','live'):
        values=saved.get(kind,{})
        values=values if isinstance(values,dict) else {}
        preset=values.get('preset')
        value={'preset':preset if preset in ('balanced','high','small') else 'balanced'}
        if kind=='live':
            mode=values.get('mode')
            mode=mode if mode in ('preserve','video','image','animation','both') else 'both'
            value['mode']=mode
            video=values.get('video_format','original_mov')
            value['video_format']=video if video=='original_mov' or video in VIDEO_FORMATS else 'original_mov'
            allowed={'livp','folder'} if mode=='preserve' else VIDEO_FORMATS if mode=='video' else {'gif','webp','apng'} if mode=='animation' else IMAGE_FORMATS
            default='livp' if mode=='preserve' else 'mp4' if mode=='video' else 'gif' if mode=='animation' else 'png'
        else:
            allowed=VIDEO_FORMATS if kind=='video' else IMAGE_FORMATS
            default='mp4' if kind=='video' else 'jpg'
        fmt=values.get('format')
        value['format']=fmt if isinstance(fmt,str) and fmt in allowed else default
        quick[kind]=value
    result['quick']=quick
    result['sound_volume']=result.get('sound_volume') if type(result.get('sound_volume')) is int and 0<=result['sound_volume']<=100 else 20
    result['idle_activity']=result.get('idle_activity') if result.get('idle_activity') in ('quiet','standard','lively') else 'standard'
    for key,default in (('hover_reactions',True),('games_enabled',True),('cat_voice',True),('idle_voice',False)):
        result[key]=result.get(key) if type(result.get(key)) is bool else default
    groups=result.get('sound_groups',{});groups=groups if isinstance(groups,dict) else {}
    result['sound_groups']={}
    for name in ('conversion','pet','game'):
        group=groups.get(name,{});group=group if isinstance(group,dict) else {}
        volume=group.get('volume',100)
        result['sound_groups'][name]={'enabled':group.get('enabled') if type(group.get('enabled')) is bool else True,
            'volume':volume if type(volume) is int and 0<=volume<=100 else 100}
    result['open_results']=result.get('open_results') if type(result.get('open_results')) is bool else False
    from .workflow import validate_folder_name
    try:result['folder_prefix']=validate_folder_name(result.get('folder_prefix','转换结果'))
    except (ValueError,TypeError):result['folder_prefix']='转换结果'
    return result
