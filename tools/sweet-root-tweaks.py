#!/usr/bin/env python3

import glob
import os
import plistlib
import shutil
import sys

BUILD_VERSION = '20H392'
PRODUCT_VERSION = '16.7.16'
MOBILE_UID = 501

DISABLED_DAEMONS = {
    'com.apple.CommCenter',
    'com.apple.driverkitd',
    'com.apple.analyticsd',
    'com.apple.awdd',
    'com.apple.adprivacyd',
    'com.apple.adid',
    'com.apple.CAReportingService',
    'com.apple.searchd',
    'com.apple.parsec-fbf',
    'com.apple.siriknowledged',
    'com.apple.siriinferenced',
    'com.apple.siriactionsd',
    'com.apple.assistantd',
    'com.apple.biomed',
    'com.apple.coreduetd',
    'com.apple.duetexpertd',
    'com.apple.contextstored',
    'com.apple.carkitd',
    'com.apple.nanoregistryd',
    'com.apple.nanoregistrylaunchd',
    'com.apple.nanoprefsyncd',
    'com.apple.wcd',
    'com.apple.fitnesscoachingd',
    'com.apple.routined',
    'com.apple.homed',
    'com.apple.passd',
    'com.apple.findmydeviced',
    'com.apple.fmflocatord',
    'com.apple.fmfd',
    'com.apple.searchpartyd',
    'com.apple.accessoryupdaterd',
    'com.apple.softwareupdated',
}

def read_plist(target_path):
    with open(target_path, 'rb') as source_stream:
        return plistlib.load(source_stream)

def write_plist(target_path, payload, owner_uid, owner_gid, permissions, serialization_format=plistlib.FMT_BINARY):
    with open(target_path, 'wb') as destination_stream:
        plistlib.dump(payload, destination_stream, fmt=serialization_format)
    try:
        os.chown(target_path, owner_uid, owner_gid)
    except PermissionError:
        pass
    try:
        os.chmod(target_path, permissions)
    except PermissionError:
        pass

def update_preferences(root_directory, preference_domain, values):
    domain_path = os.path.join(root_directory, 'private/var/mobile/Library/Preferences', preference_domain + '.plist')
    current_data = read_plist(domain_path) if os.path.exists(domain_path) else {}
    current_data.update(values)
    write_plist(domain_path, current_data, MOBILE_UID, MOBILE_UID, 0o600)
    print(f'pref {preference_domain}: updated {sorted(values)}')

def configure_launchd(root_directory):
    launchd_path = os.path.join(root_directory, 'System/Library/xpc/launchd.plist')
    file_stat = os.stat(launchd_path)
    launchd_plist = read_plist(launchd_path)
    daemon_jobs = launchd_plist['LaunchDaemons']
    
    renamed_panics = 0
    for job in daemon_jobs.values():
        if '_PanicOnCrash' in job:
            job['_PanicOnCrasX'] = job.pop('_PanicOnCrash')
            renamed_panics += 1
            
    removed_jobs = [job_key for job_key, job_spec in daemon_jobs.items() if job_spec.get('Label') in DISABLED_DAEMONS]
    for job_key in removed_jobs:
        del daemon_jobs[job_key]
        
    write_plist(launchd_path, launchd_plist, file_stat.st_uid, file_stat.st_gid, file_stat.st_mode & 0o7777)
    print(f'launchd.plist: {renamed_panics} panic flags renamed, {len(removed_jobs)} unnecessary daemons removed')

def ensure_containers(root_directory):
    containers_base = os.path.join(root_directory, 'private/var/containers')
    container_types = (('Bundle', 33), ('Data/System', 0), ('Shared/SystemGroup', 0), ('Temp', 0))
    for subfolder, owner_uid in container_types:
        target_directory = os.path.join(containers_base, subfolder)
        if not os.path.isdir(target_directory):
            os.makedirs(target_directory, exist_ok=True)
            try:
                os.chown(target_directory, owner_uid, owner_uid)
                os.chmod(target_directory, 0o755)
            except PermissionError:
                pass
            print(f'mkdir container: {target_directory}')

def locate_container(root_directory, container_category, bundle_identifier):
    search_pattern = os.path.join(root_directory, 'private/var/containers', container_category, '*',
                                  '.com.apple.mobile_container_manager.metadata.plist')
    for metadata_file in glob.glob(search_pattern):
        if read_plist(metadata_file).get('MCMMetadataIdentifier') == bundle_identifier:
            return os.path.dirname(metadata_file)
    return None

def seed_mobileactivation(root_directory):
    activation_container = locate_container(root_directory, 'Data/System', 'com.apple.mobileactivationd')
    if activation_container is None:
        print('warning: mobileactivationd container absent; data_ark not seeded')
        return
        
    internal_storage = os.path.join(activation_container, 'Library/internal')
    os.makedirs(internal_storage, exist_ok=True)
    try:
        os.chown(internal_storage, MOBILE_UID, MOBILE_UID)
        os.chmod(internal_storage, 0o755)
    except PermissionError:
        pass
    
    ark_payload = {
        '-ActivationState': 'Activated',
        '-BrickState': False,
        '-BuildVersion': BUILD_VERSION,
        '-ProductVersion': PRODUCT_VERSION,
        '-DataMigrationCompleted': True,
        '-PreSydroDataMigrationCompleted': True,
    }
    write_plist(os.path.join(internal_storage, 'data_ark.plist'), ark_payload, MOBILE_UID, MOBILE_UID, 0o600)
    print(f'data ark written to {internal_storage}')

def configure_audio_stack(root_directory):
    virtual_audio_path = os.path.join(root_directory, 'Library/Audio/Plug-Ins/HAL/VirtualAudio.plugin')
    disabled_audio_directory = os.path.join(root_directory, 'Library/Audio/Plug-Ins/HAL.disabled')
    if os.path.exists(virtual_audio_path):
        os.makedirs(disabled_audio_directory, exist_ok=True)
        shutil.move(virtual_audio_path, disabled_audio_directory)
        print('VirtualAudio.plugin moved to HAL.disabled')
        
    mediatoolbox_configs = glob.glob(os.path.join(root_directory, 'System/Library/Frameworks/MediaToolbox.framework/*/SubServerConfiguration.plist'))
    for config_path in mediatoolbox_configs:
        file_stat = os.stat(config_path)
        config_data = read_plist(config_path)
        config_data['StartRecorderServer'] = False
        write_plist(config_path, config_data, file_stat.st_uid, file_stat.st_gid, file_stat.st_mode & 0o7777, plistlib.FMT_XML)
        print(f'StartRecorderServer disabled in {os.path.relpath(config_path, root_directory)}')

def main():
    if len(sys.argv) != 2 or not os.path.isdir(os.path.join(sys.argv[1], 'System/Library/xpc')):
        sys.exit(f'Usage: {sys.argv[0]} MOUNTED_IOS_ROOT')
        
    ios_root = sys.argv[1]
    configure_launchd(ios_root)
    ensure_containers(ios_root)
    seed_mobileactivation(ios_root)
    configure_audio_stack(ios_root)
    
    update_preferences(ios_root, 'com.apple.migration', {
        'LastSystemVersion': BUILD_VERSION,
        'DMUserDataDisposition': {'SyntheticDidUpgrade': False, 'buildVersion': BUILD_VERSION}
    })
    update_preferences(ios_root, 'com.apple.springboard', {
        'BKNoWatchdogs': True,
        'FBLaunchWatchdogExceptions': {'com.apple.purplebuddy': 100.0},
        'MCForceShowCloudConfigurationUI': False
    })
    update_preferences(ios_root, 'com.apple.purplebuddy', {
        'SetupDone': True,
        'SetupFinishedAllSteps': True,
        'SetupVersion': 11,
        'daemonizeNeedsToRun': False
    })
    update_preferences(ios_root, 'com.apple.purplebuddy.notbackedup', {
        flag_name: False for flag_name in (
            'ShouldRunDiagnosticsMiniBuddy', 'ShouldRunHSA2MiniBuddy',
            'ShouldRunKeychainSyncMiniBuddy', 'ShouldRunMesaMiniBuddy',
            'ShouldRunPaymentMiniBuddy', 'ShouldRunStandardMiniBuddy',
            'SilentICDPUpgrade'
        )
    })
    update_preferences(ios_root, 'com.apple.managedconfiguration.notbackedup', {
        'LockdownActivationIndicatesCloudConfigurationAvailable': False
    })

if __name__ == '__main__':
    main()
