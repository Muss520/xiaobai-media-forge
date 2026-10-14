"""Typed metadata inputs shared by the easy form and the explicit editor."""
import json,re,math
from datetime import datetime
from PySide6.QtCore import Qt,QDate,Signal,QSignalBlocker,QLocale
from PySide6.QtGui import QDoubleValidator,QTextCharFormat,QColor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,
    QCalendarWidget,QComboBox,QSpinBox,QListWidget,QCheckBox)
from .metadata_fields import parse_coordinates

CALENDAR_STYLE='''
QWidget#metadataCalendar {background:#fcfbf7;border:1px solid #c8c1b2;border-radius:8px;}
QWidget#calendarHeader {background:transparent;border:none;}
QWidget#metadataCalendar QPushButton {padding:3px 8px;min-height:26px;min-width:24px;color:#474239;background:#f4f1e8;border:1px solid #d5cebf;border-radius:5px;}
QWidget#metadataCalendar QComboBox,QWidget#metadataCalendar QSpinBox {padding:3px 6px;min-height:26px;background:#fcfbf7;border:1px solid #d5cebf;border-radius:5px;}
QWidget#metadataCalendar QAbstractItemView {background:#fcfbf7;color:#34332f;selection-background-color:#686153;selection-color:#fffdf8;outline:0;border:none;}
QWidget#metadataCalendar QLabel {background:transparent;border:none;color:#70695c;}
'''


def split_date(value):
    text=str(value or '').strip()
    match=re.search(r'(Z|[+-]\d\d:\d\d)$',text)
    zone=match.group(0) if match else ''
    base=text[:-len(zone)] if zone else text
    base=(base[:10].replace(':','-')+base[10:]).replace('T',' ')
    try:
        parsed=datetime.fromisoformat(base)
        return parsed.strftime('%Y-%m-%d %H:%M:%S')+(f'.{parsed.microsecond:06d}'.rstrip('0') if parsed.microsecond else ''),zone
    except ValueError:return base,zone


class DateCalendar(QWidget):
    chosen=Signal(QDate)
    def __init__(self,parent=None):
        super().__init__(parent,Qt.Popup)
        self.setObjectName('metadataCalendar'); self.setStyleSheet(CALENDAR_STYLE)
        layout=QVBoxLayout(self); layout.setContentsMargins(10,10,10,10); layout.setSpacing(8)
        header=QWidget(); header.setObjectName('calendarHeader'); row=QHBoxLayout(header); row.setContentsMargins(0,0,0,0)
        self.previous=QPushButton('‹'); self.next=QPushButton('›'); self.year=QSpinBox(); self.year.setRange(1,9999)
        self.month=QComboBox(); self.month.addItems([f'{i} 月' for i in range(1,13)])
        row.addWidget(self.previous); row.addWidget(self.year,1); row.addWidget(self.month,1); row.addWidget(self.next); layout.addWidget(header)
        self.calendar=QCalendarWidget(); self.calendar.setLocale(QLocale(QLocale.Chinese,QLocale.China)); self.calendar.setNavigationBarVisible(False)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.setFirstDayOfWeek(Qt.Monday); self.calendar.setMinimumDate(QDate(1,1,1)); self.calendar.setMaximumDate(QDate(9999,12,31))
        weekend=QTextCharFormat();weekend.setForeground(QColor('#897b68'))
        self.calendar.setWeekdayTextFormat(Qt.Saturday,weekend);self.calendar.setWeekdayTextFormat(Qt.Sunday,weekend)
        layout.addWidget(self.calendar)
        bottom=QHBoxLayout(); note=QLabel('选日期，保留时间和时区'); note.setWordWrap(True); bottom.addWidget(note,1)
        self.today=QPushButton('今天'); bottom.addWidget(self.today); layout.addLayout(bottom)
        self.previous.clicked.connect(self.calendar.showPreviousMonth); self.next.clicked.connect(self.calendar.showNextMonth)
        self.calendar.currentPageChanged.connect(self.page_changed)
        self.year.valueChanged.connect(self.navigate); self.month.currentIndexChanged.connect(self.navigate)
        self.calendar.clicked.connect(self.choose); self.today.clicked.connect(lambda:self.choose(QDate.currentDate()))
        self.page_changed(self.calendar.yearShown(),self.calendar.monthShown())
    def page_changed(self,year,month):
        guards=[QSignalBlocker(self.year),QSignalBlocker(self.month)]
        self.year.setValue(year); self.month.setCurrentIndex(month-1)
    def navigate(self,*args):self.calendar.setCurrentPage(self.year.value(),self.month.currentIndex()+1)
    def choose(self,date):self.chosen.emit(date); self.hide()
    def open_for(self,owner,date):
        self.calendar.setSelectedDate(date); self.calendar.setCurrentPage(date.year(),date.month())
        self.adjustSize(); screen=owner.screen().availableGeometry(); position=owner.mapToGlobal(owner.rect().bottomLeft())
        x=max(screen.left(),min(position.x(),screen.right()-self.width()+1)); y=position.y()+4
        if y+self.height()>screen.bottom():y=owner.mapToGlobal(owner.rect().topLeft()).y()-self.height()-4
        self.move(x,max(screen.top(),y)); self.show()


class MetadataInput(QWidget):
    changed=Signal()
    def __init__(self,kind,value=None,draft=None,zone_editable=True,parent=None):
        super().__init__(parent); self.kind=kind; self.original=value
        form=QFormLayout(self); form.setContentsMargins(0,0,0,0); form.setSpacing(8); form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        if kind=='date':
            self.date=QLineEdit(); self.date.setPlaceholderText('未填写 · YYYY-MM-DD HH:mm:ss')
            self.zone=QLineEdit(); self.zone.setPlaceholderText('时区未知可留空，如 +08:00'); self.zone.setEnabled(zone_editable)
            row=QWidget(); layout=QHBoxLayout(row); layout.setContentsMargins(0,0,0,0); layout.addWidget(self.date,1)
            self.choose_date=QPushButton('选日期'); self.choose_date.setToolTip('只改变日期；首次填写使用 00:00:00，可手动更改时间'); layout.addWidget(self.choose_date)
            form.addRow('日期与时间',row); form.addRow('时区',self.zone)
            self.calendar_popup=DateCalendar(self); self.calendar_popup.chosen.connect(self.pick_date)
            self.choose_date.clicked.connect(self.show_calendar)
            self.date.textEdited.connect(self.changed); self.zone.textEdited.connect(self.changed)
        elif kind=='gps':
            self.latitude=QLineEdit(); self.longitude=QLineEdit(); self.altitude=QLineEdit()
            self.latitude.setValidator(QDoubleValidator(-90,90,6,self)); self.longitude.setValidator(QDoubleValidator(-180,180,6,self))
            self.altitude.setValidator(QDoubleValidator(-15000,100000,2,self))
            for field in (self.latitude,self.longitude,self.altitude):field.setPlaceholderText('未填写'); field.textEdited.connect(self.changed)
            self.include_altitude=QCheckBox('包含海拔'); self.include_altitude.toggled.connect(self.changed)
            form.addRow('纬度 · 北正南负',self.latitude); form.addRow('经度 · 东正西负',self.longitude)
            form.addRow(self.include_altitude); form.addRow('海拔 · 米',self.altitude)
        elif kind=='list':
            self.values=QListWidget(); self.values.setMaximumHeight(100); self.values.setMinimumHeight(60); form.addRow(self.values)
            row=QWidget(); layout=QHBoxLayout(row); layout.setContentsMargins(0,0,0,0)
            self.entry=QLineEdit(); self.entry.setPlaceholderText('输入一项后添加'); add=QPushButton('添加'); remove=QPushButton('移除')
            layout.addWidget(self.entry,1); layout.addWidget(add); layout.addWidget(remove); form.addRow(row)
            self.entry.textEdited.connect(self.changed)
            add.clicked.connect(self.add_item); self.entry.returnPressed.connect(self.add_item); remove.clicked.connect(self.remove_items)
        else:
            self.text=QLineEdit(); self.text.setPlaceholderText('未填写 · 留空保留原值'); form.addRow(self.text); self.text.textEdited.connect(self.changed)
        self.set_value(value,draft)
    def set_value(self,value,draft=None):
        children=self.findChildren(QWidget); guards=[QSignalBlocker(w) for w in children]
        if self.kind=='date':
            text,zone=split_date(value)
            self.date.setText(text); self.zone.setText(zone)
        elif self.kind=='gps':
            try:lat,lon,alt=parse_coordinates(value)
            except ValueError:lat=lon=alt=None
            self.latitude.setText('' if lat is None else f'{lat:.6f}'.rstrip('0').rstrip('.')); self.longitude.setText('' if lon is None else f'{lon:.6f}'.rstrip('0').rstrip('.'))
            self.altitude.setText('' if alt is None else f'{alt:.2f}'.rstrip('0').rstrip('.')); self.include_altitude.setChecked(alt is not None)
        elif self.kind=='list':
            self.values.clear()
            self.entry.clear()
            values=value if isinstance(value,list) else [] if value in (None,'') else [value]
            if isinstance(value,str) and value.startswith('['):
                try:values=json.loads(value)
                except ValueError:pass
            self.values.addItems([str(v) for v in values])
        else:self.text.setText('' if value is None else str(value))
        if isinstance(draft,dict):
            for key,text in draft.items():
                widget=getattr(self,key,None)
                if isinstance(widget,QLineEdit):widget.setText(str(text))
                elif isinstance(widget,QCheckBox):widget.setChecked(bool(text))
                elif isinstance(widget,QListWidget):widget.clear(); widget.addItems([str(v) for v in text])
        elif draft is not None:
            if self.kind=='date':self.date.setText(split_date(draft)[0]); self.zone.setText(split_date(draft)[1])
            elif self.kind=='list':
                try:values=json.loads(draft)
                except ValueError:values=[draft]
                self.values.clear(); self.values.addItems([str(v) for v in values])
            elif self.kind=='gps':
                try:lat,lon,alt=parse_coordinates(draft)
                except ValueError:return
                self.latitude.setText(str(lat));self.longitude.setText(str(lon));self.altitude.setText('' if alt is None else str(alt));self.include_altitude.setChecked(alt is not None)
            else:self.text.setText(str(draft))
    def raw_state(self):
        if self.kind=='date':return {'date':self.date.text(),'zone':self.zone.text()}
        if self.kind=='gps':return {name:getattr(self,name).text() for name in ('latitude','longitude','altitude')}|{'include_altitude':self.include_altitude.isChecked()}
        if self.kind=='list':return {'values':[self.values.item(i).text() for i in range(self.values.count())],'entry':self.entry.text()}
        return {'text':self.text.text()}
    def serialized(self):
        if self.kind=='date':
            text=self.date.text().strip(); zone=self.zone.text().strip()
            if not text:return ''
            if zone and not re.fullmatch(r'Z|[+-](?:0\d|1[0-4]):[0-5]\d',zone):raise ValueError('时区应为 +08:00、-05:00 或 Z')
            try:parsed=datetime.fromisoformat((text[:10].replace(':','-')+text[10:]).replace('T',' '))
            except ValueError:raise ValueError('日期需为 YYYY-MM-DD HH:mm:ss，不能使用不存在的日期')
            if parsed.tzinfo is not None:raise ValueError('请将时区填写在单独的时区框中')
            return parsed.strftime('%Y:%m:%d %H:%M:%S')+(f'.{parsed.microsecond:06d}'.rstrip('0') if parsed.microsecond else '')+zone
        if self.kind=='gps':
            lat=self.latitude.text().strip();lon=self.longitude.text().strip()
            if not lat and not lon:return ''
            try:a,b=float(lat),float(lon)
            except ValueError:raise ValueError('请同时填写有效的经度和纬度')
            if not math.isfinite(a) or not math.isfinite(b) or not -90<=a<=90 or not -180<=b<=180:raise ValueError('经纬度超出范围')
            text=f'{a:.6f}, {b:.6f}'
            if self.include_altitude.isChecked():
                try:alt=float(self.altitude.text())
                except ValueError:raise ValueError('请填写海拔，或取消包含海拔')
                if not math.isfinite(alt) or not -15000<=alt<=100000:raise ValueError('海拔超出范围')
                text+=f', {alt:.2f}'
            return text
        if self.kind=='list':
            if self.entry.text().strip():raise ValueError('还有未添加的关键词，请点击“添加”或清空输入框。')
            return json.dumps([self.values.item(i).text() for i in range(self.values.count())],ensure_ascii=False)
        return self.text.text()
    def show_calendar(self):
        text=split_date(self.date.text())[0][:10]
        date=QDate.fromString(text,'yyyy-MM-dd')
        self.calendar_popup.open_for(self.choose_date,date if date.isValid() else QDate.currentDate())
    def pick_date(self,date):
        current=self.date.text().strip()
        time=current[11:] if len(current)>10 else split_date(self.original)[0][11:] if self.original else '00:00:00'
        self.date.setText(date.toString('yyyy-MM-dd')+' '+(time or '00:00:00')); self.changed.emit()
    def add_item(self):
        if self.entry.text().strip():self.values.addItem(self.entry.text().strip());self.entry.clear();self.changed.emit()
    def remove_items(self):
        for item in self.values.selectedItems():self.values.takeItem(self.values.row(item))
        self.changed.emit()
