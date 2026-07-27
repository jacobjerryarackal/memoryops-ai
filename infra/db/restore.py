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
    print("Starting database restore procedure...")
    
    # 1. Verify backup file exists locally
    if not backup_file.exists():
        print(f"Error: Backup file does not exist at {backup_file}")
        sys.exit(1)
        
    # 2. Verify Docker container is running
    container_name = "memoryops-postgres"
    check_container = run_cmd(["docker", "ps", "-q", "-f", f"name={container_name}"])
    if not check_container.stdout.strip():
        print(f"Error: Docker container '{container_name}' is not running.")
        sys.exit(1)
        
    print(f"Docker container '{container_name}' is active.")
    
    # 3. Copy dump file into container
    container_restore_path = "/tmp/db_restore.dump"
    print("Copying backup file to container...")
    cp_cmd = ["docker", "cp", str(backup_file), f"{container_name}:{container_restore_path}"]
    res_cp = run_cmd(cp_cmd)
    if res_cp.returncode != 0:
        print("Error copying file to container:")
        print(res_cp.stderr)
        sys.exit(1)
        
    # 4. Terminate active connections to database
    print("Terminating active connections to 'memoryops_ai'...")
    term_sql = (
        "SELECT pg_terminate_backend(pid) "
        "FROM pg_stat_activity "
        "WHERE datname = 'memoryops_ai' AND pid <> pg_backend_pid();"
    )
    term_cmd = ["docker", "exec", container_name, "psql", "-U", "postgres", "-c", term_sql]
    run_cmd(term_cmd)
    
    # 5. Drop and Recreate database
    print("Dropping database 'memoryops_ai' if exists...")
    drop_cmd = ["docker", "exec", container_name, "psql", "-U", "postgres", "-c", "DROP DATABASE IF EXISTS memoryops_ai;"]
    res_drop = run_cmd(drop_cmd)
    if res_drop.returncode != 0:
        print("Error dropping database:")
        print(res_drop.stderr)
        # Cleanup container file before exit
        run_cmd(["docker", "exec", container_name, "rm", container_restore_path])
        sys.exit(1)
        
    print("Creating database 'memoryops_ai'...")
    create_cmd = ["docker", "exec", container_name, "psql", "-U", "postgres", "-c", "CREATE DATABASE memoryops_ai;"]
    res_create = run_cmd(create_cmd)
    if res_create.returncode != 0:
        print("Error creating database:")
        print(res_create.stderr)
        run_cmd(["docker", "exec", container_name, "rm", container_restore_path])
        sys.exit(1)
        
    # 6. Execute pg_restore inside container
    print("Executing pg_restore inside container...")
    restore_cmd = [
        "docker", "exec", container_name,
        "pg_restore", "-U", "postgres", "-d", "memoryops_ai", container_restore_path
    ]
    res_restore = run_cmd(restore_cmd)
    
    # Clean up container file
    print("Cleaning up temporary file in container...")
    run_cmd(["docker", "exec", container_name, "rm", container_restore_path])
    
    if res_restore.returncode != 0:
        # Note: pg_restore sometimes returns warnings (non-zero or exit code 1) which might be acceptable,
        # but let's output the warning / error for full transparency.
        print("pg_restore output / warnings:")
        print(res_restore.stderr)
        
    print("Database restore completed successfully.")


if __name__ == "__main__":
    main()
