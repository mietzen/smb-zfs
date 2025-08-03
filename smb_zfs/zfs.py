import time
import subprocess
import logging
from typing import List, Optional
from .system import System
from .errors import ZfsCmdError

# --- Logger Setup ---
logger = logging.getLogger(__name__)


class Zfs:
    """A helper class to interact with ZFS command-line tools."""

    def __init__(self, system_helper: System) -> None:
        """Initializes the Zfs helper."""
        self._system = system_helper
        logger.debug("Zfs helper initialized.")

    def list_pools(self) -> List[str]:
        """Lists all available ZFS storage pools."""
        logger.debug("Listing all ZFS pools.")
        result = self._system._run(["zpool", "list", "-H", "-o", "name"])
        if result.stdout:
            pools = result.stdout.strip().split('\n')
            logger.info("Found ZFS pools: %s", pools)
            return pools
        logger.info("No ZFS pools found.")
        return []

    def dataset_exists(self, dataset: str) -> bool:
        """Checks if a ZFS dataset or volume exists."""
        logger.debug("Checking for existence of dataset: %s", dataset)
        result = self._system._run(
            ["zfs", "list", "-H", "-o", "name", "-t", "filesystem", dataset],
            check=False
        )
        return result.returncode == 0

    def snapshot_exists(self, snapshot: str) -> bool:
        """Checks if a ZFS snapshot exists."""
        logger.debug("Checking for existence of snapshot: %s", snapshot)
        result = self._system._run(
            ["zfs", "list", "-H", "-o", "name", "-t", "snapshot", snapshot],
            check=False
        )
        return result.returncode == 0

    def list_snapshots(self, dataset: str) -> List[str]:
        """Lists all snapshots for a given dataset."""
        logger.debug("Listing snapshots for dataset: %s", dataset)
        result = self._system._run(
            ["zfs", "list", "-H", "-r", "-t", "snapshot", "-o", "name", dataset],
            check=False
        )
        if result.returncode == 0 and result.stdout:
            snapshots = result.stdout.strip().split('\n')
            logger.info("Found snapshots for %s: %s", dataset, snapshots)
            return snapshots
        logger.info("No snapshots found for dataset: %s", dataset)
        return []

    def _get_zfs_property(self, target: str, prop: str) -> Optional[str]:
        """Helper to get a single ZFS property value. Returns None on failure."""
        logger.debug("Getting ZFS property '%s' for target '%s'.", prop, target)
        result = self._system._run(
            ["zfs", "get", "-H", "-p", "-o", "value", prop, target],
            check=False
        )
        if result.returncode == 0:
            value = result.stdout.strip()
            logger.debug("Property '%s' for '%s' is '%s'.", prop, target, value)
            return value
        logger.warning("Could not get ZFS property '%s' for target '%s'.", prop, target)
        return None

    def get_mountpoint(self, dataset: str) -> str:
        """Gets the mountpoint property for a given dataset."""
        logger.debug("Getting mountpoint for dataset: %s", dataset)
        result = self._system._run(
            ["zfs", "get", "-H", "-o", "value", "mountpoint", dataset]
        )
        mountpoint = result.stdout.strip()
        logger.info("Mountpoint for %s is %s.", dataset, mountpoint)
        return mountpoint

    def create_dataset(self, dataset: str) -> None:
        """Creates a ZFS dataset, including parent datasets."""
        logger.info("Creating ZFS dataset: %s", dataset)
        self._system._run(["zfs", "create", "-p", dataset])
        logger.info("Successfully created dataset: %s", dataset)

    def destroy_dataset(self, dataset: str) -> None:
        """Destroys a ZFS dataset and all its children."""
        if self.dataset_exists(dataset):
            logger.warning(
                "Destroying ZFS dataset and all its children: %s", dataset)
            self._system._run(["zfs", "destroy", "-r", dataset])
            logger.info("Successfully destroyed dataset: %s", dataset)
        else:
            logger.warning(
                "Attempted to destroy non-existent dataset: %s", dataset)

    def set_quota(self, dataset: str, quota: str) -> None:
        """Sets a quota on a ZFS dataset."""
        if self.dataset_exists(dataset):
            logger.info("Setting quota to '%s' on dataset: %s", quota, dataset)
            self._system._run(["zfs", "set", f"quota={quota}", dataset])
            logger.info("Successfully set quota on %s.", dataset)
        else:
            logger.warning(
                "Attempted to set quota on non-existent dataset: %s", dataset)

    def get_quota(self, dataset: str) -> Optional[str]:
        """Gets the quota for a ZFS dataset."""
        logger.debug("Getting quota for dataset: %s", dataset)
        if self.dataset_exists(dataset):
            result = self._system._run(
                ["zfs", "get", "-H", "-o", "value", "quota", dataset]
            )
            quota = result.stdout.strip()
            logger.info("Quota for %s is %s.", dataset, quota)
            return quota
        logger.warning(
            "Attempted to get quota for non-existent dataset: %s", dataset)
        return None

    def rename_dataset(self, old_dataset: str, new_dataset: str) -> None:
        """Renames a ZFS dataset."""
        logger.info("Attempting to rename dataset '%s' to '%s'.",
                    old_dataset, new_dataset)
        if not self.dataset_exists(old_dataset):
            raise ZfsCmdError(
                f"Cannot rename: source dataset '{old_dataset}' does not exist.")

        if self.dataset_exists(new_dataset):
            raise ZfsCmdError(
                f"Cannot rename: destination dataset '{new_dataset}' already exists.")

        self._system._run(["zfs", "rename", old_dataset, new_dataset])
        logger.info("Successfully renamed dataset '%s' to '%s'.",
                    old_dataset, new_dataset)

    def move_dataset(self, dataset_path: str, new_pool: str) -> None:
        """Safely moves a ZFS dataset to a new pool with verification."""
        logger.info("Attempting to move dataset '%s' to pool '%s'.", dataset_path, new_pool)

        # Validate source dataset
        if not self.dataset_exists(dataset_path):
            raise ZfsCmdError(f"Source dataset '{dataset_path}' does not exist.")

        # Validate destination pool using pool list, not dataset check
        pools = self.list_pools()
        if new_pool not in pools:
            raise ZfsCmdError(f"Destination pool '{new_pool}' does not exist.")

        # Space checks: require properties to exist
        used_str = self._get_zfs_property(dataset_path, 'used')
        avail_str = self._get_zfs_property(new_pool, 'available')
        if used_str is None or avail_str is None:
            raise ZfsCmdError("Failed to retrieve required ZFS properties for space check.")
        required_bytes = int(used_str)
        available_bytes = int(avail_str)
        logger.debug("Space check: Required=%d, Available=%d on pool %s.", required_bytes, available_bytes, new_pool)

        if required_bytes > available_bytes:
            raise ZfsCmdError(
                f"Not enough space on pool '{new_pool}'. "
                f"Required: {required_bytes}, Available: {available_bytes}"
            )

        # Ensure parent path exists on destination pool
        base_dataset_name = dataset_path.split('/')[1:]
        new_path = [new_pool]
        for path in base_dataset_name[:-1]:
            new_path.append(path)
            self.create_dataset('/'.join(new_path))

        snapshot_name = f"moving_{int(time.time())}"
        source_snapshot = f"{dataset_path}@{snapshot_name}"
        dest_dataset = f"{new_pool}/{'/'.join(base_dataset_name)}"
        dest_snapshot = f"{dest_dataset}@{snapshot_name}"
        logger.debug("Using source snapshot '%s' and destination dataset '%s'.", source_snapshot, dest_dataset)

        if self.dataset_exists(dest_dataset):
            raise ZfsCmdError(
                f"Destination dataset '{dest_dataset}' already exists. Please remove it first."
            )

        try:
            logger.info("Creating source snapshot: %s", source_snapshot)
            self._system._run(["zfs", "snapshot", source_snapshot])
            logger.info("Sending snapshot from '%s' to '%s'.", source_snapshot, dest_dataset)
            self._system._run_piped(
                [["zfs", "send", source_snapshot], ["zfs", "recv", "-F", dest_dataset]]
            )

            logger.info("Verifying data integrity via snapshot GUIDs.")
            source_guid = self._get_zfs_property(source_snapshot, 'guid')
            dest_guid = self._get_zfs_property(dest_snapshot, 'guid')
            logger.debug("Source GUID: %s, Destination GUID: %s", source_guid, dest_guid)

            if source_guid is None or dest_guid is None or source_guid != dest_guid:
                raise ZfsCmdError(
                    "Verification failed! Snapshot GUIDs do not match. "
                    f"Source: {source_guid}, Dest: {dest_guid}"
                )
            logger.info("Verification successful. GUIDs match.")

            logger.warning("Destroying original source dataset: %s", dataset_path)
            self._system._run(["zfs", "destroy", "-r", dataset_path])
            logger.debug("Destroying temporary destination snapshot: %s", dest_snapshot)
            self._system._run(["zfs", "destroy", dest_snapshot])
            logger.info("Dataset move completed successfully.")

        except (subprocess.CalledProcessError, ZfsCmdError) as e:
            logger.error("ZFS move failed. Initiating rollback.", exc_info=True)
            if self.dataset_exists(dest_dataset):
                logger.warning("Rolling back: destroying partially received dataset '%s'.", dest_dataset)
                self._system._run(["zfs", "destroy", "-r", dest_dataset], check=False)

            if self.snapshot_exists(source_snapshot):
                logger.warning("Rolling back: destroying source snapshot '%s'.", source_snapshot)
                self._system._run(["zfs", "destroy", source_snapshot], check=False)

            raise ZfsCmdError("ZFS move failed and has been rolled back.") from e
