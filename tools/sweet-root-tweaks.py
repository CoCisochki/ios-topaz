#!/usr/bin/env python3

import glob
import os
import plistlib
import shutil
import subprocess
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
    'com.apple.ReportCrash',
    'com.apple.ReportCrash.DirectoryService',
    'com.apple.ReportCrash.Jetsam',
    'com.apple.DumpPanic',
    'com.apple.DumpBasebandCrash',
    'com.apple.osanalytics.osanalyticshelper',
    'com.apple.OTACrashCopier',
    'com.apple.ProxiedCrashCopier.ProxyingDevice',
    'com.apple.dmd',
    'com.apple.ScreenTimeAgent',
    'com.apple.cloudd',
    'com.apple.chronod',
    'com.apple.liveactivitiesd',
    'com.apple.memory-maintenance',
    'com.apple.geod',
    'com.apple.syncdefaultsd',
    'com.apple.suggestd',
    'com.apple.symptomsd-diag',
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
    paths = [
        os.path.join(root_directory, 'private/var/mobile/Library/Preferences', preference_domain + '.plist'),
        os.path.join(root_directory, 'Library/Managed Preferences/mobile', preference_domain + '.plist')
    ]
    for domain_path in paths:
        target_dir = os.path.dirname(domain_path)
        os.makedirs(target_dir, exist_ok=True)
        try:
            os.chown(target_dir, MOBILE_UID, MOBILE_UID)
        except PermissionError:
            pass
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

    daemon_jobs['com.topaz.shell'] = {
        'Label': 'com.topaz.shell',
        'Program': '/usr/local/bin/topaz-shell',
        'RunAtLoad': True,
        'KeepAlive': True
    }

    prof_key = '/System/Library/LaunchDaemons/com.apple.managedconfiguration.profiled.plist'
    if prof_key in daemon_jobs:
        daemon_jobs[prof_key]['ThrottleInterval'] = 5

    acct_key = '/System/Library/LaunchDaemons/com.apple.accountsd.plist'
    if acct_key not in daemon_jobs:
        acct_path = os.path.join(root_directory, acct_key.lstrip('/'))
        if os.path.exists(acct_path):
            daemon_jobs[acct_key] = read_plist(acct_path)
            daemon_jobs[acct_key]['ThrottleInterval'] = 5
        
    write_plist(launchd_path, launchd_plist, file_stat.st_uid, file_stat.st_gid, file_stat.st_mode & 0o7777)
    print(f'launchd.plist: {renamed_panics} panic flags renamed, {len(removed_jobs)} unnecessary daemons removed, com.topaz.shell added')

    rc_bin = os.path.join(root_directory, 'System/Library/CoreServices/ReportCrash')
    if os.path.exists(rc_bin):
        rc_dis = os.path.join(root_directory, 'System/Library/CoreServices/ReportCrash.disabled')
        if not os.path.exists(rc_dis):
            shutil.move(rc_bin, rc_dis)
            print('ReportCrash executable disabled')

    for ld in ('com.apple.ReportCrash.plist', 'com.apple.DumpPanic.plist', 'com.apple.DumpBasebandCrash.plist'):
        ld_path = os.path.join(root_directory, 'System/Library/LaunchDaemons', ld)
        if os.path.exists(ld_path):
            shutil.move(ld_path, ld_path + '.disabled')

def ensure_system_directories(root_directory):
    dirs_mobile = [
        'private/var/mobile/Library/Accounts',
        'private/var/mobile/Library/ConfigurationProfiles',
        'private/var/mobile/Library/UserConfigurationProfiles',
    ]
    for d in dirs_mobile:
        p = os.path.join(root_directory, d)
        os.makedirs(p, exist_ok=True)
        try:
            os.chown(p, MOBILE_UID, MOBILE_UID)
            os.chmod(p, 0o755)
        except PermissionError:
            pass

    dirs_root = [
        'private/var/root/Library/Accounts',
        'private/var/root/Library/ConfigurationProfiles',
    ]
    for d in dirs_root:
        p = os.path.join(root_directory, d)
        os.makedirs(p, exist_ok=True)
        try:
            os.chown(p, 0, 0)
            os.chmod(p, 0o755)
        except PermissionError:
            pass

    system_groups = [
        ('systemgroup.com.apple.configurationprofiles', ['Library/ConfigurationProfiles']),
    ]
    sg_base = os.path.join(root_directory, 'private/var/containers/Shared/SystemGroup')
    for sg_id, subdirs in system_groups:
        sg_dir = os.path.join(sg_base, sg_id)
        os.makedirs(sg_dir, exist_ok=True)
        try:
            os.chown(sg_dir, 0, 0)
            os.chmod(sg_dir, 0o755)
        except PermissionError:
            pass
        meta_plist = os.path.join(sg_dir, '.com.apple.mobile_container_manager.metadata.plist')
        if not os.path.exists(meta_plist):
            write_plist(meta_plist, {'MCMMetadataIdentifier': sg_id}, 0, 0, 0o644, plistlib.FMT_XML)
        for s in subdirs:
            sp = os.path.join(sg_dir, s)
            os.makedirs(sp, exist_ok=True)
            try:
                os.chown(sp, 0, 0)
                os.chmod(sp, 0o755)
            except PermissionError:
                pass

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

def install_topaz_shell(root_directory):
    shell_src_asm = os.path.join(os.path.dirname(__file__), 'sweet-shell.S')
    obj_path = '/tmp/sweet-shell.o'
    shell_bin = '/tmp/topaz-shell'
    subprocess.run(['clang', '-target', 'arm64-apple-ios16.0', '-c', shell_src_asm, '-o', obj_path], check=True)
    mkinit_script = os.path.join(os.path.dirname(__file__), 'mkinit.py')
    subprocess.run([sys.executable, mkinit_script, obj_path, shell_bin], check=True)
    
    bin_dir = os.path.join(root_directory, 'usr/local/bin')
    os.makedirs(bin_dir, exist_ok=True)
    dst_bin = os.path.join(bin_dir, 'topaz-shell')
    shutil.copy2(shell_bin, dst_bin)
    try:
        os.chown(dst_bin, 0, 0)
    except PermissionError:
        pass
    os.chmod(dst_bin, 0o755)
    
    plist_dir = os.path.join(root_directory, 'Library/LaunchDaemons')
    os.makedirs(plist_dir, exist_ok=True)
    dst_plist = os.path.join(plist_dir, 'com.topaz.shell.plist')
    write_plist(dst_plist, {
        'Label': 'com.topaz.shell',
        'Program': '/usr/local/bin/topaz-shell',
        'RunAtLoad': True,
        'KeepAlive': True
    }, 0, 0, 0o644, plistlib.FMT_XML)
    print(f'topaz-shell installed to {dst_bin}')

def stage_system_applications(root_directory):
    src_base = os.path.join(root_directory, 'private/var/staged_system_apps')
    dst_base = os.path.join(root_directory, 'Applications')
    if os.path.isdir(src_base):
        for item in sorted(os.listdir(src_base)):
            if item.endswith('.app'):
                src_path = os.path.join(src_base, item)
                dst_path = os.path.join(dst_base, item)
                if not os.path.exists(dst_path):
                    shutil.copytree(src_path, dst_path, symlinks=True)
                    print(f'staged app: {item} -> /Applications/')
    camera_plist = os.path.join(root_directory, 'Applications/Camera.app/Info.plist')
    if os.path.exists(camera_plist):
        d = read_plist(camera_plist)
        if 'SBAppTags' in d:
            del d['SBAppTags']
            write_plist(camera_plist, d, 0, 0, 0o644, plistlib.FMT_XML)
            print('Camera.app: SBAppTags removed')

def main():
    if len(sys.argv) != 2 or not os.path.isdir(os.path.join(sys.argv[1], 'System/Library/xpc')):
        sys.exit(f'Usage: {sys.argv[0]} MOUNTED_IOS_ROOT')
        
    ios_root = sys.argv[1]
    configure_launchd(ios_root)
    ensure_containers(ios_root)
    ensure_system_directories(ios_root)
    seed_mobileactivation(ios_root)
    configure_audio_stack(ios_root)
    install_topaz_shell(ios_root)
    stage_system_applications(ios_root)
    
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
    update_preferences(ios_root, 'com.apple.Accessibility', {
        'EnhancedBackgroundContrastEnabled': True,
        'ReduceMotionEnabled': True,
        'ReduceMotionAutoplayMessagesEffectsEnabled': False,
        'ReduceMotionAutoplayVideoPreviewsEnabled': False
    })
    update_preferences(ios_root, 'com.apple.UIKit', {
        'UIAnimationDragCoefficient': 0.1
    })
    update_preferences(ios_root, '.GlobalPreferences', {
        'UIAnimationDragCoefficient': 0.1
    })

if __name__ == '__main__':
    main()
