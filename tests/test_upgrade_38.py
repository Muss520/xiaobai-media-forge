import json
import random
from pathlib import Path
import pytest


def test_old_preferences_keep_volume_and_get_quiet_companion_defaults():
    from mediaforge.preferences import normalize_desktop
    prefs=normalize_desktop({'sounds':False,'sound_volume':37,'quick':{'live':{'video_format':'mkv'}}})
    assert prefs['sound_volume']==37 and not prefs['sounds']
    assert prefs['idle_activity']=='standard' and prefs['idle_voice'] is False
    assert prefs['sound_groups']=={name:{'enabled':True,'volume':100} for name in ('conversion','pet','game')}
    assert prefs['quick']['live']['video_format']=='mkv'


def test_idle_scheduler_varies_without_repeating_and_respects_ranges():
    from mediaforge.companion import IdleScheduler
    scheduler=IdleScheduler(random.Random(7))
    for activity,limits in [('quiet',(20,40)),('standard',(10,25)),('lively',(5,15))]:
        previous=None;seen=set()
        for _ in range(240):
            action,seconds=scheduler.next(activity)
            assert action!=previous and limits[0]<=seconds<=limits[1]
            previous=action;seen.add(action)
        assert {'wash','lick','scratch','sniff','ears','yawn','lie','hug'}<=seen


def test_ball_game_uses_elapsed_time_pause_and_catch_window():
    from mediaforge.play import PlaySession
    game=PlaySession('ball');game.start()
    game.advance(.2);assert game.remaining==pytest.approx(29.8)
    assert game.click()=='throw'
    game.advance(.75);assert game.click()=='catch' and game.score==1
    game.pause();left=game.remaining;game.advance(3);assert game.remaining==left
    game.pause();game.advance(40);assert game.finished and game.remaining==0
    game.start();assert game.score==0 and not game.finished


def test_wand_click_requires_target_and_gameplay_gate(qt_app,tmp_path):
    from mediaforge.controller import AppController
    c=AppController(qt_app,tmp_path/'settings.json',quit_application=False);c.window.hardware_enabled=False
    try:
        assert hasattr(c,'open_play')
        c.open_play('wand');first=c.play_dialog;assert first and first.isVisible()
        c.open_play('ball');assert c.play_dialog is first
        first.session.start();first.session.target=False;assert first.session.click()=='miss'
        first.session.target=True;assert first.session.click()=='catch'
        c.stop_play();assert c.play_dialog is None and not first.timer.isActive()
        c.window.busy=True;c.open_play('ball');assert c.play_dialog is None
    finally:c.window.busy=False;c.request_exit()


def test_new_assets_have_four_distinct_safe_frames_for_each_action():
    from PIL import Image
    root=Path(__file__).parents[1]/'assets'
    manifest=json.loads((root/'xiaobai-states.json').read_text(encoding='utf-8'))
    added=('wash','lick','scratch','sniff','ears','yawn','lie','hug','rub','snack','joy','shy','pounce','catch')
    with Image.open(root/manifest['image']) as sheet:
        for action in added:
            sequence=manifest['actions'].get(action,[])
            assert len(sequence)>=4,action
            pixels=[]
            for index in sequence:
                frame=manifest['frames'][index];x,y,w,h=frame['rect'];image=sheet.crop((x,y,x+w,y+h)).convert('RGBA')
                assert image.getbbox() and image.getbbox()[0]>0 and image.getbbox()[1]>0
                assert image.getbbox()[2]<w and image.getbbox()[3]<h
                pixels.append(image.tobytes())
            assert len(set(pixels))>=4,action


def test_sound_preferences_apply_immediately_and_conversion_has_priority(qt_app,monkeypatch):
    from mediaforge.sounds import SoundBank
    from mediaforge.preferences import normalize_desktop
    from PySide6 import QtMultimedia
    class Effect:
        def __init__(self,parent):self.playing=False;self.volume=0
        def setSource(self,source):pass
        def setVolume(self,value):self.volume=value
        def stop(self):self.playing=False
        def play(self):self.playing=True
        def isPlaying(self):return self.playing
    monkeypatch.setattr(QtMultimedia,'QSoundEffect',Effect)
    prefs=normalize_desktop({});bank=SoundBank(prefs)
    assert hasattr(bank,'apply_preferences')
    clock=[10.0];bank.clock=lambda:clock[0]
    assert bank.play('meow') and bank.effects['meow'].playing
    assert not bank.play('meow')
    assert not bank.play('meow',preview=True)
    clock[0]+=1;assert bank.play('complete')
    assert not bank.effects['meow'].playing and not bank.play('catch')
    prefs['sound_volume']=50;bank.apply_preferences();assert bank.effects['complete'].volume==.5
    prefs['sounds']=False;bank.apply_preferences();assert not any(effect.playing for effect in bank.effects.values())


def test_five_settings_pages_sound_groups_and_reset_isolation(qt_app,tmp_path):
    from mediaforge.controller import AppController
    c=AppController(qt_app,tmp_path/'settings.json',quit_application=False);c.window.hardware_enabled=False
    try:
        c.show_settings();s=c.settings_dialog
        assert [s.tabs.tabText(i) for i in range(s.tabs.count())]==['界面','小白','声音','保存与使用','作者与打赏']
        c.preferences['folder_prefix']='作品';c.preferences['idle_activity']='lively'
        enabled,slider,label=s.group_controls['pet'];slider.setValue(45);enabled.setChecked(False)
        assert c.preferences['sound_groups']['pet']=={'enabled':False,'volume':45}
        s.reset_page('sound')
        assert c.preferences['sound_volume']==20 and c.preferences['sound_groups']['pet']['enabled']
        assert c.preferences['folder_prefix']=='作品' and c.preferences['idle_activity']=='lively'
        s.idle_voice.setChecked(True);s.activity.setCurrentIndex(0)
        assert c.preferences['idle_voice'] and c.preferences['idle_activity']=='quiet'
        again=json.loads((tmp_path/'settings.json').read_text(encoding='utf-8'))
        assert again['desktop']['idle_voice'] and again['desktop']['idle_activity']=='quiet'
    finally:c.request_exit()


def test_games_wait_for_terminal_feedback_and_hidden_pet(qt_app,tmp_path):
    from mediaforge.controller import AppController
    c=AppController(qt_app,tmp_path/'settings.json',quit_application=False);c.window.hardware_enabled=False
    try:
        c.pet.set_state('complete');assert c.pet.state_reset.isActive()
        c.open_play('ball');assert c.play_dialog is None and c.pet.state_reset.isActive()
        c.pet.set_state('idle');c.pet.hide();c.open_play('wand');assert c.play_dialog is None
    finally:c.request_exit()


def test_readers_preempt_running_game_and_idle_resumes(qt_app,tmp_path):
    from mediaforge.controller import AppController
    c=AppController(qt_app,tmp_path/'settings.json',quit_application=False);c.window.hardware_enabled=False
    try:
        c.open_play('ball');game=c.play_dialog;game.start()
        sentinel=object();c.window.information_page.loaders.append(sentinel)
        assert not c.can_play()
        game.play_click()
        assert c.play_dialog is None and not game.timer.isActive() and not game.session.active
        c.pet.set_state('idle');assert not c.pet.timer.isActive()
        c.window.information_page.loaders.clear();c.pet.update_progress()
        assert c.pet.timer.isActive() and c.pet.idle_waiting
        c.open_play('wand');game=c.play_dialog;game.start()
        c.window.inspectors.append(sentinel);game.tick()
        assert c.play_dialog is None and not game.timer.isActive()
        c.window.inspectors.clear()
    finally:
        c.window.inspectors.clear();c.window.information_page.loaders.clear();c.request_exit()


def test_tray_gates_refresh_and_reduced_game_updates_live(qt_app,tmp_path):
    from mediaforge.controller import AppController
    c=AppController(qt_app,tmp_path/'settings.json',quit_application=False);c.window.hardware_enabled=False
    try:
        menu=c.tray.contextMenu();games=next(a.menu() for a in menu.actions() if a.text()=='小白游乐场')
        c.preferences['games_enabled']=False;menu.aboutToShow.emit()
        assert not any(a.isEnabled() for a in games.actions())
        c.preferences['games_enabled']=True;menu.aboutToShow.emit()
        assert all(a.isEnabled() for a in games.actions())
        c.open_play('ball');game=c.play_dialog;game.start();c.set_motion(True)
        assert game.timer.interval()==100
        c.set_motion(False);assert game.timer.interval()==33
    finally:c.request_exit()


def test_large_game_instructions_and_settings_status_fit(qt_app,tmp_path):
    from mediaforge.controller import AppController
    from PySide6.QtTest import QTest
    c=AppController(qt_app,tmp_path/'settings.json',quit_application=False);c.window.hardware_enabled=False
    try:
        c.window.ui_preferences['font_points']=20;c.apply_appearance();c.open_play('ball');game=c.play_dialog
        QTest.qWait(30)
        assert game.help.height()>=game.help.heightForWidth(game.help.width())
        assert game.status.height()>=game.status.fontMetrics().height()*2
        c.show_settings();s=c.settings_dialog;s.resize(480,740);QTest.qWait(30)
        assert s.save_status.height()<=s.save_status.fontMetrics().height()*2
    finally:c.request_exit()


def test_email_copy_does_not_report_success_when_clipboard_rejects(qt_app,monkeypatch):
    from mediaforge.support import AuthorPage,QApplication
    class UnavailableClipboard:
        def setText(self,value):pass
        def text(self):return ''
    monkeypatch.setattr(QApplication,'clipboard',lambda:UnavailableClipboard())
    page=AuthorPage()
    try:
        assert page.copy_email() is False
        assert '未能复制' in page.copy_status.text()
    finally:page.close();page.deleteLater()
