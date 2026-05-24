"""
streamlit_app.py — Cloud & 本地入口
Streamlit Cloud 部署時，指定此檔案為 Main file path。
本地開發：streamlit run streamlit_app.py
"""
import sys
import os

# 確保 src/ 可以被 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.dashboard.app import main

main()
