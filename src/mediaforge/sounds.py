"""Short bundled WAV cues, optional and independent of media processing."""
import logging
import time
from PySide6.QtCore import QObject,QUrl
from .paths import resource_home
from .sound_catalog import CUES

class SoundBank(QObject):
    def __init__(self,preferences,parent=None):
        super().__init__(parent);self.preferences=preferences;self.effects={}
        self.clock=time.monotonic;self.last_played={};self.last_voice=float('-inf');self.priority_until=0
        try:
            from PySide6.QtMultimedia import QSoundEffect
            root=resource_home()/'assets/sounds'
            for name in CUES:
                effect=QSoundEffect(self);effect.setSource(QUrl.fromLocalFile(str(root/(name+'.wav'))));self.effects[name]=effect
        except Exception:logging.warning('音效不可用，媒体处理继续',exc_info=True)
        self.apply_preferences()

    def enabled(self,name):
        cue=CUES[name];group=self.preferences.get('sound_groups',{}).get(cue.group,{})
        return bool(self.preferences.get('sounds',True) and group.get('enabled',True)
                    and (not cue.voice or self.preferences.get('cat_voice',True)))

    def volume(self,name):
        group=self.preferences.get('sound_groups',{}).get(CUES[name].group,{})
        return max(0,min(1,self.preferences.get('sound_volume',20)*group.get('volume',100)/10000))

    def apply_preferences(self):
        for name,effect in self.effects.items():
            effect.setVolume(self.volume(name))
            if not self.enabled(name) or self.volume(name)==0:effect.stop()
        if not self.preferences.get('sounds',True) or not self.preferences.get('sound_groups',{}).get('conversion',{}).get('enabled',True):self.priority_until=0

    def stop_group(self,group):
        for name,effect in self.effects.items():
            if CUES[name].group==group:effect.stop()
        if group=='conversion':self.priority_until=0

    def stop_all(self):
        for effect in self.effects.values():effect.stop()
        self.priority_until=0

    def play(self,name,preview=False):
        if name not in self.effects or not self.enabled(name) or self.volume(name)==0:return False
        cue=CUES[name];now=self.clock()
        if cue.priority<3 and now<self.priority_until:return False
        if cue.voice and now-self.last_voice<8:return False
        if not preview and now-self.last_played.get(name,float('-inf'))<cue.cooldown:return False
        try:
            self.stop_group(cue.group)
            if cue.priority==3:
                self.stop_group('pet');self.stop_group('game');self.priority_until=now+cue.duration
            effect=self.effects[name];effect.setVolume(self.volume(name));effect.play()
            self.last_played[name]=now
            if cue.voice:self.last_voice=now
            return True
        except Exception:
            logging.warning('播放音效失败，媒体处理继续',exc_info=True)
            return False
