import os, sys
sys.path.insert(0, r"D:\HAJIMI_B\Fuzzy-Visual-Assisted-Question-Answering-System\HAJIMI_UI")
from core.user_settings import load_user_settings
s = load_user_settings()
print('a_end_url:', s.get('a_end_url'))
print('deployment_mode:', s.get('deployment_mode'))
print('HAJIMI_API_URL env:', os.environ.get('HAJIMI_API_URL', 'NOT SET'))
