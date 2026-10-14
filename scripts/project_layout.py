"""Locations shared by build and verification scripts, including source bundles."""
from pathlib import Path
import sys
DEV=Path(__file__).resolve().parents[1]
PROJECT=DEV.parent if DEV.name=='开发资料' and (DEV.parent/'project.marker').is_file() else DEV
CLASSIFIED=DEV!=PROJECT
RUN=PROJECT/'运行数据' if CLASSIFIED else PROJECT
DOCS=PROJECT/'文档' if CLASSIFIED else DEV/'docs'
PORTABLE=PROJECT/'软件程序/MediaForge' if CLASSIFIED else PROJECT/'成品/MediaForge'
RELEASE=PROJECT/'发布包' if CLASSIFIED else PROJECT
sys.path.insert(0,str(DEV/'src'))
from mediaforge.product import NAME,VERSION,EXE_NAME,ARCHIVE_NAME,LAUNCHER_NAME

