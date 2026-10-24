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

def main():
    img_path = 'ios16-root.img'
    ranges_path = 'diff_ranges.txt'
    bs = 4096

    ranges = []
    with open(ranges_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line:
                s, c = line.split()
                ranges.append((int(s), int(c)))

    total_blocks = sum(c for _, c in ranges)
    total_bytes = total_blocks * bs
    print(f'Packing {len(ranges)} ranges ({total_blocks} blocks, {total_bytes/1024:.1f} KB)...')

    payload_path = '/tmp/delta_payload.bin'
    script_path = '/tmp/apply_delta.sh'

    sh_lines = ['#!/bin/sh', 'DEV=/dev/block/sda19', 'BIN=/tmp/delta_payload.bin']
    bin_offset_blks = 0

    with open(img_path, 'rb') as fn, open(payload_path, 'wb') as fout:
        for s, c in ranges:
            fn.seek(s * bs)
            data = fn.read(c * bs)
            fout.write(data)
            sh_lines.append(f'dd if=$BIN of=$DEV bs=4096 skip={bin_offset_blks} seek={s} count={c} conv=notrunc,fsync status=none')
            bin_offset_blks += c

    sh_lines.append('sync')
    sh_lines.append('echo APPLY_DONE')

    with open(script_path, 'w') as fsh:
        fsh.write('\n'.join(sh_lines) + '\n')

    print('Waiting for device in ADB (OrangeFox recovery)...')
    while True:
        code, out, _ = run('adb devices')
        lines = [l for l in out.splitlines() if l and not l.startswith('*') and not l.startswith('List')]
        if lines:
            print(f'Device detected: {lines[0]}')
            break
        time.sleep(1)

    t0 = time.time()
    print('Pushing delta payload and apply script to device...')
    subprocess.check_call(['adb', 'push', payload_path, '/tmp/delta_payload.bin'], stdout=subprocess.DEVNULL)
    subprocess.check_call(['adb', 'push', script_path, '/tmp/apply_delta.sh'], stdout=subprocess.DEVNULL)

    print('Applying delta blocks directly on device...')
    res = subprocess.check_output(['adb', 'shell', 'sh /tmp/apply_delta.sh']).decode()
    if 'APPLY_DONE' not in res:
        print(f'Error applying delta: {res}')
        sys.exit(1)

    subprocess.check_call(['adb', 'shell', 'rm -f /tmp/delta_payload.bin /tmp/apply_delta.sh'])
    dt = time.time() - t0
    print(f'Delta applied successfully in {dt:.2f}s!')

    print('Verifying written blocks...')
    with open(img_path, 'rb') as fn:
        for s, c in ranges:
            fn.seek(s * bs)
            expected_data = fn.read(c * bs)
            expected_crc = zlib.crc32(expected_data)
            dev_data = subprocess.check_output(['adb', 'exec-out', f'dd if=/dev/block/sda19 bs=4096 skip={s} count={c} status=none'])
            actual_crc = zlib.crc32(dev_data)
            if actual_crc != expected_crc:
                print(f'Verification MISMATCH at block {s} (count {c}): expected {expected_crc:08x}, got {actual_crc:08x}')
                sys.exit(1)

    print(f'ALL {len(ranges)} ranges ({total_blocks} blocks) VERIFIED BIT-FOR-BIT ON FLASH!')

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
