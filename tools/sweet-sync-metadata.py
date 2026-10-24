#!/usr/bin/env python3
import sys
import os
import struct
import zlib
import time
import subprocess

def run(cmd):
    p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

METADATA_RANGES = [
    (0, 2),
    (8, 7),
    (717, 66),
    (857, 34),
    (4472, 34),
    (6863, 34),
    (7682, 4),
    (8303, 4),
    (12675, 2),
    (13172, 2),
]

def main():
    img_path = 'ios16-root.img'
    chunk_size = 1048576

    total_chunks = sum(c for _, c in METADATA_RANGES)
    total_bytes = total_chunks * chunk_size
    print(f'Metadata sync: {len(METADATA_RANGES)} ranges, {total_chunks} chunks ({total_bytes / (1024*1024):.1f} MB)')

    print('Waiting for device in ADB (OrangeFox recovery)...')
    while True:
        code, out, _ = run('adb devices')
        lines = [l for l in out.splitlines() if l and not l.startswith('*') and not l.startswith('List')]
        if lines:
            print(f'Device detected: {lines[0]}')
            break
        time.sleep(1)

    t0 = time.time()
    temp_local = '/tmp/_sync_range.bin'
    temp_dev = '/tmp/_sync_range.bin'

    with open(img_path, 'rb') as fn:
        for idx, (s, c) in enumerate(METADATA_RANGES):
            offset = s * chunk_size
            length = c * chunk_size
            fn.seek(offset)
            data = fn.read(length)
            with open(temp_local, 'wb') as tf:
                tf.write(data)
            subprocess.check_call(['adb', 'push', temp_local, temp_dev], stdout=subprocess.DEVNULL)
            dd_cmd = f'dd if={temp_dev} of=/dev/block/sda19 bs=1048576 seek={s} count={c} conv=notrunc status=none && rm -f {temp_dev}'
            subprocess.check_call(['adb', 'shell', dd_cmd])
            if os.path.exists(temp_local):
                os.remove(temp_local)
            print(f'[{idx+1}/{len(METADATA_RANGES)}] Range seek {s}M count {c}M ({c} MB) OK')

    subprocess.check_call(['adb', 'shell', 'sync'])
    dt = time.time() - t0
    print(f'All metadata ranges written in {dt:.2f}s ({total_bytes / (1024*1024*dt):.2f} MB/s)')

    print('Verifying written ranges...')
    with open(img_path, 'rb') as fn:
        for idx, (s, c) in enumerate(METADATA_RANGES):
            offset = s * chunk_size
            length = c * chunk_size
            fn.seek(offset)
            expected_data = fn.read(length)
            expected_crc = zlib.crc32(expected_data)
            cmd = ['adb', 'exec-out', f'dd if=/dev/block/sda19 bs=1048576 skip={s} count={c} status=none']
            dev_data = subprocess.check_output(cmd)
            actual_crc = zlib.crc32(dev_data)
            if actual_crc != expected_crc:
                print(f'Verification MISMATCH at range {idx+1} (seek {s}M, count {c}M): expected {expected_crc:08x}, got {actual_crc:08x}')
                sys.exit(1)

    print(f'ALL {len(METADATA_RANGES)} RANGES ({total_chunks} MB) VERIFIED BIT-FOR-BIT ON FLASH!')

    print('Rebooting to bootloader...')
    run('adb reboot bootloader')

    print('Waiting for fastboot...')
    while True:
        code, out, _ = run('fastboot devices')
        lines = [l for l in out.splitlines() if l]
        if lines:
            print(f'Fastboot device detected: {lines[0]}')
            break
        time.sleep(1)

    boot_img = 'shim/out/shim-boot.img'
    print(f'Booting {boot_img} via fastboot...')
    code = subprocess.call(['fastboot', 'boot', boot_img])
    if code != 0:
        print('fastboot boot failed!')
        sys.exit(1)
    print('Boot command sent. Device is booting iOS with 100% verified flash!')

if __name__ == '__main__':
    main()
