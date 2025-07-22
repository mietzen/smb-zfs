from . import SmbZfsError


class ZFS:
    def __init__(self, system_helper):
        self._system = system_helper

    def dataset_exists(self, dataset):
        result = self._system._run(
            ["zfs", "list", "-H", "-o", "name", dataset], check=False
        )
        return result.returncode == 0

    def get_mountpoint(self, dataset):
        if not self.dataset_exists(dataset):
            raise SmbZfsError(f"Dataset '{dataset}' does not exist.")
        result = self._system._run(
            ["zfs", "get", "-H", "-o", "value", "mountpoint", dataset]
        )
        return result.stdout.strip()

    def create_dataset(self, dataset):
        if not self.dataset_exists(dataset):
            self._system._run(["zfs", "create", dataset])

    def destroy_dataset(self, dataset):
        if self.dataset_exists(dataset):
            self._system._run(["zfs", "destroy", "-r", dataset])
