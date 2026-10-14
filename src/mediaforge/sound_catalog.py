"""Bundled offline audio cue definitions shared by playback and acceptance."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Cue:
    group:str
    duration:float
    cooldown:float=.3
    priority:int=0
    voice:bool=False

CUES={
    'receive':Cue('conversion',.16,.5,1),'start':Cue('conversion',.24,.5,1),
    'complete':Cue('conversion',.42,.5,3),'failed':Cue('conversion',.35,.5,3),
    'pet_touch':Cue('pet',.16,.6),'rub':Cue('pet',.28,.8),'snack':Cue('pet',.4,.8),
    'meow':Cue('pet',.62,8,0,True),'purr':Cue('pet',1.1,8,0,True),'joy':Cue('pet',.28,.8),
    'wand':Cue('game',.1,.5),'throw':Cue('game',.2,.3),'bounce':Cue('game',.16,.3),
    'catch':Cue('game',.26,.3),'miss':Cue('game',.17,.5),'game_finish':Cue('game',.45,.8),
}
