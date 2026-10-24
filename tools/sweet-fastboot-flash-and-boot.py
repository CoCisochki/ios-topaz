#!/usr/bin/env python3
import sys
import os
import time
import subprocess

def run(cmd):
    p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def main():
    print('Waiting for device in fastboot or recovery...')
    while True:
        code, out, _ = run('fastboot devices')
        lines = [l for l in out.splitlines() if l]
        if lines:
            print(f'Fastboot device detected: {lines[0]}')
            break
        code, out, _ = run('adb devices')
        lines = [l for l in out.splitlines() if l and not l.startswith('*') and not l.startswith('List')]
        if lines:
            print(f'ADB recovery detected: {lines[0]}, rebooting to bootloader...')
            run('adb reboot bootloader')
            time.sleep(2)
            continue
        time.sleep(1)

    delta_simg = 'delta.simg'
    if not os.path.exists(delta_simg):
        print(f'Error: {delta_simg} not found!')
        sys.exit(1)

    sz_kb = os.path.getsize(delta_simg) / 1024.0
    print(f'Flashing instant delta ({sz_kb:.1f} KB) to userdata...')
    t0 = time.time()
    code = subprocess.call(['fastboot', 'flash', 'userdata', delta_simg])
    if code != 0:
        print('fastboot flash userdata failed!')
        sys.exit(1)
    dt = time.time() - t0
    print(f'Flash completed in {dt:.2f}s!')

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
