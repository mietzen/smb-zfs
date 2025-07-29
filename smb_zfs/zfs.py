import time
import subprocess
from typing import List, Optional
from .system import System
from .errors import ZfsCmdError


class Zfs:
    def __init__(self, system_helper: System) -> None:
        """Initializes the Zfs helper."""
        self._system = system_helper

    def list_pools(self) -> List[str]:
        """Lists all available ZFS storage pools."""
        result = self._system._run(["zpool", "list", "-H", "-o", "name"])
        if result.stdout:
            return result.stdout.strip().split('\n')
        return []

    def dataset_exists(self, dataset: str) -> bool:
        """Checks if a ZFS dataset or volume exists."""
        result = self._system._run(
            ["zfs", "list", "-H", "-o", "name", "-t", "filesystem", dataset],
            check=False
        )
        return result.returncode == 0

    def snapshot_exists(self, snapshot: str) -> bool:
        """Checks if a ZFS snapshot exists."""
        result = self._system._run(
            ["zfs", "list", "-H", "-o", "name", "-t", "snapshot", snapshot],
            check=False
        )
        return result.returncode == 0

    def list_snapshots(self, dataset: str) -> List[str]:
        """Lists all snapshots for a given dataset."""
        result = self._system._run(
            ["zfs", "list", "-H", "-r", "-t", "snapshot", "-o", "name", dataset],
            check=False
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.strip().split('\n')
        return []

    def _get_zfs_property(self, target: str, prop: str) -> str:
        """Helper to get a single ZFS property value."""
        result = self._system._run(
            ["zfs", "get", "-H", "-p", "-o", "value", prop, target],
            check=False
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return "0"

    def get_mountpoint(self, dataset: str) -> str:
        """Gets the mountpoint property for a given dataset."""
        result = self._system._run(
            ["zfs", "get", "-H", "-o", "value", "mountpoint", dataset]
        )
        return result.stdout.strip()

    def create_dataset(self, dataset: str) -> None:
        """Creates a ZFS dataset, including parent datasets."""
        self._system._run(["zfs", "create", "-p", dataset])

    def destroy_dataset(self, dataset: str) -> None:
        """Destroys a ZFS dataset and all its children."""
        if self.dataset_exists(dataset):
            self._system._run(["zfs", "destroy", "-r", dataset])

    def set_quota(self, dataset: str, quota: str) -> None:
        """Sets a quota on a ZFS dataset."""
        if self.dataset_exists(dataset):
            self._system._run(["zfs", "set", f"quota={quota}", dataset])

    def get_quota(self, dataset: str) -> Optional[str]:
        """Gets the quota for a ZFS dataset."""
        if self.dataset_exists(dataset):
            result = self._system._run(
                ["zfs", "get", "-H", "-o", "value", "quota", dataset]
            )
            return result.stdout.strip()
        return None

    def rename_dataset(self, old_dataset: str, new_dataset: str) -> None:
        """Renames a ZFS dataset."""
        if not self.dataset_exists(old_dataset):
            raise ZfsCmdError(
                f"Cannot rename: source dataset '{old_dataset}' does not exist.")

        if self.dataset_exists(new_dataset):
            raise ZfsCmdError(
                f"Cannot rename: destination dataset '{new_dataset}' already exists.")

        self._system._run(["zfs", "rename", old_dataset, new_dataset])

    def move_dataset(self, dataset_path: str, new_pool: str) -> None:
        """Safely moves a ZFS dataset to a new pool with verification."""
        if not self.dataset_exists(dataset_path):
            raise ZfsCmdError(
                f"Source dataset '{dataset_path}' does not exist.")

        if not self.dataset_exists(new_pool):
            raise ZfsCmdError(f"Destination pool '{new_pool}' does not exist.")

        required_bytes = int(self._get_zfs_property(dataset_path, 'used'))
        available_bytes = int(self._get_zfs_property(new_pool, 'available'))

        if required_bytes > available_bytes:
            raise ZfsCmdError(
                f"Not enough space on pool '{new_pool}'. "
                f"Required: {required_bytes}, Available: {available_bytes}"
            )

        base_dataset_name = dataset_path.split('/')[1:]
        new_path = [new_pool]
        for path in base_dataset_name[:-1]:
            new_path += [path]
            self.create_dataset('/'.join(new_path))
        
        snapshot_name = f"moving_{int(time.time())}"

        source_snapshot = f"{dataset_path}@{snapshot_name}"
        dest_dataset = f"{new_pool}/{'/'.join(base_dataset_name)}"
        dest_snapshot = f"{dest_dataset}@{snapshot_name}"

        if self.dataset_exists(dest_dataset):
            raise ZfsCmdError(
                f"Destination dataset '{dest_dataset}' already exists. Please remove it first.")

        try:
            self._system._run(["zfs", "snapshot", source_snapshot])
            self._system._run_piped(
                [["zfs", "send", source_snapshot], [
                    "zfs", "recv", "-F", dest_dataset]]
            )

            source_guid = self._get_zfs_property(source_snapshot, 'guid')
            dest_guid = self._get_zfs_property(dest_snapshot, 'guid')

            if source_guid == "0" or dest_guid == "0" or source_guid != dest_guid:
                raise ZfsCmdError(
                    "Verification failed! Snapshot GUIDs do not match. "
                    f"Source: {source_guid}, Dest: {dest_guid}"
                )

            self._system._run(["zfs", "destroy", "-r", dataset_path])
            self._system._run(["zfs", "destroy", dest_snapshot])

        except (subprocess.CalledProcessError, ZfsCmdError) as e:
            if self.dataset_exists(dest_dataset):
                self._system._run(
                    ["zfs", "destroy", "-r", dest_dataset], check=False)

            if self.snapshot_exists(source_snapshot):
                self._system._run(
                    ["zfs", "destroy", source_snapshot], check=False)

            raise ZfsCmdError(
                "ZFS move failed and has been rolled back.") from e
