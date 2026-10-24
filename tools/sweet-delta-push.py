#!/usr/bin/env python3
import sys
import os
import struct
import zlib
import time
import socket
import subprocess
import argparse

CHUNK_MAGIC = b'CHKS'
CHUNK_VERSION = 1
DEFAULT_CHUNK_SIZE = 1048576
DEFAULT_PARTITION = '/dev/block/sda19'
DEFAULT_HOST = '192.168.7.2'
DEFAULT_PORT = 1337

def compute_chunk_hashes(image_path, chunk_size=DEFAULT_CHUNK_SIZE):
    size = os.path.getsize(image_path)
    num_chunks = (size + chunk_size - 1) // chunk_size
    hashes = []
    t0 = time.time()
    last_print = t0
    with open(image_path, 'rb') as f:
        for idx in range(num_chunks):
            buf = f.read(chunk_size)
            if not buf:
                break
            hashes.append(zlib.crc32(buf))
            now = time.time()
            if now - last_print >= 2.0 or idx == num_chunks - 1:
                pct = (idx + 1) / num_chunks * 100.0
                mb_s = ((idx + 1) * chunk_size) / (1024 * 1024 * max(0.001, now - t0))
                print(f'\rScanning {os.path.basename(image_path)}: {pct:.1f}% ({idx+1}/{num_chunks} chunks, {mb_s:.1f} MB/s)', end='', flush=True)
                last_print = now
    print()
    return hashes, chunk_size, size

def save_chunks_file(chunk_file, hashes, chunk_size, total_size):
    with open(chunk_file, 'wb') as f:
        f.write(CHUNK_MAGIC)
        f.write(struct.pack('<IIQQ', CHUNK_VERSION, chunk_size, len(hashes), total_size))
        f.write(struct.pack(f'<{len(hashes)}I', *hashes))

def load_chunks_file(chunk_file):
    if not os.path.exists(chunk_file):
        return None, None, None
    with open(chunk_file, 'rb') as f:
        magic = f.read(4)
        if magic != CHUNK_MAGIC:
            return None, None, None
        version, chunk_size, num_chunks, total_size = struct.unpack('<IIQQ', f.read(24))
        raw = f.read(num_chunks * 4)
        hashes = list(struct.unpack(f'<{num_chunks}I', raw))
        return hashes, chunk_size, total_size

def find_dirty_ranges(image_path, baseline_hashes, chunk_size):
    size = os.path.getsize(image_path)
    num_chunks = (size + chunk_size - 1) // chunk_size
    dirty_indices = []
    current_hashes = []
    t0 = time.time()
    last_print = t0
    with open(image_path, 'rb') as f:
        for idx in range(num_chunks):
            buf = f.read(chunk_size)
            if not buf:
                break
            h = zlib.crc32(buf)
            current_hashes.append(h)
            if idx >= len(baseline_hashes) or h != baseline_hashes[idx]:
                dirty_indices.append(idx)
            now = time.time()
            if now - last_print >= 2.0 or idx == num_chunks - 1:
                pct = (idx + 1) / num_chunks * 100.0
                print(f'\rComparing chunks: {pct:.1f}% (dirty: {len(dirty_indices)})', end='', flush=True)
                last_print = now
    print()
    ranges = []
    if dirty_indices:
        start = dirty_indices[0]
        count = 1
        for idx in dirty_indices[1:]:
            if idx == start + count:
                count += 1
            else:
                ranges.append((start, count))
                start = idx
                count = 1
        ranges.append((start, count))
    return ranges, dirty_indices, current_hashes

def push_block_delta_adb(image_path, dirty_ranges, chunk_size, partition=DEFAULT_PARTITION, serial=None):
    adb_cmd = ['adb']
    if serial:
        adb_cmd += ['-s', serial]
    try:
        dev_out = subprocess.check_output(adb_cmd + ['devices']).decode()
    except FileNotFoundError:
        print('Error: adb binary not found in PATH.')
        return False
    lines = [l for l in dev_out.strip().splitlines() if l and not l.startswith('*') and not l.startswith('List')]
    if not lines:
        print('Error: no device detected via adb.')
        return False
    total_chunks = sum(count for _, count in dirty_ranges)
    total_bytes = total_chunks * chunk_size
    print(f'Pushing delta: {len(dirty_ranges)} contiguous range(s), {total_chunks} chunks ({total_bytes / (1024*1024):.2f} MB) -> {partition}')
    t0 = time.time()
    with open(image_path, 'rb') as f:
        for range_idx, (start_chunk, count) in enumerate(dirty_ranges):
            offset = start_chunk * chunk_size
            length = count * chunk_size
            f.seek(offset)
            data = f.read(length)
            cmd = f'dd of={partition} bs={chunk_size} seek={start_chunk} count={count} conv=notrunc status=none'
            p = subprocess.Popen(adb_cmd + ['exec-in', cmd], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            _, err = p.communicate(data)
            if p.returncode != 0:
                temp_local = '/tmp/_delta_chunk.bin'
                temp_dev = '/tmp/_delta_chunk.bin'
                with open(temp_local, 'wb') as tf:
                    tf.write(data)
                subprocess.check_call(adb_cmd + ['push', temp_local, temp_dev])
                dd_cmd = f'dd if={temp_dev} of={partition} bs={chunk_size} seek={start_chunk} count={count} conv=notrunc status=none && rm -f {temp_dev}'
                subprocess.check_call(adb_cmd + ['shell', dd_cmd])
                if os.path.exists(temp_local):
                    os.remove(temp_local)
            print(f'[{range_idx+1}/{len(dirty_ranges)}] Seek {start_chunk} Count {count} ({length / (1024*1024):.2f} MB) OK')
    subprocess.check_call(adb_cmd + ['shell', 'sync'])
    t1 = time.time()
    dt = max(0.001, t1 - t0)
    print(f'Delta push successfully finished in {dt:.2f}s ({total_bytes / (1024*1024*dt):.2f} MB/s)')
    return True

class TopazShellClient:
    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))
        self.read_until_prompt()

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def read_until_prompt(self):
        buf = b''
        while b'topaz# ' not in buf:
            try:
                chunk = self.sock.recv(1024)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
        return buf

    def send_cmd(self, cmd_str):
        if not cmd_str.endswith('\n'):
            cmd_str += '\n'
        self.sock.sendall(cmd_str.encode())
        res = self.read_until_prompt()
        lines = res.decode('utf-8', errors='replace').splitlines()
        clean = []
        for l in lines:
            if 'topaz#' in l:
                break
            clean.append(l)
        return '\n'.join(clean).strip()

    def put_file(self, local_path, remote_path, mode=None, uid=None, gid=None):
        size = os.path.getsize(local_path)
        cmd = f'put {remote_path} {size}\n'
        self.sock.sendall(cmd.encode())
        t0 = time.time()
        with open(local_path, 'rb') as f:
            sent = 0
            while True:
                buf = f.read(4096)
                if not buf:
                    break
                self.sock.sendall(buf)
                sent += len(buf)
        res = self.read_until_prompt()
        text = res.decode('utf-8', errors='replace')
        if 'OK' not in text:
            return False, text
        t1 = time.time()
        dt = max(0.001, t1 - t0)
        print(f'Uploaded {size} bytes in {dt:.3f}s ({size / (1024*1024*dt):.2f} MB/s)')
        if mode:
            cmd = f'chmod {mode} {remote_path}\n'
            self.sock.sendall(cmd.encode())
            self.read_until_prompt()
        if uid is not None and gid is not None:
            cmd = f'chown {uid} {gid} {remote_path}\n'
            self.sock.sendall(cmd.encode())
            self.read_until_prompt()
        return True, 'OK'

    def mkdir(self, remote_path):
        res = self.send_cmd(f'mkdir {remote_path}')
        return 'OK' in res

    def rm(self, remote_path):
        res = self.send_cmd(f'rm {remote_path}')
        return 'OK' in res

    def kill(self, pid_or_name):
        res = self.send_cmd(f'kill {pid_or_name}')
        return 'OK' in res

def main():
    parser = argparse.ArgumentParser(description='Sweet & Topaz Instant Delta-Push / Live-Push Tool')
    parser.add_argument('action', nargs='?', default='auto', choices=['auto', 'init', 'diff', 'push', 'put', 'mkdir', 'rm', 'kill', 'cmd', 'ps', 'dmesg'])
    parser.add_argument('--image', default='ios16-root.img')
    parser.add_argument('--chunks', default='ios16-root.chunks')
    parser.add_argument('--partition', default=DEFAULT_PARTITION)
    parser.add_argument('--host', default=DEFAULT_HOST)
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--serial', default=None)
    parser.add_argument('--local', help='Local source file for put')
    parser.add_argument('--remote', help='Remote destination path for put/mkdir/rm')
    parser.add_argument('--mode', help='File mode in octal (e.g. 0755)')
    parser.add_argument('--uid', type=int, default=None)
    parser.add_argument('--gid', type=int, default=None)
    parser.add_argument('extra_args', nargs='*', help='Extra arguments for cmd, kill, etc.')

    args = parser.parse_args()

    if args.action == 'init':
        hashes, chunk_size, total_size = compute_chunk_hashes(args.image)
        save_chunks_file(args.chunks, hashes, chunk_size, total_size)
        print(f'Baseline saved to {args.chunks} ({len(hashes)} chunks, {total_size / (1024**3):.2f} GB)')
        return

    if args.action in ['diff', 'push', 'auto']:
        baseline_hashes, chunk_size, total_size = load_chunks_file(args.chunks)
        if baseline_hashes is None:
            print(f'{args.chunks} not found. Initializing baseline from {args.image}...')
            hashes, chunk_size, total_size = compute_chunk_hashes(args.image)
            save_chunks_file(args.chunks, hashes, chunk_size, total_size)
            print('Baseline initialized. No diff yet.')
            return
        ranges, dirty_indices, current_hashes = find_dirty_ranges(args.image, baseline_hashes, chunk_size)
        dirty_bytes = len(dirty_indices) * chunk_size
        print(f'Dirty chunks: {len(dirty_indices)} / {len(baseline_hashes)} ({dirty_bytes / (1024*1024):.2f} MB across {len(ranges)} range(s))')
        for r_idx, (start, count) in enumerate(ranges):
            print(f'  Range {r_idx+1}: chunk {start}..{start+count-1} (seek {start}M, count {count}M)')
        if args.action == 'diff':
            return
        if len(dirty_indices) == 0:
            print('Image is identical to baseline. Nothing to push.')
            return
        if args.action == 'push' or (args.action == 'auto' and len(dirty_indices) > 0):
            success = push_block_delta_adb(args.image, ranges, chunk_size, args.partition, args.serial)
            if success:
                save_chunks_file(args.chunks, current_hashes, chunk_size, total_size)
                print(f'Updated baseline {args.chunks}')
            return

    client = TopazShellClient(host=args.host, port=args.port)
    try:
        client.connect()
    except Exception as e:
        print(f'Failed to connect to topaz-shell at {args.host}:{args.port}: {e}')
        return

    try:
        if args.action == 'put':
            local_f = args.local or (args.extra_args[0] if len(args.extra_args) > 0 else None)
            remote_f = args.remote or (args.extra_args[1] if len(args.extra_args) > 1 else None)
            if not local_f or not remote_f:
                print('Usage: sweet-delta-push.py put <local_path> <remote_path> [--mode 0755] [--uid 0] [--gid 0]')
                return
            ok, msg = client.put_file(local_f, remote_f, args.mode, args.uid, args.gid)
            print(f'put {local_f} -> {remote_f}: {msg}')
        elif args.action == 'mkdir':
            target = args.remote or (args.extra_args[0] if len(args.extra_args) > 0 else None)
            print('mkdir:', target, 'OK' if client.mkdir(target) else 'ERR')
        elif args.action == 'rm':
            target = args.remote or (args.extra_args[0] if len(args.extra_args) > 0 else None)
            print('rm:', target, 'OK' if client.rm(target) else 'ERR')
        elif args.action == 'kill':
            target = args.extra_args[0] if len(args.extra_args) > 0 else None
            print('kill:', target, 'OK' if client.kill(target) else 'ERR')
        elif args.action == 'ps':
            print(client.send_cmd('ps'))
        elif args.action == 'dmesg':
            print(client.send_cmd('dmesg'))
        elif args.action == 'cmd':
            cmd_str = ' '.join(args.extra_args)
            print(client.send_cmd(cmd_str))
    finally:
        client.close()

if __name__ == '__main__':
    main()
