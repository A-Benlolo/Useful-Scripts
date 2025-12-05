import datetime
import json
import logging
import os
import subprocess
from pathlib import Path


PASSWORD = 'redacted' # hardcoded is fine... if someone has access to this file, they have access to the plaintext files anyway
USERNAME = 'redacted'
logger = logging.getLogger(__name__)


"""
Wrapper for a backup job
"""
class BackupJob():
    def __init__(self, local_path: Path, cloud_path: Path, name: str, compression_level: int = 3):
        self.local_path = local_path
        self.cloud_path = cloud_path
        self.name = name
        self.compression_level = compression_level


"""
Create an ZSTD compressed tar ball from a source directory
"""
def make_tar_zst(src: Path, dst: Path, level: int) -> None:
    assert level > 0 and level < 20
    subprocess.run(['/usr/bin/tar', '-I', f'zstd -{level}', '-cf', dst, '-C', src, '.'], check=True)
    return


"""
Encrypt an archive using OpenSSL, deleting the plaintext in the process
"""
def encrypt_file(src: Path, passwd: str) -> Path:
    dst = src.with_suffix('.zst.enc')
    subprocess.run([
        '/usr/bin/openssl',
        'enc', '-aes-256-cbc', '-salt', '-pbkdf2',
        '-pass', f'pass:"{passwd}"',
        '-in', src, '-out', dst
    ], check=True)
    os.remove(src)
    return dst


"""
Get the most recent time a directory tree was modified
"""
def newest_mtime(root: Path) -> int:
    times = [p.stat().st_mtime for p in root.rglob('*')]
    return int(max(times)) if times else int(root.stat().st_mtime)


"""
Use megatools to get matching file names in a Mega directory
"""
def get_mega_names(root: Path, name: str) -> list:
    lsf = subprocess.run(['/usr/bin/megatools', 'ls', '--reload', f'/Root{root}'], capture_output=True, text=True)
    assert not lsf.stderr, lsf.stderr
    file_list = lsf.stdout.split('\n')[1:-1]
    name_key = f'_{name}_'
    return [f for f in file_list if name_key in f]


"""
Rename an archive in Mega
"""
def rename_archive(job: BackupJob, prev_name: str, curr_name: str) -> None:
    curr_name = f'{curr_name}.tar.zst.enc'
    logger.info(f'Updating file name to "{curr_name}" to reflect newer date')
    moveto = subprocess.run([
        '/usr/bin/rclone', 'moveto',
        f'mega:{prev_name[5:]}', f'mega:{job.cloud_path / curr_name}'
    ], capture_output=True, text=True)
    assert not moveto.stderr, moveto.stderr


"""
Create and push a new archive to Mega
"""
def create_archive(job: BackupJob, prev_name: str, curr_name: str, passwd: str) -> None:
    # The temporary directory should be in the ZFS pool
    temp_path = Path('/mnt/media_tmp')

    # Create a local archive
    archive_plain = temp_path / f'{curr_name}.tar.zst'
    logger.info(f'Compressing {job.local_path}')
    make_tar_zst(job.local_path, archive_plain, job.compression_level)

    # Encrypt the local archive, deleting the plaintext version
    logger.info(f'Encrypting {archive_plain}')
    archive_cipher = encrypt_file(archive_plain, passwd)

    # Delete existing archive in cloud
    if prev_name is not None:
        logger.info(f'Deleting {job.cloud_path / prev_name}')
        rm = subprocess.run([
            '/usr/bin/megatools', 'rm', f'{job.cloud_path / prev_name}'
        ], capture_output=True, text=True)
        assert not rm.stderr, rm.stderr

    # Push the local, encrypted archive to cloud
    archive_cipher_cloud = job.cloud_path / os.path.basename(archive_cipher)
    logger.info(f'Pushing {archive_cipher} to /Root{archive_cipher_cloud}')
    put = subprocess.run([
        '/usr/bin/megatools', 'put', '--no-progress', '--reload',
        archive_cipher, '--path', f'/Root{archive_cipher_cloud}'
    ], capture_output=True, text=True)
    assert not put.stderr, put.stderr
    os.remove(archive_cipher)


"""
Driver function
"""
def main() -> None:
    # Define the backup jobs
    jobs = []
    with open(f'/home/{USERNAME}/Documents/backup/jobs.json', 'r') as f:
        data = json.load(f)
    for entry in data:
        jobs.append(BackupJob( Path(entry['src']), Path(entry['dst']), str(entry['name']), int(entry['compression_level']) ))

    # Get the current date
    date_str = datetime.datetime.now().strftime('%Y%m%d')

    # Perform the backup jobs
    for job in jobs:
        # Get the latest modification time for the local job tree
        curr_mtime = newest_mtime(job.local_path)
        curr_name = f'{date_str}_{job.name}_{curr_mtime}'

        # Get files from Mega that match the job's name
        logger.info(f'Getting previous file names for {job.name}')
        try:
            history = get_mega_names(job.cloud_path, job.name)
            assert len(history) < 2, f'Too many matches: {history}'
        except Exception as e:
            logger.error(f'Error getting previous version of {job.name} in {job.cloud_path}.')
            logger.error(e)
            logger.error('Refusing to proceed with this job!')
            continue

        # If there are previous versions...
        if len(history) > 0:
            # Extract the previous version's modification time
            prev_name = history[0]
            prev_mtime = int(prev_name.split('_')[-1].split('.')[0])
            prev_basename = '_'.join(prev_name.split('_')[1:])

            # No modifications have occurred since last push; rename the existing version
            if prev_mtime >= curr_mtime:
                logger.info(f'Archive consistent with last push')
                try:
                    rename_archive(job, prev_name, curr_name)
                except Exception as e:
                    logger.error(f'Failed to rename mega:{job.cloud_path / prev_name}')
                    logger.error(e)

            # Modifications have occurred; recreate and push archive
            else:
                logger.info(f'{job.name} has changed since last push')
                try:
                    create_archive(job, prev_name, curr_name, PASSWORD)
                except Exception as e:
                    logger.error(f'Error while creating archive. Refusing to commit')
                    logger.error(e)
                    continue

        # If there are no previous versions, start anew
        else:
            logger.info(f'{job.name} does not exist in the Mega')
            try:
                create_archive(job, None, curr_name, PASSWORD)
            except Exception as e:
                logger.error(f'Error while creating archive. Refusing to commit')
                logger.error(e)
                continue


"""
Entry point
"""
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(name)s:%(funcName)s %(asctime)s] (%(levelname)s) %(message)s",
        datefmt="%H:%M:%S"
    )
    logger.info('Started')
    main()
    logger.info('Finished')
