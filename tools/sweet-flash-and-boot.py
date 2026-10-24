#!/usr/bin/env python3
import sys
import os
import time
import subprocess

def run(cmd):
    p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def wait_for_adb():
    print('Waiting for device in ADB (OrangeFox recovery)...')
    while True:
        code, out, _ = run('adb devices')
        lines = [l for l in out.splitlines() if l and not l.startswith('*') and not l.startswith('List')]
        if lines:
            print(f'Device detected: {lines[0]}')
            return
        time.sleep(1)

def wait_for_fastboot():
    print('Waiting for device in fastboot...')
    while True:
        code, out, _ = run('fastboot devices')
        lines = [l for l in out.splitlines() if l]
        if lines:
            print(f'Device detected in fastboot: {lines[0]}')
            return
        time.sleep(1)

def main():
    wait_for_adb()
    print('Pushing delta blocks to userdata...')
    code = subprocess.call([sys.executable, 'tools/sweet-delta-push.py', 'push-known'])
    if code != 0:
        print('Delta push failed!')
        sys.exit(1)
    print('Delta push and verification successful!')
    print('Rebooting to bootloader...')
    run('adb reboot bootloader')
    wait_for_fastboot()
    boot_img = 'shim/out/shim-boot.img'
    if not os.path.exists(boot_img):
        print(f'Error: {boot_img} not found!')
        sys.exit(1)
    print(f'Booting {boot_img} via fastboot...')
    code = subprocess.call(['fastboot', 'boot', boot_img])
    if code != 0:
        print('fastboot boot failed!')
        sys.exit(1)
    print('Boot command sent. Device is booting iOS!')

if __name__ == '__main__':
    main()
