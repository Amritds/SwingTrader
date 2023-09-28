import subprocess
import os
import time
while True:
    if 'swing_trader.py' not in os.popen('ps -aux|grep swing_trader').read():
        print('Process failed... restarting...')
        os.system('python3 -u swing_trader.py')
        time.sleep(60)
