import sys
import os
sys.path.append('.')

from app import create_app
from app.services.ollama import OllamaService

app = create_app()
print('Testing system stats API...')

with app.app_context():
    s = OllamaService(app)
    stats = s.get_system_stats()
    print('System stats:', stats)
    print('Disk percent:', stats.get('disk', {}).get('percent', 'N/A'))
