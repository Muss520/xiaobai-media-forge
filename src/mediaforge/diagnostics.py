"""Optional startup diagnostics for verifying a portable Windows installation."""
import json
import platform
from PySide6.QtCore import QTimer, qVersion, QThread, Signal
from .paths import tool_path,runtime_home,resource_home,documents_home
from .probe import run_tool
from .product import VERSION


def schedule_startup_check(app, window):
    ticks = [0]
    heartbeat = QTimer(window)
    heartbeat.timeout.connect(lambda: ticks.__setitem__(0, ticks[0] + 1))
    heartbeat.start(100)

    def finish(result):
        result['ui_timer_ticks'] = ticks[0]
        result['responsive'] = ticks[0] > 5
        result['passed'] = result['passed'] and result['responsive']
        (documents_home() / '成品启动验证.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        controller = getattr(window, 'controller', None)
        if controller:
            controller.request_exit()
        else:
            window.close()

    def check():
        folder = documents_home()
        folder.mkdir(parents=True, exist_ok=True)
        result = {'native_window': window.isVisible(), 'platform_plugin': app.platformName(),
                  'responsive': True, 'qt_version': qVersion(), 'python_version': platform.python_version(),
                  'window_size': [window.width(), window.height()], 'window_handle': int(window.winId())}
        result['version']=VERSION;result['runtime_home']=str(runtime_home());result['resource_home']=str(resource_home())
        result['device_pixel_ratio']=window.devicePixelRatioF()
        try:
            from dataclasses import asdict
            snapshots = {kind: asdict(panel.snapshot()) for kind, panel in window.panels.items()}
            result['default_simple_mode'] = window.ui_mode == 'simple'
            live=window.panels['live']
            result['live_video_primary']=live.base.labelForField(live.video_output).text()=='视频格式' and hasattr(window.simple_page.form,'live_video_output')
            controller = getattr(window, 'controller', None)
            if controller:
                result['desktop_cat_visible'] = controller.pet.isVisible()
                window.close()
                result['close_keeps_background'] = not window.isVisible() and not controller.exiting
                controller.show_window()
                result['restore_window'] = window.isVisible()
                from PySide6.QtCore import QPoint,QEvent
                from PySide6.QtTest import QTest
                from PySide6.QtWidgets import QPushButton
                from PySide6.QtGui import QPixmap
                controller.show_settings(); settings=controller.settings_dialog
                controller.show_settings()
                result['settings_single_instance']=controller.settings_dialog is settings
                original_scale=controller.pet.scale
                result['cat_all_sizes']=True
                for scale in range(2,7):
                    settings.cat_size.setValue(scale)
                    app.processEvents()
                    result['cat_all_sizes'] &= controller.pet.scale==scale and len(controller.pet.frames)==len(controller.pet.frame_anchors) and not controller.pet.mask().contains(QPoint(0,0))
                settings.cat_size.setValue(original_scale)
                settings.tabs.setCurrentIndex(1); app.processEvents()
                result['settings_screenshot']=settings.grab().save(str(folder/'成品小猫设置.png'))
                result['settings_five_pages']=[settings.tabs.widget(i).property('settingsPage') for i in range(settings.tabs.count())]==['appearance','pet','sound','usage','author']
                settings.tabs.setCurrentIndex(settings.page_index('sound'));app.processEvents()
                settings.grab().save(str(folder/'成品声音设置.png'))
                settings.tabs.setCurrentIndex(settings.page_index('author'));app.processEvents()
                from .product import NAME,EMAIL
                result['product_brand']=NAME in window.windowTitle() and app.applicationName()==NAME
                result['author_support_page']=settings.tabs.currentWidget().property('settingsPage')=='author' and not settings.reset_button.isVisible()
                result['payment_code_assets']=all(not QPixmap(str(card.image_path)).isNull() for card in settings.author_page.cards)
                from PySide6.QtCore import QMimeData
                previous=app.clipboard().mimeData();clipboard_copy=QMimeData()
                if previous:
                    for fmt in previous.formats():clipboard_copy.setData(fmt,previous.data(fmt))
                settings.author_page.copy_email();result['author_email_copy']=app.clipboard().text()==EMAIL
                if not result['author_email_copy']:
                    # Restricted Windows test desktops may deny clipboard access.
                    # Preserve the failed check and record that exact limitation;
                    # a normal accessible clipboard still has to pass the copy test.
                    import ctypes
                    user=ctypes.WinDLL('user32',use_last_error=True)
                    opened=user.OpenClipboard(None);error=ctypes.get_last_error()
                    if opened:user.CloseClipboard()
                    elif error==5:
                        result['clipboard_test_access_denied']=True
                        result['clipboard_verification']='Not verified: Windows OpenClipboard returned access denied (5) in this test desktop'
                app.clipboard().setMimeData(clipboard_copy)
                settings.grab().save(str(folder/'成品作者与打赏.png'))
                for card in settings.author_page.cards:
                    settings.tabs.currentWidget().ensureWidgetVisible(card.preview);app.processEvents()
                    settings.grab().save(str(folder/('成品收款码_'+card.image_path.stem+'.png')))
                settings.author_page.cards[0].open_large();app.processEvents()
                settings.author_page.cards[0].dialog.grab().save(str(folder/'成品放大二维码.png'))
                settings.author_page.cards[0].dialog.close();app.processEvents()
                settings.close(); app.processEvents()
                controller.pet.set_state('idle');original_sounds=controller.preferences.get('sounds',True)
                controller.preferences['sounds']=False;controller.sounds.apply_preferences()
                controller.open_play('wand');game=controller.play_dialog
                game.start();game.session.target=True;game.play_click();wand_ok=game.session.score==1
                game.pause();pause_ok=not game.timer.isActive();game.pause()
                game.grab().save(str(folder/'成品逗猫棒.png'));controller.stop_play()
                controller.open_play('ball');game=controller.play_dialog
                game.start();game.play_click();game.session.advance(.75);game.play_click();ball_ok=game.session.score==1
                game.grab().save(str(folder/'成品抛接球.png'))
                controller.pet.set_state('receiving')
                result['gameplay_and_cleanup']=wand_ok and pause_ok and ball_ok and controller.play_dialog is None and not game.timer.isActive()
                controller.pet.set_state('idle');controller.preferences['sounds']=original_sounds;controller.sounds.apply_preferences()
                window.set_ui_mode('advanced',False)
                result['stable_toolbar']=True
                for i in range(9):
                    window.tabs.setCurrentIndex(i%3)
                    button=window.findChild(QPushButton,'add_'+window.kind)
                    app.sendEvent(button,QEvent(QEvent.Enter)); app.sendEvent(button,QEvent(QEvent.Leave))
                    result['stable_toolbar'] &= button.isVisible() and button.graphicsEffect() is None
                    window.set_ui_mode('simple'); window.set_ui_mode('advanced')
                QTest.qWait(210)
                result['stable_toolbar'] &= window.advanced_page.graphicsEffect() is None
                result['control_icons']=all(not QPixmap(str(resource_home()/'assets'/name)).isNull() for name in ('chevron-down.svg','chevron-up.svg','check.svg'))
            window.set_ui_mode('advanced', False)
            result['advanced_all_pages'] = all(not panel.advanced.isHidden() for panel in window.panels.values())
            window.set_ui_mode('simple', False)
            window.set_ui_mode('information',False)
            result['information_mode']=window.view_stack.currentWidget() is window.information_page
            page=window.information_page
            result['information_three_tabs']=[page.tabs.tabText(i) for i in range(page.tabs.count())]==['常用信息','小白更改信息','完整标签']
            result['modified_copy_label']=page.export.text()=='导出修改版'
            page.tabs.setCurrentIndex(1);page.open_expanded();expanded=page.expanded_dialog
            page.open_expanded()
            result['information_expanded_shared']=page.expanded_dialog is expanded and expanded.isAncestorOf(page.surface)
            expanded.close();app.processEvents()
            result['information_expanded_restored']=page.isAncestorOf(page.surface) and page.tabs.currentIndex()==1
            page.tabs.setCurrentIndex(0)
            from .metadata_inputs import MetadataInput
            from PySide6.QtCore import QDate
            date=MetadataInput('date',None)
            result['missing_date_stays_empty']=date.serialized()==''
            date.set_value('2026:10:06 11:13:17+08:00');before=date.serialized()
            date.calendar_popup.calendar.showPreviousMonth()
            result['calendar_keeps_value']=before==date.serialized()
            date.pick_date(QDate(2025,12,31))
            result['calendar_keeps_time_zone']=date.serialized()=='2025:12:31 11:13:17+08:00'
            date.deleteLater()
            window.grab().save(str(folder/'成品信息模式.png'))
            window.set_ui_mode('simple',False)
            if controller:
                from .sound_catalog import CUES
                result['audio_assets']=set(CUES)==set(controller.sounds.effects) and all(effect.source().isLocalFile() and __import__('pathlib').Path(effect.source().toLocalFile()).is_file() for effect in controller.sounds.effects.values())
                result['companion_actions']=all(name in controller.pet.actions and len(controller.pet.actions[name])>=4 for name in ('wash','lick','scratch','sniff','ears','yawn','lie','hug','rub','snack','joy','shy','pounce','catch'))
                result['cat_topmost_flag']=bool(controller.pet.windowFlags() & __import__('PySide6.QtCore',fromlist=['Qt']).Qt.WindowStaysOnTopHint)
                controller.pet.set_state('complete'); controller.pet.settle_state()
                result['cat_terminal_settles']=controller.pet.state=='idle'
                result['explicit_sprite_bounds']=len(controller.pet.frame_anchors)==len(controller.pet.frames) and all(0<=index<len(controller.pet.frames) for sequence in controller.pet.actions.values() for index in sequence)
                images=[frame.toImage() for frame in controller.pet.base_frames]
                result['sprite_padding']=all(all(image.pixelColor(x,y).alpha()==0 for x,y in
                    [(x,y) for x in range(image.width()) for y in (0,image.height()-1)]+[(x,y) for x in (0,image.width()-1) for y in range(image.height())]) for image in images)
                controller.pet.ensure_topmost()
                import ctypes
                from ctypes import wintypes
                user=ctypes.windll.user32; user.GetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int]; user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
                result['cat_native_topmost']=bool(user.GetWindowLongPtrW(int(controller.pet.winId()),-20)&8)
            result['mode_preserves_parameters'] = snapshots == {kind: asdict(panel.snapshot()) for kind, panel in window.panels.items()}
            app.processEvents()
            result['screenshot_saved'] = window.grab().save(str(folder / '成品界面.png'))
            engine = run_tool([tool_path('ffmpeg'), '-version'], timeout=10)
            result['engine_ok'] = engine.returncode == 0
            result['engine_version'] = engine.stdout.splitlines()[0]
            exif = run_tool([tool_path('exiftool'), '-ver'], timeout=30)
            result['exiftool_ok'] = exif.returncode == 0 and '13.59' in exif.stdout
            result['exiftool_version'] = exif.stdout.strip()
            from PIL import Image
            import pillow_heif
            pillow_heif.register_heif_opener()
            Image.init()
            result['heif_ok'] = 'HEIF' in Image.OPEN and 'HEIF' in Image.SAVE
            result['avif_ok'] = 'AVIF' in Image.OPEN and 'AVIF' in Image.SAVE
            result['executable'] = __import__('sys').executable
            result['passed'] = (result['native_window'] and result['responsive'] and result['screenshot_saved']
                                and result['engine_ok'] and result['exiftool_ok'] and result['heif_ok']
                                and result['avif_ok'] and result['platform_plugin'] == 'windows')
            result['passed'] = result['passed'] and all(result[key] for key in ('default_simple_mode', 'advanced_all_pages', 'mode_preserves_parameters'))
            result['passed'] = result['passed'] and result['live_video_primary']
            result['passed'] = result['passed'] and result['information_mode']
            result['passed'] = result['passed'] and all(result[key] for key in ('information_three_tabs','modified_copy_label','information_expanded_shared','information_expanded_restored','missing_date_stays_empty','calendar_keeps_value','calendar_keeps_time_zone'))
            if controller:
                result['passed'] = result['passed'] and all(result[key] for key in ('desktop_cat_visible','close_keeps_background','restore_window'))
                result['passed'] = result['passed'] and all(result[key] for key in ('settings_single_instance','cat_all_sizes','settings_screenshot','stable_toolbar','control_icons'))
                result['passed'] = result['passed'] and all(result[key] for key in ('product_brand','author_support_page','payment_code_assets'))
                result['passed'] = result['passed'] and (result['author_email_copy'] or result.get('clipboard_test_access_denied',False))
                result['passed'] = result['passed'] and all(result[key] for key in ('audio_assets','cat_topmost_flag','cat_native_topmost','cat_terminal_settles'))
                result['passed'] = result['passed'] and result['companion_actions']
                result['passed'] = result['passed'] and result['settings_five_pages'] and result['gameplay_and_cleanup']
                result['passed'] = result['passed'] and result['explicit_sprite_bounds'] and result['sprite_padding']
        except Exception as error:
            result.update(passed=False, error=str(error))
        if '--verify-media' in __import__('sys').argv and result.get('passed'):
            window.smoke = PortableSmoke(window.home)
            def smoke_result(media):
                result['portable_media'] = media
                result['passed'] = result['passed'] and media.get('passed', False)
            window.smoke.result.connect(smoke_result)
            def media_finished():
                window.desktop_smoke = DesktopSmoke(window, lambda desktop: desktop_finished(desktop))
                window.desktop_smoke.start()
            def desktop_finished(desktop):
                result['desktop_workflow'] = desktop
                result['passed'] = result['passed'] and desktop.get('passed', False)
                finish(result)
            window.smoke.finished.connect(media_finished)
            window.smoke.start()
        else:
            finish(result)
    QTimer.singleShot(1500, check)


class DesktopSmoke:
    """Exercise the native cat drop/confirmation/queue in the actual executable."""
    def __init__(self, window, done):
        self.window, self.controller, self.done = window, window.controller, done
        self.timer = QTimer(window)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.poll)
        self.stage = 0
        self.report = {}

    def drop(self, paths):
        from PySide6.QtCore import QMimeData, QUrl, Qt
        from PySide6.QtGui import QDropEvent
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        self.controller.pet.dropEvent(QDropEvent(self.controller.pet.rect().center(),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier))

    def start(self):
        import tempfile, time, sys, shutil, subprocess
        from pathlib import Path
        from PIL import Image
        self.deadline = time.monotonic()+35
        try:
            self.temp = tempfile.TemporaryDirectory(prefix='desktop-smoke-',dir=runtime_home()/'temp')
            folder = Path(self.temp.name)
            a,b,c = (folder/name for name in ('照片 中文','视频 空格','Live'))
            for parent in (a,b,c):
                parent.mkdir()
            self.photo=a/'测试.png'
            Image.new('RGB',(80,60),'blue').save(self.photo)
            self.original=self.photo.read_bytes()
            clip=b/'原视频.mp4'
            encoded=run_tool([tool_path('ffmpeg'),'-v','error','-y','-f','lavfi','-i','testsrc2=s=160x120:r=24:d=1','-c:v','libx264',str(clip)])
            assert encoded.returncode==0,encoded.stderr
            fixtures=Path(sys.executable).parent/'源码/tests/artifacts/live-reference'
            if not fixtures.exists():
                fixtures=resource_home()/'tests/artifacts/live-reference'
            pair=[c/'照片.heic',c/'动态.mov']
            for source,target in zip((fixtures/'keyPhoto.heic',fixtures/'pairedVideo.mov'),pair):
                shutil.copyfile(source,target)
            command=[sys.executable] if getattr(sys,'frozen',False) else [sys.executable,str(resource_home()/'src/main.py')]
            self.secondary=subprocess.Popen(command,creationflags=subprocess.CREATE_NO_WINDOW)
            self.drop([self.photo,clip,*pair])
            self.timer.start()
        except Exception as error:
            self.end(error)

    def poll(self):
        import time
        try:
            assert time.monotonic()<self.deadline,'桌面流程验证超时'
            controller=self.controller
            if self.stage==0 and controller.dialog:
                assert {item for item in controller.dialog.form.kinds}=={'image','video','live'}
                assert not list(self.photo.parent.glob('转换结果*'))
                self.report['mixed_drop_and_confirmation']=True
                self.first_card=controller.dialog
                controller.dialog.form.store.edit('live','mode','both')
                controller.dialog.form.store.edit('live','format','jpg')
                controller.dialog.name.setText('转换结果_实测')
                controller.dialog.confirm.click()
                self.window.close()
                assert not self.window.isVisible() and controller.pet.isVisible()
                self.drop([self.photo])
                self.stage=1
            elif self.stage==1 and controller.dialog and controller.dialog is not self.first_card:
                controller.dialog.name.setText('转换结果_实测')
                controller.dialog.confirm.click()
                self.report['accepts_additional_batch']=True
                self.stage=2
            elif self.stage==2 and not controller.active_worker and not controller.pending and not controller.checks and self.secondary.poll() is not None:
                jobs=[j for values in self.window.jobs.values() for j in values]
                assert len(jobs)==4 and all(j.status=='完成' for j in jobs),[(j.status,j.error) for j in jobs]
                assert len({j.output.parent for j in jobs})==4
                assert self.photo.read_bytes()==self.original
                assert self.secondary.returncode==0
                self.report.update(source_grouping_and_collision=True,original_unchanged=True,second_instance_reused=True,close_during_processing=True,passed=True)
                controller.show_window()
                self.end()
        except Exception as error:
            self.end(error)

    def end(self,error=None):
        self.timer.stop()
        if error:
            self.report.update(passed=False,error=str(error))
        if hasattr(self,'secondary') and self.secondary.poll() is None:
            self.secondary.kill()
            self.secondary.wait()
        if hasattr(self,'temp') and not self.controller.active_worker:
            self.temp.cleanup()
        self.done(self.report)


class PortableSmoke(QThread):
    result = Signal(object)

    def __init__(self, root):
        super().__init__()
        self.root = root

    def run(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import threading, zipfile, sys
        from PIL import Image
        from .models import ImageOptions, VideoOptions, LiveOptions, Job
        from .images import process_image
        from .video import process_video
        from .live import process_live, verify_pair
        from .probe import probe
        report = {}
        try:
            with TemporaryDirectory(prefix='portable-smoke-', dir=runtime_home() / 'temp') as folder:
                folder = Path(folder)
                cancel = threading.Event()
                source = folder / '中文 空格 source.png'
                Image.effect_noise((240,160),50).convert('RGB').save(source)
                for fmt in ('heic', 'avif', 'jpg'):
                    out = folder / ('image.' + fmt)
                    process_image(probe(source), ImageOptions(format=fmt), out, cancel, lambda p: None)
                    assert probe(out).width == 240
                report['heic_avif_jpeg'] = True
                small = folder / 'target.jpg'
                process_image(probe(source), ImageOptions(target_bytes=6000), small, cancel, lambda p: None)
                assert small.stat().st_size <= 6000
                report['image_target_size'] = True
                clip = folder / '原视频.mp4'
                encoded = run_tool([tool_path('ffmpeg'),'-v','error','-y','-f','lavfi','-i',
                                    'testsrc2=s=160x120:r=24:d=1','-c:v','libx264','-crf','0',str(clip)])
                assert encoded.returncode == 0, encoded.stderr
                video = folder / 'target.mp4'
                process_video(probe(clip), VideoOptions(mode='size', target_bytes=18000), video, cancel, lambda p: None)
                assert video.stat().st_size <= 18000 and probe(video).video_codec == 'h264'
                report['video_target_size'] = True
                fixtures = Path(sys.executable).parent / '源码/tests/artifacts/live-reference'
                if not fixtures.exists():
                    fixtures = resource_home() / 'tests/artifacts/live-reference'
                photo, movie = fixtures / 'keyPhoto.heic', fixtures / 'pairedVideo.mov'
                assert photo.exists() and movie.exists(), '缺少真实 Live 测试样例'
                job = Job(photo, inputs=(photo,movie))
                output = folder / 'live.livp'
                process_live(job,LiveOptions(image=ImageOptions(width=160)),output,cancel,lambda p: None)
                with zipfile.ZipFile(output) as archive:
                    assert archive.read('photo.mov') == movie.read_bytes()
                    archive.extractall(folder / 'pair')
                verify_pair(folder/'pair/photo.jpg',folder/'pair/photo.mov')
                report['live_pair_and_original_mov'] = True
                both = folder / '普通照片与视频'
                both.mkdir()
                outputs=process_live(job,LiveOptions(mode='both',format='jpg'),both,cancel,lambda p:None)
                assert len(outputs)==2 and (both/'photo.mov').read_bytes()==movie.read_bytes()
                assert probe(both/'photo.jpg').width>0
                report['live_both_and_original_mov']=True
                recoded=folder/'Live 转码'; recoded.mkdir()
                process_live(job,LiveOptions(mode='both',format='png',video_copy=False,video=VideoOptions(width=160,height=160)),recoded,cancel,lambda p:None)
                assert probe(recoded/'photo.mp4').width<=160 and probe(recoded/'photo.png').width>0
                report['live_png_and_recoded_video']=True
                from .metadata import MetadataOptions,export_component,read_metadata,media_fingerprint
                meta_source=folder/'原信息.jpg'; exif=Image.Exif(); exif[315]='Original Author'; exif[274]=6
                Image.new('RGB',(80,60),'red').save(meta_source,exif=exif)
                meta_out=folder/'信息副本.jpg'
                meta_report=export_component(meta_source,meta_out,MetadataOptions(clear=True,edits=((0,'IFD0:Artist','新作者'),)),0,cancel,lambda p:None)
                assert read_metadata(meta_out)['IFD0:Artist']=='新作者'
                assert media_fingerprint(meta_out,cancel)==media_fingerprint(meta_source,cancel)
                report['metadata_original_quality_edit_clear']=meta_report['original_quality_verified']
                report['passed'] = True
        except Exception as error:
            report.update(passed=False,error=str(error))
        self.result.emit(report)
