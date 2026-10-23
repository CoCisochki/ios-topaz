#!/usr/bin/env python3

import argparse
import os
import plistlib
import shutil
import sys

SYSTEM_ROOT_UID = 0
SYSTEM_ROOT_GID = 0
MOBILE_USER_UID = 501
MOBILE_USER_GID = 501

def set_filesystem_ownership(target_path, owner_uid, owner_gid, file_mode, directory_mode):
    if os.path.isdir(target_path):
        os.chmod(target_path, directory_mode)
        os.chown(target_path, owner_uid, owner_gid)
        for directory_root, child_directories, child_files in os.walk(target_path):
            for child_directory in child_directories:
                full_directory_path = os.path.join(directory_root, child_directory)
                os.chmod(full_directory_path, directory_mode)
                os.chown(full_directory_path, owner_uid, owner_gid)
            for child_file in child_files:
                full_file_path = os.path.join(directory_root, child_file)
                os.chmod(full_file_path, file_mode)
                os.chown(full_file_path, owner_uid, owner_gid)
    else:
        os.chmod(target_path, file_mode)
        os.chown(target_path, owner_uid, owner_gid)

def install_application_bundle(ios_root, source_application_path):
    if not os.path.isdir(source_application_path) or not source_application_path.endswith('.app'):
        sys.exit(f'Error: {source_application_path} is not a valid .app directory')
        
    application_name = os.path.basename(os.path.normpath(source_application_path))
    destination_directory = os.path.join(ios_root, 'Applications', application_name)
    
    if os.path.exists(destination_directory):
        shutil.rmtree(destination_directory)
        
    shutil.copytree(source_application_path, destination_directory, symlinks=True)
    set_filesystem_ownership(destination_directory, MOBILE_USER_UID, MOBILE_USER_GID, 0o644, 0o755)
    
    info_plist_path = os.path.join(destination_directory, 'Info.plist')
    if os.path.exists(info_plist_path):
        with open(info_plist_path, 'rb') as plist_stream:
            bundle_information = plistlib.load(plist_stream)
        executable_name = bundle_information.get('CFBundleExecutable')
        if executable_name:
            binary_path = os.path.join(destination_directory, executable_name)
            if os.path.exists(binary_path):
                os.chmod(binary_path, 0o755)
                
    print(f'Installed application bundle to: {destination_directory}')

def install_command_binary(ios_root, source_binary_path, destination_name=None):
    if not os.path.isfile(source_binary_path):
        sys.exit(f'Error: {source_binary_path} is not a valid file')
        
    target_filename = destination_name or os.path.basename(source_binary_path)
    binary_directory = os.path.join(ios_root, 'usr/local/bin')
    os.makedirs(binary_directory, exist_ok=True)
    os.chmod(binary_directory, 0o755)
    os.chown(binary_directory, SYSTEM_ROOT_UID, SYSTEM_ROOT_GID)
    
    target_destination = os.path.join(binary_directory, target_filename)
    shutil.copy2(source_binary_path, target_destination)
    os.chmod(target_destination, 0o755)
    os.chown(target_destination, SYSTEM_ROOT_UID, SYSTEM_ROOT_GID)
    print(f'Installed executable binary to: {target_destination}')

def install_launch_daemon(ios_root, source_plist_path):
    if not os.path.isfile(source_plist_path):
        sys.exit(f'Error: {source_plist_path} is not a valid file')
        
    daemon_directory = os.path.join(ios_root, 'Library/LaunchDaemons')
    os.makedirs(daemon_directory, exist_ok=True)
    os.chmod(daemon_directory, 0o755)
    os.chown(daemon_directory, SYSTEM_ROOT_UID, SYSTEM_ROOT_GID)
    
    target_filename = os.path.basename(source_plist_path)
    target_destination = os.path.join(daemon_directory, target_filename)
    shutil.copy2(source_plist_path, target_destination)
    os.chmod(target_destination, 0o644)
    os.chown(target_destination, SYSTEM_ROOT_UID, SYSTEM_ROOT_GID)
    print(f'Installed launch daemon to: {target_destination}')

def parse_cli_arguments():
    argument_parser = argparse.ArgumentParser(description='Inject binaries, daemons, or .app bundles into an iOS root filesystem')
    argument_parser.add_argument('--root', required=True, help='Path to mounted iOS root')
    argument_parser.add_argument('--app', help='Path to .app bundle to install')
    argument_parser.add_argument('--bin', help='Path to executable binary to install')
    argument_parser.add_argument('--bin-name', help='Optional rename for executable binary')
    argument_parser.add_argument('--daemon', help='Path to LaunchDaemon plist to install')
    return argument_parser.parse_args()

def main():
    arguments = parse_cli_arguments()
    target_root = os.path.abspath(arguments.root)
    
    if not os.path.isdir(os.path.join(target_root, 'System/Library')):
        sys.exit(f'Error: {target_root} does not appear to be an iOS root filesystem')
        
    if arguments.app:
        install_application_bundle(target_root, os.path.abspath(arguments.app))
    if arguments.bin:
        install_command_binary(target_root, os.path.abspath(arguments.bin), arguments.bin_name)
    if arguments.daemon:
        install_launch_daemon(target_root, os.path.abspath(arguments.daemon))
        
    if not (arguments.app or arguments.bin or arguments.daemon):
        print('No injection payload specified. Use --app, --bin, or --daemon.')

if __name__ == '__main__':
    main()
