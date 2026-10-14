"""Generate Windows executable product properties from the shared brand constants."""
from project_layout import DEV,NAME,VERSION,EXE_NAME
from mediaforge.product import AUTHOR
from PyInstaller.utils.win32.versioninfo import (VSVersionInfo,FixedFileInfo,StringFileInfo,
    StringTable,StringStruct,VarFileInfo,VarStruct)

numbers=tuple(map(int,VERSION.split('.')))+(0,)
info=VSVersionInfo(
    ffi=FixedFileInfo(filevers=numbers,prodvers=numbers,mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),
    kids=[StringFileInfo([StringTable('080404B0',[
        StringStruct('CompanyName',AUTHOR),StringStruct('FileDescription',NAME),
        StringStruct('FileVersion',VERSION),StringStruct('InternalName','MediaForge'),
        StringStruct('OriginalFilename',EXE_NAME),StringStruct('ProductName',NAME),
        StringStruct('ProductVersion',VERSION),
    ])]),VarFileInfo([VarStruct('Translation',[2052,1200])])])
target=DEV/'build/version-info.txt';target.parent.mkdir(parents=True,exist_ok=True)
target.write_text(str(info),encoding='utf-8')
print(target)
