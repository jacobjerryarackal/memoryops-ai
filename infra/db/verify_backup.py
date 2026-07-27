import os
import sys
import subprocess
from pathlib import Path

# Ensure infra/db directory exists
db_dir = Path(__file__).parent.resolve()
backup_file = db_dir / "backup.dump"


def run_cmd(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    print("Starting backup integrity validation...")
    
    # 1. Structural Checks
    if not backup_file.exists():
        print(f"Error: Backup file does not exist at {backup_file}")
        sys.exit(1)
        
    file_size = backup_file.stat().st_size
    print(f"Backup file exists: size={file_size} bytes")
    if file_size < 100:
        print("Error: Backup file size is suspiciously small.")
        sys.exit(1)
        
    # Check magic header
    with open(backup_file, "rb") as f:
        header = f.read(5)
    if header != b"PGDMP":
        print(f"Error: Backup file integrity check failed. Bad header: {header}")
        sys.exit(1)
        
    print("Backup file magic header 'PGDMP' matches.")
    
    # 2. Logical TOC Verification (runs pg_restore -l inside container)
    container_name = "memoryops-postgres"
    check_container = run_cmd(["docker", "ps", "-q", "-f", f"name={container_name}"])
    if not check_container.stdout.strip():
        print(f"Warning: Docker container '{container_name}' is not running. Skipping TOC verification.")
        print("Backup structural integrity is verified, but logical TOC was skipped.")
        sys.exit(0)
        
    container_verify_path = "/tmp/verify_backup.dump"
    
    # Copy file to container for testing
    cp_cmd = ["docker", "cp", str(backup_file), f"{container_name}:{container_verify_path}"]
    res_cp = run_cmd(cp_cmd)
    if res_cp.returncode != 0:
        print("Error copying file to container for verification:")
        print(res_cp.stderr)
        sys.exit(1)
        
    # Run pg_restore -l (list contents)
    verify_cmd = ["docker", "exec", container_name, "pg_restore", "-l", container_verify_path]
    res_verify = run_cmd(verify_cmd)
    
    # Cleanup file in container
    rm_cmd = ["docker", "exec", container_name, "rm", container_verify_path]
    run_cmd(rm_cmd)
    
    if res_verify.returncode != 0:
        print("Error: Backup logical verification failed (pg_restore -l returned non-zero):")
        print(res_verify.stderr)
        sys.exit(1)
        
    print("Backup logical verification (pg_restore -l table of contents check) passed.")
    print("Backup integrity verified successfully. Ready for restore.")


if __name__ == "__main__":
    main()
