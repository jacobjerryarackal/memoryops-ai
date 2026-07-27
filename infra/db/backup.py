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
    print("Starting PostgreSQL database backup...")
    
    # 1. Verify Docker container is running
    container_name = "memoryops-postgres"
    check_container = run_cmd(["docker", "ps", "-q", "-f", f"name={container_name}"])
    if not check_container.stdout.strip():
        print(f"Error: Docker container '{container_name}' is not running.")
        sys.exit(1)
        
    print(f"Docker container '{container_name}' is active.")
    
    # 2. Run pg_dump inside the container
    container_dump_path = "/tmp/db_backup.dump"
    print(f"Executing pg_dump inside container...")
    dump_cmd = [
        "docker", "exec", container_name,
        "pg_dump", "-U", "postgres", "-d", "memoryops_ai", "-F", "c", "-f", container_dump_path
    ]
    res_dump = run_cmd(dump_cmd)
    if res_dump.returncode != 0:
        print("Error executing pg_dump inside container:")
        print(res_dump.stderr)
        sys.exit(1)
        
    # 3. Copy dump file from container to local workspace
    print(f"Copying backup file to local workspace...")
    cp_cmd = ["docker", "cp", f"{container_name}:{container_dump_path}", str(backup_file)]
    res_cp = run_cmd(cp_cmd)
    if res_cp.returncode != 0:
        print("Error copying backup file from container:")
        print(res_cp.stderr)
        sys.exit(1)
        
    # 4. Clean up temporary file in the container
    print("Cleaning up temporary backup file in container...")
    rm_cmd = ["docker", "exec", container_name, "rm", container_dump_path]
    run_cmd(rm_cmd)
    
    # 5. Verify local backup file integrity
    if not backup_file.exists():
        print("Error: Local backup file was not created.")
        sys.exit(1)
        
    file_size = backup_file.stat().st_size
    if file_size == 0:
        print("Error: Local backup file is empty (0 bytes).")
        sys.exit(1)
        
    # Check magic header for custom format pg_dump file (starts with 'PGDMP')
    with open(backup_file, "rb") as f:
        header = f.read(5)
        
    if header != b"PGDMP":
        print(f"Error: Backup file integrity check failed. Bad header: {header}")
        sys.exit(1)
        
    print(f"Database backup completed successfully.")
    print(f"Backup file location: {backup_file}")
    print(f"Backup file size: {file_size} bytes")


if __name__ == "__main__":
    main()
